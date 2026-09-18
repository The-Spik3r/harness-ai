---
story: STORY-014
prd: PRD-010
slug: pipeline-concurrency-tests
title: "Concurrency: blocked upstream calls do not stall /health, /query or the chat"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-010-multi-turn-pipeline
created: 2026-09-18
---

# Plan: Concurrency: blocked upstream calls do not stall /health, /query or the chat

## Summary

One new test module, `tests/test_pipeline_concurrency.py`, proves the MVP's operator claim
(PRD Section 11, *Concurrency*): with ten upstream calls blocked inside the dedicated
pipeline executor, `GET /health` and a fast `POST /query` both answer in under a second,
through both ingresses — the `/query` router and `ChatState._do_send` on its history path.
A fourth arm documents T6 by *choosing* saturation: with `PIPELINE_MAX_WORKERS=10` the
eleventh pipeline call queues and does not complete before release, while `/health` still
answers. A fifth, env-gated and out of CI, repeats the shape against a real local HTTP
server that delays 60 s, reached by monkeypatching `openrouter_client._API_URL`, and its
timings go into the story report. **Tests only — no production line changes.** Blocking is
expressed with a `threading.Event` plus an entry counter, never with `time.sleep`, and the
fixture releases every event *before* `pipeline_executor.shutdown()` — which joins — so no
blocked thread can leak into a later test.

## User Story

As a platform operator
I want a test proving that ten slow upstream calls don't block health checks or other requests
So that the executor change is verified rather than argued

## Story Reference

- Story file: `.agents/stories/PRD-010-multi-turn-pipeline/STORY-014-pipeline-concurrency-tests.md`
- PRD: `.agents/PRDs/PRD-010-multi-turn-pipeline/PRD.md` — Sections 1 (MVP goal), 5 (story 5), 6.3, 9.2 (T6, T8), 11 (*Concurrency*)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (a new test module; no production change) |
| Complexity | MEDIUM |
| Systems Affected | `tests/` only. Drives `app.main.app`, `app.services.pipeline_executor`, `chat_ui.chat_ui.state.ChatState` |
| Story | STORY-014 |
| PRD | PRD-010 |
| Epic Branch | `epic/PRD-010-multi-turn-pipeline` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` contains only `frontend-design` (visual identity for new UI). This story adds a backend test module and touches no component, style or copy. Story frontmatter `skills: []` and its Technical Notes ("Skills: none applicable") agree. | none |

Operational note carried instead of a skill: per the libSQL dev-server memory, **mass
fixture errors mean restarting the `harness-libsql-dev` container, not bisecting the
code**. Verified up at planning time (`docker ps` → `harness-libsql-dev  Up 35 minutes`).
This module is more exposed to that failure mode than most: every arm writes audit rows
from ten executor threads at once.

---

## Patterns to Follow

### Module header, auth constants and the seeded `temp_db` override

```python
# SOURCE: tests/test_query_router.py:1-64
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
...
_AUTH_USER_ID = "juan@empresa.com"
_AUTH_TOKEN = "test-user-token"
_AUTH_HEADERS = {"Authorization": f"Bearer {_AUTH_TOKEN}"}

@pytest.fixture
def temp_db(temp_db):
    """conftest's initialized database, plus this suite's authenticated user."""
    insert_user(
        User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN))
    )
    return temp_db

def _count_audit_rows() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]
```

The two-line `os.environ.setdefault` prologue is the house prologue, repeated at the top of
~21 modules. The table is `audit_logs`; `app.db.database.count_audit_logs()` is the
alternative idiom (`tests/test_history_off_integration.py:218`) and either is acceptable —
this module uses the local `_count_audit_rows()` so the census reads in one place.

### Resetting the executor between tests

```python
# SOURCE: tests/test_pipeline_executor.py:18-25
@pytest.fixture(autouse=True)
def _reset_executor():
    pipeline_executor.shutdown()
    yield
    pipeline_executor.shutdown()
```

```python
# SOURCE: tests/test_pipeline_executor.py:57-62
monkeypatch.setattr(settings, "PIPELINE_MAX_WORKERS", 3)
```

Sizing is `monkeypatch.setattr(settings, …)` plus a `shutdown()`, because `_get_executor()`
reads the setting only when it builds the pool.

### The injected-upstream stub signature and the thread-name spy

```python
# SOURCE: tests/test_query_router.py:775-828
def _spy_call_openrouter(messages, model="gpt-4", api_key=None):
    thread_names.append(threading.current_thread().name)
    return OpenRouterResult(response="ok", model_used=model, tokens_used=1)

