"""The on-disk audit journal (PRD-018 STORY-008, Section 6.8, D9, D10, D13).

What it is for: when the database cannot take an audit row (breaker open, retry
budget spent), the answer a user already paid for must still be recorded. The
caller appends the row here, the append is flushed AND fsynced before it
returns, and only then does the caller release the response (D13). A later
drainer (STORY-009) replays the entries into the database, keyed by `write_id`
so a replay is a no-op. This module is the storage half only: it never calls
the database, starts no thread, imports no settings and does nothing at import
(PRD-014 D2). Only the lifespans call `open_journal` / `adopt`.

Format: one JSON Lines file per process, `audit-journal-<host>-<pid>-<boot
uuid>.jsonl` (the boot uuid because a container is often pid 1 on every
restart). Each line is canonical JSON (sorted keys, ASCII) with `v`, `write_id`,
`appended_at`, `audit` (every `AuditLog` field but `id`, or null), `audit_id`
(set only on a decisions-only entry), `decisions` (every `ActionDecisionRow`
field but `audit_id` and `id`) and `sha256` of the line without that field.
Fields are serialized from `dataclasses.fields`, so a column added later is
carried automatically; tests/test_audit_journal.py pins the round trip.

Lock: the own file is held under an exclusive OS lock for the life of the
process, so a second process cannot adopt a file a live one is writing. POSIX
uses `fcntl.flock` (belongs to the open file description, so even a second
`open()` in the same process conflicts; never `lockf` record locks, which do
not conflict within one process). Windows uses `msvcrt.locking` on ONE byte at
offset 2**40, beyond EOF: a lock at offset 0 is mandatory and makes every other
handle's `read()` fail with PermissionError (measured), while a byte far past
EOF still refuses a second locker and leaves the data readable.

Torn tail vs corruption (orchestrator ruling on STORY-008): only a corrupt LAST
line (or a last line with no newline) is a torn write, was never acknowledged,
and is discarded with one ERROR (reason=torn_tail). A corrupt line that is NOT
last, or a checksum-valid line this code cannot decode, is an acknowledged entry
that was damaged: the whole file is left on disk untouched (not adopted, not
compacted, not deleted) with one ERROR (reason=corrupt / undecodable), for a
human. Logs carry the file name, line number and `write_id` when parseable,
never contents.

Decisions recorded with the orchestrator (plan "Deviations"):
- `pending_audit_rows(user_id, dedup_key)` is the index; `pending_duplicate` /
  `_is_prior_query` (STORY-011) apply `find_duplicate_timestamp`'s predicate to it.
- `bytes()` counts the own file plus every adopted file still held, so a restart
  after an outage does not double the disk budget.
- `oldest_timestamp()` is the oldest pending entry's `appended_at`.
- The journal never mints a `write_id`: an audit entry uses `audit.write_id`, a
  decisions-only entry uses the caller's `write_id`: the audit row's own
  (STORY-010), unique among pending entries because that row committed rather
  than journaled.
- `AuditUnavailableError` is also the startup error for an unwritable directory,
  raised at open, never at import.
- This module imports no settings; `app/config.py` imports
  `_JOURNAL_ENTRY_RESERVE_BYTES` from here, so no import cycle can appear.

Consumers: STORY-009 (open / adopt / pending / mark_drained), STORY-010
(append), STORY-011 (pending_duplicate, check_admission_headroom), STORY-012 (status).
"""

import dataclasses
import hashlib
import json
import logging
import os
import re
import socket
import threading
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.db.errors import AuditHeadroomError, AuditUnavailableError
from app.db.models import ActionDecisionRow, AuditLog

if os.name == "nt":
    import msvcrt
else:
    import fcntl

logger = logging.getLogger(__name__)
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

_FORMAT_VERSION = 1
# Bytes a single in-flight request may still need to journal (PRD-018 9.3). A
# module constant, not a setting (O6); app/config.py imports it for the
# AUDIT_BUFFER_MAX_BYTES minimum, and headroom_ok() reserves it per worker.
_JOURNAL_ENTRY_RESERVE_BYTES = 65536

_FILE_PREFIX = "audit-journal-"
_FILE_SUFFIX = ".jsonl"
_CHECKPOINT_SUFFIX = ".checkpoint"
_WINDOWS_LOCK_OFFSET = 1 << 40

_AUDIT_EXCLUDED = frozenset({"id"})
_DECISION_EXCLUDED = frozenset({"audit_id", "id"})

_O_BINARY = getattr(os, "O_BINARY", 0)


