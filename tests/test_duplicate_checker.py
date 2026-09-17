import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from app.db.database import get_audit_log, get_connection, insert_audit_log
from app.db.models import AuditLog
from app.models.schemas import (
    QueryBlockedDuplicateResponse,
    QueryBlockedForbiddenResponse,
    QueryBlockedSuspiciousResponse,
    QuerySuccessResponse,
)
from app.services.authz import PERMISSION_QUERY_BYOK, PERMISSION_QUERY_SUBMIT
from app.services.duplicate_checker import (
    DuplicateCheckError,
    check_duplicate,
    dedup_key,
    hash_prompt,
)
from app.services.identity import Identity
from app.services.openrouter_client import OpenRouterResult
from app.services.pii_redactor import PiiRedactorError
from app.services.query_pipeline import run_query
import app.services.query_pipeline as query_pipeline

# PRD-009 Section 6.5 (STORY-007): re-seeded with user_id + dedup_key. The lookup
# matches on the key; prompt_hash is still written, as every real row carries it,
# but is no longer read by the duplicate control (D5).

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_SEEDED_USER = "juan@empresa.com"


@dataclass(frozen=True)
class _Turn:
    role: str
    content: str


def _key(user_id: str, prompt: str) -> str:
    """The single-turn key run_query derives for this caller and raw prompt."""
    return dedup_key(user_id, [_Turn("user", prompt)])


def _timestamp(hours_ago: float) -> str:
    dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return dt.strftime(_TIMESTAMP_FORMAT)


def _seed(prompt: str, hours_ago: float) -> str:
    return _seed_row(prompt, hours_ago)


def _seed_row(prompt: str, hours_ago: float, **fields) -> str:
    timestamp = _timestamp(hours_ago)
    user_id = fields.setdefault("user_id", _SEEDED_USER)
    fields.setdefault("prompt_hash", hash_prompt(prompt))
    fields.setdefault("dedup_key", _key(user_id, prompt))
    insert_audit_log(AuditLog(timestamp=timestamp, **fields))
    return timestamp


def test_no_duplicate_when_no_matching_row(temp_db):
    result = check_duplicate(_SEEDED_USER, _key(_SEEDED_USER, "hello world"))
    assert result.is_duplicate is False
    assert result.first_query_at is None


def test_duplicate_detected_within_24h(temp_db):
    timestamp = _seed("hello world", hours_ago=2)

    result = check_duplicate(_SEEDED_USER, _key(_SEEDED_USER, "hello world"))

    assert result.is_duplicate is True
    assert result.first_query_at == timestamp


def test_not_duplicate_when_older_than_24h(temp_db):
    _seed("hello world", hours_ago=25)

    result = check_duplicate(_SEEDED_USER, _key(_SEEDED_USER, "hello world"))

    assert result.is_duplicate is False


def test_boundary_just_inside_24h(temp_db):
    timestamp = _seed("hello world", hours_ago=23 + 59 / 60)

    result = check_duplicate(_SEEDED_USER, _key(_SEEDED_USER, "hello world"))

    assert result.is_duplicate is True
    assert result.first_query_at == timestamp


def test_boundary_just_outside_24h(temp_db):
    _seed("hello world", hours_ago=24 + 1 / 60)

    result = check_duplicate(_SEEDED_USER, _key(_SEEDED_USER, "hello world"))

    assert result.is_duplicate is False


def test_whitespace_difference_produces_different_hash_and_not_flagged(temp_db):
    assert hash_prompt("hello world") != hash_prompt("hello world ")
    assert _key(_SEEDED_USER, "hello world") != _key(_SEEDED_USER, "hello world ")

    _seed("hello world", hours_ago=2)

    result = check_duplicate(_SEEDED_USER, _key(_SEEDED_USER, "hello world "))

    assert result.is_duplicate is False


def test_earliest_entry_returned_as_first_query_at(temp_db):
    earliest = _seed("hello world", hours_ago=10)
    _seed("hello world", hours_ago=3)

    result = check_duplicate(_SEEDED_USER, _key(_SEEDED_USER, "hello world"))

    assert result.is_duplicate is True
    assert result.first_query_at == earliest


