"""PRD-018 STORY-013 (Section 12 testing approach, D18): two real-fault tests, opt-in.

`tests/db_faults.py` proves the classifier and the retry rules with a scripted driver.
These two prove the same contract against failures nobody scripted: a connection that
is refused by the operating system, and a database server that restarts under a client
that still holds its old stream. They are `@pytest.mark.chaos`, skipped unless
`--run-chaos` is given (`tests/conftest.py`), so neither the everyday run nor CI ever
restarts anything:

    pytest tests/test_db_resilience_chaos.py -m chaos --run-chaos -v -s

**Never beside another pytest process.** The restart test stops the shared
`harness-libsql-dev` container, and every `db` test of every process uses it. The
`_dev_server_running` fixture leaves it started and ready whatever the test did, and
drops the cached client, so the next test's reset does not meet a dead stream (the
degradation `.agents/reports/PRD-008-*/STORY-006*.report.md` records).

The assertions are on the classifier's contract, not on one exact driver text: the
restart test accepts "absorbed" and "refused with `StorageUnavailableError`", and
fails only on what the PRD forbids (a raw driver error, or a counter that moved twice).
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import logging
import re
import shutil
import subprocess
import time
from urllib.parse import urlparse

import libsql
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import database
from app.db.database import admit_usage, find_user_by_token_hash, get_connection, insert_user
from app.db.errors import StorageUnavailableError
from app.db.models import User
from app.main import app
from app.services.identity import hash_token

pytestmark = pytest.mark.chaos

_CONTAINER = "harness-libsql-dev"
_LOG = "app.db.database"
_DEAD_PORT_URL = "http://127.0.0.1:1"  # nothing listens on port 1: a refused connection
_TOKEN = "chaos-token"
_USER = "chaos@chaos.test"


def _retry_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.name == _LOG and "retry op=" in r.getMessage()]


def _seed_user() -> None:
    insert_user(User(user_id=_USER, role="user", token_hash=hash_token(_TOKEN)))


def test_connection_refused_is_absorbed_then_refused_by_the_breaker(temp_db, caplog):
    """A dead endpoint: bounded retries, then the breaker answers without touching the network."""
    caplog.set_level(logging.INFO, logger=_LOG)
    _seed_user()
    healthy_url = settings.DATABASE_URL
    token_hash = hash_token(_TOKEN)
    try:
        settings.DATABASE_URL = _DEAD_PORT_URL
        database._invalidate_client()

        with pytest.raises(StorageUnavailableError):
            find_user_by_token_hash(token_hash)
        # Bounded: at most the three attempts of the budget. A refused connect is not
        # instant on every host (about 2 s on Windows), so the retry deadline (D1) may
        # spend the budget in fewer attempts; what is fixed is the class and the bound.
        exhausted = [
            r.getMessage()
            for r in caplog.records
            if r.name == _LOG and "retry exhausted" in r.getMessage()
        ]
        assert len(exhausted) == 1 and "class=not_sent" in exhausted[0]
        attempts = int(re.search(r"attempts=(\d+)", exhausted[0]).group(1))
        assert 1 <= attempts <= 3

        for _ in range(8):  # five failed operations open the breaker (threshold 5)
            if database._storage_breaker.status().state == "open":
                break
            with pytest.raises(StorageUnavailableError):
                find_user_by_token_hash(token_hash)
        assert database._storage_breaker.status().state == "open"

        seen = len(_retry_lines(caplog))
        started = time.monotonic()
        with pytest.raises(StorageUnavailableError) as refused:
            find_user_by_token_hash(token_hash)
        elapsed = time.monotonic() - started
        assert elapsed < 0.5, f"an open breaker took {elapsed:.3f} s to refuse"
        assert len(_retry_lines(caplog)) == seen  # no attempt was made
        assert refused.value.retry_after_seconds >= 1

        # The same outage through a real route: PRD Section 6.7's 503, fixed copy.
        response = TestClient(app, headers={"Authorization": f"Bearer {_TOKEN}"}).post(
            "/query", json={"prompt": "hello"}
        )
        assert response.status_code == 503
        assert int(response.headers["retry-after"]) >= 1
        for driver_text in ("tcp connect", "Connection refused", "Hrana", "127.0.0.1"):
            assert driver_text not in response.text
    finally:
        settings.DATABASE_URL = healthy_url
        database._invalidate_client()


def _docker(*args: str, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], check=True, capture_output=True, text=True, timeout=timeout)


def _wait_ready(url: str, seconds: float = 30) -> None:
    """Polls with a client of its own, so the shared client's cached stream is left as it is."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            libsql.connect(url).execute("SELECT 1").fetchone()
            return
        except Exception:  # noqa: BLE001 -- any failure means "not up yet"
            if time.monotonic() > deadline:
                raise
            time.sleep(0.3)


@pytest.fixture
def _dev_server_running(temp_db):
    """Skips without Docker or without the dev container; always leaves the server up."""
    host = urlparse(settings.DATABASE_URL).hostname
    if shutil.which("docker") is None or host not in ("127.0.0.1", "localhost"):
        pytest.skip("chaos restart needs Docker and the local libSQL dev server")
    try:
        _docker("inspect", _CONTAINER, timeout=15)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pytest.skip(f"no Docker container named {_CONTAINER}")
    url = settings.DATABASE_URL
    yield url
    try:
        _docker("start", _CONTAINER)  # a no-op when it is running
        _wait_ready(url)
    finally:
        database._invalidate_client()


def test_a_server_restart_under_a_live_client_is_absorbed_as_a_dead_stream(
    _dev_server_running, caplog
):
    """The client holds a stream the restarted server no longer knows (spike F4a)."""
    caplog.set_level(logging.INFO, logger=_LOG)
    _seed_user()
    token_hash = hash_token(_TOKEN)
    expected = find_user_by_token_hash(token_hash)  # warms the shared client's stream
    assert expected is not None and expected.user_id == _USER

    _docker("restart", _CONTAINER)
    _wait_ready(_dev_server_running)

    # An operation sees either the dead stream (retried on a fresh client, a read: always
    # safe) or a refusal; never a raw driver error.
    try:
        assert find_user_by_token_hash(token_hash) == expected
    except StorageUnavailableError:
        pass
    try:
        admit_usage(_USER)
    except StorageUnavailableError:
        pass

    for line in _retry_lines(caplog):
        print(line)  # visible with -s: the classes the real server produced
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(requests), 0) AS n FROM usage_daily WHERE user_id = ?", (_USER,)
        ).fetchone()
    assert row["n"] <= 1, "the counter moved twice: a non-idempotent write was replayed"
