---
id: PRD-020
slug: provider-registry
title: Provider Registry — OpenRouter Stops Being the Core; Local Models and Any OpenAI-Compatible Provider
status: draft
base_branch: main
epic_branch: epic/PRD-020-provider-registry
created: 2026-11-16
updated: 2026-11-16
---

> **Track.** PRD-020 is the foundation of the provider track. **PRD-021** (real-time streaming) builds on the adapter interface defined here (Section 6.4) and must not need to rewrite it. **PRD-022** (native adapters for Anthropic Messages, Gemini and Bedrock; fallback between providers; the provider circuit breaker) builds on the registry and is bound by the trust constraint in Section 6.8. Neither is in scope here.

## 1. Executive Summary

Every model call the harness makes goes to one place. `call_openrouter` posts to `settings.OPENROUTER_BASE_URL` + `/chat/completions` with `Authorization: Bearer <OPENROUTER_API_KEY>` (`app/services/openrouter_client.py:235-268`). `OPENROUTER_API_KEY` is a required setting with no default (`app/config.py:175`). The base URL must be `https://`, or `http://` on a loopback host only (`app/config.py:89-92`, `:489-531`). `MODEL_ALLOWLIST` is one global list of OpenRouter model ids (`app/config.py:210`), and the chat UI keeps a second, hard-coded copy of it (`chat_ui/chat_ui/config.py:1-8`). A deployment that wants to send code to a model on its own GPU, to a vLLM box on the LAN, or straight to Groq or Mistral cannot. It can only point the one base URL somewhere else, and then the OpenRouter key goes there too.

There is no formal standard for LLM APIs, but there is a de facto one: the OpenAI Chat Completions wire format. OpenRouter speaks it, and so do Ollama, vLLM, LM Studio, the llama.cpp server, LocalAI and most hosted clouds. The harness already speaks it in both directions (`/v1` in, `call_openrouter` out). This PRD replaces the single upstream with a **provider registry**: an operator-owned YAML file that names each provider (type, base URL, the env var holding its key, trust level, models, per-model capabilities, per-role access). It ships **one adapter type, `openai_compatible`**, which covers OpenRouter, the local servers and most clouds. A model id the caller sends is looked up in the registry's catalogue, never parsed, and the request goes to that model's provider through the same pipeline: identity, usage gate, duplicate, patterns, PII, upstream, action policy, audit. Every audit row records which provider answered.

**With no registry file, nothing changes.** The harness builds one implicit provider, `openrouter`, from today's settings. Payloads, error strings, `/v1/models` and verdicts stay byte-identical, so existing deployments keep working with zero new configuration.

**MVP goal:** a deployment with `PROVIDERS_FILE` naming OpenRouter and a local Ollama can serve `/query`, the chat UI and `/v1` (text and tool calls) from both. Routing is by exact model id, roles are restricted per provider and model, and the Ollama key is never needed. PII redaction stays on for both unless the admin marks Ollama `trust: internal` with `pii: relaxed`. Every row names its provider and says whether its tokens were estimated. An opt-in E2E run against a real Ollama server passes. A deployment without the file passes the full existing suite unchanged.

## 2. Mission

Make the harness a control plane in front of *any* model the operator chooses, local or hosted, without weakening a single control on the way.

Core principles:

- **The catalogue is the operator's, the model id is the caller's.** A caller names a model. Only the registry decides which host receives it. No part of a request can name a host, a key or a provider.
- **One adapter, one wire format.** OpenAI Chat Completions is the de facto standard. A thin adapter we own and test is better than a framework that normalizes forty providers in the security path (D2).
- **Redaction is the default everywhere.** The decision to send unmasked text to a provider is explicit, per provider, audited, and only possible for a provider declared internal (D7).
- **Never charge zero.** A provider that reports no usage still spends a budget. The harness estimates and says so. It never records free tokens (D8).
- **No config, no change.** Without `PROVIDERS_FILE`, every byte the harness sends and returns is today's (D1).
- **Build for the next two PRDs, implement for this one.** The adapter interface can stream (PRD-021) and the registry carries trust levels (PRD-022's fallback constraint). This PRD calls neither.

## 3. Target Users

**Platform Operator.** Owns `.env` and the new `PROVIDERS_FILE`. Wants to add an Ollama on the host, a vLLM on a LAN GPU box and a direct cloud provider next to OpenRouter. Needs a startup error, not a runtime surprise, for every misconfiguration, and needs a clear warning wherever a key or data may go over plaintext.

**Security/Compliance Admin.** Needs to know, row by row, which provider received a prompt and whether that prompt was redacted. Wants to relax PII redaction only for a model that runs inside the network, and wants that decision visible in the audit, never inferred.

**Integrating Developer (coding agent).** Points OpenCode, Cline, Aider or the OpenAI SDK at `/v1`. Wants `GET /v1/models` to list only the models they can actually use, with capabilities the harness knows, and wants a local model to work for tools when it supports them.

**Chat user.** Picks a model in the chat UI's selector. Should see only models their role may use, including local ones.

**PRD-021 / PRD-022** (internal). Need a streaming-capable adapter interface and a registry with trust levels and adapter types, so neither has to reopen this design.

## 4. MVP Scope

### In Scope

**Registry (`app/services/provider_registry.py`, new)**
- [ ] `PROVIDERS_FILE` (YAML, parsed with `app/services/strict_yaml.py`, so a duplicated key is a startup error). Empty means the implicit legacy provider (D1).
- [ ] Provider fields: `name`, `label`, `type`, `base_url`, `key_env`, `insecure_http`, `trust`, `pii`, `byok`, `passthrough`, `usage_missing`, `estimate_chars_per_token`, `timeout_seconds`, `roles`, `models` (Section 7, F1).
- [ ] Model fields: `id` (unique across the registry), `upstream`, `roles`, `capabilities: {tools, streaming, reasoning, max_context_tokens}`.
- [ ] `default_model` (required in file mode).
- [ ] `load()` at startup in both lifespans, after `action_config.load()` (`app/main.py:16-20`). It validates everything and builds an immutable snapshot. There is no hot reload.
- [ ] `resolve(model) -> Route` (exact lookup, then the single `passthrough` provider, else unresolved), `visible_models(identity)`, `supports_tools(model)`.

**Adapter (`app/services/upstream/`, new package; `openrouter_client.py` becomes a shim)**
- [ ] `ProviderAdapter` protocol: `complete(request) -> UpstreamResult` and `stream(request) -> Iterator[UpstreamEvent]`, plus `collect(events, *, provider, request) -> UpstreamResult` (D11, Section 6.4; the keywords carry the D8 estimate and the tools= gate, STORY-013).
- [ ] `OpenAICompatibleAdapter`: today's `call_openrouter` body, parameterized by provider. `complete()` is what the pipeline calls. `stream()` is implemented and tested against the stub, but no production code calls it in this PRD.
- [ ] Keyless providers send no `Authorization` header. `follow_redirects=False` is stated and tested (T1).
- [ ] `usage_missing: estimate | error` (D8). Error strings are prefixed with the provider's `label` (the implicit `"OpenRouter"` keeps today's strings).
- [ ] `openrouter_client.py` re-exports `call_openrouter`, `OpenRouterError`, `OpenRouterResult`, `GenerationParams`, `ToolParams`, `UnsupportedParameterError` as aliases, so every existing import and injected stub keeps working.

