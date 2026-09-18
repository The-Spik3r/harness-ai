---
id: STORY-010
prd: PRD-010
slug: chat-messages-history-trimmed-column
title: "chat_messages.history_trimmed column, converged by init_db()"
type: technical
priority: medium
complexity: small
phase: "3 - Chat sends history"
status: done
labels: [backend, db, migration]
epic_branch: epic/PRD-010-multi-turn-pipeline
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-010-chat-messages-history-trimmed-column.plan.md
report: .agents/reports/PRD-010-multi-turn-pipeline/STORY-010-chat-messages-history-trimmed-column.report.md
commit: null
depends_on: []
blocks: [STORY-012]
skills: []
created: 2026-09-17
updated: 2026-09-18
---

# STORY-010: chat_messages.history_trimmed column, converged by init_db()

## Description

As an end user, I want the "earlier exchanges were not sent" note to survive a reload, so that a restored chat tells me the same thing the live one did.

## Acceptance Criteria

- [ ] Given [app/db/models.py](../../../app/db/models.py), when it is read, then `CREATE_CHAT_MESSAGES_TABLE` declares `history_trimmed INTEGER` (nullable), a new `CHAT_MESSAGES_ADDED_COLUMNS = {"history_trimmed": "INTEGER"}` exists, and `StoredMessage.history_trimmed: Optional[int] = None`.
- [ ] Given a pre-PRD database whose `chat_messages` lacks the column, when `init_db()` runs, then the column is added, existing rows read `NULL`, and a second `init_db()` issues no `ALTER`.
- [ ] Given two concurrent `init_db()` calls racing the add, when one gets `duplicate column name`, then it converges via `_is_duplicate_column` instead of failing boot.
- [ ] Given `database.append_chat_message` with `history_trimmed=3`, when `list_chat_messages` reads it back, then the value is `3`. Rows written without it read `None`.
- [ ] Given the full suite, including [tests/test_db.py](../../../tests/test_db.py) and [tests/test_chat_sessions.py](../../../tests/test_chat_sessions.py), when this story lands, then it is green.

## Technical Notes

- `_add_missing_columns` in [app/db/database.py](../../../app/db/database.py) currently iterates only `AUDIT_LOGS_ADDED_COLUMNS`. Generalize it to a `(table, columns)` pair list, or add a sibling pass for `chat_messages`. Keep the audit-logs behaviour and its docstring's race reasoning intact, and read `PRAGMA table_info` per table.
- The chat_messages add must run **after** `CREATE_CHAT_MESSAGES_TABLE` in `init_db()`.
- Nothing writes a non-NULL value yet. STORY-012 does, through `ChatMessage` → `_to_stored_message`.
- Mirror the PRD-008 STORY-003 / PRD-009 STORY-002 convergence tests (fresh DB, pre-PRD DB, race, steady state).
- Following the libSQL dev-server note, mass fixture errors mean restart the container.
- Skills: none applicable.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-012

## PRD Reference

Source: [`PRD-010-multi-turn-pipeline/PRD.md`](../../PRDs/PRD-010-multi-turn-pipeline/PRD.md) — sections 4 (History), 6.8, 6.9, 11 (fit/footer persisted)
