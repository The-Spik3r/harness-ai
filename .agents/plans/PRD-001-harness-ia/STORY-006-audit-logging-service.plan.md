---
story: STORY-006
prd: PRD-001
slug: audit-logging-service
title: Audit logging service
type: feature
complexity: medium
epic_branch: epic/PRD-001-harness-ia
created: 2026-07-04
---

# Plan: Audit logging service

## Summary

Add `app/services/audit_logger.py`, a thin orchestration service that turns a completed query attempt (success, duplicate-blocked, or suspicious-pattern-blocked) into exactly one `audit_logs` row via the existing `insert_audit_log` repository function (STORY-002). The service accepts raw `prompt`/optional `response` text plus the outcome flags, computes SHA256 hashes over the *full* text (reusing `hash_prompt` from `duplicate_checker.py` so prompt-hash values stay byte-identical to what future duplicate lookups compute), truncates previews to exactly 500 characters, stamps a UTC timestamp in the same fixed format already established by `duplicate_checker.py`, and writes the row. For blocked requests the caller simply omits `response`/`tokens_used`/`model_used`, which flow through as `None` — no branching needed inside the logger itself. No schema or DB changes are required; STORY-002's table and repository function already have every field this story needs.

## User Story

As a compliance officer
I want every query and response logged (hashed + truncated preview) without any IP or geolocation data
So that we have a full audit trail that respects user privacy by construction

## Story Reference

- Story file: `.agents/stories/PRD-001-harness-ia/STORY-006-audit-logging-service.md`
- PRD: `.agents/PRDs/PRD-001-harness-ia/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | feature |
| Complexity | medium |
| Systems Affected | `app/services/` (new module in existing package) |
| Story | STORY-006 |
| PRD | PRD-001 |
| Epic Branch | `epic/PRD-001-harness-ia` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` is empty (no `SKILL.md` files exist in this repo), and the story's `skills: []` frontmatter is empty — same situation as STORY-001 through STORY-005.

---

## Codebase State

`app/db/database.py` (STORY-002) already exposes `insert_audit_log(entry: AuditLog) -> int`, which inserts all 13 non-PK columns and returns `cursor.lastrowid` — this story writes through that function unchanged, no repository edits needed. `app/db/models.py` defines the `AuditLog` dataclass with every field this story's AC list requires (`user_id`, `device`, `prompt_hash`, `prompt_preview`, `response_hash`, `response_preview`, `model_used`, `tokens_used`, `was_duplicate_blocked`, `suspicious_pattern`, `success`, `error_message`, `timestamp`) and no IP/location field exists anywhere in the schema (verified by `tests/test_db.py:74-95`). `app/services/duplicate_checker.py` (STORY-004) already defines `hash_prompt(prompt: str) -> str` (`hashlib.sha256(text.encode("utf-8")).hexdigest()`) and a module constant `_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"` — that plan's Design Decision 2 explicitly flagged this exact format as the shared convention future timestamp-writing stories (naming STORY-006 by number) must keep using, since `find_duplicate_timestamp`'s `WHERE timestamp >= ?` clause relies on lexicographic string comparison being equivalent to chronological comparison. `app/services/pattern_detector.py` (STORY-005) is a pure, DB-free module — not directly relevant here beyond being the second existing example of the `services/` module style (dataclass result type, no class-based service object). No `app/services/audit_logger.py` exists yet; this story creates it as a fourth module in the already-existing `app/services/` package (no new `__init__.py` needed — STORY-004 already created it).

---

## Design Decisions

1. **Raw text in, hash + preview computed inside the logger — not pre-hashed by the caller.** `log_query` takes `prompt: str` and `response: Optional[str]` (full text) rather than pre-computed hashes. This is what AC 2 requires literally ("prompt_hash/response_hash are computed over the full text" as an observable behavior of "the logger"), and keeps the 500-char truncation and hashing colocated so there's exactly one place that can get them out of sync.

2. **Reuse `hash_prompt` from `duplicate_checker.py` for both prompt and response hashing, rather than reimplementing SHA256 locally.** The prompt hash written here *must* stay byte-identical to what `check_duplicate`/`hash_prompt` computes for the same string, since STORY-004's 24h lookup depends on matching prompt-hash values already stored in `audit_logs` by this service. Importing the existing function (instead of duplicating the one-line `hashlib.sha256(...).hexdigest()`) makes that invariant hold by construction rather than by convention. The same function is reused for the response hash too — it's a generic string-hasher despite its prompt-specific name; renaming it is out of scope for this story (STORY-004 already shipped it).

