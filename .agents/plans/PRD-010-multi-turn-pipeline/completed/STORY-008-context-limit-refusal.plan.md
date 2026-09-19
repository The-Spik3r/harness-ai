---
story: STORY-008
prd: PRD-010
slug: context-limit-refusal
title: "Context-limit refusal: response model, audited pipeline arm, /query passthrough"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-010-multi-turn-pipeline
created: 2026-09-18
---

# Plan: Context-limit refusal: response model, audited pipeline arm, /query passthrough

## Summary

Add the fifth member of the `/query` response union — `QueryBlockedContextLimitResponse` — and the pipeline arm that returns it. `run_conversation` gains a check between the three authorization arms and `check_duplicate`, at the `# context limit (STORY-008)` marker STORY-007 left behind: messages first, then characters, each read from `settings` per call so a test can monkeypatch them, each refusing only when strictly over the maximum. The refusal writes exactly one audit row with `success=False`, the reason in `error_message`, the last user turn as `prompt`, and the `dedup_key` and `session_id` every other arm already passes. `/query` needs no router change — the union member is the passthrough — so the work is one model, one helper, one arm, and the tests that pin the order, the boundary, the row and outcome 7.

## User Story

As a compliance admin
I want a conversation over the configured limits refused with the limit named and the attempt audited
So that nothing is silently truncated and oversized requests leave the same evidence as any other refusal.

## Story Reference

- Story file: `.agents/stories/PRD-010-multi-turn-pipeline/STORY-008-context-limit-refusal.md`
- PRD: `.agents/PRDs/PRD-010-multi-turn-pipeline/PRD.md` — sections 4, 6.1, 6.5 (D2), 7 (F6), 9.2 (T7), 10, 11 (outcome 7)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/models/schemas.py`, `app/services/query_pipeline.py`, tests (pipeline, schemas, regression, chat state) |
| Story | STORY-008 |
| PRD | PRD-010 |
| Epic Branch | `epic/PRD-010-multi-turn-pipeline` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` holds only `frontend-design`, whose description covers visual design of new or reshaped UI. This story is backend (schema, pipeline arm, audit row) plus one interim assertion on an existing chat bubble; it designs no UI. Story frontmatter `skills: []` agrees. | none |

---

## Patterns to Follow

### Naming — blocked response models are `QueryBlocked{Reason}Response`, `status` pinned by `Literal`

```python
# SOURCE: app/models/schemas.py:96-111
class QueryBlockedForbiddenResponse(BaseModel):
    status: Literal["BLOCKED"] = "BLOCKED"
    reason: str
    required_permission: str


QueryResponse = Union[
    QuerySuccessResponse,
    QueryBlockedDuplicateResponse,
    QueryBlockedSuspiciousResponse,
    QueryBlockedForbiddenResponse,
]
```

### Error handling — a refusal arm logs one row, then returns the model

```python
# SOURCE: app/services/query_pipeline.py:158-172
    if duplicate_result.is_duplicate:
        log_query(
            user_id=identity.user_id,
            prompt=prompt,
            device=device,
            was_duplicate_blocked=True,
            success=True,
            session_id=session_id,
            dedup_key=key,
        )
        return QueryBlockedDuplicateResponse(
            reason="Duplicate query within 24 hours",
            first_query_at=duplicate_result.first_query_at,
        )
```

The difference this story must get right: duplicate / suspicious / forbidden rows are `success=True` (a verdict was reached and the row names it). A context-limit row is `success=False` with the reason in `error_message`, like the foreign-session refusal in `app/routers/query.py:106-116` and the upstream-error arm at `app/services/query_pipeline.py:246-256`. PRD 9.2 T7 accepts the `success_rate` cost.

### Settings read per call, never captured at import

```python
# SOURCE: app/services/openrouter_client.py:123
    http_client = client or httpx.Client(timeout=settings.OPENROUTER_TIMEOUT_SECONDS)
```

```python
# SOURCE: tests/test_chat_sessions.py:1373
    monkeypatch.setattr(settings, "CHAT_SESSION_LIMIT", 2)
```

