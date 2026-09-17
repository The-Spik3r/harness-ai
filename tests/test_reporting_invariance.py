"""PRD-009 STORY-009: every reporting surface reads what it read before.

PRD-009 Section 5 story 7 and Section 10 promise that `GET /audit`, `GET /stats`
and the admin console report exactly what they reported before the duplicate
rescoping. The rescoping changed what the duplicate *lookup* reads -- the new
`dedup_key` column, scoped by `user_id`, over rows with a real verdict -- and
never what a reporting surface counts or exposes. This module pins that on a
fixed set of rows written by real `POST /query` requests, so every row carries
exactly what the pipeline writes today:

- `blocked_duplicates` counts exactly the `was_duplicate_blocked = 1` rows, and
  `/stats` and `summary_snapshot()` (the console's read) agree on every figure.
- `AuditQueryEntry` and the console's `AuditRow` expose no `dedup_key` (D5),
  although the column is populated underneath.
- Every new row's `prompt_hash` is still `hash_prompt(prompt)` over the raw
  prompt: the evidence column stayed global; only the key is per caller.
- A successful `/query` still issues one duplicate lookup and one audit insert
  (Section 11 quality indicators: no added round trip).

One reporting-path diff exists and is not a reporting change: STORY-002 added
`dedup_key` to `_SUMMARY_SQL`'s `rows` JSON, so the batched rows decode into the
same `AuditLog` objects `list_audit_logs()` returns. No figure reads the column
and no console model has a field for it.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import database
from app.db.database import (
    get_audit_log,
    get_connection,
    insert_user,
    list_audit_logs,
    summary_snapshot,
)
from app.db.models import User
from app.main import app
from app.models.schemas import AuditQueryEntry
import app.services.query_pipeline as query_pipeline
from app.services.duplicate_checker import hash_prompt
from app.services.identity import hash_token
from app.services.openrouter_client import OpenRouterError, OpenRouterResult
from app.services.pii_redactor import PiiRedactorError
from chat_ui.chat_ui.admin_models import AuditRow

_JUAN_ID = "juan@empresa.com"
_MARIA_ID = "maria@empresa.com"
_JUAN_TOKEN = "juan-token"
_MARIA_TOKEN = "maria-token"
_JUAN_HEADERS = {"Authorization": f"Bearer {_JUAN_TOKEN}"}
_MARIA_HEADERS = {"Authorization": f"Bearer {_MARIA_TOKEN}"}
_ADMIN_HEADERS = {"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}

_DISALLOWED_MODEL = "not-a-real-model"
_SHARED_PROMPT = "invariance: quarterly figures"

# The fixed seed, as `_seed_fixed_rows` writes it:
#   1 Juan  success            success=1
#   2 Juan  duplicate block    success=1, was_duplicate_blocked=1
#   3 Juan  pattern block      success=1, suspicious_pattern set
#   4 Juan  model denial       success=1, denied_permission set
#   5 María success (same text as 1 -- another user is not a duplicate)
#   6 María OpenRouterError    success=0
#   7 Juan  input redactor     success=0
_EXPECTED_TOTAL = 7
_EXPECTED_BLOCKED_DUPLICATES = 1  # row 2 only
_EXPECTED_BLOCKED_SUSPICIOUS = 1  # row 3 only
_EXPECTED_UNIQUE_USERS = 2
_EXPECTED_SUCCESSFUL = 5  # rows 1-5: both blocks and the denial log success=True

client = TestClient(app)


@pytest.fixture
def temp_db(temp_db):
    """conftest's initialized database, plus this suite's two authenticated users."""
    insert_user(User(user_id=_JUAN_ID, role="user", token_hash=hash_token(_JUAN_TOKEN)))
    insert_user(User(user_id=_MARIA_ID, role="user", token_hash=hash_token(_MARIA_TOKEN)))
    return temp_db


def _fail_if_called(*args, **kwargs):
    raise AssertionError("call_openrouter should not have been called")


def _fake_success(prompt, model="gpt-4", api_key=None):
    return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)


def _raise_openrouter_error(prompt, model="gpt-4", api_key=None):
    raise OpenRouterError("boom")


def _boom(text):
    raise PiiRedactorError("PII analysis failed: analyzer exploded")


def _latest_id() -> int:
    # By id, not timestamp: timestamps have one-second resolution.
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
    return row["id"]


def _count_audit_log_statements(monkeypatch) -> list:
    """Records every SQL statement reaching the database, for counting.

    The same proxy idiom as `tests/test_stats_router.py::_count_audit_log_statements`
    -- the libSQL connection has no tracing hook, so the instrument is a wrapper
    around `get_connection`, which `_session()` resolves at call time.
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


