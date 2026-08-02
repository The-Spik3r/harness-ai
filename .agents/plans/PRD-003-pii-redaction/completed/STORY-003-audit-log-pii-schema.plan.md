---
story: STORY-003
prd: PRD-003
slug: audit-log-pii-schema
title: "audit_logs schema: PII telemetry columns"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-003-pii-redaction        # all stories commit here, no per-story branch
created: 2026-07-31
---

# Plan: audit_logs schema — PII telemetry columns

## Summary

Add three telemetry columns to the `audit_logs` table — `pii_detected_input`, `pii_detected_output`, `pii_entities` — plus the matching `AuditLog` dataclass fields, and thread them through `insert_audit_log()` and `_row_to_audit_log()` so they round-trip. This is a pure persistence-layer story: it only widens the schema so [[STORY-004]] (audit logger writes the values) and [[STORY-009]] (`/audit` + `/stats` read them) have somewhere to put and get the data. Nothing in this story computes, detects, or redacts anything — no Presidio import, no pipeline change, no `duplicate_checker.py` change (PRD Section 9, RF-6). The two booleans mirror the existing `was_duplicate_blocked` column exactly (`INTEGER NOT NULL DEFAULT 0`, `int()` on write, `bool()` on read); `pii_entities` is a nullable `TEXT` holding a comma-joined entity-type list, mirroring how `PII_ENTITIES` is already stored and parsed in `app/config.py:17-22`. All three fields are appended at the end of both the table definition and the dataclass, with defaults, so every existing `AuditLog(...)` / `insert_audit_log(...)` call site keeps working unchanged.

## User Story

As a compliance admin
I want the `audit_logs` table to record whether PII was detected on input/output and which entity types
So that `/stats` and `/audit` can report redaction activity without exposing the masked values themselves (PRD Section 4, RF-8)

## Story Reference

- Story file: `.agents/stories/PRD-003-pii-redaction/STORY-003-audit-log-pii-schema.md`
- PRD: `.agents/PRDs/PRD-003-pii-redaction/PRD.md` — Section 4 (In Scope), Section 6 (Changes to existing modules — `app/db/models.py`), Section 10 (`GET /audit` additions)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | `app/db/models.py`, `app/db/database.py`, `tests/test_db.py` |
| Story | STORY-003 |
| PRD | PRD-003 |
| Epic Branch | `epic/PRD-003-pii-redaction` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` does not exist in this repository (confirmed by directory listing), the story's `skills:` frontmatter field is `[]`, and PRD Section 15 states this explicitly. Same finding as [[STORY-001]] and [[STORY-002]] plans.

---

## Patterns to Follow

### Boolean column declaration (the exact shape to copy)
```sql
-- SOURCE: app/db/models.py:16
    was_duplicate_blocked INTEGER NOT NULL DEFAULT 0,
```
SQLite has no native BOOLEAN type; this schema already encodes booleans as `INTEGER NOT NULL DEFAULT 0`. `pii_detected_input` / `pii_detected_output` use the identical declaration — this satisfies the story's AC1 wording ("boolean, default 0") in the way this codebase already expresses it.

### Nullable text column declaration
```sql
-- SOURCE: app/db/models.py:17
    suspicious_pattern TEXT,
```
`suspicious_pattern` is the closest analogue for `pii_entities`: bare `TEXT`, implicitly nullable, no default. `pii_entities TEXT` follows it exactly.

### Dataclass field ordering + defaults
```python
# SOURCE: app/db/models.py:24-39
@dataclass
class AuditLog:
    timestamp: str
    user_id: str
    prompt_hash: str
    device: Optional[str] = None
    ...
    was_duplicate_blocked: bool = False
    suspicious_pattern: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
    id: Optional[int] = None
```
Three required positional fields first, then every optional field with a default, with `id` deliberately last. New fields go **after `error_message` but before `id`**, preserving `id`-last (see Design Note 2). Booleans are typed `bool` in the dataclass even though the column is `INTEGER` — the conversion happens at the DB boundary, not in the model.

### Write-side boolean conversion
```python
# SOURCE: app/db/database.py:48,50
                int(entry.was_duplicate_blocked),
                ...
                int(entry.success),
```
Every `bool` dataclass field is wrapped in `int()` in the INSERT parameter tuple. `pii_detected_input`/`pii_detected_output` do the same.

### Read-side boolean conversion
```python
# SOURCE: app/db/database.py:83,85
        was_duplicate_blocked=bool(row["was_duplicate_blocked"]),
        ...
        success=bool(row["success"]),
