---
story: STORY-010
prd: PRD-011
slug: narrowed-counters-and-admin-fields
title: "blocked_suspicious counts blocks only; role and action surfaced in /audit and the console"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-011-pattern-policy        # all stories commit here, no per-story branch
created: 2026-09-23
---

# Plan: blocked_suspicious counts blocks only; role and action surfaced in /audit and the console

## Summary

STORY-009 added `pattern_role` and `pattern_action` to `audit_logs` and made the pipeline write flag rows. Every reader still treats `suspicious_pattern IS NOT NULL` as "blocked as suspicious". This story narrows those readers and makes the two columns readable.

**The two counters.** `count_blocked_suspicious()` (`app/db/database.py:930-935`) and the `blocked_suspicious` subquery in `_SUMMARY_SQL` (`app/db/database.py:1212-1213`) both gain `AND (pattern_action IS NULL OR pattern_action = 'block')`. The predicate is written once, as a module constant, and interpolated into both statements so the two figures cannot drift apart. `NULL` counts as a block (D6, Risk 4), so no historical row moves.

**`GET /audit`.** `AuditQueryEntry` gains `pattern_role: Optional[str] = None` and `pattern_action: Optional[str] = None`, and `get_audit` passes both through verbatim. `suspicious_pattern_detected` is **not** narrowed. It still means "a pattern was matched", so it is true for a flag row as well.

**The snapshot JSON.** STORY-009 already carries both fields in `_SUMMARY_SQL`'s `json_object` (`database.py:1205-1206`) and in `_row_to_audit_log` (`876-877`). This story only adds the test that the story's AC 5 asks for.

**The console Register.** `AuditRow` gains two pre-formatted strings, `pattern_role` and `pattern_action`. `to_audit_row` fills them through `_text`, so NULL renders as `VALUE_ABSENT`. The disclosure shows them on two lines directly after "Matched pattern". There is no new view, no new column in the row, and no layout change.

**One change the story's text does not name (D-C, flagged for review).** `derive_verdict` (`chat_ui/chat_ui/admin_formatting.py:84-87`) returns **denied** for any row with a `suspicious_pattern`. Left as it is, every flag row would render as "denied" on the Register. That is the console-side twin of the counter bug this story exists to fix, and it would fail AC 4's "without a misleading label". The denied arm is therefore narrowed by the same D6 rule. A flag row falls through to the existing precedence: `success=1` gives **cleared**, because the request did pass the pattern check. Its disclosure says `flag` and names the role.

## User Story

As a compliance admin
I want a flagged request not counted as a blocked one, and the triggering role visible where I read the audit
So that my security figures stay true and I can tell a careless user from a compromised data source

## Story Reference

