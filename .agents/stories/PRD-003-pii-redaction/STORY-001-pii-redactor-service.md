---
id: STORY-001
prd: PRD-003
slug: pii-redactor-service
title: "Presidio PII redactor service"
type: feature
priority: high
complexity: medium
phase: "1 - Presidio Integration"
status: done
labels: [backend, pii, nlp]
epic_branch: epic/PRD-003-pii-redaction
plan: .agents/plans/PRD-003-pii-redaction/completed/STORY-001-pii-redactor-service.plan.md
report: .agents/reports/PRD-003-pii-redaction/STORY-001-pii-redactor-service.report.md
commit: 0495068
depends_on: []
blocks: [STORY-002, STORY-005]
skills: []
created: 2026-07-24
updated: 2026-07-25
---

# STORY-001: Presidio PII redactor service

## Description

As a devops engineer, I want a single `pii_redactor.py` module that wraps Presidio's `AnalyzerEngine` and `AnonymizerEngine` behind a `redact(text)` function, so the rest of the pipeline never imports Presidio directly and the NLP engine is a reusable, lazily-created singleton (PRD Section 6, RF-4).

## Acceptance Criteria

- [ ] Given a text containing default-entity PII (e.g. `"my email is a@b.com"`), when `redact(text)` is called, then it returns `(redacted_text, entities_found)` with the email masked (e.g. `<EMAIL_ADDRESS>`) and `entities_found` containing `"EMAIL_ADDRESS"`.
- [ ] Given text with no detectable PII, when `redact(text)` is called, then the original text is returned unchanged and `entities_found` is an empty list.
- [ ] Given the module is imported and `redact()` called multiple times, when inspected, then the `AnalyzerEngine`/NLP model is constructed only once (module-level singleton), not per call.
- [ ] Given `PII_ENTITIES` and `PII_SCORE_THRESHOLD` env vars are set, when `redact(text)` runs, then only the configured entity types are checked and matches below the threshold are not masked (default threshold is low/permissive, favoring recall).
- [ ] Given `PII_NLP_MODEL` is set, when the analyzer initializes, then it loads that spaCy model name instead of a hardcoded default.

## Technical Notes

- New module: `app/services/pii_redactor.py` exposing `redact(text: str) -> tuple[str, list[str]]`, per PRD Section 6 "New module" spec.
- Add settings to `app/config.py` (`Settings` in this repo, using `pydantic_settings.BaseSettings`, mirrors existing `OPENROUTER_API_KEY`/`ADMIN_TOKEN` pattern): `PII_REDACTION_ENABLED` (bool, default `true`), `PII_SCORE_THRESHOLD` (float, default `0.35`), `PII_ENTITIES` (comma-separated list parsed into `List[str]`, default `PERSON,EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE,LOCATION`), `PII_NLP_MODEL` (str, default `en_core_web_lg`) — PRD Section 9 env var block.
- Adapter pattern (PRD Section 6): no other module should `import presidio_*` directly — everything Presidio-specific stays inside this file.
- Add `presidio-analyzer`, `presidio-anonymizer`, `spacy` to `requirements.txt` (PRD Section 8); the `en_core_web_lg` model itself is installed separately via `python -m spacy download en_core_web_lg` (covered in [[STORY-011]]'s Docker step, not pip-installable as a plain requirement).
- This story does not wire the redactor into the request pipeline or force it to load at startup — that is [[STORY-002]] and [[STORY-005]]/[[STORY-006]].

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-002, STORY-005

## PRD Reference

Source: [`PRD-003/PRD.md`](../../PRDs/PRD-003-pii-redaction/PRD.md) — Section 6 (Core Architecture), Section 8 (Technology Stack), Section 9 (Environment variables), Section 12 (Phase 1)