monkeypatch.setattr("app.routers.query.call_openrouter", _spy_call_openrouter)
...
assert all(name.startswith("pipeline") for name in thread_names)
```

`app/routers/query.py:120` passes its own module-level `call_openrouter` into `run_query`,
so the router's binding is the patch target. `chat_ui/chat_ui/state.py` holds an
independent import of the same name, patched as
`monkeypatch.setattr(chat_state_mod, "call_openrouter", …)`
(`tests/test_chat_state.py:47,230`). Two bindings is what lets the chat arm block ten chat
sends while a concurrent `/query` stays fast.

### Driving `ChatState` without Reflex

```python
# SOURCE: tests/test_chat_history_send.py:69-79 (twin at tests/test_chat_state.py:123-133)
def _make_state() -> ChatState:
    state = ChatState(_reflex_internal_init=True)
    state.user_id = _AUTH_USER_ID
    state._token = _AUTH_TOKEN
    return state

async def _send(state: ChatState, text: str) -> None:
    state.input_text = text
    handler = type(state).event_handlers["send"]
    await handler.fn(state)  # bypasses the background-task chain guard
```

### A free port for the manual smoke's server

```python
# SOURCE: tests/test_reports_e2e.py:139-142
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
```

### Env-gated, out-of-CI test

```python
# SOURCE: tests/test_reports_e2e.py:45-61
BASE_URL = os.environ.get("REPORTS_E2E_URL", "").rstrip("/")
pytestmark = [
    pytest.mark.skipif(not BASE_URL, reason="set REPORTS_E2E_URL to a running server"),
]
```

### Async test marking, and the absence of a timeout plugin

There is no `pytest.ini`, `pyproject.toml`, `setup.cfg` or `tox.ini` anywhere in the repo,
so `pytest-asyncio` runs in its default **strict** mode: every async test carries an
explicit `@pytest.mark.asyncio` (`tests/test_chat_state.py`, `tests/test_admin_state.py:327`
and four other modules). `anyio` is never used as a test plugin, and **`pytest-timeout` is
not in `requirements.txt`**, so the story's "hard test timeout" is `asyncio.wait_for`, not
`pytest.mark.timeout`. CI (`.github/workflows/ci.yml`) runs plain `pytest -q` against a
libSQL service container.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_pipeline_concurrency.py` | CREATE | The whole story: four CI arms + one env-gated manual smoke |

No production file changes. If an arm fails, that is a real defect in STORY-006 or
STORY-012: the fix lands in its own commit referencing the story that introduced it, and
these tests land after it.

---

## Design notes the tasks depend on

Seven facts settled at planning time, so no task has to rediscover them:

1. **`pipeline_executor.shutdown()` is also the reset.** `app/services/pipeline_executor.py:56-63`
   sets `_executor = None` after `shutdown(wait=True)`, and `_get_executor()` builds the next
   one lazily from `settings.PIPELINE_MAX_WORKERS` (`:34-43`). There is no `reset()`. So
   "an executor of size N" is `monkeypatch.setattr(settings, "PIPELINE_MAX_WORKERS", N)`
   **followed by** a `shutdown()` — before the body, to discard whatever size an earlier
   test left, and again in teardown. This is exactly `tests/test_pipeline_executor.py:18-25`'s
   autouse fixture, extended with the stub release.
2. **`shutdown(wait=True)` joins its threads.** Teardown must therefore `release.set()`
   *before* it calls `shutdown()`, or the fixture itself hangs. That is the story's "always
   release the event in a `finally`", and it lives in the fixture so no arm can forget it.
3. **`/health` is a sync `def`** (`app/main.py:27-29`), so Starlette runs it through
   `run_in_threadpool` on anyio's shared pool — exactly the pool that must stay free.
   `POST /query` is `async def` (`app/routers/query.py:22`) and holds no anyio token while
   awaiting `run_in_pipeline`; only the sync `require_permission` dependency
   (`app/middleware/auth.py:23-31`) touches that pool, and briefly.
