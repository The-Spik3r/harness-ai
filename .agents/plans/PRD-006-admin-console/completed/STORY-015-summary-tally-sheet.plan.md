---
story: STORY-015
prd: PRD-006
slug: summary-tally-sheet
title: "summary.py: nine StatsResponse figures as a ruled tally sheet with stated scopes"
type: feature
complexity: HIGH
epic_branch: epic/PRD-006-admin-console
created: 2026-08-31
---

# Plan: summary.py — nine StatsResponse figures as a ruled tally sheet with stated scopes

## Summary

`/admin/stats` renders an empty `rx.fragment()` today — `chat_ui.py` says so in a
comment that names this story as the one that replaces it. This story fills that
slot with `components/summary.py`: a ruled tally sheet in three blocks, carrying
all nine `StatsResponse` figures with `blocked_duplicates` and
`blocked_suspicious` **indented beneath** `total_queries`, a scope on every
figure, the completion figure relabelled so it cannot read as an answer rate, and
PRD-003's PII telemetry rendered in a UI for the first time.

Nothing is computed in the component. Every figure is a `SummaryFigure`
(STORY-001, declared and so far unused) assembled in five `AdminState` computed
vars from STORY-004's loaded counts, STORY-008's `admin_copy` labels and
STORY-002's `format_count` / `format_share`. That is the derived-once rule this
console has held since STORY-002, and it is also the only way the share can
degrade to a placeholder on a total of 0 (AC 8) — `format_share` already returns
`SHARE_UNDEFINED` rather than dividing, and a Var cannot run that branch.

No new copy, no new theme token, no new dependency, and nothing under `app/`.
`admin_copy.py` already declares every string this sheet needs, down to
`FIGURE_COMPLETION_LABEL` and `RANKED_CUT_TEMPLATE`; `tests/test_admin_palette.py`
already globs `components/summary.py` by name, so the no-tint and no-chat-ink
guards bind the moment the file exists.

## User Story

As a compliance admin
I want each figure to say what it counts and over what window
So that I do not report a blocked-inclusive completion rate as a user success rate

## Story Reference

- Story file: `.agents/stories/PRD-006-admin-console/STORY-015-summary-tally-sheet.md`
- PRD: `.agents/PRDs/PRD-006-admin-console/PRD.md` — Section 1, Section 4 (summary),
  Section 5 (stories 6, 7), Section 6.1 (tally sheet), Section 12 Phase 3, Risk 4

## Metadata

| Field | Value |
|-------|-------|
| Type | feature |
| Complexity | HIGH (story: large) |
| Systems Affected | `chat_ui/` and `tests/` only — no change under `app/` |
| Story | STORY-015 |
| PRD | PRD-006 |
| Epic Branch | `epic/PRD-006-admin-console` (commit directly on this branch) |

**Dependencies verified** — all six `done` in
`.agents/PRDs/PRD-006-admin-console/index.md`:
STORY-002 (`0fe6c69`), STORY-004 (`e8c331e`), STORY-007 (`a650a97`),
STORY-008 (`cc857e7`), STORY-009 (`5a35ce3`), STORY-010 (`b030618`).

---

## Skills In Use

| Skill | Rule it imposes | Tasks affected |
|-------|-----------------|----------------|
| **frontend-design** (`.agents/skills/frontend-design/SKILL.md`, pinned in `skills-lock.json`) | *"a big number with a small label, supporting stats, and a gradient accent is the template answer, only use if that's truly the best option."* PRD Section 6.1 rules it out here explicitly, so the sheet is a ruled list: no card, no fill, no accent, no big-number treatment. | Tasks 4, 8, 9 |
| **frontend-design** | *"Structure is information. Structural devices… should encode something true about the content, not decorate it."* The indentation under `total_queries` **is** the subset relationship; a card grid would assert four peers, which is false. | Tasks 3, 4 |
| **frontend-design** | *"Let each element do exactly one job. A label labels, an example demonstrates, and nothing quietly does double duty."* The label names the figure, the scope states the window, the note explains the completion count — three roles, three type treatments, no doubling. | Tasks 3, 4 |
| **frontend-design** | *"Treat failure and emptiness as moments for direction… An empty screen is an invitation to act."* The nothing-to-summarize panel uses `EMPTY_SUMMARY_TITLE/BODY`, which already end in the action. | Tasks 2, 4 |
| **frontend-design** | *"before leaving the house, take a look in the mirror and remove one accessory."* Applied concretely: the indent is spacing only — no bracket, no leading mark, no second rule weight for the nested rows. | Tasks 4, 9 |
| **reflex-docs** (plugin skill, per `chat_ui/AGENTS.md`: *"For anything about Reflex APIs… use the **reflex-docs** skill rather than relying on memory"*) | Consulted for `rx.foreach` over a computed var of pydantic models, `rx.match` over a `str` var, and attribute access on an object Var. The two version-specific findings below were then **verified empirically against the pinned `reflex==0.9.6.post1`** — see "Verified Reflex behaviour". | Tasks 3, 4 |
| **reflex-process-management** (plugin skill) | Required by `chat_ui/AGENTS.md` for any compile/run cycle. Task 9's check follows it rather than inventing a run command. | Task 9 |

