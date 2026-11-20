# PRD-022-provider-fallback-and-native-adapters: Provider Resilience — Native Adapters, Fallback Chains and a Provider Circuit Breaker — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-022-provider-fallback-and-native-adapters` (base: `main`)
**Status**: active

## Progress

0/18 stories done — 0%

## Stories

All stories commit on the epic branch `epic/PRD-022-provider-fallback-and-native-adapters`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Spike — confirm built PRD-018/020/021 seams, pin the anthropic SDK, check redirects and the Messages wire format | spike | 🟡 in-progress | medium | [plan](../../plans/PRD-022-provider-fallback-and-native-adapters/STORY-001-foundations-spike.plan.md) | — |
| STORY-002 | UpstreamError kind/provider/retry_after + fallback_eligible, ChainExhausted, cache fields on results | feature | ⬜ todo | medium | — | — |
| STORY-003 | PRD-022 audit columns, request_id on every row, attempt=1 on step-7 rows, /audit filter | feature | ⬜ todo | medium | — | — |
| STORY-004 | Registry accepts type anthropic and the PRD-022 catalogue fields; adapter dispatch by provider type | feature | ⬜ todo | medium | — | — |
| STORY-005 | AnthropicAdapter.complete() — request/response mapping, SDK error mapping, cache tokens | feature | ⬜ todo | large | — | — |
| STORY-006 | Stub upstream — Anthropic Messages mode (JSON + SSE) and scripted faults | technical | ⬜ todo | medium | — | — |
| STORY-007 | AnthropicAdapter.stream() — events, buffered tool input, ReasoningDelta, collect property | feature | ⬜ todo | medium | — | — |
| STORY-008 | Anthropic as a primary through the pipeline — dropped params, cache tokens on the row, /v1 tool loop | feature | ⬜ todo | medium | — | — |
| STORY-009 | PROVIDER_CHAINS_FILE loader, settings, and startup validation (trust, capability, catalogue) | feature | ⬜ todo | medium | — | — |
| STORY-010 | health.py — one CircuitBreaker per provider, fault recording rules, providers_status() | feature | ⬜ todo | medium | — | — |
| STORY-011 | chain.py — per-request eligibility, per-route redaction hook, run() with per-attempt callbacks, ChainExhausted | feature | ⬜ todo | large | — | — |
| STORY-012 | Pipeline steps 6+7 through chain.run() for buffered calls — per-attempt rows, exhaustion row, admit/charge once | feature | ⬜ todo | large | — | — |
| STORY-013 | /v1 surfaces — answering model, harness.provider/attempts, X-Harness-Provider, exhaustion with retry-after | feature | ⬜ todo | medium | — | — |
| STORY-014 | Real-time streamed requests through the chain — fall back before release, never after | feature | ⬜ todo | large | — | — |
| STORY-015 | GET /providers/status and the /stats fallback figures | feature | ⬜ todo | medium | — | — |
| STORY-016 | Admin console — Providers panel and attempt column on the Register | feature | ⬜ todo | medium | — | — |
| STORY-017 | E2E — OpenRouter killed, Anthropic answers a tools request, breaker opens, status reports it | technical | ⬜ todo | medium | — | — |
| STORY-018 | Docs, example chains/providers files, latency check, PRD done | technical | ⬜ todo | small | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Dependencies

- STORY-002 blocked by STORY-001
- STORY-003 blocked by STORY-001
- STORY-004 blocked by STORY-001
- STORY-005 blocked by STORY-002, STORY-004
- STORY-006 blocked by STORY-001
- STORY-007 blocked by STORY-005, STORY-006
- STORY-008 blocked by STORY-003, STORY-007
- STORY-009 blocked by STORY-004
- STORY-010 blocked by STORY-002
- STORY-011 blocked by STORY-009, STORY-010
- STORY-012 blocked by STORY-003, STORY-011
- STORY-013 blocked by STORY-012
- STORY-014 blocked by STORY-012, STORY-013
- STORY-015 blocked by STORY-010, STORY-012
- STORY-016 blocked by STORY-015
- STORY-017 blocked by STORY-008, STORY-013, STORY-014, STORY-015
- STORY-018 blocked by STORY-016, STORY-017
