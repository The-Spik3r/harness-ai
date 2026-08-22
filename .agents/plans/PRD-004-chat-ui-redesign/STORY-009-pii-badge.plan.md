---
story: STORY-009
prd: PRD-004
slug: pii-badge
title: "Informational PII badge on assistant bubbles"
type: NEW_CAPABILITY
complexity: SMALL
epic_branch: epic/PRD-004-chat-ui-redesign
created: 2026-08-21
---

# Plan: Informational PII badge on assistant bubbles

## Summary

Add an informational, quiet inline PII badge to assistant message bubbles when `pii_redacted` is true, listing the masked entity types from `pii_entities` using the centralized copy templates from `chat_ui/copy.py`.

## User Story

As an end user, I want to know when the harness masked personal data in my exchange, so that I understand why a response might read `<PERSON>` instead of a name (PRD User Story 3, Section 2 "Inform, don't obstruct").

## Story Reference

- Story file: `.agents/stories/PRD-004-chat-ui-redesign/STORY-009-pii-badge.md`
- PRD: `.agents/PRDs/PRD-004/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | SMALL |
| Systems Affected | `chat_ui/chat_ui/components/bubbles.py`, `chat_ui/chat_ui/copy.py` |
| Story | STORY-009 |
| PRD | PRD-004 |
| Epic Branch | `epic/PRD-004-chat-ui-redesign` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| reflex-docs | Reflex component rendering, Var operations (`.length()`, `.join()`, `rx.cond`) | Task 1 |

---

## Patterns to Follow

### Naming & Rendering
```python
// SOURCE: chat_ui/chat_ui/components/bubbles.py:22-36
def render_assistant(message) -> rx.Component:
    """Renders successful assistant message bubble (left-aligned, gray)."""
    return rx.hstack(
        rx.avatar(fallback="AI", size="2", color_scheme="gray"),
        rx.box(
            message.content,
            background_color="#f3f4f6",
            color="#111827",
            padding="0.65rem 1rem",
            border_radius="1rem",
            max_width="70%",
        ),
        justify="start",
        width="100%",
    )
```

### Copy Templates
```python
// SOURCE: chat_ui/chat_ui/copy.py:22-24
PII_BADGE_TEMPLATE = "{count} PII types masked in this exchange: {entities}"
PII_BADGE_SINGLE_TEMPLATE = "1 PII type masked in this exchange: {entities}"
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/components/bubbles.py` | UPDATE | Render PII badge inside `render_assistant` when `message.pii_redacted` is true |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Update `render_assistant` in `bubbles.py` with PII badge

- **File**: `chat_ui/chat_ui/components/bubbles.py`
- **Action**: UPDATE
- **Implement**: 
  - Compute `count = message.pii_entities.length()` and `entities_str = message.pii_entities.join(", ")`.
  - Construct `badge_text` using `rx.cond` on `count == 1` with `copy.PII_BADGE_SINGLE_TEMPLATE.format(entities=entities_str)` and `copy.PII_BADGE_TEMPLATE.format(count=count, entities=entities_str)`.
  - Construct `pii_badge` using `rx.cond` on `message.pii_redacted`, rendering a quiet inline box/badge with small font size, muted colors, and padding.
  - Wrap assistant message content and `pii_badge` in an `rx.vstack` inside the assistant `rx.box`.
- **Mirror**: Existing error/duplicate renderers in `chat_ui/chat_ui/components/bubbles.py:39-143`.
- **Validate**: Python syntax check and pytest.

---

## End-to-End Tests

- [ ] Given an assistant message whose `pii_redacted` is `true`, when rendered, then a badge appears listing the entity types from `pii_entities`.
- [ ] Given an assistant message whose `pii_redacted` is `false`, when rendered, then no badge appears.
- [ ] Badge uses exact copy templates from `copy.py` ("masked in this exchange").
- [ ] Badge displays entity types only, never raw values or matched text.

---

## Validation

```bash
python -c "import chat_ui.chat_ui.components.bubbles as b"
pytest tests/test_chat_state.py
```

---

## Acceptance Criteria

- [ ] Given an assistant message whose `pii_redacted` is `true`, when rendered, then a badge appears listing the entity types from `pii_entities`.
- [ ] Given an assistant message whose `pii_redacted` is `false`, when rendered, then no badge appears at all.
- [ ] Given the badge, when rendered, then it is quiet and inline — never a modal, never a confirmation step, never a gate.
- [ ] Given the badge copy, when read, then it describes masking as covering the exchange.
- [ ] Given the badge, when rendered, then it shows entity types only.
- [ ] Follows existing patterns.
