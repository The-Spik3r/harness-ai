---
story: STORY-009
prd: PRD-021
slug: audit-columns
title: Four audit columns for real-time delivery
type: ENHANCEMENT
complexity: medium
epic_branch: epic/PRD-021-realtime-streaming
created: 2026-11-18
---

# Plan: Four audit columns for real-time delivery

## Summary

Append `streamed_realtime`, `reasoning_shown`, `stream_redaction_divergence` (`INTEGER NOT NULL DEFAULT 0`) and `completion_id` (`TEXT NULL`) after PRD-020's five (`provider` ... `usage_estimated`) on exactly PRD-020 D13's path, then make every row-writing arm of `run_conversation` pass them. No new `database.py` public function and no new `get_connection()` caller, so the census in `tests/test_db_resilience_retry.py` is untouched. `GET /audit`, `?completion_id=` and the Register `LIVE` badge are STORY-013.

- Story: `.agents/stories/PRD-021-realtime-streaming/STORY-009-audit-columns.md`
- PRD sections used: F7 (§7), D14, D15, D17, T7, T9
- Systems affected: `app/db/models.py`, `app/db/database.py`, `app/services/audit_logger.py`, `app/services/query_pipeline.py`, `app/routers/query.py`, tests
- Skills: `.agents/skills/` holds only `frontend-design`; not applicable. Story `skills: []`.

## Design Decisions (binding, from the orchestrator)

- Column order everywhere: `..., provider, upstream_model, provider_trust, pii_input_relaxed, usage_estimated, streamed_realtime, reasoning_shown, stream_redaction_divergence, completion_id` (then `id` on `AuditLog`). Rows already stored read `0`/NULL, never backfilled.
- `log_query`: `streamed_realtime: bool` and `reasoning_shown: bool` are REQUIRED keyword-only (no default); `stream_redaction_divergence: bool = False`, `completion_id: Optional[str] = None`. Put a bare `*,` before the new block (after `usage_estimated`, before `journal_decisions`; every caller already passes `journal_decisions` by keyword).
- Values: `streamed_realtime = realtime_request`; `completion_id` stored only when `realtime_request` (else NULL, even though the local is set for any sink); `reasoning_shown` = a non-empty reasoning string reached the sink OR a non-empty whole reasoning was set on the result; `stream_redaction_divergence` = the STORY-008 local. Failure rows record what was true at the fault. Rows before step 7: `realtime_request` as known, `reasoning_shown=0`, `completion_id` NULL.
- INFO at the realtime commit: user id, model, `completion_id`; never content.
- Disconnect needs no redesign (verified, see Task 5).

