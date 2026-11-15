"""PRD-016 STORY-008: the SQL classifier (Sections 6.3 SQL rows, 6.9, F2, Risk 6; D2).

Table-driven. The statements and the expected rules are transcribed from the
story's acceptance criteria and PRD Section 6.3 and written out as literals,
not derived from the module. Every case runs on the generic dialect unless a
dialect is given.

Also pinned here, because the classifier depends on it: what sqlglot 30.27.0
returns for a statement it cannot parse (`exp.Command`), the exact pin in
`requirements.txt`, the dialect list `action_config` validates against, and
that sqlglot's fallback warning does not log the statement.

Not covered here: the `ACTION_SQL_DIALECT` startup check
(`tests/test_action_config.py`) and how `evaluate()` combines the
classifications into a decision (STORY-014).
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import importlib
import inspect
import logging
import re
from pathlib import Path

import pytest
import sqlglot
from sqlglot import exp
from sqlglot.dialects.dialect import Dialect

import app.services.action_classifiers.sql as sql
from app.services.action_classifiers import RULE_IDS, Classification, Operation
from app.services.action_classifiers.sql import SQL_DIALECTS, classify_sql

REPO_ROOT = Path(__file__).resolve().parents[1]


def _rules(statement, dialect=None):
    return tuple(c.rule for c in classify_sql(statement, dialect))


def _details(statement, dialect=None):
    return tuple(c.detail for c in classify_sql(statement, dialect))


# --- AC 1: reads -------------------------------------------------------------

_READS = [
    # The story's three.
    ("SELECT * FROM users WHERE id = 1", None, "SELECT"),
    ("WITH x AS (SELECT 1) SELECT * FROM x", None, "SELECT"),
    # Generic sqlglot parses EXPLAIN as a Command; the carve-out re-reads the inner text.
    ("EXPLAIN SELECT 1", None, "EXPLAIN"),
    # Section 6.3's other reads.
    ("SELECT 1 UNION SELECT 2", None, "SELECT"),
    ("DESCRIBE t", None, "DESCRIBE"),
    ("SHOW TABLES", None, "SHOW"),
    ("SHOW TABLES", "mysql", "SHOW"),
    ("EXPLAIN SELECT 1", "mysql", "DESCRIBE"),
    # `;` inside a string or a comment does not split a statement.
    ("SELECT ';DROP TABLE t'", None, "SELECT"),
    ("SELECT 1 /* ; DROP TABLE t */", None, "SELECT"),
]


@pytest.mark.parametrize("statement,dialect,detail", _READS)
def test_reads(statement, dialect, detail):
    assert _rules(statement, dialect) == ("sql.read",)
    assert _details(statement, dialect) == (detail,)


# --- Transaction control (orchestrator decision 3 on STORY-008's plan) --------

_TRANSACTION_CONTROL = [
    ("BEGIN", None, "BEGIN"),
    ("BEGIN TRANSACTION", None, "BEGIN"),
    ("START TRANSACTION", None, "START TRANSACTION"),
    ("START TRANSACTION", "mysql", "BEGIN"),
    ("COMMIT", None, "COMMIT"),
    ("END", "postgres", "COMMIT"),
    ("ROLLBACK", None, "ROLLBACK"),
    ("ROLLBACK TO SAVEPOINT s", None, "ROLLBACK"),
    ("SAVEPOINT s", None, "SAVEPOINT"),
    ("RELEASE s", None, "RELEASE"),
    # tsql parses a bare BEGIN as Command('BEGIN').
    ("BEGIN", "tsql", "BEGIN"),
]


@pytest.mark.parametrize("statement,dialect,detail", _TRANSACTION_CONTROL)
def test_transaction_control_is_a_read(statement, dialect, detail):
    """BEGIN / START TRANSACTION / COMMIT / ROLLBACK / SAVEPOINT / RELEASE change no data on their own."""
    assert _rules(statement, dialect) == ("sql.read",)
    assert _details(statement, dialect) == (detail,)


def test_transaction_control_does_not_hide_what_it_wraps():
    assert _rules("BEGIN; DROP TABLE t; COMMIT") == ("sql.read", "sql.ddl", "sql.read")
    assert _rules("SAVEPOINT s; DELETE FROM t") == ("sql.read", "sql.unscoped_write")


@pytest.mark.parametrize(
    "statement,dialect",
    [
        # SET and USE stay unparsed: they can change privileges or targets.
        ("SET x = 1", None),
        ("SET search_path TO evil", "postgres"),
        ("SET ROLE admin", "postgres"),
        ("SET ROLE admin", "tsql"),
        ("USE db", None),
        # A tsql BEGIN with a body is a block, not a transaction.
        ("BEGIN DELETE FROM t END", "tsql"),
        # The alias carve-out is structural and narrow.
        ('"START" TRANSACTION', None),
        ("START SOMETHING", None),
        ("SAVEPOINT", None),
        ("foo bar", None),
        # Forms sqlglot 30.27.0 cannot parse: fail closed.
        ("RELEASE SAVEPOINT s", None),
        ("START TRANSACTION READ WRITE", None),
    ],
)
def test_set_use_and_unrecognised_transaction_forms_are_unparsed(statement, dialect):
    assert _rules(statement, dialect) == ("sql.unparsed",)


# --- AC 2: writes and unscoped writes ------------------------------------------

_WRITES = [
    ("INSERT INTO t VALUES (1)", None, "INSERT"),
    ("UPDATE t SET a = 1 WHERE id = 2", None, "UPDATE"),
    ("DELETE FROM t WHERE id = 3", None, "DELETE"),
    ("INSERT INTO t SELECT * FROM s", None, "INSERT"),
    ("INSERT INTO t VALUES (1) ON CONFLICT (id) DO UPDATE SET a = 2", "postgres", "INSERT"),
    (
        "MERGE INTO t USING s ON t.id = s.id WHEN MATCHED THEN UPDATE SET a = s.a "
        "WHEN NOT MATCHED THEN INSERT (id) VALUES (s.id)",
        None,
        "MERGE",
    ),
    # The simplifier drops the tautology and keeps the real condition.
    ("DELETE FROM t WHERE 1=1 AND id = 3", None, "DELETE"),
]

_UNSCOPED_WRITES = [
    ("DELETE FROM t", None, "DELETE"),
    ("UPDATE t SET a = 1", None, "UPDATE"),
    ("DELETE FROM t WHERE 1=1", None, "DELETE"),
    ("DELETE FROM t WHERE TRUE", None, "DELETE"),
    ("DELETE FROM t WHERE 'a'='a'", None, "DELETE"),
    ("DELETE FROM t WHERE NOT FALSE", None, "DELETE"),
    ("UPDATE t SET a = 1 WHERE 2 > 1", None, "UPDATE"),
    ("DELETE FROM t WHERE 1=1 OR id = 3", None, "DELETE"),
]


@pytest.mark.parametrize("statement,dialect,detail", _WRITES)
def test_writes(statement, dialect, detail):
    assert _rules(statement, dialect) == ("sql.write",)
    assert _details(statement, dialect) == (detail,)


@pytest.mark.parametrize("statement,dialect,detail", _UNSCOPED_WRITES)
def test_unscoped_writes(statement, dialect, detail):
    assert _rules(statement, dialect) == ("sql.unscoped_write",)
    assert _details(statement, dialect) == (detail,)


# --- AC 3: DDL and DCL -------------------------------------------------------

_DDL = [
    ("DROP TABLE users", None, "DROP"),
    ("TRUNCATE t", None, "TRUNCATE"),
    ("ALTER TABLE t ADD c INT", None, "ALTER"),
    ("CREATE TABLE t (a INT)", None, "CREATE"),
    ("TRUNCATE TABLE t", None, "TRUNCATE"),
    ("ALTER TABLE t RENAME TO u", None, "ALTER"),
    ("CREATE INDEX i ON t (a)", None, "CREATE"),
    ("CREATE VIEW v AS SELECT 1", None, "CREATE"),
    ("COMMENT ON TABLE t IS 'x'", None, "COMMENT"),
    # SELECT ... INTO creates a table.
    ("SELECT * INTO n FROM t", None, "SELECT INTO"),
    # Comments between whole keywords are stripped by the tokenizer.
    ("DROP/**/TABLE t", None, "DROP"),
    ("/* c */ DROP TABLE t", None, "DROP"),
]

_DCL = [
    ("GRANT ALL ON t TO u", None, "GRANT"),
    ("REVOKE ALL ON t FROM u", None, "REVOKE"),
    ("DROP ROLE r", "snowflake", "DROP ROLE"),
]


@pytest.mark.parametrize("statement,dialect,detail", _DDL)
def test_ddl(statement, dialect, detail):
    assert _rules(statement, dialect) == ("sql.ddl",)
    assert _details(statement, dialect) == (detail,)


@pytest.mark.parametrize("statement,dialect,detail", _DCL)
def test_dcl(statement, dialect, detail):
    assert _rules(statement, dialect) == ("sql.dcl",)
    assert _details(statement, dialect) == (detail,)


# --- AC 4: multi-statement, unparsed, never raises -------------------------


def test_multi_statement_in_order():
    result = classify_sql("SELECT 1; DROP TABLE users", None)
    assert tuple(c.rule for c in result) == ("sql.read", "sql.ddl")
    assert tuple(c.detail for c in result) == ("SELECT", "DROP")


def test_trailing_semicolon_and_comment_are_skipped():
    assert _rules("SELECT * FROM t; -- trailing") == ("sql.read",)


_UNPARSED = [
    ("DR/**/OP TABLE t", None, "DR/**/OP"),
    ("SELECT FROM WHERE", None, "SELECT"),
    ("VACUUM", None, "VACUUM"),
    ("CALL p()", None, "CALL"),
    # Section 6.3 lists these under ddl / dcl; sqlglot returns Command, so
    # unparsed: still deny, and not grantable (STORY-008 report, deviation).
    ("CREATE USER bob", None, "CREATE"),
    ("CREATE ROLE r", None, "CREATE"),
    ("GRANT r TO u", None, "GRANT"),
    ("RENAME TABLE t TO u", None, "RENAME"),
    ("COPY t FROM '/etc/passwd'", None, "COPY"),
    ("ATTACH DATABASE 'x' AS y", None, "ATTACH"),
    # EXPLAIN ANALYZE executes the statement.
    ("EXPLAIN ANALYZE DELETE FROM t", None, "EXPLAIN"),
    ("EXPLAIN", None, "EXPLAIN"),
    ("EXPLAIN EXPLAIN SELECT 1", None, "EXPLAIN"),
    ("", None, ""),
    ("   ", None, ""),
    (";", None, ""),
    ("-- only a comment", None, ""),
]


@pytest.mark.parametrize("statement,dialect,detail", _UNPARSED)
def test_unparsed(statement, dialect, detail):
    assert _rules(statement, dialect) == ("sql.unparsed",)
    assert _details(statement, dialect) == (detail,)


def test_a_command_is_unparsed_whatever_sqlglot_says():
    """PRD-016 Risk 6: pins the library behaviour this story depends on."""
    assert isinstance(sqlglot.parse_one("VACUUM"), exp.Command)
    assert _rules("VACUUM") == ("sql.unparsed",)


def test_an_unparseable_explain_does_not_swallow_its_neighbours():
    assert _rules("SELECT 1; EXPLAIN ANALYZE DELETE FROM t") == ("sql.read", "sql.unparsed")


def test_embedded_modifying_cte_is_not_a_read():
    """Risk 6, "mis-parses into a safer type": a data-modifying CTE parses as a Select."""
    statement = "WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d"
    assert isinstance(sqlglot.parse_one(statement, dialect="postgres"), exp.Select)
    assert _rules(statement, "postgres") == ("sql.read", "sql.unscoped_write")


def test_explain_of_a_write_is_the_write():
    assert _rules("EXPLAIN DELETE FROM t") == ("sql.unscoped_write",)


_NEVER_RAISES = [
    ("SELECT " + "(" * 5000 + "1" + ")" * 5000, None),
    ("SELECT 1", "nosuchdb"),
    (None, None),
    (b"SELECT 1", None),
]


@pytest.mark.parametrize("statement,dialect", _NEVER_RAISES)
def test_never_raises(statement, dialect):
    result = classify_sql(statement, dialect)
    assert tuple(c.rule for c in result) == ("sql.unparsed",)


def test_never_raises_when_the_simplifier_fails(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("simplifier bug")

    monkeypatch.setattr(sql, "simplify", _boom)
    result = classify_sql("DELETE FROM t WHERE id = 3", None)
    assert result == (Classification("sql.unparsed", Operation("sql", "DELETE FROM t WHERE id = 3", ""), "DELETE"),)


# --- Every output is a well-formed SQL classification -------------------------

_ALL = (
    _READS
    + _TRANSACTION_CONTROL
    + _WRITES
    + _UNSCOPED_WRITES
    + _DDL
    + _DCL
    + _UNPARSED
    + [(s, d, None) for s, d in _NEVER_RAISES]
)


@pytest.mark.parametrize("statement,dialect,_detail", _ALL)
def test_every_rule_produced_is_a_sql_rule(statement, dialect, _detail):
    result = classify_sql(statement, dialect, source_tool="sqlite_query")
    assert isinstance(result, tuple) and result
    target = statement if isinstance(statement, str) else ""
    for classification in result:
        assert classification.rule in RULE_IDS
        assert classification.rule.startswith("sql.")
        assert classification.operation == Operation("sql", target, "sqlite_query")
        assert isinstance(classification.detail, str)
        assert len(classification.detail) <= 32


def test_source_tool_defaults_to_empty():
    (classification,) = classify_sql("SELECT 1", None)
    assert classification.operation == Operation("sql", "SELECT 1", "")


# --- The dialect list action_config validates against ------------------------


def test_sql_dialects_are_what_sqlglot_parses():
    assert "postgres" in SQL_DIALECTS
    assert "mysql" in SQL_DIALECTS
    assert "sqlite" in SQL_DIALECTS
    assert "" not in SQL_DIALECTS
    assert list(SQL_DIALECTS) == sorted(SQL_DIALECTS)
    for name in SQL_DIALECTS:
        Dialect.get_or_raise(name)
        # `dax` and `prql` are registered but are not SQL: every statement is
        # unparsed under them, which fails closed.
        expected = ("sql.unparsed",) if name in {"dax", "prql"} else ("sql.read",)
        assert _rules("SELECT 1", name) == expected, name


# --- sqlglot's log line --------------------------------------------------------


def test_sqlglot_fallback_warning_does_not_log_the_statement(caplog):
    caplog.set_level(logging.DEBUG)
    assert _rules("VACUUM secret_marker_123") == ("sql.unparsed",)
    assert "secret_marker_123" not in caplog.text


def test_log_filter_does_not_stack_on_reload():
    importlib.reload(sql)
    importlib.reload(sql)
    filters = [f for f in logging.getLogger("sqlglot").filters if type(f).__name__ == "_DropCommandFallback"]
    assert len(filters) == 1


def test_log_filter_drops_only_the_fallback_warning():
    log_filter = sql._DropCommandFallback()

    def _record(message):
        return logging.LogRecord("sqlglot", logging.WARNING, __file__, 1, message, None, None)

    assert log_filter.filter(_record("'x' contains unsupported syntax. Falling back to parsing as a 'Command'.")) is False
    assert log_filter.filter(_record("some other sqlglot warning")) is True


# --- Purity and the pin ------------------------------------------------------


def test_sql_module_stays_pure():
    """PRD-016 Section 6.12: no settings, no file I/O, no `app` import but the vocabulary."""
    source = inspect.getsource(sql)

    assert "settings" not in vars(sql)
    assert "open(" not in source
    assert "Path(" not in source
    imports = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]
    app_imports = [line for line in imports if " app." in line or line.startswith("from app")]
    assert app_imports == ["from app.services.action_classifiers import Classification, Operation, RuleId"]


def test_requirements_pins_sqlglot_exactly():
    """The classifier's mapping was verified on this version; an upgrade must be deliberate."""
    text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert re.search(r"(?m)^sqlglot==30\.27\.0\s*$", text)
    assert sqlglot.__version__ == "30.27.0"
