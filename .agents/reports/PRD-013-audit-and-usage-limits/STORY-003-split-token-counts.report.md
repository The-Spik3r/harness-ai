---
story: STORY-003
prd: PRD-013
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-003-split-token-counts.plan.md
epic_branch: epic/PRD-013-audit-and-usage-limits
commit: 9ede5a1
status: COMPLETE
completed: 2026-10-14
---

# Implementation Report — STORY-003: OpenRouter client returns input and output tokens separately

**Plan**: `.agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-003-split-token-counts.plan.md`
**Epic Branch**: `epic/PRD-013-audit-and-usage-limits`
**Commit**: `9ede5a1` (plan commit: `825a520`)

## Summary

`call_openrouter` now returns the provider's prompt and completion token counts next to the total. Nothing reads them yet: `run_conversation` passes them on in STORY-005.

- **Dataclass.** `OpenRouterResult` has `input_tokens: Optional[int] = None` and `output_tokens: Optional[int] = None` after `tokens_used`.
- **Parsing.** After `usage["total_tokens"]` is read exactly as before, `usage.get("prompt_tokens")` and `usage.get("completion_tokens")` go through `_token_count`. It keeps a non-negative `int` that is not a `bool` and returns `None` for anything else. It has no raising path.
- **`total_tokens` is unchanged.** It is still read strictly, still unvalidated, and never recomputed from the split.

**AC 5 was met, with one point about its wording.** The criterion describes the suite's stubs as building `OpenRouterResult` positionally. None does: all 64 construction sites in `tests/` and `scripts/` use the three keywords (plan F-2). They are unedited and pass. Positional construction is covered by two added tests: `test_three_positional_arguments_still_construct_a_result` and `test_the_split_fields_are_declared_last_and_in_order`.

No existing assertion changed in any file. `tests/test_audit_characterization.py` has no diff against `cbf8278`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Preflight: Docker Desktop and `harness-libsql-dev` started, branch confirmed, plan commit `825a520`, baseline taken | — | ✅ |
| 1 | `_token_count`; two fields on `OpenRouterResult`; two reads and two keywords in `call_openrouter` | `app/services/openrouter_client.py` | ✅ |
| 2 | PRD-013 STORY-003 test section, 23 cases | `tests/test_openrouter_client.py` | ✅ |
| 3 | Seven bite checks | — | ✅ |
| 4 | Full suite, diff checks, commit `9ede5a1` | — | ✅ |
| 5 | This report | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Frontend lint | N/A. The UI is Reflex (Python) and was not changed |
| Baseline full suite, before any change | ✅ 3391 passed, 27 skipped |
| `R('r','m',3)` repr after Task 1 | ✅ `OpenRouterResult(response='r', model_used='m', tokens_used=3, input_tokens=None, output_tokens=None)` |
| Client and characterization modules after Task 1, before new tests | ✅ 69 passed, the pre-change figure |
| `pytest tests/test_openrouter_client.py` | ✅ 53 passed (30 + 23) |
| `pytest tests/test_audit_characterization.py` | ✅ 39 passed; no diff against `cbf8278` |
| Full suite | ✅ 3414 passed, 27 skipped, the baseline plus 23, with no failure in one run |
| Frozen files (`test_query_outcomes_regression`, `test_chat_outcomes_regression`, `test_duplicate_scope`, `test_pii_characterization`) | ✅ no diff against `main` |
| E2E | ✅ 7/7 |

## E2E Results

Run against the local libSQL dev server with a dummy OpenRouter key and a throwaway admin token, both set as environment variables over `.env`. The script asserted that `DATABASE_URL` was `http://127.0.0.1:8080` and `TURSO_AUTH_TOKEN` was empty before doing anything. The client's `_API_URL` was pointed at a local fake upstream returning `usage = {prompt_tokens: 120, completion_tokens: 30, total_tokens: 150}`, so no request left the machine.

| # | Check | Result |
|---|-------|--------|
| 1 | `pytest tests/test_openrouter_client.py` | ✅ 53 passed |
| 2 | `pytest tests/test_audit_characterization.py` and its diff against `cbf8278` | ✅ 39 passed; empty diff |
| 3 | `python -c "from app.main import app"` | ✅ |
| 4 | The client by hand against the fake upstream | ✅ `input_tokens=120, output_tokens=30, tokens_used=150` |
| 5 | The API (`uvicorn`, real lifespan) with one `POST /query` as a `user`-role account | ✅ `GET /health` 200. `/query` 200 `SUCCESS` with `tokens_used: 150` and the same keys as before the story (no split in the body). The fake upstream received the dummy key. The audit row has `success=True`, `tokens_used=150`, and `input_tokens` and `output_tokens` still `NULL`, as expected until STORY-005 |
| 6 | Bite checks | ✅ 7/7 (below) |
| 7 | Full suite equals baseline plus 23 | ✅ 3414 |

## Bite checks (Task 3)

Each was a temporary edit applied by a script that restored the file in a `finally` block. The file's SHA-1 was identical before and after, and `git status` afterwards showed only the two story files.

