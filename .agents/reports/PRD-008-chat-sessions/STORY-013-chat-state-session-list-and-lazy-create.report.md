---
story: STORY-013
prd: PRD-008
plan: .agents/plans/PRD-008-chat-sessions/completed/STORY-013-chat-state-session-list-and-lazy-create.plan.md
epic_branch: epic/PRD-008-chat-sessions
commit: ba43c5c
status: COMPLETE
completed: 2026-09-05
---

# Implementation Report — STORY-013: ChatState holds the session list, creates lazily on first send, and passes session_id to run_query

**Plan**: `.agents/plans/PRD-008-chat-sessions/completed/STORY-013-chat-state-session-list-and-lazy-create.plan.md`
**Epic Branch**: `epic/PRD-008-chat-sessions`
**Commit**: `ba43c5c`

## Summary

`ChatState` now knows which conversation a send belongs to. It declares `sessions`, `active_session_id` and `sessions_error`; `login()` loads the caller's session list through `chat_sessions.list_for(identity)` on a worker thread; `_do_send` creates a session on the **first** send of a chat and never on page load; and `run_query(...)` receives `session_id=` so the audit row names the conversation on every outcome. No transcript row is written or read — STORY-014 and STORY-015 own those.

Two structural decisions carried the work, both verified against the pinned `reflex==0.9.6.post1` tree rather than recalled:

**`login()` became a plain `async` handler, not a background one.** AC 2 requires the rail's data to be in state *when `login()` completes*. Reflex's `_no_chain_background_task` (`reflex/state.py:102-133`) makes a background handler impossible to call from another handler — it can only be returned as a follow-up event, which lands after `login()` has already finished. A non-background async handler holds the exclusive state lock for its whole duration (`reflex/app.py:1427-1429`, *"No other event handler can modify the state while in this context"*) and receives the real state rather than a `StateProxy` (`reflex/istate/proxy.py:38-52`), so mutations are direct and an `async with self` there would deadlock. This is the opposite of the rule in `_do_send`, which *is* a background task — the asymmetry is now documented in both docstrings so it is not "fixed" into a bug later.

**The lazy create sits inside the existing `try:`**, after the user's bubble is appended and before the pipeline call. Placement, not a second `try/finally`, is what keeps PRD-004 Risk 3's guarantee that `pending` clears on every path.

The flag-off behaviour required writing no code: `chat_sessions.create` returns `None` and `list_for` returns `[]` when `CHAT_HISTORY_ENABLED` is false, so `ChatState` never names the flag — enforced by the AST guard in `tests/test_chat_sessions.py:1281` and pinned again locally.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Imports, three state vars, docstring on the client-visible id | `chat_ui/chat_ui/state.py` | ✅ |
| 2 | `login()` → async, offloaded session-list load, one shared clock read | `chat_ui/chat_ui/state.py` | ✅ |
| 3 | Lazy `chat_sessions.create` in `_do_send`; `session_id=` on `run_query` | `chat_ui/chat_ui/state.py` | ✅ |
| 4 | Six `_fake_run_query` signatures absorb `session_id` | `tests/test_chat_state.py` | ✅ |
| 5 | Five `login` tests converted to async | `tests/test_chat_state.py` | ✅ |
| 6 | Twelve new tests (15 cases with parametrization) | `tests/test_chat_state.py` | ✅ |
| 7 | One `_fake_run_query` signature | `tests/test_rbac.py` | ✅ |
| 8 | `reflex compile --dry` | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `python -c "import chat_ui.chat_ui.state"` | ✅ |
| `reflex compile --dry` (from `chat_ui/`) | ✅ "App compiled successfully in 6.266 seconds" |
| `tests/test_chat_state.py` | ✅ 54 passed (was 39) |
| `tests/test_rbac.py` | ✅ passed, assertions unchanged |
| Structural guards (`test_chat_sessions`, `test_session_ownership`, `test_untouched_app`) | ✅ 156 passed |
| Full suite | ✅ **1454 passed**, 0 failed |
| E2E script (real pipeline, real store) | ✅ 30/30 checks |
| E2E live boot + browser | ✅ sign-in, send, audit join |
| Mutation checks | ✅ 3/3 — see below |

### Mutation checks

The new tests were verified to have teeth rather than assumed to:

