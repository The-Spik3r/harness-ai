---
story: STORY-008
prd: PRD-015
plan: .agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-008-code-profile-assistant-flag.plan.md
epic_branch: epic/PRD-015-openai-compatible-endpoint
commit: 4ed6379
status: COMPLETE
completed: 2026-10-23
---

# Implementation Report — STORY-008: code profile flags assistant turns; examples/patterns.yaml matches again

**Plan**: `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-008-code-profile-assistant-flag.plan.md`
**Epic Branch**: `epic/PRD-015-openai-compatible-endpoint`
**Commit**: `4ed6379`

## Summary

The built-in `code` profile's roles are now `{"user": "block", "assistant": "flag", "tool": "flag"}`, in that declared order (PRD-015 Section 7.8, D9). `chat` is unchanged, and `code` still loads only `injection`. `examples/patterns.yaml` has the same cell, so it equals `BUILT_IN_POLICY` again. Three comments state D9:

- the comment above `code` in `_build_built_in()`
- the last paragraph of the `Profile` docstring
- the flag-arm comment in `run_conversation`, which no longer says "Unreachable from any ingress today". It now says that `/v1` reaches the `assistant` cell once STORY-009 mounts it, and that the `tool` cell stays unreachable until PRD-016.

There is no pipeline logic change.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Change the tests first (red: exactly the 3 predicted failures) | `tests/test_pattern_profiles.py`, `tests/test_pattern_config.py` | ✅ |
| 2 | Built-in `assistant: flag` cell, D9 comment, `Profile` docstring. The sample-file test then failed, as the drift guard should | `app/services/pattern_config.py` | ✅ |
| 3 | Sample file gains `assistant: flag` between `user` and `tool`. The sample test passes with no edit | `examples/patterns.yaml` | ✅ |
| 4 | Flag-arm comment (comment-only diff) | `app/services/query_pipeline.py` | ✅ |
| 5 | Three pipeline tests for AC 3 / AC 4 | `tests/test_query_pipeline_patterns.py` | ✅ |
| 6 | Corpora and default-config regression run unedited | (none edited) | ✅ |
| 7 | Full suite | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Frontend lint | N/A (no frontend change) |
| Targeted pattern/corpus/regression/PII-profile files | ✅ 330 passed |
| Full suite (throwaway libSQL on `:8086`, keep-awake wrapper) | ✅ 4,654 passed / 27 skipped in 292 s. That is STORY-007's 4,651 + 3 new tests, with no failures and no flakes |
| Mutation check: `assistant` cell removed from `_build_built_in()` | ✅ `test_assistant_injection_under_code_flags_and_is_answered` fails; restored |
| E2E | ✅ 2/2 |

### E2E

1. **Boot with the sample file.** uvicorn was started with `PATTERNS_FILE=examples/patterns.yaml` against a second throwaway libSQL (`:8087`, `init_db()` + `create-user` first). `Application startup complete`, and `GET /health` returned `{"status":"ok"}` 200. Startup does not log the pattern source, so the real `load()` was also called in a separate process. Result: `policy is not BUILT_IN_POLICY` (the file was read), `policy == BUILT_IN_POLICY`, code roles `[('user','block'), ('assistant','flag'), ('tool','flag')]`, lists `['injection']`, chat roles `{'user': 'block'}`.
2. **Boot with `PATTERNS_FILE` unset.** `/query` verdicts are unchanged: `tests/test_pattern_default_config_regression.py` passes unedited, both inside the full run and in the targeted run.

An HTTP-level check of `pattern_role='assistant'` is not possible yet, because `/v1` is mounted in STORY-009. AC 3 is verified at pipeline level against real libSQL, through the real step 0, `dedup_key`, built-in profile and audit writer.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/pattern_config.py` | UPDATE | +14/-4 |
| `app/services/query_pipeline.py` | UPDATE (comment only) | +4/-2 |
| `examples/patterns.yaml` | UPDATE | +1 |
| `tests/test_pattern_config.py` | UPDATE | +1/-1 |
| `tests/test_pattern_profiles.py` | UPDATE | +10/-3 |
| `tests/test_query_pipeline_patterns.py` | UPDATE | +94 |

## Deviations from Plan

- **Module docstring.** I also extended the module docstring of `tests/test_query_pipeline_patterns.py` with a PRD-015 STORY-008 paragraph, because that docstring lists each story's scope. Not in the plan; documentation only.
- **Line endings.** The tests were appended with a bash heredoc, which left the file with mixed line endings. It was normalized back to CRLF in binary mode before running anything.
- **Mutation check.** The plan did not include one. Pointing `PATTERNS_FILE` at a copy without the cell proved nothing, because tests never call `load()`. The cell was therefore removed from the code temporarily instead, and restored.

Otherwise the implementation matched the plan.

## AC 5: corpus and regression expectations changed

**None.** Five files were run, and no expectation changed:

- `tests/test_pattern_corpus.py`
- `tests/test_pattern_default_config_regression.py`
- `tests/test_pattern_detector.py`
- `tests/test_pattern_characterization.py`
- `tests/test_query_pipeline_pii_profiles.py`

This matches the plan's prediction: the corpus never puts an `assistant` turn under `code`, the regression runs `chat`, and every injection phrase in the `code` PII-profile tests sits in a `user` turn.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_query_pipeline_patterns.py` | `test_assistant_injection_under_code_flags_and_is_answered` (AC 3), `test_assistant_injection_under_chat_is_not_inspected` (AC 4), `test_assistant_keyword_under_code_does_not_flag` (AC 4, PRD Risk 8) |
| `tests/test_pattern_profiles.py` | `test_built_in_matrix_cell[code-assistant-flag]` (updated cell); `test_the_matrix_has_no_cells_beyond_section_6_4` (exact map + new declared-order assertion) |
| `tests/test_pattern_config.py` | `test_the_built_in_profiles_carry_the_section_6_4_matrix` (updated map) |

## Handoff to STORY-019 (README)

The README now understates `code`. Per this story, README wording belongs to STORY-019:

- `README.md` ~233-235: the role bullets have no `assistant` bullet.
- ~237: "In this release the flag is reachable by tests only". `assistant` becomes reachable from `/v1` once STORY-009 lands.
- ~270-275: the yaml block of the sample policy is missing `assistant: flag`.

## Acceptance Criteria

- [x] Given `BUILT_IN_POLICY`, when the `code` profile is read, then `roles == {"user": "block", "assistant": "flag", "tool": "flag"}` in that declared order and `lists` is still only `injection`; `chat` is unchanged.
- [x] Given `examples/patterns.yaml`, when it is loaded, then it equals `BUILT_IN_POLICY` (the existing equality test, with its expectation updated and nothing else).
- [x] Given `run_conversation(profile="code")` with `ignore previous instructions` in an `assistant` turn and a clean last `user` turn, when it runs, then the request is answered and writes a flag row with `pattern_role='assistant'`, `pattern_action='flag'`, followed by the success row.
- [x] Given the same conversation under `chat`, and an `assistant` turn containing `override` (a `keywords` entry not loaded by `code`) under `code`, when each runs, then neither writes a flag row.
- [x] Given the PRD-011 corpora (`tests/test_pattern_corpus.py`) and the default-config regression, when they run, then any change in their results is only the new `assistant` flag cell, and each changed expectation is listed in the story report. (None changed; see above.)
