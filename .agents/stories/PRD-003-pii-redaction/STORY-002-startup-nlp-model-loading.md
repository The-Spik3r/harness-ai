---
id: STORY-002
prd: PRD-003
slug: startup-nlp-model-loading
title: "Load Presidio NLP model once at FastAPI startup"
type: technical
priority: high
complexity: small
phase: "1 - Presidio Integration"
status: todo
labels: [backend, pii, performance]
epic_branch: epic/PRD-003-pii-redaction
plan: null
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-005, STORY-011]
skills: []
created: 2026-07-24
updated: 2026-07-24
---

# STORY-002: Load Presidio NLP model once at FastAPI startup

## Description

As a devops engineer, I want the Presidio `AnalyzerEngine` (and its spaCy NLP model) force-loaded during the FastAPI `lifespan` startup hook, so redaction doesn't add cold-start latency to the first `/query` request (PRD Section 6, RF-4, User Story 7).

## Acceptance Criteria

- [ ] Given the app starts, when `lifespan` runs, then the Presidio analyzer singleton from [[STORY-001]]'s `pii_redactor.py` is constructed before the app begins accepting requests (alongside the existing `init_db()` call).
- [ ] Given the app has already started, when the first `/query` request arrives, then no NLP model loading occurs on that request path — the singleton is already warm.
- [ ] Given `PII_REDACTION_ENABLED=false`, when the app starts, then the analyzer is still safe to skip or lazily defer (documented behavior), and no request-path errors occur from redaction being disabled.

## Technical Notes

- Update `app/main.py`'s `lifespan` (currently only calls `init_db()`, see [main.py:10-13](../../../app/main.py)) to also trigger the `pii_redactor` module's singleton construction — e.g. by calling an explicit `pii_redactor.load()` / `get_analyzer()` function exposed by [[STORY-001]], not by relying on import order alone.
- Mirrors the existing pattern in this file: `init_db()` is already called eagerly in `lifespan` before `yield`; follow the same style for the Presidio engine.
- Keep the route handlers untouched — this story only changes `app/main.py`.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-005, STORY-011

## PRD Reference

Source: [`PRD-003/PRD.md`](../../PRDs/PRD-003-pii-redaction/PRD.md) — Section 6 (Core Architecture — Changes to existing modules), Section 12 (Phase 1), Risk 2 (Section 14)
