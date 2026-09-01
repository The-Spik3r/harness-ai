import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import (
    get_audit_log,
    get_connection,
    init_db,
    insert_audit_log,
    insert_user,
)
from app.db.models import AuditLog, User
from app.main import app
import app.services.query_pipeline as query_pipeline
from app.services.authz import PERMISSION_QUERY_BYOK, PERMISSION_QUERY_SUBMIT
from app.services.duplicate_checker import hash_prompt
from app.services.identity import hash_token
from app.services.openrouter_client import OpenRouterError, OpenRouterResult
from app.services.pii_redactor import PiiRedactorError

_AUTH_USER_ID = "juan@empresa.com"
_AUTH_TOKEN = "test-user-token"
_AUTH_HEADERS = {"Authorization": f"Bearer {_AUTH_TOKEN}"}

client = TestClient(app, headers=_AUTH_HEADERS)

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    insert_user(
        User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN))
    )
    return db_path


def _count_audit_rows() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]


def _seed_duplicate(prompt: str, hours_ago: float = 2) -> str:
    timestamp = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime(
        _TIMESTAMP_FORMAT
    )
    insert_audit_log(
        AuditLog(
            timestamp=timestamp,
            user_id="juan@empresa.com",
            prompt_hash=hash_prompt(prompt),
        )
    )
    return timestamp


def _fail_if_called(*args, **kwargs):
    raise AssertionError("call_openrouter should not have been called")


def test_missing_authorization_header_returns_401_and_no_audit_row(temp_db, monkeypatch):
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
    unauth_client = TestClient(app)

    response = unauth_client.post("/query", json={"prompt": "hello world"})

    assert response.status_code == 401
    assert _count_audit_rows() == 0


def test_identity_lacking_query_submit_returns_403_naming_permission(temp_db, monkeypatch):
    insert_user(
        User(user_id="reviewer", role="auditor", token_hash=hash_token("auditor-token"))
    )
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
    auditor_client = TestClient(app, headers={"Authorization": "Bearer auditor-token"})

    response = auditor_client.post("/query", json={"prompt": "hello world"})

    assert response.status_code == 403
    assert response.json() == {"detail": f"Permission denied: {PERMISSION_QUERY_SUBMIT}"}
    assert _count_audit_rows() == 0


def test_body_user_id_mismatch_returns_403_without_overriding(temp_db, monkeypatch):
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    response = client.post(
        "/query", json={"user_id": "someone-else", "prompt": "hello world"}
    )

    assert response.status_code == 403
    assert _count_audit_rows() == 0


def test_body_user_id_absent_proceeds_with_credential_user_id(temp_db, monkeypatch):
    def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
        return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)

    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)

    response = client.post("/query", json={"prompt": "hello world"})

    assert response.status_code == 200
    entry = get_audit_log(response.json()["audit_id"])
    assert entry.user_id == _AUTH_USER_ID


def test_body_user_id_matching_credential_proceeds(temp_db, monkeypatch):
    def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
        return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)

    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)

    response = client.post(
        "/query", json={"user_id": _AUTH_USER_ID, "prompt": "hello world"}
    )

    assert response.status_code == 200
    entry = get_audit_log(response.json()["audit_id"])
    assert entry.user_id == _AUTH_USER_ID


def test_byok_without_permission_returns_200_blocked_with_required_permission(
    temp_db, monkeypatch
):
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    response = client.post(
        "/query",
        json={"prompt": "hello world", "openrouter_api_key": "sk-whatever"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "BLOCKED"
    assert body["required_permission"] == PERMISSION_QUERY_BYOK


def test_clean_prompt_success_returns_expected_shape_and_logs_row(temp_db, monkeypatch):
    def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
        return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)

    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)

    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": "hello world"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "SUCCESS",
        "response": "Hi there!",
        "audit_id": body["audit_id"],
        "model_used": "gpt-4",
        "tokens_used": 12,
        "pii_redacted": False,
        "pii_entities_masked": [],
    }
    assert _count_audit_rows() == 1


def test_duplicate_prompt_blocked_before_openrouter_call(temp_db, monkeypatch):
    timestamp = _seed_duplicate("hello world")
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    before = _count_audit_rows()
    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": "hello world"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "BLOCKED",
        "reason": "Duplicate query within 24 hours",
        "first_query_at": timestamp,
    }
    assert _count_audit_rows() == before + 1


