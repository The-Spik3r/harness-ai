"""GET /providers/status (PRD-022 STORY-015, F9, Section 10, D12, T10).

A pure in-memory read of `upstream/health.py` through the registry's provider
names: no database, no network. The `/stats` fallback figures are in
`test_stats_router.py` and `test_audit_stats_prd013.py`.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import socket
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import database
from app.db.database import insert_user
from app.db.models import User
from app.main import app
from app.services import circuit_breaker, provider_registry
from app.services.authz import PERMISSION_STATS_READ
from app.services.identity import hash_token
from app.services.upstream import health
from app.services.upstream.types import UPSTREAM_ERROR_KINDS, UpstreamError
from tests._providers import provider_file  # noqa: F401  (fixture)

client = TestClient(app)
_ADMIN = {"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}

_SINCE = "2026-11-20T10:00:00Z"

_YAML = """
version: 1
default_model: a/m
providers:
  - name: alpha
    label: Alpha
    type: openai_compatible
    base_url: http://127.0.0.1:9/v1
    insecure_http: true
    key_env: STATUS_KEY_ENV
    byok: false
    usage_missing: estimate
    models:
      - id: a/m
        upstream: up-a
        capabilities: {tools: true, streaming: true, reasoning: true}
  - name: anthropic-direct
    label: Ant
    type: anthropic
    base_url: http://127.0.0.1:9
    insecure_http: true
    key_env: STATUS_KEY_ENV
    byok: false
    usage_missing: estimate
    models:
      - id: claude-x
        upstream: claude-up
        default_max_tokens: 256
        capabilities: {tools: true, streaming: true, reasoning: true}
"""

_ONE_YAML = _YAML.split("  - name: anthropic-direct")[0]


@pytest.fixture
def clock(monkeypatch):
    t = [0.0]
    health.reset(clock=lambda: t[0])
    monkeypatch.setattr(
        circuit_breaker,
        "_wall_clock",
        lambda: datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc),
    )
    return t


@pytest.fixture
def registry(provider_file, monkeypatch):  # noqa: F811
    monkeypatch.setenv("STATUS_KEY_ENV", "sk-status-key")
    return provider_file(_YAML)


def _get():
    response = client.get("/providers/status", headers=_ADMIN)
    assert response.status_code == 200, response.text
    return response.json()


def _err(kind="timeout", status=None, text="x"):
    return UpstreamError(text, kind=kind, retryable=True, upstream_status=status)


def test_the_full_body_is_pinned(clock, registry):
    for _ in range(5):
        health.record("alpha", _err("timeout"))
    health.record("anthropic-direct", _err("status", status=429))
    health.count_fallback_answer()
    health.count_skipped("alpha", "open")

    body = _get()

    open_breaker = health.breaker("alpha").status()
    assert body == {
        "instance": health.providers_status([]).instance,
        "providers": {
            "alpha": {
                "breaker": {
                    "state": "open",
                    "since": _SINCE,
                    "consecutive_failures": 5,
                    "last_failure_class": "timeout",
                    "retry_after_seconds": open_breaker.retry_after_seconds,
                }
            },
            "anthropic-direct": {
                "breaker": {
                    "state": "closed",
                    "since": _SINCE,
                    "consecutive_failures": 1,
                    "last_failure_class": "status",
                    "retry_after_seconds": None,
                }
            },
        },
        "counters": {
            "attempts_failed": {"alpha:timeout": 5, "anthropic-direct:status": 1},
            "fallback_answers": 1,
            "skipped": {"alpha:open": 1},
            "breaker_opens": 1,
        },
    }
    assert open_breaker.retry_after_seconds >= 1


def test_status_makes_no_database_or_network_call(clock, registry, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("/providers/status reached the database or the network")

    monkeypatch.setattr(database, "_unit_of_work", boom)
    monkeypatch.setattr(database, "get_connection", boom)
    monkeypatch.setattr(database, "_session", boom)
    monkeypatch.setattr(database, "_shared_client", boom)
    monkeypatch.setattr(socket, "create_connection", boom)

    assert set(_get()["providers"]) == {"alpha", "anthropic-direct"}
    # Also with the storage breaker open: this endpoint does not depend on it.
    database._storage_breaker.force_open(30)
    assert set(_get()["providers"]) == {"alpha", "anthropic-direct"}


def test_legacy_deployment_lists_the_legacy_provider_closed(clock, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDERS_FILE", "")
    provider_registry.reset()
    provider_registry.load()
    try:
        body = _get()
    finally:
        provider_registry.reset()

    assert set(body["providers"]) == {"openrouter"}
    breaker = body["providers"]["openrouter"]["breaker"]
    assert breaker["state"] == "closed"
    assert breaker["consecutive_failures"] == 0
    assert breaker["retry_after_seconds"] is None
    assert breaker["last_failure_class"] is None


def test_a_401_force_open_reports_misconfigured_and_leaks_no_text(clock, registry):
    health.record(
        "anthropic-direct",
        UpstreamError(
            "CANARY-sk-leak-123", kind="misconfigured", upstream_status=401
        ),
    )

    response = client.get("/providers/status", headers=_ADMIN)
    body = response.json()
    breaker = body["providers"]["anthropic-direct"]["breaker"]

    assert breaker["last_failure_class"] == "misconfigured"
    assert breaker["last_failure_class"] in UPSTREAM_ERROR_KINDS
    assert breaker["state"] == "open"
    assert 290 <= breaker["retry_after_seconds"] <= 300
    assert "CANARY" not in response.text
    for provider in body["providers"].values():
        assert set(provider) == {"breaker"}
        assert not {"message", "detail", "error"} & set(provider["breaker"])


def test_a_pruned_provider_is_not_listed(clock, registry, provider_file, monkeypatch):  # noqa: F811
    health.record("anthropic-direct", _err("timeout"))
    assert "anthropic-direct" in _get()["providers"]

    provider_file(_ONE_YAML)
    body = _get()

    assert set(body["providers"]) == {"alpha"}


def test_status_requires_stats_read(temp_db, clock, registry):
    assert client.get("/providers/status").status_code == 401

    insert_user(User(user_id="ana", role="user", token_hash=hash_token("ana-token")))
    response = client.get(
        "/providers/status", headers={"Authorization": "Bearer ana-token"}
    )
    other = client.get("/storage/status", headers={"Authorization": "Bearer ana-token"})

    assert response.status_code == 403
    assert response.json() == {"detail": f"Permission denied: {PERMISSION_STATS_READ}"}
    assert response.json() == other.json()
