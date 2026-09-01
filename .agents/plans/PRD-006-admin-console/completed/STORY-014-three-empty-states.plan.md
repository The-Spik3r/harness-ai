---
story: STORY-014
prd: PRD-006
slug: three-empty-states
title: "Three distinct register states: nothing recorded, nothing matching, rows shown"
type: feature
complexity: LOW
epic_branch: epic/PRD-006-admin-console
created: 2026-08-31
---

# Plan: Three distinct register states: nothing recorded, nothing matching, rows shown

## Summary

`register()` renders its table unconditionally today — STORY-013's plan left that
seam open on purpose ("STORY-014 supplies the three-way condition around it").
This story supplies it, and supplies it **once, in Python**: a
`AdminState.register_state` computed var that returns one of four keys —
`read_failed`, `no_rows`, `no_matches`, `rows` — evaluated in that precedence, and
an `rx.match` over it inside the register's scroll container. Putting the
precedence in a computed var rather than in nested `rx.cond`s is what makes the
story's hardest requirement testable in plain pytest: AC 4 says a failed read must
never render as emptiness, and a nested-`rx.cond` ordering can only be checked by
reading the compiled JS.

Every string the two empty panels need already exists — STORY-008 declared
`EMPTY_REGISTER_TITLE/BODY`, `EMPTY_MATCHES_TITLE`, `EMPTY_MATCHES_TEMPLATE` and the
three `FILTER_DESCRIPTION_*` parts, and reserved them for this story by name. The
no-matches sentence is assembled by a second computed var
(`AdminState.empty_matches_message`) for the reason `register_filtered` already
records: the templates are Python format strings over a thousands-separated count
and a joined verdict list, and component functions receive Vars.

The `read_failed` arm renders **the table**, not a panel: the fault panel is
STORY-017's, and `FAULT_MESSAGE_TEMPLATE` promises "Nothing on screen has changed",
so the previously loaded rows must stay on screen under it. What this story owns is
that the arm exists and that neither empty panel can be reached while `error` is
set.

## User Story

As a compliance admin
I want an empty register to tell me whether nothing was recorded or nothing matched my filter
So that a blank table is never ambiguous

## Story Reference

- Story file: `.agents/stories/PRD-006-admin-console/STORY-014-three-empty-states.md`
- PRD: `.agents/PRDs/PRD-006-admin-console/PRD.md` — Section 4 (register), Section 6.1 (copy), Section 12 Phase 2, Risk 6

## Metadata

| Field | Value |
|-------|-------|
| Type | feature |
| Complexity | LOW |
| Systems Affected | `chat_ui/` only — no change under `app/` |
| Story | STORY-014 |
| PRD | PRD-006 |
| Epic Branch | `epic/PRD-006-admin-console` (commit directly on this branch) |

**Dependencies verified**: STORY-005 `done` (`631bbff`), STORY-008 `done` (`cc857e7`),
STORY-011 `done` (`9228979`), STORY-013 `done` (`32efec0`). All four are ✅ in
`.agents/PRDs/PRD-006-admin-console/index.md`.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| **frontend-design** (`.agents/skills/frontend-design/SKILL.md`) | "Treat failure and emptiness as moments for direction, not mood… An empty screen is an invitation to act." Both panels end in the action available from them: the nothing-recorded panel points at **Refresh**, the no-matches panel carries **Clear filters** as a real control. | Tasks 3, 4 |
| **frontend-design** | "Errors don't apologize, and they are never vague about what happened." The precedence in Task 2 is the structural form of that rule — a failed read is never re-labelled as emptiness. | Task 2 |
| **frontend-design** | "Let each element do exactly one job" / restraint. AC 6: the panels use the register's existing type and rules — no illustration, no card, no accent colour, no border, no fill. | Tasks 3, 4 |
| **frontend-design** | "An action keeps the same name through the whole flow." The no-matches panel reuses `_clear_control()` itself rather than declaring a second clear button. | Task 4 |
| **reflex-docs** (skill, via `chat_ui/AGENTS.md`) | Not listed on the story, but the story's own note about render-time conditions is a Reflex API claim. Confirm `rx.match` over a `str` computed var and its required default arm before writing Task 4. | Task 4 |

