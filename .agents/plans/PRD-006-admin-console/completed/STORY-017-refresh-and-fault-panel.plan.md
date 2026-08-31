---
story: STORY-017
prd: PRD-006
slug: refresh-and-fault-panel
title: "Manual refresh with a last-refreshed stamp, and a fault panel with retry on both pages"
type: feature
complexity: MEDIUM
epic_branch: epic/PRD-006-admin-console
created: 2026-08-31
---

# Plan: Manual refresh with a last-refreshed stamp, and a fault panel with retry on both pages

## Summary

Every piece of state this story renders already exists. STORY-004 ships
`loading`, `error` and `last_refreshed` on `AdminState`, a `load()` that commits
in one block so a failed read leaves the previous record standing, a `finally`
that clears `loading` on both paths, and an `error = ""` on success that is
documented as clearing "the panel STORY-017 renders". STORY-008 ships every
string — `REFRESH_LABEL`, `REFRESH_IN_FLIGHT_LABEL`, `REFRESHED_TEMPLATE`,
`NEVER_REFRESHED_LABEL`, `FAULT_TITLE`, `FAULT_MESSAGE_TEMPLATE` and the ten read
labels — and `admin_formatting.format_refreshed_at` already stamps the read.
STORY-014 and STORY-015 both left their `read_failed` arm rendering the data
rather than a panel, each with a docstring saying STORY-017 hangs its panel
above. **This story is the surface and the wiring, and nothing else.**

Three new components, all in `admin_shell.py` because both views need them and
the shell is the frame both sit inside: `refresh_control()` — one button, one
name, `disabled=AdminState.loading`, label switching to *Refreshing* with a
pulsing glyph; `refreshed_stamp()` — the *Refreshed 14:22:07* line; and
`fault_panel()` — the title, the sentence `AdminState.error` already carries, and
that same `refresh_control()` as its retry, exactly as `register.py:_no_matches`
reuses `_clear_control()` rather than declaring a second button for one action.
The one state addition is a computed var, `AdminState.refreshed_stamp`, because
`REFRESHED_TEMPLATE.format(...)` is a Python format string and components receive
Vars — the same reason `register_scope` is a computed var and not a formatted
literal.

The panel renders from `admin_page()`, under the masthead and above the content,
so each of the two pages carries its own instance by construction. The stamp
renders where PRD-006 Section 6.1's wireframe puts it: at the foot of the
register's scope column — the slot `register.py:_filter_strip` explicitly left
free for this story — and under the summary's scope note, its counterpart.
Motion is the existing `.hx-pulse` class in `theme.GLOBAL_CSS`, whose
`prefers-reduced-motion: reduce` block is already written; no new CSS, no new
keyframe, no interval anywhere.

## User Story

As a compliance admin
I want a deliberate refresh and a visible fault when a read fails
So that the console never shows me stale data as fresh or a failure as an empty table

## Story Reference

- Story file: `.agents/stories/PRD-006-admin-console/STORY-017-refresh-and-fault-panel.md`
- PRD: `.agents/PRDs/PRD-006-admin-console/PRD.md` — Section 4 (data access & failure handling), Section 6.1 (copy, motion), Section 7, Section 12 Phase 4

## Metadata

