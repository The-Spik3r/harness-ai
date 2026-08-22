---
story: STORY-007
prd: PRD-004
slug: copy-module
title: "Centralize all user-facing copy in chat_ui/copy.py"
type: technical
complexity: small
epic_branch: epic/PRD-004-chat-ui-redesign
created: 2026-08-21
---

# Plan: Centralize all user-facing copy in chat_ui/copy.py

## Summary

Centralize all user-facing strings, labels, templates, and risk mitigations (PII exchange phrasing, duplicate modification notice, and explicit OpenRouter upstream error naming) into a dedicated `chat_ui/chat_ui/copy.py` module.

## User Story

As an integrating developer, I want every user-facing string in one module, so that changing display language is a single-file edit rather than a hunt through components (PRD Section 4, Section 13 "Full i18n").

## Story Reference

- Story file: `.agents/stories/PRD-004-chat-ui-redesign/STORY-007-copy-module.md`
- PRD: `.agents/PRDs/PRD-004-chat-ui-redesign/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | technical |
| Complexity | SMALL |
| Systems Affected | `chat_ui/chat_ui/copy.py` (CREATE) |
| Story | STORY-007 |
| PRD | PRD-004 |
| Epic Branch | `epic/PRD-004-chat-ui-redesign` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| reflex-docs | Python module structure and constants in Reflex apps | Task 1 |

---

## Patterns to Follow

### Naming
```python
// SOURCE: chat_ui/chat_ui/models.py:4
class ChatMessage(pydantic.BaseModel):
```

### Error Handling
```python
// SOURCE: chat_ui/chat_ui/state.py:76
except OpenRouterError as exc:
```

### Tests
```python
// SOURCE: tests/test_chat_state.py:183-184
assert state.messages[-2] == {"role": "user", "content": "hello world"}
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/copy.py` | CREATE | Centralize all user-facing copy, templates, labels, and risk mitigations |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create `chat_ui/chat_ui/copy.py`

- **File**: `chat_ui/chat_ui/copy.py`
- **Action**: CREATE
- **Implement**: Define module-level constants and string templates for:
  - Welcome message / initial state copy
  - User ID prompt title, placeholder, button label, and validation/presence check messages
  - Composer input placeholder (`"Message..."`)
  - Six outcome / bubble labels & messages (including explicit OpenRouter naming for upstream error per Risk 7)
  - PII badge template specifying exchange-wide masking (`"masked in this exchange"`, per Risk 5)
  - Footer separators and metadata labels (`" ·"`, `"tokens"`, `"#"` for audit id)
  - Retry label (`"Retry"`) and Edit-and-resend label & notice stating text must change to go through (per Risk 4)
- **Mirror**: PRD Section 4 / Story 007 requirements.
- **Validate**: Python syntax check and module import.

---

## End-to-End Tests

- [ ] `chat_ui/chat_ui/copy.py` imports cleanly without error
- [ ] All required copy constants and risk mitigations (Risk 4, Risk 5, Risk 7) are present

---

## Validation

```bash
python -c "import chat_ui.copy"
```

---

## Acceptance Criteria

- [ ] Given `chat_ui/chat_ui/copy.py`, when it is created, then it holds every user-facing string the chat renders: the six bubble labels, the PII badge template, the footer separators, the retry and edit-and-resend labels, the empty state, the composer placeholder and the `user_id` prompt and validation messages.
- [ ] Given the PII badge copy, when read, then it says the masking applies to the exchange (e.g. "masked in this exchange"), never wording that implies only the user's prompt (Risk 5).
- [ ] Given the duplicate-bubble copy, when read, then it states that the text must change for the resend to go through (Risk 4).
- [ ] All tasks completed.
