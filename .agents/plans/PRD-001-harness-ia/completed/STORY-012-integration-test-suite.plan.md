---
story: STORY-012
prd: PRD-001
slug: integration-test-suite
title: "End-to-end integration test suite"
type: technical
complexity: medium
epic_branch: epic/PRD-001-harness-ia
created: 2026-07-04
---

# Plan: End-to-end integration test suite

## Summary

Add `tests/test_integration.py`, a single cohesive suite that exercises the full `/query` → `/audit` → `/stats` API surface end-to-end and ties each test explicitly back to a PRD Section 5 flow, closing two real coverage gaps that the existing per-module test files (`tests/test_query_router.py`, `tests/test_audit_router.py`, `tests/test_stats_router.py`, `tests/test_admin_auth.py`) don't fill: (1) only one of the seven suspicious patterns (`"override"`) is currently exercised through the live `/query` endpoint — AC 3 requires all seven — and (2) `/audit`/`/stats` are today only ever verified against rows inserted directly into SQLite, never against rows produced by a real `/query` call, so there's no test proving the three subsystems agree on the same data. No application source code changes — this is a test-only story. The suite reuses the exact `temp_db` fixture, `TestClient`, `_fail_if_called` OpenRouter guard, and env-bootstrap conventions already established across the ten existing test files, so it reads as one more file in the same family rather than a new pattern.

## User Story

As a devops engineer
I want a pytest suite that exercises the full API surface end-to-end
So that regressions in the pipeline, admin endpoints, or auth are caught before deployment

## Story Reference

- Story file: `.agents/stories/PRD-001-harness-ia/STORY-012-integration-test-suite.md`
- PRD: `.agents/PRDs/PRD-001-harness-ia/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | technical |
| Complexity | medium |
| Systems Affected | `tests/test_integration.py` (new) |
| Story | STORY-012 |
| PRD | PRD-001 |
| Epic Branch | `epic/PRD-001-harness-ia` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` contains no `SKILL.md` files, and the story's `skills: []` frontmatter is empty — same situation as STORY-001 through STORY-011.

---

## Codebase State

