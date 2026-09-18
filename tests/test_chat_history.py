"""PRD-010 STORY-011 -- `chat_history.assemble` and `chat_history.fit`.

Two functions, tested at two different levels. `assemble` is exercised against
a real transcript in the dev database, because what it is really asserting is a
claim about `chat_messages` rows: that an answered exchange is recoverable from
the `assistant` row alone (PRD Section 6.4, facts 1 and 2), and that nothing
else in the table contributes. `fit` is pure, so it is exercised directly, with
its limits passed in.

PRD Sections 4 (History), 5 (stories 1-3), 6.4 (D3, D4, D5), 6.5 (D2), 7 (F7),
9.1, 11.

The vacuity traps are closed deliberately and in the same shape throughout: an
exclusion test always asserts what *did* survive, never only that something is
absent, because "absent" is also what a broken `assemble` returning `[]` for
everything would produce.
"""

import ast
import inspect
import os
import pathlib
import random
import uuid

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest  # noqa: E402  -- after the bootstrap, as elsewhere in this suite

from app.config import settings  # noqa: E402
from app.db.database import (  # noqa: E402
    append_chat_message,
    create_chat_session,
    insert_user,
)
from app.db.models import StoredMessage, User  # noqa: E402
from app.models.messages import Message  # noqa: E402
from app.services import chat_history, chat_sessions  # noqa: E402
from app.services.identity import Identity  # noqa: E402
from app.services.query_pipeline import _context_limit_exceeded  # noqa: E402

ONE_INSTANT = "2026-09-17T10:00:00Z"

# The kinds that are not an answered exchange. The seven of
# `tests/test_chat_sessions.py:80-88` minus `assistant`, plus `context_limit`:
# STORY-013 adds that bubble, but `kind` is an unconstrained TEXT column, so the
# row can be written today. `assemble` filters on `kind == "assistant"` rather
# than on a deny-list, which is why it is already closed over kinds that do not
# exist yet and STORY-013 needs no change in this file.
UNANSWERED_KINDS = (
    ("user", {"prompt": "what is the retention policy?"}),
    ("duplicate", {"first_query_at": "2026-09-03T09:58:00Z"}),
    ("injection", {"pattern": "ignore previous instructions"}),
    ("forbidden", {"required_permission": "query:submit"}),
    ("upstream_error", {"detail": "502 from openrouter"}),
    ("internal_error", {"detail": "unhandled in run_query"}),
    ("context_limit", {"detail": "context limit: characters 250000 > 200000"}),
)


# --------------------------------------------------------------------------
# Helpers -- local copies, so this module does not depend on another's fixtures
# --------------------------------------------------------------------------


def _seed_users() -> None:
    """Two real users, so a foreign id in a test is a foreign id that exists."""
    insert_user(User(user_id="ana", role="user", token_hash="hash-ana"))
    insert_user(User(user_id="bob", role="user", token_hash="hash-bob"))


def _identity(user_id: str = "ana") -> Identity:
    return Identity(user_id=user_id, role="user")


def _session(owner: str = "ana", title: str = "a chat") -> str:
    _seed_users()
    return create_chat_session(owner, title)


def _row(session_id: str, kind: str = "assistant", *, owner: str = "ana", **fields) -> int:
    """One `chat_messages` row, through the real write path."""
    defaults = {"session_id": session_id, "kind": kind, "content": f"{kind} content"}
    defaults.update(fields)
    return append_chat_message(StoredMessage(**defaults), session_id, owner)


def _exchange(session_id: str, question: str, answer: str, *, owner: str = "ana") -> int:
    """One answered exchange: the `assistant` row that holds both halves."""
    return _row(
        session_id,
        "assistant",
        owner=owner,
        prompt=question,
        content=answer,
        created_at=ONE_INSTANT,
    )


def _pairs(messages) -> list:
    """`[(role, content), ...]` -- so order *within* a pair is asserted too."""
    return [(message.role, message.content) for message in messages]


def _history(exchanges: int) -> list[Message]:
    """`exchanges` whole exchanges, the shape `assemble` returns."""
    history: list[Message] = []
    for index in range(exchanges):
        history.append(Message("user", f"q{index}"))
        history.append(Message("assistant", f"a{index}"))
    return history


