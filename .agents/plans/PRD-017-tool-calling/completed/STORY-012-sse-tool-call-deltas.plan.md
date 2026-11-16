---
story: STORY-012
prd: PRD-017
slug: sse-tool-call-deltas
title: Buffered SSE tool_calls deltas in one burst
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-017-tool-calling
created: 2026-11-16
---

# Plan: Buffered SSE tool_calls deltas in one burst

## Summary

`v1_sse.completion_events` (`app/services/v1_sse.py:45-70`) already renders every streamed
success from the `ChatCompletion` that `translate_result` built, and since STORY-011 that
completion carries the released calls (`message.tool_calls`), `content: null` and
`finish_reason: "tool_calls"`. This story extends the renderer, not the router. Between the
role chunk and the finish chunk it adds one chunk per released call, each with the whole
`arguments` string (`{"index": i, "id", "type": "function", "function": {"name", "arguments"}}`).
The role chunk carries `content: null` when the completion's content is `null`.
`v1_schemas.ChunkDelta` gains `tool_calls`. Its serializer moves from "drop `None` values" to
"drop keys that were not set", which is STORY-011's `AssistantMessage` rule
(`v1_schemas.py:134-139`). So an explicit `content=None` stays `null`, while the finish chunk's
`ChunkDelta()` stays `{}` and every text-only chunk is byte-identical. The router needs no code
change. Fail-closed (`ActionAuditError`) already becomes one `internal_error` event before any
completion exists (`app/routers/v1.py:208-209, 264-281`), and an all-denied completion has
`tool_calls: None`, so it renders no delta. The interim pin
`test_interim_streamed_allowed_call_is_not_yet_streamed` is replaced by the real shape, and the
OpenAI SDK 3.40.0 `ChatCompletionStreamState` proves the accumulated message equals the
non-streamed one.

## User Story

As an integrating developer whose agent streams by default
I want a streamed `/v1` response to carry the released tool calls as standard deltas
So that my client accumulates them exactly as it would from a provider

## Story Reference

- Story file: `.agents/stories/PRD-017-tool-calling/STORY-012-sse-tool-call-deltas.md`
- PRD: `.agents/PRDs/PRD-017-tool-calling/PRD.md` (Section 6.1 lines 140-159; Section 6.6 lines 230-261, the SSE block at 250-261; T1 line 362; Risk 2 line 496; Section 10 lines 397-410, as amended by STORY-011)
- Survey: `.agents/spikes/PRD-017-tool-calling/client-survey.md` lines 47-51 and 106

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/models/v1_schemas.py`, `app/services/v1_sse.py`, `app/services/v1_translate.py` (docstring only), `tests/test_v1_tools.py`, `tests/test_v1_schemas.py` |
| Story | STORY-012 |
| PRD | PRD-017 |
| Epic Branch | `epic/PRD-017-tool-calling` (commit directly on this branch) |

---

## Key decisions (read first)

**DD-1. `ChunkDelta` drops *unset* keys, not `None` values.**
Today `_drop_unset` (`v1_schemas.py:198-202`) drops every `None` value, which would also drop
the role chunk's required `content: null`. Three options were weighed:

1. Drop keys not in `model_fields_set`, i.e. explicit-set tracking. This is STORY-011's
   `AssistantMessage._drop_unset_tool_calls` rule (`v1_schemas.py:134-139`), applied to the
   whole delta. **Chosen.**
2. Keep "drop `None`" but special-case `content` when `role` is set. Rejected because it ties
   the schema to the renderer's chunk order.
3. Build the role chunk as a raw dict in `v1_sse`. Rejected because it bypasses the shared
   wire schema the module docstring promises (`v1_schemas.py:3-7`).

Why option 1 leaves every existing byte unchanged:
- The finish chunk is `ChunkDelta()`, with nothing set, so it is still `{}`.
- The text-only role chunk is `ChunkDelta(role="assistant", content=<str>)`, with both set and
  both non-`None`, so it is unchanged.
- `QuerySuccessResponse.response` is `str` (`app/models/schemas.py:79`), and `translate_result`
  sets `content=None` only when calls are released and there is no text
  (`v1_translate.py:602`). So a text-only completion never reaches the renderer with
  `content=None`.
- The only construction sites are `v1_sse.py:60-65` and `tests/test_v1_schemas.py:158,162`.

The serializer keeps its name `_drop_unset`, which now describes it exactly. Its comment cites
PRD-017 DD-1 (this plan) and Section 6.6.

**DD-2. A tool-call delta is a new `ChunkToolCall` model, and `ToolCallFunction` is reused.**
The field order is `index, id, type, function`, which is PRD Section 6.6's key order
(line 254). `function` reuses `ToolCallFunction` (`v1_schemas.py:104-107`), so `arguments` has
one definition: the model's string, never parsed or re-serialized (D13). It cannot subclass
`CompletionToolCall` because the `index` field comes first.

**DD-3. Calls are rendered only from `choice.message.tool_calls`, and `None` or absent means no
delta.** `completion_events` iterates `choice.message.tool_calls or []`:
- A text-only completion has the key absent, which reads as `None`, so it renders no delta
  (AC2).
- An all-denied completion has an explicit `None` (Section 10), so it renders no delta and its
  role chunk carries the note (AC4).

The renderer reads the `ChatCompletion` only. The router and `upstream.result.tool_calls` are
untouched (T1, the brief's rule, and `test_router_never_reads_raw_upstream_tool_calls`). The
calls are released by 7c, which ran before the outcome existed. Buffering is what keeps them
from leaving early: `stream` sends nothing but keep-alives until the pipeline is done
(`v1_sse.py:111-127`).

**DD-4. The event order stays PRD-015's: role, tool-call chunks, finish, usage (only with
`include_usage`), `[DONE]`.** The orchestrator's question was whether OpenCode rejects the
usage chunk after the finish chunk. It does not. The survey (`client-survey.md:51`) read
OpenCode 2.0.10's `openai-chat.ts#L985-L997`: content **or tool deltas** after a
`finish_reason` are an error, but *"A usage-only chunk after the finish is fine"*. The recorded
Groq fixture itself sends usage after the finish (`client-survey.md:49`). The hand-off
(`client-survey.md:106`) asks for exactly this: finish last among the deltas, and usage only
after it. Every tool-call delta comes before the finish chunk, which satisfies OpenCode's rule.
No reordering is needed. This finding is recorded in STORY-016's Technical Notes (done by this
planner) so the live E2E confirms it.

