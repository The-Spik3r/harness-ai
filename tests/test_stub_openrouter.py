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
"""

import io
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
from app.models.messages import Message
from app.services.openrouter_client import GenerationParams, OpenRouterError, call_openrouter
from scripts import stub_openrouter
from scripts.stub_openrouter import ScriptError, load_script, make_server, parse_script

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
