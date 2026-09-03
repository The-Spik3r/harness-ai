---
story: STORY-012
prd: PRD-007
slug: admin-console-batched-reads
title: "AdminState._READS consumes the batched read, preserving per-figure failure attribution"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-007-turso-migration
created: 2026-09-01
---

# Plan: AdminState._READS consumes the batched read, preserving per-figure failure attribution

## Summary

`AdminState.load()` stops awaiting ten `asyncio.to_thread` hops over `_READS`' ten callables and instead makes **one** hop into `summary_snapshot(row_limit, ranked_limit)` — the batched read STORY-010 shipped. `_READS` keeps its exact `(field, label, callable, kwargs)` shape and its ten entries; what changes is only what supplies each field's value. Attribution survives because `SUMMARY_FIGURES` uses `_READS`' own field names, so `snapshot.errors` maps one-to-one onto the ten `READ_LABEL_*` strings and the fault sentence an admin reads is byte-identical to today's. The commit semantics PRD-006 pinned — one commit at the end, nothing written on the fault arm, `loading` cleared on both paths, `last_refreshed` only on success — are carried across unchanged, and `tests/test_render_invariants.py` proves the rendered payload is identical against a real database.

## User Story

As a compliance admin
I want the console's ten summary figures to arrive in one round trip without losing per-figure error messages
So that the register loads quickly and a partial failure still tells me which read broke instead of blanking the page

## Story Reference