class _CountingRead:
    """A `messages_for` stand-in that counts its calls and returns a fixture."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def __call__(self, identity, session_id):
        self.calls += 1
        return self.rows


# --------------------------------------------------------------------------
# AC 1 -- one pair per assistant row, in id order
# --------------------------------------------------------------------------


def test_assemble_returns_one_user_assistant_pair_per_assistant_row(temp_db):
    """AC 1. `row.prompt` becomes the user turn, `row.content` the assistant one.

    Asserted as `(role, content)` tuples rather than as two sets, so the order
    *inside* each pair is pinned: a conversation whose answer precedes its
    question would satisfy any multiset check and would be nonsense upstream.
    """
    session_id = _session()
    _exchange(session_id, "first question", "first answer")
    _exchange(session_id, "second question", "second answer")
    _exchange(session_id, "third question", "third answer")

    assembled = chat_history.assemble(_identity("ana"), session_id)

    assert _pairs(assembled) == [
        ("user", "first question"),
        ("assistant", "first answer"),
        ("user", "second question"),
        ("assistant", "second answer"),
        ("user", "third question"),
        ("assistant", "third answer"),
    ]


def test_assemble_reads_the_transcript_in_id_order_not_by_timestamp(temp_db):
    """AC 1's "in `id` order", with the tie that makes the claim meaningful.

    Twenty exchanges sharing one `created_at` to the second -- the case a
    timestamp sort gets wrong. `tests/test_chat_sessions.py:645-667` makes the
    same argument for the read one layer down: a sort on a tied column is not
    deterministic, so a passing run over distinct timestamps proves nothing.
    `assemble` adds no sort of its own; this is the test that would notice if
    `list_chat_messages` lost its `ORDER BY id ASC`.
    """
    session_id = _session()
    for index in range(20):
        _exchange(session_id, f"q{index:02d}", f"a{index:02d}")

    assembled = chat_history.assemble(_identity("ana"), session_id)

    expected = []
    for index in range(20):
        expected.append(("user", f"q{index:02d}"))
        expected.append(("assistant", f"a{index:02d}"))
    assert _pairs(assembled) == expected


@pytest.mark.parametrize("exchanges", [0, 1, 5])
def test_assemble_emits_exactly_two_messages_per_answered_exchange(temp_db, exchanges):
    """Two per exchange, so the result is always pair-shaped.

    This is the invariant `fit`'s `ValueError` rests on: `assemble` cannot hand
    it an odd history, which is why an odd one is a caller bug rather than a
    case to degrade through.
    """
    session_id = _session()
    for index in range(exchanges):
        _exchange(session_id, f"q{index}", f"a{index}")

    assembled = chat_history.assemble(_identity("ana"), session_id)

    assert len(assembled) == 2 * exchanges
    assert len(assembled) % 2 == 0


# --------------------------------------------------------------------------
# AC 2 -- only answered exchanges, and the first one survives
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind,metadata", UNANSWERED_KINDS, ids=[k for k, _ in UNANSWERED_KINDS]
)
def test_no_unanswered_kind_contributes_a_message(temp_db, kind, metadata):
    """AC 2, and PRD Section 5 story 3: a refused prompt cannot come back in.

    Parametrized rather than looped so a failure names the kind that broke, and
    each case carries the metadata that kind really carries -- including a
    `prompt` on the `user` row, so the test cannot pass merely because the
    fixture left `prompt` empty and the row was skipped for the wrong reason.

    **The noise row is sandwiched between two real exchanges and the surviving
    four messages are asserted exactly.** Asserting only that the noise content
    is absent would pass against an `assemble` that returned `[]` for
    everything, which is the failure most likely to look green.
    """
    session_id = _session()
    _exchange(session_id, "before", "answer before")
    _row(session_id, kind, created_at=ONE_INSTANT, **metadata)
    _exchange(session_id, "after", "answer after")

    assembled = chat_history.assemble(_identity("ana"), session_id)

    assert _pairs(assembled) == [
        ("user", "before"),
        ("assistant", "answer before"),
        ("user", "after"),
        ("assistant", "answer after"),
    ]


def test_a_transcript_of_every_unanswered_kind_assembles_to_nothing(temp_db):
    """AC 2's "all" half: a session where nothing was ever answered sends no history.

    D4 by construction -- none of these rows is read at all, and neither are the
    `user` bubbles that preceded them.
    """
    session_id = _session()
    for kind, metadata in UNANSWERED_KINDS:
        _row(session_id, kind, created_at=ONE_INSTANT, **metadata)

    assert chat_history.assemble(_identity("ana"), session_id) == []


def test_the_first_exchange_survives_a_missing_first_user_bubble(temp_db):
    """AC 2's second sentence, and PRD Section 6.4 fact 1.

    The transcript is written the way the app really writes a new chat: no
    `user` row for exchange 1, because `_append_and_persist` ran with
    `session_id == ""` before `chat_sessions.create` returned an id. PRD Section
    11 asks for this by name -- "the first exchange of a new chat appears in the
    history of send 2 (built from the assistant row's `prompt`, not a missing
    user row)". Pairing rows positionally would lose it.
    """
    session_id = _session()
    _exchange(session_id, "first question", "first answer")  # no user row at all
    _row(session_id, "user", prompt="second question", content="second question",
         created_at=ONE_INSTANT)
    _exchange(session_id, "second question", "second answer")

    assembled = chat_history.assemble(_identity("ana"), session_id)

    assert assembled[0] == Message("user", "first question")
    assert _pairs(assembled) == [
        ("user", "first question"),
        ("assistant", "first answer"),
        ("user", "second question"),
        ("assistant", "second answer"),
    ]


def test_assemble_does_not_redact(temp_db):
    """D5 is the pipeline's, not assembly's (PRD Section 6.4).

    Stored `prompt` is raw and comes back raw. Redacting here would mask twice,
    and would feed a redacted string into `dedup_key` and `prompt_hash`, which
    PRD Section 9.2 forbids: "computed from **raw** text. No redacted string is
    ever hashed." STORY-007 redacts every message on every send instead.
    """
    session_id = _session()
    _exchange(session_id, "email jane@corp.com about it", "I will not")

    (user_turn, _) = chat_history.assemble(_identity("ana"), session_id)

    assert user_turn.content == "email jane@corp.com about it"
    assert "<EMAIL_ADDRESS>" not in user_turn.content


# --------------------------------------------------------------------------
# AC 3 -- the three empty cases, the unusable prompt, and one read
# --------------------------------------------------------------------------


def test_assemble_is_empty_when_history_is_off(temp_db, monkeypatch):
    """AC 3. The flag off yields `[]`, and no statement is issued at all.

    The tripwire is the half that matters. An empty list is also what an empty
    database returns, so a test checking only the value would pass against a
    module that read the transcript and threw it away. PRD Section 7 F8 relies
    on the stronger property when it says the history-off path costs "no extra
    read": same function, same arguments, nothing issued.

    The flag is read in `chat_sessions` and nowhere else; `chat_history` must
    not branch on it, and `tests/test_chat_sessions.py:1352` fails the whole
    tree if it does.
    """
    session_id = _session()
    _exchange(session_id, "q", "a")

    # Non-vacuity: with the flag on, this very session has history.
    assert chat_history.assemble(_identity("ana"), session_id) != []

    class _Tripwire:
        def __getattr__(self, name: str):
            raise AssertionError(f"reached database.{name} with history off")

    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)
    monkeypatch.setattr(chat_sessions, "database", _Tripwire())

    assert chat_history.assemble(_identity("ana"), session_id) == []


def test_assemble_is_empty_for_a_foreign_session(temp_db):
    """AC 3, and PRD Section 9.1: a tampered `active_session_id` pulls nothing.

    Bob is a real account, not an unknown id -- a test driven with a name that
    has no row can pass because the id is unknown rather than because the
    `WHERE` clause scopes. Ana's own call is asserted non-empty in the same
    test, so a read broken for everyone cannot make this pass.
    """
    ana_session = _session("ana")
    _exchange(ana_session, "ana's question", "ana's answer")

    assert chat_history.assemble(_identity("bob"), ana_session) == []
    assert chat_history.assemble(_identity("ana"), ana_session) != []


def test_assemble_is_empty_for_an_unknown_session(temp_db):
    """AC 3. A well-formed id that was never created reads as empty, not as an error."""
    _seed_users()

    assert chat_history.assemble(_identity("ana"), str(uuid.uuid4())) == []


@pytest.mark.parametrize("unusable", [None, ""], ids=["null-prompt", "empty-prompt"])
def test_assemble_skips_an_assistant_row_without_a_usable_prompt(temp_db, unusable):
    """AC 3's second sentence. No empty user turn is ever emitted.

    `prompt` is nullable (`app/db/models.py:165`) and `ChatState` stores
    `prompt=bubble.prompt or None`, so `""` and `NULL` are one fact by two
    routes -- hence one falsy branch rather than an `is None` check. An empty
    user turn would blank `query_pipeline._inspection_target`, which inspects
    the last user turn, and blank the `dedup_key` prefix.

    Sandwiched between two real exchanges, so the four survivors are asserted.
    """
    session_id = _session()
    _exchange(session_id, "before", "answer before")
    _row(session_id, "assistant", prompt=unusable, content="orphan answer",
         created_at=ONE_INSTANT)
    _exchange(session_id, "after", "answer after")

    assembled = chat_history.assemble(_identity("ana"), session_id)

    assert _pairs(assembled) == [
        ("user", "before"),
        ("assistant", "answer before"),
        ("user", "after"),
        ("assistant", "answer after"),
    ]
    assert all(message.content for message in assembled if message.role == "user")


def test_assemble_keeps_an_exchange_whose_answer_is_empty(temp_db):
    """The deliberate asymmetry with the test above -- named so it is not "fixed".

    An empty `prompt` means there is no user turn to send. An empty `content`
    means the user turn is real and the answer was blank, and dropping one
    message of that pair would break user/assistant alternation for every later
    turn.
    """
    session_id = _session()
    _exchange(session_id, "a question", "")

    assembled = chat_history.assemble(_identity("ana"), session_id)

    assert _pairs(assembled) == [("user", "a question"), ("assistant", "")]


def test_assemble_makes_exactly_one_transcript_read(temp_db, monkeypatch):
    """One read per call (story Technical Notes).

    STORY-012 runs this inside `run_in_pipeline`, and PRD Section 11 budgets the
    added latency of a send as "one `messages_for` read plus per-turn
    redaction". A second read would be invisible in every other test here and
    would double that budget.
    """
    spy = _CountingRead(
        [StoredMessage(session_id="s", kind="assistant", content="a", prompt="q")]
    )
    monkeypatch.setattr(chat_sessions, "messages_for", spy)

    assembled = chat_history.assemble(_identity("ana"), "s")

    assert spy.calls == 1
    assert _pairs(assembled) == [("user", "q"), ("assistant", "a")]


def test_assemble_propagates_a_storage_failure(temp_db, monkeypatch):
    """`ChatSessionError` travels unchanged; this module declares no twin.

    Re-wrapping it would give `ChatState` two exception names for one fact,
    which is the coupling `chat_sessions.ChatSessionError` already exists to
    prevent. STORY-014's degraded arm catches this type.
    """

    def _boom(identity, session_id):
        raise chat_sessions.ChatSessionError("messages_for failed: boom")

    monkeypatch.setattr(chat_sessions, "messages_for", _boom)

    with pytest.raises(chat_sessions.ChatSessionError, match="boom"):
        chat_history.assemble(_identity("ana"), "s")


# --------------------------------------------------------------------------
# AC 4 and AC 5 -- fit, the stated behaviours
# --------------------------------------------------------------------------


def test_fit_returns_everything_and_zero_when_it_all_fits():
    """AC 4's last sentence: `(history + [new_turn], 0)`, and a fresh list."""
    history = _history(3)
    new_turn = Message("user", "new")

    fitted, dropped = chat_history.fit(history, new_turn, 100, 100_000)

    assert fitted == history + [new_turn]
    assert dropped == 0
    assert fitted is not history


