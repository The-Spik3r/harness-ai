---
story: STORY-019
prd: PRD-016
slug: admin-console-actions-view
title: "Admin console: the Actions view - recent decisions, deny first, filterable"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-016-action-policy-rules
created: 2026-11-15
---

# Plan: Admin console: the Actions view

## Summary

Add a fourth console view, **Actions**, at `/admin/actions`, as a sibling of Register, Summary and Usage. It follows the Usage view (PRD-013 STORY-016) almost line for line: its own read inside `AdminState.load()`, its own fault label (`actions_error`), its own computed `actions_state`, a `pydantic` row model with pre-formatted strings, a `components/actions.py` that re-declares the table helpers (views do not import each other), copy in `admin_copy.py`, and a fourth rule-separated link in the masthead switch. The one structural difference from Usage: it has a single-select filter (Denied, Flagged, Allowed, All; default Denied) and that filter **re-reads** the database for the chosen decision, because the 500-row window of "all" can hide every old deny, and deny is the row the view exists to find. The data comes from `list_action_decisions` and `count_action_decisions` (the same functions `GET /audit/actions` and `/stats` use), imported by name into `admin_state.py`. No API call, no write path.

## User Story

As a security admin
I want an Actions view in the admin console that shows what agents tried to do and what the policy decided
So that I can find denied actions and measure flagged classes without querying the API

## Story Reference

- Story file: `.agents/stories/PRD-016-action-policy-rules/STORY-019-admin-console-actions-view.md`
- PRD: `.agents/PRDs/PRD-016-action-policy-rules/PRD.md` (F11 line 512-513; Section 11 line 667; layout list line 446-448, 759)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/` admin console only (state, row model, formatting, copy, one component, shell, route); `theme.py` untouched unless the E2E at 390px demands it; tests |
| Story | STORY-019 |
| PRD | PRD-016 |
| Epic Branch | `epic/PRD-016-action-policy-rules` (commit directly) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| frontend-design (`.agents/skills/frontend-design/SKILL.md`, read in full) | "Build with the brief's real content and subject matter throughout": E2E and the screenshot pass seed real decisions by running corpus tool calls through `action_policy.evaluate` and `action_audit.record`, never placeholder rows. "Where the brief pins down a visual direction, follow it exactly": the existing shell/theme is the direction, so no new palette, faces or CSS beyond what the table needs. "Structure is information": no numbering, no decorative stamp margin; the decision tag carries the weight. "Name things by what people control": filter chips say Denied / Flagged / Allowed / All; column heads are plain words. "Treat failure and emptiness as moments for direction": the empty state says what the view will contain, why it is empty (PRD-017), and the action (Refresh). "Quality floor": responsive to 390px, visible focus (global `:focus-visible`), reduced motion (no new motion). The skill's "take one aesthetic risk" and token-brainstorm process are bounded by PRD Section 15 ("bounded here by the existing admin shell and theme"): the plan states the token choice below and spends no boldness. | Tasks 3, 4, 5, 10 |

Design statement (the skill's token pass, kept to what this story may decide): Colour = existing ground tokens plus the register's own three verdict inks, `INK_DENIED` (deny), `INK_HELD` (flag), `INK_CLEAR` (allow), exactly the mapping the Register uses for denied/held/cleared. Type = `FONT_DISPLAY` heads and tags, `FONT_DATA` cells, `FONT_BODY` only for the one scope line. Layout = the Usage layout: scope caption + stamp, filter strip, scrolling table. Signature = none added; the Register's stamp margin stays the console's one signature (a second mark here would be the "same shape on something that is not a row" that `admin_shell.fault_panel`'s docstring refuses). Critique pass: a first idea (stamp margin on every row, per-rule colour, sparkline of denies per day) was cut: each repeats the decision tag or decorates.

---

## Patterns to Follow

### Naming (view constants, route, page)
```python
# SOURCE: chat_ui/chat_ui/components/admin_shell.py:58-72
ROUTE_REGISTER = "/admin/audit"
ROUTE_SUMMARY = "/admin/stats"
ROUTE_USAGE = "/admin/usage"
VIEW_REGISTER = "register"
VIEW_SUMMARY = "summary"
VIEW_USAGE = "usage"
```
```python
# SOURCE: chat_ui/chat_ui/chat_ui.py:103-105, 168-172
def admin_usage_page() -> rx.Component:
    return admin_page(usage(), VIEW_USAGE)
app.add_page(admin_usage_page, route=ROUTE_USAGE, context={"sitemap": None})
```

### The fourth switch link and its phone-width behaviour
```python
# SOURCE: chat_ui/chat_ui/components/admin_shell.py:481-492
rx.box(
    _view_link(VIEW_USAGE, admin_copy.VIEW_USAGE_LABEL, ROUTE_USAGE, active),
    padding_left="0.75rem", margin_left="0.75rem",
    border_left=f"1px solid {theme.RULE}",
),
```
`hx-view-switch` (admin_shell.py:499) already takes a row of its own at <=40rem (`theme.py:437-445`); a fourth word (~270px total) still fits 390px minus gutters, to be re-measured in the E2E.

### State: separate read, own fault, computed state, falsy defaults
```python
# SOURCE: chat_ui/chat_ui/admin_state.py:196-203, 529-530, 963-984, 1204-1217
USAGE_STATE_FAULT = "read_failed"; USAGE_STATE_EMPTY = "nobody_today"; USAGE_STATE_ROWS = "rows"
usage_rows: list[UsageRow] = []
usage_error: str = ""
@rx.var
def usage_state(self) -> str:          # error tested FIRST, so a failed first read is never "empty"
    if self.usage_error: return USAGE_STATE_FAULT
    if not self.usage_rows: return USAGE_STATE_EMPTY
    return USAGE_STATE_ROWS
