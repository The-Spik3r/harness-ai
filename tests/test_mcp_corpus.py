"""PRD-023 STORY-019: the MCP decision corpus runs against the real gateway and the stub (F12, Section 11).

`tests/corpora/mcp/calls/*.yaml` (loader and fixed setup: `tests/mcp_corpus.py`).
Each file is one call with the decision and the outcome it must produce for every
role it names. The MVP definition of Section 11 is these tests: every declared
decision and outcome holds, no denied call moves the stub's counter, and every
forwarded call has its decision row before the stub sees it.

Three runners, one corpus:

- `test_call_decides_as_declared` (`-m "not db"`, runs everywhere): the real `/mcp`
  router, `mcp_gateway.call` and the real stub subprocess, with `action_audit.record` /
  `record_outcome` replaced by recorders (the harness of `tests/test_mcp_tools_call.py`).
  "The row exists" is "`record` ran before `call_tool`".
- `test_call_decides_as_declared_db` (`db`, CI): the same checks against the real
  `action_decisions` rows, read inside the `call_tool` seam (so before the stub sees the
  call). All roles of one file share one test: the database reset is the slow part.
- `test_correlation_case_db` (`db`, CI): seeds the `/v1` alias row, then makes the gateway call.

`via: v1` calls are decided at step 7c (`evaluate_all(aliases=)`), never forwarded, and need no
storage, so `test_alias_case_decides_as_declared` runs locally. One stub serves the module.
"""

import contextlib
import dataclasses
import json
import os
import time
from datetime import datetime, timedelta, timezone

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.db import database
from app.routers import mcp as mcp_router
from app.services import (
    action_audit,
    action_config,
    action_policy,
    mcp_config,
    mcp_gateway,
    mcp_upstream,
    query_pipeline,
    strict_json,
    usage_limits,
)
from app.services.action_adapters import ToolCall
from app.services.mcp_upstream import CallOutcome
from app.services.tool_release import DENIAL_NOTE_TEMPLATE, NOTE_FIELD_CAP
from tests import mcp_corpus as mc
from tests.mcp_stub import start_stub
from tests.test_action_corpus import CorpusError

_CORPUS = mc.load_corpus()
_GATEWAY = [c for c in _CORPUS if c.via == "mcp" and c.category != "correlation"]
_ALIAS = [c for c in _CORPUS if c.via == "v1"]
_CORRELATION = [c for c in _CORPUS if c.category == "correlation"]
_PAIRS = [(c, role) for c in _GATEWAY for role in c.roles]
_ALIAS_PAIRS = [(c, role) for c in _ALIAS for role in c.roles]

#: The in-process faults of `fault:` (the stub has no trigger for them).
_FAULTS = {
    "tool_error": CallOutcome("error", is_error=True, content=[{"type": "text", "text": "the tool said no"}]),
    "upstream_error": CallOutcome("upstream_error", detail="slow on stub: connection refused; it may have run"),
    "image_result": CallOutcome("ok", content=[{"type": "image", "data": "AAAA", "mimeType": "image/png"}]),
}

#: The fixed instant of the correlation window (`mcp_gateway._link_clock` is patched to it).
_NOW = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)


def _ids(pairs):
    return [f"{item[0].stem}-{item[1]}" if isinstance(item, tuple) else item.stem for item in pairs]


@pytest.fixture(scope="module")
def corpus_stub(tmp_path_factory):
    """One stub for the module; each test resets its counters and stops nothing."""
    handle = start_stub(tmp_path_factory.mktemp("mcp-corpus-stub"))
    try:
        yield handle
    finally:
        handle.stop()


# --- the world one call runs in ----------------------------------------------------


