---
story: STORY-006
prd: PRD-015
slug: parameter-classification-and-tools-refusal
title: "Parameter classification: forward, ignore-and-record, reject; the explicit tools refusal"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-015-openai-compatible-endpoint
created: 2026-10-22
---

# Plan: Parameter classification: forward, ignore-and-record, reject; the explicit tools refusal

## Summary

This story adds `translate_request(body: ChatCompletionRequest) -> V1Call` to `app/services/v1_translate.py`, next to STORY-005's `translate_messages`. Every key the client sent falls into one of three groups, held in one table (PRD Section 7.3):

1. **`FORWARDED`**: `temperature`, `top_p`, `max_tokens`, `stop`, `max_completion_tokens`. These are type-checked, then passed through `GenerationParams.from_mapping`. `max_completion_tokens` becomes `max_tokens`. A failure is `invalid_parameter`, with `param` set to the key.
2. **`REJECTED_UNLESS_DEFAULT`**: `n`, `logprobs`, `top_logprobs`, `response_format`, `modalities`, `audio`, `tools`, `tool_choice`, `functions`, `function_call`. Each key lists its accepted default values. Any other value is refused: `tools_not_supported` for the four tool keys, `unsupported_parameter` for the rest.
3. **Everything else is ignored.** Only the key's name is recorded, never its value. This includes `user`, `profile`, `ingress`, `openrouter_api_key`, unknown keys, and `stream_options.<key>` for every sub-key except `include_usage`.

`V1Call` is a frozen dataclass with these fields: `messages`, `params` (`Optional[GenerationParams]`), `model`, `stream`, `include_usage` and `ignored_params` (`Optional[str]`). `ignored_params` is the sorted, comma-joined set of ignored names, merged with STORY-005's `messages[].name`. It is `None` when nothing was ignored.

The module stays pure. Its only new imports are `dataclasses`, `app.models.v1_schemas` and `app.services.openrouter_client`.

Tests extend `tests/test_v1_translate_request.py`. All of them are DB-free except one: a T5 test runs a full request through `run_conversation` over STORY-001's `httpx.MockTransport` capture helper. It needs `temp_db`, and it pins the upstream body's keys to STORY-001's set.

## User Story

As an integrating developer
I want every parameter my client sends either honoured, ignored with a record, or refused by name
So that I am never silently given a different answer than I asked for, and the upstream request never carries more than the harness allows.

## Story Reference

- Story file: `.agents/stories/PRD-015-openai-compatible-endpoint/STORY-006-parameter-classification-and-tools-refusal.md`
- PRD: `.agents/PRDs/PRD-015-openai-compatible-endpoint/PRD.md` (Sections 7.1, 7.3, 9.2 T4/T5, 15 D3)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/services/v1_translate.py`, `tests/test_v1_translate_request.py` |
| Story | STORY-006 |
| PRD | PRD-015 |
| Epic Branch | `epic/PRD-015-openai-compatible-endpoint` (commit directly on this branch) |

Dependencies STORY-001, STORY-004 and STORY-005 are all `done`.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | None. The only skill in `.agents/skills/` is `frontend-design`, and this story has no UI. The story's `skills: []` agrees | — |

---

## Findings That Shape the Design

These were checked against the code on the epic branch (venv probe, 2026-10-22). They are why the translator does more than call `from_mapping`.

| # | Finding | Consequence |
|---|---------|-------------|
| F1 | `GenerationParams(temperature="hot")` and `GenerationParams(max_tokens="5")` raise **`TypeError`**, not `UnsupportedParameterError` (`openrouter_client.py:59-70` compares before any type check) | The translator type-checks each forwarded value **before** `from_mapping`. A `TypeError` must never reach the router as a 500 |
| F2 | `GenerationParams(temperature=True)` and `GenerationParams(max_tokens=1.5)` are **accepted** | Same type check: numbers exclude `bool`, and `max_tokens` / `max_completion_tokens` must be `int` (not `bool`) |
| F3 | Every `UnsupportedParameterError` message ends with `got {value!r}` (`openrouter_client.py:61-89`). `stop` can hold user text | The 400 message is the translator's own per-key rule text, and the error is raised `from None`, so the value is in neither the message nor `__cause__` (T6, matching STORY-005's canary tests) |
| F4 | With `extra="allow"`, `model_fields_set` already includes the extra keys, and an explicit `null` counts as set (`{'seed': None}` came back in `model_extra`, and `seed` was in `model_fields_set`) | "Sent keys" is `body.model_fields_set`. Ignored keys are recorded **on presence**, even when `null`, the same rule STORY-005 uses for `name` (`test_name_is_recorded_on_presence_even_when_null`) |
| F5 | `n=True` parses as `True` (a `bool`), and `True == 1` in Python | A rejected key's value matches its default only if **type and value** both match, so `n=True` is refused and `n=1` is accepted |
| F6 | `run_conversation` passes `params=` to `call_openrouter` only when it is not `None` (STORY-001's `_upstream_over` docstring; PRD-010 STORY-005's stub-signature rule) | `V1Call.params` is `None` when no forwarded key carried a value. It is never an empty `GenerationParams()` |
| F7 | `test_is_pure` allows imports only from `{"typing", "app.models.messages"}` (`tests/test_v1_translate_request.py:320`) | That test's allowed set grows by exactly three modules. The banned-names check (`settings`, `httpx`, ...) is unchanged and still passes |

---

## Patterns to Follow

### Error construction: location first, rule, never the value
```python
# SOURCE: app/services/v1_translate.py:63-66, 77-80
if "tool_calls" in item or "function_call" in item:
    raise V1RequestError(
        TOOLS_NOT_SUPPORTED, f"{location}: tool calls are not supported (PRD-016)", location
    )
