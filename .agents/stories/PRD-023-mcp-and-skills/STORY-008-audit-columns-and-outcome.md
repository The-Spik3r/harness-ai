---
id: STORY-008
prd: PRD-023
slug: audit-columns-and-outcome
title: "Audit: MCP columns on `action_decisions`, `record(..., mcp=)`, `record_outcome`, correlation lookup"
type: feature
priority: high
complexity: medium
phase: "2 - Vocabulary and configuration"
status: todo
labels: [audit, db, security]
epic_branch: epic/PRD-023-mcp-and-skills
plan: null
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-013, STORY-017]
skills: []
created: 2026-11-22
updated: 2026-11-22
---

# STORY-008: Audit: MCP columns on `action_decisions`, `record(..., mcp=)`, `record_outcome`, correlation lookup

## Description

As an auditor, I want every gateway call stored as one `action_decisions` row with its surface, server, skills, arguments hash and outcome, so that what ran is evidence beside what was proposed.

## Acceptance Criteria

- [ ] Given a PRD-022 database, when `init_db()` runs, then the eleven Section 6.9 columns are added through `ACTION_DECISIONS_ADDED_COLUMNS` (extending the existing mapping) plus `idx_action_decisions_link (user_id, arguments_canonical_hash)`, no other table is touched, and old rows read `surface='v1'`
- [ ] Given `record(decisions, identity, ..., *, mcp=McpRecord(...))` with no `audit_ref`, when the write fails with a storage error, then it raises and journals nothing (PRD-018 O8 / PRD-023 T9); when it succeeds the row carries `surface`, `mcp_server`, `skills`, `arguments_canonical_hash`, `linked_decision_id`, `mcp_config_digest` and `tool_call_id='mcp:<id>'`
- [ ] Given `record_outcome(row_id, outcome, duration_ms, result_bytes, result_hash, result_flags)`, when the update fails, then it does not raise and logs `ERROR` naming the user and row id; the outcome vocabulary is closed (`ok | tool_error | upstream_error | timeout | result_too_large | result_blocked`)
- [ ] Given a database helper for correlation, when called with `(user_id, server, tool, hash, window_seconds)`, then it returns the newest `/v1` row with `decision IN ('allow','flag')` inside the window and not already linked, or none

## Technical Notes

- Orchestrator decision (STORY-001): confirmed by the spike. Extend `ACTION_DECISIONS_ADDED_COLUMNS` (`app/db/models.py:480`). The insert paths are `app/db/database.py:3404` and `:3459`. Signature: `record(decisions, identity, audit_ref=None, session_id=None, *, mcp=None)` (PRD D21, amended).
- Orchestrator: the PRD says 'fourth added-columns mapping', but `ACTION_DECISIONS_ADDED_COLUMNS = {"write_id": "TEXT"}` already exists (`app/db/models.py:480`); extend it. `record()` now takes `audit_ref` (PRD-018), not `audit_id` (`app/services/action_audit.py:214`).
- Added columns that are NOT NULL must declare a default (`test_added_columns_declaring_not_null_also_declare_a_default`).
- No caller yet: the gateway (STORY-013) and alias rows (STORY-016) use these. The correlation helper is used in STORY-016.
- Results are never stored, only hash/size/flags (T14).

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-013, STORY-017

## PRD Reference

Source: [`PRD-023/PRD.md`](../../PRDs/PRD-023-mcp-and-skills/PRD.md) — Sections 4 (Audit), 6.9, F10, D9, D21, T9, T14
