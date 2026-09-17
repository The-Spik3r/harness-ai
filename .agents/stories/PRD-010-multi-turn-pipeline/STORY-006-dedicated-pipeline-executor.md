---
id: STORY-006
prd: PRD-010
slug: dedicated-pipeline-executor
title: "Dedicated pipeline executor; /query async with its body off the event loop; ChatState uses it"
type: technical
priority: high
complexity: medium
phase: "2 - Pipeline over messages"
status: todo
labels: [backend, api, concurrency, chat-ui]
epic_branch: epic/PRD-010-multi-turn-pipeline
plan: null
report: null
commit: null
depends_on: [STORY-002]
blocks: [STORY-012, STORY-014]
skills: []
created: 2026-09-17
updated: 2026-09-17
---

# STORY-006: Dedicated pipeline executor; /query async with its body off the event loop; ChatState uses it

## Description

As a platform operator, I want every pipeline call, from `/query` and from the chat UI, to wait on its own bounded thread pool, so that slow upstream calls don't consume anyio's threadpool or the event loop's default executor and stall `/health`, the session rail or the admin console.

## Acceptance Criteria

- [ ] Given the new [app/services/pipeline_executor.py](../../../app/services/pipeline_executor.py), when it is read, then it exposes `async def run_in_pipeline(fn, /, *args, **kwargs)`, backed by one process-wide `ThreadPoolExecutor(max_workers=settings.PIPELINE_MAX_WORKERS, thread_name_prefix="pipeline")`. The executor is created lazily on first use under a lock, and `shutdown()` is idempotent.
- [ ] Given [app/routers/query.py](../../../app/routers/query.py), when it is read, then `query` is `async def`, and its whole former body (user-id check, foreign-session `owns()` check and its `log_query`, `run_query`) lives in a sync `_handle_query(request, identity)`, awaited via `run_in_pipeline`. The exception→status mapping (`ChatSessionError`/`DuplicateCheckError`/`PiiRedactorError` → 500, `OpenRouterError` → 502, `HTTPException` untouched) is unchanged.
- [ ] Given a test that patches `chat_sessions.owns`, `log_query` and the injected `call_openrouter` to record `threading.current_thread().name`, when `POST /query` runs with a foreign session and with a normal send, then every recorded name starts with `pipeline` (PRD Risk 2).
- [ ] Given `ChatState._do_send` in [chat_ui/chat_ui/state.py](../../../chat_ui/chat_ui/state.py), when it calls `run_query`, then it uses `await run_in_pipeline(run_query, …)` with the same arguments. Session-rail, rename, delete and transcript reads stay on `asyncio.to_thread`.
- [ ] Given the full suite, including [tests/test_query_router.py](../../../tests/test_query_router.py), [tests/test_query_outcomes_regression.py](../../../tests/test_query_outcomes_regression.py) and [tests/test_chat_state.py](../../../tests/test_chat_state.py), when this story lands, then it is green with no outcome assertion changed, and the executor's `shutdown()` is registered as a lifespan task.

## Technical Notes

- Why not an async client inside `call_openrouter`: PRD 6.3 / D1 correction. A sync `run_query` would still hold the calling thread. Put a short version of that reasoning in the module docstring.
- Lifespan: `app.main`'s lifespan does not run under Reflex (`api_transformer` bypass, see the comments above `app.register_lifespan_task(pii_redactor.load)` in [chat_ui/chat_ui/chat_ui.py](../../../chat_ui/chat_ui/chat_ui.py)). Register the shutdown in **both** places, following the precedent: a Reflex lifespan task (an async context manager that yields, then shuts down) and `app.main`'s lifespan for plain uvicorn. Lazy creation avoids reading `settings` at import (PRD Risk 5; `database.py`'s `_client_lock` pattern).
- `require_permission` stays a sync dependency. FastAPI runs it briefly in the anyio threadpool, which is acceptable (PRD 6.3).
- `TestClient` works with `async def` routes, so existing router tests need no harness change. If a test monkeypatches `run_query` in the router module, it still works, because `_handle_query` looks it up at call time.
- Tests that call `ChatState._do_send` and assert `asyncio.to_thread` usage for `run_query` must be adapted, with a `# PRD-010 STORY-006` comment.
- Full concurrency proof (ten blocked calls) is STORY-014. This story proves thread placement only.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-002
- **Blocks**: STORY-012, STORY-014

## PRD Reference

Source: [`PRD-010-multi-turn-pipeline/PRD.md`](../../PRDs/PRD-010-multi-turn-pipeline/PRD.md) — sections 1, 4 (Concurrency), 6.3, 7 (F4), 9.2 (T6), 14 (Risks 2, 5), 15 (D1)
