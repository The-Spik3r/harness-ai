---
story: STORY-009
prd: PRD-005
slug: audit-rbac-columns
title: audit_logs gains role and denied_permission columns
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-005-rbac        # all stories commit here, no per-story branch
created: 2026-08-28
---

# Plan: audit_logs gains role and denied_permission columns

## Summary

`audit_logs` needs two new nullable `TEXT` columns — `role` and `denied_permission` — so a denial written by the future `authorize()` step (STORY-010/STORY-015) can be recorded with the same rigor as a served request. The additive-migration mechanism this depends on already exists and was hardened in STORY-001 (`AUDIT_LOGS_ADDED_COLUMNS` + `_add_missing_columns()` in `app/db/database.py`), and its comment at `app/db/models.py:26-33` already anticipates this exact story by name. This plan touches three production files in lockstep — `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS` in `app/db/models.py` (Risk 4's two-places rule), the `AuditLog` dataclass plus `insert_audit_log`/`_row_to_audit_log` in `app/db/database.py`, and two new optional keyword arguments on `log_query()` in `app/services/audit_logger.py` — then proves the contract with a migration test against a fixture built from today's (pre-RBAC) schema, a round-trip test at the `insert_audit_log`/`AuditLog` layer, and a round-trip test at the `log_query()` layer. No existing caller passes positional arguments to `log_query()` (verified in `app/services/query_pipeline.py`), so every current call site is untouched.

## User Story

As a compliance admin
I want the audit schema to carry the acting role and the missing permission
So that a denial is recorded with the same rigor as a served request

## Story Reference

- Story file: `.agents/stories/PRD-005-rbac/STORY-009-audit-rbac-columns.md`
- PRD: `.agents/PRDs/PRD-005-rbac/PRD.md` — Sections 6 and 14 (Risk 4)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (additive schema + plumbing, no new capability wired to a caller yet) |
| Complexity | LOW |
| Systems Affected | `app/db/models.py`, `app/db/database.py`, `app/services/audit_logger.py`, `tests/test_db.py`, `tests/test_audit_logger.py` |
| Story | STORY-009 |
| PRD | PRD-005 |
| Epic Branch | `epic/PRD-005-rbac` (commit directly on this branch) |

**Dependency status**: `depends_on: [STORY-001]` — done (verified: `.agents/stories/PRD-005-rbac/STORY-001-additive-audit-log-migration.md` frontmatter `status: done`). Blocks STORY-010, STORY-015.

---

## Skills In Use

None. `.agents/skills/` contains exactly one skill, `frontend-design`, scoped to UI work. This story touches `app/db/`, `app/services/audit_logger.py`, and `tests/` only. The story's `skills:` frontmatter field is `[]`, consistent with that.

---

## Patterns to Follow

### The migration mechanism this story feeds (do not modify — verified working, STORY-001)
```python
# SOURCE: app/db/database.py:32-48
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
```
This story adds two entries to `AUDIT_LOGS_ADDED_COLUMNS`; the mechanism itself is untouched.

### The two-places rule (Risk 4 — the exact failure mode this story must not repeat)
```python
# SOURCE: app/db/models.py:4-38
CREATE_AUDIT_LOGS_TABLE = """
CREATE TABLE IF NOT EXISTS audit_logs (
    ...
    pii_entities TEXT
)
"""

AUDIT_LOGS_ADDED_COLUMNS = {
    "pii_detected_input": "INTEGER NOT NULL DEFAULT 0",
    "pii_detected_output": "INTEGER NOT NULL DEFAULT 0",
    "pii_entities": "TEXT",
}
```
`CREATE TABLE IF NOT EXISTS` is a no-op against a table that already exists, so a column added only to `CREATE_AUDIT_LOGS_TABLE` never reaches an existing deployment. Both must change together.

### The comment already names this story
```python
# SOURCE: app/db/models.py:26-33
# Columns added after the initial schema shipped (PRD-003 PII telemetry; PRD-005
# RBAC adds to this in STORY-009). CREATE TABLE IF NOT EXISTS is a no-op against
# a database created before they existed, so init_db() ALTERs in whichever of
# these an old file is missing.
# Additive only: no drops, renames, or type changes.
# Every NOT NULL entry needs a non-NULL DEFAULT -- SQLite rejects ADD COLUMN
# NOT NULL without one. Enforced by
# tests/test_db.py::test_added_columns_declaring_not_null_also_declare_a_default.
```
No comment change needed — STORY-001 already generalized it to reference this story by ID.

### The exact PRD-003 precedent for adding optional kwargs to `log_query()`
```python
# SOURCE: app/services/audit_logger.py:12-45
def log_query(
    user_id: str,
    prompt: str,
    device: Optional[str] = None,
    response: Optional[str] = None,
    model_used: Optional[str] = None,
    tokens_used: Optional[int] = None,
    was_duplicate_blocked: bool = False,
    suspicious_pattern: Optional[str] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    pii_detected_input: bool = False,
    pii_detected_output: bool = False,
    pii_entities: Optional[list[str]] = None,
) -> int:
    entry = AuditLog(
        ...
        pii_detected_input=pii_detected_input,
        pii_detected_output=pii_detected_output,
        pii_entities=",".join(pii_entities) if pii_entities else None,
    )
    return insert_audit_log(entry)
```
`role` and `denied_permission` are plain `Optional[str] = None` kwargs, no transform needed (unlike `pii_entities`, which joins a list) — mirror the simpler `suspicious_pattern: Optional[str] = None` shape instead.

### `insert_audit_log` / `_row_to_audit_log` — the lockstep pair
```python
# SOURCE: app/db/database.py:51-81, 98-117
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
            (entry.timestamp, entry.user_id, ..., entry.pii_entities),
        )
        return cursor.lastrowid


def _row_to_audit_log(row: sqlite3.Row) -> AuditLog:
    return AuditLog(
        id=row["id"],
        ...
        pii_entities=row["pii_entities"],
    )
```
Both need the two new columns appended in the same position (end of column list, before nothing — `id` is server-assigned and excluded from `INSERT`).

### Tests: env bootstrap before any `app.*` import
```python
# SOURCE: tests/test_db.py:1-4
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
```

### Tests: the pinned-schema test this story must extend (not delete or loosen)
```python
# SOURCE: tests/test_db.py:309-333
def test_schema_has_no_ip_or_location_column(temp_db):
    with get_connection() as conn:
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")]

    expected = {
        "id", "timestamp", "user_id", "device", "prompt_hash", "prompt_preview",
        "response_hash", "response_preview", "model_used", "tokens_used",
        "was_duplicate_blocked", "suspicious_pattern", "success", "error_message",
        "pii_detected_input", "pii_detected_output", "pii_entities",
    }
    assert set(columns) == expected
    assert not any("ip" in c.lower() or "location" in c.lower() for c in columns)
```
17 names today. This story adds `role` and `denied_permission` to `expected`, making it 19. Neither new name contains `ip` or `location` as a substring (checked), so the second assertion needs no change.

### Tests: the pre-PII legacy fixture (mirror for the new pre-RBAC fixture)
```python
# SOURCE: tests/test_db.py:129-227
def _create_pre_pii_database(db_path) -> None:
    """Builds the 14-column audit_logs table exactly as it shipped before PRD-003."""
    legacy = sqlite3.connect(db_path)
    legacy.execute("""CREATE TABLE audit_logs (...14 columns...)""")
    legacy.execute(
        "INSERT INTO audit_logs (timestamp, user_id, prompt_hash) VALUES (?, ?, ?)",
        ("2026-07-04T10:30:00Z", "juan@empresa.com", "abc123"),
    )
    legacy.commit()
    legacy.close()


def test_init_db_migrates_pre_pii_database(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    _create_pre_pii_database(db_path)

    init_db()

    with get_connection() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")}
    assert {"pii_detected_input", "pii_detected_output", "pii_entities"} <= columns
    assert count_audit_logs() == 1
    preserved = get_audit_log(1)
    assert preserved.user_id == "juan@empresa.com"
    assert preserved.pii_detected_input is False
    assert preserved.pii_entities is None
```
This story's new migration test builds the fixture at today's **17-column** shape (raw SQL, bypassing `get_connection()`, exactly as `_create_pre_pii_database` does) — that is what "pre-RBAC" means, since PRD-003's PII columns already shipped.

### Tests: boolean/None identity assertions
```python
# SOURCE: tests/test_db.py:268-283
def test_pii_fields_default_when_not_supplied(temp_db):
    ...
    assert fetched.pii_detected_input is False
    assert fetched.pii_entities is None
```
`is None`, never falsy-checked — same idiom applies to `role`/`denied_permission` defaulting.

### Tests: `log_query()`-level round trip (mirror for role/denied_permission)
```python
# SOURCE: tests/test_audit_logger.py:131-162
def test_pii_telemetry_persisted_when_supplied(temp_db):
    audit_id = log_query(
        user_id="juan@empresa.com",
        prompt="my email is juan@empresa.com",
        ...
        pii_detected_input=True,
        pii_detected_output=True,
        pii_entities=["EMAIL_ADDRESS", "PERSON"],
    )
    fetched = get_audit_log(audit_id)
    assert fetched.pii_detected_input is True
    ...


def test_pii_telemetry_defaults_when_omitted(temp_db):
    audit_id = log_query(user_id="juan@empresa.com", prompt="hello", response="hi there")
    fetched = get_audit_log(audit_id)
    assert fetched.pii_detected_input is False
    ...
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/models.py` | UPDATE | Add `role TEXT` and `denied_permission TEXT` to `CREATE_AUDIT_LOGS_TABLE`; add both to `AUDIT_LOGS_ADDED_COLUMNS`; add both fields to the `AuditLog` dataclass |
| `app/db/database.py` | UPDATE | Add `role`, `denied_permission` to the `INSERT INTO audit_logs` column list + values tuple in `insert_audit_log`; add both to the `AuditLog(...)` construction in `_row_to_audit_log` |
| `app/services/audit_logger.py` | UPDATE | Add `role: Optional[str] = None` and `denied_permission: Optional[str] = None` keyword arguments to `log_query()`; pass through to `AuditLog(...)` |
| `tests/test_db.py` | UPDATE | Extend `test_schema_has_no_ip_or_location_column` to 19 columns; add a pre-RBAC migration fixture + test; add round-trip and default tests for the two new `AuditLog`/`insert_audit_log` fields |
| `tests/test_audit_logger.py` | UPDATE | Add round-trip and default tests for `role`/`denied_permission` through `log_query()` |

**Explicitly NOT touched**:
- `app/services/query_pipeline.py` — none of its six `log_query(...)` calls pass `role`/`denied_permission` yet; wiring the `authorize()` denial path through the pipeline is STORY-010/STORY-015's scope, not this story's. Verified every call site uses keyword arguments only, so adding new optional kwargs to `log_query()` is invisible to it.
- `app/routers/admin.py`, `app/models/schemas.py` — exposing `role`/`denied_permission` through `/audit`'s response shape (`AuditQueryEntry`) is downstream scope (PRD Section 10 example JSON), not this story's.
- `_add_missing_columns()` itself — the mechanism is correct and hardened (STORY-001); only its data (`AUDIT_LOGS_ADDED_COLUMNS`) changes here.

---

## Design Notes (decisions worth stating up front)

1. **Both new columns are plain nullable `TEXT`, no `DEFAULT` needed.** The AC requires "both nullable so historical rows stay valid" — a bare `TEXT` column with no `NOT NULL` already defaults to `NULL` on `ALTER TABLE ... ADD COLUMN`, exactly like the existing `pii_entities` entry. This also means `test_added_columns_declaring_not_null_also_declare_a_default` (the STORY-001 guard) passes trivially — neither new entry declares `NOT NULL`.

2. **Column placement: append at the end, in both places, in the same order.** `ALTER TABLE ... ADD COLUMN` always appends to the end of a table's column list — there is no way to insert a column in the middle of an existing table. So `CREATE_AUDIT_LOGS_TABLE` must place `role`/`denied_permission` after `pii_entities` too, or a fresh database and a migrated database would disagree on column order (harmless for named-column SQL, but a needless divergence `PRAGMA table_info` would expose). `role` before `denied_permission` in both places, matching the AC's own ordering ("`role TEXT` and `denied_permission TEXT`").

3. **`AuditLog` field order: after `pii_entities`, before `id`.** Every field in the dataclass already has a default except the three required ones declared first (`timestamp`, `user_id`, `prompt_hash`); `id: Optional[int] = None` is deliberately last as the "assigned after the fact" field. `role`/`denied_permission` are optional data like the PII fields, so they belong in that same optional-field block, immediately before `id` — not before it, since nothing about `id`'s position should change.

4. **`log_query()` new kwargs go after `pii_entities`, not interleaved.** All ten optional kwargs are keyword-only in practice (no caller in this codebase uses positional args — verified against every call site in `query_pipeline.py`), so position has no functional effect, but appending at the end keeps the diff minimal and matches "exactly how PRD-003 added the PII telemetry arguments" from the story's Technical Notes.

5. **"Pre-RBAC database" means today's 17-column schema, not the pre-PII 14-column one.** `_create_pre_pii_database` (already in `tests/test_db.py`) fixtures the schema from *before* PRD-003 — the wrong baseline for this story, since PRD-003 already shipped on `main`. A new `_create_pre_rbac_database` helper is needed, fixturing the current 17-column shape (i.e., `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS` exactly as they read on `main` today, before this plan's Task 1 edit) via raw `sqlite3.connect`, so the test proves migration from *today's real shape* forward, not from two migrations ago.

