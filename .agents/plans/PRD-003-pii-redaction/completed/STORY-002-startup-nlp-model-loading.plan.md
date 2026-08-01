---
story: STORY-002
prd: PRD-003
slug: startup-nlp-model-loading
title: Load Presidio NLP model once at FastAPI startup
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-003-pii-redaction        # all stories commit here, no per-story branch
created: 2026-07-26
---

# Plan: Load Presidio NLP model once at FastAPI startup

## Summary

`app/services/pii_redactor.py` ([[STORY-001]]) already builds and caches the Presidio `AnalyzerEngine`/NLP model as module-level singletons, but only lazily — the first real caller triggers the build. Today that first caller would be the first `/query` request, which is the exact cold-start latency the PRD explicitly rules out (PRD Section 6, RF-4; Section 14 Risk 2). This story closes that gap by adding one new public function, `pii_redactor.load()`, and calling it from `app/main.py`'s `lifespan` right alongside the existing `init_db()` call — mirroring the "singleton/startup-loaded resource" pattern the PRD names explicitly (PRD Section 6, Design patterns). `load()` is a thin, feature-flag-aware wrapper around the existing private `_get_analyzer()` getter: it force-builds the analyzer when `PII_REDACTION_ENABLED` is true, and no-ops when the flag is false, so a disabled deployment never pays the model-load cost and never touches Presidio at all. No route handler changes — this is exclusively a startup-sequencing change to two small, already-tested modules.

## User Story

As a devops engineer
I want the Presidio `AnalyzerEngine` (and its spaCy NLP model) force-loaded during the FastAPI `lifespan` startup hook
So that redaction doesn't add cold-start latency to the first `/query` request

## Story Reference

- Story file: `.agents/stories/PRD-003-pii-redaction/STORY-002-startup-nlp-model-loading.md`
- PRD: `.agents/PRDs/PRD-003-pii-redaction/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | `app/main.py`, `app/services/pii_redactor.py`, `tests/` |
| Story | STORY-002 |
| PRD | PRD-003 |
| Epic Branch | `epic/PRD-003-pii-redaction` (commit directly on this branch) |

---

## Skills In Use

None — `.agents/skills/` does not exist in this repository (confirmed via glob; PRD Appendix Section 15 states this explicitly, and [[STORY-001]]'s plan already documented the same finding).

---

## Patterns to Follow

### `lifespan` eager-init call (existing precedent to extend)
```python
// SOURCE: app/main.py:10-13
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
```
`init_db()` is called unconditionally, synchronously, before `yield` — no error handling, no flag check, since `init_db()` has no disable switch. The new `pii_redactor.load()` call follows the identical shape but adds its own internal flag check (see below), since `PII_REDACTION_ENABLED` has no analogue for `init_db()`.

### Lazy singleton getter (existing, to be reused not duplicated)
```python
// SOURCE: app/services/pii_redactor.py:29-33
def _get_analyzer() -> AnalyzerEngine:
    global _analyzer
    if _analyzer is None:
        _analyzer = _build_analyzer()
    return _analyzer
```
`_get_analyzer()` is already idempotent and side-effect-free to call twice — [[STORY-001]]'s plan called this out as intentionally covering STORY-002's future need. `load()` calls this existing getter directly; it does not duplicate the build logic.

### Feature-flag short-circuit (existing, in `redact()`)
```python
// SOURCE: app/services/pii_redactor.py:43-45
def redact(text: str) -> Tuple[str, List[str]]:
    if not settings.PII_REDACTION_ENABLED or not text:
        return text, []
```
`load()` mirrors this same `PII_REDACTION_ENABLED` check so a disabled deployment never constructs the analyzer at startup either — consistent, single source of truth for "is redaction on" across both the request path and the startup path.

### Tests (env bootstrap, monkeypatch on the settings singleton + module globals, small model)
```python
// SOURCE: tests/test_pii_redactor.py:1-18
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

from app.config import settings
import app.services.pii_redactor as pii_redactor
from app.services.pii_redactor import redact


