---
story: STORY-006
prd: PRD-010
slug: dedicated-pipeline-executor
title: "Dedicated pipeline executor; /query async with its body off the event loop; ChatState uses it"
type: technical
complexity: medium
epic_branch: epic/PRD-010-multi-turn-pipeline
created: 2026-09-17
---

# Plan: Dedicated pipeline executor; /query async with its body off the event loop; ChatState uses it

## Summary

Add `app/services/pipeline_executor.py`, a process-wide `ThreadPoolExecutor(max_workers=settings.PIPELINE_MAX_WORKERS, thread_name_prefix="pipeline")` created lazily under a lock, exposing `async def run_in_pipeline(fn, /, *args, **kwargs)` and an idempotent `shutdown()`. Convert `POST /query` to `async def`, moving its entire former body (user-id check, foreign-session `owns()` check + `log_query`, `run_query`) into a new sync `_handle_query(request, identity)` awaited via `run_in_pipeline`, with the existing exception→status mapping wrapping the `await`. Point `ChatState._do_send`'s `run_query` call at `run_in_pipeline` instead of `asyncio.to_thread` (every other `asyncio.to_thread` call in `state.py` — session-rail reads, rename, delete, transcript reads — is untouched). Register `shutdown()` as a lifespan task in both places the app boots: `app/main.py`'s existing `lifespan` (plain uvicorn) and a new `@asynccontextmanager` task registered in `chat_ui/chat_ui/chat_ui.py` (Reflex's `api_transformer` mount bypasses `app.main`'s lifespan entirely, the same reason `pii_redactor.load`/`authz.load`/`authz.check_bootstrap` are duplicated there). A test proves thread placement by patching `chat_sessions.owns`, both `log_query` call sites and the injected `call_openrouter` to record `threading.current_thread().name`, asserting every name starts with `pipeline` for both a foreign-session request and a normal send (PRD Risk 2). The full concurrency proof (ten blocked calls) is STORY-014; this story only proves *where* the pipeline runs, not that saturation is harmless.

## User Story

As a platform operator
I want every pipeline call, from `/query` and from the chat UI, to wait on its own bounded thread pool
So that slow upstream calls don't consume anyio's threadpool or the event loop's default executor and stall `/health`, the session rail or the admin console

## Story Reference

- Story file: `.agents/stories/PRD-010-multi-turn-pipeline/STORY-006-dedicated-pipeline-executor.md`
- PRD: `.agents/PRDs/PRD-010-multi-turn-pipeline/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | technical |
| Complexity | MEDIUM |
| Systems Affected | FastAPI router (`/query`), Reflex chat UI (`ChatState`), app lifespan (both mounts) |
| Story | STORY-006 |
| PRD | PRD-010 |
| Epic Branch | `epic/PRD-010-multi-turn-pipeline` (commit directly on this branch) |

---

## Skills In Use

None. `frontend-design` is scanned (Phase 1b) but does not apply: this story changes no UI copy or visual surface — `ChatState._do_send` only swaps which executor its existing `run_query` call is offloaded to. The story's own frontmatter carries `skills: []`.

---

## Patterns to Follow

### Lazy singleton under a lock (mirrors `_shared_client`)
```python
// SOURCE: app/db/database.py:40-42, 111-122
_client_lock = threading.Lock()
_client_key: Optional[tuple[str, str]] = None
_client: Optional[Any] = None
...
def _shared_client() -> Any:
    global _client_key, _client, _client_used_at
    key = (settings.DATABASE_URL, settings.TURSO_AUTH_TOKEN)
    with _client_lock:
        if _client is None or _client_key != key:
            _client = libsql.connect(key[0], auth_token=key[1])
            _client_key = key
        ...
        return _client
```

### Startup-error validator style (already covers PIPELINE_MAX_WORKERS)
```python
// SOURCE: app/config.py:192-201
@field_validator("CONTEXT_MAX_MESSAGES", "CONTEXT_MAX_CHARACTERS", "PIPELINE_MAX_WORKERS")
@classmethod
def _validate_positive_pipeline_setting(cls, value: int, info) -> int:
    """Each of these bounds a resource that cannot be 0 or negative (PRD-010)."""
    if value < 1:
        description = _PIPELINE_LIMIT_DESCRIPTIONS[info.field_name]
        raise ValueError(
            f"{info.field_name} must be at least 1, got {value}. It is {description}."
        )
    return value
