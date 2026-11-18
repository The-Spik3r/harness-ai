---
story: STORY-006
prd: PRD-020
slug: audit-provider-columns
title: Five provider columns on the audit table and log_query
type: ENHANCEMENT
complexity: medium
epic_branch: epic/PRD-020-provider-registry
created: 2026-11-18
---

# Plan: Five provider columns on the audit table and log_query

## Summary

Add `provider`, `upstream_model`, `provider_trust`, `pii_input_relaxed`, `usage_estimated` to `audit_logs` through the PRD-013/015/018 additive path (declared in both DDL constants), and carry them through `AuditLog`, `insert_audit_log`, `log_query`, both read shapes and `GET /audit`. No caller passes them yet (STORY-007), so every row still stores NULL/NULL/NULL/0/0. No new `database.py` function, so the resilience census is untouched.

- Story: `.agents/stories/PRD-020-provider-registry/STORY-006-audit-provider-columns.md`
- PRD sections used: 7 F5, D13, story Technical Notes
- Systems affected: `app/db/models.py`, `app/db/database.py`, `app/services/audit_logger.py`, `app/models/schemas.py`, `app/routers/admin.py`, tests

## Design Decisions

Orchestrator's binding points, applied as given: five columns in BOTH `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS` in the order `provider TEXT`, `upstream_model TEXT`, `provider_trust TEXT`, `pii_input_relaxed INTEGER NOT NULL DEFAULT 0`, `usage_estimated INTEGER NOT NULL DEFAULT 0`; no backfill, index or CHECK; `AuditLog` fields appended with defaults (`None`,`None`,`None`,`False`,`False`); bools stored `int(...)`, read `bool(row[...])` like `has_tool_calls`; `log_query` gains the five with those defaults; `AuditQueryEntry` gets five verbatim passthroughs.

**Placement interpretation (flag for orchestrator).** "After `has_tool_calls`" is implemented as "after the current tail": append after `write_id` in both DDL constants and in the dataclass (before the trailing `id`), as PRD-015 (`ignored_params`) and PRD-018 (`write_id`) did. Inserting directly after `has_tool_calls` (`models.py:35`, `:116`) would shift `conversation_key`..`write_id` and break the positional slices `tests/test_db.py:3002-3003` (`[-10:-2]`). Both readings are "after has_tool_calls". If the adjacent placement is wanted, say so before implementing.

**`log_query` style.** Its tail is positional-with-defaults, not keyword-only (`journal_decisions` is last). Insert the five before `journal_decisions`, beside `ignored_params`, same style.

**Existing closed-set assertions that must list the five new names.** AC4's "unchanged" cannot hold literally for these; each edit adds a `PRD-020 STORY-006 (D13)` comment and weakens nothing:
- `tests/test_audit_router.py:77` key set of a `/audit` entry (+5 keys).
- `tests/test_db.py:~1087` expected-column set in `test_schema_has_no_ip_or_location_column` (+5).
- `tests/test_db.py:2267` `names[-16:]` becomes `names[-21:]`, five fields before `id`.
- `tests/test_db.py:3002-3003` `[-10:-2]` becomes `[-15:-7]` (the five now trail `write_id`); update the docstring chain.
- `tests/test_audit_characterization.py:116` `FIELDS_ADDED_SINCE` (+5; its docstring says later stories add names here).
- Unaffected: `tests/test_audit_journal.py:211` (derived from `dataclasses.fields`); replay `AuditLog(**obj["audit"])` (`app/db/audit_journal.py:180`) still loads old entries because the new fields default.

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`; story `skills: []`).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| DDL, both places | `app/db/models.py:35`, `:116` | same declaration text in CREATE and mapping, PRD comment per group |
| Dataclass | `app/db/models.py:500-521` | defaulted fields before `id`, "declared after write_id to mirror the table" comment |
| INSERT | `app/db/database.py:1572-1585`, tuple `:1655-1672` | 5 columns, 5 `?` (33 -> 38), tuple in column order, flags `int()` |
| Row mapper | `app/db/database.py:1772-1820` | plain read, flags `bool(row[...])` |
| Summary JSON | `app/db/database.py:2262-2269` | 5 `'key', column` pairs after `'write_id', write_id`; fix the closing `))` |
| log_query | `app/services/audit_logger.py:45-100`, `:114-160` | defaulted params with a comment citing D13 and STORY-007 |
| API model | `app/models/schemas.py:192-262` | `Optional[str] = None` x3, `bool = False` x2, house comment (verbatim passthrough, NULL/False on pre-PRD-020 rows) |
| Projection | `app/routers/admin.py:70-100` | "Verbatim passthrough (PRD-020 D13)" after `ignored_params=` |
| Tests | `tests/test_db.py:2936-3004` (both-places + order), `:3030-3160` (round trip), `:1289-1312` (raw summary JSON) | clone shape for the five |
| Tests | `tests/test_audit_logger.py:360-400` | supplied/omitted round trip via `get_audit_log` |
| Old DB | `tests/test_db.py:553-700` (legacy `CREATE TABLE audit_logs` fixtures) | latest legacy-DB test as template |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/models.py` | UPDATE | 5 columns in CREATE (after `write_id`) and `AUDIT_LOGS_ADDED_COLUMNS`; 5 dataclass fields |
| `app/db/database.py` | UPDATE | INSERT SQL + tuple, `_row_to_audit_log`, `_SUMMARY_SQL`; migration at `:1489` iterates the mapping, no change |
| `app/services/audit_logger.py` | UPDATE | `log_query` params + `AuditLog(...)` |
| `app/models/schemas.py` | UPDATE | `AuditQueryEntry` +5 |
| `app/routers/admin.py` | UPDATE | projection +5 |
| `tests/test_db.py`, `tests/test_audit_logger.py`, `tests/test_audit_router.py`, `tests/test_audit_characterization.py` | UPDATE | new tests and the closed-set edits above |

