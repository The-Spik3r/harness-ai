"""The one place a test database is provisioned, and the one place a URL is spelled.

**This file is the seam.** PRD-007 replaced the local SQLite file with a remote
libSQL endpoint; STORY-006 changed this file's private helpers and left the 19
consumers alone. Before it existed the idiom
`monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{tmp_path}/test.db")`
was copy-pasted across 29 sites in 19 files, and the swap would have meant
editing all 19 while the suite was red.

**Why every fixture returns a `str` URL and never a `Path`.** A `Path` return
would have baked "the database is a file" into all 19 consumers, which is
precisely the assumption the migration removed -- a libSQL endpoint has no path
to join, no parent directory, and no `.exists()`. The two tests that genuinely
need a connection rather than a URL (the pre-migration schema builders in
`test_db.py`) get one from `db_connect`, so the URL-to-connection translation
also stays here rather than spreading.

**Where isolation comes from now.** It used to come from `tmp_path`: a distinct
file per test. One libSQL server serves one database, so isolation is now a
**reset** rather than a fresh name -- `_reset_database()` drops every table and
index before each test, from an autouse fixture, so every test starts empty
whether it asked for a database or not. The promise the old docstring made is
unchanged; only the mechanism behind it moved. What did not survive is distinct
URLs per test: see `database_url_factory`.

Running these tests needs the local libSQL dev server from STORY-001's decision
record. It is offline, takes no token, and cannot reach production:

    docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary \\
      ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67

Point the suite somewhere else with `HARNESS_TEST_LIBSQL_URL`.
"""

import os
from typing import Callable

import pytest

#: The libSQL endpoint every test runs against. `http://` is the local dev
#: server, which `app/config.py` accepts without a token (STORY-005).
_ENDPOINT = os.environ.get("HARNESS_TEST_LIBSQL_URL", "http://127.0.0.1:8080")

# STORY-005 removed DATABASE_URL's default, and `app/config.py` constructs
# Settings() at import -- so a value has to exist before the `from app.config`
# line below, or collection fails for every test module. CI supplies no `.env`;
# these three `setdefault`s are the only reason the suite has an environment at
# all. (The two secrets were copy-pasted into 21 test-module prologues for the
# same reason; those still work, and this makes the requirement legible in one
# place.)
#
# Unlike the placeholder this used to be, the value is now the endpoint the
# tests genuinely use -- which is what let STORY-006 delete the second
# environment variable the subprocess probes needed to carry the real URL in.
os.environ.setdefault("DATABASE_URL", _ENDPOINT)
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import libsql  # noqa: E402  -- after the bootstrap, for symmetry with the rest

from app.config import settings  # noqa: E402  -- must follow the bootstrap above
from app.db.database import get_connection, init_db  # noqa: E402


def child_db_env(url: str) -> dict:
    """The `DATABASE_URL` entry a probe subprocess needs.

    A plain function rather than a fixture: the three call sites are a mix of
    function- and module-scoped fixtures, and a helper sidesteps the
    `ScopeMismatch` that `database_url_factory` below already exists to dodge.

    It used to return two variables. A child constructs its own `Settings()`,
    where `monkeypatch` cannot reach and STORY-005's validator *does* fire, so
    while the fixtures still minted `sqlite:///` URLs the real one had to travel
    beside a second value that validated. Now that the fixtures hand out a real
    endpoint, `DATABASE_URL` carries it directly and the workaround is gone.
    """
    return {"DATABASE_URL": url}


