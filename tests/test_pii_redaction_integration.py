import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import json
import pathlib
import re
import subprocess

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import get_audit_log, get_connection, init_db, insert_user
from app.db.models import User
from app.main import app
from app.services.duplicate_checker import hash_prompt
from app.services.identity import hash_token
from app.services.openrouter_client import OpenRouterResult

client = TestClient(app)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# Every string below was measured against this branch's redactor with the shipped
# settings (en_core_web_lg, PII_SCORE_THRESHOLD=0.35).
# Three entity types in BOTH directions: a single-entity fixture cannot catch a
# regression that drops PERSON or PHONE_NUMBER from the union.
_PII_PROMPT = (
    "my name is Maria Gomez, my email is juan@empresa.com and my phone is 555-123-4567"
)
_REDACTED_PROMPT = (
    "my name is <PERSON>, my email is <EMAIL_ADDRESS> and my phone is <PHONE_NUMBER>"
)
_PII_RESPONSE = "Please contact John Smith at john.smith@acme.com or 212-555-0199."
_REDACTED_RESPONSE = "Please contact <PERSON> at <EMAIL_ADDRESS> or <PHONE_NUMBER>."

_PROMPT_PII_FRAGMENTS = ("Maria Gomez", "juan@empresa.com", "555-123-4567")
_RESPONSE_PII_FRAGMENTS = ("John Smith", "john.smith@acme.com", "212-555-0199")
_EXPECTED_ENTITIES = ["EMAIL_ADDRESS", "PERSON", "PHONE_NUMBER"]  # sorted(set(...)) union

_ADMIN_HEADERS = {"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    insert_user(
        User(user_id=_USER_ID, role="user", token_hash=hash_token(_USER_TOKEN))
    )
    return db_path


def _count_audit_rows() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]


def _capturing_openrouter(seen: list, response: str = _PII_RESPONSE):
    """Records the outbound prompt, then answers with PII of its own."""

    def _call(prompt, model="gpt-4", api_key=None):
        seen.append(prompt)
        return OpenRouterResult(response=response, model_used=model, tokens_used=9)

    return _call


# Deliberately NOT the repo's usual "juan@empresa.com": that address is embedded in
# _PII_PROMPT as PII, and user_id is legitimately stored and exposed by /audit
# (PRD-001 Section 10 -- the audit trail's whole job is "who did what"). Keeping the
# caller's identity disjoint from the prompt's PII is what lets the leak assertions
# below distinguish "leaked from the prompt" from "recorded as the requester".
_USER_ID = "analyst-7"
_USER_TOKEN = "analyst-7-token"
_USER_HEADERS = {"Authorization": f"Bearer {_USER_TOKEN}"}


def _post_pii_query(monkeypatch, seen=None, user_id=_USER_ID):
    """One full POST /query with PII in BOTH directions. Returns (response, seen)."""
    seen = [] if seen is None else seen
    monkeypatch.setattr(
        "app.routers.query.call_openrouter", _capturing_openrouter(seen)
    )
    response = client.post(
        "/query",
        json={"user_id": user_id, "prompt": _PII_PROMPT, "device": "Chrome/Windows"},
        headers=_USER_HEADERS,
    )
    return response, seen


def test_openrouter_receives_only_the_masked_prompt(temp_db, monkeypatch):
    """AC1: the mock's recorded call args contain only redacted text."""
    response, seen = _post_pii_query(monkeypatch)

    assert response.status_code == 200
    assert seen == [_REDACTED_PROMPT]


@pytest.mark.parametrize("fragment", _PROMPT_PII_FRAGMENTS)
def test_no_raw_pii_fragment_reaches_openrouter(temp_db, monkeypatch, fragment):
    """AC1, per entity: name, email and phone are each individually absent."""
    response, seen = _post_pii_query(monkeypatch)

    assert response.status_code == 200
    assert fragment in _PII_PROMPT          # the fragment really was in what the user sent
    assert fragment not in seen[0]          # ...and is not in what left the building


def test_response_body_matches_prd_section_10_shape(temp_db, monkeypatch):
    """AC2: masked response + pii_redacted/pii_entities_masked, exact field set."""
    response, _ = _post_pii_query(monkeypatch)
    body = response.json()

    assert response.status_code == 200
    assert body == {
        "status": "SUCCESS",
        "response": _REDACTED_RESPONSE,
        "audit_id": body["audit_id"],
        "model_used": "gpt-4",
        "tokens_used": 9,
        "pii_redacted": True,
        "pii_entities_masked": _EXPECTED_ENTITIES,
    }
    assert isinstance(body["audit_id"], int)


@pytest.mark.parametrize("fragment", _RESPONSE_PII_FRAGMENTS)
def test_no_raw_pii_fragment_reaches_the_caller(temp_db, monkeypatch, fragment):
    """AC2, per entity: nothing raw survives anywhere in the serialized body."""
    response, _ = _post_pii_query(monkeypatch)

    assert response.status_code == 200
    assert fragment in _PII_RESPONSE
    assert fragment not in json.dumps(response.json())


