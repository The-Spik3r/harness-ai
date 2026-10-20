"""What checking a usage limit costs, measured rather than argued about.

PRD-013 STORY-017, serving F17 and Risk 1 ("counter round trips add latency to
every request: one for the gate, one for the charge"). This is a spike: it
*records* numbers and asserts none of them, exactly as
`scripts/measure_history_latency.py` and `tests/test_two_instance_smoke.py` do.
A wall-clock threshold asserted as pass/fail would be a flaky test on a loaded
machine.

Two calls are timed, each over `--runs` iterations, and nothing else:

    admit   -- usage_limits.admit(identity, charges_budget=True)
    charge  -- usage_limits.charge(user_id, admission.day, 5, 2, 7)

These are the two service calls the pipeline makes (steps 2c and 7b of
app/services/query_pipeline.py), **not** the pipeline. What a whole request
costs with them is test_round_trip_cost_is_measured_and_reported's job; what
this script answers is how much of that cost is the counter.

**Which variant is measured.** STORY-009 verified that `RETURNING` works on
`libsql==0.1.11` and shipped Path A: `admit_usage` is one `INSERT ... ON
CONFLICT ... DO UPDATE ... RETURNING`, one round trip. The upsert-plus-`SELECT`
fallback (PRD-013 Risk 2) was never built. The script does not take that on
trust: before timing, it records the SQL each call issues and refuses to run
unless each issued exactly one statement.

**Why every run is admitted.** The bench identity carries a
`requests_per_minute` override far above `--runs`, so a run of 100 does not
start measuring the refusal path at the 61st admit. Its budget is the role's
(`*=1000000` by default), which 7 tokens a run cannot reach. Every admission is
checked, and a refusal aborts the run rather than becoming a sample.

**The first admit is not measured.** It takes the insert path and creates the
day's row; every later admit takes the conflict path, the one a user's second
and later requests take. One warm-up pair is run and discarded, so both
samples are steady-state.

This script writes one `usage_daily` row, for a bench user id with a per-run
nonce. It refuses a non-local `DATABASE_URL` unless told otherwise, and deletes
that row on the way out.

Usage:

    python scripts/measure_usage_latency.py
    python scripts/measure_usage_latency.py --runs 100
    python scripts/measure_usage_latency.py --database-url http://127.0.0.1:8080
    TURSO_AUTH_TOKEN=... python scripts/measure_usage_latency.py \
      --database-url libsql://<db>.turso.io --allow-remote-database

The dev server is the one the suite uses (tests/conftest.py):

    docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary \
      ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67
"""

import argparse
import math
import os
import platform
import statistics
import sys
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
# as scripts/measure_history_latency.py:74-98, and the same warning: do not
# "tidy" the imports back above it.
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
    # Required by Settings() with no default; irrelevant to what is measured,
    # because no upstream call and no admin route is made.
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
        "This script writes (and then deletes) one usage_daily row. Point "
        "--database-url at the local libSQL dev server, or pass "
        "--allow-remote-database if you are certain."
    )


_ENDPOINT = _bootstrap_environment()

# As a program, the guard runs *here*, before the first `app.` import, and not
# only in _measure_command. Settings() validates at import and refuses a remote
# URL without TURSO_AUTH_TOKEN with a traceback that would hide this message,
# and a remote URL that has a token should still be refused for the guard's
# reason. When the tests import the module there is no command line to read,
# so it does nothing.
if __name__ == "__main__":
    _guard_local(_ENDPOINT, "--allow-remote-database" in sys.argv[1:])

from app.db import database  # noqa: E402
from app.services import usage_limits  # noqa: E402
from app.services.identity import Identity  # noqa: E402

#: Far above any --runs, so every timed admit is an admitted one.
_BENCH_RATE = 10**9

#: What each run charges: a split report, the common case since STORY-003.
_INPUT_TOKENS, _OUTPUT_TOKENS = 5, 2
_TOTAL_TOKENS = _INPUT_TOKENS + _OUTPUT_TOKENS

_VARIANT = (
    "STORY-009 Path A: admit = one INSERT ... ON CONFLICT ... RETURNING, "
    "charge = one UPDATE (no upsert+SELECT fallback)"
)


# --------------------------------------------------------------------------
# Recording, copied from scripts/measure_history_latency.py:265-300
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


def _statements_of(work: Callable[[], object]) -> tuple[object, list[str]]:
    """Runs work(), returning its result and the SQL statements it issued."""
    statements: list[str] = []
    real = database.get_connection
    database.get_connection = lambda: Recording(real(), statements)
    try:
        result = work()
    finally:
        database.get_connection = real
    return result, statements


# --------------------------------------------------------------------------
# Timing, copied from scripts/measure_history_latency.py:309-341
# --------------------------------------------------------------------------


class Samples:
    """Wall-clock samples for one call, summarised the way the report needs."""

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
        sorted[ceil(0.95 * n) - 1], the same method as
        measure_history_latency.py so the two scripts' numbers compare.
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
# Measurement
# --------------------------------------------------------------------------


class NotAdmitted(RuntimeError):
    """An admit the bench identity should have passed was refused."""


def _bench_identity(user_id: str) -> Identity:
    return Identity(
        user_id=user_id,
        role="user",
        requests_per_minute=_BENCH_RATE,
        token_budget_daily=None,
    )


