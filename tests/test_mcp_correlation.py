"""PRD-023 STORY-016: the gateway's correlation claim (M7, D15, D21), `db` tests.

A `/v1` alias row is written the way step 8 writes it (`decision_rows` of an
`evaluate_all(aliases=)` decision) with an injected timestamp; the gateway's
pre-forward row is `record(mcp=McpRecord(link_candidates=...))`, which claims the
newest linkable alias row in the same statement as its own insert. Every test
uses `temp_db`; against libSQL they run in CI.
"""

import dataclasses
import threading
from datetime import datetime, timedelta, timezone
from types import MappingProxyType

import pytest

from app.db import database
from app.db.database import insert_action_decisions, insert_mcp_decision_linked, list_action_decisions
from app.services.action_adapters import ToolCall
from app.services.action_audit import (
    McpRecord,
    arguments_canonical_hash,
    canonical_json,
    decision_rows,
    record,
)
from app.services.action_config import BUILT_IN_POLICY
from app.services.action_policy import AliasInput, McpSurface, evaluate, evaluate_all
from app.services.identity import Identity

USER = Identity("u", "user")
OTHER = Identity("o", "user")
_SERVER = "postgres-staging"
_RAW = "harness_postgres-staging__query"
_NOW = datetime(2026, 11, 23, 12, 0, 0, tzinfo=timezone.utc)
_WINDOW = 300
_POLICY = dataclasses.replace(
    BUILT_IN_POLICY,
    mcp_tools=MappingProxyType({_SERVER: MappingProxyType({"query": BUILT_IN_POLICY.tools["query"]})}),
)
_ALIASES = AliasInput(("harness_",), {_SERVER: frozenset({"query"})})
_SELECT = {"sql": "SELECT 1"}


