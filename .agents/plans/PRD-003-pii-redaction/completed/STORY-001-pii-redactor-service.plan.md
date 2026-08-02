---
story: STORY-001
prd: PRD-003
slug: pii-redactor-service
title: Presidio PII redactor service
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-003-pii-redaction        # all stories commit here, no per-story branch
created: 2026-07-24
---

# Plan: Presidio PII redactor service

## Summary

Add a new, self-contained service module `app/services/pii_redactor.py` that wraps Presidio's `AnalyzerEngine` + `AnonymizerEngine` behind a single `redact(text: str) -> tuple[str, list[str]]` function. The Presidio NLP engine is built lazily on first call and cached in module-level globals (this codebase's first lazy-singleton — no existing precedent, so the getter/global pattern here becomes the template for later stories). Four new settings are added to `app/config.py` following the existing plain-attribute `Settings` style, with a small, isolated addition (a `str`-typed `PII_ENTITIES` field plus a derived list) to avoid fighting `pydantic-settings`' automatic JSON decoding of complex env-var types, which has no precedent in this repo. No other file changes — this story explicitly does not touch `main.py`, `query.py`, or any pipeline wiring (that's STORY-002/005/006).

## User Story

As a devops engineer
I want a single `pii_redactor.py` module that wraps Presidio's `AnalyzerEngine` and `AnonymizerEngine` behind a `redact(text)` function
So that the rest of the pipeline never imports Presidio directly and the NLP engine is a reusable, lazily-created singleton

## Story Reference

- Story file: `.agents/stories/PRD-003-pii-redaction/STORY-001-pii-redactor-service.md`
- PRD: `.agents/PRDs/PRD-003-pii-redaction/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/config.py`, `app/services/`, `requirements.txt`, `tests/` |
| Story | STORY-001 |
| PRD | PRD-003 |
| Epic Branch | `epic/PRD-003-pii-redaction` (commit directly on this branch) |

---

## Skills In Use

None — `.agents/skills/` does not exist in this repository (confirmed via glob; PRD Appendix Section 15 also states this explicitly).

---

## Patterns to Follow

### Settings (plain typed attributes, singleton export)
```python
// SOURCE: app/config.py:1-16
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    OPENROUTER_API_KEY: str
    ADMIN_TOKEN: str

    DATABASE_URL: str = "sqlite:///harness_ai.db"
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    LOG_LEVEL: str = "INFO"


settings = Settings()
```
No `Field(...)`, no validators anywhere today — bare `NAME: type = default`. `settings` is the module-level singleton every other module imports via `from app.config import settings`.

### Service module shape (custom exception + module constants + pure function)
```python
// SOURCE: app/services/duplicate_checker.py:1-23
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


def hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()
```
Import order: stdlib, blank line, third-party, blank line, `app.*` absolute imports. No module docstrings anywhere in this repo. One custom `Exception` subclass per module, wrapping lower-level errors with `raise NewError(f"...: {exc}") from exc` (see `app/services/openrouter_client.py:32-34,51-52,58-61`). No logging calls in service modules.

### Error wrapping around a third-party engine call
```python
// SOURCE: app/services/openrouter_client.py:47-61
    try:
        try:
            resp = http_client.post(_API_URL, headers=headers, json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise OpenRouterError(f"OpenRouter request failed: {exc}") from exc
        ...
    finally:
        if owns_client:
            http_client.close()
```

