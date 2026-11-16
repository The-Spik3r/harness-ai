# PRD-017-tool-calling: Tool Calling on the OpenAI-Compatible Endpoint — Every Tool Call Decided by the Action Policy Before the Client Sees It — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-017-tool-calling` (base: `main`)
**Status**: active

## Progress

6/18 stories done — 33%

## Stories

All stories commit on the epic branch `epic/PRD-017-tool-calling`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Client survey: OpenCode 2.0.10 and Cline request/response shapes; PRD-016 mappings re-verified | spike | ✅ done | medium | [plan](../../plans/PRD-017-tool-calling/completed/STORY-001-client-survey.plan.md) | `5127071` |
| STORY-002 | V1_TOOLS_ENABLED and V1_TOOL_MODELS settings with startup validation | technical | ✅ done | small | [plan](../../plans/PRD-017-tool-calling/completed/STORY-002-tool-settings.plan.md) | `afc8079` |
| STORY-003 | ToolCallSpec, Message.tool_calls / tool_call_id, and the normalizer | feature | ✅ done | medium | [plan](../../plans/PRD-017-tool-calling/completed/STORY-003-message-model-tool-fields.plan.md) | `a68762c` |
| STORY-004 | Upstream client: ToolParams, tool message serialization, tool_calls parsing | feature | ✅ done | medium | [plan](../../plans/PRD-017-tool-calling/completed/STORY-004-upstream-tool-calls.plan.md) | `1f81ec5` |
| STORY-005 | Step 0 accepts tool turns under the D6 shape rules; the audit prompt is the final turn | feature | ✅ done | medium | [plan](../../plans/PRD-017-tool-calling/completed/STORY-005-step-zero-and-prompt-anchor.plan.md) | `a86a71c` |
| STORY-006 | dedup_key over tool turns: never the anchor, in the prefix, tool-free keys unchanged | feature | ✅ done | medium | [plan](../../plans/PRD-017-tool-calling/completed/STORY-006-dedup-key-tool-turns.plan.md) | `16fd154` |
| STORY-007 | Steps 3, 5, 6 on tool content; tool-call arguments never inspected or redacted | feature | 🟡 in-progress | medium | [plan](../../plans/PRD-017-tool-calling/STORY-007-policies-on-tool-content.plan.md) | — |
| STORY-008 | /v1 request translation under V1_TOOLS_ENABLED: tools, tool turns, shape rules, V1_TOOL_MODELS; passed through to step 7 | feature | ⬜ todo | large | — | — |
| STORY-009 | tool_release.apply_decisions: release allowed calls, drop denied ones with a note, finish_reason | feature | ⬜ todo | small | — | — |
| STORY-010 | Step 7c: evaluate every call, release, record() with audit_id, fail closed, has_tool_calls | feature | ⬜ todo | large | — | — |
| STORY-011 | Completion shape: tool_calls, content null, finish_reason tool_calls, harness.actions | feature | ⬜ todo | medium | — | — |
| STORY-012 | Buffered SSE tool_calls deltas in one burst | feature | ⬜ todo | medium | — | — |
| STORY-013 | GET /audit/actions?audit_id= and the Actions view's empty-state copy | enhancement | ⬜ todo | small | — | — |
| STORY-014 | Stub upstream: scripted tool_calls replies, rules matching on any last turn | technical | ⬜ todo | small | — | — |
| STORY-015 | In-process success-criteria suite for tool calling; step 7c latency measured | technical | ⬜ todo | medium | — | — |
| STORY-016 | E2E: OpenCode completes a scripted multi-file task; a scripted DROP TABLE is denied and reported | technical | ⬜ todo | large | — | — |
| STORY-017 | E2E: Cline completes the same task through the harness | technical | ⬜ todo | large | — | — |
| STORY-018 | README, docs/features.md, docs/roadmap.md, .env.example; brief promotion verified | technical | ⬜ todo | small | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Dependencies

- STORY-004 blocked by STORY-003
- STORY-005 blocked by STORY-003
- STORY-006 blocked by STORY-005
- STORY-007 blocked by STORY-005
- STORY-008 blocked by STORY-001, STORY-002, STORY-004, STORY-005, STORY-006, STORY-007
- STORY-009 blocked by STORY-003
- STORY-010 blocked by STORY-001, STORY-002, STORY-008, STORY-009
- STORY-011 blocked by STORY-010
- STORY-012 blocked by STORY-011
- STORY-013 blocked by STORY-010
- STORY-014 blocked by STORY-004
- STORY-015 blocked by STORY-012, STORY-013
- STORY-016 blocked by STORY-001, STORY-014, STORY-015
- STORY-017 blocked by STORY-001, STORY-014, STORY-016
- STORY-018 blocked by STORY-013, STORY-015, STORY-016, STORY-017
