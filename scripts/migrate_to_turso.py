"""One-time copy of `audit_logs` and `users` from a legacy SQLite file into Turso.

PRD-007 Section 7.5, STORY-013. The source `.db` file is read, never written; it
remains authoritative until verification passes, and **deleting it is not part of
this script** -- that is STORY-014, deliberately a separate step (PRD Section 14
Risk 2: "The file is deleted only after verification, in a separate step from the
copy").

**This module holds the one sanctioned `import sqlite3` outside `app/db/`.**
PRD Section 11 requires that "no module outside `app/db/` imports `sqlite3` or any
driver module", and STORY-014's AC 6 grants this file the exception in writing:

    grep -rn "sqlite" app/ chat_ui/ docker-compose.yml Dockerfile ... returns no
    hits in any production path. `scripts/migrate_to_turso.py` is the one
    documented exception (it reads the legacy file by design).

The exception is sound because this is an operational tool, not a production code
path: nothing in the application imports it, it runs once per deployment, and its
whole purpose is to read the file the rest of the system may no longer touch. It
needs both drivers at once -- stdlib `sqlite3` for the source, the libSQL client
(through `app.db.database`) for the destination.

The source is a CLI argument and the destination is `settings.DATABASE_URL`, and
those two facts are not interchangeable: `app/config.py`'s validator rejects any
`sqlite:` URL outright, so a file can never arrive through configuration. That is
the guarantee PRD Section 2 wanted -- "a configuration that would have opened a
file is a startup error" -- and this script does not weaken it.

Usage:

    python scripts/migrate_to_turso.py --source harness_ai.db [--dry-run]
                                       [--batch-size 50] [--verify-sample 50]
"""

import argparse
import hashlib
import re
import sqlite3
import sys
from pathlib import Path
from typing import Iterator, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import settings
from app.db.database import (
    _safe_endpoint,
    get_audit_log,
    get_connection,
    init_db,
)
from app.db.errors import StorageError
from app.db.models import (
    CREATE_AUDIT_LOGS_TABLE,
    CREATE_USERS_TABLE,
    AuditLog,
)

# The two tables PRD Section 7.5 names, in copy order. `audit_logs` first because
# it is the one the compliance record lives in; if a run is going to fail, the
# operator learns about the important table first.
_TABLES = ("audit_logs", "users")

# The DDL is the single source of truth for both the column list and the column
# defaults -- re-typing either here is how two lists drift apart, and a drifted
# column list in a migration is a silently dropped column.
_DDL = {"audit_logs": CREATE_AUDIT_LOGS_TABLE, "users": CREATE_USERS_TABLE}

# Ordering key for the row-by-row content comparison. Both are the tables' real
# primary keys, so the ordering is total and the two sides line up row for row.
_PRIMARY_KEY = {"audit_logs": "id", "users": "user_id"}

# The seven columns PRD Section 5 story 4 names -- the five AUDIT_LOGS_ADDED_COLUMNS
# plus `role` and `denied_permission`. A row carrying a non-default value in any of
# them is preferred by the accessor read-back sample, because these are the columns
# the story was written about and the ones an older source is most likely to lack.
_TELEMETRY_COLUMNS = (
    "pii_detected_input",
    "pii_detected_output",
    "pii_entities",
    "role",
    "denied_permission",
)

_DEFAULT_BATCH_SIZE = 50
_DEFAULT_VERIFY_SAMPLE = 50

# At most this many mismatch lines are printed. A systematic failure produces one
# line per row, and the operator needs the summary underneath it more than they
# need line 900.
_MAX_REPORTED_MISMATCHES = 20


class MigrationError(Exception):
    """An operator-legible refusal: bad source, bad schema, populated destination.

    Distinct from `app.db.errors.StorageError`, which means the database failed.
    This means the script declined to proceed, and the message says why in a
    sentence the operator can act on.
    """