**Pipeline (`app/services/query_pipeline.py`)**
- [ ] Step 2: `authorize_model` becomes `authorize_route(identity, model) -> Route`. The denial is the same `query:model:{model}` verdict for "unknown" and "not permitted" (T3).
- [ ] Step 2: BYOK is allowed only on a provider with `byok: true`. Otherwise the forbidden verdict carries the label `query:byok:{provider}` (D10).
- [ ] Step 3: when the model declares `max_context_tokens`, an estimated-token check (D9).
- [ ] Step 6: when a provider is `trust: internal` and `pii: relaxed`, input redaction and the redaction size limit are skipped; output redaction is unchanged (D7).
- [ ] Step 7: the injected-callable seam keeps its `(messages, model, api_key, **kw)` signature (D12).
- [ ] Step 7b: an estimated usage is charged as unsplit tokens.
- [ ] Every row from step 2 onward carries the new audit fields.

**Audit (`app/db/models.py`, `app/db/database.py`, `app/services/audit_logger.py`)**
- [ ] Five `AUDIT_LOGS_ADDED_COLUMNS` entries, also declared in `CREATE_AUDIT_LOGS_TABLE`: `provider`, `upstream_model`, `provider_trust`, `pii_input_relaxed`, `usage_estimated` (D13).
- [ ] `_SUMMARY_SQL`'s `json_object` gains the five keys (`database.py:1330-1332`: a missing key is a `KeyError` in `_row_to_audit_log`). `AuditLog`, the audit query API entry and the admin Register row gain `provider`.

**Ingresses**
- [ ] `/v1`: tool capability from the registry. `GET /v1/models` and `GET /v1/models/{id}` are filtered per role and carry a `harness` extension in file mode. Legacy mode stays byte-identical (D14).
- [ ] `/query`: `model` defaults to the deployment default (`"gpt-4"` in legacy mode, as today; D15). The `openrouter_api_key` field name is unchanged.
- [ ] Chat UI: in file mode the selector lists `visible_models(identity)`. Legacy mode keeps `chat_ui/chat_ui/config.py`'s list.

**Settings (`app/config.py`)**
- [ ] `PROVIDERS_FILE: str = ""`.
- [ ] `OPENROUTER_API_KEY` becomes `str = ""`. It is required (startup error) when `PROVIDERS_FILE` is empty, or when a provider's `key_env` names it.
- [ ] In file mode, `OPENROUTER_BASE_URL`, `OPENROUTER_TIMEOUT_SECONDS` (except as the default `timeout_seconds`), `MODEL_ALLOWLIST` and `V1_TOOL_MODELS` are not read. A non-empty `V1_TOOL_MODELS` together with `PROVIDERS_FILE` is a startup error (D6).

**Stub upstream and tests**
- [ ] `scripts/stub_openrouter.py`: a reply may set `"usage": null` (omit the key), a request with `"stream": true` is answered as SSE, and the log line gains `auth=yes|no` (presence only, never the value). Two stubs in one process route two providers (`make_server` already isolates them, `:399`).
- [ ] An opt-in E2E run (`--run-e2e`) against a real Ollama (D16).

**Documentation**
- [ ] `docs/configuration.md` (`PROVIDERS_FILE`, the changed `OPENROUTER_API_KEY` row), a new `docs/features.md` "Providers" section with recipes for Ollama, vLLM, LM Studio, llama.cpp server, LocalAI and a hosted OpenAI-compatible cloud, `examples/providers.yaml`, `.env.example`, and the README.

### Out of Scope

- [ ] Native adapters: Anthropic Messages, Gemini, Bedrock (PRD-022). `type:` values other than `openai_compatible` are a startup error naming PRD-022.
- [ ] Fallback between providers, retries across providers, and the provider circuit breaker (PRD-022, bound by Section 6.8).
- [ ] Real-time streaming to the client (PRD-021). Harness output stays buffered (PRD-015 D8).
- [ ] LiteLLM or any multi-provider SDK (D2).
- [ ] Azure OpenAI's deployment-path and `api-version` URL scheme, and arbitrary extra request headers (Open decision O5).
- [ ] Hot reload of the registry; an admin UI to edit it; storing providers in the database.
- [ ] Startup or periodic health probes of providers (Future).
- [ ] Per-provider cost accounting in money; budgets per provider (Future).
- [ ] BYOK on `/v1` or in the chat UI (unchanged, `docs/features.md:249`).
- [ ] Forwarding `reasoning` or other generation parameters beyond PRD-010's four (`openrouter_client.py:11`). The `reasoning` capability is informational.
- [ ] A cap on upstream response size (Future; unchanged from today).

## 5. User Stories

1. **As a platform operator, I want to add a local Ollama next to OpenRouter, so that some traffic never leaves the machine.**
   *Example:* `providers.yaml` lists `openrouter` (key `OPENROUTER_API_KEY`) and `ollama` (`http://127.0.0.1:11434/v1`, no `key_env`). A `/v1` request for `ollama/qwen2.5-coder:7b` reaches Ollama as model `qwen2.5-coder:7b` with no `Authorization` header. A request for `openai/gpt-4o` still reaches OpenRouter. The two rows say `provider='ollama'` and `provider='openrouter'`.

2. **As a platform operator upgrading the harness, I want nothing to change until I write a registry, so that the upgrade is safe.**
   *Example:* no `PROVIDERS_FILE`. `GET /v1/models` returns exactly today's body, an upstream 503 is still `OpenRouter request failed: …` in `error_message`, and the only difference in a new row is `provider='openrouter'`, `provider_trust='external'`.

3. **As a security admin, I want redaction to stay on for every provider unless I say otherwise, so that adding a provider never silently weakens PII handling.**
   *Example:* `ollama` is `trust: internal` but has no `pii:` key, so an email in a `/v1` prompt is masked before Ollama sees it. After the admin adds `pii: relaxed`, the same prompt reaches Ollama unmasked and the row has `pii_input_relaxed=1`. Setting `pii: relaxed` on `openrouter` fails startup.

4. **As a platform operator, I want a GPU box on the LAN reachable over plain HTTP only when I opt in, so that a typo cannot send a key over plaintext.**
   *Example:* `base_url: http://192.168.1.40:8000/v1` without `insecure_http: true` is a startup error that quotes the scheme and host and says whoever controls that host receives the key. With the opt-in it boots and logs a WARNING once. `http://gpu.lan:8000/v1` is refused even with the opt-in (hostname over plaintext, D5).

