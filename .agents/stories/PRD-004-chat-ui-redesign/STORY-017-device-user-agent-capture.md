---
id: STORY-017
prd: PRD-004
slug: device-user-agent-capture
title: "Populate device from the browser User-Agent on chat sends"
type: feature
priority: medium
complexity: small
phase: "4 - Shell, session, and recovery actions"
status: done
labels: [ui, reflex, state, audit]
epic_branch: epic/PRD-004-chat-ui-redesign
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-017-device-user-agent-capture.plan.md
report: .agents/reports/PRD-004-chat-ui-redesign/STORY-017-device-user-agent-capture.report.md
commit: null
depends_on: [STORY-001]
blocks: [STORY-019]
skills: []
created: 2026-08-21
updated: 2026-08-25
---

# STORY-017: Populate device from the browser User-Agent on chat sends

## Description

As a security admin, I want chat-originated audit rows to record the device, so that `audit_logs.device` is not null for every chat row while API rows can populate it (PRD User Story 7).

## Acceptance Criteria

- [ ] Given a message sent from the chat, when `run_query(...)` is called, then `device` carries the browser User-Agent instead of the `None` hardcoded at [state.py:63](../../../chat_ui/chat_ui/state.py).
- [ ] Given that message, when its audit row is inspected, then `device` is non-null (PRD Section 11).
- [ ] Given the value written, when compared against an API-originated row, then it occupies the same column and the same `QueryRequest.device` contract — no schema change and no new column (PRD Section 4 Out of Scope: "Any change under `app/`").
- [ ] Given a session where the User-Agent is unavailable, when a message is sent, then `device` falls back to `None` and the send still succeeds — capture must never become a new failure path.

## Technical Notes

- `chat_ui/chat_ui/state.py`. Reading the User-Agent from the client request in a Reflex event is framework-specific — per `chat_ui/AGENTS.md` (verbatim): "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs."
- Privacy boundary, verbatim from PRD Section 9: "no IP address or geolocation captured. The newly-populated `device` field is the browser User-Agent, which the `audit_logs.device` column and `QueryRequest.device` already accommodate by design; it is not new data collection, it is a column stopping being null."
- Depends on [[STORY-001]] because the call site is restructured there; the argument list is otherwise untouched by that story.
- Regression guard: `tests/test_chat_state.py::test_chat_and_api_audit_rows_share_schema_and_fields` (lines 240-306) compares chat and API rows field by field — confirm the newly-populated `device` does not break that parity assertion.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-019

## PRD Reference

Source: [`PRD-004/PRD.md`](../../PRDs/PRD-004-chat-ui-redesign/PRD.md) — Section 4 (Metadata & session), Section 9, Section 10 (contract table), Section 12 Phase 4, User Story 7, Section 15 (`state.py:63`)
