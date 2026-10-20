---
story: STORY-016
prd: PRD-013
slug: console-usage-table
title: "Admin console: Usage table"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-013-audit-and-usage-limits   # all stories commit here, no per-story branch
created: 2026-10-19
---

# Plan: Admin console: Usage table

## Summary

This story adds one table to the admin console: what each user has used **today (UTC)** against their effective token budget. **Storage:** `usage_snapshot()` in `app/db/database.py` runs one statement. It reads `usage_daily` for `date('now')`, left-joins `users` for role and overrides, and left-joins a grouped count of today's `audit_logs` rows with `limit_exceeded IS NOT NULL`. It returns raw `UsageDay` dataclasses, with no limit resolved. **Formatting:** `admin_formatting.to_usage_rows` builds an `Identity` for each row and calls `usage_limits.limits_for`, which is the same function the gate uses. It then builds pre-formatted `UsageRow`s, sorted by share used, highest first. **State:** `AdminState.load` makes a second, separate read with its own `READ_LABEL_USAGE` and its own `usage_error`. A failed usage read names itself on the Usage view and never touches `error`, so the Register and summary stay as they are. `sign_out()`'s `reset()` clears `usage_rows`/`usage_error`. **View:** a third console view, `/admin/usage`, is reached from the masthead switch (Register · Summary · Usage). It renders `components/usage.py`: a caption "Today, UTC", eight columns, and an empty state reading "No one has sent anything today." It has no chart, no meter, no colour, no history and no per-row action.

## User Story

As a platform operator
I want one table showing what each user has used today against their limit
So that I can see who is near or over a budget without querying the database

## Story Reference

- Story file: `.agents/stories/PRD-013-audit-and-usage-limits/STORY-016-console-usage-table.md`
- PRD: `.agents/PRDs/PRD-013-audit-and-usage-limits/PRD.md` (Sections 5 story 3, 6.5, 6.6, 6.10, 7 F16, 11 Surfaces, 14 Risk 6)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/db/` (models, database), `app/services/identity.py` (one public constant), `chat_ui/chat_ui/` (admin_models, admin_formatting, admin_copy, admin_state, components/usage NEW, components/admin_shell, chat_ui.py), tests |
| Story | STORY-016 |
| PRD | PRD-013 |
| Depends on | STORY-008 (✅ `162820c`), STORY-009 (✅ `13f01f6`), STORY-011 (✅ `8dc6b4d`), STORY-015 (✅ `b6085a4`) |
| Blocks | STORY-018 |
| Epic Branch | `epic/PRD-013-audit-and-usage-limits` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `frontend-design` | *"Structure is information. Structural devices, numbering, eyebrows, dividers, labels, should encode something true about the content, not decorate it."* The view is a plain table with a stated window. The share is a number in a column, with no meter, bar, sparkline or accent. Rows are ordered by share used, because order is the one structural device here and it answers the operator's question ("who is near or over"). The Used head's `title` states that order. | Task 5, Task 8 |
| `frontend-design` | *"Write from the end user's side of the screen. Name things by what people control and recognize, never by how the system is built."* The heads read "Budget", "Used" and "Denied", not `token_budget_daily`, `tokens_today` or `limit_exceeded`. The budget cell reads "unlimited", not "None" or "∞". | Task 4 |
| `frontend-design` | *"Treat failure and emptiness as moments for direction, not mood… Errors don't apologize, and they are never vague about what happened."* The empty state reads "No one has sent anything today." plus one line of direction. The fault reuses `FAULT_MESSAGE_TEMPLATE` with its own label ("Could not read the usage for today. …"). | Task 4, Task 8 |
| `frontend-design` | *"Spend your boldness in one place… keep everything around it quiet."* PRD 6.10 and Risk 6 forbid a new visual direction. The table reuses the register's head and cell treatment (`TEXT_MICRO` heads, `FONT_DATA` cells, hairline rows) and only `theme` tokens. It adds no colour for an over-budget row: "104.2%" says it. | Task 8 |
| `frontend-design` | Quality floor: *"responsive down to mobile, visible keyboard focus"*. The table has a `_MIN_WIDTH` and scrolls sideways inside `.hx-scroll`, as the register does. The new switch link is an `rx.link` with the existing focus ring. | Task 8, Task 9, E2E |

---

## Design Decisions

**D-A: a third console view, `/admin/usage` (user decision, 2026-10-19).** The table is today-scoped, and every figure on the summary sheet is all-time. Putting both on one sheet is the scope confusion PRD-006 Risk 4 warns about. `admin_shell.py` gains `ROUTE_USAGE = "/admin/usage"`, `VIEW_USAGE = "usage"`, and a third `_view_link` after Summary, rule-separated the same way. `chat_ui.py` gains `admin_usage_page()` and one `add_page(..., context={"sitemap": None})`. `/admin/usage` is not a backend path, so the Caddyfile `@backend_routes` matcher is untouched, and so is `test_route_reservations.py`'s reserved set. The masthead docstring's "two-view switch" becomes three, with a sentence on why a switch is still right for three peers.

**D-B: storage returns raw facts, and Python resolves the limits.** The story says to resolve limits in Python so the table and the gate cannot disagree. `app/db` cannot import `chat_ui`, and it must not import `app.services.usage_limits`, because that module imports `database`. So:

- `app/db/models.py`: a new frozen `UsageDay` dataclass with `user_id: str`, `role: Optional[str]` (None when there is no `users` row), `token_budget_daily: Optional[int]`, `requests_per_minute: Optional[int]`, `requests: int`, `input_tokens: int`, `output_tokens: int`, `unsplit_tokens: int` and `denied: int`. It sits beside `UsageAdmission`.
- `app/db/database.py`: `usage_snapshot() -> list[UsageDay]`.
- `chat_ui/chat_ui/admin_formatting.py`: `to_usage_rows(days: list[UsageDay]) -> list[UsageRow]` builds `Identity(user_id, role, token_budget_daily=…, requests_per_minute=…)` and calls `limits_for`.

**D-C: the one statement.**

```sql
SELECT d.user_id, u.role, u.token_budget_daily, u.requests_per_minute,
       d.requests, d.input_tokens, d.output_tokens, d.unsplit_tokens,
       COALESCE(r.denied, 0) AS denied
  FROM usage_daily AS d
  LEFT JOIN users AS u ON u.user_id = d.user_id
  LEFT JOIN (SELECT user_id, COUNT(*) AS denied
               FROM audit_logs
              WHERE limit_exceeded IS NOT NULL
                AND timestamp >= date('now')
                AND timestamp <  date('now', '+1 day')
              GROUP BY user_id) AS r ON r.user_id = d.user_id
 WHERE d.day = date('now')
 ORDER BY d.user_id