@pytest.fixture(autouse=True)
def _small_model_and_reset(monkeypatch):
    monkeypatch.setattr(settings, "PII_NLP_MODEL", "en_core_web_sm")
    monkeypatch.setattr(pii_redactor, "_analyzer", None)
    monkeypatch.setattr(pii_redactor, "_anonymizer", None)
    yield
```
Required settings are pre-set via `os.environ.setdefault` before any `app.*` import; per-test overrides use `monkeypatch.setattr(settings, "ATTR", value)` on the singleton, never re-instantiation. Tests force `PII_NLP_MODEL` to the small `en_core_web_sm` model to keep load time reasonable, exactly as [[STORY-001]]'s tests already do.

### `TestClient` lifespan triggering (existing precedent, confirmed by inspection)
```python
// SOURCE: tests/test_main.py:6-10
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
```
Every existing test file instantiates `TestClient(app)` **without** the `with` context-manager form, which — verified against the installed `starlette==1.3.1` `TestClient.__init__`/`_portal_factory` — means `lifespan` startup/shutdown never actually runs for any existing test (this is why `tests/test_db.py` and `tests/test_integration.py` call `init_db()` manually via a fixture instead of relying on app startup). This story's new lifespan behavior is therefore invisible to the existing suite by default; new tests must explicitly use `with TestClient(app) as test_client:` to exercise `lifespan` at all.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/pii_redactor.py` | UPDATE | Add public `load()` function: force-builds the analyzer singleton when `PII_REDACTION_ENABLED`, no-ops otherwise |
| `app/main.py` | UPDATE | Call `pii_redactor.load()` in `lifespan`, alongside `init_db()` |
| `tests/test_pii_redactor.py` | UPDATE | Add unit tests for `load()`'s two behaviors (builds when enabled, no-op when disabled) |
| `tests/test_main.py` | UPDATE | Add tests proving `lifespan` builds the analyzer before the first request, only once, and skips it cleanly when redaction is disabled |

Route handlers (`app/routers/query.py`, `app/routers/admin.py`) are explicitly **not** touched — story Technical Notes line 39 confirms this story only changes `app/main.py` (plus the one small addition to `pii_redactor.py` needed to expose an explicit, non-private entry point, since the story's Technical Notes require calling "an explicit `pii_redactor.load()` / `get_analyzer()` function ... not by relying on import order alone").

---

## Design Notes (decisions worth stating up front)

1. **Why a new `load()` function instead of calling `_get_analyzer()` directly from `main.py`.** `_get_analyzer()` is underscore-prefixed (private to `pii_redactor.py`), and the story's Technical Notes explicitly call for "an explicit `pii_redactor.load()` / `get_analyzer()` function exposed by [[STORY-001]]" — i.e., a public entry point is a requirement, not a style preference. `load()` is the minimal public surface: it does not expose the analyzer object itself (nothing outside `pii_redactor.py` needs it — `redact()` remains the only public API for actually using it), it just triggers construction and adds the `PII_REDACTION_ENABLED` gate that `main.py` should not have to know about.

2. **`load()` only forces the analyzer, not the anonymizer.** `AnonymizerEngine()` (see `pii_redactor.py:36-40`) has no NLP model to load — it's a cheap, non-I/O constructor — so eagerly building it at startup provides no latency benefit and isn't what PRD Section 14 Risk 2 or the story ACs are concerned with ("NLP model loading", specifically). `_get_anonymizer()` stays lazily built on first real `redact()` call, unchanged.

3. **`load()` is silent and side-effect-only — no return value, no logging.** Matches this repo's existing service-module style (no logging calls in service modules, confirmed in [[STORY-001]]'s plan Design Notes). If the analyzer fails to build, `_build_analyzer()`'s existing `PiiRedactorError` propagates unchanged out of `load()` — a startup failure should fail loud (crash startup) rather than silently continue into a broken redaction state, consistent with `init_db()`'s unhandled-exception-propagates-and-crashes-startup behavior directly above it in `lifespan`.

4. **AC3 ("safe to skip or lazily defer... no request-path errors") is satisfied by the existing `PII_REDACTION_ENABLED` check inside `redact()`, not by anything new.** `load()` simply chooses not to build the analyzer when the flag is false; if a caller later flips the flag at runtime without restarting (not a supported scenario in this codebase — `settings` is a module-level singleton, not hot-reloaded) the first `redact()` call would lazily build then, exactly as it does today. No new error-handling path is needed on the request side.

