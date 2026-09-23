---
story: STORY-004
prd: PRD-011
plan: .agents/plans/PRD-011-pattern-policy/completed/STORY-004-pattern-settings.plan.md
epic_branch: epic/PRD-011-pattern-policy
commit: 782842b
status: COMPLETE
completed: 2026-09-22
---

# Implementation Report — STORY-004: Four pattern-policy settings with startup validators

**Plan**: `.agents/plans/PRD-011-pattern-policy/completed/STORY-004-pattern-settings.plan.md`
**Epic Branch**: `epic/PRD-011-pattern-policy`
**Commit**: `782842b`

## Summary

PRD-011's four knobs now exist in `app/config.py` with the defaults PRD Section 9.3 tabulates, documented in `.env.example` and covered by 21 new cases in `tests/test_config.py`. `PyYAML` is declared explicitly in `requirements.txt`. **No production code reads any of the four** — `pattern_config.load()` (STORY-005) and `inspect()` (STORY-008) are the consumers, and each field's comment names its own. That separation is the story's reason to exist: it is PRD-010 STORY-002's shape, where a settings commit stays revertible because it changes no behaviour.

Two calls are worth reading in the diff. `PATTERN_MAX_SCAN_CHARACTERS` joined the existing shared positive-integer validator rather than getting a near-duplicate of its own, which meant renaming the mapping and the validator to shed PRD-010's word "pipeline". And `PATTERN_PROFILE_DEFAULT` got a non-empty check and deliberately nothing more — the membership check needs a file that is not loaded when `Settings` is constructed, so it belongs to `pattern_config.load()`, and a test now holds that boundary open.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Generalize the positive-integer limit mapping and its validator | `app/config.py` | ✅ |
| 2 | Declare the four PRD-011 fields | `app/config.py` | ✅ |
| 3 | Non-empty validator for `PATTERN_PROFILE_DEFAULT` | `app/config.py` | ✅ |
| 4 | Document all four in `.env.example` | `.env.example` | ✅ |
| 5 | Declare `PyYAML` in `requirements.txt` | `requirements.txt` | ✅ |
| 6 | Tests for the four settings | `tests/test_config.py` | ✅ |
| 7 | Full suite green | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| `tests/test_config.py` | ✅ 69 passed (48 before, 21 added) |
| Full suite | ✅ 2354 passed, 26 skipped, 2 pre-existing warnings, 190s |
| E2E | ✅ 7/7 |
| Frontend lint | n/a — no frontend file touched (this repo's UI is Reflex; the story's scope is config) |

The two warnings are the pre-existing `StarletteDeprecationWarning` and `anyio.abc.BlockingPortal` deprecations, unrelated to this change.

### E2E checklist

