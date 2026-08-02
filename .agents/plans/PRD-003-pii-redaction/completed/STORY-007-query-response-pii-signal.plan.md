---
story: STORY-007
prd: PRD-003
slug: query-response-pii-signal
title: "POST /query response: pii_redacted signal field"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-003-pii-redaction        # all stories commit here, no per-story branch
created: 2026-08-01
---

# Plan: POST /query response — `pii_redacted` signal field

## Summary

Make redaction *visible* to the caller without making it *readable*. [[STORY-005]] and [[STORY-006]] closed both directions of the masking loop, and by the end of [[STORY-006]] `run_query()` already holds everything this story needs: `input_entities` (line 57) and `output_entities` (line 84). Nothing new is detected, computed, or analyzed here — this story only **surfaces** what is already in scope.

Two additive fields land on `QuerySuccessResponse` (`app/models/schemas.py:14-19`): `pii_redacted: bool = False` and `pii_entities_masked: List[str] = []`, matching PRD Section 10's example shape byte-for-byte. `run_query()` populates them from the same merged entity list it already passes to `log_query()`.

The one real design decision is Design Note 1: **hoist** the merge expression `sorted(set(input_entities) | set(output_entities))` — currently inlined at `query_pipeline.py:110` — into a local `masked_entities`, and feed *both* the audit column and the API response from that single name. The audit telemetry ([[STORY-004]]) and the API signal (this story) are the same fact told to two audiences; computing it twice invites the two to drift silently, and [[STORY-009]] will expose the audit side through `/audit` where a mismatch would be visible but unexplainable.

Everything else is deliberately *not* touched. `QueryRequest` gains nothing (AC4 — the whole point of PRD User Story 5). The two BLOCKED response models gain nothing: those paths `return` before any `redact()` call ever runs, so there is no signal to report (Design Note 4). `chat_ui/chat_ui/state.py` is untouched — chat-UI surfacing of redaction is explicitly deferred in PRD Section 13.

The visible cost is two existing exact-dict assertions that must be updated on purpose — `tests/test_schemas.py:39-45` and `tests/test_query_router.py:90-96`. [[STORY-006]]'s plan (Design Note 5) named this in advance as this story's job. They are the *only* two; every other success assertion in the suite is key-by-key and stays untouched (Design Note 3).

## User Story

As an integrating developer
I want the `POST /query` success response to carry a lightweight signal that redaction occurred
So that callers/UI can surface it without seeing the underlying PII, and with zero changes to the existing request contract (PRD User Story 5, RF-9, Section 10)

## Story Reference

- Story file: `.agents/stories/PRD-003-pii-redaction/STORY-007-query-response-pii-signal.md`
- PRD: `.agents/PRDs/PRD-003-pii-redaction/PRD.md` — Section 10 (`POST /query` — response), User Story 5, RF-9, Section 12 Phase 2

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | `app/models/schemas.py`, `app/services/query_pipeline.py`, `tests/test_schemas.py`, `tests/test_query_router.py` |
| Story | STORY-007 |
| PRD | PRD-003 |
| Epic Branch | `epic/PRD-003-pii-redaction` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` does not exist in this repository (verified — the directory is absent), the story's `skills:` frontmatter field is `[]`, and PRD Section 15 states it explicitly ("Skills referenced: None"). Same finding as the [[STORY-001]] through [[STORY-006]] plans.

---

## Dependency Check

| Dependency | Status | Verified |
|---|---|---|
| [[STORY-006]] — Redact model response before returning to caller | ✅ done (`87c7ea8`) | `redacted_response, output_entities = redact(openrouter_result.response)` at `app/services/query_pipeline.py:84`; merged entity expression already present at `:110` |

The single `depends_on` entry is `done` — no blocker, no user confirmation needed. Transitively: [[STORY-005]] (`c69a656`) put `input_entities` in scope at `:57`; [[STORY-004]] (`1347e53`) established the list-of-`str` entity convention; [[STORY-003]] (`c8b1195`) supplied the DB columns.

This story `blocks: [STORY-010]` (end-to-end integration suite), which will assert the full contract including these two fields.

---

## Patterns to Follow

### The schema this story extends

```python
# SOURCE: app/models/schemas.py:1-19
from typing import List, Literal, Optional, Union

from pydantic import BaseModel


class QueryRequest(BaseModel):
    user_id: str
    prompt: str
    device: Optional[str] = None
    model: str = "gpt-4"
    openrouter_api_key: Optional[str] = None


class QuerySuccessResponse(BaseModel):
    status: Literal["SUCCESS"] = "SUCCESS"
    response: str
    audit_id: int
    model_used: str
    tokens_used: int
```

`List` is **already imported** on line 1 (used by `AuditResponse`/`StatsResponse`) — no import edit is needed. The file uses plain `BaseModel` with bare-annotation defaults throughout; `Field(...)` is never imported and must not be introduced here (Design Note 2). `QueryRequest` is the class this story must leave byte-for-byte identical (AC4).

### The values this story publishes — already computed

```python
# SOURCE: app/services/query_pipeline.py:56-57
    try:
        redacted_prompt, input_entities = redact(prompt)
```

```python
# SOURCE: app/services/query_pipeline.py:83-84
    try:
        redacted_response, output_entities = redact(openrouter_result.response)
```

```python
# SOURCE: app/services/query_pipeline.py:100-118
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

    return QuerySuccessResponse(
        response=redacted_response,
        audit_id=audit_id,
        model_used=openrouter_result.model_used,
        tokens_used=openrouter_result.tokens_used,
    )