| Field | Value |
|-------|-------|
| Type | feature |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/` only — shell, register, summary, admin state, tests |
| Story | STORY-017 |
| PRD | PRD-006 |
| Epic Branch | `epic/PRD-006-admin-console` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| **frontend-design** | "Errors don't apologize, and they are never vague about what happened" — the panel names the read and the state of the screen, and every word of it is already pinned in `admin_copy`. "An action keeps the same name through the whole flow" — **Refresh** → *Refreshing* → **Refreshed 14:22:07**, one verb, and the retry is that same control rather than a second name. "Spend your boldness in one place" — the console's is the stamp margin, so the panel is hairlines and alignment with one fault mark. "Extra animation contributes to the feeling that the design is AI-generated" — one pulsing glyph, only while a read is in flight. | 2, 3, 4, 9 |
| **reflex-docs** (per `chat_ui/AGENTS.md`) | Confirmed against the docs rather than memory: a `disabled` prop takes a state Var directly (`rx.button` loading/disabled props; the repo's own `chat.py:67,80`); a background event handler **cannot be called** from another handler but **is** bound to an event trigger like any other, so `on_click=AdminState.load` is the correct form (Background Events → limitations); `rx.cond(Var != "", …, rx.fragment())` is the house conditional. `prefers-reduced-motion` is expressed through `theme.GLOBAL_CSS`, which already carries `.hx-pulse` and its `animation: none` opt-out (`theme.py:132-140`) — the component adds a `class_name`, not a stylesheet. | 1, 2 |
| **reflex-process-management** (per `chat_ui/AGENTS.md`) | The compile / run / reload cycle in Task 9 and the E2E list follows the skill; no ad-hoc `reflex run` invention. | 9, E2E |

---

## Patterns to Follow

### A control locked for the duration of an in-flight request

```python
# SOURCE: chat_ui/chat_ui/components/chat.py:76-97
rx.el.button(
    copy.COMPOSER_SEND_LABEL,
    type="submit",
    disabled=ChatState.pending,
    ...
    _disabled={"opacity": "0.35", "cursor": "not-allowed"},
)
```

### A pulsing in-flight marker that respects reduced motion

```python
# SOURCE: chat_ui/chat_ui/components/bubbles.py:20-25, 341-346
rx.box(class_name="hx-pulse" if pulse else "", width=theme.GLYPH, ...)
_evidence(copy.PENDING_INDICATOR_TEXT, class_name="hx-pulse")
```

```css
/* SOURCE: chat_ui/chat_ui/theme.py:132-141 */
@keyframes hx-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.25; } }
.hx-pulse { animation: hx-pulse 1.4s ease-in-out infinite; }
@media (prefers-reduced-motion: reduce) {
  .hx-entry, .hx-pulse { animation: none; }
  * { transition-duration: 0.01ms !important; }
}
```

### A conditional message bound to a string var

```python
# SOURCE: chat_ui/chat_ui/components/admin_shell.py:131-141
rx.cond(
    AdminState.gate_error != "",
    rx.box(AdminState.gate_error, font_family=theme.FONT_DATA,
           font_size=theme.TEXT_DATA, color=theme.INK_DENIED, ...),
    rx.fragment(),
)
```

### A rendered string composed once, in Python, as a computed var

```python
# SOURCE: chat_ui/chat_ui/admin_state.py:583-616
@rx.var
def register_scope(self) -> str:
    return REGISTER_SCOPE_TEMPLATE.format(
        shown=format_count(len(self.rows)),
        total=format_count(self.total_recorded),
    )
```

### One action, one control, reused rather than re-declared

```python
# SOURCE: chat_ui/chat_ui/components/register.py:1058-1080
def _no_matches() -> rx.Component:
    return _empty_panel(
        admin_copy.EMPTY_MATCHES_TITLE,
        AdminState.empty_matches_message,
        rx.box(_clear_control(), margin_top="0.75rem"),  # the strip's own control
    )
