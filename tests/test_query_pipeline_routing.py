"""PRD-020 STORY-007: step 2 routing, BYOK per provider, per-row provider audit.

    AC1  step 2 resolves through `authorize_route` (the verdict text is unchanged)
    AC2  a caller key is refused for a `byok: false` provider (D10): `query:byok:<name>`
    AC3  two live stubs: each model reaches only its own provider, with its own key
    AC4  `provider` / `upstream_model` / `provider_trust` on every row after step 2,
         NULL on the denials at or before it; `model_used` stays the requested id
    AC5  an injected `call_openrouter(messages, model, api_key, **kw)` stub still works

The legacy byte-for-byte replay is `tests/test_prd020_legacy_fixtures.py`. The
arm drivers are `tests/test_audit_characterization.py`'s (imported, not copied).
Per the libSQL dev-server note: mass fixture errors here mean restart the dev
container, not bisect code.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import io
import re
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.services.query_pipeline as query_pipeline
import app.services.usage_limits as usage_limits
import tests.test_audit_characterization as characterization
from app.config import settings
from app.db.database import get_audit_log, get_connection, insert_user
from app.db.models import UsageAdmission, User
from app.main import app
from app.models.messages import Message
from app.models.schemas import QueryBlockedForbiddenResponse, QueryBlockedUsageLimitResponse
from app.services.identity import Identity, hash_token
from app.services.openrouter_client import OpenRouterResult
from scripts.stub_openrouter import make_server, parse_script
from tests._providers import provider_file  # noqa: F401  (fixture)
from tests.test_audit_characterization import (  # noqa: F401
    ARM_CASES,
    _audit_rows_since,
    _drive,
    _last_audit_id,
    _shipped_settings,  # autouse: shipped settings, redact stubbed, no model loaded
)

_KEY_A = "sk-test-key-AAAA"
_KEY_CALLER = "sk-caller-key-CCCC"
_AUTH_USER_ID = "juan@empresa.com"
_AUTH_TOKEN = "test-user-token"
_ADMIN_USER_ID = "root-admin"
_ADMIN_TOKEN = "test-admin-user-token"
_USER_HEADERS = {"Authorization": f"Bearer {_AUTH_TOKEN}"}
_ADMIN_HEADERS = {"Authorization": f"Bearer {_ADMIN_TOKEN}"}
_PIPELINE = Path(__file__).resolve().parent.parent / "app" / "services" / "query_pipeline.py"


@pytest.fixture(autouse=True)
def _remote_key_env(monkeypatch):
    monkeypatch.setenv("REMOTE_KEY_ENV", _KEY_A)


@pytest.fixture
def temp_db(temp_db):
    """conftest's initialized database, plus a plain user and an admin (holds `query:byok`)."""
    insert_user(User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN)))
    insert_user(User(user_id=_ADMIN_USER_ID, role="admin", token_hash=hash_token(_ADMIN_TOKEN)))
    return temp_db


@pytest.fixture
def stubs():
    """Factory: (port, log) for a stub, optionally requiring a key; stopped at teardown."""
    started = []

    def start(script=None, require_key=None):
        log = io.StringIO()
        server = make_server(
            parse_script(script or {"rules": [], "default": {"content": "pong"}}),
            log=log,
            require_key=require_key,
        )
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        started.append((server, thread))
        return server.server_address[1], log

    yield start
    for server, thread in started:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _yaml(local_port, remote_port=None, *, byok=True):
    """`remote` is keyed (REMOTE_KEY_ENV), `local` has no key_env; both on loopback http."""
    return f"""
version: 1
default_model: remote/m
providers:
  - name: remote
    label: Remote
    type: openai_compatible
    base_url: http://127.0.0.1:{remote_port or local_port}/v1
    insecure_http: true
    key_env: REMOTE_KEY_ENV
    byok: {str(byok).lower()}
    models:
      - id: remote/m
        upstream: up-remote
  - name: local
    label: Local
    type: openai_compatible
    base_url: http://127.0.0.1:{local_port}/v1
    insecure_http: true
    trust: internal
    models:
      - id: local/m
        upstream: up-local
"""


def _two_stubs(stubs, provider_file, *, byok=True, remote_script=None):
    remote_port, remote_log = stubs(script=remote_script, require_key=None)
    local_port, local_log = stubs()
    provider_file(_yaml(local_port, remote_port, byok=byok))
    return remote_log, local_log


def _no_pii(monkeypatch):
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)


def _last_row():
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
    return get_audit_log(row["id"])


def _count_rows(table: str) -> int:
    with get_connection() as conn:
        return conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]


def _provider_fields(row):
    return (row.provider, row.upstream_model, row.provider_trust)


_NULLS = (None, None, None)


# --- AC3: two stubs -----------------------------------------------------------


