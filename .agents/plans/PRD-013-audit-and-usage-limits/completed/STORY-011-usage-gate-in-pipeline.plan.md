---
story: STORY-011
prd: PRD-013
slug: usage-gate-in-pipeline
title: "Usage gate in the pipeline: response, audited arm and duplicate-lookup exclusion"
type: NEW_CAPABILITY
complexity: HIGH
epic_branch: epic/PRD-013-audit-and-usage-limits   # all stories commit here, no per-story branch
created: 2026-10-19
---

# Plan: Usage gate in the pipeline: response, audited arm and duplicate-lookup exclusion

## Summary

Wire STORY-010's `usage_limits.admit` into `run_conversation` as **step 2c**: after the three authorization arms, before `_context_limit_exceeded`. The step is skipped entirely when `settings.USAGE_LIMITS_ENABLED` is false (read per call). With it on, `admit(identity, charges_budget=openrouter_api_key is None)` is called once and its `Admission` kept in a local (`admission`), because STORY-012 charges against `admission.day`. A refusal writes one audit row (`success=True`, `role`, `limit_exceeded=<"requests"|"tokens">`, the non-NULL `dedup_key`, no `error_message`) and returns a new `QueryBlockedUsageLimitResponse`. A `UsageLimitError` from `admit` propagates with no row and no upstream call. `POST /query` maps it to `500` beside `DuplicateCheckError`, and the chat UI routes it through the internal-error bubble.

Three supporting edits:
- `find_duplicate_timestamp` gains `AND limit_exceeded IS NULL`, so a refusal is never a prior query. NULL passes, so rows written before this PRD behave as before.
- `QueryBlockedUsageLimitResponse` joins both `QueryResponse` and `QueryPipelineResult`.
- `ChatState._do_send` gets an interim explicit arm that renders the new result as an `internal_error` bubble. STORY-014 replaces that arm with the real bubble.

## User Story

As a platform operator
I want an authorized request over its rate or budget refused before any content check and recorded like any other block
So that a looping agent is bounded and the refusal is evidence

## Story Reference

- Story file: `.agents/stories/PRD-013-audit-and-usage-limits/STORY-011-usage-gate-in-pipeline.md`
- PRD: `.agents/PRDs/PRD-013-audit-and-usage-limits/PRD.md` (sections 6.1 / D7, 6.5 / D8, 6.7 / D5 D6, 7 F10, 9.2 T2 T7 T11, 10, 11 "Limits" and "Eight outcomes", Risk 5)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | HIGH (story: large) |
| Systems Affected | `app/services/query_pipeline.py`, `app/models/schemas.py`, `app/db/database.py`, `app/routers/query.py`, `chat_ui/chat_ui/state.py`, tests |
| Story | STORY-011 |
| PRD | PRD-013 |
| Epic Branch | `epic/PRD-013-audit-and-usage-limits` (commit directly on this branch) |
| Depends on | STORY-002 ✅ (`3c61b53`), STORY-005 ✅ (`1ab83f2`), STORY-010 ✅ (`3570281`) |
| Blocks | STORY-012, STORY-014, STORY-015, STORY-016 |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | The only skill is `frontend-design`. This story makes no visual change: the chat routes the new result through the **existing** `internal_error` bubble, and the real bubble is STORY-014. | — |

---

## What already exists (inputs to this story)

| Primitive | Location | Contract |
|---|---|---|
| `admit(identity, charges_budget) -> Admission` | `app/services/usage_limits.py:139-188` | Positional-or-keyword `charges_budget`. Counts the attempt (one statement), then the rate is checked first and the budget second. Raises `UsageLimitError` on `StorageError` (fail closed). |
| `Admission` / `UsageRefusal` | `app/services/usage_limits.py:52-82` | `admission.admitted`, `admission.day`, `admission.refusal.{limit, maximum, actual, resets_at}`. The refusal fields map one-to-one onto the response. |
| `UsageLimitError` | `app/services/usage_limits.py:42-43` | Bare `Exception` subclass, like `DuplicateCheckError`. |
| `settings.USAGE_LIMITS_ENABLED` | `app/config.py:322` | `bool`, default `True`. The module docstring (`usage_limits.py:8-11`) says the pipeline reads it, not the service. A test (`tests/test_usage_limits.py:395`) pins that the service never reads it. |
| `log_query(..., limit_exceeded=...)` | `app/services/audit_logger.py:61, 94` | Already accepted and written (STORY-002 and STORY-005). No caller sets it yet. |
| `audit_logs.limit_exceeded` | STORY-002 | Nullable `TEXT`. |
| `_deny(...)` | `app/services/query_pipeline.py:163-213` | Shows the full keyword set every arm must pass (`session_id`, `dedup_key`, `profile`, `ingress`, `message_count`, `conversation_key`, `streamed`). |

