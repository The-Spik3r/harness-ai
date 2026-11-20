"""Anthropic as a primary through the pipeline (PRD-022 STORY-008).

The real `AnthropicAdapter` against the STORY-006 stub in Messages mode, through
`/v1` (buffered, TestClient) and the realtime ASGI driver. Covers dropped params
on the success row (6.5, D4), cache tokens and the charge (D10), the tool loop,
refusal and the realtime reasoning gates. An `openai_compatible` provider on the
same stub is the control for "off means PRD-020/021".
"""

import ast
import asyncio
import importlib.util
import io
import sys
import threading
from uuid import uuid4
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.services.authz as authz
from app.config import settings
from app.db.database import get_audit_log, get_connection, insert_user
from app.db.models import User
from app.main import app
from app.services import action_policy, provider_registry, query_pipeline
from app.services.identity import hash_token
from app.services.upstream import UpstreamRequest, GenerationParams, dropped_params_for
from tests import test_v1_realtime as rtm
from tests._providers import provider_file  # noqa: F401  (fixture)

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("stub_openrouter_under_test_primary", _ROOT / "scripts" / "stub_openrouter.py")
stub_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = stub_mod
_spec.loader.exec_module(stub_mod)

_USER = "juan@empresa.com"
_TOKEN = "test-user-token"
_HEADERS = {"Authorization": f"Bearer {_TOKEN}"}
_PATH = "/v1/chat/completions"
_SUBMIT = authz.PERMISSION_QUERY_SUBMIT
_RT = authz.PERMISSION_STREAM_REALTIME
_RV = authz.PERMISSION_REASONING_VIEW

_TOOL = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": "run a command",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}},
    },
}


def _yaml(port):
    return f"""
version: 1
default_model: claude-x
providers:
  - name: ant
    label: Ant
    type: anthropic
    base_url: http://127.0.0.1:{port}
    insecure_http: true
    key_env: ANT_KEY_ENV
    byok: false
    usage_missing: estimate
    models:
      - id: claude-x
        upstream: claude-up
        default_max_tokens: 256
        capabilities: {{tools: true, streaming: true, reasoning: true}}
  - name: oai
    label: Oai
    type: openai_compatible
    base_url: http://127.0.0.1:{port}/v1
    insecure_http: true
    key_env: ANT_KEY_ENV
    byok: false
    usage_missing: estimate
    models:
      - id: oai/m
        upstream: up-oai
        capabilities: {{tools: true, streaming: true, reasoning: true}}
"""


@pytest.fixture
def rig(temp_db, provider_file, monkeypatch):
    """A stub on a free port, an `ant` and an `oai` provider on it; closed at teardown."""
    insert_user(User(user_id=_USER, role="user", token_hash=hash_token(_TOKEN)))
    monkeypatch.setenv("ANT_KEY_ENV", "sk-ant-STUBKEY-123")
    for name, value in (
        ("USAGE_LIMITS_ENABLED", True),
        ("USAGE_REQUESTS_PER_MINUTE", "*=600"),
        ("USAGE_DAILY_TOKEN_BUDGET", "*=1000000"),
        ("PII_REDACTION_ENABLED", False),
        ("STREAMING_ENABLED", True),
        ("V1_TOOLS_ENABLED", True),
        ("STREAM_COALESCE_MS", 0),
    ):
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(authz, "ROLE_PERMISSIONS", {"user": {_SUBMIT, _RT, _RV}})
    started = []

    def start(script):
        server = stub_mod.make_server(stub_mod.parse_script(script), log=io.StringIO())
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        started.append((server, thread))
        provider_file(_yaml(server.server_address[1]))
        return server

    yield start
    for server, thread in started:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _client():
    return TestClient(app, headers=_HEADERS)


def _msg(prompt=None, model="claude-x", **extra):
    return {"model": model, "messages": [{"role": "user", "content": prompt or f"hello {uuid4()}"}], **extra}


def _rows():
    with get_connection() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM audit_logs ORDER BY id").fetchall()]
    return [get_audit_log(i) for i in ids]


@pytest.fixture
def charges(monkeypatch):
    seen = []
    monkeypatch.setattr(query_pipeline, "charge", lambda *args: seen.append(args))
    return seen


def _hits(server, endpoint, other):
    hits = server.endpoint_hits()
    assert hits[endpoint] >= 1 and hits[other] == 0, hits


