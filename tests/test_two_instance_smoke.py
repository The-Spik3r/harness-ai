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

**It is now two epics' exit criterion.** PRD-007 STORY-016 wrote it; PRD-008
STORY-021 extended it with the session half -- a transcript written on one
instance and read back whole on the other, a delete that lands on the instance
that did not create the row, and a `session_id` that is refused with a 403 on
the instance that never saw it created. That it could absorb a second epic
without a second harness is not luck: two processes are already two clients, so
a read on B is exactly the "separate, freshly constructed client, not the
writing one" that PRD-007 STORY-006 named as Risk 1's mitigation. The reason it
gave -- "a lost `insert_audit_log()` is invisible until someone reads an empty
audit trail" -- describes a lost transcript row without a word changed.

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

# The auto-title rule, asserted against the module that owns it rather than
# restated here -- the same reason the child imports it (see _INSTANCE_SCRIPT).
from chat_ui.chat_ui.formatting import derive_title  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The two instances. Names travel into the children and come back in every
#: reply, so an assertion can say *which* instance failed -- which for AC 5
#: ("both reject them") is the whole point.
_INSTANCE_NAMES = ("instance-a", "instance-b")

_USER_ID = "smoke@empresa.com"
_USER_TOKEN = "two-instance-smoke-token"