def _reset_database() -> None:
    """Drops every table and index, leaving an empty database.

    Indexes first: dropping a table takes its indexes with it, and asking for a
    dropped index by name afterwards is an error.

    **Through `app.db.database`'s own connection, deliberately, and not a second
    client of its own.** A fixture that opened its own client would be the one
    pattern STORY-006 measured and found dangerous: two independent clients
    writing to one libSQL database contend for its single writer, and the loser
    gets `TRANSACTION_TIMEOUT` after the driver's five-second default rather
    than waiting its turn. One client per process is the property that makes
    both the application and this suite predictable, so the fixtures hold to it
    too. The coupling costs nothing here -- these are `DROP` statements, and
    nothing about them depends on the module under test behaving correctly.
    """
    with get_connection() as conn:
        objects = conn.execute(
            "SELECT name, type FROM sqlite_master "
            "WHERE type IN ('table', 'index') AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        for name, kind in sorted(objects, key=lambda row: row[1], reverse=True):
            conn.execute(f'DROP {kind.upper()} IF EXISTS "{name}"')


@pytest.fixture(scope="session", autouse=True)
def _libsql_endpoint() -> str:
    """Proves the endpoint is reachable once, and says how to start it if not.

    A hard failure rather than a skip: a suite that quietly stops exercising
    storage still reports green, which is worse than a red one.
    """
    try:
        libsql.connect(_ENDPOINT).execute("SELECT 1").fetchone()
    except Exception as exc:  # noqa: BLE001 -- any failure means "no database"
        pytest.exit(
            f"The libSQL dev server at {_ENDPOINT} is unreachable ({exc}).\n"
            "Start it with:\n"
            "  docker run -d --name harness-libsql-dev -p 8080:8080 "
            "-e SQLD_NODE=primary \\\n"
            "    ghcr.io/tursodatabase/libsql-server@sha256:"
            "6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67\n"
            "or point HARNESS_TEST_LIBSQL_URL at another one.",
            returncode=1,
        )
    return _ENDPOINT


@pytest.fixture(autouse=True)
def _never_the_configured_database(_libsql_endpoint, monkeypatch) -> None:
    """Every test starts on an empty database, whether it asked for one or not.

    Until STORY-005, `DATABASE_URL` defaulted to `sqlite:///harness_ai.db`, so a
    test that reached storage without requesting a fixture quietly opened the
    repo-root database -- the very file PRD-007 deletes -- and passed on what it
    found there. Six tests were doing exactly that, in `tests/test_main.py` and
    `tests/test_admin_auth.py`, and two of them said so in a comment ("the real
    dev DATABASE_URL these tests run against"). Once the placeholder endpoint
    replaced that default they began to fail, which is the honest signal: the
    dependency was always there and was never declared.

    Fixing it here rather than in those files is deliberate. `test_admin_auth.py`
    is one of the suites PRD-006 pinned byte-for-byte (`test_untouched_app.py`,
    `test_pii_redaction_integration.py`), so the isolation it needs cannot be
    written into it. This fixture is also the stronger statement: the promise in
    this module's docstring -- that no test can reach another test's rows, or
    anyone's real database -- now holds for every test, not only for the ones
    that remember to ask.

    Since STORY-006 it carries the isolation itself. One endpoint serves one
    database, so "an isolated database" means "a database nothing else has left
    anything in", and the reset is what makes that true. Explicit fixtures still
    win: `database_url` below patches the same setting afterwards, and pytest
    instantiates autouse fixtures first.
    """
    monkeypatch.setattr(settings, "DATABASE_URL", _libsql_endpoint)
    _reset_database()


@pytest.fixture
def database_url(_libsql_endpoint, monkeypatch) -> str:
    """An isolated, empty database with `settings.DATABASE_URL` patched at it.

    No schema: `init_db()` has not run. Use `temp_db` for an initialized one.
    """
    monkeypatch.setattr(settings, "DATABASE_URL", _libsql_endpoint)
    return _libsql_endpoint


@pytest.fixture
def temp_db(database_url) -> str:
    """An isolated database with the current schema created.

    Named `temp_db` because that is what ~400 test signatures already spell; a
    module may override it to add seeding and still request this one by name.
    """
    init_db()
    return database_url


@pytest.fixture
def uninitialized_db(database_url) -> str:
    """A database `init_db()` never ran against, so no table exists at all.

    Serves the STORY-002 characterization tests, which pin what the storage
    layer does when the `users` table is absent -- a condition that has to be
    reachable without a test hand-rolling its own connection.
    """
    return database_url


@pytest.fixture(scope="session")
def database_url_factory(_libsql_endpoint) -> Callable[[str], str]:
    """Session-scoped URL minting for tests that hand the URL to a subprocess.

    Two reasons this exists alongside `database_url` rather than being folded
    into it. The probe fixtures in `test_admin_shell.py` and
    `test_render_invariants.py` are module-scoped, and a module-scoped fixture
    requesting a function-scoped one is a `ScopeMismatch`. And these callers
    pass the URL through the *child's* environment, so patching this process's
    `settings` would be a lie about what the fixture does.

    **It no longer mints a distinct URL per call, and cannot.** One libSQL server
    serves one database; distinct URLs would mean a namespace per probe, which
    the client addresses by hostname (`<ns>.localhost`) and which does not
    resolve inside a container -- a suite that passes on one machine and fails on
    another. What replaces the guarantee: every probe is created inside a test,
    after `_never_the_configured_database` has emptied the database, so each one
    still starts from nothing. `name` is kept because it documents the call site.
    """

    def make(name: str) -> str:
        return _libsql_endpoint

    return make


@pytest.fixture
def db_connect() -> Callable[[str], object]:
    """Opens a connection to the database named by URL, for raw DDL.

    For the handful of tests that build a *pre-migration* schema by hand and so
    need a connection rather than the URL. "Raw" means the SQL is theirs and
    `init_db()` never ran -- the point of those tests is a table shape
    `init_db()` would not produce -- not that the connection bypasses the
    module: it comes from `get_connection()` for the same one-client-per-process
    reason `_reset_database()` does.
    """

    def connect(url: str):
        return get_connection()

    return connect
