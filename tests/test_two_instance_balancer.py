"""The balancer in front of two real instances (PRD-019 STORY-007, F3, D8, D9).

A sibling of `tests/test_two_instance_smoke.py`, not an extension: that file
drives two in-process app instances over a pipe and has no network between the
client and the app. This one puts the shipped `deploy/lb/Caddyfile` (only its
upstream line replaced, `tests/_balancer_stack.py`) in front of two uvicorn
processes of the real app and a scripted OpenRouter stub, and asserts what only
a balancer in the path can break: stickiness, the shared usage limits, status
codes and `Retry-After` passing through untouched, and the balancer's own 503.

Run with `CADDY_BIN` set (or caddy on PATH); `HARNESS_REQUIRE_CADDY=1` turns a
missing binary into a failure instead of a skip.

Deviations from the plan's first sketch, all accepted by the orchestrator:

1. **There is no 429.** `/query` answers a usage-limit refusal `200` +
   `status: BLOCKED` (D5) and `/v1` maps it to `403 permission_error`. The
   status table asserts those, and the limit rows use the token budget.
2. **Success bodies are compared after blanking a closed set of per-call keys**
   (`audit_id`, `audit_ref`, and on `/v1` `id`, `created`); every non-success
   body is compared byte for byte.
3. **Kill is `kill_tree` plus a port-closed check** (`tests/e2e/_live.py`): a
   venv python on Windows is a launcher, and `Popen.kill()` orphans uvicorn.
4. **`RBAC_ENABLED=false` and `PII_REDACTION_ENABLED=false` in the children**:
   see `tests/_balancer_stack.py` for the reason of each.
5. **The forced-503 breaker has a frozen clock** (`tests/_lb_instance.py`), so
   `Retry-After` is 10 on both calls.
6. **The schema is restored per test** by POSTing `/__test__/init-db` to both
   children: conftest drops every table before each `db` test.

STORY-008 adds three tests on three stacks: drain on the module `balancer`, the
100 s calls and SSE keep-alives on a `FrontedBalancer` (lb Caddy -> a front Caddy
running the repo `Caddyfile` -> uvicorn), and an instance kill on its own
`Balancer`. Timings come from deploy/lb/Caddyfile (`HEALTH_INTERVAL_S`,
`LB_TRY_DURATION_S`), never restated.

Invariants held (as `_INVARIANTS` at the bottom): no bare sleep, every wait is a
deadline loop; latency is asserted only where the contract is a latency (the kill
test: PRD-019 D4 `lb_try_duration`; the keep-alive cadence: D6); every child
killed on teardown, and gone (port closed) after each stack stops.
"""

import os
import re
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests._balancer_stack import (  # noqa: E402
    DEFAULT_SCRIPT,
    HEALTH_INTERVAL_S,
    LB_TRY_DURATION_S,
    Balancer,
    FrontedBalancer,
    wait_until,
)
from tests.e2e._live import port_closed_within  # noqa: E402
from tests.e2e.docker_smoke_probe import _timed_stream, keepalive_problems  # noqa: E402

from app.db.database import get_connection, insert_user, set_user_limits  # noqa: E402
from app.db.models import User  # noqa: E402
from app.services.identity import hash_token  # noqa: E402

_USER_ID = "balancer@empresa.com"
_USER_TOKEN = "balancer-user-token"
_CAPPED_ID = "capped@empresa.com"
_CAPPED_TOKEN = "balancer-capped-token"

# PRD-019 F3 (amended after STORY-004): the balancer's own 503 bodies, restated
# from tests/test_lb_caddyfile.py (not derived).
_V1_BODY = (
    '{"error":{"message":"Service unavailable. Retry after the Retry-After '
    'interval.","type":"api_error","param":null,"code":"service_unavailable"}}'
)
_DETAIL_BODY = '{"detail":"Service unavailable"}'

