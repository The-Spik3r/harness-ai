---
id: STORY-015
prd: PRD-017
slug: success-criteria-suite-and-latency
title: In-process success-criteria suite for tool calling; step 7c latency measured
type: technical
priority: high
complexity: medium
phase: "4 - Real clients and docs"
status: done
labels: [tests, security]
epic_branch: epic/PRD-017-tool-calling
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-015-success-criteria-suite-and-latency.plan.md
report: .agents/reports/PRD-017-tool-calling/STORY-015-success-criteria-suite-and-latency.report.md
commit: null
depends_on: [STORY-012, STORY-013]
blocks: [STORY-016, STORY-018]
skills: []
created: 2026-11-15
updated: 2026-11-16
---

# STORY-015: In-process success-criteria suite for tool calling; step 7c latency measured

## Description

As a security admin, I want the brief's success criteria proven in the everyday suite, without a real client, so that a regression in any of them fails the build rather than an opt-in E2E run.

## Acceptance Criteria

- [ ] Given a new `tests/test_tool_calling_criteria.py` driving `/v1` through `TestClient` with `V1_TOOLS_ENABLED=true` and an injected upstream, when it runs, then: a model `DROP TABLE` (via `bash` `sqlite3` and via a mapped SQL tool) is denied, recorded with the request's `audit_id`, and the response's content carries the reason, streamed and not; a mixed response releases only the allowed calls.
- [ ] Given PII-looking, unicode and escape-heavy arguments, when sent in history and returned by the upstream, then they are byte-identical at the upstream and at the client (non-streamed and streamed) — "no tool-call argument is modified by any check".
- [ ] Given one session that runs `npm test`, edits a file and runs `npm test` again, when every request of the loop is sent, then none is held as a duplicate; a byte-identical resend of one request is.
- [ ] Given `evaluate_all` monkeypatched to deny everything, when any tool response is produced, then neither response shape contains a call (T1); with the flag off, the PRD-015 `tools_not_supported` behaviour holds.
- [ ] Given the PRD-016 synthetic corpus, when step 7c (`evaluate_all` + `apply_decisions`) is timed per response of ≤ 8 calls, then p50/p95 are recorded in the report (target p95 < 5 ms), measured by a script in the existing `scripts/measure_*_latency.py` style if a reusable one fits.

## Technical Notes

- Orchestrator note (STORY-001): Cline re-stringifies history `arguments` with `JSON.stringify`, so a history string may differ in whitespace from what the upstream sent earlier. "Not modified by any check" is a harness property: assert the harness forwards exactly the bytes it received, in each direction, not that a client round-trip is stable.
- Reuse the fixtures of `tests/test_v1_router.py` / `tests/test_v1_tools.py` (identity, DB isolation from PRD-014, `app.routers.v1.call_openrouter` replacement).
- Corpus: `tests/corpora/actions/synthetic/`; loader in `tests/test_action_corpus.py`.
- Map each test to the brief's success criterion it proves in its docstring (PRE-PRD-016 "Success criteria"; PRD-017 Section 11).
- `test_pii_redaction_integration.py` has a census of tests; register anything it asks for.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-012, STORY-013
- **Blocks**: STORY-016, STORY-018

## PRD Reference

Source: [`PRD-017-tool-calling/PRD.md`](../../PRDs/PRD-017-tool-calling/PRD.md) — sections 9.2 (T1, T2), 11 (MVP, Functional, Quality)
