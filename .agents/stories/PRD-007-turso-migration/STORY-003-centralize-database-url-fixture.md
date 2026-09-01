---
id: STORY-003
prd: PRD-007
slug: centralize-database-url-fixture
title: "Centralize the 27 DATABASE_URL test sites behind one conftest fixture, still SQLite-backed"
type: technical
priority: high
complexity: medium
phase: "1 - Driver verification and behavior pinning"
status: todo
labels: [tests, infra, database]
epic_branch: epic/PRD-007-turso-migration
plan: null
report: null
commit: null
depends_on: []
blocks: [STORY-006]
skills: []
created: 2026-09-01
updated: 2026-09-01
---

# STORY-003: Centralize the 27 DATABASE_URL test sites behind one conftest fixture, still SQLite-backed

## Description

As a maintainer, I want every test that provisions a database to obtain its `DATABASE_URL` from a single fixture, so that the driver swap in [[STORY-006]] flips one implementation instead of editing 27 sites across 19 files while the suite is red.

Today the idiom is copy-pasted: `monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")` appears 27 times across 19 files, plus two variants that pass the URL into a **subprocess environment** rather than into `settings`. This story changes no behavior and no production code — it introduces the indirection while everything is still SQLite, so the commit is green and the risky change lands later in isolation.

## Acceptance Criteria

- [ ] Given `tests/conftest.py`, when a test requests the shared database fixture, then it receives an isolated, empty database and `settings.DATABASE_URL` is patched to point at it for the duration of that test. Isolation is per-test: no test observes rows written by another.
- [ ] Given the two subprocess call sites — [tests/test_admin_shell.py:709](../../../tests/test_admin_shell.py) and [tests/test_chat_ui_startup_guard.py:65](../../../tests/test_chat_ui_startup_guard.py) — when they launch their subprocess, then they obtain the same URL from the same fixture and pass it through the child environment. These two must not keep their own hand-built `sqlite:///` strings.
- [ ] Given the whole suite, when `grep -rn "sqlite:///" tests/` runs, then the only production-facing occurrence is inside `tests/conftest.py`. Assertions that deliberately test the *rejection* of a `sqlite:///` URL are exempt and, if any exist, are named in the story report.
- [ ] Given the fixture, when a test needs a database whose schema was never initialized (the `users`-table-missing case from [[STORY-002]]), then the fixture supports that without the test hand-rolling its own connection.
- [ ] Given the full suite, when it runs after this change, then it passes with the same result as before, and no test's own assertions were weakened or deleted to achieve it.
- [ ] Given `git diff main --stat`, when it is inspected, then no file under `app/`, `chat_ui/`, or `scripts/` is modified.

## Technical Notes

- Files: new or extended `tests/conftest.py`, plus the 19 test files listed by `grep -rln "sqlite:///" tests/`: `test_admin_shell`, `test_audit_logger`, `test_audit_router`, `test_auth_dependencies`, `test_chat_state`, `test_chat_ui_startup_guard`, `test_db`, `test_duplicate_checker`, `test_identity`, `test_integration`, `test_main`, `test_manage_users_cli`, `test_pii_dedup_isolation`, `test_pii_redaction_integration`, `test_query_pipeline_authorization`, `test_query_router`, `test_rbac`, `test_render_invariants`, `test_stats_router`.
- Several files hold more than one site — `test_db.py` has six, and `test_duplicate_checker.py`, `test_identity.py`, `test_rbac.py`, `test_render_invariants.py` have two each. Do not assume one per file.
- **The fixture's return value is the seam.** Design it to yield a URL string, not a filesystem path. A fixture that yields a `Path` bakes the file assumption into 19 files and defeats the purpose of this story.
- Preserve each existing fixture's local setup. Several files do more than set the URL — [tests/test_chat_state.py:61](../../../tests/test_chat_state.py) and `tests/test_db.py` open connections to seed rows. Those keep working; this story changes where the URL comes from, not what the tests do with it.
- The comment at [tests/test_admin_shell.py:697](../../../tests/test_admin_shell.py) records why that file pins the URL at all: "importing `chat_ui.chat_ui` calls `init_db()` at import time." That constraint is unchanged and the fixture must satisfy it before the import happens.
- PRD Section 2: "Tests stay hermetic and stay green ... They must keep running offline, per-test isolated, and without a Turso account." This story establishes the first two properties while SQLite still provides them for free, so that [[STORY-006]] only has to preserve them.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story touches tests only. No skill applies.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-006

## PRD Reference

Source: [`PRD-007/PRD.md`](../../PRDs/PRD-007-turso-migration/PRD.md) — Section 4 (test infrastructure), Section 7.6, Section 12 Phase 1, Section 14 Risk 4
