"""What the MCP gateway costs per call, measured rather than argued about.

PRD-023 STORY-019, serving the Section 11 quality indicator: "Gateway overhead
(M0-M9 excluding the upstream round trip) p95 measured against the stub on a
local libSQL file ... target <= 25 ms. The gateway makes at most three database
round trips per call (admit, link lookup plus insert, outcome)". Like
`scripts/measure_usage_latency.py` and `scripts/measure_v1_latency.py` it is a
spike: it *records* numbers and asserts no latency. The round trips are
deterministic, so they are counted and reported with their own verdict.

Two arms, each timed over `--runs` iterations after one discarded warm-up call
(which opens the upstream session and fills the tools cache):

    denied   -- `stub__query` with DROP TABLE as `dev`: decided `sql.ddl`, row
                written, nothing forwarded (M0-M7, deny note)
    allowed  -- `stub__query` with SELECT: row written, forwarded to the stub,
                result screened, outcome written (M0-M9)

and two figures per arm, both **excluding the upstream round trip** (the time
spent inside `mcp_upstream.call_tool` and `mcp_upstream.list_tools` is
subtracted per call; a tools-cache refresh is an upstream round trip):

    M0-M9   the request through `TestClient` on a bare `FastAPI` app with
            `mcp_router.router` (auth patched to the bench identity). The
            TestClient adds about 1-2 ms of its own (a thread hop and the ASGI
            plumbing), which a real server does not pay.
    M3-M9   `mcp_gateway.call` alone, on the same event loop through the
            portal: the gateway's own work.

**Database.** An embedded libSQL file in a temp directory, removed on exit; the
script takes no database URL and can never touch a shared database.
`Settings` refuses a file URL at import (`app/config.py`) but does not validate
on assignment, so the script sets `DATABASE_URL` to a placeholder before the
`app.` imports and assigns the file path afterwards. That override lives here
and nowhere in `app/`. The placeholder is never connected to.

**Round trips.** Every `database.get_connection()` is one unit of work
(`_session`); the opens are counted per call, with the names of the units of
work and the statements each issues. The usage gate is real (`USAGE_LIMITS_ENABLED`,
a bench identity with a rate override far above `--runs`), and the `/v1` alias
prefixes are configured so the allowed arm takes the claim path
(`insert_mcp_decision_linked`), the one the three-trip budget is about.

Usage:

    python scripts/measure_mcp_latency.py
    python scripts/measure_mcp_latency.py --runs 200
"""

import argparse
import math
import os
import platform
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# `app.config.settings` is built at import and refuses a file URL, so the
# environment gets a placeholder (never connected to) *before* the first `app.`
# import; `_run` assigns the real file afterwards. Same bootstrap order as
# scripts/measure_usage_latency.py: do not "tidy" the imports above it.
_PLACEHOLDER_ENDPOINT = "http://127.0.0.1:8080"
os.environ["DATABASE_URL"] = _PLACEHOLDER_ENDPOINT
os.environ.setdefault("OPENROUTER_API_KEY", "measurement-stub-key")
os.environ.setdefault("ADMIN_TOKEN", "measurement-admin-token")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import database  # noqa: E402
from app.routers import mcp as mcp_router  # noqa: E402
from app.services import (  # noqa: E402
    action_config,
    authz,
    mcp_config,
    mcp_gateway,
    mcp_upstream,
)
from app.services.identity import Identity  # noqa: E402
from app.services.mcp_config import McpAuth, McpConfig, McpServer, Skill  # noqa: E402

ARMS = ("denied", "allowed")
FIGURES = ("M0-M9", "M3-M9")

#: Far above any --runs, so every admit is an admitted one.
_BENCH_RATE = 10**9
_SKILL_ID = "bench"
_TOKEN = "bench-token"
_POLICY = "mcp_tools:\n  stub:\n    query: {kind: sql, target: sql}\n"
_ARGUMENTS = {
    "denied": {"sql": "DROP TABLE accounts"},
    "allowed": {"sql": "SELECT 1"},
}
#: Section 11: admit, link lookup plus insert, outcome.
_MAX_UNITS = 3
_DEFAULT_TARGET_MS = 25.0


# --------------------------------------------------------------------------
# Recording, copied from scripts/measure_usage_latency.py
# --------------------------------------------------------------------------


class Recording:
    """A connection proxy that records the SQL issued through it.

    `__enter__`/`__exit__` are not decoration: `database._session()` does
    `with conn:`, so a proxy without them turns every write into an
    AttributeError instead of a measurement.
    """

    def __init__(self, conn, statements):
        self._conn = conn
        self._statements = statements

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, *exc_info):
        return self._conn.__exit__(*exc_info)

    def execute(self, sql, *parameters):
        self._statements.append(sql)
        return self._conn.execute(sql, *parameters)

    def cursor(self):
        return self._conn.cursor()


class Counted:
    """What one call did to the database: the units of work and the SQL they issued."""

    def __init__(self):
        self.units: list[str] = []
        self.opens = 0
        self.statements: list[str] = []