...
try:
    messages.append(normalize_message(item))
except MessageNormalizationError as exc:
    raise V1RequestError(INVALID_MESSAGES, f"{location}: {exc}", location) from exc
```
The new messages follow `f"{param}: {rule}"`. Wrapped errors use `from None`, not `from exc` (F3).

### Code constants
```python
# SOURCE: app/services/v1_translate.py:13-18
INVALID_MESSAGES = "invalid_messages"
TOOLS_NOT_SUPPORTED = "tools_not_supported"
IGNORED_MESSAGE_NAME = "messages[].name"
```
Add `INVALID_PARAMETER = "invalid_parameter"` and `UNSUPPORTED_PARAMETER = "unsupported_parameter"` beside them.

### The allowlist being fed
```python
# SOURCE: app/services/openrouter_client.py:92-100
@classmethod
def from_mapping(cls, raw: Mapping[str, Any]) -> "GenerationParams":
    """PRD-014's entry point. Raises for any key outside the allowlist, sorted."""
    unsupported = sorted(set(raw) - _ALLOWED_GENERATION_PARAMS)
    ...
    return cls(**{key: raw[key] for key in _ALLOWED_GENERATION_PARAMS if key in raw})
```
`v1_translate` is this method's first production caller. Update the `GenerationParams` docstring (`openrouter_client.py:51-52`, which says "nothing in this PRD calls it in production") so it names `v1_translate.translate_request` and says PRD-015 (see the PRD's numbering note).

### Tests: parametrized refusals with ids, ASCII only
```python
# SOURCE: tests/test_v1_translate_request.py:123-201
@pytest.mark.parametrize("raw, code, param, rule", [...], ids=[...])
def test_refuses(raw, code, param, rule):
    with pytest.raises(V1RequestError) as caught:
        translate_messages(raw)
    exc = caught.value
    assert exc.code == code
    assert exc.param == param
    assert re.search(rule, exc.message)
```

### Tests: upstream capture (T5 baseline)
```python
# SOURCE: tests/test_v1_query_isolation.py:210-237, 259-285
def _capturing_transport(seen: list) -> httpx.MockTransport: ...
def _upstream_over(transport: httpx.MockTransport): ...   # the real call_openrouter over the transport
...
assert list(body) == ["model", "messages", "temperature", "max_tokens", "top_p", "stop"]
```
Import `_capturing_transport`, `_upstream_over` and `_mask_nothing` from `tests.test_v1_query_isolation`, the same way that file imports `_API_URL` from `tests.test_openrouter_client`. Do not write a third copy (STORY-001 Technical Notes). Import only these helpers, not its `temp_db` override.

### Tests: the authenticated-user fixture
```python
# SOURCE: tests/test_v1_query_isolation.py:65-71
@pytest.fixture
def temp_db(temp_db):
    insert_user(User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN)))
    return temp_db
