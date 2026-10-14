---
id: STORY-004
prd: PRD-013
slug: conversation-key
title: "conversation_key derivation"
type: feature
priority: high
complexity: small
phase: "1 - The row"
status: in-progress
labels: [backend, audit]
epic_branch: epic/PRD-013-audit-and-usage-limits
plan: .agents/plans/PRD-013-audit-and-usage-limits/STORY-004-conversation-key.plan.md
report: null
commit: null
depends_on: []
blocks: [STORY-005]
skills: []
created: 2026-10-04
updated: 2026-10-14
---

# STORY-004: conversation_key derivation

## Description

As a compliance admin, I want a key derived from how a conversation starts, so that an external client's turns can be grouped without a harness session.

## Acceptance Criteria

- [ ] Given a conversation that grows from 1 to 50 user turns with the same `system` and first `user` message, when `conversation_key(user_id, messages)` is computed at each step, then all 50 values are equal.
- [ ] Given the same messages and two different `user_id` values, when the key is computed, then the two values differ.
- [ ] Given two conversations whose first `user` messages differ, or whose first `system` messages differ, when the key is computed, then the values differ.
- [ ] Given a conversation with no `system` turn, when the key is computed, then it succeeds, and `[user("a")]` and `[user("a"), assistant("b"), user("c")]` give the same key.
- [ ] Given `app/services/conversation_key.py`, when it is read, then it imports no settings and no database module, defines `CONVERSATION_KEY_VERSION = "c1"`, and includes the version in the hashed value.

## Technical Notes

- New file `app/services/conversation_key.py`; tests in `tests/test_conversation_key.py`.
- Frame the hash input as JSON, as `duplicate_checker._sha256_json` does (`ensure_ascii=False`, compact separators), so that field boundaries cannot be forged by content. Reuse that helper by importing it or by making it public; do not copy it.
- Raw text only. Nothing redacted is ever passed in (PRD Section 9.2 invariants).
- The input always has a `user` turn: `_validate_conversation` guarantees the last message is one. A bare `next(...)` with no default is acceptable, with a comment saying why.
- The docstring must state the three documented limits from PRD Section 6.3: same-start conversations merge, identical `/query` prompts merge, and a rewritten first message starts a new key.
- Skills: none applicable. No UI surface changes in this story.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-005

## PRD Reference

Source: [`PRD-013-audit-and-usage-limits/PRD.md`](../../PRDs/PRD-013-audit-and-usage-limits/PRD.md) — sections 6.3 (D2), 7 (F4), 9.2 (T13)
