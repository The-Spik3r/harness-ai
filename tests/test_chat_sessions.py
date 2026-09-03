"""The six chat_sessions functions from PRD-008 STORY-004.

STORY-005 extends **this file** with the message-store round trips
(`append_chat_message`, `list_chat_messages`, `count_chat_sessions`) -- add to it
rather than opening a third suite over the same two tables.

What this file does not do is enumerate the ownership rule structurally for the
whole surface. STORY-007 owns `tests/test_session_ownership.py`, which discovers
every `*_chat_session*` / `*_chat_message*` callable and asserts the rule against
whatever it finds; the signature assertions here are STORY-004's own six, named,
so that this story is verifiable before that one exists. One rule, two scopes,
deliberately not one copy-paste.
"""

import ast
import inspect
import uuid
from datetime import datetime

import pytest

from app.db import database
from app.db.database import (
    _TIMESTAMP_FORMAT,
    count_audit_logs,
    create_chat_session,
    delete_chat_session,
    get_chat_session,
    get_connection,
    insert_audit_log,
    insert_user,
    list_chat_sessions,
    rename_chat_session,
    touch_chat_session,
)
from app.db.models import AuditLog, ChatSession, User

#: The surface this story adds, in the order PRD Section 4 lists it.
THE_SIX = (
    "create_chat_session",
    "get_chat_session",
    "list_chat_sessions",
    "rename_chat_session",
    "touch_chat_session",
    "delete_chat_session",
)


def _statements_of(name: str) -> str:
    """The named function's body with its docstring removed.

    Through `ast` because the prose in these docstrings quotes the very SQL
    fragment the assertion looks for, and because two of the functions carry
    triple-quoted SQL literals that defeat splitting on quote characters.
    """
    tree = ast.parse(inspect.getsource(getattr(database, name)))
    body = tree.body[0].body
    if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return "\n".join(ast.unparse(node) for node in body)


def _seed_users() -> None:
    """Two real users, so a foreign id in a test is a foreign id that exists.

    A test that drives a read with `"bob"` when no bob row exists proves less
    than one where bob is a genuine account: the first can pass because the id
    is unknown, the second only passes because the `WHERE` clause scopes.
    """
    insert_user(User(user_id="ana", role="user", token_hash="hash-ana"))
    insert_user(User(user_id="bob", role="user", token_hash="hash-bob"))


def _set_updated_at(session_id: str, value: str) -> None:
    """Backdates a row directly.

    `touch_chat_session` writes `now` and nothing else, so ordering tests need a
    way to place rows at known, distinct timestamps -- second-resolution TEXT
    means three sessions created in one test would otherwise tie.
    """
    with get_connection() as conn:
        conn.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE session_id = ?",
            (value, session_id),
        )


def _add_message(session_id: str, content: str) -> None:
    """One `chat_messages` row, written directly.

    Deliberately not through `append_chat_message`: that function is STORY-005
    and does not exist yet, and STORY-004's delete semantics must be verifiable
    without it.
    """
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO chat_messages (session_id, kind, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, "user", content, "2026-09-03T10:00:00Z"),
        )


