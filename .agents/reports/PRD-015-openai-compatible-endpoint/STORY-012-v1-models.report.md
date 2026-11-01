---
story: STORY-012
prd: PRD-015
plan: .agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-012-v1-models.plan.md
epic_branch: epic/PRD-015-openai-compatible-endpoint
commit: 799df1d
status: COMPLETE
completed: 2026-10-25
---

# Implementation Report — STORY-012: GET /v1/models and /v1/models/{id} from MODEL_ALLOWLIST

**Plan**: `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-012-v1-models.plan.md`
**Epic Branch**: `epic/PRD-015-openai-compatible-endpoint`
**Commit**: `799df1d`

## Summary

Two read-only routes in `app/routers/v1.py`:

| Route | Success | Refusals |
|---|---|---|
| `GET /v1/models` | 200 `{"object": "list", "data": [...]}`, one `ModelEntry` per `settings.model_allowlist_list` item, in configured order | 401 `invalid_api_key`, 403 `permission_denied`, 403 `break_glass_not_permitted` |
| `GET /v1/models/{model_id:path}` | 200 `ModelEntry` | the three above, plus 404 `model_not_found` (`invalid_request_error`) |

`owned_by` is the prefix before the first `/` when it is non-empty, else `harness`. `created` is `0`. The allowlist is read on every request. An `admin`-role user token gets the same list, because the wildcard cannot be listed. Matching is exact (D4): `OPENAI/GPT-4O`, `openai/gpt-4o-mini` and a trailing `/` all return 404.

Both routes use `require_permission(PERMISSION_QUERY_SUBMIT)`, so the STORY-010 handlers already return 401 and 403 in the OpenAI shape. No pipeline runs on these routes, so the router refuses `identity.break_glass` itself. It returns the pipeline's own message (`Break-glass credential not permitted on this ingress: ingress:break_glass`) with `harness: null`, and writes no row. Neither route writes an audit row. Each refusal logs only the user id and the code, never the requested model id. The schemas (`ModelEntry`, `ModelList`) and `_error` already existed; the only new constant is `MODEL_NOT_FOUND` in `v1_translate`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `MODEL_NOT_FOUND` code constant | `app/services/v1_translate.py` | ✅ |
| 2 | `_model_entry`, `_refuse_break_glass` | `app/routers/v1.py` | ✅ |
| 3 | `list_models`, `retrieve_model`; module docstring and `_HTTP_ERRORS` comment | `app/routers/v1.py` | ✅ |
| 4 | HTTP tests for the four ACs, plus 405 and the log line | `tests/test_v1_models.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`); routes registered | ✅ |
| Frontend lint | n/a (no frontend in this repo) |
| `tests/test_v1_translate_request.py` (purity pin) | ✅ 623 passed |
| Existing `/v1` suites (router, errors, query isolation) | ✅ 83 passed |
| `tests/test_v1_models.py` | ✅ 20 passed |
| Full suite (throwaway libSQL `:8086`, keep-awake) | ✅ 4,799 passed / 27 skipped (348.7 s), 0 `libsql verdict` lines, no flakes |
| `-m "not db"` (`HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:9`) | ✅ 3,403 passed / 26 skipped (89.0 s) |
| Mutation check: new tests against the pre-story `v1.py` | ✅ all 20 fail |
| E2E (live uvicorn `:8765`, libSQL `:8087`, curl + `openai` 3.36.1) | ✅ 6/6 |

### E2E results

