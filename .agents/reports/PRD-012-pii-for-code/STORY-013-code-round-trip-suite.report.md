---
story: STORY-013
prd: PRD-012
plan: .agents/plans/PRD-012-pii-for-code/completed/STORY-013-code-round-trip-suite.plan.md
epic_branch: epic/PRD-012-pii-for-code
commit: e828e2a
status: COMPLETE
completed: 2026-09-25
---

# Implementation Report — STORY-013: Code round-trip suite and the latency-budget assertion

**Plan**: `.agents/plans/PRD-012-pii-for-code/completed/STORY-013-code-round-trip-suite.plan.md`
**Epic Branch**: `epic/PRD-012-pii-for-code` (plan commit `00bfd9b`)
**Commit**: `e828e2a`

## Summary

PRD-012's MVP definition is now a green test. `tests/test_pii_code_corpus.py` runs the three corpora through the real `code` and `chat` policies, which `pii_policy.load()` builds from the shipped settings:

- **`code/` under `code`:**
  - every fenced block is byte-identical;
  - quotes, backslashes, backticks and line breaks keep their count and positions;
  - only placeholders differ between them, and each masked run holds its entity's anchor;
  - `.py` parses, `.json` parses, `.yaml` loads.
- **`prose/`:** declared entities are masked under `chat` (en_core_web_lg, shipped settings) and under `code`. `_ABSENT_UNDER_CODE = {PERSON}` is enumerated and asserted.
- **`json/`:** tool results parse, and number-token PII (phones, cards) becomes `"<TYPE>"`.
- **Non-vacuity:** `chat` changes every one of the 7 `code/` files.
- **Latency:** `@pytest.mark.benchmark` asserts `code` p95 at 200,000 characters < 1,500 ms. **Measured: 463.23 ms** (details below). It is skipped unless `--run-benchmark` is given.

**Two production bugs were found by this suite and fixed.** Both are in `app/services/pii_redactor.py`, both are `code`-only, and `chat` never reaches either:

