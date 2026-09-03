---
story: STORY-010
prd: PRD-007
slug: batched-summary-read
title: "One batched database read returning all ten summary figures in a single round trip"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-007-turso-migration
created: 2026-09-01
---

# Plan: One batched database read returning all ten summary figures in a single round trip

## Summary

Add one public read to `app/db/database.py` — `summary_snapshot(row_limit, ranked_limit)` — that returns all ten admin summary figures from **one** `SELECT`. STORY-001 §2.6 proved the driver has no batch API (`libsql` exposes no `batch()`, `executescript()` returns `None`, and multi-statement `execute()` returns only statement 1 *while swallowing errors on the rest*), so the mechanism is not a client-side batch but a single statement whose columns are scalar subqueries — six counts, three `json_group_array` rankings, and the register rows as `json_group_array(json_object(...))`. Per-figure attribution survives because each figure is a **named column**, not a statement: the ten `READ_LABEL_*` entries map one-to-one onto column names. Decoding is per-figure and independently guarded, and if the statement itself fails the function degrades to the ten standalone reads so the caller still learns *which* figure broke — Risk 6's mitigation, which a naive all-or-nothing collapse would destroy. The ten standalone functions are untouched, and nothing under `app/routers/` or `chat_ui/` is modified; STORY-011 and STORY-012 adopt this.

## User Story

As a compliance admin
I want the admin console's summary figures fetched in one round trip
So that the register stays usable now that each read crosses a network instead of hitting a local file

## Story Reference

- Story file: `.agents/stories/PRD-007-turso-migration/STORY-010-batched-summary-read.md`
- PRD: `.agents/PRDs/PRD-007-turso-migration/PRD.md` — Section 6 Pattern 3, Section 7.3, Section 11, Section 12 Phase 3, Section 14 Risk 6
- Decision record (governs the batch shape): `.agents/reports/PRD-007-turso-migration/STORY-001-driver-decision.md` §2.6, §3.4

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/db/` (storage layer only), test suite |
| Story | STORY-010 |
| PRD | PRD-007 |
| Epic Branch | `epic/PRD-007-turso-migration` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` contains only `frontend-design`, whose `description` scopes it to visual design of UI ("aesthetic direction, typography, palette"). This story touches `app/db/database.py` and `tests/test_db.py` and renders nothing. No skill applies. | none |

---

## The constraint that shapes this plan

STORY-001 §2.6, pasted from the decision record:

```
has conn.batch: False        has conn.execute_batch: False
conn.execute('stmt1; stmt2; stmt3')            -> [(5,)]     <- only statement 1
batch containing SELECT * FROM no_such_table   -> [(5,)]     <- NO ERROR RAISED
```

> "Per-statement results and per-statement error attribution are therefore **both unavailable**. PRD Risk 6 is real and cannot be solved with a client-side batch API."

The story's Technical Notes anticipate exactly this: *"If per-statement error reporting turned out to be unsupported, the workaround recorded there governs this story."* The recorded workaround is §3.4 — one `SELECT`, measured at **1.7 ms against 16.3 ms** for ten sequential statements, with `description` giving every figure its own column name:

```
8-figure single round trip OK in 1.7 ms
 columns: ['total_recorded','blocked_duplicates','blocked_suspicious','unique_users',
           'successful','pii_detected','top_models','top_users']
 values : (6, 0, 0, 3, 6, 6, '["gpt-4","claude-3"]', '["u2","u1","u0"]')
```