| # | Check | Result |
|---|-------|--------|
| 1 | Singleton constructs against the real `.env` and prints the four defaults | ✅ `'' chat False 1000000` |
| 2 | `PATTERN_MAX_SCAN_CHARACTERS=0` fails at import naming field, value and bound | ✅ |
| 3 | Empty `PATTERN_PROFILE_DEFAULT` fails at import naming the field | ✅ |
| 4 | `PATTERN_PROFILE_DEFAULT=not-a-profile` **succeeds** — the cross-check was not smuggled in here | ✅ |
| 5 | `pytest tests/test_config.py` | ✅ |
| 6 | Full suite, no production consumer of the new settings | ✅ |
| 7 | Diff touches no file under `app/services/` or `app/routers/` | ✅ |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/config.py` | UPDATE | +73/-7 |
| `.env.example` | UPDATE | +20 |
| `requirements.txt` | UPDATE | +1 |
| `tests/test_config.py` | UPDATE | +173 |
| `.agents/plans/PRD-011-pattern-policy/completed/STORY-004-pattern-settings.plan.md` | CREATE (archived) | +314 |

No file was created under `app/`. No production module gained a reader of the new settings.

## Deviations from Plan

**None in substance.** Every task landed as written, including the rename in Task 1 and the twelve test cases in Task 6. Two notes on execution:

- The `-7` on `app/config.py` is the rename and the reflowing of the widened `@field_validator(...)` decorator onto four lines. No behaviour in the PRD-010 path changed, and its tests were untouched and stayed green.
- The plan's Task 7 anticipated the libSQL dev server needing a start. It needed more than that here: Docker Desktop itself was down and was launched from `%LOCALAPPDATA%\Programs\DockerDesktop` (not the `C:\Program Files` path), then `docker start harness-libsql-dev`. No fixture errors followed, so the degradation case the plan's Risk 6 describes did not arise.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_config.py` | `test_pattern_policy_settings_available_with_documented_defaults`; `test_patterns_allow_regex_can_be_turned_on_with_the_string_true`; `test_a_pattern_max_scan_characters_below_one_is_a_startup_error` (×3: `0`, `-1`, `"0"`); `test_pattern_max_scan_characters_accepts_the_boundary_value_of_one`; `test_an_empty_pattern_profile_default_is_a_startup_error` (×2: `""`, `"   "`); `test_pattern_profile_default_is_not_checked_against_any_policy_here`; `test_pattern_profile_default_strips_surrounding_whitespace`; `test_settings_construct_without_the_pattern_policy_vars`; `test_env_example_documents_every_pattern_policy_var_with_a_comment`; `test_env_example_pattern_policy_vars_appear_in_settings_field_order`; `test_env_example_pattern_defaults_match_the_settings_defaults`; `test_requirements_declares_pyyaml_explicitly` |

Two of these carry more weight than their size suggests:

- `test_pattern_profile_default_is_not_checked_against_any_policy_here` asserts that an **undefined** profile name constructs cleanly. It is the guard on AC 3: a future field validator that reached for `PATTERNS_FILE` would turn it red, and such a validator would either fail every boot or skip the check silently.
- `test_requirements_declares_pyyaml_explicitly` exists because nothing breaks today if `PyYAML` is missing from `requirements.txt` — `python-frontmatter` supplies it. Without the test, a dependency tidy-up removes it as redundant and the build breaks on some later day instead.

## Acceptance Criteria

- [x] `Settings` declares `PATTERNS_FILE: str = ""`, `PATTERN_PROFILE_DEFAULT: str = "chat"`, `PATTERNS_ALLOW_REGEX: bool = False` and `PATTERN_MAX_SCAN_CHARACTERS: int = 1_000_000`, each with a comment naming the story that becomes its consumer (`app/config.py:126-159`).
- [x] `PATTERN_MAX_SCAN_CHARACTERS=0` or negative raises naming the field, the rejected value and what the field bounds — via the shared `_POSITIVE_LIMIT_DESCRIPTIONS` mapping, not inlined prose.
- [x] `PATTERN_PROFILE_DEFAULT` is validated only for non-emptiness; the membership cross-check is deferred to `pattern_config.load()`, and the field comment says so.
- [x] `.env.example` carries all four with the same defaults and a two- or three-line explanation each, in the `CONTEXT_MAX_*` style.
- [x] `PyYAML` is declared explicitly in `requirements.txt`; `tests/test_config.py` covers the new fields and both validators; the full suite is green with no production consumer of the new settings.
- [x] All tasks completed.
- [x] Backend imports without error.
- [x] Follows existing patterns.

## Notes for STORY-005

`pattern_config.load()` inherits three things from this commit: `PATTERNS_FILE` (empty means built-in policy, read no file), the `PATTERNS_ALLOW_REGEX` gate it must enforce when a file declares a `match: regex` list, and the `PATTERN_PROFILE_DEFAULT` membership check this story deliberately left undone — STORY-006 is where the `PatternConfigError` naming the setting, the missing profile and the profiles that exist belongs. `import yaml` is now a declared dependency and safe to use.