# --- pure ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("edge", "dropped", "expected"),
    [
        ("presence_penalty", ("temperature",), "presence_penalty,temperature@ant"),
        ("temperature@ant", ("temperature",), "temperature@ant"),
        (None, ("temperature", "top_p"), "temperature@ant,top_p@ant"),
        (None, (), None),
        ("presence_penalty", (), "presence_penalty"),
    ],
)
def test_merge_ignored_params(edge, dropped, expected):
    route = type("R", (), {"provider": type("P", (), {"name": "ant"})()})()
    assert query_pipeline._merge_ignored_params(edge, dropped, route) == expected


def test_merge_ignored_params_without_a_route_keeps_the_edge_value():
    assert query_pipeline._merge_ignored_params("a", ("temperature",), None) == "a"


def test_every_upstream_request_in_app_passes_the_model():
    """PRD-022 STORY-008: a request built without `model=` hides the dropped-params rule."""
    bad = []
    for path in (_ROOT / "app").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "UpstreamRequest":
                if len(node.args) < 5 and "model" not in {k.arg for k in node.keywords}:
                    bad.append(f"{path.name}:{node.lineno}")
    assert bad == []


def test_dropped_params_for_dispatches_on_the_provider_type(rig):
    rig({"rules": [], "default": {"content": "x"}})
    params = GenerationParams(temperature=0.5, top_p=0.9)
    ant = provider_registry.resolve("claude-x")
    oai = provider_registry.resolve("oai/m")
    assert dropped_params_for(ant, UpstreamRequest((), "up", params, None, ant.model)) == (
        "temperature",
        "top_p",
    )
    # sampling_params False on an OpenAI-compatible model is not a drop (D4).
    assert oai.model.capabilities.sampling_params is False
    assert dropped_params_for(oai, UpstreamRequest((), "up", params, None, oai.model)) == ()


# --- buffered /v1 ----------------------------------------------------------------


