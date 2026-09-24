---
story: STORY-004
prd: PRD-012
plan: .agents/plans/PRD-012-pii-for-code/completed/STORY-004-strip-fenced-blocks.plan.md
epic_branch: epic/PRD-012-pii-for-code
commit: pending
status: COMPLETE
completed: 2026-09-24
---

# Implementation Report — STORY-004: Extract strip_fenced_blocks; rebuild strip_code_spans on it

**Plan**: `.agents/plans/PRD-012-pii-for-code/completed/STORY-004-strip-fenced-blocks.plan.md`
**Epic Branch**: `epic/PRD-012-pii-for-code` (BASE `0c841cf`, plan commit `b0bb393`)
**Commit**: pending

## Summary

The fence loop of `strip_code_spans` now lives in its own function, `strip_fenced_blocks(text: str) -> str`, in `app/services/pattern_detector.py`. The new function is public and pure.

- The loop moved **verbatim**: a `diff` of the old lines 196-212 against the new body is empty. The only new line is `return "".join(out)`.
- `strip_code_spans` is now the inline pass applied to `strip_fenced_blocks(text)`.
- `_FENCE_OPEN`, the closer regex, `_INLINE_SPAN`, `_blank` and `inspect()` are unchanged.
- In the `strip_code_spans` docstring, only the "Two passes" paragraph changed, to name `strip_fenced_blocks()`. The five phrases PRD-011's docstring test asserts are still there.

A new module, `tests/test_pattern_fenced_blocks.py` (125 collected tests), covers AC 1, 2, 3 and 5. AC 2 and the AC 3 equivalence check run as properties over every file under `tests/corpora/`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Extract `strip_fenced_blocks`; rebuild `strip_code_spans` on it; module docstring and section banner | `app/services/pattern_detector.py` | ✅ |
| 2 | New test module for AC 1, 2, 3 and 5 | `tests/test_pattern_fenced_blocks.py` | ✅ |
| 3 | Regression sweep | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Frontend lint | N/A. The repo has no npm frontend, the chat UI is Reflex, and nothing in it changed |
| PRD-011 suites named in AC 4 (`test_pattern_matching`, `test_pattern_corpus`, `test_pattern_profiles`, `test_query_pipeline_patterns`) | ✅ 195 passed, the same as the baseline. `git diff --exit-code` on the four files is clean |
| Other `pattern_detector` importers (`test_pattern_detector`, `test_pattern_config`, `test_pii_corpus_files`, `test_pattern_characterization`, `test_pattern_default_config_regression`) | ✅ 142 passed, the same as the baseline |
| New module `tests/test_pattern_fenced_blocks.py` | ✅ 125 passed |
| Full suite (`pytest -q`, local libSQL on :8080) | ✅ 2843 passed, 26 skipped |
| E2E | ✅ 4/4 |

### E2E

