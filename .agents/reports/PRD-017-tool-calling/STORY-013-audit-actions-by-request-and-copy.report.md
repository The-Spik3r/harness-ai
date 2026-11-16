---
story: STORY-013
prd: PRD-017
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-013-audit-actions-by-request-and-copy.plan.md
epic_branch: epic/PRD-017-tool-calling
commit: pending
status: COMPLETE
completed: 2026-11-16
---

# Implementation Report — STORY-013: GET /audit/actions?audit_id= and the Actions view's empty-state copy

**Plan**: `.agents/plans/PRD-017-tool-calling/completed/STORY-013-audit-actions-by-request-and-copy.plan.md`
**Epic Branch**: `epic/PRD-017-tool-calling`
**Commit**: `pending`

## Summary

`GET /audit/actions` gains `?audit_id=` (`Query(None, ge=1)`), passed to `list_action_decisions(..., audit_id=None)`, which adds one fixed `audit_id = ?` clause ANDed with the user/decision clauses. Scoping is unchanged. The Actions view's empty body is reworded (no PRD-017, no "nothing calls the engine"; names `/v1`, "denied first", `V1_TOOLS_ENABLED`). `docs/api.md` updated.

Decisions: Q1 `id DESC` kept for the filtered list ("stored order" read as the endpoint's order); Q2 `ge=1`; Q3 docs/api.md updated here. The empty `?audit_id=` case was checked empirically: FastAPI returns 422, so it stays in the parametrization.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `audit_id` filter | `app/db/database.py` | done |
| 2 | `?audit_id=` param | `app/routers/admin.py` | done |
| 3 | router + DB tests | `tests/test_admin_actions.py`, `tests/test_action_audit.py` | done |
| 4 | empty body copy | `chat_ui/chat_ui/admin_copy.py` | done |
| 5 | docstrings | `chat_ui/chat_ui/components/actions.py` | done |
| 6 | copy test + docs | `tests/test_actions_view.py`, `docs/api.md` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests (targeted, one call) | 365 passed, 0 failed, 0 skipped (5m47s) |
| E2E (TestClient tests + chat_ui startup guard) | pass |
| Full suite | deferred to orchestrator (user decision) |

Targeted files: test_admin_actions, test_action_audit, test_actions_view, test_admin_copy, test_copy, test_admin_state, test_chat_ui_startup_guard, test_untouched_app.

## Deviations from Plan

- `docs/api.md:280` (`actions_*` stats "0 until PRD-017 calls the action policy") also reworded, same stale claim.
- No other deviations.

## Pre-existing assertions changed (approved)

- `test_default_limit_is_100`: expected kwargs gain `"audit_id": None`, PRD-017 comment.
- `test_the_empty_state_says_what_why_and_what_next`: rewritten for the new body, PRD-017 comment (name unchanged).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_admin_actions.py` | audit_id newest first; combines with decision; other user's request empty under own scope; 403; invalid 422 (-1, 0, x, 1.5, empty); passed to repository |
| `tests/test_action_audit.py` | `test_list_filters_by_audit_id` |

## Acceptance Criteria

- [x] audit_id filter, newest first, combines with decision
- [x] own scope -> empty; neither permission -> 403; bad value -> 422
- [x] empty body reworded, test updated with PRD-017 comment
- [x] backend import OK; chat_ui startup guard passes
