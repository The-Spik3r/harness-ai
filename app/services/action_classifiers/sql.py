"""The SQL classifier: one statement string in, one classification per statement out (PRD-016 Sections 6.3, 6.9, F2).

`classify_sql(statement, dialect)` parses with sqlglot (D2) **once** and maps
each parsed statement **by expression class** through an explicit table to
`sql.read`, `sql.write`, `sql.unscoped_write`, `sql.ddl` or `sql.dcl`.
Anything not explicitly mapped is `sql.unparsed`: an `exp.Command` (sqlglot's
"I could not parse this, here is the raw text" node), any other unmapped
class, a parse error, and any exception at all. The function never raises
(PRD-016 Section 6.9, Risk 6): a classifier that cannot read a statement must
deny it, not let it through and not crash the call.

Verified against sqlglot 30.27.0, the exact version `requirements.txt` pins.
A different version can parse the same text into a different class, which is
why the pin is exact and `tests/test_action_sql.py` pins the library
behaviour this module depends on.

What the real library forced, each one narrow and failing closed:

- **Two `exp.Command` carve-outs.** The generic dialect returns `EXPLAIN ...`
  and `SHOW ...` as `Command`. `SHOW` is a read (Section 6.3). `EXPLAIN`
  re-classifies its inner text and is a read only when everything inside is
  one; `EXPLAIN ANALYZE ...` (which *executes* the statement), a nested
  `EXPLAIN` or an empty one is unparsed, and `EXPLAIN DELETE FROM t` is the
  inner statement's classification. A `Command` never spans a `;`: sqlglot
  splits statements before it builds one.
- **Transaction control is a read** (orchestrator decision on STORY-008's
  plan): `BEGIN`, `START TRANSACTION`, `COMMIT`, `ROLLBACK`, `SAVEPOINT`,
  `RELEASE` change no data on their own. They parse as `exp.Transaction`,
  `exp.Commit` and `exp.Rollback`, except that sqlglot reads `START
  TRANSACTION`, `SAVEPOINT s` and `RELEASE s` as a column alias
  (`Alias(Column(START), TRANSACTION)`) and tsql reads a bare `BEGIN` as
  `Command('BEGIN')`. Those three shapes are matched structurally, nothing
  wider. `SET` and `USE` stay unparsed: `SET ROLE` and `SET search_path` can
  change privileges or targets.
- **An embedded walk.** A data-modifying CTE (`WITH d AS (DELETE ... RETURNING
  *) SELECT ...`) parses as a `Select`, and `SELECT ... INTO n` creates a
  table. After each statement's own classification, its tree is searched for
  modifying nodes, one more classification per hit, so a write cannot pass as
  a read (Risk 6, "mis-parses into a safer type").
- **sqlglot's fallback warning is filtered.** When it falls back to
  `Command`, sqlglot logs up to 100 characters of the *statement*, and this
  repo keeps agent text out of its logs. A `logging.Filter` on the `sqlglot`
  logger drops exactly that record. It is this module's one import-time
  side effect, a deliberate exception to "nothing at import": it reads no
  setting, does no I/O and drops nothing else.

The `WHERE` test (Section 6.9): an `UPDATE`/`DELETE` is scoped only when it
has a `WHERE` that sqlglot's simplifier does not reduce to `TRUE`
(`WHERE 1=1`, `WHERE 'a'='a'`, `WHERE 1=1 OR id = 3`). A tautology the
simplifier does not fold (`WHERE id = id`) counts as scoped -- a known limit;
`sql.write` is still deny by default.

Every classification's `operation` is `Operation("sql", statement,
source_tool)` with the **whole input** as the target: sqlglot gives no
reliable per-statement span, and regenerated SQL would not be the call's text.
The `detail` is the statement's keyword (`DROP`, `SELECT INTO`, `VACUUM`).

Pure (PRD-016 Section 6.12): the dialect is an argument. Only `action_config`
reads `ACTION_SQL_DIALECT`, and refuses one outside `SQL_DIALECTS` at startup.
"""

