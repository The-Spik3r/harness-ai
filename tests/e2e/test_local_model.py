"""PRD-020 STORY-014 (D16): the harness against a real local OpenAI-compatible server.

Opt-in. A real `uvicorn app.main:app` subprocess runs in file mode with one
keyless, internal `local` provider, and talks to a model server on this machine
(default `http://localhost:1235/v1`, model `google/gemma-4-e4b`; override with
`HARNESS_E2E_LOCAL_BASE_URL` and `HARNESS_E2E_LOCAL_MODEL`).

    AC 1  `/query` answered by the real model; the row says provider='local',
          provider_trust='internal'
    AC 2  the OpenAI SDK against `/v1`, streamed to the client (the harness
          buffers upstream); the row says ingress='v1', streamed, provider='local'
    AC 3  one forced (`tool_choice: required`) `read` tool call released through the action policy: one
          `action_decisions` row (allow, fs.read) joined to the audit row
    AC 4  skipped, never failed, when the server is unreachable or the model is
          not served; the reason names what is missing. A missing
          HARNESS_E2E_LIBSQL_URL stays the harness-environment failure it is in
          every E2E module
    AC 5  `local-model-run.json` records the server facts the server exposes and
          whether `usage` was real or estimated per path

The model is not under test. A model that declines to call the tool is a skip;
only a harness error (a non-2xx, a missing or malformed audit row, a missing
action decision for a call the response carried) fails.

**Storage only in children**, as `tests/e2e/test_openai_sdk.py`: this process
never reaches storage and is not a `db` test.

Run (skipped without `--run-e2e`; needs `pip install -r requirements-e2e.txt`):

    docker run -d --name harness-libsql-e2e020-014 -p 8088:8080 -e SQLD_NODE=primary ghcr.io/tursodatabase/libsql-server:latest
    HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088 python -m pytest tests/e2e/test_local_model.py --run-e2e -v -s
    docker rm -f harness-libsql-e2e020-014
"""

import json
import secrets

import httpx
import pytest

from tests.e2e import _live, _local_model

openai = pytest.importorskip("openai")

pytestmark = pytest.mark.e2e

REPO_ROOT = _live.REPO_ROOT
_RECIPE = (
    "docker run -d --name harness-libsql-e2e020-014 -p 8088:8080 -e SQLD_NODE=primary "
    "ghcr.io/tursodatabase/libsql-server:latest, then "
    "HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088"
)
_CLIENT_TIMEOUT = 300  # the first request may load the model

NONCE = secrets.token_hex(4)

#: Row fields copied into the facts. Never the token, the prompt or the answer.
_REPORT_FIELDS = (
    "id", "success", "streamed", "ingress", "model_used", "provider", "provider_trust",
    "tokens_used", "usage_estimated", "has_tool_calls", "error_message",
)
_ACTION_FIELDS = ("id", "audit_id", "tool_call_id", "tool_name", "decision", "rule")

_READ_TOOL = {
    "type": "function",
    "function": {
        "name": "read",
        "description": "Read a file and return its contents.",
        "parameters": {
            "type": "object",
            "properties": {"filePath": {"type": "string", "description": "Path of the file to read."}},
            "required": ["filePath"],
        },
    },
}
# The string form: with one tool, "required" forces it, and servers that reject the object form
# ({"type": "function", ...}; LM Studio: "Supported string values: none, auto, required") accept it.
_FORCE_READ = "required"


def _usage(row: dict) -> str:
    return "estimated" if row["usage_estimated"] else "real"


# --------------------------------------------------------------------------
# Fixtures: the model server probe, database, users, harness
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def local_server():
    """Probe the model server; skip, naming what is missing, before anything starts (AC 4)."""
    base_url, model = _local_model.local_config()
    ok, reason = _local_model.probe(base_url, model)
    if not ok:
        pytest.skip(reason)
    return {"base_url": base_url, "model": model, "facts": _local_model.server_facts(base_url, model)}


