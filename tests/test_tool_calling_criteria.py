"""PRD-017 STORY-015: the brief's success criteria for tool calling, in process.

Every test drives `POST /v1/chat/completions` through `TestClient` with an injected upstream
(`app.routers.v1.call_openrouter` replaced by a stub, or the real client over an
`httpx.MockTransport` when the bytes on the upstream wire matter) and the real pipeline, policy
engine, audit and dedup. No real client and no network: the opt-in real-client run is
`tests/e2e/` (STORY-016). The criteria and where they come from:

| Criterion | Source | Test |
|---|---|---|
| `DROP TABLE` is denied, audited with the request's `audit_id` and reported | brief 3; PRD-017 11 | `test_drop_table_is_denied_...`, `test_mixed_response_...` |
| No call argument is modified by any check, both directions | brief 4; PRD-017 11, T2, D13 | `test_history_arguments_...`, `test_response_arguments_...` |
| `npm test` twice in one session is not held; a resend is | brief 5; PRD-017 6.4, 11 | `test_npm_test_twice_...` |
| No call is released undecided (T1); flag off is PRD-015 (D10) | PRD-017 9.2, 11 | `test_no_call_is_released_...`, `test_flag_off_...` |
| Step 7c latency over the PRD-016 synthetic corpus | PRD-017 11 (quality) | `test_step_7c_latency_...` (`benchmark`) |

Each test is the end-to-end `/v1` form of a criterion that narrower tests prove one layer at a
time; the docstrings name them. Fixtures and helpers are imported from the modules that own them
(the repo convention), never copied.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import copy
import json
import math
import statistics
import time
from pathlib import Path

import httpx
import pytest

from app.config import settings
from app.db.database import get_audit_log, get_connection
from app.models.messages import ToolCallSpec
from app.services import action_config, action_policy, tool_release
from app.services.action_adapters import ToolCall
from app.services.identity import Identity
from app.services.openrouter_client import OpenRouterResult
from tests.test_action_corpus import _IDENTITIES, _POLICIES, _SYNTHETIC
from tests.test_query_pipeline_tools import _all_denied, _code_policy  # noqa: F401 (pytest fixture)
from tests.test_v1_tools import (  # noqa: F401 (temp_db and _flag_state are pytest fixtures)
    _ADMIN_TOKEN,
    _AUTH_USER_ID,
    _MODEL,
    _PATH,
    _TOOLS_OFF,
    _accumulate,
    _capturing_transport,
    _count_audit_rows,
    _data_events,
    _decision_table,
    _error,
    _flag_state,
    _only_row,
    _ToolUpstream,
    _upstream_over,
    _use,
    client,
    temp_db,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_EXAMPLE_POLICY_FILE = _REPO_ROOT / "examples" / "action_policy.yaml"

# The OpenCode 2.0 tool names and argument keys (`action_adapters.py` default maps).
_OPENCODE_TOOLS = [
    {"type": "function", "function": {
        "name": name, "description": f"the {name} tool",
        "parameters": {"type": "object", "properties": {key: {"type": "string"} for key in keys}},
    }}
    for name, keys in (("shell", ("command",)), ("read", ("path",)), ("write", ("path", "content")))
]
_SYSTEM = {"role": "system", "content": "You are OpenCode, a coding agent."}
_USER_TURN = {"role": "user", "content": "drop the users table"}
_STREAMING = pytest.mark.parametrize("stream", [False, True], ids=["json", "sse"])
_ADMIN_HEADERS = {"Authorization": f"Bearer {_ADMIN_TOKEN}"}


def _flag_on(monkeypatch):
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)


def _body(messages, **extra):
    return {"model": _MODEL, "messages": messages, "tools": _OPENCODE_TOOLS, **extra}


def _content(response, stream):
    """The answer text: the message content (JSON) or the concatenated deltas (SSE)."""
    if stream:
        return "".join(
            c["choices"][0]["delta"].get("content") or "" for c in _data_events(response.text) if c["choices"]
        )
    return response.json()["choices"][0]["message"]["content"]


def _released(response, stream):
    """`[(id, name, arguments)]` of the calls the client received, in order."""
    if stream:
        deltas = [c["choices"][0]["delta"] for c in _data_events(response.text) if c["choices"]]
        calls = [t for d in deltas for t in d.get("tool_calls") or []]
    else:
        calls = response.json()["choices"][0]["message"]["tool_calls"] or []
    return [(c["id"], c["function"]["name"], c["function"]["arguments"]) for c in calls]


def _finish(response, stream):
    if stream:
        return [c["choices"][0]["finish_reason"] for c in _data_events(response.text) if c["choices"]][-1]
    return response.json()["choices"][0]["finish_reason"]


def _note(call, reason):
    return tool_release.DENIAL_NOTE_TEMPLATE.format(name=call.name, id=call.id, reason=reason)


def _assert_allowed(calls):
    """A policy change must fail here, not as a confusing release diff."""
    decisions = action_policy.evaluate_all(
        tuple(ToolCall(c.id, c.name, c.arguments) for c in calls), Identity(_AUTH_USER_ID, "user")
    )
    assert [d.decision for d in decisions] == ["allow"] * len(calls), [(d.rule, d.reason) for d in decisions]


def _assert_no_arguments(response, *calls):
    for call in calls:
        assert call.arguments not in response.text
        assert json.dumps(call.arguments) not in response.text
        assert json.dumps(call.arguments, ensure_ascii=False) not in response.text
    assert '"arguments"' not in response.text


# ===========================================================================================
# Criterion 3: DROP TABLE is denied, audited with the audit_id, and reported
# ===========================================================================================

_DROP_CALLS = {
    "shell-sqlite3": ToolCallSpec("call_d", "shell", json.dumps({"command": 'sqlite3 app.db "DROP TABLE users"'})),
    "run_sql": ToolCallSpec("call_d", "run_sql", '{"query":"DROP TABLE users"}'),
    "mcp-query": ToolCallSpec("call_d", "query", '{"sql":"DROP TABLE users"}'),
}


@_STREAMING
@pytest.mark.parametrize("case", list(_DROP_CALLS))
def test_drop_table_is_denied_recorded_with_the_audit_id_and_reported(temp_db, monkeypatch, case, stream):
    """Brief success criterion 3; PRD-017 Section 11 (Functional, DROP TABLE); T5.

    A `DROP TABLE` through the shell (`sqlite3`), a mapped SQL tool and an MCP `query` tool: no
    call reaches the client, the finish is `stop`, the content carries the PRD-016 reason, one
    `deny`/`sql.ddl` row names the request's `audit_id`, and `GET /audit/actions?audit_id=`
    finds it. Narrower: `test_v1_tools.py::test_drop_table_via_shell_is_denied_and_recorded_with_the_audit_id`
    (shell only, no audit API read).
    """
    _flag_on(monkeypatch)
    call = _DROP_CALLS[case]
    _use(monkeypatch, _ToolUpstream(response="", tool_calls=(call,), finish_reason="tool_calls"))

    response = client.post(_PATH, json=_body([_SYSTEM, _USER_TURN], stream=stream))

    assert response.status_code == 200
    (row,) = _decision_table()
    audit = _only_row()
    assert (row["decision"], row["rule"], row["tool_name"]) == ("deny", "sql.ddl", call.name)
    assert row["audit_id"] == audit.id
    note = _note(call, row["reason"])
    assert _content(response, stream) == note
    assert row["reason"] in note
    assert _released(response, stream) == []
    assert _finish(response, stream) == "stop"
    _assert_no_arguments(response, call)
    assert "DROP TABLE" not in response.text.replace(note, "")
    if stream:
        assert '"tool_calls"' not in response.text
        assert response.text.rstrip().endswith("data: [DONE]")
        assert all("harness" not in chunk for chunk in _data_events(response.text))
    else:
        body = response.json()
        assert body["choices"][0]["message"]["tool_calls"] is None
        assert body["harness"]["actions"] == [{
            "tool_call_id": call.id, "tool_name": call.name,
            "decision": "deny", "rule": "sql.ddl", "reason": row["reason"],
        }]

    listed = client.get(f"/audit/actions?audit_id={audit.id}", headers=_ADMIN_HEADERS)
    assert listed.status_code == 200
    (entry,) = listed.json()["entries"]
    assert (entry["audit_id"], entry["decision"], entry["rule"]) == (audit.id, "deny", "sql.ddl")


@_STREAMING
def test_mixed_response_releases_only_the_allowed_calls(temp_db, monkeypatch, stream):
    """PRD-017 Section 11 (Functional, mixed response); D1.

    `read`, a denied `DROP TABLE`, `write`: the allowed calls leave in model order, the denied
    one is dropped and noted once, the finish is `tool_calls`, and the three rows share the
    request's `audit_id`. Narrower: `test_v1_tools.py:983` and `:1217` (two calls, shell deny).
    """
    _flag_on(monkeypatch)
    read = ToolCallSpec("call_r", "read", '{"path":"src/a.py"}')
    drop = _DROP_CALLS["run_sql"]
    write = ToolCallSpec("call_w", "write", '{"path":"src/b.py","content":"x"}')
    _assert_allowed([read, write])
    _use(monkeypatch, _ToolUpstream(response="Reading.", tool_calls=(read, drop, write), finish_reason="tool_calls"))

    response = client.post(_PATH, json=_body([_SYSTEM, _USER_TURN], stream=stream))

    assert response.status_code == 200
    rows = _decision_table()
    assert [r["decision"] for r in rows] == ["allow", "deny", "allow"]
    assert {r["audit_id"] for r in rows} == {_only_row().id}
    assert _released(response, stream) == [
        (c.id, c.name, c.arguments) for c in (read, write)
    ]
    assert _content(response, stream) == "Reading.\n\n" + _note(drop, rows[1]["reason"])
    assert _finish(response, stream) == "tool_calls"
    assert drop.arguments not in response.text
    if not stream:
        assert [a["tool_call_id"] for a in response.json()["harness"]["actions"]] == ["call_r", "call_d", "call_w"]


# ===========================================================================================
# Criterion 4: no argument is modified by any check, in either direction
# ===========================================================================================

# Every string below is valid JSON (an unparseable one is `tool.malformed`: denied, never
# released) and allowed by the built-in policy (`_assert_allowed` pins that).
_TRICKY = (
    ToolCallSpec(
        "call_pii", "write",
        '{"path":"notes/ops.md","content":"mail ops@example.org, call +1 212 555 0100, '
        'card 4111 1111 1111 1111, SSN 078-05-1120"}',
    ),
    # Raw UTF-8 and literal \uXXXX escapes side by side, so a re-dump would rewrite one to the other.
    ToolCallSpec("call_uni", "read", '{"path":"src/café ☃ 日本 😀 \u202e.ts", "alt":"caf\\u00e9"}'),
    # Whitespace-odd and escape-heavy: `\\`, `\"`, `\n`, `\t`, `\\u0041`, `\/`.
    ToolCallSpec(
        "call_esc", "write",
        '{"path": "src/a.py" ,"content":"C:\\\\tmp\\\\a.txt \\"q\\" \\n\\t \\\\u0041 \\/ end"}',
    ),
)


def _wire_calls(calls):
    return [{"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}} for c in calls]


def test_tricky_arguments_are_what_the_test_means_them_to_be():
    """The literals above parse, differ from their re-dump (so a re-stringify would show) and are allowed."""
    for call in _TRICKY:
        parsed = json.loads(call.arguments)
        assert json.dumps(parsed) != call.arguments
        assert json.dumps(parsed, ensure_ascii=False) != call.arguments


def test_history_arguments_reach_the_upstream_byte_identical(temp_db, monkeypatch, _code_policy):
    """Brief success criterion 4; PRD-017 Section 11 (Functional, byte-identical), T2, D13.

    Client to upstream: three assistant calls with PII-looking, unicode and escape-heavy
    arguments reach the wire as the same strings, in the same raw request bytes, while the
    `code` profile's redaction demonstrably ran on a tool turn of this very request.
    Narrower: `test_query_pipeline_tools.py:406` (pipeline, history only) and
    `test_v1_tools.py:715` (ASCII).
    """
    _flag_on(monkeypatch)
    _assert_allowed(_TRICKY)
    seen: list = []
    monkeypatch.setattr("app.routers.v1.call_openrouter", _upstream_over(_capturing_transport(seen)))
    messages = [
        {"role": "user", "content": "update the notes and read the source"},
        {"role": "assistant", "content": None, "tool_calls": _wire_calls(_TRICKY)},
        {"role": "tool", "tool_call_id": "call_pii", "content": "mailed ops@example.org"},
        {"role": "tool", "tool_call_id": "call_uni", "content": "ok"},
        {"role": "tool", "tool_call_id": "call_esc", "content": "ok"},
    ]

    response = client.post(_PATH, json=_body(messages))

    assert response.status_code == 200
    (request,) = seen
    payload = json.loads(request.content)
    sent = payload["messages"]
    wire = request.content.decode("utf-8")
    for index, call in enumerate(_TRICKY):
        arguments = sent[1]["tool_calls"][index]["function"]["arguments"]
        assert arguments == call.arguments
        assert arguments.encode("utf-8") == call.arguments.encode("utf-8")
        assert json.dumps(call.arguments, ensure_ascii=False) in wire
    assert [m["tool_call_id"] for m in sent[2:]] == ["call_pii", "call_uni", "call_esc"]
    # Redaction ran in this request (the tool turn was masked), and the same address inside the
    # arguments did not change (D13).
    assert sent[2]["content"] == "mailed <EMAIL_ADDRESS>"
    assert "ops@example.org" in sent[1]["tool_calls"][0]["function"]["arguments"]


@_STREAMING
def test_response_arguments_reach_the_client_byte_identical(temp_db, monkeypatch, stream):
    """Brief success criterion 4; PRD-017 Section 11 (Functional, byte-identical), T2, D13.

    Upstream to client: the upstream sends `\\u`-escaped JSON, the real client parses it, the
    harness decides, and the client gets the same decoded argument strings, in model order,
    in the JSON body and in the SSE stream (also through the `openai` SDK's accumulator).
    "Not modified" is the harness's property: it forwards what it received. A client that
    re-stringifies (Cline) is outside it (STORY-001 note).
    """
    _flag_on(monkeypatch)
    _assert_allowed(_TRICKY)
    upstream_body = {
        "choices": [{"message": {"content": None, "tool_calls": _wire_calls(_TRICKY)}, "finish_reason": "tool_calls"}],
        "model": _MODEL, "usage": {"total_tokens": 12},
    }
    raw = json.dumps(upstream_body, ensure_ascii=True).encode()
    assert b"\\u00e9" in raw and "☃".encode() not in raw
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=raw, headers={"content-type": "application/json"}))
    monkeypatch.setattr("app.routers.v1.call_openrouter", _upstream_over(transport))

    response = client.post(_PATH, json=_body([_SYSTEM, {"role": "user", "content": "update the notes"}], stream=stream))

    assert response.status_code == 200
    expected = [(c.id, c.name, c.arguments) for c in _TRICKY]
    assert _released(response, stream) == expected
    assert _finish(response, stream) == "tool_calls"
    for call in _TRICKY:
        assert json.dumps(call.arguments, ensure_ascii=False) in response.text
    if stream:
        message = _accumulate(_data_events(response.text)).choices[0].message
        assert [(c.id, c.function.name, c.function.arguments) for c in message.tool_calls] == expected
    assert [r["decision"] for r in _decision_table()] == ["allow"] * 3


# ===========================================================================================
# Criterion 5: `npm test` twice in one session is not a duplicate; a resend is
# ===========================================================================================


class _ScriptedUpstream:
    """Pops one `OpenRouterResult` per call (the shape of `tests/e2e/scripts/tool_loop.json`)."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def __call__(self, messages, model="gpt-4", api_key=None, *, params=None, tools=None):
        assert self.script, "the upstream was called more times than scripted"
        self.calls.append(list(messages))
        return OpenRouterResult(model_used=model, tokens_used=10, **self.script.pop(0))


_NPM_TEST = '{"command":"npm test"}'
_LOOP_SCRIPT = (
    {"response": "", "tool_calls": (ToolCallSpec("call_t1", "shell", _NPM_TEST),), "finish_reason": "tool_calls"},
    {"response": "", "tool_calls": (ToolCallSpec(
        "call_w1", "write", '{"path":"src/math.js","content":"export const add = (a, b) => a + b;\\n"}'),),
     "finish_reason": "tool_calls"},
    {"response": "", "tool_calls": (ToolCallSpec("call_t2", "shell", _NPM_TEST),), "finish_reason": "tool_calls"},
    {"response": "Done: npm test passes.", "finish_reason": "stop"},
)
_LOOP_OUTPUTS = ("1 failing", "ok", "2 passing")


@pytest.mark.parametrize("resend_streams", [False, True], ids=["json", "sse"])
def test_npm_test_twice_in_one_session_is_not_held_but_a_resend_is(temp_db, monkeypatch, resend_streams):
    """Brief success criterion 5; PRD-017 Section 6.4 ("why npm test twice is not a duplicate"), Section 11.

    An OpenCode 2.0 loop (run `npm test`, edit a file, run `npm test`, answer) goes through
    `/v1` under the example policy (the built-in one denies `npm test` as `shell.unlisted`) with
    the real dedup: four requests, four distinct keys, none held. A byte-identical resend of the
    last one is a `400 duplicate_request`, as JSON even when the resend streams (`stream` is
    outside the key), and the upstream is not called again. Narrower:
    `test_query_pipeline_dedup_key.py::test_npm_test_twice_is_not_held_but_a_resend_is` (pipeline, `bash`).
    """
    _flag_on(monkeypatch)
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", str(_EXAMPLE_POLICY_FILE))
    action_config.load()  # conftest's _default_action_policy restores the policy afterwards
    stub = _use(monkeypatch, _ScriptedUpstream(*_LOOP_SCRIPT))
    messages = [_SYSTEM, {"role": "user", "content": "run the tests, fix the failure, run them again"}]
    outputs = iter(_LOOP_OUTPUTS)
    bodies = []

    for turn in range(4):
        bodies.append(copy.deepcopy(_body(messages)))
        response = client.post(_PATH, json=_body(messages))
        assert response.status_code == 200, response.text
        message = response.json()["choices"][0]["message"]
        if turn < 3:
            assert [a["decision"] for a in response.json()["harness"]["actions"]] == ["allow"]
            assert message["tool_calls"], "the loop's call must be released, not held or dropped"
            messages = messages + [{"role": "assistant", "content": message["content"], "tool_calls": message["tool_calls"]}]
            messages += [
                {"role": "tool", "tool_call_id": c["id"], "content": next(outputs)} for c in message["tool_calls"]
            ]
        else:
            assert message["content"] == "Done: npm test passes."
            assert not message.get("tool_calls")

    with get_connection() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM audit_logs ORDER BY id")]
    keys = [get_audit_log(i).dedup_key for i in ids]
    assert len(keys) == 4 and all(keys) and len(set(keys)) == 4
    assert keys[1] != keys[3]  # the two `npm test` requests share a command, never a key
    assert len(stub.calls) == 4

    resend = copy.deepcopy(bodies[3])
    if resend_streams:
        resend["stream"] = True
    response = client.post(_PATH, json=resend)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "duplicate_request"
    assert len(stub.calls) == 4
    with get_connection() as conn:
        newest = conn.execute("SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()["id"]
    assert newest not in ids
    assert get_audit_log(newest).dedup_key == keys[3]


# ===========================================================================================
# T1 and the flag-off behaviour
# ===========================================================================================


@_STREAMING
def test_no_call_is_released_when_every_call_is_denied(temp_db, monkeypatch, stream):
    """PRD-017 Section 9.2 T1 and Section 11: `evaluate_all` denying everything leaves no call.

    Neither response shape carries a call or an `arguments` key; the finish is `stop`; the
    content is the notes; one `deny` row per call names the request's `audit_id`. Narrower:
    `test_query_pipeline_tools.py::test_all_denied_releases_nothing` (pipeline only).
    """
    _flag_on(monkeypatch)
    _all_denied(monkeypatch)
    read = ToolCallSpec("call_r", "read", '{"path":"src/a.py"}')
    write = ToolCallSpec("call_w", "write", '{"path":"src/b.py","content":"x"}')
    _use(monkeypatch, _ToolUpstream(response="", tool_calls=(read, write), finish_reason="tool_calls"))

    response = client.post(_PATH, json=_body([_SYSTEM, {"role": "user", "content": "edit things"}], stream=stream))

    assert response.status_code == 200
    rows = _decision_table()
    assert [r["decision"] for r in rows] == ["deny", "deny"]
    assert {r["audit_id"] for r in rows} == {_only_row().id}
    assert _released(response, stream) == []
    assert _finish(response, stream) == "stop"
    assert _content(response, stream) == "\n\n".join(_note(c, "denied for the test") for c in (read, write))
    _assert_no_arguments(response, read, write)
    if stream:
        assert '"tool_calls"' not in response.text
        assert response.text.rstrip().endswith("data: [DONE]")
    else:
        body = response.json()
        assert body["choices"][0]["message"]["tool_calls"] is None
        assert [a["decision"] for a in body["harness"]["actions"]] == ["deny", "deny"]


@_STREAMING
def test_flag_off_refuses_the_whole_tool_request_as_prd_015(temp_db, monkeypatch, stream):
    """PRD-017 D10 and Section 11: with `V1_TOOLS_ENABLED` off a tool request is PRD-015's `tools_not_supported`.

    The full OpenCode request (tools, `tool_choice`, a tool turn in the history), streamed or
    not: `400`, the exact body, `x-should-retry: false`, no audit row, no upstream call.
    Narrower: `test_v1_tools.py::test_flag_off_refusals_are_prd_015_exactly` (per-key matrix).
    """
    assert settings.V1_TOOLS_ENABLED is False
    stub = _use(monkeypatch, _ToolUpstream())
    messages = [
        _SYSTEM,
        {"role": "user", "content": "run the tests"},
        {"role": "assistant", "content": None, "tool_calls": _wire_calls([ToolCallSpec("call_t1", "shell", _NPM_TEST)])},
        {"role": "tool", "tool_call_id": "call_t1", "content": "1 failing"},
    ]

    response = client.post(_PATH, json=_body(messages, tool_choice="auto", stream=stream))

    assert response.status_code == 400
    assert response.json() == _error(f"tools: {_TOOLS_OFF}", "tools", "tools_not_supported")
    assert response.headers["x-should-retry"] == "false"
    assert _count_audit_rows() == 0
    assert stub.calls == []


# ===========================================================================================
# Quality: step 7c latency over the PRD-016 synthetic corpus (benchmark)
# ===========================================================================================

_BENCHMARK_ROUNDS = 50
_MAX_CALLS_PER_RESPONSE = 8  # PRD-017 Section 11: "<= 8 calls"


def _responses():
    """The synthetic corpus as responses: per policy (one response is decided under one), in file order, <= 8 calls each."""
    grouped: dict = {}
    for case in _SYNTHETIC:
        grouped.setdefault(case.policy, []).append(
            ToolCallSpec(case.path.stem, case.call.name, case.call.arguments)
        )
    return [
        (_POLICIES[name], tuple(specs[i:i + _MAX_CALLS_PER_RESPONSE]))
        for name, specs in grouped.items()
        for i in range(0, len(specs), _MAX_CALLS_PER_RESPONSE)
    ]


def _p95(values):
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


@pytest.mark.benchmark
def test_step_7c_latency_over_the_synthetic_corpus(capsys, record_property):
    """Measured and printed for the story report -- **no threshold asserted** (target p95 < 5 ms).

    Step 7c's body (`query_pipeline.py`: the `ToolCallSpec` -> `ToolCall` copy, `evaluate_all`,
    `apply_decisions`) over every PRD-016 synthetic file, grouped into responses of at most 8
    calls, one warm-up pass, then `_BENCHMARK_ROUNDS` timed passes. A wall-clock gate is flaky
    (the reason at `test_action_corpus.py::test_evaluate_p95_over_the_synthetic_corpus`, whose
    form this mirrors). `policy` is passed explicitly because the corpus spans two policies;
    the pipeline's `get_policy()` is a module-global read. Full 8-call responses are reported
    separately: they are the PRD's bound, the short tail chunks are not.
    """
    identity = _IDENTITIES["user"]
    responses = _responses()

    def step_7c(policy, specs):
        calls = tuple(ToolCall(c.id, c.name, c.arguments) for c in specs)
        decisions = action_policy.evaluate_all(calls, identity, policy)
        tool_release.apply_decisions(specs, decisions)

    for policy, specs in responses:
        step_7c(policy, specs)
    timings, full = [], []
    for _ in range(_BENCHMARK_ROUNDS):
        for policy, specs in responses:
            start = time.perf_counter()
            step_7c(policy, specs)
            elapsed = (time.perf_counter() - start) * 1000
            timings.append(elapsed)
            if len(specs) == _MAX_CALLS_PER_RESPONSE:
                full.append(elapsed)

    assert len(timings) == len(responses) * _BENCHMARK_ROUNDS and full
    p95, p50 = _p95(timings), statistics.median(timings)
    record_property("step_7c_p95_ms", round(p95, 4))
    record_property("step_7c_8_call_p95_ms", round(_p95(full), 4))
    total_calls = sum(len(specs) for _, specs in responses)
    line = (
        f"STORY-015 step 7c over {len(responses)} responses ({total_calls} calls, <= {_MAX_CALLS_PER_RESPONSE} per response) "
        f"x {_BENCHMARK_ROUNDS} rounds: min {min(timings):.4f} ms / p50 {p50:.4f} ms / p95 {p95:.4f} ms / max {max(timings):.4f} ms; "
        f"8-call responses ({len(full) // _BENCHMARK_ROUNDS}): p50 {statistics.median(full):.4f} ms / p95 {_p95(full):.4f} ms"
    )
    with capsys.disabled():
        print("\n" + line)
