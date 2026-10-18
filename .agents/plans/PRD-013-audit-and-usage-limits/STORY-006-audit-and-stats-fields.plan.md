---
story: STORY-006
prd: PRD-013
slug: audit-and-stats-fields
title: "/audit entry fields and /stats token aggregates"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-013-audit-and-usage-limits        # all stories commit here, no per-story branch
created: 2026-10-17
---

# Plan: /audit entry fields and /stats token aggregates

## Summary

STORY-002 added the eight columns and STORY-005 writes them. This story makes them readable over HTTP. Nothing is written differently.

- **`GET /audit`.** `AuditQueryEntry` gains `ingress`, `message_count`, `input_tokens`, `output_tokens`, `streamed`, `has_tool_calls`, `conversation_key` and `limit_exceeded`. All eight are optional or defaulted, with no validators. `get_audit` copies them from the `AuditLog` it already holds. `dedup_key` stays hidden (PRD-009 D5).
- **`GET /stats`.** `StatsResponse` gains `input_tokens: int = 0`, `output_tokens: int = 0` and `blocked_usage_limits: int = 0`. `get_stats` keeps calling `summary_snapshot(row_limit=0)` with nothing else passed.
- **The batched read.** `_SUMMARY_SQL` gets three columns after `top_pii_entities`: `input_tokens`, `output_tokens` and `blocked_usage_limits`. None of them takes a parameter, so the four positional parameters keep their order (PRD Risk 8). `SUMMARY_FIGURES`, `_SUMMARY_DECODERS`, `_summary_figure_by_figure` and `SummarySnapshot` each gain the same three entries. Three standalone functions are added: `sum_input_tokens()`, `sum_output_tokens()` and `count_blocked_usage_limits()`. Each is that column's subquery as its own statement. The "what counts" predicates live in shared constants so the batched and standalone reads cannot drift.
- **Console state only.** `_READS` in `chat_ui/chat_ui/admin_state.py` gains three entries with three new `READ_LABEL_*` copy strings. `AdminState` gains three `int = 0` vars. `load()` already commits every figure by name, so it needs no change. Rendering the figures is STORY-015.

**One acceptance criterion cannot be met as written (F-1).** AC 5 says "no existing assertion changes". About a dozen existing tests pin an *inventory*: the exact key set of an `/audit` entry or `/stats` body, the ten names in `SUMMARY_FIGURES`, or a literal `10` for the figure count. Those tests must list the new names or they fail. AC 4 itself requires the agreement test to cover all thirteen figures. The plan follows the STORY-002 F-2 precedent, which itself followed PRD-012 STORY-011. Only inventory assertions change: a key set gains keys, a count goes from 10 to 13, or a `== {...}` literal gains the new keys with their zero or `None` defaults. Each change carries a `# PRD-013 STORY-006` comment. No pre-existing *value* changes, which is the second half of AC 5. Task 6 checks this with a diff filter.

**Nothing below was run.** Docker Desktop was not running when this plan was written, so the libSQL dev container (`tests/conftest.py`) could not be reached. Expected values come from reading the code.

## User Story

As a compliance admin
I want the new audit fields on `GET /audit` and token totals on `GET /stats`
So that I can read cost and grouping without database access

## Story Reference

- Story file: `.agents/stories/PRD-013-audit-and-usage-limits/STORY-006-audit-and-stats-fields.md`
- PRD: `.agents/PRDs/PRD-013-audit-and-usage-limits/PRD.md` (Sections 6.2, 6.10, 7/F13, 10, 11 *Audit*, 14 Risk 8)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `app/models/schemas.py`, `app/routers/admin.py`, `app/db/database.py`, `chat_ui/chat_ui/admin_state.py`, `chat_ui/chat_ui/admin_copy.py`, tests |
| Story | STORY-006 |
| PRD | PRD-013 |
| Depends on | STORY-005 ✅ done (`1ab83f2`) |
| Epic Branch | `epic/PRD-013-audit-and-usage-limits` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `frontend-design` is the only skill in `.agents/skills/`. It covers UI surfaces, and this story renders nothing; STORY-015 does. The three `READ_LABEL_*` strings are fault-message copy. They follow the existing labels' wording rule ("the object of 'Could not read ___', each begins with an article", `admin_copy.py:160-163`) rather than any new direction. | Task 4 (copy only) |

