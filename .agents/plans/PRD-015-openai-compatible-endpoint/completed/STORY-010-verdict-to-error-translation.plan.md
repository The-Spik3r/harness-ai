---
story: STORY-010
prd: PRD-015
slug: verdict-to-error-translation
title: "Verdicts to OpenAI error objects; /v1-scoped 400/401/403 handlers; /query isolation"
type: NEW_CAPABILITY
complexity: HIGH
epic_branch: epic/PRD-015-openai-compatible-endpoint
created: 2026-10-23
---

# Plan: Verdicts to OpenAI error objects; /v1-scoped 400/401/403 handlers; /query isolation

## Summary

Replace STORY-009's "non-success result" placeholder with a real translation. A pure
`translate_verdict(result) -> V1Error` in `app/services/v1_translate.py` maps each blocked
`QueryPipelineResult` member to the status, `type` and `code` in PRD Section 7.5. It uses one
table keyed on the response type, plus the two refinements the PRD names (`redaction_characters`
and the `required_permission` prefix). `error.message` is the reason plus its details.
`error.harness` is the pipeline response's fields. Then register two app-level exception
handlers, for Starlette's `HTTPException` and FastAPI's `RequestValidationError`. They return
the OpenAI shape only when `request.url.path` starts with `/v1/` and otherwise call FastAPI's
defaults, so `/query`'s 401/403/422/500 bodies stay exactly as STORY-001 pinned them. Every
`/v1` 4xx carries `x-should-retry: false`. The stream placeholder (STORY-013) and the
pipeline-exception mapping (STORY-011) are not touched.

## User Story

As an integrating developer
I want every harness verdict to arrive as an ordinary OpenAI error with a status my client does not retry and a code that names the reason
So that my tool shows me what happened instead of looping

## Story Reference

- Story file: `.agents/stories/PRD-015-openai-compatible-endpoint/STORY-010-verdict-to-error-translation.md`
- PRD: `.agents/PRDs/PRD-015-openai-compatible-endpoint/PRD.md` (Sections 7.2, 7.5, 9.1, 9.2 T6/T7/T9, 11, 14 Risk 4, 15 D2/D5)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | HIGH |
| Systems Affected | `app/services/v1_translate.py`, `app/routers/v1.py`, `app/main.py`, tests |
| Story | STORY-010 |
| PRD | PRD-015 |
| Epic Branch | `epic/PRD-015-openai-compatible-endpoint` (commit directly on this branch) |

Dependencies STORY-001, STORY-004 and STORY-009 are all `done`.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` holds only `frontend-design`, and this story is backend only. The story itself says "Skills: none applicable". | — |

---

## Patterns to Follow

### Naming: code constants and a refusal carrying `code`/`message`/`param`
```python
# SOURCE: app/services/v1_translate.py:31-41, 90-105
INVALID_MESSAGES = "invalid_messages"
...
class V1RequestError(Exception):
    def __init__(self, code: str, message: str, param: Optional[str] = None):
```
New code constants go next to these, as module-level `UPPER_SNAKE` strings.

### Error body construction (the router's single helper)
```python
# SOURCE: app/routers/v1.py:60-69
def _error(status_code, type_, code, message, param=None, headers=None) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(message=message, type=type_, param=param, code=code))
    return JSONResponse(body.model_dump(mode="json"), status_code=status_code, headers=headers)
```
Extend this helper rather than adding a second one: it gains `harness=` and sets
`x-should-retry: false` itself for every status < 500.

### The schema the body must fit
```python
# SOURCE: app/models/v1_schemas.py:190-219
ErrorType = Literal["invalid_request_error", "authentication_error", "permission_error", "api_error"]
class ErrorDetail(BaseModel):
    message: str; type: ErrorType; param: Optional[str] = None; code: str
    harness: Optional[Dict[str, Any]] = None
```
`harness` is `null` when no pipeline response exists, which covers the dependency 401/403,
validation 400s and `V1RequestError`.

### Verdict reasons and the forbidden labels (inputs to the table)
```python
# SOURCE: app/services/query_pipeline.py:40-47, 314, 325, 352-360, 417, 461, 492, 543, 617
QueryPipelineResult = Union[QuerySuccessResponse, QueryBlockedDuplicateResponse,
    QueryBlockedSuspiciousResponse, QueryBlockedForbiddenResponse,
    QueryBlockedContextLimitResponse, QueryBlockedUsageLimitResponse]
