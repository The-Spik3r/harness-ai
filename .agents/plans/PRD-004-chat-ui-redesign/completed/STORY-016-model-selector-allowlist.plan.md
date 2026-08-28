---
story: STORY-016
prd: PRD-004
slug: model-selector-allowlist
title: "Model selector driven by a curated allowlist in config.py"
type: FEATURE
complexity: MEDIUM
epic_branch: epic/PRD-004-chat-ui-redesign
created: 2026-08-25
---

# Plan: Model selector driven by a curated allowlist in config.py

## Summary

Implement a curated model allowlist in `chat_ui/chat_ui/config.py` (with no new environment variables), add `selected_model` state and `set_selected_model` event handler to `ChatState`, pass `model=self.selected_model` in `send()`, and replace the header model selector slot (`model_selector_slot()`) with a working model selector component.

## User Story

As an end user, I want to choose which model answers my message, so that the model shown in the assistant footer is one I picked rather than a hardcoded constant (PRD Section 4, Section 7).

## Story Reference

- Story file: `.agents/stories/PRD-004-chat-ui-redesign/STORY-016-model-selector-allowlist.md`
- PRD: `.agents/PRDs/PRD-004-chat-ui-redesign/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | FEATURE |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/` |
| Story | STORY-016 |
| PRD | PRD-004 |
| Epic Branch | `epic/PRD-004-chat-ui-redesign` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| reflex-docs | Reflex component APIs (`rx.select`, state variables, event handlers) | Task 1, 2, 3 |
| reflex-process-management | Compiling, running, and testing Reflex app | Task 4 |

---

## Patterns to Follow

### Config & State
```python
# SOURCE: chat_ui/chat_ui/state.py
# State variables and event handlers follow existing ChatState conventions
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/config.py` | CREATE | Curated model allowlist and default selection constant |
| `chat_ui/chat_ui/state.py` | UPDATE | Add `selected_model` state var and `set_selected_model` handler; pass `model=self.selected_model` to `run_query` in `send()` |
| `chat_ui/chat_ui/components/shell.py` | UPDATE | Replace `model_selector_slot()` with an interactive model selector bound to `ChatState.selected_model` and `ChatState.set_selected_model` |
| `tests/test_chat_state.py` (or new test file) | UPDATE | Add unit tests verifying model selection state and `run_query` model passing |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create chat_ui/chat_ui/config.py
- **File**: `chat_ui/chat_ui/config.py`
- **Action**: CREATE
- **Implement**: Create `chat_ui/chat_ui/config.py` defining `MODEL_ALLOWLIST` (e.g. `["gpt-4", "claude-3-sonnet", "openai/gpt-4o", "anthropic/claude-3.5-sonnet"]`) and `DEFAULT_MODEL = "gpt-4"`. No new environment variables.
- **Mirror**: Configuration file conventions across backend/frontend modules.
- **Validate**: Python syntax check and module import.

### Task 2: Update chat_ui/chat_ui/state.py
- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: Import `DEFAULT_MODEL` from `.config`. Add state variable `selected_model: str = DEFAULT_MODEL`. Add event handler `set_selected_model(self, model: str)`. Update `send()` to pass `model=self.selected_model` instead of hardcoded `"gpt-4"`.
- **Mirror**: `chat_ui/chat_ui/state.py:24-83`
- **Validate**: `pytest tests/test_chat_state.py`

### Task 3: Update chat_ui/chat_ui/components/shell.py
- **File**: `chat_ui/chat_ui/components/shell.py`
- **Action**: UPDATE
- **Implement**: Import `MODEL_ALLOWLIST` from `chat_ui.config`. Replace `model_selector_slot()` with `model_selector()` component using `rx.select` (or Radix select) bound to `ChatState.selected_model` and `ChatState.set_selected_model`, offering exactly the allowlist entries and no free-text entry.
- **Mirror**: `chat_ui/chat_ui/components/shell.py:17-27`
- **Validate**: Reflex compilation / import test.

### Task 4: Add and run tests
- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE
- **Implement**: Add unit tests verifying that selecting a model updates `ChatState.selected_model`, that `send()` passes `selected_model` to `run_query`, and that audit logs record the selected model.
- **Mirror**: Existing test patterns in `tests/test_chat_state.py`.
- **Validate**: `pytest` passes 100%.

---

## End-to-End Tests

- [ ] Start Reflex app, inspect header model selector -> shows allowlist entries with default selected
- [ ] Select a different model (e.g. `claude-3-sonnet`), send a message -> assistant footer shows `claude-3-sonnet`
- [ ] Inspect audit row -> `model_used` matches the selection
- [ ] Change user ID -> model selection remains unchanged (session-level UI choice, not persisted state)
- [ ] All existing test suites pass

---

## Validation

```bash
pytest
cd chat_ui && reflex run --env prod
```

---

## Acceptance Criteria

- [ ] Given `chat_ui/chat_ui/config.py`, when it is created, then it holds a curated model allowlist and the default selection — a UI-level constant, with no new environment variable (PRD Section 9).
- [ ] Given the header, when it renders, then a model selector offers exactly the allowlist entries and no free-text entry.
- [ ] Given a selected model, when a message is sent, then it is passed as `QueryRequest.model` into `run_query(...)`, replacing the hardcoded `model="gpt-4"` at `state.py:64`.
- [ ] Given a message sent with a selected model, when the resulting audit row is inspected, then its `model_used` matches the selection (PRD Section 11), and the assistant footer shows the same value.
- [ ] Given the selector, when the session changes user, then the selection behavior is unchanged — the model is a session-level UI choice, not persisted state.
- [ ] All tasks completed
- [ ] Follows existing patterns
