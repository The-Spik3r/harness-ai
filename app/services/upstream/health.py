"""Per-provider circuit breakers and the health read (PRD-022 6.10, F6, F9, D12).

One `CircuitBreaker` (PRD-018, `probe=None`) per provider name, created lazily and
held in a process-local registry; this module adds no second state machine. It
holds the recording rules (`record`), a mapped admit/deny (`admit`), process-local
counters, and `providers_status()`, the read STORY-015 renders.

**Pure.** Stdlib, `circuit_breaker` and `upstream.types` only: no settings, no I/O.
It never asks the provider registry which names exist (in legacy mode that reads
settings); the caller passes them to `sync(names)` / `providers_status(names)`,
and a provider missing from them loses its breaker (PRD-022 6.10 pruning).

**Locks.** `_lock` guards the registry dict and the counters and is held only for
those reads and writes, never across a breaker call (a breaker's `on_transition`
hook runs after the breaker's own lock is released and then takes `_lock`: no
nesting, no deadlock). Each entry also has a `record_lock` that makes
"record_failure, then read status, then extend" one critical section against other
`record()` calls, so two concurrent extensions cannot interleave a stale read into
a shortening window.

**Nothing here carries text.** A breaker only ever sees a `kind` word (or
`unclassified`), never a message, a prompt or a key (PRD-022 T10).
"""

import logging
import os
import socket
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Optional

from app.services.circuit_breaker import (
    BreakerOpen,
    BreakerStatus,
    CircuitBreaker,
)
from app.services.upstream.types import UpstreamError

# PRD-022 9.3: a provider breaker opens after five consecutive eligible failures
# and stays open ten seconds; a half-open trial is one real request.
_BREAKER_FAILURE_THRESHOLD = 5
_BREAKER_OPEN_SECONDS = 10.0
# PRD-022 D12: a provider whose own key or account is refused (`misconfigured`,
# 401/403 -- never a client's fault) will not heal in seconds: open it for five
# minutes at once instead of probing it every ten.
_PROVIDER_MISCONFIGURED_OPEN_SECONDS = 300

# PRD-022 6.7: why a candidate was skipped without being called.
SKIP_REASONS = (
    "open",
    "half_open_busy",
    "forbidden",
    "capability",
    "byok",
    "redaction_limit",
    "deadline",
)

_UNCLASSIFIED = "unclassified"


@dataclass
class _Entry:
    breaker: CircuitBreaker
    record_lock: threading.Lock


_lock = threading.Lock()
_entries: dict[str, _Entry] = {}
_clock: Callable[[], float] = time.monotonic
_attempts_failed: dict[str, int] = {}
_skipped: dict[str, int] = {}
_fallback_answers = 0
_breaker_opens = 0


def _now() -> float:
    return _clock()


def reset(clock: Optional[Callable[[], float]] = None) -> None:
    """Drop every breaker and counter and set the clock (tests; reads no setting)."""
    global _clock, _fallback_answers, _breaker_opens
    with _lock:
        _entries.clear()
        _attempts_failed.clear()
        _skipped.clear()
        _fallback_answers = 0
        _breaker_opens = 0
        _clock = clock if clock is not None else time.monotonic


def _count_open(frm: str, to: str, cls: str) -> None:
    """The breaker's `on_transition` hook: every transition into `open` (D12)."""
    global _breaker_opens
    if to == "open":
        with _lock:
            _breaker_opens += 1


def _new_breaker(name: str) -> CircuitBreaker:
    return CircuitBreaker(
        name,
        _BREAKER_FAILURE_THRESHOLD,
        _BREAKER_OPEN_SECONDS,
        clock=lambda: _now(),
        probe=None,
        on_transition=_count_open,
        # PRD-022 F9: every provider transition, a recovery included, is one
        # WARNING line naming provider, from, to and kind.
        transition_log_level=logging.WARNING,
    )


def _entry(name: str) -> _Entry:
    with _lock:
        entry = _entries.get(name)
        if entry is None:
            entry = _entries[name] = _Entry(_new_breaker(name), threading.Lock())
        return entry


def breaker(name: str) -> CircuitBreaker:
    """The provider's breaker, created closed on first use; identity-stable."""
    return _entry(name).breaker


