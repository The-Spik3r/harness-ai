"""A scripted stand-in for OpenRouter, for end-to-end runs (PRD-015 Section 7.9).

**This is a test tool, not shipped behaviour.** Nothing under `app/` imports it
(tests/test_stub_openrouter.py checks that), and production never points at it.

Why it exists (PRD-015 Risk 7, D10): outbound OpenRouter calls fail from the
development machine (TLS / 401), so a live `/query` or `/v1` request always
ends in an upstream fault, and the Aider E2E story needs a model that answers
with one specific edit. The harness reaches this stub through the
`OPENROUTER_BASE_URL` setting, which accepts plaintext `http://` on a loopback
host only (app/config.py).

It speaks just enough Chat Completions for `call_openrouter`: `POST
<anything>/chat/completions` answers from a JSON script, and `GET /health`
answers 200 so a runner can wait for it. Standard library only.

Usage:

    python scripts/stub_openrouter.py --port 9100 --script tests/e2e/scripts/example.json
    OPENROUTER_BASE_URL=http://127.0.0.1:9100/v1 uvicorn app.main:app --port 8765

Script format (JSON):

    {
      "default": {"content": "...", "finish_reason": "stop"},
      "rules": [
        {"contains": "rename foo", "content": "...", "usage": {"prompt_tokens": 12}},
        {"regex": "(?i)^slow", "delay_seconds": 5, "content": "late"},
        {"contains": "upstream down", "fail_status": 503}
      ]
    }

Each rule has exactly one matcher, `contains` (substring) or `regex`
(`re.search`), tested against the **last `user` message**. The first match
wins; no match uses `default` (or a built-in one when the script has none).
A reply sets `content`, `finish_reason` and `usage`, or `fail_status`
(400-599) instead of a body; either may be preceded by `delay_seconds`.
`usage` fields default to 1 prompt + 1 completion token, and `total_tokens`
to their sum.

Each request is logged as one ASCII line on stderr: the model, the message
count, the request's other parameter keys and the rule that answered. Message
content and request headers -- `Authorization` above all -- are never logged.
"""

import argparse
import itertools
import json
import re
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional, Sequence, TextIO

_PREFIX = "stub_openrouter"

_SCRIPT_KEYS = frozenset({"rules", "default"})
_REPLY_KEYS = frozenset({"content", "finish_reason", "usage", "delay_seconds", "fail_status"})
_BODY_KEYS = frozenset({"content", "finish_reason", "usage"})
_MATCHER_KEYS = frozenset({"contains", "regex"})
_USAGE_KEYS = frozenset({"prompt_tokens", "completion_tokens", "total_tokens"})

_BUILT_IN_DEFAULT_CONTENT = f"{_PREFIX}: no rule matched"

# A client that hangs up during a delay makes the late write fail with one of
# these (ConnectionAbortedError on Windows). The stub has nothing to tell it.
_DISCONNECTS = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)


class ScriptError(ValueError):
    """A script file that cannot be served, found when it loads rather than per request."""


@dataclass(frozen=True)
class Reply:
    content: str = ""
    finish_reason: Optional[str] = "stop"
    usage: Optional[dict] = None
    delay_seconds: float = 0.0
    fail_status: Optional[int] = None


@dataclass(frozen=True)
class Rule:
    reply: Reply
    contains: Optional[str] = None
    pattern: Optional["re.Pattern[str]"] = None

    def matches(self, subject: str) -> bool:
        if self.contains is not None:
            return self.contains in subject
        return self.pattern.search(subject) is not None


@dataclass(frozen=True)
class Script:
    rules: tuple
    default: Reply

    def select(self, subject: str) -> "tuple[str, Reply]":
        """(label, reply): the first matching rule's index, or "default"."""
        for index, rule in enumerate(self.rules):
            if rule.matches(subject):
                return str(index), rule.reply
        return "default", self.default