**DD-5. `tests/test_v1_sse.py` stays unedited (AC2).** All new SSE tests go in
`tests/test_v1_tools.py`, and the schema-level tests go in `tests/test_v1_schemas.py`, which is
the test file of the changed schema module. `test_v1_sse.py` runs unmodified as AC2's
regression proof.

**DD-6. The interim pin is replaced, not kept.** `test_interim_streamed_allowed_call_is_not_yet_streamed`
(`tests/test_v1_tools.py:943-959`) says STORY-012 replaces it. `tests/test_v1_tools.py` is new
in this epic: `git cat-file -e main:tests/test_v1_tools.py` fails. The guard
(`tests/test_pii_redaction_integration.py:525-546`) only diffs files that exist at
`merge-base main HEAD`, so this rename needs **no** `_DELIBERATELY_SUPERSEDED_TESTS` entry.
Running that guard file once confirms it.

**DD-7. The SDK tests follow the suite's convention, `pytest.importorskip("openai")`.**
Precedents are `tests/test_v1_schemas.py:342,357,455,477` and `tests/test_v1_tools.py:1006`.
`openai==3.40.0` is installed in `.venv`, so they must **run**. The implementer runs pytest with
`-rs` and reports that none of the new tests skipped. The accumulator is
`openai.lib.streaming.chat.ChatCompletionStreamState`: `handle_chunk(ChatCompletionChunk)`, then
`get_final_completion()` (`.venv/Lib/site-packages/openai/lib/streaming/chat/_completions.py:292-350`,
exported at `.../chat/__init__.py:24`). The planner verified the exact Section 6.6 sequence
against it in a scratch probe, with two calls, `content: null`, a usage chunk with
`choices: []`, and escape-heavy arguments. The result: `content is None`,
`finish_reason == "tool_calls"`, ids, names and arguments byte-equal, and usage set. The
accumulated `tool_calls` also carry `index` and `function.parsed_arguments`, so compare
`(id, type, function.name, function.arguments)` tuples, not whole model dumps.

---

## Skills In Use

`.agents/skills/` holds only `frontend-design` (visual UI design). It does not apply because
this story has no UI. The story's `skills: []` agrees.

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | No UI; backend wire format only | n/a |

---

## Patterns to Follow