| # | Temporary change | Tests that failed |
|---|---|---|
| 1 | Swap `"prompt_tokens"` and `"completion_tokens"` | the AC 1 test and all 16 cases of the two AC 3 tables (17) |
| 2 | Drop `isinstance(value, bool) or` | `true` and `false` in both AC 3 tables (4) |
| 3 | Drop `or value < 0` | `negative` in both AC 3 tables (2) |
| 4 | `0` becomes `None` (`if not value or ...`) | `test_a_zero_count_is_kept_as_zero` (1) |
| 5 | `usage["prompt_tokens"]` instead of `.get` | the AC 2 test, the characterization module's `total-only` case, and 11 older client tests whose `_response()` body has no split (13) |
| 6 | Swap the two new declarations | `test_the_split_fields_are_declared_last_and_in_order` (1) |
| 7 | Both new fields `kw_only=True` and moved above `tokens_used` | `test_the_split_fields_are_declared_last_and_in_order` (1) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/openrouter_client.py` | UPDATE | +25/-2 |
| `tests/test_openrouter_client.py` | UPDATE | +93/-0 |
| `.agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-003-split-token-counts.plan.md` | MOVE (archived) | 0 |
| `.agents/reports/PRD-013-audit-and-usage-limits/STORY-003-split-token-counts.report.md` | CREATE | this file |

## Deviations from Plan

1. **Docker Desktop was not running at preflight.** It was started from `C:\Users\tobip\AppData\Local\Programs\DockerDesktop`, and the container came up before the baseline.
2. **The plan commit was amended once, before anything else was built on it,** to add the `Story:` and `PRD:` trailers its precedent `d43055f` carries. Final SHA `825a520`.
3. **E2E 5 needed an active user.** The API refused to start because the dev database had none (`RbacNotBootstrappedError`, the RBAC startup guard). A throwaway account, `e2e-story003`, was created with `scripts/manage_users.py create-user --user-id e2e-story003 --role user` in the local dev database only, and the `/query` was sent with its token rather than `ADMIN_TOKEN`. The account remains in the dev container.
4. **E2E 5 used a local fake upstream instead of an unreachable one.** This made the check stronger: the real client parsed a real HTTP response carrying the split, through the real API, and nothing was sent to openrouter.ai.
5. **Bite check 5 failed more tests than the plan named.** Eleven older client tests build a body with `total_tokens` only, so indexing `prompt_tokens` breaks them too. Every test the plan named did fail.
6. **The frozen-file check compared the working tree with the merge base,** which is stricter than the plan's `..HEAD` form. It was empty.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_openrouter_client.py` | `test_split_is_returned_beside_the_total`; `test_total_only_succeeds_with_no_split`; `test_an_unusable_prompt_count_is_none_and_the_call_succeeds` ×8 (`string`, `negative`, `true`, `false`, `float`, `null`, `list`, `object`); `test_an_unusable_completion_count_is_none_and_the_call_succeeds` ×8 (same ids); `test_a_zero_count_is_kept_as_zero`; `test_the_split_is_reported_as_given_when_it_disagrees_with_the_total`; `test_a_split_without_a_total_still_raises`; `test_three_positional_arguments_still_construct_a_result`; `test_the_split_fields_are_declared_last_and_in_order` |

## For later stories

- **STORY-005**: `result.input_tokens` and `result.output_tokens` are ready to pass to `log_query` on the success and output-redaction-error arms. Stubs that build the result with three fields give `None` for both, which is why `_UNSET_THROUGH_DRIVE` in the characterization module still holds. E2E 5 shows the gap: the client returned 120/30 and the row recorded `NULL`/`NULL`.
- **STORY-010 and STORY-012**: the two fields are judged independently, so one can be `None` while the other is set (plan D-2). `charge` must decide whether a half split counts as "the split is present". The split is also not reconciled with `tokens_used` (plan D-3): `100 + 100` beside a total of `45` is returned as given.

## Observations (recorded, not fixed)

- **`"usage": null` and any other non-object `usage` still raise an uncaught `TypeError`.** The `except` clause covers `KeyError`, `IndexError` and `ValueError` only. STORY-001's report left this story free to wrap it. It was left alone because AC 4 requires the missing-total behaviour to stay exactly as before (plan F-3).
- **`total_tokens` is returned unvalidated,** so a string or `null` total reaches the caller as `tokens_used` (plan F-3).
- **`scripts/spike_pii_placeholders.py:622` rebuilds a result with three keywords,** which drops the split. It is a spike script on no production path.

## Acceptance Criteria

- [x] Given a provider response whose `usage` has `prompt_tokens=120`, `completion_tokens=30`, `total_tokens=150`, when `call_openrouter` returns, then `OpenRouterResult` has `input_tokens=120`, `output_tokens=30` and `tokens_used=150`.
- [x] Given a response whose `usage` has only `total_tokens`, when `call_openrouter` returns, then it succeeds with `input_tokens=None` and `output_tokens=None`.
- [x] Given `prompt_tokens` that is a string, a negative number or a `bool`, when `call_openrouter` returns, then that field is `None` and no error is raised. The same holds for `completion_tokens`, and for floats, `null`, lists and objects.
- [x] Given a response with no `total_tokens`, when `call_openrouter` runs, then it raises `OpenRouterError` exactly as before. STORY-001's assertions are unchanged and pass.
- [x] Given the existing suite's stubs, when the suite runs, then every one still constructs and passes. **They use keywords, not positions;** positional construction is covered by two added tests.
- [x] All tasks completed
- [x] Backend imports and the server starts without error
- [x] Follows existing patterns