### Tests (env bootstrap, monkeypatch on the settings singleton, pytest.raises)
```python
// SOURCE: tests/test_duplicate_checker.py:1-4,39-44,115-117
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

...

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path

...

def test_malformed_db_raises_duplicate_check_error(uninitialized_db):
    with pytest.raises(DuplicateCheckError):
        check_duplicate("anything")
```
Required settings (`OPENROUTER_API_KEY`, `ADMIN_TOKEN`) are pre-set via `os.environ.setdefault` at the very top of the test file, before any `app.*` import — required because `Settings()` fails at import time otherwise. Per-test overrides use `monkeypatch.setattr(settings, "ATTR", value)` directly on the singleton instance, never by re-instantiating `Settings`.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/config.py` | UPDATE | Add `PII_REDACTION_ENABLED`, `PII_SCORE_THRESHOLD`, `PII_ENTITIES` (+ derived list), `PII_NLP_MODEL` settings |
| `requirements.txt` | UPDATE | Add `presidio-analyzer`, `presidio-anonymizer`, `spacy` |
| `app/services/pii_redactor.py` | CREATE | Presidio adapter: `redact(text)` + lazy singleton engine getters |
| `tests/test_pii_redactor.py` | CREATE | Unit tests covering all 5 acceptance criteria |

`app/main.py` and `app/routers/query.py` are explicitly **not** touched — story frontmatter confirms this is STORY-002 (startup loading) and STORY-005/006 (pipeline wiring) territory.

---

## Design Notes (decisions worth stating up front)

1. **`PII_ENTITIES` avoids `List[str]` on the `Settings` field.** `pydantic-settings` auto-JSON-decodes env values for complex-typed fields (lists, dicts) before any custom validator runs; a plain comma string like `PERSON,EMAIL_ADDRESS` is not valid JSON and would raise at `Settings()` construction. There's no existing precedent in this repo for parsing a delimited env string, and using `pydantic_settings.NoDecode` + a `field_validator` is unverified-fragile machinery to introduce with zero prior usage. Instead: keep `PII_ENTITIES: str` (the raw comma-separated value, exactly as the env var looks) and expose a `pii_entities_list` property on `Settings` that splits/strips it. `pii_redactor.py` reads `settings.pii_entities_list`. This satisfies the AC ("only the configured entity types are checked") without fighting the framework.

2. **Lazy singleton = two module-level globals + getters**, not a class. Matches this repo's "plain functions + module constants" style (no service in this repo is a class). `_analyzer: Optional[AnalyzerEngine]` and `_anonymizer: Optional[AnonymizerEngine]`, each built on first access by `_get_analyzer()` / `_get_anonymizer()`, called from `redact()`. This is intentionally the exact shape STORY-002 will need to call into for eager startup loading (a `force_load()`-style entry point isn't required by this story's ACs, but `_get_analyzer()` being idempotent and side-effect-free to call twice covers that need without extra API surface).

3. **`redact()` is fail-open by feature flag, fail-loud otherwise.** If `PII_REDACTION_ENABLED` is `False`, or the input text is empty, return `(text, [])` immediately without touching Presidio. If the engine fails to build (e.g. spaCy model not installed) or `analyze`/`anonymize` raises, wrap in a new `PiiRedactorError` and let it propagate — mirrors `DuplicateCheckError`/`OpenRouterError`. Whether the *pipeline* should swallow that error and fail open (send raw text) or fail closed (block the request) is explicitly a pipeline-wiring decision left to STORY-005/006, not this story — `redact()` itself must not silently swallow engine errors, since that would hide a misconfiguration.

4. **Test model choice**: the PRD/story default `PII_NLP_MODEL=en_core_web_lg` (~587MB) is correct for production but too slow to fetch for local test runs. Tests will monkeypatch `settings.PII_NLP_MODEL` to `en_core_web_sm` (~12MB) — this is safe because email/phone/credit-card detection in Presidio's built-in recognizers is regex-based (not NLP-model-dependent), so the AC's `EMAIL_ADDRESS` example is deterministic regardless of model size. `en_core_web_sm` must be downloaded once locally before running tests (see Validation).

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add PII settings to `Settings`

- **File**: `app/config.py`
- **Action**: UPDATE
- **Implement**: Add four attributes after `LOG_LEVEL` (app/config.py:13), plus a `pii_entities_list` property:
  ```python
  PII_REDACTION_ENABLED: bool = True
  PII_SCORE_THRESHOLD: float = 0.35
  PII_ENTITIES: str = "PERSON,EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE,LOCATION"
  PII_NLP_MODEL: str = "en_core_web_lg"

  @property
  def pii_entities_list(self) -> list[str]:
      return [item.strip() for item in self.PII_ENTITIES.split(",") if item.strip()]
  ```
  Defaults match PRD Section 9 exactly (`.agents/PRDs/PRD-003-pii-redaction/PRD.md:178-181`).
- **Mirror**: `app/config.py:7-13` — bare typed attributes, no `Field(...)`.
- **Validate**: `python -c "from app.config import settings; print(settings.pii_entities_list)"` prints the 7-entity default list.

### Task 2: Add Presidio/spaCy dependencies

- **File**: `requirements.txt`
- **Action**: UPDATE
- **Implement**: Append after `reflex==0.9.6.post1` (requirements.txt:9):
  ```
  presidio-analyzer
  presidio-anonymizer
  spacy
  ```
  Do not add `en_core_web_lg` as a pip requirement — it is not a normal PyPI package; per the story's Technical Notes it's installed separately via `python -m spacy download en_core_web_lg` (that install step is formalized in STORY-011's Docker work). For local dev/test in this story, run `python -m spacy download en_core_web_sm` instead (small model, used only in tests — see Task 4 and Design Note 4).
- **Mirror**: `requirements.txt:1-9` — bare unpinned package names, no comments, no grouping.
- **Validate**: `pip install -r requirements.txt` succeeds.

### Task 3: Create the Presidio adapter module

- **File**: `app/services/pii_redactor.py`
- **Action**: CREATE
- **Implement**:
  ```python
  from typing import List, Optional, Tuple

  from presidio_analyzer import AnalyzerEngine
  from presidio_analyzer.nlp_engine import NlpEngineProvider
  from presidio_anonymizer import AnonymizerEngine

  from app.config import settings

  _analyzer: Optional[AnalyzerEngine] = None
  _anonymizer: Optional[AnonymizerEngine] = None


  class PiiRedactorError(Exception):
      pass


  def _build_analyzer() -> AnalyzerEngine:
      nlp_configuration = {
          "nlp_engine_name": "spacy",
          "models": [{"lang_code": "en", "model_name": settings.PII_NLP_MODEL}],
      }
      try:
          nlp_engine = NlpEngineProvider(nlp_configuration=nlp_configuration).create_engine()
          return AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
      except Exception as exc:
          raise PiiRedactorError(f"Failed to load Presidio NLP model {settings.PII_NLP_MODEL!r}: {exc}") from exc


  def _get_analyzer() -> AnalyzerEngine:
      global _analyzer
      if _analyzer is None:
          _analyzer = _build_analyzer()
      return _analyzer


  def _get_anonymizer() -> AnonymizerEngine:
      global _anonymizer
      if _anonymizer is None:
          _anonymizer = AnonymizerEngine()
      return _anonymizer


  def redact(text: str) -> Tuple[str, List[str]]:
      if not settings.PII_REDACTION_ENABLED or not text:
          return text, []

      analyzer = _get_analyzer()
      try:
          results = analyzer.analyze(
              text=text,
              language="en",
              entities=settings.pii_entities_list,
              score_threshold=settings.PII_SCORE_THRESHOLD,
          )
      except Exception as exc:
          raise PiiRedactorError(f"PII analysis failed: {exc}") from exc

      if not results:
          return text, []

      anonymizer = _get_anonymizer()
      try:
          anonymized = anonymizer.anonymize(text=text, analyzer_results=results)
      except Exception as exc:
          raise PiiRedactorError(f"PII anonymization failed: {exc}") from exc

      entities_found = sorted({result.entity_type for result in results})
      return anonymized.text, entities_found
  ```
  Keeps every Presidio-specific import confined to this file (adapter pattern, per story Technical Notes line 41 and PRD Section 6 line 127) — no other module may `import presidio_*`.
- **Mirror**: `app/services/duplicate_checker.py:1-23` (custom exception + module constants), `app/services/openrouter_client.py:47-61` (try/except wrapping a third-party call into a domain exception).
- **Validate**: `cd f:\AI\harness-ai && python -c "from app.services.pii_redactor import redact; print(redact('my email is a@b.com'))"` (requires `en_core_web_sm` or `en_core_web_lg` installed locally first) prints masked text containing `<EMAIL_ADDRESS>` and `['EMAIL_ADDRESS']`.

### Task 4: Unit tests for all 5 acceptance criteria

- **File**: `tests/test_pii_redactor.py`
- **Action**: CREATE
- **Implement**:
  ```python
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


  def test_redacts_default_entity_pii_and_reports_entity_type():
      redacted, entities_found = redact("my email is a@b.com")

      assert "a@b.com" not in redacted
      assert "<EMAIL_ADDRESS>" in redacted
      assert "EMAIL_ADDRESS" in entities_found


  def test_text_without_pii_is_returned_unchanged():
      text = "the sky is blue today"

      redacted, entities_found = redact(text)

      assert redacted == text
      assert entities_found == []


  def test_analyzer_engine_constructed_only_once(monkeypatch):
      build_calls = []
      original_build = pii_redactor._build_analyzer

      def _counting_build():
          build_calls.append(1)
          return original_build()

      monkeypatch.setattr(pii_redactor, "_build_analyzer", _counting_build)

      redact("first call, no pii")
      redact("second call, no pii either")

      assert len(build_calls) == 1


  def test_pii_entities_env_var_restricts_checked_types(monkeypatch):
      monkeypatch.setattr(settings, "PII_ENTITIES", "EMAIL_ADDRESS")

      _, entities_found = redact("call me at 555-123-4567 or a@b.com")

      assert entities_found == ["EMAIL_ADDRESS"]


  def test_score_threshold_filters_low_confidence_matches(monkeypatch):
      monkeypatch.setattr(settings, "PII_SCORE_THRESHOLD", 0.99)

      redacted, entities_found = redact("maybe John is a person")

      assert entities_found == []
      assert redacted == "maybe John is a person"


  def test_pii_nlp_model_setting_is_used_to_build_engine(monkeypatch):
      seen_models = []
      original_build = pii_redactor._build_analyzer

      def _capturing_build():
          seen_models.append(settings.PII_NLP_MODEL)
          return original_build()

      monkeypatch.setattr(pii_redactor, "_build_analyzer", _capturing_build)

      redact("trigger a build")

      assert seen_models == ["en_core_web_sm"]
  ```
  Covers all 5 story ACs: masked email + `entities_found` (AC1), no-PII passthrough (AC2), singleton construction (AC3), `PII_ENTITIES`/`PII_SCORE_THRESHOLD` filtering (AC4), `PII_NLP_MODEL` used at build time (AC5). The `test_score_threshold_filters_low_confidence_matches` test relies on a bare first-name-only sentence scoring below `0.99` with `en_core_web_sm`'s NER — if this proves flaky in practice, swap the assertion to compare `entities_found` counts between a low and a `1.01` (unreachable) threshold rather than asserting an exact empty result.
- **Mirror**: `tests/test_duplicate_checker.py:1-4` (env bootstrap), `tests/test_openrouter_client.py:59-65` (`monkeypatch.setattr(settings, ...)` per-test override).
- **Validate**: `cd f:\AI\harness-ai && python -m pytest tests/test_pii_redactor.py -v`

---

## End-to-End Tests

This story has no HTTP-facing surface (no router/pipeline change), so no live-server E2E checks apply. Manual/automated checks for `/implement` to execute:

- [ ] `python -m spacy download en_core_web_sm` succeeds locally (one-time setup, needed before tests will pass)
- [ ] `python -m pytest tests/test_pii_redactor.py -v` — all new tests pass
- [ ] `python -m pytest` (full suite) — confirms this story didn't break `test_duplicate_checker.py`, `test_openrouter_client.py`, or any other existing test (no shared state touched)
- [ ] `python -c "from app.services.pii_redactor import redact; print(redact('my email is a@b.com'))"` — manual smoke check of the AC1 example from the shell

---

## Validation

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python -m pytest tests/test_pii_redactor.py -v
python -m pytest
```