5. **As a security admin, I want a provider that reports no usage to still count against the daily budget, so that a local model cannot be used to escape it.**
   *Example:* a llama.cpp build returns no `usage`. The adapter estimates 1,240 tokens from characters sent and received, the user's `unsplit_tokens` grows by 1,240, and the row has `tokens_used=1240`, `input_tokens=NULL`, `usage_estimated=1`.

6. **As an integrating developer, I want `GET /v1/models` to show what I can use and what each model can do, so that my agent is configured correctly.**
   *Example:* a `user` sees `openai/gpt-4o` and `ollama/qwen2.5-coder:7b`, but not `lan/llama-3.1-70b` (admin only). Each entry carries `harness: {provider, capabilities: {tools, streaming, reasoning, max_context_tokens}}`. A `tools` request to a model with `tools: false` is `400 tools_not_supported`.

7. **As an auditor, I want every row to say which provider answered and under what trust, so that "where did this prompt go" has an answer even after the registry changes.**
   *Example:* the Register shows `provider` on each row. A filtered audit read shows `provider_trust='internal'`, `pii_input_relaxed=1` for last week's Ollama traffic, as recorded at the time.

8. **As an admin with BYOK, I want my own key used only with the provider that accepts it, so that it is never sent to a host I did not intend.**
   *Example:* `/query` with `openrouter_api_key` and model `openai/gpt-4o` uses the key with OpenRouter. The same body with `ollama/qwen2.5-coder:7b` is a forbidden verdict `query:byok:ollama`, and nothing goes upstream.

## 6. Core Architecture & Patterns

### 6.1 Where the registry sits in the pipeline

```
0. structural validation
1. dedup_key, conversation_key
2. authorize(query:submit)
   route = authorize_route(identity, model)       NEW: registry lookup + per-role check  (D3, D4)
   BYOK: query:byok AND route.provider.byok         NEW: label query:byok:{provider}       (D10)
2b. break-glass   2c. usage admission (BYOK not budget-charged, unchanged)
3. context limits; + estimated tokens vs route.model.max_context_tokens                    (D9)
4. duplicate   5. patterns (unchanged; not provider-dependent)
6. redact input per profile — SKIPPED iff route.relaxes_input()                            (D7)
7. upstream: call_openrouter seam → upstream.call_upstream → registry.resolve → adapter.complete
7b. charge (estimated usage → unsplit)   7c. actions (unchanged)
8. redact output per profile (unchanged), audit row with provider fields, return
```

The route is resolved once at step 2 and carried in a local, as `profile_name` is (`query_pipeline.py:353`). Every row written after step 2 records it. The step 2 denial rows and every earlier row have `provider` NULL, which is the truth: no provider was chosen. Patterns (step 5) stay provider-independent. They protect the deployment from the prompt, not the prompt from the provider.

### 6.2 Legacy mode is a registry (D1)

With `PROVIDERS_FILE` empty, `provider_registry.load()` builds this from settings and nothing else:

```yaml
default_model: gpt-4                        # QueryRequest.model's default today (schemas.py:18)
providers:
  - name: openrouter
    label: OpenRouter                       # error strings stay "OpenRouter request failed: ..."
    type: openai_compatible
    base_url: ${OPENROUTER_BASE_URL}        # its existing validator still applies
    key_env: OPENROUTER_API_KEY
    timeout_seconds: ${OPENROUTER_TIMEOUT_SECONDS}
    trust: external
    pii: standard
    byok: true
    passthrough: true                       # admin's any-model allowance keeps working
    usage_missing: error                    # today's behaviour (openrouter_client.py:310-316)
    models:                                 # one per MODEL_ALLOWLIST entry, upstream = id
      - id: <each MODEL_ALLOWLIST entry>
        capabilities: {tools: <V1_TOOL_MODELS empty or id listed>}
```

So one code path serves both modes, and legacy behaviour is a property of the data, not of a branch. Byte-identical regression tests pin the payload, headers, error strings, `/v1/models` body and verdicts in legacy mode.

### 6.3 Routing (D3)

```
resolve(model):
  1. catalogue[model]                     exact, case-sensitive; ids unique across the registry
  2. else the passthrough provider        at most one; upstream = model as sent
  3. else unresolved                      → step 2 denies query:model:{model}
```

There is no prefix parsing. `openai/gpt-4o` is an OpenRouter id whose `openai/` is OpenRouter's vendor namespace, not a provider, and parsing it as one would break every existing allowlist. The `<provider>/<model>` spelling is a recommended *convention* for new ids (`ollama/qwen2.5-coder:7b`), and `upstream:` carries the name the provider expects. A caller cannot reach a provider the catalogue does not route to, and cannot name a host.

### 6.4 The adapter interface (D11, for PRD-021)

```python
@dataclass(frozen=True)
class UpstreamRequest:
    messages: Sequence[Message]
    upstream_model: str
    params: Optional[GenerationParams]
    tools: Optional[ToolParams]

class ProviderAdapter(Protocol):
    def complete(self, request: UpstreamRequest, api_key: Optional[str]) -> UpstreamResult: ...
    def stream(self, request: UpstreamRequest, api_key: Optional[str]) -> Iterator[UpstreamEvent]: ...

UpstreamEvent = TextDelta(text) | ToolCallDelta(index, id?, name?, arguments)   # STORY-013: one fragment per event
              | UsageReport(prompt_tokens?, completion_tokens?, total_tokens?) | Finish(reason?)

def collect(events: Iterable[UpstreamEvent], *, provider: Provider, request: UpstreamRequest) -> UpstreamResult
                                                                # pure; same parsing rules as complete()
                                                                # (STORY-013: keyword-only provider/request for the D8 estimate and the tools= gate)
```

- **Synchronous iterators, not async.** The pipeline runs synchronously on the dedicated executor (`pipeline_executor.py:3-11`). PRD-021 consumes the iterator on that thread and hands deltas to the event loop. An async interface would force a rewrite of the pipeline, not of the adapter.
- **Normalized events, not raw SSE lines.** PRD-021's incremental action evaluation (PRD-017 Future) needs tool-call fragments assembled per `index`, which is the adapter's job, so it is done once here.
- **`collect()` applies `complete()`'s rules exactly.** That covers `content: null` with calls → `""`, arguments as given and never parsed (PRD-017 D13), duplicate ids refused, and the D8 usage rule. A property test asserts `collect(stream(r)) == complete(r)` for every stub script in the suite.
- **This PRD's production path calls `complete()` only**, which sends no `stream` key, exactly as today (`stub_openrouter.py:63-64`). `stream()` sends `stream: true` and `stream_options: {include_usage: true}`, and is exercised by tests against the stub.

### 6.5 Directory layout

