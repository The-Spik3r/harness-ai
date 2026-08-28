---
id: STORY-004
prd: PRD-006
slug: threaded-database-read
title: "AdminState.load(): all ten read functions via asyncio.to_thread, with a catch-all fault arm"
type: feature
priority: high
complexity: medium
phase: "1 - Access and data"
status: todo
labels: [ui, reflex, state, async, admin]
epic_branch: epic/PRD-006-admin-console
plan: null
report: null
commit: null
depends_on: [STORY-001, STORY-002, STORY-003]
blocks: [STORY-005, STORY-006, STORY-011, STORY-015, STORY-017]
skills: [reflex-docs]
created: 2026-08-28
updated: 2026-08-28
---

# STORY-004: AdminState.load(): all ten read functions via asyncio.to_thread, with a catch-all fault arm

## Description

As a compliance admin, I want the console to load the recorded traffic and the summary figures without blocking the event loop or silently swallowing a failure, so that a failed read is visible as a fault instead of an empty table (PRD Section 6 read path, Section 4 data access).

## Acceptance Criteria

- [ ] Given an authenticated `AdminState`, when `load()` runs, then it calls all ten read functions from [app/db/database.py](../../../app/db/database.py) — `list_audit_logs(limit=100)`, `count_audit_logs`, `count_blocked_duplicates`, `count_blocked_suspicious`, `count_unique_users`, `count_successful_queries`, `count_pii_detected_queries`, `top_models`, `top_users`, `top_pii_entities` — each inside `asyncio.to_thread(...)`, never on the event loop.
- [ ] Given the returned `AuditLog` list, when `load()` completes, then state holds `list[AuditRow]` built through `to_audit_row(...)`, newest first, and `total_recorded` from `count_audit_logs()` as the register's denominator.
- [ ] Given a read in flight, when the page is observed, then `loading` is True for its duration and False afterwards, including on the failure path.
- [ ] Given any read function raising, when `load()` runs, then a catch-all `except Exception` sets an `error` string naming the read that failed, leaves the previously loaded rows and figures **untouched**, and clears `loading`.
- [ ] Given a successful load, when it completes, then `last_refreshed` is set to the time of the read.
- [ ] Given an unauthenticated state, when `load()` is called, then it returns immediately and performs no database read ([[STORY-003]]'s guard).
- [ ] Given `app/`, when `git diff main --stat` is inspected, then no file under it is modified — no new database function and no query parameter is added.

## Technical Notes

- The precedent is PRD-004 STORY-001: `ChatState.send()` offloads `run_query(...)` with `asyncio.to_thread`. Read [chat_ui/chat_ui/state.py](../../../chat_ui/chat_ui/state.py) and follow the same structure, including the `finally`-reset of the pending/loading flag.
- PRD Section 6: "SQLite reads go through `asyncio.to_thread(...)`; state mutation stays inside `async with self`, per Reflex's background-event contract." Per `chat_ui/AGENTS.md`, verbatim: "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory." Confirm the background-event decorator and the `async with self` mutation rule there before writing it.
- A `sqlite3.Connection` is not shareable across threads. Check [app/db/database.py:17](../../../app/db/database.py) `get_connection()` — each read function opens its own connection, so the offload is per-call; do not hoist a connection outside the thread.
- The error arm mirrors PRD-004 STORY-002's "no silent drops" invariant. PRD Section 4: "A failed read renders a fault panel naming what failed — never a silently empty table." The panel itself is [[STORY-017]]; this story produces the state it renders from.
- Keep the ten reads' results as plain state fields here. Turning the counts into `SummaryFigure` objects with scope labels and shares is [[STORY-015]].

## Dependencies

- **Blocked by**: STORY-001, STORY-002, STORY-003
- **Blocks**: STORY-005, STORY-006, STORY-011, STORY-015, STORY-017

## PRD Reference

Source: [`PRD-006/PRD.md`](../../PRDs/PRD-006-admin-console/PRD.md) — Section 4 (data access & failure handling), Section 6 (read path), Section 12 Phase 1
