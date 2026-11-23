"""PRD-016 STORY-014: the decision engine, `action_policy.evaluate()` and `evaluate_all()`.

Covers PRD-016 Sections 4 (Decision engine), 6.2, 6.4 and 6.7, F7, T4, T9 and
T11, and decisions D7, D9 and D10: mapping a call, classifying each operation,
deciding each classification through `authz.holds()`, folding to the most
severe outcome, the reason template, the digest stamp, and failing closed
when anything in between raises.

Expected values (decisions, rule ids, reasons, permissions) are written out as
literals rather than read from the module: these tests are about the PRD, and
comparing the module with itself would prove nothing. The two exceptions are
`_SUBJECTS` / `_VERDICTS` in the reason sweep, whose key sets are pinned
against the closed vocabularies first.

What it deliberately does **not** cover: recording decisions (STORY-015) and
the action corpora (STORY-017/018). The classifiers' own behaviour belongs to
their suites; here they are reached only through `evaluate()`.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import builtins
import dataclasses
import inspect
import json
import logging
import pathlib
import re
from types import MappingProxyType

import pytest

import app.db.database as database
from app.config import settings
from app.services import action_adapters, action_config, action_policy, authz
from app.services.action_adapters import ToolCall
from app.services.action_classifiers import DECISIONS, RULE_IDS, Classification, network, paths, shell, sql
from app.services.action_config import BUILT_IN_POLICY, Rule
from app.services.action_policy import ActionDecision, evaluate, evaluate_all
from app.services.identity import Identity

USER = Identity("u", "user")
DBA = Identity("d", "dba")
ADMIN = Identity("a", "admin")

_LOGGER = "app.services.action_policy"


def _call(name, arguments, id="c1"):
    """A `ToolCall`; a dict is JSON-dumped, a string is sent as is."""
    if not isinstance(arguments, str):
        arguments = json.dumps(arguments)
    return ToolCall(id, name, arguments)


def _with(**fields):
    return dataclasses.replace(BUILT_IN_POLICY, **fields)


def _with_rules(**changes):
    return _with(rules=MappingProxyType({**BUILT_IN_POLICY.rules, **changes}))


def _grant(monkeypatch, role, *permissions):
    """A test RBAC matrix: the built-in one plus `role` holding `permissions`."""
    monkeypatch.setattr(
        authz, "ROLE_PERMISSIONS", {**authz.ROLE_PERMISSIONS, role: {"query:submit", *permissions}}
    )


@pytest.fixture
def dba_matrix(monkeypatch):
    _grant(monkeypatch, "dba", "action:sql:write")


def _reported(d: ActionDecision) -> Classification:
    """The classification the decision reports (the D-2 invariant: exactly one)."""
    matches = [c for c in d.classifications if c.rule == d.rule and c.operation is d.operation]
    assert matches, d
    return matches[0]


# --- G1 (AC 1): the built-in policy, a `user` -------------------------------


def test_drop_table_is_denied_as_ddl_with_the_prd_reason():
    d = evaluate(_call("query", {"sql": "DROP TABLE users"}), USER)

    assert d.decision == "deny"
    assert d.rule == "sql.ddl"
    assert d.reason == "destructive SQL is not permitted: DROP"
    assert d.granted_by is None
    assert d.tool_call_id == "c1"
    assert d.tool_name == "query"


def test_a_scoped_select_is_allowed_as_read():
    d = evaluate(_call("query", {"sql": "SELECT * FROM users WHERE id = 1"}), USER)

    assert (d.decision, d.rule, d.granted_by) == ("allow", "sql.read", None)


def test_an_unknown_tool_is_denied():
    d = evaluate(_call("postgres_query", {"sql": "SELECT 1"}), USER)

    assert (d.decision, d.rule) == ("deny", "tool.unknown")
    assert d.reason == "an unknown tool is not permitted: postgres_query"
    assert d.operations == ()
    assert d.operation is None
    assert d.classifications == (Classification("tool.unknown", None, "postgres_query"),)


def test_an_unknown_tool_name_detail_is_capped():
    d = evaluate(_call("x" * 200, {}), USER)

    assert d.classifications[0].detail == "x" * 64


# --- G2 (AC 2, D7, T4): grants through holds() ------------------------------


def test_scoped_delete_is_denied_for_user_and_granted_for_dba(dba_matrix):
    call = _call("query", {"sql": "DELETE FROM t WHERE id = 3"})

    user = evaluate(call, USER)
    dba = evaluate(call, DBA)

    assert (user.decision, user.rule, user.granted_by) == ("deny", "sql.write", None)
    assert (dba.decision, dba.rule, dba.granted_by) == ("allow", "sql.write", "action:sql:write")
    assert dba.reason == "SQL that changes data is permitted: DELETE"


@pytest.mark.parametrize("statement", ["DELETE FROM t", "DELETE FROM t WHERE 1=1"])
def test_unscoped_delete_is_denied_for_both(dba_matrix, statement):
    """`sql.unscoped_write` is non-grantable (T5): no grant reaches it."""
    for identity in (USER, DBA):
        d = evaluate(_call("query", {"sql": statement}), identity)
        assert (d.decision, d.rule, d.granted_by) == ("deny", "sql.unscoped_write", None)


#: One call per grantable rule, each producing that rule alone (or reporting it).
_GRANTABLE_CALLS = [
    ("sql.write", "query", {"sql": "INSERT INTO t VALUES (1)"}),
    ("sql.ddl", "query", {"sql": "DROP TABLE t"}),
    ("shell.unlisted", "bash", {"command": "make release"}),
    ("shell.inline_interpreter", "bash", {"command": "python -c 1"}),
    ("shell.package_install", "bash", {"command": "npm install x"}),
    ("shell.service_control", "bash", {"command": "systemctl stop x"}),
    ("fs.write_outside_workspace", "write", {"filePath": "/etc/hosts"}),
    ("net.unlisted", "webfetch", {"url": "https://evil.example/"}),
    ("secret.read", "read", {"filePath": ".env"}),
]


def test_the_grantable_calls_cover_every_grantable_rule():
    grantable = {rule_id for rule_id, rule in BUILT_IN_POLICY.rules.items() if rule.grant}
    assert {rule for rule, _, _ in _GRANTABLE_CALLS} == grantable


@pytest.mark.parametrize("rule, tool, arguments", _GRANTABLE_CALLS)
def test_rbac_off_grants_nothing_under_the_built_in_matrix(monkeypatch, rule, tool, arguments):
    """AC 2 / T4 (orchestrator reading, STORY-014 plan Q1): the escape hatch hands out no
    grant. With RBAC off every role -- `dba` included -- gets the rule's built-in default."""
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)

    for identity in (USER, DBA, ADMIN):
        d = evaluate(_call(tool, arguments), identity)
        assert (d.decision, d.rule, d.granted_by) == ("deny", rule, None), identity


