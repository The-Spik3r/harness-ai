import os
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import database
from app.db.database import count_active_users, insert_user
from app.db.errors import DatabaseUnreachableError
from app.db.models import User
from app.main import app
from app.services.identity import hash_token
import app.services.authz as authz
import app.services.pattern_config as pattern_config
import app.services.pii_redactor as pii_redactor
from app.services import pipeline_executor
from app.services.pattern_config import BUILT_IN_POLICY, PatternConfigError

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.fixture
def _small_model_and_reset(monkeypatch, temp_db):
    monkeypatch.setattr(settings, "PII_NLP_MODEL", "en_core_web_sm")
    monkeypatch.setattr(pii_redactor, "_analyzer", None)
    monkeypatch.setattr(pii_redactor, "_anonymizer", None)
    # `temp_db` because the lifespan calls init_db(): before STORY-005 these
    # tests ran against whatever DATABASE_URL the developer had configured --
    # the repo-root harness_ai.db -- which the comment below used to admit in
    # passing. Now that a DATABASE_URL naming no reachable database is a real
    # error rather than a file that springs into existence, the dependency has
    # to be declared. Nothing about these assertions wanted a shared database.
    #
    # RBAC_ENABLED is unrelated to the bootstrap: the fixture database has no
    # seeded users, so STORY-016's guard would otherwise fire.
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
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


def test_lifespan_loads_roles_file_before_serving_requests(tmp_path, monkeypatch, temp_db):
    roles_file = tmp_path / "roles.json"
    roles_file.write_text('{"user": ["query:submit"]}')
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(roles_file))
    # `temp_db` for the same reason as `_small_model_and_reset` above: the
    # lifespan calls init_db(), and this test used to lean on the developer's
    # configured database rather than asking for one.
    #
    # RBAC_ENABLED is unrelated to the bootstrap: the fixture database has no
    # seeded users, so STORY-016's guard would otherwise fire.
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    original = authz.ROLE_PERMISSIONS

    try:
        with TestClient(app) as test_client:
            assert authz.ROLE_PERMISSIONS == {"user": {"query:submit"}}
            response = test_client.get("/health")
            assert response.status_code == 200
    finally:
        authz.ROLE_PERMISSIONS = original


@pytest.fixture
def _empty_users_db(temp_db):
    """conftest's initialized database, with no user seeded into it.

    Requested for its side effect -- the startup guard reads the `users` table
    through `settings.DATABASE_URL`, which `temp_db` has already patched."""


def test_lifespan_fails_fast_when_rbac_enabled_and_no_active_users(
    _empty_users_db, monkeypatch
):
    monkeypatch.setattr(settings, "RBAC_ENABLED", True)
    assert count_active_users() == 0

    with pytest.raises(authz.RbacNotBootstrappedError):
        with TestClient(app):
            pass


def test_lifespan_boots_when_rbac_enabled_and_one_active_user(
    _empty_users_db, monkeypatch
):
    monkeypatch.setattr(settings, "RBAC_ENABLED", True)
    insert_user(User(user_id="ana", role="user", token_hash=hash_token("ana-token")))

    with TestClient(app) as test_client:
        response = test_client.get("/health")
        assert response.status_code == 200


def test_lifespan_skips_guard_when_rbac_disabled(_empty_users_db, monkeypatch):
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    assert count_active_users() == 0

    with TestClient(app) as test_client:
        response = test_client.get("/health")
        assert response.status_code == 200


def test_lifespan_fails_fast_even_with_only_admin_token_configured(
    _empty_users_db, monkeypatch
):
    monkeypatch.setattr(settings, "RBAC_ENABLED", True)
    assert settings.ADMIN_TOKEN
    assert count_active_users() == 0

    with pytest.raises(authz.RbacNotBootstrappedError):
        with TestClient(app):
            pass


def test_lifespan_shuts_down_the_pipeline_executor(monkeypatch, temp_db):
    """PRD-010 STORY-006 AC5: pipeline_executor.shutdown() runs on app
    shutdown, following the same `with TestClient(app):` pattern the other
    lifespan tests in this file use to exercise startup *and* teardown."""
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    calls = []
    monkeypatch.setattr(pipeline_executor, "shutdown", lambda: calls.append(1))

    with TestClient(app):
        assert calls == []

    assert calls == [1]


def test_lifespan_fails_when_the_database_is_unreachable(monkeypatch):
    """STORY-008 AC1 and AC4 on the FastAPI path.

    The distinction this test exists to make is *where* the failure happens.
    tests/test_db.py already proves init_db() raises against a dead endpoint;
    what matters here is that app.main's lifespan reaches it before the
    application is serving, so uvicorn exits during startup instead of binding a
    port and failing on the first POST /query -- the "boots, accepts queries,
    drops audit rows" outcome the story was written against.
    """
    monkeypatch.setattr(settings, "DATABASE_URL", "http://127.0.0.1:1")
    database._client = None
    database._client_key = None

    try:
        with pytest.raises(DatabaseUnreachableError):
            with TestClient(app):
                pass
    finally:
        # The module-level `client` above shares this process's client; leaving
        # it pointed at a dead endpoint would leak into every later test.
        database._client = None
        database._client_key = None


# --------------------------------------------------------------------------
# PRD-011 STORY-007 -- pattern_config.load() in app.main's lifespan.
# --------------------------------------------------------------------------

#: PRD-011 Section 6.3's file with PRD User Story 2's typo: `match` spelled
#: `mach` under `injection`. Well-formed YAML on purpose, so the failure is
#: load()'s validation naming the list and the key, not a parse error.
_MALFORMED_PATTERNS = """
lists:
  injection:
    mach: word
    scope: everywhere
    patterns:
      - ignore previous instructions
profiles:
  chat:
    lists: [injection]
    roles:
      user: block
"""

