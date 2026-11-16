---
id: STORY-005
prd: PRD-017
slug: step-zero-and-prompt-anchor
title: "Step 0 accepts tool turns under the D6 shape rules; the audit prompt is the final turn"
type: feature
priority: high
complexity: medium
phase: "2 - The pipeline accepts tools"
status: done
labels: [backend, pipeline, audit]
epic_branch: epic/PRD-017-tool-calling
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-005-step-zero-and-prompt-anchor.plan.md
report: .agents/reports/PRD-017-tool-calling/STORY-005-step-zero-and-prompt-anchor.report.md
commit: a86a71c
depends_on: [STORY-003]
blocks: [STORY-006, STORY-007, STORY-008]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-005: Step 0 accepts tool turns under the D6 shape rules; the audit prompt is the final turn

## Description

As the PRD-017 implementer, I want `run_conversation` to accept a conversation that ends in a tool result, and to refuse one whose tool turns do not answer a call, so that an agent's tool loop can run through the pipeline and a malformed one is still a programming error.

## Acceptance Criteria

- [ ] Given `[user, assistant(tool_calls=[c1, c2]), tool(c1), tool(c2)]`, when `_validate_conversation` runs, then it passes; a conversation ending in `user` passes as today.
- [ ] Given each D6 violation — last turn `assistant` or `system`; a `tool` turn first; a `tool` turn whose id is not among the nearest preceding assistant `tool_calls` turn's ids; a `tool` turn separated from that assistant turn by a `user` turn; one id answered twice — when validated, then `InvalidConversationError` names the rule (and the index), and no row is written.
- [ ] Given a conversation ending in a `tool` turn, when the pipeline writes any row, then `prompt` (and so `prompt_hash` / `prompt_preview`) is that tool turn's content; for a `user`-final conversation it is unchanged (D7).
- [ ] Given a `tool`-final conversation with PII in the tool turn under `code`, when step 6 runs, then the row's `pii_detected_input` / `pii_entities` come from that final turn (PRD-010 D7 generalized from "the last user turn" to "the final turn").
- [ ] Given the existing step-0 tests that assert `tool turns are not supported (PRD-017)`, when this story lands, then they are replaced by the tests above, each modified assertion commented with PRD-017 D6; superseded test names registered in `_DELIBERATELY_SUPERSEDED_TESTS`.

## Technical Notes

- `app/services/query_pipeline.py:69-75` (`_validate_conversation`), `:284` (`prompt = messages[-1].content`, with the comment "Guaranteed by validation: the last message is always role == user" — update it), `:623-663` (step 6's "only the last user turn's entities count" loop and its comment that `tool` cannot get here).
- `dedup_key` still raises for `tool` turns until STORY-006, so a pipeline test with a tool turn needs STORY-006, or monkeypatches `query_pipeline.dedup_key`. Test `_validate_conversation` and the anchor directly here; keep the end-to-end pipeline test for STORY-006/007.
- Put the D6 rule in one pure helper both this guard and the `/v1` edge (STORY-008) can call, so the two cannot drift — e.g. a function in `app/models/messages.py` returning the first violation as (index, rule) or None. The edge raises `V1RequestError`, step 0 raises `InvalidConversationError`.
- Reword the PRD-016 numbering comments this story touches ("until PRD-016" → PRD-017).
- Tests: `tests/test_query_pipeline_run_conversation.py` or a new `tests/test_query_pipeline_tools.py`; `tests/test_messages.py` for the helper.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-003
- **Blocks**: STORY-006, STORY-007, STORY-008

## PRD Reference

Source: [`PRD-017-tool-calling/PRD.md`](../../PRDs/PRD-017-tool-calling/PRD.md) — sections 4 (Pipeline), 6.3, 7 (F4), 15 (D6, D7)