@pytest.mark.parametrize(
    "max_messages,kept_exchanges,expected_dropped",
    [
        (11, 5, 0),  # exactly at the maximum: fits, because the check is `<=`
        (10, 4, 1),
        (9, 4, 1),  # the odd/even pair: an off-by-one in `<=` breaks one of these
        (6, 2, 3),
        (5, 2, 3),  # a total is always odd, so an even maximum buys nothing extra
        (1, 0, 5),  # the floor, reached by the message limit
    ],
)
def test_fit_drops_the_oldest_whole_exchange_for_the_message_limit(
    max_messages, kept_exchanges, expected_dropped
):
    """AC 4. Oldest first, whole exchanges, the new turn last.

    The `(9, 4)` and `(10, 4)` rows and the `(5, 2)` / `(6, 2)` rows are the
    point of the table: history plus one new turn is always an odd number of
    messages, so raising an odd maximum by one admits nothing more. A `<`
    written where `<=` belongs moves every one of these by an exchange.
    """
    history = _history(5)
    new_turn = Message("user", "new")

    fitted, dropped = chat_history.fit(history, new_turn, max_messages, 100_000)

    assert fitted == history[len(history) - 2 * kept_exchanges:] + [new_turn]
    assert dropped == expected_dropped
    assert fitted[-1] == new_turn