---

## Findings from Exploration

- **F-1: inventories that must grow.** These assertions pin exact sets or counts and are the only ones edited:

  | Test | Line(s) | What grows |
  |---|---|---|
  | `tests/test_audit_router.py::test_valid_token_returns_expected_shape` | 73-95 | entry key set +8 |
  | `tests/test_pii_redaction_integration.py` (sorted `/audit` entry keys) | 194-213 | sorted list +8, kept alphabetical |
  | `tests/test_schemas.py::test_audit_response_shape` | 137-163 | `model_dump()` literal +8 (`None` ×6, `False` ×2) |
  | `tests/test_schemas.py::test_stats_response_shape` | 195-205 | literal +3 (`0` ×3) |
  | `tests/test_stats_router.py` | 116-126, 188-198, 265-275, 424-434 | key sets +3; `== {...}` literals +3 |
  | `tests/test_stats_router.py::_snapshot_of` | 375-392 | +3 figures. **Required**: `SummarySnapshot.__post_init__` refuses a snapshot that does not cover `SUMMARY_FIGURES` |
  | `tests/test_reporting_invariance.py` | 276-286, 581-591 | `/stats` key sets +3 |
  | `tests/test_db.py::_individually` | 1624-1637 | oracle +3 standalone reads |
  | `tests/test_db.py::test_summary_snapshot_on_an_empty_database` | 1720-1738 | literal +3 zeros |
  | `tests/test_db.py::test_summary_snapshot_issues_one_round_trip` | 1825 | `len(statements) == 10` → `13` (the fallback contrast) |
  | `tests/test_db.py::test_summary_snapshot_types_match_the_standalone_functions` | 1710-1716 | int-figure tuple +3 (extends, does not change) |
  | `tests/test_admin_state.py::_READ_RETURNS` | 372-383 | +3 entries keyed by the new functions' `__name__`. **Required**: the `_Reads` stub looks results up by function name |
  | `tests/test_admin_state.py::test_the_read_table_names_all_ten_database_functions` | 580-602 | `10` → `13` ×3, name set +3 |
  | `tests/test_admin_state.py::test_load_runs_all_ten_reads_off_the_event_loop` | 618 | `10` → `13` |
  | `tests/test_admin_state.py::test_loading_is_true_for_the_duration_and_false_after` | 685 | `10` → `13` |

  Not in the list on purpose: `test_reporting_invariance.py:563` compares against `set(AuditQueryEntry.model_fields)` and follows automatically. The `len(failing.calls) == 8` assertions in `test_admin_state.py` also hold, because the new reads are appended after position 8. The `test_summary_snapshot_leaves_the_ten_standalone_signatures_unchanged` test (`test_db.py:1845`) pins the *existing* ten signatures, which do not change, so it is left alone. Task 0's grep is the safety net for anything this table missed.

- **F-2: the positional binding.** `summary_snapshot()` binds `(row_limit, ranked_limit, ranked_limit, ranked_limit)` positionally, in column order (`database.py:1205-1210`, `1389-1392`). The three new columns are plain aggregates with no `?` and come after `top_pii_entities`. The tuple does not change. `test_summary_snapshot_limits_are_parameters` (`test_db.py:1829`) already catches a misbinding because it uses different limit values.

- **F-3: what "NULL as 0" means in SQL.** `SUM(col)` over zero rows, or over rows where every value is NULL, returns NULL. Over a mix it skips the NULLs. So `COALESCE(SUM(col), 0)` is exactly "SUM with NULL as 0", and it returns `0` on an empty table. `_decode_count` (`int(value)`) then decodes it like every other count. Both the standalone and the batched read use the same expression. Like `_BLOCKED_SUSPICIOUS_WHERE` (`database.py:958-970`), it is written once as a module constant.

- **F-4: `blocked_usage_limits` is 0 today.** No row has `limit_exceeded` set until STORY-011. Tests seed `AuditLog(limit_exceeded="requests")` directly through `insert_audit_log`, which has written the column since STORY-002, so the figure is non-trivial in this story.