---

## Acceptance Criteria

(Copied from story STORY-001)

- [ ] Given a text containing default-entity PII (e.g. `"my email is a@b.com"`), when `redact(text)` is called, then it returns `(redacted_text, entities_found)` with the email masked (e.g. `<EMAIL_ADDRESS>`) and `entities_found` containing `"EMAIL_ADDRESS"`.
- [ ] Given text with no detectable PII, when `redact(text)` is called, then the original text is returned unchanged and `entities_found` is an empty list.
- [ ] Given the module is imported and `redact()` called multiple times, when inspected, then the `AnalyzerEngine`/NLP model is constructed only once (module-level singleton), not per call.
- [ ] Given `PII_ENTITIES` and `PII_SCORE_THRESHOLD` env vars are set, when `redact(text)` runs, then only the configured entity types are checked and matches below the threshold are not masked (default threshold is low/permissive, favoring recall).
- [ ] Given `PII_NLP_MODEL` is set, when the analyzer initializes, then it loads that spaCy model name instead of a hardcoded default.
- [ ] All tasks completed
- [ ] Full existing test suite (`python -m pytest`) still passes, unmodified
- [ ] `app/main.py` and `app/routers/query.py` unchanged — no pipeline wiring in this story
- [ ] No module other than `app/services/pii_redactor.py` imports `presidio_*`
- [ ] Follows existing patterns (plain functions, module-level constants, one custom exception per module, no logging in service modules)
