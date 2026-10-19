---
story: STORY-010
prd: PRD-013
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-010-usage-limits-service.plan.md
epic_branch: epic/PRD-013-audit-and-usage-limits
commit: 3570281
status: COMPLETE
completed: 2026-10-19
---

# Implementation Report — STORY-010: usage_limits: limit resolution and the rate and budget checks

**Plan**: `.agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-010-usage-limits-service.plan.md`
**Epic Branch**: `epic/PRD-013-audit-and-usage-limits`
**Commit**: `3570281`

## Summary

`app/services/usage_limits.py` is the decision layer over the STORY-007 settings maps, the STORY-008 `Identity` overrides and the STORY-009 statements. It has four parts:

- **`limits_for(identity) -> UsageLimits`** resolves each limit independently: the per-user override, else the role's entry, else `*`. The role lookup is a membership test, so an explicit `admin=unlimited` (`None`) wins over `*` instead of falling through to it. Settings are read per call. The break-glass identity resolves through `admin` with no special case.
- **`admit(identity, charges_budget) -> Admission`** makes one `admit_usage()` call. It checks the rate first (strict `>`), then the budget (`>=`), but the budget only if the rate passed and `charges_budget` is true. Only one limit is reported. `Admission` always carries the counted `day`. It holds any refusal in a nested frozen `UsageRefusal(limit, maximum, actual, resets_at)`, which is `None` when the attempt is admitted. `resets_at` is derived only from the `window_start`/`day` the database returned. `StorageError` becomes `UsageLimitError` (fail closed, T7).
- **`charge(user_id, day, input_tokens, output_tokens, total_tokens)`** charges the split when both halves are present, otherwise it charges `total_tokens` to `unsplit_tokens` (F11). It fails open (T8): a `StorageError`, or a charge that matched no row, is logged at `ERROR` with the user id, the day and the counts, and the call returns.
- **`UsageLimitError`** is the named exception that STORY-011 maps to `500`.

The module does not read `USAGE_LIMITS_ENABLED`, and nothing on the request path imports it yet (STORY-011/012).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Types, `UsageLimitError`, `limits_for` | `app/services/usage_limits.py` | ✅ |
| 2 | `admit` + `resets_at` helpers | `app/services/usage_limits.py` | ✅ |
| 3 | `charge` | `app/services/usage_limits.py` | ✅ |
| 4 | Unit tests, stubbed storage | `tests/test_usage_limits.py` | ✅ |
| 5 | Real-database wiring test | `tests/test_usage_limits.py` | ✅ |
| 6 | Full suite | — | ✅ (one unrelated flake, see below) |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A — no frontend in this repo, and no UI change in this story |
| `pytest tests/test_usage_limits.py tests/test_usage_storage.py -v` | ✅ 47 passed |
| `pytest tests/ -q` | ✅ 3608 passed, 27 skipped, 1 error (unrelated flake, see below) |
| E2E | ✅ 4/4 |

**Environment.** CPython 3.11.17 in a fresh uv venv at `C:\Users\tobip\AppData\Local\Temp\hai-venv` built from `requirements.txt`, plus `en_core_web_lg` and `en_core_web_sm` 3.8.0. The libSQL server was `harness-libsql-dev` at `http://127.0.0.1:8080`. A first venv under the session scratchpad could not import presidio because its deepest file path (295 characters) went over Windows' 260-character limit, so the venv was rebuilt at the short path. Without `en_core_web_sm`, 35 PII and `test_main` tests failed because presidio tried to download it with `uv pip`. Installing it made all 173 tests in those four files pass. Both were environment problems, not code problems.

**The one error.** `tests/test_chat_sessions.py::test_touch_moves_updated_at_and_returns_true` errored in fixture setup on the first clean full run. That file passed 128/128 on three reruns. It does not import `usage_limits`. This is the shared-database isolation flake that `pre-prds/PRE-PRD-017-test-suite-db-isolation.md` describes.

### E2E

- [x] `pytest tests/test_usage_limits.py -v`: 34/34 passed
- [x] The real-DB test passes against the libsql endpoint (admit → charge split → charge unsplit → read-back → budget refusal at exactly 16)
- [x] `python -c "from app.services.usage_limits import admit, charge, limits_for, UsageLimitError, Admission, UsageLimits"`: OK
- [x] `uvicorn app.main:app --port 8000` started; `GET /health` → `200 {"status":"ok"}`

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/usage_limits.py` | CREATE | +238 |
| `tests/test_usage_limits.py` | CREATE | +445 |

## Deviations from Plan

1. **Boundary test tightened.** The plan said to assert that `"USAGE_LIMITS_ENABLED"` does not appear in the module source. The module docstring names the switch in order to say the module does not read it, so the test now asserts that `settings.USAGE_LIMITS_ENABLED` is never read.
2. **Extra tests beyond the plan:** a year-end `resets_at` case, a per-user counting case, a rate-limit case with `charges_budget=False`, a test that a successful charge logs nothing, a test that a non-`StorageError` exception propagates out of `charge`, and a test that the module never reads the instance clock (`datetime.now`/`utcnow`).
3. **Real-DB test guard.** The final budget-refusal assertion is skipped if the second `admit` lands on a new UTC day, so the test cannot flake at midnight. Nothing else depends on the clock.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_usage_limits.py` | 34. **limits_for** (8): override + role, budget override, role entry, `*` fallback, independent fallback, unlimited role beats `*`, break-glass via `admin`, per-call read. **Rate** (3): 4th of 3 refused with an exact `resets_at`, per-user counting, override. **Budget** (7): at/above (parametrized), month-end, year-end, below, BYOK skip, BYOK still rate-limited. **Precedence and unlimited** (3). **Failure rules** (5): admit fails closed with `__cause__`; charge fails open with exactly one `ERROR` record carrying user/day/counts; no-row `ERROR`; silent on success; non-storage error propagates. **F11 routing** (4): split, no split, half split ×2. **Shape and boundary** (3): frozen dataclasses, no master-switch read, no instance clock. **Real storage** (1) |

## Acceptance Criteria

- [x] Given an identity with a per-user override, with only a role entry, and with a role that has no entry, when `limits_for(identity)` is called, then it returns the override, the role's value and the `*` value respectively, resolved independently for the budget and the rate.
- [x] Given a rate limit of 3, when `admit` is called four times in one minute, then the first three are admitted and the fourth is refused with `limit="requests"`, `maximum=3`, `actual=4` and `resets_at` equal to the end of the current minute in the audit timestamp format.
- [x] Given `tokens_today` at or above the budget and `charges_budget=True`, when `admit` is called, then it is refused with `limit="tokens"` and `resets_at` at the next 00:00 UTC; with `charges_budget=False` it is admitted.
- [x] Given both limits broken, when `admit` is called, then `limit="requests"` is the one reported; given a limit of `unlimited`, then that check never refuses.
- [x] Given `admit_usage` raising `StorageError`, when `admit` is called, then it raises `UsageLimitError`; given `charge_usage` raising `StorageError`, when `charge` is called, then it logs at `ERROR` with the user id, day and counts, and returns without raising.
