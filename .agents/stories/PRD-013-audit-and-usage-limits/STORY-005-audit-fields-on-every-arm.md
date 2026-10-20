---
id: STORY-005
prd: PRD-013
slug: audit-fields-on-every-arm
title: "log_query and every pipeline arm write the new fields; ingress at every call site"
type: feature
priority: high
complexity: large
phase: "1 - The row"
status: done
labels: [backend, audit, pipeline]
epic_branch: epic/PRD-013-audit-and-usage-limits
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-005-audit-fields-on-every-arm.plan.md
report: .agents/reports/PRD-013-audit-and-usage-limits/STORY-005-audit-fields-on-every-arm.report.md
commit: 1ab83f2
depends_on: [STORY-001, STORY-002, STORY-003, STORY-004]
blocks: [STORY-006, STORY-011, STORY-013]
skills: []
created: 2026-10-04
updated: 2026-10-17
---

# STORY-005: log_query and every pipeline arm write the new fields; ingress at every call site

## Description

As a compliance admin, I want every row to say which door the request came through, how many messages it carried, what it cost and which conversation it belongs to, so that multi-turn traffic can be reconstructed from the audit alone.

## Acceptance Criteria

- [ ] Given any arm of `run_conversation`, when it writes a row, then the row has `ingress` (as passed), `message_count == len(messages)`, a non-NULL `conversation_key` and `streamed` (as passed); the success and output-redaction-error rows also have `input_tokens` and `output_tokens`, and the upstream-error row has neither.
- [ ] Given `POST /query`, when it succeeds or is blocked, then its row has `ingress='query'` and `message_count=1`; given the foreign-session refusal, then its row has `ingress='query'`, `message_count=1` and `conversation_key` NULL.
- [ ] Given a chat send with history and one without, when each writes its row, then both have `ingress='chat'`, and the Nth send of a session with nothing trimmed has `message_count == 2N-1` (N-1 prior exchanges plus the new turn).
- [ ] Given a 50-turn conversation run through `run_conversation(ingress="v1")`, when the audit is read, then there are 50 rows with one `conversation_key`, 50 distinct `dedup_key` values and `ingress='v1'` on each.
- [ ] Given the production sources under `app/` and `chat_ui/`, when the scan test runs, then every call to `run_conversation` or `run_query` passes `ingress` explicitly or is `run_query`'s own delegation, and every direct `log_query` call passes `ingress`, `message_count` and `conversation_key`.

## Technical Notes

- `log_query` gains eight keyword parameters, defaulted like `profile`, with a comment in that style saying the pipeline never omits them. `limit_exceeded` and `has_tool_calls` are accepted here and first used in STORY-011 and PRD-016.
- `run_conversation(..., *, profile=None, ingress=None, streamed=False)`. Compute `message_count` and `conversation_key` once, beside `key` at step 1. `_deny` takes `ingress`, `message_count` and `conversation_key` as required parameters, for the reason it requires `session_id`, `dedup_key` and `profile`.
- `run_query(..., *, ingress="query")` forwards it. `ChatState._do_send` passes `ingress="chat"` on both branches (`run_conversation` and `run_query`).
- `ingress` defaults to `None` on `run_conversation` because several hundred test call sites call it directly; NULL is the honest record for them (PRD Section 6.9).
- `has_tool_calls=False` is passed from one place, with a comment naming PRD-016.
- The scan test follows `tests/test_query_pipeline_pii_profiles.py`'s call-site scan (PRD-012 STORY-011).
- Check the chat message-count formula against `chat_history.fit` before asserting it; assert what the pipeline received.
- STORY-001's row assertions gain the new fields and lose none. New file `tests/test_query_pipeline_audit_fields.py`.
- Skills: none applicable. No UI surface changes in this story.

## Dependencies

- **Blocked by**: STORY-001, STORY-002, STORY-003, STORY-004
- **Blocks**: STORY-006, STORY-011, STORY-013

## PRD Reference

Source: [`PRD-013-audit-and-usage-limits/PRD.md`](../../PRDs/PRD-013-audit-and-usage-limits/PRD.md) — sections 6.1, 6.2, 6.9 (D10), 7 (F5), 11 (MVP definition, Audit)
