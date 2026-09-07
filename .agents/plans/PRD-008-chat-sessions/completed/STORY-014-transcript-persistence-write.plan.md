---
story: STORY-014
prd: PRD-008
slug: transcript-persistence-write
title: "Persist each bubble after it is appended, touch the session, and degrade without losing the turn"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-05
---

# Plan: Persist each bubble after it is appended, touch the session, and degrade without losing the turn

## Summary

`_do_send` currently appends a `ChatMessage` to `self.messages` in eight places and writes nothing. This story routes **all eight through one helper** — `_append_and_persist(bubble, identity, session_id)` — which appends first, then writes the same bubble with `chat_sessions.append_message(...)`, then `chat_sessions.touch(...)`, then moves the active chat to the front of `self.sessions`. The helper is the whole story: PRD Risk 5 is a *forgetting* failure as much as a storage one, and the story's own Technical Notes name the shape — *"one helper called wherever a bubble is added, so a ninth outcome added later cannot be persisted-by-forgetting."*

Three structural decisions carry it.

**The persistence is outside the lock, the append is inside it, and the helper owns both — which is why it cannot be called from inside an `async with self` block.** `_do_send` is a background task, so `self` is a `StateProxy`, and `reflex/istate/proxy.py:136-137` raises `ImmutableStateError("The state is already mutable. Do not nest `async with self` blocks.")` on a nested entry. Every one of the eight call sites therefore has its existing `async with self: self.messages.append(...)` block **replaced** by a bare `await self._append_and_persist(...)`, never wrapped by one. The helper opens the lock for the append, releases it, offloads the two database calls with `asyncio.to_thread(...)`, and re-enters the lock for the notice or the reorder.

**Two guarded arms, not one, because one notice cannot be true for both failures.** AC 5 requires the notice to say *the turn was not saved*; AC 6 requires a failed `touch` to *"not surface as a lost turn"*. If `append_message` succeeded and `touch` failed, the turn **was** saved, and reusing the not-saved string would state a falsehood in the interface — the thing `frontend-design` forbids most directly (*"never vague about what happened"*). So `append_message` gets its own `try` and its own notice, and `touch` plus the reorder get a second `try` and a second, quieter notice on the rail's existing `sessions_error` slot. Both catch bare `Exception`, per the story's Technical Notes.

**Nothing branches on `CHAT_HISTORY_ENABLED`, and AC 7 is met by not writing code.** With history off, STORY-013's create arm already leaves `session_id` as `None`, and the helper's `if identity is None or not session_id: return` guard falls through before any write — no call, no notice, no attempt. The same guard is what lets the invalid-credential arm (`state.py:178-188`), which has no `Identity` at all, go through the one helper like every other site instead of keeping a hand-rolled append that a future outcome could be copied from.

## User Story

As an employee
I want a blocked or failed turn to still be part of the conversation
So that the transcript is a true account and not just the answers — and a storage problem costs me the saving, never the answer I already paid for.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-014-transcript-persistence-write.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md` — Section 4 (Chat state), Section 5 (story 5), Section 6 (send path, the bubble/`content` table), Section 9, Section 12 Phase 3, Risk 5

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/chat_ui/state.py`, `chat_ui/chat_ui/copy.py`, `tests/test_chat_state.py`, `tests/test_copy.py` |
| Story | STORY-014 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |
| Depends on | STORY-013 ✅ (verified `status: done`, commit `ba43c5c`) |
| Blocks | STORY-015 |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `reflex-docs` (plugin, named in story frontmatter) | `chat_ui/AGENTS.md`, verbatim: *"For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory."* Governs the `async with self` boundary, the non-nesting rule, and the offload placement in the new helper. | Tasks 4, 5 |
| `reflex-process-management` (plugin, in `chat_ui/AGENTS.md`) | `chat_ui/AGENTS.md`, verbatim: *"When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill for the correct sequence and error investigation steps."* Its first step is `reflex compile --dry`, run from `chat_ui/`. | Task 9, Validation |
| `.agents/skills/frontend-design` | Listed and read in full. The story scopes it: *"`frontend-design` applies here only to the failure copy."* Its rule for that copy, verbatim: *"Treat failure and emptiness as moments for direction, not mood. Explain what went wrong and how to fix it, in the interface's voice rather than a person's. Errors don't apologize, and they are never vague about what happened."* No component file is touched; the rail's visual design is STORY-017/018. | Task 1 |

`.agents/skills/` was listed and holds exactly one skill (`frontend-design`); its `description` was read and matches this story only through the copy constants above.

### `reflex-docs` outcome — the two API facts this plan depends on

The skill was invoked; it directs to the reference documentation rather than to recall. Both facts below are verified against the pinned `reflex==0.9.6.post1` tree in `.venv/`, so the citation is the code that will actually run.

