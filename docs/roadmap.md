# Roadmap

What has shipped, what is next, and design notes for the planned work. The README carries a [short version](../README.md#roadmap).

← Back to the [README](../README.md).

---

### Shipped

- [x] Duplicate detection (24h, exact match)
- [x] Prompt-injection blocking (pattern list)
- [x] Full audit logging (Turso / libSQL)
- [x] Chat UI
- [x] PII redaction on input/output
- [x] Role-based access control (RBAC)
- [x] Chat sessions — persisted, per-conversation transcripts
- [x] [Multi-turn context](features.md#multi-turn-context) — the chat sends its history, so a session is a conversation
- [x] [Configurable, per-deployment pattern lists](features.md#pattern-policy) — per-role scope, word matching, indirect injection flagged
- [x] [PII redaction for code](features.md#pii-redaction) — policy per profile, role and direction; fenced blocks skipped; within a measured latency budget
- [x] [OpenAI-compatible endpoint](#openai-compatible-endpoint) — `POST /v1/chat/completions` and `GET /v1/models` for the OpenAI SDKs, Aider and Continue, and for OpenCode and Cline with tool calling turned on, through the same pipeline under the `code` profile
- [x] [Tool calling on /v1](features.md#tool-calling) — OpenCode and Cline in agent mode; every tool call decided by the action policy before the client sees it; off by default (`V1_TOOLS_ENABLED`)
- [x] [Action policy rules](#action-policy-rules) — deny destructive SQL, shell, and filesystem operations. Built in [PRD-016](features.md#action-policy-rules) and decided on every `/v1` tool call since PRD-017
- [x] [Audit fields and usage limits](features.md#usage-limits) — per-user token budget and rate limit, shared across instances; ingress, token split and conversation key on every audit row; `ADMIN_TOKEN` scoped by ingress
- [x] [Real-time streaming](features.md#real-time-delivery) — PRD-021: opt-in per role (`stream:realtime`, `reasoning:view`) and off by default (`STREAMING_ENABLED`); text released while the model writes it, each segment redacted first, tool calls held until the action policy has decided them; the chat UI shows a progress line, a live answer and a reasoning block. Verified end to end with OpenCode 2.3.2 and Cline 3.0.74, both against the stub upstream, not a live model
- [x] [Database resilience](deployment.md#what-a-database-outage-does) — retry and circuit breaker on the database path, an audit journal with a drainer, `503` with `Retry-After` on every ingress, `GET /storage/status` and an admin Storage page
- [x] [Provider fallback and a native Anthropic adapter](features.md#provider-fallback-and-anthropic) — PRD-022: ordered fallback chains per model, a per-provider circuit breaker, `type: anthropic` providers, one audit row per attempt and `GET /providers/status`; off unless `PROVIDER_CHAINS_FILE` is set
- [x] [MCP gateway and skills](features.md#mcp-gateway-and-skills) — PRD-023: one `POST /mcp` endpoint in front of the MCP servers you configure, with skills a role holds (`skill:<id>`); every `tools/call` decided by the same action policy and recorded before it is forwarded, linked to the `/v1` proposal by correlation (not proof); off by default (`MCP_ENABLED`). Verified with OpenCode 2.3.2 and Cline CLI 3.0.74 against a stub server, not a live model

### Next up — resilience

Database resilience has shipped ([PRD-018](../.agents/PRDs/PRD-018-db-resilience/PRD.md)): a retry and circuit breaker on the database path, and a journal for audit writes, described in [What a database outage does](deployment.md#what-a-database-outage-does). Provider resilience has shipped too ([PRD-022](../.agents/PRDs/PRD-022-provider-fallback-and-native-adapters/PRD.md)): with a chains file, a transient provider outage degrades a request to the next candidate instead of failing it. The chat UI runs behind a balancer (see [Multiple instances](deployment.md#multiple-instances)):

- [x] **Retry and circuit breaker** on the database path, shipped in [PRD-018](../.agents/PRDs/PRD-018-db-resilience/PRD.md): a brief blip is ridden out instead of surfaced as a `500`, and a breaker that opens still refuses rather than waving requests through; the duplicate check and usage gate fail closed. See [What a database outage does](deployment.md#what-a-database-outage-does).
- [x] **Offline buffering of audit writes**, shipped in [PRD-018](../.agents/PRDs/PRD-018-db-resilience/PRD.md): an audit row that cannot land is journaled and drained, so it is not lost to a storage blip. The gate checks are not buffered, by design. Not covered: a resend on another instance before the drain (T4), and a stalled driver call.
- [x] **A second provider as fallback to OpenRouter**, shipped in [PRD-022](../.agents/PRDs/PRD-022-provider-fallback-and-native-adapters/PRD.md): ordered fallback chains per model with a per-provider circuit breaker, a native Anthropic adapter, one audit row per attempt and `GET /providers/status`. Trust, role, capability, bring-your-own-key and redaction are checked for every candidate, and nothing is retried after a stream has started. See [Provider fallback and Anthropic](features.md#provider-fallback-and-anthropic) and [Provider outages](deployment.md#provider-outages).
- [x] **Websocket session affinity**, so the chat UI can run behind a load balancer. Shipped (PRD-019): a sticky, health-checked Caddy balancer in `docker-compose.lb.yml`, a `/ready` probe and a rolling restart script — see [Multiple instances](deployment.md#multiple-instances).

### Planned

- [ ] Semantic (not just exact-match) duplicate detection

Everything below this line is **intended direction, not current behavior**, except where a section says it has shipped. Ingresses today: `POST /query`, the chat UI and `POST /v1/chat/completions`.

### OpenAI-compatible endpoint

**Shipped (PRD-015).** Full behaviour and per-client setup are in [Features — OpenAI-compatible endpoint](features.md#openai-compatible-endpoint); request, response and error shapes are in the [API reference](api.md#post-v1chatcompletions--success). `POST /v1/chat/completions` and `GET /v1/models` follow the OpenAI Chat Completions standard, so tools that already speak it, such as [OpenCode](https://github.com/sst/opencode), Cline, Continue, Aider and the official OpenAI SDKs, are pointed at the harness by changing one base URL:

```bash
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_API_KEY=<harness token, never the OpenRouter key>
```

It is a translation layer, not a second pipeline: it maps the `messages` array onto the existing duplicate, pattern, PII, OpenRouter and audit flow, runs the `code` profile, and maps a block back onto the standard's error shape, so the calling tool shows an ordinary API error instead of a malformed completion. The harness is the only component holding the real OpenRouter key. `stream: true` is answered after the whole response has been checked (buffered upstream and re-emitted as SSE), which is streaming-shaped, not streaming-latency, unless a role is granted real time (PRD-021, below). `ADMIN_TOKEN` is never accepted there. Settings: `V1_ENABLED`, `V1_SSE_KEEPALIVE_SECONDS`, `OPENROUTER_BASE_URL`, `V1_TOOLS_ENABLED`, `V1_TOOL_MODELS` (documented in `.env.example`).

**Tool calling (PRD-017).** With `V1_TOOLS_ENABLED=true`, `tools`, `tool_choice`, `parallel_tool_calls`, assistant `tool_calls` and `tool` turns are accepted, which is what Cline and OpenCode need in agent mode, and every call the model returns is decided before it is released. Off, the default, keeps the `tools_not_supported` refusal. See [Tool calling](features.md#tool-calling). **Still not covered:** `functions` / `function_call` (refused either way) and real streaming, which has since shipped behind a grant (see [Real-time delivery](features.md#real-time-delivery)).

**Real-time streaming (PRD-021).** Delivered, off by default: `STREAMING_ENABLED`, plus a role granted `stream:realtime` (and `reasoning:view` for the model's reasoning) and a providers-file model with `capabilities.streaming: true`; legacy mode never streams. The text is released while the model writes it, each segment redacted first, and tool calls are never sent in pieces. Verified clients: OpenCode 2.3.2 and Cline 3.0.74, both end to end against the stub upstream, not a live model. Full behaviour, costs and residual risks: [Real-time delivery](features.md#real-time-delivery). **Still not covered**, each an open item:

- [ ] **Per-call early release**: release a tool call as soon as the next call's first fragment (or the finish) proves its arguments complete, deciding each on its own, instead of after the stream ends.
- [ ] **Write-ahead audit row** at commit, updated at the end, so a crash mid-stream no longer leaves released text unrecorded.
- [ ] **Reasoning audit store** with its own retention and read permission; reasoning is not stored today.
- [ ] **Progress words for `/v1`** through a side channel a client opts into, only once a client is shown to ignore unknown event types safely.
- [ ] **Streaming on `POST /query`**, as an opt-in SSE variant, if a non-chat client appears.
- [ ] **Admin-console grant editor** for the permission matrix, covering action and stream permissions together.
- [x] **Anthropic thinking blocks in the reasoning stream** (PRD-022): the native adapter maps them to `ReasoningDelta`s, shown under PRD-021's `reasoning:view`.
- [ ] **Gemini thoughts in the reasoning stream**, together with a native Gemini adapter (deferred by PRD-022 D3).

### MCP servers and agent skills

**Shipped (PRD-023), off by default (`MCP_ENABLED`).** Full behaviour, per-client setup and limits are in [Features: MCP gateway and skills](features.md#mcp-gateway-and-skills). An OpenAI-compatible endpoint invites coding agents, and coding agents call tools that write files, run commands and query databases. The text-level checks do not cover that, so interception now reaches the tool layer:

- **MCP servers behind the harness**: `POST /mcp` aggregates the servers in `MCP_CONFIG_FILE` as `<server>__<tool>`; every `tools/call` is decided by the action policy, recorded before it is forwarded, and its result inspected (hash, size and flags are kept, never the result).
- **Skills**: named bundles of tools and instructions that a role holds as `skill:<id>`; what a caller sees in `tools/list` and `prompts/list` is what its skills list, and a call outside them is `tool.not_in_skill`.
- **Tool-call auditing**: one `action_decisions` row per call with its server, outcome and, by correlation, the `/v1` decision that proposed it. `GET /audit/actions` filters on `surface`, `server`, `outcome` and `linked`; `GET /skills` lists the skills; the admin console shows both.

The harness runs no tool code, but it does cause execution: an allowed call is forwarded to the configured server. Verified with OpenCode 2.3.2 and Cline CLI 3.0.74 against a stub server, not a live model. **Still not covered**, each an open item:

- [ ] **OAuth 2.1 on `/mcp`**, in place of the harness bearer token.
- [ ] **Per-user upstream credentials**; today every user shares a server's one credential.
- [ ] **OAuth client credentials southbound**, instead of a static header from an environment variable.
- [ ] **Skill-scoped constraints and pinned tool-description hashes**, so a changed description is held, not only re-inspected.
- [ ] **`MCP_REQUIRE_PROPOSAL`**: refuse a gateway call that no `/v1` proposal matches, once linking is shown reliable enough to block on (it is correlation today).
- [ ] **Upstream `resources` and prompts**, and **sampling** through the pipeline.
- [ ] **Operator-sandboxed `stdio` servers**.
- [ ] **The `2026-07-28` northbound handshake**.
- [ ] **Streaming and progress** for long tool calls.
- [ ] **Per-server workspace roots** for path checks.
- [ ] **A shared upstream registry** across instances, so one user keeps one upstream session.
- [ ] **`tools/list` discovery rows** in the audit.

### Action policy rules

The piece that makes the above safe to enable: a deny-by-default rule set evaluated **before** a tool call executes, occupying the same position for actions that the pattern check occupies for prompts.

| Rule class | Example of what it denies |
|---|---|
| **Destructive SQL** | `DROP`, `TRUNCATE`, `ALTER`, `GRANT`, and `DELETE`/`UPDATE` without a `WHERE` clause — read-only `SELECT` stays allowed |
| **Shell execution** | Arbitrary command execution: `rm -rf`, `curl ... \| sh`, package installs, service restarts |
| **Filesystem writes** | Writes outside an allowlisted workspace path; any edit to `.env`, credential files, or CI configuration |
| **Network egress** | Calls to hosts outside an allowlist — the same exfiltration concern the harness already answers for prompts |
| **Secret access** | Reads of environment variables or files matching secret patterns |

The design intent carries over from the existing checks: a denial short-circuits **before** the action happens, returns a `reason` string the calling agent can display, and is logged with the same rigor as an allowed call — the audit trail has to show what was attempted, not only what succeeded.

**Built (PRD-016), called by `/v1` (PRD-017).** The table above is now the built catalogue: 26 rules, a pure engine that decides a tool call as *allow*, *flag* or *deny*, six `action:*` permissions that no built-in role holds, a policy file (`ACTION_POLICY_FILE`, with [`examples/action_policy.yaml`](../examples/action_policy.yaml)), an `action_decisions` audit table, `GET /audit/actions`, an **Actions** view in the admin console, and corpora of synthetic and evasion calls that no role can get past. What it does and does not cover is in [Features: Action policy rules](features.md#action-policy-rules). The harness runs no tool code; it classifies a call the model proposed.

**What PRD-017 added.** With `V1_TOOLS_ENABLED=true`, `/v1` accepts `tools` and tool turns and evaluates each `tool_call` after the model answered and before the response leaves the harness. A denied call is dropped and replaced by a note in the content, the others are released in order (`finish_reason` is `tool_calls` while one is released, `stop` when none survived), and each decision is linked to its request by `audit_id` (`GET /audit/actions?audit_id=`). If the decisions cannot be recorded, nothing is released and the request fails with a retryable `500`. The Actions view's empty state now says decisions are recorded only while the flag is on. See [Tool calling](features.md#tool-calling).

These rules are per-deployment configuration, which made *Configurable, per-deployment pattern lists* a prerequisite rather than an independent nice-to-have. That prerequisite has shipped, see [Pattern policy](features.md#pattern-policy), and so has the record the rules act on: a tool result carrying a planted instruction is flagged in the audit and still reaches the model, and these rules are what stop the model acting on it. RBAC pairs with them: the same `DELETE` can be denied for one role and allowed for another, through the `action:*` permissions in the role matrix of `app/services/authz.py`, which extends the deny-by-default model from prompts to tool calls.

---
