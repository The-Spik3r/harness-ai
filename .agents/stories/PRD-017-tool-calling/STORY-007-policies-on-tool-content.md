---
id: STORY-007
prd: PRD-017
slug: policies-on-tool-content
title: "Steps 3, 5, 6 on tool content; tool-call arguments never inspected or redacted"
type: feature
priority: high
complexity: medium
phase: "2 - The pipeline accepts tools"
status: done
labels: [backend, pipeline, pii, patterns]
epic_branch: epic/PRD-017-tool-calling
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-007-policies-on-tool-content.plan.md
report: .agents/reports/PRD-017-tool-calling/STORY-007-policies-on-tool-content.report.md
commit: ab2dcc0
depends_on: [STORY-005]
blocks: [STORY-008]
skills: []
created: 2026-11-15
updated: 2026-11-16
---

# STORY-007: Steps 3, 5, 6 on tool content; tool-call arguments never inspected or redacted

## Description

As a security admin, I want tool results to go through the same context, pattern and PII checks as any other untrusted text, and the model's tool-call arguments to reach the upstream exactly as written, so that a planted instruction is visible and no check corrupts a path or a patch.

## Acceptance Criteria

- [ ] Given a conversation whose assistant turn carries tool calls with long `arguments`, when step 3 runs, then the character count includes `len(arguments)` of every call (D12); a conversation without calls counts exactly as today.
- [ ] Given a `tool` turn containing `ignore previous instructions` under `profile="code"`, when step 5 runs, then a `flag` row is written with `pattern_role='tool'` and the request continues; the same phrase inside a history call's `arguments` produces no hit (D13).
- [ ] Given a `tool` turn containing an email under `code`, when step 6 runs, then the turn reaches the upstream redacted; the same email inside a history call's `arguments` reaches the upstream unchanged, and the redacted `Message` keeps `tool_calls` and `tool_call_id` (byte-identical arguments, asserted on the upstream stub's received messages).
- [ ] Given the PII size limit under `code`, when `_analyzable_characters` runs, then it counts `tool` turn content (covered) and never arguments.
- [ ] Given the comments that say `tool` turns cannot reach steps 5/6 ("until PRD-016"), when this story lands, then they say what happens now, citing PRD-017.

## Technical Notes

- Orchestrator note (STORY-003 plan): `app/services/pii_redactor.py:523-526`'s docstring says `Message` has no `tool_calls` field; reword it to state the contract (arguments never reach the redactor) now that the field exists.
- `app/services/query_pipeline.py`: `_context_limit_exceeded` `:78-105`; step 5 `:496-576` (the comment at `:554-557` says the `tool` cell is unreachable); `_analyzable_characters` `:128-146`; step 6 loop `:632-663` — `Message(message.role, redacted_content)` at `:661` would drop `tool_calls`/`tool_call_id`: use `dataclasses.replace(message, content=...)`.
- `pattern_detector.inspect` walks `message.content` per role (`app/services/pattern_detector.py`); confirm it never reads other fields, and that the `code` profile's `tool: flag` cell (`app/services/pattern_config.py:249`) is what fires.
- `pii_policy` (`app/services/pii_policy.py:84-85, 130`): `code` covers `tool`; `chat` covers it "for completeness only" — reword that comment.
- PRD-012's contract: tool-call arguments are never redacted (PRD-012 Section 6.5, the `redact_for_policy` docstring). Keep it in a docstring here too.
- End-to-end pipeline tests need STORY-006's `dedup_key`; inject `call_openrouter` as the existing pipeline tests do.
- Tests: new `tests/test_query_pipeline_tools.py` (shared with STORY-005/010), plus the existing per-step files if a docstring there is now wrong.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-005
- **Blocks**: STORY-008

## PRD Reference

Source: [`PRD-017-tool-calling/PRD.md`](../../PRDs/PRD-017-tool-calling/PRD.md) — sections 2 (Same policies), 5 (story 5), 6.5, 9.2 (T2, T3, T8), 15 (D12, D13)
