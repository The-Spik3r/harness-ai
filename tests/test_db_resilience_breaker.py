"""The storage circuit breaker wired into `_unit_of_work` (PRD-018 STORY-005, D6/D7).

Two parts. The **non-`db`** tests (N1-N8) run under PRD-014's guard, which fails
any test that reaches `_shared_client()` or `libsql.connect`: an open breaker
that touched the driver would fail them without a line of assertion, and the
tests that do reach a driver install their own fake. The **`db`** tests (B1-B6)
request `faulty_db` and drive real operations against the dev server through the
`tests/db_faults.py` harness.

The breaker is reset for every test by the autouse `_fresh_storage_breaker` in
`tests/conftest.py`. Tests that need time install a clock-injected instance with
the `breaker_clock` fixture below. Threaded tests wait only on events and joins
with a timeout.
"""

import ast
import logging
import threading
from pathlib import Path

import pytest

from app.config import settings
from app.db import database
from app.db.database import (
    admit_usage,
    check_database_reachable,
    count_audit_logs,
    get_connection,
    init_db,
)
from app.db.errors import (
    DatabaseUnreachableError,
    IntegrityError,
    MissingRelationError,
    StorageError,
    StorageUnavailableError,
)
from app.services import usage_limits
from app.services.circuit_breaker import BreakerOpen, CircuitBreaker
from app.services.duplicate_checker import DuplicateCheckError, check_duplicate
from app.services.identity import Identity
from app.services.usage_limits import UsageLimitError
from tests.db_faults import CONNECT_REFUSED, NAMESPACE_SHUTDOWN_503, Fault
from tests.test_db_resilience_retry import (
    _NO_TABLE,
    _UNIQUE,
    K,
    _World,
    _calls_to,
    _top_level_functions,
)

_LOG = "app.services.circuit_breaker"


def _new_breaker(clock=None):
    kwargs = {"clock": clock} if clock is not None else {}
    return CircuitBreaker(
        "storage",
        database._BREAKER_FAILURE_THRESHOLD,
        database._BREAKER_OPEN_SECONDS,
        probe=database._probe_fresh_client,
        **kwargs,
    )


@pytest.fixture
def breaker_clock(monkeypatch):
    """A storage breaker with an injected clock; yields the one-element time cell."""
    now = [0.0]
    monkeypatch.setattr(database, "_storage_breaker", _new_breaker(lambda: now[0]))
    return now


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setattr(database, "_retry_sleep", lambda seconds: None)


@pytest.fixture(autouse=True)
def _capture(caplog):
    caplog.set_level(logging.INFO, logger=_LOG)


# --- N: non-db ---------------------------------------------------------------


def test_exactly_one_storage_breaker_with_the_prd_arguments():
    """N1: one instance, constants not defaults (AC 3)."""
    tree = ast.parse(Path(database.__file__).read_text(encoding="utf-8"))
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "CircuitBreaker"
    ]
    assert len(calls) == 1
    # PRD-018 STORY-012: the one construction moved into the factory
    # `_new_storage_breaker()` (so tests can build a counting breaker); the
    # module-level instance is still the factory's single product.
    (factory,) = [
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and any(c is calls[0] for c in ast.walk(n))
    ]
    assert factory.name == "_new_storage_breaker"
    (assign,) = [
        n
        for n in tree.body
        if isinstance(n, ast.Assign) and ast.unparse(n.value) == "_new_storage_breaker()"
    ]
    assert [t.id for t in assign.targets] == ["_storage_breaker"]
    call = calls[0]
    assert [ast.unparse(a) for a in call.args] == [
        "'storage'",
        "_BREAKER_FAILURE_THRESHOLD",
        "_BREAKER_OPEN_SECONDS",
    ]
    assert {k.arg: ast.unparse(k.value) for k in call.keywords} == {
        "probe": "_probe_fresh_client",
        "on_transition": "_count_breaker_open",  # PRD-018 STORY-012: breaker_opens
    }
    assert database._BREAKER_FAILURE_THRESHOLD == 5
    assert database._BREAKER_OPEN_SECONDS == 10.0
    assert database._storage_breaker.name == "storage"


def test_an_open_breaker_refuses_without_touching_the_driver(monkeypatch):
    """N2 / T1: no `_shared_client()` call, a fixed message with no driver text."""
    reached = []

    def counting_stub():
        reached.append(1)
        raise AssertionError("the open breaker reached the driver")

    monkeypatch.setattr(database, "_shared_client", counting_stub)
    database._storage_breaker.force_open(7.0)
    with pytest.raises(StorageUnavailableError) as raised:
        database.find_duplicate_timestamp("u", "k", "2026-01-01T00:00:00Z")
    assert raised.value.retry_after_seconds == 7
    assert isinstance(raised.value.__cause__, BreakerOpen)
    assert "Hrana" not in str(raised.value)
    assert reached == []