def test_rbac_off_keeps_an_explicit_grant(monkeypatch, dba_matrix):
    """`holds()` ignores RBAC_ENABLED in both directions (STORY-003 AC 2): `dba` keeps
    exactly what the matrix gives it, and nobody gets more."""
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    call = _call("query", {"sql": "DELETE FROM t WHERE id = 3"})

    assert evaluate(call, DBA).decision == "allow"
    assert evaluate(call, DBA).granted_by == "action:sql:write"
    assert evaluate(call, USER).decision == "deny"
    assert evaluate(call, ADMIN).decision == "deny"


def test_a_lifted_allow_outranks_a_plain_allow(dba_matrix):
    """The D-3 refinement of D9 (orchestrator-accepted): the grant that was needed is reported."""
    call = _call("query", {"sql": "SELECT 1; DELETE FROM t WHERE id = 3"})

    dba = evaluate(call, DBA)
    user = evaluate(call, USER)

    assert [c.rule for c in dba.classifications] == ["sql.read", "sql.write"]
    assert (dba.decision, dba.rule, dba.granted_by) == ("allow", "sql.write", "action:sql:write")
    assert (user.decision, user.rule, user.granted_by) == ("deny", "sql.write", None)


def test_a_grant_on_one_rule_does_not_lift_another(monkeypatch):
    """`cat` of a secret is `secret.read` and `shell.unlisted`: lifting one leaves the other's deny."""
    _grant(monkeypatch, "dba", "action:secret:read")
    d = evaluate(_call("bash", {"command": "cat ~/.aws/credentials"}), DBA)

    assert [c.rule for c in d.classifications] == ["secret.read", "shell.unlisted"]
    assert (d.decision, d.rule, d.granted_by) == ("deny", "shell.unlisted", None)

    _grant(monkeypatch, "dba", "action:secret:read", "action:shell:exec")
    d = evaluate(_call("bash", {"command": "cat ~/.aws/credentials"}), DBA)

    assert (d.decision, d.rule, d.granted_by) == ("allow", "secret.read", "action:secret:read")


