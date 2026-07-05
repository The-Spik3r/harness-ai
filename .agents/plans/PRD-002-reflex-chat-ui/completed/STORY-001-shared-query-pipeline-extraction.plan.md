---
story: STORY-001
prd: PRD-002
slug: shared-query-pipeline-extraction
title: "Extract run_query(...) shared pipeline function"
type: technical
complexity: medium
epic_branch: epic/PRD-002-reflex-chat-ui        # all stories commit here, no per-story branch
created: 2026-07-04
---

# Plan: Extract run_query(...) shared pipeline function

## Summary

Extract the body of the `POST /query` route handler (duplicate check → pattern check → OpenRouter call → audit log) into a new plain-Python function `app/services/query_pipeline.py::run_query(...)` that returns one of the existing Pydantic response models directly. `app/routers/query.py` becomes a thin adapter: it keeps the `user_id` presence check and HTTPException translation, and delegates everything else to `run_query(...)`. The critical constraint driving the design is that `tests/test_query_router.py` and `tests/test_integration.py` monkeypatch `app.routers.query.call_openrouter` (not `app.services.openrouter_client.call_openrouter`) — so the router must keep importing `call_openrouter` itself and pass that exact (patchable) reference into `run_query(...)` as a parameter, rather than `query_pipeline.py` importing and calling it independently. This is a pure refactor: zero behavior change, validated by running PRD-001's existing test suite unmodified.

## User Story

As an integrating developer
I want the `POST /query` route's pipeline body extracted into a single reusable function
So that the future Reflex chat state can call the exact same logic with no parallel implementation

## Story Reference

- Story file: `.agents/stories/PRD-002-reflex-chat-ui/STORY-001-shared-query-pipeline-extraction.md`
- PRD: `.agents/PRDs/PRD-002-reflex-chat-ui/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | technical |
| Complexity | medium |
| Systems Affected | `app/routers/query.py`, new `app/services/query_pipeline.py` |
| Story | STORY-001 |
| PRD | PRD-002 |
| Epic Branch | `epic/PRD-002-reflex-chat-ui` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` does not exist in this repo (confirmed via directory listing and PRD-002 Appendix, Section 15: "Skills referenced: None"). Story frontmatter `skills: []` is consistent with this.

---

## Patterns to Follow

### Existing route body being extracted (source of truth for behavior)
```python
// SOURCE: app/routers/query.py:18-87 (current, pre-refactor)
@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    if not request.user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")

    try:
        duplicate_result = check_duplicate(request.prompt)
    except DuplicateCheckError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if duplicate_result.is_duplicate:
        log_query(user_id=request.user_id, prompt=request.prompt, device=request.device,
                   was_duplicate_blocked=True, success=True)
        return QueryBlockedDuplicateResponse(reason="Duplicate query within 24 hours",
                                              first_query_at=duplicate_result.first_query_at)

    pattern_result = detect_suspicious_pattern(request.prompt)
    if pattern_result.is_suspicious:
        log_query(user_id=request.user_id, prompt=request.prompt, device=request.device,
                   suspicious_pattern=pattern_result.pattern, success=True)
        return QueryBlockedSuspiciousResponse(reason="Suspicious pattern detected",
                                               pattern=pattern_result.pattern)

    try:
        openrouter_result = call_openrouter(request.prompt, model=request.model,
                                             api_key=request.openrouter_api_key)
    except OpenRouterError as exc:
        log_query(user_id=request.user_id, prompt=request.prompt, device=request.device,
                   model_used=request.model, success=False, error_message=str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    audit_id = log_query(user_id=request.user_id, prompt=request.prompt, device=request.device,
                          response=openrouter_result.response, model_used=openrouter_result.model_used,
                          tokens_used=openrouter_result.tokens_used, success=True)

    return QuerySuccessResponse(response=openrouter_result.response, audit_id=audit_id,
                                 model_used=openrouter_result.model_used,
                                 tokens_used=openrouter_result.tokens_used)
```

### Service module style (dataclass result + module-level function, no FastAPI imports)
```python
// SOURCE: app/services/duplicate_checker.py:1-37
import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.db.database import find_duplicate_timestamp

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class DuplicateCheckError(Exception):
    pass


@dataclass
class DuplicateCheckResult:
    is_duplicate: bool
    first_query_at: Optional[str] = None


def check_duplicate(prompt: str) -> DuplicateCheckResult:
    ...
```
`query_pipeline.py` should follow this same shape: module-level constants/imports at top, no FastAPI types anywhere, plain functions with typed signatures.