@pytest.mark.parametrize(
    "max_characters,kept_exchanges,expected_dropped",
    [
        (23, 5, 0),  # 5 exchanges = 20 chars, + "new" = 23: exactly at the maximum
        (22, 4, 1),
        (11, 2, 3),  # admits exactly the last two exchanges plus the new turn
    ],
)
def test_fit_drops_the_oldest_whole_exchange_for_the_character_limit(
    max_characters, kept_exchanges, expected_dropped
):
    """AC 4, counted in characters. Each exchange here is 4 characters, the turn 3.

    The counts are chosen so the boundary is exact rather than comfortable:
    `23` is the total, and it fits.
    """
    history = _history(5)
    new_turn = Message("user", "new")

    fitted, dropped = chat_history.fit(history, new_turn, 100, max_characters)

    assert fitted == history[len(history) - 2 * kept_exchanges:] + [new_turn]
    assert dropped == expected_dropped
    assert sum(len(message.content) for message in fitted) <= max_characters


def test_fit_never_splits_an_exchange():
    """AC 4's "never splits a pair", swept rather than sampled.

    For every reachable message limit the history part of the output is an even
    number of messages and still alternates user/assistant. The only slice
    `fit` takes is `kept[2:]`, so this is structural -- but a later "optimization"
    that shaved one message to squeeze under a limit would show up here and
    nowhere else.
    """
    history = _history(5)
    new_turn = Message("user", "new")

    for max_messages in range(1, 2 * 5 + 2):
        fitted, _ = chat_history.fit(history, new_turn, max_messages, 100_000)

        body = fitted[:-1]
        assert len(body) % 2 == 0, f"max_messages={max_messages}"
        for index, message in enumerate(body):
            expected = "user" if index % 2 == 0 else "assistant"
            assert message.role == expected, f"max_messages={max_messages}, {index}"


