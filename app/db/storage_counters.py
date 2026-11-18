"""Process-local storage counters (PRD-018 D16, F8).

Plain in-memory integers behind one lock: reset on restart, per process, no
metrics dependency. They answer "is this a blip, an outage or a backlog" in
`GET /storage/status` and the admin console Storage view without a shell.

This is a leaf module on purpose: it imports nothing from `app`, so
`audit_journal.py` (which must not import `database`) and `database.py` (which
reads the journal) can both count into it without a cycle.

Cardinality is bounded: `op` is a string literal at each call site and `cls` is
the closed `FailureClass` vocabulary (`"<op>:<class>"` keys).

Orchestrator rulings (PRD-018 STORY-012):

- `exhausted` also counts retries *refused* (e.g. `NON_IDEMPOTENT` on
  `OUTCOME_UNKNOWN`): one increment per operation that ends in an infrastructure
  failure, placed just before `breaker.record_failure`, so `exhausted` equals the
  number of recorded failures. There is no separate `refused` map.
- `breaker_opens` counts every transition into `open`, a re-open after a failed
  half-open probe included.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

_lock = threading.Lock()
_retries: dict[str, int] = {}
_exhausted: dict[str, int] = {}
_breaker_opens = 0
_journal_appended = 0
_journal_drained = 0
_torn_tail_discarded = 0


@dataclass(frozen=True)
class CounterSnapshot:
    """A copy of every counter; plain values, serializes as is."""

    retries: dict[str, int] = field(default_factory=dict)
    exhausted: dict[str, int] = field(default_factory=dict)
    breaker_opens: int = 0
    journal_appended: int = 0
    journal_drained: int = 0
    torn_tail_discarded: int = 0


def retry(op: str, cls: str) -> None:
    """One retry was scheduled for `op` after a `cls` failure."""
    key = f"{op}:{cls}"
    with _lock:
        _retries[key] = _retries.get(key, 0) + 1


def exhausted(op: str, cls: str) -> None:
    """`op` ended in an infrastructure failure (budget spent or retry refused)."""
    key = f"{op}:{cls}"
    with _lock:
        _exhausted[key] = _exhausted.get(key, 0) + 1


def breaker_opened() -> None:
    global _breaker_opens
    with _lock:
        _breaker_opens += 1


def journal_appended() -> None:
    global _journal_appended
    with _lock:
        _journal_appended += 1


def journal_drained() -> None:
    global _journal_drained
    with _lock:
        _journal_drained += 1


def torn_tail_discarded(count: int) -> None:
    global _torn_tail_discarded
    with _lock:
        _torn_tail_discarded += count


def snapshot() -> CounterSnapshot:
    with _lock:
        return CounterSnapshot(
            retries=dict(_retries),
            exhausted=dict(_exhausted),
            breaker_opens=_breaker_opens,
            journal_appended=_journal_appended,
            journal_drained=_journal_drained,
            torn_tail_discarded=_torn_tail_discarded,
        )


def _reset() -> None:
    """Zero everything. Tests only (`tests/conftest.py::_fresh_storage_counters`)."""
    global _breaker_opens, _journal_appended, _journal_drained, _torn_tail_discarded
    with _lock:
        _retries.clear()
        _exhausted.clear()
        _breaker_opens = 0
        _journal_appended = 0
        _journal_drained = 0
        _torn_tail_discarded = 0
