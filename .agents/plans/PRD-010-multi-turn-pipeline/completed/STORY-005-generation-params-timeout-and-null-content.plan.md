---
story: STORY-005
prd: PRD-010
slug: generation-params-timeout-and-null-content
title: "GenerationParams allowlist, configurable timeout and explicit null-content error"
type: FEATURE
complexity: MEDIUM
epic_branch: epic/PRD-010-multi-turn-pipeline        # all stories commit here, no per-story branch
created: 2026-09-17
---

# Plan: GenerationParams allowlist, configurable timeout and explicit null-content error

## Summary

`app/services/openrouter_client.py` gains three things, all scoped to the client only (Technical Notes: "This story adds no pipeline change"). First, a frozen `GenerationParams(temperature, max_tokens, top_p, stop)` dataclass whose `__post_init__` range-validates every field (bool rejected explicitly for `max_tokens` since `bool` subclasses `int`), plus a `UnsupportedParameterError` and a `GenerationParams.from_mapping(raw)` classmethod that rejects any key outside the four-field allowlist, naming every unsupported key sorted. `call_openrouter` gains `params: Optional[GenerationParams] = None`; when set, only its non-`None` fields are merged into the payload, so `params=None` (every existing caller, ~90 injected stubs plus `query_pipeline.py`) keeps producing today's exact payload. Second, the module-level `_TIMEOUT_SECONDS = 30.0` constant is deleted; the client now builds its default `httpx.Client` with `timeout=settings.OPENROUTER_TIMEOUT_SECONDS`, read inside the function body (not cached at import) so tests can monkeypatch it per call. Third, a `choices[0].message.content is None` response now raises `OpenRouterError("OpenRouter returned no text content (finish_reason=<value>)")` instead of falling through to `data["usage"]["total_tokens"]` and failing with an unrelated `KeyError`-shaped "unexpected response shape" message; when `message.tool_calls` is present the message additionally names PRD-016. Neither message ever contains `resolved_key`, matching the existing `test_api_key_never_appears_in_error_message` pattern. The router's existing generic `OpenRouterError` → 502 mapping (`app/routers/query.py`) needs no code change; one new router-level test pins that this specific error shape still maps to 502.

## User Story

As a compliance admin
I want generation parameters limited to a validated allowlist, the timeout to be configurable, and a content-less upstream reply to fail with a clear reason
So that multi-turn exposes no more upstream surface than needed and slow large contexts don't time out at 30 s

## Story Reference

- Story file: `.agents/stories/PRD-010-multi-turn-pipeline/STORY-005-generation-params-timeout-and-null-content.md`
- PRD: `.agents/PRDs/PRD-010-multi-turn-pipeline/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | FEATURE |
| Complexity | MEDIUM |
| Systems Affected | `app/services/openrouter_client.py`, `tests/test_openrouter_client.py`, `tests/test_query_router.py` |
| Story | STORY-005 |
| PRD | PRD-010 |
| Epic Branch | `epic/PRD-010-multi-turn-pipeline` (commit directly on this branch) |

---

## Skills In Use

None. Story frontmatter lists `skills: []` and Technical Notes states "Skills: none applicable." The repo's one skill (`frontend-design`) governs chat-UI copy and bubble components; this story touches neither.

---

## Patterns to Follow

### Settings read at call time, not cached at import (already the client's own pattern for the API key)
```python
// SOURCE: app/services/openrouter_client.py:34
resolved_key = api_key or settings.OPENROUTER_API_KEY
```
`settings.OPENROUTER_TIMEOUT_SECONDS` is read the same way, inside `call_openrouter`, so `monkeypatch.setattr(settings, "OPENROUTER_TIMEOUT_SECONDS", 7.5)` takes effect per test (AC4; PRD Technical Notes: "Read the timeout per call... so tests can monkeypatch it").

### Settings validator already shipped (STORY-002) — nothing to add in `app/config.py`
```python
// SOURCE: app/config.py:181-190
@field_validator("OPENROUTER_TIMEOUT_SECONDS")
@classmethod
def _validate_openrouter_timeout_seconds(cls, value: float) -> float:
    """A non-positive timeout would hang forever or fail every call instantly (PRD-010)."""
    if value <= 0:
        raise ValueError(...)
    return value
