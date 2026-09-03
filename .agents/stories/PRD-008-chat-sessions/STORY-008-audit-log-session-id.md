---
id: STORY-008
prd: PRD-008
slug: audit-log-session-id
title: "session_id on AuditLog, log_query and insert_audit_log"
type: feature
priority: high
complexity: small
phase: "2 - Pipeline and API"
status: todo
labels: [backend, audit, database]
epic_branch: epic/PRD-008-chat-sessions
plan: null
report: null
commit: null
depends_on: [STORY-003]
blocks: [STORY-009, STORY-011]
skills: []
created: 2026-09-02
updated: 2026-09-02
---

# STORY-008: session_id on AuditLog, log_query and insert_audit_log

## Description

As a compliance admin, I want an audit row to be able to name the conversation it came from, so that a report about "that chat" resolves to a set of rows rather than a guess (PRD Section 5, story 8).

## Acceptance Criteria

- [ ] Given [app/services/audit_logger.py](../../../app/services/audit_logger.py), when `log_query` is read, then it accepts `session_id: Optional[str] = None` and passes it onto the `AuditLog` it constructs.
- [ ] Given the new parameter, when the signature is inspected, then it is keyword-defaulted and positioned after the existing parameters, so every current call site keeps working untouched.
- [ ] Given [app/db/database.py](../../../app/db/database.py)'s `insert_audit_log`, when it runs, then `session_id` is written, and `_row_to_audit_log` maps it back on every read.
- [ ] Given a `log_query(...)` call with no `session_id`, when the row is read back, then `session_id` is `NULL` — today's behaviour exactly, for every existing caller and every API client that omits the field.
- [ ] Given a `log_query(...)` call with a `session_id`, when `get_audit_log(audit_id)` retrieves the row, then the value round-trips unchanged.
- [ ] Given [tests/test_audit_logger.py](../../../tests/test_audit_logger.py) and [tests/test_db.py](../../../tests/test_db.py), when the suite runs, then existing assertions pass **unmodified** and new ones cover both the present and absent cases.
- [ ] Given `list_audit_logs`, `count_audit_logs` and every stats counter, when they run, then their behaviour is unchanged — this story adds a column to the row, not a filter to any query.

## Technical Notes

- Files: [app/services/audit_logger.py](../../../app/services/audit_logger.py), [app/db/database.py](../../../app/db/database.py) (`insert_audit_log` and `_row_to_audit_log` only).
- The column itself already exists — [[STORY-002]] declared it in `AUDIT_LOGS_ADDED_COLUMNS` and [[STORY-003]] converged it. This story only makes the write and read paths carry it.
- `_row_to_audit_log` at [app/db/database.py:575](../../../app/db/database.py) maps the full field set including the boolean coercions. Add `session_id` there and nowhere else; PRD-007 STORY-006 recorded that a partial mapping in this function is the silent-loss failure mode.
- Do **not** thread `session_id` through `run_query` here. That is [[STORY-009]], and keeping the parameter's arrival separate from its seven call sites keeps both diffs readable.
- Do **not** touch `AuditQueryEntry`. That is [[STORY-011]].
- No stats counter changes. Nothing in [app/models/schemas.py](../../../app/models/schemas.py)'s `StatsResponse` gains a session dimension in this PRD; PRD Section 4 puts sessions in the admin console out of scope.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story touches no UI. No skill applies.

## Dependencies

- **Blocked by**: STORY-003
- **Blocks**: STORY-009, STORY-011

## PRD Reference

Source: [`PRD-008/PRD.md`](../../PRDs/PRD-008-chat-sessions/PRD.md) — Section 4 (Pipeline & API), Section 5 (story 8), Section 12 Phase 2