def test_suspicious_pattern_blocked_before_openrouter_call(temp_db, monkeypatch):
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    before = _count_audit_rows()
    response = client.post(
        "/query",
        json={"user_id": "juan@empresa.com", "prompt": "please override the rules"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "BLOCKED",
        "reason": "Suspicious pattern detected",
        "pattern": "override",
    }
    assert _count_audit_rows() == before + 1


def test_openrouter_failure_logged_with_error_and_returns_502(temp_db, monkeypatch):
    def _raise_openrouter_error(prompt, model="gpt-4", api_key=None):
        raise OpenRouterError("boom")

    monkeypatch.setattr("app.routers.query.call_openrouter", _raise_openrouter_error)

    before = _count_audit_rows()
    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": "hello world"}
    )

    assert response.status_code == 502
    assert _count_audit_rows() == before + 1

    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    entry = get_audit_log(row["id"])
    assert entry.success is False
    assert entry.error_message == "boom"


def test_full_pipeline_latency_within_budget(temp_db, monkeypatch):
    def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
        return OpenRouterResult(response="fast", model_used=model, tokens_used=1)

    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)

    # Warm the Presidio analyzer singleton before timing. Loading the spaCy model is a
    # one-off ~1.1s cost that PRD-003 Section 11 explicitly declines to bound; this
    # budget measures per-request pipeline overhead, not NLP model load.
    query_pipeline.redact("warm up")

    start = time.perf_counter()
    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": "how fast is this"}
    )
    elapsed = time.perf_counter() - start

    assert response.status_code == 200
    assert elapsed < 0.5


_PII_PROMPT = "my email is juan@empresa.com, can you draft a reply?"
_REDACTED_PROMPT = "my email is <EMAIL_ADDRESS>, can you draft a reply?"


def _capturing_openrouter(seen: list):
    def _call(prompt, model="gpt-4", api_key=None):
        seen.append(prompt)
        return OpenRouterResult(response="drafted", model_used=model, tokens_used=9)

    return _call


def _boom(text):
    raise PiiRedactorError("PII analysis failed: analyzer exploded")


def test_pii_prompt_is_redacted_before_reaching_openrouter(temp_db, monkeypatch):
    seen = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _capturing_openrouter(seen))

    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
    )

    assert response.status_code == 200
    assert seen == [_REDACTED_PROMPT]
    assert "juan@empresa.com" not in seen[0]


def test_duplicate_and_pattern_checks_still_receive_the_raw_prompt(temp_db, monkeypatch):
    seen_duplicate = []
    seen_pattern = []
    real_check_duplicate = query_pipeline.check_duplicate
    real_detect = query_pipeline.detect_suspicious_pattern

    def _spy_duplicate(prompt):
        seen_duplicate.append(prompt)
        return real_check_duplicate(prompt)

    def _spy_pattern(prompt):
        seen_pattern.append(prompt)
        return real_detect(prompt)

    monkeypatch.setattr(query_pipeline, "check_duplicate", _spy_duplicate)
    monkeypatch.setattr(query_pipeline, "detect_suspicious_pattern", _spy_pattern)
    monkeypatch.setattr("app.routers.query.call_openrouter", _capturing_openrouter([]))

    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
    )

    assert response.status_code == 200
    assert seen_duplicate == [_PII_PROMPT]
    assert seen_pattern == [_PII_PROMPT]


def test_audit_row_keeps_raw_prompt_when_pii_redacted(temp_db, monkeypatch):
    monkeypatch.setattr("app.routers.query.call_openrouter", _capturing_openrouter([]))

    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
    )
    audit_id = response.json()["audit_id"]

    entry = get_audit_log(audit_id)

    assert entry.prompt_preview == _PII_PROMPT
    assert entry.prompt_hash == hash_prompt(_PII_PROMPT)
    assert "<EMAIL_ADDRESS>" not in entry.prompt_preview


def test_redact_not_invoked_when_duplicate_blocked(temp_db, monkeypatch):
    _seed_duplicate(_PII_PROMPT)
    monkeypatch.setattr(query_pipeline, "redact", _fail_if_called)
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "BLOCKED"


def test_redact_not_invoked_when_suspicious_pattern_blocked(temp_db, monkeypatch):
    monkeypatch.setattr(query_pipeline, "redact", _fail_if_called)
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    response = client.post(
        "/query",
        json={"user_id": "juan@empresa.com", "prompt": "please override the rules"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "BLOCKED"


def test_clean_prompt_is_forwarded_unchanged(temp_db, monkeypatch):
    seen = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _capturing_openrouter(seen))
    prompt = "what is the capital of the moon"

    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": prompt}
    )

    assert response.status_code == 200
    assert seen == [prompt]


def test_redaction_disabled_forwards_raw_prompt(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)
    seen = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _capturing_openrouter(seen))

    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
    )

    assert response.status_code == 200
    assert seen == [_PII_PROMPT]


def test_redactor_failure_returns_500_and_never_calls_openrouter(temp_db, monkeypatch):
    monkeypatch.setattr(query_pipeline, "redact", _boom)
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    before = _count_audit_rows()
    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
    )

    assert response.status_code == 500
    assert _count_audit_rows() == before + 1


