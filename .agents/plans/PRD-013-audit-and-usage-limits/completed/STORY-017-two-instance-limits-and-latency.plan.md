---
story: STORY-017
prd: PRD-013-audit-and-usage-limits
slug: two-instance-limits-and-latency
title: "Two-instance limit test and latency measurement"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-013-audit-and-usage-limits
created: 2026-10-20
---

# Plan: Two-instance limit test and latency measurement

## Summary

Two pieces of evidence for PRD-013 F17 / T5 / Risk 1. First, `tests/test_two_instance_smoke.py` gets three scenarios on its existing harness: a rate limit of 5 holds across two running processes, a token budget used up on instance A is refused on instance B, and a second user is admitted the whole time. Limits are set by the parent with `set_user_limits` while both children are running, so no child restarts and no new harness is needed. Second, a new spike script, `scripts/measure_usage_latency.py`, times `usage_limits.admit` and `usage_limits.charge` (the two service calls only, not the pipeline) and prints p50/p95 over a stated number of runs. Its bootstrap, `Samples` and local-only guard follow `scripts/measure_history_latency.py`. The variant measured is STORY-009 **Path A**: the single `INSERT … ON CONFLICT … RETURNING` statement for admit plus one `UPDATE` for charge. No fallback shipped.

## User Story

As a compliance admin
I want proof that limits hold across instances and a measured cost for checking them
So that adding a container is not a way to double a budget and the latency is known before deployment

## Story Reference

- Story file: `.agents/stories/PRD-013-audit-and-usage-limits/STORY-017-two-instance-limits-and-latency.md`
- PRD: `.agents/PRDs/PRD-013-audit-and-usage-limits/PRD.md` (sections 7 F17, 9.2 T5, 11 "Cross-instance and latency", 14 Risks 1–2)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (tests + spike script) |
| Complexity | MEDIUM |
| Systems Affected | `tests/test_two_instance_smoke.py`, `scripts/` (new script), `tests/` (new script test) |
| Story | STORY-017 |
| PRD | PRD-013-audit-and-usage-limits |
| Epic Branch | `epic/PRD-013-audit-and-usage-limits` (commit directly on this branch) |

No `app/` change. No UI surface. Dependency STORY-012 is `done`.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` holds only `frontend-design`. This story has no UI surface, so no skill applies (matches the story's `skills: []`). | — |

---

## Key Facts From Exploration

1. **Limits can change under running children.** `resolve()` reads the `users` row on every request (`app/db/database.py:1620-1647`, `set_user_limits` docstring), so the per-user overrides `token_budget_daily` / `requests_per_minute` reach `Identity` without a restart. `limits_for` (`app/services/usage_limits.py:100-122`) gives the override precedence. Setting limits through env would need new children, and the `instances` fixture is module-scoped (`tests/test_two_instance_smoke.py:775-796`). **Use `set_user_limits` from the parent.**
2. **Per-test reset already isolates counters.** `tests/conftest.py:192-220` drops every table before each test, and `fresh_schema` (`:799-812`) re-creates them, `usage_daily` included. Each new test starts with no counters and no overrides, and no existing test sees the overrides these tests set.
3. **Rate refusal is `>`, budget refusal is `>=`** (`usage_limits.py:159-185`). With limit 5, attempts 1–5 are admitted and attempts 6–10 are refused with `actual` 6, 7, 8, 9, 10. Each attempt is counted even when it is refused. Admit is one atomic statement (`database.py:1680-1720`), so concurrent attempts get distinct `window_requests`.
4. **Refusal body:** HTTP 200, `{"status": "BLOCKED", "reason": "Usage limit reached", "limit": "requests"|"tokens", "maximum", "actual", "resets_at"}` (`app/models/schemas.py:134-160`, `app/services/query_pipeline.py:403`).
5. **What the child's stub charges.** `fake_call_openrouter` returns `tokens_used=7` with no split (`test_two_instance_smoke.py:185-188`), so each SUCCESS charges `unsplit_tokens += 7` (`query_pipeline.py:694-701` → `usage_limits.py:209-212`). A budget of 7 is used up by exactly one answered query. **The stub stays unchanged:** `do_query` and the round-trip test assert against it.
6. **The window is the database's minute.** `window_start = strftime('%s','now') / 60` (`database.py:1680-1688`). The DB clock can't be frozen. Planting a row doesn't stop a straddle either: the `CASE` resets `window_requests` to 1 whenever the minute changes. A guard is the only way to avoid one (see Risk R1).
7. **Order inside the pipeline:** the identity read comes first, then the usage gate (step 2c), then the duplicate check. A refused attempt never reaches dedup. Admitted attempts do, so every prompt in the new scenarios has to be unique.
8. **Variant:** STORY-009 report: "`admit_usage` ships as **Path A**: one statement, one round trip. The upsert-plus-`SELECT` fallback was not needed." The script prints this, and checks it by counting statements.
9. **Remote endpoints** need `TURSO_AUTH_TOKEN` (`app/config.py:163-166, 371-373`). The client cache keys on `(DATABASE_URL, TURSO_AUTH_TOKEN)` (`database.py:117`).

---

## Patterns to Follow

### Naming / harness: the parent drives children over the pipe
```python
# SOURCE: tests/test_two_instance_smoke.py:988-1000
for index in range(_CONCURRENT_QUERIES_PER_INSTANCE):
    for instance in instances:
        instance.send(
            cmd="query", prompt=prompts[instance.name][index], token=smoke_user
        )

