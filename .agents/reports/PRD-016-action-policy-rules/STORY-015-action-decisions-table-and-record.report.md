---
story: STORY-015
prd: PRD-016
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-015-action-decisions-table-and-record.plan.md
epic_branch: epic/PRD-016-action-policy-rules
commit: pending
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-015: action_decisions table, indexes, record() and read functions

**Plan**: `.agents/plans/PRD-016-action-policy-rules/completed/STORY-015-action-decisions-table-and-record.plan.md`
**Epic Branch**: `epic/PRD-016-action-policy-rules`
**Commit**: `pending`

## Summary

The decision audit (PRD-016 Sections 4, 6.10, F10, D8):

- `app/db/models.py`: `CREATE_ACTION_DECISIONS_TABLE` (Section 6.10 plus `reason TEXT NOT NULL` after `rule`), the two 6.10 indexes, `ACTION_DECISION_VALUES`, and a frozen `ActionDecisionRow`. A comment block in the `usage_daily` style explains why there is no foreign key and no added-columns mapping.
- `app/db/database.py`: `init_db()` creates the table and both indexes last, in its one `_session()` block. New functions:
  - `insert_action_decisions(rows)`: one transaction, one `INSERT` per row, `lastrowid` ids in input order, and `[]` opens no session.
  - `list_action_decisions(limit=100, user_id=None, decision=None)`: `ORDER BY id DESC`.
  - `count_action_decisions()`: returns `{allow, flag, deny}`, with 0 for any decision that has no rows.
- New `app/services/action_audit.py`: `record(decisions, identity, audit_id=None, session_id=None) -> list[int]` (the Section 10 signature). It uses one UTC timestamp per call. It reuses `audit_logger`'s `_PREVIEW_LENGTH`/`_TIMESTAMP_FORMAT` and `hash_prompt`. `classifications` is stored as a JSON array of `{rule, kind, detail}`.
  - Redaction (`_redact_url`, `_redact_urls_in`): a string split that never raises. Query and fragment values become `***` and their keys are kept; userinfo becomes `***`. Redaction runs before the cut to 500.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Schema, indexes, vocabulary, row dataclass | `app/db/models.py` | ✅ |
| 2 | init_db + insert/list/count | `app/db/database.py` | ✅ |
| 3 | record() and redaction | `app/services/action_audit.py` | ✅ |
| 4 | Exact table list gains `action_decisions` | `tests/test_two_instance_smoke.py` | ✅ |
| 5 | AC 1–5 tests | `tests/test_action_audit.py` | ✅ |
| 6 | Targeted regression run | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | ✅ `from app.main import app` OK |
| Frontend lint | n/a (no frontend in this repo) |
| Targeted tests | ✅ 78 passed (`test_action_audit.py`, `test_usage_storage.py`, `test_conftest_fixtures.py`, `test_untouched_app.py`, `test_two_instance_smoke.py::test_both_instances_boot_simultaneously_against_one_database`) |
| `test_db.py -k init_db` | ✅ 51 passed, 188 deselected |
| `test_action_audit.py` alone | ✅ 39 passed |
| Full suite | deferred to orchestrator (user decision) |
| E2E | ✅ 3/3 (DB round trip through `record()` → `list_action_decisions` against libSQL; backend import; two instances converge on the six-table schema) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/models.py` | UPDATE | +97 |
| `app/db/database.py` | UPDATE | +146/-1 |
| `app/services/action_audit.py` | CREATE | +188 |
| `tests/test_action_audit.py` | CREATE | +555 |
| `tests/test_two_instance_smoke.py` | UPDATE | +3/-1 |
| `.agents/PRDs/PRD-016-action-policy-rules/PRD.md` | UPDATE (orchestrator edit) | 6.10 DDL gains `reason` |
| `.agents/stories/PRD-016-action-policy-rules/STORY-016-audit-actions-endpoint-and-stats.md` | UPDATE (orchestrator edit) | `reason` is a stored column |

## Deviations from Plan

1. **`arguments_preview` is URL-redacted, not raw** (orchestrator answer to plan Q1). Every `http://`/`https://` substring in the raw arguments goes through `_redact_url` before the cut to 500. The scan is a plain regex that also matches JSON-escaped `\/` slashes and stops at quotes, whitespace and backslashes. `arguments_hash` is still the hash of the full raw string, and apart from URLs the preview is raw (T10).
2. **A non-`http` target also gets the URL scan.** One example is a whole `shell` command such as `make https://x/a?token=…`. Without the scan, `target_preview` would show what `arguments_preview` hides, which goes against the orchestrator's "must not leak what `target_preview` redacts" rule read in reverse. An `http` target still goes through `_redact_url` as a whole, so `net.unparsed` URLs are covered too. Test: `test_a_shell_target_with_a_url_is_redacted_too`.
3. Userinfo masking was kept (Q2). The authority match also accepts a JSON-escaped `\/\/`.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_action_audit.py` | G1: columns + notnull, both indexes, second `init_db` keeps rows, pre-PRD DB gets only the 3 new objects with every existing `sqlite_master.sql` byte-identical, one bootstrap session, vocabulary == `DECISIONS`. G2: three rows/ids in order with identity, audit/session ids, one timestamp; one session holding three INSERTs; `granted_by` for a granted dba. G3: >500 hash/previews, classifications JSON, `tool.unknown` NULLs, http query/fragment redaction in both previews, shell `curl ?token=SECRET` in neither preview, shell target URL scan, JSON-escaped URLs, raw-apart-from-URLs, 11 `_redact_url` cases, redact-before-cut. G4: NULL ids, IntegrityError rollback, injected mid-batch StorageError through `record()` rollback, `[]` opens no session. G5: newest first by id, user/decision/combined filters, limit, frozen rows with every column, counts, empty counts. |
| `tests/test_two_instance_smoke.py` | `test_both_instances_boot_simultaneously_against_one_database`: list gains `action_decisions` (comment cites PRD-016 STORY-015 / D8) |

## Acceptance Criteria

- [x] AC 1: `init_db()` creates `action_decisions` (6.10 columns + `reason`) and both indexes on fresh and pre-PRD databases, alters nothing, and is a no-op the second time.
- [x] AC 2: `record(..., audit_id=7, session_id="s1")` writes three rows in one transaction with the identity, and returns their ids in order.
- [x] AC 3: hash over the full string, 500-character previews, and classifications stored as a JSON `{rule, kind, detail}` array. URL query, fragment and userinfo are redacted in both previews.
- [x] AC 4: an omitted `audit_id`/`session_id` is stored as NULL, and a failure midway writes no row.
- [x] AC 5: the reads filter by user and decision, return newest first by `id`, and the counts match.
