---
story: STORY-012
prd: PRD-007
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-012-admin-console-batched-reads.plan.md
epic_branch: epic/PRD-007-turso-migration
commit: PENDING
status: COMPLETE
completed: 2026-09-02
---

# Implementation Report — STORY-012: AdminState._READS consumes the batched read, preserving per-figure failure attribution

**Plan**: `.agents/plans/PRD-007-turso-migration/completed/STORY-012-admin-console-batched-reads.plan.md`
**Epic Branch**: `epic/PRD-007-turso-migration`
**Commit**: `PENDING`

## Summary

`AdminState.load()` now makes **one** `asyncio.to_thread` hop into `summary_snapshot(row_limit=REGISTER_ROW_LIMIT, ranked_limit=RANKED_LIMIT)` where it made ten. `_READS` did not change: same ten entries, same `(field, label, callable, kwargs)` shape, same order — only what supplies each field's value changed, which is the shape the story asked for. Per-figure attribution survives because STORY-010 keyed `SUMMARY_FIGURES` to `_READS`' own field names, so the fault arm walks the table and formats the same `READ_LABEL_*` sentence the sequential loop produced.

This was the only change permitted outside `app/db/`, and it is two files: `chat_ui/chat_ui/admin_state.py` and `tests/test_admin_state.py`. `app/db/` was not touched.

## The acceptance criteria that contradicted each other

The plan resolved this before any code was written, and the resolution is what shipped. AC 2 asks that a partial failure leave "the figures that succeeded still displayed"; AC 6 and AC 7 require that **no** figure is committed when any read fails, and two existing assertions say so literally:

- `tests/test_admin_state.py:698-702` — with `top_pii_entities` failing, `state.rows == []` even though the rows read fine.
- `tests/test_admin_state.py:674-679` — with `top_models` failing, `_loaded_record(state) == before`: not one of the seven successes is committed.

Committing partial results would fail both and would change the rendered console against `main`, which AC 7 forbids outright. So the transactional commit stayed and **attribution** is what was rescued — the reading the story's own Technical Notes point to ("The mechanism to preserve is the label"). Under it AC 2 and AC 6 agree: nothing is cleared, so what an admin was looking at is still on screen under the fault panel, and the panel names the figure that broke.

## What the fault arm does now

Three arms, where there was one:

1. **A figure in `snapshot.errors`** — walk `_READS` in order, name the first match. Order matters now in a way it did not before: one statement can report several broken figures at once, where ten sequential reads always stopped at the first. Walking the table rather than the errors dict is what keeps the sentence deterministic and equal to the old one.
2. **The batched call raises outright** — there is no partition to walk and nothing to attribute, so `_READS[0]`'s label stands. That is what a total outage read as before, when `list_audit_logs` was the first of ten to fail.
3. **Success** — `dict(snapshot.figures)` into the existing commit block, unchanged.

## The `_READS` comment was wrong and is now fixed

STORY-010's report asked STORY-012 to retire half of it, and it is retired. "The rows come first so the slowest query fails fast" described ten sequential statements aborting at the first failure; in one statement there is no first, and the attribution fallback deliberately reads every figure so that nothing fails fast. The comment now records what the order *is* load-bearing for — mirroring `SUMMARY_FIGURES` so the two tables diff against each other, and fixing which label the fault arm names — and says explicitly that the fail-fast claim must not come back. The `total_recorded`-as-denominator sentence survives, as the report said it should.

`load()`'s docstring was rewritten for the same reason: the offload is now justified by `summary_snapshot()` being synchronous and blocking, not by ten connections that could not be shared.

## The test harness change, and why it is not a weakened test

`_Reads` still patches `_READS` with recording stubs; it additionally patches `summary_snapshot` with a fake that **walks the stubbed table and calls each stub** with the limits `load()` actually passed, in the worker thread `load()` offloaded it to, stopping at the first raise. So `calls`, `threads` and `kwargs` remain records of reads that happened rather than numbers the fake invents, and `len(reads.calls) == 10`, `len(failing.calls) == 8`, `threading.get_ident() not in reads.threads` and `reads.calls == []` all keep their original meaning.

**The diff proves the assertions are untouched**: `tests/test_admin_state.py` is +209/−0. Not one line was deleted from that file, so no assertion could have been changed or removed.

Two mutation checks were run to confirm the new tests have teeth, rather than trusting that they pass:

| Mutation | Result |
|---|---|
| Fault arm walks `snapshot.errors` insertion order instead of `_READS` order | `test_the_first_failing_figure_in_read_order_names_the_fault` **failed** |
| `load()` stops forwarding `row_limit` / `ranked_limit` | **15 tests failed** |

Both were reverted; the suite returned to 105 passing.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Environment, skills confirmed, baseline captured | — | ✅ |
| 2 | `summary_snapshot` added to the named-import list | `chat_ui/chat_ui/admin_state.py` | ✅ |
| 3 | `_READS` comment corrected; table byte-unchanged | `chat_ui/chat_ui/admin_state.py` | ✅ |
| 4 | One batched hop + the attribution walk + docstring | `chat_ui/chat_ui/admin_state.py` | ✅ |
| 5 | `_Reads` fake `summary_snapshot`; `_READ_ATTRIBUTES` extended | `tests/test_admin_state.py` | ✅ |
| 6 | Four new tests (round trip, decode failure, order, outright raise) | `tests/test_admin_state.py` | ✅ |
| 7 | Rendered console proved identical against a real database | — | ✅ |
| 8 | Full suite, mutation checks, scope proof | — | ✅ |

