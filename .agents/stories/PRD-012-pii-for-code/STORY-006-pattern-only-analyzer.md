---
id: STORY-006
prd: PRD-012
slug: pattern-only-analyzer
title: "Pattern-only analyzer, selected by the entity list"
type: feature
priority: high
complexity: medium
phase: "2 - Primitives"
status: todo
labels: [backend, pii, performance]
epic_branch: epic/PRD-012-pii-for-code
plan: null
report: null
commit: null
depends_on: [STORY-003, STORY-005]
blocks: [STORY-008]
skills: []
created: 2026-09-23
updated: 2026-09-23
---

# STORY-006: Pattern-only analyzer, selected by the entity list

## Description

As an integrating developer, I want the `code` profile to run Presidio's pattern recognizers without spaCy's NER model, so that identifiers are not tagged as people and redaction at agent sizes costs milliseconds, not seconds.

## Acceptance Criteria

- [ ] Given an entity list containing no NER type (`PERSON`, `LOCATION`, or any other NER-backed type Presidio defines), when `_get_analyzer(entities)` is called, then it returns the tokenizer-only analyzer the STORY-003 report found feasible (or the documented fallback), built once and cached.
- [ ] Given an entity list containing `PERSON`, when `_get_analyzer(entities)` is called, then it returns today's `en_core_web_lg` analyzer singleton, the same object `redact()` uses.
- [ ] Given `pii_redactor.load()` with `PII_REDACTION_ENABLED=true`, when it runs at startup, then it builds today's analyzer as before **and** the analyzer `PII_ENTITIES_CODE` selects, so no analyzer is built on a request path.
- [ ] Given the pattern-only analyzer, when it analyzes `jane@example.com called 415-555-0134`, then it returns `EMAIL_ADDRESS` and `PHONE_NUMBER` spans, and a spy on `en_core_web_lg` records no call.
- [ ] Given `redact()`, when this story lands, then `test_pii_redactor.py` and `test_pii_characterization.py` pass unchanged.

## Technical Notes

- The NER-type set is a constant beside the analyzer code, with a comment naming why each member is there. Do not infer it at runtime.
- A failure to build the pattern-only analyzer raises `PiiRedactorError` from `load()`, so the boot fails. It never silently falls back to the full analyzer, which would reintroduce NER false positives and cost without anyone noticing.
- `test_analyzer_engine_constructed_only_once` has to stay true for the full analyzer. Add the equivalent test for the second one.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-003, STORY-005
- **Blocks**: STORY-008

## PRD Reference

Source: [`PRD-012-pii-for-code/PRD.md`](../../PRDs/PRD-012-pii-for-code/PRD.md) — sections 6.4 (D7), 7 (F6), 8, 14 (Risk 2)
