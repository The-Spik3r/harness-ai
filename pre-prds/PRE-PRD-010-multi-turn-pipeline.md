---
target_prd: PRD-010
slug: multi-turn-pipeline
title: Multi-turn pipeline
status: draft
prd:
depends_on: [PRD-009]
blocks: [PRD-011, PRD-012, PRD-013, PRD-014]
estimated_stories: 16-20
created: 2026-09-16
---

# Multi-turn pipeline

## Problem

The pipeline speaks exactly one user turn.

- `run_query(identity, prompt: str, …)` ([query_pipeline.py](../app/services/query_pipeline.py)) takes a string.
- `call_openrouter` ([openrouter_client.py:41-44](../app/services/openrouter_client.py)) always sends `[{"role": "user", "content": prompt}]` — no system prompt, no history, no generation parameters.
- It reads only `choices[0].message.content`; a `null` content (tool call) raises `OpenRouterError`.
- `_TIMEOUT_SECONDS = 30.0` — too short for large contexts.
- Everything is synchronous (`def` routes, `httpx.Client`). Long upstream calls hold Starlette threadpool workers (~40), so a few slow agent requests stall `/query` and the chat UI.

A chat session today is a saved transcript the model never sees (README, *Multi-turn context*). Every later PRD in this track needs a conversation, not a string.

## Goal

The pipeline takes a normalized list of messages, sends it to OpenRouter with allowed parameters, and does not block the process while it waits. `/query` becomes the one-message case and behaves exactly as before. The chat UI sends session history.

## Proposed scope

**In**
- Internal message model: `role ∈ {system, user, assistant, tool}`, `content: str`, normalization from OpenAI shapes (`content` as list of parts, `null`).
- `run_query` accepts messages; `prompt` path kept as a thin adapter.
- OpenRouter client sends `messages` plus an allowlist of parameters (`temperature`, `max_tokens`, `top_p`, `stop`).
- Configurable timeout (`OPENROUTER_TIMEOUT_SECONDS`).
- Async client or a dedicated executor so upstream waits do not starve the default threadpool.
- Context limits: max messages / max characters, with an explicit refusal (not silent truncation) or a documented truncation policy.
- Duplicate key from PRD-009 fed with the real conversation.
- Checks run against the conversation under a **provisional** role policy (patterns + PII on the last `user` turn only) until PRD-011/012 replace it.
- ChatState sends the session's history; `CHAT_HISTORY_ENABLED=false` keeps single-turn behaviour.

**Out**
- Tool calls, `tools` parameter (PRD-016).
- Streaming (PRD-014).
- Final inspection policy per role (PRD-011, PRD-012).

## Open decisions

| # | Question | Proposed default |
|---|---|---|
| D1 | Async rewrite of the pipeline, or sync pipeline in a dedicated executor? | Dedicated executor first — smaller blast radius; async client inside `call_openrouter` only. |
| D2 | Over-long context: refuse or truncate? | Refuse with an explicit reason in `/query`; truncation belongs to the client. |
| D3 | How many history turns does the chat UI send? | All turns of the session up to the limit in D2. |
| D4 | Are blocked turns (duplicate/suspicious/forbidden bubbles) part of the history sent to the model? | No — only successful user/assistant pairs. |
| D5 | Is the redacted or the original text sent as history? | Redacted, always — the model never sees what it did not see the first time. |

## Evidence

- `QueryRequest.prompt: str`, `model: str = "gpt-4"` in [schemas.py](../app/models/schemas.py).
- `ChatState` wires to `run_query` (PRD-004 STORY-001 offloads it to a thread).
- `chat_messages` table from PRD-008 already stores the transcript.

## Success criteria

- A chat session is a conversation: the model can answer "what did I just ask?".
- `/query` single-turn outcomes identical to before (six-outcome regression).
- Ten concurrent 60-second upstream calls do not block `/health` or a `/query` call.
- "yes" sent twice in one session, and in two sessions, is not held as a duplicate.

## Risks

| Risk | Mitigation |
|---|---|
| Largest refactor of the pipeline since PRD-002 | Adapter keeps `/query` signature; regression suite before touching internals. |
| Redacted history makes answers worse | Documented as intended; revisit reversible placeholders in PRD-012. |
| Token cost jumps with history | Limits in D2 now; budgets in PRD-013. |

## Tentative story breakdown

1. Message model and role enum
2. Content normalization (list parts, `null`)
3. Settings: timeout, max messages, max characters
4. OpenRouter client sends `messages` + parameter allowlist
5. Upstream call off the default threadpool
6. `run_query` over messages; `prompt` adapter
7. `/query` routes through the adapter unchanged
8. Duplicate key from PRD-009 on the real conversation
9. Provisional check policy (last user turn)
10. Context-limit refusal
11. History assembly from `chat_messages` (successful pairs, redacted)
12. ChatState sends history; flag-off path unchanged
13. Client tests (payload shape, parameters, timeout)
14. Pipeline tests over multi-turn input
15. Concurrency test (slow upstream does not stall the process)
16. Six-outcome and chat UI regression
17. Two-instance smoke with history
18. README: Multi-turn context moves from roadmap to shipped
