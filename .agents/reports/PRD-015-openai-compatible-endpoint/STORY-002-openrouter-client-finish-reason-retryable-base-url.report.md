---
story: STORY-002
prd: PRD-015
plan: .agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-002-openrouter-client-finish-reason-retryable-base-url.plan.md
epic_branch: epic/PRD-015-openai-compatible-endpoint
commit: f4f2a83
status: COMPLETE
completed: 2026-10-21
---

# Implementation Report: STORY-002, OpenRouter client: finish_reason, upstream_status and retryable, OPENROUTER_BASE_URL

**Plan**: `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-002-openrouter-client-finish-reason-retryable-base-url.plan.md`
**Epic Branch**: `epic/PRD-015-openai-compatible-endpoint`
**Commit**: `f4f2a83`

## Summary

The upstream client now reports three facts that `/v1` needs, and every existing caller is unaffected.

- `OpenRouterResult.finish_reason` comes from `choices[0].finish_reason`. It is `None` when the field is absent or not a string. It is declared last with a default, so three-argument construction still works.
- `OpenRouterError` gains keyword-only `upstream_status` and `retryable`. One helper, `_classify_http_error`, sets them:
  - `retryable` is `True` exactly for `httpx.TransportError` (timeouts, connect errors), upstream 5xx and upstream 429.
  - Shape failures, null content and a missing key stay `(None, False)`.
- The message is still the only positional argument, so `str(exc)` and `args` do not change. That keeps the audit `error_message` and `/query`'s 502 `detail` the same.
- `_API_URL` is gone. The client posts to `settings.OPENROUTER_BASE_URL.rstrip('/') + "/chat/completions"`, reading the setting on every call.
- The new setting defaults to `https://openrouter.ai/api/v1`. Its validator, the mitigation for PRD Section 9.2 T10, accepts `https://` with a host, or `http://` only on `127.0.0.1`, `localhost` or `::1`. Messages name the setting, the rule and two examples. They quote only the scheme and host.

Nothing reads the new fields yet. STORY-009 (`finish_reason`), STORY-011 (`retryable`, `upstream_status`) and STORY-014 (the base URL) are their consumers.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `OPENROUTER_BASE_URL` field, `_LOOPBACK_HOSTS`, `_validate_openrouter_base_url`; `hide_input_in_errors` | `app/config.py` | ✅ |
| 2 | Config tests: default, 8 accepted, 8 rejected with message content, 3 no-echo | `tests/test_config.py` | ✅ |
| 3 | `OpenRouterError` attributes; `_classify_http_error`; split request arm | `app/services/openrouter_client.py` | ✅ |
| 4 | `finish_reason` field and read; per-call URL; `_API_URL` deleted | `app/services/openrouter_client.py` | ✅ |
| 5 | Client tests: finish_reason, failure table, byte-identical messages, base URL | `tests/test_openrouter_client.py` | ✅ |
| 6 | Manual slow smoke repointed at the setting | `tests/test_pipeline_concurrency.py` | ✅ |
| 7 | Full suite, `-m "not db"`, `grep _API_URL app` empty | none | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | n/a (no frontend change) |
| Targeted modules (`test_openrouter_client`, `test_config`, `test_v1_query_isolation`, `test_audit_characterization`, `test_pipeline_concurrency`) | ✅ |
| Full suite | ✅ 3,946 passed / 27 skipped / 1 error. The error is an infrastructure flake: `libsql verdict: likely infrastructure`, `STREAM_EXPIRED` at fixture setup in `test_query_router.py::test_existing_success_fields_unchanged_alongside_new_signal`. Rerunning `tests/test_query_router.py` gave 41 passed |
| `-m "not db"` with `HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:9` | ✅ 2,668 passed / 26 skipped |
| Manual slow smoke (`HARNESS_SLOW_SMOKE=1`) | ✅ 1 passed. Ten sends in 61.17 s against a 60 s upstream delay; `/health` 0.0 ms while blocked |
| `grep -rn _API_URL app` | ✅ no output |
| E2E | ✅ 5/5 |

## E2E

The first three checks used a scratch script: a local `ThreadingHTTPServer`, with `OPENROUTER_BASE_URL=http://127.0.0.1:<port>/v1` set **in the environment** and no injected client, so the real `httpx.Client` ran.