Note: the story lists only `frontend-design`. `.agents/skills/` contains exactly one
skill directory (`frontend-design`); `reflex-docs` is the plugin skill
`chat_ui/AGENTS.md` mandates for Reflex API questions, and it is named here for that
reason rather than as a story field.

---

## Patterns to Follow

### A render state chosen in Python, rendered with `rx.match`

```python
# SOURCE: chat_ui/chat_ui/components/register.py:200-235 (_verdict_tag)
# The register already branches with rx.match over a str field computed
# Python-side. register_state is the same move one level up.
```

### A display string built as a computed var, never in the component

```python
# SOURCE: chat_ui/chat_ui/admin_state.py:392-425 (register_filtered)
    @rx.var
    def register_filtered(self) -> str:
        return REGISTER_FILTERED_TEMPLATE.format(
            shown=format_count(len(self.visible_rows)),
            loaded=format_count(len(self.rows)),
        )
```

Both dependencies are read off `self` **in the body** — Reflex's auto-dependency
tracker disassembles the function and records only the attributes loaded there. Its
failure mode is a `console.warn` and an empty dependency set, not an exception.

### The empty-state shape, tonally

```python
# SOURCE: chat_ui/chat_ui/components/shell.py:146-190 (empty_state)
# Title in FONT_DISPLAY over a body line in FONT_BODY, left-aligned, no card,
# no fill, no icon. Read as the tonal precedent — NOT imported and NOT reused:
# PRD-006 Section 4 forbids an admin page rendering a chat component, and
# tests/test_register.py::test_source_imports_no_chat_component enforces it.
```

### A control that appears only when it has something to do

```python
# SOURCE: chat_ui/chat_ui/components/register.py:_clear_control
    return rx.cond(
        AdminState.filters_active,
        _control_button(admin_copy.CLEAR_FILTERS_LABEL, on_click=AdminState.clear_filters, ...),
        rx.fragment(),
    )
```

### The copy, already written for this story

```python
# SOURCE: chat_ui/chat_ui/admin_copy.py — "--- The three empty states ---"
EMPTY_REGISTER_TITLE = "The register is empty."
EMPTY_REGISTER_BODY = "No prompt has passed through the harness yet. Refresh once traffic starts."
EMPTY_MATCHES_TITLE = "No rows match this filter."
EMPTY_MATCHES_TEMPLATE = "{filters} matched none of the {loaded} rows loaded."
FILTER_DESCRIPTION_VERDICT_TEMPLATE = "verdict {verdicts}"
FILTER_DESCRIPTION_SEARCH_TEMPLATE = 'text "{search}"'
FILTER_DESCRIPTION_JOIN = " and "
```

### Tests: the subprocess probe, because the app imports as `chat_ui.components…`

