---
story: STORY-001
prd: PRD-009
plan: .agents/plans/PRD-009-duplicate-rescoping/completed/STORY-001-characterization-and-outcome-baseline.plan.md
epic_branch: epic/PRD-009-duplicate-rescoping
commit: 9abef61
status: COMPLETE
completed: 2026-09-16
---

# Implementation Report — STORY-001: Characterization tests of today's duplicate lookup and the six-outcome /query baseline

**Plan**: `.agents/plans/PRD-009-duplicate-rescoping/completed/STORY-001-characterization-and-outcome-baseline.plan.md`
**Epic Branch**: `epic/PRD-009-duplicate-rescoping` (created from `main` @ `57f2d67`)
**Commit**: `9abef61`

## Summary

This story adds two test-only modules. Nothing under `app/` and no existing test file was changed. `tests/test_duplicate_characterization.py` pins five pre-PRD-009 behaviours of the global `prompt_hash` duplicate lookup, each observed through `POST /query`. Each test names the story expected to flip it. `tests/test_query_outcomes_regression.py` pins the six `/query` outcomes of PRD-009 Section 11 (status code, body, audit-row count). Its inputs were chosen so that it stays green through the whole epic without edits.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Create epic branch from `main` | git | ✅ |
| 1 | Start libSQL dev server, record baseline | — | ✅ (1850 passed, 25 skipped; see Findings) |
| 2 | Scaffold characterization module (two users, helpers) | `tests/test_duplicate_characterization.py` | ✅ |
| 3 | `OpenRouterError` row blocks retry | `tests/test_duplicate_characterization.py` | ✅ |
| 4 | Input `PiiRedactorError` row blocks retry | `tests/test_duplicate_characterization.py` | ✅ |
| 5 | Policy-denial row blocks allowed resend (D1) | `tests/test_duplicate_characterization.py` | ✅ |
| 6 | User A's row blocks user B (T2) | `tests/test_duplicate_characterization.py` | ✅ |
| 7 | Duplicate-blocked row chains the window (D3, PRD 6.4) | `tests/test_duplicate_characterization.py` | ✅ |
| 8 | Six-outcome regression (7 tests) | `tests/test_query_outcomes_regression.py` | ✅ |
| 9 | Only the two new files changed | git | ✅ |
| 10 | Full suite green | — | ✅ (1862 passed, 25 skipped) |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A: the repo has no npm frontend; `chat_ui/` (Reflex) untouched |
| API health (`uvicorn app.main:app` + `GET /health`) | ✅ 200 `{"status":"ok"}` |
| New modules | ✅ 12 passed |
| Full suite (`PYTHONUTF8=1 pytest tests/`) | ✅ 1862 passed, 25 skipped (baseline 1850 + 12) |
| `git diff --stat main -- app/ tests/` (tracked) | ✅ empty |
| E2E | ✅ 4/4 |

### E2E checklist

- [x] Characterization module: 5 passed. Every name contains `pre_prd009`. Docstrings name STORY-004 (4 tests) or STORY-005 (cross-user).
- [x] Regression module: 7 passed (outcomes 1–5, 6 redactor, 6 storage).
- [x] Mutation check, reverted and never committed: adding `AND success = 1` to `find_duplicate_timestamp` turned exactly the OpenRouter and input-redactor characterization tests red (2 failed, 10 passed). Outcome 2 stayed green. After `git checkout -- app/db/database.py`, `git diff -- app/` was empty and the modules passed 12/12 again.
- [x] Full suite green.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_duplicate_characterization.py` | CREATE | +300 |
| `tests/test_query_outcomes_regression.py` | CREATE | +211 |
| `.agents/PRDs/PRD-009-duplicate-rescoping/PRD.md`, `.agents/stories/PRD-009-duplicate-rescoping/*` | ADD (previously untracked PRD-009 planning docs) | — |
| `.agents/plans/PRD-009-duplicate-rescoping/completed/STORY-001-….plan.md` | ADD (archived plan) | — |

## Deviations from Plan

1. **Outcome 4 asserts the full body.** The plan named `status`, `required_permission` and `reason`; the test compares the whole response dict, which covers those three and also catches an extra field appearing. It is stricter, and not a change in meaning.
2. **Outcomes 5 and 6 (redactor) assert the full `{"detail": …}` body** rather than individual keys, for the same reason.
3. **Suite run under `PYTHONUTF8=1`** (see Findings). The plan's commands did not set it.
4. **`pre-prds/` not committed.** It holds the PRE-PRD-009…016 track, which this story did not produce. It stays untracked for whoever owns that track. The PRD's Appendix links to `pre-prds/PRE-PRD-009-…` and will not resolve on the branch until it is committed.

## Findings (environment; no code changed)

- **`.venv` was missing `python-frontmatter`**, which `requirements.txt` pins and `app/services/reports.py` (from the `/reports` merge) imports. Three `test_reports_*` modules failed to collect. Fixed with `pip install -r requirements.txt`.
- **`tests/test_pii_redaction_integration.py::test_no_pre_epic_test_function_was_removed_or_renamed` fails on Windows with the default locale.** This was already true on `main`. Its `_git()` helper runs `subprocess.run(..., text=True)`, which decodes as cp1252. `tests/reports_fixture.py` contains UTF-8 (`—`, `✓`), so the reader thread raises and `stdout` comes back `None`. It passes under `PYTHONUTF8=1`. Not fixed here, because the story forbids modifying pre-existing tests. A follow-up could pass `encoding="utf-8"` in that helper.
- The libSQL dev container `harness-libsql-dev` had exited. Docker Desktop was started and the container restarted, with no fixture degradation.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_duplicate_characterization.py` | `test_pre_prd009_openrouter_failure_row_blocks_same_prompt_retry` (→ STORY-004); `test_pre_prd009_input_redactor_failure_row_blocks_same_prompt_retry` (→ STORY-004); `test_pre_prd009_policy_denial_row_blocks_same_user_resend_with_allowed_model` (D1 → STORY-004); `test_pre_prd009_row_from_one_user_blocks_same_prompt_from_another_user` (→ STORY-005); `test_pre_prd009_duplicate_blocked_row_keeps_window_alive_after_original_ages_out` (D3 → STORY-004) |
| `tests/test_query_outcomes_regression.py` | `test_outcome_1_success`; `test_outcome_2_duplicate_block_after_same_user_success`; `test_outcome_3_suspicious_pattern_block`; `test_outcome_4_policy_refusal`; `test_outcome_5_upstream_failure`; `test_outcome_6_internal_failure_redactor`; `test_outcome_6_internal_failure_duplicate_storage` |

## Acceptance Criteria

- [x] New `tests/test_duplicate_characterization.py`, no change under `app/`, passes on `main` and pins each of the five behaviours with one test apiece through `POST /query`
- [x] Each characterization test's name states it pins pre-PRD-009 behaviour, and its docstring names the decision or story that flips it (D1/D3 → STORY-004, cross-user → STORY-005)
- [x] `tests/test_query_outcomes_regression.py` pins the six outcomes through `POST /query` (status, body, audit-row count), with outcome 6 in both forms. Redactor: 1 row. Duplicate storage: 0 rows. The existing test asserts no count because the table is dropped; here the 0 is asserted through a `log_query` spy.
- [x] Outcome 2's prior is a same-user, successful send
- [x] Full suite passes; no pre-existing test file modified
- [x] All tasks completed
- [x] No `app/` change
- [x] Follows existing patterns (`tests/test_query_router.py`, `tests/test_pii_dedup_isolation.py`, `tests/test_rbac.py`)