def test_audit_row_keeps_both_raw_previews_and_raw_hashes(temp_db, monkeypatch):
    """AC3 (the actual promise, PRD RF-7): the persisted row is never masked."""
    response, _ = _post_pii_query(monkeypatch)
    entry = get_audit_log(response.json()["audit_id"])

    assert entry.prompt_preview == _PII_PROMPT
    assert entry.response_preview == _PII_RESPONSE
    assert entry.prompt_hash == hash_prompt(_PII_PROMPT)
    assert entry.response_hash == hash_prompt(_PII_RESPONSE)
    assert "<" not in entry.prompt_preview
    assert "<" not in entry.response_preview
    assert _count_audit_rows() == 1


def test_audit_endpoint_reports_telemetry_and_leaks_no_masked_values(temp_db, monkeypatch):
    """AC3 (the endpoint half): telemetry is exposed, placeholders are not."""
    _post_pii_query(monkeypatch)

    audit = client.get("/audit", headers=_ADMIN_HEADERS)
    payload = audit.json()

    assert audit.status_code == 200
    assert payload["total"] == 1
    entry = payload["queries"][0]
    assert entry["pii_detected_input"] is True
    assert entry["pii_detected_output"] is True
    assert entry["pii_entities"] == _EXPECTED_ENTITIES
    assert entry["was_duplicate_blocked"] is False
    assert entry["suspicious_pattern_detected"] is False
    # No masking placeholder anywhere in the admin payload...
    assert "<" not in json.dumps(payload)
    # ...and no raw PII either -- /audit reports ABOUT the PII, never the PII itself.
    for fragment in _PROMPT_PII_FRAGMENTS + _RESPONSE_PII_FRAGMENTS:
        assert fragment not in json.dumps(payload)


def test_audit_endpoint_contract_has_no_preview_fields(temp_db, monkeypatch):
    """Pins the deliberate decision to keep previews OUT of the admin API.

    PRD Section 11 requires telemetry "without exposing masked values as a distinct
    new leak surface", and PRD-001 Section 10's /audit contract never carried
    previews. If a future story adds them, this test fails -- forcing that to be a
    deliberate, reviewed decision rather than a drift.
    """
    _post_pii_query(monkeypatch)

    entry = client.get("/audit", headers=_ADMIN_HEADERS).json()["queries"][0]

    assert sorted(entry) == [
        "audit_id",
        "denied_permission",
        "device",
        "model",
        "pii_detected_input",
        "pii_detected_output",
        "pii_entities",
        "prompt_hash",
        "role",
        "suspicious_pattern_detected",
        "timestamp",
        "user_id",
        "was_duplicate_blocked",
    ]


def test_stats_endpoint_counts_the_pii_query(temp_db, monkeypatch):
    """AC3 sibling: /stats telemetry produced by a real pipeline run."""
    _post_pii_query(monkeypatch)

    stats = client.get("/stats", headers=_ADMIN_HEADERS).json()

    assert stats["total_queries"] == 1
    assert stats["pii_detected_queries"] == 1
    assert sorted(stats["top_pii_entities"]) == _EXPECTED_ENTITIES
    assert stats["blocked_duplicates"] == 0
    assert stats["blocked_suspicious"] == 0
    assert stats["success_rate"] == "100.0%"


def test_all_four_surfaces_agree_about_one_request(temp_db, monkeypatch):
    """The story in one test: outbound masked, caller masked, audit raw, /audit tells."""
    response, seen = _post_pii_query(monkeypatch)
    body = response.json()
    entry = get_audit_log(body["audit_id"])
    reported = client.get("/audit", headers=_ADMIN_HEADERS).json()["queries"][0]

    assert seen == [_REDACTED_PROMPT]                       # 1. outbound  -> masked
    assert body["response"] == _REDACTED_RESPONSE           # 2. caller    -> masked
    assert entry.prompt_preview == _PII_PROMPT              # 3. audit     -> raw
    assert entry.response_preview == _PII_RESPONSE          # 3. audit     -> raw
    assert reported["audit_id"] == body["audit_id"]         # 4. same row, and it agrees:
    assert reported["pii_entities"] == body["pii_entities_masked"] == _EXPECTED_ENTITIES
    assert body["pii_redacted"] is (
        reported["pii_detected_input"] or reported["pii_detected_output"]
    )


def test_redaction_disabled_passes_both_directions_through_unmasked(temp_db, monkeypatch):
    """AC5: the config toggle from STORY-001, proven on every surface at once."""
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)

    response, seen = _post_pii_query(monkeypatch)
    body = response.json()
    entry = get_audit_log(body["audit_id"])
    reported = client.get("/audit", headers=_ADMIN_HEADERS).json()["queries"][0]
    stats = client.get("/stats", headers=_ADMIN_HEADERS).json()

    assert response.status_code == 200
    assert seen == [_PII_PROMPT]                  # outbound: raw, nothing masked
    assert body["response"] == _PII_RESPONSE      # caller:   raw
    assert body["pii_redacted"] is False
    assert body["pii_entities_masked"] == []
    assert entry.prompt_preview == _PII_PROMPT    # audit:    unchanged either way
    assert entry.response_preview == _PII_RESPONSE
    assert entry.pii_detected_input is False
    assert entry.pii_detected_output is False
    assert entry.pii_entities is None
    assert reported["pii_detected_input"] is False
    assert reported["pii_entities"] == []
    assert stats["pii_detected_queries"] == 0
    assert stats["top_pii_entities"] == []


