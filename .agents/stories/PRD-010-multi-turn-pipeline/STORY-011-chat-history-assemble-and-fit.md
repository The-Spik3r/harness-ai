---
id: STORY-011
prd: PRD-010
slug: chat-history-assemble-and-fit
title: "chat_history.assemble (answered exchanges only) and fit (drop oldest whole exchanges)"
type: feature
priority: high
complexity: medium
phase: "3 - Chat sends history"
status: done
labels: [backend, chat, history]
epic_branch: epic/PRD-010-multi-turn-pipeline
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-011-chat-history-assemble-and-fit.plan.md
report: .agents/reports/PRD-010-multi-turn-pipeline/STORY-011-chat-history-assemble-and-fit.report.md
commit: a3eccae
depends_on: [STORY-001]
blocks: [STORY-012]
skills: []
created: 2026-09-17
updated: 2026-09-18
---

# STORY-011: chat_history.assemble (answered exchanges only) and fit (drop oldest whole exchanges)

## Description

As an end user, I want my chat history rebuilt from the exchanges that actually got an answer, and trimmed from the oldest end when it's too long, so that refused turns never re-enter context and a long chat still sends.

## Acceptance Criteria

- [ ] Given the new [app/services/chat_history.py](../../../app/services/chat_history.py), when `assemble(identity, session_id)` reads a transcript through `chat_sessions.messages_for`, then it returns `[Message("user", row.prompt), Message("assistant", row.content), …]` for `kind == "assistant"` rows only, in `id` order.
- [ ] Given a transcript containing `user`, `duplicate`, `injection`, `forbidden`, `upstream_error` and `internal_error` rows (and a `context_limit` row), when assembled, then none of them contributes a message. A session whose **first** user bubble was never persisted still yields its first exchange (built from the assistant row's `prompt`, PRD 6.4 fact 1).
- [ ] Given history off, a foreign session or an unknown session, when `assemble` runs, then it returns `[]`. An assistant row with `prompt` `NULL` or empty is skipped rather than emitting an empty user turn.
- [ ] Given `fit(history, new_turn, max_messages, max_characters)`, when history plus the new turn exceeds either limit, then it drops the **oldest whole exchange** repeatedly until both hold and returns `(messages, dropped_count)`. It never splits a pair, and the new turn is always last. When everything fits, it returns `(history + [new_turn], 0)`.
- [ ] Given a new turn that alone exceeds `max_characters`, when `fit` runs, then it returns `([new_turn], len(history) // 2)`, so the pipeline refuses it (D2). `fit` is pure (property tests over random histories: output length ≤ limit or only the new turn; order preserved; count equals exchanges removed).

## Technical Notes

- `assemble` does one read (`chat_sessions.messages_for`), is sync, and is called via `run_in_pipeline` in STORY-012. It must not read `settings.CONTEXT_MAX_*`; `fit` takes limits as arguments so it stays testable without settings.
- `assemble` does **not** redact. D5 is enforced in the pipeline (STORY-007), because stored `prompt` is raw and future callers are untrusted (PRD 6.4).
- `chat_sessions.messages_for` already returns `[]` for foreign, unknown and history-off sessions (PRD 9.1). Rely on it and test it, rather than re-checking ownership.
- Import `Message` from `app.models.messages`. No Reflex imports in this module.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-012

## PRD Reference

Source: [`PRD-010-multi-turn-pipeline/PRD.md`](../../PRDs/PRD-010-multi-turn-pipeline/PRD.md) — sections 4 (History), 5 (stories 1–3), 6.4 (D3, D4), 7 (F7), 9.1, 10, 11