```
Mirror this as a local fixture in the request test file. Requesting `temp_db` gives the test the `db` marker automatically (`tests/conftest.py:157-173`). Every other test in the file stays DB-free and runs under `-m "not db"`.

---

## Design

### The table (top of `v1_translate.py`, below the constants)

```python
# PRD-015 Section 7.3 (D3): every key the client sends is in exactly one of
# three groups. Widening the upstream surface means changing PRD-010's
# allowlist, deliberately; test_forwarded_is_generation_params_plus_alias
# fails otherwise.
FORWARDED = frozenset({"temperature", "top_p", "max_tokens", "stop", "max_completion_tokens"})

# Accepted only as one of its listed defaults, compared by type and value so
# `n: true` is not `n: 1`. Absent is always accepted.
REJECTED_UNLESS_DEFAULT: Mapping[str, Tuple[str, Tuple[Any, ...]]] = {
    "tools": (TOOLS_NOT_SUPPORTED, (None, [])),
    "functions": (TOOLS_NOT_SUPPORTED, (None, [])),
    "tool_choice": (TOOLS_NOT_SUPPORTED, (None, "none")),
    "function_call": (TOOLS_NOT_SUPPORTED, (None,)),
    "n": (UNSUPPORTED_PARAMETER, (None, 1)),
    "logprobs": (UNSUPPORTED_PARAMETER, (None, False)),
    "top_logprobs": (UNSUPPORTED_PARAMETER, (None,)),
    "response_format": (UNSUPPORTED_PARAMETER, (None, {"type": "text"})),
    "modalities": (UNSUPPORTED_PARAMETER, (None, ["text"])),
    "audio": (UNSUPPORTED_PARAMETER, (None,)),
}

# Read by translate_request itself, so neither forwarded nor ignored.
_STRUCTURAL = frozenset({"model", "messages", "stream", "stream_options"})
```

Everything outside these three sets is ignored. No set lists the ignored keys: "everything else" is the rule (PRD Section 7.3).

### Decisions where the story and PRD leave room

| Question | Decision | Why |
|----------|----------|-----|
| `function_call: "none"` | **Refused**. Only `null` or absent is accepted | AC 3 lists `function_call` with no exception. `tool_choice: "none"` is the one stated exception. A client still on the legacy field sending `"none"` gets a clear 400 that names it |
| `top_logprobs: 0` | **Refused**. Only `null` or absent is accepted | PRD 7.1: "`false`/`null`/absent accepted". `0` is none of those |
| An explicit `null` on a forwarded key | Treated as absent: not forwarded and not recorded | `GenerationParams` treats `None` as unset already, so nothing is ignored |
| An explicit `null` on an ignored key (`seed: null`) | **Recorded** (`seed`) | The presence rule, the same as STORY-005's `name` (F4) |
| `max_tokens` and `max_completion_tokens` both sent, equal | Accepted, forwarded once as `max_tokens` | AC 1 refuses only "different values" |
| Both sent, different | `invalid_parameter`, `param="max_completion_tokens"` | The alias is the key that conflicts with the canonical one |
| `include_usage` without `stream: true` | `V1Call.include_usage` is `False` | PRD 7.1: "honoured on streamed requests". Deciding this in the pure layer means STORY-013 cannot forget it |
| `stream_options` is not an object, or `include_usage` is not a bool or `null` | `invalid_parameter`, `param="stream_options"` or `"stream_options.include_usage"` | A wrong type must not be silently read as `False` |
| Check order | Rejected keys in table order, then forwarded keys in `FORWARDED_ORDER` (`temperature`, `top_p`, `max_tokens`, `stop`, `max_completion_tokens`), then `stream_options`, then `translate_messages` | Deterministic first-failure-wins, like STORY-005. Cheap shape checks run before message work. Tools come first, so a tools client always sees `tools_not_supported` |
| Comma separator | `","` with no space (`"seed,user"`) | STORY-007's AC example |

### Forwarded value checks

| Key | Type check (before `from_mapping`) | Message (`param` = key) |
|-----|-----------------------------------|-------------------------|
| `temperature` | `int` or `float`, not `bool` | `temperature: must be a number between 0.0 and 2.0` |
| `top_p` | `int` or `float`, not `bool` | `top_p: must be a number greater than 0.0 and at most 1.0` |
| `max_tokens`, `max_completion_tokens` | `int`, not `bool` | `<key>: must be an integer >= 1` |
| `stop` | (left to `GenerationParams`, which already checks types) | `stop: must be a string or a list of at most 4 strings` |

Each present, non-null key is validated alone with `GenerationParams.from_mapping({canonical_key: value})` inside `try/except UnsupportedParameterError`. That is how the error knows its `param`, because `from_mapping` on the whole mapping cannot say which key failed. The final `GenerationParams.from_mapping(forwarded)` then runs on values that are already valid. NaN and infinity fail the range comparisons and raise `UnsupportedParameterError` (`0.0 <= nan` is `False`). No new check is needed for them.

### `translate_request` outline

```python
@dataclass(frozen=True)
class V1Call:
    """What the router passes to run_conversation (PRD-015 Section 6.1). No
    `profile` or `ingress`: the call site names those (T4)."""

    messages: List[Message]
    params: Optional[GenerationParams]
    model: str
    stream: bool
    include_usage: bool
    ignored_params: Optional[str]