def _admit(identity: Identity) -> usage_limits.Admission:
    admission = usage_limits.admit(identity, charges_budget=True)
    if not admission.admitted:
        raise NotAdmitted(f"admit refused the bench identity: {admission.refusal}")
    return admission


def _charge(identity: Identity, day: str) -> None:
    usage_limits.charge(
        identity.user_id, day, _INPUT_TOKENS, _OUTPUT_TOKENS, _TOTAL_TOKENS
    )


def _statement_check(identity: Identity) -> tuple[list[str], list[str]]:
    """The SQL one admit and one charge issue: the variant, observed."""
    admission, admit_statements = _statements_of(lambda: _admit(identity))
    _, charge_statements = _statements_of(lambda: _charge(identity, admission.day))
    return admit_statements, charge_statements


def _measure(identity: Identity, runs: int) -> dict[str, Samples]:
    arms = {"admit": Samples("admit"), "charge": Samples("charge")}

    # Warm-up, discarded: the insert path, and the client's first round trip.
    warm = _admit(identity)
    _charge(identity, warm.day)

    for _ in range(runs):
        admission, admit_ms = _timed(lambda: _admit(identity))
        _, charge_ms = _timed(lambda: _charge(identity, admission.day))
        arms["admit"].add(admit_ms)
        arms["charge"].add(charge_ms)
    return arms


def _cleanup(user_id: str) -> int:
    """Deletes the bench's own counter row.

    Raw, because `usage_daily` has no public delete. Scoped to the
    nonce-suffixed bench id, so no one else's row can match. Left behind, the
    row would show up in the admin console's Usage table.
    """
    with database.get_connection() as conn:
        return conn.execute(
            "DELETE FROM usage_daily WHERE user_id = ?", (user_id,)
        ).rowcount


def _first_words(statements: Sequence[str]) -> str:
    return ", ".join(" ".join(s.split()[:3]) for s in statements) or "(none)"


def _report(
    arms: dict[str, Samples],
    runs: int,
    endpoint: str,
    admit_statements: Sequence[str],
    charge_statements: Sequence[str],
) -> str:
    lines = [
        "",
        "--- PRD-013 STORY-017 usage-limit latency ---",
        f"  endpoint     : {endpoint}",
        f"  host         : {platform.node()} ({platform.system()} {platform.release()})",
        f"  python       : {platform.python_version()}",
        f"  runs         : {runs} timed per call, after 1 discarded warm-up pair",
        f"  variant      : {_VARIANT}",
        f"  admit SQL    : {len(admit_statements)} statement ({_first_words(admit_statements)})",
        f"  charge SQL   : {len(charge_statements)} statement ({_first_words(charge_statements)})",
        "",
        "  p50 is the median; p95 is nearest-rank, sorted[ceil(0.95*n)-1].",
        "  No latency here is asserted as a pass/fail bound.",
        "",
        f"  {'call':<8} {'n':>4} {'min ms':>9} {'p50 ms':>9} {'p95 ms':>9}",
    ]
    for name in ("admit", "charge"):
        low, p50, p95 = arms[name].summary()
        lines.append(f"  {name:<8} {arms[name].n:>4} {low:>9.2f} {p50:>9.2f} {p95:>9.2f}")

    _, admit_p50, admit_p95 = arms["admit"].summary()
    _, charge_p50, charge_p95 = arms["charge"].summary()
    lines.extend(
        [
            "",
            f"  added per request (p50, admit + charge) : {admit_p50 + charge_p50:.2f} ms",
            f"  added per request (p95, admit + charge) : {admit_p95 + charge_p95:.2f} ms",
            "  added round trips per request           : 2 (3 -> 5 statements)",
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

    database.init_db()  # converges usage_daily; a no-op on a current schema
    user_id = f"{args.user_id}-{uuid.uuid4().hex[:8]}"
    identity = _bench_identity(user_id)
    try:
        arms = _measure(identity, args.runs)
        admit_statements, charge_statements = _statement_check(identity)
        if len(admit_statements) != 1 or len(charge_statements) != 1:
            print(
                "Expected one statement per call (Path A); observed "
                f"admit={admit_statements} charge={charge_statements}. The "
                "variant changed, so these numbers would not mean what the "
                "report says.",
                file=sys.stderr,
            )
            return 1
        print(_report(arms, args.runs, _ENDPOINT, admit_statements, charge_statements))
    except NotAdmitted as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        if args.keep:
            print(f"  kept usage_daily row for {user_id} (--keep)")
        else:
            print(f"  cleaned up usage_daily for {user_id}: {_cleanup(user_id)} row(s)")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Measure p50/p95 of usage_limits.admit and usage_limits.charge "
            "(PRD-013 STORY-017). Records numbers; asserts none."
        )
    )
    parser.add_argument(
        "--runs", type=int, default=50, help="timed runs per call (default 50)"
    )
    parser.add_argument(
        "--database-url",
        default=_ENDPOINT,
        help=(
            "libSQL endpoint to measure against; read before argparse runs "
            "(default: $HARNESS_TEST_LIBSQL_URL or " + _DEFAULT_ENDPOINT + ")"
        ),
    )
    parser.add_argument(
        "--user-id",
        default="story017-bench",
        help="bench user id prefix; a per-run nonce is appended (default story017-bench)",
    )
    parser.add_argument(
        "--keep", action="store_true", help="leave the bench usage_daily row behind"
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