Two figures were not in that probe and are added here: `top_pii_entities` (STORY-009's recursive CTE, hoisted to a top-level `WITH RECURSIVE` and read from a scalar subquery) and `rows` (`json_group_array(json_object(...))` over the ordered, limited register slice).

---

## Patterns to Follow

### Read function shape — `_session()`, named columns, a comprehension out

```python
# SOURCE: app/db/database.py:670-683
def top_models(limit: int = 5) -> list[str]:
    with _session() as conn:
        rows = conn.execute(
            """
            SELECT model_used FROM audit_logs
            WHERE model_used IS NOT NULL
            GROUP BY model_used
            ORDER BY COUNT(*) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [row["model_used"] for row in rows]
```

### The CTE this statement must reuse verbatim

```sql
-- SOURCE: app/db/database.py:710-755 (top_pii_entities, STORY-009)
WITH RECURSIVE split(entity, rest) AS (
    SELECT NULL, pii_entities || ','
      FROM audit_logs
     WHERE pii_entities IS NOT NULL
    UNION ALL
    SELECT substr(rest, 1, instr(rest, ',') - 1),
           substr(rest, instr(rest, ',') + 1)
      FROM split
     WHERE rest <> ''
)
SELECT entity FROM split
WHERE entity IS NOT NULL
GROUP BY entity
ORDER BY COUNT(*) DESC, entity ASC
LIMIT ?
```

The seed row selects `NULL` rather than `''` deliberately (so `"A,,B"` keeps its empty middle), and the `entity ASC` tie-break was chosen, not inherited. Both must survive the move into the batch unchanged, or AC 5 (figure-for-figure agreement) fails.

### Row mapping — key access only, so a plain `dict` satisfies it

```python
# SOURCE: app/db/database.py:573-595
def _row_to_audit_log(row: _Row) -> AuditLog:
    return AuditLog(
        id=row["id"],
        ...
        was_duplicate_blocked=bool(row["was_duplicate_blocked"]),
        ...
    )
```

Every access is `row["name"]`, so the decoded `json_object` `dict` goes through this mapper unchanged — no second mapper, no drift between the batched and standalone shapes. The `bool(...)` coercions matter: JSON carries the `INTEGER` columns back as `0`/`1`.

### Error translation — the one seam

```python
# SOURCE: app/db/database.py:416-437
@contextmanager
def _translated() -> Iterator[None]:
    try:
        yield
    except ValueError as exc:
        message = str(exc)
        if _DRIVER_ERROR not in message:
            raise
        ...
        raise StorageError(message) from exc
```

`_session()` already wraps `_translated()`, so anything this story catches is an `app.db.errors` type, never a driver `ValueError`.

### Statement counting in tests — the existing proxy idiom

```python
# SOURCE: tests/test_db.py:109-150
statements: list[str] = []
real_get_connection = database.get_connection

class _RecordingConnection:
    def __init__(self, conn): self._conn = conn
    def __enter__(self): self._conn.__enter__(); return self
    def __exit__(self, *exc_info): return self._conn.__exit__(*exc_info)
    def execute(self, sql, *parameters):
        statements.append(sql)
        return self._conn.execute(sql, *parameters)

monkeypatch.setattr(database, "get_connection",
                    lambda: _RecordingConnection(real_get_connection()))
...
assert statements, "the proxy captured nothing -- the patch did not take"
```

This is the instrument for the round-trip count. `test_init_db_issues_no_alter_when_schema_is_current` already established it after `sqlite3`'s `set_trace_callback` went away with the driver swap.

### Test data shape

```python
# SOURCE: tests/test_db.py:484-492
insert_audit_log(
    AuditLog(timestamp="2026-07-02T10:00:00Z", user_id="a", prompt_hash="h2")
)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/database.py` | UPDATE | Add `SUMMARY_FIGURES`, `SummarySnapshot`, `summary_snapshot()`, the per-figure decoders and the attribution fallback. No existing function's body or signature changes. |
| `tests/test_db.py` | UPDATE | Agreement, per-figure failure isolation, empty database, round-trip count, limit plumbing, and the unchanged-standalone-surface guard. |

No file is created. **No file under `app/routers/` or `chat_ui/` is touched** — AC 8, and PRD Section 6 Pattern 3 grants those callers to STORY-011 and STORY-012.

---

## Design

### Return type

```python
SUMMARY_FIGURES = (
    "rows", "total_recorded", "blocked_duplicates", "blocked_suspicious",
    "unique_users", "successful_queries", "pii_detected_queries",
    "top_models", "top_users", "top_pii_entities",
)

@dataclass(frozen=True)
class SummarySnapshot:
    figures: dict[str, Any]        # name -> value, correctly typed, successes only
    errors: dict[str, Exception]   # name -> the failure, for the figures that broke
```

- **AC 2 (individually addressable, same types)**: `figures["total_recorded"]` is the `int` `count_audit_logs()` returns; `figures["top_models"]` is the `list[str]` `top_models()` returns; `figures["rows"]` is the `list[AuditLog]` `list_audit_logs(limit)` returns. Named read-only properties (`snapshot.total_recorded`, …) are provided over `figures` and **raise the recorded error** when that figure failed, so a caller that wants the value-or-nothing shape gets it and a caller that wants attribution reads `errors`.
- **AC 3 (which figure failed, the rest still delivered)**: `figures` and `errors` partition `SUMMARY_FIGURES` — every name appears in exactly one. STORY-012's loop becomes `for name, label in ...: if name in snapshot.errors: LOAD_FAILED_MESSAGE.format(read=label, detail=snapshot.errors[name])`, which is the same sentence it builds today.
- The field names are `_READS`' field names, so STORY-012's mapping is one-to-one and `len(_READS) == 10` needs no change.

### The statement

One `SELECT`, ten named columns, `WITH RECURSIVE split` hoisted to the top so `top_pii_entities` can be read from a scalar subquery alongside the rest:

```sql
WITH RECURSIVE split(entity, rest) AS ( ...STORY-009's CTE verbatim... )
SELECT
  (SELECT json_group_array(json_object('id', id, 'timestamp', timestamp, ...))
     FROM (SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?))   AS rows,
  (SELECT COUNT(*) FROM audit_logs)                                     AS total_recorded,
  (SELECT COUNT(*) FROM audit_logs WHERE was_duplicate_blocked = 1)     AS blocked_duplicates,
  (SELECT COUNT(*) FROM audit_logs WHERE suspicious_pattern IS NOT NULL) AS blocked_suspicious,
  (SELECT COUNT(DISTINCT user_id) FROM audit_logs)                      AS unique_users,
  (SELECT COUNT(*) FROM audit_logs WHERE success = 1)                   AS successful_queries,
  (SELECT COUNT(*) FROM audit_logs
    WHERE pii_detected_input = 1 OR pii_detected_output = 1)            AS pii_detected_queries,
  (SELECT json_group_array(model_used) FROM (
      SELECT model_used FROM audit_logs WHERE model_used IS NOT NULL
       GROUP BY model_used ORDER BY COUNT(*) DESC LIMIT ?))             AS top_models,
  (SELECT json_group_array(user_id) FROM (
      SELECT user_id FROM audit_logs
       GROUP BY user_id ORDER BY COUNT(*) DESC LIMIT ?))                AS top_users,
  (SELECT json_group_array(entity) FROM (
      SELECT entity FROM split WHERE entity IS NOT NULL
       GROUP BY entity ORDER BY COUNT(*) DESC, entity ASC LIMIT ?))     AS top_pii_entities
```

Every subquery is the standalone function's `WHERE`/`GROUP BY`/`ORDER BY` **copied**, not paraphrased — that is what makes AC 5 a check rather than a hope.

**Parameters are positional and bind in statement order**: `(row_limit, ranked_limit, ranked_limit, ranked_limit)`. Named placeholders were not among STORY-001's six verified behaviors, so this plan does not assume them. Reordering the columns silently reorders the parameters; the docstring must say so.

### Per-figure failure isolation, in two layers

1. **Decode layer (normal path).** The statement succeeded; each column is decoded by its own small function inside its own `try/except`, so a malformed payload for one figure lands in `errors["that_figure"]` and the other nine still arrive.
2. **Statement layer (fallback).** The statement itself failed — `MissingRelationError`, `StorageError`, an unreachable endpoint. One dead statement carries no attribution at all, which is precisely Risk 6's blank page. `summary_snapshot()` therefore falls back to calling the ten standalone functions, each individually guarded, and returns the partition they produce. It costs up to ten round trips **only on the failure path**, where the alternative is ten figures failing anonymously; the success path stays at one.

This is why AC 4 (keep the ten standalone functions) is not merely a compatibility promise — the fallback is built out of them.

### Round-trip accounting

The count under test is **statements executed**, which is what the `_RecordingConnection` proxy observes and what PRD Section 12 Phase 3 asks to measure. `_session()` also issues a `commit()` on block exit; every existing read carries that same trailer today, so the batched read is one statement where the fan-out was ten, and the commit is unchanged rather than new. Skipping the commit for read-only sessions is a real improvement and is **out of scope** — it would change `_session()`, which every one of the 22 functions shares.

### Note owed to STORY-012

The story asks whether `_READS`' ordering comment still carries weight. It does not, and the report must say so: *"the rows come first so the slowest query fails fast"* described ten sequential statements aborting at the first failure. In one statement there is no first — the database plans all ten subqueries, and the fallback runs the full ten precisely so nothing fails fast. `total_recorded` following `rows` as "the denominator the register states its 100-row cap against" remains true as **documentation of the figures' relationship**, but no longer as a statement about read order. STORY-012 should rewrite the comment rather than carry it forward.

### Risks

| # | Risk | Mitigation |
|---|---|---|
| 1 | `json_group_array` over an ordered subquery does not preserve order, so `figures["rows"]` disagrees with `list_audit_logs()`' `ORDER BY timestamp DESC`. | Task 7 asserts full-sequence equality against `list_audit_logs()`, including a tie on `timestamp`, against the live endpoint. If order is not preserved, the fix is a `ROW_NUMBER() OVER (ORDER BY timestamp DESC)` sort key carried in the `json_object` and sorted in Python — not silent acceptance. |
| 2 | Positional parameters are bound in column order; adding or moving a column corrupts every figure after it. | Named constants and a docstring stating the coupling, plus Task 9's limit test, which uses `row_limit != ranked_limit` so a swap cannot pass. |
| 3 | The fallback masks a real outage as ten tidy per-figure errors and hides the cost. | The fallback records the original statement-level failure against **every** figure it could not otherwise attribute, so the outage is still legible; Task 8 asserts all ten names carry an error when the table is gone. |
| 4 | The JSON round trip changes types — `INTEGER` columns arriving as `0`/`1`, `NULL` as `None`. | `_row_to_audit_log()` is reused unchanged and already applies `bool(...)`; Task 7 compares whole `AuditLog` objects, not field subsets. |
| 5 | Suite-wide `STREAM_EXPIRED` (open issue in the PRD index) makes a whole-suite run flaky and could be mistaken for a defect in this story. | Validate with `pytest tests/test_db.py` as its own process, as the index describes; do not chase it here. |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Confirm the dev endpoint is up

- **File**: — (environment)
- **Action**: RUN
- **Implement**: Start the pinned libSQL dev server from STORY-001 §4 if it is not already running. It is the only endpoint the suite talks to and it takes no token.
- **Validate**:
  ```bash
  curl -sf http://127.0.0.1:8080/health || docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary \
    ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67
  ```

### Task 2: Declare the figure names and the snapshot type

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: Add `SUMMARY_FIGURES` (the ten names, in `_READS`' order) and the frozen `SummarySnapshot` dataclass with `figures`, `errors`, ten named properties that raise the recorded error, and a `__post_init__` (or a construction-site assertion) that the two dicts partition `SUMMARY_FIGURES` exactly. Import `dataclass` and `json`. Place them next to the summary reads, after `count_pii_detected_queries()`.
- **Mirror**: `app/db/models.py:70-95` for dataclass style; `app/db/errors.py:31-48` for a docstring that states what the type exists to protect.
- **Docstring must record**: that this is the shape Risk 6 demanded, and that the names are `_READS`' field names so STORY-012's mapping is one-to-one.
- **Validate**: `python -c "from app.db.database import SUMMARY_FIGURES, SummarySnapshot; assert len(SUMMARY_FIGURES) == 10"`

### Task 3: Write the batched statement

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: Add the module-level `_SUMMARY_SQL` constant exactly as designed above, copying each subquery's predicates from its standalone function and STORY-009's CTE verbatim. Comment the positional-parameter order immediately above the constant.
- **Mirror**: `app/db/database.py:710-755` (the CTE), `:638-708` (the six counts and two rankings).
- **Validate**: run it once by hand against the dev server and confirm the column names come back:
  ```bash
  python -c "
  from app.db.database import _SUMMARY_SQL, get_connection, init_db
  init_db()
  cur = get_connection().cursor(); cur.execute(_SUMMARY_SQL, (100, 5, 5, 5))
  print([c[0] for c in cur.description]); print(cur.fetchone())"
  ```
  Expect the ten names in order and no exception.

### Task 4: Per-figure decoders

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: A private table mapping each figure name to the callable that turns its column value into the standalone function's return type: identity/`int` for the six counts, `json.loads` for the three rankings, and `json.loads` + `_row_to_audit_log` per element for `rows`. Widen `_row_to_audit_log`'s annotation from `_Row` to a mapping type — it only ever uses `row["name"]`, so the decoded `dict` passes through unchanged, and the annotation should say so rather than the call site casting.
- **Mirror**: `app/db/database.py:573-595`.
- **Validate**: `python -m pytest tests/test_db.py -k row_to_audit -q` (existing coverage of the mapper stays green), then `python -c "import app.db.database"`.

### Task 5: `summary_snapshot()`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  ```python
  def summary_snapshot(row_limit: int = 100, ranked_limit: int = 5) -> SummarySnapshot:
  ```
  Execute `_SUMMARY_SQL` inside `_session()` with `(row_limit, ranked_limit, ranked_limit, ranked_limit)`, `fetchone()`, then decode each figure under its own `try/except Exception` into `figures` or `errors`. Defaults match the standalone functions (`list_audit_logs(limit=100)`, ranked `limit=5`); the callers pass `REGISTER_ROW_LIMIT` and `RANKED_LIMIT` — AC 6.
- **Docstring must record**: that there is no client batch API (STORY-001 §2.6, quote the `dir(connection)` result), that one `SELECT` measured 1.7 ms against 16.3 ms for ten statements (§3.4), that attribution rides on column names rather than statements, and that the parameters bind positionally in column order.
- **Validate**:
  ```bash
  python -c "
  from app.db.database import init_db, summary_snapshot
  init_db(); s = summary_snapshot()
  print(sorted(s.figures), s.errors)"
  ```
  All ten names in `figures`, `errors` empty.

### Task 6: The attribution fallback

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: Wrap the statement in `try/except StorageError`. On failure, call the ten standalone functions — `list_audit_logs(limit=row_limit)`, `count_audit_logs()`, the five other counts, `top_models(ranked_limit)`, `top_users(ranked_limit)`, `top_pii_entities(ranked_limit)` — each individually guarded, and return the resulting partition. Record the originating statement failure in the docstring's rationale and re-raise nothing.
- **Rationale to state in the code**: PRD Risk 6 — "Collapsing ten reads into one all-or-nothing result destroys the per-figure error attribution" — and that the ten-round-trip cost is paid only when the batch is already broken.
- **Mirror**: `app/db/database.py:778-802` (`find_user_by_token_hash`) for catching a module-owned error and degrading rather than propagating.
- **Validate**: `python -m pytest tests/test_db.py -q` still green before the new tests land.

### Task 7: Test — agreement with the ten individual functions, and on an empty database

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: Two tests. (a) Seed a table exercising every figure — several users, duplicate-blocked and suspicious rows, failures, multi-entity `pii_entities`, at least two rows sharing a `timestamp` (Risk 1), and more rows than `row_limit` — then assert each of the ten `figures[...]` equals its standalone call, comparing `rows` as a full ordered list of `AuditLog` objects. (b) The same assertions against an empty database: the six counts `0`, the four lists `[]`, `errors` empty.
- **Mirror**: `tests/test_db.py:484-535` (seed shape), `:748-806` (PII seeds), `:467-470` (the empty-database idiom).
- **Validate**: `python -m pytest tests/test_db.py -k summary_snapshot -q`

### Task 8: Test — per-figure failure isolation

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: Three tests. (a) **Decode layer**: monkeypatch one figure's decoder to raise; assert that name is in `errors`, the other nine are in `figures` with correct values, and the two dicts still partition `SUMMARY_FIGURES`. (b) **Fallback layer**: force the statement to fail (monkeypatch `_SUMMARY_SQL` to reference a missing table) while monkeypatching exactly one standalone function to raise; assert nine correct values plus one named error — this is the AC 3 case, one figure identified while the rest are still delivered. (c) **Whole-database outage**: drop `audit_logs`; assert all ten names carry an error and none is silently absent (Risk 3).
- **Mirror**: `tests/test_db.py:109-150` (the monkeypatch-the-module idiom).
- **Validate**: `python -m pytest tests/test_db.py -k isolation -q`

### Task 9: Test — round-trip count, and that the limits are parameters

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: Two tests. (a) Using `_RecordingConnection`, assert `summary_snapshot()` executes **exactly one** statement — `assert len(statements) == 1`, with the proxy-took assertion first — and, as the contrast PRD Section 12 Phase 3 asks for, that the same ten figures fetched individually execute ten. (b) Call `summary_snapshot(row_limit=2, ranked_limit=1)` against a table with more rows and more distinct models than either limit; assert `len(figures["rows"]) == 2` and each ranking has length 1. Deliberately different values, so a swapped parameter cannot pass (Risk 2).
- **Mirror**: `tests/test_db.py:109-150`.
- **Validate**: `python -m pytest tests/test_db.py -k "round_trip or limit" -q`

### Task 10: Test — the ten standalone functions are unchanged

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: One test asserting via `inspect.signature` that all ten still exist with today's parameters and defaults, and one asserting `count_audit_logs(user_id=...)` still scopes — it serves `GET /audit`, not only the summary, and AC 4 names it specifically.
- **Mirror**: `tests/test_db.py:467-483`.
- **Validate**: `python -m pytest tests/test_db.py -k signature -q`

### Task 11: Full validation and the untouched-callers proof

- **File**: —
- **Action**: RUN
- **Implement**: Run the module suite and the four suites PRD Section 12 Phase 3 names, then prove AC 8 from the diff.
- **Validate**:
  ```bash
  python -m pytest tests/test_db.py -q
  python -m pytest tests/test_stats_router.py tests/test_admin_state.py tests/test_summary.py -q
  python -m pytest tests/test_admin_shell.py -q
  git diff main --stat -- app/routers/ chat_ui/    # must print nothing
  git diff main --stat                              # only app/db/database.py and tests/test_db.py
  ```
  Run each suite as its own process — the whole-suite `STREAM_EXPIRED` issue in the PRD index is pre-existing and not this story's (Risk 5).

### Task 12: Report the round-trip measurement and the ordering finding

- **File**: `.agents/reports/PRD-007-turso-migration/STORY-010-batched-summary-read.report.md`
- **Action**: CREATE
- **Implement**: Record the measured statement counts (1 batched vs 10 individual) as the evidence PRD Section 12 Phase 3 requires; state that the client has no batch API and this is the recorded §3.4 workaround, not a shortcut; and answer the story's explicit question — whether `_READS`' ordering comment still carries weight — with the finding in **Note owed to STORY-012** above, so STORY-012 knows the comment needs rewriting rather than carrying forward.
- **Mirror**: `.agents/reports/PRD-007-turso-migration/STORY-009-top-pii-entities-sql-aggregation.report.md`
- **Validate**: the report answers the ordering question in as many words.

---

## End-to-End Tests

- [ ] Dev server up; `init_db()` succeeds against it
- [ ] `summary_snapshot()` on a seeded database returns all ten figures with `errors == {}`
- [ ] Each of the ten equals its standalone function's result, `rows` compared as an ordered list of whole `AuditLog` objects
- [ ] `summary_snapshot()` on an empty database returns six zeros and four empty lists, no errors
- [ ] Exactly one statement is executed on the success path; ten individual calls execute ten
- [ ] One broken figure yields one named error and nine delivered values
- [ ] A dropped `audit_logs` yields ten named errors, not one anonymous failure
- [ ] `row_limit=2, ranked_limit=1` is honoured independently
- [ ] `tests/test_stats_router.py`, `tests/test_admin_state.py`, `tests/test_summary.py`, `tests/test_admin_shell.py` pass with assertions unchanged
- [ ] `git diff main --stat -- app/routers/ chat_ui/` is empty

## Validation

```bash
curl -sf http://127.0.0.1:8080/health
python -m pytest tests/test_db.py -q
python -m pytest tests/test_stats_router.py tests/test_admin_state.py tests/test_summary.py -q
python -m pytest tests/test_admin_shell.py -q
git diff main --stat -- app/routers/ chat_ui/
```

## Acceptance Criteria

(Copied from story `STORY-010`)

- [ ] Given the new function in `app/db/database.py`, when it is called, then it returns all ten figures — `list_audit_logs(limit)`, `count_audit_logs`, `count_blocked_duplicates`, `count_blocked_suspicious`, `count_unique_users`, `count_successful_queries`, `count_pii_detected_queries`, `top_models`, `top_users`, `top_pii_entities` — in **one** round trip
- [ ] Given the returned value, when a caller reads a figure, then each is individually addressable by name, with the same type the corresponding standalone function returns today (`int`, `list[str]`, `list[AuditLog]`)
- [ ] Given a batch where one statement fails, when the result is inspected, then the caller can tell **which** figure failed while still receiving the ones that succeeded (Risk 6)
- [ ] Given the ten existing standalone functions, when this story completes, then they still exist with unchanged signatures — `count_audit_logs(user_id=...)` in particular is not folded away
- [ ] Given the batched read and ten individual calls against the same data, when their results are compared, then every figure is identical
- [ ] Given `list_audit_logs`' row limit and the ranked functions' `limit`, when the batched read is called, then both are parameters rather than constants baked into the batch
- [ ] Given `tests/test_db.py`, when it runs, then the batched read is covered for agreement, per-figure failure isolation, an empty database, and the round-trip count
- [ ] Given `git diff main --stat`, when it is inspected, then no file under `app/routers/` or `chat_ui/` is modified
- [ ] All tasks completed
- [ ] `tests/test_db.py` passes
- [ ] Follows existing patterns
