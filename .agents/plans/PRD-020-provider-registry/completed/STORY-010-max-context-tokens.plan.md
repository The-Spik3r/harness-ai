---
story: STORY-010
prd: PRD-020
slug: max-context-tokens
title: Refuse a conversation that exceeds a model's max_context_tokens
type: NEW_CAPABILITY
complexity: small
epic_branch: epic/PRD-020-provider-registry
created: 2026-11-18
---

# Plan: Refuse a conversation that exceeds a model's max_context_tokens

## Summary

Step 3 gains a third check, after `messages` and `characters`: when the route's model declares `max_context_tokens`, the D9 estimate of the pre-redaction conversation (`usage_estimate.estimate_tokens`, received = 0, the request's tools counted) is compared with it, strict `>`. A breach reuses the existing step-3 arm unchanged (audit row, `QueryBlockedContextLimitResponse`, `/v1` `context_length_exceeded`). The `limit` Literal widens by `estimated_tokens`; the chat UI needs one new copy entry (it indexes `CONTEXT_LIMIT_UNITS[result.limit]`, so without it a refusal would `KeyError`).

- Story: `.agents/stories/PRD-020-provider-registry/STORY-010-max-context-tokens.md`
- PRD sections used: Section 4 step 3 (PRD line 149), 6.1, 7 F4, 10 (line 450), 9.2 T10, D9
- Systems affected: `query_pipeline` step 3, `schemas.py`, chat UI copy, tests

## Design Decisions

