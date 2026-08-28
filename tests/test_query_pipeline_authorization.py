import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

from app.config import settings
from app.db.database import get_audit_log, get_connection, init_db
from app.models.schemas import QueryBlockedForbiddenResponse, QuerySuccessResponse
from app.services.authz import PERMISSION_QUERY_SUBMIT
from app.services.identity import Identity
from app.services.openrouter_client import OpenRouterResult
from app.services.query_pipeline import run_query
import app.services.query_pipeline as query_pipeline


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


def _last_audit_id() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
        return row["id"]


def _fail_if_called(*args, **kwargs):
    raise AssertionError("call_openrouter should not have been called")


def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
    return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)


# ---------------------------------------------------------------------------
# AC2: a forbidden identity is denied before check_duplicate(), and
# call_openrouter is never invoked.
# ---------------------------------------------------------------------------


def test_forbidden_identity_blocked_before_check_duplicate(temp_db, monkeypatch):
    duplicate_calls = []
    real_check_duplicate = query_pipeline.check_duplicate

    def _spy_check_duplicate(prompt):
        duplicate_calls.append(prompt)
        return real_check_duplicate(prompt)

    monkeypatch.setattr(query_pipeline, "check_duplicate", _spy_check_duplicate)

    identity = Identity(user_id="reviewer", role="auditor")  # lacks query:submit

    result = run_query(
        identity=identity,
        prompt="hello world",
        device=None,
        model="gpt-4",
        openrouter_api_key=None,
        call_openrouter=_fail_if_called,
    )

    assert isinstance(result, QueryBlockedForbiddenResponse)
    assert result.required_permission == PERMISSION_QUERY_SUBMIT
    assert duplicate_calls == []  # check_duplicate() never ran


# ---------------------------------------------------------------------------
# AC3: exactly one audit row, carrying role + denied_permission, success=1.
# ---------------------------------------------------------------------------


def test_forbidden_identity_writes_exactly_one_audit_row(temp_db):
    identity = Identity(user_id="reviewer", role="auditor")
    before = _count_audit_rows()

    run_query(
        identity=identity,
        prompt="hello world",
        device=None,
        model="gpt-4",
        openrouter_api_key=None,
        call_openrouter=_fail_if_called,
    )

    assert _count_audit_rows() == before + 1

    entry = get_audit_log(_last_audit_id())
    assert entry.user_id == "reviewer"
    assert entry.role == "auditor"
    assert entry.denied_permission == PERMISSION_QUERY_SUBMIT
    assert entry.success is True


# ---------------------------------------------------------------------------
# AC4 sanity: an authorized identity still reaches OpenRouter and returns
# QuerySuccessResponse -- step 0 does not disturb steps 1-6.
# ---------------------------------------------------------------------------


def test_authorized_identity_reaches_openrouter(temp_db):
    identity = Identity(user_id="juan@empresa.com", role="user")

    result = run_query(
        identity=identity,
        prompt="hello world",
        device=None,
        model="gpt-4",
        openrouter_api_key=None,
        call_openrouter=_fake_call_openrouter,
    )

    assert isinstance(result, QuerySuccessResponse)
    assert result.response == "Hi there!"


# ---------------------------------------------------------------------------
# AC5: a caller that omits identity fails outright -- enforcement by
# signature, not a runtime guard.
# ---------------------------------------------------------------------------


def test_run_query_without_identity_raises_type_error(temp_db):
    with pytest.raises(TypeError):
        run_query(
            prompt="hello world",
            device=None,
            model="gpt-4",
            openrouter_api_key=None,
            call_openrouter=_fail_if_called,
        )
