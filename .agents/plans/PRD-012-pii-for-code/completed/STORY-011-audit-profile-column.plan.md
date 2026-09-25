---
story: STORY-011
prd: PRD-012
slug: audit-profile-column
title: "audit_logs.profile on every arm; /audit and the Register show it"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-012-pii-for-code        # all stories commit here, no per-story branch
created: 2026-09-25
---

# Plan: audit_logs.profile on every arm; /audit and the Register show it

## Summary

This story adds one nullable column, `audit_logs.profile TEXT`, and carries it end to end.

- **Schema.** The column goes into `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS`. It has no default and no backfill, the same as `dedup_key` and `pattern_action`. `AuditLog.profile` is declared after `pattern_action`, so `id` stays the trailing field.
- **Storage.** The value flows through `insert_audit_log`, `_row_to_audit_log` and the `json_object(...)` in `_SUMMARY_SQL`.
- **Pipeline.** `run_conversation` resolves `profile_name` once, directly after step 0. Today that happens at step 5. Moving it up is safe because it is a pure expression over the argument and `settings.PATTERN_PROFILE_DEFAULT`.
  - `_deny` gains a required keyword, `profile`.
  - Every one of the ten `log_query(...)` call sites in the module passes `profile=`. Nine pass `profile_name` directly, and `_deny`'s call passes its parameter.
  - `log_query` keeps an `Optional` default, because the `/query` router's foreign-session arm writes before any profile exists. That arm passes `profile=None` explicitly and has a comment explaining why.
  - A source-scan test enforces the rule for the direct call sites, the same way `session_id=` and `dedup_key=` are enforced today.
- **Read side.** `AuditQueryEntry.profile` is nullable. `GET /audit` passes it through. The admin Register shows it on the row disclosure under the label "Profile", directly above the "PII in prompt / PII in response" lines it qualifies.
- **Stats.** `/stats` and the snapshot figures do not change. No query gains a profile predicate.

## User Story

As a security admin
I want every audit row to say which profile ran
So that `pii_detected_output = 0` on a `code` row is read as "not analyzed" rather than "clean"

## Story Reference

- Story file: `.agents/stories/PRD-012-pii-for-code/STORY-011-audit-profile-column.md`
- PRD: `.agents/PRDs/PRD-012-pii-for-code/PRD.md` (Sections 6.8 / D9, 7 / F9, 9.2 T1, 10, 11)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | audit schema + convergence, db writer/readers + summary snapshot, audit logger, query pipeline (every arm), `/query` router, `/audit` schema + router, admin console Register |
| Story | STORY-011 |
| PRD | PRD-012 |
| Epic Branch | `epic/PRD-012-pii-for-code` (commit directly on this branch) |
| Depends on | STORY-010 (done, `46c88b6`) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` contains only `frontend-design`. The story sets `skills: []`, and its Technical Notes say the skill does not apply: adding one field to the existing Register row disclosure is not a visual redesign. There is no new component, layout, pigment or column. The copy follows the existing `admin_copy` vocabulary: one label constant, with the value shown exactly as recorded. | — |

---

## Patterns to Follow

### Additive nullable column: declared in both places, no backfill
```python
# SOURCE: app/db/models.py:64-72
    # PRD-011 (D6): which role's message a pattern hit was found in (`user`,
    # `tool`, `system`, `assistant`) and what the profile did about it (`block`
    # or `flag`). ... Nullable with
    # no default on purpose, like dedup_key: rows written before PRD-011 stay
    # NULL and are never backfilled, ...
    "pattern_role": "TEXT",
    "pattern_action": "TEXT",
```

### Dataclass field appended before `id`
```python
# SOURCE: app/db/models.py:253-260
    # PRD-011 STORY-009. Same pattern as dedup_key: insert_audit_log() writes
    # both and _row_to_audit_log() maps them back on both read shapes. ...
    # dedup_key to mirror the table, so id stays the trailing field.
    pattern_role: Optional[str] = None
    pattern_action: Optional[str] = None
    id: Optional[int] = None