---

## Patterns to Follow

### A verdict arm: one `log_query`, `success=True`, a dedicated column names the verdict
```python
# SOURCE: app/services/query_pipeline.py:348-366 (duplicate arm)
    if duplicate_result.is_duplicate:
        log_query(
            user_id=identity.user_id,
            prompt=prompt,
            device=device,
            was_duplicate_blocked=True,
            success=True,
            session_id=session_id,
            dedup_key=key,
            profile=profile_name,
            ingress=ingress,
            message_count=message_count,
            conversation_key=conv_key,
            streamed=streamed,
        )
        return QueryBlockedDuplicateResponse(...)
```
`role=identity.role` comes from `_deny` (`query_pipeline.py:203`). The usage-limit row carries it too (AC 1).

### Settings read per call
```python
# SOURCE: app/services/query_pipeline.py:78-82 (_context_limit_exceeded docstring)
    Both maxima are read off `settings` **here, per call** rather than captured
    at import. ... every test in this suite sets them with
    `monkeypatch.setattr(settings, ...)`, which a module-level constant would
    silently ignore
```

### Named storage exception mapped to 500 in the router
```python
# SOURCE: app/routers/query.py:26-35
    try:
        return await run_in_pipeline(_handle_query, request, identity)
    except ChatSessionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except DuplicateCheckError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
```

### Duplicate-lookup exclusion comment style
```python
# SOURCE: app/db/database.py:855-861, 869
        # A pattern *flag* row (PRD-011 D6) is excluded too: it is not a
        # verdict, because the request it records went on to redaction and
        # upstream. ... NULL passes -- every row written before PRD-011 -- and a
        # block row passes, as a content verdict (PRD-009 F4).
        ...
              AND (pattern_action IS NULL OR pattern_action <> 'flag')
```

### Blocked response model
```python
# SOURCE: app/models/schemas.py:102-131 (QueryBlockedContextLimitResponse)
class QueryBlockedContextLimitResponse(BaseModel):
    """...docstring explaining why each field exists..."""
    status: Literal["BLOCKED"] = "BLOCKED"
    reason: str
    limit: Literal["messages", "characters", "redaction_characters"]
    maximum: int
    actual: int
```

### Spy-order test
```python
# SOURCE: tests/test_query_pipeline_multiturn.py:139-182, 185-212
    real_check_duplicate = query_pipeline.check_duplicate
    def _spy_check_duplicate(user_id, key):
        trace.append("duplicate")
        return real_check_duplicate(user_id, key)
    monkeypatch.setattr(query_pipeline, "check_duplicate", _spy_check_duplicate)
    ...
    assert trace == ["authorize", "authorize"] + ["context_limit", "duplicate", "pattern"] + ...
```
The spies patch **`query_pipeline`'s own bindings**. So the gate must call `admit` through a name imported into `query_pipeline` (`from app.services.usage_limits import UsageLimitError, admit`), not `usage_limits.admit`. Otherwise `monkeypatch.setattr(query_pipeline, "admit", ...)` would not reach it. This is the same binding rule `_redact` documents at `query_pipeline.py:146-153`.

### Deterministic counter stub (never races a minute boundary)
```python
# SOURCE: tests/test_usage_limits.py:54-77
def _usage(window_requests=1, tokens_today=0, day=_DAY, window_start=_WINDOW_START):
    return UsageAdmission(day=day, window_start=window_start,
                          window_requests=window_requests, tokens_today=tokens_today)

@pytest.fixture
def counter(monkeypatch):
    counts: dict[str, int] = {}
    def fake_admit_usage(user_id):
        counts[user_id] = counts.get(user_id, 0) + 1
        return _usage(window_requests=counts[user_id])
    monkeypatch.setattr(usage_limits, "admit_usage", fake_admit_usage)
    return counts
```

### Interim chat routing precedent
```python
# SOURCE: tests/test_chat_state.py:307-316 and chat_ui/chat_ui/state.py:1267-1279
# PRD-010 STORY-008 added a fifth union member and let it fall to the catch-all
# `internal_error` bubble until STORY-013 added the real one.
```

