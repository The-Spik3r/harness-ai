"""What the OpenAI-compatible ingress adds to a request, measured rather than argued about.

PRD-015 STORY-019, serving Section 11's quality indicator: "Added `/v1`
overhead over `/query` for the same conversation, measured with the stub
upstream: p95 under 10 ms for translation, reported in the README". This is a
spike: it *records* numbers and asserts none of them, exactly as
`scripts/measure_usage_latency.py` does. A wall-clock threshold asserted as
pass/fail would be a flaky test on a loaded machine. Both verdict lines it
prints are information, never an exit code, and a miss prints as a miss.

Three arms are timed, each over `--runs` iterations:

    query      -- POST /query {"prompt": ..., "model": ...}
    v1         -- POST /v1/chat/completions, the same text as one user turn,
                  not streamed
    translate  -- translate_request + translate_result + the JSON encoding of
                  the completion: the translation itself, with no I/O

`query` and `v1` go through the real app (`TestClient(app)`, lifespan
included), real bearer authentication, the real pipeline and the real
`call_openrouter`. The upstream is `scripts/stub_openrouter.py`, in this
process on a loopback port, so every request makes a real HTTP call and
writes its real audit row to the local libSQL server. What the two arms share
cancels out; what is left is what `/v1` adds. The report gives both the
end-to-end difference (v1 p95 - query p95) and the translation-only p95,
because the first carries two database round trips of jitter per request
(README, Usage limits) and the PRD's target is stated for the second.

**Why PII redaction is off by default.** `/query` runs the `chat` profile,
which runs Presidio's named-entity model on the prompt; `/v1` runs `code`,
which runs pattern recognizers only. With redaction on, the difference
measures the two profiles and comes out negative, which says nothing about
translation. `--pii on` keeps it on, for the figure a default deployment sees.

**Why the prompts differ.** The duplicate check is per user and spans both
ingresses, so the same text twice is a `BLOCKED` the second time. Each request
carries a suffix of the same length on both arms (`run <nonce>-<i>-<arm>`),
and the run is otherwise one conversation: one user turn, the same model, the
same stub answer. The bench user's `requests_per_minute` override is far
above the request count, so no run is rate-refused; its token budget is the
role's, which 17 tokens a request cannot reach. A request that is not
answered (a block, a fault) aborts the run rather than becoming a sample.

**Order.** One warm-up request per arm is discarded (analyzer, first
connection, first route call). The timed runs are interleaved, `query` then
`v1` on even runs and the reverse on odd ones, so drift hits both arms alike.

This script creates one user with a per-run nonce (`story019-bench-<hex>`)
and deactivates it on the way out. The audit rows it writes, 2 x (runs + 1),
stay: `audit_logs` is the evidentiary log and has no delete path. That is why
it refuses a non-local `DATABASE_URL` unless told otherwise.

Usage:

    python scripts/measure_v1_latency.py
    python scripts/measure_v1_latency.py --runs 50 --pii on
    python scripts/measure_v1_latency.py --database-url http://127.0.0.1:8080

The dev server is the one the suite uses (tests/conftest.py):

    docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary \
      ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67
"""

import argparse
import io
import math
import os
import platform
import statistics
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional, Sequence
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# `app.config.settings` is a module-level singleton built at import time, and
# DATABASE_URL has no default, so the endpoint has to be in the environment
# *before* the first `app.` import, not after argparse has run. Same bootstrap
# as scripts/measure_usage_latency.py:73-125, and the same warning: do not
# "tidy" the imports back above it.
#
# The stub's base URL is deliberately *not* set here: the stub binds port 0
# when a run starts, and importing this module must start nothing.
# `call_openrouter` reads settings.OPENROUTER_BASE_URL on every call
# (app/services/openrouter_client.py), so assigning it after the bind is
# enough.
_DEFAULT_ENDPOINT = "http://127.0.0.1:8080"


def _database_url(argv: Optional[Sequence[str]]) -> str:
    """--database-url, else HARNESS_TEST_LIBSQL_URL, else the dev server."""
    args = list(sys.argv[1:] if argv is None else argv)
    for index, item in enumerate(args):
        if item == "--database-url" and index + 1 < len(args):
            return args[index + 1]
        if item.startswith("--database-url="):
            return item.split("=", 1)[1]
    return os.environ.get("HARNESS_TEST_LIBSQL_URL") or _DEFAULT_ENDPOINT


