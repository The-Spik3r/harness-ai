"""PRD-008's ownership rule, asserted against the signatures rather than remembered.

The rule is one sentence: **every function that reaches a session or a message
names an owner, and naming one is not optional.** PRD-008 Risk 2 states it and
states the mitigation verbatim:

    "RBAC has never asked *whose row is this*, so there is no habit to fall back
    on, and the failure mode is silent: a missing `WHERE user_id = ?` returns
    data rather than an error. *Mitigation*: the rule lives in the signature --
    `user_id` is required and undefaulted on every session-scoped function, so
    an omission is a `TypeError` at the call site rather than a leak at runtime.
    `tests/test_session_ownership.py` inspects the signatures and drives every
    read path with a foreign id."

`tests/test_untouched_app.py` made this same move for PRD-006's containment and
said why: "That proof was a document, and a document does not fail when someone
adds a database function next month." A rule written in a PRD does not fail. A
rule written as a list of nine function names fails only until someone adds a
tenth. So **nothing here is enumerated**: the surface is discovered from the
modules, and every assertion below runs over whatever the discovery finds.

**Why this file overlaps `tests/test_chat_sessions.py`, and what each one owns.**
That file asserts the rule over the six store functions STORY-004 added, the
three STORY-005 added and the eight service functions STORY-006 added, **by
name** -- deliberately, so each of those stories was verifiable on its own,
before this file existed. Its own docstring reserves this scope: "STORY-007 owns
`tests/test_session_ownership.py`, which discovers every `*_chat_session*` /
`*_chat_message*` callable and asserts the rule against whatever it finds." One
rule, two scopes. The named version fails when one of today's functions loses
its owner; this version also fails when tomorrow's function never had one.

**What makes discovery worth having, and what would quietly destroy it.** A
discovery whose predicate breaks finds nothing, and a suite of assertions over
an empty set is green. That would make this file *weaker* than the enumeration
it replaces. Two things prevent it: the census tests below put a floor under
each discovery, and the call tables are asserted to cover the discovered set --
so a new function is not merely inspected, it is *driven with a foreign
credential*, or the coverage test goes red before anyone reaches the rest.

Offline like every other test in this repository (PRD-007 STORY-006): the only
fixture used is `temp_db` from `tests/conftest.py`, no environment variable is
read here, and no client is opened that the application did not open.
"""

import inspect

import pytest

from app.db import database
from app.db.database import (
    count_audit_logs,
    get_connection,
    insert_audit_log,
    insert_user,
)
from app.db.errors import StorageError
from app.db.models import AuditLog, StoredMessage, User
from app.services import chat_sessions
from app.services.chat_sessions import ChatSessionError
from app.services.identity import Identity, hash_token, issue_token, resolve

#: What makes a `database.py` function part of the session surface: its name.
#: PRD-008's own spelling of the rule is a glob over names (`*_chat_session*`,
#: `*_chat_message*`), so the predicate is a substring test and nothing cleverer.
#:
#: It deliberately does **not** catch `count_audit_logs(user_id=None)`. That
#: function's `user_id` is an optional admin filter over evidence, not an
#: ownership scope over a transcript -- `GET /audit` passes it or does not,
#: depending on the caller's permission -- and a predicate wide enough to sweep
#: it in would demand an undefaulted parameter that `app/routers/admin.py`
#: relies on being optional. The two questions are different, which is Section
#: 9's whole point, and the marker is where that distinction is kept.
_SURFACE_MARKERS = ("_chat_session", "_chat_message")

#: The functions that exist today, as a floor under the discovery and nothing
#: more. No assertion below iterates these -- see the census tests.
_KNOWN_STORE = frozenset(
    {
        "create_chat_session",
        "get_chat_session",
        "list_chat_sessions",
        "rename_chat_session",
        "touch_chat_session",
        "delete_chat_session",
        "append_chat_message",
        "list_chat_messages",
        "count_chat_sessions",
    }
)