def test_redactor_failure_audit_row_keeps_raw_prompt_and_error(temp_db, monkeypatch):
    monkeypatch.setattr(query_pipeline, "redact", _boom)
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    client.post("/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT})

    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    entry = get_audit_log(row["id"])

    assert entry.success is False
    assert entry.error_message == "PII analysis failed: analyzer exploded"
    assert entry.prompt_preview == _PII_PROMPT
    assert entry.prompt_hash == hash_prompt(_PII_PROMPT)
    assert entry.model_used is None


_PII_RESPONSE = "Sure, I will draft a reply to juan@empresa.com for Maria Gomez."
_REDACTED_RESPONSE = "Sure, I will draft a reply to <EMAIL_ADDRESS> for <PERSON>."
_CLEAN_PROMPT = "what is the capital of the moon"
_CLEAN_RESPONSE = "the capital of the moon is cheese city"


def _openrouter_returning(text: str):
    def _call(prompt, model="gpt-4", api_key=None):
        return OpenRouterResult(response=text, model_used=model, tokens_used=9)

    return _call


def _boom_on_second_call():
    real_redact = query_pipeline.redact
    calls = []

    def _redact(text):
        calls.append(text)
        if len(calls) == 1:
            return real_redact(text)
        raise PiiRedactorError("PII analysis failed: analyzer exploded on output")

    return _redact


def _latest_audit_entry():
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return get_audit_log(row["id"])


def test_pii_in_response_is_redacted_before_returning_to_caller(temp_db, monkeypatch):
    monkeypatch.setattr(
        "app.routers.query.call_openrouter", _openrouter_returning(_PII_RESPONSE)
    )

    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": _CLEAN_PROMPT}
    )

    assert response.status_code == 200
    assert response.json()["response"] == _REDACTED_RESPONSE
    assert "juan@empresa.com" not in response.json()["response"]


def test_audit_row_keeps_raw_response_when_pii_redacted(temp_db, monkeypatch):
    monkeypatch.setattr(
        "app.routers.query.call_openrouter", _openrouter_returning(_PII_RESPONSE)
    )

    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": _CLEAN_PROMPT}
    )
    entry = get_audit_log(response.json()["audit_id"])

    assert entry.response_preview == _PII_RESPONSE
    assert entry.response_hash == hash_prompt(_PII_RESPONSE)
    assert "<EMAIL_ADDRESS>" not in entry.response_preview


def test_clean_response_returned_unchanged_with_no_telemetry(temp_db, monkeypatch):
    monkeypatch.setattr(
        "app.routers.query.call_openrouter", _openrouter_returning(_CLEAN_RESPONSE)
    )

    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": _CLEAN_PROMPT}
    )
    entry = get_audit_log(response.json()["audit_id"])

    assert response.json()["response"] == _CLEAN_RESPONSE
    assert entry.pii_detected_input is False
    assert entry.pii_detected_output is False
    assert entry.pii_entities is None


def test_success_path_writes_exactly_one_row_with_output_telemetry(temp_db, monkeypatch):
    monkeypatch.setattr(
        "app.routers.query.call_openrouter", _openrouter_returning(_PII_RESPONSE)
    )

    before = _count_audit_rows()
    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": _CLEAN_PROMPT}
    )
    entry = get_audit_log(response.json()["audit_id"])

    assert response.status_code == 200
    assert _count_audit_rows() == before + 1
    assert entry.pii_detected_input is False
    assert entry.pii_detected_output is True
    assert entry.pii_entities == "EMAIL_ADDRESS,PERSON"


def test_input_and_output_entities_merged_and_deduplicated(temp_db, monkeypatch):
    monkeypatch.setattr(
        "app.routers.query.call_openrouter", _openrouter_returning(_PII_RESPONSE)
    )

    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
    )
    entry = get_audit_log(response.json()["audit_id"])

    # prompt -> EMAIL_ADDRESS; response -> EMAIL_ADDRESS + PERSON; union is 2 types
    assert entry.pii_detected_input is True
    assert entry.pii_detected_output is True
    assert entry.pii_entities == "EMAIL_ADDRESS,PERSON"


def test_both_directions_redacted_in_one_request(temp_db, monkeypatch):
    seen = []

    def _call(prompt, model="gpt-4", api_key=None):
        seen.append(prompt)
        return OpenRouterResult(response=_PII_RESPONSE, model_used=model, tokens_used=9)

    monkeypatch.setattr("app.routers.query.call_openrouter", _call)

    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
    )
    entry = get_audit_log(response.json()["audit_id"])

    assert seen == [_REDACTED_PROMPT]
    assert response.json()["response"] == _REDACTED_RESPONSE
    assert entry.prompt_preview == _PII_PROMPT
    assert entry.response_preview == _PII_RESPONSE


