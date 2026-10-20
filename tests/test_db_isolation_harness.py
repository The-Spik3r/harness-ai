"""PRD-014's harness, asserted rather than assumed.

`tests/conftest.py` decides which tests are `db` tests (STORY-002), and later
stories key the reset, the guard and the diagnostics on that one decision. A
marker that silently stopped applying would not turn anything red: `-m db`
would just select fewer tests and `-m "not db"` would quietly reach storage.
So the rule is checked here, against the conftest's own constants. The guard
(STORY-003) is checked the same way, and so is the lazy endpoint (STORY-004).
The recorder adds its tests to this file when it lands.

The guard's tests never call the guard *installed* on themselves: its teardown
check would fail them. In-process they build their own `_refuse()`. The cases
that need a whole test to end -- a swallowed refusal, a worker thread, the
teardown check, `TestClient` -- run in a `pytester` child that loads a copy of
the real `tests/conftest.py`.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import textwrap
from pathlib import Path

import libsql
import pytest

from app.config import settings
from app.db import database
from app.db.database import get_connection
from tests.conftest import (
    _DB_NODEIDS,
    _ENDPOINT,
    _STORAGE_FIXTURES,
    _UNDECLARED,
    _first_app_frame,
    _in_db_nodeids,
    _refuse,
)

pytest_plugins = ("pytester",)

_REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def _through_temp_db(temp_db):
    return temp_db


# --- The marker, applied at collection ----------------------------------------


def test_a_fixture_built_on_temp_db_marks_its_test(_through_temp_db, request):
    """The test names no storage fixture itself. It is `db` only because
    `item.fixturenames` is the transitive closure, which is what lets a module
    wrap `temp_db` in its own seeding fixture without declaring anything."""
    assert request.node.get_closest_marker("db") is not None


def test_a_test_without_storage_is_not_marked(request):
    """If this fails, something marks every test, and `-m "not db"` selects
    nothing."""
    assert request.node.get_closest_marker("db") is None


def test_every_storage_fixture_is_a_conftest_fixture(request):
    """A rename in `conftest.py` that `_STORAGE_FIXTURES` did not follow would
    unmark every test using that fixture, and nothing else would notice."""
    manager = request.session._fixturemanager
    missing = [name for name in sorted(_STORAGE_FIXTURES) if not manager.getfixturedefs(name, request.node)]
    assert missing == []


def test_every_db_nodeids_entry_names_a_file_that_exists(request):
    """Same failure from the other side: a module renamed out from under its
    entry would silently stop being `db`."""
    missing = [
        entry for entry in _DB_NODEIDS if not (request.config.rootpath / entry.split("::", 1)[0]).is_file()
    ]
    assert missing == []


# --- How `_DB_NODEIDS` entries match --------------------------------------------


def test_a_module_path_matches_every_test_in_the_module():
    entries = ("tests/test_x.py",)
    assert _in_db_nodeids("tests/test_x.py::test_a", entries)
    assert _in_db_nodeids("tests/test_x.py::TestThing::test_b", entries)
    assert _in_db_nodeids("tests/test_x.py::test_c[1]", entries)


def test_a_module_path_does_not_match_a_module_it_prefixes():
    assert not _in_db_nodeids("tests/test_x_extra.py::test_a", ("tests/test_x.py",))


def test_a_nodeid_matches_itself():
    assert _in_db_nodeids("tests/test_x.py::test_a", ("tests/test_x.py::test_a",))


def test_a_nodeid_matches_its_parametrized_ids():
    entries = ("tests/test_x.py::test_a",)
    assert _in_db_nodeids("tests/test_x.py::test_a[/fake-audit]", entries)
    assert _in_db_nodeids("tests/test_x.py::test_a[1-2]", entries)


def test_a_class_nodeid_matches_its_methods():
    assert _in_db_nodeids("tests/test_x.py::TestThing::test_b", ("tests/test_x.py::TestThing",))


def test_a_nodeid_does_not_match_a_longer_name_it_prefixes():
    """A bare `startswith` would let an entry for `test_a` mark `test_ab`."""
    assert not _in_db_nodeids("tests/test_x.py::test_ab", ("tests/test_x.py::test_a",))


def test_a_nodeid_does_not_match_other_tests_in_its_module():
    assert not _in_db_nodeids("tests/test_x.py::test_b", ("tests/test_x.py::test_a",))


def test_no_entries_match_nothing():
    assert not _in_db_nodeids("tests/test_x.py::test_a", ())


# --- The reset, for db tests ------------------------------------------------------


@pytest.mark.db
def test_a_db_test_runs_on_the_endpoint_against_an_empty_database():
    """Written with the explicit marker, which is the other way to be `db`."""
    assert settings.DATABASE_URL == _ENDPOINT
    with get_connection() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    assert tables == []


# --- The guard, in-process ------------------------------------------------------


def test_a_test_that_is_not_db_has_both_patch_points_refused():
    """Looked at, never called: calling either would fail this test at teardown."""
    assert database._shared_client.__qualname__ == "_refuse.<locals>.refused"
    assert libsql.connect.__qualname__ == "_refuse.<locals>.refused"
    assert settings.DATABASE_URL == _ENDPOINT


def test_the_refusal_names_the_test_the_frame_and_every_way_to_declare(request):
    sink: list[str] = []
    refused = _refuse(request.node, sink)

    with pytest.raises(pytest.fail.Exception) as excinfo:
        refused()

    message = str(excinfo.value)
    assert message.startswith(f"{request.node.nodeid} reached storage (")
    for name in sorted(_STORAGE_FIXTURES):
        assert name in message, name
    assert "@pytest.mark.db" in message
    assert "_DB_NODEIDS" in message
    assert len(sink) == 1


def test_the_refusal_is_not_caught_by_except_exception(request):
    """Routers turn `Exception` into status codes; the refusal must get past them."""
    refused = _refuse(request.node, [])
    assert not issubclass(pytest.fail.Exception, Exception)

    with pytest.raises(pytest.fail.Exception):
        try:
            refused()
        except Exception:  # noqa: BLE001 -- the point of the test
            pytest.fail("an `except Exception` swallowed the refusal")


def test_the_first_app_frame_is_the_innermost_app_frame(request, monkeypatch):
    sink: list[str] = []
    monkeypatch.setattr(database, "_shared_client", _refuse(request.node, sink))

    with pytest.raises(pytest.fail.Exception, match=r"\(app/db/database\.py:get_connection\)"):
        database.get_connection()

    assert sink == ["app/db/database.py:get_connection"]


def test_without_an_app_frame_the_test_itself_is_named(request):
    """`libsql.connect` called straight from a test has no `app/` frame."""
    sink: list[str] = []
    with pytest.raises(pytest.fail.Exception):
        _refuse(request.node, sink)()

    assert sink == [
        "tests/test_db_isolation_harness.py:test_without_an_app_frame_the_test_itself_is_named"
    ]
    assert _first_app_frame(request.node.path) == sink[0]


def test_the_teardown_check_recognises_the_message_by_its_first_words():
    """`pytest_runtest_makereport` matches on this prefix to avoid a double report."""
    assert _UNDECLARED.startswith("{nodeid} reached storage")


# --- The guard, in a child run of the real conftest -----------------------------

#: Every guard child module starts here. Since STORY-004 a child with no `db`
#: test never runs the conftest's session probe anyway, so the `_libsql_endpoint`
#: override (closest definition wins) is belt-and-braces: it keeps a `db` arm,
#: should a guard child ever grow one, off the network. `HARNESS_TEST_LIBSQL_URL`
#: points at a dead port as well, so a connect that did happen would fail loudly
#: rather than reach the dev server.
_CHILD_PRELUDE = """
import asyncio
import time