### Exact-dict `/query` outcome assertion
```python
# SOURCE: tests/test_query_outcomes_regression.py:204-241 (outcome 7)
    assert response.status_code == 200
    assert response.json() == {"status": "BLOCKED", "reason": ..., "limit": ..., "maximum": 50, "actual": 51}
    assert _count_audit_rows() == before + 1
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/models/schemas.py` | UPDATE | Add `QueryBlockedUsageLimitResponse`; add it to `QueryResponse` |
| `app/services/query_pipeline.py` | UPDATE | Import `admit`, `UsageLimitError`; add the response to `QueryPipelineResult`; step 2c with the audited arm; fix the one mis-indented `_deny` line (294) while here |
| `app/db/database.py` | UPDATE | `find_duplicate_timestamp`: `AND limit_exceeded IS NULL` plus a comment |
| `app/routers/query.py` | UPDATE | `except UsageLimitError` → `500`, beside `DuplicateCheckError` |
| `chat_ui/chat_ui/state.py` | UPDATE | `UsageLimitError` joins the internal-error `except` tuple; an interim explicit arm for the new result; correct the catch-all's "five members" comment |
| `tests/test_query_pipeline_usage_limits.py` | CREATE | The gate, its row, order, fail-closed, switch-off, BYOK flag, duplicate exclusion |
| `tests/test_query_outcomes_regression.py` | UPDATE | Append outcome 8. Rows 1–7 untouched |
| `tests/test_schemas.py` | UPDATE | Model dump, union membership, `limit` literal |
| `tests/test_chat_state.py` | UPDATE | Interim pin: the result → `internal_error` bubble; `UsageLimitError` → `internal_error` bubble |
| `tests/test_db.py` | UPDATE | `_DEDUP_LOOKUP_SQL` gains the predicate (the drift test requires it). Add a parametrized test: a `limit_exceeded` row is not a prior query, and a NULL one still is |

---

## Tasks

Execute in order. Each task is atomic and verifiable. Test command (see memory `harness-ai-test-env`): `C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe -m pytest ...`, with Docker Desktop and the `harness-libsql-dev` container running.

### Task 1: `QueryBlockedUsageLimitResponse`

- **File**: `app/models/schemas.py`
- **Action**: UPDATE
- **Implement**: After `QueryBlockedContextLimitResponse` (line 131), add:
  ```python
  class QueryBlockedUsageLimitResponse(BaseModel):
      """docstring: PRD-013 Section 6.7 / D5 D6 -- 200 BLOCKED, never 429; one limit
      reported (rate first, the _context_limit_exceeded rule); `actual` is the
      window count for `requests` and tokens used today for `tokens`; `resets_at`
      is UTC in the audit timestamp format, derived from the database's clock."""
      status: Literal["BLOCKED"] = "BLOCKED"
      reason: str
      limit: Literal["requests", "tokens"]
      maximum: int
      actual: int
      resets_at: str
  ```
  Append it as the **last** member of `QueryResponse` (line 134-140). Order matters because the union is plain, not discriminated. Every blocked member has `status="BLOCKED"`. Pydantic's smart-mode union serializes by the actual instance type, which outcome 7 already relies on (its docstring, `tests/test_query_outcomes_regression.py:209-214`). Appending last keeps every existing member's position.
- **Mirror**: `app/models/schemas.py:102-131`
- **Validate**: `python -m pytest tests/test_schemas.py -q`

