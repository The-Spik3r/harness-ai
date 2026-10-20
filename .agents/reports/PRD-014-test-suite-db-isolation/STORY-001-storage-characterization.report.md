---
story: STORY-001
prd: PRD-014
plan: .agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-001-storage-characterization.plan.md
epic_branch: epic/PRD-014-test-suite-db-isolation
commit: pending
status: COMPLETE
completed: 2026-10-20
---

# Implementation Report — STORY-001: Characterize the suite's storage use

**Plan**: `.agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-001-storage-characterization.plan.md`
**Epic Branch**: `epic/PRD-014-test-suite-db-isolation`
**Base**: `main` @ `728dd60` (the PRD-013 merge)
**Commit**: `pending`

## Summary

Measured on untouched `main`, with no file under `tests/`, `app/` or `chat_ui/` changed. Two full runs and one targeted child-process check:

- **Run A (baseline):** 3,854 collected, 3,825 passed, 1 failed, 1 error, 27 skipped, 339.6 s. Both failures are `STREAM_EXPIRED` flakes and pass alone. **Baseline for every later story: 3,854 collected, 3,827 passing, 27 skipped.**
- **Run B (instrumented):** the same suite with a scratch `-p storage_census` plugin. 3,827 passed and 27 skipped, identical to Run A once the flakes are counted as passes, so the instrument changed nothing. **52,980 driver calls per run**: 18,014 from the autouse reset, 34,964 from the tests themselves and 2 from the endpoint probe.
- **Census:** 1,262 tests request a storage fixture and 2,592 request none. Of 100 modules, 55 have a storage test, 45 have none, and **33 are mixed**.
- **Undeclared storage: 7 tests in 4 modules reach storage in-process without a storage fixture, and 21 more in `test_chat_shell.py` reach it through a child process.** Three of the in-process tests are in PRD-006 suites (`test_admin_auth.py` ×2, `test_db.py` ×1).
- **Autouse audit:** of the 18 autouse fixtures, only `_libsql_endpoint` and `_never_the_configured_database` touch storage in-process, as expected. One module fixture, `test_two_instance_smoke.py::fresh_schema`, reaches storage through child processes, but it requests `database_url_factory` transitively, so its tests are already storage tests.

The brief's figures are out of date because PRD-013 added about 400 tests (see *Brief vs measured*). Nothing in them contradicts the PRD's design. The undeclared list is much shorter than R1 feared.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Preflight: PRD-013 in `main`, epic branch created, PRD docs and plan committed, environment checked | — (`91937c5`, `16eda3f`) | ✅ |
| 1 | Baseline Run A, flakes rerun alone | scratch `runA.*` | ✅ |
| 2 | Scratch plugin, smoke-tested | scratch `storage_census.py` | ✅ |
| 3 | Instrumented Run B, compared with Run A | scratch `runB.*`, `census.json` | ✅ |
| 4 | Analysis, plus how each undeclared test reaches storage | scratch `analyze.py`, `analysis.md` | ✅ |
| 5 | Autouse audit | this report | ✅ |
| 6 | Subprocess audit, read **and** checked with a dead inherited `DATABASE_URL` | scratch `child2.*`, `childprobe/` | ✅ |
| 7 | Report and diff check | this report | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Run A completes, counts and wall time recorded | ✅ 3,825 passed, 1 failed + 1 error (both confirmed flakes), 27 skipped, 339.6 s |
| Run B = Run A apart from confirmed flakes | ✅ 3,827 passed, 27 skipped, 3,854 collected, 302.4 s |
| `census.json` item count = collected count | ✅ 3,854 = 3,854 |
| Cached-client attribution (plan E2E 3) | ✅ smoke run: the second `test_conftest_fixtures.py` test, served by the client the first one built, records its own 14 calls |
| Undeclared counts add up; PRD-006 flags match `_UNMODIFIED_SUITES` | ✅ 2 + 1 + 1 + 3 = 7; flags on `test_admin_auth.py` and `test_db.py` only |
| `tests/test_admin_auth.py` on the list (PRD story 5) | ✅ 2 of its 9 tests |
| `git diff --stat HEAD -- tests app chat_ui` | ✅ empty |
| Backend import / frontend lint | n/a. No application code changed |
| Tests written | n/a. AC 6 forbids changes under `tests/`. The instrument was validated by the smoke run and by Run A/B parity |

## Environment

| Item | Value |
|---|---|
| Python | 3.11.17 (`C:\Users\tobip\.venvs\harness-ai`) |
| pytest | 9.1.1 |
| libsql | 0.1.11 |
| libSQL server | `ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb27…3a67`, container `harness-libsql-dev` at `http://127.0.0.1:8080` |
| Docker Desktop | engine 29.9.1 (the PRD records 29.8.2) |
| spaCy models | `en_core_web_lg`, `en_core_web_sm` both present |
| Other sessions on the container | None running pytest during the runs (checked with the process list) |
| Command (both runs) | `python -m pytest tests/ -q -rfEs -p no:cacheprovider --junitxml=…`, plus `-p storage_census` with `PYTHONPATH="<scratch>;."` for Run B |

## Baseline run (AC 1)

Run A on `728dd60`, nothing loaded.

| Collected | Passed | Failed | Errors | Skipped | Wall time |
|---:|---:|---:|---:|---:|---:|
| 3,854 | 3,825 | 1 | 1 | 27 | 339.6 s (pytest), 341 s (shell) |

| Nodeid | Phase | Error | Alone |
|---|---|---|---|
| `tests/test_manage_users_cli.py::test_set_limits_default_clears_the_column_to_null[default---token-budget-token_budget_daily]` | call | `StorageError: Hrana: api error: status=400 … "The stream has expired due to inactivity","code":"STREAM_EXPIRED"` in `init_db()` (`app/db/database.py:720`) | passed |
| `tests/test_chat_state.py::test_chat_state_send_usage_limit_renders_a_usage_limit_bubble[requests]` | setup | same `STREAM_EXPIRED`, in `init_db()` → `CREATE_AUDIT_LOGS_TABLE` (`app/db/database.py:718`) | passed |

