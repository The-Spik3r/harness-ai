"""PRD-015 STORY-014: scripts/stub_openrouter.py, driven by the real call_openrouter.

The stub runs in a thread on an ephemeral port, and `settings.OPENROUTER_BASE_URL`
points at it, so every request below crosses a real socket through the real
`httpx` client and the real timeout. There is no database: nothing here
declares storage, so the module runs under `-m "not db"` with Docker off.

    AC 1  scripted content / finish_reason / usage; one ASCII log line per
          request with model, message count and parameter keys; the literal
          `--port --script` command (subprocess test)
    AC 2  last-user-message matching by substring or regex, first match wins,
          configured and built-in defaults, delay_seconds and fail_status
    AC 3  call_openrouter's result; a delay past OPENROUTER_TIMEOUT_SECONDS is
          retryable; fail_status 400 is not (503 and 429 are)
    AC 4  the Authorization value is never logged, on any path

PRD-017 STORY-014 (the tests from "scripted tool_calls" down; no PRD-015 test
above was edited):

    AC 1  a tool_calls reply: content null, type function, string arguments,
          call_<n> ids, finish_reason tool_calls; parsed by call_openrouter
    AC 2  role / last_role / after_call / advertises; role-less rules keep
          matching the last user message
    AC 3  the log adds tools=<n> calls=<n> and never names a tool or argument
    AC 4  tests/e2e/scripts/tool_loop.json (read, edit, npm test, final text)
"""

import io
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import httpx
import pytest

from app.config import settings
from app.models.messages import Message, ToolCallSpec
from app.services.upstream import Finish, ReasoningDelta, TextDelta, UpstreamError, UsageReport, stream_upstream
from app.services.openrouter_client import (
    GenerationParams,
    OpenRouterError,
    ToolParams,
    call_openrouter,
)
from scripts import stub_openrouter
from scripts.stub_openrouter import ScriptError, load_script, make_server, parse_script
from tests._providers import provider_file  # noqa: F401  (fixture)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_EXAMPLE = _REPO_ROOT / "tests" / "e2e" / "scripts" / "example.json"
_SECRET = "sk-secret-STORY014"

_SCRIPT = {
    "default": {"content": "configured default", "usage": {"prompt_tokens": 2, "completion_tokens": 3}},
    "rules": [
        {
            "contains": "rename foo",
            "content": "Renamed foo to bar.",
            "finish_reason": "length",
            "usage": {"prompt_tokens": 12, "completion_tokens": 30, "total_tokens": 42},
        },
        {"regex": r"(?i)^\s*hello\b", "content": "regex answer"},
        {"regex": r"hello", "content": "never reached: rule 1 matches first"},
        {"contains": "please be slow", "delay_seconds": 3, "content": "late"},
        {"contains": "bad upstream request", "fail_status": 400},
        {"contains": "upstream down", "fail_status": 503},
        {"contains": "rate limited", "fail_status": 429},
    ],
}


@pytest.fixture
def stub(monkeypatch):
    """Factory: (server, log) for a script dict, with the client pointed at it."""
    servers = []

    def start(script=None):
        log = io.StringIO()
        server = make_server(parse_script(_SCRIPT if script is None else script), log=log)
        # A short poll interval keeps shutdown() at teardown from waiting 0.5 s.
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        servers.append(server)
        port = server.server_address[1]
        monkeypatch.setattr(settings, "OPENROUTER_BASE_URL", f"http://127.0.0.1:{port}/v1")
        return server, log

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def _call(*contents, roles=None, **kwargs):
    roles = roles or ["user"] * len(contents)
    kwargs.setdefault("api_key", _SECRET)
    return call_openrouter([Message(r, c) for r, c in zip(roles, contents)], **kwargs)


def _lines(log):
    return [line for line in log.getvalue().splitlines() if line]


# --------------------------------------------------------------------------
# AC 1 / AC 3: the scripted result through call_openrouter
# --------------------------------------------------------------------------


def test_call_openrouter_returns_the_scripted_result(stub):
    stub()
    result = _call("please rename foo", model="m/x")
    assert result.response == "Renamed foo to bar."
    assert result.finish_reason == "length"
    assert result.tokens_used == 42
    assert result.input_tokens == 12
    assert result.output_tokens == 30
    assert result.model_used == "m/x"


def test_each_request_logs_model_message_count_and_parameter_keys(stub):
    _, log = stub()
    _call(
        "system prompt",
        "please rename foo",
        roles=["system", "user"],
        model="m/x",
        params=GenerationParams(temperature=0.2, max_tokens=50),
    )
    _call("hello there", model="m/y")
    lines = _lines(log)
    assert len(lines) == 2
    first, second = lines
    assert "model='m/x'" in first
    assert "messages=2" in first
    assert "params=[max_tokens,temperature]" in first
    assert "rule=0" in first and first.endswith("-> 200")
    assert "model='m/y'" in second and "params=[]" in second and "rule=1" in second


def test_log_is_ascii_and_never_carries_message_content(stub):
    _, log = stub()
    _call("rename foo -- café ☃ secret-prose-xyz", model="mödell/日本")
    text = log.getvalue()
    assert text.isascii()
    assert "secret-prose-xyz" not in text
    assert "caf" not in text
    # The non-ASCII model is escaped, not dropped.
    assert "model='m\\xf6dell/\\u65e5\\u672c'" in text


# --------------------------------------------------------------------------
# AC 2: matching, defaults
# --------------------------------------------------------------------------