1. The server saw `POST /v1/chat/completions`, and the result had `finish_reason == "length"`. ✅
2. Server answering 503 gave `(503, True)`; answering 401 gave `(401, False)`. ✅
3. A closed port gave `(None, True)` (`WinError 10061`). ✅
4. `uvicorn app.main:app` with `OPENROUTER_BASE_URL=http://example.com/v1` exited with code 1 and the validator's message. With the setting unset, `/health` returned `{"status":"ok"}` 200. ✅ (The run first bootstrapped user `e2e-bootstrap-s002`, because the full suite leaves the shared DB empty.)
5. `/query` 502 body unchanged: `tests/test_v1_query_isolation.py` is green in the full run. ✅

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/config.py` | UPDATE | +63/-1 |
| `app/services/openrouter_client.py` | UPDATE | +48/-4 |
| `tests/test_config.py` | UPDATE | +75 |
| `tests/test_openrouter_client.py` | UPDATE | +171/-1 |
| `tests/test_pipeline_concurrency.py` | UPDATE | +3/-4 |
| `.agents/plans/.../completed/STORY-002-...plan.md` | CREATE (archived) | +330 |

## Deviations from Plan

1. **`hide_input_in_errors=True` on `Settings.model_config`** (not in the plan).
   - **Why**: Probing the validator showed that pydantic appends `[... input_value='<whole value>']` to every `ValidationError`. With that, `http://user:<secret>@example.com/v1` echoed the credential even though the message itself quoted only the host. That breaks plan decision 5 and the `_scheme_of` rule.
   - **Scope**: The option is model-wide, so every settings validation error loses the `input_value=` suffix.
   - **Risk**: Nothing in the repo parses `input_value`. Every validator's own message already quotes what it needs. All 165 existing `tests/test_config.py` tests pass unchanged.
   - **Side effect**: The same leak is now closed for `DATABASE_URL?authToken=...` field-level failures.
2. **`test_the_split_fields_are_declared_last_and_in_order` updated** (plan R1, foreseen). It compares the whole field list, so `"finish_reason"` was appended to the expected list. The property it pins still holds: the split fields come after `tokens_used`, in order. This is an exception to AC 5's "every existing test passes without change".
3. **Manual slow smoke repointed** (plan R2 / decision 7, foreseen). It patched the deleted `_API_URL`; it now patches `settings.OPENROUTER_BASE_URL`. The smoke is skipped in CI. It was run manually and passes, which also shows the setting routes a real socket call.
4. **Unparseable netloc.** `urlsplit("http://[bad/v1")` raises `ValueError`. The validator catches it and reports "names no host", so a startup error never becomes a traceback from inside `urllib`. The plan did not spell this out.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_config.py` | `test_openrouter_base_url_defaults_to_openrouter`; `..._accepts_https_or_loopback_http` (8 ids: default, upper-scheme, other-https-host, trailing-slash, ipv4-loopback, localhost, localhost-upper, ipv6-loopback); `..._surrounding_whitespace_is_stripped`; `..._rejection_names_the_setting_rule_and_an_example` (8 ids: http-remote, http-other-127, http-localhost-prefix, ftp, empty, blank, no-scheme, no-host); `..._rejection_never_echoes_the_value` (3 ids: userinfo, path, query-no-host) |
| `tests/test_openrouter_client.py` | `test_finish_reason_is_carried_from_the_first_choice` (stop, length, content_filter); `test_an_unusable_finish_reason_is_none_and_the_call_succeeds` (5 ids); `test_three_argument_construction_leaves_finish_reason_none`; `test_each_failure_carries_upstream_status_and_retryable` (12 ids: read-timeout, connect-timeout, connect-error, 500, 503, 429, 400, 401, 404, malformed-json, missing-choices, null-content); `test_missing_key_is_not_retryable_and_has_no_status`; `test_a_status_failure_message_is_byte_identical_to_todays`; `test_a_transport_failure_message_is_byte_identical_to_todays`; `test_a_shape_failure_message_is_byte_identical_to_todays`; `test_positional_construction_keeps_message_and_conservative_defaults`; `test_default_base_url_gives_todays_request_url`; `test_base_url_setting_redirects_the_request` (2); `test_base_url_is_read_per_call_not_cached_at_import` |

## Acceptance Criteria

- [x] `finish_reason` of `stop` / `length` / `content_filter` is carried. Absent or non-string gives `None`. Three-argument construction works.
- [x] Each listed failure sets `upstream_status` to the HTTP status or `None`, and `retryable` is `True` exactly for timeout, connect error, 5xx and 429. Existing message text is unchanged, and three tests pin it byte for byte.
- [x] With `OPENROUTER_BASE_URL` unset, the URL is `https://openrouter.ai/api/v1/chat/completions`. STORY-001's characterization (`test_v1_query_isolation.py`, `test_characterization_headers_and_url`) passes unchanged.
- [x] `http://127.0.0.1:9100/v1` routes to `.../v1/chat/completions`. `http://example.com/v1`, `ftp://...` and an empty string fail at startup with a message that names the setting, the rule and an example.
- [x] Every existing `call_openrouter` stub and test passes, with the two recorded exceptions (deviations 2 and 3).
- [x] All tasks completed
- [x] Backend server starts without error
- [x] Follows existing patterns
