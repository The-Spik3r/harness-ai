---
id: STORY-009
prd: PRD-007
slug: top-pii-entities-sql-aggregation
title: "Aggregate top_pii_entities() in SQL instead of transferring every PII-bearing row"
type: enhancement
priority: high
complexity: small
phase: "3 - Network-cost remediation"
status: todo
labels: [backend, database, performance, pii]
epic_branch: epic/PRD-007-turso-migration
plan: null
report: null
commit: null
depends_on: [STORY-006]
blocks: [STORY-010]
skills: []
created: 2026-09-01
updated: 2026-09-01
---

# STORY-009: Aggregate top_pii_entities() in SQL instead of transferring every PII-bearing row

## Description

As a compliance admin, I want the PII entity ranking computed in the database, so that loading the admin console does not pull the entire PII-bearing history across the network every time.

`top_pii_entities()` currently issues `SELECT pii_entities FROM audit_logs WHERE pii_entities IS NOT NULL`, then splits each comma-separated value and counts entities in a Python dict. Against a local file that was an acceptable shortcut. Against a remote endpoint it transfers the full history on every admin console load and every `GET /stats`, and it gets worse with every audited query. PRD Section 6 Pattern 4: "It is rewritten to aggregate in SQL, returning at most `limit` rows."

## Acceptance Criteria

- [ ] Given `top_pii_entities(limit=5)`, when it is called, then its signature, return type (`list[str]`), and ordering semantics are unchanged: entity names in descending frequency, capped at `limit`.
- [ ] Given a database with PII history, when the function runs, then it transfers at most `limit` rows from the database. The whole-table scan into Python is gone.
- [ ] Given the same data, when the new implementation and the old one are compared, then they produce identical output — including the tie-breaking order for entities with equal counts. If the old tie-break was incidental rather than specified, state the chosen behavior explicitly in the report.
- [ ] Given a `pii_entities` value holding multiple comma-separated entities, when it is counted, then each entity in the value contributes one to its own count, exactly as the current `for entity in row["pii_entities"].split(",")` loop does.
- [ ] Given an empty table or one with no PII rows, when the function runs, then it returns an empty list without error.
- [ ] Given `tests/test_db.py`, when it runs, then the existing `top_pii_entities` coverage passes unmodified, plus new cases for multi-entity values, ties, and the empty case.
- [ ] Given `chat_ui/chat_ui/admin_copy.py`, when its contract is checked, then the statement at [line 317](../../../chat_ui/chat_ui/admin_copy.py) still holds — the visible cap "comes from the read's own limit (`top_pii_entities(limit=5)`)". No copy change is needed or permitted.

## Technical Notes

- Files: [app/db/database.py](../../../app/db/database.py) (`top_pii_entities`), `tests/test_db.py`.
- The hard part is that `pii_entities` is a **comma-separated TEXT column**, not a normalized table. Aggregating it in SQL means splitting it in SQL. Decide the approach deliberately — a recursive CTE that splits on commas is the portable answer; check [[STORY-001]]'s decision record for anything the client constrains.
- Do **not** normalize the schema to make this easier. PRD Section 4 puts "Schema redesign, new tables, new columns, or new indexes beyond what the current schema declares" out of scope. A `pii_entities` junction table is a reasonable idea and belongs in a different PRD.
- This story is sequenced before [[STORY-010]] deliberately: the batched read will fold this statement in, and folding in a full-table scan would defeat the point of batching.
- Get the tie-break right. The current implementation sorts with `sorted(counts.items(), key=lambda item: item[1], reverse=True)`, which is stable over Python dict insertion order — effectively first-seen-wins among equal counts. That is incidental, not designed. Pick a deterministic rule (count descending, then entity name) and pin it with a test, rather than reproducing an accident.
- The entity vocabulary is bounded and known — `PII_ENTITIES` in [app/config.py](../../../app/config.py) defaults to seven values. That does not license hardcoding them in SQL; the column stores whatever was written, including values from an older configuration.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story changes a database read, not rendered output. No skill applies.

## Dependencies

- **Blocked by**: STORY-006
- **Blocks**: STORY-010

## PRD Reference

Source: [`PRD-007/PRD.md`](../../PRDs/PRD-007-turso-migration/PRD.md) — Section 6 Pattern 4, Section 7.4, Section 11 (functional requirements), Section 12 Phase 3
