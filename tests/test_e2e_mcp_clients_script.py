"""PRD-023 STORY-020: what the MCP client E2E renders, pinned in the everyday suite.

`tests/e2e/test_mcp_clients.py` only runs with `--run-e2e`. What it depends on is checked here
without OpenCode, Cline, a database or a subprocess: both scenario scripts answer the clients'
request sequences with the planned rules, the gateway config and the policy load through the real
loaders, the roles file agrees with the corpus matrix, the client configs have the shapes STORY-002
observed, and the embedded-database launcher parses its three modes. A change to any of them fails
here, not only under `--run-e2e`.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import json

import pytest
import yaml

from app.config import settings
from app.services import action_config, authz, mcp_config
from app.services.identity import Identity
from scripts.stub_openrouter import Request, parse_script
from tests import mcp_corpus
from tests.e2e import _embedded_db, _live, _mcp

_PROMPT_ALLOW = "E2E-MCP-ALLOW [abcd1234] run the scripted stub query"
_PROMPT_DROP = "E2E-MCP-DROP [abcd1234] run the scripted stub query"


def _script(path):
    return parse_script(json.loads(_mcp.render_script(path)))


def _label(script, body) -> str:
    return script.select_request(Request.from_body(body))[0]


def _tools(*names) -> list:
    return [{"type": "function", "function": {"name": name}} for name in names]


def _assistant(name: str) -> dict:
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": name, "arguments": "{}"}}]}


def _oc_body(prompt, *turns, tools=(_mcp.OPENCODE_QUERY, "read")) -> dict:
    return {"model": "openai/gpt-4o", "stream": True, "tools": _tools(*tools),
            "messages": [{"role": "system", "content": "You are OpenCode."},
                         {"role": "user", "content": prompt}, *turns]}


def _cl_body(workdir: str, *turns, tools=(_mcp.CLINE_QUERY, "submit_and_exit")) -> dict:
    return {"model": "openai/gpt-4o", "stream": True, "tools": _tools(*tools),
            "messages": [{"role": "system", "content": f"You are Cline. Current working directory: {workdir}"},
                         {"role": "user", "content": _PROMPT_ALLOW},
                         {"role": "user", "content": "[SYSTEM] call submit_and_exit"}, *turns]}


def _done(call_name: str) -> list:
    return [_assistant(call_name), {"role": "tool", "tool_call_id": "c1", "content": "ok"}]


def test_the_opencode_script_calls_the_corpus_arguments_and_ends_after_the_call():
    script = _script(_mcp.OPENCODE_SCRIPT)
    cases = _mcp.pick_cases()
    calls = {call.name: call.arguments for rule in script.rules for call in rule.reply.tool_calls}
    assert set(calls) == {_mcp.OPENCODE_QUERY}
    texts = sorted(call.arguments for rule in script.rules for call in rule.reply.tool_calls)
    assert texts == sorted([cases["allow"].arguments, cases["deny"].arguments])  # the corpus bytes, unchanged

    assert _label(script, _oc_body(_PROMPT_ALLOW)) == _mcp.OC_ALLOW_RULE
    assert _label(script, _oc_body(_PROMPT_DROP)) == _mcp.OC_DROP_RULE
    # After the call (the result is whatever the gateway said, allowed or denied) the loop ends.
    assert _label(script, _oc_body(_PROMPT_ALLOW, *_done(_mcp.OPENCODE_QUERY))) == _mcp.OC_AFTER_RULE
    assert _label(script, _oc_body(_PROMPT_DROP, *_done(_mcp.OPENCODE_QUERY))) == _mcp.OC_AFTER_RULE
    # OpenCode's title request has no tools.
    assert _label(script, _oc_body(_PROMPT_ALLOW, tools=())) == _mcp.OC_TITLE_RULE


def test_a_missing_mcp_tool_falls_to_the_default_in_both_scripts():
    """A tool the client did not offer must show as no row, not as a call."""
    oc = _script(_mcp.OPENCODE_SCRIPT)
    # The catch-all title rule answers it with text: no tool call, so no row.
    label, reply = oc.select_request(Request.from_body(_oc_body(_PROMPT_ALLOW, tools=("read",))))
    assert label == _mcp.OC_TITLE_RULE and not reply.tool_calls

    cl = _script(_mcp.CLINE_SCRIPT)
    body = _cl_body(f"C:/tmp/{_mcp.CL_ALLOW_DIR}0", tools=("submit_and_exit",))
    label, reply = cl.select_request(Request.from_body(body))
    assert label != _mcp.CL_ALLOW_RULE
    assert [call.name for call in reply.tool_calls] == ["submit_and_exit"]  # the default ends the run


def test_the_cline_script_picks_the_scenario_from_the_working_directory():
    script = _script(_mcp.CLINE_SCRIPT)
    assert _label(script, _cl_body(f"C:/tmp/pytest-0/{_mcp.CL_ALLOW_DIR}0")) == _mcp.CL_ALLOW_RULE
    assert _label(script, _cl_body(f"C:/tmp/pytest-0/{_mcp.CL_DROP_DIR}0")) == _mcp.CL_DROP_RULE
    after = _label(script, _cl_body(f"C:/tmp/pytest-0/{_mcp.CL_DROP_DIR}0", *_done(_mcp.CLINE_QUERY)))
    assert after == _mcp.CL_AFTER_RULE
    assert _label(script, _cl_body(f"C:/tmp/pytest-0/{_mcp.CL_ALLOW_DIR}0", *_done(_mcp.CLINE_QUERY))) == after
    ends = [call for rule in script.rules for call in rule.reply.tool_calls if call.name == "submit_and_exit"]
    assert ends and all(len(json.loads(call.arguments)["summary"]) >= 10 for call in ends)


def test_the_corpus_cases_are_the_planned_ones():
    cases = _mcp.pick_cases()
    allow, deny = cases["allow"], cases["deny"]
    assert allow.e2e and deny.e2e
    assert allow.name == deny.name == "stub__query"
    role = _mcp.CORPUS_ROLE
    assert (allow.expect[role], allow.rule[role], allow.outcome[role]) == ("allow", "sql.read", "ok")
    assert (deny.expect[role], deny.rule[role], deny.outcome[role]) == ("deny", "sql.ddl", None)
    assert "SELECT" in allow.arguments and "DROP TABLE" in deny.arguments


def test_the_visible_tools_exclude_what_must_never_be_offered():
    visible = _mcp.visible_tools()
    assert "stub__query" in visible
    for bare in _mcp.never_offered():
        assert bare not in visible
    assert _mcp.opencode_tool_name("stub__query") == _mcp.OPENCODE_QUERY == "harness_stub__query"
    assert _mcp.cline_tool_name("stub__query") == _mcp.CLINE_QUERY == "harness__stub__query"


def test_the_gateway_config_and_policy_load_through_the_real_loaders(tmp_path, monkeypatch):
    config_file, policy_file = tmp_path / "mcp.yaml", tmp_path / "action_policy.yaml"
    config_file.write_text(_mcp.mcp_config_yaml("http://127.0.0.1:9/mcp"), encoding="utf-8")
    policy_file.write_text(_mcp.policy_yaml(), encoding="utf-8")
    monkeypatch.setattr(mcp_config, "_config", mcp_config._config)  # restored at teardown
    monkeypatch.setattr(action_config, "_policy", action_config._policy)
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_CONFIG_FILE", str(config_file))
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", str(policy_file))
    action_config.load()
    mcp_config.load()

    loaded = mcp_config.get_config()
    assert set(loaded.servers) == {mcp_corpus.SERVER}
    assert loaded.servers[mcp_corpus.SERVER].allow_insecure is True
    assert [skill.id for skill in loaded.skills] == [mcp_corpus.SKILL_ID]
    assert loaded.skills[0].tools == mcp_corpus.SKILL.tools  # the same tools as the corpus's skill
    # Only the corpus policy plus the two entries the cross-validation of a real file demands.
    assert yaml.safe_load(_mcp.policy_yaml())["mcp_tools"] == yaml.safe_load(mcp_corpus.POLICY)["mcp_tools"]


def test_the_roles_file_loads_and_agrees_with_the_corpus_matrix(tmp_path, monkeypatch):
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(_mcp.roles_json(), encoding="utf-8")
    monkeypatch.setattr(authz, "ROLE_PERMISSIONS", authz.ROLE_PERMISSIONS)  # restored at teardown
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(roles_file))
    authz.load()
    real = {role: set(permissions) for role, permissions in authz.ROLE_PERMISSIONS.items()}

    skill, ddl = f"skill:{mcp_corpus.SKILL_ID}", authz.PERMISSION_ACTION_SQL_DDL
    for corpus_role, wanted_skill, wanted_ddl in (("dev", True, False), ("dba", True, True), ("user", False, False)):
        permissions = real[_mcp.ROLE_MAP[corpus_role]]
        assert (skill in permissions, ddl in permissions, "mcp:connect" in permissions) == (
            wanted_skill, wanted_ddl, True), corpus_role
    # The harness role used for `dev` holds exactly the built-in user permissions plus the skill.
    assert real["user"] == {"query:submit", "audit:read:own", "mcp:connect", skill}
    monkeypatch.setattr(settings, "RBAC_ENABLED", True)
    assert authz.holds(Identity(user_id="u", role=_mcp.ROLE_MAP["dev"]), skill)
    assert not authz.holds(Identity(user_id="u", role=_mcp.ROLE_MAP["dev"]), ddl)


def test_the_corpus_matrix_is_what_configure_installs(tmp_path, monkeypatch):
    """`configure()` is the source of the matrix `roles_json` copies: they must not drift apart."""
    mcp_corpus.configure(monkeypatch, tmp_path, "http://127.0.0.1:9/mcp")
    matrix = {role: set(permissions) for role, permissions in authz.ROLE_PERMISSIONS.items()}
    mapped = {role: set(json.loads(_mcp.roles_json())[_mcp.ROLE_MAP[role]]) for role in matrix}
    for role, permissions in matrix.items():
        assert permissions <= mapped[role], (role, permissions - mapped[role])
    assert authz.PERMISSION_ACTION_SQL_DDL in mapped["dba"] and authz.PERMISSION_ACTION_SQL_DDL not in mapped["dev"]


def test_the_client_configs_have_the_shapes_the_clients_need():
    config = _mcp.opencode_config("http://127.0.0.1:1", "http://127.0.0.1:2", "secret-token")
    server = config["mcp"]["servers"]["harness"]
    assert server["type"] == "remote" and server["codemode"] is False
    assert server["url"] == "http://127.0.0.1:2/mcp"
    assert server["headers"] == {"Authorization": "Bearer secret-token"}
    assert "enabled" not in server  # OpenCode's key is `disabled`
    assert config["provider"]["harness"]["options"]["baseURL"] == "http://127.0.0.1:1/v1"  # the fake provider
    assert "secret-token" not in json.dumps(config["provider"])  # the token goes only to the MCP server

    entry = _mcp.cline_settings("http://127.0.0.1:2", "secret-token")["mcpServers"]["harness"]
    assert entry["type"] == "streamableHttp"  # without it Cline falls back to SSE
    assert entry["url"] == "http://127.0.0.1:2/mcp"
    assert entry["headers"] == {"Authorization": "Bearer secret-token"}


def test_the_launcher_parses_its_three_modes_and_demands_the_database_file(monkeypatch, tmp_path):
    assert _embedded_db.parse(["-m", "uvicorn", "app.main:app", "--port", "1"]) == (
        "module", "uvicorn", ["app.main:app", "--port", "1"])
    assert _embedded_db.parse(["-c", "print(1)", "arg"]) == ("code", "print(1)", ["arg"])
    assert _embedded_db.parse(["scripts/x.py", "create-user"]) == ("script", "scripts/x.py", ["create-user"])
    for bad in ([], ["-m"], ["-X", "dev"]):
        with pytest.raises(SystemExit):
            _embedded_db.parse(bad)

    monkeypatch.delenv(_embedded_db.SERVER_ENV, raising=False)
    monkeypatch.delenv(_embedded_db.DB_FILE_ENV, raising=False)
    with pytest.raises(SystemExit, match=_embedded_db.DB_FILE_ENV):
        _embedded_db.db_file()
    monkeypatch.setenv(_embedded_db.DB_FILE_ENV, "relative.db")
    with pytest.raises(SystemExit, match=_embedded_db.DB_FILE_ENV):
        _embedded_db.db_file()
    monkeypatch.setenv(_embedded_db.DB_FILE_ENV, str(tmp_path / "x.db"))
    assert _embedded_db.db_file() == str(tmp_path / "x.db")
    monkeypatch.setenv(_embedded_db.SERVER_ENV, "http://127.0.0.1:8088")
    with pytest.raises(SystemExit, match=_embedded_db.SERVER_ENV):
        _embedded_db.db_file()


def test_start_harness_without_a_launcher_keeps_its_argv():
    """`launcher=None` is the default every existing caller relies on (PRD-023 STORY-020)."""
    import inspect

    parameters = inspect.signature(_live.start_harness.__wrapped__).parameters
    assert list(parameters) == ["cwd", "env", "launcher"] and parameters["launcher"].default is None
