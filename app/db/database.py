import sqlite3
from typing import Optional

from app.config import settings
from app.db.models import CREATE_AUDIT_LOGS_TABLE, AuditLog

_SQLITE_PREFIX = "sqlite:///"


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


def insert_audit_log(entry: AuditLog) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO audit_logs (
                timestamp, user_id, device, prompt_hash, prompt_preview,
                response_hash, response_preview, model_used, tokens_used,
                was_duplicate_blocked, suspicious_pattern, success, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def get_audit_log(audit_id: int) -> Optional[AuditLog]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM audit_logs WHERE id = ?", (audit_id,)
        ).fetchone()
        if row is None:
            return None
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
        )
