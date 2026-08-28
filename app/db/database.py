import sqlite3
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.db.models import (
    AUDIT_LOGS_ADDED_COLUMNS,
    CREATE_AUDIT_LOGS_TABLE,
    CREATE_USERS_TABLE,
    CREATE_USERS_TOKEN_HASH_INDEX,
    AuditLog,
    User,
)

_SQLITE_PREFIX = "sqlite:///"
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _db_path() -> str:
    url = settings.DATABASE_URL
    if not url.startswith(_SQLITE_PREFIX):
        raise ValueError(f"Unsupported DATABASE_URL scheme: {url}")
    return url[len(_SQLITE_PREFIX):]


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(CREATE_AUDIT_LOGS_TABLE)
        _add_missing_columns(conn)
        conn.execute(CREATE_USERS_TABLE)
        conn.execute(CREATE_USERS_TOKEN_HASH_INDEX)


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    """Brings a pre-existing audit_logs table up to the current schema.

    Additive only: existing rows keep their data and take the column default.
    """
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")}
    for name, ddl in AUDIT_LOGS_ADDED_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE audit_logs ADD COLUMN {name} {ddl}")


def insert_audit_log(entry: AuditLog) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO audit_logs (
                timestamp, user_id, device, prompt_hash, prompt_preview,
                response_hash, response_preview, model_used, tokens_used,
                was_duplicate_blocked, suspicious_pattern, success, error_message,
                pii_detected_input, pii_detected_output, pii_entities
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.timestamp,
                entry.user_id,
                entry.device,
                entry.prompt_hash,
                entry.prompt_preview,
                entry.response_hash,
                entry.response_preview,
                entry.model_used,
                entry.tokens_used,
                int(entry.was_duplicate_blocked),
                entry.suspicious_pattern,
                int(entry.success),
                entry.error_message,
                int(entry.pii_detected_input),
                int(entry.pii_detected_output),
                entry.pii_entities,
            ),
        )
        return cursor.lastrowid


def find_duplicate_timestamp(prompt_hash: str, since: str) -> Optional[str]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT timestamp FROM audit_logs
            WHERE prompt_hash = ? AND timestamp >= ?
            ORDER BY timestamp ASC
            LIMIT 1
            """,
            (prompt_hash, since),
        ).fetchone()
        return row["timestamp"] if row is not None else None


def _row_to_audit_log(row: sqlite3.Row) -> AuditLog:
    return AuditLog(
        id=row["id"],
        timestamp=row["timestamp"],
        user_id=row["user_id"],
        device=row["device"],
        prompt_hash=row["prompt_hash"],
        prompt_preview=row["prompt_preview"],
        response_hash=row["response_hash"],
        response_preview=row["response_preview"],
        model_used=row["model_used"],
        tokens_used=row["tokens_used"],
        was_duplicate_blocked=bool(row["was_duplicate_blocked"]),
        suspicious_pattern=row["suspicious_pattern"],
        success=bool(row["success"]),
        error_message=row["error_message"],
        pii_detected_input=bool(row["pii_detected_input"]),
        pii_detected_output=bool(row["pii_detected_output"]),
        pii_entities=row["pii_entities"],
    )


def get_audit_log(audit_id: int) -> Optional[AuditLog]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM audit_logs WHERE id = ?", (audit_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_audit_log(row)


def count_audit_logs() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]


def list_audit_logs(limit: int = 100) -> list[AuditLog]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_audit_log(row) for row in rows]


def count_blocked_duplicates() -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_logs WHERE was_duplicate_blocked = 1"
        ).fetchone()
        return row["n"]


def count_blocked_suspicious() -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_logs WHERE suspicious_pattern IS NOT NULL"
        ).fetchone()
        return row["n"]


def count_unique_users() -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(DISTINCT user_id) AS n FROM audit_logs"
        ).fetchone()
        return row["n"]


def count_successful_queries() -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_logs WHERE success = 1"
        ).fetchone()
        return row["n"]


def top_models(limit: int = 5) -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT model_used FROM audit_logs
            WHERE model_used IS NOT NULL
            GROUP BY model_used
            ORDER BY COUNT(*) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [row["model_used"] for row in rows]


def top_users(limit: int = 5) -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT user_id FROM audit_logs
            GROUP BY user_id
            ORDER BY COUNT(*) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [row["user_id"] for row in rows]


def count_pii_detected_queries() -> int:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n FROM audit_logs
            WHERE pii_detected_input = 1 OR pii_detected_output = 1
            """
        ).fetchone()
        return row["n"]


def top_pii_entities(limit: int = 5) -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT pii_entities FROM audit_logs WHERE pii_entities IS NOT NULL"
        ).fetchall()

    counts: dict[str, int] = {}
    for row in rows:
        for entity in row["pii_entities"].split(","):
            counts[entity] = counts.get(entity, 0) + 1

    ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    return [entity for entity, _ in ranked[:limit]]


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        user_id=row["user_id"],
        role=row["role"],
        token_hash=row["token_hash"],
        active=bool(row["active"]),
        created_at=row["created_at"],
    )


def get_user(user_id: str) -> Optional[User]:
    """Returns the user regardless of active state -- administrative reads
    (CLI list/deactivate) must be able to see a revoked row."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_user(row)


def find_user_by_token_hash(token_hash: str) -> Optional[User]:
    """Active users only. A revoked credential is indistinguishable from an
    unknown one by design -- PRD-005 Section 9 maps both to 401, and separating
    them would be a credential-enumeration oracle."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE token_hash = ? AND active = 1",
            (token_hash,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_user(row)


def list_users(limit: int = 100) -> list[User]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_user(row) for row in rows]


def count_active_users() -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE active = 1"
        ).fetchone()
        return row["n"]


def insert_user(entry: User) -> str:
    """Raises sqlite3.IntegrityError on a duplicate user_id or token_hash --
    deliberately not caught here; app/db/ has no error handling anywhere and the
    caller needs to tell those two cases apart."""
    created_at = entry.created_at or datetime.now(timezone.utc).strftime(
        _TIMESTAMP_FORMAT
    )
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, role, token_hash, active, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                entry.user_id,
                entry.role,
                entry.token_hash,
                int(entry.active),
                created_at,
            ),
        )
    return entry.user_id


def deactivate_user(user_id: str) -> bool:
    """Revocation is not deletion: audit_logs rows carry a bare user_id with no
    foreign key, so removing the row would orphan the audit trail. Returns False
    when no such user exists, so the CLI can report a typo."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE users SET active = 0 WHERE user_id = ?", (user_id,)
        )
        return cursor.rowcount == 1


def set_user_token_hash(user_id: str, token_hash: str) -> bool:
    """Credential rotation (STORY-004 `issue-token`). The old hash stops
    resolving the moment this returns."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE users SET token_hash = ? WHERE user_id = ?",
            (token_hash, user_id),
        )
        return cursor.rowcount == 1