def test_only_the_last_user_message_is_matched(stub):
    _, log = stub()
    # An earlier user turn carries the trigger; the last one does not.
    result = _call("please rename foo", "never mind", roles=["user", "user"])
    assert result.response == "configured default"
    # A trailing assistant turn is skipped when choosing the subject.
    result = _call("please rename foo", "assistant text", roles=["user", "assistant"])
    assert result.response == "Renamed foo to bar."
    labels = [line.split("rule=")[1].split()[0] for line in _lines(log)]
    assert labels == ["default", "0"]


def test_regex_rule_matches_and_the_first_match_wins(stub):
    stub()
    assert _call("  Hello stub").response == "regex answer"


def test_no_match_uses_the_configured_default(stub):
    stub()
    result = _call("nothing scripted for this")
    assert result.response == "configured default"
    assert result.finish_reason == "stop"
    assert (result.input_tokens, result.output_tokens, result.tokens_used) == (2, 3, 5)


def test_no_default_key_uses_the_built_in_default(stub):
    stub({"rules": [{"contains": "x", "content": "y"}]})
    result = _call("unmatched")
    assert result.response == "stub_openrouter: no rule matched"
    assert result.finish_reason == "stop"
    assert result.tokens_used == 2


def test_parts_list_content_is_matched_on_its_text_parts(stub):
    stub()
    body = {
        "model": "m",
        "messages": [{"role": "user", "content": [{"type": "text", "text": "please "}, {"type": "text", "text": "rename foo"}]}],
    }
    resp = httpx.post(f"{settings.OPENROUTER_BASE_URL}/chat/completions", json=body)
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "Renamed foo to bar."


# --------------------------------------------------------------------------
# AC 3: retryable and non-retryable faults
# --------------------------------------------------------------------------


def test_delay_past_the_timeout_raises_a_retryable_error(stub, monkeypatch):
    stub()
    monkeypatch.setattr(settings, "OPENROUTER_TIMEOUT_SECONDS", 0.3)
    started = time.monotonic()
    with pytest.raises(OpenRouterError) as info:
        _call("please be slow")
    assert time.monotonic() - started < 2.0
    assert info.value.retryable is True
    assert info.value.upstream_status is None


def test_delay_within_the_timeout_still_answers(stub):
    stub({"rules": [{"contains": "x", "delay_seconds": 0.2, "content": "late but fine"}]})
    assert _call("x").response == "late but fine"


def test_fail_status_400_raises_a_non_retryable_error(stub):
    stub()
    with pytest.raises(OpenRouterError) as info:
        _call("bad upstream request")
    assert info.value.retryable is False
    assert info.value.upstream_status == 400


@pytest.mark.parametrize("trigger,status", [("upstream down", 503), ("rate limited", 429)])
def test_fail_status_5xx_and_429_raise_retryable_errors(stub, trigger, status):
    _, log = stub()
    with pytest.raises(OpenRouterError) as info:
        _call(trigger)
    assert info.value.retryable is True
    assert info.value.upstream_status == status
    assert _lines(log)[-1].endswith(f"-> {status}")


# --------------------------------------------------------------------------
# `times`: a rule that answers its first N matches (PRD-015 STORY-015)
# --------------------------------------------------------------------------

_FLAKY = {
    "rules": [
        {"contains": "flaky", "times": 1, "fail_status": 503},
        {"contains": "flaky", "content": "recovered"},
    ]
}


def test_times_caps_a_rule_then_falls_through_to_the_next_match(stub):
    _, log = stub(_FLAKY)
    with pytest.raises(OpenRouterError) as info:
        _call("flaky")
    assert info.value.upstream_status == 503
    assert _call("flaky").response == "recovered"
    assert _call("flaky").response == "recovered"
    rules = [line.split(" rule=", 1)[1].split()[0] for line in _lines(log)]
    assert rules == ["0", "1", "1"]


def test_times_without_a_later_match_falls_through_to_default(stub):
    stub({"default": {"content": "fallback"}, "rules": [{"contains": "once", "times": 2, "content": "capped"}]})
    assert [_call("once").response for _ in range(3)] == ["capped", "capped", "fallback"]


def test_times_is_counted_per_server(stub):
    for _ in range(2):
        stub(_FLAKY)  # each start points the client at the new server
        with pytest.raises(OpenRouterError):
            _call("flaky")
        assert _call("flaky").response == "recovered"


def test_a_rule_without_times_is_never_capped():
    script = parse_script(_FLAKY)
    hits = {}
    assert [script.select("flaky", hits)[0] for _ in range(3)] == ["0", "1", "1"]
    assert script.select("flaky")[0] == "0"  # no `hits`: nothing is capped
    assert hits == {0: 1}


# --------------------------------------------------------------------------
# AC 4: the Authorization value is never logged
# --------------------------------------------------------------------------


def test_authorization_value_is_never_logged_on_any_path(stub, monkeypatch, capfd):
    _, log = stub()
    _call("please rename foo")
    _call("unmatched")
    for trigger in ("bad upstream request", "upstream down"):
        with pytest.raises(OpenRouterError):
            _call(trigger)
    monkeypatch.setattr(settings, "OPENROUTER_TIMEOUT_SECONDS", 0.3)
    with pytest.raises(OpenRouterError):
        _call("please be slow")
    base = settings.OPENROUTER_BASE_URL
    headers = {"Authorization": f"Bearer {_SECRET}"}
    assert httpx.post(f"{base}/chat/completions", content=b"not json", headers=headers).status_code == 400
    assert httpx.post(f"{base}/elsewhere", json={}, headers=headers).status_code == 404

    captured = capfd.readouterr()
    for text in (log.getvalue(), captured.out, captured.err):
        assert _SECRET not in text
        assert "Bearer" not in text
    assert len(_lines(log)) == 7


# --------------------------------------------------------------------------
# Request surface and server robustness
# --------------------------------------------------------------------------