6. **No new test duplicates `test_add_missing_columns_applies_any_declared_column` or the idempotency test.** STORY-001 already proved the mechanism applies *any* declared column (via a synthetic column) and stays idempotent across repeated `init_db()` calls, generically — those tests do not need STORY-009-specific counterparts. This story's new migration test proves the *specific* AC2 claim (both real columns land, via the mechanism, against a realistic fixture), which is a different and still-necessary assertion.

7. **`role`/`denied_permission` are not validated against the role/permission matrix at this layer.** `app/db/models.py` and `app/services/audit_logger.py` treat both as opaque strings — no `Role` enum, no `Permission` constant import. `app/services/authz.py` (STORY-006/007, already shipped) owns those types; coupling the audit schema to them would create an import from `app/db/` into `app/services/authz.py` that does not exist today and is not needed for storage. The caller (STORY-010/015) is responsible for passing a value that came from `authz.py`.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add the two columns to `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS`

- **File**: `app/db/models.py`
- **Action**: UPDATE
- **Implement**:
  - In `CREATE_AUDIT_LOGS_TABLE`, change the last two lines from:
    ```python
        pii_entities TEXT
    )
    """
    ```
    to:
    ```python
        pii_entities TEXT,
        role TEXT,
        denied_permission TEXT
    )
    """
    ```
  - In `AUDIT_LOGS_ADDED_COLUMNS`, add two entries after `"pii_entities"`:
    ```python
    AUDIT_LOGS_ADDED_COLUMNS = {
        "pii_detected_input": "INTEGER NOT NULL DEFAULT 0",
        "pii_detected_output": "INTEGER NOT NULL DEFAULT 0",
        "pii_entities": "TEXT",
        "role": "TEXT",
        "denied_permission": "TEXT",
    }
    ```
  - Leave the comment block above `AUDIT_LOGS_ADDED_COLUMNS` (lines 26-33) untouched — it already names this story.
