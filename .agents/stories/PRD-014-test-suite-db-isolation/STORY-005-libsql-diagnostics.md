---
id: STORY-005
prd: PRD-014
slug: libsql-diagnostics
title: "Driver recorder and a libsql diagnostics section with a verdict on every failing db test"
type: feature
priority: high
complexity: medium
phase: "3 - Diagnose and investigate"
status: todo
labels: [tests, conftest, diagnostics, libsql]
epic_branch: epic/PRD-014-test-suite-db-isolation
plan: null
report: null
commit: null
depends_on: [STORY-002, STORY-003]
blocks: [STORY-006, STORY-007]
skills: []
created: 2026-10-20
updated: 2026-10-20
---

# STORY-005: `libsql diagnostics` on failing `db` tests

## Description

As a harness developer, I want every failing `db` test to report whether an infrastructure stall was involved, so that I can tell a regression from a libSQL hiccup without rerunning the test.

## Acceptance Criteria

- [ ] Given a `db` test, when it runs, then every client `libsql.connect` returns is a `_RecordedClient` that forwards every attribute, times every method call (including `connect` itself) and re-raises the driver's **original** exception object. Calls are recorded into the *currently running* test's sink, including on a client built by an earlier test and cached by `_shared_client()`.
- [ ] Given a `db` test that fails in `setup`, `call` or `teardown`, when its report is produced, then it has a `libsql diagnostics` section listing call and client counts, the slowest call (with the client's idle time before it), every call ≥ 10 s, every driver error matching `database._DEAD_STREAM`, `tcp connect error` or `os error 10060`, and a last line starting `libsql verdict: `. A passing test's report has no such section.
- [ ] Given `_verdict(records)`, when unit-tested, then it returns the four outcomes in PRD Section 6.6's table: dead stream or connect error → `likely infrastructure — <op> took <s> s and ended in <error>`; a ≥ 10 s call with no error → `likely infrastructure — <op> took <s> s (no driver error)`; otherwise `no infrastructure signal (<n> calls, slowest <s> s)`; nothing recorded → `no driver calls recorded`.
- [ ] Given driver error text, when it is written into the section, then it has passed through `database._redacted()`, and the section contains no SQL text or parameters.
- [ ] Given `tests/test_db.py` and `tests/test_conftest_fixtures.py`, when run with and without the recorder, then both pass with the same counts and within 10% of the same wall time (recorded in the report). Tests that patch `libsql.connect` themselves (`tests/test_db.py:4084` onward) and the seven `monkeypatch.undo()` sites still pass, and the full suite's counts equal STORY-001's baseline.

## Technical Notes

- Design in PRD Section 6.6. The recorder is installed in `_storage_policy`'s `db` branch via `monkeypatch.setattr(libsql, "connect", recorded_connect)`, so pytest restores it. The current-item pointer is set in that fixture and cleared at its teardown, after the test's own fixtures have torn down. Make sure teardown errors still record into the item.
- Idle time: keep `last_used` per `_RecordedClient`. That is what showed the brief's failures were *not* idle streams (0–0.45 s).
- Report hook: `@pytest.hookimpl(hookwrapper=True) def pytest_runtest_makereport(item, call)`. `outcome = yield; report = outcome.get_result()`. If `report.failed` and the item has `db`, call `report.sections.append(("libsql diagnostics", text))`. Records for the item live in `item.stash[_RECORDS_KEY]`.
- A setup failure inside `_libsql_endpoint`'s session probe happens before the recorder exists. That path already exits with its own message, so don't record it.
- After `monkeypatch.undo()` the wrapper is gone for the rest of the test. Document the "may be partial" behaviour in the hook's docstring (PRD Section 6.6).
- Self-tests in `tests/test_db_isolation_harness.py`: pure `_verdict` table cases; a fake real-client whose `execute` raises a `ValueError` with `STREAM_EXPIRED`, asserting the same object is re-raised and recorded; a `pytester` subprocess run of a deliberately failing `db` test asserting the section and verdict appear in `stdout`.
- Do not trigger real stalls in tests. Fabricate records with given durations instead.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-002, STORY-003
- **Blocks**: STORY-006, STORY-007

## PRD Reference

Source: [`PRD-014-test-suite-db-isolation/PRD.md`](../../PRDs/PRD-014-test-suite-db-isolation/PRD.md) — sections 6.6, 7 (F5), 9.2, 10, 11, 14 (R4), Appendix D3
