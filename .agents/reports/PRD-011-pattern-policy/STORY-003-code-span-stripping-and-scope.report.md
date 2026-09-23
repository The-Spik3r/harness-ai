---
story: STORY-003
prd: PRD-011
plan: .agents/plans/PRD-011-pattern-policy/completed/STORY-003-code-span-stripping-and-scope.plan.md
epic_branch: epic/PRD-011-pattern-policy
commit: a7f75a2
status: COMPLETE
completed: 2026-09-22
---

# Implementation Report — STORY-003: Code-span stripping and the `outside_code` scope

**Plan**: `.agents/plans/PRD-011-pattern-policy/completed/STORY-003-code-span-stripping-and-scope.plan.md`
**Epic Branch**: `epic/PRD-011-pattern-policy`
**Commit**: `a7f75a2`

## Summary

`strip_code_spans(text) -> str` is added to `app/services/pattern_detector.py`, with the two module-level regexes (`_FENCE_OPEN`, `_INLINE_SPAN`) and the private `_blank` helper it needs. It has no production caller: `pattern_config.load()` (STORY-005) is what reads a list's `scope`, and `inspect()` (STORY-008) is what hands each list the right variant of a message's text. The module gained no import — `re` arrived with STORY-002 — and stays pure in the `app/models/messages.py` sense (PRD Section 6.9). The diff on the module is **89 insertions, 0 deletions**.

Two passes, PRD Section 6.5. Fences first, line-anchored: an opener is three or more backticks or tildes at the start of a line with up to three leading spaces, and the closer is a run of the *same* character *at least as long*, alone on its line; an unterminated fence runs to the end of the text. Inline spans second, over the already-blanked text, so a backtick inside a fenced block can never open one. Blanking means `re.sub(r"[^\n]", "\n", span)`: same length, every non-newline character becomes a newline, which is what preserves match offsets and keeps the lines either side of a block from fusing.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `_FENCE_OPEN`, `_INLINE_SPAN`, `_blank` | `app/services/pattern_detector.py` | ✅ |
| 2 | `strip_code_spans(text)` + the docstring that is an AC | `app/services/pattern_detector.py` | ✅ |
| 3 | The five ACs, T6, and the docstring assertion | `tests/test_pattern_matching.py` | ✅ |
| 4 | Full suite, scope check, commit | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Module purity (`re`, `dataclasses`, `typing` only; no `settings`, `open(`, `Path(`) | ✅ |
| F-1 guard — `grep -niE "pii\|redact\|presidio"` on the module | ✅ no output |
| `pattern_detector.py` diff is additions only | ✅ 89 / 0 |
| `tests/test_pattern_matching.py` | ✅ 63 passed |
| Full suite | ✅ 2339 passed, 26 skipped |
| E2E | ✅ 6/6 |

There is no frontend lint step for this story: the repo's UI is Reflex (`chat_ui/`) and nothing in it is touched.

### E2E checklist (from the plan)

