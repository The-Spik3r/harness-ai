---
story: STORY-010
prd: PRD-017
slug: step-7c-action-evaluation
title: "Step 7c: evaluate every call, release, record() with audit_id, fail closed, has_tool_calls"
type: NEW_CAPABILITY
complexity: HIGH
epic_branch: epic/PRD-017-tool-calling
created: 2026-11-16
---

# Plan: Step 7c, action evaluation and the decision audit

## Summary

`run_conversation` gains step **7c**, between the 7b charge and step 8. It runs only when the
upstream returned tool calls (`openrouter_result.tool_calls` is non-empty, which D18 limits to
requests that sent `tools=`). It converts each `ToolCallSpec` to `action_adapters.ToolCall`
field for field (F6) and calls `action_policy.evaluate_all(calls, identity)` once. It then
calls `tool_release.apply_decisions(openrouter_result.tool_calls, decisions)`. Step 8 is
otherwise unchanged. Output redaction (`policy.output`) still sees only the upstream content.
The denial notes are joined **after** redaction with `tool_release.content_with_notes`, and
that joined text becomes `QuerySuccessResponse.response`. The success row is written with
`has_tool_calls` from D19. Then `action_audit.record(decisions, identity, audit_id=<row id>,
session_id=session_id)` runs. A `StorageError` from `record()` is logged at ERROR (user and
`audit_id` only) and re-raised as a new `ActionAuditError`. The `/v1` router maps that error to
500 `internal_error`, retryable, in both response shapes.

The `Release` and the decisions reach the router through a new frozen
`tool_release.ToolOutcome` held in a pydantic **private attribute** on
`QuerySuccessResponse`. A read-only `tool_outcome` property exposes it. `/query`'s JSON, its
OpenAPI schema and `tests/test_query_outcomes_regression.py` do not change. Every audit row the
pipeline writes now passes `has_tool_calls`. It is a required parameter of `_deny`, so a
tool-turn request is marked on every arm (D19), not only on the success row.

## User Story

As a security admin
I want every tool call the model produced decided by the action policy and recorded against the request's audit row before the response is shaped
So that no call reaches a client undecided or unrecorded

## Story Reference

- Story file: `.agents/stories/PRD-017-tool-calling/STORY-010-step-7c-action-evaluation.md`
- PRD: `.agents/PRDs/PRD-017-tool-calling/PRD.md`: Section 6.1 (lines 140-159), 6.5 (216-228), 6.6 (230-246), F6/F7 (325-330), T1/T5 (362, 366), 11 (446-450), D8/D19 (520, 531)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | HIGH |
| Systems Affected | `app/services/query_pipeline.py`, `app/services/tool_release.py`, `app/models/schemas.py`, `app/routers/v1.py`, docstrings of `app/services/action_policy.py` / `app/services/action_audit.py`, `tests/test_query_pipeline_tools.py`, `tests/test_v1_tools.py` |
| Story | STORY-010 |
| PRD | PRD-017 |
| Epic Branch | `epic/PRD-017-tool-calling` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` (UI guidance). This story has no UI, and its frontmatter is `skills: []`. | none |

---

## Design decisions

### DD-1: How the router receives the Release and the decisions (the central question)

The four options, checked against the code:

| Option | What it costs | Verdict |
|---|---|---|
| **A. Pydantic `PrivateAttr` on `QuerySuccessResponse`** | Pydantic 2.13.5 (`.venv`). Private attributes are not fields: `model_dump`, `model_dump_json` and `model_json_schema` leave them out, so FastAPI's `response_model=QueryResponse` serialization (`app/routers/query.py:22`) and the OpenAPI document are unchanged. The value travels on the result object through `run_in_pipeline`'s future (`app/routers/v1.py:297-315`), so there is no shared state and no thread hand-off. One cost: pydantic v2 `__eq__` also compares `__pydantic_private__`, so two otherwise-equal results differ when only one carries an outcome. No existing test compares a tool-call result by equality: a calls-free result keeps the default `None`, so every existing equality holds. | **Chosen** |
| B. A field with `exclude=True` | It is still a field. It appears in `model_json_schema()` and so in `/query`'s OpenAPI schema. It is also settable from input during validation, and its type (`ActionDecision` → `Classification`/`Operation` dataclasses) would need `arbitrary_types_allowed` on a public response model. `/query`'s contract would move. | Rejected |
| C. A wrapper type the router unwraps | It changes `QueryPipelineResult` (`query_pipeline.py:42-49`), which `/query`, `ChatState` and the `_outcome` `isinstance` dispatch (`v1.py:222`) all read. Either every door learns a new member (D17 says they must not change) or the return type depends on an argument. | Rejected |
| D. A side channel on `_Upstream` written by the pipeline | The pipeline would have to know the router's wrapper type (`v1.py:111-139`). It would also put the decided calls next to the raw `upstream.result.tool_calls`, one attribute access away from a T1 mistake. | Rejected |

**Shape.** A new frozen dataclass goes in `app/services/tool_release.py`, the pure module that
STORY-011's `translate_result` (in pure `v1_translate`) can import without pulling in storage:

```python
@dataclass(frozen=True)
class ToolOutcome:
    """Step 7c's result for one response (PRD-017 Section 6.1): what the router may release."""
    release: Release
    decisions: tuple["ActionDecision", ...]   # evaluate_all's, in call order
