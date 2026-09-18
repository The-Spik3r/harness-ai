---
story: STORY-012
prd: PRD-010
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-012-chat-state-sends-history.plan.md
epic_branch: epic/PRD-010-multi-turn-pipeline
commit: PENDING
status: COMPLETE
completed: 2026-09-18
---

# Implementation Report — STORY-012: ChatState sends session history through run_conversation

**Plan**: `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-012-chat-state-sends-history.plan.md`
**Epic Branch**: `epic/PRD-010-multi-turn-pipeline`
**Commit**: `PENDING`

## Summary

`ChatState._do_send` now selects its pipeline **input**. With `CHAT_HISTORY_ENABLED` on and a chat that existed before this send, it awaits `run_in_pipeline(chat_history.assemble, identity, session_id)`, calls the pure `chat_history.fit(...)` inline with `settings.CONTEXT_MAX_MESSAGES` / `CONTEXT_MAX_CHARACTERS`, and awaits `run_in_pipeline(run_conversation, messages=…)`. Otherwise it takes today's `run_query` call, moved rather than rewritten. `fit`'s dropped count rides to the assistant bubble as the new `ChatMessage.history_trimmed: int = 0` and round-trips through the column STORY-010 added. A `ChatSessionError` from `assemble` degrades to sending without history and reports it, so the composer is never blocked.

Verified end to end on the real stack: send 1's upstream payload is one message; send 2's is `[user("What is 2+2?"), assistant(<stored reply>), user("what did I just ask?")]`, oldest first.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `ChatMessage.history_trimmed: int = 0` | `chat_ui/chat_ui/models.py` | ✅ |
| 2 | `had_session` local + the F8 branch | `chat_ui/chat_ui/state.py` | ✅ |
| 3 | Per-send `settings.CONTEXT_MAX_*` reads, reasoned | `chat_ui/chat_ui/state.py` | ✅ |
| 4 | `history_trimmed=trimmed` on the assistant bubble only | `chat_ui/chat_ui/state.py` | ✅ |
| 5 | Both mappers (`or None` exception documented) | `chat_ui/chat_ui/state.py` | ✅ |
| 6 | `_stub_pipeline` helper + 63 rewritten stub sites | `tests/test_chat_state.py` | ✅ |
| 7 | Two flag tripwires amended | `tests/test_chat_sessions.py`, `tests/test_chat_state.py` | ✅ |
| 8 | New behavioural suite | `tests/test_chat_history_send.py` | ✅ |
| — | Two further tripwires the plan missed (see Deviations) | `tests/test_chat_history.py`, `tests/test_pii_redaction_integration.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| `tests/test_history_off_integration.py` **unmodified** | ✅ (`git diff --stat` empty, 9 passed) |
| New suite `tests/test_chat_history_send.py` | ✅ 8 passed |
| Full suite | ✅ **2206 passed, 25 skipped, 0 failed** (166 s) |
| E2E | ✅ 5/6 — the live model call is deferred (below) |

There is no linter or formatter in this repo; "validate" is pytest against the local libSQL dev server.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_chat_history_send.py` | CREATE | +438 |
| `chat_ui/chat_ui/state.py` | UPDATE | +140/-24 |
| `chat_ui/chat_ui/models.py` | UPDATE | +12 |
| `tests/test_chat_state.py` | UPDATE | +152/-106 |
| `tests/test_chat_sessions.py` | UPDATE | +28 |
| `tests/test_pii_redaction_integration.py` | UPDATE | +15 |
| `tests/test_chat_history.py` | UPDATE | -34 |

## Deviations from Plan

1. **Two further tripwires, neither in the plan.** The plan found two; the suite held four.
   - `tests/test_chat_history.py::test_no_production_module_imports_chat_history_yet` failed the moment `state.py` imported the module. Its own docstring prescribes the remedy — *"**STORY-012 deletes this test.** Saying so here is what keeps it from being read later as a prohibition on using the module"* — so it was deleted, not amended.
   - `tests/test_pii_redaction_integration.py::test_no_pre_epic_test_function_was_removed_or_renamed` is a second census guard whose baseline (the `main` merge-base) *does* cover the PRD-008-era test the plan renamed. The plan checked `test_untouched_app.py` and cleared it, but missed this one. Resolved through the module's own `_DELIBERATELY_SUPERSEDED_TESTS` mechanism, with the rename and its authority documented — the same treatment the five PRD-008 STORY-023 renames already have there.

2. **A real defect the plan's degraded-arm test uncovered, fixed in `_do_send`.** Setting `sessions_error` at the point `assemble` fails is not enough: `_append_and_persist`'s successful `touch` clears that slot moments later (correctly — it has just proved the rail writable), so the user would have received a silently shortened conversation with no notice at all. The failure is now held in a `history_error` local and re-applied in the `finally` block, which also covers the upstream/internal-error arms that `return` before the append. Without this, AC "the composer… sets `sessions_error`" would have been satisfied transiently and false on screen.

