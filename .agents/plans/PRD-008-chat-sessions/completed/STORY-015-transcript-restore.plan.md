---
story: STORY-015
prd: PRD-008
slug: transcript-restore
title: "Restore a transcript on sign-in and on switch, rehydrating all seven bubble kinds"
type: NEW_CAPABILITY
complexity: HIGH
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-06
---

# Plan: Restore a transcript on sign-in and on switch, rehydrating all seven bubble kinds

## Summary

STORY-014 gave `state.py` a one-way door: `_to_stored_message` turns a `ChatMessage` into a `chat_messages` row and nothing turns one back. This story builds the other direction and the two callers that walk through it — `_to_chat_message(row)` at module level, `select_session(session_id)` as the switch, and four lines inside the existing `login()` that pick the most recently active chat and render it.

Three structural decisions carry it.

**The rehydration is the exact inverse of `_to_stored_message`, written directly beneath it, and the two are read as a pair.** `ChatMessage` defaults its optionals to `""` / `0` because a Reflex Var cannot be `None` on the wire; the columns are nullable and mean *absent*. So where the serializer converts with `or None`, the deserializer converts with `or ""` / `or 0`, and `pii_entities` splits on `","` **guarded against empty** — `database.py:1661-1666` already stores `""` as `NULL` specifically so that this layer cannot produce `[""]`, "a phantom entity on a message that had none, which is what STORY-015 would render." The two duplicate fields have no column and are recomputed here through `format_duplicate_info`, which `state.py:29` already imports for the live path — the same function, so a restored duplicate and a live one cannot diverge.

**Both callers are plain async handlers, not background tasks, and that is what makes one helper serve both.** `login()`'s own docstring (`state.py:136-148`) records the rule: a plain async handler holds the exclusive state lock for its entire duration including across `await`, so `self` is the real state, mutations are direct, and `async with self` would **deadlock on a lock the handler already holds**. `_do_send` is the opposite and its helper is written to the opposite rule. Making `select_session` a background task would fork the restore into two lock disciplines for one behaviour; making it plain async — the shape `login()` already proves against the same `asyncio.to_thread` database read — keeps it at one. The reflex docs' own advice for a load handler is *"use an async handler for network or database calls so the event loop is not blocked"*, which is exactly this.

**No `on_load` is wired, and that is a finding rather than an omission** — see Deviations. The story asked for the API to be confirmed against **reflex-docs** rather than recalled; it was, against the pinned tree, and the confirmation is what shows `on_load` cannot reach this AC: `_token` is a backend var, not client storage, so no signed-in state survives a page reload and an `on_load` on the chat page would fire with `user_id == ""` every time. "The page loads" for a signed-in user *is* the moment `login()` returns, which is why STORY-013 put the session list there.

## User Story

As an employee
I want my conversation to still be there after I reload the page, and to swap between conversations without losing either
So that a stray refresh does not cost me an afternoon of work.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-015-transcript-restore.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md` — Section 4 (Chat state), Section 5 (stories 1, 5), Section 6 (stored message table, "the same `rx.match`"), Section 11, Section 12 Phase 3, Risk 3

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | HIGH |
| Systems Affected | `chat_ui/chat_ui/state.py`, `chat_ui/chat_ui/copy.py`, `tests/test_chat_state.py`, `tests/test_copy.py` |
| Story | STORY-015 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |
| Depends on | STORY-014 ✅ (verified `status: done`, commit `36da168`) |
| Blocks | STORY-016, STORY-021 |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `reflex-docs` (plugin, named in story frontmatter) | `chat_ui/AGENTS.md`, verbatim: *"For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory."* The story names two APIs to confirm rather than recall: `on_load`, and its interaction with `rx.event(background=True)`. Governs the handler kind and the lock discipline of both new callers. | Tasks 3, 4, 5 |
| `reflex-process-management` (plugin, in `chat_ui/AGENTS.md`) | `chat_ui/AGENTS.md`, verbatim: *"When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill for the correct sequence and error investigation steps."* Its first step is `reflex compile --dry`, run from `chat_ui/`. | Task 8, Validation |
| `.agents/skills/frontend-design` | Listed in `.agents/skills/` (the only entry) and read in full. The story scopes it out of the surface — *"This story renders no new component"* — so it applies here **only** to the one new copy constant, under its rule at `SKILL.md:53`, verbatim: *"Treat failure and emptiness as moments for direction, not mood. Explain what went wrong and how to fix it, in the interface's voice rather than a person's. Errors don't apologize, and they are never vague about what happened."* | Task 1 |

`.agents/skills/` was listed and holds exactly one skill (`frontend-design`); its `description` was read and matches this story only through the copy constant above. The rail's own strings are STORY-017's, and `copy.py:109` says so.

### `reflex-docs` outcome — the three API facts this plan depends on

The skill was invoked; it directs to the reference documentation rather than to recall. The published pages for `on_load` are thin (they confirm it exists and that async handlers are the right shape for a database read, but do not give the signature), so each fact below is additionally verified against the pinned `reflex==0.9.6.post1` tree in `.venv/` — the code that will actually run.

| Fact | Evidence |
|---|---|
| `on_load` exists on both `app.add_page(...)` and the `@rx.page` decorator, is typed `EventType[()] \| None`, and accepts **either one handler or a list**. | `.venv/Lib/site-packages/reflex/app.py:871` (`on_load: EventType[()] \| None = None`), docstring at `:886` — *"The event handler(s) that will be called each time the page load."* — and the normalization at `:969-970`: `(on_load if isinstance(on_load, list) else [on_load]) if on_load is not None else []`. Same parameter on `reflex/page.py:25` and `:87`. |
| A background task may not be called from another handler; it must be returned/yielded as a follow-up event, which lands *after* the calling handler has finished. | This is the rule `login()`'s docstring already cites (`state.py:138-147`) as the reason STORY-013's session load lives inside `login()` rather than in a chained background task. It applies unchanged to the transcript load added here. |
| A plain async handler holds the exclusive state lock for its whole duration, so `self` is the real state; `async with self` inside one would deadlock. A background task is the inverse — `self` is a `StateProxy`, mutation requires `async with self`, and those blocks may not nest (`reflex/istate/proxy.py:132-137`). | `state.py:136-148` records the first half as settled practice in this file; `state.py:258-261` records the second. **The consequence for this story:** the restore helper is called only from plain async handlers and therefore mutates directly, and it must never be called from `_do_send`. |

**Conclusion carried into the design**: `on_load` is available and correct as an API, and is not used — for the reason in Deviations, which is about *this page's* state, not about the API.

---

## Patterns to Follow

### The function this story inverts

```python
# SOURCE: chat_ui/chat_ui/state.py:50-64
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