import logging
from typing import Optional

import sqlglot
from sqlglot import exp
from sqlglot.dialects.dialect import Dialect
from sqlglot.optimizer.simplify import simplify

from app.services.action_classifiers import Classification, Operation, RuleId

#: Every dialect name `sqlglot.parse(dialect=...)` accepts, without the generic
#: `""` (PRD-016 Section 6.9). `Dialect.classes` is the registry
#: `Dialect.get_or_raise` consults; it includes `singlestore`, which the public
#: `sqlglot.Dialects` enum lacks. `action_config` checks `ACTION_SQL_DIALECT`
#: against this, so sqlglot knowledge stays in the classifier. It also holds
#: `dax` and `prql`, which are not SQL: under them nothing parses, so every
#: statement is `sql.unparsed` (fails closed).
SQL_DIALECTS: tuple[str, ...] = tuple(sorted(name for name in Dialect.classes if name))

# The sqlglot log line that embeds the statement text (parser.py
# `_warn_unsupported`, 30.27.0).
_FALLBACK_MARKER = "Falling back to parsing as a 'Command'"


class _DropCommandFallback(logging.Filter):
    """Drop sqlglot's "falling back to Command" warning: it carries the agent's SQL."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            return _FALLBACK_MARKER not in record.getMessage()
        except Exception:
            # A record whose message cannot be built is not one we can vouch
            # for; it came from the sqlglot logger, so drop it.
            return False


_sqlglot_logger = logging.getLogger("sqlglot")
if not any(type(f).__name__ == _DropCommandFallback.__name__ for f in _sqlglot_logger.filters):
    # Checked so a module reload does not stack filters. By name, not
    # `isinstance`: a reload makes a new class, and the old instance stays.
    _sqlglot_logger.addFilter(_DropCommandFallback())

# The shallow table's rows that classify as a read. Used for `EXPLAIN`: a plan
# of a read is a read; a plan of anything else is that thing.
_READ: RuleId = "sql.read"

#: `kind`s of `CREATE` / `DROP` / `ALTER` that are access control, not schema
#: (Section 6.3 `sql.dcl`). Checked before the DDL row.
_DCL_KINDS = frozenset({"USER", "ROLE", "GROUP"})

# Node classes the embedded walk looks for below a statement's root. `Select`
# is listed so `SELECT ... INTO` is found; a plain nested `Select` is skipped.
_EMBEDDED = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.TruncateTable,
    exp.Comment,
    exp.Grant,
    exp.Revoke,
    exp.Command,
    exp.Select,
)

# `EXPLAIN` re-classifies its inner text once; `EXPLAIN EXPLAIN ...` is unparsed.
_MAX_DEPTH = 1

# Longest `detail` for an unparseable input's head token.
_HEAD_MAX = 32

# Transaction control that sqlglot reads as `Alias(Column(<head>), <alias>)`:
# head -> the alias it must carry (None: any plain identifier, the savepoint).
_TXN_ALIAS_HEADS: dict[str, Optional[str]] = {
    "START": "TRANSACTION",
    "SAVEPOINT": None,
    "RELEASE": None,
}


def _head(text) -> str:
    """The first whitespace-delimited token of the input, for an unparsed detail."""
    if not isinstance(text, str):
        return ""
    parts = text.split(None, 1)
    return parts[0][:_HEAD_MAX] if parts else ""


def _is_scoped(node: exp.Expression) -> bool:
    """An `UPDATE`/`DELETE` is scoped iff its `WHERE` is present and not constant-true (Section 6.9)."""
    where = node.args.get("where")
    if where is None:
        return False
    # `simplify` mutates its argument: always on a copy.
    return simplify(where.this.copy()) != exp.true()


def _plain_identifier(node) -> Optional[str]:
    """The upper-cased name of an unquoted `Identifier`, else None."""
    if isinstance(node, exp.Identifier) and not node.args.get("quoted"):
        return node.name.upper()
    return None


def _transaction_alias(node: exp.Alias) -> Optional[str]:
    """`START TRANSACTION` / `SAVEPOINT s` / `RELEASE s` as sqlglot mis-reads them, else None."""
    column = node.this
    if not isinstance(column, exp.Column) or column.args.get("table") is not None:
        return None
    head = _plain_identifier(column.this)
    if head not in _TXN_ALIAS_HEADS:
        return None
    alias = _plain_identifier(node.args.get("alias"))
    if alias is None:
        return None
    required = _TXN_ALIAS_HEADS[head]
    if required is not None and alias != required:
        return None
    return "START TRANSACTION" if head == "START" else head


def _command_tail(node: exp.Command) -> str:
    """The raw text after a `Command`'s head keyword."""
    tail = node.args.get("expression")
    if isinstance(tail, exp.Expression):
        return tail.name
    return tail if isinstance(tail, str) else ""