def _bootstrap_environment(argv: Optional[Sequence[str]] = None) -> str:
    endpoint = _database_url(argv)
    os.environ["DATABASE_URL"] = endpoint
    # Required by Settings() with no default. The key never leaves the
    # process: the only upstream is the in-process stub.
    os.environ.setdefault("OPENROUTER_API_KEY", "measurement-stub-key")
    os.environ.setdefault("ADMIN_TOKEN", "measurement-admin-token")
    return endpoint


_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]", "0.0.0.0"}


def _guard_local(endpoint: str, allow_remote: bool) -> None:
    if allow_remote:
        return
    host = urlsplit(endpoint).hostname or ""
    if host in _LOCAL_HOSTS:
        return
    raise SystemExit(
        f"Refusing to write to a non-local database: {endpoint}\n"
        "This script creates a bench user and writes audit rows that cannot "
        "be deleted. Point --database-url at the local libSQL dev server, or "
        "pass --allow-remote-database if you are certain."
    )


_ENDPOINT = _bootstrap_environment()

# As a program, the guard runs *here*, before the first `app.` import, for the
# reason scripts/measure_usage_latency.py gives: Settings() would otherwise
# refuse a remote URL without TURSO_AUTH_TOKEN with its own traceback first.
if __name__ == "__main__":
    _guard_local(_ENDPOINT, "--allow-remote-database" in sys.argv[1:])

from app.config import settings  # noqa: E402
from app.db import database  # noqa: E402
from app.db.models import User  # noqa: E402
from app.models.schemas import QuerySuccessResponse  # noqa: E402
from app.models.v1_schemas import ChatCompletionRequest  # noqa: E402
from app.services.identity import hash_token, issue_token  # noqa: E402
from app.services.openrouter_client import OpenRouterResult  # noqa: E402
from app.services.v1_translate import translate_request, translate_result  # noqa: E402
from scripts.stub_openrouter import make_server, parse_script  # noqa: E402

#: Far above any request count, so every timed request is an admitted one.
_BENCH_RATE = 10**9

#: What the stub answers every request with. 17 tokens a request.
_STUB_CONTENT = "The release adds an OpenAI-compatible endpoint."
_STUB_USAGE = {"prompt_tokens": 12, "completion_tokens": 5}
_STUB_SCRIPT = {
    "default": {"content": _STUB_CONTENT, "finish_reason": "stop", "usage": _STUB_USAGE}
}

#: PRD-015 Section 11: "p95 under 10 ms for translation".
TARGET_MS = 10.0

ARMS = ("query", "v1", "translate")


# --------------------------------------------------------------------------
# Timing, copied from scripts/measure_usage_latency.py:182-218
# --------------------------------------------------------------------------


class Samples:
    """Wall-clock samples for one arm, summarised the way the report needs."""

    def __init__(self, label: str):
        self.label = label
        self.values: list[float] = []

    def add(self, milliseconds: float) -> None:
        self.values.append(milliseconds)

    @property
    def n(self) -> int:
        return len(self.values)

    def summary(self) -> tuple[float, float, float]:
        """(min, p50, p95) in milliseconds.

        p50 is the median. p95 is the *nearest-rank* percentile,
        sorted[ceil(0.95 * n) - 1], the same method as the other measurement
        scripts so their numbers compare.
        """
        ordered = sorted(self.values)
        p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
        return min(ordered), statistics.median(ordered), p95


def _timed(work: Callable[[], object]) -> tuple[object, float]:
    """(result, elapsed_ms)."""
    started = time.perf_counter()
    result = work()
    return result, (time.perf_counter() - started) * 1000


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------


class NotAnswered(RuntimeError):
    """A request the bench expected answered was blocked or failed."""


def _prompt(nonce: str, run: str, arm: str) -> str:
    """The conversation's one user turn; the suffix only defeats the duplicate check."""
    return f"Summarise the release notes, run {nonce}-{run}-{arm}"


def _query_body(text: str, model: str) -> dict:
    return {"prompt": text, "model": model}


def _v1_body(text: str, model: str) -> dict:
    return {"model": model, "messages": [{"role": "user", "content": text}]}


def _send_query(client, headers: dict, text: str, model: str) -> dict:
    response = client.post("/query", json=_query_body(text, model), headers=headers)
    body = response.json()
    if response.status_code != 200 or body.get("status") != "SUCCESS":
        # Status and reason only: never the prompt or the answer.
        raise NotAnswered(
            f"/query was not answered: {response.status_code} {body.get('reason') or body.get('detail')}"
        )
    return body