def test_the_consumers_fail_closed_with_no_code_change(monkeypatch):
    """N3 / AC 4: `check_duplicate`, `admit` and the token lookup against an open breaker."""
    database._storage_breaker.force_open(10.0)
    with pytest.raises(DuplicateCheckError) as dup:
        check_duplicate("u", "k")
    assert isinstance(dup.value.__cause__, StorageUnavailableError)
    with pytest.raises(UsageLimitError) as limit:
        usage_limits.admit(Identity("u1", "user"), charges_budget=True)
    assert isinstance(limit.value.__cause__, StorageUnavailableError)
    # Raises rather than returning None: an outage is never a bad credential.
    with pytest.raises(StorageUnavailableError):
        database.find_user_by_token_hash("h")


def test_exhausting_the_budget_counts_once_per_operation_and_opens_on_the_fifth(
    monkeypatch, breaker_clock
):
    """N4: one `record_failure` per operation, never per attempt (AC 3, AC 4)."""
    world = _World(monkeypatch, *[{"execute": CONNECT_REFUSED}] * 40)
    with pytest.raises(StorageUnavailableError) as first:
        world.run(K.READ)
    assert first.value.retry_after_seconds == 1  # still closed (PRD 6.7)
    assert isinstance(first.value.__cause__, StorageError)
    assert str(first.value) == str(first.value.__cause__) == CONNECT_REFUSED
    assert database._storage_breaker.status().consecutive_failures == 1
    for _ in range(3):
        with pytest.raises(StorageUnavailableError):
            world.run(K.READ)
    assert database._storage_breaker.status().state == "closed"
    with pytest.raises(StorageUnavailableError) as fifth:
        world.run(K.READ)
    assert fifth.value.retry_after_seconds == 10  # this failure opened it
    assert database._storage_breaker.status().state == "open"
    built = len(world.clients)
    with pytest.raises(StorageUnavailableError):
        world.run(K.READ)
    assert len(world.clients) == built  # the sixth built no client


def test_statement_failures_and_our_own_errors_are_neutral(monkeypatch, breaker_clock):
    """N5: STATEMENT keeps its exact type and the count; a refused retry counts once."""
    breaker = database._storage_breaker
    for text, expected in ((_UNIQUE, IntegrityError), (_NO_TABLE, MissingRelationError)):
        for _ in range(database._BREAKER_FAILURE_THRESHOLD):
            world = _World(monkeypatch, {"execute": text})
            with pytest.raises(expected) as raised:
                world.run(K.READ)
            assert type(raised.value) is expected
    assert breaker.status().consecutive_failures == 0
    assert breaker.status().state == "closed"

    ours = StorageError("chat session not available for this user")
    world = _World(monkeypatch)

    def body(conn):
        raise ours

    with pytest.raises(StorageError) as raised:
        world.run(K.READ, body)
    assert raised.value is ours
    assert breaker.status().consecutive_failures == 0

    world = _World(monkeypatch, {"execute": NAMESPACE_SHUTDOWN_503})
    with pytest.raises(StorageUnavailableError):
        world.run(K.NON_IDEMPOTENT)
    assert world.runs == 1
    status = breaker.status()
    assert status.consecutive_failures == 1
    assert status.last_failure_class == "outcome_unknown"

    for _ in range(4):
        world = _World(monkeypatch, {"execute": CONNECT_REFUSED}, {"execute": CONNECT_REFUSED}, {"execute": CONNECT_REFUSED})
        with pytest.raises(StorageUnavailableError):
            world.run(K.READ)
    # the refused NON_IDEMPOTENT above counted 1; four exhausted operations make 5
    assert breaker.status().state == "open"


def test_a_success_after_four_failures_resets_the_count(monkeypatch, breaker_clock):
    for _ in range(4):
        world = _World(monkeypatch, *[{"execute": CONNECT_REFUSED}] * 3)
        with pytest.raises(StorageUnavailableError):
            world.run(K.READ)
    assert database._storage_breaker.status().consecutive_failures == 4
    assert _World(monkeypatch).run(K.READ) == "ok"
    assert database._storage_breaker.status().consecutive_failures == 0