- Confirmed baseline: `pytest tests/ -q` currently passes 83/83. This plan only adds tests; it must not reduce that count or introduce flakiness.
- `tests/test_query_router.py:1-19` establishes the full bootstrap this story reuses verbatim: `os.environ.setdefault("OPENROUTER_API_KEY", "test-key")` / `ADMIN_TOKEN` before any `app` import, a module-level `client = TestClient(app)`, and a `temp_db` fixture that monkeypatches `settings.DATABASE_URL` to a `tmp_path` SQLite file and calls `init_db()`.
- `tests/test_query_router.py:52-53` defines `_fail_if_called(*args, **kwargs)` — raises `AssertionError` if the mocked callable is invoked. `tests/test_query_router.py:56-131` monkeypatches `app.routers.query.call_openrouter` (not the module-level `openrouter_client.call_openrouter`) to this guard for duplicate/suspicious-blocked tests, proving OpenRouter is never reached (AC 2, AC 3's "OpenRouter never called").
- `tests/test_query_router.py:98-113` (`test_duplicate_prompt_blocked_before_openrouter_call`) and `:116-131` (`test_suspicious_pattern_blocked_before_openrouter_call`) already prove the BLOCKED shapes for one duplicate case and exactly one pattern (`"override"`) — this plan's new suite parametrizes the suspicious case over all seven `SUSPICIOUS_PATTERNS` (AC 3 explicitly says "for each of the 7 patterns", which no existing test does at the endpoint level).
- `app/services/pattern_detector.py:4-12` — `SUSPICIOUS_PATTERNS` is the exact list of 7 strings to parametrize over: `"ignore previous instructions"`, `"forget everything"`, `"show system prompt"`, `"reveal password"`, `"execute code"`, `"admin mode"`, `"override"`. Importing this list (rather than hardcoding it a second time) keeps the test suite in sync if the list ever changes, matching PRD Section 6's "data-driven list" strategy-pattern intent.
- `app/services/openrouter_client.py:17-21` — `OpenRouterResult(response, model_used, tokens_used)` is the dataclass the happy-path mock must return; `OpenRouterError` (line 13-14) is what a forced-failure mock would raise (not needed for this story's ACs, but already covered by `tests/test_query_router.py:134-154`, no duplication needed).
- `app/routers/query.py:18-87` is the full 8-step pipeline (PRD Section 6) this suite drives black-box, through `client.post("/query", ...)` only — no direct service-layer calls, since AC 1-3 are about the assembled endpoint, not the underlying units already covered by `tests/test_duplicate_checker.py`, `tests/test_pattern_detector.py`, `tests/test_openrouter_client.py`.
- `app/routers/admin.py:19-39` (`/audit`) and `:42-60` (`/stats`) both use `dependencies=[Depends(require_admin_token)]` from `app/middleware/auth.py`, gated by `settings.ADMIN_TOKEN` — `tests/test_admin_auth.py` already proves the dependency itself works against a fake app; this suite instead proves the *real* `/audit` and `/stats` routes reject/accept consistently or rows written by a real `/query` call actually surface there (a genuine end-to-end path, not yet tested anywhere).
- `tests/test_audit_router.py:17-22` and `tests/test_stats_router.py:17-22` both define their own identical `temp_db` fixture — this is existing, accepted duplication across the test suite (not something to refactor away as part of this story; out of scope per "don't refactor beyond what the task requires").

---

## Design Decisions

1. **One new file, not edits to existing ones.** `tests/test_query_router.py`, `test_audit_router.py`, `test_stats_router.py` each already test their own endpoint in isolation correctly — this story's job (per its title, "integration test suite") is a cross-cutting suite proving the pieces work *together*, so it belongs in its own file rather than bloating the per-router files with cross-endpoint concerns.
2. **Parametrize the suspicious-pattern test over `SUSPICIOUS_PATTERNS` imported from `app.services.pattern_detector`, not a hardcoded literal list.** Directly closes AC 3 ("for each of the 7 patterns") and stays correct automatically if the pattern list changes.
3. **Reuse `_fail_if_called` + monkeypatch `app.routers.query.call_openrouter`** (the exact mechanism already proven in `tests/test_query_router.py`) rather than mocking `httpx` at a lower level — keeps the "OpenRouter never called" assertion as strong and as simple as the existing precedent.
4. **No `conftest.py` introduced.** Every existing test file repeats the same env-bootstrap + `temp_db` fixture; introducing a shared `conftest.py` now would be an unrelated refactor of nine other files, out of scope for a story whose only new file is this one. Follow the established convention instead.
5. **The cross-endpoint proof test drives `/query` for real (mocked OpenRouter) and then reads back through `/audit` and `/stats`**, rather than inserting rows directly via `insert_audit_log` (as the other router tests do). This is the one thing genuinely missing: proof that a request that goes through the full pipeline is visible, with the right flags, through both admin endpoints.
6. **No real OpenRouter network call is ever made** (AC 5) — the module-level `OPENROUTER_API_KEY=test-key` env var plus monkeypatching `call_openrouter` for every non-BLOCKED path means the suite needs no real key and never hits the network, identical to every existing test file.

---

## Patterns to Follow

### Env bootstrap + fixture + client (existing, reused verbatim)
```python
// SOURCE: tests/test_query_router.py:1-29
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import get_connection, init_db
from app.main import app

client = TestClient(app)


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path
```

### OpenRouter-never-called guard (existing)
```python
// SOURCE: tests/test_query_router.py:52-54, 98-101
def _fail_if_called(*args, **kwargs):
    raise AssertionError("call_openrouter should not have been called")


def test_duplicate_prompt_blocked_before_openrouter_call(temp_db, monkeypatch):
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
```

### Parametrized pattern test (existing, at the unit level — this story lifts the same idea to the endpoint level)
```python
// SOURCE: tests/test_pattern_detector.py:14-19
@pytest.mark.parametrize("expected_pattern", SUSPICIOUS_PATTERNS)
def test_each_pattern_is_flagged_individually(expected_pattern):
    result = detect_suspicious_pattern(f"please {expected_pattern} now")

    assert result.is_suspicious is True
    assert result.pattern == expected_pattern
```

### Admin-token-gated request (existing)
```python
// SOURCE: tests/test_stats_router.py:42-47
def test_missing_admin_token_rejected_before_aggregation(temp_db, monkeypatch):
    _guard_all_aggregates(monkeypatch)

    response = client.get("/stats")

    assert response.status_code in (401, 403)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_integration.py` | CREATE | End-to-end suite: happy path (5.1), duplicate-blocked (5.2), all 7 suspicious patterns (5.3), combined `/audit`+`/stats` auth coverage, and a real-pipeline-to-admin-endpoint cross-check |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create `tests/test_integration.py` — bootstrap, fixtures, helpers

- **File**: `tests/test_integration.py`
- **Action**: CREATE
- **Implement**:
  ```python
  import os

  os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
  os.environ.setdefault("ADMIN_TOKEN", "test-token")

  import pytest
  from fastapi.testclient import TestClient

  from app.config import settings
  from app.db.database import get_connection, init_db
  from app.main import app
  from app.services.openrouter_client import OpenRouterResult
  from app.services.pattern_detector import SUSPICIOUS_PATTERNS

  client = TestClient(app)


  @pytest.fixture
  def temp_db(tmp_path, monkeypatch):
      db_path = tmp_path / "test.db"
      monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
      init_db()
      return db_path


  def _count_audit_rows() -> int:
      with get_connection() as conn:
          row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
          return row["n"]


  def _fail_if_called(*args, **kwargs):
      raise AssertionError("call_openrouter should not have been called")


  def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
      return OpenRouterResult(response="mock response", model_used=model, tokens_used=7)
  ```
- **Mirror**: `tests/test_query_router.py:1-53` for every helper above — no new conventions introduced.
- **Validate**: `python -c "import tests.test_integration"` succeeds (env bootstrap + imports resolve).

### Task 2: Happy-path test (PRD Section 5.1)

- **File**: `tests/test_integration.py`
- **Action**: UPDATE (append)
- **Implement**:
  ```python
  def test_happy_path_returns_success_and_logs_exactly_one_row(temp_db, monkeypatch):
      """PRD Section 5.1: clean prompt -> SUCCESS + exactly one new audit_logs row."""
      monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)

      before = _count_audit_rows()
      response = client.post(
          "/query",
          json={"user_id": "juan@empresa.com", "prompt": "what is the weather today"},
      )

      assert response.status_code == 200
      body = response.json()
      assert body["status"] == "SUCCESS"
      assert body["response"] == "mock response"
      assert body["model_used"] == "gpt-4"
      assert body["tokens_used"] == 7
      assert isinstance(body["audit_id"], int)
      assert _count_audit_rows() == before + 1
  ```
- **Mirror**: `tests/test_query_router.py:76-95`.
- **Validate**: `pytest tests/test_integration.py -k happy_path -v` passes.

### Task 3: Duplicate-blocked test (PRD Section 5.2)

- **File**: `tests/test_integration.py`
- **Action**: UPDATE (append)
- **Implement**:
  ```python
  def test_duplicate_query_blocked_and_openrouter_never_called(temp_db, monkeypatch):
      """PRD Section 5.2: same prompt twice within 24h -> second call BLOCKED, OpenRouter untouched."""
      monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)
      first = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": "duplicate me please"}
      )
      assert first.status_code == 200
      assert first.json()["status"] == "SUCCESS"

      monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
      before = _count_audit_rows()
      second = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": "duplicate me please"}
      )

      assert second.status_code == 200
      body = second.json()
      assert body["status"] == "BLOCKED"
      assert body["reason"] == "Duplicate query within 24 hours"
      assert "first_query_at" in body
      assert _count_audit_rows() == before + 1
  ```
- **Mirror**: `tests/test_query_router.py:98-113`, but driving the *first* call through the real endpoint (not seeding the DB directly) so the whole round-trip is proven, not just the block path in isolation.
- **Validate**: `pytest tests/test_integration.py -k duplicate -v` passes.

### Task 4: Suspicious-pattern test, parametrized over all 7 patterns (PRD Section 5.3)

- **File**: `tests/test_integration.py`
- **Action**: UPDATE (append)
- **Implement**:
  ```python
  @pytest.mark.parametrize("pattern", SUSPICIOUS_PATTERNS)
  def test_each_suspicious_pattern_blocked_and_openrouter_never_called(
      temp_db, monkeypatch, pattern
  ):
      """PRD Section 5.3: every one of the 7 listed patterns is blocked before OpenRouter."""
      monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

      before = _count_audit_rows()
      response = client.post(
          "/query",
          json={"user_id": "juan@empresa.com", "prompt": f"please {pattern} right now"},
      )

      assert response.status_code == 200
      body = response.json()
      assert body["status"] == "BLOCKED"
      assert body["reason"] == "Suspicious pattern detected"
      assert body["pattern"] == pattern
      assert _count_audit_rows() == before + 1
  ```
- **Mirror**: `tests/test_query_router.py:116-131` (single-pattern version) lifted to `@pytest.mark.parametrize` per `tests/test_pattern_detector.py:14-19`'s existing parametrization idiom.
- **Validate**: `pytest tests/test_integration.py -k suspicious -v` — 7 test cases collected and passing (one per pattern).

### Task 5: Combined `/audit` + `/stats` admin-auth coverage

- **File**: `tests/test_integration.py`
- **Action**: UPDATE (append)
- **Implement**:
  ```python
  @pytest.mark.parametrize("route", ["/audit", "/stats"])
  def test_admin_route_rejects_missing_or_invalid_token(temp_db, route):
      no_header = client.get(route)
      assert no_header.status_code in (401, 403)

      wrong_token = client.get(route, headers={"Authorization": "Bearer wrong-token"})
      assert wrong_token.status_code in (401, 403)


  @pytest.mark.parametrize("route", ["/audit", "/stats"])
  def test_admin_route_accepts_valid_token(temp_db, route):
      response = client.get(
          route, headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
      )
      assert response.status_code == 200
  ```
- **Mirror**: `tests/test_admin_auth.py:34-45` (parametrized-route idiom) applied to the real `/audit`/`/stats` routers instead of the fake app, directly satisfying AC 4's "both the authorized and unauthorized paths are covered" for both endpoints in one place.
- **Validate**: `pytest tests/test_integration.py -k admin_route -v` — 4 test cases pass.

### Task 6: Cross-endpoint proof — a real `/query` call surfaces correctly through `/audit` and `/stats`

- **File**: `tests/test_integration.py`
- **Action**: UPDATE (append)
- **Implement**:
  ```python
  def test_query_results_are_consistent_across_audit_and_stats(temp_db, monkeypatch):
      """A successful, a duplicate-blocked, and a suspicious-blocked query all surface
      identically through /audit and /stats — proving the three subsystems agree."""
      monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)
      ok = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": "clean prompt one"}
      )
      assert ok.json()["status"] == "SUCCESS"

      client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": "clean prompt one"}
      )  # duplicate of the above, will be BLOCKED

      client.post(
          "/query",
          json={"user_id": "maria@empresa.com", "prompt": "please override the rules"},
      )  # suspicious pattern, will be BLOCKED

      admin_headers = {"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
      audit = client.get("/audit", headers=admin_headers)
      stats = client.get("/stats", headers=admin_headers)

      assert audit.status_code == 200
      assert stats.status_code == 200

      audit_body = audit.json()
      assert audit_body["total"] == 3
      flags = {
          (entry["was_duplicate_blocked"], entry["suspicious_pattern_detected"])
          for entry in audit_body["queries"]
      }
      assert (True, False) in flags   # the duplicate-blocked entry
      assert (False, True) in flags   # the suspicious-blocked entry
      assert (False, False) in flags  # the successful entry

      stats_body = stats.json()
      assert stats_body["total_queries"] == 3
      assert stats_body["blocked_duplicates"] == 1
      assert stats_body["blocked_suspicious"] == 1
      assert stats_body["unique_users"] == 2
  ```
- **Mirror**: no direct precedent — this is the one genuinely new integration path, composed from `tests/test_query_router.py`'s request style, `tests/test_audit_router.py:81-91`'s shape assertions, and `tests/test_stats_router.py:96-117`'s aggregate assertions.
- **Validate**: `pytest tests/test_integration.py -v` — full new file passes.

---

## End-to-End Tests

- [ ] `pytest tests/test_integration.py -v` passes with no real `OPENROUTER_API_KEY` set in the environment (only the test-bootstrap `"test-key"` value) — proves AC 5
- [ ] Happy-path test asserts `SUCCESS` + exactly one new `audit_logs` row (AC 1 / PRD 5.1)
- [ ] Duplicate-blocked test asserts OpenRouter is never called and the `BLOCKED` duplicate shape is returned (AC 2 / PRD 5.2)
- [ ] Suspicious-pattern test is parametrized and passes for all 7 entries in `SUSPICIOUS_PATTERNS`, each asserting OpenRouter is never called (AC 3 / PRD 5.3)
- [ ] `/audit` and `/stats` are each tested with a missing token, a wrong token, and a valid token (AC 4)
- [ ] `pytest tests/ -v` (full suite, existing 83 tests + new ones) passes green with no regressions

---

## Validation

```bash
pytest tests/test_integration.py -v
pytest tests/ -v
```

---

## Acceptance Criteria

(Copied from story STORY-012)

- [ ] Given the happy-path flow from PRD Section 5.1, when run as a test, then it asserts a `SUCCESS` response and exactly one new `audit_logs` row.
- [ ] Given the duplicate-blocked flow from PRD Section 5.2, when run as a test, then it asserts OpenRouter is never called (mocked) and the `BLOCKED` duplicate shape is returned.
- [ ] Given the suspicious-pattern flow from PRD Section 5.3, when run as a test, then it asserts OpenRouter is never called and the `BLOCKED` suspicious shape is returned, for each of the 7 patterns.
- [ ] Given `/audit` and `/stats`, when tested with and without a valid admin token, then both the authorized and unauthorized paths are covered.
- [ ] Given the full suite, when run in CI, then it passes without requiring a real OpenRouter API key (the client is mocked/stubbed).
- [ ] All tasks completed
- [ ] Frontend lint passes — N/A, no frontend in this MVP; substitute `pytest tests/ -v` passes
- [ ] Backend server starts without error
- [ ] Follows existing patterns