```
`OPENROUTER_TIMEOUT_SECONDS: float = 120.0` and its validator already exist. This story is purely a consumer.

### Plain-`Exception` custom error style used throughout the services layer
```python
// SOURCE: app/models/messages.py:33-39
class MessageNormalizationError(Exception):
    """A raw message is not a shape the pipeline can inspect.

    The message names a location..., never the offending value...
    """
```
`UnsupportedParameterError` follows the same shape: a bare `Exception` subclass with a docstring explaining when it fires and why, no custom `__init__`.

### `Optional[...]` allowlist dataclass with per-field `None` defaults (mirrors `Message`)
```python
// SOURCE: app/models/messages.py:21-31
@dataclass(frozen=True)
class Message:
    role: Role
    content: str
```
`GenerationParams` is `@dataclass(frozen=True)` too; frozen does not block `__post_init__`, which is where every field's range check lives (no mutation needed, only validation).

### Router's existing generic `OpenRouterError` → 502 mapping (unchanged, only characterized further)
```python
// SOURCE: app/routers/query.py:96-106 (import) and the mapping around line 105
except OpenRouterError as exc:
    ... -> HTTPException(status_code=502, ...)
```
```python
// SOURCE: tests/test_query_router.py:255-267
def test_openrouter_failure_logged_with_error_and_returns_502(temp_db, monkeypatch):
    def _raise_openrouter_error(prompt, model="gpt-4", api_key=None):
        raise OpenRouterError("boom")

    monkeypatch.setattr("app.routers.query.call_openrouter", _raise_openrouter_error)

    before = _count_audit_rows()
    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": "hello world"}
    )

    assert response.status_code == 502
    assert _count_audit_rows() == before + 1
```
The AC5 "through `POST /query` that maps to 502" test mirrors this exactly, with the stub raising the new null-content-shaped message instead of `"boom"`.

### Existing fake-client + payload-assertion test pattern (STORY-003/004)
```python
// SOURCE: tests/test_openrouter_client.py:20-39
class _FakeClient:
    def __init__(self, response=None, exc=None):
        ...
    def post(self, url, headers=None, json=None):
        self.requests.append({"url": url, "headers": headers, "json": json})
        ...

def _response(content="Hello!", tokens=45, status_code=200, body=None):
    ...
```
Reused as-is for the new params-serialization tests; a small `_null_content_response(finish_reason=..., tool_calls=None)` helper is added alongside it for the null-content tests, and a client stub that raises `AssertionError` if `.post` is ever called proves the "before any HTTP call" AC for invalid params.

### Injected `call_openrouter` stubs are untouched by this story
```python
// SOURCE: tests/test_query_router.py:279 (one of ~19 identical stubs across ~15 files)
def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
```
None of these ~90 stub call sites are touched: `query_pipeline.py`'s only call site never passes `params=`, so every stub's 3-argument signature keeps matching (Technical Notes).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/openrouter_client.py` | UPDATE | Add `GenerationParams`, `UnsupportedParameterError`, `from_mapping`; `call_openrouter` gains `params`; payload merges only non-`None` param fields; `_TIMEOUT_SECONDS` constant removed, default `httpx.Client` built with `settings.OPENROUTER_TIMEOUT_SECONDS`; `content is None` raises the explicit `OpenRouterError` (with the PRD-016 addendum when `tool_calls` is present) |
| `tests/test_openrouter_client.py` | UPDATE | Update the STORY-003 timeout characterization test with the required comment and settings-based value; add a monkeypatched-timeout test (AC4); add `GenerationParams`/`from_mapping`/`UnsupportedParameterError` tests (allowlist rejection sorted, each range violation, before-any-HTTP-call); add params-in-payload serialization test; add null-content tests (plain, with `tool_calls`, api-key-absence) |
| `tests/test_query_router.py` | UPDATE | Add one test: a null-content-shaped `OpenRouterError` from a stubbed `call_openrouter` still maps to 502 through `POST /query` (AC5) |

No production file besides `app/services/openrouter_client.py` changes. `app/config.py` already has `OPENROUTER_TIMEOUT_SECONDS` and its validator (STORY-002). `app/services/query_pipeline.py` and `app/routers/query.py` need no change — the router's `except OpenRouterError` mapping is generic and already covers the new message shape.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add `GenerationParams`, `UnsupportedParameterError`, and `from_mapping`

