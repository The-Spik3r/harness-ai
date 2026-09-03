---
story: STORY-011
prd: PRD-007
slug: stats-endpoint-batched
title: "GET /stats consumes the batched read instead of nine sequential calls"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-007-turso-migration
created: 2026-09-02
---

# Plan: GET /stats consumes the batched read instead of nine sequential calls

## Summary

`get_stats()` fills one `StatsResponse` from nine sequential database functions. STORY-010 shipped `summary_snapshot()`, which returns all ten summary figures from **one** statement, and STORY-012 has already adopted it in `AdminState.load()`. This story does the same for the endpoint: replace the nine calls with one `summary_snapshot(row_limit=0)` and read nine of its ten named properties. The response schema, field order, success-rate formula, empty-database behavior and `stats:read` gate are all untouched. The only non-obvious decision is the tenth figure — `rows` — which `/stats` does not want: it is skipped by passing `row_limit=0`, so the row-carrying column comes back as an empty JSON array instead of up to 100 audit rows crossing the network for nothing. `get_audit` in the same file is not touched.

## User Story

As an integrating developer
I want `GET /stats` to answer in one database round trip
So that the endpoint's latency does not scale with the number of figures it reports now that each read crosses a network.

## Story Reference

- Story file: `.agents/stories/PRD-007-turso-migration/STORY-011-stats-endpoint-batched.md`
- PRD: `.agents/PRDs/PRD-007-turso-migration/PRD.md` — Section 6 Pattern 3, Section 7.3, Section 10, Section 12 Phase 3

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | `app/routers/admin.py` (`get_stats` only), `tests/test_stats_router.py` |
| Story | STORY-011 |
| PRD | PRD-007 |
| Epic Branch | `epic/PRD-007-turso-migration` (commit directly on this branch) |

---

## Skills In Use

`.agents/skills/` was listed in full; it contains exactly one skill.

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `frontend-design` | **Does not apply.** Its `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one". This story changes a JSON endpoint's data source; nothing rendered changes, and `chat_ui/` is not touched. The story frontmatter's `skills: []` is correct. | None |

No skill constrains the tools, commands or workflow of this story.

---

## Patterns to Follow

### The batched read and its result type

```python
# SOURCE: app/db/database.py:1039-1078
def summary_snapshot(row_limit: int = 100, ranked_limit: int = 5) -> SummarySnapshot:
    ...
    try:
        with _session() as conn:
            row = conn.execute(
                _SUMMARY_SQL,
                (row_limit, ranked_limit, ranked_limit, ranked_limit),
            ).fetchone()
    except StorageError as exc:
        return _summary_figure_by_figure(row_limit, ranked_limit, exc)

    figures: dict = {}
    errors: dict = {}
    for name in SUMMARY_FIGURES:
        try:
            figures[name] = _SUMMARY_DECODERS[name](row[name])
        except Exception as exc:  # noqa: BLE001 -- one bad column is one bad figure
            errors[name] = exc
    return SummarySnapshot(figures=figures, errors=errors)
```

```python
# SOURCE: app/db/database.py:823-828
    def _figure(self, name: str) -> Any:
        if name in self.errors:
            raise self.errors[name]
        return self.figures[name]
```

**This is the property that keeps `/stats`' error behavior identical.** Today a failing read raises out of `get_stats()` and FastAPI turns it into a 500. Reading `snapshot.total_recorded` raises the recorded exception in exactly the same place. `/stats` wants the value or nothing; it is not the caller that wants attribution (STORY-012 is), so the named properties are the right surface and `snapshot.errors` is never inspected here.

### The consumer precedent (STORY-012, same batched read)

```python
# SOURCE: chat_ui/chat_ui/admin_state.py:1052-1057
            snapshot = await asyncio.to_thread(
                summary_snapshot,
                row_limit=REGISTER_ROW_LIMIT,
                ranked_limit=RANKED_LIMIT,
            )