4. **This module is the first in the repo to use `httpx.ASGITransport`** — every existing
   suite uses `fastapi.testclient.TestClient`. The story mandates it, and httpx 0.28.1 is
   installed and exports it (verified). `ASGITransport` drives the app in the test's own
   event loop, and Starlette still routes sync endpoints through `run_in_threadpool`, so the
   anyio pool is exercised as uvicorn exercises it. **Expect no uvicorn-in-a-thread variant
   to be needed**; Task 9 is the explicit check. Note that `ASGITransport` does not run the
   lifespan — which is fine here, since `temp_db` performs `init_db()` and this module calls
   `shutdown()` itself.
5. **Every prompt in an arm must be distinct.** Ten identical concurrent prompts would meet
   PRD-009's duplicate check and some would return `BLOCKED` without reaching the stub,
   making "all ten complete with SUCCESS" false for a reason unrelated to concurrency. Use
   `f"concurrency probe {i} {uuid4()}"`.
6. **Ten concurrent `ChatState` sends need ten `ChatState` instances.** `_do_send` claims a
   per-instance `pending` flag and returns early if it is already set
   (`chat_ui/chat_ui/state.py:952-954`) — ten tabs, ten states.
7. **Concurrent writes from ten executor threads are safe.** `app/db/database.py:74-123`
   keeps one process-wide libSQL client precisely so worker threads serialize on it; the
   docstring records that a client-per-thread lost 169 of 200 writes to `TRANSACTION_TIMEOUT`
   while the shared client lost none.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create the module header, imports and fixtures

