---
id: STORY-001
prd: PRD-007
slug: libsql-driver-spike
title: "Spike: verify the six risky libSQL client behaviors and record the driver decision"
type: spike
priority: high
complexity: medium
phase: "1 - Driver verification and behavior pinning"
status: done
labels: [backend, database, spike, turso, libsql]
epic_branch: epic/PRD-007-turso-migration
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-001-libsql-driver-spike.plan.md
report: .agents/reports/PRD-007-turso-migration/STORY-001-libsql-driver-spike.report.md
commit: null
depends_on: []
blocks: [STORY-005, STORY-006]
skills: []
created: 2026-09-01
updated: 2026-09-01
---

# STORY-001: Spike: verify the six risky libSQL client behaviors and record the driver decision

## Description

As a maintainer, I want the libSQL Python client chosen on evidence rather than assumption, so that the storage swap in [[STORY-006]] does not discover mid-rewrite that the driver cannot express something [app/db/database.py](../../../app/db/database.py) depends on.

The PRD is deliberate about this: "Driver selection is a Phase 1 deliverable, not an assumption. The libSQL Python ecosystem offers more than one client, and they differ precisely where this codebase is sensitive." Every one of the six behaviors below is load-bearing in the current module, and each has a different blast radius if it turns out to be unsupported.

## Acceptance Criteria

- [ ] Given a real libSQL endpoint, when the spike runs, then it answers **named-column row access** — whether a result row supports `row["timestamp"]` / `row["n"]` subscripting as `sqlite3.Row` does, or must be mapped by position. This is used at 22 call sites and in both `_row_to_audit_log()` and `_row_to_user()`.
- [ ] Given a write executed without `with sqlite3.Connection`, when the spike reads the row back **through a separate, freshly constructed client**, then the result records whether the write durably committed and what call, if any, was required to make it so. A read-back through the same client is not acceptable evidence — see [[STORY-006]] Risk 1.
- [ ] Given an `INSERT` into a table with `INTEGER PRIMARY KEY AUTOINCREMENT`, when the spike inspects the result, then it records whether the new row id is retrievable and how. `insert_audit_log()` returns `cursor.lastrowid` and `GET /audit/{id}` depends on it.
- [ ] Given an `UPDATE` matching exactly one row and an `UPDATE` matching zero rows, when the spike inspects the result, then it records whether an affected-row count is available and correct for both. `deactivate_user()` and `set_user_token_hash()` return `cursor.rowcount == 1`.
- [ ] Given a table with a known column set, when the spike executes `PRAGMA table_info(audit_logs)`, then it records whether the statement is supported over the remote endpoint and what shape the rows take. `_add_missing_columns()` reads `row["name"]` from it, and it runs inside `init_db()` — a failure here is a failure to boot.
- [ ] Given several statements submitted together, when the spike executes them, then it records whether the client exposes a batch/multi-statement API, how many round trips it costs, and how per-statement results and per-statement errors are returned. [[STORY-010]] cannot be designed without this.
- [ ] Given all six answers, when the spike concludes, then a decision record is committed naming the chosen client, its exact pinned version, and a yes/no plus evidence for each of the six behaviors — including any behavior that is **not** supported and the workaround the later stories must adopt.
- [ ] Given `git diff main --stat`, when it is inspected, then no file under `app/`, `chat_ui/`, or `scripts/` is modified. This story produces knowledge and a document, not production code.

## Technical Notes

- Files: a throwaway spike script (scratch, not committed) plus the committed decision record. Suggested location for the record: `.agents/reports/PRD-007-turso-migration/STORY-001-driver-decision.md`, matching where the workflow already writes reports.
- The six behaviors come from PRD Section 8 verbatim: "they differ precisely where this codebase is sensitive: named-column row access, `with`-block commit semantics, `lastrowid`, `rowcount`, `PRAGMA` support, and batch execution."
- Read [app/db/database.py](../../../app/db/database.py) end to end first. The behaviors are not abstract — `get_connection()` at line 26 sets `row_factory = sqlite3.Row`, and every function in the module is written against that decision.
- The endpoint used for the spike may be a local libSQL server; it does not need to be a hosted Turso database. But the commit-semantics check specifically must not be run against an in-process or in-memory shortcut that would hide a missing commit.
- Also settle the **local dev-server workflow** here — how a developer starts a libSQL server locally, on what port, and how it is torn down. [[STORY-003]] and [[STORY-006]] both build on it, and PRD Section 12 lists it as a Phase 1 deliverable: "Local libSQL dev-server workflow documented and reproducible."
- Record the pinned version explicitly. PRD Section 8: "the driver is pinned to an exact version in `requirements.txt`, consistent with `reflex==0.9.6.post1`."
- If a behavior is unsupported, do not stop at "no". Record the workaround, because the story that needs it will otherwise rediscover the problem under time pressure.
- `.agents/skills/` was scanned: it contains only `frontend-design`, scoped to visual design of UI. This story renders nothing. No skill applies.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-005, STORY-006

## PRD Reference

Source: [`PRD-007/PRD.md`](../../PRDs/PRD-007-turso-migration/PRD.md) — Section 8 (Technology Stack, driver selection), Section 12 Phase 1, Section 14 Risk 1