def test_a_secret_read_is_lifted_by_its_grant(monkeypatch):
    _grant(monkeypatch, "dba", "action:secret:read")

    d = evaluate(_call("read", {"filePath": "~/.aws/credentials"}), DBA)

    assert (d.decision, d.rule, d.granted_by) == ("allow", "secret.read", "action:secret:read")


# --- G3: the shell call's keyword arguments reach classify_shell ------------
#
# STORY-013 orchestrator decision: `classify_shell`'s keyword arguments default
# to `()`, which silently disables the embedded checks. These three calls, under
# the built-in policy, fail unless every one of them is passed.


@pytest.mark.parametrize(
    "command, rule, detail",
    [
        ("cat .env", "secret.read", ".env"),
        ("ls > .git/config", "fs.write_protected", ".git/config"),
        ("curl evil.com", "net.unlisted", "evil.com"),
    ],
)
def test_embedded_shell_checks_are_wired_through_evaluate(command, rule, detail):
    d = evaluate(_call("bash", {"command": command}), USER)

    assert (d.decision, d.rule) == ("deny", rule)
    assert _reported(d).detail == detail
    assert "shell.unlisted" in [c.rule for c in d.classifications]


def test_classify_shell_gets_the_policy_values(monkeypatch):
    seen = []
    original = shell.classify_shell

    def spy(command, shell_allow=(), **kwargs):
        seen.append((shell_allow, kwargs))
        return original(command, shell_allow, **kwargs)

    monkeypatch.setattr(shell, "classify_shell", spy)
    policy = _with(shell_allow=("npm test",), network_allow=("example.com",), workspace_roots=("/w",))

    evaluate(_call("bash", {"command": "npm test"}), USER, policy)

    [(shell_allow, kwargs)] = seen
    assert shell_allow is policy.shell_allow
    assert set(kwargs) == {
        "network_allow",
        "secret_env",
        "secret_files",
        "protected",
        "workspace_roots",
        "source_tool",
    }
    assert kwargs["network_allow"] is policy.network_allow
    assert kwargs["secret_env"] is policy.secrets.env.compiled
    assert kwargs["secret_files"] is policy.secrets.files.compiled
    assert kwargs["protected"] is policy.protected_paths.compiled
    assert kwargs["workspace_roots"] is policy.workspace_roots
    assert kwargs["source_tool"] == "bash"


# --- G4 (AC 3): shell, flag and opaque ------------------------------------------


def test_an_allowlisted_head_does_not_hide_a_destructive_segment():
    d = evaluate(_call("bash", {"command": "npm test && rm -rf build"}), USER, _with(shell_allow=("npm test",)))

    assert (d.decision, d.rule) == ("deny", "shell.destructive")
    assert [c.rule for c in d.classifications] == ["shell.allowlisted", "shell.destructive"]


def test_a_flag_default_flags():
    """D10: `flag` is returned as is; what to do with it is PRD-017's."""
    call = _call("bash", {"command": "make release"})
    policy = _with_rules(**{"shell.unlisted": Rule("flag", "action:shell:exec")})

    d = evaluate(call, USER, policy)

    assert (d.decision, d.rule, d.granted_by) == ("flag", "shell.unlisted", None)
    assert d.reason == "a command that is not allowlisted is permitted and flagged for review: make"
    assert evaluate(call, USER).decision == "deny"


@pytest.mark.parametrize("decision", ["allow", "flag", "deny"])
def test_an_opaque_tool_takes_its_entry_decision_without_reading_arguments(decision):
    policy = _with(opaque_tools=MappingProxyType({"todowrite": decision}))

    # "not json": the arguments are never parsed (Section 6.4).
    d = evaluate(_call("todowrite", "not json"), USER, policy)

    assert (d.decision, d.rule, d.granted_by) == (decision, "tool.opaque", None)
    assert d.operations == ()
    assert d.operation is None
    assert d.classifications == (Classification("tool.opaque", None, "todowrite"),)


