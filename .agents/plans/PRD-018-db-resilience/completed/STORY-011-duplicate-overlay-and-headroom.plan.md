---
story: STORY-011
prd: PRD-018
slug: duplicate-overlay-and-headroom
title: Duplicate overlay over journaled rows and the admission headroom check
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-018-db-resilience        # all stories commit here, no per-story branch
created: 2026-11-17
---

# Plan: Duplicate overlay and admission headroom (PRD-018 D10, D12; T4, T5; Risk 6)

## Summary

Two small, independent additions on top of STORY-008/009/010.

1. **Overlay (D12).** `audit_journal.pending_duplicate(user_id, dedup_key, since) -> Optional[str]` applies `find_duplicate_timestamp`'s WHERE clause, clause for clause, to the journal's pending audit rows for `(user_id, dedup_key)` (`AuditJournal.pending_audit_rows`, STORY-008) and returns the **earliest** qualifying `timestamp`, which is what the SQL's `ORDER BY timestamp ASC LIMIT 1` returns. It returns `None` when no journal is open (`current() is None`: scripts and most tests). `check_duplicate` uses the overlay's answer only when the database lookup **succeeded and found nothing**. A failed lookup still raises `DuplicateCheckError`. A found row is answered from the database. The result is `DuplicateCheckResult(is_duplicate=True, first_query_at=<journaled timestamp>)`, so step 4 builds the same `QueryBlockedDuplicateResponse(first_query_at=...)` with no pipeline change. A drained entry leaves the index (`mark_drained` → `_unindex`, STORY-009), so the database lookup holds the next resend instead.
2. **Headroom (D10).** `audit_journal.check_admission_headroom()` raises a new `AuditHeadroomError(AuditUnavailableError)` when an open journal fails `headroom_ok()`, and does nothing otherwise (including when no journal is open). `run_conversation` calls it immediately before step 2, after the pure steps 0/1/1b, so the refusal writes no row and makes no upstream call. `run_query` and every chat path go through `run_conversation`. Because it is an `AuditUnavailableError`, the three existing STORY-010 arms already map it to 503 (`/query`, `/v1` stream and non-stream, tools included, chat UI `internal_error`) with no new `except` arm. Each arm picks the existing "not sent to the model" copy for the subclass, because this refusal happens before the model.

## User Story

As a security admin
I want a resend of a just-answered prompt still held while its row sits in this instance's journal, and a full journal to refuse requests before they pay for an upstream call
So that buffering opens neither a duplicate bypass nor an unrecorded release

## Story Reference

