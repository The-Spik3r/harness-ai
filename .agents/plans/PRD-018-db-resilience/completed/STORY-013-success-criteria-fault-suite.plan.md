---
story: STORY-013
prd: PRD-018
slug: success-criteria-fault-suite
title: Success-criteria suite - statements 1-14 under fault injection, outage end-to-end, opt-in chaos, latency
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-018-db-resilience        # all stories commit here, no per-story branch
created: 2026-11-17
---

# Plan: Prove the MVP definition (PRD-018 Section 11, Section 12 testing approach, D18)

## Summary

Everything this story proves is built (STORY-002..012). It adds **request-level proofs and no application code**: (1) one parametrized `db` test with one case per statement of PRD Section 6.3 (1-14, plus two representatives of the "refusal row" statement 6), each driving the real call path (`/query` through `TestClient`, `run_conversation`, or `ChatState` send) once fault-free and once per class (`DEAD_STREAM`, `NOT_SENT`), asserting the response equals the baseline and the row footprint is identical; (2) three `OUTCOME_UNKNOWN`-after-forward tests (admit, charge, append) plus one control; (3) the in-flight-request-across-an-outage test with journal, clear, drain; (4) an opt-in `chaos` marker and `--run-chaos` option in `tests/conftest.py` with two real-fault tests and a keep-the-server-running fixture that never run by default or in CI; (5) the healthy-path latency comparison `main` vs epic, run by the implementer with `scripts/measure_usage_latency.py`'s method and recorded in the report. Two small, backward-compatible additions to the test harness `tests/db_faults.py` are needed to hit the exact statement for a commit fault and to model recovery (see Design D-1, D-2). If a proof exposes a real defect: fix it in this story only when it is small and clearly inside PRD-018 scope (cite the PRD decision in the commit), otherwise STOP and report to the orchestrator with the failing case id; never weaken an assertion to go green.

## User Story

As a platform operator
I want the PRD's MVP definition pinned by tests at the request level
So that a blip is provably absorbed, an unsafe replay provably never happens and an outage provably loses no row

## Story Reference

- Story file: `.agents/stories/PRD-018-db-resilience/STORY-013-success-criteria-fault-suite.md`
- PRD: `.agents/PRDs/PRD-018-db-resilience/PRD.md` (Section 6.3 table :180-197, Section 6.7 :267-281, Section 6.8 :283-307, Section 11 :462-488, Section 12 testing approach :515-519)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (tests and test infrastructure only) |
| Complexity | MEDIUM |
| Systems Affected | `tests/` only (new `test_db_resilience_mvp.py`, `test_db_resilience_chaos.py`, `test_chaos_marker.py`; edits to `tests/conftest.py`, `tests/db_faults.py`) |
| Story | STORY-013 (depends_on STORY-010, STORY-011: both `status: done`, checked) |
| PRD | PRD-018 |
| Epic Branch | `epic/PRD-018-db-resilience` (commit directly on this branch) |

---

## Skills In Use

`.agents/skills/` holds only `frontend-design` (no frontend here, story `skills: []`). None applies. `chat_ui/AGENTS.md` asks for the Reflex skills before editing Reflex code: this story edits no Reflex code, it only imports `chat_ui.chat_ui.state` in a test, exactly as `tests/test_chat_history_send.py:48-49` does.

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | - | - |

---

## Patterns to Follow

### Naming / structure of a request-level `db` test file

```
# SOURCE: tests/test_db_resilience_release.py:21-27, 602-627  (module docstring cites the PRD story;
# env defaults first; `faulty_db` + `journal` fixtures; drain with journal_drainer.drain_once)
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
...
@pytest.fixture
def journal(tmp_path):
    opened = audit_journal.open_journal(str(tmp_path / "buf"), 1 << 20, 2)
    yield opened
    audit_journal.close_journal()          # the conftest leak guard (conftest.py:730-762) fails a leak
```

### Fault injection, the "landed then lost" mode

```
# SOURCE: tests/test_db_resilience_faults.py:176-186, tests/db_faults.py:183-191
faulty_db.add(Fault(NAMESPACE_SHUTDOWN_503, op="commit", when="after"))
with pytest.raises(StorageError):
    admit_usage("u-landed")
assert _usage_row("u-landed")["requests"] == 1
assert faulty_db.forwarded("INSERT INTO USAGE_DAILY") == 1       # no retry reached the server
assert not [r for r in _retry_records(caplog) if "retry op=" in r.getMessage()]
```

### Driving the real routes and the chat UI

