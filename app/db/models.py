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
    pii_entities TEXT,
    role TEXT,
    denied_permission TEXT,
    session_id TEXT
)
"""

# Columns added after the initial schema shipped (PRD-003 PII telemetry; PRD-005
# RBAC adds to this in STORY-009; PRD-008 STORY-002 adds session_id). CREATE
# TABLE IF NOT EXISTS is a no-op against a database created before they existed,
# so init_db() ALTERs in whichever of these an old file is missing.
#
# Every entry here is also declared in CREATE_AUDIT_LOGS_TABLE above. The two are
# not redundant: this mapping brings a database that predates a column up to
# date, while the CREATE is the shape a fresh database is built to -- listing a
# column in only one of them means every new deployment ALTERs its own
# brand-new table on first boot.
# Additive only: no drops, renames, or type changes.
# Every NOT NULL entry needs a non-NULL DEFAULT -- SQLite rejects ADD COLUMN
# NOT NULL without one. Enforced by
# tests/test_db.py::test_added_columns_declaring_not_null_also_declare_a_default.
AUDIT_LOGS_ADDED_COLUMNS = {
    "pii_detected_input": "INTEGER NOT NULL DEFAULT 0",
    "pii_detected_output": "INTEGER NOT NULL DEFAULT 0",
    "pii_entities": "TEXT",
    "role": "TEXT",
    "denied_permission": "TEXT",
    # PRD-008: the join key between the evidence log and the transcript.
    # Nullable with no default on purpose -- a POST /query that omits session_id
    # writes NULL, which is today's behaviour exactly (PRD Section 10).
    "session_id": "TEXT",
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

# Transcript store (PRD-008). The conversation a user reads, kept apart from the
# evidence audit_logs holds: that table stores hashes, truncated previews and
# verdicts and is immutable; these two store what was actually said and are the
# user's own working copy, theirs to rename and theirs to delete. Deleting a
# chat never deletes an audit row.
#
# session_id declares NOT NULL explicitly, for the reason the users table gives
# above: outside INTEGER PRIMARY KEY, SQLite lets a PRIMARY KEY column hold NULL,
# and more than one row of them.
#
# **No foreign key on chat_messages.session_id, deliberately.** SQLite enforces
# foreign keys only when PRAGMA foreign_keys=ON is set per connection, and the
# shared libSQL client (PRD-007) gives no place to guarantee that on every path.
# A declared-but-unenforced constraint reads as a guarantee and is not one, so
# there is none to read. delete_chat_session() removes from both tables in one
# transaction instead, and that is the enforcement.
CREATE_CHAT_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id TEXT PRIMARY KEY NOT NULL,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

# Not UNIQUE, unlike idx_users_token_hash: one user has many sessions, so this
# index serves ordering and filtering rather than a uniqueness claim. The column
# order is the rail's read exactly -- filter by owner, newest activity first.
CREATE_CHAT_SESSIONS_USER_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_updated "
    "ON chat_sessions(user_id, updated_at DESC)"
)

# Mirrors chat_ui/chat_ui/models.py's ChatMessage field for field, because a
# restored bubble renders through the same rx.match as a live one -- a second,
# lossier model is how a reloaded transcript would come to read differently from
# the conversation the user actually had.
#
# Two of ChatMessage's fields deliberately have **no column**:
# duplicate_relative_info and duplicate_release_info. They are humanized copy,
# recomputed on load so they stay relative to *now* (PRD Section 6); a stored
# "2m ago" is wrong the moment it is read back. Their absence is a decision.
#
# There is no `archived` column either: deletion is the only lifecycle operation
# this PRD ships.
#
# id is the order. Messages are read ORDER BY id ASC and never by timestamp --
# a TEXT timestamp ties arbitrarily when two rows share a second (PRD-006
# Section 13), and a transcript that reorders itself on reload would be a
# visible instance of that defect. created_at is displayed, not sorted on.
CREATE_CHAT_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    prompt TEXT,
    model_used TEXT,
    tokens_used INTEGER,
    audit_id INTEGER,
    pii_redacted INTEGER NOT NULL DEFAULT 0,
    pii_entities TEXT,
    pattern TEXT,
    required_permission TEXT,
    first_query_at TEXT,
    detail TEXT
)
"""

# (session_id, id) is list_chat_messages' read exactly: every message of one
# session, in key order.
CREATE_CHAT_MESSAGES_SESSION_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id "
    "ON chat_messages(session_id, id)"
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
    role: Optional[str] = None
    denied_permission: Optional[str] = None
    # PRD-008. The field only: insert_audit_log() and _row_to_audit_log() learn
    # about it in STORY-008, so until then a read leaves this None whatever the
    # column holds.
    session_id: Optional[str] = None
    id: Optional[int] = None


@dataclass
class User:
    user_id: str
    role: str
    token_hash: str
    active: bool = True
    created_at: Optional[str] = None  # insert_user() stamps it when omitted


@dataclass
class ChatSession:
    session_id: str
    user_id: str
    title: str
    created_at: Optional[str] = None  # create_chat_session() stamps it when omitted
    updated_at: Optional[str] = None  # touch_chat_session() moves it


@dataclass
class StoredMessage:
    """One row of chat_messages -- the table's shape, not the bubble's.

    pii_entities is the comma-joined string the column holds, matching how
    app/services/audit_logger.py:45 already persists the same data. Splitting it
    back into a list belongs to the rehydration into ChatMessage, not here: this
    dataclass mirrors the table, and one encoding serves one concept.
    """

    session_id: str
    kind: str
    content: str
    prompt: Optional[str] = None
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None
    audit_id: Optional[int] = None
    pii_redacted: bool = False
    pii_entities: Optional[str] = None
    pattern: Optional[str] = None
    required_permission: Optional[str] = None
    first_query_at: Optional[str] = None
    detail: Optional[str] = None
    created_at: Optional[str] = None  # append_chat_message() stamps it when omitted
    id: Optional[int] = None
