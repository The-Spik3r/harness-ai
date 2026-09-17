"""PRD-009 STORY-008: what counts as a prior query, proven through `POST /query`.

One test per row of PRD-009 Section 6.3's table, each driven with real bearer
tokens through `require_permission`, the router and `run_query`, and each
asserting both the HTTP outcome and the audit rows the request left behind.

**This overlaps with `tests/test_duplicate_checker.py` on purpose.** That module
proves the SQL; this one proves the wiring. A lookup can be exactly right and
the control still broken if the router passes the body's `user_id`, or an arm
forgets `dedup_key=`, and neither mistake is visible below `/query`.

Section 6.3 row -> test:

| Row written by                   | Counts? | Test                                                                   |
|----------------------------------|---------|------------------------------------------------------------------------|
| Success                          | Yes     | test_story_3_juan_repeat_at_1400_is_blocked_with_first_query_at_his_0900_success |
| Suspicious-pattern block         | Yes     | test_resend_after_suspicious_pattern_block_is_blocked_as_a_duplicate_d1 |
| Duplicate block                  | No (D3) | test_story_4_row_blocked_at_23h_no_longer_keeps_prompt_blocked_at_25h_d3 |
| Policy denial (`_deny`, 3 arms)  | No (D1) | test_story_4_juan_denied_a_disallowed_model_then_resends_with_an_allowed_one_and_reaches_the_model_d1, test_retry_after_byok_denial_reaches_the_model_d1, test_missing_query_submit_is_refused_at_the_router_and_leaves_no_prior_query_d1 |
| Input `PiiRedactorError`         | No      | test_retry_after_input_redactor_failure_reaches_the_model              |
| `OpenRouterError`                | No      | test_story_1_juan_retries_draft_the_q3_vendor_summary_after_a_502_and_reaches_the_model |
| Output `PiiRedactorError`        | No      | test_retry_after_output_redactor_failure_reaches_the_model_again_risk_4 |
| Router foreign-session refusal   | No      | test_retry_after_foreign_session_refusal_reaches_the_model             |
| Any row by another `user_id`     | No      | test_story_2_maria_at_0900_and_juan_at_0905_both_reach_the_model_with_different_keys |
| Pre-PRD row (`dedup_key` NULL)   | No (D6) | test_pre_prd009_row_with_null_dedup_key_does_not_block_the_same_prompt_risk_3 |

The Section 11 items with no other end-to-end home -- the 24h boundary,
whitespace, a key on every `log_query` call site, `prompt_hash` unchanged --
close the module.

Rows are real `/query` rows wherever possible. Two exceptions, each for a reason
the test states: a *seeded* row where no request can produce it (a 25h-old row,
a pre-PRD NULL key, a `query:submit` denial the router refuses first), and an
*aged* row (`_backdate`) where two live rows would otherwise share a
one-second timestamp and make a `first_query_at` assertion vacuous.
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
from app.services import chat_sessions
from app.services.duplicate_checker import dedup_key, hash_prompt
from app.services.identity import Identity, hash_token
from app.services.openrouter_client import OpenRouterError, OpenRouterResult
from app.services.pattern_detector import SUSPICIOUS_PATTERNS
from app.services.pii_redactor import PiiRedactorError

_JUAN_ID = "juan@empresa.com"
_MARIA_ID = "maria@empresa.com"
_JUAN_TOKEN = "juan-token"
_MARIA_TOKEN = "maria-token"
_JUAN_HEADERS = {"Authorization": f"Bearer {_JUAN_TOKEN}"}
_MARIA_HEADERS = {"Authorization": f"Bearer {_MARIA_TOKEN}"}

_DUPLICATE_REASON = "Duplicate query within 24 hours"
_PATTERN_REASON = "Suspicious pattern detected"
_DISALLOWED_MODEL = "not-a-real-model"
_PATTERN = SUSPICIOUS_PATTERNS[0]
_FOREIGN_SESSION_DETAIL = "session_id does not belong to the authenticated identity"

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

client = TestClient(app)


@pytest.fixture
def temp_db(temp_db):
    """conftest's initialized database, plus this suite's two authenticated users."""
    insert_user(User(user_id=_JUAN_ID, role="user", token_hash=hash_token(_JUAN_TOKEN)))
    insert_user(User(user_id=_MARIA_ID, role="user", token_hash=hash_token(_MARIA_TOKEN)))
    return temp_db


@dataclass(frozen=True)
class _Turn:
    role: str
    content: str


def _key(user_id: str, prompt: str) -> str:
    """The single-turn key run_query derives for this caller and raw prompt."""
    return dedup_key(user_id, [_Turn("user", prompt)])


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


def _backdate(audit_id: int, hours_ago: float) -> str:
    """Age a row a real `/query` request wrote; returns its new timestamp.

    Timestamps have one-second resolution and `log_query` always stamps *now*,
    so two live rows in one test usually share a timestamp, and
    `first_query_at == success_at` could not tell the success from the row
    blocked after it. Only the age is synthetic: the key, the hash and every
    flag stay exactly as the pipeline wrote them.
    """
    timestamp = _timestamp(hours_ago)
    with get_connection() as conn:
        conn.execute("UPDATE audit_logs SET timestamp = ? WHERE id = ?", (timestamp, audit_id))
    assert get_audit_log(audit_id).timestamp == timestamp
    return timestamp


def _assert_row_keyed(entry: AuditLog, user_id: str, prompt: str) -> None:
    """The row carries the credential's key and the raw prompt's hash (Section 6.2, D5)."""
    assert entry.user_id == user_id
    assert entry.dedup_key is not None
    assert entry.dedup_key == _key(user_id, prompt)
    assert entry.prompt_hash == hash_prompt(prompt)


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


def _boom_on_second_call():
    """Raise on the response, not on the prompt -- reaches the output arm."""
    real_redact = query_pipeline.redact
    calls = []

    def _redact(text):
        calls.append(text)
        if len(calls) == 1:
            return real_redact(text)
        raise PiiRedactorError("PII analysis failed: analyzer exploded on output")

    return _redact


def _session_owned_by(user_id: str) -> str:
    """One session belonging to `user_id`, created through the service."""
    identity = Identity(user_id=user_id, role="user")
    session_id = chat_sessions.create(identity, "the quarterly close", lambda text: text)
    assert session_id is not None
    return session_id


# --------------------------------------------------------------------------
# Rows that count as a prior query
# --------------------------------------------------------------------------


def test_story_3_juan_repeat_at_1400_is_blocked_with_first_query_at_his_0900_success(
    temp_db, monkeypatch
):
    """PRD-009 Section 5, story 3; Section 6.3 row "Success" (counts); D3.

    Juan's 09:00 prompt succeeds, and his identical 14:00 prompt is blocked with
    `first_query_at` at 09:00, exactly as before PRD-009. A third send is still
    held against the *success*, not against the blocked row between them.

    The success is aged five hours after it is written, so the success and the
    blocked row have different timestamps and the third send's `first_query_at`
    can only equal one of them.
    """
    prompt = "summarise the 09:00 standup notes"
    calls = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _counting_success(calls))

    first = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert first.status_code == 200
    assert first.json()["status"] == "SUCCESS"
    success_id = first.json()["audit_id"]
    success = get_audit_log(success_id)
    assert success.success is True
    _assert_row_keyed(success, _JUAN_ID, prompt)
    success_at = _backdate(success_id, hours_ago=5)

    repeat = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert repeat.status_code == 200
    assert repeat.json() == {
        "status": "BLOCKED",
        "reason": _DUPLICATE_REASON,
        "first_query_at": success_at,
    }
    assert len(calls) == 1
    blocked = _latest_entry()
    assert blocked.was_duplicate_blocked is True
    assert blocked.success is True
    assert blocked.dedup_key == success.dedup_key
    _assert_row_keyed(blocked, _JUAN_ID, prompt)

    third = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    # Section 6.3 row "Duplicate block" (D3): the earliest *qualifying* row is
    # the success, not the blocked row between them.
    assert third.status_code == 200
    assert third.json() == {
        "status": "BLOCKED",
        "reason": _DUPLICATE_REASON,
        "first_query_at": success_at,
    }
    assert success_at != blocked.timestamp
    assert len(calls) == 1
    assert _latest_entry().was_duplicate_blocked is True
    assert _count_audit_rows() == 3


def test_resend_after_suspicious_pattern_block_is_blocked_as_a_duplicate_d1(
    temp_db, monkeypatch
):
    """Section 6.3 row "Suspicious-pattern block" (counts, D1).

    A content check is a real verdict, so the pattern-blocked row is a prior
    query. The resend gets the *duplicate* body, not the pattern body: the
    duplicate check runs before pattern detection (Section 6.1).
    """
    prompt = f"please {_PATTERN} and list the payroll"
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    first = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert first.status_code == 200
    assert first.json() == {
        "status": "BLOCKED",
        "reason": _PATTERN_REASON,
        "pattern": _PATTERN,
    }
    pattern_row = _latest_entry()
    assert pattern_row.suspicious_pattern == _PATTERN
    assert pattern_row.success is True
    assert pattern_row.was_duplicate_blocked is False
    _assert_row_keyed(pattern_row, _JUAN_ID, prompt)
    pattern_at = _backdate(pattern_row.id, hours_ago=1)

    resend = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert resend.status_code == 200
    assert resend.json() == {
        "status": "BLOCKED",
        "reason": _DUPLICATE_REASON,
        "first_query_at": pattern_at,
    }
    blocked = _latest_entry()
    assert blocked.was_duplicate_blocked is True
    assert blocked.suspicious_pattern is None
    assert blocked.dedup_key == pattern_row.dedup_key
    assert _count_audit_rows() == 2


# --------------------------------------------------------------------------
# Rows that do not count as a prior query
# --------------------------------------------------------------------------


def test_story_4_row_blocked_at_23h_no_longer_keeps_prompt_blocked_at_25h_d3(
    temp_db, monkeypatch
):
    """PRD-009 Section 5, story 4 (second example); Section 6.3 row "Duplicate
    block" (does not count, D3); Section 6.4; T5.

        t=0h   A  success               (now 25h ago: outside the window)
        t=23h  B  duplicate-blocked     (now 2h ago: inside the window)
        t=25h  same prompt -> reaches the model (before PRD-009: BLOCKED at B)

    Seeded, because the ages are the point and no request can write a 25h-old
    row. Both rows carry the key `/query` derives, so B is matchable on
    everything except its flag, and SUCCESS proves D3, not D6.
    """
    prompt = "list the open procurement tickets"
    insert_audit_log(
        AuditLog(
            timestamp=_timestamp(hours_ago=25),
            user_id=_JUAN_ID,
            prompt_hash=hash_prompt(prompt),
            dedup_key=_key(_JUAN_ID, prompt),
            success=True,
        )
    )
    b_id = insert_audit_log(
        AuditLog(
            timestamp=_timestamp(hours_ago=2),
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

    # Section 6.3 row "Duplicate block" (D3): B does not extend the window.
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"
    assert len(calls) == 1
    entry = get_audit_log(response.json()["audit_id"])
    assert entry.success is True
    assert entry.was_duplicate_blocked is False
    _assert_row_keyed(entry, _JUAN_ID, prompt)
    assert entry.dedup_key == get_audit_log(b_id).dedup_key
    assert _count_audit_rows() == 3


def test_story_4_juan_denied_a_disallowed_model_then_resends_with_an_allowed_one_and_reaches_the_model_d1(
    temp_db, monkeypatch
):
    """PRD-009 Section 5, story 4 (first example); Section 6.3 row "Policy
    denial" (does not count, D1), `authorize_model` arm.

    The denial row carries the same key as the resend, so the resend getting
    through is the `denied_permission IS NULL` predicate at work, not a key
    mismatch.
    """
    prompt = "compare the two supplier contracts"
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    denied = client.post(
        "/query", headers=_JUAN_HEADERS, json={"prompt": prompt, "model": _DISALLOWED_MODEL}
    )

    assert denied.status_code == 200
    assert denied.json() == {
        "status": "BLOCKED",
        "reason": "Model not permitted for this role",
        "required_permission": f"query:model:{_DISALLOWED_MODEL}",
    }
    denial = _latest_entry()
    assert denial.denied_permission == f"query:model:{_DISALLOWED_MODEL}"
    assert denial.success is True
    _assert_row_keyed(denial, _JUAN_ID, prompt)

    calls = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _counting_success(calls))
    resend = client.post(
        "/query", headers=_JUAN_HEADERS, json={"prompt": prompt, "model": "gpt-4"}
    )

    assert resend.status_code == 200
    assert resend.json()["status"] == "SUCCESS"
    assert len(calls) == 1
    entry = get_audit_log(resend.json()["audit_id"])
    assert entry.denied_permission is None
    assert entry.dedup_key == denial.dedup_key
    assert _count_audit_rows() == 2


def test_retry_after_byok_denial_reaches_the_model_d1(temp_db, monkeypatch):
    """Section 6.3 row "Policy denial" (does not count, D1), BYOK arm: role
    `user` has no `query:byok`, so a caller-supplied key is refused."""
    prompt = "draft the renewal reminder"
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    denied = client.post(
        "/query",
        headers=_JUAN_HEADERS,
        json={"prompt": prompt, "openrouter_api_key": "sk-caller-supplied"},
    )

    assert denied.status_code == 200
    assert denied.json() == {
        "status": "BLOCKED",
        "reason": "Missing required permission",
        "required_permission": "query:byok",
    }
    denial = _latest_entry()
    assert denial.denied_permission == "query:byok"
    assert denial.success is True
    _assert_row_keyed(denial, _JUAN_ID, prompt)

    calls = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _counting_success(calls))
    resend = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert resend.status_code == 200
    assert resend.json()["status"] == "SUCCESS"
    assert len(calls) == 1
    assert get_audit_log(resend.json()["audit_id"]).dedup_key == denial.dedup_key
    assert _count_audit_rows() == 2


def test_missing_query_submit_is_refused_at_the_router_and_leaves_no_prior_query_d1(
    temp_db, monkeypatch
):
    """Section 6.3 row "Policy denial" (does not count, D1), `query:submit` arm.

    Over HTTP this arm never writes a row: `require_permission` refuses a caller
    without `query:submit` with a 403 before `run_query` runs, so there is
    nothing that could count. That is asserted first.

    `_deny`'s `query:submit` row is still a row the lookup can meet: it is
    written whenever `run_query` is called directly. No `/query` request can
    produce it, so it is **seeded**, with Juan's real key and hash, to prove the
    exclusion through the HTTP lookup. This is the one seed the story's
    exception list did not name (recorded in the STORY-008 report).
    """
    prompt = "export the quarterly audit trail"
    calls = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _counting_success(calls))
    insert_user(
        User(
            user_id="reviewer@empresa.com",
            role="auditor",
            token_hash=hash_token("auditor-token"),
        )
    )

    refused = client.post(
        "/query",
        headers={"Authorization": "Bearer auditor-token"},
        json={"prompt": prompt},
    )

    assert refused.status_code == 403
    assert _count_audit_rows() == 0
    assert calls == []

    insert_audit_log(
        AuditLog(
            timestamp=_timestamp(hours_ago=1),
            user_id=_JUAN_ID,
            prompt_hash=hash_prompt(prompt),
            dedup_key=_key(_JUAN_ID, prompt),
            role="user",
            denied_permission="query:submit",
            success=True,
        )
    )

    response = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"
    assert len(calls) == 1
    _assert_row_keyed(get_audit_log(response.json()["audit_id"]), _JUAN_ID, prompt)
    assert _count_audit_rows() == 2


def test_story_1_juan_retries_draft_the_q3_vendor_summary_after_a_502_and_reaches_the_model(
    temp_db, monkeypatch
):
    """PRD-009 Section 5, story 1; Section 6.3 row "`OpenRouterError`" (does not
    count, F4): the upstream timeout leaves a `success=0` row, and Juan's retry
    ten seconds later reaches the model instead of being held against it."""
    prompt = "draft the Q3 vendor summary"
    monkeypatch.setattr("app.routers.query.call_openrouter", _raise_openrouter_error)

    failed = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert failed.status_code == 502
    assert failed.json() == {"detail": "boom"}
    failure = _latest_entry()
    assert failure.success is False
    assert failure.error_message == "boom"
    _assert_row_keyed(failure, _JUAN_ID, prompt)

    calls = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _counting_success(calls))
    retry = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert retry.status_code == 200
    assert retry.json()["status"] == "SUCCESS"
    assert len(calls) == 1
    entry = get_audit_log(retry.json()["audit_id"])
    assert entry.was_duplicate_blocked is False
    assert entry.dedup_key == failure.dedup_key
    assert _count_audit_rows() == 2


def test_retry_after_input_redactor_failure_reaches_the_model(temp_db, monkeypatch):
    """Section 6.3 row "Input `PiiRedactorError`" (does not count, F4).

    The real redactor is restored before the retry, and the retry reaching the
    model proves it: a second redactor failure would never call it.
    """
    prompt = "summarise the onboarding checklist"
    real_redact = query_pipeline.redact
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
    monkeypatch.setattr(query_pipeline, "redact", _boom)

    failed = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert failed.status_code == 500
    assert failed.json() == {"detail": "PII analysis failed: analyzer exploded"}
    failure = _latest_entry()
    assert failure.success is False
    _assert_row_keyed(failure, _JUAN_ID, prompt)

    monkeypatch.setattr(query_pipeline, "redact", real_redact)
    calls = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _counting_success(calls))
    retry = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert retry.status_code == 200
    assert retry.json()["status"] == "SUCCESS"
    assert len(calls) == 1
    assert get_audit_log(retry.json()["audit_id"]).dedup_key == failure.dedup_key
    assert _count_audit_rows() == 2


def test_retry_after_output_redactor_failure_reaches_the_model_again_risk_4(
    temp_db, monkeypatch
):
    """Section 6.3 row "Output `PiiRedactorError`" (does not count); T6, Risk 4.

    The model *was* called, but the answer was withheld, so the retry calls it
    a second time. That second call is the accepted cost.
    """
    prompt = "rewrite the supplier onboarding email"
    real_redact = query_pipeline.redact
    calls = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _counting_success(calls))
    monkeypatch.setattr(query_pipeline, "redact", _boom_on_second_call())

    failed = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert failed.status_code == 500
    assert failed.json() == {"detail": "PII analysis failed: analyzer exploded on output"}
    assert len(calls) == 1
    failure = _latest_entry()
    assert failure.success is False
    _assert_row_keyed(failure, _JUAN_ID, prompt)

    monkeypatch.setattr(query_pipeline, "redact", real_redact)
    retry = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert retry.status_code == 200
    assert retry.json()["status"] == "SUCCESS"
    assert len(calls) == 2
    assert get_audit_log(retry.json()["audit_id"]).dedup_key == failure.dedup_key
    assert _count_audit_rows() == 2


def test_retry_after_foreign_session_refusal_reaches_the_model(temp_db, monkeypatch):
    """Section 6.3 row "Router foreign-session refusal" (does not count).

    The router refuses before `run_query` and writes `success=False` with
    `dedup_key=None` (PRD-009 STORY-006). The prompt's hash is still recorded
    as evidence; the resend without the foreign session reaches the model.
    """
    prompt = "close out the quarterly accruals"
    calls = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _counting_success(calls))
    foreign = _session_owned_by(_MARIA_ID)
    before = _count_audit_rows()

    refused = client.post(
        "/query", headers=_JUAN_HEADERS, json={"prompt": prompt, "session_id": foreign}
    )

    assert refused.status_code == 403
    assert refused.json() == {"detail": _FOREIGN_SESSION_DETAIL}
    assert calls == []
    assert _count_audit_rows() == before + 1
    refusal = _latest_entry()
    assert refusal.success is False
    assert refusal.dedup_key is None
    assert refusal.user_id == _JUAN_ID
    assert refusal.prompt_hash == hash_prompt(prompt)

    resend = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert resend.status_code == 200
    assert resend.json()["status"] == "SUCCESS"
    assert len(calls) == 1
    _assert_row_keyed(get_audit_log(resend.json()["audit_id"]), _JUAN_ID, prompt)
    assert _count_audit_rows() == before + 2


def test_story_2_maria_at_0900_and_juan_at_0905_both_reach_the_model_with_different_keys(
    temp_db, monkeypatch
):
    """PRD-009 Section 5, story 2; Section 6.3 row "Any row by another
    `user_id`" (does not count); T1/T2; D5.

    María's row is aged to 09:00 against Juan's 09:05-ish, so when Juan's own
    resend is blocked, its `first_query_at` can be told apart from hers: he is
    held against his own answer, never against hers (no window poisoning).
    """
    prompt = "summarise this week's incidents"
    calls = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _counting_success(calls))

    maria = client.post("/query", headers=_MARIA_HEADERS, json={"prompt": prompt})

    assert maria.status_code == 200
    assert maria.json()["status"] == "SUCCESS"
    maria_id = maria.json()["audit_id"]
    maria_at = _backdate(maria_id, hours_ago=5 + 5 / 60)

    juan = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert juan.status_code == 200
    assert juan.json()["status"] == "SUCCESS"
    assert len(calls) == 2
    maria_row = get_audit_log(maria_id)
    juan_row = get_audit_log(juan.json()["audit_id"])
    _assert_row_keyed(maria_row, _MARIA_ID, prompt)
    _assert_row_keyed(juan_row, _JUAN_ID, prompt)
    assert maria_row.dedup_key != juan_row.dedup_key
    # D5: the evidence column is unchanged, so both rows still share it.
    assert maria_row.prompt_hash == juan_row.prompt_hash == hash_prompt(prompt)

    resend = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert resend.status_code == 200
    assert resend.json() == {
        "status": "BLOCKED",
        "reason": _DUPLICATE_REASON,
        "first_query_at": juan_row.timestamp,
    }
    assert juan_row.timestamp != maria_at
    assert len(calls) == 2
    assert _latest_entry().user_id == _JUAN_ID
    assert _count_audit_rows() == 3


def test_pre_prd009_row_with_null_dedup_key_does_not_block_the_same_prompt_risk_3(
    temp_db, monkeypatch
):
    """Section 6.3 row "Pre-PRD row (`dedup_key` NULL)" (does not count); D6,
    T8, Risk 3.

    Seeded, because no request can write a NULL key through `run_query` any
    more. The seeded row is otherwise the exact row a pre-PRD success left:
    same user, same `prompt_hash`, inside the window.
    """
    prompt = "reconcile the August card statements"
    would_be = _key(_JUAN_ID, prompt)
    seed_id = insert_audit_log(
        AuditLog(
            timestamp=_timestamp(hours_ago=2),
            user_id=_JUAN_ID,
            prompt_hash=hash_prompt(prompt),
            success=True,
        )
    )
    seeded = get_audit_log(seed_id)
    assert seeded.dedup_key is None
    assert would_be is not None
    calls = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _counting_success(calls))

    response = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    # D6: NULL = ? is never true, so the pre-PRD row cannot hold the send.
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"
    assert len(calls) == 1
    entry = get_audit_log(response.json()["audit_id"])
    assert entry.dedup_key == would_be
    assert entry.prompt_hash == seeded.prompt_hash
    assert _count_audit_rows() == 2


# --------------------------------------------------------------------------
# PRD-009 Section 11 items with no other end-to-end home
# --------------------------------------------------------------------------


def test_success_at_23h59m_still_blocks_the_same_prompt(temp_db, monkeypatch):
    """Section 11: boundary behaviour unchanged, one minute inside the window."""
    prompt = "list this month's expense exceptions"
    calls = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _counting_success(calls))

    first = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})
    assert first.json()["status"] == "SUCCESS"
    success_at = _backdate(first.json()["audit_id"], hours_ago=23 + 59 / 60)

    repeat = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert repeat.status_code == 200
    assert repeat.json() == {
        "status": "BLOCKED",
        "reason": _DUPLICATE_REASON,
        "first_query_at": success_at,
    }
    assert len(calls) == 1
    assert _latest_entry().was_duplicate_blocked is True


def test_success_at_24h01m_no_longer_blocks_the_same_prompt(temp_db, monkeypatch):
    """Section 11: boundary behaviour unchanged, one minute outside the window."""
    prompt = "list this month's expense exceptions"
    calls = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _counting_success(calls))

    first = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})
    assert first.json()["status"] == "SUCCESS"
    _backdate(first.json()["audit_id"], hours_ago=24 + 1 / 60)

    repeat = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})

    assert repeat.status_code == 200
    assert repeat.json()["status"] == "SUCCESS"
    assert len(calls) == 2
    entry = get_audit_log(repeat.json()["audit_id"])
    assert entry.was_duplicate_blocked is False
    _assert_row_keyed(entry, _JUAN_ID, prompt)


def test_trailing_whitespace_is_a_different_prompt(temp_db, monkeypatch):
    """Section 11: whitespace sensitivity unchanged -- in the key and in the hash."""
    calls = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _counting_success(calls))

    plain = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": "hello world"})
    spaced = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": "hello world "})

    assert plain.json()["status"] == "SUCCESS"
    assert spaced.json()["status"] == "SUCCESS"
    assert len(calls) == 2
    plain_row = get_audit_log(plain.json()["audit_id"])
    spaced_row = get_audit_log(spaced.json()["audit_id"])
    _assert_row_keyed(plain_row, _JUAN_ID, "hello world")
    _assert_row_keyed(spaced_row, _JUAN_ID, "hello world ")
    assert plain_row.dedup_key != spaced_row.dedup_key
    assert plain_row.prompt_hash != spaced_row.prompt_hash


def _patch_success(monkeypatch):
    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_success)


def _patch_no_model_call(monkeypatch):
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)


def _patch_openrouter_failure(monkeypatch):
    monkeypatch.setattr("app.routers.query.call_openrouter", _raise_openrouter_error)


def _patch_input_redactor_failure(monkeypatch):
    _patch_no_model_call(monkeypatch)
    monkeypatch.setattr(query_pipeline, "redact", _boom)


def _patch_output_redactor_failure(monkeypatch):
    _patch_success(monkeypatch)
    monkeypatch.setattr(query_pipeline, "redact", _boom_on_second_call())


# (request body, patch, expected status code, send a same-prompt success first)
# One case per log_query call site in run_query: the three denials share `_deny`,
# and the reachable one over HTTP is the model allowlist.
_CALL_SITES = [
    pytest.param(
        {"prompt": "hello world", "model": _DISALLOWED_MODEL},
        _patch_no_model_call, 200, False, id="deny",
    ),
    pytest.param(
        # The deprecated body user_id, matching the credential: the key still
        # comes from the credential (Section 9.1), and this proves the field
        # does not perturb it.
        {"user_id": _JUAN_ID, "prompt": "hello world"},
        _patch_no_model_call, 200, True, id="duplicate",
    ),
    pytest.param(
        {"prompt": f"please {_PATTERN}"},
        _patch_no_model_call, 200, False, id="pattern",
    ),
    pytest.param(
        {"prompt": "hello world"},
        _patch_input_redactor_failure, 500, False, id="input-redactor",
    ),
    pytest.param(
        {"prompt": "hello world"},
        _patch_openrouter_failure, 502, False, id="openrouter",
    ),
    pytest.param(
        {"prompt": "hello world"},
        _patch_output_redactor_failure, 500, False, id="output-redactor",
    ),
    pytest.param(
        {"prompt": "hello world"},
        _patch_success, 200, False, id="success",
    ),
]


@pytest.mark.parametrize("body, patch, status_code, seed_first", _CALL_SITES)
def test_every_call_site_writes_the_credentials_key_and_the_raw_prompt_hash(
    temp_db, monkeypatch, body, patch, status_code, seed_first
):
    """Section 11: `dedup_key` non-NULL on every row `run_query` writes, and
    `prompt_hash == hash_prompt(prompt)` -- proven through `/query`, where the
    identity is the bearer token's and never the body's (Section 9.1)."""
    prompt = body["prompt"]
    if seed_first:
        _patch_success(monkeypatch)
        seeded = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})
        assert seeded.json()["status"] == "SUCCESS"
    patch(monkeypatch)
    before = _count_audit_rows()

    response = client.post("/query", headers=_JUAN_HEADERS, json=body)

    assert response.status_code == status_code
    assert _count_audit_rows() == before + 1
    row = _latest_entry()
    assert row.dedup_key is not None
    _assert_row_keyed(row, _JUAN_ID, prompt)
    if seed_first:
        assert row.was_duplicate_blocked is True
