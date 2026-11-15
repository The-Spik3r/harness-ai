---
story: STORY-006
prd: PRD-016
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-006-action-config-loader.plan.md
epic_branch: epic/PRD-016-action-policy-rules
commit: pending
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-006: action_config, part 1: ActionPolicy model, built-in policy, get_policy(), digest, both lifespans

**Plan**: `.agents/plans/PRD-016-action-policy-rules/completed/STORY-006-action-config-loader.plan.md`
**Epic Branch**: `epic/PRD-016-action-policy-rules`
**Commit**: `pending`

## Summary

New `app/services/action_config.py`, modelled on `pattern_config.py`. It holds `ActionConfigError`, frozen `Rule`, `Globs`, `Secrets` and `ActionPolicy` dataclasses, and its own glob translator (`*`, `?`, whole-segment `**`; it refuses `[`, `]`, `\`, an empty glob, an empty segment, a leading `/` and `**` inside a segment). Globs are compiled once and case-insensitive. Path globs are anchored as `(?:^|/)…$` and name globs as `^…$`. The module also holds the built-in data: the 25 rules of PRD 6.3, the 11 protected-path globs, the 7 secret env globs and the 8 secret file globs. `_validate(source, spec)` is the single builder, and the built-in policy goes through it at import (F8). `BUILT_IN_POLICY` uses STORY-004's `BUILT_IN_TOOLS` as the same object and an empty `opaque_tools`. `get_policy()` returns `_policy`. `policy_digest(policy=None)` returns `sha256:<hex>` over canonical sorted-key JSON of the source values. With an empty `ACTION_POLICY_FILE`, `load()` returns and reads no file. With any other value it raises `ActionConfigError` naming the path (fail closed). It is registered in both lifespans after `pii_policy.load` and before `authz.check_bootstrap`, which is after `authz.load`. A new conftest autouse fixture `_default_action_policy` pins the setting to `""` and restores `_policy`.

The built-in digest is `sha256:52b50e196e79706cbffd5dd2771ed4aa90beac22984d284ae5b872d53c229e23`, and it is identical across two separate processes.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Module: error, models, globs, built-in data, `_validate`, `get_policy`, `policy_digest`, `load` | `app/services/action_config.py` | ✅ |
| 2 | FastAPI lifespan registration | `app/main.py` | ✅ |
| 3 | Reflex lifespan registration | `chat_ui/chat_ui/chat_ui.py` | ✅ |
| 4 | conftest autouse reset | `tests/conftest.py` | ✅ |
| 5 | Unit tests | `tests/test_action_config.py` | ✅ |
| 6 | FastAPI lifespan tests | `tests/test_main.py` | ✅ |
| 7 | Reflex probe tests | `tests/test_chat_ui_startup_guard.py` | ✅ |
| 8 | Targeted regression | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| chat_ui import | The brief's `python -c "import chat_ui.chat_ui.chat_ui"` fails in this repo (`ImportError: cannot import name 'theme' from 'chat_ui'`: the package layout expects `chat_ui/` on `sys.path`). The probe's form works: `cwd=chat_ui/`, `PYTHONPATH=chat_ui;.`, `import chat_ui.chat_ui`. It lists the lifespan tasks `… authz.load, pattern_config.load, pii_policy.load, action_config.load, authz.check_bootstrap, …` |
| Frontend lint | N/A (no frontend) |
| Targeted tests (`test_action_config`, `test_main`, `test_chat_ui_startup_guard`, `test_action_adapters`, `test_pattern_config`, `test_untouched_app`) | ✅ 723 passed, 0 failed, 0 skipped (131s) |
| Full suite | Deferred to the orchestrator (user decision) |
| E2E | ✅ 4/4: backend import; `25 sha256:…` with the same digest in two runs; a missing file refuses both lifespans (test_main + probe); unset setting boots and `/health` returns 200 |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/action_config.py` | CREATE | +689 |
| `app/main.py` | UPDATE | +2/-1 |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | +14/-1 |
| `tests/conftest.py` | UPDATE | +16 |
| `tests/test_action_config.py` | CREATE | +495 |
| `tests/test_main.py` | UPDATE | +54 |
| `tests/test_chat_ui_startup_guard.py` | UPDATE | +58/-2 (docstring + probe keys + `_empty_rbac_env` pin + 3 tests; no existing assertion changed) |

Orchestrator edits committed with this story: `STORY-007`, `STORY-011`, `STORY-013` and `STORY-014` story files (the cross-story consequences of the seven accepted decisions).

## Deviations from Plan

- `chat_ui.py`'s import line became a parenthesised multi-line import, because the one-line form would exceed the line length. The content is the same.
- `_validate` rebuilds `rules` in `RULE_IDS` order whatever the input order, so `tuple(policy.rules) == RULE_IDS` holds for every validated policy and not only the built-in one.
- `_validate` keeps `BUILT_IN_TOOLS` by identity (so `BUILT_IN_POLICY.tools is BUILT_IN_TOOLS`) and copies any other `tools` mapping into a fresh `MappingProxyType` (tested by `test_validated_tools_are_copied_not_shared`).
- `_validate` also type-checks `shell_allow` / `network_allow` / `workspace_roots` as lists of strings. Their node names are `shell.allow`, `network.allow` and `workspace.roots`.
- Extra tests beyond the plan: `**` and `?` semantics, an unknown spec key, an accepted opaque tool, secret-file globs, and a `.git` non-match.

Decisions as the plan states them and the orchestrator accepted them: the lifespan slot after `pii_policy.load`, the interim `load()` failing closed, `tool.opaque` as `Rule(None, None)`, built-in-only `protected_paths`, `OPENROUTER_*` in `secrets.env`, and the glob semantics including `id_*`.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_action_config.py` | AC 1 no-file-read and fail-closed; AC 2 rules table, non-grantable (parametrized ×10), grants, `tool.opaque`, tools identity, opaque empty + `Unknown()` for 5 `none` tools, protected/secret globs, empty lists, compiled-once, immutability; glob match/non-match contract; AC 3 subprocess + in-process; AC 4 stable digest, changes (default/grant/network_allow), key-order independence; `_validate` floor (missing/unknown rule, bad decision, bad grant, grant on each non-grantable, `tool.opaque` default, empty tools, non-ToolMapping, bad opaque decision, opaque also in tools, bad globs ×7, bad secret file glob, env glob with `/`, unknown spec key) — 94 tests |
| `tests/test_main.py` | `test_lifespan_runs_action_config_load_after_authz_load`, `test_lifespan_keeps_the_built_in_action_policy_when_unset`, `test_lifespan_fails_when_action_policy_file_cannot_be_loaded` |
| `tests/test_chat_ui_startup_guard.py` | `test_action_config_load_registered_after_authz_load_as_chat_ui_lifespan_task`, `test_action_config_load_is_a_noop_when_action_policy_file_unset`, `test_action_config_load_fails_chat_ui_startup_when_a_file_is_set` |

## Acceptance Criteria

- [x] `ACTION_POLICY_FILE=""`: no file opened, `get_policy() is BUILT_IN_POLICY` (`test_load_reads_no_file_when_action_policy_file_unset`)
- [x] Built-in policy matches PRD 6.3/6.6 (`test_built_in_rules_are_prd_section_6_3` and siblings)
- [x] `get_policy()` before any `load()` (`test_get_policy_before_load_returns_the_built_in_policy`)
- [x] Digest stable and sensitive to a one-rule change (`test_policy_digest_is_stable`, `test_policy_digest_changes_with_one_change[default]`)
- [x] Both lifespans, after `authz.load()` (`test_lifespan_runs_action_config_load_after_authz_load`, `test_action_config_load_registered_after_authz_load_as_chat_ui_lifespan_task`)
