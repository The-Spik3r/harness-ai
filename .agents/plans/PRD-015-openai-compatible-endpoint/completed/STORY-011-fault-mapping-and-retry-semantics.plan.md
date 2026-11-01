---
story: STORY-011
prd: PRD-015
slug: fault-mapping-and-retry-semantics
title: "Upstream and internal fault mapping with deliberate retry semantics"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-015-openai-compatible-endpoint
created: 2026-10-23
---

# Plan: Upstream and internal fault mapping with deliberate retry semantics

## Summary

Today an exception that escapes `run_conversation` on `/v1` reaches Starlette as an unhandled
error: a plain-text 500 with no OpenAI shape and no retry signal. This story maps the four
pipeline faults to the last four rows of PRD Section 7.5. A pure table in `v1_translate`
(`_FAULTS`: code → status, `type`, retryable) plus `translate_fault(code, message) -> V1Error`
holds the mapping. The router gets an `except` around `await run_in_pipeline(...)`, mirroring
`app/routers/query.py`. It classifies the exception to a fault code (`OpenRouterError` by its
`retryable`, storage errors as `internal_error`, `PiiRedactorError` as `redaction_failed`) and
sends the error through the existing `_error` helper. Non-retryable 5xx gain
`x-should-retry: false`. Retryable ones carry no such header, so the SDK's status rule retries
them. The pipeline already writes the same audit rows for `/v1` as for `/query`, so the audit
side needs tests, not code. The upstream tests drive the real `call_openrouter` over
`httpx.MockTransport`, so `retryable` comes from STORY-002's classifier.

## User Story

As an integrating developer
I want a transient upstream or storage fault to be one my client retries and a deterministic fault to be one it does not
So that retries recover from blips without hammering the harness on failures that will repeat

## Story Reference

- Story file: `.agents/stories/PRD-015-openai-compatible-endpoint/STORY-011-fault-mapping-and-retry-semantics.md`
- PRD: `.agents/PRDs/PRD-015-openai-compatible-endpoint/PRD.md` (Sections 2, 7.5, 9.2 T6/T7, 11, 14 Risk 5, 15 D7)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/services/v1_translate.py`, `app/routers/v1.py`, tests |
| Story | STORY-011 |
| PRD | PRD-015 |
| Epic Branch | `epic/PRD-015-openai-compatible-endpoint` (commit directly on this branch) |

Dependencies STORY-002 and STORY-010 are both `done`.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` holds only `frontend-design`, and this story is backend only. The story says "Skills: none applicable". | — |

---

## Patterns to Follow

### The `/query` chain this mirrors

```python
# SOURCE: app/routers/query.py:27-41
try:
    return await run_in_pipeline(_handle_query, request, identity)
except ChatSessionError as exc:
    raise HTTPException(status_code=500, detail=str(exc)) from exc
except DuplicateCheckError as exc:
    raise HTTPException(status_code=500, detail=str(exc)) from exc
except UsageLimitError as exc:
    raise HTTPException(status_code=500, detail=str(exc)) from exc
except PiiRedactorError as exc:
    raise HTTPException(status_code=500, detail=str(exc)) from exc
except OpenRouterError as exc:
    raise HTTPException(status_code=502, detail=str(exc)) from exc
```

### A pure table with a lookup, mirrored for faults

```python
# SOURCE: app/services/v1_translate.py:409-436, 452-471
_VERDICTS: Mapping[type, Tuple[int, str, str, Callable[[Any], str]]] = {
    QueryBlockedDuplicateResponse: (
        400, "invalid_request_error", DUPLICATE_REQUEST,
        lambda r: f"first seen {r.first_query_at}",
    ),
    ...
}

def translate_verdict(result: QueryBlockedResponse) -> V1Error:
    try:
        status_code, type_, default_code, details = _VERDICTS[type(result)]
    except KeyError:
        raise TypeError(f"no /v1 verdict for {type(result).__name__}") from None
```

### Error body and the retry header (the one builder)

```python
# SOURCE: app/routers/v1.py:97-124
def _error(status_code, type_, code, message, param=None, headers=None, harness=None):
    ...
    if status_code < 500:
        headers = {**(headers or {}), "x-should-retry": "false"}
    return JSONResponse(body.model_dump(mode="json"), status_code=status_code, headers=headers)

def _from_v1_error(error: V1Error) -> JSONResponse:
    return _error(error.status_code, error.type, error.code, error.message, error.param,
                  harness=error.harness)
```

