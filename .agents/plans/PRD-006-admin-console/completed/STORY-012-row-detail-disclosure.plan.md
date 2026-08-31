---
story: STORY-012
prd: PRD-006
slug: row-detail-disclosure
title: "Row detail disclosure: error_message, prompt_hash, PII entities, full User-Agent, pattern"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-006-admin-console
created: 2026-08-31
---

# Plan: Row detail disclosure: error_message, prompt_hash, PII entities, full User-Agent, pattern

## Summary

STORY-011 shipped the register's eight columns and the stamp margin; every field
`GET /audit` does not project is already on `AuditRow` and already unrendered.
This story adds the per-row disclosure that renders them: a narrow control
column at the right edge of the grid, a `list[int]` of open `audit_id`s on
`AdminState`, and a detail block that opens beneath its row carrying six labelled
facts — `prompt_hash`, `error_message`, `suspicious_pattern`, the full
User-Agent, the PII entity types, and `pii_detected_input` / `pii_detected_output`
split apart. Open state is keyed on `audit_id` rather than held in the DOM,
because STORY-013's sort and filter reorder `visible_rows` and an `rx.foreach`
re-render would otherwise leave a `<details open>` attached to a *position*
instead of a row. Nothing is computed at render: `to_audit_row` already writes
`VALUE_ABSENT` into the three nullable string fields, so AC 5's "stated as
absent" is true at the boundary and the component only reads it.

## User Story

As a compliance admin
I want to see which queries failed and why
So that an outage or a broken redactor is visible in the record instead of
hiding behind `/audit`'s projection.

## Story Reference

- Story file: `.agents/stories/PRD-006-admin-console/STORY-012-row-detail-disclosure.md`
- PRD: `.agents/PRDs/PRD-006-admin-console/PRD.md` — Section 4, Section 5 (story 3), Section 7, Section 9, Section 10

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/` only — no change under `app/` |
| Story | STORY-012 |
| PRD | PRD-006 |
| Epic Branch | `epic/PRD-006-admin-console` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| **frontend-design** | "Let each element do exactly one job. A label labels, an example demonstrates, and nothing quietly does double duty." The disclosure carries evidence, not a second summary of the row — which is why the absolute timestamp is **not** repeated on it (it is already the second line of the in-row time cell), and why the `#3180` id cell is *not* made the toggle. Also: "An action keeps the same name through the whole flow" — `DETAIL_TOGGLE_OPEN_LABEL` / `DETAIL_TOGGLE_CLOSE_LABEL` are the two directions of one control, and "errors don't apologize" governs the absent marks. Quality floor: "visible keyboard focus". | Tasks 1, 5 |
| **reflex-docs** (`reflex:reflex-docs`) | `chat_ui/AGENTS.md`, verbatim: "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory." Consulted for the per-row open-state idiom. **Confirmed against the docs and the installed package**: (a) `in` is not supported on Vars — `Var.contains()` is the membership operator, and it requires a strict annotation (`list[int]`, never bare `list`); (b) `rx.el.details` / `rx.el.summary` and `rx.accordion` both exist in the pinned build but are rejected below for reasons that are structural, not stylistic. | Tasks 3, 5 |
| **reflex-process-management** (`reflex:reflex-process-management`) | `chat_ui/AGENTS.md`: "When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill for the correct sequence and error investigation steps." `reflex compile --dry` is the validation on every component task; `reflex run --env prod --single-port 2>&1 \| tee reflex.log` is the E2E run, and it has **no hot reload** — a change means SIGINT the listening PID from `reflex.log`'s port and start again. | Tasks 5, 7 |

### The idiom decision, recorded

Three ways to hold per-row open state over an `rx.foreach`. Two are rejected:

1. **`rx.el.details` / `rx.el.summary`** — native, keyboard-operable for free,
   no state var. Rejected: the open flag lives in the DOM node, and
   `rx.foreach` compiles to a `.map()` whose children are keyed by position.
   STORY-013 reorders and filters `visible_rows`, so a sort would leave row 4's
   disclosure open on whatever row lands in position 4. That is silent
   wrongness on an audit surface, which is the one place it cannot be tolerated.
