---
story: STORY-004
prd: PRD-015
slug: v1-schemas
title: "/v1 request, response, chunk and error schemas"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-015-openai-compatible-endpoint
created: 2026-10-22
---

# Plan: /v1 request, response, chunk and error schemas

## Summary

This story adds a new module, `app/models/v1_schemas.py`, that defines the `/v1` wire shapes as pydantic v2 models (pydantic 2.13.5 in the venv). It contains:

- `ChatCompletionRequest`, with `extra="allow"`. `model` and `messages` are required. `messages` is typed `list[Any]`, so the normalizer judges each item and pydantic does not. Every parameter Section 7.1 reads is `Optional[Any] = None`, so STORY-006 classifies each value with its own `param`-bearing error and pydantic never raises a vaguer one first.
- The success models `ChatCompletion`, `Choice`, `AssistantMessage`, `Usage` and `HarnessCompletionInfo`.
- The stream models `ChatCompletionChunk`, `ChunkChoice` and `ChunkDelta`.
- The model list models `ModelList` and `ModelEntry`.
- The error models `ErrorResponse` and `ErrorDetail`.
- One id helper, `chat_completion_id(audit_id)`.

Section 7.6 shows two shapes that a plain `model_dump()` cannot produce. `delta` is `{}` on the finish chunk, and `usage` is absent from content chunks. Two small wrap serializers drop exactly those `None`s, and every other `null` (`logprobs`, `finish_reason`, `param`, `harness`) stays on the wire. `app/models/schemas.py` is not touched. Tests go in `tests/test_v1_schemas.py`. They need no DB and compare each model's serialization with the PRD example. A final block validates the same JSON with the OpenAI SDK's own types, behind `pytest.importorskip("openai")`. `openai` is not installed in the venv today, so the plan installs it for one verification run (Task 4).

## User Story

As the `/v1` implementer
I want pydantic models for the Chat Completions request, the completion, the stream chunk, the model list and the error object
So that every later story builds and asserts against one definition of the wire shapes

## Story Reference

- Story file: `.agents/stories/PRD-015-openai-compatible-endpoint/STORY-004-v1-schemas.md`
- PRD: `.agents/PRDs/PRD-015-openai-compatible-endpoint/PRD.md` (Sections 6.2, 7.1, 7.4, 7.5, 7.6, 7.7, 10)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/models/v1_schemas.py` (new), `tests/test_v1_schemas.py` (new) |
| Story | STORY-004 |
| PRD | PRD-015 |
| Epic Branch | `epic/PRD-015-openai-compatible-endpoint` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | The only skill in `.agents/skills/` is `frontend-design`, which does not apply to a backend schema module. The story lists `skills: []`. | — |

---

## Patterns to Follow

| Category | File:Lines | Pattern |
|----------|------------|---------|
| MODULE DOCSTRING | `app/models/messages.py:1-9` | A module docstring names the PRD section the module serves and what it deliberately is not (pure, no I/O, no settings) |
| SCHEMAS | `app/models/schemas.py:74-81` | Plain `BaseModel`, `Literal[...]` with a default for constant discriminators (`status: Literal["SUCCESS"] = "SUCCESS"`), `typing` generics (`List`, `Optional`) |
| CLASS DOCSTRINGS | `app/models/schemas.py:102-131` | A docstring explains *why* a shape is as it is, citing the PRD and its decisions |
| TEST SHAPE | `tests/test_schemas.py:38-53` | Build the model, then `assert response.model_dump() == {...full dict...}` |
| TEST REFUSAL | `tests/test_schemas.py:26-28, 116-125` | `pytest.raises(ValidationError)`, parametrized over the bad values |
| NO-DB TEST | `tests/conftest.py` (PRD-014 guard) | A test without storage fixtures is not marked `db`, and storage access fails it, so these tests must not import anything that connects |

### Schemas
```python
# SOURCE: app/models/schemas.py:74-81
class QuerySuccessResponse(BaseModel):
    status: Literal["SUCCESS"] = "SUCCESS"
    response: str
    audit_id: int
    model_used: str
    tokens_used: int
    pii_redacted: bool = False
    pii_entities_masked: List[str] = []
```

### Error naming (location and rule, never the value)
```python
# SOURCE: app/models/messages.py:34-40
class MessageNormalizationError(Exception):
    """A raw message is not a shape the pipeline can inspect.

    The message names a location (`messages[3]`, `content[1]`) and the rule
    that failed, never the offending value: ...
    """
