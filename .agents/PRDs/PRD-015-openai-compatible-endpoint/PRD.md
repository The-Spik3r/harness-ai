---
id: PRD-015
slug: openai-compatible-endpoint
title: OpenAI-Compatible Endpoint (Text) — One Base URL, Every Verdict an Ordinary API Error
status: draft
base_branch: main
epic_branch: epic/PRD-015-openai-compatible-endpoint
created: 2026-10-21
updated: 2026-10-21
---

> **Numbering.** The track's briefs, PRDs 010–013 and the code comments call this PRD **"PRD-014"**. That number went to the test-suite PRD ([PRD-014](../PRD-014-test-suite-db-isolation/PRD.md)) first, so this one is PRD-015. Every comment that says "PRD-014 adds `/v1`" (`query_pipeline.Ingress`, `GenerationParams.from_mapping`, `pattern_config`, `schemas.QueryBlockedUsageLimitResponse`) means this document. Tool calling and action policy are referred to by their briefs (PRE-PRD-016, PRE-PRD-015) because their PRD numbers are not assigned yet.

## 1. Executive Summary

`POST /query` is a shape only this project speaks, so the chat UI is its only client. The tools developers actually point at a model — the OpenAI SDKs, Aider, Continue, OpenCode, Cline — speak OpenAI Chat Completions. Today they cannot use the harness without a custom client, so they go straight to a provider, and none of the harness's controls see their traffic.

The hard part is already built. PRD-010 made the pipeline take a `messages` list (`run_conversation`) and shipped the normalizer and `GenerationParams.from_mapping` for this ingress. PRD-011 and PRD-012 built the `code` profile: patterns that do not fire on source vocabulary, PII redaction that leaves fenced code and the response unmasked. PRD-013 added `ingress`, `streamed`, the conversation key, usage limits, and refused `ADMIN_TOKEN` on `v1` in advance. Every one of those is reachable today only by direct call, with comments saying where the `/v1` ingress will plug in.

This PRD is the **translation layer**, and nothing else. It adds `POST /v1/chat/completions` and `GET /v1/models`. It maps a request onto `run_conversation(profile="code", ingress="v1")`, a success onto a `chat.completion`, and each of the six verdicts onto an OpenAI error object with a 400 or 403 status and a harness `code`, so clients show the error instead of retrying. `stream: true` is **buffered SSE**: the full response is checked, then emitted as chunks. A block decided before the upstream call still gets its real status code, even on a streamed request. It adds no new check and changes no check order.

**MVP goal:** with only `OPENAI_BASE_URL` and `OPENAI_API_KEY` changed, the OpenAI Python SDK (streaming and not), Aider and Continue complete text tasks through the harness. A blocked prompt raises the SDK's `BadRequestError` or `PermissionDeniedError` naming the harness reason, with no retry. Every pipeline verdict writes its audit row with `ingress='v1'`, `profile='code'` and the request's `streamed` flag. The `/query`, chat UI and console regression suites pass with no assertion changed.

## 2. Mission

Make the harness a drop-in base URL for text completions, so the controls built in PRDs 009–013 cover the traffic of real coding tools, without a second pipeline and without weakening any of them.

Core principles:

- **Translate, never re-decide.** `/v1` maps shapes. Every verdict comes from `run_conversation`, in its existing order. The router adds no content check, and no request field selects a profile, an ingress or a policy.
- **A verdict is an error, not a completion.** A block is never dressed as an assistant message, never an empty choice, and never a status a client retries (`429`, `5xx`). The client shows it to its user.
- **Retry only what retrying can fix.** Transient upstream and storage faults are retryable. Every verdict, and every deterministic failure, says not to retry, by status code and by `x-should-retry: false`.
- **Refuse loudly, never drop silently.** A parameter that would change what the caller gets (`tools`, `n > 1`, `logprobs`, structured output) is a 400 naming it. A parameter that does not is ignored, and its *name* is recorded on the audit row.
- **Streaming-shaped, not streaming-latency.** No byte of a response leaves the process before output handling finishes. Keep-alive comments hold the connection open while it does.
- **`/query` does not move.** Its bodies, status codes and audit rows are byte-for-byte what they are today. `/v1`'s error format is scoped to `/v1`.

## 3. Target Users

**Integrating Developer (coding agent).** Runs Aider, Continue or a script on the OpenAI SDK. They want to change two environment variables and keep working. When the harness refuses something, they need the client to show *why* (duplicate, pattern, limit, model) and *not* loop. Technical level: high. Pain point today: no way in without writing a client.

**Platform Operator.** Owns `.env`, Caddy and the OpenRouter key. They need `/v1` behind the same Caddy route, the OpenRouter key never handed to a client, and the same settings (`MODEL_ALLOWLIST`, usage limits, PII and pattern files) to govern it with no second configuration.

**Security/Compliance Admin.** Reads the audit and the console. They need `/v1` rows to be as complete as chat rows: who, which door, which profile, how big, what it cost, whether it streamed, and which client parameters were ignored. They need the break-glass token to stay off this door.

**End User (Employee).** Uses the chat UI. Nothing changes for them.

**Tool-calling implementer** (internal, PRE-PRD-016). Needs the request schema, the parameter classification and the SSE writer shaped so that admitting `tools` later is a widening, not a rewrite.

## 4. MVP Scope

### In Scope

**Upstream client (additive)**
- [ ] `OpenRouterResult.finish_reason` (optional), read from `choices[0].finish_reason`
- [ ] `OpenRouterError.upstream_status` (optional) and `OpenRouterError.retryable`, set by the client from the failure it saw
- [ ] `OPENROUTER_BASE_URL` setting (default `https://openrouter.ai/api/v1`), so E2E stories can run against a local stub; `https` required unless the host is loopback

**Ingress**
- [ ] `POST /v1/chat/completions`, non-streaming and `stream: true`
- [ ] `GET /v1/models`, from `MODEL_ALLOWLIST`, behind `query:submit`
- [ ] Identity from `Authorization: Bearer` through the existing `require_permission(PERMISSION_QUERY_SUBMIT)`; `ADMIN_TOKEN` refused on every `/v1` route
- [ ] Device from the `X-Harness-Device` header; the body's `user` field ignored for identity (D1)
- [ ] `profile="code"`, `ingress="v1"`, `streamed=<request.stream>` at the one call site

