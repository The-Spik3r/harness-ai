---
story: STORY-008
prd: PRD-001
slug: post-query-pipeline
title: "POST /query endpoint: full interception pipeline"
type: feature
complexity: medium
epic_branch: epic/PRD-001-harness-ia
created: 2026-07-04
---

# Plan: POST /query endpoint — full interception pipeline

## Summary

Add `app/routers/query.py`, the first router in the codebase, exposing `POST /query` and composing the four services built in STORY-004 through STORY-007 into the exact 8-step pipeline documented in PRD Section 6: verify `user_id` → hash + duplicate-check the prompt → pattern-check the prompt → forward to OpenRouter → log the outcome → respond. The route handler stays thin (no business logic inline, per the story's own Technical Notes) — it only sequences existing service calls and maps their results onto the three `QueryResponse` shapes from STORY-003. Every exit path (empty `user_id`, duplicate block, suspicious-pattern block, OpenRouter failure, success) writes exactly one audit row before returning, except the up-front `user_id` presence check, which by definition happens before any hashing/forwarding/logging. `app/main.py` registers the new router; no other file changes.

## User Story

As an integrating developer
I want a single `POST /query` endpoint that runs the full harness pipeline
So that every prompt is verified, checked for duplicates/injection, forwarded to OpenRouter, and logged before a response reaches the user

## Story Reference

- Story file: `.agents/stories/PRD-001-harness-ia/STORY-008-post-query-pipeline.md`
- PRD: `.agents/PRDs/PRD-001-harness-ia/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | feature |
| Complexity | medium |
| Systems Affected | `app/routers/` (new package), `app/main.py` (router registration) |
| Story | STORY-008 |
| PRD | PRD-001 |
| Epic Branch | `epic/PRD-001-harness-ia` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` does not exist in this repo, and the story's `skills: []` frontmatter is empty — same situation as every prior story in this PRD.

---

## Codebase State

All four dependency services already exist and are done (STORY-004–007), each following the same function-based-service convention: a module constant or two, one custom exception class, one plain function, no classes/DI:

- `app/services/duplicate_checker.py:26-37` — `check_duplicate(prompt: str) -> DuplicateCheckResult` (`is_duplicate`, `first_query_at`); hashes internally via `hash_prompt`; raises `DuplicateCheckError` on `sqlite3.Error`. Combines PRD Section 6 steps 2 ("hash prompt") and 3 ("look up hash") into one call.
- `app/services/pattern_detector.py:21-26` — `detect_suspicious_pattern(prompt: str) -> PatternDetectionResult` (`is_suspicious`, `pattern`); pure function, no exceptions, no I/O.
- `app/services/openrouter_client.py:24-66` — `call_openrouter(prompt, model="gpt-4", api_key=None, client=None) -> OpenRouterResult` (`response`, `model_used`, `tokens_used`); raises `OpenRouterError` on config/network/response-shape failures, never a raw `httpx` exception.
- `app/services/audit_logger.py:12-39` — `log_query(user_id, prompt, device=None, response=None, model_used=None, tokens_used=None, was_duplicate_blocked=False, suspicious_pattern=None, success=True, error_message=None) -> int` (returns `audit_id`); hashes/truncates prompt+response internally, writes one row via `insert_audit_log`.

`app/models/schemas.py:6-36` (STORY-003, done) already defines `QueryRequest` (`user_id: str`, `prompt: str` both required, `device`/`model="gpt-4"`/`openrouter_api_key` optional) and the three response shapes plus `QueryResponse = Union[...]`. Its own plan (STORY-003 plan, Design Decision 6) explicitly deferred "no emptiness/whitespace validation on `user_id`" to "the request-pipeline story" — i.e. this one. Pydantic's required-field check already rejects a **missing** `user_id`/`prompt` with a 422 before the route handler ever runs (FastAPI validates the body before calling the endpoint function), which alone satisfies AC 1's literal wording ("a request missing `user_id`"); this plan additionally rejects an empty/whitespace `user_id` explicitly, per RF-14's "simple presence check" framing (Section 7) that STORY-003 flagged as out of its own scope.

`app/main.py:16-18` has the exact placeholder comment this story fills in: `# - app.routers.query (POST /query) -> STORY-008`. No `app/routers/` package exists yet — this is the first router in the repo, so there is no existing `APIRouter` example to mirror; the plan follows the same "plain function, minimal ceremony" style used everywhere else in `app/`.

No test file exercises more than one service together yet. `tests/test_main.py` is the only file using `fastapi.testclient.TestClient(app)`; `tests/test_duplicate_checker.py:39-51` is the only precedent for a `temp_db` fixture (points `settings.DATABASE_URL` at a `tmp_path` file, then `init_db()`). This story's test file combines both: `TestClient` for HTTP-level assertions, `temp_db` for a real (isolated) SQLite backing store, and `monkeypatch` to fake `call_openrouter` — no network call is ever made in tests, matching the "monkeypatch only, no mock libraries" convention already established by `tests/test_openrouter_client.py`.

---

## Design Decisions

1. **Explicit empty/whitespace `user_id` check, in addition to Pydantic's required-field check.** Pydantic already rejects a wholly *missing* `user_id` with a 422 before the handler runs — satisfying AC 1 as literally worded. But STORY-003's plan deliberately left "non-empty" enforcement to this story (RF-14: "simple presence check, not full auth"). This plan adds `if not request.user_id.strip(): raise HTTPException(400, ...)` as the very first line of the handler — before `check_duplicate`, before any hashing, before any audit write — so an empty string is rejected the same way a missing field is, with zero side effects.

2. **Blocked responses (duplicate/suspicious) return HTTP 200, not a 4xx.** PRD Section 10's examples show plain JSON bodies with no HTTP status called out, and the MVP's stated principle is "Fail loud, not silent — blocked requests return a clear, structured reason — never a silent drop" (Section 2). A block is a correct, expected pipeline outcome (the system worked as designed), not a client error — so it gets a normal 200 with a `status: "BLOCKED"` body, exactly like the PRD's documented shape, letting `response_model=QueryResponse` do the serialization. Only genuine failures (upstream/config errors) use non-2xx codes.

3. **`success=True` is logged for duplicate- and suspicious-pattern-blocked rows; `success=False` is reserved for actual upstream/DB failures.** PRD Section 10's `/stats` example (`total_queries: 250, blocked_duplicates: 12, blocked_suspicious: 3, success_rate: "98.4%"`) only works out arithmetically if blocked requests count toward the *successful* 98.4% (250 × 0.984 ≈ 246 — far more than the 15 blocked requests, so blocking can't be what drags `success` down). `success` therefore means "the harness handled this request without an internal/upstream error," independent of whether the outcome was a block. `tests/test_audit_logger.py`'s own STORY-006 example passing `success=False` for a suspicious-blocked row was an arbitrary parameter choice for testing `log_query` in isolation, not a semantic mandate for the pipeline — this plan follows the `/stats` math instead, since STORY-011 (not yet built) will consume `success` to compute that exact field.