```

### Tests
```python
# SOURCE: tests/test_schemas.py:38-53
def test_query_success_response_shape():
    response = QuerySuccessResponse(
        response="La respuesta del modelo",
        audit_id=1,
        model_used="gpt-4",
        tokens_used=45,
    )
    assert response.model_dump() == {
        "status": "SUCCESS",
        ...
    }
```

---

## Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Request parameter types | `Optional[Any] = None` for `stream_options`, `temperature`, `top_p`, `max_tokens`, `stop`, `max_completion_tokens`, `n`, `logprobs`, `top_logprobs`, `response_format`, `tools`, `tool_choice`, `functions`, `function_call`, `modalities`, `audio` and `user` | A typed `temperature: float` would turn `"hot"` into a generic 422/`invalid_request`, but Section 7.1 wants `invalid_parameter` with `param` set. STORY-006 classifies the values. Absent and explicit `null` remain distinguishable through `model_fields_set`, and STORY-006 needs that distinction |
| `model`, `messages`, `stream` | `model: str`, `messages: list[Any]`, `stream: bool = False` | AC 2: a missing value, or a `messages` that is not a list, fails validation. Pydantic v2 does not coerce an int to `str`, and a JSON object is not a list |
| Not declared | `openrouter_api_key`, `session_id`, `user_id` | Section 7.1 says they are unknown keys and are ignored. Leaving them undeclared puts them in `model_extra` |
| `finish_reason` | `FinishReason = Literal["stop", "length", "content_filter"]` | These are the values Section 7.4 names, and the OpenAI SDK's `Literal` accepts each of them. The schema refuses any other value, so STORY-009's translator must map an unknown upstream reason (for example OpenRouter's `"error"`) to `"stop"`. Section 7.4 already says "`"stop"` if the upstream omitted it". This is recorded as a risk below |
| Error `type` | `ErrorType = Literal["invalid_request_error", "authentication_error", "permission_error", "api_error"]` | These are the four values in Section 7.5. The 404 `model_not_found` (7.7) is `invalid_request_error`, as at OpenAI |
| Error `code` | `str` | The codes in the 7.5 table belong to STORY-010 and STORY-011. A `Literal` here would make those stories edit this file for every new code |
| `ErrorDetail.harness` | `Optional[dict[str, Any]] = None`, serialized as `null` when absent | It is `None` for a request-translation failure, which has no pipeline response. Keeping the key keeps the error object one shape, like `param: null` |
| Success `harness` | Typed `HarnessCompletionInfo(audit_id, pii_redacted, pii_entities_masked)` | Section 7.4 fixes these three fields. They come from `QuerySuccessResponse` |
| Chunk `delta` | A wrap `model_serializer` on `ChunkDelta` drops the `None` keys | Section 7.6 shows `"delta":{}` on the finish chunk and `{"role":"assistant","content":"…"}` on the content chunk |
| Chunk `usage` | `Optional[Usage] = None`. A wrap serializer on `ChatCompletionChunk` drops the key only when it is `None` | Section 7.6 shows no `usage` on content and finish chunks, and `usage` alongside `choices: []` on the usage chunk. The SDK's `usage` is optional, so both forms validate |
| Chunk choice `logprobs` | Not declared | Section 7.6 does not show it. The completion's choice has it (7.4, AC 3) |
| Id helper | `chat_completion_id(audit_id: int) -> str` and `CHAT_COMPLETION_ID_PREFIX = "chatcmpl-harness-"` | The story's technical notes ask for one function, used for the body, the `X-Harness-Audit-Id` header and every chunk. The module has no `created` clock and no `owned_by` helper: the translator (STORY-009), the SSE writer (STORY-013) and STORY-012 own those |
| Serialization entry point | Callers use `model_dump(mode="json")` / `model_dump_json()`. No `by_alias`, no `exclude_none` | Two targeted serializers keep `exclude_none` from erasing the `null`s that the PRD examples require |

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/models/v1_schemas.py` | CREATE | Every `/v1` wire model and the id helper |
| `tests/test_v1_schemas.py` | CREATE | Parse and serialize tests against the PRD examples, plus the guarded OpenAI SDK validation |

`app/models/schemas.py`, `app/models/__init__.py` and `requirements.txt` are unchanged. `openai` becomes a test-only dependency in STORY-015 (`requirements-e2e.txt`).

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Request model and id helper

