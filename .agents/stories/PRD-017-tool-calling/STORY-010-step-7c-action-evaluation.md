---
id: STORY-010
prd: PRD-017
slug: step-7c-action-evaluation
title: "Step 7c: evaluate every call, release, record() with audit_id, fail closed, has_tool_calls"
type: feature
priority: high
complexity: large
phase: "3 - Decide and release"
status: todo
labels: [backend, pipeline, action-policy, audit]
epic_branch: epic/PRD-017-tool-calling
plan: null
report: null
commit: null
depends_on: [STORY-001, STORY-002, STORY-008, STORY-009]
blocks: [STORY-011, STORY-013]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-010: Step 7c: evaluate every call, release, record() with audit_id, fail closed, has_tool_calls

## Description

As a security admin, I want every tool call the model produced decided by the action policy and recorded against the request's audit row before the response is shaped, so that no call reaches a client undecided or unrecorded.

## Acceptance Criteria

- [ ] Given an upstream result with tool calls, when the pipeline runs, then after the step 7b charge and before step 8 it calls `action_policy.evaluate_all` once with the calls (as `action_adapters.ToolCall`) and the identity, and `tool_release.apply_decisions` with the decisions; the pipeline's success result carries the `Release` (calls, notes, finish reason) and the decisions for the router, without changing `/query`'s response body (`tests/test_query_outcomes_regression.py` unchanged).
- [ ] Given the success row, when step 8 writes it, then `has_tool_calls` is 1 if the request had an assistant `tool_calls` or `tool` turn or the upstream returned calls, else 0 (D19); then `action_audit.record(decisions, identity, audit_id=<that row's id>, session_id=session_id)` runs; an upstream result with no calls records nothing.
- [ ] Given `record()` raising `StorageError`, when the pipeline runs, then it raises a new `ActionAuditError` (after an `ERROR` log naming the user and `audit_id`, never arguments), which `/v1` maps to 500 `internal_error`, retryable, and no call is released in either response shape (D8).
- [ ] Given a `DROP TABLE` call through `/v1` with the flag on, when the request completes, then exactly one `action_decisions` row exists with `decision='deny'`, `rule='sql.ddl'` and `audit_id` equal to the request's `audit_logs.id`.
- [ ] Given output redaction on (`policy.output`), when step 8 runs, then only `response` (content) is redacted, the notes are appended **after** redaction, and released calls are untouched.

## Technical Notes

- Orchestrator decision (STORY-009 plan): `tool_release.apply_decisions` returns `finish_reason=None` when there are no calls, meaning "keep the upstream's value"; join content with `tool_release.content_with_notes(content, notes)` (the one Section 6.6 helper); note template and the 64-char cut are `DENIAL_NOTE_TEMPLATE` / `NOTE_FIELD_CAP`.
- Position: `app/services/query_pipeline.py` between step 7b (`:699-724`) and step 8 (`:726-801`); the success row is at `:766-792` (`has_tool_calls=False` with the comment "PRD-016 sets this" — this story sets it). Number it **7c** (the lettering rule at `:362-365`).
- How the router gets the release without moving `/query`'s body: `QuerySuccessResponse` is `/query`'s response model. Options for the plan: a private attribute / `exclude=True` field on the success model, or a wrapper the router unwraps. Choose one, prove `/query`'s JSON is unchanged, and document it. The router's `_Upstream` wrapper (`app/routers/v1.py:108-136`) already captures the raw upstream result — do **not** let the router read raw `upstream.result.tool_calls` for the response (T1).
- `ActionAuditError` goes in `_PIPELINE_FAULTS` (`app/routers/v1.py:105`) and `_fault_code` (`:183-197`) → `INTERNAL_ERROR`; `/query` never reaches it (no calls without tools).
- The engine and audit: `app/services/action_policy.py:343-360`, `app/services/action_audit.py:172-188` (no catch, "PRD-017's decision"). Update those module docstrings' "PRD-017 is the first caller" lines to say where it is called.
- STORY-001 may have corrected built-in mappings; use the corrected tool names in tests.
- Tests: `tests/test_query_pipeline_tools.py`, `tests/test_v1_tools.py`; `tests/test_query_pipeline_audit_fields.py` scans every `log_query` call site — keep it green.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-001, STORY-002, STORY-008, STORY-009
- **Blocks**: STORY-011, STORY-013

## PRD Reference

Source: [`PRD-017-tool-calling/PRD.md`](../../PRDs/PRD-017-tool-calling/PRD.md) — sections 6.1, 6.6, 7 (F6, F7), 9.2 (T1, T5), 11, 15 (D8, D19)
