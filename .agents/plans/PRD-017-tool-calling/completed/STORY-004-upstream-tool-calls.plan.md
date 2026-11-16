---
story: STORY-004
prd: PRD-017
slug: upstream-tool-calls
title: "Upstream client: ToolParams, tool message serialization, tool_calls parsing"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-017-tool-calling        # all stories commit here, no per-story branch
created: 2026-11-15
---

# Plan: Upstream client: ToolParams, tool message serialization, tool_calls parsing

## Summary

Teach `app/services/openrouter_client.py` the three upstream halves of tool calling (PRD-017 Section 4 "Upstream", F5, D11, D18). (1) A new frozen `ToolParams(tools, tool_choice=None, parallel_tool_calls=None)` lives in this module. `call_openrouter` takes it as a new **keyword-only** `tools=` argument and copies its non-`None` fields into the payload after the generation params. `GenerationParams` is not widened (PRD-010 T5). (2) Each `Message` is serialized by one helper. It adds `tool_call_id` and `tool_calls` only when they are set, and it sends `content: null` for an assistant turn that has calls and `""` content. A tool-free message is still exactly `{"role", "content"}`. (3) When, and only when, `tools=` was passed, `choices[0].message.tool_calls` is parsed into `ToolCallSpec`s. `content: null` with calls becomes `response == ""`. The arguments strings are carried unparsed. Each shape problem is a non-retryable `OpenRouterError("OpenRouter returned an unexpected response shape: <field> ...")`. Without `tools=`, parsing is today's code byte for byte (D18). `OpenRouterResult` gains `tool_calls: tuple[ToolCallSpec, ...] = ()`, declared last. Nothing else in `app/` changes. The `/v1` translator, the router, `run_conversation` and the pipeline's step 7 call belong to STORY-008. Tests: `tests/test_openrouter_client.py` only.

## User Story

As the PRD-017 implementer
I want `call_openrouter` to forward a tool request, send tool history, and return the model's tool calls
So that the pipeline has calls to decide

## Story Reference

- Story file: `.agents/stories/PRD-017-tool-calling/STORY-004-upstream-tool-calls.md`
- PRD: `.agents/PRDs/PRD-017-tool-calling/PRD.md`: Section 4 Upstream lines 74-78, F5 line 319-320, Section 6.9 lines 299-300, Section 10 Internal API lines 422-428, D11 line 520, D18 line 527
- Client survey: `.agents/spikes/PRD-017-tool-calling/client-survey.md:28` (OpenCode sends `tools: []` with tool history), `:104` (notes for STORY-008)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/services/openrouter_client.py`, `tests/test_openrouter_client.py` |
| Story | STORY-004 |
| PRD | PRD-017 |
| Epic Branch | `epic/PRD-017-tool-calling` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design`. This story has no UI, and its `skills: []` frontmatter agrees | n/a |

---

## Line-number corrections to the story's Technical Notes

The story cites `openrouter_client.py:250-258 / :276-291 / :215-227`, which were the line numbers at `main @ 0bc5774`. The current file is shorter. These are the real locations on this branch (opened):

- payload: `app/services/openrouter_client.py:159-167` (messages comprehension at `:161`)
- parsing: `:185-200` (shape `try` at `:185-193`, null-content branch with the PRD-017 note at `:195-200`), finish_reason `:202-203`, usage `:205-214`
- `OpenRouterResult`: `:124-136`; `call_openrouter` signature `:139-145`; return `:219-226`
- The "runtime-string test" the story pins is `tests/test_openrouter_client.py:321-339` (`test_null_content_with_tool_calls_names_prd_017`, `test_null_content_without_tool_calls_omits_prd_017_note`). It stays unedited.
- `app/routers/v1.py:132-136`: `_Upstream.__call__(messages, model, api_key, **kwargs)` forwards kwargs. Confirmed, no change needed.

---

## Decisions this plan takes (orchestrator asked for them explicitly)

