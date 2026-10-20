---
story: STORY-016
prd: PRD-013
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-016-console-usage-table.plan.md
epic_branch: epic/PRD-013-audit-and-usage-limits
commit: 6308359
status: COMPLETE
completed: 2026-10-19
---

# Implementation Report: STORY-016, Admin console: Usage table

**Plan**: `.agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-016-console-usage-table.plan.md`
**Epic Branch**: `epic/PRD-013-audit-and-usage-limits`
**Commit**: `6308359`

## Summary

The admin console has a third view, **Usage** (`/admin/usage`). It is one table of what each user has used today against their token budget, under the caption "Today, UTC".

- **One statement.** `usage_snapshot()` reads `usage_daily` for the database's `date('now')`. It left-joins `users` for role and overrides, and left-joins a grouped count of today's `audit_logs` rows matching `_BLOCKED_USAGE_LIMITS_WHERE`, the predicate `/stats` and the Register verdict use (interpolated, not retyped). It takes no parameters. The break-glass `admin`, which has no `users` row, is kept. It returns raw `UsageDay` facts and resolves no limit.
- **The gate's budget.** `to_usage_rows` builds the identity `resolve()` would build. For break-glass it uses the new public `BREAK_GLASS_USER_ID`/`BREAK_GLASS_ROLE` aliases. It then calls `usage_limits.limits_for`, so the table and the gate cannot disagree. **Used** is `tokens_today / budget`, where `tokens_today` is input + output + unsplit, exactly `_ADMIT_USAGE_SQL`'s expression. An unlimited budget reads "unlimited" and Used reads `—`. Rows are ordered by share, highest first, then unlimited rows, with ties in `user_id` order.
- **A separate read.** `load()` reads usage before the summary, in its own `try`, into its own `usage_rows`/`usage_error`. A failed usage read names itself ("Could not read the usage for today. …") on the Usage view and never touches `error`, so the Register and summary keep rendering. A failed summary read still refreshes usage. `_READS` and `SUMMARY_FIGURES` did not grow. `sign_out()`'s `reset()` clears both new vars.
- **The view.** Eight columns: User, Role, Requests, Input, Output, Budget, Used, **Denied**. Budget, Used and Denied state their meaning in a hover `title`. The table reuses the register's head, cell and rule treatment and ground colours only. It has no chart, meter, accent, history, sort or per-row action. An empty day shows "No one has sent anything today." with a line of direction and no grid. `fault_panel(message=…)` is reused for the usage fault.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Inventory grep and baseline (605 passed) | — | ✅ |
| 1 | `UsageDay`; `_USAGE_SNAPSHOT_SQL` + `usage_snapshot()` | `app/db/models.py`, `app/db/database.py` | ✅ |
| 2 | Storage tests (6) | `tests/test_usage_view.py` | ✅ |
| 3 | `UsageRow`; `BREAK_GLASS_*` aliases; model tests | `chat_ui/chat_ui/admin_models.py`, `app/services/identity.py`, `tests/test_admin_models.py` | ✅ |
| 4 | Usage copy (16 constants), census extended | `chat_ui/chat_ui/admin_copy.py`, `tests/test_copy.py` | ✅ |
| 5 | `_usage_identity`, `to_usage_rows` | `chat_ui/chat_ui/admin_formatting.py` | ✅ |
| 6 | Formatting tests (8) | `tests/test_usage_view.py` | ✅ |
| 7 | `usage_rows`, `usage_error`, `usage_state`, `USAGE_STATE_*`; usage read in `load()`; `_Reads`/autouse stub; namespace guard; state tests (10) | `chat_ui/chat_ui/admin_state.py`, `tests/test_admin_state.py`, `tests/test_usage_view.py` | ✅ |
| 8 | `components/usage.py`; `fault_panel(message=)`; `ROUTE_USAGE`/`VIEW_USAGE` + third switch link; page registration; component tests (10 + parametrized); shell probes; palette glob | `chat_ui/chat_ui/components/usage.py`, `components/admin_shell.py`, `chat_ui.py`, `tests/test_usage_view.py`, `tests/test_admin_shell.py`, `tests/test_admin_palette.py` | ✅ |
| 9 | Full suite and regression gates | — | ✅ |
| 10 | E2E in the running console | — | ✅ |
| 11 | Commit, report, story status | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| App import (`from app.main import app`) | ✅ |
| Frontend lint | n/a (Reflex app: no npm lint script; the build probes in `test_usage_view.py`/`test_admin_shell.py` compile every factory) |
| Tests | ✅ full suite 3807 passed / 27 skipped on the first run. The rerun on the final code (after the E2E fixes) had 3805 passed with 2 failed + 1 error, all shared-DB flakes (`STREAM_EXPIRED`, connect error 10060, PRE-PRD-017) in `test_duplicate_scope.py`, `test_query_pipeline_audit_fields.py` and `test_query_pipeline_multiturn.py`. Those three files then passed on rerun (85 passed). The UI suites after the E2E fixes: 908 passed |
| Regression files unchanged | ✅ `test_query_outcomes_regression.py`, `test_chat_outcomes_regression.py`, `test_duplicate_scope.py`, `test_pii_characterization.py`, `test_untouched_app.py`, `test_register.py`, `test_summary.py`: empty diff |
| E2E | ✅ 10/10 |