```

### Required keyword on `_deny` (a forgotten arm is a TypeError)
```python
# SOURCE: app/services/query_pipeline.py:162-192
def _deny(
    identity: Identity,
    prompt: str,
    device: Optional[str],
    # Required, and deliberately not defaulted or closed over: ...
    # Required means a forgotten arm is a TypeError, not a NULL nobody
    # notices for a release. (PRD-008 STORY-009)
    session_id: Optional[str],
    # Required for the same reason as session_id: ...
    dedup_key: Optional[str],
    exc: PermissionDenied,
    reason: str,
) -> QueryBlockedForbiddenResponse:
    log_query(..., session_id=session_id, dedup_key=dedup_key)
```

### An explicit `None` at the router's foreign-session arm, spelled out as a decision
```python
# SOURCE: app/routers/query.py:85-111
    # 5. `dedup_key=None`, explicitly (PRD-009 STORY-006). ...
    #    The `None` is spelled out so it reads as a decision, not an omission.
        log_query(
            ...
            session_id=request.session_id,
            dedup_key=None,  # see 5. above
        )
```

### Read-model field: Optional, defaulted, no validator
```python
# SOURCE: app/models/schemas.py:173-184
    # PRD-011 D6: which role the matched message had ... and what the policy did with it
    # Optional, defaulted and unvalidated for `session_id`'s reasons: both are
    # NULL on every row without a pattern and on every row written before
    # PRD-011. ...
    pattern_role: Optional[str] = None
    pattern_action: Optional[str] = None
```

### Register: absent mark written at the boundary, field on the disclosure
```python
# SOURCE: chat_ui/chat_ui/admin_formatting.py:221-222
        pattern_role=_text(log.pattern_role),
        pattern_action=_text(log.pattern_action),
# SOURCE: chat_ui/chat_ui/components/register.py:434-438
            _detail_field(admin_copy.DETAIL_PATTERN_ROLE_LABEL, row.pattern_role),
            _detail_field(admin_copy.DETAIL_PATTERN_ACTION_LABEL, row.pattern_action),
```

### Tests: every-call-site source scan
```python
# SOURCE: tests/test_query_pipeline_dedup_key.py:231-251
def test_every_log_query_call_site_in_the_pipeline_passes_dedup_key():
    calls = _log_query_call_sources(inspect.getsource(query_pipeline))
    assert len(calls) == 10, f"expected ten log_query call sites, found {len(calls)}"
    missing = [call for call in calls if "dedup_key=" not in call]
    assert missing == [], f"log_query call sites not passing dedup_key: {missing}"
```

### Tests: convergence on a pre-existing database
```python
# SOURCE: tests/test_db.py:488-530 (_create_pre_pattern_role_database) and 2329-2359
def test_init_db_migrates_a_pre_pattern_role_database(uninitialized_db, db_connect):
    _create_pre_pattern_role_database(db_connect, uninitialized_db)
    init_db()
    ...
    assert columns.count("pattern_action") == 1
    preserved = get_audit_log(1)
    assert preserved.pattern_action is None
```

### Tests: driving the flag arm with no bypass
```python
# SOURCE: tests/test_query_pipeline_patterns.py:361-367
_USER_FLAGS = _Profile(lists=BUILT_IN_POLICY.profiles["code"].lists, roles={"user": "flag"})