**(a) `type` on an upstream `tool_calls` entry is lenient when absent and strict when wrong.** A missing `type` key, or `type: null`, is accepted as `"function"` (OpenRouter omits it for some providers). Any other present value, including `""` and non-strings, is refused with the shape error `choices[0].message.tool_calls[i].type must be "function"`. This deliberately differs from the client-edge normalizer (`app/models/messages.py:98-99`), which requires `type == "function"`. That normalizer validates what a *client* sends, where OpenAI's spec makes the key required. This parser reads what an *upstream* sends. The serializer always writes `"type": "function"` back out (AC2), so the client never sees the difference.

**(b) A non-string `arguments` is refused as an unexpected shape. It is never coerced.** If a provider returns `arguments` as a JSON object (or a number, list, `null`, or absent), the call fails with `OpenRouterError("OpenRouter returned an unexpected response shape: choices[0].message.tool_calls[i].function.arguments must be a string")`, not retryable. `json.dumps`-ing the object would invent bytes the model never wrote, which breaks D13 / PRD-012's "strings end to end" contract. It would also make the T2 byte-comparison test meaningless. An absent `arguments` is treated the same as a non-string one. This matches the normalizer's rule at `messages.py:110-112`. An empty string `""` is accepted, as the normalizer accepts it. This is a known strictness risk (see Risks): if a provider OpenRouter routes to turns out to send objects, the fix is a provider-specific decision for a later story, not a silent re-serialization here.

**(c) `ToolParams` lives in `openrouter_client.py`, beside `GenerationParams`.** It is the type STORY-008's translator builds (`V1Call.tools: Optional[ToolParams]`, PRD F3 line 314) and threads through `run_conversation(..., *, tools=)` to step 7. It only carries values: it does **no** shape validation of `tools` / `tool_choice` / `parallel_tool_calls`, because that is the translator's job (story Technical Notes). The router and translator import it from here, so `v1_translate` (a pure module) imports a dataclass from the client module. `v1_translate` already imports `GenerationParams` / `UnsupportedParameterError` from the same module, so this is no new dependency direction. STORY-008 should confirm that.

**(d) What "the request sent `tools=`" means.** `tools is not None`, i.e. a `ToolParams` object was passed, whatever its `tools` list holds. `ToolParams(tools=[])` therefore turns on tool parsing and sends `"tools": []` as given. Whether a `/v1` request carrying `tools: []` with tool history (OpenCode, `client-survey.md:28`) becomes `ToolParams([])` or `None` is STORY-008's call. This client forwards exactly what it is handed and drops nothing.

**(e) Without `tools=`, response parsing is today's code, unchanged (D18).** `content: null` still raises `OpenRouter returned no text content (finish_reason=...)`, plus `; tool calls are not supported (PRD-017)` when `message.get("tool_calls") is not None`. That is the existing branch at `:195-200`, untouched. A text answer that also carries `tool_calls` with no `tools=` sent still returns the text and ignores the calls, exactly as today, and `OpenRouterResult.tool_calls == ()`. The pre-existing note test uses a malformed `[{"id": "1"}]` entry and must still get the D18 message, not a shape error. So the tools-off path must not look inside `tool_calls` at all.

**(f) With `tools=` sent:**
- `tool_calls` absent or `null` means no calls. The rest of the parsing is today's (a `null` content still raises the no-text error; the PRD-017 note cannot appear because there are no calls).
- `tool_calls: []` also means no calls. It is treated exactly like absent, so `null` content plus `[]` still raises the no-text error. It is not an empty success, because there is neither text nor a call to decide.
- A non-list `tool_calls` is a shape error naming `choices[0].message.tool_calls`.
- With at least one valid call: `response = content if content is not None else ""`, and `tool_calls` is the tuple in upstream order. `finish_reason` is carried from the upstream exactly as today (`:202-203`), with nothing synthesized. If a provider says `stop` beside calls, that is what STORY-010/011 see.
- Per entry, in this order, the first failure wins and every message names the field path, never a value: the entry is an object; `id` is a non-empty string; `type` follows rule (a); `function` is an object; `function.name` is a non-empty string; `function.arguments` follows rule (b); `id` does not repeat an earlier id in the same response. The duplicate check mirrors `messages.py:113-114`. The release (STORY-010) and the client's `tool` answers key on the id, so two calls with one id are ambiguous.
- Usage parsing (`:205-214`) runs after this, unchanged. A tool-call response without `usage.total_tokens` still fails as today.