def test_bad_body_and_wrong_path_do_not_break_the_server(stub):
    stub()
    base = settings.OPENROUTER_BASE_URL
    bad = httpx.post(f"{base}/chat/completions", content=b"{not json")
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == 400
    no_messages = httpx.post(f"{base}/chat/completions", json={"model": "m"})
    assert no_messages.status_code == 400
    assert httpx.post(f"{base}/models", json={}).status_code == 404
    assert httpx.get(f"{base}/models").status_code == 404
    assert _call("please rename foo").response == "Renamed foo to bar."


def test_health_answers_without_logging(stub):
    server, log = stub()
    resp = httpx.get(f"http://127.0.0.1:{server.server_address[1]}/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert log.getvalue() == ""


def test_response_body_has_the_chat_completion_shape(stub):
    stub()
    resp = httpx.post(
        f"{settings.OPENROUTER_BASE_URL}/chat/completions",
        json={"model": "m/z", "messages": [{"role": "user", "content": "hello"}]},
    )
    body = resp.json()
    assert body["object"] == "chat.completion"
    assert body["id"].startswith("chatcmpl-stub-")
    assert body["model"] == "m/z"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["choices"][0]["index"] == 0
    assert isinstance(body["created"], int)


# --------------------------------------------------------------------------
# Script validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "script,names",
    [
        ({"rules": [{"contains": "a", "regex": "b"}]}, "exactly one of contains or regex"),
        ({"rules": [{"content": "no matcher"}]}, "exactly one of contains or regex"),
        ({"rules": [{"regex": "("}]}, "rules[0]: regex does not compile"),
        ({"rules": [{"contains": "a", "fail_status": 200}]}, "fail_status"),
        ({"rules": [{"contains": "a", "fail_status": 503, "content": "x"}]}, "remove content"),
        ({"rules": [{"contains": "a", "delay_seconds": -1}]}, "delay_seconds"),
        ({"rules": [{"contains": "a", "usage": {"prompt_tokens": True}}]}, "usage.prompt_tokens"),
        ({"rules": [{"contains": "a", "usage": {"tokens": 1}}]}, "unknown usage key(s): tokens"),
        ({"rules": [{"contains": "a", "colour": "red"}]}, "rules[0]: unknown key(s): colour"),
        ({"rules": [{"contains": 3}]}, "contains must be a string"),
        ({"rules": [{"contains": "a", "content": 5}]}, "content must be a string"),
        ({"rules": [{"contains": "a", "finish_reason": 1}]}, "finish_reason"),
        ({"default": {"contains": "a"}}, "default: unknown key(s): contains"),
        ({"rules": [{"contains": "a", "times": 0}]}, "rules[0]: times must be an integer >= 1"),
        ({"rules": [{"contains": "a", "times": True}]}, "times must be an integer >= 1"),
        ({"rules": [{"contains": "a", "times": "1"}]}, "times must be an integer >= 1"),
        ({"rules": [{"contains": "a", "times": 1.5}]}, "times must be an integer >= 1"),
        ({"default": {"content": "x", "times": 1}}, "default: unknown key(s): times"),
        ({"rules": {}}, "rules must be a list"),
        ({"extra": 1}, "unknown top-level key(s): extra"),
        ([], "must be a JSON object"),
    ],
)
def test_bad_scripts_are_rejected_naming_the_field(script, names):
    with pytest.raises(ScriptError) as info:
        parse_script(script)
    assert names in str(info.value)


def test_the_example_script_loads_with_every_rule_kind():
    script = load_script(str(_EXAMPLE))
    rules = script.rules
    assert any(rule.contains is not None for rule in rules)
    assert any(rule.pattern is not None for rule in rules)
    assert any(rule.reply.delay_seconds > 0 for rule in rules)
    assert {rule.reply.fail_status for rule in rules} >= {400, 503}
    assert any(rule.times for rule in rules)
    assert script.default.content != "stub_openrouter: no rule matched"


# --------------------------------------------------------------------------
# The CLI, as AC 1 writes it
# --------------------------------------------------------------------------


def _read_line_within(stream, timeout):
    box = []
    reader = threading.Thread(target=lambda: box.append(stream.readline()), daemon=True)
    reader.start()
    reader.join(timeout)
    assert box, f"no line from the stub within {timeout}s"
    return box[0]


def test_cli_serves_the_script_on_the_given_port():
    proc = subprocess.Popen(
        [sys.executable, "scripts/stub_openrouter.py", "--port", "0", "--script", str(_EXAMPLE)],
        cwd=_REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        line = _read_line_within(proc.stdout, 10)
        assert line.startswith("stub_openrouter: listening on http://127.0.0.1:")
        base = line.split("listening on ", 1)[1].strip()
        resp = httpx.post(
            f"{base}/chat/completions",
            json={"model": "m", "messages": [{"role": "user", "content": "please rename foo"}]},
            headers={"Authorization": f"Bearer {_SECRET}"},
            timeout=10,
        )
        assert resp.status_code == 200
        assert resp.json()["choices"][0]["message"]["content"] == "Renamed `foo` to `bar`."
        log_line = _read_line_within(proc.stderr, 10)
        assert "model='m' messages=1 params=[] rule=0" in log_line
        assert _SECRET not in log_line
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_cli_rejects_a_bad_script_with_exit_2(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"rules": [{"regex": "("}]}', encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "scripts/stub_openrouter.py", "--port", "0", "--script", str(bad)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 2
    assert proc.stderr.startswith("stub_openrouter: rules[0]: regex does not compile")


def test_cli_rejects_a_missing_script_with_exit_2(tmp_path):
    assert stub_openrouter.main(["--port", "0", "--script", str(tmp_path / "missing.json")]) == 2


# --------------------------------------------------------------------------
# Containment: a test tool, never imported by the app (PRD 7.9)
# --------------------------------------------------------------------------


def test_nothing_under_app_mentions_the_stub():
    offenders = [
        str(path.relative_to(_REPO_ROOT))
        for path in (_REPO_ROOT / "app").rglob("*.py")
        if "stub_openrouter" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


# --------------------------------------------------------------------------
# PRD-017 STORY-014: scripted tool_calls, role / last_role / after_call / advertises
# --------------------------------------------------------------------------

_TOOL_LOOP = _REPO_ROOT / "tests" / "e2e" / "scripts" / "tool_loop.json"
_BASH_ARGS = '{"command":"npm test"}'
_TOOLS = ToolParams(
    tools=[
        {"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}},
        {"type": "function", "function": {"name": "shell", "parameters": {"type": "object"}}},
    ]
)


def _post(messages, tools=None):
    body = {"model": "m", "messages": messages}
    if tools is not None:
        body["tools"] = tools
    resp = httpx.post(f"{settings.OPENROUTER_BASE_URL}/chat/completions", json=body)
    assert resp.status_code == 200
    return resp.json()["choices"][0]


def _asst(name, call_id="toolu_x", arguments="{}"):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}
        ],
    }


