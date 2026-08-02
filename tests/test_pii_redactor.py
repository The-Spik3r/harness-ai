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


def test_load_constructs_analyzer_singleton_when_enabled():
    assert pii_redactor._analyzer is None

    pii_redactor.load()

    assert pii_redactor._analyzer is not None


def test_load_is_noop_when_redaction_disabled(monkeypatch):
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)

    pii_redactor.load()

    assert pii_redactor._analyzer is None