| # | Bug | Effect before | Fix |
|---|---|---|---|
| F-1 | Presidio's email local part admits `'` and `=`, so in `email='patrick.obrien@example.org'` the span starts at `email`. Structure-safe splitting kept the quote but masked both runs | `billing_seed.py` became `<EMAIL_ADDRESS>'<EMAIL_ADDRESS>',`, a SyntaxError (AC 1's `ast.parse` failed) | **Anchored runs.** Outside JSON mode, a split email / phone / card / SSN / IBAN span masks only the runs holding `@` (email) or a digit (others). If no run holds its anchor, every run is masked, as before |
| F-4 | In a JSON string, the analyzer read the escape's letter as part of the next word: `\nGB82 …` → `nGB82`, `\t4111 …` → `t4111`. The IBAN and card recognizers need a word boundary | The IBAN and card in `build-log-escapes.json` went upstream **unmasked** (fail-open) | **Escapes blanked for the analyzer, JSON mode only.** Spaces of equal length keep offsets valid, the same trick as fence blanking. Replacement is unchanged |

F-1 was found while planning, and the plan fixed it. F-4 was found during implementation. It was raised with the user, who chose to fix it in this story rather than record it as a gap.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Anchored-run rule (F-1): `_RUN_ANCHORS`, `_anchored`, applied in `_replacement_ranges` outside JSON mode; docstrings | `app/services/pii_redactor.py` | ✅ |
| 2 | F-1 unit tests (7), appended; guard-bite observed | `tests/test_pii_structure_safe.py` | ✅ |
| 3 | M1 corpus entry and its provenance; M1 guard-bite observed | `tests/corpora/pii/json/build-log-escapes.json`, `tests/corpora/pii/SOURCES.md` | ✅ |
| 4 | `benchmark` marker, `--run-benchmark`, default skip | `tests/conftest.py` | ✅ |
| 5 | `code` arm, `_redact_policy_roles`, `CODE_P95_BUDGET_MS`, report lines; 3 pure tests | `scripts/measure_pii_latency.py`, `tests/test_measure_pii_latency.py` | ✅ |
| 6 | Suite scaffold and AC 1; guard-bite observed | `tests/test_pii_code_corpus.py` | ✅ |
| 7 | AC 2 (prose, both profiles) and AC 5 (chat non-vacuity) | `tests/test_pii_code_corpus.py` | ✅ |
| 8 | AC 3 (JSON tool results, number tokens, escape-adjacent PII) | `tests/test_pii_code_corpus.py` | ✅ |
| 9 | AC 4 benchmark test | `tests/test_pii_code_corpus.py` | ✅ |
| 10 | PRD Section 6.6 rules 1 and 2: one sentence each (F-1, F-4) | `.agents/PRDs/PRD-012-pii-for-code/PRD.md` | ✅ |
| 11 | Regression sweep | — | ✅ |
| 12 | Benchmark runs for this report | — | ✅ |
| + | F-4 fix (`_blank_escapes`), its 4 tests, guard-bite (not in plan; see Deviations) | `app/services/pii_redactor.py`, `tests/test_pii_structure_safe.py` | ✅ |
| + | Spike parity kept: `IndexedScheme` mirrors F-4 (not in plan; see Deviations) | `scripts/spike_pii_placeholders.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`python -c "import app.main"`) | ✅ OK |
| Frontend lint | n/a (no frontend, no linter configured, no UI change) |
| `tests/test_pii_code_corpus.py` | ✅ 70 passed, 1 skipped (the benchmark) |
| Benchmark (`-m benchmark --run-benchmark -s`) | ✅ 1 passed, p95 463.23 ms (E2E re-run: 460.05 ms) |
| PII group (structure-safe, policy, pattern analyzer, pipeline profiles, spike) | ✅ 326 passed |
| Corpus, script and spike tests | ✅ 169 passed |
| Full suite | ✅ 3326 passed, 27 skipped (26 pre-existing: `REPORTS_E2E_URL` ×25, `HARNESS_SLOW_SMOKE` ×1; plus the benchmark) |
| Protected files (`test_pii_redactor.py`, `test_pii_characterization.py`, `test_pii_redaction_integration.py`, `test_query_outcomes_regression.py`, `test_chat_outcomes_regression.py`, `pattern_detector.py`) | ✅ `git diff --exit-code` clean |
| `tests/test_pii_structure_safe.py` additions only | ✅ no removed line vs `HEAD` |
| E2E | ✅ 5/5 |

### Guard-bites (temporary mutations, each reverted, `grep -c MUTATION` = 0 afterwards)

| Mutation | Tests that failed |
|---|---|
| `_anchored` returns `runs` (F-1 off) | structure-safe: split email, split phone, billing-seed parse. Corpus suite: `billing_seed.py` anchor and `ast.parse` |
| `_escape_intervals` returns `[]`, **before F-4** (M1) | `test_every_json_corpus_file_still_parses[build-log-escapes.json]`, the only corpus file to fail. STORY-008 recorded that none did, so M1 is closed |
| `_escape_intervals` returns `[]`, **after F-4** | 14 tests, including the new file's parse in both suites. Since F-4 also uses `_escape_intervals`, this now disables both mechanisms |
| `_blank_escapes` returns `analysis` (F-4 off) | both letter-escape tests, the analyzer-view test, and the corpus escape-adjacent test |

### E2E checklist

- [x] `pytest tests/test_pii_code_corpus.py -q`: 70 passed, exactly 1 skipped (the benchmark)
- [x] `pytest tests/test_pii_code_corpus.py -m benchmark --run-benchmark -s -q`: 1 passed, p95 printed, 460.05 ms < 1,500 ms
- [x] One-off `ast.parse(redact_for_policy(billing_seed.py, code))` succeeds; lines 93 and 100 read `email='<EMAIL_ADDRESS>',`
- [x] Guard-bites observed and reverted; `git diff app/` shows only the F-1 and F-4 changes
- [x] `python scripts/measure_pii_latency.py --sizes 200000 --runs 5 --arms code --concurrency 1` prints the `code` row (p95 461.40 ms) and the budget-check line

