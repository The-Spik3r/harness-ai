---
story: STORY-010
prd: PRD-022
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-010-provider-breakers-health.plan.md
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
commit: pending
status: COMPLETE
completed: 2026-11-20
---

# Implementation Report - STORY-010: Provider breakers and providers_status()

## Summary

New pure module `app/services/upstream/health.py`: one PRD-018 `CircuitBreaker` per provider (`probe=None`, 5 failures, 10 s, misconfigured 300 s), `record` (PRD-022 6.2/F6 rules), `admit`, `sync`, counters, `providers_status(names)`. Two additive `circuit_breaker.py` edits plus `transition_log_level`. Nothing wired into the pipeline.

## Validation

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests | 209 passed (test_provider_health, test_circuit_breaker, test_db_resilience_breaker, test_upstream_error_fields, test_untouched_app, test_storage_status, test_db_check_ready, test_prd022_spike_anthropic_sdk) |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

- CREATE `app/services/upstream/health.py`, `tests/test_provider_health.py`
- UPDATE `app/services/circuit_breaker.py` (`BreakerOpen.state`, `force_open(failure_class=)`, `transition_log_level`), `tests/conftest.py` (autouse `_fresh_provider_health`), `tests/test_circuit_breaker.py` (3 added tests)
- UPDATE `tests/test_prd022_spike_anthropic_sdk.py`: the STORY-001 signature snapshot of `CircuitBreaker.__init__` / `force_open` now lists the new additive parameters (commented, PRD-022 STORY-010).

## Deviations from Plan

- The spike signature-snapshot test needed the update above (not named in the plan; a PRD-022 test, not PRD-015/017/020/021).
- `sync`/`providers_status` take caller-supplied names (orchestrator-confirmed).

## Acceptance Criteria

- [x] Lazy, thread-safe, constants, pruning: `test_breaker_*`, `test_sync_prunes_absent_providers`
- [x] Recording rules: `test_record_*`, `test_a_300s_window_survives_a_429`, `test_concurrent_extends_never_shorten`
- [x] admit incl. two threads: `test_admit_*`, `test_two_threads_after_the_window_admit_exactly_one`
- [x] providers_status shape, counters, no I/O: `test_providers_status_*`, `test_counters*`
- [x] Transition log, one WARNING each, no text: `test_every_transition_is_one_warning_naming_kind_never_text`, `test_circuit_breaker.py::test_transition_log_level_overrides_and_the_default_is_unchanged`, `test_force_open_names_the_failure_class`
