"""PRD-022 STORY-017: OpenRouter is down, Anthropic answers, the breaker opens.

Nothing here is in-process. Two copies of the stub upstream
(`scripts/stub_openrouter.py`: Chat mode as OpenRouter, Messages mode as
Anthropic) and `uvicorn app.main:app` run as subprocesses on ephemeral ports.
`PROVIDERS_FILE` names an `openrouter` and an `anthropic-direct` provider and
`PROVIDER_CHAINS_FILE` chains them. The client is the official OpenAI SDK.

One ordered scenario against ONE harness process (breakers and counters are per
process), as in `test_openai_sdk.py`. The OpenRouter stub fails every request
with 503; the Anthropic stub answers a `bash` tool call unless the prompt says
`total outage`, when it fails 503 too.

    AC 1  the first request is answered by Anthropic: canonical tool arguments,
          `X-Harness-Provider`, `harness.attempts == 2`, two audit rows
    AC 2  after the breaker threshold the next request never reaches OpenRouter
    AC 3  both breakers open: a retryable 502 `upstream_unavailable` with
          `Retry-After`, zero stub hits, one row with the skips
    AC 4  `GET /providers/status` reports both breakers open and the counters
    AC 5  skipped without `--run-e2e` (tests/conftest.py)

**The breaker stays open 10 s** (`health._BREAKER_OPEN_SECONDS`, a module
constant: no setting moves it). Everything from the request that opens
OpenRouter's breaker to the `/providers/status` read must fit in that window,
so those requests run back to back with no subprocess between them, and a guard
fails with a clear message when the machine is too slow. The audit rows are
read at the end (a child per read, 1-2 s each), after the window.

**Storage only in children** (the `test_openai_sdk.py` rule): user bootstrap and
the final row dump run as subprocesses against `HARNESS_E2E_LIBSQL_URL`; the
rows read in the window come over `GET /audit`. Every prompt carries a run nonce
and a counter, so the duplicate checker never rejects one.

Run (skipped without `--run-e2e`; needs `pip install -r requirements-e2e.txt`):

    docker run -d --name harness-libsql-e2e022 -p 8088:8080 -e SQLD_NODE=primary ghcr.io/tursodatabase/libsql-server:latest
    HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088 python -m pytest tests/e2e/test_failover.py -m e2e --run-e2e -v
    docker rm -f harness-libsql-e2e022
"""

import ast
import json
import re
import secrets
import time

import httpx
import pytest

from tests.e2e import _live

openai = pytest.importorskip("openai")

pytestmark = pytest.mark.e2e

REPO_ROOT = _live.REPO_ROOT
_SCRIPTS = REPO_ROOT / "tests" / "e2e" / "scripts"
_OR_SCRIPT = _SCRIPTS / "failover_openrouter.json"
_ANT_SCRIPT = _SCRIPTS / "failover_anthropic.json"
_HEALTH = REPO_ROOT / "app" / "services" / "upstream" / "health.py"
_OR_MODEL = "anthropic/claude-sonnet-4.6"
_ANT_MODEL = "anthropic-direct/claude-sonnet-4-6"
_ANT_UPSTREAM = "claude-sonnet-4-6"
_RECIPE = (
    "docker run -d --name harness-libsql-e2e022 -p 8088:8080 -e SQLD_NODE=primary "
    "ghcr.io/tursodatabase/libsql-server:latest, then "
    "HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088"
)

NONCE = secrets.token_hex(4)
#: Seconds of the open window kept as margin before the exhaustion step.
_WINDOW_MARGIN = 3.0

_TOOLS = [{
    "type": "function",
    "function": {
        "name": "bash",
        "description": "run a shell command",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}},
    },
}]

_REGISTRY = """\
version: 1
default_model: {or_model}
providers:
  - name: openrouter
    label: OpenRouter
    type: openai_compatible
    base_url: {or_base}
    insecure_http: true
    key_env: E2E_OR_KEY
    trust: external
    usage_missing: estimate
    models:
      - id: {or_model}
        capabilities: {{tools: true}}
  - name: anthropic-direct
    type: anthropic
    base_url: {ant_base}
    insecure_http: true
    key_env: E2E_ANT_KEY
    trust: external
    usage_missing: estimate
    models:
      - id: {ant_model}
        upstream: {ant_upstream}
        default_max_tokens: 256
        capabilities: {{tools: true}}
"""

_CHAINS = """\
version: 1
chains:
  - match:
      model: {or_model}
    candidates:
      - model: {or_model}
      - model: {ant_model}
"""