2. **`rx.accordion`** — Radix, and it supplies colour at compile time. This is
   the exact failure `components/admin_shell.py:_view_link` records for
   `rx.link`'s accent default, and `tests/test_register.py::test_no_colour_outside_the_allowed_set`
   greps the *rendered* output, not the source. It also brings its own chrome
   and animation, against Risk 6 (no card, no fill) and Section 6.1's
   "motion — effectively none".
3. **A `list[int]` of open `audit_id`s on `AdminState` + `Var.contains()`** —
   chosen. Open state travels with the row's identity through any reorder, it
   mirrors `toggle_verdict`'s existing reassign-don't-mutate handler exactly,
   and its falsy default keeps `test_sign_out_clears_every_declared_var` green.

---

## Patterns to Follow

### Naming — verdict keys are values, labels are copy

```python
# SOURCE: chat_ui/chat_ui/admin_formatting.py:42-60
VERDICT_CLEARED = "cleared"
...
# What a cell shows when its source column is NULL. One mark for every column,
# so "no value on this row" reads the same everywhere on the register.
VALUE_ABSENT = "—"
```

### Absence is written at the boundary, not branched at render

```python
# SOURCE: chat_ui/chat_ui/admin_formatting.py:126-130, 208-213
def _text(value: Optional[object]) -> str:
    """A NULL column reads as the absent mark, so the row field stays a plain str."""
    if value is None or value == "":
        return VALUE_ABSENT
    return str(value)

    prompt_hash=_text(log.prompt_hash),
    error_message=_text(log.error_message),
    ...
    suspicious_pattern=_text(log.suspicious_pattern),
```

**This is AC 5, already true.** `prompt_hash`, `error_message`,
`suspicious_pattern` and `device_full` can never arrive blank. The component
adds no fallback for them; the only two fields needing a render-time absence
statement are `pii_entities` (an empty `list[str]`) and the two booleans.

### Toggle handler — reassign, never mutate

```python
# SOURCE: chat_ui/chat_ui/admin_state.py:383-397
@rx.event
def toggle_verdict(self, verdict: str):
    """Adds or removes one verdict from the selection.

    Reassigns the list rather than mutating it in place: Reflex marks a var
    dirty on assignment, and an in-place `.append()` on a list var can leave
    `visible_rows` serving its cached value.
    """
    if verdict in self.selected_verdicts:
        self.selected_verdicts = [
            v for v in self.selected_verdicts if v != verdict
        ]
    else:
        self.selected_verdicts = [*self.selected_verdicts, verdict]
```

### A keyboard-operable control that draws no chrome

```python
# SOURCE: chat_ui/chat_ui/components/admin_shell.py:266-283
rx.el.button(
    admin_copy.SIGN_OUT_LABEL,
    on_click=AdminState.sign_out,
    # Explicit: an unqualified <button> defaults to submit, and
    # that is the wrong default to inherit for a control whose
    # job is to end the session.
    type="button",
    cursor="pointer",
    background="none",
    border="none",
    padding="0",
    ...
)
```

`theme.GLOBAL_CSS`'s `:focus-visible` rule gives it the ring; nothing local may
take it back (`tests/test_register.py::test_register_sets_no_focus_reset`).

### Render-time branching on a row field

```python
# SOURCE: chat_ui/chat_ui/components/register.py:247-251
rx.cond(
    row.pii_indicator,
    _cell(admin_copy.PII_INDICATOR_LABEL),
    _cell(VALUE_ABSENT, color=theme.MUTE),
),
```

### Tests — the build probe, then the source assertions

```python
# SOURCE: tests/test_register.py:163-170
factories = [
    ("register", lambda: register()),
    ("_column_head", lambda: _column_head()),
    ("_scope_line", lambda: _scope_line()),
    ("rows", lambda: rx.box(rx.foreach(AdminState.visible_rows, _row))),
    ("stamps", lambda: rx.box(rx.foreach(AdminState.visible_rows, _stamp_margin))),
    ("tags", lambda: rx.box(rx.foreach(AdminState.visible_rows, _verdict_tag))),
]
```

```python
# SOURCE: tests/test_admin_state.py:704-705
def _call(state: AdminState, handler: str, *args):
    return type(state).event_handlers[handler].fn(state, *args)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/admin_copy.py` | UPDATE | Four constants the disclosure needs and STORY-008 did not provision: the two toggle marks and the two PII presence words. |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | `open_rows: list[int]` and `toggle_detail(audit_id)`. |