4. **OpenRouter failures are caught, logged with `success=False` and `error_message=str(exc)`, then surfaced as HTTP 502.** This is explicit in PRD Risk #5's mitigation ("Log failed upstream calls with `success=false` and a clear `error_message`, rather than silently dropping or mis-logging them as successful") and in the story's own Technical Notes/AC 5 ("Given any outcome ... exactly one audit row is written"). 502 (Bad Gateway) is used because the failure originates upstream, not in the harness itself.

5. **A `DuplicateCheckError` (SQLite failure during the duplicate lookup) is *not* logged before re-raising as a 500.** Unlike the OpenRouter case, the failure here is the audit database itself being unreachable/broken — attempting `log_query` (which also hits SQLite) would either mask the real error with a second exception or silently no-op. `audit_logger.py` itself has no try/except around `insert_audit_log` (STORY-006 precedent: DB errors are trusted to bubble up, not swallowed), so this router does the same: let it propagate as an unhandled 500 rather than inventing error-recovery machinery for a scenario ("the audit DB is down") no story asks it to handle gracefully.

6. **No new dependency-injection/session machinery.** The PRD's Section 6 "suggested" architecture mentions `Depends` for DB sessions, but every existing service (`duplicate_checker`, `audit_logger`, `database.py`) already manages its own `sqlite3.Connection` internally per call (STORY-002 precedent: `get_connection()` opens/closes per call, no shared session). Introducing FastAPI `Depends`-based DB session injection here would touch every service module for no behavioral gain — this router simply calls the plain functions as-is, keeping the change scoped to `app/routers/` + `app/main.py`.

