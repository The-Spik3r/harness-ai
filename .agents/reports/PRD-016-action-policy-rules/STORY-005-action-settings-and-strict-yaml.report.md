---
story: STORY-005
prd: PRD-016
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-005-action-settings-and-strict-yaml.plan.md
epic_branch: epic/PRD-016-action-policy-rules
commit: pending
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-005: Three action settings; strict_yaml with duplicate-key rejection; pattern_config adopts it

**Plan**: `.agents/plans/PRD-016-action-policy-rules/completed/STORY-005-action-settings-and-strict-yaml.plan.md`
**Epic Branch**: `epic/PRD-016-action-policy-rules`
**Commit**: `pending`

## Summary

`app/config.py` declares `ACTION_POLICY_FILE: str = ""`, `ACTION_MAX_ARGUMENT_CHARACTERS: int = 100_000` and `ACTION_SQL_DIALECT: str = ""` in a new PRD-016 block after `V1_SSE_KEEPALIVE_SECONDS`. The integer joins the shared `_validate_positive_limit` validator, and its `_POSITIVE_LIMIT_DESCRIPTIONS` entry says what to set instead of 0. No code reads these settings yet. Their consumers arrive in STORY-006/007/008/014.

The new pure module `app/services/strict_yaml.py` holds `_StrictSafeLoader(yaml.SafeLoader)`. Its `construct_mapping` override rejects a key written twice in any mapping, at any depth, with a `ConstructorError` that names the key, the line it was first defined on and the line of the second definition. `<<` merge keys are skipped, so a merge override parses exactly as `yaml.safe_load` parses it. `safe_load(text)` is the only public entry point.

`pattern_config.load()` now calls `strict_yaml.safe_load` and keeps its `except yaml.YAMLError` arm. Its docstring's "PyYAML resolves duplicate mapping keys silently" paragraph is replaced by a note citing PRD-016 D13 and Risk 8.

Rendered message for `ACTION_MAX_ARGUMENT_CHARACTERS=0` (the shared validator was reused, as the orchestrator decided):

> ACTION_MAX_ARGUMENT_CHARACTERS must be at least 1, got 0. It is the ceiling on characters in a tool call's arguments string, over which the call is denied as tool.malformed. 0 does not remove the ceiling -- there is no unbounded value; set a positive count instead, e.g. ACTION_MAX_ARGUMENT_CHARACTERS=100000 (the default).

Rendered message for a scratch `PATTERNS_FILE` with `lists:` written twice:

```
Failed to parse PATTERNS_FILE '<path>/dup.yaml': while constructing a mapping
  in "<unicode string>", line 1, column 1:
    lists:
    ^
found duplicate key 'lists' (first defined on line 1)
  in "<unicode string>", line 6, column 1:
    lists:
    ^
```

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Declare the three settings; add the positive-limit entry | `app/config.py` | ✅ |
| 2 | Create the strict loader | `app/services/strict_yaml.py` | ✅ |
| 3 | `pattern_config` adopts it; replace the docstring paragraph | `app/services/pattern_config.py` | ✅ |
| 4 | strict_yaml tests | `tests/test_strict_yaml.py` | ✅ |
| 5 | Settings tests | `tests/test_config.py` | ✅ |
| 6 | pattern_config duplicate-key test | `tests/test_pattern_config.py` | ✅ |
| 7 | Targeted regression | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Frontend lint | N/A (no frontend) |
| Targeted tests (`test_strict_yaml`, `test_config`, `test_pattern_config`, `test_pattern_profiles`, `test_pattern_default_config_regression`, `test_untouched_app`) | ✅ 362 passed, 0 failed, 0 skipped (35.6s) |
| Full suite | Deferred to orchestrator (user decision) |
| E2E | ✅ 3/3: the app imports; `examples/patterns.yaml` loads to the built-in policy (`test_examples_patterns_yaml_loads_to_the_built_in_policy`); a scratch `PATTERNS_FILE` with `lists:` twice fails with the file, the key and both lines named (manual run, message above) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/config.py` | UPDATE | +35/-3 |
| `app/services/strict_yaml.py` | CREATE | +72 |
| `app/services/pattern_config.py` | UPDATE | +13/-9 |
| `tests/test_strict_yaml.py` | CREATE | +177 |
| `tests/test_config.py` | UPDATE | +54 |
| `tests/test_pattern_config.py` | UPDATE | +46 |

## Deviations from Plan

- `tests/test_pattern_config.py`: the new duplicate-key test is parametrized with a top-level duplicate (`lists`) and a nested one (`patterns` twice inside one list). The plan listed the nested case as optional. The test also asserts that the built-in policy stays in force. The bodies are module constants in `_VALID_FILE`'s style. No existing assertion changed.
- `tests/test_strict_yaml.py` adds a few equality cases beyond the plan: a merge list with an override, `!!set {a, b}`, and the same key in sibling list items. The `examples/patterns.yaml` equality check is its own test, not a parametrize row. The `!!python` test also asserts that the strict message equals the `safe_load` message.
- `strict_yaml.safe_load` carries `# noqa: S506`. The repo has no lint config, but the comment follows the repo's existing `noqa`-with-rationale style (`app/services/reports.py:322`).
- Orchestrator decisions applied: `!!set` duplicates are rejected, and a code comment records it. A hidden duplicate in an existing `PATTERNS_FILE` now stops the boot, as intended; STORY-020 documents the upgrade note. `map_tool_call` is unchanged, since the setting is only declared here.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_strict_yaml.py` | 24: top-level duplicate names the key and both lines; 4 nested shapes; 2 equal-but-differently-spelled keys; error is a `YAMLError`; 10 no-duplicate equality cases; `examples/patterns.yaml` equality; 3 `!!python` tags; 2 purity tests |
| `tests/test_config.py` | 7: defaults; 3 below-one startup errors (message names the field, the value, `tool.malformed` and `ACTION_MAX_ARGUMENT_CHARACTERS=100000`); boundary value of one; the dialect is only a string; the policy file is not read |
| `tests/test_pattern_config.py` | 2: duplicate `lists` and duplicate nested `patterns` raise `PatternConfigError` naming the file and the key |

## Acceptance Criteria

- [x] The three settings exist with their defaults, and `ACTION_MAX_ARGUMENT_CHARACTERS=0` fails with a message that says what to set instead (`test_action_settings_available_with_documented_defaults`, `test_an_action_max_argument_characters_below_one_is_a_startup_error`).
- [x] `strict_yaml.safe_load("a: 1\na: 2\n")` raises `yaml.YAMLError` naming `a` and its line. Nested duplicates are caught, and a document with no duplicate returns what `yaml.safe_load` returns (`test_a_duplicate_top_level_key_is_refused_naming_the_key_and_its_line`, `test_a_nested_duplicate_key_is_refused`, `test_without_duplicates_the_result_equals_yaml_safe_load`).
- [x] `!!python/object` is refused as `yaml.safe_load` refuses it (`test_python_tags_are_refused_as_safe_load_refuses_them`).
- [x] `pattern_config.load()` raises `PatternConfigError` naming the file and the duplicate key. Every other assertion in `tests/test_pattern_config.py` is unchanged and green (`test_a_duplicate_key_raises_naming_the_file_and_the_key`).
- [x] The docstring paragraph is replaced by a note citing PRD-016 D13 (`app/services/pattern_config.py`, `load()` docstring).
