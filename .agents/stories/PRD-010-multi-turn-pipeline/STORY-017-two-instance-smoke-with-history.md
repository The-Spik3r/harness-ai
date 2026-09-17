---
id: STORY-017
prd: PRD-010
slug: two-instance-smoke-with-history
title: "Two-instance smoke: a multi-turn chat continued across instances"
type: technical
priority: medium
complexity: medium
phase: "4 - Prove and document"
status: todo
labels: [tests, smoke, db]
epic_branch: epic/PRD-010-multi-turn-pipeline
plan: null
report: null
commit: null
depends_on: [STORY-012]
blocks: [STORY-018]
skills: []
created: 2026-09-17
updated: 2026-09-17
---

# STORY-017: Two-instance smoke: a multi-turn chat continued across instances

## Description

As a platform operator running more than one container against one Turso database, I want a conversation started on one instance to be continued with full history on another, so that history is proven to come from the shared database and not from process memory.

## Acceptance Criteria

- [ ] Given the two running instances in [tests/test_two_instance_smoke.py](../../../tests/test_two_instance_smoke.py) (both booted with the new `chat_messages.history_trimmed` column converged), when exchange 1 is sent in a session on instance A and exchange 2 in the same session on instance B, then B's upstream recorder receives `[user(ex1), assistant(ex1 reply), user(ex2)]`.
- [ ] Given a turn held as duplicate on instance A, when the next send happens on instance B, then that turn is absent from B's upstream messages.
- [ ] Given both instances booting simultaneously against a database **without** `history_trimmed`, when they converge, then both boot and exactly one column exists (the race path from STORY-010, end to end).
- [ ] Given a trimmed send on A (small monkeypatched limits on both), when the transcript is read on B, then the assistant row's `history_trimmed` matches.
- [ ] Given the existing smoke tests, when this story lands, then all pass unmodified.

## Technical Notes

- Reuse the `Instance`, `Recording` and `smoke_user` fixtures. Add tests; do not restructure the module.
- The instances run the real chat send path only if the fixture supports it. Otherwise drive `chat_history.assemble` + `fit` + `run_conversation` on each instance's process exactly as `ChatState` does, and say which in the test docstring.
- Following the libSQL dev-server note, mass fixture errors mean restart the container.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-012
- **Blocks**: STORY-018

## PRD Reference

Source: [`PRD-010-multi-turn-pipeline/PRD.md`](../../PRDs/PRD-010-multi-turn-pipeline/PRD.md) — sections 6.4, 11 (Quality indicators), 12 (Phase 4)