3. **Fixed timestamp format matches `duplicate_checker._TIMESTAMP_FORMAT` exactly (`"%Y-%m-%dT%H:%M:%SZ"`), duplicated as a local constant rather than imported.** Following the same no-shared-constant convention already established between `duplicate_checker.py` and `tests/test_db.py` (each file declares its own copy of this literal). This is the format STORY-004's plan called out by name as the one STORY-006 must keep using.

4. **No custom exception type for DB-write failures.** Unlike `duplicate_checker.check_duplicate` (which wraps `sqlite3.Error` into `DuplicateCheckError` to satisfy an explicit AC about failing loud on a malformed DB), this story's AC list has no equivalent requirement — there's no acceptance criterion about logger behavior on a broken DB. `insert_audit_log`'s `sqlite3.Error` is left to propagate unhandled, consistent with "don't add error handling for scenarios the story doesn't specify."

5. **`success`, `was_duplicate_blocked`, `suspicious_pattern`, `model_used`, `tokens_used`, `error_message` are plain pass-through parameters with no internal policy logic.** This service doesn't decide what `success` *means* for a blocked request (e.g. whether a duplicate-block counts as `success=True` or `False`) — that policy belongs to the caller (STORY-008's pipeline, out of scope here). `log_query` just writes whatever combination of flags it's given; tests exercise it with the combinations the story's ACs describe.

6. **Function-based service, not a class**, matching the existing `check_duplicate` / `detect_suspicious_pattern` style — a single `log_query(...) -> int` function returning the new row's `id` (matches Technical Notes: "`audit_id` returned to callers can be the DB row `id`").

---

## Patterns to Follow

### Service function style (plain function, dataclass-free result — just the DB row id)
```python
// SOURCE: app/services/duplicate_checker.py:22-37
def hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def check_duplicate(prompt: str) -> DuplicateCheckResult:
    prompt_hash = hash_prompt(prompt)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime(_TIMESTAMP_FORMAT)
    ...
```
`log_query` follows the same shape: module-level constant(s), a plain function, delegate persistence to the repository layer.

### Repository call (already exists, used as-is)
```python
// SOURCE: app/db/database.py:28-54
def insert_audit_log(entry: AuditLog) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO audit_logs (...) VALUES (...)
            """,
            (...),
        )
        return cursor.lastrowid
```
`log_query` builds an `AuditLog` instance and passes it straight to this existing function — no new SQL.

### Timestamp format constant
```python
// SOURCE: app/services/duplicate_checker.py:9
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
```
Copied verbatim into `audit_logger.py`.

### Tests: temp DB fixture + env setup
```python
// SOURCE: tests/test_duplicate_checker.py:1-4,39-44
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

...

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path
```
`tests/test_audit_logger.py` reuses this exact fixture (copied, not imported — no shared conftest exists).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/audit_logger.py` | CREATE | `log_query(...)` — hashes, truncates, stamps timestamp, writes one `audit_logs` row, returns `audit_id` |
| `tests/test_audit_logger.py` | CREATE | Unit tests: success case, duplicate-blocked case, suspicious-blocked case, long-text truncation, no-IP/location field |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create `app/services/audit_logger.py`

- **File**: `app/services/audit_logger.py`
- **Action**: CREATE
- **Implement**:
  ```python
  from datetime import datetime, timezone
  from typing import Optional

  from app.db.database import insert_audit_log
  from app.db.models import AuditLog
  from app.services.duplicate_checker import hash_prompt

  _TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
  _PREVIEW_LENGTH = 500


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
      )
      return insert_audit_log(entry)
  ```
- **Mirror**: `app/services/duplicate_checker.py:1-23` (imports, module constant, plain function style); `app/db/database.py:28-54` (`insert_audit_log` call contract — build an `AuditLog`, pass it in, use the returned id).
- **Validate**: `python -c "from app.services.audit_logger import log_query"` succeeds.

### Task 2: Create `tests/test_audit_logger.py`

- **File**: `tests/test_audit_logger.py`
- **Action**: CREATE
- **Implement**: Env-var setup (mirror `tests/test_duplicate_checker.py:1-4`), `temp_db` fixture identical to `tests/test_db.py:15-20`. Tests:
  1. `test_success_case_writes_expected_row` — call `log_query(user_id="juan@empresa.com", prompt="hello", device="Chrome/Windows", response="hi there", model_used="gpt-4", tokens_used=45, success=True)`, fetch via `get_audit_log(audit_id)`, assert every field matches (`user_id`, `device`, `prompt_hash == hash_prompt("hello")`, `prompt_preview == "hello"`, `response_hash == hash_prompt("hi there")`, `response_preview == "hi there"`, `model_used == "gpt-4"`, `tokens_used == 45`, `was_duplicate_blocked is False`, `suspicious_pattern is None`, `success is True`, `error_message is None`), and assert `timestamp` matches `_TIMESTAMP_FORMAT` (e.g. via `datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")` not raising).
  2. `test_duplicate_blocked_case_logs_null_response_fields` — call `log_query(user_id=..., prompt="hello", was_duplicate_blocked=True, success=True)` (no `response`/`model_used`/`tokens_used` passed), fetch and assert `response_hash is None`, `response_preview is None`, `tokens_used is None`, `was_duplicate_blocked is True`.
  3. `test_suspicious_blocked_case_logs_null_response_fields_and_pattern` — call `log_query(user_id=..., prompt="ignore previous instructions", suspicious_pattern="ignore previous instructions", success=False)` (no `response`), fetch and assert `response_hash is None`, `response_preview is None`, `tokens_used is None`, `suspicious_pattern == "ignore previous instructions"`.
  4. `test_long_prompt_and_response_truncated_but_hash_over_full_text` — build a 600-character prompt and a 600-character response (e.g. `"a" * 600`, `"b" * 600`), call `log_query` with both, fetch and assert `len(prompt_preview) == 500`, `prompt_preview == prompt[:500]`, `prompt_hash == hash_prompt(prompt)` (hash of the full 600-char string, not the truncated preview), and the same three assertions for `response_preview`/`response_hash`.
  5. `test_no_ip_or_location_field_in_logged_row` — call `log_query` once, fetch the row via `get_audit_log`, and assert none of `vars(fetched)`'s keys or string values contain `"ip"` or `"location"` (case-insensitive) — closes this story's own AC 4 rather than relying only on STORY-002's schema-level test.