- **File**: `app/services/openrouter_client.py`
- **Action**: UPDATE
- **Implement**:
  1. Extend the `typing` import to `Any, Mapping, Optional, Sequence, Union`.
  2. Add module-level constants: `_ALLOWED_GENERATION_PARAMS = frozenset({"temperature", "max_tokens", "top_p", "stop"})` and `_MAX_STOP_SEQUENCES = 4`.
  3. Add `class UnsupportedParameterError(Exception):` with a docstring stating it is raised by `GenerationParams` construction (direct or via `from_mapping`), always before any HTTP call.
  4. Add:
     ```python
     @dataclass(frozen=True)
     class GenerationParams:
         """The only generation parameters call_openrouter may forward (PRD-010 F3, T5).

         Every field defaults to None and is sent only when set. from_mapping is
         PRD-014's entry point; nothing in this PRD calls it in production.
         """

         temperature: Optional[float] = None   # 0.0 <= t <= 2.0
         max_tokens: Optional[int] = None       # >= 1
         top_p: Optional[float] = None          # 0.0 < p <= 1.0
         stop: Optional[Union[str, Sequence[str]]] = None   # <= 4 sequences

         def __post_init__(self) -> None:
             if self.temperature is not None and not (0.0 <= self.temperature <= 2.0):
                 raise UnsupportedParameterError(
                     f"temperature must be between 0.0 and 2.0, got {self.temperature!r}"
                 )
             if self.max_tokens is not None:
                 # bool is a subclass of int: True/False must not slip past >= 1.
                 if isinstance(self.max_tokens, bool) or self.max_tokens < 1:
                     raise UnsupportedParameterError(
                         f"max_tokens must be an integer >= 1, got {self.max_tokens!r}"
                     )
             if self.top_p is not None and not (0.0 < self.top_p <= 1.0):
                 raise UnsupportedParameterError(
                     f"top_p must be greater than 0.0 and at most 1.0, got {self.top_p!r}"
                 )
             if self.stop is not None:
                 if isinstance(self.stop, str):
                     pass
                 elif isinstance(self.stop, (list, tuple)):
                     if len(self.stop) > _MAX_STOP_SEQUENCES:
                         raise UnsupportedParameterError(
                             f"stop must have at most {_MAX_STOP_SEQUENCES} sequences, got {len(self.stop)}"
                         )
                     if not all(isinstance(s, str) for s in self.stop):
                         raise UnsupportedParameterError(
                             f"stop sequences must all be strings, got {self.stop!r}"
                         )
                 else:
                     raise UnsupportedParameterError(
                         f"stop must be a string or a list of up to {_MAX_STOP_SEQUENCES} strings, got {self.stop!r}"
                     )

         @classmethod
         def from_mapping(cls, raw: Mapping[str, Any]) -> "GenerationParams":
             """PRD-014's entry point. Raises for any key outside the allowlist, sorted."""
             unsupported = sorted(set(raw) - _ALLOWED_GENERATION_PARAMS)
             if unsupported:
                 raise UnsupportedParameterError(
                     f"unsupported parameter(s): {', '.join(unsupported)}"
                 )
             return cls(**{key: raw[key] for key in _ALLOWED_GENERATION_PARAMS if key in raw})
     ```
     Place this block after `OpenRouterError` and before `OpenRouterResult`.
- **Mirror**: `app/models/messages.py:21-39` (frozen dataclass + plain-`Exception` style)
- **Validate**: `python -c "from app.services.openrouter_client import GenerationParams, UnsupportedParameterError; GenerationParams.from_mapping({'temperature': 0.2})"`

### Task 2: `call_openrouter` gains `params`, reads the timeout from settings, and raises on `null` content

