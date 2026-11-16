---
story: STORY-008
prd: PRD-017
slug: v1-request-translation-under-flag
title: "/v1 request translation under V1_TOOLS_ENABLED: tools, tool turns, shape rules, V1_TOOL_MODELS; passed through to step 7"
type: NEW_CAPABILITY
complexity: HIGH
epic_branch: epic/PRD-017-tool-calling
created: 2026-11-16
---

# Plan: /v1 request translation under V1_TOOLS_ENABLED

## Summary

With `V1_TOOLS_ENABLED=true`, the pure translator (`app/services/v1_translate.py`) admits
`tools`, `tool_choice` and `parallel_tool_calls`. It validates their shape and builds
`V1Call.tools: Optional[ToolParams]`. It accepts assistant `tool_calls` turns and `tool`
turns through the STORY-003 normalizer, checks the D6 rules with the shared
`conversation_shape_violation` helper (STORY-005), and refuses a `tools` request for a model
outside `V1_TOOL_MODELS` (D16). The flag and the model list are **arguments**:
`translate_request(body, *, tools_enabled=False, tool_models=())`. The router reads
`settings` on every request and passes them in, so the translator stays pure. The router
passes `tools=call.tools` to `run_conversation`, which gains a keyword-only
`tools: Optional[ToolParams] = None` and hands it to `call_openrouter` at step 7 only when it
is set (`params=`'s rule). The flag-off path is today's code, unchanged. A new test runs a
representative set of PRD-015 refusals with the flag explicitly off and checks them byte for
byte. Every flag-on path is tested in a new `tests/test_v1_tools.py`. Until STORY-010/011,
the response is built from `response` only, so upstream `tool_calls` are dropped. A test pins
that interim behaviour.

## User Story

As an integrating developer
I want `/v1` to accept my agent's tool definitions and tool history when the operator has enabled tools
So that the request reaches the model with everything it needs, and is refused clearly when tools are off or malformed

## Story Reference

- Story file: `.agents/stories/PRD-017-tool-calling/STORY-008-v1-request-translation-under-flag.md`
- PRD: `.agents/PRDs/PRD-017-tool-calling/PRD.md` (Sections 4, 6.3, 6.7, 7 F3, 10, 15 D6/D10/D11/D16)
- Client shapes: `.agents/spikes/PRD-017-tool-calling/client-survey.md` (STORY-001 hand-offs)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | HIGH |
| Systems Affected | `/v1` translator, `/v1` router, query pipeline step 7 |
| Story | STORY-008 |
| PRD | PRD-017 |
| Epic Branch | `epic/PRD-017-tool-calling` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` (UI design). This story has no UI; the story's `skills: []` agrees. | — |

---

## Decisions this plan makes (orchestrator: confirm or override)

These are binding for the implementer. Each one follows the story's orchestrator notes or the PRD. Where the PRD is silent, the choice is stated so it can be checked.

1. **Signature (purity).** `translate_request(body, *, tools_enabled: bool = False, tool_models: Sequence[str] = ())` and `translate_messages(raw, *, tools_enabled: bool = False)`. The defaults are the flag-off values, so every existing caller stays byte-identical without an edit: the tests in `tests/test_v1_translate_request.py`, `tests/test_e2e_live.py:67` and `scripts/measure_v1_latency.py:254`. The router always passes both arguments explicitly, and a test pins that (Task 7). The parameter must not be named `settings`: `test_is_pure` (`tests/test_v1_translate_request.py:333-349`) bans that identifier in the module.
2. **Groups (PRD-015 Section 7.3).** `REJECTED_UNLESS_DEFAULT`, `FORWARDED` and `_STRUCTURAL` stay unchanged. They are the flag-off table, and `tests/e2e/_live.py:233-242` mirrors them (checked by `tests/test_e2e_live.py:41-43`), so neither file changes. A new `TOOL_PARAMS = frozenset({"tools", "tool_choice", "parallel_tool_calls"})` is the flag-on group. With the flag on, its keys are classified as tool params, not as rejected or ignored. `functions` and `function_call` stay rejected (D10). Each key is in exactly one group **per flag state**, and a new test pins that. `parallel_tool_calls` stays undeclared on `ChatCompletionRequest` (it is read from `model_extra`). Declaring it would break `test_every_declared_request_field_is_classified` (`tests/test_v1_translate_request.py:792-797`), and with the flag off it must remain an ignored unknown key (D11).
3. **`tools: []` / absent / `null`, flag on** gives `V1Call.tools = None` (orchestrator decision, STORY-004). With no tools to forward:
   - `tool_choice` absent, `null` or `"none"` is accepted, not forwarded and not ignored (the same as flag-off's default).
   - Any other valid `tool_choice` is 400 `invalid_parameter`, `param: "tool_choice"`, with the message `tool_choice: requires a non-empty tools list`.
   - `parallel_tool_calls` that is present (even as `null`) and is `null` or a bool is recorded in `ignored_params`, exactly as with the flag off. Nothing was forwarded, and recording it keeps "not silently dropped" (D11). As a result, flag on and flag off produce equal `V1Call`s for every request the flag-off path accepts, and Task 6 makes that a property test.
4. **`tools` non-empty, flag on**:
   - `parallel_tool_calls: null` is absent (not forwarded, not ignored), as a forwarded `null` is today (`v1_translate.py:276-278`).
   - A non-null, non-bool `parallel_tool_calls` is `invalid_parameter` whatever `tools` holds, with the message `parallel_tool_calls: must be a boolean`.
   - `tool_choice: "none"` is forwarded as sent ("values as sent", AC2).
5. **`functions` / `function_call` with the flag on** stay `tools_not_supported` with `param` = the key (Section 10). The flag-off message `tool calling is not supported (PRD-017)` would be false with tools enabled, so the flag-on rule text is `the deprecated function-calling API is not supported; use tools`. A message-level `function_call` with the flag on is `tools_not_supported`, `param: messages[i]`, message `messages[i]: function_call is the deprecated function-calling API; use tool_calls`. Flag-off strings are untouched.
6. **`null` tool fields, flag on.** `tool_calls: null`, `tool_call_id: null` (handled by the normalizer, STORY-003) and also a message's `function_call: null` count as absent. OpenAI SDK `model_dump()` echoes put `function_call: None` on every assistant message, so refusing it would break the same clients the STORY-003 decision protects. With the flag off, PRD-015's key-presence refusal (`v1_translate.py:216-219`) stays.
7. **V1_TOOL_MODELS check** (D16, STORY-002 decision). The check runs only when `V1Call.tools` is not None and `tool_models` is non-empty, and the test is `body.model in tool_models`. The translator has no identity, so the rule holds for every caller by construction. The refusal is 400 `tools_not_supported`, `param: "tools"`, message exactly `model is not enabled for tool calling (V1_TOOL_MODELS)`. This is the AC's literal text, so it has no `tools: ` prefix. Tool **history** alone (with `tools` absent or `[]`) is not checked: D16 says "a `tools` request". See Open question 2.
8. **Check order, flag on.** First, the rejected keys minus `TOOL_PARAMS`, in table order. Then the tool params (`tools`, then `tool_choice`, then `parallel_tool_calls`). Then the V1_TOOL_MODELS check. Then the forwarded keys, `stream_options` and messages. The first failure wins. Flag off: today's order, unchanged.
9. **`tools` item shape** (`invalid_parameter`; `param` is the path; the message is `{param}: {rule}` and never shows the value):
   - `tools`: must be a list. Its rule is `must be a list of tool objects`.
   - `tools[i]`: must be an object.
   - `tools[i].type`: must be `"function"`.
   - `tools[i].function`: must be an object.
   - `tools[i].function.name`: must be a non-empty string.
   - `tools[i].function.description`: absent, `null` or a string.
   - `tools[i].function.parameters`: absent, `null` or an object. It is not interpreted (F3).
   - `tools[i].function.strict`: absent, `null` or a bool.
   - Unknown keys in an item, or in `function`, are kept. `ToolParams.tools` is **the list as received**: the same object, never copied, filtered or re-serialized (F3: "forwarded as received").
   - No name regex and no duplicate-name rule: the PRD asks for shape only. The upstream judges names.
10. **`tool_choice` shape**: `"none" | "auto" | "required"`, or `{type: "function", function: {name: <non-empty str>}}`, otherwise `tool_choice: must be "none", "auto", "required" or {"type": "function", "function": {"name": ...}}`. A named function absent from `tools` gives `tool_choice: must name a function in tools`. The name is never echoed.
11. **D6 at the edge, flag on.** Only the shared helper runs, and each violation is `invalid_messages`, `param: messages[i]`, message `messages[i]: <helper rule>`. The flag-off strings `the last message must be a user turn` (`v1_translate.py:238`, pinned by `tests/e2e/test_aider.py:443`) and `tool turns are not supported (PRD-017)` are unchanged on the flag-off path. Empty messages stay `messages must not be empty` in both states.
12. **Interim T1 behaviour.** No change to `translate_result`. An upstream that answers `tool_calls` with `content: null` becomes `response=""`, and its `finish_reason: "tool_calls"` maps to `"stop"` (`_FINISH_REASONS`, `v1_translate.py:93`). The client gets an empty text completion, and nothing in the body carries the call. A test pins this, and its docstring says STORY-011 replaces it.
13. **One pre-existing `/v1` assertion has to change.** `test_profile_and_ingress_are_ordinary_ignored_keys` (`tests/test_v1_translate_request.py:763-774`) asserts that the `V1Call` field set is exactly the six PRD-015 fields. The AC requires `V1Call.tools`, so `"tools"` is added to that set with a comment citing PRD-017 STORY-008 AC2. The test's T4 intent (no field chooses the profile or the door) is kept. This is a structural assertion, not a flag-off behaviour expectation, but it breaks the brief's "UNEDITED" rule, so it is flagged here. Fallback if the orchestrator refuses: keep `V1Call` unchanged and add a pure `translate_tools(body, *, tools_enabled, tool_models) -> Optional[ToolParams]` that the router calls beside `translate_request`. The rest of the plan is unaffected. The same applies outside `/v1`: `test_run_conversation_signature_matches_the_prd` (`tests/test_query_pipeline_run_conversation.py:69-93`) gains `"tools"` in its parameter list plus two lines that pin its default and kind, with a PRD-017 comment. No test is renamed or removed, so `_DELIBERATELY_SUPERSEDED_TESTS` is untouched.

---

## Patterns to Follow

### Naming / closed constants
```
// SOURCE: app/services/v1_translate.py:95-122
FORWARDED = frozenset({"temperature", "top_p", "max_tokens", "stop", "max_completion_tokens"})
REJECTED_UNLESS_DEFAULT: Mapping[str, Tuple[str, Tuple[Any, ...]]] = {
    "tools": (TOOLS_NOT_SUPPORTED, (None, [])),
    ...
_STRUCTURAL = frozenset({"model", "messages", "stream", "stream_options"})
_REJECTED_RULES = {
    TOOLS_NOT_SUPPORTED: "tool calling is not supported (PRD-017)",
```
Add `TOOL_PARAMS` beside them, with a comment citing PRD-017 Section 4 / D11 and the "one group per flag state" rule. Add the flag-on rule texts as module constants (`_LEGACY_TOOLS_RULE`, `_TOOL_MODEL_RULE = "model is not enabled for tool calling (V1_TOOL_MODELS)"`).

### Error handling (location + rule, never a value; `from None`)
```
// SOURCE: app/services/v1_translate.py:272-295
        refusal = V1RequestError(INVALID_PARAMETER, f"{key}: {rule}", key)
        check = _FORWARDED_TYPES.get(key)
        if check is not None and not check(value):
            raise refusal
        ...
        except UnsupportedParameterError:
            # `from None`: the cause's message carries the value (T6).
            raise refusal from None
```
```
// SOURCE: app/services/v1_translate.py:298-309  (_stream_options: nested param path)
        param = "stream_options.include_usage"
        raise V1RequestError(INVALID_PARAMETER, f"{param}: must be a boolean", param)
```
```
// SOURCE: app/services/query_pipeline.py:71-79  (shared D6 helper, caller formats location)
    violation = conversation_shape_violation(messages)
    if violation is not None:
        index, rule = violation
        raise InvalidConversationError(f"messages[{index}]: {rule}")
```

### "Passed only when set" keyword (step 7)
```
// SOURCE: app/services/query_pipeline.py:697-710
    # Step 7: upstream. params is forwarded only when set: the existing
    # injected call_openrouter stubs across the suite have signature
    # (messages, model, api_key) and raise TypeError on an unexpected
    # params= keyword (PRD-010 STORY-005 Technical Notes).
    try:
        if params is not None:
            openrouter_result = call_openrouter(
                redacted_messages, model=model, api_key=openrouter_api_key, params=params
            )
        else:
            ...
```
```
// SOURCE: app/routers/v1.py:132-136  (_Upstream forwards **kwargs as received; tools= passes through unchanged)
    def __call__(self, messages, model, api_key, **kwargs) -> OpenRouterResult:
        ...
        self.result = call_openrouter(messages, model=model, api_key=api_key, **kwargs)
```

### Settings read per request in the router
```
// SOURCE: app/routers/v1.py:371-373
    # Read per request (tests monkeypatch it). ...
    models = ModelList(data=[_model_entry(model) for model in settings.model_allowlist_list])
```
`settings.v1_tool_models_list` is at `app/config.py:733-735`, and `V1_TOOLS_ENABLED` at `app/config.py:384`.

### Tests
```
// SOURCE: tests/test_v1_translate_request.py:428-436
def _body(**extra):
    return ChatCompletionRequest.model_validate({"model": "gpt-4", "messages": [_USER], **extra})

def _refusal(**extra):
    with pytest.raises(V1RequestError) as caught:
        translate_request(_body(**extra))
    return caught.value
```
```
// SOURCE: tests/test_v1_router.py:249-266  (TestClient refusal: exact error body, no row, upstream not called)
    response = client.post(_PATH, json=_body(tools=tools))
    assert response.status_code == 400
    assert response.json() == {"error": {..., "code": "tools_not_supported", "harness": None}}
    assert _count_audit_rows() == 0
    assert upstream.calls == []
```
```
// SOURCE: tests/test_v1_query_isolation.py:214-241  (real call_openrouter over httpx.MockTransport: the wire payload)
def _capturing_transport(seen: list) -> httpx.MockTransport: ...
def _upstream_over(transport): ...  # accepts params= only; the new file writes a tools-aware twin
```
```
// SOURCE: tests/test_v1_translate_request.py:401-416  (seeded property test, one id per seed)
@pytest.mark.parametrize("seed", _SEEDS)
def test_accepted_input_never_trips_the_pipeline_guard(seed): ...
```
SSE helpers: `tests/test_v1_sse.py:130-160` (`_events`, `_data`).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/v1_translate.py` | UPDATE | `TOOL_PARAMS`; flag-on `translate_messages` branch; `_tool_params`; V1_TOOL_MODELS check; `V1Call.tools`; signatures; docstrings |
| `app/services/query_pipeline.py` | UPDATE | `run_conversation(..., *, tools: Optional[ToolParams] = None)`; step 7 passes `tools=` only when set |
| `app/routers/v1.py` | UPDATE | read the flag and the model list per request, pass them to `translate_request`; pass `tools=call.tools` to `run_conversation`; module docstring line |
| `app/config.py` | UPDATE | comment at `:375-378` ("Nothing reads these yet"): `V1_TOOLS_ENABLED` / `V1_TOOL_MODELS` are now read by the `/v1` router (STORY-008); step 7c (STORY-010) is still to come |
| `tests/test_v1_tools.py` | CREATE | every flag-on translator rule, the flag-off regression set, the group partition, flag-on⊇flag-off property, router end to end (JSON + SSE), interim T1 pin, per-request flag read |
| `tests/test_query_pipeline_tools.py` | UPDATE | append a STORY-008 section: step 7 passes `tools=` only when set; three-argument stubs still work; `run_query` never sends it |
| `tests/test_query_pipeline_run_conversation.py` | UPDATE | `test_run_conversation_signature_matches_the_prd`: add `"tools"` (keyword-only, default None) with a PRD-017 comment |
| `tests/test_v1_translate_request.py` | UPDATE (one assertion) | `test_profile_and_ingress_are_ordinary_ignored_keys:767-774`: add `"tools"` to the `V1Call` field set, PRD-017 comment (Decision 13) |

Not changed, deliberately: `app/models/v1_schemas.py` (`parallel_tool_calls` stays an extra; the response shapes are STORY-011), `app/services/openrouter_client.py` (`ToolParams` landed in STORY-004), `tests/e2e/_live.py` and `tests/test_e2e_live.py` (the flag-off groups are unchanged), every other `tests/test_v1_*.py`, and `tests/test_query_outcomes_regression.py` / `tests/test_chat_outcomes_regression.py` (D17).

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Pipeline: `run_conversation(tools=)` and step 7

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**:
  - Import `ToolParams` in the existing `from app.services.openrouter_client import (...)` block (`:26-31`).
  - After `ignored_params` (`:298-301`), add a keyword-only `tools: Optional[ToolParams] = None`, with a comment in the house style: "PRD-017 Section 4, D11: the `/v1` router's `ToolParams` (STORY-008), passed to step 7 only when set, as `params` is; every other door passes nothing (D17)".
  - Step 7 (`:697-710`): replace the two-branch `if params` with a keyword dict, `extra = {}`, `params` added when not None, `tools` added when not None, and one call `call_openrouter(redacted_messages, model=model, api_key=openrouter_api_key, **extra)`. Extend the existing comment: a `tools=` keyword is passed under the same rule (PRD-017 STORY-008), so three-argument stubs keep working. Everything after the call stays unchanged: no step reads `openrouter_result.tool_calls` (STORY-010).
  - `run_query` (`:836-858`) is unchanged.
- **Mirror**: `query_pipeline.py:697-710`.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: Translator: constants, `V1Call.tools`, `translate_messages` flag-on branch

- **File**: `app/services/v1_translate.py`
- **Action**: UPDATE
- **Implement**:
  - Imports: add `conversation_shape_violation` to the `app.models.messages` import (`:27`), and `ToolParams` to the `app.services.openrouter_client` import (`:45-49`). Both modules are already in `test_is_pure`'s allowed set (`tests/test_v1_translate_request.py:340-348`).
  - Add `TOOL_PARAMS` after `_STRUCTURAL` (`:117`), with a comment. Add the rule constants from Decisions 5, 7 and 9-10.
  - `V1Call` (`:153-167`): append `tools: Optional[ToolParams] = None` as the last field (defaulted, so it is the PRD-013 widening pattern). Extend the docstring: None when no tool was forwarded, which is always the case with the flag off and with `tools` absent or `[]` (STORY-004 decision), so `call_openrouter` is called without `tools=`.
  - `translate_messages(raw, *, tools_enabled: bool = False)` (`:190-240`): the flag-off body stays byte-identical. Guard it with `if not tools_enabled:` around the two existing refusals (`:216-223`) and the last-turn check (`:235-239`). Flag-on branch, per item:
    - `function_call` present and not None gives `tools_not_supported` (Decision 5).
    - `tool_calls` and the `tool` role go to `normalize_message`. Do not refuse them, and do not special-case `null`: the normalizer already treats it as absent (`app/models/messages.py:188-209`).
    - The `name` and `developer` handling stays as it is.
    - After the loop: `violation = conversation_shape_violation(messages)`, and if it is set, `V1RequestError(INVALID_MESSAGES, f"messages[{index}]: {rule}", f"messages[{index}]")`.
  - Update the docstring. With the flag on, the edge check is the same helper as step 0, so `InvalidConversationError` stays unreachable from `/v1`. With the flag off, the PRD-015 strings are kept (orchestrator decision, STORY-005).
- **Mirror**: `v1_translate.py:204-240`; `query_pipeline.py:71-79`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_v1_translate_request.py -q` (green, apart from the one assertion Task 5 updates).

### Task 3: Translator: `_tool_params` and the V1_TOOL_MODELS check

- **File**: `app/services/v1_translate.py`
- **Action**: UPDATE
- **Implement**:
  - Write `_check_tools(value) -> List[Mapping]` for the item rules (Decision 9). It returns `value` itself and never a copy.
  - Write `_check_tool_choice(value, names) -> None` (Decision 10).
  - Write `_tool_params(sent, values) -> Tuple[Optional[ToolParams], FrozenSet[str]]`. It returns the `ToolParams` (or None, per Decisions 3 and 4) and the ignored names (`{"parallel_tool_calls"}` when Decision 3 records it).
  - Read `parallel_tool_calls` from `values.get(...)` only when the key is in `sent` (it is a `model_extra` key).
  - Every refusal is `V1RequestError(INVALID_PARAMETER, f"{param}: {rule}", param)` with no `__cause__` carrying a value.
  - `_check_rejected(sent, values, skip=frozenset(), rules=_REJECTED_RULES)`: give it the skip set (`TOOL_PARAMS` when the flag is on) and the flag-on rule text for the `TOOLS_NOT_SUPPORTED` rows. Its flag-off call stays `_check_rejected(sent, values)`, which is identical to today.
- **Mirror**: `_forwarded_params` `:272-295`, `_stream_options` `:298-309`.
- **Validate**: import check (Task 1 command).

### Task 4: Translator: `translate_request` wiring

- **File**: `app/services/v1_translate.py`
- **Action**: UPDATE
- **Implement**:
  - New signature: `translate_request(body, *, tools_enabled: bool = False, tool_models: Sequence[str] = ())`.
  - Flag off: run today's lines `:330-344` unchanged, with `tools=None`.
  - Flag on, in Decision 8's order: `_check_rejected(..., skip=TOOL_PARAMS, ...)`, then `_tool_params`, then the model check (`tools is not None and tool_models and body.model not in tool_models` gives `V1RequestError(TOOLS_NOT_SUPPORTED, _TOOL_MODEL_RULE, "tools")`), then `_forwarded_params`, then `_stream_options`, then `translate_messages(body.messages, tools_enabled=True)`.
  - `top_level` subtracts `TOOL_PARAMS` too when the flag is on. Add `tool_ignored` to the union.
  - Docstring: the flag and the list are the router's per-request reads (PRD-017 Section 6.7), passed in because this module reads no settings. Document the flag-on order and the V1_TOOL_MODELS rule (a capability list, every caller, STORY-002 decision).
  - Extend the module docstring (`:1-11`) with one sentence on PRD-017's flag-on translation.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_v1_translate_request.py tests/test_e2e_live.py -q`

### Task 5: Update the two structural assertions

- **Files**: `tests/test_v1_translate_request.py`, `tests/test_query_pipeline_run_conversation.py`
- **Action**: UPDATE (assertion only, with a comment citing PRD-017 STORY-008)
- **Implement**:
  - In `:767-774`, add `"tools"` to the `V1Call` field set. Comment: `# PRD-017 STORY-008 AC2 (D11): V1Call.tools carries the ToolParams; it is not a profile or door field, so T4 holds.`
  - In `tests/test_query_pipeline_run_conversation.py:78-82`, append `"tools"` to the list, and assert its default is None and its kind is `KEYWORD_ONLY`. Comment: `# PRD-017 STORY-008: trailing keyword-only tools, passed only by the /v1 router (Section 10's internal API).`
- **Validate**: both files green.

### Task 6: `tests/test_v1_tools.py`: translator layer (pure, no DB)

- **File**: `tests/test_v1_tools.py`
- **Action**: CREATE
- **Implement**: The module docstring cites PRD-017 STORY-008, Sections 4, 6.3, 6.7 and 10, and D6, D10, D11, D16. Fixtures come from the survey: an OpenCode-shaped body and a Cline-shaped body (below). Local helpers are `_on(**extra)`, which calls `translate_request(body, tools_enabled=True, tool_models=...)`, and `_on_refusal`. Tests:
  - **AC2 values as sent.** `tools` with name, description, parameters and strict, plus an unknown key; `tool_choice` in each of `none`, `auto`, `required` and named; `parallel_tool_calls` True and False. Assert `call.tools == ToolParams(tools=<same list>, tool_choice=..., parallel_tool_calls=...)`, `call.tools.tools is body_value`, and `"parallel_tool_calls"` is not in `ignored_params` (D11).
  - **`tools: []` / absent / `null`** gives `call.tools is None`, with `tool_choice` absent, `null` or `"none"`. `tool_choice: "auto"` with `[]` gives `invalid_parameter`, `param: tool_choice`. `parallel_tool_calls: true` with `[]` is recorded in `ignored_params`.
  - **OpenCode fixture** (`tools: []`, `stream: true`, `stream_options`, assistant `content: null` + `tool_calls`, a `tool` turn with `cache_control`, `max_tokens`, `temperature`) is accepted: `tools is None`, and the history is normalized with the arguments string byte-identical.
  - **Cline fixture** (`tools` = the four `--yolo` tools with `parameters`, `tool_choice` a string, the history `arguments` re-stringified compact JSON with odd whitespace, `reasoning_content` on the assistant turn) is accepted, and the arguments are kept exactly.
  - **Extra top-level keys** from the survey (`store`, `prompt_cache_key`, `reasoning_effort`, `tool_stream`, `seed`) are ignored, not refused.
  - **`functions` / `function_call`**, top-level and message-level, give `tools_not_supported` with `param` = the key or `messages[i]` and the flag-on messages (Decision 5). `function_call: null` in a message is accepted (Decision 6), and so are `tool_calls: null` on a user/assistant text turn and `tool_call_id: null` on a non-tool turn.
  - **Malformed `tools`**, parametrized over Decision 9's rules (not a list; item not an object; `type` "custom"; `function` missing; name `""` or `3`; description `3`; parameters `"x"`; strict `"yes"`). Each gives `invalid_parameter` with the exact `param` (`tools[1].function.name` and so on) and a message that starts `f"{param}: "`.
  - **Malformed `tool_choice`** (`"any"`, `3`, `{"type": "function"}`, `{"type": "function", "function": {"name": ""}}`, `{"type": "allowed_tools"}`) gives `invalid_parameter`, `param: tool_choice`. A named function absent from `tools` gives `tool_choice: must name a function in tools`.
  - **Non-bool `parallel_tool_calls`** (`"true"`, `1`) gives `invalid_parameter`, `param: parallel_tool_calls`. Run it with and without `tools`.
  - **D6 at the edge.** Parametrize over the four rules plus the last turn: tool first, an unknown id, separated by a user turn, answered twice, last assistant, no user turn. Each gives `invalid_messages`, `param: messages[i]`, message `messages[i]: <rule>`, and the asserted `(index, rule)` equals `conversation_shape_violation(...)` on the normalized messages. Also: the last turn may be `tool` (accepted), `tool_calls` on a user turn is `invalid_messages` (the normalizer's text kept), and a `tool` turn without an id is `invalid_messages`.
  - **AC4 V1_TOOL_MODELS.** A model outside a non-empty list with non-empty `tools` gives exactly `(TOOLS_NOT_SUPPORTED, "tools", "model is not enabled for tool calling (V1_TOOL_MODELS)")`. A model in the list passes. An empty list means any model passes. With `tools: []` plus history and a model outside the list, the request passes (Decision 7). The check follows the tool-shape check (malformed `tools` for an unlisted model gives `invalid_parameter`).
  - **Check order.** `n=2` with valid `tools` gives `unsupported_parameter` `n` first. Malformed `tools` with a bad `temperature` gives the `tools` error first. A bad `tool_choice` with a D6 violation gives the `tool_choice` error first.
  - **T6.** A canary in a tool name, a description, a `tool_choice` name, a parameters value, a tool turn's content and history `arguments`: no refusal's message or `param` contains it, and `__cause__ is None` for the parameter refusals.
  - **Groups.** `TOOL_PARAMS == {"tools", "tool_choice", "parallel_tool_calls"}`. The flag-on groups (`FORWARDED`, `REJECTED_UNLESS_DEFAULT.keys() - TOOL_PARAMS`, `TOOL_PARAMS`, `_STRUCTURAL`) are pairwise disjoint. `TOOL_PARAMS - {"parallel_tool_calls"} <= REJECTED_UNLESS_DEFAULT.keys()`. `"parallel_tool_calls" not in ChatCompletionRequest.model_fields`. `functions` and `function_call` are in `REJECTED_UNLESS_DEFAULT` and not in `TOOL_PARAMS` (D10).
  - **Flag on accepts everything flag off accepts, with an equal `V1Call`.** Use the seeded `_SEEDS` generator style from `test_v1_translate_request.py:357-399`, re-implemented locally (do not import private generators), plus a fixed list of PRD-015 accepted bodies: defaults `tools: []` and `tool_choice: "none"`, `parallel_tool_calls: true` alone, ignored keys, `stream_options`. Wherever `translate_request(body)` succeeds, `translate_request(body, tools_enabled=True)` returns an equal `V1Call`.
  - **The flag-on property guard.** A seeded generator that includes tool turns, assistant `tool_calls` (valid and invalid) and null fields: every message list the flag-on path accepts passes `query_pipeline._validate_conversation`, and the generator is non-degenerate (at least 25% accepted and at least 25% refused).
  - **Defaults are flag off.** `translate_request(body)` equals `translate_request(body, tools_enabled=False, tool_models=["openai/gpt-4o"])` for a tools body. Both raise the same `(code, param, message)`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_v1_tools.py -q`

### Task 7: `tests/test_v1_tools.py`: router and pipeline end to end (TestClient + DB)

- **File**: `tests/test_v1_tools.py`
- **Action**: UPDATE (same new file, second section)
- **Implement**: Copy the router suite's setup locally: a `client`, `_AUTH_HEADERS`, a `temp_db` override inserting the `user`-role user, and `_count_audit_rows` (`tests/test_v1_router.py:39-108`). Do not import from `test_v1_router` (it is a test module). Add a `_ToolUpstream` stub, `__call__(self, messages, model="gpt-4", api_key=None, *, tools=None)`, which records both and returns a configurable `OpenRouterResult`. Add a tools-aware twin of `_upstream_over` (real `call_openrouter` over `httpx.MockTransport`, accepting `params=None, tools=None`). Use `monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", ...)` / `"V1_TOOL_MODELS"` in every test, and `monkeypatch.setattr(query_pipeline, "redact", _mask_nothing)` where content must arrive verbatim. Tests:
  - **AC1 flag-off regression set.** Pin `V1_TOOLS_ENABLED=False` explicitly. Parametrize over representative PRD-015 refusals: `tools=[tool]`, `tool_choice="auto"`, `functions=[...]`, `function_call="auto"`, a `tool` role turn, a `tool_calls` key on an assistant turn, `tool_calls: null` (key presence still refused when off), a last assistant turn, and `tools` plus a tool turn. Each must be status 400 and give exactly the PRD-015 error body (`message`, `type`, `param`, `code`, `harness: None`), with `x-should-retry: false`, no row and the upstream not called. Also with the flag off, `parallel_tool_calls: true` on a clean request is 200 and the row's `ignored_params` contains `parallel_tool_calls`. Also with the flag off and `V1_TOOL_MODELS` set to another allowlisted model, the result is still the plain PRD-015 refusal (the list is not consulted). Check that `V1_TOOL_MODELS` must name `MODEL_ALLOWLIST` entries (startup validator `app/config.py:682-706`). Setting the attribute with monkeypatch skips that validator, but use an allowlisted name anyway.
  - **AC5 full flag-on request (JSON).** Send the Section 10 request: `tools`, `tool_choice: "auto"`, `user` → assistant(`content: null`, `tool_calls`) → `tool`, with `_MODEL` (allowlisted), through the real `call_openrouter` over a capturing transport. Assert:
    - status 200, a `chat.completion` with the text content;
    - the captured payload's `tools` equals the sent list, and `tool_choice == "auto"`;
    - `"parallel_tool_calls" not in payload` (it was not sent);
    - `payload["messages"]` equals the sent messages, with the assistant turn `content: null` and `tool_calls` identical and the tool turn `{role, tool_call_id, content}` identical;
    - each `arguments` string equals the sent string byte for byte. Use a whitespace-odd Cline-style string such as `'{"path": "a.py" ,"n":1}'`;
    - one row with `ingress='v1'` and `ignored_params` NULL.
  - **AC2 router to pipeline (stub).** With `_ToolUpstream`, `stub.calls[0]["tools"] == ToolParams(tools=sent, tool_choice=..., parallel_tool_calls=True)`. For a flag-on request without `tools` (or with `tools: []` plus history), the three-argument `_Upstream`-style stub (no `tools` kwarg) still works, which proves `tools=` is not passed when None.
  - **AC3 through the router.** One D6 violation and one malformed `tools` item: 400, the exact code, param and message, no row, the upstream not called.
  - **AC4 through the router.** `V1_TOOL_MODELS` set to another allowlisted model gives 400 `tools_not_supported`, `param: "tools"`, the exact message and no row. This holds for an `admin`-role token too (insert an admin user, or use the role the suite uses), which shows that no role bypasses the check.
  - **Flag read per request.** Off gives 400 for a tools body. Flip with monkeypatch in the same test, and on gives 200 for the same body.
  - **Streamed (OpenCode shape).** `stream: true`, `stream_options.include_usage`, `tools: []` plus tool history: 200 `text/event-stream`, the content chunk carries the stub's text, the stub got no `tools`, and the history arrived.
  - **Interim T1 pin.** The stub returns `OpenRouterResult(response="", tool_calls=(ToolCallSpec("call_2", "bash", '{"command":"rm -rf /"}'),), finish_reason="tool_calls", ...)` to a flag-on tools request. JSON: 200, `choices[0].message.content == ""`, `finish_reason == "stop"`, no `tool_calls` key anywhere in the body, and `"call_2"`, `"rm -rf"` and `"bash"` do not appear in `response.text`. Repeat for the streamed form (no chunk carries them). Docstring: "Interim (STORY-008): until STORY-010/011, the result translator reads `response` only, so no undecided call is released (T1). STORY-011 replaces this test with the release shapes."
  - **D17.** The flag on does not change `/query`: the router never passes `tools` there. Cover this with one `test_query_pipeline_tools.py` assertion in Task 8. No `/query` test file is edited.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_v1_tools.py -q`

### Task 8: Pipeline step 7 tests

- **File**: `tests/test_query_pipeline_tools.py`
- **Action**: UPDATE (append a `# --- STORY-008: step 7 forwards tools= only when set ---` section, and add one sentence to the module docstring)
- **Implement**:
  - `run_conversation(..., tools=ToolParams([...], "auto", True))` with a stub `(messages, model, api_key, *, tools=None)` records the identical object.
  - With `params` and `tools` both set, both arrive.
  - Without `tools`, the existing three-argument `_fake_call_openrouter` (`:80`) is called successfully (no `TypeError`).
  - `run_query` never passes `tools`: a stub without the kwarg works, and an AST or signature check confirms `run_query` has no `tools` parameter.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_query_pipeline_tools.py tests/test_query_pipeline_run_conversation.py -q`

### Task 9: Router wiring

- **File**: `app/routers/v1.py`
- **Action**: UPDATE
- **Implement**:
  - At `:278`, change the call to `call = translate_request(body, tools_enabled=settings.V1_TOOLS_ENABLED, tool_models=settings.v1_tool_models_list)`. Comment: read per request, so a flipped flag takes effect without a restart and tests monkeypatch it (PRD-017 Section 6.7). The translator reads no settings.
  - In `run_in_pipeline(run_conversation, ...)` (`:287-302`), add `tools=call.tools` with a comment: None unless the flag is on and tools were sent, and `run_conversation` forwards it to step 7 only when set.
  - Do **not** read `upstream.result.tool_calls` anywhere (T1). `translate_result` is unchanged.
  - Add one sentence to the module docstring (`:13-22`): PRD-017 STORY-008 passes the tool request through under `V1_TOOLS_ENABLED`, and release is STORY-010/011.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`, then Task 7's file.

### Task 10: Config comment

- **File**: `app/config.py`
- **Action**: UPDATE (comment only, `:375-378`)
- **Implement**: Reword "Nothing reads these yet -- STORY-008 ... and STORY-010 ... read them" to say that the `/v1` router reads both per request and passes them to the translator (STORY-008), and that step 7c (STORY-010) will read them too. No code change.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_config.py -q`

---

## End-to-End Tests

- [ ] TestClient, flag on: the Section 10 request reaches a capturing transport with `tools`, `tool_choice` and the tool history byte-identical, and the response is a text `chat.completion` (Task 7, AC5).
- [ ] TestClient, flag off: the representative PRD-015 refusal set returns byte-identical bodies with no row (Task 7, AC1).
- [ ] TestClient, flag on, streamed OpenCode shape (`tools: []` plus history): 200 SSE (Task 7).
- [ ] TestClient, flag on, the upstream returns `tool_calls`: no call in the JSON or SSE body (Task 7, interim T1).
- No live client run in this story: OpenCode and Cline E2E are STORY-016/017.

---

## Validation

Targeted run only (brief: the full suite is the orchestrator's), as one foreground pytest call:

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest \
  tests/test_v1_tools.py \
  tests/test_v1_translate_request.py tests/test_v1_router.py \
  tests/test_v1_translate_result.py tests/test_v1_errors.py tests/test_v1_sse.py \
  tests/test_v1_query_isolation.py tests/test_e2e_live.py \
  tests/test_query_pipeline_tools.py tests/test_query_pipeline_run_conversation.py \
  tests/test_query_pipeline_audit_fields.py tests/test_config.py \
  tests/test_query_outcomes_regression.py tests/test_untouched_app.py -q
```

`test_v1_errors.py`, `test_v1_sse.py` and `test_v1_query_isolation.py` are in the run because they go through `translate_request` and the router, and they must stay green **unedited**. `test_query_pipeline_audit_fields.py` scans the `run_conversation` call sites. `test_pii_redaction_integration.py` is not needed, because no test is renamed or removed. Record the exact counts and write "Full suite: deferred to orchestrator (user decision)".

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| A flag-off string or order drifts | Flag-off code paths are guarded, not rewritten. The defaults are False. Every existing `test_v1_*` runs unedited (apart from Decision 13). The Task 7 regression set compares exact bodies. The Task 6 property test checks that the defaults equal an explicit off. |
| An SDK echo (`function_call: None`, `tool_calls: None`) is refused with the flag on | Decision 6, with tests. |
| `tools` rewritten in transit (a copy, a filter, a re-serialization) | An `is` identity assertion on `ToolParams.tools`, plus a wire-level equality check through the real client. |
| A three-argument stub breaks on `tools=` | Passed only when set (Task 1), with a test (Task 8). The router's `_Upstream` already forwards `**kwargs` (`v1.py:132-136`). |
| Upstream `tool_calls` leak to the client before release exists | `translate_result` is untouched. The interim pin test runs in JSON and SSE. |
| OpenCode sees an empty completion when the model calls a tool, with the flag on | It is interim by design (T1). The flag defaults off, and STORY-010/011 complete the release. Say so in the report. |
| Story size | Estimate: about 150 lines in the translator, about 15 in the router and pipeline, and about 60-80 test cases. One implementer can do it in the order above. If the orchestrator prefers, the split is clean: **008a** is Tasks 2-6 (pure layer, no DB); **008b** is Tasks 1, 7-10 (pipeline and router wiring plus the TestClient tests). 008b depends on 008a. |

## Open questions (for the orchestrator)

1. Decision 13: editing one structural assertion in `tests/test_v1_translate_request.py` (the `V1Call` field set) versus the fallback, a separate `translate_tools`.
2. Decision 7: should tool **history** without `tools` (OpenCode's `tools: []`) for a model outside a non-empty `V1_TOOL_MODELS` also be refused? The plan follows D16's wording ("a `tools` request") and lets it through.
3. Decision 3: `parallel_tool_calls` with no tools to forward is recorded in `ignored_params`, not refused. OpenAI itself rejects it without `tools`. Recording it keeps flag on a superset of flag off.

---

## Acceptance Criteria

(Copied from story `STORY-008`)

- [ ] Given `V1_TOOLS_ENABLED=false`, when any PRD-015 request (with or without tools) is sent, then the response is exactly PRD-015's: every existing `tools_not_supported` test in `tests/test_v1_translate_request.py` and `tests/test_v1_router.py` passes **unchanged**. (Task 2/4 guard; Task 7 regression set; Task 6 defaults-equal-off.)
- [ ] Given the flag on, when a request carries `tools`, `tool_choice` and `parallel_tool_calls`, then `V1Call.tools` is a `ToolParams` with the values as sent, and the router passes it to `run_conversation(..., tools=...)`, which passes it to `call_openrouter` at step 7 only when set; `functions` / `function_call` stay `tools_not_supported` (D10); `parallel_tool_calls` is no longer in `ignored_params` (D11). (Tasks 1, 3, 4, 9; tests in Tasks 6, 7, 8.)
- [ ] Given the flag on, when assistant `tool_calls` and `tool` turns arrive in `messages`, then they are normalized (STORY-003) and the D6 shape rules are checked with the shared helper (STORY-005); each violation, each malformed `tools` item or `tool_choice` (including a named function absent from `tools`) and each non-bool `parallel_tool_calls` is a 400 whose `code` and `param` follow PRD-017 Section 10's table; the last turn may be `tool`. (Tasks 2, 3; tests in Tasks 6, 7.)
- [ ] Given `V1_TOOL_MODELS` set and a `tools` request for a model outside it, when translated, then 400 `tools_not_supported`, `param: "tools"`, message `model is not enabled for tool calling (V1_TOOL_MODELS)` (D16); with the list empty, any permitted model passes. (Task 4; tests in Tasks 6, 7, admin included.)
- [ ] Given a full flag-on request through `TestClient` with a stub `call_openrouter` that returns text, when it runs, then the stub received the tools and the tool history byte for byte, and the response is a normal text completion. (Task 7, wire-level capture; interim T1 pin.)
- [ ] All tasks completed
- [ ] Backend imports without error (`from app.main import app`)
- [ ] Follows existing patterns (purity, location-and-rule messages, passed-only-when-set keyword)
