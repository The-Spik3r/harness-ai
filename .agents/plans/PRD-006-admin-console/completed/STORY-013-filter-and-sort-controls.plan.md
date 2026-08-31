---
story: STORY-013
prd: PRD-006
slug: filter-and-sort-controls
title: "Verdict multi-select, free-text filter and sort controls on the register"
type: feature
complexity: MEDIUM
epic_branch: epic/PRD-006-admin-console
created: 2026-08-31
---

# Plan: Verdict multi-select, free-text filter and sort controls on the register

## Summary

STORY-005 already built every piece of filtering machinery — `selected_verdicts`,
`search`, `sort_key`, `sort_descending`, the `visible_rows` computed var, the
`filters_active` var, and the four event handlers `toggle_verdict`, `set_search`,
`sort_by` and `clear_filters`. STORY-008 already declared every string these
controls need. This story is **the surface only**: a filter strip hung on the
right-hand side of the register's existing scope strip (`register.py:_scope_line`'s
container, built as a strip in STORY-011 for exactly this), carrying a verdict
multi-select, a free-text field, a sort cluster and a clear action — all as plain
`rx.el.button`s and one `rx.input`, drawing no fill and no accent, and writing
nothing but the handlers that already exist.

Two supporting edits fall out of it and are named as tasks rather than smuggled in:
a `register_filtered` computed var on `AdminState` (AC 4's row count cannot be
formatted in a component — `REGISTER_FILTERED_TEMPLATE` is a Python format string
and components receive Vars), and one selector addition in `theme.py`'s
`GLOBAL_CSS` so Radix does not paint the new field's text with its own colour
token, which is the failure `admin_shell.py:_view_link` already records for
`rx.link`.

## User Story

As a compliance admin
I want to filter the register to one verdict or one user and to look up an `audit_id` a user quoted
So that a support report resolves to a specific row instead of a paraphrase

## Story Reference

- Story file: `.agents/stories/PRD-006-admin-console/STORY-013-filter-and-sort-controls.md`
- PRD: `.agents/PRDs/PRD-006-admin-console/PRD.md` — Section 4, Section 5 (stories 4, 5), Section 6.1, Section 7, Section 12 Phase 2, Risk 5, Risk 6

## Metadata