- Story file: `.agents/stories/PRD-011-pattern-policy/STORY-010-narrowed-counters-and-admin-fields.md`
- PRD: `.agents/PRDs/PRD-011-pattern-policy/PRD.md` (Sections 6.7 D6, 7 F7, 9.2 T8, 10, 11, 14 Risk 4)
- Previous story report: `.agents/reports/PRD-011-pattern-policy/STORY-009-flag-arm-and-audit-columns.report.md` ("Notes for Later Stories: STORY-010")

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | audit counters (`app/db/database.py`), `/audit` schema and router, admin console (Reflex: `admin_models`, `admin_formatting`, `admin_copy`, `components/register.py`) |
| Story | STORY-010 |
| PRD | PRD-011 |
| Epic Branch | `epic/PRD-011-pattern-policy` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` contains only `frontend-design`. Its description is "distinctive, intentional visual design when building new UI or reshaping an existing one". This story adds two `_detail_field` lines to an existing disclosure and reshapes nothing. The story (Technical Notes) and PRD Section 15 both state the skill does not apply, and the story's `skills: []` agrees. The two new labels still follow `admin_copy.py`'s vocabulary rule, which is the skill's consistency rule already applied there: one name per fact, copy separate from values. | none (Task 6 follows `admin_copy.py`'s existing conventions) |

---

## Design Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D-A | **One predicate constant.** `_BLOCKED_SUSPICIOUS_WHERE = "suspicious_pattern IS NOT NULL AND (pattern_action IS NULL OR pattern_action = 'block')"` is placed in `app/db/database.py` beside `count_blocked_suspicious`, with a PRD-011 D6 comment. It is interpolated (f-string, module constant, no user input) into `count_blocked_suspicious`'s SQL and into `_SUMMARY_SQL`'s subquery. | AC 1 asks for "both predicates" to be the same text. `tests/test_db.py::test_summary_snapshot_agrees_with_the_individual_reads` already checks that the two agree on a fixture. One constant makes drift impossible rather than merely detected. `_SUMMARY_SQL` is a module-level string, so interpolation happens once at import. |
| D-B | **`suspicious_pattern_detected` is unchanged.** `AuditQueryEntry` gains `pattern_role` and `pattern_action` after `session_id`, both `Optional[str] = None`, with no validator. The router passes `log.pattern_role` and `log.pattern_action` through verbatim. | Story Technical Notes: "Do not narrow it to blocks". The new field is what separates the two cases. Optional with a default mirrors `session_id`'s reasoning in the same class (`schemas.py:144-163`): `None` is the honest value for every row written before the PRD, and this is a read model. |
| D-C | **`derive_verdict`: a flag is not denied.** The denied arm becomes `if log.suspicious_pattern is not None and log.pattern_action != "flag": return VERDICT_DENIED`. The precedence comment (`admin_formatting.py:33-39`) is updated to read `suspicious_pattern (block, or NULL action) -> denied`. No fifth verdict is added. | A flag row renders **denied** today, and AC 4 forbids a misleading label. `!= "flag"` is the same D6 rule as the SQL: `NULL` and `'block'` stay denied, so every pre-PRD row keeps its verdict. A new "flagged" verdict would touch `VERDICTS`, `rx.match` arms (`register.py:192`, `227`, `659`), the filter, `theme` inks and the legend. That is a layout and vocabulary change the story rules out ("no new view, no layout change"). **Flagged for review**: the story text names only the two fields, not the verdict. |
| D-D | **Two `AuditRow` strings, filled through `_text`.** `pattern_role: str = ""` and `pattern_action: str = ""` are placed after `suspicious_pattern`. The values are raw: `user`, `tool`, `block`, `flag`. A legacy row (both NULL) shows `VALUE_ABSENT` on both lines, and NULL is **not** rendered as "block". | This follows the module rule that absence is stated at the boundary (`register.py:416-422`). An inferred "block" would be a claim the column does not hold. The legacy row's **denied** verdict already states the block, so nothing is lost and nothing is invented. That is AC 4's "without an error or a misleading label". |
| D-E | **Disclosure placement.** Two `_detail_field` lines go directly after `DETAIL_PATTERN_LABEL`: `DETAIL_PATTERN_ROLE_LABEL = "Matched in"` and `DETAIL_PATTERN_ACTION_LABEL = "Pattern action"`. They go in `admin_copy.py` beside `DETAIL_PATTERN_LABEL`. | They qualify the pattern, so they sit under it. The existing ordering test (error < pattern < hash) still holds. They are disclosure-only, like `suspicious_pattern` (`register.py:478-482`), so `_row_line` is untouched. |
| D-F | **Only additive changes to pre-existing tests**, each with a `# PRD-011 D6` comment. These are the key-set pins (`test_audit_router.py:75-90`, `test_admin_models.py:21-38`, `test_copy.py:~449`, `test_register.py:78-90/121-136`), and the hand-built `_Log` in `test_register.py:~598` gains `pattern_role = None` and `pattern_action = None`, because `to_audit_row` now reads them. No existing assertion value changes. | Story AC 5 and PRD Section 11: "Every modified pre-existing test carries a comment citing PRD-011 and its decision". `test_integration.py:184,194` (`blocked_suspicious == 1`) and `test_reporting_invariance.py:79` remain true, because they contain only block rows and legacy rows. |

---

## Patterns to Follow

### Naming / the counter being narrowed
```python
# SOURCE: app/db/database.py:930-935
def count_blocked_suspicious() -> int:
    with _session() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_logs WHERE suspicious_pattern IS NOT NULL"
        ).fetchone()
        return row["n"]
```

### The snapshot's twin predicate
```sql
-- SOURCE: app/db/database.py:1212-1213 (_SUMMARY_SQL)
       (SELECT COUNT(*) FROM audit_logs WHERE suspicious_pattern IS NOT NULL)
           AS blocked_suspicious,
```