| Fact | Evidence |
|---|---|
| A background task receives a `StateProxy` as `self` and may mutate state **only** inside `async with self`. | `.venv/Lib/site-packages/reflex/istate/proxy.py:51-52`: *"A background task will be passed the `StateProxy` as `self`, so mutability can be safely performed inside an `async with self` block."* Reading a var outside one raises `ImmutableStateError` (`proxy.py:220-223`). |
| `async with self` blocks **may not nest**. | `.venv/Lib/site-packages/reflex/istate/proxy.py:132-137`: the proxy checks `self._self_actx_lock.locked() and current_task == self._self_actx_lock_holder` and raises `ImmutableStateError("The state is already mutable. Do not nest `async with self` blocks.")`. This is the constraint that fixes where the new helper may be called from. |

---

## Patterns to Follow

### Appending under the lock, calling the store off it — the shape `_do_send` already has

```python
# SOURCE: chat_ui/chat_ui/state.py:217-235 (STORY-013's lazy create)
if not session_id:
    try:
        session_id = await asyncio.to_thread(
            chat_sessions.create, identity, text, derive_title
        )
    except ChatSessionError as exc:
        session_id = None
        async with self:
            self.sessions_error = str(exc)
```

Every database call leaves the event loop with `asyncio.to_thread(...)`; every mutation happens inside `async with self`; the two are never interleaved in one block.

### Degrading rather than raising — the arm this story generalizes

```python
# SOURCE: chat_ui/chat_ui/state.py:222-227
except ChatSessionError as exc:
    # A broken rail does not block the composer: the turn is
    # sent unattached rather than refused.
    session_id = None
```

### Building a `ChatSessionSummary` with one clock read

```python
# SOURCE: chat_ui/chat_ui/state.py:128-138
# One clock read for the whole list, per format_activity's own
# docstring: "a rail of thirty rows shares one clock read".
now = datetime.now(timezone.utc)
self.sessions = [
    ChatSessionSummary(
        session_id=row.session_id,
        title=row.title,
        activity_info=format_activity(row.updated_at, now),
    )
    for row in rows
]
```

### The target dataclass

```python
# SOURCE: app/db/models.py:204-228
@dataclass
class StoredMessage:
    session_id: str
    kind: str
    content: str
    prompt: Optional[str] = None
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None
    audit_id: Optional[int] = None
    pii_redacted: bool = False
    pii_entities: Optional[str] = None       # comma-joined, as audit_logger.py:45 persists it
    pattern: Optional[str] = None
    required_permission: Optional[str] = None
    first_query_at: Optional[str] = None
    detail: Optional[str] = None
    created_at: Optional[str] = None         # append_chat_message() stamps it
    id: Optional[int] = None
```

`ChatMessage` (`chat_ui/chat_ui/models.py:4-22`) defaults its optional fields to `""` / `0`, while every corresponding column is nullable. The mapping must convert falsy to `None`, or a transcript fills with empty strings where the schema means *absent*. `duplicate_relative_info` and `duplicate_release_info` have **no columns** and are deliberately dropped — `app/db/models.py:118-122`: *"They are humanized copy, recomputed on load so they stay relative to now; a stored '2m ago' is wrong the moment it is read back. Their absence is a decision."*

### Copy voice

```python
# SOURCE: chat_ui/chat_ui/copy.py:22-27
# A credential can go bad mid-session (deactivated by an admin while the tab
# stays open). send() re-resolves on every call and surfaces this rather
# than silently keep using a role that no longer exists.
SESSION_INVALIDATED_ERROR = (
    "Your session credential is no longer valid. Sign out and sign in again."
)
```

A full sentence, sentence case, states what happened and what to do, no apology, no mechanism.

### Tests

```python
# SOURCE: tests/test_chat_state.py:1163-1185
@pytest.mark.asyncio
async def test_a_session_error_while_creating_sets_the_error_and_still_sends(
    temp_db, monkeypatch
):
    def _raise(*args, **kwargs):
        raise ChatSessionError("create failed: store is down")

    monkeypatch.setattr(chat_state_mod.chat_sessions, "create", _raise)
    captured = {}
    monkeypatch.setattr(
        chat_state_mod, "run_query", _capturing_run_query(captured=captured)
    )

    state = _make_state()
    await _send(state, "a prompt")

    assert "store is down" in state.sessions_error
    assert [m.kind for m in state.messages] == ["user", "assistant"]
```

