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
(`re.search`), tested against the **last message of its `role`** (default
`user`; `""` when there is no user message). The first match wins; no match
uses `default` (or a built-in one when the script has none).
A reply sets `content`, `finish_reason` and `usage`, or `fail_status`
(400-599) instead of a body; either may be preceded by `delay_seconds`.
`usage` fields default to 1 prompt + 1 completion token, and `total_tokens`
to their sum; `"usage": null` answers with a null usage (a provider that
reports none, PRD-020 D8). `redirect_status` (301, 302, 303, 307, 308) with an
optional `location` answers a redirect instead of a body (PRD-020 D5). A rule with `times: N` answers its first N matches and is then
skipped as if it did not match, so "fail once, then answer" is two rules with
the same matcher; the count is per stub process.

Tool calls (PRD-017 STORY-014). A reply may carry `tool_calls`, a non-empty
list of `{"name": str, "arguments": str, "id"?: str}`. The body then has
`content: null` (unless the script sets `content`), every call has `type:
"function"`, an omitted id is generated as `call_<n>` from a per-server
counter, and `finish_reason` defaults to `"tool_calls"`. `arguments` must be a
string and is emitted as given (PRD-017 D13): an object is refused, never
serialized. A scripted id may not look like `call_<digits>`, so a generated id
never collides with one.

A rule may add qualifiers, all ANDed with its matcher (`default` rejects them):
`role` (`system|user|assistant|tool`: the matcher tests the last message of
that role, and the rule does not match when there is none), `last_role` (the
conversation must end on that role), `after_call` (the last assistant turn
called a tool of this name; independent of ids, arguments and tool-result text,
which clients rewrite) and `advertises` (the request's `tools` list offers a
function of this name, so one script can serve OpenCode and Cline). `{"regex":
""}` is the "any content" matcher. To end a loop, answer with text (OpenCode
stops on it) or, for Cline, with a `submit_and_exit` call gated by `advertises`.

The stub streams when asked (PRD-020 STORY-013): a body with `"stream": true`
is answered as server-sent events carrying the same reply (content in two
deltas, each tool call in two fragments, a finish chunk, the usage chunk only
when `stream_options.include_usage` is true and the reply has usage, then
`data: [DONE]`). `complete()` never sends `stream`, so every other request is
answered as before.

A reply may carry `stream: {chunk_chars, delay_ms, reasoning, fail_after}`
(PRD-021 F10), used only when the request streams; any other request gets the
reply's JSON as before. Frames go out in this order: `reasoning` deltas (as
`delta.reasoning`), content deltas, tool-call fragments, the finish chunk, the
usage chunk, `[DONE]`. `chunk_chars` cuts reasoning, content and each call's
`arguments` into pieces of at most that many characters (default: halves);
`delay_ms` is slept before every delta, the first included; `fail_after: K`
sends K deltas and then closes the connection with no finish chunk and no
`[DONE]`. The log line never carries the shape, content or reasoning.

Messages mode (PRD-022 STORY-006). `POST <anything>/messages` answers from the
SAME script (same rules, matchers and `times` counts) as an Anthropic Messages
JSON body, or as SSE when the request carries `"stream": true`. The request is
viewed like a Chat one: top-level `system` is a leading `system` message, a user
turn made only of `tool_result` blocks reads as role `tool`, tool names come from
`tool["name"]`, and `tool_use` blocks count for `after_call`. Auth is
`Authorization: Bearer <key>` (what the SDK sends) or `x-api-key: <key>`. Four
additive reply keys also work on Chat: `stop_reason` (one of the seven Anthropic
values; mapped to a Chat `finish_reason` there, and a script's `finish_reason`
is mapped forward on /messages; not combinable with `finish_reason`),
`retry_after` (integer >= 1, only with `fail_status`; sent as `Retry-After`),
`fault` (`timeout`: read the request, send nothing and hold the connection until
the server closes; `malformed`: status 200 and a truncated body or first frame;
replaces the body like `fail_status`) and, inside `usage`,
`cache_creation_input_tokens` / `cache_read_input_tokens` (Messages bodies only;
`prompt_tokens` is then Anthropic's `input_tokens`, which EXCLUDES the cache
counts). `stream.reasoning` becomes a `thinking` block. A tool call's
`arguments` must parse to a JSON object on /messages (else a 500, never echoed).
`server.endpoint_hits()` returns `{"chat": n, "messages": n}`, counting every
POST to either endpoint, faulted ones included.

Each request is logged as one ASCII line on stderr: the model, the message
count, the request's other parameter keys, the rule that answered, and the
counts `tools=<n>` (tools offered) and `calls=<n>` (calls answered). Message
content, tool names, arguments and request headers -- `Authorization` and
`x-api-key` above all -- are never logged; only the presence of the key header
is, as `auth=yes|no` (and `ver=yes|no` for `anthropic-version` on /messages).
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
_REPLY_KEYS = frozenset(
    {"content", "finish_reason", "usage", "delay_seconds", "fail_status", "tool_calls",
     "redirect_status", "location", "stream", "stop_reason", "retry_after", "fault"}
)
_BODY_KEYS = frozenset(
    {"content", "finish_reason", "usage", "tool_calls", "stream", "stop_reason"}
)
_STREAM_KEYS = frozenset({"chunk_chars", "delay_ms", "reasoning", "fail_after"})
_REDIRECT_STATUSES = (301, 302, 303, 307, 308)
_DEFAULT_LOCATION = "http://127.0.0.1:9/never"
_MATCHER_KEYS = frozenset({"contains", "regex"})
_RULE_KEYS = frozenset({"times"})  # rule only: `default` rejects it as unknown
_ROLES = frozenset({"system", "user", "assistant", "tool"})
_QUALIFIER_KEYS = frozenset({"role", "last_role", "after_call", "advertises"})  # rule only
_TOOL_CALL_KEYS = frozenset({"id", "name", "arguments"})
_GENERATED_ID = re.compile(r"call_\d+")
_CHAT_USAGE_KEYS = frozenset({"prompt_tokens", "completion_tokens", "total_tokens"})
_CACHE_USAGE_KEYS = frozenset({"cache_creation_input_tokens", "cache_read_input_tokens"})
_USAGE_KEYS = _CHAT_USAGE_KEYS | _CACHE_USAGE_KEYS