def test_the_new_turn_is_always_last():
    """AC 4, swept over every combination of the two limits.

    Iterated rather than parametrized for the reason given in
    `test_fit_holds_its_properties_over_random_histories`: 55 database resets
    for a pure function. The case is named in the assertion.
    """
    history = _history(5)
    new_turn = Message("user", "new")

    for max_messages in range(1, 2 * 5 + 2):
        for max_characters in (1, 3, 11, 23, 100_000):
            fitted, _ = chat_history.fit(
                history, new_turn, max_messages, max_characters
            )

            assert fitted, f"empty output: {max_messages}, {max_characters}"
            assert fitted[-1] == new_turn, f"{max_messages}, {max_characters}"


def test_fit_reports_the_limit_it_was_given_not_the_settings(monkeypatch):
    """`fit` is pure: the limits are arguments (story Technical Notes).

    Settings are set to refuse everything, and `fit` ignores them, because
    STORY-012 owns the choice of limits at the call site. The static twin of
    this is `test_assemble_and_fit_never_read_the_context_settings`.
    """
    monkeypatch.setattr(settings, "CONTEXT_MAX_MESSAGES", 1)
    monkeypatch.setattr(settings, "CONTEXT_MAX_CHARACTERS", 1)
    history = _history(3)
    new_turn = Message("user", "new")

    fitted, dropped = chat_history.fit(history, new_turn, 100, 100_000)

    assert fitted == history + [new_turn]
    assert dropped == 0


