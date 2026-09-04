---
story: STORY-008
prd: PRD-008
slug: audit-log-session-id
title: "session_id on AuditLog, log_query and insert_audit_log"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-04
---

# Plan: session_id on AuditLog, log_query and insert_audit_log

## Summary

The column and the field already exist — STORY-002 declared `session_id` in `AUDIT_LOGS_ADDED_COLUMNS` and in `CREATE_AUDIT_LOGS_TABLE`, STORY-003 converged it, and `AuditLog` carries the field with a comment saying the write and read paths learn about it in STORY-008. This story is that wiring, and nothing else: `log_query` gains a keyword-defaulted `session_id: Optional[str] = None` in last position and passes it onto the `AuditLog` it constructs; `insert_audit_log` adds the column to its INSERT list and the value to its tuple; `_row_to_audit_log` adds one `row["session_id"]` read. Because `_row_to_audit_log` deliberately serves **two** row shapes — the `_Row` off `SELECT *` and the plain `dict` decoded out of `_SUMMARY_SQL`'s hand-written `json_object(...)` — the batched read's column list must gain `'session_id', session_id` in the same edit, or the mapper raises on every `summary_snapshot()` call. That is the mapper's existing contract, not a widening of scope: no figure gains a session dimension, no `WHERE` clause changes, no counter moves. Tests follow the present/absent pair that `role` and `denied_permission` established in both suites.

## User Story

As a compliance admin
I want an audit row to be able to name the conversation it came from
So that a report about "that chat" resolves to a set of rows rather than a guess.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-008-audit-log-session-id.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md` — Section 4 (Pipeline & API), Section 5 (story 8), Section 12 Phase 2

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | `app/services/audit_logger.py`, `app/db/database.py` (write path, row mapper, batched read SQL), `tests/` |
| Story | STORY-008 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |

**Dependencies verified**: STORY-003 is `status: done` (commit `e42eed9`). Nothing blocks this story. It blocks STORY-009 (threading through `run_query`) and STORY-011 (`AuditQueryEntry`) — neither is touched here.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` was listed and holds exactly one skill, `frontend-design`, whose `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one". This story touches `app/services/` and `app/db/` only, renders nothing, and adds no string a user reads. | None |

The story's frontmatter has `skills: []` and its Technical Notes reach the same conclusion; the scan was re-run against `.agents/skills/` rather than inherited. `chat_ui/AGENTS.md`'s **reflex-docs** rule is likewise not engaged — no file under `chat_ui/` is opened.

---

## Patterns to Follow

### Naming — the optional-column parameter, keyword-defaulted, appended last

```python
# SOURCE: app/services/audit_logger.py:12-27
def log_query(
    user_id: str,
    prompt: str,
    device: Optional[str] = None,
    ...
    role: Optional[str] = None,
    denied_permission: Optional[str] = None,
) -> int:
```

`role` and `denied_permission` are the precedent PRD-005 set for exactly this shape of change: appended after everything before them, `Optional[X] = None`, no call site edited. `session_id` follows them.

### Write path — column list, placeholder count and value tuple move together

```python
# SOURCE: app/db/database.py:548-581
def insert_audit_log(entry: AuditLog) -> int:
    with _session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO audit_logs (
                ...
                role, denied_permission
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ...
                entry.role,
                entry.denied_permission,
            ),
        )
        return cursor.lastrowid
```

Three edits, one unit: the name into the column list, one `?` into VALUES (18 → 19), one `entry.session_id` at the end of the tuple. A miscount shifts every later column.

### Read path — one mapper, two row shapes

```python
# SOURCE: app/db/database.py:598-631
def _row_to_audit_log(row: Mapping[str, Any]) -> AuditLog:
    """Map one audit row onto `AuditLog`, by column name.

    Annotated as a `Mapping`, not `_Row`, because it takes both: `_Row` for a
    row off the wire, and the plain `dict` `summary_snapshot()` decodes out of
    `json_object(...)` (STORY-010). ...
    """
    return AuditLog(
        ...
        role=row["role"],
        denied_permission=row["denied_permission"],
    )
```

```sql
-- SOURCE: app/db/database.py:936-956 (_SUMMARY_SQL)
  (SELECT json_group_array(json_object(
              'id', id,
              ...
              'role', role,
              'denied_permission', denied_permission))
     FROM (SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?)
  ) AS "rows",
