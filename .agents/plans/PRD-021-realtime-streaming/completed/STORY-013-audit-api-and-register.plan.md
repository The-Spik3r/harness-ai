---
story: STORY-013
prd: PRD-021
slug: audit-api-and-register
title: GET /audit real-time fields, completion_id filter and Register LIVE marker
type: ENHANCEMENT
complexity: small
epic_branch: epic/PRD-021-realtime-streaming
created: 2026-11-19
---

# Plan: GET /audit real-time fields, completion_id filter and Register LIVE marker

## Summary

STORY-009 already stores and maps the four columns (`AuditLog` fields at `app/db/models.py:566-569`, row mapper `app/db/database.py:1838-1841`). This story only projects them: four new fields on `AuditQueryEntry` and in `get_audit` (`app/routers/admin.py`), an optional exact-match `?completion_id=` on `GET /audit` that rides the same fixed-clause / bound-parameter pattern as `list_action_decisions`, and a `LIVE` tag in the Register for `streamed_realtime=1` rows. No new public DB function, no schema change, no index.

- Story: `.agents/stories/PRD-021-realtime-streaming/STORY-013-audit-api-and-register.md`
- PRD sections used: F7, Section 10 (GET /audit), user story 6; D14, D17
- Systems affected: audit read API, `database.py` readers, Register (chat_ui)

## Design Decisions

