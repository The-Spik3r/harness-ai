---
story: STORY-008
prd: PRD-016
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-008-sql-classifier.plan.md
epic_branch: epic/PRD-016-action-policy-rules
commit: a45ae85
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-008: SQL classifier with sqlglot — read, write, unscoped write, DDL, DCL, unparsed

**Plan**: `.agents/plans/PRD-016-action-policy-rules/completed/STORY-008-sql-classifier.plan.md`
**Epic Branch**: `epic/PRD-016-action-policy-rules`
**Commit**: `a45ae85`

## Summary

New pure module `app/services/action_classifiers/sql.py` with `classify_sql(statement, dialect, *, source_tool="") -> tuple[Classification, ...]`. It parses once with sqlglot and maps each statement by expression class, through an explicit table, to `sql.read` / `sql.write` / `sql.unscoped_write` / `sql.ddl` / `sql.dcl`. Everything else is `sql.unparsed`: `exp.Command`, an unmapped class, a parse error, any exception. The function never raises. `UPDATE`/`DELETE` count as scoped only when `WHERE` is present and `simplify()` does not reduce it to `TRUE`. The narrow carve-outs the real library forces:
- `exp.Command` `SHOW` is a read.
- `EXPLAIN` re-classifies its inner text: it is a read only if the inner text is all reads. `EXPLAIN ANALYZE`, nested and empty `EXPLAIN`s are unparsed.
- Transaction control is a read (orchestrator decision 3).

An embedded walk catches data-modifying CTEs and `SELECT … INTO`. A `logging.Filter` keeps sqlglot's "falling back to Command" warning, which embeds the statement, out of the logs. `SQL_DIALECTS` is the sqlglot dialect registry. `action_config._check_sql_dialect()` runs first in `load()`, file or no file, and refuses any `ACTION_SQL_DIALECT` that is not empty and not an exact member of `SQL_DIALECTS`.

### sqlglot version and verification

`sqlglot==30.27.0`, uploaded to PyPI 2026-10-30. It is the newest release at least two weeks old on 2026-11-15. It is pure Python with no dependencies (`pip show`: `Requires:` empty). The PRD's assumptions were checked against the installed library:
- **`exp.Command` fallback**: confirmed. `VACUUM`, `CALL p()`, `RENAME TABLE`, `CREATE USER`, and generic `EXPLAIN`/`SHOW` parse as `exp.Command`. `test_a_command_is_unparsed_whatever_sqlglot_says` pins this.
- **`where` arg on `Update`/`Delete`**: confirmed. It is `args["where"]`, an `exp.Where` whose `.this` is the condition, or `None` when absent.
- `DR/**/OP TABLE t` raises `ParseError`, which classifies as unparsed. Deep nesting raises `RecursionError`, so the catch is `except Exception`.
- The full probe table is in the plan's "sqlglot verification" section.

### Transaction control (orchestrator decision 3), as probed on 30.27.0

| Statement | sqlglot class | Handling |
|---|---|---|
| `BEGIN`, `BEGIN TRANSACTION`, `BEGIN WORK`, mysql `START TRANSACTION` | `exp.Transaction` | mapped → `sql.read` (detail `BEGIN`) |
| `COMMIT`, `COMMIT WORK`, postgres `END` | `exp.Commit` | mapped → `sql.read` (`COMMIT`) |
| `ROLLBACK`, `ROLLBACK TO [SAVEPOINT] s` | `exp.Rollback` | mapped → `sql.read` (`ROLLBACK`) |
| generic `START TRANSACTION`, `SAVEPOINT s`, `RELEASE s` | **`exp.Alias(Column(START/SAVEPOINT/RELEASE), <ident>)`**, a column alias, not a `Command` | structural carve-out: an unquoted identifier head, no table qualifier, an unquoted alias, and the alias must be `TRANSACTION` for `START` → `sql.read` |
| tsql bare `BEGIN` | `exp.Command('BEGIN')`, empty tail | `Command` carve-out, only when the tail is empty → `sql.read`. tsql `BEGIN DELETE … END` stays unparsed |
| `RELEASE SAVEPOINT s`, generic `START TRANSACTION READ WRITE` | `ParseError` | unparsed (fails closed; known gap) |
| `SET …`, `SET ROLE`, `SET search_path`, `USE db` | `exp.Set` / `exp.Use` | unmapped → `sql.unparsed` (kept, per the decision) |

