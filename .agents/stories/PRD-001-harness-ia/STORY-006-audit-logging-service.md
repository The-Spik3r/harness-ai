---
id: STORY-006
prd: PRD-001
slug: audit-logging-service
title: Audit logging service
type: feature
priority: high
complexity: medium
phase: "2 - Core Logic"
status: done
labels: [backend, security, db]
epic_branch: epic/PRD-001-harness-ia
plan: .agents/plans/PRD-001-harness-ia/completed/STORY-006-audit-logging-service.plan.md
report: .agents/reports/PRD-001-harness-ia/STORY-006-audit-logging-service.report.md
commit: 42b8dbd
depends_on: [STORY-002, STORY-003]
blocks: [STORY-008]
skills: []
created: 2026-07-04
updated: 2026-07-04
---

# STORY-006: Audit logging service

## Description

As a compliance officer, I want every query and response logged (hashed + truncated preview) without any IP or geolocation data, so that we have a full audit trail that respects user privacy by construction (RF-5 through RF-9).

## Acceptance Criteria

- [ ] Given a completed query (success, duplicate-blocked, or pattern-blocked), when the logger is called, then exactly one `audit_logs` row is written with `user_id`, `device`, `prompt_hash`, `prompt_preview` (first 500 chars), `response_hash`, `response_preview` (first 500 chars), `model_used`, `tokens_used`, `timestamp` (UTC), `was_duplicate_blocked`, `suspicious_pattern`, `success`, `error_message`.
- [ ] Given a prompt/response longer than 500 characters, when logged, then `prompt_preview`/`response_preview` are truncated to exactly 500 characters while `prompt_hash`/`response_hash` are computed over the full text.
- [ ] Given a blocked request (duplicate or suspicious), when logged, then `response_hash`/`response_preview`/`tokens_used` are null/empty (no model was called) and the relevant blocked flag is set.
- [ ] Given the logger writes a row, when inspected, then no field anywhere contains an IP address or geolocation value.

## Technical Notes

- Implement `app/services/audit_logger.py` per PRD Section 6, writing through the repository functions from STORY-002.
- `audit_id` returned to callers can be the DB row `id` or a generated identifier — must be usable to correlate with `GET /audit` entries later.
- Unit test: success case, duplicate-blocked case, suspicious-blocked case, and long-prompt truncation.

## Dependencies

- **Blocked by**: STORY-002, STORY-003
- **Blocks**: STORY-008

## PRD Reference

Source: [`PRD-001/PRD.md`](../../PRDs/PRD-001-harness-ia/PRD.md) — Section 5 (User Story 4), Section 7 (Audit logging), Section 9 (Privacy guarantees), Section 12 (Phase 2)