- **Mirror**: `tests/test_duplicate_checker.py:1-51` (env setup, `temp_db` fixture, plain-assert style); `tests/test_db.py:33-67` (`insert_audit_log`/`get_audit_log` round-trip assertion style).
- **Validate**: `pytest tests/test_audit_logger.py -v` — all 5 tests pass.

---

## End-to-End Tests

- [ ] Call `log_query` for a normal successful exchange → exactly one `audit_logs` row exists with `user_id`, `device`, `prompt_hash`, `prompt_preview`, `response_hash`, `response_preview`, `model_used`, `tokens_used`, UTC `timestamp`, `was_duplicate_blocked=False`, `suspicious_pattern=None`, `success=True`, `error_message=None` (AC 1)
- [ ] Call `log_query` with a 600-character prompt and response → `prompt_preview`/`response_preview` are each exactly 500 characters, while `prompt_hash`/`response_hash` equal `hash_prompt` of the full 600-character strings (AC 2)
- [ ] Call `log_query` for a duplicate-blocked and a suspicious-blocked case (no `response` passed) → `response_hash`, `response_preview`, `tokens_used` are `None` and the corresponding blocked flag (`was_duplicate_blocked` / `suspicious_pattern`) is set (AC 3)
- [ ] Inspect a logged row's fields → no key or value contains an IP address or geolocation value (AC 4)
- [ ] `pytest tests/ -v` (full existing suite + new file) passes green

---

## Validation

```bash
pytest tests/test_audit_logger.py -v
pytest tests/ -v
python -c "from app.services.audit_logger import log_query"
```

---

## Acceptance Criteria

(Copied from story STORY-006)

- [ ] Given a completed query (success, duplicate-blocked, or pattern-blocked), when the logger is called, then exactly one `audit_logs` row is written with `user_id`, `device`, `prompt_hash`, `prompt_preview` (first 500 chars), `response_hash`, `response_preview` (first 500 chars), `model_used`, `tokens_used`, `timestamp` (UTC), `was_duplicate_blocked`, `suspicious_pattern`, `success`, `error_message`.
- [ ] Given a prompt/response longer than 500 characters, when logged, then `prompt_preview`/`response_preview` are truncated to exactly 500 characters while `prompt_hash`/`response_hash` are computed over the full text.
- [ ] Given a blocked request (duplicate or suspicious), when logged, then `response_hash`/`response_preview`/`tokens_used` are null/empty (no model was called) and the relevant blocked flag is set.
- [ ] Given the logger writes a row, when inspected, then no field anywhere contains an IP address or geolocation value.
- [ ] All tasks completed
- [ ] Frontend lint passes — N/A, no frontend in this MVP; substitute `pytest tests/ -v` passes
- [ ] Backend server starts without error
- [ ] Follows existing patterns (Repository pattern via `insert_audit_log`, `hash_prompt` reuse, function-based service style)