def _is_count(value: Any) -> bool:
    # bool is a subclass of int: True/False must not pass as 1/0.
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _parse_usage(raw: Any, where: str) -> dict:
    if not isinstance(raw, dict):
        raise ScriptError(f"{where}: usage must be an object, got {raw!r}")
    unknown = sorted(set(raw) - _USAGE_KEYS)
    if unknown:
        raise ScriptError(f"{where}: unknown usage key(s): {', '.join(unknown)}")
    for key, value in raw.items():
        if not _is_count(value):
            raise ScriptError(f"{where}: usage.{key} must be a non-negative integer, got {value!r}")
    prompt = raw.get("prompt_tokens", 1)
    completion = raw.get("completion_tokens", 1)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": raw.get("total_tokens", prompt + completion),
    }


def _parse_reply(raw: dict, where: str) -> Reply:
    delay = raw.get("delay_seconds", 0)
    if isinstance(delay, bool) or not isinstance(delay, (int, float)) or delay < 0:
        raise ScriptError(f"{where}: delay_seconds must be a number >= 0, got {delay!r}")

    if "fail_status" in raw:
        status = raw["fail_status"]
        if isinstance(status, bool) or not isinstance(status, int) or not 400 <= status <= 599:
            raise ScriptError(f"{where}: fail_status must be an integer from 400 to 599, got {status!r}")
        with_body = sorted(_BODY_KEYS & set(raw))
        if with_body:
            raise ScriptError(
                f"{where}: fail_status replaces the body; remove {', '.join(with_body)}"
            )
        return Reply(delay_seconds=float(delay), fail_status=status)

    content = raw.get("content", "")
    if not isinstance(content, str):
        raise ScriptError(f"{where}: content must be a string, got {content!r}")
    finish_reason = raw.get("finish_reason", "stop")
    if finish_reason is not None and not isinstance(finish_reason, str):
        raise ScriptError(f"{where}: finish_reason must be a string or null, got {finish_reason!r}")
    return Reply(
        content=content,
        finish_reason=finish_reason,
        usage=_parse_usage(raw.get("usage", {}), where),
        delay_seconds=float(delay),
    )


def _parse_rule(raw: Any, index: int) -> Rule:
    where = f"rules[{index}]"
    if not isinstance(raw, dict):
        raise ScriptError(f"{where}: must be an object, got {raw!r}")
    unknown = sorted(set(raw) - _REPLY_KEYS - _MATCHER_KEYS)
    if unknown:
        raise ScriptError(f"{where}: unknown key(s): {', '.join(unknown)}")
    matchers = sorted(_MATCHER_KEYS & set(raw))
    if len(matchers) != 1:
        raise ScriptError(f"{where}: needs exactly one of contains or regex, got {matchers or 'neither'}")
    reply = _parse_reply(raw, where)
    if "contains" in raw:
        if not isinstance(raw["contains"], str):
            raise ScriptError(f"{where}: contains must be a string, got {raw['contains']!r}")
        return Rule(reply=reply, contains=raw["contains"])
    if not isinstance(raw["regex"], str):
        raise ScriptError(f"{where}: regex must be a string, got {raw['regex']!r}")
    try:
        pattern = re.compile(raw["regex"])
    except re.error as exc:
        raise ScriptError(f"{where}: regex does not compile: {exc}") from exc
    return Rule(reply=reply, pattern=pattern)


def parse_script(raw: Any) -> Script:
    if not isinstance(raw, dict):
        raise ScriptError(f"a script must be a JSON object, got {type(raw).__name__}")
    unknown = sorted(set(raw) - _SCRIPT_KEYS)
    if unknown:
        raise ScriptError(f"unknown top-level key(s): {', '.join(unknown)}")
    rules = raw.get("rules", [])
    if not isinstance(rules, list):
        raise ScriptError(f"rules must be a list, got {rules!r}")
    if "default" in raw:
        default_raw = raw["default"]
        if not isinstance(default_raw, dict):
            raise ScriptError(f"default: must be an object, got {default_raw!r}")
        unknown = sorted(set(default_raw) - _REPLY_KEYS)
        if unknown:
            raise ScriptError(f"default: unknown key(s): {', '.join(unknown)}")
        default = _parse_reply(default_raw, "default")
    else:
        default = _parse_reply({"content": _BUILT_IN_DEFAULT_CONTENT}, "default")
    return Script(
        rules=tuple(_parse_rule(rule, index) for index, rule in enumerate(rules)),
        default=default,
    )