- Story file: `.agents/stories/PRD-007-turso-migration/STORY-012-admin-console-batched-reads.md`
- PRD: `.agents/PRDs/PRD-007-turso-migration/PRD.md` — Section 6 Pattern 3, Section 7.3, Section 5 story 5, Section 12 Phase 3, Section 14 Risk 6
- Dependency: STORY-010 (`status: done`, commit `b592264`) — verified before planning

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui` admin state (the only code outside `app/db/` this migration may touch), admin test suite |
| Story | STORY-012 |
| PRD | PRD-007 |
| Epic Branch | `epic/PRD-007-turso-migration` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `reflex-docs` | `chat_ui/AGENTS.md`, verbatim: "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory." This story rewrites the body of a background event handler. Consulted during planning; the contract it returned is recorded under "The Reflex contract" below and every rule is preserved rather than changed. | Task 3, Task 4 |
| `setup-python-env` | Required by `chat_ui/AGENTS.md` to be *available* before editing Reflex code. Confirmed available. Not invoked: the environment exists and this story adds no dependency. | Task 1 |
| `reflex-process-management` | Required by `chat_ui/AGENTS.md` to be available; used only if the render check in Task 7 needs investigating. | Task 7 |
| `frontend-design` | **Does not apply.** `.agents/skills/` was scanned and read in full: it holds only `frontend-design`, scoped to "distinctive, intentional visual design when building new UI or reshaping an existing one." This story's central constraint is that the rendered output is *identical* — no visual design is made. Recorded here because Phase 1b requires the scan to be stated, not because a rule is carried. | — |

### The Reflex contract (from `reflex-docs`, https://reflex.dev/docs/events/background-events/)

Four rules, all already satisfied by the current handler and all preserved verbatim by this plan:

- "Background tasks cannot modify the state outside of an `async with self` context block." → every write in `load()` stays inside one.
- "Background tasks may read the state outside of an `async with self` context block, but the value may be stale." → this is why the `authenticated` gate is asserted twice, and both assertions stay.
- "Background tasks must be `async` functions." → `load()` stays `async`.
- "Background tasks may not be directly called from other event handlers." → nothing in this story calls `load()` directly.

The docs do not mandate offloading blocking IO, but `summary_snapshot()` is a synchronous blocking call and the handler owns the event loop; the `asyncio.to_thread` hop is therefore kept, and AC 4 requires it explicitly.

---

## The design decision this story turns on

Two acceptance criteria pull against each other, and the plan must resolve them before any code is written.

**AC 2** says a partial failure must name the broken figure "and the figures that succeeded are still displayed. The all-or-nothing failure mode is not acceptable."
**AC 6** says "previously loaded rows and figures are left untouched rather than cleared," unchanged from PRD-006 STORY-004.
**AC 7** says `tests/test_admin_state.py` passes with its assertions unchanged — and two of those assertions are literal:

```python
# SOURCE: tests/test_admin_state.py:640-654 (failing="top_pii_entities")
assert label in state.error
assert state.rows == []          # rows SUCCEEDED and are still not committed
assert state.last_refreshed == ""
```

```python
# SOURCE: tests/test_admin_state.py:617-622
failing = _Reads(monkeypatch, failing="top_models").install()
await _load(state)
assert len(failing.calls) == 8
assert "the model ranking" in state.error
assert _loaded_record(state) == before   # not one of the seven successes committed
```

**Resolution: the transactional commit stays; attribution is what is being rescued.** Committing the nine successes on a partial failure would fail both assertions above and would change the rendered console against `main`, which AC 7 forbids outright. Re-reading the story's own framing settles which reading is intended — the Description says the risk is that batching "turns ten legible partial failures into one blank page," and the Technical Notes name the mechanism: "The mechanism to preserve is the **label**." The blank page AC 2 rejects is the page whose fault panel names *nothing*, not a page that declines to half-commit. Under this resolution AC 2 and AC 6 agree: nothing is cleared, so whatever was displayed before stays displayed, and the fault names the specific figure that broke.

Two consequences to implement deliberately:

1. When more than one figure is in `snapshot.errors`, the fault names the **first in `_READS` order**. That is exactly the label the old sequential loop produced (it aborted at the first failure), so the copy an admin sees is unchanged.
2. STORY-010's report answered a question this story asked, and the answer is a required edit: "'The rows come first so the slowest query fails fast' is now false." That half of the `_READS` order comment must be rewritten, not carried forward. The `total_recorded` half survives as a statement about a relationship between two figures.

---

## Patterns to Follow

### Naming — the batched read's public surface

```python
# SOURCE: app/db/database.py:779-791
SUMMARY_FIGURES = (
    "rows",
    "total_recorded",
    ...
)
# SOURCE: app/db/database.py:1039
def summary_snapshot(row_limit: int = 100, ranked_limit: int = 5) -> SummarySnapshot:
```

`snapshot.figures` and `snapshot.errors` partition `SUMMARY_FIGURES` exactly, enforced in `SummarySnapshot.__post_init__` (`app/db/database.py:818-825`). The ten named properties **raise** the recorded failure; `load()` wants attribution, so it reads the two dicts and never touches the properties — `app/db/database.py:809-812` says so in as many words.

### Error handling — the fault arm, unchanged in shape

```python
# SOURCE: chat_ui/chat_ui/admin_state.py:1024-1033
except Exception as exc:
    # Catch-all, matching PRD-004's "no silent drops": a read
    # that fails is a fault naming what failed, never a silently
    # empty table (PRD-006 Section 4). Nothing has been written
    # to state at this point, so the previous record stands.
    async with self:
        self.error = LOAD_FAILED_MESSAGE.format(
            read=label, detail=exc
        )
    return
