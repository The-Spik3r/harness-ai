---
id: STORY-002
prd: PRD-014
slug: db-marker
title: "db marker: registered, applied from the storage fixtures and _DB_NODEIDS, independent of --run-benchmark"
type: technical
priority: high
complexity: small
phase: "1 - Measure and mark"
status: todo
labels: [tests, conftest, pytest]
epic_branch: epic/PRD-014-test-suite-db-isolation
plan: null
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-003, STORY-005]
skills: []
created: 2026-10-20
updated: 2026-10-20
---

# STORY-002: `db` marker

## Description

As a harness developer, I want every test that needs storage to carry a `db` marker without any test file being edited, so that `-m db` / `-m "not db"` select the right tests and later stories can key the reset and the guard on it.

## Acceptance Criteria

- [ ] Given `tests/conftest.py`, when `pytest --markers` runs, then `db` is listed with a one-line description beside `benchmark`.
- [ ] Given a test that requests any of `temp_db`, `database_url`, `uninitialized_db`, `database_url_factory` or `db_connect`, directly or through another fixture (its `item.fixturenames` closure), when the suite is collected, then the test carries the `db` marker.
- [ ] Given a test whose nodeid, or module path, is in `_DB_NODEIDS`, when collected, then it carries `db`. `_DB_NODEIDS` is seeded with STORY-001's undeclared-storage list.
- [ ] Given `--run-benchmark` passed or not, when the suite is collected, then the set of `db`-marked nodeids is identical (the hook no longer `return`s before marking), and benchmark skipping behaves as before.
- [ ] Given the change, when the full suite runs, then total and passing counts match STORY-001's baseline (the reset is still autouse for every test, so behaviour is unchanged). `pytest --collect-only -q -m db` reports the census count plus the list count from STORY-001, and `git diff main` over the six PRD-006 suites is empty.

## Technical Notes

- Constants per PRD Section 6.2: `_STORAGE_FIXTURES` (frozenset) and `_DB_NODEIDS` (tuple of strings, each a module path or a full nodeid). Match a module path by `item.nodeid.split("::", 1)[0] == entry`, and a nodeid by equality or as a prefix (to cover parametrized ids). Document the rule in the constant's comment.
- Restructure `pytest_collection_modifyitems` ([tests/conftest.py:85-100](../../../tests/conftest.py)): mark `db` first, then apply the benchmark skip only `if not config.getoption("--run-benchmark")`. Keep the existing docstring's benchmark paragraph and add one for `db`.
- New file `tests/test_db_isolation_harness.py` holds this PRD's harness self-tests. In this story: a module-local fixture depending on `temp_db` marks its test (assert via `request.node.get_closest_marker("db")`), a non-storage test is unmarked, and a `pytester` case shows `_DB_NODEIDS` matching (or a direct unit test of the matching helper, which is cheaper).
- A test can also add `@pytest.mark.db` itself. pytest supports that natively, and nothing here needs to change for it.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-003, STORY-005

## PRD Reference

Source: [`PRD-014-test-suite-db-isolation/PRD.md`](../../PRDs/PRD-014-test-suite-db-isolation/PRD.md) — sections 6.2, 7 (F2), 11 (Functional requirements), Appendix D1
