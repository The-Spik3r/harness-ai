---
story: STORY-008
prd: PRD-022
slug: anthropic-primary-end-to-end
title: Anthropic as a primary through the pipeline — dropped params, cache tokens on the row, /v1 tool loop
type: ENHANCEMENT
complexity: medium
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
created: 2026-11-20
---

# Plan: Anthropic as a primary through the pipeline

## Summary

A wiring story. The adapter factory already serves every upstream path, so the only pipeline gaps are (1) `dropped_params` never reaches the success row's `ignored_params`, and (2) the realtime path's own `UpstreamRequest` lacks `model=`. Everything else (tool loop, cache columns, charge, refusal, reasoning gates) is verified by new integration tests against the STORY-006 stub, with no code change unless a test shows a hole.

- Story: `.agents/stories/PRD-022-provider-fallback-and-native-adapters/STORY-008-anthropic-primary-end-to-end.md`
- PRD sections used: 6.5, 6.6, Phase 2 validation, user stories 3 and 5, D4, D10, D11
- Systems affected: `app/services/query_pipeline.py` (step 7 and the success row); tests otherwise

## Path audit (what already goes through the factory)

| Path | Seam | Factory? |
|---|---|---|
| `/query` (`routers/query.py:14,200`), chat UI (`chat_ui/chat_ui/state.py:26`, buffered), `/v1` buffered (`routers/v1.py:71,181` `_Upstream` wrapper) | `call_upstream` -> `_resolve_call` -> `_build_adapter` (`upstream/__init__.py:127`) | yes, no change |
| realtime `/v1` | `stream_upstream` (`upstream/__init__.py:~141-153`) builds its own `UpstreamRequest(..., route.model)` and passes `reasoning=route.capabilities.reasoning` | yes, no change |
| realtime `collect()` input | `query_pipeline.py:1082` `UpstreamRequest(redacted_messages, route.upstream_model, params, tools)` | request only feeds `collect()` (tools gate, D8 estimate), so the stream itself is not broken today; it **lacks `model=`** (GAP) |

`UpstreamRequest(` sites in `app/` (grep, 3 total): `upstream/__init__.py:127` and `:150` pass `route.model`; `query_pipeline.py:1082` does not. Nothing under `chat_ui/` or `scripts/` constructs one.

Other verified facts: `charge()` (`query_pipeline.py:~1256`) already receives `input_tokens`/`output_tokens`/`tokens_used` from the result, and `_usage_counts` (`upstream/anthropic.py:260`) already folds both cache counts into the prompt; the success row already writes `cache_read_tokens`/`cache_write_tokens` (`:1379-1380`). `/v1` already maps `content_filter` (`v1_translate.py:124,620`). `dropped_params` is set only by `AnthropicAdapter.complete()` (`anthropic.py:507`) and survives `call_upstream`'s `dataclasses.replace`.

## Design Decisions

