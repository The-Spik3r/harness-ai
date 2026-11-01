---
story: STORY-006
prd: PRD-015
plan: .agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-006-parameter-classification-and-tools-refusal.plan.md
epic_branch: epic/PRD-015-openai-compatible-endpoint
commit: b62f21e
status: COMPLETE
completed: 2026-10-22
---

# Implementation Report — STORY-006: Parameter classification: forward, ignore-and-record, reject; the explicit tools refusal

**Plan**: `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-006-parameter-classification-and-tools-refusal.plan.md`
**Epic Branch**: `epic/PRD-015-openai-compatible-endpoint`
**Commit**: `b62f21e`

## Summary

`app/services/v1_translate.py` now has `translate_request(body: ChatCompletionRequest) -> V1Call`. `V1Call` is a frozen dataclass with these fields: `messages`, `params`, `model`, `stream`, `include_usage` and `ignored_params`. It has no `profile` or `ingress` field (T4).

Every key the client sends is in exactly one of three groups (PRD Section 7.3):

- **`FORWARDED`**: `temperature`, `top_p`, `max_tokens`, `stop`, `max_completion_tokens`. Each value is type-checked, then validated alone through `GenerationParams.from_mapping`, so a failure is `invalid_parameter` with `param` set to the key. `max_completion_tokens` becomes `max_tokens`. If both are sent with different values, the request is refused on `max_completion_tokens`. `params` is `None` when nothing was forwarded.
- **`REJECTED_UNLESS_DEFAULT`**: each key lists its accepted defaults, and a value matches only when both type and value match, so `n: true` is not `n: 1`. A non-default value of `tools`, `functions`, `tool_choice` (anything except `"none"`) or `function_call` is `tools_not_supported`. A non-default value of `n`, `logprobs`, `top_logprobs`, `response_format`, `modalities` or `audio` is `unsupported_parameter`.
- **Everything else** is ignored, and only its name is recorded. `ignored_params` is the sorted, comma-joined set of top-level names, `stream_options.<key>` sub-keys and STORY-005's `messages[].name`. It is `None` when nothing was ignored. A key counts as sent when it is present, even as `null`.

`include_usage` is `True` only when the request is streamed. A malformed `stream_options` is `invalid_parameter`. Checks run in a fixed order: rejected keys, forwarded keys, `stream_options`, messages.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Constants, the classification table and `V1Call` | `app/services/v1_translate.py` | ✅ |
| 2 | Rejected-unless-default check | `app/services/v1_translate.py` | ✅ |
| 3 | Forwarded parameters (type check, per-key `from_mapping`, alias) | `app/services/v1_translate.py` | ✅ |
| 4 | `stream_options`, ignored names, `translate_request` | `app/services/v1_translate.py` | ✅ |
| 5 | DB-free unit tests for AC 1-5, T4 and T6; `test_is_pure` allowlist | `tests/test_v1_translate_request.py` | ✅ |
| 6 | T5 upstream-body test through `run_conversation` (db) | `tests/test_v1_translate_request.py` | ✅ |
| 7 | `GenerationParams` / `from_mapping` docstrings name the production caller | `app/services/openrouter_client.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | n/a (no frontend in this repo's change) |
| `tests/test_v1_translate_request.py -m "not db"` | ✅ 623 passed, 1 deselected (the T5 test) |
| Targeted with DB: translate_request, v1_query_isolation, openrouter_client, v1_schemas | ✅ 745 passed |
| Full suite | ✅ 4,612 passed, 27 skipped (6 min 12 s), no `libsql verdict` lines |
| E2E | ✅ 3/3 |

E2E checklist (from the plan):

- [x] The T5 test passes. The upstream body keys are exactly `model, messages, temperature, max_tokens, top_p, stop` while the request carries every ignored key and every accepted default, and `max_completion_tokens=100` arrives as `max_tokens: 100`.
- [x] `tests/test_v1_query_isolation.py` passes unchanged.
- [x] Interactive check with an Aider-like body (`stream`, `stream_options.include_usage`, `temperature: 0`, `max_tokens`, `seed`, `user`, `frequency_penalty`, `parallel_tool_calls`, `tools: []`, `tool_choice: "none"`, `n: 1`, a message `name`). Result: `params=GenerationParams(temperature=0, max_tokens=4096)`, `include_usage=True`, `ignored_params='frequency_penalty,messages[].name,parallel_tool_calls,seed,user'`. No value appears in the `V1Call`.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/v1_translate.py` | UPDATE | +173/-6 |
| `app/services/openrouter_client.py` | UPDATE (docstrings) | +3/-2 |
| `tests/test_v1_translate_request.py` | UPDATE | +500/-3 |
| `.agents/plans/.../completed/STORY-006-...plan.md` | CREATE (archived plan) | +377 |