def test_malformed_db_raises_duplicate_check_error(uninitialized_db):
    with pytest.raises(DuplicateCheckError):
        check_duplicate(_SEEDED_USER, _key(_SEEDED_USER, "anything"))


# ---------------------------------------------------------------------------
# PRD-009 STORY-004 (F4): only rows with a real verdict count as a prior query.
# ---------------------------------------------------------------------------


def test_failed_row_is_not_a_prior_query(temp_db):
    _seed_row("hello world", hours_ago=2, success=False)

    result = check_duplicate(_SEEDED_USER, _key(_SEEDED_USER, "hello world"))

    assert result.is_duplicate is False


def test_policy_denied_row_is_not_a_prior_query(temp_db):
    # success defaults to True: a denial is logged success=1 (D1).
    _seed_row("hello world", hours_ago=2, denied_permission="query:submit")

    result = check_duplicate(_SEEDED_USER, _key(_SEEDED_USER, "hello world"))

    assert result.is_duplicate is False


def test_duplicate_blocked_row_is_not_a_prior_query(temp_db):
    _seed_row("hello world", hours_ago=2, was_duplicate_blocked=True)

    result = check_duplicate(_SEEDED_USER, _key(_SEEDED_USER, "hello world"))

    assert result.is_duplicate is False


def test_suspicious_pattern_row_is_a_prior_query(temp_db):
    # D1: a content-check verdict counts.
    timestamp = _seed_row(
        "hello world",
        hours_ago=2,
        suspicious_pattern="ignore previous instructions",
    )

    result = check_duplicate(_SEEDED_USER, _key(_SEEDED_USER, "hello world"))

    assert result.is_duplicate is True
    assert result.first_query_at == timestamp


def test_success_outside_window_and_blocked_row_inside_is_not_a_duplicate(temp_db):
    # D3: the blocked row at -2h no longer chains the -25h success's window.
    _seed_row("hello world", hours_ago=25)
    _seed_row("hello world", hours_ago=2, was_duplicate_blocked=True)

    result = check_duplicate(_SEEDED_USER, _key(_SEEDED_USER, "hello world"))

    assert result.is_duplicate is False


def test_first_query_at_skips_a_later_blocked_row_for_the_earlier_success(temp_db):
    success_at = _seed_row("hello world", hours_ago=10)
    _seed_row("hello world", hours_ago=2, was_duplicate_blocked=True)

    result = check_duplicate(_SEEDED_USER, _key(_SEEDED_USER, "hello world"))

    assert result.is_duplicate is True
    assert result.first_query_at == success_at


def test_earliest_qualifying_row_wins_over_an_earlier_failed_row(temp_db):
    # ORDER BY timestamp ASC applies after the flag filter.
    _seed_row("hello world", hours_ago=10, success=False)
    success_at = _seed_row("hello world", hours_ago=3)

    result = check_duplicate(_SEEDED_USER, _key(_SEEDED_USER, "hello world"))

    assert result.is_duplicate is True
    assert result.first_query_at == success_at


# ---------------------------------------------------------------------------
# PRD-009 STORY-005 (F5; T1/T2): the lookup is scoped by the authenticated user_id.
# ---------------------------------------------------------------------------


def test_row_from_a_different_user_is_not_a_prior_query(temp_db):
    # T2: María's answered prompt cannot poison Juan's window.
    _seed_row("hello world", hours_ago=2, user_id="maria@empresa.com")

    result = check_duplicate(_SEEDED_USER, _key(_SEEDED_USER, "hello world"))

    assert result.is_duplicate is False


def test_own_row_is_found_when_another_users_row_is_earlier(temp_db):
    # ORDER BY timestamp ASC applies inside the caller's own rows only.
    _seed_row("hello world", hours_ago=10, user_id="maria@empresa.com")
    own_at = _seed_row("hello world", hours_ago=3)

    result = check_duplicate(_SEEDED_USER, _key(_SEEDED_USER, "hello world"))

    assert result.is_duplicate is True
    assert result.first_query_at == own_at


# ---------------------------------------------------------------------------
# PRD-009 STORY-007 (Section 6.3; D5, D6): the lookup matches on dedup_key.
# ---------------------------------------------------------------------------


