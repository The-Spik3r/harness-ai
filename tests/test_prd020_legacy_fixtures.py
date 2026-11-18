"""PRD-020 STORY-001: the legacy byte-identical fixtures (D1, risk 1).

`tests/fixtures/prd020_legacy/` pins every byte the harness sends upstream and
returns to clients WITHOUT a `PROVIDERS_FILE`. It was recorded against the
unchanged `app/`, through the real `call_openrouter` over `httpx.MockTransport`
and through `TestClient(app)`. STORY-005 (adapter), 007 (routing), 011
(`/v1/models`) and 012 (`/query` default model) must keep this file green
WITHOUT editing a fixture: a failing replay is a legacy regression to report,
never a stale file. The README beside the fixtures says the same.

How the bytes are compared:

- Upstream request bodies are produced by httpx (`json=`), whose whitespace and
  escaping are not ours and `httpx` is unpinned. The body is therefore parsed
  with `json.loads(..., object_pairs_hook=list)` (nested ordered pairs) and
  compared to the fixture parsed the same way: key order, values and types are
  pinned, httpx's formatting is not. Headers are `Authorization`,
  `Content-Type`, the method and the URL path.
- Client-facing responses (`/v1/models*`, `/query`) are produced by our app, so
  the raw `response.content` bytes are compared.
- Error strings built from `str(httpx exception)` carry httpx's own wording, so
  for those cases only the harness-owned prefix, the status, `retryable` and
  the URL are pinned (`message_prefix` / `message_contains`).

Record mode (`PRD020_RECORD_FIXTURES=1`) exists for STORY-001 only: it was run
once, against the unchanged code. A later story must never run it.
"""

import dataclasses
import json
import os
import re
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import insert_user
from app.db.models import User
from app.main import app
import app.routers.query as query_router_module
from app.models.messages import Message, ToolCallSpec
from app.services.identity import hash_token
from app.services.openrouter_client import (
    GenerationParams,
    OpenRouterError,
    ToolParams,
    call_openrouter,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "prd020_legacy"
_RECORD = os.environ.get("PRD020_RECORD_FIXTURES") == "1"

_BASE_URL = "https://openrouter.ai/api/v1"
_SETTINGS_KEY = "test-key"
_CALLER_KEY = "sk-caller-key"  # clearly fake; BYOK cases
_DEFAULT_ALLOWLIST = "gpt-4,claude-3-sonnet,openai/gpt-4o,anthropic/claude-3.5-sonnet"
_POST_PATH = "/api/v1/chat/completions"
_HTTPX_PREFIX = "OpenRouter request failed: "

_ADMIN_TOKEN = "legacy-admin-token"
_USER_TOKEN = "legacy-user-token"
_ADMIN = {"Authorization": f"Bearer {_ADMIN_TOKEN}"}
_USER = {"Authorization": f"Bearer {_USER_TOKEN}"}


@pytest.fixture(autouse=True)
def _pinned_settings(monkeypatch):
    """Fixed inputs: a developer `.env` must not change a fixture.

    The base URL is pinned because httpx error text embeds it. PII redaction is
    off so the /query cases never build the spaCy analyzer; their prompts carry
    no PII, so the bytes sent and returned are the same either way.
    """
    monkeypatch.setattr(settings, "OPENROUTER_BASE_URL", _BASE_URL)
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", _SETTINGS_KEY)
    monkeypatch.setattr(settings, "MODEL_ALLOWLIST", _DEFAULT_ALLOWLIST)
    monkeypatch.setattr(settings, "V1_TOOL_MODELS", "")
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)


# --------------------------------------------------------------------------
# Record / replay helpers
# --------------------------------------------------------------------------


def _path(rel: str) -> Path:
    return _FIXTURES / rel


