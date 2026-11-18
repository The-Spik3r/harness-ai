---
story: STORY-006
prd: PRD-018
slug: ingress-503-mapping
title: Ingress mapping — require_identity, POST /query and /v1 storage_unavailable with Retry-After
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-018-db-resilience
created: 2026-11-17
---

# Plan: 503 + Retry-After on every HTTP ingress

## Summary

STORY-005 made every infrastructure-class storage failure reach its caller as
`StorageUnavailableError(StorageError)` with `retry_after_seconds`. This story
maps that type, and only that type, to a 503 with `Retry-After` on the three HTTP
ingresses (PRD-018 Section 6.7, D8):

- `require_identity` catches `StorageUnavailableError` from `resolve()` and raises
  `HTTPException(503, "Storage unavailable", headers={"Retry-After": n})`. It is
  never a 401. Break-glass still resolves with no read.
- `POST /query` maps a gate error (`ChatSessionError`, `DuplicateCheckError`,
  `UsageLimitError`) that is *caused by* `StorageUnavailableError` to
  `503 {"detail":"Storage unavailable: the request was not sent to the model."}` +
  `Retry-After`. Any other cause keeps today's 500 arm unchanged.
- `/v1` gets a new `storage_unavailable` fault (503, `api_error`, retryable, no
  `x-should-retry`, `Retry-After`). It covers the same gate faults in
  `_outcome` (JSON, pre-commit stream and post-commit SSE) and a 503
  `HTTPException` from `require_identity` through `_HTTP_ERRORS[503]`.

One shared rule decides "caused by": `storage_unavailable_cause(exc)` in a new
pure module, `app/services/storage_faults.py`. Both routers use it, and so will the
chat UI (STORY-007). The 503 bodies use fixed text and never `str(exc)`. The
driver text is already logged once, through `_redacted()`, by `_unit_of_work`'s
`retry exhausted` / `retry refused` WARNING (`app/db/database.py:1170-1185`,
`_retry_detail` at `:1044-1047`). The routers log only the code and
`retry_after`.

## User Story

As an integrating developer
I want a storage outage to come back as a standard, retryable 503 with `Retry-After` (an OpenAI error object on `/v1`)
So that my client backs off and retries instead of seeing a plain-text 500 or a 401.

## Story Reference

