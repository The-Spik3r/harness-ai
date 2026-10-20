---
id: STORY-008
prd: PRD-014
slug: d5-follow-up
title: "(Conditional on D5) Act on the spike: in-network test recipe, or a rerun policy scoped to infrastructure failures"
type: technical
priority: low
complexity: small
phase: "4 - Document and prove"
status: todo
labels: [tests, docker, conditional]
epic_branch: epic/PRD-014-test-suite-db-isolation
plan: null
report: null
commit: null
depends_on: [STORY-006]
blocks: []
skills: []
created: 2026-10-20
updated: 2026-10-20
---

# STORY-008: Act on the D5 result

## Description

As a harness developer on Windows + Docker Desktop, I want the follow-up the spike points to, so that `db` tests either stop stalling or stop costing a manual rerun.

**This story is conditional.** `/plan` reads PRD Appendix "D5 result" first. If the spike recommends no further action, close the story as `done` with a one-line report citing the spike, and no code.

## Acceptance Criteria

- [ ] Given D5 **confirmed**, when this story lands, then a committed script (e.g. `scripts/test-db-in-network.sh`) runs `-m db` from the `harness-ai` image on `harness-test-net`, creating the network idempotently. README *Running Tests* documents it, and one run of the script is recorded green in the report.
- [ ] Given D5 **refuted** or stalls unavoidable on Docker Desktop, when this story lands, then `pytest-rerunfailures` is pinned in `requirements.txt` and applied only to `db` tests. Only failures matching `STREAM_EXPIRED|os error 10060` are rerun, at most once. The first attempt's `libsql diagnostics` section stays visible in the output. A `pytester` self-test shows a non-matching `db` failure is **not** rerun and a non-`db` failure is never rerun.
- [ ] Given **inconclusive**, when this story is planned, then it is closed `done` with the decision recorded, or left `blocked` with the reason. Nothing is implemented on an unproven hypothesis.
- [ ] Given whichever arm is implemented, when the full suite runs, then counts equal STORY-001's baseline and no file under `app/` or `chat_ui/` changes.

## Technical Notes

- The rerun arm reverses D4's "no retry for now", so its report must quote the spike's numbers as justification.
- Scoping the rerun to `db` tests: rather than a global `--only-rerun` in an ini file, apply `@pytest.mark.flaky(reruns=1, only_rerun=[...])` from `pytest_collection_modifyitems` to `db` items. Check the plugin version's marker kwargs with context7 before writing it.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-006
- **Blocks**: None

## PRD Reference

Source: [`PRD-014-test-suite-db-isolation/PRD.md`](../../PRDs/PRD-014-test-suite-db-isolation/PRD.md) — sections 7 (F8), 13, Appendix D4, D5
