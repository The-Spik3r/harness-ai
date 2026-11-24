"""PRD-023 STORY-008: the gateway audit columns, `record(mcp=)`, `record_outcome`
and the `/v1` correlation lookup (D9, D21, T9, T14).

The tests that need no storage run without Docker (`-m "not db"`); the ones
using `temp_db` run against the libSQL dev server like the rest of the suite.
"""

import dataclasses
import hashlib
import inspect
import json
import logging
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import get_args

import pytest

from app.db import database
from app.db.database import (
    find_linkable_v1_decision,
    get_connection,
    init_db,
    insert_action_decisions,
    list_action_decisions,
)
from app.db.errors import StorageUnavailableError
from app.db.models import MCP_OUTCOME_VALUES, ActionDecisionRow, McpOutcome
from app.services import action_audit
from app.services.action_adapters import ToolCall
from app.services.action_audit import (
    McpRecord,
    arguments_canonical_hash,
    canonical_json,
    decision_rows,
    record,
    record_outcome,
)
from app.services.action_config import BUILT_IN_POLICY
from app.services.action_policy import evaluate
from app.services.identity import Identity

USER = Identity("u", "user")
_NOW = datetime(2026, 11, 22, 12, 0, 0, tzinfo=timezone.utc)


def _decision(call_id="c1"):
    return evaluate(
        ToolCall(call_id, "query", json.dumps({"sql": "SELECT 1"})), USER, BUILT_IN_POLICY
    )


def _mcp(**over):
    base = dict(
        surface="mcp",
        mcp_server="github",
        skills=("a@1.0.0", "b@2.1.0"),
        arguments_canonical_hash="h" * 64,
        linked_decision_id=None,
        mcp_config_digest="d" * 64,
        jsonrpc_id=7,
    )
    base.update(over)
    return McpRecord(**base)


# --- vocabulary and hashing -------------------------------------------------


def test_the_outcome_literal_and_tuple_agree_and_are_the_six_names():
    assert get_args(McpOutcome) == MCP_OUTCOME_VALUES
    assert MCP_OUTCOME_VALUES == (
        "ok", "tool_error", "upstream_error", "timeout",
        "result_too_large", "result_blocked",
    )


def test_canonical_json_sorts_keys_drops_whitespace_and_keeps_non_ascii():
    assert canonical_json({"b": 1, "a": {"z": "ñ", "y": [1, 2]}}) == (
        '{"a":{"y":[1,2],"z":"ñ"},"b":1}'
    )


def test_the_canonical_hash_ignores_key_order_and_is_sha256_of_the_utf8_text():
    one = arguments_canonical_hash({"a": 1, "b": "ñ"})
    two = arguments_canonical_hash({"b": "ñ", "a": 1})
    assert one == two
    assert one == hashlib.sha256('{"a":1,"b":"ñ"}'.encode("utf-8")).hexdigest()


# --- McpRecord and record(mcp=) --------------------------------------------


def test_mcp_record_is_frozen_and_only_the_mcp_surface_is_allowed():
    rec = _mcp()
    with pytest.raises(dataclasses.FrozenInstanceError):
        rec.mcp_server = "x"
    with pytest.raises(ValueError):
        _mcp(surface="v1")


def test_record_mcp_rejects_a_ref_a_session_and_a_batch(monkeypatch):
    monkeypatch.setattr(
        action_audit, "insert_action_decisions",
        lambda rows: pytest.fail("nothing may be written"),
    )
    ref = action_audit.AuditRef(audit_id=1, write_id="w")
    with pytest.raises(ValueError):
        record([_decision()], USER, audit_ref=ref, mcp=_mcp())
    with pytest.raises(ValueError):
        record([_decision()], USER, session_id="s", mcp=_mcp())
    with pytest.raises(ValueError):
        record([_decision("a"), _decision("b")], USER, mcp=_mcp())
    with pytest.raises(ValueError):
        record([], USER, mcp=_mcp())


def test_record_mcp_storage_error_propagates_and_never_journals(monkeypatch):
    def boom(rows):
        raise StorageUnavailableError("down", 1)

    monkeypatch.setattr(action_audit, "insert_action_decisions", boom)
    monkeypatch.setattr(
        action_audit.audit_journal, "append",
        lambda *a, **k: pytest.fail("a gateway row is never journaled (T9)"),
    )
    with pytest.raises(StorageUnavailableError):
        record([_decision()], USER, mcp=_mcp())