- Story file: `.agents/stories/PRD-018-db-resilience/STORY-011-duplicate-overlay-and-headroom.md`
- PRD: `.agents/PRDs/PRD-018-db-resilience/PRD.md`: 5 story 6 (:118-120), 6.7 headroom row (:276), 6.8 Bounds (:303) and Duplicate overlay (:307), 9.2 T4/T5 (:397-398), 10 internal API (:459), 11 (:480-481), 14 Risk 6 (:540), 15 D10/D12 (:558, :560)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM (story says small; two features, three ingresses, one parity `db` test) |
| Systems Affected | `app/db/errors.py`, `app/db/audit_journal.py`, `app/db/database.py` (comment only), `app/services/duplicate_checker.py`, `app/services/query_pipeline.py`, `app/routers/query.py`, `app/routers/v1.py`, `chat_ui/chat_ui/state.py`, tests |
| Story | STORY-011 |
| PRD | PRD-018 |
| Epic Branch | `epic/PRD-018-db-resilience` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design`, which covers the visual design of new UI. This story adds no component, copy or styling. The chat UI change picks an existing notice (`STORAGE_UNAVAILABLE_NOT_SENT_NOTICE`, `chat_ui/chat_ui/copy.py:37-39`) inside an existing `except` arm, uses no Reflex API, and is validated by the startup-guard probe from SUBAGENT_BRIEF. | — |

---

## Orchestrator rulings requested (proposals; the plan implements them unless overruled)

- **R1: Snapshot the overlay before the DB lookup, use it only after.** The orchestrator note and PRD 6.8 say "consults it after the database lookup succeeds and only if that found nothing". Read literally (lookup first, then read the journal), this leaves a same-instance race. (1) `find_duplicate_timestamp` reads before the drainer commits the row. (2) The drainer commits and `mark_drained` removes it from the index (`app/db/journal_drainer.py:116-129`, `app/db/audit_journal.py:400-407`). (3) The overlay then reads an index without the row. Neither side sees the row, so the resend is admitted. The lookup is a network round trip and the drainer runs during exactly this recovery period, so the race is real (T4 on the *same* instance, which D12 claims to close). Proposal: `check_duplicate` calls `audit_journal.pending_duplicate(...)` once **before** the lookup, keeps the answer in a local, and **uses** it only when the lookup succeeded and returned `None`. If the row is drained before the lookup, the database sees it. If it is drained after the lookup, the snapshot holds it. Every stated property survives. A failed lookup raises `DuplicateCheckError` and the snapshot is discarded, so the overlay never stands in for the database. A found row returns the database's timestamp and ignores the snapshot. The cost is one in-memory dict read under the journal mutex per request, and zero when no journal is open. The AC 2 tests assert *outcomes* (the DB answer wins, the failure still raises even with a matching journal row), not call order. **Fallback if overruled:** move the call after the lookup. The tests stay the same, except that `test_overlay_is_not_read_when_the_lookup_fails_or_finds_a_row` also asserts the spy was not called.
- **R2: A dedicated `AuditHeadroomError(AuditUnavailableError)`**, in `app/db/errors.py` and raised only by `audit_journal.check_admission_headroom()`. Every arm that catches `AuditUnavailableError` (`app/routers/query.py:68`, `app/routers/v1.py:121-130 / 232 / 260`, `chat_ui/chat_ui/state.py:1253`) catches it with no new arm, and `_fault_code` already returns `STORAGE_UNAVAILABLE` for it. The subclass exists only so each arm can say "not sent". The STORY-010 copy (`STORAGE_UNAVAILABLE_DETAIL` "Storage unavailable", `AUDIT_UNAVAILABLE_MESSAGE` "...could not be recorded, so it was not released", `AUDIT_UNAVAILABLE_NOTICE` "...could not be recorded, so nothing is shown") describes a *post-model* refusal, which is untrue here. The headroom arms reuse the existing pre-model copy: `/query` `STORAGE_UNAVAILABLE_NOT_SENT_DETAIL`, `/v1` `STORAGE_UNAVAILABLE_MESSAGE`, chat `STORAGE_UNAVAILABLE_NOT_SENT_NOTICE` (generic `internal_error` headline, as for every pre-model storage fault). No new copy string is added.
- **R3: `Retry-After` for the headroom 503 is `1`.** `audit_unavailable_retry_after(exc)` (`app/services/storage_faults.py:45-61`) walks `__context__`. The check runs outside any `except` block, so the chain is empty and the answer is `1`. The journal module may not import `database` (purity, and `tests/test_audit_journal.py:490-497` pins that it never imports settings), so it cannot read the breaker. We accept this: the client retries cheaply, and each retry is refused at entry, again before any work.
- **R4: Placement of the check is "step 1c", immediately before `# Step 2`** (`app/services/query_pipeline.py:379-381`), not before step 0. Step 0 (`InvalidConversationError`) is a programming error that writes no row anyway, and steps 1/1b are pure (`dedup_key`, `conversation_key`, `_has_tool_turns`). Either position satisfies "before step 2, no row, zero upstream". This one keeps step 0 first, as its comment requires ("before anything else can run", `:351-353`).
- **R5: "Both live next to each other" (Risk 6) becomes "both cross-reference each other, and a test pins them together".** The overlay predicate cannot live in `database.py`: `audit_journal` must not import it (no settings, no DB; `tests/test_audit_journal.py:490-497`), and the PRD's internal API names `audit_journal.pending_duplicate` (`PRD.md:459`). So the predicate `_is_prior_query` lives in `audit_journal.py`. Both sides carry a cross-reference comment, and the parity test enumerates both sides mechanically (Task 7).

---

## Patterns to Follow

### The SQL predicate the overlay mirrors (and its shape pin)
```python
# SOURCE: app/db/database.py:1500-1544 (WHERE at :1526-1534)
        row = conn.execute(
            """
            SELECT timestamp FROM audit_logs
            WHERE user_id = ? AND dedup_key = ? AND timestamp >= ?
              AND success = 1
              AND was_duplicate_blocked = 0
              AND denied_permission IS NULL
              AND (pattern_action IS NULL OR pattern_action <> 'flag')
              AND limit_exceeded IS NULL
            ORDER BY timestamp ASC
            LIMIT 1
            """,
            (user_id, dedup_key, since),
        ).fetchone()
```
**Constraint:** `tests/test_db.py:2563-2577` (`test_find_duplicate_timestamp_sql_is_the_planned_shape`) takes `re.findall(r'"""(.*?)"""', inspect.getsource(find_duplicate_timestamp))` and asserts there is exactly one match equal to `_DEDUP_LOOKUP_SQL` (`tests/test_db.py:~2515-2528`). The cross-reference must therefore be a `#` comment inside `_op`, above the existing comment block. **Do not add a `"""` docstring to `find_duplicate_timestamp`**, and do not touch the SQL text.

