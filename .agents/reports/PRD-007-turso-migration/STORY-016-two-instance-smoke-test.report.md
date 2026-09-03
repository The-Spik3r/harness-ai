---
story: STORY-016
prd: PRD-007
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-016-two-instance-smoke-test.plan.md
epic_branch: epic/PRD-007-turso-migration
commit: 153d2f3
status: COMPLETE
completed: 2026-09-02
---

# Implementation Report — STORY-016: Prove two instances share one database

**Plan**: `.agents/plans/PRD-007-turso-migration/completed/STORY-016-two-instance-smoke-test.plan.md`
**Epic Branch**: `epic/PRD-007-turso-migration`
**Commit**: `153d2f3`

## Summary

`tests/test_two_instance_smoke.py` (822 lines, 7 tests) starts **two real application
processes** against the one libSQL endpoint `tests/conftest.py` provisions and drives them
from the parent through a line-delimited JSON command protocol on stdin/stdout. Both
children are constructed before either's ready line is read, so they race `init_db()`
against one database with nothing serializing them; they then stay booted for the whole
module, which is what makes "instance B blocks a duplicate instance A wrote" evidence of
shared state rather than of persistence.

Every acceptance criterion passes. The migration's stated goal — scaling past one
container — is now demonstrated rather than assumed. Two things the story asked for came
back different from what the PRD predicted, and both are recorded below rather than
smoothed over: **`POST /query` costs three round trips, not two**, and **`STREAM_EXPIRED`
did not reproduce** under the conditions this module creates.

No production file was changed. The plan said a need to change one would be a finding
first; none arose.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Module prologue and the worker script | `tests/test_two_instance_smoke.py` | ✅ |
| 2 | `Instance` harness and the simultaneous-start fixture | `tests/test_two_instance_smoke.py` | ✅ |
| 3 | `fresh_schema` fixture and AC 1 — both boot, schema correct | `tests/test_two_instance_smoke.py` | ✅ |
| 4 | AC 2 — cross-instance duplicate detection, inside and outside the window | `tests/test_two_instance_smoke.py` | ✅ |
| 5 | AC 3 + AC 6 — concurrent writes, no loss, unique ids, no corruption | `tests/test_two_instance_smoke.py` | ✅ |
| 6 | AC 4 — a CLI-created user authenticates against both instances | `tests/test_two_instance_smoke.py` | ✅ |
| 7 | AC 5 — a CLI-deactivated user is rejected by both instances | `tests/test_two_instance_smoke.py` | ✅ |
| 8 | AC 8 — the measured numbers | `tests/test_two_instance_smoke.py` | ✅ |
| 9 | Determinism pass | `tests/test_two_instance_smoke.py` | ✅ |
| 10 | Full-suite regression | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Module parses; embedded worker script parses | ✅ |
| Collection | ✅ 7 tests |
| This module | ✅ 7 passed in 5.5–5.8 s |
| Determinism — 3 consecutive runs | ✅ identical results, stable figures |
| Mutation check (assertions are not vacuous) | ✅ caught, legibly |
| Full suite | ✅ **1120 passed, 20 skipped, 0 failed** (baseline 1113 + these 7) |
| E2E | ✅ 9/9 |
| Production files changed | ✅ none |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_two_instance_smoke.py` | CREATE | +822 |
| `.agents/stories/PRD-007-turso-migration/STORY-016-two-instance-smoke-test.md` | UPDATE | +3/−3 |
| `.agents/PRDs/PRD-007-turso-migration/index.md` | UPDATE | +2/−2 |

## Findings

### 1. 🔴 `POST /query` costs **three** round trips, not the two PRD Section 5 story 6 predicts

This is what AC 8 exists to catch, and it caught something. Measured at the endpoint:

```
POST /query : 3 statements
  1. SELECT * FROM users WHERE token_hash = ? AND active = 1
  2. SELECT timestamp FROM audit_logs WHERE prompt_hash = ? AND timestamp >= ? ...
  3. INSERT INTO audit_logs (...) VALUES (...)
