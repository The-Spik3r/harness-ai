---
story: STORY-007
prd: PRD-007
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-007-concurrent-safe-init-db.plan.md
epic_branch: epic/PRD-007-turso-migration
commit: pending
status: COMPLETE
completed: 2026-09-01
---

# Implementation Report — STORY-007: Concurrency-safe `init_db()` / `_add_missing_columns()`

**Plan**: `.agents/plans/PRD-007-turso-migration/completed/STORY-007-concurrent-safe-init-db.plan.md`
**Epic Branch**: `epic/PRD-007-turso-migration`
**Commit**: `pending` (recorded by the follow-up chore commit, as for STORY-004/005/006)

## Summary

`_add_missing_columns()` now treats *this column already exists* as success and re-raises everything
else, so the instance that loses the read-then-`ALTER` race converges instead of crashing at import
time. The pre-check is untouched — it is what keeps a steady-state boot from issuing any `ALTER` at
all — and the handler covers only the window between the `PRAGMA` and the `ALTER`. Fifty-seven lines
of production change; the weight of the story is six new tests, four of them deterministic.

The headline evidence is not a unit test. Eight real processes started together against a pre-PII
schema: **with** the change all eight exit 0 in every round; **without** it, five or six of the eight
exit 1. That is Risk 3's "a container that will not boot", reproduced and then removed.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Probe: does a failed statement poison the transaction? | `scratchpad/probe_alter_failure.py` (throwaway) | ✅ answered: **no** |
| 2 | `_DUPLICATE_COLUMN` pattern + `_is_duplicate_column()` | `app/db/database.py` | ✅ |
| 3 | Narrow handler around the `ALTER` | `app/db/database.py` | ✅ |
| 4 | Deterministic forced-loser test | `tests/test_db.py` | ✅ |
| 5 | Deterministic two-thread interleave | `tests/test_db.py` | ✅ |
| 6 | Propagation tests (locked; duplicate naming another column) | `tests/test_db.py` | ✅ (split into two) |
| 7 | N-thread convergence, empty database | `tests/test_db.py` | ✅ |
| 8 | N-thread convergence, partially migrated database | `tests/test_db.py` | ✅ |
| 9 | Record the `PRAGMA table_info` shape answer (AC6) | this report | ✅ |

## Task 1 — the probe, and what it settled

Run against the live libSQL endpoint. Both answers are recorded here because Design Note D2 gated
the implementation on the first and AC6 asks for the second.

**D2 — a failed statement does *not* poison the surrounding transaction.** A duplicate `ALTER` was
issued mid-block; the `CREATE TABLE` and `INSERT` that followed it in the same
`with get_connection()` block both survived the commit:

```
=== duplicate ADD COLUMN raised ===
builtins.ValueError: Hrana: `stream error: `Error { message: "SQLite error: duplicate column name: b", code: "SQLITE_UNKNOWN" }``

=== post-failure statements survived the commit? ===
probe_t2 created : True
inserted row     : True
=> transaction poisoned: False
```

So the plan's primary design stands and D2's fallback (one `_session()` per `ALTER`) was not needed.
The captured message is byte-identical in shape to what STORY-006 recorded, which is what
`_DUPLICATE_COLUMN` is written against.

**AC6 — the `PRAGMA table_info` result shape needs no handling.** Rows come back as `_Row`, carrying
exactly `sqlite3`'s six `table_info` column names, and both name and positional access work:

```
row type   : _Row
row.keys() : ['cid', 'name', 'type', 'notnull', 'dflt_value', 'pk']
row["name"]: ['a', 'b']
positional : (0, 'a', 'INTEGER', 0, None, 0)
```

`_Cursor`/`_Row` (`app/db/database.py`) already map `cursor.description` onto the driver's tuple rows
and make the cursor iterable, and `description` is populated for `PRAGMA` statements. **No code change
was required for AC6** — this is the verified answer the AC asked for rather than an assumption.
`SELECT name FROM pragma_table_info(...)` remains the fallback should a future driver version stop
populating `description`.

## Validation Results

| Check | Result |
|-------|--------|
| `import app.db.database` | ✅ |
| `from app.main import app` | ✅ |
| `tests/test_db.py` | ✅ 64 passed (58 before, 6 new) |
| New tests, 10 consecutive runs | ✅ no flakes |
| Negative control (tests vs. pre-fix code) | ✅ 3 of 6 fail without the change |
| Full suite, per module | ✅ all modules pass except 3 that fail identically at baseline |
| Full suite, single `pytest -q` process | ❌ pre-existing breakage, unchanged by this story — see Deviation 2 |
| E2E, 8 real processes × 6 rounds | ✅ 8/8 exit 0 every round (pre-fix: 5–6 of 8 exit 1) |
| `sqlite3` code-level hits in `app/`, `chat_ui/`, `scripts/` | ✅ zero (5 docstring-prose mentions, the STORY-006 Deviation 4 set) |
| `reflex run` ingress | ⚠️ not run — no Node/Bun toolchain available; see Deviation 3 |