def _use_profile(monkeypatch, profile) -> None:
    monkeypatch.setattr(query_pipeline, "get_profile", lambda name: profile)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/models.py` | UPDATE | `profile TEXT` in `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS`; `AuditLog.profile` |
| `app/db/database.py` | UPDATE | Writer (+1 column/placeholder), `_row_to_audit_log`, `_SUMMARY_SQL` `json_object`, `init_db` docstring |
| `app/services/audit_logger.py` | UPDATE | `log_query(..., profile: Optional[str] = None)` with the documented exception |
| `app/services/query_pipeline.py` | UPDATE | Resolve `profile_name` at the top; required `profile` on `_deny`; `profile=` on all ten call sites; refresh the comments at step 5 and step 8 |
| `app/routers/query.py` | UPDATE | Foreign-session arm passes `profile=None` explicitly, with a numbered comment |
| `app/models/schemas.py` | UPDATE | `AuditQueryEntry.profile: Optional[str] = None` |
| `app/routers/admin.py` | UPDATE | `GET /audit` passes `profile=log.profile` through |
| `chat_ui/chat_ui/admin_models.py` | UPDATE | `AuditRow.profile: str = ""` (disclosure-only) |
| `chat_ui/chat_ui/admin_formatting.py` | UPDATE | `to_audit_row` sets `profile=_text(log.profile)` |
| `chat_ui/chat_ui/admin_copy.py` | UPDATE | `DETAIL_PROFILE_LABEL = "Profile"` |
| `chat_ui/chat_ui/components/register.py` | UPDATE | `_detail` renders the profile above the PII lines; docstrings list it |
| `tests/test_db.py` | UPDATE | Column set, dataclass tail, and a new pre-profile convergence and round-trip section |
| `tests/test_migrate_to_turso_cli.py` | UPDATE | DDL column list gains `profile` |
| `tests/test_audit_logger.py` | UPDATE | `log_query` default is None; it carries a value |
| `tests/test_query_pipeline_pii_profiles.py` | UPDATE | New section: profile on every arm, `_deny` signature, call-site scan, resolution once |
| `tests/test_query_router.py` | UPDATE | `/query` writes `profile='chat'`; foreign-session arm writes NULL |
| `tests/test_chat_state.py` | UPDATE | `ChatState.send` writes `profile='chat'` on both pipeline branches |
| `tests/test_audit_router.py` | UPDATE | Key set gains `profile`; passthrough test incl. legacy NULL |
| `tests/test_schemas.py` | UPDATE | Serialized entry gains `"profile": None` |
| `tests/test_stats_router.py` | UPDATE | PII figures identical with and without `profile='chat'` |
| `tests/test_admin_models.py` | UPDATE | `AuditRow` field set gains `profile` |
| `tests/test_admin_formatting.py` | UPDATE | `to_audit_row` carries the profile; legacy row shows `VALUE_ABSENT` |
| `tests/test_register.py` | UPDATE | `DETAIL_LABELS`, `DETAIL_ROW_FIELDS`, the `_Log` stub, and an ordering test |

No files are created. The migration script (`scripts/migrate_to_turso.py`) needs no change, because it derives its column list from the DDL through `_ddl_columns`. Its pinned test is updated in Task 9.

---

## Tasks

Execute in order. Each task is atomic and verifiable. The validate commands assume the libSQL dev server `conftest.py` expects is running. If a test file shows mass fixture errors, restart the server first.

### Task 1: Schema: declare the column in both places, and add it to `AuditLog`

- **File**: `app/db/models.py`
- **Action**: UPDATE
- **Implement**:
  - Append `    profile TEXT` after `pattern_action TEXT` in `CREATE_AUDIT_LOGS_TABLE`. Add the comma on the preceding line.
  - Append `"profile": "TEXT"` to `AUDIT_LOGS_ADDED_COLUMNS`, with a comment in the house style:
    - It is PRD-012 (D9): the profile name the call site passed, after default resolution (`chat` for `/query` and the chat UI).
    - It is what tells a reader that `pii_detected_output = 0` under `code` means "not analyzed".
    - It is nullable with no default on purpose, like `dedup_key`. Rows written before PRD-012 stay NULL and are never backfilled, and so does the router's foreign-session refusal, which writes before any profile exists.
  - Extend the header comment's history list with "PRD-012 STORY-011 adds profile".
  - Add `profile: Optional[str] = None` to `AuditLog` after `pattern_action` and before `id`. Give it a comment matching the `pattern_role` one: `insert_audit_log()` writes it, and `_row_to_audit_log()` maps it back on both read shapes.
- **Mirror**: `app/db/models.py:64-72`, `:253-260`
- **Validate**: `python -c "from app.db.models import AuditLog, AUDIT_LOGS_ADDED_COLUMNS, CREATE_AUDIT_LOGS_TABLE as C; assert 'profile TEXT' in C and AUDIT_LOGS_ADDED_COLUMNS['profile']=='TEXT'; print([f for f in AuditLog.__dataclass_fields__][-3:])"` prints `['pattern_action', 'profile', 'id']`

### Task 2: Storage: writer, both readers, and the batched snapshot

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  - `insert_audit_log`: add `profile` to the column list after `pattern_action`, add a 23rd `?`, and append `entry.profile` to the tuple.
  - `_row_to_audit_log`: add `profile=row["profile"]`.
  - `_SUMMARY_SQL`: add `'profile', profile` to the `json_object(...)` after `'pattern_action', pattern_action`. The four positional parameters do not move, because this is inside the `rows` subquery and no `?` is added. If this key is missing, every batched `rows` read fails (see the batched-read test pattern at `tests/test_db.py:2403`).
  - `init_db` docstring: add one paragraph. PRD-012 STORY-011 adds `audit_logs.profile` on the `pattern_role`/`pattern_action` path with no new code: it is nullable, has no default and is not indexed.
  - No counter or `/stats` query changes (AC 5).
- **Mirror**: `app/db/database.py:762-800`, `:841-878`, `:1196-1220`
- **Validate**: `pytest tests/test_db.py -q` (expected failures before Task 9 updates them: only the pinned column-set and dataclass-tail tests)

### Task 3: `log_query` accepts `profile`, with the router exception documented

- **File**: `app/services/audit_logger.py`
- **Action**: UPDATE
- **Implement**: Add `profile: Optional[str] = None` after `pattern_action` and pass `profile=profile` into `AuditLog(...)`. Put a comment above the parameter that covers three points:
  - It is defaulted here but **not** in the pipeline. Every row `run_conversation` writes passes it explicitly: `_deny` requires it, and `tests/test_query_pipeline_pii_profiles.py` scans every direct call site.
  - The default exists for one caller, the `/query` router's foreign-session refusal (`app/routers/query.py`). That arm writes before `run_query` runs, so before any profile is resolved, and NULL is the truth for it.
  - Refer to PRD-012 D9 and PRD-008 STORY-009 / PRD-009 Risk 6 for the required-keyword rule.
- **Mirror**: `app/services/audit_logger.py:30-34` (the `pattern_role` comment)
- **Validate**: `pytest tests/test_audit_logger.py -q`

### Task 4: Pipeline: resolve once at the top; `profile` on every arm

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**:
  1. Move `profile_name = profile if profile is not None else settings.PATTERN_PROFILE_DEFAULT` up to directly after `prompt = messages[-1].content` (after step 0 and before step 1).
     - Comment: the audit needs the name on every arm, the forbidden ones included (PRD-012 D9). It is a pure function of the argument and one setting, so resolving it before authorization cannot change the check order, the same argument step 1 makes for `key`.
     - Delete the original line at step 5. Step 5 and step 6 keep reading `profile_name`.
  2. Rewrite the step-5 comment "An unknown profile is a call-site bug and raises PatternConfigError here. Every earlier arm that writes a row has already returned, so it leaves no row behind." It is still a call-site bug that raises here, but an earlier arm (forbidden, context limit, duplicate) now records the unresolvable name on its row. That is accurate: the name is what the call site passed. Keep the sentence short.
  3. `_deny`: add a required keyword parameter `profile: str` after `dedup_key`. No default, with a comment: "Required for the same reason as session_id and dedup_key: a forgotten arm is a TypeError, not a NULL that makes a `code` row's `pii_detected_output = 0` read as clean (PRD-012 D9)." Pass `profile=profile` to `log_query`. The three `_deny(...)` call sites add `profile=profile_name`.
     - Annotate it `str`, not `Optional[str]`, because after resolution it is never None.
  4. Add `profile=profile_name` to each of the nine direct `log_query(...)` call sites, placed after `dedup_key=key` (or after `pattern_action=` where present):
     - context limit
     - duplicate
     - pattern block
     - pattern flag
     - redaction limit
     - input redaction error
     - upstream error
     - output redaction error
     - success
  5. Step-8 comment: replace "PRD-012 STORY-011's `profile` column is what tells a reader of the row which it was" with the present tense: the row's `profile` column says which it was.
- **Mirror**: `app/services/query_pipeline.py:162-192` (`_deny`), `:211-216` (step 1 comment style)
- **Validate**: `pytest tests/test_query_pipeline_dedup_key.py tests/test_query_pipeline_session_passthrough.py tests/test_query_pipeline_patterns.py tests/test_query_pipeline_pii_profiles.py -q` (existing suites stay green; the call-site count stays **10**)

### Task 5: Router: explicit `profile=None` on the foreign-session arm

- **File**: `app/routers/query.py`
- **Action**: UPDATE
- **Implement**: Add a numbered item `6.` to the existing comment block: "`profile=None`, explicitly (PRD-012 D9). The refusal happens before `run_query`, the single place the profile is resolved for `/query`, so no profile ran, and NULL records that. It is the one row `/query` writes without `profile='chat'`." Pass `profile=None,  # see 6. above` in the `log_query(...)` call.
- **Mirror**: `app/routers/query.py:85-111`
- **Validate**: `pytest tests/test_query_router.py tests/test_session_ownership.py -q`