| Mutation | Result |
|---|---|
| `session_id=session_id or None` → `session_id=None` | ✅ 6 tests fail |
| `if not session_id:` → `if True:` (create on every send) | ✅ `test_second_send_reuses_the_session_and_creates_no_second_row` fails |
| `session_id=session_id or None` → `session_id=session_id` | ⚠️ **passed** — see Deviations; the comment in the code was corrected rather than the claim left standing |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/state.py` | UPDATE | +93 / -3 |
| `tests/test_chat_state.py` | UPDATE | +374 / -22 |
| `tests/test_rbac.py` | UPDATE | +1 / -1 |
| `tests/test_pii_redaction_integration.py` | UPDATE | +6 / -1 |

## Deviations from Plan

| Plan said | Implementation did | Why |
|---|---|---|
| `or None` on the `run_query` call is "load-bearing" | Kept the guard, **corrected the comment** to say it is defensive and not currently reachable | A mutation check disproved the plan's claim: when `active_session_id` is `""` the create always runs, and it returns either a real id or `None` — never `""`. Leaving a false "load-bearing" comment in the code would mislead the next reader, so the code now states what is actually true and why the guard is still worth keeping. |
| — | `tests/test_pii_redaction_integration.py:291` regex widened to `^(?:async )?def (test_\w+)` | Unplanned and required. That census resolves its baseline from `merge-base main HEAD`, so it saw the five `def` → `async def` login conversions as deletions. The regex was blind to `async def` entirely — it could not have caught the deletion of any async test, and most of `test_chat_state.py` is async. Widening it strengthens the guard rather than working around it. The sibling census in `test_untouched_app.py:88` has the identical blind spot but passes, because its pinned baseline `d3e6279` predates PRD-005's login rework and never contained these names; it was left untouched as out of scope. |
| — | `_slow_to_thread` in `test_chat_state_concurrent_send_guard` now dispatches on the callable | The blanket `to_thread` patch began intercepting the lazy create as well as the pipeline call, so `called_count` counted 2 and a `QuerySuccessResponse` was fed into `active_session_id`. The fake now counts only `run_query`, so the assertion keeps meaning "the pipeline ran once". The test's name, premise and other assertions are unchanged. |
| Test 2 would order the rail by touching the newer session | Backdates the older session instead | Both rows are created inside the same second and `updated_at` is a TEXT timestamp, so a touch left the order a coin flip — the arbitrary-tie defect PRD-006 §13 already records. Backdating makes the ordering a fact. |
| `self.sessions` not mutated in `_do_send` | Unchanged — confirmed as planned | **STORY-014 must reconcile this.** Its AC says "the in-state `sessions` list reorders so the active chat is first"; because a newly created chat is not inserted into `sessions` here (`create` returns only an id, no `updated_at`), STORY-014 must re-read the list after `touch(...)` rather than reorder in place. |
| — | `logout()` left untouched | STORY-016 AC 8 owns clearing `sessions`, `active_session_id` and `sessions_error`, and asserts row counts across the logout. Interim exposure is bounded: nothing renders `sessions` until STORY-018, and `login()` overwrites the list on every sign-in. |

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_chat_state.py` | `test_chat_state_declares_the_three_session_vars` (AC 1); `test_login_loads_the_session_list_into_state` (AC 2); `test_login_offloads_the_session_read_to_a_thread` (AC 2); `test_an_idle_mount_creates_no_session_row` (AC 3); `test_first_send_creates_exactly_one_session_titled_from_the_prompt` (AC 4); `test_active_session_id_is_set_before_run_query_is_called` (AC 4, ordering); `test_second_send_reuses_the_session_and_creates_no_second_row` (AC 5); `test_run_query_receives_the_active_session_id_on_every_outcome[success/duplicate/injection/forbidden]` (AC 6); `test_history_off_creates_no_session_and_passes_none_to_run_query` (AC 7); `test_chat_state_never_names_the_history_flag` (AC 7, structural, via `ast`); `test_a_session_error_while_creating_sets_the_error_and_still_sends` (AC 8); `test_a_session_error_while_loading_sets_the_error_and_still_signs_in` (AC 8); `test_pending_clears_when_session_creation_raises` (AC 9) |

Helpers added: `_session_rows` (reads the store directly, because AC 3 says "when the database is inspected"), `_backdate_session`, `_capturing_run_query`.

## End-to-End Verification

Two layers beyond the unit tests.

**Scripted, against the real pipeline and real database (30/30 checks):** idle mount writes no row; first send creates one auto-titled session whose id appears on the audit row; second send reuses it and both audit rows name the same conversation; a fresh sign-in restores the rail with titles and activity times; `CHAT_HISTORY_ENABLED=false` writes no session, still writes the audit row with `session_id` NULL, and still answers; a failing `create` keeps the turn, surfaces the error, clears `pending`, and the audit row is written anyway.

**Live boot** (`reflex run --env prod --single-port`, per the **reflex-process-management** skill) driven through the browser — the one check that proves the async handler works through Reflex's real event dispatch rather than a direct `await`:

- The gate's `on_submit=ChatState.login` fired and cleared; the header rendered *SENDING AS ana@empresa.com*, which only happens if the coroutine ran to completion including the offloaded session read.
- A real send produced a `YOU` bubble and a `CLEARED` bubble (*"1 PII type masked in this exchange: LOCATION"*, gpt-4, 76 tokens, `#5`), and the composer re-enabled — `pending` cleared.
- The database showed exactly one **new** session titled *summarise the Q3 vendor spend* alongside the pre-seeded one, and audit row `id=5` carrying that session's id: **the record-to-conversation join working in the running app.**

Live data and `reflex.log` were cleaned up afterwards, and the `reflex.lock/` files the server run modified were reverted so they stay out of this commit.

## Note on the environment

The full suite collapsed into 580 fixture errors on one run while every suite passed in isolation. This is the known libSQL dev-container degradation, not a regression: `docker restart harness-libsql-dev` and the suite returned 1454 passed. Recorded so the next reader does not bisect the code for it.

## Acceptance Criteria

- [x] `ChatState` declares `sessions: list[ChatSessionSummary]`, `active_session_id: str` and `sessions_error: str`
- [x] On successful sign-in the session list is loaded through `chat_sessions.list_for(identity)`, offloaded via `asyncio.to_thread(...)`
- [x] A user who opens the app and sends nothing leaves **no `chat_sessions` row** — asserted against the database, and confirmed in the live app
- [x] The first send creates exactly one session, titled from that prompt, with `active_session_id` set **before** `run_query` is called
- [x] A second send creates no session and reuses the existing `active_session_id`
- [x] `run_query(...)` receives `session_id=self.active_session_id` on every outcome, including the blocked arms from STORY-009
- [x] With `CHAT_HISTORY_ENABLED is False`: no session created, `active_session_id` stays empty, `run_query` receives `None`, and the send otherwise behaves exactly as before
- [x] A `ChatSessionError` while loading or creating sets `sessions_error` and the send still proceeds
- [x] `pending` still clears on every path, including the new failure mode
- [x] `tests/test_chat_state.py` passes with its existing assertions plus the new ones
- [x] All tasks completed
- [x] Backend imports cleanly; `reflex compile --dry` succeeds
- [x] Follows existing patterns
