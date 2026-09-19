---
story: STORY-017
prd: PRD-010
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-017-two-instance-smoke-with-history.plan.md
epic_branch: epic/PRD-010-multi-turn-pipeline
commit: 92b2d2a
status: COMPLETE
completed: 2026-09-19
---

# Implementation Report — STORY-017: Two-instance smoke: a multi-turn chat continued across instances

**Plan**: `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-017-two-instance-smoke-with-history.plan.md`
**Epic Branch**: `epic/PRD-010-multi-turn-pipeline`
**Commit**: `92b2d2a`

## Summary

`tests/test_two_instance_smoke.py` absorbed the conversation half of the epic the way it
absorbed PRD-008's session half: by addition, with no second harness and no restructuring.
The child process gained four commands — `send`, `upstream`, `reset_upstream`, `set_limits` —
and the module gained four tests, one per substantive acceptance criterion. The fifth AC
(existing tests unmodified) is carried by the diff rather than by a test.

The headline claim is AC 1's, and it is the one assertion in the file that process memory
cannot fake: exchange 1 is sent on instance A, exchange 2 on instance B, and B's upstream
recorder holds `[user(ex1), assistant(ex1 reply), user(ex2)]`. B never executed exchange 1 —
no bubble, no cached session, no shared interpreter — so all three messages came out of the
shared database through `messages_for` → `chat_history.assemble`.

**Tests only. No production file changed.**

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Child imports + `recording_call_openrouter` (the upstream recorder) | `tests/test_two_instance_smoke.py` | ✅ |
| 2 | `do_send` — `ChatState`'s history arm, reproduced, with the five returned outcome kinds persisted through `chat_sessions` | `tests/test_two_instance_smoke.py` | ✅ |
| 3 | `do_upstream`, `do_reset_upstream`, `do_set_limits` | `tests/test_two_instance_smoke.py` | ✅ |
| 4 | Parent helpers: `_conversation`, `_sends`, `_reset_upstream`, `_limits`, `_pre_history_trimmed_ddl`, `_booted_pair` | `tests/test_two_instance_smoke.py` | ✅ |
| 5 | AC 1 and AC 2 tests | `tests/test_two_instance_smoke.py` | ✅ |
| 6 | AC 4 test (trimmed send on A, count read on B) | `tests/test_two_instance_smoke.py` | ✅ |
| 7 | AC 3 test (pre-`history_trimmed` boot race, two fresh processes) | `tests/test_two_instance_smoke.py` | ✅ |
| 8 | Module docstring third paragraph + seventh invariant; AC 5 confirmed by diff | `tests/test_two_instance_smoke.py` | ✅ |
| 9 | Full-suite run + this report | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Module: `pytest tests/test_two_instance_smoke.py -q` | ✅ 14 passed (10 pre-existing + 4 new) |
| Full suite: `pytest -q` | ✅ 2253 passed, 26 skipped, 2 warnings (190 s) |
| E2E checklist | ✅ 10/10 |
| No production file changed | ✅ `git diff --stat HEAD` touches `tests/` and `.agents/` only |
| No orphan child processes after the run | ✅ |
| libSQL container restart needed | No — no fixture errors were seen at any point |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_two_instance_smoke.py` | UPDATE | +673 / −2 |
| `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-017-two-instance-smoke-with-history.plan.md` | CREATE (archived from `/plan`) | +636 |
| `.agents/reports/PRD-010-multi-turn-pipeline/STORY-017-two-instance-smoke-with-history.report.md` | CREATE | this file |

The two deleted lines are both import statements that were expanded in place
(`from app.db.models import AUDIT_LOGS_ADDED_COLUMNS, User` and
`from app.services import authz, chat_sessions`). No existing test body, fixture or handler
was modified — which is AC 5, stated as a diff rather than as a claim.

## The two deliberate deviations from `ChatState`, and why neither weakens the claim

Recorded here because the story's Technical Notes require saying which path the test drives,
and because `_INVARIANTS` now carries the obligation that comes with the first one.

1. **`ChatState` is not imported; `do_send` reproduces its history arm.**
   `chat_ui/chat_ui/state.py:5` imports `reflex`, and an `rx.State` subclass needs an app
   context a pipe-driven probe has not got. `do_send` therefore runs the same sequence the
   production arm runs (`chat_ui/chat_ui/state.py:1072-1121`): `chat_history.assemble` →
   `chat_history.fit` with `settings.CONTEXT_MAX_MESSAGES` / `CONTEXT_MAX_CHARACTERS` →
   `run_conversation`, then one `user` row and exactly one outcome row through
   `app/services/chat_sessions.py`, with `history_trimmed` on the answer and nowhere else.
   The precedent is `scripts/measure_history_latency.py:437-446`. The in-process pins on the
   real `ChatState` remain `tests/test_chat_state.py` and `tests/test_chat_history_send.py`;
   what this file claims is the database boundary, which a reproduction of the sequence is
   sufficient to test and an import would not improve.
2. **No `run_in_pipeline` hop.** `ChatState` awaits both calls on the dedicated executor
   (STORY-006); the child calls them synchronously on its only thread. What the executor buys
   is measured by `tests/test_pipeline_concurrency.py` (STORY-014), and a thread hop cannot
   change which messages cross the database boundary.

`upstream_error` and `internal_error` have no arm in `do_send` because `run_conversation`
*raises* for them rather than returning; the child lets them propagate, the dispatch loop
turns a raise into `{"error": ...}`, and `Instance.recv` fails the test with it. No test in
this module produces one, and a send that started raising would be a finding rather than a
bubble.

## The `fit` arithmetic AC 4 asserts

Two answered exchanges are four messages. With `CONTEXT_MAX_MESSAGES = 3`, `fit` compares
`4 + 1 > 3` → drops the oldest whole exchange (`kept[2:]`, both halves together) → `2 + 1 <= 3`
→ stops. So `dropped == 1` and three messages go upstream, which the test asserts as an exact
list: `[("user", q2), ("assistant", "reply to q2"), ("user", q3)]`, with both halves of
exchange 1 asserted absent.

A trimmed send is a **success**, never a `context_limit` bubble: `fit` accepts on `<=` where
`query_pipeline._context_limit_exceeded` refuses on `>`, over the identical two counts
(`app/services/chat_history.py:143-150`). The test asserts `kind == "assistant"` explicitly so
that a future drift between those two halves fails on the kind rather than surfacing as a
confusing `history_trimmed is None`.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_two_instance_smoke.py` | `test_a_conversation_started_on_one_instance_is_continued_with_history_on_the_other` (AC 1) — exchange 1 on A, exchange 2 on B; B's recorder holds the exact three-message conversation; A's recorder still holds one send; B's transcript reads `user, assistant, user, assistant` |
| | `test_a_turn_held_as_a_duplicate_on_one_instance_is_absent_from_the_others_history` (AC 2) — an `injection` turn and then a `duplicate` turn on A (both kinds asserted, both produced by the real pipeline); B's next send carries neither, and the answered exchange appears exactly once |
| | `test_a_trimmed_send_on_one_instance_reports_its_dropped_count_on_the_other` (AC 4) — limits set on both instances, `trimmed == 1`, whole exchange dropped, `history_trimmed` reads `[0, 0, 1]` on B, limits restored on both |
| | `test_two_instances_booting_on_a_pre_history_trimmed_database_converge` (AC 3) — two fresh processes booted simultaneously against a 15-column `chat_messages`; both ready, exactly one `history_trimmed` each, identical boot schemas, seeded transcript preserved reading `None` |

