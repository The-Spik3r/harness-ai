---
id: PRD-022
slug: provider-fallback-and-native-adapters
title: Provider Resilience — Native Adapters, Fallback Chains and a Provider Circuit Breaker
status: draft
base_branch: main
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
created: 2026-11-16
updated: 2026-11-16
---

> **Builds on [PRD-020 provider-registry](../PRD-020-provider-registry/PRD.md)** (draft). This PRD uses PRD-020's provider and catalogue model, its trust levels (`internal` / `external`, D5/D7), its capability fields (D6), its adapter protocol and `call_upstream` seam (D11, D12), its `UpstreamError`, and its audit columns (D13). It satisfies the four fallback rules in PRD-020 Section 6.8 (see Section 6.4 here). The registry fields and capabilities this PRD adds are labelled **PRD-022 addition** wherever they appear. It also builds on **[PRD-018 db-resilience](../PRD-018-db-resilience/PRD.md)** (draft). PRD-018 defines the breaker's state machine (D6, Section 6.5), its error carrying `retry_after_seconds` (D7), and its status reporting (D16). PRD-018's breaker is written as one storage singleton. Section 6.10 states exactly what this PRD reuses, what it generalizes, and the one edit it proposes to PRD-018 (O10).

## 1. Executive Summary

Today the harness has one upstream. `call_openrouter()` ([app/services/openrouter_client.py:219](../../../app/services/openrouter_client.py)) posts to `OPENROUTER_BASE_URL/chat/completions` ([config.py:246](../../../app/config.py)). Every failure becomes an `OpenRouterError` whose `retryable` flag `_classify_http_error` sets ([openrouter_client.py:188-197](../../../app/services/openrouter_client.py)): timeout, transport errors, 5xx and 429 are retryable; any other 4xx or a malformed body is not. The pipeline then writes one `success=False` row and re-raises ([query_pipeline.py:764-784](../../../app/services/query_pipeline.py)). `/query` answers 502 ([routers/query.py:40-41](../../../app/routers/query.py)). `/v1` answers 502 `upstream_unavailable` (retryable) or `upstream_error` (not retryable, `x-should-retry: false`) ([v1.py:198-212](../../../app/routers/v1.py), [v1_translate.py:713-718](../../../app/services/v1_translate.py)). When OpenRouter is down, the harness is down. The roadmap names this gap: "a control plane tied to one upstream is a single point of failure" ([docs/roadmap.md:32](../../../docs/roadmap.md)).

PRD-020 turns OpenRouter into one entry of a provider registry. It accepts only `type: openai_compatible`, and its startup error for any other type names this PRD (PRD-020 F1). This PRD adds three things:

1. **Native adapters**, for the cases where an OpenAI-compatible layer loses features. The first is the Anthropic Messages API (`type: anthropic`): tool use, thinking blocks, and prompt caching with honest cache-token accounting. Gemini and AWS Bedrock were evaluated and deferred (D3). The native adapter implements PRD-020's `ProviderAdapter` protocol unchanged (`complete()`, `stream()`, `collect()`).
2. **Fallback chains.** An ordered list of catalogued alternatives, per model and optionally per ingress, is tried when an upstream failure is retryable. Three rules are hard. A fallback **never automatically goes from an `internal` provider to an `external` one**, because that would send data that was never meant to leave the network. It never goes to a model the caller's role may not use. It never goes to a model that lacks a capability the request needs (D5–D7, PRD-020 6.8).
3. **A provider circuit breaker**, reusing PRD-018's primitive. It opens after consecutive failures and probes with live traffic once half-open. The chain skips any open provider. When every candidate is open, the error is retryable and carries a `retry-after` hint (D12).