...
try:
    usage_rows = to_usage_rows(await asyncio.to_thread(usage_snapshot))
except Exception as exc:
    async with self:
        self.usage_error = LOAD_FAILED_MESSAGE.format(read=READ_LABEL_USAGE, detail=exc)
else:
    async with self:
        self.usage_rows = usage_rows; self.usage_error = ""
```
Every declared var must default falsy (`tests/test_admin_state.py:328-333`, `sign_out()` is `reset()`), so the filter var is `actions_filter: str = ""` where `""` means the default, Denied.

### Read-only imports by name
```python
# SOURCE: chat_ui/chat_ui/admin_state.py:38-60  (named imports, never `from app.db import database`)
from app.db.database import (count_audit_logs, ..., usage_snapshot, top_users as read_top_users)
```
Add `list_action_decisions` and `count_action_decisions` the same way. `tests/test_admin_state.py:358-374` asserts the write paths are absent from the module namespace; `insert_action_decisions` must stay out.

### Row model is a projection that omits what must not reach the screen
```python
# SOURCE: chat_ui/chat_ui/admin_models.py:1-25, 93-110
class UsageRow(pydantic.BaseModel):   # every field a pre-formatted str; no Python control flow at render
    user_id: str = ""
```
`ActionRow` mirrors this and, like `AuditRow` (no preview fields; `tests/test_admin_models.py` pins it), has **no** `arguments_preview`, `arguments_hash`, `session_id` or `classifications` field. `ActionDecisionRow` (`app/db/models.py:578-605`) carries the first three; they are storage aids (same reasoning as `ActionDecisionEntry`, `app/models/schemas.py:263-292`).

### Formatting: shared helpers, absent mark, relative + absolute time
```python
# SOURCE: chat_ui/chat_ui/admin_formatting.py:171 (_text), 233-247 (_format_timestamps), 331-371 (to_usage_rows)
relative, absolute = _format_timestamps(row.timestamp, now)
```

### Component: re-declared head/cell helpers, role=table, fixed GRID, own scroll container
```python
# SOURCE: chat_ui/chat_ui/components/usage.py:69-74, 77-113, 179-189, 256-277
_GRID = "minmax(8rem, 16rem) 6rem ..."; _MIN_WIDTH = "56.75rem"
custom_attrs={"role": "table", "aria-label": admin_copy.USAGE_CAPTION}
rx.box(_usage_body(), class_name="hx-scroll", overflow_y="auto", overflow_x="auto", flex="1", min_height="0", width="100%", padding_left="1.5rem")
fault_panel(AdminState.usage_error)   # one panel definition, one retry for the console
rx.match(AdminState.usage_state, (EMPTY, _empty_usage()), (FAULT, _table()), (ROWS, _table()), _table())  # default arm renders the record
```

### Filter control and decision tag (re-declare, do not import register.py)
```python
# SOURCE: chat_ui/chat_ui/components/register.py:181-190, 242-258 (_tag), 663-698 (_control_label/_control_button), 704-761 (_chip_button: aria-pressed, ink as text + 2px underline, no fill)
_control_button(label, on_click=..., color=ink if selected else theme.MUTE, weight=..., attrs={"aria-pressed": ...}, border_bottom=...)
```
Real `<button type="button">`, so keyboard focus and Enter/Space come free and the global `:focus-visible` ring (theme.py:291, `tests/test_admin_shell.py:889-920`) shows. No local `outline`/`tabindex` (guarded for every admin module).

### Redaction / role masking (checked)
No per-role masking exists in the console. The only boundary is the projection (no previews in `AuditRow`, `admin_models.py:1-25`), and `get_audit_actions` states "a row filter only, with no per-role masking, as on `GET /audit`" (`app/routers/admin.py:109-121`). Previews and targets are already redacted at write (`app/services/action_audit.py:19-37`). The view therefore renders `target_preview` as stored and masks nothing further.

### RBAC / gate (checked, deviation from AC 1 wording)
The console has no RBAC. `AdminState.authenticate()` (`admin_state.py:1070-1104`) compares `ADMIN_TOKEN`; `load()` returns before reading anything unless `authenticated` (twice, `admin_state.py:1184-1195`); `admin_page()` is the render gate (`admin_shell.py:568-607`). A token holder reads every row in-process (no `user_id` scope), which is the behaviour of `audit:read:all`. Story AC 1's "admin with `audit:read:all`" is satisfied in substance; no permission check is added or possible here (there is no `Identity` on the console). Flagged for the orchestrator.

### Tests
```python
# SOURCE: tests/test_usage_view.py:396-468 (_Console fake: monkeypatch settings + admin_state_mod.summary_snapshot/usage_snapshot), 470-600 (state tests via asyncio.run(type(state).event_handlers["load"].fn(state))), 695-735 (subprocess probe, cwd chat_ui/, PYTHONPATH=chat_ui;repo), 836-888 (copy-not-literal, imports, scroll-container, hx-view-switch source asserts)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/components/actions.py` | CREATE | The Actions view: caption/scope, filter strip, table, empty arm, fault panel |
| `chat_ui/chat_ui/admin_models.py` | UPDATE | `ActionRow` projection (append; docstring mention) |
| `chat_ui/chat_ui/admin_formatting.py` | UPDATE | `DECISION_*` keys, `to_action_rows()` (module docstring gains one sentence) |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | named read imports, `ACTIONS_ROW_LIMIT`, filter/state constants, vars, `actions_state`/`actions_scope`/`actions_empty_title`, `choose_actions_filter`, `load_actions`, read inside `load()` |
| `chat_ui/chat_ui/admin_copy.py` | UPDATE | view label, column heads/titles, filter labels, scope template, empty copy, `READ_LABEL_ACTIONS` |
| `chat_ui/chat_ui/components/admin_shell.py` | UPDATE | `ROUTE_ACTIONS`, `VIEW_ACTIONS`, fourth `_view_link`; docstring "three peers" -> four |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | `admin_actions_page()` + one `add_page` (sitemap None); import the two constants and `actions` |
| `tests/test_actions_view.py` | CREATE | Layers: formatting, state, component probe, source guards (the Usage-view test's shape) |
| `tests/test_admin_shell.py` | UPDATE (pinned sets) | `EXPECTED_ROUTES`, `EXPECTED_PAGE_KEYS`, `CONSOLE_PAGE_KEYS`, `len(views)==3` -> 4, probe script gets the fourth masthead/page; each edit commented citing PRD-016 STORY-019 |
| `tests/test_admin_palette.py` | UPDATE | add `components/actions.py` to `ADMIN_MODULE_PATTERNS` (hex guard covers it) |
| `tests/test_admin_shell.py` | UPDATE (module globs) | add `components/actions.py` to its `ADMIN_MODULE_PATTERNS` so the focus-ring, width-pin and no-auto-refresh guards cover the new module (Task 6) |
| `tests/test_copy.py` | UPDATE (literal set) | the `dir(admin_copy)` census list near line 440-480 gains the new names, comment citing PRD-016 |
| `tests/test_admin_state.py` | UPDATE (fixture only) | autouse `_no_actions_read` beside `_no_usage_read` (line 398) so existing `load()` tests do not reach a database; no assertion changed |
| `tests/test_usage_view.py` | UPDATE (fixture only) | `_Console` also stubs the actions reads, same reason |
| `.agents/stories/.../STORY-019-*.md`, `.agents/PRDs/.../index.md` | UPDATE | frontmatter + board (done in this plan phase) |

`app/`, `Caddyfile`, `theme.py`: no change expected. `/admin/*` already falls through Caddy's static matcher (`tests/test_caddyfile_routes.py:57` lists `/admin/usage`; the planner confirms `/admin/actions` needs no matcher change and `tests/test_caddyfile_routes.py` is left untouched (pre-existing); the new test file asserts the route is not a backend path).

---

## Design decisions

**D-A. The filter re-reads the database (per-decision), it does not filter 500 loaded rows.** The Register filters in memory because its window is every verdict. Here `ORDER BY id DESC LIMIT 500` over all decisions would drop old denies behind newer allows the moment PRD-017 produces volume, which defeats "deny first". So the selected key maps to `decision=` for `list_action_decisions` (`None` for All). `app/db/database.py:2311-2343` already takes `decision`. This departs from PRD-006 Section 6's "filtering never re-reads the database", which is the Register's rule, not this view's; documented in the `actions_filter` comment.

**D-B. Two read paths, one helper.** `load()` (Refresh, sign-in) reads actions inside its own `try/except` right after usage, with its own `actions_error`, so a summary fault never skips it and vice versa. A second background event `load_actions` (own double auth check, own `loading`-independent guard) serves the filter chips: `choose_actions_filter(key)` is a plain event that validates the key against `ACTIONS_FILTERS`, sets `actions_filter` and returns `AdminState.load_actions` (background events cannot be called, only returned/yielded; same rule as `authenticate()` returning `AdminState.load`, `admin_state.py:1099-1104`). Both use one module-level sync function `read_actions(decision)` returning `(rows, counts)` that runs in `asyncio.to_thread`. After the read, `load_actions` commits only if `self.actions_filter` still equals the filter it read (a second click in flight wins), and never touches `loading`/`error`/the register.

**D-C. Counts for a stated scope.** `read_actions` also calls `count_action_decisions()` (one more cheap statement) so the scope line can say "500 most recent of 1,204 denied" (`REGISTER_SCOPE_TEMPLATE` precedent; PRD-006 Risk 4: every figure states its window). Counts are stored as three ints `actions_denied/actions_flagged/actions_allowed = 0` mirroring the `/stats` field names and the summary's int vars (`admin_state.py:505-523`). `actions_scope` computed var formats the sentence in Python (components cannot).

**D-D. "All" is newest-first, not deny-first.** "Deny first" is the default filter. Re-sorting All by decision would break the `LIMIT` meaning (which 500). Stated in the scope copy by being plain ("most recent").

**D-E. Full text availability = `title` attribute on truncated cells** (target, rule, tool). Same device the Usage heads use for their one-line explanations. A row disclosure (the Register's `open_rows` mechanism) was considered and cut as extra state and scope; touch devices have no hover, so this is the known limitation: raised as Open Question 2. The `reason` (stored text) is the `title` of the Rule cell, so an admin can read why without a sixth column.

**D-F. No permission-based UI gating / masking** (see "RBAC / gate" above).

**D-G. Empty copy is explicit about PRD-017**, as the AC requires, which makes its body time-bound: PRD-017 should revise `EMPTY_ACTIONS_BODY`. The empty state is chosen by `actions_state` (fault first, then empty). The title names the active filter ("No denied actions recorded.") via a computed var `actions_empty_title`.

---

## Tasks

Execute in order. Each task is atomic + verifiable. Reflex rules (chat_ui/AGENTS.md): the reflex skills are not installed in the planner's session; the implementer should read the installed Reflex 0.9.6.post1 behaviour from existing code, not from memory (the existing modules are the reference), and must not start `reflex run` until the E2E task.

### Task 1: Copy
- **File**: `chat_ui/chat_ui/admin_copy.py`
- **Action**: UPDATE (new section `# --- Actions (PRD-016 STORY-019) ---` after Usage, before "Filter and sort controls", line ~283)
- **Implement** (all plain `str` constants; `tests/test_admin_copy.py:62-83` requires every public constant to be a non-empty `str`, so no tuples or dicts):
  - `VIEW_ACTIONS_LABEL = "Actions"`
  - `READ_LABEL_ACTIONS = "the action decisions"` (formatted into `FAULT_MESSAGE_TEMPLATE`, line 159-193 shows the pattern; check the sentence reads "Could not read the action decisions...")
  - `ACTIONS_FILTER_LABEL = "Show"` (eyebrow over the chips), `ACTIONS_FILTER_DENIED_LABEL = "Denied"`, `..._FLAGGED_LABEL = "Flagged"`, `..._ALLOWED_LABEL = "Allowed"`, `..._ALL_LABEL = "All"`
  - Column heads: `COLUMN_TOOL = "Tool"`, `COLUMN_OPERATION = "Operation"`, `COLUMN_TARGET = "Target"`, `COLUMN_RULE = "Rule"`, `COLUMN_DECISION = "Decision"`, `COLUMN_ALLOWED_BY = "Allowed by"` (the permission that lifted it; PRD line 102 says "the permission that lifted it"), plus `COLUMN_TIME`/`COLUMN_USER`/`COLUMN_ROLE` already exist (reuse). Titles: `COLUMN_RULE_TITLE` (the hover on a rule cell says "Hover a rule for the reason it gave" is NOT needed; keep titles only where a head needs them: Operation, Allowed by -> "The permission that lets this role through the rule. Empty when the decision did not depend on one.").
  - Decision words (for tags and rows): `DECISION_DENY_LABEL = "denied"`, `DECISION_FLAG_LABEL = "flagged"`, `DECISION_ALLOW_LABEL = "allowed"` lowercase with caps applied by `text_transform` for exceptions, exactly as `VERDICT_*_LABEL` do (register `_tag`). The chip labels above are the sentence-case controls; the lowercase pair feeds the empty-title sentence and the scope line.
  - `ACTIONS_SCOPE_TEMPLATE = "{shown} most recent of {total} {decision}"` (shown = rows loaded, total = that decision's count; for All the word is `ACTIONS_SCOPE_ALL = "recorded"`... keep to two constants).
  - `EMPTY_ACTIONS_TITLE_TEMPLATE = "No {decision} actions recorded."`, `EMPTY_ACTIONS_ALL_TITLE = "No actions recorded."`
  - `EMPTY_ACTIONS_BODY = "This view lists what agents tried to do and what the action policy decided, denied first. It is empty because nothing calls the policy engine yet: decisions start to appear when PRD-017 connects it. Refresh to read again."` Must not contain "sorry/apolog/please try" (`tests/test_admin_shell.py` apology guard) nor the word family "refus" (`tests/test_admin_copy.py:191` exactly one refusal constant).
- **Mirror**: `admin_copy.py:238-281` (Usage block) and its comment style (cite PRD-016 STORY-019 and the skill rule behind each name).
- **Validate**: `.venv/Scripts/python -m pytest tests/test_admin_copy.py -q -p no:cacheprovider` (after Task 9 updates the census; before it, `tests/test_copy.py` census will fail by design).

### Task 2: Row model and formatting
- **Files**: `chat_ui/chat_ui/admin_models.py`, `chat_ui/chat_ui/admin_formatting.py`
- **Action**: UPDATE
- **Implement**:
  - `ActionRow(pydantic.BaseModel)`, all `str`, falsy default `""`: `action_id` (the row `id`, str, not rendered; kept as a stable key if needed else omit), `timestamp_relative`, `timestamp_absolute`, `user_id`, `role`, `tool_name`, `operation_kind`, `target` (full text, redacted at write), `rule`, `reason`, `decision` (the key `deny|flag|allow`, for `rx.match`), `allowed_by` (granted_by, or the absent mark). **No** `arguments_preview`, `arguments_hash`, `session_id`, `classifications`, `policy_digest`, `tool_call_id`. Docstring cites PRD-016 F11 and the `AuditRow` boundary.
  - `admin_formatting.py`: `DECISION_ALLOW = "allow"`, `DECISION_FLAG = "flag"`, `DECISION_DENY = "deny"`, `DECISIONS = (DECISION_DENY, DECISION_FLAG, DECISION_ALLOW)` (deny first, like `VERDICTS` runs exceptions first; a test binds `set(DECISIONS) == set(app.db.models.ACTION_DECISION_VALUES)`), and `to_action_rows(rows: list[ActionDecisionRow], now=None) -> list[ActionRow]` using `_format_timestamps` and `_text`. It enumerates its fields (no `**row.__dict__`). `ActionDecisionRow` import is type-only data from `app.db.models`, so no new write path.
  - Empty/`None` columns (`operation_kind`, `target_preview`, `granted_by` are Optional) render `VALUE_ABSENT`.
- **Mirror**: `admin_formatting.py:262-306` (`to_audit_row`), `331-371` (`to_usage_rows`); `admin_models.py:93-110`.
- **Validate**: unit tests in Task 8.

### Task 3: State
- **File**: `chat_ui/chat_ui/admin_state.py`
- **Action**: UPDATE
- **Implement**:
  - Imports by name: `count_action_decisions`, `list_action_decisions` from `app.db.database` (comment beside it, like the `usage_snapshot` one at line 50); `to_action_rows`, `DECISION_*` from formatting; `ActionRow`; the new copy names. Update the module docstring's "ten read functions" sentence only if it states a count that the two new imports falsify (it says "The ten read functions ... The Usage table's read ... imported the same way"): add one sentence for the Actions reads.
  - Constants next to `USAGE_STATE_*` (line 193-203): `ACTIONS_ROW_LIMIT = 500` (equals the router's `ACTIONS_LIMIT_MAX`; import that constant from `app.routers.admin` is NOT allowed here, it is not a read function and the console never imports routers: type the number once here, with a comment naming `ACTIONS_LIMIT_MAX` and a test asserting equality), `ACTIONS_FILTER_DENY/FLAG/ALLOW/ALL = "deny"/"flag"/"allow"/"all"`, `ACTIONS_FILTERS` tuple, `ACTIONS_STATE_FAULT = "read_failed"`, `ACTIONS_STATE_EMPTY = "no_decisions"`, `ACTIONS_STATE_ROWS = "rows"`, `ACTIONS_STATES`. `_filter_decision(key) -> Optional[str]`: `""`/`deny` -> `"deny"`, `all` -> `None`, `flag`/`allow` themselves; unknown -> `"deny"`.
  - Vars (all falsy defaults, next to `usage_*`, line 524-530): `action_rows: list[ActionRow] = []`, `actions_error: str = ""`, `actions_filter: str = ""` (comment: `""` is the default, Denied; falsy so `reset()` clears it), `actions_denied: int = 0`, `actions_flagged: int = 0`, `actions_allowed: int = 0`.
  - Computed vars (read their deps off `self` in the body, per the rule at `admin_state.py:580-587`): `actions_state` (fault first, then empty, then rows; reads `actions_error`, `action_rows`), `actions_selected` (resolved filter key, `""` -> `deny`, so the chips can compare), `actions_scope` (the `ACTIONS_SCOPE_TEMPLATE` sentence from `len(action_rows)` and the matching count via `format_count`), `actions_empty_title`.
  - Module-level `read_actions(decision) -> tuple[list[ActionRow], dict[str, int]]`: sync; `to_action_rows(list_action_decisions(limit=ACTIONS_ROW_LIMIT, decision=decision), now)` and `count_action_decisions()`. Both inside the one function so one `to_thread` hop covers both and formatting errors count as this read's.
  - `load()`: add `self.actions_error = ""` to the opening reset block (line 1197) and a third `try/except/else` after usage, before the summary read: `except` -> `self.actions_error = LOAD_FAILED_MESSAGE.format(read=READ_LABEL_ACTIONS, detail=exc)`; `else` commit rows, counts and clear the error. Update the docstring's "The usage read is separate" paragraph with a sentence for actions (and the "before the summary read so its early returns cannot skip it" reasoning applies equally).
  - `choose_actions_filter(key)` `@rx.event`: ignore unknown keys; set `actions_filter`; `return AdminState.load_actions`. Reassign, never mutate (the `toggle_verdict` note). `load_actions` `@rx.event(background=True)`: the `load()` two-step gate (`authenticated` outside and inside the lock), read, commit only if `actions_filter` unchanged, own fault into `actions_error`; it does not set `loading` (so Refresh is not locked by a chip click) but it also must not clobber an in-flight `load()` commit: both write only `action_rows/actions_*`, last commit wins, and the staleness check covers the filter.
- **Mirror**: `admin_state.py:963-984` (`usage_state`), `1121-1217` (`load()` and its two-step gate), `1048-1055` (`clear_filters` docstring style), `994-1007` (`toggle_verdict`).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_admin_state.py tests/test_usage_view.py -q -p no:cacheprovider` (existing tests must stay green after Task 9's fixture edits).

### Task 4: The component
- **File**: `chat_ui/chat_ui/components/actions.py`
- **Action**: CREATE
- **Implement** (imports: `reflex`, `admin_copy`, `theme`, `AdminState` + the `ACTIONS_*`/`DECISION_*` constants, and `fault_panel`, `refreshed_stamp` from `admin_shell`; nothing from `register`, `summary`, `usage`, `chat`, `bubbles`; module docstring in the Usage module's voice: what the view refuses (no chart, no per-day history, no per-row action, no export, no stamp margin), why the filter re-reads, the empty-state rule, that the component reads fields and computes nothing):
  - `_GRID` with eleven decisions in the AC's order: time `8.5rem`, user `minmax(6rem, 10rem)`, role `5rem`, tool `7.5rem`, operation `5.5rem`, target `minmax(12rem, 1fr)` (the one flexible track, truncating), rule `minmax(9rem, 14rem)`, decision `5.5rem`, allowed-by `minmax(8rem, 12rem)`; `_MIN_WIDTH` = sum of tracks + 8 gaps of `0.75rem`, arithmetic in the comment (the Usage `_MIN_WIDTH` precedent, `usage.py:71-74`). Since target is `1fr`, set the table to `width="100%"` with `min_width=_MIN_WIDTH` (Register's pattern) rather than Usage's `fit-content`; confirm at 1920 in the E2E that Role does not drift a thousand pixels from User (Usage's measured failure); if it does, bound the target track (`minmax(12rem, 40rem)`) and use `fit-content`.
  - `_head_cell`, `_cell(value, title=None)` re-declared (set `custom_attrs={"role": "cell", "title": ...}` when a title Var is given), `_tag(label, ink, exception)` re-declared, `_decision_cell(row)`: `rx.match(row.decision, (DECISION_DENY, _tag(DECISION_DENY_LABEL, INK_DENIED)), (DECISION_FLAG, _tag(..., INK_HELD)), (DECISION_ALLOW, _tag(..., INK_CLEAR, exception=False)), _tag(VALUE_ABSENT-copy...))` with a default arm (an unrecognised or blank decision must not claim "allowed").
  - Target cell: `title=row.target`, `overflow:hidden; text-overflow:ellipsis; white-space:nowrap`. Rule cell: `title=row.reason`. Tool cell title = tool name (cheap, can be long, e.g. MCP names).
  - `_filter_strip()`: `_control_label(ACTIONS_FILTER_LABEL)` + four `_control_button`s from a Python tuple `_FILTER_CHIPS = ((ACTIONS_FILTER_DENY, label, theme.INK_DENIED), (FLAG, ..., INK_HELD), (ALLOW, ..., INK_CLEAR), (ALL, ..., theme.INK))`, both selected/unselected built and chosen with `rx.cond(AdminState.actions_selected == key, ...)` (the `_verdict_filter` pattern), `aria-pressed`, ink as text + 2px underline, `on_click=AdminState.choose_actions_filter(key)`. Wrap in `rx.flex(..., wrap="wrap", gap="0.75rem")` so it wraps at 390px. Label "Show" is the eyebrow so the group is named for a screen reader: `role="group"` + `aria-label` from the same constant on the flex.
  - `_caption()`: `AdminState.actions_scope` (FONT_BODY, the one scope line) over `refreshed_stamp()`; `_empty_actions()` (Usage's `_empty_usage` shape: title = `AdminState.actions_empty_title`, body = `EMPTY_ACTIONS_BODY`); `_table()` with `role=table` and `aria-label` = the Actions view label; `_actions_body()` `rx.match` over `AdminState.actions_state` (fault arm renders the table: last good rows stand under the panel); `actions()` = `vstack(fault_panel(AdminState.actions_error), _caption(), filter strip, scroll box)` with `min_height="0"` chain exactly as `usage.py:256-277`.
  - Rows: `rx.foreach(AdminState.action_rows, _row)`; no hover, no click, no tint (same reasoning as `usage.py:156-158`); hairline `RULE_SOFT` between rows; the column head is sticky.
  - Only ground tokens plus the three decision inks; no literal hex (`tests/test_admin_palette.py` guard), no `rx.moment`/interval, no animation (the Refresh glyph stays the console's sole moving element).
- **Mirror**: `usage.py` whole file; `register.py:181-258, 663-761`.
- **Validate**: `cd chat_ui` probe form from the brief (import `chat_ui.chat_ui`), or `tests/test_actions_view.py` (Task 8).

### Task 5: Shell, route, page
- **Files**: `chat_ui/chat_ui/components/admin_shell.py`, `chat_ui/chat_ui/chat_ui.py`
- **Action**: UPDATE
- **Implement**: `ROUTE_ACTIONS = "/admin/actions"` and `VIEW_ACTIONS = "actions"` (with a comment: not a backend path, falls through Caddy's static matcher; its own view because it is a decision log, not a figure on the all-time summary); fourth rule-separated `rx.box(_view_link(VIEW_ACTIONS, admin_copy.VIEW_ACTIONS_LABEL, ROUTE_ACTIONS, active), ...)` after Usage; update the masthead docstring ("three peers" -> four, one line why a switch is still right) and the module docstring's "Register and Summary since PRD-006, and Usage since PRD-013" sentence. `chat_ui.py`: import `ROUTE_ACTIONS`, `VIEW_ACTIONS`, `from chat_ui.components.actions import actions`; `admin_actions_page()` returning `admin_page(actions(), VIEW_ACTIONS)`; `app.add_page(admin_actions_page, route=ROUTE_ACTIONS, context={"sitemap": None})`; extend the comment at lines 86-91 and 154-157 ("all four admin routes" becomes five incl. `/admin`? the existing text says four; recount: audit, stats, usage, actions, admin landing = five pages; adjust the number only if it is stated). The route is imported, never retyped (`tests/test_admin_shell.py:865-872`). No `on_load` (page-load must read nothing, `tests/test_admin_shell.py:804-821`).
- **Mirror**: `admin_shell.py:481-492`, `chat_ui.py:103-105, 168-172`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_admin_shell.py -q -p no:cacheprovider`.

### Task 6: Existing-test census edits (assertions that pin "three views", each with a PRD-016 comment)
- `tests/test_admin_shell.py`: `EXPECTED_ROUTES` (+`ROUTE_ACTIONS`), the probe script (fourth `admin_masthead`/`admin_page` factories, `routes`/`views` dicts, `both_have_switch_labels` and `both_mark_current` include the fourth masthead and `VIEW_ACTIONS_LABEL`), `EXPECTED_PAGE_KEYS` and `CONSOLE_PAGE_KEYS` (+`admin/actions`, sorted position after `admin/usage`? `reflex_app._unevaluated_pages` order is registration order sorted by the test's list; the list is already ordered `admin, admin/audit, admin/stats, admin/usage, index, reports...`, so it is sorted; insert `admin/actions` first among the `admin*` keys alphabetically: `admin, admin/actions, admin/audit, ...`; verify against the real output when running), `len(set(views.values())) == 3` -> `== 4`.
- `tests/test_copy.py` (census list at ~line 440-480 and the `assert admin_copy.X` block at ~385): add the new names with a PRD-016 comment (the PRD's own rule: "no existing assertion changed except ... each with a comment citing PRD-016 and the decision"; these are additions to pinned census sets, the same kind PRD-013 STORY-016 made).
- `tests/test_admin_palette.py` `ADMIN_MODULE_PATTERNS`: add `chat_ui/chat_ui/components/actions.py` (comment).
- `tests/test_admin_state.py`: add autouse `_no_actions_read` fixture next to `_no_usage_read` (line 398) patching `admin_state_mod.list_action_decisions`/`count_action_decisions` to harmless stubs. Same for `tests/test_usage_view.py::_Console.__init__`. Search `tests/` for other `event_handlers["load"]` callers (`grep -rn 'event_handlers\["load"\]' tests`) and add the stub wherever the real database would otherwise be hit; known: `tests/test_admin_state.py`, `tests/test_usage_view.py`, possibly `tests/test_register.py`/`test_summary.py`/`test_render_invariants.py`.
- Guard tests that use the module glob (focus ring `test_admin_shell.py:889-935`, no-auto-refresh `:656`, width pin `:929`): their `ADMIN_MODULE_PATTERNS` (line ~96-102) list register and summary only, not `usage.py`. Add `actions.py` to that tuple (one line, PRD-016 comment) so the new module is covered by the width/focus/auto-refresh guards; do not also add `usage.py` (not this story's).

### Task 7: (reserved) `tests/test_pii_redaction_integration.py` census
No test is renamed or removed, so `_DELIBERATELY_SUPERSEDED_TESTS` is untouched. Run the file once as a guard.

### Task 8: New tests, `tests/test_actions_view.py`
Four layers like `tests/test_usage_view.py`, db tests only where a real read is needed (`temp_db` fixture; `docker restart harness-libsql-dev` if many db tests error at setup):
1. **Formatting/model** (no DB): `to_action_rows` maps every field, `None` -> absent mark, an unparseable timestamp keeps the absolute text; `ActionRow` has no `arguments_preview`/`arguments_hash`/`session_id`/`classifications` field and no value of those reaches a row (build an `ActionDecisionRow` with a recognisable arguments preview and assert it is absent from `repr(row)`); every field is `str`; `DECISIONS` equals `ACTION_DECISION_VALUES`; `ACTIONS_ROW_LIMIT == app.routers.admin.ACTIONS_LIMIT_MAX`.
2. **Storage via the real functions** (`temp_db`): seed through `action_audit.record()` with decisions from `action_policy.evaluate()` over real corpus calls (e.g. `rm -rf /`, `curl ... | sh`, a DROP TABLE, an allowed `git status`) for two identities (user, dba via the corpus' test matrix, `tests/test_action_corpus.py` shows how the identities/policy are built): the console's `read_actions("deny")` returns only denies, newest first, `read_actions(None)` mixes, counts equal `count_action_decisions()`, and a 500+ row seed is capped at 500 (AC 4 "Given 500 rows").
3. **State** (`_Console`-style fake): `load()` commits `action_rows` for the default Denied filter and passes `decision="deny"`; `choose_actions_filter("flag"/"allow"/"all")` returns `AdminState.load_actions` and the read follows with the right `decision` (`None` for All); an unknown key changes nothing; the empty state for each filter; first failed read is the fault state, not empty; the fault leaves Register/summary/usage standing and a failed summary still refreshes actions (the Usage tests' mirror, `test_usage_view.py:499-566`); a stale filter result is not committed; `sign_out()` clears every new var; unauthenticated `load_actions` reads nothing; the new vars are in `base_vars` and the three computed ones are not; `AdminState` namespace has no `insert_action_decisions`.
4. **Component probe** (subprocess, `cwd=chat_ui`, `PYTHONPATH=chat_ui;repo`): builds; every head and chip label is present; the four chips carry `aria-pressed` and `on_click`; the empty arm contains the PRD-017 sentence and `EMPTY_ACTIONS_TITLE` and no `columnheader`; the table arm has `role=table` and `title` bindings on target/rule; only ground tokens plus `INK_DENIED/INK_HELD/INK_CLEAR` in the compiled table (no `INK_UPSTREAM/INK_SELF/INK_FAULT`); no literal hex; every string comes from `admin_copy` (the not-a-literal pattern, `test_usage_view.py:836-845`); imports nothing from chat/other views; scroll container is `hx-scroll` with `overflow_x="auto"` and `min_width=_MIN_WIDTH`; `hx-view-switch` still present and the fourth link renders in the masthead of every view; routes: `/admin/actions` registered, sitemap None, no on_load, and `app.main` routes unchanged (extends the `test_admin_shell.py` probes, which Task 6 already covers).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_actions_view.py -q -p no:cacheprovider`.

### Task 9: Targeted validation (the brief's narrow set; do NOT run the full suite)
```
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_actions_view.py tests/test_usage_view.py tests/test_admin_shell.py tests/test_admin_state.py tests/test_admin_copy.py tests/test_copy.py tests/test_admin_palette.py tests/test_admin_models.py tests/test_admin_formatting.py tests/test_register.py tests/test_summary.py tests/test_chat_ui_startup_guard.py tests/test_untouched_app.py tests/test_pii_redaction_integration.py tests/test_caddyfile_routes.py -q -p no:cacheprovider
```
(`test_copy.py` is large; keep it, because the census lives there. Known environmental failure to ignore: `tests/test_query_router.py::test_full_pipeline_latency_within_budget`, not in this set.) AC 5: Register, Summary, Usage tests (`test_register.py`, `test_summary.py`, `test_usage_view.py`, the shell/state files) must be green with only the Task 6 edits.

### Task 10: E2E in the running console (the `run` skill / the PRD-013 STORY-016 method, `reflex run --env prod`)
Seed with the real writers on a database the executor may dirty (the shared `harness-libsql-dev` was reset by another process during PRD-013's E2E; prefer a throwaway container of the same image on another port, removed afterwards): build `ToolCall`s from corpus entries, `evaluate()` them for `Identity(user)` and `Identity(dba)`, `action_audit.record(decisions, identity)`; include one long `shell` target (>200 chars) and an `http` target with a redacted query (`***`). Then `cd chat_ui && ... reflex.exe run --env prod`, open `/admin`, sign in with `ADMIN_TOKEN`:
- [ ] Masthead reads Register, Summary, Usage, Actions; `/admin/actions` marks `aria-current`; Tab reaches the link with the visible ring.
- [ ] Opens on Denied: only deny rows, newest first, columns Time, User, Role, Tool, Operation, Target, Rule, Decision, Allowed by; decision tag in `INK_DENIED` caps; scope line "N most recent of N denied" with the Refreshed stamp.
- [ ] Chips: Flagged, Allowed, All each re-read and the list follows; `aria-pressed` and the underline move; keyboard Tab/Enter/Space works and the focus ring is visible on every chip.
- [ ] A dba allowed row shows its permission under Allowed by (`action:sql:write`); a row with no permission shows the absent mark.
- [ ] Long target truncates with an ellipsis; hovering shows the full text; the redacted URL shows `***`, never a token.
- [ ] 500 rows (seed 520 deny rows): the list renders and scrolls inside the container; scope line says "500 most recent of 520 denied"; no page scroll at 390px (`documentElement.scrollWidth == innerWidth`); the four-word switch still fits its own row at 390px and sign out stays on screen.
- [ ] Empty: delete the seeded rows, Refresh: the empty panel names the filter, states it is empty because nothing calls the engine until PRD-017, and ends with Refresh; no empty grid. Switch to All: the generic title.
- [ ] Fault: stop the database, Refresh on `/admin/actions`: the fault panel names "the action decisions"; on recovery it clears.
- [ ] Sign out and back in: nothing visible before the load.
- [ ] Dark ground (`ground_switch`): tags and chips stay legible (the inks have dark variants, `theme.py:114-118`).
Cleanup: revert `chat_ui/reflex.lock/package.json`, delete generated `package-lock.json`, remove the throwaway container and seeded rows.

### Task 11: Report, commit, story/index
Per the brief (code + plan + report in one commit with `commit: pending`, then the `chore(PRD-016): STORY-019 report; update status + index` follow-up with the SHA; regenerate the index with the gen_index script, `errors: none`).

---

## End-to-End Tests

See Task 10. Backend sanity: `GET /audit/actions?decision=deny&limit=500` (STORY-016, header `X-Api-Key`/identity as the API requires) returns the same rows the view shows for the same filter; the `/stats` `actions_denied` equals the count in the scope line.

---

## Validation

```
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest <Task 9 set> -q -p no:cacheprovider
# chat_ui import probe (cwd chat_ui/, PYTHONPATH="<repo>/chat_ui;<repo>", DATABASE_URL/OPENROUTER_API_KEY/ADMIN_TOKEN set): import chat_ui.chat_ui
```
Full suite: deferred to orchestrator (user decision).

---

## Risks and Open Questions

1. **AC 1 names `audit:read:all`, but the console has no RBAC** (ADMIN_TOKEN gate; see "RBAC / gate"). Plan follows the code: the token holder sees all rows, no permission check, no masking. Orchestrator to confirm this reading.
2. **"Full text available" is a `title` attribute**: no help on touch. A per-row disclosure (the Register's `open_rows` mechanism) would cover it, at the cost of one more state var, a toggle event, detail copy and tests. Recommend shipping `title` only; say if the orchestrator wants the disclosure.
3. **The filter re-reads the database** (D-A), against PRD-006's Register rule; chosen so deny is never hidden by newer allows. `load_actions` and `load()` can interleave; mitigated by the stale-filter check and last-commit-wins on the same vars.
4. **Empty-state body is time-bound** (names PRD-017). PRD-017 must reword `EMPTY_ACTIONS_BODY` (note for STORY-020 docs).
5. **Existing census tests must be edited** (route sets, view count, copy census, module globs): PRD Section 11 says no existing assertion changes except the six retargeted strings; PRD-013 STORY-016 set the precedent of extending pinned sets, and each edit gets a PRD-016 STORY-019 comment. Tell the orchestrator; AC 5 is met because no Register/Summary/Usage behaviour changes.
6. **`load()` gaining a database read** means every existing test that runs `load()` without stubbing would reach a real DB. Mitigation in Task 6 (autouse stubs); the implementer greps for all `event_handlers["load"]` callers.
7. **Masthead at 390px with four views** is estimated (~270px) not measured; E2E decides, `theme.py` change only if it overflows.
8. **Reflex skills are not installed** (`chat_ui/AGENTS.md` asks for `reflex-docs` etc.); the planner could not load them. The plan relies on in-repo Reflex 0.9.6.post1 patterns only; the implementer should re-check `rx.cond`/`rx.match` on a `str` Var, `@rx.event(background=True)` return semantics and `custom_attrs={"title": Var}` against the existing code (Usage heads use a static `title`; a Var `title` on a cell is new here: verify it compiles, else build the cell as `rx.el.div(title=...)`).
9. **Worktree note**: `.agents/stories/.../STORY-020-docs-and-promotion.md` is modified before this story and belongs to the orchestrator.

---

## Acceptance Criteria

(Copied from story `STORY-019`; each with how it is covered)

- [ ] AC1: fourth view **Actions** in the switch beside Register, Summary, Usage; route renders through `admin_page(...)`. Covered by Task 5; tests: shell probe (switch labels, `aria-current`), `test_admin_shell.py` page-key sets, `test_actions_view.py` page/route assertions.
- [ ] AC2: deny rows by default; columns time, user, role, tool, operation, target, rule, decision, permission; a control switches deny/flag/allow/all and the list follows. Tasks 3-4; tests: state tests (`decision=` follows the key), component probe (heads, chips), storage test (only denies).
- [ ] AC3: empty state says what the view contains and why it is empty (PRD-017), not a blank table. Tasks 1, 4; test: empty arm has the sentence and no `columnheader`.
- [ ] AC4: 500 rows and phone width usable: no page scroll, truncated targets with full text available, visible focus on the filter. Tasks 4, 10; tests: 500-row seed capped at 500, `hx-scroll`/`min_width` source asserts, `title` binding; E2E at 390px; the global focus-ring guard.
- [ ] AC5: Register, Summary, Usage unchanged and green. Task 9 runs their suites; only pinned-set extensions edited.
- [ ] All tasks completed
- [ ] `from app.main import app` imports; chat_ui import probe passes
- [ ] Follows existing patterns (Usage view, Register controls)
