"""PRD-016 STORY-015: the `action_decisions` table, `action_audit.record()` and the reads.

Covers PRD-016 Sections 4 (Audit), 6.10, 6.12, F10, T10 and D8, AC 1-5 of the
story, plus the redaction the orchestrator decided (STORY-012/015 plans):
`target_preview` keeps an `http` URL's keys and replaces its query and
fragment values and any userinfo with `***`, and `arguments_preview` gets the
same treatment for every `http(s)://` URL inside it.

Every decision recorded here is a real STORY-014 `ActionDecision`, built by
`evaluate()`, never a hand-made stand-in.

Requesting `temp_db` / `uninitialized_db` makes these `db` tests: they run
against the libSQL dev server. If many of them error at fixture setup, restart
the container (`docker restart harness-libsql-dev`) before suspecting code.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import dataclasses
import json
from collections import Counter
from types import MappingProxyType

import pytest

from app.db import database
from app.db.database import (
    count_action_decisions,
    get_connection,
    get_user,
    init_db,
    insert_action_decisions,
    insert_user,
    list_action_decisions,
)
from app.db.errors import IntegrityError, StorageError
from app.db.models import (
    ACTION_DECISION_VALUES,
    CREATE_AUDIT_LOGS_DEDUP_INDEX,
    CREATE_AUDIT_LOGS_TABLE,
    CREATE_CHAT_MESSAGES_SESSION_INDEX,
    CREATE_CHAT_MESSAGES_TABLE,
    CREATE_CHAT_SESSIONS_TABLE,
    CREATE_CHAT_SESSIONS_USER_INDEX,
    CREATE_USAGE_DAILY_TABLE,
    CREATE_USERS_TABLE,
    CREATE_USERS_TOKEN_HASH_INDEX,
    ActionDecisionRow,
    User,
)
from app.services import action_audit, authz
from app.services.action_adapters import ToolCall
from app.services.action_audit import _redact_url, record
from app.services.action_classifiers import DECISIONS
from app.services.action_config import BUILT_IN_POLICY, Rule
from app.services.action_policy import evaluate
from app.services.duplicate_checker import hash_prompt
from app.services.identity import Identity

USER = Identity("u", "user")
OTHER = Identity("v", "user")
DBA = Identity("d", "dba")

# PRD Section 6.10 in order, plus `reason` after `rule` (orchestrator decision,
# STORY-014 plan; PRD 6.10 amended). (name, notnull)
_COLUMNS = [
    ("id", 0),
    ("timestamp", 1),
    ("audit_id", 0),
    ("session_id", 0),
    ("user_id", 1),
    ("role", 1),
    ("tool_call_id", 1),
    ("tool_name", 1),
    ("operation_kind", 0),
    ("target_preview", 0),
    ("arguments_hash", 1),
    ("arguments_preview", 0),
    ("decision", 1),
    ("rule", 1),
    ("reason", 1),
    ("granted_by", 0),
    ("classifications", 1),
    ("policy_digest", 1),
    ("write_id", 0),  # PRD-018 STORY-004 (D4): "<batch>:<index>", nullable
]

# `make release` is `shell.unlisted`; flag it, so the batch has all three outcomes.
_POLICY = dataclasses.replace(
    BUILT_IN_POLICY,
    rules=MappingProxyType(
        {**BUILT_IN_POLICY.rules, "shell.unlisted": Rule("flag", "action:shell:exec")}
    ),
)


def _call(name, arguments, id="c1"):
    if not isinstance(arguments, str):
        arguments = json.dumps(arguments)
    return ToolCall(id, name, arguments)


def _decide(name, arguments, identity=USER, id="c1"):
    return evaluate(_call(name, arguments, id), identity, _POLICY)


def _three():
    """allow, flag, deny -- in that order."""
    ds = [
        _decide("query", {"sql": "SELECT 1"}, id="c1"),
        _decide("bash", {"command": "make release"}, id="c2"),
        _decide("query", {"sql": "DROP TABLE users"}, id="c3"),
    ]
    assert [d.decision for d in ds] == ["allow", "flag", "deny"]
    return ds


def _rows_by_id():
    with get_connection() as conn:
        return {r["id"]: r for r in conn.execute("SELECT * FROM action_decisions")}


def _count():
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM action_decisions").fetchone()["n"]


class _Recording:
    """A proxy over one connection that records the SQL passed through
    (the `tests/test_usage_storage.py` idiom); `fail_on` raises `StorageError`
    on the n-th `INSERT INTO action_decisions`."""

    def __init__(self, inner, sessions, fail_on=None):
        self._inner = inner
        self._fail_on = fail_on
        self.statements: list[str] = []
        sessions.append(self.statements)

    def execute(self, sql, *args):
        self.statements.append(sql)
        if self._fail_on is not None and "INSERT INTO action_decisions" in sql:
            inserts = sum("INSERT INTO action_decisions" in s for s in self.statements)
            if inserts == self._fail_on:
                raise StorageError("injected failure")
        return self._inner.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def __enter__(self):
        self._inner.__enter__()
        return self

    def __exit__(self, *exc):
        return self._inner.__exit__(*exc)


@pytest.fixture
def sessions(monkeypatch):
    recorded: list[list[str]] = []
    real = database.get_connection
    monkeypatch.setattr(database, "get_connection", lambda: _Recording(real(), recorded))
    return recorded


# --- G1 (AC 1): the schema ------------------------------------------------


def test_init_db_creates_action_decisions_with_the_prd_columns(temp_db):
    with get_connection() as conn:
        info = list(conn.execute("PRAGMA table_info(action_decisions)"))
    assert [(r["name"], r["notnull"]) for r in info] == _COLUMNS
    assert [r["name"] for r in info if r["pk"]] == ["id"]


def test_init_db_creates_both_action_decisions_indexes(temp_db):
    with get_connection() as conn:
        user_ts = [r["name"] for r in conn.execute("PRAGMA index_info(idx_action_decisions_user_ts)")]
        audit = [r["name"] for r in conn.execute("PRAGMA index_info(idx_action_decisions_audit)")]
    assert user_ts == ["user_id", "timestamp"]
    assert audit == ["audit_id"]


def test_a_second_init_db_keeps_recorded_rows(temp_db):
    [row_id] = record([_decide("query", {"sql": "SELECT 1"})], USER)

    init_db()

    assert list(_rows_by_id()) == [row_id]


def test_init_db_adds_action_decisions_to_a_pre_prd_database_and_alters_nothing(
    uninitialized_db, db_connect
):
    legacy = db_connect(uninitialized_db)
    for statement in (
        CREATE_AUDIT_LOGS_TABLE,
        CREATE_AUDIT_LOGS_DEDUP_INDEX,
        CREATE_USERS_TABLE,
        CREATE_USERS_TOKEN_HASH_INDEX,
        CREATE_CHAT_SESSIONS_TABLE,
        CREATE_CHAT_SESSIONS_USER_INDEX,
        CREATE_CHAT_MESSAGES_TABLE,
        CREATE_CHAT_MESSAGES_SESSION_INDEX,
        CREATE_USAGE_DAILY_TABLE,
    ):
        legacy.execute(statement)
    legacy.execute(
        "INSERT INTO audit_logs (timestamp, user_id, prompt_hash) VALUES (?, ?, ?)",
        ("2026-01-01T00:00:00Z", "dana", "h"),
    )
    legacy.commit()
    insert_user(User(user_id="dana", role="user", token_hash="hash-dana"))

    def schema():
        with get_connection() as conn:
            return {
                (r["type"], r["name"]): r["sql"]
                for r in conn.execute("SELECT type, name, sql FROM sqlite_master")
            }

    before = schema()
    init_db()
    after = schema()

    added = set(after) - set(before)
    assert added == {
        ("table", "action_decisions"),
        ("index", "idx_action_decisions_user_ts"),
        ("index", "idx_action_decisions_audit"),
        # PRD-018 STORY-004 (D4): the write_id indexes are new. The legacy
        # audit_logs here is built from the current CREATE, so its column is
        # already there and nothing is ALTERed -- only its index is created.
        ("index", "idx_action_decisions_write_id"),
        ("index", "idx_audit_logs_write_id"),
    }
    assert {key: after[key] for key in before} == before  # byte-identical
    assert get_user("dana").role == "user"
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()["n"] == 1


def test_init_db_creates_action_decisions_inside_the_one_bootstrap_session(
    uninitialized_db, sessions
):
    init_db()

    holding = [s for s in sessions if any("action_decisions" in sql for sql in s)]
    assert len(holding) == 1
    assert any("CREATE TABLE IF NOT EXISTS audit_logs" in sql for sql in holding[0])
    # PRD-018 STORY-004 (D4): table + PRAGMA table_info (the added-columns pass)
    # + 3 indexes (user_ts, audit, write_id).
    assert sum("action_decisions" in sql for sql in holding[0]) == 5


def test_the_db_decision_vocabulary_mirrors_the_classifiers():
    assert ACTION_DECISION_VALUES == DECISIONS


# --- G2 (AC 2): recording a batch -----------------------------------------


def test_record_writes_three_rows_with_the_identity_and_ids_in_order(temp_db):
    ds = _three()

    ids = record(ds, USER, audit_id=7, session_id="s1")

    assert len(ids) == 3 and ids == sorted(ids) and len(set(ids)) == 3
    rows = _rows_by_id()
    assert sorted(rows) == ids
    for row_id, d in zip(ids, ds):
        row = rows[row_id]
        assert row["audit_id"] == 7
        assert row["session_id"] == "s1"
        assert (row["user_id"], row["role"]) == ("u", "user")
        assert row["tool_call_id"] == d.tool_call_id
        assert row["tool_name"] == d.tool_name
        assert row["operation_kind"] == d.operation.kind
        assert row["decision"] == d.decision
        assert row["rule"] == d.rule
        assert row["reason"] == d.reason
        assert d.granted_by is None and row["granted_by"] is None
        assert row["policy_digest"] == d.policy_digest
    assert len({rows[i]["timestamp"] for i in ids}) == 1  # one timestamp per call


def test_record_writes_the_batch_in_one_session(temp_db, sessions):
    record(_three(), USER, audit_id=7, session_id="s1")

    holding = [s for s in sessions if any("INSERT INTO action_decisions" in sql for sql in s)]
    assert len(holding) == 1
    assert sum("INSERT INTO action_decisions" in sql for sql in holding[0]) == 3


def test_record_stores_the_permission_that_lifted_the_rule(temp_db, monkeypatch):
    monkeypatch.setattr(
        authz,
        "ROLE_PERMISSIONS",
        {**authz.ROLE_PERMISSIONS, "dba": {"query:submit", "action:sql:write"}},
    )
    d = evaluate(_call("query", {"sql": "DELETE FROM t WHERE id = 3"}), DBA)
    assert (d.decision, d.rule) == ("allow", "sql.write")

    [row_id] = record([d], DBA)

    row = _rows_by_id()[row_id]
    assert row["granted_by"] == "action:sql:write"
    assert (row["user_id"], row["role"]) == ("d", "dba")


# --- G3 (AC 3): hash, previews, classifications, redaction -----------------


def test_long_arguments_store_the_full_hash_and_500_character_previews(temp_db):
    d = _decide("bash", {"command": "echo " + "a" * 600})
    assert len(d.arguments) > 500 and len(d.operation.target) > 500

    [row_id] = record([d], USER)

    row = _rows_by_id()[row_id]
    assert row["arguments_hash"] == hash_prompt(d.arguments)
    assert row["arguments_preview"] == d.arguments[:500]
    assert row["target_preview"] == d.operation.target[:500]
    assert len(row["arguments_preview"]) == len(row["target_preview"]) == 500


def test_classifications_are_a_json_array_of_rule_kind_detail_in_order(temp_db):
    d = _decide("bash", {"command": "npm test && rm -rf build"})
    assert len(d.classifications) == 2

    [row_id] = record([d], USER)

    stored = json.loads(_rows_by_id()[row_id]["classifications"])
    assert stored == [
        {"rule": c.rule, "kind": c.operation.kind, "detail": c.detail}
        for c in d.classifications
    ]
    assert [c["rule"] for c in stored] == ["shell.unlisted", "shell.destructive"]


def test_an_unknown_tool_stores_no_kind_and_no_target(temp_db):
    d = _decide("mystery", {})
    assert d.rule == "tool.unknown"

    [row_id] = record([d], USER)

    row = _rows_by_id()[row_id]
    assert row["operation_kind"] is None
    assert row["target_preview"] is None
    assert json.loads(row["classifications"]) == [
        {"rule": "tool.unknown", "kind": None, "detail": "mystery"}
    ]


def test_http_target_and_arguments_preview_redact_query_and_fragment_values(temp_db):
    """Orchestrator decisions (STORY-012/015): keys kept, values `***`, in both
    previews; the hash stays over the raw string."""
    url = "https://api.example.com/v1?token=abc&q=1#access_token=zzz"
    d = _decide("webfetch", {"url": url})
    assert d.operation.kind == "http" and d.operation.target == url

    [row_id] = record([d], USER)

    row = _rows_by_id()[row_id]
    redacted = "https://api.example.com/v1?token=***&q=***#access_token=***"
    assert row["target_preview"] == redacted
    assert row["arguments_preview"] == json.dumps({"url": redacted})
    assert row["arguments_hash"] == hash_prompt(d.arguments)
    for secret in ("abc", "zzz"):
        assert secret not in row["target_preview"]
        assert secret not in row["arguments_preview"]


def test_a_query_token_in_shell_arguments_appears_in_neither_preview(temp_db):
    d = _decide("bash", {"command": "curl https://api.example.com/v1?token=SECRET"})

    [row_id] = record([d], USER)

    row = _rows_by_id()[row_id]
    assert "SECRET" not in row["target_preview"]
    assert "SECRET" not in row["arguments_preview"]
    assert row["arguments_preview"] == json.dumps(
        {"command": "curl https://api.example.com/v1?token=***"}
    )
    assert row["arguments_hash"] == hash_prompt(d.arguments)


def test_a_shell_target_with_a_url_is_redacted_too(temp_db):
    """A non-`http` target (the whole command) gets the URL scan, so the
    stored target never shows what the arguments preview hides."""
    d = _decide("bash", {"command": "make https://x.example/a?token=SECRET"})
    assert d.operation.kind == "shell"

    [row_id] = record([d], USER)

    row = _rows_by_id()[row_id]
    assert row["target_preview"] == "make https://x.example/a?token=***"
    assert "SECRET" not in row["arguments_preview"]


def test_json_escaped_urls_in_arguments_are_redacted():
    raw = '{"url":"https:\\/\\/u:p@x\\/a?token=SECRET","c":"curl \\"https://y?k=SECRET\\""}'
    assert action_audit._redact_urls_in(raw) == (
        '{"url":"https:\\/\\/***@x\\/a?token=***","c":"curl \\"https://y?k=***\\""}'
    )


def test_arguments_preview_is_raw_apart_from_urls(temp_db):
    """T10: the preview is the raw string; only URLs are redacted."""
    d = _decide("query", {"sql": "SELECT 'password=hunter2'"})

    [row_id] = record([d], USER)

    assert _rows_by_id()[row_id]["arguments_preview"] == d.arguments


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://x.example/a", "https://x.example/a"),
        ("https://x.example/a?a", "https://x.example/a?***"),
        ("https://x.example/a?a=", "https://x.example/a?a="),
        ("https://x.example/a?a=1&&b=2", "https://x.example/a?a=***&&b=***"),
        ("https://x.example/a#token", "https://x.example/a#***"),
        ("https://x.example/a#k=v", "https://x.example/a#k=***"),
        ("https://x.example/a?", "https://x.example/a?"),
        ("https://x.example/a?#", "https://x.example/a?#"),
        ("http://[bad/x?k=v", "http://[bad/x?k=***"),
        ("https://user:tok@evil.com/p", "https://***@evil.com/p"),
        ("https://allowed.com@evil.com", "https://***@evil.com"),
    ],
)
def test_redact_url(url, expected):
    assert _redact_url(url) == expected


def test_a_long_url_is_redacted_before_it_is_cut(temp_db):
    url = "https://x.example/" + "p" * 480 + "?token=" + "S" * 100
    d = _decide("webfetch", {"url": url})

    [row_id] = record([d], USER)

    row = _rows_by_id()[row_id]
    assert row["target_preview"] == _redact_url(url)[:500]
    assert len(row["target_preview"]) == 500
    assert "S" not in row["target_preview"].split("?", 1)[1]
    assert "SSS" not in row["arguments_preview"]


# --- G4 (AC 4): NULLs and atomicity ---------------------------------------


def test_omitted_audit_and_session_ids_store_null(temp_db):
    ids = record(_three(), USER)

    rows = _rows_by_id()
    assert all(rows[i]["audit_id"] is None and rows[i]["session_id"] is None for i in ids)


def test_a_constraint_failure_midway_writes_no_row_of_the_batch(temp_db):
    good = action_audit._row_of(_three()[0], USER, "2026-11-15T00:00:00Z", None, None)
    bad = dataclasses.replace(good, decision=None)

    with pytest.raises(IntegrityError):
        insert_action_decisions([good, bad, good])

    assert _count() == 0


def test_a_storage_failure_midway_through_record_writes_no_row(temp_db, monkeypatch):
    recorded: list[list[str]] = []
    real = database.get_connection
    monkeypatch.setattr(
        database, "get_connection", lambda: _Recording(real(), recorded, fail_on=2)
    )

    with pytest.raises(StorageError):
        record(_three(), USER, audit_id=7, session_id="s1")

    monkeypatch.setattr(database, "get_connection", real)
    assert _count() == 0


def test_recording_nothing_opens_no_session(temp_db, sessions):
    assert record([], USER) == []
    assert insert_action_decisions([]) == []
    assert sessions == []


# --- G5 (AC 5): reads -----------------------------------------------------


def _seed_two_users():
    """u: allow, flag, deny; v: deny, allow. Returns every id, in insertion order."""
    ids = record(_three(), USER, audit_id=1)
    ids += record(
        [
            _decide("query", {"sql": "DROP TABLE t"}, OTHER, id="c4"),
            _decide("query", {"sql": "SELECT 2"}, OTHER, id="c5"),
        ],
        OTHER,
        audit_id=2,
    )
    return ids


def test_list_returns_every_row_newest_first_by_id(temp_db):
    ids = _seed_two_users()

    rows = list_action_decisions(100)

    assert [r.id for r in rows] == list(reversed(ids))
    # One batch shares one timestamp, so the order can only come from id.
    assert len({r.timestamp for r in rows[-3:]}) == 1


def test_list_filters_by_user_and_by_decision(temp_db):
    _seed_two_users()

    assert {r.user_id for r in list_action_decisions(100, user_id="u")} == {"u"}
    assert len(list_action_decisions(100, user_id="u")) == 3
    denies = list_action_decisions(100, decision="deny")
    assert [r.decision for r in denies] == ["deny", "deny"]
    both = list_action_decisions(100, user_id="v", decision="deny")
    assert [(r.user_id, r.decision, r.tool_call_id) for r in both] == [("v", "deny", "c4")]
    assert list_action_decisions(100, decision="nonsense") == []


def test_list_filters_by_audit_id(temp_db):
    """PRD-017 STORY-013 (Section 10): one request's decisions, ANDed with the rest."""
    ids = _seed_two_users()

    assert [r.id for r in list_action_decisions(100, audit_id=1)] == list(
        reversed(ids[:3])
    )
    only = list_action_decisions(100, audit_id=2, decision="deny")
    assert [r.tool_call_id for r in only] == ["c4"]
    assert list_action_decisions(100, user_id="u", audit_id=2) == []
    assert list_action_decisions(100, audit_id=999) == []


def test_list_limit_returns_the_newest(temp_db):
    ids = _seed_two_users()

    [newest] = list_action_decisions(1)

    assert newest.id == ids[-1]


def test_list_returns_frozen_rows_with_every_column(temp_db):
    ids = record(_three(), USER, audit_id=7, session_id="s1")

    rows = list_action_decisions(100)

    assert all(isinstance(r, ActionDecisionRow) for r in rows)
    raw = _rows_by_id()
    for r in rows:
        assert dataclasses.asdict(r) == {name: raw[r.id][name] for name, _ in _COLUMNS}
    with pytest.raises(dataclasses.FrozenInstanceError):
        rows[0].decision = "allow"
    assert sorted(r.id for r in rows) == ids


def test_count_matches_the_tally_per_decision(temp_db):
    _seed_two_users()

    expected = Counter(r.decision for r in list_action_decisions(100))
    assert count_action_decisions() == {d: expected.get(d, 0) for d in ACTION_DECISION_VALUES}
    assert count_action_decisions() == {"allow": 2, "flag": 1, "deny": 2}


def test_count_on_an_empty_table_is_all_zeros(temp_db):
    assert count_action_decisions() == {"allow": 0, "flag": 0, "deny": 0}
