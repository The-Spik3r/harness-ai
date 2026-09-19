"""A chat session rebuilt as a conversation, and made to fit -- in one place.

PRD-010 Section 6.4 opens with two facts about `chat_messages`, and between them
they decide everything in this module.

**1. The first user bubble of a new chat is never persisted.**
`ChatState._append_and_persist` runs with `session_id == ""` before
`chat_sessions.create` has returned an id (README, *Limitations*), so the `user`
row for a session's first question does not exist. Rebuilding pairs by walking
`user` rows and attaching whatever followed them would therefore lose every
session's opening question -- the one turn a follow-up is most likely to refer
back to.

**2. Every `assistant` row already holds its whole exchange.** `row.prompt` is
the raw user text of that turn and `row.content` is the redacted reply, the only
form ever persisted (PRD-008 Section 9).

So `assemble` reads **only** `kind == "assistant"` rows and emits a pair from
each. Fact 2 is what makes fact 1 survivable.

**D4 holds by construction, not by exclusion.** `duplicate`, `injection`,
`forbidden`, `upstream_error`, `internal_error` and `context_limit` rows are
never *read*, and neither are the `user` bubbles that preceded them. There is no
deny-list of kinds here to keep in sync with the bubble model: a kind added
later -- STORY-013's `context_limit` is the next one -- is excluded the moment it
exists, because it is not `"assistant"`. A refused prompt cannot come back in
through history (PRD Section 5, story 3).

**This module does not redact (D5).** Stored `prompt` is raw, and step 6 of PRD
Section 6.1 redacts every message on every send (STORY-007). Redacting here
would mask twice, and -- worse -- would feed a redacted string into `dedup_key`
and `prompt_hash`, which PRD Section 9.2 forbids outright: "`dedup_key` and
`prompt_hash` are computed from **raw** text. No redacted string is ever
hashed."

**This module does not check ownership and does not read the history flag.**
`chat_sessions.messages_for` already returns `[]` for a session that is off, one
that does not exist and one belonging to someone else (PRD Section 9.1), and a
second check here would be a second place to get it wrong. Two tests enforce
this from outside, and an edit that "helpfully" adds either check fails in a test
module that has nothing else to do with history assembly:
`tests/test_chat_sessions.py::test_no_module_outside_the_service_branches_on_chat_history_enabled`
fails on any reference to the flag identifier under `app/` or `chat_ui/`, and
`::test_no_module_outside_the_service_calls_the_store_session_functions` fails
any module outside the service that reaches `database.list_chat_messages` --
so the shorter read is not available even as an optimization.

`identity.role` is never read either. PRD Section 9 divides the two questions;
`authz.py` answers what a role may do, `chat_sessions.py` answers whose row this
is, and this module asks neither -- it hands the whole `Identity` down.

It imports nothing from `chat_ui/` and nothing from Reflex. The dependency runs
one way in this repository: `chat_ui/chat_ui/state.py` imports `app.services`,
never the reverse.

**Which half is pure.** `assemble` does exactly one read and is sync, so
STORY-012 calls it through `run_in_pipeline` and it never touches the event
loop. `fit` does no I/O and reads no `settings` -- its limits are arguments --
so it is called inline and is testable without configuration.
"""

from typing import Sequence

from app.models.messages import Message
from app.services import chat_sessions
from app.services.identity import Identity


def assemble(identity: Identity, session_id: str) -> list[Message]:
    """This session's answered exchanges as a conversation, oldest first.

    `[]` for history off, for an unknown session and for one this identity does
    not own -- all three from `chat_sessions.messages_for`, which is the single
    place those rules live (PRD Section 9.1). Nothing here distinguishes them,
    and nothing here re-derives them.

    **The user turn comes from `row.prompt`, not from the preceding `user`
    row.** That is fact 1 in the module docstring: the first exchange of a new
    chat has no `user` row at all, so pairing rows positionally would silently
    drop it. Read this way, send 2 of a brand-new chat still carries send 1 --
    the property PRD Section 11 asks for by name.

    **An assistant row whose `prompt` is `NULL` or empty is skipped rather than
    emitting `Message("user", "")`.** The column is nullable
    (`app/db/models.py:165`) and `ChatState` stores `prompt=bubble.prompt or
    None`, so `""` and `NULL` are one fact arriving by two routes. An empty user
    turn is not a turn: it would blank `query_pipeline._inspection_target`,
    which inspects the last user turn, and blank the `dedup_key` prefix that
    PRD-009 derives from the conversation. Pre-PRD-008 rows and any future
    writer that omits `prompt` land here.

    **An assistant row whose `content` is empty is *not* skipped**, and the
    asymmetry is deliberate. The user half of that exchange is real, and
    dropping one message of a pair would break user/assistant alternation for
    every turn after it. `content` is `NOT NULL` at the table
    (`app/db/models.py:163`), so `""` is the only degenerate value reachable.

    The rows arrive in `id` order and are used in that order. `ORDER BY id ASC`
    is `database.list_chat_messages`' guarantee and its docstring explains why it
    is not a timestamp sort; re-sorting here would hide a regression in that
    clause rather than defend against one.

    `chat_sessions.ChatSessionError` propagates unchanged. Wrapping it in a name
    of this module's own would give `ChatState` two exceptions to catch for one
    fact, which is the coupling `chat_sessions` already exists to prevent.

    Nothing is redacted. See D5 in the module docstring.
    """
    history: list[Message] = []
    for row in chat_sessions.messages_for(identity, session_id):
        if row.kind != "assistant":
            continue
        if not row.prompt:
            continue
        history.append(Message("user", row.prompt))
        history.append(Message("assistant", row.content))
    return history


