---
id: STORY-003
prd: PRD-006
slug: admin-token-gate
title: "AdminState token gate: compare_digest, one generic error, sign-out clears state"
type: feature
priority: high
complexity: medium
phase: "1 - Access and data"
status: todo
labels: [ui, reflex, state, security, admin]
epic_branch: epic/PRD-006-admin-console
plan: null
report: null
commit: null
depends_on: []
blocks: [STORY-004, STORY-006, STORY-009]
skills: [reflex-docs]
created: 2026-08-28
updated: 2026-08-28
---

# STORY-003: AdminState token gate: compare_digest, one generic error, sign-out clears state

## Description

As a security admin, I want the console to require the admin token and to hold nothing after sign-out, so that an open browser on a shared machine is not a standing disclosure (PRD Section 5, story 8).

## Acceptance Criteria

- [ ] Given `chat_ui/chat_ui/admin_state.py`, when it is created, then `AdminState` holds `token_input`, `authenticated: bool = False` and `gate_error: str`, and `authenticate()` compares the submitted token with `secrets.compare_digest` against `settings.ADMIN_TOKEN` — the same comparison `require_admin_token` uses.
- [ ] Given an empty token, a wrong-length token and a wrong token of the correct length, when each is submitted, then all three produce the **identical** `gate_error` string and leave `authenticated` False — no oracle distinguishes them.
- [ ] Given a correct token, when it is submitted, then `authenticated` becomes True, `gate_error` is cleared, and the load is triggered.
- [ ] Given an authenticated state with rows and figures populated, when `sign_out()` is called, then the token, the loaded rows, the summary figures and the last-refreshed stamp are all cleared from state — not merely hidden from the view.
- [ ] Given a submitted token and a configured token of differing byte lengths, when `compare_digest` is called, then it does not raise — both operands are encoded consistently first.
- [ ] Given `load()` on an unauthenticated state, when it is called directly, then it returns without reading the database and the row list stays empty (Risk 1).
- [ ] Given [app/config.py](../../../app/config.py) and [app/middleware/auth.py](../../../app/middleware/auth.py), when the diff is inspected, then neither is modified.

## Technical Notes

- New file `chat_ui/chat_ui/admin_state.py`. It imports `settings` from `app/config.py` and read functions from `app/db/database.py` only — PRD Section 9, verbatim: "`AdminState` imports only the read functions from `app/db/database.py`. `insert_audit_log` is not imported, and there is no write path from any admin page."
- Read [app/middleware/auth.py](../../../app/middleware/auth.py)'s `require_admin_token` first and mirror its comparison exactly, including how it handles a `None` or empty configured token. Do not modify it — [tests/test_admin_auth.py](../../../tests/test_admin_auth.py) must pass unmodified.
- PRD Section 9: the token "is not stored beyond the Reflex session state. It is never written to `localStorage`, never placed in a URL, and never sent as a header from the browser, because the console reads the database in-process rather than calling its own HTTP endpoints."
- Risk 1 mitigation starts here: the guard clause on `load()` is defined in this story so an unauthenticated page has no data in state regardless of what renders. The `load()` body is [[STORY-004]].
- Per `chat_ui/AGENTS.md`, verbatim: "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory." Confirm there whether `AdminState` should subclass `rx.State` directly and how [chat_ui/chat_ui/state.py](../../../chat_ui/chat_ui/state.py) `ChatState` is declared. `AdminState` must be a **sibling** of `ChatState`, not a substate — PRD Section 4: "`ChatState` never reads admin state, and no admin page renders a chat component."

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-004, STORY-006, STORY-009

## PRD Reference

Source: [`PRD-006/PRD.md`](../../PRDs/PRD-006-admin-console/PRD.md) — Section 4 (console shell & access), Section 6 (read path), Section 9, Section 12 Phase 1, Risk 1
