---
story: STORY-007
prd: PRD-018
plan: .agents/plans/PRD-018-db-resilience/completed/STORY-007-chat-ui-storage-failures.plan.md
epic_branch: epic/PRD-018-db-resilience
commit: 4f1073e
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report - STORY-007: Chat UI survives a storage failure

## Summary

`_do_send` now resolves the identity inside its try/finally and off the event loop; a `StorageError` gives an `internal_error` bubble with fixed copy and `pending` is cleared. `login` offloads `resolve` and shows a storage notice (not "invalid token") on `StorageError`. The gate arm applies the "caused by" rule via `storage_unavailable_cause`; `ChatSessionError` joined the named arm. Two new strings in `copy.py`.

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests | 270 passed, 0 failed, 0 skipped (after one pinned-count update) |
| Full suite | GitHub CI on push (user decision) |

Run: test_chat_ui_storage_failures, test_copy, test_chat_state, test_chat_ui_startup_guard, test_chat_components_import, test_chat_outcomes_regression. First run: 269 passed, 1 failed (AST pin of `_append_and_persist` call count, 6 -> 7); fixed and re-run (that test passes).

## Files Changed

`chat_ui/chat_ui/state.py`, `chat_ui/chat_ui/copy.py`, `tests/test_chat_ui_storage_failures.py` (new, 15 cases), `tests/test_copy.py` (+1 test), `tests/test_chat_state.py` (one pinned count 6 -> 7, commented).

## Deviations from Plan

- `tests/test_chat_state.py::test_every_bubble_append_in_do_send_goes_through_the_helper` pinned 6 calls; the new storage arm is a 7th. Assertion updated with a PRD-018 comment (plan said no assertion would change).
- Orchestrator resolutions: the catch-all `except Exception` is unchanged (STORY-010 owns it); the four other inline `resolve()` calls (retry_sessions, select_session, rename_session, delete_session) stay as they are (follow-up).
- `chat_ui/AGENTS.md` asks for the Reflex agent skills before Reflex edits; they were not available and were not installed. Edits follow existing patterns; no markup changed.

## Acceptance Criteria

- [x] resolve StorageError in `_do_send` -> fixed bubble, pending False (tests 1-3 in test_chat_ui_storage_failures.py)
- [x] login StorageError -> storage notice, not signed in (test_login_storage_unavailable_shows_the_storage_notice)
- [x] gate faults caused by outage -> fixed copy; other causes keep today's bubble (gate_fault tests; existing test_chat_state 437-471 unchanged)
- [x] new English strings in copy.py (test_copy.py new test)
- [x] chat UI tests + startup guard pass; pending pinned False after resolve failure