### The cutoff and the timestamp format (string comparison is valid)
```python
# SOURCE: app/services/duplicate_checker.py:10, 29-39
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
def check_duplicate(user_id: str, key: str) -> DuplicateCheckResult:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime(_TIMESTAMP_FORMAT)
    try:
        match = find_duplicate_timestamp(user_id, key, cutoff)
    except StorageError as exc:
        raise DuplicateCheckError(f"Duplicate lookup failed: {exc}") from exc
```
`log_query` stamps rows with the same format (`app/services/audit_logger.py:15, 115`). The journal stores `AuditLog.timestamp` verbatim, and the drainer inserts that original timestamp (`tests/test_db_resilience_drain.py:290-296`). `audit_logs.timestamp` is `TEXT` (`app/db/models.py:7`), compared with SQLite's default BINARY collation (memcmp). Python's `str >=` on fixed-width ASCII ISO-8601 gives the same order, so `row.timestamp >= since` matches `timestamp >= ?`. The parity test pins the boundary (`timestamp == since` is included on both sides).

### Journal index and module slot (STORY-008)
```python
# SOURCE: app/db/audit_journal.py:475-478, 502-505, 653-655
    def pending_audit_rows(self, user_id: str, dedup_key: str) -> list[AuditLog]:
        """Copies of pending audit rows for (user, key): STORY-011's overlay input."""
        with self._mutex:
            return [dataclasses.replace(a) for a in self._by_key.get((user_id, dedup_key), {}).values()]
    def headroom_ok(self) -> bool:
        """bytes <= MAX - PIPELINE_MAX_WORKERS x reserve (PRD 6.8 Bounds)."""
        with self._mutex:
            return self._bytes_locked() <= self._max_bytes - self._workers * _JOURNAL_ENTRY_RESERVE_BYTES
def current() -> Optional[AuditJournal]:
    """The open journal, or None when this process never opened one."""
    return _current
```
`headroom_ok()` is `bytes <= MAX − W×64 KiB`, so it refuses exactly when `bytes > MAX − W×64 KiB` (AC 4). `W` is the `pipeline_max_workers` passed to `open_journal` (`:643-650`; the lifespans pass `settings.PIPELINE_MAX_WORKERS`).

### Error class docstring style
```python
# SOURCE: app/db/errors.py:143-152
class AuditUnavailableError(StorageError):
    """The audit journal cannot take an entry (PRD-018 D10 / D13, T5).
    Raised only by `app/db/audit_journal.py`: ... the 503 mapping on the ingresses is STORY-010's and the
    headroom refusal STORY-011's. The message never carries journal contents.
    """
```

### Ingress arms this story extends (no new arms)
```python
# SOURCE: app/routers/query.py:64-79
    except AuditUnavailableError as exc:
        retry_after = audit_unavailable_retry_after(exc)
        logger.warning("query request refused: user_id=%s code=audit_unavailable retry_after=%s", ...)
        raise HTTPException(status_code=503, detail=STORAGE_UNAVAILABLE_DETAIL, headers={"Retry-After": str(retry_after)}) from exc
```
```python
# SOURCE: app/routers/v1.py:258-267 (inside _outcome)
        if isinstance(exc, AuditUnavailableError):
            # PRD-018 D10, T5: fixed copy that does not say "not sent" -- step 8
            # runs after the upstream call. Retry-After per R5.
            return translate_fault(code, AUDIT_UNAVAILABLE_MESSAGE, retry_after_seconds=audit_unavailable_retry_after(exc))
```
```python
# SOURCE: chat_ui/chat_ui/state.py:1247-1265
            except AuditUnavailableError:
                logger.warning("chat send refused: user_id=%s code=audit_unavailable", identity.user_id)
                await self._append_and_persist(ChatMessage(kind="internal_error", content="internal_error", prompt=text, detail=AUDIT_UNAVAILABLE_NOTICE), identity, session_id)
                return
```
`/v1` streaming: the commit rule (`app/routers/v1.py:~387-391`, `if not (call.stream and upstream.called): return _json_response(...)`) sends a pre-upstream fault with its real status. The headroom refusal never calls the upstream, so a streamed request also gets a plain 503 JSON body, not an SSE event. Tools: the R2 wrapper of STORY-010 (`app/services/query_pipeline.py:945-955`) wraps only step 8, so a headroom error on a `tools=` request propagates unchanged and maps to 503, not 500. That is correct, because nothing was sent.

