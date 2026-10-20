---
id: STORY-009
prd: PRD-013
slug: usage-counter-storage
title: "usage_daily table with atomic admit and charge statements; RETURNING verified"
type: spike
priority: high
complexity: medium
phase: "2 - Limit primitives"
status: done
labels: [backend, database, limits]
epic_branch: epic/PRD-013-audit-and-usage-limits
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-009-usage-counter-storage.plan.md
report: .agents/reports/PRD-013-audit-and-usage-limits/STORY-009-usage-counter-storage.report.md
commit: 13f01f6
depends_on: []
blocks: [STORY-010, STORY-016]
skills: []
created: 2026-10-04
updated: 2026-10-18
---

# STORY-009: usage_daily table with atomic admit and charge statements; RETURNING verified

## Description

As a platform operator, I want usage counted in one shared row per user per day by single atomic statements, so that limits hold across instances and cost one round trip to check.

## Acceptance Criteria

- [ ] Given the pinned `libsql==0.1.11` against the local dev server, when `INSERT ... ON CONFLICT ... DO UPDATE ... RETURNING` is executed, then the story report records whether rows come back, with the exact statement and output; if they do not, `admit_usage` is implemented as upsert plus `SELECT` in one `_session()` transaction and the report says so.
- [ ] Given a fresh database, when `init_db()` runs, then `usage_daily` exists with primary key `(user_id, day)` and the columns in PRD Section 6.5, created in the same `_session()` block as the other tables.
- [ ] Given a user with no row today, when `admit_usage(user_id)` is called three times within one minute, then it returns `window_requests` 1, 2, 3, `tokens_today` 0, and a `day` and `window_start` taken from the database clock; `requests` on the row is 3.
- [ ] Given a row whose `window_start` is an earlier minute, when `admit_usage` is called, then `window_requests` is 1 and `requests` keeps increasing.
- [ ] Given `charge_usage(user_id, day, input_tokens=120, output_tokens=30, unsplit_tokens=0)` and then `charge_usage(..., 0, 0, 150)`, when `admit_usage` is called next, then `tokens_today` is 300.

## Technical Notes

- Type `spike` because the first criterion is a finding that decides the implementation. `RETURNING` was not among the six driver behaviours PRD-007 STORY-001 verified; the comment above `_SUMMARY_SQL` records what was.
- Statements are in PRD Section 6.5. `day` is `date('now')` and the window is `strftime('%s','now') / 60`, both computed by the database so instances share one clock. Do not compute either in Python.
- Add `CREATE_USAGE_DAILY_TABLE` to `app/db/models.py` and a frozen `UsageAdmission(day, window_start, window_requests, tokens_today)` dataclass.
- To test window rollover without sleeping, insert a row with an old `window_start` directly.
- No limit is compared here; that is STORY-010. These two functions only count and report.
- Tests in `tests/test_db.py` or a new `tests/test_usage_storage.py`.
- Skills: none applicable. No UI surface changes in this story.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-010, STORY-016

## PRD Reference

Source: [`PRD-013-audit-and-usage-limits/PRD.md`](../../PRDs/PRD-013-audit-and-usage-limits/PRD.md) — sections 6.5 (D3), 7 (F8), 14 (Risk 2)
