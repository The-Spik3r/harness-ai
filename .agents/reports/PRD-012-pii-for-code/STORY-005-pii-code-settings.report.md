---
story: STORY-005
prd: PRD-012
plan: .agents/plans/PRD-012-pii-for-code/completed/STORY-005-pii-code-settings.plan.md
epic_branch: epic/PRD-012-pii-for-code
commit: pending
status: COMPLETE
completed: 2026-09-25
---

# Implementation Report — STORY-005: Six PII code-profile settings with startup validators

**Plan**: `.agents/plans/PRD-012-pii-for-code/completed/STORY-005-pii-code-settings.plan.md`
**Epic Branch**: `epic/PRD-012-pii-for-code` (BASE `aad98b1`, plan commit `df66dfa`)
**Commit**: pending

## Summary

`app/config.py` has a new PRD-012 group of six settings. It sits after the PRD-011 group, so the `:82-85` lines that `tests/test_pii_characterization.py` cites have not moved.

| Setting | Default | Source |
|---|---|---|
| `PII_ENTITIES_CODE` | `EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE` | STORY-003 R4 / D7; equals `scripts/measure_pii_latency.PATTERN_ENTITIES` |
| `PII_SCORE_THRESHOLD_CODE` | `0.40` | STORY-003 R1 |
| `PII_MAX_CHARACTERS_CODE` | `200_000` | STORY-003 R3 |
| `PII_CODE_REDACT_OUTPUT` | `False` | D1 |
| `PII_CODE_REDACT_SYSTEM` | `False` | D3 |
| `PII_CODE_SKIP_CODE_BLOCKS` | `True` | D2 |

The module also gained the following:

- **`_PRESIDIO_ENTITY_NAMES`.** These are the 20 names in Presidio 2.2.364's default English registry. The constant exists so `Settings` never loads an analyzer, and a test compares it to the live registry.
- **`_split_comma_list`.** This is the parsing `pii_entities_list` does. The new validator and the new property use it. The two existing properties are unchanged.
- **`_validate_pii_entities_code`.** It rejects an empty list or an unknown name. The message names the setting, the bad name, the full value and all accepted names. For an empty value it also names `PII_REDACTION_ENABLED=false` as the real off switch.
- **`_validate_pii_score_threshold_code`.** It requires the value to be in `[0, 1]`. The check is written as `not 0 <= value <= 1`, so NaN is rejected too.
- **`PII_MAX_CHARACTERS_CODE`.** It was added to `_POSITIVE_LIMIT_DESCRIPTIONS` and to `_validate_positive_limit`, so its message is the same `"… must be at least 1, got N. It is …"` shape the other limits use. The PRD's `_RESOURCE_BOUNDS` does not exist; this dict is the one it meant (plan F-1).
- **`pii_entities_code_list`**, the new property.

Nothing reads the new fields yet. Each field's comment names its consumer: STORY-006, STORY-007 or STORY-010. The four existing `PII_*` settings, `pii_entities_list` and `model_allowlist_list` are unchanged.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Constant, helper, positive-limit entry, six fields, two validators, property | `app/config.py` | ✅ |
| 2 | PRD-012 STORY-005 test block (AC 1-5) | `tests/test_config.py` | ✅ |
| 3 | Regression sweep | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Frontend lint | N/A. The repo has no npm frontend, and no UI changed |
| `tests/test_config.py` | ✅ 117 passed (70 before, plus 47 new) |
| PII-related sweep: `test_config`, `test_pii_characterization`, `test_pii_redactor`, `test_measure_pii_latency`, `test_pii_corpus_files`, `test_conftest_fixtures` | ✅ 246 passed |
| Full suite (`pytest -q`, local libSQL on :8080) | ✅ 2890 passed, 26 skipped. This is the second run; see Deviation 3 |
| E2E | ✅ 6/6, plus the `/health` smoke test |

### E2E