def _answer(choice):
    return choice["message"]["content"]


def test_tool_calls_reply_parses_through_call_openrouter(stub):
    # AC 1: the story's exact reply, through the real client's D18 parsing rules.
    stub({"rules": [{"contains": "go", "tool_calls": [{"name": "bash", "arguments": _BASH_ARGS}]}]})
    result = _call("go", tools=_TOOLS)
    assert [(c.id, c.name, c.arguments) for c in result.tool_calls] == [("call_1", "bash", _BASH_ARGS)]
    assert result.finish_reason == "tool_calls"
    assert result.response == ""


def test_tool_calls_body_has_content_null_type_function_and_string_arguments(stub):
    stub(
        {
            "rules": [
                {"contains": "a", "tool_calls": [{"name": "bash", "arguments": _BASH_ARGS}]},
                {
                    "contains": "b",
                    "tool_calls": [{"name": "bash", "arguments": "{}"}],
                    "finish_reason": "stop",
                },
                {
                    "contains": "c",
                    "tool_calls": [{"name": "bash", "arguments": "{}"}],
                    "content": "text beside the call",
                },
            ]
        }
    )
    first = _post([{"role": "user", "content": "a"}])
    assert first["message"]["content"] is None
    call = first["message"]["tool_calls"][0]
    assert call["type"] == "function" and call["function"]["arguments"] == _BASH_ARGS
    assert isinstance(call["function"]["arguments"], str)
    assert first["finish_reason"] == "tool_calls"
    assert _post([{"role": "user", "content": "b"}])["finish_reason"] == "stop"
    third = _post([{"role": "user", "content": "c"}])
    assert third["message"]["content"] == "text beside the call"
    # A reply without calls keeps today's body: no tool_calls key at all.
    stub({"rules": [{"contains": "a", "content": "plain"}]})
    assert "tool_calls" not in _post([{"role": "user", "content": "a"}])["message"]


def test_generated_ids_are_unique_across_answers_and_explicit_ids_are_kept(stub):
    stub(
        {
            "rules": [
                {
                    "contains": "go",
                    "tool_calls": [
                        {"name": "a", "arguments": "{}"},
                        {"name": "b", "arguments": "{}", "id": "toolu_scripted"},
                        {"name": "c", "arguments": "{}"},
                    ],
                }
            ]
        }
    )
    first = [c["id"] for c in _post([{"role": "user", "content": "go"}])["message"]["tool_calls"]]
    second = [c["id"] for c in _post([{"role": "user", "content": "go"}])["message"]["tool_calls"]]
    assert first == ["call_1", "toolu_scripted", "call_2"]
    assert second == ["call_3", "toolu_scripted", "call_4"]


def _history():
    return [
        {"role": "user", "content": "start"},
        _asst("read", "id1"),
        {"role": "tool", "tool_call_id": "id1", "content": "marker-A"},
        _asst("edit", "id2"),
        {"role": "tool", "tool_call_id": "id2", "content": "marker-B"},
    ]


def test_role_tool_matches_the_last_tool_message(stub):
    stub(
        {
            "rules": [
                {"role": "tool", "contains": "marker-A", "content": "saw A"},
                {"role": "tool", "contains": "marker-B", "content": "saw B"},
            ]
        }
    )
    assert _answer(_post(_history())) == "saw B"
    # Only the first tool turn present: the A rule answers.
    assert _answer(_post(_history()[:3])) == "saw A"


def test_role_without_a_message_of_that_role_does_not_match(stub):
    stub({"rules": [{"role": "tool", "regex": "", "content": "tool"}], "default": {"content": "dflt"}})
    assert _answer(_post([{"role": "user", "content": "hi"}])) == "dflt"
    assert _answer(_post(_history())) == "tool"


def test_last_role_requires_the_final_turn(stub):
    stub({"rules": [{"last_role": "tool", "regex": "", "content": "ends on tool"}], "default": {"content": "dflt"}})
    assert _answer(_post(_history())) == "ends on tool"
    assert _answer(_post(_history() + [{"role": "user", "content": "more"}])) == "dflt"
    assert _answer(_post([])) == "dflt"


