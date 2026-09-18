---
id: STORY-008
prd: PRD-010
slug: context-limit-refusal
title: "Context-limit refusal: response model, audited pipeline arm, /query passthrough"
type: feature
priority: high
complexity: medium
phase: "2 - Pipeline over messages"
status: done
labels: [backend, api, audit]
epic_branch: epic/PRD-010-multi-turn-pipeline
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-008-context-limit-refusal.plan.md
report: .agents/reports/PRD-010-multi-turn-pipeline/STORY-008-context-limit-refusal.report.md
commit: e4de634
depends_on: [STORY-002, STORY-007]
blocks: [STORY-009, STORY-013, STORY-016]
skills: []
created: 2026-09-17
updated: 2026-09-18
---

# STORY-008: Context-limit refusal: response model, audited pipeline arm, /query passthrough

## Description

As a compliance admin, I want a conversation over the configured limits to be refused with the limit named and the attempt audited, so that nothing is silently truncated and oversized requests leave the same evidence as any other refusal.

## Acceptance Criteria

- [ ] Given [app/models/schemas.py](../../../app/models/schemas.py), when it is read, then `QueryBlockedContextLimitResponse(status: Literal["BLOCKED"] = "BLOCKED", reason: str, limit: Literal["messages", "characters"], maximum: int, actual: int)` exists and is a member of `QueryResponse`, and `QueryPipelineResult` includes it.
- [ ] Given `CONTEXT_MAX_MESSAGES=3` and a 4-message conversation, when `run_conversation` runs for an authorized identity, then it returns `limit="messages", maximum=3, actual=4, reason="Conversation exceeds context limit"`. Messages are checked first: a conversation over both limits reports `messages`.
- [ ] Given `CONTEXT_MAX_CHARACTERS=10` and contents totalling 12 characters, when it runs, then it returns `limit="characters", maximum=10, actual=12`. Exactly 10 characters is **not** refused (boundary test).
- [ ] Given a refusal, when the audit row is read, then there is exactly one row with `success=0`, `error_message="context limit: characters 12 > 10"` (or the `messages` equivalent), the last user turn as `prompt`, a non-NULL `dedup_key`, and the passed `session_id`. The check runs **after** all three authorization checks and **before** `check_duplicate` (spy test: a forbidden identity gets `forbidden`, not `context_limit`; `check_duplicate` is never called on refusal).
- [ ] Given `POST /query` with a prompt of `CONTEXT_MAX_CHARACTERS + 1` characters (limit monkeypatched small), when sent, then the response is 200 with the context-limit body, and a new `test_outcome_7_context_limit` in [tests/test_query_outcomes_regression.py](../../../tests/test_query_outcomes_regression.py) pins it. Rows 1–6 are unmodified.

## Technical Notes

- Read the limits per call from `settings` so tests can monkeypatch them.
- `success=False` means the row never counts as a prior query (PRD-009 Section 6.3), which is correct (PRD 9.2 T7). No new `audit_logs` column.
- Put the new arm at STORY-007's `# context limit (STORY-008)` marker, and pass `session_id=` and `dedup_key=` explicitly like every other arm.
- `ChatState._do_send` currently lands an unknown result type on its "Unhandled response type" `internal_error` bubble. That is acceptable for this commit; STORY-013 adds the real bubble. Add a test pinning the interim behaviour, with a `# replaced by STORY-013` comment, so the gap is visible rather than accidental.
- The response is 200 `BLOCKED`, like the other three blocks. No new status code (PRD Section 10).
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-002, STORY-007
- **Blocks**: STORY-009, STORY-013, STORY-016

## PRD Reference

Source: [`PRD-010-multi-turn-pipeline/PRD.md`](../../PRDs/PRD-010-multi-turn-pipeline/PRD.md) — sections 4 (Pipeline), 6.1, 6.5 (D2), 7 (F6), 9.2 (T7), 10, 11 (outcome 7)
