"""PRD-013 STORY-006: the eight audit fields on `GET /audit`, and the three
token and limit figures on `GET /stats`.

STORY-002 gave `audit_logs` the columns and STORY-005 made every pipeline arm
write them. Until this story they were readable only from inside the process.
These tests read them the way a compliance admin does, over HTTP, plus the
batched summary read both surfaces share, which went from ten figures to
thirteen.

The seeds are local rather than imported from `tests/test_db.py`, for the
reason `tests/test_audit_session_id.py` records: importing from a suite makes
any later edit there a failure here.

Offline like the rest of the suite: the only fixture is `temp_db` from
`tests/conftest.py`, and `call_openrouter` is always patched.
"""

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
    _session,
    _summary_figure_by_figure,
    count_audit_logs,
    count_blocked_duplicates,
    count_blocked_suspicious,
    count_blocked_usage_limits,
    count_pii_detected_queries,
    count_successful_queries,
    count_unique_users,
    get_audit_log,
    insert_audit_log,
    insert_user,
    list_audit_logs,
    sum_input_tokens,
    sum_output_tokens,
    summary_snapshot,
    top_models,
    top_pii_entities,
    top_users,
)
from app.db.models import AuditLog, User
from app.main import app
from app.services.identity import hash_token
from app.services.openrouter_client import OpenRouterResult

_ADMIN_HEADERS = {"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}

_AUTH_USER_ID = "dana@empresa.com"
_AUTH_TOKEN = "prd013-story006-user-token"
_AUTH_HEADERS = {"Authorization": f"Bearer {_AUTH_TOKEN}"}

client = TestClient(app)

_NEW_FIGURES = ("input_tokens", "output_tokens", "blocked_usage_limits")

_NULLABLE_FIELDS = (
    "ingress",
    "message_count",
    "input_tokens",
    "output_tokens",
    "conversation_key",
    "limit_exceeded",
)
_FLAG_FIELDS = ("streamed", "has_tool_calls")


def _audit_entries() -> list[dict]:
    response = client.get("/audit", headers=_ADMIN_HEADERS)
    assert response.status_code == 200
    return response.json()["queries"]


def _stats() -> dict:
    response = client.get("/stats", headers=_ADMIN_HEADERS)
    assert response.status_code == 200
    return response.json()


def _row(index: int, **fields) -> AuditLog:
    fields.setdefault("timestamp", f"2026-10-0{1 + index % 9}T10:00:0{index % 10}Z")
    fields.setdefault("user_id", "alice")
    fields.setdefault("prompt_hash", f"h{index}")
    return AuditLog(**fields)


def _seed_every_figure() -> None:
    """A table where every one of the thirteen figures is non-trivial.

    Two rows share a timestamp, as `tests/test_db.py`'s seed does, because a
    tie is where the batched read's ordered `json_group_array` would diverge
    from `list_audit_logs` first.
    """
    rows = [
        _row(0, timestamp="2026-10-09T10:00:00Z", model_used="gpt-4",
             pii_detected_input=True, pii_entities="PERSON,EMAIL_ADDRESS",
             input_tokens=2140, output_tokens=312, ingress="chat",
             message_count=3, conversation_key="ck-a"),
        _row(1, timestamp="2026-10-09T10:00:00Z", user_id="bob",
             model_used="gpt-4", was_duplicate_blocked=True, ingress="query",
             message_count=1),
        _row(2, timestamp="2026-10-08T10:00:00Z", model_used="claude-3",
             suspicious_pattern="injection", success=False,
             pii_detected_input=True, pii_entities="PERSON"),
        _row(3, timestamp="2026-10-07T10:00:00Z", user_id="carol",
             model_used="gpt-4", input_tokens=5, output_tokens=None),
        _row(4, timestamp="2026-10-06T10:00:00Z", user_id="bob",
             limit_exceeded="requests", ingress="chat"),
        _row(5, timestamp="2026-10-05T10:00:00Z", limit_exceeded="tokens",
             input_tokens=None, output_tokens=7),
    ]
    for row in rows:
        insert_audit_log(row)


def _individually(row_limit: int = 100, ranked_limit: int = 5) -> dict:
    """All thirteen figures read one function at a time: the oracle."""
    return {
        "rows": list_audit_logs(limit=row_limit),
        "total_recorded": count_audit_logs(),
        "blocked_duplicates": count_blocked_duplicates(),
        "blocked_suspicious": count_blocked_suspicious(),
        "unique_users": count_unique_users(),
        "successful_queries": count_successful_queries(),
        "pii_detected_queries": count_pii_detected_queries(),
        "top_models": top_models(limit=ranked_limit),
        "top_users": top_users(limit=ranked_limit),
        "top_pii_entities": top_pii_entities(limit=ranked_limit),
        "input_tokens": sum_input_tokens(),
        "output_tokens": sum_output_tokens(),
        "blocked_usage_limits": count_blocked_usage_limits(),
    }


def _direct(sql: str):
    with _session() as conn:
        return conn.execute(sql).fetchone()[0]


# --------------------------------------------------------------------------
# AC 1 and AC 2 -- /audit carries the eight fields
# --------------------------------------------------------------------------


def test_prd013_audit_entry_carries_all_eight_fields_as_stored(temp_db):
    """AC 1. Every value is distinct from its default, so a dropped
    passthrough line shows up as a default instead of passing silently."""
    insert_audit_log(
        _row(
            0,
            ingress="chat",
            message_count=3,
            input_tokens=2140,
            output_tokens=312,
            streamed=True,
            has_tool_calls=True,
            conversation_key="ck-0123456789abcdef",
            limit_exceeded="tokens",
        )
    )

    (entry,) = _audit_entries()

    assert entry["ingress"] == "chat"
    assert entry["message_count"] == 3
    assert entry["input_tokens"] == 2140
    assert entry["output_tokens"] == 312
    assert entry["streamed"] is True
    assert entry["has_tool_calls"] is True
    assert entry["conversation_key"] == "ck-0123456789abcdef"
    assert entry["limit_exceeded"] == "tokens"


def test_prd013_pre_prd_row_reports_null_fields_and_false_flags(temp_db):
    """AC 2. A default `AuditLog` leaves the six columns NULL and the two flags
    0, which is the state convergence leaves a pre-PRD-013 row in."""
    insert_audit_log(_row(0))

    (entry,) = _audit_entries()

    for name in _NULLABLE_FIELDS:
        assert name in entry, name
        assert entry[name] is None, name
    for name in _FLAG_FIELDS:
        assert entry[name] is False, name


@pytest.fixture
def sender(temp_db):
    insert_user(User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN)))
    return temp_db


