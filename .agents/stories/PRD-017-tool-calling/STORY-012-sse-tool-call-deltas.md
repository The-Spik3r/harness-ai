---
id: STORY-012
prd: PRD-017
slug: sse-tool-call-deltas
title: Buffered SSE tool_calls deltas in one burst
type: feature
priority: high
complexity: medium
phase: "3 - Decide and release"
status: done
labels: [backend, api, v1, streaming]
epic_branch: epic/PRD-017-tool-calling
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-012-sse-tool-call-deltas.plan.md
report: .agents/reports/PRD-017-tool-calling/STORY-012-sse-tool-call-deltas.report.md
commit: 0865708
depends_on: [STORY-011]
blocks: [STORY-015]
skills: []
created: 2026-11-15
updated: 2026-11-16
---

# STORY-012: Buffered SSE tool_calls deltas in one burst

## Description

As an integrating developer whose agent streams by default, I want a streamed `/v1` response to carry the released tool calls as standard deltas, so that my client accumulates them exactly as it would from a provider.

## Acceptance Criteria

- [ ] Given a completion with two released calls and no content, when `completion_events` renders it, then the events are: a role chunk (`delta: {"role": "assistant", "content": null}`), one chunk per call (`delta: {"tool_calls": [{"index": i, "id", "type": "function", "function": {"name", "arguments": <whole string>}}]}`), the finish chunk (`finish_reason: "tool_calls"`), the usage chunk only with `include_usage`, then `[DONE]` (PRD-017 Section 6.6).
- [ ] Given a text-only completion, when rendered, then the events are byte-identical to PRD-015's (`tests/test_v1_sse.py` unchanged).
- [ ] Given the streamed events of a tool-call response, when fed to the installed `openai` SDK's stream accumulator (or `ChatCompletionStreamState`), then the accumulated message equals the non-streamed completion's message (calls, arguments, finish reason).
- [ ] Given every call denied in a streamed response, then the content chunk carries the notes and the finish chunk `stop`; given `record()` failing after commit, then a single `error` event `internal_error` and no `[DONE]`, and no tool-call delta was sent.

## Technical Notes

- Orchestrator note (STORY-001 plan): OpenCode 2.0.10 raises an error if anything arrives after the finish chunk, and sends `stream_options` only when the provider supports usage. Check against the survey note whether the `include_usage` chunk after the finish chunk (OpenAI's own order) is a problem for OpenCode; if it is, record it for STORY-016 rather than reordering the PRD-015 sequence.
- `app/services/v1_sse.py:362-387` (`completion_events`), `app/models/v1_schemas.py:134-172` (`ChunkDelta` drops `None` keys via its serializer; add `tool_calls`; `FinishReason` already widened by STORY-011). The role chunk's `content: null` must survive `_drop_unset` — check the serializer and adjust deliberately, keeping the finish chunk's `delta: {}`.
- Streamed responses carry no `harness` object (PRD-015); the audit holds the decisions (D14).
- The commit rule is unchanged (`app/routers/v1.py:307-331`): 7c runs after the upstream call, so a streamed request is already committed when calls are decided — buffering is what keeps calls from leaving early (T1).
- Tests: `tests/test_v1_sse.py`, `tests/test_v1_tools.py`.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-011
- **Blocks**: STORY-015

## PRD Reference

Source: [`PRD-017-tool-calling/PRD.md`](../../PRDs/PRD-017-tool-calling/PRD.md) — sections 6.1, 6.6, 9.2 (T1), 14 (Risk 2)
