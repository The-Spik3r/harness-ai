---
story: STORY-008
prd: PRD-004
slug: bubble-renderers-match-dispatch
title: "Six bubble renderers dispatched by rx.match on kind"
type: feature
complexity: large
epic_branch: epic/PRD-004-chat-ui-redesign
created: 2026-08-21
---

# Plan: Six bubble renderers dispatched by rx.match on kind

## Summary

Create `chat_ui/chat_ui/components/bubbles.py` exposing six distinct bubble renderers (`user`, `assistant`, `duplicate`, `injection`, `upstream_error`, `internal_error`) with zero hardcoded literals (using `chat_ui.copy`), and update `chat_ui/chat_ui/components/chat.py` to dispatch via a single `rx.match(message.kind, ...)` replacing the legacy nested `rx.cond`.

## User Story

As an end user, I want a duplicate block, an injection block, an upstream failure and an internal failure to look different from each other, so that I can tell "you already asked this" apart from "this was logged as a security event" and from "the provider is down" (PRD User Story 2, Section 2 "Every outcome is visible").

## Story Reference

- Story file: `.agents/stories/PRD-004-chat-ui-redesign/STORY-008-bubble-renderers-match-dispatch.md`
- PRD: `.agents/PRDs/PRD-004-chat-ui-redesign/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | feature |
| Complexity | LARGE |
| Systems Affected | `chat_ui/chat_ui/components/bubbles.py` (CREATE), `chat_ui/chat_ui/components/chat.py` (UPDATE) |
| Story | STORY-008 |
| PRD | PRD-004 |
| Epic Branch | `epic/PRD-004-chat-ui-redesign` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| reflex-docs | `rx.match`, component composition, and attribute access in Reflex apps | Task 1, Task 2 |
| reflex-process-management | Verifying compilation and runtime after component refactoring | Task 3 |

---

## Patterns to Follow

### Naming & Dispatch
```python
// SOURCE: chat_ui/chat_ui/components/chat.py:6-51
def message_bubble(message) -> rx.Component:
    return rx.cond(message.kind == "user", ...)
```

### Copy Usage
```python
// SOURCE: chat_ui/chat_ui/copy.py
UPSTREAM_ERROR_PREFIX = "OpenRouter upstream error"
INTERNAL_ERROR_PREFIX = "Internal error"
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/components/bubbles.py` | CREATE | Define six distinct bubble renderers for user, assistant, duplicate, injection, upstream_error, and internal_error |
| `chat_ui/chat_ui/components/chat.py` | UPDATE | Replace nested `rx.cond` with `rx.match(message.kind, ...)` dispatching to the six renderers plus default arm |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create `chat_ui/chat_ui/components/bubbles.py`
- **File**: `chat_ui/chat_ui/components/bubbles.py`
- **Action**: CREATE
- **Implement**: Define six renderers using constants from `chat_ui.copy`:
  - `render_user(message)`: right-aligned blue user bubble
  - `render_assistant(message)`: left-aligned assistant bubble (with hook points for PII badge / footer)
  - `render_duplicate(message)`: benign-nudge card (styled distinctly from security events)
  - `render_injection(message)`: security-event card displaying matched `pattern`
  - `render_upstream_error(message)`: upstream-incident card naming OpenRouter explicitly (`UPSTREAM_ERROR_PREFIX` + `detail`)
  - `render_internal_error(message)`: internal error card showing `detail` (`INTERNAL_ERROR_PREFIX` + `detail`)
- **Mirror**: PRD Section 4 / Story 008 requirements.
- **Validate**: Python syntax check and module import.

### Task 2: Update `chat_ui/chat_ui/components/chat.py`
- **File**: `chat_ui/chat_ui/components/chat.py`
- **Action**: UPDATE
- **Implement**: Replace legacy `message_bubble` with `rx.match(message.kind, ...)` dispatching to `render_user`, `render_assistant`, `render_duplicate`, `render_injection`, `render_upstream_error`, `render_internal_error`, and a default fallback arm rendering a visible bubble for unknown kinds.
- **Mirror**: PRD Section 6 discriminated union rendering.
- **Validate**: pytest test suite (`pytest tests/test_chat_state.py`) and reflex compile.

### Task 3: Verify Compilation and Tests
- **File**: Test suite and reflex application
- **Action**: VERIFY
- **Implement**: Run tests and check application builds without error.
- **Validate**: `pytest tests/test_chat_state.py`

---

## End-to-End Tests

- [ ] `chat_ui/chat_ui/components/bubbles.py` imports cleanly
- [ ] `components/chat.py` dispatches via `rx.match` on `message.kind` to six renderers
- [ ] `pytest tests/test_chat_state.py` passes

---

## Validation

```bash
pytest tests/test_chat_state.py
```

---

## Acceptance Criteria

- [ ] Given `chat_ui/chat_ui/components/bubbles.py`, when it is created, then it exposes one renderer per `kind` — `user`, `assistant`, `duplicate`, `injection`, `upstream_error`, `internal_error` — and no two semantically different outcomes share a bubble style.
- [ ] Given `components/chat.py`, when a message is rendered, then dispatch is a single `rx.match` on `message.kind`, replacing the nested `rx.cond` over three roles.
- [ ] Given a `duplicate` message, when rendered, then it uses benign-nudge styling; given an `injection` message, then it uses security-event styling and displays the matched `pattern` value.
- [ ] Given an `upstream_error` message, when rendered, then it is an upstream-incident card that names OpenRouter as the failing party, visually distinct from the `internal_error` card.
- [ ] Given any error card, when rendered, then it shows `detail`.
- [ ] Given `rx.match` over `kind`, when an unknown kind value is encountered, then the default arm still renders a visible bubble rather than nothing.
- [ ] All tasks completed.
