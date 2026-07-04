import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import base64

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.middleware import auth as auth_module
from app.middleware.auth import require_admin_token

_fake_app = FastAPI()


@_fake_app.get("/fake-audit", dependencies=[Depends(require_admin_token)])
def fake_audit() -> dict:
    return {"ok": True}


@_fake_app.get("/fake-stats", dependencies=[Depends(require_admin_token)])
def fake_stats() -> dict:
    return {"ok": True}


client = TestClient(_fake_app)

_PROTECTED_ROUTES = ["/fake-audit", "/fake-stats"]


@pytest.mark.parametrize("route", _PROTECTED_ROUTES)
def test_missing_authorization_header_rejected(route):
    response = client.get(route)

    assert response.status_code in (401, 403)


@pytest.mark.parametrize("route", _PROTECTED_ROUTES)
def test_incorrect_bearer_token_rejected(route):
    response = client.get(route, headers={"Authorization": "Bearer wrong-token"})

    assert response.status_code in (401, 403)


@pytest.mark.parametrize("route", _PROTECTED_ROUTES)
def test_correct_bearer_token_allowed(route):
    response = client.get(
        route, headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_non_bearer_scheme_rejected():
    basic_value = base64.b64encode(b"test-token").decode("ascii")

    response = client.get(
        "/fake-audit", headers={"Authorization": f"Basic {basic_value}"}
    )

    assert response.status_code in (401, 403)


def test_same_dependency_protects_both_routes():
    for route in _PROTECTED_ROUTES:
        no_header_response = client.get(route)
        assert no_header_response.status_code in (401, 403)

        authorized_response = client.get(
            route, headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
        )
        assert authorized_response.status_code == 200


def test_token_compared_via_constant_time_check(monkeypatch):
    calls = []
    original_compare_digest = auth_module.secrets.compare_digest

    def _tracking_compare_digest(a, b):
        calls.append((a, b))
        return original_compare_digest(a, b)

    monkeypatch.setattr(auth_module.secrets, "compare_digest", _tracking_compare_digest)

    response = client.get(
        "/fake-audit", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    assert response.status_code == 200
    assert len(calls) == 1
