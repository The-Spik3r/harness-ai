"""PRD-020 STORY-011: the /v1 tool-capability rule from the registry (D6, F4, T3).

File mode: the router passes `tools_supported`, decided by `authz.authorize_route`
for a model the caller may use; a denial passes True so the pipeline's one denial
answers (byte-equal for uncatalogued / forbidden). Legacy keeps the
`(V1_TOOL_MODELS)` suffix; flag off is PRD-015/017 exactly in both modes.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import get_connection, insert_user
from app.db.models import User
from app.main import app
from app.models.v1_schemas import ChatCompletionRequest
from app.services.identity import hash_token
from app.services.openrouter_client import OpenRouterResult
from app.services.v1_translate import TOOLS_NOT_SUPPORTED, V1RequestError, translate_request
from tests._providers import provider_file  # noqa: F401

_USER_TOKEN = "story011-tools-user"
_HEADERS = {"Authorization": f"Bearer {_USER_TOKEN}"}
client = TestClient(app, headers=_HEADERS)

_TOOL = {"type": "function", "function": {"name": "f", "parameters": {"type": "object"}}}
_MSG = {"role": "user", "content": "hello"}
_RULE = "model is not enabled for tool calling"

REGISTRY = """
version: 1
default_model: tools-yes
providers:
  - name: alpha
    type: openai_compatible
    base_url: https://alpha.example.com/v1
    passthrough: true
    passthrough_capabilities: {tools: true}
    models:
      - id: tools-yes
        capabilities: {tools: true}
      - id: tools-no
        capabilities: {tools: false}
      - id: admin-tools-yes
        roles: [admin]
        capabilities: {tools: true}
      - id: admin-tools-no
        roles: [admin]
        capabilities: {tools: false}
"""


class _Upstream:
    def __init__(self):
        self.calls = []

    def __call__(self, messages, model="gpt-4", api_key=None, *, params=None, tools=None):
        self.calls.append(model)
        return OpenRouterResult(model_used=model, response="ok", tokens_used=3)


@pytest.fixture
def temp_db(temp_db):
    insert_user(User(user_id="u@x.com", role="user", token_hash=hash_token(_USER_TOKEN)))
    return temp_db


@pytest.fixture
def stub(monkeypatch):
    stub = _Upstream()
    monkeypatch.setattr("app.routers.v1.call_openrouter", stub)
    return stub


def _post(model, **extra):
    return client.post("/v1/chat/completions", json={"model": model, "messages": [_MSG], **extra})


def _rows() -> int:
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()["n"]


def test_tools_false_model_is_refused(temp_db, provider_file, monkeypatch, stub):
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    provider_file(REGISTRY)

    response = _post("tools-no", tools=[_TOOL])

    assert response.status_code == 400
    error = response.json()["error"]
    assert (error["code"], error["param"], error["message"]) == (
        TOOLS_NOT_SUPPORTED, "tools", _RULE)
    assert stub.calls == [] and _rows() == 0


def test_tools_true_model_passes(temp_db, provider_file, monkeypatch, stub):
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    provider_file(REGISTRY)

    assert _post("tools-yes", tools=[_TOOL]).status_code == 200
    assert stub.calls == ["tools-yes"]


def test_no_tools_request_ignores_the_capability(temp_db, provider_file, monkeypatch, stub):
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    provider_file(REGISTRY)

    assert _post("tools-no").status_code == 200


def test_t3_denials_are_byte_equal(temp_db, provider_file, monkeypatch, stub):
    """Uncatalogued, role-forbidden tools:true and role-forbidden tools:false ids
    all get the pipeline's one denial: no capability verdict reveals them."""
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    provider_file(REGISTRY)
    ids = ("no/such-model", "admin-tools-yes", "admin-tools-no")

    responses = [_post(m, tools=[_TOOL]) for m in ids]

    assert all(r.status_code == 403 for r in responses)
    assert all(r.json()["error"]["code"] != TOOLS_NOT_SUPPORTED for r in responses)
    # The denial text quotes the requested id (T3 one-text rule): equal once it is masked.
    assert len({r.text.replace(m, "<id>") for r, m in zip(responses, ids)}) == 1
    assert stub.calls == []


def test_passthrough_id_uses_passthrough_capabilities_for_admin(
    temp_db, provider_file, monkeypatch, stub
):
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    provider_file(REGISTRY)
    insert_user(User(user_id="a@x.com", role="admin", token_hash=hash_token("adm-tok")))

    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer adm-tok"},
        json={"model": "free/form-id", "messages": [_MSG], "tools": [_TOOL]},
    )

    assert response.status_code == 200


def test_flag_off_in_file_mode(temp_db, provider_file, monkeypatch, stub):
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", False)
    provider_file(REGISTRY)

    response = _post("tools-yes", tools=[_TOOL])

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "tools: tool calling is not supported (PRD-017)"


def test_legacy_message_keeps_the_suffix(temp_db, monkeypatch, stub):
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    monkeypatch.setattr(settings, "V1_TOOL_MODELS", "other/model")

    response = _post("openai/gpt-4o", tools=[_TOOL])

    assert response.status_code == 400
    assert response.json()["error"]["message"] == (
        "model is not enabled for tool calling (V1_TOOL_MODELS)")


# --- translator level ------------------------------------------------------------------


def _translate(extra=None, **kw):
    body = ChatCompletionRequest.model_validate(
        {"model": "m", "messages": [_MSG], "tools": [_TOOL], **(extra or {})})
    return translate_request(body, tools_enabled=kw.pop("tools_enabled", True), **kw)


def test_translator_tools_supported_values():
    assert _translate(tools_supported=True).tools is not None
    assert _translate(tools_supported=None).tools is not None
    with pytest.raises(V1RequestError) as caught:
        _translate(tools_supported=False)
    assert (caught.value.code, caught.value.param, caught.value.message) == (
        TOOLS_NOT_SUPPORTED, "tools", _RULE)


def test_translator_none_with_list_keeps_legacy_rule():
    with pytest.raises(V1RequestError) as caught:
        _translate(tool_models=("other",), tools_supported=None)
    assert caught.value.message == _RULE + " (V1_TOOL_MODELS)"


def test_translator_check_follows_rejected_keys():
    with pytest.raises(V1RequestError) as caught:
        _translate({"functions": [{"name": "f"}]}, tools_supported=False)
    assert caught.value.param == "functions"


def test_translator_flag_off_ignores_tools_supported():
    with pytest.raises(V1RequestError) as caught:
        _translate(tools_enabled=False, tools_supported=True)
    assert caught.value.param == "tools"
