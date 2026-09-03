---
story: STORY-010
prd: PRD-007
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-010-batched-summary-read.plan.md
epic_branch: epic/PRD-007-turso-migration
commit: b592264
status: COMPLETE
completed: 2026-09-01
---

# Implementation Report — STORY-010: One batched database read returning all ten summary figures in a single round trip

**Plan**: `.agents/plans/PRD-007-turso-migration/completed/STORY-010-batched-summary-read.plan.md`
**Epic Branch**: `epic/PRD-007-turso-migration`
**Commit**: `b592264`

## Summary

`summary_snapshot(row_limit=100, ranked_limit=5)` in `app/db/database.py` returns all ten admin summary figures from **one** statement, replacing the ten-round-trip fan-out two callers perform today. It is not a client batch, because the driver has none: STORY-001 §2.6 established that `libsql` exposes no `batch()`, that `executescript()` returns `None`, and that multi-statement `execute()` returns only statement 1 *while reporting success for a batch containing a bad statement*. Per-statement results and per-statement errors are both unavailable, so PRD Risk 6 could not be answered with a batch API at all. The story anticipated this — "the workaround recorded there governs this story" — and §3.4's workaround is what shipped: one `SELECT` of scalar subqueries, where each figure is a **named column** and `cursor.description` carries the attribution that statements could not.

The ten standalone functions are untouched and are now load-bearing twice over: they are the public surface STORY-006 promised, and they are what the failure path is built out of.

## Round-trip measurement

The evidence PRD Section 12 Phase 3 asks for ("Measured round-trip counts for an admin console load"), counted rather than asserted in prose. `tests/test_db.py::test_summary_snapshot_issues_one_round_trip` wraps the connection in a recording proxy and counts statements reaching the database:

| Path | Statements | Wall clock (60-row table, best of 5) |
|---|---|---|
| `summary_snapshot()` | **1** | 2.7 ms |
| The same ten figures read individually | **10** | 21.2 ms |

Roughly 7.8×, consistent with STORY-001 §3.4's 1.7 ms against 16.3 ms on a smaller table. The count is the assertion; the timing is context.

One clarification the number needs: `_session()` also issues a `commit()` on block exit, and every existing read has always carried that same trailer. So this is one statement where there were ten, with the commit unchanged rather than newly introduced. Dropping the commit for read-only sessions is a real further improvement and was deliberately left alone — it lives in `_session()`, which all 22 functions share.

## Risk 6: what per-figure attribution actually required

A single statement is all-or-nothing, which is the exact shape Risk 6 warns about ("ten legible partial failures into one blank page"). Attribution is therefore preserved in two layers:

1. **Decode layer** — the statement succeeded and each column is decoded by its own entry in `_SUMMARY_DECODERS`, inside its own `try/except`. One malformed column is one failed figure; the other nine still arrive.
2. **Statement layer** — the statement itself failed, so there are no columns to attribute anything to. `summary_snapshot()` falls back to the ten standalone reads, each individually guarded, and returns the partition they produce. It costs up to ten round trips **only when the batch is already broken**; the success path stays at one.

The result is `SummarySnapshot`, whose `figures` and `errors` dicts partition `SUMMARY_FIGURES` exactly — enforced in `__post_init__`, because a figure silently in neither is the blank page arriving by another route. The names are `_READS`' field names, so STORY-012's ten `READ_LABEL_*` entries map one-to-one and `len(_READS) == 10` needs no change.

## Answer owed to STORY-012: does `_READS`' ordering still carry weight?

The story asked this explicitly. **Half of it no longer does, and STORY-012 should rewrite the comment rather than carry it forward.**

The current comment reads:

> "Order is the read order and is deliberate: the rows come first so the slowest query fails fast, and `total_recorded` follows them because it is the denominator the register states its 100-row cap against."

- **"The rows come first so the slowest query fails fast" is now false.** It described ten sequential statements aborting at the first failure. In one statement there is no first — the database plans all ten subqueries together — and the fallback deliberately runs the full ten precisely so that nothing fails fast and every figure gets attributed. Fail-fast was traded for attribution, knowingly.
- **"`total_recorded` follows them because it is the denominator the register states its 100-row cap against" survives**, but only as documentation of a relationship between two figures, not as a claim about read order. It is still true and still worth saying.