```
# SOURCE: tests/test_query_pipeline_usage_limits.py:527-530, 533-545   (/query, real db, stubbed upstream)
@pytest.fixture
def client(temp_db):
    insert_user(User(user_id=..., role="user", token_hash=hash_token(_AUTH_TOKEN)))
    return TestClient(app, headers={"Authorization": f"Bearer {_AUTH_TOKEN}"})
monkeypatch.setattr("app.routers.query.call_openrouter", stub)

# SOURCE: tests/test_chat_history_send.py:72-82, 174-195   (ChatState send, real pipeline, upstream faked)
state = ChatState(_reflex_internal_init=True); state.user_id = ...; state._token = ...
monkeypatch.setattr(chat_state_mod, "call_openrouter", _fake_call_openrouter)
await type(state).event_handlers["send"].fn(state)     # bypasses the background-task chain guard
```

### Tools path through `run_conversation` and drain back

```
# SOURCE: tests/test_db_resilience_release.py:121-146, 602-627
_run_tools(_READ, _SHELL)  ->  result.audit_id is None; journal.pending() has one entry with write_id == result.audit_ref
journal_drainer.drain_once(journal) is journal_drainer.DrainOutcome.DRAINED
```

### Opt-in marker (the pattern `--run-chaos` copies)

```
# SOURCE: tests/conftest.py:107-111, 160-178, 212-218; tests/test_e2e_marker.py:20-80 (pytester child over a copy of conftest)
parser.addoption("--run-e2e", action="store_true", default=False, help=...)
config.addinivalue_line("markers", f"{_E2E_MARKER}: ...; skipped unless --run-e2e")
for marker, option in ((_BENCHMARK_MARKER, "--run-benchmark"), (_E2E_MARKER, "--run-e2e")):
    if config.getoption(option): continue
    skip = pytest.mark.skip(reason=f"{marker}: pass {option}")
```

### Error handling (what the assertions rely on)

```
# SOURCE: app/routers/query.py:50-83   - storage-caused gate error -> 503 + Retry-After, fixed copy;
#                                          AuditUnavailableError -> 503; other storage errors keep 500
# SOURCE: app/services/query_pipeline.py:826-833 (charge fails open), :956-966 (journal / R2),
#                                          :977-1001 (record -> StorageError -> mark_audit_log_failed -> ActionAuditError)
```

---

## Statement map (PRD Section 6.3 -> real call path -> `Fault`)

All faults are `Fault(text, sql=<prefix>, nth=<n>)`, `op="execute"`, `when="before"` (default), `times=1`. `text` is `INVALID_BATON` (class `DEAD_STREAM`) or `CONNECT_REFUSED` (class `NOT_SENT`); both from `tests/db_faults.py:48-78`. Prefixes are the whitespace-normalised, upper-cased start of the SQL (db_faults.py:81-99); `nth` counts only matches made after `faulty_db.add(...)`, so a fault added just before the target step needs `nth` only to skip an earlier same-prefix statement *inside* that step. Each case also asserts `faulty_db.fired == [that fault]` (proves the intended statement was hit, not a neighbour) and `faulty_db.connects` rose by at least one (the retry ran on a fresh client).

