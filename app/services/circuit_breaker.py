"""A process-local circuit breaker (PRD-018 Section 6.5, decisions D6 and D7).

One class. Storage holds one instance (`database._storage_breaker`); PRD-022
holds one per provider, and PRD-019's `/ready` reads `status()`. Nothing here
knows about storage: no settings, no database import, no I/O beyond the stdlib
logger. The constructor has no storage defaults -- the thresholds are the
caller's arguments (PRD-018 6.5).

**A breaker refuses, it never admits (D7).** `before()` raises `BreakerOpen`
while the circuit is open and the caller turns that into its own fail-closed
error. Nothing in a breaker can answer a request on the caller's behalf.

**The half-open probe is claimed under the lock and run outside it.** The
contract reads "the probe runs under the breaker's own lock" so that exactly one
caller runs it. That exclusivity is kept -- the caller that finds the open
window elapsed flips the state to `half_open` and sets `_probing` while it holds
`_lock`, and every other caller sees the claim and is refused -- but the probe
itself runs after `_lock` is released, for two reasons. First, a probe is a
network call that may stall for the driver's whole connect time (there is no read
timeout); holding the lock across it would make every other caller, and
`status()` (which `/ready` calls), block behind it instead of being refused at
once. Second, the probe takes the storage module's `_client_lock`. Because this
breaker never holds its own lock while it runs the probe, and nothing holding
`_client_lock` ever calls the breaker, **no thread holds both locks**, so a
lock-order deadlock cannot exist.

**`probe=None`** is for a breaker whose half-open trial is a real request (PRD-022
providers): the first caller to find the window elapsed is the trial and is
admitted; everyone else is refused until the trial reports through
`record_success()` / `record_failure()`. A trial that never reports (it failed
for a reason the caller does not count) would wedge the breaker, so a trial
older than `open_seconds` is replaced by a new one. A lease protecting those
per-provider breakers, not something storage uses.

Every transition writes one structured log line,
`breaker name=<n> from=<s> to=<s> class=<c>`, emitted after the lock is released
so a slow handler never extends the critical section. It carries no SQL,
parameters or driver text.
"""

import logging
import math
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Literal, Optional

logger = logging.getLogger(__name__)

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

BreakerState = Literal["closed", "open", "half_open"]


