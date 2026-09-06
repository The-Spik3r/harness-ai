"""The chat store from PRD-008, and the service over it: STORY-004's six
session functions, STORY-005's three message functions, and STORY-006's eight
service functions.

STORY-005 extended **this file** with the message-store round trips
(`append_chat_message`, `list_chat_messages`, `count_chat_sessions`) rather than
opening a third suite over the same two tables, as the STORY-004 docstring here
directed. The two stories' cases are kept in labelled sections below.

What this file does not do is enumerate the ownership rule structurally for the
whole surface. STORY-007 owns `tests/test_session_ownership.py`, which discovers
every `*_chat_session*` / `*_chat_message*` callable and asserts the rule against
whatever it finds; the signature assertions here are STORY-004's own six, named,
so that this story is verifiable before that one exists. One rule, two scopes,
deliberately not one copy-paste.

STORY-006 extended this file a third time, for the same reason STORY-005 did and
because its own AC 9 names this path: the service's cases are about the same two
tables and read against the same fixtures. Its section is labelled below and its
imports come from `app.services.chat_sessions`, so what is being exercised is
never ambiguous.
"""

import ast
import inspect
import pathlib
import uuid
from datetime import datetime

import pytest

from app.config import settings
from app.db import database
from app.db.database import (
    _TIMESTAMP_FORMAT,
    append_chat_message,
    count_audit_logs,
    count_chat_sessions,
    create_chat_session,
    delete_chat_session,
    get_chat_session,
    get_connection,
    insert_audit_log,
    insert_user,
    list_chat_messages,
    list_chat_sessions,
    rename_chat_session,
    touch_chat_session,
)
from app.db.errors import StorageError
from app.db.models import AuditLog, ChatSession, StoredMessage, User
from app.services import chat_sessions
from app.services.chat_sessions import ChatSessionError
from app.services.identity import Identity

#: The surface STORY-004 added, in the order PRD Section 4 lists it.
THE_SIX = (
    "create_chat_session",
    "get_chat_session",
    "list_chat_sessions",
    "rename_chat_session",
    "touch_chat_session",
    "delete_chat_session",
)

#: The surface STORY-005 adds, in the order the story lists it.
THE_THREE = (
    "append_chat_message",
    "list_chat_messages",
    "count_chat_sessions",
)

