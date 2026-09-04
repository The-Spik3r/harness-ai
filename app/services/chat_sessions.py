"""Whose row this is, and whether history is on at all -- in one place.

PRD-008 Section 6 names this module and what it holds, verbatim:
"`app/services/chat_sessions.py` holds the ownership rule and the
`CHAT_HISTORY_ENABLED` short-circuit in one place, the way `authz.py` holds the
permission matrix. `ChatState` calls the service, never `database.py` directly."

Two rules live here and nowhere else.

**The Identity is converted to an owner exactly once, here.** Every function
below takes an `Identity` and passes `identity.user_id` down; nothing outside
this module calls `app/db/database.py`'s session or message functions, and
nothing outside it hands one of those functions a bare `user_id` string. Those
functions require an undefaulted `user_id` (PRD Risk 2: "the rule lives in the
signature"), and this module is the only caller that has to satisfy it.

**No caller branches on the flag.** PRD Section 6, again verbatim: "with
`CHAT_HISTORY_ENABLED=false` the service returns empty lists and writes nothing,
and the rail renders as absent. **No caller branches on the flag.**" An
`if settings.CHAT_HISTORY_ENABLED` anywhere but here and `app/config.py` is a
defect, and `tests/test_chat_sessions.py` fails on one rather than trusting that
nobody writes it.

Both rules are about what callers do *not* have to remember, which is why the
short-circuits below return a value the caller can proceed with -- `None`, `[]`,
`False` -- rather than raising. A caller that must handle `HistoryDisabled` is a
caller branching on the flag with extra steps.

What this module is *not* is an authorization check. `authz.py` answers what a
role may do; this answers whose row this is. PRD Section 9 requires both to
apply without either substituting for the other -- "`query:submit` still gates
sending; owning a session grants nothing beyond reading and deleting it" -- so
there is no new permission here, no call into `authz`, and `identity.role` is
never read. The break-glass `admin` identity gets no special case either: it
"owns its own sessions like any other user and gains no read access to anyone
else's."

It imports nothing from `chat_ui/`. The dependency runs one way in this
repository -- `chat_ui/chat_ui/state.py` imports `app.services`, never the
reverse -- and `create()` below keeps it that way while still not owning the
auto-title rule; see its docstring.
"""

from contextlib import contextmanager
from typing import Callable, Iterator, Optional

from app.config import settings
from app.db import database
from app.db.errors import StorageError
from app.db.models import ChatSession, StoredMessage
from app.services.identity import Identity


class ChatSessionError(Exception):
    """A session or transcript operation failed at the storage layer.

    The same move `app/services/duplicate_checker.py` makes with
    `DuplicateCheckError`: a `StorageError` is a fact about the database, and
    letting it travel into `ChatState` would make the caller import
    `app.db.errors` to catch it -- which is the coupling this service exists to
    prevent. STORY-014's degraded arm catches this one type and reports "the
    turn was not saved".
    """


@contextmanager
def _wrapped(operation: str) -> Iterator[None]:
    """`StorageError` in, `ChatSessionError` out, with the operation named.

    `duplicate_checker.check_duplicate` writes this arm inline because it has
    exactly one call to guard. This module has nine, and nine copies of a
    three-line `except` is nine places for the ninth to be forgotten -- the
    failure mode `app/db/errors.py`'s own docstring describes for an `except`
    clause that stops matching: "an `except` that stops firing does not raise,
    it lets the exception through."

    `operation` is the service function's own name rather than the store's, so
    the message reads in the caller's vocabulary ("append_message failed"), and
    `from exc` keeps the `StorageError` on `__cause__` for anything that needs
    the storage detail.
    """
    try:
        yield
    except StorageError as exc:
        raise ChatSessionError(f"{operation} failed: {exc}") from exc


def create(
    identity: Identity,
    first_prompt: str,
    derive_title: Callable[[str], str],
) -> Optional[str]:
    """Opens a new session for this identity, titled from its first prompt.

    Returns the new `session_id`, or `None` when history is off -- and `None`
    there is a value to proceed with, not a failure. STORY-013's lazy-create arm
    reads it as "there is no session to record against" and sends the turn
    anyway, which is what "the chat behaves exactly as it did before this PRD"
    (PRD Section 9) means in practice.

    **`derive_title` is injected, and that is what keeps the auto-title rule out
    of this module.** STORY-012 owns the rule and puts `derive_title(prompt)` in
    `chat_ui/chat_ui/formatting.py` (PRD Section 6's file map). This module
    cannot import it: the dependency in this repository runs `chat_ui` -> `app`
    and never back, and an `app` module reaching into the Reflex package would
    couple the FastAPI application to it. Taking the function as a parameter
    delegates the derivation literally -- the service calls the rule and does
    not know it -- while `first_prompt` stays in the signature, so the caller
    still hands over a prompt rather than a title it had to remember to derive.

    It has no default on purpose. Any default would be a derivation living
    *here*, which is the reimplementation the story forbids.

    The id is the store's: `create_chat_session` mints a UUID4 and takes no
    caller-supplied id, because the value furthest up this path is
    `ChatState.active_session_id`, a Reflex state var the client can set
    (PRD Risk 3).
    """
    if not settings.CHAT_HISTORY_ENABLED:
        return None

    with _wrapped("create"):
        return database.create_chat_session(identity.user_id, derive_title(first_prompt))


