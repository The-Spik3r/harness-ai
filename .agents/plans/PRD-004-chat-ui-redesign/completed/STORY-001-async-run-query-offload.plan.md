---
story: STORY-001
prd: PRD-004
slug: async-run-query-offload
title: "Offload run_query(...) to a worker thread via asyncio.to_thread"
type: bug
complexity: MEDIUM
epic_branch: epic/PRD-004-chat-ui-redesign        # all stories commit here, no per-story branch
created: 2026-08-21
---

# Plan: Offload run_query(...) to a worker thread via asyncio.to_thread

## Summary

As an end user, I want the harness to stay responsive while my message is being processed, so that a slow OpenRouter call does not freeze the whole page for every session. This plan offloads the synchronous `run_query(...)` call inside `ChatState.send()` to a worker thread via `asyncio.to_thread(...)`, keeping the Reflex event loop unblocked while preserving the exact existing behavior, exception handling, and user-facing output.

## User Story

As an end user
I want the harness to stay responsive while my message is being processed
So that a slow OpenRouter call does not freeze the whole page for every session

## Story Reference

- Story file: `.agents/stories/PRD-004-chat-ui-redesign/STORY-001-async-run-query-offload.md`
- PRD: `.agents/PRDs/PRD-004-chat-ui-redesign/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | bug |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/chat_ui/state.py` |
| Story | STORY-001 |
| PRD | PRD-004 |
| Epic Branch | `epic/PRD-004-chat-ui-redesign` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| reflex-docs | Reference for Reflex state management and asynchronous event background handlers | Task 1 |
| reflex-process-management | Guide for running and validating Reflex app compilation and test execution | Task 2 |

---

## Patterns to Follow

### Naming
```python
// SOURCE: chat_ui/chat_ui/state.py:46-56
    @rx.event(background=True)
    async def send(self):
        async with self:
            if not self.user_id.strip():
                return
            text = self.input_text.strip()
            if not text:
                return
            self.messages.append({"role": "user", "content": text})
            self.input_text = ""
            user_id = self.user_id
```

### Error Handling
```python
// SOURCE: chat_ui/chat_ui/state.py:58-70
        try:
            result = run_query(
                user_id=user_id,
                prompt=text,
                device=None,
                model="gpt-4",
                openrouter_api_key=None,
                call_openrouter=call_openrouter,
            )
        except (DuplicateCheckError, OpenRouterError) as exc:
            async with self:
                self.messages.append({"role": "system", "content": f"Error: {exc}"})
            return
```

### Tests
```python
// SOURCE: tests/test_chat_state.py:171-184
@pytest.mark.asyncio
async def test_chat_state_send_success_appends_user_then_assistant_bubble(temp_db, monkeypatch):
    def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
        return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)

    monkeypatch.setattr(chat_state_mod, "call_openrouter", _fake_call_openrouter)

    state = _make_state()
    await _send(state, "hello world")

    assert state.messages[-2] == {"role": "user", "content": "hello world"}
    assert state.messages[-1] == {"role": "assistant", "content": "Hi there!"}
    assert state.input_text == ""
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/state.py` | UPDATE | Import `asyncio` and wrap `run_query` inside `await asyncio.to_thread(...)` |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Update `ChatState.send()` to use `asyncio.to_thread`

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: Import `asyncio`, and change the synchronous `run_query(...)` invocation to `await asyncio.to_thread(run_query, user_id=user_id, prompt=text, device=None, model="gpt-4", openrouter_api_key=None, call_openrouter=call_openrouter)`
- **Mirror**: `chat_ui/chat_ui/state.py:1-7` and `58-66` — follow existing import and call pattern
- **Validate**: `pytest tests/test_chat_state.py` passes successfully

### Task 2: Verify Test Suite Integrity

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE / VERIFY
- **Implement**: Run full chat state test suite to confirm asynchronous execution breaks nothing and existing test cases pass unmodified
- **Mirror**: Existing test execution routines in `tests/`
- **Validate**: `pytest tests/test_chat_state.py`

---

## End-to-End Tests

- [ ] Run `pytest tests/test_chat_state.py` → all tests pass successfully.
- [ ] Run broader test suite `pytest` → passes without regression.

---

## Validation

```bash
pytest tests/test_chat_state.py
pytest
```

---

## Acceptance Criteria

(Copied from story `STORY-001`)

- [ ] Given `ChatState.send()`, when it calls the pipeline, then it does so as `await asyncio.to_thread(run_query, ...)` instead of the blocking direct call at [state.py:59](../../../chat_ui/chat_ui/state.py) — the arguments passed (`user_id`, `prompt`, `device`, `model`, `openrouter_api_key`, `call_openrouter`) are unchanged in this story.
- [ ] Given a `run_query(...)` that blocks for several seconds, when one session has a request in flight, then a second browser session can still navigate and interact — the Reflex event loop is not blocked (PRD Section 11: "Event-loop blocking during a request — 0 ms").
- [ ] Given the three result types and the two currently-caught exceptions, when they are produced by the threaded call, then the appended bubbles are identical to today's — this story has no visible change (PRD Section 12 Phase 1: "no visual change yet").
- [ ] Given all state mutation in `send()`, when it happens, then it remains inside `async with self` blocks, per Reflex's background-event contract (PRD Section 6, Risk 3).
- [ ] Given `tests/test_chat_state.py`, when the suite runs, then it passes unmodified.