```

The same three lines survive; only what produces `label` and `exc` changes.

### Named imports — read-only by construction

```python
# SOURCE: chat_ui/chat_ui/admin_state.py:34-51
from app.db.database import (
    count_audit_logs,
    ...
    top_models as read_top_models,
)
```

PRD-006 Section 9, asserted at `tests/test_admin_state.py:288-293`: a `from app.db import database` would make `insert_audit_log` reachable. `summary_snapshot` is added to this same named-import list; the ten existing names stay, because `_READS`' third slot still records which database function each figure is read from and `tests/test_admin_state.py:483-506` asserts all ten are distinct.

### Tests — the harness that stands in for the database

```python
# SOURCE: tests/test_admin_state.py:441-449
stubbed = tuple(
    (field, label, self._stub(field, fn.__name__, returns), kwargs)
    for field, label, fn, kwargs in _ORIGINAL_READS
)
self._monkeypatch.setattr(admin_state_mod, "_READS", stubbed)
```

```python
# SOURCE: tests/test_admin_state.py:451-464
def _stub(self, field, name, returns):
    def stub(**kwargs):
        self.calls.append(field)
        self.threads.append(threading.get_ident())
        ...
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/admin_state.py` | UPDATE | Import `summary_snapshot`; correct the `_READS` order comment; replace the ten-hop loop in `load()` with one batched hop plus the attribution walk |
| `tests/test_admin_state.py` | UPDATE | `_Reads` stands in for the batched seam while every existing assertion stays literally unchanged; new tests for the round-trip count and for attribution arriving through `snapshot.errors` |

No other file changes. `app/db/` is untouched — STORY-010 built everything this story consumes. `app/routers/admin.py` is STORY-011's, not this story's.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Confirm the environment and capture the baseline

- **File**: — (environment)
- **Action**: RUN
- **Implement**: Confirm the three Reflex skills required by `chat_ui/AGENTS.md` are available (`reflex-docs`, `setup-python-env`, `reflex-process-management`) — `AGENTS.md` says STOP if they are not. Start the pinned libSQL dev server if it is down. Then run the suites this story must not regress and record the pass counts as the baseline to compare against at the end.
- **Mirror**: `.agents/plans/PRD-007-turso-migration/completed/STORY-010-batched-summary-read.plan.md` Task 1 — same endpoint, same `harness-test:py311` container on `harness-net` (`libsql==0.1.11` publishes no wheel for this host's Python 3.14, STORY-001 §5).
- **Validate**:
  ```bash
  curl -sf http://127.0.0.1:8080/health || docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary \
    ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67
  python -m pytest tests/test_admin_state.py tests/test_admin_shell.py tests/test_summary.py tests/test_render_invariants.py -q
  ```

### Task 2: Import the batched read by name

- **File**: `chat_ui/chat_ui/admin_state.py`
- **Action**: UPDATE
- **Implement**: Add `summary_snapshot` to the `from app.db.database import (...)` block at line 34, in alphabetical position among the unaliased names. Do **not** switch to a module import and do **not** remove the ten existing read names.
- **Mirror**: `chat_ui/chat_ui/admin_state.py:34-51`
- **Comment must record**: nothing new here — but the module docstring at lines 12-17 quotes PRD-006 Section 9 ("`AdminState` imports only the read functions") and still reads true, since `summary_snapshot` is a read. Leave it.
- **Validate**: `python -c "import chat_ui.chat_ui.admin_state as m; assert m.summary_snapshot and not hasattr(m, 'insert_audit_log')"`

### Task 3: Correct the `_READS` comment, keep the table

- **File**: `chat_ui/chat_ui/admin_state.py` (comment block at lines 212-228, table at 229-260)
- **Action**: UPDATE
- **Implement**: The tuple itself is **not** edited — same ten entries, same `(field, label, callable, kwargs)` shape, same order. Rewrite only the final paragraph of the comment (lines 226-228). Delete the fail-fast claim: STORY-010's report states it plainly — "'The rows come first so the slowest query fails fast' is now false ... In one statement there is no first." Replace it with what the order now means: it is the order `SUMMARY_FIGURES` (`app/db/database.py:779`) mirrors, so the two tables stay diff-able, and it is the order the fault arm walks to pick which label to name when more than one figure fails. Keep the `total_recorded`-as-denominator sentence — the report confirms it survives as documentation of a relationship between two figures. Also extend the opening paragraph to say the third slot is now the database function each figure is *read from* rather than the callable `load()` awaits.
- **Mirror**: `chat_ui/chat_ui/admin_state.py:212-228` — same comment voice: what would break if this were changed, not what it does.
- **Validate**: `python -c "import chat_ui.chat_ui.admin_state as m; assert len(m._READS) == 10 and len({f for f,_,_,_ in m._READS}) == 10"`

### Task 4: One batched hop in `load()`, with the attribution walk

- **File**: `chat_ui/chat_ui/admin_state.py` (`load()`, lines 962-1052)
- **Action**: UPDATE
- **Implement**: Replace the `for field, label, read, kwargs in _READS:` loop (lines 1021-1033) with:
  1. One offloaded call — `snapshot = await asyncio.to_thread(summary_snapshot, row_limit=REGISTER_ROW_LIMIT, ranked_limit=RANKED_LIMIT)` — wrapped in `try/except Exception as exc`. If the call itself raises, nothing came back to attribute, so arm the fault with `_READS[0]`'s label (`READ_LABEL_ROWS`) and return: that is the same sentence a total outage produced before, when `list_audit_logs` was the first read to fail.
  2. The attribution walk — iterate `_READS` in order and, on the first `field in snapshot.errors`, set `self.error = LOAD_FAILED_MESSAGE.format(read=label, detail=snapshot.errors[field])` inside `async with self` and `return`. First-in-order is deliberate: it reproduces the label the sequential loop produced.
  3. `results = dict(snapshot.figures)` and then the existing commit block, entirely unchanged — `rows = [to_audit_row(log, now) for log in results.pop("rows")]`, one `async with self`, `setattr` over the rest, `last_refreshed`, `self.error = ""`.
  The `now` clock read, the double `authenticated` gate, the `loading` guard, and the `finally` that clears `loading` are all untouched.
- **Mirror**: `chat_ui/chat_ui/admin_state.py:1024-1033` for the fault arm's exact shape; `app/db/database.py:1060-1078` for how `figures`/`errors` are consumed.
- **Docstring must record**: rewrite the "Each read is offloaded **per call**" paragraph (lines 981-990). It is now one hop, not ten, and its rationale has moved: the offload exists because `summary_snapshot()` is synchronous and blocking, not because ten connections could not be shared. Keep STORY-006's finding that the shared client is safe to reach from a worker thread — it is why one hop is enough — and delete the "Sequential rather than gathered" paragraph, which described a fan-out that no longer exists. State that the fault arm walks `_READS` in order so the label is the one the sequential loop would have named. Leave the "collected into a **local**" and "`finally` clears `loading` on **both** paths" paragraphs exactly as they are; both are still load-bearing and both are still true.
- **Validate**: `python -m pytest tests/test_admin_state.py -q -k "load or read"` (expected to fail until Task 5 — the harness still stubs the old seam; do not "fix" it by touching `load()`)

### Task 5: Point the `_Reads` harness at the batched seam

- **File**: `tests/test_admin_state.py` (`_Reads`, lines 418-464; `_READ_ATTRIBUTES`, lines 844-855)
- **Action**: UPDATE
- **Implement**: `install()` keeps everything it does today — it still builds `stubbed` from `_ORIGINAL_READS` and still patches `_READS`, so `_stub` is unchanged and the recorded `calls` / `threads` / `kwargs` keep their present meaning. Add a second patch: `admin_state_mod.summary_snapshot` is replaced by a fake that stands in for the database. The fake takes `row_limit` and `ranked_limit`, walks `admin_state_mod._READS` **in order**, and for each entry calls that entry's stub with the limit it was actually handed (`{"limit": row_limit}` for `rows`, `{"limit": ranked_limit}` for the three ranked fields, `{}` for the counts) — derived from the fake's arguments, not from the table's literals, so `assert reads.kwargs["rows"] == {"limit": 100}` keeps its teeth. It stops at the first stub that raises, recording that field and every field after it in `errors`, and returns a real `app.db.database.SummarySnapshot` (whose `__post_init__` then enforces the full partition). Add `"summary_snapshot"` to `_READ_ATTRIBUTES` so `test_evaluating_visible_rows_performs_no_database_read` boom-patches the new seam too.
- **Mirror**: `tests/test_admin_state.py:441-464`
- **Not changed**: not one assertion in any test body. `len(reads.calls) == 10`, `len(failing.calls) == 8`, `threading.get_ident() not in reads.threads`, `reads.calls == []`, `len(seen) == 10` — all keep their present text and all keep their present meaning, because the fake genuinely calls the stubs, genuinely runs inside the `to_thread` worker, and genuinely stops where the sequential read stopped.
- **Comment must record**: on the fake — that the ten stubs are still what produce the figures, so `_READS`' third slot is exercised rather than decorative, and that stopping at the first raise is what keeps `len(failing.calls) == 8` a statement about the read rather than a number the fake invents.
- **Validate**: `python -m pytest tests/test_admin_state.py -q`, then `git diff tests/test_admin_state.py` — no changed line may be an `assert` inside a test body

### Task 6: Test what batching newly makes possible — and newly risks

- **File**: `tests/test_admin_state.py`
- **Action**: UPDATE
- **Implement**: Four tests, appended to the load-path section:
  1. `test_the_ten_figures_arrive_in_one_round_trip` — patch `summary_snapshot` with a counter returning a full snapshot; assert it was entered exactly once per `load()` and that `row_limit`/`ranked_limit` were `REGISTER_ROW_LIMIT` and `RANKED_LIMIT`. This is AC 1, counted rather than asserted in prose, mirroring `tests/test_db.py::test_summary_snapshot_issues_one_round_trip`.
  2. `test_a_figure_that_failed_to_decode_is_named_by_its_own_label` — hand `load()` a snapshot with nine figures and `errors={"top_users": ...}` (the decode-layer failure only batching can produce, which no existing test reaches). Assert the error contains `READ_LABEL_TOP_USERS` and that the record is untouched. This is AC 2's mechanism at the layer STORY-010 built for it.
  3. `test_the_first_failing_figure_in_read_order_names_the_fault` — a snapshot with two figures in `errors`; assert the earlier one in `_READS` order is the one named, so multiple failures cannot make the copy nondeterministic.
  4. `test_a_batched_read_that_raises_outright_still_names_a_read` — make `summary_snapshot` raise; assert `READ_LABEL_ROWS` is named, `loading` is False, and nothing was committed. Guards the arm where there is no `errors` dict to walk.
- **Mirror**: `tests/test_admin_state.py:605-654` for the fault-arm test shape; `tests/test_db.py` for the round-trip counter.
- **Validate**: `python -m pytest tests/test_admin_state.py -q`

### Task 7: Prove the rendered console is identical

- **File**: — (validation only)
- **Action**: RUN
- **Implement**: `tests/test_render_invariants.py:217-223` drives `authenticate()` then `load()` against a real libSQL database in a subprocess and compares the whole serialized state and both rendered pages. It is the AC 7 check that the output matches `main` for the same data, and it is the one place the real `summary_snapshot` — not a fake — reaches the console. Run it, plus the register, summary and shell suites. If the Reflex compile step misbehaves, investigate per `reflex-process-management` rather than editing the test.
- **Validate**: `python -m pytest tests/test_render_invariants.py tests/test_summary.py tests/test_admin_shell.py tests/test_register.py -q`

### Task 8: Full suite and scope proof

- **File**: — (validation only)
- **Action**: RUN
- **Implement**: Run the whole suite against the baseline from Task 1 and confirm this story's own diff is exactly two files. Per STORY-010's report, check the story's own diff (`git diff HEAD --stat`), not `git diff main`, which on an epic branch carries every earlier story.
- **Validate**:
  ```bash
  python -m pytest -q
  git diff HEAD --stat
  ```

---

## End-to-End Tests

- [ ] libSQL dev endpoint answers `/health` before any suite runs
- [ ] `tests/test_render_invariants.py` — `load()` against a real database produces a serialized state and two rendered pages with no new errors; figures, shares, ranked lines and copy unchanged
- [ ] `python -m pytest tests/test_admin_state.py -q` passes with no assertion line changed (`git diff` proves it)
- [ ] `tests/test_admin_shell.py`, `tests/test_summary.py`, `tests/test_register.py`, `tests/test_copy.py` pass at their Task 1 baseline counts
- [ ] `summary_snapshot` entered exactly once per `load()`, with `row_limit=100` and `ranked_limit=5`
- [ ] A figure in `snapshot.errors` renders the fault panel naming that figure's `READ_LABEL_*`; the previously loaded record is intact and `loading` is False
- [ ] An unauthenticated `load()` enters `summary_snapshot` zero times

## Validation

```bash
curl -sf http://127.0.0.1:8080/health
python -m pytest tests/test_admin_state.py -q
python -m pytest tests/test_admin_shell.py tests/test_summary.py tests/test_register.py tests/test_render_invariants.py -q
python -m pytest -q
python -c "import chat_ui.chat_ui.admin_state as m; assert len(m._READS) == 10; assert not hasattr(m, 'insert_audit_log')"
git diff HEAD --stat
```

## Acceptance Criteria

(Copied from story STORY-012)

- [ ] Given `AdminState.load()`, when it runs, then the ten summary figures are obtained in **one** database round trip via the batched read from STORY-010.
- [ ] Given one figure's underlying statement failing, when the console renders, then the fault names that figure using its existing `READ_LABEL_*` copy, and the figures that succeeded are still displayed. The all-or-nothing failure mode is not acceptable. *(Resolved as documented above: nothing is cleared, so the successes on screen stay on screen, and the fault names the specific figure. Committing a partial result is excluded by AC 7.)*
- [ ] Given `tests/test_admin_shell.py`, when it runs, then its `len(_READS) == 10` assertion passes **unmodified**. *(The assertion is at `tests/test_admin_state.py:489-490`, not `test_admin_shell.py` — STORY-010's report already flagged the PRD's misattribution. It passes unmodified, and `_READS` does not change shape.)*
- [ ] Given the database read, when it executes, then it is still off the event loop via `asyncio.to_thread(...)`, and state mutation still happens inside `async with self`.
- [ ] Given a load in flight, when the page is observed, then `loading` is True for its duration and False afterwards, including on the failure path, and `last_refreshed` is set only on success.
- [ ] Given any failure, when `load()` handles it, then previously loaded rows and figures are left untouched rather than cleared.
- [ ] Given the rendered console, when it is compared to `main` for the same data, then the output is identical. `tests/test_admin_state.py`, `tests/test_summary.py`, `tests/test_admin_shell.py` and `tests/test_render_invariants.py` pass with their assertions unchanged.
- [ ] Given an unauthenticated state, when `load()` is called, then it returns immediately and performs no database read.
- [ ] All tasks completed
- [ ] Full test suite passes at or above the Task 1 baseline
- [ ] This story's own diff is exactly `chat_ui/chat_ui/admin_state.py` and `tests/test_admin_state.py`
- [ ] Follows existing patterns

## Risks

| Risk | Mitigation |
|------|-----------|
| The `_Reads` harness change is mistaken for a weakened test | Task 5 forbids touching any assertion and requires the fake to call the real stubs in the worker thread; `git diff` on the file is the proof, and Task 7's real-database render check does not use the fake at all |
| A partial-commit reading of AC 2 is implemented instead | The design decision above is stated before any task, with the two literal assertions that exclude it quoted |
| The corrected `_READS` comment drifts back to the fail-fast claim | Task 3 makes the deletion explicit and cites STORY-010's report as the source that retired it |
| `summary_snapshot`'s own fallback costs up to ten round trips | By design (STORY-010): paid only when the batch is already broken. `load()` does not need to know, but its docstring must not claim one round trip unconditionally |
