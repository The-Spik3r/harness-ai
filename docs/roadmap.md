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
- [x] [Audit fields and usage limits](features.md#usage-limits) — per-user token budget and rate limit, shared across instances; ingress, token split and conversation key on every audit row; `ADMIN_TOKEN` scoped by ingress

### Next up — resilience

This is the first work beyond the Turso migration, called out as such in [The database is a hard dependency of every request](deployment.md#the-database-is-a-hard-dependency-of-every-request). The migration unblocked running several instances against one database, but it also made every request depend on a network round trip, and the harness fronts a single upstream provider with no fallback. A transient database or OpenRouter outage therefore fails requests rather than degrading them. The resilience work closes that gap:

- [ ] **Retry and circuit breaker** on the database path, so a brief blip is ridden out instead of surfaced as a `500`. The two fail-closed checks (duplicate and usage gate) keep their security contract — a breaker that opens still refuses rather than waving requests through.
- [ ] **Offline buffering of audit writes**, so an audit row is never lost to a storage blip even when the write cannot land immediately. Audit is append-only and already tolerates a late write; the gate checks are not buffered, by design.
- [ ] **A second provider as fallback to OpenRouter.** The project's own thesis is a control plane in front of LLM traffic, and a control plane tied to one upstream is a single point of failure. The pipeline is already provider-agnostic at the call boundary; what is missing is a configured fallback and the policy for when to use it.
- [ ] **Websocket session affinity**, so the chat UI can run behind a load balancer. The chat holds a websocket per session, so a round-robin balancer without sticky sessions is not supported today — see [Multiple instances](deployment.md#multiple-instances).

### Planned

- [ ] Semantic (not just exact-match) duplicate detection
- [ ] [OpenAI-compatible endpoint](#openai-compatible-endpoint) — drop-in use from OpenCode and other coding agents
- [ ] [MCP servers and agent skills](#mcp-servers-and-agent-skills) — code-writing tools behind the same pipeline
- [ ] [Action policy rules](#action-policy-rules) — deny destructive SQL, shell, and filesystem operations

Everything below this line is **intended direction, not current behavior**. The only ingress that exists today is `POST /query`.

### OpenAI-compatible endpoint

`POST /query` is a shape specific to this project: every client has to be written against it, which is why the chat UI is the only thing that speaks it. The plan is to add `POST /v1/chat/completions` following the OpenAI Chat Completions standard, so tools that already speak it — [OpenCode](https://github.com/sst/opencode), Cline, Continue, Aider, the official OpenAI SDKs — can be pointed at the harness by changing one base URL:

```bash
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_API_KEY=<harness token — never the OpenRouter key>
```

This would be a translation layer, not a second pipeline: it maps the `messages` array onto the existing duplicate → pattern → PII → OpenRouter → audit flow, and maps a block back onto the standard's error shape, so the calling tool surfaces an ordinary API error instead of a malformed completion. The harness becomes the only component holding the real OpenRouter key. Half of that is now built: the pipeline already takes a `messages` list, redacts every turn and keys the duplicate check over the conversation — see [Multi-turn context](features.md#multi-turn-context) — and the `code` PII policy that ingress will run, which leaves fenced code and the response unmasked, is built and measured (see [PII redaction](features.md#pii-redaction)). What does not exist is the HTTP ingress, and the trust model for `system` and `assistant` turns a caller supplies, which is what this section is still about.

Open design questions:

- How `user_id` and device are carried — a custom header, or the standard's optional `user` field.
- ~~What gets hashed for duplicate detection in a multi-turn conversation.~~ **Answered:** the last user turn plus a hash of the preceding turns, per user — the key `POST /query` already uses, with a non-empty prefix. An agent that resends an unchanged history and repeats its last turn is a duplicate; one whose history has moved on is not. See [Multi-turn context](features.md#multi-turn-context).
- Whether `stream: true` can be supported at all, given the harness must inspect a complete response before releasing it. A partial answer is buffering upstream and re-emitting as SSE once the checks pass — streaming-shaped, not streaming-latency.

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

These rules are per-deployment configuration, which made *Configurable, per-deployment pattern lists* a prerequisite for this work rather than an independent nice-to-have. That prerequisite has shipped — see [Pattern policy](features.md#pattern-policy) — and so has the record this work would act on: a tool result carrying a planted instruction is already flagged in the audit, and still reaches the model. These rules are what would stop the model acting on it; they are not built yet. RBAC, already shipped, is the natural pairing: the same `DELETE` can already be denied for one role and allowed for another via the role→permission matrix in `app/services/authz.py` — action policy rules would extend that same deny-by-default model from prompts to tool calls.

---