Both are the PRD's subject: a stream died mid-statement and `_translated()` correctly refused to retry it. **The baseline is therefore 3,854 collected, 3,827 passing, 27 skipped, 0 real failures.** The 27 skips are 25 in `test_reports_e2e.py` (opt-in, no `REPORTS_E2E_URL`), 1 benchmark (`--run-benchmark`) and 1 manual slow smoke (`HARNESS_SLOW_SMOKE`).

## Driver calls and census (AC 2)

### Driver calls per run (Run B)

**52,980 driver calls.** A driver call is every `libsql.connect` plus every method called on a driver connection or on a cursor from `connection.cursor()`. Reads on the result of `connection.execute()` are not counted. They are served from the fetched result, so the round-trip figure is the same 52,980.

| Bucket | Calls | Meaning |
|---|---:|---|
| test | 34,964 | the test's own setup, call and teardown, including storage fixtures and module fixtures |
| reset | 18,014 | inside the autouse `_never_the_configured_database` |
| endpoint | 2 | the session probe in `_libsql_endpoint`, on the first test |
| outside any test | 0 | — |

| Method | Calls |
|---|---:|
| `conn.execute` | 39,489 |
| `conn.commit` | 13,382 |
| `conn.rollback` | 87 |
| `connect` | 22 |

By phase: setup 34,320, call 18,660, teardown 0.

**Split by kind of test** (the input to PRD success criterion 6):

| | reset | test | endpoint | Total |
|---|---:|---:|---:|---:|
| storage-fixture tests (1,262) | 12,176 | 34,868 | — | 47,044 |
| no-fixture tests (2,592) | 5,838 | 96 | 2 | 5,936 |

So the calls STORY-003 removes are the 5,838 resets on non-storage tests, about 2.25 per test (one `SELECT` from `sqlite_master` on an empty database, then a commit). The 96 own calls move to `db` with the 7 tests that make them. Expected full-run figure after STORY-003: about 47,000 plus the resets those 7 tests gain.

**Slowest calls and driver errors.** Run B was green, yet it contained one real stall:

| Test | Phase | Bucket | Method | Seconds | Error |
|---|---|---|---|---:|---|
| `tests/test_chat_state.py::test_every_bubble_kind_is_persisted[context_limit]` | call | test | `conn.execute` | **15.046** | `STREAM_EXPIRED` |
| `tests/test_db.py::test_init_db_fails_fast_against_an_unreachable_endpoint` | call | test | `conn.execute` | 2.046 | `tcp connect error … actively refused` (intended: `http://127.0.0.1:1`) |
| `tests/test_main.py::test_lifespan_fails_when_the_database_is_unreachable` | call | test | `conn.execute` | 2.031 | same, intended |

Every other call took ≤ 1.02 s, and all but one took ≤ 0.31 s. The 15.05 s stall matches the PRD's evidence: the same 15 s, ending in `STREAM_EXPIRED`. It is the first one recorded **inside a test that still passed**. See *Observations*.

### Storage-fixture census

Measured from `item.fixturenames` (the transitive closure) against `temp_db`, `database_url`, `uninitialized_db`, `database_url_factory` and `db_connect`.

| Measure | Value |
|---|---:|
| tests collected | 3,854 |
| tests requesting a storage fixture | **1,262** |
| tests requesting none | **2,592** |
| modules | 100 |
| modules with ≥ 1 storage test | 55 |
| modules with no storage test | 45 |
| mixed modules | **33** |

| Fixture (transitive) | Tests |
|---|---:|
| `database_url` | 1,163 |
| `temp_db` | 1,093 |
| `database_url_factory` | 101 |
| `uninitialized_db` | 68 |
| `db_connect` | 27 |

**Mixed modules (33), storage / none:** `test_admin_shell.py` 16/86, `test_audit_characterization.py` 27/12, `test_audit_stats_prd013.py` 13/4, `test_auth_dependencies.py` 5/6, `test_chat_history.py` 24/34, `test_chat_outcomes_regression.py` 21/1, `test_chat_sessions.py` 96/32, `test_chat_state.py` 122/25, `test_chat_ui_startup_guard.py` 9/2, `test_db.py` 157/77, `test_identity.py` 15/13, `test_main.py` 17/2, `test_migrate_to_turso_cli.py` 19/2, `test_pattern_corpus.py` 5/58, `test_pattern_default_config_regression.py` 6/2, `test_pii_characterization.py` 8/17, `test_pii_dedup_isolation.py` 12/7, `test_pii_redaction_integration.py` 14/3, `test_query_pipeline_audit_fields.py` 31/7, `test_query_pipeline_break_glass.py` 16/10, `test_query_pipeline_dedup_key.py` 11/2, `test_query_pipeline_multiturn.py` 22/3, `test_query_pipeline_patterns.py` 23/1, `test_query_pipeline_pii_profiles.py` 72/3, `test_query_pipeline_run_conversation.py` 14/4, `test_query_pipeline_session_passthrough.py` 16/1, `test_query_session_id.py` 23/3, `test_render_invariants.py` 58/1, `test_session_ownership.py` 20/9, `test_spike_pii_placeholders.py` 7/78, `test_usage_bubble.py` 6/7, `test_usage_limits.py` 1/33, `test_usage_view.py` 5/47.

The full per-module table follows.

<details>
<summary>All 100 modules (storage / none)</summary>