```

`AdminState` passes both limits because it owns the caps its copy states. `/stats` owns neither: its three ranked figures are called today as `top_models()`, `top_users()`, `top_pii_entities()` — i.e. each function's own default of 5 (`app/db/database.py:684,699,724`), which is also `summary_snapshot`'s `ranked_limit` default. So `/stats` leaves `ranked_limit` unpassed, and a default that ever moved would move for both paths together, exactly as it does today.

### Naming and imports in the router

```python
# SOURCE: app/routers/admin.py:3-14
from app.db.database import (
    count_audit_logs,
    count_blocked_duplicates,
    ...
)
```

Flat, alphabetized `from app.db.database import (...)`. After this story only `count_audit_logs` and `list_audit_logs` (both `get_audit`'s) plus `summary_snapshot` remain.

### Test patterns

```python
# SOURCE: tests/test_stats_router.py:19-38
def _fail_if_called(*args, **kwargs):
    raise AssertionError("repository function should not have been called")


def _guard_all_aggregates(monkeypatch):
    for name in (
        "count_audit_logs",
        ...
    ):
        monkeypatch.setattr(f"app.routers.admin.{name}", _fail_if_called)
```

```python
# SOURCE: tests/test_db.py:118-148 (the recording-connection idiom)
        def execute(self, sql, *parameters):
            statements.append(sql)
            return self._conn.execute(sql, *parameters)

    monkeypatch.setattr(
        database, "get_connection", lambda: _RecordingConnection(real_get_connection()),
    )