# --- schema, read out of the DDL rather than re-typed ---------------------------


def _ddl_body(ddl: str) -> str:
    return ddl[ddl.index("(") + 1 : ddl.rindex(")")]


def _ddl_columns(ddl: str) -> list:
    """The column names a CREATE TABLE statement declares, in declaration order.

    Neither of the two DDLs has a table-level constraint or a nested parenthesis,
    so splitting the body on commas and taking the first token of each part is
    exact rather than approximate. `test_dest_columns_match_the_ddl` pins the
    result against the literal column lists so a future schema change that breaks
    the assumption breaks a test rather than a migration.
    """
    return [part.split()[0] for part in _ddl_body(ddl).split(",") if part.strip()]


def _ddl_defaults(ddl: str) -> dict:
    """Column name -> the value the destination applies when the INSERT omits it.

    Needed because a source predating PRD-003/PRD-005 lacks some columns entirely
    (AC 9). Those columns are left out of the INSERT so the destination's own
    DEFAULT fills them, and the content verification then has to compare against
    that default rather than against a value the source never had.
    """
    defaults = {}
    for part in _ddl_body(ddl).split(","):
        tokens = part.split()
        if not tokens:
            continue
        match = re.search(r"\bDEFAULT\s+(\S+)", part, re.IGNORECASE)
        if match is None:
            defaults[tokens[0]] = None
            continue
        literal = match.group(1).strip("'\"")
        defaults[tokens[0]] = int(literal) if literal.lstrip("-").isdigit() else literal
    return defaults


# --- the source file, opened so that it cannot be written -----------------------