def test_sql_embedded_in_shell_is_reported_as_sql():
    """PRD Section 11: `psql -c "DROP TABLE t"` is `sql.ddl`, not `shell.unlisted`."""
    d = evaluate(_call("bash", {"command": 'psql -c "DROP TABLE t"'}), USER)

    assert (d.decision, d.rule) == ("deny", "sql.ddl")
    assert [c.rule for c in d.classifications] == ["sql.ddl", "shell.unlisted"]


# --- G5 (AC 4, T9): a raise fails closed ----------------------------------------

MARK = "secret_marker_9f3"


def _boom(*_args, **_kwargs):
    raise RuntimeError("boom " + MARK)


_RAISERS = [
    (sql, "classify_sql", "query", {"sql": f"SELECT '{MARK}'"}),
    (shell, "classify_shell", "bash", {"command": f"echo {MARK}"}),
    (paths, "classify_write", "write", {"filePath": f"/tmp/{MARK}"}),
    (paths, "classify_read", "read", {"filePath": f"{MARK}.txt"}),
    (network, "classify_url", "webfetch", {"url": f"https://{MARK}.example/"}),
    (action_adapters, "map_tool_call", "query", {"sql": f"SELECT '{MARK}'"}),
    # A grantable rule, so `holds()` is reached.
    (authz, "holds", "query", {"sql": f"DELETE FROM t WHERE id = '{MARK}'"}),
]


@pytest.mark.parametrize(
    "module, name, tool, arguments", _RAISERS, ids=[f"{m.__name__}.{n}" for m, n, _, _ in _RAISERS]
)
def test_a_raise_is_denied_as_malformed_and_logged_without_arguments(
    monkeypatch, caplog, module, name, tool, arguments
):
    monkeypatch.setattr(module, name, _boom)
    caplog.set_level(logging.DEBUG, logger=_LOGGER)
    call = _call(tool, arguments)

    d = evaluate(call, USER)

    assert (d.decision, d.rule, d.granted_by) == ("deny", "tool.malformed", None)
    assert d.reason == "a tool call that cannot be read is not permitted: classification failed"
    assert d.classifications == (Classification("tool.malformed", None, "classification failed"),)
    assert d.operation is None
    records = [r for r in caplog.records if r.name == _LOGGER]
    assert len(records) == 1
    [record] = records
    assert record.levelno == logging.ERROR
    message = record.getMessage()
    assert repr(tool) in message
    assert "tool.malformed" in message
    assert MARK not in message
    assert call.arguments not in message
    assert record.exc_info is None
    assert record.exc_text is None
    assert MARK not in caplog.text


def test_a_raise_is_a_hard_deny_whatever_the_malformed_default(monkeypatch):
    """STORY-014 plan D-5 / Q3 (accepted): a classifier crash is a bug, not a policy choice."""
    policy = _with_rules(**{"tool.malformed": Rule("allow", None)})
    # The configured default still governs arguments that cannot be read ...
    assert evaluate(_call("query", "not json"), USER, policy).decision == "allow"

    monkeypatch.setattr(sql, "classify_sql", _boom)
    d = evaluate(_call("query", {"sql": "SELECT 1"}), USER, policy)

    # ... but not a raise.
    assert (d.decision, d.rule) == ("deny", "tool.malformed")


def test_a_classifier_that_returns_nothing_fails_closed(monkeypatch):
    monkeypatch.setattr(sql, "classify_sql", lambda *a, **k: ())

    d = evaluate(_call("query", {"sql": "SELECT 1"}), USER)

    assert (d.decision, d.rule) == ("deny", "tool.malformed")


def test_a_classifier_that_returns_tool_opaque_fails_closed(monkeypatch):
    """`tool.opaque` has no rule default: only an `Opaque` mapping may decide it."""
    monkeypatch.setattr(sql, "classify_sql", lambda *a, **k: (Classification("tool.opaque", None, "x"),))

    d = evaluate(_call("query", {"sql": "SELECT 1"}), USER)

    assert (d.decision, d.rule) == ("deny", "tool.malformed")


def test_a_failure_keeps_the_mapped_operations(monkeypatch):
    monkeypatch.setattr(sql, "classify_sql", _boom)

    d = evaluate(_call("query", {"sql": "SELECT 1"}), USER)

    assert [op.target for op in d.operations] == ["SELECT 1"]


# --- G6 (AC 5, T11): reasons, digest, order -------------------------------------