5. **Test verification strategy for "no loading occurs on the request path" (AC2).** Directly asserting an absence of a specific call during a request requires instrumenting `_build_analyzer` with a call counter (mirroring the existing `test_analyzer_engine_constructed_only_once` pattern in `tests/test_pii_redactor.py`) and asserting the counter is still `1` after both entering the `TestClient` context (which runs `lifespan`) and issuing a request. This is more precise than merely checking `pii_redactor._analyzer is not None`, since a bug that rebuilds the analyzer per-request would still leave it non-`None` afterward but would fail a call-count assertion.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add `load()` to the Presidio adapter module

- **File**: `app/services/pii_redactor.py`
- **Action**: UPDATE
- **Implement**: Add a new public function after `_get_anonymizer()` (currently ending at line 40) and before `redact()`:
  ```python
  def load() -> None:
      if not settings.PII_REDACTION_ENABLED:
          return
      _get_analyzer()
  ```
  No new imports needed — reuses `settings` and `_get_analyzer()`, both already present in this module.
- **Mirror**: `app/services/pii_redactor.py:43-45` — the same `PII_REDACTION_ENABLED` gate style used in `redact()`.
- **Validate**: `cd f:\AI\harness-ai && python -c "from app.services import pii_redactor; pii_redactor.load(); print(pii_redactor._analyzer is not None)"` (requires `en_core_web_lg` or `en_core_web_sm` installed locally) prints `True`.

### Task 2: Call `load()` from FastAPI `lifespan`

- **File**: `app/main.py`
- **Action**: UPDATE
- **Implement**: Import `pii_redactor` and call `pii_redactor.load()` in `lifespan`, after `init_db()`:
  ```python
  from contextlib import asynccontextmanager

  from fastapi import FastAPI

  from app.db.database import init_db
  from app.routers import admin as admin_router
  from app.routers import query as query_router
  from app.services import pii_redactor


  @asynccontextmanager
  async def lifespan(app: FastAPI):
      init_db()
      pii_redactor.load()
      yield
  ```
  Route registration (`app.include_router(...)`) and the `/health` endpoint below are untouched.
- **Mirror**: `app/main.py:10-13` — same unconditional, synchronous, pre-`yield` call style as the existing `init_db()` line.
- **Validate**: `cd f:\AI\harness-ai && python -c "from app.main import app; print(app.title)"` still imports cleanly (import-order smoke check); full lifespan behavior is validated by Task 4's tests.

### Task 3: Unit tests for `pii_redactor.load()`

- **File**: `tests/test_pii_redactor.py`
- **Action**: UPDATE
- **Implement**: Add two tests after the existing `test_pii_nlp_model_setting_is_used_to_build_engine` test, using the same file's existing `_small_model_and_reset` autouse fixture:
  ```python
  def test_load_constructs_analyzer_singleton_when_enabled():
      assert pii_redactor._analyzer is None

      pii_redactor.load()

      assert pii_redactor._analyzer is not None


  def test_load_is_noop_when_redaction_disabled(monkeypatch):
      monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)

      pii_redactor.load()

      assert pii_redactor._analyzer is None
  ```
- **Mirror**: `tests/test_pii_redactor.py:38-51` (`test_analyzer_engine_constructed_only_once`) — same monkeypatch-and-assert-on-module-global shape.
- **Validate**: `cd f:\AI\harness-ai && python -m pytest tests/test_pii_redactor.py -v`

### Task 4: `lifespan` startup tests in `test_main.py`

