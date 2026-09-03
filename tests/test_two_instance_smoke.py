"""Two application instances, one database. The epic's exit criterion.

PRD-007 exists for two reasons. Every other story in it removes a blocker; this
module is the evidence that the second blocker -- "the deployment cannot scale
past one instance" -- is actually gone. If this file does not pass, the migration
is not done regardless of what the other fifteen stories say.

**Two processes, not two threads.** `tests/test_db.py:1866` already proves that
concurrent `init_db()` calls converge, and it does so with threads in one
interpreter. That is the right test for the schema race and the wrong one for
this story: a per-process client cache, a per-process schema assumption, and an
import-time `init_db()` race are all invisible inside a single interpreter,
because one process shares one `_shared_client()` and one imported module table.
So the instances here are real `subprocess.Popen` children, built the way
`tests/test_admin_shell.py:709` and `tests/test_chat_ui_startup_guard.py:61`
build their probes -- and upgraded from `subprocess.run` to a long-lived
conversation, because every existing probe answers one question and exits.

**Why a long-lived child is not a convenience.** "Instance B detects a duplicate
written by instance A" is only evidence if B was *already running* when A wrote.
A fresh process started afterwards proves the database persisted a row, which is
STORY-006's claim, not this one. Every failure mode this story targets belongs to
a process that has already booted, so the children have to stay booted.

**Determinism comes from the pipe, not from timing.** Parent and child speak
line-delimited JSON over stdin/stdout: one command in, exactly one reply out.
Every ordering asserted here -- write on A *then* read on B, create a user
*while* both are running, deactivate *then* authenticate on both -- is sequenced
by the parent's blocking `readline()`. Concurrency is expressed by writing a
batch of commands to both children *before* reading either's replies, which puts
real work in flight in two processes at once without a `sleep` anywhere in this
file. There is no timeout to tune and no race to lose: see `_INVARIANTS` at the
bottom for the constraints this file holds itself to.

Running it needs the same local libSQL dev server the rest of the suite uses
(`tests/conftest.py`), and no Turso account.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.conftest import child_db_env  # noqa: E402

from app.db.database import insert_user  # noqa: E402
from app.db.models import AUDIT_LOGS_ADDED_COLUMNS, User  # noqa: E402
from app.services.duplicate_checker import hash_prompt  # noqa: E402
from app.services.identity import hash_token  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The two instances. Names travel into the children and come back in every
#: reply, so an assertion can say *which* instance failed -- which for AC 5
#: ("both reject them") is the whole point.
_INSTANCE_NAMES = ("instance-a", "instance-b")

_USER_ID = "smoke@empresa.com"
_USER_TOKEN = "two-instance-smoke-token"

#: `app/services/duplicate_checker.py:28` computes its cutoff as now - 24h and
#: takes no configuration, so the window is controlled by choosing a row's
#: timestamp, never by waiting for one to age out. A duplicate test that raced
#: the clock would be deleted by someone in six months, which is worse than not
#: writing it.
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_OUTSIDE_THE_WINDOW = timedelta(hours=25)


# --------------------------------------------------------------------------
# The instance. Runs in a subprocess; speaks one JSON object per line.
# --------------------------------------------------------------------------

# `sys.stdout` is captured and then replaced by stderr before anything else runs.
# The protocol lives on the real stdout and nothing else may write there: a
# stray `print` from a library -- or from a future edit to app/ -- would
# otherwise land between two protocol lines and desynchronize the parent for the
# rest of the run. Redirecting instead of trusting is the difference between a
# legible failure and a mystery.
#
# TestClient is deliberately *not* used as a context manager: that would run
# FastAPI's lifespan, which calls init_db() itself. Boot ordering is what AC 1
# measures, so it has to be visible here rather than hidden in a lifespan.
#
# The schema is reported in the ready line rather than asked for later, because
# `tests/conftest.py:129`'s autouse reset drops every table before *every* test
# -- including the first one, which runs after these children have booted. The
# evidence of what a boot produced has to be captured at boot.
_INSTANCE_SCRIPT = r"""
import json, os, sys, time

