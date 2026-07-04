import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import init_db, insert_audit_log
from app.db.models import AuditLog
from app.main import app

client = TestClient(app)


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path


def _fail_if_called(*args, **kwargs):
    raise AssertionError("repository function should not have been called")


def _guard_all_aggregates(monkeypatch):
    for name in (
        "count_audit_logs",
        "count_blocked_duplicates",
        "count_blocked_suspicious",
        "count_unique_users",
        "count_successful_queries",
        "top_models",
        "top_users",
    ):
        monkeypatch.setattr(f"app.routers.admin.{name}", _fail_if_called)


def test_missing_admin_token_rejected_before_aggregation(temp_db, monkeypatch):
    _guard_all_aggregates(monkeypatch)

    response = client.get("/stats")

    assert response.status_code in (401, 403)


def test_incorrect_admin_token_rejected(temp_db, monkeypatch):
    _guard_all_aggregates(monkeypatch)

    response = client.get("/stats", headers={"Authorization": "Bearer wrong-token"})

    assert response.status_code in (401, 403)


def test_valid_token_returns_expected_shape_and_values(temp_db):
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-01T10:00:00Z",
            user_id="a",
            prompt_hash="h1",
            model_used="gpt-4",
            success=True,
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-02T10:00:00Z",
            user_id="a",
            prompt_hash="h2",
            model_used="gpt-4",
            success=True,
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-03T10:00:00Z",
            user_id="a",
            prompt_hash="h3",
            was_duplicate_blocked=True,
            success=False,
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-04T10:00:00Z",
            user_id="b",
            prompt_hash="h4",
            suspicious_pattern="override",
            success=False,
        )
    )

    response = client.get(
        "/stats", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "total_queries",
        "blocked_duplicates",
        "blocked_suspicious",
        "unique_users",
        "success_rate",
        "top_models",
        "top_users",
    }
    assert body["total_queries"] == 4
    assert body["blocked_duplicates"] == 1
    assert body["blocked_suspicious"] == 1
    assert body["unique_users"] == 2
    assert body["success_rate"] == "50.0%"
    assert body["top_models"] == ["gpt-4"]
    assert body["top_users"] == ["a", "b"]


def test_zero_rows_returns_zeroed_stats_without_error(temp_db):
    response = client.get(
        "/stats", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "total_queries": 0,
        "blocked_duplicates": 0,
        "blocked_suspicious": 0,
        "unique_users": 0,
        "success_rate": "0.0%",
        "top_models": [],
        "top_users": [],
    }