Facts found in the code that shape the design:
- `visibility` (and so `realtime_request`) is computed at step 2d (`query_pipeline.py:661-669`) but `realtime_request` is currently assigned at step 7 (`:979`, with `# noqa: F841`). Every `_deny` arm (`:520-577`) and the 2c usage refusal (`:627`) run BEFORE 2d, by design (T8: a refused caller computes nothing). For those the value is not known: pass literal `False` with a comment. Arms after 2d use the local.
- **Orchestrator decision (STORY-009 3.2)**: refusal rows at steps 3-6 never opened the upstream, so no content left: they write `streamed_realtime=False`, `completion_id=None` (F7's meaning wins over the earlier binding). `streamed_realtime=realtime_request` applies only to the step 7 failure, step 8 failure and success arms.
- `reasoning_shown` cannot reuse `released` (it also flips on content). Add a local `reasoning_sent = False`, set True at the two `safe.reasoning(...)` sites (`:1052`, `:1069`), only for non-empty text (both are already guarded by `if out:` / `if ...remainder:`).
- The whole (non-realtime) reasoning is `reasoning_text` (`:1089`, redacted, may be empty): success row uses `reasoning_sent or bool(reasoning_text)`. The step-7 and step-8 failure arms pass only `reasoning_sent` (no result is returned there, so a whole reasoning is never delivered).

## Patterns to Follow

| Category | Source | What to mirror |
|---|---|---|
| Added columns + comment style | `app/db/models.py:150-163` (`AUDIT_LOGS_ADDED_COLUMNS` PRD-020 block) | one comment block citing PRD-021 F7/D14/D17, then four entries |
| CREATE | `app/db/models.py:25-45` | append four lines after `usage_estimated INTEGER NOT NULL DEFAULT 0` (add the comma to it) |
| Dataclass | `app/db/models.py:541-548` | defaulted fields before `id` |
| INSERT | `app/db/database.py:1573-1587` (`_INSERT_AUDIT_LOG_SQL`), values tuple `:1670-1681` | add 4 columns and 4 `?` (38 -> 42); `int()` for the three flags |
| Read | `app/db/database.py:1815-1832` (`_row_to_audit_log`) | `bool(row[...])`, `row["completion_id"]` |
| Summary | `app/db/database.py:2276-2283` (json_object), comment above it | four keys after `usage_estimated`; do NOT touch the parameter tuple |
| log_query | `app/services/audit_logger.py:105-113`, entry build `:156-160` | comment block citing PRD-021, pass verbatim into `AuditLog` |
| `_deny` discipline | `query_pipeline.py:363-409` (required, commented params) and its call `:410-427` | two new required params + a comment |
| Tests (migration) | `tests/test_db.py:5215-5360` (`_PRD020_*`, ALTER capture, round trip on both read shapes) | mirror as `_PRD021_*` |
| Tests (pipeline) | `tests/test_query_pipeline_streaming.py` (`setup` fixture `:140`, `_run` `:130`, `_stream` `:98`, `_last_row` `:157`, `_Recorder` `:74`) | add a new file `tests/test_query_pipeline_audit_realtime.py` importing from it, or append there |

## Files to Change

| File | Action | Purpose |
|---|---|---|
| `app/db/models.py` | UPDATE | CREATE DDL (`:44`), `AUDIT_LOGS_ADDED_COLUMNS` (`:162`), `AuditLog` (`:547`) |
| `app/db/database.py` | UPDATE | `_INSERT_AUDIT_LOG_SQL` (`:1584`), values (`:1680`), `_row_to_audit_log` (`:1831`), `_SUMMARY_SQL` (`:2283`) |
| `app/services/audit_logger.py` | UPDATE | `log_query` kwargs and `AuditLog(...)` build |
| `app/services/query_pipeline.py` | UPDATE | `_deny` params, 5 `_deny` callers, 10 direct `log_query` arms, locals, INFO line, drop noqa |
| `app/routers/query.py` | UPDATE | the foreign-session refusal `log_query` (`:168`) needs the two required keywords |
| `tests/test_db.py`, `tests/test_audit_characterization.py`, `tests/test_migrate_to_turso_cli.py`, `tests/test_db_resilience_write_id.py`, `tests/test_query_pipeline_audit_fields.py`, `tests/test_audit_logger.py` | UPDATE | field-order guards and fixtures (Task 6) |
| `tests/test_audit_router.py`, `tests/test_db_resilience_release.py`, other direct `log_query` callers | UPDATE | add the two required kwargs to direct calls |
| `tests/test_query_pipeline_audit_realtime.py` | CREATE | pipeline rows, INFO line, disconnect |

## Tasks

### Task 1: Schema (`app/db/models.py`)
Append to `CREATE_AUDIT_LOGS_TABLE` (`usage_estimated ...,` then `streamed_realtime INTEGER NOT NULL DEFAULT 0, reasoning_shown INTEGER NOT NULL DEFAULT 0, stream_redaction_divergence INTEGER NOT NULL DEFAULT 0, completion_id TEXT`); same four in `AUDIT_LOGS_ADDED_COLUMNS` after `usage_estimated`; `AuditLog` gets `streamed_realtime: bool = False`, `reasoning_shown: bool = False`, `stream_redaction_divergence: bool = False`, `completion_id: Optional[str] = None` before `id` (defaults let an older journaled entry replay: `audit_journal.py:180` does `AuditLog(**obj["audit"])`, serialized from `dataclasses.fields`, so no journal change).
**Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: Storage (`app/db/database.py`)
Extend the INSERT column list and placeholders (38 -> 42), the values tuple (`int(entry.streamed_realtime)`, `int(entry.reasoning_shown)`, `int(entry.stream_redaction_divergence)`, `entry.completion_id`), `_row_to_audit_log`, and the four `json_object` keys. `_add_missing_columns` is generic over the mapping; no change. Check `scripts/` for any hand-written audit column list: `grep -rn "usage_estimated" scripts` found none (the Turso migrator derives columns from the DDL).
**Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_db_resilience_retry.py` (census must stay green, nothing to register).

### Task 3: `log_query` (`app/services/audit_logger.py`)
Add the `*,` block described above with a comment (required for the same reason as the other discipline fields: a forgotten arm must be a `TypeError`, not a row that claims the reply was buffered); pass the four into `AuditLog(...)`.

### Task 4: Pipeline arms (`app/services/query_pipeline.py`)
1. `_deny`: add required `streamed_realtime: bool, reasoning_shown: bool` (before `exc`, after `has_tool_calls`, with the usual comment) and pass them to its `log_query` (`:410`). The five callers (`:520, 532, 544, 555, 577`) pass `streamed_realtime=False, reasoning_shown=False` (before step 2d; nothing known, nothing sent), commented once at the first.
2. After step 2d (`:669`) add `realtime_request = bool(visibility is not None and visibility.realtime)`; delete the assignment at `:979` and its `# noqa: F841  # STORY-009`; update the comment at `:974-977` (columns now exist). Declare `reasoning_sent = False` next to `released` (`:986`); set it at `:1052` and `:1069`. Remove the "no column carries it yet" remark at `:999`.
3. Direct `log_query` arms, all of which must pass `streamed_realtime=` and `reasoning_shown=` explicitly (grep `log_query(` in the module: 11 sites = `_deny` + these 10):
   - `:627` step 2c usage refusal: `False`, `False` (before 2d).
   - `:698` step 3 context limit; `:733` step 4 duplicate; `:791` step 5 pattern block; `:829` step 5 flag; `:883` step 6 redaction limit; `:937` step 6 input-redaction failure: `streamed_realtime=False, reasoning_shown=False` (no upstream opened; orchestrator decision).
   - `:1132` step 7 failure: `streamed_realtime=realtime_request`, `reasoning_shown=reasoning_sent`, `completion_id=completion_id if realtime_request else None`, `stream_redaction_divergence=stream_redaction_divergence` (a gate `PiiRedactorError` after a divergence cannot occur; pass it anyway for uniformity).
   - `:1232` step 8 failure: same four values with `reasoning_shown=reasoning_sent`.
   - `:1279` success: `reasoning_shown=reasoning_sent or bool(reasoning_text)`, the rest as step 7.
   Pre-step-7 arms leave `completion_id`/`stream_redaction_divergence` to their defaults.
4. INFO line at the streamed commit, inside the `if completion_id is None:` block (`:1026-1028`), after `safe.committed(...)`: `if realtime_request: logger.info("realtime stream committed: user_id=%s model=%s completion_id=%s", identity.user_id, model, completion_id)`. Mirror the WARNING at `:1072-1075`. Never a content or reasoning argument.
**Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_query_pipeline_streaming.py tests/test_query_pipeline_delivery.py`

### Task 5: Router refusal and disconnect (`app/routers/query.py`, no pipeline change)
`:168` foreign-session refusal: add `streamed_realtime=False, reasoning_shown=False` (nothing streamed; the rest stays NULL by default, as the existing test at `test_query_pipeline_audit_fields.py:597-612` expects).
Disconnect: verified no change needed. `_SafeSink._call` (`query_pipeline.py:334-340`) swallows any `Exception` from a sink method (one WARNING with user and method, no completion_id), and the loop then continues to `collect()`, step 7b `charge`, and the success `log_query`. `released` flips regardless of the sink's fault, which is what T6 wants. The router-side disconnect handling (sink that stops queueing) is STORY-010.

### Task 6: Tests
- `tests/test_db.py`: add the four names to the expected set (`:1085-1100`); `names[-21:]` -> `names[-25:]` with the four before `"id"` (`:2271-2278`); append four `ALTER ... ADD COLUMN` lines after `usage_estimated` in each ALTER list (`:3055`, `:3317`, and the one ending `:5290` region, plus the `[-5:]` PRD-020 check at `:5290-5296`, which must become a `[-9:]` comparison of both dicts, with a comment citing PRD-021 F7); new `_PRD021_*` constants and a test mirroring `:5215-5360` (ALTER only the missing four on an upgrade DB, old rows read 0/NULL, no ALTER on second `init_db`, fresh DB has them without ALTER, round trip on `SELECT *` and on `summary_snapshot`, `type(...) is bool`).
- `tests/test_audit_characterization.py:126`: add the four to `FIELDS_ADDED_SINCE` (PRD-021 STORY-009).
- `tests/test_migrate_to_turso_cli.py:176`: extend the `_ddl_columns` list and its comment.
- `tests/test_db_resilience_write_id.py:313` (`[-7:]` -> `[-11:]` with the four) and the ALTER list near `:234`.
- `tests/test_query_pipeline_audit_fields.py:231`: add `streamed_realtime`, `reasoning_shown` to the `_deny` required-params parametrize, and a source scan that all 10 direct pipeline `log_query` sites pass both keywords (counts of sites stay 11/12; no new site).
- `tests/test_audit_logger.py`: its wrapper `log_query(*args, **kwargs)` (`:17`) should `kwargs.setdefault("streamed_realtime", False)` and `reasoning_shown` once, with a PRD-021 comment, instead of editing 25 calls; plus new tests: round trip of the four values, defaults for `stream_redaction_divergence`/`completion_id`, and `TypeError` when either required keyword is omitted (call the raw `_log_query_ref`).
- Other direct `log_query` callers (`grep -rn "log_query(" tests`: `test_audit_router.py` x2, `test_db_resilience_release.py` x7, `test_db_resilience_write_id.py` x4, and possibly `test_query_outcomes_regression.py`, `test_query_router.py`, `test_v1_*`; many are mentions or patches, open before editing): add `streamed_realtime=False, reasoning_shown=False`.
- New `tests/test_query_pipeline_audit_realtime.py` (reuse the streaming test fixtures):
  1. realtime success: row `streamed_realtime=True`, `completion_id` equals `rec.of("committed")[0]`, `reasoning_shown` True with reasoning events + both grants, False with only the content grant.
  2. buffered with a sink (`grants=(_SUBMIT,)`) and `sink=None`: `False`, `completion_id is None`, even though a sink got an id (the `committed` id exists; the row is NULL).
  3. non-realtime reasoning (progress-only stream with reasoning granted, whole reasoning on the result) -> `reasoning_shown=True`, `streamed_realtime=False`; empty reasoning text -> False.
  4. divergence: a PII straddling the hold-back (reuse the case from STORY-008's tests) -> `stream_redaction_divergence=True`; clean run -> False.
  5. fault after release: row `success=False`, `streamed_realtime=True`, `completion_id` set, `reasoning_shown=True` when reasoning was released first; fault before any release: `reasoning_shown=False`; `completion_id` NULL if no event arrived (the id is only made on the first event).
  6. step-8 failure row (spy `_redact` to raise `PiiRedactorError` on the buffered/ non-gate path) carries the real values.
  7. denial arms (use `ARM_CASES` style or a denied caller): `streamed_realtime=False`, `reasoning_shown=False`, `completion_id` NULL; step 3 refusal of a would-be realtime request records `streamed_realtime=False` and `completion_id` NULL (orchestrator decision).
  8. INFO line (`caplog`, INFO, logger `app.services.query_pipeline`): exactly one record with user id, `s/m`, and the same id as `committed`, containing none of the prompt/answer text (canary); no such line for buffered runs.
  9. disconnect: a sink whose `content()` raises after the first call (a `_Recorder` subclass): the run returns success, row `success=True`, `tokens_used` equals the stub's usage, and the usage was charged (read `usage_daily` as `test_query_pipeline_streaming.py:327-345` does).
**Validate**: see below.

## End-to-End Tests

- [ ] Drive `run_conversation` with a file-mode registry, `STREAMING_ENABLED=true`, grants incl. `stream:realtime`, a streamed upstream: the stored row (`get_audit_log`) has `streamed_realtime=1`, `completion_id` = the id passed to `sink.committed`.
- [ ] Same request without the grant: row `0`/NULL; and `sink=None`: `0`/NULL (off means today).
- [ ] Existing database upgrade: covered by the `test_db.py` ALTER tests.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider \
  tests/test_query_pipeline_audit_realtime.py tests/test_query_pipeline_streaming.py \
  tests/test_query_pipeline_delivery.py tests/test_query_pipeline_audit_fields.py \
  tests/test_audit_logger.py tests/test_audit_characterization.py tests/test_audit_router.py \
  tests/test_migrate_to_turso_cli.py tests/test_db_resilience_write_id.py \
  tests/test_db_resilience_release.py tests/test_db_resilience_retry.py \
  tests/test_query_pipeline_dedup_key.py tests/test_query_pipeline_pii_profiles.py \
  tests/test_pii_redaction_integration.py tests/test_untouched_app.py
# tests/test_db.py alone is ~12 min: run it separately, or with -k "audit or prd020 or prd021 or alter or add_missing"
```
One pytest at a time. Full suite: GitHub CI.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|---|---|---|
| AC1 four columns in both lists, after PRD-020's five, on `AuditLog` | 1 | `tests/test_db.py` column set, `names[-25:]`, ALTER lists; `test_audit_characterization.py`; `test_migrate_to_turso_cli.py` |
| AC2 upgrade adds them, old rows 0/NULL, fresh DB no ALTER | 1, 2 | new `_PRD021_*` test in `tests/test_db.py` |
| AC3 `_SUMMARY_SQL` and `_row_to_audit_log` keys, params unchanged | 2 | `_PRD021` round trip via `summary_snapshot` in `tests/test_db.py` (existing parameter-tuple guards in `test_db.py` stay green) |
| AC4 required keywords on every arm; success row values | 3, 4, 5 | `test_query_pipeline_audit_fields.py` (scan + `_deny` params); `test_audit_logger.py` TypeError; `test_query_pipeline_audit_realtime.py` 1, 2, 3 |
| AC5 INFO line, never content; disconnect still writes success=1 and charges | 4, 5 | `test_query_pipeline_audit_realtime.py` 8 and 9 |

## Risks / questions for the orchestrator

- Required keywords break every direct `log_query` call in tests (about 14 files had a match; fewer real calls). Mitigated with the wrapper in `test_audit_logger.py` and explicit kwargs elsewhere; enumerate them with `grep -rn "log_query(" tests/` (do not run the full suite to find them).
- The `_SafeSink` fault WARNING (D15 "log the disconnect (user, `completion_id`)") names user and method, not `completion_id`; left as is (router side is STORY-010).
