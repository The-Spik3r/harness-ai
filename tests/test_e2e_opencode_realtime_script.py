"""PRD-021 STORY-014: what the real-time OpenCode E2E renders, pinned in the everyday suite.

`tests/e2e/test_opencode_realtime.py` only runs with `--run-e2e`. Its stub script, registry,
roles file and SSE helpers are checked here without OpenCode, a database or a subprocess.
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
from tests.e2e import _opencode, _opencode_realtime as rt

_REPO = "C:/e2e/repo"
_SENTINEL = "RSN-abcd1234"
_TOOLS = ("edit", "read", "shell", "write", "execute")


def _script():
    return parse_script(json.loads(rt.render_script(_REPO, _SENTINEL)))


def _label(script, prompt: str) -> str:
    body = {"model": "openai/gpt-4o", "stream": True,
            "messages": [{"role": "system", "content": "You are OpenCode."}, {"role": "user", "content": prompt}],
            "tools": [{"type": "function", "function": {"name": name}} for name in _TOOLS]}
    return script.select_request(Request.from_body(body))[0]


def test_each_trigger_selects_its_rule():
    script = _script()
    assert _label(script, "E2E-RT-DROP [x] clean up") == rt.DROP_RULE
    assert _label(script, "E2E-RT-TEXT [x] say it") == rt.TEXT_RULE
    assert _label(script, "E2E-RT-REASON [x] think") == rt.REASON_RULE


def test_every_scripted_reply_streams_in_small_paced_pieces():
    rules = _script().rules[:3]
    for rule in rules:
        shape = rule.reply.stream
        assert shape is not None and 1 <= shape.chunk_chars <= 8 and shape.delay_ms > 0
    assert rules[2].reply.stream.reasoning


def test_the_drop_call_is_cut_into_at_least_four_fragments():
    [call] = _script().rules[0].reply.tool_calls
    assert call.id == "call_rt_drop"
    assert json.loads(call.arguments) == {"command": 'sqlite3 app.db "DROP TABLE users"'}
    assert len(rt.argument_fragments(call.arguments, 6)) >= 4
    assert "".join(rt.argument_fragments(call.arguments, 6)) == call.arguments


def test_the_sentinel_is_only_in_the_reasoning_and_is_substituted():
    text = rt.SCRIPT.read_text(encoding="utf-8")
    assert text.count("@SENTINEL@") == 1 and "@REPO@" not in text
    rendered = rt.render_script(_REPO, _SENTINEL)
    assert "@SENTINEL@" not in rendered
    for index, rule in enumerate(_script().rules):
        reply = rule.reply
        assert _SENTINEL not in (reply.content or "")
        reasoning = reply.stream.reasoning if reply.stream else None
        assert (reasoning is not None and _SENTINEL in reasoning) == (index == 2)


def test_the_policy_denies_the_scripted_drop(tmp_path, monkeypatch):
    policy = tmp_path / "action_policy.yaml"
    policy.write_text(_opencode.policy_yaml(_REPO), encoding="utf-8")
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", str(policy))
    action_config.load()  # conftest's _default_action_policy restores the policy afterwards
    [call] = _script().rules[0].reply.tool_calls
    [decision] = action_policy.evaluate_all([ToolCall(call.id, call.name, call.arguments)], Identity("e2e", "user"))
    assert (decision.decision, decision.rule) == ("deny", "sql.ddl")


def test_the_registry_makes_the_model_stream_and_reason(tmp_path, monkeypatch):
    with _providers.providers_file(tmp_path, rt.registry_yaml("http://127.0.0.1:9/v1"), monkeypatch=monkeypatch):
        caps = provider_registry.resolve(rt.HARNESS_MODEL).capabilities
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
    assert authz.PERMISSION_QUERY_SUBMIT in matrix["user"] and authz.PERMISSION_QUERY_SUBMIT in matrix["auditor"]
    # The literals mirror authz's constants; admin keeps the built-in matrix.
    assert (authz.PERMISSION_STREAM_REALTIME, authz.PERMISSION_REASONING_VIEW) == ("stream:realtime", "reasoning:view")
    assert set(rt.ADMIN_PERMISSIONS) == {
        authz.PERMISSION_QUERY_SUBMIT, authz.PERMISSION_QUERY_BYOK, authz.PERMISSION_AUDIT_READ_ALL,
        authz.PERMISSION_AUDIT_READ_OWN, authz.PERMISSION_STATS_READ}


def test_parse_sse_reads_chunks_and_done():
    def frame(delta, finish=None):
        return json.dumps({"id": "chatcmpl-harness-rt-x", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]})

    chunks = rt.parse_sse([
        (0.0, frame({"role": "assistant"})), (0.1, frame({"reasoning_content": "hm"})),
        (0.2, frame({"content": "hi"})), (0.3, frame({}, "stop")), (0.4, "[DONE]"),
    ])
    assert [c["role"] for c in chunks[:1]] == ["assistant"]
    assert chunks[1]["reasoning"] == "hm" and chunks[2]["content"] == "hi"
    assert chunks[3]["finish_reason"] == "stop" and chunks[4]["done"] is True
    assert {c["id"] for c in chunks[:-1]} == {"chatcmpl-harness-rt-x"}
    assert rt.parse_sse(None) == []


def test_opencode_config_adds_the_reasoning_key_and_leaves_the_base_alone():
    base = _opencode.opencode_config("http://x", "t")
    config = rt.opencode_config("http://x", "t", {"compatibility": {"reasoningField": "reasoning_content"}})
    assert config["provider"]["harness"]["models"][rt.HARNESS_MODEL]["compatibility"] == {
        "reasoningField": "reasoning_content"}
    assert "compatibility" not in base["provider"]["harness"]["models"][rt.HARNESS_MODEL]


def test_the_denial_template_the_e2e_uses_equals_the_release_step_s():
    assert _opencode.DENIAL_NOTE_TEMPLATE == tool_release.DENIAL_NOTE_TEMPLATE