def test_after_call_and_advertises_qualify_a_rule(stub):
    stub(
        {
            "rules": [
                {"after_call": "edit", "advertises": "submit_and_exit", "regex": "", "content": "cline"},
                {"after_call": "edit", "regex": "", "content": "opencode"},
            ],
            "default": {"content": "dflt"},
        }
    )
    submit = {"type": "function", "function": {"name": "submit_and_exit"}}
    other = {"type": "function", "function": {"name": "shell"}}
    history = _history()  # the last assistant turn called "edit"
    assert _answer(_post(history, [other, submit])) == "cline"
    assert _answer(_post(history, [other])) == "opencode"
    assert _answer(_post(history)) == "opencode"  # no tools: advertises fails, after_call holds
    # The last assistant turn called "read", not "edit": neither rule applies.
    assert _answer(_post(history[:3], [submit])) == "dflt"
    # A malformed tools list is not validated; it just offers no names.
    assert _answer(_post(history, ["junk", {"function": 3}])) == "opencode"


def test_rules_without_role_keep_matching_the_last_user_message(stub):
    # AC 2: a role-less rule still tests the last user message when the conversation ends on a tool turn.
    stub({"rules": [{"contains": "start", "content": "user rule"}, {"regex": "marker", "content": "never"}]})
    assert _answer(_post(_history())) == "user rule"


def test_tool_loop_script_runs_read_edit_test_then_final_text(stub):
    # AC 4: the example loop through the real call_openrouter; client-style ids prove
    # that matching does not depend on ids, and each call passes the client's parsing.
    stub(json.loads(_TOOL_LOOP.read_text(encoding="utf-8")))
    messages = [Message("user", "TOOL-LOOP fix add()")]
    names = []
    reasons = []
    for result_text in ["function add(a, b) { return a - b; }", "edited", "3 passing"]:
        result = call_openrouter(messages, api_key=_SECRET, tools=_TOOLS)
        reasons.append(result.finish_reason)
        assert len(result.tool_calls) == 1
        call = result.tool_calls[0]
        names.append(call.name)
        assert call.id and isinstance(call.arguments, str)
        # The client rewrites the id; the next reply must not depend on it.
        rewritten = ToolCallSpec(id=f"toolu_{len(names)}", name=call.name, arguments=call.arguments)
        messages += [
            Message("assistant", "", tool_calls=(rewritten,)),
            Message("tool", result_text, tool_call_id=rewritten.id),
        ]
    final = call_openrouter(messages, api_key=_SECRET, tools=_TOOLS)
    assert names == ["read", "edit", "shell"]
    assert reasons == ["tool_calls"] * 3
    assert final.tool_calls == () and final.finish_reason == "stop"
    assert final.response == "Done: fixed add() in src/math.js and npm test passes."

    # The failure branch still ends the loop.
    messages[-1] = Message("tool", "1 failing", tool_call_id="toolu_3")
    failed = call_openrouter(messages, api_key=_SECRET, tools=_TOOLS)
    assert failed.tool_calls == () and failed.response == "The tests failed; stopping here."


def test_tool_loop_log_names_counts_never_arguments_or_tool_content(stub):
    _, log = stub(json.loads(_TOOL_LOOP.read_text(encoding="utf-8")))
    messages = [Message("user", "TOOL-LOOP fix add()")]
    first = call_openrouter(messages, api_key=_SECRET, tools=_TOOLS)
    spec = first.tool_calls[0]
    messages += [
        Message("assistant", "", tool_calls=(spec,)),
        Message("tool", "secret-tool-output-xyz function add", tool_call_id=spec.id),
    ]
    call_openrouter(messages, api_key=_SECRET, tools=_TOOLS)
    text = log.getvalue()
    lines = _lines(log)
    assert text.isascii()
    assert lines[0].endswith("tools=2 calls=1 -> 200")
    assert "params=[tools]" in lines[0] and "rule=0 " in lines[0]
    assert "calls=1" in lines[1]
    for leaked in ("src/math.js", "npm test", "read", "secret-tool-output-xyz", "path", _SECRET, "Bearer"):
        assert leaked not in text, leaked


def test_a_failed_answer_logs_zero_calls(stub):
    _, log = stub({"rules": [{"contains": "x", "fail_status": 503}]})
    httpx.post(
        f"{settings.OPENROUTER_BASE_URL}/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "x"}]},
    )
    assert _lines(log)[0].endswith("tools=0 calls=0 -> 503")


_CALL = {"name": "bash", "arguments": "{}"}


@pytest.mark.parametrize(
    "script,names",
    [
        ({"rules": [{"contains": "a", "tool_calls": []}]}, "rules[0]: tool_calls must be a non-empty list"),
        ({"rules": [{"contains": "a", "tool_calls": "bash"}]}, "tool_calls must be a non-empty list"),
        ({"rules": [{"contains": "a", "tool_calls": ["bash"]}]}, "rules[0].tool_calls[0]: must be an object"),
        ({"rules": [{"contains": "a", "tool_calls": [{**_CALL, "type": "function"}]}]}, "tool_calls[0]: unknown key(s): type"),
        ({"rules": [{"contains": "a", "tool_calls": [{"arguments": "{}"}]}]}, "tool_calls[0]: name must be a non-empty string"),
        ({"rules": [{"contains": "a", "tool_calls": [{"name": "", "arguments": "{}"}]}]}, "name must be a non-empty string"),
        ({"rules": [{"contains": "a", "tool_calls": [{"name": "bash", "arguments": {"a": 1}}]}]}, "tool_calls[0]: arguments must be a string"),
        ({"rules": [{"contains": "a", "tool_calls": [{"name": "bash"}]}]}, "arguments must be a string"),
        ({"rules": [{"contains": "a", "tool_calls": [{**_CALL, "id": ""}]}]}, "tool_calls[0]: id must be a non-empty string"),
        ({"rules": [{"contains": "a", "tool_calls": [{**_CALL, "id": "call_7"}]}]}, "must not look like a generated id"),
        ({"rules": [{"contains": "a", "tool_calls": [{**_CALL, "id": "x"}, {**_CALL, "id": "x"}]}]}, "tool_calls[1]: id repeats"),
        ({"rules": [{"contains": "a", "fail_status": 503, "tool_calls": [_CALL]}]}, "remove tool_calls"),
        ({"rules": [{"contains": "a", "content": None}]}, "content must be a string"),
        ({"rules": [{"contains": "a", "role": "robot"}]}, "rules[0]: role must be one of"),
        ({"rules": [{"contains": "a", "last_role": 3}]}, "rules[0]: last_role must be one of"),
        ({"rules": [{"contains": "a", "after_call": ""}]}, "rules[0]: after_call must be a non-empty string"),
        ({"rules": [{"contains": "a", "advertises": 1}]}, "rules[0]: advertises must be a non-empty string"),
        ({"default": {"content": "x", "role": "user"}}, "default: unknown key(s): role"),
        ({"default": {"tool_calls": [{**_CALL, "arguments": 5}]}}, "default.tool_calls[0]: arguments must be a string"),
    ],
)
def test_bad_tool_scripts_are_rejected_naming_the_field(script, names):
    with pytest.raises(ScriptError) as info:
        parse_script(script)
    assert names in str(info.value)