def _counting(work: Callable[[], object]) -> tuple[object, Counted]:
    """Runs `work()`, returning its result and what it did to the database.

    Replaces `database.get_connection` (every open is one unit of work) and
    `database._unit_of_work` (for the names). Both are module globals the
    callers look up at call time, as `tests/test_mcp_correlation.py` relies on.
    """
    counted = Counted()
    real_connection, real_unit = database.get_connection, database._unit_of_work

    def connection():
        counted.opens += 1
        return Recording(real_connection(), counted.statements)

    def unit(name, kind, op):
        counted.units.append(name)
        return real_unit(name, kind, op)

    database.get_connection, database._unit_of_work = connection, unit
    try:
        result = work()
    finally:
        database.get_connection, database._unit_of_work = real_connection, real_unit
    return result, counted


# --------------------------------------------------------------------------
# Timing, copied from scripts/measure_usage_latency.py
# --------------------------------------------------------------------------


class Samples:
    """Wall-clock samples (overhead, ms) for one arm and figure."""

    def __init__(self, label: str):
        self.label = label
        self.values: list[float] = []

    def add(self, milliseconds: float) -> None:
        self.values.append(milliseconds)

    @property
    def n(self) -> int:
        return len(self.values)

    def summary(self) -> tuple[float, float, float]:
        """(min, p50, p95) in milliseconds; p95 is nearest-rank, sorted[ceil(0.95 * n) - 1]."""
        ordered = sorted(self.values)
        return min(ordered), statistics.median(ordered), ordered[math.ceil(0.95 * len(ordered)) - 1]


class UpstreamClock:
    """Time spent in the upstream seams, accumulated per call and reset by the sampler."""

    def __init__(self):
        self.elapsed_ms = 0.0

    def wrap(self, module, name: str) -> None:
        real = getattr(module, name)

        async def timed(*args, **kwargs):
            started = time.perf_counter()
            try:
                return await real(*args, **kwargs)
            finally:
                self.elapsed_ms += (time.perf_counter() - started) * 1000

        setattr(module, name, timed)


# --------------------------------------------------------------------------
# The measured world
# --------------------------------------------------------------------------


def _configure(workdir: Path, stub_url: str) -> Identity:
    """File database, config, policy and a bench identity; returns the identity."""
    settings.DATABASE_URL = str(workdir / "mcp-latency.db")
    database.init_db()
    settings.RBAC_ENABLED = True
    settings.USAGE_LIMITS_ENABLED = True
    settings.MCP_ALLOWED_ORIGINS = ""
    authz.ROLE_PERMISSIONS = {"dev": {f"skill:{_SKILL_ID}", "mcp:connect"}}
    policy_file = workdir / "action_policy.yaml"
    policy_file.write_text(_POLICY, encoding="utf-8")
    settings.ACTION_POLICY_FILE = str(policy_file)
    action_config.load()
    server = McpServer("stub", stub_url, True, McpAuth(type="none"), 30, 1_048_576)
    mcp_config._config = McpConfig(
        servers={"stub": server},
        skills=(Skill(_SKILL_ID, "1.0.0", "d", "i", ("stub__query",), ()),),
        v1_prefixes=("harness_",),
    )
    identity = Identity(
        user_id="bench-user", role="dev", requests_per_minute=_BENCH_RATE, token_budget_daily=None
    )
    import app.middleware.auth as auth

    auth.resolve = lambda token: identity
    return identity


def _post(client: TestClient, arm: str, rpc_id: int):
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0", "id": rpc_id, "method": "tools/call",
            "params": {"name": "stub__query", "arguments": _ARGUMENTS[arm]},
        },
        headers={"Authorization": f"Bearer {_TOKEN}", "Content-Type": "application/json"},
    )
    result = response.json().get("result")
    if response.status_code != 200 or result is None:
        raise Unanswered(f"{arm}: HTTP {response.status_code}: {response.text[:200]}")
    if result["isError"] is not (arm == "denied"):
        raise Unanswered(f"{arm}: unexpected isError={result['isError']}: {response.text[:200]}")
    return response


def _direct(client: TestClient, identity: Identity, arm: str, rpc_id: int):
    params = {"name": "stub__query", "arguments": _ARGUMENTS[arm]}
    result = client.portal.call(mcp_gateway.call, identity, params, rpc_id)
    if result["isError"] is not (arm == "denied"):
        raise Unanswered(f"{arm}: unexpected isError={result['isError']}")
    return result


class Unanswered(RuntimeError):
    """A call that should have been decided and answered was not: the numbers would mean nothing."""


def _sample(work: Callable[[], object], clock: UpstreamClock) -> float:
    """Overhead in ms: wall time of `work()` minus the time it spent upstream."""
    clock.elapsed_ms = 0.0
    started = time.perf_counter()
    work()
    return (time.perf_counter() - started) * 1000 - clock.elapsed_ms