| Field | Value |
|-------|-------|
| Type | feature |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/` only — no change under `app/` |
| Story | STORY-013 |
| PRD | PRD-006 |
| Epic Branch | `epic/PRD-006-admin-console` (commit directly on this branch) |

**Dependencies verified**: STORY-005 `done`, STORY-008 `done`, STORY-011 `done`.

---

## Skills In Use

| Skill | Rule from the skill / AGENTS.md | Tasks affected |
|-------|---------------------------------|----------------|
| **reflex-docs** (`reflex:reflex-docs`) | `chat_ui/AGENTS.md`, verbatim: *"For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory."* The story adds: *"Confirm the current multi-select / toggle-group component and its event signature there — do not recall it."* **Done in planning; findings below.** | Tasks 2, 3, 4 |
| **frontend-design** (`.agents/skills/frontend-design/SKILL.md`) | *"A control should say exactly what happens when it's used: 'Save changes,' not 'Submit.'"* — every label comes from `admin_copy`, which already carries `CLEAR_FILTERS_LABEL = "Clear filters"`. Also: *"Spend your boldness in one place"* — the stamp margin is that place, so these controls draw hairlines and ink only. And: *"Build to a quality floor without announcing it: responsive down to mobile, visible keyboard focus."* | Tasks 3, 4, 5 |
| **reflex-process-management** | `chat_ui/AGENTS.md`: any run/compile/restart cycle follows this skill. Only needed for the E2E pass. | E2E section |

### reflex-docs findings (verified against the pinned build, not recalled)

`reflex==0.9.6.post1` / `reflex_components_radix==0.9.5`, read from the installed
package rather than from memory:

1. **There is no `rx.toggle_group`.** The pinned Radix component set is
   `checkbox`, `checkbox_cards`, `checkbox_group`, `radio`, `radio_cards`,
   `radio_group`, `segmented_control`, `select`, `switch`, `tabs`. No toggle group
   exists to reach for.
2. **`rx.checkbox_group.root` is uncontrolled.** `CheckboxGroupRoot` declares
   `default_value`, `name`, `size`, `variant`, `color_scheme`, `high_contrast` —
   and **no `value` prop and no `on_change` event**. It cannot be driven from
   `AdminState.selected_verdicts`, so it is not a candidate.
3. **`rx.segmented_control.root(type="multiple")` exists and is controlled.**
   `SegmentedControlRoot` declares `type: Literal["single", "multiple"]`, `value`,
   `default_value`, and `on_change: EventHandler[on_value_change]` where
   `on_value_change(value: Var[str | list[str]]) -> (value,)` — i.e. the handler
   receives **one argument: the whole selection as a list** under
   `type="multiple"`.
4. **Neither Radix candidate fits this surface**, for two independent reasons:
   - `SegmentedControlRoot.variant` is `"classic" | "surface"` and it carries
     `color_scheme: LiteralAccentColor`. Both variants are **fills**, which PRD-006
     Risk 6 and Section 6.1 rule out ("no cards, no fills, and no accent colour"),
     and the accent is supplied at compile time — the failure mode
     `admin_shell.py:_view_link` records for `rx.link` and `register.py`'s
     docstring records for `rx.accordion`, invisible to a source grep and caught
     only by `tests/test_register.py::test_no_colour_outside_the_allowed_set`.
   - Its `on_change` hands over a **list**, but `AdminState.toggle_verdict(verdict)`
     takes **one verdict string**. Wiring it would mean adding a
     `set_selected_verdicts`-shaped handler to `admin_state.py`, which is STORY-005's
     territory and which the story's own note forbids: *"The state and the computed
     var are STORY-005; this story is the controls only."*

   → **Decision: four `rx.el.button`s with `aria-pressed`, one per verdict**, wired
   to the existing `toggle_verdict`. This is the same shape `register.py:_toggle_button`
   already uses for the disclosure control, gives Enter/Space and tab order for free,
   and takes its focus ring from `theme.GLOBAL_CSS`'s `:focus-visible`.
5. **Risk 5 is already mitigated by the framework.** `TextFieldRoot.create` ends with:
   *"if `props.get("value") is not None and props.get("on_change") is not None:*
   *return DebounceInput.create(component)"*, and
   `reflex_components_core.core.debounce.DEFAULT_DEBOUNCE_TIMEOUT = 300`. So an
   `rx.input` given both `value` and `on_change` is **automatically debounced at
   300 ms** — `visible_rows` re-evaluates on a pause, not on a keystroke. No manual
   debounce is needed, and `debounce_timeout=<ms>` passes through `rx.input` if it
   ever needs tuning. `rx.debounce_input` also exists in core as the escape hatch
   for a non-Radix input.
6. **`Var.contains()`, not `in`.** Already the established form in this file
   (`register.py:_is_open`); the verdict chip's selected test is
   `AdminState.selected_verdicts.contains(key)`.
7. **Var boolean `|`** is the supported form for the timestamp-default test
   (`sort_key == ""` **or** `sort_key == "timestamp"`); Python `or` short-circuits
   on a Var and is wrong.

---

## Patterns to Follow

### A control that is a real button, drawing no chrome

```python
# SOURCE: chat_ui/chat_ui/components/register.py:_toggle_button (lines ~250-280)
return rx.el.button(
    mark,
    on_click=AdminState.toggle_detail(row.audit_id),
    type="button",              # unqualified <button> defaults to submit
    cursor="pointer",
    background="none",
    border="none",
    padding="0",
    font_family=theme.FONT_DATA,
    font_size=theme.TEXT_DATA,
    color=theme.MUTE,
    _hover={"color": theme.INK},
    custom_attrs={"aria-label": label, "aria-expanded": expanded},
)
```

### Two full variants inside one `rx.cond`, because the styling branches on a Var

