---
id: STORY-003
prd: PRD-014
slug: reset-and-guard
title: "Reset only db tests, refuse storage in every other test, and declare every test the guard catches"
type: technical
priority: high
complexity: medium
phase: "2 - Enforce"
status: todo
labels: [tests, conftest, isolation]
epic_branch: epic/PRD-014-test-suite-db-isolation
plan: null
report: null
commit: null
depends_on: [STORY-001, STORY-002]
blocks: [STORY-004, STORY-005, STORY-007]
skills: []
created: 2026-10-20
updated: 2026-10-20
---

# STORY-003: Reset only `db` tests; guard every other test

## Description

As a story implementer, I want a test that reaches storage without declaring it to fail immediately with a message saying what to add, and every test that doesn't need storage to stay off the network, so that isolation is enforced instead of assumed and two thirds of the suite stops being exposed to libSQL stalls.

## Acceptance Criteria

- [ ] Given a `db` test, when it starts, then `settings.DATABASE_URL` is the test endpoint and the database is empty. `_reset_database()` and its one dead-stream retry are unchanged, and the three reset tests in `tests/test_conftest_fixtures.py` pass.
- [ ] Given a non-`db` test that calls `get_connection()` (or anything that reaches `database._shared_client` or `libsql.connect`), when it runs, then it fails with a message containing its nodeid, the first `app/` frame, the five storage fixture names, `@pytest.mark.db` and `_DB_NODEIDS`. It makes no network call.
- [ ] Given the same access wrapped in `except Exception:` inside the test, or made inside `asyncio.to_thread`, or swallowed by `except BaseException:`, when the test ends, then it still fails, through the raised `pytest.fail.Exception` or through the teardown check of the recorded access.
- [ ] Given a `db` test that left a cached client in `app.db.database._client`, when a non-`db` test runs next and reaches storage, then the guard refuses. The cached client is not lent.
- [ ] Given the full suite before and after this story, when both run, then the total and passing counts equal STORY-001's baseline. Every guard catch is declared in this same commit (in `_DB_NODEIDS` for the six PRD-006 suites, by fixture, `@pytest.mark.db` or `_DB_NODEIDS` elsewhere). No assertion changes in any test, and `git diff main` over the six PRD-006 suites is empty.

## Technical Notes

- Replace `_never_the_configured_database` with `_storage_policy(request, monkeypatch)`, **declared first among the autouse fixtures** in `conftest.py` so it instantiates before `_default_pattern_policy` and `_default_pii_policy` (PRD R2). Keep the old docstring's history (STORY-005's six tests, why the fix lives in conftest) and add the new mechanism to it.
- `db` branch: `request.getfixturevalue("_libsql_endpoint")`, `monkeypatch.setattr(settings, "DATABASE_URL", endpoint)`, `_reset_database()`. In this story `_libsql_endpoint` may still be autouse, since STORY-004 makes it lazy. Using `getfixturevalue` now makes that change a one-line diff.
- Non-`db` branch: `monkeypatch.setattr(settings, "DATABASE_URL", _ENDPOINT)` (no probe), then patch `database._shared_client` and `libsql.connect` with `_refuse(item, sink)` (PRD Section 6.3). Teardown: `if sink: pytest.fail(...)`. Patch `libsql.connect` on the `libsql` module object, which is what `app/db/database.py` imports as `import libsql`.
- `pytest.fail.Exception` derives from `BaseException`, so it gets past `except Exception` in routers and services. Verify that the FastAPI `TestClient` re-raises it from the app rather than returning a `500`. If it doesn't, the teardown check still fails the test. Record which happens.
- `_first_app_frame()`: walk `traceback.extract_stack()` for the innermost frame under `app/` or `chat_ui/`, falling back to the innermost test frame.
- Expect catches through the app lifespan (`TestClient(app)` running `init_db()`) in `test_main.py` and `test_admin_auth.py` (the six tests from PRD-007 STORY-005). Prefer `_DB_NODEIDS` module entries when most of a module needs storage, and nodeids when only a few tests do.
- `tests/test_migrate_to_turso_cli.py:6`'s docstring names `_never_the_configured_database`. Update the name (a comment-only change).
- Harness self-tests in `tests/test_db_isolation_harness.py`: call the refused function inside `pytest.raises(pytest.fail.Exception)` to check the message. Use a `pytester` subprocess run for the swallow, thread and teardown cases.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-001, STORY-002
- **Blocks**: STORY-004, STORY-005, STORY-007

## PRD Reference

Source: [`PRD-014-test-suite-db-isolation/PRD.md`](../../PRDs/PRD-014-test-suite-db-isolation/PRD.md) — sections 6.3, 6.4, 7 (F3), 10 (guard failure message), 11, 14 (R1, R2, R6), Appendix D2