Its docstring (`state.py:46-48`) hands this story its own instruction: *"`duplicate_relative_info` and `duplicate_release_info` are dropped, and their absence is the schema's decision rather than an oversight… STORY-015 recomputes them from `first_query_at` on load."*

### Reading the store from a lock-holding async handler — the shape `login()` already has

```python
# SOURCE: chat_ui/chat_ui/state.py:164-184 (STORY-013's session list)
        self.sessions_error = ""
        try:
            rows = await asyncio.to_thread(chat_sessions.list_for, identity)
        except ChatSessionError as exc:
            # A rail that will not load is not a failed sign-in. ...
            self.sessions = []
            self.sessions_error = str(exc)
        else:
            # One clock read for the whole list, per format_activity's own
            # docstring: "a rail of thirty rows shares one clock read".
            now = datetime.now(timezone.utc)
            self.sessions = [...]
```

Direct mutation, no `async with self`, the blocking call offloaded with `asyncio.to_thread`. The transcript load added below sits immediately after this block and follows it exactly.

### The live duplicate bubble a restored one must be indistinguishable from

```python
# SOURCE: chat_ui/chat_ui/state.py:479-490
            elif isinstance(result, QueryBlockedDuplicateResponse):
                relative_info, release_info = format_duplicate_info(
                    result.first_query_at
                )
                bubble = ChatMessage(
                    kind="duplicate",
                    content=result.reason,
                    prompt=text,
                    first_query_at=result.first_query_at,
                    duplicate_relative_info=relative_info,
                    duplicate_release_info=release_info,
                )
```

The restore calls the **same** `format_duplicate_info`, already imported at `state.py:29`.

### The read this story calls, and its deliberate three-way sameness

```python
# SOURCE: app/services/chat_sessions.py:297-315
def messages_for(identity: Identity, session_id: str) -> list[StoredMessage]:
    """This identity's whole transcript for one session, in write order.

    Empty when history is off, empty for a session that does not exist, and
    empty for someone else's -- the same three-way sameness `get` above keeps,
    and for the same reason.
    ...
    """
    if not settings.CHAT_HISTORY_ENABLED:
        return []

    with _wrapped("messages_for"):
        return database.list_chat_messages(session_id, identity.user_id)
```

### The `pii_entities` encoding, and the trap named at the column

```python
# SOURCE: app/db/database.py:1661-1666
    `pii_entities` is normalized: `""` is stored as `NULL`, exactly as
    `app/services/audit_logger.py:45` already stores an empty entity list. The
    difference matters one layer up -- `"".split(",")` is `[""]`, a phantom
    entity on a message that had none, which is what STORY-015 would render.
```

### Copy voice

```python
# SOURCE: chat_ui/chat_ui/copy.py:122-132
TRANSCRIPT_NOT_SAVED_NOTICE = (
    "This turn was not saved to your history. It stays on screen until you "
    "reload the page."
)
# The counterpart for a failed touch, and deliberately a different string.
SESSION_ORDER_STALE_NOTICE = (
    "This chat is saved. The list order is out of date until you reload."
)
```

Two sentences, sentence case, states what happened and what is now true, no apology, no mechanism.

### Tests