Helpers already in the suite and reused unchanged: `_make_state()` (`:93`), `_send()` (`:100`), `_capturing_run_query()` (`:930`), `_session_rows()` (`:906`), `_backdate_session()` (`:917`), `_count_audit_rows()` (`:66`).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/copy.py` | UPDATE | The two failure notices — one for a transcript write that did not land, one for a rail order that did not move. |
| `chat_ui/chat_ui/state.py` | UPDATE | `transcript_error` var; `_to_stored_message`; `_append_and_persist`; `_promote_session`; all eight append sites routed through the helper; `logout()` clears the new var. |
| `tests/test_copy.py` | UPDATE | The two constants exist, are non-empty, and hold the voice. |
| `tests/test_chat_state.py` | UPDATE | The STORY-014 section: persistence on all seven kinds, redacted `assistant` content, touch + reorder, both degraded arms, `pending`, the audit-row independence, and the flag-off silence. |

No file is created. `app/` is untouched — every function this story calls (`chat_sessions.append_message`, `chat_sessions.touch`, `chat_sessions.get`) shipped in STORY-006 and is already documented as STORY-014's counterpart (`app/services/chat_sessions.py:229-231`, `:271-282`).

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: The two failure notices

- **File**: `chat_ui/chat_ui/copy.py`
- **Action**: UPDATE
- **Implement**: Append a new section after `# --- Session fallbacks ---`:

```python
# --- Transcript persistence ---------------------------------------------
# PRD-008 Risk 5: the model answered and the audit row is already written --
# only the saving failed, and the notice says exactly that much. It names the
# consequence the reader can act on (the turn is here until they reload)
# rather than the mechanism that produced it, and it does not apologize
# (frontend-design: "errors don't apologize, and they are never vague about
# what happened").
TRANSCRIPT_NOT_SAVED_NOTICE = (
    "This turn was not saved to your history. It stays on screen until you "
    "reload the page."
)
# The counterpart for a failed touch, and deliberately a different string.
# The write landed; only the ordering did not. Saying "not saved" here would
# be false, and STORY-014 AC 6 is explicit that a failed reorder "must not
# surface as a lost turn".
SESSION_ORDER_STALE_NOTICE = (
    "This chat is saved. The list order is out of date until you reload."
)
```

- **Mirror**: `chat_ui/chat_ui/copy.py:22-27` (`SESSION_INVALIDATED_ERROR`) for the comment-then-constant shape and the voice.
- **Validate**: `python -c "from chat_ui.chat_ui.copy import TRANSCRIPT_NOT_SAVED_NOTICE, SESSION_ORDER_STALE_NOTICE; print('ok')"`

### Task 2: `transcript_error` on `ChatState`

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: Declare `transcript_error: str = ""` beside `sessions_error` (`:68`), and import the two new constants from `.copy`. Comment it as the *turn's* notice slot, distinct from `sessions_error`, which is the *rail's*: one says a bubble is not in the database, the other says the list is stale, and conflating them would make one of the two messages a lie on every failure of the other. Note that nothing renders it yet — exactly as `sessions_error` was unrendered when STORY-013 introduced it; STORY-018/019 own the surface.
- **Mirror**: `chat_ui/chat_ui/state.py:66-68` — the three session vars STORY-013 added.
- **Validate**: `python -c "from chat_ui.chat_ui.state import ChatState; assert ChatState.__annotations__['transcript_error'] is str; print('ok')"`

### Task 3: `_to_stored_message(bubble, session_id)`

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: A module-level function above the class:

```python
def _to_stored_message(bubble: ChatMessage, session_id: str) -> StoredMessage:
    """One bubble as one `chat_messages` row.

    `ChatMessage` defaults its optional fields to "" and 0 because a Reflex Var
    cannot be None on the wire; every matching column is nullable and means
    *absent*. So every optional field is converted with `or None` -- a
    transcript full of empty strings would restore into bubbles that render an
    empty "Matched pattern" label instead of no label at all.

    `pii_entities` is comma-joined, matching how `app/services/audit_logger.py:45`
    already persists the same data and what `StoredMessage`'s own docstring asks
    for: "one encoding serves one concept."

    `duplicate_relative_info` and `duplicate_release_info` are dropped, and
    their absence is the schema's decision rather than an oversight --
    `app/db/models.py:118-122`: "a stored '2m ago' is wrong the moment it is
    read back." STORY-015 recomputes them from `first_query_at` on load.
    """
    return StoredMessage(
        session_id=session_id,
        kind=bubble.kind,
        content=bubble.content,
        prompt=bubble.prompt or None,
        model_used=bubble.model_used or None,
        tokens_used=bubble.tokens_used or None,
        audit_id=bubble.audit_id or None,
        pii_redacted=bubble.pii_redacted,
        pii_entities=",".join(bubble.pii_entities) or None,
        pattern=bubble.pattern or None,
        required_permission=bubble.required_permission or None,
        first_query_at=bubble.first_query_at or None,
        detail=bubble.detail or None,
    )
```

  Add `from app.db.models import ChatSession, StoredMessage` to the imports. This is the only `app.db` import in `chat_ui/` and both names are dataclasses, not calls: PRD Section 6's rule is *"`ChatState` calls the service, never `database.py` directly"*, and the service's own signature (`append_message(identity, session_id, message: StoredMessage)`) requires the caller to construct one.