```

The batched read enumerates its columns by hand; the standalone reads are `SELECT *`. Any key the mapper reads must exist in **both** shapes. `_Row.__getitem__` raises `IndexError` on an unknown name (`app/db/database.py:94-101`) and the JSON path's `dict` raises `KeyError` — loud, but `summary_snapshot()`'s per-figure isolation would turn it into a permanently broken `rows` figure on the admin console rather than a crash.

### Tests — the present/absent pair

```python
# SOURCE: tests/test_audit_logger.py:196-234
def test_role_and_denied_permission_persisted_when_supplied(temp_db):
    audit_id = log_query(..., role="user", denied_permission="query:byok")
    fetched = get_audit_log(audit_id)
    assert fetched.role == "user"


def test_role_and_denied_permission_default_to_none_when_omitted(temp_db):
    audit_id = log_query(user_id="juan@empresa.com", prompt="hello", response="hi there")
    fetched = get_audit_log(audit_id)
    assert fetched.role is None
```

```python
# SOURCE: tests/test_db.py:485-521
def test_role_and_denied_permission_round_trip(temp_db):
    ...
    # And via list_audit_logs, the other read path (AuditQueryEntry's future source).
    entries = list_audit_logs()
    assert entries[0].role == "user"
```

Both suites take `temp_db` (`tests/conftest.py:171-178`), which runs `init_db()` against an isolated database — so the `session_id` column is present without any test hand-rolling a schema.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/database.py` | UPDATE | `insert_audit_log` writes the column; `_row_to_audit_log` reads it; `_SUMMARY_SQL`'s `json_object` carries it so the shared mapper keeps working on both shapes; the `_Row` docstring's "19 named reads" becomes 20 |
| `app/services/audit_logger.py` | UPDATE | `log_query` accepts `session_id` and forwards it to the `AuditLog` it builds |
| `app/db/models.py` | UPDATE | Comment only — the `session_id` field comment currently says the paths do *not* know about it "until STORY-008"; that sentence stops being true here |
| `tests/test_db.py` | UPDATE | Present/absent pair through `insert_audit_log`; a parity assertion across the two read shapes |
| `tests/test_audit_logger.py` | UPDATE | Present/absent pair through `log_query` → `get_audit_log` |

Explicitly **not** touched: `app/services/query_pipeline.py` (its seven `log_query` call sites are STORY-009), `app/models/schemas.py` (`QueryRequest` is STORY-009, `AuditQueryEntry` is STORY-011, `StatsResponse` gains nothing in this PRD), `app/routers/`, `chat_ui/`, and the two column declarations in `app/db/models.py`, which STORY-002 already landed.

---

## Dependency Order

1. Write path (`insert_audit_log`) — the column has to be written before a round trip proves anything.
2. Read paths (`_row_to_audit_log` + `_SUMMARY_SQL`) — one edit, because the mapper serves both.
3. `log_query` — the store's caller.
4. Tests, then the full suite.

---

## Risks + Mitigations

| # | Risk | Mitigation |
|---|------|------------|
| 1 | Adding `row["session_id"]` to the mapper without adding it to `_SUMMARY_SQL` breaks the batched read that shares that mapper. | Task 2 does both in one edit. `test_summary_snapshot_agrees_with_the_individual_reads` (`tests/test_db.py:1094`) compares `snapshot.rows` against `list_audit_logs()` as whole `AuditLog` objects and is the existing test that catches it; Task 2's validation runs it before anything else. |
| 2 | Positional drift in `insert_audit_log`'s column list / `?` count / value tuple. | Task 1 states all three edits as one unit; Task 4's round-trip test reads back `prompt_hash`, `role` and `denied_permission` alongside `session_id`, so a shift surfaces as a wrong neighbour, not just a missing value. |
| 3 | Scope creep into `run_query`. | The seven call sites at `app/services/query_pipeline.py:34,72,86,101,115,128,144` stay untouched; Tasks 3 and 7 assert the diff names no file outside the five listed above. |
| 4 | A counter or list query quietly gaining a session filter. | No `WHERE` clause is edited anywhere in this story; AC 7 is covered by the existing `test_db.py` audit and summary tests running unmodified. |
| 5 | A degraded libSQL dev server read as a code regression. | If a run shows mass fixture errors, restart the libSQL dev container before bisecting — that degradation is environmental. |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: `insert_audit_log` writes `session_id`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: In `insert_audit_log` (line 548), three aligned additions: `session_id` at the end of the INSERT column list (after `denied_permission`), one more `?` in the VALUES list (18 → 19), and `entry.session_id,` as the last element of the parameter tuple.
- **Mirror**: `app/db/database.py:548-581` — the shape `denied_permission` already occupies.
- **Do not**: reorder or reflow any existing column; the diff should read as three token additions.
- **Validate**: `pytest tests/test_db.py -k "audit" -q` → green (every existing insert still works against the widened statement).