```
`_row_to_audit_log()` wraps integer columns back into `bool`. Nullable text columns (`suspicious_pattern`) are passed through raw with no conversion — `pii_entities` does the same.

### Column-count consistency in the INSERT
```python
# SOURCE: app/db/database.py:31-37
            """
            INSERT INTO audit_logs (
                timestamp, user_id, device, prompt_hash, prompt_preview,
                response_hash, response_preview, model_used, tokens_used,
                was_duplicate_blocked, suspicious_pattern, success, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
```
Explicit column list (never `INSERT INTO audit_logs VALUES (...)`), five columns per line, and a `?` placeholder count that must be bumped 13 → 16.

### Tests: temp-DB fixture + monkeypatched settings singleton
```python
# SOURCE: tests/test_db.py:28-33
@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path
```
Every DB test takes `temp_db` and gets a fresh, schema-current SQLite file per test via `tmp_path`. This is why the test suite is immune to the stale-local-DB risk in Design Note 4.

### Tests: round-trip assertion style
```python
# SOURCE: tests/test_db.py:63-80
    new_id = insert_audit_log(entry)
    fetched = get_audit_log(new_id)

    assert fetched is not None
    assert fetched.id == new_id
    ...
    assert fetched.was_duplicate_blocked is True
```
Insert one fully-populated `AuditLog`, fetch it back, assert field-by-field. Booleans are asserted with `is True` / `is False` (identity, not truthiness) — this is what actually proves the `int()`→`bool()` conversion works rather than returning `1`/`0`.

### Tests: exact-column-set schema assertion (⚠️ this test must be updated — see Design Note 3)
```python
# SOURCE: tests/test_db.py:87-108
def test_schema_has_no_ip_or_location_column(temp_db):
    with get_connection() as conn:
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")]

    expected = {
        "id", "timestamp", "user_id", ..., "error_message",
    }
    assert set(columns) == expected
    assert not any("ip" in c.lower() or "location" in c.lower() for c in columns)
```
This is the one existing test that a schema change *cannot* leave untouched: it asserts set equality against a hardcoded 14-column set.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/models.py` | UPDATE | Append 3 columns to `CREATE_AUDIT_LOGS_TABLE`; append 3 fields with defaults to the `AuditLog` dataclass |
| `app/db/database.py` | UPDATE | Add the 3 columns to `insert_audit_log()`'s column list + placeholder count + parameter tuple; add the 3 fields to `_row_to_audit_log()` |
| `tests/test_db.py` | UPDATE | Extend the `expected` column set in `test_schema_has_no_ip_or_location_column` (14→17); extend the round-trip test to cover the new fields; add a defaults test proving unset fields land as `False`/`False`/`None` |

**Explicitly NOT touched** (story Technical Notes line 41, PRD Section 9 / RF-6):
- `app/services/duplicate_checker.py` and its hash logic — untouched, and no test of it changes
- `app/services/audit_logger.py` — [[STORY-004]]'s scope (it converts a `list[str]` to the joined string; this story only stores whatever string it is handed)
- `app/routers/admin.py` and `app/models/schemas.py` — [[STORY-009]]'s scope (`/audit` and `/stats` field exposure)
- `app/routers/query.py`, `app/services/pii_redactor.py` — nothing in this story imports or knows about Presidio

---

## Design Notes (decisions worth stating up front)

1. **`pii_entities` is `Optional[str]`, not a list — and this story does no joining.** Story AC2 pins the dataclass field type to `Optional[str]`, and the Technical Notes pin the storage format to a comma-joined string ("mirrors how `PII_ENTITIES` env var is parsed", i.e. `app/config.py:20-22`) rather than a JSON column, to keep the schema's all-TEXT/INTEGER simplicity. The `list[str]` → `"A,B"` conversion happens one layer up in `log_query()` ([[STORY-004]] Technical Notes line 38); the `"A,B"` → `list[str]` conversion happens in the response layer ([[STORY-009]], per PRD Section 10 where `/audit` returns `"pii_entities": ["EMAIL_ADDRESS"]`). Adding a split/join helper here would duplicate logic those stories own — so the DB layer stays a dumb pass-through, exactly like `suspicious_pattern`.

2. **New fields go after `error_message` and before `id`, not at the very end of the dataclass.** `id: Optional[int] = None` is deliberately last in the current dataclass (`models.py:39`) because it is the DB-assigned field, not a caller-supplied one; `_row_to_audit_log()` is the only place that passes it, and it does so by keyword. Since every field involved has a default, ordering is free of breakage either way — putting the new fields before `id` preserves the existing "user fields, then `id`" reading order. In the SQL table the columns are appended at the very end (after `error_message`), which is the only option that keeps existing row layouts and `SELECT *` ordering stable.

3. **`test_schema_has_no_ip_or_location_column` must be modified, and this does not violate AC4.** AC4 scopes its "still pass unmodified" guarantee to "existing PRD-001 tests that construct `AuditLog`/call `insert_audit_log()` without the new fields" — i.e. tests exercising the *call contract*. Those (all of `tests/test_db.py`'s aggregate tests, `tests/test_audit_logger.py`, `tests/test_query_router.py`, `tests/test_integration.py`, `tests/test_audit_router.py`, `tests/test_stats_router.py`) pass untouched because every new field has a default. `test_schema_has_no_ip_or_location_column` is a different kind of test: it asserts `set(columns) == expected` against a hardcoded 14-name set, so *any* schema addition fails it by design. Updating its `expected` set to 17 names is the intended maintenance of a schema-pinning test, not a weakening of it. Its second assertion — `not any("ip" in c.lower() or "location" in c.lower())` — was checked against all three new names and still holds unchanged: `pii_detected_input`, `pii_detected_output`, and `pii_entities` contain no `ip` substring (the `i`s are followed by `i`, `_`, or `n`) and no `location` substring. That assertion is the actual privacy guarantee from PRD-001 and must be left exactly as-is.

4. **Risk: an existing local `harness_ai.db` will NOT gain the new columns.** `init_db()` runs `CREATE TABLE IF NOT EXISTS` (`database.py:23-25`) and there is no migration framework — the story's Technical Notes acknowledge this explicitly. A developer machine with a pre-existing `harness_ai.db` (one is present in the repo root; it is gitignored via `*.db`) will keep the old 14-column table, and the new `insert_audit_log()` will fail at runtime with `sqlite3.OperationalError: table audit_logs has no column named pii_detected_input`. **Mitigation**: delete the local `harness_ai.db` (or point `DATABASE_URL` at a fresh path) before running the app after this change — captured as an explicit E2E step below. The automated test suite is unaffected: `temp_db` builds a fresh DB under `tmp_path` for every test (`tests/test_db.py:28-33`). Production/Docker deployments start from an empty volume. This is a known, accepted consequence of PRD-001's no-migrations design, not a new defect introduced here.

5. **`NOT NULL DEFAULT 0` over nullable booleans.** AC1 says "nullable/defaulted"; `NOT NULL DEFAULT 0` is the stricter, defaulted reading and is what `was_duplicate_blocked`/`success` already do. It also means [[STORY-009]]'s future `COUNT(*) ... WHERE pii_detected_input = 1` aggregate (PRD Section 10, `pii_detected_queries`) never has to reason about `NULL`, matching `count_blocked_duplicates()` (`database.py:115-120`) exactly.

6. **No index on the new columns.** No existing column in this schema is indexed, including `prompt_hash` which is queried on every request by `find_duplicate_timestamp()`. Adding one only for telemetry columns would be inconsistent and premature; [[STORY-009]]'s aggregates are `COUNT`s over a small table.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add the three columns to the table definition and the dataclass

- **File**: `app/db/models.py`
- **Action**: UPDATE
- **Implement**:
  - In `CREATE_AUDIT_LOGS_TABLE`, add a comma after `error_message TEXT` (line 19) and append three columns as the last three in the table:
    ```sql
        error_message TEXT,
        pii_detected_input INTEGER NOT NULL DEFAULT 0,
        pii_detected_output INTEGER NOT NULL DEFAULT 0,
        pii_entities TEXT
    )
    ```
  - In the `AuditLog` dataclass, insert three fields after `error_message` (line 38) and before `id` (line 39):
    ```python
        error_message: Optional[str] = None
        pii_detected_input: bool = False
        pii_detected_output: bool = False
        pii_entities: Optional[str] = None
        id: Optional[int] = None
    ```
  - No new imports — `Optional` is already imported (`models.py:2`).
- **Mirror**: `app/db/models.py:16` (`was_duplicate_blocked INTEGER NOT NULL DEFAULT 0`) for the booleans, `app/db/models.py:17` (`suspicious_pattern TEXT`) for `pii_entities`, and `app/db/models.py:35-38` for the dataclass field/default style.
- **Validate**: `cd f:\AI\harness-ai && python -c "from app.db.models import AuditLog; e = AuditLog(timestamp='t', user_id='u', prompt_hash='h'); print(e.pii_detected_input, e.pii_detected_output, e.pii_entities)"` prints `False False None` (proves defaults exist and no existing call site breaks).

### Task 2: Persist the new fields in `insert_audit_log()`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: In `insert_audit_log()` (lines 28-54), extend the column list, the placeholder count (13 → 16), and the parameter tuple:
  ```python
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
                  ...
                  entry.error_message,
                  int(entry.pii_detected_input),
                  int(entry.pii_detected_output),
                  entry.pii_entities,
              ),
          )
  ```
  Count the `?` placeholders explicitly — there must be exactly 16, matching the 16 named columns and 16 tuple elements. Leave every existing line above `entry.error_message` untouched.
- **Mirror**: `app/db/database.py:48,50` — `int(...)` wrapping for `bool` fields; `app/db/database.py:51` — nullable text passed through raw.
- **Validate**: `cd f:\AI\harness-ai && python -m pytest tests/test_db.py -k "insert or count or list or top" -v` — the pre-existing insert/aggregate tests still pass (they call `insert_audit_log()` without the new fields, exercising the defaults path end-to-end).

### Task 3: Hydrate the new fields in `_row_to_audit_log()`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: In `_row_to_audit_log()` (lines 71-87), add three keyword arguments after `error_message=row["error_message"]`:
  ```python
          error_message=row["error_message"],
          pii_detected_input=bool(row["pii_detected_input"]),
          pii_detected_output=bool(row["pii_detected_output"]),
          pii_entities=row["pii_entities"],
      )
  ```
  No change is needed to `get_audit_log()` or `list_audit_logs()` — both use `SELECT *` (lines 93, 109) and delegate to this single mapper, so they pick the new columns up automatically.
- **Mirror**: `app/db/database.py:83,85` — `bool(row[...])` for integer-backed booleans; `app/db/database.py:84` — raw pass-through for nullable text.
- **Validate**: `cd f:\AI\harness-ai && python -m pytest tests/test_db.py -v` — everything except `test_schema_has_no_ip_or_location_column` passes (that one is expected to fail until Task 4; if anything else fails, stop and fix before proceeding).

### Task 4: Update the schema-pinning test to the new 17-column set

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: In `test_schema_has_no_ip_or_location_column` (lines 87-108), add the three new names to the `expected` set, keeping the existing 14 and the existing final assertion **byte-for-byte unchanged**:
  ```python
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
      }
      assert set(columns) == expected
      assert not any("ip" in c.lower() or "location" in c.lower() for c in columns)
  ```
  Do **not** relax `==` to `<=` or `issubset` — the exact-set assertion is the point of this test (Design Note 3). Do **not** modify the `ip`/`location` assertion; it must keep passing on its own merits.
- **Mirror**: `tests/test_db.py:91-108` — same literal-set style, one name per line, alphabetically-irrelevant but schema-ordered.
- **Validate**: `cd f:\AI\harness-ai && python -m pytest tests/test_db.py::test_schema_has_no_ip_or_location_column -v`

### Task 5: Add round-trip and default-value tests for the new fields

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**:
  - Extend the existing `test_insert_and_read_round_trip` (lines 46-80) by adding the three fields to the constructed `AuditLog` and three assertions to the block, keeping every existing line intact:
    ```python
        entry = AuditLog(
            ...
            error_message="upstream timeout",
            pii_detected_input=True,
            pii_detected_output=True,
            pii_entities="EMAIL_ADDRESS,PERSON",
        )
        ...
        assert fetched.pii_detected_input is True
        assert fetched.pii_detected_output is True
        assert fetched.pii_entities == "EMAIL_ADDRESS,PERSON"
    ```
  - Add two new tests immediately after it:
    ```python
    def test_pii_fields_default_when_not_supplied(temp_db):
        new_id = insert_audit_log(
            AuditLog(
                timestamp="2026-07-31T10:00:00Z",
                user_id="a",
                prompt_hash="h1",
            )
        )

        fetched = get_audit_log(new_id)

        assert fetched is not None
        assert fetched.pii_detected_input is False
        assert fetched.pii_detected_output is False
        assert fetched.pii_entities is None


    def test_pii_fields_round_trip_via_list_audit_logs(temp_db):
        insert_audit_log(
            AuditLog(
                timestamp="2026-07-31T11:00:00Z",
                user_id="a",
                prompt_hash="h2",
                pii_detected_input=True,
                pii_detected_output=False,
                pii_entities="PHONE_NUMBER",
            )
        )

        entries = list_audit_logs()

        assert len(entries) == 1
        assert entries[0].pii_detected_input is True
        assert entries[0].pii_detected_output is False
        assert entries[0].pii_entities == "PHONE_NUMBER"
    ```
    `list_audit_logs` and `get_audit_log` are both already imported at `tests/test_db.py:11-24` — no import changes needed. The second test covers AC3's `list_audit_logs()` half explicitly, and its mixed `True`/`False` pair guards against a copy-paste bug that binds the same parameter to both columns.
  - Assert booleans with `is True` / `is False`, never `== True` — identity assertions are what prove `bool()` conversion rather than a raw `1`/`0` leaking through.
- **Mirror**: `tests/test_db.py:46-80` (round-trip shape), `tests/test_db.py:128-145` (`list_audit_logs` usage + `temp_db` fixture), `tests/test_db.py:77,79` (`is True` / `is False` assertion style).
- **Validate**: `cd f:\AI\harness-ai && python -m pytest tests/test_db.py -v` — all tests green, including the three new/extended ones.

### Task 6: Full-suite regression check (AC4)

- **File**: — (no file change)
- **Action**: VERIFY
- **Implement**: Run the whole suite and confirm that **no test file other than `tests/test_db.py` was modified** (`git diff --name-only` must list exactly `app/db/models.py`, `app/db/database.py`, `tests/test_db.py`). Any other test needing a change means a default was missed in Task 1.
- **Mirror**: [[STORY-002]] plan's Task-4 full-suite gate — same "prove the change is invisible to existing callers" discipline.
- **Validate**:
  ```bash
  cd f:\AI\harness-ai
  python -m pytest
  git diff --name-only
  ```

---

## End-to-End Tests

Checks for `/implement` to execute:

- [ ] `python -m pytest tests/test_db.py -v` — all tests pass, including the extended round-trip, the two new PII tests, and the updated 17-column schema test
- [ ] `python -m pytest tests/test_audit_logger.py tests/test_audit_router.py tests/test_stats_router.py tests/test_query_router.py tests/test_integration.py -v` — every downstream consumer of `AuditLog`/`insert_audit_log()` passes **unmodified** (AC4)
- [ ] `python -m pytest` — full suite green
- [ ] `git diff --name-only` — exactly three files changed; `app/services/duplicate_checker.py` is **not** among them (RF-6)
- [ ] **Delete the stale local DB first** (Design Note 4): `rm -f f:/AI/harness-ai/harness_ai.db`, then `uvicorn app.main:app --reload` — server starts without error and `init_db()` creates the 17-column table
- [ ] With the server running: `curl http://localhost:8000/health` → `{"status":"ok"}`
- [ ] Schema spot-check against the real (non-test) DB:
  ```bash
  python -c "import sqlite3; print([r[1] for r in sqlite3.connect('harness_ai.db').execute('PRAGMA table_info(audit_logs)')])"
  ```
  → lists all 17 columns ending in `pii_detected_input`, `pii_detected_output`, `pii_entities`
- [ ] `curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/audit` → still returns 200 with the same response shape as before (this story adds no API fields — that is [[STORY-009]])

---

## Validation

```bash
cd f:\AI\harness-ai
python -m pytest tests/test_db.py -v
python -m pytest
git diff --name-only
rm -f harness_ai.db
uvicorn app.main:app --reload
curl http://localhost:8000/health
```

---

## Acceptance Criteria

(Copied from story STORY-003)

- [ ] Given the `audit_logs` table is created, when inspected, then it has three new nullable/defaulted columns: `pii_detected_input` (boolean, default 0), `pii_detected_output` (boolean, default 0), `pii_entities` (text, stores a serialized list of entity type strings, nullable).
- [ ] Given the `AuditLog` dataclass, when constructed, then it accepts `pii_detected_input: bool = False`, `pii_detected_output: bool = False`, `pii_entities: Optional[str] = None` fields matching the new columns.
- [ ] Given `insert_audit_log()` is called with the new fields populated, when read back via `get_audit_log()`/`list_audit_logs()`, then the values round-trip correctly.
- [ ] Given existing PRD-001 tests that construct `AuditLog`/call `insert_audit_log()` without the new fields, when run, then they still pass unmodified (new fields must have safe defaults).
- [ ] All tasks completed
- [ ] Full test suite (`python -m pytest`) passes
- [ ] Backend server starts without error (after clearing a stale local `harness_ai.db`)
- [ ] `app/services/duplicate_checker.py` untouched (PRD Section 9, RF-6)
- [ ] Only `app/db/models.py`, `app/db/database.py`, and `tests/test_db.py` changed
- [ ] Follows existing patterns (INTEGER-backed booleans with `int()`/`bool()` conversion at the DB boundary, nullable TEXT pass-through, explicit INSERT column list, `temp_db` fixture in tests)
