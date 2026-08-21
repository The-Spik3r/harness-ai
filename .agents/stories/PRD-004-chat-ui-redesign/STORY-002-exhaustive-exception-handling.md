---
id: STORY-002
prd: PRD-004
slug: exhaustive-exception-handling
title: "Exhaustive except arms in send(): PiiRedactorError + catch-all"
type: bug
priority: high
complexity: small
phase: "1 - Correctness foundation"
status: done
labels: [ui, reflex, state, errors]
epic_branch: epic/PRD-004-chat-ui-redesign
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-002-exhaustive-exception-handling.plan.md
report: .agents/reports/PRD-004-chat-ui-redesign/STORY-002-exhaustive-exception-handling.report.md
commit: 59899ca
depends_on: [STORY-001]
blocks: [STORY-004]
skills: []
created: 2026-08-21
updated: 2026-08-21
---

# STORY-002: Exhaustive except arms in send() — PiiRedactorError + catch-all

## Description

As an end user, I want a message that fails inside the harness to still produce a visible bubble, so that my message is never silently swallowed (PRD User Story 1, Section 2 "No silent drops").

## Acceptance Criteria

- [ ] Given `run_query(...)` raises `PiiRedactorError` (raised at `app/services/query_pipeline.py:58` and `:83`), when `send()` handles it, then a bubble carrying the exception text is appended instead of nothing being appended at all.
- [ ] Given `run_query(...)` raises an arbitrary unexpected exception (e.g. `RuntimeError("boom")`), when `send()` handles it, then a bubble is still appended — a catch-all `except Exception` arm guarantees no path ends without a bubble.
- [ ] Given `DuplicateCheckError` or `OpenRouterError`, when either is raised, then a bubble is still appended as today — no regression on the two arms that already exist at [state.py:67](../../../chat_ui/chat_ui/state.py).
- [ ] Given a test forcing each of the four exception paths, when it asserts on `state.messages`, then the message count grew by exactly one bubble in every case.
- [ ] Given `app/`, when the diff is inspected, then no file under it is modified — `PiiRedactorError` is newly *caught*, never changed (PRD Section 11).

## Technical Notes

- `chat_ui/chat_ui/state.py`: import `PiiRedactorError` from `app.services.pii_redactor`. It is already handled by the REST layer at `app/routers/query.py:28` (HTTP 500); the chat is the only consumer missing it, which is the silent-drop bug of PRD Section 1.
- The catch-all is the structural invariant behind "no silent drops" — PRD Section 6 calls it "the invariant that makes 'no silent drops' structurally true rather than aspirational". Order the arms named-first, `except Exception` last.
- Per-kind error styling (`upstream_error` vs `internal_error`) is [[STORY-004]] and [[STORY-008]]; this story only guarantees a bubble exists on every path, keeping today's `{"role": "system", ...}` shape so there is still no visual change.
- Add regression tests in `tests/test_chat_state.py` for `PiiRedactorError` and for a generic `Exception`, per PRD Section 12 Phase 1 validation.
- Per `chat_ui/AGENTS.md` (verbatim): "Before writing or editing any Reflex code, confirm these three skills are available: `reflex-docs`, `setup-python-env`, and `reflex-process-management`. If they are not, STOP and run the install step above — do not proceed without them."

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-004

## PRD Reference

Source: [`PRD-004/PRD.md`](../../PRDs/PRD-004-chat-ui-redesign/PRD.md) — Section 4 (Error handling), Section 6, Section 11, Section 12 Phase 1, User Story 1