```python
# SOURCE: tests/test_chat_state.py:1253-1269
@pytest.mark.asyncio
async def test_a_send_persists_the_user_bubble_and_the_assistant_bubble(
    temp_db, monkeypatch
):
    """AC 1 and AC 2. The second send of a chat is the one that writes both
    bubbles: the first send opens the session *after* the user bubble is
    already on screen, so that bubble has no session to be filed under (see the
    plan's Deviations)."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    state = _make_state()
    await _send(state, "first prompt")
    await _send(state, "second prompt")

    rows = _stored_messages(state.active_session_id)
    assert [r.kind for r in rows] == ["assistant", "user", "assistant"]
    assert [r.id for r in rows] == sorted(r.id for r in rows)
```

Async handlers are driven through `type(state).event_handlers["<name>"]` then `await handler.fn(state, *args)` (`tests/test_chat_state.py:110-113`); `login()` is awaited directly because it is not a background task (`:983`, `:1010`, …). The seven-kind parametrization at `:1306-1368` is the template for this story's per-kind round trip.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/copy.py` | UPDATE | `TRANSCRIPT_NOT_LOADED_NOTICE` — the one string a failed read needs. |
| `chat_ui/chat_ui/state.py` | UPDATE | `_to_chat_message`, `_read_transcript`, `select_session`, and the restore arm inside `login()`. |
| `tests/test_chat_state.py` | UPDATE | The STORY-015 section: per-kind round trip, switch semantics, the guards. |
| `tests/test_copy.py` | UPDATE | Assertions on the new constant, matching STORY-014's block at `:588-603`. |

No file created. `app/` is untouched — every function this story needs already exists and is `done`.

---

## Dependency Order

1 (copy) → 2 (rehydration) → 3 (read helper) → 4 (`select_session`) → 5 (`login()` arm) → 6 (`logout` note, verify only) → 7–8 (tests) → 9 (compile + suite).

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: The one new copy constant

- **File**: `chat_ui/chat_ui/copy.py`
- **Action**: UPDATE
- **Implement**: In the existing `# --- Transcript persistence ---` block (after `SESSION_ORDER_STALE_NOTICE`, `:130-132`), add:

  ```python
  # The read counterpart of TRANSCRIPT_NOT_SAVED_NOTICE above. STORY-015 AC 9
  # requires the transcript on screen to be left alone when a load fails, so
  # the notice must say that the *previous* conversation is what the reader is
  # still looking at -- a bare "could not load" would leave them unsure which
  # chat the bubbles belong to. Names the consequence, not the mechanism, and
  # does not apologize (frontend-design SKILL.md:53).
  TRANSCRIPT_NOT_LOADED_NOTICE = (
      "This chat could not be loaded. The conversation on screen is unchanged."
  )
  ```

  Reuse `sessions_error` as its slot — see Task 4. Add **no** new state var: `test_chat_state_declares_the_three_session_vars` (`tests/test_chat_state.py:954-966`) pins the trio, and a fourth would be a rail var without a rail.
- **Mirror**: `chat_ui/chat_ui/copy.py:115-132` — the STORY-014 pair, comment-then-constant, each comment naming why the string is not the neighbouring one.
- **Validate**: `python -c "from chat_ui.chat_ui.copy import TRANSCRIPT_NOT_LOADED_NOTICE; print(TRANSCRIPT_NOT_LOADED_NOTICE)"`

### Task 2: `_to_chat_message` — the inverse of `_to_stored_message`

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: A module-level function directly beneath `_to_stored_message` (i.e. after `:64`), so the pair reads as a pair:

  ```python
  def _to_chat_message(row: StoredMessage) -> ChatMessage:
      """One `chat_messages` row as one bubble -- the inverse of
      `_to_stored_message` above, and deliberately adjacent to it.

      Every conversion is that function's read backwards. It writes the
      optional fields with `or None` because the columns mean *absent*; this
      reads them with `or ""` / `or 0` because a Reflex Var cannot be None on
      the wire. `pii_entities` splits on "," and guards the empty case:
      `"".split(",")` is `[""]`, and `app/db/database.py:1661-1666` stores an
      empty list as NULL precisely so this line cannot invent a phantom entity.

      The two duplicate fields have no column (`app/db/models.py:119-122`) and
      are recomputed here through the same `format_duplicate_info` the live
      duplicate branch calls at `:480`, so "already sent 2m ago" reads
      correctly hours later. It is called **only** for `kind == "duplicate"`:
      the function returns DUPLICATE_FALLBACK_TEXT rather than "" for an empty
      timestamp (`formatting.py:70-71`), so running every kind through it would
      put duplicate copy on a user bubble -- invisible today, because only
      `render_duplicate` reads those fields, and a divergence from the live
      path all the same.
      """
      relative_info = ""
      release_info = ""
      if row.kind == "duplicate":
          relative_info, release_info = format_duplicate_info(row.first_query_at or "")

      return ChatMessage(
          kind=row.kind,
          content=row.content,
          prompt=row.prompt or "",
          model_used=row.model_used or "",
          tokens_used=row.tokens_used or 0,
          audit_id=row.audit_id or 0,
          pii_redacted=row.pii_redacted,
          pii_entities=row.pii_entities.split(",") if row.pii_entities else [],
          pattern=row.pattern or "",
          required_permission=row.required_permission or "",
          first_query_at=row.first_query_at or "",
          duplicate_relative_info=relative_info,
          duplicate_release_info=release_info,
          detail=row.detail or "",
      )
  ```

  `row.created_at` and `row.id` are not mapped: `ChatMessage` has no field for either, and `id` is the ordering the store already applied (`database.py:1749`, `ORDER BY id ASC`).