class _ProbeClient:
    """A stand-in for the client `libsql.connect` returns inside the probe."""

    def __init__(self, execute=None):
        self._execute = execute
        self.entered = threading.Event()
        self.holding_lock = []

    def execute(self, sql):
        assert sql == "SELECT 1"
        self.holding_lock.append(database._client_lock.locked())
        self.entered.set()
        if self._execute is not None:
            self._execute()
        return self

    def fetchone(self):
        return (1,)


def _install_cache_sentinels(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(database, "_client", sentinel)
    monkeypatch.setattr(database, "_client_key", ("sentinel-url", ""))
    monkeypatch.setattr(database, "_client_used_at", 0.0)
    return sentinel


def _half_open_ready(breaker_clock):
    database._storage_breaker.force_open(10.0)
    breaker_clock[0] = 10.0


def test_the_probe_holds_the_client_lock_and_nobody_waits_on_the_breaker(
    monkeypatch, breaker_clock
):
    """N6: no thread holds both locks, so nothing deadlocks, and nothing blocks on a probe."""
    _install_cache_sentinels(monkeypatch)
    go = threading.Event()
    client = _ProbeClient(execute=lambda: go.wait(timeout=5))
    import libsql

    monkeypatch.setattr(libsql, "connect", lambda *a, **k: client)
    _half_open_ready(breaker_clock)
    breaker = database._storage_breaker

    prober = threading.Thread(target=breaker.before)
    prober.start()
    assert client.entered.wait(timeout=5)
    assert client.holding_lock == [True]

    results = {}

    def read_status():
        results["status"] = breaker.status()

    def refused():
        try:
            breaker.before()
        except BreakerOpen:
            results["refused"] = True

    invalidator = threading.Thread(target=database._invalidate_client)
    others = [
        threading.Thread(target=read_status),
        threading.Thread(target=refused),
    ]
    for t in others:
        t.start()
    for t in others:
        t.join(timeout=1)
        assert not t.is_alive(), "status()/before() blocked behind the probe"
    assert results["status"].state == "half_open"
    assert results["refused"] is True
    invalidator.start()
    invalidator.join(timeout=0.05)
    assert invalidator.is_alive()  # blocked on _client_lock, as it should be

    go.set()
    for t in (prober, invalidator):
        t.join(timeout=2)
        assert not t.is_alive(), "deadlock between the breaker and _client_lock"
    assert breaker.status().state == "closed"
    # _invalidate_client ran after the probe cached its client and dropped it, so
    # either order is legal; what matters is that the lock was released.
    assert not database._client_lock.locked()


def test_the_probe_caches_the_new_client_on_success(monkeypatch, breaker_clock):
    _install_cache_sentinels(monkeypatch)
    client = _ProbeClient()
    import libsql

    monkeypatch.setattr(libsql, "connect", lambda *a, **k: client)
    _half_open_ready(breaker_clock)
    database._storage_breaker.before()
    assert database._client is client
    assert database._client_used_at > 0.0  # the idle gate is satisfied


def test_a_failed_probe_keeps_the_cache_and_a_foreign_error_propagates(
    monkeypatch, breaker_clock
):
    """N7."""
    sentinel = _install_cache_sentinels(monkeypatch)
    import libsql

    def refuse():
        raise ValueError(CONNECT_REFUSED)

    monkeypatch.setattr(libsql, "connect", lambda *a, **k: _ProbeClient(refuse))
    _half_open_ready(breaker_clock)
    with pytest.raises(BreakerOpen):
        database._storage_breaker.before()
    assert database._storage_breaker.status().state == "open"
    assert database._client is sentinel

    foreign = ValueError("not the driver's")

    def explode():
        raise foreign

    monkeypatch.setattr(libsql, "connect", lambda *a, **k: _ProbeClient(explode))
    breaker_clock[0] = 20.0
    with pytest.raises(ValueError) as raised:
        database._storage_breaker.before()
    assert raised.value is foreign
    assert database._storage_breaker.status().state == "open"  # not stuck half_open
    assert database._client is sentinel


def test_only_the_unit_of_work_consults_the_breaker():
    """N8 / D17: the boot path has no breaker (storage_status joins in STORY-012)."""
    users = {
        name
        for name, function in _top_level_functions().items()
        if any(
            isinstance(n, ast.Name) and n.id == "_storage_breaker"
            for n in ast.walk(function)
        )
    }
    # PRD-018 STORY-012: `storage_status()` reads `.status()` only (D16); the
    # docstring above announced it.
    # PRD-019 STORY-001 (D5): `check_ready()` joins them, and like `storage_status()`
    # it only reads `.status()`; test_db_check_ready.py proves it never moves the breaker.
    assert users == {"_unit_of_work", "storage_status", "check_ready"}
    functions = _top_level_functions()
    for name in ("init_db", "check_database_reachable"):
        assert _calls_to(functions[name], "_unit_of_work") == [], name


# --- B: db -------------------------------------------------------------------

_COUNT = "SELECT COUNT(*) AS N FROM AUDIT_LOGS"


def _fail_five_operations(faulty_db):
    faulty_db.add(Fault(CONNECT_REFUSED, sql=_COUNT, times=15))
    for _ in range(database._BREAKER_FAILURE_THRESHOLD):
        with pytest.raises(StorageUnavailableError):
            count_audit_logs()


def test_five_real_failed_operations_open_the_breaker(faulty_db):
    """B1."""
    _fail_five_operations(faulty_db)
    assert database._storage_breaker.status().state == "open"
    fired, connects, calls = (
        len(faulty_db.fired),
        faulty_db.connects,
        len(faulty_db.calls),
    )
    with pytest.raises(StorageUnavailableError) as sixth:
        count_audit_logs()
    assert sixth.value.retry_after_seconds >= 1
    assert (len(faulty_db.fired), faulty_db.connects, len(faulty_db.calls)) == (
        fired,
        connects,
        calls,
    )


def test_the_real_probe_closes_the_breaker_and_its_client_is_kept(
    faulty_db, breaker_clock
):
    """B2."""
    _fail_five_operations(faulty_db)
    connects = faulty_db.connects
    breaker_clock[0] = 10.0
    assert count_audit_logs() == 0
    assert faulty_db.connects == connects + 1  # the probe's client, nothing else
    assert database._client is not None
    assert database._storage_breaker.status().state == "closed"
    assert count_audit_logs() == 0
    assert faulty_db.connects == connects + 1  # that client is the cached one


def test_a_failing_probe_leaves_the_breaker_open(faulty_db, breaker_clock):
    _fail_five_operations(faulty_db)
    faulty_db.add(Fault(CONNECT_REFUSED, sql="SELECT 1"))
    breaker_clock[0] = 10.0
    with pytest.raises(StorageUnavailableError) as raised:
        count_audit_logs()
    assert raised.value.retry_after_seconds == 10
    assert database._storage_breaker.status().state == "open"


def test_statement_failures_never_open_the_breaker_against_the_real_server(faulty_db):
    """B3."""
    with get_connection() as conn:
        conn.execute("DROP TABLE audit_logs")
    for _ in range(6):
        with pytest.raises(MissingRelationError):
            count_audit_logs()
    status = database._storage_breaker.status()
    assert status.state == "closed" and status.consecutive_failures == 0


def test_a_refused_non_idempotent_retry_counts_once(faulty_db):
    """B4: the effect landed, and the breaker was told exactly once."""
    faulty_db.add(Fault(NAMESPACE_SHUTDOWN_503, op="commit", when="after"))
    with pytest.raises(StorageUnavailableError) as raised:
        admit_usage("dana")
    assert raised.value.retry_after_seconds == 1
    assert database._storage_breaker.status().consecutive_failures == 1
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM usage_daily WHERE user_id = ?", ("dana",)
        ).fetchone()
    assert row["requests"] == 1