- **File**: `tests/test_main.py`
- **Action**: UPDATE
- **Implement**: Add imports, a reset fixture (module-local, not autouse — the existing `test_health_returns_ok` test must keep working unmodified with no `lifespan` side effects), and three new tests:
  ```python
  import os

  os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
  os.environ.setdefault("ADMIN_TOKEN", "test-token")

  import pytest
  from fastapi.testclient import TestClient

  from app.config import settings
  from app.main import app
  import app.services.pii_redactor as pii_redactor

  client = TestClient(app)


  def test_health_returns_ok():
      response = client.get("/health")
      assert response.status_code == 200
      assert response.json() == {"status": "ok"}


  @pytest.fixture
  def _small_model_and_reset(monkeypatch):
      monkeypatch.setattr(settings, "PII_NLP_MODEL", "en_core_web_sm")
      monkeypatch.setattr(pii_redactor, "_analyzer", None)
      monkeypatch.setattr(pii_redactor, "_anonymizer", None)
      yield


  def test_lifespan_loads_pii_analyzer_before_serving_requests(_small_model_and_reset):
      with TestClient(app) as test_client:
          assert pii_redactor._analyzer is not None
          response = test_client.get("/health")
          assert response.status_code == 200


  def test_lifespan_does_not_reload_analyzer_on_first_request(_small_model_and_reset, monkeypatch):
      build_calls = []
      original_build = pii_redactor._build_analyzer

      def _counting_build():
          build_calls.append(1)
          return original_build()

      monkeypatch.setattr(pii_redactor, "_build_analyzer", _counting_build)

      with TestClient(app) as test_client:
          assert len(build_calls) == 1
          test_client.get("/health")
          assert len(build_calls) == 1


  def test_lifespan_skips_analyzer_when_redaction_disabled(_small_model_and_reset, monkeypatch):
      monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)

      with TestClient(app) as test_client:
          assert pii_redactor._analyzer is None
          response = test_client.get("/health")
          assert response.status_code == 200
  ```
  The pre-existing `test_health_returns_ok` keeps using the module-level `client` (built without `with`, so `lifespan` never runs for it, exactly as today — zero behavior change for that test). The three new tests each open their own `with TestClient(app) as test_client:` block so `lifespan` actually executes.
- **Mirror**: `tests/test_pii_redactor.py:13-18` (fixture shape), Design Note 5 above (call-count assertion over presence-only assertion).
- **Validate**: `cd f:\AI\harness-ai && python -m pytest tests/test_main.py -v`

---

## End-to-End Tests

No HTTP request/response contract changes (no new routes, no schema changes), so no live-server manual E2E beyond the automated `TestClient`-based tests above. Checks for `/implement` to execute:

- [ ] `python -m pytest tests/test_pii_redactor.py -v` — all tests pass, including the two new `load()` tests
- [ ] `python -m pytest tests/test_main.py -v` — all tests pass, including the three new lifespan tests
- [ ] `python -m pytest` (full suite) — confirms this story didn't break any other test (in particular `tests/test_integration.py`, `tests/test_query_router.py`, `tests/test_db.py`, all of which build their own `TestClient(app)` without `with` and are therefore unaffected by the `lifespan` change)
- [ ] `cd f:\AI\harness-ai && uvicorn app.main:app --reload` then `curl http://localhost:8000/health` — server starts without error and the analyzer loads during startup (observable as a brief pause before "Application startup complete" in the terminal, then instant `/health` response)

---

## Validation

```bash
cd f:\AI\harness-ai
python -m pytest tests/test_pii_redactor.py tests/test_main.py -v
python -m pytest
uvicorn app.main:app --reload
curl http://localhost:8000/health
```

---

## Acceptance Criteria

(Copied from story STORY-002)

- [ ] Given the app starts, when `lifespan` runs, then the Presidio analyzer singleton from [[STORY-001]]'s `pii_redactor.py` is constructed before the app begins accepting requests (alongside the existing `init_db()` call).
- [ ] Given the app has already started, when the first `/query` request arrives, then no NLP model loading occurs on that request path — the singleton is already warm.
- [ ] Given `PII_REDACTION_ENABLED=false`, when the app starts, then the analyzer is still safe to skip or lazily defer (documented behavior), and no request-path errors occur from redaction being disabled.
- [ ] All tasks completed
- [ ] Full existing test suite (`python -m pytest`) still passes, unmodified
- [ ] Route handlers untouched — only `app/main.py` and `app/services/pii_redactor.py` change
- [ ] Follows existing patterns (unconditional pre-`yield` call in `lifespan`, module-level singleton getter reuse, no logging in service modules)