```

- `limit_exceeded IS NOT NULL` is `_BLOCKED_USAGE_LIMITS_WHERE` interpolated (`database.py:1118`), not retyped, so `/stats`, the Register verdict and this table count the same rows.
- `usage_daily` drives the query. A user with denials today necessarily has a counted attempt today, because `admit` increments before it refuses (PRD 6.5). So the left join loses nothing, except the midnight straddle covered in Risks.
- `audit_logs.timestamp` is `'%Y-%m-%dT%H:%M:%SZ'` (`audit_logger.py:8`). A lexical range against `date('now')` and `date('now','+1 day')` is correct for that format, and the comment says so. `date('now')` is the database clock, the same one `usage_daily.day` uses. SQLite evaluates `'now'` once per statement, so the three uses agree.
- No parameters at all. This sidesteps the positional-binding note on `_SUMMARY_SQL`.
- `LEFT JOIN users` keeps the break-glass `admin`, which has no `users` row. The story requires it to show role `admin`. That happens in Python (D-D), not with a SQL `COALESCE(u.role, 'admin')`, which would also label any orphan row "admin".

**D-D: break-glass role in Python, from `identity.py`'s own constant.** `identity.py:15-16` holds `_ADMIN_BREAK_GLASS_USER_ID = "admin"` and `_ADMIN_ROLE = "admin"`, both private. Add public aliases `BREAK_GLASS_USER_ID` and `BREAK_GLASS_ROLE` that bind to the same values, and do not change `resolve()`. In `to_usage_rows`, when `day.role is None and day.user_id == BREAK_GLASS_USER_ID`, the identity is `Identity(user_id, BREAK_GLASS_ROLE, break_glass=True)`. That is exactly what `resolve(ADMIN_TOKEN)` builds, so `limits_for` gives the gate's answer. Any other row with no `users` row (an orphan, not expected) shows role `VALUE_ABSENT` and resolves through `*`, because `_resolve` treats an unknown role that way. It is documented, not hidden.

**D-E: `UsageRow` columns and their formats.** All fields are plain `str`, pre-formatted (the `AuditRow` rule):

| Field | Source | Format |
|---|---|---|
| `user_id` | `day.user_id` | as is |
| `role` | D-D | as is, or `VALUE_ABSENT` |
| `requests` | `day.requests` | `format_count` |
| `input_tokens` | `day.input_tokens` | `format_count` |
| `output_tokens` | `day.output_tokens` | `format_count` |
| `budget` | `limits_for(...).token_budget_daily` | `format_count`, or `USAGE_BUDGET_UNLIMITED` ("unlimited") when None |
| `used` | `tokens_today / budget` | `format_share(tokens_today, budget)` (for example "27.8%" or "104.2%"), or `VALUE_ABSENT` when unlimited |
| `denied` | `day.denied` | `format_count` |

`tokens_today = input_tokens + output_tokens + unsplit_tokens`, the exact expression `_ADMIT_USAGE_SQL` returns as `tokens_today` (`database.py:1688`). The share therefore matches the number the gate compares against the budget. Unsplit tokens have no column of their own (scope is fixed at the PRD's eight), so Input + Output can sum to less than what Used measures. The Used head's `title` says so (Task 4), and the Risks table records it. `format_share` is reused as is: its `"{:.1f}%"` already formats over 100%, and a 0 budget is impossible (validators require ≥ 1).

The rate limit (`requests_per_minute`) is not shown. The PRD's table has no column for it, and Risk 6 fixes the scope.

**D-F: order is share used, highest first, then unlimited rows, then `user_id`.** Sorting happens in `to_usage_rows` on the numeric share before formatting. The SQL `ORDER BY d.user_id` provides the deterministic tie order, and Python's stable sort keeps it. This is the one structural statement the table makes, and the Used head's `title` names it. The table has no sort control (the story says "no history control and no per-row action", and PRD 6.10 says "no controls beyond the console's existing refresh").

**D-G: the column is "Denied", never "Refused".** `tests/test_admin_copy.py::test_exactly_one_refusal_constant_exists` allows `refus` only in `GATE_REFUSED_MESSAGE` (STORY-015 D-F). "Denied" is also the verdict word the Register shows for these same rows, and the summary's "Denied at a usage limit". The AC's word "refusals" describes the figure, not its label.

**D-H: a separate read, a separate error, and the existing record is untouched.** In `load()`:

- `_READS` and `SUMMARY_FIGURES` are **not** extended. The usage read is not a summary figure, and `len(_READS) == len(SUMMARY_FIGURES)` must keep holding.
- New declared vars, both with falsy defaults so `reset()` clears them: `usage_rows: list[UsageRow] = []` and `usage_error: str = ""`.
- In `load()`, inside the `try`, **before** the summary read: one `asyncio.to_thread(usage_snapshot)` plus `to_usage_rows(...)` in its own `try/except Exception`. On failure it sets `usage_error = LOAD_FAILED_MESSAGE.format(read=READ_LABEL_USAGE, detail=exc)` and leaves `usage_rows` as they were. On success it commits `usage_rows` and clears `usage_error` in one lock block. Execution then falls through to the summary path **unchanged**. Running first means the summary path's early `return`s cannot skip it, so a failed summary read still refreshes usage, and a failed usage read never reaches `error`.
- The opening lock block that sets `loading = True` and `error = ""` also clears `usage_error`, for symmetry with `error`.
- The two reads make two round trips per load where there was one. This is stated in the docstring. The story fixes "outside `summary_snapshot`", and F16 requires the separate label.
- New computed var `usage_state` returns `USAGE_STATE_FAULT` if `usage_error`, else `USAGE_STATE_EMPTY` if not `usage_rows`, else `USAGE_STATE_ROWS`. Error comes first, the `register_state` rule, so a first failed read is never shown as "No one has sent anything today."

**D-I: where the usage fault renders.** `admin_shell.fault_panel()` is bound to `AdminState.error`. It gains an optional parameter, `fault_panel(message=AdminState.error)`, so `usage.py` can render `fault_panel(AdminState.usage_error)` above its table. That gives one panel definition, one title ("The read failed.") and one retry (Refresh). `admin_page()` keeps calling `fault_panel()` with the default, so every page still shows a summary fault. A usage fault appears only on the Usage view, which is the only view whose content it affects. The Register and summary pages never show it, and their `register_state`/`summary_state` read `error` only, so AC 4's "summary and Register still render" holds by construction.

**D-J: read-only by construction stays true.** `admin_state` imports `usage_snapshot` by name. `admin_formatting` imports `limits_for` and `Identity`/`BREAK_GLASS_*` by name. `usage_limits.admit`/`charge` and `database.admit_usage`/`charge_usage` are not attributes of either chat module. Task 7 extends the namespace test to assert it.

---

## Patterns to Follow

### Storage read: one statement, row → dataclass
```python
# SOURCE: app/db/database.py:1700-1718 (admit_usage)
    with _session() as conn:
        row = conn.execute(_ADMIT_USAGE_SQL, (user_id,)).fetchone()
        return UsageAdmission(
            day=row["day"],
            window_start=row["window_start"],
            ...
        )