@pytest.mark.parametrize("exchanges", [1, 2, 5])
def test_fit_returns_only_the_new_turn_when_it_alone_exceeds_the_characters(exchanges):
    """AC 5, as the literal expression the story states: `([new_turn], len(history) // 2)`.

    The pipeline then refuses it (D2). `fit` does not refuse -- see
    `test_a_fitted_conversation_is_never_refused_for_the_limits_it_was_fitted_to`
    for the other half of that handoff.
    """
    history = _history(exchanges)
    big_turn = Message("user", "x" * 500)

    assert chat_history.fit(history, big_turn, 100, 100) == (
        [big_turn],
        len(history) // 2,
    )


def test_fit_returns_only_the_new_turn_when_the_message_limit_admits_nothing_else():
    """The same floor, reached by the other limit.

    `fit` never returns `[]` and never returns a conversation without its new
    turn: there would be nothing for the pipeline to refuse, and a refusal
    needs a prompt to audit.
    """
    history = _history(4)
    new_turn = Message("user", "new")

    assert chat_history.fit(history, new_turn, 1, 100_000) == (
        [new_turn],
        len(history) // 2,
    )


def test_fit_does_not_mutate_its_input():
    """A caller's history survives a trimming call unchanged.

    `assemble`'s output is reused by STORY-012 after `fit` runs (for the
    duplicate key over the conversation as received), so a mutating `fit` would
    corrupt a value the caller still holds.
    """
    history = _history(5)
    before = list(history)
    new_turn = Message("user", "new")

    chat_history.fit(history, new_turn, 3, 100_000)

    assert history == before
    assert chat_history.fit([], new_turn, 100, 100_000) == ([new_turn], 0)


@pytest.mark.parametrize("length", [1, 3, 5])
def test_fit_rejects_a_history_that_is_not_whole_exchanges(length):
    """An odd history is a call-site bug, so it fails loudly.

    `assemble` emits two messages per row and cannot produce one. The precedent
    for a plain `ValueError` in a pure function is
    `duplicate_checker.dedup_key`, which raises one for an empty turn list
    rather than declaring an exception of its own. Degrading instead would mean
    slicing by twos until one orphaned message was paired with the new turn --
    a wrong conversation, and an inexact `len(history) // 2`.
    """
    history = [Message("user", "q")] * length

    with pytest.raises(ValueError, match="even"):
        chat_history.fit(history, Message("user", "new"), 100, 100_000)


def test_fit_accepts_an_empty_history():
    """`[]` is even, and is what a first send passes."""
    new_turn = Message("user", "new")

    assert chat_history.fit([], new_turn, 100, 100_000) == ([new_turn], 0)