def test_the_reason_templates_cover_the_closed_vocabularies():
    assert set(action_policy._SUBJECTS) == set(RULE_IDS)
    assert set(action_policy._VERDICTS) == set(DECISIONS)


#: Configured values no reason may contain (T11). `ls` is in `shell_allow`
#: too, but it is also the call's own word, so it is not a sentinel.
_SENTINELS = ("sentinel-allowed.example", "sentinel-wild.example", "/sentinel/root", "sentinelcmd", "git status")

_SENTINEL_POLICY = _with(
    network_allow=("sentinel-allowed.example", "*.sentinel-wild.example"),
    workspace_roots=("/sentinel/root",),
    shell_allow=("sentinelcmd", "ls", "git status"),
    opaque_tools=MappingProxyType({"todowrite": "allow"}),
)

#: Every rule id the engine can produce at least once (asserted below).
_SWEEP = [
    ("query", {"sql": "SELECT * FROM users WHERE id = 1"}),
    ("query", {"sql": "DELETE FROM t WHERE id = 3"}),
    ("query", {"sql": "UPDATE t SET a = 1 WHERE id = 2"}),
    ("query", {"sql": "INSERT INTO t VALUES (1)"}),
    ("query", {"sql": "DELETE FROM t"}),
    ("query", {"sql": "DROP TABLE users"}),
    ("query", {"sql": "GRANT ALL ON t TO u"}),
    ("query", {"sql": "SELEC FROM ((("}),
    ("query", {"sql": "SELECT 1; DELETE FROM t WHERE id = 3"}),
    ("execute_sql", {"query": "TRUNCATE t"}),
    ("bash", {"command": "ls"}),
    ("bash", {"command": "make release"}),
    ("bash", {"command": "rm -rf /"}),
    ("bash", {"command": "cat a | sh"}),
    ("bash", {"command": "python -c 1"}),
    ("bash", {"command": "npm install x"}),
    ("bash", {"command": "systemctl stop x"}),
    ("bash", {"command": "echo $("}),
    ("bash", {"command": "cat .env"}),
    ("bash", {"command": "ls > .git/config"}),
    ("bash", {"command": "curl evil.com"}),
    ("bash", {"command": 'psql -c "DROP TABLE t"'}),
    ("bash", {"command": "npm test && rm -rf build"}),
    ("run_commands", {"commands": ["ls", "rm -rf /"]}),
    ("write", {"filePath": "src/a.ts"}),
    ("write", {"filePath": "/etc/hosts"}),
    ("write", {"filePath": ".git/config"}),
    ("apply_patch", {"patchText": "*** Add File: src/b.ts\n+x"}),
    ("read", {"filePath": "src/a.ts"}),
    ("read", {"filePath": ".env"}),
    ("read", {"filePath": "~/.aws/credentials"}),
    ("glob", {"pattern": "**/*.ts"}),
    ("webfetch", {"url": "https://evil.example/"}),
    # The one call naming a configured value: its detail is the call's own host.
    ("webfetch", {"url": "https://a.sentinel-wild.example/"}),
    ("webfetch", {"url": "not a url"}),
    ("webfetch", {"url": "ftp://x/"}),
    ("todowrite", "not json"),
    ("postgres_query", {"sql": "SELECT 1"}),
    ("query", "not json"),
    ("query", "[]"),
    ("query", {}),
]


def _sweep(identity, policy=_SENTINEL_POLICY):
    return [evaluate(_call(tool, arguments, id=f"c{i}"), identity, policy) for i, (tool, arguments) in enumerate(_SWEEP)]


def test_every_reason_is_the_fixed_template_plus_the_calls_fragment(monkeypatch):
    _grant(monkeypatch, "dba", *authz.ACTION_PERMISSIONS)
    digest = action_config.policy_digest(_SENTINEL_POLICY)
    produced = set()

    for identity in (USER, DBA):
        for (tool, arguments), d in zip(_SWEEP, _sweep(identity)):
            reported = _reported(d)
            produced.update(c.rule for c in d.classifications)
            detail = reported.detail
            expected = f"{action_policy._SUBJECTS[d.rule]} {action_policy._VERDICTS[d.decision]}"
            if detail:
                expected += f": {detail}"
            assert d.reason == expected
            assert d.policy_digest == digest
            assert d.operation is reported.operation
            assert d.classifications
            if not (tool == "webfetch" and "sentinel-wild" in arguments["url"]):
                for sentinel in _SENTINELS:
                    assert sentinel not in d.reason, (tool, arguments, d.reason)

    # PRD-023 D7: `tool.not_in_skill` is produced only by a gateway call outside the
    # caller's skills (STORY-006), which no sweep entry here is; its subject is pinned
    # by test_the_reason_templates_cover_the_closed_vocabularies.
    assert produced == set(RULE_IDS) - {"tool.not_in_skill"}


