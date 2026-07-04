import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import sqlite3

import pytest

from app.config import settings
from app.db.database import get_audit_log, get_connection, init_db, insert_audit_log
from app.db.models import AuditLog


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path


def test_init_db_creates_table(temp_db):
    init_db()  # calling twice must not raise or duplicate the schema

    with get_connection() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_logs'"
        ).fetchone()
    assert row is not None


def test_insert_and_read_round_trip(temp_db):
    entry = AuditLog(
        timestamp="2026-07-04T10:30:00Z",
        user_id="juan@empresa.com",
        prompt_hash="abc123",
        device="Chrome/Windows",
        prompt_preview="hola mundo",
        response_hash="def456",
        response_preview="respuesta",
        model_used="gpt-4",
        tokens_used=45,
        was_duplicate_blocked=True,
        suspicious_pattern="override",
        success=False,
        error_message="upstream timeout",
    )

    new_id = insert_audit_log(entry)
    fetched = get_audit_log(new_id)

    assert fetched is not None
    assert fetched.id == new_id
    assert fetched.timestamp == entry.timestamp
    assert fetched.user_id == entry.user_id
    assert fetched.device == entry.device
    assert fetched.prompt_hash == entry.prompt_hash
    assert fetched.prompt_preview == entry.prompt_preview
    assert fetched.response_hash == entry.response_hash
    assert fetched.response_preview == entry.response_preview
    assert fetched.model_used == entry.model_used
    assert fetched.tokens_used == entry.tokens_used
    assert fetched.was_duplicate_blocked is True
    assert fetched.suspicious_pattern == entry.suspicious_pattern
    assert fetched.success is False
    assert fetched.error_message == entry.error_message


def test_get_audit_log_missing_id_returns_none(temp_db):
    assert get_audit_log(999) is None


def test_schema_has_no_ip_or_location_column(temp_db):
    with get_connection() as conn:
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")]

    expected = {
        "id",
        "timestamp",
        "user_id",
        "device",
        "prompt_hash",
        "prompt_preview",
        "response_hash",
        "response_preview",
        "model_used",
        "tokens_used",
        "was_duplicate_blocked",
        "suspicious_pattern",
        "success",
        "error_message",
    }
    assert set(columns) == expected
    assert not any("ip" in c.lower() or "location" in c.lower() for c in columns)