- **File**: `tests/test_pipeline_concurrency.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring stating what is proven (PRD Section 11 *Concurrency*; Section 9.2 T6),
    that blocking is a `threading.Event` and never a sleep, that the release-before-shutdown
    order in the fixture is load-bearing, and that this module is the repo's first
    `ASGITransport` user and why the story asks for it.
  - The `os.environ.setdefault` prologue, then imports: `asyncio`, `socket`, `threading`,
    `time`, `uuid4`, `pytest`, `httpx` (`ASGITransport`, `AsyncClient`), `settings`,
    `get_connection`, `insert_user`, `User`, `hash_token`, `OpenRouterResult`,
    `app.main.app`, `app.services.pipeline_executor`, `app.services.chat_sessions`,
    `chat_ui.chat_ui.state as chat_state_mod` + `ChatState`, and `derive_title`.
  - `_AUTH_USER_ID` / `_AUTH_TOKEN` / `_AUTH_HEADERS`, the seeded `temp_db` override, and
    `_count_audit_rows()`.
  - `_HARD_TIMEOUT = 10.0` (the story's hard timeout) and `_FAST = 1.0` (the PRD's "< 1 s").
- **Mirror**: `tests/test_query_router.py:1-64` for header, constants, `temp_db` override and
  `_count_audit_rows`; `tests/test_chat_history_send.py:1-30` for the docstring voice.
- **Validate**: `pytest -q tests/test_pipeline_concurrency.py --collect-only` (imports clean,
  collects 0 tests)

### Task 2: The blocking upstream stub

- **File**: `tests/test_pipeline_concurrency.py`
- **Action**: UPDATE
- **Implement**: `class _BlockingUpstream`, constructed as `_BlockingUpstream(block_first: int)`,
  holding `self.release = threading.Event()`, `self._cond = threading.Condition()`,
  `self.calls = 0`, `self.in_stub = 0`.
  - `__call__(self, messages, model="gpt-4", api_key=None)` — the injected `call_openrouter`
    signature (`tests/test_query_router.py:804`). Under the condition, increment `calls`;
    if `calls <= block_first`, increment `in_stub`, `notify_all()`, release the lock, and
    `self.release.wait(timeout=_HARD_TIMEOUT)`; a `False` return raises
    `AssertionError("blocked upstream was never released")`, so a regression fails instead of
    hanging. Always returns
    `OpenRouterResult(response="ok", model_used=model, tokens_used=1)`.
  - `wait_until_blocked(self, n: int) -> None` — a **synchronous** helper waiting on the
    condition until `in_stub >= n`, bounded by `_HARD_TIMEOUT`, raising `AssertionError` on
    expiry. Arms call it as
    `await asyncio.wait_for(asyncio.to_thread(stub.wait_until_blocked, 10), _HARD_TIMEOUT)`,
    so the event loop is never blocked and no arm ever sleeps to wait for calls to be in
    flight (the story's first Technical Note).
  - A module-level `_fast_upstream(messages, model="gpt-4", api_key=None)` returning
    immediately, for the arms that need a concurrent call fast by construction rather than by
    luck.
- **Mirror**: `tests/test_query_router.py:800-806` for the call signature and result shape;
  `tests/test_chat_state.py:119-120` for the fake's voice.
- **Validate**: `pytest -q tests/test_pipeline_concurrency.py --collect-only`

### Task 3: The executor-sizing fixture

- **File**: `tests/test_pipeline_concurrency.py`
- **Action**: UPDATE
- **Implement**: `@pytest.fixture def pipeline_pool(monkeypatch)` yielding a factory
  `configure(workers: int, block_first: int) -> _BlockingUpstream`:
  - `monkeypatch.setattr(settings, "PIPELINE_MAX_WORKERS", workers)`, then
    `pipeline_executor.shutdown()` so the next `run_in_pipeline` builds a pool of that size
    (Design note 1); build the stub, keep it in a list for teardown, return it.
  - Teardown in a `finally`: `release.set()` on **every** stub handed out first, then
    `pipeline_executor.shutdown()` (Design note 2), so no blocked `pipeline-*` thread
    survives into the next test. Comment both halves with *why* the order is fixed — a
    reader who "tidies" it into shutdown-then-release deadlocks the suite.
- **Mirror**: `tests/test_pipeline_executor.py:18-25` (the `_reset_executor` shape this
  extends); `tests/conftest.py:155-205` for fixture-layering voice.
- **Validate**: `pytest -q tests/test_pipeline_executor.py` still passes (the fixture must
  leave no pool behind for it)

### Task 4: AC 1 — `/health` answers while ten `/query` calls are blocked

- **File**: `tests/test_pipeline_concurrency.py`
- **Action**: UPDATE
- **Implement**: `@pytest.mark.asyncio async def test_health_answers_while_ten_query_calls_are_blocked(temp_db, monkeypatch, pipeline_pool)`.
  - `stub = pipeline_pool(workers=16, block_first=10)`;
    `monkeypatch.setattr("app.routers.query.call_openrouter", stub)`.
  - One `async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=_AUTH_HEADERS) as client:`.
  - Ten `asyncio.create_task(client.post("/query", json={"prompt": f"concurrency probe {i} {uuid4()}"}))`
    (Design note 5), then
    `await asyncio.wait_for(asyncio.to_thread(stub.wait_until_blocked, 10), _HARD_TIMEOUT)`.
  - `started = time.monotonic()`;
    `health = await asyncio.wait_for(client.get("/health"), _HARD_TIMEOUT)`; assert
    `health.status_code == 200`, `health.json() == {"status": "ok"}`, and
    `time.monotonic() - started < _FAST`.
  - Tail: `stub.release.set()`, then
    `responses = await asyncio.wait_for(asyncio.gather(*tasks), _HARD_TIMEOUT)`; assert all
    ten are 200 with `status == "SUCCESS"`.
- **Mirror**: `tests/test_query_router.py:168-190` for the success-shape assertions.
- **Validate**: `pytest -q tests/test_pipeline_concurrency.py -k health_answers_while_ten_query`

### Task 5: AC 2 — an eleventh `/query` succeeds in < 1 s, and each call writes one row

- **File**: `tests/test_pipeline_concurrency.py`
- **Action**: UPDATE
- **Implement**: `@pytest.mark.asyncio async def test_eleventh_query_succeeds_while_ten_are_blocked(temp_db, monkeypatch, pipeline_pool)`.
  - The same 16/10 setup and the same ten blocked tasks, waited into the stub the same way.
  - `started = time.monotonic()`; the eleventh
    `await asyncio.wait_for(client.post("/query", …), _HARD_TIMEOUT)` — call 11 is past
    `block_first`, so the stub returns immediately; assert 200, `status == "SUCCESS"`, and
    elapsed `< _FAST`.
  - Release, gather the ten, assert each is 200/`SUCCESS`.
  - Then `assert _count_audit_rows() == 11` — the story's "each writes exactly one audit
    row", stated as a census over the whole table, which is only meaningful because `temp_db`
    starts empty (`tests/conftest.py:155-205`).
- **Mirror**: `tests/test_query_router.py:561-578` and
  `tests/test_query_pipeline_multiturn.py:691-730` for the exactly-one-row claim.
- **Validate**: `pytest -q tests/test_pipeline_concurrency.py -k eleventh_query`

### Task 6: AC 3 — ten blocked `ChatState._do_send`s stall neither `/health` nor `/query`

- **File**: `tests/test_pipeline_concurrency.py`
- **Action**: UPDATE
- **Implement**: `@pytest.mark.asyncio async def test_health_and_query_answer_while_ten_chat_sends_are_blocked(temp_db, monkeypatch, pipeline_pool)`.
  - `monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", True)` and a comment saying why:
    the story asks for "the history path, with an active session", which is the
    `had_session and settings.CHAT_HISTORY_ENABLED` branch at
    `chat_ui/chat_ui/state.py:1072-1121` — `assemble` on the executor, then `run_conversation`
    on it. Without both, `_do_send` takes the `run_query` branch and the arm proves the wrong
    thing.
  - `stub = pipeline_pool(workers=16, block_first=10)`;
    `monkeypatch.setattr(chat_state_mod, "call_openrouter", stub)` for the chat binding, and
    `monkeypatch.setattr("app.routers.query.call_openrouter", _fast_upstream)` so the
    concurrent `/query` is fast by construction (Design note: two independent bindings).
  - Ten states from a local `_make_state()`, each with an **active session**: create one per
    state through `chat_sessions.create(identity, "seed", derive_title)` and assign
    `state.active_session_id`, so `had_session` is true on the send under test. (The
    alternative — one cheap first send per state against `_fast_upstream` before swapping the
    binding — is equivalent; pick one and say which in the report.)
  - Ten `asyncio.create_task(_send(state, f"concurrency probe {i} {uuid4()}"))` — ten distinct
    instances because of the per-instance `pending` guard (Design note 6).
  - `wait_until_blocked(10)`, then time `GET /health` and `POST /query` separately, each 200
    and each `< _FAST` (`/query` → `SUCCESS`), both through the `AsyncClient`/`ASGITransport`
    pair.
  - Release, gather the ten sends, assert each state's last bubble is an assistant bubble and
    not `upstream_error` / `internal_error` — a blocked-then-released send must still land
    normally.