- **File**: `app/services/openrouter_client.py`
- **Action**: UPDATE
- **Implement**:
  1. Delete the module constant `_TIMEOUT_SECONDS = 30.0`.
  2. Add `params: Optional[GenerationParams] = None` as the fourth parameter of `call_openrouter`, before `client`.
  3. After building `payload` (unchanged: `model` + `messages`), add:
     ```python
     if params is not None:
         for field in ("temperature", "max_tokens", "top_p", "stop"):
             value = getattr(params, field)
             if value is not None:
                 payload[field] = value
     ```
  4. Change `http_client = client or httpx.Client(timeout=_TIMEOUT_SECONDS)` to `http_client = client or httpx.Client(timeout=settings.OPENROUTER_TIMEOUT_SECONDS)`.
  5. Replace the response-parsing block. Split content extraction (checked for `None`) from usage extraction, so a missing `usage` key never masks the null-content message and vice versa:
     ```python
     try:
         data = resp.json()
         choice = data["choices"][0]
         message = choice["message"]
         content = message["content"]
     except (KeyError, IndexError, ValueError) as exc:
         raise OpenRouterError(
             f"OpenRouter returned an unexpected response shape: {exc}"
         ) from exc

     if content is None:
         finish_reason = choice.get("finish_reason")
         error_message = f"OpenRouter returned no text content (finish_reason={finish_reason})"
         if message.get("tool_calls") is not None:
             error_message += "; tool calls are not supported (PRD-016)"
         raise OpenRouterError(error_message)

     try:
         tokens_used = data["usage"]["total_tokens"]
     except (KeyError, IndexError, ValueError) as exc:
         raise OpenRouterError(
             f"OpenRouter returned an unexpected response shape: {exc}"
         ) from exc
     ```
  6. Leave the empty-`messages` guard, key resolution, headers, `owns_client`/`finally` close, and the `OpenRouterResult(...)` return untouched.
- **Mirror**: existing structure at `app/services/openrouter_client.py:44-70`; the resolved-key-never-in-message discipline already followed by `test_api_key_never_appears_in_error_message`
- **Validate**: `python -c "import app.services.openrouter_client"` (no leftover reference to the deleted `_TIMEOUT_SECONDS`)

### Task 3: Update the STORY-003 timeout characterization test and add the settings-monkeypatch test (AC3, AC4)

- **File**: `tests/test_openrouter_client.py`
- **Action**: UPDATE
- **Implement**:
  1. In `test_characterization_default_client_uses_todays_timeout` (lines 148-167): update the docstring to state the constant is now gone, and change the final assertion line to:
     ```python
     assert captured["kwargs"] == {"timeout": 120.0}  # PRD-010 STORY-005: timeout from settings (default 120.0)
     ```
     Keep everything else in the test (the `_StubHttpxClient`, the `monkeypatch.setattr(httpx, "Client", ...)`) unchanged — it still proves the *default* `httpx.Client` construction, only the source of the value moved from a module constant to `settings.OPENROUTER_TIMEOUT_SECONDS`.
  2. Add a new test directly after it:
     ```python
     def test_timeout_setting_is_read_per_call_not_cached_at_import(monkeypatch):
         """AC4: settings.OPENROUTER_TIMEOUT_SECONDS is read inside call_openrouter,
         so a monkeypatched value takes effect without reimporting the module."""
         monkeypatch.setattr(settings, "OPENROUTER_TIMEOUT_SECONDS", 7.5)
         captured = {}

         class _StubHttpxClient:
             def __init__(self, *args, **kwargs):
                 captured["kwargs"] = kwargs

             def post(self, url, headers=None, json=None):
                 return _response()

             def close(self):
                 pass

         monkeypatch.setattr(httpx, "Client", _StubHttpxClient)

         call_openrouter([Message("user", "hello")], api_key="k")

         assert captured["kwargs"] == {"timeout": 7.5}
     ```
- **Mirror**: the test being updated, `tests/test_openrouter_client.py:148-167`
- **Validate**: `python -m pytest tests/test_openrouter_client.py -k timeout -q`

### Task 4: Add `GenerationParams` / `from_mapping` / `UnsupportedParameterError` tests (AC1, AC2)

