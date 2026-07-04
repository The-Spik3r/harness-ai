---
story: STORY-004
prd: PRD-001
slug: duplicate-detection-service
title: Duplicate detection service (24h exact-match)
type: feature
complexity: medium
epic_branch: epic/PRD-001-harness-ia
created: 2026-07-04
---

# Plan: Duplicate detection service (24h exact-match)

## Summary

Add `app/services/duplicate_checker.py`, the first module in the not-yet-created `app/services/` package. It SHA256-hashes the raw prompt string (no normalization) and asks a new repository function in `app/db/database.py` — `find_duplicate_timestamp(prompt_hash, since)` — whether a row with that exact hash exists with a `timestamp` at or after a computed 24h-ago UTC cutoff. If the earliest such row exists, the service returns a `DuplicateCheckResult(is_duplicate=True, first_query_at=<that row's timestamp>)`; otherwise `is_duplicate=False`. Any unexpected DB failure (e.g. a missing `audit_logs` table) is caught and re-raised as a dedicated `DuplicateCheckError` so a broken DB fails loudly rather than silently reporting "not a duplicate" — this is an explicit acceptance criterion (AC 4) and matches the PRD's "Fail loud, not silent" mission principle. This keeps all SQL inside `db/database.py` (Repository pattern, PRD Section 6) and the service itself is pure orchestration + hashing.

## User Story

As a security admin
I want identical queries blocked if repeated within 24 hours
So that the same prompt can't be used to duplicate-train or duplicate-leak information

## Story Reference

- Story file: `.agents/stories/PRD-001-harness-ia/STORY-004-duplicate-detection-service.md`
- PRD: `.agents/PRDs/PRD-001-harness-ia/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | feature |
| Complexity | medium |
| Systems Affected | `app/services/` (new package), `app/db/database.py` (repository layer) |
| Story | STORY-004 |
| PRD | PRD-001 |
| Epic Branch | `epic/PRD-001-harness-ia` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` is still empty (no `SKILL.md` files exist in this repo), and the story's `skills: []` frontmatter is empty — same situation as STORY-001/002/003.

---

## Codebase State

`app/db/database.py` (STORY-002) currently exposes exactly three repository functions — `init_db()`, `insert_audit_log(entry)`, `get_audit_log(audit_id)` — all opening their own `with get_connection() as conn:` block per call, no shared/pooled connection. `app/db/models.py` defines `CREATE_AUDIT_LOGS_TABLE` and the `AuditLog` dataclass; the `timestamp` column is `TEXT NOT NULL` and every existing test/schema example uses the fixed-width ISO-8601 UTC format `"2026-07-04T10:30:00Z"` (see `tests/test_db.py:35`, `tests/test_schemas.py:51,76`) — no fractional seconds, always a literal `Z` suffix, always `%Y-%m-%dT%H:%M:%SZ`. `app/models/schemas.py` (STORY-003) defines the `QueryBlockedDuplicateResponse` shape (`status`, `reason`, `first_query_at`) that a later story (STORY-008) will populate from this service's output — this story only needs to produce a `first_query_at` string compatible with that field, not construct the response itself. There is no `app/services/` package yet; this story creates it. `tests/test_db.py` establishes the `temp_db` fixture pattern (`tmp_path` + `monkeypatch.setattr(settings, "DATABASE_URL", ...)` + `init_db()`) that new service tests should reuse to get an isolated on-disk SQLite file per test.

---

## Design Decisions

1. **New repository function in `db/database.py`, not raw SQL in the service.** `find_duplicate_timestamp(prompt_hash: str, since: str) -> Optional[str]` runs `SELECT timestamp FROM audit_logs WHERE prompt_hash = ? AND timestamp >= ? ORDER BY timestamp ASC LIMIT 1`, following the exact call/connection style of the existing `get_audit_log`. This preserves PRD Section 6's Repository pattern ("no other module ever writes raw SQL") established by STORY-002.

2. **Fixed ISO-8601 UTC timestamp format, compared lexicographically.** Every timestamp in the codebase so far (`tests/test_db.py`, `tests/test_schemas.py`, PRD examples) is `%Y-%m-%dT%H:%M:%SZ` — fixed-width, always UTC, always `Z`-suffixed. String comparison of two such timestamps is equivalent to chronological comparison, so the cutoff (`now - 24h`, formatted the same way) can be passed straight into the `WHERE timestamp >= ?` clause without parsing every row in Python. This matches the story's Technical Notes query pattern verbatim. Future stories that write timestamps (STORY-006 `audit_logger.py`) must keep using this exact format for the comparison to remain valid — flagged here as a shared convention, not enforced by a shared constant in this story's scope (no such constant exists yet to import).

3. **"Original entry" = earliest matching row inside the 24h window** (`ORDER BY timestamp ASC LIMIT 1`), not the most recent one. This matches the PRD's example (`first_query_at` refers back to the original first attempt, not the just-blocked repeat) and AC 1's wording ("the `first_query_at` of the original entry").