class Evidence:
    """What the call path did, observed at the seams the corpus asserts on.

    Two row sources behind one `row()`: the recorders (`db=False`) or the real
    `action_decisions` table (`db=True`). `current` is the `tool_call_id` of the
    request being made; `call_tool` records, on entry, whether that call's decision
    row already existed (evidence before effect, T9).
    """

    def __init__(self, db: bool):
        self.db = db
        self.current = None
        self.entered = []  # (tool_call_id, row existed when the forward began)
        self._rows = {}
        self._ids = {}

    # recorders (db=False)
    def record(self, decisions, identity, *args, mcp=None, **kwargs):
        (d,) = decisions
        row_id = len(self._ids) + 1
        key = f"mcp:{mcp.jsonrpc_id}"
        self._ids[row_id] = key
        self._rows[key] = {
            "decision": d.decision, "rule": d.rule, "reason": d.reason, "granted_by": d.granted_by,
            "surface": mcp.surface, "mcp_server": mcp.mcp_server, "outcome": None, "result_flags": None,
            "result_bytes": None, "result_hash": None, "linked_decision_id": None, "audit_id": None,
        }
        return [row_id]

    def record_outcome(self, row_id, outcome, duration_ms, size, digest, flags, *, user_id):
        self._rows[self._ids[row_id]].update(
            outcome=outcome, result_flags=list(flags), result_bytes=size, result_hash=digest
        )

    def exists(self, call_id: str) -> bool:
        if not self.db:
            return call_id in self._rows
        with database.get_connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) AS n FROM action_decisions WHERE tool_call_id = ?", (call_id,)
            ).fetchone()["n"] > 0

    def row(self, call_id: str) -> dict:
        if not self.db:
            return self._rows[call_id]
        with database.get_connection() as conn:
            rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM action_decisions WHERE tool_call_id = ?", (call_id,)
                ).fetchall()
            ]
        assert len(rows) == 1, f"{call_id}: expected one decision row, found {len(rows)}"
        row = rows[0]
        if row["result_flags"] is not None:
            row["result_flags"] = json.loads(row["result_flags"])
        return row


def _install(monkeypatch, case, evidence: Evidence) -> None:
    """The seams: admit, the row writers (recorders only without a database) and `call_tool`."""
    monkeypatch.setattr(
        usage_limits, "admit", lambda identity, charges_budget: usage_limits.Admission(day="2026-11-24")
    )
    if not evidence.db:
        monkeypatch.setattr(action_audit, "record", evidence.record)
        monkeypatch.setattr(action_audit, "record_outcome", evidence.record_outcome)
    real_call_tool = mcp_upstream.call_tool
    fault = _FAULTS.get(case.fault) if case.fault else None

    async def call_tool(server, user_id, tool, arguments=None, **kwargs):
        evidence.entered.append((evidence.current, evidence.exists(evidence.current)))
        if fault is not None:
            return fault
        return await real_call_tool(server, user_id, tool, arguments, **kwargs)

    monkeypatch.setattr(mcp_upstream, "call_tool", call_tool)
    monkeypatch.setattr("app.middleware.auth.resolve", mc.IDENTITIES.get)


@contextlib.contextmanager
def _serving():
    app = FastAPI()
    app.include_router(mcp_router.router)
    with TestClient(app) as test_client:
        try:
            yield test_client
        finally:
            test_client.portal.call(mcp_upstream.aclose_all)


def _post(client, role, name, arguments, rpc_id):
    return client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": rpc_id, "method": "tools/call", "params": {"name": name, "arguments": arguments}},
        headers={"Authorization": f"Bearer {role}", "Content-Type": "application/json"},
    )


def _stub_total(stub) -> int:
    return sum(stub.stats()["calls"].values())


def _expected_text(kind, case, role, rpc_id, row):
    name, call_id = case.name[:NOTE_FIELD_CAP], str(rpc_id)
    if kind == "denied":
        return DENIAL_NOTE_TEMPLATE.format(name=name, id=call_id, reason=row["reason"])
    if kind == "timeout":
        return mcp_gateway.TIMEOUT_TEXT.format(name=name, id=call_id, n=mc.TIMEOUT_SECONDS)
    if kind == "upstream_error":
        return mcp_gateway.UPSTREAM_ERROR_TEXT.format(name=name, id=call_id, server=case.server)
    if kind == "too_large":
        return mcp_gateway.RESULT_TOO_LARGE_TEXT.format(name=name, id=call_id, n=mc.MAX_RESULT_BYTES)
    if kind == "blocked":
        return mcp_gateway.RESULT_BLOCKED_TEXT.format(name=name, id=call_id)
    return None


