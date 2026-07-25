---
id: STORY-010
prd: PRD-003
slug: pii-pipeline-integration-tests
title: "End-to-end PII redaction integration test suite"
type: technical
priority: high
complexity: medium
phase: "3 - Isolation Testing"
status: todo
labels: [backend, testing, pii]
epic_branch: epic/PRD-003-pii-redaction
plan: null
report: null
commit: null
depends_on: [STORY-007, STORY-008, STORY-009]
blocks: [STORY-012]
skills: []
created: 2026-07-24
updated: 2026-07-24
---

# STORY-010: End-to-end PII redaction integration test suite

## Description

As a compliance admin, I want automated proof that the whole redaction feature works end-to-end — masked text never reaches OpenRouter, the caller only ever sees masked text, and the audit trail stays raw — so the MVP's definition of done is verifiable in CI, not just by manual inspection (PRD Section 11, Section 12 Phase 3).

## Acceptance Criteria

- [ ] Given a full `POST /query` request with PII in the prompt, when run against a mocked `call_openrouter`, then the mock's recorded call args contain only redacted text — never the raw PII.
- [ ] Given the mocked OpenRouter response also contains PII, when the request completes, then the HTTP response body's `response` field is the masked version, and `pii_redacted`/`pii_entities_masked` match PRD Section 10's shape.
- [ ] Given the same request, when the audit row is fetched via `GET /audit` (admin token), then `prompt_preview`/`response_preview` are the **raw**, unmasked originals.
- [ ] Given the full existing PRD-001 test suite (`tests/test_integration.py`, `tests/test_query_router.py`, etc.), when run alongside the new PII tests, then all pass unmodified — no regressions introduced by this epic.
- [ ] Given `PII_REDACTION_ENABLED=false`, when the same request runs, then prompt/response pass through unmasked (regression guard for the config toggle from [[STORY-001]]).

## Technical Notes

- Extend `tests/test_integration.py` (and/or add `tests/test_pii_redaction_integration.py`) following the existing pattern of mocking `call_openrouter` at the boundary (see how `tests/test_query_router.py`/`test_integration.py` already do this for PRD-001).
- This is the story that runs the full regression pass required by PRD Section 11's "MVP definition of done" checklist — treat it as the final gate before [[STORY-012]]'s docs/rollout.
- Since `en_core_web_lg` is a real, non-trivial NLP model, confirm with the team/CI config whether tests run against the real Presidio pipeline or a stubbed `pii_redactor.redact` — either is acceptable as long as the "never reaches OpenRouter unmasked" and "audit stays raw" assertions are genuinely exercised end-to-end at least once.

## Dependencies

- **Blocked by**: STORY-007, STORY-008, STORY-009
- **Blocks**: STORY-012

## PRD Reference

Source: [`PRD-003/PRD.md`](../../PRDs/PRD-003-pii-redaction/PRD.md) — Section 11 (Success Criteria), Section 12 (Phase 3 — Isolation Testing), Section 8 (Testing)
