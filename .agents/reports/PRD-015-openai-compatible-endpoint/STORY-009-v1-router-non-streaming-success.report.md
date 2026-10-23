---
story: STORY-009
prd: PRD-015
plan: .agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-009-v1-router-non-streaming-success.plan.md
epic_branch: epic/PRD-015-openai-compatible-endpoint
commit: 3193854
status: COMPLETE
completed: 2026-10-23
---

# Implementation Report — STORY-009: POST /v1/chat/completions: router, identity, device header and non-streaming success

**Plan**: `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-009-v1-router-non-streaming-success.plan.md`
**Epic Branch**: `epic/PRD-015-openai-compatible-endpoint`
**Commit**: `3193854`

## Summary

`POST /v1/chat/completions` now exists in the new `app/routers/v1.py` and is mounted by `app/main.py` only when `V1_ENABLED` is on. It authenticates with `require_permission(query:submit)`, the same check `/query` uses. `X-Harness-Device` goes through the new pure `v1_translate.translate_device`, and the body through the existing `translate_request`. `run_conversation` then runs on the pipeline executor with the literals `profile="code"` and `ingress="v1"`, plus `streamed=False` and the translated `ignored_params`. A per-request `call_openrouter` wrapper (`_Upstream`) keeps the upstream `OpenRouterResult`, so `finish_reason` and the token split reach the response without changing the pipeline or `/query`'s body. The new pure `v1_translate.translate_result` builds the Section 7.4 `chat.completion`, and the response carries `X-Harness-Audit-Id`. A `V1RequestError` becomes a 400 error object. `stream: true` and every non-success result return a 501 placeholder with `x-should-retry: false`, which STORY-013 and STORY-010 replace.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `translate_device`, `translate_result`, `INVALID_HEADER`, `MAX_DEVICE_LENGTH`, `DEVICE_HEADER` | `app/services/v1_translate.py` | ✅ |
| 2 | Pure tests for both functions | `tests/test_v1_translate_result.py` | ✅ |
| 3 | Router: route, `_Upstream` wrapper, `_error`, placeholders | `app/routers/v1.py` | ✅ |
| 4 | Mount behind `V1_ENABLED` | `app/main.py` | ✅ |
| 5 | Call-site scan lists the `/v1` site | `tests/test_query_pipeline_audit_fields.py` | ✅ |
| 6 | Route reservations assert `/v1/chat/completions` | `tests/test_route_reservations.py` | ✅ |
| 7 | HTTP tests for AC 1-5 and the placeholders | `tests/test_v1_router.py` | ✅ |
| 8 | Regression: targeted set, full suite, `-m "not db"` | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | n/a (no frontend in this repo; backend-only story) |
| Targeted regression (11 files) | ✅ 920 passed |
| Full suite, throwaway libSQL `:8086` | ✅ 4,698 passed / 27 skipped in 309 s (first run: 2 failed, see Deviations) |
| `-m "not db"`, Docker-free (`HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:9`) | ✅ 3,366 passed / 26 skipped |
| E2E | ✅ 6/6 |

### E2E (uvicorn on `:8765`, throwaway libSQL `:8087`, scratchpad stub upstream on `:9109` via `OPENROUTER_BASE_URL`)

| # | Check | Result |
|---|-------|--------|
| 1 | Server starts, `/health` → `{"status":"ok"}` | ✅ |
| 2 | curl success: 200, `x-harness-audit-id: 1`, `id: chatcmpl-harness-1`, `finish_reason: length`, `usage` 12/5/17, `harness.audit_id: 1` | ✅ |
| 3 | `GET /audit` (admin token): row 1 `ingress=v1`, `profile=code`, `streamed=False`, `device=e2e-laptop`, `ignored_params=seed`, `message_count=1`, `session_id=None` | ✅ |
| 4 | OpenAI Python SDK `openai==3.36.1`: `ChatCompletion`, content, `finish_reason=length`, usage, `r.id == chatcmpl-harness-{model_extra["harness"]["audit_id"]}` → True | ✅ |
| 5 | 129-char `X-Harness-Device` → 400 `invalid_header`, message without the value, audit total stays 2, stub received no request | ✅ |
| 6 | Restart with `V1_ENABLED=false` (`:8766`): `/v1/chat/completions` → 404, `/query` → 200 SUCCESS | ✅ |

