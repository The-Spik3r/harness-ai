---
id: STORY-017
prd: PRD-013
slug: two-instance-limits-and-latency
title: "Two-instance limit test and latency measurement"
type: technical
priority: high
complexity: medium
phase: "4 - See it and prove it"
status: todo
labels: [backend, tests, limits, performance]
epic_branch: epic/PRD-013-audit-and-usage-limits
plan: null
report: null
commit: null
depends_on: [STORY-012]
blocks: [STORY-018]
skills: []
created: 2026-10-04
updated: 2026-10-04
---

# STORY-017: Two-instance limit test and latency measurement

## Description

As a compliance admin, I want proof that limits hold across instances and a measured cost for checking them, so that adding a container is not a way to double a budget and the latency is known before deployment.

## Acceptance Criteria

- [ ] Given two application processes on one database and a user with a rate limit of 5, when 10 requests alternate between the processes within one minute, then exactly 5 are admitted and 5 return the usage-limit body.
- [ ] Given a user whose budget is exhausted by requests through instance A, when the next request goes to instance B, then it is refused with `limit="tokens"`.
- [ ] Given a second user during both scenarios, when they send through either instance, then they are admitted.
- [ ] Given `python scripts/measure_usage_latency.py`, when it runs against the local libSQL dev server, then it prints p50 and p95 for `admit` and for `charge` over a stated number of runs, and the story report records those numbers plus one run against a remote endpoint (or states that none was available).
- [ ] Given the existing two-instance smoke scenarios, when the file runs, then they pass with no assertion changed.

## Technical Notes

- Extend `tests/test_two_instance_smoke.py`; reuse its process start-up and stub-upstream arrangement. Set limits through the environment of both processes or with `set_user_limits`.
- The rate scenario must not straddle a minute boundary or it will flake: check the database's current second first and wait for a fresh window if fewer than about 15 seconds remain, or insert the window row explicitly.
- `scripts/measure_usage_latency.py` sits beside `measure_history_latency.py` and follows its environment bootstrap (`os.environ.setdefault` for the required settings). It times the two service calls only, not the pipeline.
- The numbers go to the story report here and into the README in STORY-018.
- If STORY-009 shipped the two-statement fallback, this is where its cost becomes visible; say which variant was measured.
- Skills: none applicable. No UI surface changes in this story.

## Dependencies

- **Blocked by**: STORY-012
- **Blocks**: STORY-018

## PRD Reference

Source: [`PRD-013-audit-and-usage-limits/PRD.md`](../../PRDs/PRD-013-audit-and-usage-limits/PRD.md) — sections 7 (F17), 9.2 (T5), 11 (Cross-instance and latency), 14 (Risks 1, 2)