### Task 6: `/audit`: `AuditQueryEntry.profile`, passed through

- **Files**: `app/models/schemas.py`, `app/routers/admin.py`
- **Action**: UPDATE
- **Implement**:
  - `AuditQueryEntry`: add `profile: Optional[str] = None` after `pattern_action`. Comment: this is PRD-012 D9, the profile that ran. It is Optional, defaulted and unvalidated for `session_id`'s reasons. NULL on every row written before PRD-012 and on `/query`'s foreign-session refusal. Under `code`, `pii_detected_output = False` means "not analyzed", and this field is what says so.
  - `admin.py`: add `profile=log.profile` after `pattern_action=log.pattern_action`, with a one-line "verbatim passthrough (PRD-012 D9)" comment.
- **Mirror**: `app/models/schemas.py:173-184`, `app/routers/admin.py:53-57`
- **Validate**: `pytest tests/test_audit_router.py tests/test_schemas.py -q` (expected failures before Task 9 updates them: only the pinned key sets)

### Task 7: Admin Register: the profile on the row disclosure

- **Files**: `chat_ui/chat_ui/admin_models.py`, `chat_ui/chat_ui/admin_formatting.py`, `chat_ui/chat_ui/admin_copy.py`, `chat_ui/chat_ui/components/register.py`
- **Action**: UPDATE
- **Implement**:
  - `admin_models.AuditRow`: add `profile: str = ""` after `pattern_action`. Comment: PRD-012 D9, disclosure-only; the absent mark on pre-PRD-012 rows.
  - `admin_formatting.to_audit_row`: `profile=_text(log.profile)`. It is shown as recorded (`chat` / `code` / a custom name), and nothing is inferred for a NULL.
  - `admin_copy`: add `DETAIL_PROFILE_LABEL = "Profile"` beside the PII labels. The comment says it qualifies the two PII lines below it: under `code`, "PII in response: none" means the response was not analyzed.
  - `register._detail`: insert `_detail_field(admin_copy.DETAIL_PROFILE_LABEL, row.profile)` **directly before** `_detail_label(admin_copy.DETAIL_PII_ENTITIES_LABEL)`, with a short comment explaining why it sits there. Add `profile` to the disclosure-only field lists in the `_detail` and `_row_line` docstrings.
  - The row itself stays at "ten children and no eleventh" (`register.py:470-480`). Placing the field on the disclosure is how the Register shows it without a visual redesign (story Technical Notes; PRD Section 10: "Admin console · Register | Shows `profile`").
