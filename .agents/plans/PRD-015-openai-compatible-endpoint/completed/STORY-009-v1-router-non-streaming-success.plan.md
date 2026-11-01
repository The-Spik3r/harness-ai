---
story: STORY-009
prd: PRD-015
slug: v1-router-non-streaming-success
title: "POST /v1/chat/completions: router, identity, device header and non-streaming success"
type: NEW_CAPABILITY
complexity: HIGH
epic_branch: epic/PRD-015-openai-compatible-endpoint
created: 2026-10-23
---

# Plan: POST /v1/chat/completions: router, identity, device header and non-streaming success

## Summary

Add `app/routers/v1.py` with one route, `POST /v1/chat/completions`, included by `app/main.py` only when `settings.V1_ENABLED`. The route authenticates with `require_permission(PERMISSION_QUERY_SUBMIT)` exactly as `/query` does, validates `X-Harness-Device` through a new pure `v1_translate.translate_device`, turns the body into pipeline arguments with the existing `v1_translate.translate_request`, and runs `run_conversation` on the dedicated executor via `run_in_pipeline`, with the literals `profile="code"`, `ingress="v1"`, `streamed=False` and the translated `ignored_params`. The upstream `finish_reason` and token split, which `QuerySuccessResponse` does not carry, are captured by a per-request `call_openrouter` wrapper (option (a) in the story; the pipeline and `/query`'s body do not change). A new pure `v1_translate.translate_result(success, upstream, created)` builds the `ChatCompletion`; the route returns it as JSON with an `X-Harness-Audit-Id` header. A `V1RequestError` becomes a minimal 400 error object (STORY-010 generalizes this). `stream: true` and every non-success pipeline result return a placeholder 501 that STORY-013 and STORY-010 replace. Pipeline exceptions are not mapped yet (STORY-011). The call-site scan, the route-reservation test and a new `tests/test_v1_router.py` and `tests/test_v1_translate_result.py` cover it.

## User Story

As an integrating developer
I want to send a Chat Completions request with my harness token and get a standard `chat.completion` back
So that my existing OpenAI-shaped code works by changing the base URL and key

## Story Reference

- Story file: `.agents/stories/PRD-015-openai-compatible-endpoint/STORY-009-v1-router-non-streaming-success.md`
- PRD: `.agents/PRDs/PRD-015-openai-compatible-endpoint/PRD.md` (Sections 6.1, 6.3, 6.4, 7.2, 7.4, 9.3, 10, 11)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | HIGH |
| Systems Affected | `app/routers/v1.py` (new), `app/services/v1_translate.py`, `app/main.py`, tests (call-site scan, route reservations, new router + result tests) |
| Story | STORY-009 |
| PRD | PRD-015 |
| Epic Branch | `epic/PRD-015-openai-compatible-endpoint` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design`; this story is backend-only. Story frontmatter `skills: []` agrees. | — |

---

## Design Decisions

1. **Capturing `finish_reason` and the split: option (a), a per-request wrapper.** `_Upstream` is a small callable class in the router. It calls the module-level `call_openrouter` by name (so `monkeypatch.setattr("app.routers.v1.call_openrouter", stub)` takes effect, the binding rule `app/routers/query.py:11` follows), stores the `OpenRouterResult`, and returns it unchanged. Its signature is `(messages, model, api_key, **kwargs)` and it forwards `**kwargs` as-is, so `params=` reaches the real client only when the pipeline passed it (`app/services/query_pipeline.py:665-677`), and the existing three-argument stubs keep working (PRD-010 STORY-005). STORY-013 adds the `threading.Event` to this same class. Option (b) is rejected: it would add fields to `QuerySuccessResponse`, and `/query`'s body is pinned by STORY-001.
2. **`translate_result` is success-only for now.** `translate_result(result: QuerySuccessResponse, upstream: OpenRouterResult, created: int) -> ChatCompletion`. `created` is passed in (the router reads `int(time.time())`) so the module stays pure (`app/services/v1_translate.py:1-7`: no I/O, no settings reads). STORY-010 adds the verdict mapping as its own pure function (its Technical Notes say so).
3. **`finish_reason` mapping.** The upstream value if it is one of `"stop"`, `"length"`, `"content_filter"` (the schema's `FinishReason`, `app/models/v1_schemas.py:83`), else `"stop"`. That covers `None` (AC 1) and any provider-specific string the schema cannot carry (`v1_schemas.py:81-82` says the translator maps those to `"stop"`). `tool_calls` cannot arrive: null content already raises in the client (`openrouter_client.py:195-200`).
4. **`usage`.** `prompt_tokens` is `upstream.input_tokens`, or `0` when it is `None`; `completion_tokens` likewise from `upstream.output_tokens`; `total_tokens = result.tokens_used` (the reported total, which is also `upstream.tokens_used`). Spell the fallback as an `is None` check, not `or`: the result is the same, but it reads as "missing split" rather than "falsy". The audit row keeps NULL for a missing split (the pipeline writes it; nothing here touches the row).
5. **`model` and `harness`.** `model = result.model_used` (the requested name, PRD 7.4). `harness = HarnessCompletionInfo(audit_id, pii_redacted, pii_entities_masked)` from `QuerySuccessResponse`. `id = chat_completion_id(result.audit_id)`; the header uses `str(result.audit_id)`.
6. **Device header: `translate_device(raw: Optional[str]) -> Optional[str]`, pure, in `v1_translate`.** `None` → `None`. Otherwise strip; empty after stripping → `None` (nothing to record); longer than 128 characters or `not value.isprintable()` → `V1RequestError(INVALID_HEADER, "X-Harness-Device: must be at most 128 printable characters", None)`. The message never contains the value (T6). The 128 limit is a module constant `MAX_DEVICE_LENGTH = 128`. The length is checked after stripping (PRD 7.2: "stripped, at most 128").
7. **Check order in the route** (all before the pipeline, none writes a row): dependency (401/403, FastAPI) → body schema (FastAPI 422 until STORY-010) → device header → `translate_request` → `stream` placeholder → pipeline. Header before body translation because it is the cheaper check and independent of the body.
8. **Minimal error responses.** One private helper `_error(status, type_, code, message, param=None) -> JSONResponse` building `ErrorResponse(error=ErrorDetail(...)).model_dump(mode="json")`. Used for `V1RequestError` → 400 `invalid_request_error` with the exception's `code`/`message`/`param`, and for the two 501 placeholders (`type="api_error"`, `code="not_implemented"`). The 501s also carry `x-should-retry: false`, because the OpenAI SDK retries 5xx by default and a placeholder must not cause retries (and duplicate rows) in a manual test. `x-should-retry` on 4xx is STORY-010's AC; do not add it to the 400 here, so STORY-010's test drives that change.
9. **Placeholders.** `stream: true` → 501 before the pipeline, no row (STORY-013 replaces). Non-success `QueryPipelineResult` → 501 after the pipeline; the pipeline's row is already written, which is correct and stays so when STORY-010 maps it. Both are marked `# STORY-010/013 replaces this placeholder` and the tests that pin them are named `test_placeholder_*` so the later stories find and rewrite them. The epic must not ship between this story and STORY-010 (story Technical Notes).
10. **Exceptions from the pipeline** (`OpenRouterError`, `DuplicateCheckError`, `UsageLimitError`, `PiiRedactorError`) are not caught here: they surface as Starlette's 500. STORY-011 adds the `except` chain. No test pins that behaviour.
11. **`V1_ENABLED` is read once, at import of `app.main`**, as PRD 9.3 says ("Off: routes are not included"). The off-case test loads `app/main.py` into a fresh module object with `importlib.util.spec_from_file_location` while `settings.V1_ENABLED` is monkeypatched to `False`, so `sys.modules["app.main"]` and every other suite's `app` object are untouched. It sends requests without entering the lifespan (no DB), asserting `/v1/chat/completions` → 404 and `/query` without a bearer → 401 (the route is mounted and answers exactly as before).
12. **Call site literal form.** The story's call shape, with the wrapper in place of the bare client:
    ```python
    result = await run_in_pipeline(
        run_conversation,
        identity,
        call.messages,
        device,
        call.model,
        None,  # openrouter_api_key: BYOK is out (PRD Section 4)
        call.params,
        call_openrouter=upstream,
        profile="code",
        ingress="v1",
        streamed=False,
        ignored_params=call.ignored_params,
    )
    ```
    `session_id` takes its default `None` (no `/v1` session). The scan in `tests/test_query_pipeline_audit_fields.py:530-532` matches `run_in_pipeline(run_conversation, ...)` by its first positional argument and checks for `ingress=` in the keywords.

---

## Patterns to Follow

### Router shape and executor
```python
# SOURCE: app/routers/query.py:19-28
router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    identity: Identity = Depends(require_permission(PERMISSION_QUERY_SUBMIT)),
) -> QueryResponse:
    try:
        return await run_in_pipeline(_handle_query, request, identity)
```

### Upstream binding by name (so tests can replace it)
```python
# SOURCE: app/routers/query.py:11, 134-146
from app.services.openrouter_client import OpenRouterError, call_openrouter
...
    return run_query(
        ...
        call_openrouter=call_openrouter,
        session_id=request.session_id,
        # Spelled out although it is run_query's default: every production call
        # site names its door, and the scan in
        # tests/test_query_pipeline_audit_fields.py holds them to it.
        ingress="query",
    )
```

### params forwarded only when set
```python
# SOURCE: app/services/query_pipeline.py:665-677
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
            openrouter_result = call_openrouter(
                redacted_messages, model=model, api_key=openrouter_api_key
            )
```

### Error handling (translation refusals, never echo the value)
```python
# SOURCE: app/services/v1_translate.py:67-80
class V1RequestError(Exception):
    """A request this ingress refuses before the pipeline runs.

    No pipeline step runs, so no audit row is written (PRD-015 T9). `message`
    names a location and the rule that failed, never a value (T6): ...
    """

    def __init__(self, code: str, message: str, param: Optional[str] = None):
```

### Schemas and serialization
```python
# SOURCE: app/models/v1_schemas.py:9-12, 22-29
# Serialize with `model_dump(mode="json")` or `model_dump_json()`, never with
# `exclude_none=True` ...
def chat_completion_id(audit_id: int) -> str:
    return f"{CHAT_COMPLETION_ID_PREFIX}{audit_id}"
```

### Tests (fixture, client, thread-placement assertion)
```python
# SOURCE: tests/test_v1_query_isolation.py:33-71 and tests/test_query_router.py:779-832
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
...
_AUTH_USER_ID = "juan@empresa.com"
_AUTH_TOKEN = "test-user-token"
_AUTH_HEADERS = {"Authorization": f"Bearer {_AUTH_TOKEN}"}
client = TestClient(app, headers=_AUTH_HEADERS)

@pytest.fixture
def temp_db(temp_db):
    insert_user(User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN)))
    return temp_db
...
    assert thread_names
    assert all(name.startswith("pipeline") for name in thread_names)
```

### Route listing
```python
# SOURCE: tests/test_route_reservations.py:12-31
def _harness_route_paths():
    paths = set()
    for route in app.routes:
        if type(route).__name__ == "_IncludedRouter":
            paths.update(r.path for r in route.original_router.routes)
        elif hasattr(route, "path"):
            paths.add(route.path)
    return paths
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/v1_translate.py` | UPDATE | `INVALID_HEADER`, `MAX_DEVICE_LENGTH`, `translate_device`, `translate_result`; module docstring mentions result translation |
| `app/routers/v1.py` | CREATE | `POST /v1/chat/completions`, `_Upstream` wrapper, `_error` helper, placeholders |
| `app/main.py` | UPDATE | `if settings.V1_ENABLED: app.include_router(v1_router.router)` |
| `tests/test_v1_translate_result.py` | CREATE | Pure tests for `translate_result` and `translate_device` |
| `tests/test_v1_router.py` | CREATE | HTTP tests for AC 1-5 with `TestClient`, `temp_db`, injected upstream |
| `tests/test_query_pipeline_audit_fields.py` | UPDATE | Add the `/v1` site to the exact call-site list |
| `tests/test_route_reservations.py` | UPDATE | Assert `/v1/chat/completions` is present (V1 on, the default) |

---

## Tasks

Execute in order. Each task is atomic + verifiable. Python is `C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe` (`python` below).

### Task 1: `translate_device` and `translate_result` in `v1_translate`

- **File**: `app/services/v1_translate.py`
- **Action**: UPDATE
- **Implement**:
  - Constants beside the others: `INVALID_HEADER = "invalid_header"`, `MAX_DEVICE_LENGTH = 128`, `DEVICE_HEADER = "X-Harness-Device"`.
  - `translate_device(raw: Optional[str]) -> Optional[str]` per Design Decision 6. Docstring: PRD 7.2, D1 (the body's `user` is never the device), T6 (value never echoed).
  - `_FINISH_REASONS = frozenset({"stop", "length", "content_filter"})` and `translate_result(result: QuerySuccessResponse, upstream: OpenRouterResult, created: int) -> ChatCompletion` per Design Decisions 3-5. Docstring: PRD 7.4; why `created` is a parameter (purity); why unknown finish reasons become `"stop"`; the 0/0/total rule and that the audit row keeps NULL.
  - Imports: `QuerySuccessResponse` from `app.models.schemas`; `AssistantMessage, ChatCompletion, Choice, HarnessCompletionInfo, Usage, chat_completion_id` from `app.models.v1_schemas`; `OpenRouterResult` from `app.services.openrouter_client`.
  - Update the module docstring's first paragraph: it now also turns a success result into the completion and validates the device header.
- **Mirror**: `app/services/v1_translate.py:208-219` (`_stream_options`: small pure helper raising `V1RequestError` with a rule-only message).
- **Validate**: `python -c "from app.services.v1_translate import translate_device, translate_result; print(translate_device('  laptop '))"` prints `laptop`.

### Task 2: Pure tests for Task 1

- **File**: `tests/test_v1_translate_result.py`
- **Action**: CREATE
- **Implement** (no DB, no app; runs under `-m "not db"`):
  - `translate_result` builds the PRD 7.4 example exactly: compare `model_dump(mode="json")` as a whole dict for a `QuerySuccessResponse(response="...", audit_id=1842, model_used="openai/gpt-4o", tokens_used=908)` and `OpenRouterResult(..., input_tokens=812, output_tokens=96, finish_reason="stop")`, `created=1792569600`.
  - `finish_reason` parametrized: `"stop"`, `"length"`, `"content_filter"` pass through; `None`, `"error"`, `"tool_calls"`, `""` → `"stop"`.
  - Split missing (`input_tokens=None`, `output_tokens=None`) → `0`, `0`, total as reported; one side missing → that side `0`; reported `0` stays `0`.
  - `harness` carries `pii_redacted=True` and `pii_entities_masked=["EMAIL_ADDRESS"]` through.
  - `id == chat_completion_id(audit_id)`; `model` is `model_used`, not `upstream.model_used` (build them different to prove it).
  - Purity: an `ast` scan of `v1_translate.py` imports no `time`, `datetime`, `logging` or `app.config` (mirror the import-scan style in `tests/test_v1_translate_request.py`, which already imports `ast` and `inspect`).
  - `translate_device`: `None` → `None`; `"  "` → `None`; `" laptop-01 "` → `"laptop-01"`; exactly 128 printable chars → kept; 129 → `V1RequestError` with `code == "invalid_header"`; 128 chars plus surrounding spaces → kept (length after strip); `"dev\tice"`, `"dev\x00ice"`, `"dev\x7fice"`, `"dev\u200bice"` → `invalid_header`; a canary value (`"SECRET-CANARY" * 20`) does not appear in `str(exc)` or `exc.message`.
- **Mirror**: `tests/test_v1_translate_request.py:1-40` (module docstring, env setdefaults, imports).
- **Validate**: `python -m pytest tests/test_v1_translate_result.py -q`

### Task 3: The router

- **File**: `app/routers/v1.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring: PRD-015 Sections 6.1, 6.4, 7.2, 7.4; that the call site names `profile="code"` and `ingress="v1"` (PRD-011 6.6, PRD-013 6.9); that `call_openrouter` is imported by name so tests replace `app.routers.v1.call_openrouter`; that this story ships only the non-streaming success path and STORY-010/011/012/013 add the rest.
  - Imports: `time`, `Optional`; `APIRouter, Depends, Header` from fastapi; `JSONResponse` from `fastapi.responses`; `require_permission`; `QuerySuccessResponse`; `ChatCompletionRequest, ErrorDetail, ErrorResponse`; `PERMISSION_QUERY_SUBMIT`; `Identity`; `OpenRouterResult, call_openrouter`; `run_in_pipeline`; `run_conversation`; `V1RequestError, translate_device, translate_request, translate_result`.
  - `router = APIRouter()`.
  - `class _Upstream` per Design Decision 1: `self.result: Optional[OpenRouterResult] = None`; `__call__(self, messages, model, api_key, **kwargs)` → `self.result = call_openrouter(messages, model=model, api_key=api_key, **kwargs)`; return it. Comment: kwargs is forwarded as received so `params=` reaches the client only when the pipeline passed it (PRD-010 STORY-005); STORY-013 adds the start signal here.
  - `_error(status_code, type_, code, message, param=None, headers=None) -> JSONResponse` per Design Decision 8.
  - The route:
    ```python
    @router.post("/v1/chat/completions")
    async def chat_completions(
        body: ChatCompletionRequest,
        x_harness_device: Optional[str] = Header(default=None, alias="X-Harness-Device"),
        identity: Identity = Depends(require_permission(PERMISSION_QUERY_SUBMIT)),
    ):
    ```
    then: `try: device = translate_device(x_harness_device); call = translate_request(body)` / `except V1RequestError as exc: return _error(400, "invalid_request_error", exc.code, exc.message, exc.param)`; `if call.stream: return _placeholder(...)` (Decision 9); `upstream = _Upstream()`; the `run_in_pipeline` call exactly as Design Decision 12; `if not isinstance(result, QuerySuccessResponse): return _placeholder(...)`; `completion = translate_result(result, upstream.result, int(time.time()))`; `return JSONResponse(completion.model_dump(mode="json"), headers={"X-Harness-Audit-Id": str(result.audit_id)})`.
  - A success with `upstream.result is None` is impossible (step 7 ran); guard with `assert upstream.result is not None` and a one-line comment, rather than a silent fallback.
  - No `try/except` around the pipeline call (Design Decision 10).
- **Mirror**: `app/routers/query.py:1-41` (imports, `router`, dependency, `run_in_pipeline`).
- **Validate**: `python -c "import app.routers.v1 as m; print([r.path for r in m.router.routes])"` prints `['/v1/chat/completions']`.

### Task 4: Mount it behind `V1_ENABLED`

- **File**: `app/main.py`
- **Action**: UPDATE
- **Implement**: `from app.config import settings`, `from app.routers import v1 as v1_router`; after the two existing `include_router` lines:
  ```python
  # PRD-015 Section 9.3: off means the routes are not mounted and /v1/* is 404.
  # Read once, at import, like every other route decision here.
  if settings.V1_ENABLED:
      app.include_router(v1_router.router)
  ```
- **Mirror**: `app/main.py:25-26`.
- **Validate**: `python -c "from app.main import app; print(sorted(r.path for r in app.routes if hasattr(r,'path')))"` lists `/v1/chat/completions` (or check through `_IncludedRouter` as the reservation test does).

### Task 5: Call-site scan sees the new site

- **File**: `tests/test_query_pipeline_audit_fields.py`
- **Action**: UPDATE
- **Implement**: In `test_every_production_pipeline_call_names_its_door` (line ~552), add `("app/routers/v1.py", "chat_completions", "run_conversation")` to the exact sorted list (it sorts between `query.py` and `services/...`). Add one sentence to the docstring: PRD-015 STORY-009 adds the `/v1` site. No other test in this file changes: `v1.py` has no `log_query` call, so the 12-site count and the "elsewhere" list hold.
- **Mirror**: the existing list at `tests/test_query_pipeline_audit_fields.py:559-564`.
- **Validate**: `python -m pytest tests/test_query_pipeline_audit_fields.py -q -k "door or log_query_call"`

### Task 6: Route reservations include `/v1`

- **File**: `tests/test_route_reservations.py`
- **Action**: UPDATE
- **Implement**: Add `test_v1_routes_present_when_enabled`: `assert settings.V1_ENABLED` (guards the premise) and `assert {"/v1/chat/completions"} <= _harness_route_paths()`. Comment: STORY-012 adds `/v1/models` here. The existing two tests are unchanged and must pass with the router mounted (no collision with `/ping`, `/_event`, `/_upload`).
- **Mirror**: `tests/test_route_reservations.py:30-31`.
- **Validate**: `python -m pytest tests/test_route_reservations.py -q`

### Task 7: HTTP tests for the route

- **File**: `tests/test_v1_router.py`
- **Action**: CREATE
- **Implement**: module docstring naming STORY-009 and that the placeholder tests are rewritten by STORY-010/013. Fixtures as in `tests/test_v1_query_isolation.py:33-71` (env setdefaults, `user`-role `juan@empresa.com`, `TestClient(app, headers=...)`). An `_Upstream` stub class in the test with signature `(messages, model="gpt-4", api_key=None)` that records calls and returns a configurable `OpenRouterResult` (`response`, `tokens_used`, `input_tokens`, `output_tokens`, `finish_reason`), plus a variant accepting `params=None` for the forwarding test. Patch with `monkeypatch.setattr("app.routers.v1.call_openrouter", stub)`. Patch `query_pipeline.redact` / PII as the isolation tests do only if the `code` profile needs it (it runs the tokenizer-only analyzer, so probably not; keep it unpatched if green). Use model `"openai/gpt-4o"` (in the default `MODEL_ALLOWLIST`, `app/config.py:204`) and a clean prompt (`"hello world"`). Cases:
  - **AC 1** `test_success_returns_chat_completion`: 200; body equals, as a whole dict except `created` (assert it is an `int` within a few seconds of `time.time()`), `{"id": f"chatcmpl-harness-{audit_id}", "object": "chat.completion", "model": "openai/gpt-4o", "choices": [{"index": 0, "message": {"role": "assistant", "content": "..."}, "logprobs": None, "finish_reason": "length"}], "usage": {...812/96/908}, "harness": {"audit_id": audit_id, "pii_redacted": False, "pii_entities_masked": []}}`; `response.headers["X-Harness-Audit-Id"] == str(audit_id)`; `audit_id` read from the single row.
  - `test_finish_reason_none_is_stop` and `test_missing_split_is_zero_with_reported_total` over HTTP (one each; the matrix lives in Task 2).
  - **AC 2** `test_success_writes_one_v1_row`: body with three messages (`system`, `assistant`, `user`), `seed: 7`, `user: "someone-else"`, header `X-Harness-Device: laptop-01`. Exactly one row (`COUNT(*)` before/after). Row: `ingress == "v1"`, `profile == "code"`, `streamed is False`, `session_id is None`, `message_count == 3`, `ignored_params == "seed,user"`, `device == "laptop-01"`, `user_id == "juan@empresa.com"`, `success is True`. Read with `get_audit_log(audit_id)`.
  - **AC 3**: `test_device_header_over_128_is_invalid_header` (129 chars) and `test_device_header_non_printable_is_invalid_header` (a tab inside; httpx accepts tabs in header values) → 400, `body["error"]["code"] == "invalid_header"`, `type == "invalid_request_error"`, zero rows, stub not called. `test_device_header_absent_records_null`. `test_body_user_is_neither_device_nor_identity`: `user: "mallory@empresa.com"`, no header → row `device is None`, `user_id == "juan@empresa.com"`, `"user"` in `ignored_params.split(",")`.
  - `test_translation_refusal_is_400_without_row`: `tools: [{"type": "function", ...}]` → 400 `tools_not_supported`, zero rows, stub not called.
  - `test_params_reach_upstream_only_when_sent`: with `temperature: 0.2` the params-accepting stub receives `params == GenerationParams(temperature=0.2)`; without it the three-argument stub is called and no `TypeError` occurs.
  - **AC 5** `test_pipeline_body_runs_on_dedicated_executor_thread`: spy `query_pipeline.log_query` and the injected stub, record `threading.current_thread().name`, assert non-empty and every name starts with `"pipeline"` (mirror `tests/test_query_router.py:779-832`).
  - **AC 4** `test_v1_disabled_routes_404_and_query_unaffected` (no DB, mark nothing): `monkeypatch.setattr(settings, "V1_ENABLED", False)`; load `app/main.py` with `importlib.util.spec_from_file_location("_harness_main_v1_off", path)` + `module_from_spec` + `exec_module`; `TestClient(module.app)` without a `with` block (no lifespan); `POST /v1/chat/completions` → 404; `POST /query` with no bearer → 401 with body `{"detail": "Invalid or missing credential"}` (the STORY-001 pin). Assert `"/query"` is in the fresh app's paths and `"/v1/chat/completions"` is not.
  - `test_placeholder_stream_true_is_501_without_row`: `stream: true` → 501, `code == "not_implemented"`, `x-should-retry == "false"`, zero rows, stub not called.
  - `test_placeholder_blocked_result_is_501`: a prompt that hits the `code` profile's user `block` (use an injection phrase already used by `tests/test_pattern_profiles.py` or `tests/test_query_pipeline_patterns.py`; find one with `grep -n "ignore previous" tests/`) → 501 and one row with `success`/pattern fields as the pipeline writes them. STORY-010 rewrites this to 400 `suspicious_pattern`.
  - Keep all output text ASCII (cp1252 note in the test-env memory).
- **Mirror**: `tests/test_v1_query_isolation.py:33-90`; `tests/test_query_router.py:779-832`.
- **Validate**: `python -m pytest tests/test_v1_router.py -q` (needs the libSQL container; the AC 4 test also passes under `-m "not db"`).

### Task 8: Regression

- **Action**: run, no file changes
- **Implement**: the suites this story could disturb, then the full suite.
- **Validate**:
  - `python -m pytest tests/test_v1_router.py tests/test_v1_translate_result.py tests/test_v1_translate_request.py tests/test_v1_schemas.py tests/test_v1_query_isolation.py tests/test_route_reservations.py tests/test_query_pipeline_audit_fields.py tests/test_query_pipeline_pii_profiles.py tests/test_query_router.py tests/test_query_outcomes_regression.py tests/test_main.py -q`
  - Full suite `python -m pytest tests/ -q` (about 5 min on a throwaway libSQL, see the test-env memory); if Docker is down, `-m "not db"` and say which ran.

---

## End-to-End Tests

For `/implement` to execute against a running server (the OpenRouter call fails from this machine, so point the upstream at a local stub: a 20-line `http.server` script in the scratchpad that answers `POST /v1/chat/completions` with a fixed Chat Completions JSON, and `OPENROUTER_BASE_URL=http://127.0.0.1:<port>/v1`; STORY-014 builds the real stub later):

- [ ] Start uvicorn with a throwaway libSQL (`HARNESS_TEST_LIBSQL_URL`/`DATABASE_URL` per memory), a user token from `scripts/manage_users.py`, and the stub upstream.
- [ ] `curl -s -i -X POST http://127.0.0.1:8000/v1/chat/completions -H "Authorization: Bearer <token>" -H "X-Harness-Device: e2e-laptop" -H "Content-Type: application/json" -d '{"model":"openai/gpt-4o","messages":[{"role":"user","content":"hello"}],"seed":1}'` → 200, `X-Harness-Audit-Id` header, body `id == chatcmpl-harness-<that id>`, `finish_reason`, `usage`.
- [ ] `GET /audit` with the admin token → the row has `ingress=v1`, `profile=code`, `streamed=false`, `device=e2e-laptop`, `ignored_params=seed`.
- [ ] OpenAI Python SDK (installed in the venv, `openai==3.36.1`): `OpenAI(base_url="http://127.0.0.1:8000/v1", api_key=<token>).chat.completions.create(model="openai/gpt-4o", messages=[...])` returns a `ChatCompletion` with the content; `resp.model_extra["harness"]["audit_id"]` matches the id suffix.
- [ ] Same curl with a 129-char `X-Harness-Device` → 400 `invalid_header`, and no new audit row.
- [ ] Restart with `V1_ENABLED=false` → `/v1/chat/completions` 404, `/query` still answers.

---

## Validation

```bash
python -m pytest tests/test_v1_translate_result.py tests/test_v1_router.py tests/test_route_reservations.py tests/test_query_pipeline_audit_fields.py -q
python -m pytest tests/ -q -m "not db"
python -m pytest tests/ -q
```

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Reloading `app.main` for the `V1_ENABLED=false` test leaks a second `app` into other suites | Load into a fresh, uniquely named module via `spec_from_file_location`; never touch `sys.modules["app.main"]`; no lifespan entered |
| A test stub replaces `call_openrouter` but the wrapper captured the original at import | `_Upstream.__call__` looks up the module global `call_openrouter` at call time, never stores it |
| The placeholder 501 tests are forgotten and contradict STORY-010/013 | Named `test_placeholder_*` and documented in the module docstring and in the router comments |
| `X-Harness-Device` with control characters cannot be sent by httpx (`\n`, `\0`) | Those characters are covered in the pure `translate_device` tests; HTTP covers tab and length |
| Call-site scan's exact list | Updated in the same commit (Task 5); the enclosing function name is `chat_completions` |
| `code` profile PII analysis needs a spaCy model in tests | The `code` profile uses the tokenizer-only analyzer (PRD-012); if a test turns out to load a model, stub `query_pipeline.redact_for_policy` as the PII profile tests do |
| Body-schema failures are 422 `{"detail": ...}` on `/v1` until STORY-010 | Accepted for this story; not asserted, so STORY-010 is free to change it |

---

## Acceptance Criteria

(Copied from story `STORY-009`)

- [ ] Given a `user`-role token, an allowlisted model and a clean conversation, when `POST /v1/chat/completions` is sent without `stream`, then the response is 200 with the Section 7.4 shape: `id == f"chatcmpl-harness-{audit_id}"`, `model` as requested, the upstream `finish_reason` (or `"stop"` when it was `None`), `usage` from the upstream split (0 for a missing split, total as reported), `harness.audit_id`, and an `X-Harness-Audit-Id` header with the same id.
- [ ] Given that request, when the audit is read, then exactly one row was written, with `ingress='v1'`, `profile='code'`, `streamed=0`, `session_id` NULL, `message_count == len(messages)`, `ignored_params` as translated, and `device` from `X-Harness-Device`.
- [ ] Given an `X-Harness-Device` value over 128 characters or with a non-printable character, when sent, then 400 with `code="invalid_header"` and no row; given the header absent, then `device` is NULL; given a body `user` field, then it is not the device and not the identity.
- [ ] Given `V1_ENABLED=false`, when the app starts, then `/v1/chat/completions` returns 404 and `/query` is unaffected; given it on, then `tests/test_route_reservations.py` still passes and also asserts the `/v1` paths are present.
- [ ] Given the pipeline body, when the request runs, then it runs on the dedicated pipeline executor thread, never the event loop or anyio's threadpool (the assertion `tests/test_query_router.py` makes for `/query`).
- [ ] All tasks completed
- [ ] Backend server starts without error
- [ ] Follows existing patterns