- **F-5: pre-PRD rows.** `_row_to_audit_log` (`database.py:899-906`) already maps NULL to `None` for the six nullable columns, and the two `NOT NULL DEFAULT 0` flags come back as `bool(0) == False`. A row inserted with a default `AuditLog()` stands in for "a row written before this PRD" for AC 2: the six are NULL and the flags 0. That is the same state convergence leaves an old row in, which STORY-002 already tested.

- **F-6: console commit path.** `load()` does `setattr(self, field, value)` for every remaining figure (`admin_state.py:1092-1103`). A figure with no declared var would make Reflex raise at commit time, which is why the three vars are added here even though nothing renders them. `sign_out()` resets to declared defaults, so `int = 0` keeps the "empty default" rule (`admin_state.py:425-431`).

---

## Patterns to Follow

### Read-model field: optional, defaulted, unvalidated
```python
# SOURCE: app/models/schemas.py:184-191
    # PRD-012 D9: the profile that ran (`chat`, `code`, or a custom name).
    # ... Optional,
    # defaulted and unvalidated for `session_id`'s reasons: NULL on every row
    # written before PRD-012 and on /query's foreign-session refusal.
    profile: Optional[str] = None
```

### Verbatim passthrough in the router
```python
# SOURCE: app/routers/admin.py:57-58
            # Verbatim passthrough (PRD-012 D9); NULL on pre-PRD-012 rows.
            profile=log.profile,
```

### Shared predicate, standalone function
```python
# SOURCE: app/db/database.py:966-977
_BLOCKED_SUSPICIOUS_WHERE = (
    "suspicious_pattern IS NOT NULL"
    " AND (pattern_action IS NULL OR pattern_action = 'block')"
)


def count_blocked_suspicious() -> int:
    with _session() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM audit_logs WHERE {_BLOCKED_SUSPICIOUS_WHERE}"
        ).fetchone()
        return row["n"]
```

### Summary column + decoder + fallback entry
```python
# SOURCE: app/db/database.py:1263-1265, 1308-1309, 1341
  (SELECT COUNT(*) FROM audit_logs WHERE {_BLOCKED_SUSPICIOUS_WHERE})
      AS blocked_suspicious,
...
    "blocked_suspicious": _decode_count,
...
        ("blocked_suspicious", count_blocked_suspicious),
```

### Console read table entry
```python
# SOURCE: chat_ui/chat_ui/admin_state.py:258-263
    (
        "blocked_suspicious",
        READ_LABEL_BLOCKED_SUSPICIOUS,
        count_blocked_suspicious,
        {},
    ),
```

### Inventory edit with provenance comment
```python
# SOURCE: tests/test_audit_router.py:89-95
            # PRD-011 D6: two additive, nullable fields (STORY-010).
            "pattern_role",
            "pattern_action",
            # PRD-012 D9: additive, nullable (STORY-011).
            "profile",
```

### Tests: seed via `insert_audit_log`, read via `TestClient`
```python
# SOURCE: tests/test_audit_router.py:40-66 (shape) and tests/test_db.py:1678-1693 (agreement)
    snapshot = summary_snapshot()
    expected = _individually()
    assert snapshot.errors == {}
    assert set(snapshot.figures) == set(SUMMARY_FIGURES)
    for name in SUMMARY_FIGURES:
        assert snapshot.figures[name] == expected[name], name
```

---

## Design

### `app/models/schemas.py`

```python
class AuditQueryEntry(BaseModel):
    ...
    profile: Optional[str] = None
    # PRD-013 Section 6.2/6.10: ...comment in the house style...
    ingress: Optional[str] = None
    message_count: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    streamed: bool = False
    has_tool_calls: bool = False
    conversation_key: Optional[str] = None
    limit_exceeded: Optional[str] = None


class StatsResponse(BaseModel):
    ...
    top_pii_entities: List[str] = []
    input_tokens: int = 0
    output_tokens: int = 0
    blocked_usage_limits: int = 0
```

One comment block covers the eight. It says they are unvalidated for `session_id`'s reasons. It says the two flags are `False` rather than `None` because `0` is true of every older row (PRD 6.2). It says `conversation_key` is a grouping aid while `dedup_key` stays hidden (D5). It says a usage-limit row is `success=true` (PRD Section 10).

### `app/db/database.py`