| # | Statement / function (database.py) | Real path the test drives | Fault prefix, nth | Armed |
|---|---|---|---|---|
| 1 | `find_user_by_token_hash` :2370 (`SELECT * FROM users WHERE token_hash`) | `POST /query` via `TestClient` with a user bearer token (`require_identity`) | `SELECT * FROM USERS WHERE TOKEN_HASH`, 1 | before the request |
| 2 | `get_chat_session` via `chat_sessions.owns` :2753 / query.py:161 | `POST /query` with `session_id` of a pre-created session | `SELECT * FROM CHAT_SESSIONS WHERE SESSION_ID`, 1 | before the request |
| 3 | `list_chat_messages` :3059 via `chat_history.assemble` (state.py:1138) | `ChatState` second send (history on) | `SELECT * FROM CHAT_MESSAGES`, 1 | between send 1 and send 2 |
| 4 | `admit_usage` :2565 | `POST /query` | `INSERT INTO USAGE_DAILY`, 1 | before the request |
| 5 | `find_duplicate_timestamp` :1611 | `POST /query` | `SELECT TIMESTAMP FROM AUDIT_LOGS`, 1 | before the request |
| 6a | `insert_audit_log` :1592, refusal row (`was_duplicate_blocked`) | `POST /query` same prompt twice; the second is the refusal | `INSERT INTO AUDIT_LOGS`, 2 (the 1st is the first send's success row) | between the two requests |
| 6b | `insert_audit_log`, the router's foreign-session refusal (query.py:161-178) | `POST /query` with another user's `session_id` -> 403 | `INSERT INTO AUDIT_LOGS`, 1 | before the request |
| 7 | `charge_usage` :2589 | `POST /query` | `UPDATE USAGE_DAILY SET INPUT_TOKENS`, 1 | before the request |
| 8 | `insert_audit_log`, success row | `POST /query` | `INSERT INTO AUDIT_LOGS`, 1 | before the request |
| 9 | `insert_action_decisions` :3193 (block of N rows, replayed from row 1) | `run_conversation(tools=..., call_openrouter=_Upstream("", _READ, _SHELL))` with 2 calls | `INSERT INTO ACTION_DECISIONS`, 2 (fails on row 2 so the block rollback is exercised, as test_db_resilience_faults.py:207-220 does) | before the call |
| 10 | `mark_audit_log_failed` :1662 | `run_conversation` with tools where the decisions write fails by a `STATEMENT` fault (`Fault(UNIQUE_SESSION_ID, sql="INSERT INTO ACTION_DECISIONS")`, applied to baseline **and** faulted runs as the scenario's precondition); outcome is `ActionAuditError` | `UPDATE AUDIT_LOGS SET SUCCESS = 0`, 1 | before the call |
| 11 | `create_chat_session` :2699 (lazy create) | `ChatState` first send | `INSERT INTO CHAT_SESSIONS`, 1 | before send 1 |
| 12 | `append_chat_message` :2953 | `ChatState` second send (user bubble is the first append once the session exists) | `INSERT INTO CHAT_MESSAGES`, 1 | between send 1 and send 2 |
| 13 | `touch_chat_session` :2844 | same | `UPDATE CHAT_SESSIONS SET UPDATED_AT`, 1 | between send 1 and send 2 |
| 14 | `get_chat_session` re-read after touch (state.py:973) | same; in send 2 the first `SELECT * FROM chat_sessions` is this re-read (`assemble` and `messages_for` come later and use other prefixes) | `SELECT * FROM CHAT_SESSIONS WHERE SESSION_ID`, 1 | between send 1 and send 2 |

Chat-only rows are 3, 11-14 (and 2 reaches `chat_sessions.owns` through `/query`, as PRD 6.3 row 2 says); rows 12-14 hit the user bubble's append, touch and re-read; the assistant bubble repeats them unfaulted, so the footprint compare covers both.

**What "equals the fault-free response" means.** Each scenario returns an `Observation(responses, footprint)`:
- `/query` responses: `response.status_code` + `response.json()` with `audit_id` and `audit_ref` removed (per-request fields, PRD-018 D14; the STORY-010 lesson in the brief). Retry-After header absent in both.
- tools cases: `QuerySuccessResponse.model_dump(exclude={"audit_id", "audit_ref"})` or the exception type name, plus `[(tool_call_id, decision)]` read back from `action_decisions`.
- chat cases: `[(m.kind, m.content) for m in state.messages]`, `state.pending is False`, `state.transcript_error == ""`, `state.sessions_error == ""`.
- `footprint` per user id, read with raw `get_connection()` queries: `audit_logs` row count and the `(success, was_duplicate_blocked, denied_permission)` tuples, `usage_daily` `requests`/`input_tokens`/`output_tokens`/`unsplit_tokens`, `chat_sessions` count, `chat_messages` count and `kind`s, `action_decisions` count. Timestamps, ids and write_ids are never compared.
- The baseline and the faulted runs use different user ids (and tokens) in the same test and database, so nothing collides in the duplicate window or the counters; the per-user footprint is what is compared. "Exactly one row per expected row lands" is the footprint equality plus, for the replayed-block case, `len(rows) == len(baseline rows)`.

---

## Design

### D-1. `tests/db_faults.py`: `Fault.follows` (commit faults aimed at one statement)

A `commit` fault matches "by occurrence only" (db_faults.py:25-27), but every unit commits, so "the commit of `admit_usage`" is the 2nd or 3rd commit depending on the route and would break on any added read. Add an optional last field `follows: str = ""` to `Fault`: for `op="commit"`, the fault matches only when the **last `execute` on that client** (normalised) starts with `follows.upper()`. `_FaultyClient` keeps `self._last_sql` (set in `execute`), and `_decide(op, sql="", last_sql="")` passes it to `Fault.matches(op, sql, last_sql="")`; the `calls` log keeps `("commit", "")` (existing tests assert it; not changed). Default `""` means unchanged behaviour. Update the module docstring's "Matching" paragraph and add 3 pure (non-`db`) tests of `Fault.matches` in the new module.

### D-2. `tests/db_faults.py`: `FaultScript.clear()` (the outage ends)

Empties `_faults`/`_seen` under the lock so an in-flight-outage test can say "the database is back" without uninstalling the proxy. One pure test.

Both are additive; the existing callers (`test_db_resilience_faults.py`, `_drain.py`, `_release.py`, `_retry.py`, `_write_id.py`) are in the targeted run to prove it.

### D-3. Cost control

Each `db` test pays ~3.5 s of fixture setup (`_reset_database`, conftest.py:612-684) and `temp_db` cannot be module-scoped (the autouse reset is per test). So a test = one **statement**, not one (statement x class): inside one test the baseline runs once and then the two faulted classes run sequentially under distinct user ids, with the class in every assertion message. That is 15 cases (rows 1-5, 6a, 6b, 7-14) at ~3.5 s setup + ~1-2 s of requests, retry sleeps (at most 0.25 s per fault) and chat-state steps. Expected runtime of `test_db_resilience_mvp.py`: **about 90-120 s, roughly 24 `db` tests + 4 pure ones**. The chaos file adds 2 skipped tests by default; with `--run-chaos` about 40-60 s. Parametrization is `@pytest.mark.parametrize("case", _CASES, ids=lambda c: c.id)` with ids `s01_identity`, `s02_session_owns`, `s03_history_read`, `s04_admit`, `s05_duplicate_lookup`, `s06a_refusal_row_duplicate`, `s06b_refusal_row_foreign_session`, `s07_charge`, `s08_success_row`, `s09_decisions_block`, `s10_mark_failed`, `s11_create_session`, `s12_append_message`, `s13_touch`, `s14_session_reread`.

### D-4. `OUTCOME_UNKNOWN` after the effect landed (spike Q1)

DML is not durable before `commit()`, so "landed then lost" is `Fault(NAMESPACE_SHUTDOWN_503, op="commit", when="after", follows=<prefix>)` (the commit is forwarded, then the error is raised; class `OUTCOME_UNKNOWN`, `NAMESPACE_SHUTDOWN_503` is captured text, db_faults.py:62-66). Never an `execute`/`after` fault (undone by the rollback, test_db_resilience_faults.py:189-201).

| Test | Fault `follows` | Path | Assertions |
|---|---|---|---|
| `test_a_landed_admit_is_counted_once_and_the_request_fails_closed` | `INSERT INTO USAGE_DAILY` | `POST /query` | status 503 + `Retry-After`, fixed copy (STORAGE_UNAVAILABLE_NOT_SENT_DETAIL), no driver text; `usage_daily.requests == 1` exactly; `faulty_db.forwarded("INSERT INTO USAGE_DAILY") == 1` (no replay); upstream stub `calls == []`; zero `audit_logs` rows; no `retry op=` log line (caplog, as faults.py:186) |
| `test_a_landed_charge_is_counted_once_and_the_answer_is_released` | `UPDATE USAGE_DAILY` | `POST /query`, baseline user vs faulted user | 200, body equals baseline (minus audit fields); `input_tokens`/`output_tokens`/`unsplit_tokens` equal the baseline's single charge; `requests == 1`; `forwarded("UPDATE USAGE_DAILY") == 1`; one `audit_logs` row (charge fails open, PRD 6.3 row 7) |
| `test_a_landed_append_is_one_message_not_two` | `INSERT INTO CHAT_MESSAGES` | `ChatState` second send (fault armed between sends) | `chat_messages` count and kinds equal the baseline's; `forwarded("INSERT INTO CHAT_MESSAGES")` equals the baseline's count (the faulted append reached the server once, was not replayed); no duplicate bubble after `messages_for` reload. (The `TRANSCRIPT_NOT_SAVED_NOTICE` is cleared by the next successful append, so it is not asserted at the end.) |
| control `test_a_landed_audit_row_is_replayed_to_the_same_row` | `INSERT INTO AUDIT_LOGS` (IDEMPOTENT, keyed) | `POST /query` | response equals baseline; exactly one `audit_logs` row for the user; `forwarded("INSERT INTO AUDIT_LOGS") == 2` (replayed) and the second hit `ON CONFLICT` (row id unchanged). Shows the rule is "kind decides", not "never retry" |

### D-5. In-flight request across an outage (AC 3, PRD 11 bullet 4)

`test_an_in_flight_request_across_an_outage_is_journaled_and_drains_to_one_row` (`faulty_db`, `journal` fixture, `monkeypatch` upstream stub). A user is seeded; the request goes through `TestClient` so the released JSON is the one a client sees.
1. Arm faults on **every statement after step 4**: `Fault(CONNECT_REFUSED, sql="UPDATE USAGE_DAILY", times=20)` (step 7b), `Fault(CONNECT_REFUSED, sql="INSERT INTO AUDIT_LOGS", times=20)` (step 8). Steps 1, 2c, 4 (identity, admit, duplicate lookup) run healthy: this is "the request was already past step 4 when the database went down". Record `before = {"audit_logs": 0}`.
2. `POST /query` -> assert 200, `body["audit_id"] is None`, `body["audit_ref"]` is 32 hex, upstream called exactly once, `journal.pending()` has one entry whose `write_id == body["audit_ref"]` and whose `audit.timestamp` is captured as `original_ts`; `audit_logs` count is 0 in the database (row is only in the journal); charge failed open (`input_tokens == 0`).
3. Duplicate overlay sanity (cheap, STORY-011): none, left to its own tests.
4. Recovery: `faulty_db.clear()` (D-2). The breaker (2 failed operations, threshold 5) is still closed; a second parametrization `breaker_opened` swaps in an injected-clock breaker (`CircuitBreaker("storage", threshold, open_seconds, clock=..., probe=database._probe_fresh_client)` as `_clocked_breaker` in test_db_resilience_drain.py:158-162), calls `force_open(10)` after the request, asserts `drain_once` returns `BREAKER_OPEN` with `faulty_db.forwarded("INSERT INTO AUDIT_LOGS") == 3` unchanged (no network while open) and the journal entry still pending, then advances the clock by 11 s so the breaker's own probe closes it on the same call.
5. `journal_drainer.drain_once(journal) is DrainOutcome.DRAINED`; then `SELECT COUNT(*) FROM audit_logs WHERE write_id = ?` is 1, that row's `timestamp == original_ts` (the event time, not the landing time, PRD 6.4), `SELECT COUNT(*) FROM audit_logs` is 1, `journal.pending() == []`. A second `drain_once` returns `EMPTY` and the count stays 1 (the kill-between-commit-and-checkpoint half of PRD 11 bullet 4 is already pinned by test_db_resilience_drain.py:321-342 and is referenced, not redone).
The journal fixture closes in `finally`/fixture teardown (conftest leak guard).

### D-6. `--run-chaos` / `chaos` marker (AC 4)

`tests/conftest.py` (edit, mirroring conftest.py:107-111, 160-178, 212-218):
- constant `_CHAOS_MARKER = "chaos"` beside `_E2E_MARKER`;
- `parser.addoption("--run-chaos", action="store_true", default=False, help="run @pytest.mark.chaos real-fault tests; they restart the shared libSQL dev server (PRD-018 STORY-013)")`;
- `config.addinivalue_line("markers", "chaos: real-fault test that restarts or blackholes the libSQL dev server; skipped unless --run-chaos")`;
- add `(_CHAOS_MARKER, "--run-chaos")` to the tuple in the `for marker, option in (...)` loop of `pytest_collection_modifyitems`, and extend that docstring with the invocation `pytest tests/test_db_resilience_chaos.py -m chaos --run-chaos -v -s`.
- A `chaos` test also uses `temp_db`, so it is `db`-marked: `-m db` in-network runs collect it and **skip** it (no `--run-chaos`), CI never passes the option. `scripts/test-db-in-network.sh` needs no change (its deselect list is for the two latency-script tests only).

`tests/test_chaos_marker.py` (new, non-`db`, 4 tests): the `tests/test_e2e_marker.py` pytester pattern (child over a copy of the real conftest, `HARNESS_TEST_LIBSQL_URL` at a dead port): skipped by default, `--run-chaos` runs it and leaves `benchmark`/`e2e` skipped, `--run-e2e` does not un-skip chaos, and `--markers` lists it.

`tests/test_db_resilience_chaos.py` (new, `@pytest.mark.chaos`, module `pytestmark`; all take `temp_db`). Keep two robust tests plus the guard:
1. `test_connection_refused_is_absorbed_then_refused_by_the_breaker`: `temp_db`, seed a user, then `monkeypatch.setattr(settings, "DATABASE_URL", "http://127.0.0.1:1")` + `database._invalidate_client()`. `find_user_by_token_hash` raises `StorageUnavailableError` after the retry budget (assert 3 attempts via `caplog` `retry op=` lines with `class=not_sent`); five such operations open the breaker; the sixth returns in well under the connect time (assert `< 0.5 s`, no `tcp connect` attempt: caplog has no new `retry op=`), with `retry_after_seconds >= 1`; and `POST /query` through `TestClient` with the override identity gives the Section 6.7 503 + `Retry-After` with no driver text. Restore settings and invalidate the client in `finally`. Needs no Docker.
2. `test_a_server_restart_under_a_live_client_is_absorbed_as_a_dead_stream`: warm the shared client (`find_user_by_token_hash` ok), `docker restart harness-libsql-dev` (`subprocess.run(["docker","restart","harness-libsql-dev"], check=True, timeout=60)`), poll a **separate** `libsql.connect(endpoint).execute("SELECT 1")` until it answers (<= 30 s; the shared client is not touched so the cached dead stream is kept), then call `find_user_by_token_hash` and `admit_usage("chaos-u")`: both return normally, caplog shows `retry op=... class=dead_stream` for the first call of each kind that met the dead stream, `usage_daily.requests == 1` (NON_IDEMPOTENT admit retried only because `DEAD_STREAM`@execute provably did not run). Assert on the classifier's contract, not on one exact driver text: either absorbed (result equals baseline) or `StorageUnavailableError`, but `requests` is never 2.
3. The guard is not a test but a `finally`/fixture (`_dev_server_running`): after every chaos test `docker start harness-libsql-dev` (no-op if running), wait for readiness, `database._invalidate_client()`, so the next suite test's `_reset_database` does not meet STREAM_EXPIRED (the recorded degradation pattern in `.agents/reports/PRD-008-*/STORY-006...report.md:83`). Tests skip with a reason (not fail) when `shutil.which("docker")` is None or `docker inspect harness-libsql-dev` fails, so a machine with an external `HARNESS_TEST_LIBSQL_URL` is not affected.
Data survives `docker restart`: the container mounts a named volume at `/var/lib/sqld` (checked with `docker inspect`).

### D-7. Latency (AC 5), measured by the implementer, not asserted in CI

No new benchmark assertion (the scripts record numbers and assert none by design, scripts/measure_usage_latency.py:3-8; the existing `--run-benchmark` pattern is for the PII corpus). Method, short runs, one worktree at a time:
1. `git worktree add --detach "<scratchpad>/main-wt" main` (detached: no branch is switched or created in the epic checkout). `main` carries `scripts/measure_usage_latency.py` and `admit_usage`/`charge_usage`, so the same script runs on both trees. It prepends its own repo root to `sys.path` (script :68-70), so run `G:/coding/harness-ai/.venv/Scripts/python <tree>/scripts/measure_usage_latency.py --runs 200` once from `<scratchpad>/main-wt` and once from the repo, **interleaved main, epic, main, epic** to expose drift, same `harness-libsql-dev` (do not restart it between runs; never two processes at once).
2. The script times only `admit` + `charge`. The epic also touched the identity read and the audit insert, so add a throwaway scratchpad script (not committed, same Samples/p50 method, `statistics.median`) that times `find_user_by_token_hash`, `usage_limits.admit`, `usage_limits.charge` and `audit_logger.log_query(...)` (returns an `int` on `main`, an `AuditRef` on the epic: the call is the same) over 200 runs, and report the sum of per-call p50 deltas as "added per request (p50)". Note the epic's `scripts/measure_usage_latency.py` statement check (`_statements_of` patches `database.get_connection`) must still pass on the epic: it asserts one statement per call, which doubles as proof of "no extra round trip".
3. Record in the report: the four p50/p95 tables, the deltas, the machine line the script prints, the verdict against 0.5 ms (PRD 11). A noise floor on this host (Docker Desktop port forward) is likely ~0.1-0.3 ms: report the spread of the two main runs next to the delta. If the delta exceeds 0.5 ms, do not tune in this story: report the number and the suspect (`_unit_of_work` + breaker `before()`/`record_success()` + counters) to the orchestrator.
4. `git worktree remove --force "<scratchpad>/main-wt"` then `git worktree prune`; confirm `git worktree list` shows only the epic checkout and `git status` is clean of the scratch.
The in-network `scripts/test-db-in-network.sh` runs are executed by the orchestrator/CI, not by the implementer.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_db_resilience_mvp.py` | CREATE | Statement map cases (1-14, 6a/6b), OUTCOME_UNKNOWN-after tests, in-flight outage test, `follows`/`clear` pure tests |
| `tests/test_db_resilience_chaos.py` | CREATE | Two `chaos` tests and the leave-the-server-running fixture |
| `tests/test_chaos_marker.py` | CREATE | pytester proof of the opt-in marker (mirrors `tests/test_e2e_marker.py`) |
| `tests/conftest.py` | UPDATE | `--run-chaos`, `chaos` marker, skip loop entry, docstring |
| `tests/db_faults.py` | UPDATE | `Fault.follows`, `FaultScript.clear()`, docstring |
| `.agents/reports/PRD-018-db-resilience/STORY-013-success-criteria-fault-suite.report.md` | CREATE (implement phase) | numbers, ACs, deviations |

No application file changes. No renamed or removed test function, so `_DELIBERATELY_SUPERSEDED_TESTS` is untouched.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: `Fault.follows` and `FaultScript.clear()`
- **File**: `tests/db_faults.py`
- **Action**: UPDATE
- **Implement**: D-1 and D-2. `Fault.matches(op, sql, last_sql="")`; `_FaultyClient._last_sql`; `_decide(op, sql="", last_sql="")`; `clear()`. Extend the module docstring (Matching paragraph, table row for `commit`/`after`).
- **Mirror**: `tests/db_faults.py:85-141` (frozen dataclass, lock discipline).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db_resilience_faults.py tests/test_db_resilience_retry.py -q -p no:cacheprovider` (unchanged behaviour with the default).

### Task 2: the `chaos` marker and option
- **File**: `tests/conftest.py`
- **Action**: UPDATE
- **Implement**: D-6 first bullet list (constant, option, marker line, loop tuple, docstring).
- **Mirror**: `tests/conftest.py:107-111, 160-178, 212-218`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_e2e_marker.py -q -p no:cacheprovider` (the e2e/benchmark behaviour is unchanged).

### Task 3: marker test
- **File**: `tests/test_chaos_marker.py`
- **Action**: CREATE
- **Implement**: D-6 second paragraph.
- **Mirror**: `tests/test_e2e_marker.py:1-80`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_chaos_marker.py -q -p no:cacheprovider` (4 passed).

### Task 4: scenario helpers and the 15 statement cases
- **File**: `tests/test_db_resilience_mvp.py`
- **Action**: CREATE
- **Implement**: module docstring (cite PRD-018 Section 11 / 12, D18, spike Q1; say that each test is one statement and why, D-3). Helpers: `_world(temp_db, monkeypatch)` seeding two or three users by `insert_user` with `hash_token`, a recording upstream stub patched on `app.routers.query.call_openrouter` and `chat_state_mod.call_openrouter`; `Observation`; `_footprint(user_id)`; `Case(id, prefix, nth, scenario)`; scenario functions (`_q_success`, `_q_session`, `_q_two_sends`, `_q_foreign_session`, `_tools_ok`, `_tools_decisions_fail`, `_chat_first_send`, `_chat_second_send`) each taking `(world, user, arm)`; `arm()` is called at the "Armed" point of the statement map and is a no-op for the baseline. The parametrized test (`async` because of `ChatState`, `@pytest.mark.asyncio` as in test_chat_history_send.py:165) runs the baseline, then for `(DEAD_STREAM, INVALID_BATON)` and `(NOT_SENT, CONNECT_REFUSED)` the faulted run, and asserts the equality, `fired`, `connects` points of the Statement map section. A single synchronous-looking `/query` scenario still runs inside the async test via the `TestClient` (blocking is fine). Pure tests for `Fault.follows` (3) and `FaultScript.clear` (1).
- **Mirror**: `tests/test_db_resilience_faults.py:49-92` (helpers), `tests/test_query_pipeline_usage_limits.py:116-169` (usage readers), `tests/test_chat_history_send.py:72-96` (`_make_state`, `_send`), `tests/test_db_resilience_release.py:121-146` (`_Upstream`, `_run_tools`).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db_resilience_mvp.py -q -p no:cacheprovider -k "s0 or s1 or follows or clear"`. If a case fails, see "If a proof fails" below.

### Task 5: OUTCOME_UNKNOWN-after tests (D-4)
- **File**: `tests/test_db_resilience_mvp.py`
- **Action**: UPDATE (same file)
- **Implement**: the three tests and the control of D-4, reusing the Task 4 helpers.
- **Mirror**: `tests/test_db_resilience_faults.py:176-186`.
- **Validate**: `... -k "landed"`.

### Task 6: in-flight outage test (D-5)
- **File**: `tests/test_db_resilience_mvp.py`
- **Action**: UPDATE (same file)
- **Implement**: D-5, two parametrizations (`plain`, `breaker_opened`), journal fixture local to the module (copy of test_db_resilience_release.py:91-96).
- **Mirror**: `tests/test_db_resilience_release.py:602-627`, `tests/test_db_resilience_drain.py:158-162`.
- **Validate**: `... -k "in_flight"`.

### Task 7: chaos tests (D-6)
- **File**: `tests/test_db_resilience_chaos.py`
- **Action**: CREATE
- **Implement**: D-6 third paragraph. Run them **once** by hand with `--run-chaos` (the implementer must run the file once to prove it, then confirm `docker ps` shows `harness-libsql-dev` Up and `curl -s http://127.0.0.1:8080/health` answers). Never two pytest processes at once; run it alone, after the other targeted files.
- **Mirror**: `.agents/PRDs/PRD-018-db-resilience/PRD.md:518`, conftest.py:576-598 (the probe) for the readiness poll.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db_resilience_chaos.py -m chaos --run-chaos -q -p no:cacheprovider -s`, and without the option: 2 skipped.

### Task 8: latency (D-7) and report
- **File**: scratchpad script + report
- **Action**: run, record
- **Implement**: D-7. Numbers go in the report; nothing from the scratchpad is committed. Remove the worktree.
- **Validate**: `git worktree list` shows one entry.

### If a proof fails

A failing case is a finding. Classify it: (a) test wiring (wrong prefix or nth: `fired` empty or hit the wrong statement) - fix the test; (b) a real defect in resilience code - fix in this story only if the change is small, local and inside PRD-018 (cite the decision in the commit message and add the failing case as the regression), otherwise **stop, keep the failing case as an `xfail(strict=True, reason=...)` only if the orchestrator agrees, and report** (case id, the observed vs expected, the PRD row). Never relax an equality to make a case pass.

---

## End-to-End Tests

- [ ] `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db_resilience_mvp.py -q -p no:cacheprovider` -> all pass (about 22 db + 4 pure, 90-120 s).
- [ ] `... tests/test_db_resilience_chaos.py -m chaos --run-chaos -s` -> 2 real-fault tests pass, dev server still Up afterwards; without the option 2 skipped.
- [ ] Latency numbers recorded for `main` vs epic, delta vs 0.5 ms stated.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider \
  tests/test_db_resilience_mvp.py tests/test_chaos_marker.py tests/test_e2e_marker.py \
  tests/test_db_resilience_faults.py tests/test_db_resilience_retry.py tests/test_db_resilience_drain.py \
  tests/test_db_resilience_release.py tests/test_db_isolation_harness.py tests/test_conftest_fixtures.py
# then, alone:
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_db_resilience_chaos.py -m chaos --run-chaos -s
```

Targeted set rationale (brief rule: no full suite): new files; the two pre-existing modules touched (`conftest.py` -> marker/isolation tests `test_e2e_marker.py`, `test_db_isolation_harness.py`, `test_conftest_fixtures.py`; `db_faults.py` -> every module that imports it: faults, retry, drain, release, plus `test_db_resilience_write_id.py` and `test_db_resilience_headroom.py`/`_overlay.py` if they import it - run `grep -l db_faults tests/*.py` and include every hit). No app file is touched, so `test_untouched_app.py` is not needed; no test is renamed, so `test_pii_redaction_integration.py` is not needed. Record exact counts. "Full suite: GitHub CI on push (user decision)".

## Acceptance Criteria

(Copied from story STORY-013, with how each is covered)

- [ ] AC 1: parametrized `DEAD_STREAM`/`NOT_SENT` on each of statements 1-14, response equals fault-free, one row per expected row -> Task 4 (`test_db_resilience_mvp.py`, one case per statement id `s01`..`s14`, plus `s06b`).
- [ ] AC 2: `OUTCOME_UNKNOWN` after `admit_usage`, `charge_usage`, `append_chat_message` executed -> never replayed, counters/transcript move by one -> Task 5 (three tests + control, `Fault(op="commit", when="after", follows=...)`).
- [ ] AC 3: in-flight across an outage -> released, journaled, one row with original `timestamp` and `write_id` after recovery and drain -> Task 6.
- [ ] AC 4: `--run-chaos` option and `chaos` marker, skipped by default; `127.0.0.1:1` and `docker restart harness-libsql-dev` -> Tasks 2, 3, 7.
- [ ] AC 5: p50 added latency < 0.5 ms recorded in the report; suite and `scripts/test-db-in-network.sh` green (orchestrator/CI runs the in-network script) -> Task 8.
- [ ] All tasks completed
- [ ] `from app.main import app` imports
- [ ] No application file changed; no pinned assertion changed
- [ ] The dev server is left running and unpaused
- [ ] Follows existing patterns