# The seven stop reasons STORY-001 recorded, and how the two endpoints translate (PRD-022 6.5).
_STOP_REASONS = (
    "end_turn", "max_tokens", "stop_sequence", "tool_use", "pause_turn", "refusal",
    "model_context_window_exceeded",
)
_STOP_TO_FINISH = {
    "end_turn": "stop", "stop_sequence": "stop", "max_tokens": "length",
    "model_context_window_exceeded": "length", "tool_use": "tool_calls",
    "refusal": "content_filter",
}  # pause_turn has no Chat twin: verbatim
_FINISH_TO_STOP = {
    "stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use",
    "content_filter": "refusal",
}  # any other finish_reason is sent verbatim
_FAULTS = ("timeout", "malformed")
_HOLD_SECONDS = 60  # a `timeout` fault's ceiling when nothing closes the server first
_ERROR_TYPES = {
    400: "invalid_request_error", 401: "authentication_error", 403: "permission_error",
    404: "not_found_error", 429: "rate_limit_error", 529: "overloaded_error",
}

_BUILT_IN_DEFAULT_CONTENT = f"{_PREFIX}: no rule matched"

# A client that hangs up during a delay makes the late write fail with one of
# these (ConnectionAbortedError on Windows). The stub has nothing to tell it.
_DISCONNECTS = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)


class ScriptError(ValueError):
    """A script file that cannot be served, found when it loads rather than per request."""


@dataclass(frozen=True)
class ScriptedCall:
    name: str
    arguments: str  # a string, emitted as given (PRD-017 D13)
    id: Optional[str] = None  # None: generated as call_<n> per answer


@dataclass(frozen=True)
class StreamShape:
    """How a streamed reply is cut and paced (PRD-021 F10); `{}` flags the shape with defaults."""

    chunk_chars: Optional[int] = None  # None: today's two halves
    delay_ms: int = 0  # slept before each delta frame
    reasoning: Optional[str] = None  # emitted first, as delta.reasoning
    fail_after: Optional[int] = None  # drop the connection after this many delta frames


@dataclass(frozen=True)
class Reply:
    content: Optional[str] = ""
    finish_reason: Optional[str] = "stop"
    usage: Optional[dict] = None
    delay_seconds: float = 0.0
    fail_status: Optional[int] = None
    tool_calls: tuple = ()
    redirect_status: Optional[int] = None
    location: str = _DEFAULT_LOCATION
    stream: Optional[StreamShape] = None
    # PRD-022 STORY-006: additive keys; the defaults leave every old script's behaviour alone.
    stop_reason: Optional[str] = None  # None: derived from finish_reason on /messages
    retry_after: Optional[int] = None  # sent as Retry-After with fail_status
    fault: Optional[str] = None  # "timeout" | "malformed", replaces the body
    cache_creation_tokens: int = 0  # Messages bodies only
    cache_read_tokens: int = 0


@dataclass(frozen=True)
class Request:
    """The parsed view of a request that a rule is tested against."""

    messages: tuple
    tool_names: frozenset

    @classmethod
    def from_body(cls, body: dict) -> "Request":
        tools = body.get("tools")
        names = set()
        if isinstance(tools, list):  # not validated: a malformed entry just has no name
            for tool in tools:
                function = tool.get("function") if isinstance(tool, dict) else None
                if isinstance(function, dict) and isinstance(function.get("name"), str):
                    names.add(function["name"])
        return cls(messages=tuple(body["messages"]), tool_names=frozenset(names))

    @classmethod
    def from_messages_body(cls, body: dict) -> "Request":
        """The same view of an Anthropic Messages body (PRD-022 STORY-006).

        `system` becomes a leading system message, a user turn holding only
        `tool_result` blocks becomes role `tool`, tool names come from `name`.
        """
        messages = []
        system = body.get("system")
        if isinstance(system, list):
            system = "".join(
                block.get("text", "")
                for block in system
                if isinstance(block, dict) and isinstance(block.get("text"), str)
            )
        if isinstance(system, str) and system:
            messages.append({"role": "system", "content": system})
        for message in body["messages"]:
            content = message.get("content") if isinstance(message, dict) else None
            if (
                isinstance(content, list)
                and content
                and all(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)
            ):
                messages.append({"role": "tool", "content": "".join(_result_text(b) for b in content)})
            else:
                messages.append(message)
        tools = body.get("tools")
        names = {
            tool["name"]
            for tool in (tools if isinstance(tools, list) else [])
            if isinstance(tool, dict) and isinstance(tool.get("name"), str)
        }
        return cls(messages=tuple(messages), tool_names=frozenset(names))


