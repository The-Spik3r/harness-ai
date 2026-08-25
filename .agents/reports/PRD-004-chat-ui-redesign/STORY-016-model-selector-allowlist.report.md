---
story: STORY-016
prd: PRD-004
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-016-model-selector-allowlist.plan.md
epic_branch: epic/PRD-004-chat-ui-redesign
commit: b418c07
status: COMPLETE
completed: 2026-08-25
---

# Implementation Report — STORY-016: Model selector driven by a curated allowlist in config.py

**Plan**: `.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-016-model-selector-allowlist.plan.md`
**Epic Branch**: `epic/PRD-004-chat-ui-redesign`

## Summary

Implemented a curated model allowlist in `chat_ui/chat_ui/config.py` with no new environment variables, added `selected_model` state and `set_selected_model` event handler to `ChatState`, passed `model=self.selected_model` into `run_query()`, replaced the shell header model selector slot with an interactive dropdown component, and added unit tests covering model configuration, state selection, and `run_query` model passing.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Create curated model allowlist config | `chat_ui/chat_ui/config.py` | ✅ |
| 2 | Update state with selected model & allowlist passing | `chat_ui/chat_ui/state.py` | ✅ |
| 3 | Replace model selector slot with interactive selector | `chat_ui/chat_ui/components/shell.py` | ✅ |
| 4 | Add unit tests for model selection and allowlist | `tests/test_chat_state.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import / Python syntax | ✅ |
| Frontend / UI tests & pytest | ✅ (226 passed) |
| E2E / manual checks | ✅ |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/config.py` | CREATE | +10 |
| `chat_ui/chat_ui/state.py` | UPDATE | +15/-3 |
| `chat_ui/chat_ui/components/shell.py` | UPDATE | +20/-15 |
| `tests/test_chat_state.py` | UPDATE | +45 |

## Deviations from Plan

None.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_chat_state.py` | `test_model_config_allowlist_and_default`, `test_chat_state_model_selection`, `test_chat_state_send_passes_selected_model` |

## Acceptance Criteria

- [x] Given `chat_ui/chat_ui/config.py`, when it is created, then it holds a curated model allowlist and the default selection — a UI-level constant, with no new environment variable (PRD Section 9).
- [x] Given the header, when it renders, then a model selector offers exactly the allowlist entries and no free-text entry.
- [x] Given a selected model, when a message is sent, then it is passed as `QueryRequest.model` into `run_query(...)`, replacing the hardcoded `model="gpt-4"` at `state.py:64`.
- [x] Given a message sent with a selected model, when the resulting audit row is inspected, then its `model_used` matches the selection (PRD Section 11), and the assistant footer shows the same value.
- [x] Given the selector, when the session changes user, then the selection behavior is unchanged — the model is a session-level UI choice, not persisted state.