```

`app/models/schemas.py` (`QuerySuccessResponse`, `:74-81`) gains
`_tool_outcome: Any = PrivateAttr(default=None)`, commented as never serialized, plus a
read-only `@property tool_outcome`. `schemas.py` imports nothing from `app`
today, and the attribute is typed `Any` so that stays true. The property's return annotation
names `ToolOutcome` under `TYPE_CHECKING` only. The pipeline sets the attribute once, right after it
builds the success response, and only when 7c ran. `None` means "no calls were evaluated":
STORY-011 reads that as `harness.actions == []` with the upstream's `finish_reason`. This
matches `Release.finish_reason=None`'s "keep the upstream's".

**Proof that `/query` is unchanged.** `tests/test_query_outcomes_regression.py` and
`tests/test_chat_outcomes_regression.py` stay unedited and green. A new test asserts that
a `QuerySuccessResponse` with a `ToolOutcome` set gives the same `model_dump()`,
`model_dump_json()` and `model_json_schema()` as one without. It also asserts that
`app.openapi()`'s `QuerySuccessResponse` component lists exactly the seven fields from
`schemas.py:75-81`.

**T1.** The router still never reads `upstream.result.tool_calls`. This story adds a source-scan
test over `app/routers/v1.py` that fails on any `<x>.result.tool_calls` attribute chain. The
router consuming `tool_outcome` is STORY-011 (F8). This story does not touch
`translate_result`.

### DD-2: Notes join `response` here, so the interim `/v1` body shows them

`QuerySuccessResponse.response` becomes `content_with_notes(redacted_response, release.notes)`
when 7c ran, and stays `redacted_response` otherwise. The second branch keeps `/query`'s code path
byte for byte. This follows from AC5 and the `tool_release` module docstring
(`tool_release.py:21-23`: "STORY-010 calls it after step 8 redaction ... the response shapes
(STORY-011/012) do not re-join"). It also matches STORY-011 AC2 ("every call denied → `content`
is the notes"). One consequence is that the two interim T1 pins in `tests/test_v1_tools.py:835-877` change.
Their upstream (`bash`, `rm -rf /`) is now really decided (deny), so the client gets the note
as content. **The plan names exactly what changes** (Task 7): the content assertion and the
leak list. The pin's point, no undecided call and no `tool_calls` key in either shape, stays,
and an allowed-call twin is added. The audit row's `response` stays `openrouter_result.response`
(`query_pipeline.py:809`). The row records what the upstream said, and the decisions live in
`action_decisions`.

### DD-3: `has_tool_calls` on every row (D19), required in `_deny`

D19: "1 when the request carries an assistant `tool_calls` or a `tool` turn, or the upstream
response carried calls (before release)". Every row can know the request half, because the
request half is a pure function of `messages`. So it is computed once at step 1b (`query_pipeline.py:318-328`,
the same "pure, computed before authorization" argument), as
`request_has_tool_turns = _has_tool_turns(messages)`. A new module-level helper returns
`any(m.role == "tool" or m.tool_calls for m in messages)`, module-level so tests can call it.
It is passed as follows:

- `_deny` gets a new **required** parameter `has_tool_calls: bool`. It is placed after
  `ignored_params`, before `exc`, with the same comment discipline as `:217-248`, so a forgotten
  arm is a TypeError. All four `_deny` calls (`:334-385`) pass `request_has_tool_turns`.
- Direct `log_query` calls for usage limit (`:425`), context limit (`:470`), duplicate (`:501`),
  pattern block (`:555`), flag (`:591`), redaction limit (`:632`), input-redaction error
  (`:679`) and upstream error (`:718`) pass `has_tool_calls=request_has_tool_turns`. The
  upstream-error arm has no result, so it cannot know the response half. The request half is
  still true for it.
- The output-redaction error (`:776`) and the success row (`:805`) have the upstream result, so they pass
  `request_has_tool_turns or bool(openrouter_result.tool_calls)` (one local, `has_tool_calls`).

The scans `tests/test_query_pipeline_*.py` count **eleven** `log_query` sites
(`test_query_pipeline_pii_profiles.py:894`, `test_query_pipeline_session_passthrough.py:507`).
This story adds no site, because `record()` is not `log_query`. `_drive`'s conversations are
tool-free, so `test_audit_characterization.py:545-555` (`has_tool_calls: False` on every arm)
stays green. The existing `_deny(...)` TypeError tests (`test_query_pipeline_dedup_key.py:201`,
`test_query_pipeline_pii_profiles.py:877`, `test_query_pipeline_audit_fields.py:286-293`) use
`pytest.raises(TypeError, match=<name>)`. Python's message lists every missing argument, so it
still names theirs and they stay green unedited. `/query` and chat rows remain `0`.

### DD-4: Where `ActionAuditError` lives and what it says

It goes in `app/services/query_pipeline.py`, beside `InvalidConversationError` (`:60-69`). The
pipeline is what catches and re-raises, and the router already imports from it (`v1.py:61`).
`action_audit` keeps its "no catch" contract (`action_audit.py:38-40`). The pattern is
`duplicate_checker.py:33-35` / `usage_limits.py:159-162` (catch `StorageError`, raise a typed
error `from exc`), with one difference. `translate_fault` sends `str(exc)` to the client
(`v1_translate.py:686-705`), so the message is a **fixed string** with no driver text:
`"Action audit failed: decisions could not be recorded"`. It catches `app.db.errors.StorageError`,
and `IntegrityError` is a subclass of it (`app/db/errors.py:49`). Before raising,
`logger.error("action audit failed: user_id=%s audit_id=%s", identity.user_id, audit_id)` runs.
That logs no arguments, no exception text and no traceback (T9 rule; `action_policy.py:321-329` is the precedent).
`/query` cannot reach it: it never sends `tools`, so no calls come back (D18). Its router's
`except` chain (`app/routers/query.py:29-40`) is not touched (D17).

### DD-5: Call collaborators through their modules

`from app.services import action_adapters, action_audit, action_policy, tool_release`, called
as `action_policy.evaluate_all(...)`, `action_audit.record(...)` and so on. Tests then patch
the source module (`monkeypatch.setattr(action_audit, "record", ...)`) and reach the
pipeline. The precedent is `action_policy._classify` (`action_policy.py:171-178`, "called
through its module so a test's monkeypatch reaches it"). The `query_pipeline.admit`/`redact`
by-name rule (`:37-40`) is for names the suite already patches there. These four are new, so
module-qualified calls are the simpler rule. A comment at the import says this.

### DD-6: What 7c does not do

- 7c does not run when the upstream returned no calls. In that case there is no `evaluate_all`, no `apply_decisions`, no
  `record()`, and `tool_outcome` is `None`. AC2's "an upstream result with no calls records nothing" is
  tested with spies that must not be called.
- It records nothing on the output-redaction error arm. Nothing is released there, the row is
  `success=False` with `has_tool_calls=1`, and the PRD places `record()` at step 8 against
  the success row only (Section 6.1, F7). One `record()` site keeps the T5 reasoning simple.
- It does not re-evaluate history calls (T3).
- `apply_decisions`' `ValueError` (a programming error) is not caught. It propagates as a bug:
  Starlette's 500 for JSON, `internal_error` for SSE (`v1.py:252-258`).

---

## Patterns to Follow

### Naming / step lettering
```python
# SOURCE: app/services/query_pipeline.py:387-391
    # Step 2c: the usage gate (PRD-013 Sections 6.1, 6.5-6.7; D7, D8, F10).
    #
    # Lettered, not renumbered: three PRDs and the comments below cite steps
    # 3-8 by number. The break-glass arm (2b) sits directly above.
