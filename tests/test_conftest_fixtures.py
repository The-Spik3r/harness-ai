"""The database fixtures' own contract, asserted rather than assumed.

`tests/conftest.py` is the seam PRD-007 STORY-006 flips: 19 files stopped
spelling their own database URLs and now depend on what these fixtures
promise. Those promises -- a URL string and not a path, per-test isolation, and
a database with no schema when one is asked for -- are only worth something if
something checks them, and every consuming test would keep passing today for
reasons that have nothing to do with them.

These tests are written against the *contract*, never against SQLite. Nothing
here opens a file, joins a path, or asserts a scheme, so STORY-006 inherits
them unchanged.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

from app.config import Settings, settings
from app.db.database import count_audit_logs, get_connection, insert_audit_log, init_db
from app.db.models import AuditLog


def _an_audit_row(user_id: str = "ana@empresa.com") -> AuditLog:
    return AuditLog(
        timestamp="2026-09-01T10:00:00Z", user_id=user_id, prompt_hash="abc123"
    )


# --- The seam itself: a URL string, and the one settings actually reads ------


def test_the_fixture_yields_a_url_string_not_a_path(temp_db):
    """A `Path` return would bake "the database is a file" into 19 files, which
    is the assumption the migration removes. Asserted by type, so this fails the
    day someone "helpfully" hands back a path again."""
    assert isinstance(temp_db, str)


def test_settings_points_at_the_url_the_fixture_returned(temp_db):
    """The fixture's whole job. Without this, every test below could pass
    against the developer's real database and no one would know."""
    assert settings.DATABASE_URL == temp_db


def test_the_url_is_not_the_configured_default(temp_db):
    """A fixture that silently failed to patch would leave the developer's own
    configured database in place, and every test below would still pass.

    Compared against the declared default rather than a literal, so this test
    neither duplicates `app/config.py` nor has to be edited when STORY-005
    changes what that default is.
    """
    assert temp_db != Settings.model_fields["DATABASE_URL"].default


# --- Isolation (AC 1): no test sees another test's rows ---------------------

_FIRST_MARKER = "isolation-probe-one@empresa.com"
_SECOND_MARKER = "isolation-probe-two@empresa.com"


def test_isolation_first_test_writes_a_row(temp_db):
    insert_audit_log(_an_audit_row(_FIRST_MARKER))

    assert count_audit_logs() == 1


def test_isolation_second_test_sees_an_empty_database(temp_db):
    """Runs after the test above and must not observe its row. The pair is the
    assertion; neither half means anything alone."""
    assert count_audit_logs() == 0

    insert_audit_log(_an_audit_row(_SECOND_MARKER))
    with get_connection() as conn:
        users = {
            row["user_id"] for row in conn.execute("SELECT user_id FROM audit_logs")
        }
    assert users == {_SECOND_MARKER}


def test_two_requests_in_one_test_get_one_database(temp_db, database_url):
    """`temp_db` is built on `database_url`, so a test requesting both must get
    a single database -- not two, and not a second one that quietly replaces the
    first's patch."""
    assert temp_db == database_url


# --- The uninitialized case (AC 4) -----------------------------------------


def test_uninitialized_db_has_no_schema(uninitialized_db):
    """The STORY-002 characterization tests need a database whose `users` table
    is absent. Proven by asking the storage layer, not by stat-ing a file.

    The exception type is deliberately unpinned: STORY-004 replaces the driver's
    exception with a module-owned one, and this test must survive that untouched
    -- the claim here is "no schema", not "sqlite3 raised".
    """
    with pytest.raises(Exception):
        count_audit_logs()


def test_uninitialized_db_becomes_usable_after_init_db(uninitialized_db):
    """The fixture withholds the schema; it does not hand back something broken."""
    init_db()

    assert count_audit_logs() == 0


def test_uninitialized_db_also_yields_a_url_string(uninitialized_db):
    assert isinstance(uninitialized_db, str)
    assert settings.DATABASE_URL == uninitialized_db


# --- The subprocess factory -------------------------------------------------


def test_factory_yields_a_distinct_url_on_every_call(database_url_factory):
    """Two probes must not share a database. `mktemp` guarantees this; the
    assertion is here because the guarantee is easy to lose when the factory is
    rewritten for a libSQL endpoint."""
    first = database_url_factory("probe")
    second = database_url_factory("probe")

    assert isinstance(first, str) and isinstance(second, str)
    assert first != second


def test_factory_does_not_patch_this_process_settings(database_url_factory, temp_db):
    """It mints URLs for *child* processes. Patching the parent would leak
    across a module-scoped fixture and silently redirect the caller's own
    database."""
    minted = database_url_factory("probe")

    assert settings.DATABASE_URL == temp_db
    assert settings.DATABASE_URL != minted


# --- db_connect -------------------------------------------------------------


def test_db_connect_opens_the_same_database_settings_names(temp_db, db_connect):
    """The pre-migration schema builders in test_db.py write through this
    connection and then read back through the storage layer, so the two must be
    the same database."""
    insert_audit_log(_an_audit_row())

    conn = db_connect(temp_db)
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()
    finally:
        conn.close()

    assert count == 1
    assert count_audit_logs() == 1


def test_db_connect_can_build_a_table_init_db_would_not(uninitialized_db, db_connect):
    """Why a raw connection exists at all: the legacy-migration tests need a
    table shape `init_db()` does not produce."""
    conn = db_connect(uninitialized_db)
    try:
        conn.execute("CREATE TABLE legacy_probe (id INTEGER PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()

    with get_connection() as check:
        found = check.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='legacy_probe'"
        ).fetchone()
    assert found is not None
