---
id: STORY-019
prd: PRD-015
slug: regression-latency-and-docs
title: "Regression sweep, translation latency, README API reference and per-client setup, .env.example"
type: technical
priority: high
complexity: medium
phase: "4 - Real clients, deployment, documentation"
status: todo
labels: [docs, tests, regression]
epic_branch: epic/PRD-015-openai-compatible-endpoint
plan: null
report: null
commit: null
depends_on: [STORY-008, STORY-015, STORY-016, STORY-017, STORY-018]
blocks: []
skills: []
created: 2026-10-21
updated: 2026-10-21
---

# STORY-019: Regression sweep, translation latency, README API reference and per-client setup, .env.example

## Description

As a platform operator and integrating developer, I want the README to describe `/v1` as shipped (how to point each client at it, what each error means, what it does not do) and the existing behaviour proven unchanged, so that I can adopt it from the documentation alone.

## Acceptance Criteria

- [ ] Given the full suite (`-m "not db"` without Docker, then with the libSQL container), when it runs, then the `/query` outcome regression, chat UI regression, console suites and `tests/test_v1_query_isolation.py` pass with no pre-existing assertion changed except those listed in STORY-008's report.
- [ ] Given a measurement script run against the stub upstream (50 runs, the same conversation via `/query` and via `/v1`), when it reports, then `/v1`'s added p95 overhead is recorded in the README; under 10 ms meets the PRD target, and a miss is recorded as such, not hidden.
- [ ] Given the README, when it is read, then "OpenAI-compatible endpoint" has moved from Roadmap > Planned to Features; the API Reference has `POST /v1/chat/completions` (success, streamed, every error code in PRD Section 7.5), `GET /v1/models`; per-client setup for the OpenAI SDK, Aider and Continue uses the settings proven in STORIES 015–017; and the "what `/v1` does not do" list (tools, real streaming, BYOK, aliasing, the admin wildcard in `/v1/models`) is stated plainly.
- [ ] Given the README sections that say `code` or the `assistant`/`tool` flag are "reachable by tests only" or that `/v1` "will" exist (Pattern policy, PII redaction, Usage limits), when read, then they describe the shipped state, including `assistant: flag` (D9).
- [ ] Given `.env.example`, when read, then `OPENROUTER_BASE_URL`, `V1_ENABLED` and `V1_SSE_KEEPALIVE_SECONDS` are present with defaults and one-line explanations, and `OPENROUTER_BASE_URL` notes the T10 rule.

## Technical Notes

- Measurement script `scripts/measure_v1_latency.py`, modelled on `scripts/measure_usage_latency.py`; test it like `tests/test_measure_usage_latency.py`.
- README references the PRD for design detail, as PRD-013's section does ("The full design ... is in PRD-015"). Mention once that earlier documents call this PRD "PRD-014".
- Point the `code`-profile rollout note at [PRD-012 D5-placeholders](../../PRDs/PRD-012-pii-for-code/decisions/D5-placeholders.md) (fixed placeholders in files an agent reads).
- Update `pre-prds/README.md` milestones: Milestone 1 reached.
- Set PRD `status` and regenerate `index.md` per the workflow.
- Skills: none applicable. No UI change.

## Dependencies

- **Blocked by**: STORY-008, STORY-015, STORY-016, STORY-017, STORY-018
- **Blocks**: None

## PRD Reference

Source: [`PRD-015-openai-compatible-endpoint/PRD.md`](../../PRDs/PRD-015-openai-compatible-endpoint/PRD.md) — sections 10, 11 (Quality indicators), 12 (Phase 4), 13
