import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import insert_audit_log, insert_user
from app.db.models import AuditLog, User
from app.main import app
from app.services.identity import hash_token
from app.services.openrouter_client import OpenRouterResult

client = TestClient(app)


def _fail_if_called(*args, **kwargs):
    raise AssertionError("repository function should not have been called")


def test_missing_admin_token_rejected_before_db_access(temp_db, monkeypatch):
    monkeypatch.setattr("app.routers.admin.list_audit_logs", _fail_if_called)
    monkeypatch.setattr("app.routers.admin.count_audit_logs", _fail_if_called)

    response = client.get("/audit")

    assert response.status_code in (401, 403)


def test_incorrect_admin_token_rejected(temp_db, monkeypatch):
    monkeypatch.setattr("app.routers.admin.list_audit_logs", _fail_if_called)
    monkeypatch.setattr("app.routers.admin.count_audit_logs", _fail_if_called)

    response = client.get("/audit", headers={"Authorization": "Bearer wrong-token"})

    assert response.status_code in (401, 403)


def test_valid_token_returns_expected_shape(temp_db):
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-04T09:00:00Z",
            user_id="juan@empresa.com",
            device="Chrome/Windows",
            prompt_hash="hash1",
            model_used="gpt-4",
            suspicious_pattern="override",
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-04T10:00:00Z",
            user_id="maria@empresa.com",
            device="Firefox/Linux",
            prompt_hash="hash2",
            model_used="claude-3-sonnet",
            was_duplicate_blocked=True,
        )
    )

    response = client.get(
        "/audit", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["queries"]) == 2
    assert [q["timestamp"] for q in body["queries"]] == [
        "2026-07-04T10:00:00Z",
        "2026-07-04T09:00:00Z",
    ]
    for entry in body["queries"]:
        assert set(entry.keys()) == {
            "audit_id",
            "user_id",
            "timestamp",
            "model",
            "prompt_hash",
            "was_duplicate_blocked",
            "suspicious_pattern_detected",
            "device",
            "pii_detected_input",
            "pii_detected_output",
            "pii_entities",
            "role",
            "denied_permission",
            "session_id",
            # PRD-011 D6: two additive, nullable fields (STORY-010).
            "pattern_role",
            "pattern_action",
            # PRD-012 D9: additive, nullable (STORY-011).
            "profile",
            # PRD-013 6.10: eight additive fields, six nullable and two
            # defaulted flags (STORY-006).
            "ingress",
            "message_count",
            "input_tokens",
            "output_tokens",
            "streamed",
            "has_tool_calls",
            "conversation_key",
            "limit_exceeded",
            # PRD-015 Section 10: additive, nullable (STORY-007).
            "ignored_params",
            # PRD-020 D13 (STORY-006): five additive provider fields.
            "provider",
            "upstream_model",
            "provider_trust",
            "pii_input_relaxed",
            "usage_estimated",
            # PRD-021 F7 (STORY-013): four additive real-time fields.
            "streamed_realtime",
            "reasoning_shown",
            "stream_redaction_divergence",
            "completion_id",
            # PRD-022 F8 / D10 (STORY-003): seven additive, nullable fields.
            "request_id",
            "attempt",
            "route_model",
            "fallback_reason",
            "skipped_providers",
            "cache_read_tokens",
            "cache_write_tokens",
        }

    newest, oldest = body["queries"]
    assert newest["was_duplicate_blocked"] is True
    assert newest["suspicious_pattern_detected"] is False
    assert oldest["suspicious_pattern_detected"] is True
    assert oldest["model"] == "gpt-4"


