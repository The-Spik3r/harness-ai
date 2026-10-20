---
story: STORY-004
prd: PRD-013
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-004-conversation-key.plan.md
epic_branch: epic/PRD-013-audit-and-usage-limits
commit: 99845b5
status: COMPLETE
completed: 2026-10-14
---

# Implementation Report — STORY-004: conversation_key derivation

**Plan**: `.agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-004-conversation-key.plan.md`
**Epic Branch**: `epic/PRD-013-audit-and-usage-limits`
**Commit**: `99845b5` (plan commit: `4ed9a2c`)

## Summary

`app/services/conversation_key.py` is new. It defines `CONVERSATION_KEY_VERSION = "c1"` and `conversation_key(user_id, messages)`, the exact body from PRD Section 6.3: `_sha256_json([CONVERSATION_KEY_VERSION, user_id, first_system, first_user])`, where `first_system` defaults to `""` and `first_user` comes from a bare `next(...)` with a comment naming `_validate_conversation`. Nothing calls it yet: `run_conversation` computes it in STORY-005.

- **Hashing is reused, not copied.** `_sha256_json` is imported by name from `app.services.duplicate_checker`. The by-name binding is deliberate (plan Decision 1). `tests/test_query_pipeline_multiturn.py:323-340` monkeypatches `duplicate_checker._sha256_json` and asserts that `framed[0]` is `dedup_key`'s prefix. A bound name is not affected by that patch, so the test will still pass once STORY-005 computes both keys.
- **The docstring** states the three documented limits from Section 6.3, the chat-UI caveat (`session_id` is authoritative for chat rows), and T13 (why exposing the key discloses nothing new).

No existing file changed.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Preflight: plan committed as `4ed9a2c`, epic branch confirmed, predecessors 001–003 have SHAs, Docker Desktop and `harness-libsql-dev` started | — | ✅ |
| 1 | Baseline full suite | — | ✅ (2 flaky, below) |
| 2 | Create the module | `app/services/conversation_key.py` | ✅ |
| 3 | Create the tests, 12 cases | `tests/test_conversation_key.py` | ✅ |
| 3b | Five mutation bite checks | — | ✅ |
| 4 | Full suite, E2E checklist, `/health` | — | ✅ (1 flaky per run, below) |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | n/a: the repo has no `frontend/`; the UIs are Reflex Python modules, and this story changes none |
| `GET /health` | ✅ `200 {"status":"ok"}` (server started with `RBAC_ENABLED=false`, see Deviation 3) |
| `pytest tests/test_conversation_key.py` | ✅ 12 passed |
| `pytest tests/test_dedup_key.py tests/test_query_pipeline_multiturn.py` | ✅ 50 passed |
| Baseline full suite, before any change | 3412 passed, 27 skipped, 2 failed (both libSQL `STREAM_EXPIRED`; 8/8 pass alone) |
| Full suite after, run 1 | 3425 passed, 27 skipped, 1 failed: `test_duplicate_scope.py::...[success]` (a 500, i.e. a storage error; passes alone 3/3, file 22/22) |
| Full suite after, run 2 | 3425 passed, 27 skipped, 1 failed: `test_integration.py::...[show system prompt]` (`STREAM_EXPIRED`; 7/7 pass alone) |
| E2E | ✅ 3/3 |

The counts reconcile: 3414 + 12 = 3426. Every full-suite failure is in a database-backed test, is a different test in each run, and passes when rerun alone. This is the local libSQL flakiness that PRD Section 11 and the STORY-001 report describe. The new module is not imported by anything in `app/`, so it cannot reach any of those code paths.

### Bite checks

Each mutation was applied to the module, the new tests were run, and the original file was restored. The final diff was empty.

| Mutation | Result |
|----------|--------|
| Version left out of the hashed list | 3 failed |
| `user_id` left out | 4 failed |
| Last `user` turn instead of the first | 3 failed |
| `system` left out | 4 failed |
| String concatenation instead of a framed list | 4 failed |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/conversation_key.py` | CREATE | +45 |
| `tests/test_conversation_key.py` | CREATE | +152 |

## Deviations from Plan

1. **Test 10 checks for `"import settings"`, not `"settings"`.** The plan's wording would have matched the docstring's own phrase "no settings". The `ast` import check is the real guard, and it is unchanged.
2. **Test 3 also asserts the conversation ends with 50 user turns**, so the "1 to 50 user turns" in AC 1 is checked directly rather than inferred from the loop bounds.
3. **`/health` was checked with `RBAC_ENABLED=false` set for that one process.** With the repo `.env` as is, startup refuses because RBAC is on and the configured dev database has no active user (`RbacNotBootstrappedError`). That is a local environment precondition, unrelated to this story. No user was created and no file was changed to get around it.
4. **Environment.** `python` on the PATH is the Microsoft Store stub. The suite ran in the venv at `C:\Users\tobip\.venvs\harness-ai`, as recorded in the STORY-001 report.

## Findings

- **F-1 (from the plan): importing the module loads `app.db` and `app.config` indirectly**, through `duplicate_checker`'s own imports. AC 5 is about the file's own imports and holds. If a later story needs this module importable without settings, move `_sha256_json` into a dependency-free module then, and keep `duplicate_checker` importing it under the same name so the spy test is unaffected.
- **For STORY-005:** compute `conversation_key` after `_validate_conversation`. Before validation, a conversation with no `user` turn would surface as `StopIteration`, not `InvalidConversationError`.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_conversation_key.py` | `test_exports_version_c1_and_the_specified_signature`, `test_key_is_the_framed_hash_of_version_user_system_and_first_user`, `test_stable_across_fifty_growing_turns`, `test_differs_by_user`, `test_differs_by_first_user_message`, `test_differs_by_first_system_message`, `test_no_system_turn`, `test_only_the_first_system_and_first_user_count`, `test_field_boundaries_cannot_be_forged`, `test_non_ascii_is_hashed_as_utf8`, `test_imports_no_settings_and_no_database_module`, `test_docstring_states_the_three_documented_limits` |

## Acceptance Criteria

- [x] Given a conversation that grows from 1 to 50 user turns with the same `system` and first `user` message, when `conversation_key(user_id, messages)` is computed at each step, then all 50 values are equal. (`test_stable_across_fifty_growing_turns`)
- [x] Given the same messages and two different `user_id` values, when the key is computed, then the two values differ. (`test_differs_by_user`)
- [x] Given two conversations whose first `user` messages differ, or whose first `system` messages differ, when the key is computed, then the values differ. (`test_differs_by_first_user_message`, `test_differs_by_first_system_message`)
- [x] Given a conversation with no `system` turn, when the key is computed, then it succeeds, and `[user("a")]` and `[user("a"), assistant("b"), user("c")]` give the same key. (`test_no_system_turn`)
- [x] Given `app/services/conversation_key.py`, when it is read, then it imports no settings and no database module, defines `CONVERSATION_KEY_VERSION = "c1"`, and includes the version in the hashed value. (`test_imports_no_settings_and_no_database_module`, `test_exports_version_c1_and_the_specified_signature`, `test_key_is_the_framed_hash_of_version_user_system_and_first_user`)
- [x] All tasks completed
- [x] Full test suite passes (apart from the libSQL flakiness above, each case confirmed passing alone)
- [x] Follows existing patterns