```

### Required keyword in `_deny`
```python
# SOURCE: app/services/query_pipeline.py:245-248
    # Required for the same reason as the five above (PRD-015 STORY-007): a
    # forgotten authorization arm is a TypeError, not a `/v1` row that
    # silently claims the client got everything it asked for.
    ignored_params: Optional[str],
```

### Error handling (storage → typed fault)
```python
# SOURCE: app/services/duplicate_checker.py:32-35
    try:
        match = find_duplicate_timestamp(user_id, key, cutoff)
    except StorageError as exc:
        raise DuplicateCheckError(f"Duplicate lookup failed: {exc}") from exc
```
Deviation, as DD-4 explains: the message is fixed and carries no `{exc}`.

### Router fault mapping
```python
# SOURCE: app/routers/v1.py:108, 196-197
_PIPELINE_FAULTS = (OpenRouterError, DuplicateCheckError, UsageLimitError, PiiRedactorError)
...
    if isinstance(exc, (DuplicateCheckError, UsageLimitError)):
        return INTERNAL_ERROR
```

### Tests
```python
# SOURCE: tests/test_query_pipeline_tools.py:87-92 (pipeline driver)
def _run(messages, call_openrouter=_fake_call_openrouter, **kwargs):
    kwargs.setdefault("identity", _JUAN)
    return query_pipeline.run_conversation(
        messages=messages, device=None, model="gpt-4", openrouter_api_key=None,
        call_openrouter=call_openrouter, **kwargs,
    )