A quirk of the structural match: `START AS TRANSACTION`, which no database accepts, also reads as `sql.read`. It changes no data.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Pin sqlglot | `requirements.txt` | ✅ |
| 2 | Classifier, `SQL_DIALECTS`, log filter | `app/services/action_classifiers/sql.py` | ✅ |
| 3 | `_check_sql_dialect()` first in `load()`; docstrings | `app/services/action_config.py` | ✅ |
| 4 | Classifier tests | `tests/test_action_sql.py` | ✅ |
| 5 | Dialect tests; module docstring | `tests/test_action_config.py` | ✅ |
| 6 | Targeted regression | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Targeted: `test_action_sql`, `test_action_config`, `test_action_vocabulary`, `test_action_adapters`, `test_config`, `test_untouched_app` | ✅ 1126 passed, 0 failed, 0 skipped (5.88 s) |
| Lifespans: `test_main`, `test_chat_ui_startup_guard` | ✅ 36 passed (133.75 s) |
| Full suite | deferred to orchestrator (user decision) |
| E2E | ✅ 3/3: `ACTION_SQL_DIALECT=nosuchdb` → `ActionConfigError` listing the 33 dialects; `postgres` loads; the probe table spot-run through `classify_sql` matches the plan |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `requirements.txt` | UPDATE | +1 |
| `app/services/action_classifiers/sql.py` | CREATE | +336 |
| `app/services/action_config.py` | UPDATE | +41/-7 |
| `tests/test_action_sql.py` | CREATE | +396 |
| `tests/test_action_config.py` | UPDATE | +74/-3 |
| `.agents/stories/PRD-016-action-policy-rules/STORY-014-decision-engine.md` | UPDATE (orchestrator edit, staged here) | +1 |
| `.agents/stories/PRD-016-action-policy-rules/STORY-020-docs-and-promotion.md` | UPDATE (orchestrator edit, staged here) | +1 |

## Deviations from Plan

1. **Transaction control is `sql.read`** (orchestrator decision 3), not unparsed. The plan's `BEGIN` case in `test_unparsed` moved to the new `test_transaction_control_is_a_read`. Two forms needed carve-outs: the generic dialect reads `START TRANSACTION` / `SAVEPOINT` / `RELEASE` as `exp.Alias`, which needed a structural match, and tsql reads a bare `BEGIN` as a `Command`. `SET`/`USE` stay unparsed, tested in `test_set_use_and_unrecognised_transaction_forms_are_unparsed`.
2. **Stricter than PRD 6.3** (orchestrator decision 4, accepted): `RENAME TABLE`, `CREATE USER`/`CREATE ROLE`, `DROP USER`, `ALTER USER` and `GRANT role TO u` are `exp.Command`, so they classify as `sql.unparsed` (deny, non-grantable), not `sql.ddl`/`sql.dcl`. `ALTER TABLE … RENAME TO` is `sql.ddl`. `DROP ROLE` under snowflake parses and is `sql.dcl` (detail `DROP ROLE`).
3. **The MERGE `WHEN` actions are skipped in the embedded walk.** sqlglot nests `exp.Update`/`exp.Insert` under `exp.When`, so without the skip `MERGE … WHEN MATCHED THEN UPDATE SET …` would also produce an `sql.unscoped_write`. The `MERGE`'s own `sql.write` covers them.
4. **An inner `EXPLAIN` parse failure is caught locally**, so `SELECT 1; EXPLAIN ANALYZE DELETE FROM t` gives `(sql.read, sql.unparsed)` instead of collapsing the whole input to one unparsed. The decision is deny either way.
5. **`SQL_DIALECTS` includes `dax` and `prql`.** They are registered sqlglot dialects but are not SQL, so nothing parses under them and every statement is `sql.unparsed` (fails closed). They are kept because the AC says "the dialects sqlglot knows". The plan's test (`parse("SELECT 1")` succeeds for every name) was adjusted to assert this.
6. **Log-filter dedup by class name**, not `isinstance`: a module reload makes a new class. Covered by `test_log_filter_does_not_stack_on_reload`.
7. No `get_sql_dialect()` getter was added (orchestrator decision 2): `_check_sql_dialect` stores nothing, so the getter belongs to STORY-014.

