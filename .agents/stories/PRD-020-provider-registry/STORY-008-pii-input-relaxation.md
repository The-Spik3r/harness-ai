---
id: STORY-008
prd: PRD-020
slug: pii-input-relaxation
title: PII input relaxation for an internal, relaxed provider
type: feature
priority: high
complexity: medium
phase: "3 - Policies that depend on the provider"
status: done
labels: [backend, security, pii]
epic_branch: epic/PRD-020-provider-registry
plan: .agents/plans/PRD-020-provider-registry/completed/STORY-008-pii-input-relaxation.plan.md
report: .agents/reports/PRD-020-provider-registry/STORY-008-pii-input-relaxation.report.md
commit: 8ab795e
depends_on: [STORY-007]
blocks: [STORY-014]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-008: PII input relaxation for an internal, relaxed provider

## Description

As a security admin, I want input redaction and the code size limit skipped only for a provider declared `trust: internal` and `pii: relaxed`, with output redaction unchanged, so that a local model can read unmasked text without any other control weakening.

## Acceptance Criteria

- [ ] Given a relaxed internal provider and an email in a `/v1` (`code` profile) prompt, when the request is sent, then the email reaches the stub unmasked, step 6's size limit (`PII_MAX_CHARACTERS_CODE`) is not applied, and the row has `pii_input_relaxed=1` and `pii_detected_input=0`.
- [ ] Given the same relaxed provider under the `chat` profile (`/query`), when the prompt contains an email and the stub echoes it, then the input is unmasked, the output is still masked, and the row has `pii_input_relaxed=1`.
- [ ] Given an internal provider with `pii: standard` (or no `pii` key), when the same prompt is sent, then it is masked and the code size limit is enforced, and the row has `pii_input_relaxed=0`.
- [ ] Given `PII_REDACTION_ENABLED=false`, when a relaxed provider is used, then `route.relaxes_input()` is false and `pii_input_relaxed=0`; the section 6.6 table's four columns are each covered by a test.
- [ ] Given patterns (step 5), when a relaxed provider is used, then pattern blocking is unchanged and runs before step 6.

## Technical Notes

- Step 6 starts at `app/services/query_pipeline.py:676` (`policy = get_pii_policy(profile_name)` at `:680`; size limit `_redaction_limit_exceeded` `:696`, row `:699-717`; per-message redaction loop `:733-768`; output redaction step 8 at `:863-875`). Gate both the limit and the input loop on `route.relaxes_input()`; leave `_redact` and the output arm untouched.
- `relaxes_input()` is STORY-004's; the decision is never made from a request field, role, profile or host address (section 6.6). `pii_detected_input=0` means not analyzed under relaxation; record `pii_input_relaxed=True` through `log_query` (STORY-006) on every row after step 6 for that request, including the output-redaction error arm.
- Output redaction stays on under `chat` so a user may see their own name masked (O2, adopted as proposed). The `code` policy and `PII_CODE_REDACT_OUTPUT` are in `app/services/pii_policy.py:108-148`.
- Orchestrator decision (stories): PRD open decisions O1-O8 are adopted as proposed.
- Tests: `tests/test_query_pipeline_pii_profiles.py` is the unchanged guard; new cases use two stubs and `tests/_providers.py` (OD2), reading what the stub received from its request log or a capturing fake.

## Dependencies

- **Blocked by**: STORY-007
- **Blocks**: STORY-014

## PRD Reference

Source: [`PRD-020/PRD.md`](../../PRDs/PRD-020-provider-registry/PRD.md) — Sections 4 (Pipeline step 6), 6.6, 9.2 T4; decisions D7
