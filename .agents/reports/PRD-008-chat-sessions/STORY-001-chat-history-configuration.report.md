---
story: STORY-001
prd: PRD-008
plan: .agents/plans/PRD-008-chat-sessions/completed/STORY-001-chat-history-configuration.plan.md
epic_branch: epic/PRD-008-chat-sessions
commit: pending
status: COMPLETE
completed: 2026-09-03
---

# Implementation Report — STORY-001: CHAT_HISTORY_ENABLED and CHAT_SESSION_LIMIT settings

**Plan**: `.agents/plans/PRD-008-chat-sessions/completed/STORY-001-chat-history-configuration.plan.md`
**Epic Branch**: `epic/PRD-008-chat-sessions`
**Commit**: `pending` (recorded by the follow-up chore commit, per the PRD-007 precedent `bb12176`)

## Summary

`app/config.py` declares `CHAT_HISTORY_ENABLED: bool = True` and `CHAT_SESSION_LIMIT: int = 50` as a PRD-008 group after the `PII_*` block, and a `_validate_chat_session_limit` field validator refuses any value below 1 with a message that names the setting and points at `CHAT_HISTORY_ENABLED=false` as the way to actually turn the feature off. `.env.example` documents both, with the off state spelled out as a consequence rather than a type. `tests/test_config.py` gained an append-only PRD-008 section of eight test functions (ten items).

Nothing reads either setting. That is the story's design, not an omission: `app/services/chat_sessions.py` in STORY-006 is the sole consumer, and the flag exists in the tree first because PRD-008 Risk 1 makes it the mitigation for the largest exposure the PRD introduces.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Declare the two settings and the limit validator | `app/config.py` | ✅ |
| 2 | Document both variables with the off state's consequence | `.env.example` | ✅ |
| 3 | Append the PRD-008 test section | `tests/test_config.py` | ✅ |
| 4 | Full suite as CI runs it | — | ⚠️ not runnable on this machine — see Validation Results |

## Validation Results

| Check | Result |
|-------|--------|
| `app.config` imports (`Settings()` runs at import) | ✅ `True 50` |
| `tests/test_config.py` — 36 items | ✅ 36 passed (26 pre-existing + 10 new) |
| Insertions only in `tests/test_config.py` | ✅ `90 insertions, 0 deletions` |
| E2E checks 1–4 and 6 | ✅ 5/6 |
| E2E check 5 — full `pytest -q` | ⚠️ blocked by the environment, not by this change |
| Lint | n/a — this repo has no linter or formatter; CI runs `pip install` then `pytest -q` |

**How the tests were run, and the one thing that could not be.** This machine has only Python 3.14; `libsql==0.1.11` publishes no wheel for it and its source build fails, and there is no Docker daemon to run the libSQL dev server. `tests/conftest.py` imports `libsql` at module scope and `pytest.exit`s when the endpoint is unreachable, so **no** test module can be collected here — a pre-existing limitation of this workstation, unrelated to this diff. CI pins Python 3.11 and runs a `libsql-server` service container (`.github/workflows/ci.yml:18-36,55`), where the suite runs normally.

To validate this story's tests anyway, `tests/test_config.py` and a byte-identical copy of `.env.example` (`cmp`-verified) were run in a scratch directory with no repo conftest, `PYTHONPATH` pointed at the real repo so `app.config` is the module under test, and the three environment variables the conftest normally supplies set explicitly. Nothing in `test_config.py` uses a conftest fixture, so this exercises every assertion in the file exactly as CI will. The full suite (E2E check 5) remains for CI.

**Guard suites checked by hand** instead, since they could not be executed:

