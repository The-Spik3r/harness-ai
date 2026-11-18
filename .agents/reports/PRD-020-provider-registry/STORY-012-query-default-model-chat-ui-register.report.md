---
story: STORY-012
prd: PRD-020
plan: .agents/plans/PRD-020-provider-registry/completed/STORY-012-query-default-model-chat-ui-register.plan.md
epic_branch: epic/PRD-020-provider-registry
commit: pending
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report - STORY-012: /query default model, chat UI selector and Register provider column

## Summary

`QueryRequest.model` is `Optional[str] = None`; the router resolves None to the registry default (file mode) or the named constant `_LEGACY_DEFAULT_MODEL = "gpt-4"`. The chat selector reads the per-session `ChatState.model_options`, filled at login by `_model_choices(identity)` (`visible_models` in file mode, `MODEL_ALLOWLIST` in legacy); an empty list shows `SHELL_MODEL_NONE_NOTICE`. The Register gains a Provider head and cell after Model (`AuditRow.provider`).

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Batch 1 (query router, schemas, legacy fixtures, untouched_app) | 105 passed |
| Batch 2 (admin_models/formatting/copy/state, register, chat_shell, contrast, render_invariants, copy, startup guard) | 663 passed |
| test_chat_state.py -k "logout or model" (final) | 14 passed |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- `logout()` sets `model_options = []` unconditionally (plan: legacy list in legacy mode). `test_logout_calls_no_service_and_can_write_nothing` forbids any call in `logout`; login recomputes, and the selector is behind the sign-in gate.
- `tests/test_register.py` `_Log` stub gained `provider = None` (`to_audit_row` reads it).
- OpenAPI: the `/query` `model` property is now `anyOf [string, null]`, default null, in both modes (no test pins it).

## Modified pre-existing assertions (each commented PRD-020 STORY-012)

test_schemas `request.model is None`; test_admin_models field set and default list gain `provider`; test_register `test_the_row_gains_no_column` 10 -> 11 tracks; test_copy census gains `COLUMN_PROVIDER`.

## Acceptance Criteria

- [x] AC1 default model: new tests in test_query_router.py, test_prd020_legacy_fixtures.py unedited
- [x] AC2 selector per role: new tests in test_chat_state.py, test_chat_shell.py
- [x] AC3 provider cell and empty cell: test_admin_formatting.py, test_register.py
- [x] AC4 guards pass, strings in copy: test_copy.py, test_contrast, test_render_invariants
- [x] AC5 focus/phone width: structural asserts only (global `:focus-visible`, `_MIN_WIDTH`, overflow); no live browser pass
