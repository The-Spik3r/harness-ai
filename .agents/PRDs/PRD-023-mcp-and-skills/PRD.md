---
id: PRD-023
slug: mcp-and-skills
title: MCP Servers and Agent Skills Behind the Harness — Every tools/call Decided and Audited
status: draft
base_branch: main
epic_branch: epic/PRD-023-mcp-and-skills
created: 2026-11-16
updated: 2026-11-16
---

> **Scope note.** This is the roadmap's *MCP servers and agent skills* item ([docs/roadmap.md:55-63](../../../docs/roadmap.md)). It changes one principle that PRD-016 and PRD-017 state on every page: "the harness never executes a tool" ([docs/roadmap.md:79](../../../docs/roadmap.md), [docs/features.md:483](../../../docs/features.md)). After this PRD the harness still **runs no tool code**, but for MCP tools it **causes execution**: it forwards an allowed `tools/call` to an MCP server it is configured to front. D2 and Section 9.2 give the reasoning. Everything about `/v1` that PRD-017 shipped stays as it is unless Section 6.8 says otherwise.

## 1. Executive Summary

PRD-016 built a decision engine for tool calls and PRD-017 put it on `/v1`: every `tool_call` the model returns is classified and decided (`allow`, `flag`, `deny`) before the client sees it, and each decision is written to `action_decisions` ([app/services/query_pipeline.py:813](../../../app/services/query_pipeline.py)). That control has two gaps that show up as soon as agents use MCP. First, **the decision is advisory**. The harness decides what the model may *propose*, and the client executes. A client that ignores the decision, or calls a tool on its own, is not stopped ([docs/features.md:483](../../../docs/features.md)). Second, **MCP tools are not classified at all**. They reach `/v1` under client-specific prefixed names (`postgres_query`, `supabase__execute_sql`, `<uid>0mcp0<tool>`; [tests/corpora/actions/SOURCES.md:80,160,222](../../../tests/corpora/actions/SOURCES.md)) that match no built-in mapping ([app/services/action_adapters.py:449](../../../app/services/action_adapters.py)). Or, in OpenCode 2.x, they are called from inside the CodeMode `execute` tool, which is always denied as `tool.unknown` ([docs/features.md:488,536](../../../docs/features.md); [SOURCES.md:112-113](../../../tests/corpora/actions/SOURCES.md)). Today the honest summary is: an agent using MCP through the harness either has its MCP calls denied or calls its MCP servers directly, outside the harness.

This PRD makes the harness an **MCP gateway**. Northbound, it is an MCP server at `POST /mcp` that the agent connects to with its ordinary harness bearer token. Southbound, it is an MCP client to one or more MCP servers that the deployment configures. The harness holds the credentials for those servers and the agent never sees them. Every `tools/list` is filtered to what the caller's role may see. Every `tools/call` is decided by **the PRD-016 engine, unchanged in its rules, grants and fail-closed boundary**, using a per-server extension of its `tools:` mapping. The decision is recorded in `action_decisions` before anything is forwarded, and is then forwarded or refused. The harness does not need the client's cooperation for any of this. For an MCP tool behind the gateway the decision is the enforcement, because the gateway is the only path to the server and its credential.

**Skills** are how a deployment says what an agent may do. A skill is a named, versioned bundle in the deployment's MCP config: a list of gateway tools, instructions for the model, and the action permissions it needs. A role is given a skill through a `skill:<id>` permission in `RBAC_ROLES_FILE`. A tool is visible to a caller only when it belongs to a skill the caller's role holds. *Write code*, *open a pull request* and *run a migration* stop being things a client happens to have configured. They become entries an admin enables per role, reviewable in two files and auditable per call.

**MVP goal:** with `MCP_ENABLED=true`, a role holding `skill:open-pull-request` sees exactly that skill's three GitHub tools in `tools/list`, and a plain `user` sees none. A `postgres-staging__query` call with `DROP TABLE users` is denied under `sql.ddl`, recorded, and **never reaches the server** (the stub server counts zero calls). A `push_files` touching `.github/workflows/ci.yml` is denied under `fs.write_protected`. An allowed call is forwarded with the harness-held credential and its result returns unmodified. A call the model proposed through `/v1` is linked to that request's `audit_id`. A broken MCP config stops startup with a message that names the file and the node.

## 2. Mission

Make the harness the only path between an agent and the tools it is allowed to use, so that what an agent can do is decided by the deployment, enforced at execution and recorded before it happens.

Core principles:

- **One engine, one vocabulary.** A gateway `tools/call` is a `ToolCall` and goes through `action_policy.evaluate()` like a `/v1` call. The 25 rules, the six `action:*` grants, `holds()` without the `RBAC_ENABLED` bypass, most-severe-wins and the fail-closed boundary all carry over ([app/services/action_policy.py:262-345](../../../app/services/action_policy.py)). What is new is *which mapping table* the engine reads (D4), not how it decides.
- **Evidence before effect.** No call is forwarded until its decision row is written. A call whose decision cannot be recorded is not executed (D9). This is PRD-017 D8 moved one step earlier, because here the effect is real.
- **The harness runs no tool code.** It forwards a JSON-RPC request to a server the operator configured. It spawns no process, loads no plugin, evaluates no script and opens no URL the client named (D2, D3).
- **Deny by default, at three levels.** A server is reachable only when it is configured. A tool is visible only when a skill the caller's role holds contains it (D7). A visible tool is executed only when the action policy allows it. Each level is a line that someone wrote.
- **Credentials stay in the harness.** Upstream MCP credentials are read from the environment at startup and attached southbound only. The caller's harness token is never forwarded (D10). The agent cannot leak a credential it never holds.
- **Results are data, not instructions.** A tool result goes back to the agent unmodified, is inspected as untrusted `tool` content, and is never acted on by the harness (D11).
- **Off means PRD-017.** Behind `MCP_ENABLED` (default off) nothing is mounted and nothing is loaded. With it on, `/v1` behaves as before for every tool name that is not a gateway alias (Section 6.8).

## 3. Target Users

**Security/Compliance Admin.** Owns which agent capabilities exist and who has them. Needs a skill to be a reviewable artefact (tools, instructions, required grants). Needs the decision to be enforced at execution, not left to the client's goodwill. Needs every `tools/call` in the audit beside the prompt that caused it, including calls that no prompt through the harness proposed.

**Platform Operator.** Owns `.env`, `ACTION_POLICY_FILE`, `RBAC_ROLES_FILE` and now `MCP_CONFIG_FILE`. Runs the MCP servers as separate services (containers, internal hosts). Needs to add a server by URL and credential name, hand roles skills, and have a typo stop the boot. Needs to rotate a GitHub token in one place instead of on every developer laptop.

**Integrating Developer (coding agent user).** Points OpenCode or Cline at `<harness>/mcp` with the same token they use for `/v1`. Needs the tools of their skills to appear, ordinary calls to work, and a denial to come back as text the agent can read and act on (not a transport error or a retry storm).

**Data/DBA role holder.** Holds `skill:run-migration` and `action:sql:ddl`. Needs `ALTER TABLE` on staging to go through the gateway for them and still be denied for every other role that can see `postgres-staging__query`.

**PRD-016/017 code** (internal). `evaluate`, `record`, the `tools:` mapping grammar, `DENIAL_NOTE_TEMPLATE` ([app/services/tool_release.py:41](../../../app/services/tool_release.py)) and the pattern profile's `tool` cell ([app/services/pattern_config.py:246-250](../../../app/services/pattern_config.py)) are reused. Their contracts must hold: `evaluate` never raises for model input, `reason` is safe to show the agent (PRD-016 T11), and a `tool` result flags without blocking (PRD-011 D4).

## 4. MVP Scope

### In Scope

**Gateway, northbound (`app/routers/mcp.py`, new; `app/services/mcp_gateway.py`, new)**
- [ ] `POST /mcp`: the MCP Streamable HTTP transport, **stateless** with JSON responses only. No `Mcp-Session-Id` is issued, no SSE stream is opened, and `GET` and `DELETE` return `405` (D3)
- [ ] Auth: `require_identity` ([app/middleware/auth.py:14](../../../app/middleware/auth.py)), then `authorize(identity, "mcp:connect")`. The break-glass `ADMIN_TOKEN` is refused as on `/v1` ([app/routers/v1.py:368](../../../app/routers/v1.py)). An `Origin` header that is present must be on `MCP_ALLOWED_ORIGINS` (T11)
- [ ] JSON-RPC 2.0 parsing: one message per POST, batches refused, duplicate object keys refused via `strict_yaml`'s JSON sibling (T7), body capped at `MCP_MAX_REQUEST_BYTES`
- [ ] Methods: `initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`, `prompts/list`, `prompts/get`. Anything else is `-32601 Method not found` (D19)
- [ ] Declared server capabilities: `tools` and `prompts`, both `listChanged: false`. No `resources`, `logging` or `completions`

**Gateway, southbound (`app/services/mcp_upstream.py`, new)**
- [ ] One MCP client per configured server over Streamable HTTP, using the pinned `mcp` SDK's client (D18). No stdio and no legacy HTTP+SSE (D3)
- [ ] Sessions keyed by `(server, user_id)` per instance and expired after `MCP_UPSTREAM_SESSION_IDLE_SECONDS`. The harness re-initializes on session expiry and never retries a call otherwise (D14, D16)
- [ ] Declared client capabilities: none. Server-to-client `sampling/createMessage`, `roots/list` and `elicitation/create` requests are refused (T12)
- [ ] Credentials attached from configuration: `bearer` (`Authorization: Bearer <env value>`) or `header` (`<name>: <env value>`). The caller's `Authorization` is never forwarded (D10)
- [ ] Per-server timeout (default `MCP_CALL_TIMEOUT_SECONDS`). On expiry the harness sends a best-effort `notifications/cancelled` and returns a result saying the call *may have run* (D14)
- [ ] `tools/list` from each server, paginated through `nextCursor`, cached per server for `MCP_TOOLS_CACHE_SECONDS`

