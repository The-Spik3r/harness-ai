---
story: STORY-011
prd: PRD-006
slug: register-table-stamp-margin
title: "register.py: the audit table, the verdict column and the stamp margin"
type: NEW_CAPABILITY
complexity: HIGH
epic_branch: epic/PRD-006-admin-console
created: 2026-08-31
---

# Plan: `register.py` — the table, the verdict column, and the stripe of exceptions

## Summary

Create `chat_ui/chat_ui/components/register.py` and fill the `content` slot STORY-010 left empty at `/admin/audit`. The module renders `AdminState.visible_rows` as one CSS-grid table — a scope line, a sticky column head, and one row per `AuditRow` — with the **stamp margin** as the grid's first column: a fixed `theme.STAMP_X` strip carrying each non-cleared row's verdict as a solid `theme.GLYPH` square in its own ink, blank for cleared rows, so a hundred rows resolve into a vertical stripe of exceptions. Verdict dispatch is `rx.match` over `AuditRow.verdict`, the same shape `components/chat.py:22-31` uses over `ChatMessage.kind`; it appears twice (once for the stamp, once for the tag) because the two are different marks of one fact, and both carry the default arm `AuditRow.verdict = ""` requires. Three small edits ride along: `admin_formatting.py` gains `format_count()` (thousands separators, so 3180 reads as *3,180*), `admin_state.py` gains a `register_scope` computed var that assembles `REGISTER_SCOPE_TEMPLATE` from it, and `chat_ui.py` swaps `rx.fragment()` for `register()`. Out of scope and deliberately absent: row disclosure (STORY-012), the filter and sort controls (STORY-013), the three empty states (STORY-014), refresh and the fault panel (STORY-017).

## User Story

As a compliance admin
I want blocked traffic to stand out from cleared traffic at a glance
So that I can scan a hundred rows without reading a hundred rows.

## Story Reference

- Story file: `.agents/stories/PRD-006-admin-console/STORY-011-register-table-stamp-margin.md`
- PRD: `.agents/PRDs/PRD-006-admin-console/PRD.md` — Section 4 (register columns, three states), Section 5 (stories 1, 2, 5, 7), Section 6 (components read fields), Section 6.1 (colour, type, layout, signature, row identifiers), Section 12 Phase 2, Risks 2, 4 and 6

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | HIGH |
| Systems Affected | `chat_ui/chat_ui/components/register.py` (CREATE), `chat_ui/chat_ui/admin_formatting.py` (UPDATE — one function), `chat_ui/chat_ui/admin_state.py` (UPDATE — one computed var + two imports), `chat_ui/chat_ui/chat_ui.py` (UPDATE — two lines), `tests/test_register.py` (CREATE), `tests/test_admin_formatting.py` (UPDATE, append-only), `tests/test_admin_state.py` (UPDATE, append-only). No `app/` change, no `theme.py` change, no `admin_copy.py` change, no new dependency. |
| Story | STORY-011 |
| PRD | PRD-006 |
| Epic Branch | `epic/PRD-006-admin-console` (commit directly on this branch) |

**Dependency check.** `depends_on: [STORY-001, STORY-002, STORY-004, STORY-007, STORY-008, STORY-009, STORY-010]` — all seven `status: done` (`577a285`, `0fe6c69`, `e8c331e`, `a650a97`, `cc857e7`, `5a35ce3`, `b030618`). Everything this story consumes was read before planning: `AuditRow`'s sixteen fields (`admin_models.py:27-53`), the four verdict keys and `VALUE_ABSENT` (`admin_formatting.py:42-50`), `AdminState.visible_rows` / `rows` / `total_recorded` (`admin_state.py:262-320`), the four register tokens `HOVER` / `ROW_H` / `STAMP_X` / `TEXT_MICRO` (`theme.py:28,85,83,75`), the ten register constants in `admin_copy.py:86-126`, and `admin_page()`'s `content` slot (`components/admin_shell.py:309`). `blocks: [STORY-012, STORY-013, STORY-014, STORY-018]`, all `todo`, so the names exported below are free. Working tree clean on `epic/PRD-006-admin-console` at `e030ce3`. Baseline captured before planning: `python -m pytest tests/ -q` → **432 passed in 13.98s**. Cleared to proceed.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `.agents/skills/frontend-design` | Read in full (`.agents/skills/frontend-design/SKILL.md`). Four rules bind. **(1)** *"Structural devices, numbering, eyebrows, dividers, labels, should encode something true about the content, not decorate it"* — the story quotes this at the stamp margin, and PRD Section 6.1 answers the skill's own numbered-marker caution: `#3180` *"is the row's real `audit_id`, monotonic, and the exact string a user quotes out of the chat's success footer… It is a key, not a decoration."* So the id column renders `AUDIT_ID_PREFIX` + the real `audit_id`, never a row ordinal. **(2)** *"Spend your boldness in one place"* — the stamp margin is that place; every other column is hairlines, alignment and type weight. No zebra striping, no fill, no icon, no badge pill. **(3)** *"Match complexity to the vision… minimal directions need precision in spacing, type, and detail"* — this is why the head and the rows share one `_GRID` constant rather than two matching strings (Task 3). **(4)** *"Let each element do exactly one job"* — the stamp states the verdict as position-and-colour, the tag states it as a word; the PII cell states presence or absence and nothing else. | Tasks 3–6 |
| `reflex-docs` (**NOT INSTALLED** — substituted, see below) | `chat_ui/AGENTS.md` mandates it for any Reflex API. The story names the two that decide this module: `rx.foreach` over `list[AuditRow]` and `rx.match` over a string field. | Tasks 2, 3, 4, 5 |
| `reflex-process-management` (**NOT INSTALLED** — substituted) | Mandated for any compile/run/reload cycle. This story is the first that puts data on a compiled admin page, so the E2E section below does run `reflex run` against a seeded database. | E2E |