### Task 2: Step 2c in `run_conversation`

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**:
  1. Imports: add `QueryBlockedUsageLimitResponse` to the schemas import, and `from app.services.usage_limits import UsageLimitError, admit`. `UsageLimitError` is imported so that the module's docstring and comments can name what propagates. If the linter flags it as unused, drop it and name it only in the comment.
  2. `QueryPipelineResult` (lines 35-41): append `QueryBlockedUsageLimitResponse`.
  3. Fix line 294's indentation (`conversation_key=conv_key, ...` is one level short inside the BYOK `_deny` call). This is cosmetic and in a block this task sits right after.
  4. Between the BYOK arm (ends line 296) and the `# Step 3: context limits` comment (line 298), insert:
     ```python
     # Step 2c: the usage gate (PRD-013 Sections 6.1, 6.5-6.7; D7, D8, F10).
     #
     # Lettered, not renumbered: three PRDs and the comments below cite steps
     # 3-8 by number. STORY-013's break-glass arm (2b) goes between the BYOK
     # arm above and this block.
     #
     # The position is the decision (D7). After every authorization arm, so a
     # caller without `query:submit` learns nothing about limits and consumes
     # no one's window (T11) -- it has no usage_daily row at all. Before the
     # context limit, the duplicate check and patterns, so every authorized
     # attempt counts toward the rate, including the ones those steps refuse:
     # a looping agent's retries are mostly duplicates (T2), and a resend after
     # a forced failure is an attempt too (PRD-009 T3).
     #
     # The switch is read here, per call, for the reason _context_limit_exceeded
     # gives. Off means admit() is not called and no statement touches
     # usage_daily: the pipeline's round trips are exactly the pre-PRD-013 ones.
     #
     # BYOK spends the caller's own key, so it is rate-limited but not held to
     # the budget (D8). `admission` is kept in a local: STORY-012 charges the
     # `day` it was counted against, so a request straddling midnight is
     # charged to the day it was admitted.
     #
     # admit() fails closed (T7): a counter outage raises UsageLimitError,
     # which propagates with no row written and nothing sent upstream -- the
     # router maps it to 500 beside DuplicateCheckError, ChatState to the
     # internal-error bubble.
     #
     # A refusal is `success=True`, unlike step 3: a verdict was reached and
     # the row names it in a dedicated column, `limit_exceeded` (PRD-013
     # Section 6.2) -- the rule in step 3's comment. It carries the key like
     # every row, and find_duplicate_timestamp excludes it, so a prompt refused
     # today is not held as a duplicate when sent again after the reset (D6).
     admission = None
     if settings.USAGE_LIMITS_ENABLED:
         admission = admit(identity, charges_budget=openrouter_api_key is None)
         if not admission.admitted:
             refusal = admission.refusal
             log_query(
                 user_id=identity.user_id,
                 prompt=prompt,
                 device=device,
                 success=True,
                 role=identity.role,
                 limit_exceeded=refusal.limit,
                 session_id=session_id,
                 dedup_key=key,
                 profile=profile_name,
                 ingress=ingress,
                 message_count=message_count,
                 conversation_key=conv_key,
                 streamed=streamed,
             )
             return QueryBlockedUsageLimitResponse(
                 reason="Usage limit reached",
                 limit=refusal.limit,
                 maximum=refusal.maximum,
                 actual=refusal.actual,
                 resets_at=refusal.resets_at,
             )
     ```
     `admission` is assigned but not yet read. STORY-012 reads `admission.day`. If ruff/flake8 flags F841, keep the local and suppress the warning with `# noqa: F841  # STORY-012 charges admission.day` rather than dropping it, because the story requires the local.
  5. Pass `charges_budget` by keyword. It reads as a decision at the call site, and the signature allows it.
- **Mirror**: `app/services/query_pipeline.py:348-366` (verdict arm), `:298-315` (position comment)
- **Validate**: `python -m pytest tests/test_query_pipeline_audit_fields.py tests/test_query_pipeline_run_conversation.py tests/test_query_pipeline_multiturn.py -q`. `test_every_direct_log_query_call_passes_the_three_fields` (AST scan) must stay green, and it covers the new call.

### Task 3: Duplicate lookup excludes usage-limit rows

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: In `find_duplicate_timestamp` (line 840), add `AND limit_exceeded IS NULL` after the `pattern_action` predicate (line 869). Extend the comment block (lines 842-861) with a paragraph in the flag-exclusion style:
  > A usage-limit refusal (PRD-013 D6) is excluded too: it is `success = 1` because a verdict was reached, but the verdict is about the caller's spend, not the prompt. Counting it would hold a prompt refused for budget today as a duplicate when it is sent again tomorrow. NULL passes, so every row written before PRD-013 behaves as before (Risk 5).
- **Required companion edit, `tests/test_db.py:2509-2518`**: `_DEDUP_LOOKUP_SQL` spells the lookup out, and `test_find_duplicate_timestamp_sql_is_the_planned_shape` (`:2554`) fails if the function's SQL drifts from it. `test_dedup_lookup_shape_uses_the_dedup_index` (`:2522`) runs it through `EXPLAIN QUERY PLAN`. Add `"AND limit_exceeded IS NULL "` after the `pattern_action` line, with a comment in the PRD-011 STORY-009 style: `# PRD-013 STORY-011 (D6): a usage-limit refusal is not a prior query. A residual filter, like the four above -- the index assertion below still holds.` This is the one permitted edit to an existing assertion's input, and it follows the precedent PRD-011 set on this same constant. The index-plan assertion itself must not change.
- **Test home**: `tests/test_db.py`, directly after `test_duplicate_lookup_ignores_a_flag_row` (`:2720-2742`). Add `test_duplicate_lookup_ignores_a_usage_limit_row`, parametrized `[(None, True), ("requests", False), ("tokens", False)]`, seeding a `success=True, dedup_key="k"` row with that `limit_exceeded`. Same shape and docstring style. The `None` case pins "NULL passes" (Risk 5).
- **Mirror**: `app/db/database.py:855-870`, `tests/test_db.py:2720-2742`
- **Validate**: `python -m pytest tests/test_db.py -k "dedup or duplicate" tests/test_duplicate_scope.py tests/test_duplicate_characterization.py tests/test_dedup_key.py tests/test_reporting_invariance.py -q`. **No assertion in `test_duplicate_scope.py` may change** (AC 3, PRD Risk 5).

