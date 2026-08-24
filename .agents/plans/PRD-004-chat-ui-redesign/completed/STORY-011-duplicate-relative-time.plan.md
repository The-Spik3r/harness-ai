---
story: STORY-011
prd: PRD-004
slug: duplicate-relative-time
title: "Duplicate card: humanized relative time and 24h window release"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-004-chat-ui-redesign
created: 2026-08-24
---

# Plan: Duplicate card — humanized relative time and 24h window release

## Summary

Enhance the duplicate block rendering (`render_duplicate` in `chat_ui/chat_ui/components/bubbles.py`) and copy module (`chat_ui/chat_ui/copy.py`) to display a humanized relative time and absolute timestamp for `first_query_at`, calculate and display the 24-hour window release time, incorporate the Risk 4 change notice, and ensure robust fallback handling for empty or unparseable timestamps without crashing.

## User Story

As an end user, I want a duplicate block to tell me when I first sent the message and when the block lifts, so that "you already asked this" is actionable rather than a bare rejection (PRD User Story 2, Section 4).

## Story Reference

- Story file: `.agents/stories/PRD-004-chat-ui-redesign/STORY-011-duplicate-relative-time.md`
- PRD: `.agents/PRDs/PRD-004-chat-ui-redesign/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | `chat_ui/chat_ui/components/bubbles.py`, `chat_ui/chat_ui/copy.py`, tests |
| Story | STORY-011 |
| PRD | PRD-004 |
| Epic Branch | `epic/PRD-004-chat-ui-redesign` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| reflex-docs | Reflex component styling, conditional rendering (`rx.cond`), and server-side python execution in renderers | Task 1, Task 2 |

---

## Patterns to Follow

### Naming
```python
# SOURCE: chat_ui/chat_ui/components/bubbles.py:86-109
def render_duplicate(message) -> rx.Component:
    """Renders duplicate block card with benign-nudge styling."""
```

### Error Handling
```python
# SOURCE: PRD Section 4 & Technical Notes ("No silent drops")
# Graceful fallback on unparseable/empty first_query_at without raising exceptions or swallowing the bubble.
```

### Tests
```python
# SOURCE: tests/test_copy.py:37-41
def test_risk_4_duplicate_change_notice():
    assert DUPLICATE_CHANGE_NOTICE
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/copy.py` | UPDATE | Add duplicate relative time and window release copy templates and constants. |
| `chat_ui/chat_ui/components/bubbles.py` | UPDATE | Update `render_duplicate` to parse `first_query_at`, compute humanized relative time and 24h window release, and display change notice (Risk 4). |
| `tests/test_copy.py` (or new test) | UPDATE | Add unit tests for duplicate time formatting and fallback behavior. |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add duplicate copy templates to `chat_ui/chat_ui/copy.py`
- **File**: `chat_ui/chat_ui/copy.py`
- **Action**: UPDATE
- **Implement**: Add `DUPLICATE_RELATIVE_TIME_TEMPLATE`, `DUPLICATE_WINDOW_RELEASE_TEMPLATE`, and ensure `DUPLICATE_CHANGE_NOTICE` is available.
- **Mirror**: Existing copy constants in `chat_ui/chat_ui/copy.py`.
- **Validate**: `pytest tests/test_copy.py` passes successfully.

### Task 2: Implement humanized relative time, absolute timestamp, 24h window release, and fallback in `render_duplicate`
- **File**: `chat_ui/chat_ui/components/bubbles.py`
- **Action**: UPDATE
- **Implement**: Write helper logic or inline parsing in `render_duplicate` to parse ISO timestamps from `message.first_query_at`, compute relative time (e.g. "X hours ago", "just now"), compute `first_query_at + 24 hours`, format absolute timestamp, include `DUPLICATE_CHANGE_NOTICE`, and wrap in try/except fallback for unparseable strings ("No silent drops").
- **Mirror**: Existing error/duplicate renderers in `chat_ui/chat_ui/components/bubbles.py`.
- **Validate**: Python unit test / pytest runs successfully.

### Task 3: Add unit tests for duplicate time formatting and edge cases
- **File**: `tests/test_copy.py` or `tests/test_chat_state.py`
- **Action**: UPDATE
- **Implement**: Test valid ISO string parsing, relative time calculation, 24h window release calculation, and invalid/empty `first_query_at` fallback without raising exceptions.
- **Mirror**: Existing test patterns in `tests/test_copy.py`.
- **Validate**: `pytest` passes all tests.

---

## End-to-End Tests

- [ ] Seed a duplicate in DB / test state and render duplicate card → shows humanized relative time, absolute timestamp, 24h window release, and change notice.
- [ ] Render duplicate card with empty or malformed `first_query_at` → renders raw value / fallback without crash ("No silent drops").
- [ ] Run full pytest suite → all tests pass.

---

## Validation

```bash
pytest tests/test_copy.py tests/test_chat_state.py
```

---

## Acceptance Criteria

- [ ] Given a `duplicate` message with `first_query_at`, when rendered, then the card shows a humanized relative time plus the absolute timestamp — e.g. "Already sent 2 hours ago (2026-08-21T10:30:00Z)".
- [ ] Given the same message, when rendered, then the card states when the 24-hour window releases, derived as `first_query_at` + 24 hours.
- [ ] Given a `first_query_at` that is empty or unparseable, when rendered, then the card still renders with the raw value and no crash — an error in time formatting must not swallow the bubble ("No silent drops").
- [ ] Given the duplicate card copy, when read, then it states that the text must change for a resend to go through (Risk 4).
- [ ] All tasks completed
- [ ] Follows existing patterns