### Skill availability and the substitution

`reflex-docs` and `reflex-process-management` ship in the `reflex-dev/agent-skills` Claude Code *plugin*, which is not installed in this environment — `~/.claude/plugins` is absent and `.agents/skills/` holds only `frontend-design`. This is the same gap STORY-001 … STORY-010 each recorded; it is a tooling gap, not a decision to work from memory. `chat_ui/AGENTS.md`'s rule is *"rather than relying on memory"*, so both APIs below were verified by **building them against the pinned package** (`reflex==0.9.6.post1`, confirmed via `importlib.metadata`) with the project's real `AdminState` and `AuditRow`, not recalled:

1. **`rx.foreach(AdminState.visible_rows, callback)` yields a Var whose `AuditRow` fields are addressable, including the non-`str` ones.** Probed: a callback reading `row.verdict` (str), `row.timestamp_relative` (str), `row.audit_id` (**int**) and `row.pii_indicator` (**bool**) compiled to a component of 1103 characters with no error. The callback does **not** need a type annotation for this to work — `visible_rows` is annotated `list[AuditRow]` on the computed var, and that is where Reflex gets the element type. This is the same mechanism `components/chat.py:39` uses over `ChatState.messages` (`list[ChatMessage]`, also a `pydantic.BaseModel`), so `AuditRow` needs no `rx.Base` conversion.
2. **`rx.match(row.verdict, (KEY, component), …, default)` compiles to a JS `switch`.** Probed in the same build: the four verdict constants as arms plus a bare default arm produced `switch` in the compiled output. The keys may be module constants (`admin_formatting.VERDICT_DENIED`), not just literals — they are resolved in Python before the Var is built. **The default arm is not optional here**: `AuditRow.verdict` defaults to `""` (`admin_models.py:40`, whose comment says so outright — *"The register's `rx.match` therefore needs a default arm"*), and `rx.match` raises at build time without one.
3. **A `str` Var and a Python `str` cannot be joined with `+` for the id column without `.to_string()` on the int.** Avoided rather than solved: `rx.box(admin_copy.AUDIT_ID_PREFIX, row.audit_id)` passes both as children and Reflex renders them adjacent. No Var arithmetic, so nothing to get wrong.
4. **`str.format` cannot build the scope line.** `REGISTER_SCOPE_TEMPLATE` needs a thousands separator (`3,180`), and `f"{n:,}"` is Python-side formatting that cannot run against a Var. This is why Task 2 puts `format_count()` in `admin_formatting.py` and Task 3 puts `register_scope` on the state — which is also what PRD Section 6 requires independently: *"Components read fields; they do not compute."*
5. **A computed var does not break the sign-out guarantee.** Verified against the real class: `AdminState.base_vars` returns the twenty declared fields and `AdminState.computed_vars` returns `['filters_active', 'visible_rows']` — the two sets are disjoint. `tests/test_admin_state.py::test_sign_out_clears_every_declared_var` iterates `base_vars`, so adding `register_scope` as an `@rx.var` cannot fail it. (It would have: `register_scope` on a cleared state returns the truthy string `"0 most recent of 0"`.)

---

## Patterns to Follow

### The verdict dispatch — one `rx.match`, one arm per outcome, and a default

```python
# SOURCE: chat_ui/chat_ui/components/chat.py:19-31
def message_bubble(message) -> rx.Component:
    """One rx.match over `kind`, one arm per pipeline outcome. A seventh
    outcome later is one new arm, not another level of nesting."""
    return rx.match(
        message.kind,
        ("user", render_user(message)),
        ("assistant", render_assistant(message)),
        ...
        render_fallback(message),
    )
```

Follow the shape exactly, with one change: the arm keys are `admin_formatting.VERDICT_*` constants rather than string literals, because that module's docstring already declares them the dispatch keys (`admin_formatting.py:28-46`) and a literal here would be the fifth place the word *denied* is typed.

### The rail glyph the stamp margin continues

```python
# SOURCE: chat_ui/chat_ui/components/bubbles.py:20-46
def _glyph(ink: str, filled: bool = True, pulse: bool = False) -> rx.Component:
    """The rail marker. A stamped square is a verdict the harness reached..."""
    return rx.box(
        width=theme.GLYPH, height=theme.GLYPH,
        flex_shrink="0", border_radius="1px",
        background_color=ink,
    )
```

`theme.STAMP_X is theme.RAIL_X` (asserted by identity in `tests/test_admin_palette.py:77-81`), and the mark is the same `theme.GLYPH` square in the same ink. The register does **not** import `bubbles` to get it — that is the cross-surface import PRD Section 4 forbids and `tests/test_register.py` will assert against; the shape is re-declared, exactly as `admin_copy.py` re-declares the wordmark.

### The evidence face, and a component that takes styling props

```python
# SOURCE: chat_ui/chat_ui/components/bubbles.py:74-84
def _evidence(*children, color: str = theme.MUTE, **props) -> rx.Component:
    """A line of machine fact — an id, a count, a matched pattern. Always set in
    the data face so it never reads as prose."""
    return rx.box(
        *children,
        font_family=theme.FONT_DATA, font_size=theme.TEXT_DATA,
        color=color, overflow_wrap="anywhere", **props,
    )
```

