---
story: STORY-006
prd: PRD-010
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-006-dedicated-pipeline-executor.plan.md
epic_branch: epic/PRD-010-multi-turn-pipeline
commit: d265843
status: COMPLETE
completed: 2026-09-17
---

# Implementation Report — STORY-006: Dedicated pipeline executor; /query async with its body off the event loop; ChatState uses it

**Plan**: `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-006-dedicated-pipeline-executor.plan.md`
**Epic Branch**: `epic/PRD-010-multi-turn-pipeline`
**Commit**: `d265843`

## Summary

Added `app/services/pipeline_executor.py`: a process-wide `ThreadPoolExecutor(max_workers=settings.PIPELINE_MAX_WORKERS, thread_name_prefix="pipeline")`, created lazily under a lock on first use, exposing `async def run_in_pipeline(fn, /, *args, **kwargs)` and an idempotent `shutdown()`. `POST /query` is now `async def`; its entire former body (user-id check, foreign-session `owns()` check + `log_query`, `run_query`) moved into a sync `_handle_query(request, identity)`, awaited via `run_in_pipeline`, with the existing exception→status mapping unchanged and wrapping the `await`. `ChatState._do_send`'s pipeline call now runs through `run_in_pipeline` instead of `asyncio.to_thread`; every other `asyncio.to_thread` call in `state.py` is untouched. `pipeline_executor.shutdown()` is registered as a lifespan task in both `app/main.py` (plain uvicorn) and `chat_ui/chat_ui/chat_ui.py` (a new `@asynccontextmanager` task, since Reflex's `api_transformer` mount bypasses `app.main`'s lifespan entirely — the same reason `pii_redactor.load`/`authz.load`/`authz.check_bootstrap` are duplicated there).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Create the pipeline executor module | `app/services/pipeline_executor.py` | ✅ |
| 2 | Unit-test the executor in isolation | `tests/test_pipeline_executor.py` | ✅ |
| 3 | Make `POST /query` async, body off the event loop | `app/routers/query.py` | ✅ |
| 4 | Prove thread placement (PRD Risk 2) | `tests/test_query_router.py` | ✅ |
| 5 | Register shutdown in `app/main.py`'s lifespan | `app/main.py` | ✅ |
| 6 | Test the plain-uvicorn shutdown registration | `tests/test_main.py` | ✅ |
| 7 | Register shutdown as a Reflex lifespan task | `chat_ui/chat_ui/chat_ui.py` | ✅ |
| 8 | Prove the Reflex lifespan task is registered | `tests/test_chat_ui_startup_guard.py` | ✅ |
| 9 | Point `ChatState._do_send` at the pipeline executor | `chat_ui/chat_ui/state.py` | ✅ |
| 10 | Adapt the concurrent-send-guard test | `tests/test_chat_state.py` | ✅ |
| 11 | Full suite | N/A | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `app/services/pipeline_executor.py` imports cleanly | ✅ |
| `chat_ui.chat_ui` imports cleanly under Reflex `PYTHONPATH` | ✅ |
| `tests/test_pipeline_executor.py` | ✅ 9 passed |
| `tests/test_query_router.py` + `test_query_outcomes_regression.py` + `test_query_session_id.py` + `test_query_pipeline_session_passthrough.py` | ✅ 88 passed (no outcome assertion changed) |
| `tests/test_query_router.py::test_pipeline_body_runs_on_dedicated_executor_thread` | ✅ 1 passed |
| `tests/test_main.py` (incl. new shutdown-registration test) | ✅ 11 passed |
| `tests/test_chat_ui_startup_guard.py` (incl. new pipeline-shutdown-registered test) | ✅ 5 passed |
| `tests/test_chat_state.py` (incl. adapted concurrent-send-guard test) | ✅ 136 passed |
| Full suite: `pytest tests/ -q` | ✅ 2065 passed, 25 skipped, 0 failed (1701.95s) |

## Files Changed