def load_script(path: str) -> Script:
    with open(path, encoding="utf-8") as handle:
        try:
            raw = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ScriptError(f"{path} is not valid JSON: {exc}") from exc
    return parse_script(raw)


def _last_user_text(messages: list) -> str:
    """The content of the last `user` message; a parts list is joined from its text parts."""
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict) and isinstance(part.get("text"), str)
                )
            return ""
    return ""


class _StubHandler(BaseHTTPRequestHandler):
    # Bound per server by make_server's subclass, so two stubs in one process stay apart.
    script: Script
    log_stream: TextIO
    log_lock: threading.Lock
    ids: "itertools.count"

    def log_message(self, *args):  # the access log would be a second, unscrubbed line
        pass

    def _log(self, line: str) -> None:
        # ASCII only: a non-ASCII model name must not break a cp1252 console.
        safe = line.encode("ascii", "backslashreplace").decode("ascii")
        with self.log_lock:
            self.log_stream.write(safe + "\n")
            self.log_stream.flush()

    def _send_json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except _DISCONNECTS:
            pass

    def _send_error_body(self, status: int, message: str) -> None:
        self._send_json(status, {"error": {"message": f"{_PREFIX}: {message}", "code": status}})

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's spelling
        if self.path.rstrip("/") == "/health":
            self._send_json(200, {"status": "ok"})
        else:
            self._send_error_body(404, f"no route for GET {self.path}")

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler's spelling
        # Content-Length is the only header this handler ever reads.
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length)
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._log(f"{_PREFIX}: POST {ascii(self.path)} -> 404")
            self._send_error_body(404, "only POST .../chat/completions is served")
            return
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
            self._log(f"{_PREFIX}: POST {ascii(self.path)} unreadable body -> 400")
            self._send_error_body(400, "body must be a JSON object with a messages list")
            return

        messages = body["messages"]
        model = body.get("model")
        params = sorted(str(key) for key in body if key not in ("model", "messages"))
        label, reply = self.script.select(_last_user_text(messages))
        status = reply.fail_status or 200
        self._log(
            f"{_PREFIX}: POST {ascii(self.path)} model={ascii(model)} messages={len(messages)} "
            f"params=[{','.join(params)}] rule={label} delay={reply.delay_seconds:g} -> {status}"
        )

        if reply.delay_seconds:
            time.sleep(reply.delay_seconds)
        if reply.fail_status is not None:
            self._send_error_body(reply.fail_status, "scripted failure")
            return
        self._send_json(
            200,
            {
                "id": f"chatcmpl-stub-{next(self.ids)}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": reply.content},
                        "finish_reason": reply.finish_reason,
                    }
                ],
                "usage": dict(reply.usage),
            },
        )


class _StubServer(ThreadingHTTPServer):
    # A handler asleep on a delay rule must never hold up shutdown.
    daemon_threads = True


def make_server(
    script: Script,
    host: str = "127.0.0.1",
    port: int = 0,
    log: Optional[TextIO] = None,
) -> ThreadingHTTPServer:
    """A bound, not yet serving, stub. Port 0 picks a free port: read server_address[1]."""
    handler = type(
        "_BoundStubHandler",
        (_StubHandler,),
        {
            "script": script,
            "log_stream": log if log is not None else sys.stderr,
            "log_lock": threading.Lock(),
            "ids": itertools.count(1),
        },
    )
    return _StubServer((host, port), handler)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stub_openrouter.py",
        description="Scripted Chat Completions stub for E2E runs (a test tool, PRD-015 7.9).",
    )
    parser.add_argument("--port", type=int, required=True, help="port to listen on (0 picks a free one)")
    parser.add_argument("--script", required=True, help="path to the JSON script file")
    parser.add_argument("--host", default="127.0.0.1", help="interface to bind (default 127.0.0.1)")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        script = load_script(args.script)
    except (OSError, ScriptError) as exc:
        print(f"{_PREFIX}: {exc}", file=sys.stderr)
        return 2
    server = make_server(script, host=args.host, port=args.port)
    host, port = server.server_address[:2]
    print(f"{_PREFIX}: listening on http://{host}:{port}/v1", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
