---
story: STORY-009
prd: PRD-007
slug: top-pii-entities-sql-aggregation
title: "Aggregate top_pii_entities() in SQL instead of transferring every PII-bearing row"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-007-turso-migration
created: 2026-09-01
---

# Plan: Aggregate top_pii_entities() in SQL

## Summary

`top_pii_entities()` is the last read in `app/db/database.py` that pulls a whole
column across the network to compute a five-element answer in Python. Replace its
two-part body (a `SELECT pii_entities FROM audit_logs WHERE pii_entities IS NOT NULL`
plus a Python `dict` count) with a single statement: a recursive CTE that splits the
comma-separated TEXT column server-side, groups, orders by count descending then
entity name ascending, and applies `LIMIT ?`. The function then reads exactly like
`top_models()` and `top_users()` two definitions above it — one `conn.execute(...)`,
one list comprehension over the rows — and transfers at most `limit` rows. Signature,
return type, and the descending-frequency contract are unchanged; the only observable
change is that the tie-break becomes specified (alphabetical) instead of incidental.

## User Story

As a compliance admin
I want the PII entity ranking computed in the database
So that loading the admin console does not pull the entire PII-bearing history
across the network every time.

## Story Reference

- Story file: `.agents/stories/PRD-007-turso-migration/STORY-009-top-pii-entities-sql-aggregation.md`
- PRD: `.agents/PRDs/PRD-007-turso-migration/PRD.md` — Section 6 Pattern 4, Section 7.4, Section 12 Phase 3
- Prior art: `.agents/reports/PRD-007-turso-migration/STORY-001-driver-decision.md` §3.4

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | `app/db/database.py` (one function), `tests/test_db.py` |
| Story | STORY-009 |
| PRD | PRD-007 |
| Epic Branch | `epic/PRD-007-turso-migration` (commit directly on this branch) |

---

## Skills In Use

`.agents/skills/` was listed in full. It contains exactly one skill.

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `frontend-design` | **Does not apply.** Its `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one". This story changes one SQL statement behind an unchanged `list[str]` return; nothing rendered changes, and AC 7 forbids touching `chat_ui/chat_ui/admin_copy.py`. | none |

No skill constrains this work. The story's `skills: []` frontmatter is correct.

---

## Prior Verification (do not re-litigate)

STORY-001 §3.4 already proved the approach executes on the real endpoint:

```
recursive CTE split of pii_entities: OK -> [('PERSON', 6), ('EMAIL_ADDRESS', 3)]
```

This plan additionally verified the *exact* statement below against SQLite,
comparing it row-for-row with the current Python loop over a fixture containing a
multi-entity value, a repeated-within-one-row value, a `NULL`, an empty string, and
an embedded empty segment (`"A,,B"`):

```
SQL : [('PERSON', 3), ('', 2), ('EMAIL_ADDRESS', 2), ('A', 1), ('B', 1), ('LOCATION', 1), ('PHONE_NUMBER', 1)]
Py  : [('PERSON', 3), ('', 2), ('EMAIL_ADDRESS', 2), ('A', 1), ('B', 1), ('LOCATION', 1), ('PHONE_NUMBER', 1)]
empty table -> []
LIMIT 0     -> []
```

Identical, including the empty-segment cases. See "Design Decisions" for why the
seed row is `NULL` and not `''`.

---

## Design Decisions

### 1. The seed column is `NULL`, not `''`

The idiomatic SQLite split CTE seeds with `SELECT '', col || ','` and then discards
the seed with `WHERE entity <> ''`. That filter is wrong here: it would also discard
genuine empty segments, so a stored `"A,,B"` would produce `{A: 1, B: 1}` where the
current `for entity in row["pii_entities"].split(",")` loop produces
`{A: 1, "": 1, B: 1}`. AC 3 asks for identical output on the same data and AC 4 asks
that each segment contribute one to its own count "exactly as the current loop does".
Seeding with `NULL` and filtering `WHERE entity IS NOT NULL` separates "the seed"
from "an empty entity" and reproduces `str.split(",")` exactly, `""` included.

Empty segments should not occur — `app/services/audit_logger.py:45` writes
`",".join(pii_entities) if pii_entities else None`, so an empty list becomes `NULL`
— but the column is TEXT holding whatever history put there, and the story is
explicit that behavior is preserved rather than tidied.

### 2. The tie-break becomes `entity ASC`, stated

Today's `sorted(counts.items(), key=lambda item: item[1], reverse=True)` is stable
over `dict` insertion order, so ties resolve first-seen-wins — which is really
"whatever order the rows came back in", i.e. table order. That is incidental, and
the story says so. The rewrite pins `ORDER BY COUNT(*) DESC, entity ASC`:
deterministic, independent of row order, and reproducible across instances.

This is a **deliberate, declared behavior change** under AC 3's escape clause and
must be stated in the report. It is invisible to both existing tie-bearing tests —
`test_top_pii_entities_ranked_by_frequency_desc` asserts `[0]` and a `set()`, and
`test_top_pii_entities_respects_limit` has no tie at the cut — so AC 6's "existing
coverage passes unmodified" holds. Task 2 pins the new rule with its own test.

### 3. `SELECT entity` only, not `SELECT entity, COUNT(*)`

Mirrors `top_models()` / `top_users()`, which select only the value column and order
by `COUNT(*) DESC` without projecting it. The count is never returned to the caller,
so there is no reason to ship it. Verified: SQLite accepts an aggregate in `ORDER BY`
that is absent from the select list, and `cursor.description` still reports `entity`,
so `_Row.__getitem__` by name works.

### 4. No schema change

PRD Section 4 puts new tables, columns, and indexes out of scope. A `pii_entities`
junction table would make this trivial and belongs in a different PRD. The CTE scans
`audit_logs` server-side; that cost stays in the database, which is the entire point.

---

## Patterns to Follow

### Naming and shape of a ranked read

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

The target shape: `with _session() as conn:` wraps the whole body (the current
`top_pii_entities` closes the session *before* counting — that goes away), a
triple-quoted SQL literal, `?` placeholders in a tuple, and a comprehension reading
the row by column name.

### Error handling

```python
# SOURCE: app/db/database.py:439-451
@contextmanager
def _session() -> Iterator[_Connection]:
    with _translated():
        conn = get_connection()
        with conn:
            yield conn