def _run_role(client, evidence: Evidence, stub, case, role) -> dict:
    """One call as `role`; asserts the declared decision, outcome, reply, evidence and stub counter.

    Returns the decision row (for the correlation assertions).
    """
    rpc_id = mc.JSONRPC_IDS[role]
    call_id = f"mcp:{rpc_id}"
    evidence.current = call_id
    entered_before = len(evidence.entered)
    stub_before = _stub_total(stub)

    response = _post(client, role, case.name, case.arguments_object(), rpc_id)
    assert response.status_code == 200, (case.stem, role, response.text)

    decision, outcome = case.expect[role], case.outcome[role]
    forwarded = decision in ("allow", "flag")
    expect_stub = 1 if forwarded and case.fault is None else 0
    deadline = time.monotonic() + 10
    while _stub_total(stub) - stub_before < expect_stub and time.monotonic() < deadline:
        time.sleep(0.1)  # a timed-out `slow` counts when its body starts, which can trail the reply

    # AC2: a denied call never moves the stub; a forwarded one entered the upstream seam once.
    assert _stub_total(stub) - stub_before == expect_stub, (case.stem, role)
    forwards = evidence.entered[entered_before:]
    assert len(forwards) == (1 if forwarded else 0), (case.stem, role, "forward count")
    # AC2: the row existed before the stub could see the call (T9).
    assert all(existed for _, existed in forwards), (case.stem, role, "row written before the forward")

    row = evidence.row(call_id)
    assert (row["decision"], row["rule"]) == (decision, case.rule[role]), (case.stem, role)
    assert row["granted_by"] == case.granted_by.get(role), (case.stem, role)
    assert row["outcome"] == outcome, (case.stem, role)
    assert (row["surface"], row["mcp_server"]) == ("mcp", case.server), (case.stem, role)
    if outcome is not None and case.flags is not None:
        assert mc.normalise_flags(row["result_flags"]) == mc.normalise_flags(case.flags), (case.stem, role)
    if outcome in ("ok", "tool_error", "result_too_large", "result_blocked"):
        # Size and hash of the upstream result are kept; the result itself never is (T14).
        assert row["result_bytes"] and len(row["result_hash"]) == 64, (case.stem, role)

    kind = mc.reply_kind(case, role)
    if kind == "not_callable":
        assert response.json()["error"] == {"code": -32602, "message": mcp_gateway.UNKNOWN_TOOL_MESSAGE}
        return row
    result = response.json()["result"]
    text = _expected_text(kind, case, role, rpc_id, row)
    if text is not None:
        assert result == {"content": [{"type": "text", "text": text}], "isError": True}, (case.stem, role)
    else:
        assert result["isError"] is (outcome == "tool_error"), (case.stem, role)
    return row


def _prepare(monkeypatch, tmp_path, stub, case, *, db, prefixes=(), mcp_enabled=False) -> Evidence:
    stub.reset()
    mc.configure(
        monkeypatch, tmp_path, stub.url, rbac=case.rbac, patterns=case.patterns, prefixes=prefixes,
        mcp_enabled=mcp_enabled,
    )
    evidence = Evidence(db)
    _install(monkeypatch, case, evidence)
    return evidence


# --- loader ------------------------------------------------------------------------


def test_the_corpus_holds_at_least_30_calls_covering_every_class():
    assert len(_CORPUS) >= 30
    assert {c.category for c in _CORPUS} == set(mc.CATEGORIES)
    assert {d for c in _CORPUS for d in c.expect.values()} == {"allow", "deny", "flag"}
    # Every outcome of the closed vocabulary, and the never-forwarded NULL.
    assert {o for c in _CORPUS for o in c.outcome.values()} == {None, *mc.OUTCOMES}
    assert {role for c in _CORPUS for role in c.roles} == set(mc.ROLES)
    assert {c.via for c in _CORPUS} == {"mcp", "v1"}
    assert {c.name for c in _ALIAS} >= {"harness_stub__query", "harness__stub__query"}
    assert len(_CORRELATION) >= 6


