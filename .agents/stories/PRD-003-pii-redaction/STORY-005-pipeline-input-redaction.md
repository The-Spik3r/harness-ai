---
id: STORY-005
prd: PRD-003
slug: pipeline-input-redaction
title: "Redact prompt before forwarding to OpenRouter"
type: feature
priority: high
complexity: medium
phase: "2 - Pipeline Wiring"
status: todo
labels: [backend, pii, api]
epic_branch: epic/PRD-003-pii-redaction
plan: null
report: null
commit: null
depends_on: [STORY-001, STORY-002]
blocks: [STORY-006, STORY-008]
skills: []
created: 2026-07-24
updated: 2026-07-24
---

# STORY-005: Redact prompt before forwarding to OpenRouter

## Description

As an end user, I want any PII I type into a prompt masked before it leaves the organization's infrastructure, so my personal data is never sent to the third-party model provider (PRD User Story 1, RF-1).

## Acceptance Criteria

- [ ] Given a prompt containing PII (e.g. `"my email is juan@empresa.com, can you draft a reply?"`), when it passes the duplicate/pattern checks, then `call_openrouter()` is invoked with the redacted text (`"my email is <EMAIL_ADDRESS>, can you draft a reply?"`), never the raw prompt.
- [ ] Given the same prompt, when `check_duplicate()` and `detect_suspicious_pattern()` run, then they still receive the **raw** prompt, unchanged from today's behavior — redaction happens strictly after those two checks (PRD Section 6, steps 2-3 vs 4-5).
- [ ] Given a duplicate-blocked or suspicious-pattern-blocked request, when the pipeline short-circuits, then Presidio's `redact()` is never invoked (OpenRouter is never called either) — no wasted NLP inference on blocked requests.
- [ ] Given a clean prompt with no PII, when redaction runs, then the text forwarded to OpenRouter is unchanged and no entities are reported.

## Technical Notes

- Modify `run_query()` in `app/services/query_pipeline.py` ([query_pipeline.py](../../../app/services/query_pipeline.py)): after the existing `pattern_result.is_suspicious` check (line 42) and before the `call_openrouter(...)` call (line 56), call `pii_redactor.redact(prompt)` from [[STORY-001]] to get `(redacted_prompt, input_entities)`, then pass `redacted_prompt` (not `prompt`) into `call_openrouter`.
- `duplicate_checker.check_duplicate(prompt)` (line 26) and `detect_suspicious_pattern(prompt)` (line 41) keep receiving the original `prompt` variable, untouched — do not reorder or rename this variable in a way that risks accidentally feeding redacted text into either check (PRD Section 9, RF-6).
- Hold onto `input_entities` for [[STORY-004]]'s `log_query(pii_detected_input=..., pii_entities=...)` call and for [[STORY-007]]'s response signal — this story doesn't need to wire those yet if [[STORY-006]] does it, but keep the return value available rather than discarding it.
- Respect `PII_REDACTION_ENABLED=false` (from [[STORY-001]]'s config): when disabled, `redact()` should be a no-op pass-through (or the pipeline should skip calling it) — confirm the exact toggle point with [[STORY-001]]'s implementation.

## Dependencies

- **Blocked by**: STORY-001, STORY-002
- **Blocks**: STORY-006, STORY-008

## PRD Reference

Source: [`PRD-003/PRD.md`](../../PRDs/PRD-003-pii-redaction/PRD.md) — Section 6 (Core Architecture, steps 4-6), User Story 1, Section 9 (Redaction scope)
