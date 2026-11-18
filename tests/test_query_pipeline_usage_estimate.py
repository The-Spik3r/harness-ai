"""PRD-020 STORY-009 (D8, F5): an estimated usage reaches the charge and the audit row.

    AC2  `usage: null` + estimate: `unsplit_tokens` grows by exactly the estimate
    AC4  the success row has `usage_estimated=1`, tokens = estimate, split NULL;
         an upstream-error row stays 0
"""

import io
import os
import threading

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

import app.services.query_pipeline as query_pipeline
from app.db.database import get_audit_log, get_connection
from app.models.messages import Message
from app.services.identity import Identity
from app.services.upstream import UpstreamError
from scripts.stub_openrouter import make_server, parse_script
from tests._providers import provider_file  # noqa: F401  (fixture)
from tests.test_audit_characterization import _shipped_settings  # noqa: F401  (autouse)
from tests.test_query_pipeline_usage_limits import _today

_USER = "estimate-user"
_PROMPT = "a" * 8
_REPLY = "b" * 12  # ceil(8/4) + ceil(12/4) = 5


def _yaml(port):
    return f"""
version: 1
default_model: local/m
providers:
  - name: local
    label: Local
    type: openai_compatible
    base_url: http://127.0.0.1:{port}/v1
    insecure_http: true
    usage_missing: estimate
    models:
      - id: local/m
        upstream: up-local
"""


@pytest.fixture
def stub():
    started = []

    def start(script):
        server = make_server(parse_script(script), log=io.StringIO())
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        started.append((server, thread))
        return server.server_address[1]

    yield start
    for server, thread in started:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _last_row():
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
    return get_audit_log(row["id"])


def _run(prompt=_PROMPT):
    return query_pipeline.run_conversation(
        Identity(_USER, "user"), [Message("user", prompt)], "pytest/estimate", "local/m", None,
        ingress="query", profile="chat",
    )


def test_row_is_flagged_with_null_split(temp_db, provider_file, stub):
    provider_file(_yaml(stub({"default": {"content": _REPLY, "usage": None}})))
    result = _run()
    assert result.tokens_used == 5
    row = _last_row()
    assert row.usage_estimated is True
    assert row.tokens_used == 5
    assert row.input_tokens is None and row.output_tokens is None


def test_unsplit_tokens_grows_by_exactly_the_estimate(temp_db, provider_file, stub):
    provider_file(_yaml(stub({"default": {"content": _REPLY, "usage": None}})))
    _run()
    _run("c" * 8)  # a different prompt: an identical one is a duplicate
    assert _today(_USER) == (0, 0, 10)


def test_reported_usage_row_is_not_flagged(temp_db, provider_file, stub):
    provider_file(_yaml(stub({"default": {"content": _REPLY}})))
    _run()
    row = _last_row()
    assert row.usage_estimated is False and row.tokens_used == 2


def test_upstream_error_row_not_flagged(temp_db, provider_file, stub):
    provider_file(_yaml(stub({"default": {"fail_status": 503}})))
    with pytest.raises(UpstreamError):
        _run()
    row = _last_row()
    assert row.success is False
    assert row.usage_estimated is False


# --- E2E over HTTP ------------------------------------------------------------

_TOKEN = "test-user-token"
_HEADERS = {"Authorization": f"Bearer {_TOKEN}"}


@pytest.fixture
def http_user(temp_db):
    from app.db.database import insert_user
    from app.db.models import User
    from app.services.identity import hash_token

    insert_user(User(user_id=_USER, role="user", token_hash=hash_token(_TOKEN)))


@pytest.mark.parametrize("usage, estimated", [(None, True), ({"prompt_tokens": 2, "completion_tokens": 3}, False)])
def test_http_bodies(http_user, provider_file, stub, monkeypatch, usage, estimated):
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)
    provider_file(_yaml(stub({"default": {"content": _REPLY, "usage": usage}})))
    client = TestClient(app, headers=_HEADERS)

    query = client.post("/query", json={"prompt": "q" * 8, "model": "local/m"})
    assert query.status_code == 200, query.text
    assert "usage_estimated" not in query.text
    assert _last_row().usage_estimated is estimated

    v1 = client.post(
        "/v1/chat/completions",
        json={"model": "local/m", "messages": [{"role": "user", "content": "v" * 8}]},
    )
    assert v1.status_code == 200, v1.text
    body = v1.json()
    assert ("usage_estimated" in body["harness"]) is estimated
    if estimated:
        assert body["harness"]["usage_estimated"] is True
        assert body["usage"] == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 5}
    else:
        assert body["usage"]["total_tokens"] == 5