### Where `retryable` comes from

```python
# SOURCE: app/services/openrouter_client.py:112-122, 176-183
def _classify_http_error(exc):
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status, status >= 500 or status == 429
    if isinstance(exc, httpx.TransportError):
        return None, True
    return None, False
...
raise OpenRouterError(f"OpenRouter request failed: {exc}",
                      upstream_status=upstream_status, retryable=retryable) from exc
```

Every other `OpenRouterError` (empty messages, missing key, unexpected shape, null content)
is built without `retryable=` and defaults to `False`.

### Tests: the real client over `MockTransport`

```python
# SOURCE: tests/test_v1_query_isolation.py:229-241
def _upstream_over(transport: httpx.MockTransport):
    def _call(messages, model="gpt-4", api_key=None, params=None):
        with httpx.Client(transport=transport) as http_client:
            return _real_call_openrouter(
                messages, model=model, api_key=api_key, params=params, client=http_client
            )
    return _call
```

### Tests: storage and redaction faults through the pipeline's own bindings

```python
# SOURCE: tests/test_v1_query_isolation.py:170-195, tests/test_duplicate_scope.py:170-181
monkeypatch.setattr(query_pipeline, "check_duplicate",
                    _raising(DuplicateCheckError("Duplicate lookup failed: isolation probe")))
monkeypatch.setattr(query_pipeline, "redact", _raising(PiiRedactorError("...")))
# output side: real on the first call, raise on the second
```

Under `code`, `_redact` calls `query_pipeline.redact_for_policy` (query_pipeline.py:173-190),
not `redact`. The `/v1` tests patch that name. The usage gate is `query_pipeline.admit`
(query_pipeline.py:396-397).

### Tests: whole-body assertions

```python
# SOURCE: tests/test_v1_errors.py:99-115
def _error(status_code, type_, code, message, harness=None, param=None): ...
def _assert_response(response, expected):
    status_code, body = expected
    assert (response.status_code, response.json()) == (status_code, body)
    assert response.headers["x-should-retry"] == _NO_RETRY
    assert _CANARY not in response.text
```

---

## Design decisions (made here, flagged for review)

1. **The table is keyed by fault code, not exception type.** The story asks for "exception type
   + `retryable` → status, type, code, retry flag" in `v1_translate`. `DuplicateCheckError`
   lives in `duplicate_checker` (imports `app.db.database`), `UsageLimitError` in
   `usage_limits` (storage and settings), `PiiRedactorError` in `pii_redactor` (spaCy,
   Presidio, settings). Importing any of them breaks `test_is_pure`
   (`tests/test_v1_translate_request.py:333-349`) and the module's "no storage" rule, which
   STORY-010 kept for the same reason (`v1_translate.py:399-400`). So:
   - `v1_translate` holds `_FAULTS: Mapping[str, Tuple[int, str, bool]]`, which maps
     code → (status, type, retryable), and `translate_fault(code, message) -> V1Error`.
   - `app/routers/v1.py` holds the exception → code step (`_fault_code(exc)`), the only place
     that imports the four exception types. STORY-013's post-commit error event is in the same
     module, so it reuses both `_fault_code` and `translate_fault`.
2. **`V1Error` gains `retryable: bool = False`.** It goes last with a default, so
   `translate_verdict`'s keyword construction is unchanged. `_from_v1_error` adds
   `x-should-retry: false` when `not error.retryable`. For a 4xx, `_error` already adds it, so
   the merge is idempotent. A retryable fault sends **no** header, rather than `true`: "true"
   would force a retry even where the SDK's status rule would not retry, and the AC asks only
   for its absence.
3. **`error.message` is `str(exc)`**, exactly the `detail` `/query` returns for the same fault.
   For upstream errors this is the client's own text. It names the httpx failure (status line
   and URL) or the shape problem, never the response body. `KeyError` / `JSONDecodeError` texts
   are a key name or a parse position. A test makes the upstream body a canary and asserts it is
   absent. Storage messages (`Duplicate lookup failed: ...`) can carry driver text, as `/query`'s
   500 detail already does. That is accepted for parity, and T6 is about content, which those
   errors never hold. `harness` is `null`, since there is no pipeline response.