def test_v1_tool_loop_through_an_anthropic_primary(rig, monkeypatch):
    server = rig(
        {
            "rules": [{"role": "tool", "regex": "", "after_call": "bash", "content": "tests pass"}],
            "default": {"tool_calls": [{"name": "bash", "arguments": '{"command": "npm test"}', "id": "toolu_01x"}]},
        }
    )
    seen = []
    real = action_policy.evaluate_all

    def spy(calls, identity, *args, **kwargs):
        decisions = real(calls, identity, *args, **kwargs)
        seen.append((tuple((c.name, c.arguments) for c in calls), tuple((d.decision, d.rule) for d in decisions)))
        return decisions

    monkeypatch.setattr(query_pipeline.action_policy, "evaluate_all", spy)
    # `npm test` is unlisted under the built-in policy; the grant lifts the deny so the call is released.
    monkeypatch.setattr(authz, "ROLE_PERMISSIONS", {"user": {_SUBMIT, authz.PERMISSION_ACTION_SHELL_EXEC}})
    client = _client()

    first = client.post(_PATH, json=_msg("run the tests", tools=[_TOOL]))
    assert first.status_code == 200
    choice = first.json()["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    call = choice["message"]["tool_calls"][0]
    # Canonical, unspaced (STORY-005): the model's input re-serialized compactly.
    assert call["function"]["arguments"] == '{"command":"npm test"}'
    assert seen[0][0] == (("bash", '{"command":"npm test"}'),)

    second = client.post(
        _PATH,
        json={
            "model": "claude-x",
            "tools": [_TOOL],
            "messages": [
                {"role": "user", "content": "run the tests"},
                {"role": "assistant", "content": None, "tool_calls": [call]},
                {"role": "tool", "tool_call_id": call["id"], "content": "ok"},
            ],
        },
    )
    assert second.status_code == 200
    assert second.json()["choices"][0]["message"]["content"] == "tests pass"
    _hits(server, "messages", "chat")

    # Equivalence: the same turn through an OpenAI-compatible route is decided alike.
    client.post(_PATH, json=_msg("run the tests again", model="oai/m", tools=[_TOOL]))
    assert seen[1][1] == seen[0][1]
    rows = _rows()
    assert [r.has_tool_calls for r in rows[:2]] == [True, True]


def test_temperature_is_recorded_as_ignored_on_the_success_row(rig):
    rig({"rules": [], "default": {"content": "ok"}})
    client = _client()

    assert client.post(_PATH, json=_msg(temperature=0.7, presence_penalty=0.1)).status_code == 200
    assert client.post(_PATH, json=_msg(model="oai/m", temperature=0.7, presence_penalty=0.1)).status_code == 200

    ant, oai = _rows()
    assert ant.ignored_params == "presence_penalty,temperature@ant"
    # Control: an OpenAI-compatible route is byte-identical to PRD-020/021.
    assert oai.ignored_params == "presence_penalty"


def test_an_error_row_keeps_only_the_edge_ignored_params(rig):
    rig({"rules": [], "default": {"fail_status": 503}})

    response = _client().post(_PATH, json=_msg(temperature=0.7, presence_penalty=0.1))

    assert response.status_code >= 500
    (row,) = _rows()
    assert row.success is False and row.ignored_params == "presence_penalty"


def test_cache_usage_lands_on_the_row_and_charge_gets_the_full_prompt(rig, charges):
    usage = {"prompt_tokens": 10, "completion_tokens": 4, "cache_creation_input_tokens": 3, "cache_read_input_tokens": 2}
    server = rig({"rules": [], "default": {"content": "ok", "usage": usage}})
    client = _client()

    assert client.post(_PATH, json=_msg()).status_code == 200

    (row,) = _rows()
    assert (row.cache_write_tokens, row.cache_read_tokens) == (3, 2)
    assert (row.input_tokens, row.output_tokens, row.tokens_used) == (15, 4, 19)
    assert charges[0][2:] == (15, 4, 19)
    _hits(server, "messages", "chat")

    # Control: Chat without cache keys leaves the cache columns NULL.
    assert client.post(_PATH, json=_msg(model="oai/m")).status_code == 200
    control = _rows()[1]
    assert control.cache_write_tokens is None and control.cache_read_tokens is None


def test_refusal_is_content_filter_one_success_row_attempt_one(rig):
    server = rig({"rules": [], "default": {"content": "", "stop_reason": "refusal"}})

    response = _client().post(_PATH, json=_msg())

    assert response.status_code == 200
    assert response.json()["choices"][0]["finish_reason"] == "content_filter"
    (row,) = _rows()
    assert row.success is True and row.attempt == 1
    assert server.endpoint_hits()["messages"] == 1  # no retry


# --- realtime /v1 ----------------------------------------------------------------


async def _rt(body):
    sent = await rtm._drive(body)
    assert rtm._status(sent) == 200
    return rtm._events(sent), rtm._text(sent)


def _rt_body(model="claude-x", **extra):
    return rtm._body(stream=True, **extra) | {"model": model}


@pytest.mark.asyncio
async def test_realtime_reasoning_with_and_without_reasoning_view(rig, charges):
    server = rig({"rules": [], "default": {"content": "answer", "stream": {"reasoning": "think hard"}}})

    parsed, _ = await _rt(_rt_body())
    assert rtm._reasoning(parsed) == "think hard" and rtm._content(parsed) == "answer"
    assert all("reasoning" not in d for d in rtm._deltas(parsed))
    (row,) = await rtm._until_rows(1)
    assert row.reasoning_shown is True and row.streamed_realtime is True

    authz_grants = {"user": {_SUBMIT, _RT}}
    authz.ROLE_PERMISSIONS = authz_grants  # restored by the fixture's monkeypatch
    parsed, text = await _rt(_rt_body())
    assert "think hard" not in text and rtm._content(parsed) == "answer"
    rows = await rtm._until_rows(2)
    assert rows[1].reasoning_shown is False
    _hits(server, "messages", "chat")


@pytest.mark.asyncio
async def test_realtime_records_dropped_params_and_cache_usage(rig, charges):
    usage = {"prompt_tokens": 10, "completion_tokens": 4, "cache_creation_input_tokens": 3, "cache_read_input_tokens": 2}
    server = rig({"rules": [], "default": {"content": "answer", "usage": usage}})

    await _rt(_rt_body(temperature=0.7))
    await _rt(_rt_body(model="oai/m", temperature=0.7))

    ant, oai = await rtm._until_rows(2)
    assert ant.ignored_params == "temperature@ant" and ant.streamed_realtime is True
    assert (ant.cache_write_tokens, ant.cache_read_tokens) == (3, 2)
    assert charges[0][2:] == (15, 4, 19)
    # Control: the OpenAI-compatible route records nothing extra.
    assert oai.ignored_params is None
    assert server.endpoint_hits()["messages"] >= 1


@pytest.mark.asyncio
async def test_realtime_refusal_is_a_success_row_content_filter(rig):
    rig({"rules": [], "default": {"content": "", "stop_reason": "refusal"}})

    parsed, _ = await _rt(_rt_body())

    finishes = [p["choices"][0]["finish_reason"] for k, p in parsed if k == "data" and p != "[DONE]" and p["choices"]]
    assert "content_filter" in finishes
    (row,) = await rtm._until_rows(1)
    assert row.success is True and row.attempt == 1
