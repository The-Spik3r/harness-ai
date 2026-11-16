---
id: STORY-003
prd: PRD-017
slug: message-model-tool-fields
title: "ToolCallSpec, Message.tool_calls / tool_call_id, and the normalizer"
type: feature
priority: high
complexity: medium
phase: "1 - Survey and foundations"
status: done
labels: [backend, models]
epic_branch: epic/PRD-017-tool-calling
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-003-message-model-tool-fields.plan.md
report: .agents/reports/PRD-017-tool-calling/STORY-003-message-model-tool-fields.report.md
commit: a68762c
depends_on: []
blocks: [STORY-004, STORY-005, STORY-009]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-003: ToolCallSpec, Message.tool_calls / tool_call_id, and the normalizer

## Description

As the PRD-017 implementer, I want the one internal message shape to carry an assistant turn's tool calls and a tool turn's call id, so that every pipeline step can see tool traffic without a second message type.

## Acceptance Criteria

- [ ] Given `app/models/messages.py`, when imported, then it defines `ToolCallSpec(id: str, name: str, arguments: str)` (frozen) and `Message` gains `tool_calls: tuple[ToolCallSpec, ...] = ()` and `tool_call_id: Optional[str] = None`; every existing `Message(role, content)` construction in the repo and the suite works unchanged, and the module still imports nothing from `app`.
- [ ] Given an assistant message `{"role": "assistant", "content": null, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "bash", "arguments": "{\"command\":\"ls\"}"}}]}`, when normalized, then it is `Message("assistant", "", (ToolCallSpec("c1", "bash", "{\"command\":\"ls\"}"),))` with `arguments` byte-identical to the input string; `tool_calls: []` normalizes to `()`.
- [ ] Given a `tool` message `{"role": "tool", "tool_call_id": "c1", "content": "ok"}` (string or text parts), when normalized, then it is `Message("tool", "ok", tool_call_id="c1")`.
- [ ] Given each invalid shape — `tool_calls` on a non-assistant role, not a list, an item without `id`/`function.name`/`function.arguments`, `type` other than `"function"`, non-string `arguments`, duplicate ids in one turn, `tool_call_id` missing or empty on a `tool` turn, `tool_call_id` on any other role — when normalized, then `MessageNormalizationError` names the location (`tool_calls[1].function.arguments`) and the rule, never the value.
- [ ] Given `tests/test_messages.py`'s existing assertions that `tool_calls` is refused with `PRD-017`, when this story lands, then they are replaced by the acceptance tests above, each modified assertion commented with PRD-017 D5, and any renamed or removed test function registered in `_DELIBERATELY_SUPERSEDED_TESTS`; a test asserts `ToolCallSpec`'s field names equal `action_adapters.ToolCall`'s.

## Technical Notes

- Current refusal: `app/models/messages.py:73-76` (before content, because a tool-call turn has `content: null`). The `Role` comment at `:14-15` says "so PRD-016 does not have to widen the type" — reword it (PRD-017; see the PRD's numbering note).
- `v1_translate.translate_messages` (`app/services/v1_translate.py:216-223`) still refuses tool calls and tool turns *before* the normalizer, so `/v1` behaviour does not change in this story. Do not touch it (STORY-008).
- `normalize_message` has other callers? Grep before changing; the chat UI and `/query` build `Message` directly and never send these fields.
- `DedupTurn` (`app/services/duplicate_checker.py:486-488`) is a Protocol with `role` and `content`; adding fields to `Message` keeps it satisfied. `dedup_key` still raises for `tool` (STORY-006).
- `arguments` must not be parsed, stripped or re-serialized anywhere (PRD-017 Section 6.2, PRD-012's contract).
- Tests: `tests/test_messages.py`.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-004, STORY-005, STORY-009

## PRD Reference

Source: [`PRD-017-tool-calling/PRD.md`](../../PRDs/PRD-017-tool-calling/PRD.md) — sections 4 (Message model), 6.2, 15 (D5)