# SOURCE: tests/test_v1_tools.py:590-599 (router stub with tools=), :838-848 (interim pin)
# SOURCE: tests/test_v1_sse.py:587-609 (post-commit fault = one data event, no [DONE])
# SOURCE: tests/test_v1_errors.py:589-610 (_assert_fault: body, retry header)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/tool_release.py` | UPDATE | Add frozen `ToolOutcome(release, decisions)` (DD-1); docstring line for it. Stays pure. |
| `app/models/schemas.py` | UPDATE | `QuerySuccessResponse`: `_tool_outcome` `PrivateAttr(default=None)` + read-only `tool_outcome` property (DD-1). |
| `app/services/query_pipeline.py` | UPDATE | `ActionAuditError`; `_has_tool_turns`; step 1b local; `_deny(has_tool_calls=)`; `has_tool_calls` on all 11 `log_query` sites; step 7c; step 8 notes join + `record()` + fail closed; set `_tool_outcome`. |
| `app/routers/v1.py` | UPDATE | `ActionAuditError` into `_PIPELINE_FAULTS` and `_fault_code` → `INTERNAL_ERROR`; module and `_Upstream` docstrings (T1: decided calls come from the pipeline result). |
| `app/services/action_policy.py` | UPDATE | Docstring only (`:27-28`, `:55-58`): name the live caller (`query_pipeline` step 7c, PRD-017 STORY-010). |
| `app/services/action_audit.py` | UPDATE | Docstring only (`:5-6`, `:38-40`): `record()` is called at step 8. A `StorageError` becomes `ActionAuditError` there (D8). |
| `tests/test_query_pipeline_tools.py` | UPDATE | New STORY-010 section (pipeline level: AC1, AC2, AC3, AC5, D19 per arm, scans). |
| `tests/test_v1_tools.py` | UPDATE | New STORY-010 section (router level: AC3 both shapes, AC4 DROP TABLE, T1 scan, `/query` schema proof); interim pins adjusted (Task 7); module docstring. |

No new files. No DB, migration or settings changes.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: `ToolOutcome` in `tool_release`

- **File**: `app/services/tool_release.py`
- **Action**: UPDATE
- **Implement**: Below `Release` (`:52-62`), add `@dataclass(frozen=True) class ToolOutcome` with
  `release: Release` and `decisions: tuple["ActionDecision", ...]`. Use `#:` field comments like
  `Release`'s: decisions are `evaluate_all`'s, in call order, one per upstream call. Add one
  module-docstring sentence: "`ToolOutcome` is what step 7c hands the router on the success
  result (STORY-010)". Keep `ActionDecision` under `TYPE_CHECKING` (`:35-36`). The purity
  test (`tests/test_tool_release.py:210-228`) must stay green.
- **Mirror**: `tool_release.py:52-62`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_tool_release.py -q`

### Task 2: Private attribute on `QuerySuccessResponse`

- **File**: `app/models/schemas.py`
- **Action**: UPDATE
- **Implement**: Import `PrivateAttr` from pydantic, `Any` from typing, and, under
  `TYPE_CHECKING`, `ToolOutcome` from `app.services.tool_release`. Add
  `_tool_outcome: Any = PrivateAttr(default=None)` with a comment. It is not a field: never
  serialized and absent from the schema, so `/query`'s body and OpenAPI do not move (PRD-017
  D17, STORY-010 DD-1). Step 7c sets it, `None` means no call was evaluated, and its type is
  `Any` so this module imports nothing from `app`. Add
  `@property def tool_outcome(self) -> "Optional[ToolOutcome]": return self._tool_outcome`.
- **Mirror**: n/a (first private attribute in the repo; grep found none).
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`;
  `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_schemas.py -q`

### Task 3: `ActionAuditError`, `_has_tool_turns`, and `has_tool_calls` on every arm

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**:
  1. Imports: `from app.db.errors import StorageError` and
     `from app.services import action_adapters, action_audit, action_policy, tool_release`, with the DD-5
     comment.
  2. After `InvalidConversationError` (`:60-69`), add `class ActionAuditError(Exception)`. Its docstring
     says: `record()` failed after the success row was written (PRD-017 D8, F7). The pipeline
     logs the user and `audit_id` at ERROR and raises this with a fixed message (no driver text,
     because `/v1` sends the message to the client). `/v1` maps it to 500 `internal_error`, retryable, and
     nothing is released. `/query` never reaches it (no tools, D17/D18).
  3. Add module-level `_has_tool_turns(messages) -> bool` with a D19 docstring: request half only, and
     a pure function of the conversation, so step 1b computes it.
  4. `_deny`: add the required `has_tool_calls: bool` after `ignored_params` (`:248`) with the
     "Required for the same reason ... (PRD-017 D19)" comment, and pass it to `log_query` (`:252-267`).
  5. Step 1b (`:318-328`): `request_has_tool_turns = _has_tool_turns(messages)`, and extend the comment
     to say this is the D19 request half.
  6. Pass `has_tool_calls=request_has_tool_turns` to each of the four `_deny` calls and the eight
     pre-result `log_query` sites listed in DD-3.
