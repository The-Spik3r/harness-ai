---
id: STORY-002
prd: PRD-016
slug: retarget-tool-calling-runtime-strings
title: Retarget the six "(PRD-016)" tool-calling runtime strings to "(PRD-017)"
type: technical
priority: medium
complexity: small
phase: "1 - Threat model and vocabulary"
status: done
labels: [backend, v1, docs]
epic_branch: epic/PRD-016-action-policy-rules
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-002-retarget-tool-calling-runtime-strings.plan.md
report: .agents/reports/PRD-016-action-policy-rules/STORY-002-retarget-tool-calling-runtime-strings.report.md
commit: 9f7b379
depends_on: []
blocks: [STORY-020]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-002: Retarget the six "(PRD-016)" tool-calling runtime strings to "(PRD-017)"

## Description

As an integrating developer reading a `/v1` error, I want "tool calling is not supported" to point at the PRD that will actually enable tools, so that I am not sent to the action-policy document when I look up why my request was refused.

## Acceptance Criteria

- [ ] Given a `/v1` request with `tools`, when it is refused, then the error message reads `tool calling is not supported (PRD-017)` and the code is still `tools_not_supported`.
- [ ] Given the six runtime strings listed in PRD Section 15 Evidence (`v1_translate.py` x3, `messages.py`, `openrouter_client.py`, `query_pipeline.py`), when the story is done, then each says `(PRD-017)` and nothing else in the string changed.
- [ ] Given the test suite, when it runs, then every test asserting one of these strings asserts the new text, each change carries a comment citing PRD-016 D14, and the full suite is green.
- [ ] Given a search of `app/` for string literals containing `(PRD-016)`, when run after the story, then it finds none; code comments mentioning PRD-016 are left unchanged (they are read through the PRD's numbering note).

## Technical Notes

- Files: `app/services/v1_translate.py` (about lines 120, 218, 222), `app/models/messages.py` (about 76), `app/services/openrouter_client.py` (about 199), `app/services/query_pipeline.py` (about 73).
- Tests likely touched: `tests/test_v1_translate_request.py`, `tests/test_v1_router.py`, `tests/test_messages.py`, `tests/test_openrouter_client.py`; find them with `grep -rn "PRD-016" tests/`.
- `docs/features.md` refers to tool calling as PRD-016; update those user-facing references in the same commit.
- Do not edit PRD-015's documents, plans or reports.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-020

## PRD Reference

Source: [`PRD-016-action-policy-rules/PRD.md`](../../PRDs/PRD-016-action-policy-rules/PRD.md) — Numbering note, sections 10, 15 (D14)
