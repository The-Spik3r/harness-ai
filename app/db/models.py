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
    session_id TEXT,
    dedup_key TEXT
)
"""

# Columns added after the initial schema shipped (PRD-003 PII telemetry; PRD-005
# RBAC adds to this in STORY-009; PRD-008 STORY-002 adds session_id; PRD-009
# STORY-002 adds dedup_key). CREATE TABLE IF NOT EXISTS is a no-op against a
# database created before they existed, so init_db() ALTERs in whichever of
# these an old file is missing.
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
    # PRD-009: the per-caller duplicate key, derived from a conversation rather
    # than a string (PRD Section 6.2). Nullable with no default on purpose --
    # rows written before the column existed stay NULL and are never backfilled
    # (D6), and a NULL key can never match a duplicate lookup.
    "dedup_key": "TEXT",
}

# The duplicate lookup's access path exactly (PRD-009 Section 6.3): equality on
# user_id, equality on dedup_key, range on timestamp. The three flag predicates
# that lookup also applies filter the handful of rows left inside one user's key
# range and are deliberately not indexed.
#
# Not UNIQUE, unlike idx_users_token_hash: the same key legitimately repeats --
# a duplicate-blocked row, a failure or a denial carries the key of the request
# it answered. init_db() must execute this *after* _add_missing_columns(): on a
# database created before PRD-009, dedup_key does not exist until then, and an
# index on a missing column fails the boot.
CREATE_AUDIT_LOGS_DEDUP_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_dedup "
    "ON audit_logs(user_id, dedup_key, timestamp)"
)

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
# One column is ahead of that mirror for now: PRD-010 STORY-010 adds
# history_trimmed here, and STORY-012 adds the matching ChatMessage field and
# the two mappers. The gap is a story wide, deliberately -- the column has to
# exist before there is anything to persist into it.
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
    detail TEXT,
    history_trimmed INTEGER
)
"""

# The second added-columns mapping, and the first over a table that is not
# audit_logs (PRD-010 STORY-010). CREATE TABLE IF NOT EXISTS is a no-op against
# a chat_messages created before this PRD, so init_db() ALTERs the column in --
# the same convergence AUDIT_LOGS_ADDED_COLUMNS above describes, run for a
# second table rather than reimplemented for one.
#
# Every entry here is also declared in CREATE_CHAT_MESSAGES_TABLE above, and the
# two are not redundant for the reason the audit mapping gives: this brings an
# old database up to date, the CREATE is what a fresh one is built to, and a
# column listed in only one of them means every new deployment ALTERs its own
# brand-new table on first boot.
#
# Nullable with no default on purpose, and the distinction is the point. NULL
# means "this row was written before the feature existed"; 0 means "this send
# dropped nothing". INTEGER NOT NULL DEFAULT 0 would report every restored
# pre-PRD row as the second, which is a footer that lies about what was sent.
# Additive only: no drops, renames, or type changes. Every NOT NULL entry would
# need a non-NULL DEFAULT -- SQLite rejects ADD COLUMN NOT NULL without one.
#
# Nothing writes a non-NULL value yet: STORY-012 does, through ChatMessage and
# chat_ui/chat_ui/state.py's _to_stored_message.
CHAT_MESSAGES_ADDED_COLUMNS = {"history_trimmed": "INTEGER"}

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
    # PRD-008. Wired end to end as of STORY-008: insert_audit_log() writes it,
    # and _row_to_audit_log() maps it back on both read shapes -- the `SELECT *`
    # row and the json_object(...) the summary snapshot decodes.
    session_id: Optional[str] = None
    # PRD-009. Same pattern as session_id: insert_audit_log() writes it and
    # _row_to_audit_log() maps it back on both read shapes, as of STORY-002.
    # Nothing sets a real key until STORY-006, and it is never exposed on
    # GET /audit (D5). Declared after session_id to mirror the table, so id
    # stays the trailing field.
    dedup_key: Optional[str] = None
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
    # PRD-010: how many whole earlier exchanges chat_history.fit dropped from the
    # send this row answered (STORY-011), carried on the assistant row so a
    # reloaded transcript renders the same footer note the live bubble showed
    # (STORY-013). Declared after detail to mirror the table, so created_at and
    # id stay the trailing fields.
    #
    # Optional[int], not int: None is "written before this PRD", 0 is "this send
    # dropped nothing", and only a nullable field can say both.
    history_trimmed: Optional[int] = None
    created_at: Optional[str] = None  # append_chat_message() stamps it when omitted
    id: Optional[int] = None