| Category | File:Lines | Pattern |
|----------|------------|---------|
| SCHEMAS | `app/models/v1_schemas.py:121-139` | `AssistantMessage`: `@model_serializer(mode="wrap")` dropping a key when `not in self.model_fields_set` (explicit `None` kept) |
| SCHEMAS | `app/models/v1_schemas.py:104-118` | `ToolCallFunction` / `CompletionToolCall`: `type: Literal["function"] = "function"`, `arguments: str` with the D13 comment |
| SCHEMAS | `app/models/v1_schemas.py:194-232` | `ChunkDelta` / `ChunkChoice` / `ChatCompletionChunk` serializers with Section-cited comments |
| RENDERER | `app/services/v1_sse.py:45-70` | `completion_events`: local `chunk(**fields)` factory, `data_event` per chunk, usage only with `include_usage`, `DONE` last |
| ERRORS | `app/routers/v1.py:198-212, 254-281` | `ActionAuditError` → `internal_error`; a post-commit fault is one `error_event`, no `[DONE]` |
| TRANSLATION | `app/services/v1_translate.py:585-604` | the release is read from `result.tool_outcome`; `content = None if released and not result.response` |
| TESTS | `tests/test_v1_sse.py:134-147, 185-210` | `_events` parser; exact event lists as `[("data", dict), ..., ("data", "[DONE]")]` |
| TESTS | `tests/test_v1_tools.py:816-821, 895-910, 1004-1014, 1088-1102` | `_data_events`; streamed denied twin; SDK round trip with `importorskip`; audit-failure SSE event |
| TESTS | `tests/test_v1_schemas.py:147-173, 176-178, 355-364` | `_chunk` builder, `_all_dumps` (python / json / JSON-string agree), SDK validates each chunk |

### Naming / schema (mirror)
```python
# SOURCE: app/models/v1_schemas.py:110-139
class CompletionToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: ToolCallFunction

class AssistantMessage(BaseModel):
    ...
    @model_serializer(mode="wrap")
    def _drop_unset_tool_calls(self, handler):
        data = handler(self)
        if "tool_calls" not in self.model_fields_set:
            data.pop("tool_calls", None)
        return data
```

### Renderer (extend)
```python
# SOURCE: app/services/v1_sse.py:59-70
events = [
    data_event(chunk(choices=[ChunkChoice(
        delta=ChunkDelta(role="assistant", content=choice.message.content)
    )])),
    data_event(chunk(choices=[ChunkChoice(
        delta=ChunkDelta(), finish_reason=choice.finish_reason
    )])),
]
if include_usage:
    events.append(data_event(chunk(choices=[], usage=completion.usage)))
events.append(DONE)
```

### Error handling (unchanged, relied on)
```python
# SOURCE: app/routers/v1.py:208-209 and 271-281
if isinstance(exc, (DuplicateCheckError, UsageLimitError, ActionAuditError)):
    return INTERNAL_ERROR
...
if isinstance(outcome, ChatCompletion):
    return v1_sse.completion_events(outcome, include_usage)
...
return [v1_sse.error_event(_error_body(...))]
```

### Tests (mirror)
```python
# SOURCE: tests/test_v1_sse.py:199-202
def test_completion_events_without_usage():
    events = _events("".join(v1_sse.completion_events(_completion(), include_usage=False)))
    assert events == [("data", _CONTENT_CHUNK), ("data", _FINISH_CHUNK), ("data", "[DONE]")]
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/models/v1_schemas.py` | UPDATE | `ChunkToolCall`; `ChunkDelta.tool_calls`; `_drop_unset` by set-ness (DD-1); docstring/comment updates |
| `app/services/v1_sse.py` | UPDATE | `completion_events` emits one tool-call chunk per released call; role chunk `content: null`; docstrings |
| `app/services/v1_translate.py` | UPDATE (docstring only) | `translate_result` line 583 "Streamed deltas are STORY-012's." → points at `v1_sse.completion_events` |
| `tests/test_v1_schemas.py` | UPDATE (additions only) | role chunk with `content: null`, tool-call chunk shape, SDK validates them |
| `tests/test_v1_tools.py` | UPDATE | replace the interim pin; pure renderer tests (AC1); SDK accumulator (AC3); text-only flag on = off stream (AC2); all-denied exact sequence (AC4); mixed stream; module docstring |
| `.agents/stories/PRD-017-tool-calling/STORY-016-e2e-opencode.md` | UPDATE (planner, done) | DD-4 finding recorded as a Technical Note |

