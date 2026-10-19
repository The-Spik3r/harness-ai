---
story: STORY-012
prd: PRD-013
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-012-charge-after-upstream.plan.md
epic_branch: epic/PRD-013-audit-and-usage-limits
commit: 01c415d
status: COMPLETE
completed: 2026-10-19
---

# Implementation Report — STORY-012: Charge tokens after the upstream call; BYOK and counter-failure rules

**Plan**: `.agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-012-charge-after-upstream.plan.md`
**Epic Branch**: `epic/PRD-013-audit-and-usage-limits`
**Commit**: `01c415d`

## Summary

`run_conversation` now has step 7b, the charge. It is one `charge(user_id, admission.day, input_tokens, output_tokens, tokens_used)` call, placed right after step 7's `except OpenRouterError` arm and before step 8's output redaction. It is called through `query_pipeline`'s own `charge` binding, so tests can spy on it.

- **Which arms are charged:** the success arm and the output-redaction-error arm. The upstream-error arm re-raises before step 7b, so it is never charged.
- **When it runs:** only when `admission is not None` (the gate ran, because `USAGE_LIMITS_ENABLED` was on at step 2c) and `openrouter_api_key is None` (not BYOK, D8). It reads `admission`, not the setting, so a request is charged by the rule it was admitted under.
- **Which day:** the `day` the gate returned, so a request that straddles midnight is charged to the day it was admitted.
- **Failure:** fails open (T8). STORY-010's `charge()` already logs a `StorageError` at `ERROR` with the user, day and counts and returns. There is no extra wrapper, so non-storage errors still surface.
- **Unsplit responses:** `charge()` sends `tokens_used` to `unsplit_tokens`, which counts toward the budget.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Bind `charge` by name into the pipeline; extend the binding comment | `app/services/query_pipeline.py` | ✅ |
| 2 | Step 7b call site; step 2c forward references to STORY-012 now point at step 7b | `app/services/query_pipeline.py` | ✅ |
| 3 | 13 tests for the charge (AC 1-5, order, admitted day, switch, overshoot); docstring, helpers, `charge_calls` fixture | `tests/test_query_pipeline_usage_limits.py` | ✅ |
| 4 | Round-trip guard raised from 4 to 5 statements (`UPDATE usage_daily` at index 3); printed label updated | `tests/test_two_instance_smoke.py` | ✅ |
| 5 | Mutation check (3 mutations, restored after each) | — | ✅ |
| 6 | Full-suite sweep | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| `py_compile app/services/query_pipeline.py` | ✅ |
| Frontend lint | N/A. There is no npm frontend (the UI is Reflex) and no Python linter is configured. |
| `GET /health` on the dev server | ✅ `{"status":"ok"}` |
| `tests/test_query_pipeline_usage_limits.py` | ✅ 37 passed (24 existing + 13 new) |
| `tests/test_two_instance_smoke.py -k round_trip` | ✅ 1 passed. It now reports "5 statements (identity read, usage gate, duplicate check, usage charge, audit write)". |
| Full suite | ✅ 3658 passed, 27 skipped, 1 error. The error is a fixture-setup failure in `test_chat_sessions.py::test_rename_returns_true_when_owned_and_false_otherwise`: libSQL `STREAM_EXPIRED` ("The stream has expired due to inactivity"). This is the known shared-DB flake (PRE-PRD-017). The file passes 128/128 on rerun. |
| Mutation check | Charge moved after step 8: 2 tests fail (output-redaction charge, order). BYOK guard dropped: 2 fail (both BYOK tests). Literal wrong day: 8 fail. All green after each restore, and the diff was verified to be only the intended change. |
| E2E | ✅ 3/3 (below) |

### E2E

Ran `uvicorn app.main:app --port 8765` against the dev libSQL with `OPENROUTER_API_KEY` set to a placeholder, so nothing was spent. Users were created with `manage_users.py create-user`.