def _ts(seconds_before):
    return (_NOW - timedelta(seconds=seconds_before)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _v1_row(args=_SELECT, *, identity=USER, age=10, audit_id=None, name=_RAW, write_id="v1"):
    """One `/v1` alias row as step 8 builds it, aged `age` seconds before `_NOW`."""
    (d,) = evaluate_all([ToolCall("c", name, canonical_json(args))], identity, _POLICY, aliases=_ALIASES)
    (row,) = decision_rows([d], identity, write_id, audit_id)
    return dataclasses.replace(row, timestamp=_ts(age))


def _insert_v1(**kw):
    (row_id,) = insert_action_decisions([_v1_row(**kw)])
    return row_id


def _gateway(args=_SELECT, *, identity=USER, server=_SERVER, candidates=(_RAW,), window=_WINDOW, now=_NOW):
    d = evaluate(
        ToolCall("1", "query", canonical_json(args)), identity, _POLICY,
        surface=McpSurface(_SERVER, frozenset({"query"})),
    )
    mcp = McpRecord(
        surface="mcp", mcp_server=server, skills=("s@1.0.0",),
        arguments_canonical_hash=arguments_canonical_hash(args), linked_decision_id=None,
        mcp_config_digest="d" * 64, jsonrpc_id=1,
        link_candidates=tuple(candidates), link_window_seconds=window, link_now=now,
    )
    (row_id,) = record([d], identity, mcp=mcp)
    return row_id


def _by_id():
    return {r.id: r for r in list_action_decisions()}


def test_a_matching_alias_row_is_linked_with_its_audit_id(temp_db):
    v1 = _insert_v1(audit_id=None)
    gw = _gateway()
    assert _by_id()[gw].linked_decision_id == v1


def test_the_alias_rows_audit_id_is_copied(temp_db):
    with database.get_connection() as conn:
        audit_id = conn.execute(
            "INSERT INTO audit_logs (timestamp, user_id, prompt_hash) VALUES (?, 'u', 'h')",
            (_ts(10),),
        ).lastrowid
    v1 = _insert_v1(audit_id=audit_id)
    gw = _gateway()
    row = _by_id()[gw]
    assert (row.linked_decision_id, row.audit_id) == (v1, audit_id)


def test_outside_the_window_nothing_links(temp_db):
    _insert_v1(age=_WINDOW + 1)
    row = _by_id()[_gateway()]
    assert (row.linked_decision_id, row.audit_id) == (None, None)


def test_the_window_is_inclusive_and_zero_still_runs(temp_db):
    v1 = _insert_v1(age=_WINDOW)
    assert _by_id()[_gateway()].linked_decision_id == v1
    _insert_v1(age=0, write_id="v1b")
    assert _by_id()[_gateway(window=0, args=_SELECT)].linked_decision_id is not None


def test_different_arguments_do_not_link(temp_db):
    _insert_v1({"sql": "SELECT 2"})
    assert _by_id()[_gateway()].linked_decision_id is None


def test_a_denied_alias_row_is_never_linked(temp_db):
    _insert_v1({"sql": "DROP TABLE t"})
    assert _by_id()[_gateway({"sql": "DROP TABLE t"})].linked_decision_id is None


def test_another_users_alias_row_is_never_linked(temp_db):
    _insert_v1(identity=OTHER)
    assert _by_id()[_gateway()].linked_decision_id is None


def test_an_already_linked_alias_row_is_not_reused(temp_db):
    v1 = _insert_v1()
    first, second = _gateway(), _gateway()
    rows = _by_id()
    assert rows[first].linked_decision_id == v1
    assert rows[second].linked_decision_id is None


def test_the_newest_of_two_candidates_wins_then_the_older_is_used(temp_db):
    older = _insert_v1(age=30, write_id="o")
    newer = _insert_v1(age=5, write_id="n")
    first, second = _gateway(), _gateway()
    rows = _by_id()
    assert (rows[first].linked_decision_id, rows[second].linked_decision_id) == (newer, older)


def test_no_candidates_means_one_plain_insert_and_no_claim(temp_db, monkeypatch):
    _insert_v1()
    units = []
    real = database._unit_of_work

    def counting(name, kind, op):
        units.append(name)
        return real(name, kind, op)

    monkeypatch.setattr(database, "_unit_of_work", counting)
    gw = _gateway(candidates=(), server=None)
    assert units == ["insert_action_decisions"]
    assert _by_id()[gw].linked_decision_id is None


def test_a_claim_is_one_statement_unit(temp_db, monkeypatch):
    _insert_v1()
    units = []
    real = database._unit_of_work

    def counting(name, kind, op):
        units.append(name)
        return real(name, kind, op)

    monkeypatch.setattr(database, "_unit_of_work", counting)
    _gateway()
    assert units == ["insert_mcp_decision_linked"]


def test_a_replayed_write_id_returns_the_original_id_and_claims_nothing_more(temp_db):
    v1 = _insert_v1()
    d = evaluate(
        ToolCall("1", "query", canonical_json(_SELECT)), USER, _POLICY,
        surface=McpSurface(_SERVER, frozenset({"query"})),
    )
    (base,) = decision_rows([d], USER, "gw")
    row = dataclasses.replace(
        base, surface="mcp", mcp_server=_SERVER, arguments_canonical_hash=arguments_canonical_hash(_SELECT),
        timestamp=_ts(0),
    )
    first = insert_mcp_decision_linked(row, [_RAW], _WINDOW, now=_NOW)
    again = insert_mcp_decision_linked(row, [_RAW], _WINDOW, now=_NOW)
    assert first == again
    rows = _by_id()
    assert rows[first].linked_decision_id == v1
    assert sum(1 for r in rows.values() if r.surface == "mcp") == 1


def test_two_concurrent_gateway_calls_claim_one_alias_row_at_most_once(temp_db):
    v1 = _insert_v1()
    barrier = threading.Barrier(2)
    ids, errors = [], []

    def worker():
        try:
            barrier.wait(timeout=10)
            ids.append(_gateway())
        except BaseException as exc:  # surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not errors
    assert len(ids) == 2
    rows = _by_id()
    linked = [rows[i].linked_decision_id for i in ids]
    assert sorted(linked, key=lambda x: (x is None, x)) == [v1, None]
    assert sum(1 for r in rows.values() if r.linked_decision_id == v1) == 1
