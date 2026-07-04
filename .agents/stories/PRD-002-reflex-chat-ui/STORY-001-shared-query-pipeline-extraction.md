---
id: STORY-001
prd: PRD-002
slug: shared-query-pipeline-extraction
title: "Extract run_query(...) shared pipeline function"
type: technical
priority: high
complexity: medium
phase: "1 - Shared pipeline extraction"
status: done
labels: [backend, refactor]
epic_branch: epic/PRD-002-reflex-chat-ui
plan: .agents/plans/PRD-002-reflex-chat-ui/completed/STORY-001-shared-query-pipeline-extraction.plan.md
report: .agents/reports/PRD-002-reflex-chat-ui/STORY-001-shared-query-pipeline-extraction.report.md
commit: PENDING
depends_on: []
blocks: [STORY-006]
skills: []
created: 2026-07-04
updated: 2026-07-04
---

# STORY-001: Extract run_query(...) shared pipeline function

## Description

As an integrating developer, I want the `POST /query` route's pipeline body (duplicate check → pattern check → OpenRouter call → audit log) extracted into a single reusable function, so that the future Reflex chat state can call the exact same logic with no parallel implementation (PRD Section 6, User Story 3).

## Acceptance Criteria

- [ ] Given the existing `app/routers/query.py` handler, when the pipeline logic is extracted, then it lives in a new `app/services/query_pipeline.py::run_query(...)` callable with no FastAPI-specific types (no `HTTPException`, no `response_model`) in its signature or body.
- [ ] Given `run_query(...)` is called with the same arguments the route currently uses (`user_id`, `prompt`, `device`, `model`, `openrouter_api_key`), when it runs, then it returns a value the route can map 1:1 to `QuerySuccessResponse`, `QueryBlockedDuplicateResponse`, or `QueryBlockedSuspiciousResponse` without re-implementing any branching logic.
- [ ] Given `app/routers/query.py` is updated to call `run_query(...)`, when PRD-001's existing test suite (STORY-012) runs, then it passes unmodified — this is a pure refactor with zero behavior change.
- [ ] Given the `user_id` presence check currently done in the route (`if not request.user_id.strip()`), when the refactor is complete, then this validation remains enforced (either still in the route as a pre-check, or moved into `run_query(...)` — either is acceptable as long as behavior is unchanged).
- [ ] Given any outcome (success, duplicate-blocked, suspicious-blocked, or OpenRouter error), when `run_query(...)` completes, then exactly one audit row is still written via `log_query(...)`, matching current behavior exactly.

## Technical Notes

- Source to extract from: [`app/routers/query.py`](../../../app/routers/query.py) — the full body of the `query(...)` handler (duplicate check via `check_duplicate`, pattern check via `detect_suspicious_pattern`, OpenRouter call via `call_openrouter`, audit logging via `log_query`).
- Per PRD Section 6: "the `POST /query` route handler's body ... is extracted into a single reusable function (e.g. `app/services/query_pipeline.py::run_query(...)`) that both the FastAPI route and the Reflex `ChatState` event handler call."
- Per PRD Section 12 Phase 1: "Goal: no behavior change, pure refactor." Validation is PRD-001's existing test suite (STORY-012) passing unmodified against the refactored route — do not introduce new response shapes yet.
- Per PRD risk #3 (Section 14): watch for request-scoped concerns (e.g. FastAPI `Depends`-injected sessions) that may not translate cleanly to a plain function; the current codebase does not use `Depends` for DB access (SQLite access is direct), so this risk is low but must be re-verified during extraction.
- Keep `app/routers/query.py`'s handler thin after the refactor — it should only translate `run_query(...)`'s return value into the appropriate Pydantic response model and raise `HTTPException` for the `user_id`-missing and OpenRouter-error cases.
- This story must land and pass PRD-001's test suite *before* any Reflex code is introduced (STORY-002+), isolating the refactor risk from the UI work.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-006

## PRD Reference

Source: [`PRD-002/PRD.md`](../../PRDs/PRD-002-reflex-chat-ui/PRD.md) — Section 6 (Core Architecture & Patterns), Section 12 Phase 1 (Shared pipeline extraction), Section 14 Risk 3
