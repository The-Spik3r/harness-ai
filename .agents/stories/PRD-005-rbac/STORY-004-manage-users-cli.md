---
id: STORY-004
prd: PRD-005
slug: manage-users-cli
title: Bootstrap CLI — scripts/manage_users.py
type: technical
priority: high
complexity: small
phase: "Phase 1 — Identity foundation"
status: done
labels: [backend, tooling, ops]
epic_branch: epic/PRD-005-rbac
plan: .agents/plans/PRD-005-rbac/completed/STORY-004-manage-users-cli.plan.md
report: .agents/reports/PRD-005-rbac/STORY-004-manage-users-cli.report.md
commit: 10e63fc
depends_on: [STORY-003]
blocks: [STORY-016]
skills: []
created: 2026-08-28
updated: 2026-08-28
---

# STORY-004: Bootstrap CLI — scripts/manage_users.py

## Description

As an operator, I want a CLI to create users, issue tokens, list them, and deactivate them, so that a deployment can be bootstrapped without user-management HTTP endpoints.

## Acceptance Criteria

- [ ] Given `python scripts/manage_users.py create-user --user-id ana --role user`, when it runs, then the row is created and the plaintext token is printed exactly once with a warning that it cannot be recovered
- [ ] Given `--role` is omitted, when a user is created, then the role is `RBAC_DEFAULT_ROLE`
- [ ] Given a role outside the known set, when `create-user` runs, then it exits non-zero with a message listing the valid roles
- [ ] Given `list-users`, when it runs, then it prints `user_id`, `role`, `active`, `created_at` — and never a token or a hash
- [ ] Given `deactivate-user --user-id ana`, when it runs, then that user's next `resolve()` returns `None`

## Technical Notes

- New `scripts/` directory; stdlib `argparse` only.
- The script imports `app.services.identity` and `app.db.database`, so it needs the repo root on `sys.path` — use the same `Path(__file__).resolve().parents[N]` pattern already in `chat_ui/chat_ui/chat_ui.py`.
- Call `init_db()` first so the script works against a fresh checkout with no database file.
- This CLI is the only administration surface in the MVP; user-management endpoints are explicitly out of scope (PRD Section 4).

## Dependencies

- **Blocked by**: STORY-003
- **Blocks**: STORY-016

## PRD Reference

Source: [`PRD-005/PRD.md`](../../PRDs/PRD-005-rbac/PRD.md) — sections 4 and 7