_KNOWN_SERVICE = frozenset(
    {
        "create",
        "list_for",
        "get",
        "owns",
        "rename",
        "touch",
        "delete",
        "append_message",
        "messages_for",
    }
)

#: `create_chat_session` and `create` mint a row owned by whoever is named, and
#: take no session id at all. There is no foreign row for them to reach, so the
#: foreign-credential drives below exempt them -- and say so here rather than
#: skipping them silently. They are still discovered, still signature-checked,
#: and still required to appear in the call tables.
_EXEMPT_STORE = frozenset({"create_chat_session"})
_EXEMPT_SERVICE = frozenset({"create"})


def _store_surface() -> dict:
    """Every public session/message function *defined* in `app/db/database.py`.

    `__module__` is load-bearing: `database.py` imports `datetime`, `uuid` and
    several dataclasses into its namespace, and a predicate that only looked at
    names would inspect things the module never wrote. The same filter is what
    `tests/test_chat_sessions.py:_service_functions` uses, for the same reason.
    """
    return {
        name: obj
        for name, obj in vars(database).items()
        if inspect.isfunction(obj)
        and not name.startswith("_")
        and obj.__module__ == database.__name__
        and any(marker in name for marker in _SURFACE_MARKERS)
    }


def _service_surface() -> dict:
    """Every public function *defined* in `app/services/chat_sessions.py`.

    No name filter here: the module exists only to serve sessions, so its whole
    public surface is the surface. `__module__` excludes `contextmanager`, which
    is public in that namespace because it was imported there.
    """
    return {
        name: obj
        for name, obj in vars(chat_sessions).items()
        if inspect.isfunction(obj)
        and not name.startswith("_")
        and obj.__module__ == chat_sessions.__name__
    }


# --------------------------------------------------------------------------
# The floor under the discovery
# --------------------------------------------------------------------------


def test_the_store_surface_is_discovered_and_not_empty():
    """A broken predicate finds nothing, and every assertion below then passes
    over an empty set -- which would make this file weaker than the list of
    names it replaces. The floor is asserted as a *superset*, not an equality:
    adding a tenth function must change the rule tests' outcome, not this one's.
    """
    discovered = set(_store_surface())
    assert discovered, "the store surface predicate found nothing"
    assert _KNOWN_STORE <= discovered, sorted(_KNOWN_STORE - discovered)


def test_the_service_surface_is_discovered_and_not_empty():
    """The same floor, over `app/services/chat_sessions.py`."""
    discovered = set(_service_surface())
    assert discovered, "the service surface predicate found nothing"
    assert _KNOWN_SERVICE <= discovered, sorted(_KNOWN_SERVICE - discovered)


# --------------------------------------------------------------------------
# AC 1 and AC 2 -- the rule as a property of the module, not of a call
# --------------------------------------------------------------------------


def test_every_discovered_store_function_requires_an_undefaulted_user_id():
    """AC 1, and Risk 2's mitigation exactly: "`user_id` is required and
    undefaulted on every session-scoped function".

    A default would be the leak: `list_chat_messages(session_id, user_id=None)`
    reads perfectly and returns the transcript of whoever asked for it. So the
    assertion is not "a `user_id` parameter exists" but "a caller cannot get
    away without supplying one".
    """
    for name, function in sorted(_store_surface().items()):
        parameters = inspect.signature(function).parameters
        assert "user_id" in parameters, f"{name} names no owner"
        user_id = parameters["user_id"]
        assert user_id.default is inspect.Parameter.empty, f"{name} defaults user_id"
        assert user_id.annotation is str, f"{name} does not annotate user_id as str"
        assert user_id.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD, name


def test_omitting_user_id_is_a_type_error_on_every_discovered_function():
    """AC 1's consequence, exercised rather than only inspected. Risk 2 promises
    "a `TypeError` at the call site rather than a leak at runtime" -- this is the
    difference between a crash and a leak, so it gets its own case."""
    for name, function in sorted(_store_surface().items()):
        with pytest.raises(TypeError):
            function()


