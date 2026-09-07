---
story: STORY-015
prd: PRD-008
plan: .agents/plans/PRD-008-chat-sessions/completed/STORY-015-transcript-restore.plan.md
epic_branch: epic/PRD-008-chat-sessions
commit: f096f2f
status: COMPLETE
completed: 2026-09-06
---

# Implementation Report — STORY-015: Restore a transcript on sign-in and on switch, rehydrating all seven bubble kinds

**Plan**: `.agents/plans/PRD-008-chat-sessions/completed/STORY-015-transcript-restore.plan.md`
**Epic Branch**: `epic/PRD-008-chat-sessions`
**Commit**: `f096f2f`

## Summary

STORY-014 left a one-way door: `_to_stored_message` wrote a bubble to a row and nothing read one back. `_to_chat_message(row)` is the inverse, written directly beneath it so the two read as a pair — every conversion is that function's read backwards, `or None` becoming `or ""` / `or 0` because a Reflex Var cannot be `None` on the wire, and `pii_entities` splitting on `","` with the empty case guarded.

Two callers walk through it, both **plain async handlers rather than background tasks**. `login()` opens the most recently active chat and renders it; `select_session(session_id)` is the switch, refused while `pending`. Plain async is what lets one helper serve both: those handlers hold the exclusive state lock for their whole duration, so `async with self` would deadlock on a lock they already hold — the inverse of `_do_send`'s rule, and the reason a background task would have forked the restore into two lock disciplines.

The duplicate copy is recomputed through the same `format_duplicate_info` the live branch calls, gated on `kind == "duplicate"` because the function returns `DUPLICATE_FALLBACK_TEXT` rather than `""` for an empty timestamp. `session_id` stays untrusted: ownership is re-checked server-side against an Identity resolved fresh from `_token`, and a foreign, unknown or history-off session all read empty alike.

`CHAT_HISTORY_ENABLED` is still named nowhere in `chat_ui/`. With history off, `list_for` returns `[]`, so `if self.sessions` is false and no read is attempted.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `TRANSCRIPT_NOT_LOADED_NOTICE`, the one new string | `chat_ui/chat_ui/copy.py` | ✅ |
| 2 | `_to_chat_message` — the inverse of `_to_stored_message` | `chat_ui/chat_ui/state.py` | ✅ |
| 3 | `_read_transcript` — the offloaded read, one place | `chat_ui/chat_ui/state.py` | ✅ |
| 4 | `select_session` — the switch, with the `pending` guard | `chat_ui/chat_ui/state.py` | ✅ |
| 5 | The restore arm inside `login()` | `chat_ui/chat_ui/state.py` | ✅ |
| 6 | Confirm `logout()` needs no change (verify only) | `chat_ui/chat_ui/state.py` | ✅ no edit |
| 7 | Copy assertions | `tests/test_copy.py` | ✅ |
| 8 | The STORY-015 test section (24 cases) | `tests/test_chat_state.py` | ✅ |
| 9 | Compile + full suite | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `import chat_ui.chat_ui.state` | ✅ |
| `from app.main import app` | ✅ |
| `reflex compile --dry` | ✅ compiled in 10.0s, no new warnings |
| `tests/test_chat_state.py` | ✅ 95 passed (71 pre-existing + 24 new) |
| `tests/test_copy.py` | ✅ 26 passed (25 + 1 new) |
| `tests/test_chat_sessions.py`, `test_session_ownership.py`, `test_db.py` | ✅ 299 passed |
| `tests/test_untouched_app.py` (census + AST guards) | ✅ included in the 86 below |
| `tests/test_chat_components_import.py`, `test_render_invariants.py`, `test_rbac.py` | ✅ 86 passed |
| Full suite | ✅ **1509 passed** (was 1472 after STORY-014) |
| E2E | ✅ **12/12** |

### Mutation checks

Three assertions were verified to fail against the defect they exist to catch, rather than trusted to pass. The first one **found a real gap in the tests as first written**.

| Mutation | Outcome |
|---|---|
| Drop the `if row.kind == "duplicate"` gate | ❌ **initially PASSED** — the round-trip comparison excluded the two derived fields, so nothing asserted that a user bubble stays free of duplicate copy. The test was strengthened to assert the derived fields per kind; the mutation then correctly failed all 6 cases. |
| `pii_entities` split left unguarded (`(row.pii_entities or "").split(",")`) | ✅ correctly failed 7 cases |
| `detail` no longer read from the row | ✅ correctly failed, naming the dropped field: `_to_chat_message drops ['detail']` |

### End-to-End

Driven against the local libSQL dev server the suite uses — **never the configured Turso database**, reusing `conftest._reset_database` rather than opening a second client. Only the OpenRouter network boundary is stubbed; the duplicate checker, pattern detector, PII redactor, audit write and the transcript store are all the production path.