4. **The except chain is one arm over a tuple** (`_PIPELINE_FAULTS`), with the per-type choice
   in `_fault_code`. The chain is the four `/query` arms minus `ChatSessionError`: `/v1` passes
   no session, so it cannot be raised. A test pins `session_id=None`. An exception outside the
   tuple (a `TypeError` from `translate_verdict`, a bug) still propagates to Starlette's 500.
   That is intended: guessing a shape for a bug is out of scope, as STORY-010 said for the
   verdict table.
5. **One log line per fault** at WARNING: `v1 request failed: user_id=%s code=%s`. This matches
   T9's "who and which rule, never the message". `/query` does not log faults. `/v1` is the door
   unattended agents use, and the code is the only operator signal that is not in the audit
   (storage faults write no row).
6. **No change to `query_pipeline`.** Each fault arm there already writes its row with the
   caller's `ingress` (`query_pipeline.py:644-662, 678-696, 736-760`), and the storage faults
   write none (`:384-388`). AC 3 and AC 5 are proven by tests, not code.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/v1_translate.py` | UPDATE | Fault codes, `_FAULTS` table, `translate_fault`, `V1Error.retryable`; docstring |
| `app/routers/v1.py` | UPDATE | `_PIPELINE_FAULTS`, `_fault_code`, the except around `run_in_pipeline`, retry header from `V1Error.retryable`, WARNING log; `INTERNAL_ERROR` constant replaces the literal in `_SERVER_ERROR`; docstring/comment updates |
| `tests/test_v1_translate_result.py` | UPDATE | Unit tests for the fault table (no db) |
| `tests/test_v1_errors.py` | UPDATE | HTTP tests per fault (MockTransport for upstream), audit parity with `/query`, retry-then-answer, `session_id=None`, log line, canary |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Fault table in `v1_translate`

- **File**: `app/services/v1_translate.py`
- **Action**: UPDATE
- **Implement**:
  - Constants next to the verdict codes: `UPSTREAM_UNAVAILABLE = "upstream_unavailable"`,
    `UPSTREAM_ERROR = "upstream_error"`, `INTERNAL_ERROR = "internal_error"`,
    `REDACTION_FAILED = "redaction_failed"`.
  - `V1Error`: append `retryable: bool = False`, and say in the docstring that it is True only
    for a fault the client may retry. Every verdict is False.
  - Below `translate_verdict`, add a comment block that cites Section 7.5 and D7, then
    `_FAULTS: Mapping[str, Tuple[int, str, bool]]`:
    `UPSTREAM_UNAVAILABLE: (502, "api_error", True)`, `UPSTREAM_ERROR: (502, "api_error", False)`,
    `INTERNAL_ERROR: (500, "api_error", True)`, `REDACTION_FAILED: (500, "api_error", False)`.
  - `translate_fault(code: str, message: str) -> V1Error`: look up the code, and raise
    `TypeError(f"no /v1 fault for {code}")` from None on a miss, mirroring `translate_verdict`.
    Return `V1Error(status_code, type, code, message, retryable=...)` with `harness=None`. The
    docstring says the router names the code (design decision 1), and that the message is the
    exception's own text (decision 3).
  - Module docstring: add "and a pipeline fault into the `V1Error` its retry semantics call for
    (D7)".
- **Mirror**: `translate_verdict` / `_VERDICTS` (`v1_translate.py:409-471`)
- **Validate**: `$PY -m pytest tests/test_v1_translate_request.py::test_is_pure -q -m "not db"` (purity still holds)

### Task 2: Unit tests for the table

- **File**: `tests/test_v1_translate_result.py`
- **Action**: UPDATE
- **Implement** (new section `# --- STORY-011: faults ---`, module docstring extended):
  - Parametrized `test_fault_maps_to_the_section_7_5_row`: each code →
    (status, `type`, retryable), with `message` passed through and `harness is None`.
  - `test_unknown_fault_is_a_type_error`.
  - `test_every_fault_is_a_5xx_and_only_transient_ones_retry`: statuses ⊆ {500, 502}, and the
    set of retryable codes == {UPSTREAM_UNAVAILABLE, INTERNAL_ERROR}.
  - `test_no_verdict_is_retryable`: every `_VERDICT_CASES` translation has `retryable is False`.
  - `test_every_fault_type_fits_the_error_schema`: `ErrorDetail(type=...)` accepts `api_error`,
    as the existing verdict schema test does.