#: The seven bubble kinds `chat_ui/chat_ui/models.py` renders, each paired with
#: the metadata PRD Section 6's table gives it. Named here rather than inline so
#: that a kind added to the UI without a store round trip is one obvious edit.
#:
#: Deliberately a literal list and not an import from `chat_ui/`: `app/` has
#: never imported the UI package and this story does not start (STORY-005
#: technical notes). Keeping the kinds as strings is what preserves that.
SEVEN_KINDS = (
    ("user", {"prompt": "what is the retention policy?"}),
    ("assistant", {"model_used": "anthropic/claude-3", "tokens_used": 412}),
    ("duplicate", {"first_query_at": "2026-09-03T09:58:00Z"}),
    ("injection", {"pattern": "ignore previous instructions"}),
    ("forbidden", {"required_permission": "query:submit"}),
    ("upstream_error", {"detail": "502 from openrouter"}),
    ("internal_error", {"detail": "unhandled in run_query"}),
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

    Deliberately not through `append_chat_message`. When STORY-004 wrote this
    that function did not exist; now that it does, the helper is **kept** rather
    than replaced, so STORY-004's delete semantics stay verifiable without
    depending on STORY-005's write path. A test that used the new function to set
    up the old one's fixtures would fail for two different reasons and say which
    only by luck. `test_delete_chat_session_removes_messages_written_through_append`
    below asserts the two paths agree.
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


# ==========================================================================
# STORY-005 -- append_chat_message, list_chat_messages, count_chat_sessions
# ==========================================================================


def _stored(session_id: str, kind: str = "user", **overrides) -> StoredMessage:
    """One `StoredMessage` with sane defaults, so a round trip is one call.

    `content` defaults off `kind` rather than to a constant, so a failure message
    names the kind that broke without the test having to say so twice.
    """
    fields = {"session_id": session_id, "kind": kind, "content": f"{kind} content"}
    fields.update(overrides)
    return StoredMessage(**fields)


def _seeded_session(user_id: str = "ana", title: str = "a chat") -> str:
    """Two real users plus one session owned by `user_id`."""
    _seed_users()
    return create_chat_session(user_id, title)


# --------------------------------------------------------------------------
# AC 1, AC 2 and AC 3 -- statements about the module, no database needed
# --------------------------------------------------------------------------


def test_the_three_message_functions_are_declared():
    """AC 1."""
    for name in THE_THREE:
        assert hasattr(database, name), name
        assert callable(getattr(database, name)), name


def test_every_message_signature_requires_an_undefaulted_user_id():
    """AC 2, and PRD Risk 2's mitigation applied to this story's three: the rule
    lives in the signature, so an omission is a `TypeError` at the call site
    rather than a leak at runtime."""
    for name in THE_THREE:
        parameters = inspect.signature(getattr(database, name)).parameters
        assert "user_id" in parameters, name
        user_id = parameters["user_id"]
        assert user_id.default is inspect.Parameter.empty, name
        assert user_id.annotation is str, name
        assert user_id.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD, name


def test_omitting_user_id_is_a_type_error_on_the_message_functions():
    """AC 2, exercised. The difference between a leak and a crash."""
    for name in THE_THREE:
        with pytest.raises(TypeError):
            getattr(database, name)()


def test_every_message_statement_scopes_on_user_id():
    """AC 2, the SQL half.

    **All three, `append_chat_message` included** -- unlike `create_chat_session`,
    which `test_every_statement_over_existing_rows_scopes_on_user_id` above has to
    exclude because a bare INSERT has no `WHERE` clause to put the owner in. This
    story's INSERT carries a `WHERE EXISTS`, so it genuinely scopes and needs no
    exemption. The difference between the two inserts is the point: one mints a
    row it owns by construction, the other writes into a row someone else already
    owns and must prove the caller is that someone.
    """
    for name in THE_THREE:
        assert "user_id = ?" in _statements_of(name), name


def test_list_chat_messages_orders_by_id_and_not_by_a_timestamp():
    """AC 3, as a statement inspection.

    The negative half is the one that catches the regression: an `ORDER BY
    created_at` would still return rows, in an order that looks right in every
    test whose messages land in distinct seconds.
    """
    statements = _statements_of("list_chat_messages")
    assert "ORDER BY id ASC" in statements
    assert "ORDER BY created_at" not in statements
    assert "ORDER BY timestamp" not in statements


def test_list_chat_messages_takes_no_limit_parameter():
    """The story's "do not add a `limit`" note, pinned.

    A partial transcript is a wrong transcript, and nothing on screen would say
    it was partial. PRD Section 4 caps sessions, not messages within one.
    """
    parameters = inspect.signature(list_chat_messages).parameters
    assert set(parameters) == {"session_id", "user_id"}
    assert "LIMIT" not in _statements_of("list_chat_messages")


# --------------------------------------------------------------------------
# AC 4 -- order is the key, not the clock
# --------------------------------------------------------------------------


def test_twenty_messages_appended_in_one_second_read_back_in_order(temp_db):
    """AC 4. Twenty messages sharing one `created_at` to the second.

    This is the case a timestamp sort gets wrong, and the reason AC 3 is written
    as a statement inspection *and* a behavioural test: a sort on a tied column
    is not deterministic, so a passing run proves nothing on its own.
    """
    session_id = _seeded_session()
    one_instant = "2026-09-03T10:00:00Z"
    for index in range(20):
        append_chat_message(
            _stored(session_id, content=f"message {index:02d}", created_at=one_instant),
            session_id,
            "ana",
        )

    restored = list_chat_messages(session_id, "ana")

    assert [message.content for message in restored] == [
        f"message {index:02d}" for index in range(20)
    ]
    assert {message.created_at for message in restored} == {one_instant}


def test_append_returns_the_new_row_id_and_ids_increase(temp_db):
    """The `int` coming back is the row's key, and the key is the order."""
    session_id = _seeded_session()

    first = append_chat_message(_stored(session_id), session_id, "ana")
    second = append_chat_message(_stored(session_id), session_id, "ana")

    assert isinstance(first, int)
    assert second > first
    assert [message.id for message in list_chat_messages(session_id, "ana")] == [
        first,
        second,
    ]


# --------------------------------------------------------------------------
# AC 7 and AC 8 -- every kind, every field
# --------------------------------------------------------------------------


@pytest.mark.parametrize("kind,metadata", SEVEN_KINDS, ids=[k for k, _ in SEVEN_KINDS])
def test_each_of_the_seven_kinds_round_trips_unchanged(temp_db, kind, metadata):
    """AC 7 and AC 8.

    Parametrized rather than looped so that a failure names the kind that broke.
    A single representative kind would pass while `pattern`, `required_permission`
    or `first_query_at` were silently dropped -- each is carried by exactly one
    kind, and a bubble that restores without its metadata renders through the same
    `rx.match` with its evidence missing.
    """
    session_id = _seeded_session()
    written = _stored(session_id, kind, created_at="2026-09-03T10:00:00Z", **metadata)

    append_chat_message(written, session_id, "ana")
    (restored,) = list_chat_messages(session_id, "ana")

    for field_name in (
        "session_id",
        "kind",
        "content",
        "prompt",
        "model_used",
        "tokens_used",
        "audit_id",
        "pii_redacted",
        "pii_entities",
        "pattern",
        "required_permission",
        "first_query_at",
        "detail",
        "created_at",
    ):
        assert getattr(restored, field_name) == getattr(written, field_name), field_name


def test_tokens_used_and_audit_id_round_trip_as_integers(temp_db):
    """AC 7. Integers, and `None` that stays `None`.

    `isinstance` rather than `==` alone: a driver handing back `"412"` compares
    unequal and would be caught, but one handing back `412.0` would not.
    """
    session_id = _seeded_session()
    append_chat_message(
        _stored(session_id, "assistant", tokens_used=1234, audit_id=99),
        session_id,
        "ana",
    )

    (restored,) = list_chat_messages(session_id, "ana")

    assert restored.tokens_used == 1234
    assert isinstance(restored.tokens_used, int)
    assert restored.audit_id == 99
    assert isinstance(restored.audit_id, int)


def test_absent_tokens_used_and_audit_id_read_back_as_none_not_zero(temp_db):
    """The half the previous test cannot cover.

    An `int()` coercion in the row mapper would turn a genuine `NULL` into `0`,
    which reads as "this turn used zero tokens" rather than "this turn never
    called a model" -- and `0` is a legitimate value, so nothing downstream could
    tell the two apart afterwards.
    """
    session_id = _seeded_session()
    append_chat_message(_stored(session_id, "user"), session_id, "ana")

    (restored,) = list_chat_messages(session_id, "ana")

    assert restored.tokens_used is None
    assert restored.audit_id is None


@pytest.mark.parametrize(
    "written,expected",
    [(None, None), ("", None), ("EMAIL,PHONE", "EMAIL,PHONE")],
    ids=["none", "empty-string", "two-entities"],
)
def test_empty_pii_entities_stores_null_and_reads_back_as_none(
    temp_db, written, expected
):
    """AC 7's `pii_entities` clause, and the bug the story names by hand.

    `",".join([])` is `""`, and `"".split(",")` is `[""]` -- one phantom entity on
    a message that had none. It would surface in STORY-015, on the rehydration
    into `ChatMessage`, as a PII badge on a clean bubble. `append_chat_message`
    normalizes `""` to `NULL` so the split upstream is never handed an empty
    string, which is the same guard `app/services/audit_logger.py:45` applies to
    the audit row.
    """
    session_id = _seeded_session()
    append_chat_message(
        _stored(session_id, "assistant", pii_entities=written), session_id, "ana"
    )

    (restored,) = list_chat_messages(session_id, "ana")

    assert restored.pii_entities == expected
    assert restored.pii_entities != ""


def test_pii_redacted_round_trips_as_a_bool(temp_db):
    """The one column the row mapper coerces.

    `is True` / `is False` rather than a truthiness check: the column is INTEGER,
    so a mapper that forgot `bool()` would hand back `1` and pass every `assert
    restored.pii_redacted` ever written.
    """
    session_id = _seeded_session()
    append_chat_message(
        _stored(session_id, "assistant", content="redacted", pii_redacted=True),
        session_id,
        "ana",
    )
    append_chat_message(
        _stored(session_id, "assistant", content="clean", pii_redacted=False),
        session_id,
        "ana",
    )

    redacted, clean = list_chat_messages(session_id, "ana")

    assert redacted.pii_redacted is True
    assert clean.pii_redacted is False


def test_append_stamps_created_at_when_omitted_and_keeps_it_when_given(temp_db):
    """Both arms of `StoredMessage.created_at`'s "stamps it when omitted"."""
    session_id = _seeded_session()
    append_chat_message(_stored(session_id, content="stamped"), session_id, "ana")
    append_chat_message(
        _stored(session_id, content="given", created_at="2020-01-01T00:00:00Z"),
        session_id,
        "ana",
    )

    stamped, given = list_chat_messages(session_id, "ana")

    assert given.created_at == "2020-01-01T00:00:00Z"
    assert stamped.created_at is not None
    # Parses under the module's own format, which is the claim that matters --
    # a stamp in another shape would sort and display wrong everywhere else.
    datetime.strptime(stamped.created_at, _TIMESTAMP_FORMAT)


# --------------------------------------------------------------------------
# AC 5 and AC 6 -- the ownership rule, exercised
# --------------------------------------------------------------------------


def test_list_chat_messages_returns_empty_for_a_foreign_owner(temp_db):
    """AC 5. Empty list, not the rows, and not an exception.

    `bob` is a real account (`_seed_users`), so this passes only because the
    subselect scopes -- not because the id is unknown.
    """
    session_id = _seeded_session()
    for index in range(3):
        append_chat_message(
            _stored(session_id, content=f"m{index}"), session_id, "ana"
        )

    assert list_chat_messages(session_id, "bob") == []
    assert len(list_chat_messages(session_id, "ana")) == 3


def test_append_for_a_foreign_owner_writes_nothing_and_raises(temp_db):
    """AC 6. The failure is visible, and the table is untouched.

    A silent no-op here would look like a working write in STORY-014's degraded
    arm: the bubble stays on screen, no notice appears, and the turn is gone on
    the next reload.
    """
    session_id = _seeded_session()

    with pytest.raises(StorageError):
        append_chat_message(_stored(session_id), session_id, "bob")

    assert _count_messages(session_id) == 0
    assert list_chat_messages(session_id, "ana") == []


def test_append_to_an_unknown_session_raises_the_same_way(temp_db):
    """The two refusals are not distinguishable, and that is deliberate.

    A caller able to tell "no such session" from "someone else's session" has a
    membership oracle over other people's session ids -- the same reason
    `get_chat_session` returns `None` for both rather than raising two things.
    AC 6 requires the failure to be *visible*; it does not require it to be
    *informative*, and this test fails if someone later "improves" the message by
    naming which case occurred.
    """
    session_id = _seeded_session()

    with pytest.raises(StorageError) as foreign:
        append_chat_message(_stored(session_id), session_id, "bob")
    with pytest.raises(StorageError) as unknown:
        append_chat_message(_stored("no-such-session"), "no-such-session", "ana")

    assert type(unknown.value) is type(foreign.value)
    assert str(unknown.value) == str(foreign.value)


def test_append_ignores_the_session_id_on_the_message(temp_db):
    """The `StoredMessage.session_id` field is never read.

    Two candidate values, one winner. If the dataclass field were what got
    written, the `WHERE EXISTS` would have checked ana's session while the row
    landed in bob's -- an ownership check that passes and a row that goes
    somewhere else entirely.
    """
    _seed_users()
    ana_session = create_chat_session("ana", "ana's chat")
    bob_session = create_chat_session("bob", "bob's chat")

    append_chat_message(
        _stored(bob_session, content="smuggled"), ana_session, "ana"
    )

    (landed,) = list_chat_messages(ana_session, "ana")
    assert landed.content == "smuggled"
    assert landed.session_id == ana_session
    assert list_chat_messages(bob_session, "bob") == []


def test_delete_chat_session_removes_messages_written_through_append(temp_db):
    """STORY-004's delete and STORY-005's write agree.

    `_add_message` above writes rows directly because `append_chat_message` did
    not exist when STORY-004 was written. It does now, and a transcript written
    through the real path must be just as deletable as one inserted by hand --
    otherwise "delete removes the messages" is only true of the fixture.
    """
    session_id = _seeded_session()
    for index in range(3):
        append_chat_message(
            _stored(session_id, content=f"m{index}"), session_id, "ana"
        )
    assert _count_messages(session_id) == 3

    assert delete_chat_session(session_id, "ana") is True

    assert _count_messages(session_id) == 0


# --------------------------------------------------------------------------
# count_chat_sessions -- a true total, so the rail can state its cap
# --------------------------------------------------------------------------


def test_count_chat_sessions_counts_only_the_callers_own(temp_db):
    _seed_users()
    for index in range(3):
        create_chat_session("ana", f"ana {index}")
    for index in range(2):
        create_chat_session("bob", f"bob {index}")

    assert count_chat_sessions("ana") == 3
    assert count_chat_sessions("bob") == 2


def test_count_chat_sessions_is_zero_for_an_unknown_user(temp_db):
    """Zero, not an exception. An account with no chats is an ordinary state --
    it is what every account looks like on its first visit."""
    _seed_users()

    assert count_chat_sessions("nobody") == 0


def test_count_chat_sessions_ignores_the_list_limit(temp_db):
    """The reason this function exists at all.

    `len(list_chat_sessions(user_id))` can never exceed the limit it was called
    with, so a capped list reports "50 of 50" for an account with fifty-two
    sessions and for one with two hundred, identically. The rail needs the number
    the cap is being stated *against*, the way PRD-006's register says "100 most
    recent of 3,180".
    """
    _seed_users()
    for index in range(52):
        create_chat_session("ana", f"ana {index}")

    listed = list_chat_sessions("ana")

    assert len(listed) == 50
    assert count_chat_sessions("ana") == 52


# ==========================================================================
# STORY-006 -- app/services/chat_sessions.py, the service over the store
# ==========================================================================

#: The surface STORY-006 adds, in the order the story lists it, plus the ninth
#: STORY-010 added -- `owns`, which answers `app/routers/query.py`'s question
#: without handing it the flag branch that `get` would have forced -- and the
#: tenth STORY-018 added: `count`, which the rail needs to state its cap against
#: a true total, since a capped list's own length can never exceed that cap.
THE_TEN = (
    "create",
    "list_for",
    "count",
    "get",
    "owns",
    "rename",
    "touch",
    "delete",
    "append_message",
    "messages_for",
)


def _identity(user_id: str) -> Identity:
    """An `Identity` the way `resolve()` would have produced one.

    Constructed directly rather than resolved through a token: the subject here
    is what the service does with `identity.user_id`, and going through
    `resolve()` would make every case below depend on credential verification
    working, which `tests/test_identity.py` already owns.
    """
    return Identity(user_id=user_id, role="user")


class _Tripwire:
    """A stand-in for `app.db.database` on which every access is a failure.

    AC 4 asks for more than an empty result: "asserted by patching the database
    module and observing that nothing on it was called, not merely by observing
    an empty result". An empty list is what an empty database returns too, so a
    test that only checked the value would pass on a service that issued the
    statement and found nothing.

    `__getattr__` fires on the attribute lookup, which is *before* the call, so
    this catches `database.list_chat_sessions` even if the result were never
    used. Deliberately not a Mock: a Mock records and returns another Mock, so
    the test would have to remember to assert `not called` afterwards, and a
    forgotten assertion is a green test. Here forgetting is impossible.
    """

    def __getattr__(self, name: str):
        raise AssertionError(
            f"chat_sessions reached database.{name} with CHAT_HISTORY_ENABLED off"
        )


def _service_functions() -> dict:
    """Every public function *defined* in the service module.

    Discovered, not enumerated -- STORY-007's point, applied one story early so
    that the surface assertions here cannot go stale. `__module__` is what
    excludes `contextmanager`, a public callable in the module's namespace
    because it was imported there and no part of its surface.
    """
    return {
        name: obj
        for name, obj in vars(chat_sessions).items()
        if inspect.isfunction(obj)
        and not name.startswith("_")
        and obj.__module__ == chat_sessions.__name__
    }


def _service_statements_of(name: str) -> str:
    """One service function's body with its docstring removed.

    `_statements_of` above does this for `database`; this is the same move over
    the other module. Kept separate rather than parametrized by module because
    the STORY-004 helper is part of that story's own assertions and widening it
    would make two stories' tests fail together for one story's reason.
    """
    tree = ast.parse(inspect.getsource(getattr(chat_sessions, name)))
    body = tree.body[0].body
    if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return "\n".join(ast.unparse(node) for node in body)


def _call(name: str, identity: Identity, session_id: str, **overrides):
    """Calls one service function with arguments valid for its signature.

    One table of call shapes, so the flag-off, foreign-identity and
    error-wrapping cases below can drive all eight without any of them
    enumerating arguments a second time -- and so a signature change breaks one
    place rather than three.
    """
    title = overrides.get("title", "renamed")
    prompt = overrides.get("prompt", "what is the retention policy?")
    derive = overrides.get("derive_title", lambda text: text[:20])
    shapes = {
        "create": lambda: chat_sessions.create(identity, prompt, derive),
        "list_for": lambda: chat_sessions.list_for(identity),
        "count": lambda: chat_sessions.count(identity),
        "get": lambda: chat_sessions.get(identity, session_id),
        "owns": lambda: chat_sessions.owns(identity, session_id),
        "rename": lambda: chat_sessions.rename(identity, session_id, title),
        "touch": lambda: chat_sessions.touch(identity, session_id),
        "delete": lambda: chat_sessions.delete(identity, session_id),
        "append_message": lambda: chat_sessions.append_message(
            identity, session_id, _stored(session_id)
        ),
        "messages_for": lambda: chat_sessions.messages_for(identity, session_id),
    }
    return shapes[name]()


def _count_sessions_rows() -> int:
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM chat_sessions").fetchone()["n"]


def _count_messages_rows() -> int:
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM chat_messages").fetchone()["n"]


# --------------------------------------------------------------------------
# AC 1 and AC 2 -- the surface, and the Identity that is the only way in
# --------------------------------------------------------------------------


def test_the_ten_service_functions_are_declared():
    """AC 1. A statement about the module; no database needed."""
    for name in THE_TEN:
        assert hasattr(chat_sessions, name), name
        assert callable(getattr(chat_sessions, name)), name


def test_the_service_exposes_exactly_those_ten():
    """AC 1, the other direction. A story that exposes a further function has to
    say so by editing this tuple rather than by nobody noticing.

    STORY-010 was the first story to take that path: `owns` is the ninth, and it
    is here because the router's ownership refusal needed an answer `get` could
    not give without the caller branching on `CHAT_HISTORY_ENABLED`.

    STORY-018 is the second. `count` wraps `database.count_chat_sessions`, which
    this test previously noted was "deliberately not re-exported": the rail now
    needs it, and it comes through the service rather than around it so that the
    flag short-circuit and the `_wrapped` error contract still apply.
    """
    assert sorted(_service_functions()) == sorted(THE_TEN)


def test_every_service_function_takes_an_identity_first():
    """AC 1, and STORY-007's AC 3 one story early. Discovered from the module
    rather than listed, so the rule outlives this story's function names."""
    for name, function in _service_functions().items():
        parameters = list(inspect.signature(function).parameters.values())
        assert parameters, name
        assert parameters[0].name == "identity", name
        assert parameters[0].annotation is Identity, name
        assert parameters[0].default is inspect.Parameter.empty, name


def test_no_service_function_accepts_a_bare_user_id():
    """AC 1's "rather than a bare `user_id` string". The store's own functions
    all require one; the point of this layer is that its callers cannot supply
    one, so a `user_id` parameter up here would mean the conversion leaked back
    out."""
    for name, function in _service_functions().items():
        assert "user_id" not in inspect.signature(function).parameters, name


def test_every_service_function_passes_identity_user_id_to_the_store():
    """AC 2, structurally. A function that takes an `Identity` and then reads
    something else off it -- or nothing at all -- satisfies the signature tests
    above and still queries the wrong owner.

    `identity.role` is asserted absent in the same pass: PRD Section 9 divides
    the two questions, and a service consulting the role would be RBAC
    substituting for ownership, which Section 6 forbids.
    """
    for name in THE_TEN:
        statements = _service_statements_of(name)
        assert "identity.user_id" in statements, name
        assert "identity.role" not in statements, name


def test_no_module_outside_the_service_calls_the_store_session_functions():
    """AC 2's second half: "no caller outside it reaches `database.py`'s session
    functions". Structural, because the rule is about what future code may do --
    `ChatState` calling `list_chat_sessions` directly would work perfectly and
    quietly bypass both the ownership conversion and the flag."""
    root = pathlib.Path(__file__).resolve().parents[1]
    surface = {name for name in dir(database) if "_chat_session" in name or "_chat_message" in name}
    allowed = {root / "app" / "db" / "database.py", root / "app" / "services" / "chat_sessions.py"}

    offenders = []
    for path in sorted(list((root / "app").rglob("*.py")) + list((root / "chat_ui").rglob("*.py"))):
        if path in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                called = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
                if called in surface:
                    offenders.append(f"{path.relative_to(root)}:{node.lineno} {called}")

    assert offenders == [], f"the store's session functions are called outside the service: {offenders}"


# --------------------------------------------------------------------------
# AC 3 and AC 4 -- CHAT_HISTORY_ENABLED off issues no statement at all
# --------------------------------------------------------------------------


@pytest.fixture
def history_off(monkeypatch):
    """The flag off, and a database module that fails on contact.

    Both halves matter. The flag alone would let a passing test prove only that
    the return value was empty; the tripwire is what makes "no statement is
    issued" the thing actually asserted.
    """
    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)
    monkeypatch.setattr(chat_sessions, "database", _Tripwire())