```

No `try` / `except` is written in a read function. `_session()` already translates
every driver `ValueError` into an `app/db/errors.py` type, so a missing `audit_logs`
table still raises `MissingRelationError` from the new statement exactly as it did
from the old one. Nothing about the error surface changes.

### Row access by name

```python
# SOURCE: app/db/database.py:65-92 (_Row)
def __getitem__(self, key):
    if isinstance(key, str):
        index = self._names[key]
        return self._values[index]
```

`_Row` builds its name index from `cursor.description`. A CTE's projected column is
named by its select-list expression, so `SELECT entity FROM split` yields
`description[0][0] == "entity"` and `row["entity"]` resolves. Confirmed in the probe.

### Tests

```python
# SOURCE: tests/test_db.py:748-776
def test_top_pii_entities_ranked_by_frequency_desc(temp_db):
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-01T10:00:00Z",
            user_id="a",
            prompt_hash="h1",
            pii_entities="EMAIL_ADDRESS,PERSON",
        )
    )
    ...
    # EMAIL_ADDRESS: 2, PERSON: 1, PHONE_NUMBER: 1 -- no tie at the top
    assert top_pii_entities()[0] == "EMAIL_ADDRESS"
```

New tests go beside these: `temp_db` fixture, seeded through the public
`insert_audit_log(AuditLog(...))` rather than raw SQL, distinct `prompt_hash` per row
(duplicate detection is keyed on it), a comment stating the expected counts, and a
plain `assert` on the function's return.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/database.py` | UPDATE | Rewrite `top_pii_entities()` (lines 710-722) as a single aggregating statement |
| `tests/test_db.py` | UPDATE | Add cases for multi-entity values, the specified tie-break, repetition within one row, and rows without PII |

No files to create. `chat_ui/chat_ui/admin_copy.py` is explicitly **not** touched (AC 7).

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Rewrite `top_pii_entities()` to aggregate in SQL

- **File**: `app/db/database.py`
- **Action**: UPDATE (replace lines 710-722 in full)
- **Implement**: replace the body with the single statement below. Keep the
  signature `def top_pii_entities(limit: int = 5) -> list[str]:` byte-for-byte.
  Add a docstring in the module's established voice — it explains *why*, not what —
  covering the three things a reader cannot recover from the SQL: that the column is
  comma-separated TEXT and the CTE is what splits it, that the `NULL` seed (rather
  than `''`) is what keeps an empty segment countable, and that the `entity ASC`
  tie-break is chosen and deterministic where the old Python sort's was incidental.

