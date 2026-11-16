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
- [x] [OpenAI-compatible endpoint](#openai-compatible-endpoint) — `POST /v1/chat/completions` and `GET /v1/models` for the OpenAI SDKs, Aider and Continue, through the same pipeline under the `code` profile
- [x] [Audit fields and usage limits](features.md#usage-limits) — per-user token budget and rate limit, shared across instances; ingress, token split and conversation key on every audit row; `ADMIN_TOKEN` scoped by ingress

### Next up — resilience

This is the first work beyond the Turso migration, called out as such in [The database is a hard dependency of every request](deployment.md#the-database-is-a-hard-dependency-of-every-request). The migration unblocked running several instances against one database, but it also made every request depend on a network round trip, and the harness fronts a single upstream provider with no fallback. A transient database or OpenRouter outage therefore fails requests rather than degrading them. The resilience work closes that gap:

- [ ] **Retry and circuit breaker** on the database path, so a brief blip is ridden out instead of surfaced as a `500`. The two fail-closed checks (duplicate and usage gate) keep their security contract — a breaker that opens still refuses rather than waving requests through.
- [ ] **Offline buffering of audit writes**, so an audit row is never lost to a storage blip even when the write cannot land immediately. Audit is append-only and already tolerates a late write; the gate checks are not buffered, by design.
- [ ] **A second provider as fallback to OpenRouter.** The project's own thesis is a control plane in front of LLM traffic, and a control plane tied to one upstream is a single point of failure. The pipeline is already provider-agnostic at the call boundary; what is missing is a configured fallback and the policy for when to use it.
- [ ] **Websocket session affinity**, so the chat UI can run behind a load balancer. The chat holds a websocket per session, so a round-robin balancer without sticky sessions is not supported today — see [Multiple instances](deployment.md#multiple-instances).

### Planned

- [ ] Semantic (not just exact-match) duplicate detection
- [ ] [MCP servers and agent skills](#mcp-servers-and-agent-skills) — code-writing tools behind the same pipeline
- [ ] [Action policy rules](#action-policy-rules) — deny destructive SQL, shell, and filesystem operations. The engine and its audit are built ([PRD-016](features.md#action-policy-rules)); the box stays unticked until tool calling on `/v1` (PRD-017) calls it

Everything below this line is **intended direction, not current behavior**, except where a section says it has shipped. Ingresses today: `POST /query`, the chat UI and `POST /v1/chat/completions`.

### OpenAI-compatible endpoint

**Shipped (PRD-015).** `POST /v1/chat/completions` and `GET /v1/models` follow the OpenAI Chat Completions standard, so tools that already speak it, such as [OpenCode](https://github.com/sst/opencode), Cline, Continue, Aider and the official OpenAI SDKs, are pointed at the harness by changing one base URL:

```bash
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_API_KEY=<harness token, never the OpenRouter key>
```

It is a translation layer, not a second pipeline: it maps the `messages` array onto the existing duplicate, pattern, PII, OpenRouter and audit flow, runs the `code` profile, and maps a block back onto the standard's error shape, so the calling tool shows an ordinary API error instead of a malformed completion. The harness is the only component holding the real OpenRouter key. `stream: true` is answered after the whole response has been checked (buffered upstream and re-emitted as SSE), which is streaming-shaped, not streaming-latency. `ADMIN_TOKEN` is never accepted there. Settings: `V1_ENABLED`, `V1_SSE_KEEPALIVE_SECONDS`, `OPENROUTER_BASE_URL` (documented in `.env.example`).

**Not yet:** a request that carries `tools`, `tool_calls` or a `tool` turn is refused with `tools_not_supported`. That is [PRD-017](../pre-prds/PRE-PRD-016-tool-calling.md), and it is what Cline and OpenCode need in agent mode.

### MCP servers and agent skills

An OpenAI-compatible endpoint invites coding agents, and coding agents do not only produce text — they call tools, and those tools write files, run commands, and query databases. The current text-level checks do not cover that: a prompt can pass the injection filter and still yield a tool call that drops a table.

The plan is to extend interception down to the tool layer:

- **[MCP](https://modelcontextprotocol.io) servers behind the harness** — the harness fronts one or more MCP servers, so tool discovery and every `tools/call` pass through it and land in the audit log next to the prompts that caused them.
- **Skills** — packaged capabilities (write code, open a pull request, run a migration) exposed through that same interception point, so what an agent is allowed to do becomes a deployment decision rather than a client-side one.
- **Tool-call auditing** — one row per call: tool name, arguments, user, allowed or denied. The current `audit_logs` schema records prompts and responses only, so this needs a schema addition.

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

**Built (PRD-016), not yet called.** The table above is now the built catalogue: 25 rules, a pure engine that decides a tool call as *allow*, *flag* or *deny*, six `action:*` permissions that no built-in role holds, a policy file (`ACTION_POLICY_FILE`, with [`examples/action_policy.yaml`](../examples/action_policy.yaml)), an `action_decisions` audit table, `GET /audit/actions`, an **Actions** view in the admin console, and corpora of synthetic and evasion calls that no role can get past. What it does and does not cover is in [Features: Action policy rules](features.md#action-policy-rules). The harness never executes a tool; it classifies a call the model proposed.

**What PRD-017 adds.** Nothing in the request path calls the engine yet: `/v1` still refuses `tools`. PRD-017 accepts them, evaluates each `tool_call` before the response leaves the harness, decides what a denial looks like on the wire and what happens to a response that mixes allowed and denied calls, links each decision to its `audit_id`, and rewords the Actions view's empty state. Until then the checkbox above stays unticked.

These rules are per-deployment configuration, which made *Configurable, per-deployment pattern lists* a prerequisite rather than an independent nice-to-have. That prerequisite has shipped, see [Pattern policy](features.md#pattern-policy), and so has the record the rules act on: a tool result carrying a planted instruction is flagged in the audit and still reaches the model, and these rules are what will stop the model acting on it. RBAC pairs with them: the same `DELETE` can be denied for one role and allowed for another, through the `action:*` permissions in the role matrix of `app/services/authz.py`, which extends the deny-by-default model from prompts to tool calls.

---
