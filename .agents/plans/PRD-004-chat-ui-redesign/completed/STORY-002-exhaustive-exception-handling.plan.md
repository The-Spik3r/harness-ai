---
story: STORY-002
prd: PRD-004
slug: exhaustive-exception-handling
title: "Exhaustive except arms in send(): PiiRedactorError + catch-all"
type: bug
complexity: small
epic_branch: epic/PRD-004-chat-ui-redesign
created: 2026-08-21
---

# Plan: Exhaustive except arms in send(): PiiRedactorError + catch-all

## Summary

Extend `ChatState.send()` error handling to catch `PiiRedactorError` and include a catch-all `except Exception` arm, ensuring every exception path terminates in a visible system error bubble and no message is silently dropped.

## User Story

As an end user, I want a message that fails inside the harness to still produce a visible bubble, so that my message is never silently swallowed (PRD User Story 1, Section 2 "No silent drops").

## Story Reference

- Story file: `.agents/stories/PRD-004-chat-ui-redesign/STORY-002-exhaustive-exception-handling.md`
- PRD: `.agents/PRDs/PRD-004/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | bug |
| Complexity | small |
| Systems Affected | chat_ui/chat_ui/state.py, tests/test_chat_state.py |
| Story | STORY-002 |
| PRD | PRD-004 |
| Epic Branch | `epic/PRD-004-chat-ui-redesign` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| reflex-docs | Reference for Reflex state event handling and async background events | Task 1, Task 2 |
| reflex-process-management | Reference for running tests and verifying Reflex state | Task 3 |

---

## Patterns to Follow

### Naming
```python
// SOURCE: chat_ui/chat_ui/state.py:15-16
class ChatState(rx.State):
```

### Error Handling
```python
// SOURCE: chat_ui/chat_ui/state.py:69-72
        except (DuplicateCheckError, OpenRouterError) as exc:
            async with self:
                self.messages.append({"role": "system", "content": f"Error: {exc}"})
            return
```

### Tests
```python
// SOURCE: tests/test_chat_state.py:187-198
@pytest.mark.asyncio
async def test_chat_state_send_duplicate_blocked_appends_system_bubble(temp_db, monkeypatch):
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/state.py` | UPDATE | Import `PiiRedactorError`, add `PiiRedactorError` and catch-all `except Exception` arms to `send()` |
| `tests/test_chat_state.py` | UPDATE | Add regression tests for `PiiRedactorError` and unexpected `Exception` in `ChatState.send()` |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Update `chat_ui/chat_ui/state.py` with exhaustive exception handling

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: Import `PiiRedactorError` from `app.services.pii_redactor`. Update `ChatState.send()` try/except block to catch `(DuplicateCheckError, OpenRouterError, PiiRedactorError)` and add `except Exception as exc:` catch-all arm appending `{"role": "system", "content": f"Error: {exc}"}`.
- **Mirror**: `chat_ui/chat_ui/state.py:5-7` and `69-72` — follow this pattern
- **Validate**: `pytest tests/test_chat_state.py`

### Task 2: Add unit tests in `tests/test_chat_state.py`

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE
- **Implement**: Add `test_chat_state_send_pii_redactor_error_appends_system_bubble` and `test_chat_state_send_unexpected_exception_appends_system_bubble`.
- **Mirror**: `tests/test_chat_state.py:187-210`
- **Validate**: `pytest tests/test_chat_state.py`

### Task 3: Run full verification suite

- **File**: Test suite
- **Action**: VERIFY
- **Implement**: Run `pytest` across all tests to ensure no regressions.
- **Validate**: `pytest` passes successfully without errors.

---

## End-to-End Tests

- [ ] Run `pytest` and verify all tests pass, including new exception handling tests.
- [ ] Verify no files under `app/` are modified.

---

## Validation

```bash
pytest tests/test_chat_state.py
pytest
```

---

## Acceptance Criteria

(Copied from story `STORY-002`)

- [ ] Given `run_query(...)` raises `PiiRedactorError`, when `send()` handles it, then a bubble carrying the exception text is appended instead of nothing being appended at all.
- [ ] Given `run_query(...)` raises an arbitrary unexpected exception, when `send()` handles it, then a bubble is still appended — a catch-all `except Exception` arm guarantees no path ends without a bubble.
- [ ] Given `DuplicateCheckError` or `OpenRouterError`, when either is raised, then a bubble is still appended as today — no regression on the two arms that already exist.
- [ ] Given a test forcing each of the four exception paths, when it asserts on `state.messages`, then the message count grew by exactly one bubble in every case.
- [ ] Given `app/`, when the diff is inspected, then no file under it is modified.
- [ ] All tasks completed.
- [ ] Follows existing patterns.