### The negative control, and what it exposed

Running the six new tests against the stashed pre-STORY-007 `_add_missing_columns()`:

| Test | Pre-fix | Why |
|---|---|---|
| `..._treats_an_existing_column_as_success` | **FAILS** | the loser's exact condition |
| `..._interleaved_between_read_and_alter_both_succeed` | **FAILS** | the forced race |
| `..._on_a_partially_migrated_database_converges` | **FAILS** | real migration work to race over |
| `..._propagates_a_failure_that_is_not_a_duplicate_column` | passes | by design — it guards against *over*-broad catching, so it must hold on both sides |
| `..._propagates_a_duplicate_naming_a_different_column` | passes | same |
| `..._on_an_empty_database_converges` | **passes** | see below |

The last row is worth stating plainly rather than burying: on an *empty* database
`CREATE TABLE IF NOT EXISTS` builds the current schema outright, so no `ALTER` is ever issued and
there is no race to lose. AC1's scenario therefore does not, on its own, exercise the bug. That is
measured, not assumed, and it is now written into the test's own docstring — which is exactly the
kind of test AC7 says is not evidence. The deterministic proof lives in the two tests that do fail.

### E2E: eight real processes

The one check that exercises the actual topology — separate processes, separate clients, one
database — repeated over six rounds against a freshly seeded pre-PII schema:

```
########## WITH the STORY-007 fix, 8 processes ##########
round 1..6: CONVERGED   exit codes: 0 0 0 0 0 0 0 0

########## WITHOUT it (pre-fix code), 8 processes ##########
round 1: exit codes: 1 1 1 1 1 0 0 1
round 2: exit codes: 1 0 0 0 1 1 1 1
round 3: exit codes: 0 0 0 1 1 1 1 0
round 4: exit codes: 0 0 1 0 1 1 1 1
round 5: exit codes: 1 1 1 0 1 1 1 0
round 6: exit codes: 1 0 1 0 1 1 1 1
```

Note what does **not** differ: the resulting schema converged in both columns of that comparison —
some process wins each `ALTER` either way. What the change fixes is that no instance dies doing it.
That is precisely AC1's wording — *every call returns successfully; no caller crashes because another
won the race* — and it is why "the schema ended up correct" would have been the wrong thing to assert.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/database.py` | UPDATE | +57 / -2 |
| `tests/test_db.py` | UPDATE | +313 / -0 |
| `.agents/reports/PRD-007-turso-migration/STORY-007-concurrent-safe-init-db.report.md` | CREATE | this file |

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db.py` | `test_add_missing_columns_treats_an_existing_column_as_success` (deterministic forced loser) |
| | `test_two_init_db_calls_interleaved_between_read_and_alter_both_succeed` (deterministic forced race) |
| | `test_add_missing_columns_propagates_a_failure_that_is_not_a_duplicate_column` |
| | `test_add_missing_columns_propagates_a_duplicate_naming_a_different_column` |
| | `test_concurrent_init_db_on_an_empty_database_converges` |
| | `test_concurrent_init_db_on_a_partially_migrated_database_converges` |

No existing test was modified, removed or renamed. The four `init_db()` tests the plan named as the
regression set — `test_init_db_issues_no_alter_when_schema_is_current`,
`test_init_db_migration_is_idempotent_across_repeated_calls`, `test_init_db_migrates_pre_pii_database`,
`test_init_db_migrates_pre_rbac_database` — pass unmodified.

## Deviations from Plan

