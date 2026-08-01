---
id: STORY-006
prd: PRD-003
slug: pipeline-output-redaction
title: "Redact model response before returning to caller"
type: feature
priority: high
complexity: medium
phase: "2 - Pipeline Wiring"
status: done
labels: [backend, pii, api]
epic_branch: epic/PRD-003-pii-redaction
plan: .agents/plans/PRD-003-pii-redaction/completed/STORY-006-pipeline-output-redaction.plan.md
report: .agents/reports/PRD-003-pii-redaction/STORY-006-pipeline-output-redaction.report.md
commit: 87c7ea8
depends_on: [STORY-005, STORY-004]
blocks: [STORY-007, STORY-008]
skills: []
created: 2026-07-24
updated: 2026-07-31
---

# STORY-006: Redact model response before returning to caller

## Description

As an end user, I want PII appearing in the model's response also masked before I see it, so a model that echoes back or infers personal data doesn't expose it to me, while the audit log still keeps the raw response for compliance investigation (PRD User Story 2 and 3, RF-3, RF-7).

## Acceptance Criteria

- [ ] Given `call_openrouter()` returns a response containing PII, when the pipeline processes it, then the caller-facing `QuerySuccessResponse.response` field is the **redacted** text.
- [ ] Given the same response, when `log_query()` is called, then it receives the **raw, unredacted** `response` — `response_preview`/`response_hash` in the audit log remain exactly as raw as before this feature (PRD Section 9, User Story 3).
- [ ] Given a response with no PII, when redaction runs, then the returned text is unchanged and no output entities are reported.
- [ ] Given the full success path, when measured, then the pipeline still returns exactly one audit row per request, matching PRD-001's existing guarantee.

## Technical Notes

- Modify `run_query()` in `app/services/query_pipeline.py` ([query_pipeline.py:55-83](../../../app/services/query_pipeline.py)): after `openrouter_result = call_openrouter(...)` succeeds, call `pii_redactor.redact(openrouter_result.response)` to get `(redacted_response, output_entities)`.
- Critical ordering: call `log_query(..., response=openrouter_result.response, ...)` with the **raw** response (as today, line 68-76) — do not pass `redacted_response` into `log_query`. Only the `QuerySuccessResponse(response=..., ...)` returned to the caller (line 78-83) should use `redacted_response`.
- Wire [[STORY-004]]'s new `log_query` parameters here: `pii_detected_input=bool(input_entities)`, `pii_detected_output=bool(output_entities)`, `pii_entities=input_entities + output_entities` (deduplicated), using the `input_entities` captured in [[STORY-005]].
- The OpenRouter-error path (lines 56-66) is unaffected — no response exists yet to redact when the call fails.

## Dependencies

- **Blocked by**: STORY-005, STORY-004
- **Blocks**: STORY-007, STORY-008

## PRD Reference

Source: [`PRD-003/PRD.md`](../../PRDs/PRD-003-pii-redaction/PRD.md) — Section 6 (Core Architecture, steps 7-10), User Story 2 and 3, Section 9 (Why the audit log stays raw)
