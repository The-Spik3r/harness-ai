---
story: STORY-008
prd: PRD-016
slug: sql-classifier
title: SQL classifier with sqlglot — read, write, unscoped write, DDL, DCL, unparsed
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-016-action-policy-rules
created: 2026-11-15
---

# Plan: SQL classifier with sqlglot — read, write, unscoped write, DDL, DCL, unparsed

## Summary

Add `sqlglot==30.27.0` (pure Python, no dependencies) and a pure module `app/services/action_classifiers/sql.py` exposing `classify_sql(statement, dialect, *, source_tool="") -> tuple[Classification, ...]`. It calls `sqlglot.parse(statement, dialect=dialect or None)` once. It maps each parsed statement **by expression class** through an explicit table to `sql.read`, `sql.write`, `sql.unscoped_write`, `sql.ddl` or `sql.dcl`. Everything else becomes `sql.unparsed`: `exp.Command`, any unmapped class, a parse error, or any exception at all (the function never raises). `UPDATE`/`DELETE` count as scoped only when `where` is present and `simplify()` does not reduce it to `TRUE`. Two narrow, tested `exp.Command` carve-outs are needed, because the real library parses `EXPLAIN` and `SHOW` as `Command` in the generic dialect (verified below). After the root statement, the module walks the tree for embedded modifying nodes, so a data-modifying CTE cannot pass as a read. It also exposes `SQL_DIALECTS`, which `action_config.load()` uses to refuse an `ACTION_SQL_DIALECT` sqlglot does not know. That check runs first, whether or not `ACTION_POLICY_FILE` is set.

## User Story

As a security admin
I want SQL in a tool call classified by a parser, statement by statement
So that a `DROP` hidden behind a `SELECT;` or a `DELETE` with no real `WHERE` is caught, and anything the parser cannot read is denied.

## Story Reference

- Story file: `.agents/stories/PRD-016-action-policy-rules/STORY-008-sql-classifier.md`
- PRD: `.agents/PRDs/PRD-016-action-policy-rules/PRD.md`: 4 (line 65), 6.2 (184-218), 6.3 SQL rows (226-231), 6.9 (379-381), F2 (484-485), 8 (524), 9.3 (563), 14 Risk 6 (710), 15 D2 (725), assumption line 746

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `requirements.txt`, `app/services/action_classifiers/sql.py` (new), `app/services/action_config.py`, `tests/test_action_sql.py` (new), `tests/test_action_config.py` |
| Story | STORY-008 |
| PRD | PRD-016 |
| Epic Branch | `epic/PRD-016-action-policy-rules` (commit directly on this branch) |

