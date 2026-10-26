"""PRD-015 STORY-012: `GET /v1/models` and `/v1/models/{id}` (Sections 7.2, 7.7).

The list is `settings.model_allowlist_list` in configured order, read per
request; `owned_by` is the prefix before `/`, else `harness`. An `admin`-role
user token sees the same entries: the wildcard cannot be enumerated. A name
not in the list is a 404 `model_not_found`, matched exactly (D4).

No pipeline runs on these routes, so the router refuses the break-glass
credential itself, and nothing on either route writes an audit row. The
401 and 403 shape refusals come from the STORY-010 handlers. Every 4xx
carries `x-should-retry: false`.

Only the no-bearer test reaches no storage.
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
from app.services.identity import hash_token

_AUTH_USER_ID = "juan@empresa.com"
_AUTH_TOKEN = "test-user-token"
_AUTH_HEADERS = {"Authorization": f"Bearer {_AUTH_TOKEN}"}
_LIST = "/v1/models"
_ONE = "/v1/models/openai/gpt-4o"
_PATHS = [_LIST, _ONE]

client = TestClient(app, headers=_AUTH_HEADERS)

_NO_RETRY = "false"

# The default MODEL_ALLOWLIST (app/config.py), in its order.
_DEFAULT_LIST = {
    "object": "list",
    "data": [
        {"id": "gpt-4", "object": "model", "created": 0, "owned_by": "harness"},
        {"id": "claude-3-sonnet", "object": "model", "created": 0, "owned_by": "harness"},
        {"id": "openai/gpt-4o", "object": "model", "created": 0, "owned_by": "openai"},
        {
            "id": "anthropic/claude-3.5-sonnet",
            "object": "model",
            "created": 0,
            "owned_by": "anthropic",
        },
    ],
}


@pytest.fixture
def temp_db(temp_db):
    """conftest's initialized database, plus this suite's authenticated user."""
    insert_user(
        User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN))
    )
    return temp_db


def _count_audit_rows() -> int:
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()["n"]


def _error(status_code, type_, code, message):
    return status_code, {
        "error": {"message": message, "type": type_, "param": None, "code": code, "harness": None}
    }


def _assert_response(response, expected):
    status_code, body = expected
    assert (response.status_code, response.json()) == (status_code, body)
    assert response.headers["x-should-retry"] == _NO_RETRY


# --- AC 1: the list is the allowlist, in order -----------------------------------


def test_list_is_allowlist_in_order(temp_db):
    response = client.get(_LIST)

    assert (response.status_code, response.json()) == (200, _DEFAULT_LIST)
    assert "x-should-retry" not in response.headers
    assert _count_audit_rows() == 0


def test_list_reads_allowlist_per_request(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "MODEL_ALLOWLIST", "z/last, a-first ,m/mid")

    ids = [(entry["id"], entry["owned_by"]) for entry in client.get(_LIST).json()["data"]]

    assert ids == [("z/last", "z"), ("a-first", "harness"), ("m/mid", "m")]


def test_empty_prefix_is_owned_by_harness(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "MODEL_ALLOWLIST", "/leading-slash")

    assert client.get(_LIST).json()["data"][0]["owned_by"] == "harness"


# --- AC 2: an admin-role user token sees the same entries -------------------------


def test_admin_role_user_sees_same_entries(temp_db):
    insert_user(User(user_id="ops", role="admin", token_hash=hash_token("admin-user-token")))
    admin_client = TestClient(app, headers={"Authorization": "Bearer admin-user-token"})

    response = admin_client.get(_LIST)

    assert (response.status_code, response.json()) == (200, _DEFAULT_LIST)
    assert _count_audit_rows() == 0


# --- AC 3: one entry, encoded or not; 404 model_not_found -------------------------


@pytest.mark.parametrize("path", ["/v1/models/openai%2Fgpt-4o", "/v1/models/openai/gpt-4o"])
def test_retrieve_encoded_and_unencoded(temp_db, path):
    response = client.get(path)

    assert (response.status_code, response.json()) == (
        200,
        {"id": "openai/gpt-4o", "object": "model", "created": 0, "owned_by": "openai"},
    )
    assert _count_audit_rows() == 0


def test_retrieve_unprefixed_is_owned_by_harness(temp_db):
    assert client.get("/v1/models/gpt-4").json() == {
        "id": "gpt-4", "object": "model", "created": 0, "owned_by": "harness",
    }


@pytest.mark.parametrize(
    "name", ["not-a-real-model", "openai/gpt-4o-mini", "OPENAI/GPT-4O", "openai/gpt-4o/"]
)
def test_retrieve_unknown_is_404_model_not_found(temp_db, name):
    response = client.get(f"/v1/models/{name}")

    _assert_response(
        response,
        _error(404, "invalid_request_error", "model_not_found", "model is not in MODEL_ALLOWLIST"),
    )
    assert name not in response.text
    assert _count_audit_rows() == 0


def test_retrieve_reads_allowlist_per_request(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "MODEL_ALLOWLIST", "gpt-4")

    assert client.get(_ONE).status_code == 404
    assert client.get("/v1/models/gpt-4").status_code == 200


# --- AC 4: break-glass, no bearer, no query:submit; never a row ------------------


@pytest.mark.parametrize("path", _PATHS)
def test_admin_token_is_403_break_glass_not_permitted_without_row(temp_db, path):
    admin_client = TestClient(app, headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"})

    _assert_response(
        admin_client.get(path),
        _error(
            403, "permission_error", "break_glass_not_permitted",
            "Break-glass credential not permitted on this ingress: ingress:break_glass",
        ),
    )
    assert _count_audit_rows() == 0


@pytest.mark.parametrize("path", _PATHS)
def test_no_bearer_is_401_invalid_api_key(path):
    # No temp_db: resolve(None) returns before any lookup.
    _assert_response(
        TestClient(app).get(path),
        _error(401, "authentication_error", "invalid_api_key", "Invalid or missing credential"),
    )


@pytest.mark.parametrize("path", _PATHS)
def test_auditor_is_403_permission_denied(temp_db, path):
    insert_user(
        User(user_id="reviewer", role="auditor", token_hash=hash_token("auditor-token"))
    )
    auditor_client = TestClient(app, headers={"Authorization": "Bearer auditor-token"})

    _assert_response(
        auditor_client.get(path),
        _error(403, "permission_error", "permission_denied", "Permission denied: query:submit"),
    )
    assert _count_audit_rows() == 0


def test_post_to_models_is_405(temp_db):
    response = client.post(_LIST)

    _assert_response(
        response, _error(405, "invalid_request_error", "method_not_allowed", "Method Not Allowed")
    )
    assert response.headers["allow"] == "GET"


# --- T9: refusals are logged with who and which rule only -----------------------


def test_refusals_log_user_and_code_only(temp_db, caplog):
    admin_client = TestClient(app, headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"})
    with caplog.at_level("INFO", logger="app.routers.v1"):
        client.get("/v1/models/secret-model-name")
        admin_client.get(_LIST)

    messages = [record.getMessage() for record in caplog.records if record.name == "app.routers.v1"]
    assert messages == [
        f"v1 request refused: user_id={_AUTH_USER_ID} code=model_not_found",
        "v1 request refused: user_id=admin code=break_glass_not_permitted",
    ]
