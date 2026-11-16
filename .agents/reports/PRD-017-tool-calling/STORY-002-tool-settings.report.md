---
story: STORY-002
prd: PRD-017
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-002-tool-settings.plan.md
epic_branch: epic/PRD-017-tool-calling
commit: afc8079
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-002: V1_TOOLS_ENABLED and V1_TOOL_MODELS settings

**Plan**: `.agents/plans/PRD-017-tool-calling/completed/STORY-002-tool-settings.plan.md`
**Epic Branch**: `epic/PRD-017-tool-calling`
**Commit**: `afc8079`

## Summary

Added `V1_TOOLS_ENABLED: bool = False` and `V1_TOOL_MODELS: str = ""` to `Settings`, a `v1_tool_models_list` property, and a `model_validator(mode="after")` that rejects entries not in `MODEL_ALLOWLIST` (exact match; message names the setting, the offending entries and an example). The admin rule (V1_TOOL_MODELS is a capability list that applies to every role when non-empty) is in the field comment and validator docstring; the request-time check is STORY-008's. Nothing reads the settings yet.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Two fields | `app/config.py` | done |
| 2 | Cross-field validator | `app/config.py` | done |
| 3 | `v1_tool_models_list` property | `app/config.py` | done |
| 4 | Tests | `tests/test_config.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests (`test_config.py`, `test_untouched_app.py`) | 228 passed |
| E2E (default import; `V1_TOOL_MODELS=nosuch/model` fails naming setting, entry, example) | 2/2 |
| `git diff --stat .env.example` | empty |
| Full suite | deferred to orchestrator (user decision) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/config.py` | UPDATE | +50 |
| `tests/test_config.py` | UPDATE | +58 |

## Deviations from Plan

None. Optional test 6 (no role exemption) dropped: it duplicated the empty-allowlist case of test 4, whose docstring states the rule.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_config.py` | defaults; `"true"` parsing; stripped ordered list; outside-allowlist startup error (3 params); blank list parses to none (2 params) |

## Acceptance Criteria

- [x] Defaults False / "" / [] (test_tool_settings_available_with_documented_defaults)
- [x] Stripped ordered `v1_tool_models_list` (test_v1_tool_models_list_returns_stripped_names_in_order)
- [x] Unknown entry fails naming setting, entry, example (test_v1_tool_models_entry_outside_model_allowlist_is_a_startup_error)
- [x] `.env.example` unchanged