- **Mirror**: `tests/test_chat_history_send.py:69-79` for `_make_state`/`_send`;
  `chat_ui/chat_ui/state.py:1072-1121` for which branch an active session takes.
- **Validate**: `pytest -q tests/test_pipeline_concurrency.py -k chat_sends_are_blocked`

### Task 7: AC 4 — saturation queues and does not fail (T6, documented on purpose)

- **File**: `tests/test_pipeline_concurrency.py`
- **Action**: UPDATE
- **Implement**: `@pytest.mark.asyncio async def test_saturated_pool_queues_the_eleventh_call_while_health_answers(temp_db, monkeypatch, pipeline_pool)`.
  - `stub = pipeline_pool(workers=10, block_first=10)` — the control run the story names.
  - Ten blocked `/query` tasks, waited into the stub; then an eleventh task.
  - Prove it waits **without** sleeping for progress: assert `stub.calls == 10` (the eleventh
    never reached the stub, because no worker is free) and that a bounded
    `await asyncio.wait_for(asyncio.shield(eleventh), 0.5)` raises `asyncio.TimeoutError`.
    Comment that this bounded non-completion check is not the forbidden "sleep until it is in
    flight": it asserts an absence, and its failure mode is a fast failure, never a hang.
  - Time `GET /health` during the saturation: 200 in `< _FAST`. That is the whole point of T6
    — the failure is contained to pipeline calls and `/health` stays truthful.
  - Release, then `await asyncio.wait_for(asyncio.gather(eleventh, *tasks), _HARD_TIMEOUT)`;
    all eleven 200/`SUCCESS`, and `_count_audit_rows() == 11`.
  - Docstring citing PRD Section 6.3 ("Saturation queues and does not fail") and Section 9.2
    T6, so a future reader sees this arm asserts intended behaviour, not a bug.
- **Mirror**: `app/services/pipeline_executor.py:1-20` for the reasoning voice.
- **Validate**: `pytest -q tests/test_pipeline_concurrency.py -k saturated_pool`

### Task 8: AC 5 — the env-gated 60-second manual smoke (not in CI)