- **Mirror**: `chat_ui/chat_ui/state.py:32-64` — same module-level placement, same field order, same `or`-conversion discipline.
- **Validate**: `python -c "import chat_ui.chat_ui.state as s; from app.db.models import StoredMessage; print(s._to_chat_message(StoredMessage(session_id='x', kind='user', content='hi')))"` — asserts `pii_entities == []`, not `['']`.

### Task 3: `_read_transcript` — the offloaded read, one place

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: A method on `ChatState`, placed beside `_promote_session` (`:211`):

  ```python
      async def _read_transcript(
          self, identity: Identity, session_id: str
      ) -> list[ChatMessage]:
          """This session's stored bubbles, in write order, rehydrated.

          **Callable only from a plain async handler**, and the opposite rule
          to `_append_and_persist` below. Both callers (`login` and
          `select_session`) hold the exclusive state lock for their whole
          duration, so `self` is the real state and an `async with self` here
          would deadlock on a lock the caller already holds -- `login`'s own
          docstring records the same rule for the same reason. Nothing here
          mutates state; the caller does that with the returned list.

          Raises whatever the read raised. The caller owns the notice, because
          only the caller knows what is on screen to be left alone.
          """
          rows = await asyncio.to_thread(chat_sessions.messages_for, identity, session_id)
          return [_to_chat_message(row) for row in rows]
  ```

  Ordering is the store's (`ORDER BY id ASC`) and is not re-sorted here — a second sort in a second module is a second opinion about the order, which PRD Section 6 spends a paragraph refusing.
- **Mirror**: `chat_ui/chat_ui/state.py:166` for the `asyncio.to_thread(chat_sessions.<fn>, identity, ...)` offload; `:211-231` for a private helper that takes the lock discipline of its caller as given and says so in its docstring.
- **Validate**: `python -c "import chat_ui.chat_ui.state; print('ok')"`

### Task 4: `select_session` — the switch

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: A public handler placed after `edit_and_resend` (`:204-209`), which it borrows its guard from:

  ```python
      @rx.event
      async def select_session(self, session_id: str):
          """Makes `session_id` the active chat and renders its transcript.

          Plain async, not `background=True`, for the reason `login` states:
          a background task cannot be called from another handler and holds no
          lock across its awaits. Plain async holds the exclusive lock for the
          whole handler, so the read below and the swap after it cannot
          interleave with a send -- which is the other half of the `pending`
          guard rather than a duplicate of it.

          `session_id` arrives from the client and is untrusted (PRD-008
          Risk 3). It is not validated here and must not be: `chat_sessions`
          re-checks ownership server-side against the freshly resolved
          Identity, and returns [] for a foreign id, an unknown id and history
          being off alike. A caller that could tell those apart would be a
          caller branching on the flag.
          """
          if self.pending:
              # The same refusal `edit_and_resend` applies, and for a sharper
              # reason: `_do_send` is holding a `session_id` in a local and
              # will append the answer to it. Swapping `messages` out from
              # under an in-flight send files that answer in the wrong chat.
              return

          identity = resolve(self._token)
          if identity is None:
              self.sessions_error = SESSION_INVALIDATED_ERROR
              return

          try:
              restored = await self._read_transcript(identity, session_id)
          except Exception:
              # Bare `Exception`, not `ChatSessionError`: a StorageError that
              # escaped the service's wrapping must not empty the screen
              # either -- the escape STORY-014's test at :1477 exists for.
              self.sessions_error = TRANSCRIPT_NOT_LOADED_NOTICE
              return

          self.messages = restored
          self.active_session_id = session_id
          self.sessions_error = ""
          # The notice was about the transcript this line just replaced, so it
          # cannot outlive it -- the reasoning `logout` records at :197-201.
          self.transcript_error = ""
      ```

  Nothing touches `selected_model`, `user_id`, `_token` or `input_text` (AC 3). On the failure arm nothing is assigned at all, so `messages` **and** `active_session_id` both stand: moving the active id to a chat whose transcript is not on screen would make the rail mark the wrong row.
- **Mirror**: `chat_ui/chat_ui/state.py:204-209` (`pending` guard), `:154-157` (`resolve` then bail), `:164-184` (the offloaded read with its error arm, in a lock-holding handler).
- **Validate**: `python -c "from chat_ui.chat_ui.state import ChatState; print('select_session' in ChatState.event_handlers)"`