_out = sys.stdout
sys.stdout = sys.stderr  # nothing but the protocol reaches the real stdout


def emit(payload):
    _out.write(json.dumps(payload) + "\n")
    _out.flush()


NAME = os.environ["INSTANCE_NAME"]

try:
    from fastapi.testclient import TestClient

    import app.db.database as database
    import app.routers.query as query_router
    from app.db.models import AuditLog
    from app.main import app
    from app.services import authz
    from app.services.openrouter_client import OpenRouterResult

    # The one thing that must not reach the network. Patched by assignment
    # because a child has no monkeypatch; the shape is
    # tests/test_integration.py:46's fake, and the call site it replaces is
    # tests/test_integration.py:53's. PII redaction is left real, exactly as
    # tests/test_integration.py leaves it: this is a smoke test of the deployed
    # pipeline, not of a stubbed one.
    def fake_call_openrouter(prompt, model="gpt-4", api_key=None):
        return OpenRouterResult(response="mock response", model_used=model, tokens_used=7)

    query_router.call_openrouter = fake_call_openrouter

    authz.load()
    database.init_db()
    client = TestClient(app)
except Exception as exc:
    emit({"ready": False, "name": NAME, "error": "{}: {}".format(type(exc).__name__, exc)})
    raise


def schema():
    with database.get_connection() as conn:
        tables = sorted(
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        )
        columns = {}
        for table in tables:
            columns[table] = sorted(
                row["name"] for row in conn.execute("PRAGMA table_info({})".format(table))
            )
    return {"tables": tables, "columns": columns}


class Recording:
    '''tests/test_db.py:967's proxy, hand-rolled: a child has no monkeypatch.

    __enter__/__exit__ are not decoration. app/db/database.py:441's _session()
    does `with conn:`, so a proxy without them turns every measured write into
    an AttributeError instead of a measurement.
    '''

    def __init__(self, conn, statements):
        self._conn = conn
        self._statements = statements

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, *exc_info):
        return self._conn.__exit__(*exc_info)

    def execute(self, sql, *parameters):
        self._statements.append(sql)
        return self._conn.execute(sql, *parameters)

    def cursor(self):
        return self._conn.cursor()


def measured(work):
    '''Runs work(), returning (result, elapsed_ms, statements-issued).'''
    statements = []
    real = database.get_connection
    database.get_connection = lambda: Recording(real(), statements)
    started = time.perf_counter()
    try:
        result = work()
    finally:
        database.get_connection = real
    elapsed_ms = (time.perf_counter() - started) * 1000
    return result, elapsed_ms, statements


def do_query(command):
    def work():
        return client.post(
            "/query",
            json={"prompt": command["prompt"], "model": command.get("model", "gpt-4")},
            headers={"Authorization": "Bearer " + command["token"]},
        )

    response, elapsed_ms, statements = measured(work)
    return {
        "status_code": response.status_code,
        "body": response.json(),
        "elapsed_ms": elapsed_ms,
        "statements": statements,
    }


def do_authenticate(command):
    # A real request through the real dependency chain, not a resolve() call:
    # AC 4 and AC 5 are claims about what an instance *serves*, and calling
    # resolve() directly would skip app/middleware/auth.py's 401.
    response = client.get(
        "/audit", headers={"Authorization": "Bearer " + command["token"]}
    )
    return {"status_code": response.status_code}


def do_plant_audit_row(command):
    # Writes straight through the storage layer rather than through the
    # pipeline: the point is a row whose timestamp the test chose.
    return {
        "audit_id": database.insert_audit_log(
            AuditLog(
                timestamp=command["timestamp"],
                user_id=command["user_id"],
                prompt_hash=command["prompt_hash"],
                prompt_preview=command.get("prompt_preview"),
            )
        )
    }