Not changed: `app/routers/v1.py` (its docstring at line 26 already says "STORY-012 streams them"),
`tests/test_v1_sse.py` (AC2, DD-5), `app/services/query_pipeline.py`, `app/services/tool_release.py`.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Wire shape: `ChunkToolCall`, `ChunkDelta.tool_calls`, set-based dropping

- **File**: `app/models/v1_schemas.py`
- **Action**: UPDATE
- **Implement**:
  - After `ChatCompletion` (or next to `ChunkDelta`), add the model:
    ```python
    class ChunkToolCall(BaseModel):
        """One released call as a stream delta (PRD-017 Section 6.6).

        One per call, carrying the whole `arguments` string: a client
        concatenates fragments per `index`, and one fragment is a complete
        one (Risk 2). The OpenAI SDK's `ChoiceDeltaToolCall` shape.
        """
        index: int
        id: str
        type: Literal["function"] = "function"
        function: ToolCallFunction
    ```
  - `ChunkDelta`: add `tool_calls: Optional[List[ChunkToolCall]] = None`. Replace the body of
    `_drop_unset` with `data = handler(self); return {key: value for key, value in data.items() if key in self.model_fields_set}`.
    Rewrite the comment: Section 7.6's finish chunk delta is `{}` (nothing set), and the
    role chunk keeps an explicit `content: null` when calls are released and there is no text
    (PRD-017 Section 6.6, STORY-012 DD-1); the same set-ness rule as `AssistantMessage`.
  - `ChunkChoice.finish_reason` comment: "`null` on the role and tool-call chunks, the reason on the finish chunk."
  - `ChatCompletionChunk` docstring: "Role, tool-call and finish chunks carry no `usage` key".
  - Module docstring (lines 9-15): add that a chunk delta omits every key it was not given,
    so the finish chunk's `{}` and the role chunk's `content: null` both hold (PRD-017).
  - Keep the module pure: no new imports beyond what is there.
- **Mirror**: `app/models/v1_schemas.py:121-139` (set-ness serializer), `:104-118`
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: Renderer: tool-call chunks between the role and the finish chunk