`SUMMARY_FIGURES` preserves `_READS`' order anyway — not because execution depends on it, but so the two tables stay diff-able against each other.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Confirm the libSQL dev endpoint is up | — | ✅ |
| 2 | `SUMMARY_FIGURES` + `SummarySnapshot` (partition invariant, ten properties) | `app/db/database.py` | ✅ |
| 3 | `_SUMMARY_SQL` — one SELECT, ten named columns, STORY-009's CTE hoisted | `app/db/database.py` | ✅ |
| 4 | Per-figure decoders; `_row_to_audit_log` annotation widened to `Mapping` | `app/db/database.py` | ✅ |
| 5 | `summary_snapshot(row_limit, ranked_limit)` | `app/db/database.py` | ✅ |
| 6 | `_summary_figure_by_figure()` attribution fallback | `app/db/database.py` | ✅ |
| 7 | Tests — agreement with the individual reads, types, empty database | `tests/test_db.py` | ✅ |
| 8 | Tests — per-figure failure isolation (decode, fallback, whole outage) | `tests/test_db.py` | ✅ |
| 9 | Tests — round-trip count, limits as parameters | `tests/test_db.py` | ✅ |
| 10 | Tests — the ten standalone signatures, `count_audit_logs(user_id=...)` scoping | `tests/test_db.py` | ✅ |
| 11 | Full validation + untouched-callers proof | — | ✅ |
| 12 | This report | `.agents/reports/…` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `tests/test_db.py` | ✅ 97 passed (87 baseline + 10 new) |
| `tests/test_stats_router.py`, `test_admin_state.py`, `test_summary.py` | ✅ 171 passed, assertions unchanged |
| `tests/test_admin_shell.py` | ✅ 95 passed |
| Backend import (`from app.main import app`) | ✅ |
| Batched statement by hand (ten columns, correct names/order) | ✅ |
| Round-trip count 1 vs 10 | ✅ |
| No `app/routers/` or `chat_ui/` file modified by this story | ✅ |

The ten-read invariant (`len(reads) == 10`) is asserted at `tests/test_admin_state.py:490-492`, not in `test_admin_shell.py` as PRD Section 6 Pattern 3 and Risk 6 state; it passed unchanged either way. Worth correcting in the PRD if anyone leans on that reference.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/database.py` | UPDATE | +329/-2 |
| `tests/test_db.py` | UPDATE | +304 |

## Deviations from Plan

| Deviation | Why |
|---|---|
| The new code sits after `top_pii_entities()` rather than after `count_pii_detected_queries()` as the plan said | Keeps all ten standalone reads contiguous and ahead of the batch that is built from them. Cosmetic. |
| `"rows"` is quoted in the SQL | `ROWS` is a keyword (window frames); an unquoted alias is a syntax error. Not foreseen in the plan. |
| The signature test pins return annotations too, not just parameters | The first run failed because the plan's expected strings omitted them — and the return types are exactly the `int` / `list[str]` / `list[AuditLog]` AC 2 names, so pinning them is the stronger test. Fixed by widening the assertion, not by loosening it. |
| Tests run in a `harness-test:py311` container | `libsql==0.1.11` publishes no wheel for this host's Python 3.14 (STORY-001 §5). Same container earlier stories used; the dev server was attached to `harness-net` to reach it. |
| Risk 1 (`json_group_array` ordering) did not fire | Verified against the live endpoint before writing the tests: order is preserved through the ordered, limited subquery, including a deliberate tie on `timestamp`. The `ROW_NUMBER()` contingency was not needed. |

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db.py` | `test_summary_snapshot_agrees_with_the_individual_reads`, `test_summary_snapshot_types_match_the_standalone_functions`, `test_summary_snapshot_on_an_empty_database`, `test_summary_snapshot_isolation_of_one_bad_decode`, `test_summary_snapshot_isolation_names_the_one_broken_figure`, `test_summary_snapshot_reports_every_figure_when_the_table_is_gone`, `test_summary_snapshot_issues_one_round_trip`, `test_summary_snapshot_limits_are_parameters`, `test_summary_snapshot_leaves_the_ten_standalone_signatures_unchanged`, `test_count_audit_logs_still_scopes_by_user` |

## Acceptance Criteria

- [x] Returns all ten figures in **one** round trip — proved by statement count (1 vs 10), not prose
- [x] Each figure individually addressable by name, with the standalone function's type (`int`, `list[str]`, `list[AuditLog]`) — including `bool` fields surviving the JSON hop
- [x] A failure names **which** figure broke while the others are still delivered — both layers tested
- [x] The ten standalone functions still exist with unchanged signatures; `count_audit_logs(user_id=...)` still scopes for `GET /audit`
- [x] Batched and individual results identical, figure for figure
- [x] `row_limit` and `ranked_limit` are parameters, tested with different values so a swapped binding cannot pass
- [x] `tests/test_db.py` covers agreement, per-figure failure isolation, an empty database, and the round-trip count
- [x] No file under `app/routers/` or `chat_ui/` modified by this story

**One note on the last AC's literal wording.** It says to inspect `git diff main --stat`. That diff *does* show `chat_ui/chat_ui/admin_state.py`, because the epic branch accumulates every earlier story — that change is STORY-006's (`86ece73`), not this one's. This story's own diff (`git diff HEAD --stat`) is exactly `app/db/database.py` and `tests/test_db.py`. The AC's intent — this story builds the capability, STORY-011 and STORY-012 adopt it — holds; the check should be against the story's own diff on an epic branch, not against `main`.