- `tests/test_pii_redaction_integration.py::test_pre_epic_test_files_are_unmodified_by_this_epic` — `_PRE_EPIC_UNTOUCHED_TESTS` lists four files; `tests/test_config.py` is not among them. `test_no_pre_epic_test_function_was_removed_or_renamed` checks removals only, and none were removed.
- `tests/test_untouched_app.py::_UNMODIFIED_SUITES` — six pinned suites; `tests/test_config.py` is not among them, and `.env.example` is pinned nowhere.
- `tests/test_untouched_app.py::test_no_file_under_app_changed_since_prd_006_began` — **already red at HEAD before this story**: 14 files under `app/` differ from its pinned base `d3e6279`, all of them PRD-007's, `app/config.py` among them. This change adds no file to that list and does not alter the test's outcome. Flagged as a pre-existing condition for whoever owns it; it is not this story's to fix.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/config.py` | UPDATE | +29/-0 |
| `.env.example` | UPDATE | +9/-0 |
| `tests/test_config.py` | UPDATE | +90/-0 |

## Deviations from Plan

1. **The `.env.example` comment gained "no session rail" and the `app/config.py` group comment was expanded** to state the off state as a consequence (nothing written, nothing read, no rail, pre-PRD-008 behaviour) rather than naming the variable back at the reader. The plan's Task 2 text was close to this already; the wording landed slightly longer so that `test_env_example_says_what_the_off_state_does` asserts on substance that is actually there.
2. **A tooling repair, not a design change**: the Bash heredoc used to append the test block unescaped `\n` inside three string literals, which broke the file. Caught immediately by `py_compile`, repaired in place, and the three lines now read exactly as the plan specified (matching the existing `rf"(?m)^#.+\n{var}="` idiom at `tests/test_config.py:68`).
3. **Task 4 could not be executed** — see Validation Results. Everything within reach of this machine was run; the full suite is CI's.

Nothing else deviated. No consumer was wired, and no file outside the three in the plan was touched (`README.md` stays with STORY-022).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_config.py` | `test_chat_history_settings_available_with_documented_defaults` (AC 1) · `test_chat_history_can_be_turned_off_with_the_string_false` (AC 3) · `test_a_chat_session_limit_below_one_is_a_startup_error[0, -1, "0"]` (AC 2) · `test_a_chat_session_limit_of_one_is_accepted` · `test_settings_construct_without_the_chat_vars` · `test_env_example_documents_both_chat_vars_with_a_comment` (AC 4) · `test_env_example_chat_vars_appear_in_settings_field_order` · `test_env_example_says_what_the_off_state_does` (AC 4) |

`"0"` is parametrized alongside the integers because the environment supplies strings and pydantic coerces before the validator runs — a validator written against the raw string would pass the int cases and leak that one. `test_a_chat_session_limit_of_one_is_accepted` pins the accepted boundary so a `<= 1` slip fails here rather than in STORY-006.

## Acceptance Criteria

- [x] `Settings` declares `CHAT_HISTORY_ENABLED: bool = True` and `CHAT_SESSION_LIMIT: int = 50`, grouped and commented in the `RBAC_*` / `PII_*` style, naming PRD-008 — `app/config.py:76-85`
- [x] A `CHAT_SESSION_LIMIT` below 1 fails startup with a message naming the setting — `app/config.py:126-142`; verified end-to-end: `CHAT_SESSION_LIMIT=0 python -c "import app.config"` exits 1 and prints `CHAT_SESSION_LIMIT must be at least 1, got 0.`
- [x] `CHAT_HISTORY_ENABLED=false` in the environment yields `settings.CHAT_HISTORY_ENABLED is False`, asserted with the string `"false"`
- [x] `.env.example` carries both variables with their defaults and a comment stating what the off state does — `.env.example:57-64`
- [x] Existing assertions in `tests/test_config.py` pass unmodified (0 deletions) and the new ones cover the default, the explicit `false`, and the rejected limit
- [x] All tasks completed, except the full-suite run that this machine cannot perform (stated above rather than claimed)
- [x] `app.config` still imports — `Settings()` is constructed at import time
- [x] Follows existing patterns (`app/config.py:64-74,87-109`; `tests/test_config.py:95-97,255-273`)
- [x] No file outside the three listed is touched; `README.md` left to STORY-022
