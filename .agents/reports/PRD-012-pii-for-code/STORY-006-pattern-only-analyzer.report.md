---
story: STORY-006
prd: PRD-012
plan: .agents/plans/PRD-012-pii-for-code/completed/STORY-006-pattern-only-analyzer.plan.md
epic_branch: epic/PRD-012-pii-for-code
commit: pending
status: COMPLETE
completed: 2026-09-25
---

# Implementation Report — STORY-006: Pattern-only analyzer, selected by the entity list

**Plan**: `.agents/plans/PRD-012-pii-for-code/completed/STORY-006-pattern-only-analyzer.plan.md`
**Epic Branch**: `epic/PRD-012-pii-for-code` (BASE `042af3e`, plan commit `745643f`)
**Commit**: `pending`

## Summary

`app/services/pii_redactor.py` now has a second Presidio analyzer. It runs over `spacy.blank("en")` plus one component, `pii_lower_as_lemma`, which copies each token's lower-cased text into its lemma. This is STORY-003's `subclass+lemma` route.

**Which analyzer is used.** `_get_analyzer(entities=None)` decides:

| Call | Analyzer returned |
|---|---|
| `_get_analyzer()` | today's full analyzer over `PII_NLP_MODEL`, unchanged |
| a list containing any type in `_NER_ENTITY_TYPES` | the same full analyzer |
| any other list | the tokenizer-only analyzer |

**The NER set.** `_NER_ENTITY_TYPES` = `PERSON, LOCATION, ORGANIZATION, NRP, DATE_TIME`. These are exactly the types Presidio's `SpacyRecognizer` serves. Each member carries a comment saying why it is there, and a test pins the set to the live recognizer.

**Singletons.** Both analyzers are lazy module singletons, and each has its own builder. `_build_analyzer` is untouched.

**`load()`.** At startup it builds today's analyzer first, then the one `PII_ENTITIES_CODE` selects. If `PII_ENTITIES_CODE` contains a NER type, that second call returns the full analyzer, and nothing else is built. If the tokenizer-only analyzer cannot be built, `load()` raises `PiiRedactorError` naming `PII_ENTITIES_CODE`. That stops both boots. It never falls back to the full analyzer.

**`redact()`.** It keeps calling `_get_analyzer()` with no argument, so `chat` stays on the full analyzer whatever `PII_ENTITIES` holds.

**Not wired in yet.** Nothing on the request path uses the new analyzer. STORY-008's `redact_for_policy` is its consumer.

**Measured.** The tokenizer-only analyzer builds in about 150 ms, with no download and no `spacy.load`. On `jane@example.com called 415-555-0134` it returns `EMAIL_ADDRESS (0,16) 1.0` and `PHONE_NUMBER (24,36) 0.75`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Preflight: on the epic branch, clean tree, plan committed (`745643f`), libSQL container up, baseline of the affected suites 220 passed | — | ✅ |
| 1 | `_NER_ENTITY_TYPES`, `pii_lower_as_lemma`, `_TokenizerOnlySpacyNlpEngine`, `_pattern_analyzer`, `_build_pattern_analyzer`, `_get_analyzer(entities=None)`, `load()` builds both | `app/services/pii_redactor.py` | ✅ |
| 2 | Comment above `PII_ENTITIES_CODE` now names the NER set | `app/config.py` | ✅ |
| 3 | AC 1-4 tests, NER-set drift guard, chat-invariance guard | `tests/test_pii_pattern_analyzer.py` | ✅ |
| 4 | Lifespan block: both analyzers built at startup; a build failure stops the boot | `tests/test_main.py` | ✅ |
| 5 | AC 5 proof, targeted sweep, full suite | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK. Importing builds no analyzer |
| Frontend lint | N/A. The repo has no npm frontend, and no UI changed |
| `tests/test_pii_pattern_analyzer.py` | ✅ 34 passed |
| `tests/test_main.py` | ✅ 16 passed: 14 existing, unchanged, plus 2 new |
| AC 5: `git diff --exit-code HEAD -- tests/test_pii_redactor.py tests/test_pii_characterization.py` | ✅ no diff; both files pass |
| Targeted sweep (redactor, characterization, pattern analyzer, main, benchmark, pipeline concurrency, config) | ✅ 260 passed, 1 skipped. The skip is the pre-existing manual `HARNESS_SLOW_SMOKE` test |
| Full suite (`pytest -q`, libSQL on :8080) | ✅ **2926 passed, 26 skipped, 0 failed** in 4:53. That is 2890 at STORY-005 plus 36 new |
| Mutation check (not in the plan) | ✅ Forcing every list onto the full analyzer (`if True:` in `_get_analyzer`) turned 20 of the 34 new tests red, including the no-fallback test and the AC 4 spy test. The code was then restored and re-run green |
| E2E | ✅ 6/6 |

### E2E