@pytest.mark.parametrize(
    "model, auth, wire, own_log, other_log",
    [
        ("remote/m", "auth=yes", "up-remote", "remote", "local"),
        ("local/m", "auth=no", "up-local", "local", "remote"),
    ],
)
def test_two_stubs_query_reaches_only_its_own_provider(
    temp_db, stubs, provider_file, monkeypatch, model, auth, wire, own_log, other_log
):
    _no_pii(monkeypatch)
    remote_log, local_log = _two_stubs(stubs, provider_file)
    logs = {"remote": remote_log, "local": local_log}

    response = TestClient(app, headers=_USER_HEADERS).post(
        "/query", json={"prompt": f"hello {model}", "model": model}
    )

    assert response.status_code == 200, response.text
    assert response.json()["response"] == "pong"
    assert auth in logs[own_log].getvalue()
    assert logs[other_log].getvalue() == ""
    # The row names the route; model_used stays the requested id (D3, D13).
    row = _last_row()
    assert row.model_used == model
    assert row.provider == own_log and row.upstream_model == wire


@pytest.mark.parametrize("model, auth, own_log, other_log", [
    ("remote/m", "auth=yes", "remote", "local"),
    ("local/m", "auth=no", "local", "remote"),
])
def test_two_stubs_v1_reaches_only_its_own_provider(
    temp_db, stubs, provider_file, monkeypatch, model, auth, own_log, other_log
):
    _no_pii(monkeypatch)
    remote_log, local_log = _two_stubs(stubs, provider_file)
    logs = {"remote": remote_log, "local": local_log}

    response = TestClient(app, headers=_USER_HEADERS).post(
        "/v1/chat/completions",
        json={"model": model, "messages": [{"role": "user", "content": f"hi {model}"}]},
    )

    assert response.status_code == 200, response.text
    assert auth in logs[own_log].getvalue()
    assert logs[other_log].getvalue() == ""
    assert _last_row().provider == own_log


# --- AC2: BYOK per provider ---------------------------------------------------