### Test convention this refactor MUST NOT break (the reason for the `call_openrouter` injection)
```python
// SOURCE: tests/test_query_router.py:56-61, 76-95
def test_missing_user_id_returns_422(temp_db, monkeypatch):
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
    ...

def test_clean_prompt_success_returns_expected_shape_and_logs_row(temp_db, monkeypatch):
    def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
        return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)
    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)
    ...
```
Also referenced identically in `tests/test_integration.py:42,62,69,88,124` and documented as the deliberate convention in `.agents/plans/PRD-001-harness-ia/completed/STORY-012-integration-test-suite.plan.md:52` ("monkeypatches `app.routers.query.call_openrouter` (not the module-level `openrouter_client.call_openrouter`)"). Because `monkeypatch.setattr` rebinds the **router module's** attribute, `query_pipeline.py` cannot independently import and call `call_openrouter` — it must receive the router's (possibly-patched) reference as an argument.

### Response models being returned directly (plain Pydantic, not FastAPI-specific)
```python
// SOURCE: app/models/schemas.py:14-36
class QuerySuccessResponse(BaseModel):
    status: Literal["SUCCESS"] = "SUCCESS"
    response: str
    audit_id: int
    model_used: str
    tokens_used: int


class QueryBlockedDuplicateResponse(BaseModel):
    status: Literal["BLOCKED"] = "BLOCKED"
    reason: str
    first_query_at: str


class QueryBlockedSuspiciousResponse(BaseModel):
    status: Literal["BLOCKED"] = "BLOCKED"
    reason: str
    pattern: str


QueryResponse = Union[
    QuerySuccessResponse, QueryBlockedDuplicateResponse, QueryBlockedSuspiciousResponse
]
```
`run_query(...)` returns one of these three models directly (they are plain `pydantic.BaseModel`, not FastAPI types), so the route can `return run_query(...)` with zero re-implemented branching, satisfying AC2.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/query_pipeline.py` | CREATE | New `run_query(...)` — the extracted, FastAPI-free pipeline (duplicate check → pattern check → OpenRouter call → audit log) |
| `app/routers/query.py` | UPDATE | Reduce to: `user_id` presence check, call `run_query(...)`, translate `DuplicateCheckError`/`OpenRouterError` to `HTTPException`, return the result as-is |

No test files are changed — `tests/test_query_router.py` and `tests/test_integration.py` must pass unmodified (AC3).

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create `app/services/query_pipeline.py` with `run_query(...)`

- **File**: `app/services/query_pipeline.py`
- **Action**: CREATE
- **Implement**:
  - Imports: `Callable`, `Optional`, `Union` from `typing`; `log_query` from `app.services.audit_logger`; `check_duplicate` from `app.services.duplicate_checker` (do **not** import `DuplicateCheckError` here — let it propagate un-caught, same as today); `call_openrouter`, `OpenRouterError`, `OpenRouterResult` from `app.services.openrouter_client`; `detect_suspicious_pattern` from `app.services.pattern_detector`; `QueryBlockedDuplicateResponse`, `QueryBlockedSuspiciousResponse`, `QuerySuccessResponse` from `app.models.schemas` (plain Pydantic models — permitted, not FastAPI-specific).
  - Define `QueryPipelineResult = Union[QuerySuccessResponse, QueryBlockedDuplicateResponse, QueryBlockedSuspiciousResponse]` as a module-level type alias (mirrors `QueryResponse` in `app/models/schemas.py:34-36`).
  - Define `run_query(user_id: str, prompt: str, device: Optional[str], model: str, openrouter_api_key: Optional[str], call_openrouter: Callable[..., OpenRouterResult] = call_openrouter) -> QueryPipelineResult:`
    - The `call_openrouter` parameter defaults to the real module-level import (so callers like the future `ChatState` can omit it), but callers that need test-patchability (the FastAPI route) must pass their own module-level reference explicitly — see Task 2.
  - Body: line-for-line the logic from `app/routers/query.py:23-87` (source block above), with these adjustments:
    - Do **not** wrap `check_duplicate(prompt)` in a try/except — let `DuplicateCheckError` propagate to the caller unchanged (the router already handles this exception; moving the catch up one frame does not change observable behavior or the exception type raised).
    - Do **not** wrap `call_openrouter(...)` in a try/except that raises `HTTPException` — instead: catch `OpenRouterError`, call `log_query(...)` exactly as today (same args), then `raise` (bare re-raise, propagating `OpenRouterError` to the caller).
    - Replace every `request.<field>` reference with the corresponding bare parameter (`user_id`, `prompt`, `device`, `model`, `openrouter_api_key`).
    - Replace the `call_openrouter(request.prompt, model=request.model, api_key=request.openrouter_api_key)` call with `call_openrouter(prompt, model=model, api_key=openrouter_api_key)` — using the function parameter, not a re-import, so the injected/patched reference is what actually executes.
    - Return the three response models directly (`QueryBlockedDuplicateResponse(...)`, `QueryBlockedSuspiciousResponse(...)`, `QuerySuccessResponse(...)`) exactly as constructed today — same field values, same order of operations (log before duplicate/suspicious return; log after success call).
- **Mirror**: `app/services/duplicate_checker.py:1-37` for module shape/style (no FastAPI imports, typed plain functions).
- **Validate**: `python -c "from app.services.query_pipeline import run_query"` succeeds with no import errors.

### Task 2: Update `app/routers/query.py` to delegate to `run_query(...)`

- **File**: `app/routers/query.py`
- **Action**: UPDATE
- **Implement**:
  - Keep imports: `APIRouter`, `HTTPException` from `fastapi`; `QueryRequest`, `QueryResponse` from `app.models.schemas` (drop the now-unused `QueryBlockedDuplicateResponse`, `QueryBlockedSuspiciousResponse`, `QuerySuccessResponse` imports — no longer referenced in this file); keep `DuplicateCheckError` from `app.services.duplicate_checker` (needed for the except clause); keep `OpenRouterError`, `call_openrouter` from `app.services.openrouter_client` (needed for the except clause and to pass the patchable reference into `run_query`); drop `log_query` and `detect_suspicious_pattern` imports (no longer used directly in this file). Add `from app.services.query_pipeline import run_query`.
  - Rewrite the `query(...)` handler body to:
    ```python
    @router.post("/query", response_model=QueryResponse)
    def query(request: QueryRequest) -> QueryResponse:
        if not request.user_id.strip():
            raise HTTPException(status_code=400, detail="user_id is required")

        try:
            return run_query(
                user_id=request.user_id,
                prompt=request.prompt,
                device=request.device,
                model=request.model,
                openrouter_api_key=request.openrouter_api_key,
                call_openrouter=call_openrouter,
            )
        except DuplicateCheckError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except OpenRouterError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    ```
  - The `call_openrouter=call_openrouter` keyword argument is the critical line: it forwards the router module's own (test-patchable) name, not `query_pipeline.py`'s independent import, into `run_query`.
- **Mirror**: existing route signature/decorator (`app/routers/query.py:18-19`) stays unchanged; only the body shrinks.
- **Validate**: `python -c "from app.routers.query import router"` succeeds.

### Task 3: Run the full existing test suite unmodified

- **File**: N/A (validation only, no file changes)
- **Action**: VALIDATE
- **Implement**: Run `pytest` from the repo root. Confirm all files in `tests/` pass with zero modifications, with particular attention to:
  - `tests/test_query_router.py` — all `monkeypatch.setattr("app.routers.query.call_openrouter", ...)` cases (missing/empty user_id, success shape, duplicate-blocked, suspicious-blocked, OpenRouter failure → 502 + audit row with `success=False`/`error_message`, latency budget).
  - `tests/test_integration.py` — happy path, duplicate-blocked-second-call, all 7 suspicious patterns parametrized, audit/stats consistency across success+duplicate+suspicious rows.
- **Mirror**: N/A — this is a pass/fail gate, not new code.
- **Validate**: `pytest` exits 0 with no failures, errors, or skips introduced.

---

## End-to-End Tests

- [ ] `pytest` — full suite green, unmodified test files (AC3)
- [ ] Manual: `uvicorn app.main:app --reload` starts without error; `curl -X POST localhost:8000/query -H "Content-Type: application/json" -d '{"user_id":"x","prompt":"hello"}'` (with `OPENROUTER_API_KEY` set or a real duplicate/pattern hit) returns the same shape as before the refactor
- [ ] Confirm exactly one audit row is written per request outcome (success, duplicate-blocked, suspicious-blocked, OpenRouter error) — already covered by `tests/test_integration.py`'s row-count assertions

---

## Validation

```bash
python -c "from app.services.query_pipeline import run_query"
python -c "from app.routers.query import router"
pytest
```

---

## Acceptance Criteria

(Copied from story STORY-001)

- [ ] Given the existing `app/routers/query.py` handler, when the pipeline logic is extracted, then it lives in a new `app/services/query_pipeline.py::run_query(...)` callable with no FastAPI-specific types (no `HTTPException`, no `response_model`) in its signature or body.
- [ ] Given `run_query(...)` is called with the same arguments the route currently uses (`user_id`, `prompt`, `device`, `model`, `openrouter_api_key`), when it runs, then it returns a value the route can map 1:1 to `QuerySuccessResponse`, `QueryBlockedDuplicateResponse`, or `QueryBlockedSuspiciousResponse` without re-implementing any branching logic.
- [ ] Given `app/routers/query.py` is updated to call `run_query(...)`, when PRD-001's existing test suite (STORY-012) runs, then it passes unmodified — this is a pure refactor with zero behavior change.
- [ ] Given the `user_id` presence check currently done in the route, when the refactor is complete, then this validation remains enforced in the route as a pre-check (unchanged location).
- [ ] Given any outcome (success, duplicate-blocked, suspicious-blocked, or OpenRouter error), when `run_query(...)` completes, then exactly one audit row is still written via `log_query(...)`, matching current behavior exactly.
- [ ] All tasks completed
- [ ] `pytest` passes (full suite, unmodified)
- [ ] Backend server starts without error (`uvicorn app.main:app --reload`)
- [ ] Follows existing patterns (dataclass-free plain function, no FastAPI imports in `query_pipeline.py`)
