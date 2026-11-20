---
story: STORY-009
prd: PRD-022
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-009-chain-config-and-startup-validation.plan.md
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
commit: pending
status: COMPLETE
completed: 2026-11-20
---

# Implementation Report - STORY-009: Chain config and startup validation

## Summary

`app/services/upstream/chain_config.py`: contract types (`Candidate`, `Chain`, `ChainLimits`, `ChainSnapshot`), pure `validate_chains` (every F3 rule, each entry compared with the primary, WARNING texts returned), and the loader (`load`, `reset`, `current`, `chain_for`, `ChainConfigError`). Four settings with validators; `load()` wired after `provider_registry.load()` in both lifespans; fixtures, docs, `.env.example`, `examples/chains.yaml`.

## Validation

| Check | Result |
|---|---|
| Backend import | OK |
| tests/test_chain_config.py | 49 passed |
| test_chain_config, test_config, test_provider_registry, test_providers_docs, test_chat_ui_startup_guard, test_untouched_app, test_main | 492 passed |
| test_chain_config, test_anthropic_primary_pipeline, test_pii_redaction_integration | 81 passed |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- An empty `PROVIDER_CHAIN_DEADLINE_SECONDS=` does not parse (float_parsing), so it stays commented out in `.env.example`, as the plan said.
- No probe field was added to `test_chat_ui_startup_guard.py`; chat UI registration order is asserted by a source-order test in `test_chain_config.py`.
- Primary-timeout deadline check runs per chain after the entries (plan order).

## Acceptance Criteria

- [x] AC1 settings + file needs PROVIDERS_FILE: `tests/test_config.py` chain tests, `test_chains_file_without_providers_file`
- [x] AC2 immutable snapshot, lookup order: `test_lookup_order`, `test_snapshot_is_immutable`, `test_example_file_loads`
- [x] AC3 every F3 rule, T1: `test_startup_error[*]`, `test_t1_third_entry_fails`
- [x] AC4 one WARNING per crossing opt-in: `test_warning_once_per_crossing_entry`, `test_no_warning_without_crossing`
- [x] AC5 no file: `test_no_file_is_prd020`
