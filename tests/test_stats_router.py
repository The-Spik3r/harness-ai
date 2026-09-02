import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import database
from app.db.database import (
    SUMMARY_FIGURES,
    SummarySnapshot,
    count_audit_logs,
    count_blocked_duplicates,
    count_blocked_suspicious,
    count_pii_detected_queries,
    count_successful_queries,
    count_unique_users,
    insert_audit_log,
    insert_user,
    top_models,
    top_pii_entities,
    top_users,
)
from app.db.models import AuditLog, User
from app.main import app
from app.services.authz import PERMISSION_STATS_READ
from app.services.identity import hash_token

client = TestClient(app)


def _fail_if_called(*args, **kwargs):
    raise AssertionError("repository function should not have been called")


def _guard_all_aggregates(monkeypatch):
    """Makes any aggregation the endpoint attempts a hard failure.

    The claim the two callers make through it is unchanged -- the gate refuses
    before a single figure is read -- but there is now one call to guard rather
    than seven. STORY-011 replaced `get_stats()`'s nine sequential reads with
    one `summary_snapshot()`, so the seven names this used to patch are no
    longer imported by `app.routers.admin` and `monkeypatch.setattr` would
    raise `AttributeError` on every one of them.

    The single target is also the stricter guard of the two: the old list
    omitted `count_pii_detected_queries` and `top_pii_entities`, so two of the
    nine reads could have run behind a refused gate without failing this. All
    ten figures now sit behind the one name.
    """
    monkeypatch.setattr("app.routers.admin.summary_snapshot", _fail_if_called)


def test_missing_admin_token_rejected_before_aggregation(temp_db, monkeypatch):
    _guard_all_aggregates(monkeypatch)

    response = client.get("/stats")

    assert response.status_code in (401, 403)


def test_incorrect_admin_token_rejected(temp_db, monkeypatch):
    _guard_all_aggregates(monkeypatch)

    response = client.get("/stats", headers={"Authorization": "Bearer wrong-token"})

    assert response.status_code in (401, 403)


def test_valid_token_returns_expected_shape_and_values(temp_db):
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-01T10:00:00Z",
            user_id="a",
            prompt_hash="h1",
            model_used="gpt-4",
            success=True,
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-02T10:00:00Z",
            user_id="a",
            prompt_hash="h2",
            model_used="gpt-4",
            success=True,
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-03T10:00:00Z",
            user_id="a",
            prompt_hash="h3",
            was_duplicate_blocked=True,
            success=False,
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-04T10:00:00Z",
            user_id="b",
            prompt_hash="h4",
            suspicious_pattern="override",
            success=False,
        )
    )

    response = client.get(
        "/stats", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "total_queries",
        "blocked_duplicates",
        "blocked_suspicious",
        "unique_users",
        "success_rate",
        "top_models",
        "top_users",
        "pii_detected_queries",
        "top_pii_entities",
    }
    assert body["total_queries"] == 4
    assert body["blocked_duplicates"] == 1
    assert body["blocked_suspicious"] == 1
    assert body["unique_users"] == 2
    assert body["success_rate"] == "50.0%"
    assert body["top_models"] == ["gpt-4"]
    assert body["top_users"] == ["a", "b"]
    assert body["pii_detected_queries"] == 0
    assert body["top_pii_entities"] == []


def test_zero_rows_returns_zeroed_stats_without_error(temp_db):
    response = client.get(
        "/stats", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "total_queries": 0,
        "blocked_duplicates": 0,
        "blocked_suspicious": 0,
        "unique_users": 0,
        "success_rate": "0.0%",
        "top_models": [],
        "top_users": [],
        "pii_detected_queries": 0,
        "top_pii_entities": [],
    }