@pytest.fixture(scope="module")
def e2e_db_url():
    return _live.resolve_e2e_db_url(_RECIPE)


@pytest.fixture(scope="module")
def child_cwd(tmp_path_factory):
    """A directory with no `.env`, so no child reads the developer's settings."""
    return tmp_path_factory.mktemp("e2e020_014")


@pytest.fixture(scope="module")
def child_env(e2e_db_url):
    def build(**extra) -> dict:
        return _live.child_env(e2e_db_url, **extra)

    return build


@pytest.fixture(scope="module")
def run_child(child_cwd, child_env):
    def run(*args: str):
        return _live.run_child(child_cwd, child_env(), *args)

    return run


@pytest.fixture(scope="module")
def users(local_server, run_child):
    """{label: (user_id, token)}. After `local_server`: a skip happens before any child starts."""
    user_id = f"e2e020-014-main-{NONCE}"
    return {"main": (user_id, _live.create_user(run_child, user_id))}


@pytest.fixture(scope="module")
def registry_path(local_server, child_cwd):
    path = child_cwd / "providers.yaml"
    path.write_text(_local_model.registry_yaml(local_server["model"], local_server["base_url"]), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def harness(local_server, users, registry_path, child_cwd, child_env):
    """`uvicorn app.main:app` in file mode. No OPENROUTER_API_KEY, no MODEL_ALLOWLIST, no V1_TOOL_MODELS."""
    env = child_env(
        PROVIDERS_FILE=str(registry_path),
        OPENROUTER_API_KEY="",
        RBAC_ENABLED="true",
        V1_ENABLED="true",
        V1_TOOLS_ENABLED="true",
        USAGE_REQUESTS_PER_MINUTE="*=unlimited",
    )
    with _live.start_harness(child_cwd, env) as running:
        yield running


@pytest.fixture(scope="module")
def run_facts(request, local_server, child_cwd):
    """What the report needs; written to `local-model-run.json` at teardown (AC 5)."""
    facts: dict = {"base_url": local_server["base_url"], "model": local_server["model"],
                   "server_facts": local_server["facts"], "usage": {}, "rows": {}, "tool_call": None}
    yield facts
    out = child_cwd / "local-model-run.json"
    out.write_text(json.dumps(facts, indent=2), encoding="ascii")
    reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line(f"e2e020-014: run facts written to {out}")


@pytest.fixture(scope="module")
def rows(run_child, users, run_facts):
    """rows() -> the user's audit rows, oldest first."""

    def read() -> list:
        found = _live.dump_rows(run_child, users["main"][0])
        for row in found:
            run_facts["rows"][str(row["id"])] = {key: row[key] for key in _REPORT_FIELDS}
        return found

    return read


@pytest.fixture(scope="module")
def actions(run_child, users):
    def read() -> list:
        return _live.dump_action_decisions(run_child, users["main"][0])

    return read


@pytest.fixture
def new_rows(rows):
    """new_rows() -> a callable returning the rows written since this call."""

    def mark():
        before = {row["id"] for row in rows()}
        return lambda: [row for row in rows() if row["id"] not in before]

    return mark


@pytest.fixture(scope="module")
def sdk(harness, users):
    return openai.OpenAI(base_url=f"{harness.base}/v1", api_key=users["main"][1], timeout=_CLIENT_TIMEOUT, max_retries=0)


# --------------------------------------------------------------------------
# AC 1: /query
# --------------------------------------------------------------------------


def test_query_is_answered_and_the_row_names_local(harness, users, local_server, new_rows, run_facts):
    written = new_rows()

    response = httpx.post(
        f"{harness.base}/query",
        json={"prompt": f"Reply with one short sentence about the sea. [{NONCE}-query]", "model": local_server["model"]},
        headers={"Authorization": f"Bearer {users['main'][1]}"},
        timeout=_CLIENT_TIMEOUT,
    )

    assert response.status_code == 200, response.text
    assert response.json()["response"].strip()
    [row] = written()
    assert row["success"] is True, row
    assert (row["provider"], row["provider_trust"]) == ("local", "internal")
    assert row["model_used"] == local_server["model"]
    assert row["tokens_used"] > 0
    run_facts["usage"]["query"] = _usage(row)


# --------------------------------------------------------------------------
# AC 2: /v1 through the OpenAI SDK, streamed to the client
# --------------------------------------------------------------------------


def test_sdk_v1_streamed_to_client_is_answered_and_the_row_names_local(sdk, local_server, new_rows, run_facts):
    written = new_rows()

    chunks = list(sdk.chat.completions.create(
        model=local_server["model"],
        messages=[{"role": "user", "content": f"Name one primary colour in a few words. [{NONCE}-stream]"}],
        stream=True,
        stream_options={"include_usage": True},
        temperature=0,
        max_tokens=64,
    ))

    text = "".join(chunk.choices[0].delta.content or "" for chunk in chunks if chunk.choices)
    assert text.strip()
    [row] = written()
    assert row["success"] is True, row
    assert (row["ingress"], row["streamed"]) == ("v1", True)
    assert (row["provider"], row["provider_trust"]) == ("local", "internal")
    assert row["tokens_used"] > 0
    run_facts["usage"]["v1_stream"] = _usage(row)


# --------------------------------------------------------------------------
# AC 3: a forced tool call released through the action policy
# --------------------------------------------------------------------------


def _ask_for_read(sdk, model: str, **extra):
    return sdk.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": f"Read the file notes.txt using the read tool. [{NONCE}-tool]"}],
        tools=[_READ_TOOL],
        temperature=0,
        max_tokens=128,
        **extra,
    )


