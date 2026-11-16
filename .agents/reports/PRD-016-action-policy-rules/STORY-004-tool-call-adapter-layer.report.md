---
story: STORY-004
prd: PRD-016
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-004-tool-call-adapter-layer.plan.md
epic_branch: epic/PRD-016-action-policy-rules
commit: 9e277d3
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-004: ToolCall, Operation, the tool mapping layer and built-in OpenCode/Cline/SQL mappings

**Plan**: `.agents/plans/PRD-016-action-policy-rules/completed/STORY-004-tool-call-adapter-layer.plan.md`
**Epic Branch**: `epic/PRD-016-action-policy-rules`
**Commit**: `9e277d3`

## Summary

New pure module `app/services/action_adapters.py`. It holds `ToolCall` (PRD 6.2) and re-exports `Operation` / `OperationKind` from `action_classifiers`. It adds `TargetFormat` / `TARGET_FORMATS` (`text`, `command`, `patch`), a frozen `ToolMapping(kind, target, default=None, format="text", extra_targets=())` validated in `__post_init__` (it raises `ToolMappingError(ValueError)`), the four results `Operations` / `Opaque` / `Unknown` / `Malformed`, and `map_tool_call(call, tools, opaque_tools, max_argument_characters)`. It also adds `BUILT_IN_TOOLS`, a read-only `MappingProxyType` with 24 entries, one per non-`none` row of `SOURCES.md`.

The target expression grammar is `path ("|" path)*` with `key[]` array segments. Alternatives resolve level by level, so a per-element alias (`files[].path|files[].filePath`) is chosen per element. Two spellings present at the same level is `Malformed`. One key can be both an array and a scalar (`commands[]|commands`), and the value's type picks which. `ToolMapping` refuses overlapping alternatives at construction.

Every ambiguity fails closed to `Malformed`:
- a missing key, or one present but null
- an empty array
- a patch with no header, or a header with no path
- an empty or whitespace target
- a line break or NUL in an `fs_*` / `http` target
- a duplicate JSON key at any level
- non-object JSON, invalid JSON, or `RecursionError` / int-digit-limit `ValueError`
- arguments over the cap, which are refused before `json.loads`

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Module skeleton, types, grammar, `ToolMapping` validation | `app/services/action_adapters.py` | ✅ |
| 2 | `map_tool_call`, the patch extractor, the duplicate-key hook | `app/services/action_adapters.py` | ✅ |
| 3 | `BUILT_IN_TOOLS` (24), with Cline 4.x aliases | `app/services/action_adapters.py` | ✅ |
| 4 | Tests, parametrized over the `SOURCES.md` tables | `tests/test_action_adapters.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ `OK` |
| Frontend lint / chat UI import | n/a (no `frontend/`; `chat_ui/` not touched) |
| Story tests (`tests/test_action_adapters.py`) | ✅ 518 passed |
| Targeted set (`test_action_adapters.py`, `test_action_vocabulary.py`, `test_untouched_app.py`) | ✅ 536 passed, 0 failed, 0 skipped (1.38 s) |
| Full suite | Deferred to orchestrator (user decision) |
| E2E | No route, UI or startup change: nothing calls `map_tool_call` until STORY-014. Backend import is clean |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/action_adapters.py` | CREATE | +556 |
| `tests/test_action_adapters.py` | CREATE | +639 |
| `.agents/plans/PRD-016-action-policy-rules/completed/STORY-004-tool-call-adapter-layer.plan.md` | CREATE (archived, with an implementation addendum) | |
| `.agents/stories/PRD-016-action-policy-rules/STORY-004-tool-call-adapter-layer.md` | UPDATE (status, plan, report, commit, ACs ticked) | |
| `.agents/PRDs/PRD-016-action-policy-rules/index.md` | UPDATE (regenerated) | |
| `.agents/PRDs/PRD-016-action-policy-rules/PRD.md` | UPDATE (orchestrator edit: the 6.6 sample `apply_patch` gains `format: patch`) | +1/-1 |
| `.agents/stories/PRD-016-action-policy-rules/STORY-006-action-config-loader.md` | UPDATE (orchestrator note: built-in `opaque_tools` is empty) | +1 |
| `.agents/stories/PRD-016-action-policy-rules/STORY-007-action-policy-file-load-and-validation.md` | UPDATE (orchestrator note: accept `default` / `format` / `extra_targets`, wrap `ToolMappingError`) | +1 |

## Deviations from Plan