def test_the_four_mvp_goal_calls_are_present_verbatim():
    by_stem = {c.stem: c for c in _CORPUS}
    drop = by_stem["brief-drop-table"]
    assert (drop.name, drop.arguments) == ("stub__query", '{"sql":"DROP TABLE users"}')
    assert (drop.expect["dev"], drop.rule["dev"]) == ("deny", "sql.ddl")
    assert (drop.expect["dba"], drop.granted_by["dba"], drop.outcome["dba"]) == ("allow", "action:sql:ddl", "ok")
    workflow = by_stem["brief-push-files-workflow"]
    assert workflow.name == "stub__push_files"
    assert workflow.arguments_object()["files"][0]["path"] == ".github/workflows/ci.yml"
    assert (workflow.expect["dev"], workflow.rule["dev"]) == ("deny", "fs.write_protected")
    clean = by_stem["brief-push-files-clean"]
    assert clean.name == "stub__push_files" and clean.expect["dev"] == "allow"
    assert all(not f["path"].startswith(".github/") for f in clean.arguments_object()["files"])
    pull = by_stem["brief-create-pull-request-opaque"]
    assert (pull.name, pull.expect["dev"], pull.rule["dev"]) == ("stub__create_pull_request", "flag", "tool.opaque")


def test_a_file_is_named_by_its_category_and_marks_what_a_client_cannot_replay():
    for case in _CORPUS:
        assert case.stem.startswith(case.category + "-"), case.stem
        if case.fault or case.via == "v1" or case.category == "correlation" or "timeout" in case.outcome.values():
            assert case.e2e is False, case.stem
        for role in case.granted_by:
            assert case.expect[role] == "allow", case.stem


def test_a_missing_corpus_directory_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="MCP corpus directory not found"):
        mc.load_corpus(tmp_path / "nope")


_VALID = """\
tool_call:
  name: stub__query
  arguments: '{"sql":"SELECT 1"}'
server: stub
category: brief
expect: {dev: allow}
outcome: {dev: ok}
rule: sql.read
note: ok
"""

_BAD_DOCUMENTS = [
    ("not a mapping", "- a\n- b\n", "file", "must be a mapping"),
    ("unknown key", _VALID + "extra: 1\n", "extra", "unknown key"),
    ("missing key", _VALID.replace("rule: sql.read\n", ""), "rule", "required key is missing"),
    ("bad category", _VALID.replace("brief", "other"), "category", "is not one of"),
    ("bad server", _VALID.replace("server: stub", "server: elsewhere"), "server", "is not 'stub' or null"),
    ("bad role", _VALID.replace("expect: {dev: allow}", "expect: {admin: allow}"), "expect", "is not one of"),
    ("bad decision", _VALID.replace("expect: {dev: allow}", "expect: {dev: maybe}"), "expect.dev", "is not one of"),
    ("bad rule id", _VALID.replace("rule: sql.read", "rule: sql.nope"), "rule.dev", "is not one of"),
    ("bad outcome", _VALID.replace("outcome: {dev: ok}", "outcome: {dev: lost}"), "outcome.dev", "is not one of"),
    ("outcome roles differ", _VALID.replace("outcome: {dev: ok}", "outcome: {dba: ok}"), "outcome", "exactly the roles"),
    (
        "denied call with an outcome",
        _VALID.replace("expect: {dev: allow}", "expect: {dev: deny}"),
        "outcome.dev",
        "must be null",
    ),
    ("granted_by on a deny", _VALID.replace("expect: {dev: allow}", "expect: {dev: deny}").replace("outcome: {dev: ok}", "outcome: {dev: null}") + "granted_by: {dev: 'action:sql:ddl'}\n", "granted_by.dev", "allow"),
    ("arguments not JSON", _VALID.replace("""'{"sql":"SELECT 1"}'""", "'not json'"), "tool_call.arguments", "not valid JSON"),
    ("arguments not an object", _VALID.replace("""'{"sql":"SELECT 1"}'""", "'[1]'"), "tool_call.arguments", "JSON object"),
    ("arguments not a string", _VALID.replace("""'{"sql":"SELECT 1"}'""", "{sql: x}"), "tool_call.arguments", "must be a string"),
    ("bad fault", _VALID + "fault: meltdown\n", "fault", "is not one of"),
    ("bad pattern mode", _VALID + "patterns: strict\n", "patterns", "is not one of"),
    ("bad rbac", _VALID + "rbac: maybe\n", "rbac", "is not one of"),
    ("flags not a list", _VALID + "flags: {a: 1}\n", "flags", "must be a list"),
    ("e2e not a bool", _VALID + "e2e: 3\n", "e2e", "true or false"),
    ("prior outside correlation", _VALID + "prior: {user: same, name: x, arguments: '{}', age_seconds: 1, audit: false}\n", "prior", "only a correlation"),
    ("correlation without linked", _VALID.replace("brief", "correlation"), "linked", "declares linked"),
    (
        "correlation prior key missing",
        _VALID.replace("brief", "correlation") + "linked: true\nprior: {user: same, name: x, arguments: '{}', age_seconds: 1}\n",
        "prior.audit",
        "required key is missing",
    ),
    (
        "correlation negative age",
        _VALID.replace("brief", "correlation") + "linked: true\nprior: {user: same, name: x, arguments: '{}', age_seconds: -1, audit: false}\n",
        "prior.age_seconds",
        "non-negative",
    ),
    ("v1 call with an outcome", _VALID + "via: v1\n", "outcome", "never forwarded"),
]


