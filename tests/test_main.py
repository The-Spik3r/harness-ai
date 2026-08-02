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