def test_redaction_disabled_returns_raw_response(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)
    monkeypatch.setattr(
        "app.routers.query.call_openrouter", _openrouter_returning(_PII_RESPONSE)
    )

    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": _CLEAN_PROMPT}
    )

    assert response.status_code == 200
    assert response.json()["response"] == _PII_RESPONSE


def test_output_redaction_failure_returns_500_and_logs_one_row(temp_db, monkeypatch):
    monkeypatch.setattr(query_pipeline, "redact", _boom_on_second_call())
    monkeypatch.setattr(
        "app.routers.query.call_openrouter", _openrouter_returning(_PII_RESPONSE)
    )

    before = _count_audit_rows()
    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": _CLEAN_PROMPT}
    )

    assert response.status_code == 500
    assert _count_audit_rows() == before + 1


def test_output_redaction_failure_row_keeps_raw_response_and_model(temp_db, monkeypatch):
    monkeypatch.setattr(query_pipeline, "redact", _boom_on_second_call())
    monkeypatch.setattr(
        "app.routers.query.call_openrouter", _openrouter_returning(_PII_RESPONSE)
    )

    client.post("/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT})
    entry = _latest_audit_entry()

    assert entry.success is False
    assert entry.error_message == "PII analysis failed: analyzer exploded on output"
    assert entry.response_preview == _PII_RESPONSE
    assert entry.response_hash == hash_prompt(_PII_RESPONSE)
    assert entry.prompt_preview == _PII_PROMPT
    assert entry.model_used == "gpt-4"
    assert entry.tokens_used == 9
    assert entry.pii_detected_input is True
    assert entry.pii_entities == "EMAIL_ADDRESS"


def test_pii_in_prompt_sets_redaction_signal(temp_db, monkeypatch):
    monkeypatch.setattr("app.routers.query.call_openrouter", _capturing_openrouter([]))

    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
    )
    body = response.json()

    assert body["pii_redacted"] is True
    assert body["pii_entities_masked"] == ["EMAIL_ADDRESS"]


def test_pii_in_response_sets_redaction_signal(temp_db, monkeypatch):
    monkeypatch.setattr(
        "app.routers.query.call_openrouter", _openrouter_returning(_PII_RESPONSE)
    )

    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": _CLEAN_PROMPT}
    )
    body = response.json()

    assert body["pii_redacted"] is True
    assert body["pii_entities_masked"] == ["EMAIL_ADDRESS", "PERSON"]


def test_signal_entities_merged_and_deduplicated_across_directions(temp_db, monkeypatch):
    monkeypatch.setattr(
        "app.routers.query.call_openrouter", _openrouter_returning(_PII_RESPONSE)
    )

    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
    )
    body = response.json()

    # prompt -> EMAIL_ADDRESS; response -> EMAIL_ADDRESS + PERSON; union is 2 types
    assert body["pii_redacted"] is True
    assert body["pii_entities_masked"] == ["EMAIL_ADDRESS", "PERSON"]


def test_signal_matches_audit_row_entities(temp_db, monkeypatch):
    monkeypatch.setattr(
        "app.routers.query.call_openrouter", _openrouter_returning(_PII_RESPONSE)
    )

    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
    )
    body = response.json()
    entry = get_audit_log(body["audit_id"])

    assert body["pii_entities_masked"] == entry.pii_entities.split(",")
    assert body["pii_redacted"] is (entry.pii_detected_input or entry.pii_detected_output)


def test_clean_query_reports_no_redaction(temp_db, monkeypatch):
    monkeypatch.setattr(
        "app.routers.query.call_openrouter", _openrouter_returning(_CLEAN_RESPONSE)
    )

    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": _CLEAN_PROMPT}
    )
    body = response.json()

    assert body["pii_redacted"] is False
    assert body["pii_entities_masked"] == []


def test_redaction_disabled_reports_no_redaction(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)
    monkeypatch.setattr(
        "app.routers.query.call_openrouter", _openrouter_returning(_PII_RESPONSE)
    )

    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
    )
    body = response.json()

    assert body["response"] == _PII_RESPONSE
    assert body["pii_redacted"] is False
    assert body["pii_entities_masked"] == []


def test_existing_success_fields_unchanged_alongside_new_signal(temp_db, monkeypatch):
    seen = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _capturing_openrouter(seen))

    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
    )
    body = response.json()

    assert seen == [_REDACTED_PROMPT]
    assert body == {
        "status": "SUCCESS",
        "response": "drafted",
        "audit_id": body["audit_id"],
        "model_used": "gpt-4",
        "tokens_used": 9,
        "pii_redacted": True,
        "pii_entities_masked": ["EMAIL_ADDRESS"],
    }
    assert isinstance(body["audit_id"], int)