#: A second identity, for STORY-021 AC 7. Written by the test that needs it
#: rather than by a fixture: the story asks for no second harness, and the one
#: test that wants a foreign session needs two lines, not a shared surface.
_OTHER_USER_ID = "someone-else@empresa.com"
_OTHER_TOKEN = "two-instance-smoke-other-token"

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
import dataclasses, json, os, sys, time

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
    from app.db.models import AuditLog, StoredMessage
    from app.main import app
    from app.services import authz, chat_sessions
    from app.services.identity import Identity
    from app.services.openrouter_client import OpenRouterResult

    # The auto-title rule, from the module that owns it. `chat_sessions.create`
    # takes its deriver as a parameter and refuses to own the rule
    # (app/services/chat_sessions.py:130), and the production caller that
    # supplies it is chat_ui/chat_ui/state.py:995 -- so supplying the same
    # function here is the honest reproduction, where a lambda would be a second
    # title rule to drift. The import costs nothing and pulls in no Reflex:
    # chat_ui/chat_ui/__init__.py is empty and formatting.py imports only the
    # standard library and .copy.
    from chat_ui.chat_ui.formatting import derive_title

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
    # The field is added only when the command carries one, and the omission
    # stays a genuine omission: app/routers/query.py:68's `is not None` guard is
    # what keeps owns() from issuing a statement for the requests that name no
    # session, and test_round_trip_cost_is_measured_and_reported asserts exactly
    # three statements on that path. Sending an explicit None would not change
    # that count, but building the body conditionally keeps the two call shapes
    # visibly distinct.
    body = {"prompt": command["prompt"], "model": command.get("model", "gpt-4")}
    if command.get("session_id") is not None:
        body["session_id"] = command["session_id"]

    def work():
        return client.post(
            "/query",
            json=body,
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
                "session_id": row.session_id,
                "error_message": row.error_message,
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


def _identity(command):
    '''An Identity the way resolve() would have produced one.

    Constructed directly, as tests/test_chat_sessions.py:1000 does: what the
    session handlers below are about is what the service does with
    identity.user_id, and going through resolve() would make each of them depend
    on credential verification -- which do_authenticate already covers, through
    the real dependency chain, for the tests that are about it.
    '''
    return Identity(user_id=command["user_id"], role=command.get("role", "user"))


# Every session command goes through app/services/chat_sessions.py and never
# through database.py directly. That is the rule tests/test_chat_sessions.py
# enforces across app/, and the child holds itself to it so that this file
# exercises the ownership rule rather than routing around it -- an instance that
# called the store directly would prove the database persisted a row and say
# nothing about whether the deployed call path does.
def do_create_session(command):
    return {
        "session_id": chat_sessions.create(
            _identity(command), command["prompt"], derive_title
        )
    }


def do_append(command):
    return {
        "row_id": chat_sessions.append_message(
            _identity(command),
            command["session_id"],
            StoredMessage(**command["message"]),
        )
    }


def do_transcript(command):
    return {
        "messages": [
            dataclasses.asdict(row)
            for row in chat_sessions.messages_for(
                _identity(command), command["session_id"]
            )
        ]
    }


def do_sessions(command):
    return {
        "sessions": [
            dataclasses.asdict(row) for row in chat_sessions.list_for(_identity(command))
        ]
    }


def do_delete_session(command):
    return {
        "deleted": chat_sessions.delete(_identity(command), command["session_id"])
    }


def do_transcript_row_counts(command):
    '''Both transcript tables counted raw, unscoped by owner.

    `do_transcript` above answers "is it gone for its owner", which a delete
    that removed the session row and orphaned its messages would also satisfy --
    list_chat_messages joins through the session. AC 3 says "gone from both
    tables", so the tables are what this reads.
    '''
    with database.get_connection() as conn:
        return {
            "sessions": conn.execute(
                "SELECT COUNT(*) AS n FROM chat_sessions"
            ).fetchone()["n"],
            "messages": conn.execute(
                "SELECT COUNT(*) AS n FROM chat_messages"
            ).fetchone()["n"],
        }


def do_audit_count(command):
    return {"count": database.count_audit_logs()}


HANDLERS = {
    "init_db": lambda command: {"ok": database.init_db() is None},
    "schema": lambda command: schema(),
    "query": do_query,
    "authenticate": do_authenticate,
    "plant_audit_row": do_plant_audit_row,
    "rows": do_rows,
    "audit_ids": do_audit_ids,
    "console_load": do_console_load,
    "create_session": do_create_session,
    "append": do_append,
    "transcript": do_transcript,
    "sessions": do_sessions,
    "delete_session": do_delete_session,
    "transcript_row_counts": do_transcript_row_counts,
    "audit_count": do_audit_count,
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
        # to the invocation, which is the same triple README.md's *Running
        # Tests* section documents for the in-container suite. Named by section
        # rather than by line number: STORY-022 edited the README above it and
        # the old citation had already gone stale.
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
        # Four tables since PRD-008 STORY-003 taught init_db() to create the
        # transcript pair; it was ["audit_logs", "users"] before.
        assert schema["tables"] == [
            "audit_logs",
            "chat_messages",
            "chat_sessions",
            "users",
        ], instance.name
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
        assert schema["columns"]["chat_sessions"] == [
            "created_at",
            "session_id",
            "title",
            "updated_at",
            "user_id",
        ], instance.name
        # Containment, not the full fifteen: what this test is for is that two
        # instances converged on the *same* schema, and `schemas[0] ==
        # schemas[1]` below is what carries that. The exact chat_messages shape
        # is pinned against the DDL in
        # tests/test_db.py::test_chat_messages_table_matches_its_ddl, and a
        # second fifteen-name literal here would only be a copy to drift.
        assert {"id", "session_id", "kind", "content", "created_at"} <= set(
            schema["columns"]["chat_messages"]
        ), (instance.name, schema["columns"]["chat_messages"])

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
# PRD-008 STORY-021 -- one session, two instances
# --------------------------------------------------------------------------

#: The seven bubble kinds, each with every optional `StoredMessage` field set to
#: a distinct, non-default value.
#:
#: Defaults are what a field-by-field comparison cannot see through. A column
#: dropped on the wire and a column defaulting to `False` are the same
#: observation, so `pii_redacted` is `True` on every row here and no optional
#: field is left `None` -- which is what makes AC 2's "every field" mean every
#: field rather than every field that happened to differ from its default.
#:
#: `content` names its own index so a transcript returned out of order fails
#: with a legible message rather than a diff of seven similar dicts.
_TRANSCRIPT_KINDS = (
    "user",
    "assistant",
    "duplicate",
    "injection",
    "forbidden",
    "upstream_error",
    "internal_error",
)


def _transcript(session_id: str) -> list[dict]:
    return [
        {
            "session_id": session_id,
            "kind": kind,
            "content": f"message {index} of kind {kind}",
            "prompt": f"the prompt behind message {index}",
            "model_used": "gpt-4",
            "tokens_used": 40 + index,
            "audit_id": 900 + index,
            "pii_redacted": True,
            "pii_entities": "EMAIL_ADDRESS,PERSON",
            "pattern": "ignore previous instructions",
            "required_permission": "query:submit",
            "first_query_at": "2026-09-04T10:00:00Z",
            "detail": f"the detail line for message {index}",
        }
        for index, kind in enumerate(_TRANSCRIPT_KINDS)
    ]


#: The two fields the store stamps rather than the caller supplying
#: (app/db/database.py:1614). Everything else must survive the round trip
#: unchanged.
_STORE_ASSIGNED = ("created_at", "id")


def test_a_transcript_written_on_one_instance_reads_back_whole_on_the_other(
    instances, smoke_user
):
    """AC 1 and AC 2, and PRD Section 5 story 6.

    **Instance B is the "separate, freshly constructed client".** PRD-007
    STORY-006 required a durable write to be verified "through a separate,
    freshly constructed client, not through the writing one", and named the
    reason: "a lost `insert_audit_log()` is invisible until someone reads an
    empty audit trail". A lost transcript row has the same shape and the same
    invisibility. The two children each build their own `_shared_client()` in
    their own interpreter (`app/db/database.py:72`), so nothing A cached can
    serve B's read -- a stronger instrument than the requirement asks for, and
    the reason this story extends this file rather than starting a harness.
    """
    instance_a, instance_b = instances

    created = instance_a.call(
        cmd="create_session", user_id=_USER_ID, prompt="the quarterly close, in full"
    )
    session_id = created["session_id"]
    assert session_id, created

    written = _transcript(session_id)
    for message in written:
        appended = instance_a.call(
            cmd="append", user_id=_USER_ID, session_id=session_id, message=message
        )
        assert isinstance(appended["row_id"], int), (instance_a.name, appended)

    # The session row itself, read on the instance that did not create it.
    listed = instance_b.call(cmd="sessions", user_id=_USER_ID)["sessions"]
    assert [row["session_id"] for row in listed] == [session_id], (
        instance_b.name,
        listed,
    )
    assert listed[0]["title"] == derive_title("the quarterly close, in full"), listed[0]

    read_back = instance_b.call(
        cmd="transcript", user_id=_USER_ID, session_id=session_id
    )["messages"]

    assert len(read_back) == len(written), (instance_b.name, read_back)
    assert [row["kind"] for row in read_back] == list(_TRANSCRIPT_KINDS), (
        instance_b.name,
        [row["kind"] for row in read_back],
    )

    for expected, actual in zip(written, read_back):
        compared = {
            key: value for key, value in actual.items() if key not in _STORE_ASSIGNED
        }
        assert compared == expected, (instance_b.name, expected["kind"])

    # The ordering key has to exist for the order asserted above to be the
    # store's rather than a coincidence: `list_chat_messages` orders BY id.
    ids = [row["id"] for row in read_back]
    assert all(isinstance(value, int) for value in ids), ids
    assert ids == sorted(ids), ids
    assert len(set(ids)) == len(ids), ids
    for row in read_back:
        assert isinstance(row["created_at"], str) and row["created_at"], row


def test_a_session_deleted_on_one_instance_is_gone_from_both_tables_on_the_other(
    instances, smoke_user
):
    """AC 3. The delete lands on B; A is the one that asked for it back.

    The query first is not decoration. "`count_audit_logs()` is unchanged"
    across a delete is a comparison of zero with zero unless the audit trail
    holds a row that *names* the session, so one real send carries the
    `session_id` onto `audit_logs` before anything is deleted.
    """
    instance_a, instance_b = instances

    created = instance_a.call(
        cmd="create_session", user_id=_USER_ID, prompt="a chat that will be deleted"
    )
    session_id = created["session_id"]
    assert session_id, created

    answered = instance_a.call(
        cmd="query",
        prompt="what is the retention policy",
        token=smoke_user,
        session_id=session_id,
    )
    assert answered["status_code"] == 200, answered
    assert answered["body"]["status"] == "SUCCESS", answered["body"]

    for index in range(2):
        instance_a.call(
            cmd="append",
            user_id=_USER_ID,
            session_id=session_id,
            message={
                "session_id": session_id,
                "kind": "user",
                "content": f"a turn {index}",
            },
        )

    before = instance_a.call(cmd="audit_count")["count"]
    assert before == 1, before

    deleted = instance_b.call(
        cmd="delete_session", user_id=_USER_ID, session_id=session_id
    )
    assert deleted["deleted"] is True, (instance_b.name, deleted)

    # Read on A -- the instance that wrote it and never saw the delete.
    assert instance_a.call(cmd="sessions", user_id=_USER_ID)["sessions"] == [], (
        instance_a.name,
        "the deleted session is still listed",
    )
    assert (
        instance_a.call(cmd="transcript", user_id=_USER_ID, session_id=session_id)[
            "messages"
        ]
        == []
    ), (instance_a.name, "the deleted transcript still reads back")

    # The raw tables, unscoped by owner: `messages_for` above joins through the
    # session row, so a delete that removed the session and orphaned its
    # messages would satisfy it and leave rows behind.
    counts = instance_a.call(cmd="transcript_row_counts")
    assert counts["sessions"] == 0, (instance_a.name, counts)
    assert counts["messages"] == 0, (instance_a.name, counts)

    # PRD Section 9: "deleting a conversation deletes a conversation, it does
    # not edit the record of what was asked." The count alone would pass against
    # an implementation that deleted the audit row and inserted a tombstone, so
    # the surviving row is identified by the session it names.
    assert instance_a.call(cmd="audit_count")["count"] == before
    rows = instance_a.call(cmd="rows")["rows"]
    assert [row["session_id"] for row in rows] == [session_id], rows


def test_a_session_owned_by_another_user_is_refused_on_the_other_instance(
    instances, smoke_user
):
    """AC 7. The ownership check is not instance-local state.

    The second credential is written here rather than in a fixture: the story
    asks for no second harness, and one more identity is two lines. The parent
    writes it while both children are already running, exactly as `smoke_user`
    does.

    **The owner's 200 is what makes the 403 mean ownership.** Without it the
    refusal would be equally consistent with "instance B has never heard of that
    id" -- which is the opposite of what this story claims.
    """
    instance_a, instance_b = instances

    insert_user(
        User(
            user_id=_OTHER_USER_ID,
            role="user",
            token_hash=hash_token(_OTHER_TOKEN),
        )
    )

    created = instance_a.call(
        cmd="create_session", user_id=_USER_ID, prompt="a private conversation"
    )
    session_id = created["session_id"]
    assert session_id, created

    refused = instance_b.call(
        cmd="query",
        prompt="whose conversation is this",
        token=_OTHER_TOKEN,
        session_id=session_id,
    )
    assert refused["status_code"] == 403, (instance_b.name, refused)

    allowed = instance_b.call(
        cmd="query",
        prompt="my own question in my own conversation",
        token=smoke_user,
        session_id=session_id,
    )
    assert allowed["status_code"] == 200, (instance_b.name, allowed)
    assert allowed["body"]["status"] == "SUCCESS", allowed["body"]

    # The refusal is audited on the shared trail, so the row instance B wrote is
    # readable from instance A -- STORY-010's audited 403
    # (app/routers/query.py:71) closed across instances rather than in one
    # process. `session_id` is on the row because recording the attempt is the
    # whole evidentiary value of an audited refusal.
    rows = instance_a.call(cmd="rows")["rows"]
    refusals = [row for row in rows if row["success"] is False]
    assert len(refusals) == 1, rows
    assert refusals[0]["user_id"] == _OTHER_USER_ID, refusals[0]
    assert refusals[0]["session_id"] == session_id, refusals[0]
    assert refusals[0]["error_message"] == (
        "session_id does not belong to the authenticated identity"
    ), refusals[0]


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
#:  6. Every session command goes through `app/services/chat_sessions.py` and
#:     never through `database.py` directly, so the child exercises the
#:     ownership rule rather than routing around it. An instance that called the
#:     store would prove the database persisted a row and say nothing about
#:     whether the deployed call path does -- which is the whole claim.
_INVARIANTS = (
    "no sleep",
    "no asserted latency",
    "no race winner",
    "no hosted database",
    "no store call outside the service",
)