def _classify_node(node: exp.Expression, op: Operation) -> Classification:
    """The shallow table: one node's own class to one rule. Closed by default (PRD-016 Section 6.9)."""
    # Read.
    if isinstance(node, exp.Select):
        if node.args.get("into") is not None:
            # `SELECT ... INTO new_t` creates a table.
            return Classification("sql.ddl", op, "SELECT INTO")
        return Classification(_READ, op, "SELECT")
    if isinstance(node, exp.SetOperation):
        return Classification(_READ, op, "SELECT")
    if isinstance(node, exp.Describe):
        return Classification(_READ, op, "DESCRIBE")
    if isinstance(node, exp.Show):
        return Classification(_READ, op, "SHOW")
    # Transaction control: a read (it changes no data on its own).
    if isinstance(node, exp.Transaction):
        return Classification(_READ, op, "BEGIN")
    if isinstance(node, exp.Commit):
        return Classification(_READ, op, "COMMIT")
    if isinstance(node, exp.Rollback):
        return Classification(_READ, op, "ROLLBACK")
    if isinstance(node, exp.Alias):
        keyword = _transaction_alias(node)
        if keyword is not None:
            return Classification(_READ, op, keyword)
        return Classification("sql.unparsed", op, node.key.upper())
    # Write.
    if isinstance(node, exp.Insert):
        return Classification("sql.write", op, "INSERT")
    if isinstance(node, exp.Merge):
        return Classification("sql.write", op, "MERGE")
    if isinstance(node, (exp.Update, exp.Delete)):
        keyword = "UPDATE" if isinstance(node, exp.Update) else "DELETE"
        rule: RuleId = "sql.write" if _is_scoped(node) else "sql.unscoped_write"
        return Classification(rule, op, keyword)
    # DCL, before DDL: `CREATE ROLE` / `DROP USER` are access control.
    if isinstance(node, exp.Grant):
        return Classification("sql.dcl", op, "GRANT")
    if isinstance(node, exp.Revoke):
        return Classification("sql.dcl", op, "REVOKE")
    for cls, keyword in ((exp.Create, "CREATE"), (exp.Drop, "DROP"), (exp.Alter, "ALTER")):
        if isinstance(node, cls):
            kind = str(node.args.get("kind") or "").upper()
            if kind in _DCL_KINDS:
                return Classification("sql.dcl", op, f"{keyword} {kind}")
            return Classification("sql.ddl", op, keyword)
    if isinstance(node, exp.TruncateTable):
        return Classification("sql.ddl", op, "TRUNCATE")
    if isinstance(node, exp.Comment):
        return Classification("sql.ddl", op, "COMMENT")
    # Everything else, `exp.Command` included, is unparsed.
    if isinstance(node, exp.Command):
        head = node.this if isinstance(node.this, str) else ""
        return Classification("sql.unparsed", op, head.upper()[:_HEAD_MAX])
    return Classification("sql.unparsed", op, node.key.upper()[:_HEAD_MAX])


