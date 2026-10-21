---
id: STORY-005
prd: PRD-015
slug: message-translation
title: "Request translation: messages, the developer role and edge structure checks"
type: feature
priority: high
complexity: medium
phase: "1 - Foundations"
status: todo
labels: [backend, api, translation]
epic_branch: epic/PRD-015-openai-compatible-endpoint
plan: null
report: null
commit: null
depends_on: [STORY-004]
blocks: [STORY-006, STORY-009]
skills: []
created: 2026-10-21
updated: 2026-10-21
---

# STORY-005: Request translation: messages, the developer role and edge structure checks

## Description

As an integrating developer, I want my client's `messages` array accepted in every text shape the standard allows and refused with a precise 400 when it is not text, so that my conversation reaches the pipeline intact and a bad one never becomes an unaudited 500.

## Acceptance Criteria

- [ ] Given messages with string content, text-part lists and an assistant `content: null`, when `translate_messages` runs, then it returns `Message` objects equal to what `normalize_messages` returns for the same input.
- [ ] Given a `developer` message, when it is translated, then it becomes `Message("system", ...)`; given a per-message `name` field, then it is ignored and reported as `messages[].name` in the ignored names this function returns.
- [ ] Given an empty list, a `tool` role, a message carrying `tool_calls`, a last message that is not `user`, an image content part or an unknown role, when it is translated, then `V1RequestError(code="invalid_messages", param=<location>)` is raised, and its message names the location and rule but never the content.
- [ ] Given any input this function accepts, when the result is passed to `query_pipeline._validate_conversation`, then it never raises `InvalidConversationError` (property test over generated message lists).

## Technical Notes

- New pure module `app/services/v1_translate.py` (no I/O, no settings reads), the style of `app/models/messages.py`. `V1RequestError(code, message, param)` is defined here and is what the router maps to a 400 in STORY-009/010.
- Map `developer` to `system` **before** calling `normalize_messages`, which rejects unknown roles. Do not widen `Role`: `developer` is a wire alias, not a pipeline role.
- `tool` and `tool_calls` are refused here with `code="tools_not_supported"`, not `invalid_messages`, so the client sees the same code as for `tools` (STORY-006). Use one constant.
- Edge structure checks duplicate `_validate_conversation` on purpose: the pipeline's version is a programming-error guard that writes no row (PRD-010 Section 6.1); this one is the client-facing 400 (PRD Section 4, "so `InvalidConversationError` stays unreachable").
- `MessageNormalizationError`'s message already names location and rule; wrap it, keep its text.
- Tests: `tests/test_v1_translate_request.py`; no DB.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-004
- **Blocks**: STORY-006, STORY-009

## PRD Reference

Source: [`PRD-015-openai-compatible-endpoint/PRD.md`](../../PRDs/PRD-015-openai-compatible-endpoint/PRD.md) — sections 4 (Request translation), 7.1, 9.2 (T6)
