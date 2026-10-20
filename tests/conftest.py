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
index before each `db` test, from the autouse `_storage_policy`. Since PRD-014 a
test that is not `db` cannot reach storage at all, so it has nothing to start
empty. The promise the old docstring made is
unchanged; only the mechanism behind it moved. What did not survive is distinct
URLs per test: see `database_url_factory`.

Running these tests needs the local libSQL dev server from STORY-001's decision
record. It is offline, takes no token, and cannot reach production:

    docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary \\
      ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67

Point the suite somewhere else with `HARNESS_TEST_LIBSQL_URL`.
"""

import os
import traceback
from pathlib import Path
from typing import Callable, NoReturn, Optional

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
from app.db import database  # noqa: E402
from app.db.database import get_connection, init_db  # noqa: E402
from app.services import pattern_config  # noqa: E402
from app.services import pii_policy  # noqa: E402


#: The marker on latency-budget assertions (PRD-012 STORY-013).
_BENCHMARK_MARKER = "benchmark"

#: The marker on tests that reach storage (PRD-014 STORY-002), applied at collection.
_DB_MARKER = "db"

#: Requesting any of these, directly or through another fixture, makes a test a `db` test.
#: `item.fixturenames` is the transitive closure, so a module-local fixture built on
#: `temp_db` marks its tests too. `db_connect` opens a raw connection, so it counts.
_STORAGE_FIXTURES = frozenset(
    {"temp_db", "database_url", "uninitialized_db", "database_url_factory", "db_connect"}
)

#: Tests that reach storage without one of the fixtures above, and whose files must not be
#: edited (PRD-006's six suites) or reach it through a path no fixture names (app lifespan,
#: an in-process script, `request.getfixturevalue`). Seeded from STORY-001's measured list
#: of tests with driver calls and no storage fixture.
#:
#: An entry without `::` is a module path and matches every test in that module. Any
#: other entry is a nodeid and matches itself, its parametrized ids (`entry[...]`) and,
#: for a class, its methods (`entry::...`) -- never a longer name it merely prefixes.
_DB_NODEIDS: tuple[str, ...] = (
    # PRD-006: `require_admin_token` -> `identity.resolve()` -> `find_user_by_token_hash()`.
    "tests/test_admin_auth.py::test_incorrect_bearer_token_rejected",
    # PRD-006: `init_db()` against a dead port; the driver call is the test's subject.
    "tests/test_db.py::test_init_db_fails_fast_against_an_unreachable_endpoint",
    # The same, through `TestClient(app)`'s lifespan.
    "tests/test_main.py::test_lifespan_fails_when_the_database_is_unreachable",
    # In-process `bench.main()`: `init_db()`, `admit`/`charge` and a cleanup.
    "tests/test_measure_usage_latency.py::test_a_short_run_reports_both_calls_and_cleans_up",
    "tests/test_measure_usage_latency.py::test_a_refused_admit_ends_the_run_without_a_report",
    "tests/test_measure_usage_latency.py::test_a_changed_statement_count_ends_the_run_without_a_report",
)


def _in_db_nodeids(nodeid: str, entries: tuple[str, ...] = _DB_NODEIDS) -> bool:
    """Whether `nodeid` is declared by `entries`, under the rule `_DB_NODEIDS` states."""
    for entry in entries:
        if "::" not in entry:
            if nodeid.split("::", 1)[0] == entry:
                return True
        elif nodeid == entry or nodeid.startswith((entry + "[", entry + "::")):
            return True
    return False


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--run-benchmark",
        action="store_true",
        default=False,
        help="run @pytest.mark.benchmark latency assertions (PRD-012 STORY-013)",
    )


def pytest_configure(config) -> None:
    config.addinivalue_line("markers", f"{_BENCHMARK_MARKER}: latency-budget assertion; skipped unless --run-benchmark")
    config.addinivalue_line("markers", f"{_DB_MARKER}: reaches storage (a storage fixture, or listed in _DB_NODEIDS); applied at collection")


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items) -> None:
    """Mark `db` tests, then skip `@pytest.mark.benchmark` tests unless `--run-benchmark` is given.

    A test is `db` when its fixture closure meets `_STORAGE_FIXTURES` or its
    nodeid is in `_DB_NODEIDS` (PRD-014 STORY-002), so `-m db` / `-m "not db"`
    select by what a test reaches rather than by what its file says. No test
    file names the marker, though `@pytest.mark.db` written in one works too.
    Marking comes before the benchmark check so `--run-benchmark` cannot change
    which tests are `db`, and `tryfirst` because `-m` is applied by pytest's own
    `pytest_collection_modifyitems`: this one has to have marked before that one
    deselects. Without it the order rests on plugin registration alone.

    A marker alone skips nothing, and `-m` only narrows a run someone already
    chose to make. STORY-013's note is that the budget assertion must not run
    by default, "so the everyday run stays fast": it times twenty 200,000-
    character conversations. STORY-013 and STORY-014 run it explicitly:

        pytest tests/test_pii_code_corpus.py -m benchmark --run-benchmark -s
    """
    db = getattr(pytest.mark, _DB_MARKER)
    for item in items:
        if _STORAGE_FIXTURES.intersection(getattr(item, "fixturenames", ())) or _in_db_nodeids(item.nodeid):
            item.add_marker(db)
    if config.getoption("--run-benchmark"):
        return
    skip = pytest.mark.skip(reason=f"{_BENCHMARK_MARKER}: pass --run-benchmark")
    for item in items:
        if _BENCHMARK_MARKER in item.keywords:
            item.add_marker(skip)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    """Notes when the storage guard's own exception failed setup or call.

    `_storage_policy` fails a test at teardown when its guard recorded an
    access, which catches an access something swallowed. When nothing did, the
    raised exception has already failed the test, and a second report from
    teardown would turn one undeclared test into "1 failed, 1 error". STORY-005
    adds the `libsql diagnostics` section to this hook.
    """
    report = yield
    if (
        report.when in ("setup", "call")
        and report.failed
        and call.excinfo is not None
        and call.excinfo.errisinstance(pytest.fail.Exception)
        and str(call.excinfo.value).startswith(f"{item.nodeid} reached storage")
    ):
        item.stash[_REFUSED] = True
    return report


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

    **One retry on a dead stream, and only on that.** The shared client's idle
    probe (PRD-008 STORY-024) is a floor, not a guarantee: the app's own design
    accepts that a stream can die between probe and statement, and recovers by
    dropping the client so the *next* call rebuilds it. This fixture is the first
    statement of every test, so without that second call the loss landed as a
    setup ERROR on whichever unrelated test came next -- seen on
    `test_summary.py` and `test_manage_users_cli.py` in full runs, as
    `STREAM_EXPIRED`, never in isolation. Replaying is safe because every
    statement here is idempotent (`DROP ... IF EXISTS`). Any other failure, and a
    second dead stream in a row, still fails the test: a genuinely unreachable
    server must stay loud.
    """
    try:
        _drop_every_table_and_index()
    except ValueError as exc:
        # __exit__'s rollback on a dead client may raise in turn; the expiry is
        # then the context of what reaches us, not its message.
        messages = (str(exc), str(exc.__context__ or ""))
        if not any(database._is_dead_stream(message) for message in messages):
            raise
        database._invalidate_client()
        _drop_every_table_and_index()