failures = []
for index in range(_CONCURRENT_QUERIES_PER_INSTANCE):
    for instance in instances:
        reply = instance.recv()
```

### Second identity written inline by the test, not by a fixture
```python
# SOURCE: tests/test_two_instance_smoke.py:1334-1340
insert_user(
    User(
        user_id=_OTHER_USER_ID,
        role="user",
        token_hash=hash_token(_OTHER_TOKEN),
    )
)
```

### Warm the analyzer before anything timing-sensitive
```python
# SOURCE: tests/test_two_instance_smoke.py:1399-1403
# One warm query first: the first call in a process pays for the PII
# analyzer's model load, which is not a round trip and must not be counted
# as one.
warmup = instance_a.call(cmd="query", prompt="warm the analyzer", token=smoke_user)
```

### Script bootstrap: environment before the first `app.` import
```python
# SOURCE: scripts/measure_history_latency.py:74-98
_DEFAULT_ENDPOINT = "http://127.0.0.1:8080"

def _database_url(argv): ...  # --database-url, else HARNESS_TEST_LIBSQL_URL, else dev server

def _bootstrap_environment(argv=None) -> str:
    endpoint = _database_url(argv)
    os.environ["DATABASE_URL"] = endpoint
    os.environ.setdefault("OPENROUTER_API_KEY", "measurement-stub-key")
    os.environ.setdefault("ADMIN_TOKEN", "measurement-admin-token")
    return endpoint

_ENDPOINT = _bootstrap_environment()