```
Already landed by STORY-002 — nothing to add here, just confirms `settings.PIPELINE_MAX_WORKERS` is safe to read at first use.

### FastAPI lifespan (where `/query`'s shutdown hook is registered)
```python
// SOURCE: app/main.py:11-20
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    pii_redactor.load()
    authz.load()
    authz.check_bootstrap()
    yield

app = FastAPI(title="Harness IA", lifespan=lifespan)
```

### Reflex lifespan-task registration under the `api_transformer` bypass
```python
// SOURCE: chat_ui/chat_ui/chat_ui.py:189-203
# Same api_transformer lifespan bypass as init_db() above: app.main's lifespan --
# and so STORY-002's pii_redactor.load() -- never fires under Reflex. Registered as
# a lifespan task (not called at import) so `reflex export --frontend-only` in the
# Dockerfile's builder stage still never touches the spaCy model.
app.register_lifespan_task(pii_redactor.load)
app.register_lifespan_task(authz.load)
app.register_lifespan_task(authz.check_bootstrap)
```
`register_lifespan_task` raises `InvalidLifespanTaskTypeError` for a bare generator function (`.venv/Lib/site-packages/reflex/app_mixins/lifespan.py:187-189`) — it must be wrapped in `@contextlib.asynccontextmanager`, which the mixin detects via `isinstance(t_, contextlib._AsyncGeneratorContextManager)` and enters/exits through an `AsyncExitStack` around the whole app lifetime (same file, lines 89-120). That is exactly the "async context manager that yields, then shuts down" shape STORY-006's Technical Notes ask for.

### `_do_send`'s existing offload call (the one call site that moves)
```python
// SOURCE: chat_ui/chat_ui/state.py:1018-1036
try:
    result = await asyncio.to_thread(
        run_query,
        identity=identity,
        prompt=text,
        device=device,
        model=model,
        openrouter_api_key=None,
        call_openrouter=call_openrouter,
        session_id=session_id or None,
    )
except OpenRouterError as exc:
    ...
```
Every other `asyncio.to_thread` call in this file (session-rail list/count, rename, delete, transcript reads, session `create`) stays exactly as is — STORY-006 only touches this one.

### Injected-callable spy pattern for the thread-name test
```python
// SOURCE: tests/test_query_router.py:347-368 (test_duplicate_and_pattern_checks_still_receive_the_raw_prompt)
def _spy_duplicate(user_id, key):
    seen_duplicate.append(raw_for_key.get(key, key))
    return real_check_duplicate(user_id, key)

monkeypatch.setattr(query_pipeline, "check_duplicate", _spy_duplicate)
```
The new thread-name test follows this shape: wrap the real callable, record something, delegate.

### Lifespan-registration probe (subprocess, PYTHONPATH=chat_ui/)
```python
// SOURCE: tests/test_chat_ui_startup_guard.py:37-57, 84-87
tasks = chat_ui_module.app.get_lifespan_tasks()
result["guard_registered"] = chat_ui_module.authz.check_bootstrap in tasks
...
def test_check_bootstrap_registered_as_chat_ui_lifespan_task(_empty_rbac_env):
    result = _run_probe(_empty_rbac_env)
    assert not result["errors"], result["errors"]
    assert result["guard_registered"] is True
```

### Resetting module-level singleton state around a `TestClient` lifespan (mirrors `database._client` reset)
```python
// SOURCE: tests/test_main.py:161-173 (test_lifespan_fails_when_the_database_is_unreachable)
monkeypatch.setattr(settings, "DATABASE_URL", "http://127.0.0.1:1")
database._client = None
database._client_key = None
try:
    with pytest.raises(DatabaseUnreachableError):
        with TestClient(app):
            pass