- **Mirror**: `chat_ui/chat_ui/admin_formatting.py:221-222`, `components/register.py:434-438`, `admin_copy.py:271-277`
- **Validate**: `pytest tests/test_admin_formatting.py tests/test_admin_models.py tests/test_register.py tests/test_admin_copy.py -q` (expected failures before Task 9 updates them: only the pinned field sets)

### Task 8: New tests: profile on every arm (pipeline, router, chat UI)

- **Files**: `tests/test_query_pipeline_pii_profiles.py`, `tests/test_query_router.py`, `tests/test_chat_state.py`
- **Action**: UPDATE
- **Implement**: Add a section `# --- STORY-011: audit_logs.profile on every arm ---` to `test_query_pipeline_pii_profiles.py`, reusing its `_run`, `_Upstream`, `_audit_rows_since`, `_last_audit_id` and `_set`.
  - **`test_every_arm_records_the_resolved_profile`**, parametrized over `(arm, profile, expected)`. Each case asserts exactly one new row (two for the flag arm) and `row.profile == expected`.
    - **Chat, the default resolution**: `profile=None` expects `"chat"` on these arms:
      - permission denied (`role="auditor"`)
      - model not permitted
      - BYOK denied
      - context limit (`CONTEXT_MAX_CHARACTERS=10`)
      - duplicate (seed first)
      - pattern block (`override`)
      - input redaction error (monkeypatch `query_pipeline.redact` to raise `PiiRedactorError`)
      - upstream error
      - output redaction error (raise on the second call)
      - success
    - **Code**: `profile="code"` expects `"code"` on these arms:
      - permission denied
      - pattern block
      - redaction limit (`_set(monkeypatch, "PII_MAX_CHARACTERS_CODE", 10)` or the existing STORY-010 helper)
      - input redaction error via `redact_for_policy`
      - upstream error
      - success
    - **Flag**: `profile="code"` with `_use_profile(monkeypatch, _USER_FLAGS)` (imported from `tests.test_query_pipeline_patterns`) expects both the flag row and the success row to carry `"code"`.
    - **Output redaction error under `code`**: this arm is reachable only with `PII_CODE_REDACT_OUTPUT=True`, so set it for that case.
  - **`test_code_success_row_says_output_was_not_analyzed`**: under `code` with default settings and a response containing `alice@example.com`, the row has `pii_detected_output is False` and `profile == "code"` (PRD Section 5 story 2 example).
  - **`test_default_profile_setting_is_what_the_row_records`**: `monkeypatch.setattr(settings, "PATTERN_PROFILE_DEFAULT", "code")` plus a forbidden arm with `profile=None` records `"code"`. This proves the name is resolved from the setting and not hard-coded. The forbidden arm returns before step 5 needs the profile to exist in the patterns policy.
  - **`test_deny_requires_profile_with_no_default`**: `inspect.signature(query_pipeline._deny).parameters["profile"].default is inspect.Parameter.empty`, and calling `_deny` without it raises `TypeError` matching `"profile"`.
  - **`test_every_log_query_call_site_in_the_pipeline_passes_profile`**: reuse `_log_query_call_sources` (import from `tests.test_query_pipeline_dedup_key`). Assert `len(calls) == 10` and `[c for c in calls if "profile=" not in c] == []`. The docstring names the router exception.
  - **`test_profile_is_resolved_before_authorization`**: with `get_profile` monkeypatched to raise, a forbidden arm still writes its row with `profile == "chat"`. This proves the name does not depend on step 5's lookup.
  - `tests/test_query_router.py`:
    - `test_query_writes_profile_chat`: `POST /query` success, then `get_audit_log(audit_id).profile == "chat"`.
    - `test_foreign_session_refusal_writes_null_profile`: mirror the existing foreign-session test and assert `profile is None`.
  - `tests/test_chat_state.py`: `test_chat_state_send_writes_profile_chat`. After `_send(state, "hello world")`, `get_audit_log(state.messages[-1].audit_id).profile == "chat"`. Cover both branches if history is on by default in the test settings; otherwise add a second case with the history setting enabled so the `run_conversation` branch runs (PRD T1).
