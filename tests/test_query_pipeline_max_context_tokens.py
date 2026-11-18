"""PRD-020 STORY-010 (D9, T10): step 3 refuses a conversation over a model's max_context_tokens.

    AC1  estimate > N: `limit="estimated_tokens"`, nothing goes upstream
    AC2  estimate == N proceeds (strict `>`)
    AC3  no `max_context_tokens` (or legacy mode): unchanged, estimate not computed
    AC4  `/v1` 400 `context_length_exceeded` and an audit row with the reason
    AC5  the schema literal accepts the value (tests/test_schemas.py)

`estimate_chars_per_token: 1` makes the estimate equal the character count.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import json

import pytest
from fastapi.testclient import TestClient

import app.services.query_pipeline as query_pipeline
from app.config import settings
from app.db.database import get_audit_log, get_connection, insert_user
from app.db.models import User
from app.main import app
from app.models.messages import Message
from app.models.schemas import QueryBlockedContextLimitResponse
from app.services.identity import Identity, hash_token
from app.services.openrouter_client import OpenRouterResult
from app.services.upstream.params import ToolParams
from tests._providers import provider_file  # noqa: F401  (fixture)
from tests.test_audit_characterization import _shipped_settings  # noqa: F401  (autouse)

_USER = "ctx-user"
_TOKEN = "ctx-user-token"
_LIMIT = 100


def _yaml(extra=""):
    return f"""
version: 1
default_model: local/capped
providers:
  - name: local
    label: Local
    type: openai_compatible
    base_url: http://127.0.0.1:9/v1
    insecure_http: true
    trust: internal
    estimate_chars_per_token: 1
{extra}    models:
      - id: local/capped
        upstream: up-capped
        capabilities: {{max_context_tokens: {_LIMIT}}}
      - id: local/open
        upstream: up-open
"""


class _Upstream:
    """(messages, model, api_key, **kw) stub (D12); records calls."""

    def __init__(self):
        self.calls = []

    def __call__(self, messages, model, api_key, **kw):
        self.calls.append(model)
        return OpenRouterResult(response="ok", model_used=model, tokens_used=1)


@pytest.fixture
def upstream(monkeypatch):
    stub = _Upstream()
    monkeypatch.setattr(query_pipeline, "call_openrouter", stub)
    monkeypatch.setattr("app.routers.v1.call_openrouter", stub)
    return stub


def _run(upstream, size, model="local/capped", tools=None, role="user"):
    return query_pipeline.run_conversation(
        Identity(_USER, role), [Message("user", "a" * size)], "pytest/ctx", model, None,
        call_openrouter=upstream, ingress="query", profile="chat", tools=tools,
    )


def _last_row():
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
    return get_audit_log(row["id"])


def test_over_the_maximum_is_refused_and_nothing_goes_upstream(temp_db, provider_file, upstream):
    provider_file(_yaml())
    result = _run(upstream, _LIMIT + 1)
    assert isinstance(result, QueryBlockedContextLimitResponse)
    assert (result.limit, result.maximum, result.actual) == ("estimated_tokens", _LIMIT, _LIMIT + 1)
    assert upstream.calls == []


def test_exactly_the_maximum_proceeds(temp_db, provider_file, upstream):
    provider_file(_yaml())
    result = _run(upstream, _LIMIT)
    assert not isinstance(result, QueryBlockedContextLimitResponse)
    assert upstream.calls == ["local/capped"]


def test_a_model_without_a_maximum_is_not_checked_or_estimated(
    temp_db, provider_file, upstream, monkeypatch
):
    provider_file(_yaml())
    computed = []
    monkeypatch.setattr(query_pipeline, "estimate_tokens", lambda *a, **k: computed.append(1) or 10**9)
    result = _run(upstream, _LIMIT * 5, model="local/open")
    assert not isinstance(result, QueryBlockedContextLimitResponse)
    assert upstream.calls == ["local/open"]
    assert computed == []


def test_legacy_mode_is_unchanged(temp_db, upstream, monkeypatch):
    monkeypatch.setattr(settings, "CONTEXT_MAX_CHARACTERS", 10**6)
    result = query_pipeline.run_conversation(
        Identity(_USER, "user"), [Message("user", "a" * 50000)], "pytest/ctx", "openai/gpt-4o",
        None, call_openrouter=upstream, ingress="query", profile="chat",
    )
    assert not isinstance(result, QueryBlockedContextLimitResponse)
    assert len(upstream.calls) == 1


@pytest.mark.parametrize("setting, expected", [("CONTEXT_MAX_MESSAGES", "messages"), ("CONTEXT_MAX_CHARACTERS", "characters")])
def test_earlier_limits_win_even_when_the_estimate_also_breaches(
    temp_db, provider_file, upstream, monkeypatch, setting, expected
):
    provider_file(_yaml())
    monkeypatch.setattr(settings, setting, 0 if setting == "CONTEXT_MAX_MESSAGES" else 5)
    result = _run(upstream, _LIMIT + 50)
    assert result.limit == expected
    assert upstream.calls == []


def test_the_requests_tools_are_counted(temp_db, provider_file, upstream):
    """A direct `run_conversation(tools=...)` call: the tools gate is the `/v1` router's."""
    provider_file(_yaml())
    tools = ({"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}},)
    tool_chars = len(json.dumps(tools, sort_keys=True, ensure_ascii=False))
    assert 10 + tool_chars <= _LIMIT < 15 + tool_chars  
    assert not isinstance(_run(upstream, 10), QueryBlockedContextLimitResponse)
    result = _run(upstream, 15, tools=ToolParams(tools=tools))
    assert isinstance(result, QueryBlockedContextLimitResponse)
    assert (result.limit, result.maximum, result.actual) == ("estimated_tokens", _LIMIT, 15 + tool_chars)


def test_the_audit_row_names_the_refusal_and_the_route(temp_db, provider_file, upstream):
    provider_file(_yaml())
    _run(upstream, _LIMIT + 1)
    row = _last_row()
    assert row.success is False
    assert row.error_message == f"context limit: estimated_tokens {_LIMIT + 1} > {_LIMIT}"
    assert row.provider == "local"
    assert row.upstream_model == "up-capped"


def test_a_passthrough_route_uses_the_passthrough_capabilities(temp_db, provider_file, upstream):
    provider_file(_yaml("    passthrough: true\n    passthrough_capabilities: {max_context_tokens: 50}\n"))
    result = _run(upstream, 51, model="anything/else", role="admin")  # wildcard role (OD3)
    assert isinstance(result, QueryBlockedContextLimitResponse)
    assert (result.limit, result.maximum, result.actual) == ("estimated_tokens", 50, 51)
    assert upstream.calls == []


def test_v1_answers_400_context_length_exceeded(temp_db, provider_file, upstream):
    insert_user(User(user_id=_USER, role="user", token_hash=hash_token(_TOKEN)))
    provider_file(_yaml())
    client = TestClient(app, headers={"Authorization": f"Bearer {_TOKEN}"})
    response = client.post(
        "/v1/chat/completions",
        json={"model": "local/capped", "messages": [{"role": "user", "content": "v" * (_LIMIT + 1)}]},
    )
    assert response.status_code == 400, response.text
    error = response.json()["error"]
    assert error["code"] == "context_length_exceeded"
    assert error["message"] == f"Conversation exceeds context limit: estimated_tokens {_LIMIT + 1} > {_LIMIT}"
    assert error["harness"] == {
        "reason": "Conversation exceeds context limit",
        "limit": "estimated_tokens", "maximum": _LIMIT, "actual": _LIMIT + 1,
    }
    assert upstream.calls == []
