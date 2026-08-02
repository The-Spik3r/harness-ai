---
story: STORY-001
prd: PRD-003
plan: .agents/plans/PRD-003-pii-redaction/completed/STORY-001-pii-redactor-service.plan.md
epic_branch: epic/PRD-003-pii-redaction
commit: 0495068
status: COMPLETE
completed: 2026-07-25
---

# Implementation Report — STORY-001: Presidio PII redactor service

**Plan**: `.agents/plans/PRD-003-pii-redaction/completed/STORY-001-pii-redactor-service.plan.md`
**Epic Branch**: `epic/PRD-003-pii-redaction`
**Commit**: `0495068`

## Summary

Added `app/services/pii_redactor.py`, a Presidio adapter exposing `redact(text: str) -> tuple[str, list[str]]`. The `AnalyzerEngine`/`AnonymizerEngine` are built lazily on first call and cached in module-level globals (`_analyzer`, `_anonymizer`) — this is the first lazy-singleton pattern in the codebase, matching this repo's plain-function/module-constant style rather than a class. Four new settings (`PII_REDACTION_ENABLED`, `PII_SCORE_THRESHOLD`, `PII_ENTITIES`, `PII_NLP_MODEL`) were added to `app/config.py`. `PII_ENTITIES` is kept as a raw `str` with a derived `pii_entities_list` property, deliberately avoiding a `List[str]`-typed `Settings` field, since `pydantic-settings` auto-JSON-decodes complex env types and a plain comma string is not valid JSON. No pipeline wiring — `app/main.py` and `app/routers/query.py` are untouched, as scoped.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add PII settings to `Settings` | `app/config.py` | ✅ |
| 2 | Add Presidio/spaCy dependencies | `requirements.txt` | ✅ |
| 3 | Create the Presidio adapter module | `app/services/pii_redactor.py` | ✅ |
| 4 | Unit tests for all 5 acceptance criteria | `tests/test_pii_redactor.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`python -c "from app.main import app"`) | ✅ |
| New tests (`pytest tests/test_pii_redactor.py`) | ✅ 6 passed |
| Full test suite (`pytest`) | ✅ 115 passed, 0 failed, no regressions |
| E2E checklist | ✅ 4/4 |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/config.py` | UPDATE | +9 |
| `requirements.txt` | UPDATE | +3 |
| `app/services/pii_redactor.py` | CREATE | +65 |
| `tests/test_pii_redactor.py` | CREATE | +76 |

## Deviations from Plan

None — implementation matches the plan exactly, including the `PII_ENTITIES`-as-`str` design decision and the `en_core_web_sm` test-model substitution.

One environment note not in the plan: this session used `.venv` (the project's existing virtualenv) for installs/validation rather than a bare global interpreter — no plan change, just the concrete install path.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_pii_redactor.py` | `test_redacts_default_entity_pii_and_reports_entity_type`, `test_text_without_pii_is_returned_unchanged`, `test_analyzer_engine_constructed_only_once`, `test_pii_entities_env_var_restricts_checked_types`, `test_score_threshold_filters_low_confidence_matches`, `test_pii_nlp_model_setting_is_used_to_build_engine` |

## Acceptance Criteria

- [x] Given a text containing default-entity PII (e.g. `"my email is a@b.com"`), when `redact(text)` is called, then it returns `(redacted_text, entities_found)` with the email masked (e.g. `<EMAIL_ADDRESS>`) and `entities_found` containing `"EMAIL_ADDRESS"`.
- [x] Given text with no detectable PII, when `redact(text)` is called, then the original text is returned unchanged and `entities_found` is an empty list.
- [x] Given the module is imported and `redact()` called multiple times, when inspected, then the `AnalyzerEngine`/NLP model is constructed only once (module-level singleton), not per call.
- [x] Given `PII_ENTITIES` and `PII_SCORE_THRESHOLD` env vars are set, when `redact(text)` runs, then only the configured entity types are checked and matches below the threshold are not masked.
- [x] Given `PII_NLP_MODEL` is set, when the analyzer initializes, then it loads that spaCy model name instead of a hardcoded default.