def translate_request(body: ChatCompletionRequest) -> V1Call:
    sent = body.model_fields_set
    values = {**{k: getattr(body, k) for k in body.model_fields}, **(body.model_extra or {})}
    _check_rejected(sent, values)                     # tools_not_supported / unsupported_parameter
    params = _forwarded_params(sent, values)          # invalid_parameter; None when empty
    include_usage, stream_ignored = _stream_options(body)
    messages, message_ignored = translate_messages(body.messages)
    ignored = (sent - FORWARDED - REJECTED_UNLESS_DEFAULT.keys() - _STRUCTURAL) | stream_ignored | message_ignored
    return V1Call(messages, params, body.model, body.stream,
                  body.stream and include_usage, ",".join(sorted(ignored)) or None)
```

Keep the helpers private and small. Look `sent` keys up in `values`, not with `getattr` alone, because extras are not attributes declared on the model. Add a `values` comment if needed.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/v1_translate.py` | UPDATE | Constants, the classification table, `V1Call`, `translate_request` and its private helpers. Module docstring: drop "lands here too" and describe what it does now |
| `app/services/openrouter_client.py` | UPDATE (docstring only) | `GenerationParams` docstring: name the production caller and the PRD number. No behaviour change |
| `tests/test_v1_translate_request.py` | UPDATE | Module docstring names STORY-006 too. New sections for AC 1-5 and T4/T5. `test_is_pure`'s allowed modules grow by three |

No new files. No schema change: `ChatCompletionRequest` already declares every field (STORY-004).

---

## Tasks

Execute in order. Each task is atomic and verifiable. Python is `C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe`. Run it from the repo root with `PYTHONPATH=.` (the Git Bash recipe in memory).

### Task 1: Constants, table and `V1Call`

- **File**: `app/services/v1_translate.py`
- **Action**: UPDATE
- **Implement**: Add `INVALID_PARAMETER` and `UNSUPPORTED_PARAMETER`. Add `FORWARDED`, `REJECTED_UNLESS_DEFAULT` and `_STRUCTURAL` as in the Design, with the comment on each. Add the frozen `V1Call` dataclass. New imports: `dataclasses.dataclass`, `ChatCompletionRequest` from `app.models.v1_schemas`, and `GenerationParams` and `UnsupportedParameterError` from `app.services.openrouter_client`. Extend the `typing` import to cover `Dict` and `Tuple`. Rewrite the module docstring's last sentence.
- **Mirror**: `v1_translate.py:13-34` (constant placement, docstring tone)
- **Validate**: `python -c "import app.services.v1_translate"` imports cleanly (no cycle)

### Task 2: Rejected-unless-default check

- **File**: `app/services/v1_translate.py`
- **Action**: UPDATE
- **Implement**: `_is_default(value, defaults)` returns true when some default `d` satisfies `type(value) is type(d) and value == d` (F5). `_check_rejected(sent, values)` goes through `REJECTED_UNLESS_DEFAULT` in table order and skips absent keys. Present keys that are not a default raise `V1RequestError(code, f"{key}: {rule}", key)`. The rule is `"tool calling is not supported (PRD-016)"` for `TOOLS_NOT_SUPPORTED` and `"only the default value is supported on this endpoint"` for `UNSUPPORTED_PARAMETER`. Never interpolate the value.
- **Mirror**: `v1_translate.py:63-70`
- **Validate**: Task 5's AC 2/3 tests

