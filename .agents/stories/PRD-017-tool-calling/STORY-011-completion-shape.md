---
id: STORY-011
prd: PRD-017
slug: completion-shape
title: "Completion shape: tool_calls, content null, finish_reason tool_calls, harness.actions"
type: feature
priority: high
complexity: medium
phase: "3 - Decide and release"
status: in-progress
labels: [backend, api, v1]
epic_branch: epic/PRD-017-tool-calling
plan: .agents/plans/PRD-017-tool-calling/STORY-011-completion-shape.plan.md
report: null
commit: null
depends_on: [STORY-010]
blocks: [STORY-012]
skills: []
created: 2026-11-15
updated: 2026-11-16
---

# STORY-011: Completion shape: tool_calls, content null, finish_reason tool_calls, harness.actions

## Description

As an integrating developer, I want the non-streamed `/v1` completion to carry the released tool calls in the standard shape, so that the OpenAI SDK and my agent parse it like any provider's response.

## Acceptance Criteria

- [ ] Given a release with two calls and no text, when `translate_result` builds the completion, then `choices[0].message` is `{"role": "assistant", "content": null, "tool_calls": [{"id", "type": "function", "function": {"name", "arguments"}}, ...]}` with arguments byte-identical to the upstream's, and `finish_reason == "tool_calls"`.
- [ ] Given every call denied, then `content` is the notes, `tool_calls` is `null` (key kept, PRD-015's serialization rule), `finish_reason == "stop"`; given text plus released calls, then both are present.
- [ ] Given any evaluated response, when serialized, then `harness.actions` lists one `{tool_call_id, tool_name, decision, rule, reason}` per evaluated call in model order; a text-only response has `harness.actions == []` (D14).
- [ ] Given a completion built here, when parsed by the installed `openai` Python SDK's `ChatCompletion` model, then `message.tool_calls[i].function.arguments` equals the upstream string and `finish_reason == "tool_calls"`.
- [ ] Given a response with no tool calls, when serialized, then the body is PRD-015's plus only the keys this story adds (`tool_calls: null`, `harness.actions: []`); `tests/test_v1_translate_result.py`'s existing expectations are updated only for those keys, each change commented with PRD-017 D14.

## Technical Notes

- Orchestrator decision (STORY-009 plan): `tool_release.apply_decisions` returns `finish_reason=None` when there are no calls, meaning "keep the upstream's value"; join content with `tool_release.content_with_notes(content, notes)` (the one Section 6.6 helper); note template and the 64-char cut are `DENIAL_NOTE_TEMPLATE` / `NOTE_FIELD_CAP`.
- `app/models/v1_schemas.py`: `FinishReason` `:83`, `AssistantMessage` `:100-102` (`content: str` → `Optional[str]`, add `tool_calls: Optional[List[...]] = None`), `HarnessCompletionInfo` `:112-121`. Serialize with `model_dump(mode="json")`, never `exclude_none` (module docstring).
- `app/services/v1_translate.py`: `_FINISH_REASONS` `:93`, `translate_result` `:368-408`. The finish reason comes from the `Release` (STORY-009), not from `upstream.finish_reason`, when calls were evaluated.
- Decide in the plan whether `tool_calls: null` on a text-only response is acceptable to every PRD-015 E2E client (Aider, Continue, the SDK); if a key that was absent breaks a strict client, omit it when `None` and record the deviation.
- Tests: `tests/test_v1_translate_result.py`, `tests/test_v1_schemas.py`, `tests/test_v1_tools.py`.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-010
- **Blocks**: STORY-012

## PRD Reference

Source: [`PRD-017-tool-calling/PRD.md`](../../PRDs/PRD-017-tool-calling/PRD.md) — sections 6.6, 7 (F8), 10, 15 (D2, D14)