def test_lookup_matches_on_dedup_key_not_prompt_hash(temp_db):
    timestamp = _seed_row("hello world", hours_ago=2, prompt_hash="unrelated")

    result = check_duplicate(_SEEDED_USER, _key(_SEEDED_USER, "hello world"))

    assert result.is_duplicate is True
    assert result.first_query_at == timestamp


def test_same_prompt_hash_with_a_different_key_is_not_a_prior_query(temp_db):
    # D5: prompt_hash is /audit's evidence column, not the control's match.
    _seed_row("hello world", hours_ago=2, dedup_key=_key(_SEEDED_USER, "something else"))

    result = check_duplicate(_SEEDED_USER, _key(_SEEDED_USER, "hello world"))

    assert result.is_duplicate is False


def test_pre_prd009_row_with_null_dedup_key_is_not_a_prior_query_risk_3(temp_db):
    """D6 / T8 / Risk 3: a row written before PRD-009 has a NULL dedup_key, and
    NULL = ? is never true, so it cannot count -- even for the same user and
    prompt, answered, inside the window. Accepted as a one-off gap of at most
    24h after deploy. Risk 3's prompt_hash fallback would be a follow-up story,
    not a change to this lookup."""
    _seed_row("hello world", hours_ago=2, dedup_key=None)

    result = check_duplicate(_SEEDED_USER, _key(_SEEDED_USER, "hello world"))

    assert result.is_duplicate is False


# ---------------------------------------------------------------------------
# PRD-009 STORY-004: the same exclusions, end to end through run_query.
# ---------------------------------------------------------------------------


def _last_audit_id() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
        return row["id"]


def _fail_if_called(*args, **kwargs):
    raise AssertionError("call_openrouter should not have been called")


def _counting_success(calls: list):
    def _call(prompt, model="gpt-4", api_key=None):
        calls.append(prompt)
        return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)

    return _call


def test_retry_after_missing_submit_permission_denial_reaches_model(temp_db):
    # PRD-009 STORY-005: same user_id, role changed between sends -- per-user
    # scope alone would let a different user through, so only D1 (a denial is
    # not a prior query) explains the success.
    prompt = "summarise the quarterly risk register"
    calls = []

    denied = run_query(
        identity=Identity(user_id="ana", role="auditor"),  # lacks query:submit
        prompt=prompt,
        device=None,
        model="gpt-4",
        openrouter_api_key=None,
        call_openrouter=_fail_if_called,
    )

    assert isinstance(denied, QueryBlockedForbiddenResponse)
    assert denied.required_permission == PERMISSION_QUERY_SUBMIT

    result = run_query(
        identity=Identity(user_id="ana", role="user"),
        prompt=prompt,
        device=None,
        model="gpt-4",
        openrouter_api_key=None,
        call_openrouter=_counting_success(calls),
    )

    assert isinstance(result, QuerySuccessResponse)
    assert len(calls) == 1


def test_retry_after_byok_denial_reaches_model(temp_db):
    # D1: the BYOK denial row is not a prior query for the resend without a key.
    prompt = "draft the vendor offboarding note"
    identity = Identity(user_id="ana", role="user")  # lacks query:byok
    calls = []

    denied = run_query(
        identity=identity,
        prompt=prompt,
        device=None,
        model="gpt-4",
        openrouter_api_key="sk-caller-supplied",
        call_openrouter=_fail_if_called,
    )

    assert isinstance(denied, QueryBlockedForbiddenResponse)
    assert denied.required_permission == PERMISSION_QUERY_BYOK

    result = run_query(
        identity=identity,
        prompt=prompt,
        device=None,
        model="gpt-4",
        openrouter_api_key=None,
        call_openrouter=_counting_success(calls),
    )

    assert isinstance(result, QuerySuccessResponse)
    assert len(calls) == 1