### Task 3: Forwarded parameters

- **File**: `app/services/v1_translate.py`
- **Action**: UPDATE
- **Implement**: Add `_FORWARDED_RULES: Dict[str, str]` (the message table above) and the per-key type predicate. `_forwarded_params(sent, values) -> Optional[GenerationParams]` handles the keys in fixed order and skips `None`. A failed type check raises `invalid_parameter`. Otherwise it calls `GenerationParams.from_mapping({canonical: value})`, and if that raises `UnsupportedParameterError` it raises `V1RequestError(INVALID_PARAMETER, f"{key}: {rule}", key) from None`, with a comment citing F3 / T6. `canonical` is `max_tokens` for `max_completion_tokens`. Then apply the alias rule: when both are set and different, raise `invalid_parameter` on `max_completion_tokens` with the message `"max_completion_tokens: must equal max_tokens when both are sent"`. Return `GenerationParams.from_mapping(collected)` when `collected` is non-empty, else `None` (F6).
- **Mirror**: `v1_translate.py:77-80`, but `from None`
- **Validate**: Task 5's AC 1 tests

### Task 4: `stream_options`, ignored names and `translate_request`

- **File**: `app/services/v1_translate.py`
- **Action**: UPDATE
- **Implement**: `_stream_options(value) -> Tuple[bool, FrozenSet[str]]`. `None` gives `(False, ∅)`. A value that is not a `Mapping` raises `invalid_parameter` with `param="stream_options"`. In a mapping, `include_usage` must be `bool` or `None` (else `invalid_parameter`, `param="stream_options.include_usage"`), and every other key becomes `f"stream_options.{key}"`. Then write `translate_request` as outlined, with a docstring that states the check order and the presence rule. The `ignored` set is a union of sets, so each name appears once (story note: "each listed once").
- **Mirror**: `translate_messages` docstring style (`v1_translate.py:38-50`)
- **Validate**: Task 5

### Task 5: Unit tests (DB-free)

- **File**: `tests/test_v1_translate_request.py`
- **Action**: UPDATE
- **Implement**: Add a helper `_body(**fields)` that returns `ChatCompletionRequest.model_validate({"model": "gpt-4", "messages": [_USER], **fields})`. Then add sections in the file's `# --- AC n: ... ---` style:
  - **AC 1, forwarded**: all four in range give `call.params == GenerationParams(temperature=0.2, top_p=0.9, max_tokens=100, stop=["END"])`. Nothing forwarded gives `params is None`. Explicit `null`s give `params is None` and `ignored_params is None`. `max_completion_tokens=50` alone gives `params.max_tokens == 50`. Both equal is accepted. Both different gives `invalid_parameter` / `max_completion_tokens`. A parametrized refusal table with ids covers: `temperature` 2.5, -0.1, `"hot"` (F1), `True` (F2), NaN; `top_p` 0, 1.5; `max_tokens` 0, 1.5 (F2), `"5"` (F1), `True`; `max_completion_tokens` 0; `stop` five strings, `[1]`, `{}`. Each must give `code == INVALID_PARAMETER`, `param == key` and `message.startswith(f"{key}: ")`. Add a test that no `TypeError` escapes for any of those values.
  - **AC 2, unsupported**: `n=2`, `n=True` (F5), `logprobs=True`, `top_logprobs=3`, `top_logprobs=0`, `response_format` `json_object` and `json_schema`, `modalities=["text","audio"]` and `audio={...}` give `UNSUPPORTED_PARAMETER` with `param`. Accepted: `n=1`, `logprobs=False`, `logprobs=None`, `response_format={"type":"text"}`, `modalities=["text"]`, each giving `ignored_params is None`.
  - **AC 3, tools**: `tools=[{...}]`, `functions=[{...}]`, `tool_choice="auto"`, `tool_choice={"type":"function",...}`, `function_call="auto"` and `function_call="none"` give `TOOLS_NOT_SUPPORTED` with `param`. Accepted: `tools=[]`, `tools=None`, `tool_choice="none"`, `tools=[]` together with `tool_choice="none"`. Order: `tools=[...]` together with `n=2` gives `tools_not_supported`.
  - **AC 4, ignored**: the AC's exact body (`seed`, `user`, `presence_penalty`, `logit_bias`, `metadata`, `profile`, `ingress`, `openrouter_api_key`, an unknown key, and `stream_options={"include_usage": True, "foo": 1}` with `stream=True`) gives `ignored_params == "ingress,logit_bias,metadata,openrouter_api_key,presence_penalty,profile,seed,stream_options.foo,<unknown>,user"`, i.e. `",".join(sorted(...))`. `include_usage is True`. A canary value on every ignored key (`"SECRET-CANARY"`) does not appear in `repr(call)`. A `name` on a message merges in as `messages[].name`, listed once even when two messages carry one. Nothing ignored gives `None`. `seed: null` is recorded. `include_usage` without `stream` is `False`. `stream_options` as `"yes"` and `include_usage="true"` give `invalid_parameter` with their params.
  - **T4**: a body with `profile="permissive"` and `ingress="query"` records both as ignored, and `{f.name for f in fields(V1Call)}` has no `profile` or `ingress`.
  - **AC 5, table**: `FORWARDED == {f.name for f in fields(GenerationParams)} | {"max_completion_tokens"}`. `FORWARDED`, `REJECTED_UNLESS_DEFAULT.keys()` and `_STRUCTURAL` are pairwise disjoint. Every declared `ChatCompletionRequest` field is in one of them or is `user`, which pins STORY-004's schema to the table.
  - **T6 canary**: a `stop=[_CANARY]*5`, `stop=[_CANARY, 1]` and `temperature=_CANARY` refusal has `"CANARY"` in neither `str(exc)`, `exc.param` nor `repr(exc.__cause__)`, and `exc.__cause__ is None`.
  - **Messages still translate**: `translate_request(_body(messages=[...developer...]))` gives `call.messages == translate_messages(...)[0]`. A message refusal still surfaces as STORY-005's error.
  - Update `test_is_pure`: allowed modules become `{"typing", "dataclasses", "app.models.messages", "app.models.v1_schemas", "app.services.openrouter_client"}`. The banned-names assertion is unchanged.