@pytest.mark.parametrize(
    "name, expected",
    [
        ("create", None),
        ("append_message", None),
        ("touch", False),
        ("rename", False),
        ("delete", False),
    ],
)
def test_writes_return_a_usable_value_and_issue_nothing_when_history_is_off(
    history_off, name, expected
):
    """AC 3. Each write returns the value the story names, and the tripwire
    proves the store was never reached to produce it.

    Values a caller can proceed with rather than an exception, which is the whole
    of "no caller branches on the flag": a caller that had to catch a
    `HistoryDisabled` would be branching on the flag with extra steps.
    """
    assert _call(name, _identity("ana"), str(uuid.uuid4())) is expected


def test_owns_answers_true_and_issues_nothing_when_history_is_off(history_off):
    """PRD-008 STORY-010 AC 7, and the one return value on this surface that is
    not "empty".

    `True` here does not claim the identity owns the row. It says *nothing about
    this id is grounds to refuse the send*: with persistence off there are no
    `chat_sessions` rows for anybody, so there is no ownership to assert, and
    the id is only a label on the audit row -- "the flag governs the transcript,
    not the audit column". The tripwire proves the store was never consulted to
    produce the answer.
    """
    assert _call("owns", _identity("ana"), str(uuid.uuid4())) is True


@pytest.mark.parametrize(
    "name, expected",
    [
        ("list_for", []),
        ("get", None),
        ("messages_for", []),
        # 0 is the count-shaped spelling of "empty", and the same deliberate
        # sameness the three above keep: with history off there are no rows for
        # anybody, so "none yet" and "disabled" answer identically here too.
        ("count", 0),
    ],
)
def test_reads_return_empty_and_issue_nothing_when_history_is_off(
    history_off, name, expected
):
    """AC 4, including its "not merely by observing an empty result" clause --
    `_Tripwire` raises on the attribute lookup, so reaching the store at all is
    a failure here rather than a different return value."""
    assert _call(name, _identity("ana"), str(uuid.uuid4())) == expected