- **Mirror**: `app/services/audit_logger.py:45` for the comma-join; `app/db/models.py:204-228` for the field order.
- **Validate**: `python -m pytest tests/test_chat_components_import.py -q`

### Task 4: `_append_and_persist` and `_promote_session`

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: Two methods on `ChatState`, placed directly above `_do_send`.

```python
def _promote_session(self, row: ChatSession, now: datetime) -> None:
    """Moves this session to the front of the rail, inserting it if new.

    Called under the lock, from `_append_and_persist` only. Sync on purpose: it
    touches no database and its one caller is already inside `async with self`.

    The row is the store's, not a locally built one. The title in particular
    must not be re-derived here -- `chat_ui/chat_ui/formatting.py:96-104` says
    `derive_title` is "called exactly once per session" and that "a renamed
    session must never drift back to its first prompt", so the rail shows the
    title that is actually stored.
    """
    remaining = [s for s in self.sessions if s.session_id != row.session_id]
    self.sessions = [
        ChatSessionSummary(
            session_id=row.session_id,
            title=row.title,
            activity_info=format_activity(row.updated_at, now),
        ),
        *remaining,
    ]

async def _append_and_persist(
    self,
    bubble: ChatMessage,
    identity: Optional[Identity],
    session_id: Optional[str],
) -> None:
    """Puts one bubble on screen, then tries to record it. In that order.

    **The order is the story.** PRD Section 6: "the transcript write happens
    after, in the UI layer, and is allowed to fail without taking the turn with
    it." PRD Risk 5 is the failure it is written against: "the model answered,
    the audit row is written, and then the transcript insert fails -- a naive
    implementation raises and the user loses a paid, logged answer."

    **Every bubble in `_do_send` goes through here, including the ones that
    cannot be written.** The guard below returns for a send with no resolvable
    identity and for one with no session -- history off, or a create that
    failed. Routing those through the same helper rather than leaving them as
    hand-rolled appends is what makes a ninth outcome added later persist by
    default instead of by remembering.

    **It must not be called from inside `async with self`.** `_do_send` is a
    background task, so `self` is a `StateProxy`, and nesting the context raises
    `ImmutableStateError` ("Do not nest `async with self` blocks",
    reflex/istate/proxy.py:136). The lock is opened here, three times, around
    three short mutations, with both database calls offloaded between them.

    **Two guarded arms, not one, because one notice cannot be true for both.**
    A failed `append_message` means the turn is not in the database. A failed
    `touch` means it is, and only the ordering is stale. AC 6 requires the
    second not to "surface as a lost turn", so it gets its own quieter notice on
    the rail's own error slot instead of borrowing the transcript's.

    Both arms catch bare `Exception` rather than `ChatSessionError`. The story
    is explicit: a `StorageError` that escaped wrapping would otherwise take the
    turn down, which is the one outcome this helper exists to prevent.
    """
    async with self:
        self.messages.append(bubble)

    if identity is None or not session_id:
        # Nothing to record against: the credential did not resolve, the create
        # failed, or persistence is off. No write, and no notice -- AC 7's "no
        # write is attempted, no notice appears", reached without this class
        # ever naming the flag.
        return

    try:
        await asyncio.to_thread(
            chat_sessions.append_message,
            identity,
            session_id,
            _to_stored_message(bubble, session_id),
        )
    except Exception:
        async with self:
            self.transcript_error = TRANSCRIPT_NOT_SAVED_NOTICE
        return

    async with self:
        self.transcript_error = ""

    try:
        await asyncio.to_thread(chat_sessions.touch, identity, session_id)
        # Re-read rather than stamp a timestamp here: `touch` returns a bool,
        # and the row carries both the authoritative `updated_at` and the
        # authoritative title -- which the rail needs on the first send of a new
        # chat, when STORY-013's create left no summary behind. One primary-key
        # read on a path that has just made two writes and a model round trip.
        row = await asyncio.to_thread(chat_sessions.get, identity, session_id)
        if row is not None:
            now = datetime.now(timezone.utc)
            async with self:
                self._promote_session(row, now)
                self.sessions_error = ""
    except Exception:
        async with self:
            self.sessions_error = SESSION_ORDER_STALE_NOTICE
```

  Add `Identity` to the existing `app.services.identity` import (`resolve` already comes from there) and `Optional` from `typing`.

- **Mirror**: `chat_ui/chat_ui/state.py:217-235` for the offload/lock alternation; `:128-138` for the one-clock-read summary construction.
- **Validate**: `python -c "import chat_ui.chat_ui.state; print('ok')"`