- **Mirror**: `query_pipeline.py:217-248` (required-keyword comments), `:318-328`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_query_pipeline_audit_fields.py tests/test_audit_characterization.py -q`

### Task 4: Step 7c and the step 8 changes

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**: After the 7b block (`:738-763`):
  ```python
  # Step 7c: actions (PRD-017 Section 6.1; F6; D1, D2, D9; T1).
  # <comment: why after 7b (tokens spent whatever the decision, PRD-013 T3); why
  #  before 8 (classifies the arguments as written, PRD-016 6.1; step 8 needs the
  #  final content); runs only when the upstream returned calls, which D18 limits
  #  to a request that sent tools=; ToolCallSpec -> ToolCall field for field (F6);
  #  evaluate_all never raises for model input (PRD-016 F7); apply_decisions'
  #  ValueError is a programming error and propagates (T1).>
  outcome = None
  if openrouter_result.tool_calls:
      calls = tuple(
          action_adapters.ToolCall(c.id, c.name, c.arguments)
          for c in openrouter_result.tool_calls
      )
      decisions = action_policy.evaluate_all(calls, identity)
      outcome = tool_release.ToolOutcome(
          release=tool_release.apply_decisions(openrouter_result.tool_calls, decisions),
          decisions=decisions,
      )
  has_tool_calls = request_has_tool_turns or bool(openrouter_result.tool_calls)
  ```
  In step 8:
  - Output redaction (`:772-801`) is unchanged and still redacts `openrouter_result.response`
    only. Add a comment that it covers content only, never a call's arguments (Section 6.5, D13),
    and that the notes are joined below, after it, so they are never masked (Section 6.6). The
    error arm's `log_query` gets `has_tool_calls=has_tool_calls`.
  - After redaction:
    `content = redacted_response if outcome is None else tool_release.content_with_notes(redacted_response, outcome.release.notes)`.
    The `outcome is None` branch is `/query`'s path, unchanged.
  - Success row (`:805-830`): replace the `has_tool_calls=False` comment (`:814-817`) with a D19
    comment and pass `has_tool_calls=has_tool_calls`. Leave `response=openrouter_result.response` as it is (DD-2).
  - After `audit_id = log_query(...)`:
    ```python
    # The decision audit (PRD-017 F7, D8; T5): after the row, which it needs
    # the id of (PRD-016 6.1). Fail closed: no release without the rows.
    if outcome is not None:
        try:
            action_audit.record(outcome.decisions, identity, audit_id=audit_id, session_id=session_id)
        except StorageError as exc:
            logger.error("action audit failed: user_id=%s audit_id=%s", identity.user_id, audit_id)
            raise ActionAuditError("Action audit failed: decisions could not be recorded") from exc
    ```
  - Build `success = QuerySuccessResponse(response=content, ...)` (otherwise `:832-839`). If
    `outcome is not None`, set `success._tool_outcome = outcome` (comment: DD-1, never serialized).
    Then `return success`.
- **Mirror**: `query_pipeline.py:738-763` (comment voice); `action_policy.py:321-329` (log line names no value).
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 5: Router maps `ActionAuditError`

- **File**: `app/routers/v1.py`
- **Action**: UPDATE
- **Implement**: Import `ActionAuditError` from `app.services.query_pipeline` (`:61`). Add it to
  `_PIPELINE_FAULTS` (`:108`). Extend the comment at `:105-107`: "plus `ActionAuditError`, which only a
  tools request reaches (PRD-017 D8)". In `_fault_code` (`:196-197`), add it to the
  `(DuplicateCheckError, UsageLimitError)` tuple, since it is a storage fault and transient (D8 cites PRD-015
  D7's storage rule). Docstrings: reword `:22-24` to say that STORY-010 decides and records the calls in
  the pipeline (step 7c), and that the response is still built from `response` (content plus denial notes)
  until STORY-011 releases the allowed calls from the pipeline result's `tool_outcome`, never from
  `upstream.result` (T1). Add one sentence to `_Upstream` (`:111-127`): its `result.tool_calls`
  are the raw upstream calls and are never read to build a response (T1).
  Nothing else changes in `_outcome`/`_sse_events`. A post-commit `ActionAuditError` becomes the SSE
  error event through the existing `_PIPELINE_FAULTS` arm (`:212-220`).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_v1_errors.py -q -k fault_code`

### Task 6: Docstrings of the engine and the audit

