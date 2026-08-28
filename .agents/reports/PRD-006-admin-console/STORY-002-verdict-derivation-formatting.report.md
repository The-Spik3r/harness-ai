---
story: STORY-002
prd: PRD-006
plan: .agents/plans/PRD-006-admin-console/completed/STORY-002-verdict-derivation-formatting.plan.md
epic_branch: epic/PRD-006-admin-console
commit: 0fe6c69
status: COMPLETE
completed: 2026-08-28
---

# Implementation Report — STORY-002: admin_formatting.py: verdict derivation, relative time, device and shares

**Plan**: `.agents/plans/PRD-006-admin-console/completed/STORY-002-verdict-derivation-formatting.plan.md`
**Epic Branch**: `epic/PRD-006-admin-console`
**Commit**: `0fe6c69`

## Summary

Created `chat_ui/chat_ui/admin_formatting.py`, the module that computes every displayed value on a register row once, in Python, when the row is built (PRD-006 Section 6). It holds the four verdict constants and `derive_verdict` — PRD Section 6's table applied as a precedence (held → denied → fault → cleared) with the ordering and the Risk 3 reasoning stated in comments — plus `to_audit_row`, which is the Risk 2 boundary and enumerates every field it copies so neither preview is read, `format_share` with a placeholder rather than a false `"0.0%"` on an empty table, and the private timestamp / device / entity helpers. `chat_ui/chat_ui/formatting.py` gained a shared `_bucket` helper and `humanize_compact`, so the register's `"2m ago"` and the chat's `"2 minutes ago"` read one threshold table instead of two; `_humanize` keeps its name and byte-identical output and `tests/test_copy.py` is unchanged and green. Nothing under `app/` was touched.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Share the relative-time thresholds instead of duplicating them | `chat_ui/chat_ui/formatting.py` | ✅ |
| 2 | Verdict constants, `derive_verdict`, `to_audit_row`, `format_share`, helpers | `chat_ui/chat_ui/admin_formatting.py` | ✅ |
| 3 | Tests across every AC and every degrade arm | `tests/test_admin_formatting.py` | ✅ |
| 4 | Prove the blast radius | — (verification) | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| New tests (`tests/test_admin_formatting.py`) | ✅ 27 passed |
| Full suite (`python -m pytest tests/ -q`) | ✅ 297 passed (270 before + 27 new) |
| `tests/test_copy.py` green **and** unmodified | ✅ 17 passed, `git diff` empty |
| Eight PRD Section 15 pinned test files unmodified | ✅ `git diff --stat` empty |
| `git diff --stat -- app/` | ✅ empty |
| `admin_formatting.py` does not pull in `reflex` | ✅ asserted via `sys.modules` after import |
| No `preview` reference outside the docstring | ✅ 3 hits, all prose explaining the absence |
| E2E | ✅ 4/4 |

No frontend lint step and no backend-import step apply: `chat_ui` is Reflex/Python with no JS package, and this story adds no route, component or FastAPI wiring. No Reflex compile/run cycle was needed, so `reflex-process-management` did not apply.

### E2E detail

| # | Check | Result |
|---|-------|--------|
| 1 | An `AuditLog` per row of PRD Section 6's table | ✅ `held` / `denied` / `fault` / `cleared` |
| 2 | Round-trip `list_audit_logs()` → `to_audit_row()` | ✅ 5 rows built from a real database read; 6 preview values present on the source `AuditLog`s, 0 in the produced rows |
| 3 | `format_share` over a summary's worth of numbers | ✅ `13.0%` / `1.2%` / `0.0%`, and `format_share(3, 0)` → placeholder, no traceback |
| 4 | The chat's duplicate card after the shared-threshold refactor | ✅ still `"Already sent 2 minutes ago (…)"`; `test_copy.py` 17 passed |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/admin_formatting.py` | CREATE | +175 |
| `tests/test_admin_formatting.py` | CREATE | +287 |
| `chat_ui/chat_ui/formatting.py` | UPDATE | +32/-10 |

## Deviations from Plan