## Latency (AC 4)

**Asserted** by `tests/test_pii_code_corpus.py::test_code_p95_at_200k_is_within_the_story_003_budget`:

```
STORY-013 code p95 at 200000 chars: 463.23 ms (min 444.22, p50 448.53, n=20; budget 1500 ms)
```

**Reproduced by the script:** `python scripts/measure_pii_latency.py --sizes 40000,200000,400000 --runs 20 --arms code,pattern-blank --concurrency 1`, on the same host as STORY-003 (Python 3.11.9, 12 logical CPUs; presidio 2.2.364, spaCy 3.8.16, en_core_web_lg 3.8.0, phonenumbers 9.0.38).

| size | arm | min (ms) | p50 (ms) | p95 (ms) |
|---|---|---|---|---|
| 40,000 | code | 68.91 | 70.07 | 70.62 |
| 40,000 | pattern-blank | 75.75 | 76.45 | 77.26 |
| 200,000 | **code** | 445.11 | 449.13 | **465.44** |
| 200,000 | pattern-blank | 511.79 | 518.20 | 528.77 |
| 400,000 | code | 901.75 | 909.02 | 928.62 |
| 400,000 | pattern-blank | 1,042.99 | 1,054.23 | 1,063.18 |

- `code` is the shipped policy: no `system` turn, fences skipped, chunked, structure-safe. It is about 12% under STORY-003's `pattern-blank` arm, which redacts every message whole. It is **31% of the budget**, and about 23× faster than `chat`'s 10,749.60 ms p95 (STORY-003).
- **Conversation shape changed (D-h).** `build-log-escapes.json` joined the tool-shaped rotation, now 12 files. At 200k the conversation has 69 messages, not 67, with 27,460 fenced characters (13.7%) instead of 27,079. At 400k it has 138 messages and 56,181 fenced characters.
- Single-message worst case (`pattern-blank`) at 200,000: unchunked p95 2,534.27 ms, chunked 745.44 ms. Chunked and unchunked spans are identical (791).

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/pii_redactor.py` | UPDATE | +80/-6 |
| `scripts/measure_pii_latency.py` | UPDATE | +54/-9 |
| `scripts/spike_pii_placeholders.py` | UPDATE | +5/-1 |
| `tests/conftest.py` | UPDATE | +35 |
| `tests/test_pii_code_corpus.py` | CREATE | +395 |
| `tests/test_pii_structure_safe.py` | UPDATE | +127 |
| `tests/test_measure_pii_latency.py` | UPDATE | +29 |
| `tests/corpora/pii/json/build-log-escapes.json` | CREATE | +56 |
| `tests/corpora/pii/SOURCES.md` | UPDATE | +15 |
| `.agents/PRDs/PRD-012-pii-for-code/PRD.md` | UPDATE | +2/-2 |
| `.agents/plans/PRD-012-pii-for-code/completed/STORY-013-code-round-trip-suite.plan.md` | MOVE (archived) | 0 |
| `.agents/reports/PRD-012-pii-for-code/STORY-013-code-round-trip-suite.report.md` | CREATE | this file |

## Deviations from Plan

1. **A second production fix, F-4 (escapes in JSON), approved by the user during implementation.**
   - **Discovery.** The plan's Task 8 assertion `\n<IBAN_CODE>` failed on unmodified code: the IBAN after `\n` and the card after `\t` in `build-log-escapes.json` were not detected at all. The pre-planning probe had checked only an email and a `+1` phone after an escape, and those match without a word boundary.
   - **Fix.** `_blank_escapes` in JSON mode only, plus four tests: two letter-escape cases, what the analyzer sees in JSON, and a check that non-JSON text is untouched.
   - **Cost.** `redact_for_policy` now runs `_is_json_document` before analysis, so JSON-looking text pays for `json.loads` even when it holds no PII. Text not starting with `{` / `[` still never pays. The comment says so.
   - **What remains open.** The same gap exists in source code: a Java or Python string `"...\n4111 1111 ..."` is still analyzed with the backslash. In non-JSON text a backslash also starts paths like `C:\Users`, so blanking there was not attempted (see *Observations*).
2. **`scripts/spike_pii_placeholders.py` changed.** STORY-012's parity test (`test_indexed_scheme_differs_from_production_only_in_the_suffix`) failed for `build-log-escapes.json`, because the spike's `IndexedScheme` copies `redact_for_policy`'s steps and lacked F-4. It now mirrors F-4. No spike test changed. D5's conclusions are unaffected: F-4 only adds masks after JSON escapes.
3. **The number-token test is keyed on PII classes, not "≥ 9 digits".** `ticket-thread-export.json` has `"order_number": 4000813378`, which is not PII. The test uses the corpus's value classes: 555-01xx phones (`_PHONE_555`) and Luhn-valid cards. It is parametrized only over files that hold such tokens (`crm-contact-search.json`, `payment-webhook.json`), with a guard, so the default run has exactly one skip.
4. **The M1 sample puts the email in a path directory, not a file name.** `jane.doe@example.com.eml` read as domain `example.com.eml` and failed the reserved-domain guard. It is now `mail\\jane.doe@example.com\\message.eml`.
5. **Extra assertions beyond the plan:**
   - the corpus escape test also checks `\t<CREDIT_CARD>`;
   - the fenced-block guard requires both a `` ``` `` and a `~~~` block;
   - `test_the_code_corpus_has_python_json_and_yaml_samples` guards the three parse tests.
6. **The script's latency table heading** now reads "one redaction per message; `code`: only the policy's roles" instead of "redact() per message", which was wrong for the new arm.
7. **Task 5 wiring.** The script's `work(arm, conversation)` closure replaces the two inline `_redact_all(redactors[arm], …)` lambdas, because the `code` arm is not a text-to-text `Redactor`. Throughput is unchanged, and still `chat` / `pattern-*` only.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_pii_code_corpus.py` (71) | These tests: <ul><li>**AC 1:** `test_every_fenced_block_is_byte_identical` ×7; `test_the_code_corpus_has_several_fenced_blocks`; `test_structural_characters_keep_their_count_and_positions` ×7; `test_only_placeholders_change_between_structural_characters` ×7; `test_every_masked_run_holds_its_entity_anchor` ×7; `test_every_code_sample_is_masked_under_code` ×7; `test_the_code_corpus_has_python_json_and_yaml_samples`; `test_every_python_sample_still_parses`; `test_every_json_code_sample_still_parses`; `test_every_yaml_sample_still_loads`</li><li>**AC 2:** `test_the_types_code_does_not_mask_are_enumerated`; `test_prose_declared_entities_are_masked_under_code` ×6; `test_prose_declared_entities_are_masked_under_chat` ×6</li><li>**AC 5:** `test_chat_changes_every_code_sample` ×7</li><li>**AC 3:** `test_code_redacts_tool_turns`; `test_every_json_tool_result_parses_after_redaction` ×5; `test_the_json_corpus_has_number_token_pii`; `test_number_token_pii_is_quoted` ×2; `test_escape_adjacent_pii_is_masked_and_the_escape_kept`</li><li>**AC 4:** `test_code_p95_at_200k_is_within_the_story_003_budget` (benchmark)</li></ul> |
| `tests/test_pii_structure_safe.py` (+11; the new corpus file adds parametrized cases to existing tests) | **F-1:** `test_split_email_span_masks_only_the_run_with_the_at_sign`, `test_split_phone_span_masks_only_runs_with_digits`, `test_split_span_with_digits_on_both_sides_masks_both`, `test_split_span_with_no_anchored_run_masks_every_run`, `test_split_span_of_an_unanchored_type_masks_every_run`, `test_json_mode_ignores_run_anchors`, `test_billing_seed_parses_after_code_redaction`. **F-4:** `test_json_pii_right_after_a_letter_escape_is_masked` ×2, `test_escapes_are_blanked_only_for_the_analyzer`, `test_escapes_are_not_blanked_outside_json_mode` |
| `tests/test_measure_pii_latency.py` (+3) | `test_arms_accept_code`, `test_code_arm_redacts_only_the_policy_roles`, `test_code_budget_is_story_003s` |

## Observations (recorded, not fixed)

- **The escape gap in source code (F-4's non-JSON half).**
  - A letter escape directly before an IBAN or a card inside a Java, TypeScript or Python string literal (`"card:\t4111 1111 1111 1111"`) is still missed under `code`. `chat` misses it too, since `redact()` sees the same text.
  - No corpus file has this today.
  - Fixing it in non-JSON text needs a rule that tells `\t` in a string literal from `\U` in `C:\Users`. That is for STORY-014 to document or for a follow-up to design.
- **R2 re-applied today gives 1,250 ms, not 1,500.**
  - This run's `pattern-blank` p95 is 528.77 ms (STORY-003: 645.60 ms), so the script's "decision inputs" line now prints a 1,250 ms budget.
  - The budget is STORY-003's recorded decision (`CODE_P95_BUDGET_MS = 1_500`), not a value re-derived per run, and `code` (465 ms) is under both.
  - STORY-014 should quote the fixed 1,500 ms.
- **`_escape_intervals` now serves two purposes:** keeping escapes whole at replacement (STORY-008) and blanking them for analysis (F-4). A regression in it breaks both at once, and the 14-test guard-bite shows the suite notices.

## Handoff (for later stories)

- **STORY-014 (chat regression sweep, README):**
  - Quote `code` p95 at 200k = **463 ms** (budget 1,500 ms) beside `chat`'s 10.7 s (STORY-003).
  - Run `pytest tests/test_pii_code_corpus.py -m benchmark --run-benchmark -s` in the sweep. The everyday suite skips it.
  - The README should state:
    - under `code`, names and places in prose are not masked (`_ABSENT_UNDER_CODE`);
    - PII in fenced blocks reaches the provider (Risk 1);
    - a split email or number span masks only its anchored part (F-1);
    - in JSON tool results, escapes are invisible to detection (F-4);
    - in source-code strings, a letter escape directly before an IBAN or card can hide it (the open half).
- **PRD-016 (tool turns):** once step 0 admits `tool`, add a `run_conversation` case over one `json/` file. `build-log-escapes.json` is the one that exercises F-4.

## Acceptance Criteria

- [x] Given `tests/test_pii_code_corpus.py`, when it runs, then under `code` every fenced sample in `tests/corpora/pii/code/` is byte-identical after redaction, and every unfenced sample keeps its count and positions of quotes, backslashes, backticks and line breaks, with every `.py` still passing `ast.parse` and every `.json` still passing `json.loads`.
- [x] Given `tests/corpora/pii/prose/`, when each file is redacted under both `chat` and `code`, then its declared entities are masked, except entity types absent from `PII_ENTITIES_CODE` under `code`, which the test enumerates explicitly (`{PERSON}`).
- [x] Given `tests/corpora/pii/json/`, when each file is redacted under `code`, then it parses, and number-token PII is quoted.
- [x] Given the benchmark rerun at 200,000 characters under `code`, when p95 is measured, then it is under the budget the STORY-003 report fixed (463.23 ms < 1,500 ms), and the number is recorded in this report.
- [x] Given at least one code-corpus file, when it goes through today's `chat` policy, then it is asserted to change: all 7 do, each with a placeholder not in the original.
- [x] All tasks completed
- [x] Backend imports without error
- [x] No assertion changed in the protected files; `tests/test_pii_structure_safe.py` changed by additions only
- [x] Follows existing patterns