- **Mirror**: `tests/test_query_pipeline_dedup_key.py:101-176, 192-251`, `tests/test_query_pipeline_patterns.py:361-367, 439-470`
- **Validate**: `pytest tests/test_query_pipeline_pii_profiles.py tests/test_query_router.py tests/test_chat_state.py -q`

### Task 9: Update pinned tests and add convergence, read-side and Register tests

- **Files**: `tests/test_db.py`, `tests/test_migrate_to_turso_cli.py`, `tests/test_audit_logger.py`, `tests/test_audit_router.py`, `tests/test_schemas.py`, `tests/test_stats_router.py`, `tests/test_admin_models.py`, `tests/test_admin_formatting.py`, `tests/test_register.py`
- **Action**: UPDATE
- **Implement**:
  - **`test_db.py`**:
    - Add `"profile"` to the expected column set (around `:880-899`, with a `# PRD-012 STORY-011 (D9)` comment).
    - Change the dataclass-tail assertion (around `:2045`) to `names[-6:] == ["session_id", "dedup_key", "pattern_role", "pattern_action", "profile", "id"]`.
    - Add a section `# PRD-012 STORY-011: profile (D9)` containing:
      - `_create_pre_profile_database(connect, url)`: the 23-column table as it shipped after PRD-011 (with `pattern_role`/`pattern_action`), the dedup index, and one pattern-block row.
      - `test_audit_logs_added_columns_carries_nullable_profile`: declared in both places.
      - `test_init_db_adds_a_nullable_profile_column`: `notnull == 0`, `dflt_value is None`.
      - `test_init_db_migrates_a_pre_profile_database`: `columns.count("profile") == 1`, the legacy row reads `profile is None` (not backfilled), and its neighbours are preserved.
      - `test_profile_round_trips`: checks neighbours `pattern_action`/`dedup_key` too, to catch a placeholder miscount.
      - `test_profile_survives_the_batched_read`: `summary_snapshot().rows == list_audit_logs()`, with profiles `[None, "code"]`.
      - `test_init_db_issues_no_alter_when_schema_is_current`: already covers steady state; no edit expected, but confirm it passes.
  - **`test_migrate_to_turso_cli.py:165-174`**: append `"profile"` to the DDL list and to the trailing comment.
  - **`test_audit_logger.py`**: `log_query` without `profile` gives NULL, and with `profile="code"` gives `"code"`. Mirror `:295-327`.
  - **`test_audit_router.py`**:
    - Add `"profile"` to the key set (`:75-93`).
    - Add `test_audit_entry_carries_profile`: rows with `"chat"`, `"code"` and `None` pass through verbatim and in order.
  - **`test_schemas.py:~162`**: add `"profile": None` to the serialized entry.
  - **`test_stats_router.py`**: add `test_pii_figures_are_unchanged_by_the_profile_column` (AC 5). Insert the same PII-bearing rows twice, into two `temp_db` states (or compare against constants): once with `profile=None` and once with `profile="chat"`. Assert that `/stats` `pii_detected_queries` and `top_pii_entities`, and `summary_snapshot().pii_detected_queries` / `.top_pii_entities`, are equal. The simplest form is to insert the rows with `profile="chat"` and assert the same literal figures an existing PII stats test asserts for identical rows without it.
  - **`test_admin_models.py:~41`**: add `"profile"` to the `AuditRow` field set.
  - **`test_admin_formatting.py`**: add `test_to_audit_row_carries_the_profile`. `profile="code"` gives `"code"`, and a legacy row gives `VALUE_ABSENT`.
  - **`test_register.py`**:
    - Add `admin_copy.DETAIL_PROFILE_LABEL` to `DETAIL_LABELS`.
    - Add `"profile"` to `DETAIL_ROW_FIELDS`.
    - Add `profile = None` to the `_Log` stub (`:600-620`). Without it, `to_audit_row` raises `AttributeError`.
    - Add `test_the_profile_precedes_the_pii_lines`: `profile_at < pii_entities_at < pii_input_at < pii_output_at` in `probe["detail"]`.
