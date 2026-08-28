from dataclasses import dataclass
from typing import Optional

CREATE_AUDIT_LOGS_TABLE = """
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    user_id TEXT NOT NULL,
    device TEXT,
    prompt_hash TEXT NOT NULL,
    prompt_preview TEXT,
    response_hash TEXT,
    response_preview TEXT,
    model_used TEXT,
    tokens_used INTEGER,
    was_duplicate_blocked INTEGER NOT NULL DEFAULT 0,
    suspicious_pattern TEXT,
    success INTEGER NOT NULL DEFAULT 1,
    error_message TEXT,
    pii_detected_input INTEGER NOT NULL DEFAULT 0,
    pii_detected_output INTEGER NOT NULL DEFAULT 0,
    pii_entities TEXT
)
"""

# Columns added after the initial schema shipped (PRD-003 PII telemetry; PRD-005
# RBAC adds to this in STORY-009). CREATE TABLE IF NOT EXISTS is a no-op against
# a database created before they existed, so init_db() ALTERs in whichever of
# these an old file is missing.
# Additive only: no drops, renames, or type changes.
# Every NOT NULL entry needs a non-NULL DEFAULT -- SQLite rejects ADD COLUMN
# NOT NULL without one. Enforced by
# tests/test_db.py::test_added_columns_declaring_not_null_also_declare_a_default.
AUDIT_LOGS_ADDED_COLUMNS = {
    "pii_detected_input": "INTEGER NOT NULL DEFAULT 0",
    "pii_detected_output": "INTEGER NOT NULL DEFAULT 0",
    "pii_entities": "TEXT",
}

# Identity store (PRD-005). Lives in the same SQLite file as audit_logs -- no
# second service, no ORM, stdlib only.
#
# user_id declares NOT NULL explicitly: outside INTEGER PRIMARY KEY, SQLite lets
# a PRIMARY KEY column hold NULL, and more than one row of them.
#
# token_hash holds a SHA-256 digest produced by app/services/identity.py
# (STORY-003). Nothing in app/db/ ever sees the plaintext token.
CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY NOT NULL,
    role TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
)
"""

# UNIQUE, not merely indexed: it serves the lookup path (no table scan) and makes
# two users sharing a credential an IntegrityError at write time rather than an
# arbitrary winner at read time.
CREATE_USERS_TOKEN_HASH_INDEX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_token_hash ON users(token_hash)"
)


@dataclass
class AuditLog:
    timestamp: str
    user_id: str
    prompt_hash: str
    device: Optional[str] = None
    prompt_preview: Optional[str] = None
    response_hash: Optional[str] = None
    response_preview: Optional[str] = None
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None
    was_duplicate_blocked: bool = False
    suspicious_pattern: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
    pii_detected_input: bool = False
    pii_detected_output: bool = False
    pii_entities: Optional[str] = None
    id: Optional[int] = None


@dataclass
class User:
    user_id: str
    role: str
    token_hash: str
    active: bool = True
    created_at: Optional[str] = None  # insert_user() stamps it when omitted
