"""The one place a test database is provisioned, and the one place a URL is spelled.

**This file is the seam.** PRD-007 replaces the local SQLite file with a remote
libSQL endpoint; STORY-006 changes the two private helpers below and nothing
else in `tests/`. Before this file existed the idiom
`monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{tmp_path}/test.db")`
was copy-pasted across 29 sites in 19 files, and the swap would have meant
editing all 19 while the suite was red.

**Why every fixture returns a `str` URL and never a `Path`.** A `Path` return
would bake "the database is a file" into all 19 consumers, which is precisely
the assumption the migration removes -- a libSQL endpoint has no path to join,
no parent directory, and no `.exists()`. The two tests that genuinely need a
connection rather than a URL (the pre-migration schema builders in
`test_db.py`) get one from `db_connect`, so the URL-to-connection translation
also stays here rather than spreading.

Isolation is per-test and comes from `tmp_path` / `tmp_path_factory`: every
fixture below hands out a database no other test can reach, which is what lets
`STORY-006` promise the same property against a shared libSQL server rather
than having to establish it.
"""

import os
import sqlite3
from pathlib import Path
from typing import Callable

import pytest

# The endpoint an unpatched `Settings()` validates against. Nothing connects to
# it: it is the local dev-server URL from STORY-001's decision record, chosen
# because it is the one value that satisfies STORY-005's validator without a
# token.
_PLACEHOLDER_URL = "http://127.0.0.1:8080"

# STORY-005 removed DATABASE_URL's default, and `app/config.py` constructs
# Settings() at import -- so a value has to exist before the `from app.config`
# line below, or collection fails for every test module. CI supplies no `.env`;
# these three `setdefault`s are the only reason the suite has an environment at
# all. (The two secrets were copy-pasted into 21 test-module prologues for the
# same reason; those still work, and this makes the requirement legible in one
# place.)
#
# This is a *placeholder that satisfies validation*, not a database any test
# reads: every fixture below repoints `settings.DATABASE_URL` through
# `monkeypatch`, which assigns to a constructed instance and so does not re-run
# validators. That is what lets the fixtures keep minting `sqlite:///` URLs
# after STORY-005 made that scheme a startup error, until STORY-006 swaps them
# for real libSQL endpoints.
os.environ.setdefault("DATABASE_URL", _PLACEHOLDER_URL)
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

from app.config import settings  # noqa: E402  -- must follow the bootstrap above
from app.db.database import init_db  # noqa: E402

# The only `sqlite:///` literal in tests/. STORY-006 replaces these two helpers
# with the libSQL endpoint equivalents; nothing else in this directory knows the
# scheme exists.
_SQLITE_PREFIX = "sqlite:///"

#: Environment variable the child probes carry their real (still SQLite)
#: database URL in. A subprocess constructs its own `Settings()`, where
#: `monkeypatch` cannot reach and STORY-005's validator *does* fire -- so
#: `DATABASE_URL` must carry something that validates, and the throwaway URL
#: travels beside it. The preamble below then assigns it onto the constructed
#: settings: the subprocess equivalent of what every in-process fixture does.
#: STORY-006 deletes both this constant and the preamble, because once the
#: fixtures mint libSQL endpoints, `DATABASE_URL` carries them directly again.
TEST_DATABASE_URL_ENV = "HARNESS_TEST_DATABASE_URL"

CHILD_SETTINGS_PREAMBLE = f"""
import os as _os
from app.config import settings as _settings
_settings.DATABASE_URL = _os.environ["{TEST_DATABASE_URL_ENV}"]
"""


def child_db_env(url: str) -> dict:
    """The two DATABASE_URL entries a probe subprocess needs.

    A plain function rather than a fixture: the three call sites are a mix of
    function- and module-scoped fixtures, and a helper sidesteps the
    `ScopeMismatch` that `database_url_factory` below already exists to dodge.
    """
    return {"DATABASE_URL": _PLACEHOLDER_URL, TEST_DATABASE_URL_ENV: url}


def _url_for(directory: Path, name: str) -> str:
    """A DATABASE_URL naming a database inside `directory`, created on first use."""
    return f"{_SQLITE_PREFIX}{directory / name}"


def _path_from_url(url: str) -> str:
    """The filesystem path a `sqlite:///` URL names.

    Deliberately not `app.db.database._db_path()`: coupling the test seam to a
    private production helper that STORY-006 deletes would make the swap harder,
    not easier.
    """
    if not url.startswith(_SQLITE_PREFIX):
        raise ValueError(f"not a sqlite URL: {url}")
    return url[len(_SQLITE_PREFIX):]


@pytest.fixture(autouse=True)
def _never_the_configured_database(tmp_path, monkeypatch) -> None:
    """Every test points at an isolated database, whether it asked for one or not.

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

    Explicit fixtures still win: `database_url` below patches the same setting
    afterwards, and pytest instantiates autouse fixtures first.
    """
    monkeypatch.setattr(settings, "DATABASE_URL", _url_for(tmp_path, "unrequested.db"))


@pytest.fixture
def database_url(tmp_path, monkeypatch) -> str:
    """An isolated, empty database with `settings.DATABASE_URL` patched at it.

    No schema: `init_db()` has not run. Use `temp_db` for an initialized one.
    """
    url = _url_for(tmp_path, "test.db")
    monkeypatch.setattr(settings, "DATABASE_URL", url)
    return url


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
def database_url_factory(tmp_path_factory) -> Callable[[str], str]:
    """Session-scoped URL minting for tests that hand the URL to a subprocess.

    Two reasons this exists alongside `database_url` rather than being folded
    into it. The probe fixtures in `test_admin_shell.py` and
    `test_render_invariants.py` are module-scoped, and a module-scoped fixture
    requesting a function-scoped one is a `ScopeMismatch`. And these callers
    pass the URL through the *child's* environment, so patching this process's
    `settings` would be a lie about what the fixture does.

    `name` distinguishes call sites; `mktemp` makes each call unique.
    """

    def make(name: str) -> str:
        return _url_for(tmp_path_factory.mktemp(name), "test.db")

    return make


@pytest.fixture
def db_connect() -> Callable[[str], sqlite3.Connection]:
    """Opens a raw connection to a database named by URL.

    For the handful of tests that build a *pre-migration* schema by hand and so
    need a connection rather than the URL -- deliberately raw, because the
    point of those tests is a table shape `init_db()` would not produce.
    """

    def connect(url: str) -> sqlite3.Connection:
        return sqlite3.connect(_path_from_url(url))

    return connect