**(g) Serialization is per message and role-agnostic.** `Message` is deliberately unvalidated (`messages.py:42-46`), so the serializer does not enforce roles. It writes `tool_call_id` when it is not `None` and `tool_calls` when non-empty, on whatever role carries them. Cross-message shape is STORY-005's. Key order matches the AC: `role`, then `tool_call_id` (if set), then `content`, then `tool_calls` (if set). `content` is `None` only when `tool_calls` is non-empty and `content == ""`. The serializer is applied whether or not `tools=` was passed. `/query` and the chat UI never build tool messages, so their payloads are unchanged (D17).

---

## Patterns to Follow

### Naming / frozen value dataclass carried by keyword
```python
# SOURCE: app/services/openrouter_client.py:47-59
@dataclass(frozen=True)
class GenerationParams:
    """The only generation parameters call_openrouter may forward (PRD-010 F3, T5).

    Every field defaults to None and is sent only when set. from_mapping is
    PRD-015's entry point (the track's "PRD-014"): v1_translate.translate_request
    is its production caller.
    """

    temperature: Optional[float] = None   # 0.0 <= t <= 2.0
```

### Fields sent only when set
```python
# SOURCE: app/services/openrouter_client.py:163-167
    if params is not None:
        for field in ("temperature", "max_tokens", "top_p", "stop"):
            value = getattr(params, field)
            if value is not None:
                payload[field] = value
```

### Defaulted trailing dataclass field (PRD-013 / PRD-015 precedent)
```python
# SOURCE: app/services/openrouter_client.py:129-136
    # PRD-013 STORY-003: usage.prompt_tokens and usage.completion_tokens, None
    # when the provider omitted or malformed the field. Declared after
    # tokens_used with defaults so three-argument construction keeps working.
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    # PRD-015 STORY-002: choices[0].finish_reason, None when absent or not a
    # string. Declared last with a default for the same reason as the split.
    finish_reason: Optional[str] = None
```

### Error Handling: the shape error (not retryable, no status)
```python
# SOURCE: app/services/openrouter_client.py:185-193
        try:
            data = resp.json()
            choice = data["choices"][0]
            message = choice["message"]
            content = message["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise OpenRouterError(
                f"OpenRouter returned an unexpected response shape: {exc}"
            ) from exc
```

### Per-entry tool-call validation naming the location (client-edge twin)
```python
# SOURCE: app/models/messages.py:91-116
    for index, call in enumerate(calls):
        where = f"tool_calls[{index}]"
        if not isinstance(call, Mapping):
            raise MessageNormalizationError(f"{where} is not an object")
        call_id = call.get("id")
        if not isinstance(call_id, str) or not call_id:
            raise MessageNormalizationError(f"{where}.id must be a non-empty string")
        ...
        if call_id in seen:
            raise MessageNormalizationError(f"{where}.id repeats an earlier id in this turn")
```

### Tests: fake client and ordered payload comparison
```python
# SOURCE: tests/test_openrouter_client.py:24-43, 126-136
class _FakeClient:
    def post(self, url, headers=None, json=None):
        self.requests.append({"url": url, "headers": headers, "json": json})
        ...
    payload = client.requests[0]["json"]
    expected = {"model": "gpt-4", "messages": [{"role": "user", "content": "hello"}]}
    assert json.dumps(payload, sort_keys=False) == json.dumps(expected, sort_keys=False)
```

