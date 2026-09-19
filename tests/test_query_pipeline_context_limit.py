"""PRD-010 STORY-008: the context-limit arm of `run_conversation`.

Scope is exactly this story's ACs -- which limit is reported and with what
numbers, the boundary (exactly at the maximum is *within* it), the precedence
of messages over characters, the single `success=0` audit row the refusal
leaves, and the arm's position: after all three authorization checks, before
`check_duplicate`. The position is pinned from both sides with spies, because
it is the only property here that no field of the response body would reveal
if it broke.

Full multi-turn invariant coverage -- the whole check order in one spy list,
raw-text hashing over prefixes, the no-new-ingress schema test -- is STORY-009's
`tests/test_query_pipeline_multiturn.py`, not this file.

The limits are set with `monkeypatch.setattr(settings, ...)` rather than through
the environment, which is also the assertion behind
`test_limits_are_read_per_call_not_captured_at_import`: a pipeline that read its
maxima once at import would ignore every one of these tests and pass none of
them.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

from app.config import settings
from app.db.database import get_audit_log, get_connection
from app.models.messages import Message
from app.models.schemas import (
    QueryBlockedContextLimitResponse,
    QueryBlockedForbiddenResponse,
    QuerySuccessResponse,
)
from app.services.duplicate_checker import dedup_key, hash_prompt
from app.services.identity import Identity
from app.services.openrouter_client import OpenRouterResult
import app.services.query_pipeline as query_pipeline

_JUAN = Identity(user_id="juan@empresa.com", role="user")
_DENIED = Identity(user_id="reviewer", role="auditor")  # lacks query:submit

_SESSION_ID = "0c8f6f0e-6a1e-4a6c-9f2e-0b1a2c3d4e5f"


def _count_audit_rows() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]


def _last_audit_entry():
    # By id, not timestamp: timestamps have one-second resolution.
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
    return get_audit_log(row["id"])


def _fail_if_called(*args, **kwargs):
    raise AssertionError("this collaborator should not have been called")


class _Upstream:
    """A stub that records whether it was reached, for the boundary test."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, messages, model="gpt-4", api_key=None):
        self.calls += 1
        return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)


# ---------------------------------------------------------------------------
# AC2: the messages limit, and its precedence over the characters limit.
# ---------------------------------------------------------------------------


def test_conversation_over_the_message_limit_is_refused_with_the_counts(
    temp_db, monkeypatch
):
    monkeypatch.setattr(settings, "CONTEXT_MAX_MESSAGES", 3)
    messages = [
        Message("user", "one"),
        Message("assistant", "ok"),
        Message("user", "two"),
        Message("user", "three"),
    ]

    result = query_pipeline.run_conversation(
        identity=_JUAN, messages=messages, device=None, model="gpt-4",
        openrouter_api_key=None, call_openrouter=_fail_if_called,
    )

    assert isinstance(result, QueryBlockedContextLimitResponse)
    assert result.model_dump() == {
        "status": "BLOCKED",
        "reason": "Conversation exceeds context limit",
        "limit": "messages",
        "maximum": 3,
        "actual": 4,
    }


def test_conversation_over_both_limits_reports_messages(temp_db, monkeypatch):
    """AC2: messages are checked first and the function returns on the first
    breach, so the character count is never even computed for this call."""
    monkeypatch.setattr(settings, "CONTEXT_MAX_MESSAGES", 3)
    monkeypatch.setattr(settings, "CONTEXT_MAX_CHARACTERS", 1)
    messages = [
        Message("user", "one"),
        Message("assistant", "ok"),
        Message("user", "two"),
        Message("user", "three"),
    ]

    result = query_pipeline.run_conversation(
        identity=_JUAN, messages=messages, device=None, model="gpt-4",
        openrouter_api_key=None, call_openrouter=_fail_if_called,
    )

    assert isinstance(result, QueryBlockedContextLimitResponse)
    assert result.limit == "messages"
    assert result.maximum == 3
    assert result.actual == 4


# ---------------------------------------------------------------------------
# AC3: the characters limit, and the boundary.
# ---------------------------------------------------------------------------