### Task 5: Route all eight append sites through the helper

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: Replace each `async with self: self.messages.append(...)` in `_do_send` with `await self._append_and_persist(bubble, identity, session_id)`. The eight sites, by current line:

  | Site | Lines | Kind | Notes |
  |---|---|---|---|
  | invalid credential | `:178-187` | `internal_error` | `identity` is `None` here and `session_id` is not yet read; pass `None, None`. Keep `self.pending = False` in its own `async with self` **after** the call — the helper must not be nested inside it. |
  | user bubble | `:191-194` | `user` | The block also clears `input_text` and reads `model`, `session_id`, `device`. **Split it**: keep that block for the reads and the clear, and call the helper immediately after it, before the lazy-create arm. `session_id` at that moment is `self.active_session_id` — correct for a continuing chat, empty for a new one, in which case the helper's guard skips the write. See **Deviations**. |
  | `OpenRouterError` | `:256-266` | `upstream_error` | Build the bubble, `await` the helper, then `return`. |
  | `DuplicateCheckError` / `PiiRedactorError` | `:267-277` | `internal_error` | Same. |
  | catch-all `Exception` | `:278-288` | `internal_error` | Same. |
  | the four `isinstance` arms + fallback | `:290-339` | `assistant` / `duplicate` / `injection` / `forbidden` / `internal_error` | Already collapse into one `self.messages.append(bubble)` at `:338-339`; that single block becomes one `await self._append_and_persist(bubble, identity, session_id)`. |

  The `assistant` arm needs no change to satisfy AC 3: it already sets `content=result.response` (`:293`), which is the redacted text (`QuerySuccessResponse.response`). PRD Section 9: *"The raw upstream text is never written to `chat_messages`."* Add a one-line comment at that field naming the rule, since this is the commit at which the field starts reaching disk.

  Do **not** wrap any helper call in `async with self`, and do not add a third `try/finally` — every call stays inside the existing `try:` at `:190`, whose `finally` at `:340-342` clears `pending` (PRD-004 Risk 3).

- **Mirror**: `chat_ui/chat_ui/state.py:338-339` — the one collapsed append the four branches already share.
- **Validate**: `python -m pytest tests/test_chat_state.py -q` (the pre-existing PRD-004/STORY-013 tests must stay green before the new ones are written).

### Task 6: `logout()` clears the new notice

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: Add `self.transcript_error = ""` to `logout()` (`:141-150`), beside the existing `self.messages = []`. One line, and a comment: the notice is *about* the transcript being cleared, so leaving it standing would report a lost turn for a conversation that is no longer on screen. This is a deliberate step outside the story's *"`_do_send` only"* scope line; see **Deviations**. STORY-016 owns clearing `sessions`, `active_session_id` and `sessions_error`, and this pre-empts none of its assertions.
- **Mirror**: `chat_ui/chat_ui/state.py:145-150`.
- **Validate**: `python -m pytest tests/test_chat_state.py -k logout -q`

### Task 7: Copy assertions

- **File**: `tests/test_copy.py`
- **Action**: UPDATE
- **Implement**: One test, after `test_session_fallback_copy_names_the_thing_rather_than_the_failure` (`:536`), with both constants added to the module's `chat_ui.chat_ui.copy` import:

```python
def test_transcript_notices_name_the_saving_and_never_the_answer():
    """STORY-014 AC 5 and AC 6, as copy rather than as behaviour.

    Both notices are full sentences in the interface's voice (frontend-design:
    "explain what went wrong and how to fix it... errors don't apologize"), and
    the two are *different strings* on purpose: only one of them may claim a
    turn was not saved, because only one of the two failures means that.
    """
    assert TRANSCRIPT_NOT_SAVED_NOTICE
    assert SESSION_ORDER_STALE_NOTICE
    assert TRANSCRIPT_NOT_SAVED_NOTICE != SESSION_ORDER_STALE_NOTICE

    for text in (TRANSCRIPT_NOT_SAVED_NOTICE, SESSION_ORDER_STALE_NOTICE):
        assert text[0].isupper() and text.endswith(".")
        for word in ("sorry", "apologise", "apologize", "oops", "unfortunately"):
            assert word not in text.lower()
        # No mechanism: the reader does not run the database.
        for word in ("sql", "database", "exception", "storageerror", "insert"):
            assert word not in text.lower()

    assert "not saved" in TRANSCRIPT_NOT_SAVED_NOTICE.lower()
    # The stale-order notice must not read as a lost turn -- AC 6.
    assert "not saved" not in SESSION_ORDER_STALE_NOTICE.lower()
    assert "saved" in SESSION_ORDER_STALE_NOTICE.lower()
```

- **Mirror**: `tests/test_copy.py:536-563`.
- **Validate**: `python -m pytest tests/test_copy.py -q`

### Task 8: The STORY-014 test section

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE
- **Implement**: A new `# --- Transcript persistence (STORY-014) ---` section at the end, plus one shared reader:

