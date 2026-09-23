---
story: STORY-002
prd: PRD-011
plan: .agents/plans/PRD-011-pattern-policy/completed/STORY-002-word-and-regex-compilation.plan.md
epic_branch: epic/PRD-011-pattern-policy
commit: 116e0aa
status: COMPLETE
completed: 2026-09-22
---

# Implementation Report — STORY-002: Word-boundary and regex pattern compilation

**Plan**: `.agents/plans/PRD-011-pattern-policy/completed/STORY-002-word-and-regex-compilation.plan.md`
**Epic Branch**: `epic/PRD-011-pattern-policy`
**Commit**: `116e0aa`

## Summary

`app/services/pattern_detector.py` gained three names — `PatternCompileError`, `compile_pattern(pattern, match)` and `has_nested_quantifier(pattern)` — plus a module docstring and `import re`. Nothing calls them: the pipeline still calls `detect_suspicious_pattern`, `SUSPICIOUS_PATTERNS` is unchanged, and the diff on the module is **additions only, zero deleted lines** (`git show 116e0aa -- app/services/pattern_detector.py`). The module stays pure in the `app/models/messages.py` sense — no `settings`, no file I/O, nothing read at import beyond one compiled constant — and a test now enforces that rather than trusting it.

Word compilation is PRD Section 6.2's formula verbatim. Regex compilation is the pattern as written under `re.IGNORECASE`, with `re.error` wrapped so the message names both the pattern and the engine's own complaint. `has_nested_quantifier` is the ReDoS heuristic PRD 9.2 T4 describes, and its docstring — which AC 5 makes a deliverable — is asserted by a test, because that wording is the only thing keeping a documented limit from being read later as a guarantee.

The story also had to retire a guard outside its own files. See *Deviations*.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Module docstring, `import re`, `PatternCompileError` | `app/services/pattern_detector.py` | ✅ |
| 2 | `compile_pattern(pattern, match)` — word and regex modes | `app/services/pattern_detector.py` | ✅ |
| 3 | `_NESTED_QUANTIFIER` + `has_nested_quantifier(pattern)` | `app/services/pattern_detector.py` | ✅ |
| 4 | Retire PRD-009's source-byte pin, keep the RF-6 claim | `tests/test_pii_dedup_isolation.py` | ✅ |
| 5 | The five ACs as tests | `tests/test_pattern_matching.py` | ✅ |
| 6 | Full suite, scope check, commit | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| New module tests | ✅ (40 passed) |
| Full suite (`pytest tests/`) | ✅ (2316 passed, 26 skipped, 187.9 s) |
| E2E checklist | ✅ (6/6) |
| Scope — exactly the planned paths | ✅ |
| `pattern_detector.py` diff additive only | ✅ (0 deletions) |
| Frontend lint | n/a — no frontend file touched |

### E2E checklist (from the plan)

