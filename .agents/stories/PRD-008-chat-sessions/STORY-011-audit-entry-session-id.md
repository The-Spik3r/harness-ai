---
id: STORY-011
prd: PRD-008
slug: audit-entry-session-id
title: "AuditQueryEntry.session_id so GET /audit reports the conversation"
type: feature
priority: medium
complexity: small
phase: "2 - Pipeline and API"
status: todo
labels: [backend, api, audit]
epic_branch: epic/PRD-008-chat-sessions
plan: null
report: null
commit: null
depends_on: [STORY-008]
blocks: [STORY-022]
skills: []
created: 2026-09-02
updated: 2026-09-02
---

# STORY-011: AuditQueryEntry.session_id so GET /audit reports the conversation

## Description

As a compliance admin, I want `GET /audit` to return the session an entry belongs to, so that three rows that were one conversation are visibly one conversation.

## Acceptance Criteria

- [ ] Given [app/models/schemas.py](../../../app/models/schemas.py), when `AuditQueryEntry` is read, then it declares `session_id: Optional[str] = None`.
- [ ] Given [app/routers/admin.py](../../../app/routers/admin.py), when `GET /audit` projects a row, then `session_id` is included.
- [ ] Given a row written before this PRD, when it is returned, then `session_id` is `null` and every other field is unchanged — an additive field on a response model, invisible to a consumer that does not read it.
- [ ] Given three sends in one session, when `GET /audit` is called, then all three entries carry the same `session_id`.
- [ ] Given [tests/test_audit_router.py](../../../tests/test_audit_router.py), when the suite runs, then it passes **unmodified**, and new assertions cover the present and absent cases.
- [ ] Given [tests/test_schemas.py](../../../tests/test_schemas.py), when it runs, then the new field is asserted as optional with a `None` default — a required field here would break every existing constructor.
- [ ] Given PRD-006's admin console, when `git diff` is inspected, then nothing under [chat_ui/chat_ui/components/register.py](../../../chat_ui/chat_ui/components/register.py) or [chat_ui/chat_ui/admin_state.py](../../../chat_ui/chat_ui/admin_state.py) changed.

## Technical Notes

- Files: [app/models/schemas.py](../../../app/models/schemas.py), [app/routers/admin.py](../../../app/routers/admin.py).
- PRD Section 4 draws the boundary this story must not cross: "**Sessions in the admin console** — PRD-006's register and summary are untouched. The `session_id` column reaches `GET /audit` and stops there." Rendering it in the register is a PRD-006 extension recorded in PRD Section 13, not work for this story.
- `AuditQueryEntry` currently projects nine of the audit row's fields and drops `success` and `error_message` — a defect PRD-006 Section 1 documented and PRD-006 Section 13 parked as a follow-up. This story adds one field and does **not** open that question; adding `success` here would be a different PRD's work smuggled into this commit.
- `GET /stats` is unchanged. `StatsResponse` gains no session dimension.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story touches no UI. No skill applies.

## Dependencies

- **Blocked by**: STORY-008
- **Blocks**: STORY-022

## PRD Reference

Source: [`PRD-008/PRD.md`](../../PRDs/PRD-008-chat-sessions/PRD.md) — Section 4 (Pipeline & API, Out of Scope), Section 5 (story 8), Section 10, Section 12 Phase 2
