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
- [x] [Database resilience](deployment.md#what-a-database-outage-does) — retry and circuit breaker on the database path, an audit journal with a drainer, `503` with `Retry-After` on every ingress, `GET /storage/status` and an admin Storage page

### Next up — resilience

Database resilience has shipped ([PRD-018](../.agents/PRDs/PRD-018-db-resilience/PRD.md)): a retry and circuit breaker on the database path, and a journal for audit writes, described in [What a database outage does](deployment.md#what-a-database-outage-does). What remains is on the provider side, and it is still true there that a transient OpenRouter outage fails requests rather than degrading them. The harness fronts a single upstream provider with no fallback, and the chat UI cannot yet run behind a balancer:

- [x] **Retry and circuit breaker** on the database path, shipped in [PRD-018](../.agents/PRDs/PRD-018-db-resilience/PRD.md): a brief blip is ridden out instead of surfaced as a `500`, and a breaker that opens still refuses rather than waving requests through; the duplicate check and usage gate fail closed. See [What a database outage does](deployment.md#what-a-database-outage-does).
- [x] **Offline buffering of audit writes**, shipped in [PRD-018](../.agents/PRDs/PRD-018-db-resilience/PRD.md): an audit row that cannot land is journaled and drained, so it is not lost to a storage blip. The gate checks are not buffered, by design. Not covered: a resend on another instance before the drain (T4), and a stalled driver call.
- [ ] **A second provider as fallback to OpenRouter.** The project's own thesis is a control plane in front of LLM traffic, and a control plane tied to one upstream is a single point of failure. The pipeline is already provider-agnostic at the call boundary; what is missing is a configured fallback and the policy for when to use it.
- [ ] **Websocket session affinity**, so the chat UI can run behind a load balancer. The chat holds a websocket per session, so a round-robin balancer without sticky sessions is not supported today — see [Multiple instances](deployment.md#multiple-instances).

### Planned

- [ ] Semantic (not just exact-match) duplicate detection
- [ ] [MCP servers and agent skills](#mcp-servers-and-agent-skills) — code-writing tools behind the same pipeline

Everything below this line is **intended direction, not current behavior**, except where a section says it has shipped. Ingresses today: `POST /query`, the chat UI and `POST /v1/chat/completions`.

### OpenAI-compatible endpoint

**Shipped (PRD-015).** Full behaviour and per-client setup are in [Features — OpenAI-compatible endpoint](features.md#openai-compatible-endpoint); request, response and error shapes are in the [API reference](api.md#post-v1chatcompletions--success). `POST /v1/chat/completions` and `GET /v1/models` follow the OpenAI Chat Completions standard, so tools that already speak it, such as [OpenCode](https://github.com/sst/opencode), Cline, Continue, Aider and the official OpenAI SDKs, are pointed at the harness by changing one base URL:

```bash
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_API_KEY=<harness token, never the OpenRouter key>
```

It is a translation layer, not a second pipeline: it maps the `messages` array onto the existing duplicate, pattern, PII, OpenRouter and audit flow, runs the `code` profile, and maps a block back onto the standard's error shape, so the calling tool shows an ordinary API error instead of a malformed completion. The harness is the only component holding the real OpenRouter key. `stream: true` is answered after the whole response has been checked (buffered upstream and re-emitted as SSE), which is streaming-shaped, not streaming-latency. `ADMIN_TOKEN` is never accepted there. Settings: `V1_ENABLED`, `V1_SSE_KEEPALIVE_SECONDS`, `OPENROUTER_BASE_URL`, `V1_TOOLS_ENABLED`, `V1_TOOL_MODELS` (documented in `.env.example`).

**Tool calling (PRD-017).** With `V1_TOOLS_ENABLED=true`, `tools`, `tool_choice`, `parallel_tool_calls`, assistant `tool_calls` and `tool` turns are accepted, which is what Cline and OpenCode need in agent mode, and every call the model returns is decided before it is released. Off, the default, keeps the `tools_not_supported` refusal. See [Tool calling](features.md#tool-calling). **Still not covered:** `functions` / `function_call` (refused either way) and real streaming (the stream is still buffered).

### MCP servers and agent skills

An OpenAI-compatible endpoint invites coding agents, and coding agents do not only produce text — they call tools, and those tools write files, run commands, and query databases. The current text-level checks do not cover that: a prompt can pass the injection filter and still yield a tool call that drops a table.

The plan is to extend interception down to the tool layer:

- **[MCP](https://modelcontextprotocol.io) servers behind the harness** — the harness fronts one or more MCP servers, so tool discovery and every `tools/call` pass through it and land in the audit log next to the prompts that caused them.
- **Skills** — packaged capabilities (write code, open a pull request, run a migration) exposed through that same interception point, so what an agent is allowed to do becomes a deployment decision rather than a client-side one.
- **Tool-call auditing** — one row per call: tool name, arguments, user, allowed or denied. That record now exists for `/v1` tool calls (`action_decisions`, linked to the request's audit row by `audit_id`); MCP `tools/call` would reuse it.

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

**Built (PRD-016), called by `/v1` (PRD-017).** The table above is now the built catalogue: 25 rules, a pure engine that decides a tool call as *allow*, *flag* or *deny*, six `action:*` permissions that no built-in role holds, a policy file (`ACTION_POLICY_FILE`, with [`examples/action_policy.yaml`](../examples/action_policy.yaml)), an `action_decisions` audit table, `GET /audit/actions`, an **Actions** view in the admin console, and corpora of synthetic and evasion calls that no role can get past. What it does and does not cover is in [Features: Action policy rules](features.md#action-policy-rules). The harness never executes a tool; it classifies a call the model proposed.

**What PRD-017 added.** With `V1_TOOLS_ENABLED=true`, `/v1` accepts `tools` and tool turns and evaluates each `tool_call` after the model answered and before the response leaves the harness. A denied call is dropped and replaced by a note in the content, the others are released in order (`finish_reason` is `tool_calls` while one is released, `stop` when none survived), and each decision is linked to its request by `audit_id` (`GET /audit/actions?audit_id=`). If the decisions cannot be recorded, nothing is released and the request fails with a retryable `500`. The Actions view's empty state now says decisions are recorded only while the flag is on. See [Tool calling](features.md#tool-calling).

These rules are per-deployment configuration, which made *Configurable, per-deployment pattern lists* a prerequisite rather than an independent nice-to-have. That prerequisite has shipped, see [Pattern policy](features.md#pattern-policy), and so has the record the rules act on: a tool result carrying a planted instruction is flagged in the audit and still reaches the model, and these rules are what stop the model acting on it. RBAC pairs with them: the same `DELETE` can be denied for one role and allowed for another, through the `action:*` permissions in the role matrix of `app/services/authz.py`, which extends the deny-by-default model from prompts to tool calls.

---