_PRE_EPIC_UNTOUCHED_TESTS = [
    "tests/test_admin_auth.py",
    "tests/test_duplicate_checker.py",
    "tests/test_openrouter_client.py",
    "tests/test_pattern_detector.py",
    "tests/test_route_reservations.py",
]

# STORY-013 (PRD-005 Section 9/10) makes POST /query require a bearer credential and
# refuses a body user_id that doesn't match it -- a deliberate, documented breaking
# change to the pre-RBAC contract. tests/test_integration.py posts as two different
# users in a single test (PRD-001 Section 5's happy-path/dup/pattern coverage), so it
# had to gain per-request Authorization headers rather than staying untouched.
_TEST_DEF = re.compile(r"^def (test_\w+)", re.MULTILINE)


def _git(*args):
    """Run a git command at the repo root; None when git/history is unavailable."""
    try:
        result = subprocess.run(
            ["git", *args], cwd=_REPO_ROOT, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def _epic_base():
    base = _git("merge-base", "main", "HEAD")
    return base.strip() if base and base.strip() else None


@pytest.mark.parametrize("path", _PRE_EPIC_UNTOUCHED_TESTS)
def test_pre_epic_test_files_are_unmodified_by_this_epic(path):
    """AC4, layer 1: the PRD-001 suites this epic never needed to open."""
    base = _epic_base()
    if base is None:
        pytest.skip("git history unavailable; the census pin below still applies")

    changed = _git("diff", "--name-only", base, "--", path)
    assert changed is not None, f"git diff failed for {path}"
    assert [line for line in changed.splitlines() if line.strip()] == []


# Test functions whose entire premise was the pre-RBAC contract and that STORY-013
# deliberately superseded (not an accidental deletion -- see the comment above
# _PRE_EPIC_UNTOUCHED_TESTS). Each was replaced by a same-file test asserting the new,
# PRD-005-documented behavior:
#   - QueryRequest.user_id is now Optional[str] = None (app/models/schemas.py), so a
#     request without it no longer raises ValidationError -- replaced by
#     test_query_request_missing_user_id_defaults_to_none.
#   - POST /query without a body user_id is no longer a 422/400 validation error --
#     it's now the AC4 "proceeds using the credential's user_id" case, replaced by
#     test_body_user_id_absent_proceeds_with_credential_user_id and
#     test_missing_authorization_header_returns_401_and_no_audit_row.
#
# STORY-014 (PRD-005 Section 6/9, Risk 5) replaces the free-text user_id prompt with a
# real token login: ChatState.submit_user_id()/reset_user_id() become login()/logout().
# Each superseded test was replaced by a same-file test asserting the new,
# token-based behavior:
#   - test_chat_state_submit_empty_or_whitespace_user_id_shows_error ->
#     test_chat_state_login_empty_token_shows_error
#   - test_chat_state_submit_valid_user_id_clears_error_and_sets_user ->
#     test_chat_state_login_valid_token_sets_user_id_and_clears_error
#   - test_chat_state_reset_user_id_clears_error -> folded into
#     test_chat_state_logout_clears_session_and_credential
#   - test_reset_user_id_clears_the_transcript -> test_logout_clears_the_transcript
_DELIBERATELY_SUPERSEDED_TESTS = {
    "tests/test_schemas.py": {"test_query_request_missing_user_id_raises"},
    "tests/test_query_router.py": {
        "test_missing_user_id_returns_422",
        "test_empty_user_id_returns_400_before_any_side_effect",
    },
    "tests/test_chat_state.py": {
        "test_chat_state_submit_empty_or_whitespace_user_id_shows_error",
        "test_chat_state_submit_valid_user_id_clears_error_and_sets_user",
        "test_chat_state_reset_user_id_clears_error",
        "test_reset_user_id_clears_the_transcript",
    },
}


def test_no_pre_epic_test_function_was_removed_or_renamed():
    """AC4, layer 2: catches a deletion inside a file the epic legitimately extended."""
    base = _epic_base()
    if base is None:
        pytest.skip("git history unavailable")

    listing = _git("ls-tree", "-r", "--name-only", base, "tests/")
    assert listing is not None, "git ls-tree failed"

    missing = {}
    for path in listing.split():
        if not path.endswith(".py"):
            continue
        base_source = _git("show", f"{base}:{path}")
        assert base_source is not None, f"git show failed for {path}"
        current = _REPO_ROOT / path
        current_source = current.read_text(encoding="utf-8") if current.exists() else ""
        gone = set(_TEST_DEF.findall(base_source)) - set(_TEST_DEF.findall(current_source))
        gone -= _DELIBERATELY_SUPERSEDED_TESTS.get(path, set())
        if gone:
            missing[path] = sorted(gone)

    assert missing == {}
