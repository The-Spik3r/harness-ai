---
id: STORY-004
prd: PRD-014
slug: docker-free-run
title: "Lazy _libsql_endpoint: pytest -m \"not db\" passes with Docker stopped"
type: technical
priority: high
complexity: small
phase: "2 - Enforce"
status: todo
labels: [tests, conftest, docker]
epic_branch: epic/PRD-014-test-suite-db-isolation
plan: null
report: null
commit: null
depends_on: [STORY-003]
blocks: [STORY-007]
skills: []
created: 2026-10-20
updated: 2026-10-20
---

# STORY-004: Docker-free `not db` run

## Description

As a harness developer, I want `pytest -m "not db"` to run with Docker Desktop stopped, so that I have a fast, reliable loop for the tests that never needed storage.

## Acceptance Criteria

- [ ] Given `_libsql_endpoint`, when `conftest.py` is read, then it is `scope="session"` without `autouse=True`. It is instantiated only by `_storage_policy`'s `db` branch and by the storage fixtures, and it keeps its `pytest.exit(...)` message and `returncode=1`.
- [ ] Given `HARNESS_TEST_LIBSQL_URL` pointing at a port with nothing listening, when a `pytester` subprocess run collects one non-`db` test, then it passes. When it collects one `db` test, then the run exits with the "libSQL dev server ... is unreachable" message.
- [ ] Given Docker Desktop stopped, when `pytest tests/ -m "not db" -q` runs, then it reports 0 failed and 0 errors. The pass count equals STORY-001's non-storage count adjusted by STORY-003's declarations, and the report records the command, output tail and wall time.
- [ ] Given Docker running, when the full suite runs, then total and passing counts equal STORY-001's baseline.

## Technical Notes

- Expected one-line change in `conftest.py` plus the docstring: `@pytest.fixture(scope="session")`. `database_url` and `database_url_factory` already request `_libsql_endpoint`, so nothing else needs to depend on it.
- With Docker stopped, a full run now exits at the *first* `db` test instead of before the first test. Note this in the fixture docstring (PRD Section 6.5).
- Watch for imports that construct a client at module import time. STORY-001's audit should have found none. If `-m "not db"` with Docker stopped hangs or errors during collection, that is the cause.
- The `pytester` self-test lives in `tests/test_db_isolation_harness.py` and uses `runpytest_subprocess` with the real `conftest.py` copied in (`pytester.copy_example` or by reading `tests/conftest.py`), plus the env var.
- Windows: a refused localhost connect takes ~2 s. Use `http://127.0.0.1:9` in the self-test so the `db` arm finishes quickly.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-003
- **Blocks**: STORY-007

## PRD Reference

Source: [`PRD-014-test-suite-db-isolation/PRD.md`](../../PRDs/PRD-014-test-suite-db-isolation/PRD.md) — sections 6.5, 7 (F4), 10, 11 (MVP definition)
