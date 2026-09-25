---
story: STORY-008
prd: PRD-012
plan: .agents/plans/PRD-012-pii-for-code/completed/STORY-008-redact-for-policy.plan.md
epic_branch: epic/PRD-012-pii-for-code
commit: pending
status: COMPLETE
completed: 2026-09-25
---

# Implementation Report — STORY-008: redact_for_policy: fence skipping, structure-safe replacement, JSON-aware mode

**Plan**: `.agents/plans/PRD-012-pii-for-code/completed/STORY-008-redact-for-policy.plan.md`
**Epic Branch**: `epic/PRD-012-pii-for-code`
**Commit**: `pending`

## Summary

`app/services/pii_redactor.py` gains `redact_for_policy(text, policy) -> RedactionResult`. `redact()` is unchanged.

- **Master switch.** `PII_REDACTION_ENABLED=false`, or empty text, returns the text unchanged.
- **`chat`.** A policy without `structure_safe` returns `RedactionResult(*redact(text))`, so `chat` is byte-identical by construction.
- **`code`.** A structure-safe policy runs these steps:
  1. **Fence blanking** with `strip_fenced_blocks`, when `skip_fenced_blocks` is set.
  2. **Analysis** by the analyzer `policy.entities` selects, at `policy.threshold`, in line-aligned windows of at most 20,000 characters (STORY-003 R3). Windows that are only whitespace, which is what blanked fences become, skip the analyzer call.
  3. **Overlap resolution**: longest first, then earliest start, then entity type name.
  4. **Structure-safe splitting.** Quotes, backticks, line breaks, **whole escape sequences** and fenced characters are never replaced. A run with no alphanumeric character is left alone.
  5. **JSON-aware clipping** when the stripped text starts with `{` or `[` and `json.loads` accepts it. A span keeps only the parts inside a string (value or key) interior. A span over any part of a number replaces the whole token with `"<TYPE>"`. Anything else is dropped.
  6. **One splice** into the original text.
  7. **Post-condition** `json.loads(result)` in JSON mode. On failure it raises `PiiRedactorError("redaction would produce invalid JSON")`, and the message carries no text.
- **Docstring.** It states each rule and carries PRD Section 6.6's tool-call-argument paragraph verbatim.

Nothing on the request path calls `redact_for_policy` yet. STORY-009 wires it into step 6.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `RedactionResult` (NamedTuple) and the function shell: master switch, `chat` delegation | `app/services/pii_redactor.py` | ✅ |
| 2 | `_ANALYSIS_WINDOW_CHARACTERS`, `_analysis_windows`, `_analyze` (R3) | `app/services/pii_redactor.py` | ✅ |
| 3 | `_resolve_overlaps`, plus `_take` (sorted, disjoint range insert, shared with Task 5) | `app/services/pii_redactor.py` | ✅ |
| 4 | `_STRUCTURAL_CHARACTERS`, `_ESCAPE`, `_escape_intervals`, `_structure_safe_runs` | `app/services/pii_redactor.py` | ✅ |
| 5 | `_JSON_TOKEN`, `_is_json_document`, `_json_tokens`, `_replacement_ranges` | `app/services/pii_redactor.py` | ✅ |
| 6 | `_splice`, entity list, post-condition, full docstring | `app/services/pii_redactor.py` | ✅ |
| 7 | Test module scaffold: fixture, `_code`, stub analyzer, tripwire | `tests/test_pii_structure_safe.py` | ✅ |
| 8 | Tests grouped by AC, plus the mutation check | `tests/test_pii_structure_safe.py` | ✅ |
| 9 | Regression sweep and full suite | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`python -c "import app.main"`) | ✅ |
| FastAPI boot (`uvicorn app.main:app`), `GET /health` | ✅ 200 `{"status":"ok"}` |
| Frontend lint | n/a. There is no npm frontend and no linter configured, and this story changes no UI |
| `tests/test_pii_structure_safe.py` | ✅ 100 passed (52 test functions) |
| Regression sweep (10 PII and pattern modules) | ✅ 328 passed |
| Protected files: `git diff --exit-code` on `pattern_detector.py` and the 5 PRD Section 11 test files | ✅ unchanged |
| Full suite | ⚠️ run 1: 3050 passed, 26 skipped, 1 failed, 1 error; run 2: 3051 passed, 26 skipped, 1 failed. A **different** test failed each time, all outside this story's code, and every one passes on rerun (see below) |
| E2E | ✅ 6/6 |