No new files.

## Tasks

### Task 1: Schema constants and dataclass
- **File**: `app/db/models.py`
- **Implement**: five lines after `write_id TEXT` in the CREATE (comma on `write_id`); five entries after `write_id` in the mapping with a D13 comment (nullable, never backfilled, `0` true of every earlier row, trust vocabulary validated by the registry so no CHECK); five `AuditLog` fields before `id`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_db.py -k "added_columns or declares"`

### Task 2: Writer and readers
- **File**: `app/db/database.py`
- **Implement**: INSERT columns/placeholders (`:1575-1585`), bound tuple (`:1660-1672`), `_row_to_audit_log` (`:1815-1820`), `_SUMMARY_SQL` (`:2269`). Hand-count placeholders; the round-trip test uses two rows with different values per field and opposite flags (as `_PRD013_ROW_A/B`).
- **Validate**: `tests/test_db.py -k "summary or audit"`

### Task 3: log_query
- **File**: `app/services/audit_logger.py`
- **Implement**: five params (see Design Decisions) and pass them into `AuditLog(...)` after `ignored_params=`. Comment: defaulted because no caller passes them until STORY-007, which passes them explicitly.
- **Validate**: `tests/test_audit_logger.py`

### Task 4: API model and projection
- **Files**: `app/models/schemas.py` (after `ignored_params`), `app/routers/admin.py` (after `ignored_params=`)
- **Implement**: five passthroughs, flags default `False`.

### Task 5: Tests
- `tests/test_db.py`: (a) parametrized both-places test for the five (`AUDIT_LOGS_ADDED_COLUMNS[name] == ddl`, `f"{name} {ddl}" in CREATE_AUDIT_LOGS_TABLE`) plus an order test (`[-5:]` of both); (b) fresh `init_db()`: `PRAGMA table_info` shows the five, flags `notnull=1`, `dflt_value='0'`; (c) old-DB convergence from a legacy-table fixture: seed a row, `init_db()`, assert NULL/NULL/NULL/0/0 by raw SELECT and `get_audit_log`; (d) `log_query` with all five then `list_audit_logs` and `get_audit_log` (flags `is True`), and omitted args giving `None,None,None,False,False`; (e) raw `_SUMMARY_SQL` entries carry the five keys and `summary_snapshot().rows == list_audit_logs()` with one set row and one default row.
- `tests/test_audit_router.py`: extend the key set; new test seeding a row via `log_query` with the five set and asserting `GET /audit` as admin passes them through verbatim, plus a default row (mirror `test_audit_entry_carries_pattern_role_and_action`).
- The closed-set edits listed above, each with a PRD-020 comment.
- Census: `tests/test_db_resilience_retry.py:696-741` was read. `len(_EXPECTED_KINDS) == 42` and the public-function set are unchanged since only parameters and columns are added; do not edit it, run it as proof.

## End-to-End Tests

- [ ] `TestClient(app)` `GET /audit` as admin over a row written by `log_query` with all five set: entry carries them; a default row: null/null/null/false/false.
- [ ] `init_db()` twice over a database built from the older DDL: second run is a no-op, five columns present.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_db.py tests/test_audit_logger.py tests/test_audit_router.py tests/test_audit_characterization.py tests/test_audit_stats_prd013.py tests/test_audit_journal.py tests/test_db_resilience_retry.py tests/test_untouched_app.py
```

No test is renamed or removed, so `test_pii_redaction_integration.py` is not required.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 fresh DB + old-DB convergence | 1 | new both-places, fresh-schema, old-DB tests in `tests/test_db.py` |
| AC2 round trip with/without args | 1-3 | new round-trip tests in `tests/test_db.py`, `tests/test_audit_logger.py` |
| AC3 summary keys, no KeyError | 2 | new raw-`_SUMMARY_SQL` + `summary_snapshot` test in `tests/test_db.py` |
| AC4 GET /audit passthrough | 4 | new test in `tests/test_audit_router.py` (key-set extension aside, other assertions unchanged) |
| AC5 census unchanged | none (no new function) | `tests/test_db_resilience_retry.py` green unmodified |

## Risks

- Hand-counted INSERT placeholders (33 -> 38): two rows with different values per field.
- `_SUMMARY_SQL` comma/paren placement: covered by the summary test.
- Journal replay of pre-change entries: safe through defaults; add a one-line journal test only if `tests/test_audit_journal.py` does not already cover missing keys.