- **Files**: `app/services/action_policy.py`, `app/services/action_audit.py`
- **Action**: UPDATE (docstrings only)
- **Implement**: In `action_policy.py:27-28` ("what to do with it is PRD-017's") and `:55-58`, add
  that PRD-017 STORY-010 calls `evaluate_all` at `query_pipeline` step 7c, and that `tool_release` releases
  `allow`/`flag` and turns a `deny` into a note. In `action_audit.py:5-6` ("PRD-017 is the first live
  caller ... ships the function and its storage only"), name the caller:
  `query_pipeline` step 8, after the success row, with its `audit_id`. In `:38-40`, record what
  PRD-017 decided: the pipeline turns a `StorageError` into `ActionAuditError` and fails closed (D8). No
  code change.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_audit.py tests/test_action_policy.py -q`

### Task 7: Adjust the interim T1 pins (named, minimal)

- **File**: `tests/test_v1_tools.py`
- **Action**: UPDATE (pre-existing assertions; each change gets a comment citing PRD-017
  STORY-010, D2/T1)
- **Implement**: Keep both function names, so there is no rename and nothing goes in `_DELIBERATELY_SUPERSEDED_TESTS`.
  - Module docstring `:12-13`: since STORY-010 the pipeline decides every call. The body
    carries `response` (content plus denial notes) only, so no call is sent until STORY-011, and
    `test_interim_*` pin that.
  - `_assert_no_call_released` (`:846-848`): drop `"call_2"`, `"bash"` and `"rm -rf"`, which the denial note now
    legitimately contains. Check instead that the arguments string `'{"command":"rm -rf /"}'`
    (and its JSON-escaped form), `'"arguments"'` and `'"tool_calls"'` are absent.
  - `test_interim_upstream_tool_calls_are_dropped_not_released` (`:851-866`): `content == ""`
    becomes `content == <expected note>`. Build the expected note in the test from the real engine:
    `tool_release.DENIAL_NOTE_TEMPLATE.format(name="bash", id="call_2", reason=action_policy.evaluate(ToolCall("call_2","bash",'{"command":"rm -rf /"}'), Identity(_AUTH_USER_ID,"user")).reason)`.
    Also assert `decision == "deny"`. `finish_reason == "stop"` and the absence of the `tool_calls` key stay.
  - `test_interim_streamed_tool_calls_are_dropped_not_released` (`:869-877`): it keeps `_assert_no_call_released(response.text)`, which now uses the narrowed list. Add that
    the concatenated `delta.content` equals the same note.
  - Add `test_interim_allowed_call_is_decided_but_not_yet_released` (new). The upstream returns `read`
    `{"path":"src/a.py"}` (fs.read → allow under the built-in policy). The body has `content == ""`, no
    `tool_calls` key and `finish_reason == "stop"`. One `action_decisions` row is written with
    `decision='allow'`. Its docstring says STORY-011 replaces it.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_v1_tools.py -q -k interim`

### Task 8: Pipeline tests (new section in `tests/test_query_pipeline_tools.py`)

- **File**: `tests/test_query_pipeline_tools.py`
- **Action**: UPDATE (append `# --- STORY-010: step 7c ---`; extend the module docstring by one paragraph)
- **Implement**: Add a stub `_CallsUpstream(content, *calls)` that accepts `tools=` and returns
  `OpenRouterResult(response=content, tool_calls=calls, finish_reason="tool_calls", ...)`, plus
  helpers `_decisions_rows(audit_id)` (SQL on `action_decisions WHERE audit_id = ?`) and an `_events` spy list.
  OpenCode 2.0 names: `shell` `{"command": ...}`, `write` `{"path": ...}`, `read` `{"path": ...}`.
  Tests:
  1. `test_7c_runs_after_the_charge_and_before_step_8` (AC1). Set `USAGE_LIMITS_ENABLED=True`
     (as `test_query_pipeline_usage_limits.py` does) and spy `query_pipeline.charge`,
     `action_policy.evaluate_all` (wrapping the real one), `tool_release.apply_decisions`,
     `query_pipeline.redact_for_policy` (policy.output on), `query_pipeline.log_query` and
     `action_audit.record`. The order must be
     `[charge, evaluate_all, apply_decisions, redact(output), log_query(success), record]`, with
     `evaluate_all` called once with `ToolCall`s equal field for field to the upstream specs and
     `identity is _JUAN`.
  2. `test_success_result_carries_the_outcome` (AC1). `result.tool_outcome.release` equals
     `apply_decisions(upstream calls, decisions)`. The released specs are the **same objects**
     (`is`). `decisions` matches `evaluate_all`'s. `model_dump()` has exactly the seven fields.
  3. `test_no_calls_means_no_7c` (AC2). Spies that must not be called (`evaluate_all`,
     `apply_decisions`, `record`), `tool_outcome is None`, no `action_decisions` row, and
     `has_tool_calls` False for a tool-free request.
  4. `test_record_gets_the_success_rows_id_and_session` (AC2). Run with `session_id`. Rows
     come back via SQL with `audit_id == result.audit_id`, `session_id` set, one per call, in order.
  5. `test_has_tool_calls_success_row` (AC2, D19), parametrized: tool-free request + no calls → 0;
     tool-free request + calls → 1; tool-turn request (`_tool_final()`) + no calls → 1.
  6. `test_has_tool_calls_on_every_arm_for_a_tool_turn_request` (D19, DD-3), parametrized over
     the forbidden (`_DENIED`), duplicate (send twice), context-limit, flag (`profile="code"`,
     injection in the tool turn: the flag row and the success row), upstream-error
     (`OpenRouterError` stub) and output-redaction-error arms. Every written row has
     `has_tool_calls is True`.
  7. `test_deny_requires_has_tool_calls` + `test_every_log_query_site_passes_has_tool_calls`. Check the
     signature (`default is empty`, `POSITIONAL_OR_KEYWORD`) and that `_log_query_call_sources` finds 11
     sites, each containing `has_tool_calls=`. Mirror `test_query_pipeline_audit_fields.py:230-236`
     and `test_query_pipeline_pii_profiles.py:884-897`.
  8. `test_record_storage_error_is_action_audit_error` (AC3), parametrized `StorageError` /
     `IntegrityError`. `action_audit.record` raises `StorageError(f"driver said {_CANARY}")`, so the run raises
     `ActionAuditError` with `__cause__` that error and `str(exc)` the fixed message without the canary. caplog
     (`logger="app.services.query_pipeline"`) holds exactly one ERROR,
     `f"action audit failed: user_id={_JUAN.user_id} audit_id={id}"`, where id is the new success row's
     id (it exists, `success=True`, `has_tool_calls=True`, as D8 says). No log record contains the arguments
     or the canary.
  9. `test_output_redaction_covers_content_only_and_notes_follow` (AC5). Turn
     `PII_CODE_REDACT_OUTPUT` on and run `pii_policy.load()`. Replace `query_pipeline.redact_for_policy`
     with a recording fake that masks `ops@example.org` → `<EMAIL_ADDRESS>`. The upstream content is
     `"mailed ops@example.org"`. Calls: a denied call whose **tool name** is `ops@example.org`. That is
     `tool.unknown` → deny under the built-in policy, and both the note's `{name}` and the reason's detail
     carry the raw email, deterministically. Also an allowed `read` `{"path": "notes/ops@example.org.md"}`.
     Assert that the fake was called exactly once, on the content (never on a note or an argument string), that
     `result.response == "mailed <EMAIL_ADDRESS>\n\n" + note`, where `note` is built from
     `DENIAL_NOTE_TEMPLATE` and the decision's `reason` and contains `ops@example.org` unmasked, and that
     the released `read` spec's `arguments` is byte-identical (`is` the upstream's).
  10. `test_all_denied_releases_nothing` (T1 at the pipeline). Monkeypatch `action_policy.evaluate_all`
      to return a deny `ActionDecision` per call (build with `dataclasses.replace` of a real
      decision), so `release.tool_calls == ()`, `finish_reason == "stop"`, and one note per call.
  11. `test_mixed_and_flag_are_released_in_order` (D1, D9). Patch the decisions to [allow, deny, flag], so
      the release is calls [0, 2], one note, `"tool_calls"`, and the stored rows read `allow/deny/flag`.