```

### Shared predicate, interpolated, never retyped
```python
# SOURCE: app/db/database.py:1118, 1137-1142
_BLOCKED_USAGE_LIMITS_WHERE = "limit_exceeded IS NOT NULL"
...
            f"SELECT COUNT(*) AS n FROM audit_logs WHERE {_BLOCKED_USAGE_LIMITS_WHERE}"
```

### Projection (named fields, pre-formatted, absent mark)
```python
# SOURCE: chat_ui/chat_ui/admin_formatting.py:123-162 (format_share, format_count, _text)
def format_count(value: Optional[int]) -> str:
    if value is None:
        return VALUE_ABSENT
    return f"{value:,}"
```

### Limit resolution (the gate's function, reused)
```python
# SOURCE: app/services/usage_limits.py:107-130 (limits_for)
    return UsageLimits(
        token_budget_daily=_resolve(identity.token_budget_daily, identity.role,
                                    settings.usage_daily_token_budget_map),
        ...
```

### Fault: names the read, commits nothing
```python
# SOURCE: chat_ui/chat_ui/admin_state.py:1143-1158
            try:
                snapshot = await asyncio.to_thread(summary_snapshot, ...)
            except Exception as exc:
                async with self:
                    self.error = LOAD_FAILED_MESSAGE.format(read=_READS[0][1], detail=exc)
                return
```

### State precedence as a Python var
```python
# SOURCE: chat_ui/chat_ui/admin_state.py:579-611 (register_state), 906-934 (summary_state)
        if self.error:
            return REGISTER_STATE_FAULT
        if not self.rows:
            return REGISTER_STATE_EMPTY
```

### Component: head cells, data cells, grid constant, empty panel, rx.match body
```python
# SOURCE: chat_ui/chat_ui/components/register.py:122-180 (_GRID, _MIN_WIDTH, _head_cell, _cell),
#         581-622 (_column_head), 1058-1098 (_empty_panel), 1141-1177 (_table, _register_body),
#         1180-1212 (register(): .hx-scroll, min_height="0")
```

### Third view link
```python
# SOURCE: chat_ui/chat_ui/components/admin_shell.py:445-466
                rx.box(
                    _view_link(VIEW_SUMMARY, admin_copy.VIEW_SUMMARY_LABEL, ROUTE_SUMMARY, active),
                    padding_left="0.75rem", margin_left="0.75rem",
                    border_left=f"1px solid {theme.RULE}",
                ),
```

### Tests
```python
# SOURCE: tests/test_usage_storage.py:46-69 (_db_clock, _insert_row: write old days directly, never sleep)
# SOURCE: tests/test_db.py:1694-1729 (_RecordingConnection, _count_statements: one-statement proof)
# SOURCE: tests/test_usage_limits.py:49-51, 97-102 (_limits / role_maps: patch settings maps)
# SOURCE: tests/test_admin_state.py:430-500 (_Reads.install: monkeypatch admin_state's reads)
# SOURCE: tests/test_admin_state.py:369-374 (namespace read-only assertion)
# SOURCE: tests/test_summary.py (colour/tint/card/literal guards to mirror for usage.py)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/models.py` | UPDATE | `UsageDay` frozen dataclass |
| `app/db/database.py` | UPDATE | `_USAGE_SNAPSHOT_SQL` + `usage_snapshot() -> list[UsageDay]` |
| `app/services/identity.py` | UPDATE | Public `BREAK_GLASS_USER_ID`, `BREAK_GLASS_ROLE` aliases (D-D); `resolve()` unchanged |
| `chat_ui/chat_ui/admin_models.py` | UPDATE | `UsageRow` projection (8 `str` fields) |
| `chat_ui/chat_ui/admin_copy.py` | UPDATE | `VIEW_USAGE_LABEL`, caption, 8 column heads + 3 titles, `USAGE_BUDGET_UNLIMITED`, empty-state title/body, `READ_LABEL_USAGE` |
| `chat_ui/chat_ui/admin_formatting.py` | UPDATE | `to_usage_rows` (identity → `limits_for` → share → sort → `UsageRow`) |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | `usage_rows`, `usage_error`, `usage_state`, `USAGE_STATE_*`; usage read in `load()` |
| `chat_ui/chat_ui/components/usage.py` | CREATE | The table view |
| `chat_ui/chat_ui/components/admin_shell.py` | UPDATE | `ROUTE_USAGE`, `VIEW_USAGE`, third switch link; `fault_panel(message=…)` |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | `admin_usage_page()` + `add_page` |
| `tests/test_usage_view.py` | CREATE | Storage, formatting, state and component tests for this story |
| `tests/test_admin_state.py` | UPDATE | `_Reads.install` stubs `usage_snapshot`; namespace test extended |
| `tests/test_admin_shell.py` | UPDATE | `EXPECTED_ROUTES`, view probes, `EXPECTED_PAGE_KEYS` + usage |
| `tests/test_admin_models.py` | UPDATE (extend) | `UsageRow` fields and types; no preview field |

---

## Tasks

Execute in order. Each task is atomic and verifiable. `PY=/c/Users/tobip/.venvs/harness-ai/Scripts/python.exe`, run from the repo root. Start the libSQL container first (`docker start harness-libsql-dev`).

### Task 0: Inventory and a green baseline

- **Action**: READ only
- **Implement**: `grep -rn -E "VIEW_SUMMARY|ROUTE_SUMMARY|EXPECTED_PAGE_KEYS|EXPECTED_ROUTES|two-view|fault_panel\(|base_vars|_ORIGINAL_READS" tests/ chat_ui/` and list every site the third view or the new vars touch. Confirm that `test_sign_out_clears_every_declared_var` iterates the declared vars generically, so it picks up `usage_rows`/`usage_error` with no edit. Read `tests/test_admin_shell.py:640-800` (pages probe) and `tests/test_render_invariants.py` around its `VIEW_SUMMARY` import to see whether either enumerates the views exhaustively.
- **Validate**: `$PY -m pytest tests/test_admin_state.py tests/test_admin_shell.py tests/test_admin_models.py tests/test_admin_copy.py tests/test_register.py tests/test_summary.py tests/test_usage_storage.py tests/test_usage_limits.py tests/test_render_invariants.py -q` is green. Record the count.

### Task 1: `UsageDay` and `usage_snapshot()`

- **Files**: `app/db/models.py`, `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  - `models.py`: `@dataclass(frozen=True) class UsageDay` after `UsageAdmission` (D-B). The docstring says it holds one user's counters for the database's current day, with raw overrides and no resolved limit (Section 6.6 resolves in Python so the table and the gate share one function), and that `role is None` means "no `users` row", which is the break-glass `admin`.
  - `database.py`, directly after `charge_usage`: the `_USAGE_SNAPSHOT_SQL` constant (D-C) with a comment block covering one statement and no parameters, the database clock, the lexical timestamp range and why it holds for `_TIMESTAMP_FORMAT`, the shared `_BLOCKED_USAGE_LIMITS_WHERE` predicate (an f-string), and why `usage_daily` drives the join. Then `def usage_snapshot() -> list[UsageDay]` maps each row by name, `with _session() as conn: return [UsageDay(...) for row in conn.execute(_USAGE_SNAPSHOT_SQL).fetchall()]`. A `StorageError` propagates, and the caller names it. Import `UsageDay` in the models import block.
- **Mirror**: `database.py:1700-1718`, `:1118`, `:1137-1142`
- **Validate**: Task 2's storage tests.

### Task 2: Storage tests (`tests/test_usage_view.py`, part 1)

- **File**: `tests/test_usage_view.py`
- **Action**: CREATE
- **Implement**: Module docstring citing STORY-016 and PRD 6.10. The `os.environ.setdefault` header from `test_usage_storage.py:9-10`. Helpers: `_db_clock()` (copied, not imported across test modules), `_insert_day(user_id, day, requests=1, input_tokens=0, output_tokens=0, unsplit_tokens=0)`, and `_audit(user_id, timestamp, limit_exceeded)` through `insert_audit_log(AuditLog(...))`. Tests, all on `temp_db`:
  1. `test_usage_snapshot_is_empty_when_nobody_sent_today`: a row for yesterday only (`date('now','-1 day')` read from the db) gives `[]`.
  2. `test_usage_snapshot_reads_todays_counters_and_overrides`: `insert_user` ana (`user`) and bob (`analyst`), `set_user_limits` on bob, then rows for both today and one for ana yesterday. The result is exactly two `UsageDay`s with the right counters, `role`, and bob's overrides. Ana's are `None`.
  3. `test_usage_snapshot_keeps_the_break_glass_admin`: `admit_usage("admin")` with no users row gives one `UsageDay(user_id="admin", role=None, …, requests=1)`.
  4. `test_usage_snapshot_counts_todays_limit_rows_only`: for ana, two audit rows today with `limit_exceeded` (`"tokens"`, `"requests"`), one today with `None`, and one yesterday with `"tokens"` (timestamp built from the db's yesterday date). `denied == 2`. A user with no audit rows gets `denied == 0` (COALESCE).
  5. `test_usage_snapshot_issues_one_statement` (AC 5): copy the `_RecordingConnection`/`_count_statements` idiom from `test_db.py:1694-1729`, seed two users, call it, and assert exactly 1 statement.
  6. `test_usage_snapshot_shares_the_stats_predicate`: assert `database._BLOCKED_USAGE_LIMITS_WHERE in database._USAGE_SNAPSHOT_SQL`.
- **Validate**: `$PY -m pytest tests/test_usage_view.py -q`

### Task 3: `UsageRow` and the identity constants

- **Files**: `chat_ui/chat_ui/admin_models.py`, `app/services/identity.py`, `tests/test_admin_models.py`
- **Action**: UPDATE
- **Implement**:
  - `admin_models.py`: `class UsageRow(pydantic.BaseModel)` after `SummaryFigure`, with eight `str = ""` fields in D-E's order. The docstring says it is a projection of `UsageDay` plus the resolved budget, that every value is pre-formatted, and that components read fields without computing. One sentence in the module docstring names the third model.
  - `identity.py`: `BREAK_GLASS_USER_ID = _ADMIN_BREAK_GLASS_USER_ID` and `BREAK_GLASS_ROLE = _ADMIN_ROLE`, with a comment that these are public for the usage view (PRD-013 STORY-016) so it names the same identity `resolve()` builds, and are not a second definition.
  - `tests/test_admin_models.py`: `USAGE_ROW_FIELDS` (exact set and order), all `str`, and no `prompt_preview`/`response_preview` (mirror the `AuditRow` guard).
- **Validate**: `$PY -m pytest tests/test_admin_models.py tests/test_identity.py -q`

### Task 4: Copy

- **File**: `chat_ui/chat_ui/admin_copy.py`
- **Action**: UPDATE
- **Implement**: Add a `# --- Usage (PRD-013 STORY-016) ---` section. None of these may contain `refus` (D-G).
  - `VIEW_USAGE_LABEL = "Usage"` beside `VIEW_SUMMARY_LABEL`.
  - `USAGE_CAPTION = "Today, UTC"`. Comment: PRD-006 Risk 4, every figure states its window.
  - Heads: `COLUMN_ROLE = "Role"`, `COLUMN_REQUESTS = "Requests"`, `COLUMN_INPUT = "Input"`, `COLUMN_OUTPUT = "Output"`, `COLUMN_BUDGET = "Budget"`, `COLUMN_USED = "Used"`, `COLUMN_DENIED = "Denied"`. "User" reuses the existing `COLUMN_USER`.
  - Head titles: `COLUMN_BUDGET_TITLE = "Tokens a day: this user's own limit where one is set, otherwise their role's"`, `COLUMN_USED_TITLE = "Share of the budget used today, counting tokens with no input/output split. Highest first."`, `COLUMN_DENIED_TITLE = "Requests denied at a usage limit today"`.
  - `USAGE_BUDGET_UNLIMITED = "unlimited"`.
  - `EMPTY_USAGE_TITLE = "No one has sent anything today."` (the AC's exact words) and `EMPTY_USAGE_BODY = "A user appears here after their first request of the day. Counts reset at 00:00 UTC; Refresh to read them again."`
  - `READ_LABEL_USAGE = "the usage for today"`, which begins with an article per the `READ_LABEL_*` rule. Its comment says it is not in `_READS`: it is a separate read (F16).
- **Validate**: `$PY -m pytest tests/test_admin_copy.py tests/test_copy.py -q`. The single-refusal and non-empty sweeps pick up the new constants.

### Task 5: `to_usage_rows`

- **File**: `chat_ui/chat_ui/admin_formatting.py`
- **Action**: UPDATE
- **Implement**: Imports by name: `from app.db.models import UsageDay`, `from app.services.identity import BREAK_GLASS_ROLE, BREAK_GLASS_USER_ID, Identity`, `from app.services.usage_limits import limits_for`, and `USAGE_BUDGET_UNLIMITED` from `.admin_copy`, `UsageRow` from `.admin_models`. Then:
  - `_usage_identity(day) -> Identity` (D-D).
  - `to_usage_rows(days: list[UsageDay]) -> list[UsageRow]`. For each day: `limits = limits_for(_usage_identity(day))`, `tokens_today = input + output + unsplit`, `budget = limits.token_budget_daily`, share key `tokens_today / budget if budget else None`. Sort with key `(share is None, -(share or 0))`, which is stable over the SQL's `user_id` order (D-F). Then build `UsageRow`s per D-E's table. The docstring states that `limits_for` is the gate's function and settings are read per call, so a reconfiguration shows on the next Refresh. It also states that `tokens_today` is `_ADMIT_USAGE_SQL`'s expression, so Used is what the gate compares.
- **Mirror**: `admin_formatting.py:123-162`, `usage_limits.py:107-130`
- **Validate**: Task 6.

### Task 6: Formatting tests (`tests/test_usage_view.py`, part 2)

- **File**: `tests/test_usage_view.py`
- **Action**: UPDATE
- **Implement**: Pure `UsageDay` fixtures with no database. Patch settings with the `_limits` idiom (`USAGE_DAILY_TOKEN_BUDGET="*=1000000,analyst=5000,admin=unlimited"`).
  1. `test_effective_budget_override_role_default_and_unlimited` (AC 2): a user with an override of 2,000,000 reads `"2,000,000"`. An analyst with no override reads `"5,000"`. The `admin` break-glass row (`role=None`) reads role `"admin"`, budget `"unlimited"` and used `VALUE_ABSENT`, and the row contains no `%` anywhere.
  2. `test_the_table_and_the_gate_agree`: for each fixture day, `to_usage_rows`' budget equals `format_count(limits_for(<the identity resolve() would build>).token_budget_daily)`. For break-glass, build it the way `resolve(settings.ADMIN_TOKEN)` does, by calling `resolve` with the test token.
  3. `test_used_counts_unsplit_tokens`: input 300, output 100, unsplit 600, budget 1,000 gives `"100.0%"`. Input and output read `"300"`/`"100"`.
  4. `test_used_over_budget_is_a_number_not_a_colour`: tokens 1,042 on a 1,000 budget give `"104.2%"`.
  5. `test_rows_are_ordered_by_share_then_unlimited_then_user`: three limited users at 10%, 90% and 90%, plus one unlimited, come out in the order 90% (lower `user_id`), 90%, 10%, unlimited.
  6. `test_an_orphan_row_shows_the_absent_role`: `role=None`, `user_id="ghost"` gives role `VALUE_ABSENT` and the `*` budget.
  7. `test_every_usage_row_field_is_a_string` and `test_zero_counts_read_zero` (`"0"`, not the absent mark).
- **Validate**: `$PY -m pytest tests/test_usage_view.py -q`

### Task 7: State

- **Files**: `chat_ui/chat_ui/admin_state.py`, `tests/test_admin_state.py`
- **Action**: UPDATE
- **Implement**:
  - Imports: `usage_snapshot` in the `app.db.database` block, `READ_LABEL_USAGE` from copy, `to_usage_rows` from formatting, `UsageRow` from models. The module docstring's "ten read functions" paragraph gains one sentence: the usage read is imported by name like the rest, and no counter write (`admit_usage`, `charge_usage`) is reachable.
  - `USAGE_STATE_FAULT = "read_failed"`, `USAGE_STATE_EMPTY = "empty"`, `USAGE_STATE_ROWS = "rows"` beside the register/summary state constants. Use the same values if those are strings shared by convention; check them first.
  - Declared vars under a `# --- Usage (PRD-013 STORY-016)` comment: `usage_rows: list[UsageRow] = []` and `usage_error: str = ""`. The comment says they are cleared by `sign_out()`'s `reset()` with no edit there (AC 4).
  - `@rx.var def usage_state(self) -> str` (D-H precedence), with the auto-dependency note.
  - `load()`, per D-H: clear `usage_error` in the opening lock. After `now = …`, add the usage block with its own `try/except Exception`. Docstring: a sixth structural property, "The usage read is separate", covering the two round trips, the separate error, why it runs before the summary read, and why `_READS` does not grow.
  - **Tests** in `tests/test_admin_state.py`. `_Reads.install` also patches `admin_state_mod.usage_snapshot` with a recorder returning `self.usage` (a new keyword, default `[]`), so no existing load test reaches the database for usage. Existing assertions stay unedited. Extend `test_admin_state_has_no_write_path_to_the_audit_log` (or add a sibling) to assert that `admit_usage`, `charge_usage`, `admit` and `charge` are not attributes of `admin_state` or `admin_formatting`.
  - **New tests** in `tests/test_usage_view.py`, part 3, driving `load()` the way `test_admin_state.py` does. Reuse its `_Reads` by import if it is importable, or a minimal local equivalent.
    1. `test_load_commits_usage_rows` (AC 1): the stub returns two `UsageDay`s, `state.usage_rows` holds two `UsageRow`s, and `usage_state == USAGE_STATE_ROWS`.
    2. `test_empty_day_is_the_empty_state` (AC 3): `[]` gives `USAGE_STATE_EMPTY`.
    3. `test_a_failed_usage_read_names_itself_and_leaves_the_record` (AC 4): a good load, then a stub that raises `StorageError("boom")`. `READ_LABEL_USAGE in state.usage_error`, `state.error == ""`, `register_state`/`summary_state` are not fault, the rows and figures equal the first load's, `usage_rows` equals the first load's, and `usage_state == USAGE_STATE_FAULT`.
    4. `test_a_failed_summary_read_still_refreshes_usage`: the summary snapshot raises and the usage stub returns rows. Then `error` is set, `usage_error == ""` and `usage_rows` are committed.
    5. `test_a_first_failed_usage_read_is_not_shown_as_empty`: `usage_state == USAGE_STATE_FAULT` with `usage_rows == []`.
    6. `test_sign_out_clears_the_usage_rows` (AC 4): load, `sign_out()`, then `usage_rows == []` and `usage_error == ""`.
    7. `test_an_unauthenticated_load_reads_no_usage`: the usage stub records zero calls (PRD-006 Risk 1).
    8. `test_usage_is_not_a_summary_read`: `"usage" not in {f for f, *_ in _READS}` and `len(_READS) == len(SUMMARY_FIGURES)`.
- **Mirror**: `admin_state.py:579-611`, `:1070-1189`, `tests/test_admin_state.py:430-500`
- **Validate**: `$PY -m pytest tests/test_admin_state.py tests/test_usage_view.py -q`

### Task 8: The component

- **File**: `chat_ui/chat_ui/components/usage.py`
- **Action**: CREATE
- **Implement**: The module docstring follows `summary.py`'s structure. It covers what the view refuses (meters, sparklines, accent colours, charts and history, quoting the `frontend-design` "Structure is information" rule from the story), that it reads fields and does not compute, that its states are chosen upstream (`usage_state`), and its imports (`admin_copy`, `theme`, `AdminState`, `admin_shell.refreshed_stamp`/`fault_panel`) with nothing from the chat or from `register.py`/`summary.py`. Views do not reach into each other, so `_head_cell`/`_cell`/`_empty_panel` are re-declared here, as `summary.py` re-declares its empty panel.
  - `_GRID`: eight tracks, `"minmax(8rem, 1fr) 6rem 6rem 7rem 7rem 8rem 5rem 5rem"` (User, Role, Requests, Input, Output, Budget, Used, Denied), with a comment giving the widest expected value per numeric track ("999,999,999" in the data face at `TEXT_DATA` for Input/Output, "unlimited"/"10,000,000" for Budget, "104.2%" for Used). Measure live in Task 9 and adjust as STORY-015 did. `_MIN_WIDTH` is the sum of the tracks plus 7 × 0.75rem gaps, with the arithmetic in the comment.
  - `_caption()`: `USAGE_CAPTION` in `FONT_BODY` `TEXT_DATA` `MUTE`, then `refreshed_stamp()`, the register's scope-column order. The table box carries `custom_attrs={"role": "table", "aria-label": admin_copy.USAGE_CAPTION}`, so the window is in the accessible name as well as on screen.
  - `_column_head()`: sticky, `PAPER` background, a full `RULE` bottom border and the `role="row"` attrs, as in `register.py:581-622`. Numeric heads are right-aligned. Budget, Used and Denied carry their `title`s.
  - `_row(row)`: eight `_cell`s, numeric cells right-aligned, user and role in `INK`, a hairline `RULE` bottom border, and no hover fill, no click and no disclosure (AC 5: no per-row action).
  - `_table()`, `_empty_usage()`, `_usage_body()` (`rx.match` over `usage_state`: empty gives the empty panel, fault and rows give the table, and the default is the table, the register's direction).
  - `usage()`: `rx.vstack(fault_panel(AdminState.usage_error), <caption strip>, rx.box(_usage_body(), class_name="hx-scroll", overflow_x="auto", overflow_y="auto", flex="1", min_height="0", padding_left="1.5rem"), …)`.
- **Also** `admin_shell.py`: `fault_panel(message=AdminState.error)` (D-I). The docstring gains a paragraph: the parameter exists for the Usage view's separate read, and the default keeps every existing call site unchanged. Add `ROUTE_USAGE`, `VIEW_USAGE`, and the third `_view_link` in the switch (D-A), and update the module and masthead docstrings from "two views" to three.
- **Also** `chat_ui.py`: `def admin_usage_page(): return admin_page(usage(), VIEW_USAGE)` and `app.add_page(admin_usage_page, route=ROUTE_USAGE, context={"sitemap": None})`. Update the "two views" comment above them.
- **Tests** in `tests/test_usage_view.py`, part 4, mirroring `tests/test_summary.py`'s render and source guards:
  1. `test_usage_renders_every_column_head_and_the_caption`: render `usage()` to string. All eight head constants and `USAGE_CAPTION` are present, and the three titles are present.
  2. `test_the_empty_state_says_no_one_has_sent_anything_today`: `EMPTY_USAGE_TITLE` is in the render, inside the `rx.match` empty arm.
  3. `test_no_chart_no_history_no_row_action` (AC 5): the source of `usage.py` contains none of `rx.recharts`, `chart`, `sparkline`, `progress`, `on_click`, `rx.el.button`, `rx.select`, `date_picker` or `history` (case-insensitive, outside the docstring; strip it with `ast.get_docstring`/`ast` as `test_summary.py`'s literal guard does). `AdminState` has no event handler mentioning `usage` other than `load`/`sign_out`.
  4. `test_only_theme_colours`: mirror `test_summary.py`'s colour/tint/card guard. No hex literal, no `rgb(`, no `background_color` other than `theme.PAPER`, no `box_shadow` and no `border_radius` on rows.
  5. `test_usage_imports_nothing_from_the_chat_or_the_other_views`: the source-import check from `test_admin_shell.py:454`.
  6. In `tests/test_admin_shell.py`: `EXPECTED_ROUTES` gains `"ROUTE_USAGE": "/admin/usage"`, the probe dict gains the usage route and view, the masthead probes add `admin_masthead(usage)`/`admin_page(usage)`, and the pages probe's `EXPECTED_PAGE_KEYS` gains the usage route. Add a test that the three view keys are distinct. Each edited assertion carries a `# PRD-013 (STORY-016)` comment.
- **Mirror**: `register.py:122-180, 581-622, 1058-1212`, `summary.py:287-460`, `admin_shell.py:340-466, 580-616`
- **Validate**: `$PY -m pytest tests/test_usage_view.py tests/test_admin_shell.py tests/test_summary.py tests/test_register.py tests/test_render_invariants.py tests/test_admin_palette.py tests/test_contrast.py -q`

### Task 9: Full suite and regression gates

- **Action**: RUN
- **Validate**: `$PY -m pytest tests/ -q`. If fixture errors appear across the suite, restart the libSQL container rather than bisecting. `tests/test_chat_sessions.py` has a known intermittent flake (PRE-PRD-017), so rerun it before blaming the change. `git diff --stat` must show no change to `test_query_outcomes_regression.py`, `test_chat_outcomes_regression.py`, `test_duplicate_scope.py`, `test_pii_characterization.py` or `test_untouched_app.py`. `git diff tests/test_register.py tests/test_summary.py` is empty.

### Task 10: E2E in the running console

- **Action**: RUN (see End-to-End Tests). Revert `chat_ui/reflex.lock/package.json` and delete the `chat_ui/package-lock.json` changes that `reflex run` produces before committing.

### Task 11: Commit, report, story status

- **Action**: Commit on `epic/PRD-013-audit-and-usage-limits` as `feat(admin-console): STORY-016 usage table`. Write the report like the earlier PRD-013 stories. Flag D-A (third view) and D-F (share order) for the reviewer. Set the story's `report` and `commit`, set `status: done`, move this plan to `completed/`, and regenerate the index.

---

## End-to-End Tests

Seed through the real writers. A live send cannot be answered here (OpenRouter TLS/401). From the repo root, with `.env` sourced, use `PYTHONPATH=. $PY`:

- `insert_user(User("e2e-ana", "user", "h-e2e-ana"))` and `insert_user(User("e2e-bob", "user", "h-e2e-bob"))`, then `set_user_limits("e2e-bob", token_budget_daily=5000)`.
- `admit_usage("e2e-ana")` ×3, then `charge_usage("e2e-ana", day, 2140, 312, 0)`.
- `admit_usage("e2e-bob")`, then `charge_usage("e2e-bob", day, 0, 0, 5210)`, which puts bob over budget with unsplit tokens only.
- `admit_usage("admin")` (break-glass).
- `insert_audit_log(AuditLog(user_id="e2e-bob", success=True, limit_exceeded="tokens", …))` ×2, with a current timestamp.

Then `cd chat_ui && set -a; . ../.env; set +a; reflex.exe run --env prod`, open `http://localhost:3000/admin`, and sign in with `ADMIN_TOKEN`.

- [ ] The masthead reads Register · Summary · Usage. Usage navigates to `/admin/usage` and carries `aria-current` there. Keyboard Tab reaches it with a visible focus ring.
- [ ] The caption reads "Today, UTC" above the table, with the Refreshed stamp.
- [ ] Rows appear in this order: e2e-bob first (Budget `5,000`, Used `104.2%`, Input `0`, Output `0`, Denied `2`), then e2e-ana (role `user`, Requests `3`, Input `2,140`, Output `312`, Budget = the `*` value, Used = its share, Denied `0`), then admin (role `admin`, Budget per the `admin`/`*` entry, or `unlimited` with Used `—` if configured so). Hovering Used shows the "counting tokens with no input/output split. Highest first." title.
- [ ] Each budget agrees with `PYTHONPATH=. $PY -c "from app.services.usage_limits import limits_for; ..."` for the same identities.
- [ ] No colour, bar or meter marks the over-budget row, and no row responds to click or hover.
- [ ] Empty day: clean up the seeded rows (below) and Refresh. The page reads "No one has sent anything today." with its direction line, and no empty grid.
- [ ] Usage fault: stop the libSQL container and Refresh on `/admin/usage`. The usage fault panel reads "Could not read the usage for today. …" and the summary's own panel appears too, since both reads failed. Restart, open `/admin/audit` with the summary fault cleared, then stop the container again. **Optional:** AC 4's isolated arm (usage fails, summary succeeds) is proved by Task 7 #3, because one database cannot fail one statement and not the other live.
- [ ] Sign out, sign back in: the usage rows come back only after the load, and nothing is visible before it.
- [ ] Narrow to 390px: the table scrolls sideways inside its container with no page scroll, and the masthead wraps.
- [ ] Both grounds (light and dark): legibility check only. The table uses only existing ink.

Cleanup: `DELETE FROM usage_daily WHERE user_id IN ('e2e-ana','e2e-bob','admin') AND day = date('now')`, `DELETE FROM audit_logs WHERE user_id LIKE 'e2e-%'` and `DELETE FROM users WHERE user_id LIKE 'e2e-%'`. Check first that no real `admin` usage row exists today on the dev database before deleting it.

---

## Validation

```bash
PY=/c/Users/tobip/.venvs/harness-ai/Scripts/python.exe
docker start harness-libsql-dev
$PY -m pytest tests/test_usage_view.py tests/test_admin_state.py tests/test_admin_shell.py tests/test_admin_models.py tests/test_admin_copy.py tests/test_usage_storage.py tests/test_usage_limits.py -q
$PY -m pytest tests/ -q
git diff --stat tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py tests/test_register.py tests/test_summary.py   # must be empty
```

---

## Risks

| Risk | Mitigation |
|------|------------|
| `audit_logs.timestamp` is the instance's clock and `usage_daily.day` is the database's, so a request near 00:00 UTC under clock skew counts its denial on a different day from its attempt | Bounded to seconds around midnight. Documented in the SQL comment. Both sides of the filter use the database's `date('now')`, so the window itself is one day |
| A request admitted at 23:59:59 that is denied after midnight has its audit row "today" and its counter row "yesterday", so it is dropped by the inner join on `usage_daily` | It is one denial per straddle and the same property PRD 6.5 accepts for the charge. Noted in the SQL comment |
| Input + Output < what Used measures when unsplit tokens exist | Intentional: Used must equal the gate's `tokens_today`. The Used head's `title` says so. A separate "Unsplit" column is out of scope (Risk 6) |
| `to_usage_rows` imports `app.services.usage_limits`, which imports the counter writers | Name imports only. Task 7 asserts the writers are not attributes of `admin_state`/`admin_formatting` |
| A second round trip per console load (PRD-007 measured one) | Required by the story ("outside `summary_snapshot`") and F16's separate label. It is one primary-key-ranged statement. Stated in `load()`'s docstring |
| A real `users` row with `user_id = "admin"` merges with break-glass counters | Pre-existing (the counters are keyed by `user_id`). The users row's role wins, which is what its gate resolves for that token. Noted, not fixed |
| `audit_logs` has no index on `timestamp`/`limit_exceeded`, so the grouped count scans | Same cost class as `count_blocked_usage_limits()` on `/stats`. An index is Section 13 material if the measurement in STORY-017 shows it matters |
| A third view widens the masthead at narrow widths | The masthead already wraps (`flex_wrap="wrap"`, `hx-header-meta`). E2E checks 390px |
| Scope creep (PRD Risk 6) | One table, today only, no sort control, no history, no per-row action, no chart. AC 5 is asserted against the source |

---

## Acceptance Criteria

(Copied from story `STORY-016`)

- [ ] Given users who sent requests today, when the console loads, then the Usage table shows one row per such user with user, role, requests, input tokens, output tokens, budget, share of budget used and refusals today, and its caption states the window ("Today, UTC").
- [ ] Given a user with a per-user override, a user on the role default and a user whose budget is `unlimited`, when the table renders, then each shows its effective budget, and the unlimited row shows no share.
- [ ] Given nobody has sent anything today, when the table renders, then it shows "No one has sent anything today." and no empty grid.
- [ ] Given the usage read failing, when the console loads, then the failure is named under its own read label and the summary and Register still render; given `sign_out()`, then the usage rows are cleared.
- [ ] Given `usage_snapshot()`, when it is called, then it issues one statement, and the component contains no chart, no history control and no per-row action.
- [ ] All tasks completed
- [ ] Full suite green; no assertion changed in the regression files listed in Task 9
- [ ] Follows existing patterns (register table treatment, `READ_LABEL_*` fault, pre-formatted projection)
