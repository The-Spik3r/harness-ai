---
id: STORY-014
prd: PRD-005
slug: chat-ui-login
title: Chat UI login replaces the free-text user_id prompt
type: feature
priority: high
complexity: medium
phase: "Phase 3 — Pipeline and ingress wiring"
status: done
labels: [frontend, security]
epic_branch: epic/PRD-005-rbac
plan: .agents/plans/PRD-005-rbac/completed/STORY-014-chat-ui-login.plan.md
report: .agents/reports/PRD-005-rbac/STORY-014-chat-ui-login.report.md
commit: a38f38b
depends_on: [STORY-010, STORY-008]
blocks: [STORY-017]
skills: []
created: 2026-08-28
updated: 2026-08-29
---

# STORY-014: Chat UI login replaces the free-text user_id prompt

## Description

As an end user, I want to log in to the chat with my own credential, so that my activity is attributed to me and cannot be spoofed by typing someone else's user id.

## Acceptance Criteria

- [ ] Given the login form, when a valid token is submitted, then the session becomes authenticated and the chat is usable
- [ ] Given an invalid or deactivated token, when it is submitted, then an error is shown and the chat stays locked
- [ ] Given an authenticated session, when `send()` runs, then the role is re-resolved server-side on every call, never read from a state var
- [ ] Given `ChatState`, when inspected, then it holds no token and no role — only the authenticated `user_id`, set exclusively by `login()`
- [ ] Given a `QueryBlockedForbiddenResponse`, when returned, then `send()` handles it in an explicit `isinstance` branch and renders its own bubble, not the suspicious-pattern one

## Technical Notes

- `chat_ui/chat_ui/state.py`: `submit_user_id()` becomes `login()`; `chat_ui/chat_ui/components/chat.py`: `user_id_prompt()` becomes a login form.
- PRD Risk 5: Reflex state vars are serialized to the client and mutable by client-originated events, so they are not a trust boundary. Role-gating with `rx.cond` is cosmetic — the decision must come from the server on every event.
- `send()` currently ends in a catch-all `else` over the response union; with a fourth member that branch must become explicit or forbidden results render as injection blocks.
- **Merge `epic/PRD-004-chat-ui-redesign` into `main` before starting this story** (PRD Appendix) — it rewrites the same file with a typed `ChatMessage`, a `pending` flag, and `formatting.py`/`copy.py`. Doing this story first guarantees a painful conflict.
- Tests: `tests/test_chat_state.py`.

## Dependencies

- **Blocked by**: STORY-010, STORY-008
- **Blocks**: STORY-017

## PRD Reference

Source: [`PRD-005/PRD.md`](../../PRDs/PRD-005-rbac/PRD.md) — sections 6, 9, 14 (Risk 5)
