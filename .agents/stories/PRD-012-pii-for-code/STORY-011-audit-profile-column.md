---
id: STORY-011
prd: PRD-012
slug: audit-profile-column
title: "audit_logs.profile on every arm; /audit and the Register show it"
type: feature
priority: medium
complexity: medium
phase: "3 - Policy into the pipeline"
status: todo
labels: [backend, audit, database, admin]
epic_branch: epic/PRD-012-pii-for-code
plan: null
report: null
commit: null
depends_on: [STORY-010]
blocks: [STORY-014]
skills: []
created: 2026-09-23
updated: 2026-09-23
---

# STORY-011: audit_logs.profile on every arm; /audit and the Register show it

## Description

As a security admin, I want every audit row to say which profile ran, so that `pii_detected_output = 0` on a `code` row is read as "not analyzed" rather than "clean".

## Acceptance Criteria

- [ ] Given `app/db/models.py`, when it is read, then `profile TEXT` is declared in both `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS`, and `AuditLog.profile: Optional[str] = None`. Given a database created before this story, when `init_db()` runs, then the column is added and no row is backfilled.
- [ ] Given `run_conversation`, when any arm writes a row (forbidden ×3, context limit, duplicate, pattern block, pattern flag, redaction limit, redaction error ×2, upstream error, success), then `profile` is passed explicitly as a required keyword and holds the resolved profile name.
- [ ] Given `/query` and the chat UI, when they write rows, then `profile='chat'`.
- [ ] Given `GET /audit`, when it returns an entry, then `AuditQueryEntry.profile` is present and nullable; given the admin Register, when a row is shown, then its profile is shown.
- [ ] Given `/stats` and the admin snapshot, when they are computed, then `pii_detected_queries` and `top_pii_entities` are unchanged for a database of `chat` rows.

## Technical Notes

- Arms written before the PII policy is resolved (the forbidden arms) still know the profile name: it is a pure function of the argument and `PATTERN_PROFILE_DEFAULT`. Resolve the name once, at the top of `run_conversation`.
- Make `profile` a required keyword on `_deny` and on each direct `log_query` call site in the pipeline. A forgotten arm should be a `TypeError`, not a NULL (PRD-008 STORY-009, PRD-009 Risk 6). `log_query` itself keeps an `Optional` default for the router's foreign-session arm, which writes before any profile exists. Document that exception in a comment.
- Tests: extend `tests/test_db.py` (convergence), `tests/test_audit_router.py`, and the admin Register tests.
- Skills: `frontend-design` does not apply. Adding one field to the existing Register row is not a visual redesign.

## Dependencies

- **Blocked by**: STORY-010
- **Blocks**: STORY-014

## PRD Reference

Source: [`PRD-012-pii-for-code/PRD.md`](../../PRDs/PRD-012-pii-for-code/PRD.md) — sections 6.8 (D9), 7 (F9), 10, 11 (Functional requirements)