def test_the_digest_is_the_policy_in_force():
    d = evaluate(_call("query", {"sql": "SELECT 1"}), USER)
    assert d.policy_digest == action_config.policy_digest()
    assert d.policy_digest == action_config.policy_digest(BUILT_IN_POLICY)

    # Restored by the `_default_action_policy` autouse fixture.
    action_config._policy = _with_rules(**{"sql.read": Rule("flag", None)})
    changed = evaluate(_call("query", {"sql": "SELECT 1"}), USER)

    assert changed.decision == "flag"
    assert changed.policy_digest != d.policy_digest
    assert changed.policy_digest == action_config.policy_digest()


def test_evaluate_all_preserves_input_order():
    calls = [
        _call("query", {"sql": "DROP TABLE t"}, id="c3"),
        _call("query", {"sql": "SELECT 1"}, id="c1"),
        _call("nope", {}, id="c2"),
    ]

    decisions = evaluate_all(calls, USER)

    assert isinstance(decisions, tuple)
    assert [d.tool_call_id for d in decisions] == ["c3", "c1", "c2"]
    assert [d.decision for d in decisions] == ["deny", "allow", "deny"]
    assert decisions == tuple(evaluate(c, USER) for c in calls)
    assert evaluate_all([], USER) == ()


def test_evaluate_all_resolves_the_policy_once(monkeypatch):
    seen = []
    original = action_config.get_policy

    def counting():
        seen.append(1)
        return original()

    monkeypatch.setattr(action_config, "get_policy", counting)

    evaluate_all([_call("query", {"sql": "SELECT 1"})] * 3, USER)

    assert len(seen) == 1


# --- G7: shape, malformed input, cross-operation order ----------------------


def test_action_decision_shape():
    assert [f.name for f in dataclasses.fields(ActionDecision)] == [
        "tool_call_id",
        "tool_name",
        "decision",
        "rule",
        "reason",
        "granted_by",
        "classifications",
        "policy_digest",
        "operations",
        "operation",
        "arguments",
    ]
    d = evaluate(_call("query", {"sql": "SELECT 1"}), USER)
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.decision = "allow"


def test_arguments_are_kept_but_not_in_repr():
    """T10: the raw arguments may hold a secret; they are for the audit, not for a log line."""
    call = _call("query", {"sql": "SELECT 1", "note": MARK})

    d = evaluate(call, USER)

    assert d.arguments == call.arguments
    assert MARK not in repr(d)
    assert "arguments=" not in repr(d)


@pytest.mark.parametrize("arguments", ["not json", "[]", "{}"])
def test_unreadable_arguments_are_malformed(arguments):
    d = evaluate(_call("query", arguments), USER)

    assert (d.decision, d.rule, d.operations) == ("deny", "tool.malformed", ())


def test_oversized_arguments_are_malformed(monkeypatch):
    """The cap reaches the adapter through `action_config.get_max_argument_characters()`."""
    monkeypatch.setattr(settings, "ACTION_MAX_ARGUMENT_CHARACTERS", 10)

    d = evaluate(_call("query", {"sql": "SELECT * FROM users"}), USER)

    assert (d.decision, d.rule) == ("deny", "tool.malformed")
    # Orchestrator decision 5: the reason may name the cap; it is not a host, root or entry.
    assert d.reason == "a tool call that cannot be read is not permitted: arguments exceed 10 characters"


def test_a_denied_second_operation_is_reported():
    d = evaluate(_call("run_commands", {"commands": ["ls", "rm -rf /"]}), USER, _with(shell_allow=("ls",)))

    assert (d.decision, d.rule) == ("deny", "shell.destructive")
    assert [op.target for op in d.operations] == ["ls", "rm -rf /"]
    assert [c.rule for c in d.classifications] == ["shell.allowlisted", "shell.destructive"]
    assert d.operation == d.operations[1]


