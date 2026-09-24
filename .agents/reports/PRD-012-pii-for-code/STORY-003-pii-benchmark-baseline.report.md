---
story: STORY-003
prd: PRD-012
plan: .agents/plans/PRD-012-pii-for-code/completed/STORY-003-pii-benchmark-baseline.plan.md
epic_branch: epic/PRD-012-pii-for-code
commit: ddf6596
status: COMPLETE
completed: 2026-09-24
---

# Implementation Report — STORY-003: Benchmark harness, baseline numbers, pinned versions and tokenizer-only analyzer feasibility

**Plan**: `.agents/plans/PRD-012-pii-for-code/completed/STORY-003-pii-benchmark-baseline.plan.md`
**Epic Branch**: `epic/PRD-012-pii-for-code` (BASE `d0b1739`, plan commit `7363fe8`)
**Commit**: `ddf6596`

## Summary

`scripts/measure_pii_latency.py` measures PII redaction at agent sizes on untouched code. It covers:
- redaction time per conversation, in three arms;
- whether a tokenizer-only analyzer can be built;
- how much of the cost is spaCy's NLP pipeline;
- a single-message worst case, unchunked and chunked;
- throughput at thread concurrency 1 and 4;
- per-entity false positives over `tests/corpora/pii/code/`;
- prose recall and required probes per candidate threshold.

It asserts nothing about latency. `requirements.txt` now pins `presidio-analyzer==2.2.364`, `presidio-anonymizer==2.2.364` and `spacy==3.8.16`. No file under `app/` or `chat_ui/` changed.

**The decided values** (rules R1–R4 of the plan, applied mechanically; see *Decisions*):

| setting | value | rule | evidence |
|---|---|---|---|
| `PII_SCORE_THRESHOLD_CODE` | **0.40** | R1 | The highest candidate that keeps 6/6 prose files and 2/2 required probes. At 0.50 both probes are missed, including the PRD's own user-story-3 phone |
| p95 budget at 200,000 characters | **1,500 ms** | R2 | 2 × `pattern-blank` p95 645.60 ms = 1,291.2 ms, rounded up to 250 ms. `chat` is 10,749.60 ms (16.7×) |
| `PII_MAX_CHARACTERS_CODE` | **200,000** | R3 | One 200,000-character message: p95 2,711.74 ms unchunked (over budget), 751.25 ms chunked (under budget). **Condition:** STORY-006/008 must analyze in line-aligned 20,000-character chunks |
| `PERSON` in `PII_ENTITIES_CODE` (D7) | **stays out** | R4 | `PERSON` needs `en_core_web_lg`. `pattern-lg` p95 at 200,000 is 11,125.98 ms, over the 1,500 ms budget |

## Tasks Completed

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 0 | Preflight: branch clean at `d0b1739`, container `harness-libsql-dev` up, plan committed (`7363fe8`), `pip freeze` saved, baseline suite 2662 passed / 26 skipped | — | ✅ |
| 1 | Skeleton, env bootstrap, CLI, corpus copies | `scripts/measure_pii_latency.py` | ✅ |
| 2 | Analyzers, four routes, parity | same | ✅ (deviation 1) |
| 3 | Redaction callables, agent-shaped conversation, single-message worst case | same | ✅ |
| 4 | Timing, NLP share, chunked worst case, concurrency | same | ✅ |
| 5 | Value-class classifier, detections, prose recall, required probes | same | ✅ |
| 6 | Report output and R1–R4 block | same | ✅ |
| 7 | Tests of the pure parts and drift guards | `tests/test_measure_pii_latency.py` | ✅ (deviation 2) |
| 8 | Pins, `pip freeze` diff, `pip check`, full suite, characterization | `requirements.txt` | ✅ |
| 9 | Full run (11:24:47–12:01:57, idle machine, one invocation, exit 0), this report | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) after pinning | ✅ OK |
| Frontend lint | N/A. No frontend change |
| `pip install -r requirements.txt`, then `pip freeze` diff against the Task 0 snapshot | ✅ no diff |
| `pip check` | ✅ No broken requirements found |
| `pytest tests/test_measure_pii_latency.py` | ✅ 56 passed in about 1 s. No lg model loads |
| `pytest tests/test_pii_characterization.py` after pinning | ✅ 25 passed, unchanged. STORY-002's pins show the pins moved nothing |
| Full suite | ✅ 2717 passed, 26 skipped, **0 failed**, 1 error (see note) |
| E2E (plan checklist) | ✅ 7/7 |
| `git diff --name-only d0b1739 HEAD -- app/ chat_ui/` | ✅ empty |

**About the full-suite runs.** The first post-pin run had two failures:
- **`test_importing_the_script_builds_no_analyzer`.** This was my own test, and it was order-dependent. It compared against a value captured at collection time, and other tests reset the singleton in between. It now checks in a fresh interpreter.
- **`test_pattern_corpus.py::…[indirect-ci-log.log-flag]`.** It passes in isolation.