finally:
    database._client = None
    database._client_key = None
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/pipeline_executor.py` | CREATE | Bounded, lazily-created, process-wide `ThreadPoolExecutor`; `run_in_pipeline`; idempotent `shutdown()` |
| `tests/test_pipeline_executor.py` | CREATE | Unit tests: return value, thread naming, lazy creation under lock, settings sizing, idempotent shutdown, exception propagation |
| `app/routers/query.py` | UPDATE | `query` becomes `async def`; body moves into sync `_handle_query`, awaited via `run_in_pipeline` |
| `tests/test_query_router.py` | UPDATE | Add the thread-name-recording test (PRD Risk 2, story AC3) |
| `app/main.py` | UPDATE | Register `pipeline_executor.shutdown()` after `yield` in the existing lifespan |
| `tests/test_main.py` | UPDATE | Add a test that `pipeline_executor.shutdown()` runs on app shutdown |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | Register a new `@asynccontextmanager` lifespan task that shuts the executor down |
| `tests/test_chat_ui_startup_guard.py` | UPDATE | Extend the subprocess probe + add a test that the new lifespan task is registered |
| `chat_ui/chat_ui/state.py` | UPDATE | `_do_send`'s `run_query` call uses `await run_in_pipeline(run_query, …)` instead of `asyncio.to_thread` |
| `tests/test_chat_state.py` | UPDATE | Adapt `test_chat_state_concurrent_send_guard` to patch the new seam, with a `# PRD-010 STORY-006` comment |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create the pipeline executor module

- **File**: `app/services/pipeline_executor.py`
- **Action**: CREATE
- **Implement**:
  ```python
  """One dedicated, bounded thread pool for every pipeline call (PRD-010 F4).

  **Why not an async client inside call_openrouter instead (D1 correction to
  the brief, PRD Section 6.3).** `run_query`/`run_conversation` is a
  synchronous function. If `call_openrouter` awaited an async HTTP client
  internally, something would still have to block a thread waiting for the
  synchronous function to return -- anyio's threadpool for `/query`, the event
  loop's default executor for `ChatState`. What frees those shared pools is
  *whose* thread does the waiting, not whether the HTTP call inside is sync or
  async. So the dedicated pool wraps the whole pipeline call, not one HTTP
  request inside it.

  The executor is process-wide and created lazily, under a lock, on first use
  -- never at import -- so importing this module never reads `settings`
  (PRD Risk 5; mirrors `app/db/database.py`'s `_shared_client`/`_client_lock`
  pattern for the same reason). `shutdown()` is idempotent and is registered as
  a lifespan task in both `app/main.py` (plain uvicorn) and
  `chat_ui/chat_ui/chat_ui.py` (Reflex's `api_transformer` mount bypasses
  `app.main`'s lifespan entirely).
  """

  import asyncio
  import functools
  import threading
  from concurrent.futures import ThreadPoolExecutor
  from typing import Any, Callable, Optional

  from app.config import settings

  _lock = threading.Lock()
  _executor: Optional[ThreadPoolExecutor] = None


  def _get_executor() -> ThreadPoolExecutor:
      global _executor
      with _lock:
          if _executor is None:
              _executor = ThreadPoolExecutor(
                  max_workers=settings.PIPELINE_MAX_WORKERS,
                  thread_name_prefix="pipeline",
              )
          return _executor


  async def run_in_pipeline(fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
      """Await `fn(*args, **kwargs)` on the dedicated pipeline executor.

      The only way either ingress (`/query`, `ChatState`) runs the pipeline.
      """
      loop = asyncio.get_running_loop()
      return await loop.run_in_executor(
          _get_executor(), functools.partial(fn, *args, **kwargs)
      )


  def shutdown() -> None:
      """Stop the executor if one was ever created. Safe to call more than once."""
      global _executor
      with _lock:
          if _executor is not None:
              _executor.shutdown(wait=True)
              _executor = None
  ```
- **Mirror**: `app/db/database.py:40-42,73,111-122` (`_client_lock` lazy-singleton pattern); `app/main.py:1,11-17` (`@asynccontextmanager` style already in the repo)
- **Validate**: `cd "G:/coding/harness-ai" && python -c "import app.services.pipeline_executor"` (imports with no `settings` read error, i.e. no `Settings()` construction failure)

### Task 2: Unit-test the executor in isolation

