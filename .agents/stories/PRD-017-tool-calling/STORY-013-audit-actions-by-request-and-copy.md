---
id: STORY-013
prd: PRD-017
slug: audit-actions-by-request-and-copy
title: "GET /audit/actions?audit_id= and the Actions view's empty-state copy"
type: enhancement
priority: medium
complexity: small
phase: "3 - Decide and release"
status: todo
labels: [backend, api, admin, ui]
epic_branch: epic/PRD-017-tool-calling
plan: null
report: null
commit: null
depends_on: [STORY-010]
blocks: [STORY-015, STORY-018]
skills: [frontend-design]
created: 2026-11-15
updated: 2026-11-15
---

# STORY-013: GET /audit/actions?audit_id= and the Actions view's empty-state copy

## Description

As an auditor, I want to list the decisions of one request and to see an Actions view that describes what it holds now that tool calls are live, so that "what was asked" and "what the model tried" read together.

## Acceptance Criteria

- [ ] Given decisions recorded for audit rows 41 and 42, when `GET /audit/actions?audit_id=41` is called with `audit:read:all`, then only row 41's decisions are returned, in their stored order; combined with `?decision=deny` both filters apply.
- [ ] Given `audit:read:own`, when `?audit_id=` names another user's request, then the response is empty (scoping applies before the filter, exactly as today); neither permission → 403; a non-integer or negative `audit_id` → 422/400 as the endpoint's other parameters fail.
- [ ] Given the admin console's Actions view with zero rows, when rendered, then the body no longer says nothing calls the engine or names PRD-017 as future work; it says the view lists the decisions the action policy made on `/v1` tool calls, denied first, and how to get rows (tool calling is off unless `V1_TOOLS_ENABLED`), and `tests/test_actions_view.py:806-809` is updated with a PRD-017 comment.

## Technical Notes

- `app/routers/admin.py` (`GET /audit/actions`, added by PRD-016 STORY-016) and `app/db/database.py` (`list_action_decisions(limit, user_id=None, decision=None)`); the index `idx_action_decisions_audit` already exists (`app/db/models.py:399`).
- Copy: `chat_ui/chat_ui/admin_copy.py:332-338` (`EMPTY_ACTIONS_BODY`, "Time-bound by design: PRD-017 … must reword this body"); `chat_ui/chat_ui/components/actions.py:29, 244` docstrings mention PRD-017 — reword them too.
- Skill `frontend-design`: "Build with the brief's real content and subject matter throughout." Name what the view really holds (decisions on live tool calls), not generic filler. Copy only; no layout change.
- If you touch `chat_ui/`, run `tests/test_chat_ui_startup_guard.py` (brief).
- Tests: `tests/test_admin_actions.py`, `tests/test_actions_view.py`, `tests/test_admin_copy.py`.

## Dependencies

- **Blocked by**: STORY-010
- **Blocks**: STORY-015, STORY-018

## PRD Reference

Source: [`PRD-017-tool-calling/PRD.md`](../../PRDs/PRD-017-tool-calling/PRD.md) — sections 4 (Admin console and API), 5 (story 7), 7 (F10), 10