def _fake_call_openrouter(messages, model="gpt-4", api_key=None):
    return OpenRouterResult(
        response="Here is the summary.",
        model_used=model,
        tokens_used=2452,
        input_tokens=2140,
        output_tokens=312,
    )


def test_prd013_a_pipeline_row_reads_back_what_story_005_wrote(sender, monkeypatch):
    """AC 1 over a row the pipeline wrote rather than one inserted by hand, and
    the `dedup_key` exclusion (PRD-009 D5) still holding on it."""
    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)

    response = client.post(
        "/query", json={"prompt": "summarise the Q3 vendor spend"}, headers=_AUTH_HEADERS
    )
    assert response.status_code == 200
    audit_id = response.json()["audit_id"]

    (entry,) = _audit_entries()
    stored = get_audit_log(audit_id)

    assert entry["audit_id"] == audit_id
    assert entry["ingress"] == "query" == stored.ingress
    assert entry["message_count"] == 1 == stored.message_count
    assert entry["input_tokens"] == 2140 == stored.input_tokens
    assert entry["output_tokens"] == 312 == stored.output_tokens
    assert entry["streamed"] is False
    assert entry["has_tool_calls"] is False
    assert entry["conversation_key"] is not None
    assert entry["conversation_key"] == stored.conversation_key
    assert entry["limit_exceeded"] is None

    assert stored.dedup_key is not None
    assert "dedup_key" not in entry


# --------------------------------------------------------------------------
# AC 3 -- /stats sums with NULL as 0 and counts usage-limit rows
# --------------------------------------------------------------------------


def test_prd013_token_totals_sum_with_null_as_zero(temp_db):
    for index, (tokens_in, tokens_out) in enumerate(
        [(100, 20), (None, None), (5, None), (None, 7)]
    ):
        insert_audit_log(_row(index, input_tokens=tokens_in, output_tokens=tokens_out))

    body = _stats()

    assert body["input_tokens"] == 105
    assert body["output_tokens"] == 27
    assert body["input_tokens"] == _direct(
        "SELECT COALESCE(SUM(input_tokens), 0) FROM audit_logs"
    ) == sum_input_tokens()
    assert body["output_tokens"] == _direct(
        "SELECT COALESCE(SUM(output_tokens), 0) FROM audit_logs"
    ) == sum_output_tokens()


def test_prd013_token_totals_are_zero_when_no_row_has_a_split(temp_db):
    """`SUM` over a column that is NULL on every row is NULL. The figure is 0."""
    insert_audit_log(_row(0))
    insert_audit_log(_row(1))

    body = _stats()

    assert body["input_tokens"] == 0
    assert body["output_tokens"] == 0


def test_prd013_new_figures_are_zero_on_an_empty_table(temp_db):
    body = _stats()

    for name in _NEW_FIGURES:
        assert body[name] == 0, name
    for name in _NEW_FIGURES:
        assert isinstance(body[name], int), name


def test_prd013_blocked_usage_limits_counts_rows_naming_a_limit(temp_db):
    for index, limit in enumerate(["requests", "tokens", None, None]):
        insert_audit_log(_row(index, limit_exceeded=limit, success=True))

    body = _stats()

    assert body["blocked_usage_limits"] == 2
    assert body["blocked_usage_limits"] == _direct(
        "SELECT COUNT(*) FROM audit_logs WHERE limit_exceeded IS NOT NULL"
    ) == count_blocked_usage_limits()


