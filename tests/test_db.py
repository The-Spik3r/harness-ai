import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import sqlite3

import pytest

from app.config import settings
from app.db.database import (
    count_audit_logs,
    count_blocked_duplicates,
    count_blocked_suspicious,
    count_successful_queries,
    count_unique_users,
    get_audit_log,
    get_connection,
    init_db,
    insert_audit_log,
    list_audit_logs,
    top_models,
    top_users,
)
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


def test_count_audit_logs_empty_returns_zero(temp_db):
    assert count_audit_logs() == 0


def test_count_audit_logs_reflects_inserted_rows(temp_db):
    for i in range(3):
        insert_audit_log(
            AuditLog(
                timestamp=f"2026-07-0{i + 1}T10:00:00Z",
                user_id="juan@empresa.com",
                prompt_hash=f"hash{i}",
            )
        )

    assert count_audit_logs() == 3


def test_list_audit_logs_orders_newest_first(temp_db):
    insert_audit_log(
        AuditLog(timestamp="2026-07-02T10:00:00Z", user_id="a", prompt_hash="h2")
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-04T10:00:00Z", user_id="a", prompt_hash="h4")
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-01T10:00:00Z", user_id="a", prompt_hash="h1")
    )

    entries = list_audit_logs()

    assert [entry.timestamp for entry in entries] == [
        "2026-07-04T10:00:00Z",
        "2026-07-02T10:00:00Z",
        "2026-07-01T10:00:00Z",
    ]


def test_list_audit_logs_respects_limit(temp_db):
    insert_audit_log(
        AuditLog(timestamp="2026-07-01T10:00:00Z", user_id="a", prompt_hash="h1")
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-02T10:00:00Z", user_id="a", prompt_hash="h2")
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-03T10:00:00Z", user_id="a", prompt_hash="h3")
    )

    entries = list_audit_logs(limit=2)

    assert len(entries) == 2
    assert [entry.timestamp for entry in entries] == [
        "2026-07-03T10:00:00Z",
        "2026-07-02T10:00:00Z",
    ]


def test_list_audit_logs_fewer_than_limit_returns_all(temp_db):
    insert_audit_log(
        AuditLog(timestamp="2026-07-01T10:00:00Z", user_id="a", prompt_hash="h1")
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-02T10:00:00Z", user_id="a", prompt_hash="h2")
    )

    entries = list_audit_logs(limit=100)

    assert len(entries) == 2


def test_count_blocked_duplicates_counts_only_flagged_rows(temp_db):
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-01T10:00:00Z",
            user_id="a",
            prompt_hash="h1",
            was_duplicate_blocked=True,
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-02T10:00:00Z",
            user_id="a",
            prompt_hash="h2",
            was_duplicate_blocked=True,
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-03T10:00:00Z",
            user_id="a",
            prompt_hash="h3",
            was_duplicate_blocked=False,
        )
    )

    assert count_blocked_duplicates() == 2


def test_count_blocked_suspicious_counts_only_flagged_rows(temp_db):
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-01T10:00:00Z",
            user_id="a",
            prompt_hash="h1",
            suspicious_pattern="override",
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-02T10:00:00Z",
            user_id="a",
            prompt_hash="h2",
            suspicious_pattern="admin mode",
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-03T10:00:00Z",
            user_id="a",
            prompt_hash="h3",
            suspicious_pattern=None,
        )
    )

    assert count_blocked_suspicious() == 2


def test_count_unique_users_deduplicates(temp_db):
    insert_audit_log(
        AuditLog(timestamp="2026-07-01T10:00:00Z", user_id="a", prompt_hash="h1")
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-02T10:00:00Z", user_id="a", prompt_hash="h2")
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-03T10:00:00Z", user_id="b", prompt_hash="h3")
    )

    assert count_unique_users() == 2


def test_count_successful_queries_counts_only_success_true(temp_db):
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-01T10:00:00Z",
            user_id="a",
            prompt_hash="h1",
            success=True,
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-02T10:00:00Z",
            user_id="a",
            prompt_hash="h2",
            success=True,
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-03T10:00:00Z",
            user_id="a",
            prompt_hash="h3",
            success=False,
        )
    )

    assert count_successful_queries() == 2


def test_top_models_ranked_by_count_desc(temp_db):
    for i in range(3):
        insert_audit_log(
            AuditLog(
                timestamp=f"2026-07-0{i + 1}T10:00:00Z",
                user_id="a",
                prompt_hash=f"gpt{i}",
                model_used="gpt-4",
            )
        )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-04T10:00:00Z",
            user_id="a",
            prompt_hash="claude1",
            model_used="claude-3-sonnet",
        )
    )

    assert top_models() == ["gpt-4", "claude-3-sonnet"]


def test_top_models_respects_limit(temp_db):
    for i in range(3):
        insert_audit_log(
            AuditLog(
                timestamp=f"2026-07-0{i + 1}T10:00:00Z",
                user_id="a",
                prompt_hash=f"m1-{i}",
                model_used="model-1",
            )
        )
    for i in range(2):
        insert_audit_log(
            AuditLog(
                timestamp=f"2026-07-0{i + 4}T10:00:00Z",
                user_id="a",
                prompt_hash=f"m2-{i}",
                model_used="model-2",
            )
        )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-06T10:00:00Z",
            user_id="a",
            prompt_hash="m3-0",
            model_used="model-3",
        )
    )

    result = top_models(limit=2)

    assert result == ["model-1", "model-2"]


def test_top_users_ranked_by_count_desc(temp_db):
    for i in range(3):
        insert_audit_log(
            AuditLog(
                timestamp=f"2026-07-0{i + 1}T10:00:00Z",
                user_id="a",
                prompt_hash=f"ha{i}",
            )
        )
    insert_audit_log(
        AuditLog(timestamp="2026-07-04T10:00:00Z", user_id="b", prompt_hash="hb1")
    )

    assert top_users() == ["a", "b"]


def test_aggregates_on_empty_db_return_zero_or_empty(temp_db):
    assert count_blocked_duplicates() == 0
    assert count_blocked_suspicious() == 0
    assert count_unique_users() == 0
    assert count_successful_queries() == 0
    assert top_models() == []
    assert top_users() == []