| # | Check | Result |
|---|-------|--------|
| 1 | `tests/test_pattern_characterization.py` green and unmodified (STORY-001's pin) | ✅ |
| 2 | `tests/test_pattern_detector.py` green and byte-unmodified (layer 1) | ✅ |
| 3 | `tests/test_query_outcomes_regression.py` green, no assertion changed | ✅ |
| 4 | `tests/test_query_router.py` + `tests/test_integration.py` green, no assertion changed | ✅ |
| 5 | `tests/test_pii_redaction_integration.py` layers 1 and 2 green after Task 4 | ✅ |
| 6 | Full suite green | ✅ |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/pattern_detector.py` | UPDATE | +122 / −0 |
| `tests/test_pattern_matching.py` | CREATE | +343 |
| `tests/test_pii_dedup_isolation.py` | UPDATE | +29 / −41 |
| `.agents/plans/.../completed/STORY-002-....plan.md` | CREATE (archived) | +371 |

## Deviations from Plan

**1. The purity assertion could not be a raw-source substring check.** The plan's Task 5 sketched `assert "settings" not in inspect.getsource(pattern_detector)`. That fails against the module the plan itself asked for: the docstring says "no I/O, no settings, no pydantic" — the same phrasing `app/models/messages.py:1-9` uses — so the word appears in the source by design. `test_pattern_detector_stays_a_pure_module` instead asserts `"settings" not in vars(pattern_detector)` (the module's actual namespace), that the source contains no `open(` or `Path(`, and that no `import` line reaches into the `app` package. That is a stronger check than the one planned and does not break the moment someone documents the constraint they are honouring.

**2. `compile_pattern("", "regex")` is rejected too.** The plan specified the empty-pattern rejection for `word` mode only (where `"".split()` is `[]` and would build a bare `\b\b`). The empty *regex* compiles happily and matches at every position, which is the same hazard with a different mechanism — PRD threat T5 is about configuration that silently matches nothing; this is configuration that silently matches everything. Rejected, with its own test.

**3. Task 4 was larger than "edit the test".** `import subprocess` became unused once `_epic_base()` and `_changed_since_epic_base()` were deleted, so it went too. `pathlib` and `_REPO_ROOT` stayed — still used by the `hash_prompt` census at `tests/test_pii_dedup_isolation.py:390`. Verified before deleting.

Everything else matched the plan. The word formula, the regex arm and the nested-quantifier regex all behaved exactly as the plan's F-4 and F-5 predicted; no case needed adjusting after implementation.

### On the guard this story had to retire

This was the plan's F-1 and it is worth repeating in the record. `test_dedup_and_pattern_sources_unmodified_on_this_branch` asserted by `git diff` that `app/services/pattern_detector.py` was byte-unmodified since the merge-base with `main`. PRD-009 wrote it because PRD-009 never touched that module; PRD-011 rewrites it by design (PRD Section 6.8), so the guard would have failed on this story and on every remaining story in the epic.

It could not simply be deleted: `tests/test_pii_redaction_integration.py:424` censuses every pre-epic `def test_*` name and fails on a disappearance. So the **name was kept** and the body narrowed to the behavioural claim RF-6 actually makes — that pattern detection never grows a redaction dependency — in the shape `test_duplicate_checker_has_no_redaction_dependency` already uses for the sibling module. No `_DELIBERATELY_SUPERSEDED_TESTS` entry was needed. The comment above it cites PRD-011 and the decision, per PRD Section 11's quality indicator.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_pattern_matching.py` | `test_word_match_is_case_insensitive_and_suffix_safe` (7 params), `test_word_boundary_does_not_fix_at_override`, `test_phrase_matches_across_runs_of_whitespace` (6 params), `test_word_mode_escapes_metacharacters` (6 params), `test_word_mode_rejects_an_empty_or_whitespace_only_pattern`, `test_regex_mode_compiles_the_pattern_as_written_case_insensitively`, `test_regex_mode_raises_naming_the_pattern_and_the_re_error`, `test_regex_mode_rejects_an_empty_pattern`, `test_unknown_match_mode_raises_rather_than_returning_none`, `test_regex_mode_does_not_consult_the_redos_heuristic`, `test_has_nested_quantifier` (11 params), `test_the_heuristic_documents_itself_as_a_heuristic`, `test_pattern_detector_stays_a_pure_module`, `test_the_pre_prd_011_api_is_untouched_by_this_story` — **40 collected** |
| `tests/test_pii_dedup_isolation.py` | `test_dedup_and_pattern_sources_unmodified_on_this_branch` rewritten (name kept, body narrowed) |

## Notes for later stories

- **STORY-005** calls `compile_pattern` and `has_nested_quantifier` and owns both gates the primitives deliberately do not apply: `PATTERNS_ALLOW_REGEX`, and refusing a nested-quantifier pattern. It catches `PatternCompileError` and re-raises `PatternConfigError` with the list name attached. It must also validate `match` against the closed vocabulary — `compile_pattern` raises on an unknown mode, but that error names no list.
- **STORY-005 / R-5**: a pattern beginning or ending with a non-word character (`!important`) compiles to `\b!important\b`, whose leading `\b` demands a word character before the `!`. It silently narrows rather than failing. No AC covers it and the built-in list has no such pattern, but an operator-authored file can first contain one at STORY-005, and STORY-011's CSS corpus sample is the place it would surface.
- **STORY-008** deletes `detect_suspicious_pattern` and `SUSPICIOUS_PATTERNS`, and with them `test_the_pre_prd_011_api_is_untouched_by_this_story` in this suite, with a comment citing PRD Section 10 ("removed, not deprecated"). It also has to move `tests/test_pattern_detector.py` out of layer 1's `_PRE_EPIC_UNTOUCHED_TESTS`.
- **STORY-013** (README): the heuristic is a heuristic. `has_nested_quantifier`'s docstring, and the test that enforces its wording, are the record of what it does not catch — `(a|b)+` among them. The README must not upgrade it to a ReDoS guarantee.

## Acceptance Criteria

- [x] `compile_pattern(pattern, match="word")` on `override` matches `override` and `Override`, not `overrides` / `overridden` / `overriding`; **does** match `@Override`, asserted explicitly with a comment citing PRD Section 6.2 (`test_word_boundary_does_not_fix_at_override`)
- [x] `compile_pattern("ignore previous instructions", match="word")` matches `ignore\nprevious  instructions` and `Ignore Previous Instructions`; does not match `ignoreprevious instructions`
- [x] Regex metacharacters (`a.b`, `c+d`) are literal in word mode — tokens `re.escape`d before being joined with `\s+`
- [x] `compile_pattern(pattern, match="regex")` returns the pattern compiled with `re.IGNORECASE`; an uncompilable pattern raises `PatternCompileError` naming the pattern and the underlying `re.error` text
- [x] `has_nested_quantifier` returns `True` for `(a+)+`, `(\w*)*`, `(x+)*y` and `False` for `overrid\w*`, `ignore\s+previous`; the docstring states it is a heuristic for the common catastrophic shape, not a proof of linear-time matching (PRD 9.2 T4) — and a test enforces that wording
- [x] `app/services/pattern_detector.py` stays a pure module: no `settings`, no file I/O, nothing read at import (PRD Section 6.9)
- [x] `detect_suspicious_pattern` and `SUSPICIOUS_PATTERNS` unchanged; `tests/test_pattern_characterization.py` green and unmodified
- [x] All tasks completed
- [x] Full suite green (2316 passed, 26 skipped)
- [x] No assertion changed in `test_query_router.py`, `test_integration.py` or `test_query_outcomes_regression.py`
- [x] The one modified pre-existing test carries a comment citing PRD-011 and its decision
- [x] Follows existing patterns