```

PRD Section 5 story 6 says: *"`run_query(...)` adds one duplicate-check read and one audit
write per request — two round trips."* That sentence is **accurate about `run_query()` and
wrong about a request.** It counts from the pipeline's edge, and by the time `run_query()`
is reached, `app/middleware/auth.py`'s `require_permission` → `require_identity` →
`resolve()` has already spent a round trip in `find_user_by_token_hash()`
(`app/services/identity.py:58`) on the same shared client.

**The third statement is not a defect and must not be removed.** It is the same read that
AC 4 and AC 5 prove is *uncached* — which is precisely what makes a CLI revocation take
effect on both running instances at once. Caching it would buy one round trip per request
and cost the revocation guarantee, which PRD-005 Section 9 and this story's own AC 5 both
treat as a security property. The right response is to correct the PRD's arithmetic, not
the code.

The test pins the three **by name and order** rather than by count, so both a fourth
statement and the identity read quietly disappearing into a cache fail loudly.

Bounded impact: three round trips still sit inside a request dominated by the OpenRouter
call, so PRD Section 5 story 6's *conclusion* (imperceptible to the end user) survives its
arithmetic being off by one.

### 2. `STREAM_EXPIRED` did not reproduce — and this module is where it would have

The index carries an open finding that the shared libSQL client's Hrana stream expires
after an idle window, that this "breaks the running application" (a `POST /query`
returning 500 from `find_user_by_token_hash` that did not recover), and that it should be
scheduled *before* this story. It was treated as a design input rather than a blocker, and
it did not fire: two children held clients open across the whole module, through seven
tests and three consecutive full-module runs, plus a whole-suite run, with no
`STREAM_EXPIRED` and no unexplained 500.

This is **not** evidence the finding is invalid. STORY-015 observed it after an idle period
measured in minutes on a spaCy-model-loading boot; this module's instances are pinged by
`fresh_schema`'s `init_db` at the start of every test and never idle for more than a few
seconds. So the honest reading is: **this module does not exercise the idle window**, and
the finding still needs its own story, which should measure the window explicitly rather
than infer it. What this run does establish is that the two-instance claim holds for
actively-used clients.

### 3. The concurrency is real, demonstrated by mutation

To confirm the concurrency assertions are not vacuous, both instances were temporarily
given the *same* twenty prompts. The test failed, legibly, naming the instance and the
index — and the shape of the failure is itself evidence: instance B's query **0** succeeded
while its queries **1–4** came back `BLOCKED`. Query 0 raced — both instances passed their
duplicate check before either's row landed — and everything after it lost the race and was
correctly blocked. That is genuine cross-process concurrency, not interleaved bookkeeping,
and it is the same window PRD-007 accepts by design (the duplicate check is a read
followed by a write, not an atomic operation).

The mutation was reverted; the file on disk is the unmutated one, re-verified green.

### 4. The container ships a baked-in copy of the code

`docker-compose run ... harness-ai pytest tests/` runs the **image's** copy of the repo
(`Dockerfile:66`, `COPY . .`), not the working tree, so the README's documented command
cannot see an uncommitted test file. Every run in this story therefore added
`-v "<repo>:/app"`. This is a developer-workflow gap rather than a defect in anything this
epic built — the documented command is correct for verifying a *built* image — but anyone
iterating on tests in a container needs the mount, and nothing currently says so. Noted for
whoever next touches `README.md`'s Running Tests section; not fixed here, because
STORY-015 owns that section and this story owns no documentation AC.

On this host the mount also needs `MSYS_NO_PATHCONV=1` and a Windows-style path, since
Git Bash rewrites `/app` into a Windows path before Docker sees it.

## Measured Round-Trip Cost (AC 8)

Closing PRD Section 12 Phase 3's "Measured round-trip counts" deliverable with real
numbers. Local libSQL dev server, same host — which **understates** the gain against a
remote endpoint, the same caveat STORY-011 recorded for its figures.

| Operation | Statements | Wall clock |
|---|---|---|
| `POST /query` (warm process, warm client) | **3** — identity read, duplicate check, audit write | 26.4 / 27.1 / 27.8 / 29.5 ms across four runs |
| Admin console load (`summary_snapshot(row_limit=100, ranked_limit=5)`) | **1** | 3.6 / 3.8 / 4.0 / 4.3 ms |

Two things the numbers do **not** say. The `POST /query` wall clock is the whole request,
including two real `redact()` calls through Presidio — it is not three round trips' worth
of network. And no latency is asserted as a pass/fail bound anywhere in the module; only
the statement counts are, because a threshold would make the epic's exit criterion flaky
on a loaded machine.

The console figure is consistent with the 2.7 ms STORY-010 recorded for the same single
statement, and the contrast it was measured against still stands: ten sequential reads
before STORY-010, one now.

Standing caveat, unchanged and deliberately not acted on: `audit_logs` has no index on
`prompt_hash` or `timestamp`, so the duplicate check scans. At the row counts here that is
invisible. PRD Section 4 puts new indexes out of scope and PRD Section 13 flags this as
worth measuring against real data volume — still the right disposition, and still nobody's
story.

## Deviations from Plan

| Deviation | Why |
|---|---|
| The `POST /query` assertion is **3 statements pinned by name**, not the planned `== 2` | Finding 1. The plan predicted two and said an unexpected count "fails the test with the recorded SQL attached, because 'we issue two round trips per query' is a claim the PRD makes and this is where it is checked". It was checked and the PRD is off by one. Pinning by name is strictly stronger than the count the plan asked for. |
| Added an `audit_ids` command to the protocol (8 commands, not the 7 tabulated) | AC 6 asks for `audit_logs.id` uniqueness, and `list_audit_logs()` returns `AuditLog` objects, which carry no id. Reading ids needed its own statement. |
| Every validation run added `-v "<repo>:/app"` to the documented command | Finding 4 — the image ships its own copy of the code. |
| The spaCy fallback (patching `redact` in the child) was **not** needed | The plan held it in reserve if two model loads proved intolerable. They cost ~25 ms per query in this image, so PII redaction stays real, as `tests/test_integration.py` has it. |

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_two_instance_smoke.py` | `test_both_instances_boot_simultaneously_against_one_database` (AC 1) · `test_a_prompt_answered_by_instance_a_is_blocked_by_instance_b` (AC 2) · `test_a_prompt_outside_the_window_is_not_blocked_by_the_other_instance` (AC 2 control) · `test_concurrent_queries_from_both_instances_lose_no_rows` (AC 3, AC 6) · `test_a_user_created_by_the_cli_resolves_on_both_running_instances` (AC 4) · `test_a_deactivated_user_is_rejected_by_both_running_instances` (AC 5) · `test_round_trip_cost_is_measured_and_reported` (AC 8) |