**Full-suite failures, and why they are not this story's.**

- **Run 1.** `test_query_pipeline_multiturn.py::test_context_limit_arm_writes_exactly_one_row` failed, and `test_config.py::test_remote_endpoint_without_a_token_is_a_startup_error[https://harness-ai-acme.turso.io]` errored. The output was captured with `tail -6`, so there is no traceback. A FastAPI E2E boot was running concurrently. Both tests pass alone, and both whole modules pass together (142 passed).
- **Run 2.** Nothing else was running. `test_pattern_default_config_regression.py::test_query_verdicts_differ_from_before_prd_011_exactly_on_the_flip_set[examples-patterns-yaml]` failed on `Duplicate lookup failed: Hrana: … tcp connect error … (os error 10060)`. That is a connection timeout to the libSQL dev container. The module passes on rerun (8 passed).
- **Assessment.** None of these modules exercises `redact_for_policy`: nothing on the request path calls it yet. This is the transient libSQL behaviour PRD Section 11 and the STORY-004 report describe. It is recorded rather than claimed as a clean green run.

**Mutation check (plan Task 8)**, each change reverted, and the file confirmed byte-identical with `cmp`:

| Mutation | Tests failing |
|---|---|
| M1: `_escape_intervals` always returns `[]` | 8: the backslash, escape ×6 and mid-escape tests |
| M2: number tokens handled like strings | 12: every number-token test, PRD user story 4, both corpus number files, and 2 more |
| M3: fence guard (`analysis[i] != text[i]`) removed | 1: `test_fence_guard_never_touches_fenced_bytes` |

**Finding from M1, recorded as the plan asked.** With escape handling removed, `test_every_json_corpus_file_still_parses` still **passes**. Under the default `code` entities, no corpus span touches an escape sequence. The `\nAisha Bello` in `ticket-thread-export.json:32` is a `PERSON`, and `PERSON` is off. So F-5 is proved by the dedicated escape tests, not by the corpus. STORY-013 may want a JSON corpus entry with an email or phone directly after `\n`.

**Timing (informative; STORY-013 owns the budget assertion).** One 200,000-character message built from the `code/` corpus, through `redact_for_policy(text, get_pii_policy("code"))`, 5 runs: 534–589 ms per call. That is under the 1,500 ms budget and in line with STORY-003's chunked figure (751 ms p95).

## E2E

- [x] PRD user story 4: `{"id": 7, "contact": "bob@x.io", "phone": 4155550134}` becomes `{"id": 7, "contact": "<EMAIL_ADDRESS>", "phone": "<PHONE_NUMBER>"}`, which parses. The real analyzer scores the bare number at or above 0.40, so the Task 6 fallback note was not needed.
- [x] PRD user story 3: `email the diff to <EMAIL_ADDRESS> and call her on <PHONE_NUMBER>`.
- [x] PRD user story 1: a `new User("Jane Doe", "jane@example.com")` line inside a ```` ```java ```` fence comes back byte-identical, with `entities == []`.
- [x] Every file in `tests/corpora/pii/json/` parses after redaction under `get_pii_policy("code")`. The entities found are listed per file.
- [x] `test_pii_characterization.py` is green and unedited.
- [x] `test_query_outcomes_regression.py` and `test_chat_outcomes_regression.py` are green in the full suite.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/pii_redactor.py` | UPDATE | +327/-2 |
| `tests/test_pii_structure_safe.py` | CREATE | +586 |

## Deviations from Plan

1. **Whitespace-only windows skip the analyzer call.** Not in the plan. A blanked fence is all newlines, so a window made only of whitespace cannot contain a match. Skipping it saves one analyzer call per such window. `test_blank_windows_skip_the_analyzer` pins it.
2. **`_take` is shared by overlap resolution (P5) and range collection (P8).** The plan described them separately. Both need "insert into a sorted, disjoint list unless it overlaps, and the earlier one wins", and one `bisect` helper keeps both O(n log n).
3. **Two test expectations were corrected while writing the tests. The code did not change.**
   - A run is replaced whole, so in `C:\jane` the run `C:` becomes `<PERSON>`, colon included.
   - In `caf\u00e9 jane@x.io`, the space after the escape belongs to the masked run. Whitespace is not structural in PRD 6.6 rule 1.
