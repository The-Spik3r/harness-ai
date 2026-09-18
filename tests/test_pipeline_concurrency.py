"""PRD-010 STORY-014: ten blocked upstream calls stall nothing else.

`tests/test_pipeline_executor.py` proves the executor in isolation and
`tests/test_query_router.py::test_pipeline_body_runs_on_dedicated_executor_thread`
proves the pipeline body runs on it. This module proves the thing an operator
would notice, and the thing the PRD's MVP definition actually promises (Section
11, *Concurrency*): with ten upstream calls stuck inside the pipeline pool,
`GET /health` and a fast `POST /query` still answer in under a second -- through
both ingresses, the `/query` router and `ChatState._do_send` on its history path.

**Blocking is a `threading.Event`, never a sleep.** The stub below parks the
first N calls on an event and announces its arrival on a `Condition`, so a test
waits for "all ten are genuinely inside the upstream" as a fact rather than as an
elapsed duration. Nothing here sleeps to let progress happen. Every wait is
bounded -- `asyncio.wait_for(..., _HARD_TIMEOUT)` in the tests, a `timeout=` on
the event wait in the stub -- because `pytest-timeout` is not installed, so a
regression that reintroduces the stall must fail this suite rather than hang it.

**The release-before-shutdown order in `pipeline_pool` is load-bearing.**
`pipeline_executor.shutdown()` joins its threads (`wait=True`), so a teardown
that shut the pool down while ten workers were still parked on the event would
deadlock the suite rather than clean up after it. The fixture releases every stub
it handed out first, and only then shuts down -- see the comments there before
reordering.

**The repo's first `httpx.ASGITransport` user.** Every other suite drives the app
through `fastapi.testclient.TestClient`, which runs the app on its own worker
thread and would not let a test hold ten requests open while issuing an eleventh
from the same coroutine. The story names `AsyncClient(transport=ASGITransport(app))`
for exactly that reason. It changes nothing about where the app puts its work:
Starlette still routes a sync endpoint through `run_in_threadpool`, which
`test_health_answers_while_ten_query_calls_are_blocked` asserts outright rather
than assumes, so "the anyio pool stayed free" is a claim this suite proves about
the same pool uvicorn would use.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import asyncio
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.db.database import get_connection, insert_user
from app.db.models import User
from app.main import app
from app.services import chat_sessions, pipeline_executor
from app.services.identity import hash_token, resolve
from app.services.openrouter_client import OpenRouterResult

import chat_ui.chat_ui.state as chat_state_mod
from chat_ui.chat_ui.formatting import derive_title
from chat_ui.chat_ui.state import ChatState

_AUTH_USER_ID = "juan@empresa.com"
_AUTH_TOKEN = "test-user-token"
_AUTH_HEADERS = {"Authorization": f"Bearer {_AUTH_TOKEN}"}

#: Every wait in this module is bounded by this, so a regression fails in ten
#: seconds instead of hanging a CI run. It is deliberately far larger than
#: anything a healthy run needs -- it is a backstop, not a measurement.
_HARD_TIMEOUT = 10.0

#: The PRD's "< 1 s" (Section 11, MVP definition), which is what `/health` and a
#: fast `/query` must come back within while ten calls are blocked.
_FAST = 1.0

_BLOCKED = 10


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


def _prompt(i: int) -> str:
    """A prompt no other call in this suite will match.

    PRD-009's duplicate check keys on the conversation, so ten identical
    concurrent prompts would come back `BLOCKED` without ever reaching the
    upstream -- and "all ten completed with SUCCESS" would then be false for a
    reason that has nothing to do with concurrency.
    """
    return f"concurrency probe {i} {uuid4()}"


# --------------------------------------------------------------------------
# The upstream stubs
# --------------------------------------------------------------------------


class _BlockingUpstream:
    """An injected `call_openrouter` that parks its first `block_first` callers.

    Mirrors the real signature (`tests/test_query_router.py:804`), so it can be
    dropped into either binding: `app.routers.query.call_openrouter` for the
    router arms, `chat_ui.chat_ui.state.call_openrouter` for the chat arm.
    """

    def __init__(self, block_first: int) -> None:
        self.block_first = block_first
        self.release = threading.Event()
        self._cond = threading.Condition()
        #: How many callers have arrived, blocked or not. The (block_first+1)-th
        #: is the "fast" one every arm relies on.
        self.calls = 0
        #: How many are parked on the event right now.
        self.in_stub = 0

    def __call__(self, messages, model="gpt-4", api_key=None) -> OpenRouterResult:
        with self._cond:
            self.calls += 1
            blocking = self.calls <= self.block_first
            if blocking:
                self.in_stub += 1
                self._cond.notify_all()
        if blocking:
            # Bounded, so a test that forgets to release fails here instead of
            # parking an executor thread until the run is killed.
            if not self.release.wait(timeout=_HARD_TIMEOUT):
                raise AssertionError("blocked upstream was never released")
        return OpenRouterResult(response="ok", model_used=model, tokens_used=1)

    def wait_until_blocked(self, n: int) -> None:
        """Block until `n` callers are parked inside. Synchronous on purpose.

        Tests reach it through `asyncio.to_thread`, so the event loop stays free
        while the test waits -- which matters, because the whole claim under
        test is about what the loop and the shared threadpool can still do.
        """
        deadline = time.monotonic() + _HARD_TIMEOUT
        with self._cond:
            while self.in_stub < n:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not self._cond.wait(timeout=remaining):
                    raise AssertionError(
                        f"only {self.in_stub} of {n} calls reached the upstream"
                    )


def _fast_upstream(messages, model="gpt-4", api_key=None) -> OpenRouterResult:
    """An upstream that never blocks, for the call that must stay fast.

    Used where a test needs the *other* ingress answered quickly by
    construction rather than by luck.
    """
    return OpenRouterResult(response="ok", model_used=model, tokens_used=1)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def pipeline_pool(monkeypatch):
    """A pipeline executor of a chosen size, plus the stub that will fill it.

    `pipeline_executor.shutdown()` is also the reset: it sets `_executor = None`
    and `_get_executor()` builds the next one lazily from
    `settings.PIPELINE_MAX_WORKERS`, so a size override only takes effect if the
    current pool is discarded first. Same reasoning as
    `tests/test_pipeline_executor.py`'s `_reset_executor`, extended with the
    release the blocking stub makes necessary.
    """
    handed_out: list[_BlockingUpstream] = []

    def configure(workers: int, block_first: int) -> _BlockingUpstream:
        monkeypatch.setattr(settings, "PIPELINE_MAX_WORKERS", workers)
        # Before the body, not only after: whatever size an earlier test left
        # behind would otherwise serve this one and the arm would silently
        # measure the wrong pool.
        pipeline_executor.shutdown()
        stub = _BlockingUpstream(block_first)
        handed_out.append(stub)
        return stub

    try:
        yield configure
    finally:
        # Release first, shut down second. `shutdown(wait=True)` joins its
        # threads, so shutting down while ten workers are still parked on the
        # event deadlocks the teardown -- the suite would hang here rather than
        # fail. Do not reorder these two lines.
        for stub in handed_out:
            stub.release.set()
        pipeline_executor.shutdown()


def _make_state() -> ChatState:
    state = ChatState(_reflex_internal_init=True)
    state.user_id = _AUTH_USER_ID
    state._token = _AUTH_TOKEN
    return state


async def _send(state: ChatState, text: str) -> None:
    state.input_text = text
    handler = type(state).event_handlers["send"]
    await handler.fn(state)  # bypasses the background-task chain guard


def _client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers=_AUTH_HEADERS,
    )


async def _blocked_query_tasks(client, stub, n=_BLOCKED, start=0):
    """Fire `n` `/query` requests and return once all `n` are inside the stub."""
    tasks = [
        asyncio.create_task(client.post("/query", json={"prompt": _prompt(start + i)}))
        for i in range(n)
    ]
    await asyncio.wait_for(
        asyncio.to_thread(stub.wait_until_blocked, n), _HARD_TIMEOUT
    )
    return tasks


def _assert_all_succeeded(responses) -> None:
    for response in responses:
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "SUCCESS"


# --------------------------------------------------------------------------
# AC 1: /health answers while ten /query calls are blocked
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_answers_while_ten_query_calls_are_blocked(
    temp_db, monkeypatch, pipeline_pool
):
    """The PRD's MVP line: ten calls to a 60 s model, `/health` in milliseconds.

    Also the module's one assertion that `ASGITransport` exercises the pool this
    claim is about. `/health` is a sync `def` (`app/main.py:27-29`), so Starlette
    must hand it to anyio's threadpool -- the shared pool `POST /query` stopped
    drawing on when STORY-006 moved its body to the dedicated executor. If the
    endpoint ran inline on the event loop here, this suite would be measuring a
    pool uvicorn does not use, so the thread name is recorded rather than
    trusted.
    """
    stub = pipeline_pool(workers=16, block_first=_BLOCKED)
    monkeypatch.setattr("app.routers.query.call_openrouter", stub)

    health_threads: list[str] = []
    # The spy goes on the route's `dependant.call`, not on `app.main.health`:
    # the route captured the function object at import time, so patching the
    # module attribute would record nothing. FastAPI decides sync-vs-async once,
    # when the route is built (`get_request_handler`'s `is_coroutine`), and
    # calls `dependant.call` per request -- so a sync spy installed here is
    # dispatched through `run_in_threadpool` exactly as the real endpoint is.
    health_route = next(
        route for route in app.routes if getattr(route, "path", None) == "/health"
    )
    real_health = health_route.dependant.call

    def _spy_health():
        health_threads.append(threading.current_thread().name)
        return real_health()

    monkeypatch.setattr(health_route.dependant, "call", _spy_health)

    async with _client() as client:
        tasks = await _blocked_query_tasks(client, stub)

        started = time.monotonic()
        health = await asyncio.wait_for(client.get("/health"), _HARD_TIMEOUT)
        elapsed = time.monotonic() - started

        assert health.status_code == 200
        assert health.json() == {"status": "ok"}
        assert elapsed < _FAST, f"/health took {elapsed:.3f}s while ten calls blocked"

        # Not `MainThread`: the sync endpoint went to anyio's threadpool, which
        # is the pool this whole story is about keeping free.
        assert health_threads and all(
            name != "MainThread" for name in health_threads
        ), health_threads

        stub.release.set()
        responses = await asyncio.wait_for(asyncio.gather(*tasks), _HARD_TIMEOUT)

    _assert_all_succeeded(responses)


# --------------------------------------------------------------------------
# AC 2: an eleventh /query succeeds in < 1 s; every call writes exactly one row
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eleventh_query_succeeds_while_ten_are_blocked(
    temp_db, monkeypatch, pipeline_pool
):
    """Sixteen workers, ten parked: the eleventh request is served immediately.

    The audit census at the end is the story's "each writes exactly one audit
    row", stated over the whole table rather than per request -- which is only
    meaningful because `temp_db` hands out an empty database
    (`tests/conftest.py:155-205`).
    """
    stub = pipeline_pool(workers=16, block_first=_BLOCKED)
    monkeypatch.setattr("app.routers.query.call_openrouter", stub)

    async with _client() as client:
        tasks = await _blocked_query_tasks(client, stub)

        started = time.monotonic()
        eleventh = await asyncio.wait_for(
            client.post("/query", json={"prompt": _prompt(99)}), _HARD_TIMEOUT
        )
        elapsed = time.monotonic() - started

        assert eleventh.status_code == 200, eleventh.text
        assert eleventh.json()["status"] == "SUCCESS"
        assert elapsed < _FAST, f"the eleventh /query took {elapsed:.3f}s"

        stub.release.set()
        responses = await asyncio.wait_for(asyncio.gather(*tasks), _HARD_TIMEOUT)

    _assert_all_succeeded(responses)
    assert _count_audit_rows() == _BLOCKED + 1


# --------------------------------------------------------------------------
# AC 3: the same, with the ten sends issued through ChatState's history path
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_and_query_answer_while_ten_chat_sends_are_blocked(
    temp_db, monkeypatch, pipeline_pool
):
    """Ten chat tabs waiting on the model; `/health` and `/query` unaffected.

    The history path specifically: `CHAT_HISTORY_ENABLED` on plus a session that
    existed before the send takes `_do_send` into the
    `had_session and settings.CHAT_HISTORY_ENABLED` branch
    (`chat_ui/chat_ui/state.py:1072-1121`), which puts *two* things on the
    dedicated executor -- `chat_history.assemble` and then `run_conversation`.
    Without both conditions the send would take the `run_query` branch and this
    arm would prove the wrong thing.

    Ten `ChatState` instances, not ten sends on one: `_do_send` claims a
    per-instance `pending` flag and returns early if it is already set
    (`chat_ui/chat_ui/state.py:952-954`), so a single state would quietly
    swallow nine of the ten.
    """
    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", True)
    stub = pipeline_pool(workers=16, block_first=_BLOCKED)
    # Two independent bindings of the same name: the chat's is blocked, the
    # router's is not, so the concurrent `/query` below is fast by construction
    # rather than by luck.
    monkeypatch.setattr(chat_state_mod, "call_openrouter", stub)
    monkeypatch.setattr("app.routers.query.call_openrouter", _fast_upstream)

    # Which branch ran is proven, not assumed. Both branches end in an
    # `OpenRouterResult` from the same stub, so an assertion on the result could
    # not tell them apart; a `run_query` that raises can
    # (`tests/test_chat_history_send.py`'s "absence is proven with a raising
    # stub, never with an empty list").
    def _off_path_not_taken(**kwargs):
        raise AssertionError(
            "the send took the single-turn run_query branch, so this arm did "
            "not exercise the history path it claims to"
        )

    monkeypatch.setattr(chat_state_mod, "run_query", _off_path_not_taken)

    identity = resolve(_AUTH_TOKEN)
    assert identity is not None

    states = []
    for i in range(_BLOCKED):
        state = _make_state()
        session_id = chat_sessions.create(identity, f"seed {i}", derive_title)
        assert session_id, "history is on, so a session id is expected here"
        state.active_session_id = session_id
        states.append(state)

    sends = [
        asyncio.create_task(_send(state, _prompt(i))) for i, state in enumerate(states)
    ]
    await asyncio.wait_for(
        asyncio.to_thread(stub.wait_until_blocked, _BLOCKED), _HARD_TIMEOUT
    )

    async with _client() as client:
        started = time.monotonic()
        health = await asyncio.wait_for(client.get("/health"), _HARD_TIMEOUT)
        health_elapsed = time.monotonic() - started
        assert health.status_code == 200
        assert health_elapsed < _FAST, f"/health took {health_elapsed:.3f}s"

        started = time.monotonic()
        query = await asyncio.wait_for(
            client.post("/query", json={"prompt": _prompt(99)}), _HARD_TIMEOUT
        )
        query_elapsed = time.monotonic() - started
        assert query.status_code == 200, query.text
        assert query.json()["status"] == "SUCCESS"
        assert query_elapsed < _FAST, f"/query took {query_elapsed:.3f}s"

    stub.release.set()
    await asyncio.wait_for(asyncio.gather(*sends), _HARD_TIMEOUT)

    # A send that was blocked and then released still lands normally.
    for state in states:
        assert state.messages, "the send produced no bubbles at all"
        assert state.messages[-1].kind == "assistant", state.messages[-1].kind
        assert state.pending is False


# --------------------------------------------------------------------------
# AC 4: saturation queues and does not fail (PRD Section 9.2, T6)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_saturated_pool_queues_the_eleventh_call_while_health_answers(
    temp_db, monkeypatch, pipeline_pool
):
    """The control run: ten workers, ten blocked, so the eleventh must wait.

    This arm asserts *intended* behaviour, not a bug. PRD Section 6.3:
    "Saturation queues and does not fail. With all `PIPELINE_MAX_WORKERS`
    threads waiting upstream, the next pipeline call waits in the executor's
    queue. `/health`, static routes and non-pipeline Reflex events are
    unaffected." Section 9.2's T6 accepts the same trade: resource exhaustion
    moves rather than disappearing, the failure stays contained to pipeline
    calls, and `/health` stays truthful.

    "It waits" is proven as an absence -- the eleventh call never reaches the
    upstream, and does not finish within half a second -- which is not the
    forbidden "sleep until something is in flight": nothing here waits *for*
    progress, and the failure mode is a fast assertion failure rather than a
    hang.
    """
    stub = pipeline_pool(workers=_BLOCKED, block_first=_BLOCKED)
    monkeypatch.setattr("app.routers.query.call_openrouter", stub)

    async with _client() as client:
        tasks = await _blocked_query_tasks(client, stub)

        eleventh = asyncio.create_task(
            client.post("/query", json={"prompt": _prompt(99)})
        )
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(eleventh), 0.5)
        # Every worker is parked, so the eleventh is still in the queue and its
        # body -- the upstream call included -- has not started.
        assert stub.calls == _BLOCKED

        started = time.monotonic()
        health = await asyncio.wait_for(client.get("/health"), _HARD_TIMEOUT)
        elapsed = time.monotonic() - started
        assert health.status_code == 200
        assert elapsed < _FAST, f"/health took {elapsed:.3f}s under saturation"

        stub.release.set()
        responses = await asyncio.wait_for(
            asyncio.gather(eleventh, *tasks), _HARD_TIMEOUT
        )

    _assert_all_succeeded(responses)
    assert _count_audit_rows() == _BLOCKED + 1


# --------------------------------------------------------------------------
# AC 5: the manual smoke against a genuinely slow server (not in CI)
# --------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _SlowHandler(BaseHTTPRequestHandler):
    """Answers an OpenRouter-shaped body, `delay` seconds late.

    Counts arrivals on a class-level `Condition` so the smoke can wait for "all
    ten requests are on the socket" as a fact, the same way `_BlockingUpstream`
    does for the in-process arms. The `time.sleep` below is the *server* being
    slow -- the condition being simulated -- not the test waiting for progress.
    """

    delay = 60.0
    arrivals = 0
    cond = threading.Condition()

    @classmethod
    def reset(cls) -> None:
        with cls.cond:
            cls.arrivals = 0

    @classmethod
    def wait_for_arrivals(cls, n: int, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        with cls.cond:
            while cls.arrivals < n:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not cls.cond.wait(timeout=remaining):
                    raise AssertionError(
                        f"only {cls.arrivals} of {n} requests reached the slow server"
                    )

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler's spelling
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        with _SlowHandler.cond:
            _SlowHandler.arrivals += 1
            _SlowHandler.cond.notify_all()
        time.sleep(self.delay)
        body = json.dumps(
            {
                "choices": [
                    {"message": {"content": "ok"}, "finish_reason": "stop"}
                ],
                "usage": {"total_tokens": 1},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep pytest output clean
        pass


@pytest.mark.skipif(
    not os.environ.get("HARNESS_SLOW_SMOKE"),
    reason="manual: set HARNESS_SLOW_SMOKE=1 (PRD-010 STORY-014 AC 5, out of CI)",
)
@pytest.mark.asyncio
async def test_manual_smoke_against_a_slow_local_server(
    temp_db, monkeypatch, pipeline_pool, capsys
):
    """Ten real HTTP calls to a server that answers 60 s late.

    The arms above stub `call_openrouter` out, so nothing in CI exercises the
    real `httpx` client, the real timeout or a real socket. This one does: the
    *server* delays, which is the condition being simulated, and the pipeline
    blocks on it exactly as it would against a slow model. Out of CI because it
    takes a minute by construction; run it with
    `HARNESS_SLOW_SMOKE=1 pytest -q tests/test_pipeline_concurrency.py -k manual_smoke -s`
    and paste the printed timings into the story report.
    """
    # PRD Section 9.3: the default is 120 s, so a 60 s delay completes rather
    # than tripping the upstream timeout. Asserted, not assumed -- a lowered
    # default would turn this smoke into a test of the timeout instead.
    assert settings.OPENROUTER_TIMEOUT_SECONDS > _SlowHandler.delay

    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", True)
    # The pool must be wide enough for the ten sends, or the smoke would measure
    # queuing (AC 4's subject) instead of concurrency.
    pipeline_pool(workers=16, block_first=0)

    port = _free_port()
    _SlowHandler.reset()
    server = ThreadingHTTPServer(("127.0.0.1", port), _SlowHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setattr(
            "app.services.openrouter_client._API_URL",
            f"http://127.0.0.1:{port}/",
        )

        identity = resolve(_AUTH_TOKEN)
        assert identity is not None

        states = []
        for i in range(_BLOCKED):
            state = _make_state()
            session_id = chat_sessions.create(identity, f"smoke seed {i}", derive_title)
            state.active_session_id = session_id
            states.append(state)

        run_started = time.monotonic()
        sends = [
            asyncio.create_task(_send(state, _prompt(i)))
            for i, state in enumerate(states)
        ]
        # Wait until all ten are genuinely on the socket, on the server's own
        # arrival count rather than on an elapsed duration.
        await asyncio.wait_for(
            asyncio.to_thread(_SlowHandler.wait_for_arrivals, _BLOCKED, 30.0), 60
        )

        async with _client() as client:
            started = time.monotonic()
            health = await asyncio.wait_for(client.get("/health"), _HARD_TIMEOUT)
            health_elapsed = time.monotonic() - started
            assert health.status_code == 200

        # Deliberately no `/query` probe here: every ingress now points at the
        # same 60 s server, so a `/query` would measure the slow upstream rather
        # than the pool's freedom. The in-process arms above already prove
        # `/query` stays fast while ten calls are blocked; what this smoke adds
        # is that the blocking is a real socket rather than a stub.
        await asyncio.wait_for(asyncio.gather(*sends), 180)
        total = time.monotonic() - run_started

        with capsys.disabled():
            print(
                "\n[STORY-014 AC 5 manual smoke]"
                f"\n  upstream delay:        {_SlowHandler.delay:.1f}s"
                f"\n  /health while blocked: {health_elapsed * 1000:.1f}ms"
                f"\n  ten chat sends total:  {total:.2f}s"
            )

        assert health_elapsed < _FAST
        for state in states:
            assert state.messages[-1].kind == "assistant", state.messages[-1].kind
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
