"""PRD-017 STORY-017: what the Cline E2E renders, pinned in the everyday suite.

`tests/e2e/test_cline.py` only runs with `--run-e2e`. The things it depends on
are checked here without Cline, a database or a subprocess: the stub script
answers Cline's request sequence with the planned rules, every scripted call
carries Cline 4.x's shapes, and the Cline action policy file decides each call
as the E2E asserts. A change to the script or to the policy fails here, not only
under `--run-e2e`.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import json
import re

from app.config import settings
from app.services import action_config, action_policy
from app.services.action_adapters import BUILT_IN_TOOLS, ToolCall
from app.services.identity import Identity
from scripts.stub_openrouter import Request, parse_script
from tests.e2e import _cline, _opencode

_REPO = "C:/e2e/repo"
_TASK_REPO = f"C:/tmp/pytest-0/{_cline.TASK_DIR}0"
_DROP_REPO = f"C:/tmp/pytest-0/{_cline.DROP_DIR}0"
_NUDGE = "[SYSTEM] This run is not complete until you call one of these terminal completion tools: submit_and_exit."
_PROMPT = "E2E-CLINE-TASK [abcd1234] fix add() in src/calc.py, write its test, run the tests"


def _script():
    return parse_script(json.loads(_cline.render_script(_REPO)))


def _calls(script) -> list:
    return [call for reply in [*(rule.reply for rule in script.rules), script.default] for call in reply.tool_calls]


def _body(workspace: str, *turns) -> dict:
    """A Cline request as the planning probe recorded it: the system prompt names the working
    directory, the prompt and Cline's own nudge are two user turns, `tools` are the `--yolo` ones."""
    messages = [
        {"role": "system", "content": f"You are Cline. Current working directory: {workspace}"},
        {"role": "user", "content": _PROMPT},
        {"role": "user", "content": _NUDGE},
        *turns,
    ]
    return {
        "model": "openai/gpt-4o", "messages": messages, "stream": True, "tool_choice": "auto",
        "tools": [{"type": "function", "function": {"name": name}} for name in _cline.YOLO_TOOLS],
    }


def _assistant(call_id: str, name: str) -> dict:
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name, "arguments": "{}"}}]}


def _tool(call_id: str, content: str) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def _label(script, body) -> str:
    return script.select_request(Request.from_body(body))[0]


def _unittest_result(outcome: str) -> str:
    """Cline wraps the command's output in JSON text, with the unittest lines on stderr (probe item 9)."""
    return json.dumps([{"query": "python -m unittest -q",
                        "result": f"\n[stderr]\n---\r\nRan 1 test in 0.000s\r\n\r\n{outcome}\r\n", "success": True}])


def test_the_rendered_script_answers_cline_s_sequence_with_the_planned_rules():
    script = _script()
    read = _assistant("call_read_calc", "read_files")
    read_out = _tool("call_read_calc", json.dumps([{"query": f"{_TASK_REPO}/src/calc.py",
                                                    "result": "1 | def add(a, b):\n2 |     return a - b", "success": True}]))
    edit = _assistant("call_edit_calc", "editor")
    edit_out = _tool("call_edit_calc", json.dumps({"query": f"edit:{_TASK_REPO}/src/calc.py",
                                                   "result": f"Edited {_TASK_REPO}/src/calc.py\n```diff\n-a - b\n+a + b\n```"}))
    write = _assistant("call_write_test", "editor")
    write_out = _tool("call_write_test", json.dumps({"query": f"edit:{_TASK_REPO}/tests/test_calc.py",
                                                     "result": f"Edited {_TASK_REPO}/tests/test_calc.py"}))
    unittest = _assistant("call_unittest", "run_commands")
    history = [read, read_out, edit, edit_out]

    assert _label(script, _body(_TASK_REPO)) == _cline.START_RULE
    assert _label(script, _body(_TASK_REPO, read, read_out)) == _cline.EDIT_RULE
    assert _label(script, _body(_TASK_REPO, *history)) == _cline.WRITE_RULE
    assert _label(script, _body(_TASK_REPO, *history, write, write_out)) == _cline.TEST_RULE
    done = [*history, write, write_out, unittest]
    assert _label(script, _body(_TASK_REPO, *done, _tool("call_unittest", _unittest_result("OK")))) == _cline.DONE_RULE
    failed = _tool("call_unittest", _unittest_result("FAILED (failures=1)"))
    assert _label(script, _body(_TASK_REPO, *done, failed)) == _cline.FAILED_RULE

    # The drop run: request 1 is the drop call, request 2 follows the harness's note and Cline's nudge.
    assert _label(script, _body(_DROP_REPO)) == _cline.DROP_RULE
    note = {"role": "assistant", "content": _cline.DENIAL_NOTE_TEMPLATE.format(
        name="run_commands", id="call_drop", reason="sql.ddl")}
    second = _body(_DROP_REPO, note, {"role": "user", "content": _NUDGE})
    assert _label(script, second) == _cline.DROP_SUBMIT_RULE

    # A request that names neither directory reaches the default, which is a `submit_and_exit` too.
    other = _body("C:/tmp/elsewhere")
    assert _label(script, other) == "default"
    assert script.select_request(Request.from_body(other))[1].tool_calls[0].name == "submit_and_exit"