### Tests — audit rows read back through `get_audit_log`, counted with a helper

```python
# SOURCE: tests/test_query_pipeline_run_conversation.py:37-52
def _count_audit_rows() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]


def _last_audit_entry():
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
    return get_audit_log(row["id"])


def _fail_if_called(*args, **kwargs):
    raise AssertionError("this collaborator should not have been called")
```

### Tests — a `/query` outcome row asserts status, exact body and row delta

```python
# SOURCE: tests/test_query_outcomes_regression.py:108-119
    before = _count_audit_rows()
    response = client.post("/query", json={"prompt": prompt})

    assert response.status_code == 200
    assert response.json() == {
        "status": "BLOCKED",
        "reason": "Duplicate query within 24 hours",
        "first_query_at": success_at,
    }
    assert _count_audit_rows() == before + 1
```

### Tests — a ChatState bubble test stubs `run_query` on the state module

```python
# SOURCE: tests/test_chat_state.py:288-302
    def _fake_run_query(identity, prompt, device, model, openrouter_api_key, call_openrouter, session_id=None):
        return QueryBlockedForbiddenResponse(...)

    monkeypatch.setattr(chat_state_mod, "run_query", _fake_run_query)

    state = _make_state()
    await _send(state, "hello world")

    assert state.messages[-1].kind == "forbidden"
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/models/schemas.py` | UPDATE | Add `QueryBlockedContextLimitResponse`; add it to `QueryResponse` |
| `app/services/query_pipeline.py` | UPDATE | Add it to `QueryPipelineResult`; `_context_limit_exceeded` helper; the arm at the STORY-007 marker |
| `tests/test_schemas.py` | UPDATE | Model shape + union-membership tests (AC1) |
| `tests/test_query_pipeline_context_limit.py` | CREATE | Both limits, boundary, precedence, audit row, check order (AC2–AC4) |
| `tests/test_query_outcomes_regression.py` | UPDATE | `test_outcome_7_context_limit` (AC5); rows 1–6 untouched |
| `tests/test_chat_state.py` | UPDATE | Interim `internal_error` bubble pin, marked `# replaced by STORY-013` |

Deliberately **not** in scope: `app/routers/query.py` (the union member *is* the passthrough — the route already declares `response_model=QueryResponse` and returns the pipeline result unchanged), the real chat bubble (STORY-013), README / `.env.example` (STORY-018), and the multi-turn invariant suite (STORY-009).

---

## Dependency Order

Task 1 (model) → Task 3 (pipeline arm) are the only production edits, and the arm imports the model. Tests follow their subject: 2 after 1; 4, 5, 6 after 3. Task 7 is the whole suite.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add the response model and widen `QueryResponse`

- **File**: `app/models/schemas.py`
- **Action**: UPDATE
- **Implement**: After `QueryBlockedForbiddenResponse`, add:

  ```python
  class QueryBlockedContextLimitResponse(BaseModel):
      status: Literal["BLOCKED"] = "BLOCKED"
      reason: str
      limit: Literal["messages", "characters"]
      maximum: int
      actual: int
  ```

  Add it as the fifth member of `QueryResponse`. Field names and order come from PRD Section 6.5 verbatim — the JSON body in Section 10 is the contract. Add a short comment saying what `limit` names (which of the two configured maxima was hit) and that only one is ever reported, messages first.
- **Mirror**: `app/models/schemas.py:96-111` — same `status: Literal["BLOCKED"] = "BLOCKED"` head, same `Union` block style.
- **Validate**: `python -c "from app.models.schemas import QueryBlockedContextLimitResponse as R; print(R(reason='x', limit='messages', maximum=3, actual=4).model_dump())"`

### Task 2: Pin the model's shape and its union membership

