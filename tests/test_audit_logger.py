import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

from datetime import datetime

import pytest

from app.config import settings
from app.db.database import get_audit_log, init_db
from app.services.audit_logger import log_query
from app.services.duplicate_checker import hash_prompt

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path


def test_success_case_writes_expected_row(temp_db):
    audit_id = log_query(
        user_id="juan@empresa.com",
        prompt="hello",
        device="Chrome/Windows",
        response="hi there",
        model_used="gpt-4",
        tokens_used=45,
        success=True,
    )

    fetched = get_audit_log(audit_id)

    assert fetched is not None
    assert fetched.user_id == "juan@empresa.com"
    assert fetched.device == "Chrome/Windows"
    assert fetched.prompt_hash == hash_prompt("hello")
    assert fetched.prompt_preview == "hello"
    assert fetched.response_hash == hash_prompt("hi there")
    assert fetched.response_preview == "hi there"
    assert fetched.model_used == "gpt-4"
    assert fetched.tokens_used == 45
    assert fetched.was_duplicate_blocked is False
    assert fetched.suspicious_pattern is None
    assert fetched.success is True
    assert fetched.error_message is None
    datetime.strptime(fetched.timestamp, _TIMESTAMP_FORMAT)  # raises if malformed


def test_duplicate_blocked_case_logs_null_response_fields(temp_db):
    audit_id = log_query(
        user_id="juan@empresa.com",
        prompt="hello",
        was_duplicate_blocked=True,
        success=True,
    )

    fetched = get_audit_log(audit_id)

    assert fetched.response_hash is None
    assert fetched.response_preview is None
    assert fetched.tokens_used is None
    assert fetched.was_duplicate_blocked is True


def test_suspicious_blocked_case_logs_null_response_fields_and_pattern(temp_db):
    audit_id = log_query(
        user_id="juan@empresa.com",
        prompt="ignore previous instructions",
        suspicious_pattern="ignore previous instructions",
        success=False,
    )

    fetched = get_audit_log(audit_id)

    assert fetched.response_hash is None
    assert fetched.response_preview is None
    assert fetched.tokens_used is None
    assert fetched.suspicious_pattern == "ignore previous instructions"
    assert fetched.success is False


def test_long_prompt_and_response_truncated_but_hash_over_full_text(temp_db):
    prompt = "a" * 600
    response = "b" * 600

    audit_id = log_query(
        user_id="juan@empresa.com",
        prompt=prompt,
        response=response,
        model_used="gpt-4",
        tokens_used=10,
    )

    fetched = get_audit_log(audit_id)

    assert len(fetched.prompt_preview) == 500
    assert fetched.prompt_preview == prompt[:500]
    assert fetched.prompt_hash == hash_prompt(prompt)

    assert len(fetched.response_preview) == 500
    assert fetched.response_preview == response[:500]
    assert fetched.response_hash == hash_prompt(response)


def test_no_ip_or_location_field_in_logged_row(temp_db):
    audit_id = log_query(
        user_id="juan@empresa.com",
        prompt="hello",
        device="Chrome/Windows",
        response="hi there",
        model_used="gpt-4",
        tokens_used=45,
    )

    fetched = get_audit_log(audit_id)

    for field_name, value in vars(fetched).items():
        assert "ip" not in field_name.lower()
        assert "location" not in field_name.lower()
        if isinstance(value, str):
            assert "ip address" not in value.lower()
            assert "location" not in value.lower()