```python
# What "NULL as 0" means for the two token totals (PRD-013 6.10)...
_SUM_INPUT_TOKENS = "COALESCE(SUM(input_tokens), 0)"
_SUM_OUTPUT_TOKENS = "COALESCE(SUM(output_tokens), 0)"
# A usage-limit refusal is the only row that names a limit (PRD-013 6.2)...
_BLOCKED_USAGE_LIMITS_WHERE = "limit_exceeded IS NOT NULL"

def sum_input_tokens() -> int: ...      # SELECT {_SUM_INPUT_TOKENS} AS n FROM audit_logs
def sum_output_tokens() -> int: ...
def count_blocked_usage_limits() -> int: ...
```

Place them after `top_pii_entities()` and before `SUMMARY_FIGURES`. `SUMMARY_FIGURES` appends `"input_tokens", "output_tokens", "blocked_usage_limits"`. `SummarySnapshot` gains three `@property` that call `_figure`. `_SUMMARY_SQL` appends the following after `AS top_pii_entities` (add a comma there):

```sql
  (SELECT {_SUM_INPUT_TOKENS} FROM audit_logs) AS input_tokens,
  (SELECT {_SUM_OUTPUT_TOKENS} FROM audit_logs) AS output_tokens,
  (SELECT COUNT(*) FROM audit_logs WHERE {_BLOCKED_USAGE_LIMITS_WHERE})
      AS blocked_usage_limits
```

`_SUMMARY_DECODERS` maps all three to `_decode_count`. `_summary_figure_by_figure`'s `reads` tuple gains the three functions in the same order. Wherever the comments and docstrings say "ten", they become "thirteen", or "ten ... plus PRD-013's three" where the history matters. The positional-binding comment gains one sentence: the three new columns take no parameter and come last, so the tuple is unchanged (Risk 8).

### `app/routers/admin.py`

`get_audit`: add the eight keyword arguments after `profile=log.profile`, under a `# Verbatim passthrough (PRD-013 6.10) ...` comment. `get_stats`: add `input_tokens=snapshot.input_tokens`, `output_tokens=snapshot.output_tokens` and `blocked_usage_limits=snapshot.blocked_usage_limits`. `row_limit=0` stays, and so does the absence of `ranked_limit`. The long comment's "nine figures" and "tenth figure" wording is updated so it stays accurate: `/stats` now reads twelve of the thirteen and declines `rows`.

### Console (`chat_ui/chat_ui/`)

- `admin_copy.py`: add `READ_LABEL_INPUT_TOKENS = "the input token total"`, `READ_LABEL_OUTPUT_TOKENS = "the output token total"` and `READ_LABEL_USAGE_LIMITS = "the usage-limit refusals"`. Update the "ten reads" comment.
- `admin_state.py`: import the three functions and labels. Append three `_READS` entries, using the `{}` kwargs form. Add three vars under `# --- The record ---` after `top_pii_entities`: `input_tokens: int = 0`, `output_tokens: int = 0`, `blocked_usage_limits: int = 0`. Update the "ten" comments. Do not touch `load()`.

### Dependency order

