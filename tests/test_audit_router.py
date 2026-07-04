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


def test_missing_admin_token_rejected_before_db_access(temp_db, monkeypatch):
    monkeypatch.setattr("app.routers.admin.list_audit_logs", _fail_if_called)
    monkeypatch.setattr("app.routers.admin.count_audit_logs", _fail_if_called)

    response = client.get("/audit")

    assert response.status_code in (401, 403)


def test_incorrect_admin_token_rejected(temp_db, monkeypatch):
    monkeypatch.setattr("app.routers.admin.list_audit_logs", _fail_if_called)
    monkeypatch.setattr("app.routers.admin.count_audit_logs", _fail_if_called)

    response = client.get("/audit", headers={"Authorization": "Bearer wrong-token"})

    assert response.status_code in (401, 403)


def test_valid_token_returns_expected_shape(temp_db):
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-04T09:00:00Z",
            user_id="juan@empresa.com",
            device="Chrome/Windows",
            prompt_hash="hash1",
            model_used="gpt-4",
            suspicious_pattern="override",
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-04T10:00:00Z",
            user_id="maria@empresa.com",
            device="Firefox/Linux",
            prompt_hash="hash2",
            model_used="claude-3-sonnet",
            was_duplicate_blocked=True,
        )
    )

    response = client.get(
        "/audit", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["queries"]) == 2
    assert [q["timestamp"] for q in body["queries"]] == [
        "2026-07-04T10:00:00Z",
        "2026-07-04T09:00:00Z",
    ]
    for entry in body["queries"]:
        assert set(entry.keys()) == {
            "audit_id",
            "user_id",
            "timestamp",
            "model",
            "prompt_hash",
            "was_duplicate_blocked",
            "suspicious_pattern_detected",
            "device",
        }

    newest, oldest = body["queries"]
    assert newest["was_duplicate_blocked"] is True
    assert newest["suspicious_pattern_detected"] is False
    assert oldest["suspicious_pattern_detected"] is True
    assert oldest["model"] == "gpt-4"


def test_fewer_than_100_rows_returns_all_without_error(temp_db):
    for i in range(3):
        insert_audit_log(
            AuditLog(
                timestamp=f"2026-07-0{i + 1}T10:00:00Z",
                user_id="juan@empresa.com",
                prompt_hash=f"hash{i}",
            )
        )

    response = client.get(
        "/audit", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["queries"]) == 3


def test_response_never_includes_ip_or_raw_text(temp_db):
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-04T10:00:00Z",
            user_id="juan@empresa.com",
            device="Chrome/Windows",
            prompt_hash="hash1",
            prompt_preview="this is a raw prompt preview",
            response_hash="resphash1",
            response_preview="this is a raw response preview",
            model_used="gpt-4",
        )
    )

    response = client.get(
        "/audit", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    assert response.status_code == 200
    body = response.json()
    for entry in body["queries"]:
        assert not any("ip" in key.lower() for key in entry.keys())
        assert "prompt" not in entry or entry.get("prompt_hash") == "hash1"
        assert "response" not in entry
        assert "prompt_preview" not in entry
        assert "response_preview" not in entry
        assert "response_hash" not in entry