### The D6 predicate already in the codebase (STORY-009's D-E, its inverse)
```sql
-- SOURCE: app/db/database.py:832 (find_duplicate_timestamp)
AND (pattern_action IS NULL OR pattern_action <> 'flag')
```

### Read-model field with a stated reason for Optional
```python
# SOURCE: app/models/schemas.py:144-163
    # Optional and defaulted because `None` is the honest answer for two whole
    # classes of row: everything written before this PRD, ...
    session_id: Optional[str] = None
```

### Verbatim passthrough in the router
```python
# SOURCE: app/routers/admin.py:41-46
            # A verbatim passthrough (PRD-008 STORY-011). `list_audit_logs`
            # builds its rows through `_row_to_audit_log`, which has mapped
            # this column since STORY-008 -- the value was already in hand
            # here and merely went unprojected.
            session_id=log.session_id,
```

### Console: absence at the boundary
```python
# SOURCE: chat_ui/chat_ui/admin_formatting.py:126-130, 213
def _text(value: Optional[object]) -> str:
    """A NULL column reads as the absent mark, so the row field stays a plain str."""
    if value is None or value == "":
        return VALUE_ABSENT
    return str(value)
...
        suspicious_pattern=_text(log.suspicious_pattern),
```

### Console: disclosure lines
```python
# SOURCE: chat_ui/chat_ui/components/register.py:432-434
            _detail_field(admin_copy.DETAIL_ERROR_LABEL, row.error_message),
            _detail_field(admin_copy.DETAIL_PATTERN_LABEL, row.suspicious_pattern),
            _detail_field(admin_copy.DETAIL_PROMPT_HASH_LABEL, row.prompt_hash),
```

### Error handling
There is no new error path. Both columns are nullable reads. The console's rule is that no figure or field may raise into a page render (`admin_formatting.py:97-99`), and `_text` covers it.

### Tests: seeding rows directly
```python
# SOURCE: tests/test_db.py:1002-1028
def test_count_blocked_suspicious_counts_only_flagged_rows(temp_db):
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-01T10:00:00Z",
            user_id="a",
            prompt_hash="h1",
            suspicious_pattern="override",
        )
    )
    ...
    assert count_blocked_suspicious() == 2
```

### Tests: /audit key-set pin (equality, extended additively)
```python
# SOURCE: tests/test_audit_router.py:74-95
    for entry in body["queries"]:
        assert set(entry.keys()) == {
            "audit_id", ..., "session_id",
        }
    newest, oldest = body["queries"]
    assert oldest["suspicious_pattern_detected"] is True
```

### Tests: console formatting
```python
# SOURCE: tests/test_admin_formatting.py:41-65
def make_log(**overrides) -> AuditLog: ...
    assert derive_verdict(make_log(suspicious_pattern="ignore_instructions")) == VERDICT_DENIED
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/database.py` | UPDATE | `_BLOCKED_SUSPICIOUS_WHERE` constant; narrow `count_blocked_suspicious` and `_SUMMARY_SQL`'s `blocked_suspicious` |
| `app/models/schemas.py` | UPDATE | `AuditQueryEntry.pattern_role`, `.pattern_action` |
| `app/routers/admin.py` | UPDATE | Pass both through in `get_audit` |
| `chat_ui/chat_ui/admin_models.py` | UPDATE | `AuditRow.pattern_role`, `.pattern_action` |
| `chat_ui/chat_ui/admin_formatting.py` | UPDATE | `derive_verdict` narrowed (D-C); `to_audit_row` fills both fields |
| `chat_ui/chat_ui/admin_copy.py` | UPDATE | `DETAIL_PATTERN_ROLE_LABEL`, `DETAIL_PATTERN_ACTION_LABEL` |
| `chat_ui/chat_ui/components/register.py` | UPDATE | Two `_detail_field` lines; docstrings mention them |
| `tests/test_db.py` | UPDATE | Block/flag/legacy counter test; snapshot counter test; snapshot JSON field test |
| `tests/test_stats_router.py` | UPDATE | `/stats` block/flag/legacy test |
| `tests/test_audit_router.py` | UPDATE | Key-set pin extended; new role/action passthrough test |
| `tests/test_admin_formatting.py` | UPDATE | Verdict tests for flag/block/legacy; `to_audit_row` fields; NULL → absent |
| `tests/test_admin_state.py` | UPDATE | A snapshot row with a flag renders **cleared**, not denied |
| `tests/test_admin_models.py` | UPDATE | `AUDIT_ROW_FIELDS` + 2 (PRD-011 D6 comment) |
| `tests/test_copy.py` | UPDATE | Constant registry + 2 (PRD-011 D6 comment) |
| `tests/test_register.py` | UPDATE | Label/field tuples + 2; `_Log` + 2 attributes; ordering test extended |