### Task 4: `/query` maps `UsageLimitError` to 500

- **File**: `app/routers/query.py`
- **Action**: UPDATE
- **Implement**: Import `UsageLimitError` from `app.services.usage_limits`. Add `except UsageLimitError as exc: raise HTTPException(status_code=500, detail=str(exc)) from exc` directly after the `DuplicateCheckError` arm (line 30-31). The refusal itself needs no router change: it is a `QueryResponse` member, so it passes through as `200`.
- **Mirror**: `app/routers/query.py:30-31`
- **Validate**: `python -m pytest tests/test_query_router.py -q`

### Task 5: `ChatState._do_send` handles both new exits

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**:
  1. Import `QueryBlockedUsageLimitResponse` (schemas import, lines 10-16) and `UsageLimitError` (`app.services.usage_limits`).
  2. Line 1164: `except (DuplicateCheckError, PiiRedactorError, UsageLimitError) as exc:` → the existing `internal_error` bubble. Today the bare `except Exception` below would already catch it, but the story asks for an explicit route. Naming it here makes the routing a decision a reader can see.
  3. Before the catch-all `else` (line 1267), add an **interim** arm:
     ```python
     elif isinstance(result, QueryBlockedUsageLimitResponse):
         # Interim (PRD-013 STORY-011): routed through the existing internal-error
         # bubble so a refused send is never silently dropped. STORY-014 replaces
         # this arm with the `usage_limit` bubble and its copy. `detail` keeps
         # the limit and the reset on the persisted row meanwhile.
         bubble = ChatMessage(
             kind="internal_error",
             content="internal_error",
             prompt=text,
             detail=f"{result.reason}: {result.limit}, resets at {result.resets_at}",
         )
     ```
     Use an explicit arm rather than leaving the result to the catch-all. The catch-all would say "Unhandled response type", which is not true once this story knowingly handles the type.
  4. Update the catch-all's comment (lines 1268-1273): the chain now covers all **six** members, and the sixth is routed to the interim bubble until STORY-014.
- **Mirror**: `chat_ui/chat_ui/state.py:1164-1175` and `:1237-1279`
- **Validate**: `python -m pytest tests/test_chat_state.py tests/test_chat_outcomes_regression.py -q`. `test_chat_outcomes_regression.py` must not change.

### Task 6: `tests/test_query_pipeline_usage_limits.py`