- **File**: `tests/test_pipeline_executor.py`
- **Action**: CREATE
- **Implement**: Using `@pytest.mark.asyncio` (already the convention — see `tests/test_chat_state.py`), with an autouse fixture that calls `pipeline_executor.shutdown()` before and after each test so the process-wide singleton never leaks between tests:
  - `test_run_in_pipeline_returns_the_function_result` — `await run_in_pipeline(lambda x: x + 1, 41) == 42`
  - `test_run_in_pipeline_forwards_args_and_kwargs` — a function taking `(a, b, c=None)`, called with both positional and keyword args
  - `test_run_in_pipeline_runs_on_a_pipeline_named_thread` — `await run_in_pipeline(lambda: threading.current_thread().name)` starts with `"pipeline"`
  - `test_executor_created_lazily_on_first_use` — `pipeline_executor._executor is None` before any call, not `None` after
  - `test_executor_sized_from_settings` — `monkeypatch.setattr(settings, "PIPELINE_MAX_WORKERS", 3)`, then `pipeline_executor._executor._max_workers == 3` after first use
  - `test_concurrent_first_use_creates_exactly_one_executor` — monkeypatch `pipeline_executor.ThreadPoolExecutor` with a counting wrapper around the real class, fire 20 concurrent `run_in_pipeline` calls via `asyncio.gather`, assert exactly one was constructed (proves the lock, not just the lazy check)
  - `test_shutdown_is_idempotent` — use once, `shutdown()` twice, no exception, `_executor is None`
  - `test_shutdown_before_any_use_is_a_noop` — `shutdown()` with no prior use raises nothing
  - `test_run_in_pipeline_propagates_exceptions` — a function that raises `ValueError`, asserted via `pytest.raises`
- **Mirror**: `tests/test_main.py:151-173` (module-level singleton reset around a test); `tests/test_query_router.py:347-368` (spy-wrapping-real-callable pattern) for the counting-wrapper test
- **Validate**: `cd "G:/coding/harness-ai" && pytest tests/test_pipeline_executor.py -v`

### Task 3: Make `POST /query` async, body off the event loop

- **File**: `app/routers/query.py`
- **Action**: UPDATE
- **Implement**: Add `from app.services.pipeline_executor import run_in_pipeline`. Rename the current `query` body into a new sync function `_handle_query(request: QueryRequest, identity: Identity) -> QueryResponse`, carrying over **unchanged**: the `user_id` mismatch check (still raises `HTTPException(403)` directly, still writes no audit row), the foreign-session `owns()` check with its `log_query` call and its five-point comment block (lines 31-74 today), and the final `run_query(...)` call. `query` itself becomes:
  ```python
  @router.post("/query", response_model=QueryResponse)
  async def query(
      request: QueryRequest,
      identity: Identity = Depends(require_permission(PERMISSION_QUERY_SUBMIT)),
  ) -> QueryResponse:
      try:
          return await run_in_pipeline(_handle_query, request, identity)
      except ChatSessionError as exc:
          raise HTTPException(status_code=500, detail=str(exc)) from exc
      except DuplicateCheckError as exc:
          raise HTTPException(status_code=500, detail=str(exc)) from exc
      except PiiRedactorError as exc:
          raise HTTPException(status_code=500, detail=str(exc)) from exc
      except OpenRouterError as exc:
          raise HTTPException(status_code=502, detail=str(exc)) from exc
  ```
  `_handle_query`'s `HTTPException(403)` calls are caught by none of these `except` arms, so they propagate through the executor's future exactly as `OpenRouterError`/etc. do, and FastAPI's own exception handling turns them into the same 403 response as before — no router-level change to that behavior. Add a short docstring note on `_handle_query` citing PRD Risk 2 and this story: the whole body runs on the pipeline executor now, not on anyio's threadpool.
