---
id: STORY-002
prd: PRD-012
slug: pii-characterization
title: "Characterize today's redact() and pipeline steps 6 and 8 before anything moves"
type: technical
priority: high
complexity: small
phase: "1 - Measure and pin"
status: todo
labels: [tests, pii, regression]
epic_branch: epic/PRD-012-pii-for-code
plan: null
report: null
commit: null
depends_on: []
blocks: [STORY-009, STORY-014]
skills: []
created: 2026-09-23
updated: 2026-09-23
---

# STORY-002: Characterize today's redact() and pipeline steps 6 and 8 before anything moves

## Description

As an end user, I want today's redaction behaviour pinned before it is refactored, so that the `chat` profile demonstrably does not change.

## Acceptance Criteria

- [ ] Given `tests/test_pii_characterization.py` on untouched code, when it runs, then it is green and pins the exact output of `redact()` (masked text and sorted entity list) for a fixed set of at least ten prompts, including one with no PII, one with an already-masked `<PERSON>`, and one with every default entity type.
- [ ] Given a chat-shaped conversation (no system turn, user/assistant history plus a new user turn), when `run_conversation` runs with a recording `call_openrouter` stub, then the test pins the exact `Message` list the stub receives, the exact response returned, and the audit row's `pii_detected_input`, `pii_detected_output` and `pii_entities`.
- [ ] Given the same conversation with PII only in a history turn, when it runs, then the test pins that the history turn is masked upstream and that its entities are **not** recorded in the audit fields (PRD-010 D7).
- [ ] Given the response contains PII, when it runs, then the test pins that the returned response is masked and `pii_detected_output` is true.
- [ ] Given this story's commit, when it is diffed, then no file under `app/` changes.

## Technical Notes

- Characterization first is the house rule (PRD-009 STORY-001, PRD-011 STORY-001). These assertions must not change in any later story of this PRD. STORY-014 checks that.
- Use the real `en_core_web_lg` model, as `test_pii_redactor.py` does (README, *Tests*). Stub only `call_openrouter`.
- Use exact-string assertions, not `in` checks: the point is to detect byte-level drift in the `chat` path.
- Skills: none applicable.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-009, STORY-014

## PRD Reference

Source: [`PRD-012-pii-for-code/PRD.md`](../../PRDs/PRD-012-pii-for-code/PRD.md) — sections 6.10 (Characterization first), 7 (F2), 11 (Quality indicators)
