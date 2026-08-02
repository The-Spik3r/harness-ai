---
story: STORY-006
prd: PRD-003
slug: pipeline-output-redaction
title: "Redact model response before returning to caller"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-003-pii-redaction        # all stories commit here, no per-story branch
created: 2026-07-31
---

# Plan: Redact model response before returning to caller

## Summary

Close the second half of the redaction loop in `run_query()` (`app/services/query_pipeline.py`). [[STORY-005]] made the *outbound* prompt safe; this story makes the *inbound* model response safe: after `call_openrouter(...)` returns, call `redact(openrouter_result.response)` to get `(redacted_response, output_entities)`, and hand **`redacted_response` to the caller** while `log_query(...)` keeps receiving `openrouter_result.response` **raw**.

That split is the entire story. One value, two destinations, deliberately different: the audit row stays raw (PRD Section 9 — an auditor investigating an incident needs the actual value, not `<EMAIL_ADDRESS>`), the HTTP response gets masked (PRD User Story 2). It is enforced mechanically by the same rule [[STORY-005]] used for the prompt — bind the redacted text to a **new** name and never rebind `openrouter_result.response`, so `response_preview`/`response_hash` provably still see raw text by reading the diff, not by tracing control flow (Design Note 1).

This story also wires [[STORY-004]]'s three telemetry parameters into the success `log_query(...)` call — the seam [[STORY-005]] deliberately left open by capturing `input_entities` and not using it. `pii_detected_input=bool(input_entities)`, `pii_detected_output=bool(output_entities)`, `pii_entities=sorted(set(input_entities) | set(output_entities))`. Both halves of the merge now exist in one place, exactly as [[STORY-005]]'s Design Note 5 promised (Design Note 3).

Redaction failure on the response reuses the log-then-bare-`raise` idiom the file now owns twice over, with one deliberate difference from [[STORY-005]]'s input-failure row: this one **does** record `model_used`/`tokens_used`/the raw `response`, because the model genuinely was invoked and did return text (Design Note 4). No router change is needed — `app/routers/query.py:28-29` already maps `PiiRedactorError` → HTTP 500. `QuerySuccessResponse` gains no fields here; `pii_redacted`/`pii_entities_masked` are [[STORY-007]] (Design Note 5).

## User Story

As an end user
I want PII appearing in the model's response also masked before I see it
So that a model that echoes back or infers personal data doesn't expose it to me, while the audit log still keeps the raw response for compliance investigation (PRD User Story 2 and 3, RF-3, RF-7)

## Story Reference

- Story file: `.agents/stories/PRD-003-pii-redaction/STORY-006-pipeline-output-redaction.md`
- PRD: `.agents/PRDs/PRD-003-pii-redaction/PRD.md` — Section 6 (Core Architecture, steps 7-10), User Story 2 and 3, Section 9 (Why the audit log stays raw), Section 12 Phase 2

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `app/services/query_pipeline.py`, `tests/test_query_router.py` |
| Story | STORY-006 |
| PRD | PRD-003 |
| Epic Branch | `epic/PRD-003-pii-redaction` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` does not exist in this repository (verified: the directory is absent), the story's `skills:` frontmatter field is `[]`, and PRD Section 15 states it explicitly ("Skills referenced: None"). Same finding as the [[STORY-001]] through [[STORY-005]] plans.

---

## Dependency Check

| Dependency | Status | Verified |
|---|---|---|
| [[STORY-005]] — Redact prompt before forwarding to OpenRouter | ✅ done (`c69a656`) | `redacted_prompt, input_entities = redact(prompt)` at `app/services/query_pipeline.py:57`; `input_entities` in scope and unused |
| [[STORY-004]] — Audit logger records PII telemetry | ✅ done (`1347e53`) | `log_query()` accepts `pii_detected_input`/`pii_detected_output`/`pii_entities` at `app/services/audit_logger.py:23-25` |

Both `depends_on` entries are `done` — no blocker, no user confirmation needed. Transitively, [[STORY-003]] (`c8b1195`) supplied the three DB columns (`app/db/models.py:20-22`).

---

## Patterns to Follow

### The seam this story consumes

```python
# SOURCE: app/services/query_pipeline.py:56-66
    try:
        redacted_prompt, input_entities = redact(prompt)
    except PiiRedactorError as exc:
        log_query(
            user_id=user_id,
            prompt=prompt,
            device=device,
            success=False,
            error_message=str(exc),
        )
        raise
```

`input_entities` was bound and left unused by [[STORY-005]] specifically so this story could merge it with `output_entities` in one place. The output-side block is this block with a different input, a different output name, and a richer failure row.

### Raw-in, raw-out at every `log_query` call site

```python
# SOURCE: app/services/query_pipeline.py:83-91
    audit_id = log_query(
        user_id=user_id,
        prompt=prompt,
        device=device,
        response=openrouter_result.response,
        model_used=openrouter_result.model_used,
        tokens_used=openrouter_result.tokens_used,
        success=True,
    )
```

`response=openrouter_result.response` is the line this story must **not** touch (AC2). Only new keyword arguments are appended to this call.

### The audit logger's raw-preview contract

```python
# SOURCE: app/services/audit_logger.py:33-34
        response_hash=hash_prompt(response) if response is not None else None,
        response_preview=response[:_PREVIEW_LENGTH] if response is not None else None,
```

```python
# SOURCE: app/services/audit_logger.py:41-43
        pii_detected_input=pii_detected_input,
        pii_detected_output=pii_detected_output,
        pii_entities=",".join(pii_entities) if pii_entities else None,
