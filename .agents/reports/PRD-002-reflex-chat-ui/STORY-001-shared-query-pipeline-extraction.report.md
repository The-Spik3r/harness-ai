---
story: STORY-001
prd: PRD-002
plan: .agents/plans/PRD-002-reflex-chat-ui/completed/STORY-001-shared-query-pipeline-extraction.plan.md
epic_branch: epic/PRD-002-reflex-chat-ui
commit: 3e04c4e
status: COMPLETE
completed: 2026-07-04
---

# Implementation Report — STORY-001: Extract run_query(...) shared pipeline function

**Plan**: `.agents/plans/PRD-002-reflex-chat-ui/completed/STORY-001-shared-query-pipeline-extraction.plan.md`
**Epic Branch**: `epic/PRD-002-reflex-chat-ui`
**Commit**: `3e04c4e`

## Summary

Extracted the `POST /query` route handler's pipeline body (duplicate check → pattern check → OpenRouter call → audit log) into a new plain-Python function `app/services/query_pipeline.py::run_query(...)`. It returns one of the existing `QuerySuccessResponse` / `QueryBlockedDuplicateResponse` / `QueryBlockedSuspiciousResponse` Pydantic models directly, so `app/routers/query.py` now just does the `user_id` presence check, calls `run_query(...)`, translates `DuplicateCheckError`/`OpenRouterError` into `HTTPException`, and returns the result unmodified. `call_openrouter` is injected as a parameter (defaulting to the real implementation) so the router can forward its own module-level (test-patchable) reference into the pipeline function, preserving the existing `monkeypatch.setattr("app.routers.query.call_openrouter", ...)` test convention with zero test changes.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Create `run_query(...)` pipeline function | `app/services/query_pipeline.py` | ✅ |
| 2 | Update router to delegate to `run_query(...)` | `app/routers/query.py` | ✅ |
| 3 | Run full existing test suite unmodified | N/A | ✅ (97 passed) |

## Validation Results

| Check | Result |
|-------|--------|
| `python -c "from app.services.query_pipeline import run_query"` | ✅ |
| `python -c "from app.routers.query import router"` | ✅ |
| `pytest` (full suite) | ✅ 97 passed, 0 modified |
| Server start (`uvicorn app.main:app`) | ✅ starts without error |
| E2E manual checks | ✅ 3/3 |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/query_pipeline.py` | CREATE | +79 |
| `app/routers/query.py` | UPDATE | +11/-70 |

## Deviations from Plan

None. Implementation matched the plan exactly, including the `call_openrouter` dependency-injection design required to keep `tests/test_query_router.py` and `tests/test_integration.py` passing unmodified.

## Tests Written

None — this story is a pure refactor validated entirely by PRD-001's existing test suite (STORY-012), which passes unmodified per AC3. No new test file was required by the story's acceptance criteria.

## End-to-End Verification

- [x] `pytest` — 97/97 passed, no test files modified
- [x] `uvicorn app.main:app --reload` starts without error
- [x] `POST /query` with a suspicious-pattern prompt → `{"status":"BLOCKED","reason":"Suspicious pattern detected","pattern":"override"}` (200)
- [x] `POST /query` missing `user_id` → 422 (Pydantic validation, unchanged)
- [x] `POST /query` with blank `user_id` → 400 `{"detail":"user_id is required"}` (unchanged)

## Acceptance Criteria

- [x] Pipeline logic extracted into `app/services/query_pipeline.py::run_query(...)` with no FastAPI-specific types (no `HTTPException`, no `response_model`) in signature or body
- [x] `run_query(...)` accepts `user_id`, `prompt`, `device`, `model`, `openrouter_api_key` and returns one of the three response models directly — no branching re-implemented in the route
- [x] `app/routers/query.py` calls `run_query(...)`; PRD-001's existing test suite passes unmodified (97/97)
- [x] `user_id` presence check remains enforced in the route as a pre-check (unchanged location)
- [x] Exactly one audit row is written via `log_query(...)` for every outcome (success, duplicate-blocked, suspicious-blocked, OpenRouter error) — unchanged behavior
