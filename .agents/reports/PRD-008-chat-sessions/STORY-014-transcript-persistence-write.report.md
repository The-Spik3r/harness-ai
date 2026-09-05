---
story: STORY-014
prd: PRD-008
plan: .agents/plans/PRD-008-chat-sessions/completed/STORY-014-transcript-persistence-write.plan.md
epic_branch: epic/PRD-008-chat-sessions
commit: 36da168
status: COMPLETE
completed: 2026-09-05
---

# Implementation Report — STORY-014: Persist each bubble after it is appended, touch the session, and degrade without losing the turn

**Plan**: `.agents/plans/PRD-008-chat-sessions/completed/STORY-014-transcript-persistence-write.plan.md`
**Epic Branch**: `epic/PRD-008-chat-sessions`
**Commit**: `36da168`

## Summary

`_do_send` appended a `ChatMessage` in eight places and wrote nothing. All eight now route through one helper, `ChatState._append_and_persist(bubble, identity, session_id)`, which appends under the state lock, then offloads `chat_sessions.append_message(...)` and `chat_sessions.touch(...)`, then promotes the active chat to the front of `self.sessions` from a freshly read `ChatSession` row.

Two independent `except Exception` arms sit after the append, which is the whole of PRD Risk 5: a transcript write that fails costs the *saving*, never the answer. A failed `append_message` sets `transcript_error` to `TRANSCRIPT_NOT_SAVED_NOTICE`; a failed `touch` sets `sessions_error` to `SESSION_ORDER_STALE_NOTICE` and leaves `transcript_error` empty, because after a successful write "this turn was not saved" would be a falsehood in the interface.

`CHAT_HISTORY_ENABLED` is never named in `chat_ui/`. With history off, STORY-013's create arm leaves `session_id` as `None` and the helper's `identity is None or not session_id` guard returns before any call — no write, no notice. That same guard is what lets the invalid-credential arm, which has no `Identity` at all, use the one helper instead of keeping a hand-rolled append a future outcome could be copied from.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Two failure notices, distinct by design | `chat_ui/chat_ui/copy.py` | ✅ |
| 2 | `transcript_error` var, separate from `sessions_error` | `chat_ui/chat_ui/state.py` | ✅ |
| 3 | `_to_stored_message` — bubble → `StoredMessage`, falsy to `None` | `chat_ui/chat_ui/state.py` | ✅ |
| 4 | `_append_and_persist` + `_promote_session` | `chat_ui/chat_ui/state.py` | ✅ |
| 5 | All eight append sites routed through the helper | `chat_ui/chat_ui/state.py` | ✅ |
| 6 | `logout()` clears `transcript_error` | `chat_ui/chat_ui/state.py` | ✅ |
| 7 | Copy assertions | `tests/test_copy.py` | ✅ |
| 8 | The STORY-014 test section (17 cases) | `tests/test_chat_state.py` | ✅ |
| 9 | Compile + full suite | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `import chat_ui.chat_ui.state` | ✅ |
| `reflex compile --dry` | ✅ (compiled in 6.5s, no new warnings) |
| `tests/test_chat_state.py` | ✅ 71 passed (54 pre-existing + 17 new) |
| `tests/test_copy.py` | ✅ 25 passed |
| `tests/test_chat_sessions.py`, `test_session_ownership.py`, `test_db.py` | ✅ 287 passed |
| `tests/test_untouched_app.py` (census + AST guards) | ✅ 9 passed |
| `tests/test_chat_components_import.py`, `test_render_invariants.py`, `test_rbac.py` | ✅ 77 passed |
| Full suite | ✅ 1472 passed |
| E2E | ⚠️ 9/10 — the live boot could not be run; see **Deviations** |

### Mutation checks

Two assertions were verified to fail against the defect they exist to catch, rather than trusted to pass:

| Mutation | Test that caught it |
|---|---|
| The write moved ahead of the append (the ordering AC 1 forbids) | `test_the_bubble_is_appended_before_it_is_written` ❌→ correctly failed |
| A "ninth outcome" appending directly in `_do_send` | `test_every_bubble_append_in_do_send_goes_through_the_helper` ❌→ correctly failed |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/copy.py` | UPDATE | +19 |
| `chat_ui/chat_ui/state.py` | UPDATE | +216/-43 |
| `tests/test_chat_state.py` | UPDATE | +397/-1 |
| `tests/test_copy.py` | UPDATE | +29 |

No file created; `app/` untouched.

## Deviations from Plan

All five deviations the plan recorded in advance were implemented as written. One further item arose during validation.

| Item | Outcome |
|---|---|
| Story said `state.py`, `_do_send` only | Also `copy.py` (required by the story itself) and one line in `logout()`, so a "turn not saved" notice cannot outlive the transcript it refers to. STORY-016 keeps every assertion its AC 8 names. |
| AC 2's "including `user`" | The `user` bubble of the **first** send of a new chat is not written: STORY-013 appends it before the lazy create, deliberately, so there is no `session_id` yet. `test_a_send_persists_the_user_bubble_and_the_assistant_bubble` encodes this as `["assistant", "user", "assistant"]` rather than hiding it. **STORY-015 inherits it**: a restored first turn starts at the `assistant` bubble. |
| AC 6's "the same applies" | A different notice on a different var. The AC's other half — a failed reorder "must not surface as a lost turn" — cannot hold with one string once `append_message` has succeeded. Behavioural half (bubble stays, `messages` intact, `pending` clears) satisfied exactly. |
| "never `database.py` directly" | `state.py` imports `ChatSession` and `StoredMessage` from `app.db.models` — dataclasses the service's own signature requires. No `app.db.database` function is called from `chat_ui/`. |
| Reorder "the in-state `sessions` list" | Done from a fresh `chat_sessions.get(...)`, so the title is the stored one (`derive_title` still runs exactly once per session) and the timestamp is the store's. |
| **E2E: the live boot was not run** | Blocked by pre-existing infrastructure, not by this story. The local libSQL dev container returns `STREAM_EXPIRED` to the long-lived Reflex server, while a short-lived process resolves the same token against the same server. It fails in `login() → resolve() → find_user_by_token_hash` — PRD-005 code untouched here — and was **reproduced at baseline `237226b` with all of this story's changes stashed**. A file-backed database is not an alternative: `app/config.py` rejects `sqlite:` URLs by design (PRD-007 removed the file fallback). The remaining option was seeding the live production Turso database, which was declined. The other nine E2E items are asserted at state level and pass. |

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_chat_state.py` | `test_a_send_persists_the_user_bubble_and_the_assistant_bubble`, `test_the_bubble_is_appended_before_it_is_written`, `test_every_bubble_kind_is_persisted` (×6: assistant, duplicate, injection, forbidden, upstream_error, internal_error), `test_the_assistant_row_stores_the_redacted_response`, `test_a_successful_write_touches_the_session_and_moves_it_to_the_front`, `test_the_first_send_puts_the_new_chat_at_the_front_of_the_rail`, `test_a_failed_append_keeps_the_turn_on_screen_and_reports_it`, `test_a_storage_error_that_escaped_wrapping_still_does_not_lose_the_turn`, `test_a_failed_touch_does_not_report_a_lost_turn`, `test_history_off_writes_nothing_and_says_nothing`, `test_the_audit_row_survives_a_failed_transcript_write`, `test_every_bubble_append_in_do_send_goes_through_the_helper` |
| `tests/test_copy.py` | `test_transcript_notices_name_the_saving_and_never_the_answer` |

## Acceptance Criteria

- [x] Given any send, when a bubble is appended to `self.messages`, then the same bubble is written with `chat_sessions.append_message(...)` **after** the append, not before and not instead. — `test_the_bubble_is_appended_before_it_is_written`, mutation-verified.
- [x] Given all seven bubble kinds, when each is produced, then each is persisted — including `user`, and including the four non-success outcomes and the two error kinds. — `test_every_bubble_kind_is_persisted`, with the documented first-send `user` exception.
- [x] Given an `assistant` bubble, when it is persisted, then the stored `content` is `QuerySuccessResponse.response`. — `test_the_assistant_row_stores_the_redacted_response`, asserting the raw text appears in **no** row.
- [x] Given a successful write, when it completes, then `chat_sessions.touch(...)` updates `updated_at` and the in-state `sessions` list reorders so the active chat is first. — `test_a_successful_write_touches_the_session_and_moves_it_to_the_front` and `test_the_first_send_puts_the_new_chat_at_the_front_of_the_rail`.
- [x] Given `append_message` raising, the bubble stays on screen, a notice states the turn was not saved, `self.messages` is not cleared, and `pending` still clears. — `test_a_failed_append_keeps_the_turn_on_screen_and_reports_it`.
- [x] Given `touch` raising, the same applies — a failed reorder must not surface as a lost turn. — `test_a_failed_touch_does_not_report_a_lost_turn`.
- [x] Given `CHAT_HISTORY_ENABLED is False`, no write is attempted, no notice appears, and the chat behaves exactly as today. — `test_history_off_writes_nothing_and_says_nothing`, with `append_chat_message` patched to raise if called at all.
- [x] Given `tests/test_chat_state.py`, a test patches `append_chat_message` to raise and asserts the transcript is intact, the notice is present and `pending` is `False`. — `test_a_storage_error_that_escaped_wrapping_still_does_not_lose_the_turn`.
- [x] Given the audit trail, when a transcript write fails, the audit row for that send is still present. — `test_the_audit_row_survives_a_failed_transcript_write`, driving the real pipeline.
- [x] All tasks completed
- [x] `reflex compile --dry` succeeds
- [x] Full suite green (1472 passed)
- [x] Follows existing patterns