- [x] `tests/test_pattern_matching.py` — green, STORY-002's cases unchanged in behaviour
- [x] `tests/test_pattern_characterization.py` — green, unmodified; `fenced-at-override` still reports `override`
- [x] `tests/test_pattern_detector.py` — green, byte-unmodified (layer 1)
- [x] `tests/test_pii_dedup_isolation.py` + `tests/test_pii_redaction_integration.py` — 37 passed; the F-1 guard passes on the edited module
- [x] `tests/test_query_outcomes_regression.py`, `test_query_router.py`, `test_integration.py` — 62 passed, no assertion changed
- [x] `pytest tests/ -q` — 2339 passed, 26 skipped

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/pattern_detector.py` | UPDATE | +89 / -0 |
| `tests/test_pattern_matching.py` | UPDATE | +310 / -2 |
| `.agents/plans/PRD-011-pattern-policy/completed/STORY-003-…plan.md` | CREATE | +379 |

## Deviations from Plan

1. **The docstring assertion compares flowed text, not raw.** The plan's Task 3 asked the test to assert `"unfenced source gets no protection"` is in `strip_code_spans.__doc__`. It failed on the first run: the sentence wraps across a docstring line, so the raw string contains a newline and indentation mid-phrase. The test now asserts against `" ".join(doc.split())`, with a comment saying why — the claim is about the wording, not about where the line happens to wrap, and rewrapping the paragraph must not fail the test. No weakening: every phrase the plan named is still asserted.

2. **One escape-sequence bug of my own, found and fixed before the commit.** The `strip_code_spans` docstring originally wrote `` `\s+` `` inside a non-raw string, which Python 3.11 reports as `DeprecationWarning: invalid escape sequence '\s'` — it showed up in the full-suite run as `<unknown>:178`. Corrected to `` `\\s+` ``, matching what `compile_pattern`'s docstring already does two functions above. Verified by compiling both files under `-W error::SyntaxWarning -W error::DeprecationWarning`; the suite's warning count dropped from 4 to 2, the remaining two being third-party (`starlette`, `anyio`).

3. **One flaky full-suite error, not reproduced.** The first full-suite run reported `ERROR tests/test_chat_state.py::test_a_failed_read_keeps_the_transcript_and_reports_it` alongside 2338 passes. `pytest tests/test_chat_state.py` alone passed 140/140, and after restarting the libSQL dev container the full suite passed clean. This is the documented degradation of the dev server under repeated suites (plan R-9) — no code was bisected.

Everything else matched the plan, including D-A: `pattern_detector` exposes `strip_code_spans` and no scope-applying API, and the scope logic lives in the four-line test-local `_scoped_text` that names STORY-008 as its successor.

## Cost measurement (PRD Section 11, *Quality indicators*)

Measured against the committed implementation, not the prototype. Both regexes are a simple star with no nested quantifier, so there is no backtracking blowup to bound:

| Input | Size | Time |
|---|---|---|
| 100,000 backticks on one line | 100 KB | 0.0061 s |
| Unterminated fence over 12,000 lines | 108 KB | 0.0060 s |
| Plain prose, no code at all | 101 KB | 0.0016 s |
| 1,000 tiny inline spans | 6 KB | 0.0011 s |

Each ran with `len(result) == len(text)` holding. These are the stripping half of the inspection cost STORY-011 measures at the `CONTEXT_MAX_MESSAGES` ceiling.

## Carried forward to STORY-008

- **PRD Risk 8's budget is not enforceable here.** `strip_code_spans` has no view of the message walk, so "once per message per scope requested, not once per pattern" is the caller's to keep. It is stated in the function's docstring and is the reason `_scoped_text` in the tests is a stand-in rather than shipped code.
- **A phrase matches across a blanked span**, because a blanked span is whitespace and a `word` pattern joins its tokens with `\s+`. Pinned by `test_a_phrase_still_matches_across_a_stripped_span` with its reasoning, so it is met as a decision rather than as a surprise.
- **`scope: everywhere` lists must never be passed through this function** — that is what stops a fence hiding an injection phrase (T6).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_pattern_matching.py` | `test_a_fenced_block_is_stripped_and_its_surroundings_are_not` (4 params: backtick, tilde, three-space-indented opener, info string) · `test_stripping_preserves_offsets_and_does_not_fuse_the_lines_either_side` · `test_inline_spans_are_stripped_and_a_lone_backtick_is_not` (4 params, incl. `lone-backtick-unchanged`) · `test_a_backtick_inside_a_fence_cannot_open_an_inline_span` · `test_an_unterminated_fence_strips_to_the_end_of_the_text` · `test_the_closer_is_the_same_character_and_at_least_as_long` (3 params) · `test_outside_code_reports_only_the_hit_outside_the_fence` · `test_everywhere_reports_the_first_hit_in_text_order_fence_or_not` · `test_a_fence_is_not_an_evasion_for_the_injection_list` (T6) · `test_a_phrase_still_matches_across_a_stripped_span` · `test_text_with_no_code_is_returned_unchanged` (4 params) · `test_strip_code_spans_documents_itself_as_a_heuristic` · helpers `_assert_blanked_in_place`, `_scoped_text` |

`_assert_blanked_in_place` runs inside every stripping test rather than only AC 2's, so a change from blanking to deleting fails broadly instead of in one place.

## Acceptance Criteria

- [x] A backtick- or tilde-fenced block opening at the start of a line has its content replaced; the surrounding text is returned unchanged
- [x] `len(result) == len(text)` and every non-newline character of the span has become a newline — offsets survive, and the lines either side cannot fuse
- [x] Single-, double- and triple-backtick inline spans are stripped; a lone unmatched backtick strips nothing and raises nothing
- [x] An unterminated fence strips to the end of the text
- [x] Under `scope: outside_code` only the hit outside the fence is reported; under `scope: everywhere` the first hit in text order is reported, fence or not
- [x] The docstring states it is a heuristic and that unfenced source gets no protection from it, and a test asserts that wording
- [x] A test named for PRD 9.2 T6 shows a fenced `ignore previous instructions` still matching under `scope: everywhere`
- [x] The module stays pure: no `settings` import, no file I/O, nothing read at import
- [x] `SUSPICIOUS_PATTERNS`, `detect_suspicious_pattern`, `compile_pattern` and `has_nested_quantifier` unchanged; `tests/test_pattern_characterization.py` green and unmodified
- [x] All tasks completed
- [x] Full suite green
- [x] No assertion changed in `test_query_router.py`, `test_integration.py` or `test_query_outcomes_regression.py`
- [x] Follows existing patterns
