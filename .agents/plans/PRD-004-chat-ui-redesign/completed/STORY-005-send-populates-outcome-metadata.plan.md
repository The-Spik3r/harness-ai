---
story: STORY-005
prd: PRD-004
slug: send-populates-outcome-metadata
title: "send() populates every metadata field from each pipeline outcome"
type: feature
complexity: medium
epic_branch: epic/PRD-004-chat-ui-redesign
created: 2026-08-21
---

# Plan: send() populates every metadata field from each pipeline outcome

## Summary

Update `ChatState.send()` in `chat_ui/chat_ui/state.py` to populate every metadata field from each pipeline outcome (`QuerySuccessResponse`, `QueryBlockedDuplicateResponse`, `QueryBlockedSuspiciousResponse`, and all four exception paths), consuming all 6 response fields instead of 1, preserving raw timestamps and reasons, capturing prompt text, and separating error display copy from exception detail text.

## User Story

As an integrating developer, I want `send()` to carry every field the pipeline already returns onto the appended `ChatMessage`, so that the UI stops discarding five of the six response fields (PRD Section 10 contract table, Section 12 Phase 2).

## Story Reference

- Story file: `.agents/stories/PRD-004-chat-ui-redesign/STORY-005-send-populates-outcome-metadata.md`
- PRD: `.agents/PRDs/PRD-004-chat-ui-redesign/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | feature |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/chat_ui/state.py` |
| Story | STORY-005 |
| PRD | PRD-004 |
| Epic Branch | `epic/PRD-004-chat-ui-redesign` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| reflex-docs | Reflex State event handling and model instantiation rules | Task 1 |

---

## Patterns to Follow

### Naming
```python
# SOURCE: chat_ui/chat_ui/state.py:110-134
if isinstance(result, QuerySuccessResponse):
    bubble = ChatMessage(
        kind="assistant",
        content=result.response,
        prompt=text,
        model_used=result.model_used,
        tokens_used=result.tokens_used,
        audit_id=result.audit_id,
        pii_redacted=result.pii_redacted,
        pii_entities=result.pii_entities_masked,
    )
```

### Error Handling
```python
# SOURCE: chat_ui/chat_ui/state.py:76-108
except OpenRouterError as exc:
    async with self:
        self.messages.append(
            ChatMessage(
                kind="upstream_error",
                content="upstream_error",
                prompt=text,
                detail=str(exc),
            )
        )
    return
```

### Tests
```python
# SOURCE: chat_ui/chat_ui/state.py:61
self.messages.append(ChatMessage(kind="user", content=text, prompt=text))
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/state.py` | UPDATE | Populate all metadata fields for success, duplicate, injection, and error outcomes in `send()` |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Update `ChatState.send()` in `chat_ui/chat_ui/state.py`

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: 
  - `QuerySuccessResponse`: populate `response`, `model_used`, `tokens_used`, `audit_id`, `pii_redacted`, `pii_entities_masked` -> `pii_entities`, `prompt`.
  - `QueryBlockedDuplicateResponse`: `kind="duplicate"`, `content=result.reason` (unformatted), `first_query_at=result.first_query_at`, `prompt=text`.
  - `QueryBlockedSuspiciousResponse` (else): `kind="injection"`, `content=result.reason` (unformatted), `pattern=result.pattern`, `prompt=text`.
  - Exception arms (`OpenRouterError`, `DuplicateCheckError`, `PiiRedactorError`, catch-all `Exception`): `content` = copy key/label (`"upstream_error"` or `"internal_error"`), `detail=str(exc)`, `prompt=text`.
- **Mirror**: `chat_ui/chat_ui/state.py:51-137`
- **Validate**: `pytest`

---

## End-to-End Tests

- [ ] All test assertions in `tests/test_chat_state.py` run and pass successfully (or are adapted/migrated per downstream test stories).
- [ ] No changes to backend code under `app/`.

---

## Validation

```bash
pytest tests/test_chat_state.py
```

---

## Acceptance Criteria

- [ ] Given a `QuerySuccessResponse`, when the assistant message is appended, then `content == result.response`, `model_used`, `tokens_used`, `audit_id`, `pii_redacted` and `pii_entities` (from `pii_entities_masked`) all land on the message — 6 of 6 response fields consumed, versus 1 of 6 today.
- [ ] Given a `QueryBlockedDuplicateResponse`, when the duplicate message is appended, then `kind == "duplicate"`, `content == result.reason` (unformatted) and `first_query_at == result.first_query_at` as the raw timestamp string, not inlined into prose.
- [ ] Given a `QueryBlockedSuspiciousResponse`, when the injection message is appended, then `kind == "injection"`, `content == result.reason` and `pattern == result.pattern`.
- [ ] Given any of the four exception paths, when the error message is appended, then `detail` carries the exception text and `content` carries the copy key/label rather than a pre-formatted `f"Error: {exc}"` string.
- [ ] Given every appended non-user message, when inspected, then `prompt` holds the original prompt text.
- [ ] All tasks completed.
