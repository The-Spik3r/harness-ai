---
story: STORY-017
prd: PRD-004
slug: device-user-agent-capture
title: Populate device from the browser User-Agent on chat sends
type: FEATURE
complexity: SMALL
epic_branch: epic/PRD-004-chat-ui-redesign
created: 2026-08-25
---

# Plan: Populate device from the browser User-Agent on chat sends

## Summary

Capture the browser User-Agent from Reflex request headers (`self.router.headers.raw_headers`) during chat message submission in `ChatState.send()`, passing it as the `device` parameter to `run_query(...)` instead of hardcoded `None`, ensuring chat-originated audit rows record the device while gracefully falling back to `None` when unavailable.

## User Story

As a security admin, I want chat-originated audit rows to record the device, so that `audit_logs.device` is not null for every chat row while API rows can populate it (PRD User Story 7).

## Story Reference

- Story file: `.agents/stories/PRD-004-chat-ui-redesign/STORY-017-device-user-agent-capture.md`
- PRD: `.agents/PRDs/PRD-004-chat-ui-redesign/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | FEATURE |
| Complexity | SMALL |
| Systems Affected | `chat_ui/chat_ui/state.py`, `tests/test_chat_state.py` |
| Story | STORY-017 |
| PRD | PRD-004 |
| Epic Branch | `epic/PRD-004-chat-ui-redesign` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| reflex-docs | Accessing `self.router.headers.raw_headers` safely in Reflex state events | Task 1 |

---

## Patterns to Follow

### Naming & State Access
```python
// SOURCE: chat_ui/chat_ui/state.py:64-90
    @rx.event(background=True)
    async def send(self):
        async with self:
            ...
```

### Error Handling / Safe Fallback
```python
// SOURCE: chat_ui/chat_ui/state.py:80-90
        device = None
        try:
            if self.router and self.router.headers and self.router.headers.raw_headers:
                device = self.router.headers.raw_headers.get("user-agent")
        except Exception:
            device = None
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/state.py` | UPDATE | Extract browser User-Agent from `self.router.headers.raw_headers` and pass to `run_query(...)` |
| `tests/test_chat_state.py` | UPDATE | Add tests verifying User-Agent capture and fallback to `None` when unavailable |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Extract User-Agent in `ChatState.send()` and pass to `run_query(...)`

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: 
  - Before calling `run_query` (or inside the event handler before/during `send`), attempt to retrieve `self.router.headers.raw_headers.get("user-agent")` inside a `try...except` block, defaulting to `None`.
  - Pass `device=device` to `run_query(...)`.
- **Mirror**: `chat_ui/chat_ui/state.py:80-90`
- **Validate**: `pytest tests/test_chat_state.py`

### Task 2: Add unit tests for User-Agent capture & fallback

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE
- **Implement**:
  - Add test `test_chat_state_send_populates_device_from_router_headers`: mock `self.router.headers.raw_headers` with `{"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}`, run `_send()`, assert `run_query` received that user agent and audit row `device` is populated.
  - Add test `test_chat_state_send_device_fallback_when_headers_missing`: verify that when router/headers are unavailable or empty, `device` falls back to `None` and send succeeds.
- **Mirror**: `tests/test_chat_state.py:174-210`
- **Validate**: `pytest tests/test_chat_state.py`

---

## End-to-End Tests

- [ ] Send a message via chat, inspect SQLite `audit_logs` table (`SELECT device FROM audit_logs ORDER BY id DESC LIMIT 1`) -> `device` matches User-Agent header (non-null).
- [ ] Send a message when router headers are absent -> `device` is `None` and message succeeds without error.

---

## Validation

```bash
pytest tests/test_chat_state.py
```

---

## Acceptance Criteria

- [ ] Given a message sent from the chat, when `run_query(...)` is called, then `device` carries the browser User-Agent instead of `None`.
- [ ] Given that message, when its audit row is inspected, then `device` is non-null.
- [ ] Given the value written, when compared against an API-originated row, then it occupies the same column and `QueryRequest.device` contract — no schema change.
- [ ] Given a session where the User-Agent is unavailable, when a message is sent, then `device` falls back to `None` and send succeeds.
- [ ] All existing tests pass.