# --------------------------------------------------------------------------
# AC 3 -- the service converts an Identity, and never takes a bare id
# --------------------------------------------------------------------------


def test_every_discovered_service_function_takes_an_identity_first():
    """AC 3. The store requires a `user_id`; this layer is the only thing that
    supplies one, and it derives it from an `Identity` that `resolve()` produced.
    A function here that took anything else first would be a second way in."""
    for name, function in sorted(_service_surface().items()):
        parameters = list(inspect.signature(function).parameters.values())
        assert parameters, f"{name} takes no arguments at all"
        first = parameters[0]
        assert first.name == "identity", f"{name} does not take identity first"
        assert first.annotation is Identity, f"{name} does not annotate Identity"
        assert first.default is inspect.Parameter.empty, f"{name} defaults identity"


def test_no_discovered_service_function_accepts_a_bare_user_id():
    """AC 3's other half. The `Identity`-to-owner conversion happens once, inside
    the service; a `user_id` parameter up here would mean it leaked back out and
    a caller could name an owner it was never issued."""
    for name, function in sorted(_service_surface().items()):
        assert "user_id" not in inspect.signature(function).parameters, name


# --------------------------------------------------------------------------
# Fixtures, call tables, and the coverage that makes a tenth function fail
# --------------------------------------------------------------------------


def _seed_two_users() -> tuple[Identity, Identity]:
    """Two real accounts with real credentials, resolved the way production does.

    The tokens come from `issue_token()` and are hashed with `hash_token()`
    rather than written by hand, and the `Identity` comes back out of
    `resolve()`: what is driven below is therefore a credential the system would
    have accepted, not a struct a test invented.

    Both users are genuine, which is the point `tests/test_chat_sessions.py`
    records: "A test that drives a read with `bob` when no bob row exists proves
    less than one where bob is a genuine account: the first can pass because the
    id is unknown, the second only passes because the `WHERE` clause scopes."
    """
    identities = []
    for user_id in ("ana", "bob"):
        token = issue_token()
        insert_user(User(user_id=user_id, role="user", token_hash=hash_token(token)))
        identity = resolve(token)
        assert identity is not None and identity.user_id == user_id
        identities.append(identity)
    return identities[0], identities[1]


def _stored(session_id: str, content: str = "ana said this") -> StoredMessage:
    """The minimum a `chat_messages` row needs. The kinds' full round trip is
    `tests/test_chat_sessions.py`'s subject; here a message is only something to
    try to write into someone else's session."""
    return StoredMessage(session_id=session_id, kind="user", content=content)


#: How to call each discovered store function, keyed by name. One table, so the
#: drives below never enumerate arguments a second time and a signature change
#: breaks one place rather than three (`tests/test_chat_sessions.py:1059`).
#:
#: A table rather than a chain of `if name ==` because the coverage tests below
#: read its keys: what makes a tenth function fail is that its name is missing
#: from *this dict*, which is a fact available without calling anything.
_STORE_SHAPES = {
    "create_chat_session": lambda user_id, session_id: database.create_chat_session(
        user_id, "a title"
    ),
    "get_chat_session": lambda user_id, session_id: database.get_chat_session(
        session_id, user_id
    ),
    "list_chat_sessions": lambda user_id, session_id: database.list_chat_sessions(user_id),
    "rename_chat_session": lambda user_id, session_id: database.rename_chat_session(
        session_id, user_id, "renamed by a stranger"
    ),
    "touch_chat_session": lambda user_id, session_id: database.touch_chat_session(
        session_id, user_id
    ),
    "delete_chat_session": lambda user_id, session_id: database.delete_chat_session(
        session_id, user_id
    ),
    "append_chat_message": lambda user_id, session_id: database.append_chat_message(
        _stored(session_id, "written by a stranger"), session_id, user_id
    ),
    "list_chat_messages": lambda user_id, session_id: database.list_chat_messages(
        session_id, user_id
    ),
    "count_chat_sessions": lambda user_id, session_id: database.count_chat_sessions(user_id),
}