### Task 2: `_row_to_audit_log` reads `session_id`, and `_SUMMARY_SQL` carries it

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: Two edits, made together.
  1. In `_row_to_audit_log` (line 598), add `session_id=row["session_id"],` after `denied_permission=row["denied_permission"],`. No coercion — the column is nullable `TEXT`, so the value arrives as `str` or `None` on both shapes, unlike the INTEGER columns the `bool(...)` calls exist for.
  2. In `_SUMMARY_SQL` (line 924), add `'session_id', session_id` to the `json_object(...)` list after `'denied_permission', denied_permission`, keeping the closing `))` where it is.
  Then update the `_Row` docstring at `app/db/database.py:80` — "19 named reads" becomes 20.
- **Mirror**: `app/db/database.py:611-631` and `app/db/database.py:936-956`.
- **Why both**: the mapper's docstring records that a second mapper for the batched path is how the two would drift; the reciprocal is that a key added to one input shape has to be added to the other.
- **Validate**: `pytest tests/test_db.py -k "summary_snapshot" -q` → green, in particular `test_summary_snapshot_agrees_with_the_individual_reads` and `test_summary_snapshot_types_match_the_standalone_functions`.

### Task 3: `log_query` accepts and forwards `session_id`

- **File**: `app/services/audit_logger.py`
- **Action**: UPDATE
- **Implement**: Add `session_id: Optional[str] = None` as the **last** parameter of `log_query`, after `denied_permission`, and pass `session_id=session_id` into the `AuditLog(...)` construction after `denied_permission=denied_permission`. Nothing else: no validation and no UUID4 check — that is STORY-009's `QueryRequest` validator and STORY-010's 403 — and no value derived from anything.
- **Mirror**: `app/services/audit_logger.py:25-26` and `:47-48`.
- **Guard**: every existing call site — the seven in `app/services/query_pipeline.py` and the twelve in `tests/test_audit_logger.py` — passes keywords only and must remain byte-identical.
- **Validate**: `python -c "import inspect; from app.services.audit_logger import log_query; p = list(inspect.signature(log_query).parameters.values()); print(p[-1].name, p[-1].default)"` prints `session_id None`; `git diff --stat -- app/services/query_pipeline.py` is empty.

### Task 4: the model comment stops promising the opposite

- **File**: `app/db/models.py`
- **Action**: UPDATE
- **Implement**: The comment at `app/db/models.py:179-182` reads "insert_audit_log() and _row_to_audit_log() learn about it in STORY-008, so until then a read leaves this None whatever the column holds." That is now false. Replace the second sentence with one saying both paths carry it as of STORY-008. Comment only — the field, its type, its default and its position before `id` are unchanged, which is what `test_audit_log_carries_session_id_without_breaking_construction` (`tests/test_db.py:1553`) pins.
- **Validate**: `pytest tests/test_db.py -k "session_id" -q` → green; `git diff -- app/db/models.py` shows comment lines only.

### Task 5: store-level tests

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: Add three tests immediately after `test_role_and_denied_permission_round_trip` (ends line 521), keeping the audit-row block contiguous:
  - `test_session_id_defaults_to_none_when_not_supplied(temp_db)` — insert a minimal `AuditLog(timestamp=..., user_id="a", prompt_hash="h5")`, read back with `get_audit_log`, assert `session_id is None`. AC 4 at the store level.
  - `test_session_id_round_trips(temp_db)` — insert with `session_id="0f6c2e5a-9b3d-4c81-a7f2-1d5e8c9b0a34"`, assert `get_audit_log(...).session_id` equals it, then assert `list_audit_logs()[0].session_id` equals it too, carrying the same kind of trailing comment the `role` test uses about the second read path.
  - `test_session_id_survives_the_batched_read(temp_db)` — insert one row with a `session_id` and one without, call `summary_snapshot()`, assert `snapshot.errors == {}` and `snapshot.rows == list_audit_logs()` element for element. This pins Risk 1 as a test rather than a note, and is the only new assertion that mentions `summary_snapshot`.
- **Mirror**: `tests/test_db.py:485-521` for the pair; `tests/test_db.py:1094-1109` for how the two read paths are compared.
- **Do not**: modify `_seed_summary_fixture`, any existing assertion, or anything above line 485.
- **Validate**: `pytest tests/test_db.py -k "session_id" -q` → green; `git diff -- tests/test_db.py | grep "^-" | grep -v "^---"` prints nothing (additions only — AC 6).

### Task 6: service-level tests