| Module | Storage | None | Mixed |
|---|---:|---:|---|
| `tests/test_admin_auth.py` | 0 | 9 |  |
| `tests/test_admin_copy.py` | 0 | 5 |  |
| `tests/test_admin_formatting.py` | 0 | 47 |  |
| `tests/test_admin_models.py` | 0 | 10 |  |
| `tests/test_admin_palette.py` | 0 | 19 |  |
| `tests/test_admin_shell.py` | 16 | 86 | yes |
| `tests/test_admin_state.py` | 0 | 119 |  |
| `tests/test_audit_characterization.py` | 27 | 12 | yes |
| `tests/test_audit_logger.py` | 22 | 0 |  |
| `tests/test_audit_router.py` | 13 | 0 |  |
| `tests/test_audit_session_id.py` | 3 | 0 |  |
| `tests/test_audit_stats_prd013.py` | 13 | 4 | yes |
| `tests/test_auth_dependencies.py` | 5 | 6 | yes |
| `tests/test_authz.py` | 0 | 32 |  |
| `tests/test_chat_components_import.py` | 0 | 4 |  |
| `tests/test_chat_history.py` | 24 | 34 | yes |
| `tests/test_chat_history_send.py` | 8 | 0 |  |
| `tests/test_chat_outcomes_regression.py` | 21 | 1 | yes |
| `tests/test_chat_sessions.py` | 96 | 32 | yes |
| `tests/test_chat_shell.py` | 0 | 38 |  |
| `tests/test_chat_state.py` | 122 | 25 | yes |
| `tests/test_chat_ui_startup_guard.py` | 9 | 2 | yes |
| `tests/test_config.py` | 0 | 165 |  |
| `tests/test_conftest_fixtures.py` | 16 | 0 |  |
| `tests/test_context_limit_bubble.py` | 0 | 5 |  |
| `tests/test_contrast.py` | 0 | 93 |  |
| `tests/test_conversation_key.py` | 0 | 12 |  |
| `tests/test_copy.py` | 0 | 65 |  |
| `tests/test_db.py` | 157 | 77 | yes |
| `tests/test_dedup_key.py` | 0 | 25 |  |
| `tests/test_duplicate_characterization.py` | 5 | 0 |  |
| `tests/test_duplicate_checker.py` | 26 | 0 |  |
| `tests/test_duplicate_scope.py` | 22 | 0 |  |
| `tests/test_formatting.py` | 0 | 43 |  |
| `tests/test_ground.py` | 0 | 28 |  |
| `tests/test_history_off_integration.py` | 9 | 0 |  |
| `tests/test_identity.py` | 15 | 13 | yes |
| `tests/test_integration.py` | 14 | 0 |  |
| `tests/test_main.py` | 17 | 2 | yes |
| `tests/test_manage_users_cli.py` | 32 | 0 |  |
| `tests/test_measure_pii_latency.py` | 0 | 59 |  |
| `tests/test_measure_usage_latency.py` | 0 | 12 |  |
| `tests/test_messages.py` | 0 | 50 |  |
| `tests/test_migrate_to_turso_cli.py` | 19 | 2 | yes |
| `tests/test_openrouter_client.py` | 0 | 53 |  |
| `tests/test_pattern_characterization.py` | 0 | 22 |  |
| `tests/test_pattern_config.py` | 0 | 64 |  |
| `tests/test_pattern_corpus.py` | 5 | 58 | yes |
| `tests/test_pattern_default_config_regression.py` | 6 | 2 | yes |
| `tests/test_pattern_detector.py` | 0 | 24 |  |
| `tests/test_pattern_fenced_blocks.py` | 0 | 128 |  |
| `tests/test_pattern_matching.py` | 0 | 62 |  |
| `tests/test_pattern_profiles.py` | 0 | 46 |  |
| `tests/test_pii_badge.py` | 0 | 2 |  |
| `tests/test_pii_characterization.py` | 8 | 17 | yes |
| `tests/test_pii_code_corpus.py` | 0 | 71 |  |
| `tests/test_pii_corpus_files.py` | 0 | 25 |  |
| `tests/test_pii_dedup_isolation.py` | 12 | 7 | yes |
| `tests/test_pii_pattern_analyzer.py` | 0 | 34 |  |
| `tests/test_pii_policy.py` | 0 | 20 |  |
| `tests/test_pii_redaction_integration.py` | 14 | 3 | yes |
| `tests/test_pii_redactor.py` | 0 | 8 |  |
| `tests/test_pii_structure_safe.py` | 0 | 112 |  |
| `tests/test_pipeline_concurrency.py` | 5 | 0 |  |
| `tests/test_pipeline_executor.py` | 0 | 9 |  |
| `tests/test_query_outcomes_regression.py` | 10 | 0 |  |
| `tests/test_query_pipeline_audit_fields.py` | 31 | 7 | yes |
| `tests/test_query_pipeline_authorization.py` | 10 | 0 |  |
| `tests/test_query_pipeline_break_glass.py` | 16 | 10 | yes |
| `tests/test_query_pipeline_context_limit.py` | 13 | 0 |  |
| `tests/test_query_pipeline_dedup_key.py` | 11 | 2 | yes |
| `tests/test_query_pipeline_multiturn.py` | 22 | 3 | yes |
| `tests/test_query_pipeline_patterns.py` | 23 | 1 | yes |
| `tests/test_query_pipeline_pii_profiles.py` | 72 | 3 | yes |
| `tests/test_query_pipeline_run_conversation.py` | 14 | 4 | yes |
| `tests/test_query_pipeline_session_passthrough.py` | 16 | 1 | yes |
| `tests/test_query_pipeline_usage_limits.py` | 37 | 0 |  |
| `tests/test_query_router.py` | 41 | 0 |  |
| `tests/test_query_session_id.py` | 23 | 3 | yes |
| `tests/test_rbac.py` | 16 | 0 |  |
| `tests/test_register.py` | 0 | 205 |  |
| `tests/test_render_invariants.py` | 58 | 1 | yes |
| `tests/test_reporting_invariance.py` | 9 | 0 |  |
| `tests/test_reports_e2e.py` | 0 | 25 |  |
| `tests/test_reports_pages.py` | 0 | 42 |  |
| `tests/test_reports_service.py` | 0 | 47 |  |
| `tests/test_route_reservations.py` | 0 | 2 |  |
| `tests/test_schemas.py` | 0 | 37 |  |
| `tests/test_session_ownership.py` | 20 | 9 | yes |
| `tests/test_session_rail.py` | 0 | 43 |  |
| `tests/test_spike_pii_placeholders.py` | 7 | 78 | yes |
| `tests/test_stats_router.py` | 11 | 0 |  |
| `tests/test_success_metadata_footer.py` | 0 | 4 |  |
| `tests/test_summary.py` | 0 | 66 |  |
| `tests/test_two_instance_smoke.py` | 16 | 0 |  |
| `tests/test_untouched_app.py` | 0 | 9 |  |
| `tests/test_usage_bubble.py` | 6 | 7 | yes |
| `tests/test_usage_limits.py` | 1 | 33 | yes |
| `tests/test_usage_storage.py` | 13 | 0 |  |
| `tests/test_usage_view.py` | 5 | 47 | yes |