# --------------------------------------------------------------------------
# The seam with the pipeline's limit check
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exchanges,max_messages,max_characters,turn_content,still_over",
    [
        (5, 100, 100_000, "new", False),  # nothing trimmed
        (5, 5, 100_000, "new", False),  # trimmed on messages
        (5, 100, 11, "new", False),  # trimmed on characters
        (5, 5, 11, "new", False),  # trimmed on both
        (20, 7, 30, "new", False),  # trimmed hard, from both ends of the table
        (5, 100, 100, "x" * 500, True),  # the floor: the new turn alone is over
    ],
)
def test_a_fitted_conversation_is_never_refused_for_the_limits_it_was_fitted_to(
    monkeypatch, exchanges, max_messages, max_characters, turn_content, still_over
):
    """The two halves of one contract, split across two modules.

    `fit` accepts on `<=`; `query_pipeline._context_limit_exceeded` breaches on
    strict `>`. Same two counts, same character expression, opposite sides of
    the same boundary. Nothing else in this suite would notice if one of them
    started counting something else -- and the symptom would be the worst
    possible one: a context-limit bubble on the very send that trimming was
    supposed to rescue.

    Reaching into a private function is the point rather than a shortcut: the
    boundary is private, so a test that only used public surfaces could not
    assert the pairing at all.

    The last row is the handoff in the other direction. When the new turn alone
    is over, `fit` returns it anyway and the pipeline *does* refuse it, which is
    AC 5's "so the pipeline refuses it (D2)" asserted rather than described.
    """
    history = _history(exchanges)
    new_turn = Message("user", turn_content)

    fitted, _ = chat_history.fit(history, new_turn, max_messages, max_characters)

    monkeypatch.setattr(settings, "CONTEXT_MAX_MESSAGES", max_messages)
    monkeypatch.setattr(settings, "CONTEXT_MAX_CHARACTERS", max_characters)
    exceeded = _context_limit_exceeded(fitted)

    if still_over:
        assert exceeded is not None
        assert exceeded[0] == "characters"
    else:
        assert exceeded is None


# --------------------------------------------------------------------------
# AC 5 -- fit as a property, over random histories
# --------------------------------------------------------------------------


def _random_case(seed: int):
    """A random but reproducible `(history, new_turn, max_messages, max_characters)`.

    `random.Random(seed)` rather than `hypothesis`: there is no property-testing
    library in `requirements.txt` and PRD Section 8's stack does not add one.
    The seed is parametrized rather than drawn at collection time, so the suite
    stays deterministic and a failure reproduces by name -- an unseeded
    `random` here would make this the flakiest test in the repository.
    """
    rng = random.Random(seed)
    exchanges = rng.randrange(0, 16)
    history: list[Message] = []
    for index in range(exchanges):
        history.append(Message("user", "q" * rng.randrange(0, 51)))
        history.append(Message("assistant", "a" * rng.randrange(0, 51)))
    new_turn = Message("user", "n" * rng.randrange(0, 51))
    return history, new_turn, rng.randrange(1, 41), rng.randrange(1, 601)


def test_fit_holds_its_properties_over_random_histories():
    """AC 5's property tests: 200 random cases, five properties each.

    Property 3 is asserted as a *contiguous suffix* identity rather than as
    containment: that is what pins "the oldest end was dropped and nothing was
    reordered" in one expression. A containment check would pass against a
    `fit` that dropped from the middle.

    **The 200 cases are iterated here rather than parametrized**, which is a
    deviation from this story's plan and is about the fixtures, not the
    properties. `tests/conftest.py:155` resets the database before *every* test,
    autouse, so each parametrized case would open a real libSQL connection for a
    function that performs no I/O -- and 200 of them in one module exhausts the
    dev server's sockets (`os error 10048`). Every assertion below names the
    seed, so a failure still reproduces exactly, which is the whole reason the
    plan reached for parametrization in the first place.
    """
    for seed in range(200):
        history, new_turn, max_messages, max_characters = _random_case(seed)

        fitted, dropped = chat_history.fit(
            history, new_turn, max_messages, max_characters
        )
        body = fitted[:-1]

        fits = (
            len(fitted) <= max_messages
            and sum(len(message.content) for message in fitted) <= max_characters
        )
        assert fits or fitted == [new_turn], f"neither fits nor the floor: seed {seed}"
        assert fitted[-1] == new_turn, f"new turn is not last: seed {seed}"
        assert history[len(history) - len(body):] == body, f"not a suffix: seed {seed}"
        assert len(body) % 2 == 0, f"split an exchange: seed {seed}"
        assert dropped == (len(history) - len(body)) // 2, f"wrong count: seed {seed}"


def test_the_random_cases_actually_exercise_trimming():
    """The property test above is only worth its runtime if the cases vary.

    Without this, a `_random_case` that happened to generate nothing but
    comfortable limits would make 200 green assertions about the branch `fit`
    never took. All three paths must be represented.
    """
    untrimmed = trimmed = floor = 0
    for seed in range(200):
        history, new_turn, max_messages, max_characters = _random_case(seed)
        fitted, dropped = chat_history.fit(
            history, new_turn, max_messages, max_characters
        )
        if history and fitted == [new_turn]:
            floor += 1
        elif dropped == 0:
            untrimmed += 1
        else:
            trimmed += 1

    assert untrimmed > 20, untrimmed
    assert trimmed > 20, trimmed
    assert floor > 10, floor