# forbidden labels: "query:submit", "query:byok", f"query:model:{model}" (authz.py:154),
# "ingress:break_glass" (query_pipeline.py:357)
```

### Router-scoped refusal before the pipeline (no row)
```python
# SOURCE: app/routers/v1.py:86-92
try:
    device = translate_device(x_harness_device)
    call = translate_request(body)
except V1RequestError as exc:
    return _error(400, "invalid_request_error", exc.code, exc.message, exc.param)
```

### Logging
```python
# SOURCE: app/services/query_pipeline.py:55
logger = logging.getLogger(__name__)
```
Add the same module-level logger to `app/routers/v1.py`.

### Tests: whole-body pins, the `temp_db` user fixture, and settings monkeypatch for limits
```python
# SOURCE: tests/test_v1_router.py:48-58, 98-106 (client, temp_db fixture, _count_audit_rows, _only_row)
# SOURCE: tests/test_query_outcomes_regression.py:220-245 (CONTEXT_MAX_CHARACTERS=50 -> context verdict)
# SOURCE: tests/test_query_outcomes_regression.py:256-275 (USAGE_DAILY_TOKEN_BUDGET="*=100" + seeded usage_daily row)
# SOURCE: tests/test_query_outcomes_regression.py:141-160 (_DISALLOWED_MODEL -> query:model:* forbidden)
# SOURCE: tests/test_query_pipeline_break_glass.py:20-31 (identity from resolve(settings.ADMIN_TOKEN), never hand-built)
# SOURCE: tests/test_v1_query_isolation.py:94-205 (/query 401/403/422/500 bodies compared as whole dicts)
```

---

## Design decisions (made here, flagged for review)

1. **Handler registration is gated by `V1_ENABLED`.** `install_error_handlers(app)` is called
   inside the existing `if settings.V1_ENABLED:` block in `app/main.py`. When the setting is
   off, the app is byte-for-byte what it was before PRD-015, so the existing
   `test_v1_disabled_routes_404_and_query_unaffected` stays meaningful.
2. **The handler is registered on `starlette.exceptions.HTTPException`**, not FastAPI's
   subclass. That key is the one FastAPI's default handler uses, so it also covers routing
   404/405 under `/v1/` (for example `/v1/foo`, or `GET /v1/chat/completions`). That keeps the
   "every `/v1` 4xx has `x-should-retry: false`" acceptance criterion true for those responses
   too. The status table is: 401 → `authentication_error`/`invalid_api_key`; 403 →
   `permission_error`/`permission_denied`; 404 → `invalid_request_error`/`not_found`; 405 →
   `invalid_request_error`/`method_not_allowed`; any other 4xx →
   `invalid_request_error`/`invalid_request`; ≥500 → `api_error`/`internal_error`. Nothing in
   `/v1` raises a 5xx `HTTPException` today, and STORY-011 owns that mapping. `exc.headers`
   are preserved.
3. **`harness` leaves out `status`.** It is `result.model_dump(mode="json", exclude={"status"})`,
   which matches the PRD 7.5 example (`reason`, `limit`, `maximum`, `actual`, `resets_at`). The
   constant `"BLOCKED"` adds nothing to an HTTP error. Every other field is carried. If the
   reviewer wants `status` kept, it is a one-line change plus one test assertion.
4. **Message formats** (reason + details, never content; T6):
   - duplicate: `"{reason}: first seen {first_query_at}"`
   - suspicious: `"{reason}: {pattern}"` (the configured pattern, as `/query` returns it)
   - context / redaction: `"{reason}: {limit} {actual} > {maximum}"`
   - forbidden: `"{reason}: {required_permission}"`
   - usage: `"{reason}: {limit} {actual} of {maximum}; resets at {resets_at}"` (the PRD example)
5. **Validation 400s:** `param` comes from the first error's `loc` without the leading `"body"`.
   String keys are joined with `.` and ints are written as `[i]`, so
   `("body","messages",0,"content")` becomes `"messages[0].content"`. An empty remainder, or a
   `json_invalid` error whose loc is `("body", <pos>)`, gives `param=None`. `message` is
   `"{param}: {msg}"` (or `msg` alone when there is no param), for the first error only. The
   `input` and `ctx` fields are never read, so no content is echoed.
6. **Shape-refusal logging (T9):** `V1RequestError` is logged in the route at INFO with
   `identity.user_id` and `code`. A `RequestValidationError` is raised before the identity
   dependency's result is available, so the handler logs `code` with `user_id=None`. The
   401/403 handlers log `code` only. No message, param value or body is ever logged.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/v1_translate.py` | UPDATE | New code constants, the `V1Error` dataclass, the `_VERDICTS` table and the pure `translate_verdict` |
