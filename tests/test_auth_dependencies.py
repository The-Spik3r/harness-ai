import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import init_db, insert_user
from app.db.models import User
from app.middleware.auth import require_admin_token, require_identity, require_permission
from app.services.authz import PERMISSION_QUERY_BYOK
from app.services.identity import hash_token

_fake_app = FastAPI()


@_fake_app.get("/fake-identity")
def fake_identity(identity=Depends(require_identity)) -> dict:
    return {"user_id": identity.user_id, "role": identity.role}


@_fake_app.get(
    "/fake-byok",
    dependencies=[Depends(require_permission(PERMISSION_QUERY_BYOK))],
)
def fake_byok() -> dict:
    return {"ok": True}


@_fake_app.get("/fake-admin", dependencies=[Depends(require_admin_token)])
def fake_admin() -> dict:
    return {"ok": True}


client = TestClient(_fake_app)


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path


# --- AC1: require_identity rejects no/invalid/malformed credential with 401 ---


def test_require_identity_rejects_missing_credential():
    response = client.get("/fake-identity")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing credential"}


def test_require_identity_rejects_invalid_credential(temp_db):
    response = client.get(
        "/fake-identity", headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing credential"}


def test_require_identity_rejects_non_bearer_scheme():
    import base64

    basic_value = base64.b64encode(b"test-token").decode("ascii")

    response = client.get(
        "/fake-identity", headers={"Authorization": f"Basic {basic_value}"}
    )

    assert response.status_code == 401


# --- AC2: require_identity returns the resolved Identity for a valid credential ---


def test_require_identity_returns_resolved_identity_for_valid_credential(temp_db):
    insert_user(User(user_id="ana", role="user", token_hash=hash_token("tok")))

    response = client.get("/fake-identity", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    assert response.json() == {"user_id": "ana", "role": "user"}


def test_require_identity_resolves_admin_token():
    response = client.get(
        "/fake-identity", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    assert response.status_code == 200
    assert response.json() == {"user_id": "admin", "role": "admin"}


# --- AC3: require_permission(p) raises 403 naming the permission when missing ---


def test_require_permission_rejects_identity_lacking_permission(temp_db):
    insert_user(User(user_id="ana", role="user", token_hash=hash_token("tok")))

    response = client.get("/fake-byok", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 403
    assert response.json() == {"detail": f"Permission denied: {PERMISSION_QUERY_BYOK}"}


def test_require_permission_allows_identity_with_permission():
    response = client.get(
        "/fake-byok", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_require_permission_rejects_missing_credential_with_401_not_403():
    response = client.get("/fake-byok")

    assert response.status_code == 401


# --- AC4/AC5: require_admin_token reimplemented on require_identity, behavior unchanged ---


def test_require_admin_token_still_authenticates_admin_token():
    response = client.get(
        "/fake-admin", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_require_admin_token_rejects_non_admin_identity(temp_db):
    insert_user(User(user_id="ana", role="user", token_hash=hash_token("tok")))

    response = client.get("/fake-admin", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 401