- **File**: `app/models/v1_schemas.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring: "The `/v1` wire shapes (PRD-015 Sections 7.1, 7.4-7.7)." Say that it is pure (no I/O, no settings, no `app` import) and that `/query`'s shapes stay in `schemas.py`.
  - Imports: `from typing import Any, List, Literal, Optional` and `from pydantic import BaseModel, ConfigDict, model_serializer`.
  - `CHAT_COMPLETION_ID_PREFIX = "chatcmpl-harness-"` and `def chat_completion_id(audit_id: int) -> str: return f"{CHAT_COMPLETION_ID_PREFIX}{audit_id}"`. Its docstring says that the id is derived from the audit id so that a client log line leads to the row (7.4), and that the body, the header and every chunk call this function.
  - `class ChatCompletionRequest(BaseModel)` with `model_config = ConfigDict(extra="allow")`:
    - `model: str`, `messages: List[Any]`, `stream: bool = False`, `stream_options: Optional[Any] = None`
    - forwarded: `temperature`, `top_p`, `max_tokens`, `stop`, `max_completion_tokens`, each `Optional[Any] = None`
    - reject-unless-default: `n`, `logprobs`, `top_logprobs`, `response_format`, `tools`, `tool_choice`, `functions`, `function_call`, `modalities`, `audio`, each `Optional[Any] = None`
    - `user: Optional[Any] = None`. It is read only to be recorded (D1).
    - The docstring says why the parameters are `Any` (STORY-006 classifies them and reports `param`), that absent and `null` are told apart with `model_fields_set`, that `model_extra` holds the unknown keys, and that `openrouter_api_key` / `session_id` / `user_id` are not declared on purpose.
- **Mirror**: `app/models/messages.py:1-9` (docstring), `app/models/schemas.py:7-24` (field comments)
- **Validate**: `C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe -c "from app.models.v1_schemas import ChatCompletionRequest, chat_completion_id"`

### Task 2: Success, chunk and model-list models

- **File**: `app/models/v1_schemas.py`
- **Action**: UPDATE
- **Implement**:
  - `FinishReason = Literal["stop", "length", "content_filter"]`
  - `class Usage(BaseModel)`: `prompt_tokens: int`, `completion_tokens: int`, `total_tokens: int`. The docstring says that a missing split is `0` and that the total is still the reported total (7.4).
  - `class AssistantMessage(BaseModel)`: `role: Literal["assistant"] = "assistant"`, `content: str`
  - `class Choice(BaseModel)`: `index: int = 0`, `message: AssistantMessage`, `logprobs: None = None`, `finish_reason: FinishReason`
  - `class HarnessCompletionInfo(BaseModel)`: `audit_id: int`, `pii_redacted: bool = False`, `pii_entities_masked: List[str] = []` (pydantic copies the mutable default per instance. `tests/test_schemas.py:243` already relies on this)
  - `class ChatCompletion(BaseModel)`: `id: str`, `object: Literal["chat.completion"] = "chat.completion"`, `created: int`, `model: str`, `choices: List[Choice]`, `usage: Usage`, `harness: HarnessCompletionInfo`
  - `class ChunkDelta(BaseModel)`: `role: Optional[Literal["assistant"]] = None`, `content: Optional[str] = None`. Add this serializer:
    ```python
    @model_serializer(mode="wrap")
    def _drop_unset(self, handler):
        # Section 7.6: the finish chunk's delta is `{}`, not
        # `{"role": null, "content": null}`.
        return {key: value for key, value in handler(self).items() if value is not None}
    ```
  - `class ChunkChoice(BaseModel)`: `index: int = 0`, `delta: ChunkDelta`, `finish_reason: Optional[FinishReason] = None` (serialized as `null` on the content chunk)
  - `class ChatCompletionChunk(BaseModel)`: `id: str`, `object: Literal["chat.completion.chunk"] = "chat.completion.chunk"`, `created: int`, `model: str`, `choices: List[ChunkChoice]`, `usage: Optional[Usage] = None`. It gets a wrap serializer that removes the `usage` key only when it is `None`.
  - `class ModelEntry(BaseModel)`: `id: str`, `object: Literal["model"] = "model"`, `created: int = 0`, `owned_by: str`
  - `class ModelList(BaseModel)`: `object: Literal["list"] = "list"`, `data: List[ModelEntry]`
- **Mirror**: `app/models/schemas.py:74-81`
- **Gotcha**: with `mode="wrap"`, `handler(self)` returns a dict in both python and json mode. Check that `model_dump()`, `model_dump(mode="json")` and `model_dump_json()` all drop the keys. The tests in Task 4 assert all three.
- **Validate**: the same import command, with the new names

### Task 3: Error models

- **File**: `app/models/v1_schemas.py`
- **Action**: UPDATE
- **Implement**:
  - `ErrorType = Literal["invalid_request_error", "authentication_error", "permission_error", "api_error"]`
  - `class ErrorDetail(BaseModel)`: `message: str`, `type: ErrorType`, `param: Optional[str] = None`, `code: str`, `harness: Optional[dict[str, Any]] = None`. The docstring says that `message` names the rule and never echoes content (6.3), that `harness` carries the pipeline response's own fields, and that it is `null` when no pipeline ran.
  - `class ErrorResponse(BaseModel)`: `error: ErrorDetail`. The docstring says this same object is the SSE `error` event payload after commit (7.6).
- **Mirror**: `app/models/messages.py:34-40` (the docstring's message rule)
- **Validate**: the same import command

### Task 4: Tests

- **File**: `tests/test_v1_schemas.py`
- **Action**: CREATE
- **Implement**: Module docstring: "PRD-015 STORY-004: the /v1 wire shapes against PRD Sections 7.1 and 7.4-7.7. No DB." Define module constants that copy the PRD examples verbatim: `_COMPLETION_EXAMPLE` (7.4, with `content` set to a concrete string), `_ERROR_EXAMPLE` (7.5), `_MODELS_EXAMPLE` (7.7), and three chunk dicts from 7.6 with a fixed `created`. Tests:
  1. **AC 1**: `test_request_keeps_unknown_keys_in_model_extra`. Parse `{"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "hi"}], "stream": True, "seed": 7, "profile": "chat", "session_id": "x"}`. Assert the typed fields, `model_extra == {"seed": 7, "profile": "chat", "session_id": "x"}`, and that `model_dump()` contains every input key (nothing dropped).
  2. **AC 1**: `test_request_defaults`. `stream is False`, and every optional parameter is `None` and absent from `model_fields_set`.
  3. `test_request_tells_absent_from_explicit_null`. `{"n": None}` puts `"n"` in `model_fields_set`. Omitting it does not.
  4. `test_request_parameters_are_not_typed_by_pydantic`. `temperature="hot"` and `n=3` parse without error, because STORY-006 judges them.
  5. **AC 2**: `test_request_missing_or_malformed_required_fields_fail`, parametrized over: no `model`, no `messages`, `messages` as `"hi"`, `messages` as `{"role": "user"}`, `model` as `5`. Each one raises `ValidationError`.
  6. **AC 2**: `test_request_messages_items_stay_raw`. `messages=[{"role": "developer", "content": [{"type": "text", "text": "x"}]}, 3, None]` parses, and `messages` equals the input unchanged (the normalizer judges it).
  7. **AC 3**: `test_completion_matches_section_7_4`. Build `ChatCompletion(id=chat_completion_id(1842), created=1792569600, model="openai/gpt-4o", choices=[Choice(message=AssistantMessage(content=...), finish_reason="stop")], usage=Usage(812, 96, 908), harness=HarnessCompletionInfo(audit_id=1842))` and assert `model_dump(mode="json") == _COMPLETION_EXAMPLE`. Also assert `json.loads(model_dump_json()) == _COMPLETION_EXAMPLE`.
  8. `test_chat_completion_id_is_the_one_derivation`. `chat_completion_id(1842) == "chatcmpl-harness-1842"` and it starts with `CHAT_COMPLETION_ID_PREFIX`.
  9. **AC 3**: `test_completion_refuses_an_unknown_finish_reason`. `"tool_calls"` and `"error"` raise.
  10. **AC 4**: `test_chunks_match_section_7_6`, parametrized over the content, finish and usage chunks. Assert each dumps exactly to its example. The finish chunk's delta is `{}`. The usage chunk has `choices == []` and a `usage`. The content and finish chunks have no `usage` key and have `"finish_reason": None` / `"stop"`. Check `model_dump()`, `model_dump(mode="json")` and `json.loads(model_dump_json())`.
  11. **AC 4**: `test_model_list_matches_section_7_7`
  12. **AC 4**: `test_error_matches_section_7_5`. This includes `harness` inside `error` and `param: None`.
  13. `test_error_without_harness_keeps_the_key_as_null`
  14. `test_error_type_is_one_of_the_four`. `type="rate_limit_error"` raises, because `429` is never sent (PRD-013 D5).
  15. **AC 5**: the SDK block. `openai = pytest.importorskip("openai")` inside each test (not at module level, so tests 1-14 run without the SDK):
      - `test_openai_sdk_validates_the_completion`. `openai.types.chat.ChatCompletion.model_validate(json.loads(completion.model_dump_json()))` succeeds, `.choices[0].finish_reason == "stop"`, and `.model_extra["harness"]["audit_id"] == 1842` (the SDK keeps the extension, 7.4).
      - `test_openai_sdk_validates_each_chunk`, parametrized over the three chunks: `openai.types.chat.ChatCompletionChunk.model_validate(...)` succeeds.
- **Mirror**: `tests/test_schemas.py:38-53`, `tests/test_schemas.py:116-125`
- **Validate**:
  ```bash
  C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe -m pytest tests/test_v1_schemas.py -q
  # The SDK tests show as skipped: openai is not in the venv today.
  # Run them once for real, then record the version in the report:
  C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe -m pip install openai
  C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe -m pytest tests/test_v1_schemas.py -q -rs   # 0 skipped
  ```
  Leaving `openai` installed is fine, because STORY-015 pins it in `requirements-e2e.txt`. Do not add it to `requirements.txt`.

---

## End-to-End Tests

This story adds no route, so there is nothing to call over HTTP. Its end-to-end check is that the OpenAI SDK accepts the shapes:

- [ ] With `openai` installed, the AC 5 tests pass (none skipped). The report records the `openai` version used
- [ ] `python -c "import app.main"` still imports, so the new module does not break the app's import graph
- [ ] `tests/test_schemas.py` passes unchanged, which shows that `/query`'s shapes did not move

---

## Validation

```bash
C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe -m pytest tests/test_v1_schemas.py tests/test_schemas.py -q -rs
C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe -m pytest -m "not db" -q    # Docker-free sweep, no other test changes
git diff --stat main -- app/models/schemas.py                                    # empty
```

---

## Risks

| Risk | Mitigation |
|------|-----------|
| An upstream `finish_reason` outside the `Literal` (OpenRouter can send `"error"` or `"tool_calls"`) fails `ChatCompletion` construction with a 500 | The Literal is deliberate, because the SDK's own Literal is just as strict and a client would fail anyway. STORY-009's translator maps anything else to `"stop"`. Test 9 pins the refusal so that STORY-009 sees the rule |
| A wrap `model_serializer` changes the JSON schema or breaks `model_dump_json` | Tests 10 and 7 assert the python, json-mode and JSON-string dumps. FastAPI's OpenAPI generation for `/v1` routes is STORY-009's, and wrap serializers keep the field schema |
| Someone later "simplifies" serialization with `exclude_none=True` and erases `logprobs: null`, `finish_reason: null`, `param: null` and `harness: null` | Tests 7, 10, 12 and 13 assert those `null`s explicitly |
| `openai` is absent, so AC 5 silently never runs | Task 4 runs it once with the SDK installed. `-rs` makes skips visible. STORY-015 makes it a pinned test dependency |
| The `List[str] = []` default on `HarnessCompletionInfo.pii_entities_masked` is shared between instances | Pydantic deep-copies field defaults, and the existing `/query` model relies on the same behaviour (`tests/test_schemas.py:243`) |

---

## Acceptance Criteria

(Copied from story `STORY-004`)

- [ ] Given a request body with `model`, `messages`, `stream` and unknown keys such as `seed` and `profile`, when `ChatCompletionRequest` parses it, then the known fields are typed, the unknown keys are preserved (`extra="allow"`, readable via `model_extra`) and nothing is dropped.
- [ ] Given a body without `model` or without `messages`, or with `messages` not a list, when it parses, then validation fails; `messages` items stay raw mappings (the normalizer judges them, not pydantic).
- [ ] Given a `ChatCompletion` built with audit id 1842, when it is serialized, then it matches PRD Section 7.4's example field for field: `id == "chatcmpl-harness-1842"`, `object == "chat.completion"`, `choices[0]` with `index`, `message.role == "assistant"`, `logprobs: null` and `finish_reason`, a `usage` of three integers, and a `harness` object.
- [ ] Given a `ChatCompletionChunk`, a `ModelList` and an `ErrorResponse`, when serialized, then they match Sections 7.6, 7.7 and 7.5 respectively, including `choices: []` on the usage chunk and the `harness` object inside `error`.
- [ ] Given each example serialized to JSON, when the OpenAI Python SDK's own types validate it (`ChatCompletion.model_validate`, `ChatCompletionChunk.model_validate`), then it validates; the test is skipped when `openai` is not installed.
- [ ] All tasks completed
- [ ] Backend imports and starts without error
- [ ] Follows existing patterns