| `app/routers/v1.py` | UPDATE | `_error` gains `harness` + automatic `x-should-retry: false`; the verdict placeholder is replaced; INFO log for `V1RequestError`; new `install_error_handlers(app)` with the two path-scoped handlers |
| `app/main.py` | UPDATE | Call `v1_router.install_error_handlers(app)` inside the `V1_ENABLED` block |
| `tests/test_v1_translate_result.py` | UPDATE | Pure unit tests for `translate_verdict`, including a test over every `QueryPipelineResult` member |
| `tests/test_v1_errors.py` | CREATE | Per-verdict HTTP tests through the real pipeline, plus the 401/403/400 shape tests and the header/no-429 checks |
| `tests/test_v1_query_isolation.py` | UPDATE | Add the `/v1` half. No STORY-001 pin changes |
| `tests/test_v1_router.py` | UPDATE | Rewrite `test_placeholder_blocked_result_is_501` (as STORY-009's module docstring anticipates). The stream placeholder test stays. Update the docstring |

---

## Tasks

Execute in order. Each task is atomic and verifiable.
Python: `C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe` (no Python on PATH). DB tests
need a reachable libSQL: start Docker Desktop and a throwaway libsql container, then point
`HARNESS_TEST_LIBSQL_URL` at it. See memory `harness-ai-test-env`, since `harness-libsql-dev`
is gone.

### Task 1: Pure verdict translation in `v1_translate`

- **File**: `app/services/v1_translate.py`
- **Action**: UPDATE
- **Implement**:
  - Constants: `DUPLICATE_REQUEST`, `SUSPICIOUS_PATTERN`, `CONTEXT_LENGTH_EXCEEDED`
    (`"context_length_exceeded"`, OpenAI's own spelling), `REDACTION_LIMIT_EXCEEDED`,
    `MODEL_NOT_PERMITTED`, `BREAK_GLASS_NOT_PERMITTED`, `PERMISSION_DENIED`,
    `USAGE_LIMIT_EXCEEDED`, `INVALID_REQUEST`, `INVALID_API_KEY`.
  - `@dataclass(frozen=True) class V1Error: status_code: int; type: str; code: str; message: str; harness: Optional[Dict[str, Any]] = None; param: Optional[str] = None`.
  - `_VERDICTS: Mapping[type, Tuple[int, str, str, Callable[[Any], str]]]`, one row per blocked
    member, giving the default status, type, code and a detail formatter (decision 4).
  - `_code(result, default)` holds only the two refinements. `QueryBlockedContextLimitResponse`
    with `limit == "redaction_characters"` gives `REDACTION_LIMIT_EXCEEDED`.
    `QueryBlockedForbiddenResponse` gives `MODEL_NOT_PERMITTED` when `required_permission`
    starts with `"query:model:"`, `BREAK_GLASS_NOT_PERMITTED` when it equals
    `"ingress:break_glass"`, and the default `permission_denied` otherwise.
  - `translate_verdict(result) -> V1Error`: looks up `type(result)` and raises `TypeError` for
    an unmapped type (including `QuerySuccessResponse`). `harness` is
    `result.model_dump(mode="json", exclude={"status"})`. The docstring states the module is
    still pure: no I/O, no clock, no settings.
  - Update the module docstring to mention verdict translation.
- **Mirror**: `translate_result` (`app/services/v1_translate.py:301-341`) for docstring style.
  Use the constants block at `:31-41`.
- **Validate**: `python -c "import app.services.v1_translate"` (with `OPENROUTER_API_KEY`/`ADMIN_TOKEN` set)

### Task 2: Unit tests for `translate_verdict`

- **File**: `tests/test_v1_translate_result.py`
- **Action**: UPDATE (new section)
- **Implement**:
  - Write a parametrized test over constructed responses for every verdict cell in the
    acceptance criteria: duplicate; suspicious; context `messages`, `characters` and
    `redaction_characters`; forbidden `query:submit`, `query:byok`, `query:model:openai/gpt-4o`
    and `ingress:break_glass`; usage `requests` and `tokens`. Each case asserts the exact
    `(status_code, type, code, message, harness)`.
  - Add a completeness test that iterates `typing.get_args(QueryPipelineResult)` minus
    `QuerySuccessResponse` and asserts each type is a key of `_VERDICTS`. Also assert that no
    status is 429 or ≥ 500.
  - Assert that `translate_verdict(QuerySuccessResponse(...))` raises `TypeError`.
  - Assert that `harness == result.model_dump(mode="json", exclude={"status"})` for every case,
    so a field added to a response is carried automatically.
- **Validate**: `python -m pytest tests/test_v1_translate_result.py -q -m "not db"`

### Task 3: Router: verdict responses, header, logging

- **File**: `app/routers/v1.py`
- **Action**: UPDATE
- **Implement**:
  - `_error(...)` gains `harness: Optional[Dict[str, Any]] = None`. When `status_code < 500` it
    merges `{"x-should-retry": "false"}` into `headers`. `_placeholder` is unchanged: it is 501
    and passes the header itself.
  - Add `_from_v1_error(err: V1Error) -> JSONResponse` as a thin wrapper over `_error`.
  - Replace the non-success placeholder with `return _from_v1_error(translate_verdict(result))`.
    Keep the comment that the pipeline has already written the row.
  - In the `V1RequestError` branch, log
    `logger.info("v1 request refused: user_id=%s code=%s", identity.user_id, exc.code)` before
    returning.
  - Update the module docstring: STORY-010 is now delivered, so the remaining work is
    STORY-011/012/013.
- **Mirror**: `app/routers/v1.py:60-78`
- **Validate**: `python -m pytest tests/test_v1_router.py -q` (the blocked-placeholder test fails, as expected, until Task 6)

### Task 4: Path-scoped exception handlers

- **File**: `app/routers/v1.py`
- **Action**: UPDATE
- **Implement**:
  - `_V1_PREFIX = "/v1/"` and `def _is_v1(request) -> bool: return request.url.path.startswith(_V1_PREFIX)`.
  - `async def _http_exception(request, exc: StarletteHTTPException)`: if not `_is_v1`, return
    `await fastapi.exception_handlers.http_exception_handler(request, exc)`. Otherwise map the
    status per decision 2. The message is `exc.detail` when it is a `str`, else the HTTP phrase.
    `harness=None`. Pass `exc.headers` through. Log INFO with `code`.
  - `async def _validation_exception(request, exc: RequestValidationError)`: if not `_is_v1`,
    return `await fastapi.exception_handlers.request_validation_exception_handler(request, exc)`.
    Otherwise return 400 `invalid_request_error`/`invalid_request` with `param` and `message`
    per decision 5. Log INFO with `user_id=None` and `code`.
  - `def install_error_handlers(app: FastAPI) -> None`: two `app.add_exception_handler` calls.
    The docstring cites PRD Risk 4 and names `tests/test_v1_query_isolation.py`.
- **Mirror**: FastAPI 0.142.2 `fastapi/exception_handlers.py`, the delegate targets (check
  their signatures in the venv before wiring).
- **Validate**: `python -c "from app.routers.v1 import install_error_handlers"`

### Task 5: Wire the handlers

- **File**: `app/main.py`
- **Action**: UPDATE
- **Implement**: Inside `if settings.V1_ENABLED:`, after `include_router`, call
  `v1_router.install_error_handlers(app)`. Extend the comment: off leaves both the routes and
  the handlers out.
- **Validate**: `python -m pytest tests/test_v1_router.py::test_v1_disabled_routes_404_and_query_unaffected -q`

### Task 6: Rewrite the blocked placeholder test

- **File**: `tests/test_v1_router.py`
- **Action**: UPDATE
- **Implement**: Rename `test_placeholder_blocked_result_is_501` to
  `test_blocked_result_is_translated_verdict`. Assert 400, `code == "suspicious_pattern"`,
  `harness["pattern"] == _INJECTION` and the `x-should-retry` header, and keep the existing
  row assertions unchanged. Update the module docstring: only the stream placeholder remains
  (STORY-013).
- **Validate**: `python -m pytest tests/test_v1_router.py -q`

### Task 7: `tests/test_v1_errors.py`, the per-verdict and shape-refusal HTTP tests

- **File**: `tests/test_v1_errors.py`
- **Action**: CREATE
- **Implement**: Use the same module header as `test_v1_router.py` (env defaults, client,
  `temp_db` user fixture, `_count_audit_rows`/`_only_row`, the `upstream` stub on
  `app.routers.v1.call_openrouter`). Each test asserts the whole `response.json()` dict, the
  status, `x-should-retry: false`, and the row count.
  - **duplicate**: two identical requests; the second gets 400 `duplicate_request`, with
    `harness.first_query_at` present.
  - **suspicious**: `_INJECTION` gives 400 `suspicious_pattern`.
  - **context `messages`** (`CONTEXT_MAX_MESSAGES` small) and **`characters`**
    (`CONTEXT_MAX_CHARACTERS=50`): 400 `context_length_exceeded`.
  - **redaction**: `PII_REDACTION_ENABLED=True`, `PII_MAX_CHARACTERS_CODE` small (re-run
    `pii_policy.load()` per the pattern in `tests/test_query_pipeline_pii_profiles.py:80-100`):
    400 `redaction_limit_exceeded`.
  - **model**: `model=_DISALLOWED_MODEL` gives 403 `model_not_permitted`.
  - **break-glass** (AC 2): bearer `settings.ADMIN_TOKEN` gives 403 `break_glass_not_permitted`,
    with exactly one row where `denied_permission == "ingress:break_glass"` and
    `ingress == "v1"`.
  - **usage `tokens`**: seed `usage_daily` as in outcome 8. **Usage `requests`**:
    `USAGE_REQUESTS_PER_MINUTE="*=1"` and two requests. Both give 403 `usage_limit_exceeded`.
  - **forbidden `query:submit`/other through the router**: unreachable over HTTP, because the
    dependency refuses first. Monkeypatch `app.routers.v1.run_conversation` to return
    `QueryBlockedForbiddenResponse(required_permission="query:submit")` and assert 403
    `permission_denied` with `harness` set.
  - **Shape refusals with no row** (AC 3): no bearer and an unknown bearer give 401
    `authentication_error`/`invalid_api_key`. An `auditor` token gives 403
    `permission_error`/`permission_denied` with message `"Permission denied: query:submit"`.
    `content=b"not json"` with a JSON content type gives 400 `invalid_request` with
    `param=None`. A body missing `messages` gives 400 `invalid_request` with `param="messages"`.
    `messages: "x"` gives a `param` that starts with `messages`. A `V1RequestError` case (for
    example `n: 2`) gives 400 `unsupported_parameter` with `param="n"`. Each has `harness is None`
    and `_count_audit_rows() == 0`.
  - **Routing 4xx**: `GET /v1/chat/completions` gives 405 and `/v1/nope` gives 404, both in
    OpenAI shape with the header.
  - **No-message-echo (T6)**: put a sentinel string in message content for the
    suspicious/context cases and assert it is absent from `response.text`.
  - **INFO log (T9)**: `caplog` on a `V1RequestError` case asserts that the record has the user
    id and code, and that the sentinel content is absent.
  - **Never 429/5xx**: a final parametrized sweep over every verdict test's status (or the
    asserts above) is enough, and the pure test in Task 2 covers the table.
- **Mirror**: `tests/test_v1_router.py:1-106`, `tests/test_query_outcomes_regression.py:141-300`,
  `tests/test_query_pipeline_break_glass.py`
- **Validate**: `python -m pytest tests/test_v1_errors.py -q`

### Task 8: The `/v1` half of the isolation test

- **File**: `tests/test_v1_query_isolation.py`
- **Action**: UPDATE (append only; every STORY-001 pin stays byte-identical)
- **Implement**: Add a `# --- /v1 half (STORY-010) ---` section that mirrors each `/query` pin
  on `/v1/chat/completions`. No bearer gives the 401 OpenAI body as a whole dict; an unknown
  bearer gives 401; an auditor gives 403; an empty body gives 400 `invalid_request`. Add one
  test that, in one session, hits `/query` with no bearer and then `/v1` with no bearer and
  asserts both bodies, which proves the same app serves both shapes. Keep the
  no-bearer `/v1` test free of storage so it runs under `-m "not db"`. Add one sentence to the
  docstring saying the `/v1` half was added by STORY-010 and below the line.
- **Validate**: `python -m pytest tests/test_v1_query_isolation.py -q`

### Task 9: Regression sweep

- **Validate**:
  - `python -m pytest tests/test_v1_*.py tests/test_query_outcomes_regression.py tests/test_query_router.py tests/test_query_pipeline_audit_fields.py -q`
  - `python -m pytest tests/ -q -m "not db"` (Docker-free subset)
  - Full suite, if the throwaway libSQL is up. A `/query` 500 or `os error 10060` is the known
    storage flake, so rerun before blaming the change.

---

## End-to-End Tests

Run in-process (an outbound OpenRouter call is impossible here; see memory): `TestClient(app)`
against the throwaway libSQL, with `app.routers.v1.call_openrouter` replaced.

- [ ] Start a live `uvicorn app.main:app` against the throwaway DB (bootstrap a user with
      `scripts/manage_users.py`). Using the `openai` SDK (in the venv), send an injection prompt with
      `openai.OpenAI(base_url="http://127.0.0.1:8000/v1", api_key=<token>, max_retries=2)`. The
      expected result is `openai.BadRequestError`, `e.code == "suspicious_pattern"`, and exactly
      one audit row, which proves the SDK did not retry.
- [ ] The same client with a wrong key gives `openai.AuthenticationError` and no row.
- [ ] `curl -i -X POST http://127.0.0.1:8000/query` with no bearer gives `{"detail":"Invalid or missing credential"}`, unchanged.
- [ ] `curl -i -X POST http://127.0.0.1:8000/v1/chat/completions -d 'not json' -H 'Content-Type: application/json' -H 'Authorization: Bearer <token>'` gives 400 `invalid_request` and `x-should-retry: false`.

The live E2E needs no upstream: every case above is decided before step 7. Note that the
upstream stub is STORY-014.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| A `/query` body changes (PRD Risk 4) | Handlers delegate outside `/v1/`. STORY-001 pins are compared as whole dicts, and Task 8 is append-only |
| The NiceGUI chat UI (`chat_ui` mounts onto `app.main.app`) registers its own status handlers (for example 404), which Starlette checks before class handlers | Those only affect UI paths. `/v1/` 401/403/400 are unaffected because NiceGUI does not register those codes. Check with one manual `/v1/nope` request under `app.py` during E2E; if NiceGUI wins on 404, note it and leave it to STORY-012/018 |
| FastAPI parses the JSON body before running dependencies, so an unauthenticated non-JSON body gets 400, not 401 | This is the framework's order and leaks nothing (no content, no identity). Tests send a valid bearer for 400 cases, as STORY-001's 422 pins do. Document it in the handler docstring |
| A pydantic `msg` echoes a value (a custom `ValueError` in a validator) | `ChatCompletionRequest` has no custom validators (`extra="allow"` only). The message uses `msg`, never `input`. The T6 sentinel test catches a regression |
| A future pipeline member has no mapping | The completeness test over `get_args(QueryPipelineResult)` fails, and `translate_verdict` raises `TypeError` instead of guessing |
| The `x-should-retry` merge clobbers `exc.headers` | Merge into a copy; test the 401 path keeps any header the exception carried |

---

## Validation

```bash
PY=/c/Users/tobip/.venvs/harness-ai/Scripts/python.exe
$PY -m pytest tests/test_v1_translate_result.py tests/test_v1_errors.py tests/test_v1_router.py tests/test_v1_query_isolation.py -q
$PY -m pytest tests/test_query_outcomes_regression.py tests/test_query_router.py -q
$PY -m pytest tests/ -q -m "not db"
```

---

## Acceptance Criteria

(Copied from story `STORY-010`)

- [ ] Given each pipeline verdict (duplicate; suspicious; context limit `messages` and `characters`; `redaction_characters`; forbidden for `query:submit`, `query:model:*`, `ingress:break_glass`; usage limit `requests` and `tokens`), when it is the result of a `/v1` request, then the status, `type` and `code` are exactly those in PRD Section 7.5, `error.harness` carries every field of the pipeline response, and `error.message` is the reason plus its details.
- [ ] Given `ADMIN_TOKEN` as the bearer, when `POST /v1/chat/completions` is sent, then 403 `break_glass_not_permitted` and the PRD-013 refusal row with `denied_permission='ingress:break_glass'` and `ingress='v1'`.
- [ ] Given no bearer, an invalid bearer, an identity without `query:submit`, a non-JSON body, a body failing schema validation, or a `V1RequestError` from STORY-005/006, when sent to `/v1/*`, then the response is the error object (401 `invalid_api_key` / 403 `permission_denied` / 400 `invalid_request` or the translation code) with `param` where known, and no audit row.
- [ ] Given every 4xx response from `/v1`, when its headers are read, then `x-should-retry: false` is present; and no `/v1` verdict is ever 429 or 5xx.
- [ ] Given `tests/test_v1_query_isolation.py` from STORY-001, when it runs after this story's handlers are registered, then every `/query` body is unchanged, and its new `/v1` half passes.
- [ ] All tasks completed
- [ ] Backend imports and the server starts without error
- [ ] Follows existing patterns (pure translator, single `_error` helper, whole-body test pins)