Supporting surfaces added: four child commands (`send`, `upstream`, `reset_upstream`,
`set_limits`) and six parent helpers. `_pre_history_trimmed_ddl()` derives the pre-PRD-010
table by removing the `history_trimmed` line from `CREATE_CHAT_MESSAGES_TABLE` — asserting
exactly one line matched, and repairing the dangling comma — rather than re-typing fifteen
column names that would drift.

## Deviations from Plan

1. **Section placement.** The plan said to put the new section immediately after the PRD-008
   STORY-021 section. It went *after* the PRD-007 "AC 8 — the measured numbers" test instead,
   so that the file still ends with `_INVARIANTS` and the epic sections stay in chronological
   order. No assertion is affected.
2. **The legacy session id is a local constant.** The plan implied reusing
   `tests/test_db.py`'s `_PRE_010_SESSION_ID`; that name is private to that module, so the
   test defines `_LEGACY_SESSION_ID` with the same value and its own comment. Cross-importing
   between test modules is not this suite's idiom.
3. **The plan's "no production file moved" command was mis-specified.** It compared against
   `main`, which necessarily lists all sixteen earlier stories of the epic. The check that
   answers the question for *this* story is `git diff --stat HEAD`, and that is what was run:
   `tests/` and `.agents/` only.
4. **`_sends` and `_reset_upstream` were added** as small parent helpers beyond the plan's
   list, so "A has still called upstream once" and the per-test recorder reset read as one
   line each at the call sites.

## Acceptance Criteria

- [x] Exchange 1 on A, exchange 2 on B → B's upstream recorder receives `[user(ex1), assistant(ex1 reply), user(ex2)]`
- [x] A turn held as duplicate on A is absent from B's upstream messages
- [x] Both instances booting simultaneously against a database without `history_trimmed` converge: both boot, exactly one column exists
- [x] A trimmed send on A (small limits on both) → the assistant row's `history_trimmed` matches when read on B
- [x] The existing smoke tests all pass unmodified
- [x] All tasks completed
- [x] Full suite green
- [x] No production file changed
- [x] Follows existing patterns (child handler shape, `_identity`, service-only session writes, boot-evidence-at-boot, and now a seventh invariant)