The second run had 0 failures and 1 error: `Hrana … tcp connect error (os error 10060)` in `test_chat_history.py::test_assemble_emits_exactly_two_messages_per_answered_exchange[1]`. That file passes in isolation (113 passed together with this story's module). This is the libSQL dev-container flakiness the STORY-002 report records. None of these involve this story.

### E2E checklist

- [x] `--help` returns in 1.05 s and loads no model.
- [x] `--show-corpus` shows exact sizes 40,000 / 200,000 / 400,000, a leading `system` turn, and no `tool` role (also asserted in the tests).
- [x] `--no-timing` prints feasibility with 4 routes. Route 1 is refused, with no download, network or pip output. It also prints the false-positive and threshold tables.
- [x] The smoke run (`--sizes 40000 --runs 3 --arms pattern-blank --concurrency 1,4 --concurrency-size 40000 --concurrency-rounds 1`) prints every table and the R1–R4 block, in 22.7 s.
- [x] The full run completed with exit 0. It has p50/p95 for 3 arms × 3 sizes, throughput at concurrency 1 and 4, and today's per-type false positives at 0.35.
- [x] `pytest tests/test_measure_pii_latency.py -q` is green, in about 1 s.
- [x] After pinning, `pip freeze` is unchanged, the full suite is green (see note) and the characterization is green.

## Environment and versions (AC 3)

The command was `python scripts/measure_pii_latency.py --sizes 40000,200000,400000 --runs 20 --concurrency 1,4`. It ran on Python 3.11.9 on Windows 10 (the host is Windows 11 Pro 10.0.26200), with 12 logical CPUs, on AC power and otherwise idle.

| Package | Resolved | Pinned in `requirements.txt` |
|---|---|---|
| presidio-analyzer | 2.2.364 | `presidio-analyzer==2.2.364` |
| presidio-anonymizer | 2.2.364 | `presidio-anonymizer==2.2.364` |
| spacy | 3.8.16 | `spacy==3.8.16` |
| en_core_web_lg | 3.8.0 | not pinned. `Dockerfile:63` runs `spacy download`, which picks the model compatible with the pinned spaCy |
| phonenumbers | 9.0.38 | not pinned (outside AC 3). **Recorded because it moves phone scores.** A bump is a candidate cause if phone results shift |

`requirements.txt` pins exactly the three resolved versions the script printed. They are the same versions STORY-001 and STORY-002 measured with.

## Feasibility of a tokenizer-only analyzer (AC 2, PRD Risk 2)

| Route | Loads | Error | Differences from lg (17 texts: 4 probes + 7 `code/` + 6 `prose/`) |
|---|---|---|---|
| `provider:blank:en`: `NlpEngineProvider` with `model_name="blank:en"` | **no** | `RuntimeError: download of 'blank:en' refused: the benchmark never installs packages` | — |
| `provider:path`: `NlpEngineProvider` with a directory from `spacy.blank("en").to_disk()` | yes | — | 140 |
| `subclass`: a `SpacyNlpEngine` subclass whose `load()` is `spacy.blank("en")` | yes | — | 140 |
| `subclass+lemma`: the same, plus a `lower_as_lemma` pipeline component | yes | — | **4** |

**Why route 1 fails.**
- `SpacyNlpEngine.load()` calls `_download_spacy_model_if_needed(name)`, which runs `spacy.cli.download(name)` for any name that is neither an installed package nor an existing path (`presidio_analyzer/nlp_engine/spacy_nlp_engine.py:78-81`).
- Unguarded, that is a network call. It ends in `SystemExit(1)` ("No compatible package found for 'blank:en'"), which `except Exception` does not catch.
- The script replaces the download with one that raises, so the error above is the guarded form of that failure. **Presidio cannot take a blank model by name.**

**Why routes 2 and 3 are not enough.**
- Both load, and every pattern recognizer is present.
- But Presidio's context enhancer compares context words against `token.lemma_`, and a blank pipeline leaves every lemma empty. So no score is ever boosted: a phone with "phone" nearby stays at 0.40 instead of 0.75, and `219-09-9999` with "social security number" stays at 0.50 instead of 0.85.
- That is 140 differences, and the detector would be weaker than lg's.

**Route 4, `subclass+lemma`, is feasible, and it is the one the code arm uses.**
- `lower_as_lemma` sets `token.lemma_ = token.lower_`.
- Its 4 differences are 2 spans (each counted once per side), both in `onboarding-runbook.md` after the word **"Called"**. lg lemmatizes it to `call`, which is not a phone context word. The lower-cased `called` does boost. So the route scores 0.75 where lg scores 0.40.
- **Every difference is in the masking-safe direction**: the route never scores lower than lg.

**The NLP share answers Risk 2's second question.** At 200,000 characters (p50):
- `en_core_web_lg`'s `process_text` is 10,098.19 ms of `pattern-lg`'s 10,849.29 ms, which is **93.1%**. Dropping `PERSON`/`LOCATION` from the entity list saves nothing on lg: `pattern-lg` ≈ `chat` at every size.
- On the blank route, NLP is 135.03 ms of 599.96 ms (22.5%). **Recognition and anonymization now dominate.** That is the next place to look if the budget ever tightens.

## Conversation shape (how the corpus is repeated)

The conversation is built deterministically:
- One `system` turn: a 6,000-character PII-free agent prompt.
- Then this cycle repeats:
  1. `user`: a `prose/` file with its header stripped;
  2. `assistant`: a lead sentence, the first 40 lines of a `code/` file in a ```` fence, and a closing sentence;
  3. a tool-shaped `user` turn (a raw, unfenced `code/` or `json/` file, since step 0 refuses `tool`).
- The last message is truncated so the total is exact.

| size | messages | largest | system chars | fenced chars | uses per corpus file |
|------|----------|---------|--------------|--------------|----------------------|
| 40,000 | 10 | 9,523 | 6,000 | 3,605 (9.0%) | 1–2 |
| 200,000 | 67 | 12,958 | 6,000 | 27,079 (13.5%) | 2–6 |
| 400,000 | 135 | 12,958 | 6,000 | 53,999 (13.5%) | 4–11 |

All arms redact **every** message, fences and the system turn included, because no policy exists yet. D2 (fence skipping) and D3 (no `system`) can only reduce the `code` figures, by about 16% of characters at 200,000.

## Baseline latency (AC 1, AC 2; PRD Section 11 "baseline before any change")

`redact()` runs once per message, n = 20 after one discarded warm conversation per arm. p50 is the median and p95 is nearest-rank.

| size | arm | min (ms) | p50 (ms) | p95 (ms) |
|---|---|---|---|---|
| 40,000 | chat | 1,763.61 | 1,776.58 | 1,841.87 |
| 40,000 | pattern-lg | 1,755.33 | 1,764.86 | 1,779.47 |
| 40,000 | pattern-blank | 75.25 | 76.23 | 77.28 |
| 200,000 | chat | 10,161.33 | 10,228.84 | 10,749.60 |
| 200,000 | pattern-lg | 10,180.91 | 10,849.29 | 11,125.98 |
| 200,000 | pattern-blank | 577.87 | 599.96 | 645.60 |
| 400,000 | chat | 20,730.58 | 21,578.53 | 22,481.89 |
| 400,000 | pattern-lg | 20,796.38 | 21,161.58 | 21,255.19 |
| 400,000 | pattern-blank | 1,092.43 | 1,111.53 | 1,154.05 |

- **Today's `chat` at 200,000 characters is about 10.2 s (p50) / 10.7 s (p95) of CPU-bound redaction per request.** This confirms the PRD Section 1 extrapolation ("on the order of 10 s").
- Agent-shaped cost is **linear** in size for every arm: 200k→400k is ×2.1 for chat and ×1.85 for blank.

**Worst case: all characters in one `user` message (`pattern-blank`).**

| size | unchunked p50 / p95 (ms) | chunked (20,000, line-aligned) p50 / p95 (ms) |
|---|---|---|
| 40,000 | 112.11 / 125.79 | 99.40 / 119.85 |
| 200,000 | 2,599.01 / 2,711.74 | 723.98 / 751.25 |
| 400,000 | 10,337.63 / 11,614.36 | 1,654.84 / 1,699.53 |

- Unchunked cost is **superlinear** in the length of one string: ×4.3 from 200k to 400k, and 2,712 ms at 200k against 646 ms when the same characters arrive as 67 messages. Chunking makes it linear again.
- Chunked and unchunked analysis found **identical** spans on the 200,000-character message (781 spans). At this size, chunk boundaries cost no detection.

**Throughput (T10; threads; 200,000-character conversation; no budget asserted).**

| arm | concurrency | conversations | wall (s) | conv/s | chars/s | vs c=1 |
|---|---|---|---|---|---|---|
| chat | 1 | 3 | 32.43 | 0.093 | 18,501 | 1.00× |
| chat | 4 | 12 | 184.76 | 0.065 | 12,990 | **0.70×** |
| pattern-blank | 1 | 3 | 1.49 | 2.013 | 402,534 | 1.00× |
| pattern-blank | 4 | 12 | 5.96 | 2.014 | 402,874 | 1.00× |

- Threads do not scale. Redaction holds the GIL, so four concurrent requests each take about four times as long.
- `chat` actually **loses** 30% throughput at concurrency 4, likely from contention inside spaCy's large pipeline.
- Under load, `chat`'s effective per-request latency is `concurrency × 10 s`. That is T10's risk, recorded, and the process pool stays PRD Section 13's future consideration.

## False positives over `tests/corpora/pii/code/` (AC 1)

**Definition.** A detection is a true positive when its span is one of the corpus's value classes (`tests/corpora/pii/SOURCES.md`, *Value classes*):
- emails on `example.com` or `example.org`, matched case-insensitively;
- `NPA-555-01xx` phones;
- the two test card numbers and the two test IBANs;
- `219-09-9999`;
- a span made only of cast-name words, after undoing `''` and `\'` and stripping quotes;
- a `LOCATION` from `_PLACES`, which lists each place with its `file:line`.

Anything else is a false positive. **Structural** means the span contains `"`, `'`, `` ` ``, `\` or a newline. For `PERSON` that includes correct apostrophe names such as `O'Brien`, so the structural count is an upper bound on structure-breaking spans.

**Today's analyzer (`en_core_web_lg`, `PII_ENTITIES`) at `PII_SCORE_THRESHOLD=0.35`:**

| entity | detected | true pos | false pos | structural |
|---|---|---|---|---|
| CREDIT_CARD | 9 | 9 | 0 | 0 |
| EMAIL_ADDRESS | 99 | 99 | 0 | 2 |
| IBAN_CODE | 8 | 8 | 0 | 0 |
| LOCATION | 18 | 11 | **7** | 0 |
| PERSON | 90 | 79 | **11** | 25 |
| PHONE_NUMBER | 71 | 66 | **5** | 0 |
| US_SSN | 0 (none detected; no row printed) | 0 | 0 | 0 |

The false-positive spans, as the run printed them:
- **`LOCATION`**: `America` ×4 (timezone IDs), `USD` ×2, `Europe/Berlin`.
- **`PERSON`**, one each:
  - identifiers: `PENDING_VERIFICATION`, `SUPPORT_CONTACT_NAME`, `minReplicas`, `letsencrypt`, `contact.email`, `Email`;
  - spans that swallowed code: `'Maria Lopez\n  SUPPORT_CONTACT_EMAIL'`, `'display_name="Patrick O\'Brien'`, `'expect(dir.getUserByEmail("patrick.obrien@example.org")?…'`, `'str\n    expires'`, `'ping Priya Raghunathan'`.
- **`PHONE_NUMBER`**: `078-05-1120` ×5, the voided SSN and a deliberate near-miss.

**Pattern entities on the code arm (`pattern-blank`) at 0.35:** `CREDIT_CARD` 9/9, `EMAIL_ADDRESS` 99/99 (2 structural), `IBAN_CODE` 8/8, `PHONE_NUMBER` 71 with 66 true, and **5 false positives, all `078-05-1120`**.

**Per candidate threshold** (code arm for the pattern entities; lg for `PERSON`):

| threshold | pattern FP | pattern TP | prose recall | required probes | PERSON FP / detected (structural) |
|---|---|---|---|---|---|
| 0.35 | 5 | 182 | 6/6 | 2/2 | 11 / 90 (25) |
| **0.40** | **5** | **182** | **6/6** | **2/2** | 11 / 90 (25) |
| 0.50 | 1 | 173 | 6/6 | 0/2 | 11 / 90 (25) |
| 0.60 | 1 | 173 | 6/6 | 0/2 | 11 / 90 (25) |
| 0.75 | 1 | 173 | 6/6 | 0/2 | 11 / 90 (25) |

All `PERSON` detections score 0.85, so no threshold in range removes a single one of its false positives.

## Decisions (AC 4)

Each rule is quoted from the plan (*Decision rules*, written before measuring) and applied as written. Judgement, where added, is marked.

**`PII_SCORE_THRESHOLD_CODE = 0.40` (R1).** Rule: *the highest candidate `t` at which (a) 100% of the declared pattern entities in `prose/` are found and (b) every required probe is found.*
- 0.40 passes both (6/6, 2/2). 0.50 fails (b) at 0/2:
  - PRD Section 5, user story 3 ("… call her on +1 415 555 0134") scores 0.40, because `call` is not a context word;
  - a bare `212-555-0147` in prose scores 0.40 too.
- The provisional 0.5 would therefore have broken a user story the PRD commits to.
- **The cost of 0.40:** 5 false positives on `code/` rather than 1 at 0.50. All are `078-05-1120`, a phone-shaped voided SSN, and structure-safe replacement makes masking one cheap. It also keeps 9 more true example phones masked (182 vs 173).
- *Judgement:* 0.35 detects exactly the same set on this corpus. 0.40 is chosen by the rule's "highest", and it drops the 0.35–0.40 band that no measured true positive uses.

**p95 budget at 200,000 characters = 1,500 ms (R2).** Rule: *`2 ×` the code arm's agent-shaped p95 at 200,000, rounded up to 250 ms.*
- 2 × 645.60 = 1,291.2 ms, which rounds up to **1,500 ms**.
- The 2× is headroom for STORY-013 asserting it on a loaded developer or CI machine.
- For comparison, `chat` is 10,749.60 ms, 16.7× the code arm.
- The measurement redacted every message, fences and the system turn included. So the real `code` policy should land further under the budget.

**`PII_MAX_CHARACTERS_CODE = 200,000` (R3).** Rule: *keep 200,000 (= `CONTEXT_MAX_CHARACTERS`) if the single-message worst case at 200,000 has p95 ≤ budget, unchunked or chunked. If only chunked meets it, chunking becomes a requirement on STORY-006/008.*
- Unchunked p95 is 2,711.74 ms, **over** the budget. Chunked p95 is 751.25 ms, **within** it. So the limit stays 200,000, **on condition** that `redact_for_policy` analyzes in line-aligned windows of ≤ 20,000 characters.
- Without chunking, R3's interpolation would have set a limit that refuses requests step 3 admits.

**`PERSON` stays out of `PII_ENTITIES_CODE` (R4, D7).** Rule: *`PERSON` forces the full lg analyzer; if `pattern-lg`'s agent-shaped p95 at 200,000 exceeds the R2 budget, `PERSON` stays out.*
- 11,125.98 ms > 1,500 ms, so it stays out. That is 7.4× the budget, and the NLP share (93.1%) shows no entity-list change can close the gap.
- Supporting evidence: on `code/`, `PERSON` has 11 false positives out of 90 detections at every candidate threshold (all score 0.85). Five of those false positives swallow code or cross a line break (listed above).
- The round-trip half of PRD 6.4's test is not needed: the latency half already fails.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `scripts/measure_pii_latency.py` | CREATE | +1243 |
| `tests/test_measure_pii_latency.py` | CREATE | +272 |
| `requirements.txt` | UPDATE | +3/-3 |
| `.agents/plans/PRD-012-pii-for-code/completed/STORY-003-pii-benchmark-baseline.plan.md` | MOVE (archived) | 0 |
| `.agents/reports/PRD-012-pii-for-code/STORY-003-pii-benchmark-baseline.report.md` | CREATE | this file |

## Deviations from Plan

1. **Route selection is by fewest differences, not "full parity, else the first that loads".**
   - No route reached zero differences (the "Called" lemma case above).
   - Under the plan's literal fallback, the arm would have used `provider:path`. That route has no context boost at all, so the first `--no-timing` run reported prose recall 1/6 at 0.50, a detector weaker than lg's and weaker than STORY-006 will build.
   - `_pattern_blank_route` now takes the loaded route with the fewest differences, first on a tie, and its docstring explains why. A test (`test_route_choice_prefers_fewest_differences`) pins it.
   - Every difference of the chosen route masks more, never less.
2. **`test_importing_the_script_builds_no_analyzer` runs in a subprocess.** The in-process version compared against a value captured at collection time. Other tests reset `pii_redactor._analyzer` in between, so the check was order-dependent and failed in the full suite.
3. **`_PLACES` includes `CA`**, the state field at `CustomerFixtures.java:74, 88`. NER never tagged it, so it changes no count. It is listed because it is a place in the corpus.
4. **The plan's route-1 failure mode was confirmed but not reproduced unguarded.** The script never lets the download run. The unguarded `SystemExit(1)` ("No compatible package found for 'blank:en'") was observed once during `/plan` exploration and is described above rather than re-run.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_measure_pii_latency.py` | `test_importing_the_script_builds_no_analyzer`; `test_conversation_is_exactly_the_requested_size` ×4; `test_conversation_smaller_than_the_system_prompt_is_one_truncated_system_turn`; `test_conversation_is_deterministic`; `test_assistant_turns_carry_a_fenced_excerpt_and_the_shape_counts_it`; `test_single_message_worst_case_is_one_user_turn_of_the_same_size`; `test_true_positive_classification` ×25; `test_structural_spans` ×6; `test_nearest_rank_p95`; `test_chunks_are_line_aligned_and_cover_the_text`; `test_a_line_longer_than_the_window_is_cut_hard`; `test_rule_r2_doubles_and_rounds_up_to_250_ms`; `test_interpolated_size_is_log_log_and_rounded_down`; `test_rule_r1_takes_the_highest_acceptable_threshold`; `test_rule_r1_reports_when_nothing_is_acceptable`; `test_rule_r3_branches`; `test_the_cast_matches_the_corpus_loader`; `test_corpus_discovery_matches_the_corpus_loader`; `test_declared_headers_match_the_corpus_loader`; `test_pattern_entities_are_known_and_contain_no_ner_type`; `test_tokenizer_only_route_with_lemmas_boosts_context`; `test_blank_route_by_name_never_downloads`; `test_a_route_raising_systemexit_is_recorded_not_fatal`; `test_route_choice_prefers_fewest_differences` (56 cases) |

## For later stories

- **STORY-005 (settings):**
  - Set `PII_SCORE_THRESHOLD_CODE` default **0.40** and `PII_MAX_CHARACTERS_CODE` default **200000**. Keep `PII_ENTITIES_CODE` without `PERSON`/`LOCATION`.
  - The validator dict is **`_POSITIVE_LIMIT_DESCRIPTIONS`** (`app/config.py:19-24`). `_RESOURCE_BOUNDS`, named in the PRD (Sections 6.10, 7/F4), does not exist.
- **STORY-006 (pattern-only analyzer):**
  - **Use `subclass+lemma`:** a `SpacyNlpEngine` subclass whose `load()` sets `self.nlp = {"en": spacy.blank("en")}` with `lower_as_lemma` added (`scripts/measure_pii_latency.py`, `lower_as_lemma` and `_TokenizerOnlySpacyNlpEngine`).
  - Do **not** pass a blank model name to `NlpEngineProvider`: it triggers a network download that ends in `SystemExit`. Do not use a lemma-less blank pipeline: it loses every context boost.
  - Carry over `test_tokenizer_only_route_with_lemmas_boosts_context`, which checks 0.75 with lemmas and 0.40 without.
  - Register the spaCy component name once. `@Language.component("lower_as_lemma")` at module import is enough.
- **STORY-008 (`redact_for_policy`):**
  - **Chunking is a requirement (R3):** analyze in line-aligned windows of ≤ 20,000 characters (cut after the last `\n` before the window end; hard cut if a line is longer), shift `start`/`end` by the window offset, and replace once in the original. `_chunks` / `_chunked_results` are the reference, and the chunked and unchunked spans were identical at 200,000.
  - Structural spans at 0.35 on `code/`: `EMAIL_ADDRESS` 2 (escaped-quote cases), `PERSON` 25 (includes apostrophe names), all others 0.
- **STORY-013 (round-trip + budget):**
  - Assert **`code` p95 at 200,000 < 1,500 ms** on the agent-shaped conversation (`_conversation(200000)`), not on a single message.
  - Reproduce the figures with `python scripts/measure_pii_latency.py --sizes 40000,200000,400000 --runs 20 --concurrency 1,4`. Add a `code` arm (through `redact_for_policy`) beside the three here, rather than replacing them.
- **STORY-014 (README):**
  - Today `chat` costs about 10.2 s p50 / 10.7 s p95 per 200,000-character conversation. The measured tokenizer-only pattern path costs about 0.60 s p50 / 0.65 s p95.
  - Threads do not scale for either (throughput at concurrency 4: chat 0.70×, blank 1.00×).
  - Quote beside the existing ~0.93 s figure.

## Observations (recorded, not fixed)

- **The story's "README note" is not in the README.** The "restart the libSQL dev container on mass fixture errors" advice lives in PRD Section 11 and in test docstrings (`tests/test_query_pipeline_patterns.py:30-31`).
- **Recognition, not NLP, is now the tokenizer-only path's cost** (77.5% of it). If the budget ever tightens, profile the recognizers and the anonymizer before revisiting the engine.
- **`chat` throughput drops at concurrency 4** (0.70×). A chat deployment under concurrent large requests degrades worse than linearly. This is relevant to T10 and to the process-pool future consideration.
- **The ground-truth classification is by span text.** `US` counts as a place even where it is prose ("Legacy US tax-id") or a locale suffix (`en-US`).

## Acceptance Criteria

- [x] Given `scripts/measure_pii_latency.py --sizes 40000,200000,400000 --runs N`, when it runs on untouched code, then it prints p50/p95 of `redact()` per size over conversations built from `tests/corpora/pii/code/` plus prose filler, and the per-entity-type false-positive count over the code corpus at `PII_SCORE_THRESHOLD=0.35`.
- [x] Given the script, when it runs with a pattern-only entity list (`EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE`) on (a) the full `en_core_web_lg` analyzer and (b) a tokenizer-only `spacy.blank("en")` analyzer, then both sets of timings are reported, or (b) is reported as infeasible with the Presidio error that shows why. *Both are reported. The by-name route is infeasible, and its error is recorded.*
- [x] Given the report, when it is read, then it states the resolved `presidio-analyzer`, `presidio-anonymizer` and `spacy` versions, and `requirements.txt` pins exactly those.
- [x] Given the numbers, when the report concludes, then it fixes `PII_SCORE_THRESHOLD_CODE`, `PII_MAX_CHARACTERS_CODE` and the p95 budget at 200,000 characters, states the reasoning for each, and states whether `PERSON` stays out of `PII_ENTITIES_CODE` (D7).
- [x] Given concurrency, when the script runs with `--concurrency 1` and `--concurrency 4` in threads, then throughput for both is reported (T10). No budget is asserted on it.
- [x] All tasks completed
- [x] Full suite green after pinning (0 failures; one environmental libSQL connect timeout that passes in isolation). `tests/test_pii_characterization.py` is unchanged and green
- [x] No file under `app/` or `chat_ui/` changed
- [x] Follows existing patterns

## Appendix: raw run output

The verbatim stdout of the full run. Every figure above is taken from it.

```
--- STORY-003 PII redaction latency and false positives (PRD-012 Section 11, Risk 2) ---

  python               : 3.11.9 on Windows 10
  cpu count            : 12
  presidio-analyzer    : 2.2.364
  presidio-anonymizer  : 2.2.364
  spacy                : 3.8.16
  en_core_web_lg       : 3.8.0
  phonenumbers         : 9.0.38
  PII_REDACTION_ENABLED: True
  PII_NLP_MODEL        : en_core_web_lg
  PII_SCORE_THRESHOLD  : 0.35 (timing arms)
  PII_ENTITIES         : PERSON,EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE,LOCATION
  pattern entities     : EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE
  CONTEXT_MAX_CHARACTERS: 200000
  sizes                : 40000,200000,400000
  runs per arm         : 20 (after one discarded warm conversation per arm)
  arms                 : chat,pattern-lg,pattern-blank
  code arm             : pattern-blank

  Tokenizer-only feasibility (AC 2, PRD Risk 2):
  | route | loaded | error | parity with lg (texts, differing) |
  |-------|--------|-------|-----------------------------------|
  | provider:blank:en | no | RuntimeError: download of 'blank:en' refused: the benchmark never installs packages | - |
  | provider:path | yes | - | 17 texts, 140 differing |
  | subclass | yes | - | 17 texts, 140 differing |
  | subclass+lemma | yes | - | 17 texts, 4 differing |
    provider:path examples: route only: PHONE_NUMBER 0.4 '415-555-0134'; lg only: PHONE_NUMBER 0.75 '415-555-0134'; route only: PHONE_NUMBER 0.4 '(212) 555-0147'; lg only: PHONE_NUMBER 0.75 '(212) 555-0147'; route only: US_SSN 0.5 '219-09-9999'
    subclass examples: route only: PHONE_NUMBER 0.4 '415-555-0134'; lg only: PHONE_NUMBER 0.75 '415-555-0134'; route only: PHONE_NUMBER 0.4 '(212) 555-0147'; lg only: PHONE_NUMBER 0.75 '(212) 555-0147'; route only: US_SSN 0.5 '219-09-9999'
    subclass+lemma examples: lg only: PHONE_NUMBER 0.4 '+1 415 555 0134'; route only: PHONE_NUMBER 0.75 '+1 415 555 0134'; lg only: PHONE_NUMBER 0.4 '+1 415 555 0134'; route only: PHONE_NUMBER 0.75 '+1 415 555 0134'
  pattern-blank uses  : subclass+lemma

  Conversation shape (agent-shaped: system, then user prose / assistant with fenced excerpt / tool-shaped user):
  | size | messages | largest | system chars | fenced chars | corpus file uses (min-max) |
  |------|----------|---------|--------------|--------------|----------------------------|
  | 40000 | 10 | 9523 | 6000 | 3605 (9.0%) | 1-2 |
  | 200000 | 67 | 12958 | 6000 | 27079 (13.5%) | 2-6 |
  | 400000 | 135 | 12958 | 6000 | 53999 (13.5%) | 4-11 |

  p50 is the median; p95 is nearest-rank, sorted[ceil(0.95*n)-1].
  No latency here is asserted as a pass/fail bound.

  Agent-shaped conversation, 40000 characters (redact() per message):
  | arm | n | min (ms) | p50 (ms) | p95 (ms) |
  |-----|---|----------|----------|----------|
  | chat | 20 | 1763.61 | 1776.58 | 1841.87 |
  | pattern-lg | 20 | 1755.33 | 1764.86 | 1779.47 |
  | pattern-blank | 20 | 75.25 | 76.23 | 77.28 |

  Agent-shaped conversation, 200000 characters (redact() per message):
  | arm | n | min (ms) | p50 (ms) | p95 (ms) |
  |-----|---|----------|----------|----------|
  | chat | 20 | 10161.33 | 10228.84 | 10749.60 |
  | pattern-lg | 20 | 10180.91 | 10849.29 | 11125.98 |
  | pattern-blank | 20 | 577.87 | 599.96 | 645.60 |

  Agent-shaped conversation, 400000 characters (redact() per message):
  | arm | n | min (ms) | p50 (ms) | p95 (ms) |
  |-----|---|----------|----------|----------|
  | chat | 20 | 20730.58 | 21578.53 | 22481.89 |
  | pattern-lg | 20 | 20796.38 | 21161.58 | 21255.19 |
  | pattern-blank | 20 | 1092.43 | 1111.53 | 1154.05 |

  NLP share (process_text over every message vs the arm's redaction, p50):
    en_core_web_lg vs pattern-lg at 200000: nlp 10098.19 ms / total 10849.29 ms = 93.1%
    blank (subclass+lemma) vs pattern-blank at 200000: nlp 135.03 ms / total 599.96 ms = 22.5%

  Worst case, pattern-blank, all characters in one message:
  | arm | n | min (ms) | p50 (ms) | p95 (ms) |
  |-----|---|----------|----------|----------|
  | 40000 unchunked | 20 | 108.25 | 112.11 | 125.79 |
  | 40000 chunked 20000 | 20 | 87.69 | 99.40 | 119.85 |
  | 200000 unchunked | 20 | 2430.80 | 2599.01 | 2711.74 |
  | 200000 chunked 20000 | 20 | 712.59 | 723.98 | 751.25 |
  | 400000 unchunked | 20 | 9577.90 | 10337.63 | 11614.36 |
  | 400000 chunked 20000 | 20 | 1630.27 | 1654.84 | 1699.53 |
  chunked vs unchunked spans: identical at 200000 (781 spans)

  Throughput (T10; threads; 200000-character conversation; no budget asserted):
  | arm | concurrency | conversations | wall (s) | conv/s | chars/s | vs c=1 |
  |-----|-------------|---------------|----------|--------|---------|--------|
  | chat | 1 | 3 | 32.43 | 0.093 | 18501 | 1.00x |
  | chat | 4 | 12 | 184.76 | 0.065 | 12990 | 0.70x |
  | pattern-blank | 1 | 3 | 1.49 | 2.013 | 402534 | 1.00x |
  | pattern-blank | 4 | 12 | 5.96 | 2.014 | 402874 | 1.00x |

  Detections over tests/corpora/pii/code/, today's analyzer (en_core_web_lg, PII_ENTITIES) at 0.35:
  | entity | detected | true pos | false pos | structural |
  |--------|----------|----------|-----------|------------|
  | CREDIT_CARD | 9 | 9 | 0 | 0 |
  | EMAIL_ADDRESS | 99 | 99 | 0 | 2 |
  | IBAN_CODE | 8 | 8 | 0 | 0 |
  | LOCATION | 18 | 11 | 7 | 0 |
  | PERSON | 90 | 79 | 11 | 25 |
  | PHONE_NUMBER | 71 | 66 | 5 | 0 |
  False-positive spans (today's analyzer):
    LOCATION      x4   max 0.85  'America'
    LOCATION      x2   max 0.85  'USD'
    LOCATION      x1   max 0.85  'Europe/Berlin'
    PERSON        x1   max 0.85  'Email'
    PERSON        x1   max 0.85  'Maria Lopez\n  SUPPORT_CONTACT_EMAIL'
    PERSON        x1   max 0.85  'PENDING_VERIFICATION'
    PERSON        x1   max 0.85  'SUPPORT_CONTACT_NAME'
    PERSON        x1   max 0.85  'contact.email'
    PERSON        x1   max 0.85  'display_name="Patrick O\'Brien'
    PERSON        x1   max 0.85  'expect(dir.getUserByEmail("patrick.obrien@example.org")?...
    PERSON        x1   max 0.85  'letsencrypt'
    PERSON        x1   max 0.85  'minReplicas'
    PERSON        x1   max 0.85  'ping Priya Raghunathan'
    PERSON        x1   max 0.85  'str\n    expires'
    PHONE_NUMBER  x5   max 0.75  '078-05-1120'

  Detections over code/, pattern-blank (pattern entities) at 0.35:
  | entity | detected | true pos | false pos | structural |
  |--------|----------|----------|-----------|------------|
  | CREDIT_CARD | 9 | 9 | 0 | 0 |
  | EMAIL_ADDRESS | 99 | 99 | 0 | 2 |
  | IBAN_CODE | 8 | 8 | 0 | 0 |
  | PHONE_NUMBER | 71 | 66 | 5 | 0 |
  False-positive spans (pattern-blank):
    PHONE_NUMBER  x5   max 0.75  '078-05-1120'

  Per candidate threshold (pattern-blank for pattern entities; en_core_web_lg for PERSON):
  | threshold | pattern FP (code/) | pattern TP (code/) | prose recall | required probes | PERSON FP / detected (structural) |
  |-----------|--------------------|--------------------|--------------|-----------------|-----------------------------------|
  | 0.35 | 5 | 182 | 6/6 | 2/2 | 11 / 90 (25) |
  | 0.40 | 5 | 182 | 6/6 | 2/2 | 11 / 90 (25) |
  | 0.50 | 1 | 173 | 6/6 | 0/2 | 11 / 90 (25) |
  | 0.60 | 1 | 173 | 6/6 | 0/2 | 11 / 90 (25) |
  | 0.75 | 1 | 173 | 6/6 | 0/2 | 11 / 90 (25) |

  Decision inputs (rules R1-R4, STORY-003 plan):
    R1 PII_SCORE_THRESHOLD_CODE = 0.4 (pattern FP on code/ = 5; at 0.50: FP 1, prose 6/6, probes 0/2)
    R2 budget at 200000 = 1500 ms (2 x pattern-blank p95 645.60 ms, rounded up to 250 ms; chat p95 10750 ms = 16.7x the code arm)
    R3 PII_MAX_CHARACTERS_CODE = 200000 (unchunked p95 2712 ms > budget, chunked p95 751 ms <= budget: STORY-006/008 must analyze in 20000-character line-aligned chunks)
    R4 PERSON stays out: pattern-lg p95 11126 ms at 200000 > budget 1500 ms
```
