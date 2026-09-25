---
id: STORY-009
prd: PRD-012
slug: pipeline-pii-per-policy
title: "Pipeline steps 6 and 8 redact per the resolved policy"
type: feature
priority: high
complexity: medium
phase: "3 - Policy into the pipeline"
status: in-progress
labels: [backend, pii, pipeline]
epic_branch: epic/PRD-012-pii-for-code
plan: .agents/plans/PRD-012-pii-for-code/STORY-009-pipeline-pii-per-policy.plan.md
report: null
commit: null
depends_on: [STORY-002, STORY-007, STORY-008]
blocks: [STORY-010, STORY-012, STORY-013]
skills: []
created: 2026-09-23
updated: 2026-09-25
---

# STORY-009: Pipeline steps 6 and 8 redact per the resolved policy

## Description

As an integrating developer, I want `run_conversation(profile="code")` to apply the `code` PII policy on input and to leave the model's output unmasked, so that my agent's context is protected without placeholders being written into my files.

## Acceptance Criteria

- [ ] Given `run_conversation` with no `profile` (the `/query` and chat UI path), when it runs, then step 6 calls `redact()` for every message and step 8 redacts the response, and `test_pii_characterization.py`, `test_pii_redaction_integration.py` and `test_query_outcomes_regression.py` pass with no assertion changed.
- [ ] Given `profile="code"`, when a conversation has `system`, `user` and `assistant` turns, then the `system` turn reaches `call_openrouter` byte-identical, and `user` and `assistant` turns go through `redact_for_policy` with the `code` policy.
- [ ] Given `profile="code"` and a response containing `alice@example.com`, when it runs, then the returned response is unchanged and the audit row has `pii_detected_output=0`; with `PII_CODE_REDACT_OUTPUT=true`, it is masked and `pii_detected_output=1`.
- [ ] Given either profile, when history turns carry PII, then only the last user turn's entities (plus output entities, when output is redacted) are recorded in `pii_detected_input` / `pii_entities` (PRD-010 D7 kept).
- [ ] Given `redact_for_policy` raises `PiiRedactorError` on any message, when step 6 runs, then the existing redaction-error arm writes its row and re-raises, and `call_openrouter` is never called.

## Technical Notes

- Resolve the policy once per request: `get_pii_policy(profile_name)`, where `profile_name` is the value step 5 already computes from `profile` / `PATTERN_PROFILE_DEFAULT`. Do not resolve it twice.
- Messages whose role is not in `policy.input_roles` are appended unchanged, the same `Message` object.
- `tool` turns are still refused at step 0 (PRD-016). Do not relax `_validate_conversation`. The `tool` cell is covered by STORY-008's direct-call tests.
- New tests go in `tests/test_query_pipeline_pii_profiles.py`, with an injected `call_openrouter` stub, never the network.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-002, STORY-007, STORY-008
- **Blocks**: STORY-010, STORY-012, STORY-013

## PRD Reference

Source: [`PRD-012-pii-for-code/PRD.md`](../../PRDs/PRD-012-pii-for-code/PRD.md) — sections 6.1, 6.3, 6.8, 7 (F8), 10, 11 (Functional requirements)