4. **Extra tests beyond the plan's list:**
   - `\r\n` splitting;
   - a span that starts inside an escape;
   - a span over structure only (`entities == []`);
   - disjoint spans all kept;
   - two spans on one number token replaced once;
   - a top-level number is not JSON mode;
   - `test_number_token_phones_become_strings` (`crm-contact-search.json`);
   - the non-vacuity guard for the fenced-corpus test;
   - hard-cut windows.
5. **The plan-commit precedent was followed.** The plan was committed on its own first (`418ab9f docs(PRD-012): STORY-008 plan`), as for STORY-004 to STORY-007.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_pii_structure_safe.py` | **AC 1:** fenced unchanged / prose masked (```` ``` ````, `~~~`); inline span masked; unterminated fence; skip off; fence guard; corpus fenced bytes identical (×7); non-vacuity guard. **AC 2:** quotes kept; `\n`, `\r\n`, backtick, backslash splitting; escapes kept whole (×6); span starting mid-escape; `O'Brien`; non-alphanumeric run left alone; structure-only span; structural counts over the code corpus (×7). **Overlaps:** longest, earliest, entity name, disjoint. **AC 3:** string value, key, number token, partial number (×3), two spans on one number, dropped spans (×6), multi-token clipping, formatting kept, PRD user story 4, JSON corpus parses (×5), cards, phones, keys, non-JSON text (×3), top-level number, leading whitespace. **AC 4:** post-condition raises with no text in the message; analysis failure. **AC 5:** equals `redact` over `REDACT_CASES`; delegation spy; policy fields match `redact`'s settings. **Other:** `en_core_web_lg` never touched; selection by `policy.entities`; master switch; empty text; sorted entities, only those replaced; windows match `bench._chunks` (×7); hard cut; PII past the first window; blank windows skipped |

## Handoff (for later stories)

- **STORY-009**:
  - Call `redact_for_policy(m.content, policy)` for the roles in `policy.input_roles`. It unpacks like `redact()`, and under `chat` it **is** `redact()`.
  - `PiiRedactorError` covers both analysis failure and the JSON post-condition. Neither message carries content.
- **STORY-010**: count analyzable characters with `strip_fenced_blocks`, the blanking this module uses.
- **STORY-012**: masked JSON keys in one object collide on one placeholder, and the last one wins on parse. Number tokens become strings.
- **STORY-013**:
  - Extend these corpus tests rather than duplicating them.
  - Add a JSON corpus entry with a default-entity span right after an escape (the M1 finding).
  - Measure the budget through `redact_for_policy`, which is now chunked.

## Acceptance Criteria

- [x] Given `redact_for_policy(text, code_policy)`, when `text` has an email inside a ```` ``` ```` or `~~~` fence and another in prose, then the fenced one is unchanged and the prose one becomes `<EMAIL_ADDRESS>`; an email inside an inline backtick span **is** masked; an unterminated fence skips to end of text.
- [x] Given a structure-safe policy, when a span covers `"jane@example.com"` including its quotes, or contains a backslash, a backtick or a line break, then every quote, backslash, backtick and line break stays in place, the span is split around them, and runs without an alphanumeric character are left alone (`O'Brien` masks as `<PERSON>'<PERSON>` when `PERSON` is enabled).
- [x] Given content that is a JSON object or array, when PII sits in a string value or key, then it is replaced inside the quotes; when PII is a number token (`"phone": 4155550134`), then the whole token becomes `"<PHONE_NUMBER>"`; spans over punctuation, `true`/`false`/`null` or whitespace are dropped; and `json.loads(result)` succeeds for every file in `tests/corpora/pii/json/`.
- [x] Given a stub analyzer that returns a span which would make the result unparseable, when JSON-aware mode runs, then `PiiRedactorError("redaction would produce invalid JSON")` is raised.
- [x] Given `redact_for_policy(text, chat_policy)`, when it runs, then the result is identical to `redact(text)`, and `redact()` itself is unchanged (characterization green).
