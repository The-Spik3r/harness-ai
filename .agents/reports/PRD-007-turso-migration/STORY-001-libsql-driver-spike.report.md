---
story: STORY-001
prd: PRD-007
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-001-libsql-driver-spike.plan.md
epic_branch: epic/PRD-007-turso-migration
commit: 6e6b1c4
status: COMPLETE
completed: 2026-09-01
---

# Implementation Report — STORY-001: Spike: verify the six risky libSQL client behaviors and record the driver decision

**Plan**: `.agents/plans/PRD-007-turso-migration/completed/STORY-001-libsql-driver-spike.plan.md`
**Epic Branch**: `epic/PRD-007-turso-migration`
**Commit**: `6e6b1c4`
**Decision record**: [`STORY-001-driver-decision.md`](./STORY-001-driver-decision.md) — the story's actual deliverable

## Summary

Stood up `ghcr.io/tursodatabase/libsql-server` locally, installed `libsql==0.1.11` under CPython 3.11.16, and answered all six behaviors PRD Section 8 flags as risky, using `app/db/models.py`'s DDL and `app/db/database.py`'s SQL verbatim. Every answer is a pasted observation reproduced twice, the second time against a freshly recreated empty server. The decision is **`libsql==0.1.11`**: three behaviors pass outright, commit semantics pass in the form the module already uses, and the two failures (named-column access, batch) have workarounds that were *run against the endpoint*, not merely proposed. No production code was written; `git diff main --stat` is empty for every tracked path.

The headline result reverses the plan's worst-case assumption about PRD Risk 1: **`with conn:` does commit**, so the module's 22 existing `with get_connection() as conn:` blocks are durable as written. The real danger is narrower and was located precisely — a bare `execute` and `close()` both discard the write silently.

## Tasks Completed

| # | Task | File / Target | Status |
|---|------|------|--------|
| 0 | Create epic branch from `main` | — (git) | ✅ |
| 1 | Start local libSQL dev server, capture digest | — (docker) | ✅ |
| 2 | Pin `libsql==0.1.11` under Python 3.11, record wheel coverage | — (container) | ✅ |
| 3 | Write the spike harness | *scratchpad* `spike_libsql.py` | ✅ (not committed) |
| 4 | Behavior 1 — named-column row access | harness | ✅ **NO** |
| 5 | Behavior 2 — commit semantics via fresh client | harness | ✅ **QUALIFIED YES** |
| 6 | Behavior 3 — `lastrowid` | harness | ✅ **YES** |
| 7 | Behavior 4 — `rowcount` | harness | ✅ **YES** |
| 8 | Behavior 5 — `PRAGMA table_info` | harness | ✅ **YES, with caveat** |
| 9 | Behavior 6 — batch / multi-statement | harness | ✅ **NO** |
| 10 | Candidate comparison and decision | — (analysis) | ✅ |
| 11 | Write the decision record | `.agents/reports/PRD-007-turso-migration/STORY-001-driver-decision.md` | ✅ |
| 12 | Prove no production code moved | — (verification) | ✅ |

## The six answers

| # | Behavior | Answer | One-line evidence |
|---|---|---|---|
| 1 | Named-column row access | **NO** | rows are `tuple`; no `row_factory`; but `description` is populated → mapping wrapper viable |
| 2 | Commit without explicit `commit()` | **QUALIFIED YES** | `with conn:` DURABLE; bare execute LOST; `close()` LOST |
| 3 | `lastrowid` | **YES** | `1, 2, 3`, confirmed by fresh-client `SELECT id` |
| 4 | `rowcount` | **YES** | `1` on hit, `0` on miss, never `-1` |
| 5 | `PRAGMA table_info` | **YES, caveat** | supported; **`Cursor` is not iterable** — `database.py:45` must use `.fetchall()` |
| 6 | Batch / multi-statement | **NO** | no `batch()`; `executescript()` → `None`; multi-statement `execute()` returns statement 1 and **swallows errors** |

## Validation Results

| Check | Result |
|-------|--------|
| Local libSQL server reachable | ✅ `/health`, `/v2`, `/version` all HTTP 200 |
| `libsql==0.1.11` installs as a **wheel** on 3.11 | ✅ `libsql-0.1.11-cp311-cp311-manylinux_2_17_x86_64…whl` |
| Harness imports `app.db.models` unmodified | ✅ 5 added columns resolved |
| All six behaviors answered with pasted evidence | ✅ 6/6 |
| Results reproduced on a freshly recreated server | ✅ identical |
| Commit sequence reproduced (separate processes) | ✅ identical |
| `git diff main --stat -- app/ chat_ui/ scripts/ tests/ requirements.txt` | ✅ **empty** |
| `git diff main --stat` (all tracked paths) | ✅ **empty** |
| Spike script absent from repo | ✅ scratchpad only |
| Full test suite | ⚠️ 1017 passed, 7 failed — **pre-existing on `main`**, see Deviations |

## Files Changed

| File | Action | Notes |
|------|--------|-------|
| `.agents/reports/PRD-007-turso-migration/STORY-001-driver-decision.md` | CREATE | The deliverable — decision, six answers, workarounds, dev-server workflow |
| `.agents/reports/PRD-007-turso-migration/STORY-001-libsql-driver-spike.report.md` | CREATE | This report |
| `.agents/plans/PRD-007-turso-migration/completed/STORY-001-libsql-driver-spike.plan.md` | CREATE (archived) | Plan, moved to `completed/` |
| `.agents/stories/PRD-007-turso-migration/*.md` | CREATE | 16 story files (first commit of the epic) |
| `.agents/PRDs/PRD-007-turso-migration/{PRD.md,index.md}` | CREATE | PRD + board (first commit of the epic) |
| **`app/`, `chat_ui/`, `scripts/`, `tests/`, `requirements.txt`** | **UNCHANGED** | Verified by `git diff main --stat` |