```python
# SOURCE: chat_ui/chat_ui/components/register.py:_disclosure_toggle
rx.cond(
    _is_open(row),
    _toggle_button(row, admin_copy.DETAIL_TOGGLE_CLOSE_MARK, ..., "true"),
    _toggle_button(row, admin_copy.DETAIL_TOGGLE_OPEN_MARK, ..., "false"),
)
```

### A controlled field, with the id `theme.py` needs to reach its text

```python
# SOURCE: chat_ui/chat_ui/components/admin_shell.py:admin_gate
rx.input(
    id="admin_token_input",      # Radix paints the real <input> inside its wrapper
    class_name="hx-field-boxed", # standalone field keeps a real frame
    value=AdminState.token_input,
    on_change=AdminState.set_token_input,
    placeholder=admin_copy.GATE_PLACEHOLDER,
    font_family=theme.FONT_DATA,
    height="2.5rem",
    border_radius=theme.RADIUS,
)
```

```css
/* SOURCE: chat_ui/chat_ui/theme.py:GLOBAL_CSS */
#chat_input, #user_id_input, #admin_token_input {
  color: {INK} !important;
  background: transparent;
}
```

### A scope statement as a computed var, because the format string is Python-side

```python
# SOURCE: chat_ui/chat_ui/admin_state.py:register_scope
@rx.var
def register_scope(self) -> str:
    return REGISTER_SCOPE_TEMPLATE.format(
        shown=format_count(len(self.rows)),
        total=format_count(self.total_recorded),
    )
```

### Tests: a build probe in a subprocess, plus source assertions