### Task 5: The restore arm in `login()`

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: Extend the `else:` branch of `login()` (`:173-184`), after `self.sessions` is built:

  ```python
              # The list is ORDER BY updated_at DESC (database.py:1491), so the
              # first row is the most recently active chat. Opening it is what
              # makes a reload cost nothing: this handler *is* the page load
              # for a signed-in user, because `_token` is a backend var and no
              # signed-in state survives a refresh (see the plan's Deviations
              # on `on_load`).
              if self.sessions:
                  self.active_session_id = self.sessions[0].session_id
                  try:
                      self.messages = await self._read_transcript(
                          identity, self.active_session_id
                      )
                  except Exception:
                      # A transcript that will not load is not a failed
                      # sign-in, exactly as a rail that will not load is not
                      # -- the arm six lines above. The chat opens empty and
                      # the composer works.
                      self.sessions_error = TRANSCRIPT_NOT_LOADED_NOTICE
  ```

  With `CHAT_HISTORY_ENABLED` false, `list_for` returned `[]` at `:166`, so `self.sessions` is empty, `if self.sessions` is false and **no read is attempted** (AC 10) — without `state.py` naming the flag, which `test_chat_state_never_names_the_history_flag` (`:1153-1167`) forbids.
- **Mirror**: `chat_ui/chat_ui/state.py:165-172` — the sibling try/except that already degrades a failed load into a notice rather than a failed sign-in.
- **Validate**: `python -m pytest tests/test_chat_state.py -q -k "login"`

### Task 6: Confirm `logout()` needs no change

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: VERIFY (expected: no edit)
- **Implement**: `logout()` (`:186-202`) already clears `messages` and `transcript_error`. `sessions`, `active_session_id` and `sessions_error` are STORY-016's AC 8 by name and stay untouched here — a restore story must not quietly take assertions from the story that owns them. Read the handler, confirm no new var was introduced in Tasks 1–5, and leave it alone.
- **Mirror**: `chat_ui/chat_ui/state.py:197-201` — the comment that already partitions the two stories' responsibilities.
- **Validate**: `python -m pytest tests/test_chat_state.py -q -k "logout"`

### Task 7: Copy assertions

- **File**: `tests/test_copy.py`
- **Action**: UPDATE
- **Implement**: Import `TRANSCRIPT_NOT_LOADED_NOTICE` alongside the two at `:34-35`, and extend the STORY-014 block at `:588-603` so all three are asserted together:
  - all three are non-empty and pairwise distinct;
  - all three satisfy the block's existing shape checks (the loop at `:592`);
  - `"not saved"` is in `TRANSCRIPT_NOT_SAVED_NOTICE` and in **neither** of the other two — a load failure did not lose a turn, and saying so would be false in the interface;
  - `TRANSCRIPT_NOT_LOADED_NOTICE` says the screen is `"unchanged"`, which is the AC 9 promise the string exists to make.
- **Mirror**: `tests/test_copy.py:588-603`.
- **Validate**: `python -m pytest tests/test_copy.py -q`