def test_conversation_over_the_character_limit_is_refused_with_the_counts(
    temp_db, monkeypatch
):
    monkeypatch.setattr(settings, "CONTEXT_MAX_CHARACTERS", 10)
    # 5 + 2 + 5 = 12 characters across the three contents.
    messages = [
        Message("user", "aaaaa"),
        Message("assistant", "bb"),
        Message("user", "ccccc"),
    ]

    result = query_pipeline.run_conversation(
        identity=_JUAN, messages=messages, device=None, model="gpt-4",
        openrouter_api_key=None, call_openrouter=_fail_if_called,
    )

    assert isinstance(result, QueryBlockedContextLimitResponse)
    assert result.model_dump() == {
        "status": "BLOCKED",
        "reason": "Conversation exceeds context limit",
        "limit": "characters",
        "maximum": 10,
        "actual": 12,
    }


def test_conversation_exactly_at_the_character_limit_is_not_refused(
    temp_db, monkeypatch
):
    """AC3 boundary: `> maximum`, not `>=`. The upstream stub's call count is
    asserted too, so an off-by-one cannot pass this test by refusing the
    conversation for some other reason and never reaching the model."""
    monkeypatch.setattr(settings, "CONTEXT_MAX_CHARACTERS", 10)
    upstream = _Upstream()
    # 5 + 2 + 3 = 10 characters: exactly the maximum, which is within it.
    messages = [
        Message("user", "aaaaa"),
        Message("assistant", "bb"),
        Message("user", "ccc"),
    ]

    result = query_pipeline.run_conversation(
        identity=_JUAN, messages=messages, device=None, model="gpt-4",
        openrouter_api_key=None, call_openrouter=upstream,
    )

    assert isinstance(result, QuerySuccessResponse)
    assert upstream.calls == 1


def test_conversation_exactly_at_the_message_limit_is_not_refused(
    temp_db, monkeypatch
):
    monkeypatch.setattr(settings, "CONTEXT_MAX_MESSAGES", 3)
    upstream = _Upstream()
    messages = [
        Message("user", "one"),
        Message("assistant", "ok"),
        Message("user", "two"),
    ]

    result = query_pipeline.run_conversation(
        identity=_JUAN, messages=messages, device=None, model="gpt-4",
        openrouter_api_key=None, call_openrouter=upstream,
    )

    assert isinstance(result, QuerySuccessResponse)
    assert upstream.calls == 1


# ---------------------------------------------------------------------------
# AC4: the audit row.
# ---------------------------------------------------------------------------


def test_character_refusal_writes_exactly_one_row_naming_the_limit(
    temp_db, monkeypatch
):
    monkeypatch.setattr(settings, "CONTEXT_MAX_CHARACTERS", 10)
    messages = [
        Message("user", "aaaaa"),
        Message("assistant", "bb"),
        Message("user", "ccccc"),
    ]
    before = _count_audit_rows()

    query_pipeline.run_conversation(
        identity=_JUAN, messages=messages, device=None, model="gpt-4",
        openrouter_api_key=None, call_openrouter=_fail_if_called,
        session_id=_SESSION_ID,
    )

    assert _count_audit_rows() == before + 1
    row = _last_audit_entry()
    assert row.success is False
    assert row.error_message == "context limit: characters 12 > 10"
    # The audited prompt is the last user turn: the row stores a hash and a
    # preview of it, never the raw conversation.
    assert row.prompt_preview == "ccccc"
    assert row.prompt_hash == hash_prompt("ccccc")
    assert row.session_id == _SESSION_ID
    # Non-NULL, and the same key every other arm of this send would have
    # recorded -- computed once, before authorization (STORY-007).
    assert row.dedup_key is not None
    assert row.dedup_key == dedup_key(_JUAN.user_id, messages)


def test_message_refusal_row_names_the_messages_limit(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "CONTEXT_MAX_MESSAGES", 3)
    messages = [
        Message("user", "one"),
        Message("assistant", "ok"),
        Message("user", "two"),
        Message("user", "three"),
    ]
    before = _count_audit_rows()

    query_pipeline.run_conversation(
        identity=_JUAN, messages=messages, device=None, model="gpt-4",
        openrouter_api_key=None, call_openrouter=_fail_if_called,
    )

    assert _count_audit_rows() == before + 1
    row = _last_audit_entry()
    assert row.success is False
    assert row.error_message == "context limit: messages 4 > 3"
    assert row.prompt_preview == "three"
    assert row.dedup_key == dedup_key(_JUAN.user_id, messages)


def test_refusal_row_is_not_flagged_as_duplicate_or_suspicious(
    temp_db, monkeypatch
):
    """`success=0` with the reason in `error_message` is the whole record: no
    verdict column is set, because no verdict was reached (PRD 6.5, 9.2 T7)."""
    monkeypatch.setattr(settings, "CONTEXT_MAX_CHARACTERS", 10)
    messages = [Message("user", "aaaaabbbbbcc")]

    query_pipeline.run_conversation(
        identity=_JUAN, messages=messages, device=None, model="gpt-4",
        openrouter_api_key=None, call_openrouter=_fail_if_called,
    )

    row = _last_audit_entry()
    assert row.was_duplicate_blocked is False
    assert row.suspicious_pattern is None
    assert row.denied_permission is None
    assert row.model_used is None