- No binding design points from the orchestrator (not a critical story).
- **Filter shape**: `count_audit_logs(user_id=None, completion_id=None)` and `list_audit_logs(limit=100, user_id=None, completion_id=None)`. Build `clauses`/`params` lists of fixed strings with `?` binds, AND-combined (mirror `database.py:3440-3452`). With neither argument the SQL text must stay today's (`SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?` / `SELECT COUNT(*) AS n FROM audit_logs`), so the no-filter path is byte-identical.
- **Scoping**: `scope_user_id` is computed first, exactly as now (`admin.py:35-47`); the filter is applied after it with AND. Under `audit:read:own`, another user's `completion_id` reads as an empty list (`total: 0`), not a 403 (same rule as `/audit/actions?audit_id=`).
- **`total`** counts the filtered set (pass `completion_id` to `count_audit_logs` too), so `total` and `queries` agree. Without the filter it is unchanged.
- **Exact match** is `completion_id = ?`: no LIKE, no prefix, no normalization. Param: `Query(None, min_length=1, max_length=128)`; an empty string is a 422, not "no filter" and not `= ''`.
- **No index** on `completion_id` (PRD F7 specifies columns only; index lists are guarded in `tests/test_db.py`). Flagged under risks.
- **API field names** are the column names, appended after `usage_estimated` in `AuditQueryEntry` and in the `get_audit` kwargs: `streamed_realtime`, `reasoning_shown`, `stream_redaction_divergence` (bool, default False), `completion_id` (Optional[str], default None). Verbatim passthrough; rows before PRD-021 read false/false/false/null (D14).
- **Register field is `live`, not `streamed_realtime`.** `tests/test_register.py::test_the_row_gains_no_column` asserts `f"row.{field}" not in body` for `streamed`; `row.streamed_realtime` contains `row.streamed` and would fail it. `AuditRow.live: bool = False`, set in `to_audit_row` from `bool(log.streamed_realtime)`. The disclosure's "Streamed" field (`row.streamed`, SSE) is untouched.
- **LIVE placement**: no twelfth row child (`register.py:521` "Eleven children and no twelfth"; the test counts `_GRID` tracks == 11). Replace `_verdict_tag(row),` at `register.py:537` with a small `_verdict_cell(row)`: an `rx.box(display="flex", align_items="center", gap="0.4rem")` holding `_verdict_tag(row)` and `rx.cond(row.live, _live_tag(), rx.fragment())`. `_verdict_tag` stays as is (tests import it, `test_register.py:263,288`). Widen the verdict track `5.5rem` -> `7.5rem` in `_GRID` (`register.py:128`) and raise `_MIN_WIDTH` by the same 2rem (`71.5rem` -> `73.5rem`, `register.py:135`); update the pin `'_MIN_WIDTH = "71.5rem"'` at `tests/test_register.py:1473`. Track count stays 11.
- **LIVE look** (frontend-design, restrained): reuse `_tag` typography (`register.py:250`: display face, `TEXT_TAG`, caps, tracking) via `_tag(admin_copy.LIVE_LABEL, ink)` with an ink from the existing set (`theme.INK_UPSTREAM` suggested; no new hex, so no new contrast pair). It must not reuse a verdict's ink in a way that reads as that verdict; if `INK_UPSTREAM` reads as an error beside fault/denied rows, pick another existing ink, not a new one. No fill or accent (PRD-006 Risk 6). Give it `title`/`aria-label` `LIVE_TITLE` ("Delivered in real time") so it is not only a caps word.
- **Copy**: `LIVE_LABEL = "LIVE"`, `LIVE_TITLE` in `chat_ui/chat_ui/admin_copy.py` beside `COLUMN_PROVIDER` (`:98`), English (O1). The Register's strings live in `admin_copy.py` (PRD-020 STORY-012 did the same), not `copy.py`.
- **Disclosure** (reasoning_shown, divergence, completion_id) is out of scope: the AC asks only for the marker.

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| frontend-design (`.agents/skills/frontend-design/SKILL.md`) | The tag is a deliberate, restrained choice inside the Register's existing vocabulary, not a templated badge | Task 5 |

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Filter SQL | `app/db/database.py:3440-3459` (`list_action_decisions`) | `clauses`/`params`, fixed strings, bound values, `WHERE` only when non-empty |
| Router filter + scope | `app/routers/admin.py` `get_audit_actions` (`audit_id: Optional[int] = Query(None, ge=1)`) | FastAPI validation (422), filter after scoping |
| Passthrough | `app/routers/admin.py:90-95`, `app/models/schemas.py:294-301` | `# Verbatim passthrough (PRD-021 F7)`; defaults on the model |
| Register projection | `chat_ui/chat_ui/admin_formatting.py:326`, `admin_models.py:45-46` | one defaulted field, set in `to_audit_row` |
| Tag | `chat_ui/chat_ui/components/register.py:227-262` | `_tag(label, ink, exception=True)` |
| Tests | `tests/test_audit_router.py:440-475`, `tests/test_register.py:1449-1475` | real `TestClient` + `log_query` on `temp_db`; probe + source checks |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/database.py` | UPDATE | `count_audit_logs` (`:1857`) / `list_audit_logs` (`:1871`) gain `completion_id` |
| `app/models/schemas.py` | UPDATE | four fields on `AuditQueryEntry` after `usage_estimated` (`:301`) |
| `app/routers/admin.py` | UPDATE | `completion_id` Query param, pass to both readers, project four fields |
| `chat_ui/chat_ui/admin_models.py` | UPDATE | `AuditRow.live: bool = False` |
| `chat_ui/chat_ui/admin_formatting.py` | UPDATE | `live=bool(log.streamed_realtime)` in `to_audit_row` |
| `chat_ui/chat_ui/admin_copy.py` | UPDATE | `LIVE_LABEL`, `LIVE_TITLE` |
| `chat_ui/chat_ui/components/register.py` | UPDATE | `_live_tag`, `_verdict_cell`, grid / min-width, docstring counts |
| `tests/test_audit_router.py`, `tests/test_schemas.py` | UPDATE | shape guards + new tests |
| `tests/test_register.py`, `tests/test_admin_formatting.py`, `tests/test_admin_models.py` | UPDATE | stub, field sets, `_MIN_WIDTH`, new tests |

No file is created. No new public function in `database.py` (census guard `tests/test_db_resilience_retry.py` unaffected: same two functions, same `_unit_of_work` kinds). No `requirements.txt` change.

## Tasks

### Task 1: Readers take `completion_id`
- **File**: `app/db/database.py` (`count_audit_logs`, `list_audit_logs`)
- **Implement**: add `completion_id: Optional[str] = None` to both; clause builder; no-filter SQL unchanged; docstring cites PRD-021 F7 ("exact match, bound value, no caller text in the SQL").
- **Mirror**: `database.py:3440-3459`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_audit_router.py`

### Task 2: Schema and router
- **File**: `app/models/schemas.py`, `app/routers/admin.py` (`get_audit`)
- **Implement**: the four fields with a PRD-021 F7/D14 comment; signature `get_audit(identity=Depends(require_identity), completion_id: Optional[str] = Query(None, min_length=1, max_length=128))`; pass `completion_id=` to both readers; add the four kwargs after `usage_estimated=log.usage_estimated,`. Scoping code untouched.
- **Mirror**: `admin.py:84-96`
- **OpenAPI**: the repo pins no schema file (`app.openapi()` is generated; `tests/test_v1_tools.py:1382` pins only `QuerySuccessResponse`), so nothing to update.
- **Validate**: as Task 1.