Known gaps (orchestrator decision 5, recorded for STORY-020's docs): tautologies the simplifier does not fold (`id = id`) count as scoped; side-effecting functions inside a `SELECT` (`pg_sleep`, `lo_import`) are reads; `ACTION_SQL_DIALECT` is not in `policy_digest`; `RELEASE SAVEPOINT s` and `START TRANSACTION READ WRITE` (generic) are unparsed.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_action_sql.py` (171) | `test_reads`, `test_transaction_control_is_a_read`, `test_transaction_control_does_not_hide_what_it_wraps`, `test_set_use_and_unrecognised_transaction_forms_are_unparsed`, `test_writes`, `test_unscoped_writes`, `test_ddl`, `test_dcl`, `test_multi_statement_in_order`, `test_trailing_semicolon_and_comment_are_skipped`, `test_unparsed`, `test_a_command_is_unparsed_whatever_sqlglot_says`, `test_an_unparseable_explain_does_not_swallow_its_neighbours`, `test_embedded_modifying_cte_is_not_a_read`, `test_explain_of_a_write_is_the_write`, `test_never_raises`, `test_never_raises_when_the_simplifier_fails`, `test_every_rule_produced_is_a_sql_rule`, `test_source_tool_defaults_to_empty`, `test_sql_dialects_are_what_sqlglot_parses`, `test_sqlglot_fallback_warning_does_not_log_the_statement`, `test_log_filter_does_not_stack_on_reload`, `test_log_filter_drops_only_the_fallback_warning`, `test_sql_module_stays_pure`, `test_requirements_pins_sqlglot_exactly` |
| `tests/test_action_config.py` (+8) | `test_load_accepts_a_known_sql_dialect`, `test_empty_sql_dialect_is_the_generic_one`, `test_load_refuses_an_unknown_sql_dialect`, `test_sql_dialect_check_is_exact` (x4), `test_sql_dialect_is_checked_before_the_policy_file` |

## Acceptance Criteria

- [x] The three reads each yield one `sql.read` (`test_reads`)
- [x] Writes → `sql.write`; `DELETE FROM t`, `UPDATE t SET a = 1`, `WHERE 1=1`, `WHERE TRUE` → `sql.unscoped_write` (`test_writes`, `test_unscoped_writes`)
- [x] DROP/TRUNCATE/ALTER/CREATE → `sql.ddl` with the keyword as detail; GRANT/REVOKE → `sql.dcl` (`test_ddl`, `test_dcl`)
- [x] `SELECT 1; DROP TABLE users` → read then ddl; `DR/**/OP`, parse errors, `Command`, unmapped → `sql.unparsed`; never raises (`test_multi_statement_in_order`, `test_unparsed`, `test_a_command_is_unparsed_whatever_sqlglot_says`, `test_never_raises*`)
- [x] `ACTION_SQL_DIALECT=postgres` loads; `nosuchdb` → `ActionConfigError` naming the setting and listing the dialects (`test_load_accepts_a_known_sql_dialect`, `test_load_refuses_an_unknown_sql_dialect`)
- [x] `sqlglot==30.27.0` pinned; version and verification recorded above (`test_requirements_pins_sqlglot_exactly`)