def _send_v1(client, headers: dict, text: str, model: str) -> dict:
    response = client.post("/v1/chat/completions", json=_v1_body(text, model), headers=headers)
    body = response.json()
    if response.status_code != 200 or body.get("object") != "chat.completion":
        error = body.get("error") or {}
        raise NotAnswered(
            f"/v1/chat/completions was not answered: {response.status_code} {error.get('code')}"
        )
    return body


def _translate_once(body: dict, result: QuerySuccessResponse, upstream: OpenRouterResult) -> str:
    """What the router does around the pipeline, and nothing else."""
    translate_request(ChatCompletionRequest.model_validate(body))
    return translate_result(result, upstream, int(time.time())).model_dump_json()


def _measure(client, headers: dict, model: str, nonce: str, runs: int) -> dict[str, Samples]:
    arms = {name: Samples(name) for name in ARMS}
    send = {
        "query": lambda text: _send_query(client, headers, text, model),
        "v1": lambda text: _send_v1(client, headers, text, model),
    }

    # Warm-up, discarded: the first request on each arm.
    query_body = send["query"](_prompt(nonce, "warm", "query"))
    send["v1"](_prompt(nonce, "warm", "v1"))

    for i in range(runs):
        order = ("query", "v1") if i % 2 == 0 else ("v1", "query")
        for arm in order:
            body, elapsed = _timed(lambda: send[arm](_prompt(nonce, str(i), arm)))
            arms[arm].add(elapsed)
            if arm == "query":
                query_body = body

    # The translation arm's inputs are a real answer: the last /query success,
    # and the upstream result the stub returned for it.
    result = QuerySuccessResponse.model_validate(query_body)
    upstream = OpenRouterResult(
        response=_STUB_CONTENT,
        model_used=model,
        tokens_used=result.tokens_used,
        input_tokens=_STUB_USAGE["prompt_tokens"],
        output_tokens=_STUB_USAGE["completion_tokens"],
        finish_reason="stop",
    )
    body = _v1_body(_prompt(nonce, "translate", "v1"), model)
    _translate_once(body, result, upstream)  # warm-up, discarded
    for _ in range(runs):
        _, elapsed = _timed(lambda: _translate_once(body, result, upstream))
        arms["translate"].add(elapsed)
    return arms


# --------------------------------------------------------------------------
# The bench user and the stub
# --------------------------------------------------------------------------


def _create_bench_user(user_id: str) -> str:
    """The user's token. Mirrors scripts/manage_users.py create-user, plus the rate override."""
    token = issue_token()
    database.insert_user(User(user_id=user_id, role="user", token_hash=hash_token(token)))
    database.set_user_limits(user_id, requests_per_minute=_BENCH_RATE)
    return token


def _audit_row_count(user_id: str) -> int:
    return len(database.list_audit_logs(limit=100_000, user_id=user_id))


def _start_stub():
    """A serving stub on a free loopback port, logging to a buffer so the report stays clean."""
    server = make_server(parse_script(_STUB_SCRIPT), port=0, log=io.StringIO())
    thread = threading.Thread(target=server.serve_forever, name="stub-openrouter", daemon=True)
    thread.start()
    return server, thread


def _stop_stub(server, thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=10)


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def _verdict(p95: float) -> str:
    return "MET" if p95 < TARGET_MS else "MISSED"