### Tests: field-order pin that this story must extend
```python
# SOURCE: tests/test_openrouter_client.py:436-440
def test_the_split_fields_are_declared_last_and_in_order():
    assert [f.name for f in dataclasses.fields(OpenRouterResult)] == [
        # PRD-015 STORY-002 appends finish_reason after the split.
        "response", "model_used", "tokens_used", "input_tokens", "output_tokens", "finish_reason",
    ]
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/openrouter_client.py` | UPDATE | `ToolParams`; `_wire_message` serializer; keyword-only `tools=`; `_parse_tool_calls`; `OpenRouterResult.tool_calls` |
| `tests/test_openrouter_client.py` | UPDATE | New PRD-017 STORY-004 section; extend the field-order pin (commented, citing PRD-017 D5 / Section 6.9) |

No file is created. No test function is renamed or removed, so `_DELIBERATELY_SUPERSEDED_TESTS` is untouched.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: `ToolParams` and `OpenRouterResult.tool_calls`

- **File**: `app/services/openrouter_client.py`
- **Action**: UPDATE
- **Implement**:
  - `from app.models.messages import Message, ToolCallSpec` (line 7).
  - After `GenerationParams` (after `:101`), add:
    ```python
    @dataclass(frozen=True)
    class ToolParams:
        """The tool request call_openrouter forwards (PRD-017 Section 4, D11).

        Its own keyword, not fields on GenerationParams (PRD-010 T5: from_mapping
        must keep refusing `tools`). Carries values only: shape validation is
        the `/v1` translator's (STORY-008), which is its one builder. Fields are
        sent as given, and a None field is not sent.
        """

        tools: Sequence[Mapping[str, Any]]
        tool_choice: Optional[Union[str, Mapping[str, Any]]] = None
        parallel_tool_calls: Optional[bool] = None
    ```
  - Append to `OpenRouterResult` (after `finish_reason`, `:136`):
    ```python
    # PRD-017 STORY-004: choices[0].message.tool_calls, parsed only when the
    # request sent tools= (D18). Declared last with a default, the PRD-013 /
    # PRD-015 precedent, so three-argument construction keeps working.
    tool_calls: tuple[ToolCallSpec, ...] = ()
    ```
- **Mirror**: `app/services/openrouter_client.py:47-59`, `:129-136`
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: Message serialization

- **File**: `app/services/openrouter_client.py`
- **Action**: UPDATE
- **Implement**: Add a module-level helper (near `_token_count`) and use it at `:161`:
  ```python
  def _wire_message(message: Message) -> dict[str, Any]:
      """One Message as the upstream wire shape (PRD-017 F5).

      Tool-free messages stay exactly {"role", "content"}. arguments is the
      ToolCallSpec's string, never parsed or re-serialized (D13).
      """
      wire: dict[str, Any] = {"role": message.role}
      if message.tool_call_id is not None:
          wire["tool_call_id"] = message.tool_call_id
      # OpenAI's tool-call assistant turn is content: null; the normalizer
      # turned that null into "" (messages.py), so it is restored here.
      wire["content"] = None if message.tool_calls and message.content == "" else message.content
      if message.tool_calls:
          wire["tool_calls"] = [
              {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
              for c in message.tool_calls
          ]
      return wire
  ```
  and `"messages": [_wire_message(m) for m in messages],`.
- **Mirror**: comment and docstring density of `_token_count` / `_classify_http_error` (`:104-121`)
- **Validate**: the existing `test_characterization_payload_shape_is_byte_identical` (`tests/test_openrouter_client.py:126`) and `test_multi_message_conversation_preserves_order_roles_and_content` (`:200`) still pass unedited.

### Task 3: keyword-only `tools=` into the payload

- **File**: `app/services/openrouter_client.py`
- **Action**: UPDATE
- **Implement**: The signature becomes `(messages, model=_DEFAULT_MODEL, api_key=None, params=None, client=None, *, tools: Optional[ToolParams] = None)`, matching PRD Section 10 line 425. After the `params` block (`:163-167`):
  ```python
  # PRD-017 D11: forwarded as given, a None field not sent. A separate keyword,
  # passed only when set (params='s rule), so (messages, model, api_key) stubs
  # keep working.
  if tools is not None:
      payload["tools"] = tools.tools
      for field in ("tool_choice", "parallel_tool_calls"):
          value = getattr(tools, field)
          if value is not None:
              payload[field] = value
  ```
  `tools.tools` is put in the payload as the same object, not copied, so the tests can assert identity.