- **Mirror**: `app/db/models.py:4-38` (table DDL), `app/db/models.py:34-38` (mapping) — both already shown above under Patterns to Follow.
- **Validate**: `.venv/Scripts/python.exe -c "from app.db.models import AUDIT_LOGS_ADDED_COLUMNS, CREATE_AUDIT_LOGS_TABLE; print(AUDIT_LOGS_ADDED_COLUMNS); assert 'role' in CREATE_AUDIT_LOGS_TABLE and 'denied_permission' in CREATE_AUDIT_LOGS_TABLE"`

### Task 2: Add `role`/`denied_permission` to the `AuditLog` dataclass

- **File**: `app/db/models.py`
- **Action**: UPDATE
- **Implement**: In the `AuditLog` dataclass, insert two fields immediately before `id: Optional[int] = None`:
  ```python
      pii_entities: Optional[str] = None
      role: Optional[str] = None
      denied_permission: Optional[str] = None
      id: Optional[int] = None
  ```
- **Mirror**: `app/db/models.py:81-84` (the existing `pii_*` fields immediately before `id`).
- **Validate**: `.venv/Scripts/python.exe -c "from app.db.models import AuditLog; a = AuditLog(timestamp='t', user_id='u', prompt_hash='h'); print(a.role, a.denied_permission)"` — prints `None None`.