def test_byok_refused_for_a_provider_that_does_not_take_a_caller_key(
    temp_db, stubs, provider_file, monkeypatch
):
    _no_pii(monkeypatch)
    monkeypatch.setattr(settings, "USAGE_LIMITS_ENABLED", True)
    remote_log, local_log = _two_stubs(stubs, provider_file, byok=False)
    usage_before = _count_rows("usage_daily")

    response = TestClient(app, headers=_ADMIN_HEADERS).post(
        "/query",
        json={"prompt": "use my key", "model": "remote/m", "openrouter_api_key": _KEY_CALLER},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reason"] == "Missing required permission"
    assert body["required_permission"] == "query:byok:remote"
    assert remote_log.getvalue() == "" and local_log.getvalue() == ""
    assert _count_rows("usage_daily") == usage_before  # nothing admitted, nothing charged
    row = _last_row()
    assert row.denied_permission == "query:byok:remote"
    assert _provider_fields(row) == _NULLS
    assert _KEY_CALLER not in body.__repr__() and _KEY_CALLER not in repr(row)


def test_byok_is_sent_to_a_provider_that_takes_it(temp_db, stubs, provider_file, monkeypatch):
    _no_pii(monkeypatch)
    remote_port, remote_log = stubs(require_key=_KEY_CALLER)
    local_port, _ = stubs()
    provider_file(_yaml(local_port, remote_port, byok=True))

    response = TestClient(app, headers=_ADMIN_HEADERS).post(
        "/query",
        json={"prompt": "use my key", "model": "remote/m", "openrouter_api_key": _KEY_CALLER},
    )

    assert response.status_code == 200, response.text
    assert response.json()["response"] == "pong"
    assert " auth=yes " in remote_log.getvalue() and remote_log.getvalue().strip().endswith("-> 200")
    assert _provider_fields(_last_row())[0] == "remote"


def test_caller_without_query_byok_keeps_todays_verdict_and_null_fields(
    temp_db, stubs, provider_file, monkeypatch
):
    _no_pii(monkeypatch)
    remote_log, _ = _two_stubs(stubs, provider_file, byok=True)

    response = TestClient(app, headers=_USER_HEADERS).post(
        "/query",
        json={"prompt": "use my key", "model": "remote/m", "openrouter_api_key": _KEY_CALLER},
    )

    assert response.json()["required_permission"] == "query:byok"
    assert remote_log.getvalue() == ""
    assert _provider_fields(_last_row()) == _NULLS


# --- AC4: per-row provider fields ---------------------------------------------

#: Arms at or before the model check: no route exists, so the three columns are NULL.
_NO_ROUTE_ARMS = {"permission-denied", "model-not-permitted", "byok-denied"}
_ARMS = [pytest.param(case[0], id=case[0]) for case in ARM_CASES]


@pytest.mark.parametrize("arm", _ARMS)
def test_row_provider_fields_in_legacy_mode(temp_db, monkeypatch, arm):
    before = _last_audit_id()

    characterization._drive(monkeypatch, arm)

    rows = _audit_rows_since(before)
    assert rows
    expected = _NULLS if arm in _NO_ROUTE_ARMS else ("openrouter", "gpt-4", "external")
    assert [_provider_fields(row) for row in rows] == [expected] * len(rows), arm


# `_drive`'s duplicate arm seeds with `_run`'s default model (bound at import), so it
# cannot name a catalogue id; it has its own test below.
@pytest.mark.parametrize("arm", [a for a in _ARMS if a.values[0] != "duplicate"])
def test_row_provider_fields_in_file_mode(temp_db, stubs, provider_file, monkeypatch, arm):
    local_port, _ = stubs()
    provider_file(_yaml(local_port))
    monkeypatch.setattr(characterization, "_MODEL", "remote/m")  # the model `_drive` names
    before = _last_audit_id()

    characterization._drive(monkeypatch, arm)

    rows = _audit_rows_since(before)
    assert rows
    expected = _NULLS if arm in _NO_ROUTE_ARMS else ("remote", "up-remote", "external")
    assert [_provider_fields(row) for row in rows] == [expected] * len(rows), arm
    if arm == "upstream-error":
        assert rows[0].model_used == "remote/m"  # the requested id, not `upstream`


def test_duplicate_rows_carry_the_route(temp_db, stubs, provider_file):
    local_port, _ = stubs()
    provider_file(_yaml(local_port))
    before = _last_audit_id()
    send = characterization._Upstream()

    _run(Identity("juan", "user"), upstream=send, model="remote/m", prompt="same text twice")
    second = _run(Identity("juan", "user"), upstream=send, model="remote/m", prompt="same text twice")

    assert second.__class__.__name__ == "QueryBlockedDuplicateResponse"
    rows = _audit_rows_since(before)
    assert len(rows) == 2 and rows[1].was_duplicate_blocked
    assert [_provider_fields(r) for r in rows] == [("remote", "up-remote", "external")] * 2


def _run(identity, *, ingress="query", upstream=None, model="local/m", prompt="route me"):
    return query_pipeline.run_conversation(
        identity, [Message("user", prompt)], "pytest/routing", model, None,
        call_openrouter=upstream or characterization._fail_if_called,
        ingress=ingress,
    )


def test_break_glass_row_carries_the_route(temp_db, stubs, provider_file):
    local_port, _ = stubs()
    provider_file(_yaml(local_port))
    before = _last_audit_id()

    result = _run(Identity("root", "admin", break_glass=True), ingress="v1")

    assert isinstance(result, QueryBlockedForbiddenResponse)
    (row,) = _audit_rows_since(before)
    assert row.denied_permission == "ingress:break_glass"
    assert _provider_fields(row) == ("local", "up-local", "internal")


def test_usage_limit_row_carries_the_route(temp_db, stubs, provider_file, monkeypatch):
    local_port, _ = stubs()
    provider_file(_yaml(local_port))
    monkeypatch.setattr(settings, "USAGE_LIMITS_ENABLED", True)
    monkeypatch.setattr(settings, "USAGE_REQUESTS_PER_MINUTE", "*=1")
    monkeypatch.setattr(
        usage_limits, "admit_usage",
        lambda user_id: UsageAdmission(day="2026-10-19", window_start=29_000_000,
                                       window_requests=2, tokens_today=0),
    )
    before = _last_audit_id()

    result = _run(Identity("juan", "user"))

    assert isinstance(result, QueryBlockedUsageLimitResponse)
    (row,) = _audit_rows_since(before)
    assert _provider_fields(row) == ("local", "up-local", "internal")


def test_upstream_5xx_row_carries_the_route_and_the_requested_model(
    temp_db, stubs, provider_file, monkeypatch
):
    _no_pii(monkeypatch)
    local_port, _ = stubs()
    remote_port, _ = stubs(script={"rules": [], "default": {"fail_status": 503}})
    provider_file(_yaml(local_port, remote_port))

    response = TestClient(app, headers=_USER_HEADERS, raise_server_exceptions=False).post(
        "/query", json={"prompt": "will fail", "model": "remote/m"}
    )

    assert response.status_code >= 500
    row = _last_row()
    assert row.success is False
    assert row.model_used == "remote/m"
    assert _provider_fields(row) == ("remote", "up-remote", "external")


# --- AC5: injected upstream stub ----------------------------------------------


def test_injected_stub_receives_the_original_model_id_in_file_mode(temp_db, stubs, provider_file):
    local_port, local_log = stubs()
    provider_file(_yaml(local_port))
    seen = []

    def _stub(messages, model, api_key, **kw):
        seen.append((model, api_key))
        return OpenRouterResult(response="ok", model_used=model, tokens_used=3)

    result = _run(Identity("juan", "user"), upstream=_stub, model="remote/m")

    assert seen == [("remote/m", None)]  # the requested id, never `up-remote`
    assert result.model_used == "remote/m"
    assert local_log.getvalue() == ""


# --- Source guard -------------------------------------------------------------


def test_every_log_query_call_in_the_pipeline_passes_the_route_fields():
    source = _PIPELINE.read_text(encoding="utf-8")
    calls = [m.start() for m in re.finditer(r"\blog_query\(", source)]
    # The import line has no "(": 11 call sites plus `_deny`'s, one `def _deny` helper.
    assert len(calls) == 11, len(calls)
    for start in calls:
        assert "_route_fields(route)" in source[start:start + 120], source[start:start + 80]