def _drop_every_table_and_index() -> None:
    with get_connection() as conn:
        objects = conn.execute(
            "SELECT name, type FROM sqlite_master "
            "WHERE type IN ('table', 'index') AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        for name, kind in sorted(objects, key=lambda row: row[1], reverse=True):
            conn.execute(f'DROP {kind.upper()} IF EXISTS "{name}"')


#: What a test that is not `db` is told when it reaches storage (PRD-014 Section 10).
#: The teardown check and `pytest_runtest_makereport` recognise it by its first words.
_UNDECLARED = (
    "{nodeid} reached storage ({where}) without declaring it.\n"
    "Request temp_db (or database_url / uninitialized_db / database_url_factory / db_connect),\n"
    "add @pytest.mark.db, or -- for a suite that must not be edited -- add its nodeid to\n"
    "_DB_NODEIDS in tests/conftest.py."
)

#: The repository root, from the application package rather than pytest's rootdir, so
#: frames resolve the same in a `pytester` child whose rootdir is a temp directory.
_REPO = Path(database.__file__).resolve().parents[2]

#: Where "the first app frame" may live.
_APP_ROOTS = (_REPO / "app", _REPO / "chat_ui")

_HERE = Path(__file__).resolve()


def _where(path: Path, name: str) -> str:
    try:
        shown = path.relative_to(_REPO).as_posix()
    except ValueError:
        shown = path.as_posix()
    return f"{shown}:{name}"


def _first_app_frame(test_path: Optional[Path] = None) -> str:
    """The innermost frame of application code on the current stack, e.g.
    `app/db/database.py:get_connection`.

    Failing that -- a test that calls `libsql.connect` itself -- the innermost
    frame in the test's own file, and failing that the innermost frame outside
    this one, so the message always names somewhere to look.
    """
    frames = [(Path(frame.filename).resolve(), frame.name) for frame in reversed(traceback.extract_stack())]
    for path, name in frames:
        if any(path.is_relative_to(root) for root in _APP_ROOTS):
            return _where(path, name)
    if test_path is not None:
        target = Path(test_path).resolve()
        for path, name in frames:
            if path == target:
                return _where(path, name)
    for path, name in frames:
        if path != _HERE:
            return _where(path, name)
    return "unknown"


def _refuse(item, sink: list[str]) -> Callable[..., NoReturn]:
    """What `database._shared_client` and `libsql.connect` become in a test that is not `db`.

    **`pytest.fail`, which raises a `BaseException`.** Routers and services turn
    `Exception` into status codes (`StorageError` into a `503`, for one), so an
    `Exception` would be swallowed and the test could pass on the error page.
    `pytest.fail.Exception` gets past every `except Exception`.

    **The sink is the backstop for what does catch it** -- an `except
    BaseException`, a worker thread from `asyncio.to_thread`, a background task:
    `_storage_policy` fails the test at teardown when anything was recorded.

    **Not "point the test at an unreachable URL".** On Windows a refused localhost
    connect costs about two seconds of SYN retries per test, and it reads as a
    network error -- the very ambiguity PRD-014 exists to remove. This refuses
    before any socket is opened.
    """

    def refused(*args, **kwargs) -> NoReturn:
        where = _first_app_frame(getattr(item, "path", None))
        sink.append(where)
        pytest.fail(_UNDECLARED.format(nodeid=item.nodeid, where=where), pytrace=False)

    return refused


@pytest.fixture(scope="session")
def _libsql_endpoint() -> str:
    """Proves the endpoint is reachable once, and says how to start it if not.

    A hard failure rather than a skip: a suite that quietly stops exercising
    storage still reports green, which is worse than a red one.

    **Since PRD-014 STORY-004 it is not autouse.** Only `_storage_policy`'s `db`
    branch and the storage fixtures (`database_url`, `database_url_factory`)
    instantiate it, so a `-m "not db"` session never probes and runs with
    Docker stopped. The price is where a full run with Docker stopped ends: at
    the *first `db` test*, not before the first test. The tests that ran before
    it have already reported and the rest never run, so it is still a hard
    exit, and it still names the fix.
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


#: Set on an item whose setup or call already failed through the guard, so the
#: teardown check does not report the same access a second time.
_REFUSED = pytest.StashKey[bool]()


@pytest.fixture(autouse=True)
def _storage_policy(request, monkeypatch):
    """A `db` test starts on an empty database; any other test cannot reach one.

    Until PRD-014 STORY-003 this fixture was `_never_the_configured_database`,
    and it reset the database before every test, whether it asked for one or
    not. The history that shaped it still holds:

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

    **Since PRD-014 STORY-003 only `db` tests are reset** (the marker from
    `pytest_collection_modifyitems`), and every other test is refused storage
    outright. Two thirds of the suite never needed a database, yet each paid a
    reset and each was exposed to the libSQL stalls that made full runs red at
    random. A test that is not `db` gets `DATABASE_URL` set to the endpoint --
    code that only *reads* the setting behaves as before -- and two patch points
    replaced by `_refuse()`: `database._shared_client`, which every
    `get_connection()` goes through and which also stops a client cached by an
    earlier `db` test from being lent, and `libsql.connect`, which catches direct
    construction. Isolation still holds without the reset: a test that cannot
    reach storage can neither see rows nor leave them. Declared first among the
    function-scoped autouse fixtures, so nothing it guards runs before it.

    The guard rides on the test's own `monkeypatch`, so a test that patches
    either point itself is restored in the right order. The one way round it is
    `monkeypatch.undo()` in a test that is not `db`; the seven calls in
    `tests/test_db.py` are all in `db` tests.
    """
    item = request.node
    if item.get_closest_marker(_DB_MARKER) is not None:
        monkeypatch.setattr(settings, "DATABASE_URL", request.getfixturevalue("_libsql_endpoint"))
        _reset_database()
        yield
        return
    monkeypatch.setattr(settings, "DATABASE_URL", _ENDPOINT)
    sink: list[str] = []
    refused = _refuse(item, sink)
    monkeypatch.setattr(database, "_shared_client", refused)
    monkeypatch.setattr(libsql, "connect", refused)
    yield
    if sink and not item.stash.get(_REFUSED, False):
        pytest.fail(_UNDECLARED.format(nodeid=item.nodeid, where=sink[0]), pytrace=False)


@pytest.fixture(autouse=True)
def _default_pattern_policy(monkeypatch):
    """Every test starts under the default pattern configuration (PRD-011 STORY-013).

    The default -- `PATTERNS_FILE` empty, `PATTERN_PROFILE_DEFAULT=chat`, the
    built-in policy in force -- is what an existing deployment gets after
    upgrading, so it is what every regression runs under unless a test opts out.
    Before this fixture the `/query` regression suites passed on it by luck:
    `Settings` reads `.env`, nothing reset either setting, and a developer's
    `PATTERN_PROFILE_DEFAULT=code` would have changed their verdicts. Pinning it
    here is the one way to reach those suites without editing them, which
    PRD-011 Section 11 forbids.

    A test that wants another policy patches the setting in its own fixture or
    body, which runs after this one, and may call `load()`: `_policy` is saved
    and restored directly rather than through `monkeypatch`, because `load()`
    rebinds it with a plain assignment and because `tests/test_db.py`'s
    `monkeypatch.undo()` must not be able to leave a test's policy behind.
    """
    monkeypatch.setattr(settings, "PATTERNS_FILE", "")
    monkeypatch.setattr(settings, "PATTERN_PROFILE_DEFAULT", "chat")
    original = pattern_config._policy
    yield
    pattern_config._policy = original


@pytest.fixture(autouse=True)
def _default_pii_policy():
    """Every test ends with the PII policies it started with (PRD-012 STORY-007).

    A test that patches a `PII_*` setting calls `pii_policy.load()` itself to
    see it. `_policies` is saved and restored directly, for the reason
    `_default_pattern_policy` gives: `load()` rebinds it with a plain
    assignment, which `monkeypatch` would not undo.
    """
    original = pii_policy._policies
    yield
    pii_policy._policies = original


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
    after `_storage_policy` has emptied the database, so each one
    still starts from nothing. `name` is kept because it documents the call site.
    (Requesting this fixture makes the test `db`, which is what gets it reset.)
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