1. **Upstream error charges nothing.** `POST /query` returned `502`. The outbound call fails TLS verification on this machine (`CERTIFICATE_VERIFY_FAILED`), which still exercises the upstream-error arm. The `usage_daily` row afterwards: `requests=1, input_tokens=0, output_tokens=0, unsplit_tokens=0`. ✅
2. **Success charges the row.** A real paid call was not possible: every outbound OpenRouter call fails TLS on this machine, as step 1 shows. As a stand-in, one `POST /query` ran in-process through the real router and app against the same dev database, with only `app.routers.query.call_openrouter` replaced by a stub reporting 120 in / 30 out / 150 total. Result: `200 SUCCESS`. The row went from `requests=1, 0/0/0` to `requests=2, 120/30/0`. `GET /audit` showed that row with `input_tokens=120, output_tokens=30, ingress="query"`. ✅
3. **Limits off.** The server was restarted with `USAGE_LIMITS_ENABLED=false` and a second user. `POST /query` returned `502` (same TLS failure), and that user has no `usage_daily` row. ✅

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/query_pipeline.py` | UPDATE | +32/-5 |
| `tests/test_query_pipeline_usage_limits.py` | UPDATE | +312/-4 |
| `tests/test_two_instance_smoke.py` | UPDATE | +9/-2 |

## Deviations from Plan

1. **E2E 2 used an in-process stand-in, not a real paid call.** The plan allowed falling back to the automated tests when a real key could not be used. Here the network blocks every outbound OpenRouter call at TLS, so no real call was possible either way. The stand-in goes further than the automated tests: it uses the real router, the dev database and `/audit`.
2. **The smoke test's printed label was also updated** ("usage charge" added). The plan named only the assertions. Without the change, the printed label would have listed four names for five statements.
3. **One extra helper, `_seed_today`.** The plan used the outcome-8 seeding SQL in two tests (BYOK and overshoot). It is factored into one helper rather than written out twice.
4. **No other guards tripped.** The plan's Task 6 risk (`_returns`-stubbed success tests now log one `ERROR` "matched no row") produced no failures. No test asserts zero `ERROR` records from `app.services.usage_limits` on the pipeline path.
5. **Plan-commit hygiene.** The unrelated uncommitted docs (`pre-prds/README.md`, `pre-prds/PRE-PRD-017-test-suite-db-isolation.md`) were left unstaged and untouched, as the user chose.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_query_pipeline_usage_limits.py` | split charged to the admitted day (real storage); a later admission sees `tokens_today` +150; output-redaction failure still charged, with a `success=0` row carrying the tokens; upstream error charges nothing (row exists at 0/0/0); order `upstream → charge → redact_output`; unsplit response → `unsplit_tokens`; unsplit tokens trip the budget (`actual=150`); BYOK consumes one unit with the budget spent, charges nothing, and the row records 120/30; harness key charged and BYOK not (spy); `charge_usage` `StorageError` → success, matching success row, one `ERROR` line naming user, day, counts and error; charge goes to the gate's `day` (`_DAY`, not today); limits off → no charge and no row; two requests admitted at 999/1000 both complete, the day ends at 1299, and the next is refused for `tokens` |
| `tests/test_two_instance_smoke.py` | `test_round_trip_cost_is_measured_and_reported`: five statements, asserted by name |

## Acceptance Criteria

- [x] Given a successful request reporting 120 input and 30 output tokens, when it completes, then the user's `usage_daily` row for the admitted day has those amounts added, and a later request sees `tokens_today` increased by 150.
- [x] Given an output-redaction failure after the provider answered, when the request fails, then the tokens are still charged; given an upstream error, then nothing is charged.
- [x] Given a provider response with no split, when the request completes, then `tokens_used` is charged to `unsplit_tokens` and counts toward the budget.
- [x] Given a BYOK request (`openrouter_api_key` supplied), when it completes, then it consumed one unit of the rate window, was not refused for budget even with the budget exhausted, and charged nothing, while its audit row still records the tokens.
- [x] Given `charge_usage` raising `StorageError` after a successful upstream call, when the request completes, then the caller receives the normal success response, the success audit row is written, and one `ERROR` log line names the user, day and counts.
