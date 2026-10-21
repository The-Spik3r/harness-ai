---
target_prd: PRD-014
slug: test-suite-db-isolation
title: Test suite — isolate the tests that need the database, and make their failures diagnosable
status: promoted
prd: .agents/PRDs/PRD-014-test-suite-db-isolation/PRD.md
depends_on: []
blocks: []
estimated_stories: 6-8
created: 2026-10-17
---

# Test suite — isolate the tests that need the database

## Problem

**The full suite is never green in one run on this machine, and the failures are not bugs.** Every full run fails one or two tests, a different one each time, and every one of them passes when rerun alone. PRD-013's STORY-001, STORY-002 and STORY-004 reports all record it, and so do earlier PRDs ("restart the libSQL dev container, not bisect code"). A red run therefore carries no signal: a real regression and an infrastructure hiccup look the same, and the only way to tell them apart is to rerun each failure by hand.

**The cause is outside the code: individual TCP connections to the local libSQL server stall for 7–21 s.** The server is `harness-libsql-dev`, a container in Docker Desktop on Windows (WSL2 backend), reached at `http://127.0.0.1:8080`. When a statement is caught in a stall longer than about 10 s, the server expires its Hrana stream, and the request that finally arrives is answered with `STREAM_EXPIRED`. When the stall hits the TCP handshake itself, the driver gives up after 21 s with `tcp connect error ... (os error 10060)`, which is Windows' SYN retransmission limit. See *Evidence* for the measurements.

**The existing defence cannot help, by construction.** `_shared_client()` probes a client that has been idle for `_IDLE_PROBE_AFTER_SECONDS = 5.0` ([database.py:51-124](../app/db/database.py)). That catches a stream that died *while nobody was using it*. Here the client is in active use: every failure landed on a client last used between 0 and 0.45 s earlier. The stream dies *during* the statement, which `_translated()` correctly turns into `StorageError` without retrying, because a retry there could replay half a transaction ([database.py:585-620](../app/db/database.py)). Lowering the probe threshold, or probing on every call, would not prevent a single one of the observed failures.

**Two thirds of the suite is exposed to this for no reason.** The autouse fixture `_never_the_configured_database` ([tests/conftest.py:192-220](../tests/conftest.py)) resets the database before *every* test, whether it uses storage or not. 2,363 of 3,453 tests request no database fixture at all, yet each one opens a round trip to Docker before it runs. Several of the observed stalls landed on exactly such tests: `test_spike_pii_placeholders.py`, `test_pii_corpus_files.py`, `test_messages.py` and `test_chat_ui_startup_guard.py`. Each full run issues about 40,000 driver calls.

The autouse reset exists for a good reason, and any fix has to keep it. Before PRD-007 STORY-005, six tests in `test_main.py` and `test_admin_auth.py` reached storage without declaring it and quietly read the repo-root database. The fixture makes "no test can reach another test's rows, or anyone's real database" hold for every test, including the ones that forget to ask.

## Goal

A failing test means a defect. The tests that do not need storage never touch the network, so a failure there is always real. The tests that do need it report, when they fail, whether an infrastructure stall was involved. The isolation guarantee the autouse fixture provides today stays at least as strong.

## Proposed scope

**In**
- A `db` marker, applied automatically in `conftest.py` to every test that requests `temp_db`, `database_url`, `uninitialized_db` or `database_url_factory`, plus an explicit list for tests that need storage without one of those fixtures. Test files are not edited to add it.
- The database reset runs only for `db` tests.
- **Undeclared storage access fails loudly.** In a test without the marker, the first use of the shared client raises an error that names the test and says it touches storage without declaring `db`. This replaces "silently reset and allow" with "refuse and explain", which is stricter than today.
- Every test the new rule catches is marked, through the explicit list in `conftest.py` for files that are pinned byte-for-byte (`test_admin_auth.py` and the other PRD-006 suites) and with the marker or a fixture elsewhere.
- **Diagnostics on a failing `db` test.** A light version of the instrumentation used for this brief: wrap the clients `libsql.connect` returns, record the duration of every driver call and every driver error, and on failure append a section to the report: slowest call, any call over 10 s, any `STREAM_EXPIRED` or `tcp connect error`, and a one-line verdict ("likely infrastructure: a 15.0 s call ended in STREAM_EXPIRED" or "no infrastructure signal").
- A spike that confirms the Docker-networking hypothesis (D5), with its result recorded in this brief or the PRD.
- README: how to run `pytest -m "not db"` (no Docker needed) and `pytest -m db`, and how to read the diagnostics section.

**Out**
- Any change to `app/`. The production recovery design (probe before lending, invalidate without retrying mid-transaction) is correct for the failure seen here and stays as it is.
- Retrying failed tests automatically (D4).
- Running the suite in parallel. `pytest-xdist` against one libSQL database means several independent clients contending for its single writer, which STORY-006 measured losing 169 of 200 writes to `TRANSACTION_TIMEOUT`.
- Replacing Docker Desktop on developer machines.

## Open decisions

| # | Question | Proposed default |
|---|---|---|
| D1 | How tests get the `db` marker | Automatically from the four storage fixtures in `pytest_collection_modifyitems`; an explicit nodeid/module list in `conftest.py` for the rest. No per-file edits, so pinned suites stay byte-identical. |
| D2 | What an undeclared storage access does | Raise immediately from `_shared_client()` (patched for non-`db` tests) with an instructive message. Not "point at an unreachable URL": that would cost a 2 s connect timeout per test and read as a network error. |
| D3 | Where diagnostics live | In `conftest.py` as a fixture or hook active only for `db` tests, appended to the failure report through `item.user_properties` or a report section. No new dependency. |
| D4 | Retry flaky `db` failures automatically | No, for now. With D3 the cause is visible on the report. Revisit with `pytest-rerunfailures --only-rerun "STREAM_EXPIRED\|os error 10060"` if, after D5, the stalls turn out to be unavoidable on Docker Desktop. |
| D5 | Is Docker Desktop's Windows port forwarding the source of the stalls | Spike: run the `db` tests from a Linux container on the same Docker network as `harness-libsql-dev`, addressing it by container name, three full runs. Zero stalls means confirmed. |
| D6 | One command or two by default | `pytest` keeps running everything. `-m "not db"` and `-m db` are documented, not required. |

