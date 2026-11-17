"""The journal drainer (PRD-018 STORY-009, Section 6.8 Drain, D11, D17, Risk 7).

What it is for: STORY-008's journal holds the audit rows a user already paid
for while the database could not take them. This module replays them, oldest
first, one entry per transaction, into the database once it answers again, and
marks each drained only AFTER the transaction committed. Every row is keyed by
`write_id` (`database.drain_journal_entry`), so a crash between the commit and
the journal's checkpoint replays as a no-op: the audit trail has no hole and no
duplicate. Only this module calls the journal's drain side; the journal itself
never calls the database (STORY-008) and nothing here runs at import (PRD-014
D2): only the two lifespans (`app/main.py`, `chat_ui/chat_ui/chat_ui.py`) call
`start()` / `stop()`, after `init_db()` succeeded (D17).

`drain_once(journal)` is the whole decision, with no sleeping and a closed
outcome vocabulary (`DrainOutcome`); `_run` is the loop around it. Tests drive
both with a fake `stop` object, so no test sleeps for real.

Rulings recorded with the orchestrator (plan "Design decisions"):
- D-2 Breaker gate. Nothing is drained while the storage breaker is not closed,
  and the drainer never touches a client while the open window is running. But
  `CircuitBreaker.status()` never leaves `open`: only `before()` moves it to
  `half_open` and runs the breaker's own single probe (D6). So when the journal
  is non-empty and the breaker is not closed, the drainer calls `before()`
  itself: an idle instance (no request to be the probe) still recovers. An
  empty journal never reaches the breaker, so a healthy idle process never
  probes. A breaker refuses and never admits (D7): `BreakerOpen` means "not now".
- D-3 Failure policy per entry. `StorageUnavailableError` (an infrastructure
  failure `_unit_of_work` already fed to the breaker) stops the pass and the
  entry stays first. Any other exception holds that entry back for the life of
  the process (one ERROR with the class name only, counted by `held_back()`),
  and the pass moves on: one poison entry must not wedge every later row. A held
  back entry is never deleted and never marked drained, so it stays on disk and
  in the journal's duplicate index, the checkpoint cannot pass it, and the next
  boot adopts and retries it.
- D-4 One journal and one thread per process: `start()` / `stop()` are
  reference counted, so both lifespans running in one process share the first's
  journal and the last `stop()` closes it.
- Stalled shutdown: the driver has no read timeout, so `stop()` joins the thread
  for `_DRAIN_STOP_JOIN_SECONDS`, logs a WARNING if it is still alive, and then
  closes the journal anyway. An entry that committed but was not marked replays
  as a no-op at the next boot.

Parameters are module constants, not settings (PRD-018 O6). Logs carry
`write_id`, `user_id`, ids and counts, never SQL, parameters, journal contents
or driver text.
"""

import enum
import logging
import threading
from typing import Optional

from app.db import audit_journal, database
from app.db.audit_journal import AuditJournal
from app.db.errors import StorageUnavailableError
from app.services.circuit_breaker import BreakerOpen

logger = logging.getLogger(__name__)

# Between two drained entries: one entry per transaction and a short yield so
# live traffic shares the one client (PRD-018 Risk 7).
_DRAIN_YIELD_SECONDS = 0.01
# Journal empty, breaker not ready, storage unavailable, or an entry held back.
_DRAIN_IDLE_SECONDS = 1.0
# How long stop() waits for a drain call in flight (the driver has no read timeout).
_DRAIN_STOP_JOIN_SECONDS = 5.0

_THREAD_NAME = "audit-journal-drainer"


class DrainOutcome(str, enum.Enum):
    """What one `drain_once` call did (closed vocabulary)."""

    EMPTY = "empty"
    BREAKER_OPEN = "breaker_open"
    UNAVAILABLE = "unavailable"
    HELD_BACK = "held_back"
    DRAINED = "drained"


# -- process state (guarded by _lock) ---------------------------------------

_lock = threading.Lock()
_users = 0
_thread: Optional[threading.Thread] = None
_stop_event: Optional[threading.Event] = None
_journal: Optional[AuditJournal] = None
_held_back: set[str] = set()


def _storage_ready() -> bool:
    """True when the storage breaker admits a drain (D-2)."""
    breaker = database._storage_breaker  # read at call time: tests swap it
    if breaker.status().state == "closed":
        return True
    try:
        breaker.before()  # open + window elapsed: the breaker's own SELECT 1 probe
    except BreakerOpen:
        return False
    return breaker.status().state == "closed"