@pytest.mark.parametrize("jsonrpc_id,expected", [(7, "mcp:7"), ("abc", "mcp:abc")])
def test_record_mcp_row_fields(monkeypatch, jsonrpc_id, expected):
    seen = []

    def fake(rows):
        seen.extend(rows)
        return [41]

    monkeypatch.setattr(action_audit, "insert_action_decisions", fake)
    ids = record(
        [_decision()], USER,
        mcp=_mcp(jsonrpc_id=jsonrpc_id, linked_decision_id=5, audit_id=9),
    )

    assert ids == [41]
    (row,) = seen
    assert row.tool_call_id == expected
    assert row.session_id is None and row.audit_id == 9
    assert row.surface == "mcp" and row.mcp_server == "github"
    assert row.skills == '["a@1.0.0","b@2.1.0"]'
    assert row.arguments_canonical_hash == "h" * 64
    assert row.linked_decision_id == 5 and row.mcp_config_digest == "d" * 64
    assert row.write_id is not None
    assert row.outcome is None and row.duration_ms is None


def test_record_without_mcp_builds_the_same_rows_as_decision_rows(monkeypatch):
    seen = []
    monkeypatch.setattr(
        action_audit, "insert_action_decisions", lambda rows: seen.extend(rows) or [1]
    )
    monkeypatch.setattr(action_audit, "_new_write_id", lambda: "wid")
    d = _decision()
    record([d], USER)
    (expected,) = decision_rows([d], USER, "wid", None, None)
    assert dataclasses.replace(seen[0], timestamp="t") == dataclasses.replace(
        expected, timestamp="t"
    )
    assert seen[0].surface == "v1" and seen[0].mcp_server is None


# --- record_outcome ---------------------------------------------------------


def test_record_outcome_signature_has_no_content_parameter():
    params = list(inspect.signature(record_outcome).parameters)
    assert params == [
        "row_id", "outcome", "duration_ms", "result_bytes",
        "result_hash", "result_flags", "user_id",
    ]
    assert inspect.signature(record_outcome).parameters["user_id"].kind is (
        inspect.Parameter.KEYWORD_ONLY
    )


def test_record_outcome_rejects_an_unknown_outcome_without_writing(monkeypatch, caplog):
    monkeypatch.setattr(
        action_audit, "update_action_outcome",
        lambda *a: pytest.fail("an unknown outcome must not be written"),
    )
    with caplog.at_level(logging.ERROR, logger=action_audit.logger.name):
        record_outcome(12, "exploded", 1, 2, "h", [], user_id="ana")
    assert any(
        r.levelno == logging.ERROR and "ana" in r.getMessage() and "12" in r.getMessage()
        for r in caplog.records
    )


@pytest.mark.parametrize(
    "error", [StorageUnavailableError("down", 1), RuntimeError("secret")]
)
def test_record_outcome_swallows_a_failed_update_and_logs_without_the_message(
    monkeypatch, caplog, error
):
    def boom(*a):
        raise error

    monkeypatch.setattr(action_audit, "update_action_outcome", boom)
    with caplog.at_level(logging.ERROR, logger=action_audit.logger.name):
        assert record_outcome(12, "ok", 1, 2, "h", ["f"], user_id="ana") is None
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "ana" in text and "12" in text and "secret" not in text


def test_record_outcome_passes_flag_names_as_a_json_array(monkeypatch):
    calls = []
    monkeypatch.setattr(action_audit, "update_action_outcome", lambda *a: calls.append(a))
    record_outcome(3, "result_blocked", 10, 20, "rh", ["injection", "secret"], user_id="u")
    assert calls == [(3, "result_blocked", 10, 20, "rh", '["injection","secret"]')]


def test_record_outcome_stores_dict_flags_as_json_with_sorted_keys(monkeypatch):
    # PRD-023 STORY-014 (T14): flags may be small dicts naming a list and a pattern index.
    calls = []
    monkeypatch.setattr(action_audit, "update_action_outcome", lambda *a: calls.append(a))
    record_outcome(
        4, "ok", 1, 2, "h", [{"pattern_id": 0, "list": "injection"}, {"uninspected": 2}], user_id="u"
    )
    assert calls == [(4, "ok", 1, 2, "h", '[{"list":"injection","pattern_id":0},{"uninspected":2}]')]


def test_find_linkable_v1_decision_signature():
    sig = inspect.signature(find_linkable_v1_decision)
    assert list(sig.parameters) == [
        "user_id", "server", "tool_names", "arguments_canonical_hash",
        "window_seconds", "now",
    ]
    assert sig.parameters["now"].kind is inspect.Parameter.KEYWORD_ONLY


def test_find_linkable_with_no_candidate_names_returns_none_without_a_query(monkeypatch):
    monkeypatch.setattr(
        database, "_unit_of_work", lambda *a, **k: pytest.fail("no query expected")
    )
    assert find_linkable_v1_decision("u", "s", [], "h", 60, now=_NOW) is None


# --- storage (db) -----------------------------------------------------------