def test_a_rejected_arguments_value_is_never_echoed():
    with pytest.raises(ScriptError) as info:
        parse_script({"rules": [{"contains": "a", "tool_calls": [{"name": "b", "arguments": {"k": "s3cret-arg"}}]}]})
    assert "s3cret-arg" not in str(info.value)


def test_the_tool_loop_script_loads():
    script = load_script(str(_TOOL_LOOP))
    replies = [rule.reply for rule in script.rules]
    assert [len(r.tool_calls) for r in replies] == [1, 1, 1, 0, 0]
    assert any(rule.after_call for rule in script.rules)
    assert any(rule.role == "tool" for rule in script.rules)
    ids = [call.id for r in replies for call in r.tool_calls]
    assert None in ids and any(i for i in ids)


# --------------------------------------------------------------------------
# PRD-020 STORY-005: usage null, auth=yes|no, redirect_status
# --------------------------------------------------------------------------


def test_log_carries_auth_presence_only(stub):
    _, log = stub()
    _call("hello", api_key="sk-secret-value")
    [line] = _lines(log)
    assert line.endswith("-> 200") and " auth=yes " in line and "sk-secret-value" not in line


def test_usage_null_answers_a_null_usage(stub):
    port = stub({"rules": [], "default": {"content": "x", "usage": None}})[0].server_address[1]
    reply = httpx.post(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert reply.status_code == 200 and reply.json()["usage"] is None


def test_redirect_status_answers_the_status_with_a_location(stub):
    server, log = stub({"rules": [], "default": {"redirect_status": 307, "location": "http://127.0.0.1:9/x"}})
    port = server.server_address[1]
    reply = httpx.post(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert reply.status_code == 307 and reply.headers["location"] == "http://127.0.0.1:9/x"
    assert _lines(log)[0].endswith("-> 307")


@pytest.mark.parametrize("reply", [
    {"redirect_status": 200},
    {"redirect_status": 302, "content": "x"},
    {"location": "http://x/"},
])
def test_redirect_reply_is_validated(reply):
    with pytest.raises(ScriptError, match="redirect_status|location"):
        parse_script({"rules": [], "default": reply})


# --------------------------------------------------------------------------
# PRD-020 STORY-013: the stub streams when asked
# --------------------------------------------------------------------------


def _sse_post(extra=None, content="please rename foo"):
    body = {"model": "m", "messages": [{"role": "user", "content": content}], "stream": True}
    body.update(extra or {})
    return httpx.post(
        f"{settings.OPENROUTER_BASE_URL}/chat/completions",
        json=body,
        headers={"Authorization": f"Bearer {_SECRET}"},
    )


def _frames(response):
    """The `data:` payloads of an SSE body: parsed JSON chunks, and the literal [DONE]."""
    out = []
    for block in response.text.split("\n\n"):
        if not block:
            continue
        assert block.startswith("data: "), block
        payload = block[len("data: "):]
        out.append(payload if payload == "[DONE]" else json.loads(payload))
    return out


def test_stream_log_field(stub):
    _, log = stub()
    _sse_post()
    httpx.post(
        f"{settings.OPENROUTER_BASE_URL}/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "x"}]},
    )
    streamed, plain = _lines(log)
    assert " auth=yes stream=yes tools=0 calls=0 -> 200" in streamed
    assert " auth=no stream=no tools=0 calls=0 -> 200" in plain
    assert "params=[stream,stream_options]" not in streamed  # stream_options not sent here
    assert "params=[stream]" in streamed


def test_sse_body_shape(stub):
    stub()
    response = _sse_post({"stream_options": {"include_usage": True}})
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream"
    frames = _frames(response)
    assert frames[-1] == "[DONE]"
    chunks = frames[:-1]
    deltas = [c["choices"][0]["delta"].get("content") for c in chunks if c["choices"] and "content" in c["choices"][0]["delta"]]
    assert len(deltas) == 2 and "".join(deltas) == "Renamed foo to bar."
    assert all(deltas)  # both halves non-empty
    finish = [c for c in chunks if c["choices"] and c["choices"][0]["finish_reason"] is not None]
    assert [c["choices"][0]["finish_reason"] for c in finish] == ["length"]
    assert chunks[-1]["choices"] == [] and chunks[-1]["usage"] == {
        "prompt_tokens": 12, "completion_tokens": 30, "total_tokens": 42,
    }


def test_sse_usage_chunk_only_with_include_usage(stub):
    stub()
    without = _frames(_sse_post())
    assert not any("usage" in c for c in without[:-1])
    declined = _frames(_sse_post({"stream_options": {"include_usage": False}}))
    assert not any("usage" in c for c in declined[:-1])


def test_sse_tool_calls_arrive_as_two_fragments_each(stub):
    script = {"default": {"tool_calls": [{"name": "read", "arguments": '{"path": "a.py"}'}, {"name": "ls", "arguments": ""}]}}
    stub(script)
    chunks = _frames(_sse_post())[:-1]
    fragments = [c["choices"][0]["delta"]["tool_calls"][0] for c in chunks if c["choices"] and "tool_calls" in c["choices"][0]["delta"]]
    assert [f["index"] for f in fragments] == [0, 0, 1, 1]
    first, rest = fragments[0], fragments[1]
    assert first["id"] and first["function"]["name"] == "read" and first["type"] == "function"
    assert "id" not in rest and first["function"]["arguments"] + rest["function"]["arguments"] == '{"path": "a.py"}'
    assert fragments[2]["function"]["arguments"] == "" and fragments[3]["function"]["arguments"] == ""
    assert not any("content" in c["choices"][0]["delta"] for c in chunks if c["choices"])  # null content: no text delta


def test_non_stream_request_is_unchanged(stub):
    stub()
    response = httpx.post(
        f"{settings.OPENROUTER_BASE_URL}/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "please rename foo"}]},
    )
    assert response.headers["content-type"] == "application/json"
    assert response.json()["choices"][0]["message"]["content"] == "Renamed foo to bar."


def test_streaming_failure_and_header_value_are_handled_like_json(stub, capfd):
    _, log = stub()
    assert _sse_post(content="upstream down").status_code == 503
    _sse_post()
    captured = capfd.readouterr()
    for text in (log.getvalue(), captured.out, captured.err):
        assert _SECRET not in text


# --------------------------------------------------------------------------
# PRD-021 STORY-004: a reply may carry `stream: {chunk_chars, delay_ms, reasoning, fail_after}`
#
#   AC 1  chunk_chars cuts content and tool arguments; finish, usage, [DONE] follow
#   AC 2  delay_ms spaces every delta, the first included
#   AC 3  reasoning deltas (delta.reasoning) precede every content delta
#   AC 4  fail_after drops the connection: no finish chunk, no [DONE]
#   AC 5  the log carries no content or reasoning; no shape or no stream request: as today
# --------------------------------------------------------------------------


def _stream_script(shape, **reply):
    return {"default": {"stream": shape, **reply}}


def _sse_read(extra=None):
    """([(monotonic time, data payload)], start): the stream read line by line to EOF."""
    body = {"model": "m", "messages": [{"role": "user", "content": "hi"}], "stream": True}
    body.update(extra or {})
    seen = []
    start = time.monotonic()
    with httpx.stream(
        "POST", f"{settings.OPENROUTER_BASE_URL}/chat/completions", json=body,
        timeout=httpx.Timeout(10),
    ) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("data: "):
                seen.append((time.monotonic(), line[len("data: "):]))
    return seen, start


def _deltas(frames, key):
    return [
        c["choices"][0]["delta"][key]
        for c in frames
        if c != "[DONE]" and c["choices"] and key in c["choices"][0]["delta"]
    ]


def test_stream_chunk_chars_splits_content_and_ends_with_finish_usage_done(stub):
    stub(_stream_script({"chunk_chars": 4}, content="abcdefghij", usage={}))
    frames = _frames(_sse_post({"stream_options": {"include_usage": True}}))
    assert _deltas(frames, "content") == ["abcd", "efgh", "ij"]
    assert frames[-1] == "[DONE]"
    assert frames[-2]["choices"] == [] and frames[-2]["usage"]["total_tokens"] == 2
    assert frames[-3]["choices"][0]["finish_reason"] == "stop"


def test_stream_chunk_chars_splits_tool_arguments_into_nine_fragments(stub):
    arguments = "DROP TABLE users; -- " + "x" * 51  # 72 characters (PRD-021 T1)
    assert len(arguments) == 72
    stub(_stream_script({"chunk_chars": 8}, tool_calls=[{"name": "sql", "arguments": arguments}]))
    frames = _frames(_sse_post())
    raw = [t[0] for t in _deltas(frames, "tool_calls")]
    assert len(raw) == 9
    assert "".join(r["function"]["arguments"] for r in raw) == arguments
    assert all(r["function"]["arguments"] for r in raw)
    assert raw[0]["id"] and raw[0]["function"]["name"] == "sql"
    assert all("id" not in r and "name" not in r["function"] for r in raw[1:])


def test_stream_delay_ms_spaces_every_delta_including_the_first(stub):
    stub(_stream_script({"chunk_chars": 3, "delay_ms": 200}, content="abcdefghi"))
    seen, start = _sse_read()
    stamps = [t for t, data in seen if data != "[DONE]" and '"content"' in data]
    assert len(stamps) == 3
    # 10% margin; no upper bound (CI is slower).
    assert stamps[0] - start >= 0.18
    assert all(b - a >= 0.18 for a, b in zip(stamps, stamps[1:]))


def test_stream_reasoning_deltas_precede_content(stub):
    stub(_stream_script({"chunk_chars": 5, "reasoning": "thinking it over"}, content="the answer"))
    response = _sse_post()
    frames = _frames(response)
    reasoning = _deltas(frames, "reasoning")
    assert "".join(reasoning) == "thinking it over" and all(len(p) <= 5 for p in reasoning)
    assert "".join(_deltas(frames, "content")) == "the answer"
    kinds = [
        "r" if "reasoning" in c["choices"][0]["delta"] else "c"
        for c in frames[:-1]
        if c["choices"] and c["choices"][0]["delta"]
    ]
    assert kinds == sorted(kinds, reverse=True)  # every "r" before every "c"
    assert "reasoning_content" not in response.text


def test_stream_fail_after_drops_the_connection_without_finish(stub):
    stub(_stream_script({"chunk_chars": 2, "fail_after": 2}, content="abcdefgh", usage={}))
    seen, _ = _sse_read({"stream_options": {"include_usage": True}})
    frames = [json.loads(d) if d != "[DONE]" else d for _, d in seen]
    assert len(frames) == 2 and _deltas(frames, "content") == ["ab", "cd"]
    assert not any(c["choices"] and c["choices"][0]["finish_reason"] for c in frames)
    # K = 0: headers, then the close.
    stub(_stream_script({"fail_after": 0}, content="abcd"))
    assert _sse_read()[0] == []


def _file_registry(provider_file, port):
    provider_file(f"""
version: 1
default_model: local/m
providers:
  - name: local
    label: Local
    type: openai_compatible
    base_url: http://127.0.0.1:{port}/v1
    insecure_http: true
    models:
      - id: local/m
        upstream: up-local
        capabilities: {{streaming: true, reasoning: true}}
""")


def test_stream_upstream_maps_scripted_reasoning(stub, provider_file):
    server, _ = stub(_stream_script({"chunk_chars": 4, "reasoning": "hmm hmm"}, content="done now"))
    _file_registry(provider_file, server.server_address[1])
    events = list(stream_upstream([Message("user", "x")], model="local/m", api_key=None))
    # The adapter asks for usage, so the default reply's usage chunk follows the Finish.
    kinds = [type(e) for e in events if not isinstance(e, UsageReport)]
    assert kinds == [ReasoningDelta] * 2 + [TextDelta] * 2 + [Finish]
    assert "".join(e.text for e in events if isinstance(e, ReasoningDelta)) == "hmm hmm"


def test_stream_upstream_raises_upstream_error_after_fail_after(stub, provider_file):
    server, _ = stub(_stream_script({"chunk_chars": 2, "fail_after": 2}, content="abcdefgh"))
    _file_registry(provider_file, server.server_address[1])
    events = []
    with pytest.raises(UpstreamError) as info:
        for event in stream_upstream([Message("user", "x")], model="local/m", api_key=None):
            events.append(event)
    # PRD-021 §6.2: a dropped stream surfaces as UpstreamError, never a raw httpx error.
    assert info.value.retryable is False
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "abcd"
    assert not any(isinstance(e, Finish) for e in events)


def test_stream_shape_never_reaches_the_log(stub):
    _, log = stub(
        _stream_script({"chunk_chars": 3, "reasoning": "REASONING-SECRET-xyz"}, content="CONTENT-SECRET-xyz")
    )
    _sse_post()
    httpx.post(
        f"{settings.OPENROUTER_BASE_URL}/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "x"}]},
    )
    text = log.getvalue()
    assert "SECRET" not in text and "chunk_chars" not in text
    assert text.isascii()
    streamed, plain = _lines(log)
    assert streamed.endswith("stream=yes tools=0 calls=0 -> 200")
    assert plain.endswith("stream=no tools=0 calls=0 -> 200")


def test_shape_without_stream_request_answers_json_as_today(stub):
    shaped = {"stream": {"chunk_chars": 2, "reasoning": "why", "delay_ms": 1}, "content": "full text"}
    request = {"model": "m", "messages": [{"role": "user", "content": "x"}]}
    stub({"default": shaped})
    shaped_json = httpx.post(f"{settings.OPENROUTER_BASE_URL}/chat/completions", json=request).json()
    stub({"default": {"content": "full text"}})
    plain_json = httpx.post(f"{settings.OPENROUTER_BASE_URL}/chat/completions", json=request).json()
    message = shaped_json["choices"][0]["message"]
    assert message["content"] == "full text" and "reasoning" not in message
    for body in (shaped_json, plain_json):
        body.pop("id")
        body.pop("created")
    assert shaped_json == plain_json


@pytest.mark.parametrize(
    "reply, names",
    [
        ({"stream": "fast"}, "stream must be an object"),
        ({"stream": {"speed": 1}}, "stream: unknown key(s): speed"),
        ({"stream": {"chunk_chars": 0}}, "stream.chunk_chars must be an integer >= 1"),
        ({"stream": {"chunk_chars": True}}, "stream.chunk_chars must be an integer >= 1"),
        ({"stream": {"chunk_chars": "4"}}, "stream.chunk_chars must be an integer >= 1"),
        ({"stream": {"delay_ms": -1}}, "stream.delay_ms must be an integer >= 0"),
        ({"stream": {"fail_after": -1}}, "stream.fail_after must be an integer >= 0"),
        ({"stream": {"reasoning": ""}}, "stream.reasoning must be a non-empty string"),
        ({"stream": {"reasoning": 5}}, "stream.reasoning must be a non-empty string"),
        ({"stream": {}, "fail_status": 503}, "fail_status replaces the body; remove stream"),
    ],
)
def test_bad_stream_shapes_are_rejected_naming_the_field(reply, names):
    with pytest.raises(ScriptError) as info:
        parse_script({"default": reply})
    assert "default: " in str(info.value) and names in str(info.value)
    with pytest.raises(ScriptError) as info:  # a rule names its index
        parse_script({"rules": [{"contains": "a", **reply}]})
    assert "rules[0]: " in str(info.value) and names in str(info.value)


def test_a_rejected_reasoning_value_is_never_echoed():
    with pytest.raises(ScriptError) as info:
        parse_script({"default": {"stream": {"reasoning": 12345}}})
    assert "12345" not in str(info.value)
