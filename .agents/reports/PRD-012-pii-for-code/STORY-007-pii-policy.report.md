---
story: STORY-007
prd: PRD-012
plan: .agents/plans/PRD-012-pii-for-code/completed/STORY-007-pii-policy.plan.md
epic_branch: epic/PRD-012-pii-for-code
commit: pending
status: COMPLETE
completed: 2026-09-25
---

# Implementation Report — STORY-007: pii_policy: built-in chat and code policies, profile fallback, load() in both lifespans

**Plan**: `.agents/plans/PRD-012-pii-for-code/completed/STORY-007-pii-policy.plan.md`
**Epic Branch**: `epic/PRD-012-pii-for-code`
**Commit**: `pending`

## Summary

This story adds `app/services/pii_policy.py`:

- `PiiPolicy`, a frozen dataclass with the eight fields of PRD Section 6.2. Its `input_roles` field is typed with PRD-010's `Role`.
- `PiiConfigError`.
- `FALLBACK_POLICY_NAME = "chat"`.
- The two built-in policies, built from `settings` by private builders (`_build_chat_policy`, `_build_code_policy`).
- `get_pii_policy(name)`, which returns `chat` for any name it does not know. It never raises and never logs.
- `load()`, which does the following in order:
  1. rebuilds both policies from `settings`;
  2. refuses the one inconsistent combination (`skip_fenced_blocks` without `structure_safe`);
  3. logs one INFO line, in sorted order, for each profile in the loaded pattern policy that has no PII policy;
  4. rebinds the private `_policies` as its last statement, so a failed load leaves the previous policies in force.

The policies are built once at import, so `get_pii_policy()` works before `load()` runs. This is the same get/load split `pattern_config` uses.

`load()` now runs directly after `pattern_config.load()` in both lifespans: `app/main.py`, and the chat UI's lifespan task list in `chat_ui/chat_ui/chat_ui.py`. A new autouse fixture in `tests/conftest.py` restores the policies after every test.

Nothing on the request path reads the module yet. STORY-008 and STORY-009 are its consumers. `pii_policy` does not import `pii_redactor`, so STORY-008 can import `PiiPolicy` into the redactor without an import cycle.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Create the policy module | `app/services/pii_policy.py` | ✅ |
| 2 | Autouse `_default_pii_policy` restore fixture | `tests/conftest.py` | ✅ |
| 3 | Unit tests for AC 1–4 and `PiiConfigError` | `tests/test_pii_policy.py` | ✅ |
| 4 | `pii_policy.load()` after `pattern_config.load()` | `app/main.py` | ✅ |
| 5 | Register `pii_policy.load` after `pattern_config.load` | `chat_ui/chat_ui/chat_ui.py` | ✅ |
| 6 | FastAPI lifespan tests (order, config error stops boot, settings reach the policy) | `tests/test_main.py` | ✅ |
| 7 | Reflex lifespan probe (registration and order, no-op load, forced `PiiConfigError`) | `tests/test_chat_ui_startup_guard.py` | ✅ |
| 8 | Regression sweep | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A (no linter configured, no npm frontend, no UI change) |
| `tests/test_pii_policy.py` | ✅ 20 passed |
| `tests/test_main.py` | ✅ 19 passed |
| `tests/test_chat_ui_startup_guard.py` | ✅ 11 passed |
| Regression subset (pattern config/profiles, multiturn schema test, PII redactor/characterization/pattern analyzer) | ✅ 202 passed |
| Protected files unchanged (`git diff --exit-code`) | ✅ |
| Full suite | ✅ with two infrastructure flakes (see below): 2951 passed and 26 skipped in each of two runs |
| Mutation check: each lifespan registration removed | ✅ Reflex: 2 new tests fail (the default no-op test still passes, as it should); FastAPI: all 3 new tests fail |
| E2E | ✅ 5/5 |

**Full-suite flakes.** Each of the two full runs had exactly one failure, and it was a different test each time. Every test passed in at least one full run, and each failing test also passes when rerun on its own.

- Run 1: `tests/test_chat_state.py::test_new_chat_then_a_send_creates_exactly_one_session` errored in setup. It passes alone, and `test_chat_state.py` passes 140/140 on its own.
- Run 2: `tests/test_query_pipeline_run_conversation.py::test_every_message_is_redacted_before_it_leaves_the_process` failed with libSQL `STREAM_EXPIRED` ("The stream has expired due to inactivity"), a dev-server connection timeout. Its file passes 18/18 on its own.

Neither test touches `pii_policy`. This matches PRD Section 11: "Mass fixture errors mean restart the libSQL dev container, not bisect code."

## E2E

| # | Check | Result |
|---|-------|--------|
| 1 | `g('chat').output and not g('code').output and g('anything') is g('chat')` | ✅ |
| 2 | Boot `app.main:app` (local libSQL, RBAC off). `/health` returns 200 and no `pii policy:` line is logged under the built-in pattern policy. | ✅ 0 lines |
| 3 | Boot with `PATTERNS_FILE` set to `examples/patterns.yaml` plus a `strict` profile: exactly one INFO line | ✅ `pattern profile 'strict' has no PII policy; it resolves to 'chat'` |
| 4 | Chat UI probe: registered directly after `pattern_config.load`; forced inconsistency raises `PiiConfigError` | ✅ |
| 5 | `/query` regressions (`test_query_outcomes_regression.py`, `test_pii_redaction_integration.py`) pass with no assertion changed | ✅ |

