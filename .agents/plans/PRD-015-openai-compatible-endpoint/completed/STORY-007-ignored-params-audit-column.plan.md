---
story: STORY-007
prd: PRD-015
slug: ignored-params-audit-column
title: "audit_logs.ignored_params: column, writer, every pipeline arm and the /audit field"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-015-openai-compatible-endpoint
created: 2026-10-23
---

# Plan: audit_logs.ignored_params: column, writer, every pipeline arm and the /audit field

## Summary

Add one nullable TEXT column, `audit_logs.ignored_params`, the same way PRD-013 STORY-002 added its eight: declared in `CREATE_AUDIT_LOGS_TABLE` and in `AUDIT_LOGS_ADDED_COLUMNS` (so `init_db()` converges old databases through the existing, data-driven `_add_missing_columns`), carried on the `AuditLog` dataclass, written by `insert_audit_log`, read back by `_row_to_audit_log` on both read shapes (the row path and `summary_snapshot()`'s `json_object` path). `log_query` gains a defaulted `ignored_params`; `_deny` gains it as a **required** parameter; `run_conversation` gains it keyword-only beside `ingress` and `streamed` and threads it to all fourteen sites (four `_deny` calls, ten direct `log_query` calls). `run_query`, `/query`'s foreign-session refusal and the chat UI pass nothing and keep writing NULL. `GET /audit` exposes it verbatim on `AuditQueryEntry`. The `/v1` router (STORY-009) is the first caller that will set a non-NULL value; this story only builds the path and proves every arm carries it.

## User Story

As a compliance admin
I want every `/v1` row to name the client parameters the harness did not forward
So that "what did the client ask for that it did not get" is answerable from the audit alone

## Story Reference

- Story file: `.agents/stories/PRD-015-openai-compatible-endpoint/STORY-007-ignored-params-audit-column.md`
- PRD: `.agents/PRDs/PRD-015-openai-compatible-endpoint/PRD.md` (Sections 4, 6.3, 7.3, 10, 15 D1/D3)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/db` (schema, writer, readers), `app/services/audit_logger.py`, `app/services/query_pipeline.py`, `app/models/schemas.py`, `app/routers/admin.py`, tests |
| Story | STORY-007 |
| PRD | PRD-015 |
| Epic Branch | `epic/PRD-015-openai-compatible-endpoint` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` holds only `frontend-design`; the story has no UI change and declares `skills: []`. | — |

---

## Patterns to Follow

### Additive column (schema + migration mapping)
```python
# SOURCE: app/db/models.py:29-37 (CREATE) and :92-97 (AUDIT_LOGS_ADDED_COLUMNS)
    profile TEXT,
    ingress TEXT,
    ...
    limit_exceeded TEXT
)
...
    # PRD-013 (Section 6.2): which door the request came through -- ...
    # Nullable with no default on purpose, like dedup_key: rows written before
    # PRD-013 stay NULL and are never backfilled, and so does a direct call
    # that passed none.
    "ingress": "TEXT",
```
`_add_missing_columns(conn, "audit_logs", AUDIT_LOGS_ADDED_COLUMNS)` (`app/db/database.py:719`, `:732`) iterates the mapping — **no code change in `database.py`'s migration path**, only the mapping entry.

### Dataclass field (keep `id` trailing)
```python
# SOURCE: app/db/models.py:384-398
    ingress: Optional[str] = None
    ...
    conversation_key: Optional[str] = None
    limit_exceeded: Optional[str] = None
    id: Optional[int] = None
```

### Writer default with the "never omitted in the pipeline" comment
```python
# SOURCE: app/services/audit_logger.py:35-43
    # PRD-012 STORY-011 (D9). Defaulted here but never omitted in the
    # pipeline: every row run_conversation writes passes it explicitly --
    # _deny requires it, and tests/test_query_pipeline_pii_profiles.py scans
    # every direct call site -- ...
    profile: Optional[str] = None,
```

### Required `_deny` parameter
```python
# SOURCE: app/services/query_pipeline.py:213-226
    # Required for the same reason as the three above (PRD-013 Section 6.9):
    # a forgotten arm is a TypeError, not a row that cannot say which door it
    # came through, ...
    ingress: Optional[Ingress],
    message_count: int,
    conversation_key: Optional[str],
    streamed: bool,
    exc: PermissionDenied,
```

### Keyword-only pipeline parameter
```python
# SOURCE: app/services/query_pipeline.py:255-270
    *,
    profile: Optional[str] = None,
    ...
    ingress: Optional[Ingress] = None,
    # Whether the response is delivered as SSE. Always False until PRD-014.
    streamed: bool = False,
) -> QueryPipelineResult:
```

### Read model field, unvalidated for `session_id`'s reasons
```python
# SOURCE: app/models/schemas.py:213-218
    # PRD-012 D9: the profile that ran ... Optional,
    # defaulted and unvalidated for `session_id`'s reasons: NULL on every row
    # written before PRD-012 and on /query's foreign-session refusal.
    profile: Optional[str] = None
```

### Verbatim passthrough on `/audit`
```python
# SOURCE: app/routers/admin.py:59-60
            # Verbatim passthrough (PRD-012 D9); NULL on pre-PRD-012 rows.
            profile=log.profile,
```

### Tests: per-arm via a wrapper around `_drive`, rows read back by id
```python
# SOURCE: tests/test_query_pipeline_audit_fields.py:119-140, 190-201
def _with_door(monkeypatch) -> None:
    real = query_pipeline.run_conversation
    def _run_conversation(*args, call_openrouter, **kwargs):
        ...
        return real(*args, call_openrouter=_split, ingress="v1", streamed=True, **kwargs)
    monkeypatch.setattr(query_pipeline, "run_conversation", _run_conversation)

@pytest.mark.parametrize("arm", _ARMS)
def test_each_arm_writes_the_new_fields(temp_db, monkeypatch, arm):
    _with_door(monkeypatch)
    before = _last_audit_id()
    _drive(monkeypatch, arm)
    written = _audit_rows_since(before)
```

### Tests: call-site scans
```python
# SOURCE: tests/test_query_pipeline_audit_fields.py:505-518 (AST, (path, enclosing, keywords, lineno))
# SOURCE: tests/test_query_pipeline_pii_profiles.py:884-897 (paren-matched source text, `"profile=" not in call`)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/models.py` | UPDATE | Column in `CREATE_AUDIT_LOGS_TABLE` + `AUDIT_LOGS_ADDED_COLUMNS`; `AuditLog.ignored_params` before `id` |
| `app/db/database.py` | UPDATE | `insert_audit_log` column list + `?` + value; `_row_to_audit_log` mapping; `'ignored_params'` key in `_SUMMARY_SQL`'s `json_object` |
| `app/services/audit_logger.py` | UPDATE | `log_query(..., ignored_params: Optional[str] = None)` → `AuditLog(ignored_params=...)` |
| `app/services/query_pipeline.py` | UPDATE | Required `_deny` param; keyword-only `run_conversation` param; threaded to 4 `_deny` + 10 `log_query` sites |
| `app/models/schemas.py` | UPDATE | `AuditQueryEntry.ignored_params: Optional[str] = None` |
| `app/routers/admin.py` | UPDATE | `ignored_params=log.ignored_params` passthrough |
| `tests/test_db.py` | UPDATE | Column set (`:1089`), dataclass tail (`:2262`), new migration/round-trip tests |
| `tests/test_audit_characterization.py` | UPDATE | `"ignored_params"` into `FIELDS_ADDED_SINCE` (`:116`) |
| `tests/test_query_pipeline_audit_fields.py` | UPDATE | Per-arm `ignored_params` assertions (12 arms), `_deny` required, scan extension |
| `tests/test_query_pipeline_pii_profiles.py` | UPDATE | Scan: every pipeline `log_query` call passes `ignored_params=` |
| `tests/test_query_pipeline_break_glass.py` | UPDATE | Break-glass arm carries the value / NULL |
| `tests/test_query_pipeline_usage_limits.py` | UPDATE | Usage-limit arm carries the value / NULL |
| `tests/test_query_pipeline_run_conversation.py` | UPDATE | Signature list gains `ignored_params` (keyword-only, default None) |
| `tests/test_audit_router.py` | UPDATE | `/audit` key set (`:104`) + value / NULL tests |

**Not changed**, by the story: `app/routers/query.py` (foreign-session refusal stays NULL by default), `run_query` (passes nothing), `chat_ui/` (admin console out of scope, PRD Section 4), `app/services/reports.py` (does not project audit columns — verified: no column names in it), `/stats` (no change, PRD Section 10), `tests/test_admin_models.py` (console model, untouched).

---

## Tasks

Execute in order. Each task is atomic + verifiable. All test runs use the venv and libSQL setup from the harness-ai test-env notes; DB tests carry the `db` marker.

### Task 1: Schema — column, migration entry, dataclass field

- **File**: `app/db/models.py`
- **Action**: UPDATE
- **Implement**:
  - Append `ignored_params TEXT` after `limit_exceeded TEXT` in `CREATE_AUDIT_LOGS_TABLE` (comma on the preceding line).
  - Extend the header comment of `AUDIT_LOGS_ADDED_COLUMNS` ("...; PRD-015 STORY-007 adds ignored_params").
  - Append `"ignored_params": "TEXT"` at the end of `AUDIT_LOGS_ADDED_COLUMNS` with a comment in the style of `ingress`: PRD-015 (Section 7.3, D3): the sorted, comma-joined *names* of top-level request keys (and `stream_options.<key>`) a `/v1` caller sent that the harness did not forward — never values. Nullable with no default on purpose: NULL is "nothing ignored", which is true of every `/query` and chat row and every row written before PRD-015; never backfilled.
  - Add `ignored_params: Optional[str] = None` to `AuditLog` after `limit_exceeded`, before `id`, with a short comment in the existing style ("PRD-015 STORY-007. Same pattern as limit_exceeded: insert_audit_log() writes it and _row_to_audit_log() maps it back on both read shapes. Set only by `/v1` (STORY-009); NULL everywhere else. Declared after limit_exceeded to mirror the table, so id stays the trailing field.").
- **Mirror**: `app/db/models.py:92-97` (`ingress` entry), `:378-398` (dataclass tail)
- **Validate**: `python -c "from app.db.models import AUDIT_LOGS_ADDED_COLUMNS as m; assert m['ignored_params']=='TEXT'"`

### Task 2: Writer and readers in `database.py`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  - `insert_audit_log` (`:788`): add `ignored_params` after `limit_exceeded` in the column list, one more `?` (32 total), and `entry.ignored_params` last in the tuple.
  - `_row_to_audit_log` (`:886`): `ignored_params=row["ignored_params"]`.
  - `_SUMMARY_SQL` (`:1308-1342`): add `'ignored_params', ignored_params` after `'limit_exceeded', limit_exceeded` in the `json_object(...)`. **Required**, not optional: `summary_snapshot()` feeds those dicts to `_row_to_audit_log`, and a missing key is a `KeyError` that takes down the admin console summary. It adds no `?`, so the parameter tuple is unchanged (the comment at `:1290-1294` stays true).
  - `_add_missing_columns` and `init_db` need **no** change.
- **Mirror**: the `limit_exceeded` lines in each of the three places
- **Validate**: `pytest tests/test_db.py -q -m db` (after Task 7's test edits, or expect the two known shape assertions in Task 7 to fail until then)

### Task 3: `log_query` parameter

- **File**: `app/services/audit_logger.py`
- **Action**: UPDATE
- **Implement**: Add `ignored_params: Optional[str] = None` after `limit_exceeded`, preceded by a comment in the `profile` style: "PRD-015 STORY-007 (Section 7.3, D3). Defaulted here but never omitted in the pipeline: every row run_conversation writes passes it explicitly -- _deny requires it, and tests/test_query_pipeline_audit_fields.py and tests/test_query_pipeline_pii_profiles.py scan every direct call site. The default exists for the callers that never ignore anything: /query's foreign-session refusal (app/routers/query.py), the test suite and scripts/, where NULL is the truth." Pass `ignored_params=ignored_params` into `AuditLog(...)`. Store the string verbatim (the router builds it; no joining here, unlike `pii_entities`).
- **Mirror**: `app/services/audit_logger.py:35-43`, `:86`
- **Validate**: `pytest tests/test_audit_logger.py -q`

### Task 4: Thread through the pipeline

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**:
  - `_deny`: add `ignored_params: Optional[str],` after `streamed: bool,` and before `exc`, **no default**, comment: "Required for the same reason as the five above (PRD-015 STORY-007): a forgotten authorization arm is a TypeError, not a `/v1` row that silently claims the client got everything it asked for." Pass `ignored_params=ignored_params` to its `log_query`.
  - `run_conversation`: add keyword-only `ignored_params: Optional[str] = None` after `streamed`, comment: "PRD-015 Section 7.3: the names `/v1` did not forward, computed by v1_translate and passed by the router (STORY-009). None for every other door; run_query passes nothing."
  - Thread `ignored_params=ignored_params` to all fourteen sites, placed right after `streamed=...` in each (PRD-013 STORY-005 diff shape):
    - `_deny` × 4: permission-denied (`:300`), model-not-permitted (`:310`), byok-denied (`:321`), break-glass (`:341`)
    - `log_query` × 10: usage limit (`:387`), context limit (`:431`), duplicate (`:461`), pattern block (`:509`), flag (`:541`), redaction limit (`:581`), input-redaction error (`:624`), upstream error (`:657`), output-redaction error (`:714`), success (`:742`)
  - `run_query`: **no change** (it passes nothing; the default is None).
- **Mirror**: every existing `streamed=streamed,` line in the module
- **Validate**: `grep -c "ignored_params=ignored_params" app/services/query_pipeline.py` → `15` (14 sites + `_deny`'s own `log_query`)

### Task 5: `/audit` read model and passthrough

- **Files**: `app/models/schemas.py`, `app/routers/admin.py`
- **Action**: UPDATE
- **Implement**:
  - `AuditQueryEntry`: `ignored_params: Optional[str] = None` after `limit_exceeded`, with a comment: "PRD-015 Section 10: the client parameter names `/v1` did not forward, sorted and comma-joined. Optional, defaulted and unvalidated for `session_id`'s reasons: NULL on every `/query` and chat row and on every row written before PRD-015."
  - `admin.py`: `ignored_params=log.ignored_params,` after `limit_exceeded=log.limit_exceeded,`, with "Verbatim passthrough (PRD-015 Section 10); NULL off `/v1`."
  - No `/stats` change.
- **Mirror**: `app/models/schemas.py:213-218`, `app/routers/admin.py:59-60`
- **Validate**: `pytest tests/test_audit_router.py -q` (after Task 9)

### Task 6: Characterization bookkeeping

- **File**: `tests/test_audit_characterization.py`
- **Action**: UPDATE
- **Implement**: add `# PRD-015 STORY-007.` and `"ignored_params"` to `FIELDS_ADDED_SINCE` (`:116`). This is what that module's docstring prescribes for a new `AuditLog` field. No pinned row changes: `_drive` passes nothing, so every characterized row stays NULL.
- **Validate**: `pytest tests/test_audit_characterization.py -q -m db`

### Task 7: DB tests

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**:
  - `:1089` column-set test: add `"ignored_params"` with a `# PRD-015 STORY-007` comment.
  - `:2262` dataclass-tail test: extend to `names[-15:]` with `"ignored_params"` before `"id"`, and extend its comment.
  - New tests in a `# PRD-015 STORY-007` section, mirroring the PRD-013 STORY-002 section (`:2895+`):
    1. `AUDIT_LOGS_ADDED_COLUMNS["ignored_params"] == "TEXT"` and the column appears in `CREATE_AUDIT_LOGS_TABLE`.
    2. Migration (AC 1): build an `audit_logs` table **without** the column (reuse the existing "old database" helper used for the PRD-013 migration test), insert a row, run `init_db()` → `PRAGMA table_info` shows `ignored_params` with type `TEXT`, `notnull == 0`, `dflt_value is None`; the old row reads NULL through `get_audit_log`; a second `init_db()` is a no-op (column set unchanged, row unchanged).
    3. Round trip: `insert_audit_log(AuditLog(..., ignored_params="seed,user"))` → `get_audit_log(id).ignored_params == "seed,user"`; default construction reads `None`.
    4. Summary path: one row with `ignored_params="seed"` → `summary_snapshot()`'s row carries it (guards the `json_object` key from Task 2).
- **Mirror**: `tests/test_db.py:2895-2945` (`_PRD013_COLUMNS` section) and its migration test
- **Validate**: `pytest tests/test_db.py -q -m db`

### Task 8: Pipeline tests — every arm, `_deny` required, scans

- **Files**: `tests/test_query_pipeline_audit_fields.py`, `tests/test_query_pipeline_pii_profiles.py`, `tests/test_query_pipeline_break_glass.py`, `tests/test_query_pipeline_usage_limits.py`, `tests/test_query_pipeline_run_conversation.py`
- **Action**: UPDATE
- **Implement**:
  - `test_query_pipeline_audit_fields.py` (new `# --- PRD-015 STORY-007: ignored_params` section, docstring bullet added):
    - `_with_ignored(monkeypatch, value)`: wraps `query_pipeline.run_conversation` like `_with_door` and adds `ignored_params=value`.
    - `test_each_arm_records_ignored_params` parametrized over `_ARMS` (the 12 `ARM_CASES` arms): every row in `_audit_rows_since(before)` has `ignored_params == "seed,user"`, and the row count equals `len(_ROWS_BY_ARM[arm])`.
    - `test_each_arm_without_ignored_params_records_null` over `_ARMS`: `_drive` as is → every row `None`.
    - Extend `test_deny_requires_each_new_field_with_no_default`'s parametrize list with `"ignored_params"` (AC 3), plus a direct `TypeError` test: call `query_pipeline._deny` with every other argument and no `ignored_params` → `pytest.raises(TypeError)`.
    - New scan test `test_every_pipeline_log_query_call_passes_ignored_params`: from `_scan().log_query`, sites with `path == "app/services/query_pipeline.py"` (the 11: ten arms + `_deny`) must all have `"ignored_params" in keywords`; the router's foreign-session site is asserted to **not** pass it (it stays NULL by default, per the story). Leave the `len(sites) == 12` count test unchanged.
  - `test_query_pipeline_pii_profiles.py`: beside `test_every_log_query_call_site_in_the_pipeline_passes_profile`, add `..._passes_ignored_params` using `_log_query_call_sources(inspect.getsource(query_pipeline))`, `len(calls) == 11`, `"ignored_params=" in call` for each.
  - `test_query_pipeline_break_glass.py` (arm outside `ARM_CASES`): `_run(_break_glass(), ingress="v1", ...)` with `ignored_params="seed,user"` added to the kwargs (extend `_run` with an optional `**kwargs` passthrough, or call `run_conversation` directly) → `_last_audit_entry().ignored_params == "seed,user"`; without it → `None`.
  - `test_query_pipeline_usage_limits.py` (arm outside `ARM_CASES`): with `_limits(rpm="*=1")` + `_returns(_usage(window_requests=2))` and `USAGE_LIMITS_ENABLED` as the existing refusal test sets it, `_run(..., ignored_params="seed,user")` (its `_run` already forwards `**kwargs`) → refusal row carries `"seed,user"`; omitted → `None`.
  - `test_query_pipeline_run_conversation.py:76`: append `"ignored_params"` to the signature list, assert default `None` and `KEYWORD_ONLY`; extend the comment. `run_query`'s signature test stays unchanged (it gains nothing).
- **Mirror**: `tests/test_query_pipeline_audit_fields.py:119-229`, `tests/test_query_pipeline_pii_profiles.py:884-897`, `tests/test_query_pipeline_break_glass.py:132-153`, `tests/test_query_pipeline_usage_limits.py:223-265`
- **Validate**: `pytest tests/test_query_pipeline_audit_fields.py tests/test_query_pipeline_pii_profiles.py tests/test_query_pipeline_break_glass.py tests/test_query_pipeline_usage_limits.py tests/test_query_pipeline_run_conversation.py -q`

### Task 9: `/audit` tests

- **File**: `tests/test_audit_router.py`
- **Action**: UPDATE
- **Implement**:
  - `:104` key-set assertion: add `"ignored_params"` with a `# PRD-015 Section 10: additive, nullable (STORY-007).` comment. Every value assertion stays as is.
  - New test: `insert_audit_log` a row with `ignored_params="seed,user"` and one without → `GET /audit` (admin headers) returns `"seed,user"` and `null` respectively.
  - New test: a `/query` success through the real route (`TestClient`, user headers, stubbed upstream as the existing router tests do) → its `/audit` entry has `ignored_params is None`. The chat-UI NULL case is covered by `ChatState` passing nothing to `run_conversation`/`run_query`; add one assertion to the existing `test_a_chat_send_without_history_names_the_chat_door`-style test in `test_query_pipeline_audit_fields.py` (`row.ignored_params is None`) rather than a new chat harness.
- **Mirror**: `tests/test_audit_router.py:85-115` and the PRD-013 entry test in `tests/test_audit_stats_prd013.py:160-240`
- **Validate**: `pytest tests/test_audit_router.py tests/test_audit_stats_prd013.py -q -m db`

### Task 10: Full regression

- **Validate**: full suite (`pytest -q`), then `-m "not db"` if the libSQL container is unavailable, and record which ran. Expect zero changes to `/stats` and every existing `/audit` value assertion.

---

## End-to-End Tests

- [ ] Fresh DB: start the app (`uvicorn app.main:app`) → boots; `PRAGMA table_info(audit_logs)` lists `ignored_params` TEXT nullable.
- [ ] Old DB: point the app at a database file created before this story (or a throwaway libSQL container seeded with the pre-story schema) → boots, column added, existing rows `ignored_params IS NULL`; restart → no ALTER, no error.
- [ ] `POST /query` with a valid user token → 200; `GET /audit` with the admin token → the new entry has `"ignored_params": null`, every other field as before.
- [ ] `GET /stats` → body shape and figures unchanged.
- [ ] A direct `run_conversation(..., ingress="v1", ignored_params="seed,user")` against the running DB → `GET /audit` shows `"ignored_params": "seed,user"` (the `/v1` route itself lands in STORY-009).

---

## Validation

```bash
pytest tests/test_db.py tests/test_audit_logger.py tests/test_audit_characterization.py \
       tests/test_query_pipeline_audit_fields.py tests/test_query_pipeline_pii_profiles.py \
       tests/test_query_pipeline_break_glass.py tests/test_query_pipeline_usage_limits.py \
       tests/test_query_pipeline_run_conversation.py tests/test_audit_router.py \
       tests/test_audit_stats_prd013.py -q
pytest -q
uvicorn app.main:app  # boots without error
```

---

## Risks + Mitigations

| Risk | Mitigation |
|------|------------|
| `summary_snapshot()`'s `json_object` omits the key → `KeyError` in `_row_to_audit_log` on the console summary | Task 2 adds it; Task 7 test 4 pins it |
| Hand-counted `?` / tuple drift in `insert_audit_log` | Column, `?` and value all appended last; round-trip test with a distinctive value |
| A forgotten arm writes NULL on `/v1` | `_deny` param required (TypeError); two independent call-site scans; per-arm tests over all 12 `ARM_CASES` + break-glass + usage-limit = 14 |
| Router's foreign-session `log_query` caught by an over-broad scan | The AST scan filters on `path == app/services/query_pipeline.py`; the source scan only reads `query_pipeline` |
| Existing shape assertions (column set, dataclass tail, `/audit` key set, `FIELDS_ADDED_SINCE`, `run_conversation` signature) fail | Listed explicitly in Tasks 6–9; they are additive name additions, not value changes |
| libSQL dev container down / flaky shared DB | Use the throwaway `HARNESS_TEST_LIBSQL_URL` container; fall back to `-m "not db"` and report which ran |

---

## Acceptance Criteria

(Copied from story `STORY-007`)

- [ ] Given an existing database without the column, when `init_db()` runs, then `audit_logs.ignored_params` exists as nullable TEXT, existing rows read NULL, and a second `init_db()` is a no-op.
- [ ] Given `run_conversation(..., ignored_params="seed,user")`, when each arm writes its row (the three authorization denials, break-glass, usage limit, context limit, duplicate, pattern block, flag, redaction limit, redaction error, upstream error, output-redaction error, success), then every row carries `"seed,user"`; given the keyword omitted, then every row carries NULL.
- [ ] Given `_deny` called without `ignored_params`, when it runs, then it raises `TypeError` (required, as `session_id`, `dedup_key`, `profile` and `ingress` are).
- [ ] Given `GET /audit`, when a row has the column set, then `AuditQueryEntry.ignored_params` returns it; rows written by `/query` and the chat UI return `null`, and every existing `/audit` and `/stats` assertion is unchanged.
- [ ] Given the production sources, when the call-site scans run (`tests/test_query_pipeline_audit_fields.py`, `tests/test_query_pipeline_pii_profiles.py`), then every direct `log_query` call inside `run_conversation` passes `ignored_params`.
- [ ] All tasks completed
- [ ] Backend server starts without error
- [ ] Follows existing patterns