- **File**: `tests/test_query_pipeline_usage_limits.py`
- **Action**: CREATE
- **Implement**: Module header in the style of `tests/test_usage_limits.py:1-12` (`os.environ.setdefault` for `OPENROUTER_API_KEY` and `ADMIN_TOKEN`; docstring citing PRD-013 STORY-011, Sections 6.1/6.7, D6/D7/D8, T2/T7/T11).
  - **Determinism**: every refusal test stubs `usage_limits.admit_usage` with a fixed `window_start` (`_usage()` / `counter` helpers copied from `tests/test_usage_limits.py:54-77`). No test depends on a real minute boundary. Rate-counting tests that need real storage read `usage_daily.requests` (the day total), never `window_requests`, so a minute rolling over mid-test cannot flake them.
  - Limits are set with `monkeypatch.setattr(settings, "USAGE_REQUESTS_PER_MINUTE"/"USAGE_DAILY_TOKEN_BUDGET", ...)` (the `_limits()` helper).
  - All tests use `temp_db`.

  Tests (one per bullet, named for the behaviour):

  **AC 1: refusal shape and row**
  - Rate refusal: `rpm="*=1"`, stubbed `window_requests=2` → result `== QueryBlockedUsageLimitResponse(reason="Usage limit reached", limit="requests", maximum=1, actual=2, resets_at=<end of _WINDOW_START>)`. `call_openrouter` is `_fail_if_called`. Exactly one new row with `success is True`, `limit_exceeded == "requests"`, `role == identity.role`, `dedup_key` not None and equal to `dedup_key(user, messages)`, `error_message is None`, and `prompt_hash`/`prompt_preview` those of the last user turn (PRD 6.7: no prompt withheld). It also carries `ingress`, `message_count` and `conversation_key` (the Section 9.2 invariant) when called with `ingress="chat"`.
  - Budget refusal: stubbed `tokens_today=budget` → `limit="tokens"`, `resets_at` is the next 00:00 UTC of the stubbed day, row `limit_exceeded == "tokens"`.
  - Both broken → `requests` reported.
  - `run_query` reaches the same arm (`ingress` defaults to `"query"` on the row).

  **AC 2: order and counting**
  - Spy order: extend the `_install_order_spies` pattern (`tests/test_query_pipeline_multiturn.py:139-182`) with a spy on `query_pipeline.admit` labelled `"usage"`. On a success: `["authorize", "authorize", "usage", "context_limit", "duplicate", "pattern", ...]`.
  - Forbidden caller (`Identity("reviewer", "auditor")`, lacks `query:submit`): `query_pipeline.admit` is `_fail_if_called`, the result is `QueryBlockedForbiddenResponse`, and `SELECT COUNT(*) FROM usage_daily WHERE user_id=?` is `0` (real storage, no stub).
  - Disallowed model and BYOK-denied: `admit` is never called (the same spy). Each authorization arm precedes the gate.
  - Duplicate-blocked request consumes one unit: real storage, a success then the same prompt → `QueryBlockedDuplicateResponse`, and `usage_daily.requests == 2`.
  - Context-limit refusal consumes one unit: `CONTEXT_MAX_CHARACTERS=10`, an over-limit prompt → `QueryBlockedContextLimitResponse`, `requests == 1`.
  - Pattern block consumes one unit (follows from the order, and cheap to pin).
  - A usage refusal precedes the context limit: an over-limit conversation from an over-rate identity → usage-limit response, and `_context_limit_exceeded` is `_fail_if_called`.

  **AC 3: duplicate-lookup exclusion end to end**
  - `rpm="*=1"`. The stub returns `window_requests=2` on the first call (refused) and `1` on the second, simulating the reset. Send prompt P → usage-limit response. Send P again → `QuerySuccessResponse`, not duplicate. Then the stub stays at 1 and P a third time → `QueryBlockedDuplicateResponse` whose `first_query_at` is the **success** row's timestamp, not the refusal's. This proves the success is a prior query and the refusal is not.

  **AC 4: fail closed**
  - `query_pipeline.admit` raising `UsageLimitError` → `run_conversation` raises it. A `log_query` spy records nothing, and `call_openrouter` is `_fail_if_called`.
  - Realistic: `usage_limits.admit_usage` raising `StorageError` → `UsageLimitError` reaches the caller (the wrapper is STORY-010's, and this pins that the pipeline does not swallow it).
  - Router: through `TestClient`, with `query_pipeline.admit` raising `UsageLimitError("Usage admission failed: x")` → `500`, `{"detail": "Usage admission failed: x"}`, and `app.routers.query.call_openrouter` is `_fail_if_called`. Use the authenticated-user fixture pattern from `tests/test_query_outcomes_regression.py:36-52`.

  **AC 5: switch off**
  - `USAGE_LIMITS_ENABLED=False`. `query_pipeline.admit`, `usage_limits.admit_usage` and `usage_limits.charge_usage` are all `_fail_if_called`. A success, a duplicate and a context-limit refusal each run normally, and `SELECT COUNT(*) FROM usage_daily` is `0`.
  - With the switch off and an rpm of 1 (which would refuse), two different prompts both succeed.

  **D8: BYOK**
  - Admin identity with `openrouter_api_key="sk-x"`: the spy on `query_pipeline.admit` records `charges_budget is False`. Without a key it records `True`. With stubbed `tokens_today >= budget` and a key → success, not refused (the budget is skipped). With rate over and a key → refused with `requests`.

  **Settings per call**
  - Flipping `USAGE_LIMITS_ENABLED` between two calls in one test changes behaviour (mirror `test_limits_are_read_per_call_not_captured_at_import`, `tests/test_query_pipeline_context_limit.py:344`).
- **Mirror**: `tests/test_query_pipeline_context_limit.py:40-60, 288-342`, `tests/test_usage_limits.py:45-91`, `tests/test_query_pipeline_multiturn.py:139-212`
- **Validate**: `python -m pytest tests/test_query_pipeline_usage_limits.py -q -p no:randomly`

### Task 7: Outcome 8 in the `/query` regression

- **File**: `tests/test_query_outcomes_regression.py`
- **Action**: UPDATE (append only)
- **Implement**: Add `test_outcome_8_usage_limit` directly after outcome 7, with a docstring citing PRD-013 Section 11 "Eight outcomes" and D5 (never 429). Rows 1–7 and the characterization test stay byte-identical. Diff-check that only additions appear.
  - Setup through **real storage**, so the regression covers the real `admit_usage` statement. Set `USAGE_DAILY_TOKEN_BUDGET="*=100"`, then seed today's row for `_AUTH_USER_ID` with `INSERT INTO usage_daily (user_id, day, requests, window_start, window_requests, input_tokens) VALUES (?, date('now'), 0, strftime('%s','now')/60, 0, 100)`. This is a budget refusal, so no minute boundary can flip it. `call_openrouter` is `_fail_if_called`.
  - Assert `status_code == 200` and an exact dict: `{"status": "BLOCKED", "reason": "Usage limit reached", "limit": "tokens", "maximum": 100, "actual": 100, "resets_at": expected}`. `expected` is the next 00:00 UTC after the `day` read back from that user's single `usage_daily` row. That reads the database's day, not Python's, so a run that straddles midnight cannot make it wrong. The exact dict is what proves FastAPI serializes the sixth union member as itself (outcome 7's reasoning).
  - `_count_audit_rows() == before + 1`. The latest row has `success is True`, `limit_exceeded == "tokens"`, and `dedup_key is not None`.
  - Update the module docstring only by appending a sentence for PRD-013 (rows 1–7 unchanged, row 8 added). Do not edit the existing sentences.