**Request translation**
- [ ] `messages` through `normalize_messages`; `developer` role mapped to `system`; per-message `name` ignored
- [ ] Structure checked at the edge (non-empty, no `tool` turn, last turn `user`), so `InvalidConversationError` stays unreachable
- [ ] Parameter classification: forward, ignore-and-record, reject (D3, Section 7.3)
- [ ] `tools`, `tool_choice`, `functions`, `function_call` present and non-empty → 400 `tools_not_supported`
- [ ] `max_completion_tokens` accepted as `max_tokens`

**Response translation**
- [ ] Success → `chat.completion` with `id`, `object`, `created`, `model`, `choices[0]`, `usage`
- [ ] Six verdicts → OpenAI error objects, 400 or 403, harness `code` and details (D2, Section 7.5)
- [ ] Upstream and internal faults → 502 / 500 error objects with deliberate retry semantics (D7)
- [ ] 401 and request-validation failures on `/v1` as error objects, not FastAPI's `{"detail": …}`

**Streaming**
- [ ] Buffered SSE: chunk sequence, `[DONE]`, `stream_options.include_usage`
- [ ] Real status codes for every block decided before the upstream call, on streamed requests too (D8)
- [ ] Keep-alive comment lines while the upstream call runs
- [ ] A post-commit failure (upstream, output redaction) as an SSE `error` event, then end of stream

**Audit**
- [ ] One additive column, `audit_logs.ignored_params`, written on every arm for `/v1` and exposed on `/audit`
- [ ] The built-in `code` profile gains `assistant: flag` (D9); `examples/patterns.yaml` updated to match

**Validation**
- [ ] A local stub upstream for E2E runs
- [ ] E2E stories: OpenAI Python SDK, Aider, Continue, with pinned client versions
- [ ] Caddy routes `/v1/*`; Docker smoke
- [ ] README: the section moves from Roadmap to Features and the API Reference, with per-client setup

### Out of Scope

- [ ] Tool calling: `tools`, `tool_calls`, `tool` turns (PRE-PRD-016)
- [ ] Real token streaming; any byte released before checks finish
- [ ] `/v1/completions` (legacy), embeddings, images, audio, moderations, the Responses API, Assistants
- [ ] Image or audio content parts (a non-text part is a 400, as the normalizer already decides)
- [ ] BYOK on `/v1`: no field or header carries an OpenRouter key
- [ ] Model aliasing or prefix matching (D4)
- [ ] Returning the earlier answer on a duplicate (D5)
- [ ] Widening `GenerationParams` past its four fields (PRD-010 T5)
- [ ] A `/v1` chat session or transcript: `/v1` writes no `chat_sessions` or `chat_messages` rows; `session_id` stays NULL and `conversation_key` groups the turns (PRD-013)
- [ ] Admin console changes. The Register already shows `ingress` and `profile`
- [ ] A request body size cap separate from `CONTEXT_MAX_CHARACTERS` (Section 13)

## 5. User Stories

1. **As an Integrating Developer, I want to point the OpenAI SDK at the harness by changing base URL and key, so that my existing code works unchanged.**
   *Example:* `OpenAI(base_url="http://localhost:8000/v1", api_key=HARNESS_TOKEN).chat.completions.create(model="openai/gpt-4o", messages=[...])` returns a `ChatCompletion` whose `choices[0].message.content` is the answer, and `id` is `chatcmpl-harness-1842`, which is audit row 1842.

2. **As an Integrating Developer, I want a blocked prompt to raise an ordinary API error that names the reason, so that I see what happened instead of my agent retrying.**
   *Example:* a prompt containing `ignore previous instructions` raises `openai.BadRequestError` with `code == "suspicious_pattern"` and message `Suspicious pattern detected: ignore previous instructions`. One audit row, one request: the SDK does not retry.

3. **As an Integrating Developer using Aider, I want streaming to work, so that I can use the client with its default settings.**
   *Example:* Aider streams by default. The harness holds the response, emits `: keep-alive` while the model answers, then sends the whole edit as one chunk, a finish chunk and `[DONE]`. Aider applies the edit.

4. **As an Integrating Developer, I want my client to discover which models I may use, so that its model picker shows only usable names.**
   *Example:* `GET /v1/models` with a `user`-role token returns the four entries in `MODEL_ALLOWLIST`. Asking for a model not in the list returns 403 `model_not_permitted`, not a 404 that a client might treat as a typo to auto-correct.

5. **As an Integrating Developer, I want a parameter the harness cannot honour to be refused by name, so that I am not given a different answer than I asked for.**
   *Example:* `n=3` is a 400 with `param: "n"`, `code: "unsupported_parameter"`. `tools=[...]` is a 400 `tools_not_supported`. `seed=7` is accepted, not forwarded, and the row records `ignored_params = "seed"`.

6. **As a Platform Operator, I want the usage limits to hold on `/v1` as they do on `/query`, without a 429 my clients retry, so that a looping agent stops.**
   *Example:* over the daily budget, the SDK raises `PermissionDeniedError` with `code: "usage_limit_exceeded"`, and the error carries `limit: "tokens"` and `resets_at: "2026-10-22 00:00:00"`. Aider shows it and stops.

7. **As a Security/Compliance Admin, I want `/v1` rows to be as complete as chat rows, so that agent traffic is as reconstructable as human traffic.**
   *Example:* an Aider session's twelve requests are twelve rows with `ingress='v1'`, `profile='code'`, `streamed=1`, one `conversation_key`, the `X-Harness-Device` value as `device`, and `ignored_params` naming what Aider sent that was not forwarded.

8. **As a Security/Compliance Admin, I want the break-glass token refused on `/v1`, so that it cannot be left in an agent config.**
   *Example:* `ADMIN_TOKEN` as the bearer on `/v1/chat/completions` returns 403 `break_glass_not_permitted` and writes the refusal row PRD-013 defined. On `/v1/models` it returns the same 403 with no row (no pipeline ran).

## 6. Core Architecture & Patterns

### 6.1 Where it sits

