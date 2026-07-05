---
story: STORY-006
prd: PRD-002
plan: .agents/plans/PRD-002-reflex-chat-ui/completed/STORY-006-wire-chatstate-to-pipeline.plan.md
epic_branch: epic/PRD-002-reflex-chat-ui
commit: 682ee14
status: COMPLETE
completed: 2026-07-05
---

# Implementation Report — STORY-006: Wire ChatState.send() to the shared query pipeline

**Plan**: `.agents/plans/PRD-002-reflex-chat-ui/completed/STORY-006-wire-chatstate-to-pipeline.plan.md`
**Epic Branch**: `epic/PRD-002-reflex-chat-ui`
**Commit**: `682ee14`

## Summary

`ChatState.send()` was rewritten as a Reflex background event (`@rx.event(background=True)`) that calls the shared `run_query(...)` pipeline (STORY-001) in-process, with the same argument shape `app/routers/query.py` uses. The blocking `call_openrouter` HTTP call happens outside any `async with self:` block so it doesn't hold the state lock for other sessions. The three pipeline outcomes are discriminated with `isinstance` (both blocked variants share `status="BLOCKED"`) and mapped to bubbles: `role="assistant"` for success, and a new `role="system"` bubble style (centered, amber, no avatar) for both blocked variants, using the exact `reason` text with no rewording. A `try/except` around `DuplicateCheckError`/`OpenRouterError` renders a `system` bubble with the error text instead of silently dropping the message, per PRD Section 2's "fail loud, not silent" principle.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Rewrite `ChatState.send()` as a background event calling `run_query(...)` | `chat_ui/chat_ui/state.py` | ✅ |
| 2 | Add a distinct `system`-role bubble style to `message_bubble()` | `chat_ui/chat_ui/components/chat.py` | ✅ |
| 3 | Manual walkthrough of all outcomes + audit parity (real browser, real running app) | N/A | ✅ |
| 4 | Full backend test suite regression check | N/A | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Syntax validation (`ast.parse`) on both changed files | ✅ |
| Full `pytest` suite | ✅ (99 passed, unmodified) |
| E2E (real headless-Chrome + real `reflex run --env prod --single-port`) | ✅ (4/4 outcomes) |

## End-to-End Verification

Driven live against a real `reflex run --env prod --single-port` process using headless Chrome (CDP), not a unit test:

1. **SUCCESS** — sent a fresh prompt ("describe a sunrise over the ocean..."); a real OpenRouter response rendered as a left-aligned assistant bubble: *"The golden sun peeks over the vast horizon, setting the rippling waves aglow with fiery hues."*
2. **Duplicate-blocked** — resending an already-logged prompt rendered `Blocked — Duplicate query within 24 hours (first sent at <timestamp>)` in the new amber system bubble.
3. **Suspicious-pattern-blocked** — a prompt containing `"ignore previous instructions"` rendered `Blocked — Suspicious pattern detected`.
4. **Error path (bonus robustness, not an explicit AC)** — while the configured `OPENROUTER_API_KEY` was still invalid mid-session, an OpenRouter `401` correctly surfaced as `Error: OpenRouter request failed: Client error '401 Unauthorized'...` in a system bubble instead of a silent hang.
5. **Audit parity (User Story 3 / AC 5)** — `curl -X POST http://localhost:3000/query` with an already-logged prompt returned the identical `BLOCKED` response (same `first_query_at`) the chat UI showed, proving the shared 24h dedup window. `GET /audit` confirmed all chat-originated and curl-originated rows (including the SUCCESS row, `audit_id: 9`) share the exact same schema (`AuditQueryEntry`) with no chat-specific fields.

One environment issue was found and fixed during verification (not a code bug): `app/config.py`'s `Settings` reads `.env` relative to the process's working directory, and `reflex run` is invoked from `chat_ui/`, so it was reading a separate, stale `chat_ui/.env` rather than the repo-root `.env` the user had just updated with a working `OPENROUTER_API_KEY`. Copied the working `.env` into `chat_ui/.env` (gitignored, not part of this commit) to unblock the live SUCCESS-path check. Flagging this for STORY-008 (Docker packaging), since the same relative-path lookup will matter for the container's working directory.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/state.py` | UPDATE | +45/-8 |
| `chat_ui/chat_ui/components/chat.py` | UPDATE | +23/-14 |

## Deviations from Plan

None — implementation matches the plan's Task 1/Task 2 code exactly. Task 3's manual walkthrough was executed via a real headless-Chrome/CDP session (not just visual review) since a browser-automation tool wasn't otherwise available in this environment; this is a strictly stronger form of the plan's specified validation, not a deviation in scope.

## Tests Written

None — this story's plan intentionally deferred automated test-writing to STORY-007 ("Chat pipeline unit test suite"), which depends on STORY-006. `call_openrouter` is imported and passed explicitly in `chat_ui/chat_ui/state.py` (mirroring `app/routers/query.py`) specifically so STORY-007 can `monkeypatch.setattr("chat_ui.state.call_openrouter", ...)` the same way `tests/test_query_router.py` does today.

## Acceptance Criteria

- [x] `ChatState.send()` calls `run_query(...)` directly in-process (a plain Python call via a Reflex background event, not an HTTP round-trip)
- [x] `SUCCESS` result renders as a distinct assistant-style chat bubble
- [x] Duplicate-blocked result renders as a distinct system-style bubble with the exact `reason` text `POST /query` returns
- [x] Suspicious-pattern-blocked result renders as a distinct system-style bubble with the exact `reason` text `POST /query` returns
- [x] Chat-originated and curl-originated audit rows for the same prompt share schema and the same 24h duplicate window
- [x] Blocked reasons match 100% between chat and `/query` for both duplicate and suspicious cases
- [x] All tasks completed
- [x] Follows existing patterns