---

## Patterns to Follow

### Service composition (thin handler, plain function calls, no classes)
```python
// SOURCE: app/services/duplicate_checker.py:26-37, app/services/pattern_detector.py:21-26
def check_duplicate(prompt: str) -> DuplicateCheckResult: ...
def detect_suspicious_pattern(prompt: str) -> PatternDetectionResult: ...
```
The router imports and calls these directly — no wrapper classes, no repository objects, matching every other module in `app/services/`.

### Typed exception → HTTP mapping
```python
// SOURCE: app/services/openrouter_client.py:13-14, app/services/duplicate_checker.py:12-13
class OpenRouterError(Exception): pass
class DuplicateCheckError(Exception): pass
```
The router `except`-catches these two specific types and converts to the appropriate HTTP response; it never catches bare `Exception`.

### Env-var bootstrap + TestClient + temp_db (tests)
```python
// SOURCE: tests/test_main.py:1-10
import os
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
```
```python
// SOURCE: tests/test_duplicate_checker.py:39-44
@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path
```
`tests/test_query_router.py` combines both plus `monkeypatch.setattr("app.routers.query.call_openrouter", fake)` (same monkeypatch-only convention as `tests/test_openrouter_client.py`).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/routers/__init__.py` | CREATE | Marks `app/routers/` as a package |
| `app/routers/query.py` | CREATE | `POST /query` — composes duplicate/pattern/openrouter/audit services in PRD Section 6 order |
| `app/main.py` | UPDATE | Register `query.router` via `include_router`, update the placeholder comment |
| `tests/test_query_router.py` | CREATE | End-to-end pipeline tests via `TestClient` + `temp_db` + monkeypatched `call_openrouter` |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create `app/routers/__init__.py`

- **File**: `app/routers/__init__.py`
- **Action**: CREATE
- **Implement**: Empty file — marks `app/routers/` as a package.
- **Mirror**: `app/db/__init__.py`, `app/services/__init__.py` (empty-package-marker convention).
- **Validate**: `python -c "import app.routers"` succeeds.

### Task 2: Create `app/routers/query.py`

- **File**: `app/routers/query.py`
- **Action**: CREATE
- **Implement**:
  ```python
  from fastapi import APIRouter, HTTPException

  from app.models.schemas import (
      QueryBlockedDuplicateResponse,
      QueryBlockedSuspiciousResponse,
      QueryRequest,
      QueryResponse,
      QuerySuccessResponse,
  )
  from app.services.audit_logger import log_query
  from app.services.duplicate_checker import DuplicateCheckError, check_duplicate
  from app.services.openrouter_client import OpenRouterError, call_openrouter
  from app.services.pattern_detector import detect_suspicious_pattern

  router = APIRouter()


  @router.post("/query", response_model=QueryResponse)
  def query(request: QueryRequest) -> QueryResponse:
      if not request.user_id.strip():
          raise HTTPException(status_code=400, detail="user_id is required")

      try:
          duplicate_result = check_duplicate(request.prompt)
      except DuplicateCheckError as exc:
          raise HTTPException(status_code=500, detail=str(exc)) from exc

      if duplicate_result.is_duplicate:
          log_query(
              user_id=request.user_id,
              prompt=request.prompt,
              device=request.device,
              was_duplicate_blocked=True,
              success=True,
          )
          return QueryBlockedDuplicateResponse(
              reason="Duplicate query within 24 hours",
              first_query_at=duplicate_result.first_query_at,
          )

      pattern_result = detect_suspicious_pattern(request.prompt)
      if pattern_result.is_suspicious:
          log_query(
              user_id=request.user_id,
              prompt=request.prompt,
              device=request.device,
              suspicious_pattern=pattern_result.pattern,
              success=True,
          )
          return QueryBlockedSuspiciousResponse(
              reason="Suspicious pattern detected",
              pattern=pattern_result.pattern,
          )

      try:
          openrouter_result = call_openrouter(
              request.prompt,
              model=request.model,
              api_key=request.openrouter_api_key,
          )
      except OpenRouterError as exc:
          log_query(
              user_id=request.user_id,
              prompt=request.prompt,
              device=request.device,
              model_used=request.model,
              success=False,
              error_message=str(exc),
          )
          raise HTTPException(status_code=502, detail=str(exc)) from exc

      audit_id = log_query(
          user_id=request.user_id,
          prompt=request.prompt,
          device=request.device,
          response=openrouter_result.response,
          model_used=openrouter_result.model_used,
          tokens_used=openrouter_result.tokens_used,
          success=True,
      )

      return QuerySuccessResponse(
          response=openrouter_result.response,
          audit_id=audit_id,
          model_used=openrouter_result.model_used,
          tokens_used=openrouter_result.tokens_used,
      )
  ```
- **Mirror**: `app/services/duplicate_checker.py:12-13` (typed-exception convention); `app/models/schemas.py:6-36` (exact response field names). Order follows PRD Section 6 verbatim: user_id check → duplicate check → pattern check → OpenRouter → log → respond.
- **Validate**: `python -c "from app.routers.query import router"` succeeds.

### Task 3: Wire the router into `app/main.py`

- **File**: `app/main.py`
- **Action**: UPDATE
- **Implement**: Add `from app.routers import query as query_router` and `app.include_router(query_router.router)`; update the comment block so the `query` line no longer reads as a pending placeholder:
  ```python
  from contextlib import asynccontextmanager

  from fastapi import FastAPI

  from app.db.database import init_db
  from app.routers import query as query_router


  @asynccontextmanager
  async def lifespan(app: FastAPI):
      init_db()
      yield


  app = FastAPI(title="Harness IA", lifespan=lifespan)

  app.include_router(query_router.router)

  # Remaining routers registered by later stories:
  #   - app.routers.admin   (GET /audit, GET /stats) -> STORY-010, STORY-011


  @app.get("/health")
  def health() -> dict:
      return {"status": "ok"}
  ```
- **Mirror**: existing `app/main.py:1-23` structure — only the import/registration/comment lines change.
- **Validate**: `cd`-independent — `python -c "from app.main import app; print([r.path for r in app.routes])"` includes `/query`.

### Task 4: Create `tests/test_query_router.py`

- **File**: `tests/test_query_router.py`
- **Action**: CREATE
- **Implement**: Env-var bootstrap (mirror `tests/test_main.py:1-4`), `temp_db` fixture (mirror `tests/test_duplicate_checker.py:39-44`), `TestClient(app)`, and a `_fake_openrouter(response="...", model="gpt-4", tokens=10)` helper installed via `monkeypatch.setattr("app.routers.query.call_openrouter", ...)`. A `_count_audit_rows()` helper using `app.db.database.get_connection()` (`SELECT COUNT(*) FROM audit_logs`) to assert exactly-one-row-per-request. Tests:
  1. `test_missing_user_id_returns_422` — POST body omitting `user_id` entirely → `response.status_code == 422`; assert `_count_audit_rows() == 0` (AC 1).
  2. `test_empty_user_id_returns_400_before_any_side_effect` — POST with `user_id="   "`; monkeypatch `call_openrouter` to raise `AssertionError` if called → `response.status_code == 400`; assert `_count_audit_rows() == 0` (AC 1, no hashing/forwarding/logging occurred).
  3. `test_clean_prompt_success_returns_expected_shape_and_logs_row` — monkeypatch `call_openrouter` to return a fixed `OpenRouterResult`; POST a novel prompt → `response.json()` matches `{"status": "SUCCESS", "response": ..., "audit_id": ..., "model_used": ..., "tokens_used": ...}` exactly (5 keys); `_count_audit_rows() == 1` (AC 2).
  4. `test_duplicate_prompt_blocked_before_openrouter_call` — seed one row via `insert_audit_log`/`AuditLog` (mirror `tests/test_duplicate_checker.py:27-36`) with the same prompt hash, 2h old; monkeypatch `call_openrouter` to raise `AssertionError` if called; POST the identical prompt → `response.json() == {"status": "BLOCKED", "reason": "Duplicate query within 24 hours", "first_query_at": <seeded timestamp>}`; row count increases by exactly 1 (AC 3).
  5. `test_suspicious_pattern_blocked_before_openrouter_call` — prompt containing `"override"`; monkeypatch `call_openrouter` to raise `AssertionError` if called; POST → `response.json() == {"status": "BLOCKED", "reason": "Suspicious pattern detected", "pattern": "override"}`; row count increases by exactly 1 (AC 4).
  6. `test_openrouter_failure_logged_with_error_and_returns_502` — monkeypatch `call_openrouter` to raise `OpenRouterError("boom")`; POST a clean prompt → `response.status_code == 502`; row count increases by exactly 1; fetch the new row via `get_audit_log` and assert `success is False` and `error_message == "boom"` (AC 5).
  7. `test_full_pipeline_latency_within_budget` — with `call_openrouter` monkeypatched to return instantly, time a full successful POST with `time.perf_counter()`; assert elapsed `< 0.5` seconds (AC 6 — measures harness-added overhead only, since the fake stub has no network latency of its own).
- **Mirror**: `tests/test_duplicate_checker.py:27-51` (seeding + `temp_db` fixture); `tests/test_openrouter_client.py:1-13` (env bootstrap + monkeypatch-only convention).
- **Validate**: `pytest tests/test_query_router.py -v` — all 7 tests pass.

---

## End-to-End Tests

- [ ] POST `/query` missing `user_id` → 422, zero audit rows written (AC 1)
- [ ] POST `/query` with a novel, clean prompt → pipeline runs hash → duplicate check → pattern check → OpenRouter → log → respond in order; returns the `SUCCESS` shape from PRD Section 10 (AC 2)
- [ ] POST `/query` twice with the identical prompt within 24h → second call never reaches the (monkeypatched) OpenRouter call and returns the `BLOCKED` duplicate shape (AC 3)
- [ ] POST `/query` with a prompt containing a listed suspicious pattern → OpenRouter never called, returns the `BLOCKED` suspicious shape (AC 4)
- [ ] Every outcome (success, both blocks, OpenRouter failure) writes exactly one audit row (AC 5)
- [ ] Full pipeline with a stubbed OpenRouter call completes in well under 500ms, confirming harness-added overhead (excluding real upstream latency) is within budget (AC 6)
- [ ] `pytest tests/ -v` (full existing suite + new file) passes green

---

## Validation

```bash
pytest tests/test_query_router.py -v
pytest tests/ -v
python -c "from app.main import app; print([r.path for r in app.routes])"
```

---

## Acceptance Criteria

(Copied from story STORY-008)

- [ ] Given a request missing `user_id`, when posted to `/query`, then it is rejected before any hashing/forwarding occurs (RF-14).
- [ ] Given a novel, clean prompt, when posted to `/query`, then the pipeline runs in order — hash → duplicate check → pattern check → OpenRouter call → log → respond — and returns the `SUCCESS` shape from PRD Section 10, matching the happy-path flow in PRD Section 5.1.
- [ ] Given a prompt identical to one submitted within the last 24h, when posted to `/query`, then OpenRouter is never called and the `BLOCKED` duplicate shape is returned (PRD Section 5.2).
- [ ] Given a prompt containing a suspicious pattern, when posted to `/query`, then OpenRouter is never called and the `BLOCKED` suspicious-pattern shape is returned (PRD Section 5.3).
- [ ] Given any outcome (success or blocked), when the request completes, then exactly one audit row is written via the audit logging service.
- [ ] Given the full pipeline runs end-to-end, when measured, then total added latency (excluding the upstream model call itself) stays within the <500ms NFR budget.
- [ ] All tasks completed
- [ ] Frontend lint passes — N/A, no frontend in this MVP; substitute `pytest tests/ -v` passes
- [ ] Backend server starts without error
- [ ] Follows existing patterns (thin handler, function-based services, typed-exception-to-HTTP mapping, monkeypatch-only tests)
