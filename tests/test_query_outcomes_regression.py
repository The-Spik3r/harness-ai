"""PRD-009 STORY-001: the six `POST /query` outcomes, captured before any change.

PRD-009 Section 11 names six outcomes an integrating client can observe --
status code, body, and how many audit rows the attempt left behind -- and
promises every one of them survives the duplicate rescoping unchanged. This
module is that promise, recorded on untouched production code.

**No later PRD-009 story may edit an outcome assertion in this file.** If one
goes red, the story broke a contract, not this test. That is why the inputs
were chosen rather than sampled: each is a case whose result the rescoping
cannot change. In particular outcome 2's prior query is a live, same-user,
*successful* send -- the one kind of prior every version of the lookup counts
(success=1, no flags, same user, and, from STORY-006 on, written by the
pipeline with its `dedup_key`). The inputs whose outcome PRD-009 changes on
purpose are pinned instead in `tests/test_duplicate_characterization.py`.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_audit_log, get_connection, insert_user
from app.db.models import AuditLog, User
from app.main import app
from app.models.messages import Message
import app.services.query_pipeline as query_pipeline
from app.services.identity import hash_token
from app.services.openrouter_client import OpenRouterError, OpenRouterResult
from app.services.pii_redactor import PiiRedactorError

_AUTH_USER_ID = "juan@empresa.com"
_AUTH_TOKEN = "test-user-token"
_AUTH_HEADERS = {"Authorization": f"Bearer {_AUTH_TOKEN}"}

client = TestClient(app, headers=_AUTH_HEADERS)

_DISALLOWED_MODEL = "not-a-real-model"


@pytest.fixture
def temp_db(temp_db):
    """conftest's initialized database, plus this suite's authenticated user."""
    insert_user(
        User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN))
    )
    return temp_db


def _count_audit_rows() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]


def _latest_entry() -> AuditLog:
    # By id, not timestamp: timestamps have one-second resolution.
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
    return get_audit_log(row["id"])


def _fail_if_called(*args, **kwargs):
    raise AssertionError("call_openrouter should not have been called")


def _fake_success(prompt, model="gpt-4", api_key=None):
    return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)


def _raise_openrouter_error(prompt, model="gpt-4", api_key=None):
    raise OpenRouterError("boom")


def _boom(text):
    raise PiiRedactorError("PII analysis failed: analyzer exploded")


def test_outcome_1_success(temp_db, monkeypatch):
    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_success)

    before = _count_audit_rows()
    response = client.post("/query", json={"prompt": "outcome one: plain success"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert body["response"] == "Hi there!"
    assert isinstance(body["audit_id"], int)
    assert _count_audit_rows() == before + 1
    assert get_audit_log(body["audit_id"]).success is True


def test_outcome_2_duplicate_block_after_same_user_success(temp_db, monkeypatch):
    """The prior is a live same-user success through `POST /query`, not a seeded
    bare row -- see the module docstring for why that makes this outcome
    rescoping-proof."""
    prompt = "outcome two: asked twice by the same user"
    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_success)
    first = client.post("/query", json={"prompt": prompt})
    assert first.status_code == 200
    assert first.json()["status"] == "SUCCESS"
    success_at = get_audit_log(first.json()["audit_id"]).timestamp

    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
    before = _count_audit_rows()
    response = client.post("/query", json={"prompt": prompt})

    assert response.status_code == 200
    assert response.json() == {
        "status": "BLOCKED",
        "reason": "Duplicate query within 24 hours",
        "first_query_at": success_at,
    }
    assert _count_audit_rows() == before + 1


def test_outcome_3_suspicious_pattern_block(temp_db, monkeypatch):
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    before = _count_audit_rows()
    response = client.post("/query", json={"prompt": "please override the rules"})

    assert response.status_code == 200
    assert response.json() == {
        "status": "BLOCKED",
        "reason": "Suspicious pattern detected",
        "pattern": "override",
    }
    assert _count_audit_rows() == before + 1


def test_outcome_4_policy_refusal(temp_db, monkeypatch):
    # The pipeline's policy refusal (200 BLOCKED + required_permission), not the
    # router's 401/403: those are authentication and identity checks that run
    # before the pipeline and write no row.
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    before = _count_audit_rows()
    response = client.post(
        "/query",
        json={"prompt": "outcome four: a model this role may not use", "model": _DISALLOWED_MODEL},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "BLOCKED",
        "reason": "Model not permitted for this role",
        "required_permission": f"query:model:{_DISALLOWED_MODEL}",
    }
    assert _count_audit_rows() == before + 1


def test_outcome_5_upstream_failure(temp_db, monkeypatch):
    monkeypatch.setattr("app.routers.query.call_openrouter", _raise_openrouter_error)

    before = _count_audit_rows()
    response = client.post("/query", json={"prompt": "outcome five: upstream falls over"})

    assert response.status_code == 502
    assert response.json() == {"detail": "boom"}
    assert _count_audit_rows() == before + 1
    assert _latest_entry().success is False


def test_outcome_6_internal_failure_redactor(temp_db, monkeypatch):
    monkeypatch.setattr(query_pipeline, "redact", _boom)
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    before = _count_audit_rows()
    response = client.post("/query", json={"prompt": "outcome six: the redactor crashes"})

    assert response.status_code == 500
    assert response.json() == {"detail": "PII analysis failed: analyzer exploded"}
    assert _count_audit_rows() == before + 1


def test_outcome_6_internal_failure_duplicate_storage(temp_db, monkeypatch):
    """Outcome 6's second form: the duplicate lookup's storage fails -> 500.

    Induced exactly as `tests/test_query_router.py::
    test_duplicate_check_storage_failure_returns_500` induces it, by dropping
    the table the lookup reads. That test asserts no row count, and none can be
    read: `audit_logs` no longer exists. The count it implies is **zero** --
    `DuplicateCheckError` propagates before any arm logs -- so this test makes
    that observable without querying the dropped table, through a spy on the
    pipeline's `log_query` that must never be called.

    Fails closed. `README.md` says a failed duplicate check "lets the query
    through"; the code and the existing test say 500, and PRD-009 (Appendix,
    *Observed discrepancy*) keeps the tested behaviour and corrects the README.
    """
    logged = []
    real_log_query = query_pipeline.log_query

    def _spy_log_query(**kwargs):
        logged.append(kwargs)
        return real_log_query(**kwargs)

    monkeypatch.setattr(query_pipeline, "log_query", _spy_log_query)
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
    with get_connection() as conn:
        conn.execute("DROP TABLE audit_logs")

    response = client.post("/query", json={"prompt": "outcome six: storage is gone"})

    assert response.status_code == 500
    assert "Duplicate lookup failed" in response.json()["detail"]
    assert logged == []


# --- PRD-010 STORY-003: characterization of the /query upstream call ---
#
# Pinned before PRD-010 STORY-004. Assertions change only where a later
# story cites the decision. This is the pipeline-level counterpart to
# tests/test_openrouter_client.py's characterization tests: it is what
# STORY-004 must keep green when it changes call_openrouter's signature.


def test_characterization_query_upstream_receives_prompt_model_and_no_api_key(
    temp_db, monkeypatch
):
    received = {}

    # PRD-010 STORY-004: upstream now receives list[Message]
    def _recording_success(messages, model="gpt-4", api_key=None):
        received["messages"] = messages
        received["model"] = model
        received["api_key"] = api_key
        return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)

    monkeypatch.setattr("app.routers.query.call_openrouter", _recording_success)

    prompt = "characterization: pin today's upstream body before STORY-004"
    response = client.post("/query", json={"prompt": prompt})

    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"
    assert received == {
        "messages": [Message("user", prompt)],
        "model": "gpt-4",
        "api_key": None,
    }