def test_history_off_reaches_the_database_for_none_of_the_ten(history_off):
    """AC 3 and AC 4 over the whole surface at once. The parametrized cases above
    assert the values; this asserts the property for all ten together, so a
    further function that forgot its guard fails here even if nobody remembered
    to add it to the tables above."""
    for name in THE_TEN:
        _call(name, _identity("ana"), str(uuid.uuid4()))


def test_the_flag_is_read_at_call_time_not_captured_at_import(monkeypatch, temp_db):
    """The story's technical note, verbatim: "A flag captured at import cannot be
    flipped by a test without reloading the module." The module was imported at
    collection with the flag on, so flipping it now must change behaviour without
    a reload -- which is what every other test in this section depends on.

    `authz.load()` is the deliberate counter-example, reading its setting once at
    startup and saying so, which is why this is asserted rather than assumed to
    be the house style.
    """
    _seed_users()
    assert chat_sessions.create(_identity("ana"), "hello", lambda text: text) is not None

    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)
    assert chat_sessions.create(_identity("ana"), "hello", lambda text: text) is None

    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", True)
    assert chat_sessions.create(_identity("ana"), "hello", lambda text: text) is not None


def test_no_module_outside_the_service_branches_on_chat_history_enabled():
    """PRD Section 6, verbatim: "**No caller branches on the flag.**"

    The story makes preventing that this module's job, and a rule stated only in
    prose is a rule that lasts one story -- the argument
    `tests/test_untouched_app.py` makes for PRD-006's containment: "That proof
    was a document, and a document does not fail when someone adds a database
    function next month."

    Read through `ast` rather than by grepping text, so the paragraphs of comment
    in `app/config.py` and in the service that discuss the setting by name are
    not what is measured -- only a real reference to the identifier in code is.
    """
    root = pathlib.Path(__file__).resolve().parents[1]
    allowed = {root / "app" / "config.py", root / "app" / "services" / "chat_sessions.py"}

    offenders = []
    for path in sorted(list((root / "app").rglob("*.py")) + list((root / "chat_ui").rglob("*.py"))):
        if path in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            named = (
                isinstance(node, ast.Attribute) and node.attr == "CHAT_HISTORY_ENABLED"
            ) or (isinstance(node, ast.Name) and node.id == "CHAT_HISTORY_ENABLED")
            if named:
                offenders.append(f"{path.relative_to(root)}:{node.lineno}")

    assert offenders == [], (
        "CHAT_HISTORY_ENABLED is referenced outside app/config.py and "
        f"app/services/chat_sessions.py: {offenders}"
    )