</details>

**Storage-fixture tests with no driver call of their own (89, informational).** `test_render_invariants.py` 58, `test_admin_shell.py` 16, `test_chat_ui_startup_guard.py` 9, `test_two_instance_smoke.py` 3, and one each in `test_conftest_fixtures.py`, `test_identity.py` and `test_pipeline_concurrency.py`. Nearly all request `database_url_factory` to hand a URL to a child process. Their storage access is real but out of process. They are correctly `db` by fixture.

## Undeclared storage (AC 3)

Tests with ≥ 1 driver call in the `test` bucket and no storage fixture. Calls from the autouse reset are excluded by construction (bucket `reset`).

### In-process (Run B): 7 tests in 4 modules

| Module | Undeclared / no-fixture tests in module | PRD-006 |
|---|---:|---|
| `tests/test_admin_auth.py` | 2 / 9 | **yes** |
| `tests/test_db.py` | 1 / 77 | **yes** |
| `tests/test_main.py` | 1 / 2 | |
| `tests/test_measure_usage_latency.py` | 3 / 12 | |

| Test | Calls | How it reaches storage |
|---|---:|---|
| `tests/test_admin_auth.py::test_incorrect_bearer_token_rejected[/fake-audit]` **(PRD-006)** | 2 (`execute`, `commit`) | `TestClient` → `require_admin_token` → `identity.resolve()` → `find_user_by_token_hash()` (`app/services/identity.py:83`) via `get_connection()`. Passes on the reset's empty database |
| `tests/test_admin_auth.py::test_incorrect_bearer_token_rejected[/fake-stats]` **(PRD-006)** | 2 | same |
| `tests/test_db.py::test_init_db_fails_fast_against_an_unreachable_endpoint` **(PRD-006)** | 2 (`connect`, `execute`) | points `settings.DATABASE_URL` at `http://127.0.0.1:1` and calls `init_db()`. The driver call against a dead port is the subject of the test |
| `tests/test_main.py::test_lifespan_fails_when_the_database_is_unreachable` | 2 (`connect`, `execute`) | same, through `TestClient(app)`'s lifespan |
| `tests/test_measure_usage_latency.py::test_a_short_run_reports_both_calls_and_cleans_up` | 38 | in-process `bench.main()`: `database.init_db()` (`scripts/measure_usage_latency.py:352`), `usage_limits.admit` and `charge`, and a cleanup through `get_connection()` |
| `tests/test_measure_usage_latency.py::test_a_refused_admit_ends_the_run_without_a_report` | 16 | same, ending at the refused admit |
| `tests/test_measure_usage_latency.py::test_a_changed_statement_count_ends_the_run_without_a_report` | 34 | same |

Every call happened in the `call` phase, so no module fixture reaches storage undeclared, and none of these comes from a lingering thread (risk R-5 did not occur).

### Through a child process (Task 6): 21 tests in 1 module

| Module | Tests | How |
|---|---:|---|
| `tests/test_chat_shell.py` | 21 of 38 (every test requesting the module-scoped `probe`) | The probe child runs `from chat_ui.chat_ui import index` with `chat_ui/` first on `PYTHONPATH`, which imports the app module. `chat_ui/chat_ui/chat_ui.py:39` calls `init_db()` at import, which runs `check_database_reachable()` and the schema DDL against the inherited `DATABASE_URL`, i.e. `_ENDPOINT`, the local dev server. Unlike `test_reports_pages.py:300`, the probe does not set `DB_BOOTSTRAP_ENABLED=false` |

Neither guard sees these 21 tests: they make no driver call in-process. They matter to STORY-004 (see *For later stories*).

## Autouse audit (AC 4)

Every `autouse=True` fixture in `tests/conftest.py` and in test modules. No `usefixtures` appears anywhere in `tests/`.

| Fixture | File:line | Scope | What it does | Touches storage |
|---|---|---|---|---|
| `_libsql_endpoint` | `tests/conftest.py:169` | session | `libsql.connect(_ENDPOINT).execute("SELECT 1")` | **yes** (2 calls per run, `endpoint` bucket) |
| `_never_the_configured_database` | `tests/conftest.py:192` | function | patches `settings.DATABASE_URL`, `_reset_database()` | **yes** (18,014 calls, `reset` bucket) |
| `_default_pattern_policy` | `tests/conftest.py:223` | function | patches two settings, saves and restores `pattern_config._policy` | no |
| `_default_pii_policy` | `tests/conftest.py:249` | function | saves and restores `pii_policy._policies` | no |
| `_no_usage_read` | `tests/test_admin_state.py:397` | function | replaces `admin_state.usage_snapshot` with `lambda: []`, which *prevents* a read | no |
| `_shipped_settings` | `tests/test_audit_characterization.py:154` | function | settings, `authz.ROLE_PERMISSIONS`, stubs `redact`, `pii_policy.load()` | no |
| `_default_profile_is_chat` | `tests/test_pattern_config.py:73` | function | one setting | no |
| `_default_profile_is_chat` | `tests/test_pattern_profiles.py:52` | function | one setting | no |
| `_shipped_pii_settings` | `tests/test_pii_characterization.py:76` | function | settings, loads the spaCy analyzer | no |
| `_shipped_code_settings` | `tests/test_pii_code_corpus.py:84` | function | settings, `pii_policy.load()` | no |
| `_small_model_and_reset` | `tests/test_pii_pattern_analyzer.py:30` | function | settings, clears redactor singletons | no |
| `_small_model_and_reset` | `tests/test_pii_redactor.py:13` | function | same | no |
| `_small_model_and_reset` | `tests/test_pii_structure_safe.py:46` | function | same | no |
| `_warm_presidio` | `tests/test_pipeline_concurrency.py:81` | function | `pii_redactor.load()` | no |
| `_reset_executor` | `tests/test_pipeline_executor.py:18` | function | `pipeline_executor.shutdown()` before and after | no |
| `_shipped_code_policy` | `tests/test_query_pipeline_pii_profiles.py:83` | function | settings, `pii_policy.load()` | no |
| `_shipped_code_policy` | `tests/test_spike_pii_placeholders.py:41` | function | same | no |
| `fresh_schema` | `tests/test_two_instance_smoke.py:809` | function | sends `init_db` to two child instances | **out of process only**. It depends on `instances` → `database_url_factory`, so every test in the module is already a storage test |

