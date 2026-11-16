"""PRD-017 STORY-016: what the OpenCode E2E renders, pinned in the everyday suite.

`tests/e2e/test_opencode.py` only runs with `--run-e2e`. The two things it
depends on are checked here without OpenCode, a database or a subprocess: the
stub script answers OpenCode's request sequence with the planned rules, and the
action policy decides each scripted call as the E2E asserts. A change to the
script or to the policy fails here, not only under `--run-e2e`.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import json
import re

from app.config import settings
from app.services import action_config, action_policy, tool_release
from app.services.action_adapters import ToolCall
from app.services.identity import Identity
from scripts.stub_openrouter import Request, parse_script
from tests.e2e import _opencode

_REPO = "C:/e2e/repo"
#: The tools OpenCode 2.0.10 advertises for `openai/gpt-4o` (STORY-016 live diagnosis).
_TOOLS = ("edit", "glob", "grep", "question", "read", "shell", "skill", "subagent", "webfetch", "websearch",
          "write", "execute")
_TASK = "E2E-OPENCODE-TASK [abcd1234] fix add() in src/calc.py, write its test, run the tests"


def _script():
    return parse_script(json.loads(_opencode.render_script(_REPO)))


def _calls(script) -> list:
    return [call for rule in script.rules for call in rule.reply.tool_calls]


def _body(*turns, tools=True) -> dict:
    messages = [{"role": "system", "content": "You are OpenCode."}, *turns]
    body = {"model": "openai/gpt-4o", "messages": messages, "stream": True}
    if tools:
        body["tools"] = [{"type": "function", "function": {"name": name}} for name in _TOOLS]
    return body


def _assistant(call_id: str, name: str) -> dict:
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name, "arguments": "{}"}}]}


def _tool(call_id: str, content: str) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def _label(script, body) -> str:
    return script.select_request(Request.from_body(body))[0]


def test_the_rendered_script_answers_opencode_s_sequence_with_the_planned_rules():
    script = _script()
    user = {"role": "user", "content": _TASK}
    read, read_out = _assistant("call_read_calc", "read"), _tool(
        "call_read_calc", "<path>C:/e2e/repo/src/calc.py</path>\n1: def add(a, b):\n2:     return a - b")
    edit, edit_out = _assistant("call_edit_calc", "edit"), _tool("call_edit_calc", "Edited file")
    write, write_out = _assistant("call_write_test", "write"), _tool("call_write_test", "Wrote file successfully.")
    shell = _assistant("call_unittest", "shell")

    assert _label(script, _body(user)) == _opencode.START_RULE
    assert _label(script, _body(user, read, read_out)) == _opencode.EDIT_RULE
    assert _label(script, _body(user, read, read_out, edit, edit_out)) == _opencode.WRITE_RULE
    assert _label(script, _body(user, read, read_out, edit, edit_out, write, write_out)) == _opencode.TEST_RULE
    done = [user, read, read_out, edit, edit_out, write, write_out, shell]
    assert _label(script, _body(*done, _tool("call_unittest", "Ran 1 test in 0.001s\n\nOK"))) == _opencode.DONE_RULE
    assert _label(script, _body(*done, _tool("call_unittest", "FAILED (failures=1)"))) == _opencode.FAILED_RULE

    drop = {"role": "user", "content": "E2E-OPENCODE-DROP [abcd1234] clean up the database"}
    assert _label(script, _body(drop)) == _opencode.DROP_RULE
    # A title request has no `tools`: no rule that advertises one may answer it.
    assert _label(script, _body(user, tools=False)) == _opencode.TITLE_RULE
    assert _label(script, _body(drop, tools=False)) == _opencode.TITLE_RULE


def test_the_scripted_calls_carry_paths_under_the_repository_and_the_planned_commands():
    calls = {call.id: json.loads(call.arguments) for call in _calls(_script())}
    assert set(calls) == {"call_drop", "call_read_calc", "call_edit_calc", "call_write_test", "call_unittest"}
    assert calls["call_read_calc"] == {"path": f"{_REPO}/src/calc.py"}
    assert calls["call_edit_calc"] == {"path": f"{_REPO}/src/calc.py", "oldString": "return a - b",
                                       "newString": "return a + b"}
    assert calls["call_write_test"] == {"path": f"{_REPO}/tests/test_calc.py", "content": _opencode.TEST_WRITTEN}
    assert calls["call_unittest"] == {"command": "python -m unittest -q"}
    assert calls["call_drop"] == {"command": 'sqlite3 app.db "DROP TABLE users"'}


def test_the_script_has_no_generated_style_ids_and_only_the_placeholder_for_paths():
    text = _opencode.SCRIPT.read_text(encoding="utf-8")
    # The stub generates `call_<n>` for a call without an id; a scripted id must not look like one.
    assert not re.search(r'"id":\s*"call_\d+"', text)
    assert all(call.id for call in _calls(_script()))
    assert text.count("@REPO@") == 3  # read, edit and write: the only paths in the script
    assert "@REPO@" not in _opencode.render_script(_REPO)


def test_the_rendered_policy_decides_each_scripted_call_as_planned(tmp_path, monkeypatch):
    policy = tmp_path / "action_policy.yaml"
    policy.write_text(_opencode.policy_yaml(_REPO), encoding="utf-8")
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", str(policy))
    action_config.load()  # conftest's _default_action_policy restores the policy afterwards
    identity = Identity("e2e", "user")

    def decide(*calls):
        return [(d.decision, d.rule) for d in action_policy.evaluate_all(calls, identity)]

    scripted = [ToolCall(c.id, c.name, c.arguments) for c in _calls(_script())]
    assert dict(zip([c.id for c in scripted], decide(*scripted))) == {
        "call_drop": ("deny", "sql.ddl"),
        "call_read_calc": ("allow", "fs.read"),
        "call_edit_calc": ("allow", "fs.write_in_workspace"),
        "call_write_test": ("allow", "fs.write_in_workspace"),
        "call_unittest": ("allow", "shell.allowlisted"),
    }
    # `execute` (CodeMode) stays unmapped, and the workspace root is what keeps the absolute paths allowed.
    execute = ToolCall("c1", "execute", json.dumps({"code": "1"}))
    outside = ToolCall("c2", "write", json.dumps({"path": "C:/elsewhere/x.py", "content": "x"}))
    assert decide(execute, outside) == [("deny", "tool.unknown"), ("deny", "fs.write_outside_workspace")]


def test_the_mirrored_denial_note_equals_the_release_step_s():
    assert _opencode.DENIAL_NOTE_TEMPLATE == tool_release.DENIAL_NOTE_TEMPLATE
