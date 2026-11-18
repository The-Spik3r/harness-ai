---
story: STORY-003
prd: PRD-021
slug: stream-upstream-seam
title: stream_upstream seam, ReasoningDelta and collect()'s usage override
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-021-realtime-streaming
created: 2026-11-18
---

# Plan: stream_upstream seam, ReasoningDelta and collect()'s usage override

## Summary

Add the PRD-020 stream surface the pipeline (STORY-006) will consume: a `ReasoningDelta` event, an opt-in reasoning mapping in `parse_events`, a stream-end-without-`Finish` check in the adapter, a `usage_missing` override on `collect()`, and `stream_upstream()` beside `call_upstream()` sharing one route/key helper. Nothing outside `app/services/upstream/` changes. `complete()`, `call_upstream` and every existing caller stay byte-identical.

- Story: `.agents/stories/PRD-021-realtime-streaming/STORY-003-stream-upstream-seam.md` (ACs live there)
- PRD sections used: 6.2, F2, D4, D20 (out of scope here, STORY-006), Risk 3, OD1/OD3
- Systems affected: `app/services/upstream/` only (`openrouter_client.py` needs no alias: `stream_upstream` is new, nothing imports it under an old name; the shim's pattern aliases only the old `call_openrouter` names)

## Design Decisions

Binding points from the orchestrator, with the code facts that shape them:

- **`ReasoningDelta(text: str)`**: frozen dataclass in `types.py` (after `Finish`, `types.py:101-108`), added to the `UpstreamEvent` Union and to `__init__.__all__` plus its import list (`__init__.py:23-51`).
- **Opt-in reasoning**: `parse_events(lines, label, *, reasoning: bool = False)` -> `_chunk_events(..., reasoning)` (`sse.py:22,47`). When true, inside `if delta:` (`sse.py:60`) and before the content branch: take the first of `delta.reasoning_content`, `delta.reasoning` that is a non-empty `str` and yield one `ReasoningDelta` (one event, never both: OpenRouter sends only `reasoning`, DeepSeek-style only `reasoning_content`; STORY-001 order is `reasoning_content` then `reasoning`). Non-str (`null`) and `""` yield nothing. `reasoning_details` is never read. When false, none of these keys is read (Risk 3: dropped).
- **Empty content stays** (orchestrator correction, retracts that half of point 2): `sse.py:62-63` is unchanged, so `content: ""` still yields `TextDelta("")`. A reasoning model that spends its budget on reasoning ends with `content: ""` + `finish_reason: length`; dropping the delta would make `collect()` see null content and raise where `complete()` returns `""`. Only empty/non-str reasoning is dropped. For later stories: STORY-006's `phase_of` and the sink forwarding must ignore empty text.
- **Adapter**: `OpenAICompatibleAdapter.stream(self, request, api_key, *, reasoning: bool = False)` (`openai_compatible.py:166`) passes it to `parse_events`. Update the `ProviderAdapter` Protocol (`types.py:116`) with the same optional keyword. `complete()` is untouched.
- **Several `Finish`**: `collect()` keeps `finish_reason = event.reason` only when it is not None (`collect.py:50-51`; `Finish.reason` is `str`, so "last non-None" is today's behaviour with the explicit guard). Add `ReasoningDelta` as an ignored branch before the `else: raise TypeError` (`collect.py:62`); `test_collect_rejects_an_unknown_event` still passes.
- **No `Finish` check exists today** (only `stream ended without [DONE]`, `sse.py:44`). Add it in `stream()` at `openai_compatible.py:184`: replace `yield from parse_events(...)` by a loop that records `isinstance(event, Finish)`, yields each event, and after the loop raises `UpstreamError(f"{label} returned an unexpected response shape: stream ended without a finish reason")` (non-retryable by default; same prefix as `sse.py:24`). Inside the `with`/`try`, so the response and client close as today (`UpstreamError` is not `httpx.HTTPError`, so it passes `except` at `:185`). Not in `collect()`, so `collect` of hand-built events is unchanged.
- **`collect(events, *, provider, request, usage_missing: Optional[str] = None)`**: `None` = the provider's mode. Any other value must be in the registry's `USAGE_MISSING = ("estimate", "error")` (`provider_registry.py:52`) else `ValueError` naming the value's allowed set. **Purity constraint**: `test_pure_modules_import_no_http_client_settings_or_registry_at_runtime` (`tests/test_upstream_stream_collect.py:432-451`) forbids any runtime import of `app.services.provider_registry` in `collect.py`/`reply.py`/`sse.py`, and `types.py` cannot host the tuple (the registry importing `upstream.types` would run the package `__init__`, which imports the registry: cycle). So `reply.py` gets a private `_USAGE_MODES = ("estimate", "error")` and a test pins it equal to `provider_registry.USAGE_MISSING`. Validation runs at the top of `collect`, before consuming events. The override reaches `_resolve_usage(provider, label, data, content, calls, request, *, usage_missing=None)` (`reply.py:68`) via `result_from_reply(..., *, usage_missing=None)` (`reply.py:118`); inside, `mode = usage_missing or provider.usage_missing` replaces the read at `reply.py:88`. `Provider` is never mutated or replaced. `complete()` passes nothing.
- **`stream_upstream(messages, model=_DEFAULT_MODEL, api_key=None, params=None, client=None, *, tools=None) -> Iterator[UpstreamEvent]`**: a plain `def` (no `yield`), so errors raise at call time. A private `_resolve_call(messages, model, api_key) -> (route, key)` holds `__init__.py:71-88` verbatim (empty-messages check, route None error, D10 key choice and hint messages); `call_upstream` calls it, then builds the adapter and request exactly as before (`:90-93`). `stream_upstream` calls it, builds `UpstreamRequest(messages, route.upstream_model, params, tools)`, and returns `OpenAICompatibleAdapter(route.provider, client).stream(request, key, reasoning=route.capabilities.reasoning)`. No `dataclasses.replace(model_used)` applies (events carry no model). Legacy mode keeps `reasoning=False` (OD1), untouched. Add to `__all__`.
- **D20** (total stream deadline) is STORY-006's; do not touch timeouts.

### Conflicts between the binding design and existing tests (the implementer must resolve, with a PRD-021 comment on each edit, and tell the orchestrator)

1. **Stream-end-without-`Finish` vs `collect(stream(r)) == complete(r)`** (accepted, PRD F2): inline case `{"content": "x", "finish_reason": None}` (`test_upstream_stream_collect.py:138`) sends a finish chunk with `null`, no `Finish` event, so `stream()` now raises while `complete()` succeeds. Keep it out of the property with a comment citing PRD-021 F2, and give it its own test asserting the non-retryable error. The `:137` case (`content: ""`) stays in the property unchanged.
2. **Tests that drain `stream()` on bodies with no finish chunk** now raise: `test_payload_keys` (`:405-416`), `test_blank_lines_comments_and_unknown_fields_are_ignored` (`:356`), `test_chunk_with_empty_choices_and_usage_yields_a_usage_report` (`:367`), the closing tests (`:479-510`), the `_capture` handler (`:395`); grep `_stream_events(`, `list(adapter.stream`, `_sse(_delta(` for the rest. Append a `finish_reason: "stop"` chunk (adjust expected events) with a PRD-021 comment. Do not weaken the `Finish` rule.

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`; no UI here).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Naming/docstrings | `types.py:73-105` | frozen dataclass + one-line docstring citing the PRD |
| Errors | `sse.py:24,40` and `openai_compatible.py:123-128` | non-retryable `UpstreamError`, shared "returned an unexpected response shape: " prefix, field named, no payload quoted (T7) |
| Shared logic | `reply.py:118` `result_from_reply` serves `complete()` and `collect()` | thread the override as an optional keyword, no duplication |
| Fixtures | `tests/test_upstream_stream_collect.py:97-110` (`_sse`, `_delta`, `_mock_client`, `_stream_events`) | feed saved `.sse` lines through `MockTransport` |
| Registry in tests | `tests/_providers.py:26` `providers_file` | file-mode registry with `streaming/reasoning: true` for the `stream_upstream` route tests; `tests/test_upstream_adapter.py:100-130,167` shows `call_upstream` against a file registry |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/upstream/types.py` | UPDATE | `ReasoningDelta`, union, Protocol keyword |
| `app/services/upstream/sse.py` | UPDATE | `reasoning` flag (empty content unchanged) |
| `app/services/upstream/openai_compatible.py` | UPDATE | `stream(..., reasoning=False)`, no-`Finish` check |
| `app/services/upstream/collect.py` | UPDATE | ignore `ReasoningDelta`, last non-None finish, `usage_missing` |
| `app/services/upstream/reply.py` | UPDATE | `_USAGE_MODES`, override into `_resolve_usage` / `result_from_reply` |
| `app/services/upstream/__init__.py` | UPDATE | `_resolve_call`, `stream_upstream`, exports |
| `tests/test_upstream_stream_collect.py` | UPDATE | conflicts 1-4 above |
| `tests/test_stream_upstream_seam.py` | CREATE | new behaviour tests (below) |

## Tasks

Execute in order.

### Task 1: ReasoningDelta type
- **File**: `app/services/upstream/types.py` and `__init__.py` exports
- **Implement**: dataclass, `UpstreamEvent` union, Protocol `stream(..., *, reasoning: bool = False)`; import and `__all__` entry.
- **Mirror**: `types.py:75-80`
- **Validate**: `.venv/Scripts/python -c "from app.services.upstream import ReasoningDelta"`

### Task 2: Parser
- **File**: `sse.py`
- **Implement**: per Design Decisions (flag, one event, empty/None/non-str dropped, `reasoning_details` ignored; content untouched). Reasoning is yielded before content within one delta.
- **Validate**: `tests/test_stream_upstream_seam.py`

### Task 3: Adapter Finish check + reasoning keyword
- **File**: `openai_compatible.py:166-189`
- **Implement**: per Design Decisions. Keep laziness (`test_stream_is_lazy...`) and the close-on-end/early-close/error behaviour (`:479-510` tests).
- **Validate**: `tests/test_upstream_stream_collect.py`

### Task 4: collect + usage override
- **File**: `collect.py`, `reply.py`
- **Implement**: per Design Decisions; docstring of `collect` cites PRD-021 D4. Validation error text: `usage_missing must be one of ('estimate', 'error'), got <value>` (a mode name, never content).
- **Validate**: `tests/test_upstream_stream_collect.py`, `tests/test_upstream_adapter.py`

### Task 5: stream_upstream
- **File**: `__init__.py:56-93`
- **Implement**: extract `_resolve_call`; keep `call_upstream` messages and order identical (empty messages first, then route, then key). `stream_upstream` as a plain function, docstring: lazy network, eager route/key.
- **Mirror**: `__init__.py:56-93`
- **Validate**: `tests/test_upstream_adapter.py` (`test_call_upstream_keeps_call_openrouters_signature` still passes)

### Task 6: Tests
- **File**: `tests/test_stream_upstream_seam.py` (CREATE) and the edits for conflicts 1-4
- **Implement** (replay the three `tests/fixtures/prd021_survey/*.sse` files through `parse_events` and through `OpenAICompatibleAdapter(...).stream()` on a `MockTransport`, no network):
  - AC1: `ReasoningDelta` frozen (`FrozenInstanceError`), in `typing.get_args(UpstreamEvent)`, in `upstream.__all__`.
  - AC2: deepseek fixture with `reasoning=True`: `ReasoningDelta` events, joined text equals the concatenated `delta.reasoning`, 38 empty `TextDelta` (content is `""` on every chunk), 2 `Finish`, 1 `UsageReport`; with `reasoning=False` (default): no `ReasoningDelta`, the same 38 empty `TextDelta`. Inline: `reasoning_content` mapped; both keys on one delta give one event; `reasoning: null`, `""`, a number, a list and `reasoning_details` give none; gpt-4o-mini and gemma fixtures give identical events with either flag. `reasoning` and `reasoning_content` never reach text (`collect` response unaffected).
  - AC3: `collect([... ReasoningDelta ...])` equals the same without them; two `Finish("length")` events give `finish_reason == "length"`, `[Finish("stop"), Finish("length")]` gives `"length"`; the existing property test still passes for every non-diverging case.
  - AC4: `collect(..., usage_missing="estimate")` on a provider with `usage_missing="error"` and no `UsageReport` -> `usage_estimated` True and `tokens_used` equal to the `estimate` provider's result; without the override still raises `'usage'`; `usage_missing="error"` on an `estimate` provider raises; `"bogus"` raises `ValueError`; the frozen provider is unchanged (`provider.usage_missing` same); `_USAGE_MODES == provider_registry.USAGE_MISSING`; the existing purity AST test still passes.
  - AC5: with `providers_file`: `stream_upstream([], ...)` raises `UpstreamError("messages must not be empty")` at call time (assert before any `next`); an unknown model raises "No provider route for the requested model" at call time; a missing key raises the same text `call_upstream` raises (parametrize both functions and compare messages); the returned object is an iterator whose first `next` sends the request; a route with `reasoning: true` maps reasoning, one with `reasoning: false` (and legacy mode) drops it; D10 key choice (byok caller key vs provider key) matches `call_upstream`. Stream-end: each of the three fixtures drains fine (all have a `Finish`); the same fixture minus its `Finish` lines raises a non-retryable `UpstreamError` (`retryable is False`, `upstream_status is None`) with the "finish reason" text and no payload text; two-`Finish` streams (deepseek, gpt-4o-mini) do not raise.
  - Empty content: a stream with `content: ""` and `finish_reason: length` still yields `TextDelta("")` and `collect` returns `""` (parity with `complete()`); the deepseek fixture still yields its 38 empty `TextDelta` (counts in the AC2 test).
- **Validate**: see below

## End-to-End Tests

- [ ] `stream_upstream` against the stub (`scripts/stub_openrouter.py`, free port, pattern at `tests/test_upstream_stream_collect.py:62-80`) with a file-mode registry: `collect(stream_upstream(...), provider=route.provider, request=...)` returns the stub's text and finish reason.
- [ ] Not applicable: no route, `chat_ui/` or pipeline change in this story (`/v1`, `/query` untouched).

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_stream_upstream_seam.py tests/test_upstream_stream_collect.py tests/test_upstream_adapter.py tests/test_untouched_app.py
```

Also run `tests/test_stub_openrouter.py` and `tests/test_provider_routing.py` if the implementer touches nothing else shared (they exercise `call_upstream`). No test is renamed or removed, so the PII guard is not needed; if one is renamed, register it in `_DELIBERATELY_SUPERSEDED_TESTS`.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 ReasoningDelta type/export | 1 | `test_stream_upstream_seam.py::test_reasoning_delta_is_frozen_in_union_and_exported` |
| AC2 reasoning opt-in, fixture replay | 2, 3, 6 | `::test_deepseek_fixture_maps_reasoning_only_when_enabled` and siblings |
| AC3 collect ignores reasoning, parity holds | 4 | `::test_collect_ignores_reasoning_and_keeps_last_finish`, `test_upstream_stream_collect.py::test_collect_of_stream_equals_complete` (with the `:138` case excluded, PRD-021 F2) |
| AC4 usage override | 4 | `::test_collect_usage_missing_override_*` |
| AC5 stream_upstream, eager errors, no-Finish | 3, 5 | `::test_stream_upstream_*`, `::test_stream_without_finish_raises_non_retryable` |

Plus: all tasks done, validation passes, no change to `call_upstream` behaviour or messages.

## Risks

- Divergence at `:138` (null finish chunk) is accepted (PRD F2).
- `_USAGE_MODES` duplicates the registry vocabulary because purity forbids the import; the equality test is the guard.