def test_pii_detected_queries_and_top_pii_entities_reflect_flagged_rows(temp_db):
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-01T10:00:00Z",
            user_id="a",
            prompt_hash="h1",
            pii_detected_input=True,
            pii_entities="EMAIL_ADDRESS",
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-02T10:00:00Z",
            user_id="b",
            prompt_hash="h2",
            pii_detected_output=True,
            pii_entities="EMAIL_ADDRESS,PERSON",
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-03T10:00:00Z",
            user_id="c",
            prompt_hash="h3",
        )
    )

    response = client.get(
        "/stats", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    body = response.json()
    assert body["pii_detected_queries"] == 2
    assert body["top_pii_entities"][0] == "EMAIL_ADDRESS"
    assert set(body["top_pii_entities"]) == {"EMAIL_ADDRESS", "PERSON"}


def test_identity_lacking_stats_read_returns_403_naming_permission(temp_db):
    insert_user(
        User(user_id="ana", role="user", token_hash=hash_token("ana-token"))
    )

    response = client.get(
        "/stats", headers={"Authorization": "Bearer ana-token"}
    )

    assert response.status_code == 403
    assert response.json() == {"detail": f"Permission denied: {PERMISSION_STATS_READ}"}


def test_auditor_role_reads_stats_with_unchanged_shape(temp_db):
    insert_user(
        User(user_id="reviewer", role="auditor", token_hash=hash_token("auditor-token"))
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-01T10:00:00Z", user_id="a", prompt_hash="h1")
    )

    response = client.get(
        "/stats", headers={"Authorization": "Bearer auditor-token"}
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "total_queries",
        "blocked_duplicates",
        "blocked_suspicious",
        "unique_users",
        "success_rate",
        "top_models",
        "top_users",
        "pii_detected_queries",
        "top_pii_entities",
    }
    assert body["total_queries"] == 1


# --------------------------------------------------------------------------
# STORY-011: the nine sequential reads are one batched read
# --------------------------------------------------------------------------


def _count_audit_log_statements(monkeypatch) -> list:
    """Records every SQL statement reaching the database, for counting.

    The same proxy idiom as `tests/test_db.py::_count_statements` -- the libSQL
    connection has no tracing hook (STORY-006), so the instrument is a wrapper
    rather than a callback.
    """
    statements: list = []
    real_get_connection = database.get_connection

    class _RecordingConnection:
        def __init__(self, conn):
            self._conn = conn

        def __enter__(self):
            self._conn.__enter__()
            return self

        def __exit__(self, *exc_info):
            return self._conn.__exit__(*exc_info)

        def execute(self, sql, *parameters):
            statements.append(sql)
            return self._conn.execute(sql, *parameters)

    monkeypatch.setattr(
        database,
        "get_connection",
        lambda: _RecordingConnection(real_get_connection()),
    )
    return statements


def _seed_four_rows() -> None:
    for index, entry in enumerate(
        (
            {"user_id": "a", "model_used": "gpt-4", "success": True},
            {"user_id": "a", "model_used": "gpt-4", "success": True},
            {"user_id": "b", "was_duplicate_blocked": True, "success": False},
            {"user_id": "b", "suspicious_pattern": "override", "success": False},
        )
    ):
        insert_audit_log(
            AuditLog(
                timestamp=f"2026-07-0{index + 1}T10:00:00Z",
                prompt_hash=f"h{index}",
                **entry,
            )
        )


def test_stats_issues_one_database_round_trip_for_its_figures(temp_db, monkeypatch):
    """AC 1, counted rather than asserted in prose.

    **Only statements against `audit_logs` are counted.** A `/stats` request is
    not one statement end to end: `require_permission` -> `require_identity`
    resolves the bearer token against the `users` table first, and it always
    did. What this story changed, and therefore what this test pins, is the
    endpoint's *figure* reads -- nine of them before, one now.

    The contrast is measured here rather than assumed: the same nine figures
    read the way `get_stats()` read them until STORY-011 issue nine statements.
    `tests/test_db.py::test_summary_snapshot_issues_one_round_trip` counts the
    batched read's own 1-vs-10; this counts the endpoint's adoption of it.
    """
    _seed_four_rows()

    statements = _count_audit_log_statements(monkeypatch)
    response = client.get(
        "/stats", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    assert response.status_code == 200
    assert statements, "the proxy captured nothing -- the patch did not take"
    figure_reads = [sql for sql in statements if "audit_logs" in sql]
    assert len(figure_reads) == 1, figure_reads

    # What the endpoint used to do, under the same instrument.
    statements.clear()
    count_audit_logs()
    count_successful_queries()
    count_blocked_duplicates()
    count_blocked_suspicious()
    count_unique_users()
    count_pii_detected_queries()
    top_models()
    top_users()
    top_pii_entities()
    assert len([sql for sql in statements if "audit_logs" in sql]) == 9


def _snapshot_of(**overrides) -> SummarySnapshot:
    """A complete ten-figure snapshot -- `figures` and `errors` must partition
    `SUMMARY_FIGURES` exactly or `SummarySnapshot.__post_init__` refuses it."""
    figures = {
        "rows": [],
        "total_recorded": 7,
        "blocked_duplicates": 1,
        "blocked_suspicious": 2,
        "unique_users": 3,
        "successful_queries": 4,
        "pii_detected_queries": 5,
        "top_models": ["gpt-4"],
        "top_users": ["a", "b"],
        "top_pii_entities": ["EMAIL_ADDRESS"],
    }
    figures.update(overrides)
    assert set(figures) == set(SUMMARY_FIGURES)
    return SummarySnapshot(figures=figures, errors={})


def test_stats_does_not_fetch_the_register_rows(temp_db, monkeypatch):
    """The endpoint needs nine of the batched read's ten figures, and declines
    the tenth by emptying it.

    `rows` cannot be projected away -- `_SUMMARY_SQL` is a fixed ten-column
    SELECT -- but its subquery ends in `LIMIT ?`, so `row_limit=0` returns an
    empty array instead of up to 100 fully serialized audit rows crossing the
    network per call with nothing reading them.

    `ranked_limit` is asserted *absent*, not merely equal to 5. Until STORY-011
    the three `top_*` figures were read through the functions' own default of
    5, which is also `summary_snapshot()`'s; passing nothing is what keeps the
    two defaults tracking each other, and pinning the absence is what stops a
    later edit from freezing one of them by hand.
    """
    calls: list = []

    def fake(*args, **kwargs):
        calls.append((args, kwargs))
        return _snapshot_of()

    monkeypatch.setattr("app.routers.admin.summary_snapshot", fake)

    response = client.get(
        "/stats", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    assert calls == [((), {"row_limit": 0})]
    assert response.status_code == 200
    assert response.json() == {
        "total_queries": 7,
        "blocked_duplicates": 1,
        "blocked_suspicious": 2,
        "unique_users": 3,
        "success_rate": "57.1%",
        "top_models": ["gpt-4"],
        "top_users": ["a", "b"],
        "pii_detected_queries": 5,
        "top_pii_entities": ["EMAIL_ADDRESS"],
    }
