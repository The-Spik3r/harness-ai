---
id: STORY-007
prd: PRD-018
slug: chat-ui-storage-failures
title: Chat UI — resolve() inside the send's try/finally, sign-in storage notice, fixed storage_unavailable copy
type: bug
priority: high
complexity: small
phase: "3 - Fail fast and say so"
status: todo
labels: [frontend, chat-ui]
epic_branch: epic/PRD-018-db-resilience
plan: null
report: null
commit: null
depends_on: [STORY-005, STORY-006]
blocks: []
skills: [frontend-design]
created: 2026-11-17
updated: 2026-11-17
---

# STORY-007: Chat UI survives a storage failure

## Description

As a chat user, I want a storage failure during sign-in or at the start of a send to show a clear message and leave the composer usable, so that I am never stuck with a locked composer and driver text in a bubble.

## Acceptance Criteria

- [ ] Given `_do_send`, when `resolve(token)` raises `StorageError` (including `StorageUnavailableError`), then the user sees an `internal_error` bubble with fixed copy ("the harness's database is unavailable, nothing was sent") and `pending == False` afterwards. `resolve()` now runs inside the `try`/`finally` that clears `pending` (today `state.py:962` sets it, `:967` resolves, `:995` opens the `try`).
- [ ] Given `ChatState.login`, when `resolve()` raises `StorageError`, then `login_error` shows a storage-unavailable notice (not "invalid token") and the user is not signed in.
- [ ] Given a `DuplicateCheckError` / `UsageLimitError` / `ChatSessionError` caused by `StorageUnavailableError` during a send, when the bubble renders, then its detail is the fixed `storage_unavailable` copy with no driver text (today `detail=str(exc)`, `:1175-1196`). Non-transient causes keep today's bubble.
- [ ] Given `chat_ui/chat_ui/copy.py`, when read, then the new strings live there beside the existing notices, in the same language as the existing UI copy (English).
- [ ] Given the chat UI tests and `tests/test_chat_ui_startup_guard.py`, when run, then they pass, and a new test pins `pending == False` after a `resolve()` storage failure.

## Technical Notes

- `chat_ui/chat_ui/state.py` (`login` `:311`, `_do_send` `:955-1000`, internal-error arms `:1175-1196`), `chat_ui/chat_ui/copy.py`.
- Reflex 0.9.6.post1. Follow the existing notice/bubble components. No new component is needed. The `frontend-design` skill applies only if visual changes are made; keep this to state and copy.
- Do not add any retry in the UI: storage retries already happened in `_unit_of_work`.
- Chat UI probe rule from the brief: if you touch `chat_ui/`, run `tests/test_chat_ui_startup_guard.py`.
- Tests: the existing `tests/test_chat_ui_*.py` state tests (find the one covering `_do_send` and `login`), plus a new focused test.

## Dependencies

- **Blocked by**: STORY-005, STORY-006 (shares the fixed copy and the "caused by" rule)
- **Blocks**: None

## PRD Reference

Source: [`PRD-018-db-resilience/PRD.md`](../../PRDs/PRD-018-db-resilience/PRD.md) — sections 3 (Chat user), 4 (Ingress mapping, chat UI), 6.7, 9.2 (T9), 11 (Functional: `pending == False`)
