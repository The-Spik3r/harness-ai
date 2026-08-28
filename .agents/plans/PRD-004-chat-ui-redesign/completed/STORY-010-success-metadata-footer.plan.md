---
story: STORY-010
prd: PRD-004
slug: success-metadata-footer
title: "Assistant bubble footer with model_used, tokens_used and audit_id"
type: NEW_CAPABILITY
complexity: SMALL
epic_branch: epic/PRD-004-chat-ui-redesign
created: 2026-08-21
---

# Plan: Assistant bubble footer with model_used, tokens_used and audit_id

## Summary

Add a subdued metadata footer to assistant message bubbles showing `model_used`, `tokens_used`, and `audit_id` (e.g., `gpt-4 · 45 tokens · #127`), utilizing centralized copy tokens from `chat_ui/copy.py`.

## User Story

As an end user, I want to see which model answered and what it cost, so that my usage is not invisible — and so that a support request can quote an audit row ID instead of a paraphrase (PRD User Story 6, Section 3 Security/Compliance Admin).

## Story Reference

- Story file: `.agents/stories/PRD-004-chat-ui-redesign/STORY-010-success-metadata-footer.md`
- PRD: `.agents/PRDs/PRD-004/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | SMALL |
| Systems Affected | `chat_ui/chat_ui/components/bubbles.py`, `chat_ui/chat_ui/copy.py` |
| Story | STORY-010 |
| PRD | PRD-004 |
| Epic Branch | `epic/PRD-004-chat-ui-redesign` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| reflex-docs | Reflex component rendering, Var operations, `rx.cond`, `rx.text`, `rx.vstack` | Task 1 |

---

## Patterns to Follow

### Assistant Bubble Rendering & Copy
```python
# SOURCE: chat_ui/chat_ui/components/bubbles.py:22-61
def render_assistant(message) -> rx.Component:
    ...
```
```python
# SOURCE: chat_ui/chat_ui/copy.py:26-29
FOOTER_SEPARATOR = " · "
FOOTER_TOKENS_LABEL = "tokens"
FOOTER_AUDIT_PREFIX = "#"
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/components/bubbles.py` | UPDATE | Render metadata footer inside `render_assistant` displaying `model_used`, `tokens_used`, and `audit_id`. |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Update `render_assistant` in `bubbles.py` with Success Metadata Footer

- **File**: `chat_ui/chat_ui/components/bubbles.py`
- **Action**: UPDATE
- **Implement**:
  - Construct `footer_text` using `rx.text` with `message.model_used`, `copy.FOOTER_SEPARATOR`, `message.tokens_used`, `" "`, `copy.FOOTER_TOKENS_LABEL`, `copy.FOOTER_SEPARATOR`, `copy.FOOTER_AUDIT_PREFIX`, `message.audit_id`.
  - Apply subdued styling (`font_size="0.75rem"`, `color="#6b7280"`, `margin_top="0.5rem"`).
  - Wrap `footer_text` in an `rx.cond` checking `message.model_used != ""`.
  - Add `footer` to `rx.vstack` inside assistant message `rx.box` below `pii_badge`.
- **Mirror**: Existing `pii_badge` in `render_assistant`.
- **Validate**: Python syntax check and pytest.

---

## End-to-End Tests

- [ ] Given a successful exchange, when the assistant bubble renders, then a subdued footer shows `model_used`, `tokens_used` and `audit_id` (e.g. `gpt-4 · 45 tokens · #127`).
- [ ] Given the footer, when rendered, then it is visually subdued relative to response text (`font_size="0.75rem"`, muted color).
- [ ] Given a non-assistant message kind, when rendered, then no metadata footer appears.
- [ ] Coexists cleanly with PII badge from STORY-009 on the same bubble.

---

## Validation

```bash
python -c "import chat_ui.chat_ui.components.bubbles as b"
pytest tests/
```

---

## Acceptance Criteria

- [ ] Given a successful exchange, when the assistant bubble renders, then a subdued footer shows `model_used`, `tokens_used` and `audit_id`.
- [ ] Given the footer, when rendered, then it is visually subdued relative to the response text and does not compete with it for attention.
- [ ] Given a non-assistant message kind, when rendered, then no metadata footer appears.
- [ ] Given `audit_id`, when displayed, then it matches the `audit_id` of the row `run_query(...)` wrote.
- [ ] Follows existing patterns.