- **Mirror**: `tests/test_query_pipeline_tools.py:87-123`, `:466-501`; `tests/test_v1_errors.py:571-581` (`_real_then_raising`).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_query_pipeline_tools.py -q`

### Task 9: Router tests (new section in `tests/test_v1_tools.py`)

- **File**: `tests/test_v1_tools.py`
- **Action**: UPDATE (append `# --- STORY-010: decide and record ---`)
- **Implement**:
  1. `test_drop_table_via_shell_is_denied_and_recorded_with_the_audit_id` (AC4), parametrized
     over `stream` False/True. The flag is on and the upstream returns
     `ToolCallSpec("call_1", "shell", json.dumps({"command": 'sqlite3 app.db "DROP TABLE users"'}))`,
     `finish_reason="tool_calls"`. Exactly one `action_decisions` row: `decision='deny'`, `rule='sql.ddl'`,
     `tool_name='shell'`, `audit_id == _only_row().id` (and `== int(X-Harness-Audit-Id)` when not streamed).
     The row has `has_tool_calls is True`. The body or stream carries no `"tool_calls"` key, and the content
     is the note.
  2. `test_action_audit_failure_is_500_internal_error_and_releases_nothing` (AC3, JSON).
     Patch `action_audit.record` to raise `StorageError(_CANARY)`, with an allowed `read` call plus a denied one.
     The response is 500 with body
     `{"error": {"message": "Action audit failed: decisions could not be recorded", "type": "api_error", "param": None, "code": "internal_error", "harness": None}}`.
     It has no `x-should-retry` header (retryable, `v1.py:176-183`). Neither call id, the arguments nor the
     canary appear in it. One `audit_logs` row with `success=True` and no `action_decisions` row.
  3. `test_action_audit_failure_after_stream_commit_is_the_error_event` (AC3, SSE). 200
     `text/event-stream`, exactly one `data:` event equal to the JSON body above, no `[DONE]`, and no
     call id or arguments in the text. Mirror `test_v1_sse.py:587-609`.
  4. `test_fault_code_maps_action_audit_error` checks `isinstance(ActionAuditError("x"), _PIPELINE_FAULTS)`
     and `_fault_code(...) == "internal_error"`. A new test, so the pre-existing parametrize at
     `test_v1_errors.py:624-638` stays unedited.
  5. `test_router_never_reads_raw_upstream_tool_calls` (T1). AST-scan `app/routers/v1.py` for
     `Attribute(attr="tool_calls", value=Attribute(attr="result"))`, which must find none.
  6. `test_query_body_and_schema_ignore_the_tool_outcome` (DD-1). A `QuerySuccessResponse` with and
     without `_tool_outcome` set gives equal `model_dump()`, `model_dump_json()` and `model_json_schema()`.
     `app.openapi()["components"]["schemas"]["QuerySuccessResponse"]["properties"]` keys equal the seven
     fields. Plus one `/query` POST through `TestClient` whose JSON keys are those seven.
