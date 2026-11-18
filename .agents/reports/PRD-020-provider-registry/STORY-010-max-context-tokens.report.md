---
story: STORY-010
prd: PRD-020
plan: .agents/plans/PRD-020-provider-registry/completed/STORY-010-max-context-tokens.plan.md
epic_branch: epic/PRD-020-provider-registry
commit: pending
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report - STORY-010: Refuse a conversation that exceeds a model's max_context_tokens

**Plan**: `.agents/plans/PRD-020-provider-registry/completed/STORY-010-max-context-tokens.plan.md`
**Epic Branch**: `epic/PRD-020-provider-registry`
**Commit**: `pending`

## Summary

Step 3 gains `_estimated_tokens_exceeded(messages, route, tools)`, called after `_context_limit_exceeded` with `or` (first breach wins). It reads `route.capabilities.max_context_tokens`, skips before any estimate when None (legacy mode included), else compares `estimate_tokens` (pre-redaction messages, tools counted, provider `estimate_chars_per_token`) with strict `>`. `ContextLimit` and the schema `limit` Literal gain `estimated_tokens`; the chat UI gets a `CONTEXT_LIMIT_UNITS` entry.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Schema literal + docstring | `app/models/schemas.py` | done |
| 2 | Widened `get_args` assertion (commented) + new test | `tests/test_schemas.py` | done |
| 3 | Chat UI unit | `chat_ui/chat_ui/copy.py` | done |
| 4 | Pipeline check | `app/services/query_pipeline.py` | done |
| 5 | Tests | `tests/test_query_pipeline_max_context_tokens.py` (10), `test_copy.py`, `test_chat_state.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests | 336 + 69 passed, chat_state `-k "context_limit or estimated"` 6 passed |
| E2E (/v1 400, chat bubble) | pass |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- Unit word is `"estimated length"`, not `"estimated tokens"`: `tests/test_copy.py::test_every_unit_obeys_the_context_limit_vocabulary_rules` forbids "token" in any unit. Existing test untouched.
- Risk 5 verified: the pipeline has no tools-capability gate, so a direct `run_conversation(tools=ToolParams(...))` works.
- Passthrough test runs as `admin` (passthrough only for wildcard roles, OD3).
- Chat-state test stubs the pipeline, like its neighbour; the real refusal path is covered by the pipeline and `/v1` tests.

## Acceptance Criteria

- [x] AC1 over maximum refused, nothing upstream (test_over_the_maximum_is_refused...)
- [x] AC2 equal proceeds (test_exactly_the_maximum_proceeds)
- [x] AC3 no maximum / legacy unchanged, estimate not computed, earlier limits win
- [x] AC4 /v1 400 + audit row (test_v1_answers_400..., test_the_audit_row_names...)
- [x] AC5 schema literal (test_schemas.py)