```python
def _stored_messages(session_id: str, user_id: str = _AUTH_USER_ID):
    """The session's rows, read straight from the store rather than through
    app/services/chat_sessions.py -- asserting the service's writes against the
    service would be asserting it against itself, the rule `_session_rows`
    above already states for STORY-013."""
    return list_chat_messages(session_id, user_id)
```

  (add `list_chat_messages` to the `app.db.database` import block at `:14-24`, `StorageError` from `app.db.errors`, and the two copy constants.)

  Twelve tests, one per acceptance criterion plus the two structural guards:

  1. **`test_a_send_persists_the_user_bubble_and_the_assistant_bubble`** — AC 1/2. Second send of an established chat (the first send opens the session; see **Deviations**): both rows present, in `id` order, `kind` == `["user", "assistant"]`.
  2. **`test_the_bubble_is_appended_before_it_is_written`** — AC 1's *"after the append, not before and not instead"*. Patch `chat_state_mod.chat_sessions.append_message` with a stand-in asserting `state.messages[-1].kind` already matches the row it was handed. The only assertion that distinguishes the two orderings, since both leave the same row behind.
  3. **`test_every_bubble_kind_is_persisted`** — AC 2, parametrized over all seven kinds: `user` (implicit in every case), `assistant`, `duplicate`, `injection`, `forbidden` via the four `run_query` return types; `upstream_error` via `OpenRouterError`; `internal_error` via `PiiRedactorError`. Assert `kind` on the stored row, not merely a row count.
  4. **`test_the_assistant_row_stores_the_redacted_response`** — AC 3 and PRD Section 9. `run_query` returns `QuerySuccessResponse(response="redacted <EMAIL>")`; assert the stored `content` is the response the pipeline released, and that the raw pre-redaction string appears in **no** row.
  5. **`test_a_successful_write_touches_the_session_and_moves_it_to_the_front`** — AC 4. Two sessions via `create_chat_session` + `_backdate_session`, the older made active; after a send its `updated_at` has moved and `state.sessions[0].session_id` is the active one, with a non-empty `activity_info`.
  6. **`test_the_first_send_puts_the_new_chat_at_the_front_of_the_rail`** — AC 4's insert half: STORY-013 leaves the created session out of `sessions`, so this asserts the helper's `get`-and-promote adds it, carrying the **stored** title (`derive_title(prompt)`) rather than a re-derived one.
  7. **`test_a_failed_append_keeps_the_turn_on_screen_and_reports_it`** — AC 5 and AC 8. Patch `chat_state_mod.chat_sessions.append_message` to raise `ChatSessionError`; assert `[m.kind for m in state.messages] == ["user", "assistant"]`, `state.transcript_error == TRANSCRIPT_NOT_SAVED_NOTICE`, `state.pending is False`, and that the composer is genuinely usable again (a second send appends a second `user` bubble, the shape `test_pending_clears_when_session_creation_raises` at `:1209` uses).
  8. **`test_a_storage_error_that_escaped_wrapping_still_does_not_lose_the_turn`** — AC 5's structural half and the reason the catch is bare. Patch **`app.db.database.append_chat_message`** — the function the story's AC names — to raise `StorageError`; the turn survives identically. Also exercises the service's `_wrapped` path end to end.
  9. **`test_a_failed_touch_does_not_report_a_lost_turn`** — AC 6. Patch `chat_sessions.touch` to raise; the row **is** in `chat_messages`, `transcript_error` is empty, and `sessions_error == SESSION_ORDER_STALE_NOTICE`. The empty `transcript_error` is the whole of AC 6.
  10. **`test_history_off_writes_nothing_and_says_nothing`** — AC 7. `monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)`; zero `chat_messages` rows, `transcript_error == ""`, `sessions_error == ""`, bubbles `["user", "assistant"]`, `pending is False`.
  11. **`test_the_audit_row_survives_a_failed_transcript_write`** — AC 9. Real `run_query` with a fake `call_openrouter`, `append_message` patched to raise; `_count_audit_rows()` is 1 and that row's `session_id` names the session. The two writes are independent, and the evidence one already happened inside the pipeline.
  12. **`test_every_bubble_append_in_do_send_goes_through_the_helper`** — the structural guard behind the story's *"a ninth outcome added later cannot be persisted-by-forgetting"*. Walk `_do_send`'s AST (the pattern `test_chat_state_never_names_the_history_flag` at `:1146` establishes) and assert no `self.messages.append(...)` call remains inside it — every append is the helper's.

- **Mirror**: `tests/test_chat_state.py:1163-1226` for the monkeypatched-failure shape; `:1146-1161` for the AST guard.
- **Validate**: `python -m pytest tests/test_chat_state.py -q`

### Task 9: Compile and full suite