### Tests
```python
# SOURCE: tests/test_db_resilience_release.py:91-96, 112-118, 120-148 (journal fixture, pipeline stubs, counting upstream)
@pytest.fixture
def journal(tmp_path):
    """The module slot, open under `tmp_path` and always closed (the conftest fails a leak)."""
    opened = audit_journal.open_journal(str(tmp_path / "buf"), 1 << 20, 2)
    yield opened
    audit_journal.close_journal()
```
```python
# SOURCE: tests/test_chat_ui_storage_failures.py:42-82 (_make_state, _send, _stub_pipeline_raising)
```
```python
# SOURCE: tests/test_db_resilience_drain.py:46-49 (_audit helper), :290 (db test over temp_db)
```
`db` marking is automatic from the `temp_db` fixture (`tests/conftest.py:180-206`). The autouse `_isolated_audit_buffer` (`tests/conftest.py:720+`) fails a test that leaks an open journal.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/errors.py` | UPDATE | Add `AuditHeadroomError(AuditUnavailableError)`; one line in `AuditUnavailableError`'s docstring pointing at it |
| `app/db/audit_journal.py` | UPDATE | `_is_prior_query` (the overlay predicate, cross-referenced), module `pending_duplicate(...)`, module `check_admission_headroom()`; module docstring "Consumers"/decisions line |
| `app/db/database.py` | UPDATE (comment only) | Cross-reference comment in `find_duplicate_timestamp._op` (no docstring, SQL untouched) |
| `app/services/duplicate_checker.py` | UPDATE | Overlay in `check_duplicate` (R1) |
| `app/services/query_pipeline.py` | UPDATE | Headroom check before step 2 |
| `app/routers/query.py` | UPDATE | Headroom → `STORAGE_UNAVAILABLE_NOT_SENT_DETAIL` inside the existing arm |
| `app/routers/v1.py` | UPDATE | Headroom → `STORAGE_UNAVAILABLE_MESSAGE` inside `_outcome`'s existing branch |
| `chat_ui/chat_ui/state.py` | UPDATE | Headroom → `STORAGE_UNAVAILABLE_NOT_SENT_NOTICE` inside the existing arm |
| `tests/test_db_resilience_overlay.py` | CREATE | Overlay unit tests (non-`db`), parity `db` test, drain-leaves-index `db` test |
| `tests/test_db_resilience_headroom.py` | CREATE | Headroom tests (non-`db`, journal on `tmp_path`): pipeline, `/query`, `/v1` json/stream/tools, chat UI |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: `AuditHeadroomError`

- **File**: `app/db/errors.py`
- **Action**: UPDATE
- **Implement**: After `AuditUnavailableError` (`:143-152`) add:
  ```python
  class AuditHeadroomError(AuditUnavailableError):
      """The journal is above its admission headroom: refuse at pipeline entry (PRD-018 D10, 6.8 Bounds).

      Raised only by `audit_journal.check_admission_headroom()`, which
      `query_pipeline.run_conversation` calls before step 2, so nothing has run:
      no row, no upstream call. An `AuditUnavailableError` so every ingress arm
      that refuses an unrecordable request (503) catches it unchanged; the
      subclass exists only so those arms can say "not sent to the model",
      which is true here and not for a step 8 refusal (STORY-011 R2).
      """
  ```
  In `AuditUnavailableError`'s docstring, replace "the headroom refusal STORY-011's" with "the headroom refusal is the `AuditHeadroomError` subclass (STORY-011)". Keep the "Raised only by `app/db/audit_journal.py`" claim, which stays true.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: Overlay predicate, `pending_duplicate`, `check_admission_headroom` in `audit_journal`

- **File**: `app/db/audit_journal.py`
- **Action**: UPDATE
- **Implement**:
  - Import `AuditHeadroomError` beside `AuditUnavailableError` (`:72`).
  - Module-level (after the `AuditJournal` class, in the "module slot" section near `:637-671`), a pure predicate whose body is **one `return` of a single `and` chain with exactly eight operands, in the SQL's clause order** (Task 7 pins the operand count by AST):
    ```python
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
    ```
    `row.dedup_key == dedup_key` is never true for a `None` key. The index only holds non-`None` keys (`:380-381`), and `None = ?` is never true in SQL.
  - Module function:
    ```python
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
            (row.timestamp for row in journal.pending_audit_rows(user_id, dedup_key)
             if _is_prior_query(row, user_id, dedup_key, since)),
            default=None,
        )
    ```
  - Module function:
    ```python
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
    ```
    The log carries sizes only, never contents, which keeps `tests/test_audit_journal.py`'s `test_logs_never_contain_contents` valid. The two reads (`headroom_ok`, `status`) are not atomic, which only affects the logged figures.
  - Module docstring: update the "Decisions recorded" bullet (`:40-41`) to "`pending_audit_rows(user_id, dedup_key)` is the index; `pending_duplicate` / `_is_prior_query` (STORY-011) apply `find_duplicate_timestamp`'s predicate to it", and the "Consumers" line (`:54-55`) to `STORY-011 (pending_duplicate, check_admission_headroom)`. Add no import of `database` or `app.config`.
- **Mirror**: module functions `append` / `current` (`:653-671`); log style `logger.info("journal ... key=%s", ...)`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_audit_journal.py -q` (its import-purity test included).

### Task 3: Cross-reference in `find_duplicate_timestamp`