The stub logged both upstream bodies as only `model` and `messages`: `seed` and the body `user` were not forwarded (T5).

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/routers/v1.py` | CREATE | +129 |
| `app/services/v1_translate.py` | UPDATE | +93/-6 |
| `app/main.py` | UPDATE | +7 |
| `tests/test_v1_router.py` | CREATE | +370 |
| `tests/test_v1_translate_result.py` | CREATE | +181 |
| `tests/test_v1_translate_request.py` | UPDATE | +2 |
| `tests/test_route_reservations.py` | UPDATE | +7 |
| `tests/test_query_pipeline_audit_fields.py` | UPDATE | +4/-1 |
| `tests/test_query_pipeline_multiturn.py` | UPDATE | +10 |
| `tests/test_pii_redaction_integration.py` | UPDATE | +5/-1 |

## Deviations from Plan

1. **Purity test extended instead of duplicated.** The plan (Task 2) asked for a new `ast` purity test in `tests/test_v1_translate_result.py`. `tests/test_v1_translate_request.py::test_is_pure` already pins the whole module's imports, and it failed on the new `app.models.schemas` import. I added `app.models.schemas` to its allowlist (it is pydantic only) and wrote no second test.
2. **Two guards the plan did not foresee failed the first full run, and both were written for exactly this handoff:**
   - `tests/test_query_pipeline_multiturn.py::test_no_route_accepts_messages_params_or_system`. Its docstring says "PRD-014 … must update this test deliberately", and "PRD-014" is this PRD's former number. `/v1/chat/completions` is now exempt for `messages` only. A new pin fails if that route gains `params`, `system` or `profile`, or if any other route gains any of the four fields.
   - `tests/test_pii_redaction_integration.py::test_pre_epic_test_files_are_unmodified_by_this_epic[tests/test_route_reservations.py]`. AC 4 requires that file to assert the `/v1` paths, so it can no longer be byte-pinned. Following the precedent PRD-010 STORY-003 and PRD-011 STORY-008 set, it leaves the layer 1 list with a comment. Layer 2 (no test function removed or renamed) still covers it, and both of its original functions are unchanged.
3. **Smaller additions.** `translate_device` refusals set `param=None` and name the header in the message. There is one extra HTTP test (`test_device_header_is_stripped`) and one for BYOK (`test_no_byok_key_reaches_upstream`: a body `openrouter_api_key` is ignored and recorded, and the upstream gets `api_key=None`). The blocked-result placeholder test checks `suspicious_pattern` and `pattern_action`, because `AuditLog` has no `suspicious_pattern_detected` field (that name belongs to `AuditQueryEntry`).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_v1_translate_result.py` (28) | Section 7.4 example as a whole dict; finish reasons that pass through (3); others become `stop` (None, `error`, `tool_calls`, empty); missing split 0/0/total; each side of the split falls back alone (3); the total is the pipeline's; the `harness` PII fields; `id`/`model` from the pipeline result; blank or absent device becomes None (4); stripping; the 128 limit counted after stripping; over the limit; non-printable (tab, NUL, DEL, zero-width space, newline); the refusal never echoes the value |
| `tests/test_v1_router.py` (16) | Success shape plus header (AC 1); finish_reason None becomes stop; missing split; one v1 row with all fields (AC 2); bad device header, over 128 and non-printable (AC 3); stripped device; absent device is NULL; body `user` is neither device nor identity; tools refusal is 400 with no row; params sent only when given; no BYOK; executor threads (AC 5); V1 disabled returns 404 and `/query` is unaffected (AC 4, no DB); placeholder 501 for `stream`; placeholder 501 for a blocked result |
| `tests/test_route_reservations.py` | `test_v1_routes_present_when_enabled` |
| `tests/test_query_pipeline_audit_fields.py`, `tests/test_query_pipeline_multiturn.py` | Guard updates (see Deviations) |

## Acceptance Criteria

- [x] AC 1: 200 with the Section 7.4 shape, `id == chatcmpl-harness-{audit_id}`, `model` as requested, the upstream `finish_reason` (or `"stop"`), usage 0 for a missing split with the total as reported, `harness.audit_id`, and the `X-Harness-Audit-Id` header.
- [x] AC 2: exactly one row with `ingress='v1'`, `profile='code'`, `streamed=0`, `session_id` NULL, `message_count == len(messages)`, `ignored_params` as translated, and `device` from the header.
- [x] AC 3: a device header over 128 characters or with a non-printable character gets 400 `invalid_header` and no row; an absent header is NULL; the body `user` is neither device nor identity.
- [x] AC 4: with `V1_ENABLED=false` the route is 404 and `/query` is unaffected (test and live server); with it on, `tests/test_route_reservations.py` passes and asserts the `/v1` path.
- [x] AC 5: the pipeline body runs on the `pipeline` executor threads.
- [x] All tasks completed
- [x] Backend server starts without error
- [x] Follows existing patterns