schemas → database (constants, functions, `SUMMARY_FIGURES`, snapshot, SQL, decoders, fallback) → router → console copy and state → inventories → new tests. The database edits and the console `_READS` edit must land in the same commit. Between them, `test_admin_state` fails because `_READS` and `SUMMARY_FIGURES` disagree on length.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/models/schemas.py` | UPDATE | 8 fields on `AuditQueryEntry`, 3 on `StatsResponse` |
| `app/db/database.py` | UPDATE | 3 constants, 3 standalone reads, `SUMMARY_FIGURES` 10→13, 3 properties, 3 SQL columns, 3 decoders, 3 fallback reads |
| `app/routers/admin.py` | UPDATE | passthrough in `get_audit`, three figures in `get_stats` |
| `chat_ui/chat_ui/admin_copy.py` | UPDATE | 3 `READ_LABEL_*` strings |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | 3 `_READS` entries, 3 state vars |
| `tests/test_audit_router.py`, `tests/test_pii_redaction_integration.py`, `tests/test_schemas.py`, `tests/test_stats_router.py`, `tests/test_reporting_invariance.py`, `tests/test_db.py`, `tests/test_admin_state.py` | UPDATE | F-1 inventories only |
| `tests/test_audit_stats_prd013.py` | CREATE | the story's own behavioral tests (Task 5) |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 0: Preflight

- **Action**: Confirm the branch is `epic/PRD-013-audit-and-usage-limits` and HEAD descends from `a6482da`. Start Docker Desktop and the libSQL dev container (`harness-libsql-dev`, see `tests/conftest.py`). Run the full suite once and record the baseline pass count.
- **Inventory sweep**: `grep -rn -E '"top_pii_entities"|"profile",$|SUMMARY_FIGURES|_READS|== 10\b' tests/`. Reconcile the hits against the F-1 table. The three `log_query call sites == 10` hits are unrelated and are left alone. Add anything new to the F-1 list before editing.
- **Validate**: baseline suite green.

### Task 1: Read models

- **File**: `app/models/schemas.py`
- **Action**: UPDATE
- **Implement**: The eight `AuditQueryEntry` fields and three `StatsResponse` fields as in Design, with the comment block.
- **Mirror**: `app/models/schemas.py:184-191`
- **Validate**: `$PY -c "from app.main import app"`

### Task 2: The thirteen-figure read

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: Everything in Design › `app/db/database.py`. Append only. Do not reorder any existing column, figure, decoder or fallback read.
- **Mirror**: `database.py:958-977` (shared predicate + function), `1091-1102` (figures), `1150-1157` (properties), `1262-1265` (column), `1305-1316` (decoders), `1337-1348` (fallback)
- **Validate**: `$PY -c "from app.db.database import summary_snapshot, SUMMARY_FIGURES; assert len(SUMMARY_FIGURES) == 13"`. A `SummarySnapshot()` built from all thirteen must not raise.

### Task 3: Router passthrough

- **File**: `app/routers/admin.py`
- **Action**: UPDATE
- **Implement**: As in Design. Keep `summary_snapshot(row_limit=0)` byte-for-byte.
- **Mirror**: `admin.py:43-58`, `114-124`
- **Validate**: `$PY -c "from app.main import app"`

### Task 4: Console read table and state

- **Files**: `chat_ui/chat_ui/admin_copy.py`, `chat_ui/chat_ui/admin_state.py`
- **Action**: UPDATE
- **Implement**: As in Design › Console. No component or rendering change.
- **Mirror**: `admin_copy.py:164-174`, `admin_state.py:249-280`, `admin_state.py:440-451`
- **Validate**: `$PY -c "import chat_ui.chat_ui.admin_state as m; from app.db.database import SUMMARY_FIGURES; assert tuple(f for f,*_ in m._READS) == SUMMARY_FIGURES"`

### Task 5: The story's own tests

- **File**: `tests/test_audit_stats_prd013.py`
- **Action**: CREATE
- **Implement**: Use the `temp_db` fixture, `TestClient(app)` and `settings.ADMIN_TOKEN` headers, the same way `tests/test_audit_router.py` and `tests/test_stats_router.py` do. Prefix test names with `test_prd013_`.
  1. **AC 1, stored values pass through.** Insert one `AuditLog` with every field set to a distinctive value: `ingress="chat"`, `message_count=3`, `input_tokens=2140`, `output_tokens=312`, `streamed=True`, `has_tool_calls=True`, `conversation_key="ck-…"` and `limit_exceeded="tokens"`. `GET /audit`, then assert each of the eight equals the stored value. Use real values rather than fixture values, so the test fails if a passthrough line is dropped.
  2. **AC 2, pre-PRD row.** Insert a default `AuditLog(...)` (F-5). Assert the six nullable fields are `None` and `streamed` and `has_tool_calls` are `False`. Also run one real `POST /query` through the stubbed pipeline (the pattern in `tests/test_audit_session_id.py:91-118`). Assert `ingress == "query"`, `message_count == 1` and a non-null `conversation_key`, which ties AC 1 to the rows STORY-005 writes.
  3. **AC 1, `dedup_key` stays hidden.** The pipeline-written row carries a non-NULL `dedup_key` in the database, and the `/audit` entry has no such key.
  4. **AC 3, sums with NULL as 0.** Seed four rows: (100, 20), (None, None), (5, None) and (None, 7). Assert `/stats` gives `input_tokens == 105` and `output_tokens == 27`. Cross-check against a direct `SELECT COALESCE(SUM(...),0)` and against `sum_input_tokens()` / `sum_output_tokens()`.
  5. **AC 3, empty table.** All three figures are `0`, not `null`.
  6. **AC 3, `blocked_usage_limits`.** Seed `limit_exceeded` as `"requests"`, `"tokens"`, `None` and `None`, and expect `2`. Run it once with zero such rows and expect `0`, which is today's value until STORY-011.
  7. **AC 4, batched vs fallback, all thirteen.** Seed rows that make every figure non-trivial (reuse `tests/test_db.py::_seed_summary_fixture` by import if it is importable cleanly, otherwise a local seed, plus token and limit rows). Compute `summary_snapshot()`. Then compute `_summary_figure_by_figure(100, 5, RuntimeError("unused"))` directly, with no failure injected. Assert both have empty `errors` and equal `figures` for every name in `SUMMARY_FIGURES`, and `len(SUMMARY_FIGURES) == 13`. Also assert the batched result equals `_individually()` from `test_db.py`, which Task 6 extends.
  8. **AC 4, partition.** `SummarySnapshot(figures={13 names}, errors={})` constructs. Dropping any one of the three new names raises `AssertionError`.
  9. **Risk 8, the binding did not move.** `summary_snapshot(row_limit=2, ranked_limit=1)` on the seeded table returns two rows and one-item rankings, *and* the three new figures equal their whole-table standalone values. No limit touches them.
  10. **Isolation for a new figure.** Monkeypatch `_SUMMARY_DECODERS["input_tokens"]` to raise. Only `input_tokens` is in `errors`, `snapshot.input_tokens` re-raises, and `GET /stats` returns 500. Today, that broken read raises out of `get_stats` (`admin.py:98-101`).
  11. **Console table ties to figures.** `tuple(field for field, *_ in _READS) == SUMMARY_FIGURES`, and the three new fields are `AdminState.base_vars` with default `0`.
- **Mirror**: `tests/test_audit_router.py:310-340`, `tests/test_db.py:1678-1760`, `tests/test_stats_router.py:56-136`
- **Validate**: `$PY -m pytest tests/test_audit_stats_prd013.py -q`

### Task 6: Grow the pinned inventories (F-1)

- **Files**: the seven test files in the F-1 table
- **Action**: UPDATE
- **Implement**: Exactly the edits in the F-1 table, each under a `# PRD-013 STORY-006: additive ...` comment, matching the PRD-011 and PRD-012 comment style already in those lists. `_READ_RETURNS` gains `"sum_input_tokens": 2140`, `"sum_output_tokens": 312` and `"count_blocked_usage_limits": 0`. Use non-zero token values so a dropped commit shows up. `test_load_builds_audit_rows_newest_first_with_the_true_total` is **not** edited, because its existing assertions are values and must hold as they are. The new state vars are covered by Task 5 #11.
- **Validate**:
  - `$PY -m pytest tests/test_audit_router.py tests/test_pii_redaction_integration.py tests/test_schemas.py tests/test_stats_router.py tests/test_reporting_invariance.py tests/test_db.py tests/test_admin_state.py -q`
  - AC 5 audit: `git diff -U0 HEAD -- tests/ ':!tests/test_audit_stats_prd013.py' | grep '^-' | grep -v '^---'`. Every removed line must be a `10`→`13` count, a docstring or comment wording ("ten"→"thirteen"), or a closing line that moved when keys were appended. No expected value may be removed.

