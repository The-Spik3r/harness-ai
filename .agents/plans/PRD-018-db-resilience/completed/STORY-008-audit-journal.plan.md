---
story: STORY-008
prd: PRD-018
slug: audit-journal
title: Audit journal — append/fsync JSON Lines, exclusive lock, checksum, torn-tail recovery, adoption, bounds
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-018-db-resilience        # all stories commit here, no per-story branch
created: 2026-11-17
---

# Plan: The on-disk audit journal (PRD-018 F6 storage half, D9, D10)

## Summary

Add `app/db/audit_journal.py`, a filesystem-only module (no database call, no thread, no settings import, no import-time side effect). It holds one class, `AuditJournal`, plus a module-level "current journal" slot that STORY-009's lifespans set with `open_journal(...)` and clear with `close_journal()`. A journal is one JSON Lines file per process, `audit-journal-<host>-<pid>-<boot uuid>.jsonl` under `AUDIT_BUFFER_DIR`, held under an exclusive OS lock (`fcntl.flock` on POSIX; `msvcrt.locking` on one byte at offset 2**40 on Windows, so the lock never blocks reads of the data). Each line carries `v`, `write_id`, `appended_at`, `audit`, `audit_id`, `decisions` and a `sha256` of the canonical JSON without that field. `append` writes, `flush()`es and `os.fsync()`s before it returns, refuses with `AuditUnavailableError` when the line would push the bytes past `AUDIT_BUFFER_MAX_BYTES` (nothing written), and rolls a failed write back by truncation. The class also owns the in-memory pending queue (oldest first), the checkpoint sidecar (`<journal>.checkpoint`, a byte offset), compaction (own file truncated to zero once fully drained; an adopted file deleted once drained), adoption of unlocked sibling journals with torn-tail discard, the per-`(user_id, dedup_key)` index STORY-011's overlay reads, and the depth and headroom queries STORY-011 and STORY-012 read. `app/db/errors.py` gains `AuditUnavailableError(StorageError)`. `app/config.py` gains `AUDIT_BUFFER_DIR` (default `./var/audit-buffer`, non-empty) and `AUDIT_BUFFER_MAX_BYTES` (default 67108864, validated `>= PIPELINE_MAX_WORKERS × 65536 × 2` by a model validator). `.gitignore` gains `var/`. Tests: new `tests/test_audit_journal.py` (non-`db`, `tmp_path`, runs on Windows and Linux) and a new block in `tests/test_config.py`.

## User Story

As a compliance admin
I want an audit row that cannot reach the database to be appended and fsynced to a local journal before anything is released
So that no answered request goes unrecorded because of a storage hiccup

## Story Reference