| Check | Outcome |
|-------|---------|
| `curl /v1/models` with a `user` token | 200, the four default entries in order, `owned_by` harness/harness/openai/anthropic |
| `curl /v1/models/openai%2Fgpt-4o` and `/v1/models/openai/gpt-4o` | 200 for both, the same entry: real uvicorn decodes `%2F` before routing |
| `curl -i /v1/models/nope` | 404 `model_not_found`, `x-should-retry: false`, `harness: null` |
| `curl -i` with `ADMIN_TOKEN` on both routes | 403 `break_glass_not_permitted`, `x-should-retry: false` |
| No bearer; `auditor` token | 401 `invalid_api_key`; 403 `permission_denied` (`Permission denied: query:submit`) |
| OpenAI SDK: `models.list()`, `models.retrieve("openai/gpt-4o")`, an unknown id, break-glass | ids in order; entry `openai/gpt-4o` / `openai` / `0` / `model`; `NotFoundError` 404 `model_not_found` with `x-should-retry: false`; `PermissionDeniedError` 403 `break_glass_not_permitted` |
| `GET /audit` with `ADMIN_TOKEN` after all of the above | `{"total": 0, "queries": []}` |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/routers/v1.py` | UPDATE | +80/-3 |
| `app/services/v1_translate.py` | UPDATE | +2 |
| `tests/test_v1_models.py` | CREATE | +225 |
| `.agents/plans/.../completed/STORY-012-v1-models.plan.md` | CREATE (archived) | +305 |

## Deviations from Plan

1. **The OpenAI SDK does not encode the slash.** The plan's E2E note said `models.retrieve("openai/gpt-4o")` would send `%2F`. `openai` 3.36.1 actually sends `/v1/models/openai/gpt-4o` unencoded. Both forms are tested and work, so behaviour is unchanged.
2. **404 message.** The plan's sketch wrote `"model not in MODEL_ALLOWLIST"`. The implementation uses `"model is not in MODEL_ALLOWLIST"`. Either way the message names the rule, never the id.
3. **Three tests beyond the plan's nine:** `test_empty_prefix_is_owned_by_harness` (a leading `/`, so the prefix is empty), `test_retrieve_reads_allowlist_per_request`, and `test_refusals_log_user_and_code_only` (T9: the log never names the requested id).
4. **E2E cleanup.** After `TaskStop` on `serve.sh`, the uvicorn child (PID 5668) was still holding `:8765`, as in STORY-011. I confirmed its command line and stopped it by PID. Results unaffected.

Everything else matches the plan. The `%2F` risk the plan raised did not happen: Starlette and uvicorn decode before routing, so the route never unquotes.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_v1_models.py` | `test_list_is_allowlist_in_order`, `test_list_reads_allowlist_per_request`, `test_empty_prefix_is_owned_by_harness`, `test_admin_role_user_sees_same_entries`, `test_retrieve_encoded_and_unencoded` (x2), `test_retrieve_unprefixed_is_owned_by_harness`, `test_retrieve_unknown_is_404_model_not_found` (x4), `test_retrieve_reads_allowlist_per_request`, `test_admin_token_is_403_break_glass_not_permitted_without_row` (x2), `test_no_bearer_is_401_invalid_api_key` (x2), `test_auditor_is_403_permission_denied` (x2), `test_post_to_models_is_405`, `test_refusals_log_user_and_code_only` |

20 test cases in total.

## Acceptance Criteria

- [x] Given a `user`-role token and the default `MODEL_ALLOWLIST`, when `GET /v1/models` is sent, then 200 with `object: "list"` and one entry per allowlisted model in configured order, each `{"id", "object": "model", "created": 0, "owned_by"}` with `owned_by` the prefix before `/` or `harness`.
- [x] Given an `admin`-role user token, when the list is requested, then it returns the same entries (the wildcard cannot be enumerated; documented in STORY-019).
- [x] Given `GET /v1/models/openai%2Fgpt-4o` (and the unencoded `/v1/models/openai/gpt-4o`), when sent, then 200 with that entry; given a name not in the list, then 404 `model_not_found` with `x-should-retry: false`.
- [x] Given `ADMIN_TOKEN`, no bearer, or an identity without `query:submit`, when either route is called, then 403 `break_glass_not_permitted`, 401 `invalid_api_key` or 403 `permission_denied` respectively, in the error shape; no route writes an audit row.
- [x] All tasks completed
- [x] Backend tests pass (full suite and `-m "not db"`)
- [x] Follows existing patterns
