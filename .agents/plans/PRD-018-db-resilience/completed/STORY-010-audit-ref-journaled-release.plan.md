---
story: STORY-010
prd: PRD-018
slug: audit-ref-journaled-release
title: AuditRef, journaled release of step 8, PRD-017 D13 decisions path, audit_ref response fields
type: NEW_CAPABILITY
complexity: HIGH
epic_branch: epic/PRD-018-db-resilience        # all stories commit here, no per-story branch
created: 2026-11-17
---

# Plan: Release under a journaled record (PRD-018 F7, D13, D14, O2, O8)

## Summary

`audit_logger.log_query` returns a frozen `AuditRef(audit_id: Optional[int], write_id: str)` instead of an int. When `insert_audit_log` raises `StorageUnavailableError` (retry budget spent, retry refused, or breaker open), it appends the row to the journal (`audit_journal.append`) and returns `AuditRef(None, write_id)`. If the append fails, `AuditUnavailableError` propagates. It also propagates when no journal is open (`current() is None`), because the module-level `append` already raises in that case. A STATEMENT or non-transient `StorageError` is not journaled and propagates as today. For a request with tool decisions, step 8 passes `log_query` a `journal_decisions` callable, so a journaled row carries its decisions **in the same entry** (D13). `action_audit.record(decisions, identity, audit_ref=None, session_id=None)` keys its rows `<audit write_id>:<i>`. If the row committed and the decisions write raises `StorageUnavailableError`, it journals a decisions-only entry (`audit_id` known, `write_id` = the audit row's `write_id`). If the row was journaled, `record` writes nothing, because the decisions are already in the row's entry. A direct call with no ref (`audit_ref=None`) never journals, and neither does `database.insert_action_decisions` (O8). On success, `QuerySuccessResponse` and `/v1`'s `harness` gain `audit_ref` (`audit_id` becomes `Optional[int]`). A journaled `/v1` success sends `X-Harness-Audit-Ref` instead of `X-Harness-Audit-Id`, and its id is `chatcmpl-harness-ref-<write_id>`. The chat UI stores `audit_id` NULL. `AuditUnavailableError` maps to `/query` 503 `"Storage unavailable"` + `Retry-After` and to `/v1` 503 `storage_unavailable`, with a new fixed message. Tools keep PRD-017's 500 `internal_error`, via `ActionAuditError`. The chat UI shows a new fixed `internal_error` detail that does not say "nothing was sent".

## User Story

As a compliance admin
I want an answer that was already paid for to be released only once its audit row (and decisions) is committed or fsynced to the journal
So that the trail has no hole and nothing is released without a record

## Story Reference

- Story file: `.agents/stories/PRD-018-db-resilience/STORY-010-audit-ref-journaled-release.md`
- PRD: `.agents/PRDs/PRD-018-db-resilience/PRD.md`: 4 (In Scope, audit_ref, :79), 5 story 4 example (:114), 6.3 rows 6, 8, 9 (:189-192), 6.7 (:267-281), 6.8 (journal format, Durability, Bounds, :283-303), 7 F7 (:363-364), 9.2 T5 (:398), 10 (:433, :456-457), 14 Risk 5 (:539), 15 D13/D14 (:561-562), O2 (:573), O8 (:579)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | HIGH |
| Systems Affected | `app/services/audit_logger.py`, `app/services/action_audit.py`, `app/services/query_pipeline.py`, `app/services/storage_faults.py`, `app/services/v1_translate.py`, `app/routers/query.py`, `app/routers/v1.py`, `app/models/schemas.py`, `app/models/v1_schemas.py`, `app/db/audit_journal.py` (docstring only), `chat_ui/chat_ui/state.py`, `chat_ui/chat_ui/copy.py`, tests |
| Story | STORY-010 |
| PRD | PRD-018 |
| Epic Branch | `epic/PRD-018-db-resilience` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` (visual design of new UI). This story adds one fixed copy string and one `except` arm to `chat_ui/chat_ui/state.py`. It adds no component and no styling. `chat_ui/AGENTS.md` asks for the Reflex agent skills before editing Reflex code. The `state.py` change is a plain Python exception arm that uses no Reflex API, so those skills are not needed. Validation uses the repo's startup-guard probe (SUBAGENT_BRIEF). | — |

---

## Orchestrator rulings requested (proposals; the plan implements them unless overruled)

- **R1 — A refusal row that can be neither written nor journaled → refuse with 503; do not return the refusal.** `_deny` and the refusal arms at steps 2c, 3, 4, 5 (block), 6 (redaction limit, PII error) and 7 (upstream error), plus `/query`'s foreign-session refusal, let `AuditUnavailableError` propagate. The flag row at step 5, which writes and then continues, aborts the request before upstream. Why: (a) D10 / 6.8 Bounds: `AuditUnavailableError` means "the request **fails closed**: nothing is released without a record". (b) A refusal *is* a release. It discloses a verdict: a duplicate's `first_query_at`, the matched `pattern`, `required_permission`, a usage-limit figure. PRD-008 STORY-010 requires a rejected send to be "logged with the same rigour as an accepted one". (c) It costs the user nothing. Every refusal arm except steps 7 and 8 runs before any upstream call, so a 503 with `Retry-After` is the cheap, honest answer, and a retry meets the same verdict once storage answers. (d) It needs no new code. The exception already propagates out of `log_query`, so the only work is the ingress mapping. One consequence to note: on the upstream-error arm (step 7) and the output-redaction arm (step 8), a journal failure turns today's 502/500 into a 503. That is still a refusal with nothing released. In practice a refusal row reaches `AuditUnavailableError` only when the journal is full or broken (or no journal is open), and STORY-011's headroom check refuses those requests at entry.
- **R2 — "tools" in 6.7's `AuditUnavailableError` row means a response with decisions to record (`outcome is not None`).** When the **row itself** can be neither written nor journaled on such a request, the pipeline raises `ActionAuditError` from the `AuditUnavailableError`, so `/v1` answers PRD-017's 500 `internal_error` (6.7: "tools: PRD-017's 500 internal_error, unchanged"). No `mark_audit_log_failed` runs, because no row exists. When the row committed and the **decisions** can be neither written nor journaled, today's D8 path runs unchanged: `record` raises `AuditUnavailableError`, which is a `StorageError`, so the existing `except StorageError` → `mark_audit_log_failed` → `ActionAuditError` handles it. A `tools=` request whose response has no calls behaves like any other request: 503 `storage_unavailable`.
- **R3 — `record()` with a journaled ref (`audit_id is None`) is a no-op returning `[]`.** The decisions are already in the row's entry, which `log_query` wrote through `journal_decisions`. The alternative is to have the pipeline skip `record()` when the ref is journaled, and have `record()` raise `ValueError` for such a ref, which is louder on misuse. The plan takes the no-op because AC 2 phrases the outcome as "when `record(...)` runs". A pipeline test pins that the entry holds the decisions. Pick the other if you prefer fail-loud.
- **R4 — Healthy `/v1` headers stay byte-identical.** `X-Harness-Audit-Id` only, and no `X-Harness-Audit-Ref`. The PRD says "`X-Harness-Audit-Ref` instead of `X-Harness-Audit-Id`" only for the journaled case (6.7, D14), so a journaled success sends `X-Harness-Audit-Ref` only.
- **R5 — The `Retry-After` of an `AuditUnavailableError` 503** is the `retry_after_seconds` of the first `StorageUnavailableError` in its `__context__` chain, else `1`. The append runs inside `log_query`'s / `record`'s `except StorageUnavailableError` block, so the outage that sent the row to the journal is on the chain. When the write failed, an `OSError` sits between them. `AuditUnavailableError` (STORY-008) gets no new attribute.
- **R6 — The decisions-only entry's `write_id` is the audit row's `write_id`.** This is safe against the journal's duplicate-pending `ValueError` (`app/db/audit_journal.py:317-318`): a decisions-only entry is written only after the audit row **committed** (`audit_id` is an int), so that `write_id` was never journaled. A journaled row puts its decisions in its own entry and never writes a decisions-only one. The drainer keys `mark_drained` on the entry's `write_id` (`app/db/journal_drainer.py:116-129`) and passes `audit_id=entry.audit_id` to `drain_journal_entry` (`app/db/database.py:3112-3150`), which never reads the entry `write_id` into SQL. Update the one stale line in `audit_journal`'s docstring (`:45-46` "a decisions-only entry uses the caller's batch hex").

---

## Patterns to Follow

### Naming / frozen dataclasses
```python
# SOURCE: app/db/audit_journal.py:98-106
@dataclasses.dataclass(frozen=True)
class JournalEntry:
    """One acknowledged journal line, decoded."""

    write_id: str
    appended_at: str
    audit: Optional[AuditLog]
    audit_id: Optional[int]
    decisions: tuple[ActionDecisionRow, ...]
```

### Write-id minting and keyed decisions (STORY-004)
```python
# SOURCE: app/services/action_audit.py:200-208
    if not decisions:
        return []
    timestamp = datetime.now(timezone.utc).strftime(_TIMESTAMP_FORMAT)
    batch = _new_write_id()
    rows = [
        _row_of(d, identity, timestamp, audit_id, session_id, f"{batch}:{index}")
        for index, d in enumerate(decisions)
    ]
    return insert_action_decisions(rows)
```

### Journal API (STORY-008): module `append` fails closed with no journal
```python
# SOURCE: app/db/audit_journal.py:664-669
def append(*args, **kwargs) -> JournalEntry:
    """Append to the open journal; fail closed when there is none (D13)."""
    journal = _current
    if journal is None:
        raise AuditUnavailableError("audit journal is not open")
    return journal.append(*args, **kwargs)
```
`AuditJournal.append(audit=None, decisions=(), *, audit_id=None, write_id=None)` (`:292-346`): an audit entry takes `write_id` from `audit.write_id`. A decisions-only entry needs `audit_id` (an int) and `write_id`. Every decision needs a `write_id` and `id is None`.

### Error handling: the D8 arm this story extends
```python
# SOURCE: app/services/query_pipeline.py:923-946
    if outcome is not None:
        try:
            action_audit.record(
                outcome.decisions, identity, audit_id=audit_id, session_id=session_id
            )
        except StorageError as exc:
            logger.error(
                "action audit failed: user_id=%s audit_id=%s", identity.user_id, audit_id
            )
            ...
            raise ActionAuditError(
                "Action audit failed: decisions could not be recorded"
            ) from exc
```

### Ingress mapping (STORY-006)
```python
# SOURCE: app/routers/query.py:47-60
    except (ChatSessionError, DuplicateCheckError, UsageLimitError) as exc:
        cause = storage_unavailable_cause(exc)
        if cause is not None:
            logger.warning(
                "query request refused: user_id=%s code=storage_unavailable retry_after=%s", ...)
            raise HTTPException(
                status_code=503,
                detail=STORAGE_UNAVAILABLE_NOT_SENT_DETAIL,
                headers=retry_after_headers(cause),
            ) from exc
```
```python
# SOURCE: app/routers/v1.py:246-256 (_outcome)
        if code == STORAGE_UNAVAILABLE:
            # Fixed copy, never `str(exc)`: that is driver text (T9, PRD-018 D8).
            cause = storage_unavailable_cause(exc)
            assert cause is not None
            return translate_fault(
                code, STORAGE_UNAVAILABLE_MESSAGE, retry_after_seconds=cause.retry_after_seconds
            )
```

### Chat UI fixed copy (STORY-007)
```python
# SOURCE: chat_ui/chat_ui/copy.py:37-39
STORAGE_UNAVAILABLE_NOT_SENT_NOTICE = (
    "The harness's database is unavailable, so nothing was sent. Retry in a moment."
)
```
```python
# SOURCE: chat_ui/chat_ui/state.py:1246-1257 -- the catch-all this story pre-empts
            except Exception as exc:
                await self._append_and_persist(
                    ChatMessage(kind="internal_error", content="internal_error",
                                prompt=text, detail=str(exc)),
                    identity, session_id)
                return
```

### Tests
```python
# SOURCE: tests/test_db_resilience_drain.py:74-78 -- a journal under tmp_path, always closed
@pytest.fixture
def journal(tmp_path):
    j = AuditJournal(str(tmp_path / "buf"), 1 << 20, 2)
    yield j
    j.close()
```
```python
# SOURCE: tests/test_audit_journal.py:33-37 -- module slot opened via open_journal must be closed
@pytest.fixture(autouse=True)
def _slot_clean():
    assert audit_journal.current() is None
    yield
    audit_journal.close_journal()
```
- Non-`db` ingress tests: `tests/test_db_resilience_ingress.py:92-110` (`upstream` recorder fixture, `v1_identity` override). The conftest guard proves zero driver calls.
- `db` fault tests: `tests/db_faults.py:86-100` `Fault(text, op, sql, nth, times, when)` + the `faulty_db` fixture (`tests/conftest.py:831`). The breaker is fresh per test (`tests/conftest.py:689`).
- Every modified pre-existing assertion carries `# PRD-018 D14:` (body/shape) or `# PRD-018 F7:` (the `AuditRef` return / `record` signature).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/audit_logger.py` | UPDATE | `AuditRef`, journal fallback in `log_query`, `journal_decisions` parameter, logger |
| `app/services/action_audit.py` | UPDATE | `decision_rows(...)`, `record(..., audit_ref=None, ...)` keyed `<write_id>:<i>`, decisions-only journal fallback, O8 docstring |
| `app/services/query_pipeline.py` | UPDATE | step 8: `AuditRef`, `journal_decisions`, R2 arm, `record(audit_ref=...)`, response fields |
| `app/models/schemas.py` | UPDATE | `QuerySuccessResponse.audit_id: Optional[int]`, `audit_ref: str` |
| `app/models/v1_schemas.py` | UPDATE | `HarnessCompletionInfo.audit_id: Optional[int]`, `audit_ref: str`; `CHAT_COMPLETION_REF_ID_PREFIX`, `chat_completion_ref_id()` |
| `app/services/v1_translate.py` | UPDATE | `translate_result` id + harness fields; `AUDIT_UNAVAILABLE_MESSAGE` |
| `app/services/storage_faults.py` | UPDATE | `audit_unavailable_retry_after(exc)` (R5) |
| `app/routers/query.py` | UPDATE | `except AuditUnavailableError` → 503 `STORAGE_UNAVAILABLE_DETAIL` + `Retry-After` |
| `app/routers/v1.py` | UPDATE | `AuditUnavailableError` in `_PIPELINE_FAULTS`, `_fault_code`, `_outcome`; header choice in `_json_response` |
| `app/db/audit_journal.py` | UPDATE | docstring line `:45-46` only (R6) |
| `chat_ui/chat_ui/copy.py` | UPDATE | `AUDIT_UNAVAILABLE_NOTICE` |
| `chat_ui/chat_ui/state.py` | UPDATE | `except AuditUnavailableError` arm; `audit_id=result.audit_id or 0` |
| `tests/test_db_resilience_release.py` | CREATE | the story's tests (non-`db` + one `db` fault test) |
| `tests/test_chat_ui_storage_failures.py` | UPDATE | chat UI: the fixed bubble for `AuditUnavailableError`; a journaled success stores NULL |
| existing tests (see Task 11) | UPDATE | `AuditRef` return, `record(audit_ref=...)`, D14 shapes |
| `tests/test_pii_redaction_integration.py` | UPDATE | register one renamed test in `_DELIBERATELY_SUPERSEDED_TESTS` |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: `AuditRef` and the journal fallback in `log_query`

- **File**: `app/services/audit_logger.py`
- **Action**: UPDATE
- **Implement**:
  - `import dataclasses, logging`; `from typing import Callable, Optional, Sequence`; `from app.db import audit_journal` (module import, so tests patch `audit_journal._current` / open a journal); `from app.db.errors import StorageUnavailableError`; `from app.db.models import ActionDecisionRow, AuditLog`. There is no cycle: `audit_journal` imports only `app.db.errors` / `app.db.models` (`app/db/audit_journal.py:70-71`).
  - `logger = logging.getLogger(__name__)`.
  - ```python
    @dataclasses.dataclass(frozen=True)
    class AuditRef:
        """Where an audit row is recorded (PRD-018 F7, D13, D14). `audit_id` is the
        committed row's id, or None when the row is only fsynced to the journal
        (released with `audit_id: null`, O2). `write_id` is always set: the row's
        key, the client-facing `audit_ref`."""
        audit_id: Optional[int]
        write_id: str
    ```
  - `log_query(..., ignored_params=None, journal_decisions: Optional[Callable[[str], Sequence[ActionDecisionRow]]] = None) -> AuditRef`. Add a comment block in the house style: the parameter exists for step 8 of a request with tool decisions only (D13: a journaled row carries its decisions in the same entry). The callable receives the row's `write_id`. It is called only on the journal path, so the healthy path builds no extra rows.
  - Body: build `entry` as today, then
    ```python
    try:
        audit_id = insert_audit_log(entry)
    except StorageUnavailableError:
        decisions = tuple(journal_decisions(entry.write_id)) if journal_decisions is not None else ()
        audit_journal.append(entry, decisions)   # AuditUnavailableError propagates (D10, T5)
        logger.warning("audit row journaled: user_id=%s write_id=%s decisions=%d", ...)
        return AuditRef(None, entry.write_id)
    return AuditRef(audit_id, entry.write_id)
    ```
    Only `StorageUnavailableError` is caught. A STATEMENT failure (`IntegrityError`, `MissingRelationError`) or any other `StorageError` propagates as today (orchestrator note). The log carries no driver text: the unit of work has already logged it through `_retry_detail`.
  - Replace the STORY-004 comment "Still returns the int id; STORY-010 changes that." (`:120-124`) with the journal rule. Update the `_new_write_id` docstring only if it now reads stale (it already names `audit_ref`, so it should not).
- **Mirror**: `app/db/journal_drainer.py:55, 58` (module import of `audit_journal`, logger), the comment density of `audit_logger.py:44-85`.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: `action_audit.record` takes the ref; decisions-only fallback; O8 rule

- **File**: `app/services/action_audit.py`
- **Action**: UPDATE
- **Implement**:
  - Imports: `from app.db import audit_journal`, `from app.db.errors import StorageUnavailableError`, and `AuditRef` from `app.services.audit_logger` (already imported from there, `:58-62`).
  - New public `decision_rows(decisions, identity, write_id: str, audit_id: Optional[int] = None, session_id: Optional[str] = None) -> list[ActionDecisionRow]`: one UTC timestamp, rows keyed `f"{write_id}:{index}"`. The pipeline passes it to `log_query` as `journal_decisions` (Task 3), and `record` uses it too, so both paths build identical rows from one function.
  - `record(decisions, identity, audit_ref: Optional[AuditRef] = None, session_id=None) -> list[int]`. The `audit_id=` keyword is removed, per the PRD 10 signature (`:457`).
    - `not decisions` → `[]` (unchanged).
    - `audit_ref is None` → a direct call: fresh `_new_write_id()` batch, `audit_id` NULL, `insert_action_decisions(rows)`, **no journal** (today's behaviour, and O8).
    - `audit_ref.audit_id is None` → return `[]`. The row was journaled and its decisions went into the same entry (R3).
    - Otherwise: rows keyed `<audit_ref.write_id>:<i>` with `audit_id=audit_ref.audit_id`. `try: return insert_action_decisions(rows)`. `except StorageUnavailableError:` → `audit_journal.append(None, rows, audit_id=audit_ref.audit_id, write_id=audit_ref.write_id)`, a WARNING `"action decisions journaled: user_id=%s audit_id=%s write_id=%s decisions=%d"`, then return `[]`. `AuditUnavailableError` propagates, and the pipeline's D8 arm catches it as a `StorageError`.
  - Docstrings: the module docstring's "`write_id`" bullet (`:27-29`) now reads `<audit write_id>:<i>` when a ref is given, or a fresh batch hex for a direct call. Replace the "No catch." paragraph (`:42-45`). The `record` docstring states the **O8 rule** verbatim: the journal satisfies "recorded" only for PRD-017's post-response release (step 8, a ref from `log_query`). A pre-execution decision write (PRD-023's MCP pre-forward write, PRD-023 T9) must call without a ref, or `database.insert_action_decisions` directly. That path commits or raises and never journals (PRD-018 O8, D13). Cite PRD-018 O8 and PRD-023 T9.
- **Mirror**: `action_audit.py:183-208`.
- **Validate**: import check as above.

### Task 3: Step 8 in the pipeline

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**:
  - Import `AuditUnavailableError` from `app.db.errors` (`:7`) and `functools`.
  - `:893` `audit_id = log_query(` → `audit_ref = log_query(`, passing `journal_decisions=None if outcome is None else functools.partial(action_audit.decision_rows, outcome.decisions, identity, session_id=session_id)`. Call it through the module (`action_audit.decision_rows`) for the DD-5 monkeypatch rule (`:17-20`). Wrap that one call:
    ```python
    except AuditUnavailableError as exc:
        if outcome is None:
            raise                                    # /query 503, /v1 503 storage_unavailable
        logger.error("action audit failed: user_id=%s audit_id=%s", identity.user_id, None)
        raise ActionAuditError("Action audit failed: decisions could not be recorded") from exc  # R2
    ```
    The call stays one `log_query(` site with `has_tool_calls=`. `tests/test_query_pipeline_tools.py:783-788` counts 11 sites, and `tests/test_query_pipeline_audit_fields.py` / `test_query_pipeline_pii_profiles.py` scan them, so keep every keyword spelled out.
  - D8 arm (`:923-946`): `action_audit.record(outcome.decisions, identity, audit_ref=audit_ref, session_id=session_id)`. The log and `mark_audit_log_failed(audit_ref.audit_id, ...)` keep today's text. This arm is reached only when `audit_ref.audit_id` is an int, because a journaled ref makes `record` return `[]`. Add a comment citing PRD-018 D13: the journal is "recorded", so release follows the commit or the fsync, and `AuditUnavailableError` from `record` is a `StorageError` and takes this arm unchanged.
  - `QuerySuccessResponse(... audit_id=audit_ref.audit_id, audit_ref=audit_ref.write_id, ...)` (`:948-955`).
  - Refusal arms (`_deny` `:288`, `:465`, `:511`, `:543`, `:598`, `:635`, `:677`, `:725`, `:765`, `:854`): no code change. Their `log_query` journals on its own, and on `AuditUnavailableError` propagates (R1). Add one comment at `_deny` stating R1 (PRD-018 D10/T5: a refusal is a release; an unrecordable one is refused with 503).
  - Update the `ActionAuditError` docstring (`:82-91`) for D13: "after the success row was committed or journaled ... or the row itself could not be recorded on a tools response (PRD-018 6.7)".
- **Mirror**: the existing step 8 code.
- **Validate**: import check; `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_query_pipeline_tools.py -q`

### Task 4: Response schemas

- **Files**: `app/models/schemas.py`, `app/models/v1_schemas.py`
- **Action**: UPDATE
- **Implement**:
  - `QuerySuccessResponse` (`schemas.py:77-87`): `audit_id: Optional[int]` (still **required**, no default, so a forgotten arm is a validation error) and `audit_ref: str` (required) on the line after it. That matches the PRD 10 key order `"audit_id":null,"audit_ref":"…","model_used"`. Comment: PRD-018 D14 / O2, `audit_id` stays an int whenever the row committed, `audit_ref` equals the row's `write_id` on every success.
  - `HarnessCompletionInfo` (`v1_schemas.py:164-180`): `audit_id: Optional[int]` (serialized as `null`, never dropped) and `audit_ref: str` after it. Update the docstring.
  - `v1_schemas.py:23-33`: add `CHAT_COMPLETION_REF_ID_PREFIX = "chatcmpl-harness-ref-"` and `def chat_completion_ref_id(audit_ref: str) -> str`. Its docstring names D14 and explains why the prefix differs: a client that parses the int after `chatcmpl-harness-` must not misread a hex ref. `chat_completion_id(audit_id: int)` is unchanged, which keeps `tests/test_v1_schemas.py:263-265` green. Update the `ChatCompletionChunk` docstring (`:240-241`): "`chat_completion_id(audit_id)`, or `chat_completion_ref_id(audit_ref)` when journaled".
- **Validate**: import check.

### Task 5: `/v1` translation

- **File**: `app/services/v1_translate.py`
- **Action**: UPDATE
- **Implement**:
  - `translate_result` (`:567-643`): `id=chat_completion_id(result.audit_id) if result.audit_id is not None else chat_completion_ref_id(result.audit_ref)`, and `HarnessCompletionInfo(audit_id=result.audit_id, audit_ref=result.audit_ref, ...)`. Add the docstring sentence (D14). The stream inherits both fields through `v1_sse.completion_events`, which copies `completion.id` into every chunk (`app/services/v1_sse.py:60-65`). The chunks carry no `harness`, so a journaled stream finishes normally and its ref is the chunk `id`.
  - Beside `STORAGE_UNAVAILABLE_MESSAGE` (`:100-101`): `AUDIT_UNAVAILABLE_MESSAGE = "Storage is unavailable; the response could not be recorded, so it was not released."` Fixed copy. It does not say "not sent to the model", because step 8 runs after the upstream call.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_v1_translate_result.py -q` (after Task 11's edits to that file).

### Task 6: `storage_faults` helper

- **File**: `app/services/storage_faults.py`
- **Action**: UPDATE
- **Implement**: `def audit_unavailable_retry_after(exc: AuditUnavailableError) -> int`. It walks `exc.__context__` (bounded by the chain's end) and returns the first `StorageUnavailableError.retry_after_seconds`, else `1` (R5). The docstring explains why `__context__` and not `__cause__`: the journal raises `from` an `OSError` on a write failure, and the outage is the context the append ran in. Import `AuditUnavailableError`. The module still does no I/O.
- **Validate**: import check.

### Task 7: `/query` mapping

- **File**: `app/routers/query.py`
- **Action**: UPDATE
- **Implement**: add an arm to `query()` (`:36-64`), after the gate arm and before `PiiRedactorError`:
  ```python
  # PRD-018 D10/D13, T5: the row could be neither committed nor journaled, so
  # nothing is released -- a success or a refusal (R1). Fixed copy, not "not
  # sent": step 8 runs after the upstream call.
  except AuditUnavailableError as exc:
      retry_after = audit_unavailable_retry_after(exc)
      logger.warning("query request refused: user_id=%s code=audit_unavailable retry_after=%s", ...)
      raise HTTPException(503, detail=STORAGE_UNAVAILABLE_DETAIL, headers={"Retry-After": str(retry_after)}) from exc
  ```
  This also covers the foreign-session refusal row (`:141-155`). Its journal failure becomes this 503, not the 403 (R1).
- **Validate**: import check.

### Task 8: `/v1` mapping and headers

- **File**: `app/routers/v1.py`
- **Action**: UPDATE
- **Implement**:
  - Import `AuditUnavailableError` and `audit_unavailable_retry_after`, plus `AUDIT_UNAVAILABLE_MESSAGE`.
  - `_PIPELINE_FAULTS` (`:116-122`): add `AuditUnavailableError`, and extend the comment. `_STORAGE_GATE_FAULTS` is unchanged.
  - `_fault_code` (`:212-230`): `if isinstance(exc, AuditUnavailableError): return STORAGE_UNAVAILABLE`, before the gate test.
  - `_outcome` (`:246-256`): when `code == STORAGE_UNAVAILABLE` and `exc` is an `AuditUnavailableError`, return `translate_fault(code, AUDIT_UNAVAILABLE_MESSAGE, retry_after_seconds=audit_unavailable_retry_after(exc))`. Otherwise keep the existing branch.
  - Post-commit: `_sse_events` already sends any `_PIPELINE_FAULTS` outcome as the error event (`:279-305`). A journal failure after a stream committed therefore becomes an SSE `storage_unavailable` event, with no `Retry-After`, as 6.7 states. Tools requests never reach this, because they arrive as `ActionAuditError` (R2).
  - `_json_response` (`:269-276`): `harness = outcome.harness`. Send `{"X-Harness-Audit-Id": str(harness.audit_id)}` when `audit_id is not None`, else `{"X-Harness-Audit-Ref": harness.audit_ref}` (R4, D14). Update the `:370` comment: "Every chunk's id carries the id or, when journaled, the ref".
- **Validate**: import check.

### Task 9: Chat UI

- **Files**: `chat_ui/chat_ui/copy.py`, `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**:
  - `copy.py`, after `STORAGE_UNAVAILABLE_NOT_SENT_NOTICE` (`:37-39`): `AUDIT_UNAVAILABLE_NOTICE = "The harness's database is unavailable and this send could not be recorded, so nothing is shown. Retry in a moment."`. Add a comment citing PRD-018 T5/T9 and the orchestrator's STORY-007 note: it must not say "nothing was sent", because the model may have been called.
  - `state.py`: import `AuditUnavailableError` from `app.db.errors` and the new copy constant. Add an arm **before** `except Exception as exc:` (`:1246`): `except AuditUnavailableError:` → an `internal_error` bubble with `detail=AUDIT_UNAVAILABLE_NOTICE`, then `return`. Log `logger.warning("chat send refused: user_id=%s code=audit_unavailable", identity.user_id)` with no exception text. Comment: a raw `StorageUnavailableError` on the step 8 write no longer reaches the catch-all, because `log_query` journals it; this arm covers the case where the journal cannot take it.
  - `state.py:1269`: `audit_id=result.audit_id or 0`. Comment: PRD-018 D14 / 6.7, a journaled success has `audit_id` None, the Var cannot be None, and `_to_stored_message` (`:103`) writes `0 or None` → NULL on the transcript row.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_chat_ui_startup_guard.py tests/test_chat_ui_storage_failures.py -q`

### Task 10: `audit_journal` docstring (R6)

- **File**: `app/db/audit_journal.py`
- **Action**: UPDATE (docstring only, `:45-46`)
- **Implement**: "a decisions-only entry uses the caller's `write_id`: the audit row's own `write_id` (STORY-010), unique among pending entries because that row committed rather than journaled". No code change.

### Task 11: Adapt existing tests (each modified line or assertion commented `# PRD-018 F7:` or `# PRD-018 D14:`)

`AuditRef` return of `log_query`:
- `tests/test_audit_logger.py`: 22 `audit_id = log_query(...)` sites (`:18-375`) → `log_query(...).audit_id`. Add one module-level comment, plus `# PRD-018 F7` on each site.
- `tests/test_db_resilience_write_id.py:443-451`: rename `test_log_query_mints_a_hex_write_id_and_still_returns_int` → `test_log_query_mints_a_hex_write_id_and_returns_its_ref`. Assert `isinstance(first, AuditRef)`, an int `audit_id`, and that `first.write_id` equals the stored key. **Register the old name** in `_DELIBERATELY_SUPERSEDED_TESTS` (`tests/test_pii_redaction_integration.py:481`). `:458` `audit_id = log_query(...).audit_id`.
- `tests/test_db_resilience_write_id.py:468-486` (`test_record_keys_its_rows_batch_colon_index`): keep the direct-call assertions and add one case (orchestrator note): `record(decisions, _USER, audit_ref=AuditRef(audit_id=<a real row id>, write_id=W))` keys `W:0..2`.
- The pass-through spies (`test_query_outcomes_regression.py:208`, `test_query_pipeline_patterns.py:470`, `test_query_pipeline_tools.py:624`, `test_query_router.py:813-814`, `test_v1_router.py:308`, `test_v1_sse.py:638`) return the real value and need no change. `test_db_resilience_ingress.py:99-100` and `test_query_pipeline_usage_limits.py:502` stub `log_query` on arms that never reach step 8, so they need no change either. Verify by running them.

`record(audit_ref=...)` (the `audit_id=` keyword is gone):
- `tests/test_action_audit.py:269, 291, 481, 498, 499-506, 554` → `audit_ref=AuditRef(audit_id=N, write_id=_new_write_id())`. The two-argument direct calls (`:188, 307-457`; `test_actions_view.py:127-129, 274-291`; `test_admin_actions.py:390`; `test_action_corpus.py:631, 866`; `test_db_resilience_write_id.py:475-476`) are unchanged.
- `tests/test_query_pipeline_tools.py:795-870`: the `record` stubs take `*args, **kwargs` and are unchanged. Re-run.

Body / schema shapes (healthy path = old body + `audit_ref`), D14:
- `tests/test_schemas.py:41-55, 285-300`: add `audit_ref="…"` to the construction and to the expected dump. The other 2 constructions there get `audit_ref`.
- `tests/test_query_router.py:181-190, 765-775` and `tests/test_pii_redaction_integration.py:120-128`: add `"audit_ref": body["audit_ref"]` to the expected dict, and assert it is 32 hex and equals the row's `write_id`.
- `tests/test_query_pipeline_tools.py:659-661`: add `"audit_ref"` to the key set.
- `tests/test_v1_tools.py:1367-1381`: `fields` gains `"audit_ref"`. This is the OpenAPI properties assertion; the `QuerySuccessResponse` JSON schema also gains the `audit_id` anyOf-null. The `QuerySuccessResponse(...)` constructions there get `audit_ref=`, and so does `HarnessCompletionInfo(audit_id=42, ...)` at `:1058`.
- `tests/test_v1_router.py:120-138`: the expected body's `harness` gains `"audit_ref": row.write_id`. The header assertion at `:138` is unchanged (R4).
- `tests/test_v1_translate_result.py:57-66` (`_success` gains `audit_ref`), `:107` (golden `harness`), `:552` (key set gains `"audit_ref"`).
- `tests/test_v1_schemas.py:58` (`_COMPLETION_EXAMPLE` harness), `:144`, `:392`, `:419-440`, `:458`: add `audit_ref`.
- `tests/test_v1_sse.py:181`: `HarnessCompletionInfo(... audit_ref=...)`. The QuerySuccessResponse construction there gets it too.
- `QuerySuccessResponse(` constructions without `audit_ref`, which now fail validation: `tests/test_chat_history_send.py` (2), `test_chat_outcomes_regression.py` (1), `test_chat_state.py` (12), `test_chat_ui_storage_failures.py` (1), `test_rbac.py` (1), `test_usage_bubble.py` (1). Add `audit_ref="0" * 32` or a named constant, with one comment per file.
- Live e2e (`tests/e2e/*`, opt-in) assert only the healthy header (`test_openai_sdk.py:250`) and are unchanged. `tests/e2e/_opencode.py:90` is a canned body and is left alone.
- **Validate**: run every file named above in one pytest call (see Validation).

### Task 12: New tests `tests/test_db_resilience_release.py`

Fixtures:
- `open_journal(tmp_path)`: `audit_journal.open_journal(str(tmp_path / "buf"), 1 << 20, 2)`, yield, `audit_journal.close_journal()`. The conftest fails a leaked journal.
- `outage`: a `StorageUnavailableError("Hrana: STREAM_EXPIRED <canary>", retry_after_seconds=7)`.
- Stub `audit_logger.insert_audit_log` / `action_audit.insert_action_decisions` by name (they are bound into those modules). For pipeline tests, stub `query_pipeline.check_duplicate` → not duplicate and leave `USAGE_LIMITS_ENABLED` off, so the tests are non-`db` and the conftest guard proves zero driver calls.

Tests (non-`db` unless marked):
1. `test_log_query_returns_a_ref_with_the_committed_id`: stub returns 41 → `AuditRef(41, <hex>)`, and the `write_id` is the one passed to the insert.
2. `test_log_query_journals_on_storage_unavailable_and_returns_a_null_id`: the entry's `audit.write_id == ref.write_id`, it has no decisions, the WARNING is present, and the canary appears in no log line.
3. `test_log_query_journal_failure_raises_audit_unavailable` (journal full: `max_bytes` tiny) and `..._no_journal_open` (no fixture) → `AuditUnavailableError`.
4. `test_log_query_statement_failure_is_not_journaled` (`IntegrityError`, `MissingRelationError`, plain `StorageError`) → propagates, and the journal is empty.
5. `test_record_keys_decisions_by_the_audit_write_id`: `<W>:<i>`, `audit_id` set.
6. `test_record_decisions_exhausted_journal_a_decisions_only_entry`: `audit is None`, `audit_id == 41`, `write_id == W`, decision keys `W:i`. Add a duplicate-pending sanity check: append the same `W` twice → `ValueError`, which shows why R6 holds only because the row committed.
7. `test_record_with_a_journaled_ref_writes_nothing` (R3), and `test_record_without_a_ref_never_journals` plus `test_insert_action_decisions_never_journals`: outage stubbed on the driver path → raises, journal empty (O8, AC 5).
8. `test_record_decisions_journal_failure_raises_audit_unavailable`.
9. Pipeline: `test_step8_row_journaled_releases_with_null_id_and_ref`: `QuerySuccessResponse.audit_id is None`, `audit_ref == entry.write_id`.
10. Pipeline with tools: `test_step8_row_journaled_carries_its_decisions_in_the_same_entry`. One entry holds the audit row and N decisions keyed `<W>:<i>`, and `insert_action_decisions` is never called.
11. Pipeline with tools: `test_step8_decisions_journaled_alone_after_the_row_committed`.
12. Pipeline with tools: `test_step8_decisions_journal_failure_is_todays_d8_path`: `mark_audit_log_failed(41, ...)` is called, `ActionAuditError.__cause__` is an `AuditUnavailableError`, and nothing is released.
13. Pipeline with tools: `test_step8_row_unrecordable_on_a_tools_response_is_action_audit_error` (R2): no mark.
14. Pipeline: `test_refusal_row_journaled_keeps_the_refusal_shape` (`_deny` forbidden, a pattern block): the response is unchanged and the entry is in the journal. `test_refusal_row_unrecordable_raises` (R1).
15. `/query` (TestClient, upstream stubbed): journaled success → 200, `audit_id: null`, `audit_ref`. `AuditUnavailableError` → 503 `{"detail": "Storage unavailable"}`, `Retry-After: 7`, and no `response` in the body.
16. `/v1` JSON: journaled → 200, `harness.audit_id is None`, `harness.audit_ref == W`, `X-Harness-Audit-Ref == W`, no `X-Harness-Audit-Id`, `id == "chatcmpl-harness-ref-" + W`. Healthy → `X-Harness-Audit-Id` only (R4).
17. `/v1` stream: journaled → every chunk id is `chatcmpl-harness-ref-<W>`, and `[DONE]` is present.
18. `/v1` `AuditUnavailableError` JSON → 503 `storage_unavailable`, `AUDIT_UNAVAILABLE_MESSAGE`, `Retry-After`. Stream after commit → one `storage_unavailable` error event, no `[DONE]`. Tools → 500 `internal_error` (`_AUDIT_FAILED` shape from `tests/test_v1_tools.py`). No canary anywhere.
19. `audit_unavailable_retry_after`: direct context, an `OSError` in between, no outage → `1`.
20. **`db`** (`faulty_db` + journal): a tools request through `run_conversation` with `Fault(STREAM_EXPIRED, sql="INSERT INTO AUDIT_LOGS", times=3)` (`tests/db_faults.py:56`). The journal holds one entry with the row and decisions, and the DB has no row. Then `journal_drainer.drain_once(journal)` → `DRAINED`. The audit row lands with `write_id == W`, and the decisions land with `audit_id == row.id` and keys `W:i`.

`tests/test_chat_ui_storage_failures.py` (extend, non-`db`):
21. `test_audit_unavailable_shows_the_fixed_bubble_not_driver_text`: the pipeline raises `AuditUnavailableError("audit journal is full ... <canary>")`. The bubble is `internal_error`, `detail == AUDIT_UNAVAILABLE_NOTICE`, the detail does not contain "nothing was sent", and `pending` is False.
22. `test_a_journaled_success_stores_a_null_audit_id`: the pipeline returns `QuerySuccessResponse(audit_id=None, audit_ref=W, ...)`. The persisted `StoredMessage.audit_id is None` (capture via `append_chat_message` / `_append_and_persist` stub, the file's existing pattern).

- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db_resilience_release.py tests/test_chat_ui_storage_failures.py -q`

---

## End-to-End Tests

- [ ] `/query` healthy (TestClient, `db`): 200, body = the old body plus `audit_ref` (32 hex, equals the row's `write_id`).
- [ ] `/query` with `insert_audit_log` raising `StorageUnavailableError` and a journal open: 200, `audit_id: null`, `audit_ref` = journal entry `write_id`.
- [ ] `/v1` journaled: `X-Harness-Audit-Ref`, `chatcmpl-harness-ref-<W>`, stream ends with `[DONE]`.
- [ ] `AuditUnavailableError` on each ingress: `/query` 503 + `Retry-After`; `/v1` 503 `storage_unavailable` (tools → 500 `internal_error`); chat UI `internal_error` bubble with fixed copy.
- [ ] Drain round trip (Task 12 #20): the journaled row and decisions land keyed, `audit_id` linked.

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
# chat_ui touched -> the startup-guard probe:
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_chat_ui_startup_guard.py -q
# One pytest call (never two at once); Full suite: GitHub CI on push (user decision)
PYTHONUTF8=1 .venv/Scripts/python -m pytest \
  tests/test_db_resilience_release.py tests/test_chat_ui_storage_failures.py \
  tests/test_audit_logger.py tests/test_action_audit.py tests/test_db_resilience_write_id.py \
  tests/test_query_pipeline_tools.py tests/test_query_pipeline_audit_fields.py \
  tests/test_query_pipeline_pii_profiles.py tests/test_query_router.py tests/test_schemas.py \
  tests/test_v1_router.py tests/test_v1_sse.py tests/test_v1_tools.py tests/test_v1_schemas.py \
  tests/test_v1_translate_result.py tests/test_db_resilience_ingress.py tests/test_db_resilience_drain.py \
  tests/test_audit_journal.py tests/test_chat_state.py tests/test_chat_history_send.py \
  tests/test_chat_outcomes_regression.py tests/test_rbac.py tests/test_usage_bubble.py \
  tests/test_query_outcomes_regression.py tests/test_query_pipeline_patterns.py \
  tests/test_query_pipeline_usage_limits.py tests/test_actions_view.py tests/test_admin_actions.py \
  tests/test_pii_redaction_integration.py tests/test_untouched_app.py tests/test_chat_ui_startup_guard.py -q
```
`tests/test_db.py` is not needed: no `database.py` change. If the run passes ~10 minutes, drop `test_chat_state.py` to a `-k "success or send"` subset and say so in the report.

---

## Acceptance Criteria

(Copied from story `STORY-010`)

- [ ] AC 1: `log_query` → `AuditRef(audit_id=int, write_id)` on success. Exhausted retries or an open breaker → journaled, `AuditRef(None, write_id)`. Journal append failure → `AuditUnavailableError`. Every call site in `query_pipeline.py` and `routers/query.py` is updated, and refusal rows journal the same way. (Tasks 1, 3, 7; tests 1-4, 14)
- [ ] AC 2: step 8 with tools: both committed → today. Row committed + decisions exhausted → decisions journaled alone (`audit_id` known). Row journaled → decisions in the same entry. Release only after commit or fsync. Journal failure → PRD-017 D8 path unchanged. (Tasks 2, 3; tests 5-13, 20)
- [ ] AC 3: a journaled success has `audit_id: null` + `audit_ref` on `/query`; `harness.audit_id: null`, `harness.audit_ref`, `X-Harness-Audit-Ref`, `chatcmpl-harness-ref-<W>` on `/v1`; `audit_ref` on every success; NULL `audit_id` on the chat transcript row. (Tasks 4, 5, 8, 9; tests 9, 15-17, 22)
- [ ] AC 4: `AuditUnavailableError` → `/query` 503 with nothing released; `/v1` 503 `storage_unavailable` (tools 500 `internal_error`); chat UI `internal_error` bubble. (Tasks 6-9; tests 15, 18, 19, 21)
- [ ] AC 5: healthy bodies byte-identical except `audit_ref`, each modified assertion citing PRD-018 D14; `insert_action_decisions` called directly never journals. (Task 11; test 7)
- [ ] All tasks completed
- [ ] `from app.main import app` imports; chat UI startup-guard probe passes
- [ ] Follows existing patterns

---

## Risks

- **Mass `QuerySuccessResponse(...)` / `HarnessCompletionInfo(...)` edits (~30 sites).** Making `audit_ref` required breaks every hand-built stub. That is deliberate: "present on every success" is enforced by validation, and the cost is mechanical. Mitigation: the Task 11 list, and pydantic's `ValidationError` names any missed site.
- **OpenAPI change.** `QuerySuccessResponse.audit_id` becomes `anyOf: [integer, null]`. Clients generated from the schema see a nullable field. That is PRD Risk 5, accepted under O2.
- **Chat footer shows "audit #0" for a journaled success.** `bubbles.py:219` renders `message.audit_id`. Cosmetic, outage-only, and not in this story's ACs. Flagged for STORY-012/013 or the orchestrator.
- **The `internal_error` bubble headline reads "The harness failed before reaching the model."** (`copy.py:127`), even when step 8's journal failed after the model answered. This story changes only the detail, per the orchestrator note. The headline belongs to the shared renderer, so it is flagged rather than changed.
- **`journal_decisions` as a callable couples `log_query` to step 8.** Mitigation: it defaults to None, is documented as step-8-only, and a pipeline test pins the same-entry property (R3 alternative noted above).
- **No journal open in most tests (`current() is None`).** Any existing test whose success-row write raises a driver-classified failure now sees `AuditUnavailableError` instead of `StorageUnavailableError`. None found: `test_v1_sse.py:629-640` raises `RuntimeError`, and `test_query_outcomes_regression.py:195-215` fails the duplicate lookup with a STATEMENT error. The targeted run confirms it.