- **Validate**: import check; Task 6 tests.

### Task 4: Parsing `tool_calls` (only with `tools=`)

- **File**: `app/services/openrouter_client.py`
- **Action**: UPDATE
- **Implement**:
  - Add a module-level helper `_parse_tool_calls(raw: Any) -> tuple[ToolCallSpec, ...]`. It implements decision (f)'s per-entry checks in the stated order. Each failure is `OpenRouterError(f"OpenRouter returned an unexpected response shape: {where}... must ...")` with `where = f"choices[0].message.tool_calls[{index}]"` (and `choices[0].message.tool_calls is not a list` for a non-list). Default `upstream_status=None, retryable=False`. A short comment cites decisions (a) and (b) and D13. `type`: `call.get("type")` must be `None` or `== "function"`. Absent and `null` are accepted, and any other value is refused.
  - Replace the block at `:195-200` with:
    ```python
    calls: tuple[ToolCallSpec, ...] = ()
    if tools is not None:
        # PRD-017: parsed only when tools= was sent. Absent, null and [] are no calls.
        raw_calls = message.get("tool_calls")
        if raw_calls is not None:
            calls = _parse_tool_calls(raw_calls)
    if content is None and calls:
        content = ""  # content: null beside calls (PRD-017 Section 4)
    if content is None:
        ... # today's lines 196-200, byte for byte, including the D18 note
    ```
    With `tools is None` the existing branch runs exactly as today (decision (e)). With `tools=` and no calls (absent, `null` or `[]`), a `null` content reaches the same branch, unedited. Its note condition is `message.get("tool_calls") is not None`, so `[]` plus `null` under `tools=` still gets the `; tool calls are not supported (PRD-017)` suffix. Keep the condition as is, so the D18 branch stays byte-identical. Pin this in a test and say so in a comment.
  - Pass `tool_calls=calls` to the `OpenRouterResult(...)` at `:219-226`.
- **Mirror**: `app/models/messages.py:86-117` (order of checks, `where` naming); `:185-193` (shape message prefix)
- **Validate**: import check; Task 6 tests.

### Task 5: Docstring / comment hygiene

- **File**: `app/services/openrouter_client.py`
- **Action**: UPDATE
- **Implement**: Add a short docstring to `call_openrouter` if a sentence is needed to state D18 ("tool_calls are parsed only when `tools=` was sent; otherwise a null content with calls stays today's error"). Do not reword lines you do not touch. The existing `(PRD-017)` note string at `:199` is already correct and stays byte-identical.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 6: Tests

