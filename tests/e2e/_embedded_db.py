"""PRD-023 STORY-020: a launcher that runs a child against an embedded libSQL file.

The MCP client E2E (`test_mcp_clients.py`) needs a database but not Docker. `Settings` refuses
a file URL (`app/config.py`), so the file cannot be passed as `DATABASE_URL`. This launcher stands
in for `python` in every child (the harness, `scripts/manage_users.py`, the row dump), so they
all open the same file:

    python tests/e2e/_embedded_db.py -m uvicorn app.main:app --port N      (module, as `python -m`)
    python tests/e2e/_embedded_db.py -c "<code>" [args]                    (code, as `python -c`)
    python tests/e2e/_embedded_db.py path/to/script.py [args]              (script, as `python path`)

The child env carries `DATABASE_URL=http://127.0.0.1:8080` (a placeholder, never connected to: it
only has to validate) and `HARNESS_E2E_DB_FILE=<absolute path of the file>`. The launcher imports
`app.config`, assigns the file to `settings.DATABASE_URL` before anything connects (the bootstrap
of `scripts/measure_mcp_latency.py`; `app/db/database.py` keys its client on that value at call
time) and then dispatches. Nothing in `app/` changes and authentication is never touched.

It refuses to run when `HARNESS_E2E_LIBSQL_URL` is set: that variable is the other, Docker, recipe
and the two must never be mixed in one run. Never imported by a test module of the everyday suite
except for `parse`, which is pure.
"""

import os
import runpy
import sys
from pathlib import Path

DB_FILE_ENV = "HARNESS_E2E_DB_FILE"
SERVER_ENV = "HARNESS_E2E_LIBSQL_URL"
USAGE = "usage: _embedded_db.py (-m MODULE | -c CODE | SCRIPT) [ARGS...]"


def parse(argv: list) -> tuple:
    """`(mode, target, rest)` for the arguments after the launcher's own name. Pure.

    `mode` is `module`, `code` or `script`; `rest` are the arguments the child sees as
    `sys.argv[1:]` (module, script) or after the `-c` entry (code).
    """
    if not argv:
        raise SystemExit(USAGE)
    head, *tail = argv
    if head in ("-m", "-c"):
        if not tail:
            raise SystemExit(f"{head} needs an argument. {USAGE}")
        return ("module" if head == "-m" else "code"), tail[0], tail[1:]
    if head.startswith("-"):
        raise SystemExit(f"unsupported option {head!r}. {USAGE}")
    return "script", head, tail


def db_file() -> str:
    """The absolute database path from `HARNESS_E2E_DB_FILE`, or `SystemExit` naming the variable."""
    if os.environ.get(SERVER_ENV, "").strip():
        raise SystemExit(f"{SERVER_ENV} is set: use the plain interpreter, not the embedded launcher")
    path = os.environ.get(DB_FILE_ENV, "").strip()
    if not path or not Path(path).is_absolute():
        raise SystemExit(f"{DB_FILE_ENV} must name an absolute path (got {path!r})")
    return path


def main(argv: list) -> None:
    mode, target, rest = parse(argv)
    path = db_file()
    from app.config import settings  # after the environment is complete: builds Settings()

    settings.DATABASE_URL = path
    if mode == "module":
        sys.argv = [target, *rest]
        runpy.run_module(target, run_name="__main__", alter_sys=True)
    elif mode == "code":
        sys.argv = ["-c", *rest]
        exec(compile(target, "<string>", "exec"), {"__name__": "__main__"})
    else:
        sys.argv = [target, *rest]
        runpy.run_path(target, run_name="__main__")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    main(sys.argv[1:])