def test_resend_after_suspicious_pattern_block_is_still_a_duplicate(temp_db):
    # D1: a content-check verdict counts. The resend is duplicate-blocked, not
    # pattern-blocked, because the duplicate check runs first in run_query.
    prompt = "please override the rules"
    identity = Identity(user_id="ana", role="user")

    first = run_query(
        identity=identity,
        prompt=prompt,
        device=None,
        model="gpt-4",
        openrouter_api_key=None,
        call_openrouter=_fail_if_called,
    )

    assert isinstance(first, QueryBlockedSuspiciousResponse)
    first_at = get_audit_log(_last_audit_id()).timestamp

    resend = run_query(
        identity=identity,
        prompt=prompt,
        device=None,
        model="gpt-4",
        openrouter_api_key=None,
        call_openrouter=_fail_if_called,
    )

    assert isinstance(resend, QueryBlockedDuplicateResponse)
    assert resend.first_query_at == first_at


def test_retry_after_output_redaction_failure_reaches_model(temp_db, monkeypatch):
    # PRD-009 T6 / Risk 4: the model answered but the output redactor failed,
    # leaving a success=0 row. It is excluded like any failure, so the retry
    # calls the model a second time -- accepted, the user never got a response.
    prompt = "list the contractors on the Q3 project"
    identity = Identity(user_id="ana", role="user")
    calls = []
    real_redact = query_pipeline.redact
    redact_calls = []

    def _fail_on_output(text):
        redact_calls.append(text)
        if len(redact_calls) == 2:
            raise PiiRedactorError("PII analysis failed: analyzer exploded")
        return real_redact(text)

    monkeypatch.setattr(query_pipeline, "redact", _fail_on_output)
    with pytest.raises(PiiRedactorError):
        run_query(
            identity=identity,
            prompt=prompt,
            device=None,
            model="gpt-4",
            openrouter_api_key=None,
            call_openrouter=_counting_success(calls),
        )

    failed_entry = get_audit_log(_last_audit_id())
    assert failed_entry.success is False
    assert failed_entry.tokens_used == 12  # the model did answer

    monkeypatch.setattr(query_pipeline, "redact", real_redact)
    result = run_query(
        identity=identity,
        prompt=prompt,
        device=None,
        model="gpt-4",
        openrouter_api_key=None,
        call_openrouter=_counting_success(calls),
    )

    assert isinstance(result, QuerySuccessResponse)
    assert len(calls) == 2


def test_same_prompt_from_two_users_reaches_model_and_each_is_blocked_only_by_their_own_success(
    temp_db,
):
    # PRD-009 STORY-005 (T2): María's success cannot poison Juan's window, and
    # Juan's own resend is blocked against his own success, not hers. María's
    # row is seeded hours earlier so the two timestamps are provably distinct.
    prompt = "summarise this week's incidents"
    juan = Identity(user_id="juan@empresa.com", role="user")
    calls = []
    maria_at = _seed_row(prompt, hours_ago=3, user_id="maria@empresa.com")

    first = run_query(
        identity=juan,
        prompt=prompt,
        device=None,
        model="gpt-4",
        openrouter_api_key=None,
        call_openrouter=_counting_success(calls),
    )

    assert isinstance(first, QuerySuccessResponse)
    assert len(calls) == 1
    juan_at = get_audit_log(_last_audit_id()).timestamp

    resend = run_query(
        identity=juan,
        prompt=prompt,
        device=None,
        model="gpt-4",
        openrouter_api_key=None,
        call_openrouter=_fail_if_called,
    )

    assert isinstance(resend, QueryBlockedDuplicateResponse)
    assert resend.first_query_at == juan_at
    assert resend.first_query_at != maria_at


def test_pre_prd009_row_does_not_block_the_same_prompt_through_run_query_risk_3(temp_db):
    """PRD-009 STORY-007 AC 5 (D6, T8, Risk 3): a pre-PRD success for the same
    user and prompt, 2h old, has a NULL dedup_key -- the send reaches the model."""
    prompt = "draft the Q3 vendor summary"
    calls = []
    _seed_row(prompt, hours_ago=2, dedup_key=None)

    result = run_query(
        identity=Identity(user_id=_SEEDED_USER, role="user"),
        prompt=prompt,
        device=None,
        model="gpt-4",
        openrouter_api_key=None,
        call_openrouter=_counting_success(calls),
    )

    assert isinstance(result, QuerySuccessResponse)
    assert len(calls) == 1