def _measure(client: TestClient, identity: Identity, clock: UpstreamClock, runs: int):
    """`(samples[(arm, figure)], counted[arm])`."""
    samples = {(arm, figure): Samples(f"{arm} {figure}") for arm in ARMS for figure in FIGURES}
    ids = iter(range(1, 10**9))
    for arm in ARMS:
        _post(client, arm, next(ids))  # warm-up, discarded
        _direct(client, identity, arm, next(ids))
    for arm in ARMS:
        for _ in range(runs):
            samples[(arm, "M0-M9")].add(_sample(lambda: _post(client, arm, next(ids)), clock))
            samples[(arm, "M3-M9")].add(_sample(lambda: _direct(client, identity, arm, next(ids)), clock))
    counted = {}
    for arm in ARMS:
        _, counted[arm] = _counting(lambda: _post(client, arm, next(ids)))
    return samples, counted


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def _first_words(statements: Sequence[str]) -> str:
    return ", ".join(" ".join(s.split()[:3]) for s in statements) or "(none)"


def _report(
    samples: dict,
    counted: dict,
    runs: int,
    target_ms: float,
    stub_port: Optional[int] = None,
) -> str:
    worst = max(samples[(arm, "M0-M9")].summary()[2] for arm in ARMS)
    verdict = "MET" if worst <= target_ms else "MISSED"
    units = {arm: counted[arm].opens for arm in ARMS}
    trips = "MET" if max(units.values()) <= _MAX_UNITS else "EXCEEDED"
    lines = [
        "",
        "--- PRD-023 STORY-019 MCP gateway latency ---",
        "  database      : embedded libSQL file (temp directory, removed on exit)",
        f"  upstream      : stub MCP server on 127.0.0.1:{stub_port}" if stub_port else "  upstream      : stub MCP server",
        f"  host          : {platform.node()} ({platform.system()} {platform.release()})",
        f"  python        : {platform.python_version()}",
        f"  runs          : {runs} timed per arm and figure, after 1 discarded warm-up call per arm",
        "  overhead      : request time minus the time spent in mcp_upstream.call_tool / list_tools",
        "  M0-M9 includes the TestClient's own ~1-2 ms; M3-M9 is mcp_gateway.call alone.",
        "  p50 is the median; p95 is nearest-rank, sorted[ceil(0.95*n)-1]. No latency is asserted.",
        "",
        f"  {'arm':<8} {'figure':<7} {'n':>4} {'min ms':>9} {'p50 ms':>9} {'p95 ms':>9}",
    ]
    for arm in ARMS:
        for figure in FIGURES:
            low, p50, p95 = samples[(arm, figure)].summary()
            lines.append(f"  {arm:<8} {figure:<7} {samples[(arm, figure)].n:>4} {low:>9.2f} {p50:>9.2f} {p95:>9.2f}")
    lines += [""]
    lines.append(
        "  units per call        : "
        + ", ".join(f"{arm} {units[arm]} ({'+'.join(counted[arm].units) or 'none'})" for arm in ARMS)
        + f" (limit {_MAX_UNITS}) -> {trips}"
    )
    lines.append(
        "  statements per call   : "
        + ", ".join(f"{arm} {len(counted[arm].statements)} ({_first_words(counted[arm].statements)})" for arm in ARMS)
        + " (informational)"
    )
    for figure in FIGURES:
        lines.append(
            f"  p95 ms ({figure}, upstream excluded) : "
            + ", ".join(f"{arm} {samples[(arm, figure)].summary()[2]:.2f}" for arm in ARMS)
        )
    lines += [
        f"  PRD-023 target (Section 11): p95 <= {target_ms:g} ms, worst M0-M9 arm {worst:.2f} ms -> {verdict}",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _run(runs: int, target_ms: float) -> int:
    from tests.mcp_stub import start_stub  # the suite's stub launcher (a subprocess on a free port)

    workdir = Path(tempfile.mkdtemp(prefix="mcp-latency-"))
    stub = None
    try:
        stub = start_stub(workdir)
        identity = _configure(workdir, stub.url)
        clock = UpstreamClock()
        clock.wrap(mcp_upstream, "call_tool")
        clock.wrap(mcp_upstream, "list_tools")
        app = FastAPI()
        app.include_router(mcp_router.router)
        with TestClient(app) as client:
            try:
                samples, counted = _measure(client, identity, clock, runs)
            finally:
                client.portal.call(mcp_upstream.aclose_all)
        print(_report(samples, counted, runs, target_ms, stub.port))
        return 0
    except Unanswered as exc:
        print(f"A call was not answered as expected, so there is no report: {exc}", file=sys.stderr)
        return 1
    finally:
        if stub is not None:
            stub.stop()
        database._invalidate_client()
        shutil.rmtree(workdir, ignore_errors=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Measure the MCP gateway's overhead (M0-M9 and M3-M9, upstream excluded) and its "
            "database round trips against the stub on a local libSQL file (PRD-023 STORY-019). "
            "Records numbers; asserts none."
        )
    )
    parser.add_argument("--runs", type=int, default=50, help="timed runs per arm and figure (default 50)")
    parser.add_argument(
        "--target-ms", type=float, default=_DEFAULT_TARGET_MS,
        help=f"p95 target in ms, printed as MET or MISSED (default {_DEFAULT_TARGET_MS:g})",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.runs < 1:
        print("--runs must be at least 1", file=sys.stderr)
        return 1
    return _run(args.runs, args.target_ms)


if __name__ == "__main__":
    sys.exit(main())
