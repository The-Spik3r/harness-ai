---
story: STORY-001
prd: PRD-012
plan: .agents/plans/PRD-012-pii-for-code/completed/STORY-001-pii-corpora.plan.md
epic_branch: epic/PRD-012-pii-for-code
commit: PENDING
status: COMPLETE
completed: 2026-09-23
---

# Implementation Report — STORY-001: PII corpora: code, prose and JSON samples as checked-in files

**Plan**: `.agents/plans/PRD-012-pii-for-code/completed/STORY-001-pii-corpora.plan.md`
**Epic Branch**: `epic/PRD-012-pii-for-code` (created from `origin/main` @ `e10d191`)
**Commit**: `PENDING`

## Summary

`tests/corpora/pii/` now holds three corpora and a provenance file. All data is synthetic and none of it is production code:

| Directory | Files | Lines | Characters |
|---|---|---|---|
| `code/` | 7: `.java`, `.ts`, `.py`, `.yaml`, `.json`, two `.md` | 1,487 | 48,856 |
| `prose/` | 6 messages, each with a `# expect: …` header | 151 | 6,073 |
| `json/` | 4 tool-result documents | 881 | 23,039 |

`tests/corpora/pii/SOURCES.md` records:
- the source of each class of value
- the invented cast of names
- the Presidio measurements that shaped the files
- what the header means
- one section per sample

`tests/test_pii_corpus_files.py` has 24 tests: 12 guards and 12 per-file cases. They prove the files exist, parse, hold the edge cases the story names, and declare what they contain. They also check that the files are synthetic and that `SOURCES.md` names every one. **They assert nothing about redaction.**

No production module, schema, setting or dependency changed. `git diff --stat origin/main -- app/ chat_ui/ requirements*.txt` is empty.

## Tasks Completed

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 0 | Preflight: created the epic branch from `main`, committed the PRD and stories (`c313842`) and the plan (`c749ee3`) separately, and recorded the baseline: 2613 passed, 26 skipped | — | ✅ |
| 1 | `code/` source and config files, 196–237 non-blank lines each | `CustomerFixtures.java`, `contact-directory.ts`, `billing_seed.py`, `staging-values.yaml`, `seed-users.json` | ✅ |
| 2 | `code/` Markdown: mixed fences plus an unterminated fence | `onboarding-runbook.md`, `handoff-unterminated.md` | ✅ |
| 3 | `prose/` with declared entities | 6 files | ✅ |
| 4 | `json/` tool results | 4 files | ✅ |
| 5 | Provenance | `SOURCES.md` | ✅ |
| 6 | Loader test | `tests/test_pii_corpus_files.py` | ✅ |
| 7 | Guard-bite checks (10), then the full suite | — | ✅ |
| 8 | This report | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Frontend lint | N/A. No frontend in the change, and the repository has no npm frontend (the UI is Reflex/Python) |
| `/health` smoke (uvicorn on :8765) | ✅ `{"status":"ok"}` [200] |
| `pytest tests/test_pii_corpus_files.py` | ✅ 24 passed |
| Full suite | ✅ 2637 passed, 26 skipped (baseline 2613 plus these 24) |
| No production diff | ✅ empty |
| E2E checklist | ✅ 6/6 |

### Data-sanity scripts (Tasks 2–4; not part of the test suite)