`.agents/skills/` contains exactly one skill directory (`frontend-design`);
`reflex-docs` and `reflex-process-management` are the Reflex plugin skills
`chat_ui/AGENTS.md` mandates. All were loaded before this plan was written.

---

## Verified Reflex behaviour (pinned `reflex==0.9.6.post1`)

Two findings from a probe run against the installed build. **The second is a trap
that fails at build time if ignored.**

1. **A computed var returning one pydantic model works, and its fields are
   reachable by attribute.** `AdminState.total_figure.label` compiles to
   `…total_figure?.["label"]`. A single-figure computed var is therefore a
   legitimate shape; solitary figures do not need one-element list wrappers.

2. **`figure.items` does NOT reach the `items` field.** `SummaryFigure.items`
   collides with `ObjectVar.items`, the dict-like method Reflex puts on every
   object Var, so `rx.foreach(figure.items, …)` raises
   `TypeError: Unsupported type <class 'method'> for LiteralVar`.
   **Use `figure["items"]`**, which returns a correctly typed `list[str]` array
   Var and compiles to `f?.["items"]`. Probe output:

   ```
   f["items"] -> ArrayCastedVar  list[str]
   Array.prototype.map.call(f_rx_state_?.["items"] ?? [], …)
   ```

   Renaming the field is not the fix:
   `tests/test_admin_models.py::test_summary_figure_fields_and_defaults` asserts
   the field set by equality, and STORY-001 pinned it deliberately.

---

## Patterns to Follow

### Figures are assembled in state, never in the component

```python
# SOURCE: chat_ui/chat_ui/admin_state.py:481-513 (register_scope)
    @rx.var
    def register_scope(self) -> str:
        return REGISTER_SCOPE_TEMPLATE.format(
            shown=format_count(len(self.rows)),
            total=format_count(self.total_recorded),
        )
```

Every dependency is read off `self` **in the var body** — Reflex's
auto-dependency tracker disassembles the function and records the attribute
loads; a value handed to a module-level helper is invisible to it, and the
failure mode is a `console.warn` plus a var that stops updating, not an
exception (`chat_ui/chat_ui/admin_state.py:380-387`).

### Precedence resolved once, in Python, then `rx.match`

```python
# SOURCE: chat_ui/chat_ui/admin_state.py:407-438 (register_state)
        if self.error:
            return REGISTER_STATE_FAULT
        if not self.rows:
            return REGISTER_STATE_EMPTY
```

```python
# SOURCE: chat_ui/chat_ui/components/register.py:1102-1121 (_register_body)
    return rx.match(
        AdminState.register_state,
        (REGISTER_STATE_EMPTY, _empty_register()),
        ...
        _table(),
    )
```

### The empty panel: type and rules, nothing else

```python
# SOURCE: chat_ui/chat_ui/components/register.py:1001-1041 (_empty_panel)
    return rx.box(
        rx.box(title, font_family=theme.FONT_DISPLAY, font_size=theme.TEXT_LEAD,
               font_weight="600", letter_spacing="-0.01em", color=theme.INK),
        rx.box(*body_children, font_family=theme.FONT_BODY,
               font_size=theme.TEXT_BODY, line_height="1.6", color=theme.MUTE,
               max_width=theme.MEASURE, margin_top="0.5rem"),
        padding="3rem 0 2rem", width="100%",
    )
```

### Type roles are inverted from the chat, and `FONT_BODY` is reserved

```python
# SOURCE: chat_ui/chat_ui/components/register.py:897-911 (_scope_line)
    """The only place `FONT_BODY` appears on this surface: PRD-006 Section 6.1
    reserves the reading face for the two or three lines that state a scope."""
```

`tests/test_register.py::test_the_body_face_is_reserved_for_the_scope_lines` and
`::test_the_data_face_is_dominant` enforce this on the register; Task 8 writes
the summary's counterpart.

### Tests: a subprocess build probe plus source assertions

