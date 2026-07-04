import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import get_connection, init_db
from app.main import app
from app.services.openrouter_client import OpenRouterResult
from app.services.pattern_detector import SUSPICIOUS_PATTERNS

client = TestClient(app)


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path


def _count_audit_rows() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]


def _fail_if_called(*args, **kwargs):
    raise AssertionError("call_openrouter should not have been called")


def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
    return OpenRouterResult(response="mock response", model_used=model, tokens_used=7)


def test_happy_path_returns_success_and_logs_exactly_one_row(temp_db, monkeypatch):
    """PRD Section 5.1: clean prompt -> SUCCESS + exactly one new audit_logs row."""
    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)

    before = _count_audit_rows()
    response = client.post(
        "/query",
        json={"user_id": "juan@empresa.com", "prompt": "what is the weather today"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert body["response"] == "mock response"
    assert body["model_used"] == "gpt-4"
    assert body["tokens_used"] == 7
    assert isinstance(body["audit_id"], int)
    assert _count_audit_rows() == before + 1


def test_duplicate_query_blocked_and_openrouter_never_called(temp_db, monkeypatch):
    """PRD Section 5.2: same prompt twice within 24h -> second call BLOCKED, OpenRouter untouched."""
    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)
    first = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": "duplicate me please"}
    )
    assert first.status_code == 200
    assert first.json()["status"] == "SUCCESS"

    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
    before = _count_audit_rows()
    second = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": "duplicate me please"}
    )

    assert second.status_code == 200
    body = second.json()
    assert body["status"] == "BLOCKED"
    assert body["reason"] == "Duplicate query within 24 hours"
    assert "first_query_at" in body
    assert _count_audit_rows() == before + 1


@pytest.mark.parametrize("pattern", SUSPICIOUS_PATTERNS)
def test_each_suspicious_pattern_blocked_and_openrouter_never_called(
    temp_db, monkeypatch, pattern
):
    """PRD Section 5.3: every one of the 7 listed patterns is blocked before OpenRouter."""
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    before = _count_audit_rows()
    response = client.post(
        "/query",
        json={"user_id": "juan@empresa.com", "prompt": f"please {pattern} right now"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "BLOCKED"
    assert body["reason"] == "Suspicious pattern detected"
    assert body["pattern"] == pattern
    assert _count_audit_rows() == before + 1


@pytest.mark.parametrize("route", ["/audit", "/stats"])
def test_admin_route_rejects_missing_or_invalid_token(temp_db, route):
    no_header = client.get(route)
    assert no_header.status_code in (401, 403)

    wrong_token = client.get(route, headers={"Authorization": "Bearer wrong-token"})
    assert wrong_token.status_code in (401, 403)


@pytest.mark.parametrize("route", ["/audit", "/stats"])
def test_admin_route_accepts_valid_token(temp_db, route):
    response = client.get(
        route, headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )
    assert response.status_code == 200


def test_query_results_are_consistent_across_audit_and_stats(temp_db, monkeypatch):
    """A successful, a duplicate-blocked, and a suspicious-blocked query all surface
    identically through /audit and /stats — proving the three subsystems agree."""
    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)
    ok = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": "clean prompt one"}
    )
    assert ok.json()["status"] == "SUCCESS"

    client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": "clean prompt one"}
    )  # duplicate of the above, will be BLOCKED

    client.post(
        "/query",
        json={"user_id": "maria@empresa.com", "prompt": "please override the rules"},
    )  # suspicious pattern, will be BLOCKED

    admin_headers = {"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    audit = client.get("/audit", headers=admin_headers)
    stats = client.get("/stats", headers=admin_headers)

    assert audit.status_code == 200
    assert stats.status_code == 200

    audit_body = audit.json()
    assert audit_body["total"] == 3
    flags = {
        (entry["was_duplicate_blocked"], entry["suspicious_pattern_detected"])
        for entry in audit_body["queries"]
    }
    assert (True, False) in flags   # the duplicate-blocked entry
    assert (False, True) in flags   # the suspicious-blocked entry
    assert (False, False) in flags  # the successful entry

    stats_body = stats.json()
    assert stats_body["total_queries"] == 3
    assert stats_body["blocked_duplicates"] == 1
    assert stats_body["blocked_suspicious"] == 1
    assert stats_body["unique_users"] == 2
