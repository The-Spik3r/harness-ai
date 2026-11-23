"""PRD-023 STORY-016: `/v1` alias resolution under the MCP mapping (D15, F9, Section 6.8).

The resolver, `evaluate_all(aliases=)`, the audit columns of an alias row and
`query_pipeline._alias_input` need no storage (`-m "not db"`). The step-7c test
at the end (buffered and PRD-021 real-time path) uses `temp_db`. The correlation
claim itself is `tests/test_mcp_correlation.py`.
"""

import ast
import dataclasses
import hashlib
import inspect
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

from types import MappingProxyType

import pytest

import app.db.database as database
from app.config import settings
from app.models.messages import ToolCallSpec
from app.services import action_config, authz, mcp_config, query_pipeline
from app.services.action_adapters import ToolCall
from app.services.action_audit import arguments_canonical_hash, canonical_json, decision_rows
from app.services.action_config import BUILT_IN_POLICY
from app.services.action_policy import AMBIGUOUS, AliasInput, evaluate, evaluate_all, resolve_v1_alias
from app.services.identity import Identity
from app.services.mcp_config import McpAuth, McpConfig, McpServer, Skill
from app.services.openrouter_client import ToolParams
from app.services.upstream import Finish, ToolCallDelta, UsageReport
from tests.test_query_pipeline_streaming import (  # noqa: F401  (`setup` is a fixture)
    _Recorder,
    _buffered,
    _run as _stream_run,
    _stream,
    setup,
)
# `setup` requests `provider_file`, a fixture of tests/_providers.py: it must be
# in this module's namespace too, or pytest cannot resolve it (PRD-023 STORY-016).
from tests._providers import provider_file  # noqa: F401  (fixture)

USER = Identity("u", "user")
_SERVER = "postgres-staging"
_RAW = "harness_postgres-staging__query"
_DROP = '{"sql": "DROP TABLE t"}'
_SELECT = '{"sql": "SELECT 1", "limit": 5}'
_POLICY = dataclasses.replace(
    BUILT_IN_POLICY,
    mcp_tools=MappingProxyType({_SERVER: MappingProxyType({"query": BUILT_IN_POLICY.tools["query"]})}),
)
_ALIASES = AliasInput(("harness_", "harness__"), {_SERVER: frozenset({"query"})})


def _one(name, arguments, aliases=_ALIASES, identity=USER):
    (d,) = evaluate_all([ToolCall("c1", name, arguments)], identity, _POLICY, aliases=aliases)
    return d


# --- the resolver -------------------------------------------------------------------


def test_resolver_splits_at_the_first_double_underscore_and_checks_visibility():
    vis = {_SERVER: frozenset({"query", "a__b"})}
    assert resolve_v1_alias(_RAW, ("harness_",), vis) == (_SERVER, "query")
    assert resolve_v1_alias("harness_postgres-staging__a__b", ("harness_",), vis) == (_SERVER, "a__b")
    assert resolve_v1_alias("harness_postgres-staging__other", ("harness_",), vis) is None
    assert resolve_v1_alias("harness_nowhere__query", ("harness_",), vis) is None
    assert resolve_v1_alias("query", ("harness_",), vis) is None
    # `harness__pg__q` against `harness_` leaves `_pg`, which is no server: no false ambiguity.
    assert resolve_v1_alias("harness__postgres-staging__query", ("harness_", "harness__"), vis) == (
        _SERVER, "query",
    )


def test_two_resolving_prefixes_are_ambiguous():
    vis = {"b_s": frozenset({"t"}), "s": frozenset({"t"})}
    assert resolve_v1_alias("a_b_s__t", ("a_", "a_b_"), vis) == AMBIGUOUS


def test_the_resolver_is_pure():
    tree = ast.parse(inspect.getsource(resolve_v1_alias))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & {"settings", "database", "mcp_config", "open"}


# --- evaluate_all(aliases=) ---------------------------------------------------------


def test_drop_table_alias_is_denied_sql_ddl_and_keeps_the_raw_name():
    d = _one(_RAW, _DROP)
    assert (d.decision, d.rule) == ("deny", "sql.ddl")
    assert d.tool_name == _RAW and d.tool_call_id == "c1" and d.mcp_server == _SERVER


def test_select_alias_is_released_and_the_row_carries_the_alias_columns():
    d = _one(_RAW, _SELECT)
    assert (d.decision, d.rule) == ("allow", "sql.read")
    (row,) = decision_rows([d], USER, "w")
    assert (row.surface, row.mcp_server, row.tool_name) == ("v1", _SERVER, _RAW)
    # The gateway hashes canonical_json(arguments); a shuffled key order is the same hash.
    shuffled = {"limit": 5, "sql": "SELECT 1"}
    assert row.arguments_canonical_hash == arguments_canonical_hash(shuffled)
    assert row.arguments_canonical_hash == hashlib.sha256(
        canonical_json(shuffled).encode("utf-8")
    ).hexdigest()


def test_empty_object_arguments_hash_like_an_absent_gateway_arguments():
    (row,) = decision_rows([_one(_RAW, "{}")], USER, "w")
    assert row.arguments_canonical_hash == arguments_canonical_hash({})


@pytest.mark.parametrize("arguments", ["", "not json", "[1]", "3", '{"sql": '])
def test_unparseable_or_non_object_arguments_hash_to_null(arguments):
    d = _one(_RAW, arguments)
    assert d.decision == "deny" and d.mcp_server == _SERVER
    (row,) = decision_rows([d], USER, "w")
    assert row.arguments_canonical_hash is None