```python
# SOURCE: tests/test_register.py:329-348
@pytest.fixture(scope="module")
def probe():
    proc = subprocess.run(
        [sys.executable, "-c", _CHECK_SCRIPT],
        cwd=str(REPO_ROOT / "chat_ui"),
        env={**os.environ, "PYTHONPATH": os.pathsep.join(_PYTHONPATH),
             "ADMIN_TOKEN": os.environ.get("ADMIN_TOKEN", "test-token"),
             "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", "test-key")},
        capture_output=True, text=True)
```

The subprocess exists because `summary.py` will do `from chat_ui import
admin_copy`, which resolves only under the `chat_ui/` PYTHONPATH Reflex itself
uses — importing it in-process would shadow the namespace package every other
test module reaches by its repo-root path.

---

## The nine figures, mapped

`StatsResponse` is **not touched** (AC 9). This is the render mapping only.

| `StatsResponse` field | State field (STORY-004) | Block | Label constant | Value | Share |
|---|---|---|---|---|---|
| `total_queries` | `total_recorded` | Traffic | `FIGURE_TOTAL_LABEL` | `format_count` | — |
| `blocked_duplicates` | `blocked_duplicates` | Traffic, **indented** | `FIGURE_BLOCKED_DUPLICATES_LABEL` | `format_count` | share of total |
| `blocked_suspicious` | `blocked_suspicious` | Traffic, **indented** | `FIGURE_BLOCKED_SUSPICIOUS_LABEL` | `format_count` | share of total |
| `success_rate` | `successful_queries` | Traffic | `FIGURE_COMPLETION_LABEL` + `FIGURE_COMPLETION_NOTE` | `format_count` | share of total |
| `unique_users` | `unique_users` | Who and what | `FIGURE_UNIQUE_USERS_LABEL` | `format_count` | — |
| `top_models` | `top_models` | Who and what | `FIGURE_TOP_MODELS_LABEL` | `RANKED_CUT_TEMPLATE` | — (items) |
| `top_users` | `top_users` | Who and what | `FIGURE_TOP_USERS_LABEL` | `RANKED_CUT_TEMPLATE` | — (items) |
| `pii_detected_queries` | `pii_detected_queries` | Personal data | `FIGURE_PII_QUERIES_LABEL` | `format_count` | share of total |
| `top_pii_entities` | `top_pii_entities` | Personal data | `FIGURE_TOP_PII_LABEL` | `RANKED_CUT_TEMPLATE` | — (items) |

**On `success_rate`.** `app/routers/admin.py:57` computes it as
`successful / total`, rounded to one decimal. The console holds the numerator
(`successful_queries`) and the denominator (`total_recorded`) separately, so the
figure renders the count **and** `format_share(successful_queries,
total_recorded)` — which is `success_rate`'s exact value, at `format_share`'s
deliberately identical rounding (`chat_ui/chat_ui/admin_formatting.py:96-105`).
The ninth field is therefore on screen with its own value, under a label that
says what it counts. **The computation is not fixed here**: `app/` is out of
scope and a truthful `count_answered_queries()` is deferred to PRD Section 13.