---

## Tasks

Execute in order. Each task is atomic and verifiable. Mass fixture errors against the libSQL dev server mean restart `harness-libsql-dev`, not bisect the code.

### Task 1: Narrow the two counters

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  - Above `count_blocked_suspicious` (~line 928), add `_BLOCKED_SUSPICIOUS_WHERE` (D-A). Its comment should say: PRD-011 D6; a flag row is not a block; NULL is a pre-PRD row, which was a block; not backfilled; the same text is shared with `_SUMMARY_SQL`.
  - Replace the literal in `count_blocked_suspicious` with `f"SELECT COUNT(*) AS n FROM audit_logs WHERE {_BLOCKED_SUSPICIOUS_WHERE}"`.
  - In `_SUMMARY_SQL` (1212-1213), use the same constant in the subquery. `_SUMMARY_SQL` is defined after the function, so the constant is already in scope. If `_SUMMARY_SQL` is a plain string, convert it to an f-string. Check first for literal `{` or `}` in the SQL: `json_object` uses none, but verify, and double any braces you find.
  - `grep -rn "suspicious_pattern IS NOT NULL" app/` must then return only the constant.
- **Mirror**: `app/db/database.py:832`: the D6 predicate style STORY-009 used.
- **Validate**: `pytest tests/test_db.py -k "blocked_suspicious or summary" -q`. The existing tests stay green unchanged.

### Task 2: Counter tests (AC 1, AC 2, AC 5)

- **File**: `tests/test_db.py`
- **Action**: UPDATE (additive)
- **Implement**: Add a helper `_seed_block_flag_and_legacy()` that inserts three `AuditLog` rows through `insert_audit_log`:
  - a block row: `suspicious_pattern="ignore previous instructions", pattern_role="user", pattern_action="block"`;
  - a flag row: `suspicious_pattern="ignore previous instructions", pattern_role="tool", pattern_action="flag", success=True`;
  - a legacy row: `suspicious_pattern="override"`, both fields left None.

  Tests:
  - `test_count_blocked_suspicious_excludes_flags_and_keeps_legacy_rows`: the count is `2`. Its docstring cites PRD-011 D6 and Risk 4, and says why the predicate is not simply `= 'block'`, as the story's Technical Notes ask.
  - `test_summary_snapshot_blocked_suspicious_excludes_flags_and_keeps_legacy_rows`: `summary_snapshot().blocked_suspicious == 2`.
  - `test_summary_snapshot_rows_carry_pattern_role_and_action`: rows are read back as `(pattern_role, pattern_action)`, including `(None, None)` for the legacy row. This is AC 5's "both new fields appear in the per-row object". Also assert that the raw JSON object from `_SUMMARY_SQL` has both keys. Execute `_SUMMARY_SQL` directly and `json.loads` the rows column, following `test_pattern_role_and_action_survive_the_batched_read` (~2303) for how the snapshot is read.
  - `test_blocked_suspicious_predicate_is_shared`: `_BLOCKED_SUSPICIOUS_WHERE in _SUMMARY_SQL`, and the constant's text equals the PRD's predicate exactly (AC 1).
- **Mirror**: `tests/test_db.py:1002-1028` and `2303`.
- **Validate**: `pytest tests/test_db.py -q`. Mutation check: revert Task 1's constant to `suspicious_pattern IS NOT NULL`, and the new tests must fail. Then restore.

### Task 3: `/stats` test (AC 2)