def drain_once(journal: AuditJournal) -> DrainOutcome:
    """Drain at most one entry: the oldest not held back (D-7)."""
    with _lock:
        skip = frozenset(_held_back)
    entry = next((e for e in journal.pending() if e.write_id not in skip), None)
    if entry is None:
        return DrainOutcome.EMPTY
    if not _storage_ready():
        return DrainOutcome.BREAKER_OPEN
    user = entry.audit.user_id if entry.audit is not None else (
        entry.decisions[0].user_id if entry.decisions else "-"
    )
    try:
        audit_id = database.drain_journal_entry(
            entry.audit, entry.decisions, audit_id=entry.audit_id
        )
    except StorageUnavailableError:
        return DrainOutcome.UNAVAILABLE  # already in the breaker; entry stays first
    except Exception as exc:  # noqa: BLE001 - a refused entry, held back (D-3)
        with _lock:
            _held_back.add(entry.write_id)
        logger.error(
            "journal drain held back write_id=%s user_id=%s error=%s",
            entry.write_id, user, type(exc).__name__,
        )
        return DrainOutcome.HELD_BACK
    journal.mark_drained(entry.write_id)
    logger.info(
        "journal drained write_id=%s user_id=%s audit_id=%d decisions=%d",
        entry.write_id, user, audit_id, len(entry.decisions),
    )
    return DrainOutcome.DRAINED


def _tick(journal: AuditJournal) -> DrainOutcome:
    """`drain_once` that never raises, so the daemon thread never dies."""
    try:
        return drain_once(journal)
    except Exception as exc:  # noqa: BLE001
        logger.error("journal drainer tick failed error=%s", type(exc).__name__)
        return DrainOutcome.UNAVAILABLE


def _run(journal: AuditJournal, stop) -> None:
    """The loop: one entry per tick; `stop` needs `is_set()` and `wait(timeout)`."""
    while not stop.is_set():
        outcome = _tick(journal)
        stop.wait(
            _DRAIN_YIELD_SECONDS if outcome is DrainOutcome.DRAINED else _DRAIN_IDLE_SECONDS
        )


# -- lifecycle ----------------------------------------------------------------


def start(directory: str, max_bytes: int, pipeline_max_workers: int) -> None:
    """Open the journal, adopt orphaned ones, start the drainer (D-4).

    Reference counted: only the first call does the work. An unwritable
    directory raises `AuditUnavailableError` naming AUDIT_BUFFER_DIR, and a
    failed start leaves no journal and no thread behind.
    """
    global _users, _thread, _stop_event, _journal
    with _lock:
        if _users > 0:
            _users += 1
            return
        journal = audit_journal.open_journal(directory, max_bytes, pipeline_max_workers)
        try:
            adopted = journal.adopt()
            pending = len(journal.pending())
            stop = threading.Event()
            thread = threading.Thread(
                target=_run, args=(journal, stop), name=_THREAD_NAME, daemon=True
            )
            thread.start()
        except BaseException:
            audit_journal.close_journal()
            raise
        _users = 1
        _journal, _stop_event, _thread = journal, stop, thread
    logger.info("journal drainer started adopted=%d pending=%d", adopted, pending)


def stop() -> None:
    """Release one user; the last one stops the thread and closes the journal."""
    global _users, _thread, _stop_event, _journal
    with _lock:
        if _users == 0:
            return
        _users -= 1
        if _users > 0:
            return
        thread, event = _thread, _stop_event
        _thread = _stop_event = _journal = None
        _held_back.clear()  # a re-start in this process retries them
    if event is not None:
        event.set()
    if thread is not None:
        thread.join(_DRAIN_STOP_JOIN_SECONDS)
        if thread.is_alive():
            logger.warning(
                "journal drainer did not stop within %.0f s; closing the journal anyway",
                _DRAIN_STOP_JOIN_SECONDS,
            )
    audit_journal.close_journal()
    logger.info("journal drainer stopped")


def running() -> bool:
    """True while the drainer thread is alive."""
    thread = _thread
    return thread is not None and thread.is_alive()


def held_back() -> int:
    """Entries held back in this process (STORY-012 decides whether to show it)."""
    with _lock:
        return len(_held_back)


def _stop_all() -> None:
    """Tests only: force the module back to its import state (conftest leak guard)."""
    global _users
    with _lock:
        _users = 1 if _users else 0
    stop()
    audit_journal.close_journal()
    with _lock:
        _held_back.clear()
