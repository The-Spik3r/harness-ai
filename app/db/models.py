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
    dedup_key TEXT,
    pattern_role TEXT,
    pattern_action TEXT,
    profile TEXT,
    ingress TEXT,
    message_count INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    streamed INTEGER NOT NULL DEFAULT 0,
    has_tool_calls INTEGER NOT NULL DEFAULT 0,
    conversation_key TEXT,
    limit_exceeded TEXT
)
"""

# Columns added after the initial schema shipped (PRD-003 PII telemetry; PRD-005
# RBAC adds to this in STORY-009; PRD-008 STORY-002 adds session_id; PRD-009
# STORY-002 adds dedup_key; PRD-011 STORY-009 adds pattern_role and
# pattern_action; PRD-012 STORY-011 adds profile; PRD-013 STORY-002 adds
# ingress, message_count, input_tokens, output_tokens, streamed,
# has_tool_calls, conversation_key and limit_exceeded). CREATE TABLE IF NOT
# EXISTS is a no-op against a database created before they existed, so
# init_db() ALTERs in whichever of these an old file is missing.
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
    # PRD-011 (D6): which role's message a pattern hit was found in (`user`,
    # `tool`, `system`, `assistant`) and what the profile did about it (`block`
    # or `flag`). Needed because a `flag` row sets suspicious_pattern without
    # blocking, so that column alone no longer means "blocked". Nullable with
    # no default on purpose, like dedup_key: rows written before PRD-011 stay
    # NULL and are never backfilled, and `pattern_action IS NULL` means
    # "block" for every one of them -- each such row carrying a pattern was a
    # block. The counters read it that way as of STORY-010.
    "pattern_role": "TEXT",
    "pattern_action": "TEXT",
    # PRD-012 (D9): the profile that ran -- the name the call site passed,
    # after default resolution (`chat` for /query and the chat UI). It is what
    # tells a reader that `pii_detected_output = 0` under `code` means "not
    # analyzed" rather than "clean". Nullable with no default on purpose, like
    # dedup_key: rows written before PRD-012 stay NULL and are never
    # backfilled, and so does /query's foreign-session refusal, which writes
    # before any profile exists.
    "profile": "TEXT",
    # PRD-013 (Section 6.2): which door the request came through -- `query`,
    # `chat` or `v1`, named by the call site and never by a request field.
    # Nullable with no default on purpose, like dedup_key: rows written before
    # PRD-013 stay NULL and are never backfilled, and so does a direct call
    # that passed none.
    "ingress": "TEXT",
    # PRD-013: `len(messages)` as received, before redaction. Nullable for the
    # same reason: nothing recorded the count for an earlier row, and 0 would
    # claim a request with no messages.
    "message_count": "INTEGER",
    # PRD-013: `usage.prompt_tokens` and `usage.completion_tokens`. Nullable
    # because NULL has two true meanings that 0 would erase: no upstream call
    # was made, or the provider omitted the split. tokens_used is unchanged
    # and stays the reported total.
    "input_tokens": "INTEGER",
    "output_tokens": "INTEGER",
    # PRD-013: the response was delivered as SSE; the request or response
    # carried tool calls. NOT NULL DEFAULT 0, unlike the six around them,
    # because 0 is true of every row written before them: neither was
    # possible. Always 0 until PRD-014 and PRD-016 respectively.
    "streamed": "INTEGER NOT NULL DEFAULT 0",
    "has_tool_calls": "INTEGER NOT NULL DEFAULT 0",
    # PRD-013 (Section 6.3): the grouping key over the user id and the
    # conversation's opening turns. Nullable and never backfilled: an earlier
    # row kept only the last turn's hash, so its key cannot be derived. Not
    # indexed (PRD Section 4, Out of Scope).
    "conversation_key": "TEXT",
    # PRD-013 (D6): `requests` or `tokens` on a usage-limit refusal, NULL on
    # every other row. It is the dedicated verdict column that lets that row
    # be success=1. Nullable with no default: NULL is "not a usage-limit row",
    # which is every earlier row.
    #
    # Nothing writes a non-default value into these eight yet: log_query gains
    # the parameters in STORY-005.
    "limit_exceeded": "TEXT",
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
    created_at TEXT NOT NULL,
    token_budget_daily INTEGER,
    requests_per_minute INTEGER
)
"""

# UNIQUE, not merely indexed: it serves the lookup path (no table scan) and makes
# two users sharing a credential an IntegrityError at write time rather than an
# arbitrary winner at read time.
CREATE_USERS_TOKEN_HASH_INDEX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_token_hash ON users(token_hash)"
)

# The third added-columns mapping (PRD-013 STORY-008, Section 6.6): the two
# per-user limit overrides. CREATE TABLE IF NOT EXISTS is a no-op against a
# users table created before this PRD, so init_db() ALTERs them in through the
# same _add_missing_columns() the audit_logs and chat_messages mappings use.
#
# Every entry here is also declared in CREATE_USERS_TABLE above, for the reason
# AUDIT_LOGS_ADDED_COLUMNS gives: this brings an old database up to date, the
# CREATE is what a fresh one is built to.
#
# Nullable with no default on purpose. NULL means "use the role's limit from
# USAGE_DAILY_TOKEN_BUDGET / USAGE_REQUESTS_PER_MINUTE", which is the true
# value for every user that existed before this column did. A default of any
# number would silently give every existing user an override. Additive only.
#
# Nothing reads them yet: app/services/identity.py carries them on Identity,
# and usage_limits.limits_for consumes them in STORY-010.
USERS_ADDED_COLUMNS = {
    "token_budget_daily": "INTEGER",
    "requests_per_minute": "INTEGER",
}

