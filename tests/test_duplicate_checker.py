import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.db.database import init_db, insert_audit_log
from app.db.models import AuditLog
from app.services.duplicate_checker import (
    DuplicateCheckError,
    check_duplicate,
    hash_prompt,
)

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _timestamp(hours_ago: float) -> str:
    dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return dt.strftime(_TIMESTAMP_FORMAT)


def _seed(prompt_hash: str, hours_ago: float) -> str:
    timestamp = _timestamp(hours_ago)
    insert_audit_log(
        AuditLog(
            timestamp=timestamp,
            user_id="juan@empresa.com",
            prompt_hash=prompt_hash,
        )
    )
    return timestamp


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path


@pytest.fixture
def uninitialized_db(tmp_path, monkeypatch):
    db_path = tmp_path / "malformed.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_no_duplicate_when_no_matching_row(temp_db):
    result = check_duplicate("hello world")
    assert result.is_duplicate is False
    assert result.first_query_at is None


def test_duplicate_detected_within_24h(temp_db):
    timestamp = _seed(hash_prompt("hello world"), hours_ago=2)

    result = check_duplicate("hello world")

    assert result.is_duplicate is True
    assert result.first_query_at == timestamp


def test_not_duplicate_when_older_than_24h(temp_db):
    _seed(hash_prompt("hello world"), hours_ago=25)

    result = check_duplicate("hello world")

    assert result.is_duplicate is False


def test_boundary_just_inside_24h(temp_db):
    timestamp = _seed(hash_prompt("hello world"), hours_ago=23 + 59 / 60)

    result = check_duplicate("hello world")

    assert result.is_duplicate is True
    assert result.first_query_at == timestamp


def test_boundary_just_outside_24h(temp_db):
    _seed(hash_prompt("hello world"), hours_ago=24 + 1 / 60)

    result = check_duplicate("hello world")

    assert result.is_duplicate is False


def test_whitespace_difference_produces_different_hash_and_not_flagged(temp_db):
    assert hash_prompt("hello world") != hash_prompt("hello world ")

    _seed(hash_prompt("hello world"), hours_ago=2)

    result = check_duplicate("hello world ")

    assert result.is_duplicate is False


def test_earliest_entry_returned_as_first_query_at(temp_db):
    prompt_hash = hash_prompt("hello world")
    earliest = _seed(prompt_hash, hours_ago=10)
    _seed(prompt_hash, hours_ago=3)

    result = check_duplicate("hello world")

    assert result.is_duplicate is True
    assert result.first_query_at == earliest


def test_malformed_db_raises_duplicate_check_error(uninitialized_db):
    with pytest.raises(DuplicateCheckError):
        check_duplicate("anything")
