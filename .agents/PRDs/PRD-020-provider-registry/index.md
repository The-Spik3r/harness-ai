# PRD-020-provider-registry: Provider Registry — OpenRouter Stops Being the Core; Local Models and Any OpenAI-Compatible Provider — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-020-provider-registry` (base: `main`)
**Status**: active

## Progress

0/15 stories done — 0%

## Stories

All stories commit on the epic branch `epic/PRD-020-provider-registry`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Record the legacy byte-identical fixtures before any refactor | technical | ⬜ todo | medium | — | — |
| STORY-002 | PROVIDERS_FILE setting and the conditional OPENROUTER_API_KEY requirement | feature | ⬜ todo | small | — | — |
| STORY-003 | Provider registry loader, validation and the legacy implicit provider | feature | ⬜ todo | large | — | — |
| STORY-004 | Route resolution, visible models and authorize_route | feature | ⬜ todo | medium | — | — |
| STORY-005 | Upstream package, OpenAI-compatible adapter and call_upstream | technical | ⬜ todo | large | — | — |
| STORY-006 | Five provider columns on the audit table and log_query | feature | ⬜ todo | medium | — | — |
| STORY-007 | Pipeline step 2 routing, BYOK per provider and per-row provider audit | feature | ⬜ todo | large | — | — |
| STORY-008 | PII input relaxation for an internal, relaxed provider | feature | ⬜ todo | medium | — | — |
| STORY-009 | Estimate usage when a provider reports none | feature | ⬜ todo | medium | — | — |
| STORY-010 | Refuse a conversation that exceeds a model's max_context_tokens | feature | ⬜ todo | small | — | — |
| STORY-011 | /v1 tool capability from the registry and per-role GET /v1/models | feature | ⬜ todo | medium | — | — |
| STORY-012 | /query default model, chat UI model selector and Register provider column | feature | ⬜ todo | medium | — | — |
| STORY-013 | Adapter stream() with normalized events and pure collect() | feature | ⬜ todo | large | — | — |
| STORY-014 | Opt-in end-to-end run against a real local OpenAI-compatible server | technical | ⬜ todo | medium | — | — |
| STORY-015 | Providers documentation, example registry, .env.example and README | technical | ⬜ todo | medium | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Dependencies

- STORY-003 blocked by STORY-002
- STORY-004 blocked by STORY-003
- STORY-005 blocked by STORY-001, STORY-003
- STORY-007 blocked by STORY-004, STORY-005, STORY-006
- STORY-008 blocked by STORY-007
- STORY-009 blocked by STORY-007, STORY-005
- STORY-010 blocked by STORY-007
- STORY-011 blocked by STORY-007, STORY-004
- STORY-012 blocked by STORY-007, STORY-004
- STORY-013 blocked by STORY-005, STORY-009
- STORY-014 blocked by STORY-008, STORY-009, STORY-011, STORY-013
- STORY-015 blocked by STORY-010, STORY-012, STORY-014