`_cell()` in Task 4 is this helper's register-side counterpart: same `**props` passthrough so one cell can right-align without a second function.

### The scrolling column inside a `100vh` shell

```python
# SOURCE: chat_ui/chat_ui/components/chat.py:34-52
def message_list() -> rx.Component:
    return rx.auto_scroll(
        rx.box(..., width="100%", max_width=theme.COLUMN_MAX, margin="0 auto"),
        class_name="hx-scroll",
        display="flex", flex_direction="column",
        flex="1", width="100%",
    )
```

The register takes `class_name="hx-scroll"` and `flex="1"` from this, and **not** `rx.auto_scroll` — that component pins the view to the newest entry, which is right for a live transcript and wrong for a register an admin is scanning. It adds `min_height="0"`, without which a flex child refuses to shrink below its content and the page scrolls instead of the table (AC 7).

### The test file: a subprocess build probe plus source assertions

```python
# SOURCE: tests/test_admin_shell.py:189-213
@pytest.fixture(scope="module")
def probe():
    proc = subprocess.run(
        [sys.executable, "-c", _CHECK_SCRIPT],
        cwd=str(REPO_ROOT / "chat_ui"),
        env={**os.environ, "PYTHONPATH": os.pathsep.join(_PYTHONPATH),
             "ADMIN_TOKEN": os.environ.get("ADMIN_TOKEN", "test-token"),
             "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", "test-key")},
        capture_output=True, text=True,
    )
    ...
```