- [x] `import app.main` works with no `.env` change. The new defaults validate.
- [x] `PII_ENTITIES_CODE=EMAIL_ADDRESS,FOO` exits with code 1. The message names `PII_ENTITIES_CODE`, `FOO`, the full value and all 20 accepted names.
- [x] `PII_SCORE_THRESHOLD_CODE=1.5` exits with code 1: `must be between 0 and 1, got 1.5. It is the minimum Presidio confidence …`.
- [x] `PII_MAX_CHARACTERS_CODE=0` exits with code 1: `must be at least 1, got 0. It is the analyzable characters per request …`.
- [x] `PII_ENTITIES_CODE=PERSON,EMAIL_ADDRESS` is accepted and parses as `['PERSON', 'EMAIL_ADDRESS']`. This is the NER opt-in, plan decision P3.
- [x] The diff touches only `app/config.py` and `tests/test_config.py`, plus this story's `.agents/` files. `.env.example`, the README and `app/services/*` are untouched.
- [x] Smoke test: `uvicorn app.main:app` started, and `GET /health` returned `200 {"status":"ok"}`. The server was then stopped.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/config.py` | UPDATE | +134/-2 |
| `tests/test_config.py` | UPDATE | +208 |

## Deviations from Plan

1. **The plan was committed first, on its own** (`df66dfa docs(PRD-012): STORY-005 plan`). This follows STORY-004's `b0bb393`.
2. **The threshold test quotes the value for every case, not only the numeric ones.** `float("nan")` and `float("inf")` format as `nan` and `inf`, which is exactly what the message prints. So `f"got {float(value)}"` holds for all seven parameters, and the plan's "numeric cases only" restriction wasn't needed. The tests also share a small `_assert_pii_code_defaults` helper, used by the defaults test and the `delenv` test, instead of repeating six assertions.
3. **One failure in the first full run did not repeat.** `tests/test_chat_outcomes_regression.py::test_each_outcome_renders_its_kind_and_persists_one_bubble[success]` failed once. It passed alone, passed with its module (22 passed), and passed in the second full run (2890 passed). That test drives the chat UI through the database and does not read any new setting. The first run started seconds after the libSQL container had been started. That the failure came from the container not yet being ready is a guess; it was not confirmed.
4. **The precondition needed Docker Desktop to be launched.** It was not running (plan F-6). Once it was up, `harness-libsql-dev` started, and the conftest's pre-existing `test_settings_construct_without_new_env_vars` (which fails under `--noconftest`) passes.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_config.py` (PRD-012 STORY-005 block, 47 cases) | `test_pii_code_settings_available_with_documented_defaults`; `test_pii_entities_code_default_is_the_benchmarked_pattern_list`; `test_pii_code_bools_parse_the_strings_a_dotenv_supplies`; `test_settings_construct_without_the_pii_code_vars`; `test_an_empty_pii_entities_code_is_a_startup_error` ×3; `test_an_unknown_pii_entity_code_is_a_startup_error` ×3 (unknown name, lowercase name, near-miss `PASSPORT`); `test_every_known_entity_name_is_accepted_alone` ×20; `test_known_entity_names_match_presidios_default_registry`; `test_known_entity_names_cover_todays_pii_entities`; `test_a_pii_score_threshold_code_outside_zero_to_one_is_a_startup_error` ×7 (incl. `nan`, `inf`); `test_pii_score_threshold_code_accepts_both_boundaries`; `test_a_pii_max_characters_code_below_one_is_a_startup_error` ×3; `test_pii_max_characters_code_accepts_the_boundary_value_of_one`; `test_pii_entities_code_list_parses_like_pii_entities_list`; `test_existing_pii_settings_keep_their_defaults`; `test_existing_pii_settings_gained_no_validation` |

## For later stories

- **STORY-006:** `_PRESIDIO_ENTITY_NAMES` accepts `NRP`, `ORGANIZATION` and `DATE_TIME`. Presidio's `SpacyRecognizer` serves all three, and `DATE_TIME` is also served by the pattern `DateRecognizer`. The PRD's "NER type" set is only `{PERSON, LOCATION}`. STORY-006 must decide whether these three also select the full analyzer. The safe reading is that they do.
- **STORY-007:** read the six settings from `settings`. `pii_entities_code_list` is the parsed entity list, and `PII_REDACTION_ENABLED` stays the master switch.
- **STORY-014:** `.env.example` needs the six settings in field order, each with a comment line. Numbers go without underscores (`200000`) and bools in lowercase. The `.env.example` tests follow `tests/test_config.py`'s per-group pattern.

## Acceptance Criteria

- [x] Given `app/config.py`, when it is read, then `PII_ENTITIES_CODE`, `PII_SCORE_THRESHOLD_CODE`, `PII_MAX_CHARACTERS_CODE`, `PII_CODE_REDACT_OUTPUT` (`False`), `PII_CODE_REDACT_SYSTEM` (`False`) and `PII_CODE_SKIP_CODE_BLOCKS` (`True`) exist, with the entity list, threshold and size limit defaults taken from the STORY-003 report.
- [x] Given `PII_ENTITIES_CODE` empty or naming an unknown entity type, when `Settings` is constructed, then it raises with a message naming the setting, the bad value and the accepted names.
- [x] Given `PII_SCORE_THRESHOLD_CODE` outside `[0, 1]`, or `PII_MAX_CHARACTERS_CODE < 1`, when `Settings` is constructed, then it raises with the `_RESOURCE_BOUNDS`-style message (`_POSITIVE_LIMIT_DESCRIPTIONS`).
- [x] Given a `pii_entities_code_list` property, when it is read, then it parses like `pii_entities_list`.
- [x] Given the existing four `PII_*` settings, when this story lands, then their names, defaults and validation are unchanged.
- [x] All tasks completed
- [x] Full test suite passes
- [x] App imports and starts without error
- [x] Follows existing patterns