#: The same table over the service, whose functions take an `Identity`.
_SERVICE_SHAPES = {
    "create": lambda identity, session_id: chat_sessions.create(
        identity, "what is the retention policy?", lambda text: text[:20]
    ),
    "list_for": lambda identity, session_id: chat_sessions.list_for(identity),
    # Takes no session_id: like `list_for`, its whole answer is scoped by the
    # identity. A stranger's count of another account's sessions is 0, which
    # `_assert_returns_nothing` already treats as the count-shaped spelling of
    # "no rows" -- the arm it grew for `count_chat_sessions` in the store.
    "count": lambda identity, session_id: chat_sessions.count(identity),
    "get": lambda identity, session_id: chat_sessions.get(identity, session_id),
    "owns": lambda identity, session_id: chat_sessions.owns(identity, session_id),
    "rename": lambda identity, session_id: chat_sessions.rename(
        identity, session_id, "renamed by a stranger"
    ),
    "touch": lambda identity, session_id: chat_sessions.touch(identity, session_id),
    "delete": lambda identity, session_id: chat_sessions.delete(identity, session_id),
    "append_message": lambda identity, session_id: chat_sessions.append_message(
        identity, session_id, _stored(session_id, "written by a stranger")
    ),
    "messages_for": lambda identity, session_id: chat_sessions.messages_for(
        identity, session_id
    ),
}


def _call_store(name: str, *, user_id: str, session_id: str):
    return _STORE_SHAPES[name](user_id, session_id)


def _call_service(name: str, *, identity: Identity, session_id: str):
    return _SERVICE_SHAPES[name](identity, session_id)


def _count(table: str) -> int:
    with get_connection() as conn:
        return conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]


def _rows(table: str) -> list:
    """Every row of a table as comparable tuples, ordered deterministically.

    Counts alone would miss a foreign `rename` that changed a title without
    changing the number of rows, which is exactly the kind of write AC 5 calls
    "not byte-identical".
    """
    with get_connection() as conn:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    return sorted(tuple(row) for row in rows)


def _snapshot() -> tuple:
    """Both transcript tables, whole, as one comparable value."""
    return (_rows("chat_sessions"), _rows("chat_messages"))


def test_the_store_call_table_covers_every_discovered_function():
    """**The test that catches the tenth function.**

    Discovering a function and then never driving it would be discovery in name
    only -- the new function would be signature-checked and never asked whether
    it actually scopes. So the call table is asserted against the discovery
    rather than written beside it: a function added to `database.py` has no
    shape in `_STORE_SHAPES`, and this goes red before anyone reaches the drives
    below.

    Equality in both directions: a shape for a function that no longer exists is
    also a failure, because it is a drive nobody is running any more.
    """
    assert sorted(_STORE_SHAPES) == sorted(_store_surface())


def test_the_service_call_table_covers_every_discovered_function():
    """The same coverage over `app/services/chat_sessions.py`."""
    assert sorted(_SERVICE_SHAPES) == sorted(_service_surface())


# --------------------------------------------------------------------------
# AC 4 -- every read path, driven with the other user's credential
# --------------------------------------------------------------------------

#: The discovered functions that read. Split from the writes by what they do,
#: not by name: AC 4 asks for "empty, `None` or `False`" and AC 5 asks for an
#: unchanged database, and those are different assertions over the same drive.
_STORE_READS = ("get_chat_session", "list_chat_sessions", "list_chat_messages", "count_chat_sessions")
# `owns` is a read: it issues one SELECT and changes nothing. Its answer for a
# foreign credential is `False`, which is what AC 4 asks of a function whose
# answer is a boolean -- `_assert_returns_nothing` already accepts it.
_SERVICE_READS = ("get", "list_for", "messages_for", "owns", "count")

_STORE_WRITES = ("rename_chat_session", "touch_chat_session", "delete_chat_session", "append_chat_message")
_SERVICE_WRITES = ("rename", "touch", "delete", "append_message")