1. **E2E 2 ran against a seeded temporary database, not the repo's `harness_ai.db`.** The plan's command reads the repo database, which holds **0 rows** (`count_audit_logs()` → 0), so the literal command printed an empty list and proved nothing. The check was re-run against a temporary SQLite file seeded through the real `insert_audit_log` with one row per verdict and preview text on six of them, then read back through the real `list_audit_logs`. That exercises the same code path the plan intended and makes the Risk 2 assertion meaningful — the version against an empty database could not have detected a leak.
2. **`formatting.py` grew a named `_DAY_BUCKET` constant** alongside `_BUCKETS`, rather than the plan's inline `seconds // 86400` fallthrough. The day case has no upper bound, so it does not fit the same tuple shape; naming it keeps the two spellings symmetric and the fallthrough readable.
3. **Four tests beyond the plan's list** — `test_pii_indicator_combines_both_sides` (AC 3's combined indicator plus the split that survives for the disclosure), `test_error_message_reaches_the_row_for_a_fault` (the field `AuditQueryEntry` drops, and the console's clearest gain over `curl /audit`), `test_to_audit_row_defaults_now_to_the_current_clock` (STORY-004 may omit `now`), and `test_naive_now_degrades_instead_of_raising` (plan decision 9's guarantee, previously unasserted). Also `test_short_device_is_not_truncated` and `test_future_timestamp_reads_as_just_now`, covering decision 8's "only truncate when it buys something" and decision 10's clock-skew arm.
4. **`chat_ui/reflex.lock/` restored, not committed** — importing the `chat_ui` package makes Reflex rewrite `bun.lock` and `package.json`. Same interpreter side effect STORY-001 recorded (its Deviation 5); reverted with `git checkout --` and kept out of the commit.
5. **The report and the story/index updates ride in a follow-up chore commit**, following the STORY-001 precedent (`faee203`): the report carries the story commit's SHA, which cannot exist before that commit does.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_admin_formatting.py` | **Verdicts**: `test_each_verdict_derives_from_its_condition`, `test_verdict_precedence_is_deterministic_when_conditions_overlap`, `test_fault_does_not_branch_on_model_used`, `test_verdict_constants_are_the_registers_four`. **Projection**: `test_to_audit_row_populates_every_field`, `test_pii_indicator_combines_both_sides`, `test_to_audit_row_carries_no_preview_value`, `test_short_device_is_not_truncated`, `test_null_columns_render_the_absent_mark`, `test_tokens_used_zero_is_not_the_absent_mark`, `test_error_message_reaches_the_row_for_a_fault`, `test_to_audit_row_defaults_now_to_the_current_clock`. **Relative time**: `test_relative_time_compact_at_every_boundary` (9 parametrized boundaries), `test_future_timestamp_reads_as_just_now`, `test_missing_and_unparseable_timestamp_degrade`, `test_naive_now_degrades_instead_of_raising`. **Shares**: `test_format_share_placeholder_and_value`, `test_format_share_never_raises_on_a_bad_denominator`, `test_format_share_matches_the_stats_router_number_format`. 27 cases in total. |

## Acceptance Criteria

- [x] `derive_verdict(log)` returns exactly one of `cleared` / `held` / `denied` / `fault`, in PRD Section 6's precedence
- [x] A duplicate-blocked *and* pattern-flagged row is deterministic; the precedence is stated in a module comment above the constants
- [x] `to_audit_row(log, now)` returns a fully-populated `AuditRow` — relative time (`"2m ago"`), absolute timestamp, truncated and full device, combined PII indicator, `pii_entities` parsed from the stored TEXT form
- [x] Neither preview value from the source `AuditLog` is present on the returned row *(asserted on a hand-built row and on a real database read)*
- [x] `format_share(count, total)` returns a defined placeholder at `total == 0` instead of raising; otherwise the share, matching the `/stats` router's number format
- [x] A failed row carrying `model_used` still derives **fault**; the function never branches on that field (Risk 3)
- [x] All tasks completed
- [x] Backend/app untouched: `git diff --stat -- app/` empty
- [x] Full suite passes (297); PRD Section 15's eight pinned test files unmodified
- [x] Follows existing patterns (`chat_ui/chat_ui/formatting.py`, `chat_ui/chat_ui/admin_models.py`, `app/routers/admin.py`)

## Notes Forward

- **STORY-004** calls `to_audit_row(log, now)` inside the `asyncio.to_thread` read; pass one `datetime.now(timezone.utc)` for the whole batch so a hundred rows share one clock read rather than drifting across the list.
- **STORY-011 / STORY-013** import `VERDICT_*` and `VERDICTS` from this module for the `rx.match` keys and the filter values — do not re-spell the strings. `AuditRow.verdict` still defaults to `""`, so the `rx.match` needs its default arm (STORY-001's note stands).
- **STORY-008** owns `admin_copy.py`. `SHARE_UNDEFINED` is the candidate to re-home there if the summary wants different wording for an undefined ratio; `VALUE_ABSENT` and the `VERDICT_*` values are data, not copy, and stay here.
- **STORY-015** renders `format_share` beside each blocked count; `format_share(0, n)` is `"0.0%"` and only an absent/zero/negative denominator yields the placeholder.
- The repo's `harness_ai.db` is empty, so any story validating against "real data" must seed first — see Deviation 1.
