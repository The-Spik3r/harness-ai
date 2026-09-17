---
target_prd: PRD-016
slug: tool-calling
title: Tool calling on the OpenAI-compatible endpoint
status: draft
prd:
depends_on: [PRD-014, PRD-015]
blocks: []
estimated_stories: 10-12
created: 2026-09-16
---

# Tool calling on the OpenAI-compatible endpoint

## Problem

After PRD-014, `/v1/chat/completions` refuses `tools`. OpenCode and Cline in agent mode are unusable without function calling: the model must be able to return `tool_calls`, and the client must be able to send `tool`-role results back. Today [openrouter_client.py](../app/services/openrouter_client.py) reads only `message.content` and treats anything else as an unexpected shape.

## Goal

OpenCode and Cline run real tasks through the harness, with every tool call passed through PRD-015's action policy before the client sees it.

## Proposed scope

**In**
- Forward `tools` and `tool_choice` to OpenRouter.
- Parse `tool_calls` (and `content: null`) from upstream.
- Every `tool_call` evaluated by PRD-015 before the response leaves the harness.
- Denial wire shape the agent can understand and recover from (PRD-015 D4).
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

## Open decisions

| # | Question | Proposed default |
|---|---|---|
| D1 | One denied call among several in a response | Deny only that call; return the others plus an assistant note. Revisit if agents mis-handle partial responses. |
| D2 | Denial shape | Drop the denied `tool_call`, append assistant text with the reason; `finish_reason` stays `tool_calls` if any remain, else `stop`. |
| D3 | Models without tool support | Refuse at `/v1/models` level via a capability flag in the allowlist. |
| D4 | Dedup on `tool` turns | Excluded from the key's last-turn component; included in the prefix hash. |

## Evidence

- `content = data["choices"][0]["message"]["content"]` — the only field read upstream.
- PRD-014 D-scope: `tools` currently refused with 400.

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