def _check_bytes(rel: str, actual: bytes) -> None:
    """Record mode writes `actual`; replay asserts it equals the recorded bytes."""
    path = _path(rel)
    if _RECORD:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(actual)
        return
    assert path.exists(), f"missing legacy fixture {rel}"
    assert actual == path.read_bytes(), f"legacy bytes changed: {rel}"


def _dump(obj) -> bytes:
    """Our own deterministic fixture formatting (ASCII, sorted, indent 2)."""
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("ascii")


def _pairs(text) -> object:
    """Nested ordered pairs: pins key order independently of httpx's formatting."""
    return json.loads(text, object_pairs_hook=list)


def _check_ordered_json(rel: str, body: bytes) -> None:
    """An upstream request body: ordered structure, not raw bytes (httpx is unpinned)."""
    path = _path(rel)
    if _RECORD:
        path.parent.mkdir(parents=True, exist_ok=True)
        # json.loads keeps insertion order, so this writes the keys as sent.
        path.write_bytes(
            (json.dumps(json.loads(body), indent=2, ensure_ascii=True) + "\n").encode("ascii")
        )
        return
    assert path.exists(), f"missing legacy fixture {rel}"
    assert _pairs(body) == _pairs(path.read_text(encoding="ascii")), f"legacy payload changed: {rel}"


def _capture(responder):
    """(client, calls): a real httpx.Client over MockTransport, recording each request.

    `responder(request)` returns an httpx.Response or raises. Only the two
    headers the harness sets are kept; httpx's own (user-agent, accept,
    content-length) are not ours to pin.
    """
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(
            {
                "method": request.method,
                "path": request.url.path,
                "url": str(request.url),
                "authorization": request.headers.get("authorization"),
                "content_type": request.headers.get("content-type"),
                "body": request.content,  # raw bytes, for reference only
            }
        )
        return responder(request)

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def _ok(content="Hello from upstream", usage=None, **extra_message):
    usage = {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12} if usage is None else usage
    message = {"role": "assistant", "content": content, **extra_message}
    return httpx.Response(
        200, json={"choices": [{"message": message, "finish_reason": "stop"}], "usage": usage}
    )


def _meta(call: dict) -> dict:
    return {
        "method": call["method"],
        "path": call["path"],
        "authorization": call["authorization"],
        "content_type": call["content_type"],
    }


def _record_upstream(case: str, call: dict) -> None:
    _check_ordered_json(f"upstream/{case}.request.json", call["body"])
    _check_bytes(f"upstream/{case}.meta.json", _dump(_meta(call)))


# --------------------------------------------------------------------------
# AC1: upstream request payload and headers
# --------------------------------------------------------------------------

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }
]


def _call_case(case: str, messages, **kwargs) -> dict:
    client, calls = _capture(lambda request: _ok())
    call_openrouter(messages, client=client, **kwargs)
    assert len(calls) == 1
    return calls[0]


def test_upstream_request_text_minimal():
    call = _call_case("text_minimal", [Message("user", "hello")], model="gpt-4")
    assert call["authorization"] == f"Bearer {_SETTINGS_KEY}"
    assert call["content_type"] == "application/json"
    assert call["path"] == _POST_PATH and call["method"] == "POST"
    assert "stream" not in json.loads(call["body"])
    _record_upstream("text_minimal", call)


def test_upstream_request_text_params():
    messages = [
        Message("system", "be brief"),
        Message("user", "first"),
        Message("assistant", "answer"),
        Message("user", "second"),
    ]
    params = GenerationParams(temperature=0.5, max_tokens=64, top_p=0.9, stop=["END", "STOP"])
    call = _call_case("text_params", messages, model="openai/gpt-4o", params=params)
    assert list(json.loads(call["body"])) == [
        "model", "messages", "temperature", "max_tokens", "top_p", "stop",
    ]
    _record_upstream("text_params", call)


