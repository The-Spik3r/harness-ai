import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import count_active_users, insert_user
from app.db.models import User
from app.main import app
from app.services.identity import hash_token
import app.services.authz as authz
import app.services.pii_redactor as pii_redactor

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.fixture
def _small_model_and_reset(monkeypatch):
    monkeypatch.setattr(settings, "PII_NLP_MODEL", "en_core_web_sm")
    monkeypatch.setattr(pii_redactor, "_analyzer", None)
    monkeypatch.setattr(pii_redactor, "_anonymizer", None)
    # Unrelated to RBAC bootstrap; the real dev DATABASE_URL these tests run
    # against has no seeded users, so STORY-016's guard would otherwise fire.
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    yield


def test_lifespan_loads_pii_analyzer_before_serving_requests(_small_model_and_reset):
    with TestClient(app) as test_client:
        assert pii_redactor._analyzer is not None
        response = test_client.get("/health")
        assert response.status_code == 200


def test_lifespan_does_not_reload_analyzer_on_first_request(_small_model_and_reset, monkeypatch):
    build_calls = []
    original_build = pii_redactor._build_analyzer

    def _counting_build():
        build_calls.append(1)
        return original_build()

    monkeypatch.setattr(pii_redactor, "_build_analyzer", _counting_build)

    with TestClient(app) as test_client:
        assert len(build_calls) == 1
        test_client.get("/health")
        assert len(build_calls) == 1


def test_lifespan_skips_analyzer_when_redaction_disabled(_small_model_and_reset, monkeypatch):
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)

    with TestClient(app) as test_client:
        assert pii_redactor._analyzer is None
        response = test_client.get("/health")
        assert response.status_code == 200


def test_lifespan_loads_roles_file_before_serving_requests(tmp_path, monkeypatch):
    roles_file = tmp_path / "roles.json"
    roles_file.write_text('{"user": ["query:submit"]}')
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(roles_file))
    # Unrelated to RBAC bootstrap; the real dev DATABASE_URL this test runs
    # against has no seeded users, so STORY-016's guard would otherwise fire.
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    original = authz.ROLE_PERMISSIONS

    try:
        with TestClient(app) as test_client:
            assert authz.ROLE_PERMISSIONS == {"user": {"query:submit"}}
            response = test_client.get("/health")
            assert response.status_code == 200
    finally:
        authz.ROLE_PERMISSIONS = original


@pytest.fixture
def _empty_users_db(temp_db):
    """conftest's initialized database, with no user seeded into it.

    Requested for its side effect -- the startup guard reads the `users` table
    through `settings.DATABASE_URL`, which `temp_db` has already patched."""


def test_lifespan_fails_fast_when_rbac_enabled_and_no_active_users(
    _empty_users_db, monkeypatch
):
    monkeypatch.setattr(settings, "RBAC_ENABLED", True)
    assert count_active_users() == 0

    with pytest.raises(authz.RbacNotBootstrappedError):
        with TestClient(app):
            pass


def test_lifespan_boots_when_rbac_enabled_and_one_active_user(
    _empty_users_db, monkeypatch
):
    monkeypatch.setattr(settings, "RBAC_ENABLED", True)
    insert_user(User(user_id="ana", role="user", token_hash=hash_token("ana-token")))

    with TestClient(app) as test_client:
        response = test_client.get("/health")
        assert response.status_code == 200


def test_lifespan_skips_guard_when_rbac_disabled(_empty_users_db, monkeypatch):
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    assert count_active_users() == 0

    with TestClient(app) as test_client:
        response = test_client.get("/health")
        assert response.status_code == 200


def test_lifespan_fails_fast_even_with_only_admin_token_configured(
    _empty_users_db, monkeypatch
):
    monkeypatch.setattr(settings, "RBAC_ENABLED", True)
    assert settings.ADMIN_TOKEN
    assert count_active_users() == 0

    with pytest.raises(authz.RbacNotBootstrappedError):
        with TestClient(app):
            pass
