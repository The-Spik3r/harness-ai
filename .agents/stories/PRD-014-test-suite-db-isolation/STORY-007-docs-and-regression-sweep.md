---
id: STORY-007
prd: PRD-014
slug: docs-and-regression-sweep
title: "README and conftest docstring for the db split, plus a three-run regression sweep"
type: technical
priority: medium
complexity: small
phase: "4 - Document and prove"
status: done
labels: [docs, tests, regression]
epic_branch: epic/PRD-014-test-suite-db-isolation
plan: .agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-007-docs-and-regression-sweep.plan.md
report: .agents/reports/PRD-014-test-suite-db-isolation/STORY-007-docs-and-regression-sweep.report.md
commit: 57a534c
depends_on: [STORY-003, STORY-004, STORY-005, STORY-006]
blocks: []
skills: []
created: 2026-10-20
updated: 2026-10-21
---

# STORY-007: Documentation and regression sweep

## Description

As a harness developer reading the README, I want to know how to run the suite with and without Docker and how to read a diagnostics section, so that I use the split and trust a red run.

## Acceptance Criteria

- [ ] Given README *Running Tests*, when read, then it documents `pytest tests/` (everything, the default, needs Docker), `pytest tests/ -m "not db"` (no Docker) and `pytest tests/ -m db`. It explains what the guard's failure means and the three ways to resolve it, shows an example `libsql diagnostics` section, and says what each verdict means and what to do about it. The existing in-container overrides and their warnings are unchanged.
- [ ] Given `tests/conftest.py`'s module docstring, when read, then "Where isolation comes from now" describes the marker, the `db`-only reset, the guard and the lazy endpoint, without stating that every test is reset.
- [ ] Given three consecutive full runs, when they complete, then each run's counts are recorded and equal STORY-001's baseline, apart from flakes. Every failure, if any, carries `libsql verdict: likely infrastructure`. A failure with `no infrastructure signal` is a defect that blocks the story.
- [ ] Given STORY-001's scratch plugin rerun once on the final tree, when the driver-call count is compared, then non-`db` tests issue 0 calls and the total per run is recorded beside STORY-001's figure.
- [ ] Given PRD Section 11, when this story's report is written, then every checkbox is ticked with a pointer to the evidence (story report, command output, or test name). `git diff main` over the six PRD-006 suites is empty, and no file under `app/` or `chat_ui/` changed across the epic.

## Technical Notes

- Mirror the README's existing tone: commands first, then a "why" paragraph per caveat.
- If STORY-006 concluded **confirmed**, the README gains a short "if `db` tests flake on Docker Desktop" paragraph pointing at the in-network recipe. Anything more belongs in STORY-008.
- `grep -rn "_never_the_configured_database\|every test starts on an empty database" tests README.md` should return nothing stale.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-003, STORY-004, STORY-005, STORY-006
- **Blocks**: None

## PRD Reference

Source: [`PRD-014-test-suite-db-isolation/PRD.md`](../../PRDs/PRD-014-test-suite-db-isolation/PRD.md) — sections 4 (Documentation), 7 (F7), 10, 11, 12 (Phase 4)