## Evidence

Measured on 2026-10-14 during PRD-013 STORY-004, over five full-suite runs with an instrumentation plugin (a proxy around every real client from `libsql.connect`, logging per-call idle time, duration, origin and every driver error) and an independent probe (a fresh stateless `POST /v2/pipeline` with `SELECT 1` every 250 ms).

**Results per run**

| Run | Result | Infrastructure events |
|---|---|---|
| Baseline (no instrumentation) | 2 failed, 3412 passed | `STREAM_EXPIRED` in `test_chat_sessions.py` and `test_main.py` |
| 1 | 3426 passed | 1 `STREAM_EXPIRED`, absorbed by the fixture's retry |
| 2 | 1 failed | 3 `STREAM_EXPIRED`; `test_migrate_to_turso_cli.py` failed (the CLI exits 1) |
| 3 | 1 error | 3 `STREAM_EXPIRED`; `test_query_pipeline_multiturn.py` setup error, `tcp connect error ... 10060` after 21 s |
| 4 | 3426 passed | 2 `STREAM_EXPIRED`, both absorbed by the fixture's retry |
| 5 | 1 error | `test_router.py` setup error, `tcp connect error ... 10060` after 21.05 s |

**What rules out an idle stream**
- Every `STREAM_EXPIRED` landed on a client last used 0.0–0.45 s before the failing call.
- The longest gap between two calls on any client, across all runs, was 3.5 s. The local server expires an idle stream at 10–12 s (measured in PRD-008 STORY-024).

**What points at stalled connections**
- Every `STREAM_EXPIRED` whose duration was recorded came from a call that took 15.0 s (15.047 s, 15.032 s, and about 15 s in run 2). Calls on the same client before it returned in milliseconds.
- The probe saw one slow request in 2,205: 7.03 s, from s 192.8 to 199.8. The suite's first stalled call in run 4 ran from s 191.4 to 206.4. Two independent processes stalled at the same moment.
- The other stalls did not reach the probe, so this is not a global server freeze. Specific connections hang.
- The container logs show nothing but `Stream handle for ... is expired`. No restart, 0% CPU, 23 MB of memory.

**Hypotheses ruled out**
- **Idle stream:** see above.
- **Ephemeral port exhaustion on Windows:** sockets in `TIME_WAIT` fell from 1,373 to 380 while `test_db.py` ran. The driver keeps 6–25 connections to port 8080 open and reuses them. The dynamic port range is the default 16,384.
- **Server overload:** nothing in the logs or the resource figures.

**Not yet established**
- Why the stalled calls take exactly 15 s. It looks like a timeout or retry inside the driver's HTTP stack (`libsql` 0.1.11) but was not traced.
- Whether the stall is in Docker Desktop's port forwarding or inside the server's network stack. D5 decides it.

**Suite shape**

| | Tests |
|---|---|
| Total | 3,453 |
| Request a storage fixture | 1,090 (32%), in 47 of 91 modules |
| Request none, reset anyway by the autouse fixture | 2,363 (68%) |
| Modules mixing both kinds | 27 |

Environment: Docker Desktop 29.8.2 (WSL2, kernel 6.18.54.1), `ghcr.io/tursodatabase/libsql-server` sqld 0.24.33, `libsql` 0.1.11, Python 3.11.

## Success criteria

- `pytest -m "not db"` passes with Docker Desktop stopped.
- Every test without the `db` marker issues zero driver calls (asserted by the D2 guard, not assumed).
- A test that reaches storage without declaring it fails with a message that names it and says what to add.
- Every `db` test failure carries a diagnostics section with a verdict line.
- The suite's total count and pass count are unchanged, and no assertion in any pinned suite changes.
- Driver calls per full run drop from about 40,000 to the `db` tests' own share.

## Risks

| Risk | Mitigation |
|---|---|
| A test depends on storage without saying so and now fails | That is the intended outcome of D2: the failure names it, and it is marked. Done in one story with the full suite run before and after. |
| Pinned suites cannot be edited to add the marker | D1's explicit list lives in `conftest.py`. |
| Autouse fixtures that run before the guard touch storage | Audit every autouse fixture in the story that adds the guard. The PII and pattern policy fixtures in `conftest.py` do not touch storage. |
| The diagnostics wrapper changes driver behaviour | It forwards every attribute and only times calls. The instrumentation used for this brief left `test_db.py` and `test_conftest_fixtures.py` at 234 passed with and without it, at the same speed. Tests that patch `libsql.connect` themselves keep working, because `monkeypatch` restores the wrapper. |
| `db` tests still flake | Expected until D5 is acted on. The diagnostics make each one cheap to classify. |

## Tentative story breakdown

1. Characterize: count driver calls per test, and list every test that touches storage without a storage fixture.
2. `db` marker: automatic from the storage fixtures, plus the explicit list.
3. Reset only for `db` tests; guard that fails undeclared storage access in all others.
4. Mark every test the guard catches; pinned suites through the list.
5. Diagnostics on failing `db` tests, with the verdict line.
6. Spike: run the `db` tests from inside the Docker network (D5); record the result.
7. README: the two commands and how to read the diagnostics.
8. (Conditional on D5) Retry policy for infrastructure-classified failures, or the alternative D5 points to.