- **Mirror**: `tests/test_db.py:2299-2445`, `tests/test_audit_router.py:96-135`, `tests/test_admin_formatting.py:152-167`, `tests/test_register.py:685-694`
- **Validate**: `pytest tests/test_db.py tests/test_migrate_to_turso_cli.py tests/test_audit_logger.py tests/test_audit_router.py tests/test_schemas.py tests/test_stats_router.py tests/test_admin_models.py tests/test_admin_formatting.py tests/test_register.py -q`

### Task 10: Full regression

- **Action**: Run the whole suite. Confirm that the seven-outcome regressions (`test_query_outcomes_regression.py`, `test_chat_outcomes_regression.py`), the PII characterization suite and `test_reporting_invariance.py` pass with **no assertion changed**. Only the pinned field and column lists in Task 9 may change.
- **Validate**: `pytest tests/ -q`

---

## End-to-End Tests

- [ ] Start the API (`uvicorn app.main:app`) against a database file created **before** this story. `init_db()` adds `profile` once, a second boot issues no `ALTER`, and every old row reads `profile: null` on `GET /audit`.
- [ ] `POST /query` with a user token: the new `GET /audit` entry has `"profile": "chat"`.
- [ ] `POST /query` with a `session_id` the caller does not own: 403, and the new entry has `"profile": null`.
- [ ] `POST /query` as a role without `query:submit`: forbidden body, and the entry has `"profile": "chat"`.
- [ ] Send one message in the chat UI: the row's `/audit` entry has `"profile": "chat"`.
- [ ] In a Python shell, call `run_conversation(..., profile="code")` with a stub upstream returning `alice@example.com`. `GET /audit` shows `"profile": "code"` and `"pii_detected_output": false`.
- [ ] Open the admin console Register and expand that row. "Profile: code" sits directly above "PII types / PII in prompt / PII in response". Expanding a pre-existing row shows the absent mark.
- [ ] `GET /stats` and the admin summary show the same `pii_detected_queries` and `top_pii_entities` before and after the migration on the same data.

