---
target_prd: PRD-017
slug: tool-calling
title: Tool calling on the OpenAI-compatible endpoint
status: draft
prd:
depends_on: [PRD-015, PRD-016]
blocks: []
estimated_stories: 10-12
created: 2026-09-16
---

# Tool calling on the OpenAI-compatible endpoint

## Problem

After PRD-015, `/v1/chat/completions` refuses `tools`. OpenCode and Cline in agent mode are unusable without function calling: the model must be able to return `tool_calls`, and the client must be able to send `tool`-role results back. Today [openrouter_client.py](../app/services/openrouter_client.py) reads only `message.content` and treats anything else as an unexpected shape.

## Goal

OpenCode and Cline run real tasks through the harness, with every tool call passed through PRD-016's action policy before the client sees it.

## Proposed scope

**In**
- Forward `tools` and `tool_choice` to OpenRouter.
- Parse `tool_calls` (and `content: null`) from upstream.
- Every `tool_call` evaluated by PRD-016 before the response leaves the harness.
- Denial wire shape the agent can understand and recover from (PRD-016 D4).
- `tool`-role messages accepted in the pipeline, under PRD-011/012 role policies.
- Duplicate key revisited for `tool` turns (PRD-009 D4).
- Tool-call arguments never PII-redacted; JSON validity guaranteed (PRD-012).
- Buffered SSE deltas for `tool_calls`.
- Audit: `has_tool_calls`, tool names, decisions (PRD-013/015 columns).
- E2E with OpenCode and Cline.

**Out**
- Real streaming.
- Parallel tool-call execution semantics beyond passing them through.
- MCP server hosting.

## Hand-off from PRD-016

What exists (all on `epic/PRD-016-action-policy-rules`, documented in [Features: Action policy rules](../docs/features.md#action-policy-rules)):

- `action_policy.evaluate` and `evaluate_all`, `action_audit.record(decisions, identity, audit_id, session_id)`, `action_config.load()` called in both lifespans, six `action:*` permissions (held by no built-in role), `GET /audit/actions`, the `actions_*` fields on `GET /stats`, the admin console **Actions** view, and the corpora under `tests/corpora/actions/`.
- Nothing in the request path calls any of it. `/v1` still refuses `tools` with `tools_not_supported`, and the `tool_calls` and `tool`-turn refusals say `(PRD-017)` already.

What PRD-017 must do:

- Lift the `tools_not_supported` refusal, call `evaluate_all` before the response leaves the harness, and pass the `audit_id` of the request's row into `record()`.
- Decide D1 (a response that mixes allowed and denied calls) and D4 (the wire shape of a denial); PRD-016 deliberately left both open.
- Reword the three `(PRD-017)` runtime strings only if their meaning changes.

Notes carried from the PRD-016 stories:

- **The admin console's Actions empty-state copy names PRD-017 and must be reworded when tool calls go live.** The console is gated by `ADMIN_TOKEN` only (no per-permission check), and a truncated target shows its full text through a `title` tooltip only, which a touch device cannot read.
- S9 (a directory search can return a secret file's contents) is a stated limitation, not a rule. S6 (MCP tool names arrive prefixed) means an agent deployment must map its MCP tools in `tools:`. `examples/action_policy.yaml` maps OpenCode and SQL tools only, so a Cline deployment writes its own `tools:` and `shell.allow`.
- `depends_on: [PRD-015, PRD-016]` is correct under the final numbering; `status` stays `draft` until this brief is promoted.

## Open decisions

| # | Question | Proposed default |
|---|---|---|
| D1 | One denied call among several in a response | Deny only that call; return the others plus an assistant note. Revisit if agents mis-handle partial responses. |
| D2 | Denial shape | Drop the denied `tool_call`, append assistant text with the reason; `finish_reason` stays `tool_calls` if any remain, else `stop`. |
| D3 | Models without tool support | Refuse at `/v1/models` level via a capability flag in the allowlist. |
| D4 | Dedup on `tool` turns | Excluded from the key's last-turn component; included in the prefix hash. |

## Evidence

- `content = data["choices"][0]["message"]["content"]` — the only field read upstream.
- PRD-015 D-scope: `tools` currently refused with 400.

## Success criteria

- OpenCode completes a small multi-file task through the harness.
- Cline completes the same task.
- A model-generated `DROP TABLE` is denied, audited, and the agent reports the reason instead of crashing.
- No tool-call argument is modified by any check.
- Running `npm test` twice in one session is not held as a duplicate.

## Risks

| Risk | Mitigation |
|---|---|
| Agents break on modified responses | E2E per client; D1/D2 revisited with data. |
| Buffered tool-call streaming confuses clients expecting incremental deltas | Emit spec-valid deltas in one burst; test per client. |
| Enabling this before 011–013/015 are solid | Hard dependency in this brief; feature flag `V1_TOOLS_ENABLED` default off. |

## Tentative story breakdown

1. `tools`/`tool_choice` forwarding and model capability flag
2. Upstream `tool_calls` parsing
3. Action policy evaluation per call
4. Denial wire shape
5. `tool` role through pipeline policies
6. Dedup key for tool turns
7. SSE deltas for tool calls
8. Audit of tool names and decisions
9. Feature flag
10. E2E: OpenCode
11. E2E: Cline
12. README: tool calling and client setup