`tests/test_register.py` copies this fixture verbatim (including both env defaults — `register.py` imports `admin_state`, which imports `app.config.settings`, where `ADMIN_TOKEN` is required). The subprocess is not optional: importing `chat_ui.components.register` in-process puts the inner package on `sys.path` and breaks every other test module, which is why `tests/test_chat_components_import.py` and `tests/test_admin_shell.py` both take one.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/admin_formatting.py` | UPDATE | `format_count()` — the thousands separator the scope line's *3,180* needs, in the module that owns rendered strings |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | `register_scope` computed var — the scope line assembled in Python, because components read fields |
| `chat_ui/chat_ui/components/register.py` | CREATE | The scope line, the sticky column head, the grid rows, the verdict tag, the stamp margin |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | `admin_register_page` renders `register()` instead of `rx.fragment()` |
| `tests/test_admin_formatting.py` | UPDATE | `format_count` cases, append-only |
| `tests/test_admin_state.py` | UPDATE | `register_scope` cases, append-only |
| `tests/test_register.py` | CREATE | Build probe, palette/type/copy source assertions, and the preview-boundary pair |

**Not changed, each a checked absence rather than an omission:**

- `chat_ui/chat_ui/theme.py` — STORY-007 added the four tokens this story spends (`HOVER`, `ROW_H`, `STAMP_X`, `TEXT_MICRO`) and every other value it needs already exists. A new token here would be a design decision PRD Section 6.1 did not leave open.
- `chat_ui/chat_ui/admin_copy.py` — STORY-008 wrote all ten register constants. If a string is needed that is not there, that is a signal the scope has drifted into STORY-012/013/014, not a signal to add a constant.
- `tests/test_contrast.py` — every pairing this story draws is already asserted: the four verdict inks on `PAPER` and on `HOVER` (`_INK_ON_HOVER`, lines 72-81), and `INK`/`MUTE` on `PAPER`, on `CARD` and on `HOVER` (`test_neutral_pairs_are_readable`, lines 84-105). The register introduces **no new ink/ground pairing**. Verified by reading the file, not assumed.
- `tests/test_admin_palette.py` — already globs `chat_ui/chat_ui/components/register.py` (line 46), so its no-tint and no-chat-ink guards start applying to this file the moment it exists. **Consequence for Task 4: the strings `INK_UPSTREAM`, `INK_SELF` and `TINT_` must not appear in `register.py` at all — not in code, and not in a docstring or comment.** The test is a plain substring search of the file text, and `admin_shell.py`'s docstring already navigates this constraint deliberately (`components/admin_shell.py:28-33`).

---

## Design decisions worth stating before the tasks

Three choices below are not forced by the story and are made here so `/implement` does not re-open them.

**A CSS grid, not `rx.table` and not `<table>`.** Two reasons, and the second is the deciding one. (1) The whole codebase renders in `rx.box`/`rx.hstack`/`rx.vstack`; there is no `rx.table` anywhere, and Radix's table brings its own surface fill and border tokens — the same fight `theme.py:158-199` already records having with `TextFieldRoot` and the select trigger, and a fill is what PRD Section 6.1 forbids outright. (2) STORY-012 hangs a per-row disclosure region under each row; in a `<table>` that is a second `<tr>` with a `colspan` that has to be kept in sync with the column count by hand, and in a grid it is one more grid child spanning `1 / -1`. The grid is chosen with STORY-012 in view. ARIA roles (`role="table"`, `"row"`, `"columnheader"`, `"cell"`) are set with `custom_attrs` so the semantics a `<table>` would have given are not lost — the same mechanism `admin_shell.py:202` uses for `aria-current`.

**One `_GRID` constant, shared by the head and every row.** AC 5 requires that the numeric columns *"align down the full window"*. Two matching template strings satisfy that until someone edits one of them; one constant makes it true by construction. This is the frontend-design skill's *"minimal directions need precision"* applied literally.

**The column head is sticky inside the scroll container, not fixed above it.** If the head sits outside the scrolling box, the 10px scrollbar `theme.GLOBAL_CSS:116-123` draws on `.hx-scroll` shifts the body columns relative to the head — the exact misalignment AC 5 rules out. Putting the head inside the same container as the first grid child with `position="sticky"; top="0"` keeps the two on one scrollbar *and* keeps the heads readable through a hundred rows, which is what the register is for. No new CSS: `position` is an inline prop.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: `format_count()` — the scope line's thousands separator

- **File**: `chat_ui/chat_ui/admin_formatting.py`
- **Action**: UPDATE (append one function, after `format_share`)
- **Implement**: `format_count(value: Optional[int]) -> str` returning `f"{value:,}"`, and `VALUE_ABSENT` when `value is None`. Docstring states why it lives here rather than in a component: PRD Section 6.1's scope line reads *"100 most recent of 3,180"*, the separator is Python-side formatting, and components receive Vars — the same rule the module docstring already states at lines 1-9. Note that STORY-015's summary figures are the second caller, which is why it is a general `format_count` and not a `format_scope`.
- **Mirror**: `chat_ui/chat_ui/admin_formatting.py:93-103` (`format_share`) — same signature shape, same `Optional` guard returning a placeholder rather than raising, same "no figure may raise into a page render" reasoning.
- **Validate**: `python -m pytest tests/test_admin_formatting.py -q` (still green — this task adds no test yet)

### Task 2: `register_scope` — the window stated against the true total

- **File**: `chat_ui/chat_ui/admin_state.py`
- **Action**: UPDATE
- **Implement**: import `REGISTER_SCOPE_TEMPLATE` in the existing `from .admin_copy import (...)` block and `format_count` in the existing `from .admin_formatting import ...` line. Add, directly after `filters_active` (line 332), an `@rx.var def register_scope(self) -> str` returning
  `REGISTER_SCOPE_TEMPLATE.format(shown=format_count(len(self.rows)), total=format_count(self.total_recorded))`.
  Two points the docstring must carry:
  - **`len(self.rows)`, not `REGISTER_ROW_LIMIT` and not `len(self.visible_rows)`.** Against a table of 12 rows, a hard-coded 100 would render *"100 most recent of 12"*, which is false; `len(self.rows)` is `min(REGISTER_ROW_LIMIT, total)` by construction, so it states the cap whenever the cap binds and states the truth when it does not. It is not `visible_rows` because STORY-013's filtered count is a different statement with its own constant — `admin_copy.py:124-126` says so, and the two lines must not collapse into one.
  - **Both dependencies are read off `self` in this body.** Same requirement `visible_rows`' docstring records at `admin_state.py:305-314`: Reflex's auto-dependency tracker disassembles the function and records the attributes loaded from `self`, and its failure mode is a `console.warn` plus an empty dependency set, not an exception. `format_count` is handed a plain `int`, never `self`.
- **Mirror**: `chat_ui/chat_ui/admin_state.py:322-332` (`filters_active`) — a small `@rx.var` reading declared fields directly.
- **Validate**: `ADMIN_TOKEN=test-token OPENROUTER_API_KEY=test-key python -c "import sys; sys.path.insert(0,'.'); from chat_ui.chat_ui.admin_state import AdminState; print(sorted(AdminState.computed_vars)); print(sorted(AdminState.base_vars))"` → `computed_vars` gains `register_scope`, `base_vars` is unchanged at twenty names.

### Task 3: `register.py` — the module, its constants and the grid

- **File**: `chat_ui/chat_ui/components/register.py`
- **Action**: CREATE
- **Implement**: module docstring plus the layout constants. Imports are exactly `reflex as rx`, `from chat_ui import admin_copy, theme`, `from chat_ui.admin_formatting import VALUE_ABSENT, VERDICT_CLEARED, VERDICT_DENIED, VERDICT_FAULT, VERDICT_HELD`, and `from chat_ui.admin_state import AdminState` — no `copy`, no `state`, no `components.chat`, no `components.bubbles`. Docstring states: the stamp margin is the signature and the one place boldness is spent; the module reads `AuditRow` fields and computes nothing (PRD Section 6); and the file may name no colour outside the four verdict inks and the ground tokens. **It must not name the two chat-only inks or the tint prefix even to say they are excluded** — `tests/test_admin_palette.py` greps this file for those strings.
  Constants:
  ```python
  # One template, shared by the head and every row: two matching strings would
  # satisfy AC 5 until someone edited one of them.
  _GRID = f"{theme.STAMP_X} 8.5rem 8rem 5.5rem 9rem 5rem 3.5rem minmax(9rem, 1fr) 5.5rem"
  # Below this the nine columns crush rather than wrap; the table scrolls
  # sideways in its own container instead of the page doing it.
  _MIN_WIDTH = "58rem"
  ```
  Column order is PRD Section 4's, verbatim: stamp margin, Time, User, Verdict, Model, Tokens, PII, Device, ID.
- **Mirror**: `chat_ui/chat_ui/components/admin_shell.py:1-64` — module docstring stating the structural invariants, then value constants with the reason they are values and not copy.
- **Validate**: `ADMIN_TOKEN=test-token OPENROUTER_API_KEY=test-key PYTHONPATH=chat_ui python -c "import chat_ui.components.register"` from the repo root (module imports clean)

### Task 4: the cell vocabulary — head, cell, stamp, verdict tag

- **File**: `chat_ui/chat_ui/components/register.py`
- **Action**: UPDATE
- **Implement**: five private helpers.
  - `_head_cell(label: str, align: str = "left")` — `FONT_DISPLAY`, `TEXT_MICRO`, `MUTE`, `font_weight="600"`, `letter_spacing="0.1em"`, `text_transform="uppercase"`, `text_align=align`, `custom_attrs={"role": "columnheader"}`. `TEXT_MICRO`'s own comment calls it *"register column heads — a signpost, never row data"* (`theme.py:75`); it appears on the heads and on the absolute timestamp beneath the relative one, and nowhere else.
  - `_cell(*children, color=theme.INK, **props)` — `FONT_DATA`, `TEXT_DATA`, `custom_attrs={"role": "cell"}`, plus `overflow="hidden"`, `text_overflow="ellipsis"`, `white_space="nowrap"` so a long `model_used` truncates rather than breaking the row height. `**props` passthrough carries `text_align="right"` on the two numeric columns.
  - `_stamp(ink: str)` — a `theme.GLYPH` square, `border_radius="1px"`, `background_color=ink`.
  - `_stamp_margin(row)` — `rx.match(row.verdict, (VERDICT_HELD, _stamp(theme.INK_HELD)), (VERDICT_DENIED, _stamp(theme.INK_DENIED)), (VERDICT_FAULT, _stamp(theme.INK_FAULT)), (VERDICT_CLEARED, rx.fragment()), rx.fragment())` inside a `rx.box` of `width=theme.STAMP_X` that centres its child and carries `border_right=f"1px solid {theme.RULE}"` — the `├─┬──` edge in PRD Section 6.1's wireframe, and the margin's only rule. Cleared and the `""` default are both blank, which is what makes the column a stripe of exceptions rather than a column of marks.
  - `_verdict_tag(row)` — `rx.match` over the same field: `VERDICT_CLEARED` → `admin_copy.VERDICT_CLEARED_LABEL` in `INK_CLEAR`, `FONT_DISPLAY`, `TEXT_TAG`, weight 500, lowercase; `VERDICT_HELD` / `VERDICT_DENIED` / `VERDICT_FAULT` → their labels in `INK_HELD` / `INK_DENIED` / `INK_FAULT`, weight 600, `text_transform="uppercase"`, `letter_spacing="0.08em"`; default → `VALUE_ABSENT` in `MUTE`. The case split is the treatment PRD Section 6.1's wireframe shows (exceptions in caps) applied here rather than baked into the constants — `admin_copy.py:105-113` says exactly that, and says why: *"the same word cannot arrive in two cases from two constants and leave the filter chip disagreeing with the row."* AC 3 is satisfied by the four distinct inks; the case is the second, redundant channel that makes it survive a greyscale print.
- **Mirror**: `chat_ui/chat_ui/components/bubbles.py:20-32` (`_glyph`), `:49-58` (`_tag`), `:74-84` (`_evidence`) — re-declared, never imported.
- **Validate**: `python -m pytest tests/test_admin_palette.py -q` (the no-tint and no-chat-ink guards now cover the new file)

### Task 5: the row, the head row, and the scope line

- **File**: `chat_ui/chat_ui/components/register.py`
- **Action**: UPDATE
- **Implement**: three functions.
  - `_row(row)` — one `rx.box` with `display="grid"`, `grid_template_columns=_GRID`, `align_items="center"`, `min_height=theme.ROW_H`, `column_gap="0.75rem"`, `padding_right="1.5rem"`, `border_bottom=f"1px solid {theme.RULE_SOFT}"`, `_hover={"background_color": theme.HOVER}`, `custom_attrs={"role": "row"}`. `min_height`, not `height`: the time cell is two lines and a fixed `ROW_H` would clip the second. Children in PRD Section 4's order:
    1. `_stamp_margin(row)`
    2. time — a stacked `rx.box`: `row.timestamp_relative` in `_cell` style, then `row.timestamp_absolute` at `TEXT_MICRO` in `MUTE`. Both are shown because AC 1 names *"timestamp (relative + absolute)"*; the relative reads at a glance and the absolute is the evidence under it. `_format_timestamps` already writes `VALUE_ABSENT` into both when the column is NULL (`admin_formatting.py:133-147`), so neither can render blank.
    3. `row.user_id`
    4. `_verdict_tag(row)`
    5. `row.model_used`
    6. `row.tokens_used`, `text_align="right"`
    7. `rx.cond(row.pii_indicator, <PII_INDICATOR_LABEL in INK>, <VALUE_ABSENT in MUTE>)` — a render-time branch on a bool Var, which is the supported mechanism; the *derivation* already happened in `to_audit_row` (`admin_formatting.py:185`).
    8. `row.device_short` — already truncated to 32 characters in Python (`admin_formatting.py:124-130`); the full string is STORY-012's.
    9. `rx.box(admin_copy.AUDIT_ID_PREFIX, row.audit_id)`, `text_align="right"` — two children, no Var concatenation.
    **Nine children and no tenth.** `row.device_full`, `row.prompt_hash`, `row.error_message`, `row.pii_entities`, `row.pii_detected_input`, `row.pii_detected_output` and `row.suspicious_pattern` are disclosure-only (`admin_models.py:45-53`) and belong to STORY-012.
  - `_column_head()` — the same grid, `_head_cell` for each of the eight named columns (the stamp margin's head is an empty `rx.box`: a head over a column with no values would be a label that labels nothing, which is the skill's *"let each element do exactly one job"* read backwards). `position="sticky"`, `top="0"`, `z_index="1"`, `background_color=theme.PAPER`, `border_bottom=f"1px solid {theme.RULE}"` — a full rule under the head against the hairline `RULE_SOFT` between rows, so the head reads as the boundary it is. Heads come from `admin_copy.COLUMN_TIME`, `COLUMN_USER`, `COLUMN_VERDICT`, `COLUMN_MODEL`, `COLUMN_TOKENS`, `COLUMN_PII`, `COLUMN_DEVICE`, `COLUMN_ID`; the two numeric heads take `align="right"` to sit over their columns.
  - `_scope_line()` — `AdminState.register_scope` in `FONT_BODY`, `TEXT_DATA`, `MUTE`. **The only `FONT_BODY` in this module** (AC 5), which Task 7 asserts by counting occurrences in the source.
- **Mirror**: `chat_ui/chat_ui/components/bubbles.py:112-120` (`_entry` — shared geometry taken once, per-kind content passed in) and `components/admin_shell.py:236-306` (a header strip: rule under, explicit padding, `flex_shrink="0"`).
- **Validate**: `ADMIN_TOKEN=test-token OPENROUTER_API_KEY=test-key PYTHONPATH=chat_ui python -c "import chat_ui.components.register as r; print(len(str(r._column_head())))"` from the repo root

### Task 6: `register()` and the page that renders it

- **Files**: `chat_ui/chat_ui/components/register.py`, then `chat_ui/chat_ui/chat_ui.py`
- **Action**: UPDATE both
- **Implement**:
  - `register() -> rx.Component` — a `rx.vstack` of two things, `spacing="0"`, `flex="1"`, `min_height="0"`, `width="100%"`:
    1. the scope strip: `_scope_line()` in a `rx.box` with `padding="0.75rem 1.5rem"`, `border_bottom=f"1px solid {theme.RULE}"`, `flex_shrink="0"`. STORY-013 adds the filter and sort controls to the right of this strip, which is why it is a strip and not a bare line.
    2. the table: `rx.box(_column_head(), rx.foreach(AdminState.visible_rows, _row), display="block", min_width=_MIN_WIDTH, custom_attrs={"role": "table"})` wrapped in the scroll container — `class_name="hx-scroll"`, `overflow_y="auto"`, `overflow_x="auto"`, `flex="1"`, `min_height="0"`, `width="100%"`, `padding_left="1.5rem"`. `min_height="0"` is AC 7: without it the flex child refuses to shrink below its content and the *page* scrolls, not the table.
    **Not `rx.auto_scroll`** — see Patterns above.
    Neither empty state is rendered here; STORY-014 wraps this call in the `rx.cond` that chooses between them, and adding a placeholder now would be a user-facing string with no home in `admin_copy.py`.
  - `chat_ui.py`: add `from chat_ui.components.register import register` to the imports and change `admin_register_page` to `return admin_page(register(), VIEW_REGISTER)`. Update the comment block at lines 57-66 — it currently says *"STORY-011 fills it with `register.py`"*, which is now done; leave the sentence about STORY-015 and `summary.py` and the sentence about not re-emitting `GLOBAL_CSS` intact, because both are still true. `admin_summary_page` keeps its `rx.fragment()`.
- **Mirror**: `chat_ui/chat_ui/chat_ui.py:57-72` — the comment block that names which story fills the slot.
- **Validate**: `python -m pytest tests/test_admin_shell.py -q` — the registration probe imports the real `rx.App` and builds every page, so a broken `register()` fails here; `EXPECTED_PAGE_KEYS` must still be exactly `["admin", "admin/audit", "admin/stats", "index"]`.

### Task 7: `tests/test_register.py`

- **File**: `tests/test_register.py`
- **Action**: CREATE
- **Implement**: the two halves `tests/test_admin_shell.py` establishes, plus a third for the preview boundary.

  **The build probe** (subprocess, fixture copied from `tests/test_admin_shell.py:189-208`). Its script imports `chat_ui.components.register`, builds `register()`, `_column_head()` and `_row` through a one-element `rx.foreach`, and emits JSON carrying: `errors`; `broken_factories`; `chat_modules_loaded` (from `sys.modules`, the transitive-import check); and `rendered` — `str(register())` — for the assertions below. Tests over it:
  - the module imports and every factory builds
  - no chat component is loaded (PRD Section 4, from the importing side)
  - all eight column heads are present in the rendered output
  - all four verdict labels are present (the four `rx.match` arms compiled, so no verdict renders as the default)
  - the four verdict ink **hex values** are all present, and the rendered output contains no other `#rrggbb` outside the allowed set `{INK, PAPER, CARD, MUTE, RULE, RULE_SOFT, SPINE, HOVER, the four inks}`. This is the same shape as STORY-018's AC 4 but scoped to this one component and computed from `theme.py` rather than hard-coded — STORY-018 extends it to the whole console and to a live page. `theme.GLOBAL_CSS` is not in this output (`admin_page()` owns it), so the `:focus-visible` exception `tests/test_admin_palette.py:15-21` warns about does not arise here; note that in the docstring so STORY-018 does not rediscover it.
  - `theme.STAMP_X`, `theme.ROW_H` and `theme.HOVER` each appear in the rendered output — the stamp margin is a fixed-width column, the rows have the register's height, and the hover ground is wired

  **The source assertions** (read the file as text, fixture per `tests/test_admin_shell.py:211-213`):
  - no literal `#rrggbb`
  - each of `COLUMN_TIME`, `COLUMN_USER`, `COLUMN_VERDICT`, `COLUMN_MODEL`, `COLUMN_TOKENS`, `COLUMN_PII`, `COLUMN_DEVICE`, `COLUMN_ID`, `AUDIT_ID_PREFIX`, `PII_INDICATOR_LABEL`, `VERDICT_CLEARED_LABEL`, `VERDICT_HELD_LABEL`, `VERDICT_DENIED_LABEL`, `VERDICT_FAULT_LABEL` reaches the screen as `admin_copy.<NAME>`, and none of their values appears as a quoted literal (parametrised exactly as `tests/test_admin_shell.py:311-328`)
  - no chat-component import (`FORBIDDEN_IMPORTS`, restated rather than imported)
  - **`theme.FONT_BODY` occurs exactly once** — AC 5's *"`FONT_BODY` appears only on the scope lines"*, made countable
  - `theme.FONT_DATA` occurs more often than `theme.FONT_DISPLAY` — AC 5's *"`FONT_DATA` is the dominant face"*, made countable in the one way that survives a refactor
  - no focus reset (`"outline": "none"`, `"box_shadow": "none"`), per `tests/test_admin_shell.py:347-355`

  **The preview boundary** (AC 8, and the honest half of it — the render half is STORY-018's, which needs a live seeded page):
  - build an `AuditLog` carrying distinctive `prompt_preview` / `response_preview` values, pass it through `to_audit_row`, and assert neither string appears in **any** field of the resulting `AuditRow` — the boundary assertion, complementing `tests/test_admin_models.py`'s field-absence check
  - extract every `row.<attr>` reference from `register.py`'s source with a regex and assert the set is a subset of `AuditRow.model_fields` — so a field that does not exist on the projection cannot be rendered, which is what makes the boundary hold for the *component* rather than only for the model. The docstring must say why these two together are the whole of what is checkable at this level, and that STORY-018 owns the live-render check.
- **Mirror**: `tests/test_admin_shell.py` end to end — same fixtures, same subprocess reasoning, same parametrised copy assertions.
- **Validate**: `ADMIN_TOKEN=test-token OPENROUTER_API_KEY=test-key python -m pytest tests/test_register.py -q`

### Task 8: the two append-only test additions

- **Files**: `tests/test_admin_formatting.py`, `tests/test_admin_state.py`
- **Action**: UPDATE (append only — neither file's existing tests may be edited)
- **Implement**:
  - `test_admin_formatting.py`: `format_count` over `0` → `"0"`, `999` → `"999"`, `3180` → `"3,180"`, `1234567` → `"1,234,567"`, `None` → `VALUE_ABSENT`. The `0` case is the one worth naming: zero recorded rows is a fact, not an absence, exactly as `tokens_used` distinguishes them at `admin_formatting.py:182-184`.
  - `test_admin_state.py`: `register_scope` on a state with 100 rows and `total_recorded = 3180` equals `"100 most recent of 3,180"` — asserted against `REGISTER_SCOPE_TEMPLATE.format(...)` so a reworded template stays a one-file change; on a state with 12 rows and `total_recorded = 12` it reads `"12 most recent of 12"` (the cap does not bind and the line does not claim it does); and after `sign_out()` it is `"0 most recent of 0"` with `rows == []`, which documents why it is a computed var and not a declared one.
- **Mirror**: `tests/test_admin_state.py:267-279` for the state-construction helpers (`_state`, `_authenticate`, `_populate`, `_sign_out`), which already exist in that file.
- **Validate**: `ADMIN_TOKEN=test-token OPENROUTER_API_KEY=test-key python -m pytest tests/ -q` → **432 + new, 0 failures**

---

## End-to-End Tests

Per PRD Section 12 Phase 2, the register is validated *"against a seeded database"*. Follow the **reflex-process-management** skill for the run/reload sequence if it has become available; otherwise use the sequence below, and investigate a failed compile from the Reflex output rather than by restarting.

Write the seed script to the scratchpad directory, **not** into the repo — this story's deliverable is the component, and a fixture script is STORY-018's to promote if it needs one.

- [ ] Seed a scratch database with ~120 rows spanning all four verdicts (`was_duplicate_blocked=True` → held; `suspicious_pattern` set → denied; `success=False` → fault; otherwise cleared), several with `pii_detected_input`/`pii_detected_output`, at least one with a NULL `model_used`, one with a NULL `tokens_used`, one with a NULL/unparseable `timestamp`, one with a >32-character `device`, and **distinctive `prompt_preview` / `response_preview` strings on every row** (AC 8). Point `DATABASE_URL` at it.
- [ ] `cd chat_ui && reflex run` — compiles with no error; `/admin/audit` serves the gate.
- [ ] Enter the correct `ADMIN_TOKEN` → the register renders 100 rows, newest first, over the eight named columns (AC 1).
- [ ] The scope line reads **"100 most recent of 120"** (AC 2). Re-seed with 12 rows and confirm it reads "12 most recent of 12" — the cap does not bind and the line does not claim it does.
- [ ] A row of each verdict is present and each carries its own ink; **cleared** is the quietest and **denied** is the one the eye finds first (AC 3).
- [ ] With 100 rows loaded, the stamp margin reads as a vertical stripe of exceptions down the left edge, blank on cleared rows (AC 4). Scroll the full window and confirm the stripe, not the table, is what the eye follows.
- [ ] Hover a row → the ground lifts to `HOVER` and every verdict ink stays readable on it.
- [ ] The numeric columns (Tokens, ID) align down the full window; the column heads stay visible while the body scrolls and stay aligned with their columns (AC 5).
- [ ] Shorten the viewport → the table scrolls **inside its own container**; the page itself does not scroll and the masthead stays put (AC 7).
- [ ] Narrow the viewport below `_MIN_WIDTH` → the table scrolls sideways in its own container; the page does not scroll horizontally.
- [ ] View source on the rendered page and search for both preview strings → **neither appears anywhere** (AC 8).
- [ ] Search the rendered page for `TINT_` values and for the two chat-only ink hexes → absent, except the `:focus-visible` outline `theme.GLOBAL_CSS` supplies globally, which `tests/test_admin_palette.py:15-21` records as a known and deliberate exception (AC 6).
- [ ] Tab through the page → focus is visible on every focusable element; nothing in the register traps focus.
- [ ] Sign out → the register is gone and the gate is back, with no row data in the page's state payload.

## Validation

```bash
# From the repo root
ADMIN_TOKEN=test-token OPENROUTER_API_KEY=test-key python -m pytest tests/ -q   # 432 + new, 0 failures
ADMIN_TOKEN=test-token OPENROUTER_API_KEY=test-key python -m pytest tests/test_register.py tests/test_admin_palette.py tests/test_contrast.py tests/test_admin_shell.py -q

# Nothing under app/ changed, for STORY-020
git diff main --stat -- app/    # empty

cd chat_ui && reflex run         # compiles; /admin/audit serves
```

---

## Risks + Mitigations

| Risk | Mitigation |
|---|---|
| **The KPI-cards-over-striped-table default** (story note, PRD Risk 6 — *"the strongest pull in this design space"*). | No cards, no fills, no accent, no zebra striping — stated in the module docstring, enforced for tints and chat-only inks by `tests/test_admin_palette.py` (which already globs this file), and for stray colour by Task 7's allowed-hex set. STORY-018 extends both to the live page. |
| **A colour arriving from Radix rather than from `theme.py`**, invisible to a source grep — the failure `admin_shell.py:181-193` records for `rx.link`. | The register uses no Radix component: every element is `rx.box`/`rx.vstack`/`rx.foreach`/`rx.match`/`rx.cond`. Task 7's allowed-hex assertion runs over the *rendered* output, so a compile-time colour would be caught even so. |
| **The scope line reading "100 most recent of 12"** on a small table — a false claim on the one line whose job is to prevent a false reading (PRD Risk 4). | `len(self.rows)`, not `REGISTER_ROW_LIMIT`. Task 8 asserts both the binding and the non-binding case. |
| **`register_scope` silently ceasing to update** — Reflex's dependency tracker warns to the browser console and returns an empty dependency set rather than raising (`admin_state.py:305-314`). | Both dependencies are loaded off `self` in the var's own body; `format_count` receives a plain `int`. The E2E re-seed step (12 rows) exercises a *change* in both, which is what a stale var would fail. |
| **The head misaligning from the body** by the 10px `.hx-scroll` scrollbar — the exact thing AC 5 rules out. | The head is `position: sticky` inside the same scroll container, so there is one scrollbar and one grid. |
| **The page scrolling instead of the table** (AC 7) — the standard flexbox trap: a flex child will not shrink below its content without `min-height: 0`. | `min_height="0"` on both `register()`'s vstack and the scroll container, called out in Task 6 rather than left to be discovered. |
| **Scope creep into STORY-012/013/014.** The disclosure, the filters and the empty states are all one small step from this file. | `_row` renders exactly nine children and the six disclosure-only `AuditRow` fields are named in Task 5 as out of scope; `register()` renders no `rx.cond` over emptiness; the scope strip is built as a strip precisely so STORY-013 can add to it without restructuring. |
| **The reflex skills are still not installed**, so no live doc lookup is available at implement time. | Both APIs this story rests on were verified by building them against `reflex==0.9.6.post1` (see *Skill availability* above), and Task 7's build probe re-verifies them on every test run. If the skills have since been installed, use them and reconcile any difference with the findings above before writing code. |

---

## Acceptance Criteria

(Copied from story `STORY-011`)

- [ ] Given `chat_ui/chat_ui/components/register.py`, when `/admin/audit` renders authenticated, then it shows the 100 most recent rows, newest first, over the columns PRD Section 4 names: timestamp (relative + absolute), `user_id`, verdict, `model_used`, `tokens_used`, PII indicator, `device`, `audit_id`.
- [ ] Given the scope line, when it renders, then it states the cap against the true total — "100 most recent of 3,180" — using `count_audit_logs()` as the denominator, so the window is never mistaken for the whole record.
- [ ] Given a row of each verdict, when the register renders, then **held**, **denied** and **fault** each carry their own ink (`INK_HELD`, `INK_DENIED`, `INK_FAULT`) and **cleared** carries `INK_CLEAR` — no two verdicts share a treatment.
- [ ] Given the stamp margin, when a hundred rows are loaded, then it is a fixed-width left column carrying each non-cleared row's verdict as a solid mark in its ink, blank for cleared rows, resolving into a vertical stripe of exceptions.
- [ ] Given the register's type, when it renders, then `FONT_DATA` is the dominant face and the numeric columns align down the full window; `FONT_DISPLAY` sets the verdict tags and column heads; `FONT_BODY` appears only on the scope lines.
- [ ] Given the register, when its rendered output is inspected, then no `TINT_*` value and no colour outside the four verdict inks plus the ground tokens appears, and no card or fill is used.
- [ ] Given the table, when the viewport is short, then it scrolls **within its own container** rather than scrolling the page.
- [ ] Given a seeded database whose rows have populated previews, when the page renders, then neither preview string appears anywhere in the output.
- [ ] All tasks completed
- [ ] `tests/` green with the 432-test baseline unmodified
- [ ] `git diff main --stat -- app/` empty
- [ ] `reflex run` compiles and serves `/admin/audit`
- [ ] Follows existing patterns
