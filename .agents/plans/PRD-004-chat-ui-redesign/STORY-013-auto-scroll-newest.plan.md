---
story: STORY-013
prd: PRD-004
slug: auto-scroll-newest
title: "Auto-scroll the message area to the newest message on append"
type: ENHANCEMENT
complexity: SMALL
epic_branch: epic/PRD-004-chat-ui-redesign
created: 2026-08-24
---

# Plan: Auto-scroll the message area to the newest message on append

## Summary

Replace the bare `overflow_y="auto"` `rx.box` in `message_list()` with Reflex's `rx.auto_scroll` component so that newly appended messages, all six message kinds, and the pending indicator are automatically scrolled into view without manual scrolling.

## User Story

As an end user, I want the conversation to scroll to the newest message automatically, so that a reply that lands below the fold is not invisible (PRD Section 4, Section 7).

## Story Reference

- Story file: `.agents/stories/PRD-004-chat-ui-redesign/STORY-013-auto-scroll-newest.md`
- PRD: `.agents/PRDs/PRD-004-chat-ui-redesign/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | SMALL |
| Systems Affected | `chat_ui/` |
| Story | STORY-013 |
| PRD | PRD-004 |
| Epic Branch | `epic/PRD-004-chat-ui-redesign` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| reflex-docs | Reflex component API (`rx.auto_scroll`) | Task 1 |
| reflex-process-management | Compiling / running / testing Reflex app | Task 2 |

---

## Patterns to Follow

### Components
```python
// SOURCE: chat_ui/chat_ui/components/chat.py:30-46
def message_list() -> rx.Component:
    """Scrollable column of chat bubbles, grows to fill available height."""
    return rx.auto_scroll(
        rx.foreach(ChatState.messages, message_bubble),
        rx.cond(
            ChatState.pending,
            render_pending_indicator(),
            rx.fragment(),
        ),
        display="flex",
        flex_direction="column",
        gap="0.75rem",
        flex="1",
        width="100%",
        padding="1rem",
    )
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/components/chat.py` | UPDATE | Replace `rx.box` with `overflow_y="auto"` with `rx.auto_scroll` in `message_list()` |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Replace rx.box with rx.auto_scroll in message_list
- **File**: `chat_ui/chat_ui/components/chat.py`
- **Action**: UPDATE
- **Implement**: Change `rx.box(..., overflow_y="auto", ...)` to `rx.auto_scroll(..., display="flex", flex_direction="column", gap="0.75rem", flex="1", width="100%", padding="1rem")`.
- **Validate**: Python syntax check and test execution (`pytest`).

### Task 2: Verify changes and run test suite
- **File**: `tests/`
- **Action**: VERIFY
- **Implement**: Run `pytest` to ensure all tests pass.
- **Validate**: All test suites passing successfully.
