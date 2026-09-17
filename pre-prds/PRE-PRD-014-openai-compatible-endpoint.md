---
target_prd: PRD-014
slug: openai-compatible-endpoint
title: OpenAI-compatible endpoint (text)
status: draft
prd:
depends_on: [PRD-011, PRD-012, PRD-013]
blocks: [PRD-016]
estimated_stories: 14-16
created: 2026-09-16
---

# OpenAI-compatible endpoint (text)

## Problem

`POST /query` is a project-specific shape; only the chat UI speaks it. Tools that speak OpenAI Chat Completions — OpenAI SDKs, Aider, Continue, OpenCode, Cline — cannot use the harness without a custom client. The README ([OpenAI-compatible endpoint](../README.md#openai-compatible-endpoint)) describes the intent:

```bash
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_API_KEY=<harness token — never the OpenRouter key>
```

This PRD is deliberately a **translation layer**: PRDs 009–013 make the pipeline safe for this traffic; this one only maps shapes.

## Goal

Point an OpenAI-compatible client at the harness by changing base URL and key, for text completions, with every harness verdict surfaced as an ordinary API error the client displays instead of retrying.

## Proposed scope

**In**
- `POST /v1/chat/completions` with request/response schemas following the Chat Completions standard.
- Identity from `Authorization: Bearer` (already how [auth.py](../app/middleware/auth.py) works); `user` field and a header mapped to `device`.
- Success translation: `choices[0].message`, `usage`, `model`, `id`, `created`, `finish_reason`.
- Block translation: duplicate / suspicious / forbidden / budget → OpenAI error object with a harness-specific `code`, HTTP 400 or 403.
- Upstream errors → 502 with error object; decide retryability deliberately.
- `stream: true` as buffered SSE: full response, checks pass, then emitted as chunks + `[DONE]`.
- `GET /v1/models` from `MODEL_ALLOWLIST` (filtered by the caller's role).
- `tools` / `tool_choice` present → explicit 400 "not supported yet", never silently dropped.
- Unsupported parameters: allowlist, ignore-with-warning or reject (D3).
- `code` profile for PRD-011/012 policies on this ingress.
- E2E validation with real clients as stories, not a checklist.

**Out**
- Tool calling (PRD-016).
- Real token streaming.
- `/v1/completions` (legacy), embeddings, images, audio, Responses API.
- BYOK on this ingress.

## Open decisions

| # | Question | Proposed default |
|---|---|---|
| D1 | Device: `user` field or header? | Header `X-Harness-Device`; `user` field ignored for identity, recorded only. |
| D2 | Block status code | 400 for content blocks (duplicate, suspicious), 403 for policy/budget. Never 429/5xx. |
| D3 | Unknown parameters | Ignore and record in audit; reject only ones that change semantics (`n>1`, `logprobs`). |
| D4 | Model names | Exact allowlist match; no aliasing in this PRD. |
| D5 | Does a duplicate-blocked request return the previous answer? | No — error, as `/query` does. |
| D6 | SSE chunking | Single content chunk + finish chunk; configurable chunk size later. |

## Evidence

- `HTTPBearer` already parses the header OpenAI SDKs send.
- OpenRouter's upstream API is itself Chat Completions shaped, so success mapping is near-identity.
- `QueryBlocked*Response` models give the reason strings the error object carries.

## Success criteria

- OpenAI Python SDK: non-streaming and streaming calls succeed; a blocked prompt raises `BadRequestError` with the harness reason.
- Aider completes an edit on a sample repo through the harness.
- Continue chat works against the harness.
- No client enters a retry loop on any block.
- Every `/v1` request produces exactly one audit row with `ingress='v1'`.

## Risks

| Risk | Mitigation |
|---|---|
| Clients depend on real streaming latency (timeouts on first byte) | Keep-alive SSE comment lines while buffering. |
| Standard drift (new required fields) | Pin tested client versions in e2e stories. |
| Starting this before 011–013 ("the easy part") | Dependency is explicit in this brief; see track README shortcut and its debt. |

## Tentative story breakdown

1. Request/response schemas
2. Router and identity/device mapping
3. Message translation into the PRD-010 model
4. Success translation
5. Block → error translation
6. Upstream error mapping and retry semantics
7. `GET /v1/models`
8. Explicit refusal of `tools`
9. Parameter allowlist
10. Buffered SSE with keep-alive
11. `code` profile wiring
12. E2E: OpenAI Python SDK
13. E2E: Aider
14. E2E: Continue
15. Docker/Caddy smoke
16. README: section moves from roadmap to API reference, per-client setup