def test_upstream_request_tool_request():
    messages = [
        Message("user", "weather in Paris?"),
        Message(
            "assistant",
            "",
            tool_calls=(ToolCallSpec(id="call_1", name="get_weather", arguments='{"city": "Paris"}'),),
        ),
        Message("tool", "sunny", tool_call_id="call_1"),
    ]
    tools = ToolParams(
        tools=_TOOLS, tool_choice={"type": "function", "function": {"name": "get_weather"}},
        parallel_tool_calls=False,
    )
    call = _call_case("tool_request", messages, model="gpt-4", tools=tools)
    _record_upstream("tool_request", call)


def test_upstream_request_tool_minimal():
    # tool_choice and parallel_tool_calls None: omitted from the payload.
    call = _call_case(
        "tool_minimal", [Message("user", "weather?")], model="gpt-4", tools=ToolParams(tools=_TOOLS)
    )
    assert sorted(json.loads(call["body"])) == ["messages", "model", "tools"]
    _record_upstream("tool_minimal", call)


def test_upstream_request_byok_key():
    call = _call_case(
        "byok_key", [Message("user", "hello")], model="gpt-4", api_key=_CALLER_KEY
    )
    assert call["authorization"] == f"Bearer {_CALLER_KEY}"
    _record_upstream("byok_key", call)


def test_upstream_request_base_url_trailing_slash(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_BASE_URL", _BASE_URL + "/")
    call = _call_case("base_url_trailing_slash", [Message("user", "hello")], model="gpt-4")
    assert call["path"] == _POST_PATH
    # Path only: the body is the minimal case's, already pinned above.
    _check_bytes("upstream/base_url_trailing_slash.meta.json", _dump({"path": call["path"]}))


# --------------------------------------------------------------------------
# AC2: error strings, upstream_status, retryable; and success result fields
# --------------------------------------------------------------------------


def _tool_call_body(raw_calls):
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": None, "tool_calls": raw_calls}}],
            "usage": {"total_tokens": 3},
        },
    )


def _good_call(call_id="c1"):
    return {"id": call_id, "type": "function", "function": {"name": "f", "arguments": "{}"}}


def _json_response(body):
    return httpx.Response(200, json=body)


def _raise(exc):
    def responder(request):
        raise exc

    return responder


_USER_MESSAGES = [Message("user", "hello")]
_ONE_TOOL = ToolParams(tools=_TOOLS)

# case -> (responder, call kwargs, messages)
_ERROR_CASES = {
    "http_400": (lambda r: httpx.Response(400, json={"error": "bad"}), {}),
    "http_429": (lambda r: httpx.Response(429, json={"error": "slow"}), {}),
    "http_503": (lambda r: httpx.Response(503, json={"error": "down"}), {}),
    "transport_timeout": (_raise(httpx.ConnectTimeout("timed out")), {}),
    "transport_connect_error": (_raise(httpx.ConnectError("connection refused")), {}),
    "body_not_json": (lambda r: httpx.Response(200, content=b"not json"), {}),
    "body_no_choices": (lambda r: _json_response({"usage": {"total_tokens": 1}}), {}),
    "choices_empty_list": (lambda r: _json_response({"choices": [], "usage": {"total_tokens": 1}}), {}),
    "message_without_content": (
        lambda r: _json_response({"choices": [{"message": {}}], "usage": {"total_tokens": 1}}), {}
    ),
    "content_null": (
        lambda r: _json_response(
            {"choices": [{"message": {"content": None}, "finish_reason": "length"}],
             "usage": {"total_tokens": 1}}
        ),
        {},
    ),
    "content_null_with_tool_calls_no_tools_sent": (
        lambda r: _tool_call_body([_good_call()]),
        {},
    ),
    "usage_missing": (
        lambda r: _json_response({"choices": [{"message": {"content": "hi"}}]}), {}
    ),
    "usage_without_total_tokens": (
        lambda r: _json_response(
            {"choices": [{"message": {"content": "hi"}}], "usage": {"prompt_tokens": 1}}
        ),
        {},
    ),
    "tool_calls_not_a_list": (lambda r: _tool_call_body("nope"), {"tools": _ONE_TOOL}),
    "tool_call_not_an_object": (lambda r: _tool_call_body(["nope"]), {"tools": _ONE_TOOL}),
    "tool_call_empty_id": (
        lambda r: _tool_call_body([{**_good_call(), "id": ""}]), {"tools": _ONE_TOOL}
    ),
    "tool_call_wrong_type": (
        lambda r: _tool_call_body([{**_good_call(), "type": "other"}]), {"tools": _ONE_TOOL}
    ),
    "tool_call_no_name": (
        lambda r: _tool_call_body([{"id": "c1", "function": {"arguments": "{}"}}]),
        {"tools": _ONE_TOOL},
    ),
    "tool_call_arguments_not_string": (
        lambda r: _tool_call_body([{"id": "c1", "function": {"name": "f", "arguments": {}}}]),
        {"tools": _ONE_TOOL},
    ),
    "tool_call_duplicate_id": (
        lambda r: _tool_call_body([_good_call("dup"), _good_call("dup")]), {"tools": _ONE_TOOL}
    ),
}

