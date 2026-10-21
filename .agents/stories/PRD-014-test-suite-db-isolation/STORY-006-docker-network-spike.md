---
id: STORY-006
prd: PRD-014
slug: docker-network-spike
title: "Spike: run the db tests from inside the Docker network vs the host to test the port-forwarding hypothesis (D5)"
type: spike
priority: medium
complexity: small
phase: "3 - Diagnose and investigate"
status: done
labels: [spike, docker, libsql, infrastructure]
epic_branch: epic/PRD-014-test-suite-db-isolation
plan: .agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-006-docker-network-spike.plan.md
report: .agents/reports/PRD-014-test-suite-db-isolation/STORY-006-docker-network-spike.report.md
commit: f905425
depends_on: [STORY-005]
blocks: [STORY-007, STORY-008]
skills: []
created: 2026-10-20
updated: 2026-10-21
---

# STORY-006: Spike: stalls inside the Docker network (D5)

## Description

As the owner of the local environment, I want to know whether Docker Desktop's Windows port forwarding causes the 7–21 s connection stalls, so that the follow-up (move the server, add a scoped retry, or accept it) rests on a measurement.

## Acceptance Criteria

- [ ] Given `harness-libsql-dev` attached to a user network `harness-test-net`, when `pytest tests/ -m db -q -rA` runs three times from the `harness-ai` image on that network with `HARNESS_TEST_LIBSQL_URL` and `DATABASE_URL` set to `http://harness-libsql-dev:8080` and `TURSO_AUTH_TOKEN=` empty, then each run's counts, failures and verdict lines are recorded.
- [ ] Given the same session, when `pytest tests/ -m db -q -rA` runs three times from the host against `http://127.0.0.1:8080` (control arm), then the same figures are recorded.
- [ ] Given both arms, when the STORY-005 recorder's data is summarized, then the report counts per run calls ≥ 10 s, `STREAM_EXPIRED` and `os error 10060` events (including stalls absorbed by `_reset_database()`'s retry, not only failures).
- [ ] Given those counts, when concluded, then `.agents/spikes/PRD-014-docker-network-stalls.md` states one of **confirmed** (zero stalls in-network and at least one on the host), **refuted** (in-network stalls at a comparable rate) or **inconclusive** (zero in both arms: repeat up to three more host runs, then record that it could not be reproduced). The conclusion and a one-paragraph recommendation for STORY-008 are copied into PRD Appendix "D5 result".
- [ ] Given the story's diff, when reviewed, then it contains the spike report, the PRD appendix update and at most a helper script. No test or app code changes. The containers and network are left as they were found, or the report says what was left.

## Technical Notes

- Recipe in PRD Section 12, Phase 3. The image already contains `en_core_web_lg`. Add `--add-host` only if the image needs host access, which it shouldn't here.
- Getting recorder data out: the diagnostics section appears only on failures. For absorbed stalls, run both arms with an extra uncommitted `-p` plugin (STORY-001's scratch plugin adapted) that dumps every recorded call ≥ 10 s and every driver error to a JSONL file in the mounted repo. Or, if STORY-005's recorder exposes its records, use a `pytest_sessionfinish` dump from that plugin.
- The repo lives under OneDrive. Bind-mounting it into a container may be slow or hit path issues (see the test-env memory: MAX_PATH). If the mount is impractical, `docker cp` a clean checkout into a named volume and record the deviation.
- Run the arms interleaved (in-net, host, in-net, …) so time-of-day drift affects both.
- The 15 s duration of stalled calls is out of scope (PRD Section 4). Note it if a run reveals something, but don't trace it.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-005
- **Blocks**: STORY-007, STORY-008

## PRD Reference

Source: [`PRD-014-test-suite-db-isolation/PRD.md`](../../PRDs/PRD-014-test-suite-db-isolation/PRD.md) — sections 7 (F6), 11 (Quality indicators), 12 (Phase 3), 13, Appendix D5