def test_the_scripted_calls_carry_cline_s_shapes_and_the_planned_paths():
    calls = {call.id: json.loads(call.arguments) for call in _calls(_script())}
    assert set(calls) == {"call_submit_drop", "call_drop", "call_read_calc", "call_edit_calc", "call_write_test",
                          "call_unittest", "call_submit_done", "call_submit_failed", "call_submit_default"}
    assert calls["call_read_calc"] == {"files": [{"path": f"{_REPO}/src/calc.py"}]}
    assert calls["call_edit_calc"] == {"path": f"{_REPO}/src/calc.py", "old_text": "return a - b",
                                       "new_text": "return a + b"}
    # `editor` on an existing file needs `old_text`: the test file is written by replacing its placeholder line.
    assert calls["call_write_test"] == {"path": f"{_REPO}/tests/test_calc.py",
                                        "old_text": _opencode.TEST_ORIGINAL, "new_text": _opencode.TEST_WRITTEN}
    assert calls["call_unittest"] == {"commands": ["python -m unittest -q"]}
    assert calls["call_drop"] == {"commands": ['sqlite3 app.db "DROP TABLE users"']}
    for call_id, arguments in calls.items():
        if call_id.startswith("call_submit_"):
            assert set(arguments) == {"summary", "verified"}, call_id
            assert len(arguments["summary"]) >= 10, call_id  # Cline's schema: a shorter summary is rejected, and it loops
    assert calls["call_submit_done"]["verified"] is True and calls["call_submit_failed"]["verified"] is False


def test_the_script_has_no_generated_style_ids_and_only_the_placeholder_for_paths():
    text = _cline.SCRIPT.read_text(encoding="utf-8")
    assert not re.search(r'"id":\s*"call_\d+"', text)
    assert all(call.id for call in _calls(_script()))
    assert text.count("@REPO@") == 3  # read, edit and write: the only paths in the script
    assert "@REPO@" not in _cline.render_script(_REPO)
    rules = json.loads(text)["rules"]
    assert rules[int(_cline.DROP_RULE)]["contains"] == _cline.DROP_DIR
    assert rules[int(_cline.START_RULE)]["contains"] == _cline.TASK_DIR
    assert all(rule.get("role") == "system" for rule in (rules[int(_cline.DROP_RULE)], rules[int(_cline.START_RULE)]))


def test_the_cline_policy_decides_each_scripted_call_as_planned(tmp_path, monkeypatch):
    policy = tmp_path / "action_policy.yaml"
    policy.write_text(_cline.policy_yaml(_REPO), encoding="utf-8")
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
        "call_submit_drop": ("allow", "tool.opaque"),
        "call_submit_done": ("allow", "tool.opaque"),
        "call_submit_failed": ("allow", "tool.opaque"),
        "call_submit_default": ("allow", "tool.opaque"),
    }
    outside = ToolCall("c1", "editor", json.dumps({"path": "C:/elsewhere/x.py", "old_text": "a", "new_text": "b"}))
    rm = ToolCall("c2", "run_commands", json.dumps({"commands": ["rm -rf /"]}))
    unknown = ToolCall("c3", "ask_question", json.dumps({"question": "?"}))
    got = decide(outside, rm, unknown)
    assert got[0] == ("deny", "fs.write_outside_workspace")
    assert got[1][0] == "deny"
    assert got[2] == ("deny", "tool.unknown")


def test_the_policy_file_maps_cline_s_tools_as_the_built_in_mapping_does(tmp_path, monkeypatch):
    policy_file = tmp_path / "action_policy.yaml"
    policy_file.write_text(_cline.policy_yaml(_REPO), encoding="utf-8")
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", str(policy_file))
    action_config.load()
    policy = action_config.get_policy()
    for name in ("run_commands", "read_files", "editor", "fetch_web_content"):
        assert policy.tools[name] == BUILT_IN_TOOLS[name], name
    # `apply_patch` reads `input` only (Cline's spelling); the built-in one also reads OpenCode's `patchText`.
    assert (policy.tools["apply_patch"].kind, policy.tools["apply_patch"].target, policy.tools["apply_patch"].format) == (
        "fs_write", "input", "patch")
    assert set(policy.tools) == {"run_commands", "read_files", "editor", "apply_patch", "fetch_web_content"}
    # `submit_and_exit` is unmapped: it is only an opaque tool, and `allow`.
    assert "submit_and_exit" not in policy.tools
    assert policy.opaque_tools["submit_and_exit"] == "allow"
