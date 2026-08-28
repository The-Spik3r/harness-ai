---
story: STORY-008
prd: PRD-005
plan: .agents/plans/PRD-005-rbac/completed/STORY-008-forbidden-response-schema.plan.md
epic_branch: epic/PRD-005-rbac
commit: 6e9e773
status: COMPLETE
completed: 2026-08-28
---

# Implementation Report — STORY-008: QueryBlockedForbiddenResponse joins the QueryResponse union

**Plan**: `.agents/plans/PRD-005-rbac/completed/STORY-008-forbidden-response-schema.plan.md`
**Epic Branch**: `epic/PRD-005-rbac`
**Commit**: `6e9e773`

## Summary

Added `QueryBlockedForbiddenResponse` to `app/models/schemas.py` as the fourth member of the `QueryResponse` union, giving a policy-refused query (model outside a role's allowlist, or `openrouter_api_key` supplied without `query:byok`) a distinct, discriminable response type instead of overloading an existing block reason. The model mirrors the shape of `QueryBlockedDuplicateResponse`/`QueryBlockedSuspiciousResponse`: `status: Literal["BLOCKED"] = "BLOCKED"`, `reason: str`, plus one distinguishing field, `required_permission: str`, matching the PRD Section 10 example response. This is a pure schema addition — no production code constructs or returns the new model yet; that wiring belongs to STORY-010 (`run_query()`) and STORY-014 (the explicit `ChatState.send()` branch).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add `QueryBlockedForbiddenResponse` model | `app/models/schemas.py` | ✅ |
| 2 | Add it as the fourth `QueryResponse` union member | `app/models/schemas.py` | ✅ |
| 3 | Add shape test + import | `tests/test_schemas.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Model instantiation/serialization | ✅ (`status`/`reason`/`required_permission` round-trip via `model_dump()`) |
| `app.routers.query` import (widened `response_model=QueryResponse`) | ✅ |
| `tests/test_schemas.py` | ✅ (12 passed, including 1 new) |
| Full suite (`tests/`) | ✅ (342 passed) |
| `QueryResponse` union member order | ✅ (`QuerySuccessResponse`, `QueryBlockedDuplicateResponse`, `QueryBlockedSuspiciousResponse`, `QueryBlockedForbiddenResponse`) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/models/schemas.py` | UPDATE | +6/-1 |
| `tests/test_schemas.py` | UPDATE | +12/-0 |

## Deviations from Plan

None. Implementation matched the plan exactly (field names, model shape, union order, test placement).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_schemas.py` | `test_query_blocked_forbidden_response_shape` |

## Acceptance Criteria

- [x] Given `QueryBlockedForbiddenResponse`, when defined, then it carries `status: Literal["BLOCKED"]`, `reason: str`, and `required_permission: str`
- [x] Given the `QueryResponse` union, when the fourth member is added, then FastAPI's `response_model` still discriminates all four members correctly
- [x] Given the existing three response models, when this ships, then their shapes are byte-for-byte unchanged and `tests/test_schemas.py` passes unmodified for them
- [x] Given the new model, when serialized, then `status == "BLOCKED"`, so clients that branch only on `status` keep working