def _breaker_constants() -> tuple:
    """(failure threshold, open seconds) read from health.py by AST, never imported.

    Importing `app.services` here would build `Settings()` and read `.env`
    (`_live.py`), and the values must not be hard-coded: they are the harness's.
    """
    found = {}
    for node in ast.parse(_HEALTH.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ("_BREAKER_FAILURE_THRESHOLD", "_BREAKER_OPEN_SECONDS"):
                found[node.targets[0].id] = ast.literal_eval(node.value)
    assert set(found) == {"_BREAKER_FAILURE_THRESHOLD", "_BREAKER_OPEN_SECONDS"}, found
    assert isinstance(found["_BREAKER_FAILURE_THRESHOLD"], int)
    assert isinstance(found["_BREAKER_OPEN_SECONDS"], (int, float))
    return found["_BREAKER_FAILURE_THRESHOLD"], float(found["_BREAKER_OPEN_SECONDS"])


THRESHOLD, OPEN_SECONDS = _breaker_constants()


# --------------------------------------------------------------------------
# Fixtures: database, user, two stubs, harness (plumbing in tests/e2e/_live.py)
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def e2e_db_url():
    return _live.resolve_e2e_db_url(_RECIPE)


@pytest.fixture(scope="module")
def child_cwd(tmp_path_factory):
    """A directory with no `.env`, so no child reads the developer's settings."""
    return tmp_path_factory.mktemp("e2e022")


@pytest.fixture(scope="module")
def child_env(e2e_db_url):
    def build(**extra) -> dict:
        return _live.child_env(e2e_db_url, **extra)

    return build


@pytest.fixture(scope="module")
def run_child(child_cwd, child_env):
    def run(*args: str):
        return _live.run_child(child_cwd, child_env(), *args)

    return run


@pytest.fixture(scope="module")
def user(run_child):
    """(user_id, token): the one client of this module."""
    user_id = f"e2e022-main-{NONCE}"
    return user_id, _live.create_user(run_child, user_id)


@pytest.fixture(scope="module")
def or_stub(child_cwd):
    with _live.start_stub(_OR_SCRIPT, child_cwd) as running:
        yield running


@pytest.fixture(scope="module")
def ant_stub(child_cwd):
    with _live.start_stub(_ANT_SCRIPT, child_cwd) as running:
        yield running


@pytest.fixture(scope="module")
def harness(user, or_stub, ant_stub, child_cwd, child_env):
    """`uvicorn app.main:app` on a free port. After `user`: startup refuses an empty users table."""
    registry = child_cwd / "providers.yaml"
    registry.write_text(
        _REGISTRY.format(
            or_model=_OR_MODEL, or_base=or_stub.base, ant_model=_ANT_MODEL,
            ant_upstream=_ANT_UPSTREAM,
            # The Anthropic provider takes the base without `/v1` (the SDK adds it).
            ant_base=ant_stub.base.removesuffix("/v1"),
        ),
        encoding="utf-8",
    )
    chains = child_cwd / "chains.yaml"
    chains.write_text(_CHAINS.format(or_model=_OR_MODEL, ant_model=_ANT_MODEL), encoding="utf-8")
    policy = child_cwd / "action_policy.yaml"
    policy.write_text(
        "# PRD-022 STORY-017: the one allowlisted command the Anthropic stub answers with.\n"
        "workspace:\n"
        "  roots:\n"
        f'    - "{child_cwd.as_posix()}"\n'
        "shell:\n"
        "  allow:\n"
        "    - npm test\n",
        encoding="utf-8",
    )
    env = child_env(
        PROVIDERS_FILE=str(registry),
        PROVIDER_CHAINS_FILE=str(chains),
        OPENROUTER_API_KEY="",
        E2E_OR_KEY="e2e-or-unused-key",
        E2E_ANT_KEY="e2e-ant-unused-key",
        RBAC_ENABLED="true",
        V1_ENABLED="true",
        V1_TOOLS_ENABLED="true",
        ACTION_POLICY_FILE=str(policy),
        USAGE_REQUESTS_PER_MINUTE="*=unlimited",
    )
    with _live.start_harness(child_cwd, env) as running:
        yield running


@pytest.fixture(scope="module")
def client(harness, user):
    # max_retries=0, unlike test_openai_sdk.py (which asserts the SDK default of 2):
    # a 502 `upstream_unavailable` is retryable, so the SDK would resend it and
    # multiply the stub hits this module counts exactly.
    return openai.OpenAI(base_url=f"{harness.base}/v1", api_key=user[1], max_retries=0)


@pytest.fixture(scope="module")
def state():
    """What the ordered tests hand to each other."""
    return {"counter": 0}


def _prompt(state: dict, text: str) -> list:
    state["counter"] += 1
    return [{"role": "user", "content": f"{text} [{NONCE}-{state['counter']}]"}]


def _ask(client, state: dict, text: str):
    """One tools request, raw: the SDK's parsed completion plus the response headers."""
    return client.chat.completions.with_raw_response.create(
        model=_OR_MODEL, messages=_prompt(state, text), tools=_TOOLS,
    )


def _audit(harness, **params) -> list:
    reply = httpx.get(
        f"{harness.base}/audit", params=params,
        headers={"Authorization": f"Bearer {harness.admin_token}"}, timeout=10,
    )
    assert reply.status_code == 200, f"GET /audit {params} -> {reply.status_code}"
    return reply.json()["queries"]


def _answer_row(harness, completion_id: str) -> dict:
    """The audit row a buffered answer points at (`completion_id` is stored only for real-time streams).

    The module writes a few dozen rows, well under `/audit`'s page of 100.
    """
    audit_id = _audit_id(completion_id)
    [row] = [entry for entry in _audit(harness) if entry["audit_id"] == audit_id]
    return row


def _audit_id(completion_id: str) -> int:
    match = re.fullmatch(r"chatcmpl-harness-(\d+)", completion_id)
    assert match, f"unexpected completion id {completion_id!r}"
    return int(match.group(1))


# --------------------------------------------------------------------------
# The scenario, in definition order
# --------------------------------------------------------------------------


def test_first_request_is_answered_by_anthropic_with_two_audit_rows(client, harness, or_stub, ant_stub, state):
    """AC 1: OpenRouter fails 503, Anthropic answers; the client sees canonical arguments."""
    raw = _ask(client, state, "failover first request")
    completion = raw.parse()
    choice = completion.choices[0]

    assert choice.finish_reason == "tool_calls"
    assert choice.message.tool_calls[0].function.name == "bash"
    assert choice.message.tool_calls[0].function.arguments == '{"command":"npm test"}'
    assert completion.model == _ANT_MODEL
    assert raw.headers["x-harness-provider"] == "anthropic-direct"
    provenance = completion.model_extra["harness"]
    assert provenance["provider"] == "anthropic-direct"
    assert provenance["attempts"] == 2

    answered = _answer_row(harness, completion.id)
    rows = sorted(_audit(harness, request_id=answered["request_id"]), key=lambda row: row["attempt"])
    assert [row["attempt"] for row in rows] == [1, 2]
    failed, answer = rows
    assert (failed["provider"], failed["route_model"]) == ("openrouter", _OR_MODEL)
    assert (answer["provider"], answer["upstream_model"]) == ("anthropic-direct", _ANT_UPSTREAM)
    assert answer["provider_trust"] == "external"
    assert answer["fallback_reason"] == "status_503"
    assert len(or_stub.settle()) == 1
    assert len(ant_stub.settle()) == 1
    state["first_request_id"] = answered["request_id"]


def test_breaker_opens_at_the_threshold_and_openrouter_is_not_called(client, harness, or_stub, ant_stub, state):
    """AC 2: `threshold` consecutive failures open OpenRouter's breaker; the next request skips it."""
    for index in range(THRESHOLD - 1):  # R1 was the first failure
        completion = _ask(client, state, f"failover warm-up {index}").parse()
        assert completion.model == _ANT_MODEL
    state["opened_at"] = time.monotonic()  # the window opened at the last of those requests
    # Settling costs 0.3 s per stub: it is spent before the skipped request is
    # measured, inside the window (the guard in the next test counts it).
    or_before = len(or_stub.settle())
    ant_before = len(ant_stub.settle())
    assert or_before == THRESHOLD, "OpenRouter should have been called once per request so far"

    completion = _ask(client, state, "failover with the breaker open").parse()

    assert completion.model == _ANT_MODEL
    assert len(or_stub.settle()) - or_before == 0, "an open breaker must not reach OpenRouter"
    assert len(ant_stub.settle()) - ant_before == 1
    assert completion.model_extra["harness"]["attempts"] == 1  # OpenRouter was skipped, not attempted
    row = _answer_row(harness, completion.id)
    assert row["attempt"] == 1
    assert row["provider"] == "anthropic-direct"
    assert row["skipped_providers"] == "openrouter:open"


def test_total_outage_is_a_retryable_502_with_zero_stub_hits(client, or_stub, ant_stub, state):
    """AC 3: OpenRouter skipped, Anthropic failing 503 until its own breaker opens, then nothing is called."""
    for index in range(THRESHOLD):
        with pytest.raises(openai.APIStatusError) as caught:
            _ask(client, state, f"failover total outage {index}")
        assert caught.value.status_code == 502
        assert caught.value.code == "upstream_unavailable"
    elapsed = time.monotonic() - state["opened_at"]
    assert elapsed < OPEN_SECONDS - _WINDOW_MARGIN, (
        f"too slow for the breaker cooldown: {elapsed:.1f} s of the {OPEN_SECONDS:g} s open window "
        f"are gone before the exhaustion step; rerun on an idle machine"
    )
    or_before = len(or_stub.settle())
    ant_before = len(ant_stub.settle())

    with pytest.raises(openai.APIStatusError) as caught:
        _ask(client, state, "failover everything is down")
    exhausted = caught.value
    assert exhausted.status_code == 502
    assert exhausted.code == "upstream_unavailable", exhausted.body
    retry_after = exhausted.response.headers["retry-after"]
    assert retry_after.isdigit() and 1 <= int(retry_after) <= OPEN_SECONDS
    assert "x-should-retry" not in exhausted.response.headers
    assert len(or_stub.settle()) - or_before == 0
    assert len(ant_stub.settle()) - ant_before == 0
    state["window_elapsed_at_exhaustion"] = time.monotonic() - state["opened_at"]


def test_providers_status_matches_what_happened(harness, state):
    """AC 4: both breakers open; the counters equal what the scenario did."""
    reply = httpx.get(
        f"{harness.base}/providers/status",
        headers={"Authorization": f"Bearer {harness.admin_token}"}, timeout=10,
    )
    state["window_elapsed_at_status"] = time.monotonic() - state["opened_at"]
    assert reply.status_code == 200, reply.text
    status = reply.json()

    for name in ("openrouter", "anthropic-direct"):
        breaker = status["providers"][name]["breaker"]
        assert breaker["state"] == "open", (name, breaker)
        assert breaker["consecutive_failures"] >= THRESHOLD
        assert breaker["last_failure_class"] == "status"  # a 503 is `UpstreamError.kind == "status"`
    counters = status["counters"]
    assert counters["breaker_opens"] == 2
    # One per request answered by a candidate after the first attempt: R1..R5. R6 was answered
    # by Anthropic as its FIRST attempt (OpenRouter skipped), so it is not a fallback answer.
    assert counters["fallback_answers"] == THRESHOLD
    assert counters["attempts_failed"] == {
        "openrouter:status": THRESHOLD,
        "anthropic-direct:status": THRESHOLD,
    }
    # R6 and the THRESHOLD outage requests and R12 met OpenRouter's open breaker; only R12 met Anthropic's.
    assert counters["skipped"] == {"openrouter:open": 1 + THRESHOLD + 1, "anthropic-direct:open": 1}
    assert state["window_elapsed_at_status"] < OPEN_SECONDS, "the status read fell outside the open window"


def test_failed_attempts_are_rows_without_prompt_or_answer_text(run_child, user, state):
    """The rows behind the figures: failures carry a kind and a status, never text (T10)."""
    rows = _live.dump_rows(run_child, user[0])
    by_request: dict = {}
    for row in rows:
        by_request.setdefault(row["request_id"], []).append(row)

    first = sorted(by_request[state["first_request_id"]], key=lambda row: row["attempt"])
    failed, answer = first
    assert failed["success"] is False
    # The adapter's wording: the provider `label`, then the HTTP client's status text (no body, T10).
    assert failed["error_message"].startswith("OpenRouter request failed:"), failed["error_message"]
    assert "503" in failed["error_message"]
    assert answer["success"] is True
    assert failed["model_used"] == answer["model_used"] == _OR_MODEL

    # The exhausted request: no attempt ran, one row on the primary's columns with the skips (F7, F8).
    exhausted = max((row for row in rows if row["attempt"] is None), key=lambda row: row["id"])
    assert exhausted["success"] is False
    assert exhausted["provider"] == "openrouter"
    assert exhausted["skipped_providers"] == "openrouter:open,anthropic-direct:open"
    assert exhausted["error_message"], "the exhausted row should say why"
    for row in rows:
        for text in (row["error_message"] or "",):
            assert "e2e-or-unused-key" not in text and "e2e-ant-unused-key" not in text

    # The whole open-window part of the run, for the story report.
    print(
        f"\ne2e022: open window used {state['window_elapsed_at_status']:.2f} s of {OPEN_SECONDS:g} s "
        f"at the status read ({state['window_elapsed_at_exhaustion']:.2f} s at the exhaustion step)"
    )
