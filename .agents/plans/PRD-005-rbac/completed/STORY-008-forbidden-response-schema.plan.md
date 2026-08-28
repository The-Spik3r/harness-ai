---
story: STORY-008
prd: PRD-005
slug: forbidden-response-schema
title: QueryBlockedForbiddenResponse joins the QueryResponse union
type: NEW_CAPABILITY
complexity: LOW
epic_branch: epic/PRD-005-rbac        # all stories commit here, no per-story branch
created: 2026-08-28
---

# Plan: QueryBlockedForbiddenResponse joins the QueryResponse union

## Summary

Add a fourth Pydantic model, `QueryBlockedForbiddenResponse`, to `app/models/schemas.py` and fold it into the `QueryResponse` union so a policy-refused query (model outside a role's allowlist, `openrouter_api_key` supplied without `query:byok`) is a first-class, discriminable member of the API contract — per PRD Section 9's third HTTP-semantics row (`200` + `status: "BLOCKED"` + `reason` + `required_permission`). This is a schema-only change: `app/models/schemas.py` and its test file are the only touched files. Nothing yet constructs or returns the new model in production code — `run_query(...)` and `ChatState.send()` wiring belongs to STORY-010/STORY-014, which the story notes explicitly say to ship close together because the union becoming a 4-member type makes `ChatState.send()`'s catch-all `else` branch (currently treating anything not success-or-duplicate as the suspicious-pattern case) silently swallow the new member until that follow-up story adds an explicit branch.

## User Story

As an integrating developer
I want a distinct response type for a policy-refused query
So that a forbidden outcome is a first-class member of the contract instead of being folded into an existing block reason

## Story Reference

- Story file: `.agents/stories/PRD-005-rbac/STORY-008-forbidden-response-schema.md`
- PRD: `.agents/PRDs/PRD-005-rbac/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | LOW |
| Systems Affected | `app/models/schemas.py`, `tests/test_schemas.py` |
| Story | STORY-008 |
| PRD | PRD-005 |
| Epic Branch | `epic/PRD-005-rbac` (commit directly on this branch) |

---

## Skills In Use

None — `.agents/skills/` contains only `frontend-design`, which does not apply to a backend Pydantic schema change. Story frontmatter `skills: []` confirms this.

---

## Patterns to Follow

### Naming — sibling BLOCKED response models

```python
// SOURCE: app/models/schemas.py:24-33
class QueryBlockedDuplicateResponse(BaseModel):
    status: Literal["BLOCKED"] = "BLOCKED"
    reason: str
    first_query_at: str


class QueryBlockedSuspiciousResponse(BaseModel):
    status: Literal["BLOCKED"] = "BLOCKED"
    reason: str
    pattern: str
```
The new model follows this exact shape: `status: Literal["BLOCKED"] = "BLOCKED"` plus `reason: str` plus one discriminating extra field (`required_permission: str` here, matching PRD Section 10's 200-response example).

### Union declaration

```python
// SOURCE: app/models/schemas.py:36-38
QueryResponse = Union[
    QuerySuccessResponse, QueryBlockedDuplicateResponse, QueryBlockedSuspiciousResponse
]
```
Append the new member as a fourth entry. FastAPI/Pydantic discriminate a plain (non-tagged) `Union` in `response_model` by attempting each member in order and returning the first that validates against the given data — since all four members share the literal `status="BLOCKED"`/`"SUCCESS"` but each has a distinct extra required field (`first_query_at`, `pattern`, `required_permission`, or none), order does not create ambiguity as long as each model's non-`status` fields stay mutually distinguishing. No `Field(discriminator=...)` is used today, so none is introduced here.

### Tests — `model_dump()` exact-shape assertion

```python
// SOURCE: tests/test_schemas.py:50-59
def test_query_blocked_duplicate_response_shape():
    response = QueryBlockedDuplicateResponse(
        reason="Duplicate query within 24 hours",
        first_query_at="2026-07-04T10:30:00Z",
    )
    assert response.model_dump() == {
        "status": "BLOCKED",
        "reason": "Duplicate query within 24 hours",
        "first_query_at": "2026-07-04T10:30:00Z",
    }
```
Mirror this for `QueryBlockedForbiddenResponse` with `required_permission` in place of `first_query_at`/`pattern`.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/models/schemas.py` | UPDATE | Add `QueryBlockedForbiddenResponse` model; add it as the fourth member of the `QueryResponse` union |
| `tests/test_schemas.py` | UPDATE | Import the new model; add a shape test for it |

No other file is touched. `app/routers/query.py` (imports `QueryResponse` for `response_model=QueryResponse`) and `chat_ui/chat_ui/state.py` (the `isinstance` chain) automatically pick up the wider union/type but are not modified — wiring them is STORY-010 and STORY-014.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Add `QueryBlockedForbiddenResponse` model

- **File**: `app/models/schemas.py`
- **Action**: UPDATE
- **Implement**: Insert a new class directly after `QueryBlockedSuspiciousResponse` (before the `QueryResponse = Union[...]` declaration):
  ```python
  class QueryBlockedForbiddenResponse(BaseModel):
      status: Literal["BLOCKED"] = "BLOCKED"
      reason: str
      required_permission: str
  ```
- **Mirror**: `app/models/schemas.py:30-33` (`QueryBlockedSuspiciousResponse`) — identical structure, swap `pattern` for `required_permission`.
- **Validate**: `python -c "from app.models.schemas import QueryBlockedForbiddenResponse; print(QueryBlockedForbiddenResponse(reason='x', required_permission='query:submit').model_dump())"` prints `{'status': 'BLOCKED', 'reason': 'x', 'required_permission': 'query:submit'}`.

### Task 2: Add the model as the fourth `QueryResponse` union member

- **File**: `app/models/schemas.py`
- **Action**: UPDATE
- **Implement**: Change
  ```python
  QueryResponse = Union[
      QuerySuccessResponse, QueryBlockedDuplicateResponse, QueryBlockedSuspiciousResponse
  ]
  ```
  to
  ```python
  QueryResponse = Union[
      QuerySuccessResponse,
      QueryBlockedDuplicateResponse,
      QueryBlockedSuspiciousResponse,
      QueryBlockedForbiddenResponse,
  ]
  ```
- **Mirror**: `app/models/schemas.py:36-38` — same union, one more member appended at the end so existing member order (and therefore FastAPI's validate-in-order discrimination for the first three) is unchanged.
- **Validate**: `cd F:\AI\harness-ai && python -c "import app.routers.query"` imports without error (confirms `response_model=QueryResponse` still constructs a valid FastAPI response model with the widened union).

### Task 3: Add a shape test for the new model

- **File**: `tests/test_schemas.py`
- **Action**: UPDATE
- **Implement**:
  1. Add `QueryBlockedForbiddenResponse` to the `from app.models.schemas import (...)` block (keep alphabetical ordering, matching the existing import style).
  2. Add a new test function, placed after `test_query_blocked_suspicious_response_shape` (mirrors its structure):
     ```python
     def test_query_blocked_forbidden_response_shape():
         response = QueryBlockedForbiddenResponse(
             reason="Model not permitted for this role",
             required_permission="query:model:anthropic/claude-3.5-sonnet",
         )
         assert response.model_dump() == {
             "status": "BLOCKED",
             "reason": "Model not permitted for this role",
             "required_permission": "query:model:anthropic/claude-3.5-sonnet",
         }
     ```
     (`reason`/`required_permission` values match the PRD Section 10 example response.)
- **Mirror**: `tests/test_schemas.py:62-71` (`test_query_blocked_suspicious_response_shape`).
- **Validate**: `cd F:\AI\harness-ai && python -m pytest tests/test_schemas.py -v` — new test passes, all 10 pre-existing tests in the file still pass unmodified.

---

## End-to-End Tests

This is a pure schema addition with no ingress wiring, so there is no user-facing flow to exercise yet. The checks below confirm the contract itself is sound and non-breaking:

- [ ] `python -m pytest tests/test_schemas.py -v` → all tests pass, including the new `test_query_blocked_forbidden_response_shape`
- [ ] `python -c "from app.models.schemas import QueryResponse; import typing; print(typing.get_args(QueryResponse))"` → prints all four member classes in the expected order
- [ ] `python -c "import app.routers.query"` → module imports cleanly with `response_model=QueryResponse` referencing the widened union
- [ ] `python -m pytest tests/ -v` → full existing suite passes unmodified (confirms `tests/test_chat_state.py`'s `isinstance` checks on the first three members, and `tests/test_query_pipeline.py`/`test_api.py` if they exist, are unaffected by the wider union)

---

## Validation

```bash
cd F:\AI\harness-ai
python -m pytest tests/test_schemas.py -v
python -m pytest tests/ -v
python -c "from app.models.schemas import QueryBlockedForbiddenResponse, QueryResponse; print(QueryBlockedForbiddenResponse(reason='r', required_permission='p').model_dump())"
```

---

## Acceptance Criteria

(Copied from story STORY-008)

- [ ] Given `QueryBlockedForbiddenResponse`, when defined, then it carries `status: Literal["BLOCKED"]`, `reason: str`, and `required_permission: str`
- [ ] Given the `QueryResponse` union, when the fourth member is added, then FastAPI's `response_model` still discriminates all four members correctly
- [ ] Given the existing three response models, when this ships, then their shapes are byte-for-byte unchanged and `tests/test_schemas.py` passes unmodified for them
- [ ] Given the new model, when serialized, then `status == "BLOCKED"`, so clients that branch only on `status` keep working
- [ ] All tasks completed
- [ ] Backend server / imports start without error
- [ ] Follows existing patterns (mirrors `QueryBlockedDuplicateResponse`/`QueryBlockedSuspiciousResponse`)
