---
story: STORY-001
prd: PRD-015
plan: .agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-001-query-error-body-characterization.plan.md
epic_branch: epic/PRD-015-openai-compatible-endpoint
commit: 0341ed6
status: COMPLETE
completed: 2026-10-21
---

# Implementation Report: STORY-001, Characterize /query's error bodies and the upstream request body before /v1 exists

**Plan**: `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-001-query-error-body-characterization.plan.md`
**Epic Branch**: `epic/PRD-015-openai-compatible-endpoint` (created from `main` @ `c1b2e33`, after fast-forwarding the stale local `main` from `728dd60`)
**Commit**: `0341ed6`

## Summary

`tests/test_v1_query_isolation.py` pins the `/query` half of PRD-015's isolation guarantee. It compares the status and whole JSON body for each `/query` error that STORY-010's app-wide exception handlers could touch: 401 for no bearer and for an unknown bearer, 403 for a caller without `query:submit`, 422 for a missing `prompt` and for a malformed `session_id`, 500 for `DuplicateCheckError` and `PiiRedactorError`, and 502 for `OpenRouterError`. It also pins the PRD Section 9.2 T5 baseline for the upstream request. The real `call_openrouter` runs over an `httpx.MockTransport`, from a `/query` success and from `run_conversation` with all four `GenerationParams`. The tests assert the URL and the exact, ordered body keys. No production file changed.

The PRD's documents (PRD, index, 19 stories, pre-PRD promotion) went in a separate commit on the epic branch first, `docs(PRD-015): PRD, stories and index; pre-PRD promoted`, following PRD-014's `91937c5`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Create epic branch; capture today's 422 bodies on untouched code | none (throwaway probe, deleted) | ✅ |
| 2 | Error-body half: 8 whole-body pins | `tests/test_v1_query_isolation.py` | ✅ |
| 3 | Upstream-request half: `/query` success and `run_conversation` with four params | `tests/test_v1_query_isolation.py` | ✅ |
| 4 | Prove the `db` split | none | ✅ |
| 5 | Full-suite regression | none | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Frontend lint | N/A: the repo has no `frontend/` and no lint config; `chat_ui/` is untouched |
| New module | ✅ 10 passed (2.6 s) |
| Mutation check (sensitivity) | ✅ A throwaway `-p` plugin registering reshaping `HTTPException` / `RequestValidationError` handlers made all 8 error-body pins fail; the 2 upstream pins stayed green, as they should |
| `-m db --collect-only` | ✅ 9/10 collected (all but the no-bearer test) |
| `-m "not db"` with `HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:9` | ✅ 1 passed, 9 deselected (no Docker reached) |
| Full suite | ✅ 3,895 passed / 27 skipped / 1 failed in 6 m 57 s; the failure was a stall (below), and the rerun passed |
| ASCII-only source | ✅ |
| `git diff --stat origin/main -- app tests` | ✅ only `tests/test_v1_query_isolation.py` |
| E2E (live server) | ✅ 6/6 |

**The full-suite failure was infrastructure.** `tests/test_query_router.py::test_success_path_writes_exactly_one_row_with_output_telemetry` printed `libsql verdict: likely infrastructure -- execute took 15.05 s and ended in STREAM_EXPIRED`. That is the known shared-DB stall. A rerun of `tests/test_query_router.py` gave 41 passed. The total is 3,923 tests, which is the previous 3,913 plus the 10 new ones.

### E2E

Run against a live `uvicorn app.main:app --port 8765` on the dev libSQL container, with a seeded user `e2e-story001`:

- [x] `GET /health` gives `200 {"status":"ok"}`
- [x] `POST /query` with no bearer gives `401 {"detail":"Invalid or missing credential"}`. The test proves the same with Docker unreachable.
- [x] `POST /query` with an unknown bearer gives the same 401 body
- [x] `POST /query` with body `{}` returns the pinned 422 body, byte for byte
- [x] `POST /query` with a malformed `session_id` returns the pinned 422 body, byte for byte, `ctx: {"error": {}}` included
- [x] The 7 storage-backed error cases and both upstream captures are green in-process against the dev container (`TestClient`, as the plan specifies). A live 500 or 502 cannot be scripted on this machine without a stub.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_v1_query_isolation.py` | CREATE | +289 |
| `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-001-query-error-body-characterization.plan.md` | CREATE (archived plan) | +282 |

## Deviations from Plan

- **Branch creation.** The plan said `git checkout -b ... origin/main`. I ran `git fetch origin main:main` and branched from `main` instead. The result is the same commit, `c1b2e33`, and local `main` is no longer stale. The PRD-015 documents went in their own `docs` commit before the story commit (PRD-014 precedent). Phase 2.1 found the working tree dirty, but only with PRD-015 material, so nothing unrelated was carried.
- **Keep-awake wrapper.** On the full run, `SetThreadExecutionState(0x80000001)` failed. PowerShell 5.1 parses `0x80000001` as a negative Int32, which won't convert to `uint`. The suite ran without the wrapper and the machine did not sleep. `[uint32]2147483649` works, verified afterwards. This is tooling only and affects no result.
- **Live E2E added.** The plan listed only in-process checks. Phase 4 asks for a running app, so the live-server checks above were added.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_v1_query_isolation.py` | `test_query_401_without_bearer_body_is_pinned` (storage-free), `test_query_401_with_unknown_bearer_body_is_pinned`, `test_query_403_without_query_submit_body_is_pinned`, `test_query_422_missing_prompt_body_is_pinned`, `test_query_422_malformed_session_id_body_is_pinned`, `test_query_500_duplicate_check_error_body_is_pinned`, `test_query_500_pii_redactor_error_body_is_pinned`, `test_query_502_openrouter_error_body_is_pinned`, `test_query_success_upstream_request_is_pinned`, `test_run_conversation_upstream_request_with_all_four_params_is_pinned` |

## Notes for later stories

- **STORY-010** adds the `/v1` half to this module and may not edit a pin. The mutation check above shows the shape of the regression it must avoid: a handler that reshapes `HTTPException` or `RequestValidationError` bodies outside `/v1/`.
- **STORY-002 and STORY-006**: the upstream pins assert the URL literal `https://openrouter.ai/api/v1/chat/completions` and that no key exists outside `model`, `messages` and the four fields. `OPENROUTER_BASE_URL` must leave its default producing that exact URL.

## Acceptance Criteria

- [x] Given untouched `main`, `tests/test_v1_query_isolation.py` pins the full status and JSON body of `POST /query` for no bearer (401), invalid bearer (401), identity without `query:submit` (403), missing `prompt` and malformed `session_id` (422), `DuplicateCheckError` (500), `PiiRedactorError` (500) and `OpenRouterError` (502), and it passes.
- [x] Given a `/query` success and a `run_conversation` call with all four `GenerationParams` set, the upstream request captured with an `httpx.MockTransport` has the URL `https://openrouter.ai/api/v1/chat/completions`, and its JSON body keys are exactly `model`, `messages` and the set parameters.
- [x] Given the new tests, the whole suite runs with no existing assertion changed, and the new tests are green without any production change.
- [x] Given `-m "not db"`, the storage-free test runs without Docker, and the 9 that need storage carry the `db` marker.