# --------------------------------------------------------------------------
# AC 5 -- CHAT_SESSION_LIMIT is the service's to apply, and nobody else's
# --------------------------------------------------------------------------


def test_list_for_takes_no_limit_parameter():
    """AC 5's "no caller supplies its own". `list_chat_sessions` one layer down
    does take one and defaults it; the cap being a deployment decision is
    expressed here by there being nothing to pass."""
    assert list(inspect.signature(chat_sessions.list_for).parameters) == ["identity"]


def test_list_for_applies_the_configured_limit(monkeypatch, temp_db):
    """AC 5. Three sessions, a limit of two, two returned -- and the two are the
    most recently active, so the cap drops the oldest rather than an arbitrary
    pair."""
    _seed_users()
    monkeypatch.setattr(settings, "CHAT_SESSION_LIMIT", 2)

    oldest = create_chat_session("ana", "oldest")
    middle = create_chat_session("ana", "middle")
    newest = create_chat_session("ana", "newest")
    _set_updated_at(oldest, "2026-09-01T10:00:00Z")
    _set_updated_at(middle, "2026-09-02T10:00:00Z")
    _set_updated_at(newest, "2026-09-03T10:00:00Z")

    listed = chat_sessions.list_for(_identity("ana"))

    assert [s.session_id for s in listed] == [newest, middle]


