# PRD-015-openai-compatible-endpoint: OpenAI-Compatible Endpoint (Text) — One Base URL, Every Verdict an Ordinary API Error — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-015-openai-compatible-endpoint` (base: `main`)
**Status**: active

## Progress

0/19 stories done — 0%

## Stories

All stories commit on the epic branch `epic/PRD-015-openai-compatible-endpoint`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Characterize /query's error bodies and the upstream request body before /v1 exists | technical | 🟡 in-progress | small | [plan](../../plans/PRD-015-openai-compatible-endpoint/STORY-001-query-error-body-characterization.plan.md) | — |
| STORY-002 | OpenRouter client: finish_reason, upstream_status and retryable, OPENROUTER_BASE_URL | feature | ⬜ todo | medium | — | — |
| STORY-003 | V1_ENABLED and V1_SSE_KEEPALIVE_SECONDS settings with startup validators | technical | ⬜ todo | small | — | — |
| STORY-004 | /v1 request, response, chunk and error schemas | feature | ⬜ todo | medium | — | — |
| STORY-005 | Request translation: messages, the developer role and edge structure checks | feature | ⬜ todo | medium | — | — |
| STORY-006 | Parameter classification: forward, ignore-and-record, reject; the explicit tools refusal | feature | ⬜ todo | medium | — | — |
| STORY-007 | audit_logs.ignored_params: column, writer, every pipeline arm and the /audit field | feature | ⬜ todo | medium | — | — |
| STORY-008 | code profile flags assistant turns; examples/patterns.yaml matches again | enhancement | ⬜ todo | small | — | — |
| STORY-009 | POST /v1/chat/completions: router, identity, device header and non-streaming success | feature | ⬜ todo | large | — | — |
| STORY-010 | Verdicts to OpenAI error objects; /v1-scoped 400/401/403 handlers; /query isolation | feature | ⬜ todo | large | — | — |
| STORY-011 | Upstream and internal fault mapping with deliberate retry semantics | feature | ⬜ todo | medium | — | — |
| STORY-012 | GET /v1/models and /v1/models/{id} from MODEL_ALLOWLIST | feature | ⬜ todo | small | — | — |
| STORY-013 | Buffered SSE: commit on upstream start, keep-alive, chunk sequence, include_usage, post-commit error | feature | ⬜ todo | large | — | — |
| STORY-014 | Scripted stub upstream for E2E runs | technical | ⬜ todo | medium | — | — |
| STORY-015 | E2E: OpenAI Python SDK, non-streaming, streaming, blocks and retries | technical | ⬜ todo | medium | — | — |
| STORY-016 | E2E: Aider applies a scripted edit through the harness | technical | ⬜ todo | medium | — | — |
| STORY-017 | E2E: Continue chat through the harness | technical | ⬜ todo | medium | — | — |
| STORY-018 | Caddy routes /v1/*; Docker smoke with keep-alive through Caddy | technical | ⬜ todo | medium | — | — |
| STORY-019 | Regression sweep, translation latency, README API reference and per-client setup, .env.example | technical | ⬜ todo | medium | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Dependencies

- STORY-002 blocked by STORY-001
- STORY-005 blocked by STORY-004
- STORY-006 blocked by STORY-001, STORY-004, STORY-005
- STORY-009 blocked by STORY-002, STORY-003, STORY-004, STORY-005, STORY-006, STORY-007
- STORY-010 blocked by STORY-001, STORY-004, STORY-009
- STORY-011 blocked by STORY-002, STORY-010
- STORY-012 blocked by STORY-004, STORY-009, STORY-010
- STORY-013 blocked by STORY-003, STORY-004, STORY-010, STORY-011
- STORY-014 blocked by STORY-002
- STORY-015 blocked by STORY-012, STORY-013, STORY-014
- STORY-016 blocked by STORY-013, STORY-014, STORY-015
- STORY-017 blocked by STORY-013, STORY-014, STORY-015
- STORY-018 blocked by STORY-013, STORY-014
- STORY-019 blocked by STORY-008, STORY-015, STORY-016, STORY-017, STORY-018