from app.config import settings  # noqa: E402
```

### Percentiles, recording proxy, local guard
```python
# SOURCE: scripts/measure_history_latency.py:309-334  (Samples: min, median, nearest-rank p95)
# SOURCE: scripts/measure_history_latency.py:265-300  (Recording + _statements_of)
# SOURCE: scripts/measure_history_latency.py:349-360  (_guard_local / --allow-remote-database)
# SOURCE: scripts/measure_history_latency.py:748-794  (_build_parser / main(argv) -> int)
```

### Error handling
Tests follow the harness's existing rule: `Instance.recv` fails the test with the child's error and stderr (`:722-767`), and nothing new is needed. The script follows the history script: it raises `SystemExit` with a message for a refused remote endpoint, and returns `1` with a stderr line when a precondition fails (`measure_history_latency.py:704-711`). A refused or failed `admit` during measurement aborts the run. A sample never gets recorded for the wrong path.

### Script tests: pure parts only, plus a fresh-interpreter import probe
```python
# SOURCE: tests/test_measure_pii_latency.py:14-40
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
import scripts.measure_pii_latency as bench
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_two_instance_smoke.py` | UPDATE | Three PRD-013 scenarios (rate, budget, second user), helpers, docstring paragraph, invariant 1 wording |
| `scripts/measure_usage_latency.py` | CREATE | Times `admit` and `charge`, prints p50/p95 and statement counts |
| `tests/test_measure_usage_latency.py` | CREATE | Pure-part tests and one short run against the dev server |
| `.agents/reports/PRD-013-audit-and-usage-limits/STORY-017-two-instance-limits-and-latency.report.md` | CREATE (by `/implement`) | Measured numbers: local, plus remote or a statement that none was available |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Rate-window guard and usage helpers in the smoke file

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: UPDATE (new section after the PRD-010 section, before `# AC 7 -- what keeps this deterministic`)
- **Implement**:
  - Section header `# PRD-013 STORY-017 -- usage limits, two instances, one counter`.
  - Import `set_user_limits` and `get_connection` from `app.db.database` alongside `insert_user`.
  - `_insert_other_user()`: the two-line `insert_user(User(_OTHER_USER_ID, "user", hash_token(_OTHER_TOKEN)))` from `:1334-1340`, pulled out because three tests now need it. **Leave the existing call at `:1334` alone** (AC 5: no existing test changes).
  - `_RATE_LIMIT = 5`, `_RATE_ATTEMPTS = 10`, `_BUDGET = 7` (with a comment: "one answered query at the child stub's `tokens_used=7`"), `_FRESH_WINDOW_MARGIN_S = 15`.
  - `_db_second() -> int`: the parent reads `CAST(strftime('%s','now') AS INTEGER) % 60` through `get_connection()`. This is the **database's** clock, the one `admit_usage` uses, never Python's.
  - `_fresh_rate_window()`: if `60 - _db_second() < _FRESH_WINDOW_MARGIN_S`, wait once with `time.sleep(60 - second + 1)`, then re-read and assert it rolled over. That is at most ~16 s, once, and only to step off a minute boundary. Docstring: it is the file's **only** wait. It waits for the clock, never for work to finish, and the story's Technical Notes ask for it.
  - `_usage_row(user_id) -> dict`: the parent does a raw `SELECT requests, window_start, window_requests, input_tokens + output_tokens + unsplit_tokens AS tokens FROM usage_daily WHERE user_id = ? AND day = date('now')`. It is used for the post-hoc "all in one window" check.
- **Mirror**: `_reset_upstream` / `_limits` helpers at `:1509-1539` (the shape of small private helpers and their docstrings).
- **Validate**: `C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe -m pytest tests/test_two_instance_smoke.py -q` (still green; no test added yet)

### Task 2: AC 1 + AC 3: a rate limit of 5 admits exactly 5 of 10 alternating requests

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: UPDATE
- **Implement**: `test_a_rate_limit_of_five_admits_five_of_ten_alternating_requests(instances, smoke_user)`:
  1. `_insert_other_user()`. **Warm both children with the other user**: one query each with a unique prompt, asserted SUCCESS. Warming with the smoke user would spend its window. A cold child (`-k` run) pays several seconds of spaCy load, which could otherwise push the batch across a minute.
  2. `assert set_user_limits(_USER_ID, requests_per_minute=_RATE_LIMIT)`.
  3. `_fresh_rate_window()`.
  4. Send the whole batch **before reading any reply**, alternating A, B, A, B… with smoke-user prompts `f"rate probe {index} via {instance.name}"` (unique, so the admitted ones never collide in dedup). Put one other-user query per instance in the middle of the batch (AC 3, "during").
  5. Read every reply. Smoke user: `sum(SUCCESS) == 5`; refused replies all have `status == "BLOCKED"`, `reason == "Usage limit reached"`, `limit == "requests"`, `maximum == 5`, and `sorted(actual) == [6, 7, 8, 9, 10]`. Distinct values prove the counter is shared and atomic across processes, and the assertions run over totals, never over which instance won (invariant 3). Every refused `resets_at` is equal. Both other-user replies are SUCCESS.
  6. Post-hoc: `_usage_row(_USER_ID)` gives `requests == 10` and `window_requests == 10`, so all ten landed in one window. If the guard ever fails, this line names the straddle instead of a misleading count.
  7. After the batch, the other user sends once more through **each** instance and gets SUCCESS (AC 3, "either instance").