Dependency STORY-007 (`7e765b7`, report `55edbbc`) is `status: done`.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` (UI aesthetics; description read). No UI here; story frontmatter `skills: []`. | — |

---

## sqlglot verification (done during planning; record it in the story report)

**Version chosen: `sqlglot==30.27.0`**, uploaded to PyPI 2026-10-30T18:18:57. That is the newest release at least two weeks old on 2026-11-15. 30.29.0 (11-03), 30.30.0 (11-06) and 30.31.0 (11-10) are newer than two weeks. The planner installed it into `.venv` (`pip show`: `Requires:` empty, pure-Python wheel). `requirements.txt` is still unedited (Task 1). Probe script: `C:/Users/nahue/AppData/Local/Temp/claude/G--coding-harness-ai/20d13059-18e1-4943-818b-68572342f8ca/scratchpad/probe_sqlglot.py`.

What `sqlglot.parse(s, dialect=None)` returns on 30.27.0 (the generic dialect unless noted):

| Input | Result | Consequence for the mapping |
|---|---|---|
| `SELECT * FROM users WHERE id = 1`, `WITH x AS (SELECT 1) SELECT * FROM x` | `exp.Select` | read |
| `SELECT 1 UNION SELECT 2` | `exp.Union` (an `exp.SetOperation`) | read |
| **`EXPLAIN SELECT 1`** | **`exp.Command(this='EXPLAIN', expression=Literal('SELECT 1'))`**, plus a WARNING log | the AC needs `sql.read`, so a carve-out is required (decision 3) |
| `EXPLAIN SELECT 1` with `dialect='mysql'` | `exp.Describe` | read |
| `EXPLAIN ANALYZE DELETE FROM t` | `Command('EXPLAIN', 'ANALYZE DELETE FROM t')`; re-parsing the inner text raises `ParseError` | falls to unparsed (fail closed; `EXPLAIN ANALYZE` executes) |
| `SHOW TABLES` | `Command('SHOW')` in generic/postgres/sqlite/tsql; `exp.Show` in mysql/snowflake | carve-out plus `exp.Show` mapped (decision 3) |
| `DESCRIBE t`, `DESC t` | `exp.Describe` | read |
| `INSERT INTO t VALUES (1)`, `INSERT … SELECT`, `INSERT … ON CONFLICT DO NOTHING` | `exp.Insert` | write |
| `MERGE INTO t USING s …` | `exp.Merge` | write |
| `UPDATE t SET a = 1 WHERE id = 2` / `DELETE FROM t WHERE id = 3` | `exp.Update` / `exp.Delete`, `args["where"]` is `exp.Where`, `.this` = `EQ` | **assumption confirmed**: `where` arg exists |
| `DELETE FROM t`, `UPDATE t SET a = 1` | `args.get("where") is None` | unscoped |
| `WHERE 1=1`, `WHERE TRUE`, `WHERE 'a'='a'`, `WHERE NOT FALSE`, `WHERE 2>1`, `WHERE 1=1 OR id = 3` | `simplify(where.this.copy())` is `exp.Boolean(this=True)`, `== exp.true()` | unscoped |
| `WHERE 1=1 AND id = 3` | simplifies to `id = 3` | scoped (write) |
| `WHERE id = id` | not simplified (NULL semantics) | scoped (write). A documented limit (Risks) |
| `DROP TABLE users` | `exp.Drop(kind='TABLE')` | ddl `DROP` |
| `TRUNCATE t`, `TRUNCATE TABLE t` | `exp.TruncateTable` | ddl `TRUNCATE` |
| `ALTER TABLE t ADD c INT`, `ALTER TABLE t RENAME TO u` | `exp.Alter(kind='TABLE')` | ddl `ALTER` |
| `CREATE TABLE t (a INT)`, `CREATE INDEX …`, `CREATE VIEW …` | `exp.Create(kind=…)` | ddl `CREATE` |
| `COMMENT ON TABLE t IS 'x'` | `exp.Comment(kind='TABLE')` | ddl `COMMENT` |
| `RENAME TABLE t TO u` | `exp.Command('RENAME')` in all dialects probed | unparsed (still deny). A deviation from 6.3's "RENAME" (Risks) |
| `GRANT ALL ON t TO u` / `REVOKE ALL ON t FROM u` | `exp.Grant` / `exp.Revoke` | dcl |
| `CREATE USER bob`, `CREATE ROLE r`, `DROP USER bob`, `ALTER USER …`, `GRANT r TO u` | `exp.Command` (generic, mysql, postgres, sqlite, tsql) | unparsed (deny, non-grantable, so same outcome as dcl) |
| `DROP ROLE r` with `dialect='snowflake'` | `exp.Drop(kind='ROLE')` | dcl (kind check, decision 5) |
| `SELECT 1; DROP TABLE users` | `[Select, Drop]` | two classifications in order |
| **`DR/**/OP TABLE t`** | **raises `ParseError`** (a `SqlglotError`), not a Command | unparsed. Confirmed |
| `DROP/**/TABLE t`, `/* c */ DROP TABLE t` | `exp.Drop`: comments between whole keywords are stripped | ddl |
| `SELECT FROM WHERE`, `ATTACH DATABASE 'x' AS y`, `LOCK TABLE t`, `REPLACE INTO t VALUES (1)` (generic) | `ParseError` | unparsed |
| `VACUUM`, `CALL p()`, `EXECUTE IMMEDIATE '…'` | `exp.Command` | **`exp.Command` fallback confirmed** → unparsed |
| `SET …`, `USE db`, `BEGIN`, `COMMIT`, `ROLLBACK`, `PRAGMA …`, `COPY t FROM '/etc/passwd'` | `Set`, `Use`, `Transaction`, `Commit`, `Rollback`, `Pragma`, `Copy` | unmapped → unparsed |
| **`WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d`** | **`exp.Select`** (the Delete is nested) | needs the embedded walk (decision 4) |
| `SELECT * INTO new_t FROM t` | `exp.Select` with `args["into"]` set | creates a table: ddl (decision 4) |
| `SELECT * FROM t; -- trailing` | `[Select, exp.Semicolon]` | `Semicolon` and `None` are skipped |
| `''`, `';'`, `'   '`, `'-- c'` | `[None]` | nothing classifiable: one `sql.unparsed` (decision 6) |
| `SELECT ';DROP TABLE t'`, `SELECT 1 /* ; DROP TABLE t */` | one `Select` | correct; `;` inside a string or comment does not split |
| `'SELECT ' + '('*5000 + '1' + ')'*5000` | raises **`RecursionError`** | the catch must be `except Exception`, not `SqlglotError` |

Other library facts:

- **Dialect list API.** `sqlglot.dialects.dialect.Dialect.classes` is the registry `Dialect.get_or_raise` consults. It has 34 keys, including `''` (generic) and `singlestore`, which the public `sqlglot.Dialects` enum (33 values) lacks: athena, bigquery, clickhouse, databricks, dax, doris, dremio, drill, druid, duckdb, dune, exasol, fabric, hive, materialize, mysql, oracle, postgres, presto, prql, redshift, risingwave, singlestore, snowflake, solr, spark, spark2, sqlite, starrocks, tableau, teradata, trino, tsql. `get_or_raise('nosuchdb')` raises `ValueError("Unknown dialect 'nosuchdb'.")`. It is case-sensitive (`'Postgres'` fails with "Did you mean postgres?"). It also accepts a settings suffix: `'mysql, normalization_strategy = lowercase'` parses.
- **Logging leak.** `parser.py:2341-2351` `_warn_unsupported()` calls `logging.getLogger("sqlglot").warning(f"'{sql}' contains unsupported syntax. Falling back to parsing as a 'Command'.")` with up to 100 characters of the **statement text**. This repo redacts PII from logs, so the agent's SQL must not reach the log. A `logging.Filter` added to the `"sqlglot"` logger that drops records whose message contains `"Falling back to parsing as a 'Command'"` was verified to suppress it (decision 8).
- Cost: `import sqlglot` plus the simplifier takes about 0.15 s; one parse of a small `DELETE … WHERE … IN (SELECT …)` takes about 0.2 ms.
- `simplify()` mutates its argument, so always call it on `.copy()`.

---

## Patterns to Follow

| Category | File:Lines | Pattern |
|----------|------------|---------|
| VOCABULARY | `app/services/action_classifiers/__init__.py:46-81, 107-131` | `RuleId` closed `Literal`; frozen `Operation(kind, target, source_tool)`; `Classification(rule, operation, detail)` where `detail` is the matched fragment of the call, never a configured value (T11) |
| PURITY | `app/services/action_classifiers/__init__.py:18-21`; `tests/test_action_vocabulary.py:142-153` | no `settings`, no `open(`/`Path(`, no `app.` import except the package's own vocabulary; asserted by an `inspect.getsource` test |
| SETTING CROSS-CHECK | `app/services/pattern_config.py:534-547` | `_check_default_profile`: reads the setting at call time inside the loader, raises the module's error with `{value!r}` and `(defined …: {_allowed(...)})` |
| ERROR HELPERS | `app/services/action_config.py:350-355` | `_fail(source, *parts)` → `"<source>: a: b"`; `_allowed(values)` sorted, comma-joined |
| LOAD ORDER | `app/services/action_config.py:981-1028` | `path = settings.ACTION_POLICY_FILE`; `if not path: return` (line 1011); `_policy = policy` last |
| LOAD TESTS | `tests/test_action_config.py:125-160` | `monkeypatch.setattr(settings, "ACTION_POLICY_FILE", …)`, `pytest.raises(ActionConfigError) as excinfo`, assert substrings, `get_policy() is BUILT_IN_POLICY` after |
| PIN TEST | `tests/test_config.py:645-658` | read `requirements.txt`, `re.search(r"(?mi)^…")` |
| TEST HEADER | `tests/test_action_vocabulary.py:1-16`; `tests/test_action_config.py:1-25` | docstring citing PRD sections and stating what is *not* covered; literals transcribed from the PRD, not imported |

### Naming
```
# SOURCE: app/services/action_classifiers/__init__.py:122-131
@dataclass(frozen=True)
class Classification:
    rule: RuleId
    operation: Optional[Operation]
    detail: str
```

### Error Handling
```
# SOURCE: app/services/pattern_config.py:541-547
default = settings.PATTERN_PROFILE_DEFAULT
if default not in profiles:
    raise PatternConfigError(
        f"PATTERN_PROFILE_DEFAULT {default!r} names a profile {source} does not "
        f"define (defined profiles: {_allowed(profiles)}){note}"
    )
```

### Tests
```
# SOURCE: tests/test_action_config.py:146-157
monkeypatch.setattr(settings, "ACTION_POLICY_FILE", path)
with pytest.raises(ActionConfigError) as excinfo:
    load()
assert "ACTION_POLICY_FILE" in str(excinfo.value)
assert get_policy() is BUILT_IN_POLICY
```

---

## Design decisions (for the implementer and the orchestrator)

1. **Signature.** `classify_sql(statement: str, dialect: Optional[str], *, source_tool: str = "") -> tuple[Classification, ...]`. The PRD (F2) and story positional signature is kept. `source_tool` is an added keyword-only argument, because `Classification.operation` is documented as `None` only for `tool.unknown`/`tool.malformed` (`__init__.py:128`). Every SQL classification carries `Operation(kind="sql", target=statement, source_tool=source_tool)`, with the **whole input** as the target. sqlglot gives no reliable per-statement source span, and regenerated SQL would not be "the call's" text. STORY-014 and STORY-013 (`psql -c`) pass the tool name. Flagged as open question 1.
2. **Map by class, explicit table, closed by default.** Classes are checked in this order with `isinstance`, with subclasses noted:
   - read: `exp.Select` without `into`, `exp.SetOperation` (Union, Intersect, Except), `exp.Describe`, `exp.Show`. Details: `SELECT`, `SELECT`, `DESCRIBE`, `SHOW`. A `WITH … SELECT` parses as `Select`, so its detail is `SELECT`.
   - write: `exp.Insert` (`INSERT`), `exp.Merge` (`MERGE`), and scoped `exp.Update`/`exp.Delete` (`UPDATE`/`DELETE`).
   - unscoped_write: `exp.Update`/`exp.Delete` whose `where` is absent or simplifies to `exp.true()`. Detail: `UPDATE`/`DELETE`.
   - ddl: `exp.Drop` (`DROP`), `exp.Create` (`CREATE`), `exp.Alter` (`ALTER`), `exp.TruncateTable` (`TRUNCATE`), `exp.Comment` (`COMMENT`), and `exp.Select` with `args["into"]` (`SELECT INTO`).
   - dcl: `exp.Grant` (`GRANT`), `exp.Revoke` (`REVOKE`), and `Create`/`Drop`/`Alter` whose `kind` upper-cased is in `{"USER", "ROLE", "GROUP"}` (`CREATE ROLE`, `DROP USER`, …). This check runs **before** the ddl row.
   - everything else, `exp.Command` included, is `sql.unparsed`. For a Command the detail is `node.this` (the upper-cased head, e.g. `VACUUM`, `CREATE`); for other classes it is `node.key.upper()` (e.g. `SET`, `COPY`, `TRANSACTION`).
   No `exp.Expression` base-class fallback: only listed classes map.
3. **Two `exp.Command` carve-outs, both forced by the real library** (generic dialect, verified above), and both fail closed:
   - `this == "SHOW"` → `sql.read`, detail `SHOW`. PRD 6.3 lists SHOW as a read. A Command never spans a `;`, because sqlglot splits statements before it builds the Command (verified: `SHOW TABLES; DROP TABLE t` → `[Command, Drop]`).
   - `this == "EXPLAIN"` → re-classify the inner text `node.expression.name` with the same function at depth+1. If it yields exactly the read rules, the result is one `sql.read`, detail `EXPLAIN`. Otherwise the inner classifications are returned as they are, so `EXPLAIN DELETE FROM t` → `sql.unscoped_write` (strict, but no grant is needed to read a plan of a read). An empty inner text, a nested `EXPLAIN` (depth > 1), or a parse error → `sql.unparsed` (detail `EXPLAIN`). This makes `EXPLAIN ANALYZE <anything>` unparsed, which is correct, because `ANALYZE` executes the statement.
   No other Command head is carved out.
4. **Embedded modifying nodes.** For every root statement, after its own classification, walk `root.find_all(...)` for `Insert, Update, Delete, Merge, Drop, Create, Alter, TruncateTable, Comment, Grant, Revoke, Command` and for `Select` nodes with `into`, skipping `root` itself. Append one classification per hit, classified **shallowly** by the same table (no second walk, so there are no duplicates), in `find_all` order. `WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d` → `(sql.read, sql.unscoped_write)`, and the decision is deny. Plain statements have no hits, so the AC's "one classification" cases hold. Statement order is preserved: all of statement 1's classifications come before statement 2's.
5. **WHERE test.** `where = node.args.get("where")`; scoped iff `where is not None and simplify(where.this.copy()) != exp.true()`. Import `from sqlglot.optimizer.simplify import simplify`.
6. **Nothing to classify.** Skip `None` and `exp.Semicolon` results. If no statement remains (an empty string, whitespace, `;`, comment-only), return one `sql.unparsed` with detail `""`. An empty SQL target is not a statement anyone can vouch for, and this fails closed. A non-`str` `statement` goes the same way.
7. **Never raises.** Wrap the whole body in `try: … except Exception:` and return `(Classification("sql.unparsed", op, _head(statement)),)`, where `_head` is the first whitespace-delimited token of the input, at most 32 characters (e.g. `DR/**/OP`), or `""`. This covers `ParseError`, `TokenError`, `RecursionError` (verified), a `ValueError` from an unknown `dialect` passed straight in, and a simplifier failure. The same `_head` detail is used for parse errors. `BaseException` (KeyboardInterrupt) is deliberately not caught.
8. **sqlglot's log line is suppressed, at import.** This is the module's one import-time side effect: `logging.getLogger("sqlglot").addFilter(_DropCommandFallback())`, a `logging.Filter` returning False when `"Falling back to parsing as a 'Command'"` is in `record.getMessage()`. Reason: the warning embeds up to 100 characters of the agent's SQL. The filter does no I/O, reads no setting and drops nothing else. It is documented in the module docstring as a deliberate exception to "nothing at import" and covered by a `caplog` test. Add the filter only if no `_DropCommandFallback` instance is already present, so a reload does not stack filters.
9. **`SQL_DIALECTS`** lives in `sql.py`: `tuple(sorted(name for name in Dialect.classes if name))`, from `from sqlglot.dialects.dialect import Dialect`. It is computed at import and holds the registry `get_or_raise` consults. It includes `singlestore`, which `sqlglot.Dialects` lacks, so the accepted set equals the set `parse(dialect=…)` accepts. sqlglot knowledge stays in the classifier; `action_config` imports the constant.
10. **`ACTION_SQL_DIALECT` cross-check in `action_config`.** Add a new `_check_sql_dialect() -> None` that reads `settings.ACTION_SQL_DIALECT` at call time. `""` passes. Otherwise it requires **exact, case-sensitive membership** in `SQL_DIALECTS`, which also refuses `"Postgres"`, `" postgres"` and the `"mysql, k=v"` settings form that `get_or_raise` would accept. Raise `ActionConfigError(f"ACTION_SQL_DIALECT {value!r} is not a dialect sqlglot knows (expected: empty for the generic dialect, or one of: {_allowed(SQL_DIALECTS)})")`. `load()` calls it as its **first** statement, before `if not path: return` (`action_config.py:1011`), so the check also runs with no policy file. It rebinds nothing, so a failure leaves `_policy` as it was. The dialect is **not** added to `ActionPolicy` or the digest in this story; see open question 2.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `requirements.txt` | UPDATE | add `sqlglot==30.27.0` after `PyYAML` |
| `app/services/action_classifiers/sql.py` | CREATE | `classify_sql`, `SQL_DIALECTS`, log filter |
| `app/services/action_config.py` | UPDATE | `_check_sql_dialect()`, called first in `load()`; docstrings at lines 28-33, 89-90, 660, 1005-1006 lose "not here yet: STORY-008" |
| `tests/test_action_sql.py` | CREATE | table-driven classifier tests, purity, never-raises, log filter, pin |
| `tests/test_action_config.py` | UPDATE | dialect AC tests; module docstring line 16 updated (it says the cross-check is not covered) |

`app/services/action_classifiers/__init__.py` is unchanged; its docstring already says "Every classifier in this package (STORY-008..013)". `app/config.py` is unchanged, and so is `tests/test_config.py:1378-1381` (`test_action_sql_dialect_is_only_a_string_here` stays true).

---

## Tasks

### Task 1: Pin sqlglot
- **File**: `requirements.txt`. **Action**: UPDATE. Add the line `sqlglot==30.27.0`.
- **Validate**: `.venv/Scripts/python -c "import sqlglot; print(sqlglot.__version__)"` prints `30.27.0` (already installed by the planner).

### Task 2: `sql.py`
- **File**: `app/services/action_classifiers/sql.py`. **Action**: CREATE.
- **Implement**: decisions 1-9. Write a module docstring in the `__init__.py` style: cite PRD-016 Sections 6.3, 6.9, F2, D2 and Risk 6; state purity (dialect is an argument, only `action_config` reads `ACTION_SQL_DIALECT`); name the two Command carve-outs, the embedded walk and the log filter with reasons; and cite sqlglot 30.27.0 as the version this was verified on. Imports: `logging`, `typing.Optional`, `sqlglot`, `from sqlglot import exp`, `from sqlglot.dialects.dialect import Dialect`, `from sqlglot.optimizer.simplify import simplify`, and from `app.services.action_classifiers` import `Classification`, `Operation`, `RuleId`. The `from app.services.action_classifiers import` line will trip a naive "no `from app`" check; the new purity test allows exactly that import. Use private helpers: `_classify_node(node, op) -> Classification` (shallow table), `_classify_statement(root, op, depth) -> list[Classification]` (own result, carve-outs, embedded walk), `_is_scoped(node) -> bool` and `_head(text) -> str`.
- **Mirror**: `app/services/action_classifiers/__init__.py:1-21` for the docstring and the closed-vocabulary comment style.
- **Validate**: `.venv/Scripts/python -c "from app.services.action_classifiers.sql import classify_sql as c; print(c('SELECT 1; DROP TABLE users', None))"`

### Task 3: `action_config` dialect cross-check
- **File**: `app/services/action_config.py`. **Action**: UPDATE.
- **Implement**: `from app.services.action_classifiers.sql import SQL_DIALECTS`; add `_check_sql_dialect()` (decision 10) near `load()`. Make `load()`'s first statement `_check_sql_dialect()`, placed after `global _policy` and before `path = …`. Update the docstrings at lines 28-33, 68-90 (the `ActionConfigError` docstring: "STORY-008 adds …" becomes present tense), 660 and 1005-1006. In `load()`'s docstring add: "`ACTION_SQL_DIALECT` is checked first, file or no file".
- **Mirror**: `app/services/pattern_config.py:534-547`.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 4: Tests, `tests/test_action_sql.py` (new)
Header docstring (PRD-016 STORY-008; sections 6.3, 6.9, F2, Risk 6; literals transcribed from the PRD). Mirror `tests/test_action_vocabulary.py:1-16`; add `os.environ.setdefault` lines as `tests/test_action_config.py:21-24` does if anything imports `app.config` transitively. Run with `dialect=None` unless stated.
- `test_reads` (parametrized, AC 1): the three AC statements, plus `SELECT 1 UNION SELECT 2`, `DESCRIBE t`, `SHOW TABLES` (generic), `SHOW TABLES` with `mysql`, and `EXPLAIN SELECT 1` with `mysql` → exactly one classification, `rule == "sql.read"`. Expected details as literals (`EXPLAIN SELECT 1` → `EXPLAIN`).
- `test_writes` and `test_unscoped_writes` (AC 2): the AC's 3 + 4 statements, plus `MERGE …`, `INSERT … SELECT`, `WHERE 'a'='a'`, `WHERE NOT FALSE`, `WHERE 1=1 OR id = 3` (unscoped) and `WHERE 1=1 AND id = 3` (write). Each yields one classification, and its detail is the keyword.
- `test_ddl` (AC 3): the 4 AC statements, with details `DROP`, `TRUNCATE`, `ALTER`, `CREATE`, plus `COMMENT ON TABLE t IS 'x'` → `COMMENT`, `SELECT * INTO n FROM t` → `SELECT INTO`, `DROP/**/TABLE t` → `DROP`.
- `test_dcl` (AC 3): `GRANT ALL ON t TO u`, `REVOKE ALL ON t FROM u`, and `DROP ROLE r` with `snowflake` → `sql.dcl`.
- `test_multi_statement_in_order` (AC 4): `SELECT 1; DROP TABLE users` → rules `("sql.read", "sql.ddl")`, details `("SELECT", "DROP")`. Add `SELECT * FROM t; -- trailing` → one read (Semicolon skipped).
- `test_unparsed` (AC 4): `DR/**/OP TABLE t` (detail `DR/**/OP`), `SELECT FROM WHERE`, `VACUUM`, `CALL p()`, `CREATE USER bob`, `RENAME TABLE t TO u`, `SET x = 1`, `BEGIN`, `COPY t FROM '/etc/passwd'`, `EXPLAIN ANALYZE DELETE FROM t`, `EXPLAIN`, `EXPLAIN EXPLAIN SELECT 1`, `''`, `'   '`, `';'` → exactly one `sql.unparsed`.
- `test_a_command_is_unparsed_whatever_sqlglot_says` (AC 4, Risk 6): assert `isinstance(sqlglot.parse_one("VACUUM"), exp.Command)`, which pins the library behaviour this story depends on, and then that the classification is `sql.unparsed`.
- `test_embedded_modifying_cte_is_not_a_read`: `WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d` → contains `sql.unscoped_write`. `EXPLAIN DELETE FROM t` → `sql.unscoped_write`.
- `test_never_raises` (AC 4): deep nesting (`'('*5000`), `None`, `"SELECT 1"` with `dialect="nosuchdb"`, and a `monkeypatch` of `sql.simplify` to raise → each returns `(sql.unparsed,)` and nothing propagates.
- `test_every_rule_produced_is_a_sql_rule`: over all inputs above, `rule in RULE_IDS`, `rule.startswith("sql.")`, `operation == Operation("sql", <input>, "")` (or a given `source_tool`), and `detail` a `str` of at most 32 characters.
- `test_sql_dialects_are_what_sqlglot_parses`: `"postgres" in SQL_DIALECTS`, `"" not in SQL_DIALECTS`, and for every name `sqlglot.parse("SELECT 1", dialect=name)` succeeds (33 cheap parses).
- `test_sqlglot_fallback_warning_does_not_log_the_statement`: with `caplog.set_level(logging.DEBUG)`, run `classify_sql("VACUUM secret_marker_123", None)` and assert `"secret_marker_123" not in caplog.text`.
- `test_sql_module_stays_pure`: mirror `tests/test_action_vocabulary.py:142-153` on `inspect.getsource(sql)`. No `settings` in `vars`, no `open(`/`Path(`, and the only `from app` import is `from app.services.action_classifiers import`.
- `test_requirements_pins_sqlglot_exactly`: `re.search(r"(?m)^sqlglot==30\.27\.0$", requirements.txt)` and `sqlglot.__version__ == "30.27.0"` (mirror `tests/test_config.py:645-658`).

### Task 5: Tests, `tests/test_action_config.py` (update)
- Update the module docstring line 16: drop the "does not cover `ACTION_SQL_DIALECT`" clause and mention STORY-008. Add a comment citing PRD-016 STORY-008.
- `test_load_accepts_a_known_sql_dialect` (AC 5): `ACTION_POLICY_FILE=""`, `ACTION_SQL_DIALECT="postgres"` → `load()` returns None, `get_policy() is BUILT_IN_POLICY`.
- `test_load_refuses_an_unknown_sql_dialect` (AC 5): `"nosuchdb"` → `ActionConfigError`, message contains `ACTION_SQL_DIALECT`, `'nosuchdb'`, `postgres`, `mysql`, `sqlite`.
- `test_sql_dialect_check_is_exact` (parametrized): `"Postgres"`, `" postgres"`, `"mysql, normalization_strategy = lowercase"` → refused.
- `test_sql_dialect_is_checked_before_the_policy_file`: a valid policy file plus `nosuchdb` → raises, and `get_policy() is BUILT_IN_POLICY` (nothing rebound).
- `test_empty_sql_dialect_is_the_generic_one`: `""` → load OK. The existing `test_load_reads_no_file_when_action_policy_file_unset` (lines 125-143) must still pass unchanged, which shows the check does no I/O.

### Task 6: Targeted regression
`PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_sql.py tests/test_action_config.py tests/test_action_vocabulary.py tests/test_action_adapters.py tests/test_config.py tests/test_untouched_app.py -q -p no:cacheprovider`. The full suite is deferred to the orchestrator (user decision).

---

## End-to-End Tests

- [ ] `.venv/Scripts/python -c "from app.main import app; print('OK')"` (both lifespans already call `action_config.load()`; the new import of `sql` must not break boot)
- [ ] `ACTION_SQL_DIALECT=nosuchdb .venv/Scripts/python -c "from app.services import action_config; action_config.load()"` → `ActionConfigError` naming the setting and the dialect list
- [ ] Spot-run the probe table through `classify_sql` and compare with the verification table above

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_sql.py tests/test_action_config.py tests/test_action_vocabulary.py tests/test_action_adapters.py tests/test_config.py tests/test_untouched_app.py -q -p no:cacheprovider
```

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| sqlglot returns `Command` for `EXPLAIN`/`SHOW`, against the PRD's implicit assumption that they parse | Two head carve-outs only (decision 3). `EXPLAIN` re-parses its inner text and fails closed; tests pin both |
| A data-modifying CTE or `SELECT INTO` parses as `Select` (Risk 6, "mis-parses into a safer type") | Embedded walk plus the `into` check (decision 4), with tests |
| `RENAME TABLE`, `CREATE USER/ROLE`, `GRANT role TO u` are `Command` → `sql.unparsed`, not `sql.ddl`/`sql.dcl` as 6.3 lists them | All are deny. `sql.ddl` is grantable and `sql.unparsed` is not, so `RENAME TABLE` cannot be lifted by `action:sql:ddl`. That is stricter, fails closed, and is recorded in the report (`ALTER TABLE … RENAME TO` is ddl) |
| Transaction control (`BEGIN`, `COMMIT`, `ROLLBACK`) and `SET`/`USE` are unparsed (deny, non-grantable) | PRD 6.9: unmapped means unparsed. This may be noisy for agents; see open question 3 |
| Tautologies the simplifier does not fold (`id = id`, `x IS NOT NULL OR x IS NULL`, `1 IN (1)`) count as scoped | Documented limit. `sql.write` is still deny by default and grant-only. The STORY-016 evasion corpus can add cases |
| Side-effecting functions inside a SELECT (`pg_sleep`, `pg_terminate_backend`, `lo_import`) classify as read | Out of PRD-016's statement-type model; noted for the report and the threat model |
| sqlglot logs statement text | Filter (decision 8) and a caplog test |
| Upgrading sqlglot silently changes parses | Exact pin plus `test_requirements_pins_sqlglot_exactly` and `test_a_command_is_unparsed_whatever_sqlglot_says` |

## Open questions for the orchestrator

1. `source_tool` keyword-only argument on `classify_sql` (decision 1), versus returning `operation=None` and having STORY-014 fill it in. The plan picks the kwarg; it keeps the PRD positional signature.
2. How STORY-014's pure `evaluate()` gets the dialect. This story only validates it. Options: an `ActionPolicy.sql_dialect` field, which then enters the digest (arguably right: the same SQL can classify differently per dialect), or an `action_config.get_sql_dialect()`. Deferred to STORY-014 to avoid changing the digest contract here.
3. Whether `BEGIN`/`COMMIT`/`ROLLBACK` should be `sql.read` rather than unparsed. The plan follows PRD 6.9 literally (unparsed).

---

## Acceptance Criteria

(Copied from story `STORY-008`)

- [ ] Given `classify_sql`, when called with `SELECT * FROM users WHERE id = 1`, `WITH x AS (SELECT 1) SELECT * FROM x`, `EXPLAIN SELECT 1`, then each yields one `sql.read` classification. (Task 4 `test_reads`)
- [ ] Given `INSERT INTO t VALUES (1)`, `UPDATE t SET a = 1 WHERE id = 2`, `DELETE FROM t WHERE id = 3`, when classified, then `sql.write`; given `DELETE FROM t`, `UPDATE t SET a = 1`, `DELETE FROM t WHERE 1=1`, `DELETE FROM t WHERE TRUE`, then `sql.unscoped_write`. (Task 4 `test_writes`, `test_unscoped_writes`)
- [ ] Given `DROP TABLE users`, `TRUNCATE t`, `ALTER TABLE t ADD c INT`, `CREATE TABLE t (a INT)`, then `sql.ddl` with `detail` naming the keyword (`DROP`, …); given `GRANT ALL ON t TO u`, `REVOKE …`, then `sql.dcl`. (Task 4 `test_ddl`, `test_dcl`)
- [ ] Given `SELECT 1; DROP TABLE users`, when classified, then two classifications in order, `sql.read` then `sql.ddl`; given `DR/**/OP TABLE t`, a parse error, or any statement sqlglot returns as `exp.Command` or an unmapped type, then `sql.unparsed`; the function never raises. (Task 4 `test_multi_statement_in_order`, `test_unparsed`, `test_a_command_is_unparsed_whatever_sqlglot_says`, `test_never_raises`)
- [ ] Given `ACTION_SQL_DIALECT=postgres`, when `action_config.load()` runs, then it loads; given `ACTION_SQL_DIALECT=nosuchdb`, then `ActionConfigError` names the setting and lists the dialects sqlglot knows. (Task 5)
- [ ] `sqlglot==<exact version>` in `requirements.txt`, with version and verification recorded in the report (Task 1; the verification table above)
- [ ] All tasks completed
- [ ] Backend import passes (`from app.main import app`)
- [ ] Follows existing patterns