def test_prd013_blocked_usage_limits_is_zero_until_a_refusal_is_written(temp_db):
    """Today's value: no arm writes `limit_exceeded` until STORY-011."""
    insert_audit_log(_row(0))
    insert_audit_log(_row(1, was_duplicate_blocked=True))

    assert _stats()["blocked_usage_limits"] == 0


def test_prd013_stats_reports_the_batched_figures_unchanged(temp_db):
    """`/stats` takes the three figures from the same snapshot the console
    reads, through `row_limit=0`, not from a second read."""
    _seed_every_figure()

    body = _stats()
    snapshot = summary_snapshot()

    for name in _NEW_FIGURES:
        assert body[name] == snapshot.figures[name], name


# --------------------------------------------------------------------------
# AC 4 -- batched and figure-by-figure agree on all thirteen
# --------------------------------------------------------------------------


def test_prd013_summary_figures_are_the_ten_plus_three_in_order():
    assert len(SUMMARY_FIGURES) == 13
    assert SUMMARY_FIGURES[-3:] == _NEW_FIGURES


def test_prd013_batched_read_and_fallback_agree_on_all_thirteen(temp_db):
    _seed_every_figure()

    batched = summary_snapshot()
    fallback = _summary_figure_by_figure(100, 5, RuntimeError("not raised: no failure"))
    oracle = _individually()

    assert batched.errors == {}
    assert fallback.errors == {}
    assert set(batched.figures) == set(SUMMARY_FIGURES)
    for name in SUMMARY_FIGURES:
        assert batched.figures[name] == fallback.figures[name], name
        assert batched.figures[name] == oracle[name], name
    # Non-trivial on this seed, so the agreement is not 0 == 0.
    assert batched.input_tokens == 2145
    assert batched.output_tokens == 319
    assert batched.blocked_usage_limits == 2


def test_prd013_new_figures_have_the_standalone_type(temp_db):
    _seed_every_figure()

    snapshot = summary_snapshot()

    for name in _NEW_FIGURES:
        assert type(snapshot.figures[name]) is int, name
        assert type(getattr(snapshot, name)) is int, name


def test_prd013_snapshot_still_partitions_the_thirteen_exactly():
    SummarySnapshot(figures={name: 0 for name in SUMMARY_FIGURES}, errors={})

    for missing in _NEW_FIGURES:
        figures = {name: 0 for name in SUMMARY_FIGURES if name != missing}
        with pytest.raises(AssertionError):
            SummarySnapshot(figures=figures, errors={})


def test_prd013_limits_still_bind_to_their_own_columns(temp_db):
    """PRD Risk 8. The new columns take no parameter and come last, so the
    positional tuple still binds `row_limit` to `rows` and `ranked_limit` to the
    three rankings. Distinct limits make a misbinding visible, and the three
    new figures are whole-table values no limit touches."""
    _seed_every_figure()

    snapshot = summary_snapshot(row_limit=2, ranked_limit=1)

    assert snapshot.errors == {}
    assert snapshot.rows == list_audit_logs(limit=2)
    assert snapshot.top_models == top_models(limit=1)
    assert snapshot.top_users == top_users(limit=1)
    assert snapshot.top_pii_entities == top_pii_entities(limit=1)
    assert snapshot.input_tokens == sum_input_tokens() == 2145
    assert snapshot.output_tokens == sum_output_tokens() == 319
    assert snapshot.blocked_usage_limits == count_blocked_usage_limits() == 2


def test_prd013_one_bad_new_figure_fails_alone_and_stats_still_500s(temp_db, monkeypatch):
    _seed_every_figure()

    def boom(value):
        raise ValueError("bad input_tokens column")

    monkeypatch.setitem(database._SUMMARY_DECODERS, "input_tokens", boom)

    snapshot = summary_snapshot()

    assert set(snapshot.errors) == {"input_tokens"}
    assert snapshot.output_tokens == 319
    with pytest.raises(ValueError):
        snapshot.input_tokens

    raising_client = TestClient(app, raise_server_exceptions=False)
    response = raising_client.get("/stats", headers=_ADMIN_HEADERS)
    assert response.status_code == 500


# --------------------------------------------------------------------------
# The console's read table stays tied to the figures
# --------------------------------------------------------------------------


def test_prd013_console_read_table_matches_summary_figures():
    import chat_ui.chat_ui.admin_state as admin_state

    reads = admin_state._READS

    assert len(reads) == len(SUMMARY_FIGURES)
    assert tuple(field for field, _, _, _ in reads) == SUMMARY_FIGURES
    by_field = {field: fn for field, _, fn, _ in reads}
    assert by_field["input_tokens"] is sum_input_tokens
    assert by_field["output_tokens"] is sum_output_tokens
    assert by_field["blocked_usage_limits"] is count_blocked_usage_limits


def test_prd013_console_state_declares_the_three_figures_with_zero_defaults():
    from chat_ui.chat_ui.admin_state import AdminState

    for name in _NEW_FIGURES:
        assert name in AdminState.base_vars, name
        assert AdminState.get_fields()[name].default == 0, name