```

```python
# SOURCE: tests/test_admin_state.py:762-776 (how STORY-012 pinned "one round trip" in a consumer)
async def test_the_ten_figures_arrive_in_one_round_trip(configured_token, monkeypatch):
    ...
    assert calls == [(REGISTER_ROW_LIMIT, RANKED_LIMIT)]
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/routers/admin.py` | UPDATE | `get_stats()` fills `StatsResponse` from one `summary_snapshot()` call; the seven now-unused imports go, the two `get_audit` still uses stay. |
| `tests/test_stats_router.py` | UPDATE | `_guard_all_aggregates` retargets onto the name the router now imports; two new tests pin the single round trip and the skipped `rows` figure. Every existing assertion stays byte-identical. |

Nothing is created. `app/models/schemas.py`, `app/db/database.py`, `chat_ui/` and `get_audit` are not touched.

---

## Decision: the tenth figure

The story asks this be settled and reported: *"Confirm the batched read lets a caller skip a figure it does not want, or that fetching it is cheap enough not to matter."*

**It cannot be skipped structurally, but it can be emptied, and emptying it is what matters.** `_SUMMARY_SQL` (`app/db/database.py:901-961`) is a fixed ten-column `SELECT`; there is no per-figure projection, and adding one would reopen STORY-010's design. But the rows column is `(SELECT json_group_array(json_object(...)) FROM (SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?))` and that `?` is `row_limit`. Passing `row_limit=0` makes the subquery empty, so the column that would otherwise carry up to 100 fully serialized audit rows — nineteen fields each, including two preview strings — carries an empty array instead. That is precisely the transfer cost Section 6 Pattern 4 exists to avoid, and leaving it at the default 100 would have `/stats` pay a per-load payload for a figure it never reads.

Two consequences to verify rather than assume (Task 1):

1. `json_group_array` over zero rows returns `'[]'`, not `NULL`. If it returned `NULL` the `rows` decode fails, lands in `snapshot.errors`, and — because `/stats` never touches `snapshot.rows` — nothing raises and the response is still correct. The failure mode is benign either way; the plan still measures which one is real, because "benign either way" is a claim, not an observation.
2. `LIMIT 0` is accepted by the endpoint (it is standard SQLite, but STORY-001's rule for this driver is that behavior gets verified, not assumed).

---

## Dependency Order

Task 1 (verify `row_limit=0`) gates Task 2, because a `LIMIT 0` that misbehaved would change the endpoint's argument. Task 3 must follow Task 2 (the retargeted guard names an import that only exists after Task 2). Tasks 4–5 follow Task 3. Task 6 validates all of it. Task 7 reports.

## Risks + Mitigations

| Risk | Mitigation |
|---|---|
| Removing the seven imports breaks `_guard_all_aggregates`, which patches them by name on `app.routers.admin` — `monkeypatch.setattr` raises `AttributeError` on a missing attribute. Two auth tests fail. | Task 3 retargets the helper onto `summary_snapshot`, which is **stronger**: it guards one gate instead of seven, and it covers `count_pii_detected_queries`/`top_pii_entities`, which the current list silently omits. The tests' assertions do not change; only the helper's target does. Flag this in the report as the one edit the story's "assertions unchanged" AC permits. |
| Counting *all* statements during a `/stats` request will not equal 1: `require_permission` → `require_identity` resolves the caller's token against the `users` table first. | The new round-trip test counts only statements that read `audit_logs`, and asserts exactly one. That is the AC's claim ("one database round trip for all its figures") stated precisely, and it does not become brittle if the auth path's read count ever changes. |
| The success-rate figure is tempting to "fix" while touching it — `success = 1` counts blocked-but-recorded queries. | AC 3 forbids it. The formula moves operand for operand: `count_audit_logs()` → `snapshot.total_recorded`, `count_successful_queries()` → `snapshot.successful_queries`. The `total > 0` guard and the `"0.0%"` literal are copied verbatim. |
| `SummarySnapshot`'s field name for the total is `total_recorded`, not `total_queries`; a mis-mapping would be silent because both are `int`. | Task 2 maps them one at a time against the table below, and `test_valid_token_returns_expected_shape_and_values` already pins four distinct integer values (4/1/1/2) that a swap could not survive. |
| Widening the diff into `get_audit`. | `get_audit`'s `count_audit_logs(user_id=scope_user_id)` is a scoped read, and `list_audit_logs(limit=100, user_id=...)` likewise; neither figure exists in the batch, which is whole-table only. Both imports stay. Task 6 proves the diff touches nothing else. |
| `get_stats` accidentally becoming `async def`. | It stays a plain `def` (line 70). FastAPI dispatches it to a threadpool; `summary_snapshot()` is blocking, and on the event loop it would block every other request. Task 2 keeps the signature unchanged. |

### The nine-figure mapping

| `StatsResponse` field | Today | After |
|---|---|---|
| `total_queries` | `count_audit_logs()` | `snapshot.total_recorded` |
| `blocked_duplicates` | `count_blocked_duplicates()` | `snapshot.blocked_duplicates` |
| `blocked_suspicious` | `count_blocked_suspicious()` | `snapshot.blocked_suspicious` |
| `unique_users` | `count_unique_users()` | `snapshot.unique_users` |
| `success_rate` | `count_successful_queries()` / `count_audit_logs()` | `snapshot.successful_queries` / `snapshot.total_recorded` |
| `top_models` | `top_models()` | `snapshot.top_models` |
| `top_users` | `top_users()` | `snapshot.top_users` |
| `pii_detected_queries` | `count_pii_detected_queries()` | `snapshot.pii_detected_queries` |
| `top_pii_entities` | `top_pii_entities()` | `snapshot.top_pii_entities` |
| — | — | `rows` — not read, emptied via `row_limit=0` |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Verify `row_limit=0` empties the rows figure without disturbing the other nine

- **File**: none (investigation; the result is recorded in the report)
- **Action**: VERIFY
- **Implement**: Against the running libSQL dev server, seed a handful of audit rows and compare `summary_snapshot(row_limit=0)` with `summary_snapshot()`. Record: (a) whether `"rows"` lands in `figures` (as `[]`) or in `errors`; (b) that the other nine figures are identical between the two calls; (c) that the statement count is still 1. Confirm the dev server is up first — `tests/conftest.py` documents the exact `docker run` line and `pytest.exit`s with it if not.
- **Mirror**: `tests/test_db.py:1136-1153` — the recording-connection statement count is the instrument.
- **Validate**: a scratch script or pytest printing both snapshots' `figures`/`errors` keys; the nine non-`rows` figures compare equal.

### Task 2: `get_stats()` reads one snapshot

- **File**: `app/routers/admin.py`
- **Action**: UPDATE
- **Implement**:
  - In the `from app.db.database import (...)` block, drop `count_blocked_duplicates`, `count_blocked_suspicious`, `count_pii_detected_queries`, `count_successful_queries`, `count_unique_users`, `top_models`, `top_pii_entities`, `top_users`; add `summary_snapshot`. Keep `count_audit_logs` and `list_audit_logs` — `get_audit` uses both. Keep the block alphabetized.
  - In `get_stats()` (still `def`; decorator and `dependencies=[...]` untouched), open with `snapshot = summary_snapshot(row_limit=0)`, then fill `StatsResponse` from the mapping table above, in the same field order the constructor already uses.
  - Keep `total`/`successful` as locals so the `success_rate` expression stays character-identical: `f"{(successful / total * 100):.1f}%" if total > 0 else "0.0%"`.
  - Add a short comment saying (i) one statement replaces nine reads (PRD-007 Section 6 Pattern 3), (ii) `row_limit=0` because the endpoint wants nine of the ten figures and the tenth would otherwise put up to 100 serialized audit rows on the wire per call, (iii) `ranked_limit` is left at the shared default because the three `top_*` functions are called with their own default of 5 today, and (iv) the function stays synchronous on purpose — `summary_snapshot()` blocks, and `async def` would move that onto the event loop.
- **Mirror**: `chat_ui/chat_ui/admin_state.py:1052-1057` (the other consumer of the same read); `app/db/database.py:823-828` (the properties raise, which is why no error handling is added here).
- **Validate**: `python -c "from app.main import app"` imports clean; `grep -n "count_blocked\|top_models\|count_unique" app/routers/admin.py` returns nothing.

### Task 3: Retarget `_guard_all_aggregates` onto the batched read

- **File**: `tests/test_stats_router.py`
- **Action**: UPDATE
- **Implement**: Replace the seven-name loop with a single `monkeypatch.setattr("app.routers.admin.summary_snapshot", _fail_if_called)`. Keep `_fail_if_called` and the helper's name and signature as they are — the two callers do not change. Add a comment: the guard's claim is unchanged ("the gate refuses before any aggregation happens"), there is now one call to guard instead of seven, and this guard is the stricter of the two because the old list omitted `count_pii_detected_queries` and `top_pii_entities`.
- **Mirror**: `tests/test_stats_router.py:19-38` — the same helper, one target.
- **Validate**: `pytest tests/test_stats_router.py -k "token" -q` — the two auth tests pass, and they still fail if the gate is bypassed.

### Task 4: Pin the single round trip

- **File**: `tests/test_stats_router.py`
- **Action**: UPDATE
- **Implement**: Add `test_stats_issues_one_database_round_trip_for_its_figures`. Wrap `app.db.database.get_connection` in a recording proxy that appends each SQL string, seed a few audit rows, then issue the authenticated `GET /stats`. Assert the proxy captured something ("the patch did not take"), and that exactly one captured statement reads `audit_logs`. Docstring: the count is filtered to `audit_logs` because `require_identity` resolves the bearer token against `users` first, so what this pins is the endpoint's *figure* reads, per AC 1. Carry the "instead of nine" contrast explicitly — either count the same statements while calling the nine standalone functions directly (expect nine) or state in the docstring that `tests/test_db.py::test_summary_snapshot_issues_one_round_trip` holds the 1-vs-10 contrast and this test pins the endpoint's adoption of it.
- **Mirror**: `tests/test_db.py:990-1002` + `:1136-1153` (proxy + count); `tests/test_admin_state.py:762-776` (a consumer pinning the same property).
- **Validate**: `pytest tests/test_stats_router.py -q` — the new test passes, and fails if `get_stats` is reverted to nine calls.

### Task 5: Pin that `/stats` does not pull the register rows

- **File**: `tests/test_stats_router.py`
- **Action**: UPDATE
- **Implement**: Add `test_stats_does_not_fetch_the_register_rows`. Monkeypatch `app.routers.admin.summary_snapshot` with a recorder returning a valid ten-figure `SummarySnapshot`, call `GET /stats`, and assert the recorder saw `row_limit=0` and that the response is unchanged. Assert `ranked_limit` was **not** passed (or was passed as 5), so the "defaults track defaults" decision is pinned rather than left to a comment. Docstring: the endpoint needs nine of ten figures; the tenth is emptied rather than skipped because `_SUMMARY_SQL` is a fixed ten-column SELECT, and a `row_limit` that drifted back to 100 would put up to 100 serialized audit rows on the wire per call with nothing reading them.
- **Mirror**: `tests/test_admin_state.py:748-758` (`_fixed_snapshot` — the same recorder-around-`summary_snapshot` idiom).
- **Validate**: `pytest tests/test_stats_router.py -q` — passes; fails if `row_limit=0` is dropped.

### Task 6: Full validation and untouched-callers proof

- **File**: none
- **Action**: VERIFY
- **Implement**: Run the affected suites, confirm `git diff` covers exactly the two files, and confirm `get_audit`'s body is byte-identical to `HEAD`.
- **Validate**: the commands in the Validation section below.

### Task 7: Implementation report

- **File**: `.agents/reports/PRD-007-turso-migration/STORY-011-stats-endpoint-batched.report.md`
- **Action**: CREATE
- **Implement**: Follow the STORY-010/012 report shape. It must answer the two questions the story asks by name: **(a)** whether the batched read lets a caller skip a figure it does not want — Task 1's measured answer, with the `row_limit=0` reasoning; **(b)** the measured round-trip count for `/stats` (Section 12 Phase 3 asks for counts, not prose). Also record the `_guard_all_aggregates` retarget as the single test-helper edit, with why it does not violate "assertions unchanged".
- **Validate**: the report cites the real commit SHA and real measured numbers.

---

## End-to-End Tests

- [ ] Start the libSQL dev server; `uvicorn app.main:app` boots without error.
- [ ] `GET /stats` with no token → 401/403, and no aggregation runs.
- [ ] `GET /stats` with a wrong token → 401/403.
- [ ] `GET /stats` with `ADMIN_TOKEN` on a seeded database → 200, and the JSON is byte-identical to `main`'s for the same rows (diff the two response bodies, key order included).
- [ ] `GET /stats` on an **empty** database → 200 with `success_rate == "0.0%"` and every list empty — the division-by-zero path unchanged (AC 4).
- [ ] `GET /stats` as an `auditor` → 200, same shape (the PRD-005 gate did not move, AC 5).
- [ ] `GET /stats` as a `user` lacking `stats:read` → 403 with `Permission denied: stats:read`.
- [ ] `GET /audit` still answers unchanged for both an `audit:read:all` and an `audit:read:own` caller (AC 7).

## Validation

```bash
# The suites this story can affect
pytest tests/test_stats_router.py -q
pytest tests/test_admin_auth.py tests/test_main.py -q
pytest tests/test_db.py -q                    # summary_snapshot itself, unchanged