- **File**: `tests/test_openrouter_client.py`
- **Action**: UPDATE
- **Implement**: Import `ToolParams` and `ToolCallSpec`. Edit the field-order pin at `:436-440` to append `"tool_calls"`, with the comment `# PRD-017 STORY-004 (D5, Section 6.9): tool_calls appended last with a default.` Do not rename the test. Add a section `# --- PRD-017 STORY-004: tool calls upstream ---` with:
  - AC1 payload:
    - `test_tool_params_reach_the_payload_exactly_as_given`: `ToolParams(tools=[...], tool_choice="auto", parallel_tool_calls=False)`. Assert an ordered `json.dumps` equal to the recorded expected dict (keys after `messages`: `tools`, `tool_choice`, `parallel_tool_calls`), `payload["tools"] is tp.tools`, and `parallel_tool_calls is False`, which is sent because `False` is not `None`.
    - A parametrized test over the four `tool_choice` forms (`"none"`, `"auto"`, `"required"`, `{"type": "function", "function": {"name": "bash"}}`) checks that each is sent byte-equal.
    - `test_a_none_tool_field_is_not_sent`: `ToolParams(tools=[...])` gives no `tool_choice` / `parallel_tool_calls` keys.
    - `test_without_tools_the_payload_is_byte_identical_to_a_recorded_one`: a multi-turn conversation plus `GenerationParams(temperature=0.2, stop=["x"])`, compared against a **literal recorded JSON string** (`'{"model": "gpt-4", "messages": [...], "temperature": 0.2, "stop": ["x"]}'`), so the test does not depend on the serializer under test.
    - `test_tools_is_keyword_only`: `call_openrouter(msgs, "m", "k", None, client, tp)` raises `TypeError`.
    - `GenerationParams.from_mapping({"tools": []})` still raises `UnsupportedParameterError` naming `tools` (PRD-010 T5).
  - AC2 serialization:
    - Assistant turn `Message("assistant", "", (ToolCallSpec("call_1", "bash", '{"command":"ls"}'),))` becomes `{"role":"assistant","content":null,"tool_calls":[{"id":"call_1","type":"function","function":{"name":"bash","arguments":"{\"command\":\"ls\"}"}}]}` (ordered dumps).
    - With content `"thinking"` the content string is kept.
    - Tool turn `Message("tool", "app.db", tool_call_id="call_1")` becomes `{"role":"tool","tool_call_id":"call_1","content":"app.db"}` (ordered).
    - An escape-heavy, PII-looking, non-JSON `arguments` string (`'{"p":"C:\\\\x\\n", "email":"a@b.co"} '`, trailing space) arrives byte-equal (`==`, and the same object `is` the spec's string).
    - An empty assistant turn with no calls still sends `content: ""`, not `null`.
  - AC3 parsing:
    - A helper `_tool_call_response(content, tool_calls, finish_reason="tool_calls")`.
    - `content: null` + two calls with `tools=` gives `response == ""`, a `tool_calls` tuple of `ToolCallSpec`s in order, `arguments` byte-identical (escape-heavy string), and `finish_reason == "tool_calls"`.
    - Text + calls keeps both.
    - An entry without a `type` key is accepted, and `type: null` is accepted (decision a).
    - Usage and the split are still read on a tool-call response.
    - `tools=` with no `tool_calls` key returns text with `tool_calls == ()`.
    - `tools=` with `tool_calls: []` and text gives `()`; with `null` content it raises the no-text error (decision f).
  - AC4 D18:
    - `null` content + a well-formed call with **no** `tools=` raises `OpenRouterError` whose `str` equals `"OpenRouter returned no text content (finish_reason=tool_calls); tool calls are not supported (PRD-017)"` (exact), `retryable is False`.
    - Text + calls with no `tools=` returns the text and `tool_calls == ()` (decision e).
    - The existing tests at `:321-339` stay unedited.
  - AC5 malformed (parametrized, all with `tools=`):
    - `tool_calls` is `{}` / `"x"`: `...: choices[0].message.tool_calls is not a list`
    - entry not an object
    - `id` missing, `""`, or int
    - `type: "custom"` / `type: ""`: `...tool_calls[0].type must be "function"`
    - `function` missing or a string
    - `function.name` missing or `""`: `...tool_calls[0].function.name must be a non-empty string`
    - `function.arguments` as an object `{"command": "ls"}`, absent, `null`, or int: `...function.arguments must be a string`
    - a duplicate id on the second entry
    - Each asserts `str(exc).startswith("OpenRouter returned an unexpected response shape: ")`, that the field path is in the message, `retryable is False`, and `upstream_status is None`.
    - One test checks that no message contains a value: put a sentinel string in `arguments` / `name` / `id` and assert it is absent from `str(exc)`.
  - Stub compatibility: a `(messages, model, api_key)` stub is still callable by `_Upstream` without `tools`. This is already covered by the existing suite, so no new test is needed. Name it in the report.
- **Mirror**: `tests/test_openrouter_client.py:126-136`, `:302-311`, `:495-521`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_openrouter_client.py tests/test_untouched_app.py -q` (record counts)

---

## End-to-End Tests

- [ ] `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_openrouter_client.py tests/test_untouched_app.py tests/test_v1_router.py tests/test_query_outcomes_regression.py -q`. `tests/test_v1_router.py` (it exercises `_Upstream`) checks that the `**kwargs` forwarding is unaffected. The `/query` regression checks D17. Run it as one pytest call, in the foreground.
- [ ] Import check: `.venv/Scripts/python -c "from app.main import app; print('OK')"`
- [ ] No live upstream call (PRD-015 Risk 7). STORY-014 drives the stub upstream with tool calls later.

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_openrouter_client.py tests/test_untouched_app.py -q
git diff --stat   # only app/services/openrouter_client.py and tests/test_openrouter_client.py (+ plan/report/story/index)
```

Full suite: deferred to orchestrator (user decision).

---

## Risks

| Risk | Mitigation |
|---|---|
| A provider behind OpenRouter returns `arguments` as an object, or omits it for a no-argument call. Decision (b) fails the request | Stated deliberately: D13 forbids inventing bytes. The failure is an explicit, named shape error, not a silent change. If E2E (STORY-014/015) or a live run shows it, a later decision can map a *missing* `arguments` to `""` without touching the object case |
| `[]` + `null` under `tools=` carries the PRD-017 note in its message, which is slightly misleading | Kept, so the D18 branch stays byte-identical. Pinned by a test so the behaviour is deliberate |
| `ToolParams.tools` is a mutable list inside a frozen dataclass (unhashable) | The class only carries values, as `GenerationParams.stop` may carry a list. Nothing hashes it. Not copied, so "as given" is literal |
| STORY-008 passes `ToolParams([])` for OpenCode's `tools: []`, and an upstream rejects an empty `tools` array | Out of this story: the client forwards what it is given (decision d). Flagged to the orchestrator for STORY-008 |
| `query_pipeline.py:661` rebuilds `Message(message.role, redacted_content)` and drops tool fields before step 7 | Not this story (STORY-006/008 widen step 6). Noted so the serializer is not blamed when history calls vanish end to end |
| Upstream `finish_reason` may be `stop` beside calls | Carried as given; STORY-010's release decides the client-facing value (PRD 6.6 line 242) |

---

## Acceptance Criteria

(Copied from story `STORY-004`)

- [ ] Given `ToolParams(tools=[...], tool_choice="auto", parallel_tool_calls=False)` passed as `call_openrouter(..., tools=tp)`, when the request is sent, then the payload carries `tools`, `tool_choice` and `parallel_tool_calls` exactly as given (a `None` field is not sent); without `tools=`, the payload is byte-identical to today's (asserted against a recorded payload). *Task 3, Task 6 AC1 tests.*
- [ ] Given messages with an assistant `tool_calls` turn and a `tool` turn, when serialized, then the assistant turn is `{"role": "assistant", "content": null, "tool_calls": [{"id", "type": "function", "function": {"name", "arguments"}}]}` when its content is `""` (the content string otherwise) and the tool turn is `{"role": "tool", "tool_call_id", "content"}`; tool-free messages serialize exactly as today; `arguments` is the same string object's value, unparsed. *Task 2, Task 6 AC2 tests.*
- [ ] Given an upstream response with `message.content: null` and `tool_calls`, when the request sent `tools=`, then `OpenRouterResult.response == ""`, `.tool_calls` holds `ToolCallSpec`s in order with byte-identical arguments, and `.finish_reason == "tool_calls"`; with text content and calls, both are kept. *Task 4, Task 6 AC3 tests.*
- [ ] Given an upstream `tool_calls` response to a request that sent **no** `tools=`, when parsed, then `OpenRouterError` is raised with today's message ending `; tool calls are not supported (PRD-017)` (D18); `/query` and the chat UI are unaffected. *Task 4 (branch untouched), Task 6 AC4 tests, existing `:321-339`, `test_query_outcomes_regression.py`.*
- [ ] Given a malformed `tool_calls` entry (not a list, missing `function.name`, non-string `arguments`), when parsed, then `OpenRouterError("OpenRouter returned an unexpected response shape: ...")` naming the field, not retryable. *Task 4, Task 6 AC5 parametrized test.*
- [ ] All tasks completed
- [ ] Backend imports without error (`from app.main import app`)
- [ ] Follows existing patterns (frozen value dataclass, keyword passed only when set, defaulted trailing field, location-naming messages)
