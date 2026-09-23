---
story: STORY-007
prd: PRD-011
plan: .agents/plans/PRD-011-pattern-policy/completed/STORY-007-startup-load-and-sample-file.plan.md
epic_branch: epic/PRD-011-pattern-policy
commit: efb1924
status: COMPLETE
completed: 2026-09-22
---

# Implementation Report — STORY-007: pattern_config.load() in both lifespans, and a working sample file

**Plan**: `.agents/plans/PRD-011-pattern-policy/completed/STORY-007-startup-load-and-sample-file.plan.md`
**Epic Branch**: `epic/PRD-011-pattern-policy`
**Commit**: `efb1924`

## Summary

`pattern_config.load()` now runs at startup in both entry points. In each one it runs right after `authz.load()` and before `authz.check_bootstrap()`.

- **`app/main.py`'s lifespan** serves uvicorn and the test client.
- **`chat_ui/chat_ui/chat_ui.py`** registers `load()` as a Reflex lifespan task. Production runs this path, and `api_transformer`'s mount keeps it from ever reaching `app.main`'s lifespan.

A malformed `PATTERNS_FILE` now stops both processes with `PatternConfigError`. This was checked on a real uvicorn launch and a real `reflex run --env prod --backend-only` launch, not only in tests. With `PATTERNS_FILE` unset, no file is read and the built-in policy stays in force.

`examples/patterns.yaml` is PRD Section 6.3 byte for byte. A test loads it through `load()` and asserts that the result `==` `BUILT_IN_POLICY`. It also asserts declared order, and that a new policy object was actually built, so the equality can't pass trivially.

This is the first story in PRD-011 where production code runs pattern-policy code. It only happens at startup. Nothing on the request path reads the policy until STORY-008.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Import `pattern_config`; `pattern_config.load()` between `authz.load()` and `authz.check_bootstrap()` | `app/main.py` | ✅ |
| 2 | `app.register_lifespan_task(pattern_config.load)` directly after `authz.load`, with a "same bypass (PRD-011 STORY-007)" comment | `chat_ui/chat_ui/chat_ui.py` | ✅ |
| 3 | Pattern-settings header comment no longer claims "no production code reads these yet" | `app/config.py` | ✅ |
| 4 | Sample file, extracted from the PRD's Section 6.3 fence and verified equal (`verbatim: OK`) | `examples/patterns.yaml` | ✅ |
| 5 | Sample loads to `BUILT_IN_POLICY`, with declared order checked | `tests/test_pattern_config.py` | ✅ |
| 6 | FastAPI lifespan: malformed file fails, sample loads, unset reads no file | `tests/test_main.py` | ✅ |
| 7 | Reflex probe: registration, adjacency, no-op, malformed-file failure | `tests/test_chat_ui_startup_guard.py` | ✅ |
| 8 | Full regression | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`python -c "from app.main import app"`) | ✅ |
| Frontend lint | N/A. No linter is configured in this repository; `pytest` is the only gate |
| Tests | ✅ 2470 passed, 26 skipped (`pytest -q`, 330 s) |
| Removal checks | ✅ With `pattern_config.load()` removed from `app/main.py`, the malformed-file and sample tests fail (2). With the Reflex registration removed, the registration and malformed-file tests fail (2). Restored afterwards |
| Sample drift check | ✅ With `override` → `overrides` in the sample, the equality test fails. Reverted afterwards |
| E2E | ✅ 5/5 |

### E2E detail

All launches used environment overrides so they would not touch the Turso database configured in `.env`: `DATABASE_URL=http://127.0.0.1:8080` (local libSQL dev server), `RBAC_ENABLED=false` (that database has no seeded users), and `PII_REDACTION_ENABLED=false`. None of these affect the pattern load.