def _classify_command(
    node: exp.Command, op: Operation, dialect: Optional[str], depth: int
) -> list[Classification]:
    """The `exp.Command` carve-outs (`SHOW`, `EXPLAIN`, tsql's bare `BEGIN`); anything else is unparsed."""
    head = node.this.upper() if isinstance(node.this, str) else ""
    tail = _command_tail(node).strip()
    if head == "SHOW":
        return [Classification(_READ, op, "SHOW")]
    if head == "BEGIN" and not tail:
        # tsql's bare `BEGIN`. With a tail it is a block (`BEGIN DELETE ... END`).
        return [Classification(_READ, op, "BEGIN")]
    if head == "EXPLAIN":
        if not tail or depth >= _MAX_DEPTH:
            return [Classification("sql.unparsed", op, "EXPLAIN")]
        try:
            inner = _classify_text(tail, dialect, op, depth + 1)
        except Exception:
            # `EXPLAIN ANALYZE DELETE ...` lands here: `ANALYZE` executes the
            # statement, and the inner text does not parse. Unparsed, but
            # local, so the other statements keep their classifications.
            return [Classification("sql.unparsed", op, "EXPLAIN")]
        if all(c.rule == _READ for c in inner):
            return [Classification(_READ, op, "EXPLAIN")]
        return inner
    return [_classify_node(node, op)]


def _classify_statement(
    root: exp.Expression, op: Operation, dialect: Optional[str], depth: int
) -> list[Classification]:
    """One parsed statement: its own classification, then one per embedded modifying node."""
    if isinstance(root, exp.Command):
        out = _classify_command(root, op, dialect, depth)
    else:
        out = [_classify_node(root, op)]
    for node in root.find_all(*_EMBEDDED):
        if node is root:
            continue
        if isinstance(node, exp.Select) and node.args.get("into") is None:
            continue
        if isinstance(node.parent, exp.When):
            # A `MERGE`'s own `WHEN ... THEN UPDATE/INSERT` actions: the
            # `MERGE`'s `sql.write` already covers them.
            continue
        out.append(_classify_node(node, op))
    return out


def _classify_text(
    text: str, dialect: Optional[str], op: Operation, depth: int
) -> list[Classification]:
    """Parse once, classify each statement in order. Raises whatever sqlglot raises."""
    out: list[Classification] = []
    for root in sqlglot.parse(text, dialect=dialect or None):
        if root is None or isinstance(root, exp.Semicolon):
            continue
        out.extend(_classify_statement(root, op, dialect, depth))
    if not out:
        # Empty, whitespace, `;`, comment-only: nothing anyone can vouch for.
        return [Classification("sql.unparsed", op, "")]
    return out


def classify_sql(
    statement: str, dialect: Optional[str], *, source_tool: str = ""
) -> tuple[Classification, ...]:
    """Classify every statement in `statement`, in order (PRD-016 F2). Never raises.

    `dialect` is a sqlglot dialect name or None/"" for the generic one;
    `action_config` validates `ACTION_SQL_DIALECT` against `SQL_DIALECTS`
    before it gets here. `source_tool` names the tool the SQL came from, for
    the audit (`Operation.source_tool`).

    Any exception -- a `ParseError`, a `TokenError`, a `RecursionError` on
    deep nesting, a `ValueError` for an unknown dialect, a simplifier failure
    -- becomes one `sql.unparsed` whose detail is the input's first token.
    `BaseException` (KeyboardInterrupt) is deliberately not caught.
    """
    target = statement if isinstance(statement, str) else ""
    op = Operation(kind="sql", target=target, source_tool=source_tool)
    try:
        if not isinstance(statement, str):
            return (Classification("sql.unparsed", op, ""),)
        return tuple(_classify_text(statement, dialect, op, 0))
    except Exception:
        return (Classification("sql.unparsed", op, _head(statement)),)