def test_the_boot_path_bypasses_the_breaker(faulty_db, monkeypatch):
    """B5 / D17."""
    database._storage_breaker.force_open(10.0)
    init_db()
    check_database_reachable()
    assert database._storage_breaker.status().state == "open"

    fresh = _new_breaker()
    monkeypatch.setattr(database, "_storage_breaker", fresh)
    database._invalidate_client()
    faulty_db.add(Fault(CONNECT_REFUSED, sql="SELECT 1", times=5))
    with pytest.raises(DatabaseUnreachableError):
        init_db()
    assert fresh.status().consecutive_failures == 0


def test_the_transitions_are_logged_once_each_with_no_sql_or_credentials(
    faulty_db, breaker_clock, caplog
):
    """B6 / AC 5."""
    _fail_five_operations(faulty_db)
    breaker_clock[0] = 10.0
    count_audit_logs()
    lines = [r.getMessage() for r in caplog.records if r.name == _LOG]
    assert lines == [
        "breaker name=storage from=closed to=open class=not_sent",
        "breaker name=storage from=open to=half_open class=none",
        "breaker name=storage from=half_open to=closed class=none",
    ]
    for line in lines:
        assert "SELECT" not in line.upper()
        assert not settings.TURSO_AUTH_TOKEN or settings.TURSO_AUTH_TOKEN not in line