def test_the_read_and_write_partitions_cover_the_whole_discovered_surface():
    """The partitions above are lists of names, which is the thing this file
    exists to distrust. So they are checked against the discovery too: every
    discovered function is a read, a write, or an exemption -- and a new one is
    none of the three until someone classifies it."""
    store = set(_store_surface())
    service = set(_service_surface())
    assert store - set(_STORE_READS) - set(_STORE_WRITES) - _EXEMPT_STORE == set()
    assert service - set(_SERVICE_READS) - set(_SERVICE_WRITES) - _EXEMPT_SERVICE == set()


def _seeded_transcript(owner: Identity) -> str:
    """One session owned by `owner`, with two messages in it."""
    session_id = database.create_chat_session(owner.user_id, "Ana private")
    database.append_chat_message(_stored(session_id, "first"), session_id, owner.user_id)
    database.append_chat_message(_stored(session_id, "second"), session_id, owner.user_id)
    return session_id


def _assert_returns_nothing(name: str, result) -> None:
    """AC 4's "empty, `None` or `False`, and never a row".

    A list is asserted equal to `[]` rather than merely falsy, so a single
    leaked row cannot pass as truthy-but-unchecked. `count_chat_sessions`
    returns `0`, which is the count-shaped spelling of "no rows" and is what AC
    4 asks of a function whose answer is a number.
    """
    if isinstance(result, list):
        assert result == [], f"{name} returned rows for a foreign credential"
    elif isinstance(result, int) and not isinstance(result, bool):
        assert result == 0, f"{name} counted rows for a foreign credential"
    else:
        assert result is None or result is False, f"{name} returned {result!r}"


@pytest.mark.parametrize("name", _STORE_READS)
def test_every_store_read_path_returns_nothing_for_a_foreign_credential(name, temp_db):
    """AC 4, over the store. `bob` is a real account with a real credential and
    ana's session id -- the id being valid is the point, since a `WHERE` clause
    that forgot the owner would find the row."""
    ana, bob = _seed_two_users()
    session_id = _seeded_transcript(ana)

    _assert_returns_nothing(name, _call_store(name, user_id=bob.user_id, session_id=session_id))


@pytest.mark.parametrize("name", _SERVICE_READS)
def test_every_service_read_path_returns_nothing_for_a_foreign_credential(name, temp_db):
    """AC 4, over the service, driven with bob's resolved `Identity`."""
    ana, bob = _seed_two_users()
    session_id = _seeded_transcript(ana)

    _assert_returns_nothing(name, _call_service(name, identity=bob, session_id=session_id))


def test_the_owner_still_reads_everything_a_stranger_could_not(temp_db):
    """The control. Every assertion above is satisfied by a function that
    returns nothing to *anyone*, so the same reads are driven with ana's own
    credential and must find the rows bob could not."""
    ana, bob = _seed_two_users()
    session_id = _seeded_transcript(ana)

    assert database.get_chat_session(session_id, ana.user_id) is not None
    assert [s.session_id for s in database.list_chat_sessions(ana.user_id)] == [session_id]
    assert len(database.list_chat_messages(session_id, ana.user_id)) == 2
    assert database.count_chat_sessions(ana.user_id) == 1
    assert chat_sessions.get(ana, session_id) is not None
    assert chat_sessions.owns(ana, session_id) is True
    assert [s.session_id for s in chat_sessions.list_for(ana)] == [session_id]
    assert len(chat_sessions.messages_for(ana, session_id)) == 2


# --------------------------------------------------------------------------
# AC 5 -- every write path, driven with a foreign credential, changes nothing
# --------------------------------------------------------------------------


