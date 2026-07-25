---
id: STORY-007
prd: PRD-003
slug: query-response-pii-signal
title: "POST /query response: pii_redacted signal field"
type: feature
priority: medium
complexity: small
phase: "2 - Pipeline Wiring"
status: todo
labels: [backend, api, pii]
epic_branch: epic/PRD-003-pii-redaction
plan: null
report: null
commit: null
depends_on: [STORY-006]
blocks: [STORY-010]
skills: []
created: 2026-07-24
updated: 2026-07-24
---

# STORY-007: POST /query response — pii_redacted signal field

## Description

As an integrating developer, I want the `POST /query` success response to carry a lightweight signal that redaction occurred, so callers/UI can surface it without seeing the underlying PII, and with zero changes to the existing request contract (PRD User Story 5, RF-9).

## Acceptance Criteria

- [ ] Given a successful query where PII was masked in either the prompt or the response, when `POST /query` returns, then `pii_redacted` is `true` and `pii_entities_masked` lists the distinct entity types masked (e.g. `["EMAIL_ADDRESS"]`).
- [ ] Given a successful query where no PII was detected, when `POST /query` returns, then `pii_redacted` is `false` and `pii_entities_masked` is `[]`.
- [ ] Given an existing integration that ignores unknown response fields, when it parses the response, then it is unaffected — `pii_redacted`/`pii_entities_masked` are additive only.
- [ ] Given the `QueryRequest` schema, when inspected, then it is completely unchanged — no new required or optional request fields (PRD Section 10).

## Technical Notes

- Add `pii_redacted: bool = False` and `pii_entities_masked: List[str] = []` fields to `QuerySuccessResponse` in `app/models/schemas.py` ([schemas.py:14-19](../../../app/models/schemas.py)), matching the example shape in PRD Section 10.
- `QueryBlockedDuplicateResponse`/`QueryBlockedSuspiciousResponse` are unaffected — those paths return before OpenRouter/redaction ever run (per [[STORY-005]]), so PRD Section 10 only documents the field on the success shape.
- In `run_query()` (`app/services/query_pipeline.py`), populate the new fields from the `input_entities`/`output_entities` computed in [[STORY-005]]/[[STORY-006]]: `pii_redacted = bool(input_entities or output_entities)`, `pii_entities_masked` = deduplicated union of both lists.

## Dependencies

- **Blocked by**: STORY-006
- **Blocks**: STORY-010

## PRD Reference

Source: [`PRD-003/PRD.md`](../../PRDs/PRD-003-pii-redaction/PRD.md) — Section 10 (`POST /query` — response), User Story 5, RF-9