# Per-call by design: a fresh audit row id and timestamp on every success.
_PER_CALL_KEYS = frozenset({"audit_id", "audit_ref", "id", "created"})

_FRESH_WINDOW_MARGIN_S = 15
_RATE_LIMIT = 5
_RATE_ATTEMPTS = 10

_ENDPOINTS = ("/query", "/v1/chat/completions")

# PRD-019 D4: an unready instance leaves rotation within health_interval x 2
# (one tick plus the probe's own wait), measured from the drain-file touch.
_DRAIN_DEADLINE_S = HEALTH_INTERVAL_S * 2

# Same cadence and tolerance as tests/test_docker_smoke.py:56-57.
_KEEPALIVE_S = 10.0
_TOLERANCE_S = 2.0

# A delay rule that did not fire would make a "100 s call" return at once.
_LONG_CALL_MIN_S = 95


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def balancer(database_url_factory, tmp_path_factory):
    """stub + two instances + the balancer, started once for the module.

    `database_url_factory` rather than `database_url`: a module-scoped fixture
    cannot request a function-scoped one (`tests/conftest.py:889`).
    """
    stack = Balancer(
        database_url_factory("two_instance_balancer"),
        tmp_path_factory.mktemp("balancer"),
        # STORY-008 drain case: only a prompt with this tag is slow, so the
        # STORY-007 prompts are unaffected.
        script={
            "rules": [{"contains": "drain-slow", "delay_seconds": 25, "content": "ok"}],
            **DEFAULT_SCRIPT,
        },
    )
    try:
        stack.start()
        yield stack
    finally:
        _stop_and_assert_gone(stack)


@pytest.fixture
def fronted(database_url_factory, tmp_path_factory):
    """The 100 s calls and SSE: lb Caddy -> front Caddy (repo Caddyfile) -> uvicorn."""
    script = {
        "rules": [
            {"contains": "slow-100", "delay_seconds": 100, "content": "late"},
            {"contains": "slow-30", "delay_seconds": 30, "content": "late"},
        ],
        **DEFAULT_SCRIPT,
    }
    stack = FrontedBalancer(
        database_url_factory("two_instance_balancer_fronted"),
        tmp_path_factory.mktemp("fronted"),
        script=script,
        # tests/test_docker_smoke.py:56: the keep-alive cadence the test expects
        instance_env={"V1_SSE_KEEPALIVE_SECONDS": "10"},
    )
    try:
        stack.start()
        _prepare(stack)
        yield stack
    finally:
        _stop_and_assert_gone(stack)


@pytest.fixture
def killable(database_url_factory, tmp_path_factory):
    """Its own stack: the kill case must never poison the module's instances."""
    stack = Balancer(
        database_url_factory("two_instance_balancer_kill"),
        tmp_path_factory.mktemp("killable"),
    )
    try:
        stack.start()
        _prepare(stack)
        yield stack
    finally:
        _stop_and_assert_gone(stack)


def _prepare(stack) -> None:
    """Schema and counters for an extra stack, after conftest's per-test drop
    (same reason as `fresh_schema`)."""
    for instance in stack.instances:
        instance.init_db()
        instance.reset_counters()


def _stop_and_assert_gone(stack) -> None:
    """PRD-019 STORY-008: stop the stack, then every child is dead and its port closed.
    `stop()` must not raise for an instance the test already killed."""
    children = stack.all_children()
    stack.stop()
    for child in children:
        assert not child.alive(), f"{child.name} still running after stop()"
        assert port_closed_within(child.port, 5), f"{child.name}: port {child.port} still open"


@pytest.fixture(autouse=True)
def fresh_schema(balancer):
    """Restores the schema conftest's autouse reset just dropped, and clears the
    per-test state the children keep (counters, breaker, drain flags)."""
    for index, instance in enumerate(balancer.instances):
        balancer.undrain(index)
        instance.init_db()
        instance.reset_breaker()
        instance.reset_counters()