- **Mirror**: `tests/test_v1_translate_request.py:123-201` (parametrize and ids), `:254-280` (canary)
- **Validate**: `python -m pytest tests/test_v1_translate_request.py -m "not db" -q`

### Task 6: T5 upstream-body test (DB)

- **File**: `tests/test_v1_translate_request.py`
- **Action**: UPDATE
- **Implement**: Add a local `_v1_user` fixture (over `temp_db`) that inserts `_AUTH_USER_ID`, mirroring the isolation file's fixture. Write `test_translated_request_upstream_body_is_the_t5_set(_v1_user, monkeypatch)` as follows:
  1. Build a body with all four forwarded keys, every ignored key from AC 4, the accepted defaults of every rejected key (`n=1`, `tools=[]`, `tool_choice="none"`, `response_format={"type":"text"}`, `modalities=["text"]`, `logprobs=False`), and `profile` and `ingress`.
  2. Run `translate_request` on it.
  3. Monkeypatch `query_pipeline.redact` to `_mask_nothing`.
  4. Call `run_conversation(Identity(...), call.messages, None, call.model, None, call.params, call_openrouter=_upstream_over(_capturing_transport(seen)), profile="code", ingress="v1")`. Do not pass `ignored_params`: that keyword is STORY-007's.

  Assert `list(json.loads(seen[0].content)) == ["model", "messages", "temperature", "max_tokens", "top_p", "stop"]`, and that no ignored or rejected key name appears among the body keys.
- **Mirror**: `tests/test_v1_query_isolation.py:259-285`
- **Validate**: `python -m pytest tests/test_v1_translate_request.py -q` (needs Docker and the libsql container, see memory)

### Task 7: Docstring on `GenerationParams`

- **File**: `app/services/openrouter_client.py`
- **Action**: UPDATE (docstring at lines 51-52, and the `from_mapping` one-liner at 94)
- **Implement**: Change "PRD-014's entry point; nothing in this PRD calls it in production" to say it is PRD-015's entry point (the track's "PRD-014"), called by `v1_translate.translate_request`. Change no code.
- **Validate**: `python -m pytest tests/test_openrouter_client.py tests/test_v1_query_isolation.py -q`

---

## End-to-End Tests