def test_v1_tool_call_is_released_through_the_action_policy(sdk, local_server, new_rows, actions, run_facts):
    written = new_rows()
    quirk = None
    try:
        completion = _ask_for_read(sdk, local_server["model"], tool_choice=_FORCE_READ)
    except openai.APIStatusError as exc:
        # The server may reject a forced tool_choice (PRD-020 risk 2): retry once without it and record the
        # quirk. The harness answers 502 and records a failed row; it does not relay the server's reason.
        [failed] = written()
        assert (exc.status_code, failed["success"]) == (502, False), (exc.status_code, failed)
        quirk = f"server rejected forced tool_choice (HTTP {exc.status_code})"
        written = new_rows()
        completion = _ask_for_read(sdk, local_server["model"])

    [row] = written()
    calls = completion.choices[0].message.tool_calls or []
    run_facts["tool_call"] = {"outcome": "called" if calls else "skipped: no tool call", "tool_choice_quirk": quirk}
    run_facts["usage"]["v1_tool"] = _usage(row)
    if not calls:
        pytest.skip("model returned no tool call")

    assert row["success"] is True, row
    assert (row["provider"], row["has_tool_calls"]) == ("local", True)
    call = calls[0]
    assert call.function.name == "read"
    decided = [a for a in actions() if a["audit_id"] == row["id"]]
    assert len(decided) == len(calls), decided
    first = next(a for a in decided if a["tool_call_id"] == call.id)
    assert (first["tool_name"], first["decision"], first["rule"]) == ("read", "allow", "fs.read")


# --------------------------------------------------------------------------
# AC 5: what the report needs
# --------------------------------------------------------------------------


def test_zz_facts_recorded(run_facts):
    assert set(run_facts["server_facts"]) >= {"server", "version", "digest", "model_info"}
    assert set(run_facts["usage"]) >= {"query", "v1_stream"}, run_facts["usage"]
    assert all(value in ("real", "estimated") for value in run_facts["usage"].values())
    assert run_facts["tool_call"] is not None
    assert run_facts["rows"], "no audit row was recorded"