| # | Check | Outcome |
|---|-------|---------|
| 1 | `uvicorn app.main:app` with a malformed file (`mach: word`) | Exit 3. `PatternConfigError: PATTERNS_FILE '…/bad.yaml': list 'injection': unknown key 'mach' (expected one of: match, patterns, scope)`, then `Application startup failed`. No port bound |
| 2 | uvicorn with `PATTERNS_FILE=examples/patterns.yaml` | Startup complete; `/health` → `{"status":"ok"}`. Checked separately that the path resolves and the file loads to a new policy equal to the built-in one |
| 3 | uvicorn with `PATTERNS_FILE` unset | Startup complete; `/health` → `{"status":"ok"}` |
| 4 | `reflex run --env prod --backend-only` with the malformed file | Exit 1. `ASGI lifespan startup failed` with the same `PatternConfigError`. No backend listening |
| 5 | The same Reflex command with the sample file | `App running`; `/health` → `{"status":"ok"}`. Stopped afterwards, including its orphaned multiprocessing worker; port 8766 verified free |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/main.py` | UPDATE | +2/-1 |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | +7/-1 |
| `app/config.py` | UPDATE | +5/-3 (comment only) |
| `examples/patterns.yaml` | CREATE | +30 |
| `tests/test_pattern_config.py` | UPDATE | +29 |
| `tests/test_main.py` | UPDATE | +94 |
| `tests/test_chat_ui_startup_guard.py` | UPDATE | +92/-3 (the 3 removed lines are module-docstring prose) |
| `.agents/plans/PRD-011-pattern-policy/completed/STORY-007-startup-load-and-sample-file.plan.md` | CREATE (archived) | +398 |

## Deviations from Plan

1. **The Reflex malformed-file test also asserts registration.** The plan's Task 7 check expected both the registration test and the malformed-file test to fail once the registration was removed. Only the registration test failed. The probe calls `load()` by hand, so a raise on its own proves nothing about startup. `assert result["patterns_load_registered"] is True` was added to the malformed-file test, and the docstring says why. The removal check was re-run, and both tests now fail without the registration.
2. **The Reflex E2E ran for real.** The plan allowed falling back to the subprocess probe if running Reflex locally was impractical. It wasn't needed.
3. **`examples/patterns.yaml` is committed with LF endings.** Git warns it may become CRLF in a Windows working copy. That changes bytes on disk, not the parsed policy, and the equality test is the ongoing guard (plan D-G).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_pattern_config.py` | `test_examples_patterns_yaml_loads_to_the_built_in_policy` |
| `tests/test_main.py` | `test_lifespan_fails_when_patterns_file_is_malformed`, `test_lifespan_loads_patterns_file_before_serving_requests`, `test_lifespan_reads_no_patterns_file_when_unset` |
| `tests/test_chat_ui_startup_guard.py` | `test_pattern_config_load_registered_as_chat_ui_lifespan_task`, `test_pattern_config_load_is_a_noop_when_patterns_file_unset`, `test_pattern_config_load_fails_chat_ui_startup_on_malformed_file` |

No existing assertion changed:

- `test_query_router.py`, `test_integration.py`, `test_query_outcomes_regression.py`, `test_chat_outcomes_regression.py` and `test_history_off_integration.py` are untouched.
- In `test_chat_ui_startup_guard.py`, `_empty_rbac_env` now also pins `PATTERNS_FILE=""` and `PATTERN_PROFILE_DEFAULT=chat`. This is additive and commented. The probe's existing result keys are unchanged.

## Acceptance Criteria

- [x] `app/main.py`'s lifespan runs `pattern_config.load()` beside `authz.load()`, and a `PatternConfigError` propagates: the process does not start. (`test_lifespan_fails_when_patterns_file_is_malformed`; E2E 1)
- [x] `chat_ui/chat_ui/chat_ui.py` runs `pattern_config.load()` when the Reflex backend starts with the FastAPI app mounted through `api_transformer`. (Registration and adjacency test; E2E 4 and 5)
- [x] `examples/patterns.yaml` is PRD Section 6.3 verbatim, comments included, and a test loads it through `load()` and asserts the policy equals the built-in one. (Task 4 check; `test_examples_patterns_yaml_loads_to_the_built_in_policy`)
- [x] With `PATTERNS_FILE` pointed at a malformed file, startup fails with `PatternConfigError`, asserted for both entry points. (`tests/test_main.py` and `tests/test_chat_ui_startup_guard.py`)
- [x] With no `PATTERNS_FILE`, no file is read, the built-in policy stands, and no existing startup test changes. (`test_lifespan_reads_no_patterns_file_when_unset`, the Reflex no-op test, E2E 3; existing startup tests green and unedited)