| `chat_ui/chat_ui/components/register.py` | UPDATE | The control column, the toggle, the detail block, and the row restructure that carries them. |
| `tests/test_copy.py` | UPDATE | Assert the four new constants non-empty and add them to the exhaustiveness set (line 325's `declared`/`asserted` comparison fails otherwise). |
| `tests/test_admin_state.py` | UPDATE | `toggle_detail` adds, removes, reassigns, is independent per id, and clears on sign-out. |
| `tests/test_register.py` | UPDATE | The disclosure's factories in the probe, the new copy names, and AC 6's "no preview" restated over the detail. |

No file is created. Nothing under `app/` is touched (PRD-006 Section 4, Out of
Scope). No new `theme.py` token is needed — the detail reuses `STAMP_X`, `RULE`,
`RULE_SOFT`, `MUTE`, `INK`, `TEXT_MICRO`, `TEXT_DATA` and the three faces.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Four copy constants for the disclosure

- **File**: `chat_ui/chat_ui/admin_copy.py`
- **Action**: UPDATE
- **Implement**: extend the existing `# --- Row disclosure ---` block (line 222)
  with four constants, each carrying the comment that says why it is a separate
  name:
  - `DETAIL_TOGGLE_OPEN_MARK = "+"` and `DETAIL_TOGGLE_CLOSE_MARK = "−"`
    (U+2212 MINUS SIGN, not a hyphen — the same typographic register as
    `VALUE_ABSENT`'s em dash and `SORT_ASCENDING_MARK`'s arrow). These are the
    *visible* content of the toggle; `DETAIL_TOGGLE_OPEN_LABEL` /
    `DETAIL_TOGGLE_CLOSE_LABEL` stay as its accessible name. Two names for one
    control is not drift here — the mark fits a 2.5rem column at the right edge
    of a hundred rows, and "Show detail" repeated a hundred times down that edge
    would compete with the stamp margin, which is where Section 6.1 spends the
    whole design's boldness. `SORT_ASCENDING_MARK` is the precedent for a mark
    living in this module; the register's "no icon" refusal is about icons, and
    these are characters.
  - `DETAIL_PII_PRESENT_LABEL = "detected"` and
    `DETAIL_PII_ABSENT_LABEL = "not detected"` — AC 5 requires the empty case be
    *stated*, and a false boolean has no `VALUE_ABSENT` to fall back on because
    `False` is a recorded fact, not a missing value (the same distinction
    `to_audit_row` makes for `tokens_used`). "not detected" says the redactor
    ran and found nothing; a dash would say the column was NULL.
- **Also record, in the block's comment**: `DETAIL_TIMESTAMP_LABEL` is
  **deliberately not rendered** by this story. STORY-008 provisioned "one label
  per field PRD-006 Section 10 puts on disclosure", but Section 10's timestamp
  row describes the *in-row* column ("relative + absolute"), and
  `register._time_cell` already sets the absolute stamp under the relative one.
  Rendering it again would be the frontend-design skill's "nothing quietly does
  double duty", and the story's AC 1 names five fields, not six. The constant
  stays declared and unused; `tests/test_copy.py` only asserts it non-empty.
- **Mirror**: `chat_ui/chat_ui/admin_copy.py:213-220` — the sort labels and
  marks block, which pairs a name with a mark for the same reason.
- **Validate**: `python -c "from chat_ui.chat_ui import admin_copy; print(admin_copy.DETAIL_TOGGLE_CLOSE_MARK, admin_copy.DETAIL_PII_ABSENT_LABEL)"` from the repo root.

### Task 2: Pin the four constants in the copy test

- **File**: `tests/test_copy.py`
- **Action**: UPDATE
- **Implement**: add the four names to the import list (line 102 block), add
  four `assert` lines in `test_admin_copy_constants_exist_and_not_empty`, and
  add the four strings to the `asserted` set at line 329. **The set is not
  optional**: the test compares `declared` (every uppercase name in
  `admin_copy`) against `asserted` and fails on a constant that ships untested.
- **Mirror**: `tests/test_copy.py:296-305` and `:392-400`.
- **Validate**: `python -m pytest tests/test_copy.py -q`

### Task 3: Per-row open state on `AdminState`

- **File**: `chat_ui/chat_ui/admin_state.py`
- **Action**: UPDATE
- **Implement**:
  - A fifth field in the `# --- Filter and sort ---` block (after
    `sort_descending`, line 298) — or a new `# --- Disclosure ---` block, which
    reads better since it is not a filter:
    ```python
    open_rows: list[int] = []
    ```
    Annotated `list[int]` and not bare `list`: `Var.contains()` needs the strict
    annotation to compile, and the empty default is what
    `test_sign_out_clears_every_declared_var` requires of every declared var —
    a disclosure left open across a sign-out is exactly the standing disclosure
    PRD-006 Section 9 is about.
  - The handler, beside `toggle_verdict`:
    ```python
    @rx.event
    def toggle_detail(self, audit_id: int):
        """Opens or closes one row's disclosure. Every other row is untouched."""
        if audit_id in self.open_rows:
            self.open_rows = [i for i in self.open_rows if i != audit_id]
        else:
            self.open_rows = [*self.open_rows, audit_id]
    ```
    Reassignment, not `.append()`, for the reason `toggle_verdict` records.
  - Docstring/comment: keyed on `audit_id`, not on the row's index, so an open
    disclosure survives STORY-013's sort and filter — the index is a position
    and the id is the row.
  - **Do not** clear `open_rows` in `load()` or `clear_filters()`. `audit_id` is
    monotonic and stable, so a refresh that returns the same row should return
    it in the same state; and an admin clearing a filter is not asking for their
    open rows to close. `sign_out()` clears it, via the existing `reset()`.
- **Mirror**: `chat_ui/chat_ui/admin_state.py:383-397` (`toggle_verdict`) and
  `:295-298` (the falsy-default block comment).
- **Validate**: `python -m pytest tests/test_admin_state.py -q` (existing suite
  must stay green — in particular `test_sign_out_clears_every_declared_var`,
  which now iterates one more var).

### Task 4: Test the handler

- **File**: `tests/test_admin_state.py`
- **Action**: UPDATE
- **Implement**: four tests in the filter/sort section, using the existing
  `_call` helper and `_loaded` fixture:
  - `test_toggle_detail_opens_closes_and_reassigns` — open 129, open 127,
    close 129; assert the list contents and that a *new* list object is
    assigned each time (`ids` differ), matching `toggle_verdict`'s test.
  - `test_each_rows_disclosure_is_independent` (AC 8) — opening three rows and
    closing one leaves the other two open.
  - `test_open_rows_defaults_empty_and_is_a_declared_var` — `"open_rows" in
    AdminState.base_vars` and the default is falsy.
  - `test_sign_out_closes_every_disclosure` — after opening two, `sign_out()`
    leaves `open_rows == []`.
- **Mirror**: `tests/test_admin_state.py:966-981` and `:1017-1035`.
- **Validate**: `python -m pytest tests/test_admin_state.py -q`

### Task 5: The disclosure in `register.py`

- **File**: `chat_ui/chat_ui/components/register.py`
- **Action**: UPDATE
- **Implement**, in this order inside the module:

  1. **Grid** — append a tenth track to `_GRID` for the control column:
     `... minmax(9rem, 1fr) 5.5rem 2.5rem`. Raise `_MIN_WIDTH` from `"58rem"` to
     `"61.25rem"` (the new track plus one `0.75rem` column gap), so the table
     still scrolls sideways in its own container rather than crushing the nine
     columns that carry data.
  2. **`_column_head`** — a tenth child: `rx.box()` with no label, for the same
     reason the stamp margin gets one — "a label over a column that carries no
     values would be a label that labels nothing." The control column carries a
     control, not values.
  3. **`_disclosure_toggle(row)`** — the control:
     ```python
     rx.cond(
         AdminState.open_rows.contains(row.audit_id),
         _toggle_button(row, admin_copy.DETAIL_TOGGLE_CLOSE_MARK,
                        admin_copy.DETAIL_TOGGLE_CLOSE_LABEL, "true"),
         _toggle_button(row, admin_copy.DETAIL_TOGGLE_OPEN_MARK,
                        admin_copy.DETAIL_TOGGLE_OPEN_LABEL, "false"),
     )
     ```
     with `_toggle_button` an `rx.el.button` carrying
     `on_click=AdminState.toggle_detail(row.audit_id)`, `type="button"`,
     `cursor="pointer"`, `background="none"`, `border="none"`,
     `font_family=theme.FONT_DATA`, `color=theme.MUTE`,
     `_hover={"color": theme.INK}`, and
     `custom_attrs={"aria-label": label, "aria-expanded": expanded}`. AC 7 is
     satisfied by it being a real `<button>` — focusable and Enter/Space
     operable with no key handling of our own — plus `GLOBAL_CSS`'s
     `:focus-visible` ring, which nothing here may reset.
     **`Var.contains()`, never `in`**: the `in` operator is not supported on
     Vars (reflex-docs, var operations).
  4. **`_detail_field(label, *value_children)`** — one labelled fact: the label
     in `FONT_DISPLAY` / `TEXT_MICRO` / uppercase / `MUTE` (the same treatment
     `_head_cell` gives a signpost, because both are labels), the value in
     `FONT_DATA` / `TEXT_DATA` / `INK` with `white_space="normal"` and
     `word_break="break-word"` — the opposite of `_cell`'s truncation, because
     an error message and a full User-Agent are exactly the two values that must
     not be cut, and nothing below the row line has an alignment to protect.
  5. **`_detail(row)`** — the block, six fields in this order:

     | Label constant | Value | Absence |
     |---|---|---|
     | `DETAIL_ERROR_LABEL` | `row.error_message` | `_text()` already wrote `VALUE_ABSENT` (AC 2, AC 5) |
     | `DETAIL_PATTERN_LABEL` | `row.suspicious_pattern` | same (AC 3 — the real pattern, not `AuditQueryEntry`'s flattened bool) |
     | `DETAIL_PROMPT_HASH_LABEL` | `row.prompt_hash` | same |
     | `DETAIL_DEVICE_LABEL` | `row.device_full` | `_truncate_device` already wrote it |
     | `DETAIL_PII_ENTITIES_LABEL` | `rx.foreach(row.pii_entities, …)` | `rx.cond(row.pii_entities.length() > 0, …, VALUE_ABSENT)` |
     | `DETAIL_PII_INPUT_LABEL`, `DETAIL_PII_OUTPUT_LABEL` | `rx.cond(row.pii_detected_input, PRESENT, ABSENT)` | AC 4 — **two separate fields**, split from the one in-row `pii_indicator` |

     **Test the entity list with `.length() > 0`, not truthiness.** `rx.cond`
     compiles to JavaScript, where `[]` is truthy; a bare
     `rx.cond(row.pii_entities, …)` would render an empty entity list as though
     it were populated. The entity types render as plain words spaced apart in
     the data face — no chip, no pill, no fill (Risk 6).

     Ordering is evidence-first: an admin opens a **fault** row to read the
     error and a **denied** row to read the pattern, so those are the top two
     lines rather than the hash.

     Layout: `display="grid"`, `grid_template_columns="9rem minmax(0, 1fr)"`,
     `row_gap="0.5rem"`, `column_gap="0.75rem"`, `padding="0.75rem 1.5rem 1rem 0.75rem"`,
     and — the one structural move —
     `margin_left=theme.STAMP_X` with `border_left=f"1px solid {theme.RULE}"`.
     That continues the stamp margin's own edge down through the open
     disclosure, so the stripe of exceptions is never broken by an open row and
     the detail visibly hangs off the register's spine. No card, no fill, no
     background — the block sits on `PAPER` like everything else.
  6. **`_row(row)`** — restructure. The grid box that exists today becomes
     `_row_line(row)` (unchanged except for the tenth child, the toggle, and
     `border_bottom` moving off it). `_row(row)` returns a wrapper:
     ```python
     rx.box(
         _row_line(row),
         rx.cond(
             AdminState.open_rows.contains(row.audit_id),
             _detail(row),
             rx.fragment(),
         ),
         border_bottom=f"1px solid {theme.RULE_SOFT}",
         custom_attrs={"role": "rowgroup"},
     )
     ```
     `role="rowgroup"` on the wrapper, `role="row"` on the line, and the detail
     block rendered as a second `role="row"` holding a single `role="cell"`.
     A bare `<div>` between `role="table"` and `role="row"` would break the ARIA
     table structure; a rowgroup containing two rows does not.
     The hairline moves to the wrapper so an open row is separated from the next
     row rather than from its own disclosure.
     `_hover` stays on the line, not the wrapper — hovering must not tint the
     open detail.
  7. **Module docstring** — replace the closing paragraph's "The disclosure
     (STORY-012) … is not here" with what is now true: what the disclosure
     renders, why the open state is a state var keyed on `audit_id` rather than
     `rx.el.details` or `rx.accordion` (the reorder argument above), and why
     `DETAIL_TIMESTAMP_LABEL` is not among the labels. Also update `_row`'s
     docstring, which currently reads "Nine children and no tenth" and lists the
     disclosure-only fields as belonging to STORY-012.
- **Mirror**: `chat_ui/chat_ui/components/register.py:229-267` (`_row`),
  `:77-93` (`_head_cell`'s label treatment),
  `chat_ui/chat_ui/components/admin_shell.py:266-283` (the chromeless button).
- **Validate**: `cd chat_ui && reflex compile --dry` — per the
  **reflex-process-management** skill, this catches import, syntax and
  component errors without starting a server. Then
  `python -m pytest tests/test_register.py -q` from the repo root.

### Task 6: Extend the register's tests

- **File**: `tests/test_register.py`
- **Action**: UPDATE
- **Implement**:
  - **Probe**: import `_detail`, `_disclosure_toggle` and `_row_line` in
    `_CHECK_SCRIPT` and add them to `factories`, each built through a real
    `rx.foreach(AdminState.visible_rows, …)` so they are handed the Var they get
    in production. Add `result["detail"] = built.get("detail", "")`.
  - `test_every_disclosure_label_is_rendered` (AC 1) — parametrized over the six
    label constants plus the two PII presence words; each must appear in the
    rendered detail.
  - `test_the_disclosure_renders_no_preview` (AC 6) — restate
    `test_the_register_reads_only_fields_that_exist_on_the_row` over the whole
    module (it already regexes `row.<attr>` file-wide, so it covers the new
    helpers for free) and assert neither `prompt_preview` nor `response_preview`
    appears in the rendered detail.
  - `test_the_toggle_is_a_real_button_with_an_accessible_name` (AC 7) — the
    rendered toggle contains `aria-expanded` and both toggle labels, and the
    source contains no `outline`/`box_shadow` reset (the existing
    `test_register_sets_no_focus_reset` already covers the second half).
  - `test_the_pii_indicator_is_split_on_the_disclosure` (AC 4) — the row's
    combined `PII_INDICATOR_LABEL` and the detail's two separate labels are all
    present, and the two detail labels differ.
  - `test_open_state_is_keyed_on_the_audit_id` — `"open_rows"` appears in the
    rendered output (proving the component binds the state var rather than a
    DOM-held `<details>`), and the source contains neither `rx.el.details` nor
    `rx.accordion`.
  - Extend `COPY_NAMES` with `DETAIL_ERROR_LABEL`, `DETAIL_PATTERN_LABEL`,
    `DETAIL_PROMPT_HASH_LABEL`, `DETAIL_DEVICE_LABEL`,
    `DETAIL_PII_ENTITIES_LABEL`, `DETAIL_PII_INPUT_LABEL`,
    `DETAIL_PII_OUTPUT_LABEL`, `DETAIL_TOGGLE_OPEN_LABEL`,
    `DETAIL_TOGGLE_CLOSE_LABEL`, `DETAIL_TOGGLE_OPEN_MARK`,
    `DETAIL_TOGGLE_CLOSE_MARK`, `DETAIL_PII_PRESENT_LABEL`,
    `DETAIL_PII_ABSENT_LABEL` — which puts each through both the
    "read from admin_copy" and the "not written as a literal" assertions.
    Note `DETAIL_TOGGLE_OPEN_MARK`'s value is `"+"`; check that
    `test_no_copy_value_is_written_as_a_literal` does not false-positive on a
    quoted `"+"` elsewhere in the file (it should not — there is no string
    concatenation in this module).
  - `test_body_face_appears_only_on_the_scope_line` must still hold: the detail
    uses `FONT_DATA` and `FONT_DISPLAY` only. The disclosure carries evidence,
    not prose.
- **Mirror**: `tests/test_register.py:131-185` (the probe) and `:239-306`.
- **Validate**: `python -m pytest tests/test_register.py tests/test_admin_palette.py tests/test_copy.py -q`

### Task 7: Run the console against a seeded database

- **File**: none (verification)
- **Action**: RUN
- **Implement**: per the **reflex-process-management** skill —
  `cd chat_ui && reflex run --env prod --single-port 2>&1 | tee reflex.log`,
  read the port out of `reflex.log` (do not assume 8000), open `/admin/audit`,
  enter `ADMIN_TOKEN`. Production mode has no hot reload: any fix means
  `kill -INT $(lsof -i :<port> -sTCP:LISTEN -t)` and a restart.
  Seed the database so all four verdicts are present, including a **fault** row
  with a real `error_message` and a **denied** row with a real
  `suspicious_pattern` — PRD Section 12 Phase 2's requirement, and the only way
  AC 2 and AC 3 are actually observed rather than inferred.
- **Validate**: the E2E checks below.

---

## End-to-End Tests

- [ ] Open `/admin/audit` authenticated, click a row's toggle → the detail opens
      beneath that row and the mark flips from `+` to `−`.
- [ ] Expand a **fault** row → `error_message` renders in full, wrapped, not
      truncated (AC 2).
- [ ] Expand a **denied** row → the actual `suspicious_pattern` string is shown
      (AC 3).
- [ ] Expand a row with PII → `PII in prompt` and `PII in response` appear as
      two separate lines with `detected` / `not detected`, and the PII types are
      listed (AC 4).
- [ ] Expand a **cleared** row with no error and no pattern → both fields read
      `—`, and the PII lines read `not detected`; no blank cell anywhere (AC 5).
- [ ] View source / DevTools on an open disclosure → neither `prompt_preview`
      nor `response_preview` content appears (AC 6).
- [ ] Tab to a row's toggle → a visible focus ring; Enter and Space both open
      and close it; no pointer used (AC 7).
- [ ] Open four disclosures, close the second → the other three stay open
      (AC 8).
- [ ] Open a disclosure, then re-sort or filter (STORY-013 is not built yet —
      set `AdminState.sort_key` by hand or re-`Refresh`) → the disclosure is
      still on the same `#audit_id`, not on the same screen position.
- [ ] Open a disclosure, **Sign out**, sign back in → every disclosure is closed.
- [ ] Narrow the viewport → the table scrolls sideways inside its own container;
      the page does not scroll horizontally, and the open detail wraps rather
      than widening the grid.
- [ ] With DevTools' colour picker on an open row: no fill, no card, no colour
      outside the four verdict inks and the ground tokens (the focus ring's
      `INK_UPSTREAM` is the known, documented exception — `tests/test_admin_palette.py`'s
      docstring records it).

## Validation

```bash
cd chat_ui && reflex compile --dry
cd .. && python -m pytest tests/test_register.py tests/test_admin_state.py tests/test_copy.py tests/test_admin_palette.py tests/test_contrast.py -q
python -m pytest -q          # the whole suite: app/ is untouched and must stay green
```

---

## Acceptance Criteria

(Copied from story `STORY-012`)

- [ ] Given any register row, when its disclosure is opened, then it shows
      `prompt_hash`, `error_message`, the PII entity types, the full User-Agent
      string and `suspicious_pattern`.
- [ ] Given a row marked **fault**, when it is expanded, then its
      `error_message` is rendered in full — a value `GET /audit` does not return
      at all.
- [ ] Given a row marked **denied**, when it is expanded, then the actual
      `suspicious_pattern` is shown, not the flattened boolean
      `AuditQueryEntry` exposes.
- [ ] Given a row with PII, when it is expanded, then `pii_detected_input` and
      `pii_detected_output` are shown **split**, having been shown combined as a
      single indicator in the row.
- [ ] Given a row with no error and no pattern, when it is expanded, then the
      empty fields are stated as absent rather than rendering blank cells.
- [ ] Given the disclosure, when it renders, then it exposes no `prompt_preview`
      and no `response_preview`.
- [ ] Given a keyboard user, when they reach a row's disclosure control, then it
      is focusable with visible focus and operable without a pointer.
- [ ] Given many rows, when several disclosures are opened, then each row's open
      state is independent and closing one does not close the others.
- [ ] All tasks completed
- [ ] `reflex compile --dry` passes
- [ ] Full pytest suite passes
- [ ] No card, no fill, no accent, no tint on the disclosure (Risk 6)
- [ ] Follows existing patterns
