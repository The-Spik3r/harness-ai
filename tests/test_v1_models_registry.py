"""PRD-020 STORY-011: file-mode `GET /v1/models` and `/v1/models/{id}` (F4, Section 10, D4, T3).

The list is `provider_registry.visible_models(identity)` in registry order with a
`harness` extension; passthrough ids are never listed. Retrieve answers 200 for a
visible id and one shared 404 for everything else (uncatalogued, role-forbidden,
passthrough), so the three bodies are byte-equal (T3). Legacy entries carry no
`harness` key (D1).
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
from tests._providers import provider_file  # noqa: F401

_USER_TOKEN = "story011-user-token"
_ADMIN_TOKEN = "story011-admin-token"
_USER = {"Authorization": f"Bearer {_USER_TOKEN}"}
_ADMIN = {"Authorization": f"Bearer {_ADMIN_TOKEN}"}

client = TestClient(app)

REGISTRY = """
version: 1
default_model: m-open
providers:
  - name: alpha
    type: openai_compatible
    base_url: https://alpha.example.com/v1
    passthrough: true
    passthrough_capabilities: {tools: true}
    models:
      - id: m-open
        capabilities: {tools: true, streaming: true, max_context_tokens: 8000}
      - id: m-admin-only
        roles: [admin]
        capabilities: {tools: true}
  - name: beta
    type: openai_compatible
    base_url: https://beta.example.com/v1
    models:
      - id: m-nolimit
        capabilities: {reasoning: true}
"""


@pytest.fixture
def temp_db(temp_db):
    insert_user(User(user_id="u@x.com", role="user", token_hash=hash_token(_USER_TOKEN)))
    insert_user(User(user_id="a@x.com", role="admin", token_hash=hash_token(_ADMIN_TOKEN)))
    return temp_db


def _audit_rows() -> int:
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()["n"]


def test_list_is_visible_models_in_order_with_harness(temp_db, provider_file):
    provider_file(REGISTRY)

    response = client.get("/v1/models", headers=_USER)

    assert response.status_code == 200
    assert response.json() == {
        "object": "list",
        "data": [
            {
                "id": "m-open", "object": "model", "created": 0, "owned_by": "alpha",
                "harness": {"provider": "alpha", "capabilities": {
                    "tools": True, "streaming": True, "reasoning": False,
                    "max_context_tokens": 8000}},
            },
            {
                "id": "m-nolimit", "object": "model", "created": 0, "owned_by": "beta",
                "harness": {"provider": "beta", "capabilities": {
                    "tools": False, "streaming": False, "reasoning": True,
                    "max_context_tokens": None}},
            },
        ],
    }
    assert list(response.json()["data"][0]) == ["id", "object", "created", "owned_by", "harness"]
    assert _audit_rows() == 0


def test_admin_sees_every_catalogued_model_and_no_passthrough(temp_db, provider_file):
    provider_file(REGISTRY)

    ids = [e["id"] for e in client.get("/v1/models", headers=_ADMIN).json()["data"]]

    assert ids == ["m-open", "m-admin-only", "m-nolimit"]


def test_retrieve_visible_model(temp_db, provider_file):
    provider_file(REGISTRY)

    response = client.get("/v1/models/m-nolimit", headers=_USER)

    assert response.status_code == 200
    assert response.json()["harness"]["capabilities"]["max_context_tokens"] is None
    assert response.json()["owned_by"] == "beta"


def test_retrieve_404_bodies_are_byte_equal(temp_db, provider_file):
    provider_file(REGISTRY)
    # uncatalogued, catalogued but role-forbidden, and a passthrough-only id (T3).
    responses = [
        client.get(f"/v1/models/{model_id}", headers=_USER)
        for model_id in ("never/heard-of-it", "m-admin-only", "some/passthrough-id")
    ]

    for r in responses:
        assert r.status_code == 404
        assert r.json()["error"]["message"] == "model not found"
        assert r.json()["error"]["code"] == "model_not_found"
        assert r.headers["x-should-retry"] == "false"
    assert len({r.content for r in responses}) == 1
    assert _audit_rows() == 0


def test_admin_retrieve_of_a_passthrough_id_is_still_404(temp_db, provider_file):
    provider_file(REGISTRY)

    assert client.get("/v1/models/some/passthrough-id", headers=_ADMIN).status_code == 404


def test_break_glass_is_still_refused_in_file_mode(temp_db, provider_file):
    provider_file(REGISTRY)
    headers = {"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}

    assert client.get("/v1/models", headers=headers).status_code == 403
    assert client.get("/v1/models/m-open", headers=headers).status_code == 403


def test_legacy_list_has_no_harness_key(temp_db):
    data = client.get("/v1/models", headers=_USER).json()["data"]

    assert data and all("harness" not in entry for entry in data)