```python
def top_pii_entities(limit: int = 5) -> list[str]:
    """The most frequent PII entity types, most frequent first.

    `pii_entities` is comma-separated TEXT, not a normalized table, so ranking it
    means splitting it -- and the split belongs in the database. This used to read
    every PII-bearing row and count them in a Python dict, which was free against a
    local file and is the whole PII history over the network against a remote one
    (PRD-007 Section 6 Pattern 4). The recursive CTE peels one entity off the front
    of each value per step, and at most `limit` rows come back.

    **The seed row selects `NULL`, not `''`.** The usual idiom seeds with `''` and
    drops the seed with `WHERE entity <> ''`, which would also drop a genuine empty
    segment -- `"A,,B"` would lose its middle where `"A,,B".split(",")` keeps it.
    `NULL` distinguishes the seed from an empty entity, so this counts exactly what
    the loop it replaces counted.

    **The tie-break is chosen here, not inherited.** The old `sorted(..., key=count,
    reverse=True)` was stable over dict insertion order, so equal counts resolved by
    whichever row the database happened to return first -- incidental, and not a
    thing to reproduce across N instances. Equal counts now order by entity name
    (STORY-009).
    """
    with _session() as conn:
        rows = conn.execute(
            """
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
            """,
            (limit,),
        ).fetchall()
        return [row["entity"] for row in rows]
```

- **Mirror**: `app/db/database.py:670-683` (`top_models`) for the session/execute/
  comprehension shape; `app/db/database.py:452-478` (`init_db`) for docstring voice.
- **Check while editing**: the Python `counts` dict and the `sorted(...)` call must
  both be gone. `grep -n "counts" app/db/database.py` should return nothing from
  this function.
- **Validate**: `python -c "import app.db.database"` (module imports clean), then
  `python -m pytest tests/test_db.py -k top_pii_entities -q` — the two existing tests
  pass **unmodified** (AC 6).

### Task 2: Extend `tests/test_db.py` with the cases the rewrite makes load-bearing

- **File**: `tests/test_db.py`
- **Action**: UPDATE (insert after `test_top_pii_entities_respects_limit`, which ends
  at line 807; do not modify lines 748-807)
- **Implement**: four new tests, in this order, each seeded via `insert_audit_log`
  with a distinct `prompt_hash`:
  1. `test_top_pii_entities_counts_each_entity_in_a_multi_entity_value` — one row with
     `pii_entities="EMAIL_ADDRESS,PERSON,LOCATION"` and one with `pii_entities="PERSON"`.
     Assert `top_pii_entities() == ["PERSON", "EMAIL_ADDRESS", "LOCATION"]`. This pins
     AC 4 (each comma-separated segment counts once) *and* the tie-break in one
     assertion: PERSON has 2, the other two tie at 1 and order alphabetically.
  2. `test_top_pii_entities_breaks_ties_by_entity_name` — three rows,
     `"PERSON"`, `"LOCATION"`, `"EMAIL_ADDRESS"`, all count 1, inserted in that
     deliberately non-alphabetical order so the test would fail if insertion order
     still decided the outcome. Assert
     `top_pii_entities() == ["EMAIL_ADDRESS", "LOCATION", "PERSON"]`. The comment must
     state that the rule is chosen, not inherited — pointing at STORY-009.
  3. `test_top_pii_entities_counts_repeats_within_one_value` — a single row with
     `pii_entities="PERSON,PERSON,EMAIL_ADDRESS"`. Assert
     `top_pii_entities() == ["PERSON", "EMAIL_ADDRESS"]`: PERSON is 2 from one row.
     This is the case a `DISTINCT`-based or row-counting rewrite would get wrong.
  4. `test_top_pii_entities_ignores_rows_without_pii` — one row with
     `pii_entities="PERSON"` and two rows with `pii_entities` left at its `None`
     default. Assert `top_pii_entities() == ["PERSON"]` — no `None` and no `""` in
     the result.
- **On the empty case (AC 5)**: the empty *table* is already covered by
  `test_aggregates_on_empty_db_return_zero_or_empty` at
  `tests/test_db.py:709-717` (`assert top_pii_entities() == []`) — do **not**
  duplicate it. "A table with rows but no PII rows" is covered by new test 4 above,
  so no fifth test is needed. Say this explicitly in the report so AC 5 reads as
  discharged rather than skipped.
- **On `"A,,B"`**: deliberately **not** given a test. Such a value is unreachable
  through `app/services/audit_logger.py:45`, so a test would pin behavior on data the
  application cannot produce. The `NULL`-seed design note and the docstring carry the
  reasoning instead. Record this as a choice in the report.
- **Mirror**: `tests/test_db.py:748-776`.
- **Validate**: `python -m pytest tests/test_db.py -k top_pii_entities -q` — six tests
  pass (2 existing + 4 new).

### Task 3: Confirm no caller or copy changed

- **File**: none — verification only
- **Action**: VERIFY
- **Implement**: confirm the contract at `chat_ui/chat_ui/admin_copy.py:315-317` still
  holds and was not edited, and that no call site needed a change.