- Story file: `.agents/stories/PRD-018-db-resilience/STORY-008-audit-journal.md`
- PRD: `.agents/PRDs/PRD-018-db-resilience/PRD.md`: Section 4 audit journal scope (:74-79), 6.8 Format / Durability / Ownership / Bounds / Drain / Overlay (:283-307), 9.2 T5-T8 (:398-401), 9.3 settings and the `_JOURNAL_ENTRY_RESERVE_BYTES` constant (:406-413), 10 Internal API (:448-460), 12 testing approach (:515-519), 15 D9/D10/D13 (:557-558, :561)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (story `type: technical`, `complexity: medium`) |
| Complexity | MEDIUM: ~350 lines of new module, ~40 lines of config, ~450 lines of tests |
| Systems Affected | `app/db/audit_journal.py` (new), `app/db/errors.py`, `app/config.py`, `.gitignore`, `tests/test_audit_journal.py` (new), `tests/test_config.py` |
| Story | STORY-008 |
| PRD | PRD-018 |
| Epic Branch | `epic/PRD-018-db-resilience` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` (UI aesthetics). The story has `skills: []` and touches no UI | — |

---

## Pre-flight findings (verified by the planner on 2026-11-17)

| Fact | Evidence | Consequence |
|---|---|---|
| `AuditLog` is a mutable dataclass; `write_id` sits before `id`, `id` is last | `app/db/models.py:453-522` | The entry's `audit` is every field but `id` (a journaled row has none yet). Decode with `AuditLog(**fields)` |
| `ActionDecisionRow` is frozen; `audit_id` (no default) is the 2nd field, `write_id` before `id` | `app/db/models.py:626-659` | `decisions` are every field but `audit_id` and `id`. Decode with `ActionDecisionRow(audit_id=<entry audit_id>, **fields)`; the drainer `dataclasses.replace`s `audit_id` when the audit row was journaled |
| `models.py` and `errors.py` import only `dataclasses` / `typing` | `app/db/models.py:1-2`, `app/db/errors.py:14` | `audit_journal.py` can import both with no cycle, and `app/config.py` can import the reserve constant from `audit_journal.py` without importing `database.py` (which imports `app.config`, `app/db/database.py:26`) |
| `app/db/__init__.py` is empty | file is 0 bytes | Importing `app.db.audit_journal` from `app.config` runs nothing else |
| Audit `write_id` = `uuid4().hex`; decision `write_id` = `"<batch hex>:<i>"` | `app/services/audit_logger.py:13-23`, `app/services/action_audit.py:200-207` | The journal never mints: a decisions-only entry's `write_id` is the caller's batch hex (STORY-010). `app/db/` must not import `app/services/` |
| Timestamps are `"%Y-%m-%dT%H:%M:%SZ"`, each module declares its own copy | `app/services/audit_logger.py:9`, `app/services/circuit_breaker.py:51` | `appended_at` uses the same format, declared locally |
| Structured logs are `key=value` through a module `logger` | `app/db/database.py:67`, `:1160-1185` | `journal append write_id=%s user_id=%s decisions=%d bytes=%d`, `journal torn_tail file=%s line=%d write_id=%s` |
| **Windows lock, measured on this machine (Python 3.11, `.venv`).** `msvcrt.locking` on offset 0 refuses a second handle **and** makes every other handle's `read()` fail with `PermissionError` (mandatory lock). Locking 1 byte at offset 2**30 or 2**40 (beyond EOF) refuses a second handle in the same process (errno 13) and a child process (errno 13), other handles still read the data, and `ab` writes still append at EOF (file size stays 6, not 2**40) | scratchpad spike `lockspike.py` | Lock 1 byte at `_WINDOWS_LOCK_OFFSET = 1 << 40` after `os.lseek`; data reads by tests and by adoption are unaffected. The in-process "two handles" test works on Windows |
| **POSIX lock, measured in `python:3.11-slim` (Docker).** `fcntl.flock(LOCK_EX \| LOCK_NB)` on a second `open()` of the same path in the **same process** raises `BlockingIOError` (errno 11), and a child process is refused too: flock locks belong to the open file description, so two `open()`s conflict. `os.makedirs(mode=0o700)` and `os.open(..., 0o600)` give `0o700` / `0o600` under umask 022 | scratchpad spike `flockspike.py` | The in-process two-handle test is valid on both platforms; a subprocess test is added anyway for "live process" adoption. **Never** use `fcntl.lockf`/`fcntl.fcntl` record locks: those do not conflict within one process |
| No test enumerates every Settings field against `.env.example`; the `.env.example` tests list their vars explicitly | `tests/test_config.py:61-72`, `:1109-1114`, `:1301-1316` | Registering the two settings needs no census edit. `.env.example` and compose stay STORY-014's (story Technical Notes) |
| The source-census tests scan `app/` for `hash_prompt(`, `log_query`, `CHAT_HISTORY_ENABLED`, session functions | `tests/test_pii_dedup_isolation.py:383-392`, `tests/test_query_pipeline_audit_fields.py:494-540`, `tests/test_chat_sessions.py:1225-1245` | The new module must call none of them (it does not) |
| No existing test sets `PIPELINE_MAX_WORKERS` above 512 through `Settings(...)` (the bound where 64 MiB stops satisfying the new rule); the pipeline tests monkeypatch the attribute, which skips validators | `tests/test_config.py:421-431`, `tests/test_pipeline_executor.py:58`, `tests/test_v1_sse.py:775` | The new model validator breaks no existing construction |
| `.gitignore` has no `var/` | `.gitignore` | Running the app locally would create an untracked `./var/audit-buffer`; add `var/` |
| CI image may run tests as root, where `chmod 000` does not make a directory unwritable | (general POSIX fact) | The "unwritable dir" test points `AUDIT_BUFFER_DIR` under a regular **file** (`tmp_path/"f"/"sub"`), which fails `makedirs` on both platforms for any user |

---

## Design decisions

**D-1. One class, one module slot, explicit parameters (no settings import).** `AuditJournal` takes `directory`, `max_bytes`, `pipeline_max_workers` (and test seams). The module keeps `_current: Optional[AuditJournal] = None`. STORY-009's lifespans call
`audit_journal.open_journal(settings.AUDIT_BUFFER_DIR, settings.AUDIT_BUFFER_MAX_BYTES, settings.PIPELINE_MAX_WORKERS)` then `current().adopt()`, and `close_journal()` on shutdown. `open_journal` raises `RuntimeError` if a journal is already open (a leaked lifespan must be loud); `close_journal()` is a no-op when unset. `current() -> Optional[AuditJournal]` is the read side: `None` means "this process never opened one" (every non-`db` test, scripts, the Docker build). The module-level `append(...)` raises `AuditUnavailableError("audit journal is not open")` when unset, so a call site cannot mistake "no journal" for "journaled" (fail closed, D13). Status readers (STORY-012) treat `None` as an empty journal.

**D-2. The reserve constant lives in `audit_journal.py`; `app/config.py` imports it.** `_JOURNAL_ENTRY_RESERVE_BYTES = 65536` (PRD 9.3, module constant, O6). `config.py` does `from app.db.audit_journal import _JOURNAL_ENTRY_RESERVE_BYTES` for its validator. One source of truth; no cycle (pre-flight rows 3-4). The journal never imports `app.config`, so its tests construct it without `Settings`.

**D-3. Entry model.** `JournalEntry` (frozen dataclass): `write_id: str`, `appended_at: str`, `audit: Optional[AuditLog]`, `audit_id: Optional[int]`, `decisions: tuple[ActionDecisionRow, ...]`. `AuditJournal.append(audit=None, decisions=(), *, audit_id=None, write_id=None) -> JournalEntry` validates the caller's shape with `ValueError` (programming errors, never I/O):
- `audit` given: `audit.write_id` required, `audit.id is None`, `audit_id is None`; the entry `write_id` is `audit.write_id` (a passed `write_id` must equal it). Decisions optional (the "row and decisions in one entry" case, D13).
- `audit` is `None`: `audit_id` is an `int`, `decisions` non-empty, `write_id` given (the caller's batch hex).
- every decision has a `write_id` and `id is None`.
Serialization uses `_AUDIT_EXCLUDED = frozenset({"id"})` and `_DECISION_EXCLUDED = frozenset({"audit_id", "id"})` over `dataclasses.fields(...)`, so a field added later is carried automatically; the round-trip test pins it.

**D-4. Line format and checksum.** `_canonical(obj) = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`. `sha256 = hashlib.sha256(_canonical(body).encode("ascii")).hexdigest()` where `body` is the object without `sha256`; the line is `_canonical({**body, "sha256": sha}) + "\n"`. Verification: `json.loads`, `pop("sha256")`, recompute, compare. ASCII + sorted keys make the re-serialization byte-stable (no floats in either dataclass). `v` is `1`; a different `v` is an undecodable line (D-8).

**D-5. Durability and failure rollback.** One `threading.Lock` (`self._mutex`) serializes every mutation and query (pipeline workers append, STORY-009's drainer drains). `append`: encode; if `self._bytes + len(line) > max_bytes` → `AuditUnavailableError` and nothing is written; else `self._file.write(line)`, `self._file.flush()`, `os.fsync(self._file.fileno())`, then update the in-memory state and return. Any `OSError` (or `ValueError` from a closed file) in write/flush/fsync: best effort `os.ftruncate(fd, previous_size)` + fsync (the file is `O_APPEND`, so the next write still lands at the new EOF), log `ERROR journal append failed write_id=... errno=...` (no contents), and raise `AuditUnavailableError(...) from exc`. If the truncate itself fails, set `self._broken = True`: every later `append` raises `AuditUnavailableError` without writing (a partial line must never be followed by a good one). The entry joins the pending index only after fsync returns.

**D-6. File, directory, lock.** `open`: `os.makedirs(directory, mode=0o700, exist_ok=True)`; if this call created it, `os.chmod(directory, 0o700)` on POSIX (umask-proof). An existing directory is left as the operator made it (a compose named volume). The own file is created with `os.open(path, O_RDWR | O_CREAT | O_EXCL | O_APPEND | getattr(os, "O_BINARY", 0), 0o600)`, wrapped by `os.fdopen(fd, "ab")` (the object whose `write`/`flush` the AC names), and locked with `_try_lock(fd)`. POSIX: `fcntl.flock(fd, LOCK_EX | LOCK_NB)`. Windows: `os.lseek(fd, _WINDOWS_LOCK_OFFSET, SEEK_SET)`, `msvcrt.locking(fd, LK_NBLCK, 1)`, `os.lseek(fd, 0, SEEK_END)`. Either raises `OSError` (`BlockingIOError` / `PermissionError`) when held elsewhere → `_try_lock` returns `False`. Unlock on close: POSIX `flock(LOCK_UN)`, Windows seek + `LK_UNLCK`; then close. `fcntl` / `msvcrt` are imported inside the platform branch at module top (`if os.name == "nt": import msvcrt else: import fcntl`), which is an import, not a side effect. After creating the file, POSIX only: fsync the directory once (`os.open(dir, O_RDONLY)` + `os.fsync`), best effort, so the new name survives a crash. Any `OSError` in `open` (makedirs, create, lock, dir fsync excluded) → `AuditUnavailableError(f"AUDIT_BUFFER_DIR {directory!r} cannot be created or written: {exc.strerror}")` — the startup error the AC requires, raised at open, never at import. File name: `audit-journal-{host}-{pid}-{boot}.jsonl` with `host = re.sub(r"[^A-Za-z0-9._-]", "_", socket.gethostname()) or "host"`, `boot = uuid.uuid4().hex`. The boot uuid matters: in a container the app is often pid 1 on every restart.

**D-7. Checkpoint and compaction.** Sidecar `<journal file>.checkpoint` holds the ASCII byte offset of the first undrained line. Each in-memory pending record remembers `(file, end_offset)`. `mark_drained(write_id)` (raises `KeyError` for an unknown id): removes the entry from pending and from the duplicate index, then advances that file's checkpoint over the contiguous drained prefix and writes the sidecar atomically (`<sidecar>.tmp` + `os.replace`; no fsync needed: a lost checkpoint replays an entry and `write_id` makes the replay a no-op, PRD 6.8 Drain). When a file has no pending entry left: **own file** → flush, `os.ftruncate(fd, 0)`, fsync, `_bytes` for it = 0, sidecar removed (T6 "compacted to zero bytes"); **adopted file** → unlock, close, unlink the journal and its sidecar (best effort, logged on failure). Compaction is automatic inside `mark_drained`, so STORY-009 cannot forget it. Lines before the checkpoint are skipped on load.

**D-8. Load, torn tail, undecodable lines.** `_load(fd_path, checkpoint)` reads bytes from the checkpoint offset, splits on `b"\n"`. A last segment without a trailing newline, or a last line whose JSON or checksum fails, is a **torn tail**: one `ERROR` (`journal torn_tail file=<name> line=<n> write_id=<id or ->`; `write_id` only if the JSON parsed, never contents), counted in `torn_tail_discarded`, discarded. A bad line that is **not** last is corruption, not a torn write: same handling (one `ERROR` with `reason=corrupt`, discarded, counted). A line whose checksum passes but which cannot be decoded (`v != 1`, unknown or missing required dataclass field → `TypeError`) is not discarded: the file is released (unlocked, closed, left on disk untouched) with one `ERROR` naming the file and line, and it is not adopted. That keeps a row a future version wrote for a human, rather than deleting it. File `bytes` counted for an adopted file = its size on disk.

**D-9. Adoption.** `adopt() -> int` (number of files adopted by this call): for every `audit-journal-*.jsonl` in the directory except its own file, in name order: `os.open(path, O_RDWR | O_APPEND | O_BINARY)` (skip if it vanished), `_try_lock`; refused → close, one `INFO journal adopt skipped file=<name> reason=locked`; acquired → read checkpoint, load (D-8), append its entries to the pending queue, log `INFO journal adopted file=<name> entries=<n> discarded=<k>`. An adopted file with zero pending entries is deleted at once (D-7). Adopted entries are queued in file order after anything already pending; STORY-009 calls `adopt()` once at boot, before traffic, so in practice they are the oldest.

**D-10. Depth, headroom, consumer API.** All under `_mutex`:
- `pending() -> list[JournalEntry]`: snapshot, oldest first (STORY-009 iterates it; entries stay pending until `mark_drained`).
- `mark_drained(write_id) -> None` (D-7).
- `pending_audit_rows(user_id, dedup_key) -> list[AuditLog]`: copies (`dataclasses.replace`) of pending audit rows with that user and key, from `self._by_key: dict[tuple[str, str], dict[str, AuditLog]]`; rows whose `dedup_key` is `None` are not indexed (SQL equality never matches NULL). **This is the index STORY-011 needs; its `pending_duplicate(user_id, dedup_key, since)` predicate (success, not blocked, etc., `database.py:885-898`) is STORY-011's, not added here.**
- `entries() -> int`, `bytes() -> int` (own file + every adopted file still held: the disk the process occupies, so a restart after an outage does not double the budget), `oldest_timestamp() -> Optional[str]` (the oldest pending entry's `appended_at`), `adopted_files() -> int` (adopted files still held), `headroom_ok() -> bool` = `bytes() <= max_bytes - pipeline_max_workers * _JOURNAL_ENTRY_RESERVE_BYTES` (PRD 6.8 Bounds; STORY-011 calls it at pipeline entry).
- `status() -> JournalStatus` (frozen dataclass: `entries`, `bytes`, `max_bytes`, `reserve_bytes`, `oldest_timestamp`, `adopted_files`, `torn_tail_discarded`, `path`): one consistent snapshot for STORY-012. The `draining` flag and the appended/drained counters are STORY-009/012's.
- `close()`: unlock and close own and adopted files; leaves files on disk (a non-empty journal survives a shutdown; the next boot adopts it).

**D-11. Logging (T6).** Never contents. `INFO journal opened file=<name>`, `INFO journal append write_id=<id> user_id=<user or -> decisions=<n> bytes=<len>` (an append only happens in degraded mode, so INFO is not noisy), `ERROR` for torn tail / corrupt / undecodable / failed append, `INFO` for adopt and compaction. No `prompt_preview`, no `dedup_key`.

---

## Patterns to Follow

### Error type subclassing StorageError
```python
# SOURCE: app/db/errors.py:118-140
class StorageUnavailableError(StorageError):
    """Storage is unavailable right now: refuse and let the caller retry later.

    PRD-018 D7 / Section 6.5. Raised only by `database._unit_of_work()`: ...
    A `StorageError` on purpose ("subclass, don't widen", PRD 6.10): every
    existing fail-closed arm ... keeps working with no change ...
    """
    def __init__(self, message: str, retry_after_seconds: int) -> None:
```
`AuditUnavailableError(StorageError)` follows: a docstring citing PRD-018 D10/D13/T5, who raises it (`audit_journal` only), and who maps it (STORY-010). No extra attribute; the message is enough.

### Settings validator with a message naming the setting
```python
# SOURCE: app/config.py:533-549
    @field_validator("CONTEXT_MAX_MESSAGES", ..., "PIPELINE_MAX_WORKERS", ...)
    @classmethod
    def _validate_positive_limit(cls, value: int, info) -> int:
        if value < 1:
            description = _POSITIVE_LIMIT_DESCRIPTIONS[info.field_name]
            raise ValueError(f"{info.field_name} must be at least 1, got {value}. It is {description}.")
```
### Cross-field rule as a model validator
```python
# SOURCE: app/config.py:683-709
    @model_validator(mode="after")
    def _validate_v1_tool_models(self) -> "Settings":
        """... Both fields are needed, so this cannot be a field validator, the way
        `_require_token_for_remote_endpoint` is not. ..."""
```
`AUDIT_BUFFER_MAX_BYTES` depends on `PIPELINE_MAX_WORKERS`, so it is a `model_validator(mode="after")` in this shape.

### Commented settings group
```python
# SOURCE: app/config.py:258-260 and :394-419
    # Size of the dedicated pipeline executor thread pool, ... Consumed by STORY-006.
    PIPELINE_MAX_WORKERS: int = 32
```
New group at the end of `Settings` (after `ACTION_SQL_DIALECT`, `:419`), with a header comment citing PRD-018 9.3 and naming STORY-009 (open) and STORY-011 (headroom) as consumers. Appending at the end keeps every `.env.example` order test (`tests/test_config.py:1118-1125`, `:1318-1326`) untouched.

### Module constants and local timestamp format
```python
# SOURCE: app/services/circuit_breaker.py:49-51
logger = logging.getLogger(__name__)
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
```

### Pure test file header
```python
# SOURCE: tests/test_circuit_breaker.py:1-24
"""The reusable circuit breaker, driven with an injected clock (PRD-018 STORY-005).

Pure: no database, no settings, no sleeping. ...
"""
...
_LOG = "app.services.circuit_breaker"
```

### Settings tests
```python
# SOURCE: tests/test_config.py:92-97, :394-418
def _settings(**overrides) -> Settings:
    base = {"OPENROUTER_API_KEY": "test-key", "ADMIN_TOKEN": "test-token"}
    return Settings(_env_file=None, **{**base, **overrides})
...
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, **{field: value})
    assert field in str(exc_info.value)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/errors.py` | UPDATE | `AuditUnavailableError(StorageError)` after `StorageUnavailableError` |
| `app/db/audit_journal.py` | CREATE | The journal (D-1 … D-11) |
| `app/config.py` | UPDATE | `AUDIT_BUFFER_DIR`, `AUDIT_BUFFER_MAX_BYTES`, their validators; import of `_JOURNAL_ENTRY_RESERVE_BYTES` |
| `.gitignore` | UPDATE | `var/` (the default `AUDIT_BUFFER_DIR` is `./var/audit-buffer`) |
| `tests/test_audit_journal.py` | CREATE | Non-`db` journal tests on `tmp_path` |
| `tests/test_config.py` | UPDATE | Append a PRD-018 STORY-008 block (no existing assertion changes) |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: `AuditUnavailableError`

- **File**: `app/db/errors.py`
- **Action**: UPDATE (append after `StorageUnavailableError`, `:118-140`)
- **Implement**: `class AuditUnavailableError(StorageError)` with a docstring: PRD-018 D10/D13, T5. Raised only by `app/db/audit_journal.py`: the journal is not open, the append would exceed `AUDIT_BUFFER_MAX_BYTES`, the write/flush/fsync failed, or (at open) `AUDIT_BUFFER_DIR` cannot be created or written. A `StorageError` so the existing fail-closed arms see it; the 503 mapping on the ingresses is STORY-010's and the headroom refusal STORY-011's. Its message never carries journal contents. No custom `__init__`.
- **Mirror**: `app/db/errors.py:118-140`
- **Validate**: `.venv/Scripts/python -c "from app.db.errors import AuditUnavailableError, StorageError; assert issubclass(AuditUnavailableError, StorageError)"`

### Task 2: `app/db/audit_journal.py`

- **File**: `app/db/audit_journal.py`
- **Action**: CREATE
- **Implement**, top to bottom:
  1. Module docstring: what the journal is for (PRD 6.8 "What it actually absorbs", one paragraph), the file format, durability rule (D13: the caller releases only after `append` returns), the lock design and **why offset 2**40 on Windows** (the measured mandatory-lock read failure), purity (filesystem only, no database, no thread, no settings import, nothing at import, PRD-014 D2), and the consumers (STORY-009 open/adopt/pending/mark_drained, STORY-010 append, STORY-011 `pending_audit_rows` + `headroom_ok`, STORY-012 `status`).
  2. Imports: `dataclasses`, `hashlib`, `json`, `logging`, `os`, `re`, `socket`, `threading`, `uuid`, `datetime`/`timezone`, `pathlib.Path`, typing; `from app.db.errors import AuditUnavailableError`; `from app.db.models import ActionDecisionRow, AuditLog`; `if os.name == "nt": import msvcrt` / `else: import fcntl`.
  3. Constants: `logger`, `_TIMESTAMP_FORMAT`, `_FORMAT_VERSION = 1`, `_JOURNAL_ENTRY_RESERVE_BYTES = 65536` (comment: PRD 9.3, a constant not a setting, O6; `app/config.py` imports it), `_FILE_PREFIX = "audit-journal-"`, `_FILE_SUFFIX = ".jsonl"`, `_CHECKPOINT_SUFFIX = ".checkpoint"`, `_WINDOWS_LOCK_OFFSET = 1 << 40`, `_AUDIT_EXCLUDED`, `_DECISION_EXCLUDED`.
  4. `JournalEntry`, `JournalStatus` frozen dataclasses (D-3, D-10).
  5. Private helpers: `_canonical`, `_encode(entry) -> bytes`, `_decode(line: bytes) -> (JournalEntry | None, write_id | None, reason)` (checksum + decode, D-4/D-8), `_audit_fields(audit) -> dict`, `_decision_fields(row) -> dict`, `_try_lock(fd) -> bool`, `_unlock(fd)`, `_host_tag()`, `_utc_now()` (a module seam so tests can pin `appended_at`).
  6. `class AuditJournal`: `__init__(self, directory, max_bytes, pipeline_max_workers)` does the open (D-6) — or a `@classmethod open(...)`; either way **no I/O happens at import**. Methods: `append`, `pending`, `mark_drained`, `pending_audit_rows`, `entries`, `bytes`, `oldest_timestamp`, `adopted_files`, `headroom_ok`, `status`, `adopt`, `close`, `path` property. Internal per-file record `_JournalFile(path, file_obj, fd, checkpoint, bytes, own: bool, pending_ids: list[str])`.
  7. Module slot: `_current`, `open_journal(directory, max_bytes, pipeline_max_workers) -> AuditJournal`, `current() -> Optional[AuditJournal]`, `close_journal() -> None`, module `append(...)` delegating to `_current` or raising `AuditUnavailableError("audit journal is not open")`.
- **Docstrings** cite PRD-018 sections/decisions (house style). Comments only where the why is not obvious (rollback by truncate, Windows offset, checkpoint without fsync, boot uuid with pid 1).
- **Mirror**: `app/services/circuit_breaker.py` (pure module with a lock, frozen status dataclass, local timestamp format); `app/db/database.py:1160-1185` (log line shape)
- **Validate**: `.venv/Scripts/python -c "import app.db.audit_journal as j; assert j.current() is None; print('OK')"` (and confirm no file/dir was created in the cwd)

### Task 3: Settings

- **File**: `app/config.py`
- **Action**: UPDATE
- **Implement**:
  - Near the top: `from app.db.audit_journal import _JOURNAL_ENTRY_RESERVE_BYTES` with a one-line comment (one constant, owned by the journal, PRD-018 9.3).
  - At the end of the fields (after `ACTION_SQL_DIALECT`, `:419`): a commented group "Audit journal (PRD-018 Section 9.3, D9, D10)". `AUDIT_BUFFER_DIR: str = "./var/audit-buffer"` (comment: created at open by STORY-009's lifespans, never at import; 0700 on POSIX; compose sets a named volume in STORY-014; holds raw prompt previews, T6). `AUDIT_BUFFER_MAX_BYTES: int = 67_108_864` (comment: 64 MiB; an append past it fails closed; minimum is two reserves per pipeline worker).
  - `@field_validator("AUDIT_BUFFER_DIR")`: strip; empty → `ValueError("AUDIT_BUFFER_DIR must name a directory, got an empty value. It is where the audit journal is written when the database cannot take a row (PRD-018 D9). Example: AUDIT_BUFFER_DIR=./var/audit-buffer.")`. Return the stripped value. No filesystem check here (the AC: not at import).
  - `@model_validator(mode="after") _validate_audit_buffer_max_bytes`: `minimum = self.PIPELINE_MAX_WORKERS * _JOURNAL_ENTRY_RESERVE_BYTES * 2`; below it → `ValueError(f"AUDIT_BUFFER_MAX_BYTES must be at least {minimum} (PIPELINE_MAX_WORKERS={...} × 65536 × 2), got {value}. It is the audit journal's capacity in bytes; each pipeline worker needs a reserved entry plus room to spare, or a paid answer could be refused for lack of space (PRD-018 D10). Example: AUDIT_BUFFER_MAX_BYTES=67108864.")`. Docstring says why it is a model validator (needs both fields, the `_validate_v1_tool_models` precedent).
- **Mirror**: `app/config.py:551-573` (strip + non-empty), `:683-709` (model validator)
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 4: `.gitignore`

- **File**: `.gitignore`
- **Action**: UPDATE: add `var/` with a comment `# PRD-018 STORY-008: default AUDIT_BUFFER_DIR (./var/audit-buffer), local journal files`.
- **Validate**: `git check-ignore var/audit-buffer/x.jsonl` prints the path.