- **Fences** (checked with `strip_code_spans`):
  - `onboarding-runbook.md` has 22 emails, 11 of them outside fences and inline spans. The `````` ```` `````` block also blanks the ```` ``` ```` lines inside it.
  - `handoff-unterminated.md`: the text is blanked through to end of file.
- **Prose, checked with today's analyzer**:
  - Every declared type is found at 0.35 (`chat`).
  - Every declared non-NER type is found at 0.5 (the provisional `code` threshold).
  - No prose phone scores below 0.5.
- **JSON number tokens at ≥ 0.5**:
  - All 24 `"phone": 1NPA55501xx` tokens in `crm-contact-search.json` are detected.
  - `4111111111111111`, `5555555555554444` and `12125550147` in `payment-webhook.json` are detected.
  - The 10-digit order number `4000813378` is not detected, which is correct.
- **YAML**: `staging-values.yaml` loads with `yaml.safe_load`. PyYAML is present transitively but not declared, so this check is not a test.

### Guard-bite checks (Task 7)

Each mutation was applied, the named test failed, and the corpus was restored. `diff -r` against a backup came out identical.

| # | Mutation | Observed failure |
|---|---|---|
| 1 | Delete line 1 of `payroll-bank-change.txt` | `payroll-bank-change.txt: line 1 is not '# expect: <ENTITY>, <ENTITY>, ...' (got 'Hello HR team,')` |
| 2 | `EMAIL_ADDRESS` → `EMAIL` in a header | `agent-task-with-contacts.md: unknown entity types ['EMAIL']` |
| 3 | Remove `CREDIT_CARD` from every header | `no prose sample declares ['CREDIT_CARD']` |
| 4 | Delete the last `}` of `crm-contact-search.json` | `crm-contact-search.json: does not parse: Expecting ',' delimiter at line 552, column 1` |
| 5a | Quote every phone and card number token | `no phone as a JSON number token` |
| 5b | Quote only the card number tokens | `no card number as a JSON number token` |
| 6 | Append `x = (` to `billing_seed.py` | `SyntaxError` from `ast.parse` at `billing_seed.py`, line 282 |
| 7 | Close the final fence of `handoff-unterminated.md` | `no .md sample ending inside an unterminated fence` |
| 8 | Add `bob@corp.com` to a prose file | `emails outside example.com / example.org: [('agent-task-with-contacts.md', 'corp.com')]` |
| 9 | Add `prose/extra.txt` | `extra.txt has no provenance in SOURCES.md` |
| 10 | Copy `billing_seed.py` to `test_billing_seed.py` | `corpus files pytest would collect: ['test_billing_seed.py']` |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/corpora/pii/SOURCES.md` | CREATE | +238 |
| `tests/corpora/pii/code/CustomerFixtures.java` | CREATE | +266 |
| `tests/corpora/pii/code/contact-directory.ts` | CREATE | +265 |
| `tests/corpora/pii/code/billing_seed.py` | CREATE | +281 |
| `tests/corpora/pii/code/staging-values.yaml` | CREATE | +218 |
| `tests/corpora/pii/code/seed-users.json` | CREATE | +237 |
| `tests/corpora/pii/code/onboarding-runbook.md` | CREATE | +157 |
| `tests/corpora/pii/code/handoff-unterminated.md` | CREATE | +63 |
| `tests/corpora/pii/prose/support-refund-request.txt` | CREATE | +25 |
| `tests/corpora/pii/prose/payroll-bank-change.txt` | CREATE | +23 |
| `tests/corpora/pii/prose/vendor-onboarding.md` | CREATE | +25 |
| `tests/corpora/pii/prose/benefits-enrollment.txt` | CREATE | +25 |
| `tests/corpora/pii/prose/agent-task-with-contacts.md` | CREATE | +19 |
| `tests/corpora/pii/prose/escalation-thread.txt` | CREATE | +34 |
| `tests/corpora/pii/json/crm-contact-search.json` | CREATE | +551 |
| `tests/corpora/pii/json/payment-webhook.json` | CREATE | +126 |
| `tests/corpora/pii/json/directory-index-by-email.json` | CREATE | +110 |
| `tests/corpora/pii/json/ticket-thread-export.json` | CREATE | +94 |
| `tests/test_pii_corpus_files.py` | CREATE | +322 |

## Deviations from Plan

1. **`crm-contact-search.json` is 551 lines**, against the plan's 80–300. It holds 24 contact records, the number the plan asked for, and pretty-printing each one with its nested `address.geo` takes about 23 lines. It was generated once by a deterministic script and then checked in. The larger size helps STORY-003's benchmark, and nothing depends on the upper bound.
2. **The unterminated-fence check.** The plan's check was "the last opener found by `finditer` has no closer after it". That cannot work, because a closing fence line matches the same regex as an opener, so the last match is often a closer. The check is now `_ends_inside_a_fence`: the text after the last fence-like line is non-empty, and `strip_code_spans` blanks all of it. A fence closed at end of file has nothing after its closer. A closer followed by prose leaves that prose unblanked. Guard-bite 7 confirms the check fails when the fence is closed.
3. **`_declared` returns `tuple[str, ...]` rather than `frozenset`**, keeping file order so the duplicate check can see duplicates. Consumers call `set()` on it.
4. **An extended cast.** `crm-contact-search.json` uses sixteen invented names beyond the eight-name cast, so that a 24-record search result is realistic. They are listed in `SOURCES.md`. The loader test's `_CAST` check applies only to `code/`, which uses the core cast.
5. **Guard-bite 5 was run twice (5a, 5b).** The first assertion to fail hides the second, so the card-number check was confirmed on its own.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_pii_corpus_files.py` | These tests: <ul><li>`test_the_code_corpus_holds_every_required_kind_of_file`</li><li>`test_the_code_corpus_mixes_fenced_and_unfenced_code_in_markdown`</li><li>`test_the_code_corpus_has_an_apostrophe_name`</li><li>`test_the_code_corpus_has_pii_against_its_quotes`</li><li>`test_the_code_corpus_has_an_escaped_quote_and_a_backslash_path`</li><li>`test_the_code_corpus_has_an_unterminated_fence`</li><li>`test_every_prose_sample_declares_its_entities`, ×6</li><li>`test_the_prose_corpus_covers_the_required_entities`</li><li>`test_every_json_sample_parses`, ×5</li><li>`test_the_json_corpus_covers_strings_keys_numbers_nesting_and_escapes`</li><li>`test_the_corpus_holds_a_python_sample`</li><li>`test_every_python_sample_parses`, ×1</li><li>`test_no_corpus_python_file_is_collectable_as_a_test`</li><li>`test_every_email_in_the_corpus_is_on_a_reserved_domain`</li><li>`test_sources_names_every_sample`</li></ul> |

## Findings for later stories

**STORY-003 (benchmark, thresholds)**
- **Bare phone numbers.** A `555-01xx` number with area code scores **0.40** as `PHONE_NUMBER` with no context word, and **0.75** with `phone` / `mobile` / `cell` / `telephone` nearby. `call` does not boost it. At the provisional `PII_SCORE_THRESHOLD_CODE=0.5`, bare numbers in prose are **not masked**. Weigh that when fixing the threshold. A 7-digit `555-0142` is never detected.
- **`LOCATION` false positives.** The word `IBAN` is itself a 0.85 `LOCATION`, and so is `UK`.
- **`US_SSN`.** `078-05-1120` is rejected as `US_SSN` and scores as a 0.40 `PHONE_NUMBER` instead, a false positive under `chat`.
- **Corpus size.** `code/` is about 48.9k characters. A 200k-character conversation needs the code corpus about four times over, plus prose filler. Say in the report how it is repeated.
- **Analyzer versions.** Measured with presidio-analyzer 2.2.364, presidio-anonymizer 2.2.364, spaCy 3.8.16 and phonenumbers 9.0.38. These are the candidates for pinning.

**STORY-008 / STORY-013 (behaviour over the corpora)**
- **Intersect declared entities with the policy's.** Prose headers mean "types present". Assert `set(declared) & set(policy.entities) <= found`. `PERSON` is declared in five of the six prose files and is off under default `code` (D7). Every file declares at least one non-NER type, so no case is vacuous.
- **Reuse the discovery code.** Import `_PROSE_FILES`, `_JSON_FILES`, `_CODE_FILES` and `_declared` from `tests.test_pii_corpus_files`.
- **Where each edge case lives**, for STORY-008's structure-safe tests:

  | Edge case | Location |
  |---|---|
  | Apostrophe name, double-quoted | `CustomerFixtures.java:83`, `billing_seed.py:92` |
  | Apostrophe name, escaped in a single-quoted string (PRD Risk 4) | `billing_seed.py:123` (`'Patrick O\'Brien'`) |
  | Escaped quotes around a phone number | `CustomerFixtures.java:175`, `billing_seed.py:133` |
  | JSON inside a Java string | `CustomerFixtures.java:261` |
  | An email wrapped in escaped quotes | `contact-directory.ts:239` (`"\"maria\"@example.com"`) |
  | Backslash paths | `CustomerFixtures.java:52`; `contact-directory.ts:38, 59` (the second inside a single-quoted string); `billing_seed.py:34` (raw) and `:36` (UNC) |
  | Unterminated fence | `handoff-unterminated.md:41` (```` ```yaml ```` to end of file) |
  | Unfenced code in Markdown | `onboarding-runbook.md:44` (`curl`) and `:91-92` (Java) |
  | Four-backtick fence containing ```` ``` ```` | `onboarding-runbook.md:114-123` |
  | `~~~~` fence | `onboarding-runbook.md:102-107` |
  | Inline-span email that must stay masked (D2) | `onboarding-runbook.md:18` (`` `ops@example.org` ``) |
  | Number-token phone | `payment-webhook.json:35`; every record in `crm-contact-search.json` |
  | Number-token card | `payment-webhook.json:49, 114` |

## Acceptance Criteria

- [x] Given `tests/corpora/pii/code/`, when it is listed, then it holds at least one `.java`, `.ts`, `.py`, `.yaml` and `.json` file, each containing example emails, personal names and phone-shaped numbers, and at least one Markdown file mixing fenced (```` ``` ```` and `~~~`) and unfenced code with PII in the prose around the fences.
- [x] Given the code corpus, when it is read, then it includes the named edge cases: a name with an apostrophe (`O'Brien`), a string literal whose PII sits right against its quotes, an escaped quote and a backslash path inside a string, and an unterminated fence.
- [x] Given `tests/corpora/pii/prose/`, when each file is read, then it declares its expected entity types in a header (the PRD-011 `injections/` convention), covering at least `EMAIL_ADDRESS`, `PHONE_NUMBER`, `CREDIT_CARD`, `IBAN_CODE` and `PERSON`.
- [x] Given `tests/corpora/pii/json/`, when each file is loaded with `json.loads`, then it parses; together they cover PII in string values, PII in keys, a phone and a card number as JSON **number** tokens, nesting, and `\\` / `\"` escapes inside strings.
- [x] Given a small loader test (`tests/test_pii_corpus_files.py`), when it runs, then every JSON file parses, every `.py` file passes `ast.parse`, and every prose file has a readable expected-entities declaration. It asserts nothing about redaction yet.
- [x] All tasks completed
- [x] Full suite green
- [x] Follows existing patterns
