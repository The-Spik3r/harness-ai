---
story: STORY-015
prd: PRD-006
plan: .agents/plans/PRD-006-admin-console/completed/STORY-015-summary-tally-sheet.plan.md
epic_branch: epic/PRD-006-admin-console
commit: d8a9a9d
status: COMPLETE
completed: 2026-08-31
---

# Implementation Report — STORY-015: summary.py, nine StatsResponse figures as a ruled tally sheet

**Plan**: `.agents/plans/PRD-006-admin-console/completed/STORY-015-summary-tally-sheet.plan.md`
**Epic Branch**: `epic/PRD-006-admin-console`
**Commit**: `d8a9a9d`

## Summary

`/admin/stats` rendered an empty `rx.fragment()` before this story. It now renders
`components/summary.py`: a ruled tally sheet in PRD-006 Section 6.1's three
blocks — Traffic, Who and what, Personal data — carrying all nine
`StatsResponse` figures, with `blocked_duplicates` and `blocked_suspicious`
indented beneath `total_queries` because they are a subset of it.

Nothing is computed in the component. Every figure is a `SummaryFigure` (declared
by STORY-001 and unused until now) assembled in five `AdminState` computed vars
out of STORY-004's counts, STORY-008's copy and STORY-002's `format_count` /
`format_share`. That is what makes AC 8 true by construction: on a total of 0,
`format_share` returns its placeholder rather than dividing, and the division
never reaches a component that could only receive a Var.

The completion figure is `StatsResponse.success_rate` rendered honestly. Its
share is that field's exact value at `app/routers/admin.py`'s own rounding, and
its numerator sits beside it — under `FIGURE_COMPLETION_LABEL`
("Completed without error (blocked queries included)") with
`FIGURE_COMPLETION_NOTE` beneath it. The label was fixed; the computation was
not, because `app/` is out of scope and a truthful metric is PRD Section 13's.

No new copy constant, no new theme token, no new dependency, and no change under
`app/`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `RANKED_LIMIT`, passed to the three ranked reads | `chat_ui/chat_ui/admin_state.py` | ✅ |
| 2 | `SUMMARY_STATE_*` keys and the `summary_state` var | `chat_ui/chat_ui/admin_state.py` | ✅ |
| 3 | The five figure computed vars and their two builders | `chat_ui/chat_ui/admin_state.py` | ✅ |
| 4 | The tally sheet | `chat_ui/chat_ui/components/summary.py` | ✅ |
| 5 | `admin_summary_page` renders `summary()` | `chat_ui/chat_ui/chat_ui.py` | ✅ |
| 6 | State tests over the nine figures | `tests/test_admin_state.py` | ✅ |
| 7 | Build probe | `tests/test_summary.py` | ✅ |
| 8 | Source and palette assertions | `tests/test_summary.py` | ✅ |
| 9 | Compile, run, and the design self-critique | — | ✅ |
| 10 | Prove `app/` untouched | — | ✅ (with a finding, below) |

## Validation Results

| Check | Result |
|-------|--------|
| `reflex compile --dry` | ✅ compiled in 2.0s, no error |
| Prod server + `/admin/stats` | ✅ renders authenticated, no console error or warning |
| `tests/test_summary.py` | ✅ 60 passed |
| `tests/test_admin_state.py` | ✅ 96 passed (80 before, +16) |
| Full suite | ✅ 706 passed |
| PRD-001/003/004 test files | ✅ unmodified and passing |
| `git diff main -- app/models/schemas.py` | ✅ empty — `StatsResponse` unchanged |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/components/summary.py` | CREATE | +454 |
| `tests/test_summary.py` | CREATE | +531 |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | +243/-4 |
| `tests/test_admin_state.py` | UPDATE | +279/-3 |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | +4/-4 |

## Deviations from Plan

**1. Where the nine figure labels are asserted.** The plan's Task 7 said the
component test would assert each of the nine `FIGURE_*_LABEL` strings appears in
the rendered output. It cannot: the labels live on `SummaryFigure` objects built
in state, so the compiled sheet carries `total_figure?.["label"]` rather than the
words — which is the derived-once rule working, not a gap. The nine labels are
asserted in `tests/test_admin_state.py` (`test_the_sheet_carries_all_nine_stats_response_figures`,
by set equality so a tenth fails as loudly as a missing one), and
`tests/test_summary.py` asserts the sheet binds to all five figure vars and to
each of the five rendered fields. The two halves together carry AC 1.

**2. The indent guard is a source count, not a render assertion.** The compiled
output cannot say which `padding_left` belonged to which figure, so
`test_only_the_blocked_figures_are_indented` asserts in the source that
`indent=theme.STAMP_X` appears exactly once and that it is
`rx.foreach(AdminState.blocked_figures, _indented_figure)` that carries it.

**3. The `figure.items` guard is an AST walk, not a regex.** Both the module
docstring and `_ranked_items` name the attribute form in order to warn about it,
and a text guard that cannot tell a warning from a use would be answered by
deleting the warning.

**4. Two changes from the live self-critique (Task 9), neither in the plan.**
- The value column is `flex="1"` with a minimum, not a fixed minimum alone: at a
  380px viewport a wrapped value kept its `min_width` and landed stranded in the
  middle of the row, reading as a third column. It now stays on the same right
  edge whether or not the row wraps.
- `_figure_note` carries no rule of its own. It is the last thing in its block
  and the next block's `border_top` already draws that boundary, so its hairline
  put two lines a few pixels apart doing one job. This is the accessory the
  **frontend-design** skill's last look in the mirror took off.

## Finding: `app/` already differs from `main` on this branch

`git diff main --stat -- app/` is **not** empty, and this story is not the cause:

```
 app/db/database.py | 14 +++++++++++++-
 app/db/models.py   | 11 +++++++++++