- **Mirror**: `tests/test_v1_tools.py:590-626`, `:810-815`; `tests/test_v1_sse.py:587-609`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_v1_tools.py -q`

---

## End-to-End Tests

All automated (no UI, no live upstream):

- [ ] `/v1` flag on, stub upstream returns `shell` + `sqlite3 app.db "DROP TABLE users"`. Gives 200, content = note,
      no `tool_calls` key, one `action_decisions` row `deny`/`sql.ddl` with the request's `audit_id`
      (Task 9.1, JSON and SSE).
- [ ] `/v1`, `record()` raising gives 500 `internal_error` retryable (JSON), or the one SSE error event after
      commit. Nothing is released (Task 9.2/9.3).
- [ ] `/query` success JSON unchanged: `tests/test_query_outcomes_regression.py` unedited and green.

---

## Validation

Targeted run (brief: **no full suite**, one pytest call, foreground, `PYTHONUTF8=1`):

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest \
  tests/test_query_pipeline_tools.py tests/test_v1_tools.py tests/test_tool_release.py \
  tests/test_schemas.py tests/test_action_audit.py tests/test_action_policy.py \
  tests/test_query_pipeline_audit_fields.py tests/test_audit_characterization.py \
  tests/test_query_pipeline_dedup_key.py tests/test_query_pipeline_pii_profiles.py \
  tests/test_query_pipeline_session_passthrough.py \
  tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py \
  tests/test_v1_errors.py tests/test_v1_sse.py tests/test_v1_router.py tests/test_untouched_app.py -q
```

`test_pii_redaction_integration.py` is not needed because no test is renamed or removed. Full suite: deferred to the
orchestrator (user decision).

---

## Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | **Retry after `record()` failure is a duplicate.** The success row is written `success=1` before `record()` runs (it needs the id), and `find_duplicate_timestamp` (`app/db/database.py:886-893`) counts such a row as a prior query. An identical retry within 24 h, which D8 calls retryable, is answered as a duplicate verdict (400). It is still fail closed, because nothing is released, so this is an availability issue, not a security one. | **Flagged to the orchestrator as a PRD gap.** Fixing it needs either a new storage call (mark the row failed, or pass `audit_id` into `record` after a row update), which is out of this story's scope and adds a twelfth write site, or a PRD decision to accept it. The plan implements D8 as written and documents the behaviour in the `ActionAuditError` docstring. |
| R2 | Pydantic private-attribute equality (`__pydantic_private__` is compared by `__eq__`). | Only results with evaluated calls carry a non-`None` value, and no existing test builds one. Noted in the `schemas.py` comment. |
| R3 | `has_tool_calls` on refusal rows changes row content for tool-turn requests that earlier stories' tests drive. | Grep shows no test asserting `has_tool_calls` False on a tool-turn request (`tests/` hits are all tool-free or storage-level). `_drive` is tool-free. Run the audit-field and characterization files in the targeted set. |
| R4 | The interim body now shows notes, and an allowed call is still silently dropped until STORY-011. | T1 holds: nothing undecided is released. The drop is an interim gap pinned by Task 7's new allowed-call test, which STORY-011 replaces. |
| R5 | `_deny` TypeError tests elsewhere use `match=<their name>`. | Python lists every missing argument in the message, so they stay green unedited. Verified by running those files. |

---

## Acceptance Criteria

(Copied from story `STORY-010`, with how each is covered.)

- [ ] **AC1**. Given an upstream result with tool calls, the pipeline calls `action_policy.evaluate_all` once, after the 7b charge and before step 8, with `ToolCall`s and the identity, then `tool_release.apply_decisions`. The success result carries the `Release` and decisions without changing `/query`'s body. *Task 4. Tests: 8.1, 8.2, 9.6, plus the unedited `test_query_outcomes_regression.py`.*
- [ ] **AC2**. `has_tool_calls` follows D19 on the success row, then `record(decisions, identity, audit_id=<row id>, session_id=session_id)` runs. No calls means nothing is recorded. *Tasks 3-4. Tests: 8.3, 8.4, 8.5 (plus 8.6/8.7 for the other arms, DD-3).*
- [ ] **AC3**. `record()` raising `StorageError` raises `ActionAuditError` after an ERROR log naming the user and `audit_id`. `/v1` maps it to 500 `internal_error`, retryable, and nothing is released in either shape (D8). *Tasks 4-5. Tests: 8.8, 9.2, 9.3, 9.4.*
- [ ] **AC4**. A `DROP TABLE` call through `/v1` with the flag on leaves exactly one `action_decisions` row, `deny`/`sql.ddl`, with `audit_id` equal to the request's `audit_logs.id`. *Test 9.1 (JSON and SSE).*
- [ ] **AC5**. With `policy.output` on, only the content is redacted, the notes are appended after it, and the released calls are untouched. *Task 4. Test 8.9.*
- [ ] All tasks completed
- [ ] Backend imports without error (`from app.main import app`)
- [ ] Follows existing patterns (step lettering, required `_deny` keywords, typed storage faults, log lines that name no value)
