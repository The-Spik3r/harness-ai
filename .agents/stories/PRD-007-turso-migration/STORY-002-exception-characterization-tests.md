---
id: STORY-002
prd: PRD-007
slug: exception-characterization-tests
title: "Characterization tests pinning the three driver-exception behaviors against current SQLite"
type: technical
priority: high
complexity: small
phase: "1 - Driver verification and behavior pinning"
status: done
labels: [backend, database, tests, rbac]
epic_branch: epic/PRD-007-turso-migration
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-002-exception-characterization-tests.plan.md
report: .agents/reports/PRD-007-turso-migration/STORY-002-exception-characterization-tests.report.md
commit: 403b191
depends_on: []
blocks: [STORY-004]
skills: []
created: 2026-09-01
updated: 2026-09-01
---

# STORY-002: Characterization tests pinning the three driver-exception behaviors against current SQLite

## Description

As a maintainer, I want the three behaviors that currently depend on `sqlite3` exception types pinned by tests **before** the driver changes, so that the swap in [[STORY-006]] is measured against a green baseline rather than against my memory of what the code did.

Three sites catch stdlib SQLite exceptions and will silently stop matching once the driver changes. A `except sqlite3.OperationalError` that no longer fires does not raise — it lets the exception escape, and one of these three converts a 401 into a 500 on the login path.

## Acceptance Criteria

- [ ] Given a database whose `users` table does not exist, when `find_user_by_token_hash(...)` is called, then it returns `None` rather than raising — pinning [app/db/database.py:289](../../../app/db/database.py). A companion test asserts the endpoint-level consequence: the request resolves to **401, not 500**.
- [ ] Given a storage failure during the duplicate check, when the query pipeline runs, then the query still completes rather than failing — pinning the `except sqlite3.Error` arm at [app/services/duplicate_checker.py:32](../../../app/services/duplicate_checker.py).
- [ ] Given an existing `user_id`, when `scripts/manage_users.py` is asked to create it again, then the CLI reports a duplicate-user error rather than a traceback — pinning [scripts/manage_users.py:37](../../../scripts/manage_users.py).
- [ ] Given an existing `token_hash` on a different `user_id`, when the CLI creates a user with it, then the duplicate-credential case is reported **distinguishably** from the duplicate-`user_id` case. `app/db/database.py`'s own docstring on `insert_user()` states the reason: the caller "needs to tell those two cases apart."
- [ ] Given these new tests, when they run on `main` with no production changes, then all pass. A characterization test that needs a code change to go green is describing a bug, not a baseline — stop and raise it.
- [ ] Given `git diff main --stat`, when it is inspected, then only files under `tests/` are modified.

## Technical Notes

- Files: `tests/` only. The three behaviors span existing suites — `tests/test_db.py`, `tests/test_auth_dependencies.py` / `tests/test_rbac.py`, `tests/test_duplicate_checker.py`, and `tests/test_manage_users_cli.py` are the natural homes. Prefer extending the existing file for each behavior over creating a new one.
- The 401-not-500 behavior is not a convenience. PRD-005 Section 9 treats it as a credential-enumeration control, and the docstring at [app/db/database.py](../../../app/db/database.py) states it directly: "A revoked credential is indistinguishable from an unknown one by design ... separating them would be a credential-enumeration oracle." The `users`-table-missing case is folded into the same closed door.
- Write the assertions against **observable behavior**, not against the exception type. A test that asserts `sqlite3.OperationalError` is raised somewhere will itself need rewriting in [[STORY-004]] and is worthless as a baseline. Assert the return value, the status code, and the CLI output.
- Follow the existing fixture idiom for now — `monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")` with `tmp_path`, as used across the suite. [[STORY-003]] centralizes that; do not pre-empt it here.
- To reach "the `users` table does not exist", note that `init_db()` creates it. The existing test at [app/db/database.py](../../../app/db/database.py) `find_user_by_token_hash()` describes the condition as "`init_db()` never ran against this connection" — construct the database without it.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design. This story touches no UI. No skill applies.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-004

## PRD Reference

Source: [`PRD-007/PRD.md`](../../PRDs/PRD-007-turso-migration/PRD.md) — Section 6 Pattern 6 (errors owned by the module), Section 11 (functional requirements), Section 12 Phase 1