def _result_text(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
    return ""


def _role(message: Any) -> Optional[str]:
    return message.get("role") if isinstance(message, dict) else None


def _text(message: dict) -> str:
    """A message's content; a parts list is joined from its text parts, null reads as ""."""
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


def _last_text(messages: Sequence, role: str) -> Optional[str]:
    """The content of the last message of `role`, or None when there is none."""
    for message in reversed(messages):
        if _role(message) == role:
            return _text(message)
    return None


def _called_names(message: dict) -> "set[str]":
    names = set()
    calls = message.get("tool_calls")
    if isinstance(calls, list):
        for call in calls:
            function = call.get("function") if isinstance(call, dict) else None
            if isinstance(function, dict) and isinstance(function.get("name"), str):
                names.add(function["name"])
    content = message.get("content")  # Messages mode: tool_use blocks (PRD-022 STORY-006)
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use" and isinstance(block.get("name"), str):
                names.add(block["name"])
    return names


@dataclass(frozen=True)
class Rule:
    reply: Reply
    contains: Optional[str] = None
    pattern: Optional["re.Pattern[str]"] = None
    times: Optional[int] = None
    role: Optional[str] = None
    last_role: Optional[str] = None
    after_call: Optional[str] = None
    advertises: Optional[str] = None

    def matches(self, request: Request) -> bool:
        messages = request.messages
        if self.last_role is not None and (not messages or _role(messages[-1]) != self.last_role):
            return False
        if self.advertises is not None and self.advertises not in request.tool_names:
            return False
        if self.after_call is not None:
            last_assistant = next((m for m in reversed(messages) if _role(m) == "assistant"), None)
            if last_assistant is None or self.after_call not in _called_names(last_assistant):
                return False
        subject = _last_text(messages, self.role or "user")
        if subject is None:
            if self.role is not None:
                return False  # no message of that role
            subject = ""  # today's behaviour: no user message reads as ""
        if self.contains is not None:
            return self.contains in subject
        return self.pattern.search(subject) is not None


@dataclass(frozen=True)
class Script:
    rules: tuple
    default: Reply

    def select(self, subject: str, hits: Optional[dict] = None) -> "tuple[str, Reply]":
        """select_request for a conversation of one user message."""
        request = Request(messages=({"role": "user", "content": subject},), tool_names=frozenset())
        return self.select_request(request, hits)

    def select_request(self, request: Request, hits: Optional[dict] = None) -> "tuple[str, Reply]":
        """(label, reply): the first matching rule's index, or "default".

        `hits` is the caller's {rule index: answers so far}, which a rule with
        `times` is checked against and charged to. Without it no rule is capped.
        """
        for index, rule in enumerate(self.rules):
            if not rule.matches(request):
                continue
            if rule.times is not None and hits is not None:
                if hits.get(index, 0) >= rule.times:
                    continue
                hits[index] = hits.get(index, 0) + 1
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
    return {  # exactly the Chat keys: the cache counts are split off by _cache_counts
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": raw.get("total_tokens", prompt + completion),
    }


def _cache_counts(raw: Any) -> "tuple[int, int]":
    """(cache_creation, cache_read) of an already validated usage object; (0, 0) for none."""
    if not isinstance(raw, dict):
        return 0, 0
    return raw.get("cache_creation_input_tokens", 0), raw.get("cache_read_input_tokens", 0)


def _parse_stream(raw: Any, where: str) -> StreamShape:
    """The `stream:` shape (PRD-021 F10). `reasoning` is model output: never echoed in an error."""
    at = f"{where}: stream"
    if not isinstance(raw, dict):
        raise ScriptError(f"{at} must be an object, got {raw!r}")
    unknown = sorted(set(raw) - _STREAM_KEYS)
    if unknown:
        raise ScriptError(f"{at}: unknown key(s): {', '.join(unknown)}")
    chunk_chars = raw.get("chunk_chars")
    if "chunk_chars" in raw and not (_is_count(chunk_chars) and chunk_chars >= 1):
        raise ScriptError(f"{at}.chunk_chars must be an integer >= 1, got {chunk_chars!r}")
    delay_ms = raw.get("delay_ms", 0)
    if not _is_count(delay_ms):
        raise ScriptError(f"{at}.delay_ms must be an integer >= 0, got {delay_ms!r}")
    fail_after = raw.get("fail_after")
    if "fail_after" in raw and not _is_count(fail_after):
        raise ScriptError(f"{at}.fail_after must be an integer >= 0, got {fail_after!r}")
    reasoning = raw.get("reasoning")
    if "reasoning" in raw and (not isinstance(reasoning, str) or not reasoning):
        raise ScriptError(f"{at}.reasoning must be a non-empty string")
    return StreamShape(
        chunk_chars=chunk_chars, delay_ms=delay_ms, reasoning=reasoning, fail_after=fail_after
    )


def _parse_tool_calls(raw: Any, where: str) -> tuple:
    if not isinstance(raw, list) or not raw:
        raise ScriptError(f"{where}: tool_calls must be a non-empty list")
    calls = []
    seen = set()
    for index, entry in enumerate(raw):
        at = f"{where}.tool_calls[{index}]"
        if not isinstance(entry, dict):
            raise ScriptError(f"{at}: must be an object")
        unknown = sorted(set(entry) - _TOOL_CALL_KEYS)
        if unknown:
            raise ScriptError(f"{at}: unknown key(s): {', '.join(unknown)}")
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise ScriptError(f"{at}: name must be a non-empty string")
        # No value is echoed: arguments is model output (PRD-017 D13).
        if not isinstance(entry.get("arguments"), str):
            raise ScriptError(f"{at}: arguments must be a string (emitted as given, never serialized)")
        call_id = entry.get("id")
        if "id" in entry:
            if not isinstance(call_id, str) or not call_id:
                raise ScriptError(f"{at}: id must be a non-empty string")
            if _GENERATED_ID.fullmatch(call_id):
                raise ScriptError(f"{at}: id must not look like a generated id (call_<digits>)")
            if call_id in seen:
                raise ScriptError(f"{at}: id repeats an earlier call's id")
            seen.add(call_id)
        calls.append(ScriptedCall(name=name, arguments=entry["arguments"], id=call_id))
    return tuple(calls)


def _parse_reply(raw: dict, where: str) -> Reply:
    delay = raw.get("delay_seconds", 0)
    if isinstance(delay, bool) or not isinstance(delay, (int, float)) or delay < 0:
        raise ScriptError(f"{where}: delay_seconds must be a number >= 0, got {delay!r}")

    if "retry_after" in raw:
        retry_after = raw["retry_after"]
        if not (_is_count(retry_after) and retry_after >= 1):
            raise ScriptError(f"{where}: retry_after must be an integer >= 1, got {retry_after!r}")
        if "fail_status" not in raw:
            raise ScriptError(f"{where}: retry_after needs fail_status")

    if "fault" in raw:
        fault = raw["fault"]
        if not isinstance(fault, str) or fault not in _FAULTS:
            raise ScriptError(f"{where}: fault must be one of {', '.join(_FAULTS)}, got {fault!r}")
        others = sorted(({"fail_status", "redirect_status"} | _BODY_KEYS) & set(raw))
        if others:
            raise ScriptError(f"{where}: fault replaces the body; remove {', '.join(others)}")
        return Reply(delay_seconds=float(delay), fault=fault)

    if "fail_status" in raw:
        status = raw["fail_status"]
        if isinstance(status, bool) or not isinstance(status, int) or not 400 <= status <= 599:
            raise ScriptError(f"{where}: fail_status must be an integer from 400 to 599, got {status!r}")
        with_body = sorted(_BODY_KEYS & set(raw))
        if with_body:
            raise ScriptError(
                f"{where}: fail_status replaces the body; remove {', '.join(with_body)}"
            )
        return Reply(delay_seconds=float(delay), fail_status=status, retry_after=raw.get("retry_after"))

    if "redirect_status" in raw:
        status = raw["redirect_status"]
        if isinstance(status, bool) or status not in _REDIRECT_STATUSES:
            raise ScriptError(
                f"{where}: redirect_status must be one of {', '.join(map(str, _REDIRECT_STATUSES))}, got {status!r}"
            )
        with_body = sorted(_BODY_KEYS & set(raw))
        if with_body:
            raise ScriptError(
                f"{where}: redirect_status replaces the body; remove {', '.join(with_body)}"
            )
        location = raw.get("location", _DEFAULT_LOCATION)
        if not isinstance(location, str) or not location:
            raise ScriptError(f"{where}: location must be a non-empty string, got {location!r}")
        return Reply(delay_seconds=float(delay), redirect_status=status, location=location)
    if "location" in raw:
        raise ScriptError(f"{where}: location needs redirect_status")

    calls = _parse_tool_calls(raw["tool_calls"], where) if "tool_calls" in raw else ()
    # With calls, content defaults to null and finish_reason to "tool_calls".
    content = raw.get("content", None if calls else "")
    if not (isinstance(content, str) or (content is None and calls)):
        raise ScriptError(f"{where}: content must be a string, got {content!r}")
    finish_reason = raw.get("finish_reason", "tool_calls" if calls else "stop")
    if finish_reason is not None and not isinstance(finish_reason, str):
        raise ScriptError(f"{where}: finish_reason must be a string or null, got {finish_reason!r}")
    stop_reason = raw.get("stop_reason")
    if "stop_reason" in raw:
        if "finish_reason" in raw:
            raise ScriptError(f"{where}: stop_reason and finish_reason are two spellings of one thing; use one")
        if not isinstance(stop_reason, str) or stop_reason not in _STOP_REASONS:
            raise ScriptError(f"{where}: stop_reason must be one of {', '.join(_STOP_REASONS)}, got {stop_reason!r}")
        finish_reason = _STOP_TO_FINISH.get(stop_reason, stop_reason)  # what Chat answers
    shape = _parse_stream(raw["stream"], where) if "stream" in raw else None
    cache = _cache_counts(raw.get("usage"))
    return Reply(
        content=content,
        finish_reason=finish_reason,
        usage=None if raw.get("usage", {}) is None else _parse_usage(raw.get("usage", {}), where),
        delay_seconds=float(delay),
        tool_calls=calls,
        stream=shape,
        stop_reason=stop_reason,
        cache_creation_tokens=cache[0],
        cache_read_tokens=cache[1],
    )


def _parse_rule(raw: Any, index: int) -> Rule:
    where = f"rules[{index}]"
    if not isinstance(raw, dict):
        raise ScriptError(f"{where}: must be an object, got {raw!r}")
    unknown = sorted(set(raw) - _REPLY_KEYS - _MATCHER_KEYS - _RULE_KEYS - _QUALIFIER_KEYS)
    if unknown:
        raise ScriptError(f"{where}: unknown key(s): {', '.join(unknown)}")
    matchers = sorted(_MATCHER_KEYS & set(raw))
    if len(matchers) != 1:
        raise ScriptError(f"{where}: needs exactly one of contains or regex, got {matchers or 'neither'}")
    times = raw.get("times")
    if "times" in raw and not (_is_count(times) and times >= 1):
        raise ScriptError(f"{where}: times must be an integer >= 1, got {times!r}")
    for key in ("role", "last_role"):
        if key in raw and not (isinstance(raw[key], str) and raw[key] in _ROLES):
            raise ScriptError(
                f"{where}: {key} must be one of {', '.join(sorted(_ROLES))}, got {raw[key]!r}"
            )
    for key in ("after_call", "advertises"):
        if key in raw and not (isinstance(raw[key], str) and raw[key]):
            raise ScriptError(f"{where}: {key} must be a non-empty string, got {raw[key]!r}")
    reply = _parse_reply(raw, where)
    qualifiers = {key: raw.get(key) for key in _QUALIFIER_KEYS}
    if "contains" in raw:
        if not isinstance(raw["contains"], str):
            raise ScriptError(f"{where}: contains must be a string, got {raw['contains']!r}")
        return Rule(reply=reply, contains=raw["contains"], times=times, **qualifiers)
    if not isinstance(raw["regex"], str):
        raise ScriptError(f"{where}: regex must be a string, got {raw['regex']!r}")
    try:
        pattern = re.compile(raw["regex"])
    except re.error as exc:
        raise ScriptError(f"{where}: regex does not compile: {exc}") from exc
    return Rule(reply=reply, pattern=pattern, times=times, **qualifiers)


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


class _StubHandler(BaseHTTPRequestHandler):
    # Bound per server by make_server's subclass, so two stubs in one process stay apart.
    script: Script
    log_stream: TextIO
    log_lock: threading.Lock
    ids: "itertools.count"
    call_ids: "itertools.count"
    hits: dict
    hits_lock: threading.Lock
    tool_ids: "itertools.count"  # toolu_stub_<n> (PRD-022 STORY-006)
    request_ids: "itertools.count"  # request-id: req_stub_<n>
    endpoint_hits: dict  # {"chat": n, "messages": n}, under hits_lock
    release: threading.Event  # set by server_close: a `timeout` fault stops holding its connection
    require_key: Optional[str] = None
    # One small write per SSE frame: without this, Nagle plus delayed ACK costs ~40 ms a frame.
    disable_nagle_algorithm = True

    def log_message(self, *args):  # the access log would be a second, unscrubbed line
        pass

    def _log(self, line: str) -> None:
        # ASCII only: a non-ASCII model name must not break a cp1252 console.
        safe = line.encode("ascii", "backslashreplace").decode("ascii")
        with self.log_lock:
            self.log_stream.write(safe + "\n")
            self.log_stream.flush()

    def _send_json(self, status: int, body: dict, headers: Optional[dict] = None) -> None:
        data = json.dumps(body).encode("utf-8")
        try:
            self.send_response(status)
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except _DISCONNECTS:
            pass

    def _send_redirect(self, status: int, location: str) -> None:
        data = json.dumps({"error": {"message": f"{_PREFIX}: scripted redirect", "code": status}}).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Location", location)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except _DISCONNECTS:
            pass

    def _send_sse(self, model: Any, reply: Reply, wire_calls: list, include_usage: bool) -> None:
        """The reply as chat.completion.chunk frames (PRD-020 STORY-013).

        No Content-Length and `Connection: close`, so the client sees EOF at the
        end; one flush per frame.
        """
        stream_id = f"chatcmpl-stub-{next(self.ids)}"
        created = int(time.time())

        def frame(choices: list, usage: Any = None) -> bytes:
            chunk: dict = {
                "id": stream_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": choices,
            }
            if usage is not None:
                chunk["usage"] = usage
            return b"data: " + json.dumps(chunk).encode("utf-8") + b"\n\n"

        def delta_choice(delta: dict, finish: Optional[str] = None) -> list:
            return [{"index": 0, "delta": delta, "finish_reason": finish}]

        shape = reply.stream
        size = shape.chunk_chars if shape else None

        def pieces(text: str) -> list:
            # No chunk_chars: today's halves; else pieces of at most `size` characters.
            if size is None:
                half = len(text) // 2
                return [text[:half], text[half:]] if half else [text]
            return [text[i:i + size] for i in range(0, len(text), size)]

        deltas: list = []  # the frames that delay_ms paces and fail_after counts
        if shape is not None and shape.reasoning is not None:
            for part in pieces(shape.reasoning):
                deltas.append(frame(delta_choice({"reasoning": part})))
        content = reply.content
        # Without a shape, "" still yields one empty delta, byte-for-byte as before.
        if isinstance(content, str) and (content or shape is None):
            for part in pieces(content):
                deltas.append(frame(delta_choice({"content": part})))
        for index, call in enumerate(wire_calls):
            arguments = call["function"]["arguments"]
            if size is None:
                half = len(arguments) // 2
                parts = [arguments[:half], arguments[half:]]
            else:
                parts = pieces(arguments) or [""]
            for position, part in enumerate(parts):
                fragment: dict = {"index": index, "function": {"arguments": part}}
                if position == 0:
                    fragment = {
                        "index": index,
                        "id": call["id"],
                        "type": "function",
                        "function": {"name": call["function"]["name"], "arguments": part},
                    }
                deltas.append(frame(delta_choice({"tool_calls": [fragment]})))
        tail: list = [frame(delta_choice({}, reply.finish_reason))]
        if include_usage and reply.usage is not None:
            tail.append(frame([], dict(reply.usage)))
        tail.append(b"data: [DONE]\n\n")
        delay = shape.delay_ms / 1000 if shape else 0.0
        if shape is not None and shape.fail_after is not None:
            deltas = deltas[: shape.fail_after]
            tail = []  # the fault: no finish, no usage, no [DONE]; the close is the EOF
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            self.wfile.flush()
            for data in deltas:
                if delay:
                    time.sleep(delay)
                self.wfile.write(data)
                self.wfile.flush()
            for data in tail:
                self.wfile.write(data)
                self.wfile.flush()
        except _DISCONNECTS:
            pass

    def _send_error_body(self, status: int, message: str, retry_after: Optional[int] = None) -> None:
        headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
        self._send_json(status, {"error": {"message": f"{_PREFIX}: {message}", "code": status}}, headers)

    def _send_fault(self, fault: str, streaming: bool, endpoint: str) -> None:
        """A scripted transport fault (PRD-022 STORY-006), the same on both endpoints.

        `timeout` sends nothing and holds the connection until the server closes
        (the release event) or _HOLD_SECONDS pass; `malformed` is a 200 whose body
        (or first SSE frame) stops mid-token.
        """
        self.close_connection = True
        if fault == "timeout":
            self.release.wait(_HOLD_SECONDS)
            return
        try:
            if streaming:
                frame = (
                    b'data: {"choices":'
                    if endpoint == "chat"
                    else b'event: message_start\ndata: {"type":"message_start","message":'
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(frame)
                self.wfile.flush()
            else:
                data = b'{"id": "'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except _DISCONNECTS:
            pass

    # -- Anthropic Messages mode (PRD-022 STORY-006) ---------------------------

    def _send_messages_error(self, status: int, message: str, retry_after: Optional[int] = None) -> None:
        error_type = _ERROR_TYPES.get(status, "api_error")
        headers = {"request-id": f"req_stub_{next(self.request_ids)}"}
        if retry_after is not None:
            headers["Retry-After"] = str(retry_after)
        self._send_json(
            status, {"type": "error", "error": {"type": error_type, "message": f"{_PREFIX}: {message}"}}, headers
        )

    @staticmethod
    def _stop_reason(reply: Reply) -> Optional[str]:
        if reply.stop_reason is not None:
            return reply.stop_reason
        return _FINISH_TO_STOP.get(reply.finish_reason, reply.finish_reason)

    @staticmethod
    def _wire_usage(reply: Reply, output_tokens: Optional[int] = None) -> dict:
        usage = reply.usage or {}
        return {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0) if output_tokens is None else output_tokens,
            "cache_creation_input_tokens": reply.cache_creation_tokens,
            "cache_read_input_tokens": reply.cache_read_tokens,
        }

    def _messages_body(self, model: Any, reply: Reply, calls: list) -> Optional[dict]:
        """The Messages JSON body, or None when a call's arguments are not a JSON object."""
        blocks: list = []
        if reply.stream is not None and reply.stream.reasoning is not None:
            blocks.append({"type": "thinking", "thinking": reply.stream.reasoning, "signature": "stub-signature"})
        if isinstance(reply.content, str) and reply.content:
            blocks.append({"type": "text", "text": reply.content})
        for call in calls:
            try:
                tool_input = json.loads(call["arguments"])
            except ValueError:
                return None
            if not isinstance(tool_input, dict):
                return None
            blocks.append({"type": "tool_use", "id": call["id"], "name": call["name"], "input": tool_input})
        return {
            "id": f"msg_stub_{next(self.ids)}",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": blocks,
            "stop_reason": self._stop_reason(reply),
            "stop_sequence": None,
            "usage": None if reply.usage is None else self._wire_usage(reply),
        }

    def _send_messages_sse(self, model: Any, reply: Reply, calls: list) -> None:
        """The reply as Messages SSE (PRD-022 6.6): message_start, ping, blocks, message_delta, message_stop.

        Same pacing as the Chat stream (`stream:` shape): `delay_ms` before each
        delta frame, `fail_after: K` closes after K delta frames with no tail.
        """
        shape = reply.stream
        size = shape.chunk_chars if shape else None

        def cut(text: str) -> list:
            if size is None:
                half = len(text) // 2
                return [text[:half], text[half:]] if half else [text]
            return [text[i:i + size] for i in range(0, len(text), size)]

        def frame(event: str, data: dict) -> bytes:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")

        def delta(index: int, payload: dict) -> tuple:
            return "delta", frame("content_block_delta", {"type": "content_block_delta", "index": index, "delta": payload})

        def start(index: int, block: dict) -> tuple:
            return "other", frame("content_block_start", {"type": "content_block_start", "index": index, "content_block": block})

        def stop(index: int) -> tuple:
            return "other", frame("content_block_stop", {"type": "content_block_stop", "index": index})

        message: dict = {
            "id": f"msg_stub_{next(self.ids)}", "type": "message", "role": "assistant", "model": model,
            "content": [], "stop_reason": None, "stop_sequence": None,
        }
        if reply.usage is not None:
            message["usage"] = self._wire_usage(reply, output_tokens=1)
        frames: list = [
            ("other", frame("message_start", {"type": "message_start", "message": message})),
            ("other", frame("ping", {"type": "ping"})),
        ]
        index = 0
        if shape is not None and shape.reasoning is not None:
            frames.append(start(index, {"type": "thinking", "thinking": ""}))
            for part in cut(shape.reasoning):
                frames.append(delta(index, {"type": "thinking_delta", "thinking": part}))
            frames.append(delta(index, {"type": "signature_delta", "signature": "stub-signature"}))
            frames.append(stop(index))
            index += 1
        if isinstance(reply.content, str) and reply.content:
            frames.append(start(index, {"type": "text", "text": ""}))
            for part in cut(reply.content):
                frames.append(delta(index, {"type": "text_delta", "text": part}))
            frames.append(stop(index))
            index += 1
        for call in calls:
            frames.append(start(index, {"type": "tool_use", "id": call["id"], "name": call["name"], "input": {}}))
            for part in cut(call["arguments"]) or [""]:
                frames.append(delta(index, {"type": "input_json_delta", "partial_json": part}))
            frames.append(stop(index))
            index += 1
        tail: list = []
        message_delta: dict = {
            "type": "message_delta",
            "delta": {"stop_reason": self._stop_reason(reply), "stop_sequence": None},
        }
        if reply.usage is not None:
            message_delta["usage"] = {"output_tokens": reply.usage.get("completion_tokens", 0)}
        tail.append(("tail", frame("message_delta", message_delta)))
        tail.append(("tail", frame("message_stop", {"type": "message_stop"})))
        pause = shape.delay_ms / 1000 if shape else 0.0
        limit = shape.fail_after if shape else None
        if limit is not None:
            tail = []  # the fault: no message_delta, no message_stop; the close is the EOF
        headers = {"request-id": f"req_stub_{next(self.request_ids)}"}
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.close_connection = True
            self.wfile.flush()
            sent = 0
            for kind, data in frames + tail:
                if kind == "delta":
                    if limit is not None and sent >= limit:
                        break
                    if pause:
                        time.sleep(pause)
                    sent += 1
                self.wfile.write(data)
                self.wfile.flush()
                if kind == "delta" and limit is not None and sent >= limit:
                    break
        except _DISCONNECTS:
            pass

    def _post_messages(self, raw: bytes) -> None:
        """POST .../messages: the same script as Chat, answered as Anthropic Messages."""
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        max_tokens = body.get("max_tokens") if isinstance(body, dict) else None
        valid = (
            isinstance(body, dict)
            and isinstance(body.get("messages"), list)
            and isinstance(body.get("model"), str)
            and body["model"]
            and isinstance(max_tokens, int)
            and not isinstance(max_tokens, bool)
            and max_tokens >= 1
        )
        if not valid:
            self._log(f"{_PREFIX}: POST {ascii(self.path)} api=messages unreadable body -> 400")
            self._send_messages_error(400, "body must be a JSON object with messages, model and max_tokens >= 1")
            return

        model = body["model"]
        params = sorted(str(key) for key in body if key not in ("model", "messages"))
        tools = body.get("tools")
        offered = len(tools) if isinstance(tools, list) else 0
        with self.hits_lock:
            label, reply = self.script.select_request(Request.from_messages_body(body), self.hits)
        # Presence only, never a value: x-api-key and Authorization are compared in-process.
        bearer = self.headers.get("Authorization")
        api_key = self.headers.get("x-api-key")
        auth = "yes" if bearer is not None or api_key is not None else "no"
        version = "yes" if self.headers.get("anthropic-version") is not None else "no"
        unauthorized = self.require_key is not None and (
            bearer != f"Bearer {self.require_key}" and api_key != self.require_key
        )
        streaming = body.get("stream") is True
        status = 401 if unauthorized else (reply.fail_status or 200)
        fault_tag = f" fault={reply.fault}" if reply.fault else ""
        self._log(
            f"{_PREFIX}: POST {ascii(self.path)} api=messages model={ascii(model)} messages={len(body['messages'])} "
            f"params=[{','.join(params)}] rule={label} delay={reply.delay_seconds:g} auth={auth} ver={version} "
            f"stream={'yes' if streaming else 'no'} tools={offered} calls={len(reply.tool_calls)}{fault_tag} -> {status}"
        )

        if reply.delay_seconds:
            time.sleep(reply.delay_seconds)
        if unauthorized:
            self._send_messages_error(401, "unauthorized")
            return
        if reply.redirect_status is not None:
            self._send_redirect(reply.redirect_status, reply.location)
            return
        if reply.fail_status is not None:
            self._send_messages_error(reply.fail_status, "scripted failure", reply.retry_after)
            return
        if reply.fault is not None:
            self._send_fault(reply.fault, streaming, "messages")
            return
        calls = [
            {"id": call.id or f"toolu_stub_{next(self.tool_ids)}", "name": call.name, "arguments": call.arguments}
            for call in reply.tool_calls
        ]
        if streaming:
            self._send_messages_sse(model, reply, calls)
            return
        wire = self._messages_body(model, reply, calls)
        if wire is None:  # never echo the arguments
            self._send_messages_error(500, "tool arguments are not a JSON object")
            return
        self._send_json(200, wire, {"request-id": f"req_stub_{next(self.request_ids)}"})

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's spelling
        if self.path.rstrip("/") == "/health":
            self._send_json(200, {"status": "ok"})
        else:
            self._send_error_body(404, f"no route for GET {self.path}")

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler's spelling
        # Content-Length is the only header this handler ever reads.
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length)
        path = self.path.rstrip("/")
        if path.endswith("/chat/completions"):
            endpoint = "chat"
        elif path.endswith("/messages"):
            endpoint = "messages"
        else:
            self._log(f"{_PREFIX}: POST {ascii(self.path)} -> 404")
            self._send_error_body(404, "only POST .../chat/completions is served")
            return
        with self.hits_lock:  # every POST to a served endpoint, faulted ones included
            self.endpoint_hits[endpoint] += 1
        if endpoint == "messages":
            self._post_messages(raw)
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
        tools = body.get("tools")
        offered = len(tools) if isinstance(tools, list) else 0
        # Under the lock, so two concurrent requests cannot both take a capped rule's last answer.
        with self.hits_lock:
            label, reply = self.script.select_request(Request.from_body(body), self.hits)
        # Presence only, never the value (PRD-020 T6). With require_key set, the
        # value is compared in-process and a mismatch answers 401.
        authorization = self.headers.get("Authorization")
        auth = "yes" if authorization is not None else "no"
        unauthorized = self.require_key is not None and authorization != f"Bearer {self.require_key}"
        streaming = body.get("stream") is True
        status = 401 if unauthorized else (reply.redirect_status or reply.fail_status or 200)
        fault_tag = f" fault={reply.fault}" if reply.fault else ""  # absent unless scripted
        # Counts only: never a tool name, argument or content (PRD-017 D13, PRD-015 T6).
        self._log(
            f"{_PREFIX}: POST {ascii(self.path)} model={ascii(model)} messages={len(messages)} "
            f"params=[{','.join(params)}] rule={label} delay={reply.delay_seconds:g} auth={auth} "
            f"stream={'yes' if streaming else 'no'} tools={offered} calls={len(reply.tool_calls)}{fault_tag} -> {status}"
        )

        if reply.delay_seconds:
            time.sleep(reply.delay_seconds)
        if unauthorized:
            self._send_error_body(401, "unauthorized")
            return
        if reply.redirect_status is not None:
            self._send_redirect(reply.redirect_status, reply.location)
            return
        if reply.fail_status is not None:
            self._send_error_body(reply.fail_status, "scripted failure", reply.retry_after)
            return
        if reply.fault is not None:
            self._send_fault(reply.fault, streaming, "chat")
            return
        message: dict = {"role": "assistant", "content": reply.content}
        # Ids are generated per answer, so a rule answering twice yields fresh ones.
        wire_calls = [
            {
                "id": call.id or f"call_{next(self.call_ids)}",
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in reply.tool_calls
        ]
        if wire_calls:
            message["tool_calls"] = wire_calls
        if streaming:
            options = body.get("stream_options")
            include_usage = isinstance(options, dict) and options.get("include_usage") is True
            self._send_sse(model, reply, wire_calls, include_usage)
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
                        "message": message,
                        "finish_reason": reply.finish_reason,
                    }
                ],
                "usage": None if reply.usage is None else dict(reply.usage),
            },
        )