## Acceptance Criteria

- [x] **Two instances start simultaneously; both boot and the schema is correct.** Both children are constructed before either ready line is read, so they race `init_db()` unserialized. Each reports its post-`init_db()` schema *at boot* — necessary, because conftest's autouse reset drops every table before every test — and the two records are asserted complete, containing all five `AUDIT_LOGS_ADDED_COLUMNS` (imported, not spelled out) **and equal to each other**. Two instances that each boot fine but converge on different schemas is the failure this guards.
- [x] **A prompt answered by A is blocked by B inside the window.** B has never seen the prompt and never restarted; its `first_query_at` is asserted equal to the timestamp of the row A wrote, so the block is traced to A's row rather than merely observed.
- [x] **Concurrent traffic produces exactly one row per query, none lost, none duplicated.** Twenty queries, ten per instance, all written to both children before any reply is read. Twenty rows, twenty distinct prompt hashes, and the prompt set read back from **B** equal to the set sent.
- [x] **A CLI-created user authenticates against either instance.** Created while both were running; both accept the token without a restart.
- [x] **A CLI-deactivated user is rejected by both.** Asserted to work on both *before* revocation and to return 401 on both after, each instance named in its own failure message.
- [x] **`audit_logs.id` values are unique and no row is corrupted.** Twenty unique ids, and every row's `user_id`, `model_used`, `tokens_used`, `success` and `was_duplicate_blocked` compared against what was submitted — plus `prompt_hash == hash_prompt(prompt_preview)`, which catches a row whose fields were shifted or crossed between concurrent writers.
- [x] **Deterministic in CI, no hosted Turso.** Three consecutive runs, identical results. No `time.sleep`, no polling, no asserted latency, no dependence on which instance wins a race; the endpoint comes only from conftest's `database_url_factory`, so `HARNESS_TEST_LIBSQL_URL` redirects it with the rest of the suite. The constraints are recorded in the module as `_INVARIANTS`.
- [x] **The report states the measured round-trip cost of a `POST /query` and an admin console load.** Above, with the count that contradicts the PRD called out rather than rounded to fit.

## Security Note

The story asked for identity-resolution caching to be raised immediately as a security
finding if found. **None exists.** `resolve()` reads `users` on every request, which is why
`POST /query` costs three round trips (Finding 1) and why revocation lands on both
instances at once. The cost and the guarantee are the same fact.

Every child process is launched with `DATABASE_URL` pinned and **`TURSO_AUTH_TOKEN`
blanked**, in code rather than by convention. A child builds its own `Settings()` where
`monkeypatch` cannot reach — the exact mechanism behind STORY-014's Finding 1 and
STORY-015's Finding 1, both of which were an inherited environment variable reaching a real
database. This module spawns more subprocesses than the rest of the suite combined, so it
enforces the hygiene rather than trusting the invocation.