def test_fit_is_deterministic_and_leaves_its_input_alone():
    """Called twice on one case, `fit` answers the same and changes nothing."""
    for seed in range(20):
        history, new_turn, max_messages, max_characters = _random_case(seed)
        before = list(history)

        first = chat_history.fit(history, new_turn, max_messages, max_characters)
        second = chat_history.fit(history, new_turn, max_messages, max_characters)

        assert first == second, f"not deterministic: seed {seed}"
        assert history == before, f"mutated its input: seed {seed}"


# --------------------------------------------------------------------------
# Module shape
# --------------------------------------------------------------------------


def _module_tree() -> ast.Module:
    return ast.parse(inspect.getsource(chat_history))


def test_the_module_exports_exactly_assemble_and_fit():
    """Two public functions, so a helper does not become API by accident.

    Read off the module's own definitions rather than `dir()`, which would also
    list the imported `Message`, `Identity` and `chat_sessions`.
    """
    defined = {
        node.name
        for node in _module_tree().body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    }

    assert {name for name in defined if not name.startswith("_")} == {"assemble", "fit"}


def test_chat_history_imports_nothing_from_reflex_or_the_chat_ui():
    """Story Technical Notes: "No Reflex imports in this module."

    The dependency runs one way -- `chat_ui` imports `app.services`, never the
    reverse -- and a Reflex import here would also make `assemble` unusable from
    `POST /query`'s process in PRD-014.
    """
    imported = set()
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    offenders = [
        name
        for name in imported
        if name.split(".")[0] in {"reflex", "rx", "chat_ui"}
    ]
    assert offenders == [], offenders
    assert "app.config" not in imported


def test_assemble_and_fit_never_read_the_context_settings():
    """Story Technical Notes, both halves, as one structural check.

    `assemble` "must not read `settings.CONTEXT_MAX_*`"; `fit` "takes limits as
    arguments so it stays testable without settings". Asserted over the names
    the module actually references in code -- the prose in its docstrings
    discusses `settings` and `database` by name on purpose, and the `ast` walk
    is what keeps that prose from failing a test about behaviour.

    `CHAT_HISTORY_ENABLED` and `database` overlap with what
    `tests/test_chat_sessions.py:1352` and `:1225` already enforce across the
    whole tree. The overlap is deliberate rather than accidental: a breach
    caught here names `chat_history`, where the fix is, instead of surfacing in
    a sessions test that has nothing else to do with this module.
    """
    tree = _module_tree()
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}

    assert not names & {
        "settings",
        "CONTEXT_MAX_MESSAGES",
        "CONTEXT_MAX_CHARACTERS",
        "CHAT_HISTORY_ENABLED",
        "database",
        "list_chat_messages",
        "httpx",
        "log_query",
        "redact",
    }, names


def test_no_production_module_imports_chat_history_yet():
    """STORY-011 ships the module; STORY-012 is its first caller.

    The same criterion STORY-001 held itself to -- "`messages.py` is imported
    only by its tests" -- which is what makes this story provably unable to
    change any existing behaviour.

    **STORY-012 deletes this test.** Saying so here is what keeps it from being
    read later as a prohibition on using the module.
    """
    root = pathlib.Path(__file__).resolve().parents[1]
    module = root / "app" / "services" / "chat_history.py"

    offenders = []
    for path in sorted(
        list((root / "app").rglob("*.py"))
        + list((root / "chat_ui").rglob("*.py"))
        + list((root / "scripts").rglob("*.py"))
    ):
        if path == module:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                targets = [node.module or ""] + [alias.name for alias in node.names]
            else:
                continue
            if any("chat_history" in target for target in targets):
                offenders.append(f"{path.relative_to(root)}:{node.lineno}")

    assert offenders == [], offenders