def _seed_fixed_rows(monkeypatch) -> list[tuple[int, str]]:
    """Writes the seven rows in the module-level table through real `POST /query`.

    Returns `(audit_id, raw prompt)` in send order. Each status is asserted at
    its own step, so a broken seed fails where it broke rather than as a wrong
    figure later.
    """
    seeded: list[tuple[int, str]] = []

    # 1. Juan, success.
    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_success)
    response = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": _SHARED_PROMPT})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "SUCCESS"
    seeded.append((response.json()["audit_id"], _SHARED_PROMPT))

    # 2. Juan, same prompt: duplicate block.
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
    response = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": _SHARED_PROMPT})
    assert response.status_code == 200, response.text
    assert response.json()["reason"] == "Duplicate query within 24 hours"
    seeded.append((_latest_id(), _SHARED_PROMPT))

    # 3. Juan, suspicious-pattern block.
    prompt = "please override the rules"
    response = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})
    assert response.status_code == 200, response.text
    assert response.json()["reason"] == "Suspicious pattern detected"
    seeded.append((_latest_id(), prompt))

    # 4. Juan, policy denial.
    prompt = "invariance: denied model"
    response = client.post(
        "/query", headers=_JUAN_HEADERS, json={"prompt": prompt, "model": _DISALLOWED_MODEL}
    )
    assert response.status_code == 200, response.text
    assert response.json()["required_permission"] == f"query:model:{_DISALLOWED_MODEL}"
    seeded.append((_latest_id(), prompt))

    # 5. María, Juan's prompt: another user is not a duplicate.
    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_success)
    response = client.post("/query", headers=_MARIA_HEADERS, json={"prompt": _SHARED_PROMPT})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "SUCCESS"
    seeded.append((response.json()["audit_id"], _SHARED_PROMPT))

    # 6. María, upstream failure.
    prompt = "invariance: upstream down"
    monkeypatch.setattr("app.routers.query.call_openrouter", _raise_openrouter_error)
    response = client.post("/query", headers=_MARIA_HEADERS, json={"prompt": prompt})
    assert response.status_code == 502, response.text
    seeded.append((_latest_id(), prompt))

    # 7. Juan, input redactor failure.
    prompt = "invariance: redactor down"
    real_redact = query_pipeline.redact
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
    monkeypatch.setattr(query_pipeline, "redact", _boom)
    response = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})
    assert response.status_code == 500, response.text
    seeded.append((_latest_id(), prompt))
    monkeypatch.setattr(query_pipeline, "redact", real_redact)

    assert len({audit_id for audit_id, _ in seeded}) == _EXPECTED_TOTAL
    return seeded


# --------------------------------------------------------------------------
# AC 3 -- /stats and summary_snapshot() count what they counted before
# --------------------------------------------------------------------------


