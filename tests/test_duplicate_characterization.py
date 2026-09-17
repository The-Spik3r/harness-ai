"""PRD-009 STORY-001: today's duplicate lookup, pinned before anything changes it.

**Every test in this module pins pre-PRD-009 behaviour. None of it is a
requirement.** `find_duplicate_timestamp` (`app/db/database.py`) runs
`WHERE prompt_hash = ? AND timestamp >= ?` over every `audit_logs` row -- no
`user_id`, no `success`, no flag predicates -- and each test below observes one
consequence of that through `POST /query`, which is where a user meets it.

These are the defects PRD-009 exists to fix (Section 1, Section 6.3). They are
pinned first so that each fix lands as a deliberate, cited edit to an assertion
that already existed, rather than as a new test that silently started passing
(PRD-009 Section 2, "Pin before you change"; Risk 5). Who flips what:

- failure rows (`OpenRouterError`, input `PiiRedactorError`), policy-denial rows
  (D1) and duplicate-blocked rows (D3) -> **STORY-004** (flipped; assertions
  now pin PRD-009 behaviour, each cited in place)
- another user's row (T1/T2) -> **STORY-005** (flipped; assertions now pin
  PRD-009 behaviour, each cited in place)

A story that flips one of these must rewrite the assertion in place with a
comment citing PRD-009 and its decision -- not delete the test. Every test in
the module has now been flipped; each docstring still records the pre-PRD pin
it started as. The six
`/query` outcomes that must *not* change live separately, in
`tests/test_query_outcomes_regression.py`.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db.database import (
    get_audit_log,
    get_connection,
    insert_audit_log,
    insert_user,
)
from app.db.models import AuditLog, User
from app.main import app
import app.services.query_pipeline as query_pipeline
from app.services.duplicate_checker import dedup_key, hash_prompt
from app.services.identity import hash_token
from app.services.openrouter_client import OpenRouterError, OpenRouterResult
from app.services.pii_redactor import PiiRedactorError

_JUAN_ID = "juan@empresa.com"
_MARIA_ID = "maria@empresa.com"
_JUAN_TOKEN = "juan-token"
_MARIA_TOKEN = "maria-token"
_JUAN_HEADERS = {"Authorization": f"Bearer {_JUAN_TOKEN}"}
_MARIA_HEADERS = {"Authorization": f"Bearer {_MARIA_TOKEN}"}

client = TestClient(app)

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(frozen=True)
class _Turn:
    role: str
    content: str


def _key(user_id: str, prompt: str) -> str:
    """The single-turn key run_query derives for this caller and raw prompt."""
    return dedup_key(user_id, [_Turn("user", prompt)])
_DUPLICATE_REASON = "Duplicate query within 24 hours"
_DISALLOWED_MODEL = "not-a-real-model"


@pytest.fixture
def temp_db(temp_db):
    """conftest's initialized database, plus this suite's two authenticated users."""
    insert_user(User(user_id=_JUAN_ID, role="user", token_hash=hash_token(_JUAN_TOKEN)))
    insert_user(User(user_id=_MARIA_ID, role="user", token_hash=hash_token(_MARIA_TOKEN)))
    return temp_db


def _count_audit_rows() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]


def _latest_entry() -> AuditLog:
    # By id, not timestamp: timestamps have one-second resolution, so two rows
    # written by one test routinely share one.
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
    return get_audit_log(row["id"])


def _timestamp(hours_ago: float) -> str:
    dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return dt.strftime(_TIMESTAMP_FORMAT)


def _fail_if_called(*args, **kwargs):
    raise AssertionError("call_openrouter should not have been called")


def _fake_success(prompt, model="gpt-4", api_key=None):
    return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)


def _counting_success(calls: list):
    def _call(prompt, model="gpt-4", api_key=None):
        calls.append(prompt)
        return _fake_success(prompt, model=model, api_key=api_key)

    return _call


def _raise_openrouter_error(prompt, model="gpt-4", api_key=None):
    raise OpenRouterError("boom")


def _boom(text):
    raise PiiRedactorError("PII analysis failed: analyzer exploded")


def test_pre_prd009_openrouter_failure_row_blocks_same_prompt_retry(temp_db, monkeypatch):
    """Pins pre-PRD-009 behaviour (defect #1, PRD-009 Section 1): the
    `success=0` row an upstream failure leaves behind blocks the user's retry
    of the same prompt, which never got an answer.

    Flipped in **STORY-004** (PRD-009 Section 6.3, F4): a `success=0` row is no
    longer a prior query, so the retry reaches the model.
    """
    prompt = "draft the Q3 vendor summary"

    monkeypatch.setattr("app.routers.query.call_openrouter", _raise_openrouter_error)
    failed = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert failed.status_code == 502
    failed_entry = _latest_entry()
    assert failed_entry.success is False
    assert failed_entry.error_message == "boom"

    calls = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _counting_success(calls))
    retry = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert retry.status_code == 200
    # PRD-009 STORY-004 (Section 6.3, F4): failed rows no longer count -- was
    # BLOCKED with first_query_at = failed_entry.timestamp.
    assert retry.json()["status"] == "SUCCESS"
    assert len(calls) == 1
    assert _latest_entry().was_duplicate_blocked is False
    assert _latest_entry().success is True
    assert _count_audit_rows() == 2


def test_pre_prd009_input_redactor_failure_row_blocks_same_prompt_retry(temp_db, monkeypatch):
    """Pins pre-PRD-009 behaviour (defect #1, PRD-009 Section 1): the
    `success=0` row an input `PiiRedactorError` leaves behind blocks the retry.

    Flipped in **STORY-004** (PRD-009 Section 6.3, F4): a `success=0` row is no
    longer a prior query, so the retry reaches the model.

    The real redactor is restored before the retry, and the retry reaching the
    model proves it: a second redactor failure would never call it.
    """
    prompt = "summarise the onboarding checklist"
    real_redact = query_pipeline.redact

    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
    monkeypatch.setattr(query_pipeline, "redact", _boom)
    failed = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert failed.status_code == 500
    failed_entry = _latest_entry()
    assert failed_entry.success is False

    monkeypatch.setattr(query_pipeline, "redact", real_redact)
    calls = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _counting_success(calls))
    retry = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert retry.status_code == 200
    # PRD-009 STORY-004 (Section 6.3, F4): failed rows no longer count -- was
    # BLOCKED with first_query_at = failed_entry.timestamp.
    assert retry.json()["status"] == "SUCCESS"
    assert len(calls) == 1
    assert _latest_entry().was_duplicate_blocked is False
    assert _count_audit_rows() == 2


def test_pre_prd009_policy_denial_row_blocks_same_user_resend_with_allowed_model(
    temp_db, monkeypatch
):
    """Pins pre-PRD-009 behaviour (D1, PRD-009 Section 6.3): a policy denial --
    `denied_permission` set, logged `success=1` by `_deny` -- carries the
    prompt's hash, so the same user resending with an *allowed* model is held
    as a duplicate of the refusal.

    Flipped in **STORY-004** (D1: a policy denial is not a prior query): the
    resend reaches the model.
    """
    prompt = "compare the two supplier contracts"
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    denied = client.post(
        "/query",
        headers=_JUAN_HEADERS,
        json={"prompt": prompt, "model": _DISALLOWED_MODEL},
    )

    assert denied.status_code == 200
    assert denied.json()["status"] == "BLOCKED"
    assert denied.json()["required_permission"] == f"query:model:{_DISALLOWED_MODEL}"
    denial_entry = _latest_entry()
    assert denial_entry.denied_permission == f"query:model:{_DISALLOWED_MODEL}"
    # success=1 on a denial is why the lookup needs `denied_permission IS NULL`.
    assert denial_entry.success is True

    calls = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _counting_success(calls))
    resend = client.post(
        "/query", headers=_JUAN_HEADERS, json={"prompt": prompt, "model": "gpt-4"}
    )

    assert resend.status_code == 200
    # PRD-009 STORY-004 (D1): a policy denial is not a prior query -- was
    # BLOCKED with first_query_at = denial_entry.timestamp.
    assert resend.json()["status"] == "SUCCESS"
    assert len(calls) == 1
    assert _count_audit_rows() == 2


def test_pre_prd009_row_from_one_user_blocks_same_prompt_from_another_user(
    temp_db, monkeypatch
):
    """Pins pre-PRD-009 behaviour (defect #2, PRD-009 Section 1; threat T2): the
    lookup has no `user_id` predicate, so Juan's answered prompt blocks María's
    identical one -- a prompt she never saw.

    Flipped in **STORY-005** (PRD-009 T1/T2, F5): the lookup is scoped by the
    authenticated `user_id`, so María's send reaches the model, and only her own
    resend is blocked, against her own row. The name is kept because it
    describes the pre-PRD pin this test was written against.
    """
    prompt = "summarise this week's incidents"
    calls = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _counting_success(calls))

    juan = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert juan.status_code == 200
    assert juan.json()["status"] == "SUCCESS"
    juan_at = get_audit_log(juan.json()["audit_id"]).timestamp

    maria = client.post("/query", headers=_MARIA_HEADERS, json={"prompt": prompt})

    assert maria.status_code == 200
    # PRD-009 STORY-005 (T1/T2): another user's row is no longer a prior query --
    # was BLOCKED with first_query_at = juan_at.
    assert maria.json()["status"] == "SUCCESS"
    assert len(calls) == 2
    maria_entry = _latest_entry()
    assert maria_entry.user_id == _MARIA_ID
    assert maria_entry.was_duplicate_blocked is False
    maria_at = maria_entry.timestamp

    resend = client.post("/query", headers=_MARIA_HEADERS, json={"prompt": prompt})

    # Her own success is the prior. Timestamps have one-second resolution, so
    # maria_at may equal juan_at here; the "not the other user's timestamp"
    # proof lives in tests/test_duplicate_checker.py, with seeded rows.
    assert resend.status_code == 200
    assert resend.json() == {
        "status": "BLOCKED",
        "reason": _DUPLICATE_REASON,
        "first_query_at": maria_at,
    }
    assert len(calls) == 2
    resend_entry = _latest_entry()
    assert resend_entry.user_id == _MARIA_ID
    assert resend_entry.was_duplicate_blocked is True


def test_pre_prd009_duplicate_blocked_row_keeps_window_alive_after_original_ages_out(
    temp_db, monkeypatch
):
    """Pins pre-PRD-009 behaviour (D3, PRD-009 Section 6.4): a duplicate-blocked
    row carries the same `prompt_hash`, so once the original ages out of the
    24h window the *blocked* row becomes the earliest match and the window
    chains:

        t=-25h  A  success             (outside the window)
        t=-2h   B  duplicate-blocked   (inside the window)
        t=now   same prompt -> reaches the model (was: BLOCKED, first_query_at = B)

    Flipped in **STORY-004** (D3, PRD-009 Section 6.4): a duplicate-blocked row
    does not extend the window. The name is kept because it describes the
    pre-PRD pin this test was written against; the assertions now pin D3.

    Seeded rather than sent: the ages are the point, and only a backdated row
    can have them. Both rows carry the key /query derives (PRD-009 STORY-007),
    so the blocked row is matchable on everything but its flag: SUCCESS proves
    D3, not merely that a NULL-keyed row never matches (D6).
    """
    prompt = "list the open procurement tickets"
    a_timestamp = _timestamp(hours_ago=25)
    b_timestamp = _timestamp(hours_ago=2)
    insert_audit_log(
        AuditLog(
            timestamp=a_timestamp,
            user_id=_JUAN_ID,
            prompt_hash=hash_prompt(prompt),
            dedup_key=_key(_JUAN_ID, prompt),
            success=True,
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp=b_timestamp,
            user_id=_JUAN_ID,
            prompt_hash=hash_prompt(prompt),
            dedup_key=_key(_JUAN_ID, prompt),
            was_duplicate_blocked=True,
            success=True,
        )
    )
    calls = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _counting_success(calls))

    response = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert response.status_code == 200
    # PRD-009 STORY-004 (D3): a duplicate-blocked row no longer extends the
    # window -- was BLOCKED with first_query_at = b_timestamp.
    assert response.json()["status"] == "SUCCESS"
    assert len(calls) == 1