import libsql
import pytest

from app.config import settings
from app.db import database
from app.db.database import get_connection


@pytest.fixture(scope="session")
def _libsql_endpoint():
    return "http://127.0.0.1:9"
"""

#: The lazy endpoint's children start here instead: no override, so the real
#: `_libsql_endpoint` decides whether the dead port is ever probed. On top of
#: `_CHILD_PRELUDE` these tests would pass with the fixture autouse again.
_LAZY_PRELUDE = """
import pytest

from app.config import settings
"""

_GET_CONNECTION_REFUSED = "test_child.py::test_it reached storage (app/db/database.py:get_connection)"


def _run_child(pytester, monkeypatch, body: str, prelude: str = _CHILD_PRELUDE):
    monkeypatch.setenv("PYTHONPATH", str(_REPO_ROOT))
    monkeypatch.setenv("HARNESS_TEST_LIBSQL_URL", "http://127.0.0.1:9")
    pytester.makeconftest((_REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8"))
    pytester.makepyfile(test_child=prelude + textwrap.dedent(body))
    return pytester.runpytest_subprocess("-p", "no:cacheprovider")


def _assert_no_network(output: str) -> None:
    for sign in ("10060", "actively refused", "Cannot reach", "DatabaseUnreachableError"):
        assert sign not in output, sign


def test_reaching_storage_undeclared_fails_once_with_the_whole_message(pytester, monkeypatch):
    result = _run_child(pytester, monkeypatch, """
        def test_it():
            get_connection()
    """)

    result.assert_outcomes(failed=1)  # and errors=0: teardown does not report it again
    output = result.stdout.str()
    assert _GET_CONNECTION_REFUSED in output
    for name in sorted(_STORAGE_FIXTURES):
        assert name in output, name
    assert "@pytest.mark.db" in output
    assert "_DB_NODEIDS" in output
    _assert_no_network(output)


def test_an_except_exception_in_the_test_does_not_swallow_the_refusal(pytester, monkeypatch):
    result = _run_child(pytester, monkeypatch, """
        def test_it():
            try:
                get_connection()
            except Exception:
                pass
    """)

    result.assert_outcomes(failed=1)
    assert _GET_CONNECTION_REFUSED in result.stdout.str()


def test_an_access_swallowed_by_except_baseexception_fails_at_teardown(pytester, monkeypatch):
    result = _run_child(pytester, monkeypatch, """
        def test_it():
            try:
                get_connection()
            except BaseException:
                pass
    """)

    result.assert_outcomes(passed=1, errors=1)
    output = result.stdout.str()
    assert "ERROR at teardown of test_it" in output
    assert _GET_CONNECTION_REFUSED in output


def test_an_access_in_a_worker_thread_fails_at_teardown(pytester, monkeypatch):
    """`chat_ui/chat_ui/admin_state.py` reaches storage through `asyncio.to_thread`."""
    result = _run_child(pytester, monkeypatch, """
        def _swallowing():
            try:
                get_connection()
            except BaseException:
                pass

        def test_it():
            asyncio.run(asyncio.to_thread(_swallowing))
    """)

    result.assert_outcomes(passed=1, errors=1)
    assert _GET_CONNECTION_REFUSED in result.stdout.str()


def test_a_direct_libsql_connect_is_refused_and_names_the_test(pytester, monkeypatch):
    result = _run_child(pytester, monkeypatch, """
        def test_it():
            libsql.connect("http://127.0.0.1:9")
    """)

    result.assert_outcomes(failed=1)
    output = result.stdout.str()
    assert "test_child.py::test_it reached storage (" in output
    assert "test_child.py:test_it)" in output
    _assert_no_network(output)


def test_a_client_cached_by_an_earlier_test_is_not_lent(pytester, monkeypatch):
    """The cache a `db` test leaves behind, installed by hand: the key matches and
    the idle probe is not due, so the real `_shared_client` would hand it out."""
    result = _run_child(pytester, monkeypatch, """
        def test_it():
            database._client = object()
            database._client_key = (settings.DATABASE_URL, settings.TURSO_AUTH_TOKEN)
            database._client_used_at = time.monotonic()
            get_connection()
    """)

    result.assert_outcomes(failed=1)
    assert _GET_CONNECTION_REFUSED in result.stdout.str()


def test_a_refusal_inside_a_testclient_request_fails_the_test(pytester, monkeypatch):
    """`ServerErrorMiddleware` catches `Exception` only, and `TestClient` re-raises
    server exceptions by default, so the refusal surfaces from the request."""
    result = _run_child(pytester, monkeypatch, """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        api = FastAPI()

        @api.get("/x")
        def x():
            get_connection()
            return {}

        def test_it():
            TestClient(api).get("/x")
    """)

    result.assert_outcomes(failed=1)
    assert _GET_CONNECTION_REFUSED in result.stdout.str()


def test_a_test_that_touches_no_storage_does_not_hear_from_the_guard(pytester, monkeypatch):
    result = _run_child(pytester, monkeypatch, """
        def test_it():
            assert settings.DATABASE_URL == "http://127.0.0.1:9"
    """)

    result.assert_outcomes(passed=1)


# --- The lazy endpoint, in a child run of the real conftest ---------------------


def test_a_test_that_is_not_db_runs_with_the_endpoint_unreachable(pytester, monkeypatch):
    """`-m "not db"` with Docker stopped, in one test: nothing asks for the probe."""
    result = _run_child(pytester, monkeypatch, """
        def test_it():
            assert settings.DATABASE_URL == "http://127.0.0.1:9"
    """, prelude=_LAZY_PRELUDE)

    result.assert_outcomes(passed=1)
    assert "is unreachable" not in result.stdout.str()


def test_a_db_test_exits_the_run_with_the_unreachable_message(pytester, monkeypatch):
    """`pytest.exit` leaves no outcome summary to parse, so the return code and
    the message are the assertion."""
    result = _run_child(pytester, monkeypatch, """
        @pytest.mark.db
        def test_it():
            pass
    """, prelude=_LAZY_PRELUDE)

    assert result.ret == 1
    result.stdout.fnmatch_lines(["*The libSQL dev server at http://127.0.0.1:9 is unreachable*"])
    output = result.stdout.str()
    assert "Start it with:" in output
    assert "1 passed" not in output