---

## Validation

```bash
pytest tests/test_db.py tests/test_audit_logger.py tests/test_query_pipeline_pii_profiles.py -q
pytest tests/test_audit_router.py tests/test_stats_router.py tests/test_register.py tests/test_admin_formatting.py -q
pytest tests/ -q
uvicorn app.main:app --port 8000 &  curl -s http://localhost:8000/health
```

---

## Risks and Mitigations

| # | Risk | Mitigation |
|---|------|------------|
| 1 | A future arm is added without `profile=` and writes NULL, and a `code` row reads as clean | `_deny` requires it (TypeError). A source scan fails on any direct call site without `profile=`, and the count assertion (10) fails when an eleventh call site appears |
| 2 | `json_object(...)` in `_SUMMARY_SQL` is missed, so the batched snapshot fails on every call | `test_profile_survives_the_batched_read` |
| 3 | A placeholder miscount in `insert_audit_log` shifts values into the wrong columns | The round-trip test asserts the neighbouring columns |
| 4 | Moving `profile_name` above authorization changes behaviour | It is a pure expression, and step 5's `get_profile` call stays where it is. `test_profile_is_resolved_before_authorization` pins this, and the authorization, context-limit and duplicate suites are unchanged |
| 5 | AC 3 says `/query` writes `profile='chat'`, but the foreign-session refusal writes NULL | This follows the story's Technical Notes. That row is written before any profile exists, and the exception is documented in `log_query`, the router, `AuditQueryEntry`, and a test that asserts NULL |
| 6 | An operator sets `PATTERN_PROFILE_DEFAULT` to something other than `chat`, so `/query` rows record that name | This is correct per D9: the row records what actually ran. The `profile='chat'` assertions pin the shipped default |
| 7 | An unknown profile name is now recorded on forbidden, context-limit and duplicate rows before step 5 raises | This is accurate evidence of what the call site passed. The step-5 comment is updated. No ingress can pass an unknown name (PRD-011 T1) |
| 8 | Test stubs that duck-type `AuditLog` (`test_register.py` `_Log`) break on `log.profile` | Task 9 adds `profile = None` to the stub. Grep `class _Log` across the test files while doing so |

---

## Acceptance Criteria

(Copied from story `STORY-011`)

- [ ] Given `app/db/models.py`, when it is read, then `profile TEXT` is declared in both `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS`, and `AuditLog.profile: Optional[str] = None`. Given a database created before this story, when `init_db()` runs, then the column is added and no row is backfilled.
- [ ] Given `run_conversation`, when any arm writes a row (forbidden ×3, context limit, duplicate, pattern block, pattern flag, redaction limit, redaction error ×2, upstream error, success), then `profile` is passed explicitly as a required keyword and holds the resolved profile name.
- [ ] Given `/query` and the chat UI, when they write rows, then `profile='chat'`.
- [ ] Given `GET /audit`, when it returns an entry, then `AuditQueryEntry.profile` is present and nullable; given the admin Register, when a row is shown, then its profile is shown.
- [ ] Given `/stats` and the admin snapshot, when they are computed, then `pii_detected_queries` and `top_pii_entities` are unchanged for a database of `chat` rows.
- [ ] All tasks completed
- [ ] `pytest tests/` passes with no existing assertion changed beyond the pinned field and column lists
- [ ] Backend server starts without error
- [ ] Follows existing patterns
