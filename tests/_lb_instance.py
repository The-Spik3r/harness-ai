"""One harness instance for the balancer tests (PRD-019 STORY-007). A test tool.

**Nothing under `app/` imports this file**, and nothing shipped depends on it.
`python tests/_lb_instance.py --port N` serves the real `app.main.app` with
uvicorn, plus two additions a test needs and the application must never carry:

* a pure-ASGI middleware counting the requests this process served, per path,
  so a test can say which instance a balanced request reached (AC2, AC3);
* `/__test__/*` routes: read and reset the counters, re-create the schema
  (conftest drops every table before each `db` test; the child's client stays
  valid, PRD-019 STORY-007 plan), and open or close the storage breaker.

`breaker/open` installs a breaker whose clock is frozen. `Retry-After` is
`ceil(open_until - now)` (`app/services/circuit_breaker.py:150`), so with a
real clock it could differ by one second between the direct call and the
balanced call; frozen, both read exactly 10 (the shipped open window).
"""

import argparse
import collections
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import uvicorn  # noqa: E402
from fastapi import APIRouter  # noqa: E402

import app.db.database as database  # noqa: E402
from app.main import app  # noqa: E402

_TEST_PREFIX = "/__test__/"

counts: "collections.Counter[str]" = collections.Counter()


class _CountRequests:
    """Counts every HTTP request outside `/__test__/`, then delegates untouched.

    The event loop is single-threaded, so the Counter needs no lock.
    """

    def __init__(self, inner):
        self._inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and not scope["path"].startswith(_TEST_PREFIX):
            counts[scope["path"]] += 1
        await self._inner(scope, receive, send)


router = APIRouter(prefix="/__test__")


@router.get("/counters")
def get_counters() -> dict:
    return dict(counts)


@router.post("/reset-counters")
def reset_counters() -> dict:
    counts.clear()
    return {"ok": True}


@router.post("/init-db")
def init_db() -> dict:
    database.init_db()
    return {"ok": True}


@router.post("/breaker/open")
def breaker_open() -> dict:
    database._storage_breaker = database.CircuitBreaker(
        "storage",
        database._BREAKER_FAILURE_THRESHOLD,
        database._BREAKER_OPEN_SECONDS,
        clock=lambda: 0.0,
        probe=database._probe_fresh_client,
        on_transition=database._count_breaker_open,
    )
    database._storage_breaker.force_open(database._BREAKER_OPEN_SECONDS)
    return {"ok": True}


@router.post("/breaker/reset")
def breaker_reset() -> dict:
    database._storage_breaker = database._new_storage_breaker()
    return {"ok": True}


app.include_router(router)
app.add_middleware(_CountRequests)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
