---
story: STORY-010
prd: PRD-018
plan: .agents/plans/PRD-018-db-resilience/completed/STORY-010-audit-ref-journaled-release.plan.md
epic_branch: epic/PRD-018-db-resilience
commit: pending
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report - STORY-010: Release under a journaled record

**Plan**: `.agents/plans/PRD-018-db-resilience/completed/STORY-010-audit-ref-journaled-release.plan.md`
**Epic Branch**: `epic/PRD-018-db-resilience`
**Commit**: `pending`

## Summary

`audit_logger.log_query` returns `AuditRef(audit_id, write_id)`. A `StorageUnavailableError` on the audit insert is journaled (`audit_journal.append`) and returns `AuditRef(None, write_id)`; a failed append (or no open journal) raises `AuditUnavailableError`. STATEMENT and other non-transient `StorageError`s are not journaled. Step 8 passes `journal_decisions` so a journaled row carries its decisions in the same entry. `action_audit.record(decisions, identity, audit_ref=None, session_id=None)` keys rows `<audit write_id>:<i>`, journals a decisions-only entry when only the decisions failed, and never journals without a ref (O8). `/query` and `/v1` bodies gain `audit_ref`; a journaled success is `audit_id: null`, `X-Harness-Audit-Ref`, `chatcmpl-harness-ref-<write_id>`. `AuditUnavailableError` is `/query` 503 + `Retry-After`, `/v1` 503 `storage_unavailable` (tools: 500 `internal_error`), and a fixed chat bubble.

Orchestrator rulings applied (also in the docstrings):
- R1: a refusal row that can be neither written nor journaled is refused with 503 (also the step 7 / step 8 redaction arms 502/500 -> 503 and `/query`'s foreign-session 403 -> 503 in that case only).
- R2: an unrecordable row on a response with decisions raises `ActionAuditError` (500 `internal_error` on `/v1`, no mark).
- R3 (changed): the pipeline does not call `record()` for a journaled ref; `record()` raises `ValueError` for one. Both tested.
- R4/R5/R6 as planned (healthy headers unchanged; `Retry-After` from the `__context__` chain, else 1; decisions-only entry keyed by the row's `write_id`; `audit_journal` docstring corrected).
- UI risk 1: the chat footer shows `audit pending` (`FOOTER_AUDIT_PENDING`) instead of `#0` when `audit_id` is 0.
- UI risk 2: a distinct headline `AUDIT_UNAVAILABLE_HEADLINE` ("The harness could not record this answer.") is chosen when the bubble's detail is `AUDIT_UNAVAILABLE_NOTICE`; neither string says "before".

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `AuditRef`, journal fallback, `journal_decisions` | `app/services/audit_logger.py` | done |
| 2 | `decision_rows`, `record(audit_ref=...)`, decisions-only journal, O8 docstring | `app/services/action_audit.py` | done |
| 3 | Step 8, R2 arm, R3 skip, refusal comment | `app/services/query_pipeline.py` | done |
| 4 | `audit_ref` fields, `chat_completion_ref_id` | `app/models/schemas.py`, `app/models/v1_schemas.py` | done |
| 5 | `/v1` translation, `AUDIT_UNAVAILABLE_MESSAGE` | `app/services/v1_translate.py` | done |
| 6 | `audit_unavailable_retry_after` | `app/services/storage_faults.py` | done |
| 7 | `/query` 503 arm | `app/routers/query.py` | done |
| 8 | `/v1` mapping, header choice | `app/routers/v1.py` | done |
| 9 | Chat UI arm, copy, footer, headline | `chat_ui/chat_ui/state.py`, `copy.py`, `components/bubbles.py` | done |
| 10 | Journal docstring (R6) | `app/db/audit_journal.py` | done |
| 11 | Existing tests adapted | 17 test files | done |
| 12 | New tests | `tests/test_db_resilience_release.py`, `tests/test_chat_ui_storage_failures.py`, `tests/test_v1_translate_result.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Chat UI startup guard | passed (`tests/test_chat_ui_startup_guard.py`, 15) |
| Run A (28 files, one pytest process) | 922 passed, 1 skipped, 3 failed. The 3: `test_full_pipeline_latency_within_budget` (environmental on this machine, passes in CI) and two stale expected dicts (`test_v1_schemas::test_harness_actions_serialize_one_entry_per_decision`, `test_v1_translate_result::test_harness_carries_the_pii_fields`), fixed. Rerun of those two files plus the latency test: 104 passed, 1 failed (latency only) |
| Run B (`test_audit_logger`, `test_chat_state` whole, `test_v1_tools` `-k` subset on audit/harness/release/fields/openapi) | 180 passed, 1 failed (`test_every_bubble_append_in_do_send_goes_through_the_helper`: helper-call pin 7 -> 8 for the new bubble, fixed; rerun passed) |
| New file alone | `tests/test_db_resilience_release.py`: 35 passed |
| Full suite | GitHub CI on push (user decision) |

`tests/test_v1_tools.py` was run only as the `-k` subset above (716 of 897 tests deselected; they do not touch `audit_ref`).

## Deviations from Plan

- R3 changed by the orchestrator (above). `tests/test_audit_logger.py` unwraps `.audit_id` through one local wrapper instead of editing 22 call sites.
- `tests/test_chat_state.py::test_every_bubble_append_in_do_send_goes_through_the_helper`: helper-call pin 7 -> 8 (the new bubble), not in the plan's list.
- Rendering tests for the footer and headline run in a subprocess with the Reflex import path (the `test_chat_components_import.py` approach), because importing `chat_ui.components` in-process breaks the other test modules.
- `docs/api.md` and `docs/features.md` still describe only `X-Harness-Audit-Id` / `chatcmpl-harness-<id>`; not in this story's plan, left for the docs story.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db_resilience_release.py` | ref on success; journal on outage (canary not logged); decisions in the same entry; builder not called when healthy; journal full / no journal; statement failures not journaled; decision-row keys; `record` keyed by the ref; decisions-only entry + duplicate-pending `ValueError`; R3 `ValueError`; no journal without a ref (O8); `insert_action_decisions` never journals; decisions journal failure; step 8 journaled / same entry / decisions alone / D8 path / R2 / no-calls; refusal journaled / unrecordable (R1); `/query` journaled, 503, foreign-session 503; `/v1` journaled JSON, healthy headers, stream ids, 503, SSE error event, tools 500; `Retry-After` rule; db drain round trip |
| `tests/test_chat_ui_storage_failures.py` | fixed bubble for `AuditUnavailableError`; headline/detail do not say "before"; journaled success stores NULL; footer shows `audit pending` |
| `tests/test_v1_translate_result.py` | journaled success: null id, ref, ref completion id |

## Acceptance Criteria

- [x] AC 1: `log_query` returns `AuditRef`; journals on outage; `AuditUnavailableError` on append failure; refusal rows journal the same way (log_query and refusal tests)
- [x] AC 2: committed / decisions-alone / same-entry / D8 path (step 8 tests, db drain round trip)
- [x] AC 3: `audit_id: null` + `audit_ref` on `/query`; `harness.*`, `X-Harness-Audit-Ref`, `chatcmpl-harness-ref-<W>` on `/v1`; NULL on the transcript row (ingress tests, chat test)
- [x] AC 4: `/query` 503, `/v1` 503 (tools 500), chat bubble (ingress and chat tests)
- [x] AC 5: healthy bodies unchanged except `audit_ref`, each edit commented PRD-018 D14; `insert_action_decisions` never journals