@dataclasses.dataclass(frozen=True)
class JournalEntry:
    """One acknowledged journal line, decoded."""

    write_id: str
    appended_at: str
    audit: Optional[AuditLog]
    audit_id: Optional[int]
    decisions: tuple[ActionDecisionRow, ...]


@dataclasses.dataclass(frozen=True)
class JournalStatus:
    """One consistent snapshot for the status endpoint (STORY-012)."""

    entries: int
    bytes: int
    max_bytes: int
    reserve_bytes: int
    oldest_timestamp: Optional[str]
    adopted_files: int
    torn_tail_discarded: int
    held_back_files: int
    path: str


def _utc_now() -> str:
    """Module seam so tests can pin `appended_at`."""
    return datetime.now(timezone.utc).strftime(_TIMESTAMP_FORMAT)


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _checksum(body: dict) -> str:
    return hashlib.sha256(_canonical(body).encode("ascii")).hexdigest()


def _fields_of(obj: Any, excluded: frozenset) -> dict:
    return {f.name: getattr(obj, f.name) for f in dataclasses.fields(obj) if f.name not in excluded}


def _encode(entry: JournalEntry) -> bytes:
    body = {
        "v": _FORMAT_VERSION,
        "write_id": entry.write_id,
        "appended_at": entry.appended_at,
        "audit": None if entry.audit is None else _fields_of(entry.audit, _AUDIT_EXCLUDED),
        "audit_id": entry.audit_id,
        "decisions": [_fields_of(d, _DECISION_EXCLUDED) for d in entry.decisions],
    }
    return (_canonical({**body, "sha256": _checksum(body)}) + "\n").encode("ascii")


def _decode(line: bytes) -> tuple[Optional[JournalEntry], Optional[str], Optional[str]]:
    """Return (entry, write_id if parseable, failure reason or None).

    Reasons: `checksum` (not JSON, or the hash does not match: a torn or
    damaged line) and `undecodable` (checksum-valid but not readable by this
    code: another format version, an unknown field).
    """
    try:
        obj = json.loads(line.decode("ascii"))
        if not isinstance(obj, dict):
            return None, None, "checksum"
        write_id = obj.get("write_id") if isinstance(obj.get("write_id"), str) else None
        claimed = obj.pop("sha256", None)
        if claimed != _checksum(obj):
            return None, write_id, "checksum"
    except ValueError:
        return None, None, "checksum"
    try:
        if obj["v"] != _FORMAT_VERSION:
            return None, write_id, "undecodable"
        audit_id = obj["audit_id"]
        audit = None if obj["audit"] is None else AuditLog(**obj["audit"])
        decisions = tuple(ActionDecisionRow(audit_id=audit_id, **d) for d in obj["decisions"])
        return JournalEntry(obj["write_id"], obj["appended_at"], audit, audit_id, decisions), write_id, None
    except (KeyError, TypeError, ValueError):
        return None, write_id, "undecodable"


def _try_lock(fd: int) -> bool:
    """Take the exclusive lock on `fd`; False when someone else holds it."""
    try:
        if os.name == "nt":
            os.lseek(fd, _WINDOWS_LOCK_OFFSET, os.SEEK_SET)
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            finally:
                os.lseek(fd, 0, os.SEEK_END)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(fd: int) -> None:
    try:
        if os.name == "nt":
            os.lseek(fd, _WINDOWS_LOCK_OFFSET, os.SEEK_SET)
            try:
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            finally:
                os.lseek(fd, 0, os.SEEK_END)
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass  # closing the descriptor releases it anyway


def _host_tag() -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", socket.gethostname()) or "host"


class _JournalFile:
    """One held journal file: the lock, the checkpoint and its undrained lines."""

    def __init__(self, path: Path, fd: int, file_obj, own: bool, size: int) -> None:
        self.path = path
        self.fd = fd
        self.file = file_obj
        self.own = own
        self.size = size
        self.checkpoint = 0
        # [write_id, end_offset, drained], in file order.
        self.records: list[list] = []

    @property
    def sidecar(self) -> Path:
        return self.path.with_name(self.path.name + _CHECKPOINT_SUFFIX)


