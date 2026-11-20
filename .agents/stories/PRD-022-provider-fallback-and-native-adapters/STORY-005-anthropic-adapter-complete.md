---
id: STORY-005
prd: PRD-022
slug: anthropic-adapter-complete
title: AnthropicAdapter.complete() — request/response mapping, SDK error mapping, cache tokens
type: feature
priority: high
complexity: large
phase: "2 - Anthropic native adapter"
status: todo
labels: [backend, upstream, anthropic]
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
plan: null
report: null
commit: null
depends_on: [STORY-002, STORY-004]
blocks: [STORY-007]
skills: []
created: 2026-11-20
updated: 2026-11-20
---

# STORY-005: AnthropicAdapter.complete()

## Description

As a coding agent, I want a Claude model reached through the Messages API to give me the same `UpstreamResult` — text, tool calls, finish reason, usage — as the OpenAI-compatible path, so that my tool loop does not care which wire format answered.

## Acceptance Criteria

- [ ] Given an `UpstreamRequest`, when mapped, then every row of PRD 6.5's request table holds (system hoisting joined by `\n\n`; `""` assistant content omitted; `tool_calls` → `tool_use` with `json.loads(arguments)`; consecutive `tool` turns → one `user` message of `tool_result` blocks; tools → `input_schema`; `tool_choice` none/auto/required/named; `parallel_tool_calls: false` → `disable_parallel_tool_use`; `max_tokens` default from `default_max_tokens`; `stop` → `stop_sequences`; `temperature`/`top_p` only with `sampling_params`), and the request's top-level key set equals an explicit allowlist (T9 test)
- [ ] Given `arguments` that is not a JSON object, or a forced `tool_choice` on a model without `forced_tool_choice`, when mapped, then `UpstreamError(kind="incompatible", retryable=False)` is raised before any network call; nothing is guessed
- [ ] Given a Messages response, when mapped, then text blocks concatenate into `response`; `tool_use` → `ToolCallSpec(id, name, json.dumps(input, ensure_ascii=False, separators=(",", ":")))`; `thinking`/`redacted_thinking` only increment `reasoning_blocks`; `stop_reason` maps per 6.5 (`refusal` → `content_filter`, `pause_turn` → `shape` error); prompt tokens = `input_tokens + cache_creation_input_tokens + cache_read_input_tokens` (unit test with all three non-zero); cache fields set; missing `usage` is a `shape` error
- [ ] Given SDK exceptions, when raised, then `APITimeoutError` → `timeout`, `APIConnectionError` → `transport`, `AuthenticationError` → `misconfigured` (401, not retryable), `RateLimitError` → `status` 429 retryable with `retry_after_seconds`, 529/5xx → `status` retryable, other `APIStatusError` → `status` non-retryable; messages start with the provider `label`; the key never appears in a message
- [ ] Given `sampling_params: false` and a request with `temperature`/`top_p`, when sent, then they are dropped and the result reports the dropped names so the row's `ignored_params` can record `temperature@<provider name>` (the pipeline wiring is STORY-008); `prompt_cache: auto` adds top-level `cache_control: {"type": "ephemeral"}`; the client is built with `max_retries=0`, `timeout=provider.timeout_seconds`, `base_url=provider.base_url`; all tests run without network (SDK transport mocked or a local fake)

## Technical Notes

- New file `app/services/upstream/anthropic.py`; register it in STORY-004's type→adapter mapping. Pure mapping functions (`build_request`, `map_response`) separate from the SDK call so they are unit-testable.
- Message model: `app/models/messages.py:38-51`. `ToolParams`/`GenerationParams`: `app/services/upstream/params.py`. Mirror `openai_compatible.py`'s structure and docstring style.
- The dropped-parameter channel: a new defaulted `UpstreamResult` field (e.g. `dropped_params: tuple[str, ...] = ()`) is acceptable; record the choice in the plan.
- `reasoning` capability on: request thinking per STORY-001's finding (6.6); `complete()` never puts thinking text in `response` (D14).
- Use the SDK version pinned by STORY-001; if STORY-001 recommended raw `httpx` (D2 fallback), the orchestrator will have amended this story.
- Orchestrator decision (STORY-001 findings, binding): build `anthropic.Anthropic(api_key=key, base_url=provider.base_url, timeout=<timeout>, max_retries=0, http_client=anthropic.DefaultHttpxClient(follow_redirects=False))` -- the SDK's default client follows redirects; a 30x then surfaces as `APIStatusError` and maps to a non-retryable `status` error (PRD-020 D5). The SDK sends the key as `Authorization: Bearer` (not `x-api-key`). Catch `APITimeoutError` before `APIConnectionError` (subclass). `OverloadedError` (529) subclasses `InternalServerError`. `retry-after` comes from `exc.response.headers.get("retry-after")` (int >= 1, else None). `stop_reason` has a 7th value `model_context_window_exceeded` -> `length` (PRD 6.5 amended). Thinking `{"type":"adaptive","display":"summarized"}` exists in 2.11.0. Facts and SDK file paths: the STORY-001 report.

## Dependencies

- **Blocked by**: STORY-002, STORY-004
- **Blocks**: STORY-007

## PRD Reference

Source: [`PRD-022/PRD.md`](../../PRDs/PRD-022-provider-fallback-and-native-adapters/PRD.md) — Sections 6.5, F2, D2, D4, D14, T6, T9