```python
# SOURCE: tests/test_register.py:186-300 (_CHECK_SCRIPT + probe fixture)
# New factories are appended to the `factories` list and captured into
# `result[...]`, so a test about the empty panels fails when the panels break.
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/admin_copy.py` | UPDATE | One constant: `FILTER_DESCRIPTION_VERDICT_JOIN`. Two selected verdicts need a separator on screen, and AC 5 requires every string on these panels resolve from `admin_copy`. |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | Four `REGISTER_STATE_*` keys, the `_VERDICT_LABELS` map, and the two computed vars `register_state` and `empty_matches_message`. |
| `chat_ui/chat_ui/components/register.py` | UPDATE | `_empty_panel`, `_empty_register`, `_no_matches`, `_table`, `_register_body`; `register()` rewired to render `_register_body()` instead of the table directly. |
| `tests/test_admin_state.py` | UPDATE | The precedence (all four states incl. AC 4's fault-before-empty), the sentence assembly, and the label-map/`VERDICTS` binding. |
| `tests/test_register.py` | UPDATE | New probe factories, per-panel assertions, the clear action inside the no-matches panel, no card/fill/illustration, and the `FONT_BODY` count moved 2 → 4 with its justification. |

No file is created. No file under `app/` is touched (PRD-006 Section 3).

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add the verdict-list separator to `admin_copy`

- **File**: `chat_ui/chat_ui/admin_copy.py`
- **Action**: UPDATE
- **Implement**: In the "The three empty states" block, beside
  `FILTER_DESCRIPTION_JOIN`, add:
  ```python
  # Between two selected verdicts inside FILTER_DESCRIPTION_VERDICT_TEMPLATE —
  # "verdict held, denied". Distinct from FILTER_DESCRIPTION_JOIN, which joins the
  # two *kinds* of filter ("verdict denied and text \"ana\""): one list, one
  # conjunction, and collapsing them would read as "verdict held and denied and
  # text …". A separate constant because AC 5 requires every string on these
  # panels resolve from admin_copy, and ", " typed in admin_state.py would not.
  FILTER_DESCRIPTION_VERDICT_JOIN = ", "
  ```
- **Mirror**: `chat_ui/chat_ui/admin_copy.py` — `MASTHEAD_SEPARATOR` is the
  precedent for a separator living as a named constant in this module.
- **Validate**: `python -c "from chat_ui.chat_ui import admin_copy; print(admin_copy.FILTER_DESCRIPTION_VERDICT_JOIN)"`

### Task 2: The precedence, as a computed var on `AdminState`

- **File**: `chat_ui/chat_ui/admin_state.py`
- **Action**: UPDATE
- **Implement**:
  1. Extend the `.admin_copy` import block with `EMPTY_MATCHES_TEMPLATE`,
     `FILTER_DESCRIPTION_JOIN`, `FILTER_DESCRIPTION_SEARCH_TEMPLATE`,
     `FILTER_DESCRIPTION_VERDICT_JOIN`, `FILTER_DESCRIPTION_VERDICT_TEMPLATE`,
     `VERDICT_CLEARED_LABEL`, `VERDICT_DENIED_LABEL`, `VERDICT_FAULT_LABEL`,
     `VERDICT_HELD_LABEL`. Extend the `.admin_formatting` import with the four
     `VERDICT_*` keys (`VERDICTS` is already imported).
  2. Module-level constants, beside `SORT_KEYS`:
     ```python
     # The register's four render states, in the order register_state resolves
     # them. Keys, not copy — the rx.match arms — so they live here with SORT_KEYS
     # and not in admin_copy.py, which holds words on screen.
     #
     # "read_failed" rather than "fault": VERDICT_FAULT_LABEL is the string
     # "fault", and a state key that collides with a copy value would make
     # tests/test_register.py::test_no_copy_value_is_written_as_a_literal
     # unreadable — it could no longer tell a hard-coded label from a state key.
     REGISTER_STATE_FAULT = "read_failed"
     REGISTER_STATE_EMPTY = "no_rows"
     REGISTER_STATE_NO_MATCHES = "no_matches"
     REGISTER_STATE_ROWS = "rows"
     REGISTER_STATES = (
         REGISTER_STATE_FAULT,
         REGISTER_STATE_EMPTY,
         REGISTER_STATE_NO_MATCHES,
         REGISTER_STATE_ROWS,
     )

     # One label per verdict key, in VERDICTS order. The same key/label separation
     # components/register.py:_VERDICT_CHIPS keeps — the key is the formatter's and
     # the filter's, the label is the word on screen — so the sentence naming the
     # filter cannot disagree with the chip that produced it.
     # tests/test_admin_state.py binds this to admin_formatting.VERDICTS so a fifth
     # verdict fails here rather than silently dropping out of the sentence.
     _VERDICT_LABELS = {
         VERDICT_CLEARED: VERDICT_CLEARED_LABEL,
         VERDICT_HELD: VERDICT_HELD_LABEL,
         VERDICT_DENIED: VERDICT_DENIED_LABEL,
         VERDICT_FAULT: VERDICT_FAULT_LABEL,
     }
     ```
  3. `register_state`, placed directly after `filters_active`:
     ```python
     @rx.var
     def register_state(self) -> str:
         """Which of the four the register is showing — decided once, in Python.

         **The order is the acceptance criterion.** PRD-006 Section 4 forbids a
         failed read being presented as emptiness, and a failed read very often
         *is* an empty `rows` — `load()` leaves the previously loaded rows
         untouched, so a first read that raises leaves `rows == []` with `error`
         set. Checking `error` first is what keeps that case out of "The register
         is empty."

         `rows` before `visible_rows`: with nothing recorded at all there is no
         filter to blame, even when one is set, so the no-matches sentence would
         name a filter that removed nothing.

         Every dependency is read off `self` in this body, per the
         auto-dependency rule `visible_rows` records. Reading `self.visible_rows`
         here makes this var depend transitively on the whole filter state.

         A `str` and not four bools: the precedence then has exactly one home,
         and `tests/test_admin_state.py` can assert it in plain Python instead of
         reading compiled JS.
         """
         if self.error:
             return REGISTER_STATE_FAULT
         if not self.rows:
             return REGISTER_STATE_EMPTY
         if not self.visible_rows:
             return REGISTER_STATE_NO_MATCHES
         return REGISTER_STATE_ROWS
     ```
  4. `empty_matches_message`, after it:
     ```python
     @rx.var
     def empty_matches_message(self) -> str:
         """"verdict denied and text "ana" matched none of the 100 rows loaded."

         PRD-006 Section 6.1: "the no-matches state names the filter that produced
         it and offers to clear it." This is the naming half; the offer is
         `components/register.py:_clear_control`.

         A computed var for the reason `register_filtered` records: three Python
         format strings and a `format_count` thousands separator, none of which
         can run against a Var.

         The verdicts are listed in `VERDICTS` order, not in the order they were
         clicked, so the same selection always produces the same sentence.
         """
         parts = []
         if self.selected_verdicts:
             parts.append(
                 FILTER_DESCRIPTION_VERDICT_TEMPLATE.format(
                     verdicts=FILTER_DESCRIPTION_VERDICT_JOIN.join(
                         _VERDICT_LABELS[v]
                         for v in VERDICTS
                         if v in self.selected_verdicts
                     )
                 )
             )
         if self.search.strip():
             parts.append(
                 FILTER_DESCRIPTION_SEARCH_TEMPLATE.format(
                     search=self.search.strip()
                 )
             )
         return EMPTY_MATCHES_TEMPLATE.format(
             filters=FILTER_DESCRIPTION_JOIN.join(parts),
             loaded=format_count(len(self.rows)),
         )
     ```
- **Mirror**: `chat_ui/chat_ui/admin_state.py:358-425` (`register_scope`,
  `register_filtered`) — same var shape, same dependency discipline, same
  docstring convention.
- **Note**: both are computed vars, so
  `test_sign_out_clears_every_declared_var` (which iterates `base_vars`) stays
  green without modification — the same reason `register_scope` is computed.
- **Validate**: `python -m pytest tests/test_admin_state.py -q`

### Task 3: The shared empty panel and the nothing-recorded state

- **File**: `chat_ui/chat_ui/components/register.py`
- **Action**: UPDATE
- **Implement**: After `_filter_strip()`, add:
  ```python
  # --- The three states (STORY-014) ----------------------------------------
  # The register's docstring used to say "The three empty states (STORY-014) are
  # not here" — update that paragraph in the same edit.

  def _empty_panel(title: str, *body_children) -> rx.Component:
      """One empty state: a line that says what is true, then the way out.

      AC 6, as the list of what is absent: no illustration, no card, no border,
      no background, no accent — the panel paints INK and MUTE on the register's
      own PAPER and nothing else. The type is the surface's existing scale:
      FONT_DISPLAY for the title, exactly as the column heads and verdict tags
      take it, and FONT_BODY for the sentence.

      Left-aligned and set at the table's own left inset rather than centred in
      the container: a centred panel would be a card without a border, and the
      register reads down its left edge.
      """
      return rx.box(
          rx.box(title, font_family=theme.FONT_DISPLAY, font_size=theme.TEXT_LEAD,
                 font_weight="600", letter_spacing="-0.01em", color=theme.INK),
          rx.box(*body_children, font_family=theme.FONT_BODY,
                 font_size=theme.TEXT_BODY, line_height="1.6", color=theme.MUTE,
                 max_width=theme.MEASURE, margin_top="0.5rem"),
          padding="3rem 0 2rem",
          width="100%",
      )


  def _empty_register() -> rx.Component:
      """Nothing has ever been recorded.

      Deliberately not the no-matches wording: PRD-006 Section 4 wants the two
      distinguishable, and this one blames no filter because there is none to
      blame. It ends in Refresh — the skill's "an empty screen is an invitation
      to act" — and the control it points at is the masthead's, so no second
      button is declared here.
      """
      return _empty_panel(
          admin_copy.EMPTY_REGISTER_TITLE, admin_copy.EMPTY_REGISTER_BODY
      )
  ```
- **Mirror**: `chat_ui/chat_ui/components/shell.py:146-190` for the tonal shape
  only — nothing is imported from it (Section 4's separation; enforced by
  `test_source_imports_no_chat_component`).
- **Validate**: `python -m pytest tests/test_register.py -q` (the palette,
  no-literal-hex and no-chat-import tests all run over the new source)

### Task 4: The no-matches state, the table, and the four-armed body

- **File**: `chat_ui/chat_ui/components/register.py`
- **Action**: UPDATE
- **Implement**:
  1. Extend the `admin_state` import with `REGISTER_STATE_EMPTY`,
     `REGISTER_STATE_FAULT`, `REGISTER_STATE_NO_MATCHES`, `REGISTER_STATE_ROWS`.
  2. ```python
     def _no_matches() -> rx.Component:
         """Rows are loaded; this filter matched none of them.

         PRD-006 Section 6.1 asks for two things and this renders both: the
         sentence names the filter (AdminState.empty_matches_message, a Var —
         hence a second child rather than a formatted string), and the way out is
         `_clear_control()` itself, not a second button with the same job. One
         name for one action across the strip and the panel is the skill's
         consistency rule; a second constant would be the drift it warns about.

         `_clear_control` is `rx.cond(filters_active, …)`, which is always true
         in this arm by construction — `register_state` only returns
         no_matches when `visible_rows` is empty and `rows` is not, which
         requires an active filter. The guard is left in place rather than
         bypassed so the control has one definition, not two.
         """
         return _empty_panel(
             admin_copy.EMPTY_MATCHES_TITLE,
             AdminState.empty_matches_message,
             rx.box(_clear_control(), margin_top="0.75rem"),
         )


     def _table() -> rx.Component:
         """The column heads over the rows — STORY-011's table, unchanged and
         now one arm of four.

         It is also the `read_failed` arm: PRD-006's fault copy promises
         "Nothing on screen has changed", so a failed read leaves the previously
         loaded rows standing and STORY-017 hangs its panel above them. An empty
         table under a fault panel is correct; an empty *state* under one is the
         misreading AC 4 forbids.
         """
         return rx.box(
             _column_head(),
             rx.foreach(AdminState.visible_rows, _row),
             min_width=_MIN_WIDTH,
             custom_attrs={"role": "table"},
         )


     def _register_body() -> rx.Component:
         """The three states, chosen by the one var that owns the precedence.

         `rx.match` over `AdminState.register_state` rather than nested
         `rx.cond`s: the ordering AC 4 turns on is then a Python function
         (`admin_state.register_state`) a unit test can call, instead of a nesting
         order that can only be verified by reading compiled JS.

         The default arm is the table, and that is the safe direction: an
         unrecognised state renders the record rather than a claim of emptiness.
         """
         return rx.match(
             AdminState.register_state,
             (REGISTER_STATE_EMPTY, _empty_register()),
             (REGISTER_STATE_NO_MATCHES, _no_matches()),
             (REGISTER_STATE_FAULT, _table()),
             (REGISTER_STATE_ROWS, _table()),
             _table(),
         )
     ```
  3. In `register()`, replace the inner `rx.box(_column_head(), rx.foreach(...), …)`
     with `_register_body()`, leaving the scroll container and `_filter_strip()`
     exactly as they are. Add to `register()`'s docstring that the filter strip
     renders in every state — it carries the scope line and the clear control, and
     removing the controls in the state they are needed to escape would be the
     dead end the skill's "invitation to act" rules out.
- **Mirror**: `chat_ui/chat_ui/components/register.py:_verdict_tag` for the
  `rx.match`-over-a-key form and its default arm.
- **Reflex check (per `chat_ui/AGENTS.md`)**: confirm via the **reflex-docs**
  skill that `rx.match` accepts a `str` computed var as its subject and requires a
  trailing default. If the pinned build disagrees, fall back to nested `rx.cond`
  in the same precedence — `register_state` and every test in Task 5 still hold,
  because the precedence lives in the var either way.
- **Validate**: `python -m pytest tests/test_register.py -q`

### Task 5: Tests — the precedence in pytest, the panels in the probe

- **File**: `tests/test_admin_state.py`, `tests/test_register.py`
- **Action**: UPDATE
- **Implement**:

  In `tests/test_admin_state.py`, a new section after the filter/sort block:
  - `test_the_four_register_states_are_resolved_in_order` — parametrized over the
    four: `(rows=[], error="")` → `no_rows`; `(rows=[r], search="zzz")` →
    `no_matches`; `(rows=[r])` → `rows`.
  - `test_a_failed_read_is_never_reported_as_emptiness` — **AC 4, and the reason
    the var exists**: `error` set with `rows == []` returns `REGISTER_STATE_FAULT`,
    and set with `rows` populated *and* a filter matching nothing still returns
    `REGISTER_STATE_FAULT`. Both empty keys must be unreachable while `error` is set.
  - `test_register_state_is_a_computed_var` — present in
    `AdminState.computed_vars`, absent from `base_vars` (so sign-out keeps its
    guarantee).
  - `test_the_no_matches_sentence_names_the_filter_that_produced_it` — verdict
    only; search only; both, asserting `FILTER_DESCRIPTION_JOIN` between them and
    the loaded count from `format_count(len(rows))`.
  - `test_the_verdict_list_is_ordered_and_labelled` — selecting `denied` then
    `held` produces the `VERDICTS`-order sentence, joined by
    `FILTER_DESCRIPTION_VERDICT_JOIN`, in `admin_copy`'s labels.
  - `test_every_verdict_has_a_label` — `set(_VERDICT_LABELS) == set(VERDICTS)`,
    binding the map to the formatter so a fifth verdict fails loudly.

  In `tests/test_register.py`:
  - `_CHECK_SCRIPT`: import `_empty_panel`, `_empty_register`, `_no_matches`,
    `_register_body`, `_table`; append `("empty_register", …)`,
    `("no_matches", …)`, `("body", …)`, `("table", …)` to `factories` and capture
    each into `result[...]` beside `strip` and `filtered_line`.
  - `COPY_NAMES` += `EMPTY_REGISTER_TITLE`, `EMPTY_REGISTER_BODY`,
    `EMPTY_MATCHES_TITLE` (AC 5's grep — the templates are formatted in
    `admin_state.py` and are covered by the state tests instead).
  - `test_both_empty_states_reach_the_output` — both titles and the
    nothing-recorded body appear in `probe["rendered"]`; the two titles differ
    (AC 1's "distinct in wording").
  - `test_the_no_matches_state_offers_the_clear_action` — `CLEAR_FILTERS_LABEL`
    and `AdminState.clear_filters` are both inside `probe["no_matches"]` (AC 2).
  - `test_the_no_matches_sentence_is_bound_to_the_state` — the panel renders
    `empty_matches_message`, not a literal (mirrors
    `test_the_scope_line_is_bound_to_the_state`).
  - `test_the_fault_arm_renders_the_table_not_an_empty_state` — **AC 4 at the
    render layer**: in `register.py`'s source the `REGISTER_STATE_FAULT` arm is
    `_table()`, and neither `_empty_register` nor `_no_matches` appears on that
    line.
  - `test_the_empty_states_carry_no_card_and_no_illustration` — over
    `probe["empty_register"]` + `probe["no_matches"]`: no `background`, no
    `border`, no `border_radius`, no `<svg`, no `<img` (AC 6). The existing
    `test_no_colour_outside_the_allowed_set` and `test_no_tint_reaches_the_output`
    already cover the accent half over `probe["rendered"]`.
  - `test_the_body_face_is_reserved_for_the_scope_lines` — count **2 → 4**, with
    the docstring extended: "PRD-006 Section 6.1 reserves the reading face for
    'the two or three explanatory lines that state a scope'. There are now four
    uses and never more than three on screen at once — the two scope lines are
    mutually exclusive with the nothing-recorded panel's sentence, and the
    no-matches panel renders with the scope lines above it for a maximum of
    three. Still exact: the face creeping onto a fifth element is how a register
    starts reading as prose."
- **Mirror**: `tests/test_register.py:406-418`
  (`test_the_scope_line_is_bound_to_the_state`) and
  `tests/test_admin_state.py:730-845` (the filter/sort section's fixtures
  `_loaded`, `_call`, `_visible`).
- **Validate**:
  `python -m pytest tests/test_register.py tests/test_admin_state.py -q`

### Task 6: Full suite and the `app/` guarantee

- **File**: — (verification only)
- **Action**: VERIFY
- **Implement**: Run the whole suite, then confirm the diff touches nothing under
  `app/`.
- **Validate**:
  ```bash
  python -m pytest -q
  git diff main --stat -- app/    # must print nothing
  ```

---

## End-to-End Tests

Follow the **reflex-process-management** skill for the run/compile cycle.

- [ ] `python -m pytest -q` — the whole suite green, with PRD-001/003/004 test
      modules unmodified (PRD-006 Section 3).
- [ ] Point the app at an empty database (or a temp copy with `audit_logs`
      truncated), sign in at `/admin/audit` → **"The register is empty."** with its
      body line, no column heads, no card, no illustration (AC 1).
- [ ] Restore the seeded database, sign in → the table renders and **neither**
      empty panel is on screen (AC 3).
- [ ] Type a string matching nothing (e.g. `zzzz`) → **"No rows match this
      filter."** over a sentence naming `text "zzzz"` and the loaded count, with
      **Clear filters** beneath it (AC 2).
- [ ] Select **denied** as well → the sentence names both, joined by " and ", with
      the verdict word in the same case-treatment vocabulary as the chip (AC 2).
- [ ] Use the panel's **Clear filters** → both filters reset and the full window
      returns (AC 2).
- [ ] Select a verdict with no rows in the window (e.g. **fault** on clean traffic)
      → the no-matches state, not the nothing-recorded state (AC 1 vs AC 2).
- [ ] Force the fault path (monkeypatch `list_audit_logs` to raise, or point
      `DATABASE_URL` at an unreadable file) and refresh → `error` is set and the
      table stays on screen; **neither** empty panel appears (AC 4). The panel
      itself arrives with STORY-017.
- [ ] Tab into the no-matches panel → **Clear filters** is reachable and shows the
      `:focus-visible` ring; Enter operates it (quality floor).
- [ ] Narrow to ~40rem → the panel's sentence wraps inside `theme.MEASURE`; nothing
      overflows horizontally.
- [ ] `grep -n '"' chat_ui/chat_ui/components/register.py` → no user-facing string
      literal added; every panel string reads `admin_copy.` or an `AdminState` var
      (AC 5).

---

## Validation

```bash
python -m pytest tests/test_register.py tests/test_admin_state.py tests/test_admin_palette.py tests/test_copy.py tests/test_contrast.py -q
python -m pytest -q
git diff main --stat -- app/
```

---

## Risks & Mitigations

| # | Risk | Mitigation |
|---|------|------------|
| 1 | **AC 4 is unverifiable at the render layer.** `rx.match` compiles every arm into the output, so "the fault case does not render an empty state" cannot be read off the compiled string. | The precedence lives in `AdminState.register_state`, a plain Python function, and `test_a_failed_read_is_never_reported_as_emptiness` calls it directly with `error` set both with and without rows. The render-layer test asserts only the arm binding. |
| 2 | **STORY-017 has not landed**, so the `read_failed` arm has no panel to show. | The arm renders the table, which is what `FAULT_MESSAGE_TEMPLATE`'s "Nothing on screen has changed" already promises. STORY-017 adds its panel above `_register_body()` in `register()` and changes no arm. Recorded in `_table()`'s docstring so the seam is findable. |
| 3 | **`test_the_body_face_is_reserved_for_the_scope_lines` asserts an exact count of 2** and will fail the moment the panels land. | Task 5 moves it to 4 deliberately, with the "never more than three on screen at once" argument written into the docstring rather than the number quietly bumped. It stays an exact count. |
| 4 | **Scope creep into STORY-005's state.** | Two computed vars and two module constants, over vars STORY-005 already owns. No new filter var, no change to `visible_rows`, `filters_active` or any of the four handlers. `filters_active`'s own docstring already assigns "STORY-014's no-matches state" to this story. |
| 5 | **PRD Risk 6 — a fill or an accent creeping in.** An empty state is exactly where a card and an illustration are the template answer. | The panels paint only `theme.INK` and `theme.MUTE`; `test_the_empty_states_carry_no_card_and_no_illustration` plus the existing `test_no_colour_outside_the_allowed_set` and `test_no_tint_reaches_the_output` hold it. |
| 6 | **Two clear buttons**, one in the strip and one in the panel, drifting apart. | `_no_matches` calls `_clear_control()` itself. One definition, one constant, one handler. |
| 7 | **The verdict list could disagree with the chips** if the label map is duplicated. | `_VERDICT_LABELS` is keyed on `admin_formatting`'s own `VERDICT_*` and bound to `VERDICTS` by `test_every_verdict_has_a_label`; the chips read the same `admin_copy` labels. |
| 8 | **A `console.warn`-only dependency-tracking failure** would leave `register_state` stale — the register frozen on one state. | Every dependency (`error`, `rows`, `visible_rows`, `selected_verdicts`, `search`) is loaded off `self` inside each var body, per the rule `visible_rows` records; the E2E filter/clear steps exercise the transitions live. |

---

## Acceptance Criteria

(Copied from story `STORY-014`)

- [ ] Given a database with no audit rows at all, when the register renders, then it shows a "nothing recorded" state that says the record is empty — distinct in wording from the no-matches state.
- [ ] Given rows loaded but a filter that matches none of them, when the register renders, then it names the filter that produced the empty result and offers to clear it, and the clear action restores the full window.
- [ ] Given rows that match, when the register renders, then the table is shown and neither empty state appears.
- [ ] Given a failed read, when the register renders, then the fault panel is shown (STORY-017) rather than either empty state — an error is never presented as emptiness.
- [ ] Given all three states, when their copy is grepped, then every string resolves from `admin_copy`.
- [ ] Given the empty states, when they render, then they use the register's existing type and rules — no illustration, no card, no accent colour.
- [ ] All tasks completed
- [ ] `python -m pytest -q` passes, with `app/` and its test suites unmodified
- [ ] Reflex app compiles and the register renders without error
- [ ] Follows existing patterns