| File | Action | Notes |
|------|--------|-------|
| `app/services/pipeline_executor.py` | CREATE | `run_in_pipeline`, lazy lock-guarded `ThreadPoolExecutor`, idempotent `shutdown()` |
| `tests/test_pipeline_executor.py` | CREATE | 9 unit tests: return value, arg/kwarg forwarding, thread naming, lazy creation, settings sizing, lock correctness under concurrency, idempotent shutdown, exception propagation |
| `app/routers/query.py` | UPDATE | `query` → `async def`; body → sync `_handle_query`, awaited via `run_in_pipeline`; exception mapping unchanged |
| `tests/test_query_router.py` | UPDATE | New `test_pipeline_body_runs_on_dedicated_executor_thread` (PRD Risk 2) |
| `app/main.py` | UPDATE | `pipeline_executor.shutdown()` added after `yield` in the existing lifespan |
| `tests/test_main.py` | UPDATE | New `test_lifespan_shuts_down_the_pipeline_executor` |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | New `_pipeline_executor_lifespan` (`@asynccontextmanager`) registered via `app.register_lifespan_task` |
| `tests/test_chat_ui_startup_guard.py` | UPDATE | Probe script + new `test_pipeline_executor_shutdown_registered_as_chat_ui_lifespan_task`; docstring updated to name the third lifespan concern |
| `chat_ui/chat_ui/state.py` | UPDATE | `_do_send`'s `run_query` call: `asyncio.to_thread` → `run_in_pipeline` |
| `tests/test_chat_state.py` | UPDATE | `test_chat_state_concurrent_send_guard` adapted to patch `run_in_pipeline` directly instead of branching inside a patched `asyncio.to_thread` |

## Deviations from Plan

None. Two things worth naming as they weren't spelled out in the plan's task pseudocode:

- The thread-placement test's foreign-session request needed a canonical UUID4 `session_id` (`QueryRequest.session_id`'s validator rejects anything else with a 422 before the route body runs) — the plan's task description didn't specify a literal value; `"11111111-1111-4111-8111-111111111111"` was used.
- `tests/test_query_router.py` needed `import app.routers.query as query_router_module` (not previously imported in that file) to reach the router's own `log_query` binding for the spy; the plan named the patch target but not this import.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_pipeline_executor.py` | `test_run_in_pipeline_returns_the_function_result`, `test_run_in_pipeline_forwards_args_and_kwargs`, `test_run_in_pipeline_runs_on_a_pipeline_named_thread`, `test_executor_created_lazily_on_first_use`, `test_executor_sized_from_settings`, `test_concurrent_first_use_creates_exactly_one_executor`, `test_shutdown_is_idempotent`, `test_shutdown_before_any_use_is_a_noop`, `test_run_in_pipeline_propagates_exceptions` |
| `tests/test_query_router.py` | `test_pipeline_body_runs_on_dedicated_executor_thread` |
| `tests/test_main.py` | `test_lifespan_shuts_down_the_pipeline_executor` |
| `tests/test_chat_ui_startup_guard.py` | `test_pipeline_executor_shutdown_registered_as_chat_ui_lifespan_task` |
| `tests/test_chat_state.py` | `test_chat_state_concurrent_send_guard` (adapted, not new) |

## Acceptance Criteria

- [x] `app/services/pipeline_executor.py` exposes `async def run_in_pipeline(fn, /, *args, **kwargs)`, backed by one process-wide `ThreadPoolExecutor(max_workers=settings.PIPELINE_MAX_WORKERS, thread_name_prefix="pipeline")`, created lazily under a lock, with an idempotent `shutdown()`
- [x] `app/routers/query.py`'s `query` is `async def`, its whole former body lives in sync `_handle_query(request, identity)` awaited via `run_in_pipeline`, and the exception→status mapping is unchanged
- [x] A test patching `chat_sessions.owns`, `log_query` (both call sites) and the injected `call_openrouter` shows every recorded `threading.current_thread().name` starts with `pipeline`, for both a foreign-session request and a normal send
- [x] `ChatState._do_send` calls `await run_in_pipeline(run_query, …)`; session-rail, rename, delete and transcript reads stay on `asyncio.to_thread`
- [x] Full suite green (2065 passed, 25 skipped, 0 failed), no outcome assertion changed in `test_query_router.py` / `test_query_outcomes_regression.py` / `test_chat_state.py`; `shutdown()` registered as a lifespan task in both `app/main.py` and `chat_ui/chat_ui/chat_ui.py`
