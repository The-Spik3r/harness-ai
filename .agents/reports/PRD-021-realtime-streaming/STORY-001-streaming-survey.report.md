---
story: STORY-001
prd: PRD-021
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-001-streaming-survey.plan.md
epic_branch: epic/PRD-021-realtime-streaming
commit: 48bfb48
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report — STORY-001: Survey what providers stream and what clients display

**Plan**: `.agents/plans/PRD-021-realtime-streaming/completed/STORY-001-streaming-survey.plan.md`
**Epic Branch**: `epic/PRD-021-realtime-streaming`
**Commit**: `48bfb48`

## Summary

A spike: `scripts/survey_streaming.py` sent small streamed requests, saved sanitized fixtures under `tests/fixtures/prd021_survey/`, and replayed them through `app.services.upstream.sse.parse_events`. The client survey was done by reading installed source. No application code changed. Each finding is labeled **observed** (live request), **code-read** (installed source), or **docs**.

## Requests and cost

5 of the 6 allowed streamed requests, all `max_tokens` 64, `stream: true`, `include_usage: true`:

| # | Target | Result |
|---|--------|--------|
| 1 | OpenRouter `deepseek/deepseek-r1` | HTTP 404, model no longer served (no tokens) |
| 2 | OpenRouter `qwen/qwen3-8b` (the one retry) | HTTP 404, model deprecated (no tokens) |
| 3 | local `google/gemma-4-e4b` @ `localhost:1235/v1` | reachable, streamed |
| 4 | OpenRouter `deepseek/deepseek-r1-0528` (id found via the public `/models` list, which is not a counted call) | streamed |
| 5 | OpenRouter `openai/gpt-4o-mini` | streamed |

The "reasoning only with a parameter" re-run was not needed (reasoning arrived without a parameter). The script counter is per process, so the second run was started with `--already-used 3`. Cost as reported by OpenRouter: about 0.00014 USD for the reasoning call, less for gpt-4o-mini. The first run's local fixture was written before a crash in the summary step (`ModuleNotFoundError: app`, fixed by running with `PYTHONPATH=.`); its summary was recomputed offline from the saved fixture.

## Per-model facts (observed)

| Fact | OpenRouter `deepseek/deepseek-r1-0528` (provider DeepInfra) | OpenRouter `openai/gpt-4o-mini` | local `google/gemma-4-e4b` |
|---|---|---|---|
| Reasoning delta field | `delta.reasoning` (string) and `delta.reasoning_details[]` (`{"type":"reasoning.text","text":...}`); never `reasoning_content` | none | none |
| Reasoning without a request parameter | yes: no `reasoning` param sent, reasoning streamed | n/a | n/a |
| Reasoning vs content | all 64 tokens went to reasoning; `finish_reason: "length"`; `content` was `""` on every chunk, so content never started | n/a | n/a |
| Usage chunk | last chunk, with a non-empty `choices` (it also carries `finish_reason`); keys `prompt_tokens, completion_tokens, total_tokens, cost, cost_details, is_byok, prompt_tokens_details, completion_tokens_details{reasoning_tokens,...}`. `reasoning_tokens` was 74 against `completion_tokens` 64: do not assume reasoning_tokens <= completion_tokens | last chunk, with non-empty `choices`; same keys, `reasoning_tokens` 0 | separate final chunk with `choices: []`; keys `prompt_tokens, completion_tokens, total_tokens, completion_tokens_details{reasoning_tokens: 0}` |
| Keep-alive SSE comments | yes (`: OPENROUTER PROCESSING`; dropped from the fixture) | none seen | none seen |
| Chunks with `finish_reason` | two (`length` on the last reasoning chunk, again on the usage chunk) | two (`stop` twice) | one |
| Extra delta keys | `role` and `content: ""` on every chunk | `role`; `content: ""` on the finish chunks | `role` on the first chunk only |
| Extra chunk keys | `provider`, `service_tier`, `native_finish_reason` | `provider`, `system_fingerprint`, `service_tier`, `native_finish_reason` | `system_fingerprint`, `logprobs` |

## What `parse_events` yields and drops (observed, replay of the saved fixtures)

| Fixture | Events yielded | Delta keys that produce no event |
|---|---|---|
| deepseek-r1-0528 | `TextDelta` 38, `Finish` 2, `UsageReport` 1 | `reasoning`, `reasoning_details`, `role` |
| gpt-4o-mini | `TextDelta` 4, `Finish` 2, `UsageReport` 1 | `role` |
| gemma-4-e4b | `TextDelta` 2, `Finish` 1, `UsageReport` 1 | `role` |