- **File**: `tests/test_openrouter_client.py`
- **Action**: UPDATE
- **Implement**:
  1. Add `from app.services.openrouter_client import GenerationParams, UnsupportedParameterError` to the existing `from app.services.openrouter_client import (...)` import.
  2. Add a section comment `# --- PRD-010 STORY-005: GenerationParams allowlist and range validation ---` followed by:
     ```python
     def test_from_mapping_rejects_unsupported_keys_named_and_sorted():
         with pytest.raises(UnsupportedParameterError, match=r"logit_bias, stream, tools"):
             GenerationParams.from_mapping(
                 {"logit_bias": {}, "tools": [], "stream": True, "temperature": 0.2}
             )


     def test_from_mapping_builds_only_allowed_fields():
         params = GenerationParams.from_mapping({"temperature": 0.2, "max_tokens": 100})
         assert params == GenerationParams(temperature=0.2, max_tokens=100)


     @pytest.mark.parametrize(
         "kwargs",
         [
             {"temperature": 3},
             {"top_p": 0},
             {"max_tokens": 0},
             {"max_tokens": True},
             {"stop": ["a", "b", "c", "d", "e"]},
             {"stop": ["a", 2]},
         ],
     )
     def test_out_of_range_params_raise_naming_field_and_range(kwargs):
         with pytest.raises(UnsupportedParameterError):
             GenerationParams(**kwargs)


     def test_invalid_params_raise_before_any_http_call():
         class _ExplodingClient:
             def post(self, *args, **kwargs):
                 raise AssertionError("HTTP call must not happen for invalid params")

         with pytest.raises(UnsupportedParameterError):
             call_openrouter(
                 [Message("user", "hi")],
                 api_key="k",
                 params=GenerationParams.from_mapping({"temperature": 3}),
                 client=_ExplodingClient(),
             )


     def test_params_only_non_none_fields_reach_the_payload():
         client = _FakeClient(response=_response())
         params = GenerationParams(temperature=0.2, max_tokens=100)

         call_openrouter([Message("user", "hi")], api_key="k", params=params, client=client)

         payload = client.requests[0]["json"]
         assert payload["temperature"] == 0.2
         assert payload["max_tokens"] == 100
         assert "top_p" not in payload
         assert "stop" not in payload


     def test_params_none_leaves_payload_byte_identical_to_story_003():
         """AC2: same assertion as test_characterization_payload_shape_is_byte_identical,
         restated here with params passed explicitly as None."""
         client = _FakeClient(response=_response())

         call_openrouter([Message("user", "hello")], model="gpt-4", api_key="k", params=None, client=client)

         payload = client.requests[0]["json"]
         expected = {"model": "gpt-4", "messages": [{"role": "user", "content": "hello"}]}
         assert json.dumps(payload, sort_keys=False) == json.dumps(expected, sort_keys=False)
     ```
- **Mirror**: `tests/test_openrouter_client.py:122-132` (the byte-identical characterization test being restated) and the existing `_FakeClient`/`_response` fixtures
- **Validate**: `python -m pytest tests/test_openrouter_client.py -k "params or GenerationParams" -q`

### Task 5: Add `null`-content tests (AC5)

- **File**: `tests/test_openrouter_client.py`
- **Action**: UPDATE
- **Implement**:
  1. Add a `_null_content_response` helper next to `_response`:
     ```python
     def _null_content_response(finish_reason="stop", tool_calls=None, tokens=10):
         request = httpx.Request("POST", _API_URL)
         message = {"content": None}
         if tool_calls is not None:
             message["tool_calls"] = tool_calls
         payload = {
             "choices": [{"message": message, "finish_reason": finish_reason}],
             "usage": {"total_tokens": tokens},
         }
         return httpx.Response(200, request=request, json=payload)
     ```
  2. Add a section comment `# --- PRD-010 STORY-005: explicit null-content error ---` followed by:
     ```python
     def test_null_content_raises_with_finish_reason():
         client = _FakeClient(response=_null_content_response(finish_reason="length"))

         with pytest.raises(OpenRouterError, match=r"finish_reason=length"):
             call_openrouter([Message("user", "hi")], api_key="k", client=client)


     def test_null_content_with_tool_calls_names_prd_016():
         client = _FakeClient(
             response=_null_content_response(finish_reason="tool_calls", tool_calls=[{"id": "1"}])
         )

         with pytest.raises(OpenRouterError, match=r"tool calls are not supported \(PRD-016\)"):
             call_openrouter([Message("user", "hi")], api_key="k", client=client)


     def test_null_content_without_tool_calls_omits_prd_016_note():
         client = _FakeClient(response=_null_content_response(finish_reason="stop"))

         with pytest.raises(OpenRouterError) as exc_info:
             call_openrouter([Message("user", "hi")], api_key="k", client=client)

         assert "PRD-016" not in str(exc_info.value)


     def test_null_content_error_never_contains_api_key():
         client = _FakeClient(response=_null_content_response())

         with pytest.raises(OpenRouterError) as exc_info:
             call_openrouter([Message("user", "hi")], api_key="super-secret-key", client=client)

         assert "super-secret-key" not in str(exc_info.value)
     ```