**1 — The whole story was validated inside a container, not on the host.** The host runs Python
3.14; `libsql==0.1.11` publishes no wheel for it and its source build fails (`maturin`/`cargo` exit
101). Nothing in this repo can import `app.db` on this machine. Tests, probe and E2E therefore ran in
a `python:3.11-slim` image (the version the project's own `Dockerfile` targets) on a Docker network
with the libSQL dev server. This is an environment deviation, not a design one, but it is the reason
every command in this report is a `docker run`. **A contributor on this machine cannot run the suite
without it** — worth a line in the README when STORY-015 rewrites it.

**2 — `pytest -q` as a single process does not pass, and did not before this story either.** It ends
`1 failed, 335 passed, 726 errors` on a clean tree and `1 failed, 335 passed, 732 errors` with this
story's changes. The cause is one pre-existing defect, not many:

```
tests/conftest.py::_never_the_configured_database -> _reset_database()
ValueError: Hrana: `api error: `status=400 Bad Request,
    body={"message":"The stream has expired due to inactivity","code":"STREAM_EXPIRED"}``
```

The process-wide shared client's Hrana stream expires after inactivity, and `_shared_client()` caches
it forever with no liveness check — so once a slow module runs (the PII suites take ~40s), every
later test's autouse reset fails. The +6 error delta is exactly this story's six new tests hitting the
same dead client; the passing count is identical at 335 either way.

This is a STORY-006-era gap and, more seriously, **it is not only a test problem**: an idle production
instance holds the same cached client, so the same expiry would surface on the next request. It is out
of this story's scope and I did not touch it, but it should be scheduled — it sits squarely in
PRD-007's Risk 5 (resilience) territory and it currently makes the suite unable to report green in one
process. Substituted validation: every test module run in its own pytest process (table above), which
passes for all but the three below.

**3 — The `reflex run` ingress check was not performed.** It needs a Node/Bun toolchain that the test
image does not carry and the repo's own `Dockerfile` builds in a discarded stage. What stands in for
it: `tests/test_chat_ui_startup_guard.py` passes (2 tests), and the E2E repeated-boot check runs
`init_db()` twice in one process and again in a fresh one, which is the hot-reload behavior that
ingress check exists to catch. The claim is weaker than the plan asked for and is flagged rather than
counted as passed.

**4 — Three test modules fail, all pre-existing and unrelated.** `test_chat_state.py`
(1 failed, 37 errors), `test_pii_badge.py` (1 error), `test_success_metadata_footer.py` (1 error) —
byte-identical results with this story's changes stashed. They are chat-UI and PII-fixture modules
that touch nothing in `app/db/`.

**5 — PRD-006's byte-pin on `tests/test_db.py` was already stale before this story.**
`test_untouched_app.py::test_the_pinned_suites_are_byte_unmodified` pins six suites against PRD-006's
baseline `d3e6279`. Four of them — `test_audit_router.py`, `test_chat_state.py`, `test_db.py`,
`test_stats_router.py` — already differ **at `HEAD`**, because STORY-003 and STORY-006 legitimately
rewrote them for the driver swap. The set of violating files is identical before and after this
story, so this change introduces no new breach, but the guard is now decoration on this branch and
either its baseline or its suite list should be re-pointed by PRD-007 before the epic merges.

**6 — Task 6 became two test functions** rather than one with two cases, so a failure names which
half broke. Task 4 also gained a `users`-table assertion the plan did not specify: it proves the
statements *after* the swallowed failures still landed, which is the half of convergence that a
"did not raise" assertion cannot see.

**7 — One E2E result in this session was a false alarm, corrected.** The first four-process run
reported a half-migrated schema. The fault was the harness, not the code: `jobs -p` inside a
non-interactive `sh` lists nothing, so `wait` never ran and verification raced processes that were
still working. With a correct `wait` the same scenario converged 10/10 at four processes and 6/6 at
eight. Recorded because the intermediate result was alarming and someone re-reading this work should
know it was investigated rather than retried until green.

## Acceptance Criteria

- [x] **AC1** — N concurrent `init_db()` calls on an empty database all return, schema correct and
      complete. `test_concurrent_init_db_on_an_empty_database_converges` (8 threads), plus the
      8-process E2E. Recorded honestly: the empty-database case does not itself exercise the race.
- [x] **AC2** — N concurrent calls against a table missing a subset of `AUDIT_LOGS_ADDED_COLUMNS`
      leave all five present exactly once, every call returning.
      `test_concurrent_init_db_on_a_partially_migrated_database_converges` and the two-thread
      interleave; the E2E rounds are the multi-process form.
- [x] **AC3** — "column already exists" is treated as success; anything else propagates.
      `_is_duplicate_column()` matches the message *and* the column name; both propagation tests pass,
      including a duplicate naming a different column.
- [x] **AC4** — a current schema is a no-op: no `ALTER`, no error.
      `test_init_db_issues_no_alter_when_schema_is_current` passes **unmodified**; the pre-check was
      deliberately kept for exactly this.
- [x] **AC5** — the five added columns match `AUDIT_LOGS_ADDED_COLUMNS`, `NOT NULL` entries carrying a
      non-NULL `DEFAULT`. `test_added_columns_declaring_not_null_also_declare_a_default` unmodified;
      the concurrency tests additionally assert the pre-existing row took the declared default
      (`pii_detected_input is False`) after a contended migration.
- [x] **AC6** — `PRAGMA table_info` column names extract correctly against libSQL. Verified against
      the live endpoint (output above); no shape difference reaches `_add_missing_columns()`, no code
      change needed, recorded here as the AC requires.
- [x] **AC7** — the concurrency tests are deterministic. Four of the six reproduce the condition
      directly and do not depend on an interleave occurring; two of those four fail against the
      pre-fix code. The two N-thread tests are labelled in their own docstrings as realism rather than
      evidence, and the empty-database one carries the measured reason it cannot be evidence.