- **File**: `tests/test_schemas.py`
- **Action**: UPDATE
- **Implement**: Three tests.
  1. `test_query_blocked_context_limit_response_shape` — construct with `reason="Conversation exceeds context limit", limit="characters", maximum=200000, actual=250113` and assert the exact `model_dump()` dict, `status: "BLOCKED"` included.
  2. `QueryBlockedContextLimitResponse in get_args(QueryResponse)` (AC1's "is a member of `QueryResponse`").
  3. `limit="tokens"` raises `ValidationError` — the `Literal` is the contract, not a hint.
- **Mirror**: `tests/test_schemas.py:75-85`
- **Validate**: `python -m pytest tests/test_schemas.py -q`

### Task 3: Add the pipeline check and the audited arm

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**:
  1. `from app.config import settings` (the module has no settings import today), import `QueryBlockedContextLimitResponse`, and add it to the `QueryPipelineResult` union.
  2. A module-level helper beside `_inspection_target`:

     ```python
     def _context_limit_exceeded(
         messages: Sequence[Message],
     ) -> Optional[tuple[Literal["messages", "characters"], int, int]]:
         """The limit this conversation breaks, or None. Messages first (D2)."""
         message_count = len(messages)
         if message_count > settings.CONTEXT_MAX_MESSAGES:
             return "messages", settings.CONTEXT_MAX_MESSAGES, message_count
         character_count = sum(len(m.content) for m in messages)
         if character_count > settings.CONTEXT_MAX_CHARACTERS:
             return "characters", settings.CONTEXT_MAX_CHARACTERS, character_count
         return None
     ```

     Both limits are read off `settings` **inside** the function, per call, so `monkeypatch.setattr(settings, ...)` works (story Technical Notes). Strict `>`: exactly at the maximum passes (AC3 boundary). `Literal` needs importing from `typing`.
  3. Replace the `# context limit (STORY-008)` marker (`app/services/query_pipeline.py:150`) with the arm, numbered `# Step 3:` to match its neighbours:

     ```python
     exceeded = _context_limit_exceeded(messages)
     if exceeded is not None:
         limit, maximum, actual = exceeded
         log_query(
             user_id=identity.user_id,
             prompt=prompt,
             device=device,
             success=False,
             error_message=f"context limit: {limit} {actual} > {maximum}",
             session_id=session_id,
             dedup_key=key,
         )
         return QueryBlockedContextLimitResponse(
             reason="Conversation exceeds context limit",
             limit=limit,
             maximum=maximum,
             actual=actual,
         )
     ```

     Comment the two decisions that read as mistakes otherwise: **position** (after all three authorization arms, so a caller without `query:submit` learns nothing about limits; before `check_duplicate`, so an over-limit conversation neither consults nor counts toward the window — PRD 6.1), and **`success=False`** (no verdict was reached, so the row must never serve as a prior query — PRD 6.5 — and it is why `success_rate` counts it as a failure, PRD 9.2 T7). Pass `session_id=` and `dedup_key=` explicitly, like every other arm.
- **Mirror**: `app/services/query_pipeline.py:152-172` (log then return) and `app/services/query_pipeline.py:246-256` (`success=False` + `error_message` shape)
- **Validate**: `python -m pytest tests/test_query_pipeline_run_conversation.py tests/test_query_pipeline_authorization.py tests/test_query_pipeline_session_passthrough.py tests/test_query_pipeline_dedup_key.py -q`

### Task 4: Pipeline tests — both limits, boundary, precedence, row, order

- **File**: `tests/test_query_pipeline_context_limit.py`
- **Action**: CREATE
- **Implement**: Module docstring naming STORY-008 and its scope (order spies beyond these two are STORY-009's). Reuse the `_count_audit_rows` / `_last_audit_entry` / `_fail_if_called` helpers and the `_JUAN` / `_DENIED` identities from `tests/test_query_pipeline_run_conversation.py`. Tests:
  - **AC2 messages**: `CONTEXT_MAX_MESSAGES=3`, a 4-message conversation (user / assistant / user / user — the last turn must be `user`, `_validate_conversation` requires it) → `QueryBlockedContextLimitResponse(limit="messages", maximum=3, actual=4, reason="Conversation exceeds context limit")`, with `call_openrouter=_fail_if_called`.
  - **AC2 precedence**: over both limits (`CONTEXT_MAX_MESSAGES=3`, `CONTEXT_MAX_CHARACTERS=1`) → `limit == "messages"`.
  - **AC3 characters**: `CONTEXT_MAX_CHARACTERS=10`, contents totalling 12 → `limit="characters", maximum=10, actual=12`.
  - **AC3 boundary**: exactly 10 characters is **not** refused — with a stub upstream it returns `QuerySuccessResponse`. Assert both the result type and that the stub was called, so an off-by-one cannot pass by refusing for some other reason.
  - **AC4 row**: exactly one new row (`before + 1`), `success is False`, `error_message == "context limit: characters 12 > 10"` (and the `messages` equivalent in the messages test), `prompt_hash == hash_prompt(<last user turn content>)` — the row stores a hash and a preview, not the raw prompt, so mirror how `tests/test_query_pipeline_run_conversation.py` asserts the audited prompt — `dedup_key` non-NULL and equal to `dedup_key(identity.user_id, messages)`, and `session_id` equal to the value passed in.
  - **AC4 order, from below**: `monkeypatch.setattr(query_pipeline, "check_duplicate", _fail_if_called)`; an over-limit conversation still returns the context-limit response — `check_duplicate` is never called on refusal.
  - **AC4 order, from above**: `_DENIED` (lacks `query:submit`) with an over-limit conversation returns `QueryBlockedForbiddenResponse`, not the context-limit one.
  - **Per-call settings read**: with the limit patched small the call refuses; restored, the same conversation passes to a stub upstream — proving nothing captured the value at import.
- **Mirror**: `tests/test_query_pipeline_run_conversation.py:1-55` (docstring, helpers, identities) and `:154-158` (spy via `monkeypatch.setattr(query_pipeline, ...)`)
- **Validate**: `python -m pytest tests/test_query_pipeline_context_limit.py -q`

### Task 5: `/query` regression outcome 7

- **File**: `tests/test_query_outcomes_regression.py`
- **Action**: UPDATE
- **Implement**: Append `test_outcome_7_context_limit` after the outcome-6 tests. Monkeypatch `settings.CONTEXT_MAX_CHARACTERS` small (e.g. `50`), post a prompt of `CONTEXT_MAX_CHARACTERS + 1` characters with `app.routers.query.call_openrouter` stubbed to `_fail_if_called`, and assert: status 200; `response.json() == {"status": "BLOCKED", "reason": "Conversation exceeds context limit", "limit": "characters", "maximum": 50, "actual": 51}`; `_count_audit_rows() == before + 1`; `_latest_entry().success is False`. The exact-dict assertion is what proves FastAPI's `response_model=QueryResponse` union serializes the new member without dropping `limit` / `maximum` / `actual` (see Risks). Rows 1–6 stay byte-identical — the module docstring's "no later story may edit an outcome assertion" holds here too.
- **Mirror**: `tests/test_query_outcomes_regression.py:97-119`
- **Validate**: `python -m pytest tests/test_query_outcomes_regression.py -q` then `git diff -U0 tests/test_query_outcomes_regression.py` (additions only)

### Task 6: Pin the interim ChatState behaviour

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE
- **Implement**: `test_chat_state_send_context_limit_lands_on_interim_internal_error_bubble` — stub `chat_state_mod.run_query` to return a `QueryBlockedContextLimitResponse`, send, and assert `state.messages[-1].kind == "internal_error"` and `detail == "Unhandled response type: QueryBlockedContextLimitResponse"`. Docstring plus an inline `# replaced by STORY-013` comment saying this pins the *gap*, not the wanted behaviour: `chat_ui/chat_ui/state.py:1122-1129`'s catch-all `else` is where the fifth union member lands until STORY-013 adds the real bubble. No production change to `state.py` in this commit.
- **Mirror**: `tests/test_chat_state.py:282-302`
- **Validate**: `python -m pytest tests/test_chat_state.py -q`

### Task 7: Full suite

- **File**: —
- **Action**: VERIFY
- **Implement**: Run the whole suite. Per the libSQL dev-server note, mass fixture errors mean restarting the libSQL container, not bisecting this change.
- **Validate**: `python -m pytest -q`

---

## End-to-End Tests

- [ ] `POST /query` with `CONTEXT_MAX_CHARACTERS` monkeypatched small and an over-limit prompt → 200 with `{"status": "BLOCKED", "reason": "Conversation exceeds context limit", "limit": "characters", "maximum": N, "actual": N+1}`
- [ ] The same attempt leaves exactly one `audit_logs` row: `success=0`, `error_message="context limit: characters N+1 > N"`, non-NULL `dedup_key`, `session_id` as sent
- [ ] `GET /audit` still renders that row — it is an ordinary `success=false` row, no reader change
- [ ] A normal `/query` prompt under the default limits is unaffected: outcomes 1–6 green, upstream payload unchanged
- [ ] `run_conversation` with a forbidden identity and an over-limit conversation → `forbidden`, one row, `check_duplicate` never called
- [ ] Chat send whose pipeline result is the new member → interim `internal_error` bubble (pinned, replaced by STORY-013)

---

## Validation

```bash
python -m pytest tests/test_schemas.py tests/test_query_pipeline_context_limit.py tests/test_query_outcomes_regression.py tests/test_chat_state.py -q
python -m pytest -q
python -c "import app.main"
```

---

## Risks + Mitigations

| Risk | Mitigation |
|---|---|
| FastAPI serializes `response_model=QueryResponse` through a plain (non-discriminated) `Union`, and all four blocked members share `status: "BLOCKED"` — a wrong member match would silently drop `limit` / `maximum` / `actual`. | Pydantic v2 smart-union matches on required fields, which are disjoint here. Proven rather than assumed by Task 5's exact-dict assertion on the HTTP body. If it ever mismatches, the fix is a discriminated union, not reordering members. |
| `success=False` makes context-limit rows count against `success_rate` in `/stats`. | Intended and accepted: PRD 9.2 T7. No `/stats` change, no new `audit_logs` column. |
| Reading `settings` at import would freeze the limits per process and make them unpatchable. | Both reads live inside `_context_limit_exceeded`; Task 4 has a test that proves the per-call read. |
| Character counting is O(total characters) per send. | A `sum(len(...))` over strings already in memory, far below the redaction pass that follows. No caching. |
| The arm could drift ahead of `check_duplicate` or behind authorization in a later edit. | Two spy tests (Task 4) fix its position from both sides; STORY-009 adds the full order assertion. |
| The chat UI shows a misleading `internal_error` for an over-limit send until STORY-013. | Accepted by the story's Technical Notes, and made visible by Task 6's pinned test carrying `# replaced by STORY-013`. |

---

## Acceptance Criteria

(Copied from story `STORY-008`)

- [ ] `QueryBlockedContextLimitResponse(status: Literal["BLOCKED"] = "BLOCKED", reason: str, limit: Literal["messages", "characters"], maximum: int, actual: int)` exists in `app/models/schemas.py`, is a member of `QueryResponse`, and `QueryPipelineResult` includes it
- [ ] `CONTEXT_MAX_MESSAGES=3` + a 4-message conversation → `limit="messages", maximum=3, actual=4, reason="Conversation exceeds context limit"`; a conversation over both limits reports `messages`
- [ ] `CONTEXT_MAX_CHARACTERS=10` + contents totalling 12 → `limit="characters", maximum=10, actual=12`; exactly 10 characters is not refused
- [ ] One audit row with `success=0`, `error_message="context limit: characters 12 > 10"` (or the `messages` equivalent), the last user turn as `prompt`, a non-NULL `dedup_key` and the passed `session_id`; the check runs after all three authorization checks and before `check_duplicate` (spies: a forbidden identity gets `forbidden`; `check_duplicate` never called on refusal)
- [ ] `POST /query` with a prompt of `CONTEXT_MAX_CHARACTERS + 1` characters → 200 with the context-limit body, pinned by `test_outcome_7_context_limit`; rows 1–6 unmodified
- [ ] Interim `ChatState` behaviour pinned with a `# replaced by STORY-013` comment
- [ ] All tasks completed
- [ ] Full suite green
- [ ] Follows existing patterns
