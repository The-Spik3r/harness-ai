---
id: STORY-008
prd: PRD-016
slug: sql-classifier
title: SQL classifier with sqlglot — read, write, unscoped write, DDL, DCL, unparsed
type: feature
priority: high
complexity: medium
phase: "3 - Classifiers and the engine"
status: todo
labels: [backend, security, classifier]
epic_branch: epic/PRD-016-action-policy-rules
plan: null
report: null
commit: null
depends_on: [STORY-007]
blocks: [STORY-013, STORY-014]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-008: SQL classifier with sqlglot — read, write, unscoped write, DDL, DCL, unparsed

## Description

As a security admin, I want SQL in a tool call classified by a parser, statement by statement, so that a `DROP` hidden behind a `SELECT;` or a `DELETE` with no real `WHERE` is caught, and anything the parser cannot read is denied.

## Acceptance Criteria

- [ ] Given `classify_sql`, when called with `SELECT * FROM users WHERE id = 1`, `WITH x AS (SELECT 1) SELECT * FROM x`, `EXPLAIN SELECT 1`, then each yields one `sql.read` classification.
- [ ] Given `INSERT INTO t VALUES (1)`, `UPDATE t SET a = 1 WHERE id = 2`, `DELETE FROM t WHERE id = 3`, when classified, then `sql.write`; given `DELETE FROM t`, `UPDATE t SET a = 1`, `DELETE FROM t WHERE 1=1`, `DELETE FROM t WHERE TRUE`, then `sql.unscoped_write`.
- [ ] Given `DROP TABLE users`, `TRUNCATE t`, `ALTER TABLE t ADD c INT`, `CREATE TABLE t (a INT)`, then `sql.ddl` with `detail` naming the keyword (`DROP`, …); given `GRANT ALL ON t TO u`, `REVOKE …`, then `sql.dcl`.
- [ ] Given `SELECT 1; DROP TABLE users`, when classified, then two classifications in order, `sql.read` then `sql.ddl`; given `DR/**/OP TABLE t`, a parse error, or any statement sqlglot returns as `exp.Command` or an unmapped type, then `sql.unparsed`; the function never raises.
- [ ] Given `ACTION_SQL_DIALECT=postgres`, when `action_config.load()` runs, then it loads; given `ACTION_SQL_DIALECT=nosuchdb`, then `ActionConfigError` names the setting and lists the dialects sqlglot knows.

## Technical Notes

- Add `sqlglot==<exact version>` to `requirements.txt`; record the version and why in the story report, and verify there the PRD's assumptions (`exp.Command` fallback, `where` arg on `Update`/`Delete`).
- New `app/services/action_classifiers/sql.py`: `classify_sql(statement: str, dialect: str | None) -> tuple[Classification, ...]`. Map by expression class; anything not explicitly mapped → `sql.unparsed`.
- Tautology check: run sqlglot's simplifier on the `WHERE` condition and treat a constant-true result as absent (PRD Section 6.9).
- Pure module: the dialect is an argument; only `action_config` reads `ACTION_SQL_DIALECT`.
- Tests: new `tests/test_action_sql.py`, table-driven.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-007
- **Blocks**: STORY-013, STORY-014

## PRD Reference

Source: [`PRD-016-action-policy-rules/PRD.md`](../../PRDs/PRD-016-action-policy-rules/PRD.md) — sections 4 (Classifiers), 6.3 (SQL rows), 6.9, 7 (F2), 8, 9.3, 14 (Risk 6), 15 (D2)