- **Mirror**: `app/routers/query.py:20-107` (today's file — becomes the split); `app/services/pipeline_executor.py`'s `run_in_pipeline` (Task 1)
- **Validate**: `cd "G:/coding/harness-ai" && pytest tests/test_query_router.py tests/test_query_outcomes_regression.py tests/test_query_session_id.py tests/test_query_pipeline_session_passthrough.py -v`

### Task 4: Prove thread placement (PRD Risk 2, story AC3)

- **File**: `tests/test_query_router.py`
- **Action**: UPDATE
- **Implement**: Add `import threading` and `from app.services import chat_sessions` to the imports. Add one test, `test_pipeline_body_runs_on_dedicated_executor_thread`, that:
  1. Wraps `chat_sessions.owns` (patched via `monkeypatch.setattr(chat_sessions, "owns", ...)`, since `app/routers/query.py` calls it as `chat_sessions.owns(...)` off the shared module object), the router's own `log_query` (patched via `monkeypatch.setattr("app.routers.query.log_query", ...)`, since it's bound directly into that module's namespace), the pipeline's `log_query` (patched via `monkeypatch.setattr(query_pipeline, "log_query", ...)`), and the injected `call_openrouter` (patched via `monkeypatch.setattr("app.routers.query.call_openrouter", ...)`) — each wrapper appends `threading.current_thread().name` to a shared list, then delegates to (or fakes, for `call_openrouter`) the real behavior.
  2. Sends one request with a `session_id` the identity does not own (`owns()` returns `False`, exercising the router's own `log_query` call) and asserts `403`.
  3. Sends one normal request with no `session_id` (exercising the pipeline's own `log_query` and `call_openrouter`) and asserts `200`.
  4. Asserts the recorded list is non-empty and every entry `.startswith("pipeline")`.
- **Mirror**: `tests/test_query_router.py:347-368` (`test_duplicate_and_pattern_checks_still_receive_the_raw_prompt`, the spy-wrapping-real-callable shape)
- **Validate**: `cd "G:/coding/harness-ai" && pytest tests/test_query_router.py::test_pipeline_body_runs_on_dedicated_executor_thread -v`

### Task 5: Register the executor's shutdown in `app/main.py`'s lifespan

- **File**: `app/main.py`
- **Action**: UPDATE
- **Implement**: Import `from app.services import pipeline_executor`, add `pipeline_executor.shutdown()` after the `yield` in the existing `lifespan`:
  ```python
  @asynccontextmanager
  async def lifespan(app: FastAPI):
      init_db()
      pii_redactor.load()
      authz.load()
      authz.check_bootstrap()
      yield
      pipeline_executor.shutdown()
  ```
- **Mirror**: `app/main.py:11-17` (unchanged structure, one new line)
- **Validate**: `cd "G:/coding/harness-ai" && pytest tests/test_main.py -v`

### Task 6: Test the plain-uvicorn shutdown registration

- **File**: `tests/test_main.py`
- **Action**: UPDATE
- **Implement**: Import `from app.services import pipeline_executor`. Add `test_lifespan_shuts_down_the_pipeline_executor`: `monkeypatch.setattr(settings, "RBAC_ENABLED", False)` (mirrors `_small_model_and_reset`), `monkeypatch.setattr(pipeline_executor, "shutdown", lambda: calls.append(1))`, run `with TestClient(app): pass` inside the `temp_db` fixture, assert `calls == [1]` after the block exits.
- **Mirror**: `tests/test_main.py:46-51` (`with TestClient(app) as test_client:` pattern that exercises the lifespan)
- **Validate**: `cd "G:/coding/harness-ai" && pytest tests/test_main.py::test_lifespan_shuts_down_the_pipeline_executor -v`

### Task 7: Register the executor's shutdown as a Reflex lifespan task

- **File**: `chat_ui/chat_ui/chat_ui.py`
- **Action**: UPDATE
- **Implement**: Add `from contextlib import asynccontextmanager` and `from app.services import pipeline_executor` to the imports (alongside the existing `from app.services import authz, pii_redactor`). Below the three existing `app.register_lifespan_task(...)` lines (after `authz.check_bootstrap`), add:
  ```python
  # Same bypass again (STORY-006): app.main's lifespan shuts the pipeline
  # executor down on exit, and this ingress never runs app.main's lifespan.
  # A bare generator function is rejected by register_lifespan_task
  # (InvalidLifespanTaskTypeError); wrapped in @asynccontextmanager it is
  # entered once at Reflex startup and its teardown runs at Reflex shutdown,
  # the same "yield, then clean up" shape STORY-006 uses in app/main.py.
  @asynccontextmanager
  async def _pipeline_executor_lifespan():
      yield
      pipeline_executor.shutdown()


  app.register_lifespan_task(_pipeline_executor_lifespan)
  ```
- **Mirror**: `chat_ui/chat_ui/chat_ui.py:189-203` (the three existing `register_lifespan_task` calls and their comments); `.venv/Lib/site-packages/reflex/app_mixins/lifespan.py:89-120,187-189` (why the async-context-manager shape is required)
- **Validate**: `cd "G:/coding/harness-ai/chat_ui" && python -c "import chat_ui.chat_ui"` (imports cleanly with `PYTHONPATH` including `chat_ui/`)

### Task 8: Prove the Reflex lifespan task is registered

- **File**: `tests/test_chat_ui_startup_guard.py`
- **Action**: UPDATE
- **Implement**: Extend `_CHECK_SCRIPT`'s body (after `tasks = chat_ui_module.app.get_lifespan_tasks()`) with:
  ```python
  result["pipeline_shutdown_registered"] = (
      chat_ui_module._pipeline_executor_lifespan in tasks
  )
  ```
  Add one test, `test_pipeline_executor_shutdown_registered_as_chat_ui_lifespan_task`, reusing the existing `_empty_rbac_env` fixture and `_run_probe` helper:
  ```python
  def test_pipeline_executor_shutdown_registered_as_chat_ui_lifespan_task(_empty_rbac_env):
      result = _run_probe(_empty_rbac_env)
      assert not result["errors"], result["errors"]
      assert result["pipeline_shutdown_registered"] is True
  ```
  Update the module docstring's "Two guards live here now" opening to "Three lifespan concerns live here now" (or similarly adjust the count), naming the new one, so the file's own framing stays accurate.
- **Mirror**: `tests/test_chat_ui_startup_guard.py:37-57,84-87` (`_CHECK_SCRIPT` + `test_check_bootstrap_registered_as_chat_ui_lifespan_task`, identical shape for a different task)
- **Validate**: `cd "G:/coding/harness-ai" && pytest tests/test_chat_ui_startup_guard.py -v`

### Task 9: Point `ChatState._do_send` at the pipeline executor

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: Replace the import `from app.services.query_pipeline import run_query` region's neighbor imports with an added `from app.services.pipeline_executor import run_in_pipeline`. At the call site (today `state.py:1018-1036`), change:
  ```python
  result = await asyncio.to_thread(
      run_query,
      identity=identity,
      ...
  )
  ```
  to
  ```python
  # PRD-010 STORY-006: the pipeline call runs on the dedicated pipeline
  # executor, not the event loop's default executor -- the same pool
  # session-rail reads and admin snapshots use, and the one this change
  # stops starving.
  result = await run_in_pipeline(
      run_query,
      identity=identity,
      prompt=text,
      device=device,
      model=model,
      openrouter_api_key=None,
      call_openrouter=call_openrouter,
      session_id=session_id or None,
  )
  ```
  Every other `asyncio.to_thread` call in this file is untouched.
- **Mirror**: `chat_ui/chat_ui/state.py:994-996` (the lazy session `create`, which stays on `asyncio.to_thread`, for contrast — nothing about it changes)
- **Validate**: `cd "G:/coding/harness-ai" && pytest tests/test_chat_state.py -v`

### Task 10: Adapt the concurrent-send-guard test to the new seam

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE
- **Implement**: In `test_chat_state_concurrent_send_guard` (today lines 568-600), replace the `_slow_to_thread` wrapper — which today branches on `fn is chat_state_mod.run_query` because `run_query` and the lazy session `create` shared one seam (`asyncio.to_thread`) — with a direct patch of the new, `run_query`-only seam:
  ```python
  @pytest.mark.asyncio
  async def test_chat_state_concurrent_send_guard(temp_db, monkeypatch):
      called_count = 0

      # PRD-010 STORY-006: run_query now runs through run_in_pipeline, not
      # asyncio.to_thread, so this test patches the new seam instead of
      # branching inside a patched asyncio.to_thread.
      async def _slow_run_in_pipeline(fn, *args, **kwargs):
          nonlocal called_count
          await asyncio.sleep(0.05)
          called_count += 1
          return QuerySuccessResponse(response="ok", audit_id=1, model_used="gpt-4", tokens_used=1)

      monkeypatch.setattr(chat_state_mod, "run_in_pipeline", _slow_run_in_pipeline)

      state = _make_state()
      task1 = asyncio.create_task(_send(state, "first prompt"))
      await asyncio.sleep(0.01)
      assert state.pending is True

      await _send(state, "second prompt")

      await task1
      assert state.pending is False
      assert called_count == 1
      user_messages = [m for m in state.messages if m.kind == "user"]
      assert len(user_messages) == 1
      assert user_messages[0].content == "first prompt"
  ```
  The lazy session `create` for the first send still runs on the real `asyncio.to_thread` (unpatched), which is correct and requires no branching. Leave `tests/test_chat_state.py:1012-1033` (`test_login_offloads_the_session_read_to_a_thread`) untouched — it patches `asyncio.to_thread` for an unrelated read and is unaffected by this story.
- **Mirror**: The AC's own instruction: "Tests that call `ChatState._do_send` and assert `asyncio.to_thread` usage for `run_query` must be adapted, with a `# PRD-010 STORY-006` comment."
- **Validate**: `cd "G:/coding/harness-ai" && pytest tests/test_chat_state.py::test_chat_state_concurrent_send_guard -v`

### Task 11: Full suite

- **File**: N/A
- **Action**: N/A
- **Implement**: Run the complete backend + chat UI suite and fix any fallout (e.g. any other test that happens to assert `asyncio.to_thread` was called for the pipeline path, beyond the one identified in Task 10).
- **Mirror**: N/A
- **Validate**: `cd "G:/coding/harness-ai" && pytest tests/ -v`

---

## End-to-End Tests

- [ ] `POST /query` with a clean prompt still returns `200 SUCCESS` with the same body shape (`tests/test_query_outcomes_regression.py` outcome 1, unmodified)
- [ ] `POST /query` with a `session_id` the caller does not own still returns `403` with the same detail, and the thread it ran on is a `pipeline-*` thread (Task 4's new test)
- [ ] In the chat UI, sending a message still produces the assistant bubble and clears `pending`, exercised via `tests/test_chat_state.py`'s existing send-path tests (all pass with `run_in_pipeline` swapped in for `run_query`'s offload)
- [ ] `chat_ui.chat_ui` still imports cleanly under Reflex's `PYTHONPATH`, with `_pipeline_executor_lifespan` registered as a lifespan task

---

## Validation

```bash
cd "G:/coding/harness-ai" && pytest tests/ -v
```

---

## Acceptance Criteria

(Copied from story `STORY-006`)

- [ ] `app/services/pipeline_executor.py` exposes `async def run_in_pipeline(fn, /, *args, **kwargs)`, backed by one process-wide `ThreadPoolExecutor(max_workers=settings.PIPELINE_MAX_WORKERS, thread_name_prefix="pipeline")`, created lazily on first use under a lock, with an idempotent `shutdown()`
- [ ] `app/routers/query.py`'s `query` is `async def`; its whole former body lives in a sync `_handle_query(request, identity)`, awaited via `run_in_pipeline`; the exception→status mapping is unchanged
- [ ] A test patching `chat_sessions.owns`, `log_query` and the injected `call_openrouter` to record `threading.current_thread().name` shows every recorded name starts with `pipeline`, for both a foreign-session request and a normal send
- [ ] `ChatState._do_send` calls `await run_in_pipeline(run_query, …)` with the same arguments; session-rail, rename, delete and transcript reads stay on `asyncio.to_thread`
- [ ] The full suite, including `tests/test_query_router.py`, `tests/test_query_outcomes_regression.py` and `tests/test_chat_state.py`, is green with no outcome assertion changed; the executor's `shutdown()` is registered as a lifespan task in both `app/main.py` and `chat_ui/chat_ui/chat_ui.py`
- [ ] All tasks completed
- [ ] Follows existing patterns (lazy-singleton-under-lock, lifespan-task registration, injected-callable spies)