- **Separate function, existing one untouched.** Add `_estimated_tokens_exceeded(messages, route, tools) -> Optional[Tuple[ContextLimit, int, int]]` next to `_context_limit_exceeded`; do NOT change that signature: `tests/test_query_pipeline_tools.py:324,327,336` and `tests/test_chat_history.py:681` call `_context_limit_exceeded(messages)` with one argument. Step 3 then reads: `exceeded = _context_limit_exceeded(messages) or _estimated_tokens_exceeded(messages, route, tools)`. Order is messages -> characters -> estimated_tokens, first breach wins; the `or` short-circuits, so the estimate is not computed after an earlier breach.
- **Capability source.** Use `route.capabilities.max_context_tokens` (`provider_registry.py:140-148`), not `route.model.capabilities`: `route.model` is `None` for a passthrough route (`provider_registry.py:665`), whose `passthrough_capabilities` may set the value. For a catalogued route `route.capabilities` is the entry's capabilities (`:662`), so it is the same value the brief names. Minor reading of the brief, same semantics, no `None` deref. Legacy mode: `Capabilities()` default `max_context_tokens=None` (`:94`), so the check is skipped and nothing changes (D1).
- **Skip entirely when None**: `limit = route.capabilities.max_context_tokens; if limit is None: return None` before any estimate call.
- **Estimate**: `estimate_tokens(messages, ("", ()), route.provider.estimate_chars_per_token, tools=tools.tools if tools is not None else None)` (`usage_estimate.py:24-45`). Conversion: `tools` at step 3 is the pipeline's `Optional[ToolParams]` (`query_pipeline.py:370`, `params.py:81`); `estimate_tokens` wants the bare `Sequence[Mapping]`, i.e. `tools.tools`, exactly as the adapter does at `upstream/openai_compatible.py:140-145`. An empty tools list counts (`[]` is not None). Pre-redaction `messages` (step 3 runs before step 6); no char-count formula duplicated.
- **Strict `>`**: `actual > limit` refuses, `==` proceeds. `maximum` = limit, `actual` = estimate.
- **Return type**: widen `ContextLimit` (`query_pipeline.py:60`) to `Literal["messages", "characters", "estimated_tokens"]`.
- **No other arm changes**: error text `context limit: estimated_tokens <a> > <m>` falls out of `query_pipeline.py:574`; `/v1` maps via `_VERDICTS` (`v1_translate.py:688-691`), and `_verdict_code` (`:703-707`) only special-cases `redaction_characters`, so it stays `context_length_exceeded`. No `v1_translate.py` change.
- **Chat UI**: add `"estimated_tokens": "estimated tokens"` to `CONTEXT_LIMIT_UNITS` (`chat_ui/chat_ui/copy.py:162-166`), reading "estimated tokens 31000 of 8192" via `CONTEXT_LIMIT_DETAIL_TEMPLATE` (`:155`). Plain reader words, no identifier, like the `redaction_characters` entry. `state.py:1363` indexes, so this entry is required, not optional.

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| frontend-design (`.agents/skills/frontend-design/SKILL.md`) | Task 3 adds one user-facing string to the chat UI copy; its copy guidance (plain words, no identifiers) shaped the unit wording. No visual change, no agent-browser flow. | Task 3 |

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Step-3 shape | `query_pipeline.py:123-161` | docstring citing PRD ids, tuple return `(limit, maximum, actual)` |
| Estimate call | `upstream/openai_compatible.py:140-146` | `tools=tools.tools if tools is not None else None` |
| Schema widen | `schemas.py:150`, test `tests/test_schemas.py:408-429` | additive Literal; docstring paragraph like `:139-145` |
| Copy unit | `chat_ui/chat_ui/copy.py:156-166`, `tests/test_copy.py:1278-1285` | one entry, test appended (`test_copy.py` is in the `test_untouched_app.py:86` census: append, never edit above) |
| File-mode tests | `tests/test_query_pipeline_usage_estimate.py:23-46,73-77` | `provider_file` fixture, `_shipped_settings` autouse import, `run_conversation` direct call |
| /v1 error test | `tests/test_v1_errors.py:76-82,185-207` | `client.post("/v1/chat/completions")`, `_error(...)`, `_assert_response`, stub `app.routers.v1.call_openrouter` |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/query_pipeline.py` | UPDATE | `ContextLimit` literal, new `_estimated_tokens_exceeded`, step-3 call (`:565`), import `estimate_tokens` |
| `app/models/schemas.py` | UPDATE | `limit` Literal (`:150`) + docstring paragraph (`:123-146`) |
| `chat_ui/chat_ui/copy.py` | UPDATE | `CONTEXT_LIMIT_UNITS["estimated_tokens"]` (`:162`), comment |
| `tests/test_query_pipeline_max_context_tokens.py` | CREATE | pipeline, `/v1`, audit tests |
| `tests/test_schemas.py` | UPDATE | fix the `get_args` assertion at `:425-429` (it asserts a 3-tuple and will fail) and append a test for the new value |
| `tests/test_copy.py` | UPDATE | append a unit-word test |
| `tests/test_chat_state.py` | UPDATE | append a bubble test modelled on `:3369-3401` |

## Tasks

### Task 1: Schema literal
- **File**: `app/models/schemas.py`
- **Implement**: `limit: Literal["messages", "characters", "redaction_characters", "estimated_tokens"]`; add a docstring paragraph: `estimated_tokens` is PRD-020 D9's maximum, a model's `max_context_tokens`, reported from step 3 after the two character limits; `actual` is the D8 estimate, not a measured count.
- **Mirror**: `schemas.py:139-145`
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: Existing schema literal assertion
- **File**: `tests/test_schemas.py:425-429`
- **Implement**: the `get_args(...) == ("messages","characters","redaction_characters")` assertion fails once widened. Edit it to the 4-tuple with a comment `# PRD-020 D9 (STORY-010): estimated_tokens added; the first three unchanged` (a modified pre-existing assertion, so the citation is required). Append `test_query_blocked_context_limit_response_accepts_estimated_tokens` (model_dump body field for field, like `:412-424`). No rename, so nothing to register in `_DELIBERATELY_SUPERSEDED_TESTS`.