def test_a_non_alias_decision_row_is_unchanged():
    (row,) = decision_rows([evaluate(ToolCall("c1", "query", _SELECT), USER, _POLICY)], USER, "w")
    assert (row.surface, row.mcp_server, row.arguments_canonical_hash) == ("v1", None, None)


def test_two_resolving_prefixes_are_tool_malformed():
    aliases = AliasInput(("a_", "a_b_"), {"b_s": frozenset({"t"}), "s": frozenset({"t"})})
    d = _one("a_b_s__t", "{}", aliases)
    assert (d.decision, d.rule, d.mcp_server, d.tool_name) == ("deny", "tool.malformed", None, "a_b_s__t")
    assert "ambiguous" in d.reason


def test_unresolved_invisible_and_hashed_names_are_todays_decision():
    for name in (
        "harness_postgres-staging__other",      # not a visible tool
        "harness_nowhere__query",               # not a server
        "harness_postgres-staging__qu_ab12cd",  # a client-truncated hashed name
        "query",
    ):
        d = _one(name, _SELECT)
        assert d == evaluate(ToolCall("c1", name, _SELECT), USER, _POLICY)
        assert d.mcp_server is None
    # A role that holds no skill sees nothing: the alias does not resolve.
    empty = AliasInput(("harness_",), {})
    assert _one(_RAW, _SELECT, empty) == evaluate(ToolCall("c1", _RAW, _SELECT), USER, _POLICY)
    assert _one(_RAW, _SELECT, empty).rule == "tool.unknown"


def test_aliases_none_is_todays_loop():
    calls = [ToolCall("c1", "query", _SELECT), ToolCall("c2", _RAW, _DROP)]
    assert evaluate_all(calls, USER, _POLICY, aliases=None) == evaluate_all(calls, USER, _POLICY)
    assert inspect.signature(evaluate_all).parameters["aliases"].kind is inspect.Parameter.KEYWORD_ONLY


def test_alias_resolution_adds_no_database_read(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("alias resolution must not touch the database")

    for name in ("get_connection", "_session", "_unit_of_work"):
        monkeypatch.setattr(database, name, boom)
    assert _one(_RAW, _SELECT).decision == "allow"
    _mcp_on(monkeypatch)
    assert query_pipeline._alias_input(USER) is not None


# --- step 7c wiring: `_alias_input` ----------------------------------------------------


def _mcp_on(monkeypatch, grants=("skill:s",)):
    server = McpServer(_SERVER, "http://127.0.0.1:9/mcp", True, McpAuth(type="none"), 30, 1_048_576)
    skill = Skill("s", "1.0.0", "d", "i", (f"{_SERVER}__query",), ())
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(
        mcp_config, "_config",
        McpConfig(servers={_SERVER: server}, skills=(skill,), v1_prefixes=("harness_",)),
    )
    monkeypatch.setattr(authz, "ROLE_PERMISSIONS", {"user": set(grants)})
    monkeypatch.setattr(action_config, "get_policy", lambda: _POLICY)


def test_mcp_disabled_passes_no_aliases_and_never_reads_mcp_config(monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", False)
    monkeypatch.setattr(
        mcp_config, "get_config", lambda: pytest.fail("mcp_config must not be read with MCP off (D20)")
    )
    assert query_pipeline._alias_input(USER) is None


def test_no_prefixes_means_no_aliases(monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(mcp_config, "_config", McpConfig())
    assert query_pipeline._alias_input(USER) is None


def test_alias_input_is_the_config_prefixes_and_the_callers_visible_set(monkeypatch):
    _mcp_on(monkeypatch)
    aliases = query_pipeline._alias_input(USER)
    assert aliases.prefixes == ("harness_",)
    assert dict(aliases.visible) == {_SERVER: frozenset({"query"})}
    monkeypatch.setattr(authz, "ROLE_PERMISSIONS", {"user": set()})
    assert dict(query_pipeline._alias_input(USER).visible) == {}


# --- step 7c, both paths (db) ---------------------------------------------------------

_OFFERED = ToolParams(tools=[{"type": "function", "function": {"name": _RAW, "parameters": {}}}])
_USAGE = UsageReport(prompt_tokens=3, completion_tokens=4, total_tokens=7)
_GRANTS = (authz.PERMISSION_QUERY_SUBMIT, authz.PERMISSION_STREAM_REALTIME, "skill:s")


def test_alias_call_is_decided_under_the_mcp_mapping_on_the_buffered_and_realtime_paths(setup, monkeypatch):
    setup(grants=_GRANTS)
    _mcp_on(monkeypatch, grants=_GRANTS)
    events = [
        ToolCallDelta(0, id="c1", name=_RAW, arguments='{"sql": "DROP '),
        ToolCallDelta(0, arguments='TABLE t"}'),
        Finish("tool_calls"), _USAGE,
    ]
    streamed = _stream_run(_Recorder(), prompt="drop one", stream=_stream(events), tools=_OFFERED)
    buffered = _stream_run(
        None, prompt="drop two",
        buffered=_buffered("", calls=(ToolCallSpec("c1", _RAW, _DROP),)),
        tools=_OFFERED,
    )
    for result in (streamed, buffered):
        (d,) = result.tool_outcome.decisions
        assert (d.decision, d.rule, d.tool_name, d.mcp_server) == ("deny", "sql.ddl", _RAW, _SERVER)
    with database.get_connection() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM action_decisions ORDER BY id")]
    assert len(rows) == 2
    for row in rows:
        assert (row["surface"], row["mcp_server"], row["tool_name"]) == ("v1", _SERVER, _RAW)
        assert row["arguments_canonical_hash"] == arguments_canonical_hash({"sql": "DROP TABLE t"})