**Skills and configuration (`app/services/mcp_config.py`, new)**
- [ ] `MCP_CONFIG_FILE`: YAML through `strict_yaml.safe_load`, with sections `servers:`, `skills:` and `v1_aliases:`. It is loaded once at startup in **both** lifespans and raises `MCPConfigError` on any violation (Section 9.3)
- [ ] A skill is `{version, description, instructions, tools[], requires[]}` (D5). Every `tools[]` entry names a configured server's tool as `<server>__<tool>`
- [ ] Cross-file validation after `authz.load()` and `action_config.load()`. Every skill tool has an `mcp_tools` mapping or an `mcp_opaque_tools` entry. Every `skill:<id>` granted in the role matrix names a defined skill. Every `requires[]` entry is an action permission. Every role holding a skill also holds the skill's `requires[]` (Open decision O2)
- [ ] `mcp_config_digest()`: SHA-256 of the canonical loaded config, credential **names** included and credential **values** excluded

**Action policy (`app/services/action_config.py`, `app/services/action_policy.py`, `app/services/action_classifiers/__init__.py`)**
- [ ] Two new optional sections in `ACTION_POLICY_FILE`: `mcp_tools: {<server>: {<tool>: <ToolMapping>}}` and `mcp_opaque_tools: {<server>: {<tool>: <decision>}}`. They are validated by the existing `_validate_tools` / `_validate_opaque_tools` for each server ([app/services/action_config.py:457,482](../../../app/services/action_config.py)) and are part of `policy_digest()` (D4)
- [ ] `evaluate(call, identity, policy=None, *, surface=V1)`. `surface=McpSurface(server, visible)` selects the server's mapping tables and checks visibility first. The digest is always that of the whole policy (D4)
- [ ] One new rule, `tool.not_in_skill`: deny, no grant, added to `NON_GRANTABLE_RULES` ([app/services/action_classifiers/__init__.py:91](../../../app/services/action_classifiers/__init__.py)). That makes 26 rules and 11 non-grantable (D7)

**RBAC (`app/services/authz.py`)**
- [ ] `mcp:connect` added to `_KNOWN_PERMISSIONS` ([app/services/authz.py:40](../../../app/services/authz.py))
- [ ] `skill:<id>` accepted by `authz.load()` when it matches `skill:[a-z0-9][a-z0-9-]{0,47}`. Whether the skill exists is checked by `mcp_config.load()` (D6)
- [ ] Built-in roles: `admin` and `user` hold `mcp:connect` (O1). **No built-in role holds any `skill:*`** (D6)

**tools/call path (`app/services/mcp_gateway.py`)**
- [ ] Steps M0–M9 (Section 6.3): usage admission, visibility, evaluation, correlation, **record before forward**, forwarding, result inspection, outcome update
- [ ] Denial wire shape: a `CallToolResult` with `isError: true` and one text block in PRD-017's note format (D8). A tool outside the caller's skills gets `-32602` and is still recorded (D7)
- [ ] Results: returned unmodified. Text and embedded-text blocks and `structuredContent` are pattern-inspected under the `code` profile's `tool` cell (flag). A result over `MCP_MAX_RESULT_BYTES` is replaced by an error result (D11)
- [ ] Tool descriptions and input schemas from `tools/list` are inspected with the injection list, and a tool with a hit is withheld (D12, O6)

**`/v1` bridge (`app/services/query_pipeline.py` step 7c, `app/services/action_policy.py`)**
- [ ] `v1_aliases.prefixes` in `MCP_CONFIG_FILE`. A `/v1` `tool_call` whose name is a configured prefix followed by a gateway tool visible to the caller is evaluated under that tool's MCP mapping, so the proposal and the execution are decided alike (D15)
- [ ] Correlation: a gateway call whose `(user_id, server, tool, canonical arguments hash)` matches a `/v1` alias decision released within `MCP_LINK_WINDOW_SECONDS` inherits that row's `audit_id` and stores `linked_decision_id` (D15)