def test_audit_entry_carries_pattern_role_and_action(temp_db):
    """PRD-011 D6 (STORY-010 AC 3). Both fields pass through verbatim, and
    `suspicious_pattern_detected` keeps its meaning -- "a pattern was
    matched" -- so it is true for the flag row too. A pre-PRD-011 row reads
    null/null, and a row with no pattern reads null/null and False."""
    rows = [
        ("2026-09-23T12:00:00Z", "hb", "ignore previous instructions", "user", "block"),
        ("2026-09-23T11:00:00Z", "hf", "ignore previous instructions", "tool", "flag"),
        ("2026-09-23T10:00:00Z", "hl", "override", None, None),
        ("2026-09-23T09:00:00Z", "hc", None, None, None),
    ]
    for timestamp, prompt_hash, pattern, role, action in rows:
        insert_audit_log(
            AuditLog(
                timestamp=timestamp,
                user_id="juan@empresa.com",
                prompt_hash=prompt_hash,
                suspicious_pattern=pattern,
                pattern_role=role,
                pattern_action=action,
            )
        )

    response = client.get(
        "/audit", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    assert response.status_code == 200
    assert [
        (q["pattern_role"], q["pattern_action"], q["suspicious_pattern_detected"])
        for q in response.json()["queries"]
    ] == [
        ("user", "block", True),
        ("tool", "flag", True),
        (None, None, True),
        (None, None, False),
    ]


def test_fewer_than_100_rows_returns_all_without_error(temp_db):
    for i in range(3):
        insert_audit_log(
            AuditLog(
                timestamp=f"2026-07-0{i + 1}T10:00:00Z",
                user_id="juan@empresa.com",
                prompt_hash=f"hash{i}",
            )
        )

    response = client.get(
        "/audit", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["queries"]) == 3


def test_pii_telemetry_fields_reflect_audit_log_values(temp_db):
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-05T10:00:00Z",
            user_id="juan@empresa.com",
            prompt_hash="hash-pii",
            pii_detected_input=True,
            pii_detected_output=True,
            pii_entities="EMAIL_ADDRESS,PERSON",
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-06T10:00:00Z",
            user_id="maria@empresa.com",
            prompt_hash="hash-clean",
        )
    )

    response = client.get(
        "/audit", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    body = response.json()
    by_hash = {q["prompt_hash"]: q for q in body["queries"]}

    flagged = by_hash["hash-pii"]
    assert flagged["pii_detected_input"] is True
    assert flagged["pii_detected_output"] is True
    assert flagged["pii_entities"] == ["EMAIL_ADDRESS", "PERSON"]

    clean = by_hash["hash-clean"]
    assert clean["pii_detected_input"] is False
    assert clean["pii_detected_output"] is False
    assert clean["pii_entities"] == []


def test_response_never_includes_ip_or_raw_text(temp_db):
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-04T10:00:00Z",
            user_id="juan@empresa.com",
            device="Chrome/Windows",
            prompt_hash="hash1",
            prompt_preview="this is a raw prompt preview",
            response_hash="resphash1",
            response_preview="this is a raw response preview",
            model_used="gpt-4",
        )
    )

    response = client.get(
        "/audit", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    assert response.status_code == 200
    body = response.json()
    for entry in body["queries"]:
        # PRD-022 D10 (STORY-003): `skipped_providers` contains the letters
        # "ip" by accident; the guard is for an IP-address field, so it matches
        # the word, not the substring.
        assert not any("ip" in key.lower().split("_") for key in entry.keys())
        assert "prompt" not in entry or entry.get("prompt_hash") == "hash1"
        assert "response" not in entry
        assert "prompt_preview" not in entry
        assert "response_preview" not in entry
        assert "response_hash" not in entry


def test_auditor_role_sees_every_row(temp_db):
    insert_user(
        User(user_id="reviewer", role="auditor", token_hash=hash_token("auditor-token"))
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-01T10:00:00Z", user_id="a", prompt_hash="h1")
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-02T10:00:00Z", user_id="b", prompt_hash="h2")
    )

    response = client.get(
        "/audit", headers={"Authorization": "Bearer auditor-token"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {q["user_id"] for q in body["queries"]} == {"a", "b"}


def test_user_role_sees_only_own_rows_and_scoped_total(temp_db):
    insert_user(
        User(user_id="ana", role="user", token_hash=hash_token("ana-token"))
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-01T10:00:00Z", user_id="ana", prompt_hash="h1")
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-02T10:00:00Z", user_id="someone-else", prompt_hash="h2")
    )

    response = client.get(
        "/audit", headers={"Authorization": "Bearer ana-token"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["queries"]) == 1
    assert body["queries"][0]["user_id"] == "ana"


def test_identity_lacking_both_audit_permissions_returns_403(temp_db):
    insert_user(
        User(user_id="outsider", role="guest", token_hash=hash_token("guest-token"))
    )

    response = client.get(
        "/audit", headers={"Authorization": "Bearer guest-token"}
    )

    assert response.status_code == 403


def test_audit_entry_carries_role_and_denied_permission(temp_db):
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-01T10:00:00Z",
            user_id="ana",
            prompt_hash="h1",
            role="user",
            denied_permission="query:byok",
        )
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-02T10:00:00Z", user_id="ana", prompt_hash="h2")
    )

    response = client.get(
        "/audit", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    body = response.json()
    by_hash = {q["prompt_hash"]: q for q in body["queries"]}
    assert by_hash["h1"]["role"] == "user"
    assert by_hash["h1"]["denied_permission"] == "query:byok"
    assert by_hash["h2"]["role"] is None
    assert by_hash["h2"]["denied_permission"] is None


def test_audit_entry_carries_session_id_when_present_and_null_when_absent(temp_db):
    """PRD-008 STORY-011 AC 3 and AC 5: the present case and the absent one.

    The second row is constructed exactly as `AuditLog` was constructible
    before this PRD -- no `session_id` argument at all -- so it stands in for
    every row written before the column existed. Reporting `None` for it is the
    whole of the backward-compatibility claim: an additive field on a response
    model, invisible to a consumer that does not read it.
    """
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-01T10:00:00Z",
            user_id="ana",
            prompt_hash="h-session",
            session_id="0f6c2e5a-9b3d-4c81-a7f2-1d5e8c9b0a34",
        )
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-02T10:00:00Z", user_id="ana", prompt_hash="h-no-session")
    )

    response = client.get(
        "/audit", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    body = response.json()
    by_hash = {q["prompt_hash"]: q for q in body["queries"]}
    assert by_hash["h-session"]["session_id"] == "0f6c2e5a-9b3d-4c81-a7f2-1d5e8c9b0a34"
    assert by_hash["h-no-session"]["session_id"] is None


def test_audit_entry_carries_profile(temp_db):
    """PRD-012 D9 (STORY-011 AC 4): passed through verbatim, newest first; a
    row written before PRD-012 reads null."""
    for timestamp, prompt_hash, profile in [
        ("2026-09-25T12:00:00Z", "hc", "chat"),
        ("2026-09-25T11:00:00Z", "hk", "code"),
        ("2026-09-25T10:00:00Z", "hl", None),
    ]:
        insert_audit_log(
            AuditLog(
                timestamp=timestamp,
                user_id="juan@empresa.com",
                prompt_hash=prompt_hash,
                profile=profile,
            )
        )

    response = client.get(
        "/audit", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    assert response.status_code == 200
    assert [q["profile"] for q in response.json()["queries"]] == ["chat", "code", None]


def test_audit_entry_carries_ignored_params(temp_db):
    """PRD-015 STORY-007 AC 4: passed through verbatim, newest first; a row
    with nothing ignored -- every row off `/v1` -- reads null."""
    for timestamp, prompt_hash, ingress, ignored in [
        ("2026-10-23T12:00:00Z", "hv", "v1", "seed,user"),
        ("2026-10-23T11:00:00Z", "hq", "query", None),
    ]:
        insert_audit_log(
            AuditLog(
                timestamp=timestamp,
                user_id="juan@empresa.com",
                prompt_hash=prompt_hash,
                ingress=ingress,
                ignored_params=ignored,
            )
        )

    response = client.get(
        "/audit", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    assert response.status_code == 200
    assert [q["ignored_params"] for q in response.json()["queries"]] == ["seed,user", None]


def test_a_query_row_reads_null_ignored_params_on_audit(temp_db, monkeypatch):
    """PRD-015 STORY-007 AC 4, over a row the real `/query` route wrote."""
    insert_user(
        User(user_id="juan@empresa.com", role="user", token_hash=hash_token("story007-token"))
    )
    monkeypatch.setattr(
        "app.routers.query.call_openrouter",
        lambda messages, model="gpt-4", api_key=None: OpenRouterResult(
            response="ok", model_used=model, tokens_used=3
        ),
    )

    sent = client.post(
        "/query",
        json={"prompt": "what is a linked list?"},
        headers={"Authorization": "Bearer story007-token"},
    )
    assert sent.status_code == 200
    assert sent.json()["status"] == "SUCCESS"

    response = client.get(
        "/audit", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    (entry,) = response.json()["queries"]
    assert entry["audit_id"] == sent.json()["audit_id"]
    assert entry["ingress"] == "query"
    assert entry["ignored_params"] is None


def test_audit_entry_carries_the_prd020_provider_fields(temp_db):
    """PRD-020 D13 (STORY-006 AC 4): the five fields pass through verbatim; a
    row no PRD-020 caller wrote reads null/null/null/false/false."""
    from app.services.audit_logger import log_query
    from app.services.duplicate_checker import hash_prompt

    log_query(
        user_id="juan@empresa.com",
        prompt="served by a local model",
        provider="lmstudio",
        upstream_model="bonsai-27b",
        provider_trust="local",
        pii_input_relaxed=True,
        usage_estimated=True,
        streamed_realtime=False,  # PRD-021 STORY-009: required keywords
        reasoning_shown=False,
    )
    log_query(
        user_id="juan@empresa.com", prompt="plain row",
        streamed_realtime=False, reasoning_shown=False,
    )

    response = client.get(
        "/audit", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    assert response.status_code == 200
    by_hash = {q["prompt_hash"]: q for q in response.json()["queries"]}
    fields = ("provider", "upstream_model", "provider_trust", "pii_input_relaxed", "usage_estimated")
    carried = by_hash[hash_prompt("served by a local model")]
    plain = by_hash[hash_prompt("plain row")]
    assert tuple(carried[f] for f in fields) == ("lmstudio", "bonsai-27b", "local", True, True)
    assert tuple(plain[f] for f in fields) == (None, None, None, False, False)


# --- PRD-021 F7 (STORY-013): real-time fields and ?completion_id= -----------

_ADMIN = {"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}


def _seed(user_id, completion_id, ts, **extra):
    insert_audit_log(
        AuditLog(
            timestamp=ts,
            user_id=user_id,
            prompt_hash=f"h-{completion_id}-{ts}",
            completion_id=completion_id,
            **extra,
        )
    )


def test_audit_entry_carries_the_prd021_realtime_fields(temp_db):
    """PRD-021 F7 / D14: the four columns pass through verbatim; a row no
    PRD-021 caller wrote reads false / false / false / null."""
    _seed(
        "u", "chatcmpl-harness-rt-aaa", "2026-07-01T10:00:00Z",
        streamed_realtime=True, reasoning_shown=True,
        stream_redaction_divergence=True,
    )
    _seed("u", None, "2026-07-01T09:00:00Z")

    body = client.get("/audit", headers=_ADMIN).json()

    fields = (
        "streamed_realtime", "reasoning_shown",
        "stream_redaction_divergence", "completion_id",
    )
    live, plain = body["queries"]
    assert tuple(live[f] for f in fields) == (
        True, True, True, "chatcmpl-harness-rt-aaa"
    )
    assert tuple(plain[f] for f in fields) == (False, False, False, None)


def test_completion_id_filter_is_an_exact_match(temp_db):
    _seed("u", "chatcmpl-harness-rt-aaa", "2026-07-01T10:00:00Z")
    _seed("u", "chatcmpl-harness-rt-aaab", "2026-07-01T11:00:00Z")
    _seed("u", None, "2026-07-01T12:00:00Z")

    exact = client.get(
        "/audit?completion_id=chatcmpl-harness-rt-aaa", headers=_ADMIN
    ).json()
    prefix = client.get(
        "/audit?completion_id=chatcmpl-harness-rt", headers=_ADMIN
    ).json()
    unfiltered = client.get("/audit", headers=_ADMIN).json()

    assert exact["total"] == 1
    assert [q["completion_id"] for q in exact["queries"]] == [
        "chatcmpl-harness-rt-aaa"
    ]
    assert prefix == {"total": 0, "queries": []}
    assert unfiltered["total"] == 3


def test_completion_id_filter_composes_with_own_scope(temp_db):
    insert_user(User(user_id="ana", role="user", token_hash=hash_token("ana-token")))
    _seed("ana", "chatcmpl-harness-rt-ana", "2026-07-01T10:00:00Z")
    _seed("bob", "chatcmpl-harness-rt-bob", "2026-07-01T11:00:00Z")
    own = {"Authorization": "Bearer ana-token"}

    mine = client.get("/audit?completion_id=chatcmpl-harness-rt-ana", headers=own)
    theirs = client.get("/audit?completion_id=chatcmpl-harness-rt-bob", headers=own)
    as_admin = client.get(
        "/audit?completion_id=chatcmpl-harness-rt-bob", headers=_ADMIN
    )

    assert mine.json()["total"] == 1
    # Another user's id under audit:read:own is empty, not a 403.
    assert theirs.status_code == 200
    assert theirs.json() == {"total": 0, "queries": []}
    assert as_admin.json()["total"] == 1


def test_completion_id_filter_is_a_bound_value_not_sql(temp_db):
    _seed("u", "chatcmpl-harness-rt-aaa", "2026-07-01T10:00:00Z")

    response = client.get(
        "/audit", params={"completion_id": "x' OR '1'='1"}, headers=_ADMIN
    )

    assert response.status_code == 200
    assert response.json() == {"total": 0, "queries": []}


def test_an_empty_completion_id_is_a_422_not_no_filter(temp_db):
    response = client.get("/audit?completion_id=", headers=_ADMIN)

    assert response.status_code == 422


# --- PRD-022 F8 / D10 (STORY-003): trail fields and ?request_id= ---------------


def _seed_request(user_id, request_id, ts, **extra):
    insert_audit_log(
        AuditLog(
            timestamp=ts,
            user_id=user_id,
            prompt_hash=f"h-{request_id}-{ts}",
            request_id=request_id,
            **extra,
        )
    )


def test_audit_entry_carries_the_prd022_trail_fields(temp_db):
    """PRD-022 F8 / D10: the seven columns pass through verbatim; a row no
    PRD-022 caller wrote reads all null."""
    _seed_request(
        "u", "req-aaa", "2026-07-01T10:00:00Z", attempt=1, route_model="gpt-4",
        fallback_reason="unavailable", skipped_providers="a,b",
        cache_read_tokens=10, cache_write_tokens=5,
    )
    _seed_request("u", None, "2026-07-01T09:00:00Z")

    body = client.get("/audit", headers=_ADMIN).json()

    fields = (
        "request_id", "attempt", "route_model", "fallback_reason",
        "skipped_providers", "cache_read_tokens", "cache_write_tokens",
    )
    live, plain = body["queries"]
    assert tuple(live[f] for f in fields) == ("req-aaa", 1, "gpt-4", "unavailable", "a,b", 10, 5)
    assert tuple(plain[f] for f in fields) == (None,) * 7


def test_request_id_filter_is_an_exact_match(temp_db):
    _seed_request("u", "req-aaa", "2026-07-01T10:00:00Z")
    _seed_request("u", "req-aaa", "2026-07-01T10:30:00Z", attempt=2)
    _seed_request("u", "req-aaab", "2026-07-01T11:00:00Z")
    _seed_request("u", None, "2026-07-01T12:00:00Z")

    exact = client.get("/audit?request_id=req-aaa", headers=_ADMIN).json()
    prefix = client.get("/audit?request_id=req", headers=_ADMIN).json()
    unfiltered = client.get("/audit", headers=_ADMIN).json()

    assert exact["total"] == 2
    assert [q["request_id"] for q in exact["queries"]] == ["req-aaa", "req-aaa"]
    assert prefix == {"total": 0, "queries": []}
    assert unfiltered["total"] == 4


def test_request_id_filter_composes_with_own_scope(temp_db):
    insert_user(User(user_id="ana", role="user", token_hash=hash_token("ana-token")))
    _seed_request("ana", "req-ana", "2026-07-01T10:00:00Z")
    _seed_request("bob", "req-bob", "2026-07-01T11:00:00Z")
    own = {"Authorization": "Bearer ana-token"}

    mine = client.get("/audit?request_id=req-ana", headers=own)
    theirs = client.get("/audit?request_id=req-bob", headers=own)
    as_admin = client.get("/audit?request_id=req-bob", headers=_ADMIN)

    assert mine.json()["total"] == 1
    # Another user's id under audit:read:own is empty, not a 403.
    assert theirs.status_code == 200
    assert theirs.json() == {"total": 0, "queries": []}
    assert as_admin.json()["total"] == 1


def test_request_id_filter_is_a_bound_value_not_sql(temp_db):
    _seed_request("u", "req-aaa", "2026-07-01T10:00:00Z")

    response = client.get("/audit", params={"request_id": "x' OR '1'='1"}, headers=_ADMIN)

    assert response.status_code == 200
    assert response.json() == {"total": 0, "queries": []}


def test_an_empty_request_id_is_a_422_not_no_filter(temp_db):
    assert client.get("/audit?request_id=", headers=_ADMIN).status_code == 422
