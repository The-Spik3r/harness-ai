---
story: STORY-003
prd: PRD-003
plan: .agents/plans/PRD-003-pii-redaction/completed/STORY-003-audit-log-pii-schema.plan.md
epic_branch: epic/PRD-003-pii-redaction
commit: c8b1195
status: COMPLETE
completed: 2026-07-31
---

# Implementation Report — STORY-003: audit_logs schema — PII telemetry columns

**Plan**: `.agents/plans/PRD-003-pii-redaction/completed/STORY-003-audit-log-pii-schema.plan.md`
**Epic Branch**: `epic/PRD-003-pii-redaction`
**Commit**: `c8b1195`

## Summary

Added three telemetry columns to the `audit_logs` table — `pii_detected_input`, `pii_detected_output`, `pii_entities` — with matching `AuditLog` dataclass fields, threaded through `insert_audit_log()` and `_row_to_audit_log()` so they round-trip via both `get_audit_log()` and `list_audit_logs()`.

The two booleans mirror the existing `was_duplicate_blocked` column exactly (`INTEGER NOT NULL DEFAULT 0`, `int()` on write, `bool()` on read). `pii_entities` is a nullable `TEXT` column holding a comma-joined entity-type list, passed through raw like `suspicious_pattern` — the `list[str]` ↔ `"A,B"` conversion deliberately stays out of the DB layer, belonging to STORY-004 (write side) and STORY-009 (read side).

All three fields have defaults, so every pre-existing `AuditLog(...)` / `insert_audit_log(...)` call site continues to work unmodified. `app/services/duplicate_checker.py` and its hash logic are untouched (PRD Section 9, RF-6). No Presidio import, no pipeline change, no API-surface change.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Append 3 columns to `CREATE_AUDIT_LOGS_TABLE` + 3 defaulted fields to the `AuditLog` dataclass | `app/db/models.py` | ✅ |
| 2 | Extend `insert_audit_log()` column list, placeholders (13→16), and parameter tuple | `app/db/database.py` | ✅ |
| 3 | Hydrate the 3 new fields in `_row_to_audit_log()` | `app/db/database.py` | ✅ |
| 4 | Update the schema-pinning test's expected column set (14→17) | `tests/test_db.py` | ✅ |
| 5 | Extend round-trip test + add defaults test and `list_audit_logs()` round-trip test | `tests/test_db.py` | ✅ |
| 6 | Full-suite regression + changed-file scope check | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Frontend lint | N/A — no npm frontend in this repo (Reflex/Python project; no `package.json`) |
| Tests | ✅ 122 passed |
| `tests/test_db.py` | ✅ 19 passed (16 pre-existing + 2 new + 1 extended) |
| E2E | ✅ 7/7 |
| Changed-file scope | ✅ exactly `app/db/models.py`, `app/db/database.py`, `tests/test_db.py` |
| `duplicate_checker.py` untouched | ✅ (RF-6) |

### E2E Checklist

