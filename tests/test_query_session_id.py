"""`session_id` over `POST /query` -- PRD-008 STORY-010.

The API boundary is the only place a `session_id` arrives from outside the
process, and each of the three answers it can get there is a security-visible
decision:

- **accepted** -- the id joins the audit row, and the record can be grouped by
  conversation for the first time;
- **422** -- the value is not a canonical UUID4, refused by the request model
  before any handler runs;
- **403** -- the id names a session that is not the caller's, refused *and
  audited*, with the foreign session and the nonexistent one answered
  identically so the endpoint is not a membership oracle over other people's
  session ids.

Two of those are new refusals in a system whose founding property (PRD-001) is
that a rejected send is recorded with the same rigour as an accepted one, which
is why AC 6 gets its own section below rather than riding along on the 403's
status code.

The prologue is copied from `tests/test_query_router.py` rather than imported:
STORY-010 AC 8 requires that file to pass **unmodified**, and importing from it
would make it a module this suite depends on -- a coupling that turns any later
edit there into a failure here.

Offline like the rest of the suite: the only fixture is `temp_db` from
`tests/conftest.py`, and `call_openrouter` is always patched.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import ast
import pathlib
import subprocess
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import get_audit_log, get_connection, insert_user
from app.db.models import User
from app.main import app
from app.services import chat_sessions
from app.services.identity import Identity, hash_token
from app.services.openrouter_client import OpenRouterResult

_AUTH_USER_ID = "juan@empresa.com"
_AUTH_TOKEN = "test-user-token"
_AUTH_HEADERS = {"Authorization": f"Bearer {_AUTH_TOKEN}"}

_OTHER_USER_ID = "ana@empresa.com"
_OTHER_TOKEN = "other-user-token"

_FOREIGN_SESSION_DETAIL = "session_id does not belong to the authenticated identity"

client = TestClient(app, headers=_AUTH_HEADERS)


@pytest.fixture
def temp_db(temp_db):
    """conftest's initialized database, plus this suite's two authenticated users.

    Both are genuine accounts with real credentials, for the reason
    `tests/test_session_ownership.py` records: driving a refusal with a user who
    does not exist proves less than driving it with one who does, because the
    first can pass merely because the id is unknown.
    """
    insert_user(User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN)))
    insert_user(User(user_id=_OTHER_USER_ID, role="user", token_hash=hash_token(_OTHER_TOKEN)))
    return temp_db


def _count_audit_rows() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]


def _last_audit_row():
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
    return get_audit_log(row["id"])


def _fail_if_called(*args, **kwargs):
    raise AssertionError("call_openrouter should not have been called")


def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
    return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)


def _session_owned_by(user_id: str) -> str:
    """One session belonging to `user_id`, created through the service."""
    identity = Identity(user_id=user_id, role="user")
    session_id = chat_sessions.create(identity, "the quarterly close", lambda text: text)
    assert session_id is not None
    return session_id


# --------------------------------------------------------------------------
# AC 2 -- the omitted field is the current release, exactly
# --------------------------------------------------------------------------


def test_a_request_without_session_id_still_succeeds_and_writes_null(temp_db, monkeypatch):
    """AC 2. The compatibility promise PRD Section 3 makes to the integrating
    developer: "a client that omits it behaves exactly as it does today"."""
    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)

    response = client.post("/query", json={"prompt": "hello world"})

    assert response.status_code == 200
    assert get_audit_log(response.json()["audit_id"]).session_id is None


def test_omitting_session_id_leaves_the_rest_of_the_audit_row_identical(temp_db, monkeypatch):
    """AC 2's "the audit row [is] identical to the current release", asserted
    rather than assumed.

    Two sends on distinct prompts -- distinct so the second is not held as a
    duplicate -- must agree on every field except the ones that are *supposed*
    to differ. A `session_id` that quietly changed `role` or `pii_entities` on
    the way past would satisfy a test that only looked at `session_id`.
    """
    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)
    session_id = _session_owned_by(_AUTH_USER_ID)

    without = client.post("/query", json={"prompt": "first question"})
    with_id = client.post("/query", json={"prompt": "second question", "session_id": session_id})

    assert (without.status_code, with_id.status_code) == (200, 200)
    a = get_audit_log(without.json()["audit_id"])
    b = get_audit_log(with_id.json()["audit_id"])

    shared = (
        "user_id",
        "device",
        "model_used",
        "tokens_used",
        "success",
        "role",
        "denied_permission",
        "pii_detected_input",
        "pii_detected_output",
        "pii_entities",
        "was_duplicate_blocked",
        "suspicious_pattern",
        "error_message",
    )
    for field in shared:
        assert getattr(a, field) == getattr(b, field), field

    assert a.session_id is None
    assert b.session_id == session_id


# --------------------------------------------------------------------------
# AC 3 -- malformed is a 422, not a 500 and not a silently ignored field
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "not-a-uuid",
        "",
        "0f6c2e5a9b3d4c81a7f21d5e8c9b0a34",
        "{0f6c2e5a-9b3d-4c81-a7f2-1d5e8c9b0a34}",
        "urn:uuid:0f6c2e5a-9b3d-4c81-a7f2-1d5e8c9b0a34",
        "0F6C2E5A-9B3D-4C81-A7F2-1D5E8C9B0A34",
    ],
    ids=["not-a-uuid", "empty", "unhyphenated", "braced", "urn", "uppercase"],
)
def test_a_malformed_session_id_is_a_422_from_validation(temp_db, monkeypatch, value):
    """AC 3, end to end. Not a 500 -- the refusal comes from the request model
    before any handler runs -- and not silently ignored.

    No audit row either: a request refused before it is a request was never a
    send, so there is nothing for the record to hold. That is the line between
    this and the 403 below, which *was* a send and *is* recorded.
    """
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    response = client.post("/query", json={"prompt": "hello world", "session_id": value})

    assert response.status_code == 422
    assert _count_audit_rows() == 0


def test_a_version_1_uuid_is_also_a_422(temp_db, monkeypatch):
    """AC 1's "UUID4" taken literally. `create_chat_session` mints
    `str(uuid.uuid4())` and accepts no caller-supplied id, so a v1 value -- which
    parses, and which carries a MAC address and a timestamp -- is not an id this
    system ever issued."""
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    response = client.post(
        "/query", json={"prompt": "hello world", "session_id": str(uuid.uuid1())}
    )

    assert response.status_code == 422


def test_a_malformed_session_id_names_the_field_in_the_422_body(temp_db, monkeypatch):
    """The integrating developer is told *which* field, not merely that
    something failed."""
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    response = client.post("/query", json={"prompt": "hello world", "session_id": "nope"})

    assert response.status_code == 422
    assert any("session_id" in entry["loc"] for entry in response.json()["detail"])


def test_a_non_string_session_id_is_also_a_422(temp_db, monkeypatch):
    """The field must not be reachable only by strings that happen to parse: a
    JSON number is refused by the type before the validator is consulted."""
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    response = client.post("/query", json={"prompt": "hello world", "session_id": 12345})

    assert response.status_code == 422
    assert _count_audit_rows() == 0


# --------------------------------------------------------------------------
# AC 4 and AC 5 -- the foreign session and the unknown one, refused identically
# --------------------------------------------------------------------------


def test_a_session_owned_by_another_identity_is_a_403_with_the_exact_detail(
    temp_db, monkeypatch
):
    """AC 4. The detail string is fixed verbatim by the story, so it is asserted
    verbatim: it is the contract an integrating developer reads."""
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
    foreign = _session_owned_by(_OTHER_USER_ID)

    response = client.post("/query", json={"prompt": "hello world", "session_id": foreign})

    assert response.status_code == 403
    assert response.json()["detail"] == _FOREIGN_SESSION_DETAIL


def test_a_session_that_does_not_exist_is_the_same_403(temp_db, monkeypatch):
    """AC 5, asserted as an *equality between the two responses* rather than as
    two separate lookups.

    The claim is not "both are 403". It is that the caller cannot tell the two
    apart -- "None covers every failure case alike ... so the caller cannot
    distinguish them" (`app/services/identity.py`). A test that checked each
    status in isolation would still pass if one of them grew a distinguishing
    detail, which is precisely the leak.
    """
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
    foreign = _session_owned_by(_OTHER_USER_ID)

    refused_foreign = client.post(
        "/query", json={"prompt": "hello world", "session_id": foreign}
    )
    refused_unknown = client.post(
        "/query", json={"prompt": "hello world", "session_id": str(uuid.uuid4())}
    )

    assert refused_unknown.status_code == refused_foreign.status_code == 403
    assert refused_unknown.json() == refused_foreign.json()


def test_the_refused_request_never_reaches_openrouter(temp_db, monkeypatch):
    """A refusal that still paid for a completion would be a refusal in name
    only. `_fail_if_called` is the assertion; both arms are driven through it."""
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
    foreign = _session_owned_by(_OTHER_USER_ID)

    assert client.post("/query", json={"prompt": "a", "session_id": foreign}).status_code == 403
    assert (
        client.post(
            "/query", json={"prompt": "b", "session_id": str(uuid.uuid4())}
        ).status_code
        == 403
    )


def test_the_owner_of_the_session_is_not_refused(temp_db, monkeypatch):
    """The control. Every assertion above is satisfied by a router that refuses
    every `session_id` it is given, so the owned case is driven too -- and the
    id must reach the audit row, which is the whole point of accepting it."""
    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)
    own = _session_owned_by(_AUTH_USER_ID)

    response = client.post("/query", json={"prompt": "hello world", "session_id": own})

    assert response.status_code == 200
    assert get_audit_log(response.json()["audit_id"]).session_id == own


# --------------------------------------------------------------------------
# AC 6 -- the refusal is in the record
# --------------------------------------------------------------------------


def test_the_403_writes_one_audit_row_naming_the_refusal(temp_db, monkeypatch):
    """AC 6, and PRD-001's founding property: a rejected send is logged with the
    same rigour as an accepted one.

    Exactly one row, not zero and not two. `user_id` is the credential's and
    never the body's -- the rule PRD-005 wrote and this story does not relax --
    and the attempted `session_id` is on the row, because recording *what was
    attempted* is the entire evidentiary value of auditing a refusal.

    `success is False` with the reason in `error_message` rather than `_deny`'s
    `success=True`: no permission was denied here (RBAC passed and admitted the
    request), so `denied_permission` would be a lie, and a `success=True` row
    with no permission would be indistinguishable from an ordinary send.
    """
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
    foreign = _session_owned_by(_OTHER_USER_ID)
    before = _count_audit_rows()

    response = client.post(
        "/query", json={"prompt": "the refused question", "session_id": foreign}
    )

    assert response.status_code == 403
    assert _count_audit_rows() == before + 1

    row = _last_audit_row()
    assert row.success is False
    assert row.error_message == _FOREIGN_SESSION_DETAIL
    assert row.user_id == _AUTH_USER_ID
    assert row.role == "user"
    assert row.denied_permission is None
    assert row.session_id == foreign


def test_the_unknown_session_refusal_is_audited_too(temp_db, monkeypatch):
    """AC 5 and AC 6 together. The two refusals are indistinguishable to the
    caller and equally recorded for the admin -- indistinguishability is a
    property of the *response*, never of the record."""
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
    unknown = str(uuid.uuid4())

    response = client.post("/query", json={"prompt": "hello world", "session_id": unknown})

    assert response.status_code == 403
    assert _count_audit_rows() == 1
    assert _last_audit_row().session_id == unknown


def test_the_user_id_mismatch_403_still_writes_no_row(temp_db, monkeypatch):
    """The asymmetry, pinned here on purpose.

    The `user_id` mismatch check beside this story's is older and writes no
    audit row; `tests/test_query_router.py` has asserted that since PRD-005 and
    must pass unmodified. Someone will eventually notice the two arms disagree
    and reach to unify them -- this test says which way the existing decision
    goes, in the file that added the second arm.
    """
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    response = client.post(
        "/query", json={"user_id": "someone-else", "prompt": "hello world"}
    )

    assert response.status_code == 403
    assert _count_audit_rows() == 0


# --------------------------------------------------------------------------
# AC 7 -- the flag governs the transcript, not the audit column
# --------------------------------------------------------------------------


def test_history_off_makes_the_ownership_check_a_no_op(temp_db, monkeypatch):
    """AC 7. With persistence off there are no `chat_sessions` rows for anybody,
    so there is no ownership to assert and nothing to refuse.

    The id used here belongs to another user *when the flag is on*, which is
    what makes this a test of the no-op rather than of an unknown id.
    """
    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)
    foreign = _session_owned_by(_OTHER_USER_ID)
    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)

    response = client.post("/query", json={"prompt": "hello world", "session_id": foreign})

    assert response.status_code == 200


def test_history_off_writes_the_supplied_id_verbatim(temp_db, monkeypatch):
    """AC 7's second half: "the id is written to the audit row as supplied".

    Asserted with `==` against the string that was sent, so a normalizing or
    re-parsing implementation -- one that stored `str(uuid.UUID(value))` -- fails
    here rather than shipping a second spelling of the id into the column the
    admin joins on.
    """
    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)
    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)
    supplied = str(uuid.uuid4())

    response = client.post("/query", json={"prompt": "hello world", "session_id": supplied})

    assert response.status_code == 200
    assert get_audit_log(response.json()["audit_id"]).session_id == supplied


def test_history_off_still_validates_the_uuid(temp_db, monkeypatch):
    """AC 7's boundary. Validation is a property of the request model, and the
    flag has no reach into it: an unparseable id is a 422 whether or not any
    transcript is being kept."""
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)

    response = client.post("/query", json={"prompt": "hello world", "session_id": "not-a-uuid"})

    assert response.status_code == 422


# --------------------------------------------------------------------------
# AC 8, and the structural guard
# --------------------------------------------------------------------------

_PINNED_SUITES = (
    "tests/test_query_router.py",
    "tests/test_integration.py",
    "tests/test_route_reservations.py",
)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _git(*args):
    """Run a git command at the repo root; None when git/history is unavailable.

    Copied from `tests/test_untouched_app.py`, including its skip contract: a
    checkout without git history must not fail this suite, because the assertion
    is about provenance and provenance is simply unverifiable there.
    """
    try:
        result = subprocess.run(
            ["git", *args], cwd=_REPO_ROOT, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def test_the_three_pinned_suites_are_unmodified_in_the_working_tree():
    """AC 8, turned from a promise into an assertion.

    The story requires `tests/test_query_router.py`, `tests/test_integration.py`
    and `tests/test_route_reservations.py` to pass **unmodified** -- which is a
    claim about the diff, not about the exit code, and running them green proves
    only half of it. A story that quietly relaxed one of their assertions to
    accommodate `session_id` would still be green.
    """
    unstaged = _git("diff", "--name-only")
    staged = _git("diff", "--cached", "--name-only")
    if unstaged is None or staged is None:
        pytest.skip("git unavailable; the working tree's provenance is unverifiable here")

    touched = set(unstaged.split()) | set(staged.split())
    assert [s for s in _PINNED_SUITES if s in touched] == []


def test_the_router_never_branches_on_the_history_flag():
    """PRD Section 6: "**No caller branches on the flag.**"

    `tests/test_chat_sessions.py` already asserts this over every module under
    `app/` and `chat_ui/`. It is asserted again here, narrowly, because the
    router is where the temptation actually lives: reaching for AC 7's no-op,
    `if settings.CHAT_HISTORY_ENABLED and not chat_sessions.owns(...)` is the
    first thing anyone writes, and it works. Putting the refusal beside the
    reason means whoever writes it reads why `owns()` exists instead.
    """
    tree = ast.parse((_REPO_ROOT / "app" / "routers" / "query.py").read_text(encoding="utf-8"))

    named = [
        node.lineno
        for node in ast.walk(tree)
        if (isinstance(node, ast.Attribute) and node.attr == "CHAT_HISTORY_ENABLED")
        or (isinstance(node, ast.Name) and node.id == "CHAT_HISTORY_ENABLED")
    ]

    assert named == [], f"app/routers/query.py branches on the flag at lines {named}"
