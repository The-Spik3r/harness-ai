---
story: STORY-004
prd: PRD-006
plan: .agents/plans/PRD-006-admin-console/completed/STORY-004-threaded-database-read.plan.md
epic_branch: epic/PRD-006-admin-console
commit: e8c331e
status: COMPLETE
completed: 2026-08-28
---

# Implementation Report — STORY-004: AdminState.load() via asyncio.to_thread

**Plan**: `.agents/plans/PRD-006-admin-console/completed/STORY-004-threaded-database-read.plan.md`
**Epic Branch**: `epic/PRD-006-admin-console`
**Commit**: `e8c331e`

## Summary

`AdminState.load()` now reads. All ten read functions in `app/db/database.py` are driven from a module-level `_READS` table of `(field, label, function, kwargs)`, each offloaded with `asyncio.to_thread` — per call, because every read function opens its own `sqlite3` connection and a connection cannot cross threads. Results are collected into locals and committed to state in one `async with self` block after all ten return, which is what makes the fault arm's "rows and figures untouched" structural rather than disciplinary: there is no instant at which some fields are new and others old. A catch-all `except Exception` names the read that failed, a `finally` clears `loading` on both paths, and the gate is re-asserted inside the first lock because a background task's read outside it can be stale. Rows are built only through `to_audit_row`, keeping Risk 2's projection on the read path. Nothing under `app/` changed.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `format_refreshed_at()` + `REFRESHED_AT_FORMAT` | `chat_ui/chat_ui/admin_formatting.py` | ✅ |
| 2 | Ten named read imports, `REGISTER_ROW_LIMIT`, `LOAD_FAILED_MESSAGE`, `_READS` | `chat_ui/chat_ui/admin_state.py` | ✅ |
| 3 | `load()` body — offloaded reads, single commit, fault arm, `finally` | `chat_ui/chat_ui/admin_state.py` | ✅ |
| 4 | Direct-drive AC script (scratchpad) + committed pytest coverage | `tests/test_admin_state.py` | ✅ |
| 5 | Proof nothing under `app/` moved | — | ✅ (scoped, see Deviations) |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`app.main`) | ✅ |
| `chat_ui.chat_ui.admin_state` import | ✅ |
| Frontend lint | N/A — no JS package in `chat_ui` |
| Tests | ✅ 324 passed (full suite), 27 in `test_admin_state.py` |
| E2E | ✅ 6/6 (stubbed) + seeded-database run |
| `app/` untouched by PRD-006 | ✅ `git diff 577a285~1 HEAD -- app/` empty |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/admin_state.py` | UPDATE | +129/-13 |
| `chat_ui/chat_ui/admin_formatting.py` | UPDATE | +21/-1 |
| `tests/test_admin_state.py` | UPDATE | +327/-3 |
| `.agents/plans/.../completed/STORY-004-...plan.md` | CREATE (archived) | +510 |

## Deviations from Plan

1. **Tests were committed, not deferred to STORY-006.** The plan said "no test file (that is STORY-006)", but `implement.md` Phase 4 mandates tests for new code, and STORY-003 set the repo precedent by shipping `tests/test_admin_state.py` despite its own plan deferring it. Twelve load-path tests were added to that file; STORY-006 still owns the four-verdict cases and STORY-005's filter vars, and the file's docstring records that split.

2. **AC 7's literal check does not pass, for a reason that predates this story.** `git diff main --stat -- app/` reports `app/db/database.py` and `app/db/models.py` as changed. Those come from commit `3f553f2` (a PRD-004-era PII-column migration) which was already on this epic branch when it was cut — no PRD-006 commit touches `app/`, and neither does this one. The scoped check `git diff 577a285~1 HEAD -- app/` is empty. **This will fail STORY-020's "git diff main --stat shows nothing under app/" gate for an unrelated reason and needs a decision** — either rebase the epic onto a main that includes `3f553f2`, or restate STORY-020's check against the PRD-006 range.

3. **The module docstring of `admin_state.py` was updated.** It stated "Today it imports no database function at all", which the ten imports made false. Rewritten to explain why the imports are by name rather than via the module (`insert_audit_log` must stay unreachable).

4. **Incidental lockfile churn was reverted.** Importing Reflex reformatted `chat_ui/reflex.lock/{bun.lock,package.json}`; unrelated to this story, so not committed.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_admin_state.py` | `test_the_read_table_names_all_ten_database_functions`; `test_load_runs_all_ten_reads_off_the_event_loop`; `test_load_builds_audit_rows_newest_first_with_the_true_total`; `test_neither_preview_survives_the_read`; `test_loading_is_true_for_the_duration_and_false_after`; `test_load_stamps_the_time_of_the_read`; `test_a_failed_read_names_it_and_leaves_the_record_untouched`; `test_every_read_position_faults_the_same_way[first-read, last-read]`; `test_a_recovered_read_clears_the_fault`; `test_a_second_concurrent_load_is_refused_by_the_loading_guard`; `test_an_unauthenticated_load_calls_none_of_the_ten` |

The thread assertion is the one that carries AC 1: each stub records `threading.get_ident()` inside the call, and the test asserts the caller's own ident appears nowhere. A `grep` for `asyncio.to_thread` proves nothing about where the call ran.

## E2E Results

| Check | Result |
|-------|--------|
| Seeded database → 4 rows loaded, `total_recorded` = 4 | ✅ |
| Newest first, order preserved from `ORDER BY timestamp DESC` | ✅ verdicts `fault/denied/held/cleared`, relative times `9h–12h ago` |
| No stored preview string reaches the rows | ✅ three seeded sentinels absent |
| All ten figures equal a direct database call | ✅ |
| `list_audit_logs` patched to raise → fault named, rows and stamp untouched, `loading` False | ✅ |
| Recovery → error cleared, stamp advanced | ✅ |
| Two concurrent `load()`s → 10 reads, not 20 | ✅ |

## Skill Availability

`reflex-docs` and `reflex-process-management` remain **not installed** (`~/.claude/plugins` absent; `.agents/skills/` holds only `frontend-design`) — the same gap STORY-001/002/003 recorded. Per `chat_ui/AGENTS.md`'s rule ("rather than relying on memory"), the background-event contract, the `async with self` mutation rule and the existence of `rx.run_in_thread` were verified against current Reflex documentation via context7 `/websites/reflex_dev` during planning. `rx.run_in_thread` was rejected deliberately: AC 1 and PRD Section 6 both name `asyncio.to_thread`, which `chat_ui/chat_ui/state.py` already establishes as this codebase's offload.

## Acceptance Criteria

- [x] All ten read functions called, each inside `asyncio.to_thread(...)`, never on the event loop — asserted by thread ident, not by inspection
- [x] `list[AuditRow]` built through `to_audit_row(...)`, newest first, `total_recorded` from `count_audit_logs()`
- [x] `loading` True for the read's duration and False afterwards, including on the failure path
- [x] Catch-all `except Exception` sets an `error` naming the failed read, leaves rows and figures untouched, clears `loading`
- [x] `last_refreshed` set to the time of the read
- [x] Unauthenticated `load()` returns immediately and performs no database read
- [x] No file under `app/` modified by this story (see Deviation 2 on the inherited pre-existing delta)
- [x] All tasks completed
- [x] Backend and state modules import cleanly
- [x] Follows existing patterns (`state.py:_do_send`'s offload/`finally` shape, `admin_formatting.py`'s compute-once rule, named read-only imports)