```

Line 110 is the expression this story hoists (Design Note 1); lines 113-118 are the constructor it extends. `prompt=prompt` and `response=openrouter_result.response` remain raw and untouched, as at every other call site — RF-7 is unaffected by this story.

### `redact()`'s tuple contract — why `[]` is always safe

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

Always a `list[str]`, never `None`, already sorted-and-unique. So `pii_entities_masked` never needs a `None` guard, and AC2 (`false` / `[]` when nothing detected) is guaranteed by the callee — this story only has to not interfere.

### Exact-dict schema assertion (the pattern the two updated tests follow)

```python
# SOURCE: tests/test_schemas.py:32-45
def test_query_success_response_shape():
    response = QuerySuccessResponse(
        response="La respuesta del modelo",
        audit_id=1,
        model_used="gpt-4",
        tokens_used=45,
    )
    assert response.model_dump() == {
        "status": "SUCCESS",
        "response": "La respuesta del modelo",
        "audit_id": 1,
        "model_used": "gpt-4",
        "tokens_used": 45,
    }
```

Whole-dict equality, not key-by-key — which is exactly why it is one of the two tests this story must update, and exactly why it is worth keeping in that form (it fails loudly if a *future* story adds a field silently).

### HTTP-level pipeline tests with a monkeypatched OpenRouter

```python
# SOURCE: tests/test_query_router.py:184-189
def _capturing_openrouter(seen: list):
    def _call(prompt, model="gpt-4", api_key=None):
        seen.append(prompt)
        return OpenRouterResult(response="drafted", model_used=model, tokens_used=9)

    return _call
```

```python
# SOURCE: tests/test_query_router.py:341-345
def _openrouter_returning(text: str):
    def _call(prompt, model="gpt-4", api_key=None):
        return OpenRouterResult(response=text, model_used=model, tokens_used=9)

    return _call