- **`ignored_params` merge (success row only).** New pure helper in `query_pipeline.py`: `_merge_ignored_params(edge: Optional[str], dropped: Sequence[str], provider_name: str) -> Optional[str]`. It splits the edge string on `,`, appends `f"{name}@{provider_name}"` for each dropped name not already present (edge first, then the adapter's), and returns the edge value unchanged (None stays None) when nothing is dropped. Used only at the success `log_query` (`:1411`). The step-8 `PiiRedactorError` row (`:1346`), the upstream-error row (`:1231`) and every earlier row keep the edge value (error rows unchanged).
- **Realtime path, dropped params (binding point answered: reuse, not a gap).** `collect()` carries no `dropped_params`. After `collect(...)` in the streamed branch (`:1165-1173`), `dataclasses.replace(..., dropped_params=anthropic_dropped_params(stream_request, route.model) if route.provider.type == "anthropic" else ())`, importing `dropped_params as anthropic_dropped_params` from `app.services.upstream.anthropic`. The `type` guard is mandatory: `sampling_params` defaults to False (`provider_registry.py:106`) for every model, so an unguarded call would report `temperature` dropped on OpenRouter models. This needs `model=` on `stream_request`, so the `:1082` fix is required, not cosmetic. One function, two callers; the rule is not duplicated.
- **Fix `:1082`:** `UpstreamRequest(redacted_messages, route.upstream_model, params, tools, route.model)`, same form as `upstream/__init__.py:127`.
- **Off means PRD-020/021.** For `openai_compatible`, `dropped_params` is `()` on both paths, so `ignored_params` is byte-identical to today and no existing test changes. The call seam and its arguments are untouched.
- **No chain:** every row is `attempt=1` (the pipeline already writes it). No new audit field and no `database.py` change, so no census guard applies.
- Realtime refusal: the stream yields one `TextDelta("")` (not forwarded), `collect` gives `response == ""`, finish `content_filter`. Verify it ends in a success row, not a `shape` error. If the null-content rule in `upstream/reply.py` rejects `""`, tell the orchestrator before changing anything.

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`; story `skills: []`).

## Patterns to Follow

| Category | Source | What to mirror |
|---|---|---|
| Integration harness | `tests/test_query_pipeline_routing.py:61-135` | `temp_db`, `stubs` factory (free port, shutdown at teardown), `provider_file` YAML, `TestClient(app, headers=...)`, `_last_row` |
| Anthropic stub provider | `tests/test_stub_anthropic_mode.py:26-45`, `tests/test_provider_registry.py:70-78` | `make_server(parse_script(...), require_key=...)`; `type: anthropic`, `base_url` without `/v1`, `insecure_http: true`, `key_env`, model with `default_max_tokens` |
| Realtime ASGI harness | `tests/test_v1_realtime.py:415-440` (`rt` fixture), `:611-640` (`_drive`, `_events`, `_reasoning`, `_until_rows`) | grants via `monkeypatch.setattr(authz, "ROLE_PERMISSIONS", ...)`; do NOT install a fake `stream_upstream`, so the real adapter hits the stub |
| Charge spy | `tests/test_query_pipeline_streaming.py:314-322` | `monkeypatch.setattr(query_pipeline, "charge", spy)` |
| Source guard | `tests/test_query_pipeline_routing.py:403` | static check on pipeline source |
| Stub scripting | `scripts/stub_openrouter.py:20-98` | rules with `role`, `after_call`, `regex: ""`; `tool_calls` with string `arguments`; `stop_reason: "refusal"`; cache usage keys; `stream.reasoning` becomes a `thinking` block |
| Comments | `query_pipeline.py:1374-1380` | cite `PRD-022 STORY-008, D4/D10` |

## Files to Change

| File | Action | Purpose |
|---|---|---|
| `app/services/query_pipeline.py` | UPDATE | import, `_merge_ignored_params`, `:1082` `model=`, realtime `dropped_params`, success-row `ignored_params` |
| `tests/test_anthropic_primary_pipeline.py` | CREATE | all tests below |

## Tasks

### Task 1: pipeline wiring
- **File**: `app/services/query_pipeline.py`
- **Implement**: the four edits above. Success row: `ignored_params=_merge_ignored_params(ignored_params, openrouter_result.dropped_params, route.provider.name)`; never dereference `route` when `dropped_params` is empty (injected stubs, legacy mode). Keep `**_route_fields(route),` first in every `log_query(`.
- **Mirror**: `upstream/__init__.py:127`; `anthropic.py:229-234`
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: fixtures and unit tests (`tests/test_anthropic_primary_pipeline.py`)
- Registry YAML: provider `ant` (`type: anthropic`, loopback `base_url`, `insecure_http`, `key_env: ANT_KEY_ENV` set by `monkeypatch.setenv`, `byok: false`), model `claude-x` (`upstream: claude-up`, `default_max_tokens: 256`, `capabilities: {tools: true, streaming: true, reasoning: true}`, no `sampling_params`). A second provider `oai` (`openai_compatible`, same stub, Chat mode) for the equivalence controls. Settings as the `rt` fixture (`V1_TOOLS_ENABLED`, `STREAMING_ENABLED`, `PII_REDACTION_ENABLED=False`, usage limits on so `admission` is set and `charge` runs).
- `test_merge_ignored_params_*` (pure): edge first then adapter, no duplicate, None stays None, empty dropped returns the edge unchanged.
- `test_every_upstream_request_in_app_passes_the_model` (ast over `app/**/*.py`): each `UpstreamRequest(` call has 5 args or `model=`. It fails on the old `:1082`.

### Task 3: buffered `/v1` integration tests (TestClient, real adapter, stub in Messages mode)
- **Tool loop (AC1).** Script: rule `{"role":"tool","regex":"","after_call":"bash","content":"tests pass"}`, default `tool_calls [{"name":"bash","arguments":"{\"command\":\"npm test\"}","id":"toolu_01x"}]`. Turn 1 (body advertises `bash`): `tool_calls[0].function.arguments == '{"command":"npm test"}'` (canonical, unspaced). Spy `query_pipeline.action_policy.evaluate_all` (wrap and delegate): called once with those exact arguments. Turn 2 (assistant `tool_calls` plus `tool` message sent back): answer `tests pass`, which proves `tool_use`/`tool_result` mapping end to end. Equivalence: the same turn 1 against `oai` gives equal `evaluate_all` decision tuples (`decision`, `rule`). Reuse PRD-017's tool-loop assertions where importable; otherwise assert the same facts (`harness.actions` shape, row `has_tool_calls`).
- **Dropped params (AC2).** Body `temperature: 0.7` plus an edge-ignored key (`presence_penalty`). Row `ignored_params == "presence_penalty,temperature@ant"`. Control: `oai` gives `presence_penalty` only. Error row: script `fail_status: 503` leaves `ignored_params == "presence_penalty"` (no `@`).
- **Cache + charge (AC3).** Usage `{"prompt_tokens": 10, "completion_tokens": 4, "cache_creation_input_tokens": 3, "cache_read_input_tokens": 2}`. Row: `cache_write_tokens == 3`, `cache_read_tokens == 2`, `input_tokens == 15`, `output_tokens == 4`, `tokens_used == 19`; the charge spy received `(user, day, 15, 4, 19)`. Control: `oai` without cache keys gives NULL cache columns.
- **Refusal (AC4).** Script `{"content": "", "stop_reason": "refusal"}`: `/v1` 200, `finish_reason == "content_filter"`; one new row, `success=1`, `attempt=1`; `endpoint_hits()["messages"] == 1` (no retry).

### Task 4: realtime integration tests (async ASGI, real `stream_upstream`)
- **With grants (AC5).** Grants `{submit, stream:realtime, reasoning:view}`, reply with `stream: {reasoning: "think hard"}` and content `answer`: `reasoning_content` deltas equal `think hard`, content `answer`, no `reasoning` key; row `reasoning_shown is True`, `streamed_realtime is True`.
- **Without `reasoning:view`:** same script, grants `{submit, stream:realtime}`: no reasoning text anywhere in the SSE body, row `reasoning_shown is False`, content still streams.
- **Realtime parity:** a realtime request with `temperature` records `temperature@ant` on the success row (proves the Task 1 stream branch); a realtime `oai` request records nothing extra. Cache columns and the charge spy are checked on one realtime row too.
- **Realtime refusal:** streamed `stop_reason: refusal` gives a success row, `content_filter`, `attempt=1`.
- Every Anthropic test asserts `endpoint_hits()` hit `messages`, not `chat`.

## End-to-End Tests

- [ ] `/v1` buffered tool loop through `TestClient(app)` to the Messages stub (Task 3)
- [ ] realtime `/v1` SSE through the ASGI driver to the Messages stub (Task 4)
- [ ] No `chat_ui/` change (its path is the buffered seam, covered by the audit)

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_anthropic_primary_pipeline.py tests/test_query_pipeline_routing.py tests/test_query_pipeline_streaming.py tests/test_query_pipeline_audit_realtime.py tests/test_v1_realtime.py tests/test_prd020_legacy_fixtures.py tests/test_untouched_app.py
```
Add `tests/test_anthropic_adapter.py tests/test_anthropic_stream.py` only if `anthropic.py` changes (it should not). `test_pii_redaction_integration.py` is not needed (no test renamed or removed). One pytest process at a time.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|---|---|---|
| AC1 tool loop, `evaluate_all`, canonical args | Task 3 | `test_anthropic_primary_pipeline.py::test_v1_tool_loop_through_an_anthropic_primary` (+ `oai` equivalence) |
| AC2 `temperature@<provider>` on the success row | Tasks 1, 3, 4 | `::test_temperature_is_recorded_as_ignored_on_the_success_row`, `::test_realtime_records_dropped_params` |
| AC3 cache columns, prompt total, `charge()` spy | Task 3 (4) | `::test_cache_usage_lands_on_the_row_and_charge_gets_the_full_prompt` |
| AC4 refusal row | Task 3 (4) | `::test_refusal_is_content_filter_one_success_row_attempt_one` |
| AC5 realtime reasoning gates, `reasoning_shown` | Task 4 | `::test_realtime_reasoning_with_and_without_reasoning_view` |

Plus: the `UpstreamRequest(` AST guard and `_merge_ignored_params` unit tests (Task 2); all tasks done, validation green, existing tests untouched.

## Risks

- Existing stubs of `call_openrouter` returning a non-`UpstreamResult`: the success row reads `openrouter_result.dropped_params`; use `getattr(..., "dropped_params", ())` if the targeted run shows one.
- Stub rule matching on the tool-loop second turn (`after_call` on a converted `tool_result` user turn) is documented at `stub_openrouter.py:84-88`; if it fails, fix the script, not the stub.
- Appended names follow the edge's sorted list unsorted, so the order is deterministic but not globally sorted.

## Orchestrator corrections (binding, 3.2 review)

- Do not branch on `route.provider.type` in `query_pipeline.py`. Add a public helper `dropped_params_for(route, request) -> tuple[str, ...]` in `app/services/upstream/__init__.py`, next to `stream_upstream`, that dispatches by provider type: `anthropic` -> `anthropic.dropped_params(request, route.model)`, every other type -> `()`. The pipeline's realtime branch calls it. STORY-012 will call it per attempt with that attempt's route. Unit-test it for both types, plus the OpenRouter-type model with `sampling_params` False -> `()`.
- Realtime refusal: STORY-007 already proved `collect(stream) == complete()` for the empty-refusal script, `response == ""`. Still assert the success row.