- **Docstring**: PRD T5 and F17. Explain why the sends go out together (both processes in flight) and why the other user did the warm-up.
- **Validate**: `... -m pytest tests/test_two_instance_smoke.py -q -k rate_limit_of_five`, then run it 3× in a row to check for flakes.

### Task 3: AC 2 + AC 3: a budget exhausted through A is refused on B

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: UPDATE
- **Implement**: `test_a_budget_exhausted_through_instance_a_is_refused_on_instance_b(instances, smoke_user)`:
  1. `_insert_other_user()`. `assert set_user_limits(_USER_ID, token_budget_daily=_BUDGET)`.
  2. `instance_a.call(query, unique prompt, smoke token)` gives SUCCESS. Then `_usage_row(_USER_ID)["tokens"] == 7`: the charge landed, and it was written by A.
  3. `instance_b.call(query, a different unique prompt, smoke token)` gives `BLOCKED` with `limit == "tokens"`, `maximum == 7`, `actual == 7`, and `resets_at` ending in `T00:00:00Z`. B never answered anything for this user, so the 7 can only have come from the shared row.
  4. Other user through A, then through B: both SUCCESS (AC 3).
  5. Control, so the refusal can't be put down to "B refuses everything": `instance_a` with the smoke token also gets `limit == "tokens"`.
- No minute guard is needed: the budget is per UTC day, and the rate default (`*=60`) is far away. A midnight straddle is possible in principle; note it in one docstring line and accept it, the same way the PRD accepts it for `day`.
- **Validate**: `... -m pytest tests/test_two_instance_smoke.py -q -k budget_exhausted`

### Task 4: Module docstring and invariant 1

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: UPDATE (prose only; **no assertion and no `_INVARIANTS` entry changes**)
- **Implement**:
  - Add a module-docstring paragraph after "Three epics, now.": **"Four epics."** PRD-013 STORY-017 adds the limits half. The usage counter is one row in the shared database, so a second container cannot double a budget. Say why `set_user_limits` rather than env (the children are module-scoped and resolve reads the row each request).
  - Amend invariant 1's comment text to name the single exception: `_fresh_rate_window()`, a bounded one-shot wait on the database's clock that steps off a minute boundary and never waits for work. Keep the `"no sleep"` string in `_INVARIANTS` as it is. It still describes every ordering in the file, and AC 5 forbids changing existing assertions.
- **Validate**: `... -m pytest tests/test_two_instance_smoke.py -q` (whole file green, AC 5)

### Task 5: `scripts/measure_usage_latency.py`