- **Orchestrator decision 3 (Cline 4.x aliases).** The built-ins now read these Cline 4.x aliases:
  - `run_commands` = `commands[]|commands|cmd`. This covers `cmd`, plus `commands` as a single string or a single `{command, args}`.
  - `read_files` = `files[].path|files[].file_path|files[].filePath|files.path|files.file_path|files.filePath|file_paths[]|file_paths|paths[]|paths`. This covers the per-entry `file_path` / `filePath`, `files` as one object, and `file_paths` / `paths` as an array or a string.

  These shapes are **not** covered and stay `Malformed`:
  - `run_commands` top-level `{command, args?}` / `{command}`. The arguments object is itself the argv, so reading `command` alone would drop `args`, which would be an evasion.
  - `files[]` of strings and `files` as a string. The grammar cannot read one key both as a value and as an object.
  - `paths` as an object.
  - Bare strings and arrays, which are not JSON objects.
- **Alias ambiguity.** Two spellings present is `Malformed`, and this applies to every `|` expression, including `absolutePath|path` and `patchText|input`. It replaces the plan's "classify every present spelling". The planned `test_both_aliases_present_are_both_classified` became `test_two_spellings_of_one_key_are_malformed`, which covers top-level and per-element cases. No pre-existing test was renamed.
- **Grammar refinement, not in the plan.** Resolution runs level by level, which is what makes per-element aliases work. `ToolMapping` also refuses overlapping alternatives (`a|a`, `a|a.b`, `files[]|files[].path`).
- `map_tool_call` returns `Malformed("tool name is not a string")` for a non-`str` name. This defensive guard is not in the plan.
- `_parse_target` is split into a type-checking wrapper and an `lru_cache`d parser. Otherwise an unhashable `target` would raise `TypeError` instead of `ToolMappingError`.
- Decisions 1, 2, 4, 5, 6 and 7 were applied as planned: the optional fields, the newline/NUL guard, `browser_action.url` required, `apply_migration` kept, no built-in `opaque_tools` here, and the limit number kept in the over-length detail.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_action_adapters.py` | SOURCES.md checks: `test_sources_parser_reads_every_row`, `test_every_sources_row_is_mapped_as_recorded` (41 rows), `test_built_in_tools_are_exactly_the_sources_rows`, `test_every_mapped_sources_row_has_a_realistic_sample`, `test_realistic_call_yields_documented_kind_and_targets` (28 rows) |
| | AC1: `test_bash_ls_maps_to_one_shell_operation` |
| | Shapes: patch headers, no header, empty header, `test_two_spellings_of_one_key_are_malformed` (7), `test_run_commands_lenient_aliases_are_classified` (4), `test_read_files_lenient_aliases_are_classified` (7), `test_inexpressible_cline_4_shapes_are_malformed` (5), empty arrays, shlex argv round-trip, bad argv elements, `default="."`, null target, glob `pattern` second op, glob without pattern, `browser_action` without url, nested missing key, non-object element, scalar for an array, prefixed MCP names, line break / NUL in a path or URL, shell and SQL newlines kept, empty target |
| | AC3: `test_malformed_arguments` (13), `test_detail_never_echoes_argument_values`, `test_over_length_is_malformed_without_parsing` (monkeypatched `json.loads` plus a live-patch control), `test_length_at_the_cap_is_accepted` |
| | AC4: `test_unmapped_name_is_unknown` (5), `test_opaque_tool_returns_configured_decision` (3x3), `test_mapped_name_wins_over_opaque` |
| | Validation: `test_tool_mapping_rejects_bad_definitions` (24), vocabulary messages, `ValueError` subclass, accepted grammar, read-only `BUILT_IN_TOOLS`, frozen `ToolCall`, `Operation` re-exported |
| | F7: `test_map_tool_call_never_raises` (13 hostile inputs x 24 tools), non-string arguments and name |
| | AC5: `test_action_adapters_stays_pure`, `test_importing_action_adapters_loads_no_settings` (subprocess `sys.modules` check) |

## Acceptance Criteria

- [x] AC1: `bash` / `ls` gives exactly `Operations((Operation("shell", "ls", "bash"),))` (`test_bash_ls_maps_to_one_shell_operation`).
- [x] AC2: every `SOURCES.md` mapping yields the documented kind and targets, and `apply_patch` yields one `fs_write` per header (`test_every_sources_row_is_mapped_as_recorded`, `test_realistic_call_yields_documented_kind_and_targets`, `test_apply_patch_names_one_fs_write_per_header`).
- [x] AC3: `"not json"`, `"[]"`, `"{}"`, `'{"command": 3}'` and over-length input are `Malformed`, and `json.loads` is not called for over-length input (`test_malformed_arguments`, `test_over_length_is_malformed_without_parsing`).
- [x] AC4: an unmapped name is `Unknown()`, and a name in `opaque_tools` is `Opaque(decision)` (`test_unmapped_name_is_unknown`, `test_opaque_tool_returns_configured_decision`).
- [x] AC5: the module imports no settings and does no I/O (`test_action_adapters_stays_pure`, `test_importing_action_adapters_loads_no_settings`).
