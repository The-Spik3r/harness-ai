---
id: STORY-004
prd: PRD-012
slug: strip-fenced-blocks
title: "Extract strip_fenced_blocks; rebuild strip_code_spans on it"
type: technical
priority: medium
complexity: small
phase: "2 - Primitives"
status: todo
labels: [backend, refactor]
epic_branch: epic/PRD-012-pii-for-code
plan: null
report: null
commit: null
depends_on: []
blocks: [STORY-008]
skills: []
created: 2026-09-23
updated: 2026-09-23
---

# STORY-004: Extract strip_fenced_blocks; rebuild strip_code_spans on it

## Description

As the implementer of PII fence skipping, I want the fence pass of PRD-011's code-span parser as its own pure function, so that PII can skip fenced blocks without also skipping inline spans.

## Acceptance Criteria

- [ ] Given `app/services/pattern_detector.py`, when it is read, then `strip_fenced_blocks(text: str) -> str` is public and pure, blanks fenced blocks (```` ``` ```` and `~~~`, same-character closer at least as long, unterminated to end of text) with newlines, and leaves inline backtick spans untouched.
- [ ] Given any text, when `strip_fenced_blocks` runs, then `len(result) == len(text)` and every newline stays at its original offset.
- [ ] Given `strip_code_spans`, when it is read, then it is the inline pass applied to `strip_fenced_blocks(text)`, and its docstring still describes both passes.
- [ ] Given PRD-011's `test_pattern_matching.py`, `test_pattern_corpus.py`, `test_pattern_profiles.py` and `test_query_pipeline_patterns.py`, when the suite runs, then they pass with no modification.
- [ ] Given a new test, when an inline span holding `ops@corp.com` sits outside any fence, then `strip_fenced_blocks` leaves it intact and `strip_code_spans` blanks it.

## Technical Notes

- This is a pure extraction. Moving the fence loop is the whole change. Do not alter `_FENCE_OPEN` or the closer regex.
- The module still imports nothing from `app`. `pii_redactor` will import `strip_fenced_blocks` from here, which is a one-way dependency and not a cycle.
- Skills: none applicable.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-008

## PRD Reference

Source: [`PRD-012-pii-for-code/PRD.md`](../../PRDs/PRD-012-pii-for-code/PRD.md) — sections 6.5 (D2), 7 (F3), 10