def do_rows(command):
    rows = database.list_audit_logs(limit=command.get("limit", 1000))
    return {
        "rows": [
            {
                "user_id": row.user_id,
                "prompt_hash": row.prompt_hash,
                "prompt_preview": row.prompt_preview,
                "model_used": row.model_used,
                "tokens_used": row.tokens_used,
                "success": row.success,
                "was_duplicate_blocked": row.was_duplicate_blocked,
                "timestamp": row.timestamp,
            }
            for row in rows
        ]
    }


def do_audit_ids(command):
    with database.get_connection() as conn:
        return {
            "ids": [
                row[0]
                for row in conn.execute("SELECT id FROM audit_logs ORDER BY id").fetchall()
            ]
        }


def do_console_load(command):
    # What an admin console load reduces to since STORY-012:
    # chat_ui/chat_ui/admin_state.py:1056 makes exactly this call, with these
    # limits (REGISTER_ROW_LIMIT=100, RANKED_LIMIT=5), on one to_thread hop.
    snapshot, elapsed_ms, statements = measured(
        lambda: database.summary_snapshot(row_limit=100, ranked_limit=5)
    )
    return {
        "elapsed_ms": elapsed_ms,
        "statements": statements,
        "figures": sorted(snapshot.figures),
        "errors": sorted(snapshot.errors),
    }


HANDLERS = {
    "init_db": lambda command: {"ok": database.init_db() is None},
    "schema": lambda command: schema(),
    "query": do_query,
    "authenticate": do_authenticate,
    "plant_audit_row": do_plant_audit_row,
    "rows": do_rows,
    "audit_ids": do_audit_ids,
    "console_load": do_console_load,
}

emit({"ready": True, "name": NAME, "schema": schema()})

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    command = json.loads(line)
    if command["cmd"] == "stop":
        break
    try:
        reply = HANDLERS[command["cmd"]](command)
    except Exception as exc:
        reply = {"error": "{}: {}".format(type(exc).__name__, exc)}
    reply["name"] = NAME
    emit(reply)