3. **63 stub sites rewritten, not the ~33 the plan estimated.** The plan counted *tests*; several hold more than one `monkeypatch.setattr(chat_state_mod, "run_query", …)`, and single-send tests were converted too for consistency. Both intended survivors remain: the helper's own line and `tests/test_rbac.py:315` (a single send, first-send path, unaffected).

4. **The AC 4 fixture had to be restructured, and the reason is this PRD working.** Sending the same answered question twice is no longer a duplicate: the dedup key now runs over the whole conversation, so the repeat has a different prefix — PRD Section 5's user story 7 ("yes" after two different exchanges both go through). A blocked turn still collides, because an `injection` verdict writes an audit row but no assistant row, leaving the prefix unchanged. The test now sends answered → blocked → same-blocked, yielding one `injection` and one `duplicate` inside a single session. This is a behaviour change worth knowing about and is recorded in the test's docstring.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_chat_history_send.py` | `test_a_second_send_carries_the_first_exchange` (AC 1); `test_the_history_path_runs_assemble_and_the_pipeline_on_the_executor` (AC 1, routing — and that `fit` is *not* dispatched); `test_the_first_send_of_a_new_chat_never_assembles_history` (AC 2a); `test_a_second_send_with_history_off_never_assembles_history` (AC 2b); `test_a_trimmed_send_stores_the_dropped_count_and_restores_it` (AC 3); `test_a_send_that_dropped_nothing_stores_zero` (AC 3); `test_a_held_duplicate_and_a_blocked_prompt_stay_out_of_history` (AC 4, D4); `test_a_failed_assemble_sends_without_history_and_reports_it` (degraded arm, PRD-004 Risk 3) |
| `tests/test_chat_state.py` | `test_chat_state_names_the_history_flag_once_and_only_in_do_send` (replaces the zero-reference guard; asserts one read, inside `_do_send`) |

## End-to-End Verification

Run headless against the real stack — real pipeline, real Presidio redaction, real libSQL persistence — with only the upstream call recorded rather than sent.

**Upstream payload, send 1** (unchanged from today, one message):
```json
[{"role": "user", "content": "What is 2+2?"}]
```

**Upstream payload, send 2** (PRD Section 11: "N−1 prior exchanges followed by the new user turn, oldest first"):
```json
[{"role": "user",      "content": "What is 2+2?"},
 {"role": "assistant", "content": "(reply 1)"},
 {"role": "user",      "content": "what did I just ask?"}]
```

**Reload onto the session**: the transcript restores with `history_trimmed=0` on both assistant bubbles, `restored=True`, and no error on either slot. It begins at the assistant bubble — the pre-existing, documented limitation that a new chat's first user bubble is never persisted (PRD 6.4 fact 1), not a regression from this story.

| # | E2E check | Result |
|---|-----------|--------|
| 1 | New suite passes | ✅ |
| 2 | `test_history_off_integration.py` green with a zero-line diff | ✅ |
| 3 | `test_chat_state.py` + `test_session_rail.py` green | ✅ |
| 4 | Full suite green | ✅ |
| 5 | Send 2 carries send 1's exchange (payloads above) | ✅ |
| 6 | **Live model answers "what did I just ask?" with the first question** | ⏸ deferred — run immediately after this commit at the user's direction; it spends real OpenRouter credit, so it was not run unattended |

## Known State Handed to STORY-013

`QueryBlockedContextLimitResponse` is in the union `_do_send`'s `isinstance` chain walks, and the chain has no arm for it, so an over-limit conversation currently renders an `internal_error` bubble. Out of scope here by the story's own text; STORY-013 owns that bubble and the trimmed-history footer that reads `history_trimmed`. Left untouched rather than half-solved (plan R7).

## Acceptance Criteria

- [x] With history on and one prior answered exchange, the injected upstream records `[user, assistant(stored redacted reply), user]`, via `run_in_pipeline(chat_history.assemble, …)`, `fit(...)` with `settings.CONTEXT_MAX_*`, and `run_in_pipeline(run_conversation, …)`
- [x] First send of a new chat, or `CHAT_HISTORY_ENABLED=false`: `run_query` through `run_in_pipeline` with exactly today's keyword arguments, and `assemble` never called — `tests/test_history_off_integration.py` passes unmodified, with a raising tripwire proving the off path
- [x] A trimmed send carries `history_trimmed=<dropped count>` on the assistant bubble, `_to_stored_message` persists it, `_to_chat_message` restores it; a send that dropped nothing stores `0`
- [x] A turn held as duplicate or blocked as suspicious is absent from the next send's upstream messages (end to end through `temp_db`, D4)
- [x] `ChatMessage` has `history_trimmed: int = 0`; the full suite, including `test_chat_state.py` and `test_session_rail.py`, is green
- [x] All tasks completed
- [x] The composer is never blocked: a `ChatSessionError` from `assemble` sends without history and sets `sessions_error` — and the notice now survives to the end of the send
- [x] Follows existing patterns
