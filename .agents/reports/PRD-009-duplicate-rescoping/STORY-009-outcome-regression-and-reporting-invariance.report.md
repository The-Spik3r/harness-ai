---
story: STORY-009
prd: PRD-009
plan: .agents/plans/PRD-009-duplicate-rescoping/completed/STORY-009-outcome-regression-and-reporting-invariance.plan.md
epic_branch: epic/PRD-009-duplicate-rescoping
commit: 29e471e
status: COMPLETE
completed: 2026-09-17
---

# Implementation Report — STORY-009: Six-outcome regression and /audit, /stats and admin-console invariance verified on the finished epic

**Plan**: `.agents/plans/PRD-009-duplicate-rescoping/completed/STORY-009-outcome-regression-and-reporting-invariance.plan.md`
**Epic Branch**: `epic/PRD-009-duplicate-rescoping`
**Commit**: `29e471e`

## Summary

This story checks that the finished epic changed no `POST /query` outcome and no reporting figure.

- **Git evidence.** The six-outcome regression module is byte-identical to STORY-001's commit. The router/integration diffs since the epic base change no assertion (every hunk is listed below).
- **Unmodified modules, green.** `tests/test_query_outcomes_regression.py` and `tests/test_two_instance_smoke.py` pass on the epic head without edits.
- **One new module, `tests/test_reporting_invariance.py`.** It seeds seven pipeline-written rows through real `POST /query` requests and pins the `/stats`, `summary_snapshot()` and `/audit` invariants, plus the one-lookup, one-insert statement count on a successful `/query`.

**Production changes: none.** No earlier story regressed, so no fix commit was needed.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | AC 1: regression module unchanged since `9abef61` and green | — (evidence) | ✅ |
| 2 | AC 2: every hunk in the router/integration diffs listed; no assertion changed | — (evidence) | ✅ |
| 3 | Module skeleton, two users, stubs, statement proxy, fixed 7-row seed | `tests/test_reporting_invariance.py` | ✅ |
| 4 | AC 3: `/stats` and `summary_snapshot()` figures; `blocked_duplicates`; console numerator | same | ✅ |
| 5 | AC 3: no `dedup_key` on `AuditQueryEntry`/`AuditRow`/`/audit`; `prompt_hash` over raw prompt | same | ✅ |
| 6 | AC 5: one duplicate lookup + one audit insert per successful `/query` | same | ✅ |
| 7 | AC 4: two-instance smoke, unmodified, green | — (evidence) | ✅ |
| 8 | Full suite, change audit, this report | this file | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`python -c "from app.main import app"`) | ✅ OK |
| Frontend lint | N/A: the repo has no `frontend/` directory (the UI is Reflex under `chat_ui/`, untouched) |
| `GET /health` | ✅ `{"status":"ok"}`. Booted with `uvicorn` against the local libSQL dev server with `RBAC_ENABLED=false`, because the freshly reset test database has no users and the RBAC bootstrap guard refuses to start otherwise |
| `tests/test_query_outcomes_regression.py` | ✅ 7 passed |
| `tests/test_query_router.py` + `tests/test_integration.py` | ✅ 51 passed |
| `tests/test_reporting_invariance.py` | ✅ 6 passed |
| `tests/test_two_instance_smoke.py` | ✅ 10 passed |
| Full suite | ✅ 1965 passed, 25 skipped. All 25 skips are `tests/test_reports_e2e.py` tests needing `REPORTS_E2E_URL` (a running server); they were skipped before this story too |
| E2E checklist (plan) | ✅ 8/8 |

## Acceptance Criteria Evidence

### AC 1 — regression module untouched and green

```
$ git log --oneline -- tests/test_query_outcomes_regression.py
9abef61 test(duplicates): STORY-001 pin today's duplicate lookup and the six /query outcomes

$ git diff 9abef61..HEAD -- tests/test_query_outcomes_regression.py
(empty)

$ pytest tests/test_query_outcomes_regression.py -v
7 passed
```

### AC 2 — router and integration diffs since the epic base (`57f2d67`)

`git diff 57f2d67..HEAD -- tests/test_integration.py` is **empty**.

`git diff 57f2d67..HEAD -- tests/test_query_router.py` has **5 hunks** (all from STORY-007, `c734df9`):