- **Mirror**: `tests/test_openrouter_client.py:100-113` (`test_malformed_response_body_raises_openrouter_error`, `test_api_key_never_appears_in_error_message`)
- **Validate**: `python -m pytest tests/test_openrouter_client.py -k null_content -q`

### Task 6: Router-level 502 mapping test for the null-content error shape (AC5)

- **File**: `tests/test_query_router.py`
- **Action**: UPDATE
- **Implement**: Directly after `test_openrouter_failure_logged_with_error_and_returns_502` (line ~267), add:
  ```python
  def test_null_content_openrouter_error_maps_to_502(temp_db, monkeypatch):
      """PRD-010 STORY-005 AC5: the client's explicit null-content message is just
      another OpenRouterError to the router, so the existing 502 mapping covers it
      with no router change."""

      def _raise_null_content_error(prompt, model="gpt-4", api_key=None):
          raise OpenRouterError("OpenRouter returned no text content (finish_reason=length)")

      monkeypatch.setattr("app.routers.query.call_openrouter", _raise_null_content_error)

      before = _count_audit_rows()
      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": "hello world"}
      )

      assert response.status_code == 502
      assert _count_audit_rows() == before + 1
  ```
  No import changes needed: `OpenRouterError` is already imported at the top of this file (line 26).
- **Mirror**: `tests/test_query_router.py:255-267` (the existing generic-failure 502 test, exactly one line different: the raised message)
- **Validate**: `python -m pytest tests/test_query_router.py -k null_content -q`

### Task 7: Full suite green

- **Action**: VALIDATE ONLY (no file changes)
- **Implement**: Run the complete test suite once every edit lands. Per the repo's libSQL dev-server note, mass unrelated fixture errors mean restart the local Turso/libSQL dev server, not bisect code.
- **Validate**: `python -m pytest -q`

---

## End-to-End Tests

- [ ] `python -m pytest tests/test_openrouter_client.py -q` — all pass, including every new AC1-AC5 test
- [ ] `python -m pytest tests/test_query_router.py -q` — all pass, including the new null-content 502 test
- [ ] `python -m pytest tests/test_config.py -q` — unaffected (this story adds no settings)
- [ ] Grep confirms `_TIMEOUT_SECONDS` no longer appears in `app/services/openrouter_client.py`
- [ ] Full suite: `python -m pytest -q` — green

---

## Validation

```bash
cd /g/coding/harness-ai
python -c "import app.services.openrouter_client"
python -m pytest -q
```

---

## Acceptance Criteria

(Copied from story STORY-005)

- [ ] `app/services/openrouter_client.py` defines a frozen `GenerationParams(temperature, max_tokens, top_p, stop)` (all `Optional`, default `None`), `UnsupportedParameterError`, and `GenerationParams.from_mapping(raw)`; `call_openrouter` gains `params: Optional[GenerationParams] = None`, and the payload includes only the non-`None` fields
- [ ] `from_mapping({"logit_bias": {}, "tools": [], "stream": True, "temperature": 0.2})` raises `UnsupportedParameterError` naming all three unsupported keys, sorted; `temperature=3`, `top_p=0`, `max_tokens=0`, `max_tokens=True`, or `stop` with five sequences or a non-`str` element each raise `UnsupportedParameterError` naming the field and its allowed range; all checks happen before any HTTP call
- [ ] `params=None` with one user message keeps STORY-003's characterization assertion byte for byte
- [ ] `settings.OPENROUTER_TIMEOUT_SECONDS` (monkeypatched) drives the default `httpx.Client`'s `timeout=`; `_TIMEOUT_SECONDS` module constant removed; STORY-003's `timeout=30.0` assertion updated with the `# PRD-010 STORY-005: timeout from settings (default 120.0)` comment
- [ ] `choices[0].message.content is None` raises `OpenRouterError("OpenRouter returned no text content (finish_reason=<value>)")`, naming tool calls (PRD-016) when `tool_calls` is present; maps to 502 through `POST /query`; the API key never appears in either message
- [ ] All tasks completed
- [ ] Full suite passes
- [ ] Follows existing patterns