- **Mirror**: `tests/test_query_outcomes_regression.py:204-241`
- **Validate**: `python -m pytest tests/test_query_outcomes_regression.py -q`

### Task 8: Schema and chat pins

- **Files**: `tests/test_schemas.py`, `tests/test_chat_state.py`
- **Action**: UPDATE (additions only)
- **Implement**:
  - `test_schemas.py`: `model_dump()` equals the PRD Section 10 body. `QueryBlockedUsageLimitResponse in get_args(QueryResponse)`. `limit` rejects `"messages"`, `"REQUESTS"`, `""` (mirror `:95-125`). No request schema gains a `limit`/`ingress` field (the Section 9.2 invariant), which is already pinned by STORY-005. Only check it if not.
  - `test_chat_state.py`: (a) a stubbed pipeline returning `QueryBlockedUsageLimitResponse(...)` → the last bubble has `kind == "internal_error"` and a `detail` containing `"Usage limit reached"` and the `resets_at`, with a docstring saying STORY-014 replaces this pin (mirror the PRD-010 STORY-008 interim pin, `:307-316`). (b) A stubbed pipeline raising `UsageLimitError("Usage admission failed: x")` → `internal_error` bubble with that detail. Use the existing `_stub_pipeline` / `_make_state` / `_send` helpers.
- **Validate**: `python -m pytest tests/test_schemas.py tests/test_chat_state.py -q`

### Task 9: Full-suite sweep