def _report(
    arms: dict[str, Samples],
    runs: int,
    endpoint: str,
    stub: str,
    model: str,
    pii: str,
) -> str:
    lines = [
        "",
        "--- PRD-015 STORY-019 /v1 translation latency ---",
        f"  endpoint     : {endpoint}",
        f"  stub         : {stub}",
        f"  host         : {platform.node()} ({platform.system()} {platform.release()})",
        f"  python       : {platform.python_version()}",
        f"  runs         : {runs} timed per arm, after 1 discarded warm-up each; query/v1 interleaved",
        f"  model        : {model}",
        f"  pii          : {pii} (PII_REDACTION_ENABLED={'true' if pii == 'on' else 'false'})",
        "",
        "  p50 is the median; p95 is nearest-rank, sorted[ceil(0.95*n)-1].",
        "  No latency here is asserted as a pass/fail bound.",
        "",
        f"  {'arm':<10} {'n':>4} {'min ms':>9} {'p50 ms':>9} {'p95 ms':>9}",
    ]
    for name in ARMS:
        low, p50, p95 = arms[name].summary()
        lines.append(f"  {name:<10} {arms[name].n:>4} {low:>9.2f} {p50:>9.2f} {p95:>9.2f}")

    _, query_p50, query_p95 = arms["query"].summary()
    _, v1_p50, v1_p95 = arms["v1"].summary()
    _, _, translate_p95 = arms["translate"].summary()
    added_p95 = v1_p95 - query_p95
    lines.extend(
        [
            "",
            f"  added p50, end to end (v1 p50 - query p50) : {v1_p50 - query_p50:+.2f} ms",
            f"  added p95, end to end (v1 p95 - query p95) : {added_p95:+.2f} ms",
            f"  translation p95                            : {translate_p95:.2f} ms",
            "",
            f"  {f'PRD-015 target (Section 11): translation p95 < {TARGET_MS:.0f} ms':<56} -> "
            f"{_verdict(translate_p95)}",
            f"  {f'end-to-end added p95 vs {TARGET_MS:.0f} ms':<56} -> "
            + ("within" if added_p95 < TARGET_MS else "over"),
            "",
        ]
    )
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _measure_command(args: argparse.Namespace) -> int:
    if args.runs < 1:
        print("--runs must be at least 1", file=sys.stderr)
        return 1

    _guard_local(_ENDPOINT, args.allow_remote_database)

    if not settings.V1_ENABLED:
        print("V1_ENABLED is false, so /v1 is not mounted; nothing to compare.", file=sys.stderr)
        return 1
    models = settings.model_allowlist_list
    if not models:
        print("MODEL_ALLOWLIST is empty; no model a user may request.", file=sys.stderr)
        return 1
    model = models[0]

    # Imported here, not at the top: app.main builds the app and its routes,
    # which the import-time test does not need.
    from fastapi.testclient import TestClient

    from app.main import app

    database.init_db()
    nonce = uuid.uuid4().hex[:8]
    user_id = f"{args.user_id}-{nonce}"
    # Before the lifespan: startup refuses a database with no user at all.
    token = _create_bench_user(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    saved = (settings.OPENROUTER_BASE_URL, settings.PII_REDACTION_ENABLED)
    server, thread = _start_stub()
    stub = f"http://127.0.0.1:{server.server_address[1]}/v1"
    try:
        settings.OPENROUTER_BASE_URL = stub
        settings.PII_REDACTION_ENABLED = args.pii == "on"
        with TestClient(app) as client:
            arms = _measure(client, headers, model, nonce, args.runs)
        print(_report(arms, args.runs, _ENDPOINT, stub, model, args.pii))
    except NotAnswered as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        settings.OPENROUTER_BASE_URL, settings.PII_REDACTION_ENABLED = saved
        _stop_stub(server, thread)
        rows = _audit_row_count(user_id)
        if args.keep:
            print(f"  kept bench user {user_id} active (--keep); it wrote {rows} audit row(s)")
        else:
            database.deactivate_user(user_id)
            print(f"  deactivated bench user {user_id}; it wrote {rows} audit row(s), which stay")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Measure p50/p95 of POST /query, POST /v1/chat/completions and the "
            "/v1 translation, against the stub upstream (PRD-015 STORY-019). "
            "Records numbers; asserts none."
        )
    )
    parser.add_argument(
        "--runs", type=int, default=50, help="timed runs per arm (default 50)"
    )
    parser.add_argument(
        "--database-url",
        default=_ENDPOINT,
        help=(
            "libSQL endpoint to write to; read before argparse runs "
            "(default: $HARNESS_TEST_LIBSQL_URL or " + _DEFAULT_ENDPOINT + ")"
        ),
    )
    parser.add_argument(
        "--user-id",
        default="story019-bench",
        help="bench user id prefix; a per-run nonce is appended (default story019-bench)",
    )
    parser.add_argument(
        "--pii",
        choices=("off", "on"),
        default="off",
        help="PII redaction during the run (default off: see the module docstring)",
    )
    parser.add_argument(
        "--keep", action="store_true", help="leave the bench user active"
    )
    parser.add_argument(
        "--allow-remote-database",
        action="store_true",
        help="write to a non-local DATABASE_URL (refused by default)",
    )
    parser.set_defaults(func=_measure_command)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