# Cases whose message embeds str(httpx exception): httpx's wording is not ours.
_HTTPX_TEXT_CASES = {
    "http_400", "http_429", "http_503", "transport_timeout", "transport_connect_error",
}


def _error_entry(case: str, exc: OpenRouterError) -> dict:
    entry = {"upstream_status": exc.upstream_status, "retryable": exc.retryable}
    message = str(exc)
    if case in _HTTPX_TEXT_CASES:
        assert message.startswith(_HTTPX_PREFIX)
        entry["message_prefix"] = _HTTPX_PREFIX
        if case.startswith("http_"):
            entry["message_contains"] = [f"{_BASE_URL}/chat/completions"]
    else:
        entry["message"] = message
    return entry


def _run_error_case(name: str) -> OpenRouterError:
    responder, kwargs = _ERROR_CASES[name]
    client, _calls = _capture(responder)
    with pytest.raises(OpenRouterError) as excinfo:
        call_openrouter(_USER_MESSAGES, model="gpt-4", client=client, **kwargs)
    return excinfo.value


def _no_http_error_cases() -> dict:
    """The errors raised before any request: empty messages and a missing key."""
    out = {}
    with pytest.raises(OpenRouterError) as excinfo:
        call_openrouter([], model="gpt-4")
    out["messages_empty"] = _error_entry("messages_empty", excinfo.value)
    return out


def test_error_cases_match_recorded(monkeypatch):
    entries = _no_http_error_cases()
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")
    with pytest.raises(OpenRouterError) as excinfo:
        call_openrouter(_USER_MESSAGES, model="gpt-4")
    entries["key_missing"] = _error_entry("key_missing", excinfo.value)
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", _SETTINGS_KEY)

    for name in _ERROR_CASES:
        entries[name] = _error_entry(name, _run_error_case(name))

    # The harness-owned statuses, stated here as well as pinned in the fixture.
    assert (entries["http_400"]["upstream_status"], entries["http_400"]["retryable"]) == (400, False)
    assert (entries["http_429"]["upstream_status"], entries["http_429"]["retryable"]) == (429, True)
    assert (entries["http_503"]["upstream_status"], entries["http_503"]["retryable"]) == (503, True)
    assert (entries["transport_timeout"]["upstream_status"], entries["transport_timeout"]["retryable"]) == (None, True)

    _check_bytes("errors.json", _dump(entries))
    if _RECORD:
        return
    # Each recorded message_contains fragment is really in the message.
    for name in ("http_400", "http_429", "http_503"):
        assert entries[name]["message_contains"][0] in str(_run_error_case(name))