- **File**: `scripts/measure_usage_latency.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring in the history script's style: PRD-013 STORY-017, F17, Risk 1. It is a spike that records numbers and asserts none. It times the **two service calls only** (`usage_limits.admit`, `usage_limits.charge`), not the pipeline. Variant: STORY-009 Path A (single `RETURNING` upsert), so admit is 1 statement and charge is 1 statement. It also gives usage lines and the `docker run` line for the dev server.
  - Bootstrap copied from `measure_history_latency.py:74-98` (`_DEFAULT_ENDPOINT`, `_database_url`, `_bootstrap_environment` with `os.environ.setdefault` for `OPENROUTER_API_KEY` / `ADMIN_TOKEN`), with the same "do not tidy the imports" comment. **Don't** import the history script: that would pull Presidio and the pipeline in for no reason.
  - `Recording`/`_statements_of`, `Samples`, `_timed`, `_guard_local`, `_LOCAL_HOSTS`: copied, each citing its source line. The repo has no shared bench module, and adding one is out of scope.
  - Bench identity: `Identity(user_id=f"{args.user_id}-{nonce}", role="user", requests_per_minute=10**9, token_budget_daily=None)`. The rate override means `--runs` above 60 still measures the **admitted** path. The budget falls back to the role default (`*=1000000`), and the bench charges 7 tokens per run (`input=5, output=2`), so the budget can't be reached. Each run asserts `admission.admitted`. A refusal aborts with exit 1, so a refusal-path sample can't be recorded by mistake.
  - Measurement: one discarded warm-up pair (it also takes the insert path, which creates the day's row), then `--runs` iterations (default **50**) of `admission = timed(admit)` then `timed(charge(user, admission.day, 5, 2, 7))`. Before the timed loop, one extra pair goes through `_statements_of` and asserts exactly one statement each. This proves which variant is in force (`INSERT … RETURNING`, `UPDATE usage_daily`).
  - Report: endpoint, host (`platform.node()`), Python, runs, variant line, the statement first-words for each call, then a table `call | n | min | p50 | p95` for `admit` and `charge`, plus `admit + charge (p50)`, which is the per-request added cost. Also print the history script's footnote: "p50 is the median; p95 is nearest-rank…; no latency here is asserted".
  - Cleanup in `finally` unless `--keep`: a raw `DELETE FROM usage_daily WHERE user_id = ?` through `database.get_connection()`. The comment explains that only the bench's own nonce-scoped row is touched, that `usage_daily` has no public delete, and that otherwise the row would show in the console's Usage table.
  - CLI: `--runs`, `--database-url`, `--user-id` (default `story017-bench`), `--keep`, `--allow-remote-database`; `main(argv) -> int`.
- **Mirror**: `scripts/measure_history_latency.py` (whole structure); `app/services/usage_limits.py:139-238` (call signatures).
- **Validate**: `PYTHONPATH=. C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe scripts/measure_usage_latency.py --runs 50` against `harness-libsql-dev` prints both rows. Then run it again with `--database-url https://example.invalid` and confirm the refusal.

### Task 6: `tests/test_measure_usage_latency.py`

- **File**: `tests/test_measure_usage_latency.py`
- **Action**: CREATE
- **Implement** (mirror `tests/test_measure_pii_latency.py`):
  - Import probe in a fresh interpreter: importing the script opens no DB connection and builds no analyzer. Assert `pii_redactor._analyzer is None` and that `database._client is None`.
  - `Samples.summary()` is nearest-rank: n=20 values 1..20 give p95 = 19; n=50 give p95 = 48.
  - `_guard_local` passes `127.0.0.1` / `localhost`, raises `SystemExit` for a remote host, and passes a remote host when `allow_remote=True`.
  - One end-to-end `main(["--runs", "3"])` against the conftest endpoint (the autouse fixture has already pointed `settings.DATABASE_URL` there), capturing stdout. The output contains `admit`, `charge`, `p50`, `p95`, and `1 statement`. Afterwards no `usage_daily` row remains for the bench prefix.
- **Validate**: `... -m pytest tests/test_measure_usage_latency.py -q`

### Task 7: Measure, then write the report

- **File**: `.agents/reports/PRD-013-audit-and-usage-limits/STORY-017-two-instance-limits-and-latency.report.md` (written by `/implement`)
- **Implement**:
  - Run the script 3× with `--runs 50` against the local dev server, and record every run's p50/p95 (not only the best one).
  - Remote run: if the user can supply a Turso URL plus `TURSO_AUTH_TOKEN`, run `--allow-remote-database --database-url <url>` with the token in the environment. Otherwise the report says plainly that **no remote endpoint was available** (AC 4 allows this) and names the command to run later.
  - State the variant (Path A, 1 + 1 statements) and the added round trips per request (2, from 3 to 5, already pinned by `test_round_trip_cost_is_measured_and_reported`). STORY-018 copies these into the README.
- **Validate**: the report has a numbers table plus a line on the remote run (done, or none available).

---

## End-to-End Tests

