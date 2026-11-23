---
story: STORY-008
prd: PRD-023
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-008-audit-columns-and-outcome.plan.md
epic_branch: epic/PRD-023-mcp-and-skills
commit: pending
status: COMPLETE
completed: 2026-11-22
---

# Implementation Report - STORY-008: Audit columns, `record(mcp=)`, `record_outcome`, correlation lookup

## Summary

Eleven section 6.9 columns plus `idx_action_decisions_link` on `action_decisions` (in the CREATE and in `ACTION_DECISIONS_ADDED_COLUMNS`), `ActionDecisionRow` fields, INSERT/mapper support, `McpRecord`, fail-closed `record(..., mcp=)`, best-effort `record_outcome(..., *, user_id)`, `canonical_json` / `arguments_canonical_hash`, `database.update_action_outcome` and `database.find_linkable_v1_decision(user_id, server, tool_names, hash, window_seconds, *, now=None)`. No caller wiring (STORY-013/016/017).

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Non-DB tests (`-m "not db"`, 8 files) | 312 passed, 1 skipped (after fixing one census assertion) |
| DB tests | NOT RUN locally (Docker down); collected OK, CI runs them |
| Full suite | GitHub CI on push (user decision) |

## Not run locally (DB)
`tests/test_mcp_audit.py`: the 10 `db` tests (index columns, fresh columns, legacy convergence, mcp round trip, outcome update, missing id, correlation x4). The 94 `db` tests in `test_action_audit.py`, `test_db_resilience_write_id.py` (incl. the ALTER list), `test_audit_journal.py`, `test_admin_actions.py`, `test_actions_view.py`, `test_untouched_app.py`, `test_db_resilience_retry.py`. Census files `test_db_resilience_retry.py` (44 kinds; its non-DB census passed) and `test_db_resilience_write_id.py` / `test_action_audit.py` edits are covered by CI only for their DB parts.

## Deviations from Plan
- Added one census edit not listed: `test_db_resilience_write_id.py::test_existing_constructions_...` field-order tail now lists the eleven fields (PRD-023 comment).
- `McpRecord.audit_id` optional field per orchestrator confirmation; alias rows keep the raw `/v1` tool name.

## Acceptance Criteria
- [x] AC1 columns, index, old rows read `v1` (DB tests in CI)
- [x] AC2 `record(mcp=)` fail-closed, never journals (pure tests pass)
- [x] AC3 `record_outcome` best effort, closed vocabulary (pure tests pass)
- [x] AC4 correlation helper (DB tests in CI; signature and empty-names tests pass locally)