- **Mirror**: `test_verdict_maps_to_the_section_7_5_row`, `test_no_verdict_is_retryable_by_status` (`tests/test_v1_translate_result.py:294-348`)
- **Validate**: `$PY -m pytest tests/test_v1_translate_result.py -q -m "not db"`

### Task 3: Router mapping

- **File**: `app/routers/v1.py`
- **Action**: UPDATE
- **Implement**:
  - Imports: `DuplicateCheckError`, `UsageLimitError`, `PiiRedactorError`, and `OpenRouterError`
    (added to the existing `openrouter_client` import). From `v1_translate`: `INTERNAL_ERROR`,
    `REDACTION_FAILED`, `UPSTREAM_ERROR`, `UPSTREAM_UNAVAILABLE`, `translate_fault`.
  - `_PIPELINE_FAULTS = (OpenRouterError, DuplicateCheckError, UsageLimitError, PiiRedactorError)`,
    with a comment: `/query`'s chain minus `ChatSessionError`, since `/v1` passes no session.
  - `_fault_code(exc) -> str`: an `OpenRouterError` gives `UPSTREAM_UNAVAILABLE` if
    `exc.retryable`, else `UPSTREAM_ERROR`. `DuplicateCheckError` / `UsageLimitError` give
    `INTERNAL_ERROR`. `PiiRedactorError` gives `REDACTION_FAILED`. The comment says STORY-013's
    post-commit event reuses it.
  - In `chat_completions`, wrap `result = await run_in_pipeline(...)` in
    `try: ... except _PIPELINE_FAULTS as exc:`, then
    `code = _fault_code(exc)`; `logger.warning("v1 request failed: user_id=%s code=%s", identity.user_id, code)`;
    `return _from_v1_error(translate_fault(code, str(exc)))`. Add a comment that the pipeline has
    already written whatever row `/query` writes for the same fault (decision 6).
  - `_from_v1_error`: pass `headers=None if error.retryable else {"x-should-retry": "false"}`.
  - `_SERVER_ERROR = ("api_error", INTERNAL_ERROR)`. Rewrite the `_HTTP_ERRORS` comment's last
    clause ("STORY-011 owns the deliberate 5xx mapping") to say the deliberate 5xx are the
    pipeline faults, which `chat_completions` maps.
  - Module docstring: replace "STORY-011 maps the pipeline's exceptions" with a sentence on
    what it now does (Section 7.5's fault rows, D7).
- **Mirror**: `app/routers/query.py:27-41`; logging as `chat_completions`' refusal log (`v1.py:148`)
- **Validate**: `$PY -m pytest tests/test_v1_router.py tests/test_v1_errors.py -q` (the existing tests still pass)

### Task 4: HTTP tests per fault

- **File**: `tests/test_v1_errors.py`
- **Action**: UPDATE
- **Implement**: new section `# --- STORY-011: faults ---`, plus a module docstring paragraph
  (faults are 5xx, retried only when transient, with the upstream ones driven over
  `MockTransport`).
  - Helpers: `_upstream_over(handler)`, copied from `test_v1_query_isolation.py:229-241` but
    built from a handler function. `_raising(exc)`. `_assert_fault(response, status, code,
    retry)`: whole body `_error(status, "api_error", code, <message>)`, with `harness: None`.
    When `retry` is False, `x-should-retry == "false"`; when True, the header is absent. Always
    check `_CANARY not in response.text`.
  - **Upstream, retryable** (parametrized ids `5xx`, `429`, `connect`, `timeout`): the handler
    returns `httpx.Response(503 | 429, text=_CANARY)` or raises `httpx.ConnectError` /
    `httpx.ReadTimeout`. Expect 502 `upstream_unavailable` with no header. Assert that `message`
    starts with `"OpenRouter request failed: "`. Do not pin the exact text: it is httpx's string
    with the URL.
  - **Upstream, not retryable** (ids `4xx`, `malformed`, `null-content`, `missing-key`):
    `httpx.Response(400, text=_CANARY)`, `json={"unexpected": _CANARY}`,
    `json={"choices": [{"message": {"content": None}, "finish_reason": "stop"}], "usage": {"total_tokens": 1}}`,
    and `monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")` with a handler that fails the
    test if called. Expect 502 `upstream_error` with `x-should-retry: false`. Pin the exact
    message for the last three, which are the client's fixed strings.
  - **Storage**: `query_pipeline.check_duplicate` raises
    `DuplicateCheckError("Duplicate lookup failed: probe")`, and `query_pipeline.admit` raises
    `UsageLimitError("Usage admission failed: probe")`. Each gives 500 `internal_error`, no
    header, the exact message, `_count_audit_rows() == 0`, and `upstream.calls == []`.
  - **Redaction, input**: `query_pipeline.redact_for_policy` raises
    `PiiRedactorError("PII analysis failed: probe")`. Expect 500 `redaction_failed`, the header,
    and nothing upstream.
  - **Redaction, output**: set `settings.PII_CODE_REDACT_OUTPUT = True` and call
    `pii_policy.load()` (conftest restores it). `redact_for_policy` is real on its first call and
    raises on the second. Expect 500 `redaction_failed` with the header.
- **Mirror**: `tests/test_v1_query_isolation.py:170-241`, `tests/test_duplicate_scope.py:162-181`, `tests/test_query_router.py:633-662`
- **Validate**: `$PY -m pytest tests/test_v1_errors.py -q -k fault`

### Task 5: Audit parity, retry-then-answer, session, log

- **File**: `tests/test_v1_errors.py`
- **Action**: UPDATE
- **Implement**:
  - `test_fault_rows_match_query_s` (parametrized over the six fault set-ups from Task 4 that
    `/query` can also reach: upstream retryable, upstream 4xx, duplicate lookup, usage gate,
    input redaction, output redaction). Install the same fault for both doors. Patch
    `app.routers.query.call_openrouter` and `app.routers.v1.call_openrouter`, and patch both
    `redact` and `redact_for_policy` for redaction. For output redaction, `/query`'s `chat`
    policy already redacts output, so `PII_CODE_REDACT_OUTPUT=True` is only for `/v1`. POST
    `/query`, then `/v1` with the same prompt, and compare row deltas. Same count (1 for upstream
    and redaction, 0 for storage). For a row: same `success` (False), same `error_message`, and
    `model_used` set exactly when `/query`'s is. The `/v1` row has `ingress == "v1"`,
    `profile == "code"` and `streamed is False`. The redaction faults' messages are equal because
    the probe text is fixed. Note in a comment that `pii_*` fields are not compared: the two
    profiles differ by design (PRD-012).
  - `test_retryable_upstream_failure_then_retry_is_answered_not_duplicate` (AC 5, PRD-009 6.3):
    the handler answers 503 first and 200 second. POST the same body twice. The first is 502
    `upstream_unavailable`, the second is 200. Two rows: `[False, True]` by `success`, both with
    `ingress='v1'`, and the second is not a `duplicate_request`.
  - `test_run_conversation_gets_no_session`: wrap the real `run_conversation` in a spy. Bind its
    args with `inspect.signature(real).bind(*args, **kwargs)` and assert
    `bound.arguments.get("session_id") is None`. Delegate to the real function, and expect a 200.
  - `test_fault_logs_user_and_code_only`: for a `DuplicateCheckError` whose text carries
    `_CANARY`, `caplog` for `app.routers.v1` shows exactly one WARNING record,
    `v1 request failed: user_id=juan@empresa.com code=internal_error`. `_CANARY` is not in
    `caplog.text`, though it is in the body (decision 3, parity with `/query`'s detail). Say so in
    a comment, and skip the body canary check for this test.
- **Mirror**: `test_request_refusal_logs_user_and_code_only` (`tests/test_v1_errors.py:445-455`); `_only_row` / `get_audit_log`
- **Validate**: `$PY -m pytest tests/test_v1_errors.py -q`

### Task 6: Regression sweep

- **Implement**: run the Validation block. `/query`'s bodies must not move.
  `tests/test_v1_query_isolation.py` and `tests/test_query_router.py` pass unchanged.
- **Validate**: see Validation

---

## End-to-End Tests

Live uvicorn on the epic branch, using the `/v1` live E2E recipe in memory (a throwaway libSQL
container and `HARNESS_TEST_LIBSQL_URL`; OpenRouter is TLS-blocked, so no real model):

- [ ] Start with `OPENROUTER_BASE_URL=http://127.0.0.1:9` (a closed loopback port). POST
      `/v1/chat/completions` with a user token → 502 `upstream_unavailable`, no
      `x-should-retry` header, one `success=0` row with `ingress='v1'`.
- [ ] Restart with `OPENROUTER_API_KEY=` (empty) → 502 `upstream_error`,
      `x-should-retry: false`, one `success=0` row.
- [ ] The same faulty start, POST `/query` → 502 `{"detail": "..."}` as before (no OpenAI shape).
- [ ] Optional, the `openai` SDK in the venv: `OpenAI(base_url=..., max_retries=2)` against the
      closed-port start. The SDK raises `InternalServerError` after 3 attempts, which writes 3
      rows. Against the empty-key start it raises after 1 attempt (1 row). STORY-015 owns the
      pinned-version verification; this is a smoke check only.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| httpx's `HTTPStatusError` text changes and an exact-message pin breaks | Retryable upstream messages are checked by prefix and by canary absence, not pinned. Only the client's own fixed strings are pinned |
| `PII_CODE_REDACT_OUTPUT` toggled in a test leaks into later tests | `pii_policy.load()` after the monkeypatch; conftest's `_default_pii_policy` restores it (the pattern in `test_redaction_limit_is_400_redaction_limit_exceeded`) |
| Real Presidio on the first `redact_for_policy` call is slow | The prompt is short. Same cost as the existing v1 success tests |
| The `/query`-vs-`/v1` parity test drifts into asserting profile differences | Compare only the fault fields (count, `success`, `error_message`, `model_used` presence), plus the `/v1` door fields |
| A MockTransport handler that raises is seen as a transport error by httpx | It is: `MockTransport` propagates the raised `httpx.ConnectError` / `ReadTimeout` unchanged, which is what `_classify_http_error` reads |
| Shared libSQL flakes during the db tests | Per the test env memory, restart or use a throwaway container. Do not bisect code on mass fixture errors |

---

## Validation

```bash
PY=/c/Users/tobip/.venvs/harness-ai/Scripts/python.exe
$PY -m pytest tests/test_v1_translate_result.py tests/test_v1_translate_request.py -q -m "not db"
$PY -m pytest tests/test_v1_errors.py tests/test_v1_router.py tests/test_v1_query_isolation.py -q
$PY -m pytest tests/test_query_router.py tests/test_query_outcomes_regression.py tests/test_duplicate_scope.py -q
$PY -m pytest tests/ -q -m "not db"
```

---

## Acceptance Criteria

(Copied from story `STORY-011`)

- [ ] Given `OpenRouterError(retryable=True)` (timeout, connect, upstream 5xx, upstream 429), when it reaches the `/v1` route, then 502 `api_error` / `upstream_unavailable` without `x-should-retry: false`; given `retryable=False` (upstream 4xx, malformed shape, null content, missing key), then 502 `upstream_error` with `x-should-retry: false`.
- [ ] Given `DuplicateCheckError` or `UsageLimitError`, when raised, then 500 `internal_error`, retryable; given `PiiRedactorError` (input or output), then 500 `redaction_failed` with `x-should-retry: false`.
- [ ] Given each fault, when the audit is read, then the rows are exactly what `/query` writes for the same fault today (one `success=False` row for upstream and redaction errors; none for a failed duplicate lookup or usage gate), with `ingress='v1'`.
- [ ] Given an upstream error message, when it becomes `error.message`, then it is the client's `OpenRouterError` text and never contains the provider's response body.
- [ ] Given a retryable upstream failure retried once by a client and then answered, when the audit is read, then the failed attempt is `success=False` and the retry is not held as a duplicate (PRD-009 Section 6.3).
- [ ] All tasks completed
- [ ] `-m "not db"` suite passes; ASCII-only test output
- [ ] `/query` bodies unchanged (`tests/test_v1_query_isolation.py` passes unmodified)
- [ ] Follows existing patterns