def _wall_clock() -> datetime:
    """Seam for `BreakerStatus.since`; the state machine itself reads only `clock`."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class BreakerStatus:
    """A point-in-time reading, a contract with PRD-019 `/ready` and PRD-022.

    Plain values only -- no lock, client or callable -- so it serializes as is.
    `retry_after_seconds` is `None` while closed, whole seconds (>= 1) while
    open, and 1 while half-open. `last_failure_class` is the free string the
    caller passed to `record_failure()` (storage passes a D2 class).
    """

    state: BreakerState
    since: str  # UTC, _TIMESTAMP_FORMAT; the last transition
    consecutive_failures: int
    last_failure_class: Optional[str]
    retry_after_seconds: Optional[int]


class BreakerOpen(Exception):
    """The circuit is open (or its half-open trial is taken): do not call through."""

    def __init__(self, name: str, retry_after_seconds: int) -> None:
        self.name = name
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"{name} circuit breaker is open; retry after {retry_after_seconds} s"
        )


# (from, to, class) -- computed under the lock, logged after it is released.
_Transition = tuple[str, str, str]


class CircuitBreaker:
    """closed -> open after `failure_threshold` consecutive failures -> half_open.

    See the module docstring for the locking rule. `clock` is monotonic seconds
    and is injected so tests drive time without sleeping. `probe`, when set, is
    run once by the caller that finds the open window elapsed; it returns True
    to close the circuit, False to reopen it, and if it raises the circuit is
    reopened and the exception propagates (never stuck half-open).

    `on_transition`, when set, is called with `(from, to, class)` for every
    transition after the lock is released (same place as the log line), so a
    caller can count transitions without this class knowing what it protects
    (PRD-018 STORY-012: storage counts `breaker_opens`). A hook that raises is
    logged and swallowed: it can never break the breaker.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int,
        open_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        probe: Optional[Callable[[], bool]] = None,
        on_transition: Optional[Callable[[str, str, str], None]] = None,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError(
                f"circuit breaker {name!r}: failure_threshold must be >= 1, "
                f"got {failure_threshold}"
            )
        if open_seconds <= 0:
            raise ValueError(
                f"circuit breaker {name!r}: open_seconds must be > 0, "
                f"got {open_seconds}"
            )
        self._name = name
        self._threshold = failure_threshold
        self._open_seconds = float(open_seconds)
        self._clock = clock
        self._probe = probe
        self._on_transition = on_transition
        self._lock = threading.Lock()
        self._state: BreakerState = "closed"
        self._since = _wall_clock().strftime(_TIMESTAMP_FORMAT)
        self._failures = 0
        self._last_class: Optional[str] = None
        self._open_until = 0.0
        self._probing = False
        self._trial_claimed_at = 0.0
        self._generation = 0

    @property
    def name(self) -> str:
        return self._name

    # -- internals; every `_`-method below runs with `_lock` held ----------------

    def _retry_after(self, now: float) -> int:
        return max(1, math.ceil(self._open_until - now))

    def _transition(self, to: BreakerState, cls: str) -> _Transition:
        frm = self._state
        self._state = to
        self._since = _wall_clock().strftime(_TIMESTAMP_FORMAT)
        return (frm, to, cls)

    def _open(self, now: float, seconds: float, cls: str) -> _Transition:
        self._open_until = now + seconds
        self._probing = False
        self._generation += 1
        return self._transition("open", cls)

    def _emit(self, transitions: list[_Transition]) -> None:
        for frm, to, cls in transitions:
            logger.log(
                logging.WARNING if to == "open" else logging.INFO,
                "breaker name=%s from=%s to=%s class=%s",
                self._name,
                frm,
                to,
                cls,
            )
            if self._on_transition is not None:
                try:
                    self._on_transition(frm, to, cls)
                except Exception:
                    logger.exception("breaker name=%s on_transition hook failed", self._name)

    # -- public ------------------------------------------------------------------

    def before(self) -> None:
        """Return if the caller may proceed; raise `BreakerOpen` if it may not."""
        transitions: list[_Transition] = []
        claimed: Optional[int] = None
        try:
            with self._lock:
                now = self._clock()
                if self._state == "closed":
                    return
                if self._state == "open":
                    if now < self._open_until:
                        raise BreakerOpen(self._name, self._retry_after(now))
                    transitions.append(self._transition("half_open", "none"))
                    self._trial_claimed_at = now
                    if self._probe is None:
                        self._probing = True
                        return
                    self._probing = True
                    self._generation += 1
                    claimed = self._generation
                else:  # half_open
                    if (
                        self._probe is None
                        and now - self._trial_claimed_at >= self._open_seconds
                    ):
                        # The lease: the previous trial never reported.
                        self._trial_claimed_at = now
                        return
                    raise BreakerOpen(self._name, 1)
        finally:
            self._emit(transitions)
        assert claimed is not None and self._probe is not None
        self._run_probe(claimed)

    def _run_probe(self, generation: int) -> None:
        transitions: list[_Transition] = []
        try:
            try:
                ok = bool(self._probe())  # type: ignore[misc]  # outside the lock
            except BaseException:
                with self._lock:
                    if self._generation == generation and self._state == "half_open":
                        transitions.append(
                            self._open(self._clock(), self._open_seconds, "probe")
                        )
                raise
            with self._lock:
                now = self._clock()
                if self._generation != generation or self._state != "half_open":
                    # A force_open() won while the probe ran: drop the result.
                    if self._state == "open":
                        raise BreakerOpen(self._name, self._retry_after(now))
                    return
                if ok:
                    self._failures = 0
                    self._probing = False
                    transitions.append(self._transition("closed", "none"))
                    return
                transitions.append(self._open(now, self._open_seconds, "probe"))
                raise BreakerOpen(self._name, self._retry_after(now))
        finally:
            self._emit(transitions)

    def record_success(self) -> None:
        transitions: list[_Transition] = []
        with self._lock:
            if self._state == "closed":
                self._failures = 0
            elif self._state == "half_open" and self._probe is None:
                self._failures = 0
                self._probing = False
                transitions.append(self._transition("closed", "none"))
            # open: a straggler that started before the open; no change.
            # half_open with a probe: the probe decides, not a straggler.
        self._emit(transitions)

    def record_failure(self, failure_class: str) -> None:
        transitions: list[_Transition] = []
        with self._lock:
            if self._state == "closed":
                self._failures += 1
                self._last_class = failure_class
                if self._failures >= self._threshold:
                    transitions.append(
                        self._open(self._clock(), self._open_seconds, failure_class)
                    )
            elif self._state == "half_open" and self._probe is None:
                self._failures += 1
                self._last_class = failure_class
                transitions.append(
                    self._open(self._clock(), self._open_seconds, failure_class)
                )
            else:
                # open (or half_open with a probe): a straggler. Remember its
                # class, never extend the window.
                self._last_class = failure_class
        self._emit(transitions)

    def force_open(self, seconds: float) -> None:
        """Open now for `seconds`, whatever the state (PRD-022 provider outages)."""
        transitions: list[_Transition] = []
        with self._lock:
            changed = self._state != "open"
            now = self._clock()
            if changed:
                transitions.append(self._open(now, seconds, "forced"))
            else:
                self._open_until = now + seconds
                self._generation += 1
        self._emit(transitions)

    def status(self) -> BreakerStatus:
        with self._lock:
            now = self._clock()
            if self._state == "closed":
                retry: Optional[int] = None
            elif self._state == "open":
                retry = self._retry_after(now)
            else:
                retry = 1
            return BreakerStatus(
                state=self._state,
                since=self._since,
                consecutive_failures=self._failures,
                last_failure_class=self._last_class,
                retry_after_seconds=retry,
            )
