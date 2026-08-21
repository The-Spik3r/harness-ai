---
story: STORY-003
prd: PRD-004
slug: pending-state-flag
title: "pending state var with finally-reset and single in-flight send guard"
type: technical
complexity: small
epic_branch: epic/PRD-004-chat-ui-redesign
created: 2026-08-21
---

# Plan: pending state var with finally-reset and single in-flight send guard

## Summary

Add a `pending: bool` state variable to `ChatState`, wrap the request execution in a `try...finally` block that guarantees `pending` is reset to `False` across all outcomes (including success, duplicate-blocked, suspicious-blocked, `OpenRouterError`, `PiiRedactorError`, and catch-all `Exception`), and guard `send()` against concurrent in-flight requests by returning early if `pending` is already `True`.

## User Story

As an end user, I want the harness to track that my request is in flight, so that the UI can show progress and refuse to queue a second concurrent send from the same session (PRD Section 4, Section 12 Phase 1).

## Story Reference

- Story file: `.agents/stories/PRD-004-chat-ui-redesign/STORY-003-pending-state-flag.md`
- PRD: `.agents/PRDs/PRD-004-chat-ui-redesign/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | technical |
| Complexity | small |
| Systems Affected | `chat_ui/chat_ui/state.py`, `tests/test_chat_state.py` |
| Story | STORY-003 |
| PRD | PRD-004 |
| Epic Branch | `epic/PRD-004-chat-ui-redesign` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| reflex-docs | State management, background events in Reflex | Task 1 |
| reflex-process-management | Running pytest verification correctly | Task 2 |

---

## Patterns to Follow

### Naming
```python
// SOURCE: chat_ui/chat_ui/state.py:28-32
    messages: list[dict[str, str]] = [WELCOME_MESSAGE]
    input_text: str = ""
    user_id: str = ""
    user_id_input: str = ""
```

### Error Handling
```python
// SOURCE: chat_ui/chat_ui/state.py:60-77
        try:
            result = await asyncio.to_thread(
                run_query,
                ...
            )
        except (...) as exc:
            ...
```

### Tests
```python
// SOURCE: tests/test_chat_state.py:172-185
@pytest.mark.asyncio
async def test_chat_state_send_success_appends_user_then_assistant_bubble(temp_db, monkeypatch):
    ...
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/state.py` | UPDATE | Add `pending: bool = False`, in-flight guard (`if self.pending: return`), and `try...finally` block to ensure `pending = False` on all exit paths. |
| `tests/test_chat_state.py` | UPDATE | Add unit tests verifying `pending` lifecycle across all 6 outcomes and concurrent send rejection. |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add pending state variable, in-flight guard, and finally-reset block in ChatState.send()

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: 
  1. Add `pending: bool = False` to `ChatState`.
  2. Inside `send()`, within the initial `async with self` check block (or immediately checking-and-setting): check `if self.pending: return`, then set `self.pending = True`.
  3. Wrap the execution (and exception handling / result handling) or set `self.pending = False` in a `finally` block inside an `async with self` block.
  4. Specifically:
     ```python
     @rx.event(background=True)
     async def send(self):
         async with self:
             if not self.user_id.strip():
                 return
             text = self.input_text.strip()
             if not text:
                 return
             if self.pending:
                 return
             self.pending = True
             self.messages.append({"role": "user", "content": text})
             self.input_text = ""
             user_id = self.user_id

         try:
             result = await asyncio.to_thread(
                 run_query,
                 user_id=user_id,
                 prompt=text,
                 device=None,
                 model="gpt-4",
                 openrouter_api_key=None,
                 call_openrouter=call_openrouter,
             )
         except (DuplicateCheckError, OpenRouterError, PiiRedactorError) as exc:
             async with self:
                 self.messages.append({"role": "system", "content": f"Error: {exc}"})
             return
         except Exception as exc:
             async with self:
                 self.messages.append({"role": "system", "content": f"Error: {exc}"})
             return
         finally:
             async with self:
                 self.pending = False

         if isinstance(result, QuerySuccessResponse):
             bubble = {"role": "assistant", "content": result.response}
         elif isinstance(result, QueryBlockedDuplicateResponse):
             bubble = {
                 "role": "system",
                 "content": f"Blocked — {result.reason} (first sent at {result.first_query_at})",
             }
         else:
             bubble = {"role": "system", "content": f"Blocked — {result.reason}"}

         async with self:
             self.messages.append(bubble)
     ```
  - **Mirror**: `chat_ui/chat_ui/state.py:48-90`
  - **Validate**: `pytest tests/test_chat_state.py`

### Task 2: Add unit tests for pending state transitions and concurrent send guard

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE
- **Implement**: Add tests verifying:
  1. Concurrent send when `pending is True` does not call `run_query` and does not append a second user bubble.
  2. `pending` is `False` after success, duplicate block, suspicious block, `PiiRedactorError`, `OpenRouterError`, and unexpected exception (`Exception`).
- **Mirror**: `tests/test_chat_state.py:172-245`
- **Validate**: `pytest tests/test_chat_state.py`

---

## End-to-End Tests

- [ ] Run `pytest tests/test_chat_state.py` → all tests pass including new pending assertions
- [ ] Run full test suite `pytest` → all tests pass successfully

---

## Validation

```bash
pytest tests/test_chat_state.py
pytest
```

---

## Acceptance Criteria

(Copied from story `STORY-003`)

- [ ] Given `ChatState`, when a send starts, then a `pending: bool` state var flips to `True` inside an `async with self` block and flips back to `False` before `send()` returns.
- [ ] Given any of the six outcomes — three result types plus `OpenRouterError`, `PiiRedactorError`, `DuplicateCheckError` and an arbitrary exception — when `send()` completes, then `pending is False`, because the reset lives in a `finally` block.
- [ ] Given `pending is True`, when `send()` is invoked again from the same session, then the second invocation returns immediately without calling `run_query(...)` and without appending a user bubble.
- [ ] Given a test per outcome, when it asserts after `send()`, then `pending is False` in every case, including the catch-all arm.
- [ ] All tasks completed
- [ ] Frontend lint passes / pytest passes
- [ ] Follows existing patterns