### Task 8: The STORY-015 test section

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE
- **Implement**: A sixth section banner — `# --- Transcript restore (STORY-015) ---` — appended after the STORY-014 section (which ends at `:1622`), matching the banner style at `:1236-1238`. Helper first:

  ```python
  async def _select(state: ChatState, session_id: str) -> None:
      handler = type(state).event_handlers["select_session"]
      await handler.fn(state, session_id)
  ```

  Cases:

  1. **`test_every_bubble_kind_survives_the_round_trip`** — AC 4 and AC 11, `@pytest.mark.parametrize` over the **seven** kinds, reusing the outcome fixtures of `test_every_bubble_kind_is_persisted` (`:1306-1368`). Per kind: send twice (so the `user` bubble is stored — see Deviations), capture the live `ChatMessage`, restore through `_select`, and assert the restored bubble equals the live one **field by field** over every field `bubbles.py` reads, excluding the two duplicate fields (case 3 owns those). One parametrized test per kind, not one representative — the AC says so explicitly.
  2. **`test_the_restored_transcript_is_in_id_order`** — AC 2. Three sends, restore, assert `[m.kind for m in state.messages] == ["assistant", "user", "assistant", "user", "assistant"]` — the shape `:1268` already pins on the write side, read back.
  3. **`test_a_restored_duplicate_recomputes_its_relative_copy`** — AC 5. `_seed_duplicate(prompt, hours_ago=2)` (`:85-97`) to produce a live duplicate, then restore and assert the restored `duplicate_relative_info` equals `format_duplicate_info(row.first_query_at)[0]` computed at restore time and is non-empty; and assert the value is **not** read from storage by checking `StoredMessage` has no such attribute (`dataclasses.fields`). Then re-seed at `hours_ago=20` and assert the two restorations differ — the "already sent 2m ago reads correctly hours later" half of the AC.
  4. **`test_a_restored_assistant_keeps_its_footer_and_pii_badge`** — AC 6. Assert `model_used`, `tokens_used`, `audit_id` and the `pii_entities` **list** round-trip; and assert a message with no entities restores as `[]`, not `[""]` — the phantom `database.py:1663` names.
  5. **`test_a_restored_bubble_keeps_the_prompt_its_actions_consume`** — AC 7. For `duplicate`, `injection` and the two error kinds, assert `restored.prompt == "<the prompt>"`, because `ChatState.edit_and_resend(message.prompt)` (`bubbles.py:244`) and `ChatState.retry_message(message.prompt)` (`bubbles.py:331`) are what consume it. Then drive `edit_and_resend(restored.prompt)` and assert `input_text` is refilled.
  6. **`test_login_opens_the_most_recently_active_chat`** — AC 1. Two sessions via `_backdate_session` (`:924-934`), fresh `_make_state()` with empty `messages`, `await state.login()`, assert `active_session_id` is the newer session and `messages` is its transcript.
  7. **`test_login_with_no_sessions_leaves_the_chat_empty`** — the same handler on a user with nothing stored: `sessions == []`, `active_session_id == ""`, `messages == []`, `sessions_error == ""`.
  8. **`test_a_switch_replaces_the_transcript_and_moves_the_active_id`** — AC 2. Two sessions with distinct prompts; switch; assert `messages` is the target's and `active_session_id` moved.
  9. **`test_a_switch_touches_nothing_else`** — AC 3. Set `selected_model` to a non-default before the switch; assert `selected_model`, `user_id` and `_token` are byte-identical afterwards.
  10. **`test_a_switch_is_refused_while_pending`** — AC 8. `state.pending = True`, `_select(state, other_id)`, assert `active_session_id` and `messages` are unchanged.
  11. **`test_a_failed_read_keeps_the_transcript_and_reports_it`** — AC 9. `monkeypatch.setattr(chat_state_mod.chat_sessions, "messages_for", _raise_chat_session_error)` (`:1249-1250`), assert `sessions_error == TRANSCRIPT_NOT_LOADED_NOTICE`, `messages` unchanged, `active_session_id` unchanged, and `pending is False` so the composer is usable.
  12. **`test_a_storage_error_that_escaped_wrapping_still_keeps_the_transcript`** — the bare-`Exception` half, patching `chat_state_mod.chat_sessions.database.list_chat_messages` to raise `StorageError`, mirroring `:1477`.
  13. **`test_a_foreign_session_id_restores_empty_rather_than_erroring`** — the Technical Note *"A foreign or unknown `session_id` yields an empty list, not an error"*. Create a session under a second user, switch to it, assert `messages == []` and `sessions_error == ""`.
  14. **`test_history_off_reads_nothing_on_login`** — AC 10. `monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)` (`:1535`) plus `monkeypatch.setattr(chat_state_mod.chat_sessions, "messages_for", _fail_if_called)` (`:99`); `await state.login()`; assert `messages == []` and the patched read was never called.
  15. **`test_the_rehydration_covers_every_stored_field`** — the structural guard, in the shape of `:1586-1622`. Walk `dataclasses.fields(StoredMessage)`; assert every field except `session_id`, `created_at` and `id` is read by `_to_chat_message`'s AST, so a column added later cannot be silently dropped on the way back. This is the read-side counterpart of `test_every_bubble_append_in_do_send_goes_through_the_helper`.

  **Mutation-check two assertions before the commit** rather than trusting them to pass, as STORY-014's report did: (a) drop the `if row.kind == "duplicate"` gate in `_to_chat_message` — case 1 must fail; (b) change `pii_entities` to an unguarded `.split(",")` — case 4 must fail.
- **Mirror**: `tests/test_chat_state.py:1306-1368` (the seven-kind parametrization), `:1452-1505` (the failure arms), `:1535-1561` (the flag-off case), `:1586-1622` (the AST guard).
- **Validate**: `python -m pytest tests/test_chat_state.py -q`

### Task 9: Compile and full suite

- **File**: —
- **Action**: VERIFY
- **Implement**: Run the Validation block below in order, per **reflex-process-management** (`reflex compile --dry` from `chat_ui/` first, then the suites). Investigate any new warning rather than accepting it.
- **Validate**: `python -m pytest -q` green, with the counts compared against STORY-014's report (1472 passed) plus this story's new cases.

---

## End-to-End Tests

- [ ] `cd chat_ui && reflex compile --dry` succeeds with no new warning.
- [ ] Sign in with a seeded token, send two prompts, note the bubbles; sign out and sign in again → the same bubbles are on screen, in the same order, starting at the first turn's `assistant` bubble.
- [ ] With two chats stored, drive `select_session` from a Python REPL against a live `ChatState` → `messages` swaps, `selected_model` does not.
- [ ] Force a duplicate (send the same prompt twice), sign out and back in → the restored **HELD** bubble shows a relative time computed now, and **Edit and resend** refills the composer with the original prompt.
- [ ] Force an error kind (patch `run_query` to raise), sign out and back in → the restored bubble shows its detail and **Retry** is wired to the original prompt.
- [ ] `CHAT_HISTORY_ENABLED=false`, restart, sign in → the chat opens empty and sends work.

> Note: the rail that would make the switch clickable is STORY-018's. Until then `select_session` is reachable only from tests and a REPL, exactly as `sessions_error` has been unrendered since STORY-013 — a known debt with a named owner, recorded in Risks.