def sync(names: Iterable[str]) -> None:
    """Drop the breaker of every provider not in `names` (PRD-022 6.10).

    Counters are process-lifetime and are not pruned; only `reset()` clears them.
    """
    keep = set(names)
    with _lock:
        for gone in [n for n in _entries if n not in keep]:
            del _entries[gone]


def _extend(breaker_: CircuitBreaker, seconds: float, kind: str) -> None:
    """Open for at least `seconds`; never shorten a longer window."""
    st = breaker_.status()
    if st.state != "open" or (
        st.retry_after_seconds is not None and seconds > st.retry_after_seconds
    ):
        breaker_.force_open(seconds, failure_class=kind)


def record(name: str, outcome: Optional[UpstreamError]) -> None:
    """Record one attempt's outcome against the provider (PRD-022 6.2, F6).

    `None` is a success. A fault that never falls back (4xx, `shape`,
    `incompatible`, `refusal`) is counted but leaves the breaker alone: it says
    nothing about the provider's health.
    """
    if outcome is None:
        entry = _entry(name)
        with entry.record_lock:
            entry.breaker.record_success()
        return
    kind = outcome.kind or _UNCLASSIFIED
    key = f"{name}:{kind}"
    with _lock:
        _attempts_failed[key] = _attempts_failed.get(key, 0) + 1
    if not outcome.fallback_eligible:
        return
    entry = _entry(name)
    with entry.record_lock:
        entry.breaker.record_failure(kind)
        if kind == "misconfigured":
            _extend(entry.breaker, _PROVIDER_MISCONFIGURED_OPEN_SECONDS, kind)
        elif (
            kind == "status"
            and outcome.retry_after_seconds is not None
            and entry.breaker.status().state == "open"
        ):
            _extend(
                entry.breaker,
                max(outcome.retry_after_seconds, _BREAKER_OPEN_SECONDS),
                kind,
            )


@dataclass(frozen=True)
class Admission:
    """`admit()`'s answer. `reason` is a `SKIP_REASONS` word when denied."""

    admitted: bool
    reason: Optional[str] = None
    retry_after_seconds: Optional[int] = None


def admit(name: str) -> Admission:
    """May a call go to this provider now? (PRD-022 F6)

    The first caller after the open window is the half-open trial and must report
    through `record()`; everyone else is denied until it does. Counts nothing:
    the caller counts the skip (`count_skipped`).
    """
    try:
        breaker(name).before()
    except BreakerOpen as exc:
        reason = "half_open_busy" if exc.state == "half_open" else "open"
        return Admission(False, reason, exc.retry_after_seconds)
    return Admission(True)


def count_skipped(provider: str, reason: str) -> None:
    if reason not in SKIP_REASONS:
        raise ValueError(f"skip reason must be one of {SKIP_REASONS}, got {reason!r}")
    key = f"{provider}:{reason}"
    with _lock:
        _skipped[key] = _skipped.get(key, 0) + 1


def count_fallback_answer() -> None:
    """One request answered by a candidate after the first (attempt > 1)."""
    global _fallback_answers
    with _lock:
        _fallback_answers += 1


@dataclass(frozen=True)
class ProviderCounters:
    attempts_failed: Mapping[str, int]  # "provider:kind"
    fallback_answers: int
    skipped: Mapping[str, int]  # "provider:reason"
    breaker_opens: int


@dataclass(frozen=True)
class ProvidersStatus:
    """STORY-015's contract: the instance, one reading per provider, the counters."""

    instance: str
    providers: Mapping[str, BreakerStatus]
    counters: ProviderCounters


def providers_status(names: Iterable[str]) -> ProvidersStatus:
    """A point-in-time reading of every named provider; no DB, no network (D12)."""
    ordered = list(dict.fromkeys(names))
    sync(ordered)
    readings = {n: breaker(n).status() for n in ordered}
    with _lock:
        counters = ProviderCounters(
            attempts_failed=dict(_attempts_failed),
            fallback_answers=_fallback_answers,
            skipped=dict(_skipped),
            breaker_opens=_breaker_opens,
        )
    return ProvidersStatus(
        instance=f"{socket.gethostname()}:{os.getpid()}",
        providers=readings,
        counters=counters,
    )