- **File**: `tests/test_stats_router.py`
- **Action**: UPDATE (additive)
- **Implement**: `test_stats_blocked_suspicious_counts_blocks_and_legacy_rows_not_flags`. Seed the same three rows (a local seeding, matching the file's style at 72-135), call `GET /stats` with the admin bearer, and assert `blocked_suspicious == 2` and `total_queries == 3`. Existing tests are unchanged: their `override` row has no action, which is legacy, so it still counts as 1.
- **Mirror**: `tests/test_stats_router.py:72-135`.
- **Validate**: `pytest tests/test_stats_router.py -q`

### Task 4: `AuditQueryEntry` and `get_audit` (AC 3)

- **Files**: `app/models/schemas.py`, `app/routers/admin.py`
- **Action**: UPDATE
- **Implement**:
  - In `schemas.py`, after `session_id`, add `pattern_role: Optional[str] = None` and `pattern_action: Optional[str] = None`. The comment says:
    - PRD-011 D6;
    - `pattern_role` is the role of the message the hit was in;
    - `pattern_action` is `block` or `flag`, and NULL on pre-PRD rows, which were blocks;
    - `suspicious_pattern_detected` keeps "a pattern was matched" and is true for a flag too; `pattern_action` is the field that separates the two cases;
    - there is no validator, for the same read-model reason as `session_id`.
  - In `admin.py`'s `get_audit`, add `pattern_role=log.pattern_role, pattern_action=log.pattern_action,` next to `suspicious_pattern_detected`, with a one-line verbatim-passthrough comment. Leave `suspicious_pattern_detected=log.suspicious_pattern is not None` untouched.
- **Mirror**: `app/models/schemas.py:144-163`, `app/routers/admin.py:41-46`.
- **Validate**: `python -c "from app.main import app"`

### Task 5: `/audit` tests (AC 3)

- **File**: `tests/test_audit_router.py`
- **Action**: UPDATE
- **Implement**:
  - Extend the key-set pin at 75-90 with `"pattern_role"` and `"pattern_action"`, commented `# PRD-011 D6: two additive, nullable fields`.
  - New test `test_audit_entry_carries_pattern_role_and_action`: seed a block row, a flag row and a legacy row, then assert per entry:

    | Row | `pattern_role` | `pattern_action` | `suspicious_pattern_detected` |
    |---|---|---|---|
    | block | `"user"` | `"block"` | `True` |
    | flag | `"tool"` | `"flag"` | `True` (**not narrowed**) |
    | legacy | `None` | `None` | `True` |

    A clean row has `None`, `None`, `False`.
  - `grep -rn "suspicious_pattern_detected" tests/`. Any other key-set pin, such as in `test_audit_session_id.py`, must still pass. `test_reporting_invariance.py:555` compares against `AuditQueryEntry.model_fields` and follows automatically.
- **Mirror**: `tests/test_audit_router.py:40-96`.
- **Validate**: `pytest tests/test_audit_router.py tests/test_audit_session_id.py tests/test_reporting_invariance.py -q`

### Task 6: Console row model, copy and formatting (AC 4)

- **Files**: `chat_ui/chat_ui/admin_models.py`, `chat_ui/chat_ui/admin_copy.py`, `chat_ui/chat_ui/admin_formatting.py`
- **Action**: UPDATE
- **Implement**:
  - `AuditRow`: after `suspicious_pattern`, add `pattern_role: str = ""` and `pattern_action: str = ""`. Comment: disclosure-only; PRD-011 D6.
  - `admin_copy.py`: after `DETAIL_PATTERN_LABEL`, add `DETAIL_PATTERN_ROLE_LABEL = "Matched in"` and `DETAIL_PATTERN_ACTION_LABEL = "Pattern action"`. The comment says the values are the audit's own words (`user`/`tool`, `block`/`flag`), shown as recorded, and that a pre-PRD row shows the absent mark rather than an inferred "block".
  - `admin_formatting.py`:
    - update the precedence comment at 33-39;
    - narrow `derive_verdict`'s denied arm (D-C), with a comment citing PRD-011 D6 that says a flag row falls through to **cleared** because the request passed the check and continued;
    - in `to_audit_row`, add `pattern_role=_text(log.pattern_role)` and `pattern_action=_text(log.pattern_action)`.
- **Mirror**: `chat_ui/chat_ui/admin_formatting.py:84-89`, `213`; `chat_ui/chat_ui/admin_copy.py:266-270`.
- **Validate**: `python -c "import chat_ui.chat_ui.admin_formatting"`, or run it from `chat_ui/` as the existing tests import it.

### Task 7: Register disclosure (AC 4)

- **File**: `chat_ui/chat_ui/components/register.py`
- **Action**: UPDATE
- **Implement**:
  - In `_detail` (~433), right after the pattern line, add `_detail_field(admin_copy.DETAIL_PATTERN_ROLE_LABEL, row.pattern_role)` and `_detail_field(admin_copy.DETAIL_PATTERN_ACTION_LABEL, row.pattern_action)`.
  - Update `_detail`'s docstring: the string fields that `_text` pre-fills now include the two new ones.
  - Update `_row_line`'s docstring list of disclosure-only fields.
  - The grid, the row and the verdict arms are unchanged.
- **Mirror**: `chat_ui/chat_ui/components/register.py:432-434`.
- **Validate**: `pytest tests/test_register.py tests/test_render_invariants.py -q`. This will fail until Task 8 updates the pins.

### Task 8: Console tests (AC 4, AC 5)

- **Files**: `tests/test_admin_formatting.py`, `tests/test_admin_models.py`, `tests/test_copy.py`, `tests/test_register.py`, `tests/test_admin_state.py`
- **Action**: UPDATE (every pre-existing edit is additive and commented `# PRD-011 D6`)
- **Implement**:
  - `test_admin_formatting.py`:
    - `test_a_flag_row_is_not_denied`: `make_log(suspicious_pattern="x", pattern_action="flag", pattern_role="tool")` gives `VERDICT_CLEARED`.
    - `test_a_block_row_is_denied`: gives `VERDICT_DENIED`.
    - `test_a_legacy_pattern_row_is_still_denied`: `pattern_action=None` gives `VERDICT_DENIED`.
    - `test_a_duplicate_still_outranks_a_flag`: gives `VERDICT_HELD`.
    - `test_to_audit_row_carries_pattern_role_and_action`: the raw values come through.
    - Extend `test_null_columns_render_the_absent_mark` (172-192) so `row.pattern_role == row.pattern_action == VALUE_ABSENT`, commented.
  - `test_admin_models.py`: add both names to `AUDIT_ROW_FIELDS`.
  - `test_copy.py`: add both constants to the import (~145), the non-empty check (~346) and the registry set (~449).
  - `test_register.py`:
    - add both label names to the list at 78-90, `DETAIL_LABELS` (121) and `DETAIL_ROW_FIELDS` (134);
    - add `pattern_role = None` and `pattern_action = None` to `_Log` (~598);
    - add `test_the_role_and_action_follow_the_pattern`: pattern label index < role label index < action label index < hash label index.
  - `test_admin_state.py`: add `test_a_flag_row_renders_cleared_with_its_role_and_action`. Using the `_Reads` stub (420-518), feed one flag `AuditLog`, load the record, and assert:
    - the row's verdict is `cleared`;
    - `pattern_role == "tool"` and `pattern_action == "flag"`;
    - `state.blocked_suspicious` equals the stubbed count. That count is the database's number, and the state does not recompute it.
- **Mirror**: `tests/test_admin_formatting.py:60-90, 172-192`; `tests/test_admin_state.py:521-603`; `tests/test_register.py:638-670`.
- **Validate**: `pytest tests/test_admin_formatting.py tests/test_admin_models.py tests/test_copy.py tests/test_register.py tests/test_render_invariants.py tests/test_admin_state.py -q`

### Task 9: Repository sweep

- **Implement**:
  - `grep -rn "suspicious_pattern IS NOT NULL" app/ chat_ui/`: only the constant should remain.
  - `grep -rn "suspicious_pattern is not None" app/ chat_ui/`: expect exactly `admin.py` (`suspicious_pattern_detected`, deliberately kept) and `derive_verdict` (narrowed).
  - Confirm `git diff` is empty for `tests/test_integration.py`, `tests/test_query_router.py`, `tests/test_query_outcomes_regression.py`, `tests/test_chat_outcomes_regression.py` and `tests/test_history_off_integration.py`.
  - Update the comment at `app/db/models.py:68-70`, which says the counters read NULL as a block "as of STORY-010", only if its wording now needs a tense change.
- **Validate**: grep output recorded in the report.

### Task 10: Full suite

- **Validate**: `pytest tests/ -q`. Everything must be green. If mass fixture errors appear, restart the `harness-libsql-dev` container and re-run; do not bisect.

---

## End-to-End Tests

Run against the local libSQL dev server (`DATABASE_URL=http://127.0.0.1:8080`), never the `.env` database. Serve with `uvicorn app.main:app --port 8765`.

- [ ] Seed one row of each kind directly through `insert_audit_log`: block (`user`/`block`), flag (`tool`/`flag`), legacy (pattern, both NULL), and clean.
- [ ] `GET /stats` → `blocked_suspicious: 2`
- [ ] `GET /audit` → each entry has both new keys. The flag entry is `pattern_role:"tool", pattern_action:"flag", suspicious_pattern_detected:true`; the legacy entry is `null`, `null`, `true`; the clean entry is `null`, `null`, `false`.
- [ ] `summary_snapshot()` from a Python shell: `blocked_suspicious == 2`, and `rows` carry the four `(role, action)` pairs.
- [ ] `POST /query` with `please ignore previous instructions` → the body is byte-identical to today's. `/stats` `blocked_suspicious` becomes 3, and the new `/audit` entry is `user`/`block`.
- [ ] Admin console (Reflex, `chat_ui`), Register view:
  - the flag row shows verdict **cleared**, and its disclosure shows "Matched in: tool" and "Pattern action: flag";
  - the block row shows **denied** with `user`/`block`;
  - the legacy row shows **denied** with `—`/`—` and no console or server error;
  - the summary's blocked-suspicious figure reads 3.

---

## Validation

```bash
python -c "from app.main import app"
pytest tests/test_db.py tests/test_stats_router.py tests/test_audit_router.py -q
pytest tests/test_admin_formatting.py tests/test_admin_models.py tests/test_copy.py tests/test_register.py tests/test_render_invariants.py tests/test_admin_state.py -q
pytest tests/ -q
```

There is no `frontend/` directory, so there is no npm lint. The Reflex console is covered by the Python suites above.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Converting `_SUMMARY_SQL` to an f-string breaks on literal braces | Check for `{`/`}` first. Otherwise concatenate the constant rather than use an f-string. The existing summary tests cover the result. |
| D-C changes a verdict the story did not name | Only flag rows move, and no production path writes them until PRD-016. NULL and `block` keep **denied**. Flagged for review in the output. |
| Hand-built `AuditLog` stand-ins elsewhere lack the new attributes | `grep -rn "class _Log" tests/`. Each one that reaches `to_audit_row`/`derive_verdict` gains two `None` attributes with a PRD-011 D6 comment. |
| libSQL dev-server flakes on the full run | Restart the container per the known note, and record flakes in the report as STORY-009 did. |

---

## Acceptance Criteria

(Copied from story `STORY-010`)

- [ ] Given `count_blocked_suspicious()` and the admin snapshot query in `app/db/database.py`, when they run, then both predicates are `suspicious_pattern IS NOT NULL AND (pattern_action IS NULL OR pattern_action = 'block')`.
- [ ] Given one block row, one flag row and one legacy row with `pattern_action IS NULL`, when `/stats` and the admin snapshot are read, then `blocked_suspicious` is 2: the flag is excluded and the legacy row still counts.
- [ ] Given `AuditQueryEntry` in `app/models/schemas.py` and the mapping in `app/routers/admin.py`, when `GET /audit` is read, then each entry carries nullable `pattern_role` and `pattern_action` alongside the existing `suspicious_pattern_detected`, which keeps its current meaning of "a pattern was matched" and is therefore true for a flag too.
- [ ] Given the admin console's Register view, when a row with a pattern is rendered, then the triggering role and whether it was a block or a flag are visible, and a row from before this PRD (both fields NULL) renders without an error or a misleading label.
- [ ] Given the snapshot JSON built in `app/db/database.py`, when it is read, then both new fields appear in the per-row object, and the existing reports/admin tests pass with only additive changes.
- [ ] All tasks completed
- [ ] Full `pytest tests/` green
- [ ] Backend starts without error
- [ ] Every modified pre-existing test carries a PRD-011 D6 comment; no assertion changed in `test_query_router.py`, `test_integration.py` or `test_query_outcomes_regression.py`
- [ ] Follows existing patterns (one D6 predicate text; verbatim passthrough; absence stated at the boundary)