def list_for(identity: Identity) -> list[ChatSession]:
    """This identity's sessions, newest activity first, capped by configuration.

    **It takes no `limit`, and no caller supplies one.** The cap is
    `settings.CHAT_SESSION_LIMIT` -- a deployment decision, not a UI one, so the
    rail cannot widen it by asking for more. `database.list_chat_sessions`
    defaults its own limit and says why the policy is not its own: "the
    flag-and-limit policy belongs to `app/services/chat_sessions.py`, where PRD
    Section 6 also puts the `CHAT_HISTORY_ENABLED` short-circuit." This is that
    place.

    The setting is read here, on every call, rather than captured at import.
    `app/config.py`'s validator has already refused a value below 1, so there is
    no floor to re-check.

    Empty when history is off, and empty for an identity with no sessions --
    deliberately the same answer. A rail that could tell "disabled" from "none
    yet" would be a rail branching on the flag.
    """
    if not settings.CHAT_HISTORY_ENABLED:
        return []

    with _wrapped("list_for"):
        return database.list_chat_sessions(identity.user_id, limit=settings.CHAT_SESSION_LIMIT)


def get(identity: Identity, session_id: str) -> Optional[ChatSession]:
    """This identity's session, or `None`.

    A session belonging to someone else returns `None`, exactly as one that does
    not exist does. The store already holds that line
    (`database.get_chat_session`) and this function adds no branch that could
    tell the two apart -- the precedent `app/services/identity.py`'s `resolve()`
    states for credentials: "None covers every failure case alike ... so the
    caller cannot distinguish them." A caller that could would have a membership
    oracle over other people's session ids.
    """
    if not settings.CHAT_HISTORY_ENABLED:
        return None

    with _wrapped("get"):
        return database.get_chat_session(session_id, identity.user_id)


def rename(identity: Identity, session_id: str, title: str) -> bool:
    """Retitles this identity's session. `False` when there is no such owned row.

    `False` covers the unknown session and the foreign one without separating
    them, for the reason `get` above gives. It is also what history-off returns,
    so a caller writes one `if not renamed:` arm and never learns which of the
    three it hit.

    Renaming does not move `updated_at` -- `database.rename_chat_session`
    records that omission as a decision: "a rename that bumped the timestamp
    would reorder the rail and move the row the user was looking at while they
    were looking at it." Nothing here re-derives the title either; STORY-012's
    derivation runs once, in `create`.
    """
    if not settings.CHAT_HISTORY_ENABLED:
        return False

    with _wrapped("rename"):
        return database.rename_chat_session(session_id, identity.user_id, title)


def touch(identity: Identity, session_id: str) -> bool:
    """Moves this identity's session to the top of the rail. `False` if not owned.

    The send path's reorder, called after the transcript write (PRD Section 6's
    diagram, STORY-014). With history off it returns `False` and writes nothing,
    which is the same shape the caller already handles for a session that is
    gone.
    """
    if not settings.CHAT_HISTORY_ENABLED:
        return False

    with _wrapped("touch"):
        return database.touch_chat_session(session_id, identity.user_id)


def delete(identity: Identity, session_id: str) -> bool:
    """Removes this identity's session and its transcript. `False` if not owned.

    One transaction in the store, and the message delete is scoped by ownership
    rather than by `session_id` alone -- `database.delete_chat_session` explains
    why that subselect is load-bearing. Nothing is added here; a second
    ownership check in this module would be a second place for the rule to drift
    from the one the statement enforces.

    `audit_logs` is untouched, by design (PRD Section 9): deleting a
    conversation deletes a conversation, it does not edit the record of what was
    asked.
    """
    if not settings.CHAT_HISTORY_ENABLED:
        return False

    with _wrapped("delete"):
        return database.delete_chat_session(session_id, identity.user_id)


def append_message(
    identity: Identity,
    session_id: str,
    message: StoredMessage,
) -> Optional[int]:
    """Writes one bubble into this identity's session, returning its row id.

    `None` when history is off, and nothing is written -- STORY-014 appends the
    bubble to `ChatState.messages` either way, so the turn is on screen whether
    or not it was recorded.

    **A foreign session and an unknown session raise, identically, and that is
    the ownership rule holding rather than leaking.** `database.append_chat_message`
    refuses both with one `StorageError` carrying one message, and says why a
    visible failure is right where the reads return empty: "a read that finds
    nothing is an ordinary outcome, a write that silently lands nowhere is not."
    Wrapping both in one `ChatSessionError` with one message keeps the two cases
    indistinguishable -- which is what the story asks for -- while still being
    audible. Returning `None` for them instead would collide with the history-off
    `None` above and hand STORY-014's degraded arm a successful-looking write
    that never happened.

    `message.session_id` is not the one used. The store reads the `session_id`
    parameter in both the column it writes and the `EXISTS` it checks, so
    ownership cannot be verified against one session and the row filed under
    another; this module deliberately does not reconcile the two values, because
    reconciling them here would be a second rule to keep in step with that one.
    """
    if not settings.CHAT_HISTORY_ENABLED:
        return None

    with _wrapped("append_message"):
        return database.append_chat_message(message, session_id, identity.user_id)


def messages_for(identity: Identity, session_id: str) -> list[StoredMessage]:
    """This identity's whole transcript for one session, in write order.

    Empty when history is off, empty for a session that does not exist, and
    empty for someone else's -- the same three-way sameness `get` above keeps,
    and for the same reason.

    **No `limit`, here or below.** `database.list_chat_messages` takes none by
    design: PRD Section 4 caps sessions, not messages within one, and "a partial
    transcript is a wrong transcript -- worse than a slow one, because nothing on
    screen says it is partial." `CHAT_SESSION_LIMIT` is not applied here; it caps
    the rail, and applying it to a transcript would silently truncate a
    conversation at the number of conversations a user may list.
    """
    if not settings.CHAT_HISTORY_ENABLED:
        return []

    with _wrapped("messages_for"):
        return database.list_chat_messages(session_id, identity.user_id)