def test_count_ignores_the_limit_that_caps_the_list(monkeypatch, temp_db):
    """STORY-018's reason for existing, in one assertion.

    The rail states its window as "2 most recent of 3", and it can only get the
    3 from here: `len(list_for(...))` can never exceed the limit it was called
    with, so a capped list reports "2 of 2" on an account with three sessions and
    is indistinguishable from one with exactly two. A count that respected the
    display cap could not produce the one number worth printing.
    """
    _seed_users()
    monkeypatch.setattr(settings, "CHAT_SESSION_LIMIT", 2)
    for title in ("oldest", "middle", "newest"):
        create_chat_session("ana", title)

    assert len(chat_sessions.list_for(_identity("ana"))) == 2
    assert chat_sessions.count(_identity("ana")) == 3


def test_count_counts_only_the_callers_own_sessions(temp_db):
    """PRD Risk 2 over the one function whose answer is a number rather than a
    row: a missing `WHERE user_id = ?` here would not leak a title, but it would
    tell every user how many conversations everyone else is having."""
    _seed_users()
    create_chat_session("ana", "hers")
    create_chat_session("ana", "hers too")
    create_chat_session("bob", "his")

    assert chat_sessions.count(_identity("ana")) == 2
    assert chat_sessions.count(_identity("bob")) == 1


def test_list_for_reflects_a_changed_limit_without_a_reload(monkeypatch, temp_db):
    """AC 5, and the call-time read again -- a limit captured at import would
    make `CHAT_SESSION_LIMIT` a build-time constant rather than configuration."""
    _seed_users()
    for index in range(3):
        _set_updated_at(
            create_chat_session("ana", f"session {index}"),
            f"2026-09-0{index + 1}T10:00:00Z",
        )

    monkeypatch.setattr(settings, "CHAT_SESSION_LIMIT", 1)
    assert len(chat_sessions.list_for(_identity("ana"))) == 1

    monkeypatch.setattr(settings, "CHAT_SESSION_LIMIT", 3)
    assert len(chat_sessions.list_for(_identity("ana"))) == 3


def test_messages_for_is_not_capped_by_the_session_limit(monkeypatch, temp_db):
    """The cap is on the rail, not on a transcript. Applying `CHAT_SESSION_LIMIT`
    to messages would silently truncate a conversation at the number of
    *conversations* a user may list -- a partial transcript with nothing on
    screen saying it is partial (STORY-005's `list_chat_messages` docstring)."""
    _seed_users()
    monkeypatch.setattr(settings, "CHAT_SESSION_LIMIT", 2)
    session_id = create_chat_session("ana", "a chat")
    for index in range(5):
        append_chat_message(_stored(session_id, content=f"m{index}"), session_id, "ana")

    assert len(chat_sessions.messages_for(_identity("ana"), session_id)) == 5