Evidence for each "no": the bodies above call no storage function. `pii_policy`, `pii_redactor` and `pipeline_executor` import nothing from `app.db`. `authz` imports `count_active_users`, but the fixture only patches a dict. Run B agrees: no module that has one of these fixtures and no storage test shows calls in the `test` bucket.

## Subprocess audit (AC 5)

Files that spawn a process (`subprocess.`, `Popen`, `sys.executable`, `pytester`) on the base: the story's 23 candidates minus 4 (`test_conftest_fixtures.py`, `test_context_limit_bubble.py`, `test_history_off_integration.py` and `test_usage_bubble.py` spawn nothing). `tests/conftest.py` matched only on prose (`:297`).

**Method.** Each child's `env=` and script were read. Then all 17 runnable modules were rerun with `DATABASE_URL=http://127.0.0.1:9` exported. The parent's tests still use `_ENDPOINT` through `settings` (patched by the autouse fixture). A child that inherits the environment and touches storage gets a dead URL and fails. Children of storage tests receive an explicit URL (`child_db_env()` / `database_url_factory`) and are unaffected. **Result: 768 passed, 21 errors, all `test_chat_shell.py`'s `probe`, with `DatabaseUnreachableError: Cannot reach the database at http://127.0.0.1:9`.** A direct run of that probe script with `libsql.connect` traced confirms one `connect('http://127.0.0.1:9')`.

The first attempt at this check passed everything and was void. `tests/test_spike_pii_placeholders.py:26` imports `scripts.spike_pii_placeholders` at collection, and its import-time `_bootstrap_environment()` (`scripts/spike_pii_placeholders.py:110,116`) overwrites `os.environ["DATABASE_URL"]` for the rest of the session. The rerun excluded that module, and its two children were read instead.

| File | Non-storage tests that spawn | Child reaches storage? | Evidence |
|---|---|---|---|
| `test_chat_shell.py` | 21 (`probe`) | **yes**, `_ENDPOINT` | imports the app module → `init_db()` at import; failed with the dead URL |
| `test_chat_components_import.py` | 4 (`probe`) | no | imports component modules only; passed with the dead URL |
| `test_ground.py` | all `probe` users | no | component factories only; passed |
| `test_register.py` | all `probe` users | no | `components.register` only; passed |
| `test_summary.py` | all `probe` users | no | `components.summary` only; passed |
| `test_session_rail.py` | `probe` users and `_render_with_flag` (2 tests) | no | `components.session_rail` with `CHAT_HISTORY_ENABLED` set; passed |
| `test_reports_pages.py` | `pages_probe` users | no | imports the app but sets `DB_BOOTSTRAP_ENABLED=false` (`:300`), so `init_db()` returns first; passed |
| `test_measure_pii_latency.py` | `test_importing_the_script_builds_no_analyzer` | no | import only; passed |
| `test_measure_usage_latency.py` | `test_importing_the_script_opens_no_connection`, `test_run_as_a_program_a_remote_endpoint_is_refused_before_settings_load` | no | the first asserts `database._client is None` in the child. The second is refused before `Settings()` loads. Both passed |
| `test_spike_pii_placeholders.py` | `test_the_spike_is_not_collected`, `test_importing_the_spike_builds_no_analyzer_and_opens_no_connection` | no | the first runs `pytest --collect-only scripts`, which collects nothing, loads no `tests/conftest.py` and instantiates no fixture. The second asserts `database._client is None` in the child (read, not run with the dead URL, see above) |
| `test_untouched_app.py` | the `_git()` callers | no | `git` only |
| `test_reports_e2e.py` | all | not run | opt-in. Skips without `REPORTS_E2E_URL`. The documented server uses `DB_BOOTSTRAP_ENABLED=false` |
| `test_admin_shell.py`, `test_chat_ui_startup_guard.py`, `test_pii_redaction_integration.py`, `test_query_session_id.py`, `test_render_invariants.py`, `test_two_instance_smoke.py`, `test_usage_view.py` | the non-storage tests among them spawn nothing | n/a | every spawning test requests a storage fixture and passes the URL explicitly; all passed with the dead URL |

Per PRD 9.1, the one storage-reaching child can only reach `_ENDPOINT`, never a configured database: `conftest.py` sets `DATABASE_URL` with `setdefault`, and the spike script's leak writes the same value.

## Brief vs measured

| Figure | Brief (2026-10-14) | Measured (2026-10-20, `728dd60`) |
|---|---:|---:|
| tests collected | 3,453 | 3,854 |
| storage-fixture / none | 1,090 / 2,363 | 1,262 / 2,592 |
| share without a storage fixture | 68% | 67% |
| modules with a storage test / all | 47 / 91 | 55 / 100 |
| mixed modules | 27 | 33 |
| driver calls per full run | ~40,000 | 52,980 |

The growth is PRD-013 (merged after the brief, +401 tests, 11 new test files). The brief's definition of a driver call is not recorded. This report's definition is in the appendix, and STORY-007 must rerun the same instrument for a like-for-like comparison.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `.agents/reports/PRD-014-test-suite-db-isolation/STORY-001-storage-characterization.report.md` | CREATE | this file |
| `.agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-001-storage-characterization.plan.md` | MOVE | archived |
| `.agents/stories/…/STORY-001-storage-characterization.md`, `.agents/PRDs/…/index.md`, `PRD.md` | UPDATE | status, report, commit (chore commit) |