@pytest.fixture
def user(balancer):
    insert_user(User(user_id=_USER_ID, role="user", token_hash=hash_token(_USER_TOKEN)))
    return _USER_TOKEN


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

_counter = [0]


def _unique(tag: str) -> str:
    _counter[0] += 1
    return f"{tag} {os.getpid()} {time.time_ns()} {_counter[0]}"


def _send(base: str, endpoint: str, kind: str, token=None, cookie=None, tag="x"):
    """One request from a fresh client (a cookie jar would make cookie-less
    requests sticky). `kind`: ok | bad_body."""
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if cookie is not None:
        headers["Cookie"] = cookie
    prompt = _unique(tag)
    if endpoint == "/query":
        body = {"prompt": prompt} if kind == "ok" else {}
    else:
        body = (
            {"model": "openai/gpt-4o", "messages": [{"role": "user", "content": prompt}]}
            if kind == "ok"
            else {"model": "openai/gpt-4o", "messages": []}
        )
    with httpx.Client(trust_env=False, timeout=60) as client:
        return client.post(f"{base}{endpoint}", json=body, headers=headers)


def _blank(value):
    if isinstance(value, dict):
        return {k: (None if k in _PER_CALL_KEYS else _blank(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_blank(v) for v in value]
    return value


def _cookie_pair(response: httpx.Response):
    """`harness_lb=<hex>` from the Set-Cookie lines, or None. A 503 may carry two."""
    for line in response.headers.get_list("set-cookie"):
        match = re.match(r"(harness_lb=[^;]+)", line)
        if match:
            return match.group(1)
    return None


def _pin_cookie(balancer, index: int) -> str:
    """Cookie-less `GET /health` through the balancer until instance `index` took it."""
    instance = balancer.instances[index]
    for _ in range(40):
        before = instance.counters().get("/health", 0)
        with httpx.Client(trust_env=False, timeout=10) as client:
            response = client.get(f"{balancer.lb_base}/health")
        if instance.counters().get("/health", 0) > before:
            cookie = _cookie_pair(response)
            assert cookie, response.headers
            return cookie
    pytest.fail(f"40 cookie-less requests never reached instance {index}")


def _fresh_rate_window() -> None:
    """Steps off a minute boundary before the rate batch (copy of
    tests/test_two_instance_smoke.py:1964). The one clock wait in this file."""

    def second() -> int:
        with get_connection() as conn:
            return conn.execute(
                "SELECT CAST(strftime('%s','now') AS INTEGER) % 60 AS s"
            ).fetchone()["s"]

    now = second()
    if 60 - now < _FRESH_WINDOW_MARGIN_S:
        time.sleep(60 - now + 1)
        assert second() < now, "the database's minute did not roll over"


def _capped_user():
    """A user whose daily token budget (1) one success burns (the stub reports 2 tokens)."""
    insert_user(User(user_id=_CAPPED_ID, role="user", token_hash=hash_token(_CAPPED_TOKEN)))
    assert set_user_limits(_CAPPED_ID, token_budget_daily=1)


def _burn_budget(balancer):
    _capped_user()
    burned = _send(balancer.instances[0].base, "/query", "ok", token=_CAPPED_TOKEN, tag="burn")
    assert burned.json()["status"] == "SUCCESS", burned.text


def _count(instance, path: str) -> int:
    return instance.counters().get(path, 0)


# --------------------------------------------------------------------------
# AC 1, AC 5 (tail): the stack is up and the probes keep their contracts
# --------------------------------------------------------------------------


def test_stack_is_up_and_the_probes_keep_their_contracts(balancer):
    with httpx.Client(trust_env=False, timeout=10) as client:
        health = client.get(f"{balancer.lb_base}/health")
        ready = client.get(f"{balancer.lb_base}/ready")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "breaker": "closed"}
    assert ready.headers["cache-control"] == "no-store"


# --------------------------------------------------------------------------
# AC 2: cookie-less requests spread, the cookie pins
# --------------------------------------------------------------------------


def test_twenty_cookieless_queries_reach_both_instances_and_the_cookie_pins_one(
    balancer, user
):
    a, b = balancer.instances
    first_cookie = None
    for n in range(20):
        response = _send(balancer.lb_base, "/query", "ok", token=user, tag=f"spread {n}")
        assert response.status_code == 200 and response.json()["status"] == "SUCCESS"
        if first_cookie is None:
            first_cookie = _cookie_pair(response)
    served = (_count(a, "/query"), _count(b, "/query"))
    assert min(served) > 0, f"one instance got nothing: {served}"
    assert sum(served) == 20, served
    assert first_cookie, "the first response carried no harness_lb cookie"

    a.reset_counters()
    b.reset_counters()
    for n in range(10):
        response = _send(
            balancer.lb_base, "/query", "ok", token=user, cookie=first_cookie, tag=f"pinned {n}"
        )
        assert response.json()["status"] == "SUCCESS"
    pinned = sorted((_count(a, "/query"), _count(b, "/query")))
    assert pinned == [0, 10], pinned


# --------------------------------------------------------------------------
# AC 3: the limit is the user's, not an instance's
# --------------------------------------------------------------------------


def test_a_rate_limit_of_five_admits_five_of_ten_through_the_balancer(balancer, user):
    a, b = balancer.instances
    cookies = [_pin_cookie(balancer, 0), _pin_cookie(balancer, 1)]
    assert set_user_limits(_USER_ID, requests_per_minute=_RATE_LIMIT)
    a.reset_counters()
    b.reset_counters()
    _fresh_rate_window()

    bodies = []
    for n in range(_RATE_ATTEMPTS):
        response = _send(
            balancer.lb_base, "/query", "ok", token=user, cookie=cookies[n % 2], tag=f"rate {n}"
        )
        assert response.status_code == 200, response.text  # D5: BLOCKED rides a 200
        bodies.append(response.json())
    admitted = [x for x in bodies if x["status"] == "SUCCESS"]
    refused = [x for x in bodies if x["status"] == "BLOCKED"]
    assert len(admitted) == _RATE_LIMIT, bodies
    assert len(refused) == _RATE_ATTEMPTS - _RATE_LIMIT, bodies
    assert {x["limit"] for x in refused} == {"requests"}, refused
    assert (_count(a, "/query"), _count(b, "/query")) == (5, 5)


# --------------------------------------------------------------------------
# AC 4: the status table, a balanced call equals a direct call
# --------------------------------------------------------------------------

# (case id, endpoint, request kind, token, expected status)
_TABLE = [
    ("query-success", "/query", "ok", "user", 200),
    ("query-no-token", "/query", "ok", None, 401),
    ("query-bad-token", "/query", "ok", "bad", 401),
    ("query-empty-body", "/query", "bad_body", "user", 422),
    ("query-budget", "/query", "ok", "capped", 200),
    ("v1-success", "/v1/chat/completions", "ok", "user", 200),
    ("v1-no-token", "/v1/chat/completions", "ok", None, 401),
    ("v1-bad-token", "/v1/chat/completions", "ok", "bad", 401),
    ("v1-empty-messages", "/v1/chat/completions", "bad_body", "user", 400),
    ("v1-budget", "/v1/chat/completions", "ok", "capped", 403),
]


@pytest.mark.parametrize(
    "endpoint,kind,who,expected,success",
    [pytest.param(e, k, w, s, i.endswith("-success"), id=i) for i, e, k, w, s in _TABLE],
)
def test_status_table_matches_a_direct_call(
    balancer, user, endpoint, kind, who, expected, success
):
    a = balancer.instances[0]
    token = {"user": user, "capped": _CAPPED_TOKEN, "bad": "not-a-token", None: None}[who]
    if who == "capped":
        _burn_budget(balancer)
    cookie = _pin_cookie(balancer, 0)
    a.reset_counters()

    direct = _send(a.base, endpoint, kind, token=token, tag="direct")
    before = _count(a, endpoint)
    balanced = _send(balancer.lb_base, endpoint, kind, token=token, cookie=cookie, tag="balanced")
    assert _count(a, endpoint) == before + 1, "the balanced call did not reach instance a"

    assert direct.status_code == expected, direct.text
    assert balanced.status_code == direct.status_code, (balanced.text, direct.text)
    assert balanced.headers.get("retry-after") == direct.headers.get("retry-after")
    assert balanced.headers.get("content-type") == direct.headers.get("content-type")
    assert balanced.headers.get("x-should-retry") == direct.headers.get("x-should-retry")
    if success:
        # Success bodies differ per call by design: blank the closed key set.
        assert _blank(balanced.json()) == _blank(direct.json())
    else:
        assert balanced.content == direct.content


def test_an_instance_503_arrives_byte_identical_and_it_stays_in_rotation(balancer, user):
    a = balancer.instances[0]
    cookie = _pin_cookie(balancer, 0)
    # The shipped 5 s /ready probe sees an open breaker and would take A out of
    # rotation; the window is a few ms, so retry a bounded number of times.
    for attempt in range(1, 4):
        a.force_breaker_open()
        a.reset_counters()
        results = {}
        for endpoint in _ENDPOINTS:
            direct = _send(a.base, endpoint, "ok", token=user, tag="direct503")
            balanced = _send(
                balancer.lb_base, endpoint, "ok", token=user, cookie=cookie, tag="balanced503"
            )
            results[endpoint] = (direct, balanced)
        # one direct + one balanced per endpoint, so a count of 2 means both landed
        reached = all(_count(a, e) == 2 for e in _ENDPOINTS)
        if reached:
            break
        a.reset_breaker()
        wait_until(
            lambda: _count_after_cookie_probe(balancer, cookie) is True,
            30, "instance a back in rotation before the next attempt",
        )
    else:
        pytest.fail("the balanced call never reached instance a with its breaker open (3 attempts)")
    print(f"forced-503 attempts needed: {attempt}")

    for endpoint, (direct, balanced) in results.items():
        assert direct.status_code == 503, (endpoint, direct.text)
        assert balanced.status_code == 503, (endpoint, balanced.text)
        assert balanced.headers["retry-after"] == direct.headers["retry-after"] == "10"
        assert balanced.content == direct.content, endpoint
        assert balanced.headers["content-type"] == direct.headers["content-type"]

    a.reset_breaker()
    wait_until(
        lambda: _count_after_cookie_probe(balancer, cookie) is True,
        30, "instance a selected again after the breaker closed",
    )


def _count_after_cookie_probe(balancer, cookie: str) -> bool:
    """True once a `GET /health` carrying `cookie` increments instance a."""
    a = balancer.instances[0]
    before = _count(a, "/health")
    with httpx.Client(trust_env=False, timeout=10) as client:
        client.get(f"{balancer.lb_base}/health", headers={"Cookie": cookie})
    return _count(a, "/health") > before


# --------------------------------------------------------------------------
# AC 5: no instance ready, the balancer answers with its own 503 (last: it waits)
# --------------------------------------------------------------------------


def test_both_instances_not_ready_get_the_balancers_own_503(balancer, user):
    try:
        for index in range(2):
            balancer.drain(index)

        def own_503() -> bool:
            with httpx.Client(trust_env=False, timeout=10) as client:
                response = client.get(f"{balancer.lb_base}/health")
            return response.status_code == 503 and response.text == _DETAIL_BODY

        # the active probe runs every 5 s and each poll can wait 5 s itself
        wait_until(own_503, 40, "the balancer's own 503 once both instances drained")

        query = _send(balancer.lb_base, "/query", "ok", token=user)
        v1 = _send(balancer.lb_base, "/v1/chat/completions", "ok", token=user)
        for response, body in ((query, _DETAIL_BODY), (v1, _V1_BODY)):
            assert response.status_code == 503
            assert response.headers["retry-after"] == "10"
            assert response.headers["content-type"].startswith("application/json")
            assert response.text == body
    finally:
        for index in range(2):
            balancer.undrain(index)
        wait_until(
            lambda: httpx.get(f"{balancer.lb_base}/ready", timeout=10).status_code == 200,
            30, "the balancer ready again after un-draining",
        )


# --------------------------------------------------------------------------
# STORY-008: drain, kill, long calls and SSE keep-alives
# --------------------------------------------------------------------------


def _insert_user() -> str:
    insert_user(User(user_id=_USER_ID, role="user", token_hash=hash_token(_USER_TOKEN)))
    return _USER_TOKEN


def _reaches(balancer, instance) -> bool:
    """One cookie-less `GET /health`; true when `instance` took it."""
    before = _count(instance, "/health")
    with httpx.Client(trust_env=False, timeout=10) as client:
        client.get(f"{balancer.lb_base}/health")
    return _count(instance, "/health") > before


def test_a_request_in_flight_on_a_drained_instance_completes_and_nothing_new_reaches_it(
    balancer, user
):
    a, b = balancer.instances
    cookie = _pin_cookie(balancer, 0)
    result = {}

    def slow_call():
        try:
            result["response"] = _send(
                balancer.lb_base, "/query", "ok", token=user, cookie=cookie, tag="drain-slow"
            )
        except Exception as exc:  # noqa: BLE001 - reported by the main thread
            result["error"] = exc

    a.reset_counters()
    b.reset_counters()
    thread = threading.Thread(target=slow_call)
    try:
        thread.start()
        wait_until(lambda: _count(a, "/query") == 1, 15, "the slow call reaching instance a")
        # Counter deltas, not totals: read right before the probes.
        a_before, b_before = _count(a, "/query"), _count(b, "/query")

        t_touch = time.monotonic()
        balancer.drain(0)
        # Not a bare sleep: wait out D4's window, measured from the touch.
        wait_until(
            lambda: time.monotonic() >= t_touch + _DRAIN_DEADLINE_S,
            _DRAIN_DEADLINE_S + 5, "the drain window (health_interval x 2) elapsing",
            interval=0.1,
        )
        # In flight when the drain window closed (it started before the touch).
        assert thread.is_alive(), "the call ended before the drain window did: no overlap proven"

        for n in range(10):
            response = _send(balancer.lb_base, "/query", "ok", token=user, tag=f"after-drain {n}")
            assert response.status_code == 200 and response.json()["status"] == "SUCCESS"
        for n in range(5):
            response = _send(
                balancer.lb_base, "/query", "ok", token=user, cookie=cookie, tag=f"pinned-drain {n}"
            )
            assert response.status_code == 200 and response.json()["status"] == "SUCCESS"

        assert _count(a, "/query") - a_before == 0, "a request reached the drained instance"
        assert _count(b, "/query") - b_before == 15
    finally:
        balancer.undrain(0)
        thread.join(60)
        # The 40-try _pin_cookie loop is faster than one 5 s health tick.
        wait_until(
            lambda: _reaches(balancer, a), 30, "instance a back in rotation after un-draining"
        )
    assert "error" not in result, result.get("error")
    done = result["response"]
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "SUCCESS", done.text


def test_killing_an_instance_fails_no_request_through_the_balancer(killable):
    token = _insert_user()
    b = killable.instances[1]
    cookie_a = _pin_cookie(killable, 0)
    killable.kill_instance(0)
    window_end = time.monotonic() + HEALTH_INTERVAL_S + 5

    failures, posts, n = [], 0, 0
    # PRD-019 D4: a failed dial is retried on the other instance within lb_try_duration.
    ceiling = LB_TRY_DURATION_S + 2
    while time.monotonic() < window_end:
        cookie = cookie_a if n < 3 else None
        is_get = n % 2 == 0
        kind = "GET /health" if is_get else "POST /query"
        started = time.monotonic()
        try:
            if is_get:
                headers = {"Cookie": cookie} if cookie else {}
                with httpx.Client(trust_env=False, timeout=30) as client:
                    response = client.get(f"{killable.lb_base}/health", headers=headers)
            else:
                posts += 1
                response = _send(
                    killable.lb_base, "/query", "ok", token=token, cookie=cookie, tag="kill"
                )
            took = time.monotonic() - started
            if response.status_code != 200 or took >= ceiling:
                failures.append((n, kind, response.status_code, round(took, 2)))
        except httpx.HTTPError as exc:
            failures.append((n, kind, repr(exc), round(time.monotonic() - started, 2)))
        n += 1
    assert n >= 6, f"only {n} requests in the window"
    assert not failures, f"(n, kind, status, seconds): each must be 200 under {ceiling}s: {failures}"
    assert _count(b, "/query") == posts, (_count(b, "/query"), posts)


def test_long_calls_and_sse_keepalives_through_both_caddies(fronted):
    token = _insert_user()
    results = {}

    def run(label, fn):
        started = time.monotonic()
        try:
            results[label] = (fn(), time.monotonic() - started)
        except Exception as exc:  # noqa: BLE001 - asserted below, per call
            results[label] = (exc, time.monotonic() - started)

    def v1_call():
        with httpx.Client(trust_env=False, timeout=180) as client:  # > D6's 150 s, finite
            return client.post(
                f"{fronted.lb_base}/v1/chat/completions",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "model": "openai/gpt-4o",
                    "messages": [{"role": "user", "content": _unique("slow-100 v1")}],
                },
            )

    def query_call():
        with httpx.Client(trust_env=False, timeout=180) as client:
            return client.post(
                f"{fronted.lb_base}/query",
                headers={"Authorization": f"Bearer {token}"},
                json={"prompt": _unique("slow-100 query")},
            )

    def stream_call():
        # The shared probe helper keeps httpx's default trust_env.
        return _timed_stream(fronted.lb_base, token, _unique("slow-30 stream"), "gzip")

    threads = [
        threading.Thread(target=run, args=(label, fn))
        for label, fn in (("v1", v1_call), ("query", query_call), ("stream", stream_call))
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(200)
    assert not any(thread.is_alive() for thread in threads), "a call outlived 200 s"

    v1, v1_s = results["v1"]
    assert not isinstance(v1, Exception), repr(v1)
    assert v1.status_code == 200, v1.text
    assert v1.json()["choices"][0]["message"]["content"] == "late"
    assert v1_s >= _LONG_CALL_MIN_S, f"/v1 took {v1_s:.1f}s: the stub delay rule did not fire"

    query, query_s = results["query"]
    assert not isinstance(query, Exception), repr(query)
    assert query.status_code == 200, query.text
    assert query.json()["status"] == "SUCCESS", query.text
    assert query_s >= _LONG_CALL_MIN_S, f"/query took {query_s:.1f}s: the stub delay rule did not fire"

    timing, _ = results["stream"]
    assert not isinstance(timing, Exception), repr(timing)
    shown = f"timing: {timing}"
    assert not keepalive_problems(timing, _KEEPALIVE_S, _TOLERANCE_S, minimum=2), shown
    assert timing["content_type"].startswith("text/event-stream"), shown
    assert timing["done"], shown
    # The gzip hop (the front Caddy's `encode gzip`) is proven, not assumed.
    assert timing["content_encoding"] == "gzip", shown


_INVARIANTS = (
    "no bare sleep: every wait is a deadline loop",
    "latency asserted only where the contract is one (kill: lb_try_duration; keep-alive cadence)",
    "every child killed on teardown, also after a failed start, and gone after stop()",
    "nothing under app/ changes",
)