| # | Check | Result |
|---|-------|--------|
| 1 | `pytest tests/test_db.py -v` | ✅ 19 passed |
| 2 | Downstream consumers unmodified (`test_audit_logger`, `test_audit_router`, `test_stats_router`, `test_query_router`, `test_integration`) | ✅ pass, zero edits (AC4) |
| 3 | Full suite `pytest` | ✅ 122 passed |
| 4 | `git diff --name-only` scope | ✅ 3 code/test files; `duplicate_checker.py` absent |
| 5 | Delete stale `harness_ai.db`, start `uvicorn app.main:app` | ✅ starts clean; `init_db()` creates the 17-column table |
| 6 | `curl http://localhost:8000/health` | ✅ `{"status":"ok"}` |
| 7 | `PRAGMA table_info(audit_logs)` on the real DB | ✅ 17 columns, ending `pii_detected_input`, `pii_detected_output`, `pii_entities` |
| 8 | `GET /audit` with admin token | ✅ HTTP 200, `{"total":0,"queries":[]}` — response shape unchanged (PII fields are STORY-009) |
| 9 | *(extra)* Live-DB insert round-trip outside `tmp_path` | ✅ `True False 'EMAIL_ADDRESS,PERSON'`, row cleaned up afterward |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/models.py` | UPDATE | +8/-1 |
| `app/db/database.py` | UPDATE | +11/-2 |
| `tests/test_db.py` | UPDATE | +46/-0 |

## Deviations from Plan

1. **Test/validation commands run under `.venv/Scripts/python.exe`, not bare `python`.** The plan's commands used bare `python`, which on this machine resolves to the global Python 3.13 that lacks `presidio-analyzer`. That produced 8 collection errors in every module transitively importing `app.main` → `app.services.pii_redactor` → `presidio_analyzer`. This is a pre-existing environment mismatch introduced by STORY-001/002, entirely unrelated to this story's changes — `tests/test_db.py` itself collected and passed under either interpreter. Re-running under the project's `.venv` gives 122/122. **Future plans for this repo should specify `.venv/Scripts/python.exe`** (or an activated venv) in validation commands.

2. **The stale local `harness_ai.db` was backed up before deletion.** The plan prescribed `rm -f harness_ai.db` (Design Note 4). Before deleting, the file was inspected — it held the old 14-column schema and **0 rows**, so nothing was lost — and copied to the session scratchpad as a precaution. The risk documented in Design Note 4 was confirmed real: the pre-existing DB genuinely lacked the new columns and would have failed at runtime on the first insert.

3. **One extra E2E check beyond the plan** (item 9 above): a live insert/read round-trip against the real `harness_ai.db` rather than a `tmp_path` fixture DB. Design Note 4's risk was specifically a *runtime* insert failure against a non-test DB, which the `temp_db`-based suite structurally cannot exercise. The inserted row was deleted afterward, leaving the DB empty as found.

Otherwise the implementation matched the plan exactly, including the predicted single failure of `test_schema_has_no_ip_or_location_column` after Task 3 (resolved by Task 4).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db.py` | `test_pii_fields_default_when_not_supplied` (NEW) — unset fields persist as `False`/`False`/`None` |
| `tests/test_db.py` | `test_pii_fields_round_trip_via_list_audit_logs` (NEW) — covers AC3's `list_audit_logs()` half; mixed `True`/`False` pair guards against a copy-paste bug binding the same parameter to both boolean columns |
| `tests/test_db.py` | `test_insert_and_read_round_trip` (EXTENDED) — 3 fields added to the constructed `AuditLog`, 3 assertions added |
| `tests/test_db.py` | `test_schema_has_no_ip_or_location_column` (UPDATED) — expected column set 14→17; the `ip`/`location` privacy assertion left byte-for-byte unchanged and still passing |

Booleans are asserted with `is True` / `is False` (identity, not truthiness), which is what actually proves the `int()`→`bool()` conversion rather than a raw `1`/`0` leaking through.

## Acceptance Criteria

- [x] Given the `audit_logs` table is created, when inspected, then it has three new nullable/defaulted columns: `pii_detected_input` (boolean, default 0), `pii_detected_output` (boolean, default 0), `pii_entities` (text, stores a serialized list of entity type strings, nullable).
- [x] Given the `AuditLog` dataclass, when constructed, then it accepts `pii_detected_input: bool = False`, `pii_detected_output: bool = False`, `pii_entities: Optional[str] = None` fields matching the new columns.
- [x] Given `insert_audit_log()` is called with the new fields populated, when read back via `get_audit_log()`/`list_audit_logs()`, then the values round-trip correctly.
- [x] Given existing PRD-001 tests that construct `AuditLog`/call `insert_audit_log()` without the new fields, when run, then they still pass unmodified (new fields must have safe defaults).
- [x] All tasks completed
- [x] Full test suite passes (122 passed)
- [x] Backend server starts without error (after clearing the stale local `harness_ai.db`)
- [x] `app/services/duplicate_checker.py` untouched (PRD Section 9, RF-6)
- [x] Only `app/db/models.py`, `app/db/database.py`, and `tests/test_db.py` changed
- [x] Follows existing patterns (INTEGER-backed booleans with `int()`/`bool()` conversion at the DB boundary, nullable TEXT pass-through, explicit INSERT column list, `temp_db` fixture in tests)

## Notes for Downstream Stories

- **STORY-004** (`audit_logger.py`): `pii_entities` is stored as a plain comma-joined string. `log_query()` owns the `list[str]` → `"A,B"` join. An empty list should join to `""`, not `None` — decide explicitly whether "no PII detected" is stored as `None` or `""`, since STORY-009's split needs to handle whichever is chosen.
- **STORY-009** (`/audit`, `/stats`): the read-side `"A,B"` → `list[str]` split lives in the response layer. `pii_detected_input`/`pii_detected_output` are `NOT NULL DEFAULT 0`, so the `pii_detected_queries` aggregate can use `WHERE pii_detected_input = 1` with no `NULL` handling, exactly like `count_blocked_duplicates()`.
- **Deployment note**: any environment with a pre-existing `harness_ai.db` needs that file deleted (or `DATABASE_URL` repointed) — `init_db()` is `CREATE TABLE IF NOT EXISTS` with no migration framework, so an existing table will not gain the new columns and inserts will fail with `sqlite3.OperationalError`. Worth calling out in STORY-012's README/rollout docs.