def test_the_valid_template_loads(tmp_path):
    path = tmp_path / "brief-valid.yaml"
    path.write_text(_VALID, encoding="utf-8")
    case = mc.load_case(path)
    assert (case.name, case.expect["dev"], case.outcome["dev"], case.rule["dev"]) == ("stub__query", "allow", "ok", "sql.read")
    assert (case.via, case.rbac, case.patterns, case.e2e, case.window_seconds) == ("mcp", "enabled", "flag", True, 300)


@pytest.mark.parametrize("label,text,node,problem", _BAD_DOCUMENTS, ids=[b[0] for b in _BAD_DOCUMENTS])
def test_a_bad_file_names_the_file_and_the_node(tmp_path, label, text, node, problem):
    path = tmp_path / "brief-bad.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(CorpusError) as caught:
        mc.load_case(path)
    message = str(caught.value)
    assert message.startswith(f"brief-bad.yaml: {node}: "), message
    assert problem in message, message


def test_a_duplicate_key_is_refused(tmp_path):
    path = tmp_path / "brief-dup.yaml"
    path.write_text(_VALID + "server: stub\n", encoding="utf-8")
    with pytest.raises(CorpusError, match="brief-dup.yaml: file: not valid YAML"):
        mc.load_case(path)


def test_flags_normalise_both_recorded_shapes():
    hit = {"list": "injection", "pattern_id": 0}
    assert mc.normalise_flags([hit]) == mc.normalise_flags((hit,)) == [("list", "injection", 0)]
    assert mc.normalise_flags([{"uninspected": 2}, hit]) == mc.normalise_flags([hit, {"uninspected": 2}])
    assert mc.normalise_flags(["tool.opaque"]) == [("flag", "tool.opaque")]
    assert mc.normalise_flags(None) == mc.normalise_flags([]) == []
    assert mc.normalise_flags([hit]) != mc.normalise_flags([{"list": "injection", "pattern_id": 1}])
    with pytest.raises(AssertionError, match="unknown result_flags shape"):
        mc.normalise_flags([{"surprise": 1}])


# --- the gateway runner (no storage) -----------------------------------------------


@pytest.mark.parametrize("case,role", _PAIRS, ids=_ids(_PAIRS))
def test_call_decides_as_declared(case, role, corpus_stub, monkeypatch, tmp_path):
    evidence = _prepare(monkeypatch, tmp_path, corpus_stub, case, db=False)
    with _serving() as client:
        _run_role(client, evidence, corpus_stub, case, role)


def test_a_denied_call_never_reaches_the_stub(corpus_stub, monkeypatch, tmp_path):
    """AC2 in one place: every denied call of the brief goes through one world, and the stub's
    total never moves and the upstream seam is never entered."""
    brief = [c for c in _GATEWAY if c.category == "brief"]
    evidence = _prepare(monkeypatch, tmp_path, corpus_stub, brief[0], db=False)
    posted = 0
    with _serving() as client:
        for case in brief:
            for role in case.roles:
                if case.expect[role] != "deny":
                    continue
                evidence.current = f"mcp:{mc.JSONRPC_IDS[role]}"
                assert _post(client, role, case.name, case.arguments_object(), mc.JSONRPC_IDS[role]).status_code == 200
                posted += 1
    assert posted >= 5
    assert corpus_stub.stats()["calls"] == {}
    assert evidence.entered == []


# --- /v1 aliases (decided at step 7c; no storage) ------------------------------------