### Task 3: Chat UI copy
- **File**: `chat_ui/chat_ui/copy.py:162-166`
- **Implement**: add `"estimated_tokens": "estimated tokens"` and extend the preceding comment (`:156-161`) with one sentence (PRD-020 D9: an estimate, hence the word). Existing bubble strings stay byte-identical.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_chat_ui_startup_guard.py tests/test_context_limit_bubble.py`
- `tests/test_context_limit_bubble.py` is source-text based (arm order, imports, tokens, kind string); it does not enumerate `limit` values, so it tolerates the new one. The real UI hazard is the `KeyError` above.

### Task 4: Pipeline check
- **File**: `app/services/query_pipeline.py`
- **Implement**: (a) `ContextLimit` at `:60`; (b) `_estimated_tokens_exceeded` after `_context_limit_exceeded` (`:161`): None if `route.capabilities.max_context_tokens is None`; else compute the estimate as in Design and return `("estimated_tokens", limit, estimate)` when `estimate > limit`; docstring: PRD-020 D9, T10 mitigation (not proof of the server's real window), pre-redaction messages, strict `>`. (c) at `:565` replace the single call with the `or` form; extend the step-3 comment (`:545-564`) with one line on D9. `tools` and `route` are already in scope (`:370`, `:426`). (d) import `estimate_tokens` from `app.services.usage_estimate` (pure module; follow the existing import block).
- **Mirror**: `query_pipeline.py:123-161`
- **Validate**: Task 5 tests, plus `tests/test_query_pipeline_tools.py tests/test_chat_history.py`.

### Task 5: Tests, `tests/test_query_pipeline_max_context_tokens.py`
Use `provider_file` with a YAML like `test_query_pipeline_usage_estimate.py:32-46` plus `estimate_chars_per_token: 1` (valid 0..8, `provider_registry.py:408-409`) so the estimate equals the character count, a catalogued model with `capabilities: {max_context_tokens: N}`, and a second model without it. Monkeypatch `query_pipeline.call_openrouter` with a recording stub `(messages, model, api_key, **kw)` (D12) and assert `calls == []` on refusals. Copy the role/model setup from `tests/test_query_pipeline_routing.py` (roles are validated against RBAC). Tests:
1. estimate N+1 -> `QueryBlockedContextLimitResponse(limit="estimated_tokens", maximum=N, actual=N+1)`, upstream never called (AC1).
2. estimate == N -> proceeds, upstream called once (AC2).
3. model without `max_context_tokens` (oversized but under the character limit) proceeds; the same in legacy mode (no file); a spy on `query_pipeline.estimate_tokens` is not called when it is None (AC3, "skipped, not computed").
4. precedence: with `CONTEXT_MAX_MESSAGES` (then `CONTEXT_MAX_CHARACTERS`) monkeypatched low, `limit` is `messages` (then `characters`) even when the estimate also breaches.
5. tools counted: `ToolParams(tools=[...])` pushes an otherwise-fitting conversation over N; expected `actual` = chars + `len(json.dumps(tools, sort_keys=True, ensure_ascii=False))` at cpt 1. The pipeline takes `tools` directly; the tools-capability gate is the `/v1` router's, so no `supports_tools` setup is needed for a direct `run_conversation` call (verify when writing).
6. audit row: `success is False`, `error_message == f"context limit: estimated_tokens {actual} > {N}"`, route columns present (AC4).
7. `/v1` 400: `TestClient` POST to `/v1/chat/completions` with the file-mode model, stub `app.routers.v1.call_openrouter`; expect `_error(400, "invalid_request_error", "context_length_exceeded", "Conversation exceeds context limit: estimated_tokens {a} > {N}", harness={"reason": "Conversation exceeds context limit", "limit": "estimated_tokens", "maximum": N, "actual": a})`, upstream calls `[]` (AC4). Needs a user token as in `test_v1_errors.py:76-82`, and the model must pass the `/v1` role allowlist in file mode.
8. passthrough route with `passthrough_capabilities: {max_context_tokens: N}` also refuses (guards the `route.model is None` case).
Plus the append-only schema, copy and chat-state tests from the Files table.

## End-to-End Tests

- [ ] `TestClient(app)` POST `/v1/chat/completions`, file-mode model with `max_context_tokens`, over limit -> 400 `context_length_exceeded`, nothing upstream (Task 5 test 7)
- [ ] Chat UI: `chat_state` send of an over-limit conversation renders the `context_limit` bubble with detail `estimated tokens <a> of <N>` (appended test in `test_chat_state.py`, patterned on `:3369-3401`)

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider \
  tests/test_query_pipeline_max_context_tokens.py tests/test_schemas.py tests/test_copy.py \
  tests/test_chat_state.py tests/test_context_limit_bubble.py tests/test_chat_ui_startup_guard.py \
  tests/test_query_pipeline_tools.py tests/test_chat_history.py tests/test_v1_errors.py \
  tests/test_v1_translate_result.py tests/test_untouched_app.py
```
Full suite: GitHub CI on push (user decision). If `test_chat_state.py` is too slow, run it with `-k "context_limit or estimated"`.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 > N refused, nothing upstream | 4 | `test_query_pipeline_max_context_tokens.py` test 1 |
| AC2 == N proceeds | 4 | test 2 |
| AC3 no max -> unchanged | 4 | tests 3, 4 (legacy, no capability, not computed, order) |
| AC4 /v1 400 + audit row | 4 | tests 6, 7 |
| AC5 schema literal | 1, 2 | `test_schemas.py` (modified + appended); `test_chat_state.py` and `test_copy.py` appended |

## Risks

- The existing `get_args` assertion in `tests/test_schemas.py:425` must change (Task 2).
- Chat UI `KeyError` if Task 3 is skipped: a refusal would crash the send path.
- `test_copy.py` is in the census (`test_untouched_app.py:86`): append only.
- The estimate is a heuristic (T10, section 15): a refusal near N can be a false positive; documented, not a bug.