- Story file: `.agents/stories/PRD-018-db-resilience/STORY-006-ingress-503-mapping.md`
- PRD: `.agents/PRDs/PRD-018-db-resilience/PRD.md` (Sections 3, 5 stories 2 and 7, 6.7, 9.1, 9.2 T1/T9, 10, 15 D7/D8/D15, O4, O7)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `app/middleware/auth.py`, `app/routers/query.py`, `app/routers/v1.py`, `app/services/v1_translate.py`, new `app/services/storage_faults.py`, tests |
| Story | STORY-006 |
| PRD | PRD-018 |
| Epic Branch | `epic/PRD-018-db-resilience` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` (UI visual design). This story is backend/HTTP only, and the story's `skills: []` | n/a |

---

## Verified facts the design rests on

- Every gate error wraps with `from exc`, and `exc` is the `StorageError` that left
  `_unit_of_work`, so `__cause__` is the `StorageUnavailableError` itself:
  - `check_duplicate`: `raise DuplicateCheckError(f"Duplicate lookup failed: {exc}") from exc` (`app/services/duplicate_checker.py:32-35`).
  - `admit`: `raise UsageLimitError(f"Usage admission failed: {exc}") from exc` (`app/services/usage_limits.py:159-162`).
  - `chat_sessions._wrapped`: `raise ChatSessionError(f"{operation} failed: {exc}") from exc` (`app/services/chat_sessions.py:67-85`). `owns` uses it at `:229-230`, and returns early when `CHAT_HISTORY_ENABLED` is off (`:226-227`).
- `_unit_of_work` raises `StorageUnavailableError` on breaker open (`app/db/database.py:1125-1133`) and on exhaustion/refusal (`:1186-1190`, `str(exc)` kept: driver text). `find_user_by_token_hash` runs through it (`:2255-2281`), so `resolve()` (`app/services/identity.py:69-92`) propagates it unchanged. Break-glass returns at `identity.py:78-81` before any read.
- Gate errors on `/query` are all pre-upstream: `owns` runs in `_handle_query` before `run_query` (`app/routers/query.py:115-132`), `admit` is step 2c (`app/services/query_pipeline.py:461-462`), `check_duplicate` is step 4 (`:540`), and the upstream is called at `:761`. So "the request was not sent to the model" is always true for these arms, and no row has been written (O7, D15). A `ChatSessionError` is only reachable from `owns` on `/query` (`grep` shows no other `chat_sessions.` use in the pipeline).
- `/v1` streams: a pre-upstream fault leaves `upstream.called` False, so `chat_completions` returns `_json_response` with the real status (`app/routers/v1.py:332-341`). Identity is a dependency and refuses before the route body, through the app-level handler (`v1.py:449-466`, `:489-501`).
- `_http_exception` already forwards `exc.headers` and adds `x-should-retry: false` only below 500 (`v1.py:466`, `_error` at `:167-185`). So a 503 keeps `Retry-After` and gets no `x-should-retry` with no change to `_error`. Outside `/v1/` it delegates to FastAPI's `http_exception_handler`, which also sends `exc.headers`.
- `ActionAuditError` (`query_pipeline.py:82-88, 944-946`) stays `500 internal_error`: PRD 6.7 row "tools: PRD-017's `500 internal_error`, unchanged". The helper alone would match it (its `__cause__` can be a `StorageUnavailableError`), so each router applies the rule only to its own tuple of gate errors.
- Non-`db` tests can open the breaker for real: `force_open` refuses in `before()` with no client touched, and the conftest guard (`tests/conftest.py:653-680`) proves no driver call. `_fresh_storage_breaker` (`:683-707`) resets it.
- Every existing gate-fault test raises a gate error built **without** a cause (`tests/test_v1_errors.py:630-631, 718-733, 795-802, 905-920`; `tests/test_v1_query_isolation.py:170-182`; `tests/test_v1_tools.py:1287-1347`) or drops a table (`MissingRelationError`, `tests/test_query_router.py:210-237`). None is a transient cause, so **none changes**.
- The one test that **must** change is `tests/test_v1_translate_result.py:370-405`. It pins the exact `_FAULTS` key set, `{500, 502}` statuses and the retryable set. Adding `storage_unavailable` is the point of the story, so those assertions are extended with PRD-018 D8 comments. Nothing is relaxed.

---

## Patterns to Follow

### Naming (fault codes and table)
```python
# SOURCE: app/services/v1_translate.py:92-96, 713-724
# Section 7.5, one per pipeline fault (D7). The router names the fault.
UPSTREAM_UNAVAILABLE = "upstream_unavailable"
...
_FAULTS: Mapping[str, Tuple[int, str, bool]] = {
    UPSTREAM_UNAVAILABLE: (502, "api_error", True),
    UPSTREAM_ERROR: (502, "api_error", False),
    INTERNAL_ERROR: (500, "api_error", True),
    REDACTION_FAILED: (500, "api_error", False),
}
```

### Error Handling (router arms, fixed text vs `str(exc)`)
```python
# SOURCE: app/routers/query.py:27-41
    try:
        return await run_in_pipeline(_handle_query, request, identity)
    except ChatSessionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except DuplicateCheckError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
```
```python
# SOURCE: app/routers/v1.py:222-232
    except _PIPELINE_FAULTS as exc:
        code = _fault_code(exc)
        # Who and which fault, never the message: a storage error's text is
        # driver output (T9's rule, applied to faults).
        logger.warning("v1 request failed: user_id=%s code=%s", identity.user_id, code)
        return translate_fault(code, str(exc))
```
```python
# SOURCE: app/routers/v1.py:188-195  (retryable -> no x-should-retry, D7)
def _from_v1_error(error: V1Error) -> JSONResponse:
    return _error(
        error.status_code, error.type, error.code, error.message, error.param,
        headers=None if error.retryable else {"x-should-retry": "false"},
        harness=error.harness,
    )
```

### Tests
```python
# SOURCE: tests/test_v1_errors.py:590-610  (_assert_fault: whole body + retry signal)
    assert (response.status_code, error) == (
        status_code,
        {"message": expected_message, "type": "api_error", "param": None,
         "code": code, "harness": None},
    )
    if retryable:
        assert "x-should-retry" not in response.headers
```
```python
# SOURCE: tests/test_v1_sse.py:388-400  (_sse_events unit test, no storage)
        events = _events("".join(_sse_events(
            _done(exc=RuntimeError(_CANARY)), upstream=_upstream_wrapper(), identity=_IDENTITY,
            include_usage=False,
        )))
