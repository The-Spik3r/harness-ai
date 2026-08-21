---
story: STORY-004
prd: PRD-004
slug: chat-message-model
title: "ChatMessage typed model replaces list[dict[str, str]]"
type: technical
complexity: medium
epic_branch: epic/PRD-004-chat-ui-redesign
created: 2026-08-21
---

# Plan: ChatMessage typed model replaces list[dict[str, str]]

## Summary

Replace untyped `list[dict[str, str]]` messages in `ChatState` with a typed Reflex model `ChatMessage` carrying a `kind` discriminator and metadata fields, updating `chat_ui/chat_ui/models.py`, `chat_ui/chat_ui/state.py`, and `chat_ui/chat_ui/components/chat.py`.

## User Story

As an integrating developer, I want chat messages to be a typed model with a `kind` discriminator, so that each pipeline outcome is distinguishable in state instead of being flattened into a formatted string.

## Story Reference

- Story file: `.agents/stories/PRD-004-chat-ui-redesign/STORY-004-chat-message-model.md`
- PRD: `.agents/PRDs/PRD-004-chat-ui-redesign/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | technical |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/chat_ui/models.py`, `chat_ui/chat_ui/state.py`, `chat_ui/chat_ui/components/chat.py` |
| Story | STORY-004 |
| PRD | PRD-004 |
| Epic Branch | `epic/PRD-004-chat-ui-redesign` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| reflex-docs | Reflex Base model and Var-access rules | Task 1, Task 2, Task 3 |

---

## Patterns to Follow

### Naming
```python
// SOURCE: chat_ui/chat_ui/state.py:28
messages: list[dict[str, str]] = [WELCOME_MESSAGE]
```

### Error Handling
```python
// SOURCE: chat_ui/chat_ui/state.py:75-82
except (DuplicateCheckError, OpenRouterError, PiiRedactorError) as exc:
    async with self:
        self.messages.append({"role": "system", "content": f"Error: {exc}"})
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
| `chat_ui/chat_ui/models.py` | CREATE | Define `ChatMessage(rx.Base)` model with discriminator and metadata fields |
| `chat_ui/chat_ui/state.py` | UPDATE | Update `messages: list[ChatMessage]` and construct `ChatMessage` instances in `send()` |
| `chat_ui/chat_ui/components/chat.py` | UPDATE | Access `ChatMessage` attributes (`message.kind`, `message.content`) instead of dict keys |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create `chat_ui/chat_ui/models.py`

- **File**: `chat_ui/chat_ui/models.py`
- **Action**: CREATE
- **Implement**: Define `ChatMessage(rx.Base)` with fields: `kind`, `content`, `prompt`, `model_used`, `tokens_used`, `audit_id`, `pii_redacted`, `pii_entities`, `pattern`, `first_query_at`, `detail`.
- **Mirror**: PRD Section 6 specification.
- **Validate**: Python syntax check and import.

### Task 2: Update `chat_ui/chat_ui/state.py` to use `ChatMessage`

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: Change `messages: list[ChatMessage]`, update welcome message, and construct `ChatMessage` in `send()`.
- **Mirror**: `chat_ui/chat_ui/state.py:28`
- **Validate**: `pytest tests/test_chat_state.py`

### Task 3: Update `chat_ui/chat_ui/components/chat.py` to access attributes

- **File**: `chat_ui/chat_ui/components/chat.py`
- **Action**: UPDATE
- **Implement**: Replace dictionary lookups (`message["role"]`, `message["content"]`) with attribute access (`message.kind`, `message.content`).
- **Mirror**: `chat_ui/chat_ui/components/chat.py:6-51`
- **Validate**: Reflex app compile / test suite execution.

---

## End-to-End Tests

- [ ] `pytest tests/test_chat_state.py` passes successfully
- [ ] No file under `app/` is modified

---

## Validation

```bash
pytest tests/test_chat_state.py
```

---

## Acceptance Criteria

- [ ] Given `chat_ui/chat_ui/models.py`, when it is created, then it defines `ChatMessage(rx.Base)` with exactly the fields listed in PRD Section 6.
- [ ] Given `ChatState.messages`, when inspected, then it is `list[ChatMessage]` and no longer `list[dict[str, str]]`.
- [ ] Given `components/chat.py`, when it renders, then it reads `ChatMessage` attributes instead of dict keys.
- [ ] Given `app/`, when the diff is inspected, then no file under it is modified.
- [ ] All tasks completed.
