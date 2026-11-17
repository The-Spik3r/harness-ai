---
id: STORY-010
prd: PRD-018
slug: audit-ref-journaled-release
title: AuditRef, journaled release of step 8, PRD-017 D13 decisions path, audit_ref response fields
type: feature
priority: high
complexity: large
phase: "4 - Never lose a row"
status: done
labels: [backend, api, v1, audit]
epic_branch: epic/PRD-018-db-resilience
plan: .agents/plans/PRD-018-db-resilience/completed/STORY-010-audit-ref-journaled-release.plan.md
report: .agents/reports/PRD-018-db-resilience/STORY-010-audit-ref-journaled-release.report.md
commit: 4ab037a
depends_on: [STORY-004, STORY-006, STORY-008, STORY-009]
blocks: [STORY-011, STORY-013]
skills: []
created: 2026-11-17
updated: 2026-11-17
---

# STORY-010: Release under a journaled record

## Description

As a compliance admin, I want an answer that was already paid for to be released only once its audit row (and decisions) is committed or fsynced to the journal, so that the trail has no hole and nothing is released without a record.

## Acceptance Criteria

- [ ] Given `log_query`, when the insert succeeds, then it returns `AuditRef(audit_id=<int>, write_id=<str>)`. When the insert exhausts its retries or the breaker is open, then the entry is journaled and `AuditRef(audit_id=None, write_id=...)` is returned. When the journal append also fails, `AuditUnavailableError` propagates. Every call site in `query_pipeline.py` and `routers/query.py` is updated, and refusal rows (`_deny`, steps 2c–8 error arms) journal the same way.
- [ ] Given step 8 with tools, when `action_audit.record(decisions, identity, audit_ref, session_id)` runs, then: row committed + decisions committed → today; row committed + decisions exhausted → decisions journaled alone (`audit_id` known); row journaled → decisions journaled **in the same entry** as the row. Release happens only after commit or fsync. Journal append failing → today's PRD-017 D8 path unchanged (`mark_audit_log_failed`, `ActionAuditError`, `500 internal_error`, nothing released).
- [ ] Given a journaled success, when the response is built, then `/query` returns `audit_id: null` and `audit_ref: <write_id>`; `/v1` returns `harness.audit_id: null`, `harness.audit_ref`, header `X-Harness-Audit-Ref` instead of `X-Harness-Audit-Id`, and `id: "chatcmpl-harness-ref-<write_id>"`. `audit_ref` is present on every success; `audit_id` stays an integer whenever the row committed. The chat UI transcript row stores `audit_id` NULL for a journaled success.
- [ ] Given `AuditUnavailableError` (row neither written nor journaled), when it reaches an ingress, then `/query` returns `503` with nothing released, `/v1` returns `503 storage_unavailable` (tools: PRD-017's `500 internal_error`, unchanged), and the chat UI shows the `internal_error` bubble.
- [ ] Given a healthy database, when the existing pipeline, `/query`, `/v1` and chat UI tests run, then every response body is byte-identical except for the new `audit_ref` field (each modified assertion carries a comment citing PRD-018 D14), and `insert_action_decisions` called directly (not through `record()`) never journals.

## Technical Notes

- **Orchestrator decision (user, 2026-11-17, O8 = option a):** the journal satisfies "recorded" **only** for PRD-017's post-response release (step 8). Any pre-execution decision write (PRD-023's MCP pre-forward write) must commit to the database or fail closed. So the journaling lives in `action_audit.record()` / `log_query`, never in `database.insert_action_decisions`, and the journal API offers no other entry point. Write that rule in `record()`'s docstring citing PRD-018 O8 and PRD-023 T9.
- **Orchestrator decision (STORY-004 plan):** the `write_id` convention is `uuid.uuid4().hex` via `audit_logger._new_write_id()`. STORY-004 keys decisions as `<fresh batch hex>:<i>` because `record()` has no audit key yet. In this story, `record()` receives the `AuditRef` and keys decisions as `<audit write_id>:<i>` (PRD 6.8's example), which makes a journaled decisions entry traceable to its row. Update STORY-004's `record()` tests accordingly.
- **Orchestrator note (STORY-007 plan):** the chat UI's catch-all `except Exception` in `_do_send` (`state.py` ~`:1187-1197`) shows `str(exc)`. A storage failure on the step 8 audit write (today a bare `StorageUnavailableError` after the upstream answered) reaches it with driver text (T9). This story must make that path journal (no error), or raise `AuditUnavailableError` with a **fixed** chat bubble that does *not* say "nothing was sent" (the model was called). Pin it with a test.
- **Orchestrator decision (user, 2026-11-17, O2):** release with `audit_id: null` + `audit_ref` (the default).
- `app/services/audit_logger.py`, `app/services/action_audit.py:174`, `app/services/query_pipeline.py` (`:288`, `:893-946`, the `ActionAuditError` path `:83`), `app/routers/query.py:118`, `app/routers/v1.py:250`, `app/models/schemas.py:80` (`audit_id: Optional[int]`, `audit_ref: str`), `app/models/v1_schemas.py:26-33, 173` (`chat_completion_id`), `chat_ui/chat_ui/state.py` (transcript `audit_id`).
- `AuditRef` is a frozen dataclass. A refusal row that journals still returns the refusal response as today (refusal responses carry no `audit_id`? check, and keep each shape).
- The duplicate overlay and the headroom check are STORY-011.
- Tests: `tests/test_db_resilience_release.py` (non-`db` with storage stubbed for the branches; one `db` test with `_FaultyClient` for row-journaled + decisions), plus the existing pipeline / v1 tests the plan names.

## Dependencies

- **Blocked by**: STORY-004, STORY-006, STORY-008, STORY-009
- **Blocks**: STORY-011, STORY-013

## PRD Reference

Source: [`PRD-018-db-resilience/PRD.md`](../../PRDs/PRD-018-db-resilience/PRD.md) — sections 4 (audit_ref), 5 (stories 4, 5), 6.1, 6.7, 7 (F7), 9.2 (T5), 10, 14 (Risk 5), 15 (D13, D14), Open decisions O2, O8