- **File**: —
- **Action**: verify
- **Implement**: Per **reflex-process-management**, step 1 first: `cd chat_ui && reflex compile --dry`. Then the whole suite. Investigate any failure at its source rather than adjusting an assertion.
- **Validate**: the Validation block below, in order.

---

## End-to-End Tests

- [ ] `cd chat_ui && reflex compile --dry` → compiles, no new warnings.
- [ ] Second send in an established chat → `chat_messages` holds exactly two new rows, `kind` `user` then `assistant`, in `id` order.
- [ ] All seven kinds round-trip into a row with the right `kind` — including the two error kinds and the three block kinds.
- [ ] The `assistant` row's `content` is `QuerySuccessResponse.response`; the raw upstream string appears in no row.
- [ ] A send moves `chat_sessions.updated_at` and puts the active chat at `state.sessions[0]`.
- [ ] `chat_sessions.append_message` patched to raise → both bubbles on screen, `transcript_error` set, `pending is False`, and `audit_logs` still holds the row for that send.
- [ ] `app.db.database.append_chat_message` patched to raise `StorageError` → identical outcome (the bare catch holds).
- [ ] `chat_sessions.touch` patched to raise → the message row exists, `transcript_error` is empty, `sessions_error` names a stale order.
- [ ] `CHAT_HISTORY_ENABLED=false` → zero `chat_messages` rows, both notices empty, bubbles unchanged.
- [ ] A live boot (`reflex run --env prod --single-port`, per the skill) → sign in, send, reload; the rail's active chat is first and the bubbles are the ones sent. Restore itself is STORY-015; this checks only that the write path does not break the running app.

## Validation

```bash
# The story's own suites
python -m pytest tests/test_chat_state.py tests/test_copy.py -q

# The service and store this story now calls on the send path
python -m pytest tests/test_chat_sessions.py tests/test_session_ownership.py tests/test_db.py -q

# The structural guards: the AST walks over app/ and chat_ui/, and the census
# that pins tests/test_chat_state.py and tests/test_copy.py by name
python -m pytest tests/test_untouched_app.py -q

# The chat still imports and its components still build
python -c "import chat_ui.chat_ui.state; print('ok')"
python -m pytest tests/test_chat_components_import.py tests/test_render_invariants.py -q

# The other suite that drives a chat send
python -m pytest tests/test_rbac.py -q

# The Reflex app compiles (reflex-process-management, step 1)
cd chat_ui && reflex compile --dry && cd ..

# Full suite before the commit
python -m pytest -q
```

---

## Deviations

| PRD / story says | Plan does | Why |
|---|---|---|
| Story Technical Notes: *"File: `chat_ui/chat_ui/state.py`, `_do_send` only."* | Also edits `logout()` (one line) and `copy.py` | `copy.py` is required by the story itself (*"The notice is a copy-module string"*). The `logout()` line clears `transcript_error` alongside `messages`: the notice is *about* the transcript being cleared, so leaving it standing would report a lost turn for a conversation no longer on screen. It takes no assertion from STORY-016, whose AC 8 names `sessions`, `active_session_id` and `sessions_error` and not this var. Flagged rather than done quietly. |
| Story AC 2: *"including `user`"* — every bubble of every send | The `user` bubble of the **first** send of a new chat is not written | Order forces it. STORY-013's lazy create runs *after* the user bubble is appended, deliberately — `state.py:214-216`: *"after the user's bubble is on screen, so a slow create never hides what they typed."* At that instant there is no `session_id` to file the row under. Moving the create earlier would trade a guaranteed-visible prompt for a complete first row, which inverts PRD Risk 5's priority; buffering the bubble to re-persist after the create would put a second, order-dependent write path into the helper this story exists to make singular. **STORY-015 must reconcile this**: a restored first-turn transcript starts at the `assistant` bubble. Recorded here so that story inherits a decision rather than discovering a gap. |
| Story AC 6: *"the same applies"* for a failed `touch` | A **different** notice, on `sessions_error` rather than `transcript_error` | The same AC also says a failed reorder *"must not surface as a lost turn"*, and the two halves cannot both hold with one string: after a successful `append_message`, "this turn was not saved" is false. The behavioural half of "the same applies" — bubble stays, `messages` not cleared, `pending` clears — is satisfied exactly. |
| PRD Section 6: *"`ChatState` calls the service, never `database.py` directly"* | `state.py` imports `StoredMessage` and `ChatSession` from `app.db.models` | Dataclasses, not calls. `chat_sessions.append_message(identity, session_id, message: StoredMessage)` requires the caller to construct one, so the import is the service's own signature reaching back. No `app.db.database` function is called from `chat_ui/`. |
| Story: reorder *"the in-state `sessions` list"* | Reorders from a fresh `chat_sessions.get(...)` rather than in place | STORY-013's plan flagged this exact hand-off: the created session is absent from `sessions`, so an in-place reorder is a no-op on the first send. The read supplies the authoritative title (no second `derive_title` call, which `formatting.py:96-104` forbids) and the authoritative `updated_at` (no third copy of the `"%Y-%m-%dT%H:%M:%SZ"` literal in a third module). The cost is one primary-key read per persisted bubble on a path that already does two writes and a model round trip. |