4. **No normalization before hashing.** `hashlib.sha256(prompt.encode("utf-8")).hexdigest()` on the raw string exactly as received — no `.strip()`, `.lower()`, or whitespace collapsing. This is what AC 3 requires (single-character/whitespace differences must produce different hashes) and matches the story's Technical Notes and PRD RF-4 ("match exacto, palabra por palabra").

5. **Fail loud on DB errors — dedicated `DuplicateCheckError`.** The call to `find_duplicate_timestamp` is wrapped in `try/except sqlite3.Error`, re-raising as `DuplicateCheckError(str(e))` (`raise ... from e` to preserve the traceback). This directly satisfies AC 4: an empty file with no `audit_logs` table raises `sqlite3.OperationalError: no such table: audit_logs` from the raw query, and that must surface as a clear, typed error — never get swallowed into a default "not a duplicate" return path.

6. **No injected clock.** `check_duplicate` calls `datetime.now(timezone.utc)` directly rather than accepting a `now` parameter. Simpler, and the story's own Technical Notes describe testing via seeded DB rows at relative offsets, not via clock mocking — consistent with the PRD's "Simple over clever" principle.

---

## Patterns to Follow

### Repository function style
```python
// SOURCE: app/db/database.py:57-79
def get_audit_log(audit_id: int) -> Optional[AuditLog]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM audit_logs WHERE id = ?", (audit_id,)
        ).fetchone()
        if row is None:
            return None
        return AuditLog(...)
```
`find_duplicate_timestamp` follows the same shape: open a connection via `get_connection()`, run one parameterized query, return `None` (or the scalar) on no match.

### Dataclass result types
```python
// SOURCE: app/db/models.py:24-39
@dataclass
class AuditLog:
    timestamp: str
    user_id: str
    prompt_hash: str
    ...
```
`DuplicateCheckResult` is a small `@dataclass` in the same style — typed fields, no behavior beyond data.