# ---------------------------------------------------------------------------
# AC4: position in the check order, pinned from both sides.
# ---------------------------------------------------------------------------


def test_check_duplicate_is_never_called_on_a_context_limit_refusal(
    temp_db, monkeypatch
):
    """The limit is checked *before* the duplicate window, so an over-limit
    conversation neither consults it nor counts toward it (PRD 6.1)."""
    monkeypatch.setattr(settings, "CONTEXT_MAX_CHARACTERS", 10)
    monkeypatch.setattr(query_pipeline, "check_duplicate", _fail_if_called)
    messages = [Message("user", "aaaaabbbbbcc")]

    result = query_pipeline.run_conversation(
        identity=_JUAN, messages=messages, device=None, model="gpt-4",
        openrouter_api_key=None, call_openrouter=_fail_if_called,
    )

    assert isinstance(result, QueryBlockedContextLimitResponse)


def test_a_forbidden_identity_gets_forbidden_not_context_limit(
    temp_db, monkeypatch
):
    """The limit is checked *after* all three authorization arms, so a caller
    without `query:submit` learns nothing about how this deployment is
    configured (PRD 6.1)."""
    monkeypatch.setattr(settings, "CONTEXT_MAX_CHARACTERS", 1)
    messages = [Message("user", "aaaaabbbbbcc")]

    result = query_pipeline.run_conversation(
        identity=_DENIED, messages=messages, device=None, model="gpt-4",
        openrouter_api_key=None, call_openrouter=_fail_if_called,
    )

    assert isinstance(result, QueryBlockedForbiddenResponse)
    assert result.required_permission == "query:submit"
    assert _last_audit_entry().denied_permission == "query:submit"


def test_a_disallowed_model_is_refused_before_the_context_limit(
    temp_db, monkeypatch
):
    """The second of the three authorization arms, for the same reason."""
    monkeypatch.setattr(settings, "CONTEXT_MAX_CHARACTERS", 1)
    messages = [Message("user", "aaaaabbbbbcc")]

    result = query_pipeline.run_conversation(
        identity=_JUAN, messages=messages, device=None, model="not-a-real-model",
        openrouter_api_key=None, call_openrouter=_fail_if_called,
    )

    assert isinstance(result, QueryBlockedForbiddenResponse)


# ---------------------------------------------------------------------------
# Technical Notes: the limits are settings reads, per call.
# ---------------------------------------------------------------------------


def test_limits_are_read_per_call_not_captured_at_import(temp_db, monkeypatch):
    """The same conversation is refused under a small limit and accepted once
    the limit is restored, in one process -- which a module-level constant
    could not do."""
    messages = [Message("user", "aaaaabbbbbcc")]
    upstream = _Upstream()

    monkeypatch.setattr(settings, "CONTEXT_MAX_CHARACTERS", 10)
    refused = query_pipeline.run_conversation(
        identity=_JUAN, messages=messages, device=None, model="gpt-4",
        openrouter_api_key=None, call_openrouter=_fail_if_called,
    )
    assert isinstance(refused, QueryBlockedContextLimitResponse)

    monkeypatch.setattr(settings, "CONTEXT_MAX_CHARACTERS", 200_000)
    accepted = query_pipeline.run_conversation(
        identity=_JUAN, messages=messages, device=None, model="gpt-4",
        openrouter_api_key=None, call_openrouter=upstream,
    )
    assert isinstance(accepted, QuerySuccessResponse)
    assert upstream.calls == 1


def test_run_query_reaches_the_same_arm(temp_db, monkeypatch):
    """The adapter is not a second path: a single oversized prompt is refused
    by the same check, which is what makes `/query` outcome 7 reachable."""
    monkeypatch.setattr(settings, "CONTEXT_MAX_CHARACTERS", 10)

    result = query_pipeline.run_query(
        identity=_JUAN, prompt="a" * 11, device=None, model="gpt-4",
        openrouter_api_key=None, call_openrouter=_fail_if_called,
    )

    assert isinstance(result, QueryBlockedContextLimitResponse)
    assert result.limit == "characters"
    assert result.maximum == 10
    assert result.actual == 11