```
client (OpenAI SDK / Aider / Continue)
   │  POST /v1/chat/completions   Authorization: Bearer <harness token>
   ▼
Caddy  (/v1/* → backend, new route)
   ▼
app/routers/v1.py
   ├─ require_permission(query:submit)  → Identity            (existing)
   ├─ break-glass guard for /v1/models                         (new, router-level)
   ├─ v1_translate.translate_request(body)                     (new, pure)
   │     → messages, GenerationParams, model, stream, include_usage, ignored_params
   │     → or V1RequestError → 400, no audit row
   ├─ run_in_pipeline(run_conversation,                        (existing executor)
   │       identity, messages, device, model, None, params,
   │       call_openrouter=<signalling wrapper>,
   │       profile="code", ingress="v1", streamed=stream,
   │       ignored_params=ignored_params)
   └─ v1_translate.translate_result(result) → ChatCompletion | V1Error
         └─ v1_sse.stream(...) when stream=true
```

No new pipeline step. `run_conversation` is called exactly as `ChatState` calls it, with three different keyword arguments and one new one.

### 6.2 Directory structure

```
app/
  routers/
    v1.py                  # NEW  POST /v1/chat/completions, GET /v1/models, /v1 error handlers
  models/
    v1_schemas.py          # NEW  pydantic request/response/error/chunk models
  services/
    v1_translate.py        # NEW  pure: request → pipeline args, result → response / error
    v1_sse.py              # NEW  buffered SSE writer: commit rule, keep-alive, chunks, error event
    openrouter_client.py   # +finish_reason, +upstream_status/retryable, base URL from settings
    query_pipeline.py      # +ignored_params keyword, threaded to every arm
    pattern_config.py      # code profile: +assistant: flag
    audit_logger.py        # +ignored_params
  db/
    models.py, database.py # +audit_logs.ignored_params, converged by init_db()
  main.py                  # include v1 router
examples/patterns.yaml     # code profile matches the built-in again
scripts/stub_openrouter.py # NEW  scripted Chat Completions upstream for E2E
Caddyfile                  # +/v1/* in @backend_routes
tests/
  test_v1_schemas.py, test_v1_translate_request.py, test_v1_translate_result.py,
  test_v1_router.py, test_v1_errors.py, test_v1_models.py, test_v1_sse.py,
  test_v1_query_isolation.py, test_e2e_openai_sdk.py, ...
```

### 6.3 Patterns this PRD follows

- **The call site names the door and the profile.** PRD-011 Section 6.6 and PRD-013 Section 6.9: `profile` and `ingress` are keyword arguments chosen by the router, never by a request field. `tests/test_query_pipeline_audit_fields.py` scans production call sites; the `/v1` call site passes `ingress="v1"` explicitly, as every other one does.
- **Required on `_deny`, defaulted on `log_query`.** `ignored_params` follows the rule PRD-008/009/012/013 set for `session_id`, `dedup_key`, `profile` and `ingress`: required on `_deny` so a forgotten arm is a `TypeError`, threaded explicitly to every `log_query` call in `run_conversation`, and covered by the existing call-site scan.
- **Additive columns only, converged by `init_db()`** (PRD-007, PRD-013). `ignored_params` is nullable TEXT, never backfilled.
- **Pure translation modules.** `v1_translate` has no I/O and no settings reads beyond what it is passed, like `app/models/messages.py`. Every mapping is unit-tested without an app.
- **Off the event loop.** The pipeline runs on the dedicated executor via `run_in_pipeline` (PRD-010 STORY-006). The SSE writer's keep-alive loop is on the event loop and never blocks it.
- **Error messages name the location and the rule, never the value** (`MessageNormalizationError`). A 400 body never echoes message content.
- **Characterize before moving.** The `/query` outcome regression (`tests/test_query_outcomes_regression.py`) runs unchanged; a new isolation test proves the `/v1` handlers do not change `/query`'s 401/422/500 bodies.

### 6.4 The commit rule for streamed requests (D8)

Once an SSE response's `200` and headers are sent, a status code can no longer say "blocked". But every verdict the pipeline reaches — authorization, break-glass, usage, context limit, duplicate, pattern, redaction limit — is decided **before step 7**, the upstream call. Only an upstream failure and an output-redaction failure come after it.

The router uses that. It passes `run_conversation` a wrapper around `call_openrouter` that sets a `threading.Event` and then calls the real client. `call_openrouter` is already injectable for exactly this kind of use, and the pipeline does not change. The router then waits for whichever comes first:

| First event | Meaning | Response |
|---|---|---|
| Pipeline returns or raises, event unset | A verdict or a pre-upstream fault | Ordinary JSON response with its real status (400/403/500). Same body as non-streaming. No SSE |
| Event set | Every content check passed; the model is being called | Commit `200 text/event-stream`. Send `: keep-alive` every `V1_SSE_KEEPALIVE_SECONDS` until the pipeline finishes, then the chunks or an `error` event |

The wrapper calls the real client with the same arguments, and its signature accepts `params=` only when given, so the "stubs have signature (messages, model, api_key)" rule (PRD-010 STORY-005) still holds.

## 7. Tools/Features

### 7.1 `POST /v1/chat/completions` — request

Pydantic model with `extra="allow"`, so unknown keys survive to classification instead of disappearing at parse time.

| Field | Handling |
|---|---|
| `model` | Required string. Passed to `run_conversation`; `authorize_model` decides (exact match, D4) |
| `messages` | Required list. `developer` → `system`, then `normalize_messages`. Then edge checks: non-empty, no `tool` role, last role `user`. Each failure → 400 `invalid_messages`, `param: "messages[i]..."` |
| `stream` | Bool, default false. Selects SSE and sets `streamed` |
| `stream_options` | `include_usage` honoured on streamed requests; other keys ignored and recorded |
| `temperature`, `top_p`, `max_tokens`, `stop` | Forwarded through `GenerationParams.from_mapping`. A range failure → 400 `invalid_parameter`, `param` set |
| `max_completion_tokens` | Forwarded as `max_tokens`. Both present and different → 400 `invalid_parameter` |
| `n` | `1` or absent accepted; anything else → 400 `unsupported_parameter` |
| `logprobs`, `top_logprobs` | `false`/`null`/absent accepted; otherwise 400 `unsupported_parameter` |
| `response_format` | `{"type": "text"}` or absent accepted; `json_object`, `json_schema` → 400 `unsupported_parameter` |
| `tools`, `tool_choice`, `functions`, `function_call` | Absent, `null` or `[]` accepted (and `tool_choice: "none"`); otherwise 400 `tools_not_supported` |
| `modalities`, `audio` | Absent or `["text"]` accepted; otherwise 400 `unsupported_parameter` |
| `user` | Ignored for identity and device (D1); name recorded |
| Everything else (`seed`, `presence_penalty`, `frequency_penalty`, `logit_bias`, `metadata`, `store`, `parallel_tool_calls`, `service_tier`, `reasoning_effort`, `prediction`, unknown keys) | Ignored; names recorded in `ignored_params` |