---

## Risks

| Risk | Mitigation |
|---|---|
| **PRD Risk 5 itself**: a transcript write failure takes a paid, logged answer down. | Two independent `except Exception` arms, both after the append. Task 8 tests 7, 8 and 11 assert the bubble, the notice, `pending is False` and the surviving audit row — and test 8 does it through a raw `StorageError`, the escape the story warns a `ChatSessionError`-only catch would miss. |
| Someone wraps a `_append_and_persist(...)` call in `async with self` — the natural-looking edit, since that is what the line replaced. | It raises `ImmutableStateError` immediately (`reflex/istate/proxy.py:136`), not subtly, and every send test in the suite fails. The helper's docstring states the rule and cites the line. |
| A ninth outcome is added later and appends directly, persisting nothing. | Task 8 test 12 walks `_do_send`'s AST and fails on any `self.messages.append(...)` left in it. The drift fails a test rather than a review — the mechanism PRD-006 Risk 6 established and PRD-008 Risk 6 reuses. |
| The two notices get "simplified" into one string, making the touch arm claim a lost turn. | Task 7 asserts they are different and that only one contains "not saved"; Task 8 test 9 asserts `transcript_error` stays empty when only `touch` fails. |
| `_to_stored_message` writes `""` where the column means absent, and STORY-015 restores bubbles rendering empty labels. | Every optional field converts with `or None`, and Task 8 test 3 asserts on stored `kind` and metadata per bubble kind rather than on row counts. The `pii_entities` join matches `audit_logger.py:45` exactly. |
| The raw upstream response reaches `chat_messages`, breaking PRD Section 9's most consequential promise. | The bubble already carries `result.response` and nothing else is in scope; Task 5 adds the comment at the field, and Task 8 test 4 asserts the raw string appears in **no** row, not merely that the redacted one appears in this one. |
| The extra `chat_sessions.get(...)` per bubble is read as gratuitous and removed, reintroducing the first-send rail gap. | Its comment states both reasons (authoritative title, authoritative `updated_at`), and Task 8 test 6 fails if the created chat does not reach `sessions[0]` with its stored title. |
| `transcript_error` is added but nothing renders it, so a failure is silent in the running app until STORY-018/019. | Bounded and understood, and identical to the interval `sessions_error` has sat in since STORY-013. Recorded here so the rendering is a known debt with a named owner rather than a discovery. The state-level tests assert the notice regardless of the surface. |
| The invalid-credential arm at `:178-188` sits outside the `try/finally` and now calls an `await`ing helper, re-opening PRD-004 Risk 3. | That arm already clears `pending` explicitly (`:187`); the helper is awaited before it and its own failure arms cannot raise. Task 8 test 7's `pending is False` assertion and the existing `test_chat_state_send_when_credential_revoked_mid_session_appends_internal_error` (`:314`) both cover the path. |

---

## Acceptance Criteria

(Copied from story `STORY-014`)

- [ ] Given any send, when a bubble is appended to `self.messages`, then the same bubble is written with `chat_sessions.append_message(...)` **after** the append, not before and not instead.
- [ ] Given all seven bubble kinds, when each is produced, then each is persisted — including `user`, and including the four non-success outcomes and the two error kinds.
- [ ] Given an `assistant` bubble, when it is persisted, then the stored `content` is `QuerySuccessResponse.response` — the redacted text the pipeline released.
- [ ] Given a successful write, when it completes, then `chat_sessions.touch(...)` updates `updated_at` and the in-state `sessions` list reorders so the active chat is first.
- [ ] Given `append_message` raising, when the exception is caught, then the bubble stays on screen, a notice states that the turn was not saved, `self.messages` is not cleared, and `pending` still clears.
- [ ] Given `touch` raising, when it is caught, then the same applies — a failed reorder is cosmetic and must not surface as a lost turn.
- [ ] Given `settings.CHAT_HISTORY_ENABLED is False`, when a send completes, then no write is attempted, no notice appears, and the chat behaves exactly as it does today.
- [ ] Given `tests/test_chat_state.py`, when it runs, then a test patches `append_chat_message` to raise and asserts the transcript is intact, the notice is present and `pending` is `False`.
- [ ] Given the audit trail, when a transcript write fails, then the audit row for that send is still present.
- [ ] All tasks completed
- [ ] `cd chat_ui && reflex compile --dry` succeeds
- [ ] Full suite green (`python -m pytest -q`)
- [ ] Follows existing patterns