```

Both come from commit `3f553f2` ("feat(chat-ui): implement PII column migration
and enhance duplicate message formatting", 2026-08-28) — a PRD-004-era commit
that predates every PRD-006 story. It adds `AUDIT_LOGS_ADDED_COLUMNS` and the
`init_db()` ALTER path for PRD-003's three PII columns.

It matters because PRD-006 Section 11 makes "`git diff main --stat` shows no file
under `app/` changed" a quality indicator, and **STORY-020's whole job is
asserting it**. That story will fail against the branch as it stands unless the
bar is read as "no file under `app/` changed *by PRD-006*", or `3f553f2` is
landed on `main` first. Flagged here rather than resolved: rewriting another
PRD's commit is outside this story.

AC 9 itself is unaffected — `app/models/schemas.py` is untouched and
`StatsResponse` is unchanged.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_summary.py` (new, 60 cases) | module imports; every factory builds; no chat module loaded; each of the five figure vars reaches the sheet; each of the five figure fields renders; the three block headings; only the blocked figures indent; the completion note is present; the sheet never says "success rate"; the scope note states the two windows; the ranked lists state their cut; the empty sheet says why; the body chooses between sheet and panel; no colour outside the ground tokens; no verdict ink; no tint; no card (no shadow, radius or fill); no literal hex; every string from `admin_copy` and no copy value as a literal; no chat import; no chat-only colour; `FONT_BODY` used exactly 4× and only on explanatory lines; `FONT_DATA` dominant; ranked items read by subscript; no focus reset; scrolls in its own container; wraps on a narrow viewport |
| `tests/test_admin_state.py` (+16 cases) | all nine `StatsResponse` figures by set equality; every figure states its scope; the blocked pair is a count and a share; the blocked pair is exactly what indents; the completion figure is `success_rate`'s value under a true label; the completion label is not an answer rate; each ranked figure states its cut and carries its items; the ranked reads ask for the number the surface states; PII telemetry reaches the sheet; a total of 0 renders the placeholder rather than raising; an unshared figure carries no share; `summary_state` reads a failed read before an empty table; `summary_state` is empty only when nothing is recorded; sign-out empties the sheet |

## End-to-End Verification

| Check | Result |
|-------|--------|
| `/admin/stats` unauthenticated → gate, no data | ✅ |
| Authenticated against the seeded db → nine figures, each with its scope | ✅ |
| Blocked figures indented, each a count *and* a share (`1`, `16.7% of all queries`) | ✅ |
| Completion figure reads as a completion count; "success rate" nowhere on the page | ✅ |
| `pii_detected_queries` (`2`, `33.3%`) and `top_pii_entities` both visible | ✅ |
| Ranked lists render with `top 5` stated | ✅ |
| Empty database → "Nothing to summarize." panel, no exception | ✅ (server restarted against a fresh db) |
| First failed read does not render as "Nothing to summarize" | ✅ (unit test — `summary_state` returns the fault key; not exercised in the browser) |
| Sign out → the gate returns | ✅ |
| No `prompt_preview` / `response_preview` in the rendered sheet | ✅ |
| No console error or warning on the page | ✅ |

## Acceptance Criteria

- [x] All nine `StatsResponse` figures appear when `/admin/stats` renders authenticated
- [x] `blocked_duplicates` and `blocked_suspicious` are indented beneath `total_queries`, each as a count and as a share
- [x] The completion figure's label says it counts rows the pipeline completed without raising, blocked rows included — and never reads as "success rate"
- [x] Every figure carries its scope, stated distinctly from the register's last-100 window
- [x] `pii_detected_queries` and `top_pii_entities` are both visible
- [x] `top_models` and `top_users` render as ranked lists with the "top 5" cut stated
- [x] No card, no fill and no accent colour — only rules, type and the ground tokens
- [x] A total of 0 renders every share's placeholder rather than raising
- [x] `app/models/schemas.py` is unchanged; `StatsResponse` untouched
- [x] All tasks completed
- [x] Full pytest suite passes with PRD-001/003/004's test files unmodified
- [x] Follows existing patterns