- **Action**: VERIFY
- **Implement**: Run the full suite. Limits are **on** by default in tests, as the story says, so every pipeline test that reaches step 2c now writes one `usage_daily` row. Expected fallout and the rule for each:
  - **A test fails with `UsageLimitError` / "missing relation usage_daily"**: it reached the gate on an uninitialized database (no `temp_db`). Survey: every test that stubs `check_duplicate` already uses `temp_db`, so none is expected. If one appears, give it `temp_db` with a comment citing PRD-013 STORY-011. **Do not** flip `USAGE_LIMITS_ENABLED` off in `conftest.py`: that would hide the gate from every regression suite.
  - **A test asserts on table contents or the table list after a send**: add `usage_daily` to its expectation with a PRD-013 comment. Survey: `tests/test_conftest_fixtures.py:265` and `tests/test_db.py:2041` list tables after `init_db` only, so `usage_daily` is already there from STORY-009.
  - **A test sends more than 60 requests per user in one minute**: none found (the largest are `test_query_pipeline_audit_fields.py`'s 50-turn test, `test_pipeline_concurrency.py`'s `_BLOCKED = 10` and `test_two_instance_smoke.py`'s `10` per instance). If one appears, raise that test's `USAGE_REQUESTS_PER_MINUTE` with a comment. Do not change the default.
  - `tests/test_audit_characterization.py` (STORY-001) and `ARM_CASES` are **not** extended. A thirteenth arm there would change STORY-001's assertions. The usage-limit row's fields are pinned in Task 6 instead, and the AST scan covers its `log_query` call.
  - Every modified pre-existing test carries a comment citing PRD-013 STORY-011 and the decision (PRD Section 11, Quality indicators).
  - Mass fixture errors mean restarting `harness-libsql-dev`, not bisecting code. `tests/test_chat_sessions.py` has a known intermittent flake: rerun it before blaming the change.
- **Validate**: `C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe -m pytest tests/ -q`

---

## Risks

| Risk | Mitigation |
|---|---|
| Minute-boundary flakes in rate tests | Refusal tests stub `admit_usage` with a fixed `window_start`. Real-storage tests assert the day's `requests`, not `window_requests`. The regression's outcome 8 is a **budget** refusal, and its `resets_at` is computed from the DB's `day`. |
| Spies cannot see the gate | `admit` is imported into `query_pipeline`'s namespace and called by that name (the `_redact` binding rule). |
| Union serialization picks a sibling `BLOCKED` model | Appended last. The exact-dict outcome 8 test proves `limit/maximum/actual/resets_at` survive serialization. |
| Touching the duplicate lookup breaks PRD-009 (Risk 5) | One predicate that NULL passes, a NULL-passes unit test, and `test_duplicate_scope.py` / `test_duplicate_characterization.py` unchanged. |
| Unused-local lint on `admission` | Kept deliberately for STORY-012, suppressed with `noqa` and a reason. |
| Every pipeline test now does one extra round trip | Accepted by the story. Latency is measured in STORY-017. `USAGE_LIMITS_ENABLED=false` restores today's count, as pinned in Task 6. |
| STORY-013 lands later and must sit at 2b | The 2c comment says where 2b goes. Ordering tests label authorization arms as one step, so 2b slots in without editing this story's order test, provided STORY-013 labels its spy as `"authorize"` or adds its own label before `"usage"`. |

---

## End-to-End Tests

- [ ] `pytest tests/test_query_pipeline_usage_limits.py`: all green, run twice (catches any minute-boundary dependence)
- [ ] `pytest tests/test_query_outcomes_regression.py`: 8 outcomes plus characterization green; `git diff` shows additions only
- [ ] `pytest tests/test_duplicate_scope.py tests/test_audit_characterization.py tests/test_chat_outcomes_regression.py tests/test_pii_characterization.py`: green with **no** diff to these files
- [ ] Manual: `uvicorn app.main:app` against the dev DB, `USAGE_REQUESTS_PER_MINUTE="*=2"`. Three different prompts in quick succession with a user token give the third a `200` `{"status":"BLOCKED","reason":"Usage limit reached","limit":"requests",...}`. `GET /audit` shows that row with `limit_exceeded="requests"`.
- [ ] Manual: `docker stop harness-libsql-dev` mid-run is not useful (everything fails). The `500` path is covered by the router test in Task 6.

---

## Validation

```bash
C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe -m pytest tests/test_query_pipeline_usage_limits.py tests/test_query_outcomes_regression.py tests/test_schemas.py tests/test_chat_state.py tests/test_query_router.py tests/test_duplicate_scope.py -q
C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe -m pytest tests/ -q
C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe -c "import app.main"   # server imports cleanly
```

---

## Acceptance Criteria

(Copied from story `STORY-011`)

- [ ] Given an identity over its rate limit or its budget, when `run_conversation` runs, then it returns `QueryBlockedUsageLimitResponse(reason="Usage limit reached", limit=..., maximum=..., actual=..., resets_at=...)`, `call_openrouter` is not called, and exactly one row is written with `success=1`, `limit_exceeded` set, `role` set and a non-NULL `dedup_key`.
- [ ] Given spies on each step, when a request runs, then the order is authorization, usage gate, context limit, duplicate, patterns; a caller without `query:submit` never reaches the gate and has no `usage_daily` row; a duplicate-blocked request and a context-limit refusal each consume one unit of the rate window.
- [ ] Given a prompt refused for a usage limit, when the same prompt is sent again after the window resets, then it is answered and not held as a duplicate; `test_duplicate_scope.py` and STORY-001 pass with no assertion changed.
- [ ] Given `POST /query` over a limit, when it is called, then the status is `200` with the usage-limit body; given `admit` raising `UsageLimitError`, then the status is `500` and no upstream call is made.
- [ ] Given `USAGE_LIMITS_ENABLED=false`, when any request runs, then no statement touches `usage_daily`, and `tests/test_query_outcomes_regression.py` gains row 8 (usage limit) with rows 1-7 unchanged.
- [ ] All tasks completed
- [ ] Full suite green
- [ ] Server imports without error
- [ ] Follows existing patterns; every modified pre-existing test cites PRD-013 STORY-011