### Tests: temp DB fixture
```python
// SOURCE: tests/test_db.py:15-20
@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path
```
`tests/test_duplicate_checker.py` reuses this exact fixture (copied, not imported — `test_db.py` doesn't expose it as a shared conftest fixture) plus one variant that skips `init_db()` to produce the "malformed DB" (missing-table) case for AC 4.

### Env-var setup before import
```python
// SOURCE: tests/test_main.py:1-4
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
```
Same two lines at the top of the new test file, before importing anything from `app`.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/database.py` | UPDATE | Add `find_duplicate_timestamp(prompt_hash, since)` repository function |
| `app/services/__init__.py` | CREATE | Marks `app/services/` as a package |
| `app/services/duplicate_checker.py` | CREATE | `hash_prompt`, `DuplicateCheckResult`, `DuplicateCheckError`, `check_duplicate` |
| `tests/test_duplicate_checker.py` | CREATE | Unit tests: match/no-match, 24h boundary, whitespace-sensitivity, malformed-DB error |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add `find_duplicate_timestamp` to `app/db/database.py`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: Add a new function below `get_audit_log`:
  ```python
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
  ```
  Let any `sqlite3.Error` (e.g. missing table) propagate unhandled — the caller (the service) is responsible for wrapping it into a domain-specific error.
- **Mirror**: `app/db/database.py:57-79` (`get_audit_log`) — same connection-per-call style, same parameterized-query style.
- **Validate**: `python -c "from app.db.database import find_duplicate_timestamp"` succeeds (import-only smoke check; behavior covered by Task 4's tests).

### Task 2: Create `app/services/__init__.py`

- **File**: `app/services/__init__.py`
- **Action**: CREATE
- **Implement**: Empty file — just marks `app/services/` as a package.
- **Mirror**: `app/db/__init__.py` / `app/__init__.py` (same empty-package-marker pattern from STORY-001/002).
- **Validate**: `python -c "import app.services"` succeeds from repo root.

### Task 3: Create `app/services/duplicate_checker.py`

- **File**: `app/services/duplicate_checker.py`
- **Action**: CREATE
- **Implement**:
  - `class DuplicateCheckError(Exception)`: raised when the underlying DB lookup fails unexpectedly (wraps `sqlite3.Error`).
  - `@dataclass class DuplicateCheckResult`: `is_duplicate: bool`, `first_query_at: Optional[str] = None`.
  - `_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"` module constant (documents the fixed format used for the cutoff and for comparison against stored `timestamp` values).
  - `hash_prompt(prompt: str) -> str`: `return hashlib.sha256(prompt.encode("utf-8")).hexdigest()`.
  - `check_duplicate(prompt: str) -> DuplicateCheckResult`:
    ```python
    prompt_hash = hash_prompt(prompt)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime(_TIMESTAMP_FORMAT)
    try:
        match = find_duplicate_timestamp(prompt_hash, cutoff)
    except sqlite3.Error as exc:
        raise DuplicateCheckError(f"Duplicate lookup failed: {exc}") from exc
    if match is None:
        return DuplicateCheckResult(is_duplicate=False)
    return DuplicateCheckResult(is_duplicate=True, first_query_at=match)
    ```
- **Mirror**: `app/db/models.py:24-39` for the dataclass style; `app/db/database.py`'s `from app.config import settings` singleton-import convention (here: `from app.db.database import find_duplicate_timestamp`).
- **Validate**: `python -c "from app.services.duplicate_checker import check_duplicate, hash_prompt, DuplicateCheckResult, DuplicateCheckError"` succeeds.

### Task 4: Create `tests/test_duplicate_checker.py`

- **File**: `tests/test_duplicate_checker.py`
- **Action**: CREATE
- **Implement**: Env-var setup (mirror `tests/test_main.py:1-4`), then a `temp_db` fixture identical to `tests/test_db.py:15-20`. Tests:
  1. `test_no_duplicate_when_no_matching_row` — empty (but initialized) DB, `check_duplicate("hello world")` → `is_duplicate is False`, `first_query_at is None`.
  2. `test_duplicate_detected_within_24h` — insert an `AuditLog` row via `insert_audit_log` with `prompt_hash=hash_prompt("hello world")` and `timestamp` = now-2h (formatted with `_TIMESTAMP_FORMAT`), then `check_duplicate("hello world")` → `is_duplicate is True` and `first_query_at` equals the inserted timestamp.
  3. `test_not_duplicate_when_older_than_24h` — insert a row with `timestamp` = now-25h → `check_duplicate` → `is_duplicate is False`.
  4. `test_boundary_just_inside_24h` — insert a row with `timestamp` = now - 23h59m → `is_duplicate is True`.
  5. `test_boundary_just_outside_24h` — insert a row with `timestamp` = now - 24h01m → `is_duplicate is False`.
  6. `test_whitespace_difference_produces_different_hash_and_not_flagged` — insert a row for `"hello world"`, then call `check_duplicate("hello world ")` (trailing space) → `is_duplicate is False` (also assert `hash_prompt("hello world") != hash_prompt("hello world ")` directly, per AC 3).
  7. `test_earliest_entry_returned_as_first_query_at` — insert two rows for the same hash within the window at different timestamps (e.g. now-10h and now-3h) → `check_duplicate` returns the earlier (now-10h) timestamp as `first_query_at`.
  8. `test_malformed_db_raises_duplicate_check_error` — point `DATABASE_URL` at a fresh `tmp_path` file **without** calling `init_db()` (so `audit_logs` doesn't exist), then assert `check_duplicate("anything")` raises `DuplicateCheckError` (per AC 4 — fails loud, does not silently return "not a duplicate").
- **Mirror**: `tests/test_db.py:1-32` (fixture + env setup), `tests/test_schemas.py` (plain `assert`, no unittest classes, one behavior per test function).
- **Validate**: `pytest tests/test_duplicate_checker.py -v` — all 8 tests pass.

---

## End-to-End Tests

- [ ] Seed a temp DB with a row for prompt `"hello world"` timestamped 2 hours ago → `check_duplicate("hello world")` returns `is_duplicate=True` with `first_query_at` matching the seeded row (AC 1)
- [ ] Seed a temp DB with a row for the same prompt timestamped 25 hours ago (and no other matching row) → `check_duplicate("hello world")` returns `is_duplicate=False` (AC 2)
- [ ] `hash_prompt("hello world")` and `hash_prompt("hello world ")` produce different hex digests, and a check for one never flags a row seeded for the other (AC 3)
- [ ] Calling `check_duplicate` against a DB file with no `audit_logs` table raises `DuplicateCheckError` rather than returning `is_duplicate=False` (AC 4)
- [ ] `pytest tests/ -v` (full existing suite + new file) passes green

---

## Validation

```bash
pytest tests/test_duplicate_checker.py -v
pytest tests/ -v
python -c "from app.services.duplicate_checker import check_duplicate"
```

---

## Acceptance Criteria

(Copied from story STORY-004)

- [ ] Given a prompt hashed with SHA256, when the identical hash exists in `audit_logs` with a `timestamp` within the last 24 hours, then the checker returns a blocked result with the `first_query_at` of the original entry.
- [ ] Given a prompt hashed with SHA256, when no matching hash exists in the last 24 hours (including when it exists but is older than 24h), then the checker returns "not a duplicate."
- [ ] Given two prompts that differ by even a single character/whitespace, when hashed, then they produce different hashes and are never flagged as duplicates (exact word-for-word match only, per PRD Section 4).
- [ ] Given the checker runs, when called with an empty or malformed DB, then it fails safely (raises a clear error) rather than silently treating everything as non-duplicate.
- [ ] All tasks completed
- [ ] Frontend lint passes — N/A, no frontend in this MVP; substitute `pytest tests/ -v` passes
- [ ] Backend server starts without error
- [ ] Follows existing patterns (Repository pattern in `db/database.py`, dataclass result types, `temp_db` test fixture convention)