**MVP goal:** OpenRouter is the primary for `anthropic/claude-sonnet-4.6`, and an Anthropic-native catalogue model is its fallback. With the stub OpenRouter killed, a `/v1` tool-calling request is answered by Anthropic, and its tool calls are decided by the action policy exactly as before. The failed attempt writes its own `success=false` row and the answering attempt writes the success row; both share one `request_id`. After 5 consecutive failures (PRD-018's threshold), OpenRouter is skipped without a network call. A chain from an `internal` model to an `external` one fails at startup unless that entry sets `allow_lower_trust: true`. `GET /providers/status` shows the breaker states. With no chain file, every request and row is byte-identical to PRD-020.

## 2. Mission

Keep answering when one provider fails, without ever sending data somewhere it was not already allowed to go.

Core principles:

- **Availability never outranks the data boundary.** A fallback that sends a prompt off-network is a data leak, even when it succeeds. Trust, RBAC and capability are checked for every candidate on every request. No outage makes the check optional (D5–D7).
- **A fallback is a retry, so it follows retry rules.** Only what `/v1` already calls retryable triggers one: transient faults. A deterministic 4xx, a malformed request and **a safety refusal** never do. Falling back on a refusal amounts to shopping for a model that complies (D8, T4).
- **Never retry after release.** Once any answer content reaches the client, the attempt has either succeeded or failed. It is never replayed elsewhere. Today's buffered stream makes this rule free; PRD-021's real-time stream makes it a rule that has to be enforced (D9).
- **One attempt, one row.** Every upstream attempt is audited as its own row with its own provider (PRD-020 6.8 rule 4). This matches what a client retry of a 503 already produces ([features.md:280](../../../docs/features.md)). A shared `request_id` keeps one query readable as one story (D10).
- **Translate, don't approximate.** A native adapter maps every field it can and fails loudly on the ones it cannot (for example, an unparseable `arguments` string in history). It never guesses (D4).
- **Off means PRD-020.** With no chain file and the breaker disabled, step 7 calls the `call_upstream` seam exactly once.

## 3. Target Users

**Platform Operator.** Owns `.env`, `PROVIDERS_FILE` (PRD-020) and the new chain file. They need to say "if OpenRouter fails, use Anthropic directly for Claude models" in a few lines. They need startup to refuse a chain that would leak `internal` traffic to an `external` provider, and one page that shows which provider is unhealthy and why.

**Integrating Developer (coding agent).** Runs OpenCode, Cline or the OpenAI SDK against `/v1`. A provider blip should cost them one slower answer, not a failed agent step. Tool calls should look the same whichever provider answered. A total outage should produce a retryable error that the SDK backs off from, not a retry storm.

**Security/Compliance Admin.** Needs every attempt row to say which provider handled it (`provider`, `upstream_model`, `provider_trust`, PRD-020 D13) and whether a fallback happened. Needs to know no fallback crossed a trust or RBAC line, and that failed attempts stay visible and are never folded away.

**PRD-020 registry and PRD-021 streaming** (internal). This PRD is the first one that registers a second adapter type. It must keep the adapter protocol PRD-021 streams through.

## 4. MVP Scope

### In Scope

**Errors and result (extending PRD-020's `app/services/upstream/`)**
- [ ] PRD-020's `UpstreamError` gains defaulted fields `provider`, `kind` (`timeout | transport | status | shape | refusal | incompatible | misconfigured | exhausted`) and `retry_after_seconds`, plus a `fallback_eligible` property. **PRD-022 addition.** The existing `upstream_status`, `retryable` and message are unchanged, and so is PRD-020's `openrouter_client.OpenRouterError` alias. `_PIPELINE_FAULTS` ([v1.py:111](../../../app/routers/v1.py)) and `_fault_code` therefore keep working (D11)
- [ ] `UpstreamResult` and `UsageReport` gain the defaulted fields `cache_read_tokens`, `cache_write_tokens` and `reasoning_blocks`. **PRD-022 addition**, following the defaulted-field precedent of PRD-013 and PRD-017

**Anthropic native adapter (`app/services/upstream/anthropic.py`, registry `type: anthropic`)**
- [ ] Registry: `type: anthropic` is accepted. Its `base_url` passes PRD-020 D5's transport rule and its key comes from `key_env`, both unchanged. **PRD-022 addition** to PRD-020's type set
- [ ] Implements PRD-020's `ProviderAdapter` exactly: `complete(request: UpstreamRequest, api_key) -> UpstreamResult` and a synchronous `stream(request, api_key) -> Iterator[UpstreamEvent]`. The pure `collect()` holds for it too: `collect(stream(r)) == complete(r)` over every stub script (PRD-020 6.4)
- [ ] Request mapping from `Message` ([models/messages.py:38-51](../../../app/models/messages.py)) to the Messages API: system hoisting, tool turns become `tool_result` blocks, `tool_calls` become `tool_use` blocks, plus `tools`, `tool_choice`, generation parameters and `max_tokens` (Section 6.5)
- [ ] Response mapping: text; `tool_use` becomes `ToolCallSpec` with canonical serialization of the input (D4); `stop_reason` becomes `finish_reason`; usage including the cache tokens
- [ ] Thinking runs when the model's PRD-020 `reasoning` capability is on. `stream()` emits PRD-021's `ReasoningDelta` for summarized thinking text, so `reasoning:view` works for Anthropic models. `complete()` and `collect()` discard it. Thinking blocks are never stored or round-tripped (D14)
- [ ] Prompt caching uses top-level automatic `cache_control` when the model sets `prompt_cache: auto` (**PRD-022 addition**)
- [ ] Uses the official `anthropic` Python SDK, pinned exactly, with `max_retries=0` and an explicit timeout, because the harness owns retries (D2)

**Fallback chains (`app/services/upstream/chain.py`, `PROVIDER_CHAINS_FILE`)**
- [ ] A strict-YAML file (`strict_yaml.safe_load`, [app/services/strict_yaml.py](../../../app/services/strict_yaml.py)) maps a catalogue model id, optionally with an ingress, to an ordered list of **catalogue model ids**. Each id resolves to its provider through PRD-020's `resolve()`, so a chain cannot name a host or an uncatalogued model (D5)
- [ ] Startup validation: every id is catalogued (not passthrough); the first candidate is the chain's own model; an `external` candidate in a chain whose primary is `internal` needs `allow_lower_trust: true`; candidates cover the primary's capabilities or are marked `capability_scoped: true`. Errors name the file, the chain and the entry (D6)
- [ ] Per-request eligibility: the route check (PRD-020's `authorize_route` per candidate), capability (`tools`, `streaming`, `max_context_tokens` from PRD-020 D6, and the PRD-022 addition `forced_tool_choice`), BYOK (chain of length 1, D15) and breaker state (D7)
- [ ] A chain deadline (`PROVIDER_CHAIN_DEADLINE_SECONDS`) bounds total time. Each attempt's timeout is the smaller of the provider's `timeout_seconds` and the time remaining (D13)
- [ ] Step 6 is recomputed for the candidate that receives the data, from the raw conversation, honouring PRD-020's `route.relaxes_input()`. It is reused only when the effective policy is identical (D16, PRD-020 6.8 rule 2)

**Circuit breaker (PRD-018's state machine, Section 6.10)**
- [ ] One instance of PRD-018's `closed → open → half_open → closed` breaker per provider, in process, with PRD-018's defaults: 5 consecutive failures, 10 s open (D6). Fallback-eligible faults count; `misconfigured` (401) force-opens it (D12, a generalization)
- [ ] Half-open admits a single probe, as PRD-018 does. The probe is the next live request, not a synthetic call (generalization: PRD-018 probes with `SELECT 1`). Other requests skip the provider until the probe finishes
- [ ] When every candidate is skipped as open, one `success=false` row is written with `error_message='all providers unavailable'`. `/v1` answers 502 `upstream_unavailable`, retryable, with `retry-after`; `/query` answers 502

**Audit and observability**
- [ ] PRD-020's five columns (`provider`, `upstream_model`, `provider_trust`, `pii_input_relaxed`, `usage_estimated`) are written **per attempt**
- [ ] New columns (**PRD-022 addition**): `request_id`, `attempt`, `route_model`, `fallback_reason`, `skipped_providers`, `cache_read_tokens`, `cache_write_tokens` (D10)
- [ ] `model_used` keeps PRD-020's meaning, the id the caller asked for. `route_model` is the catalogue id that handled the attempt
- [ ] `/v1`: `model` is the answering catalogue id; the body gains `harness.provider` and `harness.attempts`, and the response gains an `X-Harness-Provider` header (D17)
- [ ] `GET /providers/status` (`stats:read`) and `providers_status()` in-process: one PRD-018-shaped `breaker` object per provider plus process-local counters, with no network or database call (mirrors `GET /storage/status`, PRD-018 D16)
- [ ] `GET /stats`: `fallback_answers`, `failed_attempts`, `answers_by_provider`
- [ ] Admin console: a Providers panel, and `provider`/`attempt` columns on the Register (PRD-020 already adds `provider` there)
- [ ] Breaker transitions are logged at WARNING with the provider, the from and to states and the fault kind, never message text

**Stub and E2E**
- [ ] The stub upstream gains an Anthropic Messages mode (`/v1/messages`, JSON and SSE) and scripted faults: timeout, 503, 429 with `retry-after`, 401, refusal
- [ ] E2E: kill OpenRouter; Anthropic answers a tools request; the breaker opens; `/providers/status` reports it

### Out of Scope
- [ ] The provider registry itself (PRD-020) and real-time streaming (PRD-021). This PRD uses both
- [ ] Semantic, cost-based or latency-based routing, load balancing across healthy providers, and hedged parallel requests (Future, Section 13)
- [ ] Native Gemini (`generateContent`) and AWS Bedrock adapters (D3)
- [ ] LiteLLM or any multi-provider abstraction library (D1, as in PRD-020 D2)
- [ ] Synthetic health-check probes: they cost money and need an operator-chosen prompt
- [ ] Breaker state shared across instances (PRD-018 keeps its breaker process-local too, Section 6.5)
- [ ] Anthropic server-side features: server tools, the server-side `fallbacks` parameter, message threads, compaction, the Files API, citations. The adapter never sends them (T9)
- [ ] Who may see reasoning and how it is shown (PRD-021's `reasoning:view`, D8/D9). This PRD only feeds it `ReasoningDelta`s. A `/v1` `reasoning_effort` mapping is O8
- [ ] Same-provider retries inside the harness (O2, default 0)
- [ ] A third trust level (O9 proposes it as a PRD-020 change if it is ever wanted)

## 5. User Stories

1. **As an operator**, I want to declare `anthropic/claude-sonnet-4.6 → [anthropic/claude-sonnet-4.6, anthropic-direct/claude-sonnet-4-6]`, so that an OpenRouter outage does not stop Claude traffic.
   *Example:* the stub OpenRouter returns 503. `/audit` shows two rows with the same `request_id`. Attempt 1: `success=0`, `provider=openrouter`, `route_model=anthropic/claude-sonnet-4.6`, `error_message` "OpenRouter request failed: 503 …". Attempt 2: `success=1`, `provider=anthropic-direct`, `upstream_model=claude-sonnet-4-6`, `provider_trust=external`, `fallback_reason=status_503`. Both rows have `model_used=anthropic/claude-sonnet-4.6`.

2. **As an operator**, I want startup to refuse a chain in which `ollama/qwen2.5-coder:7b` (provider `trust: internal`) falls back to an OpenRouter model (`trust: external`), so that a misconfiguration cannot leak local traffic.
   *Example:* without `allow_lower_trust: true` on the entry, the server exits with `chains.yaml: chain 'ollama/qwen2.5-coder:7b' entry 2 (openai/gpt-4o, provider openrouter): trust external is lower than the primary's trust internal; set allow_lower_trust: true on this entry to permit it (PRD-020 6.8 rule 1)`.

3. **As a coding agent**, I want my tool call to look the same whichever provider answered, so that my loop does not care about failover.
   *Example:* Anthropic returns `tool_use {id: "toolu_01…", name: "bash", input: {"command": "npm test"}}`. The client receives `tool_calls[0].function.arguments == '{"command":"npm test"}'`, decided by `evaluate_all` at step 7c.

4. **As a coding agent**, I want a total outage to be a retryable error with a backoff hint, so that my SDK waits instead of hammering the harness.
   *Example:* both breakers are open. `/v1` returns `502 {"error": {"code": "upstream_unavailable", …}}` with `retry-after: 27` and no `x-should-retry`. One `success=0` row is written with `skipped_providers='openrouter:open,anthropic-direct:open'`.

5. **As a compliance admin**, I want a safety refusal to stay a refusal, so that the chain cannot be used to find a model that complies.
   *Example:* Anthropic answers `stop_reason: "refusal"`. The client gets `finish_reason: "content_filter"`, no fallback attempt is made, and the row has `success=1`, `attempt=1`.

6. **As an operator**, I want to see which provider is unhealthy, so that I can tell a provider outage from a bad key.
   *Example:* `GET /providers/status` shows `providers.openrouter.breaker` as `open`, `last_failure_class: timeout`, `retry_after_seconds: 7`. It shows `providers.anthropic-direct.breaker` as `open`, `last_failure_class: misconfigured`, `retry_after_seconds: 288`: a 401, so the key behind its `key_env` is wrong.

7. **As a BYOK caller on `/query`**, I want my key never to be silently swapped for the deployment's key on another provider, so that my spend and the deployment's stay separate.
   *Example:* a BYOK request hits an OpenRouter 503. No fallback is attempted; `/query` answers 502; one row is written with `skipped_providers='anthropic-direct:byok'` (PRD-020 6.8 rule 3).

## 6. Core Architecture & Patterns

### 6.1 Where the chain sits in the pipeline

Steps 0–5 are as PRD-020 leaves them (PRD-020 6.1). At step 2 the primary route is resolved and authorized once. Steps 6 and 7 become a loop owned by `chain.run()`:

```
2.  route = authorize_route(identity, model)       PRD-020: primary only; a forbidden primary is today's 403
2c. usage admission                                once per request; a fallback is not a new attempt at the gate (D10)
6+7 UPSTREAM CHAIN (new)
    candidates = chain_for(model, ingress)         # D5; [model] when no chain → exactly PRD-020
    for c in candidates:                           # c is a catalogue id; c.route = registry.resolve(c)
        skip = eligibility(c, identity, request)   # trust (startup), route check, capability, BYOK, breaker, deadline
        if skip: skipped.append((c, skip)); continue
        sent = redaction_for(c.route)              # step 6 for THIS route, from the raw conversation (D16)
        try:
            result = call_upstream(sent, model=c.id, api_key=byok_key_if_primary, **extra)   # PRD-020 D12 seam
            breaker[c.provider].record_success(); break
        except UpstreamError as e:
            breaker[c.provider].record_failure(e)  # fallback-eligible kinds only (D12)
            on_attempt_failed(c, e, attempt_no)    # the success=false row is written NOW
            if not e.fallback_eligible or released_any:   # D8, D9
                raise
    else:
        raise ChainExhausted(skipped, last_error)  # D12
7b. charge   the answering attempt's usage (estimated usage charged as PRD-020 D8 says)
7c. actions  unchanged: evaluate_all over the answering attempt's tool calls
8.  redact output per profile (unchanged), success row (attempt=n, PRD-020 columns for c.route), return
```

- **The seam is unchanged.** The chain calls PRD-020's `call_upstream` once per candidate with that candidate's catalogue id. Tests that replace `call_openrouter`/`call_upstream`, and `/v1`'s `_Upstream` wrapper ([v1.py:120-151](../../../app/routers/v1.py)), see one call per attempt. `_Upstream.called` is set on the first call, which is the commit signal; `result` holds the answering call's result.
- **Failed-attempt rows are written by a callback while the chain runs**, never collected and written afterwards. A crash on attempt 3 leaves attempts 1 and 2 on record. The callback is today's step-7 `log_query` arm ([query_pipeline.py:765-783](../../../app/services/query_pipeline.py)) plus the PRD-020 columns for the candidate's route and `request_id`, `attempt` and `route_model`.
- **Admission runs once.** The gate counts the user's attempts ([query_pipeline.py:436-438](../../../app/services/query_pipeline.py)). A fallback is the harness's choice; charging the user's rate for a provider outage would punish the user for the provider's fault.

### 6.2 Fallback eligibility of a fault (D8)

| `UpstreamError.kind` | Mapping today | Breaker | Fallback? |
|---|---|---|---|
| `timeout`, `transport` | `retryable=True` → `upstream_unavailable` | counts | yes |
| `status` 5xx (incl. Anthropic 529 overloaded) | retryable | counts | yes |
| `status` 429 | retryable | counts; `retry-after` sets the minimum open time | yes |
| `misconfigured` (401) | a non-retryable 4xx | **force-open** | yes: the fault is about the provider, not the request |
| `status` other 4xx (400, 403, 404, 413, 422) | `upstream_error` | no | **no** |
| `shape` (malformed body, PRD-020 T7) | `upstream_error` | no | **no** (O4) |
| `refusal` (`stop_reason: refusal`) | not a fault; it is an answer | no | **never** (T4) |
| `incompatible` (the adapter cannot express the request) | `upstream_error` | no | **no** (D4) |

`fallback_eligible = retryable or kind == "misconfigured"`. A 401 is still non-retryable *for the client* when it is the last word (`upstream_error`).

### 6.3 Trust and the chain (D6)

PRD-020 defines two provider trust levels, `trust: internal` and `trust: external` (default), recorded per row as `provider_trust` (PRD-020 F1, F5, D7). The rules:

- **Same trust** is allowed: `external → external` and `internal → internal`.
- **`external → internal`** is allowed. The data moves to a place the operator trusts more. Step 6 is still recomputed for the internal route, so a `pii: relaxed` internal provider receives unredacted input only if it is the route receiving the data (6.4, rule 2).
- **`internal → external`** is the crossing. It is a startup error unless that entry carries `allow_lower_trust: true`. When it is set, startup logs a WARNING naming the chain and entry, and every request that actually crosses records `fallback_reason='<kind>;trust_lowered'` on the answering row. This is PRD-020 6.8 rule 1's "explicit, per-pair policy entry": the pair is (primary, that entry).
- Each candidate is compared with the **primary** (the first entry), never with the entry before it. A crossing is evaluated per candidate, so no ordering of entries lets data reach a lower trust without its own opt-in.
- The first candidate must be the chain's own model, so a chain cannot change who answers on a good day.

### 6.4 Conformance with PRD-020 Section 6.8

| PRD-020 6.8 rule | How this PRD satisfies it |
|---|---|
| 1. Never automatic across trust levels; explicit per-pair entry | `internal → external` is a startup error without `allow_lower_trust: true` on that entry (D6). Each crossing is recorded per row (`;trust_lowered`, `provider_trust`). Tested on a chain with two external entries, only one opted in |
| 2. Redaction computed for the provider that receives the data; relaxed input never reaches an external provider | `redaction_for(route)` runs step 6 from the **raw** conversation under that route's policy, including PRD-020's `relaxes_input()` and the `code` size limit. It is reused only when `(profile policy, relaxes_input)` is identical. It never chains from another candidate's output. `relaxes_input()` requires `trust: internal`, so relaxed text cannot be built for an external route (D16, T3) |
| 3. A BYOK key never follows a fallback | A BYOK request has a chain of length 1 (D15). The key is passed only on the primary's `call_upstream` |
| 4. Each attempt is audited with its own provider | One row per attempt, each with PRD-020's `provider`, `upstream_model`, `provider_trust`, `pii_input_relaxed` and `usage_estimated` for **that** attempt's route, linked by `request_id` (D10) |

A fallback candidate's redaction can fail. A `PiiRedactorError` ends the chain through today's redaction-error arm (fail closed). A `code` size-limit breach makes that candidate ineligible (`redaction_limit` skip), because nothing was sent and another candidate may be relaxed.

### 6.5 The Anthropic mapping (D4)

**Request** (`UpstreamRequest`: `messages`, `upstream_model`, `params`, `tools` → `POST /v1/messages`):

| Internal | Messages API | Note |
|---|---|---|
| `system` turns | top-level `system` (in order, joined by `\n\n`) | Hoisted wherever they occur. A non-leading system turn loses its position, and the docs say so |
| `user` | `{"role":"user","content":[{"type":"text","text":…}]}` | |
| `assistant` content | a `text` block, omitted when it is `""` | `""` is the normalizer's stand-in for `content: null` ([openrouter_client.py:136-138](../../../app/services/openrouter_client.py)) |
| `assistant.tool_calls[i]` | `{"type":"tool_use","id","name","input": json.loads(arguments)}` | `arguments` that is not a JSON object raises `incompatible` (non-retryable, no fallback). Nothing is invented |
| consecutive `tool` turns | **one** `user` message with one `tool_result` block per turn | Parallel results go in one message |
| `ToolParams.tools[i]` | `{"name","description","input_schema": parameters or {"type":"object"},"strict"?}` | |
| `tool_choice` `none`/`auto` | `{"type":"none"}` / `{"type":"auto"}` | |
| `tool_choice` `required` / named | `{"type":"any"}` / `{"type":"tool","name"}` | Only if the model has `forced_tool_choice: true` (**PRD-022 addition** to PRD-020 D6). Some current Claude models reject forced choice with a 400. Without the capability, the candidate is **ineligible** (D7) |
| `parallel_tool_calls: false` | `tool_choice.disable_parallel_tool_use: true` | |
| `max_tokens` | `max_tokens` (required) | Defaults to the model's `default_max_tokens` (**PRD-022 addition**, a catalogue model field) |
| `stop` | `stop_sequences` (a list) | |
| `temperature`, `top_p` | sent only if `sampling_params: true` (**PRD-022 addition**) | Otherwise dropped, and recorded in the row's `ignored_params` as `temperature@anthropic-direct`. Current Claude models and API versions reject sampling parameters, and PRD-015 forbids a silent drop |

**Response** (→ `UpstreamResult`):

| Messages API | Internal | Note |
|---|---|---|
| `text` blocks | `response`, concatenated | |
| `tool_use` blocks | `ToolCallSpec(id, name, json.dumps(input, ensure_ascii=False, separators=(",", ":")))` | The one place the harness serializes arguments. The action policy classifies this string and the client receives it, so PRD-017 T1 holds |
| `thinking` / `redacted_thinking` | counted into `reasoning_blocks`; not in `response` | D14. Streamed summarized `thinking` text becomes `ReasoningDelta` (6.6). `redacted_thinking` is encrypted and never emitted |
| `stop_reason` `end_turn` / `stop_sequence` / `max_tokens` / `tool_use` / `refusal` | `stop` / `stop` / `length` / `tool_calls` / `content_filter` | `pause_turn` cannot occur because no server tools are sent; if it does, it is a `shape` error |
| `usage.input_tokens + cache_creation_input_tokens + cache_read_input_tokens` | prompt tokens | Anthropic's `input_tokens` excludes cached tokens, so counting it alone would under-charge (PRD-013 F11) |
| `usage.output_tokens` | completion tokens | Includes thinking |
| the cache pair | `cache_write_tokens`, `cache_read_tokens` | Recorded per row |

Anthropic always reports usage, so PRD-020's `usage_missing` setting has no effect for `type: anthropic`. A missing `usage` is a `shape` error.

**Prompt caching.** With `prompt_cache: auto`, the adapter sends top-level `cache_control: {"type": "ephemeral"}`. Caching matches on the prefix, and the harness's prefixes are stable: redaction placeholders are deterministic (`<PERSON>`), and `code` leaves `system` untouched.

**Transport.** The adapter uses the official SDK: `anthropic.Anthropic(api_key=<key_env value or BYOK>, base_url=provider.base_url, timeout=provider.timeout_seconds, max_retries=0)`. `base_url` passes PRD-020 D5 (F3) at load time. SDK errors map to `UpstreamError` kinds: `APITimeoutError` → `timeout`, `APIConnectionError` → `transport`, `AuthenticationError` → `misconfigured`, `RateLimitError` → 429 with `retry_after_seconds`, `APIStatusError` → `status`. Messages keep PRD-020's convention of a `label` prefix.

### 6.6 Streaming (PRD-020 D11, PRD-021, D9)

`stream()` maps Anthropic SSE events to PRD-020's `UpstreamEvent`s:

- `content_block_delta` with `text_delta` becomes `TextDelta`.
- A `tool_use` block's `input_json_delta` fragments are **buffered until `content_block_stop`**. They are then parsed and canonically serialized (D4), and emitted as **one** `ToolCallDelta(index, id, name, arguments_fragment=<whole string>)`. That keeps `collect(stream(r)) == complete(r)`, PRD-020's property test.
- `message_delta` `stop_reason` becomes `Finish`, and the usage becomes `UsageReport` with the cache fields added.
- `thinking_delta` becomes PRD-021's `ReasoningDelta(text)` (PRD-021 Section 6.2, item 1). This happens **only when the model's `reasoning` capability is true**, which is the rule PRD-021 sets for the OpenAI-compatible adapter; otherwise thinking is dropped. Recent Claude models default thinking display to "omitted", which streams empty thinking text, so with `reasoning` on the adapter requests `thinking: {type: "adaptive", display: "summarized"}`. The client therefore only ever sees the provider's summary, never raw chain of thought. `redacted_thinking` and `signature_delta` are never emitted. `collect()` ignores `ReasoningDelta`, so `collect(stream(r)) == complete(r)` holds and reasoning cannot leak into `UpstreamResult.response`. Whether a `ReasoningDelta` reaches anyone is PRD-021's gate: `reasoning:view`, its D8 redaction and D9 `reasoning_content`. A streamed attempt goes through PRD-021's `stream_upstream` seam, the streaming twin of `call_upstream`, once per candidate.

**The fallback window.** PRD-021's `DeliverySink.committed()` fires when the stream opens, and the role chunk goes out at commit. Neither carries answer content. The chain treats an attempt as **released** from the first `content()` or `reasoning()` sink call, or from the first released tool call. A failure before that point falls back exactly as `complete()` does: the next attempt continues the same committed SSE response. A failure after it becomes the stream's `error` event, and the attempt row records `success=0` with whatever usage arrived. The chain never resumes, splices or replays an answer onto another provider.

### 6.7 Duplicate check, usage and the audit row (D10)

- **Duplicate.** `dedup_key` is computed once over the raw conversation (step 1) and does not depend on the model or the provider. Failed-attempt rows are `success=0`, and `find_duplicate_timestamp` only counts real verdicts ([database.py:859-863](../../../app/db/database.py)). So failed attempts are never a prior query; only the answering attempt's success row is. The lookup does not change.
- **Rate.** `admit()` runs once at step 2c.
- **Budget.** `charge()` runs once at 7b with the answering attempt's usage, reported or estimated (PRD-020 D8). A failed buffered attempt reports nothing, as with today's upstream-error arm ([query_pipeline.py:791-793](../../../app/services/query_pipeline.py)). A failed *streamed* attempt that reported usage first is charged from its own row (PRD-013 T3).
- **Rows.** There is one row per attempt. Skips are not rows. They are listed on the final row's `skipped_providers` as `provider:reason`, with reason one of `open`, `half_open_busy`, `forbidden`, `capability`, `byok`, `redaction_limit` or `deadline`. A request with no chain writes PRD-020's rows with `attempt=1` and NULL `fallback_reason`/`skipped_providers`.

### 6.8 Directory structure (files touched)

```
app/services/provider_registry.py      type: anthropic; PRD-022 catalogue fields (forced_tool_choice, sampling_params,
                                       prompt_cache, default_max_tokens); chain validation hooks
app/services/upstream/__init__.py      UpstreamError fields (D11); UpstreamResult/UsageReport cache fields
app/services/upstream/anthropic.py     NEW: AnthropicAdapter — complete(), stream() (6.5, 6.6)
app/services/upstream/chain.py         NEW: chain_for, eligibility, redaction_for, run(), ChainExhausted
app/services/upstream/chain_config.py  NEW: PROVIDER_CHAINS_FILE loader + startup validation
app/services/upstream/health.py        NEW: one PRD-018 breaker per provider (6.10); providers_status()
app/services/query_pipeline.py         steps 6+7 → chain.run(); per-attempt row callback; request_id
app/services/audit_logger.py, app/db/*  PRD-022 columns via AUDIT_LOGS_ADDED_COLUMNS (PRD-020 D13's path)
app/routers/v1.py, app/services/v1_translate.py   ChainExhausted → retry-after; model / harness.provider
app/routers/admin.py                   GET /providers/status; /stats figures
chat_ui/chat_ui/admin_*.py             Providers panel; Register attempt column
scripts/stub_openrouter.py             Anthropic mode + scripted faults
docs/features.md, docs/api.md, docs/deployment.md
```

### 6.9 Patterns followed

- **Module-name bindings for test seams.** The pipeline calls `chain.run` through its module (PRD-017 STORY-010 DD-5, [query_pipeline.py:17-20](../../../app/services/query_pipeline.py)).
- **Required keyword arguments** on the attempt-row callback (`request_id`, `attempt`, `route`), so a forgotten argument is a `TypeError`, not a NULL. This is the `_deny` rule ([query_pipeline.py:249-284](../../../app/services/query_pipeline.py)).
- **Settings read per call** (the rule in [query_pipeline.py:125-129](../../../app/services/query_pipeline.py)). The registry and chain are one immutable snapshot per request (PRD-020 D12).
- **Strict YAML with startup errors that name the file, chain and entry** (PRD-016 D13, PRD-020 F1).

### 6.10 The breaker: what is reused from PRD-018, what is generalized

PRD-018 specifies one breaker for the storage path (Section 6.5, D6). It is **reused as a state machine, not as an instance**:

| Aspect | PRD-018 (storage) | PRD-022 (providers) | Relation |
|---|---|---|---|
| States and transitions | `closed → open` after 5 consecutive infrastructure-class failures; `open → half_open` after 10 s; probe success → `closed`, failure → `open` for another 10 s | identical | **reused** |
| What counts | operations, not attempts; `STATEMENT` failures never count | attempts, which are operations here (one provider call); only `fallback_eligible` kinds count; deterministic 4xx, `shape`, `incompatible` and refusals never count (6.2) | **reused rule**, provider classification |
| Thresholds | module constants `_BREAKER_FAILURE_THRESHOLD = 5`, `_BREAKER_OPEN_SECONDS = 10.0` (PRD-018 O6) | the same values, also constants, with the same rationale | **reused** |
| Clock | injected monotonic clock for tests (PRD-018 F4) | same | **reused** |
| `retry_after_seconds` | integer seconds until the next half-open, minimum 1 (PRD-018 Section 6.7) | same rule, carried on `UpstreamError`/`ChainExhausted` (D11) rather than on `StorageUnavailableError` (PRD-018 D7) | **reused rule** |
| Status | `storage_status()` / `GET /storage/status`: `breaker {state, since, consecutive_failures, last_failure_class, retry_after_seconds}` plus counters, no DB call (D16) | `providers_status()` / `GET /providers/status`: the same `breaker` object per provider, same counter style, no network call | **reused shape** |
| Transition logs | one structured log line per transition | same | **reused** |
| Instances | one per process (module singleton beside the shared client) | **one per provider**, keyed by registry `name`, per process | **generalized** |
| Half-open probe | the breaker's own `SELECT 1` on a fresh client; other callers keep failing fast | **the next live request is the probe**; other callers skip the provider (`half_open_busy`). There is no free synthetic call to a provider: it would cost tokens and need a prompt | **generalized** |
| Force-open | none | `misconfigured` (401) force-opens for `_PROVIDER_MISCONFIGURED_OPEN_SECONDS = 300`. A 429 opening it uses `max(retry_after, 10)` | **generalized** |
| Open means | `StorageUnavailableError`: fail closed, never wave through | skip this candidate. If none remain, `ChainExhausted`: fail, never route around a trust, RBAC or capability rule | same principle |

**As specified, PRD-018's breaker is not reusable verbatim.** It is one module-level instance in `database.py`, its probe is hard-wired to `SELECT 1`, and it has no force-open. Rather than write a second breaker, this PRD proposes **one edit to PRD-018 (O10)**. The state machine moves into a small class (for example `app/services/circuit_breaker.py: CircuitBreaker(name, threshold, open_seconds, clock)`) with `before()`, `record_success()`, `record_failure()`, `force_open(seconds)` and `status()`. Half-open is configurable: with a probe callable (storage passes its `SELECT 1`), or with none (admit exactly one live caller, as providers need). Storage keeps exactly one instance and its current behaviour. If PRD-018 is built before that edit, PRD-022's STORY-001 performs the extraction as a refactor with PRD-018's tests unchanged.

## 7. Tools/Features

### F1 — `UpstreamError` extension and the eligibility rule
The extension adds `provider`, `kind`, `retry_after_seconds` (defaulted) and `fallback_eligible` to PRD-020's `UpstreamError`. `str(exc)`, `upstream_status` and `retryable` are unchanged, so `error_message` and the 502 detail are unchanged ([openrouter_client.py:21-23](../../../app/services/openrouter_client.py)). The OpenAI-compatible adapter sets `kind` from the classification it already performs, with no behaviour change. `ChainExhausted` is a subclass with `kind="exhausted"` and `retryable=True`.

### F2 — Anthropic adapter
Sections 6.5–6.6 in full. Unit tests cover each mapping row, a golden tool loop, cache-token accounting, a refusal, `incompatible` on non-JSON arguments, SDK error mapping and `collect(stream(r)) == complete(r)`.

### F3 — Chain configuration
```yaml
# PROVIDER_CHAINS_FILE=examples/chains.yaml  — every id must be catalogued in PROVIDERS_FILE
version: 1
chains:
  - match: {model: anthropic/claude-sonnet-4.6}            # openrouter, trust: external
    candidates:
      - model: anthropic/claude-sonnet-4.6
      - model: anthropic-direct/claude-sonnet-4-6           # type: anthropic, trust: external
  - match: {model: ollama/qwen2.5-coder:7b, ingress: v1}    # ollama, trust: internal, pii: relaxed
    candidates:
      - model: ollama/qwen2.5-coder:7b
      - model: lan/llama-3.1-70b                            # gpu-box, trust: internal → no opt-in needed
      - model: openai/gpt-4o                                # openrouter, trust: external
        allow_lower_trust: true                             # internal → external: explicit (PRD-020 6.8 rule 1)
```
Match precedence: `(model, ingress)` beats `(model)`; a duplicate key is a startup error. Validation: `version` is 1; each id is catalogued (passthrough-only ids are refused, since a chain must not route to an id the operator never listed); the first candidate equals `match.model`; no id is repeated; there are at most `PROVIDER_CHAIN_MAX_CANDIDATES` (default 3) entries; the trust rule (6.3); and capability coverage, where a candidate lacking a capability the primary has needs `capability_scoped: true`, so it serves only requests not needing that capability. Unknown keys are refused.

### F4 — Eligibility per request (D7, D15)
For each candidate, in order:
- **Route check:** PRD-020's per-role check for the candidate's id (`model.roles` > `provider.roles` > all, wildcard roles as PRD-020 D4). Failing gives skip reason `forbidden`.
- **Capability:** a `tools` request needs `tools`, plus `forced_tool_choice` when `tool_choice` is `required` or names a function. A real-time streamed request needs `streaming`. PRD-020 D9's estimate must be within `max_context_tokens` when that is set. Failing gives `capability`.
- **BYOK:** non-primary candidates are skipped with `byok`.
- **Breaker state:** `open` or `half_open_busy`.
- **Deadline:** remaining time below `PROVIDER_MIN_ATTEMPT_SECONDS` gives `deadline`.

A forbidden **primary** has already been refused at step 2 with PRD-020's verdict and label. The chain never rescues it.

### F5 — Chain runner
Section 6.1. `PROVIDER_CHAIN_DEADLINE_SECONDS` defaults to the primary provider's `timeout_seconds`, so a configured chain is never slower in the worst case than today's single call.

### F6 — Breaker integration
`health.breaker(provider_name)` returns that provider's instance of PRD-018's breaker class (6.10, O10), with PRD-018's constants:
- Success closes the breaker. A fallback-eligible fault other than `misconfigured` increments it.
- `misconfigured` force-opens it for `_PROVIDER_MISCONFIGURED_OPEN_SECONDS` (300).
- A 429 that opens the breaker sets the open time to `max(retry_after, 10)`.
- Half-open admits one live request; others see `half_open_busy`.

The registry snapshot keys breakers by provider `name`. A provider that disappears on reload drops its breaker.

### F7 — Exhaustion
- `ChainExhausted.retry_after_seconds` is the smallest `retry_after_seconds` among candidates skipped as open: an integer, minimum 1, by PRD-018's rule. `None` (nothing was open) sends no header.
- When no attempt ran, the pipeline writes one `success=0` row with `'all providers unavailable'` and the primary's PRD-020 columns. When attempts ran, their rows are the record.
- `/v1` returns 502 `upstream_unavailable` (the existing retryable code): no `x-should-retry`, plus `retry-after`.
- `/query` returns 502 `all providers unavailable`.
- The chat UI shows the existing upstream-error bubble.

### F8 — Audit columns and `/audit`
These are **PRD-022 additions**, through `AUDIT_LOGS_ADDED_COLUMNS` (PRD-020 D13's path):
- `request_id TEXT`: a uuid4 per `run_conversation` call, on every row it writes, verdicts included.
- `attempt INTEGER`: 1-based; NULL on rows written before step 7.
- `route_model TEXT`: the catalogue id of this attempt.
- `fallback_reason TEXT`: the previous attempt's kind or status (e.g. `status_503`, `timeout`), plus `;trust_lowered`.
- `skipped_providers TEXT`.
- `cache_read_tokens INTEGER`, `cache_write_tokens INTEGER`.

`GET /audit` returns them, and `?request_id=` filters one request's rows. PRD-020's five columns are written per attempt with that attempt's route.

### F9 — Observability
`GET /providers/status` (`stats:read`, [authz.py:14](../../../app/services/authz.py)) mirrors PRD-018's `GET /storage/status` (D16). It returns `instance`, a `providers` map whose values are PRD-018's `breaker` object (`state`, `since`, `consecutive_failures`, `last_failure_class` = the `UpstreamError.kind`, `retry_after_seconds`), and process-local `counters`. It makes no network or database call, and its counters reset on restart (Section 10). `GET /stats` adds three figures inside the existing single-statement snapshot ([admin.py:186-215](../../../app/routers/admin.py)):
- `fallback_answers`: success rows with `attempt > 1`.
- `failed_attempts`: `attempt IS NOT NULL AND success = 0`.
- `answers_by_provider`: top N.

The console's Providers panel reads `providers_status()` in-process, beside PRD-018's Storage panel, so it needs no network call (PRD-018 F8).

### F10 — Response surfaces
On `/v1`: `model` is the answering catalogue id, plus `harness.provider`, `harness.attempts` and `X-Harness-Provider`. Without a fallback, `model` equals the requested id, as in PRD-020. On `/query`: `QuerySuccessResponse.model_used` carries the answering catalogue id, and the schema is unchanged. The audit's `model_used` keeps PRD-020's "requested" meaning; `route_model` holds the answering id (D17).

### F11 — Stub and E2E
The stub gains `POST /v1/messages` (JSON and SSE) and faults scripted per request. The E2E test runs the OpenAI SDK or OpenCode against `/v1` with tools:
- The OpenRouter stub fails and the Anthropic stub answers.
- Three requests open the breaker, and a fourth reaches OpenRouter zero times (hit counter).
- `/providers/status` is checked.

## 8. Technology Stack

- Python 3.11, FastAPI, pydantic-settings, as today.
- **New:** the `anthropic` Python SDK, pinned exactly in `requirements.txt`, like `presidio-*==2.2.364` and `sqlglot==30.27.0`. Its 1.x line is built on `httpx2`, not `httpx`, which adds a second HTTP stack beside PRD-020's `httpx.Client(follow_redirects=False)`. STORY-001 confirms the version and checks that redirects are not followed with the key attached. If the SDK cannot guarantee that, D2 falls back to raw `httpx`.
- PRD-018's breaker state machine (6.10). No new resilience library, the same choice PRD-018 makes against `tenacity`/`pybreaker`.
- PyYAML through `strict_yaml`.
- `.agents/skills/frontend-design` applies to the Providers panel: "distinctive, intentional visual design … making choices that don't read as templated defaults". The panel follows `chat_ui/chat_ui/theme.py`.

## 9. Security & Configuration

### 9.1 Authentication & authorization
Ingress authentication is unchanged. The primary is authorized at step 2 by PRD-020's route check. Every fallback candidate passes the same per-role check (F4). `GET /providers/status` requires `stats:read`. Keys stay behind `key_env` (PRD-020 F1) and never appear in rows, logs or health output.

### 9.2 Threat reasoning

| # | Threat | Treatment |
|---|---|---|
| T1 | **Data leaves the network through a fallback.** An `internal` model's prompt goes to an `external` provider during an outage | `internal → external` is a startup error without a per-entry `allow_lower_trust` (D6, PRD-020 6.8 rule 1). Every candidate is compared with the primary. Crossings are recorded per row. Tested with a chain of internal, internal, external, external where only the last external entry opts in: the third entry fails startup until it opts in too |
| T2 | **Privilege escalation by fallback.** The caller may use A but not B, and A's outage routes them to B | PRD-020's per-role check per candidate (F4). A forbidden candidate is skipped, never used. Tested with a role whose `roles:` excludes the fallback model |
| T3 | **Relaxed or weaker redaction reused.** Text relaxed for an internal provider is resent to an external one | Step 6 is recomputed per route from the raw conversation, never chained (D16, PRD-020 6.8 rule 2). `relaxes_input()` requires `internal`. A test asserts that the external candidate receives standard-redacted text after an internal relaxed primary fails |
| T4 | **Model shopping.** A refusal triggers a fallback to a more permissive model | A refusal is an answer and never fallback-eligible (6.2) |
| T5 | **Cost amplification.** A timeout fallback means two providers process (and bill) one prompt | Chain deadline (F5), the breaker, max 3 candidates, and `failed_attempts` visible. Accepted residual: a timed-out provider may still bill |
| T6 | **Tool-call drift across providers** | Serialization happens once in the adapter (D4). The policy and the client see the same string (PRD-017 T1) |
| T7 | **BYOK spend mixing** | Chain of length 1 (D15, PRD-020 6.8 rule 3) |
| T8 | **Breaker as a DoS lever.** Crafted requests open a provider's breaker for everyone | Only provider-side faults count. A deterministic 400/413/422 never counts (6.2). A 429 from one heavy user can count; the usage gate bounds per-user volume (O6) |
| T9 | **Provider-side features widen the surface** (server tools, server-side fallbacks, threads) | The request builder uses a field allowlist (PRD-010 T5's pattern). A test asserts the exact key set |
| T10 | **Health output leaks provider internals** | Only `kind` and status are exposed, never messages (`v1.py:229-232`'s rule) |
| T11 | **Key exfiltration via `base_url` or a redirect** | PRD-020 D5 governs `base_url`. Redirects must not be followed with the key (Section 8 check) |

### 9.3 Configuration

| Variable | Default | Validation | Purpose |
|---|---|---|---|
| `PROVIDER_CHAINS_FILE` | `""` (no chains) | `strict_yaml`; F3 rules; requires `PROVIDERS_FILE` | Fallback chains |
| `PROVIDER_CHAIN_MAX_CANDIDATES` | `3` | 1–5 | Bounds cost and latency (T5) |
| `PROVIDER_CHAIN_DEADLINE_SECONDS` | the primary's `timeout_seconds` | > 0 | Total time for the chain |
| `PROVIDER_MIN_ATTEMPT_SECONDS` | `5` | > 0, < deadline | Skip a candidate that cannot finish |

The breaker thresholds are **constants, not settings**, following PRD-018 (Section 6.5, O6): 5 failures, 10 s open, 300 s force-open after a 401 (6.10). O11 records the alternative.

Registry additions (**PRD-022 addition**, in `PROVIDERS_FILE`): provider `type: anthropic`; catalogue model fields `default_max_tokens` (required for `type: anthropic`), `prompt_cache: off | auto`; capabilities `forced_tool_choice`, `sampling_params` (default `false`, PRD-020's "claimed, not assumed" rule, its O6).

### 9.4 Out of scope (security)
Breaker state shared across instances (process-local, as PRD-018's is). Verifying that an `internal` provider really is internal: that is the registry's declaration, warned about for hostnames (PRD-020 O3). Inspecting responses for exfiltration beyond today's output redaction.

## 10. API Specification

**`POST /v1/chat/completions` — success after a fallback**
```
200  X-Harness-Audit-Id: 4812   X-Harness-Provider: anthropic-direct
{"id": "chatcmpl-harness-4812", "model": "anthropic-direct/claude-sonnet-4-6",
 "choices": [...], "usage": {...},
 "harness": {"audit_id": 4812, "provider": "anthropic-direct", "attempts": 2, ...}}
```

**`/v1` errors (changes only)**

| Case | Status | `code` | Retryable | Headers |
|---|---|---|---|---|
| Every candidate failed with an eligible fault | 502 | `upstream_unavailable` | yes | — |
| Every candidate skipped as `open` / `half_open_busy` | 502 | `upstream_unavailable` | yes | `retry-after: <s>` |
| Last attempt failed non-eligible (4xx, `shape`, `incompatible`) | 502 | `upstream_error` | no | `x-should-retry: false` |
| No candidate eligible (capability / route / BYOK), primary included | 502 | `upstream_error` | no | `x-should-retry: false` (O5) |

**`POST /query`**: 502, `detail` unchanged or `all providers unavailable`. Body schema unchanged.

**`GET /providers/status`** (`stats:read`)
```json
{"instance": "web-1:4120",
 "providers": {
   "openrouter":       {"breaker": {"state": "open", "since": "2026-11-16T10:04:21Z", "consecutive_failures": 5,
                                    "last_failure_class": "timeout", "retry_after_seconds": 7}},
   "anthropic-direct": {"breaker": {"state": "closed", "since": null, "consecutive_failures": 0,
                                    "last_failure_class": null, "retry_after_seconds": null}}},
 "counters": {"attempts_failed": {"openrouter:timeout": 5}, "fallback_answers": 3,
              "skipped": {"openrouter:open": 12}, "breaker_opens": 1}}
```

**`GET /stats`** gains `fallback_answers`, `failed_attempts` and `answers_by_provider: [{provider, count}]`. **`GET /audit`** rows gain the F8 columns (PRD-020's five are already there) and `?request_id=`.

## 11. Success Criteria

### MVP definition
The Section 1 goal, demonstrated by F11's E2E against the stub, plus an unchanged suite with no chain file.

### Functional requirements
- [ ] With `PROVIDER_CHAINS_FILE` empty, every PRD-020 test passes unmodified, and the captured responses and rows are byte-identical apart from the new columns (`attempt=1`, others NULL)
- [ ] 503, 429, timeout and transport errors fall back. 400, 403, 404, 422, a malformed body, a refusal and `incompatible` do not (parametrized over 6.2)
- [ ] A 401 force-opens the breaker and falls back
- [ ] Each failed attempt's `success=0` row is written before the next attempt starts, carrying that attempt's `provider`, `upstream_model` and `provider_trust`. All rows share `request_id` (PRD-020 6.8 rule 4)
- [ ] A failed attempt row is never a prior query. The same request resent after an all-failed chain is answered, not held
- [ ] `admit` is called once and `charge` once, with the answering attempt's usage, reported or estimated (spies)
- [ ] Anthropic prompt tokens = input + cache write + cache read (unit test with all three non-zero)
- [ ] A tools request falls back only to a `tools` candidate. A forced `tool_choice` falls back only to a `forced_tool_choice` candidate
- [ ] A role excluded from the fallback model by `roles:` is never answered by it (T2)
- [ ] Startup refuses: `internal → external` without `allow_lower_trust`; a first candidate other than `match.model`; a repeated or uncatalogued id; a passthrough-only id; a duplicate match; uncovered capabilities without `capability_scoped`
- [ ] `internal → external` with `allow_lower_trust` records `;trust_lowered` and `provider_trust=external` on the answering row
- [ ] After a relaxed `internal` primary fails, the `external` candidate receives standard-redacted text, and its row has `pii_input_relaxed=0` (T3, PRD-020 6.8 rule 2)
- [ ] A BYOK request makes exactly one attempt (PRD-020 6.8 rule 3)
- [ ] The Anthropic request's key set equals the allowlist (T9)
- [ ] `collect(stream(r)) == complete(r)` for the Anthropic adapter over every stub script
- [ ] Streaming (with PRD-021): a failure before the first content, reasoning or tool release falls back inside the same SSE response. A failure after it yields an `error` event and no second attempt
- [ ] With every breaker open: 502 `upstream_unavailable` with `retry-after` and zero stub hits
- [ ] `/providers/status` reports each transition, and one WARNING is logged per transition without message text

### Quality indicators
- Overhead with no chain: p95 < 0.5 ms (`scripts/measure_v1_latency.py`).
- Added latency of a fallback: the failed attempt's time-to-fail plus no more than 5 ms of harness work.
- The Anthropic mapping is covered row by row by unit tests that make no network calls.

## 12. Implementation Phases

### Phase 1 — Foundations
**Goal:** the contracts exist before behaviour changes. **Deliverables:**
- STORY-001 (spike): extracts PRD-018's breaker into the reusable class unless PRD-018 already did (6.10, O10); re-reads PRD-020 and PRD-021 as built; pins the `anthropic` SDK; checks redirect handling; confirms the "Not verified" list.
- The `UpstreamError` extension.
- PRD-022 audit columns, the migration and `/audit`.
- `request_id` on every row.

**Validation:** the suite is green, and the new columns are NULL or defaulted.

### Phase 2 — Anthropic native adapter
**Goal:** `type: anthropic` works as a primary, with no chain. **Deliverables:** registry type and fields, the 6.5 mapping, `complete()`, `stream()`, the `collect()` property, and the stub Anthropic mode. **Validation:** mapping tests pass, and a `/v1` tool loop with an Anthropic primary passes PRD-017's E2E assertions.

### Phase 3 — Chains and breaker
**Goal:** fallback and breaker work end to end. **Deliverables:** chain config and validation, eligibility, per-route redaction, the runner with per-attempt rows, the deadline, breaker integration, exhaustion handling, and the BYOK and route rules. **Validation:** Section 11, except streaming and observability.

### Phase 4 — Observability, streaming, docs
**Goal:** operators can see what happened. **Deliverables:** `/providers/status`, the `/stats` figures, the console, the streaming fallback window (once PRD-021 lands), the E2E test, and docs. **Validation:** the E2E test passes, and the doc examples were run.

## 13. Future Considerations

- A native Gemini adapter (`generateContent`: `functionDeclarations`, thought parts, `cachedContent`), when a deployment needs features the OpenAI-compatible path loses (D3).
- Bedrock. Claude on Bedrock through the Anthropic SDK's Bedrock client reuses this mapping and adds AWS credentials. Other Bedrock models need a Converse adapter.
- Breaker state shared across instances.
- Cost- and latency-aware routing, hedged requests, weighted balancing.
- Round-tripping thinking blocks across a tool loop on the same model.
- Synthetic probes for low-traffic providers.

## 14. Risks & Mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | PRD-018's breaker is built as a storage singleton before O10 is accepted, or PRD-020/021 change their interfaces in build | STORY-001 does the extraction as a behaviour-preserving refactor (PRD-018's tests unchanged). Breaker use is confined to `health.py` |
| R2 | A per-process breaker gives an inconsistent fleet picture | `instance` in the body (as in PRD-018's `/storage/status`) and the docs say per-process. Shared state is Future work |
| R3 | Anthropic API drift (sampling, forced `tool_choice`, thinking defaults) | Behaviour follows catalogue capabilities, not model names; the SDK is pinned; dropped parameters are recorded |
| R4 | Fallback hides a chronic provider problem and doubles cost | `failed_attempts` / `fallback_answers`, WARNING logs, and one row per failure |
| R5 | Mid-conversation provider switches: tool ids from one provider, history from another | Ids pass through as strings. A provider rejecting a foreign id answers 400, which gets no fallback, so the error is a clear `upstream_error`. STORY-001 checks Anthropic's id format |
| R6 | A second HTTP stack (`httpx2`) in the security path | One pinned first-party package, compared in D1/D2. The redirect check comes first, with raw `httpx` as the fallback |

## 15. Appendix

### Decisions

| # | Question | Decision and why |
|---|---|---|
| D1 | Use LiteLLM? | **No**, for PRD-020 D2's reason. It is large and fast-moving, sits in the security path, and has its own retry, fallback and translation semantics. Those would take routing decisions (trust, RBAC, BYOK) the harness must make and audit itself. Through Aider it already retries 403s and ignores `x-should-retry` ([features.md:292](../../../docs/features.md)) |
| D2 | Anthropic transport | **The official `anthropic` SDK**, pinned, `max_retries=0`, explicit timeout. It is typed and ships an SSE parser, and it is maintained against the API. `max_retries=0` because the SDK retries 408/409/429/5xx by default, which would run underneath the chain and the breaker. Fallback: raw `httpx`, if the redirect check (Section 8) fails |
| D3 | Which native adapters | **Anthropic in the MVP; Gemini and Bedrock deferred.** Anthropic is where OpenAI-compatible layers lose the most that matters here: tool fidelity, thinking, and cache-token accounting (OpenAI-shaped usage has no cache-write field, so the budget is under-charged). Claude on Bedrock reuses this mapping. Gemini needs its own mapping, and no deployment needs it yet |
| D4 | Mapping strictness | **Map exactly or fail with `incompatible`.** Inbound `tool_use.input` is serialized once, canonically, in both `complete()` and `stream()`. The policy and the client see the same string |
| D5 | Where chains live | **A strict-YAML file whose entries are catalogue ids**, resolved through PRD-020's registry. Routing policy and provider inventory change for different reasons. Catalogue ids keep the chain inside what the operator listed |
| D6 | Fallback across trust | **Same trust, or `external → internal`: allowed. `internal → external`: a startup error unless that entry sets `allow_lower_trust: true`.** Compared with the primary, recorded per row. This is PRD-020 6.8 rule 1 and the user's hard constraint |
| D7 | Route and capability per candidate | **Every candidate is checked as if it had been requested** (PRD-020's per-role check, D6 capabilities plus `forced_tool_choice`). Ineligible candidates are skipped and listed. A forbidden primary stays step 2's verdict |
| D8 | What triggers a fallback | **Today's retryable set plus 401 `misconfigured`.** Never a deterministic 4xx, `shape`, `incompatible` or a refusal |
| D9 | Retry after release | **Never.** The fallback window closes at the first content, reasoning or tool release to PRD-021's sink. Commit and the role chunk do not close it |
| D10 | Audit, duplicate, usage | **One row per attempt with its own provider columns, linked by `request_id`, numbered by `attempt`.** This matches [features.md:280](../../../docs/features.md) and PRD-020 6.8 rule 4. The duplicate lookup is unchanged (PRD-009). `admit` runs once; `charge` runs once, for the answering attempt. Skips are listed on the final row, not written as rows. Rejected: one row with an attempts array, which hides failures from the register |
| D11 | Error type | **PRD-020's `UpstreamError`**, with defaulted `provider`, `kind`, `retry_after_seconds` and `fallback_eligible` (PRD-022 addition). PRD-020's `OpenRouterError` shim alias is kept, so `/v1`'s fault table and `/query`'s 502 are unchanged |
| D12 | Breaker and exhaustion | **PRD-018's state machine and constants (D6), one instance per provider, in process** (6.10). Eligible faults count; a 401 force-opens it; half-open allows one live probe. Status uses PRD-018 D16's shape. On exhaustion: **502 `upstream_unavailable`, retryable**, plus `retry-after`. This is PRD-015's existing code and status, so no client contract changes. 503 was rejected for that reason |
| D13 | Time bound | **A chain deadline defaulting to the primary's `timeout_seconds`.** Never slower in the worst case than today's single call |
| D14 | Thinking | **Off unless the model's PRD-020 `reasoning` capability is true. When it is on, `stream()` emits summarized thinking as PRD-021's `ReasoningDelta`**, the same rule PRD-021 gives the OpenAI-compatible adapter, so `reasoning:view` works for Anthropic models. `complete()`/`collect()` keep it out of `response`. Blocks are never stored or round-tripped: an OpenAI-shaped client cannot send them back. Release, redaction and permission are PRD-021's (D8/D9). Rejected: always discarding, which would make `reasoning:view` silently empty for one provider type |
| D15 | BYOK | **Never falls back** (PRD-020 D10, 6.8 rule 3) |
| D16 | PII on fallback | **Step 6 is recomputed per route from the raw conversation**, honouring `relaxes_input()` and the `code` size limit. It is reused only when the policy is identical, and never chained. Patterns stay provider-independent (PRD-020 6.1). This is PRD-020 6.8 rule 2 |
| D17 | Which model is reported | **The answering catalogue id goes to the client** (`/v1` `model`, `/query` `model_used`), plus `harness.provider`. **The audit's `model_used` keeps PRD-020's meaning (requested)**, and `route_model` records the answering id. Without a fallback, the two are the same |

### Open decisions (proposed default)

- **O1 — Raw vs summarized thinking.** Proposed: summarized only (`display: "summarized"`). Raw chain of thought is not available from current Claude models anyway, and a summary is what PRD-021 users read.
- **O2 — Same-provider retry before fallback?** Proposed: 0. Clients already retry a retryable 502, and a retry inside the harness multiplies latency under the deadline.
- **O3 — Should `allow_lower_trust` exist at all?** Proposed: yes, per entry, off by default, with a startup WARNING. The alternative is to forbid `internal → external` outright, which is stricter and simpler but leaves no escape hatch.
- **O4 — Fall back on a `shape` error?** Proposed: no. Garbage from a provider is a bug to surface.
- **O5 — No eligible candidate at all.** Proposed: 502 `upstream_error`, non-retryable, naming the capability. The alternative is a 400 at the `/v1` edge, which would need the edge to know the chain.
- **O6 — Does one user's 429 open the breaker for everyone?** Proposed: yes, because the provider's limit is shared. The usage gate is the per-user lever.
- **O7 — Provider 403** (moderation or region blocks on some providers). Proposed: not fallback-eligible.
- **O8 — Map `/v1` `reasoning_effort` to Anthropic `output_config.effort`?** Proposed: out of scope. Effort stays per catalogue model.
- **O10 — Edit PRD-018: extract the breaker into a reusable class** with pluggable half-open (probe callable or one live caller) and `force_open(seconds)` (6.10). Proposed: yes. Storage keeps one instance and identical behaviour. The alternative is a separate provider breaker, which this PRD rejects as a parallel implementation of the same state machine.
- **O11 — Breaker thresholds as constants or settings.** Proposed: constants, matching PRD-018 O6. The alternative is settings per provider (a slow local model may need a longer open time), if operators report it.
- **O9 — A third trust level** (e.g. a contracted zero-retention cloud between `internal` and `external`). Proposed: **not needed**. Two levels express the hard constraint, and `allow_lower_trust` covers the exception. If one is ever wanted, it is a change to PRD-020 D5/D7, not something PRD-022 defines.

### Builds on PRD-020 (references, not assumptions)

- Registry, catalogue and routing: PRD-020 D3, 6.3. Chain ids resolve through `resolve()`.
- Trust and PII relaxation: PRD-020 D5/D7, 6.6. `relaxes_input()` drives D16.
- Capabilities `tools`, `streaming`, `reasoning`, `max_context_tokens`: PRD-020 D6, F4. This PRD adds `forced_tool_choice` and `sampling_params`, plus the model fields `prompt_cache` and `default_max_tokens`.
- Adapter protocol: `complete()`, synchronous `stream()` of normalized events, and pure `collect()` (PRD-020 D11, 6.4). Implemented unchanged by `AnthropicAdapter`.
- Seam: `call_upstream`, with `call_openrouter = call_upstream` in the `openrouter_client.py` shim (PRD-020 D12, 6.5). The chain calls it once per attempt.
- Error type: `UpstreamError` (PRD-020 6.5, T7), extended by D11.
- Audit columns `provider`, `upstream_model`, `provider_trust`, `pii_input_relaxed`, `usage_estimated` (PRD-020 D13, F5), written per attempt.
- BYOK per provider (PRD-020 D10) and estimated usage (D8).
- Fallback rules: PRD-020 6.8. Conformance is in Section 6.4 here.
- Registry `type` set: PRD-020 F1 accepts only `openai_compatible`. This PRD adds `anthropic`.

### Builds on PRD-018 (references)

- Breaker state machine `closed → open → half_open → closed`: 5 consecutive infrastructure failures, 10 s open, a single probe, process-local, constants (PRD-018 D6, Section 6.5, O6). Reused per provider (6.10).
- An error that carries `retry_after_seconds` (integer, minimum 1) (PRD-018 D7, Section 6.7). Reused as a field on `UpstreamError` and `ChainExhausted`, not by subclassing `StorageUnavailableError`, because a provider fault is not a storage fault.
- `GET /storage/status` and `storage_status()`: `stats:read`, the `breaker` object, process-local counters, no backend call (PRD-018 D16, Section 10). Mirrored by `GET /providers/status` / `providers_status()`.
- Not reusable as specified: a singleton instance, a `SELECT 1` probe, no force-open. The proposed PRD-018 edit is O10.

### Evidence (verified against `main` @ `2253871`)
- Retryable classification `openrouter_client.py:188-197`; error class `:15-35`; `model_used=model` `:326`.
- Step 7 call and failure row `query_pipeline.py:750-784`; charge only after a result `:786-811`; admission once `:461-462`.
- `/v1` fault mapping `v1.py:198-212`; fault table `v1_translate.py:713-718`; 4xx `x-should-retry` `v1.py:178-185`; `_Upstream` `v1.py:120-151`.
- Failed rows excluded from duplicate lookup `database.py:857-884`.
- One row per retried attempt `docs/features.md:280`; LiteLLM via Aider `:292`; buffered stream `:241`.
- PRD-020 Section 6.8, D5–D13, F1, F4, F5, read 2026-11-16 (draft).

### Not verified (STORY-001 confirms)
- Exact Anthropic SSE event names and `input_json_delta` accumulation. These come from the bundled API reference, not a live call.
- Whether current Claude models accept a tool loop's history **without** the thinking blocks of the turn that issued the `tool_use` (D14 never round-trips them).
- That `display: "summarized"` yields non-empty streamed thinking text on every Claude model the registry marks `reasoning: true` (from the bundled API reference, not a live call).
- Anthropic `tool_use.id` constraints for ids minted elsewhere (R5).
- Whether the OpenAI Python SDK honours `retry-after` on a 502 (F7).
- Whether OpenRouter uses 403 for moderation (O7).
- Gemini's OpenAI-compatible coverage of tools and usage (D3).
- The `anthropic` SDK version, its `httpx2` dependency, and its redirect behaviour (Section 8).

### Related documents
[PRD-009](../PRD-009-duplicate-rescoping/PRD.md) (failed rows never a prior query), [PRD-013](../PRD-013-audit-and-usage-limits/PRD.md) (admit/charge), [PRD-015](../PRD-015-openai-compatible-endpoint/PRD.md) (D7 retry semantics, D8 buffered stream), [PRD-017](../PRD-017-tool-calling/PRD.md) (T1, D13), [PRD-020](../PRD-020-provider-registry/PRD.md), [PRD-021](../PRD-021-realtime-streaming/PRD.md), [PRD-018](../PRD-018-db-resilience/PRD.md), [docs/roadmap.md](../../../docs/roadmap.md).

### Dependencies
- Depends on: PRD-020 (registry, adapter, seam, columns), PRD-018 (breaker state machine; O10). Consumes PRD-021's sink, `ReasoningDelta` and `stream_upstream` seam for the streaming fallback window (Phase 4 only).

Skills referenced: frontend-design