```

Every pipeline test: `temp_db` fixture (fresh SQLite per test, so the 24-hour dedup window never leaks across tests) → patch `"app.routers.query.call_openrouter"` (the router's import site) → `client.post("/query", ...)` → assert on the body and/or the fetched `AuditLog`. This story's tests are body-only variants of the same shape, reusing `_openrouter_returning` and the existing string constants.

### Entity-string constants already verified against the real redactor

```python
# SOURCE: tests/test_query_router.py:180-181, 335-336
_PII_PROMPT = "my email is juan@empresa.com, can you draft a reply?"
_REDACTED_PROMPT = "my email is <EMAIL_ADDRESS>, can you draft a reply?"
_PII_RESPONSE = "Sure, I will draft a reply to juan@empresa.com for Maria Gomez."
_REDACTED_RESPONSE = "Sure, I will draft a reply to <EMAIL_ADDRESS> for <PERSON>."
```

`_PII_PROMPT` yields `["EMAIL_ADDRESS"]`; `_PII_RESPONSE` yields `["EMAIL_ADDRESS", "PERSON"]` — pinned today by the passing `test_input_and_output_entities_merged_and_deduplicated` (`tests/test_query_router.py:432-445`). Reuse these constants; do not invent new PII strings whose detection is unproven.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/models/schemas.py` | UPDATE | Add `pii_redacted: bool = False` and `pii_entities_masked: List[str] = []` to `QuerySuccessResponse` |
| `app/services/query_pipeline.py` | UPDATE | Hoist the merged entity list to `masked_entities`; pass the two new fields to `QuerySuccessResponse` |
| `tests/test_schemas.py` | UPDATE | Update the exact-dict success assertion; add 3 schema-contract tests (incl. AC4's `QueryRequest`-unchanged test) |
| `tests/test_query_router.py` | UPDATE | Update the exact-dict body assertion; add 7 HTTP-level signal tests |

**Explicitly NOT touched:**

- `app/models/schemas.py` → `QueryRequest` — **AC4**. No new required field, no new optional field, no reordering, no comment. The class must be byte-for-byte identical in `git diff`
- `app/models/schemas.py` → `QueryBlockedDuplicateResponse` / `QueryBlockedSuspiciousResponse` — both blocked paths `return` at `query_pipeline.py:37` / `:51`, before `redact()` is ever called, so there is no redaction to signal (Design Note 4; story Technical Note 2; PRD Section 10 documents the field only on the success shape)
- `app/routers/query.py` — `response_model=QueryResponse` is the same `Union` alias (`schemas.py:34-36`), which picks up the extended member automatically. Verified empirically (Design Note 5)
- `app/services/pii_redactor.py`, `app/services/audit_logger.py`, `app/db/models.py` — this story adds no detection, no column, no logger parameter
- `app/services/duplicate_checker.py`, `app/services/pattern_detector.py` — untouched, byte-for-byte (RF-6). Must be absent from `git diff --name-only`
- `chat_ui/chat_ui/state.py` — builds its bubble from `result.response` only (`state.py:72-73`); the new fields are ignored, which is the additive contract working. Chat-UI surfacing of redaction is deferred (PRD Section 13). `tests/test_chat_state.py:222-224` constructs `QuerySuccessResponse` without the new fields and keeps passing on their defaults
- `/audit` and `/stats` exposure of PII telemetry — [[STORY-009]]
- `tests/test_integration.py`, `tests/test_audit_logger.py`, `tests/test_duplicate_checker.py`, `tests/test_pattern_detector.py`, `tests/test_pii_redactor.py`, `tests/test_chat_state.py` — must all pass **unmodified** (Design Note 3)

---

## Design Notes (decisions worth stating up front)

1. **Hoist the merge into `masked_entities`; feed the audit column and the API response from the same name.** The story's Technical Notes describe the response fields as "`pii_redacted = bool(input_entities or output_entities)`, `pii_entities_masked` = deduplicated union of both lists" — which is, character for character, the value already inlined at `query_pipeline.py:110` for `log_query`. Writing it twice creates two expressions that must stay equal forever with nothing enforcing it: a later change to one (a filter, a cap, a rename) leaves `/audit` and the `POST /query` body disagreeing about the same request. [[STORY-009]] will expose the audit side over HTTP, making such a drift *visible* to integrators but not *explicable*. So:

   ```python
   masked_entities = sorted(set(input_entities) | set(output_entities))
   ```

   is computed once before `log_query(...)`, passed as `pii_entities=masked_entities`, and reused as `pii_entities_masked=masked_entities`. `pii_redacted` becomes `bool(masked_entities)` — provably identical to the story's `bool(input_entities or output_entities)`, since the union is empty exactly when both inputs are empty. This is the only line of existing code this story modifies, and Task 6 pins the equivalence with a test that reads the audit row and the response body in the same request.

   `pii_detected_input=bool(input_entities)` and `pii_detected_output=bool(output_entities)` stay as they are — those are per-direction facts, not the merge, and [[STORY-004]] made them separate columns on purpose.

2. **`pii_entities_masked: List[str] = []` — the bare mutable default is correct here, not a bug.** In Pydantic v2 a mutable default is deep-copied per model instance rather than shared, so the classic Python foot-gun does not apply. Verified on this repo's exact version (`pydantic 2.13.4`): mutating `a.pii_entities_masked` left a second instance's list `[]`. `Field(default_factory=list)` would be equally correct but introduces the first `Field` import in a file that has never needed one, and diverges from the bare-default style used by all five existing models (`schemas.py:9-11`, `:15`). Match PRD Section 10's shape and the file's own convention.

3. **Exactly two existing assertions change — identified by inspection, not by running and seeing what breaks.** Every success-path assertion in the suite was reviewed:

   | Location | Form | Effect |
   |---|---|---|
   | `tests/test_schemas.py:39-45` | `model_dump() == {5 keys}` | ❌ **must update** — add the 2 keys |
   | `tests/test_query_router.py:90-96` | `body == {5 keys}` | ❌ **must update** — add the 2 keys |
   | `tests/test_query_router.py:110-114`, `:128-132` | `json() == {...}` on **BLOCKED** | ✅ unaffected — blocked shapes unchanged (Design Note 4) |
   | `tests/test_chat_state.py:302-306` | `json() == {...}` on **BLOCKED** | ✅ unaffected |
   | `tests/test_integration.py:50-57` | key-by-key (`body["status"]`, `body["response"]`, …) | ✅ unaffected — additive fields ignored |
   | all other `response.json()["response"]` / `["audit_id"]` assertions | single-key | ✅ unaffected |

   Both updates are *deliberate contract changes*, pre-authorized by [[STORY-006]]'s plan Design Note 5. Keep both as whole-dict equality afterwards — that strictness is what makes AC3 auditable, and it is the tripwire that will catch the next silently-added field.

4. **BLOCKED responses carry no signal, and that is a decision, not an omission.** `run_query()` returns `QueryBlockedDuplicateResponse` at line 37 and `QueryBlockedSuspiciousResponse` at line 51 — both **before** `redact()` at line 57. No analysis ran; no PII was masked; `pii_redacted: false` would be a claim the system never checked, and `true` would be false. Adding the fields there would also force edits to two more exact-dict tests for zero information gain. PRD Section 10 documents the fields only under "response (success, redaction occurred)". A test in Task 6 pins the blocked shapes as *unchanged*, so this stays a decision on the record rather than an oversight someone later "fixes".

5. **The `Union` response model needs no router change — verified, not assumed.** `app/routers/query.py:12` declares `response_model=QueryResponse`, the `Union` alias at `schemas.py:34-36`. A standalone probe on this repo's exact stack (`fastapi 0.139.0`, `pydantic 2.13.4`), mirroring that structure, confirmed all three behaviours this story depends on:

   ```
   SUCCESS + PII : {'status': 'SUCCESS', 'response': ..., 'audit_id': 1, 'model_used': 'gpt-4',
                    'tokens_used': 45, 'pii_redacted': True, 'pii_entities_masked': ['EMAIL_ADDRESS']}
   SUCCESS clean : {..., 'pii_redacted': False, 'pii_entities_masked': []}
   BLOCKED       : {'status': 'BLOCKED', 'reason': ..., 'first_query_at': 'ts'}
   ```

   Three facts land: (a) Pydantic v2 smart-union picks the success member and serializes the new fields; (b) defaults are **emitted**, not omitted — the route sets no `response_model_exclude_unset`, so `pii_redacted: false` / `pii_entities_masked: []` are always present, which AC2 requires (the fields must be *present and false*, not *absent*); (c) the BLOCKED arm is byte-identical. No `app/routers/query.py` edit.

6. **Failure paths need nothing.** `PiiRedactorError` and `OpenRouterError` propagate as bare `raise` after their audit rows are written (`query_pipeline.py:66`, `:81`, `:98`); no `QuerySuccessResponse` is ever constructed on those paths, and the router turns them into HTTP 500/502 with no body from these models. The new fields are unreachable there by construction — no defensive code, no test.

7. **"Additive only" is testable at the value level, not just the key level (AC3).** An integration that ignores unknown fields is unaffected *iff* the five pre-existing keys keep their exact prior values. Task 6's `test_existing_success_fields_unchanged_alongside_new_signal` asserts that on a redacted request — `status`, `audit_id`, `model_used`, `tokens_used` unchanged, and `response` still the redacted text from [[STORY-006]]. Merely asserting the two new keys exist would not prove additivity.

8. **`pii_entities_masked` is sorted, matching the audit column exactly.** `redact()` returns `sorted({...})` (`pii_redactor.py:73`) and [[STORY-006]] sorts the union for the audit row (its Design Note 3). Hoisting per Design Note 1 makes the response inherit that ordering for free — so `body["pii_entities_masked"] == entry.pii_entities.split(",")` is a meaningful assertion (Task 6) rather than an accident of dict ordering. PRD Section 10's `["EMAIL_ADDRESS"]` is consistent with this.

9. **No latency change.** This story adds no `redact()` call — it publishes values already computed. `test_full_pipeline_latency_within_budget` (`tests/test_query_router.py:159-177`) is unaffected and must not be touched or re-budgeted.

10. **Use `.venv/Scripts/python.exe` for every command.** [[STORY-003]]'s report (Deviation 1) recorded that bare `python` on this machine resolves to a global Python 3.13 without `presidio-analyzer`, producing collection errors in every module that transitively imports `app.main` → `app.services.pii_redactor`. Environment mismatch, not a code defect. All commands below name the venv interpreter explicitly.

11. **Baseline to preserve: 145 passed** (`.venv/Scripts/python.exe -m pytest`, measured on this branch immediately before planning — matches [[STORY-006]]'s report). Target after this story: **155 passed** (145 + 10 new; the 2 updated tests are modified, not added).

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add the two signal fields to `QuerySuccessResponse`

- **File**: `app/models/schemas.py`
- **Action**: UPDATE
- **Implement**: Append two fields to `QuerySuccessResponse` (lines 14-19). Change nothing else in the file:
  ```python
  class QuerySuccessResponse(BaseModel):
      status: Literal["SUCCESS"] = "SUCCESS"
      response: str
      audit_id: int
      model_used: str
      tokens_used: int
      pii_redacted: bool = False
      pii_entities_masked: List[str] = []
  ```
  The five existing lines are unchanged and stay in order; the two new lines go **after** `tokens_used`, matching PRD Section 10's key order.
  - Both fields have defaults, so every existing construction site keeps working unmodified — `query_pipeline.py:113`, `tests/test_chat_state.py:222`, `tests/test_schemas.py:33`.
  - `List` is already imported (`schemas.py:1`). **Do not** add a `Field` import or `default_factory` (Design Note 2).
  - **Do not** touch `QueryRequest` (AC4), `QueryBlockedDuplicateResponse`, or `QueryBlockedSuspiciousResponse` (Design Note 4).
- **Mirror**: `app/models/schemas.py:39-47` (`AuditQueryEntry`) — bare annotations with inline defaults, `List[...]`/`Optional[...]` from the module-level `typing` import, no `Field`.
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -c "
  import os
  os.environ.setdefault('OPENROUTER_API_KEY','k'); os.environ.setdefault('ADMIN_TOKEN','t')
  from app.models.schemas import QueryRequest, QuerySuccessResponse
  print(list(QuerySuccessResponse.model_fields))
  print(sorted(QueryRequest.model_fields))
  r = QuerySuccessResponse(response='x', audit_id=1, model_used='gpt-4', tokens_used=1)
  print(r.pii_redacted, r.pii_entities_masked)
  assert sorted(QueryRequest.model_fields) == ['device','model','openrouter_api_key','prompt','user_id']
  "
  ```
  → success fields end with `'pii_redacted', 'pii_entities_masked'`; request fields unchanged; defaults print `False []`.

### Task 2: Hoist the merged entity list in `run_query()`

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**: Introduce `masked_entities` immediately before the success `log_query(...)` call (currently line 100) and use it as the `pii_entities` argument, replacing the inlined expression on line 110:
  ```python
      masked_entities = sorted(set(input_entities) | set(output_entities))

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
          pii_entities=masked_entities,
      )
  ```
  - The expression is **identical** to what line 110 computes today — this is a pure extraction, no behaviour change. The suite must stay at 145 passed after this task alone.
  - `pii_detected_input` / `pii_detected_output` keep their per-direction expressions (Design Note 1) — do not rewrite them in terms of `masked_entities`.
  - `prompt=prompt` and `response=openrouter_result.response` must remain untouched (RF-7) — they must not appear as modified lines in `git diff`.
  - Do **not** hoist anything into the two failure blocks (`:85-98`, `:72-81`); `output_entities` does not exist there (Design Note 6).
- **Mirror**: `app/services/query_pipeline.py:56-57`, `:83-84` — the file's existing habit of binding redaction results to named locals before use.
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest -q
  ```
  → **145 passed**, with zero test edits. A pure refactor that changes a test result is not a pure refactor — stop and re-read the diff.

### Task 3: Populate the signal on the success response

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**: Append two arguments to the final `QuerySuccessResponse(...)` (currently lines 113-118):
  ```python
      return QuerySuccessResponse(
          response=redacted_response,
          audit_id=audit_id,
          model_used=openrouter_result.model_used,
          tokens_used=openrouter_result.tokens_used,
          pii_redacted=bool(masked_entities),
          pii_entities_masked=masked_entities,
      )
  ```
  - `response=redacted_response` from [[STORY-006]] is unchanged — this story does not touch what the caller reads, only what it is told about it.
  - `bool(masked_entities)`, not `bool(input_entities or output_entities)` — provably equal, single source (Design Note 1).
  - Pass `masked_entities` directly; no `list(...)` copy. Pydantic v2 validates and constructs its own list for the field, and the local is never mutated afterwards.
  - No change to `app/routers/query.py` (Design Note 5).
- **Mirror**: `app/services/query_pipeline.py:100-111` — same append-keyword-arguments-only edit [[STORY-006]] made to `log_query`.
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest -q
  ```
  → **143 passed, 2 failed** — and *exactly* those two: `test_query_success_response_shape` and `test_clean_prompt_success_returns_expected_shape_and_logs_row`, both failing on the two extra keys (Design Note 3). Any third failure means a non-additive change slipped in; investigate before continuing. Tasks 5 and 6 fix these two by design.

### Task 4: Verify the request contract and blocked shapes are untouched

- **File**: — (no file change)
- **Action**: VERIFY
- **Implement**: Prove AC4 and Design Note 4 from the diff before writing tests that assert them:
  - `git diff app/models/schemas.py` shows **only** two added lines, both inside `QuerySuccessResponse`. No `-` lines anywhere in the file.
  - `QueryRequest`, `QueryBlockedDuplicateResponse`, `QueryBlockedSuspiciousResponse`, `QueryResponse`, `AuditQueryEntry`, `AuditResponse`, `StatsResponse` are absent from the diff hunks.
  - `git diff app/services/query_pipeline.py` shows exactly one `-` line (`pii_entities=sorted(set(input_entities) | set(output_entities)),`) plus additions.
- **Mirror**: [[STORY-006]] plan Task 5 — the same "prove the change is invisible to everything it shouldn't touch" gate, applied to the request contract instead of the audit trail.
- **Validate**:
  ```bash
  cd f:/AI/harness-ai
  git diff app/models/schemas.py
  git diff app/services/query_pipeline.py
  git diff --name-only
  grep -c "prompt=prompt," app/services/query_pipeline.py
  grep -c "response=openrouter_result.response," app/services/query_pipeline.py
  ```
  → `git diff --name-only` lists only `app/models/schemas.py` and `app/services/query_pipeline.py` (tests arrive in Tasks 5-6); the two `grep -c` print `6` and `2` respectively, unchanged from [[STORY-006]].

### Task 5: Update and extend the schema tests

- **File**: `tests/test_schemas.py`
- **Action**: UPDATE
- **Implement**: One deliberate edit plus three additions. All imports already exist (lines 1-12).

  **(a)** Update the exact-dict assertion in `test_query_success_response_shape` (lines 39-45) — the constructor call above it stays unchanged, proving the defaults are what appear:
  ```python
      assert response.model_dump() == {
          "status": "SUCCESS",
          "response": "La respuesta del modelo",
          "audit_id": 1,
          "model_used": "gpt-4",
          "tokens_used": 45,
          "pii_redacted": False,
          "pii_entities_masked": [],
      }
  ```

  **(b)** Append three tests at the end of the file:
  ```python
  def test_query_success_response_with_pii_signal_shape():
      response = QuerySuccessResponse(
          response="Sure, I'll draft a reply to <EMAIL_ADDRESS>.",
          audit_id=1,
          model_used="gpt-4",
          tokens_used=45,
          pii_redacted=True,
          pii_entities_masked=["EMAIL_ADDRESS"],
      )
      assert response.model_dump() == {
          "status": "SUCCESS",
          "response": "Sure, I'll draft a reply to <EMAIL_ADDRESS>.",
          "audit_id": 1,
          "model_used": "gpt-4",
          "tokens_used": 45,
          "pii_redacted": True,
          "pii_entities_masked": ["EMAIL_ADDRESS"],
      }


  def test_query_success_response_pii_defaults_are_not_shared_between_instances():
      first = QuerySuccessResponse(
          response="a", audit_id=1, model_used="gpt-4", tokens_used=1
      )
      second = QuerySuccessResponse(
          response="b", audit_id=2, model_used="gpt-4", tokens_used=1
      )
      first.pii_entities_masked.append("PERSON")

      assert second.pii_entities_masked == []


  def test_query_request_contract_is_unchanged():
      assert sorted(QueryRequest.model_fields) == [
          "device",
          "model",
          "openrouter_api_key",
          "prompt",
          "user_id",
      ]
      assert QueryRequest.model_fields["user_id"].is_required()
      assert QueryRequest.model_fields["prompt"].is_required()
  ```

  Notes for the implementer:
  - `test_query_success_response_with_pii_signal_shape` is the schema half of AC1, and its body is PRD Section 10's example shape.
  - `test_query_success_response_pii_defaults_are_not_shared_between_instances` pins Design Note 2. It is cheap insurance: if a future refactor changes the field to a genuinely shared mutable, this fails immediately instead of leaking one caller's entity list into another's response.
  - `test_query_request_contract_is_unchanged` is **AC4** — the only mechanical test of "the request contract did not change". Verified working on `pydantic 2.13.4` (class-level `model_fields` access is not deprecated; instance-level is).
  - Do not modify the other five existing tests in this file.
- **Mirror**: `tests/test_schemas.py:32-45` (exact-dict success assertion), `:60-69` (a second shape test for the same family of models).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_schemas.py -v
  ```
  → 9 passed (6 pre-existing, 1 of them updated + 3 new).

### Task 6: Update and extend the router tests

- **File**: `tests/test_query_router.py`
- **Action**: UPDATE
- **Implement**: One deliberate edit plus seven additions. All imports and helpers already exist (`get_audit_log`, `settings`, `query_pipeline`, `_openrouter_returning`, `_capturing_openrouter`, `_PII_PROMPT`, `_REDACTED_PROMPT`, `_PII_RESPONSE`, `_REDACTED_RESPONSE`, `_CLEAN_PROMPT`, `_CLEAN_RESPONSE`, `temp_db`).

  **(a)** Update the exact-dict body assertion in `test_clean_prompt_success_returns_expected_shape_and_logs_row` (lines 90-96). Keep whole-dict equality:
  ```python
      assert body == {
          "status": "SUCCESS",
          "response": "Hi there!",
          "audit_id": body["audit_id"],
          "model_used": "gpt-4",
          "tokens_used": 12,
          "pii_redacted": False,
          "pii_entities_masked": [],
      }
  ```

  **(b)** Append seven tests at the end of the file:
  ```python
  def test_pii_in_prompt_sets_redaction_signal(temp_db, monkeypatch):
      monkeypatch.setattr("app.routers.query.call_openrouter", _capturing_openrouter([]))

      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
      )
      body = response.json()

      assert body["pii_redacted"] is True
      assert body["pii_entities_masked"] == ["EMAIL_ADDRESS"]


  def test_pii_in_response_sets_redaction_signal(temp_db, monkeypatch):
      monkeypatch.setattr(
          "app.routers.query.call_openrouter", _openrouter_returning(_PII_RESPONSE)
      )

      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": _CLEAN_PROMPT}
      )
      body = response.json()

      assert body["pii_redacted"] is True
      assert body["pii_entities_masked"] == ["EMAIL_ADDRESS", "PERSON"]


  def test_signal_entities_merged_and_deduplicated_across_directions(temp_db, monkeypatch):
      monkeypatch.setattr(
          "app.routers.query.call_openrouter", _openrouter_returning(_PII_RESPONSE)
      )

      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
      )
      body = response.json()

      # prompt -> EMAIL_ADDRESS; response -> EMAIL_ADDRESS + PERSON; union is 2 types
      assert body["pii_redacted"] is True
      assert body["pii_entities_masked"] == ["EMAIL_ADDRESS", "PERSON"]


  def test_signal_matches_audit_row_entities(temp_db, monkeypatch):
      monkeypatch.setattr(
          "app.routers.query.call_openrouter", _openrouter_returning(_PII_RESPONSE)
      )

      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
      )
      body = response.json()
      entry = get_audit_log(body["audit_id"])

      assert body["pii_entities_masked"] == entry.pii_entities.split(",")
      assert body["pii_redacted"] is (entry.pii_detected_input or entry.pii_detected_output)


  def test_clean_query_reports_no_redaction(temp_db, monkeypatch):
      monkeypatch.setattr(
          "app.routers.query.call_openrouter", _openrouter_returning(_CLEAN_RESPONSE)
      )

      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": _CLEAN_PROMPT}
      )
      body = response.json()

      assert body["pii_redacted"] is False
      assert body["pii_entities_masked"] == []


  def test_redaction_disabled_reports_no_redaction(temp_db, monkeypatch):
      monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)
      monkeypatch.setattr(
          "app.routers.query.call_openrouter", _openrouter_returning(_PII_RESPONSE)
      )

      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
      )
      body = response.json()

      assert body["response"] == _PII_RESPONSE
      assert body["pii_redacted"] is False
      assert body["pii_entities_masked"] == []


  def test_existing_success_fields_unchanged_alongside_new_signal(temp_db, monkeypatch):
      seen = []
      monkeypatch.setattr("app.routers.query.call_openrouter", _capturing_openrouter(seen))

      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
      )
      body = response.json()

      assert seen == [_REDACTED_PROMPT]
      assert body == {
          "status": "SUCCESS",
          "response": "drafted",
          "audit_id": body["audit_id"],
          "model_used": "gpt-4",
          "tokens_used": 9,
          "pii_redacted": True,
          "pii_entities_masked": ["EMAIL_ADDRESS"],
      }
      assert isinstance(body["audit_id"], int)
  ```

  Notes for the implementer:
  - `test_pii_in_prompt_sets_redaction_signal` and `test_pii_in_response_sets_redaction_signal` are **AC1** from each direction; `test_signal_entities_merged_and_deduplicated_across_directions` is AC1 with both at once, and fails with `["EMAIL_ADDRESS", "EMAIL_ADDRESS", "PERSON"]` if the union in Task 2 were ever replaced by concatenation.
  - `test_signal_matches_audit_row_entities` pins Design Note 1 — the audit column and the API field are the same list, in the same order (Design Note 8). This is the test that makes the hoist load-bearing rather than cosmetic.
  - `test_clean_query_reports_no_redaction` is **AC2**; note it asserts the keys are **present and false**, not absent (Design Note 5b).
  - `test_redaction_disabled_reports_no_redaction` covers the `PII_REDACTION_ENABLED=false` operational path: raw text through, and — importantly — the signal must not claim redaction happened.
  - `test_existing_success_fields_unchanged_alongside_new_signal` is **AC3** at the value level (Design Note 7): all five pre-existing keys hold exactly the values they held before this story, on a request where redaction *did* occur.
  - `_capturing_openrouter([])` returns `"drafted"` (line 187), which the redactor leaves untouched — so that test's `pii_entities_masked` is the prompt side only.
  - `test_blocked_*` shapes need no new test: the two existing exact-dict BLOCKED assertions (lines 110-114, 128-132) already fail if the fields leak onto those models, and they must stay **unmodified** — that is the AC-level proof for Design Note 4.
  - Do not modify any of the other 24 existing tests, and do not touch `test_full_pipeline_latency_within_budget` (Design Note 9).
- **Mirror**: `tests/test_query_router.py:432-445` (`test_input_and_output_entities_merged_and_deduplicated`) — the audit-side twin of the merge test; `:398-411` (clean-path telemetry assertions); `:290-300` (the `PII_REDACTION_ENABLED` toggle test).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_query_router.py -v
  ```
  → 32 passed (25 pre-existing, 1 of them updated + 7 new).

### Task 7: Full-suite regression and scope check

- **File**: — (no file change)
- **Action**: VERIFY
- **Implement**:
  - Full suite green at **155 passed** (145 baseline + 10 new). Any other number means something outside the two intended assertions changed behaviour.
  - `git diff --name-only` lists **exactly four** files: `app/models/schemas.py`, `app/services/query_pipeline.py`, `tests/test_schemas.py`, `tests/test_query_router.py`. Anything else is scope leak — in particular `app/routers/query.py` (Design Note 5), `audit_logger.py`, `pii_redactor.py`, `db/models.py`, or `chat_ui/chat_ui/state.py`.
  - `app/services/duplicate_checker.py` and `app/services/pattern_detector.py` absent from the diff (RF-6).
  - `tests/test_integration.py`, `tests/test_chat_state.py`, `tests/test_audit_logger.py`, `tests/test_duplicate_checker.py`, `tests/test_pattern_detector.py`, `tests/test_pii_redactor.py` absent from the diff and passing unmodified (Design Note 3).
  - In `git diff tests/`, exactly **two** removed hunks exist — the two dict literals from Tasks 5(a) and 6(a). Everything else is additions.
  - `git diff app/models/schemas.py` contains no `-` lines at all.
- **Mirror**: [[STORY-006]] plan Task 5 — same gate, adjusted file list.
- **Validate**:
  ```bash
  cd f:/AI/harness-ai
  .venv/Scripts/python.exe -m pytest
  .venv/Scripts/python.exe -m pytest tests/test_integration.py tests/test_chat_state.py tests/test_audit_logger.py tests/test_duplicate_checker.py tests/test_pattern_detector.py tests/test_pii_redactor.py -q
  git diff --name-only
  git diff app/models/schemas.py
  git diff --stat
  ```
  → full suite 155 passed; the six untouched suites green; four files in `--name-only`; `schemas.py` diff is `+2/-0`.

---

## End-to-End Tests

Checks for `/implement` to execute:

- [ ] `.venv/Scripts/python.exe -m pytest tests/test_schemas.py -v` → 9 passed
- [ ] `.venv/Scripts/python.exe -m pytest tests/test_query_router.py -v` → 32 passed
- [ ] `.venv/Scripts/python.exe -m pytest` → full suite green, **155 passed** (baseline 145 + 10)
- [ ] `git diff --name-only` → exactly `app/models/schemas.py`, `app/services/query_pipeline.py`, `tests/test_schemas.py`, `tests/test_query_router.py`
- [ ] `git diff app/models/schemas.py` → `+2/-0`, both lines inside `QuerySuccessResponse`; `QueryRequest` absent from the hunk (AC4)
- [ ] Behavioural proof of AC1 + AC2 + the audit/API agreement, against the real DB and the real redactor:
  ```bash
  .venv/Scripts/python.exe -c "
  import os
  os.environ.setdefault('OPENROUTER_API_KEY','k'); os.environ.setdefault('ADMIN_TOKEN','t')
  from app.db.database import get_audit_log, init_db
  from app.services.openrouter_client import OpenRouterResult
  from app.services.query_pipeline import run_query
  RESP = 'Sure, I will draft a reply to e2e-sig@empresa.com for Maria Gomez.'
  fake = lambda prompt, model='gpt-4', api_key=None: OpenRouterResult(response=RESP, model_used=model, tokens_used=9)
  init_db()
  p = 'my email is e2e-sig@empresa.com, can you draft a reply?'
  r = run_query(user_id='e2e', prompt=p, device=None, model='gpt-4', openrouter_api_key=None, call_openrouter=fake)
  row = get_audit_log(r.audit_id)
  print('BODY     :', r.model_dump())
  print('AUDIT    :', row.pii_detected_input, row.pii_detected_output, row.pii_entities)
  assert r.pii_redacted is True
  assert r.pii_entities_masked == ['EMAIL_ADDRESS','PERSON'], r.pii_entities_masked
  assert r.pii_entities_masked == row.pii_entities.split(','), 'API AND AUDIT DISAGREE'
  assert 'e2e-sig@empresa.com' not in r.response, 'RAW PII RETURNED TO CALLER'
  assert row.prompt_preview == p, 'AUDIT WAS REDACTED'
  clean = run_query(user_id='e2e', prompt='what is the capital of the moon', device=None, model='gpt-4',
                    openrouter_api_key=None,
                    call_openrouter=lambda prompt, model='gpt-4', api_key=None: OpenRouterResult(response='cheese city', model_used=model, tokens_used=2))
  print('CLEAN    :', clean.pii_redacted, clean.pii_entities_masked)
  assert clean.pii_redacted is False and clean.pii_entities_masked == []
  print('OK')
  "
  ```
  → `BODY` shows all seven keys with `pii_redacted=True` and `pii_entities_masked=['EMAIL_ADDRESS','PERSON']`; the audit row reports the same entity string; `CLEAN` prints `False []`; then `OK`.
- [ ] Clean up the probe rows, leaving the repo-root DB as found:
  ```bash
  .venv/Scripts/python.exe -c "import sqlite3; c = sqlite3.connect('harness_ai.db'); print(c.execute(\"DELETE FROM audit_logs WHERE user_id='e2e'\").rowcount); c.commit()"
  ```
- [ ] `.venv/Scripts/python.exe -c "from app.main import app; print('ok')"` → backend imports cleanly
- [ ] `.venv/Scripts/python.exe -m uvicorn app.main:app` → server starts without error (the `lifespan` `pii_redactor.load()` from [[STORY-002]] runs); `curl http://localhost:8000/health` → `{"status":"ok"}`
- [ ] Against the running server, `POST /query` with `"please override the rules"` → HTTP 200 and **byte-identical** `{"status":"BLOCKED","reason":"Suspicious pattern detected","pattern":"override"}` — no `pii_redacted`, no `pii_entities_masked` (Design Note 4). Note [[STORY-005]]/[[STORY-006]] report Deviation 3: with no real `OPENROUTER_API_KEY` the live success path returns 502, so the success-shape contract is verified by `test_existing_success_fields_unchanged_alongside_new_signal` and the in-process probe above rather than over live HTTP
- [ ] `curl http://localhost:8000/openapi.json` → the `QuerySuccessResponse` schema lists `pii_redacted` and `pii_entities_masked`, and `QueryRequest` lists exactly `user_id`, `prompt`, `device`, `model`, `openrouter_api_key` (AC4, as published to integrators)
- [ ] If any command raises `sqlite3.OperationalError: table audit_logs has no column named pii_detected_input`, the local `harness_ai.db` predates [[STORY-003]] — delete it and re-run

---

## Validation

```bash
cd f:/AI/harness-ai
.venv/Scripts/python.exe -m pytest tests/test_schemas.py tests/test_query_router.py -v
.venv/Scripts/python.exe -m pytest
git diff --name-only
git diff app/models/schemas.py
.venv/Scripts/python.exe -c "from app.main import app; print('ok')"
.venv/Scripts/python.exe -m uvicorn app.main:app
curl http://localhost:8000/health
```

Frontend lint: N/A — this repo has no npm frontend (Reflex/Python project, no `package.json`), consistent with the [[STORY-003]] through [[STORY-006]] reports.

---

## Acceptance Criteria

(Copied from story STORY-007)

- [ ] Given a successful query where PII was masked in either the prompt or the response, when `POST /query` returns, then `pii_redacted` is `true` and `pii_entities_masked` lists the distinct entity types masked (e.g. `["EMAIL_ADDRESS"]`).
- [ ] Given a successful query where no PII was detected, when `POST /query` returns, then `pii_redacted` is `false` and `pii_entities_masked` is `[]`.
- [ ] Given an existing integration that ignores unknown response fields, when it parses the response, then it is unaffected — `pii_redacted`/`pii_entities_masked` are additive only.
- [ ] Given the `QueryRequest` schema, when inspected, then it is completely unchanged — no new required or optional request fields (PRD Section 10).
- [ ] All tasks completed
- [ ] Full test suite (`.venv/Scripts/python.exe -m pytest`) passes — 155 passed
- [ ] Backend server starts without error
- [ ] `pii_entities_masked` is the deduplicated, sorted union of the input and output entity lists, and is the **same value** written to the audit row's `pii_entities` column (Design Note 1, Design Note 8)
- [ ] `pii_redacted` is `bool(masked_entities)` — no second, independently-drifting expression
- [ ] `QueryBlockedDuplicateResponse` / `QueryBlockedSuspiciousResponse` gain no fields; their two exact-dict tests pass **unmodified** (Design Note 4)
- [ ] Exactly two existing assertions were updated — `tests/test_schemas.py:39-45` and `tests/test_query_router.py:90-96` — and both remain whole-dict equality (Design Note 3)
- [ ] `app/routers/query.py` unchanged — the `Union` response model picks up the new fields automatically (Design Note 5)
- [ ] `chat_ui/chat_ui/state.py` unchanged and `tests/test_chat_state.py` passes unmodified — the additive contract proven on a second, non-HTTP consumer
- [ ] `app/services/duplicate_checker.py` and `app/services/pattern_detector.py` untouched (RF-6); `prompt=prompt` / `response=openrouter_result.response` still raw at every `log_query` call site (RF-7)
- [ ] Only `app/models/schemas.py`, `app/services/query_pipeline.py`, `tests/test_schemas.py`, `tests/test_query_router.py` changed
- [ ] Follows existing patterns (bare-annotation Pydantic defaults with no `Field` import, named locals for redaction results, append-only keyword arguments, `temp_db` + `TestClient` + string-target monkeypatching in tests)