```

Preview and hash are derived from whatever `response=` receives — so passing raw text is the whole mechanism behind RF-7. `pii_entities` is joined **in caller order without reordering** (pinned by `tests/test_audit_logger.py:204-214`), so the ordering decision belongs here, in the pipeline (Design Note 3).

### `redact()`'s tuple contract

```python
# SOURCE: app/services/pii_redactor.py:49-51
def redact(text: str) -> Tuple[str, List[str]]:
    if not settings.PII_REDACTION_ENABLED or not text:
        return text, []
```

```python
# SOURCE: app/services/pii_redactor.py:73-74
    entities_found = sorted({result.entity_type for result in results})
    return anonymized.text, entities_found
```

Always a 2-tuple; text verbatim and `[]` (never `None`) when disabled, empty, or below threshold. AC3 ("clean response → unchanged, no entities") is therefore already guaranteed by the callee — this story only has to not interfere. Note `sorted({...})`: the redactor's own convention for entity lists is sorted-and-unique, which is why the merge in Task 2 uses `sorted(set(...) | set(...))` rather than concatenation.

### Failure path: log the raw attempt, then bare `raise`

```python
# SOURCE: app/services/query_pipeline.py:68-81
    try:
        openrouter_result = call_openrouter(
            redacted_prompt, model=model, api_key=openrouter_api_key
        )
    except OpenRouterError as exc:
        log_query(
            user_id=user_id,
            prompt=prompt,
            device=device,
            model_used=model,
            success=False,
            error_message=str(exc),
        )
        raise
```

The file already owns exactly one failure idiom, now used twice. The output-redaction failure block is a third instance of it — no new pattern is invented, and the router keeps deciding status codes.

### Router-level exception translation (already in place — do not edit)

```python
# SOURCE: app/routers/query.py:26-31
    except DuplicateCheckError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except PiiRedactorError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except OpenRouterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
```

[[STORY-005]] already added the `PiiRedactorError` arm. It catches output-redaction failures identically — `app/routers/query.py` is **not** in this story's diff.

### Tests: HTTP-level pipeline tests with a monkeypatched OpenRouter

```python
# SOURCE: tests/test_query_router.py:184-189
def _capturing_openrouter(seen: list):
    def _call(prompt, model="gpt-4", api_key=None):
        seen.append(prompt)
        return OpenRouterResult(response="drafted", model_used=model, tokens_used=9)

    return _call
```

```python
# SOURCE: tests/test_query_router.py:236-248
def test_audit_row_keeps_raw_prompt_when_pii_redacted(temp_db, monkeypatch):
    monkeypatch.setattr("app.routers.query.call_openrouter", _capturing_openrouter([]))
    ...
    entry = get_audit_log(audit_id)

    assert entry.prompt_preview == _PII_PROMPT
    assert entry.prompt_hash == hash_prompt(_PII_PROMPT)
    assert "<EMAIL_ADDRESS>" not in entry.prompt_preview
```

Every pipeline test: `temp_db` fixture → patch `"app.routers.query.call_openrouter"` (the router's import site) → `client.post("/query", ...)` → assert on the body and/or the fetched `AuditLog`. The response-side tests are the mirror image of this prompt-side test, asserting on `response_preview`/`response_hash`.

### Tests: forcing a redactor failure

```python
# SOURCE: tests/test_query_router.py:192-193
def _boom(text):
    raise PiiRedactorError("PII analysis failed: analyzer exploded")
```

```python
# SOURCE: tests/test_query_router.py:316-332
def test_redactor_failure_audit_row_keeps_raw_prompt_and_error(temp_db, monkeypatch):
    monkeypatch.setattr(query_pipeline, "redact", _boom)
    ...
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
    entry = get_audit_log(row["id"])
    assert entry.success is False
```

`_boom` replaces `redact` wholesale, so it fires on the **first** call — the prompt. Testing the *output* failure needs a redactor that succeeds once and then raises (Task 4's `_boom_on_second_call`), because both call sites now share one patched name.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/query_pipeline.py` | UPDATE | Redact the response after the OpenRouter call (audited fail-closed block); wire the three telemetry args into the success `log_query()`; return `redacted_response` |
| `tests/test_query_router.py` | UPDATE | Add 9 tests covering AC1-AC4, the raw-audit guarantee, telemetry wiring, the disabled toggle, and the audited output-failure path |

**Explicitly NOT touched:**

- `app/routers/query.py` — the `PiiRedactorError` → 500 arm already exists (`query.py:28-29`) and catches this path unchanged
- `app/models/schemas.py` — `pii_redacted` / `pii_entities_masked` are [[STORY-007]]. `QuerySuccessResponse` gains **nothing** here, so `test_clean_prompt_success_returns_expected_shape_and_logs_row` (`tests/test_query_router.py:78-97`), which asserts the body is byte-for-byte a 5-key dict, stays green unmodified (Design Note 5)
- `app/services/audit_logger.py` — [[STORY-004]] is done; this story is a pure caller. No new parameter, no change to the join or the preview logic
- `app/services/pii_redactor.py` — [[STORY-001]] is done; pure consumer
- `app/services/duplicate_checker.py`, `app/services/pattern_detector.py` — untouched, byte-for-byte (RF-6). Must be absent from `git diff --name-only`
- `app/db/models.py` — the three columns landed in [[STORY-003]]
- `/audit` and `/stats` exposure of the new telemetry — [[STORY-009]]. This story only *writes* the columns
- `tests/test_audit_logger.py`, `tests/test_duplicate_checker.py`, `tests/test_pattern_detector.py`, `tests/test_pii_redactor.py`, `tests/test_integration.py` — all must pass **unmodified** (PRD Section 11)