### Task 7: Prove the tests bite

- **Action**: Temporarily break the code in each of these four ways and confirm that a Task 5 test fails each time, then revert:
  1. Delete the `conversation_key=` passthrough line.
  2. Change `_SUM_INPUT_TOKENS` to `SUM(input_tokens)`, which makes the empty-table case `None`.
  3. Insert the new columns *before* `top_models`, which misbinds the positional `?`.
  4. Remove one entry from `_summary_figure_by_figure`'s reads.
- **Validate**: each mutation fails at least one named test. Record which test in the report.

### Task 8: Full suite and commit

- **Action**: `$PY -m pytest -q`. The pass count should equal the baseline plus the new tests, with zero failures. Commit on the epic branch: `feat(PRD-013): STORY-006 /audit entry fields and /stats token aggregates`.
- **Validate**: `git log -1 --stat` lists only the files in *Files to Change*.

### Task 9: Report

- **Action**: Write the implementation report the way earlier PRD-013 stories did. Include the F-1 inventory diff summary, the Task 7 mutation results, and the measured `summary_snapshot` latency if one was taken. Update the story's `report` and `commit` fields and set `status: done`, then regenerate the index.

---

## End-to-End Tests

- [ ] Start the API (`uvicorn app.main:app`), send one `POST /query` with a user token, then `GET /audit` with `ADMIN_TOKEN`. The newest entry has `ingress: "query"`, `message_count: 1`, a `conversation_key`, the token split (or `null` if the provider omitted it), `streamed: false`, `has_tool_calls: false`, `limit_exceeded: null`, and no `dedup_key`.
- [ ] `GET /stats`: `input_tokens` and `output_tokens` equal `SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0) FROM audit_logs` run directly against the dev database, and `blocked_usage_limits` is `0`.
- [ ] Every pre-existing `/stats` field returns the same value as it did on `a6482da` against the same database. Capture the body before the change and diff it after.
- [ ] The admin console still signs in and loads with no fault panel. Nothing new is rendered, as expected.