# Backend imports
python -c "from app.main import app; print('ok')"

# The diff is exactly two files, and get_audit is untouched
git diff --stat
git diff app/routers/admin.py
```

Tests run in the `harness-test:py311` container against the libSQL dev server, per STORY-010's report — `libsql==0.1.11` publishes no wheel for this host's Python 3.14 (STORY-001 §5). Attach the container to `harness-net` so it can reach the endpoint. Note the known, pre-existing `STREAM_EXPIRED` issue on whole-suite runs (index.md, "Open issue"): run these suites individually, and do not attribute that failure to this story without checking it on a pristine tree.

## Acceptance Criteria

(Copied from story `STORY-011`)

- [ ] Given `GET /stats`, when it is served, then it issues **one** database round trip for all its figures, using the batched read from STORY-010.
- [ ] Given the response, when it is compared to `main`'s output for the same data, then it is byte-identical. `StatsResponse`'s field set, types, and ordering are unchanged.
- [ ] Given the success-rate figure, when it is computed, then it is still `count_successful_queries() / count_audit_logs()` with the same semantics documented at `chat_ui/chat_ui/admin_copy.py:292` — `success = 1` includes blocked-but-recorded queries. Not "fixed" here.
- [ ] Given a division by zero on an empty database, when `/stats` is served, then it behaves exactly as it does today.
- [ ] Given `stats:read` authorization, when an unauthorized caller requests `/stats`, then the gate behaves unchanged — no PRD-005 behavior moves in this story.
- [ ] Given `tests/test_stats_router.py`, when it runs, then it passes with its assertions unchanged, plus a new assertion pinning the single-round-trip property.
- [ ] Given `GET /audit`, when it is inspected, then it is untouched. Its `count_audit_logs(user_id=scope_user_id)` call stays a standalone call.
- [ ] All tasks completed
- [ ] Backend server starts without error
- [ ] Follows existing patterns