sys.exit(0)
"""


class Instance:
    """One running application process, addressed over its own pipes."""

    def __init__(self, name: str, url: str) -> None:
        self.name = name
        # TURSO_AUTH_TOKEN is blanked deliberately. A child builds its own
        # Settings() where monkeypatch cannot reach -- the exact mechanism
        # behind STORY-014's Finding 1 and STORY-015's Finding 1, both of which
        # were an inherited environment variable reaching a real database. The
        # URL is pinned and the credential is emptied here rather than trusted
        # to the invocation, which is the same triple README.md:456 documents
        # for the in-container suite.
        env = {
            **os.environ,
            **child_db_env(url),
            "TURSO_AUTH_TOKEN": "",
            "RBAC_ENABLED": "true",
            "INSTANCE_NAME": name,
            "PYTHONPATH": str(REPO_ROOT),
        }
        self.proc = subprocess.Popen(
            [sys.executable, "-c", _INSTANCE_SCRIPT],
            cwd=str(REPO_ROOT),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.ready: dict = {}

    # -- protocol ---------------------------------------------------------

    def send(self, **command) -> None:
        """Writes one command without waiting for its reply.

        Separate from `recv` on purpose: sending to both instances before
        reading from either is how this module expresses concurrency.
        """
        self._alive("sending " + command["cmd"])
        self.proc.stdin.write(json.dumps(command) + "\n")
        self.proc.stdin.flush()

    def recv(self) -> dict:
        line = self.proc.stdout.readline()
        if not line:
            self._died("its stdout closed")
        reply = json.loads(line)
        if reply.get("error"):
            pytest.fail(f"{self.name} returned an error: {reply['error']}")
        return reply

    def call(self, **command) -> dict:
        self.send(**command)
        return self.recv()

    # -- lifecycle --------------------------------------------------------

    def await_ready(self) -> dict:
        self.ready = self.recv()
        if not self.ready.get("ready"):
            self._died(f"it reported {self.ready.get('error')!r} during boot")
        return self.ready

    def stop(self) -> None:
        if self.proc.poll() is None:
            try:
                self.proc.stdin.write(json.dumps({"cmd": "stop"}) + "\n")
                self.proc.stdin.flush()
            except (BrokenPipeError, ValueError):
                pass
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()

    # -- failure reporting ------------------------------------------------

    def _alive(self, doing: str) -> None:
        if self.proc.poll() is not None:
            self._died(f"it had already exited before {doing}")

    def _died(self, why: str) -> None:
        """Fails the test with both streams. A dead child must never hang the
        suite on a `readline()` that will not return."""
        self.proc.kill()
        stderr = self.proc.stderr.read() if self.proc.stderr else ""
        pytest.fail(f"{self.name} is not answering -- {why}.\nstderr:\n{stderr}")


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def instances(database_url_factory):
    """Two instances, started simultaneously against one database.

    `database_url_factory` rather than `database_url`: this fixture is
    module-scoped, and a module-scoped fixture requesting a function-scoped one
    is a `ScopeMismatch` -- `tests/conftest.py:193` exists for exactly this.

    Both children are constructed before *either* ready line is read. That
    ordering is AC 1's "start simultaneously": the two processes race through
    `init_db()` against one database with nothing serializing them, which is the
    end-to-end form of `tests/test_db.py:1866`'s thread-level convergence test.
    """
    url = database_url_factory("two_instance_smoke")
    running = [Instance(name, url) for name in _INSTANCE_NAMES]
    try:
        for instance in running:
            instance.await_ready()
        yield tuple(running)
    finally:
        for instance in running:
            instance.stop()


@pytest.fixture(autouse=True)
def fresh_schema(instances):
    """Restores the schema conftest's autouse reset just dropped -- from both
    instances at once, which keeps their clients warm as a side effect.

    `tests/conftest.py:129` drops every table before every test, including the
    ones these long-lived children created at boot. Re-creating it is therefore
    per-test work, and issuing it to both instances concurrently means each test
    re-runs AC 1's convergence rather than assuming it.
    """
    for instance in instances:
        instance.send(cmd="init_db")
    for instance in instances:
        assert instance.recv()["ok"] is True, instance.name


@pytest.fixture
def smoke_user(instances):
    """One `user`-role credential, written by the parent to the shared database.

    The parent writes it because the instances are already running: a token both
    of them accept without either having restarted is the point of AC 4, and
    this fixture is the smaller version of it that the other tests need.
    """
    insert_user(User(user_id=_USER_ID, role="user", token_hash=hash_token(_USER_TOKEN)))
    return _USER_TOKEN


# --------------------------------------------------------------------------
# AC 1 -- both instances boot against one database, with the same schema
# --------------------------------------------------------------------------


def test_both_instances_boot_simultaneously_against_one_database(instances):
    """AC 1, end-to-end. `tests/test_db.py:1866` proves this for threads.

    The schema asserted here is the one each child recorded at boot, not one
    read now: conftest's autouse reset has dropped and `fresh_schema` re-created
    the tables since. Boot evidence has to be captured at boot.
    """
    for instance in instances:
        assert instance.ready["ready"] is True, instance.name
        assert instance.ready["name"] == instance.name

    schemas = [instance.ready["schema"] for instance in instances]

    for instance, schema in zip(instances, schemas):
        assert schema["tables"] == ["audit_logs", "users"], instance.name
        # Imported, not spelled out: a column added to the schema later must
        # make this test stronger rather than leave it quietly passing.
        assert set(AUDIT_LOGS_ADDED_COLUMNS) <= set(schema["columns"]["audit_logs"]), (
            instance.name,
            schema["columns"]["audit_logs"],
        )
        assert schema["columns"]["users"] == [
            "active",
            "created_at",
            "role",
            "token_hash",
            "user_id",
        ], instance.name

    # The failure AC 1 actually guards: two instances that each booted fine but
    # converged on different schemas. `_add_missing_columns()` treating
    # "duplicate column name" as success is what makes this hold.
    assert schemas[0] == schemas[1]


# --------------------------------------------------------------------------
# AC 2 -- cross-instance duplicate detection
# --------------------------------------------------------------------------


def test_a_prompt_answered_by_instance_a_is_blocked_by_instance_b(
    instances, smoke_user
):
    """AC 2, and PRD Section 5 story 2 verbatim.

    The sharpest observable proof that the two processes share state: B has
    never seen this prompt and never restarted, so the only place its answer can
    come from is A's row in the shared `audit_logs`.
    """
    instance_a, instance_b = instances
    prompt = "what did the second instance never see"

    first = instance_a.call(cmd="query", prompt=prompt, token=smoke_user)
    assert first["status_code"] == 200, first
    assert first["body"]["status"] == "SUCCESS", first["body"]
    assert isinstance(first["body"]["audit_id"], int)

    second = instance_b.call(cmd="query", prompt=prompt, token=smoke_user)
    assert second["status_code"] == 200, second
    assert second["body"]["status"] == "BLOCKED", second["body"]
    assert second["body"]["reason"] == "Duplicate query within 24 hours"

    # Not merely "blocked": blocked *by A's row*. first_query_at is the
    # timestamp instance A wrote, which is what makes this cross-instance
    # rather than a coincidence.
    rows = instance_b.call(cmd="rows")["rows"]
    written_by_a = [row for row in rows if not row["was_duplicate_blocked"]]
    assert len(written_by_a) == 1, rows
    assert second["body"]["first_query_at"] == written_by_a[0]["timestamp"]


def test_a_prompt_outside_the_window_is_not_blocked_by_the_other_instance(
    instances, smoke_user
):
    """AC 2's control. The window is chosen, never waited for.

    Without this, the test above would also pass against an implementation that
    blocked on any prompt hash ever recorded -- which would make the 24-hour
    window in `app/services/duplicate_checker.py:28` untested and the block
    above evidence of the wrong thing.
    """
    instance_a, instance_b = instances
    prompt = "a prompt whose only record is older than the window"
    stale = (datetime.now(timezone.utc) - _OUTSIDE_THE_WINDOW).strftime(
        _TIMESTAMP_FORMAT
    )

    planted = instance_a.call(
        cmd="plant_audit_row",
        timestamp=stale,
        user_id=_USER_ID,
        prompt_hash=hash_prompt(prompt),
        prompt_preview=prompt,
    )
    assert isinstance(planted["audit_id"], int)

    answered = instance_b.call(cmd="query", prompt=prompt, token=smoke_user)
    assert answered["status_code"] == 200, answered
    assert answered["body"]["status"] == "SUCCESS", answered["body"]


# --------------------------------------------------------------------------
# AC 3 and AC 6 -- concurrent writes: nothing lost, nothing duplicated
# --------------------------------------------------------------------------

#: Per instance, so 2N rows total. Large enough that a lost or double-counted
#: row is unambiguous, small enough that the module stays quick.
_CONCURRENT_QUERIES_PER_INSTANCE = 10


def test_concurrent_queries_from_both_instances_lose_no_rows(instances, smoke_user):
    """AC 3 and AC 6 together, because they are one read of the audit trail.

    Every command is written to both children *before* any reply is read, so
    both processes have work in flight at once -- concurrency without a sleep.
    Each prompt names its instance and index, so a row can be traced back to the
    process that wrote it and "no row is corrupted" is a comparison rather than
    an impression.
    """
    prompts = {
        instance.name: [
            f"concurrent probe from {instance.name} number {index}"
            for index in range(_CONCURRENT_QUERIES_PER_INSTANCE)
        ]
        for instance in instances
    }

    for index in range(_CONCURRENT_QUERIES_PER_INSTANCE):
        for instance in instances:
            instance.send(
                cmd="query", prompt=prompts[instance.name][index], token=smoke_user
            )

    failures = []
    for index in range(_CONCURRENT_QUERIES_PER_INSTANCE):
        for instance in instances:
            reply = instance.recv()
            if reply["status_code"] != 200 or reply["body"].get("status") != "SUCCESS":
                failures.append((instance.name, index, reply))
    assert not failures, f"a concurrent query did not succeed: {failures}"

    expected = sorted(prompt for batch in prompts.values() for prompt in batch)
    total = len(expected)

    # Read from B after both wrote, so this re-proves the shared view as well.
    rows = instances[1].call(cmd="rows")["rows"]

    assert len(rows) == total, f"expected {total} audit rows, found {len(rows)}"
    assert sorted(row["prompt_preview"] for row in rows) == expected
    assert len({row["prompt_hash"] for row in rows}) == total, "a prompt hash repeated"

    # AC 6: ids unique, and every field the caller supplied still matches.
    ids = instances[0].call(cmd="audit_ids")["ids"]
    assert len(ids) == total, ids
    assert len(set(ids)) == total, f"audit_logs.id repeated: {ids}"

    for row in rows:
        assert row["user_id"] == _USER_ID, row
        assert row["model_used"] == "gpt-4", row
        assert row["tokens_used"] == 7, row
        assert row["success"] is True, row
        assert row["was_duplicate_blocked"] is False, row
        assert row["prompt_hash"] == hash_prompt(row["prompt_preview"]), row


# --------------------------------------------------------------------------
# AC 4 and AC 5 -- credentials created and revoked while both instances run
# --------------------------------------------------------------------------


def _manage_users(database_url: str, *args: str) -> subprocess.CompletedProcess:
    """Runs `scripts/manage_users.py` against the shared database.

    Same environment discipline as the instances: pinned URL, blanked token.
    """
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "manage_users.py"), *args],
        cwd=str(REPO_ROOT),
        env={
            **os.environ,
            **child_db_env(database_url),
            "TURSO_AUTH_TOKEN": "",
            "PYTHONPATH": str(REPO_ROOT),
        },
        capture_output=True,
        text=True,
    )


_TOKEN_PREFIX = "Token (save this now -- it cannot be recovered): "


@pytest.fixture
def cli_user(database_url_factory):
    """A user created by the CLI *while both instances are already running*."""
    user_id = "cli-created@empresa.com"
    result = _manage_users(
        database_url_factory("two_instance_smoke"),
        "create-user",
        "--user-id",
        user_id,
        "--role",
        "user",
    )
    assert result.returncode == 0, f"create-user failed:\n{result.stdout}\n{result.stderr}"
    tokens = [
        line[len(_TOKEN_PREFIX) :]
        for line in result.stdout.splitlines()
        if line.startswith(_TOKEN_PREFIX)
    ]
    assert len(tokens) == 1, result.stdout
    return user_id, tokens[0]


def test_a_user_created_by_the_cli_resolves_on_both_running_instances(
    instances, cli_user, database_url_factory
):
    """AC 4. Neither instance restarted, so a cached identity would fail here.

    `find_user_by_token_hash()` reads the shared `users` table on every
    resolution (`app/services/identity.py:58`); this is the end-to-end statement
    that nothing above it holds on to the answer.
    """
    _, token = cli_user

    for instance in instances:
        reply = instance.call(cmd="authenticate", token=token)
        assert reply["status_code"] == 200, (instance.name, reply)


def test_a_deactivated_user_is_rejected_by_both_running_instances(
    instances, cli_user, database_url_factory
):
    """AC 5. Revocation that lands on one instance only is a security failure.

    Asserted against both instances separately, each naming itself in the
    failure message -- a version of this test that checked one instance would be
    the bug it is meant to catch.
    """
    user_id, token = cli_user
    url = database_url_factory("two_instance_smoke")

    for instance in instances:
        assert instance.call(cmd="authenticate", token=token)["status_code"] == 200, (
            instance.name,
            "the credential did not work before revocation",
        )

    result = _manage_users(url, "deactivate-user", "--user-id", user_id)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    for instance in instances:
        reply = instance.call(cmd="authenticate", token=token)
        assert reply["status_code"] == 401, (
            instance.name,
            "a deactivated credential still authenticates",
            reply,
        )


# --------------------------------------------------------------------------
# AC 8 -- the measured numbers
# --------------------------------------------------------------------------


def test_round_trip_cost_is_measured_and_reported(instances, smoke_user, capsys):
    """AC 8, closing PRD Section 12 Phase 3's "Measured round-trip counts".

    Statement counts are *asserted*, wall-clock is *recorded*. A latency
    threshold asserted as pass/fail would make this file flaky on a loaded
    machine, and the number that carries the meaning is the count: PRD Section 5
    story 6 says a query costs one duplicate-check read and one audit write, and
    this is where that claim is checked rather than restated.

    The figures are same-host against the local dev server, so they understate
    the gain against a remote endpoint -- the same caveat STORY-011 recorded.
    """
    instance_a, _ = instances

    # One warm query first: the first call in a process pays for the PII
    # analyzer's model load, which is not a round trip and must not be counted
    # as one.
    warmup = instance_a.call(cmd="query", prompt="warm the analyzer", token=smoke_user)
    assert warmup["body"]["status"] == "SUCCESS", warmup

    measured = instance_a.call(
        cmd="query", prompt="the measured query", token=smoke_user
    )
    assert measured["body"]["status"] == "SUCCESS", measured
    query_statements = measured["statements"]

    console = instance_a.call(cmd="console_load")
    console_statements = console["statements"]

    # Three, not the two PRD Section 5 story 6 predicts -- and the third is the
    # interesting one. That story counts what `run_query()` adds (a
    # duplicate-check read and an audit write) and stops at the pipeline's edge;
    # a *request* first resolves its credential through
    # `find_user_by_token_hash()` (`app/services/identity.py:58`), which is a
    # third round trip on the same shared client. It is not removable and it is
    # not a defect: the two tests above prove that read is *not* cached, which
    # is what makes revocation take effect on both instances at once. Asserted
    # by name rather than by count so that a fourth statement -- or the identity
    # read quietly disappearing into a cache -- fails here loudly.
    assert [statement.split()[0].upper() for statement in query_statements] == [
        "SELECT",
        "SELECT",
        "INSERT",
    ], query_statements
    assert "FROM users" in query_statements[0], query_statements[0]
    assert "FROM audit_logs" in query_statements[1], query_statements[1]
    assert "INTO audit_logs" in query_statements[2], query_statements[2]

    assert len(console_statements) == 1, (
        "an admin console load is one batched read since STORY-010; issued "
        f"{len(console_statements)}: {console_statements}"
    )
    assert console["errors"] == [], console

    with capsys.disabled():
        print(
            "\n--- STORY-016 measured round-trip cost "
            "(local libSQL dev server, same host) ---\n"
            f"  POST /query        : {len(query_statements)} statements "
            "(identity read, duplicate check, audit write), "
            f"{measured['elapsed_ms']:.1f} ms\n"
            f"  admin console load : {len(console_statements)} statement, "
            f"{console['elapsed_ms']:.1f} ms\n"
        )


# --------------------------------------------------------------------------
# AC 7 -- what keeps this deterministic
# --------------------------------------------------------------------------

#: Constraints this module holds itself to, recorded because the next reader
#: will be tempted to break one of them:
#:
#:  1. No `time.sleep`, and no polling loop. Ordering comes from blocking
#:     `readline()` on a pipe; concurrency comes from sending to both children
#:     before reading from either.
#:  2. No wall-clock value is asserted as a pass/fail bound. Durations are
#:     recorded and printed; only statement *counts* are asserted.
#:  3. No test depends on which instance wins a race. Where both write, the
#:     assertions are over sets and totals.
#:  4. The endpoint comes from conftest's `database_url_factory` alone, so
#:     `HARNESS_TEST_LIBSQL_URL` redirects the children with the rest of the
#:     suite. Nothing here names a hosted Turso database, and no test needs an
#:     account.
#:  5. Every child environment pins `DATABASE_URL` and blanks
#:     `TURSO_AUTH_TOKEN`, because a child builds its own `Settings()` where
#:     `monkeypatch` cannot reach.
_INVARIANTS = ("no sleep", "no asserted latency", "no race winner", "no hosted database")