```python
# SOURCE: tests/test_register.py:186-215, 370-400
factories = [("register", lambda: register()), ("_column_head", lambda: _column_head()), ...]
...
@pytest.mark.parametrize("name", COPY_NAMES)
def test_every_string_is_read_from_admin_copy(source, name):
    assert f"admin_copy.{name}" in source
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/admin_state.py` | UPDATE | Add the `register_filtered` computed var (AC 4's count). No filtering logic added. |
| `chat_ui/chat_ui/theme.py` | UPDATE | Add `#register_filter_input` to `GLOBAL_CSS`'s two Radix-text selector lists. |
| `chat_ui/chat_ui/components/register.py` | UPDATE | The verdict chips, the free-text field, the sort cluster, the clear action, and the two-column filter strip that holds them. |
| `tests/test_register.py` | UPDATE | Extend `COPY_NAMES`, add the control factories to the probe, add AC-level assertions, and raise the `FONT_BODY` count to 2. |
| `chat_ui/chat_ui/admin_copy.py` | **NO CHANGE** | Verified: every label these controls need already exists (`FILTER_VERDICT_LABEL`, `FILTER_SEARCH_LABEL`, `FILTER_SEARCH_PLACEHOLDER`, `CLEAR_FILTERS_LABEL`, `SORT_LABEL`, `SORT_TIMESTAMP_LABEL`, `SORT_USER_LABEL`, `SORT_VERDICT_LABEL`, `SORT_ASCENDING_MARK`, `SORT_DESCENDING_MARK`, `VERDICT_*_LABEL`, `REGISTER_FILTERED_TEMPLATE`). |
| `app/**` | **NO CHANGE** | PRD-006 Section 4: any change under `app/` is out of scope. |

### Layout (PRD-006 Section 6.1's wireframe, filled in)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 100 most recent of 3,180          Verdict  cleared held DENIED FAULT     │  row A
│ 12 of 100 shown                   Find [ user, model or id ]             │  row B
│ ^ only when filters_active        Sort Time↓ User Verdict   Clear filters│
├─┬────────────────────────────────────────────────────────────────────────┤
│▉│ 2m ago   a.torres   DENIED   …                                         │
```

Left column: the two scope statements, stacked. Right column: two control rows.
The refreshed stamp the wireframe shows at row B's left edge is **STORY-017's**,
and that slot is deliberately left free for it rather than filled here.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: The filtered row count, as a computed var

- **File**: `chat_ui/chat_ui/admin_state.py`
- **Action**: UPDATE
- **Implement**:
  - Add `REGISTER_FILTERED_TEMPLATE` to the existing `from .admin_copy import (...)` block.
  - Add a `register_filtered` computed var directly after `register_scope`:
    ```python
    @rx.var
    def register_filtered(self) -> str:
        return REGISTER_FILTERED_TEMPLATE.format(
            shown=format_count(len(self.visible_rows)),
            total=format_count(len(self.rows)),
        )
    ```
    (`REGISTER_FILTERED_TEMPLATE` is `"{shown} of {loaded} shown"` — use the
    keyword names the constant actually declares: `shown` and `loaded`.)
  - Docstring must record **why this is here and not in the component**: the
    template is a Python format string and `format_count` is Python-side thousands
    separation, neither of which can run against a Var — the same reason
    `register_scope` is a computed var. And **why it is not the scope line**:
    `admin_copy` states it directly — *"the scope states the window, this states
    how much of the window survived the filter"* — so the two are separate
    statements and one must not replace the other (AC 4).
  - Read both `self.visible_rows` and `self.rows` **in this body**, per the
    dependency-tracking rule `visible_rows` already records.
- **Scope note**: the story says filtering logic belongs to STORY-005. This adds
  **no** filtering logic — it is a display string over vars STORY-005 already
  computed, and `admin_copy`'s own comment on `REGISTER_FILTERED_TEMPLATE` assigns
  it to STORY-013. A computed var is also outside `base_vars`, so
  `test_sign_out_clears_every_declared_var` is unaffected.
- **Mirror**: `chat_ui/chat_ui/admin_state.py:register_scope`
- **Validate**: `python -m pytest tests/test_admin_state.py -q` (all green, nothing new expected to fail)

### Task 2: Let the new field's text be visible

- **File**: `chat_ui/chat_ui/theme.py`
- **Action**: UPDATE
- **Implement**: add `#register_filter_input` to **both** id selector lists in
  `GLOBAL_CSS` — the `color/background` rule and the `::placeholder` rule — and
  update the comment above them from *"Three fields need it"* to four, naming the
  register's filter field.
- **Why**: Radix paints the real `<input>` inside its `TextFieldRoot` wrapper, so
  inline props on the wrapper never reach the typed text. The comment already in
  `theme.py` states this; a fourth field that skips the selector renders its text
  in Radix's own resolved token.
- **Mirror**: `chat_ui/chat_ui/theme.py:GLOBAL_CSS` (`#chat_input, #user_id_input, #admin_token_input`)
- **Validate**: `python -m pytest tests/test_contrast.py tests/test_admin_palette.py -q`

### Task 3: The verdict multi-select

- **File**: `chat_ui/chat_ui/components/register.py`
- **Action**: UPDATE
- **Implement**:
  - A module-level `_VERDICT_CHIPS` tuple pairing each verdict **key** (imported
    from `admin_formatting`, already imported here) with its **label** from
    `admin_copy` and its **ink** from `theme`:
    `((VERDICT_CLEARED, admin_copy.VERDICT_CLEARED_LABEL, theme.INK_CLEAR), (VERDICT_HELD, …), (VERDICT_DENIED, …), (VERDICT_FAULT, …))`.
    Built in Python because the four verdicts are plain strings, not Vars.
  - `_chip_button(key, label, ink, selected: bool)` → `rx.el.button` with
    `on_click=AdminState.toggle_verdict(key)`, `type="button"`, no background, no
    border, `font_family=theme.FONT_DISPLAY`, `font_size=theme.TEXT_TAG`, and the
    **same case treatment `_tag` applies**: caps + letter-spacing for the three
    exceptions, lowercase for `cleared`, applied with `text_transform` so the chip
    can never disagree with the row's tag.
  - **Selection is marked without a fill** (Risk 6, and the story: *"may carry
    their verdict ink as text, not as a fill"*): unselected → `color=theme.MUTE`,
    `font_weight="500"`, `border_bottom=f"1px solid transparent"`; selected →
    `color=ink`, `font_weight="600"`, `border_bottom=f"2px solid {ink}"` with
    `padding_bottom` to seat the rule. Two channels (ink + rule), plus
    `custom_attrs={"aria-pressed": "true"/"false"}` as the third, for a screen
    reader. `_hover={"color": theme.INK}` on the unselected variant only.
  - `_verdict_filter()` → an `rx.hstack` of `admin_copy.FILTER_VERDICT_LABEL` set
    with `_control_label()` (see Task 5) followed by
    `rx.cond(AdminState.selected_verdicts.contains(key), _chip_button(..., True), _chip_button(..., False))`
    per chip. Both variants must be built — the styling branches on a Var, which is
    the `_disclosure_toggle` pattern.
- **Mirror**: `chat_ui/chat_ui/components/register.py:_disclosure_toggle` + `_tag`
- **Validate**: `python -m pytest tests/test_register.py -q`

### Task 4: The free-text field and the sort cluster

- **File**: `chat_ui/chat_ui/components/register.py`
- **Action**: UPDATE
- **Implement**:
  - `_search_field()`:
    ```python
    rx.input(
        id="register_filter_input",
        class_name="hx-field-boxed",
        value=AdminState.search,
        on_change=AdminState.set_search,
        placeholder=admin_copy.FILTER_SEARCH_PLACEHOLDER,
        custom_attrs={"aria-label": admin_copy.FILTER_SEARCH_LABEL,
                      "autoComplete": "off"},
        width="13rem",
        font_family=theme.FONT_DATA,
        font_size=theme.TEXT_DATA,
        height="1.75rem",
        border_radius=theme.RADIUS,
    )
    ```
    preceded by `_control_label(admin_copy.FILTER_SEARCH_LABEL)` as the visible
    label. `value` + `on_change` together are what trigger the automatic
    `DebounceInput` wrap at 300 ms — Risk 5's mitigation, by construction. Do not
    add a manual debounce.
  - `_SORT_MARKS`: a module-level `dict[str, tuple[str, str]]` giving
    `(mark when sort_descending is False, mark when True)` per key, so each glyph
    is literally true of what an admin sees. `sort_descending=False` is
    `sort_rows`' documented **natural** order:
    - `SORT_TIMESTAMP`: `(DESCENDING_MARK, ASCENDING_MARK)` — natural is newest
      first, i.e. time descending down the page.
    - `SORT_USER`: `(ASCENDING_MARK, DESCENDING_MARK)` — natural is A→Z.
    - `SORT_VERDICT`: `(DESCENDING_MARK, ASCENDING_MARK)` — natural is
      exceptions first, i.e. severity descending.
    Chosen per key in Python (the keys are plain strings), so no single glyph has
    to mean three different things. Record this reasoning in a comment.
  - `_is_sorted_by(key)`: for `SORT_TIMESTAMP`, `(AdminState.sort_key == key) | (AdminState.sort_key == "")`
    — the register's default is carried by `sort_key == ""`, which `sort_rows`
    reads as the loaded order, so the timestamp control must show as active on a
    fresh page (AC 6: *"timestamp descending remains the default"*). For the other
    two, `AdminState.sort_key == key`. Var `|`, never Python `or`.
  - `_sort_control(key, label)`: `rx.el.button` on
    `on_click=AdminState.sort_by(key)`, `type="button"`, `FONT_DISPLAY` /
    `TEXT_TAG`. `rx.cond(_is_sorted_by(key), <active>, <inactive>)` where active is
    `color=theme.INK`, `font_weight="600"`, `aria-pressed="true"`, and carries the
    direction mark via
    `rx.cond(AdminState.sort_descending, _SORT_MARKS[key][1], _SORT_MARKS[key][0])`
    as a second child; inactive is `color=theme.MUTE`, `font_weight="500"`,
    `aria-pressed="false"`, no mark.
  - `_sort_controls()`: `_control_label(admin_copy.SORT_LABEL)` then the three
    controls, pairing `SORT_TIMESTAMP/SORT_USER/SORT_VERDICT` (imported from
    `admin_state`) with `SORT_TIMESTAMP_LABEL/SORT_USER_LABEL/SORT_VERDICT_LABEL`.
  - `_clear_control()`: `rx.cond(AdminState.filters_active, <button>, rx.fragment())`
    — a clear action shown against nothing to clear is the *"control that does
    nothing"* `admin_shell.py:_view_link` already refuses. Label
    `admin_copy.CLEAR_FILTERS_LABEL`, `on_click=AdminState.clear_filters`,
    `type="button"`, `color=theme.MUTE`, `text_decoration="underline"`,
    `text_underline_offset="3px"`, `_hover={"color": theme.INK}` — the sign-out
    button's treatment, so a text action reads the same on both surfaces.
- **Mirror**: `chat_ui/chat_ui/components/admin_shell.py` (sign-out button, gate input)
- **Validate**: `python -m pytest tests/test_register.py -q`

### Task 5: The filter strip, and the filtered-count line

- **File**: `chat_ui/chat_ui/components/register.py`
- **Action**: UPDATE
- **Implement**:
  - `_control_label(label)`: the shared eyebrow for `Verdict` / `Find` / `Sort` —
    the `_head_cell` treatment (`FONT_DISPLAY`, `TEXT_MICRO`, `600`,
    `letter_spacing="0.1em"`, uppercase, `color=theme.MUTE`) without the
    `role="columnheader"`, since these label controls, not columns.
  - `_filtered_line()`: `rx.cond(AdminState.filters_active, rx.box(AdminState.register_filtered, font_family=theme.FONT_BODY, …, color=theme.MUTE), rx.fragment())`.
    Only when a filter is active — `100 of 100 shown` under an unfiltered register
    is noise, and `filters_active` deliberately excludes sort.
  - Rework `register()`'s first child from a bare scope line into the strip:
    ```
    rx.flex(
        rx.vstack(_scope_line(), _filtered_line(), spacing="0", align="start"),
        rx.vstack(
            _verdict_filter(),
            rx.flex(_search_field_row(), _sort_controls(), _clear_control(),
                    wrap="wrap", align="center", gap="1rem"),
            spacing="2", align="end",
        ),
        justify="between", align="start", wrap="wrap", gap="1rem",
        padding="0.75rem 1.5rem",
        border_bottom=f"1px solid {theme.RULE}",
        flex_shrink="0", width="100%",
    )
    ```
    `wrap="wrap"` on both flex rows is the whole narrow-viewport answer — the
    clusters stack rather than compress, the same move
    `admin_shell.py:admin_masthead` makes with `flex_wrap`. No new CSS.
  - Update `register()`'s and the module's docstrings: the strip is no longer
    *"STORY-013 hangs … on its right-hand side"* but the thing itself; keep the
    note that STORY-014's three-way empty-state condition still wraps the table
    and that STORY-017's refreshed stamp takes the free slot at row B's left.
- **Mirror**: `chat_ui/chat_ui/components/admin_shell.py:admin_masthead` (wrap-based responsive header)
- **Validate**: `python -m pytest tests/test_register.py -q && python -m pytest -q`

### Task 6: Extend the register's tests

- **File**: `tests/test_register.py`
- **Action**: UPDATE
- **Implement**:
  - Add to `COPY_NAMES`: `FILTER_VERDICT_LABEL`, `FILTER_SEARCH_LABEL`,
    `FILTER_SEARCH_PLACEHOLDER`, `CLEAR_FILTERS_LABEL`, `SORT_LABEL`,
    `SORT_TIMESTAMP_LABEL`, `SORT_USER_LABEL`, `SORT_VERDICT_LABEL`,
    `SORT_ASCENDING_MARK`, `SORT_DESCENDING_MARK`. (AC 8 — every label greps back
    to `admin_copy`. Note `test_no_copy_value_is_written_as_a_literal` will then
    also assert none of these values is typed in the component.)
  - Add the new factories to `_CHECK_SCRIPT`'s import list and `factories`:
    `_verdict_filter`, `_search_field`, `_sort_controls`, `_clear_control`,
    `_filtered_line` — and capture `built["strip"]` for the assertions below.
  - New tests:
    - `test_every_verdict_is_offered_as_a_filter` — the four labels reach the
      compiled strip (AC 1).
    - `test_the_verdict_filter_writes_the_state_handler` — `toggle_verdict`
      appears in the rendered output and no `app.db` symbol does (AC 2: no
      database read).
    - `test_the_free_text_field_is_bound_to_the_search_var` — `search` and
      `set_search` in the output (AC 3).
    - `test_the_field_is_debounced_by_construction` — `DebounceInput` appears in
      the compiled field, which is what makes Risk 5's mitigation checkable
      rather than assumed.
    - `test_the_filtered_count_is_bound_to_the_state` — `register_filtered` in
      the output and `register_scope` still separately present (AC 4).
    - `test_the_clear_action_is_conditional_on_filters_active` — both
      `filters_active` and `clear_filters` in the output (AC 5).
    - `test_each_sort_key_has_a_control` and
      `test_the_timestamp_default_is_treated_as_active` — the source contains the
      `sort_key == ""` disjunction (AC 6).
    - `test_every_control_is_a_real_button` — `rx.el.button` count in the source
      covers the chips, the sort controls and the clear action; `<button` appears
      in the compiled strip (AC 7).
  - **Update `test_body_face_appears_only_on_the_scope_line`**: assert `== 2` and
    rewrite the docstring to name both scope statements. PRD-006 Section 6.1
    reserves `FONT_BODY` for *"the two or three explanatory lines that state a
    scope"*; the filtered count is the second such line, and setting it in a
    different face would say the two statements are different kinds of thing.
    Rename the test to `test_the_body_face_is_reserved_for_the_scope_lines`.
- **Mirror**: `tests/test_register.py` (existing probe + source-assertion split)
- **Validate**: `python -m pytest tests/test_register.py -q`

---

## End-to-End Tests

Follow the **reflex-process-management** skill for the run/compile cycle.

- [ ] `python -m pytest -q` — the whole suite green, including
      `tests/test_route_reservations.py`, `tests/test_audit_router.py`,
      `tests/test_stats_router.py` and `tests/test_db.py` unmodified (PRD-006
      Section 3's integrating-developer guarantee).
- [ ] Start the app, sign in at `/admin/audit` with `ADMIN_TOKEN`, and confirm the
      strip renders with the verdict chips on the scope line and the text field
      under it (AC 1).
- [ ] Toggle **denied** → the table narrows, the chip takes its ink and its rule,
      and no database read occurs (watch the server log; `visible_rows` is
      synchronous) (AC 2).
- [ ] Type an `audit_id` visible in the window (e.g. the newest row's) into the
      field → that row is isolated (AC 3).
- [ ] With **denied** selected *and* a user typed, confirm the two compose as AND
      and that `{n} of {loaded} shown` appears beneath `100 most recent of {total}`
      as a **second, distinct** line (AC 4).
- [ ] Use **Clear filters** → both filters reset, the filtered line disappears, the
      full window returns, and the sort is untouched (AC 5).
- [ ] Click **Time**, **User**, **Verdict** in turn, then click the active one
      again → the table reorders, the active control is marked and the direction
      mark flips; on a fresh load **Time** is already marked active (AC 6).
- [ ] Tab from the masthead through the strip → every chip, the field, all three
      sort controls and the clear action take focus in order, each shows the
      `:focus-visible` ring, and Enter/Space operates each button (AC 7).
- [ ] Narrow the viewport to ~40rem → the strip's clusters wrap rather than
      compress; the table keeps its own horizontal scroll (quality floor).
- [ ] `grep -n '"' chat_ui/chat_ui/components/register.py` → no user-facing string
      literal; every label reads `admin_copy.` (AC 8).

---

## Validation

```bash
python -m pytest tests/test_register.py tests/test_admin_state.py tests/test_admin_palette.py tests/test_contrast.py tests/test_copy.py -q
python -m pytest -q
```

---

## Risks & Mitigations

| # | Risk | Mitigation |
|---|------|------------|
| 1 | **`rx.input` is Radix and may inject a hex colour at compile time**, which `test_no_colour_outside_the_allowed_set` would catch as a failure — the same class of failure `admin_shell.py:_view_link` records for `rx.link`'s accent. | Run that test as soon as Task 4 lands. Radix Themes resolves most colours to CSS custom properties rather than hex, so this is expected to pass. **Fallback if it does not**: swap to `rx.debounce_input(rx.el.input(...), debounce_timeout=300)` — plain HTML, no Radix, no accent, and Task 2's `theme.py` selector addition then becomes unnecessary and must be reverted. |
| 2 | **PRD Risk 5** — every keystroke re-evaluates `visible_rows` over 100 rows. | Already mitigated by the pinned build: `rx.input` with `value` + `on_change` auto-wraps in `DebounceInput` at 300 ms (verified in `text_field.py` / `debounce.py`). Task 6 asserts `DebounceInput` reaches the output so the mitigation is checkable rather than assumed. |
| 3 | **PRD Risk 6** — a fill or an accent creeping onto the register. | No `background_color` on any control; selection is ink + a 2px bottom rule in the same ink. `tests/test_register.py::test_no_colour_outside_the_allowed_set` and `test_no_tint_reaches_the_output` hold the line over the compiled output. |
| 4 | **The sort direction glyph** cannot mean one thing across three heterogeneous keys — `sort_descending=False` is "newest first" for timestamp but "A→Z" for user. | `_SORT_MARKS` picks the pair per key in Python, so each glyph is literally true of the list an admin is looking at. Recorded in a comment at the constant. |
| 5 | **Scope creep into STORY-005's state.** | Exactly one addition to `admin_state.py`, and it is a display string (`register_filtered`) over vars STORY-005 already computes — no new filtering logic, no new filter var, no change to `visible_rows` or the four handlers. `admin_copy` already assigns `REGISTER_FILTERED_TEMPLATE` to this story. |
| 6 | **Collision with STORY-017's refreshed stamp**, which the wireframe places at row B's left edge. | The strip's left column holds only the two scope statements; row B's left slot is left empty for STORY-017 rather than filled. Called out in `register()`'s docstring. |
| 7 | **STORY-014 wraps this surface next.** | `register()` keeps rendering the table unconditionally; STORY-014 supplies the three-way condition around it. Nothing here assumes a non-empty `visible_rows`. |

---

## Acceptance Criteria

(Copied from story `STORY-013`)

- [ ] Given the register header, when it renders, then it carries a verdict multi-select over the four verdicts and a free-text field over `user_id` / `model_used` / `audit_id`, positioned as PRD Section 6.1's wireframe shows.
- [ ] Given the verdict multi-select, when a verdict is toggled, then the table narrows without a database read and the selected verdicts are visibly marked.
- [ ] Given the free-text field, when `127` is typed, then the row whose `audit_id` is 127 is isolated — closing PRD-004's chat-footer loop.
- [ ] Given both filters active, when the table renders, then they compose as AND and the row count shown reflects the filtered set, distinct from the "100 most recent of {total}" scope line.
- [ ] Given active filters, when a clear action is used, then all filters reset and the full window returns.
- [ ] Given the sort controls, when timestamp, user or verdict is chosen, then the table reorders and the active sort is visibly indicated; timestamp descending remains the default.
- [ ] Given a keyboard user, when they tab through the filter and sort controls, then each is reachable and operable with visible focus.
- [ ] Given every label on these controls, when grepped, then each resolves from `admin_copy`.
- [ ] All tasks completed
- [ ] `python -m pytest -q` passes, with `app/` and its test suites unmodified
- [ ] Reflex app compiles and the register renders without error
- [ ] Follows existing patterns
