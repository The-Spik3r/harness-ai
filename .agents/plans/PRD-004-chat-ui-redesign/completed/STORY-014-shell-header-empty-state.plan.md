---
story: STORY-014
prd: PRD-004
slug: shell-header-empty-state
title: "Redesigned shell: header with session identity, and empty state"
type: FEATURE
complexity: MEDIUM
epic_branch: epic/PRD-004-chat-ui-redesign
created: 2026-08-24
---

# Plan: Redesigned shell — header with session identity, and empty state

## Summary

Implement the redesigned application shell (`chat_ui/chat_ui/components/shell.py`) providing a header with harness identity, session `user_id`, slots for the model selector and change-user action, and a designed empty state replacing the hardcoded `WELCOME_MESSAGE` dict. Update `ChatState` and `chat_ui.py` to compose header → message area (or empty state) → composer.

## User Story

As an end user, I want a proper chat shell with a header showing who I am in this session and a real empty state, so that the page explains itself instead of opening on a hardcoded fake greeting (PRD Section 4 Layout, Section 12 Phase 4).

## Story Reference

- Story file: `.agents/stories/PRD-004-chat-ui-redesign/STORY-014-shell-header-empty-state.md`
- PRD: `.agents/PRDs/PRD-004-chat-ui-redesign/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | FEATURE |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/` |
| Story | STORY-014 |
| PRD | PRD-004 |
| Epic Branch | `epic/PRD-004-chat-ui-redesign` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| frontend-design | Distinctive visual design for header and empty state | Task 1 |
| reflex-docs | Reflex component APIs (`rx.box`, `rx.hstack`, `rx.vstack`, `rx.cond`, etc.) | Task 1, 3 |
| reflex-process-management | Compiling, running, and testing Reflex app | Task 4 |

---

## Patterns to Follow

### Components & Copy
```python
# SOURCE: chat_ui/chat_ui/copy.py
# All user-facing strings must come from copy.py per STORY-007
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/components/shell.py` | CREATE | Header (session identity, user_id change action, model selector slot) and empty state component |
| `chat_ui/chat_ui/state.py` | UPDATE | Remove `WELCOME_MESSAGE`, initialize `messages: list[ChatMessage] = []`, add user_id reset/change action if needed |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | Compose header, message list (or empty state), and chat input |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create chat_ui/chat_ui/components/shell.py
- **File**: `chat_ui/chat_ui/components/shell.py`
- **Action**: CREATE
- **Implement**: Create header component with harness identity, current session `user_id`, change-user action, and model selector slot. Create empty state component replacing the welcome message. All strings sourced from `chat_ui.copy`.
- **Mirror**: Existing component patterns in `chat_ui/chat_ui/components/chat.py`.
- **Validate**: Python syntax check and module import test.

### Task 2: Update chat_ui/chat_ui/state.py
- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: Remove `WELCOME_MESSAGE`. Initialize `messages: list[ChatMessage] = []`. Add `reset_user_id` event handler to clear `user_id` so users can change their session identity without reloading the page.
- **Mirror**: `chat_ui/chat_ui/state.py:29-49`
- **Validate**: `pytest tests/test_chat_state.py`

### Task 3: Update chat_ui/chat_ui/chat_ui.py
- **File**: `chat_ui/chat_ui/chat_ui.py`
- **Action**: UPDATE
- **Implement**: Update `index()` function to compose header → message area (or empty state when `messages` is empty) → composer when `user_id != ""`, maintaining the `user_id_prompt()` gate when `user_id == ""`.
- **Mirror**: `chat_ui/chat_ui/chat_ui.py:25-36`
- **Validate**: `pytest tests/test_route_reservations.py` and Reflex build/compile check.

### Task 4: Verify full test suite
- **File**: `tests/`
- **Action**: VERIFY
- **Implement**: Run pytest across all test files to ensure backend and UI tests pass successfully.
- **Validate**: `pytest` passes 100%.

---

## End-to-End Tests

- [ ] Start Reflex app, enter user ID → lands on shell with header, empty state, and composer
- [ ] Send message → empty state disappears, message appears in scrollable list
- [ ] Click change user -> returns to user ID prompt or resets session identity
- [ ] All existing test suites pass

---

## Validation

```bash
pytest
cd chat_ui && reflex run --env prod
```

---

## Acceptance Criteria

- [ ] Given `chat_ui/chat_ui/components/shell.py`, when it is created, then it provides the header (harness identity, session `user_id`, slot for the model selector) and the empty state, and `chat_ui/chat_ui.py` composes header → message area → composer.
- [ ] Given an active session, when the header renders, then the current `user_id` is visible and there is an action to change it without reloading the page.
- [ ] Given the change-user action, when used, then the session `user_id` is replaced and subsequent sends pass the new value to `run_query(...)`.
- [ ] Given a conversation with no messages, when the page renders, then a designed empty state is shown and the hardcoded `WELCOME_MESSAGE` dict at `state.py:8-11` is gone — the app no longer fakes an assistant turn that the pipeline never produced.
- [ ] Given every string in the shell, when grepped, then it comes from `copy.py`.
- [ ] All tasks completed
- [ ] Follows existing patterns