No file under `tests/`, `app/`, `chat_ui/` or `scripts/` changed. The scratch instrument lives in `%TEMP%\prd014-story001\`, outside the repo.

## Deviations from Plan

1. **Base and gate.** By the time Task 0 ran, PRD-013 had been merged (`728dd60`), so the gate passed without asking. The first branch attempt was cut from the old local tip `c3f0ed5`: `git checkout main` was refused over the uncommitted `pre-prds/README.md`, and a pipe masked the failure. The branch was deleted before anything was committed, then recreated from `main` @ `728dd60` with the edit stashed and restored.
2. **Bucket rule: innermost, not outermost.** `_libsql_endpoint` is set up *inside* `_never_the_configured_database`'s setup, so with the plan's "outermost wins" rule the probe would have been charged to `reset`. The plugin takes the innermost policy fixture on the stack.
3. **`-p no:cacheprovider` on every run**, to keep `.pytest_cache` out of the tree. Checked first: no test uses the `cache` fixture or `config.cache`.
4. **Cursor reads not recorded.** Only `connection.cursor()` results are wrapped, not `connection.execute()` results, so `fetch*` calls are not counted at all. They are not round trips, so the round-trip figure is unaffected. The analysis's "local" column is therefore empty.
5. **Task 6 strengthened with an executed check** (dead inherited `DATABASE_URL`) on top of reading the code. The first attempt was invalidated by the `os.environ` leak described above and redone without that module.
6. **Wall time** taken from `date` differences in the shell plus pytest's own line, not `/usr/bin/time`.
7. **No tests written.** AC 6 forbids changes under `tests/`. The `/implement` "write tests" step does not apply to a measurement-only story.

## For later stories

- **STORY-002, `_DB_NODEIDS` seed:**
  - `tests/test_admin_auth.py` as a module path (PRD-006, matches PRD 6.2's example)
  - `tests/test_db.py::test_init_db_fails_fast_against_an_unreachable_endpoint` as a nodeid (PRD-006; the module's other 77 no-fixture tests make no driver call)
  - `tests/test_main.py::test_lifespan_fails_when_the_database_is_unreachable` (editable: list entry or `@pytest.mark.db`)
  - the three `tests/test_measure_usage_latency.py` `bench.main` tests (editable: a storage fixture is the cleaner fix, otherwise a list entry)
  - Expected `pytest --collect-only -m db -q`: 1,262 + 2 (or 9 with the module path) + 1 + 1 + 3, **plus whatever STORY-003 decides for `test_chat_shell.py`**.
- **STORY-003:** the guard will catch exactly the 7 in-process tests above if STORY-002 has not declared them. `test_db.py` and `test_main.py` call `libsql.connect` against a dead port on purpose, so the `libsql.connect` patch point, not `_shared_client`, is what catches them. Compare full runs against **3,854 collected / 3,827 passing / 27 skipped**.
- **STORY-004: `test_chat_shell.py` will break `pytest -m "not db"` with Docker stopped.** Its 21 `probe` tests are not `db` by any fixture, and their child runs `init_db()` against `_ENDPOINT`. Options: declare them (`_DB_NODEIDS` entry for the module or the tests), or set `DB_BOOTSTRAP_ENABLED=false` in the probe's env, as `test_reports_pages.py:300` already does. The second is a test edit, allowed because the file is not a PRD-006 suite, and makes them honestly storage-free. Decide in STORY-003 or STORY-004. Also note for STORY-004's `pytester` tests: importing `scripts.spike_pii_placeholders` rewrites `os.environ["DATABASE_URL"]` for the session.
- **STORY-005:** in Run B a stall (15.05 s, `STREAM_EXPIRED`) occurred in a test that passed. The recorder only reports on failure (PRD 6.6), so stalls like this stay invisible unless STORY-006's spike counts calls ≥ 10 s, as the PRD already says.
- **STORY-007:** rerun the appendix instrument with the same command. The non-`db` share should fall from 5,936 calls to 0 (the guard asserts it). The total should drop by about the 5,838 resets.

## Observations (recorded, not fixed)

1. **A stall inside a passing test.** `test_chat_state.py::test_every_bubble_kind_is_persisted[context_limit]` had a `conn.execute` take 15.046 s and end in `STREAM_EXPIRED`, yet it passed. Some path swallowed the `StorageError` or recovered on the next call. It was not traced, because the story changes no code. It shows that green runs are also exposed, not only red ones.
2. **`scripts/spike_pii_placeholders.py` and `scripts/measure_history_latency.py` write `os.environ["DATABASE_URL"]` at import.** `test_measure_usage_latency.py` restores the value after importing its script. `test_spike_pii_placeholders.py` does not. Today the leaked value equals `_ENDPOINT`, so nothing breaks, but any test that sets `DATABASE_URL` in the environment expecting children to inherit it is silently overridden once that module has been collected.
3. Run B (302 s) was faster than Run A (340 s). Run A had two `STREAM_EXPIRED` stalls at about 15 s each. The instrument's overhead is not measurable at this resolution, consistent with the brief's measurement.

## Appendix: scratch instrument

Not committed as code. Kept here so STORY-007 can rebuild it byte for byte (plan D-3). Save as `storage_census.py` and `analyze.py` in a directory outside the repo, then:

```bash
PYTHONPATH="<dir>;." python -m pytest tests/ -q -rfEs -p no:cacheprovider -p storage_census --junitxml=<dir>/run.xml
python -I -X utf8 <dir>/analyze.py <dir>/census.json
```

<details>
<summary><code>storage_census.py</code></summary>

```python
"""PRD-014 STORY-001 scratch instrument. Not committed; loaded with `-p storage_census`.

Counts every libsql driver call and charges it to the test that is *running*
(not the one that built the client: `_shared_client()` caches one across tests).
Each call is bucketed by the fixture being set up when it happened:

    reset     inside `_never_the_configured_database` (the autouse reset)
    endpoint  inside `_libsql_endpoint` (the session reachability probe)
    test      anything else during the test's setup/call/teardown

The innermost of the two policy fixtures on the stack wins, so the endpoint
probe, which is set up *inside* the reset fixture's setup, is "endpoint".

Writes census.json next to this file at session end.
"""

import json
import os
import re
import threading
import time
from collections import defaultdict

import libsql
import pytest

STORAGE = frozenset({"temp_db", "database_url", "uninitialized_db", "database_url_factory", "db_connect"})
POLICY = {"_never_the_configured_database": "reset", "_libsql_endpoint": "endpoint"}
FLAKE = re.compile(r"stream_expired|stream has expired|invalid baton|tcp connect error|os error 10060", re.I)
# Cursor reads are served from the already-fetched result: not round trips.
LOCAL = frozenset({"cursor.fetchone", "cursor.fetchall", "cursor.fetchmany", "cursor.close"})
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.environ.get("CENSUS_OUT", "census.json"))

