---
id: STORY-009
prd: PRD-021
slug: audit-columns
title: Four audit columns for real-time delivery
type: feature
priority: high
complexity: medium
phase: "2 - Pipeline"
status: todo
labels: [backend, audit, db]
epic_branch: epic/PRD-021-realtime-streaming
plan: null
report: null
commit: null
depends_on: [STORY-008]
blocks: [STORY-010, STORY-011, STORY-013]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-009: Four audit columns for real-time delivery

## Description

As an auditor, I want each audit row to say whether its response was delivered in real time, whether reasoning was shown, whether the live redaction diverged, and the stream's completion id, so that "what did the user see, and when" has an answer.

## Acceptance Criteria

- [ ] Given `app/db/models.py`, when inspected, then `streamed_realtime`, `reasoning_shown`, `stream_redaction_divergence` (`INTEGER NOT NULL DEFAULT 0`) and `completion_id` (`TEXT NULL`) are in `AUDIT_LOGS_ADDED_COLUMNS` and `CREATE_AUDIT_LOGS_TABLE`, after PRD-020's five in every list, and on `AuditLog`
- [ ] Given an existing database, when the app starts, then `_add_missing_columns` adds the four columns; old rows read `0`/NULL; a fresh database has them without an `ALTER`
- [ ] Given `_SUMMARY_SQL` and `_row_to_audit_log`, when a row is read, then the four keys are present after PRD-020's five, and the summary's parameter tuple is unchanged
- [ ] Given every row-writing arm of the pipeline, when it writes, then `streamed_realtime` and `reasoning_shown` are required keywords (a forgotten arm is a `TypeError`), and the success row records the real values: a real-time row has `streamed_realtime=1` and `completion_id` equal to the id passed to `sink.committed`; a buffered row has `0` and NULL
- [ ] Given a real-time commit, when the upstream stream opens, then an `INFO` line names the user, the model and `completion_id`, never content (T9); a client disconnect mid-stream still writes the row `success=1` with usage charged (D15, T7; pipeline side — the router side is STORY-010)

## Technical Notes

- Exactly PRD-020 D13's path: `app/db/models.py` `AUDIT_LOGS_ADDED_COLUMNS`, `CREATE_AUDIT_LOGS_TABLE` (`:4`); `database.py` `_add_missing_columns` (~`:730`), `_row_to_audit_log` (~`:920`), `_SUMMARY_SQL` json_object (~`:1330-1381`, comment at `:1326-1332`). Line numbers are from before PRD-020; grep.
- `audit_logger.log_query` gains the four keywords. The `_deny` discipline: `query_pipeline.py:245-305`.
- Census guards: a new public function in `database.py` or a new caller of `get_connection()`/`_session()` must be registered in `tests/test_db_resilience_retry.py`. A field-order guard test lists the audit fields (PRD-020 STORY-009's CI fix a4dc1ef added `usage_estimated` to it): add the four there.
- `GET /audit` fields and the `?completion_id=` filter are STORY-013, not here.
- Orchestrator decision (STORY-006 impl, 0eb1fc1): `completion_id` and `realtime_request` are locals in `run_conversation` (marked "STORY-009 persists these"); `completion_id` is set whenever a sink is present, including the buffered path, so persist it only when `realtime_request` (PRD F7: NULL otherwise). The streamed arm resets `model_used` to the requested id after `collect()` (PRD-020 D13).

## Dependencies

- **Blocked by**: STORY-008
- **Blocks**: STORY-010, STORY-011, STORY-013

## PRD Reference

Source: [`PRD-021/PRD.md`](../../PRDs/PRD-021-realtime-streaming/PRD.md) — Sections F7, D14, D15, D17, T7, T9