- **File**: `tests/test_audit_logger.py`
- **Action**: UPDATE
- **Implement**: Append two tests after `test_role_and_denied_permission_default_to_none_when_omitted` (ends line 234):
  - `test_session_id_persisted_when_supplied(temp_db)` — `log_query(user_id="ana@empresa.com", prompt="hello", response="hi there", session_id="0f6c2e5a-9b3d-4c81-a7f2-1d5e8c9b0a34")`, then `get_audit_log(audit_id).session_id` equals it. AC 5.
  - `test_session_id_defaults_to_none_when_omitted(temp_db)` — a `log_query` call with today's arguments only, asserting `session_id is None`. AC 4.
- **Mirror**: `tests/test_audit_logger.py:196-234`, verbatim in shape.
- **Note**: `test_no_ip_or_location_field_in_logged_row` (line 99) iterates `vars(fetched)` and asserts no field name contains "ip" or "location". `session_id` passes and that test stays unmodified — which is AC 6 in action, not a coincidence worth editing around.
- **Validate**: `pytest tests/test_audit_logger.py -q` → all green; the diff on this file is additions only.

### Task 7: prove nothing else moved

- **File**: — (verification only)
- **Action**: RUN
- **Implement**: Run, in order:
  1. `pytest tests/test_audit_logger.py tests/test_db.py -q` — the two suites the story names.
  2. `pytest tests/test_query_pipeline_authorization.py tests/test_query_router.py tests/test_audit_router.py tests/test_rbac.py tests/test_integration.py -q` — the callers and the API surface, unmodified, showing the defaulted parameter cost them nothing.
  3. `pytest -q` — full suite.
- **On mass fixture errors**: restart the libSQL dev container before concluding anything about the code (Risk 5).
- **Validate**: `pytest -q` green.

### Task 8: commit on the epic branch

- **File**: — (git)
- **Action**: RUN
- **Implement**: Confirm the branch is `epic/PRD-008-chat-sessions` — no per-story branch. Stage only the five files this plan lists. Commit as `feat(audit): STORY-008 session_id on the audit write and read paths`, ending the message with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Validate**: `git status` clean; `git diff --stat HEAD~1` names only `app/db/database.py`, `app/db/models.py`, `app/services/audit_logger.py`, `tests/test_audit_logger.py`, `tests/test_db.py`.

---

## End-to-End Tests

- [ ] `log_query(user_id="ana@empresa.com", prompt="hello")` → `get_audit_log(id).session_id is None` — today's behaviour, unchanged
- [ ] `log_query(..., session_id="<uuid4>")` → `get_audit_log(id).session_id == "<uuid4>"`
- [ ] `list_audit_logs()` reports the same `session_id` on the same row as `get_audit_log`
- [ ] `summary_snapshot().rows == list_audit_logs()` on a mixed table (one row with a session, one without), with `errors == {}` — the two read shapes agree
- [ ] `count_audit_logs()`, `count_blocked_duplicates()` and every `summary_snapshot()` figure return exactly what they returned before, on the same fixture
- [ ] The seven `log_query` call sites in `app/services/query_pipeline.py` are untouched and the pipeline and router suites are green

---

## Validation

```bash
pytest tests/test_audit_logger.py -q
pytest tests/test_db.py -k "audit or session_id or summary_snapshot" -q
pytest -q
git diff --stat HEAD~1
python -c "import inspect; from app.services.audit_logger import log_query; print(list(inspect.signature(log_query).parameters)[-1])"
```

---

## Acceptance Criteria

(Copied from story `STORY-008`)

- [ ] Given `app/services/audit_logger.py`, when `log_query` is read, then it accepts `session_id: Optional[str] = None` and passes it onto the `AuditLog` it constructs.
- [ ] Given the new parameter, when the signature is inspected, then it is keyword-defaulted and positioned after the existing parameters, so every current call site keeps working untouched.
- [ ] Given `app/db/database.py`'s `insert_audit_log`, when it runs, then `session_id` is written, and `_row_to_audit_log` maps it back on every read.
- [ ] Given a `log_query(...)` call with no `session_id`, when the row is read back, then `session_id` is `NULL` — today's behaviour exactly, for every existing caller and every API client that omits the field.
- [ ] Given a `log_query(...)` call with a `session_id`, when `get_audit_log(audit_id)` retrieves the row, then the value round-trips unchanged.
- [ ] Given `tests/test_audit_logger.py` and `tests/test_db.py`, when the suite runs, then existing assertions pass **unmodified** and new ones cover both the present and absent cases.
- [ ] Given `list_audit_logs`, `count_audit_logs` and every stats counter, when they run, then their behaviour is unchanged — this story adds a column to the row, not a filter to any query.
- [ ] All tasks completed
- [ ] Full suite `pytest -q` green
- [ ] Follows existing patterns (`role` / `denied_permission`, PRD-005)