def test_blocked_duplicates_counts_exactly_the_duplicate_blocked_rows(temp_db, monkeypatch):
    seeded = _seed_fixed_rows(monkeypatch)
    duplicate_block_id = seeded[1][0]

    with get_connection() as conn:
        flagged = [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM audit_logs WHERE was_duplicate_blocked = 1 ORDER BY id"
            ).fetchall()
        ]
    assert flagged == [duplicate_block_id]

    response = client.get("/stats", headers=_ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json()["blocked_duplicates"] == len(flagged) == _EXPECTED_BLOCKED_DUPLICATES

    # Not a proxy for "anything blocked" or "anything with a repeated hash":
    # María's row shares row 1's prompt_hash, and the pattern block and the
    # denial are blocks too -- none of them is counted.
    maria_success = get_audit_log(seeded[4][0])
    assert maria_success.prompt_hash == get_audit_log(seeded[0][0]).prompt_hash
    assert maria_success.was_duplicate_blocked is False
    assert get_audit_log(seeded[2][0]).was_duplicate_blocked is False
    assert get_audit_log(seeded[3][0]).was_duplicate_blocked is False


def test_stats_and_summary_snapshot_report_the_same_figures_on_the_fixed_seed(
    temp_db, monkeypatch
):
    _seed_fixed_rows(monkeypatch)

    response = client.get("/stats", headers=_ADMIN_HEADERS)
    snapshot = summary_snapshot()

    assert response.status_code == 200
    body = response.json()
    assert snapshot.errors == {}

    assert snapshot.total_recorded == _EXPECTED_TOTAL
    assert snapshot.blocked_duplicates == _EXPECTED_BLOCKED_DUPLICATES
    assert snapshot.blocked_suspicious == _EXPECTED_BLOCKED_SUSPICIOUS
    assert snapshot.unique_users == _EXPECTED_UNIQUE_USERS
    assert snapshot.successful_queries == _EXPECTED_SUCCESSFUL

    assert body["total_queries"] == snapshot.total_recorded
    assert body["blocked_duplicates"] == snapshot.blocked_duplicates
    assert body["blocked_suspicious"] == snapshot.blocked_suspicious
    assert body["unique_users"] == snapshot.unique_users
    assert body["success_rate"] == f"{_EXPECTED_SUCCESSFUL / _EXPECTED_TOTAL * 100:.1f}%"
    assert body["top_models"] == snapshot.top_models
    assert body["top_users"] == snapshot.top_users

    # StatsResponse's shape: no field added or removed by PRD-009.
    assert set(body) == {
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

    # The batched rows are the same AuditLog objects the standalone read returns
    # (see the module docstring on `_SUMMARY_SQL`'s dedup_key).
    assert snapshot.rows == list_audit_logs(limit=len(snapshot.rows))


def test_console_completion_numerator_still_counts_denials_as_success(temp_db, monkeypatch):
    """`chat_ui/chat_ui/admin_state.py::completion_figure` renders
    `successful_queries`, which counts `success = 1` -- every block and every
    policy denial included, because the pipeline logs them `success=True`.
    PRD-009 rewrote no row and changed no flag, so the console's figure keeps
    that meaning: the denial is still in the numerator."""
    seeded = _seed_fixed_rows(monkeypatch)

    denial = get_audit_log(seeded[3][0])

    assert denial.success is True
    assert denial.denied_permission == f"query:model:{_DISALLOWED_MODEL}"
    assert summary_snapshot().successful_queries == _EXPECTED_SUCCESSFUL


# --------------------------------------------------------------------------
# AC 3 -- /audit exposes no dedup_key, and prompt_hash keeps its meaning
# --------------------------------------------------------------------------


def test_audit_query_entry_has_no_dedup_key_d5(temp_db, monkeypatch):
    assert "dedup_key" not in AuditQueryEntry.model_fields
    assert "dedup_key" not in AuditRow.model_fields

    seeded = _seed_fixed_rows(monkeypatch)
    response = client.get("/audit", headers=_ADMIN_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == _EXPECTED_TOTAL
    assert len(body["queries"]) == _EXPECTED_TOTAL
    for entry in body["queries"]:
        assert "dedup_key" not in entry, entry

    # Absent by decision (D5), not because it is empty: every row the pipeline
    # wrote carries a key underneath.
    for audit_id, _ in seeded:
        assert get_audit_log(audit_id).dedup_key is not None, audit_id


def test_every_new_row_prompt_hash_is_the_raw_prompt_hash(temp_db, monkeypatch):
    seeded = _seed_fixed_rows(monkeypatch)
    response = client.get("/audit", headers=_ADMIN_HEADERS)
    assert response.status_code == 200
    audited = {entry["audit_id"]: entry for entry in response.json()["queries"]}

    for audit_id, prompt in seeded:
        assert get_audit_log(audit_id).prompt_hash == hash_prompt(prompt), audit_id
        assert audited[audit_id]["prompt_hash"] == hash_prompt(prompt), audit_id

    # prompt_hash stayed global evidence; only the key is per caller.
    juan, maria = get_audit_log(seeded[0][0]), get_audit_log(seeded[4][0])
    assert juan.prompt_hash == maria.prompt_hash
    assert juan.dedup_key != maria.dedup_key


# --------------------------------------------------------------------------
# AC 5 -- no added round trip on /query
# --------------------------------------------------------------------------


def test_successful_query_issues_one_duplicate_lookup_and_one_audit_insert(
    temp_db, monkeypatch
):
    """PRD-009 Section 11: the lookup stays one query; the key is computed in-process.

    **Only statements against `audit_logs` are counted.** `require_identity`
    resolves the bearer token against `users` first, and always did (the same
    reasoning as `tests/test_stats_router.py::
    test_stats_issues_one_database_round_trip_for_its_figures`).

    Before the epic (`57f2d67`), a successful `/query` issued the same two:
    `find_duplicate_timestamp`'s single `SELECT ... FROM audit_logs` and the
    success arm's one `insert_audit_log` INSERT. `dedup_key()` is pure, so
    rescoping the lookup added a predicate, not a statement.
    """
    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_success)
    query_pipeline.redact("warm up")

    statements = _count_audit_log_statements(monkeypatch)
    response = client.post(
        "/query", headers=_JUAN_HEADERS, json={"prompt": "invariance: counted round trips"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"
    assert statements, "the proxy captured nothing -- the patch did not take"

    audit = [sql for sql in statements if "audit_logs" in sql]
    assert len(audit) == 2, audit
    lookups = [sql for sql in audit if sql.lstrip().upper().startswith("SELECT")]
    inserts = [sql for sql in audit if sql.lstrip().upper().startswith("INSERT INTO AUDIT_LOGS")]
    assert len(lookups) == 1, audit
    assert len(inserts) == 1, audit
    assert "dedup_key = ?" in lookups[0], lookups[0]