# --------------------------------------------------------------------------
# AC 6 -- the title is derived, and the derivation is delegated
# --------------------------------------------------------------------------


def test_create_delegates_the_title_derivation_and_stores_its_result(temp_db):
    """AC 6. The deriver returns a sentinel no truncation rule would produce, so
    a service that derived the title itself could not pass: the stored title is
    whatever the injected function returned, unmodified."""
    _seed_users()
    calls = []

    def derive(prompt: str) -> str:
        calls.append(prompt)
        return "<<derived>>"

    session_id = chat_sessions.create(
        _identity("ana"), "what is the retention policy?", derive
    )

    assert calls == ["what is the retention policy?"]
    stored = chat_sessions.get(_identity("ana"), session_id)
    assert stored.title == "<<derived>>"


def test_create_calls_the_deriver_exactly_once(temp_db):
    """AC 6, and STORY-012's note that a title is derived once and never again --
    "`derive_title` is called once, by STORY-006's `create`, and never again for
    that session." Two calls would be harmless today and wrong the moment the
    derivation stops being pure."""
    _seed_users()
    calls = []
    chat_sessions.create(_identity("ana"), "a prompt", lambda p: calls.append(p) or "t")
    assert calls == ["a prompt"]


def test_create_does_not_call_the_deriver_when_history_is_off(history_off):
    """AC 3 and AC 6 together. History off means no work at all, and deriving a
    title for a session that will not exist is work."""
    calls = []
    result = chat_sessions.create(
        _identity("ana"), "a prompt", lambda p: calls.append(p) or "t"
    )
    assert result is None
    assert calls == []


def test_the_service_reimplements_no_title_rule():
    """AC 6's "delegated, not reimplemented". `create`'s body may call the
    injected function; what it may not do is contain a derivation of its own, so
    neither shape a truncation takes -- a slice or a split -- may appear in it."""
    body = _service_statements_of("create")
    assert "derive_title(" in body
    for reimplementation in ("[:", ".split(", ".rsplit(", "..."):
        assert reimplementation not in body, reimplementation


def test_derive_title_has_no_default(temp_db):
    """AC 6. A default would have to be a derivation living in this module, which
    is what "not reimplemented" forbids -- so omitting it is a `TypeError` at the
    call site, the shape PRD Risk 2 asks for on `user_id`."""
    parameters = inspect.signature(chat_sessions.create).parameters
    assert parameters["derive_title"].default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        chat_sessions.create(_identity("ana"), "a prompt")