| # | Check | Result |
|---|---|---|
| 1 | `reflex compile --dry` | ✅ |
| 2 | Reload restores the active transcript | ✅ `['user','assistant','user','assistant']` → `['assistant','user','assistant']` |
| 3 | Restored assistant carries `model_used`, `tokens_used`, `audit_id` | ✅ |
| 4 | Restored user bubble carries the prompt text | ✅ |
| 5 | Switch replaces the transcript | ✅ |
| 6 | Switch leaves `selected_model` and `user_id` untouched | ✅ |
| 7 | A **real** duplicate (same prompt twice, real checker) restores | ✅ |
| 8 | Restored duplicate recomputes its relative copy | ✅ `"Already sent just now (2026-09-06T04:40:28Z)"` |
| 9 | Restored duplicate keeps the prompt Edit-and-resend consumes | ✅ |
| 10 | Edit and resend refills the composer from a restored bubble | ✅ |
| 11 | Restored error bubble keeps its detail and its prompt | ✅ `detail='upstream timeout'` |
| 12 | `CHAT_HISTORY_ENABLED=false` opens empty and the chat still works | ✅ |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/copy.py` | UPDATE | +9 |
| `chat_ui/chat_ui/state.py` | UPDATE | +140 |
| `tests/test_chat_state.py` | UPDATE | +578/-3 |
| `tests/test_copy.py` | UPDATE | +33 |

No file created; `app/` untouched.

## Deviations from Plan

All six deviations the plan recorded in advance were implemented as written. Two further items arose during execution.

| Item | Outcome |
|---|---|
| No `on_load` wired | As planned. The API was confirmed against the pinned tree (`reflex/app.py:871`, normalized at `:969-970`; same parameter on `reflex/page.py:25`) and that confirmation is what disqualified it — `_token` is a backend var, so an `on_load` on the chat page fires with `user_id == ""` every time. **If a later story moves the credential to client storage, this decision must be revisited.** |
| First `user` bubble of a chat still absent from a restored transcript | Inherited from STORY-014, as planned. Every restore test sends twice; the shape is asserted rather than hidden. |
| Failed read leaves `active_session_id` where it was | As planned, and asserted. |
| `TRANSCRIPT_NOT_LOADED_NOTICE` added to `copy.py` | As planned — a state notice, not a rail string; takes nothing STORY-017 enumerates. |
| One test reaches through the service to `database.list_chat_messages` | As planned, test only, matching the existing STORY-014 pattern. |
| `select_session` performs no ownership check of its own | As planned — the service's `WHERE` is the check. |
| **NEW — `test_the_first_send_puts_the_new_chat_at_the_front_of_the_rail` needed updating** | Sign-in now opens the most recently active chat (AC 1), so a send straight after `login()` **continues** that chat instead of creating one. STORY-014's rail-insert assertion therefore now starts from a cleared `active_session_id` — the state STORY-016's "New chat" will produce, and the only one in which a create still happens. The test keeps its name and its subject; the change is documented in its docstring. This is a deliberate behavioural change the story requires, not a regression. |
| **NEW — the round-trip test was strengthened after a mutation check** | As first written it excluded the two derived duplicate fields from comparison, so removing the `kind == "duplicate"` gate passed. It now asserts those fields per kind. Recorded because the plan's mutation check is what caught it, and the plan's Risks section had named that exact defect as needing a test rather than a review. |

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_chat_state.py` | `test_every_bubble_kind_survives_the_round_trip` (×6: assistant, duplicate, injection, forbidden, upstream_error, internal_error — `user` asserted in each), `test_the_restored_transcript_is_in_id_order`, `test_a_restored_duplicate_recomputes_its_relative_copy`, `test_a_restored_assistant_keeps_its_footer_and_pii_badge`, `test_a_message_with_no_pii_entities_restores_to_an_empty_list`, `test_a_restored_bubble_keeps_the_prompt_its_actions_consume` (×4), `test_login_opens_the_most_recently_active_chat`, `test_login_with_no_sessions_leaves_the_chat_empty`, `test_a_switch_replaces_the_transcript_and_moves_the_active_id`, `test_a_switch_touches_nothing_else`, `test_a_switch_is_refused_while_pending`, `test_a_failed_read_keeps_the_transcript_and_reports_it`, `test_a_storage_error_that_escaped_wrapping_still_keeps_the_transcript`, `test_a_foreign_session_id_restores_empty_rather_than_erroring`, `test_history_off_reads_nothing_on_login`, `test_the_rehydration_reads_every_stored_field` (AST guard) |
| `tests/test_copy.py` | `test_the_load_notice_says_the_screen_is_unchanged_and_claims_no_lost_turn` |

## Known Debt

`select_session` and `TRANSCRIPT_NOT_LOADED_NOTICE` are not reachable from the running app until the rail exists (STORY-018/019) — the same interval `sessions_error` has sat in since STORY-013 and `transcript_error` since STORY-014. STORY-018 now inherits three notice slots rather than one. The state-level tests and the E2E driver assert the behaviour regardless of the surface.

## Acceptance Criteria

- [x] Given a signed-in user with sessions, when the page loads, then the most recently active session becomes active and its transcript is rendered.
- [x] Given `select_session(session_id)`, when it runs, then `self.messages` is replaced by that session's stored messages, in `id ASC` order, and `active_session_id` moves.
- [x] Given a switch, when it completes, then `selected_model`, `user_id` and `_token` are untouched.
- [x] Given each of the seven kinds, when it is stored and restored, then the rendered bubble is indistinguishable from the live one.
- [x] Given a restored `duplicate` bubble, then `duplicate_relative_info` and `duplicate_release_info` are recomputed from the stored `first_query_at`, not read from storage.
- [x] Given a restored `assistant` bubble, then its footer shows the same `model_used`, `tokens_used` and `#audit_id`, and its PII badge shows the same entity list.
- [x] Given a restored `duplicate`, `injection` or error bubble, then **Retry** and **Edit and resend** work — `prompt` survived the round trip.
- [x] Given a switch while `pending` is true, then it is refused.
- [x] Given a read that raises, then `sessions_error` is set, `self.messages` is left as it was, and the composer stays usable.
- [x] Given `settings.CHAT_HISTORY_ENABLED is False`, then no read is attempted and the chat opens empty.
- [x] Given `tests/test_chat_state.py`, then a store/restore round trip is asserted **per kind**, not once for a representative kind.
- [x] All tasks completed
- [x] `cd chat_ui && reflex compile --dry` succeeds
- [x] Full suite green (1509 passed)
- [x] Follows existing patterns