The E2E boots used `DATABASE_URL=http://127.0.0.1:8080`, not the `.env` Turso URL, so no remote database was touched.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/pii_policy.py` | CREATE | +211 |
| `tests/test_pii_policy.py` | CREATE | +307 |
| `app/main.py` | UPDATE | +2/-1 |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | +6/-1 |
| `tests/conftest.py` | UPDATE | +15 |
| `tests/test_main.py` | UPDATE | +61 |
| `tests/test_chat_ui_startup_guard.py` | UPDATE | +60 |

## Deviations from Plan

1. **Extra unit test**: `test_code_settings_do_not_touch_chat` pins PRD Section 9.3: the six code settings apply to `code` only. The plan did not list it.
2. **`test_built_in_policies_pass_the_consistency_check`** is parametrized over `PII_CODE_SKIP_CODE_BLOCKS` True/False rather than written as a single case, so both settings of the only field the check reads are covered.
3. **E2E 2/3 launcher.** The plan's E2E said to boot with `uvicorn app.main:app`. A plain uvicorn boot would not have shown the INFO line (finding below), so the E2E booted through `logging.basicConfig(level=INFO)` and then `uvicorn.run(...)`.

## Finding (pre-existing, out of scope)

**`app.*` INFO logs are not printed under a plain uvicorn boot.**

- `LOG_LEVEL` is defined in `app/config.py:114` and documented in the README configuration table, but nothing reads it.
- Nothing calls `logging.basicConfig` or `dictConfig`.
- So the root logger stays at WARNING with no handler, and INFO records from `app.*` loggers are dropped. Python's last-resort handler prints only WARNING and above.

This story's fallback line is emitted, as the caplog tests and the E2E launcher show, but an operator running the stock image will not see it until application logging is configured. It is left as found for two reasons: the AC asks for an INFO line, and wiring `LOG_LEVEL` changes logging for the whole app. It is recorded here so a later story (STORY-014's docs sweep, or PRD-013's telemetry work) can wire `LOG_LEVEL` to the root logger.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_pii_policy.py` | frozen dataclass with Section 6.2 fields; `Role` vocabulary; chat matches the 6.2 table; chat reads `PII_ENTITIES`/threshold at load; code defaults; `PII_CODE_REDACT_SYSTEM` adds system; output/skip booleans map as named (×2); code reads entities/threshold/limit; code settings do not touch chat; fallback name is chat; unknown name gives chat, not code; works before load; `get_pii_policy` never logs; no log under the built-in pattern policy; one sorted INFO line per extra profile; `PiiConfigError` for skip without structure-safe (previous policies intact); built-ins pass the check (×2); failed load logs nothing |
| `tests/test_main.py` | lifespan runs `pii_policy.load` after `pattern_config.load`; `PiiConfigError` stops the FastAPI boot and keeps the previous policies; lifespan load reflects patched settings |
| `tests/test_chat_ui_startup_guard.py` | registered directly after `pattern_config.load`; no-op by default; forced `PiiConfigError` fails chat UI startup |

## Handoff (for later stories)

- **STORY-008**:
  - `from app.services.pii_policy import PiiPolicy` is cycle-free.
  - Read `entities`, `threshold`, `skip_fenced_blocks` and `structure_safe`.
  - `PII_REDACTION_ENABLED` is not in the policy, so `redact_for_policy` must apply it itself.
  - For a policy to test with, use `dataclasses.replace(get_pii_policy("code"), ...)`.
- **STORY-009**:
  - Call `get_pii_policy(profile_name)` once per request, with the name step 5 resolves. It never raises and never logs.
  - Tests that patch `PII_*` settings must call `pii_policy.load()`; conftest restores the policies afterwards.
- **STORY-010**: `policy.max_characters` is `None` for `chat` and `PII_MAX_CHARACTERS_CODE` for `code`.
- **STORY-014**: see the `LOG_LEVEL` finding above before the README claims the fallback is visible in logs.

## Acceptance Criteria

- [x] Given `app/services/pii_policy.py`, when it is read, then the frozen `PiiPolicy` dataclass has the fields of PRD Section 6.2 (`name`, `input_roles`, `output`, `skip_fenced_blocks`, `entities`, `threshold`, `max_characters`, `structure_safe`), using PRD-010's `Role` type.
- [x] Given the built-in `chat` policy, when it is built, then it matches the Section 6.2 table exactly: every role, output on, no fence skipping, `PII_ENTITIES`, `PII_SCORE_THRESHOLD`, `max_characters=None`, `structure_safe=False`.
- [x] Given the built-in `code` policy, when it is built with default settings, then `input_roles` is `{user, assistant, tool}`, output off, fence skipping on, `PII_ENTITIES_CODE`, `PII_SCORE_THRESHOLD_CODE`, `PII_MAX_CHARACTERS_CODE`, `structure_safe=True`; with `PII_CODE_REDACT_SYSTEM=true` it adds `system`, and the other two booleans map as named.
- [x] Given `get_pii_policy(name)` with a name that is neither `chat` nor `code`, when it is called, then it returns `chat`. Given `load()` at startup, then it logs one INFO line per profile name in the loaded pattern policy that has no PII policy, naming it and saying it resolves to `chat`.
- [x] Given `app/main.py` and `chat_ui/chat_ui/chat_ui.py`, when each lifespan starts, then `pii_policy.load()` runs after `pattern_config.load()`, and a `PiiConfigError` stops the boot.
- [x] All tasks completed
- [x] Backend imports and the FastAPI app starts without error
- [x] Full test suite green apart from the libSQL infrastructure flakes above; no assertion changed in the PRD Section 11 protected files
- [x] Follows existing patterns (`pattern_config` get/load split, conftest restore fixture, lifespan probe)