### Task 3: Wire the two columns through `insert_audit_log` and `_row_to_audit_log`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  - In `insert_audit_log`, extend the `INSERT INTO audit_logs` column list and `VALUES` placeholders, and append the two new values to the parameter tuple:
    ```python
    def insert_audit_log(entry: AuditLog) -> int:
        with get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO audit_logs (
                    timestamp, user_id, device, prompt_hash, prompt_preview,
                    response_hash, response_preview, model_used, tokens_used,
                    was_duplicate_blocked, suspicious_pattern, success, error_message,
                    pii_detected_input, pii_detected_output, pii_entities,
                    role, denied_permission
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    entry.role,
                    entry.denied_permission,
                ),
            )
            return cursor.lastrowid
    ```
  - In `_row_to_audit_log`, add the two fields to the returned `AuditLog(...)`:
    ```python
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
            role=row["role"],
            denied_permission=row["denied_permission"],
        )
    ```
- **Mirror**: `app/db/database.py:51-81` and `app/db/database.py:98-117`, shown above under Patterns to Follow.
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_db.py -q` — expect failures only in `test_schema_has_no_ip_or_location_column` (fixed in Task 6) until that task lands; every other test should still pass since `role`/`denied_permission` default to `None` and no existing call supplies them.

### Task 4: Add `role`/`denied_permission` keyword arguments to `log_query()`

- **File**: `app/services/audit_logger.py`
- **Action**: UPDATE
- **Implement**:
  ```python
  def log_query(
      user_id: str,
      prompt: str,
      device: Optional[str] = None,
      response: Optional[str] = None,
      model_used: Optional[str] = None,
      tokens_used: Optional[int] = None,
      was_duplicate_blocked: bool = False,
      suspicious_pattern: Optional[str] = None,
      success: bool = True,
      error_message: Optional[str] = None,
      pii_detected_input: bool = False,
      pii_detected_output: bool = False,
      pii_entities: Optional[list[str]] = None,
      role: Optional[str] = None,
      denied_permission: Optional[str] = None,
  ) -> int:
      entry = AuditLog(
          timestamp=datetime.now(timezone.utc).strftime(_TIMESTAMP_FORMAT),
          user_id=user_id,
          device=device,
          prompt_hash=hash_prompt(prompt),
          prompt_preview=prompt[:_PREVIEW_LENGTH],
          response_hash=hash_prompt(response) if response is not None else None,
          response_preview=response[:_PREVIEW_LENGTH] if response is not None else None,
          model_used=model_used,
          tokens_used=tokens_used,
          was_duplicate_blocked=was_duplicate_blocked,
          suspicious_pattern=suspicious_pattern,
          success=success,
          error_message=error_message,
          pii_detected_input=pii_detected_input,
          pii_detected_output=pii_detected_output,
          pii_entities=",".join(pii_entities) if pii_entities else None,
          role=role,
          denied_permission=denied_permission,
      )
      return insert_audit_log(entry)
  ```
  No transform needed for either new argument — unlike `pii_entities`, both are already plain strings.
- **Mirror**: `app/services/audit_logger.py:12-45`, shown above under Patterns to Follow.
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_audit_logger.py -q` — all 10 existing tests still pass (no existing caller passes `role`/`denied_permission`, so behavior is unchanged — AC4).