@pytest.mark.parametrize("case,role", _ALIAS_PAIRS, ids=_ids(_ALIAS_PAIRS))
def test_alias_case_decides_as_declared(case, role, monkeypatch, tmp_path):
    mc.configure(monkeypatch, tmp_path, "http://127.0.0.1:9/mcp", prefixes=mc.V1_PREFIXES, mcp_enabled=True)
    identity = mc.IDENTITIES[role]
    aliases = query_pipeline._alias_input(identity)
    assert aliases is not None
    arguments = case.arguments_object()
    call = ToolCall(f"{case.stem}:{role}", case.name, action_audit.canonical_json(arguments))
    (decision,) = action_policy.evaluate_all([call], identity, action_config.get_policy(), aliases=aliases)

    resolved = case.rule[role] != "tool.unknown"
    server = case.server if resolved else None
    assert (decision.decision, decision.rule) == (case.expect[role], case.rule[role]), (case.stem, role)
    assert decision.granted_by == case.granted_by.get(role)
    assert decision.mcp_server == server
    (row,) = action_audit.decision_rows([decision], identity, "alias-w")
    assert (row.surface, row.mcp_server, row.outcome) == ("v1", server, None)
    assert row.arguments_canonical_hash == (action_audit.arguments_canonical_hash(arguments) if resolved else None)


# --- the same corpus against the real rows (CI: `db`) --------------------------------


@pytest.mark.parametrize("case", _GATEWAY, ids=_ids(_GATEWAY))
def test_call_decides_as_declared_db(case, corpus_stub, temp_db, monkeypatch, tmp_path):
    evidence = _prepare(monkeypatch, tmp_path, corpus_stub, case, db=True)
    with _serving() as client:
        for role in case.roles:
            row = _run_role(client, evidence, corpus_stub, case, role)
            assert row["mcp_config_digest"] == mcp_config.mcp_config_digest()
            assert row["arguments_canonical_hash"] == action_audit.arguments_canonical_hash(case.arguments_object())


def _seed_prior(prior: mc.Prior) -> tuple:
    """Insert the `/v1` alias row (and its audit row) the way step 8 writes them; `(row id, audit id)`."""
    identity = mc.IDENTITIES["dev"] if prior.user == "same" else mc.OTHER_USER
    audit_id = None
    stamp = (_NOW - timedelta(seconds=prior.age_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if prior.audit:
        with database.get_connection() as conn:
            audit_id = conn.execute(
                "INSERT INTO audit_logs (timestamp, user_id, prompt_hash) VALUES (?, ?, 'h')",
                (stamp, identity.user_id),
            ).lastrowid
    aliases = query_pipeline._alias_input(identity)
    arguments = strict_json.loads(prior.arguments)
    call = ToolCall("c", prior.name, action_audit.canonical_json(arguments))
    (decision,) = action_policy.evaluate_all([call], identity, action_config.get_policy(), aliases=aliases)
    (row,) = action_audit.decision_rows([decision], identity, "v1-prior", audit_id)
    row = dataclasses.replace(row, timestamp=stamp)
    if prior.decision is not None:
        row = dataclasses.replace(row, decision=prior.decision)  # a stored deny: the claim must skip it
    assert row.surface == "v1" and row.mcp_server == "stub"
    (row_id,) = database.insert_action_decisions([row])
    return row_id, audit_id


@pytest.mark.parametrize("case", _CORRELATION, ids=_ids(_CORRELATION))
def test_correlation_case_db(case, corpus_stub, temp_db, monkeypatch, tmp_path):
    # MCP on: the seed row is built through step 7c's alias input, which is None while MCP is off.
    evidence = _prepare(
        monkeypatch, tmp_path, corpus_stub, case, db=True, prefixes=mc.V1_PREFIXES, mcp_enabled=True
    )
    monkeypatch.setattr(settings, "MCP_LINK_WINDOW_SECONDS", case.window_seconds)
    monkeypatch.setattr(mcp_gateway, "_link_clock", lambda: _NOW)
    prior_id = audit_id = None
    if case.prior is not None:
        prior_id, audit_id = _seed_prior(case.prior)  # the insert comes first; the row is read after the call
    with _serving() as client:
        row = _run_role(client, evidence, corpus_stub, case, "dev")
    assert row["linked_decision_id"] == (prior_id if case.linked else None), case.stem
    assert row["audit_id"] == (audit_id if case.linked else None), case.stem
    if case.linked and case.prior.audit:
        assert row["audit_id"] is not None