**Audit (`app/db/models.py`, `app/db/database.py`, `app/services/action_audit.py`)**
- [ ] `ACTION_DECISIONS_ADDED_COLUMNS` (it already exists, holding PRD-018's `write_id`; this PRD extends it — orchestrator amendment after STORY-001), through `_add_missing_columns` ([app/db/database.py:796](../../../app/db/database.py)): `surface`, `mcp_server`, `skills`, `arguments_canonical_hash`, `linked_decision_id`, `outcome`, `duration_ms`, `result_bytes`, `result_hash`, `result_flags`, `mcp_config_digest` (D21)
- [ ] `record()` gains keyword-only MCP fields. `record_outcome(decision_row_id, …)` updates one row after forwarding
- [ ] One index for correlation: `(user_id, arguments_canonical_hash)`

**API and admin console**
- [ ] `GET /audit/actions` gains `?surface=v1|mcp`, `?server=` and `?outcome=`, and its entries gain the new fields ([app/routers/admin.py:113](../../../app/routers/admin.py))
- [ ] `GET /skills` (`stats:read`): skills, versions, tools, and the roles that hold each skill. It is read-only and reads no credential
- [ ] The Actions view gains a surface filter and server, skill and outcome columns. A **Skills** panel lists `GET /skills`

**Settings (`app/config.py`)**
- [ ] `MCP_ENABLED`, `MCP_CONFIG_FILE`, `MCP_CALL_TIMEOUT_SECONDS`, `MCP_MAX_REQUEST_BYTES`, `MCP_MAX_RESULT_BYTES`, `MCP_TOOLS_CACHE_SECONDS`, `MCP_UPSTREAM_SESSION_IDLE_SECONDS`, `MCP_LINK_WINDOW_SECONDS`, `MCP_ALLOWED_ORIGINS` (Section 9.3)

**Test infrastructure**
- [ ] `scripts/stub_mcp_server.py`: a scripted Streamable HTTP MCP server, run as a separate process in tests. It exposes `query`, `push_files`, `create_pull_request`, `slow`, `huge`, `inject` (an injection phrase in its result) and `poisoned` (an injection phrase in its description), counts calls per tool, and logs no arguments
- [ ] `tests/corpora/mcp/`: gateway calls with their declared decision per role, in the PRD-016 corpus format plus a `server:` field
- [ ] E2E (opt-in, `--run-e2e`): OpenCode 2.0.10 and the Cline CLI connected to `/mcp` against the stub server

**Documentation**
- [ ] README, `docs/features.md` (an *MCP gateway and skills* section, per-client setup, and a "what it does not cover" list), `docs/roadmap.md` (the item ticked and the "never executes" sentence reworded), `.env.example`, and `examples/mcp.yaml` loaded by a test

### Out of Scope

- [ ] **Executing anything in the harness**: shell, scripts, OpenCode `execute.code`, or WASM. The harness forwards JSON-RPC and nothing else
- [ ] **Hosting MCP servers**: in-process (the SDK's `FastMCP` mounted in the app) or as harness-spawned subprocesses, including **stdio** servers (D3). The operator runs servers as separate services
- [ ] The legacy HTTP+SSE transport (protocol `2024-11-05`), northbound or southbound
- [ ] An OAuth 2.1 authorization server for `/mcp`, and per-user OAuth to upstream servers (Section 13)
- [ ] Proxying upstream `resources/*`, `prompts/*` or `completion/complete` (D19)
- [ ] Relaying `sampling`, `roots` or `elicitation` between server and client (T12)
- [ ] Server-initiated messages, `notifications/progress`, `notifications/tools/list_changed`, and resumable streams
- [ ] Skill-scoped argument constraints (for example "only repository `acme/app`"), skill-scoped grants, and several versions of one skill side by side (Section 13)
- [ ] Validating `arguments` against the upstream `inputSchema`: the mapping reads what it needs and anything else is `tool.malformed`
- [ ] PII redaction of tool results at the gateway (D11, O5)
- [ ] MCP on `POST /query` and in the chat UI
- [ ] Hot reload of `MCP_CONFIG_FILE`, a skill registry or marketplace, and installing skills at runtime
- [ ] Classifying calls an agent makes to MCP servers it reaches directly, outside the harness. Those remain the client's (Section 9.4)

## 5. User Stories

1. **As a security admin, I want to enable the *open a pull request* skill for the `dev` role only, so that which agents can push code is a deployment decision.**
   *Example:* `RBAC_ROLES_FILE` gives `dev` the permissions `mcp:connect` and `skill:open-pull-request`. A `dev` token's `tools/list` returns `github__create_branch`, `github__push_files` and `github__create_pull_request`. A `user` token's returns `[]`. A `user` calling `github__create_pull_request` gets `-32602`, and the call is recorded as `deny`, `tool.not_in_skill`.

2. **As a security admin, I want a destructive SQL call through the gateway stopped before it reaches the database server, so that the decision is enforced rather than advisory.**
   *Example:* a `dev` (who holds `skill:run-migration` but not `action:sql:ddl`) calls `postgres-staging__query` with `{"sql": "DROP TABLE users"}`. The result is `{"isError": true, "content": [{"type": "text", "text": "[harness] tool call postgres-staging__query (7) was denied: destructive SQL is not permitted: DROP"}]}`. The row has `surface='mcp'`, `decision='deny'`, `rule='sql.ddl'` and `outcome=NULL`. The stub server's `query` counter is 0.

3. **As a DBA role holder, I want my role allowed the migration that others are denied, through the same tool, so that one skill serves both.**
   *Example:* `dba` holds `skill:run-migration` and `action:sql:ddl`. `ALTER TABLE t ADD COLUMN c INT` is `allow` with `granted_by='action:sql:ddl'`. It is forwarded and the row has `outcome='ok'`.

4. **As a security admin, I want CI configuration protected from agents even through a remote Git server, so that one protected-path list covers both surfaces.**
   *Example:* `github__push_files` with `files[1].path = ".github/workflows/ci.yml"` → `deny`, `fs.write_protected`. The same push without that file → `allow`, `fs.write_in_workspace`, and it is forwarded.

5. **As a platform operator, I want the GitHub token held by the harness, so that rotating it is one change and no laptop holds it.**
   *Example:* `servers.github.auth: {type: bearer, token_env: MCP_GITHUB_TOKEN}`. The stub server sees `Authorization: Bearer <that value>` and never the caller's harness token. The value appears in no log line, digest, API field or audit row.

6. **As an auditor, I want an MCP call linked to the prompt that proposed it, so that I can read "what was asked", "what the model proposed" and "what ran" together.**
   *Example:* OpenCode sends `/v1` request 412. Its response releases `harness_postgres-staging__query` (alias, `allow`). Eight seconds later the gateway receives the call with the same arguments. `GET /audit/actions?audit_id=412` lists both rows, and the MCP row's `linked_decision_id` is the `/v1` row's id. A call with no matching proposal has `audit_id = NULL`. That is itself visible: the client called a tool that no model response through the harness proposed.

7. **As a security admin, I want a tool whose description tries to instruct the model withheld, so that a poisoned server cannot talk to the model through its catalogue.**
   *Example:* the stub server's `poisoned` tool description contains `ignore previous instructions`. `tools/list` omits it, a `WARNING` names the server, the tool and the matched list (never the text), and calling it gets `-32602`.

8. **As a platform operator, I want a broken MCP config to stop the boot, so that a typo never exposes a tool to the wrong role.**
   *Example:* `skills.open-pull-request.tools: [github__create_pullrequest]` with no such mapping exits with `MCP_CONFIG_FILE '/etc/harness/mcp.yaml': skills.open-pull-request.tools[2]: 'github__create_pullrequest' has no mcp_tools or mcp_opaque_tools entry in ACTION_POLICY_FILE`.

## 6. Core Architecture & Patterns

### 6.1 The protocol, as far as this PRD depends on it

MCP is JSON-RPC 2.0 between a *client* (the agent host) and a *server* (the tool provider). A session starts with an `initialize` request carrying `protocolVersion`, `capabilities` and `clientInfo`. The server answers with its own version, capabilities and `serverInfo` (and, in recent versions, an optional `instructions` string). The client then sends `notifications/initialized`. Servers offer **tools** (`tools/list` with cursor pagination, `tools/call` with `{name, arguments}` → `CallToolResult {content[], isError?, structuredContent?}`), **resources** (`resources/list`, `resources/read`, templates, subscriptions) and **prompts** (`prompts/list`, `prompts/get`). Clients may offer **sampling**, **roots** and **elicitation**, which let a server send requests back to the client. Content blocks include `text`, `image`, `audio`, `resource` (embedded) and, in newer versions, `resource_link`. Tools may carry `annotations` (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`), which the specification describes as hints that are not to be trusted from an untrusted server.

There are two standard transports. **stdio** runs the server as a subprocess of the client. **Streamable HTTP** is a single endpoint taking `POST` (one JSON-RPC message, answered with `application/json` or a `text/event-stream`) and optionally `GET` (a server-to-client SSE stream). With Streamable HTTP the server may assign a session with an `Mcp-Session-Id` response header, and from `2025-06-18` the client sends `MCP-Protocol-Version` on every request. Authorization for HTTP transports is based on **OAuth 2.1**. The MCP server is a resource server that advertises its authorization server through Protected Resource Metadata (RFC 9728) in a `WWW-Authenticate` challenge. Clients use PKCE and resource indicators (RFC 8707), and servers must not accept or pass through tokens that were not issued for them.

**Resolved in STORY-001 (orchestrator amendment, 2026-11-22; sources in `tests/corpora/mcp/SOURCES.md`).** The current MCP revision is `2026-07-28`, which drops the `initialize` handshake, sessions and `ping` and adds the mandatory `server/discover`, the per-request `_meta` version and the `Mcp-Method` / `Mcp-Name` headers. **Decision: the MVP serves the handshake revisions `2025-03-26`, `2025-06-18` and `2025-11-25` only.** Both target clients are built on the TypeScript SDK v1, which tops out at `2025-11-25`. A request in the `2026-07-28` style (a modern `_meta` version and no `initialize`) is refused with a plain HTTP `400` and a `-32600` body, so a dual-era client falls back to `initialize`. Serving `2026-07-28` is a Future Consideration (Section 13). Batching was removed in `2025-06-18`. The session header is spelled `Mcp-Session-Id` (`MCP-Session-Id` in `2025-11-25`; headers are compared case-insensitively). `MCP-Protocol-Version` exists from `2025-06-18`. A stateless server may omit the session (it is a `MAY`). An unknown tool is `-32602`. A present, invalid `Origin` must be refused with `403`. Tool names SHOULD be 1–128 characters from `[A-Za-z0-9_.-]`. The original verify list follows. **Verify against the spec at implementation time (STORY-001):** the current protocol version string and the set the harness negotiates (this PRD assumes `2025-06-18` plus the newest stable revision, `2025-11-25` if that is what it is called, and `2025-03-26` for older clients). Also verify: that JSON-RPC batching was removed in `2025-06-18`; the exact spelling of `Mcp-Session-Id` and `MCP-Protocol-Version`; the `404`-on-expired-session rule; whether a stateless server may omit the session header entirely; the `instructions` field of `InitializeResult`; the tool-name character and length guidance; the `-32602` code for an unknown tool; and the `Origin`-validation requirement for HTTP servers.

### 6.2 Topology (D1, D2, D3)

```
 agent (OpenCode / Cline)                       harness                                   MCP servers (operator-run)
 ───────────────────────                        ───────                                   ──────────────────────────
  LLM calls  ── POST /v1/chat/completions ──▶  pipeline 0..8, step 7c decides proposals
                                               (alias names → MCP mapping, D15)
  tool calls ── POST /mcp  (JSON-RPC) ───────▶  identity → mcp:connect → usage →
               Bearer <harness token>           visibility (skills) → evaluate → RECORD ─▶ POST <server url>
                                                ◀────────── result ◀── inspect ◀── forward  Bearer <harness-held token>
```

- **One aggregated northbound endpoint.** The agent configures one MCP server, `harness`, and gets every tool of every skill it holds, named `<server>__<tool>`. Server ids match `[a-z0-9][a-z0-9-]{0,31}` and never contain `_`, so splitting at the first `__` is unambiguous (O7). One endpoint per upstream server was rejected: it would multiply client configuration, and skills span servers.
- **Who executes (D2).** The upstream MCP server executes. The harness is its client of record, holding the credential. Before this PRD a `deny` was a recommendation that a client could ignore. For a gateway tool the `deny` is final, because the gateway is the only holder of the credential. That is the security gain that pays for the new responsibility (Section 9.2, T1).
- **Stateless northbound (D3).** No northbound session state. Each `POST` carries the bearer token and is decided alone. Multiple harness instances therefore work behind a round-robin balancer, unlike the chat UI's websocket ([docs/roadmap.md:33](../../../docs/roadmap.md)). It also means there is no SSE stream and no server-to-client request northbound, which the MVP needs no more than `/v1` needs real streaming.
- **Southbound Streamable HTTP only (D3).** A stdio server would be a process the harness spawns, which means third-party code on the harness host under its user. That is the hosting this PRD excludes. An operator with a stdio-only server runs it in its own container behind a stdio-to-HTTP bridge and configures the bridge's URL.

### 6.3 The tools/call path

```
M0  HTTP     require_identity; break-glass → 403; authorize(mcp:connect) → 403; Origin check → 403;
             body ≤ MCP_MAX_REQUEST_BYTES → 413; Content-Type application/json → 415
M1  JSON-RPC parse: one object, jsonrpc "2.0", no batch, no duplicate keys → -32700 / -32600
M2  dispatch: initialize | ping | notifications/* handled locally; tools/list (6.5); prompts/* (6.6)
M3  tools/call params: name str; arguments object or absent (→ {}) → else -32602
M4  usage: usage_limits.admit(identity, charges_budget=False) → refused: HTTP 429 + Retry-After (D13)
M5  resolve "<server>__<tool>"; visible = tools of held skills (holds(), D6)
M6  decision = action_policy.evaluate(ToolCall(id, tool, canonical_json(arguments)), identity,
                                      surface=McpSurface(server, visible))           (D4)
M7  link = correlate(user_id, server, tool, sha256(canonical_json))                  (D15)
    row_id = action_audit.record([decision], identity, audit_id=link.audit_id, mcp=…) (D9)
    StorageError → JSON-RPC -32603 "decision could not be recorded"; NOT forwarded
M8  deny  → CallToolResult{isError: true, text: DENIAL_NOTE_TEMPLATE…}               (D8)
    allow / flag → forward with per-server timeout; never retried                    (D14)
M9  inspect result (patterns, tool cell); size cap; record_outcome(row_id, …) best effort; respond
```

Three ordering properties are fixed:

- **Usage before evaluation.** A refused caller costs no engine time and no row. This is PRD-013's "count the attempt" placement ([app/services/usage_limits.py:139](../../../app/services/usage_limits.py)).
- **Record before forward.** M7 completes before M8 starts. The only rows that can be missing an `outcome` are rows whose call was denied, or forwarded with a failed outcome update (logged at `ERROR`). There is never an executed call with no row.
- **Arguments are classified and forwarded as one object.** The body is parsed once, with duplicate keys refused. `canonical_json` is `json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)`. The engine classifies that string, and the SDK sends the *same parsed object*. There is no second parse that could disagree with the first (T7). PRD-017's "never re-serialize" rule protects `/v1` byte identity and does not apply here: an MCP `arguments` value is a JSON object, not a string, so some serialization is unavoidable.

### 6.4 The engine extension (D4, D7)

```python
# app/services/action_policy.py
@dataclass(frozen=True)
class McpSurface:
    server: str                          # a configured server id
    visible: frozenset[str]              # tool names on that server visible to the caller

V1: Final = None

def evaluate(call, identity, policy=None, *, surface: Optional[McpSurface] = V1) -> ActionDecision:
    ...
    tools, opaque = (policy.tools, policy.opaque_tools) if surface is None else (
        policy.mcp_tools.get(surface.server, EMPTY), policy.mcp_opaque_tools.get(surface.server, EMPTY))
    if surface is not None and call.name not in surface.visible:
        classifications = (Classification("tool.not_in_skill", None, call.name[:_NAME_DETAIL_CAP]),)
    else:
        result = action_adapters.map_tool_call(call, tools, opaque, cap)     # unchanged
    ...  # _classify, _decide, _fold, _reason and the fail-closed boundary: unchanged
```

`map_tool_call` already takes the mapping tables as parameters ([app/services/action_adapters.py:440-445](../../../app/services/action_adapters.py)), so the adapter layer changes not at all. The visibility check is inside the `try`, so a bug there also fails closed (PRD-016 T9). `tool.not_in_skill` has subject `"a tool outside the caller's skills"` and is non-grantable. A role cannot be granted past visibility: visibility is granted by `skill:*`, and the decision is the action policy's.

**Why `mcp_tools` is a separate namespace and not more `tools:` keys.** A `/v1` tool name is chosen by the model and prefixed by the client. A gateway server id comes from the endpoint configuration, and the tool name is checked against the caller's visible set. If both lived in one table, a model emitting `github__push_files` on `/v1` would be classified under a mapping written for the gateway, even when the client never routed it there. Separate tables keep each surface's authority separate. The `/v1` bridge (Section 6.8) crosses between them only for names the operator declared as aliases.

**No new operation kinds or classifiers.** An MCP tool either maps onto one of the five kinds (a Postgres `query` is `sql`, a filesystem `write_file` is `fs_write`, a fetch tool is `http`, and a Git `push_files` is `fs_write` over `files[].path`, the Cline `read_files` grammar) or it is opaque with an explicit decision (`create_pull_request: flag`). Tool annotations are recorded in the `tools/list` log line but never decide anything: a server's claim that it is `readOnlyHint: true` is exactly the claim a malicious server would make.

### 6.5 Visibility and tools/list (D6, D7, D12)

```
held      = {s for s in skills if holds(identity, f"skill:{s.id}")}      # no RBAC_ENABLED bypass
wanted    = ⋃ s.tools for s in held                                      # "<server>__<tool>"
for each server in wanted (concurrently, from cache when fresh):
    listed = upstream tools/list (all pages)
    for t in listed with f"{server}__{t.name}" in wanted:
        if inspect_catalogue(t.description, t.inputSchema) hits → withhold, WARNING   (D12)
        else emit {name: f"{server}__{t.name}", description, inputSchema, annotations?}
```

- An upstream that is down or times out contributes no tools and logs a `WARNING`. `tools/list` still succeeds with the rest. The skill's other servers are unaffected.
- A skill tool that the upstream does not list is not emitted (it would fail anyway) and logs at `INFO` once per cache period.
- `outputSchema` and `title` are passed through when present, and `annotations` too, marked in the docs as unverified hints.
- **`tools/list` writes no row** (O4). It is deterministic from the config and the upstream catalogue. The `INFO` line records user, servers, tool count and `mcp_config_digest`.

### 6.6 Skills (D5)

```yaml
# examples/mcp.yaml
servers:
  github:
    url: https://mcp-github.internal.example/mcp      # https required unless allow_insecure: true
    auth: { type: bearer, token_env: MCP_GITHUB_TOKEN }
    timeout_seconds: 60
  postgres-staging:
    url: http://pg-mcp.internal:8080/mcp
    allow_insecure: true                               # private network; recorded in the digest
    auth: { type: header, name: X-Api-Key, value_env: MCP_PG_STAGING_KEY }

skills:
  open-pull-request:
    version: 1.2.0
    description: Create a branch, push files and open a pull request.
    instructions: |
      Work on a new branch named agent/<short-topic>. Push all changed files in one
      push_files call, then open a pull request against main with a summary of the change.
      Never push to main directly.
    tools: [github__create_branch, github__push_files, github__create_pull_request]
    requires: []
  run-migration:
    version: 0.3.0
    description: Apply schema migrations to the staging database.
    instructions: |
      Inspect the current schema with SELECT queries first. Apply one statement per call.
    tools: [postgres-staging__query]
    requires: [action:sql:ddl]

v1_aliases:
  prefixes: ["harness_", "harness__"]   # OpenCode "<server>_<tool>", Cline 4.x "<server>__<tool>"
```

```yaml
# ACTION_POLICY_FILE, new sections
mcp_tools:
  postgres-staging:
    query:      { kind: sql,      target: sql }
  github:
    push_files: { kind: fs_write, target: "files[].path" }
mcp_opaque_tools:
  github:
    create_branch: allow
    create_pull_request: flag          # recorded for review, not blocked
```

A **skill** is therefore: an id (the key, `[a-z0-9][a-z0-9-]{0,47}`), a `version` (a string recorded on every row, semver by convention and not enforced), a `description` and `instructions` for humans and the model, `tools` (the visibility set), and `requires` (the action permissions without which its tools cannot succeed). It carries **no policy of its own**. What a call may do is decided by the action policy, which applies to every tool whichever skill exposed it. Two skills containing one tool expose it once, and the row's `skills` column lists every held skill that contains it, as `id@version`.

Instructions are delivered as MCP **prompts**: `prompts/list` returns one prompt per held skill (`name: skill-<id>`, `description`), and `prompts/get` returns the instructions as one `user` message. Whether `initialize.instructions` should also carry them is O11.

### 6.7 Results (D11)

A `CallToolResult` from upstream goes back **unmodified**. Before it is returned:

1. Its size (the serialized result) is checked against `MCP_MAX_RESULT_BYTES` (per-server override `max_result_bytes`). If it is larger, the agent gets `isError: true`, text `[harness] the result of <name> (<id>) exceeded <n> bytes and was not returned; the call ran`, and `outcome='result_too_large'`.
2. `text` blocks, the `text` of embedded `resource` blocks and the canonical JSON of `structuredContent` are inspected with `pattern_detector.inspect` ([app/services/pattern_detector.py:324](../../../app/services/pattern_detector.py)) as one `tool` message under the `code` profile. Hits go to `result_flags` (`[{list, pattern_id}]`, never the matched text). Under the `code` profile the `tool` cell is `flag`, so nothing is blocked. A deployment profile that sets `tool: block` replaces the result with an error result and `outcome='result_blocked'`.
3. `image`, `audio` and `resource_link` blocks pass through uninspected, and their count is recorded in `result_flags` as `{"uninspected": n}`.

**No PII redaction at the gateway (O5).** The harness redacts PII on the way *to the LLM upstream* (PRD-003, PRD-012). A gateway result goes to the agent, which runs for a user already authorized for the data, and it reaches an LLM only when the agent sends it as a `tool` turn. Through `/v1` that turn is redacted at step 6 under the `code` policy, which covers `tool` ([app/services/pii_policy.py:131](../../../app/services/pii_policy.py)). Redacting at the gateway too would alter data the agent may need verbatim (a row id or an email it must write back), for no protection that `/v1` does not already give.

**Results are not stored.** The row keeps `result_bytes`, `result_hash` (`hash_prompt` over the canonical result) and `result_flags`. A tool result can be a database dump. The audit is evidence of what happened, not a copy of the data.

### 6.8 The /v1 bridge (D15)

The agent advertises gateway tools to the model under its own prefix for the `harness` server: OpenCode `harness_postgres-staging__query` ([SOURCES.md:80](../../../tests/corpora/actions/SOURCES.md)), and Cline 4.x `harness__postgres-staging__query`, sanitized and hashed when over 64 characters ([SOURCES.md:160](../../../tests/corpora/actions/SOURCES.md)). Without a bridge, step 7c sees an unmapped name, denies it as `tool.unknown`, and the agent never gets to call the gateway at all.

At step 7c, before `map_tool_call`, the engine tries each `v1_aliases.prefixes` entry in order. When the name starts with the prefix and the remainder is `<server>__<tool>` visible to the caller, the call is evaluated with `surface=McpSurface(server, visible)`. The row is stored with `surface='v1'`, `mcp_server=server` and `arguments_canonical_hash`. If two prefixes resolve, the call is `tool.malformed` (fail closed). If none resolves, today's behaviour applies unchanged. A Cline name truncated with a hash suffix does not resolve and stays `tool.unknown`, a stated limitation and the reason server ids are short.

**OpenCode 2.x must set `codemode: false` on the `harness` server** ([SOURCES.md:113](../../../tests/corpora/actions/SOURCES.md)). Otherwise its MCP tools are called inside `execute`, which stays `tool.unknown` and is never opened (PRD-017).

**Correlation.** At M7 the gateway looks up the newest `/v1` row with the same `user_id`, `mcp_server`, resolved tool, `arguments_canonical_hash` and `decision IN ('allow','flag')`, no older than `MCP_LINK_WINDOW_SECONDS`, and not already linked. It copies that row's `audit_id` and stores its id as `linked_decision_id`. This is correlation, not proof. The docs say so, and an unlinked gateway call (`audit_id IS NULL`) is a first-class filter in the Actions view: it marks a call that no model response through the harness proposed.

### 6.9 The audit columns (D21)

```python
ACTION_DECISIONS_ADDED_COLUMNS = {
    "surface": "TEXT NOT NULL DEFAULT 'v1'",   # v1 | mcp
    "mcp_server": "TEXT",                      # gateway server id; v1 alias rows too
    "skills": "TEXT",                          # JSON ["open-pull-request@1.2.0"]; mcp rows
    "arguments_canonical_hash": "TEXT",        # sha256 of canonical_json(arguments); mcp + alias rows
    "linked_decision_id": "INTEGER",           # the v1 alias row this call was correlated to
    "outcome": "TEXT",                         # NULL (not forwarded) | ok | tool_error | upstream_error
                                               # | timeout | result_too_large | result_blocked
    "duration_ms": "INTEGER",
    "result_bytes": "INTEGER",
    "result_hash": "TEXT",
    "result_flags": "TEXT",                    # JSON; no matched text
    "mcp_config_digest": "TEXT",
}
CREATE INDEX IF NOT EXISTS idx_action_decisions_link ON action_decisions(user_id, arguments_canonical_hash);
```

These are nullable or defaulted (the `test_added_columns_declaring_not_null_also_declare_a_default` rule, [app/db/models.py:60](../../../app/db/models.py)), so a pre-PRD database converges through `init_db()` and existing `/v1` rows read as `surface='v1'`. `tool_call_id` for a gateway row is the JSON-RPC `id` as a string, prefixed `mcp:`. `session_id` is NULL. `audit_id` is NULL unless it was correlated. `outcome='tool_error'` means the server returned `isError: true`. `upstream_error` means a JSON-RPC error or transport failure after forwarding, which still means *may have run*.

### 6.10 Directory structure (files touched)

```
app/
├── config.py                     # + 9 MCP settings, validators
├── main.py                       # mcp_config.load() after action_config.load(); mount /mcp when MCP_ENABLED
├── db/models.py, database.py     # ACTION_DECISIONS_ADDED_COLUMNS, link index, record_outcome, link lookup
├── models/mcp_schemas.py         # NEW: JSON-RPC envelope, CallToolResult shapes (pydantic, northbound only)
├── routers/mcp.py                # NEW: POST/GET/DELETE /mcp
├── routers/admin.py              # /audit/actions filters; GET /skills
└── services/
    ├── authz.py                  # mcp:connect, skill:* acceptance
    ├── action_classifiers/__init__.py   # + tool.not_in_skill, NON_GRANTABLE_RULES
    ├── action_config.py          # + mcp_tools, mcp_opaque_tools sections
    ├── action_policy.py          # + McpSurface, surface=, alias resolution
    ├── action_audit.py           # + MCP fields, record_outcome
    ├── mcp_config.py             # NEW: servers, skills, v1_aliases, cross-validation, digest
    ├── mcp_gateway.py            # NEW: M2–M9, visibility, catalogue inspection, result inspection
    ├── mcp_upstream.py           # NEW: the only module importing `mcp`; sessions, auth headers, timeouts
    └── query_pipeline.py         # step 7c passes alias context (no new step)
chat_ui/chat_ui/                  # mcp_config.load() in the mounted lifespan; Actions filters; Skills panel
scripts/stub_mcp_server.py        # NEW (tests only, separate process)
examples/mcp.yaml                 # NEW
tests/corpora/mcp/                # NEW
```

### 6.11 Patterns followed

- **Strict YAML, wholesale replacement and fail at startup.** `MCPConfigError` names the file, the node and the rule, the `ActionConfigError` shape. There is no built-in MCP config: `MCP_ENABLED=true` with an empty `MCP_CONFIG_FILE` is a startup error, because an empty gateway is a misconfiguration and not a floor.
- **Loaded in both lifespans.** This applies to `app/main.py:15-20` and to `chat_ui/chat_ui/chat_ui.py:250`'s `register_lifespan_task`, because of the Reflex `api_transformer` bypass (PRD-007).
- **Pure engine, I/O at the edges.** `action_policy` stays free of I/O. Only `mcp_upstream` talks to servers, and only `action_audit` and `database` write rows.
- **A route mounted only when its flag is on.** The `V1_ENABLED` precedent ([app/main.py:31-36](../../../app/main.py)) is followed: off means `/mcp` is a 404 and `mcp_config.load()` reads nothing.
- **Previews and hashes, never content.** The `arguments_preview` convention stays as it is (PRD-016 T10). Results get only a hash.

## 7. Tools/Features

### F1 — Northbound endpoint
`POST /mcp` with the M0–M3 checks. `initialize` answers with the negotiated version (the client's version if supported, otherwise the newest supported), `capabilities: {tools: {listChanged: false}, prompts: {listChanged: false}}` and `serverInfo: {name: "harness", version}`. With no sessions, `initialize` is a courtesy: a `tools/call` without a prior `initialize` is accepted, because a stateless server cannot know. Notifications get `202 Accepted` with no body.

### F2 — Southbound client
`mcp_upstream.list_tools(server, user_id)` and `call_tool(server, user_id, name, arguments, timeout)` over the SDK's `ClientSession` with its Streamable HTTP client. Headers come from config. Redirects are not followed. `MCP-Protocol-Version` is set by the SDK. A per-`(server, user_id)` session pool is reaped on idle. The client capabilities are empty, and any server-to-client request is answered `-32601`.

### F3 — MCP config and skills
`mcp_config.load()`, `get_config()`, `mcp_config_digest()`, `held_skills(identity)` and `visible_tools(identity) -> Mapping[server, frozenset[tool]]`, with the validation in Section 9.3.

### F4 — Engine surface and `tool.not_in_skill`
Section 6.4. The existing PRD-016 suites pass unchanged with `surface` omitted.

### F5 — Visibility and catalogue inspection
Section 6.5. The catalogue is inspected with the `injection` list only (the list the `code` profile loads), over `description`, every `description` inside `inputSchema`, and `title`.

### F6 — tools/call execution path
Section 6.3, including correlation (F9), denial shape (D8), timeout (D14) and result handling (F7).

### F7 — Result inspection and caps
Section 6.7.

### F8 — Prompts from skills
`prompts/list` and `prompts/get` for held skills only. A prompt for a skill the caller does not hold gets `-32602`, the same as an unknown prompt.

### F9 — `/v1` alias resolution and correlation
Section 6.8. The alias step adds no database read to step 7c. Correlation reads once, at M7.

### F10 — Audit
`record(decisions, identity, audit_id=None, session_id=None, *, mcp: McpRecord | None = None) -> list[int]` and `record_outcome(row_id, outcome, duration_ms, result_bytes, result_hash, result_flags) -> None`. The latter never raises into the response path: a failure logs `ERROR` with the user and row id.

### F11 — Admin API and console
Filters on `GET /audit/actions`, `GET /skills`, the Actions view's surface filter and new columns (`server`, `skills`, `outcome`, and `linked` as a link to the `/v1` row), and a Skills panel. A deployment with `MCP_ENABLED=false` shows neither the filter nor the panel.

### F12 — Stub server, corpus and E2E
The stub server, `tests/corpora/mcp/` (at least 30 calls: every outcome, every visibility case, the four MVP-goal calls, alias and correlation cases), and the two E2E clients.

## 8. Technology Stack

| Layer | Choice | Note |
|---|---|---|
| Runtime | Python 3.11 (the `Dockerfile` base), FastAPI, httpx | Unchanged |
| MCP client | **`mcp` (the official Python SDK, `modelcontextprotocol/python-sdk`)**, **client side only**: `mcp.ClientSession` and its Streamable HTTP client (`mcp.client.streamable_http`) | New dependency. Pinned to an exact version in `requirements.txt` (the `sqlglot==30.27.0` convention), chosen and verified in STORY-001. It is imported only by `app/services/mcp_upstream.py`, which an import-graph test asserts. Its transitive dependencies (anyio, httpx-sse, starlette, pydantic, …: verify the list) are checked against the existing pins. Upgrades are a story of their own with the stub-server suite as the gate |
| MCP server side | Hand-written in `app/routers/mcp.py` + `mcp_gateway.py` | Seven methods, stateless and JSON-only. The SDK's server (`FastMCP` / `StreamableHTTPSessionManager`) was rejected for the northbound side. It wants its own task group in the app lifespan, which the Reflex mount bypasses (PRD-007). It owns request parsing, where duplicate-key refusal and identity must sit. Its value is mostly in session and SSE handling, which the MVP does not use (O-SDK in 15) |
| Stub server | The SDK's `FastMCP`, in `scripts/stub_mcp_server.py`, as a **separate process** in tests | Test infrastructure only, never imported by `app/` |
| Config | YAML via `strict_yaml` | As PRD-016 |
| Storage | libSQL / Turso | Columns added through the existing mechanism. No new table |
| Admin UI | Reflex 0.9.6.post1, existing admin shell | One filter, four columns, one panel |

## 9. Security & Configuration

### 9.1 Authentication & authorization

`/mcp` takes the harness bearer token (`require_identity`) and requires `mcp:connect` through `authorize()`. With `RBAC_ENABLED=false` that gate is open, as for every harness permission. **Visibility is not.** Skills are checked with `holds()` ([app/services/authz.py:168](../../../app/services/authz.py)), which ignores `RBAC_ENABLED` (PRD-016 D7), so with RBAC off a caller sees only the skills that the matrix grants its role, and in the built-in matrix that is none. The break-glass `ADMIN_TOKEN` is refused (`403 ingress:break_glass` semantics, without a pipeline row). `GET /skills` requires `stats:read`. `GET /audit/actions` keeps its `audit:read:all` / `audit:read:own` scoping.

**No OAuth 2.1 on `/mcp` in the MVP.** The harness's tokens are opaque bearer tokens issued by `manage_users.py`, and both surveyed clients accept a static `Authorization` header for a remote server (verify in STORY-001). A `401` carries `WWW-Authenticate: Bearer realm="harness"` with no `resource_metadata`, so a spec-following client does not start an OAuth discovery it cannot complete. Becoming an OAuth resource server is Section 13.

### 9.2 Threat reasoning

| # | Threat | Treatment |
|---|---|---|
| T1 | **The harness becomes the executor** (the D2 change). A wrong `allow` now has a real effect, carried out with a credential the harness holds. A compromised or misconfigured harness is a confused deputy for every upstream | Three gates, each written by someone: server configured, tool in a held skill, call allowed by the action policy, whose dangerous defaults are `deny` with no grant. The decision is recorded before forwarding (D9). Operators are told to issue least-privilege upstream credentials (a GitHub token scoped to the repositories the skill names). The gain that offsets the risk: for a gateway tool a `deny` can no longer be ignored by the client |
| T2 | **Token passthrough.** The caller's harness token is forwarded upstream, or an upstream token is accepted from the caller | Southbound headers are built only from config. Inbound `Authorization`, `Cookie`, `Mcp-Session-Id` and every other inbound header are dropped. Credential values come from env names, are never logged, digested, stored or returned, and a missing env var is a startup error |
| T3 | **Tool poisoning.** A description or schema carries instructions to the model | Only skill-listed tools are exposed. Descriptions and schema descriptions are injection-inspected and a hit withholds the tool (D12). `/v1` already forwards client-supplied `tools[].description` uninspected ([docs/features.md:486](../../../docs/features.md)). For gateway tools this closes that gap at the source |
| T4 | **Rug pull.** An upstream changes a tool's description or behaviour after approval | Decisions depend on name and arguments, not description. A renamed tool is out of every skill (`tool.not_in_skill`). Description changes are re-inspected on every cache refresh, and the `INFO` line records a description hash, so a change is visible. Pinning description hashes in the skill is Section 13 |
| T5 | **Indirect prompt injection through results** | Results are inspected as `tool` content and flagged (D11). Through `/v1` the result is inspected again as a `tool` turn (PRD-017), and step 7c decides whatever the model then proposes. The harness never acts on a result. Not blocked by default (PRD-011 D4) |
| T6 | **Calling a hidden or unmapped tool** | `tool.not_in_skill` (non-grantable deny) before mapping. A visible but unmapped tool cannot exist (startup cross-validation), and if one did it would be `tool.unknown`. Both are recorded. The `-32602` answer does not reveal whether the tool exists |
| T7 | **Argument smuggling.** Duplicate keys, oversized or non-object arguments, or the classifier and the forwarder disagreeing | One parse with duplicate keys refused. Classified and forwarded from the same object (6.3). `ACTION_MAX_ARGUMENT_CHARACTERS` applies to the canonical string. Non-object → `-32602` |
| T8 | **SSRF through the gateway** | Upstream URLs come only from config. No client field names a URL. `https` is required unless the server says `allow_insecure: true`. Redirects are not followed. URLs are validated at startup |
| T9 | **Executed but not recorded** | Record before forward. A storage failure → `-32603`, not forwarded. An outcome-update failure → `ERROR` log, with the decision row present. PRD-018's offline buffering, when it lands, must **not** apply to the pre-forward write |
| T10 | **Ambiguous outcomes.** A timeout or transport error after forwarding, then an agent retry that duplicates a side effect | Never retried by the harness. The result text says the call *may have run*, and the outcome is `timeout` or `upstream_error`. Amended after STORY-001: the spec says an unknown-session `404` obliges the client to re-initialize, but it does **not** say the request was not processed. The harness therefore re-initializes for the *next* call and never replays a forwarded `tools/call`, not even after a `404` |
| T11 | **DNS rebinding / cross-origin browser requests** to `/mcp` | A bearer token is required, so there is no ambient credential. A present `Origin` must be on `MCP_ALLOWED_ORIGINS` (default empty: any browser `Origin` → 403). CLI agents send none |
| T12 | **Server-to-client channels.** `sampling` is an LLM call outside the pipeline, `elicitation` asks the user for data, `roots` exposes paths | The harness declares no client capabilities southbound and answers any such request `-32601`. Northbound it is stateless and cannot carry them. An upstream that answers `tools/call` with `resultType: "input_required"` (`2026-07-28` multi-round-trip) gets that result refused as `upstream_error` ("may have run"). It is never answered and never relayed northbound (amended after STORY-001). Routing sampling through the pipeline is Section 13 |
| T13 | **Cross-user leakage through upstream session state** | Southbound sessions are per `(server, user_id)`. A stateful server across harness instances may still see one user under two sessions. This is stated in the docs, and servers that mix users within a session are unsupported |
| T14 | **Secrets in results reaching the audit** | Results are not stored (hash, size and flags only). `arguments_preview` keeps PRD-016 T10's accepted exposure |
| T15 | **Denial of service.** Floods, slow servers, huge results | `usage_limits.admit` per call (D13). Per-server timeouts. Request and result caps. `tools/list` is cached and fetched concurrently with the per-server timeout |
| T16 | **Reason strings leak config** | `reason` stays the PRD-016 template. Gateway messages name the tool the caller sent and the server id, never a URL, header name or env name |
| T17 | **Executing code in the harness** | Out of scope by construction: no stdio, no in-process servers, and `execute.code` stays denied. An import-graph test asserts that `app/` imports no `subprocess` from `mcp_*` modules and does not import the SDK's server or stdio modules |

### 9.3 Configuration

| Variable | Default | Validation | Purpose |
|---|---|---|---|
| `MCP_ENABLED` | `false` | bool | Mount `/mcp`, load `MCP_CONFIG_FILE`, enable the `/v1` alias step |
| `MCP_CONFIG_FILE` | `""` | Required and readable when enabled | Servers, skills, aliases |
| `MCP_CALL_TIMEOUT_SECONDS` | `60` | `1–600` | Default per-call timeout, overridable per server |
| `MCP_MAX_REQUEST_BYTES` | `1048576` | `≥ 1024` | Northbound body cap |
| `MCP_MAX_RESULT_BYTES` | `1048576` | `≥ 1024` | Result cap, overridable per server |
| `MCP_TOOLS_CACHE_SECONDS` | `300` | `0–86400` (`0` = no cache) | Upstream `tools/list` cache |
| `MCP_UPSTREAM_SESSION_IDLE_SECONDS` | `300` | `≥ 10` | Southbound session reap |
| `MCP_LINK_WINDOW_SECONDS` | `600` | `0–86400` (`0` = no correlation) | `/v1` proposal → gateway call correlation |
| `MCP_ALLOWED_ORIGINS` | `""` | comma list of origins | Browser origins allowed on `/mcp` |

`MCP_CONFIG_FILE` validation (each an `MCPConfigError` naming the file and the node): an unknown top-level or nested key · a server id outside `[a-z0-9][a-z0-9-]{0,31}` · a `url` that is not absolute `http(s)`, or `http` without `allow_insecure: true` · an `auth.type` outside `bearer | header | none` · a `token_env` / `value_env` that is unset or empty in the environment · a header `name` that is `Authorization` under `type: header`, or a hop-by-hop or `Mcp-*` header · `timeout_seconds` / `max_result_bytes` out of range · a skill id outside its pattern · an empty `tools` list · a skill tool not of the form `<configured server>__<tool>` · a skill tool with no `mcp_tools` / `mcp_opaque_tools` entry · a `requires` entry outside `ACTION_PERMISSIONS` · a role granted `skill:<id>` for an undefined skill · a role holding a skill without its `requires` (O2) · an empty `v1_aliases.prefixes` entry, or one containing characters outside `[A-Za-z0-9_-]` · duplicate YAML keys.

`ACTION_POLICY_FILE` additions: `mcp_tools` and `mcp_opaque_tools` are mappings of server id → the existing `tools` / `opaque_tools` shapes, validated by the existing functions. A tool in both is refused, as today. An empty server mapping is refused (PRD-016 T7). A server id there that is absent from `MCP_CONFIG_FILE` is refused by `mcp_config.load()`. With `MCP_ENABLED=false` the sections still validate, so a policy file is portable between deployments.

### 9.4 Out of scope (security)

MCP servers that an agent reaches directly, outside the harness, are not seen, decided or recorded. The harness can only advise on those, through `/v1` proposals. Also out of scope: upstream server integrity (the operator runs and trusts them), OAuth on `/mcp`, per-user upstream identity, sandboxing, and results inspection beyond patterns.

## 10. API Specification

| Endpoint | Change |
|---|---|
| `POST /mcp` | **New.** MCP Streamable HTTP, stateless, JSON responses. `mcp:connect` |
| `GET /mcp`, `DELETE /mcp` | **New.** `405 Method Not Allowed` (no SSE stream, no sessions) |
| `GET /audit/actions` | `?surface=v1\|mcp`, `?server=`, `?outcome=`, `?linked=true\|false`. Entries gain `surface`, `mcp_server`, `skills`, `linked_decision_id`, `outcome`, `duration_ms`, `result_bytes`, `result_flags` |
| `GET /skills` | **New.** `stats:read` |
| `POST /v1/chat/completions` | No shape change. Alias names are decided under the MCP mapping (6.8) |

```http
POST /mcp
Authorization: Bearer <harness token>
Content-Type: application/json
Accept: application/json, text/event-stream

{"jsonrpc":"2.0","id":7,"method":"tools/call",
 "params":{"name":"postgres-staging__query","arguments":{"sql":"DROP TABLE users"}}}
```

```json
{"jsonrpc":"2.0","id":7,"result":{"isError":true,"content":[{"type":"text",
 "text":"[harness] tool call postgres-staging__query (7) was denied: destructive SQL is not permitted: DROP"}]}}
```

| Condition | Answer |
|---|---|
| Missing or invalid token / break-glass / no `mcp:connect` / bad `Origin` | HTTP `401` / `403` / `403` / `403` |
| Body too large / wrong content type | HTTP `413` / `415` |
| Usage refused | HTTP `429`, `Retry-After` from `resets_at` |
| Not JSON, duplicate keys / not a single JSON-RPC request | `-32700` / `-32600` |
| Unknown method | `-32601` |
| Bad params; tool not visible (recorded); unknown prompt | `-32602` |
| Decision could not be recorded | `-32603`, not forwarded |
| Denied by policy | `result.isError: true`, note text |
| Upstream JSON-RPC error after forwarding | `result.isError: true`, `[harness] <name> (<id>) failed on server <server>; the call may have run`; the upstream message is logged, not returned (T16) |
| Timeout | `result.isError: true`, `… timed out after <n>s; the call may have run` |

```json
GET /skills
{"skills":[{"id":"open-pull-request","version":"1.2.0","description":"…",
  "tools":["github__create_branch","github__push_files","github__create_pull_request"],
  "requires":[],"roles":["dev"]}],
 "mcp_config_digest":"sha256:…"}
```

Internal API (Python):

```python
mcp_config.load() -> None                                       # raises MCPConfigError; startup only
mcp_config.visible_tools(identity) -> Mapping[str, frozenset[str]]
action_policy.evaluate(call, identity, policy=None, *, surface: McpSurface | None = None) -> ActionDecision
action_audit.record(decisions, identity, audit_id=None, session_id=None, *, mcp: McpRecord | None = None) -> list[int]
action_audit.record_outcome(row_id: int, outcome: str, duration_ms: int, result_bytes: int | None,
                            result_hash: str | None, result_flags: str | None) -> None
mcp_upstream.call_tool(server: str, user_id: str, name: str, arguments: dict, timeout: float) -> CallToolResult
```

## 11. Success Criteria

### MVP definition
Against the stub server, every file in `tests/corpora/mcp/` produces its declared decision and outcome for every role it names. No denied call increments the stub's counter. Every call has a row before the stub sees it. OpenCode 2.0.10 and the Cline CLI each list their skill's tools and complete one allowed and one denied call through `/mcp`. A broken `MCP_CONFIG_FILE` stops startup naming the file and the node.

### Functional requirements
- [ ] `MCP_ENABLED=false`: `/mcp` is 404, `mcp_config.load()` opens no file (asserted with a path that fails if opened), and every PRD-017 test passes unchanged
- [ ] `tools/list` for a role holding `skill:open-pull-request` returns exactly its three tools. For `user` it returns `[]`. With `RBAC_ENABLED=false` and the built-in matrix it returns `[]`
- [ ] A hidden tool → `-32602`, row `deny` / `tool.not_in_skill`, stub counter 0
- [ ] `DROP TABLE users` → `isError` with the exact note, row `deny` / `sql.ddl`, `outcome NULL`, stub counter 0. For `dba` with `action:sql:ddl`: `allow`, `granted_by='action:sql:ddl'`, `outcome='ok'`
- [ ] `push_files` with `.github/workflows/ci.yml` → `fs.write_protected` deny; without it → allow and forwarded
- [ ] `create_pull_request` (`mcp_opaque_tools: flag`) → forwarded, row `flag` / `tool.opaque`
- [ ] The stub sees the configured credential, and never the caller's token or any inbound header other than the SDK's own
- [ ] Storage failure injected at M7 → `-32603`, stub counter 0. Failure at `record_outcome` → result returned, `ERROR` logged, row present with `outcome NULL`
- [ ] `slow` beyond its timeout → `isError` "may have run", `outcome='timeout'`, no retry (stub counter 1)
- [ ] `huge` → `result_too_large`. `inject` → result unmodified and `result_flags` naming the injection pattern id. `poisoned` → absent from `tools/list`, with a `WARNING` that contains no description text
- [ ] Duplicate keys in the body → `-32700`. A batch array → `-32600`. Arguments `[]` → `-32602`
- [ ] A server-to-client `sampling/createMessage` from the stub → answered `-32601`, and nothing reaches OpenRouter
- [ ] `/v1` alias: `harness_postgres-staging__query` with `DROP TABLE` is denied at 7c under `sql.ddl` (today it is `tool.unknown`). With `SELECT` it is released. The following gateway call within the window carries the `/v1` row's `audit_id` and `linked_decision_id`. Outside the window, both are NULL
- [ ] `GET /audit/actions?surface=mcp&outcome=timeout` and `?linked=false` filter correctly. `GET /skills` lists the roles per skill and contains no URL or credential
- [ ] `init_db()` on a PRD-017 database adds the columns and the index and touches no other table. Old rows read `surface='v1'`
- [ ] The 2b/2c-style refusals: break-glass → 403, usage over the rate → 429 with `Retry-After`, and in neither case a row or an upstream request

### Configuration criteria
- [ ] Every Section 9.3 rule has a failing-file test asserting `MCPConfigError` (or `ActionConfigError` for the policy sections), with the file and node named
- [ ] `examples/mcp.yaml` plus the example policy sections load in a test
- [ ] Changing a skill's version changes `mcp_config_digest`. Changing a credential's *value* does not

### Quality indicators
- [ ] Full suite green. The PRD-016 corpus suites are unchanged, apart from the rule-count assertions (25 → 26, 10 → 11 non-grantable), each with a comment citing D7
- [ ] `mcp` is imported only by `mcp_upstream.py`, and no `app/` module imports `subprocess`, `mcp.client.stdio` or `mcp.server` (import-graph test)
- [ ] Gateway overhead (M0–M9 excluding the upstream round trip) p95 measured against the stub on a local libSQL file and recorded in the corpus story, with a target of ≤ 25 ms. The gateway makes at most three database round trips per call (admit, link lookup plus insert, outcome)
- [ ] The Actions view renders MCP rows at phone width. The Skills panel renders with zero skills

## 12. Implementation Phases

### Phase 1 — Verify the protocol and the clients (Stories 1–3)
**Goal:** every MCP and client assumption checked before code depends on it.
**Deliverables:** a spike recording the spec revision(s) to support, header names, session-expiry semantics, batching status, the unknown-tool error code and the `Origin` rule. A client survey: OpenCode 2.0.10 and the Cline CLI with a remote Streamable HTTP server and a static `Authorization` header, their tool-name prefixing (`codemode: false` for OpenCode), and whether either insists on OAuth discovery. The `mcp` SDK version pinned, with its dependency diff against `requirements.txt`. The threat model of Section 9.2 refined against the survey.
**Validation:** `tests/corpora/mcp/SOURCES.md` exists with pinned links, and every "verify" in this PRD is resolved or carried as a stated limitation.

### Phase 2 — Vocabulary and configuration (Stories 4–8)
**Goal:** the gateway's configuration exists and is validated before any traffic.
**Deliverables:** the settings. `mcp:connect` and `skill:*` in `authz`. `tool.not_in_skill`. `mcp_tools` / `mcp_opaque_tools` in `action_config`. `mcp_config` with cross-validation and digest, loaded in both lifespans. The added columns and index. `examples/mcp.yaml`.
**Validation:** every Section 9.3 rule has a failing-file test, and the PRD-016 suites are green.

### Phase 3 — The gateway (Stories 9–15)
**Goal:** `tools/list` and `tools/call` work end to end against the stub server.
**Deliverables:** the stub server. `mcp_upstream` (sessions, credentials, timeouts, refusals of server-to-client requests). The northbound router and JSON-RPC handling. Visibility and catalogue inspection. `evaluate(surface=)`. Record-before-forward with outcome update. Result inspection and caps. Prompts from skills.
**Validation:** the functional criteria above, except the `/v1` bridge, pass in process.

### Phase 4 — Bridge, evidence and clients (Stories 16–21)
**Goal:** gateway calls read beside the prompts that caused them, and real agents use the gateway.
**Deliverables:** `/v1` alias resolution at 7c and correlation. The `GET /audit/actions` filters and `GET /skills`. The Actions view and Skills panel. The `tests/corpora/mcp/` suite and the latency measurement. E2E with OpenCode and Cline. README, `docs/features.md`, `docs/roadmap.md` and `.env.example`.
**Validation:** the MVP definition, and the full suite green.

## 13. Future Considerations

- **OAuth 2.1 on `/mcp`.** The harness as a resource server with Protected Resource Metadata, and an authorization server in front of `manage_users.py` identities, for clients that only speak OAuth.
- **Per-user upstream credentials.** A user's own GitHub OAuth grant, held by the harness and attached per call, so upstream audit logs name the person. This replaces the shared service credential for servers that support it.
- **OAuth client-credentials southbound**, instead of static tokens, with refresh handled by the harness.
- **Skill-scoped constraints.** Argument constraints (`repo in [acme/app]`, `branch !~ ^main$`), skill-scoped grants ("`action:sql:ddl` only through `run-migration`"), and pinned tool-description hashes (T4).
- **`MCP_REQUIRE_PROPOSAL`.** Execute a gateway call only when it correlates to a `/v1` proposal the harness allowed, so a client cannot call a tool no model asked for through the harness (O8).
- **Resources and prompts from upstream servers**, behind a read policy (`resources/read` is a data read with no classifier today).
- **Sampling through the pipeline.** A server's `sampling/createMessage` would become a harness LLM request with identity, patterns, PII and audit.
- **stdio servers in operator-managed sandboxes**, if a deployment needs them and a sandbox story exists. They stay out of the harness process in any design.
- **The `2026-07-28` revision northbound** (added after STORY-001): `server/discover`, per-request `_meta` versions, the `Mcp-Method` / `Mcp-Name` headers with `-32020` / `-32022`, `resultType`, and `ttlMs` / `cacheScope`. The spec allows one endpoint for both eras, so this is additive once the target clients speak it.
- **Streaming and progress** northbound, once the harness has real streaming (PRD-015 D8 is still buffered).
- **Per-server workspace roots**, so an MCP filesystem server's paths are judged against that server's roots and not the client's (O10).
- **A shared upstream registry** with PRD-020's provider registry, if both grow health checks and fallbacks. They are kept separate here because an LLM provider and a tool server fail and are trusted differently.
- **`tools/list` discovery rows**, if auditors need to know who saw which catalogue (O4).

## 14. Risks & Mitigations

| # | Risk | Likelihood / Impact | Mitigation |
|---|---|---|---|
| 1 | **The spec moves.** MCP has shipped several revisions in a short time, changing transports, auth and headers | High / Medium | Supported versions are pinned and negotiated. The SDK pin is an explicit upgrade story. The stub-server suite is the gate. Every assumption is recorded in `SOURCES.md` with a revision |
| 2 | **Clients do not cooperate.** A client insists on OAuth discovery, cannot send a static header, or prefixes names in a way the alias step cannot resolve | Medium / High | STORY-001 surveys before code. Aliases are configurable. A client that cannot connect is documented as unsupported rather than worked around by weakening auth |
| 3 | **The harness becomes critical-path infrastructure for agent tooling.** A harness outage stops every gateway tool | Medium / Medium | It is the same availability dependency `/v1` already is. Stateless northbound allows several instances. PRD-018's database resilience reduces the M7 failure rate but is not required: the gateway fails closed without it |
| 4 | **Over-blocking.** Opaque-by-default tools force operators to write many `mcp_opaque_tools` entries, or they set everything to `allow` | Medium / Medium | The sample config shows classified mappings for the common servers (Postgres, Git push, fetch). `flag` is the rollout mode. The Actions view's `surface=mcp` filter shows what fires |
| 5 | **Correlation misleads.** Identical arguments from two proposals, or a client that re-sends a call | Low / Low | It is labelled "correlated" in the docs and the UI, and links to the newest unlinked match. Unlinked calls are surfaced rather than hidden |
| 6 | **Session pools grow** with many users × servers on one instance | Low / Medium | Idle reaping. Sessions are lazy, opened on first use. A per-instance cap is a follow-up if measurements call for it |

## 15. Appendix

### Decisions

| # | Question | Decision |
|---|---|---|
| D1 | Topology | **The harness is an MCP server northbound (one aggregated endpoint, `POST /mcp`) and an MCP client southbound.** Tools are named `<server>__<tool>`. Per-server endpoints were rejected: skills span servers, and the client would need more configuration |
| D2 | Which side executes | **The upstream MCP server, forwarded by the harness after an `allow`/`flag` that has been recorded.** The harness still runs no tool code. For gateway tools the decision becomes enforcement (T1) |
| D3 | Transports in the MVP | **Northbound Streamable HTTP, stateless, JSON responses only. Southbound Streamable HTTP only.** No stdio (that would mean spawning third-party code on the harness host) and no legacy HTTP+SSE |
| D4 | Engine reuse | **`evaluate(..., surface=McpSurface)` selects new per-server `mcp_tools` / `mcp_opaque_tools` tables in `ACTION_POLICY_FILE`.** Same rules, grants, fold and fail-closed boundary. No new operation kind or classifier. A separate namespace from `tools:` so that model-chosen `/v1` names cannot reach gateway mappings |
| D5 | What a skill is | **A named, versioned bundle in `MCP_CONFIG_FILE`: `version`, `description`, `instructions`, `tools[]`, `requires[]`.** It is the unit of visibility. It carries no policy, because the action policy decides every call whichever skill exposed it |
| D6 | How a role gets a skill | **A `skill:<id>` permission in `RBAC_ROLES_FILE`, checked with `holds()` (no RBAC bypass).** No built-in role holds one. `mcp:connect` gates the endpoint |
| D7 | Visibility | **`tools/list` = tools of held skills ∩ upstream listing, minus withheld tools.** A call outside it is `-32602`, recorded as the new non-grantable `tool.not_in_skill` |
| D8 | Denial wire shape | **`CallToolResult` with `isError: true` and PRD-017's `DENIAL_NOTE_TEMPLATE` text**, so the agent reads the reason and carries on. A JSON-RPC error was rejected because agents treat it as a transport failure |
| D9 | Audit ordering | **Record before forward. A failed record means no forwarding.** The outcome update is best effort and logged |
| D10 | Upstream credentials | **Held by the harness**, read from env names in config (`bearer` or a static `header`). The caller's token is never forwarded |
| D11 | Results | **Returned unmodified. Text is pattern-inspected under the `tool` cell (flag). The size is capped. Results are not stored. No PII redaction at the gateway** (the `/v1` `tool` turn is where PII is redacted) |
| D12 | Catalogue inspection | **Descriptions and schema descriptions are inspected with the injection list. A hit withholds the tool** |
| D13 | Usage and duplicates | **`usage_limits.admit(identity, charges_budget=False)` per `tools/call`**, sharing the requests-per-minute window. No duplicate check, because re-running a tool is normal |
| D14 | Timeouts and retries | **A per-server timeout and a best-effort `notifications/cancelled`; the result says "may have run". Never retried**, except re-`initialize` after an unknown-session answer |
| D15 | Link to the causing request | **`/v1` alias prefixes let step 7c decide gateway tools under the same mapping. Gateway calls are correlated to a released alias decision by user, tool and canonical arguments hash within `MCP_LINK_WINDOW_SECONDS`** |
| D16 | Southbound sessions | **Per `(server, user_id)` per instance, reaped on idle. No client capabilities** (no sampling, roots or elicitation) |
| D17 | Protocol versions | **A pinned set, negotiated per the spec. The newest supported is answered when the client's is unknown.** Resolved in STORY-001: `2025-03-26`, `2025-06-18` and `2025-11-25` (handshake). `2026-07-28` requests are refused with a plain `400` so dual-era clients fall back (Section 6.1) |
| D18 | SDK use | **`mcp` pinned exactly, client side only, imported by one module.** The northbound side is hand-written (Section 8) |
| D19 | Resources and prompts | **Upstream resources and prompts are not proxied. The harness serves skill instructions as its own prompts** |
| D20 | Rollout | **`MCP_ENABLED=false` by default. Off means not mounted and nothing loaded** |
| D21 | Audit schema | **Added columns on `action_decisions`** (extending the existing `ACTION_DECISIONS_ADDED_COLUMNS`; `record(decisions, identity, audit_ref=None, session_id=None, *, mcp=None)`, and the pre-forward write passes no `audit_ref` so it never journals, PRD-018 O8) and one index. No new table, because a gateway call is one decision with one outcome |

### Open decisions (proposed default)

| # | Question | Proposed default | Alternative |
|---|---|---|---|
| O1 | Do built-in `admin` and `user` hold `mcp:connect`? | **Yes.** Visibility is gated by skills, which no built-in role holds, so connecting alone exposes nothing | No built-in role holds it, the PRD-016 D6 posture |
| O2 | A role holds a skill without its `requires[]` | **Startup error.** A skill whose tools always deny is a misconfiguration | `WARNING` and boot |
| O3 | Rate accounting for `tools/call` | **Share the per-user requests-per-minute window** | A separate `MCP_CALLS_PER_MINUTE` counter (new usage column) |
| O4 | Record `tools/list` | **No rows, an `INFO` line only** | A discovery row per list |
| O5 | PII on results | **Not redacted at the gateway** | `MCP_RESULT_PII=redact` under the `code` policy |
| O6 | Catalogue injection hit | **Withhold the tool** | Show it and flag it |
| O7 | Tool naming | **`<server>__<tool>`, with server ids matching `[a-z0-9][a-z0-9-]{0,31}`** | `<server>.<tool>`, if both clients accept dots (verify the spec's name guidance) |
| O8 | Calls with no `/v1` proposal | **Allowed, visible as unlinked** | `MCP_REQUIRE_PROPOSAL=true` (Section 13) |
| O9 | Southbound session scope | **Per `(server, user_id)`** | One shared session per server |
| O10 | Workspace roots for MCP filesystem paths | **The same `workspace.roots` as the client**, with the docs telling operators to list both | Per-server roots in the MVP |
| O11 | `initialize.instructions` | **Unset. Skill instructions are served as prompts only** | A short list of held skills and their descriptions |
| O12 | Tell upstream servers who the user is | **No** (the credential is the harness's) | An opt-in `X-Harness-User` header per server |
| O-SDK | The SDK on the northbound side | **Hand-written** | The SDK's low-level server in stateless JSON mode, if STORY-001 finds it mounts cleanly under both lifespans |

### Facts to verify in STORY-001
- MCP: the supported revision strings. Batching removed in `2025-06-18`. The `Mcp-Session-Id` / `MCP-Protocol-Version` spellings. `404` for an expired session, and that a `404` means the request was not processed. That a stateless server may omit sessions. `InitializeResult.instructions`. Tool-name length and charset guidance. `-32602` for an unknown tool. The `Origin` requirement. That `notifications/cancelled` is the cancellation method.
- `mcp` SDK: the module paths `mcp.ClientSession` and `mcp.client.streamable_http`, that its client does not follow redirects (or can be told not to), how to set static headers and a per-call timeout, how it answers server-to-client requests when no callbacks are registered, and its transitive dependencies.
- Clients: OpenCode 2.0.10 remote MCP config (`type: remote`, `url`, `headers`, `codemode: false`). Cline CLI 3.0.74 / Cline 4.x Streamable HTTP config with headers. Each client's exact prefixing for a server named `harness`.
- Servers named in examples: the GitHub MCP server's `push_files` argument shape (`files[].path`) and tool names. The archived reference Postgres server's `query` → `sql` is already pinned ([SOURCES.md:248](../../../tests/corpora/actions/SOURCES.md)).

### Evidence (read on `main` @ `2253871`)
- `app/services/action_policy.py:262-345`: `evaluate()` maps, classifies, decides with `authz.holds`, folds, and catches every exception into a `deny` / `tool.malformed`. `:348` `evaluate_all`. The engine reads its tables only through `map_tool_call`'s parameters.
- `app/services/action_adapters.py:440-505`: `map_tool_call(call, tools, opaque_tools, max_argument_characters)`, with exact-name, case-sensitive matching and "prefixed MCP names are `Unknown` unless a deployment maps them" (`:449`). `:509-591` `BUILT_IN_TOOLS` for OpenCode 1.19.5/2.0.10, Cline 4.x/3.x and the generic SQL names (`query`→`sql`; `execute_sql`, `apply_migration`, `run_sql`→`query`).
- `app/services/action_config.py:276-304`: the 25 built-in rules. `:457`/`:482` `_validate_tools` / `_validate_opaque_tools`. `:724` `BUILT_IN_POLICY` with an empty `opaque_tools`. `:834` `_FILE_SECTIONS`.
- `app/services/action_classifiers/__init__.py:31,46,91`: `OperationKind`, `RuleId`, and `NON_GRANTABLE_RULES` (ten).
- `app/services/authz.py:29-48` `ACTION_PERMISSIONS` and `_KNOWN_PERMISSIONS`. `:57-80` the built-in matrix, in which no role holds an action permission. `:155` `authorize()` with the `RBAC_ENABLED` bypass. `:168` `holds()` without it.
- `app/services/action_audit.py:95` `record(decisions, identity, audit_id=None, session_id=None)`. `app/db/models.py:370-389` the `action_decisions` DDL. `app/db/database.py:796` `_add_missing_columns`.
- `app/services/query_pipeline.py:813-840` step 7c. `:925-948` record-after-row and fail-closed `ActionAuditError`. `:405`/`:427` steps 2b/2c.
- `app/services/tool_release.py:41` `DENIAL_NOTE_TEMPLATE`. `app/services/pattern_config.py:246-250` the `code` profile, `tool: flag`. `app/services/pii_policy.py:131` the `code` input roles include `tool`.
- `docs/features.md:484-488,536` and `tests/corpora/actions/SOURCES.md:80,112-113,160,222`: MCP names arrive prefixed, OpenCode 2.x calls MCP inside `execute` (always denied), and Cline 3.x `use_mcp_tool` / `access_mcp_resource` are `tool.unknown` by design.
- `docs/roadmap.md:55-63`: the item this PRD builds. `:33` the websocket-affinity limit that stateless `/mcp` avoids.
- `requirements.txt`: no `mcp`. `sqlglot==30.27.0` is the exact-pin precedent.

### Dependencies
- **Depends on:** PRD-016 and PRD-017 (done), PRD-005 (RBAC), PRD-011 (pattern inspection) and PRD-013 (usage gate).
- **Does not require PRD-018 (database resilience).** The gateway fails closed on storage errors without it. When it lands, its retry helps at M7, but its offline audit buffering must exclude the pre-forward decision write (T9).
- **Does not require PRD-020 (provider registry).** MCP servers are not LLM providers. A shared registry is a Future Consideration.
- **Blocks:** nothing. Enables skill-scoped constraints, OAuth on `/mcp` and `MCP_REQUIRE_PROPOSAL`.

### Related documents
- PRD-016 (action policy): the engine, rules, grants, `holds()`, `action_decisions`, `opaque_tools`, and T10/T11, which this PRD inherits
- PRD-017 (tool calling): step 7c, `DENIAL_NOTE_TEMPLATE`, the fail-closed record, and the client survey this PRD extends
- PRD-011 / PRD-012: the `tool` pattern cell, and PII on `tool` turns
- PRD-013: `usage_limits.admit`, break-glass refusal
- PRD-007: the both-lifespans rule

**Skills referenced:** frontend-design. It applies only to the Actions-view additions and the Skills panel (F11). Its direction to "make deliberate, opinionated choices … specific to this brief" is bounded by the existing admin shell and theme, which those additions reuse rather than restyle. No rule from it applies to Sections 6, 8 or 9.