- **File**: `tests/test_pipeline_concurrency.py`
- **Action**: UPDATE
- **Implement**: `test_manual_smoke_against_a_slow_local_server`, guarded per-test (not
  `pytestmark`, which would skip the whole module) by
  `@pytest.mark.skipif(not os.environ.get("HARNESS_SLOW_SMOKE"), reason="manual: set HARNESS_SLOW_SMOKE=1 (PRD-010 STORY-014 AC 5, out of CI)")`.
  - Stand up a real local HTTP server in a thread: `http.server.ThreadingHTTPServer` on
    `_free_port()` (`tests/test_reports_e2e.py:139-142`), whose handler sleeps 60 s — the
    *server* delays, which is the thing being simulated, not the test waiting on itself —
    then returns a minimal OpenRouter-shaped JSON body
    (`{"choices": [{"message": {"content": "ok"}}], "model": …, "usage": {"total_tokens": …}}`;
    confirm the exact shape against `app/services/openrouter_client.py`'s parser while
    implementing). Shut the server down in a `finally`.
  - `monkeypatch.setattr("app.services.openrouter_client._API_URL", f"http://127.0.0.1:{port}/")`
    — the constant at `app/services/openrouter_client.py:9`, used at `:126`. Comment that
    `settings.OPENROUTER_TIMEOUT_SECONDS` defaults to 120 s (PRD 9.3) so a 60 s delay
    completes rather than times out, and assert the setting rather than assume it.
  - Ten chat sends in flight plus a `/health` probe, with `time.monotonic()` around the probe
    and around the whole run; `print()` the measured timings so the `/implement` run can paste
    them into the story report (run it with `-s`).
- **Mirror**: `tests/test_reports_e2e.py:45-61` for the env-gated `skipif`;
  `tests/test_reports_e2e.py:145-174` for start-server / `finally`-kill.
- **Validate**: `pytest -q tests/test_pipeline_concurrency.py -k manual_smoke` reports
  `1 skipped` with no env var; `HARNESS_SLOW_SMOKE=1 … -s` passes and prints timings

### Task 9: Confirm `ASGITransport` exercises anyio's threadpool, or take the fallback

- **File**: `tests/test_pipeline_concurrency.py`
- **Action**: UPDATE (the assertion always; the fallback only if the check fails)
- **Implement**: The story's contingency, made explicit rather than trusted. In the Task 4
  arm, record the thread `/health` ran on — wrap `app.main.health` with a spy that appends
  `threading.current_thread().name` — and assert it is not `MainThread`, i.e. Starlette put
  the sync endpoint on anyio's threadpool exactly as uvicorn would (Design note 3/4). If it
  turns out `/health` runs inline on the loop under `ASGITransport`, the anyio pool is not
  being exercised and a separate-process variant is required instead: follow
  `tests/test_two_instance_smoke.py:452-543`'s `Instance` class (a **subprocess** pattern
  driving an in-process `TestClient` over line-delimited JSON — the repo runs no uvicorn in a
  thread anywhere), and record the deviation in the story report.
- **Mirror**: `tests/test_query_router.py:775-828` for the thread-name spy technique.
- **Validate**: `pytest -q tests/test_pipeline_concurrency.py`

### Task 10: Full suite, and prove no thread or pool leaked

- **File**: —
- **Action**: VERIFY
- **Implement**: Run the whole suite. Then confirm this module leaves nothing behind: run
  `pytest -q tests/test_pipeline_concurrency.py tests/test_pipeline_executor.py` in that
  order — the executor tests assert lazy creation and settings-based sizing
  (`tests/test_pipeline_executor.py:50,57`), so a pool left alive at the wrong size is
  precisely what they catch.
- **Validate**: `pytest -q tests/` — green, and no arm takes anywhere near `_HARD_TIMEOUT`

---

## End-to-End Tests

- [ ] `pytest -q tests/test_pipeline_concurrency.py` — all four CI arms pass, the manual smoke
      reports `skipped`
- [ ] `HARNESS_SLOW_SMOKE=1 pytest -q tests/test_pipeline_concurrency.py -k manual_smoke -s`
      against the 60 s local server — ten chat sends in flight, `/health` measured, the printed
      timings captured for the story report (AC 5)