def _drive_and_assert_nothing_changed(driver, name: str, **kwargs) -> None:
    """AC 5: "the database is byte-identical to before -- asserted by counting
    rows in both tables, not by trusting the return value".

    Both tables are captured whole, not just counted, because a foreign `rename`
    that changed a title leaves the counts equal and the database different.

    The write paths do not all answer the same way, and that is deliberate
    rather than a gap: `rename`, `touch` and `delete` return `False`, while
    `append_chat_message` raises -- `app/db/database.py` gives the reason ("a
    read that finds nothing is an ordinary outcome, a write that silently lands
    nowhere is not") and the service wraps it as `ChatSessionError`. So both
    arms are accepted, and the invariant that actually matters -- nothing was
    written -- is asserted identically in each.
    """
    before_sessions, before_messages = _count("chat_sessions"), _count("chat_messages")
    before = _snapshot()

    try:
        result = driver(name, **kwargs)
    except (StorageError, ChatSessionError):
        pass
    else:
        assert not result, f"{name} reported success for a foreign credential: {result!r}"

    assert _count("chat_sessions") == before_sessions, name
    assert _count("chat_messages") == before_messages, name
    assert _snapshot() == before, f"{name} changed a row it does not own"


@pytest.mark.parametrize("name", _STORE_WRITES)
def test_every_store_write_path_changes_nothing_for_a_foreign_credential(name, temp_db):
    """AC 5, over the store."""
    ana, bob = _seed_two_users()
    session_id = _seeded_transcript(ana)

    _drive_and_assert_nothing_changed(
        _call_store, name, user_id=bob.user_id, session_id=session_id
    )


@pytest.mark.parametrize("name", _SERVICE_WRITES)
def test_every_service_write_path_changes_nothing_for_a_foreign_credential(name, temp_db):
    """AC 5, over the service."""
    ana, bob = _seed_two_users()
    session_id = _seeded_transcript(ana)

    _drive_and_assert_nothing_changed(
        _call_service, name, identity=bob, session_id=session_id
    )


def test_the_owners_own_writes_still_land(temp_db):
    """The control for AC 5, for the same reason the read control exists: a
    store that refused every write would satisfy every assertion above."""
    ana, _bob = _seed_two_users()
    session_id = _seeded_transcript(ana)

    assert database.rename_chat_session(session_id, ana.user_id, "Renamed") is True
    assert database.touch_chat_session(session_id, ana.user_id) is True
    assert isinstance(
        database.append_chat_message(_stored(session_id, "third"), session_id, ana.user_id),
        int,
    )
    assert _count("chat_messages") == 3
    assert database.delete_chat_session(session_id, ana.user_id) is True
    assert _count("chat_sessions") == 0
    assert _count("chat_messages") == 0


# --------------------------------------------------------------------------
# AC 6 -- a refused delete touches neither the evidence nor the transcript
# --------------------------------------------------------------------------


def test_a_foreign_delete_leaves_audit_logs_and_the_owners_messages_alone(temp_db):
    """AC 6, through both layers.

    `audit_logs` is untouched even by a *successful* delete -- PRD Section 9:
    deleting a conversation deletes a conversation, it does not edit the record
    of what was asked. Here nothing is deleted at all, so both claims are
    checked: the evidence count is unchanged, and so is the owner's transcript.

    `chat_messages` has no `user_id` column of its own, which is what makes the
    second half worth asserting: a message delete scoped by `session_id` alone
    would wipe ana's transcript while still returning `False`.
    """
    ana, bob = _seed_two_users()
    session_id = _seeded_transcript(ana)
    insert_audit_log(AuditLog(timestamp="2026-09-03T10:00:00Z", user_id="ana", prompt_hash="h1"))
    insert_audit_log(AuditLog(timestamp="2026-09-03T10:00:01Z", user_id="ana", prompt_hash="h2"))

    audit_before = count_audit_logs()
    messages_before = len(database.list_chat_messages(session_id, ana.user_id))
    assert (audit_before, messages_before) == (2, 2)

    assert database.delete_chat_session(session_id, bob.user_id) is False
    assert chat_sessions.delete(bob, session_id) is False

    assert count_audit_logs() == audit_before
    assert len(database.list_chat_messages(session_id, ana.user_id)) == messages_before
    assert database.get_chat_session(session_id, ana.user_id) is not None
