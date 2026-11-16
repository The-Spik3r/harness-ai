---
id: STORY-006
prd: PRD-017
slug: dedup-key-tool-turns
title: "dedup_key over tool turns: never the anchor, in the prefix, tool-free keys unchanged"
type: feature
priority: high
complexity: medium
phase: "2 - The pipeline accepts tools"
status: done
labels: [backend, duplicates]
epic_branch: epic/PRD-017-tool-calling
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-006-dedup-key-tool-turns.plan.md
report: .agents/reports/PRD-017-tool-calling/STORY-006-dedup-key-tool-turns.report.md
commit: 16fd154
depends_on: [STORY-005]
blocks: [STORY-008]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-006: dedup_key over tool turns: never the anchor, in the prefix, tool-free keys unchanged

## Description

As an integrating developer, I want the duplicate key to tell apart each step of an agent's tool loop, so that running `npm test` twice in one session is not refused, while a byte-identical resend still is.

## Acceptance Criteria

- [ ] Given a set of tool-free conversations (single turn, multi-turn with system/assistant), when `dedup_key` runs, then each key equals a value pinned in the test from today's implementation (no upgrade resets a window).
- [ ] Given a conversation with tool turns or assistant `tool_calls`, when `dedup_key` runs, then the anchor is the last `user` turn, every other turn goes into the prefix hash in order with the anchor's position marked, an assistant turn with calls frames as `[role, content, [[id, name, arguments], ...]]` and a tool turn as `[role, content, tool_call_id]` (PRD-017 Section 6.4).
- [ ] Given `[u1, A(calls), T, u2]` and `[u1, u2, A(calls), T]` with identical texts, when keyed, then the keys differ.
- [ ] Given one session where the agent runs `npm test`, edits a file, and runs `npm test` again with identical command output, when each request of the loop is keyed, then no two requests share a key; given one request sent twice byte for byte, then both have the same key (and the pipeline holds the second as a duplicate within 24 h).
- [ ] Given a tool-containing conversation through `run_conversation`, when the pipeline runs, then step 1 no longer raises, and the `dedup_key` stored on the row is the new key; `tests/test_dedup_key.py:202-204`'s `PRD-017` assertion is replaced, commented with PRD-017 D4.

## Technical Notes

- `app/services/duplicate_checker.py:491-512` (`DEDUP_KEY_VERSION`, `_KEYED_ROLES`, `dedup_key`). Keep `DEDUP_KEY_VERSION = "v1"` if tool-free keys are unchanged; the framing must make tool-containing keys unforgeable from tool-free ones (a field count or marker, decided in the plan).
- `DedupTurn` is a Protocol with `role`/`content`; read `tool_calls` / `tool_call_id` with `getattr(turn, ..., default)` or widen the Protocol — no import of `app.models.messages` from here if it would create a cycle (check).
- `conversation_key` (`app/services/conversation_key.py`) is unchanged: first system + first user turn.
- `tests/test_query_pipeline_multiturn.py` spies on `_sha256_json` by name (see `conversation_key.py`'s import comment); keep that working.
- PRD-009 D4 left this to "PRD-016" (= this PRD). Cite PRD-009 D4 and PRD-017 D4 in the docstring.
- Tests: `tests/test_dedup_key.py`, `tests/test_query_pipeline_dedup_key.py`.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-005
- **Blocks**: STORY-008

## PRD Reference

Source: [`PRD-017-tool-calling/PRD.md`](../../PRDs/PRD-017-tool-calling/PRD.md) — sections 5 (story 4), 6.4, 11, 15 (D4)