- [x] `import app.main` is clean. Straight after the import, `_analyzer` and `_pattern_analyzer` are both `None`.
- [x] The Task 1 one-liner printed `_TokenizerOnlySpacyNlpEngine ['pii_lower_as_lemma'] True`, then `[('EMAIL_ADDRESS', 0, 16, 1.0), ('PHONE_NUMBER', 24, 36, 0.75)]`.
- [x] `uvicorn app.main:app --port 8001` with the shipped config built lg and the tokenizer-only analyzer. It reached "Application startup complete" in about 4 s, and `GET /health` returned `200 {"status":"ok"}`. The server was then stopped.
- [x] With `PII_ENTITIES_CODE=PERSON,EMAIL_ADDRESS`, the same boot served `/health` 200 in about 3 s, then was stopped. That only the full analyzer is built in this case is asserted in `test_load_with_a_ner_type_in_code_entities_builds_only_the_full_analyzer`.
- [x] Startup timing: `_get_analyzer(['EMAIL_ADDRESS'])` cold took 147 ms.
- [x] `git diff --stat HEAD` touched only `app/services/pii_redactor.py`, `app/config.py` (comment only), `tests/test_main.py` and the new `tests/test_pii_pattern_analyzer.py`. Nothing changed under `scripts/`, `app/main.py`, `chat_ui/`, `.env.example`, the README or the two AC 5 files.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/pii_redactor.py` | UPDATE | +96/-7 |
| `app/config.py` | UPDATE (comment only) | +5/-4 |
| `tests/test_pii_pattern_analyzer.py` | CREATE | +272 |
| `tests/test_main.py` | UPDATE (appended block) | +57 |
| `.agents/plans/PRD-012-pii-for-code/completed/STORY-006-pattern-only-analyzer.plan.md` | MOVE (archived) | 0 |
| `.agents/reports/PRD-012-pii-for-code/STORY-006-pattern-only-analyzer.report.md` | CREATE | this file |

## Deviations from Plan

1. **The plan was committed first, on its own** (`745643f docs(PRD-012): STORY-006 plan`). This follows STORY-004's `b0bb393` and STORY-005's `df66dfa`.
2. **The new test module shares one `_counting(monkeypatch, name)` helper.** The plan described a separate counting wrapper in each test. The helper records the calls and returns the list. The behaviour is the same, with less repetition.
3. **The tests reach `PiiRedactorError` as `pii_redactor.PiiRedactorError`.** `tests/test_main.py` already imports the module, so its import block is unchanged.
4. **The `config.py` comment was reflowed over five lines.** The inserted type list pushed one line past the file's width. The words are the same except for the added set, and there is no code change.
5. **A mutation check was added to validation** (see the table above). It is not in the plan. It shows the new tests catch the failure the story forbids: a silent fallback to the full analyzer.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_pii_pattern_analyzer.py` (34) | `test_ner_entity_types_are_exactly_what_spacy_recognizer_serves`; `test_ner_entity_types_are_known_presidio_names`; `test_code_entities_select_the_tokenizer_only_analyzer`; `test_every_pattern_only_type_alone_selects_the_tokenizer_only_analyzer` ×15; `test_pattern_analyzer_constructed_only_once`; `test_tokenizer_only_analyzer_keeps_context_boosts`; `test_a_ner_type_selects_the_full_analyzer` ×7; `test_no_argument_is_the_full_analyzer`; `test_redact_uses_the_full_analyzer_even_with_a_pattern_only_pii_entities`; `test_load_builds_the_full_and_the_code_analyzer`; `test_load_with_a_ner_type_in_code_entities_builds_only_the_full_analyzer`; `test_load_is_a_noop_for_both_when_redaction_disabled`; `test_a_tokenizer_only_build_failure_is_a_startup_error_not_a_fallback`; `test_pattern_analyzer_detects_email_and_phone_without_touching_en_core_web_lg` |
| `tests/test_main.py` (2) | `test_lifespan_prebuilds_the_code_profiles_analyzer`; `test_lifespan_fails_when_the_tokenizer_only_analyzer_cannot_be_built` |

## For later stories

- **STORY-008 (`redact_for_policy`):**
  - Call `pii_redactor._get_analyzer(policy.entities)`, never `_get_analyzer()`. The no-argument form is `chat`'s full analyzer.
  - STORY-003's R3 chunking (line-aligned windows of 20,000 characters or fewer) is still STORY-008's to implement. This story does not chunk.
- **STORY-007:** there is nothing extra to build at startup. `pii_redactor.load()` already builds what `PII_ENTITIES_CODE` selects, and it stays zero-argument, because the Reflex lifespan registers it as-is.
- **STORY-014 (README):** under `code`, "NER type" means any of the five in `_NER_ENTITY_TYPES`. Adding one to `PII_ENTITIES_CODE` puts `code` on `en_core_web_lg`, at lg's cost.

## Acceptance Criteria

- [x] Given an entity list containing no NER type (`PERSON`, `LOCATION`, or any other NER-backed type Presidio defines), when `_get_analyzer(entities)` is called, then it returns the tokenizer-only analyzer the STORY-003 report found feasible (or the documented fallback), built once and cached. *It is the feasible `subclass+lemma` route; no fallback was needed.*
- [x] Given an entity list containing `PERSON`, when `_get_analyzer(entities)` is called, then it returns today's `en_core_web_lg` analyzer singleton, the same object `redact()` uses.
- [x] Given `pii_redactor.load()` with `PII_REDACTION_ENABLED=true`, when it runs at startup, then it builds today's analyzer as before **and** the analyzer `PII_ENTITIES_CODE` selects, so no analyzer is built on a request path.
- [x] Given the pattern-only analyzer, when it analyzes `jane@example.com called 415-555-0134`, then it returns `EMAIL_ADDRESS` and `PHONE_NUMBER` spans, and a spy on `en_core_web_lg` records no call.
- [x] Given `redact()`, when this story lands, then `test_pii_redactor.py` and `test_pii_characterization.py` pass unchanged.
- [x] All tasks completed
- [x] Backend imports and the server starts without error (`import app.main`; uvicorn `/health` 200)
- [x] Full pytest suite green (2926 passed, 26 skipped, 0 failed)
- [x] Follows existing patterns
