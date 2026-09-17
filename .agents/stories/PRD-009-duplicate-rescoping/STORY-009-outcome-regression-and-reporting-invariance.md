---
id: STORY-009
prd: PRD-009
slug: outcome-regression-and-reporting-invariance
title: "Six-outcome regression and /audit, /stats and admin-console invariance verified on the finished epic"
type: technical
priority: medium
complexity: small
phase: "4 - Regress and document"
status: todo
labels: [backend, tests, audit]
epic_branch: epic/PRD-009-duplicate-rescoping
plan: null
report: null
commit: null
depends_on: [STORY-008]
blocks: [STORY-010]
skills: []
created: 2026-09-16
updated: 2026-09-16
---

# STORY-009: Six-outcome regression and /audit, /stats and admin-console invariance verified on the finished epic

## Description

As an integrating developer and a compliance admin, I want proof that `POST /query`'s outcomes and every reporting surface are unchanged by the rescoping, so that nothing built against the API and no historical figure moved.

## Acceptance Criteria

- [ ] Given `tests/test_query_outcomes_regression.py`, when `git diff <STORY-001 commit>..HEAD -- tests/test_query_outcomes_regression.py` is run, then it is empty, and the module passes on the epic branch head.
- [ ] Given the same diff over [tests/test_query_router.py](../../../tests/test_query_router.py) and [tests/test_integration.py](../../../tests/test_integration.py) since the epic's base, when it is reviewed, then the only changes are spy wrapper signatures (PRD Section 6.5). No status-code, body or row-count assertion changed. The report lists each hunk.
- [ ] Given a fixed set of seeded rows (successes, both blocks, denials, failures, two users), when `GET /stats`, `GET /audit` and `summary_snapshot()` are read, then a new invariance test asserts `blocked_duplicates` counts exactly the `was_duplicate_blocked = 1` rows. `AuditQueryEntry` has no `dedup_key` field, and every new row's `prompt_hash == hash_prompt(prompt)`.
- [ ] Given [tests/test_two_instance_smoke.py](../../../tests/test_two_instance_smoke.py), when it runs (or is skipped under its own documented conditions), then it passes **unmodified**, including `prompt_hash == hash_prompt(prompt_preview)`.
- [ ] Given a spy on the libSQL client's `execute` during one successful `/query`, when the statements are counted, then there is exactly one duplicate-lookup statement and one audit insert, the same as before the epic (no added round trip, per the PRD Section 11 quality indicators). The full suite is green.

## Technical Notes

- This is a verification story. Production changes here mean an earlier story regressed; fix that in a separate commit on the epic branch and name it in the report.
- The admin console reads through `summary_snapshot()`. [chat_ui/chat_ui/admin_state.py](../../../chat_ui/chat_ui/admin_state.py) treats denials as `success=True`, which is unchanged since this PRD rewrites no row.
- For the round-trip count, follow `test_stats_issues_one_database_round_trip_for_its_figures` in [tests/test_stats_router.py](../../../tests/test_stats_router.py).
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-008
- **Blocks**: STORY-010

## PRD Reference

Source: [`PRD-009-duplicate-rescoping/PRD.md`](../../PRDs/PRD-009-duplicate-rescoping/PRD.md) — sections 5 (stories 6, 7), 10, 11 (six outcomes, quality indicators), 12 (Phase 4)