**On the PII share.** Not required by AC 2, but PRD Section 5 story 6's own
example is *"412 of 3,180 queries contained PII"* — a share is the sentence that
example asks for, and `SHARE_TEMPLATE` already exists to carry it.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/components/summary.py` | CREATE | The tally sheet: three ruled blocks, nine figures, the indent, the empty panel |
| `tests/test_summary.py` | CREATE | Build probe + source assertions: nine figures present, indent, no card/fill/accent, type roles |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | `RANKED_LIMIT`; the three summary-state keys and `summary_state`; the five figure computed vars |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | `admin_summary_page` renders `summary()` instead of `rx.fragment()` |
| `tests/test_admin_state.py` | UPDATE | Assertions over the figure vars: nine figures, shares, the 0-total placeholder, the state precedence |

Explicitly **not** changed: `app/**` (AC 9 and PRD Section 11's `git diff` bar),
`admin_copy.py` (every string already exists), `admin_models.py` (STORY-001
pinned the field set), `theme.py` (no new token needed — see Task 4),
either `requirements.txt`.

---

## Tasks

Execute in order. Each is atomic and verifiable.

### Task 1: Own the ranked cut's `5`

- **File**: `chat_ui/chat_ui/admin_state.py`
- **Action**: UPDATE
- **Implement**:
  - Add beside `REGISTER_ROW_LIMIT`:
    ```python
    # The cut on every ranked read, and the {n} the surface states
    # (admin_copy.RANKED_CUT_TEMPLATE). Passed explicitly rather than left to
    # each function's default, so "top 5" on screen and the LIMIT 5 in
    # app/db/database.py are the same 5 — admin_copy's own comment requires
    # that the copy "does not carry a second, unowned 5".
    RANKED_LIMIT = 5
    ```
  - In `_READS`, change the three ranked entries' kwargs from `{}` to
    `{"limit": RANKED_LIMIT}` (`top_models`, `top_users`, `top_pii_entities`).
- **Mirror**: `chat_ui/chat_ui/admin_state.py:92-96` and `:185`
  (`{"limit": REGISTER_ROW_LIMIT}`)
- **Do not**: change the read order, the labels, or the length of `_READS` —
  STORY-006 asserts the table has ten entries and asserts
  `reads.kwargs["rows"] == {"limit": 100}` (`tests/test_admin_state.py:505`).
- **Validate**: `python -m pytest tests/test_admin_state.py -q`

### Task 2: The summary's render states

- **File**: `chat_ui/chat_ui/admin_state.py`
- **Action**: UPDATE
- **Implement**:
  - Three keys beside the `REGISTER_STATE_*` block, carrying the same
    keys-are-not-copy comment:
    ```python
    SUMMARY_STATE_FAULT = "read_failed"
    SUMMARY_STATE_EMPTY = "nothing_recorded"
    SUMMARY_STATE_FIGURES = "figures"
    SUMMARY_STATES = (SUMMARY_STATE_FAULT, SUMMARY_STATE_EMPTY, SUMMARY_STATE_FIGURES)
    ```
    The `"read_failed"` value is deliberately the register's — a failed read
    means the same thing on both surfaces — but it gets its own name so a later
    divergence is one edit rather than a shared constant to untangle.
  - A `summary_state` computed var with this precedence, and a docstring
    recording why:
    ```python
    if self.error:
        return SUMMARY_STATE_FAULT
    if not self.total_recorded:
        return SUMMARY_STATE_EMPTY
    return SUMMARY_STATE_FIGURES
    ```
    `error` first for the reason `register_state` tests it first: a *first* read
    that raises leaves every count at 0, and rendering that as "Nothing to
    summarize" is exactly the failure-dressed-as-emptiness PRD Section 4
    forbids. The fault arm renders **the sheet**, not a panel — STORY-017 hangs
    its fault panel above it, and `FAULT_MESSAGE_TEMPLATE` promises "Nothing on
    screen has changed", so previously loaded figures must stay standing.
  - `total_recorded` is the emptiness test, not `rows`: the sheet counts the
    whole table, and a table with rows always has a non-zero total.
  - Both dependencies are read off `self` in the var body.
- **Mirror**: `chat_ui/chat_ui/admin_state.py:107-127` and `:407-438`
- **Validate**: `python -m pytest tests/test_admin_state.py -q`

### Task 3: The five figure computed vars

- **File**: `chat_ui/chat_ui/admin_state.py`
- **Action**: UPDATE
- **Implement**: import `SummaryFigure` from `.admin_models`, `SHARE_UNDEFINED`
  from `.admin_formatting`, and the figure constants from `.admin_copy`
  (`SUMMARY_SCOPE_ALL_TIME`, `SHARE_TEMPLATE`, `RANKED_CUT_TEMPLATE`, the nine
  `FIGURE_*_LABEL`s), then add one module-level helper and five computed vars:

  ```python
  def _share_line(count: int, total: int) -> str:
      """The share of the whole table one count represents, as a sentence.

      `format_share` returns SHARE_UNDEFINED on a total of 0 rather than
      dividing (admin_formatting.py), and the placeholder is returned bare:
      "— of all queries" claims a ratio exists and is merely unknown, where the
      mark alone says there is nothing to take a share of (AC 8).
      """
      share = format_share(count, total)
      if share == SHARE_UNDEFINED:
          return share
      return SHARE_TEMPLATE.format(share=share)
  ```

  | Var | Returns | Contents |
  |---|---|---|
  | `total_figure` | `SummaryFigure` | `FIGURE_TOTAL_LABEL`, `format_count(self.total_recorded)` |
  | `blocked_figures` | `list[SummaryFigure]` | duplicates then suspicious, each with `_share_line(…, self.total_recorded)` |
  | `completion_figure` | `SummaryFigure` | `FIGURE_COMPLETION_LABEL`, `format_count(self.successful_queries)`, share of total |
  | `who_figures` | `list[SummaryFigure]` | `unique_users` (count), then `top_models` and `top_users` as ranked figures |
  | `pii_figures` | `list[SummaryFigure]` | `pii_detected_queries` (count + share), then `top_pii_entities` as a ranked figure |

  - **Every figure sets `scope=SUMMARY_SCOPE_ALL_TIME`** — AC 4, and Risk 4's
    stated mitigation. No figure may be constructed without it.
  - A ranked figure is `value=RANKED_CUT_TEMPLATE.format(n=RANKED_LIMIT)` with
    `items=list(self.top_models)` (etc.) — AC 6's "cut stated on the surface".
    The ranked reads return names only (`app/db/database.py:166-193` select the
    value, not the count), so a rank line is a name; do not invent a count.
  - **Every `self.` load happens in the var body**, including the `list(...)`
    copies. Do not pass `self` to `_share_line` or to any other helper.
  - The blocked pair is a **list** because the component renders it through one
    `rx.foreach` at one indent: the indentation is the structural claim, and two
    hand-placed rows could drift apart from it.
  - Ordering inside `blocked_figures` is duplicates then suspicious, matching
    `_READS` and `StatsResponse`'s own field order.
- **Mirror**: `chat_ui/chat_ui/admin_state.py:481-547` (`register_scope`,
  `register_filtered`) for the docstring conventions and the dependency rule.
- **Do not**: add a field to `SummaryFigure` — the indent is the component's
  business, and `tests/test_admin_models.py` pins the field set by equality.
- **Validate**:
  `python -m pytest tests/test_admin_state.py tests/test_admin_models.py -q`

### Task 4: `components/summary.py` — the tally sheet

- **File**: `chat_ui/chat_ui/components/summary.py`
- **Action**: CREATE
- **Implement**: a module docstring in `register.py`'s register — what the sheet
  refuses and why, quoting PRD Section 6.1 — then this structure:

  ```
  summary()
   └ rx.vstack (scrolls in its own container: flex="1", min_height="0")
      ├ _scope_note()          SUMMARY_SCOPE_NOTE, FONT_BODY — Risk 4 in prose
      └ _sheet_body()          rx.match over AdminState.summary_state
          ├ SUMMARY_STATE_EMPTY   -> _empty_summary()
          ├ SUMMARY_STATE_FAULT   -> _sheet()   # figures stand; STORY-017 panels above
          ├ SUMMARY_STATE_FIGURES -> _sheet()
          └ default               -> _sheet()   # render the record, never a claim of emptiness

  _sheet()
   ├ _block(SUMMARY_COUNTS_HEADING,
   │     _figure(AdminState.total_figure),
   │     rx.foreach(AdminState.blocked_figures, _indented_figure),
   │     _figure(AdminState.completion_figure),
   │     _figure_note(admin_copy.FIGURE_COMPLETION_NOTE))
   ├ _block(SUMMARY_WHO_HEADING, rx.foreach(AdminState.who_figures, _figure))
   └ _block(SUMMARY_PII_HEADING, rx.foreach(AdminState.pii_figures, _figure))
  ```

  - **`_figure(figure, indent="0")`** — one ruled line: the label
    (`FONT_DISPLAY`, `TEXT_DATA`, `INK`) over the scope (`FONT_BODY`,
    `TEXT_MICRO`, `MUTE`) on the left; the value (`FONT_DATA`, right-aligned,
    `INK`) with the share beneath it (`FONT_DATA`, `MUTE`) on the right.
    `border_bottom=f"1px solid {theme.RULE_SOFT}"`, `padding_left=indent`.
    The share renders inside `rx.cond(figure.share != "", …, rx.fragment())`.
    Ranked items render inside
    `rx.cond(figure["items"], rx.foreach(figure["items"], _rank_line), _ranked_empty())`
    — **`figure["items"]`, never `figure.items`** (see "Verified Reflex
    behaviour"; the attribute form raises at build time).
  - **`_indented_figure(figure)`** = `_figure(figure, indent=theme.STAMP_X)`.
    Indentation is spacing **only** — no bracket, no leading mark, no lighter
    rule, no smaller type. It is the honest structural statement PRD Section 6.1
    asks for, and one accessory is what the skill says to remove. `theme.STAMP_X`
    rather than a fresh literal keeps the sheet's one indent on the same measure
    as the register's stamp margin, so the two views line up.
  - **`_rank_line(item)`** — one entry of a ranked list: `FONT_DATA`, `INK`.
  - **`_ranked_empty()`** — `admin_copy.RANKED_EMPTY_LABEL` in `MUTE`.
  - **`_block(heading, *children)`** — the heading in `FONT_DISPLAY` at
    `TEXT_MICRO`, uppercased with `text_transform` plus `letter_spacing`, in
    `MUTE`, over a `1px solid {theme.RULE}` top rule. A heading, not a card title.
  - **`_figure_note(text)`** — `FONT_BODY`, `MUTE`, `max_width=theme.MEASURE`,
    sitting under the completion figure. This is the second half of AC 3: the
    label states what is counted, the note says why it is not an answer rate.
  - **`_empty_summary()`** — `EMPTY_SUMMARY_TITLE` / `EMPTY_SUMMARY_BODY` in a
    locally declared panel mirroring `register.py:_empty_panel`. **Re-declared,
    not imported from `register.py`**: the same reason `admin_copy` re-declares
    the wordmark and `register.py` re-declares the stamp shape — the two views do
    not reach into each other.
  - **Colour**: `INK`, `MUTE`, `RULE`, `RULE_SOFT`, `PAPER`/`CARD` only. **No
    verdict ink on this surface** — a figure is not a verdict, and the four inks
    are the register's legend. No `TINT_*`, no `INK_UPSTREAM`, no `INK_SELF`
    (`tests/test_admin_palette.py` already globs this file for all three).
  - **No new `theme.py` token.** Sizes come from the existing scale plus layout
    literals in rem, exactly as `register.py:_GRID` uses them; only colours are
    token-only. This also keeps `tests/test_contrast.py` unchanged — the sheet
    introduces no new ink/ground pairing.
  - Narrow viewport: `wrap="wrap"` on the figure row, the same move
    `admin_masthead` and `_filter_strip` already make. No breakpoint, no new CSS.
- **Mirror**: `chat_ui/chat_ui/components/register.py:1-90` (docstring register),
  `:1001-1041` (`_empty_panel`), `:1102-1121` (`_register_body`),
  `:1123-1158` (`register()`'s scroll container)
- **Validate**:
  ```bash
  cd chat_ui && PYTHONPATH="$PWD;$PWD/.." ADMIN_TOKEN=test-token \
    OPENROUTER_API_KEY=test-key python -c \
    "from chat_ui.components.summary import summary; print(str(summary())[:200])"
  ```

### Task 5: Wire the page

- **File**: `chat_ui/chat_ui/chat_ui.py`
- **Action**: UPDATE
- **Implement**: import `summary` from `chat_ui.components.summary`; change
  `admin_summary_page` to `return admin_page(summary(), VIEW_SUMMARY)`; rewrite
  the comment above it — it currently says the summary's slot "is still the empty
  `rx.fragment()` STORY-015 replaces with `summary.py`", which stops being true.
- **Do not** re-emit `rx.el.style(theme.GLOBAL_CSS)`: `admin_page()` owns it
  (`admin_shell.py:admin_page` docstring).
- **Mirror**: `chat_ui/chat_ui/chat_ui.py:66-70`
- **Validate**:
  `python -m pytest tests/test_route_reservations.py tests/test_admin_shell.py -q`

### Task 6: State tests for the figures

- **File**: `tests/test_admin_state.py`
- **Action**: UPDATE
- **Implement**, in the file's existing style:
  - All nine `StatsResponse` fields are represented: collect the labels across
    the five vars and assert the set equals the nine `FIGURE_*_LABEL` constants,
    imported from `admin_copy` by name rather than typed as literals (AC 1).
  - Every figure carries a non-empty `scope` (AC 4).
  - `blocked_figures` is exactly two, and each share reads `SHARE_TEMPLATE`
    around `format_share` against `total_recorded` (AC 2).
  - **Total of 0**: with every count at 0, no var raises and every share is
    `SHARE_UNDEFINED` (AC 8).
  - The completion figure's value is `format_count(successful_queries)` and its
    share carries `app/routers/admin.py`'s rounding for the same pair.
  - `summary_state` precedence: `error` set with zero counts → fault, never
    empty; zero total and no error → empty; a total → figures.
  - Ranked figures carry `items` from state and a `value` of
    `RANKED_CUT_TEMPLATE.format(n=RANKED_LIMIT)` (AC 6).
  - `RANKED_LIMIT` is the kwarg on all three ranked `_READS` entries (Task 1).
  - The existing `test_sign_out_clears_every_declared_var` must still pass — the
    five figure vars are **computed**, so they are not in `base_vars`; assert the
    sheet reads as empty after `sign_out()` rather than adding a declared var.
- **Mirror**: `tests/test_admin_state.py:399-436` (the `_READS` stub harness) and
  the existing register-var assertions.
- **Validate**: `python -m pytest tests/test_admin_state.py -q`

### Task 7: `tests/test_summary.py` — the build probe

- **File**: `tests/test_summary.py`
- **Action**: CREATE
- **Implement**: `tests/test_register.py`'s probe structure — a module-scoped
  subprocess fixture with `cwd=chat_ui/`, a `PYTHONPATH` of `chat_ui/` plus the
  repo root, and `ADMIN_TOKEN` / `OPENROUTER_API_KEY` defaults — capturing each
  factory separately (`summary`, `_sheet`, `_sheet_body`, `_empty_summary`,
  `_block`, and the per-figure helpers through a real `rx.foreach`) so a failing
  test names the piece that broke. Assert:
  - the module imports and every factory builds;
  - each of the nine `FIGURE_*_LABEL` strings appears in the rendered output (AC 1);
  - the three block headings appear;
  - `FIGURE_COMPLETION_NOTE` appears, and the output contains neither
    `"success rate"` nor `"Success rate"` (AC 3 — STORY-016 pins the constant,
    this pins the screen);
  - `SUMMARY_SCOPE_ALL_TIME` and `SUMMARY_SCOPE_NOTE` both reach the output (AC 4);
  - `FIGURE_PII_QUERIES_LABEL` and `FIGURE_TOP_PII_LABEL` are present (AC 5);
  - `RANKED_CUT_TEMPLATE.format(n=RANKED_LIMIT)` reaches the output (AC 6);
  - the blocked figures render through the indented helper and no other figure
    does (AC 2);
  - no chat module is loaded: `chat_ui.components.chat` and
    `chat_ui.components.bubbles` are absent from `sys.modules` after the import.
- **Mirror**: `tests/test_register.py:190-348`
- **Validate**: `python -m pytest tests/test_summary.py -q`

### Task 8: `tests/test_summary.py` — source and palette assertions

- **File**: `tests/test_summary.py`
- **Action**: UPDATE (the same file's second half — `test_register.py` is
  organised as probe assertions then source assertions)
- **Implement**:
  - no literal hex colour anywhere in `summary.py` (regex `#[0-9a-fA-F]{6}`);
  - every colour in the rendered output resolves to an allowed value, the set
    built **from `theme.py` by name** — `INK`, `MUTE`, `RULE`, `RULE_SOFT`,
    `PAPER`, `CARD` — and the four verdict inks asserted *absent* from this
    surface (AC 7);
  - no `TINT_`, no `INK_UPSTREAM`, no `INK_SELF` in the source (belt and braces
    beside `tests/test_admin_palette.py`, which already globs the file);
  - no card: the rendered output carries no `box_shadow`, no `border_radius`,
    and no `background_color` outside the ground tokens (AC 7);
  - every user-facing string resolves through `admin_copy.` and none is written
    as a literal in the source — the `COPY_NAMES` pattern from
    `tests/test_register.py:460-476`, with the summary's own constant list;
  - `FONT_BODY` appears only on the scope note and the completion note, and
    `FONT_DATA` carries the values — the summary's counterpart of
    `test_the_body_face_is_reserved_for_the_scope_lines` and
    `test_the_data_face_is_dominant`;
  - `figure["items"]` is used and `figure.items` never is — a one-line regex
    guard, because the attribute form fails only at build time and only on the
    ranked figures.
- **Mirror**: `tests/test_register.py:444-566`
- **Validate**: `python -m pytest tests/test_summary.py -q`

### Task 9: Compile the app and look at the page

- **File**: —
- **Action**: VERIFY
- **Implement**: per the **reflex-process-management** skill, compile and run the
  app, open `/admin/stats` against the local `chat_ui/harness_ai.db`,
  authenticate with `ADMIN_TOKEN`, and check the sheet against PRD Section 6.1:
  three ruled blocks; the two blocked figures indented under the total, each with
  a count and a share; no card, fill or accent anywhere; the completion label
  reading as a completion count; the PII block closing the sheet. Then the
  **frontend-design** skill's own last step — take one look in the mirror and
  remove one accessory.
- **Validate**: the page renders authenticated with no console error, and the
  same page against an empty database shows `EMPTY_SUMMARY_TITLE` rather than
  nine dashes.

### Task 10: Prove `app/` is untouched

- **File**: —
- **Action**: VERIFY
- **Implement**: AC 9, and PRD Section 11's `git diff` quality bar.
- **Validate**:
  ```bash
  git diff main --stat -- app/            # must print nothing
  git diff main -- app/models/schemas.py  # must print nothing
  ```

---

## End-to-End Tests

- [ ] `/admin/stats` unauthenticated → the gate renders, and the counts stay at
      their defaults (the read is gated, not just the view — Risk 1)
- [ ] `/admin/stats` authenticated against a seeded database → all nine figures
      on screen, each carrying its scope
- [ ] `blocked_duplicates` and `blocked_suspicious` render indented beneath
      `total_queries`, each as a count *and* a share
- [ ] The completion figure reads as a completion count with blocked rows
      included; the words "success rate" appear nowhere on the page
- [ ] `pii_detected_queries` and `top_pii_entities` are both visible
- [ ] `top_models`, `top_users` and `top_pii_entities` render as ranked lists
      with "top 5" stated
- [ ] Empty database → the `EMPTY_SUMMARY_TITLE` panel, no exception, no
      division by zero
- [ ] A read forced to raise on a *first* load → the sheet does not claim
      "Nothing to summarize" (`summary_state` returns the fault key)
- [ ] Sign out from `/admin/stats` → the gate returns and every figure is
      cleared from state
- [ ] The rendered output contains no `prompt_preview` / `response_preview`
      value (the summary reads counts only; STORY-018 owns the register's version)

---

## Validation

```bash
# The story's own surface
python -m pytest tests/test_summary.py tests/test_admin_state.py tests/test_admin_models.py -q

# The guards that bind on this file the moment it exists
python -m pytest tests/test_admin_palette.py tests/test_contrast.py tests/test_copy.py -q

# Nothing on the chat or the REST contract moved
python -m pytest tests/test_register.py tests/test_admin_shell.py tests/test_chat_state.py \
  tests/test_audit_router.py tests/test_stats_router.py tests/test_admin_auth.py \
  tests/test_db.py tests/test_route_reservations.py -q

# Whole suite
python -m pytest -q

# AC 9
git diff main --stat -- app/
```

---

## Risks + Mitigations

| Risk | Mitigation |
|---|---|
| `figure.items` collides with `ObjectVar.items` and fails at build time | Verified against the pinned build; the plan mandates `figure["items"]`, and Task 8 adds a regex guard against the attribute form |
| The sheet drifts toward the KPI-card default (PRD Risk 6 — "the drift arrives one reasonable-looking component at a time") | Task 8's palette and no-card assertions, plus the existing `tests/test_admin_palette.py` glob, make the drift a test failure rather than a review note |
| A total of 0 divides by zero into a page render | `format_share` returns `SHARE_UNDEFINED` on a zero, absent or negative total (`admin_formatting.py:96-105`); Task 6 asserts it across all five vars |
| A first failed read renders as "Nothing to summarize" | `summary_state` tests `error` before the counts, the same precedence `register_state` holds; Task 6 asserts it |
| Adding an `indent` field to `SummaryFigure` | Rejected: the indent is a component concern, and `tests/test_admin_models.py` pins the field set by equality — the plan carries it as `_figure(…, indent=…)` |
| A computed var silently stops updating because a dependency was read outside its body | Tasks 3 and 6: every `self.` load stays in the var body, per `admin_state.py:380-387`; the tracker's failure mode is a warning, not an exception |
| `app/models/schemas.py` edited "to make the label honest" | AC 9 and Task 10; the label is fixed here, the computation is deferred to PRD Section 13 |

---

## Acceptance Criteria

(Copied from story `STORY-015`)

- [ ] Given `chat_ui/chat_ui/components/summary.py`, when `/admin/stats` renders authenticated, then all nine `StatsResponse` figures appear: `total_queries`, `blocked_duplicates`, `blocked_suspicious`, `unique_users`, `success_rate`, `top_models`, `top_users`, `pii_detected_queries`, `top_pii_entities`.
- [ ] Given `blocked_duplicates` and `blocked_suspicious`, when the sheet renders, then they are **indented beneath** `total_queries`, and each is shown as a count *and* as a share of `total_queries`.
- [ ] Given the completion figure, when its label renders, then it says it counts rows the pipeline completed without raising, blocked rows included — it does not read as an answer rate or as "success rate".
- [ ] Given every figure, when it renders, then it carries its scope: all-time over the whole table, stated distinctly from the register's last-100 window.
- [ ] Given `pii_detected_queries` and `top_pii_entities`, when the sheet renders, then both are visible — PRD-003's telemetry rendered in a UI for the first time.
- [ ] Given `top_models` and `top_users`, when they render, then they are ranked lists with the "top 5" cut stated on the surface.
- [ ] Given the sheet, when its rendered output is inspected, then it contains no card, no fill and no accent colour — only rules, type and the ground tokens.
- [ ] Given a total of 0, when the sheet renders, then every share renders its placeholder rather than raising.
- [ ] Given `app/models/schemas.py`, when the diff is inspected, then `StatsResponse` is unchanged.
- [ ] All tasks completed
- [ ] Full pytest suite passes, with PRD-001/003/004's test files unmodified
- [ ] Follows existing patterns
