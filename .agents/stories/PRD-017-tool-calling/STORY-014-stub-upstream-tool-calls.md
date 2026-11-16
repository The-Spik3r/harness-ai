---
id: STORY-014
prd: PRD-017
slug: stub-upstream-tool-calls
title: "Stub upstream: scripted tool_calls replies, rules matching on any last turn"
type: technical
priority: medium
complexity: small
phase: "4 - Real clients and docs"
status: todo
labels: [tests, e2e, tooling]
epic_branch: epic/PRD-017-tool-calling
plan: null
report: null
commit: null
depends_on: [STORY-004]
blocks: [STORY-016, STORY-017]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-014: Stub upstream: scripted tool_calls replies, rules matching on any last turn

## Description

As the E2E author, I want the stub upstream to answer with scripted tool calls and to choose its reply from the latest tool result, so that a multi-step agent loop can be scripted without a real model.

## Acceptance Criteria

- [ ] Given a rule reply with `tool_calls: [{"name": "bash", "arguments": "{\"command\":\"npm test\"}"}]`, when it answers, then the body is a valid Chat Completions response with `content: null`, generated ids (`call_<n>`) where the script omits them, and `finish_reason: "tool_calls"` unless the script sets one; `call_openrouter` (STORY-004) parses it.
- [ ] Given a rule with `role: "tool"` (and optionally `last_role`), when matched, then `contains`/`regex` test the last message of that role, so the reply can depend on the latest tool result; rules without `role` keep today's behaviour (last `user` message) and every existing script still works.
- [ ] Given any request, when logged, then the line still names only model, message count, parameter keys and the rule — never content, arguments or headers; the existing `tests/test_stub_openrouter.py` assertions are unchanged.
- [ ] Given `tests/e2e/scripts/`, when this story lands, then it adds one example tool-loop script (read → edit → `npm test` → final text) used by the stub's own tests.

## Technical Notes

- `scripts/stub_openrouter.py`: module docstring (script format), `_PREFIX`, the rule dataclass and matcher. Standard library only; nothing under `app/` imports it (a test checks that).
- Keep `times: N` semantics per stub process.
- The `tools` the client sends are not validated by the stub; it may log their count.
- Tests: `tests/test_stub_openrouter.py`.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-004
- **Blocks**: STORY-016, STORY-017

## PRD Reference

Source: [`PRD-017-tool-calling/PRD.md`](../../PRDs/PRD-017-tool-calling/PRD.md) — sections 4 (Stub upstream), 7 (F9), 15 (D15)