def _count_messages(session_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM chat_messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row["n"]


# --------------------------------------------------------------------------
# AC 1 and AC 2 -- the rule as a property of the module, not of a call
# --------------------------------------------------------------------------


def test_the_six_functions_are_declared():
    """AC 1. No database needed: this is a statement about the module."""
    for name in THE_SIX:
        assert hasattr(database, name), name
        assert callable(getattr(database, name)), name


def test_every_signature_requires_an_undefaulted_user_id():
    """AC 2, and the mitigation PRD Risk 2 names verbatim: "the rule lives in
    the signature -- `user_id` is required and undefaulted on every
    session-scoped function, so an omission is a `TypeError` at the call site
    rather than a leak at runtime."""
    for name in THE_SIX:
        parameters = inspect.signature(getattr(database, name)).parameters
        assert "user_id" in parameters, name
        user_id = parameters["user_id"]
        assert user_id.default is inspect.Parameter.empty, name
        assert user_id.annotation is str, name
        assert user_id.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD, name


def test_omitting_user_id_is_a_type_error_not_a_wider_read():
    """The consequence the previous test asserts structurally, exercised. This
    is the difference between a leak and a crash, so it gets its own case."""
    for name in THE_SIX:
        with pytest.raises(TypeError):
            getattr(database, name)()


def test_every_statement_over_existing_rows_scopes_on_user_id():
    """AC 2, the SQL half. A signature that takes `user_id` and never puts it in
    a `WHERE` clause satisfies the test above and still returns everyone's rows,
    which is exactly the silent failure Risk 2 describes.

    `create_chat_session` is excluded because it *cannot* satisfy this: an
    INSERT has no `WHERE` clause. Ownership there is carried by the column it
    writes, which the next test asserts instead. Splitting the two is the honest
    reading of AC 2 -- the criterion is about statements that reach existing
    rows, and there is exactly one statement in this story that does not.

    The docstring is stripped through `ast` rather than by splitting on quotes:
    several of these docstrings quote `WHERE user_id = ?` while explaining the
    rule, so a test that read the prose would be no test at all -- and two of
    the functions hold triple-quoted SQL of their own, which is what a naive
    split gets wrong.
    """
    for name in THE_SIX:
        if name == "create_chat_session":
            continue
        assert "user_id = ?" in _statements_of(name), name


def test_create_writes_the_owner_onto_the_row(temp_db):
    """The other half of AC 2, for the one statement that has no `WHERE`. If the
    INSERT dropped `user_id` the column is NOT NULL, so this fails loudly -- but
    a wrong-value write would not, hence reading it back."""
    _seed_users()

    session_id = create_chat_session("ana", "Owned")

    with get_connection() as conn:
        row = conn.execute(
            "SELECT user_id FROM chat_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    assert row["user_id"] == "ana"


# --------------------------------------------------------------------------
# AC 8 -- create
# --------------------------------------------------------------------------


def test_create_returns_a_uuid4_string_that_get_retrieves(temp_db):
    """AC 8. The retrieval is a separate call on purpose: `create` returning an
    id it never wrote would pass a test that only inspected its return value."""
    _seed_users()

    session_id = create_chat_session("ana", "Vendor spend")

    assert uuid.UUID(session_id).version == 4

    session = get_chat_session(session_id, "ana")
    assert isinstance(session, ChatSession)
    assert session.session_id == session_id
    assert session.user_id == "ana"
    assert session.title == "Vendor spend"


def test_create_does_not_accept_a_caller_supplied_id(temp_db):
    """PRD Risk 3: `active_session_id` is a client-visible Reflex var. The
    defence is that the signature has nowhere to put one."""
    assert "session_id" not in inspect.signature(create_chat_session).parameters


def test_create_stamps_created_at_and_updated_at_together(temp_db):
    """Both from one `now`, in the module's one timestamp format. Two separate
    `datetime.now()` calls can straddle a second boundary and leave a new
    session sorting below itself."""
    _seed_users()

    session = get_chat_session(create_chat_session("ana", "First"), "ana")

    assert session.created_at == session.updated_at
    datetime.strptime(session.created_at, _TIMESTAMP_FORMAT)


def test_create_gives_two_sessions_distinct_ids(temp_db):
    _seed_users()

    first = create_chat_session("ana", "First")
    second = create_chat_session("ana", "Second")

    assert first != second


# --------------------------------------------------------------------------
# AC 3 -- get
# --------------------------------------------------------------------------


def test_get_chat_session_returns_none_for_a_foreign_owner(temp_db):
    """AC 3. And the second assertion is the point: the foreign-owner answer is
    indistinguishable from the unknown-id answer, so a caller cannot use this
    function to learn that somebody else's session exists."""
    _seed_users()
    session_id = create_chat_session("ana", "Vendor spend")

    assert get_chat_session(session_id, "bob") is None
    assert get_chat_session("no-such-session", "bob") is None
    assert get_chat_session(session_id, "ana") is not None


# --------------------------------------------------------------------------
# AC 4 -- list
# --------------------------------------------------------------------------


def test_list_orders_by_updated_at_desc_and_caps_at_limit(temp_db):
    """AC 4. The rows are backdated explicitly because second-resolution TEXT
    timestamps would tie three sessions created inside one test."""
    _seed_users()
    oldest = create_chat_session("ana", "Oldest")
    middle = create_chat_session("ana", "Middle")
    newest = create_chat_session("ana", "Newest")
    _set_updated_at(oldest, "2026-09-01T09:00:00Z")
    _set_updated_at(middle, "2026-09-02T09:00:00Z")
    _set_updated_at(newest, "2026-09-03T09:00:00Z")

    listed = list_chat_sessions("ana")
    assert [s.session_id for s in listed] == [newest, middle, oldest]

    assert [s.session_id for s in list_chat_sessions("ana", limit=2)] == [
        newest,
        middle,
    ]


def test_list_never_returns_another_users_rows(temp_db):
    """AC 4, the half that matters. Note bob genuinely has a session -- a test
    where the foreign user owns nothing cannot tell a scoped read from a broken
    one that happens to return an empty table."""
    _seed_users()
    create_chat_session("ana", "Ana one")
    create_chat_session("ana", "Ana two")
    bobs = create_chat_session("bob", "Bob one")

    assert [s.session_id for s in list_chat_sessions("bob")] == [bobs]
    assert len(list_chat_sessions("ana")) == 2
    assert list_chat_sessions("nobody") == []


def test_list_returns_empty_rather_than_raising_for_an_unknown_user(temp_db):
    """The rail asks before it knows whether the user has ever sent anything."""
    assert list_chat_sessions("ana") == []


# --------------------------------------------------------------------------
# AC 5 -- rename and touch
# --------------------------------------------------------------------------


def test_rename_returns_true_when_owned_and_false_otherwise(temp_db):
    """AC 5. The foreign case asserts the title too: a `False` return with the
    write already applied would be the worst of both answers."""
    _seed_users()
    session_id = create_chat_session("ana", "Original")

    assert rename_chat_session(session_id, "ana", "Renamed") is True
    assert get_chat_session(session_id, "ana").title == "Renamed"

    assert rename_chat_session("no-such-session", "ana", "Ghost") is False

    assert rename_chat_session(session_id, "bob", "Stolen") is False
    assert get_chat_session(session_id, "ana").title == "Renamed"


def test_rename_to_the_same_title_still_returns_true(temp_db):
    """`rowcount` counts matched rows, not changed ones -- the property
    `test_deactivate_user_is_idempotent` already pins for `deactivate_user`.
    Documented here so nobody "fixes" it into False later."""
    _seed_users()
    session_id = create_chat_session("ana", "Same")

    assert rename_chat_session(session_id, "ana", "Same") is True


def test_rename_leaves_updated_at_alone(temp_db):
    """Renaming is not activity. A rename that bumped `updated_at` would
    reorder the rail and move the row the user was just looking at."""
    _seed_users()
    session_id = create_chat_session("ana", "Original")
    _set_updated_at(session_id, "2026-09-01T09:00:00Z")

    rename_chat_session(session_id, "ana", "Renamed")

    assert get_chat_session(session_id, "ana").updated_at == "2026-09-01T09:00:00Z"


def test_touch_moves_updated_at_and_returns_true(temp_db):
    """AC 5. `created_at` must not move with it -- the rail sorts on one and
    reports the other."""
    _seed_users()
    session_id = create_chat_session("ana", "Active")
    created_at = get_chat_session(session_id, "ana").created_at
    _set_updated_at(session_id, "2026-09-01T09:00:00Z")

    assert touch_chat_session(session_id, "ana") is True

    touched = get_chat_session(session_id, "ana")
    assert touched.updated_at > "2026-09-01T09:00:00Z"
    assert touched.created_at == created_at
    datetime.strptime(touched.updated_at, _TIMESTAMP_FORMAT)


def test_touch_returns_false_for_unknown_or_foreign(temp_db):
    """AC 5. The zero-row case, and the foreign row must not move."""
    _seed_users()
    session_id = create_chat_session("ana", "Active")
    _set_updated_at(session_id, "2026-09-01T09:00:00Z")

    assert touch_chat_session("no-such-session", "ana") is False
    assert touch_chat_session(session_id, "bob") is False
    assert get_chat_session(session_id, "ana").updated_at == "2026-09-01T09:00:00Z"


def test_touch_does_not_rename(temp_db):
    _seed_users()
    session_id = create_chat_session("ana", "Titled")

    touch_chat_session(session_id, "ana")

    assert get_chat_session(session_id, "ana").title == "Titled"


# --------------------------------------------------------------------------
# AC 6 and AC 7 -- delete
# --------------------------------------------------------------------------


def test_delete_removes_the_session_and_its_messages(temp_db):
    """AC 6. The messages are written directly rather than through
    `append_chat_message`, which is STORY-005 and must not be a dependency of
    STORY-004 being correct."""
    _seed_users()
    session_id = create_chat_session("ana", "Doomed")
    _add_message(session_id, "first")
    _add_message(session_id, "second")
    assert _count_messages(session_id) == 2

    assert delete_chat_session(session_id, "ana") is True

    assert get_chat_session(session_id, "ana") is None
    assert _count_messages(session_id) == 0


def test_delete_leaves_other_sessions_and_their_messages_alone(temp_db):
    """One session deleted is one session deleted, including when the owner has
    others."""
    _seed_users()
    doomed = create_chat_session("ana", "Doomed")
    kept = create_chat_session("ana", "Kept")
    _add_message(doomed, "gone")
    _add_message(kept, "still here")

    delete_chat_session(doomed, "ana")

    assert get_chat_session(kept, "ana") is not None
    assert _count_messages(kept) == 1


def test_delete_returns_false_for_an_unknown_session(temp_db):
    _seed_users()

    assert delete_chat_session("no-such-session", "ana") is False


def test_delete_leaves_audit_logs_untouched(temp_db):
    """AC 6. PRD Section 9: "the orphaned `session_id` on those rows is
    expected, and it is what preserves the evidence when a user tidies their
    list." Asserted by counting across the call rather than by trusting that no
    statement in the function mentions the table."""
    _seed_users()
    session_id = create_chat_session("ana", "Doomed")
    _add_message(session_id, "hello")
    insert_audit_log(
        AuditLog(timestamp="2026-09-03T10:00:00Z", user_id="ana", prompt_hash="h1")
    )
    insert_audit_log(
        AuditLog(timestamp="2026-09-03T10:00:01Z", user_id="ana", prompt_hash="h2")
    )
    before = count_audit_logs()
    assert before == 2

    delete_chat_session(session_id, "ana")

    assert count_audit_logs() == before


def test_delete_with_a_foreign_user_deletes_nothing(temp_db):
    """AC 7, the criterion this story exists for.

    `chat_messages` has no `user_id` column, so a message delete scoped by
    `session_id` alone would wipe the owner's transcript here while still
    returning False -- the return value is precisely what cannot be trusted to
    prove this, which is why the rows are counted directly."""
    _seed_users()
    session_id = create_chat_session("ana", "Ana private")
    _add_message(session_id, "first")
    _add_message(session_id, "second")

    assert delete_chat_session(session_id, "bob") is False

    assert get_chat_session(session_id, "ana") is not None
    assert _count_messages(session_id) == 2


def test_delete_with_a_foreign_user_leaves_audit_logs_untouched(temp_db):
    """The refused path writes nothing at all, to either table."""
    _seed_users()
    session_id = create_chat_session("ana", "Ana private")
    insert_audit_log(
        AuditLog(timestamp="2026-09-03T10:00:00Z", user_id="ana", prompt_hash="h1")
    )

    delete_chat_session(session_id, "bob")

    assert count_audit_logs() == 1


# --------------------------------------------------------------------------
# AC 9 -- every path, driven with the other user's id
# --------------------------------------------------------------------------


def test_two_users_see_nothing_of_each_others_sessions(temp_db):
    """AC 9. Every read and write path in this story, driven with the wrong id,
    in one place -- so that a seventh function added without a `WHERE` clause
    has somewhere obvious to fail."""
    _seed_users()
    ana_session = create_chat_session("ana", "Ana private")
    _add_message(ana_session, "ana said this")
    bob_session = create_chat_session("bob", "Bob private")

    # Reads.
    assert get_chat_session(ana_session, "bob") is None
    assert get_chat_session(bob_session, "ana") is None
    assert [s.session_id for s in list_chat_sessions("bob")] == [bob_session]
    assert [s.session_id for s in list_chat_sessions("ana")] == [ana_session]

    # Writes.
    assert rename_chat_session(ana_session, "bob", "Bob was here") is False
    assert touch_chat_session(ana_session, "bob") is False
    assert delete_chat_session(ana_session, "bob") is False

    # And nothing bob attempted changed anything of ana's.
    survivor = get_chat_session(ana_session, "ana")
    assert survivor is not None
    assert survivor.title == "Ana private"
    assert _count_messages(ana_session) == 1