`openrouter_api_key`, `session_id` and `user_id` are not fields of this schema; if sent, they are unknown keys and ignored like any other. BYOK is out (Section 4).

### 7.2 Identity and device

- **Identity:** `require_permission(PERMISSION_QUERY_SUBMIT)`, unchanged. A missing or invalid bearer is 401 `invalid_api_key` (Section 7.5).
- **Break-glass:** the pipeline's step 2b refuses `ingress="v1"` already and writes the refusal row. `GET /v1/models` runs no pipeline, so the router refuses `identity.break_glass` there itself, with no row. `BREAK_GLASS_INGRESSES` cannot contain `v1` (validator, PRD-013).
- **Device:** `X-Harness-Device` header, stripped, at most 128 printable characters; longer or non-printable → 400 `invalid_header`. Absent → `device=None`.

### 7.3 Parameter classification (D3)

One table in `v1_translate`, three sets: `FORWARDED`, `REJECTED_UNLESS_DEFAULT` (with the accepted default per key) and everything else ignored. A test asserts that every `GenerationParams` field is in `FORWARDED` and nothing else is, so widening the upstream surface means changing PRD-010's allowlist, deliberately.

`ignored_params` is the sorted, comma-joined list of ignored top-level key **names**, plus `stream_options.<key>` for ignored sub-keys. Never values. `NULL` when nothing was ignored, and on every `/query` and chat row.

### 7.4 Success translation

```json
{
  "id": "chatcmpl-harness-1842",
  "object": "chat.completion",
  "created": 1792569600,
  "model": "openai/gpt-4o",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "…"},
    "logprobs": null,
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 812, "completion_tokens": 96, "total_tokens": 908},
  "harness": {"audit_id": 1842, "pii_redacted": false, "pii_entities_masked": []}
}
```

- `id` is derived from `audit_id`, so a client log line leads to the row. Also sent as the `X-Harness-Audit-Id` header.
- `model` is `QuerySuccessResponse.model_used` (the requested name, as the client sets it).
- `finish_reason` is the upstream's (`stop`, `length`, `content_filter`), `"stop"` if the upstream omitted it. `length` matters: Aider reacts to it.
- `usage.prompt_tokens` / `completion_tokens` are the upstream's split. When the provider omitted the split, they are `0` and `total_tokens` is still the reported total. The audit row keeps `NULL` for the split, which stays the truth. Emitting the keys avoids crashing clients that compute cost from them.
- `harness` is an extension object. The OpenAI SDK keeps unknown fields (`model_extra`); clients that do not know it ignore it.
- `content` is the response as step 8 left it: unmasked under `code` by default (PRD-012 D1), masked if `PII_CODE_REDACT_OUTPUT=true`.

### 7.5 Error translation (D2, D7)

Every error body has the OpenAI shape, plus a `harness` object with the pipeline response's own fields:

```json
{
  "error": {
    "message": "Usage limit reached: tokens 1000412 of 1000000; resets at 2026-10-22 00:00:00",
    "type": "permission_error",
    "param": null,
    "code": "usage_limit_exceeded",
    "harness": {"reason": "Usage limit reached", "limit": "tokens", "maximum": 1000000,
                "actual": 1000412, "resets_at": "2026-10-22 00:00:00"}
  }
}
```

| Source | Status | `type` | `code` | Retry |
|---|---|---|---|---|
| `QueryBlockedDuplicateResponse` | 400 | `invalid_request_error` | `duplicate_request` | no |
| `QueryBlockedSuspiciousResponse` | 400 | `invalid_request_error` | `suspicious_pattern` | no |
| `QueryBlockedContextLimitResponse`, `messages` / `characters` | 400 | `invalid_request_error` | `context_length_exceeded` | no |
| `QueryBlockedContextLimitResponse`, `redaction_characters` | 400 | `invalid_request_error` | `redaction_limit_exceeded` | no |
| `QueryBlockedForbiddenResponse`, `query:model:*` | 403 | `permission_error` | `model_not_permitted` | no |
| `QueryBlockedForbiddenResponse`, `ingress:break_glass` | 403 | `permission_error` | `break_glass_not_permitted` | no |
| `QueryBlockedForbiddenResponse`, other permission | 403 | `permission_error` | `permission_denied` | no |
| `QueryBlockedUsageLimitResponse` (`requests`, `tokens`) | 403 | `permission_error` | `usage_limit_exceeded` | no |
| Request translation failure (Section 7.1) | 400 | `invalid_request_error` | `invalid_messages`, `invalid_parameter`, `unsupported_parameter`, `tools_not_supported`, `invalid_header` | no |
| Request body not JSON / schema failure | 400 | `invalid_request_error` | `invalid_request` | no |
| Missing/invalid bearer | 401 | `authentication_error` | `invalid_api_key` | no |
| Missing `query:submit` (dependency) | 403 | `permission_error` | `permission_denied` | no |
| `OpenRouterError`, `retryable=True` (timeout, connect error, upstream 5xx, upstream 429) | 502 | `api_error` | `upstream_unavailable` | yes |
| `OpenRouterError`, `retryable=False` (upstream 4xx, malformed response, null content, missing key) | 502 | `api_error` | `upstream_error` | no |
| `DuplicateCheckError`, `UsageLimitError` (storage) | 500 | `api_error` | `internal_error` | yes |
| `PiiRedactorError` | 500 | `api_error` | `redaction_failed` | no |

- **"Retry: no"** means a status the OpenAI SDK does not retry (400/401/403) or, for 5xx, the `x-should-retry: false` header, which the Stainless-generated OpenAI SDKs honour ahead of their status-code rule. Every non-retryable response carries the header, so the rule is one rule. The OpenAI SDK story verifies the header against the pinned version.
- **Never `429`** (PRD-013 D5): every SDK retries it.
- **`context_length_exceeded`** is OpenAI's own code for the same condition, so clients that already handle it (Aider prints its token advice) do.
- **Messages** are `reason` plus the response's details (`: <pattern>`, `first seen <first_query_at>`, `messages 140 > 100`). The upstream error's message is the client's own `OpenRouterError` text, which names the HTTP failure and never the provider's response body.
- **Retrying a 5xx is safe for the duplicate check:** every fault row is `success=False`, which the duplicate lookup excludes (PRD-009 Section 6.3). It does count toward the rate limit (PRD-013 D7), which is intended.