### Task 5: `tests/test_audit_journal.py` (non-`db`, Windows and Linux)

- **File**: `tests/test_audit_journal.py`
- **Action**: CREATE
- **Implement**: module docstring (PRD-018 STORY-008; pure, `tmp_path`, no database, no settings; runs on both platforms; POSIX-only assertions skip explicitly on Windows). Helpers: `_audit(**overrides) -> AuditLog` with a `write_id`, `_decision(i, batch) -> ActionDecisionRow`, `_journal(tmp_path, max_bytes=1 << 20, workers=2)` fixture that opens and always closes (finalizer). An autouse fixture that asserts `audit_journal.current() is None` before and calls `close_journal()` after, so no test leaks the slot. Tests:
  1. `test_append_writes_one_checksummed_line_with_the_documented_keys`: keys exactly `{v, write_id, appended_at, audit, audit_id, decisions, sha256}`; `sha256` equals the hash of the canonical line without it; `audit_id` null for an audit entry.
  2. `test_append_flushes_then_fsyncs_before_returning`: monkeypatch `audit_journal.os.fsync` with a recorder that, at call time, reads the file through a **separate handle** and records its size (proves `flush()` preceded `fsync`, since unflushed bytes are invisible to another handle), and records the fd; assert one call, size at fsync = full line length, and the call happened before `append` returned (recorder list non-empty right after). Also spy the file object's `flush` order via the recorder list if the implementation exposes `_file` (keep the separate-handle proof as the primary assertion).
  3. `test_a_failed_fsync_raises_audit_unavailable_and_leaves_no_partial_line`: fsync raises `OSError(errno.EIO)`; `AuditUnavailableError`; the file size is back to the pre-append size; the entry is not pending; a following good append yields a file whose every line verifies.
  4. `test_append_that_would_exceed_max_bytes_writes_nothing`: small `max_bytes`; the refused append raises `AuditUnavailableError`, file bytes unchanged, `entries()` unchanged.
  5. `test_depth_queries_and_headroom`: `entries()`, `bytes()` (= file size), `oldest_timestamp()` (pinned via `_utc_now` seam), `headroom_ok()` true at `max - workers*65536` exactly and false one byte over (set `max_bytes` so the boundary is reachable, e.g. assert the formula against a computed `bytes()`), `status()` fields.
  6. `test_entry_round_trips_every_dataclass_field`: build `AuditLog` / `ActionDecisionRow` with a non-default value for **every** field from `dataclasses.fields` (generated by type: str → unique string, int → unique int, bool → non-default), journal them, reopen by adoption in a second journal instance, and compare: every `AuditLog` field but `id` and every `ActionDecisionRow` field but `audit_id`/`id` equal; also assert the serialized key sets equal `{f.name for f in fields(...)} - _EXCLUDED`, so a new field cannot be dropped silently.
  7. `test_decisions_only_entry_carries_audit_id_and_null_audit` and `test_append_rejects_a_malformed_entry` (parametrized ValueError cases from D-3).
  8. `test_file_name_and_second_opener_cannot_lock`: name matches `audit-journal-<host>-<pid>-<32 hex>.jsonl`; a second `os.open` of the same path + `audit_journal._try_lock(fd)` returns `False` in-process (valid on both platforms, see pre-flight), and data reads through another handle still work.
  9. `test_adopt_skips_a_file_locked_by_a_live_process`: start `subprocess.Popen([sys.executable, "-c", <script>], cwd=<repo root>, stdin=PIPE, stdout=PIPE)` whose script opens a journal in `tmp_path` via `open_journal`, appends one entry, prints its path, then blocks on `sys.stdin.readline()`. Parent opens its own journal, `adopt()` returns 0 and logs `reason=locked`; then parent writes a newline, `wait(timeout=30)`; `adopt()` now returns 1 and `pending()` holds the child's entry. Always kill the child in `finally`. (The child imports only `app.db.audit_journal`, which needs no env vars.)
  10. `test_torn_tail_partial_line_is_discarded_with_one_error` and `test_torn_tail_bad_checksum_is_discarded_with_one_error`: write an orphan file (lines from a closed journal, then append a truncated line / flip one char of the last line's body), `adopt()`: valid earlier entries pending, exactly one `ERROR` record on `app.db.audit_journal` containing the `write_id` (bad-checksum case, JSON parses) or `-` (partial case), and **no** prompt text (`caplog.text` lacks the `prompt_preview` sentinel).
  11. `test_mark_drained_advances_the_checkpoint_and_compacts_to_zero`: three entries; drain one → sidecar offset = end of line 1, `pending()` two; reopen-by-adoption (after `close`) skips the drained line; drain all → own file size 0, sidecar gone, `entries() == 0`, `bytes() == 0`, and an append after compaction verifies.
  12. `test_fully_drained_adopted_file_is_deleted` and `test_adopted_file_with_nothing_pending_is_deleted_at_once`.
  13. `test_pending_audit_rows_indexes_by_user_and_key_and_forgets_on_drain`: rows for two users/keys, a `dedup_key=None` row not indexed, returned rows are copies (mutating one does not change the index), drained rows disappear.
  14. `test_unwritable_directory_is_an_error_naming_the_setting`: `AUDIT_BUFFER_DIR` under a regular file (`tmp_path/"f"` written, then `tmp_path/"f"/"sub"`): `AuditUnavailableError` whose message contains `AUDIT_BUFFER_DIR`.
  15. `@pytest.mark.skipif(os.name == "nt", reason="POSIX modes; Windows has no 0700/0600")` `test_directory_is_0700_and_file_0600_on_posix`.
  16. `test_module_slot_unset_by_default_and_append_fails_closed`: `current() is None`; module `append(...)` raises `AuditUnavailableError`; `open_journal` twice raises `RuntimeError`; `close_journal()` resets to `None`.
  17. `test_import_has_no_side_effect`: a subprocess `python -c "import app.db.audit_journal"` with `cwd=tmp_path` and `PYTHONPATH=<repo>` creates nothing in `tmp_path` and starts no thread (`threading.active_count() == 1` printed from the child).
  18. `test_logs_never_contain_contents`: append with a sentinel in `prompt_preview`, `response_preview`, `dedup_key` and a decision `arguments_preview`; drive append / adopt / drain / torn tail with `caplog` at DEBUG; the sentinel never appears.
  19. Concurrency smoke: 8 threads × 20 appends with a `threading.Barrier`; every line verifies, `entries() == 160`, joins with a timeout.
- **Mirror**: `tests/test_circuit_breaker.py:1-24` (pure header, `_LOG` name), `tests/test_config.py:394-418`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_audit_journal.py -q` on Windows. Linux is proven by CI; optionally `docker run --rm -v <repo>:/r -w /r python:3.11-slim ...` is **not** required (the repo's deps are not in that bare image).

### Task 6: Config tests

- **File**: `tests/test_config.py`
- **Action**: UPDATE (append a `# --- PRD-018 STORY-008: audit journal settings ---` block at the end; no existing assertion changes)
- **Implement**:
  - `test_audit_buffer_settings_have_the_documented_defaults`: `./var/audit-buffer`, `67108864`.
  - `test_audit_buffer_dir_empty_is_a_startup_error` (`""`, `"   "`): message names `AUDIT_BUFFER_DIR`.
  - `test_audit_buffer_max_bytes_below_two_reserves_per_worker_is_a_startup_error`: `PIPELINE_MAX_WORKERS=4`, `AUDIT_BUFFER_MAX_BYTES=4*65536*2-1` (and `"0"` as a string) → message names `AUDIT_BUFFER_MAX_BYTES` and `PIPELINE_MAX_WORKERS`; the exact minimum `4*65536*2` is accepted.
  - `test_default_max_bytes_fits_the_default_worker_count`: default settings construct (32 × 131072 = 4 MiB ≤ 64 MiB).
  - `test_settings_construction_does_not_touch_the_audit_buffer_dir`: `AUDIT_BUFFER_DIR=str(tmp_path / "never")` → the path does not exist afterwards.
  - `test_reserve_constant_is_the_journals`: `app.config._JOURNAL_ENTRY_RESERVE_BYTES is audit_journal._JOURNAL_ENTRY_RESERVE_BYTES == 65536`.
- **Mirror**: `tests/test_config.py:373-431`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_config.py -q`

### Task 7: Targeted regression (one pytest process; never two at once)

- **Run once**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_audit_journal.py tests/test_config.py tests/test_untouched_app.py tests/test_conftest_fixtures.py tests/test_pii_dedup_isolation.py tests/test_chat_sessions.py tests/test_query_pipeline_audit_fields.py tests/test_db_resilience_write_id.py -q` (the source-census suites scan the new module; `test_db_resilience_write_id.py` covers the dataclasses the journal serializes). Record pass/fail/skip counts. No test is renamed or removed, so `_DELIBERATELY_SUPERSEDED_TESTS` is untouched.
- **Also**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`.
- Full suite: GitHub CI on push (user decision).

---

## End-to-End Tests

- [ ] `from app.main import app` imports cleanly; no `./var` directory appears from the import alone.
- [ ] `tests/test_audit_journal.py` passes on Windows locally; CI runs it on Linux (the POSIX-mode test runs there, the subprocess lock test runs on both).
- [ ] No lifespan wiring, no thread: `grep -rn "audit_journal" app chat_ui` shows only `app/config.py` and `app/db/audit_journal.py`.

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_audit_journal.py tests/test_config.py -q
```

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Windows mandatory lock at offset 0 would make every other handle's read fail (measured) | Lock 1 byte at `1 << 40` (measured: refuses second handle and child, data reads fine, appends land at EOF) |
| POSIX `lockf`/`fcntl` record locks do not conflict within a process, so a two-handle test would falsely fail | Use `flock` only (measured in `python:3.11-slim`); plus a subprocess test |
| A failed write leaves a partial line, and the next append concatenates onto it, corrupting a good entry | Truncate back to the pre-append size; if that fails, the journal is `_broken` and refuses every later append (fail closed) |
| `config.py` importing `app.db.audit_journal` could create a cycle | The journal imports only `app.db.errors` / `app.db.models` (both dependency-free); test 17 imports it standalone |
| Raw prompt previews on disk (T6) | 0700/0600 on POSIX, compaction to zero / deletion of drained files, contents never logged (test 18) |
| Root in CI defeats a `chmod`-based unwritable test | Use a path under a regular file instead |
| Subprocess test flakiness | Child blocks on stdin (no sleeps), `wait(timeout=30)`, killed in `finally`; `cwd` = repo root so `app` imports |
| A newer-version entry adopted by older code | Checksum-valid but undecodable → file released untouched with one `ERROR`, never deleted (D-8) |

---

## Deviations / decisions for the orchestrator

1. **`pending_duplicate` is not added here.** The story text and PRD Section 10 name it, but the orchestrator note assigns its predicate to STORY-011. This story ships the index it reads, `pending_audit_rows(user_id, dedup_key)`; STORY-011 adds `pending_duplicate(user_id, dedup_key, since) -> Optional[str]` on top, applying `database.py:885-898`'s predicate.
2. **`bytes()` counts adopted files still held**, not only the own file: `AUDIT_BUFFER_MAX_BYTES` is the process's disk budget, and a restart after an outage must not double it. `adopted_files()` counts adopted files still held (not cumulative). STORY-012 may add a cumulative counter.
3. **`oldest_timestamp()` is the oldest pending entry's `appended_at`**, not `audit.timestamp` (a decisions-only entry has no audit row; the two differ by at most the retry budget, ~2 s).
4. **A corrupt non-last line is discarded like a torn tail** (one `ERROR`, `reason=corrupt`, counted). The AC covers the last line only; discarding is consistent with "a line that fails its checksum was never acknowledged" and keeps the rest of the file drainable. A checksum-valid but undecodable line instead leaves the whole file in place (D-8).
5. **The reserve constant lives in `audit_journal.py` and `app/config.py` imports it** (one source of truth). `app.config` therefore imports `app.db.audit_journal` (and `app.db.models` / `errors`), all side-effect-free.
6. **`AuditUnavailableError` is also the startup error** for an unwritable `AUDIT_BUFFER_DIR` (message names the setting). STORY-009's lifespan lets it propagate, so boot fails loudly (D17).
7. **`.gitignore` gains `var/`.** `.env.example` and compose stay STORY-014's, per the story.

---

## Acceptance Criteria

(Copied from story `STORY-008`)

- [ ] Given `app/db/audit_journal.py`, when `append(entry)` is called, then one JSON line (`v`, `write_id`, `appended_at`, `audit` or `null`, `audit_id`, `decisions`, `sha256` of the line without that field) is written, `flush()`ed and `os.fsync()`ed, and `append` returns only after both. A test with a patched `os.fsync` asserts the order. An I/O failure raises `AuditUnavailableError(StorageError)` (new in `app/db/errors.py`). — Tasks 1-2; tests 1, 2, 3
- [ ] Given `AUDIT_BUFFER_MAX_BYTES`, when an append would exceed it, then it raises `AuditUnavailableError` and writes nothing. `bytes()` / `entries()` / `oldest_timestamp()` report the current depth, and a `headroom_ok()` answers `bytes ≤ MAX_BYTES − PIPELINE_MAX_WORKERS × _JOURNAL_ENTRY_RESERVE_BYTES` (65536) for STORY-011. — tests 4, 5
- [ ] Given a process, when it opens its journal, then the file is `AUDIT_BUFFER_DIR/audit-journal-<host>-<pid>-<boot uuid>.jsonl` under an exclusive OS lock (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows). A second opener cannot lock it (two handles and a subprocess). On POSIX the directory is created `0700` and files `0600`. — tests 8, 9, 15
- [ ] Given a journal whose last line fails its checksum (a torn tail), when it is loaded, then that line is discarded with one `ERROR` log line (`write_id` if parseable, never contents) and the valid lines before it are kept. Given unlocked journals from another pid, when `adopt()` runs, then it locks and loads them, and skips a file locked by a live process. — tests 9, 10, 12, 18
- [ ] Given `app/config.py`, when settings load, then `AUDIT_BUFFER_DIR` (default `./var/audit-buffer`) and `AUDIT_BUFFER_MAX_BYTES` (default 67108864, validated `≥ PIPELINE_MAX_WORKERS × 65536 × 2`, message naming the setting) exist. A directory that cannot be created or written is a startup error naming `AUDIT_BUFFER_DIR`, raised when the journal is opened, not at import. — Task 3; Task 6 tests; test 14
- [ ] Entry round-trip over `dataclasses.fields` (story Technical Notes) — test 6
- [ ] All tasks completed
- [ ] Backend imports without error (`from app.main import app`)
- [ ] Follows existing patterns