```
app/services/provider_registry.py          load(), Provider, CatalogModel, Route, resolve(), visible_models()
app/services/upstream/__init__.py          call_upstream(), UpstreamError, UpstreamResult, collect()
app/services/upstream/params.py            GenerationParams, ToolParams, UnsupportedParameterError (moved, unchanged)
app/services/upstream/openai_compatible.py OpenAICompatibleAdapter (today's call_openrouter body)
app/services/usage_estimate.py             estimate_tokens(...) — pure (D8)
app/services/openrouter_client.py          shim: aliases only; nothing new may import it
examples/providers.yaml                    the Section 7 example
```

`call_upstream(messages, model, api_key=None, params=None, client=None, *, tools=None)` has `call_openrouter`'s exact signature (`openrouter_client.py:219-227`). It resolves `model` through the registry, chooses the key (D10), and calls the provider's adapter. `call_openrouter = call_upstream` in the shim.

### 6.6 PII relaxation (D7)

| Step | `chat` (standard) | `chat`, relaxed provider | `code` (standard) | `code`, relaxed provider |
|---|---|---|---|---|
| 6, input roles redacted | every role | **none** | user, assistant, tool (+system per `PII_CODE_REDACT_SYSTEM`) | **none** |
| 6, size limit (`PII_MAX_CHARACTERS_CODE`) | n/a | n/a | enforced, fail closed | **not applied** (it bounds analysis that does not run) |
| 8, output redaction | on | **on (unchanged)** | `PII_CODE_REDACT_OUTPUT` | **unchanged** |
| 5, patterns | unchanged | unchanged | unchanged | unchanged |
| Audit | `pii_input_relaxed=0` | `pii_input_relaxed=1`, `pii_detected_input=0` means *not analyzed* | 0 | 1 |

Relaxation is decided by `route.relaxes_input()`, which is true iff `PII_REDACTION_ENABLED` and `provider.trust == "internal"` and `provider.pii == "relaxed"`. It is never decided by a request field, a role, the profile, or the host's address. Output redaction stays because it protects the *reader* of the response (the chat transcript, PRD-003), and where the model runs does not change who reads it. Under `chat` this means a user may see their own name masked in a local model's answer. That is the strict direction (Open decision O2).

### 6.7 Usage when the provider reports none (D8)

```
estimate_tokens(sent, received, chars_per_token):
  sent_chars     = Σ len(content) over the messages sent upstream (after step 6)
                 + Σ len(arguments) over history tool_calls + len(json.dumps(tools)) when sent
  received_chars = len(content) + Σ len(arguments) over response tool_calls
  return ceil(sent_chars / chars_per_token) + ceil(received_chars / chars_per_token)
```

| Upstream `usage` | `usage_missing: error` (legacy default) | `usage_missing: estimate` (file default) |
|---|---|---|
| total present (split or not) | today: total, split if valid | same |
| absent, `null`, or no `total_tokens` but both splits valid | `UpstreamError`, today's message | total = split sum, if both valid; else estimate |
| absent / unusable | `UpstreamError` | estimate; `usage_estimated=1`; split NULL; charged as `unsplit_tokens` |

`unsplit_tokens` is documented as "total_tokens of calls with no split reported" (`app/db/models.py:230`), which is literally true of an estimate, so `usage_daily` needs no change. `/v1`'s `usage` reports `0/0/estimate`, as it already does for a missing split (`v1_translate.py:617-628`), and `harness.usage_estimated: true` is added only when true.

### 6.8 The constraint this PRD places on PRD-022 (fallback)

A provider's `trust` is recorded per row and is the input PRD-022's fallback policy must read. The binding rules:

1. **Never automatic across trust levels.** Falling back from an `internal` provider to an `external` one sends data that was never meant to leave the network. Fallback across trust levels must be an explicit, per-pair policy entry, never a default.
2. **Redaction is computed for the provider that receives the data.** A request redacted for (or relaxed for) provider A must not be resent to provider B without re-running step 6 for B. Relaxed input must never reach an external provider.
3. **A BYOK key never follows a fallback.** It belongs to the provider it was sent for (D10).
4. **Each attempt is audited with its own provider.** One row per upstream attempt, as `/v1` retries already write one row each (`docs/features.md:280`).

## 7. Tools/Features

### F1 — Registry file

```yaml
# examples/providers.yaml — PROVIDERS_FILE=examples/providers.yaml
version: 1
default_model: openai/gpt-4o
providers:
  - name: openrouter                   # [a-z0-9][a-z0-9_-]{0,31}; unique
    label: OpenRouter                  # error-message prefix; default = name
    type: openai_compatible            # the only accepted type (D2)
    base_url: https://openrouter.ai/api/v1
    key_env: OPENROUTER_API_KEY        # env var NAME, never the key; absent = keyless
    trust: external                    # external (default) | internal
    byok: true                         # default false
    passthrough: true                  # at most one provider; default false
    models:
      - id: openai/gpt-4o
        capabilities: {tools: true, max_context_tokens: 128000}
      - id: anthropic/claude-3.5-sonnet
        capabilities: {tools: true}

  - name: ollama
    type: openai_compatible
    base_url: http://127.0.0.1:11434/v1    # loopback http: allowed without opt-in
    trust: internal
    pii: relaxed                           # standard (default) | relaxed; relaxed requires internal
    usage_missing: estimate                # estimate (default in file) | error
    estimate_chars_per_token: 4            # (0, 8]; default 4
    timeout_seconds: 300                   # default OPENROUTER_TIMEOUT_SECONDS; cold model loads are slow
    models:
      - id: ollama/qwen2.5-coder:7b
        upstream: qwen2.5-coder:7b         # name sent upstream; default = id
        capabilities: {tools: true, streaming: true, max_context_tokens: 32768}

  - name: gpu-box
    type: openai_compatible
    base_url: http://192.168.1.40:8000/v1
    insecure_http: true                    # private-network plaintext opt-in (D5)
    key_env: VLLM_API_KEY
    trust: internal
    roles: [admin, user]                   # provider default for its models
    models:
      - id: lan/llama-3.1-70b
        upstream: meta-llama/Llama-3.1-70B-Instruct
        roles: [admin]                     # overrides the provider's roles
```

Startup errors (each names the file, the provider or model, and the rule, never a key value):
- unknown key at any level; a missing `name`, `type`, `base_url`, or `models` (except on a `passthrough` provider); `version` ≠ 1
- a duplicate provider `name` or model `id`; more than one `passthrough`; a `default_model` that is neither catalogued nor routable by passthrough
- `type` ≠ `openai_compatible` (the message names PRD-022)
- a `base_url` failing D5; a `key_env` that names an unset or empty variable (a keyless provider omits `key_env`)
- `pii: relaxed` without `trust: internal`; `trust: internal` on a public IP literal (D7)
- `byok: true` together with `passthrough: false` and no models (unusable)
- `max_context_tokens` < 1; `estimate_chars_per_token` outside (0, 8]; `timeout_seconds` ≤ 0
- a `roles:` entry that is not an RBAC role, or an empty `roles: []` (orchestrator decision, STORY-003: a typo must not silently lock everyone out)
- `V1_TOOL_MODELS` non-empty while `PROVIDERS_FILE` is set (D6)