## Deviations from Plan

1. **Python 3.11 came from a container, not the host.** The plan's Task 2 allowed this explicitly as the documented fallback. The host has only Python 3.14.4, for which `libsql` publishes **no `win_amd64` wheel** — `pip` falls back to the sdist and needs a Rust toolchain. The whole spike ran inside `python:3.11` on a shared Docker network. This confirmed the plan's predicted constraint rather than contradicting it; §5 of the decision record carries it forward to CI and STORY-003.

2. **Docker Desktop's daemon was not running** and had to be started before Task 1. Not a plan deviation so much as an unlisted prerequisite; noted so the next runner expects it.

3. **Behavior 5 gained a caveat the plan did not anticipate.** The plan asked whether `PRAGMA` was supported (it is) and whether the result was directly iterable from `conn.execute(...)`. It is **not** — `'builtins.Cursor' object is not iterable` — which breaks `database.py:45` independently of the named-access problem. Both halves of that line must change.

4. **Behavior 6 found a failure mode worse than "unsupported".** Multi-statement `execute()` does not raise; it returns the first statement's result and silently discards a bad statement's error. Recorded prominently because a naive STORY-010 implementation could ship a summary read that reports success while returning wrong figures.

5. **Two extra findings collected while the endpoint was up**, both beyond the six but cheap and load-bearing for later stories:
   - **The exception surface is a bare `builtins.ValueError`** for every SQL error, with no hierarchy. `SQLITE_CONSTRAINT` cannot distinguish duplicate `user_id` from duplicate `token_hash`, and `SQLITE_UNKNOWN` covers both missing-table and duplicate-column. STORY-004's `app/db/errors.py` must parse message text, and the 401-not-500 behavior at `database.py:289` must match on `no such table`. (§3.5)
   - **`json_group_array` and recursive CTEs work on this endpoint**, so STORY-010 can collapse all ten summary figures — including the four list-valued ones — into a single round trip with per-figure column names, and STORY-009's `top_pii_entities` can aggregate server-side. Both verified running. (§3.4)

6. **No tests were written.** The `/implement` workflow requires tests for new code; this story produces no code, and AC 8 forbids modifying `tests/`. Characterization tests are STORY-002's scope by design (PRD Section 12, Phase 1).

7. **`turso-serverless` was not benchmarked.** The plan gated that on `libsql` failing a behavior with no acceptable workaround; the gate was never reached.

### Pre-existing conditions found (not caused by this story, not fixed)

- **The local `.env` breaks `Settings()`.** It carries three keys `app/config.py` does not declare — `tursoDBToken`, `databaseTursoDB`, `databaseURL` — and `pydantic-settings` rejects extras, so `from app.main import app` and *all* test collection fail on this machine. `.env` is gitignored and `app/config.py` is byte-identical to `main`, so this predates the story. Left alone: it is the user's local secrets file and outside this story's scope. (Note that `databaseURL` already holds a `libsql://…turso.io` endpoint — someone has begun provisioning; STORY-005 will formalize `DATABASE_URL` + `TURSO_AUTH_TOKEN`.)
- **7 test failures exist on `main`.** With those three keys removed, the suite runs: **1017 passed, 7 failed**. The identical 7 failures and identical counts were reproduced on a pristine `main` worktree. They are `test_untouched_app.py`'s provenance guards, which diff against PRD-006's pinned baseline `d3e6279` and no longer hold now that PRD-006 has merged into `main`, plus one `test_chat_state.py` assertion. Unrelated to this story; worth a follow-up on the epic.

## Tests Written

None — this story writes no production code, and AC 8 forbids touching `tests/`. Test work for Phase 1 is STORY-002 (characterization tests against current SQLite) and STORY-003 (the fixture centralization).

## Acceptance Criteria

- [x] Named-column row access answered — **NO** (tuples, no `row_factory`); `description`-based mapping proven viable; 22-call-site + two-mapper blast radius stated
- [x] Commit durability answered by reading back through a **separate, freshly constructed client in a separate process** — `with` block DURABLE, bare execute and `close()` LOST
- [x] `lastrowid` on `INTEGER PRIMARY KEY AUTOINCREMENT` answered — **YES**, cursor-level, confirmed against fresh-client reads
- [x] `rowcount` answered for one-row and zero-row `UPDATE`s as literal values — `1` and `0`, never `-1`
- [x] `PRAGMA table_info(audit_logs)` answered — **supported**; rows are tuples; cursor not iterable
- [x] Batch execution answered — no API, round-trip cost measured (16.3 ms → 1.7 ms), per-statement results and errors both unavailable
- [x] Decision record committed naming the client, **exact pinned version** `libsql==0.1.11`, and yes/no + evidence for all six including workarounds
- [x] `git diff main --stat` shows no file modified under `app/`, `chat_ui/`, or `scripts/`
- [x] Local libSQL dev-server workflow documented and reproducible — start (with digest), port, teardown
- [x] All tasks completed
- [x] No production code written; no dependency added to `requirements.txt`