def test_the_service_imports_nothing_from_chat_ui():
    """The story's technical note: it "imports nothing from `chat_ui/`". This is
    what the injected deriver buys, and without an assertion the next change that
    wants a UI helper would simply import one."""
    tree = ast.parse(pathlib.Path(chat_sessions.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("chat_ui"), alias.name
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("chat_ui"), node.module


# --------------------------------------------------------------------------
# AC 7 -- a foreign session is indistinguishable from one that never existed
# --------------------------------------------------------------------------


def test_every_read_returns_nothing_for_a_foreign_identity(temp_db):
    """AC 7, reads. Bob is a real account, so a pass here means the ownership
    predicate scoped -- not merely that the id was unknown."""
    _seed_users()
    ana_session = create_chat_session("ana", "Ana private")
    append_chat_message(_stored(ana_session), ana_session, "ana")

    bob = _identity("bob")
    assert chat_sessions.get(bob, ana_session) is None
    assert chat_sessions.messages_for(bob, ana_session) == []
    assert chat_sessions.list_for(bob) == []


def test_a_foreign_session_is_indistinguishable_from_an_unknown_one(temp_db):
    """AC 7, stated as the equality it actually is. `identity.py`'s `resolve()`
    is the precedent the story cites: "None covers every failure case alike ...
    so the caller cannot distinguish them." A caller able to tell these apart
    would have a membership oracle over other people's session ids."""
    _seed_users()
    ana_session = create_chat_session("ana", "Ana private")
    bob = _identity("bob")
    unknown = str(uuid.uuid4())

    assert chat_sessions.get(bob, ana_session) == chat_sessions.get(bob, unknown)
    assert chat_sessions.messages_for(bob, ana_session) == chat_sessions.messages_for(
        bob, unknown
    )
    assert chat_sessions.rename(bob, ana_session, "x") == chat_sessions.rename(
        bob, unknown, "x"
    )
    assert chat_sessions.touch(bob, ana_session) == chat_sessions.touch(bob, unknown)
    assert chat_sessions.delete(bob, ana_session) == chat_sessions.delete(bob, unknown)


def test_every_write_driven_by_a_foreign_identity_changes_no_row(temp_db):
    """AC 7, writes -- asserted by counting rows in both tables rather than by
    trusting the return value, which is STORY-007's AC 5 applied here early. A
    function that returned `False` and deleted the row anyway would pass a
    return-value test and fail this one."""
    _seed_users()
    ana_session = create_chat_session("ana", "Ana private")
    append_chat_message(_stored(ana_session), ana_session, "ana")
    before = (_count_sessions_rows(), _count_messages_rows(), count_audit_logs())

    bob = _identity("bob")
    assert chat_sessions.rename(bob, ana_session, "Bob was here") is False
    assert chat_sessions.touch(bob, ana_session) is False
    assert chat_sessions.delete(bob, ana_session) is False
    with pytest.raises(ChatSessionError):
        chat_sessions.append_message(bob, ana_session, _stored(ana_session))

    assert (_count_sessions_rows(), _count_messages_rows(), count_audit_logs()) == before
    survivor = chat_sessions.get(_identity("ana"), ana_session)
    assert survivor.title == "Ana private"


def test_the_break_glass_admin_identity_gets_no_special_case(temp_db):
    """PRD Section 9, verbatim: the admin identity "owns its own sessions like
    any other user and gains no read access to anyone else's". The role here is
    `admin`, the role `authz` grants everything to -- so a service that consulted
    the role rather than the owner would fail exactly here."""
    _seed_users()
    insert_user(User(user_id="admin", role="admin", token_hash="hash-admin"))
    ana_session = create_chat_session("ana", "Ana private")
    admin = Identity(user_id="admin", role="admin")

    assert chat_sessions.get(admin, ana_session) is None
    assert chat_sessions.messages_for(admin, ana_session) == []
    assert chat_sessions.list_for(admin) == []
    assert chat_sessions.delete(admin, ana_session) is False


def test_two_identities_round_trip_without_seeing_each_other(temp_db):
    """AC 7 end to end: both users do real work through the service alone, and
    each sees exactly their own."""
    _seed_users()
    ana, bob = _identity("ana"), _identity("bob")

    ana_session = chat_sessions.create(ana, "ana's question", lambda p: p)
    bob_session = chat_sessions.create(bob, "bob's question", lambda p: p)
    chat_sessions.append_message(ana, ana_session, _stored(ana_session, content="ana said"))
    chat_sessions.append_message(bob, bob_session, _stored(bob_session, content="bob said"))

    assert [s.session_id for s in chat_sessions.list_for(ana)] == [ana_session]
    assert [s.session_id for s in chat_sessions.list_for(bob)] == [bob_session]
    assert [m.content for m in chat_sessions.messages_for(ana, ana_session)] == ["ana said"]
    assert [m.content for m in chat_sessions.messages_for(bob, bob_session)] == ["bob said"]


# --------------------------------------------------------------------------
# AC 8 -- StorageError never leaves this layer
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", THE_TEN)
def test_every_function_wraps_storage_failure_in_chat_session_error(
    uninitialized_db, name
):
    """AC 8. No table exists, so every one of the eight fails at the store -- and
    each must surface it as this module's own type, the way
    `duplicate_checker.check_duplicate` turns a `StorageError` into a
    `DuplicateCheckError`. A caller importing `app.db.errors` to catch storage
    failures is the coupling this layer exists to remove."""
    with pytest.raises(ChatSessionError):
        _call(name, _identity("ana"), str(uuid.uuid4()))


@pytest.mark.parametrize("name", THE_TEN)
def test_the_wrapped_error_keeps_the_storage_error_as_its_cause(uninitialized_db, name):
    """AC 8. `from exc` rather than a bare `raise`: the storage detail stays
    reachable for a log line, it just is not the type callers catch."""
    with pytest.raises(ChatSessionError) as caught:
        _call(name, _identity("ana"), str(uuid.uuid4()))
    assert isinstance(caught.value.__cause__, StorageError)


@pytest.mark.parametrize("name", THE_TEN)
def test_the_wrapped_error_names_the_service_operation(uninitialized_db, name):
    """AC 8. The message reads in the caller's vocabulary -- "append_message
    failed" and not "append_chat_message failed" -- so a report reaching a user
    names the thing they asked for."""
    with pytest.raises(ChatSessionError) as caught:
        _call(name, _identity("ana"), str(uuid.uuid4()))
    assert str(caught.value).startswith(f"{name} failed: ")


def test_a_storage_error_never_escapes_as_itself(uninitialized_db):
    """AC 8, stated negatively. `ChatSessionError` does not inherit from
    `StorageError`, so this is a real assertion rather than a tautology."""
    assert not issubclass(ChatSessionError, StorageError)
    for name in THE_TEN:
        try:
            _call(name, _identity("ana"), str(uuid.uuid4()))
        except ChatSessionError:
            pass
        except StorageError as exc:  # pragma: no cover -- the failure this pins
            pytest.fail(f"{name} let a StorageError escape: {exc}")


def test_append_message_fails_identically_for_foreign_and_unknown_sessions(temp_db):
    """AC 7 and AC 8 at once, and the one place the two could contradict.

    `append_chat_message` raises rather than returning `None` for both cases --
    STORY-005's reasoning, verbatim: "a read that finds nothing is an ordinary
    outcome, a write that silently lands nowhere is not." AC 7 requires that the
    caller cannot *distinguish* the two, not that they are silent, so the two
    must raise with byte-identical messages. Anything more specific -- a message
    quoting the session id, say -- would be a membership oracle written into an
    error string.
    """
    _seed_users()
    ana_session = create_chat_session("ana", "Ana private")
    bob = _identity("bob")

    with pytest.raises(ChatSessionError) as foreign:
        chat_sessions.append_message(bob, ana_session, _stored(ana_session))
    with pytest.raises(ChatSessionError) as unknown:
        chat_sessions.append_message(bob, str(uuid.uuid4()), _stored(ana_session))

    assert str(foreign.value) == str(unknown.value)


def test_a_working_database_raises_nothing(temp_db):
    """The other half of AC 8: the wrap must not turn ordinary outcomes into
    errors. Every one of the eight against a healthy database, ending on a
    session that is genuinely absent because it was just deleted."""
    _seed_users()
    ana = _identity("ana")
    session_id = chat_sessions.create(ana, "a prompt", lambda p: p)

    assert chat_sessions.get(ana, session_id) is not None
    assert chat_sessions.rename(ana, session_id, "renamed") is True
    assert chat_sessions.touch(ana, session_id) is True
    assert chat_sessions.append_message(ana, session_id, _stored(session_id)) > 0
    assert len(chat_sessions.messages_for(ana, session_id)) == 1
    assert len(chat_sessions.list_for(ana)) == 1
    assert chat_sessions.delete(ana, session_id) is True
    assert chat_sessions.get(ana, session_id) is None