- **Validate**:
  ```bash
  git diff --stat                 # exactly two files: app/db/database.py, tests/test_db.py
  git diff -- chat_ui/            # empty
  grep -rn "top_pii_entities" app/routers/admin.py chat_ui/chat_ui/admin_state.py
  ```
  Both call sites (`app/routers/admin.py:84` with no argument,
  `chat_ui/chat_ui/admin_state.py:255-258` with `limit=RANKED_LIMIT`) must be
  byte-identical to `HEAD`.

### Task 4: Run the full suite

- **File**: none
- **Action**: VERIFY
- **Implement**: the rewrite is behind an unchanged signature, so the proof it is
  transparent is that every suite reading this figure is still green —
  `tests/test_stats_router.py:137-171` and
  `tests/test_pii_redaction_integration.py:214,261` exercise it end to end through
  `GET /stats`, and `tests/test_admin_state.py` exercises the console read.
- **Validate**: `python -m pytest -q` with the libSQL dev server running.

---

## End-to-End Tests

- [ ] libSQL dev server reachable: `curl -sf http://127.0.0.1:8080/health`
- [ ] `python -m pytest tests/test_db.py -q` — green, existing `top_pii_entities`
      tests unmodified
- [ ] `python -m pytest tests/test_stats_router.py -q` — `GET /stats` returns
      `top_pii_entities` ranked as before
- [ ] `python -m pytest tests/test_pii_redaction_integration.py -q` — the PRD-006
      byte-pinned suite still passes untouched
- [ ] `python -m pytest tests/test_admin_state.py -q` — the console's ranked figure
      still renders
- [ ] Round-trip cap check (AC 2): seed 50 PII-bearing rows spanning 7 entity types,
      call `top_pii_entities(limit=5)`, assert `len(...) == 5`. The old implementation
      transferred 50 rows for the same answer; the new one transfers 5.
- [ ] `git diff -- chat_ui/` is empty (AC 7)

## Validation

```bash
curl -sf http://127.0.0.1:8080/health
python -m pytest tests/test_db.py -k top_pii_entities -q
python -m pytest -q
git diff --stat   # app/db/database.py, tests/test_db.py -- and nothing else
```

---

## Risks

| Risk | Mitigation |
|------|------------|
| Recursive CTE unsupported or slow on the endpoint | Already executed against the live endpoint in STORY-001 §3.4. Task 4's full-suite run is against the real libSQL server, not a mock. |
| The `NULL`-seed subtlety is lost in a later edit and someone "simplifies" it to `WHERE entity <> ''` | The docstring states the reason, and the design note makes the regression visible in review. |
| The declared tie-break change surprises a consumer | No consumer asserts on tie order: `test_admin_state.py` and `test_stats_router.py` compare against `set()` or index `[0]`. The change is stated in the report per AC 3. |
| A CTE column name the `_Row` index cannot resolve | Verified: `SELECT entity FROM split` reports `description[0][0] == "entity"`. |
| STORY-010 must fold this statement into the batched read | Written as a single self-contained statement with one `?` parameter, which is exactly what a `json_group_array` sub-select in STORY-010 can wrap. Sequencing is intentional (story note). |

---

## Acceptance Criteria

(Copied from story `STORY-009`)

- [ ] Given `top_pii_entities(limit=5)`, when it is called, then its signature, return type (`list[str]`), and ordering semantics are unchanged: entity names in descending frequency, capped at `limit`.
- [ ] Given a database with PII history, when the function runs, then it transfers at most `limit` rows from the database. The whole-table scan into Python is gone.
- [ ] Given the same data, when the new implementation and the old one are compared, then they produce identical output — including the tie-breaking order for entities with equal counts. If the old tie-break was incidental rather than specified, state the chosen behavior explicitly in the report.
- [ ] Given a `pii_entities` value holding multiple comma-separated entities, when it is counted, then each entity in the value contributes one to its own count, exactly as the current `for entity in row["pii_entities"].split(",")` loop does.
- [ ] Given an empty table or one with no PII rows, when the function runs, then it returns an empty list without error.
- [ ] Given `tests/test_db.py`, when it runs, then the existing `top_pii_entities` coverage passes unmodified, plus new cases for multi-entity values, ties, and the empty case.
- [ ] Given `chat_ui/chat_ui/admin_copy.py`, when its contract is checked, then the statement at line 317 still holds — the visible cap "comes from the read's own limit (`top_pii_entities(limit=5)`)". No copy change is needed or permitted.
- [ ] All tasks completed
- [ ] Full test suite passes against the libSQL dev server
- [ ] Follows existing patterns (`top_models` / `top_users` shape, `_session()` error surface)