class _StubServer(ThreadingHTTPServer):
    # A handler asleep on a delay rule must never hold up shutdown.
    daemon_threads = True
    release: threading.Event
    _endpoint_hits: dict
    _hits_lock: threading.Lock

    def endpoint_hits(self) -> dict:
        """{"chat": n, "messages": n}: every POST to either endpoint so far (PRD-022 STORY-006)."""
        with self._hits_lock:
            return dict(self._endpoint_hits)

    def server_close(self) -> None:
        # Frees every `timeout` fault still holding a connection, so teardown never waits.
        self.release.set()
        super().server_close()


def make_server(
    script: Script,
    host: str = "127.0.0.1",
    port: int = 0,
    log: Optional[TextIO] = None,
    require_key: Optional[str] = None,
) -> ThreadingHTTPServer:
    """A bound, not yet serving, stub. Port 0 picks a free port: read server_address[1].

    `require_key` is in-process only (tests, PRD-020 STORY-005): a request whose
    Authorization is not exactly `Bearer <require_key>` is answered 401. The value
    is compared, never logged or echoed. On /messages `x-api-key: <require_key>` is
    accepted as well (PRD-022 STORY-006). `server.endpoint_hits()` counts requests
    per endpoint; `server.server_close()` releases held `timeout` faults.
    """
    release = threading.Event()
    endpoint_hits = {"chat": 0, "messages": 0}
    hits_lock = threading.Lock()
    handler = type(
        "_BoundStubHandler",
        (_StubHandler,),
        {
            "script": script,
            "log_stream": log if log is not None else sys.stderr,
            "log_lock": threading.Lock(),
            "ids": itertools.count(1),
            "call_ids": itertools.count(1),
            "hits": {},
            "hits_lock": hits_lock,
            "tool_ids": itertools.count(1),
            "request_ids": itertools.count(1),
            "endpoint_hits": endpoint_hits,
            "release": release,
            "require_key": require_key,
        },
    )
    server = _StubServer((host, port), handler)
    server.release, server._endpoint_hits, server._hits_lock = release, endpoint_hits, hits_lock
    return server


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
