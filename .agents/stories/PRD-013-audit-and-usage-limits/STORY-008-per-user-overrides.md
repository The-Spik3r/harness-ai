---
id: STORY-008
prd: PRD-013
slug: per-user-overrides
title: "Per-user limit overrides: users columns, Identity fields and manage_users set-limits"
type: feature
priority: high
complexity: medium
phase: "2 - Limit primitives"
status: in-progress
labels: [backend, database, identity, cli]
epic_branch: epic/PRD-013-audit-and-usage-limits
plan: .agents/plans/PRD-013-audit-and-usage-limits/STORY-008-per-user-overrides.plan.md
report: null
commit: null
depends_on: []
blocks: [STORY-010, STORY-013, STORY-016]
skills: []
created: 2026-10-04
updated: 2026-10-18
---

# STORY-008: Per-user limit overrides: users columns, Identity fields and manage_users set-limits

## Description

As a platform operator, I want to set one user's token budget or request rate from the CLI, so that a heavy user does not require a configuration change for everyone.

## Acceptance Criteria

- [ ] Given a `users` table created before this story, when `init_db()` runs, then `token_budget_daily INTEGER` and `requests_per_minute INTEGER` exist, both NULL on every existing row, converged through a new `USERS_ADDED_COLUMNS` mapping and the existing `_add_missing_columns`.
- [ ] Given `python scripts/manage_users.py set-limits --user-id dana --token-budget 5000000`, when it runs, then Dana's row has `token_budget_daily=5000000`, her `requests_per_minute` is unchanged, and `resolve(dana_token)` returns an `Identity` with `token_budget_daily=5000000`.
- [ ] Given `--token-budget default` or `--requests-per-minute default`, when it runs, then that column is set to NULL; given a value below 1, a non-number, or an unknown user, then the command exits non-zero with a message and writes nothing.
- [ ] Given `list-users`, when it runs, then each line shows both limits, printing `default` for NULL.
- [ ] Given `resolve(settings.ADMIN_TOKEN)`, when it returns, then the identity has `break_glass=True` and both overrides `None`; given a user token whose role is `admin`, then `break_glass` is `False`.

## Technical Notes

- `app/db/models.py`: declare both columns in `CREATE_USERS_TABLE` and in `USERS_ADDED_COLUMNS`. `init_db()` calls `_add_missing_columns(conn, "users", USERS_ADDED_COLUMNS)` after `CREATE_USERS_TABLE`; the position matters for the reason given for `chat_messages`.
- `User` gains two `Optional[int] = None` fields; `_row_to_user` maps them; new `set_user_limits(user_id, *, token_budget_daily=..., requests_per_minute=...)` in `database.py` that updates only the columns passed (use a sentinel to tell "leave alone" from "set to NULL").
- `app/services/identity.py`: `Identity` stays frozen and gains `break_glass: bool = False`, `token_budget_daily: Optional[int] = None`, `requests_per_minute: Optional[int] = None`. Only `resolve()` sets them. Existing `Identity(user_id, role)` constructions across the suite keep working.
- No extra round trip: `find_user_by_token_hash` already reads the row on every request.
- Nothing reads the new `Identity` fields yet (STORY-010, STORY-013).
- Tests: `tests/test_identity.py`, `tests/test_manage_users_cli.py`, `tests/test_db.py`.
- Skills: none applicable. No UI surface changes in this story.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-010, STORY-013, STORY-016

## PRD Reference

Source: [`PRD-013-audit-and-usage-limits/PRD.md`](../../PRDs/PRD-013-audit-and-usage-limits/PRD.md) — sections 4 (Identity and users), 6.6, 6.8, 7 (F7), 10 (CLI)