def _row(**over):
    base = dict(
        timestamp=_NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), audit_id=None, session_id=None,
        user_id="u", role="user", tool_call_id="c", tool_name="harness_github__pr",
        operation_kind=None, target_preview=None, arguments_hash="a",
        arguments_preview=None, decision="allow", rule="r", reason="w",
        granted_by=None, classifications="[]", policy_digest="d",
        mcp_server="github", arguments_canonical_hash="h",
    )
    base.update(over)
    return ActionDecisionRow(**base)


def _ts(seconds_before):
    return (_NOW - timedelta(seconds=seconds_before)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _find(**over):
    args = dict(
        user_id="u", server="github", tool_names=["harness_github__pr"],
        arguments_canonical_hash="h", window_seconds=60, now=_NOW,
    )
    args.update(over)
    return find_linkable_v1_decision(
        args.pop("user_id"), args.pop("server"), args.pop("tool_names"),
        args.pop("arguments_canonical_hash"), args.pop("window_seconds"), **args,
    )


def test_the_link_index_covers_user_and_canonical_hash(temp_db):
    with get_connection() as conn:
        cols = [
            r["name"]
            for r in conn.execute("PRAGMA index_info(idx_action_decisions_link)")
        ]
    assert cols == ["user_id", "arguments_canonical_hash"]


def test_a_fresh_database_has_the_eleven_columns(temp_db):
    with get_connection() as conn:
        names = {r["name"] for r in conn.execute("PRAGMA table_info(action_decisions)")}
    assert {
        "surface", "mcp_server", "skills", "arguments_canonical_hash",
        "linked_decision_id", "outcome", "duration_ms", "result_bytes",
        "result_hash", "result_flags", "mcp_config_digest",
    } <= names


def test_a_legacy_row_reads_as_surface_v1_and_the_rest_null(uninitialized_db):
    from tests.test_db_resilience_write_id import _build_pre_prd018_database

    _build_pre_prd018_database()
    init_db()
    (row,) = list_action_decisions()
    assert row.surface == "v1"
    assert row.mcp_server is None and row.outcome is None and row.skills is None


def test_an_mcp_row_round_trips_through_list_action_decisions(temp_db):
    (row_id,) = record([_decision()], USER, mcp=_mcp(linked_decision_id=3))
    (row,) = list_action_decisions()
    assert row.id == row_id and row.surface == "mcp"
    assert row.mcp_server == "github" and row.skills == '["a@1.0.0","b@2.1.0"]'
    assert row.linked_decision_id == 3 and row.tool_call_id == "mcp:7"
    assert row.outcome is None


def test_record_outcome_updates_its_own_row_only(temp_db):
    a, b = insert_action_decisions([_row(), _row()])
    record_outcome(a, "ok", 12, 34, "rh", ["x"], user_id="u")
    rows = {r.id: r for r in list_action_decisions()}
    assert (rows[a].outcome, rows[a].duration_ms, rows[a].result_bytes) == ("ok", 12, 34)
    assert rows[a].result_hash == "rh" and rows[a].result_flags == '["x"]'
    assert rows[b].outcome is None and rows[b].result_flags is None


def test_updating_a_missing_row_is_silent(temp_db):
    record_outcome(9999, "ok", 1, 1, "h", [], user_id="u")


def test_correlation_returns_the_newest_match_and_none_when_nothing_matches(temp_db):
    older, newer = insert_action_decisions([_row(timestamp=_ts(30)), _row(timestamp=_ts(5))])
    assert _find().id == newer
    assert _find(arguments_canonical_hash="nope") is None


def test_correlation_ignores_every_non_matching_row(temp_db):
    insert_action_decisions(
        [
            _row(decision="deny"),
            _row(user_id="other"),
            _row(mcp_server="gitlab"),
            _row(tool_name="harness_github__other"),
            _row(arguments_canonical_hash="x"),
            _row(surface="mcp"),
            _row(timestamp=_ts(61)),
        ]
    )
    assert _find() is None


def test_correlation_window_boundary_flag_and_candidate_names(temp_db):
    (edge,) = insert_action_decisions([_row(timestamp=_ts(60), decision="flag")])
    assert _find().id == edge  # exactly window_seconds old still qualifies
    assert _find(window_seconds=59) is None
    (alias,) = insert_action_decisions([_row(tool_name="harness__github__pr")])
    assert _find(tool_names=["harness__github__pr", "harness_github__pr"]).id == alias
    assert _find(tool_names=[]) is None


def test_correlation_skips_a_row_already_linked(temp_db):
    (target,) = insert_action_decisions([_row()])
    insert_action_decisions([_row(surface="mcp", linked_decision_id=target)])
    assert _find() is None