def test_the_first_deny_is_reported_when_several_deny():
    """D9: the first classification at the maximum severity, in classifier order."""
    d = evaluate(_call("run_commands", {"commands": ["ls", "rm -rf /"]}), USER)

    assert [c.rule for c in d.classifications] == ["shell.unlisted", "shell.destructive"]
    assert (d.decision, d.rule) == ("deny", "shell.unlisted")


def test_an_allowlisted_command_is_allowed():
    d = evaluate(_call("bash", {"command": "npm test"}), USER, _with(shell_allow=("npm test",)))

    assert (d.decision, d.rule) == ("allow", "shell.allowlisted")


def test_a_relative_write_is_allowed():
    d = evaluate(_call("write", {"filePath": "src/a.ts"}), USER)

    assert (d.decision, d.rule) == ("allow", "fs.write_in_workspace")


def test_a_non_string_name_is_malformed_without_raising():
    d = evaluate(ToolCall("c1", 123, "{}"), USER)

    assert (d.decision, d.rule, d.tool_name) == ("deny", "tool.malformed", "")


def test_a_call_that_is_not_a_tool_call_fails_closed():
    d = evaluate(None, USER)

    assert (d.decision, d.rule, d.tool_call_id, d.tool_name, d.arguments) == (
        "deny",
        "tool.malformed",
        "",
        "",
        "",
    )


@pytest.mark.parametrize("setting, expected", [("postgres", "postgres"), ("", None)])
def test_the_sql_dialect_reaches_the_classifier(monkeypatch, setting, expected):
    seen = []
    original = sql.classify_sql

    def spy(statement, dialect, **kwargs):
        seen.append(dialect)
        return original(statement, dialect, **kwargs)

    monkeypatch.setattr(sql, "classify_sql", spy)
    monkeypatch.setattr(settings, "ACTION_SQL_DIALECT", setting)

    evaluate(_call("query", {"sql": "SELECT 1"}), USER)

    assert seen == [expected]


# --- G8 (D-1): purity --------------------------------------------------------


def test_action_policy_stays_pure():
    """PRD-016 Section 6.12: no `settings` name, no file or path I/O, and exactly the
    four allowed `app` modules: `action_adapters`, `action_classifiers`, `action_config`
    (the policy and the two call-time getters) and `authz` (`holds()`). Importing them
    loads `app.config` transitively; STORY-014 plan D-1 states that limit, so there is
    no subprocess "imports load no settings" check here."""
    source = inspect.getsource(action_policy)

    assert "settings" not in vars(action_policy)
    assert "open(" not in source
    assert not re.search(r"(?<![A-Za-z])Path\(", source)
    assert "os." not in source
    # Column 0 only: the indented `TYPE_CHECKING` import of `Identity` is excluded.
    app_imports = [
        line
        for line in source.splitlines()
        if (line.startswith("import ") or line.startswith("from ")) and " app." in f" {line}"
    ]
    assert app_imports == [
        "from app.services import action_adapters, action_config, authz",
        "from app.services.action_classifiers import DECISIONS, Classification, Decision, Operation, RuleId",
        "from app.services.action_classifiers import network, paths, shell, sql",
    ]


def test_evaluate_does_no_io(monkeypatch):
    """No file opened and no connection taken. The patches record rather than raise:
    a raise would be swallowed by the fail-closed boundary and hide the I/O."""
    _sweep(USER)  # warm-up: sqlglot loads dialect modules lazily
    calls = []
    original_open = builtins.open
    original_read_text = pathlib.Path.read_text

    def recording_open(*args, **kwargs):
        calls.append(("open", args))
        return original_open(*args, **kwargs)

    def recording_read_text(self, *args, **kwargs):
        calls.append(("read_text", self))
        return original_read_text(self, *args, **kwargs)

    def recording_connection(*args, **kwargs):
        calls.append(("get_connection", args))
        raise AssertionError("action_policy took a database connection")

    monkeypatch.setattr(builtins, "open", recording_open)
    monkeypatch.setattr(pathlib.Path, "read_text", recording_read_text)
    monkeypatch.setattr(database, "get_connection", recording_connection)

    decisions = _sweep(USER) + _sweep(USER, BUILT_IN_POLICY)

    assert calls == []
    assert all(c.detail != "classification failed" for d in decisions for c in d.classifications)