---

## Design Notes (decisions worth stating up front)

1. **Bind to a new name (`redacted_response`); never rebind `openrouter_result.response`.** This is AC2's entire mechanical safeguard, and the exact rule [[STORY-005]] applied to `prompt`. Because the raw value stays reachable under its original name, the `log_query(response=openrouter_result.response, ...)` line at `query_pipeline.py:87` needs **no edit at all** — the strongest possible evidence that `response_preview`/`response_hash` are unchanged is that the line does not appear in the diff. A `openrouter_result.response = redact(...)[0]` shortcut (or reusing the name) would silently redact the audit trail, defeating PRD Section 9 while every test that only checks the HTTP body still passed. Task 5's diff check exists to catch exactly that.

2. **Redaction happens after the OpenRouter call and before `log_query()`, not after `log_query()`.** Placement is free of behavioural consequence for the audit row (both orders log raw), but putting the `redact()` call first means a redaction failure is handled *before* a success row is written — so the failure path writes one `success=False` row instead of one `success=True` row followed by an exception (which would leave `/stats` reporting a success for a request the caller received a 500 for). This preserves PRD-001's "exactly one audit row per request" guarantee with the *correct* row, which is AC4.

3. **Entity merge: `sorted(set(input_entities) | set(output_entities))`.** The story's Technical Notes say `input_entities + output_entities` "(deduplicated)"; this is the deduplication, and it also fixes an ordering that would otherwise be arbitrary. Three reasons for this exact expression:
   - `audit_logger` joins in caller order without reordering (pinned by `tests/test_audit_logger.py:204-214`), so if the pipeline doesn't sort, the stored string's order depends on which side happened to detect what — untestable, and unstable across Presidio versions.
   - `redact()` already returns `sorted({...})` (`pii_redactor.py:73`), so sorting the union keeps the whole feature on one convention.
   - Set union is the deduplication: an `EMAIL_ADDRESS` masked in both the prompt and the response is one entity *type*, and the column records types, not occurrences (PRD Section 10's `"pii_entities": ["EMAIL_ADDRESS"]` for a request where both directions were masked).

   Passing `[]` when neither side detected anything is correct and needs no special-casing: `audit_logger.py:43` already stores `None` for a falsy list, pinned by `test_empty_entity_list_stored_as_none`.

4. **Fail-closed on output-redaction failure, audited — but with `model_used`/`tokens_used`/`response`, unlike the input-failure row.** [[STORY-005]]'s Design Note 4(c) deliberately omitted `model_used` from the input-redaction failure row, because that request never reached model selection and recording it would inflate `/stats`' `top_models` (`app/db/database.py:158-166` counts every row with a non-null `model_used`, no `success` filter). Here the opposite is true: `call_openrouter` **succeeded**, a real model was invoked, real tokens were spent, and real text came back. Suppressing that would under-report actual usage. So this row carries `model_used=openrouter_result.model_used`, `tokens_used=openrouter_result.tokens_used`, and `response=openrouter_result.response` (raw — an auditor investigating a redactor crash needs to see the text that crashed it).

   Fail-closed rather than returning the raw response: a broken analyzer must never be the reason unmasked PII reaches the caller. That is the same reasoning as [[STORY-005]] and the same class of event as `DuplicateCheckError` → 500. "Mask, never block" (PRD Section 2) governs *detection outcomes* — a detected entity never denies a request — not infrastructure failure.

   Telemetry on that row: `pii_detected_input=bool(input_entities)` and `pii_entities=input_entities` are known and recorded; `pii_detected_output` keeps its `False` default, which strictly means "unknown" here, not "no PII found". Unambiguous in practice because the row is identifiable by `success=False` + `error_message`. Same convention [[STORY-005]] used for its failure row.

5. **The caller still receives no `pii_redacted` field after this story — that is correct, not incomplete.** [[STORY-007]] adds `pii_redacted`/`pii_entities_masked` to `QuerySuccessResponse` and populates them from `input_entities`/`output_entities`, both of which are in scope by the end of this story. Adding them here would change the response contract in a story whose ACs never mention it, and would break `test_clean_prompt_success_returns_expected_shape_and_logs_row`'s exact-dict assertion — a test [[STORY-007]] will update on purpose. This story's only externally visible change is the **content** of the `response` string.

6. **`redact()` is called unconditionally — no `if settings.PII_REDACTION_ENABLED` branch.** `pii_redactor.py:50` already short-circuits to `return text, []` when the flag is false, before any analyzer is touched. Duplicating the toggle in the pipeline would put it in two places that can drift. A test pins the disabled behaviour end-to-end anyway (Task 4, `test_redaction_disabled_returns_raw_response`), because "the toggle works from the caller's seat" is worth asserting even when the mechanism lives one layer down. Same decision as [[STORY-005]]'s Design Note 3.

7. **Existing tests are unaffected — verified empirically, not assumed.** Every mocked response string the current suite returns from `call_openrouter` was run through the real redactor at the default `PII_SCORE_THRESHOLD=0.35`:

   | Mocked response | `redact()` result |
   |---|---|
   | `"Hi there!"` (`test_query_router.py:80`) | `('Hi there!', [])` |
   | `"mock response"` (`test_integration.py:37`) | `('mock response', [])` |
   | `"drafted"` (`test_query_router.py:187`) | `('drafted', [])` |
   | `"fast"` (`test_query_router.py:161`) | `('fast', [])` |

   No false positive changes any response body, so every existing assertion on `body["response"]` holds. Baseline to preserve: **136 passed** (`.venv/Scripts/python.exe -m pytest`, measured on this branch before the change).

8. **Latency: second warm `redact()` call costs ~5 ms — measured.** `test_full_pipeline_latency_within_budget` (`tests/test_query_router.py:159-177`) asserts a full `/query` round trip under 0.5 s and already calls `query_pipeline.redact("warm up")` before timing (added in [[STORY-005]] per its Design Note 8). This story adds a *second* redact call to the same request. Measured on this machine with `en_core_web_lg`: cold analyzer construction 1.23 s, every subsequent call ~0.005 s; the response being redacted in that test is `"fast"` (4 chars). ~10 ms total NER against a 0.5 s budget is not a risk. Task 5 verifies it explicitly, including the isolated-run case. If it ever regresses, the fix is warming, **never** raising the budget — PRD Section 11 declines to set a latency ceiling for redaction, so that 0.5 s must keep measuring pipeline overhead, not model load.

9. **Testing the output-failure path needs a redactor that fails on the *second* call.** Both redaction call sites resolve the same module-global name `query_pipeline.redact`, so the existing `_boom` helper (`test_query_router.py:192`) raises on the prompt and never reaches the response. Task 4 adds `_boom_on_second_call()`, a closure that delegates to the real `redact` once and then raises — which also proves the input side completed normally before the output side failed. Do not restructure the pipeline (e.g. two differently-named wrappers) to make this easier; the test helper is the right place for the complexity.

10. **Use `.venv/Scripts/python.exe` for every command.** [[STORY-003]]'s report (Deviation 1) recorded that bare `python` on this machine resolves to a global Python 3.13 without `presidio-analyzer`, producing collection errors in every module that transitively imports `app.main` → `app.services.pii_redactor`. Environment mismatch, not a code defect. All commands below name the venv interpreter explicitly.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Redact the model response after the OpenRouter call

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**: Insert a new block immediately after the `call_openrouter` try/except (ends line 81) and before the `audit_id = log_query(...)` call (line 83):
  ```python
      except OpenRouterError as exc:
          log_query(
              user_id=user_id,
              prompt=prompt,
              device=device,
              model_used=model,
              success=False,
              error_message=str(exc),
          )
          raise

      try:
          redacted_response, output_entities = redact(openrouter_result.response)
      except PiiRedactorError as exc:
          log_query(
              user_id=user_id,
              prompt=prompt,
              device=device,
              response=openrouter_result.response,
              model_used=openrouter_result.model_used,
              tokens_used=openrouter_result.tokens_used,
              success=False,
              error_message=str(exc),
              pii_detected_input=bool(input_entities),
              pii_entities=input_entities,
          )
          raise

      audit_id = log_query(
  ```
  - `redacted_response` is a **new** name. `openrouter_result.response` is never reassigned (Design Note 1).
  - Unlike [[STORY-005]]'s input-failure row, this one **does** carry `response`, `model_used`, and `tokens_used` — the model really was invoked (Design Note 4). `model_used` comes from `openrouter_result.model_used` (what actually answered), not the `model` parameter (what was requested), matching the success row at line 88.
  - `response=openrouter_result.response` on the failure row is the **raw** text (RF-7), same as the success row.
  - `pii_detected_output` is deliberately left at its default on this row (Design Note 4). Do not pass `pii_detected_output=False` explicitly — the default carries the "unknown" meaning and matches the [[STORY-005]] failure row's style.
  - Bare `raise`, never `raise HTTPException` — status codes belong to the router, which already handles `PiiRedactorError` (`query.py:28-29`). **No edit to `app/routers/query.py`.**
  - No new import: `redact` and `PiiRedactorError` are both already imported at line 12.
  - No `if settings.PII_REDACTION_ENABLED` guard (Design Note 6).
- **Mirror**: `app/services/query_pipeline.py:56-66` — the [[STORY-005]] redaction block, same shape; `:68-81` — the OpenRouter failure block, for the argument order on the failure row.
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_query_router.py tests/test_integration.py -q
  ```
  → still green with **zero** test edits (Design Note 7). At this point `redacted_response`/`output_entities` are computed but unused — that is expected until Tasks 2 and 3.

### Task 2: Wire PII telemetry into the success `log_query()` call

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**: Append three keyword arguments to the existing success `log_query(...)` call (currently lines 83-91). Change **nothing** else about that call:
  ```python
      audit_id = log_query(
          user_id=user_id,
          prompt=prompt,
          device=device,
          response=openrouter_result.response,
          model_used=openrouter_result.model_used,
          tokens_used=openrouter_result.tokens_used,
          success=True,
          pii_detected_input=bool(input_entities),
          pii_detected_output=bool(output_entities),
          pii_entities=sorted(set(input_entities) | set(output_entities)),
      )
  ```
  - `response=openrouter_result.response` **must remain untouched** — this is AC2. It must not appear as a modified line in `git diff` (Design Note 1).
  - The merge is `sorted(set(...) | set(...))`, not `input_entities + output_entities` — see Design Note 3 for why the sort and the dedup are both load-bearing.
  - `prompt=prompt` stays raw here as at every other call site.
  - No `if` around the telemetry: when nothing was detected, `bool([])` is `False` and `sorted(set() | set())` is `[]`, which `audit_logger.py:43` already stores as `NULL` (pinned by `test_empty_entity_list_stored_as_none`).
- **Mirror**: `app/services/audit_logger.py:23-25` — parameter names and types; `tests/test_audit_logger.py:131-148` — the shape [[STORY-004]] proved works (`pii_entities` as a `list[str]`, joined by the logger, not pre-joined by the caller).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_audit_logger.py tests/test_query_router.py -q
  ```
  → green, no test edits yet.

### Task 3: Return the redacted response to the caller

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**: Change exactly one argument on the final `QuerySuccessResponse` (currently lines 93-98):
  ```python
      return QuerySuccessResponse(
          response=redacted_response,
          audit_id=audit_id,
          model_used=openrouter_result.model_used,
          tokens_used=openrouter_result.tokens_used,
      )
  ```
  - This one-line change is AC1. `audit_id`, `model_used`, `tokens_used` are unchanged.
  - Do **not** add `pii_redacted=` / `pii_entities_masked=` — [[STORY-007]] (Design Note 5).
- **Mirror**: `app/services/query_pipeline.py:93-98` — same constructor, one argument swapped, exactly as [[STORY-005]] swapped `prompt` → `redacted_prompt` on the `call_openrouter` call.
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && git diff -U3 app/services/query_pipeline.py
  ```
  → the only `-` line in the whole diff is `response=openrouter_result.response,` **inside the `QuerySuccessResponse` constructor**. The identically-spelled line inside `log_query(...)` must be untouched (verify by reading the hunk context, not by grepping the string — both lines read the same).
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest -q
  ```
  → 136 passed, still with zero test edits (Design Note 7).

### Task 4: Add output-redaction tests

- **File**: `tests/test_query_router.py`
- **Action**: UPDATE
- **Implement**: Append at the end of the file. All imports needed already exist (`get_audit_log`, `get_connection`, `hash_prompt`, `OpenRouterResult`, `PiiRedactorError`, `query_pipeline`, `settings` — lines 12-19). Do **not** modify any of the 16 existing tests.

  ```python
  _PII_RESPONSE = "Sure, I will draft a reply to juan@empresa.com for Maria Gomez."
  _REDACTED_RESPONSE = "Sure, I will draft a reply to <EMAIL_ADDRESS> for <PERSON>."
  _CLEAN_PROMPT = "what is the capital of the moon"
  _CLEAN_RESPONSE = "the capital of the moon is cheese city"


  def _openrouter_returning(text: str):
      def _call(prompt, model="gpt-4", api_key=None):
          return OpenRouterResult(response=text, model_used=model, tokens_used=9)

      return _call


  def _boom_on_second_call():
      real_redact = query_pipeline.redact
      calls = []

      def _redact(text):
          calls.append(text)
          if len(calls) == 1:
              return real_redact(text)
          raise PiiRedactorError("PII analysis failed: analyzer exploded on output")

      return _redact


  def _latest_audit_entry():
      with get_connection() as conn:
          row = conn.execute(
              "SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1"
          ).fetchone()
      return get_audit_log(row["id"])


  def test_pii_in_response_is_redacted_before_returning_to_caller(temp_db, monkeypatch):
      monkeypatch.setattr(
          "app.routers.query.call_openrouter", _openrouter_returning(_PII_RESPONSE)
      )

      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": _CLEAN_PROMPT}
      )

      assert response.status_code == 200
      assert response.json()["response"] == _REDACTED_RESPONSE
      assert "juan@empresa.com" not in response.json()["response"]


  def test_audit_row_keeps_raw_response_when_pii_redacted(temp_db, monkeypatch):
      monkeypatch.setattr(
          "app.routers.query.call_openrouter", _openrouter_returning(_PII_RESPONSE)
      )

      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": _CLEAN_PROMPT}
      )
      entry = get_audit_log(response.json()["audit_id"])

      assert entry.response_preview == _PII_RESPONSE
      assert entry.response_hash == hash_prompt(_PII_RESPONSE)
      assert "<EMAIL_ADDRESS>" not in entry.response_preview


  def test_clean_response_returned_unchanged_with_no_telemetry(temp_db, monkeypatch):
      monkeypatch.setattr(
          "app.routers.query.call_openrouter", _openrouter_returning(_CLEAN_RESPONSE)
      )

      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": _CLEAN_PROMPT}
      )
      entry = get_audit_log(response.json()["audit_id"])

      assert response.json()["response"] == _CLEAN_RESPONSE
      assert entry.pii_detected_input is False
      assert entry.pii_detected_output is False
      assert entry.pii_entities is None


  def test_success_path_writes_exactly_one_row_with_output_telemetry(temp_db, monkeypatch):
      monkeypatch.setattr(
          "app.routers.query.call_openrouter", _openrouter_returning(_PII_RESPONSE)
      )

      before = _count_audit_rows()
      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": _CLEAN_PROMPT}
      )
      entry = get_audit_log(response.json()["audit_id"])

      assert response.status_code == 200
      assert _count_audit_rows() == before + 1
      assert entry.pii_detected_input is False
      assert entry.pii_detected_output is True
      assert entry.pii_entities == "EMAIL_ADDRESS,PERSON"


  def test_input_and_output_entities_merged_and_deduplicated(temp_db, monkeypatch):
      monkeypatch.setattr(
          "app.routers.query.call_openrouter", _openrouter_returning(_PII_RESPONSE)
      )

      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
      )
      entry = get_audit_log(response.json()["audit_id"])

      # prompt -> EMAIL_ADDRESS; response -> EMAIL_ADDRESS + PERSON; union is 2 types
      assert entry.pii_detected_input is True
      assert entry.pii_detected_output is True
      assert entry.pii_entities == "EMAIL_ADDRESS,PERSON"


  def test_both_directions_redacted_in_one_request(temp_db, monkeypatch):
      seen = []

      def _call(prompt, model="gpt-4", api_key=None):
          seen.append(prompt)
          return OpenRouterResult(response=_PII_RESPONSE, model_used=model, tokens_used=9)

      monkeypatch.setattr("app.routers.query.call_openrouter", _call)

      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
      )
      entry = get_audit_log(response.json()["audit_id"])

      assert seen == [_REDACTED_PROMPT]
      assert response.json()["response"] == _REDACTED_RESPONSE
      assert entry.prompt_preview == _PII_PROMPT
      assert entry.response_preview == _PII_RESPONSE


  def test_redaction_disabled_returns_raw_response(temp_db, monkeypatch):
      monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)
      monkeypatch.setattr(
          "app.routers.query.call_openrouter", _openrouter_returning(_PII_RESPONSE)
      )

      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": _CLEAN_PROMPT}
      )

      assert response.status_code == 200
      assert response.json()["response"] == _PII_RESPONSE


  def test_output_redaction_failure_returns_500_and_logs_one_row(temp_db, monkeypatch):
      monkeypatch.setattr(query_pipeline, "redact", _boom_on_second_call())
      monkeypatch.setattr(
          "app.routers.query.call_openrouter", _openrouter_returning(_PII_RESPONSE)
      )

      before = _count_audit_rows()
      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": _CLEAN_PROMPT}
      )

      assert response.status_code == 500
      assert _count_audit_rows() == before + 1


  def test_output_redaction_failure_row_keeps_raw_response_and_model(temp_db, monkeypatch):
      monkeypatch.setattr(query_pipeline, "redact", _boom_on_second_call())
      monkeypatch.setattr(
          "app.routers.query.call_openrouter", _openrouter_returning(_PII_RESPONSE)
      )

      client.post("/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT})
      entry = _latest_audit_entry()

      assert entry.success is False
      assert entry.error_message == "PII analysis failed: analyzer exploded on output"
      assert entry.response_preview == _PII_RESPONSE
      assert entry.response_hash == hash_prompt(_PII_RESPONSE)
      assert entry.prompt_preview == _PII_PROMPT
      assert entry.model_used == "gpt-4"
      assert entry.tokens_used == 9
      assert entry.pii_detected_input is True
      assert entry.pii_entities == "EMAIL_ADDRESS"
  ```

  Notes for the implementer:
  - `_count_audit_rows` (line 34), `_PII_PROMPT` / `_REDACTED_PROMPT` (lines 180-181), and the `temp_db` fixture (line 26) already exist — reuse, don't redefine. `_latest_audit_entry()` is new only because the "fetch the newest row" block appears three times in the file already; do not refactor the existing two call sites to use it (keeps the diff additions-only).
  - `_REDACTED_RESPONSE` and `_REDACTED_PROMPT` are literal strings **verified against the real redactor** at the default threshold — the plan author ran each one; they are not guesses.
  - `test_pii_in_response_is_redacted_before_returning_to_caller` is the AC1 test and the most important one here: it asserts on the exact string the end user receives.
  - `test_audit_row_keeps_raw_response_when_pii_redacted` is AC2, the mirror of the existing `test_audit_row_keeps_raw_prompt_when_pii_redacted`.
  - `test_clean_response_returned_unchanged_with_no_telemetry` is AC3.
  - `test_success_path_writes_exactly_one_row_with_output_telemetry` is AC4.
  - `test_input_and_output_entities_merged_and_deduplicated` proves Design Note 3: `EMAIL_ADDRESS` appears on both sides and is stored **once**, sorted. If the implementation used `input_entities + output_entities`, this test fails with `"EMAIL_ADDRESS,EMAIL_ADDRESS,PERSON"`.
  - `test_both_directions_redacted_in_one_request` is the whole-feature test: raw prompt never leaves, redacted response comes back, and both audit previews stay raw — one assertion block covering PRD Section 6 steps 4-10.
  - The two `test_output_redaction_failure_*` tests are Design Note 4: the first proves fail-closed (500, caller gets no raw response) plus exactly one row; the second proves the row is useful and distinguishable from [[STORY-005]]'s input-failure row by carrying `model_used`/`tokens_used`/`response_preview`.
- **Mirror**: `tests/test_query_router.py:236-248` (raw-preview assertion via `get_audit_log`), `:316-332` (failure-row test, including the `ORDER BY id DESC LIMIT 1` fetch and the `entry.success is False` assertions), `:290-300` (the `PII_REDACTION_ENABLED` toggle test).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_query_router.py -v
  ```
  → 25 passed (16 pre-existing unmodified + 9 new).

### Task 5: Full-suite regression, scope check, and latency verification

- **File**: — (no file change)
- **Action**: VERIFY
- **Implement**:
  - Full suite green at **145 passed** (136 baseline + 9 new). Any other number means an existing test changed behaviour.
  - `git diff --name-only` lists **exactly two** files: `app/services/query_pipeline.py`, `tests/test_query_router.py`. Anything else is scope leak — in particular `app/routers/query.py` (already handled by [[STORY-005]]), `schemas.py` ([[STORY-007]]), `audit_logger.py` ([[STORY-004]], done), or `pii_redactor.py` ([[STORY-001]], done).
  - `app/services/duplicate_checker.py` and `app/services/pattern_detector.py` absent from the diff (RF-6).
  - In `git diff app/services/query_pipeline.py`, the **only** removed line is `response=openrouter_result.response,` from the `QuerySuccessResponse` constructor. Read the hunk to confirm the identically-spelled line inside `log_query(...)` survived — the file must still contain **exactly one** `response=openrouter_result.response,` after the change, inside `log_query`, plus one more on the new failure row (two total).
  - `grep -c "prompt=prompt," app/services/query_pipeline.py` → `6` (five from [[STORY-005]] + the new output-failure row), proving every `log_query` call still passes the raw prompt.
  - `git diff tests/test_query_router.py` is additions-only.
  - Confirm `test_full_pipeline_latency_within_budget` still passes both in a full run and when its file runs alone (Design Note 8).
- **Mirror**: [[STORY-005]] plan's Task 5 — the same "prove the change is invisible to everything it shouldn't touch" gate.
- **Validate**:
  ```bash
  cd f:/AI/harness-ai
  .venv/Scripts/python.exe -m pytest
  .venv/Scripts/python.exe -m pytest tests/test_query_router.py::test_full_pipeline_latency_within_budget -v
  .venv/Scripts/python.exe -m pytest tests/test_audit_logger.py tests/test_duplicate_checker.py tests/test_pattern_detector.py tests/test_pii_redactor.py tests/test_integration.py -q
  git diff --name-only
  git diff app/services/query_pipeline.py
  grep -c "prompt=prompt," app/services/query_pipeline.py
  grep -c "response=openrouter_result.response," app/services/query_pipeline.py
  ```
  → full suite 145 passed; the five untouched suites green; first `grep -c` prints `6`, second prints `2`.

---

## End-to-End Tests

Checks for `/implement` to execute:

- [ ] `.venv/Scripts/python.exe -m pytest tests/test_query_router.py -v` → 25 passed (16 pre-existing untouched + 9 new)
- [ ] `.venv/Scripts/python.exe -m pytest` → full suite green, **145 passed** (baseline 136 + 9)
- [ ] `git diff --name-only` → exactly `app/services/query_pipeline.py` and `tests/test_query_router.py`; `routers/query.py`, `audit_logger.py`, `pii_redactor.py`, `schemas.py`, `duplicate_checker.py`, `pattern_detector.py` are **not** listed
- [ ] `git diff tests/test_query_router.py` → additions only, no modified or deleted lines
- [ ] `grep -c "prompt=prompt," app/services/query_pipeline.py` → `6`
- [ ] Behavioural proof of AC1 + AC2 + AC4 + the merge, against the real DB and the real redactor:
  ```bash
  .venv/Scripts/python.exe -c "
  import os
  os.environ.setdefault('OPENROUTER_API_KEY','k'); os.environ.setdefault('ADMIN_TOKEN','t')
  from app.db.database import get_audit_log, get_connection, init_db
  from app.services.openrouter_client import OpenRouterResult
  from app.services.query_pipeline import run_query
  seen = []
  RESP = 'Sure, I will draft a reply to e2e-out@empresa.com for Maria Gomez.'
  def fake(prompt, model='gpt-4', api_key=None):
      seen.append(prompt)
      return OpenRouterResult(response=RESP, model_used=model, tokens_used=9)
  init_db()
  p = 'my email is e2e-out@empresa.com, can you draft a reply?'
  with get_connection() as c:
      before = c.execute('SELECT COUNT(*) AS n FROM audit_logs').fetchone()['n']
  r = run_query(user_id='e2e', prompt=p, device=None, model='gpt-4', openrouter_api_key=None, call_openrouter=fake)
  with get_connection() as c:
      after = c.execute('SELECT COUNT(*) AS n FROM audit_logs').fetchone()['n']
  row = get_audit_log(r.audit_id)
  print('SENT     :', repr(seen[0]))
  print('RETURNED :', repr(r.response))
  print('AUDIT IN :', repr(row.prompt_preview))
  print('AUDIT OUT:', repr(row.response_preview))
  print('TELEMETRY:', row.pii_detected_input, row.pii_detected_output, row.pii_entities)
  assert 'e2e-out@empresa.com' not in seen[0], 'RAW PII REACHED OPENROUTER'
  assert 'e2e-out@empresa.com' not in r.response, 'RAW PII RETURNED TO CALLER'
  assert r.response == 'Sure, I will draft a reply to <EMAIL_ADDRESS> for <PERSON>.'
  assert row.prompt_preview == p and row.response_preview == RESP, 'AUDIT WAS REDACTED'
  assert row.pii_entities == 'EMAIL_ADDRESS,PERSON', 'MERGE/DEDUP WRONG'
  assert after == before + 1, 'NOT EXACTLY ONE AUDIT ROW'
  print('OK')
  "
  ```
  → `SENT` and `RETURNED` both show placeholders, both `AUDIT` lines show the raw text, `TELEMETRY` shows `True True EMAIL_ADDRESS,PERSON`, then `OK`.
- [ ] Audited output-failure proof — force the *second* redact call to fail and confirm the row records the model and the raw response:
  ```bash
  .venv/Scripts/python.exe -c "
  import os
  os.environ.setdefault('OPENROUTER_API_KEY','k'); os.environ.setdefault('ADMIN_TOKEN','t')
  from app.db.database import get_audit_log, get_connection, init_db
  from app.services.openrouter_client import OpenRouterResult
  from app.services.pii_redactor import PiiRedactorError
  import app.services.query_pipeline as qp
  real = qp.redact; calls = []
  def flaky(text):
      calls.append(text)
      if len(calls) == 1: return real(text)
      raise PiiRedactorError('PII analysis failed: output probe')
  qp.redact = flaky
  RESP = 'Sure, I will draft a reply to e2e-fail@empresa.com.'
  init_db()
  p = 'my email is e2e-fail@empresa.com, can you draft a reply?'
  try:
      qp.run_query(user_id='e2e', prompt=p, device=None, model='gpt-4', openrouter_api_key=None,
                   call_openrouter=lambda prompt, model='gpt-4', api_key=None: OpenRouterResult(response=RESP, model_used=model, tokens_used=9))
      raise SystemExit('FAIL: exception did not propagate')
  except PiiRedactorError as exc:
      print('RAISED :', exc)
  with get_connection() as c:
      rid = c.execute(\"SELECT id FROM audit_logs WHERE user_id='e2e' ORDER BY id DESC LIMIT 1\").fetchone()['id']
  row = get_audit_log(rid)
  print('AUDIT  :', row.success, repr(row.response_preview), row.model_used, row.tokens_used, row.pii_detected_input, row.pii_entities)
  assert row.success is False and row.response_preview == RESP and row.model_used == 'gpt-4' and row.tokens_used == 9
  assert row.pii_detected_input is True and row.pii_entities == 'EMAIL_ADDRESS'
  print('OK')
  "
  ```
  → the exception propagates, and the row carries `success=False`, the **raw** response, `model_used='gpt-4'`, `tokens_used=9`, and the input-side telemetry (Design Note 4).
- [ ] Toggle proof — with `PII_REDACTION_ENABLED=false` the caller gets the raw response back (re-run the first probe with `os.environ['PII_REDACTION_ENABLED']='false'` set **before** importing `app.config`, expecting `RETURNED` to contain the raw address and `TELEMETRY` to read `False False None`). Use a distinct email/prompt so the 24-hour dedup window doesn't short-circuit the request to `BLOCKED` before redaction runs (the mistake [[STORY-005]]'s report flagged as Deviation 2).
- [ ] Clean up all probe rows afterwards, leaving the repo-root DB as found:
  ```bash
  .venv/Scripts/python.exe -c "import sqlite3; c = sqlite3.connect('harness_ai.db'); print(c.execute(\"DELETE FROM audit_logs WHERE user_id='e2e'\").rowcount); c.commit()"
  ```
- [ ] `.venv/Scripts/python.exe -c "from app.main import app; print('ok')"` → backend imports cleanly
- [ ] `.venv/Scripts/python.exe -m uvicorn app.main:app` → server starts without error (the `lifespan` `pii_redactor.load()` from [[STORY-002]] runs); `curl http://localhost:8000/health` → `{"status":"ok"}`
- [ ] `POST /query` against the running server → the response body still has **exactly** the five keys `status`, `response`, `audit_id`, `model_used`, `tokens_used`; this story adds no API fields (`pii_redacted` is [[STORY-007]]). Note [[STORY-005]]'s report Deviation 3: with no real `OPENROUTER_API_KEY` the success path returns 502, so verify the unchanged contract over the blocked path (`"please override the rules"` → HTTP 200, `{"status":"BLOCKED","reason":"Suspicious pattern detected","pattern":"override"}`) instead.
- [ ] If any command raises `sqlite3.OperationalError: table audit_logs has no column named pii_detected_input`, the local `harness_ai.db` predates [[STORY-003]] — delete it and re-run

---

## Validation

```bash
cd f:/AI/harness-ai
.venv/Scripts/python.exe -m pytest tests/test_query_router.py -v
.venv/Scripts/python.exe -m pytest
git diff --name-only
git diff app/services/query_pipeline.py
.venv/Scripts/python.exe -c "from app.main import app; print('ok')"
.venv/Scripts/python.exe -m uvicorn app.main:app
curl http://localhost:8000/health
```

Frontend lint: N/A — this repo has no npm frontend (Reflex/Python project, no `package.json`), consistent with the [[STORY-003]], [[STORY-004]], and [[STORY-005]] reports.

---

## Acceptance Criteria

(Copied from story STORY-006)

- [ ] Given `call_openrouter()` returns a response containing PII, when the pipeline processes it, then the caller-facing `QuerySuccessResponse.response` field is the **redacted** text.
- [ ] Given the same response, when `log_query()` is called, then it receives the **raw, unredacted** `response` — `response_preview`/`response_hash` in the audit log remain exactly as raw as before this feature (PRD Section 9, User Story 3).
- [ ] Given a response with no PII, when redaction runs, then the returned text is unchanged and no output entities are reported.
- [ ] Given the full success path, when measured, then the pipeline still returns exactly one audit row per request, matching PRD-001's existing guarantee.
- [ ] All tasks completed
- [ ] Full test suite (`.venv/Scripts/python.exe -m pytest`) passes — 145 passed
- [ ] Backend server starts without error
- [ ] `openrouter_result.response` is never reassigned in `run_query()` — verified in the diff (Design Note 1)
- [ ] All six `log_query(...)` calls pass `prompt=prompt` (raw), and both response-bearing calls pass `response=openrouter_result.response` (raw) — RF-7
- [ ] `pii_detected_input`/`pii_detected_output`/`pii_entities` are written on the success row, with the entity list deduplicated and sorted (Design Note 3)
- [ ] A `PiiRedactorError` on the response produces exactly one audit row with `success=False`, the raw prompt **and** raw response, `model_used`/`tokens_used` from the OpenRouter result, and a self-describing `error_message`; the router returns 500 with no code change to `app/routers/query.py` (Design Note 4)
- [ ] `QuerySuccessResponse` gains no new fields — `pii_redacted`/`pii_entities_masked` remain [[STORY-007]]'s scope (Design Note 5)
- [ ] `app/services/duplicate_checker.py` and `app/services/pattern_detector.py` untouched (RF-6)
- [ ] No direct Presidio import in `query_pipeline.py` — the adapter boundary in `pii_redactor.py` stays intact (PRD Section 6)
- [ ] Only `app/services/query_pipeline.py` and `tests/test_query_router.py` changed
- [ ] Follows existing patterns (new-name binding for redacted text, log-then-bare-`raise` failure blocks, raw text at every `log_query` call site, `temp_db` + `TestClient` + string-target monkeypatching in tests)