_lock = threading.Lock()
CURRENT = None  # nodeid of the running test; module global so worker threads see it
PHASE = None
STACK: list = []  # fixture argnames being set up, innermost last
CALLS = defaultdict(lambda: [0, 0.0, 0.0, 0, 0])  # key -> [count, total_s, max_s, errors, flake_errors]
ITEMS: dict = {}
OUTCOMES: dict = defaultdict(dict)
FLAKE_SAMPLES: list = []


def _bucket() -> str:
    for name in reversed(STACK):
        if name in POLICY:
            return POLICY[name]
    return "test"


def _record(method: str, seconds: float, exc: BaseException | None) -> None:
    key = (CURRENT or "<no test>", PHASE or "-", _bucket(), method)
    flaky = exc is not None and bool(FLAKE.search(f"{exc} {exc.__context__ or ''}"))
    with _lock:
        row = CALLS[key]
        row[0] += 1
        row[1] += seconds
        row[2] = max(row[2], seconds)
        if exc is not None:
            row[3] += 1
            row[4] += flaky
            if flaky and len(FLAKE_SAMPLES) < 50:
                FLAKE_SAMPLES.append([key[0], key[1], key[2], method, round(seconds, 3), str(exc)[:300]])


class _Counted:
    """Forwards every attribute; times callables and re-raises the original exception."""

    __slots__ = ("_real", "_kind")

    def __init__(self, real, kind: str) -> None:
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "_kind", kind)

    def __getattr__(self, name):
        attr = getattr(self._real, name)
        if not callable(attr):
            return attr
        method = f"{self._kind}.{name}"

        def timed(*args, **kwargs):
            started = time.monotonic()
            exc = None
            try:
                result = attr(*args, **kwargs)
            except BaseException as error:
                exc = error
                raise
            finally:
                _record(method, time.monotonic() - started, exc)
            return _Counted(result, "cursor") if name == "cursor" else result

        return timed

    def __setattr__(self, name, value):
        setattr(self._real, name, value)


_real_connect = libsql.connect


def counting_connect(*args, **kwargs):
    started = time.monotonic()
    exc = None
    try:
        client = _real_connect(*args, **kwargs)
    except BaseException as error:
        exc = error
        raise
    finally:
        _record("connect", time.monotonic() - started, exc)
    return _Counted(client, "conn")


def pytest_configure(config):
    libsql.connect = counting_connect


def pytest_unconfigure(config):
    libsql.connect = _real_connect


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    for item in items:
        ITEMS[item.nodeid] = {
            "module": item.nodeid.split("::", 1)[0],
            "storage": sorted(set(item.fixturenames) & STORAGE),
        }


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    global CURRENT
    CURRENT = item.nodeid
    try:
        yield
    finally:
        CURRENT = None


def _phase(name):
    @pytest.hookimpl(hookwrapper=True)
    def hook(item):
        global PHASE
        PHASE = name
        try:
            yield
        finally:
            PHASE = None

    return hook


pytest_runtest_setup = _phase("setup")
pytest_runtest_call = _phase("call")
pytest_runtest_teardown = _phase("teardown")


@pytest.hookimpl(hookwrapper=True)
def pytest_fixture_setup(fixturedef, request):
    STACK.append(fixturedef.argname)
    try:
        yield
    finally:
        STACK.pop()


def pytest_runtest_logreport(report):
    OUTCOMES[report.nodeid][report.when] = report.outcome


def pytest_sessionfinish(session, exitstatus):
    calls = [[*key, *value] for key, value in CALLS.items()]
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "fields": ["nodeid", "phase", "bucket", "method", "count", "total_s", "max_s", "errors", "flake_errors"],
                "local_methods": sorted(LOCAL),
                "items": ITEMS,
                "outcomes": OUTCOMES,
                "calls": calls,
                "flake_samples": FLAKE_SAMPLES,
            },
            fh,
        )


def pytest_terminal_summary(terminalreporter):
    total = sum(v[0] for k, v in CALLS.items())
    trips = sum(v[0] for k, v in CALLS.items() if k[3] not in LOCAL)
    terminalreporter.write_line(f"storage_census: {total} driver calls ({trips} round trips) -> {OUT}")
```

</details>

<details>
<summary><code>analyze.py</code></summary>

```python
"""PRD-014 STORY-001 scratch analysis. Reads census.json, prints Markdown tables.

usage: python analyze.py census.json
"""

import json
import sys
from collections import Counter, defaultdict

PRD006 = {
    "tests/test_admin_auth.py",
    "tests/test_audit_router.py",
    "tests/test_stats_router.py",
    "tests/test_db.py",
    "tests/test_route_reservations.py",
    "tests/test_chat_state.py",
}

data = json.load(open(sys.argv[1], encoding="utf-8"))
local = set(data["local_methods"])
items = data["items"]
outcomes = data["outcomes"]

by_bucket, by_method, by_phase = Counter(), Counter(), Counter()
trips_bucket = Counter()
own = defaultdict(Counter)  # nodeid -> method -> count, bucket "test" only
own_phase = defaultdict(Counter)
slowest = []
for nodeid, phase, bucket, method, count, total_s, max_s, errors, flaky in data["calls"]:
    by_bucket[bucket] += count
    by_method[method] += count
    by_phase[phase] += count
    if method not in local:
        trips_bucket[bucket] += count
    if bucket == "test":
        own[nodeid][method] += count
        own_phase[nodeid][phase] += count
    slowest.append((max_s, nodeid, phase, bucket, method))

total = sum(by_bucket.values())
trips = sum(trips_bucket.values())
print("## Driver calls per run\n")
print(f"- all driver calls: **{total:,}**; round trips (excluding {', '.join(sorted(local))}): **{trips:,}**\n")
print("| Bucket | Calls | Round trips |\n|---|---:|---:|")
for bucket in sorted(by_bucket, key=lambda b: -by_bucket[b]):
    print(f"| {bucket} | {by_bucket[bucket]:,} | {trips_bucket[bucket]:,} |")
print("\n| Method | Calls |\n|---|---:|")
for method, count in by_method.most_common():
    print(f"| `{method}` | {count:,} |")
