# PRD-020-provider-registry: Provider Registry — OpenRouter Stops Being the Core; Local Models and Any OpenAI-Compatible Provider — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-020-provider-registry` (base: `main`)
**Status**: active

## Progress

11/15 stories done — 73%

## Stories

All stories commit on the epic branch `epic/PRD-020-provider-registry`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Record the legacy byte-identical fixtures before any refactor | technical | ✅ done | medium | [plan](../../plans/PRD-020-provider-registry/completed/STORY-001-legacy-byte-identical-fixtures.plan.md) | `130bbee` |
| STORY-002 | PROVIDERS_FILE setting and the conditional OPENROUTER_API_KEY requirement | feature | ✅ done | small | [plan](../../plans/PRD-020-provider-registry/completed/STORY-002-providers-file-settings.plan.md) | `6586c45` |
| STORY-003 | Provider registry loader, validation and the legacy implicit provider | feature | ✅ done | large | [plan](../../plans/PRD-020-provider-registry/completed/STORY-003-registry-loader-and-validation.plan.md) | `5dc69fe` |
| STORY-004 | Route resolution, visible models and authorize_route | feature | ✅ done | medium | [plan](../../plans/PRD-020-provider-registry/completed/STORY-004-route-resolution-and-authorize-route.plan.md) | `acc101e` |
| STORY-005 | Upstream package, OpenAI-compatible adapter and call_upstream | technical | ✅ done | large | [plan](../../plans/PRD-020-provider-registry/completed/STORY-005-upstream-package-and-adapter.plan.md) | `6015bab` |
| STORY-006 | Five provider columns on the audit table and log_query | feature | ✅ done | medium | [plan](../../plans/PRD-020-provider-registry/completed/STORY-006-audit-provider-columns.plan.md) | `581f7af` |
| STORY-007 | Pipeline step 2 routing, BYOK per provider and per-row provider audit | feature | ✅ done | large | [plan](../../plans/PRD-020-provider-registry/completed/STORY-007-pipeline-routing-byok-audit.plan.md) | `d3b6ec6` |
| STORY-008 | PII input relaxation for an internal, relaxed provider | feature | ✅ done | medium | [plan](../../plans/PRD-020-provider-registry/completed/STORY-008-pii-input-relaxation.plan.md) | `8ab795e` |
| STORY-009 | Estimate usage when a provider reports none | feature | ✅ done | medium | [plan](../../plans/PRD-020-provider-registry/completed/STORY-009-usage-estimate.plan.md) | `3b12ec1` |
| STORY-010 | Refuse a conversation that exceeds a model's max_context_tokens | feature | ✅ done | small | [plan](../../plans/PRD-020-provider-registry/completed/STORY-010-max-context-tokens.plan.md) | `c0ebdd2` |
| STORY-011 | /v1 tool capability from the registry and per-role GET /v1/models | feature | ✅ done | medium | [plan](../../plans/PRD-020-provider-registry/completed/STORY-011-v1-capabilities-and-models.plan.md) | `593cfc4` |
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