```
```python
# SOURCE: tests/conftest.py:695-701  (open breaker in a test)
#   database._storage_breaker.force_open(seconds), or install one with an injected
#   clock via monkeypatch.setattr(database, "_storage_breaker", CircuitBreaker("storage", ..., clock=...))
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/storage_faults.py` | CREATE | The one "caused by `StorageUnavailableError`" rule, `storage_unavailable_cause(exc)`, plus the `Retry-After` header builder. Reused by STORY-007 (chat UI) and STORY-010/011 |
| `app/middleware/auth.py` | UPDATE | `require_identity`: `StorageUnavailableError` becomes 503 `Storage unavailable` + `Retry-After` |
| `app/routers/query.py` | UPDATE | Gate errors caused by `StorageUnavailableError` become 503 with fixed detail + `Retry-After`. Other causes keep the 500 |
| `app/services/v1_translate.py` | UPDATE | `STORAGE_UNAVAILABLE` code + fixed message, `_FAULTS` row (503, api_error, retryable), `V1Error.retry_after_seconds`, `translate_fault(..., retry_after_seconds=None)` |
| `app/routers/v1.py` | UPDATE | `_HTTP_ERRORS[503]`, fixed message for it, `_outcome` / `_fault_code` storage arm, `_from_v1_error` sends `Retry-After` |
| `tests/test_db_resilience_ingress.py` | CREATE | Non-`db` ingress tests: identity, `/query`, `/v1` JSON + stream, T1 zero upstream calls, non-transient causes unchanged, SSE rendering, helper unit tests |
| `tests/test_v1_translate_result.py` | UPDATE | Extend the `_FAULTS` pins (`:370-405`) with `storage_unavailable`, with a PRD-018 D8 comment on each changed assertion |

No changes to `chat_ui/` (STORY-007), `docs/` (STORY-014) or journal paths (STORY-010/011).

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: The shared "caused by" rule

- **File**: `app/services/storage_faults.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring: PRD-018 D8 / Section 6.7. This is the one rule every ingress uses to tell a transient storage refusal from any other storage failure: `/query`, `/v1`, and later the chat UI (STORY-007) and the journal refusals (STORY-010/011). It imports only `app.db.errors` (the `duplicate_checker` precedent, `duplicate_checker.py:8`) and does no I/O. It is a service module, not `app/db/errors.py`, so a chat-UI caller does not import the storage exception surface directly (the coupling `chat_sessions.ChatSessionError`'s docstring warns about, `chat_sessions.py:55-63`).
  - `def storage_unavailable_cause(exc: BaseException) -> Optional[StorageUnavailableError]`: return `exc` if it is a `StorageUnavailableError`, else `exc.__cause__` if *that* is one, else `None`. One level only, on purpose: every gate wraps the unit's own exception with `from exc` (cite the three sites), and a deeper walk would also match faults whose cause is incidental. The docstring states that the caller decides **which** exception types the rule applies to (e.g. `/v1` excludes `ActionAuditError`, PRD 6.7).
  - `def retry_after_headers(cause: StorageUnavailableError) -> Dict[str, str]`: `{"Retry-After": str(cause.retry_after_seconds)}`. One spelling of the header for all ingresses (PRD 6.7: integer seconds, >= 1, which `StorageUnavailableError` already guarantees, `app/db/errors.py:132-135`).
  - Also export the fixed client copy every ingress shares: `STORAGE_UNAVAILABLE_DETAIL = "Storage unavailable"` (identity) and `STORAGE_UNAVAILABLE_NOT_SENT_DETAIL = "Storage unavailable: the request was not sent to the model."` (`/query` gates). The `/v1` message lives in `v1_translate` (Task 4), beside its other copy.
- **Mirror**: module docstring style of `app/db/errors.py:1-12`. Small pure helpers like `app/services/circuit_breaker.py` (no settings, no I/O).
- **Validate**: `.venv/Scripts/python -c "from app.services.storage_faults import storage_unavailable_cause; print('OK')"`

### Task 2: `require_identity` answers 503, never 401

- **File**: `app/middleware/auth.py` (`:14-20`)
- **Action**: UPDATE
- **Implement**:
  ```python
  try:
      identity = resolve(credentials.credentials if credentials else None)
  except StorageUnavailableError as exc:
      raise HTTPException(
          status_code=503, detail=STORAGE_UNAVAILABLE_DETAIL, headers=retry_after_headers(exc)
      ) from exc
  ```
  Catch **only** `StorageUnavailableError`, not `StorageError`. A non-transient storage failure stays today's 500, and `MissingRelationError` is still folded to `None` inside `find_user_by_token_hash` (401, PRD-005 Section 9, pinned by `tests/test_auth_dependencies.py:120-140`). Add a short comment: PRD-018 D8, Section 9.1 (a real outage must not read as a bad credential, PRD-007 STORY-004). Break-glass never reaches the read (`identity.py:78-81`). `require_permission` and `require_admin_token` depend on `require_identity`, so every authenticated route inherits the 503.
  - Logging: none here. The unit already logged the driver text once through `_redacted()`, and breaker-open has none.
- **Mirror**: the `except PermissionDenied: raise HTTPException(...)` arm at `auth.py:25-28`.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 3: `POST /query` gate errors caused by an outage become 503

- **File**: `app/routers/query.py` (`:27-41`)
- **Action**: UPDATE
- **Implement**:
  - Collapse the three storage gate arms into one arm that keeps their order before `PiiRedactorError` / `OpenRouterError`:
    ```python
    except (ChatSessionError, DuplicateCheckError, UsageLimitError) as exc:
        cause = storage_unavailable_cause(exc)
        if cause is not None:
            raise HTTPException(
                status_code=503,
                detail=STORAGE_UNAVAILABLE_NOT_SENT_DETAIL,
                headers=retry_after_headers(cause),
            ) from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    ```
    Keep the existing PRD-013 T7/D9 comment and add a PRD-018 D8 / O7 comment. All three gates run before the upstream and before any row (cite `query_pipeline.py:461-462, 540, 761` and `query.py:115-132`), so the fixed text is true and nothing is written. The 500 arm is byte-identical for every other cause (`MissingRelationError`, or a gate error with no cause), so `test_duplicate_check_storage_failure_returns_500` and `test_v1_query_isolation.py:170-182` pass unchanged. A separate arm per type with the same body is also fine, if the implementer prefers to keep the diff line-for-line. Either way the rule must be the shared helper.
  - Log one WARNING with no exception text: `logger.warning("query request refused: user_id=%s code=storage_unavailable retry_after=%s", identity.user_id, cause.retry_after_seconds)`. `query.py` has no logger today; add `logger = logging.getLogger(__name__)`. This is optional, because AC 4 is already met by the unit's log. If added, a test pins that `_CANARY`/driver text is absent from `caplog.text`.
- **Mirror**: existing arms `query.py:29-41`.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 4: `/v1` fault table: `storage_unavailable`

- **File**: `app/services/v1_translate.py`
- **Action**: UPDATE
- **Implement**:
  - Beside `:92-96`: `STORAGE_UNAVAILABLE = "storage_unavailable"`, plus `STORAGE_UNAVAILABLE_MESSAGE = "Storage is unavailable; the request was not sent to the model."` (fixed copy, PRD Section 5 story 7 / Section 10). Comment: PRD-018 D8, O4.
  - `_FAULTS[STORAGE_UNAVAILABLE] = (503, "api_error", True)`. Update the comment above `_FAULTS` (`:713-718`): storage *outages* are 503 retryable with `Retry-After`; other storage faults keep `internal_error` 500.
  - `V1Error`: add `retry_after_seconds: Optional[int] = None` as the **last** field. A default keeps every existing `V1Error(...)` equality in `tests/test_v1_translate_result.py:381-389` true. Docstring: set only for `storage_unavailable`; the router sends it as `Retry-After`.
  - `translate_fault(code, message, retry_after_seconds: Optional[int] = None)`: pass it through. The module stays pure: no import of `app.db` (the comment at `:716-718` already explains why the table is keyed by code).
- **Mirror**: `v1_translate.py:209-225`, `:719-746`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_v1_translate_result.py -q` (after Task 6).

### Task 5: `/v1` router mapping

- **File**: `app/routers/v1.py`
- **Action**: UPDATE
- **Implement**:
  1. Import `STORAGE_UNAVAILABLE`, `STORAGE_UNAVAILABLE_MESSAGE` from `v1_translate`, and `storage_unavailable_cause` from `app.services.storage_faults`.
  2. `_HTTP_ERRORS` (`:98-103`): add `503: ("api_error", STORAGE_UNAVAILABLE)`. Update the comment at `:91-97`: the only 503 under `/v1/` is `require_identity`'s storage refusal (PRD-018 D8).
  3. `_http_exception` (`:449-466`): when `code == STORAGE_UNAVAILABLE`, the message is `STORAGE_UNAVAILABLE_MESSAGE`, not `exc.detail`. `/query`'s identity detail is "Storage unavailable", and `/v1`'s copy is the PRD Section 10 sentence. `headers=exc.headers` already carries `Retry-After`, and `_error` adds no `x-should-retry` for >= 500. The log line keeps `code=` only.
  4. A module tuple `_STORAGE_GATE_FAULTS = (DuplicateCheckError, UsageLimitError)` with a comment: the faults the outage rule applies to. `ActionAuditError` is deliberately absent (PRD 6.7: tools keep PRD-017's 500), and `ChatSessionError` is unreachable on `/v1` (`:107-110`).
  5. `_fault_code` (`:198-212`): before the `INTERNAL_ERROR` arm, `if isinstance(exc, _STORAGE_GATE_FAULTS) and storage_unavailable_cause(exc) is not None: return STORAGE_UNAVAILABLE`. Docstring: an outage is 503 `storage_unavailable` (PRD-018 D8), any other storage fault stays `internal_error`. `test_fault_code_per_pipeline_fault` (`tests/test_v1_errors.py:625-638`) passes unchanged, because its exceptions have no cause.
  6. `_outcome` (`:222-232`): after `code = _fault_code(exc)` and the existing log line, `if code == STORAGE_UNAVAILABLE: return translate_fault(code, STORAGE_UNAVAILABLE_MESSAGE, retry_after_seconds=storage_unavailable_cause(exc).retry_after_seconds)`. Otherwise keep `translate_fault(code, str(exc))` unchanged. Never `str(exc)` for the outage (T9).
  7. `_from_v1_error` (`:188-195`): merge `{"Retry-After": str(error.retry_after_seconds)}` into the headers when it is set. It is retryable, so there is no `x-should-retry`.
  8. `_sse_events` (`:254-281`) needs **no** change. A post-commit `storage_unavailable` renders through `_outcome`, then `_error_body(outcome.type, outcome.code, outcome.message, ...)`. The headers are already sent, so there is no `Retry-After` there, and that is acceptable (PRD 6.7 last row). Add one sentence to its docstring saying so. A unit test pins the event (Task 7).
- **Mirror**: existing code at the cited lines.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 6: Extend the `_FAULTS` pins

- **File**: `tests/test_v1_translate_result.py` (`:370-405`)
- **Action**: UPDATE (modified pre-existing assertions, each with a `# PRD-018 D8:` comment)
- **Implement**:
  - `_FAULT_CASES`: append `(STORAGE_UNAVAILABLE, 503, True)` and import `STORAGE_UNAVAILABLE`. `test_fault_maps_to_the_section_7_5_row` and `test_every_fault_type_fits_the_error_schema` then cover it with no further change (`retry_after_seconds` defaults to None on both sides).
  - `test_every_fault_is_a_5xx_and_only_transient_ones_retry`: `<= {500, 502, 503}`, and the retryable set gains `STORAGE_UNAVAILABLE`.
  - New test: `translate_fault(STORAGE_UNAVAILABLE, STORAGE_UNAVAILABLE_MESSAGE, retry_after_seconds=7).retry_after_seconds == 7`, and the message is passed through.
  - Do not rename or remove any test, so `_DELIBERATELY_SUPERSEDED_TESTS` is untouched.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_v1_translate_result.py -q`

### Task 7: Ingress tests (non-`db`)

- **File**: `tests/test_db_resilience_ingress.py`
- **Action**: CREATE
- **Implement**: no storage fixture, so the conftest guard (`tests/conftest.py:653-680`) proves zero driver calls. Open the breaker with a frozen clock so `Retry-After` is exact: `monkeypatch.setattr(database, "_storage_breaker", CircuitBreaker("storage", database._BREAKER_FAILURE_THRESHOLD, database._BREAKER_OPEN_SECONDS, clock=lambda: 1000.0))`, then `.force_open(7)`, which gives `Retry-After: 7` (`circuit_breaker.py:142-143, 268-279`). Use a recording upstream stub patched at `app.routers.query.call_openrouter` / `app.routers.v1.call_openrouter`, and a recorder over `query_pipeline.log_query` (`query_pipeline.py:21`) and `app.routers.query.log_query`, to assert "no audit row" (O7) without a database. `_CANARY` text must never appear in any body.
  1. **Helper unit tests** (`storage_unavailable_cause`): the error itself, a gate error `from` it, a gate error from a plain `StorageError` / `MissingRelationError` (None), no cause (None), and a cause two levels deep (None, documenting one level). `retry_after_headers` spelling.
  2. **Identity (AC 1)**, breaker open, user token:
     - Fake-app or real `/query`: `503`, `{"detail": "Storage unavailable"}`, `Retry-After: 7`, status != 401.
     - Break-glass `ADMIN_TOKEN` on an identity-only route (e.g. `require_identity` fake route as in `tests/test_auth_dependencies.py:17-38`) still resolves `200`, no read.
     - `/v1/chat/completions` (json and `stream: true`) and `GET /v1/models` with a user token: `503`, the exact error object `{"message": STORAGE_UNAVAILABLE_MESSAGE, "type": "api_error", "param": None, "code": "storage_unavailable", "harness": None}`, `Retry-After: 7`, `"x-should-retry" not in headers`, `content-type: application/json`. Upstream zero calls.
  3. **`/query` gates (AC 2, T1)**: `TestClient(app)` with `ADMIN_TOKEN` (break-glass is admitted on `query`, `config.py:362`), breaker open:
     - `USAGE_LIMITS_ENABLED=True`: `admit` refuses, giving `UsageLimitError` caused by `StorageUnavailableError`.
     - `USAGE_LIMITS_ENABLED=False`: `check_duplicate` refuses, giving `DuplicateCheckError`.
     - `CHAT_HISTORY_ENABLED=True` + `session_id`: `owns` refuses, giving `ChatSessionError` (verify `database.get_chat_session` runs through `_unit_of_work`. If not, raise a `ChatSessionError` built `from StorageUnavailableError(...)` via monkeypatch of `chat_sessions.owns`).
     - Each: `503`, `{"detail": "Storage unavailable: the request was not sent to the model."}`, `Retry-After: 7`, upstream zero calls, `log_query` recorder empty.
  4. **`/v1` gates (AC 3, T1)**: identity stubbed with `app.dependency_overrides[require_identity] = lambda: Identity("ingress@test", "user")` (cleaned up in a fixture) and the breaker open. Run json and `stream: true` (parametrized like `tests/test_v1_errors.py:103-110`) for both the admit and the duplicate path (toggle `USAGE_LIMITS_ENABLED`). Expect 503 `storage_unavailable` object, `Retry-After: 7`, no `x-should-retry`, upstream zero calls, `log_query` recorder empty. The stream case must still be `application/json` (pre-commit, `v1.py:337-341`).
  5. **Retry-After = breaker closed, budget only (AC 4)**: monkeypatch `query_pipeline.check_duplicate` to raise `DuplicateCheckError("Duplicate lookup failed: " + _CANARY)` `from StorageUnavailableError(_CANARY, retry_after_seconds=1)`. Expect `/query` and `/v1` 503 with `Retry-After: 1`, and `_CANARY` absent from body and from the router's log records (driver text appears only in the unit's own log, which this test does not exercise).
  6. **Non-transient unchanged**: the same monkeypatch but `from MissingRelationError("audit_logs", _CANARY)`. `/query` 500 `detail` = `str(exc)` and `/v1` 500 `internal_error`. Also `ActionAuditError` `from StorageUnavailableError` gives `_fault_code(...) == "internal_error"` (tools unchanged, PRD 6.7).
  7. **SSE post-commit rendering**: unit test on `_sse_events` with a finished future whose exception is `DuplicateCheckError` `from StorageUnavailableError(...)` (mirror `tests/test_v1_sse.py:388-400`, `_done`/`_upstream_wrapper` helpers, copied locally). The event is `{"error": {"message": STORAGE_UNAVAILABLE_MESSAGE, "type": "api_error", "param": None, "code": "storage_unavailable", "harness": None}}`.
  8. **`_fault_code` table**: `DuplicateCheckError`/`UsageLimitError` caused by `StorageUnavailableError` give `storage_unavailable`.
- **Mirror**: `tests/test_v1_errors.py:59-110, 564-610`; `tests/test_auth_dependencies.py:1-38`; `tests/test_v1_sse.py:380-400`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db_resilience_ingress.py -q`

### Task 8: Regression run (targeted, per brief)

- One pytest call, `PYTHONUTF8=1`, no full suite (brief rule):
  `tests/test_db_resilience_ingress.py tests/test_v1_translate_result.py tests/test_v1_errors.py tests/test_v1_sse.py tests/test_v1_router.py tests/test_v1_query_isolation.py tests/test_v1_models.py tests/test_v1_tools.py tests/test_query_router.py tests/test_auth_dependencies.py tests/test_admin_auth.py tests/test_untouched_app.py`
  If the call runs too long, drop `test_v1_tools.py` to `-k "action_audit or fault_code"`. Record the exact counts. "Full suite: GitHub CI on push (user decision)".

---

## End-to-End Tests

- [ ] Breaker forced open: `/query` (break-glass) → 503 + fixed detail + `Retry-After`, zero upstream calls, no row (T1, O7)
- [ ] Breaker forced open: `/v1` non-stream and stream → 503 `storage_unavailable` object + `Retry-After`, no `x-should-retry`, zero upstream calls (T1)
- [ ] Breaker forced open, user token on `/query`, `/v1/chat/completions`, `/v1/models` → 503 (never 401). Break-glass still resolves
- [ ] Non-transient cause (`MissingRelationError`): `test_duplicate_check_storage_failure_returns_500` passes unchanged
- [ ] With storage healthy, the existing `/query` and `/v1` tests pass, and only `test_v1_translate_result.py`'s `_FAULTS` pins changed (PRD-018 D8 comments)

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest <Task 8 file list> -q
```

---

## Risks / open points

1. **Body shape `harness: null`.** Every `/v1` error object carries `"harness": null` (`ErrorDetail`, pinned by `_assert_fault`, `tests/test_v1_errors.py:595-604`). The PRD/story body omits the key. The plan keeps the existing schema (the 503 body is the story's four fields plus `harness: null`, like every other fault) rather than special-casing one fault. Flag to the orchestrator as a documented deviation, and for STORY-014's docs.
2. **`_HTTP_ERRORS` lives in `app/routers/v1.py:98`, not `v1_translate.py`.** The story's AC 3 wording says "`_HTTP_ERRORS[503]`" next to `v1_translate.py`, but the real table is in the router. The plan follows the code.
3. **Identity 503 message on `/v1`.** `exc.detail` is "Storage unavailable" (the `/query` copy, AC 1). `/v1` substitutes the PRD Section 10 sentence for code `storage_unavailable`, so both bodies match their spec.
4. **No `Retry-After` on a post-commit SSE event.** Headers are already sent. This is unreachable today (all gates are pre-upstream), and is rendered for completeness only (PRD 6.7 last row).
5. **One-level cause rule.** If a later story wraps twice (e.g. a service re-wrapping a gate error), it must re-raise `from` the `StorageUnavailableError`, or extend the helper deliberately. This is stated in the helper's docstring.
6. **`ChatSessionError` via a real breaker.** This depends on `database.get_chat_session` running through `_unit_of_work` (STORY-003 converted the store functions). The test has a stated fallback.

---

## Acceptance Criteria

(Copied from story STORY-006)

- [ ] Identity read raises `StorageUnavailableError` → `require_identity` answers `503 {"detail":"Storage unavailable"}` + `Retry-After`, never 401. Break-glass `ADMIN_TOKEN` still resolves with no read.
- [ ] `POST /query` + `DuplicateCheckError` / `UsageLimitError` / `ChatSessionError` caused by `StorageUnavailableError` → `503 {"detail":"Storage unavailable: the request was not sent to the model."}` + `Retry-After`, upstream zero calls, no audit row (O7). Non-transient cause keeps the 500: `test_duplicate_check_storage_failure_returns_500` unchanged.
- [ ] `/v1/chat/completions` (stream and non-stream), same failures or identity unavailable → `503` `storage_unavailable` object, `Retry-After`, no `x-should-retry`. New `_FAULTS` entry. `_HTTP_ERRORS[503]` maps the identity 503.
- [ ] `Retry-After` = `StorageUnavailableError.retry_after_seconds`. No 503 body carries driver text. Driver text logged once through `_redacted()` (by `_unit_of_work`).
- [ ] Breaker forced open → each of `/query`, `/v1` non-stream, `/v1` stream returns its Section 6.7 response with upstream zero calls (T1). Healthy storage: existing `/query` and `/v1` tests unchanged.
- [ ] All tasks completed
- [ ] Backend imports (`from app.main import app`) without error
- [ ] Follows existing patterns