- [ ] `docker start harness-libsql-dev` (start Docker Desktop first if needed), then `python -m pytest tests/test_two_instance_smoke.py -v`: every test passes, the existing ones untouched (AC 5), the new rate and budget tests green.
- [ ] Run the rate test alone 3× (`-k rate_limit_of_five`). This covers the cold-child warm-up path and the guard. If a run triggers the guard wait, note how long it took.
- [ ] Temporarily set `_FRESH_WINDOW_MARGIN_S = 60` locally to force the wait. Confirm it waits less than 61 s, then the test passes. Revert.
- [ ] Mutation check (not committed): in the child, give instance B its own counter (e.g. patch `usage_limits.admit_usage` in one child to use a per-process dict). The rate test should fail with 10 admitted or `actual` values not distinct. Revert. This shows the test can detect the T5 failure.
- [ ] `python scripts/measure_usage_latency.py --runs 50` prints admit/charge p50/p95, `1 statement` each, and the Path A variant line. Then `SELECT COUNT(*) FROM usage_daily WHERE user_id LIKE 'story017-bench%'` returns 0.
- [ ] `python scripts/measure_usage_latency.py --database-url https://x.turso.io` without the flag is refused with the guard message.
- [ ] Remote run (if an endpoint is available), recorded in the report.

---

## Validation

```bash
cd C:/Users/tobip/OneDrive/Documentos/prog/harness-ai
C:/Users/tobip/.venvs/harness-ai/Scripts/python.exe -m pytest tests/test_two_instance_smoke.py tests/test_measure_usage_latency.py -q
C:/Users/tobip/.venvs/harness-ai/Scripts/python.exe -m pytest tests/test_usage_limits.py tests/test_usage_storage.py tests/test_query_pipeline_usage_limits.py -q
PYTHONPATH=. C:/Users/tobip/.venvs/harness-ai/Scripts/python.exe scripts/measure_usage_latency.py --runs 50
```

Shared-DB flakes (`STREAM_EXPIRED`, connect error 10060) are a known issue (PRE-PRD-017). If the suite slows sharply, `docker restart harness-libsql-dev` and rerun only the errored files before blaming the change.

---

## Risks

| # | Risk | Mitigation |
|---|------|-----------|
| R1 | The rate batch straddles a DB minute, `window_requests` resets, and more than 5 are admitted (a flake) | `_fresh_rate_window()` reads the **DB's** second and waits once if fewer than 15 s are left. Warm-up runs before the check, as the other user. The post-hoc `window_requests == 10` check names a straddle explicitly. The wait is the file's one documented exception to invariant 1. A straddle can't be prevented without it: planting a row doesn't help, because the `CASE` resets on any minute change. |
| R2 | The new tests' overrides leak into later tests | They can't. conftest drops `users` and `usage_daily` before every test, and `smoke_user` re-inserts without overrides. |
| R3 | A refused attempt also writes an audit row, and a later test counts audit rows | Same reason as R2: tables are reset per test. No existing count spans tests. |
| R4 | The budget scenario depends on the stub's `tokens_used=7` | Name it in the `_BUDGET` comment. Assert `_usage_row(...)["tokens"] == 7` after A's answer, so a changed stub fails at the precondition with a clear message instead of at the refusal. |
| R5 | Bench numbers are same-host and understate a remote endpoint | The report says so (the same caveat STORY-016/011 recorded), and the remote run (or its absence) is recorded separately. |
| R6 | Script cleanup deletes someone's real row | The DELETE is scoped to the nonce-suffixed bench `user_id` only. Remote runs need `--allow-remote-database`. |

---

## Acceptance Criteria

(Copied from story `STORY-017`)

- [ ] Given two application processes on one database and a user with a rate limit of 5, when 10 requests alternate between the processes within one minute, then exactly 5 are admitted and 5 return the usage-limit body.
- [ ] Given a user whose budget is exhausted by requests through instance A, when the next request goes to instance B, then it is refused with `limit="tokens"`.
- [ ] Given a second user during both scenarios, when they send through either instance, then they are admitted.
- [ ] Given `python scripts/measure_usage_latency.py`, when it runs against the local libSQL dev server, then it prints p50 and p95 for `admit` and for `charge` over a stated number of runs, and the story report records those numbers plus one run against a remote endpoint (or states that none was available).
- [ ] Given the existing two-instance smoke scenarios, when the file runs, then they pass with no assertion changed.
- [ ] All tasks completed
- [ ] Follows existing patterns (harness pipe protocol, history-script bootstrap)
- [ ] Measured variant (Path A) stated in the script output and the report
