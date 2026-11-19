"""PRD-021 STORY-015: what the real-time Cline E2E renders, pinned in the everyday suite.

`tests/e2e/test_cline_realtime.py` only runs with `--run-e2e`. Its stub script, policy,
registry and roles file are checked here without Cline, a database or a subprocess.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import json

from app.config import settings
from app.services import action_config, action_policy, authz, provider_registry, tool_release
from app.services.action_adapters import ToolCall
from app.services.identity import Identity
from scripts.stub_openrouter import Request, parse_script
from tests import _providers
from tests.e2e import _cline_realtime as rt

_REPO = "C:/e2e/repo"
_SENTINEL = "RSN-abcd1234"
_NUDGE = "[SYSTEM] This run is not complete until you call one of these terminal completion tools: submit_and_exit."
_PROMPT = "E2E-RT [abcd1234] do it"


def _script():
    return parse_script(json.loads(rt.render_script(_REPO, _SENTINEL)))


def _body(directory: str, *turns) -> dict:
    """A Cline request: the system prompt names the working directory, the prompt and Cline's own nudge are user turns."""
    messages = [
        {"role": "system", "content": f"You are Cline. Current working directory: C:/tmp/pytest-0/{directory}0"},
        {"role": "user", "content": _PROMPT},
        {"role": "user", "content": _NUDGE},
        *turns,
    ]
    return {"model": "openai/gpt-4o", "messages": messages, "stream": True, "tool_choice": "auto",
            "tools": [{"type": "function", "function": {"name": name}} for name in rt.YOLO_TOOLS]}


def _label(script, body) -> str:
    return script.select_request(Request.from_body(body))[0]


def test_each_working_directory_selects_its_rule_and_the_note_selects_the_follow_up():
    script = _script()
    assert _label(script, _body(rt.TEXT_DIR)) == rt.TEXT_RULE
    assert _label(script, _body(rt.DROP_DIR)) == rt.DROP_RULE
    assert _label(script, _body(rt.REASON_DIR)) == rt.REASON_RULE
    note = {"role": "assistant", "content": rt.DENIAL_NOTE_TEMPLATE.format(
        name="run_commands", id="call_rt_drop", reason="sql.ddl")}
    assert _label(script, _body(rt.DROP_DIR, note, {"role": "user", "content": _NUDGE})) == rt.FOLLOWUP_RULE
    other = _body("elsewhere")
    assert _label(script, other) == "default"
    assert script.select_request(Request.from_body(other))[1].tool_calls[0].name == "submit_and_exit"


def test_every_scripted_reply_streams_in_small_paced_pieces():
    for rule in _script().rules:
        shape = rule.reply.stream
        assert shape is not None and 1 <= shape.chunk_chars <= 8 and shape.delay_ms > 0


def test_the_drop_call_is_cut_into_at_least_four_fragments():
    [call] = _script().rules[int(rt.DROP_RULE)].reply.tool_calls
    assert (call.id, call.name) == ("call_rt_drop", "run_commands")
    assert json.loads(call.arguments) == {"commands": ['sqlite3 app.db "DROP TABLE users"']}
    assert len(rt.argument_fragments(call.arguments, 6)) >= 4


def test_every_path_ends_in_a_submit_and_exit_call_the_policy_allows(tmp_path, monkeypatch):
    script = _script()
    # Cline's loop ends only on `submit_and_exit` (summary of at least 10 characters).
    for rule in (script.rules[int(rt.FOLLOWUP_RULE)], script.rules[int(rt.TEXT_RULE)], script.rules[int(rt.REASON_RULE)]):
        [call] = rule.reply.tool_calls
        assert call.name == "submit_and_exit" and len(json.loads(call.arguments)["summary"]) >= 10
    policy = tmp_path / "action_policy.yaml"
    policy.write_text(rt.policy_yaml(_REPO), encoding="utf-8")
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", str(policy))
    action_config.load()  # conftest's _default_action_policy restores the policy afterwards
    identity = Identity("e2e", "user")
    calls = [ToolCall(c.id, c.name, c.arguments)
             for reply in [*(r.reply for r in script.rules), script.default] for c in reply.tool_calls]
    decided = {c.id: (d.decision, d.rule) for c, d in zip(calls, action_policy.evaluate_all(calls, identity))}
    assert decided["call_rt_drop"] == ("deny", "sql.ddl")
    assert all(value == ("allow", "tool.opaque") for key, value in decided.items() if key != "call_rt_drop"), decided


def test_the_sentinel_is_only_in_the_reasoning_and_is_substituted():
    text = rt.SCRIPT.read_text(encoding="utf-8")
    assert text.count("@SENTINEL@") == 1
    assert "@SENTINEL@" not in rt.render_script(_REPO, _SENTINEL)
    for index, rule in enumerate(_script().rules):
        reply = rule.reply
        assert _SENTINEL not in (reply.content or "")
        reasoning = reply.stream.reasoning if reply.stream else None
        assert (reasoning is not None and _SENTINEL in reasoning) == (index == int(rt.REASON_RULE))


def test_the_registry_makes_the_model_stream_and_reason(tmp_path, monkeypatch):
    with _providers.providers_file(tmp_path, rt.registry_yaml("http://127.0.0.1:9/v1"), monkeypatch=monkeypatch):
        caps = provider_registry.resolve("openai/gpt-4o").capabilities
    assert (caps.tools, caps.streaming, caps.reasoning) == (True, True, True)


def test_the_roles_file_grants_real_time_to_user_and_both_to_auditor(tmp_path, monkeypatch):
    path = tmp_path / "roles.json"
    path.write_text(rt.roles_json(), encoding="utf-8")
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(path))
    monkeypatch.setattr(authz, "ROLE_PERMISSIONS", dict(authz.ROLE_PERMISSIONS))  # restored on teardown
    authz.load()
    matrix = authz.ROLE_PERMISSIONS
    assert authz.PERMISSION_STREAM_REALTIME in matrix["user"] and authz.PERMISSION_REASONING_VIEW not in matrix["user"]
    assert {authz.PERMISSION_STREAM_REALTIME, authz.PERMISSION_REASONING_VIEW} <= matrix["auditor"]


def test_the_denial_template_the_e2e_uses_equals_the_release_step_s():
    assert rt.DENIAL_NOTE_TEMPLATE == tool_release.DENIAL_NOTE_TEMPLATE