## Validation Results

| Check | Baseline | After | Result |
|-------|----------|-------|--------|
| `tests/test_admin_state.py` | 101 | 105 (+4 new) | ✅ |
| `tests/test_admin_shell.py` | 95 | 95 | ✅ |
| `tests/test_summary.py` | 63 | 63 | ✅ |
| `tests/test_render_invariants.py` | 57 | 57 | ✅ |
| `tests/test_register.py` | 178 | 178 | ✅ |
| `tests/test_copy.py` | 22 | 22 | ✅ |
| `tests/test_db.py` | 97 | 97 | ✅ |
| Backend import (`from app.main import app`) | — | OK | ✅ |
| `len(_READS) == 10`, no `insert_audit_log` | — | OK | ✅ |
| Whole suite, file by file | — | 41 files, 3 pre-existing failures | ✅ |
| E2E checklist (7 items) | — | 7/7 | ✅ |

**Three suites fail, all pre-existing and none related to this story.** Each was re-run with this story's two files stashed and failed identically on the pristine tree:

| Suite | Symptom on pristine tree | Symptom after |
|---|---|---|
| `tests/test_chat_state.py` | 1 failed, 37 errors | 1 failed, 37 errors |
| `tests/test_pii_badge.py` | 1 error | 1 error |
| `tests/test_success_metadata_footer.py` | 1 error | 1 error |

These are the `STREAM_EXPIRED` idle-stream issue the PRD index already carries as an open issue owned by no story (present since STORY-006). A whole-suite run in one process also trips it, which is why the suite was run file by file — that is a workaround for the known issue, not a way of hiding a regression, and the three failures above are the same three either way.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/admin_state.py` | UPDATE | +90/-31 |
| `tests/test_admin_state.py` | UPDATE | +209/-0 |

## Deviations from Plan

| Deviation | Why |
|---|---|
| The `load()` docstring's "Four structural properties" became "Five" | The plan added an attribution paragraph without saying the counter above it names the count. Leaving it would have made the docstring lie about itself. |
| One phrase changed in the "collected into a local" paragraph the plan said to leave exactly as it was: "a read that fails on the eighth of ten" → "a figure that fails eighth of ten" | There is no eighth *read* any more. The property is unchanged and still load-bearing; only the noun was stale. |
| The fake `summary_snapshot` records fields after the failing one as errors, rather than omitting them | `SummarySnapshot.__post_init__` requires `figures` and `errors` to partition `SUMMARY_FIGURES` exactly, so a field in neither raises. Not foreseen in the plan; it makes the fake match the real type's contract rather than dodge it. |
| Tests run in a `harness-test:py311` container against the pinned libSQL dev server, reached at `host.docker.internal` | `libsql==0.1.11` publishes no wheel for this host's Python 3.14 (STORY-001 §5). Same container earlier stories used. The endpoint container and the Docker daemon both had to be restarted mid-run. |
| Two mutation checks were run that the plan did not ask for | Task 5 required proving the harness change did not weaken the tests. "The suite still passes" cannot show that; deliberately breaking the code and watching the right test fail can. |

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_admin_state.py` | `test_the_ten_figures_arrive_in_one_round_trip`, `test_a_figure_that_failed_to_decode_is_named_by_its_own_label`, `test_the_first_failing_figure_in_read_order_names_the_fault`, `test_a_batched_read_that_raises_outright_still_names_a_read` |

Plus three helpers built from `_ORIGINAL_READS` and `_READ_RETURNS` rather than retyped literals (`_snapshot_values`, `_label_for`, `_fixed_snapshot`), so a renamed figure or a reworded label cannot silently disagree with the table.

## Acceptance Criteria

- [x] The ten summary figures are obtained in **one** database round trip via STORY-010's batched read — asserted as a call count with the limits checked, not in prose
- [x] A failing figure is named by its own `READ_LABEL_*`, and nothing that was on screen is cleared — see "The acceptance criteria that contradicted each other" for how this AC and AC 6 were reconciled
- [x] `len(_READS) == 10` passes **unmodified**; `_READS` did not change shape (the assertion is at `tests/test_admin_state.py:545`, not `test_admin_shell.py` — STORY-010's report already flagged the PRD's misattribution)
- [x] The read is still off the event loop via `asyncio.to_thread(...)`, and every mutation is still inside `async with self` — the four Reflex background-event rules are quoted in the plan and each is preserved
- [x] `loading` True for the duration and False after, on both paths; `last_refreshed` set only on success
- [x] On any failure, previously loaded rows and figures are left untouched
- [x] The rendered console is identical — `tests/test_render_invariants.py` drives `load()` against a real database and compares the whole serialized state and both rendered pages; all four named suites pass with assertions unchanged
- [x] An unauthenticated `load()` returns immediately and reads nothing — `test_an_unauthenticated_load_calls_none_of_the_ten` passes, with `summary_snapshot` now also boom-patched by `_READ_ATTRIBUTES`
- [x] This story's own diff is exactly `chat_ui/chat_ui/admin_state.py` and `tests/test_admin_state.py` (plus this story's `.agents/` artifacts)