- [x] `test_query_pipeline_patterns.py` passes unchanged, which means `run_conversation` step 5 still sees the same stripping.
- [x] `test_pattern_corpus.py` passes unchanged. It includes `direct-fenced-evasion.md` run through `inspect()`.
- [x] The plan's REPL check passed: `ops@corp.com` survives `strip_fenced_blocks`, `jane@` does not, and `strip_code_spans` blanks `ops@corp.com`.
- [x] Smoke test: `uvicorn app.main:app` started, which includes `pattern_config.load()`, and `GET /health` returned `200 {"status":"ok"}`. The server was then stopped.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/pattern_detector.py` | UPDATE | +65/-28 |
| `tests/test_pattern_fenced_blocks.py` | CREATE | +246 |

## Deviations from Plan

1. **The docstrings do not use the words "PII", "redact" or `pii_redactor`.** The plan's Task 1 wording for the `strip_fenced_blocks` docstring named `pii_redactor` and "PII". The first full-suite run then failed `tests/test_pii_dedup_isolation.py::test_dedup_and_pattern_sources_unmodified_on_this_branch`.

   That test (PRD-011 STORY-002, RF-6) enforces "no redaction dependency" by asserting that `pattern_detector`'s source contains no `pii`, `redact` or `presidio`. The plan's exploration missed it because it does not import any stripping function.

   I kept the guard test as it was and changed the prose to "personal-data masking", "masking step" and "real personal data". The module docstring now also says why that wording is used, so a later editor does not put the words back.

   Consequence for STORY-008: the new function's docstring cannot name its future caller by module name. The one-way dependency is described in prose.
2. **The plan's sanity check expected test 7 to fail, and it did not.** I made `strip_fenced_blocks` return `text` unchanged. As expected, the fenced-block cases, the inline-spans-beside-a-fence case and the non-vacuity guard all failed. The behavioural equivalence test did not fail. That is correct: `strip_code_spans` is now built on the sabotaged function, so both sides of the comparison change together.

   That test catches a divergent **copy** of the loop, together with its structural partner `test_strip_code_spans_is_built_on_strip_fenced_blocks`. It does not catch a broken fence pass. The 195 unchanged PRD-011 tests catch that. I reverted the sabotage and confirmed it with `grep` and `git diff --stat`.
3. **Two tests were added and one was split.** `test_the_corpora_include_fenced_samples` guards the corpus property tests against passing vacuously. The plan's test 7 is split into a behavioural test (`…_is_the_inline_pass_over_strip_fenced_blocks`) and a structural one (`…_is_built_on_strip_fenced_blocks`), which also asserts that `_FENCE_OPEN` no longer appears in `strip_code_spans`.
4. **One transient error in the first full run.** `tests/test_db.py::test_audit_logs_added_columns_carries_a_nullable_dedup_key` errored once during setup. It passed when `test_db.py` was run alone (189 passed) and in the second full run. This story changes no database code.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_pattern_fenced_blocks.py` | `test_strip_fenced_blocks_is_public_and_pure`; `test_a_fenced_block_is_blanked` ×7 (backtick fence with info string, tilde fence, three-space-indented opener, longer run closes, shorter run does not close, other character does not close, unterminated runs to the end); `test_an_inline_span_outside_any_fence_is_left_intact` (AC 5); `test_inline_spans_survive_beside_a_fence`; `test_text_with_no_fence_is_returned_unchanged` ×4; `test_blanking_preserves_length_and_every_newline_offset` ×36 corpus files; `test_blanking_is_idempotent` ×36; `test_the_corpora_include_fenced_samples`; `test_strip_code_spans_is_the_inline_pass_over_strip_fenced_blocks` ×36; `test_strip_code_spans_is_built_on_strip_fenced_blocks`; `test_strip_code_spans_docstring_still_describes_both_passes` |

## Acceptance Criteria

- [x] Given `app/services/pattern_detector.py`, when it is read, then `strip_fenced_blocks(text: str) -> str` is public and pure, blanks fenced blocks (```` ``` ```` and `~~~`, same-character closer at least as long, unterminated to end of text) with newlines, and leaves inline backtick spans untouched.
- [x] Given any text, when `strip_fenced_blocks` runs, then `len(result) == len(text)` and every newline stays at its original offset.
- [x] Given `strip_code_spans`, when it is read, then it is the inline pass applied to `strip_fenced_blocks(text)`, and its docstring still describes both passes.
- [x] Given PRD-011's `test_pattern_matching.py`, `test_pattern_corpus.py`, `test_pattern_profiles.py` and `test_query_pipeline_patterns.py`, when the suite runs, then they pass with no modification.
- [x] Given a new test, when an inline span holding `ops@corp.com` sits outside any fence, then `strip_fenced_blocks` leaves it intact and `strip_code_spans` blanks it.
- [x] All tasks completed
- [x] Full test suite passes
- [x] App imports without error
- [x] Follows existing patterns