def test_success_result_fields_match_recorded():
    full, _ = _capture(lambda r: _ok(usage={"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12}))
    no_split, _ = _capture(lambda r: _ok(usage={"total_tokens": 9}))
    def fields(result):
        # PRD-020 STORY-009 (D8): `usage_estimated` is a new field of the result, not a
        # change to today's recorded ones; a reported usage always leaves it False.
        record = dataclasses.asdict(result)
        assert record.pop("usage_estimated") is False
        return record

    results = {
        "usage_full": fields(call_openrouter(_USER_MESSAGES, model="gpt-4", client=full)),
        "usage_without_split": fields(
            call_openrouter(_USER_MESSAGES, model="gpt-4", client=no_split)
        ),
    }
    _check_bytes("results.json", _dump(results))


def test_stub_503_through_call_openrouter(monkeypatch):
    """AC2 names the stub: a `fail_status: 503` rule. Its message holds the
    ephemeral port, so only status, retryable and the prefix are asserted."""
    import io
    import threading

    from scripts.stub_openrouter import make_server, parse_script

    script = parse_script({"rules": [{"contains": "upstream down", "fail_status": 503}]})
    server = make_server(script, log=io.StringIO())
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        monkeypatch.setattr(settings, "OPENROUTER_BASE_URL", f"http://127.0.0.1:{port}/v1")
        with pytest.raises(OpenRouterError) as excinfo:
            call_openrouter([Message("user", "upstream down")], model="gpt-4", api_key=_CALLER_KEY)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert excinfo.value.upstream_status == 503
    assert excinfo.value.retryable is True
    assert str(excinfo.value).startswith(_HTTPX_PREFIX)


# --------------------------------------------------------------------------
# AC3 / AC4: client-facing bodies through TestClient(app)
# --------------------------------------------------------------------------


@pytest.fixture
def seeded(temp_db):
    insert_user(User(user_id="legacy-admin", role="admin", token_hash=hash_token(_ADMIN_TOKEN)))
    insert_user(User(user_id="legacy-user", role="user", token_hash=hash_token(_USER_TOKEN)))
    return temp_db


def test_v1_models_bodies_match_recorded(seeded):
    client = TestClient(app)
    cases = {
        "list.admin": (_ADMIN, "/v1/models"),
        "list.user": (_USER, "/v1/models"),
        "one.admin": (_ADMIN, "/v1/models/openai/gpt-4o"),
        "one.user": (_USER, "/v1/models/openai/gpt-4o"),
        "missing.admin": (_ADMIN, "/v1/models/no-such-model"),
        "missing.user": (_USER, "/v1/models/no-such-model"),
    }
    meta = {}
    for case, (headers, url) in cases.items():
        response = client.get(url, headers=headers)
        meta[case] = {
            "status": response.status_code,
            "x-should-retry": response.headers.get("x-should-retry"),
        }
        _check_bytes(f"v1/{case}.json", response.content)
    assert meta["list.admin"]["status"] == 200 and meta["missing.user"]["status"] == 404
    _check_bytes("v1/meta.json", _dump(meta))


_AUDIT_ID = re.compile(rb'("audit_id"\s*:\s*)\d+')
_AUDIT_REF = re.compile(rb'("audit_ref"\s*:\s*)"[^"]*"')


def _normalize(content: bytes) -> bytes:
    content = _AUDIT_ID.sub(rb'\1"<AUDIT_ID>"', content)
    return _AUDIT_REF.sub(rb'\1"<AUDIT_REF>"', content)


def _post_query(monkeypatch, client, headers, body, responder):
    """POST /query with the REAL call_openrouter over MockTransport.

    The router's `call_openrouter` is wrapped, not replaced, so the upstream
    bytes and the HTTP answer are captured together.
    """
    mock, calls = _capture(responder)

    def wrapper(messages, model="gpt-4", api_key=None, **kw):
        return call_openrouter(messages, model=model, api_key=api_key, client=mock, **kw)

    monkeypatch.setattr(query_router_module, "call_openrouter", wrapper)
    response = client.post("/query", headers=headers, json=body)
    return response, calls


def test_query_bodies_match_recorded(seeded, monkeypatch):
    client = TestClient(app)
    ok = lambda request: _ok("Hello from upstream")  # noqa: E731
    meta = {}

    def run(case, headers, body, responder=ok, expect_upstream=True):
        response, calls = _post_query(monkeypatch, client, headers, body, responder)
        meta[case] = {"status": response.status_code, "upstream_calls": len(calls)}
        assert bool(calls) == expect_upstream, case
        if calls:
            call = calls[0]
            _check_ordered_json(f"query/{case}.upstream.request.json", call["body"])
            _check_bytes(f"query/{case}.upstream.meta.json", _dump(_meta(call)))
        return response

    # (a) success, an allowed model, a plain user
    response = run("success_user", _USER, {"prompt": "legacy prompt a", "model": "gpt-4"})
    assert response.status_code == 200
    _check_bytes("query/success_user.json", _normalize(response.content))

    # (b) no `model` key: the schema default, and the upstream payload's model
    # (STORY-012's contract)
    response = run("default_model", _USER, {"prompt": "legacy prompt b"})
    assert response.status_code == 200
    _check_bytes("query/default_model.json", _normalize(response.content))

    # (c) BYOK as admin: the upstream Authorization carries the caller's key
    response = run(
        "byok_admin", _ADMIN,
        {"prompt": "legacy prompt c", "model": "gpt-4", "openrouter_api_key": _CALLER_KEY},
    )
    assert response.status_code == 200
    _check_bytes("query/byok_admin.json", _normalize(response.content))

    # (d) a model off the list as a plain user: query:model:<m>, nothing upstream
    response = run(
        "model_blocked_user", _USER, {"prompt": "legacy prompt d", "model": "some/off-list-model"},
        expect_upstream=False,
    )
    assert b"query:model:some/off-list-model" in response.content
    _check_bytes("query/model_blocked_user.json", _normalize(response.content))

    # (e) a BYOK key as a plain user: query:byok, nothing upstream
    response = run(
        "byok_blocked_user", _USER,
        {"prompt": "legacy prompt e", "model": "gpt-4", "openrouter_api_key": _CALLER_KEY},
        expect_upstream=False,
    )
    assert b"query:byok" in response.content
    _check_bytes("query/byok_blocked_user.json", _normalize(response.content))

    # (f) an admin may send an off-list model (the wildcard STORY-007 must keep)
    response = run("admin_off_list_model", _ADMIN, {"prompt": "legacy prompt f", "model": "some/off-list-model"})
    assert response.status_code == 200
    _check_bytes("query/admin_off_list_model.json", _normalize(response.content))

    # (g) upstream 503 through /query: the router's 502. The detail carries
    # httpx's own wording, so only the status, the key and the prefix are pinned.
    response = run(
        "upstream_503", _USER, {"prompt": "legacy prompt g", "model": "gpt-4"},
        responder=lambda request: httpx.Response(503, json={"error": "down"}),
    )
    detail = response.json()["detail"]
    assert list(response.json()) == ["detail"] and detail.startswith(_HTTPX_PREFIX)
    meta["upstream_503"]["detail_prefix"] = _HTTPX_PREFIX
    meta["upstream_503"]["detail_contains"] = f"{_BASE_URL}/chat/completions"
    assert meta["upstream_503"]["detail_contains"] in detail

    _check_bytes("query/meta.json", _dump(meta))


# --------------------------------------------------------------------------
# AC5: the README
# --------------------------------------------------------------------------


def test_readme_documents_normalization():
    text = (_FIXTURES / "README.md").read_text(encoding="utf-8")
    assert "<AUDIT_ID>" in text and "<AUDIT_REF>" in text
    assert "without editing a fixture" in text