### E2E (live, `reflex run --env prod`, `USAGE_DAILY_TOKEN_BUDGET=*=1000000,admin=unlimited`)

The shared `harness-libsql-dev` container was reset twice mid-run by another process (see Deviations), so the E2E finished against a throwaway container of the same image on port 8086. The data was seeded through the real writers (`insert_user`, `set_user_limits`, `admit_usage`, `charge_usage`, `insert_audit_log`).

- [x] The masthead reads Register · Summary · Usage. Usage links to `/admin/usage` and carries `aria-current="page"` there. Tab focus on the link shows the 2px `:focus-visible` ring.
- [x] The caption "Today, UTC" sits above the table with the Refreshed stamp. The table's accessible name is "Today, UTC".
- [x] Rows appear in share order. e2e-bob reads user, 1, 0, 0, **5,000** (override), **104.2%** (unsplit only), **2** denied. e2e-ana reads user, 3, 2,140, 312, **1,000,000** (role default), 0.2%, 0. admin reads **admin**, 1, 0, 0, **unlimited**, **—**, 0.
- [x] The budgets equal `limits_for` for the same identities (5000 / 1000000 / None).
- [x] No colour, bar or meter on the over-budget row. Rows have a transparent background, `cursor: auto`, no hover rule and no click handler. No cell truncates at 1920px.
- [x] Empty day: rows removed, then Refresh shows "No one has sent anything today." plus its direction line, and no grid.
- [x] **AC 4, isolated arm, live.** With a good row loaded, `DROP TABLE usage_daily` (the summary never reads it) and Refresh. The Usage view shows the fault panel "Could not read the usage for today. Nothing on screen has changed. …" over the last good row. Summary and Register each render freshly refreshed data with **no** fault panel. The plan expected this arm to be unit-test-only. The isolated database made it possible live.
- [x] Sign out leaves no usage row in the DOM, only the gate. Sign in reloads the rows, and the recovered read clears its fault.
- [x] 390px: the table scrolls sideways inside `.hx-scroll` (956px content in a 390px container) with no page scroll (`scrollWidth == 390`). The view switch takes its own masthead row (see Deviations).
- [x] Dark ground (the console's own switch): the table, caption and empty state are legible, using existing ink only.

Cleanup: Reflex stopped, the throwaway container removed, the e2e rows deleted from the shared dev DB, `chat_ui/reflex.lock/package.json` reverted and the generated `package-lock.json` deleted.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/models.py` | UPDATE | +26 |
| `app/db/database.py` | UPDATE | +66 |
| `app/services/identity.py` | UPDATE | +7 |
| `chat_ui/chat_ui/admin_models.py` | UPDATE | +22/-1 |
| `chat_ui/chat_ui/admin_copy.py` | UPDATE | +53/-2 |
| `chat_ui/chat_ui/admin_formatting.py` | UPDATE | +85/-3 |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | +82/-2 |
| `chat_ui/chat_ui/components/usage.py` | CREATE | +277 |
| `chat_ui/chat_ui/components/admin_shell.py` | UPDATE | +51/-7 |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | +19/-5 |
| `chat_ui/chat_ui/theme.py` | UPDATE | +6 |
| `tests/test_usage_view.py` | CREATE | +888 |
| `tests/test_admin_state.py` | UPDATE | +38/-1 |
| `tests/test_admin_shell.py` | UPDATE | +36/-7 |
| `tests/test_admin_models.py` | UPDATE | +34/-1 |
| `tests/test_copy.py` | UPDATE | +34 |
| `tests/test_admin_palette.py` | UPDATE | +2 |

## Deviations from Plan

1. **`tests/test_copy.py` extended** (not in the plan's file list). Its admin-copy census asserts every `admin_copy` constant by name and fails on an unlisted one. The 16 new constants were added to both the assertions and the census set.
2. **`tests/test_admin_palette.py` extended.** Its glob listed `register.py`/`summary.py` by name, so `components/usage.py` was added to keep the chat-only-ink and hex guards covering every admin module.
3. **`tests/test_admin_state.py` gained an autouse `_no_usage_read` fixture**, besides the `_Reads.install` stub the plan named. Two other helpers in that file replace only `summary_snapshot`, and without the fixture their `load()` calls would have reached the database for usage.
4. **Grid and table width (E2E finding).** The plan's `minmax(8rem, 1fr)` User track stretched the table to 1,896px at 1920 and put Role about 1,100px from the user's name. User is now `minmax(8rem, 16rem)` and the table is `width: fit-content`, so the rules end at the last column. Budget/Used tracks are 7rem/5.5rem rather than 8rem/5rem. `_MIN_WIDTH` = 56.75rem, with the arithmetic in the comment.
5. **Masthead at 390px (E2E finding; touches `theme.py`, not in the plan).** The third link made the admin meta cluster 30px wider than a 390px screen and pushed the sign-out control off the edge. The admin masthead's cluster now wraps, the view switch carries `hx-view-switch`, and `theme.GLOBAL_CSS`'s existing `max-width: 40rem` block gives it `flex-basis: 100%` and drops the leading rule on the control that starts the next row. The chat header does not use the class, and a test pins both facts. Wide screens are unchanged (the meta stays one 25px row).
6. **Two E2E steps went beyond the plan.** AC 4's isolated arm was proved live (`DROP TABLE usage_daily` on a throwaway database). The planned E2E against the shared dev container became impossible: another process reset it twice mid-run (the RBAC bootstrap check failed on restart, with 0 rows in every table). The E2E moved to a throwaway `harness-libsql-e2e016` container of the same image, removed afterwards.
7. **Phase 2 working tree.** `pre-prds/README.md` (modified) and `pre-prds/PRE-PRD-017-test-suite-db-isolation.md` (untracked) were present and unrelated. They were left untouched and unstaged rather than stashed, and only this story's files were staged.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_usage_view.py` (new) | Storage: empty day; today's counters and overrides; break-glass kept; today-only denial count; **one statement**; shared `/stats` predicate. Formatting: override / role default / unlimited (AC 2); table equals gate; Used counts unsplit; over budget is a number; share order; orphan row; all strings; zero reads "0". State: commit rows; empty state; **failed usage read names itself, Register/summary untouched**; failed summary still refreshes usage; first failure is not "empty"; recovery clears fault; **sign-out clears**; unauthenticated load reads nothing; not a summary read; vars declared, state computed. Component: builds without chat modules; heads, titles, caption and accessible name; empty state without grid; own fault panel; **no chart / history / row action** (code-only AST and rendered row); ground colours only; every string from `admin_copy` (14 parametrized); no chat or sibling-view import (6 parametrized); scrolls in its container; view switch row at phone width |
| `tests/test_admin_models.py` | `UsageRow` field order; all `str`; no preview field |
| `tests/test_admin_state.py` | No path to the usage counters from `admin_state`/`admin_formatting` |
| `tests/test_admin_shell.py` | `ROUTE_USAGE`; usage masthead and page build; every switch carries three labels and marks itself current; three distinct view keys; `admin/usage` page registered and out of the sitemap |

## Acceptance Criteria

- [x] Given users who sent requests today, when the console loads, then the Usage table shows one row per such user with user, role, requests, input tokens, output tokens, budget, share of budget used and refusals today, and its caption states the window ("Today, UTC").
- [x] Given a user with a per-user override, a user on the role default and a user whose budget is `unlimited`, when the table renders, then each shows its effective budget, and the unlimited row shows no share.
- [x] Given nobody has sent anything today, when the table renders, then it shows "No one has sent anything today." and no empty grid.
- [x] Given the usage read failing, when the console loads, then the failure is named under its own read label and the summary and Register still render; given `sign_out()`, then the usage rows are cleared.
- [x] Given `usage_snapshot()`, when it is called, then it issues one statement, and the component contains no chart, no history control and no per-row action.

## For the reviewer

- **D-A (third view)** was the user's choice at plan time. **D-F (share order)** is the one structural statement the table makes, and the Used head's title says so. Overrule here if you prefer `user_id` order.
- Each console load now makes **two** round trips (summary + usage) instead of one. The story requires the separate read ("outside `summary_snapshot`") and F16 requires its own label. This is stated in `load()`'s docstring.