---

## Validation

```bash
# libSQL dev server must be up (tests/conftest.py; container harness-libsql-dev)
PY=/c/Users/tobip/.venvs/harness-ai/Scripts/python.exe
$PY -c "from app.main import app"
$PY -m pytest tests/test_audit_stats_prd013.py -q
$PY -m pytest tests/test_db.py tests/test_stats_router.py tests/test_audit_router.py tests/test_admin_state.py tests/test_reporting_invariance.py tests/test_schemas.py tests/test_pii_redaction_integration.py -q
$PY -m pytest -q
git diff -U0 a6482da -- tests/ ':!tests/test_audit_stats_prd013.py' | grep '^-' | grep -v '^---'
```

There is no frontend lint: the UI is Reflex (Python), and this story touches only state and copy.

---

## Risks + Mitigations

| Risk | Mitigation |
|---|---|
| A new column is inserted before an existing parameterized one and misbinds `?` (PRD Risk 8) | Append after `top_pii_entities` only. `test_summary_snapshot_limits_are_parameters` uses distinct limits, and Task 7 mutation 3 shows it fails |
| `SUM` returns NULL on an empty or all-NULL table, and `/stats` either 500s on `int(None)` or reports `null` | `COALESCE(..., 0)` in one shared constant (F-3), with an empty-table test |
| Batched and standalone token sums drift (for example, one forgets the COALESCE) | Both read the same constant. The AC 4 agreement test covers all thirteen |
| `_READS` and `SUMMARY_FIGURES` disagree, the console commits a figure into an undeclared var, or the fault arm mislabels it | Same-commit edit (Design › Dependency order). Task 5 #11 asserts the tuples are equal |
| An inventory edit hides a value change, against AC 5 | Inventory edits only, each commented. The Task 6 removed-line audit |
| `/stats` payload grows | Three ints. `row_limit=0` still keeps `rows` empty |
| Docker or libSQL is unavailable, so no test can run | Task 0 blocks on it. Do not mark the story done without a green run |

---

## Acceptance Criteria

(Copied from story `STORY-006`)

- [ ] Given rows written by STORY-005, when `GET /audit` is called, then each entry carries `ingress`, `message_count`, `input_tokens`, `output_tokens`, `streamed`, `has_tool_calls`, `conversation_key` and `limit_exceeded` as stored.
- [ ] Given a row written before this PRD, when `GET /audit` returns it, then the six nullable fields are `null` and the two flags are `false`.
- [ ] Given rows with and without a token split, when `GET /stats` is called, then `input_tokens` and `output_tokens` equal `SUM` over `audit_logs` with NULL as 0, and `blocked_usage_limits` equals the count of rows with `limit_exceeded IS NOT NULL` (0 until STORY-011).
- [ ] Given the batched read and the figure-by-figure fallback, when both are run against the same data, then all thirteen figures agree, and `SummarySnapshot` still partitions `SUMMARY_FIGURES` exactly.
- [ ] Given the existing `/audit` and `/stats` tests, when they run, then no existing assertion changes and every pre-existing response field keeps its value. *(Met as described in F-1: inventory assertions grow, no value assertion changes.)*
- [ ] All tasks completed
- [ ] Backend server starts without error
- [ ] Follows existing patterns