# Usage counters (PRD-013 Section 6.5, D3). One row per user per UTC day, and
# the same row also holds the fixed one-minute rate window -- that is what lets
# the gate be one statement: app/db/database.py's _ADMIT_USAGE_SQL increments
# both counters and reads back everything both checks need in a single
# round trip.
#
# `day` and `window_start` are only ever written from the database clock
# (`date('now')`, `strftime('%s','now') / 60`), never from Python, so instances
# with skewed clocks cannot split a day or a window.
#
# user_id and day declare NOT NULL explicitly, for the reason the users table
# gives above: outside INTEGER PRIMARY KEY, SQLite lets a PRIMARY KEY column
# hold NULL. The composite key is the only access path -- admit and charge both
# address one (user_id, day) -- so there is no further index.
#
# No foreign key to users, for the reason the chat tables give below, and for
# one of its own: the break-glass `admin` identity has no users row and is
# still counted (PRD Section 6.6).
#
# A new table, so it arrives by CREATE alone and has no added-columns mapping.
# No cleanup: the window is overwritten in place, and day rows accumulate at
# one per active user per day -- they are what the usage view (STORY-016) reads.
CREATE_USAGE_DAILY_TABLE = """
CREATE TABLE IF NOT EXISTS usage_daily (
    user_id TEXT NOT NULL,
    day TEXT NOT NULL,                       -- 'YYYY-MM-DD', UTC, from the database clock
    requests INTEGER NOT NULL DEFAULT 0,     -- authorized attempts today
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    unsplit_tokens INTEGER NOT NULL DEFAULT 0,   -- total_tokens of calls with no split reported
    window_start INTEGER NOT NULL,           -- unix minute of the current rate window
    window_requests INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
)
"""

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
    # PRD-011 STORY-009. Same pattern as dedup_key: insert_audit_log() writes
    # both and _row_to_audit_log() maps them back on both read shapes. Set only
    # by the pattern block and flag arms; NULL on every other row. Not exposed
    # on GET /audit or the admin console until STORY-010. Declared after
    # dedup_key to mirror the table, so id stays the trailing field.
    pattern_role: Optional[str] = None
    pattern_action: Optional[str] = None
    # PRD-012 STORY-011 (D9). Same pattern as pattern_action: insert_audit_log()
    # writes it and _row_to_audit_log() maps it back on both read shapes. Set
    # on every row run_conversation writes; NULL on rows written before
    # PRD-012 and on /query's foreign-session refusal. Declared after
    # pattern_action to mirror the table, so id stays the trailing field.
    profile: Optional[str] = None
    # PRD-013 STORY-002 (Section 6.2). Same pattern as profile:
    # insert_audit_log() writes all eight and _row_to_audit_log() maps them
    # back on both read shapes. Nothing sets a non-default value until
    # STORY-005. The two flags are bool, like pii_detected_input. Declared
    # after profile to mirror the table, so id stays the trailing field.
    ingress: Optional[str] = None
    message_count: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    streamed: bool = False
    has_tool_calls: bool = False
    conversation_key: Optional[str] = None
    limit_exceeded: Optional[str] = None
    id: Optional[int] = None


@dataclass
class User:
    user_id: str
    role: str
    token_hash: str
    active: bool = True
    created_at: Optional[str] = None  # insert_user() stamps it when omitted
    # PRD-013 STORY-008: per-user limit overrides. None means "use the role's".
    # Declared after created_at so positional construction keeps working.
    # Written only by set_user_limits(); insert_user() leaves them NULL.
    token_budget_daily: Optional[int] = None
    requests_per_minute: Optional[int] = None


@dataclass(frozen=True)
class UsageAdmission:
    """What one admit_usage() call counted and read back (PRD-013 Section 6.5).

    Everything the rate and budget checks need, from one statement. Every field
    comes from the database, so none has a default. `day` is the day the
    attempt was counted against, which is the day charge_usage() must charge.
    Nothing here compares a limit: STORY-010's usage_limits does that.
    """

    day: str
    window_start: int
    window_requests: int
    tokens_today: int


@dataclass(frozen=True)
class UsageDay:
    """One user's counters for the database's current UTC day, as
    usage_snapshot() reads them (PRD-013 STORY-016, Section 6.10).

    Raw facts only: the per-user overrides as stored, and no resolved limit.
    Section 6.6 resolves limits in Python with `usage_limits.limits_for`, the
    function the gate itself calls, so the usage view and the gate cannot
    disagree about a budget.

    `role is None` means the user has no `users` row. The break-glass `admin`
    identity is the expected case: it is counted (Section 6.6) but never
    inserted. `denied` counts today's audit rows with `limit_exceeded` set.
    """

    user_id: str
    role: Optional[str]
    token_budget_daily: Optional[int]
    requests_per_minute: Optional[int]
    requests: int
    input_tokens: int
    output_tokens: int
    unsplit_tokens: int
    denied: int


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