_SAMPLE_PATTERNS_FILE = Path(__file__).resolve().parents[1] / "examples" / "patterns.yaml"


@pytest.fixture
def _pattern_startup(monkeypatch, temp_db):
    """A lifespan that boots up to pattern_config.load() and restores the policy.

    `temp_db` because the lifespan calls init_db(). RBAC_ENABLED is unrelated
    to the patterns file: the fixture database has no seeded users, so
    STORY-016's guard would otherwise fire. PII_REDACTION_ENABLED is off so
    these tests never build the spaCy analyzer they do not exercise.
    PATTERN_PROFILE_DEFAULT is pinned so a developer's `.env` cannot decide
    load()'s cross-check (STORY-006).
    """
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)
    monkeypatch.setattr(settings, "PATTERN_PROFILE_DEFAULT", "chat")
    original = pattern_config._policy
    yield
    pattern_config._policy = original


def test_lifespan_fails_when_patterns_file_is_malformed(_pattern_startup, tmp_path, monkeypatch):
    """PRD-011 STORY-007 AC 1 and AC 4, FastAPI path: a malformed
    PATTERNS_FILE stops startup with PatternConfigError, before the app serves
    anything, and leaves no half-applied policy behind."""
    patterns_file = tmp_path / "patterns.yaml"
    patterns_file.write_text(_MALFORMED_PATTERNS, encoding="utf-8")
    monkeypatch.setattr(settings, "PATTERNS_FILE", str(patterns_file))

    with pytest.raises(PatternConfigError) as excinfo:
        with TestClient(app):
            pass

    assert "injection" in str(excinfo.value)
    assert "mach" in str(excinfo.value)
    assert pattern_config.get_policy() is BUILT_IN_POLICY


def test_lifespan_loads_patterns_file_before_serving_requests(_pattern_startup, monkeypatch):
    """PRD-011 STORY-007 AC 1: the lifespan actually calls load() -- the
    shipped sample is in force by the time the first request is served."""
    monkeypatch.setattr(settings, "PATTERNS_FILE", str(_SAMPLE_PATTERNS_FILE))

    with TestClient(app) as test_client:
        policy = pattern_config.get_policy()
        assert policy is not BUILT_IN_POLICY
        assert policy == BUILT_IN_POLICY
        response = test_client.get("/health")
        assert response.status_code == 200


def test_lifespan_reads_no_patterns_file_when_unset(_pattern_startup, monkeypatch):
    """PRD-011 STORY-007 AC 5: an existing deployment with no PATTERNS_FILE
    reads no file and keeps the built-in policy. `Path` is replaced inside
    pattern_config only -- a global Path.read_text patch would also trip on
    unrelated startup code."""
    monkeypatch.setattr(settings, "PATTERNS_FILE", "")

    def _no_path(*args, **kwargs):
        raise AssertionError("pattern_config built a Path while PATTERNS_FILE is unset")

    monkeypatch.setattr(pattern_config, "Path", _no_path)

    with TestClient(app) as test_client:
        assert pattern_config.get_policy() is BUILT_IN_POLICY
        response = test_client.get("/health")
        assert response.status_code == 200


# --------------------------------------------------------------------------
# PRD-012 STORY-006 -- pii_redactor.load() prebuilds the code profile's analyzer.
# --------------------------------------------------------------------------
# The Reflex lifespan is not re-tested here: chat_ui/chat_ui/chat_ui.py
# registers the same zero-arg pii_redactor.load, unchanged, so what it builds
# and how it fails is what these two tests show.


@pytest.fixture
def _pii_startup(_small_model_and_reset, monkeypatch):
    """The PII lifespan fixture above, plus the second analyzer reset and
    PII_ENTITIES_CODE pinned so a developer's .env cannot change the selection."""
    monkeypatch.setattr(settings, "PII_ENTITIES_CODE", "EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE")
    monkeypatch.setattr(pii_redactor, "_pattern_analyzer", None)
    yield


def test_lifespan_prebuilds_the_code_profiles_analyzer(_pii_startup, monkeypatch):
    """PRD-012 STORY-006 AC 3, FastAPI path: the lifespan builds today's analyzer
    and the tokenizer-only one PII_ENTITIES_CODE selects, and a request builds
    neither again."""
    build_calls = []
    original_build = pii_redactor._build_pattern_analyzer

    def _counting_build():
        build_calls.append(1)
        return original_build()

    monkeypatch.setattr(pii_redactor, "_build_pattern_analyzer", _counting_build)

    with TestClient(app) as test_client:
        assert pii_redactor._analyzer is not None
        assert pii_redactor._pattern_analyzer is not None
        assert len(build_calls) == 1
        response = test_client.get("/health")
        assert response.status_code == 200
        assert len(build_calls) == 1


def test_lifespan_fails_when_the_tokenizer_only_analyzer_cannot_be_built(_pii_startup, monkeypatch):
    """PRD-012 STORY-006 Technical Notes, FastAPI path: a failure to build the
    pattern-only analyzer stops startup with PiiRedactorError. It never falls
    back to the full analyzer."""

    def _raising(*args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(pii_redactor.spacy, "blank", _raising)

    with pytest.raises(pii_redactor.PiiRedactorError) as excinfo:
        with TestClient(app):
            pass

    assert "PII_ENTITIES_CODE" in str(excinfo.value)
    assert pii_redactor._pattern_analyzer is None