```

### Tests: a subprocess build probe plus source assertions

```python
# SOURCE: tests/test_admin_shell.py:107-215 (and tests/test_summary.py:113-224)
factories = [("admin_page(register)", lambda: admin_page(rx.box("x"), VIEW_REGISTER)), ...]
proc = subprocess.run([sys.executable, "-c", _CHECK_SCRIPT], cwd=str(REPO_ROOT / "chat_ui"),
                      env={..., "PYTHONPATH": os.pathsep.join(_PYTHONPATH)}, ...)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/admin_state.py` | UPDATE | One computed var, `refreshed_stamp` — *Refreshed {time}*, or *Not read yet* before the first read. |
| `chat_ui/chat_ui/components/admin_shell.py` | UPDATE | `refresh_control()`, `refreshed_stamp()`, `fault_panel()`; the control into `admin_masthead()`; the panel into `admin_page()`. |
| `chat_ui/chat_ui/components/register.py` | UPDATE | The stamp into the foot of the scope column — the slot `_filter_strip` reserved. |
| `chat_ui/chat_ui/components/summary.py` | UPDATE | The stamp under the scope note. |
| `tests/test_admin_state.py` | UPDATE | The stamp var, and that a recovered read advances it and clears the fault. |
| `tests/test_admin_shell.py` | UPDATE | The three components: build, bindings, lock, in-flight label, pulse class, panel on both pages, no auto-refresh. |
| `tests/test_register.py` | UPDATE | The stamp reaches the register. |
| `tests/test_summary.py` | UPDATE | The stamp reaches the summary. |
| `tests/test_contrast.py` | UPDATE | Only if the panel or the control introduces a pairing not already asserted (see Task 8 — the expectation is that it does not). |
| `chat_ui/chat_ui/admin_copy.py` | — | **No change.** Every string exists. If one is missing, it is added here and nowhere else. |
| `chat_ui/chat_ui/theme.py` | — | **No change expected.** The pulse keyframe and its reduced-motion opt-out are already there; the glyph reuses `theme.GLYPH`. Any token that does turn out to be needed is added here only. |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: `AdminState.refreshed_stamp`

- **File**: `chat_ui/chat_ui/admin_state.py`
- **Action**: UPDATE
- **Implement**: A `@rx.var` returning `NEVER_REFRESHED_LABEL` when
  `last_refreshed` is empty and `REFRESHED_TEMPLATE.format(time=self.last_refreshed)`
  otherwise. Import both names from `admin_copy` beside the existing copy
  imports. Docstring records two things: why it is a var and not a component-side
  format (components receive Vars — the reason `register_scope` gives), and why
  it is **computed** rather than declared (`sign_out()` is `reset()`, and
  `test_sign_out_clears_every_declared_var` iterates `base_vars`; a declared stamp
  with a truthy value would survive a sign-out, and a computed one reads the
  cleared `last_refreshed` and returns *Not read yet*). Read `self.last_refreshed`
  inside the body, per the auto-dependency rule `visible_rows` records.
- **Mirror**: `chat_ui/chat_ui/admin_state.py:583-616` (`register_scope`)
- **Validate**: `python -m pytest tests/test_admin_state.py -q`

### Task 2: The three components in the shell

- **File**: `chat_ui/chat_ui/components/admin_shell.py`
- **Action**: UPDATE
- **Implement**: Three module-level, **public** functions (public because
  `register.py` and `summary.py` call the stamp; the shell is their frame, not a
  sibling, so this is not the view-to-view coupling `summary.py:_empty_summary`
  refuses):
  - `refresh_control()` — `rx.el.button` with `type="button"` (an unqualified
    `<button>` defaults to submit, per the sign-out control's note),
    `on_click=AdminState.load`, `disabled=AdminState.loading`,
    `_disabled={"opacity": "0.35", "cursor": "not-allowed"}`, and its child a
    `rx.cond(AdminState.loading, …)` that swaps `REFRESH_LABEL` for
    `REFRESH_IN_FLIGHT_LABEL` beside a `rx.box(class_name="hx-pulse", …)` glyph
    sized `theme.GLYPH`. `FONT_DISPLAY` at `TEXT_DATA`, `MUTE` hovering to `INK`,
    matching the sign-out control it stands beside. Docstring: the background
    handler is bound to the trigger, never called (reflex-docs, background-event
    limitation), and the lock is what PRD-004 Risk 3 / STORY-004's `finally`
    exists to release.
  - `refreshed_stamp()` — `rx.box(AdminState.refreshed_stamp, …)` in `FONT_DATA`
    at `TEXT_DATA` in `MUTE`. The data face, not the reading face: it is a
    timestamp (PRD-006 Section 6.1's type roles), and it also keeps
    `register.py`'s exact `FONT_BODY` count intact (see Risk 4).
  - `fault_panel()` — `rx.cond(AdminState.error != "", panel, rx.fragment())`.
    The panel: a solid `theme.INK_FAULT` mark of `theme.GLYPH` continuing the
    stamp device, `FAULT_TITLE` in `FONT_DISPLAY`/`INK`, `AdminState.error` in
    `FONT_BODY` at `TEXT_DATA` in `MUTE` bounded by `theme.MEASURE`, then
    `refresh_control()` as the retry. Ground is `theme.PAPER` — the page ground,
    no card, no fill, no tint — with a `border_bottom` hairline in `theme.RULE`.
    `custom_attrs={"role": "alert"}`. Docstring: no second button and no second
    constant for one action; the panel sits **above** the data, which stays on
    screen because `FAULT_MESSAGE_TEMPLATE` promises "Nothing on screen has
    changed".

  Then wire: `refresh_control()` into `admin_masthead`'s right cluster, in its
  own `border_left`-ruled box before sign out (the masthead's established
  separator); and `fault_panel()` into `admin_page()`'s authenticated branch,
  between `admin_masthead(active)` and `content`, with `flex_shrink="0"`.
- **Mirror**: `chat_ui/chat_ui/components/chat.py:76-97` (lock), `bubbles.py:20-25`
  (pulse glyph), `admin_shell.py:131-141` (string-var conditional),
  `admin_shell.py:216-307` (masthead cluster and its rules)
- **Validate**: `cd chat_ui && reflex compile --dry` (per **reflex-process-management**)

### Task 3: The stamp at the foot of the register's scope column

- **File**: `chat_ui/chat_ui/components/register.py`
- **Action**: UPDATE
- **Implement**: Import `refreshed_stamp` from `chat_ui.components.admin_shell`
  and add it as the third child of `_filter_strip`'s left `rx.vstack`, under
  `_scope_line()` and `_filtered_line()`. This is the slot that function's
  docstring reserved verbatim ("The wireframe's 'Refreshed 14:22:07' belongs at
  the foot of that column and is STORY-017's; the slot is left free rather than
  filled here") and the position PRD-006 Section 6.1's wireframe draws. Replace
  that reservation sentence with what now fills it. Add no string literal and no
  colour: the stamp carries its own type and ink.
- **Mirror**: `chat_ui/chat_ui/components/register.py:945-989` (`_filter_strip`)
- **Validate**: `python -m pytest tests/test_register.py -q`

### Task 4: The stamp under the summary's scope note

- **File**: `chat_ui/chat_ui/components/summary.py`
- **Action**: UPDATE
- **Implement**: Import the same `refreshed_stamp` and place it directly under
  `_scope_note()` inside `summary()`'s bounded column, above `_sheet_body()` —
  the sheet's counterpart to the register's scope column, and the same reading
  order. Docstring note: the component is the shell's, so the two views state the
  refresh identically without either reaching into the other.
- **Mirror**: `chat_ui/chat_ui/components/summary.py:452-470` (`summary()`)
- **Validate**: `python -m pytest tests/test_summary.py -q`

### Task 5: State tests for the stamp and the recovery

- **File**: `tests/test_admin_state.py`
- **Action**: UPDATE
- **Implement**:
  - `refreshed_stamp` is `NEVER_REFRESHED_LABEL` on a fresh state, and
    `REFRESHED_TEMPLATE.format(time=…)` once `last_refreshed` is set — asserted
    against the constants, never against a retyped literal.
  - After `sign_out()`, the stamp is back to *Not read yet* (the reset guarantee,
    from the render side).
  - AC 4 end to end at the state layer, extending the existing
    `test_a_recovered_read_clears_the_fault`: a first read succeeds and stamps;
    a second read raises and leaves `error` set, `rows` and the figures
    untouched, and the stamp **unchanged** (nothing was refreshed); the retry
    succeeds and `error` is `""` while the stamp has **advanced** — patch the
    clock (as `test_load_stamps_the_time_of_the_read` does) so "advanced" is an
    assertion and not a race.
- **Mirror**: `tests/test_admin_state.py:592-666` (`test_load_stamps_the_time_of_the_read`,
  `test_every_read_position_faults_the_same_way`, `test_a_recovered_read_clears_the_fault`)
- **Validate**: `python -m pytest tests/test_admin_state.py -q`

### Task 6: Shell component tests

- **File**: `tests/test_admin_shell.py`
- **Action**: UPDATE
- **Implement**: Add `refresh_control`, `refreshed_stamp` and `fault_panel` to
  the probe's `factories`, and export each built string. Then assert:
  - **AC 1** — `admin_page(...)` for *both* views carries `REFRESH_LABEL` and
    binds `AdminState.refreshed_stamp`; the compiled control and the compiled
    stamp share the verb (assert `REFRESHED_TEMPLATE` and `REFRESH_LABEL` start
    with the same word, read off the constants, so a reworded control that left
    the line behind fails).
  - **AC 2** — the control's output binds `AdminState.loading` to `disabled`
    *and* carries `REFRESH_IN_FLIGHT_LABEL` and `hx-pulse`.
  - **AC 3/AC 4** — the panel binds `AdminState.error`, carries `FAULT_TITLE`,
    and its retry is `AdminState.load`; the source declares exactly one
    `on_click=AdminState.load` call site (`refresh_control`) — one action, one
    handler.
  - **AC 7** — `admin_page(register)` and `admin_page(summary)` each contain the
    panel's title, so neither page borrows the other's.
  - **AC 6** — `theme.GLOBAL_CSS` names `hx-pulse` inside its
    `prefers-reduced-motion: reduce` block, and the console declares no second
    animation: no `@keyframes`, `animation`, `transition` on a moving property,
    or a second pulse class in any admin module.
  - **AC 8** — no admin module contains `on_mount`, `setInterval`, `rx.moment`,
    `interval`, or an `on_load` reaching `load` (the existing
    `test_no_console_view_loads_on_page_load` covers `on_load`; this is the
    source-side companion, globbed over the admin modules the way
    `tests/test_admin_palette.py` globs them).
  - **AC 5** — every string in the three components resolves from `admin_copy`
    (extend `COPY_NAMES`), no literal, and the panel's copy contains no
    apology — assert the rendered panel matches none of `sorry|apolog|oops|
    unfortunately|whoops` case-insensitively, and that `FAULT_MESSAGE_TEMPLATE`
    names both a read and the action.
  - The existing `test_no_literal_hex_colour` and the chat-separation tests cover
    the new code automatically; leave them untouched.
- **Mirror**: `tests/test_admin_shell.py:107-360`, `tests/test_admin_palette.py:44-56`
  (the glob), `tests/test_summary.py:295-330` (source/render split)
- **Validate**: `python -m pytest tests/test_admin_shell.py -q`

### Task 7: The stamp reaches each surface

- **File**: `tests/test_register.py`, `tests/test_summary.py`
- **Action**: UPDATE
- **Implement**: In each probe, assert the rendered view binds
  `AdminState.refreshed_stamp` — the register at the foot of its scope column
  (assert it renders inside the filter strip's output, which is already built as
  a factory if present; otherwise assert against `register()`), the summary
  beside its scope note. Update `tests/test_register.py`'s
  `test_the_body_face_is_reserved_for_the_scope_lines` **only if** the count
  actually moves; it should not (Task 3 adds no `theme.FONT_BODY` to that file).
- **Mirror**: `tests/test_summary.py:257-268` (`test_every_figure_var_reaches_the_sheet`)
- **Validate**: `python -m pytest tests/test_register.py tests/test_summary.py -q`

### Task 8: Contrast

- **File**: `tests/test_contrast.py`
- **Action**: UPDATE (only if a new pairing appears)
- **Implement**: The panel paints `INK` and `MUTE` on `PAPER` and one solid
  `INK_FAULT` mark — all three already asserted
  (`test_verdict_ink_is_readable_on_the_paper`, and the `body ink on paper` /
  `muted text on paper` rows). The control paints `MUTE` on `CARD` hovering to
  `INK` on `CARD` — also already asserted. So the expected outcome of this task
  is a written confirmation rather than a new assertion. **If** the
  implementation lands the panel on `CARD` or the fault ink on any other ground,
  add that pairing to the parametrised list in the same edit; do not change the
  AA floor.
- **Mirror**: `tests/test_contrast.py:47-105`
- **Validate**: `python -m pytest tests/test_contrast.py -q`

### Task 9: Compile, run, force the fault, and critique

- **File**: — (no file)
- **Action**: —
- **Implement**: Follow **reflex-process-management** for compile/run/reload.
  Work the E2E list below against a seeded database. Then the
  **frontend-design** skill's last pass on the three new components against
  PRD-006 Section 6.1 — "take one last look and remove one accessory": if the
  panel has a mark *and* a title *and* a rule *and* a bounded measure, one of
  them is decoration, and the one that goes is whichever does not encode
  something true. Record what was cut in the story report.
- **Validate**: `python -m pytest -q` and `git diff main --stat -- app/` (empty)

---

## End-to-End Tests

Follow the **reflex-process-management** skill for the run/compile cycle.

- [ ] `cd chat_ui && reflex compile --dry` → compiles with no error or warning.
- [ ] Sign in at `/admin/audit` → **Refresh** stands in the masthead beside
      **Sign out**, and **Refreshed HH:MM:SS UTC** stands at the foot of the
      scope column, under "100 most recent of N" (AC 1).
- [ ] Go to `/admin/stats` → the same control and the same line, the line under
      the scope note (AC 1, AC 7).
- [ ] Click **Refresh** → for the read's duration the control is disabled, reads
      *Refreshing*, and its glyph pulses; afterwards the stamp advances (AC 2).
- [ ] Force a read to raise — monkeypatch `list_audit_logs` (or one of the nine
      counts) in the running process, or point the database at an unreadable
      path — then **Refresh** → the fault panel appears under the masthead
      naming that read, the table's rows and the sheet's figures are **still on
      screen and unchanged** (AC 3).
- [ ] Exercise the fault on `/admin/stats` too → its own panel renders, above
      the standing figures (AC 7).
- [ ] Restore the read and use the panel's **Refresh** → the panel clears, the
      data updates, the stamp advances (AC 4).
- [ ] Read the panel's copy aloud → it names the read, states that nothing moved,
      and gives the action; no "sorry", no "something went wrong" (AC 5).
- [ ] Set `prefers-reduced-motion: reduce` (DevTools → Rendering → Emulate CSS
      media) and refresh → the label still changes to *Refreshing* and the
      control still locks, and the glyph does not animate (AC 6).
- [ ] Leave both pages open for several minutes without touching anything → the
      stamp never advances, and the network panel shows no periodic event
      (AC 8).
- [ ] Tab to **Refresh** → the `:focus-visible` ring shows and Enter operates it;
      while locked it is skipped, and tab order reaches the panel's retry
      (quality floor).
- [ ] Narrow to ~40rem → the masthead's cluster wraps as it already does, the
      panel's sentence wraps inside `theme.MEASURE`, nothing overflows
      horizontally.
- [ ] `grep -n '"' chat_ui/chat_ui/components/admin_shell.py` → no new
      user-facing string literal; every word reads from `admin_copy` (AC 5).

---

## Validation

```bash
python -m pytest tests/test_admin_shell.py tests/test_admin_state.py tests/test_register.py tests/test_summary.py tests/test_contrast.py tests/test_admin_palette.py tests/test_admin_copy.py -q
python -m pytest -q
git diff main --stat -- app/
cd chat_ui && reflex compile --dry
```

---

## Risks & Mitigations

| # | Risk | Mitigation |
|---|------|------------|
| 1 | **`loading` stranded True locks the console permanently** — PRD-004 Risk 3. | Not this story's to fix and already fixed: STORY-004's `load()` clears `loading` in a `finally` on both paths, and `test_loading_is_true_for_the_duration_and_false_after` holds it. The E2E fault step exercises it live — the control must come back after a failed read, not only after a good one. |
| 2 | **Two Refresh buttons on screen during a fault** (masthead and panel). | Deliberate, and the precedent is `register.py:_no_matches`, which renders the strip's own `_clear_control()` inside the panel. One definition, one constant, one handler — the duplication is of a rendered instance, not of a decision. Task 6 asserts a single `on_click=AdminState.load` site. |
| 3 | **The panel placement contradicts STORY-014's note**, which said STORY-017 would add the panel "above `_register_body()` in `register()`". | Deliberate deviation, recorded here and to be repeated in the story report: the panel belongs to both views identically, so putting it in `admin_page()` gives each page its own instance (AC 7) with one call site, keeps `register.py`/`summary.py` free of a duplicated panel, and puts the fault above the filter strip where it is seen before the controls are used. No arm of either `rx.match` changes, which is what that note was actually protecting. |
| 4 | **`tests/test_register.py::test_the_body_face_is_reserved_for_the_scope_lines` asserts `source.count("theme.FONT_BODY") == 3`** and a stamp in the reading face would break it. | The stamp is a timestamp and therefore `FONT_DATA` (PRD-006 Section 6.1's type roles), and it is defined in `admin_shell.py`, so `register.py`'s count does not move. If the count does move, the number is changed with the argument written into the docstring — never bumped quietly. |
| 5 | **A new animation or a second moving element** creeping in — the skill's "extra animation contributes to the feeling that the design is AI-generated", and PRD-006 Section 6.1's "the sole moving element". | The glyph reuses the existing `.hx-pulse` class; no new keyframe, no `transition` on a moving property. Task 6 asserts no admin module declares `@keyframes` or a second pulse class, and that `hx-pulse` is inside the reduced-motion block. |
| 6 | **An auto-refresh added later** — explicitly out of scope (PRD-006 Section 4). | Task 6's source guard over the admin modules for `on_mount` / `setInterval` / `interval` / `rx.moment`, alongside the existing `test_no_console_view_loads_on_page_load`. |
| 7 | **The retry re-entering while a read is in flight.** | Two guards already: the control is `disabled` while `loading`, and `load()` itself returns early if `loading` — `test_a_second_concurrent_load_is_refused_by_the_loading_guard`. The disabled prop is the affordance; the state guard is the correctness. |
| 8 | **A fault panel over an empty screen reading as "nothing recorded"** on a *first* read that raises. | Already handled in state: `register_state` and `summary_state` both test `error` first, and both fault arms render the table/sheet rather than an empty panel. This story adds the panel that names the fault above them, which is the half those two vars were written to expect. |
| 9 | **`register.py` importing from `admin_shell.py` introducing a cycle.** | `admin_shell` imports only `admin_copy`, `theme` and `AdminState`; `chat_ui.py` composes the two. No cycle, and the build probes in `tests/test_register.py`, `tests/test_summary.py` and `tests/test_admin_shell.py` each import in a fresh subprocess, so a cycle would fail loudly rather than subtly. |
| 10 | **`INK_FAULT` on a non-verdict element** stretching PRD-006 Section 6.1's "one ink per verdict". | The precedent is in the same file: the gate's error line paints `INK_DENIED` for a refusal that is not a row's verdict. A failed read *is* the fault condition in the console's own vocabulary, and the mark reuses the stamp shape rather than introducing a new device. If the Task 9 critique disagrees, the mark is what gets cut — not the panel. |

---

## Acceptance Criteria

(Copied from story `STORY-017`)

- [ ] Given either admin page, when it renders authenticated, then it carries a **Refresh** control and a last-refreshed stamp reading **Refreshed {time}** — the same verb across the control and the line.
- [ ] Given a refresh in flight, when the page is observed, then the refresh control is locked for its duration and a loading indicator is shown.
- [ ] Given a read that raises, when the page renders, then a fault panel names the read that failed and offers a retry, and the previously loaded rows and figures are left untouched rather than cleared.
- [ ] Given the fault panel's retry, when it is used and the read succeeds, then the panel clears, the data updates and the refreshed stamp advances.
- [ ] Given the fault panel, when its copy is read, then it names what happened without apologizing and without vagueness.
- [ ] Given the loading indicator, when `prefers-reduced-motion: reduce` is set, then it does not animate — it is the console's sole moving element.
- [ ] Given both pages, when the fault path is exercised on each, then each renders the panel independently.
- [ ] Given the console, when it is left open, then it never auto-refreshes, polls, or pushes — refresh is only ever a deliberate action.
- [ ] All tasks completed
- [ ] `python -m pytest -q` passes, with `app/` and its test suites unmodified
- [ ] Reflex app compiles and both console views render without error
- [ ] Follows existing patterns