print("\n| Phase | Calls |\n|---|---:|")
for phase, count in by_phase.most_common():
    print(f"| {phase} | {count:,} |")
print("\nSlowest single calls (max per test/bucket/method):\n")
print("| Seconds | Test | Phase | Bucket | Method |\n|---:|---|---|---|---|")
for max_s, nodeid, phase, bucket, method in sorted(slowest, reverse=True)[:10]:
    print(f"| {max_s:.3f} | `{nodeid}` | {phase} | {bucket} | `{method}` |")
if data["flake_samples"]:
    print("\nDriver errors matching the flake signature:\n")
    print("| Test | Phase | Bucket | Method | Seconds | Error |\n|---|---|---|---|---:|---|")
    for nodeid, phase, bucket, method, seconds, err in data["flake_samples"]:
        print(f"| `{nodeid}` | {phase} | {bucket} | `{method}` | {seconds} | {err[:140]} |")

# --- census ---
modules = defaultdict(lambda: [0, 0])  # module -> [storage, none]
for nodeid, info in items.items():
    modules[info["module"]][0 if info["storage"] else 1] += 1
storage_tests = sum(v[0] for v in modules.values())
none_tests = sum(v[1] for v in modules.values())
with_storage = [m for m, v in modules.items() if v[0]]
mixed = sorted(m for m, v in modules.items() if v[0] and v[1])
fixture_use = Counter(f for info in items.values() for f in info["storage"])
print("\n## Storage-fixture census\n")
print(f"| Measure | Value |\n|---|---:|")
print(f"| tests collected | {len(items):,} |")
print(f"| tests requesting a storage fixture | {storage_tests:,} |")
print(f"| tests requesting none | {none_tests:,} |")
print(f"| modules | {len(modules)} |")
print(f"| modules with ≥ 1 storage test | {len(with_storage)} |")
print(f"| modules with no storage test | {len(modules) - len(with_storage)} |")
print(f"| mixed modules | {len(mixed)} |")
print("\n| Fixture (transitive) | Tests |\n|---|---:|")
for fixture, count in fixture_use.most_common():
    print(f"| `{fixture}` | {count:,} |")
print("\nPer module (storage / none):\n")
print("| Module | Storage | None | Mixed |\n|---|---:|---:|---|")
for module in sorted(modules):
    s, n = modules[module]
    print(f"| `{module}` | {s} | {n} | {'yes' if s and n else ''} |")

# --- undeclared ---
undeclared = defaultdict(list)
for nodeid, info in items.items():
    if not info["storage"] and own.get(nodeid):
        undeclared[info["module"]].append(nodeid)
n_undeclared = sum(len(v) for v in undeclared.values())
print("\n## Undeclared storage (driver calls, no storage fixture)\n")
print(f"**{n_undeclared}** tests in **{len(undeclared)}** modules.\n")
print("| Module | Undeclared / non-storage tests in module | PRD-006 |\n|---|---:|---|")
for module in sorted(undeclared):
    print(f"| `{module}` | {len(undeclared[module])} / {modules[module][1]} | {'**yes**' if module in PRD006 else ''} |")
print()
for module in sorted(undeclared):
    print(f"### `{module}`{' (PRD-006)' if module in PRD006 else ''}\n")
    print("| Test | Own calls | Methods | Phases | Outcome |\n|---|---:|---|---|---|")
    for nodeid in sorted(undeclared[module]):
        methods = own[nodeid]
        phases = ", ".join(f"{p} {c}" for p, c in own_phase[nodeid].most_common())
        outcome = "/".join(f"{w}:{o}" for w, o in outcomes.get(nodeid, {}).items() if o != "passed") or "passed"
        listed = ", ".join(f"{m.split('.')[-1]}×{c}" for m, c in methods.most_common())
        print(f"| `{nodeid.split('::', 1)[1]}` | {sum(methods.values())} | {listed} | {phases} | {outcome} |")
    print()

# --- reverse ---
idle = [n for n, info in items.items() if info["storage"] and not own.get(n)]
print("## Storage-fixture tests with no own driver call (informational)\n")
print(f"{len(idle)} tests.\n")
idle_modules = Counter(items[n]["module"] for n in idle)
print("| Module | Tests |\n|---|---:|")
for module, count in sorted(idle_modules.items()):
    print(f"| `{module}` | {count} |")

# --- outside any test ---
outside = by_bucket and sum(c for n, p, b, m, c, *_ in data["calls"] if n == "<no test>")
print(f"\nCalls outside any test (collection / session): {outside}")
```

</details>

## Acceptance Criteria

- [x] Given untouched `main`, when the full suite runs once, then the report records the collected total, passed, failed, errored and skipped counts, plus the wall time. Any failure is listed with its nodeid and error. That run is the baseline every later story compares against. (*Baseline run*)
- [x] Given an uncommitted scratch plugin loaded with `-p` that wraps `libsql.connect` and counts calls per test, when the full suite runs under it, then the report records the total driver calls per run and the storage-fixture census: tests and modules requesting any of the five fixtures (transitively, via `item.fixturenames`), tests requesting none, and modules mixing both. (*Driver calls and census*)
- [x] Given the same run, when tests with at least one driver call are cross-referenced with the census, then the report lists every test that issues driver calls without a storage fixture, grouped by module, each flagged if its file is one of the six PRD-006 suites. Reset calls are excluded. (*Undeclared storage*)
- [x] Given every autouse fixture in `tests/conftest.py` and in test modules, when each is read, then the report has a table saying whether it touches storage. (*Autouse audit*: only `_never_the_configured_database` and `_libsql_endpoint` in-process, as expected)
- [x] Given every test that spawns a subprocess and requests no storage fixture, when its child's environment and code path are read, then the report states whether the child reaches storage, and any that do are added to the undeclared list. (*Subprocess audit*: `test_chat_shell.py`, 21 tests)
- [x] Given the story's diff, when reviewed, then it contains only the report (and `.agents/` bookkeeping). No file under `tests/`, `app/` or `chat_ui/` changes, and the scratch plugin is not committed. (`git diff --stat` empty for those paths; plugin source quoted in the appendix only)
- [x] All tasks completed
- [x] Follows existing patterns (PRD-013 STORY-001 report layout, commit sequence)
