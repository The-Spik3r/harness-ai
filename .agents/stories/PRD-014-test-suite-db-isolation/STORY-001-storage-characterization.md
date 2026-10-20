---
id: STORY-001
prd: PRD-014
slug: storage-characterization
title: "Characterize the suite's storage use: baseline run, driver calls per test, census and undeclared-storage list"
type: technical
priority: high
complexity: small
phase: "1 - Measure and mark"
status: done
labels: [tests, characterization, libsql]
epic_branch: epic/PRD-014-test-suite-db-isolation
plan: .agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-001-storage-characterization.plan.md
report: .agents/reports/PRD-014-test-suite-db-isolation/STORY-001-storage-characterization.report.md
commit: 398e60e
depends_on: []
blocks: [STORY-002, STORY-003]
skills: []
created: 2026-10-20
updated: 2026-10-20
---

# STORY-001: Characterize the suite's storage use

## Description

As the PRD-014 implementer, I want to know which tests reach storage and how, measured on untouched `main`, so that the marker, the guard and the explicit list are built from data, and the "counts unchanged" criteria have a baseline to compare against.

## Acceptance Criteria

- [ ] Given untouched `main`, when the full suite runs once, then the report records the collected total, passed, failed, errored and skipped counts, plus the wall time. Any failure is listed with its nodeid and error. That run is the baseline every later story compares against.
- [ ] Given an uncommitted scratch plugin loaded with `-p` that wraps `libsql.connect` and counts calls per test, when the full suite runs under it, then the report records the total driver calls per run and the storage-fixture census: tests and modules requesting any of `temp_db`, `database_url`, `uninitialized_db`, `database_url_factory`, `db_connect` (transitively, via `item.fixturenames`), tests requesting none, and modules mixing both.
- [ ] Given the same run, when tests with at least one driver call are cross-referenced with the census, then the report lists **every test that issues driver calls without a storage fixture**, grouped by module. Each test is flagged if its file is one of the six PRD-006 suites in `tests/test_untouched_app.py::_UNMODIFIED_SUITES`. Driver calls from the autouse `_never_the_configured_database` reset are excluded from this classification.
- [ ] Given every autouse fixture in `tests/conftest.py` and in test modules, when each is read, then the report has a table saying whether it touches storage (expected: only `_never_the_configured_database` and the session `_libsql_endpoint`).
- [ ] Given every test that spawns a subprocess and requests no storage fixture, when its child's environment and code path are read, then the report states whether the child reaches storage. Any that do are added to the undeclared list.
- [ ] Given the story's diff, when reviewed, then it contains only the report (and optionally a note in `.agents/`). No file under `tests/`, `app/` or `chat_ui/` changes, and the scratch plugin is not committed.

## Technical Notes

- Counting driver calls: the scratch plugin's proxy must attribute calls to the *running* test, not the one that built the client, because `_shared_client()` caches one client across tests (PRD Section 6.6). It needs a `pytest_runtest_setup`/`teardown` pair that sets a current-nodeid pointer. To separate the reset's calls from the test's own, set a flag around `_reset_database()` by wrapping it from the plugin (e.g. `monkeypatch`-free: replace `tests.conftest._reset_database` in `pytest_configure`).
- The brief's figures (2026-10-14) are expected values only: 3,453 tests; 1,090 / 2,363; 47 of 91 modules; 27 mixed; ~40,000 calls. Record the new numbers. Later stories cite this report.
- The subprocess candidates found by grep: `test_admin_shell.py`, `test_chat_components_import.py`, `test_chat_shell.py`, `test_chat_ui_startup_guard.py`, `test_conftest_fixtures.py`, `test_context_limit_bubble.py`, `test_ground.py`, `test_history_off_integration.py`, `test_measure_pii_latency.py`, `test_measure_usage_latency.py`, `test_pii_redaction_integration.py`, `test_query_session_id.py`, `test_register.py`, `test_render_invariants.py`, `test_reports_e2e.py`, `test_reports_pages.py`, `test_session_rail.py`, `test_spike_pii_placeholders.py`, `test_summary.py`, `test_two_instance_smoke.py`, `test_untouched_app.py`, `test_usage_bubble.py`, `test_usage_view.py`. Only the non-storage tests among them need reading.
- Expect flaky `STREAM_EXPIRED` / `os error 10060` failures (the subject of this PRD). Rerun a flaked test alone to confirm it before recording it, and keep the flake itself in the report.
- The env recipe (venv, libsql container) is in the harness-ai test-env memory.
- Skills: none applicable. No UI surface.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-002, STORY-003

## PRD Reference

Source: [`PRD-014-test-suite-db-isolation/PRD.md`](../../PRDs/PRD-014-test-suite-db-isolation/PRD.md) — sections 4 (Baseline), 7 (F1), 11 (MVP definition), 14 (R1–R3)
