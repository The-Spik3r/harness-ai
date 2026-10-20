"""PRD-014's harness, asserted rather than assumed.

`tests/conftest.py` decides which tests are `db` tests (STORY-002), and later
stories key the reset, the guard and the diagnostics on that one decision. A
marker that silently stopped applying would not turn anything red: `-m db`
would just select fewer tests and `-m "not db"` would quietly reach storage.
So the rule is checked here, against the conftest's own constants, and the
guard, the lazy endpoint and the recorder add their tests to this file as they
land.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

from tests.conftest import _DB_NODEIDS, _STORAGE_FIXTURES, _in_db_nodeids


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