Startup WARNINGs (logged once, never fatal): an `insecure_http` provider (naming scheme and host); `trust: internal` on a hostname (it cannot be verified); a `key_env` that the loaded action policy's `secrets.env` globs do not match (`action_config.py:324-335`), so an agent's `echo $THAT_KEY` would not be `secret.read`.

### F2 — Per-role access (D4)

The effective roles for a model are `model.roles`, else `provider.roles`, else every role. A role outside that set is denied `query:model:{id}`, as today. `MODEL_ALLOWLIST_WILDCARD_ROLES` (`authz.py:76-78`) keeps its meaning: those roles may use any catalogued model and any passthrough model. `RBAC_ENABLED=false` still bypasses the model check (`authz.py:194-195`), but routing still applies: an unresolvable model is refused even with RBAC off, because there is nowhere to send it. Uncatalogued (passthrough) models are permitted only to `MODEL_ALLOWLIST_WILDCARD_ROLES`; `provider.roles` and `model.roles` apply to catalogued models, which keeps legacy (`passthrough: true`) identical (orchestrator decision OD3).

### F3 — Transport and keys (D5)

| `base_url` | Accepted when |
|---|---|
| `https://<any host>` | always |
| `http://` on `127.0.0.1`, `localhost`, `::1` | always (today's rule, `config.py:89-92`) |
| `http://` on a private IP **literal** (10/8, 172.16/12, 192.168/16, fc00::/7) | only with `insecure_http: true` |
| `http://` on any hostname, or a public IP | never |

The adapter builds `httpx.Client(timeout=provider.timeout_seconds, follow_redirects=False)`, so a 30x is an upstream error and is never followed with the key attached. A keyless provider sends no `Authorization` header at all. Validator messages quote the scheme and host only (`config.py:499-501`'s rule).

### F4 — Capabilities (D6)

| Capability | Default (file) | Used by |
|---|---|---|
| `tools` | `false` | `/v1` translator's model check (today's `V1_TOOL_MODELS` check, `v1_translate.py:516`) |
| `streaming` | `false` | exposed; PRD-021 reads it |
| `reasoning` | `false` | exposed only |
| `max_context_tokens` | unset | step 3 estimated check (D9); exposed |

A passthrough model gets the passthrough provider's `passthrough_capabilities:` (default all false). The legacy provider's passthrough tools capability is `V1_TOOL_MODELS` empty, which preserves `config.py:690-695`'s rule that a set list binds `admin` too.

### F5 — Audit (D13)

| Column | Type | Meaning |
|---|---|---|
| `provider` | `TEXT` | registry name; NULL before routing (step 0–2 rows, denials) |
| `upstream_model` | `TEXT` | the name sent upstream; NULL when `provider` is |
| `provider_trust` | `TEXT` | `external` / `internal` at the time of the call |
| `pii_input_relaxed` | `INTEGER NOT NULL DEFAULT 0` | step 6 was skipped for this provider |
| `usage_estimated` | `INTEGER NOT NULL DEFAULT 0` | `tokens_used` is D8's estimate |

`model_used` keeps meaning "the id the caller asked for". The upstream-error arm records `provider` and `upstream_model` too. A row written before this PRD stays NULL / 0 and is never backfilled. `0` is true of every earlier row: neither relaxation nor estimation existed.

### F6 — Stub upstream

`"usage": null` in a reply omits the key. A request with `"stream": true` gets an SSE body with the content in two deltas, each call's arguments split across two fragments, a usage chunk when `stream_options.include_usage` is set, then `[DONE]`. The log line gains `auth=yes|no` and `stream=yes|no` (presence only). A test asserts no header value is ever written.

## 8. Technology Stack

| Layer | Choice | Note |
|---|---|---|
| Wire format | OpenAI Chat Completions (`/chat/completions`, Bearer auth, SSE for `stream()`) | The de facto standard; spoken by OpenRouter, Ollama, vLLM, LM Studio, llama.cpp server, LocalAI, most clouds |
| HTTP | `httpx` (already pinned) | Same client as today; `follow_redirects=False` made explicit |
| Config | YAML via `app/services/strict_yaml.py` | The `PATTERNS_FILE` / `ACTION_POLICY_FILE` shape; duplicate keys refused |
| No new dependency | — | LiteLLM rejected (D2); no tokenizer library (D8) |
| Tests | `pytest`; two in-process stubs; E2E opt-in `--run-e2e` | E2E needs Ollama on `127.0.0.1:11434` with the pinned model pulled; skipped (never failed) when absent |

## 9. Security & Configuration

### 9.1 Authentication & authorization

Unchanged: identity, `query:submit`, break-glass, usage admission. The model check becomes a route check (F2). BYOK additionally requires `provider.byok` (D10). No new permission is added to `_KNOWN_PERMISSIONS`. `query:byok:{provider}` is a row label, like `query:model:{model}` and `ingress:break_glass` (`query_pipeline.py:413-416`).

### 9.2 Threat reasoning

| # | Threat | Treatment |
|---|---|---|
| T1 | **Key exfiltration through the base URL**: a registry edit or a 30x redirect sends a key to an attacker's host | The registry is operator-only (a file, read at startup). D5's scheme/host rule. `follow_redirects=False`, tested. Each key goes only to its own provider's `base_url`. The docs keep the warning: **whoever controls a provider's host receives its key and every prompt routed to it** |
| T2 | **Plaintext on the LAN**: key and prompts readable on the wire | `http://` beyond loopback needs `insecure_http: true` and a private IP literal (a hostname can be redirected by DNS). WARNING at startup. Stated in the docs as "the network sees everything" |
| T3 | **Caller-chosen routing**: a model string that steers to another host, or probes the catalogue | Exact lookup in an operator catalogue. No prefix parsing, no URL in any request field. Unknown and not-permitted are the same verdict, and `/v1/models/{id}` 404s for both |
| T4 | **PII to an external provider through misconfiguration** | Relaxation needs `trust: internal` **and** `pii: relaxed`. `relaxed` on `external` and `internal` on a public IP literal are startup errors. The default is `standard`. Every relaxed row is flagged `pii_input_relaxed=1` |
| T5 | **Budget escape through a provider without usage** | D8: estimate, never zero. `usage_estimated` marks it. `error` mode is available for providers that must report |
| T6 | **BYOK key sent to the wrong provider** | Used only with the resolved provider and only when `byok: true`; otherwise a forbidden verdict before step 7. Never logged (unchanged) |
| T7 | **A local server's non-conformant response** (arguments as an object, missing ids) | The same parser as today: shape errors are non-retryable `UpstreamError`s naming the field, never a value. Arguments are never coerced (PRD-017 D13) |
| T8 | **Audit ambiguity after a registry change** | `provider`, `upstream_model` and `provider_trust` are stored per row at call time, not joined from config |
| T9 | **SSRF via configuration**: an internal admin endpoint used as a provider | Operator-only config. Same trust as `OPENROUTER_BASE_URL` today. Not request-controlled |
| T10 | **Context silently truncated by a small-context local model** (drops the system prompt or early turns) | `max_context_tokens` makes it a refusal at step 3 (D9). Unverified per server (Section 15) |
| T11 | **A key env var an agent can read** | WARNING when `key_env` is not matched by `secrets.env` (F1). The built-in `*KEY*`/`*TOKEN*` globs cover conventional names |

### 9.3 Configuration

| Variable | Default | Validation | Purpose |
|---|---|---|---|
| `PROVIDERS_FILE` | `""` | file readable and valid (F1), or startup error | The registry; empty = implicit OpenRouter provider |
| `OPENROUTER_API_KEY` | `""` (was required) | required when `PROVIDERS_FILE` is empty or a `key_env` names it | The legacy provider's key |
| `OPENROUTER_BASE_URL`, `MODEL_ALLOWLIST`, `V1_TOOL_MODELS` | unchanged | unchanged; ignored in file mode; `V1_TOOL_MODELS` must be empty there | Legacy mode only |
| `OPENROUTER_TIMEOUT_SECONDS` | unchanged | unchanged | Legacy timeout; default `timeout_seconds` in file mode |

`.env.example` gains `PROVIDERS_FILE=` with a three-line comment and the key warning. `docs/configuration.md:13`'s "Required: Yes" for `OPENROUTER_API_KEY` becomes "Yes, unless `PROVIDERS_FILE` is set and no provider uses it".

### 9.4 Out of scope (security)

mTLS or custom CA bundles for providers. Egress allowlisting at the network layer. Signing or verifying provider responses. Inspecting what a self-hosted model does with prompts (that is what `trust: internal` asserts, and the operator owns the assertion).

## 10. API Specification

**`GET /v1/models`**, file mode, caller role `user`:

```json
{"object": "list", "data": [
  {"id": "openai/gpt-4o", "object": "model", "created": 0, "owned_by": "openrouter",
   "harness": {"provider": "openrouter",
               "capabilities": {"tools": true, "streaming": false, "reasoning": false, "max_context_tokens": 128000}}},
  {"id": "ollama/qwen2.5-coder:7b", "object": "model", "created": 0, "owned_by": "ollama",
   "harness": {"provider": "ollama",
               "capabilities": {"tools": true, "streaming": true, "reasoning": false, "max_context_tokens": 32768}}}
]}
```

In legacy mode the body is today's byte for byte: `owned_by` is the prefix before `/` or `harness` (`v1.py:362-365`), there is no `harness` key, and every role sees `MODEL_ALLOWLIST`. Passthrough models are not listed ("any" cannot be listed, `v1.py:396-397`). `GET /v1/models/{id}` returns the entry, or `404 model_not_found` when the id is not catalogued **or** not visible to the caller.

**`POST /v1/chat/completions`**: unchanged shape. When `usage_estimated`, the body adds `"harness": {..., "usage_estimated": true}`. A `tools` request for a model with `tools: false` is `400 tools_not_supported`, `param: "tools"`, with the message `model is not enabled for tool calling` in file mode (the legacy message, `v1_translate.py:155`, is unchanged).

**`POST /query`**: `model` is optional, defaulting to the registry's `default_model` (`"gpt-4"` in legacy mode, D15). BYOK refusal on a non-BYOK provider:

```json
{"status": "BLOCKED", "reason": "Missing required permission",
 "required_permission": "query:byok:ollama"}
```

The D9 refusal is the existing `QueryBlockedContextLimitResponse` with its `limit` literal (`app/models/schemas.py:145`, today `messages | characters | redaction_characters`) widened by `estimated_tokens`; `maximum` is `max_context_tokens`, `actual` the estimate.

**Audit read API** (`GET /audit`, admin Register): each entry gains `provider`, `upstream_model`, `provider_trust`, `pii_input_relaxed`, `usage_estimated`.

Internal API:

```python
provider_registry.load() -> None                                       # startup, both lifespans
provider_registry.resolve(model: str) -> Optional[Route]
provider_registry.visible_models(identity) -> list[CatalogModel]
authz.authorize_route(identity, model) -> Route                        # raises PermissionDenied("query:model:<m>")
upstream.call_upstream(messages, model, api_key=None, params=None, client=None, *, tools=None) -> UpstreamResult
upstream.collect(events) -> UpstreamResult
usage_estimate.estimate_tokens(sent, received, chars_per_token) -> int
```

## 11. Success Criteria

### MVP definition

With `PROVIDERS_FILE` naming the stub as `openrouter` and a second stub as `local` (keyless, `trust: internal`), `/query`, the chat UI and `/v1` (text and tools) route by id, record the provider, and honour roles, BYOK and relaxation as specified. An opt-in E2E against a real Ollama passes. With no `PROVIDERS_FILE`, the full existing suite passes with no assertion changed except the new audit fields.

### Functional requirements

- [ ] Legacy mode: upstream payload, headers, error strings, `/v1/models` body, verdicts and `QuerySuccessResponse` byte-identical to `main` (recorded fixtures)
- [ ] Legacy mode: rows carry `provider='openrouter'`, `upstream_model=model_used`, `provider_trust='external'`, `0`, `0`
- [ ] Every F1 startup error has a test, and none echoes a key value or a whole URL
- [ ] Routing: catalogued id → its provider with `upstream`; uncatalogued → passthrough or `query:model:` denial; an `openai/…` id never routes to a provider named `openai`
- [ ] Per-role: `model.roles` overrides `provider.roles`; admin wildcard; RBAC off still refuses unroutable ids
- [ ] Keyless provider: the stub logs `auth=no`. Keyed: `auth=yes` and the key goes to that stub only (two stubs, two keys, cross-checked)
- [ ] `http://192.168.x.y` refused without `insecure_http`, accepted with it; `http://host.lan` refused either way; a 302 from the stub is an `UpstreamError`, not followed
- [ ] Relaxed provider: an email reaches the stub unmasked under `chat` and `code`; output redaction under `chat` still masks; `pii_input_relaxed=1`; the same request to a `standard` internal provider is masked
- [ ] `usage: null` from the stub → `usage_estimated=1`, `tokens_used` = D8 formula, `unsplit_tokens` charged; under `usage_missing: error` → `UpstreamError`, today's message
- [ ] `max_context_tokens` exceeded → `QueryBlockedContextLimitResponse` with `limit="estimated_tokens"`, nothing upstream
- [ ] BYOK on a `byok: false` provider → `query:byok:<name>` row, nothing upstream, nothing charged
- [ ] `tools` to a `tools: false` model → `400 tools_not_supported`; `V1_TOOL_MODELS` + `PROVIDERS_FILE` → startup error
- [ ] `GET /v1/models` lists only role-visible catalogued models with the `harness` extension; `/v1/models/{id}` 404s for an invisible one
- [ ] `collect(stream(r)) == complete(r)` for every stub script in `tests/e2e/scripts/` and the suite's tool scripts
- [ ] Chat UI selector shows `visible_models` in file mode, `chat_ui/chat_ui/config.py`'s list in legacy mode
- [ ] **E2E (opt-in): real Ollama** at `127.0.0.1:11434` with a pinned small tool-capable model. A `/query` answer, a `/v1` streamed-to-client (buffered) answer via the OpenAI SDK, and one `/v1` tool call released through the action policy. The rows say `provider='ollama'`, and the report records the Ollama version, the model digest, and whether `usage` was reported

### Quality indicators

- [ ] Full suite green in both modes (file-mode tests use the shared `tests/_providers.py` fixture in the regular CI job, with no second full-suite job; orchestrator decision OD2)
- [ ] `provider_registry` resolution and `usage_estimate` are pure (no I/O after `load()`); `upstream.collect` is pure
- [ ] No new runtime dependency in `requirements.txt`
- [ ] Each changed pre-existing assertion carries a comment citing PRD-020 and the decision

## 12. Implementation Phases

### Phase 1 — Registry and legacy equivalence
**Goal:** the registry exists and legacy mode is provably today.
**Deliverables:** `PROVIDERS_FILE`, `OPENROUTER_API_KEY` relaxed with its conditional requirement, `provider_registry.load()` with every F1 validation and the legacy builder, and the byte-identical fixtures recorded *before* any refactor.
**Validation:** startup-error tests; the fixtures pass against the unchanged client.

### Phase 2 — Adapter and routing
**Goal:** requests reach the right provider with the right key.
**Deliverables:** the `upstream` package (params moved, `OpenAICompatibleAdapter.complete`, `call_upstream`, shim), D5 transport, keyless, step 2 `authorize_route` and BYOK, audit columns and `log_query` fields, the stub's `auth=`/`usage: null`.
**Validation:** two-stub routing tests; legacy fixtures still green.

### Phase 3 — Policies that depend on the provider
**Goal:** PII, usage, context and capabilities follow the provider.
**Deliverables:** step 6 relaxation, D8 estimate and charge, step 3 `max_context_tokens`, the capability check on `/v1`, `/v1/models` per role with the extension, the chat UI selector, the Register `provider` field.
**Validation:** Section 11 functional list.

### Phase 4 — Streaming interface, E2E, docs
**Goal:** PRD-021 inherits a tested `stream()`, and operators can set up local models.
**Deliverables:** `stream()`, `collect()`, the stub's SSE mode and the equivalence test, Ollama E2E, docs, `examples/providers.yaml`, `.env.example`.
**Validation:** E2E report; full suite in both modes.

## 13. Future Considerations

- **PRD-021**: real streaming, pipeline consumption of `stream()`, and per-model `streaming` gating.
- **PRD-022**: Anthropic/Gemini/Bedrock adapters behind the same protocol, policy-controlled fallback (Section 6.8), and a per-provider circuit breaker.
- `scripts/providers.py check`: list the resolved registry and probe each provider's `GET /models`. Operators would see a dead local server before users do.
- Per-provider daily budgets and cost per token; a `provider` filter and figure in the admin console.
- Azure OpenAI URL scheme, static extra headers sourced from env vars (O5).
- Hot reload of `PROVIDERS_FILE` with an atomic snapshot swap.
- A response-size cap per provider.

## 14. Risks & Mitigations

| # | Risk | Likelihood / Impact | Mitigation |
|---|---|---|---|
| 1 | **Legacy drift**: the refactor changes a byte an existing client or test relies on | Medium / High | Fixtures recorded first (Phase 1); legacy mode is data, not a branch (6.2); the shim keeps every import |
| 2 | **"OpenAI-compatible" is not uniform**: a local server rejects `parallel_tool_calls`, returns arguments as objects, or omits `id` | High / Medium | Failures are clear non-retryable errors naming the field; `tools: false` is the file default; the E2E records a real server's shapes; per-server quirks go to docs, not code, until data says otherwise |
| 3 | **Character estimate under-counts** (CJK text runs ~1 char/token) | Medium / Low–Medium | `estimate_chars_per_token` per provider; `usage_estimated` makes every estimate auditable; the budget's purpose for a local GPU is fairness, not money |
| 4 | **Operators over-use `trust: internal` / `pii: relaxed`** | Medium / High | Two explicit keys, startup refusal on public IP literals, a hostname WARNING, a per-row flag, and docs that say what the claim means |
| 5 | **Slow local models time out** (cold load) | High / Low | Per-provider `timeout_seconds`; the docs recommend keeping the model loaded |
| 6 | **The step 2 refactor reorders verdicts** | Low / High | The route check takes `authorize_model`'s exact place and label; the existing verdict-order tests are unchanged |

## 15. Appendix

### Decisions

| # | Question | Decision |
|---|---|---|
| D1 | Backward compatibility | **No file, no change.** Without `PROVIDERS_FILE` the registry is one implicit `openrouter` provider built from today's settings (6.2), with `passthrough: true`, `usage_missing: error` and label `OpenRouter`, so strings, payloads and verdicts stay byte-identical |
| D2 | Adapter strategy | **One in-house `openai_compatible` adapter**, today's client parameterized. **Not LiteLLM**: a large, fast-moving dependency in the security path whose error mapping already turned harness `403`s into retryable errors in Aider (`docs/features.md:292`). Native adapters are PRD-022 |
| D3 | Model naming and routing | **Exact catalogue lookup, then one optional passthrough provider; never prefix parsing.** `provider/model` is a convention for new ids; `upstream:` maps to the provider's name. Existing `MODEL_ALLOWLIST` ids keep routing to OpenRouter |
| D4 | Per-role allowlists | **`model.roles` > `provider.roles` > every role**; admin wildcard kept for catalogued and passthrough models; one denial label for unknown and forbidden |
| D5 | Plaintext and LAN hosts | `https` always; loopback `http` always; **private IP literal `http` only with `insecure_http: true`**; hostnames over `http` never; `follow_redirects=False`; keyless providers send no `Authorization` |
| D6 | Capabilities | Per model `tools`/`streaming`/`reasoning`/`max_context_tokens`; file default all off. **`V1_TOOL_MODELS` is absorbed**: it feeds the legacy provider and is a startup error in file mode |
| D7 | PII trust | **Redaction stays on for every provider.** Relaxing needs `trust: internal` + `pii: relaxed`. Relaxed skips step 6 input redaction and the code size limit only; output redaction and patterns unchanged; audited per row (6.6) |
| D8 | Missing usage | **Estimate from characters (default 4/token), charged as unsplit, flagged `usage_estimated`.** Not refuse: that makes most self-hosted setups unusable. Not zero: that escapes the budget. Not a tokenizer: the harness has no per-model tokenizer, the same reason `CONTEXT_MAX_CHARACTERS` counts characters (`docs/configuration.md:33`). `error` mode remains, the legacy default |
| D9 | Context window | With `max_context_tokens` set, step 3 refuses when the D8 estimate of the conversation exceeds it, as `limit="estimated_tokens"` |
| D10 | BYOK with several providers | The `openrouter_api_key` field keeps its name and means "the caller's key for the resolved provider". It is allowed only where `byok: true` (the legacy provider: yes; file default: no), else `query:byok:{provider}`. Never sent elsewhere; budget rule unchanged |
| D11 | Streaming readiness | Adapter protocol with `complete()` **and** a sync `stream()` of normalized events plus pure `collect()`. This PRD calls only `complete()`; `stream()` is implemented and tested so PRD-021 does not rewrite the adapter |
| D12 | Test seam | `call_openrouter`'s signature is kept as `call_upstream`; the pipeline and the default callable each resolve the route from the same immutable snapshot |
| D13 | Audit | Five additive columns via `AUDIT_LOGS_ADDED_COLUMNS` + `CREATE_AUDIT_LOGS_TABLE` (the PRD-013/015 path, `database.py:730`); `model_used` unchanged in meaning |
| D14 | `/v1/models` | File mode: per-role filtered, `owned_by` = provider, `harness` extension with capabilities. Legacy: byte-identical |
| D15 | Default model | Registry `default_model`; `/query` and the chat UI use it; legacy `"gpt-4"` |
| D16 | Testing | The stub covers routing, keyless, `usage: null`, SSE; **an opt-in E2E against a real Ollama is a success criterion**, skipped when no server is present |

### Open decisions (proposed default)

- **O1** — Admin wildcard and per-provider restriction. *Proposed:* `MODEL_ALLOWLIST_WILDCARD_ROLES` still reaches every provider. An operator who wants to keep admins off a provider cannot, in this PRD.
- **O2** — Output redaction for a relaxed provider under `chat`. *Proposed:* stays on (the reader is unchanged). The alternative is to relax it too, so a user is not shown their own name masked.
- **O3** — `trust: internal` on hostnames (e.g. `vllm.default.svc`). *Proposed:* allowed with a startup WARNING. Public IP literals are refused.
- **O4** — Private ranges for `insecure_http`. *Proposed:* RFC 1918 and ULA only. CGNAT `100.64.0.0/10` (Tailscale) is **not** included.
- **O5** — Azure OpenAI and extra headers. *Proposed:* out of scope. If added later, header values come from env vars, never the file.
- **O6** — `tools` default for file-defined models. *Proposed:* `false` (claimed, not assumed). The alternative `true` gives an upstream error instead of a clear 400.
- **O7** — `estimate_chars_per_token` default. *Proposed:* 4, matching the documented English proxy. 3 would over-count instead.
- **O8** — Whether to add a `provider_api_key` alias for the `/query` BYOK field. *Proposed:* no. The name stays for compatibility and the docs explain it.

### Evidence (verified against `main` @ `2253871`)

- `app/services/openrouter_client.py:9` default model `gpt-4`; `:219-227` signature; `:235-239` key resolution and message; `:241-244` Bearer header; `:265` `httpx.Client(timeout=…)`, no `follow_redirects` argument; `:268` base URL per call; `:272-278` error classification; `:310-316` a missing `usage`/`total_tokens` raises; `:318-319` split optional.
- `app/config.py:89-92` loopback hosts; `:175` `OPENROUTER_API_KEY: str` required; `:210` `MODEL_ALLOWLIST`; `:240`, `:246` timeout and base URL; `:392` `V1_TOOL_MODELS`; `:489-531` base-URL validator; `:683-709` tool-models validator.
- `app/services/authz.py:76-78` wildcard roles; `:188-203` `authorize_model`.
- `app/services/query_pipeline.py:382-403` step 2 (model, BYOK); `:462` `charges_budget=openrouter_api_key is None`; `:658` policy lookup; `:711-748` input redaction; `:750-763` the seam; `:764-784` upstream-error row; `:804-811` charge skipped for BYOK.
- `app/routers/v1.py:147-151` `_Upstream` wrapper signature; `:296-300` tool settings read per request; `:315` no BYOK on `/v1`; `:362-365` `owned_by`; `:389-421` model routes.
- `app/services/v1_translate.py:155`, `:516` tool-model rule; `:617-628` usage `0/0/total`.
- `app/services/usage_limits.py:191-212` `charge()` → `unsplit_tokens` without a split; `app/db/models.py:61-136` added columns; `:224-230` `usage_daily`; `app/db/database.py:730` migration; `:1330-1381` summary `json_object`.
- `app/services/pii_policy.py:108-148` `chat`/`code` policies; `app/services/action_config.py:324-335` built-in secret env globs.
- `chat_ui/chat_ui/config.py:1-8` hard-coded allowlist and `DEFAULT_MODEL`; `chat_ui/chat_ui/components/shell.py:98-106` selector.
- `scripts/stub_openrouter.py:63-64` never streams; `:399` per-server handler binding.
- `app/models/schemas.py:18-19` `model: str = "gpt-4"`, `openrouter_api_key`.

### Not verified in code (external facts this PRD relies on)

- Ollama, vLLM, LM Studio, llama.cpp server and LocalAI serve `POST /v1/chat/completions`. Which of them return `usage` on non-streamed responses, and the exact shape of their `tool_calls` (string `arguments`, present `id`), is to be recorded by the E2E and the docs.
- Ollama's default context window may truncate long prompts silently. T10 and D9 assume that, but this PRD does not depend on it.
- httpx's default of not following redirects. D5 sets it explicitly regardless.

### Related documents

- PRD-005 (RBAC: model allowlist, BYOK), PRD-010 (pipeline, `GenerationParams`), PRD-012 (PII for code), PRD-013 (audit columns, usage charge), PRD-015 (`/v1`, `OPENROUTER_BASE_URL` T10, stub), PRD-017 (tool calling, `V1_TOOL_MODELS`, D13)
- PRD-021 (streaming) and PRD-022 (native adapters, fallback, circuit breaker) build on this.

### Dependencies

- Depends on: PRD-015, PRD-017 (done)
- Blocks: PRD-021, PRD-022

**Skills referenced:** frontend-design (`.agents/skills/`). It applies only to the chat UI selector and the Register's `provider` field. No rule from it applies to Sections 6, 8 or 9.