The `/v1` exception handlers are registered on the app but return the OpenAI shape **only for paths under `/v1/`**; for every other path they delegate to FastAPI's default handlers. `test_v1_query_isolation.py` pins `/query`'s 401, 403, 422 and 500 bodies.

### 7.6 Buffered SSE

After commit (Section 6.4), the stream is:

```
: keep-alive                                  (every V1_SSE_KEEPALIVE_SECONDS while the pipeline runs)

data: {"id":"chatcmpl-harness-1842","object":"chat.completion.chunk","created":…,"model":"…",
       "choices":[{"index":0,"delta":{"role":"assistant","content":"<whole response>"},"finish_reason":null}]}

data: {…,"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: {…,"choices":[],"usage":{"prompt_tokens":812,"completion_tokens":96,"total_tokens":908}}   (only with include_usage)

data: [DONE]
```

- **One content chunk** (D6). A configurable chunk size is Section 13.
- **A failure after commit** (upstream, output redaction) is one event, `data: {"error": {…same object as Section 7.5…}}`, then the stream ends without `[DONE]`. The OpenAI Python SDK raises `APIError` on a `data` object with an `error` key. A mid-stream error is not retried by any SDK, which is acceptable for these two: the row is already written.
- **Headers:** `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`, `X-Harness-Audit-Id` is not sent (the id is unknown at commit time; it is in every chunk's `id`).
- **Client disconnect:** the pipeline keeps running on its executor thread to completion. The row is written and the tokens charged, as for any answered request. The writer stops sending and logs nothing extra.
- **Caddy:** `encode gzip` must not buffer `text/event-stream`. Caddy's encoder flushes on SSE responses; the Docker smoke story verifies keep-alives arrive through Caddy at their interval.

### 7.7 `GET /v1/models`

```json
{"object": "list", "data": [
  {"id": "openai/gpt-4o", "object": "model", "created": 0, "owned_by": "openai"},
  {"id": "gpt-4", "object": "model", "created": 0, "owned_by": "harness"}
]}
```

- `query:submit` required; break-glass refused (403, no row).
- Entries are `settings.model_allowlist_list`, in order. `owned_by` is the prefix before `/`, else `harness`. `created` is `0`: the harness does not know it.
- A role in `MODEL_ALLOWLIST_WILDCARD_ROLES` (`admin`) may request any model, but the list cannot enumerate "any", so it returns the same entries. Documented.
- `GET /v1/models/{id}`: returns the entry, or 404 `model_not_found` for a name not in the list. Some clients call it on startup.
- Not audited. It reveals only configuration the caller is already held to.

### 7.8 The `code` profile on this ingress (D9)

`/v1` is the first caller to pass `profile="code"`, and the first to send caller-written `system` and `assistant` turns (PRD-010 T3). The built-in matrix becomes:

| Role | `chat` | `code` (before) | `code` (this PRD) |
|---|---|---|---|
| `user` | block | block | block |
| `system` | — | — | — (the client's own prompt; PRD-011 6.4) |
| `assistant` | — | — | **flag** |
| `tool` | — | flag | flag (unreachable until PRE-PRD-016) |

A caller who writes an injection phrase into an `assistant` turn to get past the `user` block is now recorded (`pattern_role='assistant'`, `pattern_action='flag'`) instead of invisible. It is `flag`, not `block`, because a real agent's history contains the model's own answers, which may quote such phrases. Under `code`, only the `injection` list is loaded, so ordinary source vocabulary does not flag. PII already covers `assistant` prose under `code` (PRD-012). A deployment that distrusts its clients' system prompts adds `system: block` to its own file.

### 7.9 Stub upstream (E2E)

`scripts/stub_openrouter.py` is a small HTTP server speaking enough Chat Completions for the E2E stories: it answers from a script file (request predicate → response content, `finish_reason`, `usage`), can delay, and can fail with a chosen status. The harness reaches it through `OPENROUTER_BASE_URL=http://127.0.0.1:<port>`. It exists because outbound OpenRouter calls fail from the development machine, and because an E2E test of Aider needs a model that answers with a specific edit. It is a test tool, not shipped behaviour.

## 8. Technology Stack

**Backend (unchanged stack):** Python, FastAPI, uvicorn, pydantic v2, pydantic-settings, httpx, as in `requirements.txt`. SSE uses Starlette's `StreamingResponse`; no new runtime dependency.

**Storage:** libSQL / Turso through the existing driver (`libsql==0.1.11`). One added column.

**Edge:** Caddy (`Caddyfile`), one route added.

**Test-only dependencies** (a separate requirements file for E2E, not `requirements.txt`):
- `openai` (Python SDK), pinned to the version current when its story runs
- `aider-chat`, pinned likewise
- Continue: the CLI if the pinned version has a headless mode, else the VS Code extension at a pinned version with a recorded manual run

Versions are pinned in the story that first uses them and recorded in its report, not guessed here (pre-PRD risk "standard drift").

**Existing constraints that apply:**
- The OpenRouter call stays behind `GenerationParams`' four fields (PRD-010 T5).
- The pipeline runs on the dedicated executor, sized by `PIPELINE_MAX_WORKERS` (default 32). A buffered `/v1` request holds one worker for its whole upstream call, as `/query` does.
- Test output is ASCII-only (Windows console is cp1252); DB-backed tests carry the `db` marker (PRD-014, the test-suite PRD).

## 9. Security & Configuration

### 9.1 Authentication and authorization

- Harness bearer tokens only. The OpenRouter key never leaves the process and no `/v1` field accepts one.
- `query:submit` on both routes. Model permission through `authorize_model`, unchanged.
- `ADMIN_TOKEN` refused on every `/v1` route. The setting cannot change this (PRD-013 D4).

### 9.2 Threats

| # | Threat | Treatment |
|---|---|---|
| T1 | Caller forges `assistant` turns to smuggle an injection past the `user` block (PRD-010 T3) | **Flagged** under `code` (D9). Not blocked. What the model may *do* is PRE-PRD-015's |
| T2 | Caller's own `system` turn carries an injection | **Not inspected** by default: it is the caller's own prompt (PRD-011 6.4). A deployment can add `system: block` |
| T3 | Caller varies the history prefix to re-ask a duplicate (PRD-010 T4) | **Accepted.** The rate limit and budget (PRD-013) bound it |
| T4 | Caller picks the permissive profile or ingress | **Impossible:** no field carries either. Test: a body with `profile`, `ingress` keys records them as ignored and runs `code`/`v1` |
| T5 | Parameter smuggling widens the upstream request | **Impossible:** only `GenerationParams` reaches the client. Test: every non-forwarded key is absent from the upstream body (characterization from PRD-010 STORY-003) |
| T6 | Error bodies leak content or PII | Messages name locations and rules, never values; upstream errors never echo the provider body. The matched `pattern` is returned, as on `/query` |
| T7 | A retry storm from a client that treats a verdict as transient | No verdict is `429`/`5xx`; non-retryable 5xx carry `x-should-retry: false`. E2E stories count audit rows per blocked request (exactly one) |
| T8 | Partial response released before checks | Nothing is written to the socket after commit except comments until step 8 finishes (Section 7.6) |
| T9 | Shape refusals (Section 7.1) are not audited | **Accepted**, as `/query`'s 422 is not. They reach no pipeline step and no model. Logged at INFO with user id and `code`, never content |
| T10 | `OPENROUTER_BASE_URL` pointed at an attacker host captures the key | Operator-only setting; validator requires `https` unless the host is loopback. Documented beside `OPENROUTER_API_KEY` |

### 9.3 New settings

| Setting | Default | Validation | Purpose |
|---|---|---|---|
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | `https://`, or `http://` with host `127.0.0.1` / `localhost` / `::1`; no trailing path past `/v1` required | Upstream base; `/chat/completions` appended |
| `V1_ENABLED` | `true` | bool | Mount `/v1` at all. Off: routes are not included and `/v1/*` is 404 |
| `V1_SSE_KEEPALIVE_SECONDS` | `10` | `> 0`, `<= 60` | Interval between `: keep-alive` lines |

No setting chooses the `/v1` profile. It is the literal `"code"` at the call site (PRD-011 D2), and `pattern_config.get_profile` proves it exists at startup.

### 9.4 Out of scope (security)

Mutual TLS, per-client IP allowlists, request signing, and a body-size cap (Section 13). Caddy terminates TLS as today.

## 10. API Specification

| Route | Auth | Success | Errors |
|---|---|---|---|
| `POST /v1/chat/completions` | Bearer, `query:submit` | 200 `chat.completion` (JSON) or 200 `text/event-stream` | Section 7.5 |
| `GET /v1/models` | Bearer, `query:submit` | 200 list | 401, 403 |
| `GET /v1/models/{id}` | Bearer, `query:submit` | 200 model | 401, 403, 404 `model_not_found` |

**Request headers:** `Authorization: Bearer <harness token>` (required), `X-Harness-Device` (optional), `Content-Type: application/json`.

**Response headers:** `X-Harness-Audit-Id` on non-streamed success; `x-should-retry: false` on every non-retryable error.

**`/audit` change:** `AuditQueryEntry.ignored_params: Optional[str] = None`, unvalidated, for `session_id`'s reasons. No `/stats` change.

**Unchanged:** `POST /query`, `/audit` (other fields), `/stats`, `/health`, the chat UI, the console.

Client configuration (README, Section 12 Phase 4):

```bash
# OpenAI SDKs, Aider (via its OpenAI-compatible provider)
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_API_KEY=<harness token — never the OpenRouter key>
```

```yaml
# Continue (config.yaml)
models:
  - name: harness-gpt-4o
    provider: openai
    model: openai/gpt-4o
    apiBase: http://localhost:8000/v1
    apiKey: <harness token>
    roles: [chat, edit]
```

## 11. Success Criteria

### MVP definition

The OpenAI Python SDK, Aider and Continue each complete a text task through the harness with only base URL and key changed; every block surfaces as a non-retried error naming its reason; and `/query` is unchanged.

### Functional requirements

- [ ] OpenAI Python SDK, non-streaming: `ChatCompletion` with content, `usage`, `finish_reason`, `id == f"chatcmpl-harness-{audit_id}"`
- [ ] OpenAI Python SDK, streaming: chunks reassemble to the same content; `include_usage` yields the usage chunk; `[DONE]` ends it
- [ ] A suspicious prompt raises `BadRequestError` with `code == "suspicious_pattern"`, streamed and not; exactly one audit row, one HTTP request (SDK `max_retries` at its default)
- [ ] Duplicate → 400 `duplicate_request`; context → 400 `context_length_exceeded`; model → 403 `model_not_permitted`; usage → 403 `usage_limit_exceeded`; break-glass → 403 `break_glass_not_permitted`, each with its `harness` details, streamed and not
- [ ] A block decided before the upstream call returns its real status on a `stream: true` request, never a 200 stream
- [ ] A retryable upstream failure is retried by the SDK and each attempt writes one `success=False` row; a non-retryable one is not retried
- [ ] Keep-alive lines arrive at `V1_SSE_KEEPALIVE_SECONDS` while a stub upstream delays 30 s, directly and through Caddy
- [ ] `tools` non-empty → 400 `tools_not_supported`, no row, nothing upstream; `n=2` → 400 `unsupported_parameter`; `seed` → answered, `ignored_params='seed'`
- [ ] `developer` turn reaches upstream as `system`; an image content part is 400 `invalid_messages`
- [ ] `GET /v1/models` lists `MODEL_ALLOWLIST`; `ADMIN_TOKEN` → 403
- [ ] Aider applies a scripted edit to a sample repository through the harness and the stub upstream
- [ ] Continue chat returns an answer through the harness (CLI run or recorded manual run)
- [ ] Every row a `/v1` request writes has `ingress='v1'`, `profile='code'`, `streamed` equal to the request's flag; a flagged answer writes two rows (PRD-011), every other verdict one, a shape refusal none
- [ ] An injection phrase in an `assistant` turn is answered and recorded with `pattern_role='assistant'`, `pattern_action='flag'`
- [ ] No upstream request body contains a key outside `model`, `messages` and `GenerationParams`' four fields

### Quality indicators

- [ ] `/query` outcome regression, chat UI regression and console suites pass with no assertion changed
- [ ] `test_v1_query_isolation.py`: `/query`'s 401/403/422/500 bodies byte-identical to `main`
- [ ] The call-site scans (`test_query_pipeline_audit_fields.py`, `test_query_pipeline_pii_profiles.py`) cover `ignored_params` and the `/v1` call site
- [ ] `examples/patterns.yaml` loads to `BUILT_IN_POLICY` (existing test, updated expectation)
- [ ] `-m "not db"` runs without Docker; ASCII-only test output
- [ ] Added `/v1` overhead over `/query` for the same conversation, measured with the stub upstream: p95 under 10 ms for translation, reported in the README

## 12. Implementation Phases

### Phase 1 — Foundations (no route yet)
**Goal:** everything the router needs exists and is tested by direct call.
**Deliverables:** `finish_reason`, `upstream_status`/`retryable` and `OPENROUTER_BASE_URL` on the client; `V1_*` settings with validators; `v1_schemas`; `v1_translate.translate_request` (messages, parameters, tools refusal); `ignored_params` column through `log_query`, `_deny` and every arm; `code` profile `assistant: flag` and `examples/patterns.yaml`.
**Validation:** unit tests; the call-site scans extended; existing suites green unchanged.

### Phase 2 — Non-streaming endpoint
**Goal:** `POST /v1/chat/completions` (non-streaming) and `GET /v1/models` answer correctly over HTTP.
**Deliverables:** `app/routers/v1.py`; success translation; verdict → error translation; upstream and internal fault mapping with `x-should-retry`; `/v1`-scoped 401/422 handlers; `/v1/models`.
**Validation:** `TestClient` tests per outcome with an injected `call_openrouter`; `/query` isolation test; audit rows checked per outcome.

### Phase 3 — Buffered SSE
**Goal:** `stream: true` works, and blocks keep their status codes.
**Deliverables:** `v1_sse` (commit rule via the signalling wrapper, keep-alive, chunk sequence, `include_usage`, post-commit error event, disconnect behaviour).
**Validation:** async tests with a slow and a failing stub; a test per pre-upstream verdict that a streamed request gets JSON with its status; keep-alive timing test.

### Phase 4 — Real clients, deployment, documentation
**Goal:** the success criteria hold for real clients, through Caddy.
**Deliverables:** stub upstream; E2E stories for the OpenAI SDK, Aider and Continue with pinned versions; Caddy route and Docker smoke; README (section moves from Roadmap to Features and API Reference, per-client setup, what `/v1` does not do); `.env.example`; latency measurement; regression sweep.
**Validation:** each E2E story's report records the client version, the command run and the audit rows produced.

## 13. Future Considerations

- **Tool calling** (PRE-PRD-016): admits `tools`, `tool_calls` and `tool` turns; sets `has_tool_calls`. The classification table and SSE writer are where it widens.
- **Action policy** (PRE-PRD-015): what a tool call may do, which T1's flag cannot decide.
- **Configurable chunk size** for SSE, if a client renders one large chunk badly.
- **Real token streaming** with a post-hoc kill switch, if a safe design for releasing unchecked output exists. It does not today.
- **Model aliasing** (`gpt-4o` → `openai/gpt-4o`) for clients with fixed model names.
- **Per-role profile override** (PRD-011 D2's deferred half), now that a second profile has an ingress.
- **A request body size cap** at Caddy or in the app, ahead of JSON parsing.
- **Auditing shape refusals** (T9), if operators want to see agents sending `tools` before PRE-PRD-016 ships.
- **Recording the `user` field**, if a deployment wants client-reported end-user ids beside the authenticated one.
- **OpenCode and Cline** in agent mode, which need tool calling (Milestone 2).

## 14. Risks & Mitigations

| # | Risk | Likelihood / Impact | Mitigation |
|---|---|---|---|
| 1 | **A client times out waiting for the first byte** on a long buffered answer | Medium / High | Keep-alive comments from commit onward; non-streaming clients already wait for the whole body. E2E stories run a 30 s stub delay through Caddy |
| 2 | **A client sends `tools` by default** (Continue, Aider in some modes) and every request is refused | Medium / High | Refusal names it (`tools_not_supported`) so the fix is visible; the per-client README setup and the E2E configs pin a text-only mode. Silent dropping is rejected on principle |
| 3 | **Clients drift from the standard** (new required fields, new roles like `developer`) | Medium / Medium | Client versions pinned in E2E stories; `extra="allow"` plus ignore-and-record keeps unknown keys from breaking parsing; `developer` mapped now |
| 4 | **`/v1` error handlers change `/query`'s bodies** | Low / High | Handlers delegate outside `/v1/`; isolation test pins `/query`'s 401/403/422/500 bodies |
| 5 | **The commit rule races**: the event fires but the pipeline then refuses | Low / Medium | Nothing after step 7 is a verdict, only a fault; faults after commit have a defined SSE error event. Tested with a failing stub after the event |
| 6 | **Agent concurrency exhausts the executor** (32 workers, each held for an upstream call) | Medium / Medium | Same exposure as `/query` today; `PIPELINE_MAX_WORKERS` is the lever; the rate limit bounds a single user. Measured in the Docker smoke |
| 7 | **E2E cannot reach a real model** from the development machine | High / Medium | The stub upstream (Section 7.9) makes every E2E deterministic; a real-model run is an optional manual check recorded in the README story |
| 8 | **`assistant: flag` floods the audit** with flag rows from agents quoting injection text | Low / Low | `code` loads only the four injection phrases; the flag is a second row only when one matches; promotion or removal is a file change |

## 15. Appendix

### Source
- Pre-PRD brief: [pre-prds/PRE-PRD-014-openai-compatible-endpoint.md](../../../pre-prds/PRE-PRD-014-openai-compatible-endpoint.md)
- Track overview: [pre-prds/README.md](../../../pre-prds/README.md). Depends on PRD-011, PRD-012, PRD-013 (all done); blocks tool calling (PRE-PRD-016).

### Decisions (resolved from the brief's open decisions)

| # | Question | Decision |
|---|---|---|
| D1 | Device: `user` field or header? | **Header `X-Harness-Device`**, as proposed. *Deviation:* `user` is ignored and only its **name** recorded in `ignored_params`; there is no column for its value, and adding one is Section 13 |
| D2 | Block status code | **400 for content verdicts** (duplicate, suspicious, context, redaction limit), **403 for policy** (permission, model, break-glass, usage). Never 429 or 5xx. As proposed, with codes per verdict (Section 7.5) |
| D3 | Unknown parameters | **Ignore and record names** in a new `ignored_params` column; **reject** those that change semantics: `n > 1`, `logprobs`, `top_logprobs`, non-text `response_format`, non-text `modalities`, `tools` and friends. As proposed, list extended (Section 7.1) |
| D4 | Model names | **Exact allowlist match**, no aliasing. As proposed |
| D5 | Duplicate returns the previous answer? | **No**, 400 `duplicate_request`, as `/query` blocks. As proposed |
| D6 | SSE chunking | **One content chunk + finish chunk** (+ usage chunk on request) + `[DONE]`. As proposed |
| D7 | *(new)* Retry semantics for faults | **Transient upstream and storage faults retryable** (502 / 500); deterministic ones carry `x-should-retry: false`. The client records `upstream_status` to tell them apart (Section 7.5) |
| D8 | *(new)* Streamed blocks | **Real status codes**: SSE is committed only once the upstream call starts, detected through the injectable `call_openrouter`. Post-commit faults are an SSE `error` event (Section 6.4) |
| D9 | *(new)* Trust for caller-supplied turns (PRD-010 T3, PRD-011 open cell) | **`system` not inspected, `assistant` flagged** under the built-in `code` profile (Section 7.8) |
| D10 | *(new)* Upstream URL | **`OPENROUTER_BASE_URL` setting**, loopback-or-https, so E2E runs against a stub (Section 9.3) |

### Assumptions
- PRDs 011–013 are merged to `main` with their documented behaviour; `ingress="v1"` and `streamed` already reach every arm.
- `X-Harness-Device` is a new convention; no client sends it by default, so most `/v1` rows will have `device=NULL` unless the operator configures custom headers (the OpenAI SDK's `default_headers`, Continue's `requestOptions.headers`).
- The `x-should-retry` header is honoured by the pinned OpenAI Python SDK; verified in its story. Other clients rely on the status code alone.
- `V1_ENABLED` defaults to `true`: an upgrade exposes `/v1` behind the same tokens and Caddy, which is the point of the track.

### Evidence (verified against `main` @ `b7e6d87`)
- `app/services/query_pipeline.py`: `Ingress = Literal["query", "chat", "v1"]`; `run_conversation(..., call_openrouter=..., *, profile=None, ingress=None, streamed=False)`; steps 2–6 return a verdict before step 7 calls `call_openrouter`; only the upstream-error and output-redaction arms follow it; `_validate_conversation` raises `InvalidConversationError` for empty, `tool` and non-`user`-last conversations.
- `app/models/messages.py`: `normalize_messages` accepts string, text-part lists and assistant `null`; rejects unknown roles (so `developer` today), `tool_calls`, and non-text parts, naming location only.
- `app/services/openrouter_client.py`: `_API_URL` hard-coded; `GenerationParams.from_mapping` allows four keys and raises `UnsupportedParameterError`; `OpenRouterResult` has no `finish_reason`; `OpenRouterError` carries only a message; `content is None` raises.
- `app/services/pattern_config.py`: built-in `code` = `injection` list only, `roles={"user": "block", "tool": "flag"}`.
- `app/config.py`: `BREAK_GLASS_INGRESSES` validator rejects `v1`; `MODEL_ALLOWLIST`; `PIPELINE_MAX_WORKERS = 32`; `OPENROUTER_TIMEOUT_SECONDS = 120.0`.
- `app/middleware/auth.py`: `HTTPBearer(auto_error=False)`; 401 `{"detail": "Invalid or missing credential"}`.
- `app/routers/query.py`: maps `DuplicateCheckError`, `UsageLimitError`, `PiiRedactorError` to 500 and `OpenRouterError` to 502.
- `Caddyfile`: `@backend_routes` lists `/query /audit /stats /health` and Reflex paths; no `/v1`.
- `tests/test_route_reservations.py`: asserts no harness route collides with Reflex's reserved routes.

### Tentative story breakdown (to be generated by `/create-stories`)
Reordered from the brief: foundations before the router; the audit column and profile change before anything writes through them; the stub upstream before the client E2E stories.

1. OpenRouter client: `finish_reason`, `upstream_status` / `retryable`, `OPENROUTER_BASE_URL` with validator (brief 4, 6)
2. `V1_ENABLED` and `V1_SSE_KEEPALIVE_SECONDS` settings with validators
3. `/v1` request, response, chunk and error schemas (brief 1)
4. Request translation: messages, `developer`, edge structure checks (brief 3)
5. Parameter classification and the explicit `tools` refusal (brief 8, 9)
6. `audit_logs.ignored_params`: column, writer, every arm, `/audit` field
7. `code` profile `assistant: flag`; `examples/patterns.yaml` (brief 11)
8. Router, identity and device; non-streaming success translation (brief 2, 4)
9. Verdict → error translation; `/v1`-scoped 401/422 handlers; `/query` isolation test (brief 5)
10. Upstream and internal fault mapping; retry semantics (brief 6)
11. `GET /v1/models` and `/v1/models/{id}` (brief 7)
12. Buffered SSE: commit rule, keep-alive, chunks, `include_usage`, post-commit error (brief 10)
13. Stub upstream for E2E
14. E2E: OpenAI Python SDK (brief 12)
15. E2E: Aider (brief 13)
16. E2E: Continue (brief 14)
17. Caddy route and Docker smoke, keep-alive through Caddy (brief 15)
18. Regression sweep, latency measurement, README API reference and per-client setup, `.env.example` (brief 16)

### Related documents
- PRD-005 (RBAC): `require_permission`, `authorize_model`, the admin wildcard
- PRD-009 (duplicate rescoping): the key over `messages`; fault rows excluded from the lookup
- PRD-010 (multi-turn pipeline): `run_conversation`, `normalize_messages`, `GenerationParams`, T3/T4/T5, the executor
- PRD-011 (pattern policy): the `code` profile, the call-site profile argument, the flag arm's second row
- PRD-012 (PII for code): the `code` PII policy; [decisions/D5-placeholders.md](../PRD-012-pii-for-code/decisions/D5-placeholders.md) is the rollout note for agents that read files containing masked values
- PRD-013 (audit and usage limits): `ingress`, `streamed`, `conversation_key`, the usage verdict, break-glass on `v1`
- PRD-014 (test-suite db isolation): the `db` marker and the Docker-free run

### Dependencies
- Depends on: PRD-011 (done), PRD-012 (done), PRD-013 (done).
- Blocks: tool calling (PRE-PRD-016).

**Skills referenced:** none. The only skill in `.agents/skills/` is `frontend-design`, and this PRD has no UI.