class AuditJournal:
    """The process's journal. Thread-safe: one mutex covers every call."""

    def __init__(self, directory: str, max_bytes: int, pipeline_max_workers: int) -> None:
        self._directory = Path(directory)
        self._max_bytes = max_bytes
        self._workers = pipeline_max_workers
        self._mutex = threading.Lock()
        self._pending: "OrderedDict[str, tuple[JournalEntry, _JournalFile]]" = OrderedDict()
        self._by_key: dict[tuple[str, str], dict[str, AuditLog]] = {}
        self._adopted: list[_JournalFile] = []
        self._torn_tail_discarded = 0
        self._held_back = 0
        self._broken = False
        self._closed = False
        self._own = self._open_own()

    # -- open ------------------------------------------------------------

    def _open_own(self) -> _JournalFile:
        directory = self._directory
        try:
            created = not directory.exists()
            os.makedirs(directory, mode=0o700, exist_ok=True)
            if created and os.name != "nt":
                os.chmod(directory, 0o700)  # makedirs' mode is umask-filtered
            name = f"{_FILE_PREFIX}{_host_tag()}-{os.getpid()}-{uuid.uuid4().hex}{_FILE_SUFFIX}"
            path = directory / name
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_APPEND | _O_BINARY, 0o600)
        except OSError as exc:
            raise AuditUnavailableError(
                f"AUDIT_BUFFER_DIR {str(directory)!r} cannot be created or written: {exc.strerror or exc}. "
                "It is where the audit journal is written when the database cannot take a row (PRD-018 D9)."
            ) from exc
        if not _try_lock(fd):
            os.close(fd)
            raise AuditUnavailableError(f"AUDIT_BUFFER_DIR {str(directory)!r}: could not lock the journal file {name}.")
        file_obj = os.fdopen(fd, "ab")
        if os.name != "nt":
            self._fsync_directory()
        logger.info("journal opened file=%s", name)
        return _JournalFile(path, fd, file_obj, own=True, size=0)

    def _fsync_directory(self) -> None:
        try:
            dfd = os.open(self._directory, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass  # best effort: only makes the new file's name crash-durable

    @property
    def path(self) -> Path:
        return self._own.path

    # -- append ----------------------------------------------------------

    def append(
        self,
        audit: Optional[AuditLog] = None,
        decisions: tuple = (),
        *,
        audit_id: Optional[int] = None,
        write_id: Optional[str] = None,
    ) -> JournalEntry:
        """Journal one entry; return only after flush + fsync (D13).

        Raises ValueError for a malformed entry (a programming error) and
        `AuditUnavailableError` when the journal is closed or broken, the line
        would pass AUDIT_BUFFER_MAX_BYTES (nothing written), or the write fails
        (rolled back by truncation).
        """
        decisions = tuple(decisions)
        entry_write_id = self._validate(audit, decisions, audit_id, write_id)
        entry = JournalEntry(entry_write_id, _utc_now(), audit, audit_id, decisions)
        line = _encode(entry)
        user = audit.user_id if audit is not None else (decisions[0].user_id if decisions else "-")
        with self._mutex:
            if self._closed:
                raise AuditUnavailableError("audit journal is closed")
            if self._broken:
                raise AuditUnavailableError("audit journal is unusable after a failed write")
            if entry_write_id in self._pending:
                raise ValueError(f"write_id {entry_write_id!r} is already pending in the journal")
            if self._bytes_locked() + len(line) > self._max_bytes:
                raise AuditUnavailableError(
                    f"audit journal is full: this entry would exceed AUDIT_BUFFER_MAX_BYTES={self._max_bytes}"
                )
            own = self._own
            previous = own.size
            try:
                own.file.write(line)
                own.file.flush()
                os.fsync(own.fd)
            except (OSError, ValueError) as exc:
                logger.error(
                    "journal append failed write_id=%s errno=%s", entry_write_id, getattr(exc, "errno", None)
                )
                try:  # never leave a partial line for the next append to extend
                    os.ftruncate(own.fd, previous)
                    os.fsync(own.fd)
                except (OSError, ValueError):
                    self._broken = True
                raise AuditUnavailableError("audit journal write failed") from exc
            own.size = previous + len(line)
            own.records.append([entry_write_id, own.size, False])
            self._index(entry, own)
            logger.info(
                "journal append write_id=%s user_id=%s decisions=%d bytes=%d",
                entry_write_id, user, len(decisions), len(line),
            )
        return entry

    @staticmethod
    def _validate(audit, decisions, audit_id, write_id) -> str:
        if audit is not None:
            if not audit.write_id:
                raise ValueError("a journaled audit row needs a write_id")
            if audit.id is not None:
                raise ValueError("a journaled audit row has no database id yet")
            if audit_id is not None:
                raise ValueError("audit_id belongs to a decisions-only entry")
            if write_id is not None and write_id != audit.write_id:
                raise ValueError("write_id must equal audit.write_id")
            entry_write_id = audit.write_id
        else:
            if not isinstance(audit_id, int) or isinstance(audit_id, bool):
                raise ValueError("a decisions-only entry needs the audit_id of its audit row")
            if not decisions:
                raise ValueError("an entry needs an audit row or at least one decision")
            if not write_id:
                raise ValueError("a decisions-only entry needs the caller's write_id")
            entry_write_id = write_id
        for d in decisions:
            if not d.write_id:
                raise ValueError("a journaled decision needs a write_id")
            if d.id is not None:
                raise ValueError("a journaled decision has no database id yet")
        return entry_write_id

    def _index(self, entry: JournalEntry, jfile: _JournalFile) -> None:
        self._pending[entry.write_id] = (entry, jfile)
        audit = entry.audit
        if audit is not None and audit.dedup_key is not None:
            self._by_key.setdefault((audit.user_id, audit.dedup_key), {})[entry.write_id] = audit

    def _unindex(self, write_id: str) -> None:
        entry, _ = self._pending.pop(write_id)
        audit = entry.audit
        if audit is not None and audit.dedup_key is not None:
            key = (audit.user_id, audit.dedup_key)
            bucket = self._by_key.get(key, {})
            bucket.pop(write_id, None)
            if not bucket:
                self._by_key.pop(key, None)

    # -- drain side ------------------------------------------------------

    def pending(self) -> list[JournalEntry]:
        """Snapshot of undrained entries, oldest first."""
        with self._mutex:
            return [entry for entry, _ in self._pending.values()]

    def mark_drained(self, write_id: str) -> None:
        """Record that `write_id` reached the database; advance the checkpoint
        and compact a fully drained file. KeyError for an unknown id."""
        with self._mutex:
            if write_id not in self._pending:
                raise KeyError(write_id)
            _, jfile = self._pending[write_id]
            self._unindex(write_id)
            for record in jfile.records:
                if record[0] == write_id:
                    record[2] = True
                    break
            advanced = False
            while jfile.records and jfile.records[0][2]:
                jfile.checkpoint = jfile.records.pop(0)[1]
                advanced = True
            if not jfile.records:
                self._compact(jfile)
            elif advanced:
                self._write_checkpoint(jfile)

    def _write_checkpoint(self, jfile: _JournalFile) -> None:
        # No fsync: a lost checkpoint replays an entry and write_id makes the
        # replay a no-op (PRD 6.8 Drain).
        tmp = jfile.sidecar.with_name(jfile.sidecar.name + ".tmp")
        try:
            tmp.write_text(str(jfile.checkpoint), encoding="ascii")
            os.replace(tmp, jfile.sidecar)
        except OSError as exc:
            logger.warning("journal checkpoint not written file=%s errno=%s", jfile.path.name, exc.errno)

    def _compact(self, jfile: _JournalFile) -> None:
        if jfile.own:
            try:
                jfile.file.flush()
                os.ftruncate(jfile.fd, 0)
                os.fsync(jfile.fd)
                jfile.size = 0
                jfile.checkpoint = 0
            except (OSError, ValueError) as exc:
                logger.error("journal compaction failed file=%s errno=%s", jfile.path.name, getattr(exc, "errno", None))
                self._broken = True
                return
            self._remove_quietly(jfile.sidecar)
            logger.info("journal compacted file=%s", jfile.path.name)
        else:
            self._release(jfile)
            self._remove_quietly(jfile.path)
            self._remove_quietly(jfile.sidecar)
            if jfile in self._adopted:
                self._adopted.remove(jfile)
            logger.info("journal adopted file drained and deleted file=%s", jfile.path.name)

    @staticmethod
    def _remove_quietly(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning("journal file not removed file=%s errno=%s", path.name, exc.errno)

    @staticmethod
    def _release(jfile: _JournalFile) -> None:
        _unlock(jfile.fd)
        try:
            if jfile.file is not None:
                jfile.file.close()
            else:
                os.close(jfile.fd)
        except OSError:
            pass

    # -- queries ---------------------------------------------------------

    def pending_audit_rows(self, user_id: str, dedup_key: str) -> list[AuditLog]:
        """Copies of pending audit rows for (user, key): STORY-011's overlay input."""
        with self._mutex:
            return [dataclasses.replace(a) for a in self._by_key.get((user_id, dedup_key), {}).values()]

    def entries(self) -> int:
        with self._mutex:
            return len(self._pending)

    def _bytes_locked(self) -> int:
        return self._own.size + sum(f.size for f in self._adopted)

    def bytes(self) -> int:
        with self._mutex:
            return self._bytes_locked()

    def oldest_timestamp(self) -> Optional[str]:
        with self._mutex:
            return self._oldest_locked()

    def _oldest_locked(self) -> Optional[str]:
        return min((e.appended_at for e, _ in self._pending.values()), default=None)

    def adopted_files(self) -> int:
        with self._mutex:
            return len(self._adopted)

    def headroom_ok(self) -> bool:
        """bytes <= MAX - PIPELINE_MAX_WORKERS x reserve (PRD 6.8 Bounds)."""
        with self._mutex:
            return self._bytes_locked() <= self._max_bytes - self._workers * _JOURNAL_ENTRY_RESERVE_BYTES

    def status(self) -> JournalStatus:
        with self._mutex:
            return JournalStatus(
                entries=len(self._pending),
                bytes=self._bytes_locked(),
                max_bytes=self._max_bytes,
                reserve_bytes=_JOURNAL_ENTRY_RESERVE_BYTES,
                oldest_timestamp=self._oldest_locked(),
                adopted_files=len(self._adopted),
                torn_tail_discarded=self._torn_tail_discarded,
                held_back_files=self._held_back,
                path=str(self._own.path),
            )

    # -- adoption --------------------------------------------------------

    def adopt(self) -> int:
        """Lock and load every unlocked sibling journal; return how many were adopted."""
        adopted = 0
        with self._mutex:
            for path in sorted(self._directory.glob(f"{_FILE_PREFIX}*{_FILE_SUFFIX}")):
                if path == self._own.path:
                    continue
                if self._adopt_one(path):
                    adopted += 1
        return adopted

    def _adopt_one(self, path: Path) -> bool:
        try:
            fd = os.open(path, os.O_RDWR | os.O_APPEND | _O_BINARY)
        except FileNotFoundError:
            return False
        except OSError as exc:
            logger.error("journal adopt failed file=%s errno=%s", path.name, exc.errno)
            return False
        if not _try_lock(fd):
            os.close(fd)
            logger.info("journal adopt skipped file=%s reason=locked", path.name)
            return False
        jfile = _JournalFile(path, fd, None, own=False, size=0)
        try:
            data = path.read_bytes()
            jfile.size = len(data)
            jfile.checkpoint = self._read_checkpoint(jfile, len(data))
            loaded = self._load(jfile, data)
        except OSError as exc:
            logger.error("journal adopt failed file=%s errno=%s", path.name, exc.errno)
            self._release(jfile)
            return False
        if loaded is None:  # damaged: leave the file untouched, held by nobody
            self._release(jfile)
            self._held_back += 1
            return False
        entries, discarded = loaded
        self._torn_tail_discarded += discarded
        for entry, end in entries:
            if entry.write_id in self._pending:
                jfile.records.append([entry.write_id, end, True])  # replayed copy, already queued
                continue
            jfile.records.append([entry.write_id, end, False])
            self._index(entry, jfile)
        while jfile.records and jfile.records[0][2]:
            jfile.checkpoint = jfile.records.pop(0)[1]
        logger.info("journal adopted file=%s entries=%d discarded=%d", path.name, len(entries), discarded)
        self._adopted.append(jfile)
        if not jfile.records:
            self._compact(jfile)
        return True

    @staticmethod
    def _read_checkpoint(jfile: _JournalFile, size: int) -> int:
        try:
            value = int(jfile.sidecar.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            return 0
        return value if 0 <= value <= size else 0

    @staticmethod
    def _load(jfile: _JournalFile, data: bytes):
        """Return ([(entry, end_offset)], torn_tail_count), or None for a file to leave alone."""
        name = jfile.path.name
        start = jfile.checkpoint
        body = data[start:]
        if not body:
            return [], 0
        segments = body.split(b"\n")
        complete = segments[:-1]
        partial = segments[-1]  # b"" when the data ends with a newline
        entries: list[tuple[JournalEntry, int]] = []
        discarded = 0
        offset = start
        for index, line in enumerate(complete, start=1):
            end = offset + len(line) + 1
            entry, write_id, reason = _decode(line)
            is_last = index == len(complete) and not partial
            if reason == "checksum" and is_last:
                logger.error(
                    "journal torn_tail file=%s line=%d write_id=%s reason=torn_tail", name, index, write_id or "-"
                )
                discarded += 1
            elif reason is not None:
                label = "corrupt" if reason == "checksum" else "undecodable"
                logger.error(
                    "journal file left on disk file=%s line=%d write_id=%s reason=%s",
                    name, index, write_id or "-", label,
                )
                return None
            else:
                entries.append((entry, end))
            offset = end
        if partial:
            logger.error(
                "journal torn_tail file=%s line=%d write_id=- reason=torn_tail", name, len(complete) + 1
            )
            discarded += 1
        return entries, discarded

    # -- close -----------------------------------------------------------

    def close(self) -> None:
        """Release every lock and close every file; files stay on disk for the next boot."""
        with self._mutex:
            if self._closed:
                return
            self._closed = True
            for jfile in [self._own, *self._adopted]:
                self._release(jfile)
            self._adopted = []


# -- module slot ---------------------------------------------------------

_current: Optional[AuditJournal] = None
_slot_lock = threading.Lock()


def open_journal(directory: str, max_bytes: int, pipeline_max_workers: int) -> AuditJournal:
    """Open this process's journal (called by the lifespans, STORY-009)."""
    global _current
    with _slot_lock:
        if _current is not None:
            raise RuntimeError("audit journal is already open; a lifespan leaked it")
        _current = AuditJournal(directory, max_bytes, pipeline_max_workers)
        return _current


def current() -> Optional[AuditJournal]:
    """The open journal, or None when this process never opened one."""
    return _current


def close_journal() -> None:
    global _current
    with _slot_lock:
        journal, _current = _current, None
    if journal is not None:
        journal.close()


def append(*args, **kwargs) -> JournalEntry:
    """Append to the open journal; fail closed when there is none (D13)."""
    journal = _current
    if journal is None:
        raise AuditUnavailableError("audit journal is not open")
    return journal.append(*args, **kwargs)


# PRD-018 D12, Risk 6: the overlay's copy of find_duplicate_timestamp's WHERE
# clause (app/db/database.py, find_duplicate_timestamp). One operand per SQL
# clause, in the same order; change both together. The reasons for each
# exclusion are stated there, not repeated here. tests/test_db_resilience_
# overlay.py pins the parity row shape by row shape against the real SQL.
def _is_prior_query(row: AuditLog, user_id: str, dedup_key: str, since: str) -> bool:
    return (
        row.user_id == user_id
        and row.dedup_key == dedup_key
        and row.timestamp >= since  # same "%Y-%m-%dT%H:%M:%SZ" TEXT order as SQLite's
        and bool(row.success)  # success = 1
        and not row.was_duplicate_blocked  # was_duplicate_blocked = 0
        and row.denied_permission is None  # IS NULL: '' is not NULL
        and (row.pattern_action is None or row.pattern_action != "flag")
        and row.limit_exceeded is None
    )


def pending_duplicate(user_id: str, dedup_key: str, since: str) -> Optional[str]:
    """The earliest pending audit row that counts as a prior query, or None (PRD-018 D12).

    `find_duplicate_timestamp`'s answer over this process's journal: the
    same predicate (`_is_prior_query`) and the same choice (`ORDER BY
    timestamp ASC LIMIT 1` -> the minimum timestamp). None when no journal
    is open (scripts, most tests). In memory only: no I/O, never raises a
    storage error. Other instances' journals are not visible (T4 residual,
    accepted; STORY-014 documents it).
    """
    journal = _current
    if journal is None:
        return None
    return min(
        (
            row.timestamp
            for row in journal.pending_audit_rows(user_id, dedup_key)
            if _is_prior_query(row, user_id, dedup_key, since)
        ),
        default=None,
    )


def check_admission_headroom() -> None:
    """Refuse a new request when the journal is above its admission headroom (PRD-018 D10).

    `bytes > AUDIT_BUFFER_MAX_BYTES - PIPELINE_MAX_WORKERS x 64 KiB` raises
    `AuditHeadroomError`, so every worker already in flight keeps room for
    its rows and a paid answer is never refused for lack of space. A no-op
    when no journal is open (scripts, most tests).
    """
    journal = _current
    if journal is None or journal.headroom_ok():
        return
    status = journal.status()
    logger.warning(
        "journal admission refused bytes=%d max_bytes=%d reserve_bytes=%d",
        status.bytes, status.max_bytes, status.reserve_bytes,
    )
    raise AuditHeadroomError("audit journal is above its admission headroom (AUDIT_BUFFER_MAX_BYTES)")