- [ ] `pytest -q tests/test_pipeline_executor.py tests/test_query_router.py tests/test_chat_state.py tests/test_chat_history_send.py`
      — unchanged and green, proving the new fixture leaves no pool behind
- [ ] `pytest -q tests/` — full suite green, no hang, no test-ordering dependency

## Validation

```bash
python -c "from app.main import app"
pytest -q tests/test_pipeline_concurrency.py
pytest -q tests/test_pipeline_concurrency.py tests/test_pipeline_executor.py
HARNESS_SLOW_SMOKE=1 pytest -q tests/test_pipeline_concurrency.py -k manual_smoke -s
pytest -q tests/
```

There is no linter or formatter in this repo; "validate" is pytest against the local libSQL
dev server (`docker ps` → `harness-libsql-dev`).

---

## Risks + Mitigations

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | A regression hangs the suite instead of failing it | Every wait is `asyncio.wait_for(..., _HARD_TIMEOUT)` and the stub's own `release.wait(timeout=_HARD_TIMEOUT)` raises. No unbounded wait anywhere. `pytest-timeout` is not installed, so this is the only mechanism available |
| 2 | A blocked `pipeline-*` thread leaks into later tests | The fixture releases every stub **before** `pipeline_executor.shutdown()`, which joins (`wait=True`); Task 10 proves it by running `test_pipeline_executor.py` after this module |
| 3 | `shutdown(wait=True)` deadlocks teardown | The same ordering rule, stated in Design note 2 and commented in the fixture |
| 4 | Identical prompts trip PRD-009's duplicate check, so an arm's ten calls are not ten upstream calls | Every prompt carries a `uuid4()` (Design note 5) |
| 5 | Ten concurrent audit writes contend on libSQL | `app/db/database.py:74-123`'s single process-wide client serializes worker threads by design; if fixture errors appear en masse, restart `harness-libsql-dev` rather than bisecting |
| 6 | `ASGITransport` does not exercise the anyio threadpool the way uvicorn does — and no test in this repo has used it before | Task 9 asserts it explicitly; the documented fallback is `test_two_instance_smoke.py`'s subprocess `Instance` pattern, since nothing here runs uvicorn in a thread |
| 7 | A single `ChatState` silently swallows nine of ten sends via the `pending` guard | Ten separate instances (Design note 6), and the arm asserts all ten produced assistant bubbles |
| 8 | The chat arm silently takes the `run_query` branch and proves nothing about history | The arm sets `CHAT_HISTORY_ENABLED` and gives every state an active session, and says so in a comment (Task 6) |
| 9 | The manual smoke's 60 s delay trips the upstream timeout | `OPENROUTER_TIMEOUT_SECONDS` defaults to 120 s (PRD 9.3); the arm asserts the setting rather than assuming it |

---

## Acceptance Criteria

(Copied from story `STORY-014`)

- [ ] Given the new `tests/test_pipeline_concurrency.py` with `PIPELINE_MAX_WORKERS=16` and an
      injected upstream that blocks on a `threading.Event` for the first ten calls, when ten
      `POST /query` requests are issued concurrently through
      `httpx.AsyncClient(transport=ASGITransport(app))` and the test waits until all ten are
      inside the stub, then `GET /health` returns 200 in < 1 s
- [ ] Given the same ten blocked calls, when an eleventh `POST /query` is sent (the stub
      returns immediately for it), then it returns `SUCCESS` in < 1 s. After the event is set,
      all ten complete with `SUCCESS` and each writes exactly one audit row
- [ ] Given ten blocked sends issued through `ChatState._do_send` (the history path, with an
      active session), when they are in flight, then `GET /health` and a `/query` call each
      still complete in < 1 s
- [ ] Given a control run with `PIPELINE_MAX_WORKERS=10` and ten blocked calls, when an
      eleventh pipeline call is made, then it waits (it does not complete before release)
      while `/health` still answers. This documents T6 (saturation queues and does not fail)
      as intended
- [ ] Given a manual smoke against a local HTTP server delaying 60 s (pointed at via a
      monkeypatched `_API_URL`), when ten chat sends and a `/health` probe run, then the
      timings are recorded in the story report. This step is not in CI
- [ ] All tasks completed
- [ ] No production file changed
- [ ] Full suite green, no hang, and `tests/test_pipeline_executor.py` still passes when run
      after this module
- [ ] Follows existing patterns