| # | Hunk | Content | Classification |
|---|------|---------|----------------|
| 1 | `@@ -4,6 +4,7 @@` | `+from dataclasses import dataclass` | Import supporting hunk 3 |
| 2 | `@@ -20,7 +21,7 @@` | `from app.services.duplicate_checker import hash_prompt` → `import dedup_key, hash_prompt` | Import supporting hunk 3 |
| 3 | `@@ -34,6 +35,17 @@` | New `_Turn` frozen dataclass and `_key(user_id, prompt)` helper | Helper supporting hunks 4 and 5 |
| 4 | `@@ -53,11 +65,15 @@` | `_seed_duplicate()` adds `dedup_key=_key("juan@empresa.com", prompt)`, with the comment *"PRD-009 STORY-007: the lookup matches on dedup_key, so a seeded prior query carries the key /query derives… A row without one is a pre-PRD row and never matches (D6)."* | **Deviation: a seed-helper change, not a spy signature** |
| 5 | `@@ -315,9 +331,15 @@` | `_spy_duplicate(prompt)` → `_spy_duplicate(user_id, key)`, mapping the key back to the raw prompt through `raw_for_key`, with the comment *"PRD-009 Section 6.5 (STORY-007): signature only…"* | Spy wrapper signature (Section 6.5) |

**No status-code, body or row-count assertion changed.** Checked mechanically, excluding comment lines:

```
$ git diff 57f2d67..HEAD -U0 -- tests/test_query_router.py tests/test_integration.py \
    | grep -E '^[-+][^#]*(assert|status_code|json\(\))' | grep -vE '^[-+]\s*#'
(no output; grep exit 1)
```

Without the comment filter, the grep's one match is the added comment line *"assertion below unchanged -- a key derived from redacted text stays unmapped"* in hunk 5.

**About hunk 4.** The AC says the only changes are spy wrapper signatures. Hunk 4 is outside that literal wording. It is required, not incidental: once the lookup matches on `dedup_key`, a seeded prior row without a key is a pre-PRD row that never matches (D6). The seed has to carry the key the pipeline now writes so that the duplicate tests keep asserting the *same* outcome. What those tests assert is unchanged, and the change is commented with its decision. It was not reverted, because reverting it would turn the router's duplicate-block tests red.

### AC 3 — reporting invariance on a fixed seed

The seed goes through `POST /query` with bearer tokens:

| # | Caller | Outcome | Flags |
|---|---|---|---|
| 1 | Juan | 200 SUCCESS | `success=1` |
| 2 | Juan (same prompt) | 200 BLOCKED duplicate | `success=1`, `was_duplicate_blocked=1` |
| 3 | Juan | 200 BLOCKED pattern | `success=1`, `suspicious_pattern` |
| 4 | Juan | 200 BLOCKED model denial | `success=1`, `denied_permission` |
| 5 | María (Juan's prompt) | 200 SUCCESS | `success=1` |
| 6 | María | 502 | `success=0` |
| 7 | Juan | 500 (input redactor) | `success=0` |

Tests:
- `test_blocked_duplicates_counts_exactly_the_duplicate_blocked_rows`: the `was_duplicate_blocked = 1` ids are exactly `[row 2]`, and `/stats` `blocked_duplicates == 1`. Row 5, which repeats row 1's `prompt_hash`, and the pattern and denial blocks are not counted.
- `test_stats_and_summary_snapshot_report_the_same_figures_on_the_fixed_seed`:
  - figures `7 / 1 / 1 / 2 / 5`, and `success_rate == "71.4%"`
  - `/stats` equals `summary_snapshot()` on every compared figure, with `errors == {}`
  - the `StatsResponse` key set is unchanged
  - `snapshot.rows == list_audit_logs(...)`
- `test_console_completion_numerator_still_counts_denials_as_success`: the denial row is `success=True`, and `successful_queries == 5` (`admin_state.py::completion_figure`).
- `test_audit_query_entry_has_no_dedup_key_d5`: `dedup_key` is in neither `AuditQueryEntry.model_fields` nor `AuditRow.model_fields`, and in none of the seven `/audit` entries. The column is non-NULL underneath on every row.
- `test_every_new_row_prompt_hash_is_the_raw_prompt_hash`: `prompt_hash == hash_prompt(prompt)` in the DB and on `/audit` for all seven rows. Juan and María share `prompt_hash` while their `dedup_key`s differ.

**The one reporting-path diff, and why it is not a reporting change.** STORY-002 (`c8b303b`) added `'dedup_key', dedup_key` to `_SUMMARY_SQL`'s `rows` JSON. Those rows decode into `AuditLog`, which has had the field since the same commit, so the batched rows stay equal to `list_audit_logs()`. No figure reads the column, `grep -rn dedup_key chat_ui/` finds nothing, and `AuditRow` (the console projection) has no such field. `app/routers/admin.py`, `app/models/` and `chat_ui/` have no diff since `57f2d67`.

### AC 4 — two-instance smoke, unmodified

```
$ git diff 57f2d67..HEAD -- tests/test_two_instance_smoke.py
(empty)
$ pytest tests/test_two_instance_smoke.py -v
10 passed
```

The module has no skip path, because conftest exits when the libSQL dev server is unreachable, so it ran in full. That includes `test_concurrent_queries_from_both_instances_lose_no_rows`, which asserts `prompt_hash == hash_prompt(prompt_preview)`.

**Follow-up observation (not acted on; AC 4 requires the file unmodified).** `test_a_prompt_outside_the_window_is_not_blocked_by_the_other_instance` plants its stale row with `prompt_hash` only and no `dedup_key`. Under D6 that row could never match, whatever its age, so the test now passes without exercising the 24h window. The window itself is covered by `tests/test_duplicate_scope.py::test_success_at_24h01m_no_longer_blocks_the_same_prompt` and `tests/test_duplicate_checker.py`. A later change could plant the key so the cross-instance control means what its docstring says.

### AC 5 — no added round trip

`test_successful_query_issues_one_duplicate_lookup_and_one_audit_insert` wraps `app.db.database.get_connection` with a recording proxy. This is the idiom from `test_stats_router.py::test_stats_issues_one_database_round_trip_for_its_figures`, as the story's Technical Notes direct. The libSQL connection has no tracing hook, so this proxy is how "a spy on the client's `execute`" is realised. On one successful `/query`, it counts exactly two `audit_logs` statements: one `SELECT … dedup_key = ? …` and one `INSERT INTO audit_logs`.

- **Before the epic** (`git show 57f2d67:app/db/database.py`): `find_duplicate_timestamp` was one `SELECT timestamp FROM audit_logs WHERE prompt_hash = ? AND timestamp >= ? …` in one `_session()`, and the success arm made one `log_query` call. That is also 1 + 1.
- **Independent corroboration.** The smoke module's measurement printed during the full run: `POST /query : 3 statements (identity read, duplicate check, audit write)`.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_reporting_invariance.py` | CREATE | +383 |
| `.agents/plans/PRD-009-duplicate-rescoping/completed/STORY-009-outcome-regression-and-reporting-invariance.plan.md` | CREATE (archived) | +394 |
| `.agents/reports/PRD-009-duplicate-rescoping/STORY-009-outcome-regression-and-reporting-invariance.report.md` | CREATE | this file |

## Deviations from Plan

1. **Hunk count.** The plan said `test_query_router.py` has "4 hunks" but listed five items. `git diff` shows 5 hunks, all reported above.
2. **Assertion grep.** The plan's grep matched a *comment* containing the word "assertion". I added a comment-line filter; with it the grep is empty. The unfiltered match is reported above.
3. **Health check.** Booting the API needed `RBAC_ENABLED=false` and `DATABASE_URL` pointed at the local dev server. The reset test database has no users, and the RBAC bootstrap guard refuses to start without one. This was a boot-only check, and no configuration file changed.
4. **No `sys.path` insertion** for the `chat_ui.chat_ui.admin_models` import. The import resolves from `tests/` already, as in `tests/test_two_instance_smoke.py:73`.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_reporting_invariance.py` | `test_blocked_duplicates_counts_exactly_the_duplicate_blocked_rows`, `test_stats_and_summary_snapshot_report_the_same_figures_on_the_fixed_seed`, `test_console_completion_numerator_still_counts_denials_as_success`, `test_audit_query_entry_has_no_dedup_key_d5`, `test_every_new_row_prompt_hash_is_the_raw_prompt_hash`, `test_successful_query_issues_one_duplicate_lookup_and_one_audit_insert` |

## Acceptance Criteria

- [x] `git diff 9abef61..HEAD -- tests/test_query_outcomes_regression.py` is empty, and the module passes on the epic head
- [x] Router/integration diffs since the epic base reviewed. No status-code, body or row-count assertion changed, and every hunk is listed. Hunk 4 (seed helper) is reported as a deviation from the literal "only spy wrapper signatures"
- [x] New invariance test: `blocked_duplicates` counts exactly the `was_duplicate_blocked = 1` rows; `AuditQueryEntry` has no `dedup_key`; every new row's `prompt_hash == hash_prompt(prompt)`
- [x] `tests/test_two_instance_smoke.py` passes unmodified, including `prompt_hash == hash_prompt(prompt_preview)`
- [x] Exactly one duplicate-lookup statement and one audit insert per successful `/query`, as before the epic; full suite green
- [x] All tasks completed
- [x] Full pytest suite passes
- [x] No production code changed
- [x] Follows existing patterns