### Task 5: Extend the pinned-schema test to 19 columns

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: In `test_schema_has_no_ip_or_location_column`, add the two new names to `expected`:
  ```python
  def test_schema_has_no_ip_or_location_column(temp_db):
      with get_connection() as conn:
          columns = [row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")]

      expected = {
          "id",
          "timestamp",
          "user_id",
          "device",
          "prompt_hash",
          "prompt_preview",
          "response_hash",
          "response_preview",
          "model_used",
          "tokens_used",
          "was_duplicate_blocked",
          "suspicious_pattern",
          "success",
          "error_message",
          "pii_detected_input",
          "pii_detected_output",
          "pii_entities",
          "role",
          "denied_permission",
      }
      assert set(columns) == expected
      assert not any("ip" in c.lower() or "location" in c.lower() for c in columns)
  ```
  Leave the second assertion exactly as-is — neither `role` nor `denied_permission` contains `ip` or `location` as a substring.
- **Mirror**: `tests/test_db.py:309-333`, shown above under Patterns to Follow. This is the STORY-001 plan's own predicted handoff (its Design Note 5 / Handoff section named this exact edit).
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_db.py::test_schema_has_no_ip_or_location_column -v`

### Task 6: Add the pre-RBAC migration fixture and test (AC2)

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: Add a module-level helper immediately after `_create_pre_pii_database`, then a test immediately after `test_init_db_migrates_pre_pii_database`:
  ```python
  def _create_pre_rbac_database(db_path) -> None:
      """Builds the 17-column audit_logs table exactly as it ships on `main`
      today -- i.e. after PRD-003's PII columns, before this story's role /
      denied_permission columns. This is the correct "pre-RBAC" baseline;
      _create_pre_pii_database fixtures an older, pre-PII shape instead.
      """
      legacy = sqlite3.connect(db_path)
      legacy.execute(
          """
          CREATE TABLE audit_logs (
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
      )
      legacy.execute(
          "INSERT INTO audit_logs (timestamp, user_id, prompt_hash) VALUES (?, ?, ?)",
          ("2026-08-20T09:00:00Z", "ana@empresa.com", "xyz789"),
      )
      legacy.commit()
      legacy.close()


  def test_init_db_migrates_pre_rbac_database(tmp_path, monkeypatch):
      """A database created before PRD-005 gains role/denied_permission and
      keeps its rows, with NULL in both new fields (AC2).
      """
      db_path = tmp_path / "pre_rbac_audit.db"
      monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")

      _create_pre_rbac_database(db_path)

      init_db()

      with get_connection() as conn:
          columns = {row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")}
      assert {"role", "denied_permission"} <= columns

      assert count_audit_logs() == 1
      preserved = get_audit_log(1)
      assert preserved.user_id == "ana@empresa.com"
      assert preserved.role is None
      assert preserved.denied_permission is None

      insert_audit_log(
          AuditLog(
              timestamp="2026-08-20T09:30:00Z",
              user_id="bob@empresa.com",
              prompt_hash="def000",
              role="user",
              denied_permission="query:byok",
          )
      )
      assert count_audit_logs() == 2
  ```
- **Mirror**: `tests/test_db.py:129-199` (`_create_pre_pii_database` + `test_init_db_migrates_pre_pii_database`), shown above under Patterns to Follow — same shape, different baseline schema (Design Note 5).
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_db.py::test_init_db_migrates_pre_rbac_database -v`

### Task 7: Add round-trip and default tests at the `AuditLog`/`insert_audit_log` layer (AC1, AC3)

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: Add after `test_pii_fields_round_trip_via_list_audit_logs`:
  ```python
  def test_role_and_denied_permission_default_to_none(temp_db):
      new_id = insert_audit_log(
          AuditLog(
              timestamp="2026-08-28T12:00:00Z",
              user_id="a",
              prompt_hash="h3",
          )
      )

      fetched = get_audit_log(new_id)

      assert fetched is not None
      assert fetched.role is None
      assert fetched.denied_permission is None


  def test_role_and_denied_permission_round_trip(temp_db):
      new_id = insert_audit_log(
          AuditLog(
              timestamp="2026-08-28T12:05:00Z",
              user_id="ana@empresa.com",
              prompt_hash="h4",
              success=True,
              role="user",
              denied_permission="query:byok",
          )
      )

      fetched = get_audit_log(new_id)

      assert fetched is not None
      assert fetched.role == "user"
      assert fetched.denied_permission == "query:byok"

      # And via list_audit_logs, the other read path (AuditQueryEntry's future source).
      entries = list_audit_logs()
      assert entries[0].role == "user"
      assert entries[0].denied_permission == "query:byok"
  ```
- **Mirror**: `tests/test_db.py:268-303` (`test_pii_fields_default_when_not_supplied`, `test_pii_fields_round_trip_via_list_audit_logs`), shown above under Patterns to Follow.
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_db.py -k "role_and_denied" -v`

### Task 8: Add round-trip and default tests at the `log_query()` layer (AC3, AC4)

- **File**: `tests/test_audit_logger.py`
- **Action**: UPDATE
- **Implement**: Add at the end of the file:
  ```python
  def test_role_and_denied_permission_persisted_when_supplied(temp_db):
      audit_id = log_query(
          user_id="ana@empresa.com",
          prompt="give me the admin key",
          success=True,
          role="user",
          denied_permission="query:byok",
      )

      fetched = get_audit_log(audit_id)

      assert fetched is not None
      assert fetched.role == "user"
      assert fetched.denied_permission == "query:byok"


  def test_role_and_denied_permission_default_to_none_when_omitted(temp_db):
      audit_id = log_query(
          user_id="juan@empresa.com",
          prompt="hello",
          response="hi there",
      )

      fetched = get_audit_log(audit_id)

      assert fetched.role is None
      assert fetched.denied_permission is None
  ```
- **Mirror**: `tests/test_audit_logger.py:131-162` (`test_pii_telemetry_persisted_when_supplied`, `test_pii_telemetry_defaults_when_omitted`), shown above under Patterns to Follow.
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_audit_logger.py -k "role_and_denied" -v`

### Task 9: Full-suite regression and diff gate

- **File**: — (no file change)
- **Action**: VERIFY
- **Implement**:
  - Run the entire suite. Baseline today: `tests/test_db.py` 50 passed, `tests/test_audit_logger.py` 10 passed, full suite 342 passed. Expect `tests/test_db.py` at 50 + 3 = **53 passed** (Task 6 adds 1, Task 7 adds 2), `tests/test_audit_logger.py` at 10 + 2 = **12 passed** (Task 8), full suite at 342 + 5 = **347 passed**.
  - No test outside `tests/test_db.py` and `tests/test_audit_logger.py` should change or fail — confirms AC4 ("every existing caller and test is unmodified") holds for the rest of the suite, particularly `tests/test_query_router.py`, `tests/test_chat_state.py`, and `tests/test_admin_auth.py`, which exercise `log_query()`/`list_audit_logs()` indirectly through the pipeline and admin router.
  - `git diff --name-only` must list **exactly**: `app/db/models.py`, `app/db/database.py`, `app/services/audit_logger.py`, `tests/test_db.py`, `tests/test_audit_logger.py`.
- **Mirror**: `.agents/plans/PRD-005-rbac/completed/STORY-001-additive-audit-log-migration.plan.md` Task 7 — same "prove the change is invisible to existing callers" gate.
- **Validate**:
  ```bash
  cd /f/AI/harness-ai
  .venv/Scripts/python.exe -m pytest tests/test_db.py tests/test_audit_logger.py -v
  .venv/Scripts/python.exe -m pytest -q
  git diff --name-only
  ```

---

## End-to-End Tests

Checks for `/implement` to execute:

- [ ] `.venv/Scripts/python.exe -m pytest tests/test_db.py -v` — 53 tests pass (50 existing + 3 new: Task 6 migration test, Task 7's two round-trip/default tests)
- [ ] `.venv/Scripts/python.exe -m pytest tests/test_audit_logger.py -v` — 12 tests pass (10 existing + 2 new from Task 8)
- [ ] `.venv/Scripts/python.exe -m pytest -q` — full suite green at 347 (342 baseline + 5 new)
- [ ] `git diff --name-only` — exactly the five files listed in Task 9; nothing in `app/services/query_pipeline.py`, `app/routers/`, or `chat_ui/`
- [ ] Migration against a real file, not just a `tmp_path` fixture:
  ```bash
  .venv/Scripts/python.exe -c "import sqlite3; c=sqlite3.connect('probe_rbac.db'); c.executescript(\"CREATE TABLE audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, user_id TEXT NOT NULL, device TEXT, prompt_hash TEXT NOT NULL, prompt_preview TEXT, response_hash TEXT, response_preview TEXT, model_used TEXT, tokens_used INTEGER, was_duplicate_blocked INTEGER NOT NULL DEFAULT 0, suspicious_pattern TEXT, success INTEGER NOT NULL DEFAULT 1, error_message TEXT, pii_detected_input INTEGER NOT NULL DEFAULT 0, pii_detected_output INTEGER NOT NULL DEFAULT 0, pii_entities TEXT); INSERT INTO audit_logs (timestamp,user_id,prompt_hash) VALUES ('2026-08-20T09:00:00Z','probe','h');\"); c.commit()"
  DATABASE_URL=sqlite:///probe_rbac.db .venv/Scripts/python.exe -c "from app.db.database import init_db, count_audit_logs, get_connection; init_db(); init_db(); print(len([r['name'] for r in get_connection().execute('PRAGMA table_info(audit_logs)')]), count_audit_logs())"
  ```
  expect `19 1`; then delete `probe_rbac.db`
- [ ] `uvicorn app.main:app --reload` — starts without error; `init_db()` in the lifespan migrates the repo-root `harness_ai.db` in place (additive)
- [ ] `curl http://localhost:8000/health` — returns `{"status":"ok"}`
- [ ] `.venv/Scripts/python.exe -c "import sqlite3; print([r[1] for r in sqlite3.connect('harness_ai.db').execute('PRAGMA table_info(audit_logs)')])"` — 19 columns, no duplicates, includes `role` and `denied_permission`

---

## Validation

```bash
cd /f/AI/harness-ai
.venv/Scripts/python.exe -m pytest tests/test_db.py tests/test_audit_logger.py -v
.venv/Scripts/python.exe -m pytest -q
git diff --name-only
curl http://localhost:8000/health
```

---

## Handoff to downstream stories

- **STORY-010/STORY-015** (pipeline and ingress wiring) call `log_query(..., role=identity.role, denied_permission=permission)` from the new `authorize()` denial branch inside `run_query(...)`. `log_query()` and the full storage path are ready; nothing further is needed in `app/db/` or `app/services/audit_logger.py`.
- **`/audit` scoping** (also downstream, per PRD Section 10's example JSON showing `role`/`denied_permission` in an audit entry) will need `AuditQueryEntry` in `app/models/schemas.py` and the list comprehension in `app/routers/admin.py:get_audit()` extended to surface `log.role`/`log.denied_permission` — both fields are already readable off every `AuditLog` returned by `list_audit_logs()` after this story, so that wiring is a small, isolated addition when it happens.

---

## Acceptance Criteria

(Copied from story `STORY-009`)

- [ ] Given a fresh database, when `init_db()` runs, then `CREATE_AUDIT_LOGS_TABLE` includes `role TEXT` and `denied_permission TEXT`, both nullable so historical rows stay valid — *Task 1*
- [ ] Given a pre-RBAC database file, when `init_db()` runs, then both columns are added through `AUDIT_LOGS_ADDED_COLUMNS` and existing rows keep their data with `NULL` in the new fields — *Task 1 (mapping), Task 6 (test)*
- [ ] Given `log_query()` is called with `role` and `denied_permission`, when the row is read back, then both values round-trip through `_row_to_audit_log` — *Task 3 (`_row_to_audit_log`), Task 4 (`log_query`), Task 7 + Task 8 (tests)*
- [ ] Given `log_query()` is called without them, when it runs, then behavior is identical to today and every existing caller and test is unmodified — *Task 4 (both kwargs default to `None`), Task 9 (full-suite gate proves no existing test changed)*
- [ ] All tasks completed
- [ ] Backend server starts without error
- [ ] Full pytest suite green (347 tests)
- [ ] Follows existing patterns