## Deviations from Plan

- **More test cases than the plan listed, all in the plan's sections.** They cover: an integer `temperature`; `max_completion_tokens` beside a `null` `max_tokens`; `n=1.0`; a bare-string `response_format` and `modalities`; `tool_choice="required"`; a named `function_call`; accepted `functions: []` and `function_call: null`; `model` and `stream` passing through; and a tools refusal winning over a bad `n`, a bad `temperature` and a `tool` message all at once.
- **The test DB was a throwaway container.** The shared `harness-libsql-dev` container no longer exists, so the DB-backed runs used a throwaway libsql container (`harness-libsql-story006`, port 8086) through `HARNESS_TEST_LIBSQL_URL`. Shared state was not touched.
- **The first full-suite run was discarded.** The machine went into S3 sleep at 20:47 (Kernel-Power 42 and then 107 in the System log), and Docker Desktop did not survive it, so every later `db` test errored at setup. After restarting Docker Desktop and the container, the suite was rerun under the `SetThreadExecutionState` keep-awake wrapper, and that run is the one reported above. The code was not changed between the two runs.

## Notes for Later Stories

- **STORY-007**: ignored key names are client-chosen strings and are recorded verbatim. A key containing a comma would make the column ambiguous, and a very long key goes through uncapped. PRD 7.3 records names as they are and a body-size cap is out of scope (PRD 9.4), so nothing was changed here. Decide whether the column needs a cap.
- **STORY-009**: the router passes `call.messages, None, call.model, None, call.params` to `run_conversation`, plus `ignored_params=call.ignored_params` once STORY-007 lands. `profile="code"` and `ingress="v1"` stay literals at the call site.
- **STORY-013**: read `call.include_usage` as-is. It is already `False` for a request that is not streamed.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_v1_translate_request.py` | AC 1: forwarded params; `params is None` when empty; explicit nulls; integer temperature; `max_completion_tokens` alias (alone, equal, beside a null, different); 17-case invalid-parameter table (range, `"hot"`, `True`, NaN, `1.5`, `"5"`, `stop` shapes); check order. AC 2: 12 unsupported cases, 8 accepted defaults. AC 3: 8 tool-use cases, 6 accepted defaults, tools-first ordering. AC 4: the exact AC body; canary values never in `repr(call)`; nothing ignored is `None`; `seed: null` recorded; `messages[].name` merged once; `include_usage` needs `stream`; 3 malformed `stream_options` cases. T4: `profile`/`ingress` ignored, and `V1Call` has no such fields. AC 5: `FORWARDED` equals `GenerationParams` fields plus the alias; the groups are disjoint; every declared request field is classified. T6: 6 canary refusals with `__cause__ is None`. Messages delegate to `translate_messages`. T5: upstream body keys through `run_conversation` (db). `test_is_pure` allowlist updated |

The file now collects 624 tests (623 without DB, 1 db).

## Acceptance Criteria

- [x] Given `temperature`, `top_p`, `max_tokens` and `stop` within range, when `translate_request` runs, then they become a `GenerationParams`; out of range is `V1RequestError(code="invalid_parameter", param=<name>)`; `max_completion_tokens` alone becomes `max_tokens`, and both present with different values is `invalid_parameter`.
- [x] Given `n=2`, `logprobs=true`, `top_logprobs=3`, `response_format={"type":"json_object"}` or `json_schema`, or `modalities=["text","audio"]`, when it runs, then `code="unsupported_parameter"` with `param` set; given `n=1`, `logprobs=false`, `response_format={"type":"text"}` or `modalities=["text"]`, then each is accepted and none is recorded as ignored.
- [x] Given non-empty `tools`, `functions`, `tool_choice` other than `"none"`, or `function_call`, when it runs, then `code="tools_not_supported"`; given `tools: []`, `tools: null` or `tool_choice: "none"`, then the request is accepted.
- [x] Given `seed`, `user`, `presence_penalty`, `logit_bias`, `metadata`, `profile`, `ingress`, `openrouter_api_key` and an unknown key, plus `stream_options={"include_usage": true, "foo": 1}`, when it runs, then `ignored_params` is the sorted comma-joined names including `stream_options.foo` (values never appear), `include_usage` is `True`, and with nothing ignored it is `None`.
- [x] Given a test over the classification table, when it runs, then the forwarded set equals `GenerationParams`' fields plus `max_completion_tokens`; and given a full request through `run_conversation` with an `httpx.MockTransport`, the upstream body's keys are still exactly STORY-001's set (PRD T5).
- [x] All tasks completed
- [x] The file's `-m "not db"` run green with Docker stopped; full suite green
- [x] Follows existing patterns (pure module, `f"{param}: {rule}"` messages, no values in errors)