def _characters(messages: Sequence[Message]) -> int:
    """The same count `query_pipeline._context_limit_exceeded` makes.

    Written as its own helper so the expression exists once and can be compared
    with the pipeline's by eye. If the two ever disagree, `fit` trims a
    conversation to a size the pipeline then refuses.
    """
    return sum(len(message.content) for message in messages)


def fit(
    history: Sequence[Message],
    new_turn: Message,
    max_messages: int,
    max_characters: int,
) -> tuple[list[Message], int]:
    """History plus the new turn, trimmed from the oldest end until it fits, and
    how many whole exchanges that cost.

    Returns `(messages, dropped)`. `dropped` counts **exchanges**, not messages:
    that is what STORY-013's footer says ("3 earlier exchanges were not sent to
    the model") and what STORY-010's `chat_messages.history_trimmed` stores.

    **Paired with `query_pipeline._context_limit_exceeded`, deliberately.** That
    function counts `len(messages)` and `sum(len(message.content) ...)` and
    breaches on strict `>`; this one accepts on `<=` over the identical two
    counts. Same arithmetic, opposite side of the same boundary, so a
    conversation fitted to a pair of limits is never then refused for them --
    `tests/test_chat_history.py::test_a_fitted_conversation_is_never_refused_for_the_limits_it_was_fitted_to`
    is what keeps that true. The symptom of drift would be a context-limit
    bubble on the very send that trimming was supposed to rescue.

    **Pure on purpose.** The limits are arguments, not `settings` reads, so
    STORY-012 owns the choice of limits at the call site and every test here
    states them inline instead of monkeypatching configuration.

    **The oldest whole exchange, never half of one.** The only slice taken is
    `kept[2:]`, so "never splits a pair" is structural rather than checked. The
    new turn is appended last on every return path.

    **The floor is `[new_turn]`, never `[]`.** When the new turn alone breaks a
    limit -- or when `max_messages` admits nothing else -- every exchange is
    dropped and the turn is returned on its own, with `dropped == len(history)
    // 2`. That falls out of the loop rather than being special-cased: a
    separate "does the new turn alone fit" branch would duplicate the arithmetic
    and could disagree with it. Refusing is not this function's job; the
    pipeline re-checks the limits and refuses the one-message conversation if it
    is still over (PRD-010 D2).

    An odd-length `history` raises `ValueError`. `assemble` cannot produce one
    -- it emits two messages per row -- so an odd history is a programming error
    at the call site, and the precedent for saying so loudly in a pure function
    is `duplicate_checker.dedup_key`, which raises `ValueError` for an empty
    turn list rather than declaring an exception of its own. Staying silent
    would mean slicing by twos off an odd list until one orphaned message was
    paired with the new turn: a wrong conversation instead of a loud failure,
    and an inexact `len(history) // 2`. `[]` is even, and legal.
    """
    if len(history) % 2:
        raise ValueError(
            "history must be whole exchanges (an even number of messages); "
            f"got {len(history)}"
        )

    kept = list(history)  # a copy: fit never mutates its caller's list
    dropped = 0
    while True:
        candidate = kept + [new_turn]
        # `<=` against the pipeline's strict `>`: exactly at a maximum fits.
        if len(candidate) <= max_messages and _characters(candidate) <= max_characters:
            return candidate, dropped
        if not kept:
            # Nothing left to drop. `dropped` is already len(history) // 2.
            return [new_turn], dropped
        kept = kept[2:]  # the oldest whole exchange, both halves together
        dropped += 1