- **File**: `app/services/v1_sse.py`
- **Action**: UPDATE
- **Implement**:
  - Import `ChunkToolCall` from `app.models.v1_schemas` (alphabetical in the existing import block).
  - In `completion_events`, build the list as: role chunk
    `ChunkDelta(role="assistant", content=choice.message.content)`. This is unchanged code: an
    explicit `None` now serializes as `null` (DD-1). Then, for
    `index, call in enumerate(choice.message.tool_calls or [])`, one chunk
    `ChunkChoice(delta=ChunkDelta(tool_calls=[ChunkToolCall(index=index, id=call.id, function=call.function)]))`.
    Then the finish chunk, the usage chunk when `include_usage`, and `DONE`, as today.
  - Pass `call.function` (the `ToolCallFunction` instance) or rebuild it from `name`/`arguments`.
    Either way the `arguments` string is copied as is, with no `json.loads`/`dumps` (D13).
  - Docstring of `completion_events`: add PRD-017 Section 6.6. Released calls (the 7c release
    `translate_result` put on the message, never the upstream's, T1) follow the role chunk,
    one chunk each with its whole `arguments`. `tool_calls` absent (text-only) or `None` (every
    call denied) renders none, so those streams are PRD-015's. The finish chunk stays the last
    delta: OpenCode errors on a delta after a `finish_reason`, and the usage chunk after it is
    fine (survey).
  - Module docstring (lines 7-10): "one role/content chunk, one chunk per released tool call (PRD-017), one finish chunk, ...".
  - No settings, no logging, no I/O (pure module rule).
- **Mirror**: `app/services/v1_sse.py:45-70`
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`; then `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_v1_sse.py -q` must pass **unedited** (AC2 early check).

### Task 3: Docstring pointer in the translator

- **File**: `app/services/v1_translate.py`
- **Action**: UPDATE (docstring only)
- **Implement**: in `translate_result`'s docstring (line 583), replace "Streamed deltas are
  STORY-012's." with a sentence saying the stream renders the same message through
  `v1_sse.completion_events` (role chunk, one delta per released call, finish chunk), so both
  shapes follow one release. No code change.
- **Validate**: import check as above.

### Task 4: Schema tests for the new chunk shapes

- **File**: `tests/test_v1_schemas.py`
- **Action**: UPDATE (append a `# --- PRD-017 STORY-012: tool-call deltas ---` section; edit nothing existing)
- **Implement**:
  - Import `ChunkToolCall`.
  - `test_role_chunk_keeps_an_explicit_null_content`: `_chunk([ChunkChoice(delta=ChunkDelta(role="assistant", content=None))])`. For every `_all_dumps` value, `choices[0]["delta"] == {"role": "assistant", "content": None}`.
  - `test_tool_call_chunk_matches_section_6_6`: a delta with
    `ChunkToolCall(index=1, id="call_2", function=ToolCallFunction(name="bash", arguments=_ARGS_2))`.
    Assert it equals `{"tool_calls": [{"index": 1, "id": "call_2", "type": "function", "function": {"name": "bash", "arguments": _ARGS_2}}]}`
    in all three dumps. Also assert the key order of `json.loads(model_dump_json())` is
    `["index", "id", "type", "function"]`, and that `json.dumps(_ARGS_1)` appears in the JSON
    text of a chunk carrying `_ARGS_1` (D13).
  - `test_unset_delta_keys_are_dropped`: `ChunkDelta()` → `{}`; `ChunkDelta(role="assistant", content="x")` → no `tool_calls` key.
  - `test_openai_sdk_validates_the_tool_call_chunk` (`importorskip`): `openai.types.chat.ChatCompletionChunk.model_validate(...)`.
    Then `delta.tool_calls[0].index`, `.id`, `.function.name` and `.function.arguments` are
    equal to the inputs, and the role chunk's `delta.content is None`.
- **Mirror**: `tests/test_v1_schemas.py:147-173, 279-282, 355-364, 400-414`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_v1_schemas.py -q -rs`

### Task 5: Router and renderer tests; replace the interim pin

- **File**: `tests/test_v1_tools.py`
- **Action**: UPDATE
- **Implement**:
  - Module docstring (lines 12-15): STORY-011 releases the allowed calls on the non-streamed
    body and STORY-012 streams them as one delta per call (Section 6.6). Drop the
    `test_interim_streamed_*` sentence.
  - Add a pure section (no DB) `# --- STORY-012: streamed tool-call deltas ---`, placed after
    the STORY-011 section. It needs an `_events`-style parser that keeps the `[DONE]` marker.
    Add a local `_sse(text)` returning the data payloads including the `"[DONE]"` string, or
    reuse `_data_events` plus `text.endswith("data: [DONE]\n\n")`. Do not import from
    `test_v1_sse.py`. Build a completion with
    `ChatCompletion(... choices=[Choice(message=AssistantMessage(content=None, tool_calls=[CompletionToolCall(...) x2]), finish_reason="tool_calls")], usage=..., harness=HarnessCompletionInfo(audit_id=42, actions=[...]))`.
    1. **AC1** `test_completion_events_stream_two_released_calls` (parametrize `include_usage` True/False).
       The data payloads are exactly:
       - role `{"index":0,"delta":{"role":"assistant","content":None},"finish_reason":None}`
       - call 0 `{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"read","arguments":A1}}]},"finish_reason":None}`
       - call 1, the same shape with `index: 1`
       - finish `{"index":0,"delta":{},"finish_reason":"tool_calls"}`
       - usage `{"choices": [], "usage": {...}}`, only when `include_usage`
       - `[DONE]`

       Every chunk has the completion's `id`/`created`/`model`. No chunk has a `harness` key or
       a `usage` key except the usage chunk. Use escape-heavy `A1 = '{"path":"a\\"b.py"}'` and
       assert `json.dumps(A1)` appears in the raw event text (D13).
    2. **AC3 (pure)** `test_sdk_accumulator_rebuilds_the_non_streamed_message` (`openai = pytest.importorskip("openai")`;
       `from openai.lib.streaming.chat import ChatCompletionStreamState`). Feed every non-`[DONE]`
       payload of `completion_events(completion, include_usage=True)` through
       `state.handle_chunk(openai.types.chat.ChatCompletionChunk.model_validate(payload))`, then
       call `final = state.get_final_completion()`. Parse the non-streamed body with
       `openai.types.chat.ChatCompletion.model_validate(json.loads(completion.model_dump_json()))`.
       Assert `content`, `finish_reason` and the `(id, type, function.name, function.arguments)`
       tuples are equal, and that `final.usage.total_tokens` equals the completion's.
  - Router section:
    3. **Replace** `test_interim_streamed_allowed_call_is_not_yet_streamed` with
       `test_streamed_allowed_call_is_one_delta_then_finish_tool_calls`. It uses the same stub
       (`response=""`, `tool_calls=(_READ_CALL,)`). The data payloads' `choices` are exactly
       `[role(content None)]`, `[tool_call index 0 call_r read '{"path":"src/a.py"}']`,
       `[finish tool_calls]`, and the text ends with `data: [DONE]`. The decision row is
       `allow` against `_only_row().id`, there is no `harness` in any chunk, and
       `json.dumps('{"path":"src/a.py"}')` appears in the text.
    4. **AC3 (router)** `test_streamed_and_plain_tool_responses_accumulate_to_the_same_message`
       (`importorskip`). The stub returns two allowed calls (`_READ_CALL` and
       `ToolCallSpec("call_r2", "read", '{"path":"src/b.py"}')`, both `read` under the
       workspace, as `_READ_CALL` is allowed today). Send the same request twice with
       **different** user prompts (`list the files 1`/`... 2`) so the duplicate check does not
       hold the second. One is `stream=True, stream_options={"include_usage": True}`, the
       other is plain. Accumulate the stream with `ChatCompletionStreamState` and compare with
       `ChatCompletion.model_validate(plain.json())`: content, finish reason, call tuples.
    5. **AC2 (router)** `test_flag_on_text_only_stream_is_the_flag_off_stream`. This mirrors
       `test_flag_on_text_only_body_is_the_flag_off_body` (`:984-1001`) for `stream=True`,
       with and without `include_usage`. Pop `id`/`created` from each data payload, then assert
       the two payload lists are equal and contain no `tool_calls` key. Also assert the raw
       texts are equal once the ids and the `created` values are normalized (e.g. `re.sub`
       over `"id":"chatcmpl-harness-\d+"` and `"created":\d+`), so this is a byte check, not
       only a dict check.
    6. **AC4** `test_streamed_all_denied_is_the_note_then_stop_and_no_delta`. Stub:
       `_calling_upstream()`. The data payloads' `choices` are exactly
       `[{"index":0,"delta":{"role":"assistant","content":<note>},"finish_reason":None}]`,
       `[{"index":0,"delta":{},"finish_reason":"stop"}]`, then `[DONE]`. Assert
       `'"tool_calls"' not in response.text`. This is stricter than the existing
       `test_streamed_denied_call_is_the_note_and_stop` (`:895-910`), which stays as is.
    7. **Mixed stream** `test_streamed_mixed_response_is_text_and_note_then_the_allowed_call`.
       Stub: `response="Reading."`, `tool_calls=(_READ_CALL, _DROP_TABLE)`. The role chunk
       content is `"Reading.\n\n" + note`. There is exactly one tool-call chunk (`index: 0`,
       `call_r`), the finish is `tool_calls`, and the `DROP TABLE` arguments are not in the
       text.
  - AC4's `record()` failure is already proved by
    `test_action_audit_failure_after_stream_commit_is_the_error_event` (`:1088-1102`: one
    `internal_error` data event, no `[DONE]`, no call id or arguments). Leave it unedited. The
    traceability table below cites it.
  - Imports: add `re` if used; `ChatCompletion`, `AssistantMessage`, `Choice`,
    `CompletionToolCall`, `ToolCallFunction`, `HarnessCompletionInfo`, `Usage` from
    `app.models.v1_schemas`; `from app.services import v1_sse`.
  - Keep `_assert_no_call_released` and the existing streamed-denied tests unchanged. Any
    pre-existing assertion you must touch gets a comment citing PRD-017 STORY-012 and the DD.
    None is expected.
- **Mirror**: `tests/test_v1_tools.py:913-941` (released call, JSON), `:984-1001` (flag on = off), `:1004-1014` (SDK)
- **Validate**: see Validation below.

### Task 6: Targeted run (one pytest process, foreground)

- **Command**:
  `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_v1_tools.py tests/test_v1_schemas.py tests/test_v1_sse.py tests/test_v1_translate_result.py tests/test_pii_redaction_integration.py tests/test_untouched_app.py -q -rs`
  - `test_v1_sse.py`: AC2. It must pass with zero diffs to the file (`git diff --stat tests/test_v1_sse.py` empty).
  - `test_v1_translate_result.py`: `v1_translate.py` is touched, even though only its docstring changes.
  - `test_pii_redaction_integration.py`: a test was renamed (DD-6). It confirms no registration is needed.
  - `test_untouched_app.py`: app files touched.
  - Record exact pass/fail/skip counts. `-rs` must show no skip among the STORY-012 tests.
  - If many `db` tests error at fixture setup: `docker restart harness-libsql-dev`, rerun.
  - Full suite: deferred to orchestrator (user decision).

---

## End-to-End Tests

- [ ] In-process: the router's streamed tool-call response, accumulated by the installed
  `openai` 3.40.0 `ChatCompletionStreamState`, equals the non-streamed completion (Task 5.4).
- [ ] Live clients (OpenCode / Cline) are STORY-016 / STORY-017, not this story (Risk 2). DD-4's
  usage-after-finish finding is recorded in STORY-016 for live confirmation.

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_v1_tools.py tests/test_v1_schemas.py tests/test_v1_sse.py tests/test_v1_translate_result.py tests/test_pii_redaction_integration.py tests/test_untouched_app.py -q -rs
git diff --stat HEAD -- tests/test_v1_sse.py   # must print nothing before the commit (AC2)
```

No `chat_ui/` change, so there is no chat UI probe. There is no frontend lint in this repo.

---

## Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| The set-ness rule changes a text-only chunk | Proven by `test_v1_sse.py` and `test_v1_schemas.py`'s `_CHUNK_CASES` running unedited, plus Task 5.5's normalized byte comparison flag on = off |
| A call leaks into a stream before its decision (T1) | The renderer reads only the `ChatCompletion` built from `tool_outcome`. `stream` renders only after the pipeline is done, and `test_router_never_reads_raw_upstream_tool_calls` stays green |
| An all-denied stream gains a `tool_calls` key | DD-3: `tool_calls or []`. Task 5.6 and the existing `:895-910`, `:1050` assertions check it |
| `record()` fails after commit and calls go out | `ActionAuditError` is raised before `translate_result`, so there is no `ChatCompletion` and therefore no delta. `:1088-1102` pins one error event, no `[DONE]` |
| The SDK accumulator adds fields (`index`, `parsed_arguments`) | Compare tuples, not dumps (DD-7) |
| A duplicate verdict on the second router request (AC3) | Different prompts per request, as `test_v1_sse.py:473-475` does |
| OpenCode rejects the usage chunk after the finish | Survey says it is fine (DD-4). STORY-016 verifies it live. The order is not changed |

---

## Acceptance Criteria

(Copied from story `STORY-012`, with coverage)

- [ ] AC1: Two released calls, no content → role chunk `{"role":"assistant","content":null}`, one chunk per call with the whole `arguments`, finish `tool_calls`, usage only with `include_usage`, `[DONE]`. **Covered by** Task 2 + `test_completion_events_stream_two_released_calls` (both `include_usage` values) and the router pin `test_streamed_allowed_call_is_one_delta_then_finish_tool_calls`; schema-level by Task 4.
- [ ] AC2: Text-only completion → events byte-identical to PRD-015's (`tests/test_v1_sse.py` unchanged). **Covered by** `tests/test_v1_sse.py` run unedited, `test_v1_schemas.py::test_chunks_match_section_7_6` unedited, and `test_flag_on_text_only_stream_is_the_flag_off_stream`.
- [ ] AC3: Streamed events fed to the `openai` SDK accumulator equal the non-streamed message (calls, arguments, finish reason). **Covered by** `test_sdk_accumulator_rebuilds_the_non_streamed_message` (pure) and `test_streamed_and_plain_tool_responses_accumulate_to_the_same_message` (router), using `ChatCompletionStreamState` from openai 3.40.0. Both must run, not skip.
- [ ] AC4: Every call denied → the content chunk carries the notes, finish `stop`. `record()` failing after commit → a single `error` event `internal_error`, no `[DONE]`, no tool-call delta. **Covered by** `test_streamed_all_denied_is_the_note_then_stop_and_no_delta` (new, exact sequence), the existing `test_streamed_denied_call_is_the_note_and_stop` and `test_action_audit_failure_after_stream_commit_is_the_error_event`.
- [ ] All tasks completed
- [ ] Backend imports without error (`from app.main import app`)
- [ ] Follows existing patterns (set-ness serializer, pure `v1_sse`, docstrings citing PRD-017 sections and DDs)