- **File**: `app/db/database.py`
- **Action**: UPDATE (comment only)
- **Implement**: Add at the top of the existing `#` comment block in `_op` (`:1502`), before "Only a row with a real verdict...":
  ```python
        # PRD-018 D12, Risk 6: audit_journal._is_prior_query is this WHERE
        # clause over the journal's pending rows (the duplicate overlay). Any
        # exclusion added here must be added there, in the same order; the
        # parity test in tests/test_db_resilience_overlay.py fails otherwise.
  ```
  No docstring (see the `test_db.py:2563-2577` constraint above). Leave the SQL text untouched.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db.py -k "find_duplicate_timestamp or dedup_lookup_shape" -q`

### Task 4: Overlay in `check_duplicate`

- **File**: `app/services/duplicate_checker.py`
- **Action**: UPDATE
- **Implement**: `from app.db import audit_journal` (module import, so tests can patch `audit_journal.pending_duplicate`). In `check_duplicate` (R1):
  ```python
    cutoff = ...
    # PRD-018 D12 (STORY-011 R1): the journal overlay is read BEFORE the lookup
    # and used only AFTER it succeeded and found nothing. Read after, a row the
    # drainer commits after the lookup's read and removes from the index before
    # ours would be invisible to both. The overlay never stands in for the
    # database: a failed lookup still fails closed below and discards it, and
    # a row the lookup found is the answer.
    journaled = audit_journal.pending_duplicate(user_id, key, cutoff)
    try:
        match = find_duplicate_timestamp(user_id, key, cutoff)
    except StorageError as exc:
        raise DuplicateCheckError(f"Duplicate lookup failed: {exc}") from exc

    if match is None:
        match = journaled
    if match is None:
        return DuplicateCheckResult(is_duplicate=False)
    return DuplicateCheckResult(is_duplicate=True, first_query_at=match)
  ```
  Keep the signature and the `find_duplicate_timestamp` by-name import (tests patch `duplicate_checker.find_duplicate_timestamp`, e.g. `tests/test_dedup_key.py:282`). Do **not** write the words "pii", "redact" or "presidio" in this module (`tests/test_pii_dedup_isolation.py:231-236`), add no `hash_prompt(` site (census `tests/test_pii_dedup_isolation.py:~400-410`), and do not import `app.models.messages` (`tests/test_messages.py:612-617`).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_duplicate_checker.py tests/test_pii_dedup_isolation.py tests/test_messages.py -q -m "not db"` (no journal open → overlay is `None` → unchanged behaviour).

### Task 5: Headroom check before step 2

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**: `from app.db import audit_journal`. Immediately before `# Step 2: authorize / model / BYOK.` (`:381`), after `request_has_tool_turns = ...` (`:379`):
  ```python
    # Step 1c: admission headroom (PRD-018 D10, Section 6.8 Bounds; T5).
    # Before step 2, so a refused request writes no row (there may be no room
    # for one) and pays for no upstream call; steps 0-1b above are pure. Every
    # worker already in flight keeps W x 64 KiB to journal its rows, so a paid
    # answer is never withheld for lack of space. AuditHeadroomError is an
    # AuditUnavailableError: /query and /v1 answer 503, the chat UI an
    # internal_error bubble, through their existing arms (STORY-011 R2). A
    # no-op when no journal is open.
    audit_journal.check_admission_headroom()
  ```
  Call through the module (`audit_journal.check_admission_headroom`) so a test can patch it.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 6: Ingress copy for the subclass (no new arms)

- **File**: `app/routers/query.py`
  - Import `AuditHeadroomError` beside `AuditUnavailableError` (`:10`). In the arm at `:68-79`: `headroom = isinstance(exc, AuditHeadroomError)`, `code=audit_headroom` vs `audit_unavailable` in the existing warning, and `detail=STORAGE_UNAVAILABLE_NOT_SENT_DETAIL if headroom else STORAGE_UNAVAILABLE_DETAIL`. Extend the comment: "PRD-018 D10 (STORY-011): the headroom refusal is the subclass, raised before step 2, so 'not sent' is true for it."
- **File**: `app/routers/v1.py`
  - Import `AuditHeadroomError`. In `_outcome` (`:260-267`), choose `STORAGE_UNAVAILABLE_MESSAGE if isinstance(exc, AuditHeadroomError) else AUDIT_UNAVAILABLE_MESSAGE`, with a comment. `_fault_code` (`:232`) needs no change. Add one comment line to `_PIPELINE_FAULTS` (`:127-129`): "`AuditHeadroomError` (STORY-011) is a subclass, raised before step 2, so tools requests get it as 503 too."
- **File**: `chat_ui/chat_ui/state.py`
  - Import `AuditHeadroomError` (`:9`). Make it `except AuditUnavailableError as exc:` at `:1253`, `detail=STORAGE_UNAVAILABLE_NOT_SENT_NOTICE if isinstance(exc, AuditHeadroomError) else AUDIT_UNAVAILABLE_NOTICE`, and `code=audit_headroom` vs `audit_unavailable` in the warning. Do not log exception text. Comment: "PRD-018 D10 (STORY-011): the headroom refusal happens before the model, so its bubble says nothing was sent".
- **Validate**: app import + `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_chat_ui_startup_guard.py tests/test_chat_ui_storage_failures.py tests/test_db_resilience_release.py tests/test_db_resilience_ingress.py -q -m "not db"`

### Task 7: `tests/test_db_resilience_overlay.py`

- **File**: `tests/test_db_resilience_overlay.py`
- **Action**: CREATE
- **Implement**: module docstring citing PRD-018 D12, Risk 6, T4 and STORY-011 R1. Helper `_audit(**overrides)` as in `tests/test_db_resilience_drain.py:46-49`, with a fresh `uuid.uuid4().hex` `write_id`, `user_id="u1"`, `dedup_key="k"`, `timestamp="2026-11-16T14:02:13Z"`, `success=True`. `_SINCE = "2026-11-16T00:00:00Z"`. Journal fixture = the module slot under `tmp_path` (`open_journal(..., 8 << 20, 2)`, `close_journal()` in `finally`).
  Non-`db` tests (overlay semantics; `find_duplicate_timestamp` patched on `duplicate_checker`):
  1. `test_pending_duplicate_is_none_without_an_open_journal`.
  2. `test_pending_duplicate_returns_the_earliest_qualifying_timestamp`: two rows, plus an earlier excluded one (`success=False`). The earliest *qualifying* timestamp comes back.
  3. `test_check_duplicate_holds_a_journaled_row_when_the_lookup_found_nothing` (AC 1): lookup → `None`, journal row → `DuplicateCheckResult(True, "2026-11-16T14:02:13Z")`. Also through `query_pipeline.run_conversation` with `USAGE_LIMITS_ENABLED=False` and a counting upstream: a `QueryBlockedDuplicateResponse` with `first_query_at` equal to the journaled timestamp, zero upstream calls. Stub `query_pipeline.log_query` to record calls (the duplicate arm writes a `was_duplicate_blocked` row) so no driver is touched.
  4. `test_a_failed_lookup_still_fails_closed_with_a_matching_journal_row` (AC 2): lookup raises `StorageUnavailableError` → `DuplicateCheckError` whose `__cause__` is it.
  5. `test_the_database_answer_wins_when_the_lookup_found_a_row` (AC 2): lookup returns `"2026-11-16T10:00:00Z"`, journal holds `14:02:13` → `first_query_at == "2026-11-16T10:00:00Z"`.
  6. `test_a_row_drained_between_the_overlay_read_and_the_lookup_is_still_held` (R1): a fake lookup that, when called, does `journal.mark_drained(write_id)` and returns `None` (it simulates the drainer racing *after* the lookup's read). The result is still a duplicate. Delete this test if R1 is overruled.
  7. `test_mark_drained_removes_the_row_from_the_overlay`: append, `pending_duplicate` → ts, `mark_drained` → `None`.
  8. `test_both_predicates_carry_a_cross_reference`: `"_is_prior_query" in inspect.getsource(database.find_duplicate_timestamp)` and `"find_duplicate_timestamp" in inspect.getsource(audit_journal._is_prior_query)` (the comment sits directly above the `def`, so read the module source and check the lines before the `def`, or use `inspect.getcomments`).
  `db` tests (`temp_db`):
  9. `test_overlay_and_sql_agree_on_every_excluded_row_shape` (AC 3, Risk 6). Mechanical enumeration:
     - Parse the SQL: take the single `"""..."""` from `inspect.getsource(database.find_duplicate_timestamp)` (the `test_db.py:2566-2569` technique), the text between `WHERE` and `ORDER BY`, normalised by whitespace and split on `" AND "`. Assert the clause list **equals** the keys of a `_SHAPES` dict: clause → `(row overrides, query overrides)` for the shape that violates it. `user_id = ?` → row `user_id="u2"`. `dedup_key = ?` → row `dedup_key="k2"`. `timestamp >= ?` → row `timestamp="2026-11-15T23:59:59Z"`. `success = 1` → `success=False`. `was_duplicate_blocked = 0` → `True`. `denied_permission IS NULL` → `"query:submit"` (plus an extra `""` variant). `(pattern_action IS NULL OR pattern_action <> 'flag')` → `"flag"`. `limit_exceeded IS NULL` → `"daily_tokens"`. A clause added to the SQL then fails with "no shape for clause X".
     - Pin the overlay side: `ast.parse` the source of `audit_journal._is_prior_query`, find the `Return` whose value is a `BoolOp(And)`, and assert `len(values) == len(sql_clauses)`. An operand added to only one side fails one of the two pins.
     - Add positive controls: the baseline row (matches), `timestamp == since` (boundary, matches), `pattern_action="block"` and `pattern_action=None` (match), `denied_permission=""` (excluded on both, since `'' IS NULL` is false).
     - **Field sweep** (catches an overlay-only exclusion on a column no shape varies): for every `dataclasses.fields(AuditLog)` except `id`, `write_id`, `timestamp`, `user_id`, `dedup_key`, build variants by annotation: `bool` → `True`, `False`; `Optional[str]` / `str` → `None` (if Optional), `""`, `"flag"`, `"block"`, `"x"`; `Optional[int]` → `None`, `0`, `1`. Fail the test on an annotation the sweep has no rule for, so a new column type cannot slip past.
     - For every case, give the row a unique `dedup_key` (`f"k-{n}"`; for the "another key" shape, the row gets `f"k-{n}-other"` and the query `f"k-{n}"`). Write it with `insert_audit_log(row)` **and** `audit_journal.append(dataclasses.replace(row, write_id=<new hex>))`, then assert `database.find_duplicate_timestamp(u, key, _SINCE) == audit_journal.pending_duplicate(u, key, _SINCE)`. Collect mismatches and assert the list is empty, with each mismatch naming the case.
     - Keep it to one test function, so the fixture setup is paid once (~150 inserts on the local libSQL server).
  10. `test_a_drained_entry_leaves_the_overlay_and_the_database_holds_the_resend` (AC 5, `temp_db` + module journal): append a qualifying row; `check_duplicate("u1","k")` (row timestamp = now, minus a few seconds, formatted) → duplicate from the journal while `find_duplicate_timestamp` → `None`; `journal_drainer.drain_once(journal)` → `DrainOutcome.DRAINED`; `audit_journal.pending_duplicate(...) is None`; `check_duplicate` → still a duplicate with the **same** `first_query_at` (original timestamp, D11), now from the database. Reset `journal_drainer._held_back` as `tests/test_db_resilience_drain.py:67-72` does, if needed.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db_resilience_overlay.py -q`

### Task 8: `tests/test_db_resilience_headroom.py` (non-`db`)

- **File**: `tests/test_db_resilience_headroom.py`
- **Action**: CREATE
- **Implement**: fixture `full_journal(tmp_path)`: `open_journal(dir, max_bytes=2 * _JOURNAL_ENTRY_RESERVE_BYTES, pipeline_max_workers=2)`, so the headroom threshold is `0`. Append one valid audit row (with a write_id), so `bytes > 0`, i.e. above headroom. `close_journal()` in teardown. Fail-if-called stubs on `query_pipeline.log_query`, `query_pipeline.check_duplicate`, `query_pipeline.admit`, `audit_logger.insert_audit_log`; record `journal.entries()` before and after (must stay 1, so no row was journaled). A counting upstream (`tests/test_db_resilience_release.py:120-133` `_Upstream`).
  1. `test_headroom_ok_admits_and_an_empty_journal_is_at_the_boundary`: the same parameters with no append (`bytes == 0 == threshold`) → `check_admission_headroom()` passes. One append → raises `AuditHeadroomError`, an `AuditUnavailableError` and a `StorageError`.
  2. `test_no_open_journal_is_a_no_op`.
  3. `test_pipeline_refuses_before_step_2_with_no_row_and_no_upstream` (AC 4): `run_conversation` raises `AuditHeadroomError`. Upstream `sent == 0`. No stub called, including `authorize`: patch `query_pipeline.authorize` to fail if called, which proves the refusal is before step 2. Also through `run_query`.
  4. `test_the_refusal_logs_sizes_not_contents` (caplog: `bytes=` present; the row's `prompt_preview` sentinel absent).
  5. `/query` (`TestClient(app)` without `with`, so no lifespan; `_admin_headers` as in `tests/test_db_resilience_release.py:83-84`): `503`, `{"detail": STORAGE_UNAVAILABLE_NOT_SENT_DETAIL}`, `Retry-After == "1"`, upstream (`app.routers.query.call_openrouter`) not called.
  6. `/v1` non-stream, stream (`"stream": true`) and tools (`V1_TOOLS_ENABLED=True` plus a tools body, following the `tests/test_db_resilience_release.py` tools test at `:557`): each `503`, JSON (not SSE) body `error.code == "storage_unavailable"`, `error.message == STORAGE_UNAVAILABLE_MESSAGE`, `Retry-After == "1"`, upstream `sent == 0`. Use the `v1` fixture pattern (`tests/test_db_resilience_release.py:481-486`).
  7. Chat UI (`@pytest.mark.asyncio`): `_make_state` / `_send` as in `tests/test_chat_ui_storage_failures.py:42-52`. Stub `chat_state_mod.resolve`, `chat_sessions.create`, and `chat_state_mod.run_in_pipeline` with an inline runner (`async def inline(fn, *a, **k): return fn(*a, **k)`), so the **real** pipeline runs. Stub `chat_state_mod.call_openrouter` with a counter. Bubble `kind == "internal_error"`, `detail == STORAGE_UNAVAILABLE_NOT_SENT_NOTICE`, `state.pending is False`, upstream 0 calls. If `_append_and_persist` touches storage on this path, set `CHAT_HISTORY_ENABLED=False` or stub its persistence as the existing tests do.
  8. `test_a_step8_audit_unavailable_keeps_its_own_copy` (regression for R2): a plain `AuditUnavailableError` still gets `STORAGE_UNAVAILABLE_DETAIL` / `AUDIT_UNAVAILABLE_MESSAGE` / `AUDIT_UNAVAILABLE_NOTICE`. This is already covered by `tests/test_db_resilience_release.py:446-459, :532` and `tests/test_chat_ui_storage_failures.py:242-255`, so just run those and do not duplicate them.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db_resilience_headroom.py -q`

---

## End-to-End Tests

- [ ] `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db_resilience_overlay.py tests/test_db_resilience_headroom.py tests/test_audit_journal.py tests/test_duplicate_checker.py tests/test_db_resilience_release.py tests/test_db_resilience_drain.py tests/test_chat_ui_storage_failures.py tests/test_chat_ui_startup_guard.py tests/test_pii_dedup_isolation.py tests/test_messages.py tests/test_untouched_app.py tests/test_pii_redaction_integration.py -q` (one process; libSQL dev server on :8080)
- [ ] `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db.py -k "find_duplicate_timestamp or dedup_lookup_shape or mark_audit_log_failed" -q` (the SQL-shape pin still holds after the comment)
- [ ] Full suite: GitHub CI on push (user decision)

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
# chat_ui touched -> tests/test_chat_ui_startup_guard.py (probe form per SUBAGENT_BRIEF)
```

---

## Acceptance Criteria

(Copied from story `STORY-011`, with how each is covered)

- [ ] AC 1: journaled success + recovered DB + resend → `check_duplicate` (DB lookup found nothing) uses `audit_journal.pending_duplicate(user_id, dedup_key, since)` → `QueryBlockedDuplicateResponse(first_query_at=<journaled timestamp>)`. Tasks 2 and 4; tests 7.3 and 7.10.
- [ ] AC 2: a failed lookup → `DuplicateCheckError` (fail closed); the overlay never stands in for the DB and is not used when the lookup found a row. Task 4 (R1); tests 7.4, 7.5 (and 7.6 for the race).
- [ ] AC 3: every excluded row shape, written to the table and the journal, gets the same answer; both predicates carry a cross-reference comment. Tasks 2, 3; tests 7.8, 7.9 (clause list parsed from the SQL, AST operand count, field sweep).
- [ ] AC 4: `bytes > MAX − W×65536` → refused before step 2 with 503 (`/query` fixed detail, `/v1` `storage_unavailable` stream/non-stream/tools, chat `internal_error`), no row, zero upstream calls. Tasks 1, 2, 5, 6; tests 8.1-8.7.
- [ ] AC 5: a drained entry leaves the overlay index; a later resend is held by the DB lookup. Test 7.7 and the `db` test 7.10.
- [ ] All tasks completed
- [ ] Backend imports without error; chat UI startup-guard probe passes
- [ ] Follows existing patterns (docstrings cite PRD-018 decisions; fixed copy; no driver text; no new dependency; `audit_journal` still imports no settings or database)

---

## Risks

| Risk | Mitigation |
|------|------------|
| Drain race between lookup and overlay read (same-instance T4) | R1: snapshot before the lookup, use after; test 7.6 |
| Overlay drifts from SQL (Risk 6) | Clause list parsed from the SQL source must equal `_SHAPES`; AST operand count of `_is_prior_query` must equal the clause count; the field sweep catches an overlay-only exclusion on any column; cross-reference comments both ways |
| Adding a docstring to `find_duplicate_timestamp` breaks `test_find_duplicate_timestamp_sql_is_the_planned_shape` (`tests/test_db.py:2563-2577`) | Cross-reference is a `#` comment inside `_op`; SQL untouched |
| `duplicate_checker` guard tests (no "pii"/"redact" words, `hash_prompt(` census, no `messages` import) | Called out in Task 4 |
| `audit_journal` purity (`tests/test_audit_journal.py:490-497`) | New code imports only `app.db.errors`; no settings, no database |
| Retry-After of `1` on a headroom refusal while the breaker is open | R3: accepted; the retry is refused at entry again before any work |
| `/query` foreign-session refusal row (`app/routers/query.py:~160`) is written in the router before `run_query`, so before the headroom check | Out of scope: it is not the pipeline. When the journal is full its append raises `AuditUnavailableError` and the request already fails closed with 503 (STORY-010 R1). Noted for the orchestrator |
| Parity `db` test runtime (~150 inserts) | One test function, one fixture setup; the local libSQL server is fast |
| Residual T4 (cross-instance resend) | Accepted; documented in STORY-014 (story Technical Notes) |