def _fingerprint(path: Path) -> tuple:
    """`(sha256, size)` of the file as it is right now.

    Taken before the source is opened and again after it is closed, on every exit
    path. AC 6 covers "success, failure, **or interruption**", and a comment
    saying the script does not write to the file would prove none of those; the
    read-only open below is the enforcement and this is the evidence.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest(), path.stat().st_size


def _refuse_hot_journal(path: Path) -> None:
    """Refuses a source with an unmerged WAL or rollback journal beside it.

    SQLite recovers such a journal on open -- a **write** -- which would break
    AC 6 before a single row was read, and a read-only open of a hot-WAL database
    can also fail in a way that reads as a driver bug rather than as a database
    that needs checkpointing. Refusing first turns both into one instruction.
    """
    for suffix in ("-wal", "-journal"):
        sidecar = path.with_name(path.name + suffix)
        if sidecar.exists() and sidecar.stat().st_size > 0:
            raise MigrationError(
                f"{sidecar.name} exists and is not empty, so {path.name} has "
                "un-checkpointed changes. Opening it read-only would either fail "
                "or require a recovery write, and this script must not modify the "
                "source. Checkpoint it first with:\n"
                f"  python -c \"import sqlite3; sqlite3.connect(r'{path}')"
                ".execute('PRAGMA wal_checkpoint(TRUNCATE)')\""
            )


def _open_source(path: Path) -> sqlite3.Connection:
    """Opens the source strictly read-only.

    `mode=ro` is enforcement, not intention: the connection cannot issue a write,
    so no path through this script -- including one that dies halfway -- can
    mutate the file that is still the authoritative copy of the audit trail.
    """
    uri = f"file:{path.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _source_columns(source: sqlite3.Connection, table: str) -> Optional[list]:
    """The source table's columns, or `None` when the table does not exist.

    Same `PRAGMA table_info` idiom as `app/db/database.py:517`, pointed the other
    way. `None` is a real answer for `users`: a file older than PRD-005 has no
    such table, and that is a migration with nothing to copy, not an error.
    """
    rows = source.execute(f"PRAGMA table_info({table})").fetchall()
    if not rows:
        return None
    return [row["name"] for row in rows]


class _TablePlan:
    """What will be copied for one table, and what the destination will default."""

    def __init__(self, table: str, columns: list, defaulted: list, present: bool):
        self.table = table
        self.columns = columns
        self.defaulted = defaulted
        self.present = present


def _reconcile(source: sqlite3.Connection, table: str) -> _TablePlan:
    """Decides the column list for one table, or refuses (AC 9).

    **Copying is by column name, never `SELECT *`.** The real `harness_ai.db` has
    `pii_entities, role, denied_permission` appended by `ALTER TABLE`, so its
    column *order* differs from `CREATE_AUDIT_LOGS_TABLE`. A positional copy would
    shift every value one column left of where it belongs and still report
    matching row counts -- exactly the "count match with corrupted content"
    failure AC 3 exists to catch.

    Three outcomes:

    - A column in both: copied.
    - A column the destination has and the source lacks (a file predating PRD-003
      or PRD-005): omitted from the INSERT so the destination's own DEFAULT
      applies. Reported by name.
    - A column the source has and the destination does not: **refused**. The
      current schema has nowhere to put it, and silently dropping a column in a
      compliance migration is not an option.
    """
    dest_columns = _ddl_columns(_DDL[table])
    found = _source_columns(source, table)

    if found is None:
        if table == "audit_logs":
            raise MigrationError(
                "the source has no `audit_logs` table, so it is not a harness "
                "database. Nothing was copied."
            )
        return _TablePlan(table, [], [], present=False)

    unknown = [name for name in found if name not in dest_columns]
    if unknown:
        raise MigrationError(
            f"the source's `{table}` has {len(unknown)} column(s) the current "
            f"schema does not declare: {', '.join(sorted(unknown))}. Refusing "
            "rather than dropping them silently."
        )

    columns = [name for name in dest_columns if name in found]
    if table == "audit_logs" and "id" not in columns:
        raise MigrationError(
            "the source's `audit_logs` has no `id` column, so the ids this "
            "migration must preserve do not exist. Refusing."
        )

    defaulted = [name for name in dest_columns if name not in found]
    return _TablePlan(table, columns, defaulted, present=True)


# --- the copy -------------------------------------------------------------------


def _chunks(rows: Iterator, size: int) -> Iterator:
    chunk = []
    for row in rows:
        chunk.append(row)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def _copy_table(conn, source: sqlite3.Connection, plan: _TablePlan, size: int) -> int:
    """Copies one table as chunked multi-row INSERTs. Returns statements issued.

    **One statement per chunk, through `execute()`.** STORY-001 §2.6 established
    that the driver has no `batch()`, that `executescript()` returns `None`, and
    that a multi-*statement* `execute()` returns only the first result *and
    reports success for a statement it never ran*. `executemany` exists on the
    driver but is used nowhere else in this repo, so it is undemonstrated against
    this endpoint. A multi-row `VALUES (?,..),(?,..)` is a single statement
    carrying N rows, which makes the batching a property of the SQL rather than of
    an unexercised client feature -- it rides the same `execute()` path all 22
    public functions already use.

    `id` is copied like any other column, which is the whole of AC 2's cost.
    `ORDER BY id` ascending so `sqlite_sequence` climbs monotonically to MAX(id).

    Rows stream from the source cursor a chunk at a time rather than being
    materialized; a real audit history should not have to fit in memory to move.
    """
    if not plan.present or not plan.columns:
        return 0

    quoted = ", ".join(f'"{name}"' for name in plan.columns)
    order = _PRIMARY_KEY[plan.table]
    cursor = source.execute(f"SELECT {quoted} FROM {plan.table} ORDER BY {order}")

    row_values = "(" + ", ".join("?" * len(plan.columns)) + ")"
    statements = 0
    for chunk in _chunks(iter(cursor), size):
        conn.execute(
            f"INSERT INTO {plan.table} ({quoted}) VALUES "
            + ", ".join([row_values] * len(chunk)),
            tuple(value for row in chunk for value in tuple(row)),
        )
        statements += 1
    return statements


def _restore_sequence(conn, max_id: Optional[int]) -> str:
    """Keeps AUTOINCREMENT from re-issuing an id the migration just preserved.

    Inserting explicit ids into an `INTEGER PRIMARY KEY AUTOINCREMENT` column is
    supposed to advance `sqlite_sequence` to the highest id written -- verified
    against local SQLite, where ids 7 and 30 leave `seq = 30` and the next natural
    insert returns 31. This checks that the libSQL endpoint agrees rather than
    assuming parity between two engines, and repairs the sequence if it does not.
    A migration that preserves history and then breaks the first new write has
    traded one failure for another.
    """
    if max_id is None:
        return "not applicable (no rows)"

    row = conn.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'audit_logs'"
    ).fetchone()
    current = None if row is None else row["seq"]
    if current is not None and current >= max_id:
        return f"already correct at {current}"

    conn.execute(
        "INSERT OR REPLACE INTO sqlite_sequence (name, seq) VALUES ('audit_logs', ?)",
        (max_id,),
    )
    return f"repaired {current!r} -> {max_id}"


# --- verification ---------------------------------------------------------------


def _source_count(source: sqlite3.Connection, plan: _TablePlan) -> int:
    if not plan.present:
        return 0
    return source.execute(f"SELECT COUNT(*) AS n FROM {plan.table}").fetchone()["n"]


def _dest_count(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]


def _verify_counts(source, conn, plans: dict) -> tuple:
    """Layer A -- per-table row counts on both sides (AC 3)."""
    counts, failures = {}, []
    for table in _TABLES:
        expected = _source_count(source, plans[table])
        actual = _dest_count(conn, table)
        counts[table] = (expected, actual)
        if expected != actual:
            failures.append(
                f"{table}: count check failed -- {expected} source row(s), "
                f"{actual} destination row(s)"
            )
    return counts, failures


def _verify_ids(source, conn, plans: dict) -> list:
    """AC 2 -- the id sets are equal, reported as its own named check.

    Separate from the content comparison on purpose: a renumbered trail would
    otherwise surface as one mismatch per row, burying the one fact that explains
    all of them.
    """
    if not plans["audit_logs"].present:
        return []
    expected = {row["id"] for row in source.execute("SELECT id FROM audit_logs")}
    actual = {row["id"] for row in conn.execute("SELECT id FROM audit_logs")}
    if expected == actual:
        return []

    missing = sorted(expected - actual)[:5]
    extra = sorted(actual - expected)[:5]
    return [
        "audit_logs: id preservation failed -- "
        f"{len(expected - actual)} source id(s) absent from the destination "
        f"(e.g. {missing}), {len(actual - expected)} unexpected "
        f"(e.g. {extra})"
    ]


def _verify_content(source, conn, plans: dict) -> list:
    """Layer B -- every column of every row, compared cell by cell (AC 3).

    Exhaustive and bulk: two ordered selects per table, zipped. A column the
    source lacked is compared against the destination's declared DEFAULT, which
    is what "handled explicitly" means for AC 9 -- the absent column is checked,
    not skipped.

    Both sides are materialized here, unlike the streaming copy. Content
    verification is a full comparison by definition, and holding two ordered row
    lists is the cost of proving the thing the story exists to prove.
    """
    failures = []
    for table in _TABLES:
        plan = plans[table]
        if not plan.present:
            continue

        defaults = _ddl_defaults(_DDL[table])
        all_columns = _ddl_columns(_DDL[table])
        quoted = ", ".join(f'"{name}"' for name in all_columns)
        order = _PRIMARY_KEY[table]
        key_index = all_columns.index(order)

        src_quoted = ", ".join(f'"{name}"' for name in plan.columns)
        src_rows = source.execute(
            f"SELECT {src_quoted} FROM {table} ORDER BY {order}"
        ).fetchall()
        dst_rows = conn.execute(
            f"SELECT {quoted} FROM {table} ORDER BY {order}"
        ).fetchall()

        reported = 0
        for src, dst in zip(src_rows, dst_rows):
            for index, name in enumerate(all_columns):
                expected = src[name] if name in plan.columns else defaults[name]
                actual = dst[index]
                if expected == actual:
                    continue
                reported += 1
                if reported <= _MAX_REPORTED_MISMATCHES:
                    failures.append(
                        f"{table}: content check failed -- "
                        f"{order}={dst[key_index]!r} column={name} "
                        f"source={expected!r} destination={actual!r}"
                    )
        if reported > _MAX_REPORTED_MISMATCHES:
            failures.append(
                f"{table}: ... and {reported - _MAX_REPORTED_MISMATCHES} more "
                "content mismatch(es) not shown"
            )
    return failures


def _audit_log_from_source(row: sqlite3.Row, plan: _TablePlan, defaults: dict):
    """The `AuditLog` the source row should produce once migrated."""

    def value(name):
        return row[name] if name in plan.columns else defaults[name]

    return AuditLog(
        id=value("id"),
        timestamp=value("timestamp"),
        user_id=value("user_id"),
        device=value("device"),
        prompt_hash=value("prompt_hash"),
        prompt_preview=value("prompt_preview"),
        response_hash=value("response_hash"),
        response_preview=value("response_preview"),
        model_used=value("model_used"),
        tokens_used=value("tokens_used"),
        was_duplicate_blocked=bool(value("was_duplicate_blocked")),
        suspicious_pattern=value("suspicious_pattern"),
        success=bool(value("success")),
        error_message=value("error_message"),
        pii_detected_input=bool(value("pii_detected_input")),
        pii_detected_output=bool(value("pii_detected_output")),
        pii_entities=value("pii_entities"),
        role=value("role"),
        denied_permission=value("denied_permission"),
    )


def _read_back_sample(source, plan: _TablePlan, limit: int) -> list:
    """Which rows layer C checks, and why those.

    Not random: the lowest id, the highest id, and every row carrying a non-default
    value in one of the seven columns PRD Section 5 story 4 names. Rows with
    nothing in those columns are already covered well by layer B's exhaustive
    comparison; rows carrying PII telemetry, a role or a denied permission are the
    ones AC 8 was written about. `--verify-sample 0` takes every row.
    """
    rows = source.execute("SELECT * FROM audit_logs ORDER BY id").fetchall()
    if not rows:
        return []
    if limit == 0:
        return rows

    interesting = [
        row
        for row in rows
        if any(
            name in plan.columns and row[name] not in (None, 0, "")
            for name in _TELEMETRY_COLUMNS
        )
    ]
    chosen, seen = [], set()
    for row in [rows[0], rows[-1]] + interesting:
        if row["id"] not in seen:
            seen.add(row["id"])
            chosen.append(row)
        if len(chosen) >= limit:
            break
    return chosen


def _verify_read_back(source, plans: dict, limit: int) -> tuple:
    """Layer C -- the rows come back through `get_audit_log()` (AC 8).

    Layer B proves the stored values; this proves the *accessor* returns them.
    It is the `SELECT *` path `GET /audit/{id}` actually serves, and the only
    layer that exercises `_row_to_audit_log()`'s `bool()` coercions -- so a
    migration that stored `pii_detected_input` as the string "0" would pass layer
    B against a source that also held "0", and fail here. One round trip per row,
    which is why it is sampled and layer B is not.
    """
    plan = plans["audit_logs"]
    if not plan.present:
        return 0, []

    defaults = _ddl_defaults(_DDL["audit_logs"])
    sample = _read_back_sample(source, plan, limit)
    failures = []
    for row in sample:
        expected = _audit_log_from_source(row, plan, defaults)
        actual = get_audit_log(row["id"])
        if actual is None:
            failures.append(
                f"audit_logs: read-back check failed -- get_audit_log("
                f"{row['id']}) returned None"
            )
            continue
        if actual != expected:
            differing = [
                name
                for name in vars(expected)
                if getattr(expected, name) != getattr(actual, name)
            ]
            failures.append(
                f"audit_logs: read-back check failed -- id={row['id']} "
                f"column(s) {', '.join(differing)} differ "
                f"(source={[getattr(expected, n) for n in differing]!r} "
                f"destination={[getattr(actual, n) for n in differing]!r})"
            )
    return len(sample), failures


def _verify_token_hashes(conn, plans: dict) -> list:
    """AC 7 -- the hashes are distinct and the unique index still stands.

    A `token_hash` copied into a table whose unique index went missing looks
    perfectly healthy until the next `insert_user()` accepts a collision, and a
    collision in this column is two people sharing one credential.
    """
    if not plans["users"].present:
        return []

    failures = []
    row = conn.execute(
        "SELECT COUNT(*) AS total, COUNT(DISTINCT token_hash) AS distinct_hashes "
        "FROM users"
    ).fetchone()
    if row["total"] != row["distinct_hashes"]:
        failures.append(
            f"users: token_hash check failed -- {row['total']} row(s) carry only "
            f"{row['distinct_hashes']} distinct token_hash value(s)"
        )

    index = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' "
        "AND name = 'idx_users_token_hash'"
    ).fetchone()
    if index is None:
        failures.append(
            "users: token_hash check failed -- the unique index "
            "idx_users_token_hash is absent from the destination"
        )
    return failures


# --- output ---------------------------------------------------------------------


class _Outcome:
    """Everything the closing summary reports, filled in as the run proceeds."""

    def __init__(self) -> None:
        self.source_path: Optional[Path] = None
        self.sha_before: Optional[str] = None
        self.sha_after: Optional[str] = None
        self.source_counts: dict = {}
        self.dest_counts: dict = {}
        self.defaulted: dict = {}
        self.sequence: Optional[str] = None
        self.checks: list = []
        self.failures: list = []
        self.sampled: int = 0
        self.sample_of: int = 0
        self.copied: bool = False
        self.statements: int = 0


def _print_summary(outcome: _Outcome) -> None:
    """The block the story asks for in the script's own output, not only in docs.

    Printed on every path that actually attempted a migration, success or failure,
    and printed last, because it is the sentence that tells the operator what
    state they are now in.
    """
    source_line = "unchanged" if outcome.sha_before == outcome.sha_after else "CHANGED"
    print()
    print(f"Source      {outcome.source_path}")
    print(f"            sha256 {outcome.sha_before}  ({source_line})")
    print(
        "            "
        + ", ".join(
            f"{count} {table} row(s)" for table, count in outcome.source_counts.items()
        )
    )
    print(f"Destination {_safe_endpoint(settings.DATABASE_URL)}")
    print(
        "            "
        + ", ".join(
            f"{count} {table} row(s)" for table, count in outcome.dest_counts.items()
        )
    )
    for table, names in outcome.defaulted.items():
        if names:
            print(
                f"            note: source `{table}` lacks {', '.join(names)} "
                "-> destination defaults applied"
            )
    if outcome.sequence is not None:
        print(f"            audit_logs AUTOINCREMENT sequence: {outcome.sequence}")
    if outcome.copied:
        print(
            f"Copied      {sum(outcome.dest_counts.values())} row(s) in "
            f"{outcome.statements} statement(s)"
        )
    if outcome.copied and not any(outcome.source_counts.values()):
        print("            nothing to migrate -- the source held no rows")
    if outcome.checks:
        print(f"Verified    {' · '.join(outcome.checks)}")
    if outcome.failures:
        print("Rollback    Verification FAILED. The destination holds the rows above")
        print("            but has not been verified. The source file was opened")
        print("            read-only and is unmodified -- it remains authoritative.")
        print("            Clear the destination and re-run:")
        print("              DELETE FROM audit_logs; DELETE FROM users;")
    else:
        print("Rollback    The source file was opened read-only and is unmodified.")
        print("            It remains authoritative until you delete it, which is a")
        print("            separate step (STORY-014).")


# --- the run --------------------------------------------------------------------


def _run(args: argparse.Namespace, source, outcome: _Outcome) -> None:
    plans = {table: _reconcile(source, table) for table in _TABLES}
    outcome.defaulted = {table: plans[table].defaulted for table in _TABLES}
    outcome.source_counts = {
        table: _source_count(source, plans[table]) for table in _TABLES
    }

    # init_db() is also the reachability guard (app/db/database.py:454-478), so a
    # dead endpoint or a rejected credential fails here rather than mid-copy.
    init_db()

    with get_connection() as conn:
        populated = {
            table: _dest_count(conn, table)
            for table in _TABLES
            if _dest_count(conn, table) > 0
        }
    if populated:
        raise MigrationError(
            "the destination is not empty: "
            + ", ".join(f"{table} holds {n} row(s)" for table, n in populated.items())
            + ". Refusing to append into a populated table. There is deliberately "
            "no --force: the copy runs in one transaction, so a failed run leaves "
            "the destination empty and immediately re-runnable, and a flag that "
            "empties an audit table is the wrong tool to ship beside one. Clear it "
            "by hand if that is genuinely what you want."
        )

    if args.dry_run:
        print("Dry run -- nothing was written.")
        for table in _TABLES:
            plan = plans[table]
            if not plan.present:
                print(f"  {table}: absent in source, 0 rows to copy")
                continue
            print(
                f"  {table}: {outcome.source_counts[table]} row(s), "
                f"{len(plan.columns)} column(s) copied"
                + (
                    f", {len(plan.defaulted)} defaulted "
                    f"({', '.join(plan.defaulted)})"
                    if plan.defaulted
                    else ""
                )
            )
        print(f"  destination: {_safe_endpoint(settings.DATABASE_URL)}, empty")
        return

    # One transaction for both tables. `_Connection.__exit__` commits on a clean
    # exit and rolls back on any exception (app/db/database.py:212-221), so a
    # failure anywhere leaves the destination empty rather than half-populated --
    # which is what makes the non-empty refusal above a policy and not a trap.
    with get_connection() as conn:
        for table in _TABLES:
            outcome.statements += _copy_table(
                conn, source, plans[table], args.batch_size
            )
        max_id = conn.execute(
            "SELECT MAX(id) AS m FROM audit_logs"
        ).fetchone()["m"]
        outcome.sequence = _restore_sequence(conn, max_id)
    outcome.copied = True

    # Everything below reads after the commit, so it observes durable state rather
    # than the transaction's own uncommitted view (PRD Risk 1).
    with get_connection() as conn:
        counts, count_failures = _verify_counts(source, conn, plans)
        outcome.dest_counts = {table: counts[table][1] for table in _TABLES}
        id_failures = _verify_ids(source, conn, plans)
        content_failures = _verify_content(source, conn, plans)
        token_failures = _verify_token_hashes(conn, plans)

    outcome.sample_of = outcome.source_counts["audit_logs"]
    outcome.sampled, read_back_failures = _verify_read_back(
        source, plans, args.verify_sample
    )

    outcome.checks = [
        f"counts {'OK' if not count_failures else 'FAILED'}",
        f"content {'OK' if not content_failures else 'FAILED'}",
        f"id preservation {'OK' if not id_failures else 'FAILED'}",
        f"read-back {'OK' if not read_back_failures else 'FAILED'}"
        f" ({outcome.sampled} of {outcome.sample_of} sampled)",
        f"token_hash {'OK' if not token_failures else 'FAILED'}",
    ]
    outcome.failures = (
        count_failures
        + content_failures
        + id_failures
        + read_back_failures
        + token_failures
    )


def _migrate(args: argparse.Namespace) -> int:
    """Runs the migration and decides the exit code.

    Two exit shapes, deliberately different. A **refusal** -- a missing source, a
    hot journal, an unknown column, a populated destination -- happens before
    anything is written, so there is no migration to summarize and stdout stays
    clean, exactly as `scripts/manage_users.py` leaves it. A run that got as far
    as copying always prints the summary block, success or failure, because at
    that point the operator's first question is what state the two databases are
    in.

    The source-integrity check straddles both: it runs on every path, including
    the refusals, because AC 6 covers "success, failure, **or interruption**" and
    a check that only runs when things went well is not a check.
    """
    if args.batch_size < 1:
        print("Error: --batch-size must be at least 1.", file=sys.stderr)
        return 1
    if args.verify_sample < 0:
        print("Error: --verify-sample must be 0 or greater.", file=sys.stderr)
        return 1

    outcome = _Outcome()
    source = None
    refusal = None
    try:
        path = Path(args.source).expanduser().resolve()
        outcome.source_path = path
        if not path.is_file():
            raise MigrationError(f"no such source database: {path}")
        _refuse_hot_journal(path)
        outcome.sha_before = _fingerprint(path)[0]
        source = _open_source(path)
        _run(args, source, outcome)
    except MigrationError as exc:
        refusal = str(exc)
    except (StorageError, ValueError) as exc:
        # ValueError alongside StorageError because `_translated()` runs inside
        # `_session()`, and this script drives `get_connection()` directly -- so a
        # driver error can still arrive in its bare form (STORY-001 §3.5).
        message = f"the destination database failed: {exc}"
        if outcome.copied:
            # The copy committed; the operator needs the summary and the recovery
            # instructions, not just a one-line error.
            outcome.failures.append(message)
        else:
            refusal = message
    finally:
        if source is not None:
            source.close()
        if outcome.source_path is not None and outcome.source_path.is_file():
            outcome.sha_after = _fingerprint(outcome.source_path)[0]

    integrity_failure = None
    if outcome.sha_before is not None and outcome.sha_before != outcome.sha_after:
        integrity_failure = (
            "source integrity check failed -- the source file changed during the "
            f"run (sha256 {outcome.sha_before} -> {outcome.sha_after}). The source "
            "was opened read-only, so something outside this script wrote to it."
        )
        outcome.failures.append(integrity_failure)

    if refusal is not None:
        print(f"Error: {refusal}", file=sys.stderr)
        if integrity_failure is not None:
            print(f"Error: {integrity_failure}", file=sys.stderr)
        return 1

    if args.dry_run:
        return 1 if outcome.failures else 0

    _print_summary(outcome)

    if outcome.failures:
        print(file=sys.stderr)
        for failure in outcome.failures:
            print(f"Error: {failure}", file=sys.stderr)
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="migrate_to_turso.py",
        description=(
            "Copy audit_logs and users from a legacy SQLite file into the Turso "
            "database DATABASE_URL names, and verify the copy."
        ),
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to the legacy SQLite .db file. Read-only; never modified.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=_DEFAULT_BATCH_SIZE,
        help=(
            "Rows per INSERT statement (default: %(default)s). 50 rows of "
            "audit_logs is 950 bound parameters, under the conservative "
            "SQLITE_MAX_VARIABLE_NUMBER of 999."
        ),
    )
    parser.add_argument(
        "--verify-sample",
        type=int,
        default=_DEFAULT_VERIFY_SAMPLE,
        help=(
            "How many rows the get_audit_log() read-back covers (default: "
            "%(default)s; 0 means every row). The full row-by-row content "
            "comparison is exhaustive regardless."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check every precondition and report the plan without writing.",
    )
    parser.set_defaults(func=_migrate)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