### Task 3: Update the two shape guards
- **File**: `tests/test_audit_router.py` (`set(entry.keys()) == {...}`, ~`:78-115`), `tests/test_schemas.py` (`AuditResponse` expected dict, ~`:165-194`)
- **Implement**: add the four names with `# PRD-021 F7 (STORY-013): four additive real-time fields`; in `test_schemas.py` the defaults `False, False, False, None`. (The 9654456 guard, `test_every_log_query_call_in_the_pipeline_passes_the_route_fields`, concerns `log_query` call sites and is not touched; these two are this story's equivalents.)
- **Validate**: `tests/test_audit_router.py tests/test_schemas.py`

### Task 4: New API tests
- **File**: `tests/test_audit_router.py` (pattern `:440-475`; `log_query(..., streamed_realtime=True, reasoning_shown=True, completion_id="chatcmpl-harness-rt-aaa")`)
- Cases: fields round-trip and a plain row reads `(False, False, False, None)`; `?completion_id=` exact (seed `...-aaa`, `...-aaab`, one NULL row: asking `...-aaa` returns one row, `total == 1`; the bare prefix returns none); own scope (two users, an identity with only `audit:read:own`, copy how the file's existing scoping tests build one: asking for the other user's id gives 200, `queries == []`, `total == 0`; `audit:read:all` finds it); injection-shaped value (`x' OR '1'='1`) returns empty; `?completion_id=` empty is 422.
- **Validate**: `tests/test_audit_router.py`

### Task 5: Register LIVE marker
- **Files**: `admin_models.py`, `admin_formatting.py`, `admin_copy.py`, `components/register.py` as in Design Decisions. Verify Reflex props against the pinned package source (`chat_ui/AGENTS.md`). Update the `_row_line` / `_GRID` / `_MIN_WIDTH` comments (PRD-021 F7, STORY-013) so the "eleven" prose stays true. `row.streamed_realtime` must not appear anywhere.
- **Mirror**: `register.py:227-262`, `admin_formatting.py:326`
- **Validate**: `tests/test_register.py tests/test_admin_formatting.py tests/test_admin_models.py tests/test_chat_ui_startup_guard.py`

### Task 6: Register tests and guard updates
- `tests/test_register.py`: the log stub (~`:636-650`) gains `streamed_realtime = False`; `_MIN_WIDTH` pin (`:1473`) updated with a PRD-021 F7 comment; add a probe test that `LIVE_LABEL` renders for a `live=True` row and not for `live=False`.
- `tests/test_admin_models.py`: add `live` to the `AuditRow` field-name sets (~`:20-60`, ~`:96`) with a comment. `tests/test_admin_formatting.py`: `to_audit_row(make_log(streamed_realtime=True), NOW).live is True`, default False (`make_log` builds a real `AuditLog`, no stub change).
- Every modified existing assertion carries a PRD-021 F7 comment.

## End-to-End Tests

- [ ] `TestClient(app)` `GET /audit` (admin token): four new keys on every row; `?completion_id=<exact>` returns one row and `total == 1`.
- [ ] Own-scope identity cannot read another user's row by `completion_id` (empty, not 403).
- [ ] Register probe renders `LIVE` for a live row, nothing for a legacy row; grid still 11 tracks.
- [ ] Not verified in a real browser (narrow verdict track, 360 px): state it in the report, as STORY-012 did.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_audit_router.py tests/test_schemas.py tests/test_register.py tests/test_admin_formatting.py tests/test_admin_models.py tests/test_chat_ui_startup_guard.py tests/test_untouched_app.py
# DB readers: use -k, not all of tests/test_db.py (about 12 min)
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_db.py -k "audit_logs and (list or count)"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_admin_state.py -k audit
```
`tests/test_admin_state.py` fakes `list_audit_logs`/`count_audit_logs`; `admin_state.py:383` calls `list_audit_logs(limit=...)`, unaffected by the new keyword. Full suite: GitHub CI on push (user decision). One pytest at a time.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 four fields on each row | 2, 3, 4 | `tests/test_audit_router.py` round-trip test and key-set guard; `tests/test_schemas.py` expected dict |
| AC2 exact `completion_id`, own/all scoping | 1, 2, 4 | `tests/test_audit_router.py` exact-match, prefix-miss, own-scope, injection tests |
| AC3 `LIVE` only on `streamed_realtime=1` rows | 5, 6 | `tests/test_register.py` probe test; `tests/test_admin_formatting.py` `live` mapping |
| AC4 existing tests pass, modified assertions cite PRD-021 F7 | 3, 6 | the Validation run |

## Risks / Open Questions

- Unindexed `completion_id` lookup is a table scan on a growing table; an index is a schema change outside F7 and touches `tests/test_db.py` guards. Recommend deferring.
- The story says "as today" for scoping, but `/audit` has no filter today; the "existing parameterized path" is the `user_id = ?` branch in these readers, and the new filter composes with it (AND).
- Widening the verdict track by 2rem changes the Register layout slightly; the alternative (LIVE on a second line) would raise `ROW_H`. Chosen: widen.
