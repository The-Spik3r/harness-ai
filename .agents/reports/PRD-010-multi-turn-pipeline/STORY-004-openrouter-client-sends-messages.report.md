---
story: STORY-004
prd: PRD-010
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-004-openrouter-client-sends-messages.plan.md
epic_branch: epic/PRD-010-multi-turn-pipeline
commit: 65451c1
status: COMPLETE
completed: 2026-09-17
---

# Implementation Report — STORY-004: call_openrouter takes a list of Messages; the pipeline passes one user message

**Plan**: `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-004-openrouter-client-sends-messages.plan.md`
**Epic Branch**: `epic/PRD-010-multi-turn-pipeline`
**Commit**: `65451c1`

## Summary

`call_openrouter` now takes `messages: Sequence[Message]` instead of a bare `prompt: str`, building the OpenRouter payload as `[{"role": m.role, "content": m.content} for m in messages]`. An empty `messages` list raises `OpenRouterError` before any HTTP call. `run_query` in `query_pipeline.py` adapts by passing `[Message("user", redacted_prompt)]`, so the upstream JSON body for a single-turn request is unchanged. Of the roughly 90 injected `call_openrouter` test stubs across ~17 files, only the handful that actually read the prompt's string value were updated to read `messages[-1].content`, each with a comment citing this story; every other stub ignores its first positional argument and needed no change.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | New signature + payload construction from `messages`; empty-list guard | `app/services/openrouter_client.py` | ✅ |
| 2 | Call site passes `[Message("user", redacted_prompt)]` | `app/services/query_pipeline.py` | ✅ |
| 3 | Adapted 13 direct `call_openrouter("hello", …)` calls; added AC3 (four-message ordering) and AC4 (empty-list raises) tests | `tests/test_openrouter_client.py` | ✅ |
| 4 | Adapted `/query`-upstream characterization test's recording stub + assertion | `tests/test_query_outcomes_regression.py` | ✅ |
| 5 | Fixed the three stubs reading the prompt's string value | `tests/test_pii_redaction_integration.py`, `tests/test_pii_dedup_isolation.py`, `tests/test_query_router.py` (two sites) | ✅ |
| 6 | Full suite validated green | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`openrouter_client`, `query_pipeline`) | ✅ |
| `tests/test_openrouter_client.py` | ✅ (14 passed) |
| `tests/test_query_outcomes_regression.py` | ✅ (8 passed) |
| `tests/test_pii_redaction_integration.py` + `test_pii_dedup_isolation.py` + `test_query_router.py` | ✅ (74 passed) |
| `tests/test_chat_state.py` + `test_query_pipeline_session_passthrough.py` (AC5 named examples) | ✅ (153 passed, no assertion changes) |
| Full suite | ✅ (2036 passed, 25 skipped, 0 failed, 1646s) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/openrouter_client.py` | UPDATE | +9/-4 |
| `app/services/query_pipeline.py` | UPDATE | +2/-1 |
| `tests/test_openrouter_client.py` | UPDATE | +48/-14 |
| `tests/test_query_outcomes_regression.py` | UPDATE | +9/-4 |
| `tests/test_pii_redaction_integration.py` | UPDATE | +1/-1 |
| `tests/test_pii_dedup_isolation.py` | UPDATE | +1/-1 |
| `tests/test_query_router.py` | UPDATE | +2/-2 |

## Deviations from Plan

None. Implementation matched the plan exactly, including the two new client tests and the exact set of stub sites identified as reading the prompt's value.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_openrouter_client.py` | `test_multi_message_conversation_preserves_order_roles_and_content` (AC3), `test_empty_messages_raises_before_any_http_call` (AC4) |

## Acceptance Criteria

- [x] `call_openrouter` signature is `call_openrouter(messages: Sequence[Message], model: str = _DEFAULT_MODEL, api_key: Optional[str] = None, client: Optional[httpx.Client] = None)`; payload is `{"model": model, "messages": [{"role": m.role, "content": m.content} for m in messages]}`
- [x] `run_query` passes `[Message("user", redacted_prompt)]`; STORY-003's characterization tests pass with adapted inputs, no change to the payload assertion
- [x] A four-message `[system, user, assistant, user]` list preserves order, roles and content exactly in `json["messages"]`
- [x] An empty `messages` list raises `OpenRouterError` before any HTTP call
- [x] Every test injecting a fake `call_openrouter` is green; only value-reading stubs updated, each with the STORY-004 comment; no outcome assertion changed