---

## Validation

```bash
# The story's own suites
python -m pytest tests/test_chat_state.py tests/test_copy.py -q

# The service and store the restore path reads through
python -m pytest tests/test_chat_sessions.py tests/test_session_ownership.py tests/test_db.py -q

# The structural guards: the AST walks over app/ and chat_ui/, and the census
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
| Story Technical Notes: *"Reflex loads page state through an `on_load` event; confirm the exact API and its interaction with `rx.event(background=True)`."* | Confirms the API (see the `reflex-docs` outcome table) and then **wires no `on_load`**; the restore happens in `login()`. | The confirmation is what disqualifies it. `_token` is a plain backend var (`state.py:116`), not `rx.Cookie`/`rx.LocalStorage`, so a page reload produces a fresh state with `user_id == ""` and the login gate — an `on_load` on the chat page would fire with no identity, every time, and have nothing to read. "The page loads" for a signed-in user *is* `login()` returning, which is why STORY-013 put the session list there and cited the background-task chaining rule for it. Adding an unreachable handler to satisfy the letter of the note would put a second, dead restore path in the file. The note's actual instruction — verify, do not recall — was followed, and this is its result. **If STORY-016 or a later story moves the credential to client storage, the `on_load` becomes reachable and this decision must be revisited**; recorded here so that is an inherited decision rather than a discovery. |
| Story AC 4: each of the seven kinds restores *"indistinguishable from the live one"* — for a whole conversation. | The **first** `user` bubble of a chat is absent from the restored transcript; a restored first turn starts at its `assistant` bubble. | Inherited, not introduced. STORY-014's plan recorded it in advance and its report re-recorded it: STORY-013 appends the user bubble *before* the lazy create (`state.py:370-381`, *"so that a slow create never hides what the user typed"*), so at that instant there is no `session_id` to file it under. `test_a_send_persists_the_user_bubble_and_the_assistant_bubble` encodes it as `["assistant", "user", "assistant"]` rather than hiding it. Every restore test here therefore sends **twice**. Closing the gap means either delaying the user bubble behind a database write — inverting PRD Risk 5's priority — or a second, order-dependent write path into the helper STORY-014 exists to make singular. Neither belongs in a read story; it is named for the backlog. |
| Story AC 9: a failed read sets `sessions_error`. | Also clears nothing, and specifically leaves `active_session_id` where it was. | The AC names `messages` and the composer. `active_session_id` is what the rail marks: moving it to a chat whose transcript failed to load would leave the rail pointing at a conversation that is not on screen, which is the misattribution `logout`'s comment (`:188-190`) refuses on the same surface. Stated here because "left as it was" is being read wider than the AC's literal words. |
| Story AC 9 implies a message; `copy.py:109` says *"The rail's own strings are STORY-017's."* | Adds `TRANSCRIPT_NOT_LOADED_NOTICE` to `copy.py` now. | It is a state notice, not a rail string — the same category as `TRANSCRIPT_NOT_SAVED_NOTICE`, which STORY-014 added to this same block for the same reason. It takes no string STORY-017 enumerates (rail labels, the empty-rail invitation, the delete confirmation). |
| PRD Section 6: *"`ChatState` calls the service, never `database.py` directly."* | Unchanged — and one **test** patches `chat_state_mod.chat_sessions.database.list_chat_messages`. | Test case 12 only, to produce a `StorageError` that escaped the service's wrapping. This is the existing pattern at `tests/test_chat_state.py:1477`, and it reaches through the service rather than around it. No production line in `chat_ui/` calls `database.py`. |
| Story: *"the ownership check runs server-side on every switch."* | `select_session` performs no ownership check of its own. | That *is* the server-side check: `chat_sessions.messages_for` scopes on `identity.user_id` (`chat_sessions.py:315` → `database.py:1745-1748`) against an Identity re-resolved from `_token` on every call, never against the var. A second check in `state.py` would be a client-side one wearing a server-side name, and it would have to distinguish "foreign" from "empty" — which the service refuses to do on purpose (`chat_sessions.py:300-302`). Test case 13 asserts the behaviour instead. |

---

## Risks

| Risk | Mitigation |
|---|---|
| **PRD Risk 3** — `active_session_id` is client-visible and names a row; a restore that trusted it would read another user's conversation. | The var is never used as authority. Every read goes through `chat_sessions.messages_for(identity, session_id)` with the Identity re-resolved from `_token` inside the handler, and the store scopes the `WHERE` on it. Test case 13 drives the foreign-id path and asserts an empty transcript with no error, and `tests/test_session_ownership.py:381` already pins `messages_for` in `_SERVICE_READS`. |
| Someone wraps `_read_transcript` or a `login()` line in `async with self`, copying the pattern from `_append_and_persist` twelve lines away. | It deadlocks on a lock the handler already holds — `login`'s docstring (`:136-148`) states this and the new helper's docstring restates it with the inverse rule named. Every login test in the suite hangs, not fails subtly; the compile step and Task 8 case 6 both exercise the path. |
| The rehydration is called from `_do_send` by a later author, where `self` is a `StateProxy` and direct mutation raises. | `_read_transcript` mutates nothing at all, so the failure mode is confined to the caller's own assignment. Its docstring names the two legal callers. The AST guard at `:1586-1622` independently pins `_do_send` to exactly six `_append_and_persist` calls and no `self.messages.append`, so a restore spliced in there fails a test. |
| `pii_entities` restores as `[""]`, putting a phantom entity in the assistant footer's badge — the exact defect `database.py:1663` predicted for this story by name. | The split is guarded, the docstring cites the line, and Task 8 case 4 asserts `[]` for a message with no entities. Mutation-checked: removing the guard must fail that case. |
| `format_duplicate_info` is applied to every kind because it is simpler, putting `DUPLICATE_FALLBACK_TEXT` on user bubbles. | Gated on `kind == "duplicate"` with the reason at the gate (`formatting.py:70-71` returns the fallback, not `""`, for an empty timestamp). Mutation-checked: dropping the gate must fail Task 8 case 1. Invisible in the rendered page today — only `render_duplicate` reads those fields — which is exactly why it needs a test rather than a review. |
| A `duplicate` restores with stored copy rather than recomputed, so "already sent 2m ago" is still 2m ago tomorrow. | The two fields have no column to read from, so the defect is unbuildable — but Task 8 case 3 asserts it positively anyway, including that two different `first_query_at` values restore to different strings. |
| A restored bubble's empty `prompt` gives an **Edit and resend** or **Retry** button that resends nothing — a control that lies. | `prompt` round-trips through a column and Task 8 case 5 asserts it for all four kinds that carry an action, then drives `edit_and_resend` and checks the composer actually refills. |
| A column added to `chat_messages` later is written by `_to_stored_message` and silently dropped by `_to_chat_message`, so transcripts lose a field with no test failing. | Task 8 case 15 walks `dataclasses.fields(StoredMessage)` against `_to_chat_message`'s AST and fails on any unread field. The read side gains the guard the write side already has. |
| The lock is held across a database read in `login()` and `select_session`, so a slow store blocks every other event for that user. | Accepted, and pre-existing: `login()` has held it across `list_for` since STORY-013. The alternative — a background task — cannot be chained from `login()` at all, which is the constraint that produced the current shape. The read is one indexed query (`idx_chat_messages_session_id`) with no `limit` by design (`chat_sessions.py:304-309`). Recorded so the tradeoff is chosen rather than inherited silently. |
| `TRANSCRIPT_NOT_LOADED_NOTICE` is added but nothing renders it, so a failed restore is silent in the running app until STORY-018/019. | Bounded, understood, and identical to the interval `sessions_error` has sat in since STORY-013 and `transcript_error` since STORY-014. The state-level tests assert the notice regardless of the surface, and STORY-018 inherits three notice slots rather than one. |
| `select_session` is unreachable in the running app until the rail exists, so the E2E column for the switch is a REPL rather than a click. | Stated in End-to-End Tests. STORY-018 is the named owner and STORY-021's two-instance smoke is the story that closes it end to end. |

---

## Acceptance Criteria

(Copied from story `STORY-015`)

- [ ] Given a signed-in user with sessions, when the page loads, then the most recently active session becomes active and its transcript is rendered.
- [ ] Given `select_session(session_id)`, when it runs, then `self.messages` is replaced by that session's stored messages, in `id ASC` order, and `active_session_id` moves.
- [ ] Given a switch, when it completes, then `selected_model`, `user_id` and `_token` are untouched.
- [ ] Given each of the seven kinds — `user`, `assistant`, `duplicate`, `injection`, `forbidden`, `upstream_error`, `internal_error` — when it is stored and restored, then the rendered bubble is indistinguishable from the live one: same ink, same tag, same detail, same actions.
- [ ] Given a restored `duplicate` bubble, when it renders, then `duplicate_relative_info` and `duplicate_release_info` are **recomputed** from the stored `first_query_at` through `format_duplicate_info`, not read from storage.
- [ ] Given a restored `assistant` bubble, when it renders, then its footer shows the same `model_used`, `tokens_used` and `#audit_id`, and its PII badge shows the same entity list.
- [ ] Given a restored `duplicate`, `injection` or error bubble, when it renders, then **Retry** and **Edit and resend** work — `prompt` survived the round trip.
- [ ] Given a switch while `pending` is true, when it is attempted, then it is refused.
- [ ] Given a read that raises, when it is caught, then `sessions_error` is set, `self.messages` is left as it was, and the composer stays usable.
- [ ] Given `settings.CHAT_HISTORY_ENABLED is False`, when the page loads, then no read is attempted and the chat opens empty, exactly as today.
- [ ] Given `tests/test_chat_state.py`, when it runs, then a store/restore round trip is asserted **per kind**, not once for a representative kind.
- [ ] All tasks completed
- [ ] `cd chat_ui && reflex compile --dry` succeeds
- [ ] Full suite green (`python -m pytest -q`)
- [ ] Follows existing patterns
