---
story: STORY-002
prd: PRD-003
plan: .agents/plans/PRD-003-pii-redaction/completed/STORY-002-startup-nlp-model-loading.plan.md
epic_branch: epic/PRD-003-pii-redaction
commit: 358ddc6
status: COMPLETE
completed: 2026-07-31
---

# Implementation Report — STORY-002: Load Presidio NLP model once at FastAPI startup

**Plan**: `.agents/plans/PRD-003-pii-redaction/completed/STORY-002-startup-nlp-model-loading.plan.md`
**Epic Branch**: `epic/PRD-003-pii-redaction`
**Commit**: `358ddc6`

## Summary

Added a public `pii_redactor.load()` function that force-builds the Presidio `AnalyzerEngine` singleton via the existing `_get_analyzer()` getter, gated by `PII_REDACTION_ENABLED`. Wired it into `app/main.py`'s `lifespan`, called immediately after `init_db()` and before `yield`, so the spaCy NLP model loads once at process startup instead of on the first `/query` request. No route handlers were touched.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add `load()` to the Presidio adapter module | `app/services/pii_redactor.py` | ✅ |
| 2 | Call `load()` from FastAPI `lifespan` | `app/main.py` | ✅ |
| 3 | Unit tests for `pii_redactor.load()` | `tests/test_pii_redactor.py` | ✅ |
| 4 | `lifespan` startup tests in `test_main.py` | `tests/test_main.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`python -c "from app.main import app"`) | ✅ |
| `pytest tests/test_pii_redactor.py tests/test_main.py -v` | ✅ 12 passed |
| Full suite (`pytest`) | ✅ 120 passed |
| E2E: `uvicorn` startup + `curl /health` | ✅ 200 `{"status":"ok"}` |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/pii_redactor.py` | UPDATE | +6 |
| `app/main.py` | UPDATE | +2/-0 |
| `tests/test_pii_redactor.py` | UPDATE | +16 |
| `tests/test_main.py` | UPDATE | +38 (rewritten with new fixture + 3 tests, existing `test_health_returns_ok` unchanged) |

## Deviations from Plan

None. Implementation matched the plan exactly (Tasks 1–4), including the `load()` signature, its `PII_REDACTION_ENABLED` gate, the `lifespan` call site, and all six planned test cases (2 in `test_pii_redactor.py`, 3 new + 1 existing in `test_main.py`).

One incidental observation during E2E validation, not a deviation: the default `PII_NLP_MODEL=en_core_web_lg` is not pre-installed in the local `.venv` (only `en_core_web_sm`, used by the test suite, is present) — spaCy transparently pip-installed the ~400MB `en_core_web_lg` wheel on first real startup. This is expected/accepted per PRD Section 14 Risk 5 and out of scope for this story ([[STORY-011]] covers the Docker-image install step).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_pii_redactor.py` | `test_load_constructs_analyzer_singleton_when_enabled`, `test_load_is_noop_when_redaction_disabled` |
| `tests/test_main.py` | `test_lifespan_loads_pii_analyzer_before_serving_requests`, `test_lifespan_does_not_reload_analyzer_on_first_request`, `test_lifespan_skips_analyzer_when_redaction_disabled` |

## Acceptance Criteria

- [x] Given the app starts, when `lifespan` runs, then the Presidio analyzer singleton from STORY-001's `pii_redactor.py` is constructed before the app begins accepting requests (alongside the existing `init_db()` call).
- [x] Given the app has already started, when the first `/query` request arrives, then no NLP model loading occurs on that request path — the singleton is already warm.
- [x] Given `PII_REDACTION_ENABLED=false`, when the app starts, then the analyzer is still safe to skip or lazily defer (documented behavior), and no request-path errors occur from redaction being disabled.
