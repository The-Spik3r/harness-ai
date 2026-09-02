---
id: STORY-008
prd: PRD-007
slug: startup-guard
title: "Fail fast and legibly when the database is unreachable or the token is missing"
type: feature
priority: high
complexity: small
phase: "2 - Storage layer swap"
status: done
labels: [backend, database, ops, reliability]
epic_branch: epic/PRD-007-turso-migration
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-008-startup-guard.plan.md
report: .agents/reports/PRD-007-turso-migration/STORY-008-startup-guard.report.md
commit: null
depends_on: [STORY-006]
blocks: [STORY-014]
skills: []
created: 2026-09-01
updated: 2026-09-01
---

# STORY-008: Fail fast and legibly when the database is unreachable or the token is missing

## Description

As a platform engineer, I want the application to exit immediately with a legible message when it cannot reach the database, so that a misconfigured deployment never serves traffic while silently dropping audit rows.

Under the old design an unreachable database was not a possible state — the file was either there or was created. Remote-pure access makes reachability a runtime condition, and the worst outcome is a container that boots, accepts queries, and fails only on the write path where `insert_audit_log()` is fire-and-forget from the pipeline's perspective. PRD Section 2: "A fallback that silently writes audit rows to a local file no one reads is worse than a failure."

## Acceptance Criteria

- [ ] Given an unreachable `DATABASE_URL`, when the application starts, then it fails at startup with a message identifying the database as the cause. It does not start and then fail per-request.
- [ ] Given an invalid or expired `TURSO_AUTH_TOKEN`, when the application starts, then it fails at startup with a message naming the setting.
- [ ] Given any startup failure message, when it is inspected, then it contains no token value or credential fragment.
- [ ] Given the FastAPI app and the Reflex app, when each is started independently, then both are covered. `init_db()` is called at import time by `chat_ui.chat_ui` (see [tests/test_admin_shell.py:697](../../../tests/test_admin_shell.py)), so the Reflex path fails at import; the FastAPI path must fail with equal clarity.
- [ ] Given a reachable database, when the application starts, then the guard adds no perceptible startup delay and issues at most one extra round trip.
- [ ] Given `tests/test_chat_ui_startup_guard.py`, when it runs, then it covers the unreachable-database case in the same subprocess style it already uses for its existing guard scenarios.
- [ ] Given the guard, when the database becomes unreachable **after** a successful start, then the guard does not re-fire — this story covers startup, not liveness. Runtime resilience is explicitly out of MVP scope (PRD Section 4, Section 13).

## Technical Notes

- Files: [app/db/database.py](../../../app/db/database.py) or a small guard in [app/main.py](../../../app/main.py); `chat_ui/chat_ui/` startup path; `tests/test_chat_ui_startup_guard.py`.
- There is precedent to follow. `tests/test_chat_ui_startup_guard.py` already exists from PRD-005 and tests a startup guard by launching a subprocess with a controlled environment ([line 65](../../../tests/test_chat_ui_startup_guard.py)). Extend that pattern rather than inventing a new one.
- Distinguish the two failures in the message. "Cannot reach the database at `<endpoint>`" and "TURSO_AUTH_TOKEN rejected" send an operator to different places. A single generic "database error" wastes their time.
- The configuration-shape failures — `sqlite:///` URL, unset URL, missing token for a remote endpoint — are already handled by [[STORY-005]] at validation time and do not need repeating here. This story covers the cases only a live connection attempt can detect.
- Note the ordering constraint against [[STORY-014]]: the Docker build imports `chat_ui.chat_ui` during `reflex export`, and PRD Section 11 requires "The Docker build succeeds without a reachable database." A guard that runs unconditionally at import will break the build. Handle that here or confirm [[STORY-014]] does, and say which in the report.
- PRD Section 10 records the deliberate consequence: "when the database is unreachable, endpoints that previously could not fail on storage now can. Each failure mode is mapped to a defined status code." The existing degradation path at [app/services/duplicate_checker.py:32](../../../app/services/duplicate_checker.py) is preserved, not replaced by a 500.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story renders no UI. No skill applies.

## Dependencies

- **Blocked by**: STORY-006
- **Blocks**: STORY-014

## PRD Reference

Source: [`PRD-007/PRD.md`](../../PRDs/PRD-007-turso-migration/PRD.md) — Section 5 story 3, Section 7.7, Section 10, Section 11, Section 12 Phase 2, Section 14 Risk 5