Consequences for the adapter (STORY-003), all observed:
- Reasoning is dropped today (`sse.py` `_chunk_events` reads only `delta.content` and `delta.tool_calls`). It must read `delta.reasoning_content`, then `delta.reasoning` (OpenRouter's name), and ignore `reasoning_details` (a structured duplicate of the same text).
- `content: ""` becomes `TextDelta("")` (any `str` is accepted): 38 empty TextDeltas in the reasoning stream. Consumers must treat an empty `TextDelta` as nothing (no first-token stamp, no empty chunk to a client).
- A stream can carry two `Finish` events, and usage can ride on a chunk that also has `choices`, so a consumer must not treat the first `Finish` as the end or expect a separate usage chunk.
- `reasoning: null` appears on a finish chunk; a `str` check is needed.
- A reasoning model with a small `max_tokens` can end with `length` and zero content: a reasoning-only stream is a real case.

## Client survey

| Client | Version | Source | Displays `reasoning_content` | Displays `reasoning` |
|---|---|---|---|---|
| Cline | 3.0.74 CLI; `@cline/llms` 0.2.0 builds OpenAI-compatible providers with `createOpenAICompatible` from `@ai-sdk/openai-compatible` (declared `^3.0.67`; the top-level install is 3.0.92) | code-read: `tests/e2e/.clients/cline/node_modules/@cline/llms/dist/index.js` (`createOpenAICompatible as L3`) and `node_modules/@ai-sdk/openai-compatible/dist/index.js:835` `const reasoningContent = delta.reasoning_content ?? delta.reasoning;` (non-streaming `:592` the same) | yes | yes (fallback) |
| OpenCode | 2.3.2 (compiled binary, no JS source) | code-read of the binary with `grep -a`: its model catalog carries `"compatibility":{"reasoning_field":"reasoning_content"}` on 1514 entries and `"reasoning_field":"reasoning_details"` on 104; the schema `Model.ReasoningField` is the enum `reasoning`, `reasoning_content`, `reasoning_text`; message schemas accept `reasoning_content`, `reasoning`, `reasoning_text`, `reasoning_details`. The field is chosen per model from the catalog. **Inconclusive**: the default for a user-defined openai-compatible provider that sets no `reasoning_field`; `reasoning` is not the catalog value in any of the 1618 entries found. Docs were not consulted | yes (the dominant catalog value) | configurable per model; not a catalog value |
| OpenAI Python SDK | 3.40.0 | observed offline: `ChatCompletionChunk.model_validate(...)` with `delta.reasoning_content` and `delta.reasoning` leaves both in `delta.model_extra`, no typed field; code-read: `_models.py:150` `extra="allow"`, and `lib/streaming/chat/_completions.py` has no reasoning handling | no (kept as an unlisted extra, never displayed) | no |

## O5 verdict

**Emit only `reasoning_content`.** No target client reads `reasoning` without also reading `reasoning_content`: Cline reads `reasoning_content` first and falls back to `reasoning`; OpenCode's catalog value is overwhelmingly `reasoning_content`; the OpenAI SDK displays neither. The story's rule (emit `reasoning` beside `reasoning_content` only if a target client reads `reasoning` and not `reasoning_content`) therefore keeps `reasoning` off. Caveat: the OpenCode default for an unconfigured custom provider was not determined from the binary; if STORY-015's docs check finds it expects `reasoning`, revisit.

## Implications

- STORY-003: map `delta.reasoning_content` then `delta.reasoning`; drop `reasoning_details`; ignore empty strings and `null`; tolerate usage on a chunk with `choices` and a second `Finish`. Replay the three fixtures below.
- STORY-014: the `/v1` output field is `delta.reasoning_content` only (O5). Providers differ on input (`reasoning` from OpenRouter, none from the local server), so the adapter, not `/v1`, normalizes the name.
- STORY-015: document that OpenRouter reasoning arrives without a request parameter and can exhaust a small `max_tokens`; document the OpenCode default as unverified.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Survey script (sanitizer, runner, budget counter, parser comparison) | `scripts/survey_streaming.py` | done |
| 2 | Offline tests | `tests/test_survey_streaming.py` | done |
| 3 | Live run | `tests/fixtures/prd021_survey/*.sse` | done (5 requests) |
| 4 | Client survey | this report | done |
| 5 | Report | this file | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | OK |
| Targeted tests (`tests/test_survey_streaming.py`, `tests/test_untouched_app.py`) | 15 passed, 0 failed, 0 skipped |
| Offline run without a key | exit 0 with a message, nothing written |
| Fixture replay through `parse_events` | 3/3 replay to `[DONE]` without raising (4, 41, 7 events) |
| Key-leak check | first 8 characters and the full key searched in the three fixtures, the script, the test and the captured outputs: 0 hits; this report checked before commit (key never printed) |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

| File | Action |
|------|--------|
| `scripts/survey_streaming.py` | CREATE |
| `tests/test_survey_streaming.py` | CREATE (6 tests) |
| `tests/fixtures/prd021_survey/local-google-gemma-4-e4b.sse` | CREATE |
| `tests/fixtures/prd021_survey/openrouter-deepseek-deepseek-r1-0528.sse` | CREATE |
| `tests/fixtures/prd021_survey/openrouter-openai-gpt-4o-mini.sse` | CREATE |
| report, archived plan, story, index | CREATE/UPDATE |

## Deviations from Plan

- Reasoning model id: the planned `deepseek/deepseek-r1` and the fallback `qwen/qwen3-8b` both returned 404 (no longer served, deprecated), which used the budgeted retry. `deepseek/deepseek-r1-0528` came from the public models list and was call 4, within the 6-request cap. Script defaults were updated to working ids.
- The script gained `--already-used` so a second invocation counts the first run's requests.
- The error text for a failed request is reduced to the provider's message (the first 404 echoed a provider user id to the terminal; no key, and nothing reached a file).
- The 40-character cut is applied after scrubbing the key, so a cut cannot leave half a key.

## Acceptance Criteria

- [x] AC1 OpenRouter reasoning and non-reasoning facts: tables above (live run)
- [x] AC2 local server reachable and recorded; the unreachable path prints a message and exits 0 (`test_unreachable_local_is_not_an_error`)
- [x] AC3 sanitized, replayable fixtures under `tests/fixtures/prd021_survey/`, replay check above
- [x] AC4 OpenCode, Cline, OpenAI SDK and the O5 verdict: client table (OpenCode default for custom providers marked inconclusive)
- [x] AC5 clean exit without a key: `tests/test_survey_streaming.py::test_no_key_exits_cleanly`; the script is not collected (name, `scripts/`)