There is no route yet: STORY-009 mounts `/v1/chat/completions`. So this story's end-to-end check is the in-process T5 test (Task 6), which goes from the parsed wire body through translation, the real pipeline and the real `call_openrouter`, to a captured HTTP request.

- [ ] Task 6 passes: the upstream body keys are exactly STORY-001's set while the request carries every ignored and defaulted key
- [ ] `tests/test_v1_query_isolation.py` passes unchanged (the STORY-001 baseline is untouched)
- [ ] An interactive check from the venv, `translate_request(ChatCompletionRequest.model_validate({...aider-like body...}))`, prints a `V1Call` with the expected `ignored_params` and no values

---

## Validation

```bash
cd /c/Users/tobip/OneDrive/Documentos/prog/harness-ai
PY=/c/Users/tobip/.venvs/harness-ai/Scripts/python.exe
PYTHONPATH=. $PY -m pytest tests/test_v1_translate_request.py tests/test_v1_schemas.py tests/test_openrouter_client.py -m "not db" -q
PYTHONPATH=. $PY -m pytest tests/test_v1_translate_request.py tests/test_v1_query_isolation.py -q   # Docker + libsql up
PYTHONPATH=. $PY -m pytest tests/ -m "not db" -q                                                     # ~60 s, no Docker
```

Run the full suite (~5.5 min) in the background before committing. Shared-DB flakes (`STREAM_EXPIRED`, 10060) need a rerun of the errored files before anyone blames the change.

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| `GenerationParams` raises `TypeError` for wrong types, which would become a 500 (F1) | The translator type-checks first, and a test proves no `TypeError` escapes for any refusal-table value |
| Error text leaks a `stop` value (F3) | Own rule text, `from None`, canary test |
| `bool`/`int` equality accepts `n: true` (F5) | The type-and-value default match, tested |
| A future `ChatCompletionRequest` field is left unclassified | AC 5's partition test fails on any declared field outside the table |
| Ignored key **names** are client-chosen strings: a key with a comma, or a very long one, reaches the STORY-007 column as-is | Accepted for this story. PRD 7.3 records names verbatim, and a body-size cap is out of scope (PRD 9.4). Flag it in the report for STORY-007 to consider |
| Importing `tests.test_v1_query_isolation` constructs its module-level `TestClient(app)` | A `TestClient` built without `with` starts no lifespan and is cheap, so the import is harmless. If that proves noisy, move the two helpers into `tests/test_openrouter_client.py` beside `_API_URL` and import them from there in both files |

---

## Acceptance Criteria

(Copied from story `STORY-006`)

- [ ] Given `temperature`, `top_p`, `max_tokens` and `stop` within range, when `translate_request` runs, then they become a `GenerationParams`; out of range is `V1RequestError(code="invalid_parameter", param=<name>)`; `max_completion_tokens` alone becomes `max_tokens`, and both present with different values is `invalid_parameter`.
- [ ] Given `n=2`, `logprobs=true`, `top_logprobs=3`, `response_format={"type":"json_object"}` or `json_schema`, or `modalities=["text","audio"]`, when it runs, then `code="unsupported_parameter"` with `param` set; given `n=1`, `logprobs=false`, `response_format={"type":"text"}` or `modalities=["text"]`, then each is accepted and none is recorded as ignored.
- [ ] Given non-empty `tools`, `functions`, `tool_choice` other than `"none"`, or `function_call`, when it runs, then `code="tools_not_supported"`; given `tools: []`, `tools: null` or `tool_choice: "none"`, then the request is accepted.
- [ ] Given `seed`, `user`, `presence_penalty`, `logit_bias`, `metadata`, `profile`, `ingress`, `openrouter_api_key` and an unknown key, plus `stream_options={"include_usage": true, "foo": 1}`, when it runs, then `ignored_params` is the sorted comma-joined names including `stream_options.foo` (values never appear), `include_usage` is `True`, and with nothing ignored it is `None`.
- [ ] Given a test over the classification table, when it runs, then the forwarded set equals `GenerationParams`' fields plus `max_completion_tokens`; and given a full request through `run_conversation` with an `httpx.MockTransport`, the upstream body's keys are still exactly STORY-001's set (PRD T5).
- [ ] All tasks completed
- [ ] `-m "not db"` run green without Docker; full suite green (flakes rerun)
- [ ] Follows existing patterns (pure module, `f"{param}: {rule}"` messages, no values in errors)
