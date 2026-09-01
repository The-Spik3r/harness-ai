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

import sqlite3
from pathlib import Path
from typing import Callable

import pytest

from app.config import settings
from app.db.database import init_db

# The only `sqlite:///` literal in tests/. STORY-006 replaces these two helpers
# with the libSQL endpoint equivalents; nothing else in this directory knows the
# scheme exists.
_SQLITE_PREFIX = "sqlite:///"


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
