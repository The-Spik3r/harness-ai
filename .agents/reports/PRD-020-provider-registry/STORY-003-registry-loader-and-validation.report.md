---
story: STORY-003
prd: PRD-020
plan: .agents/plans/PRD-020-provider-registry/completed/STORY-003-registry-loader-and-validation.plan.md
epic_branch: epic/PRD-020-provider-registry
commit: 5dc69fe
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report - STORY-003: Provider registry loader, validation and the legacy implicit provider

## Summary

New `app/services/provider_registry.py`: frozen dataclasses (no key field), strict-YAML loader for `PROVIDERS_FILE`, one validator per F1 rule family, `classify_base_url` (D5), the three F1 WARNINGs, per-provider key resolution held in `_keys` outside the dataclasses, and the legacy registry derived from live settings. `load()` is wired into both lifespans after `action_config.load`. `tests/_providers.py` is the file-mode fixture for later stories. No resolution or adapter code (STORY-004/005).

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests (test_provider_registry, test_action_config, test_config, test_chat_ui_startup_guard, test_untouched_app, test_prd020_legacy_fixtures) | 594 passed, 0 failed, 0 skipped |
| E2E (TestClient lifespan: empty = legacy, valid file = file mode, bad file raises ProviderRegistryError) | 3/3 |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

`app/services/provider_registry.py` (CREATE), `app/main.py`, `chat_ui/chat_ui/chat_ui.py` (UPDATE, one load call each), `tests/_providers.py` (CREATE), `tests/test_provider_registry.py` (CREATE, 85 cases).

## Deviations from Plan

- Orchestrator addition: every `roles:` entry must be a role in `authz.ROLE_PERMISSIONS` (read at call time, so an `RBAC_ROLES_FILE` override loaded earlier by `authz.load` counts); an unknown role or an empty `roles: []` is a startup error naming file, provider/model and role. Tested for provider and model level.
- Legacy builder de-duplicates repeated `MODEL_ALLOWLIST` entries (first wins). STORY-011 must keep the legacy `/v1/models` body byte-identical (STORY-001 fixtures), so the listing must not change because of this de-duplication.
- Lifespan order is checked by a source-order test plus the TestClient E2E; no new probe field was added to the chat UI startup-guard subprocess.

## Acceptance Criteria

- [x] AC1 defaults + frozen: `test_full_file_exposes_defaults`, `test_minimal_file_defaults`, `test_snapshot_is_immutable`
- [x] AC2 each F1 error, no leak: `test_startup_error[*]` (32 params), `test_errors_never_echo_key_or_url`
- [x] AC3 D5 matrix: `test_base_url_matrix`, `test_classify_base_url`
- [x] AC4 three WARNINGs: `test_warning_insecure_http`, `test_warning_internal_hostname`, `test_warning_key_env_not_secret_glob`, `test_warnings_never_fail_or_leak`, `test_failing_file_logs_no_warning`
- [x] AC5 legacy live + lifespans: `test_legacy_registry_matches_section_6_2`, `test_legacy_tracks_live_settings`, `test_lifespans_call_load_after_action_config`
- [x] AC6 fixture: `test_providers_file_restores_legacy`, `test_providers_file_restores_on_failure`
