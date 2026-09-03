---
id: STORY-016
prd: PRD-007
slug: two-instance-smoke-test
title: "Prove two instances share one database: concurrent writes, cross-instance duplicate detection, no lost rows"
type: technical
priority: high
complexity: medium
phase: "4 - Data migration and cutover"
status: done
labels: [tests, integration, concurrency, deployment]
epic_branch: epic/PRD-007-turso-migration
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-016-two-instance-smoke-test.plan.md
report: .agents/reports/PRD-007-turso-migration/STORY-016-two-instance-smoke-test.report.md
commit: 153d2f3
depends_on: [STORY-007, STORY-014]
blocks: []
skills: []
created: 2026-09-01
updated: 2026-09-02
---

# STORY-016: Prove two instances share one database: concurrent writes, cross-instance duplicate detection, no lost rows

## Description

As a platform engineer, I want two application instances proven to run correctly against one database, so that the epic's stated goal — scaling past one container — is demonstrated rather than assumed.

Multi-instance is one of the two reasons this PRD exists. Every other story removes a blocker; this one is the evidence that the blocker is actually gone. PRD Section 5 story 2: "A duplicate prompt sent to instance A is detected by instance B within the detection window, because both read the same `audit_logs` table."

## Acceptance Criteria

- [ ] Given two application instances against one database, when both start simultaneously, then both boot successfully and the schema is correct — the end-to-end form of [[STORY-007]]'s convergent `init_db()`.
- [ ] Given a prompt submitted to instance A, when the same prompt is submitted to instance B inside the detection window, then B blocks it as a duplicate. Cross-instance duplicate detection is the sharpest observable proof that the two share state.
- [ ] Given concurrent query traffic to both instances, when it completes, then every query produced exactly one `audit_logs` row — none lost, none duplicated.
- [ ] Given a user created through `scripts/manage_users.py` while both instances are running, when that user authenticates against either instance, then the credential resolves. `find_user_by_token_hash(...)` reads the shared `users` table, so a stale per-instance cache would show up here.
- [ ] Given a user deactivated through the CLI, when they attempt to authenticate against **both** instances, then both reject them. Revocation that only takes effect on one instance is a security failure, not a caching quirk.
- [ ] Given concurrent writes from both instances, when the audit trail is read afterward, then `audit_logs.id` values are unique and no row is corrupted.
- [ ] Given the test, when it runs in CI, then it is deterministic and does not depend on a hosted Turso database — the local libSQL server from [[STORY-003]] / [[STORY-006]] serves as the shared endpoint.
- [ ] Given the results, when they are recorded, then the report states the measured round-trip cost of a `POST /query` and an admin console load, closing PRD Section 12 Phase 3's "Measured round-trip counts" deliverable with real numbers.

## Technical Notes

- Files: a new integration test module under `tests/`. Follow the shape of [tests/test_integration.py](../../../tests/test_integration.py), which already exercises the full pipeline.
- Two real processes, not two threads in one interpreter. The failure modes this story targets — a per-process client cache, a per-process schema assumption, an import-time `init_db()` race — only appear across process boundaries. `tests/test_admin_shell.py` and `tests/test_chat_ui_startup_guard.py` already launch subprocesses with a controlled environment; reuse that machinery.
- The duplicate-detection window is time-based. `find_duplicate_timestamp(prompt_hash, since)` in [app/db/database.py](../../../app/db/database.py) filters on `timestamp >= since`, so the test must control the window rather than race it. A flaky duplicate test will be deleted by someone in six months, which is worse than not writing it.
- Note the standing performance caveat while measuring: `audit_logs` has **no index** on `prompt_hash` or `timestamp`, so `find_duplicate_timestamp` scans. PRD Section 13 flags this as worth measuring once real data is in Turso. If the numbers are bad at realistic volume, that is a finding for a follow-up story, not a reason to add an index here — PRD Section 4 puts new indexes out of scope.
- Revocation is worth testing precisely because [[STORY-006]] introduced a shared, long-lived client. Confirm no layer caches identity resolution across requests; if one does, that is a security finding to raise immediately rather than to work around in the test.
- This story is the epic's exit criterion. If it does not pass, the migration is not done regardless of what the other fifteen stories say.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story is an integration test. No skill applies.

## Dependencies

- **Blocked by**: STORY-007, STORY-014
- **Blocks**: None

## PRD Reference

Source: [`PRD-007/PRD.md`](../../PRDs/PRD-007-turso-migration/PRD.md) — Section 5 story 2, Section 11 (MVP definition), Section 12 Phase 3 & Phase 4, Section 13
