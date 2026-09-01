---
story: STORY-019
prd: PRD-006
slug: quality-floor-and-critique
title: "Quality floor pass: keyboard, focus, narrow viewport — and a design self-critique"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-006-admin-console
created: 2026-08-31
---

# Plan: Quality floor pass: keyboard, focus, narrow viewport — and a design self-critique

## Summary

Eighteen stories built the console; this one looks at it. Nothing here is a new
capability — it is a measured pass over what is already on screen, against the
four things the **frontend-design** skill calls the quality floor (keyboard
reachability, visible focus, narrow viewport, reduced motion) plus the two
claims PRD Section 6.1 makes that only a rendered page can settle: that the
stamp margin resolves into a scannable stripe at a hundred rows, and that the
summary reads as a tally sheet rather than a dashboard. The method is
measurement, not inspection: a hundred rows across all four verdicts seeded into
a throwaway database, the production server run per the
**reflex-process-management** skill, and each floor property read out of the
live document — `document.activeElement` walked through a full Tab traversal,
`documentElement.scrollWidth` against `innerWidth` at 360px, computed
`animation-name` under an emulated `prefers-reduced-motion: reduce`, and the
left offsets of the numeric cells compared down the window. Whatever fails gets
fixed inside `chat_ui/`'s admin modules, with any new value added to `theme.py`
rather than written inline. The pass closes with the deliverable PRD Section 12
Phase 4 names: a self-critique against Section 6.1 in which at least one
accessory that does not serve the register's one job is **cut**, the cut
recorded in the story's report. Every fix and the cut are then pinned by tests,
so a floor that is met today cannot be lost silently tomorrow.

## User Story

As a compliance admin
I want the console usable on a narrow screen and from the keyboard, and stripped
of anything that does not serve the register's one job
So that the surface meets its quality bar without announcing it.

## Story Reference

- Story file: `.agents/stories/PRD-006-admin-console/STORY-019-quality-floor-and-critique.md`
- PRD: `.agents/PRDs/PRD-006-admin-console/PRD.md` — Section 4 (design & copy), Section 6.1, Section 11 (quality indicators), Section 12 Phase 4

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/chat_ui/components/{admin_shell,register,summary}.py`, `chat_ui/chat_ui/{theme,admin_copy}.py` (only if a fix needs a token or a word), `tests/` |
| Story | STORY-019 |
| PRD | PRD-006 |
| Epic Branch | `epic/PRD-006-admin-console` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| **frontend-design** (`.agents/skills/frontend-design/SKILL.md`, pinned in `skills-lock.json`) | Verbatim: *"Build to a quality floor without announcing it: responsive down to mobile, visible keyboard focus, reduced motion respected."* This story **is** that sentence. | Tasks 3, 4, 5, 6 |
| **frontend-design** | Verbatim: *"Critique your own work as you build, taking screenshots if your environment supports it – a picture is worth 1000 tokens."* The environment does support it (chrome-devtools MCP), so the stripe is judged from a screenshot, not from the code. | Tasks 7, 8 |
| **frontend-design** | Verbatim: *"Consider Chanel's advice: before leaving the house, take a look in the mirror and remove one accessory."* PRD Section 12 Phase 4 turns this into a deliverable; AC 5 turns it into a test. | Task 10 |
| **frontend-design** | Verbatim: *"Spend your boldness in one place. Let the signature element be the one memorable thing, keep everything around it quiet and disciplined, and cut any decoration that does not serve the brief."* This is the criterion the Task 10 shortlist is judged against — the signature is the stamp margin. | Tasks 8, 10 |
| **frontend-design** | Verbatim: *"nothing quietly does double duty."* The strongest cut candidates are the places the console states one fact twice. | Task 10 |
| **reflex-process-management** (plugin skill; `chat_ui/AGENTS.md` requires it verbatim for any compile/run/reload) | `reflex compile --dry` to validate; `reflex run --env prod --single-port 2>&1 \| tee reflex.log` to run; read the port out of `reflex.log` rather than assuming 8000; stop by signalling the **listening** process only, then truncate the log and restart. | Tasks 2, 3–9, 12 |
| **reflex-process-management** — Windows adaptation | The skill's `lsof -i :<port> -sTCP:LISTEN -t` does not exist on this host. The equivalent that preserves the skill's critical property (match the *listening* socket, never a browser connection) is `netstat -ano \| findstr "LISTENING" \| findstr ":<port>"` → `taskkill /PID <pid>` (`/F` only if it does not exit). Do not kill by image name. | Tasks 2, 12 |

---

## Patterns to Follow

### The floor is already built into the controls — verify, do not rebuild

```python
# SOURCE: chat_ui/chat_ui/components/register.py:286-317 (_toggle_button)
    """A real `<button>`, which is the whole of the keyboard answer: it takes focus
    in document order and fires on both Enter and Space with no key handling
    here, and `theme.GLOBAL_CSS`'s `:focus-visible` rule gives it the ring. No
    local `outline`/`box_shadow` may take that back."""
    return rx.el.button(
        mark,
        on_click=AdminState.toggle_detail(row.audit_id),
        type="button",
        ...
        custom_attrs={"aria-label": label, "aria-expanded": expanded},
    )
```

`_control_button` (`register.py:616-647`) says the same for the chips, the three
sort controls and the clear action. The expected outcome of Tasks 3 and 4 is
therefore mostly *confirmation* — and any control that fails is a real defect,
not a missing feature.

### Reduced motion and the focus ring are one shared stylesheet

```css
/* SOURCE: chat_ui/chat_ui/theme.py:110-116, 148-151 */
:focus-visible {
  outline: 2px solid {INK_UPSTREAM};
  outline-offset: 2px;
  border-radius: {RADIUS};
}

@media (prefers-reduced-motion: reduce) {
  .hx-entry, .hx-pulse { animation: none; }
  * { transition-duration: 0.01ms !important; }
}
```

`admin_page()` (`admin_shell.py`) is what carries this onto an admin page via
`rx.el.style(theme.GLOBAL_CSS)`. Two consequences the pass must respect: the
console's focus ring is `INK_UPSTREAM` **by design and by exception** — pinned
from both sides by
`tests/test_render_invariants.py::test_the_focus_ring_is_the_only_upstream_ink`
and documented in `tests/test_admin_palette.py`'s docstring — so a "stray blue"
finding here is not a finding; and `GLOBAL_CSS` is **shared with the chat**, so
AC 7 forbids editing an existing rule in it to serve the console. A new
admin-scoped rule or a new token is allowed (STORY-007's rule); retuning an
existing one is not.

### Narrow viewport is answered by wrapping, not by breakpoints

```python
# SOURCE: chat_ui/chat_ui/components/admin_shell.py:admin_masthead
        # The whole narrow-viewport answer: the two clusters wrap onto two rows
        # rather than compressing, and theme.py's hx-header-meta rule spreads
        # the second one. No new CSS.
        flex_wrap="wrap",
        row_gap="0.75rem",
```

```python
# SOURCE: chat_ui/chat_ui/components/register.py:_table, register()
    return rx.box(
        _column_head(),
        rx.foreach(AdminState.visible_rows, _row),
        min_width=_MIN_WIDTH,          # "61.25rem" — below this the ten columns crush
        custom_attrs={"role": "table"},
    )
    ...
        rx.box(
            _register_body(),
            class_name="hx-scroll",
            overflow_y="auto",
            overflow_x="auto",         # AC 2: the *container* scrolls, not the page
            flex="1",
            min_height="0",
```

`_GRID` (`register.py:117-122`) is one constant used by both the column head and
every row — the mechanism behind AC 4's "the numeric columns align down the full
window". Task 7 measures whether it holds in the browser.

### Tests: subprocess probe against a seeded database

```python
# SOURCE: tests/test_render_invariants.py:57-79, 152-170
sys.path.insert(0, str(Path(__file__).parent.parent))
_PYTHONPATH = [str(REPO_ROOT / "chat_ui"), str(REPO_ROOT)]
...
    settings.DATABASE_URL = "sqlite:///{}/console.db".format(
        tempfile.mkdtemp().replace("\\", "/")
    )
```

The admin modules import each other as `chat_ui.components...`, which resolves
only under the `chat_ui/` PYTHONPATH, so any test that renders a component runs
in a subprocess. Task 11's new tests follow `tests/test_admin_shell.py` and
`tests/test_register.py`, which already do this; the seed script in Task 1
follows the same `settings.DATABASE_URL` discipline so no test and no seed ever
touches a real `harness_ai.db`.

### Colour and size come from theme.py, never inline

```python
# SOURCE: tests/test_admin_palette.py (the STORY-018 hex guard)
ADMIN_MODULE_PATTERNS = (
    "chat_ui/chat_ui/admin_*.py",
    "chat_ui/chat_ui/components/admin_*.py",
    "chat_ui/chat_ui/components/register.py",
    "chat_ui/chat_ui/components/summary.py",
)
```

A literal hex added by this story's fixes fails that guard. Anything new goes in
`theme.py`, which is the story's own Technical Note.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/components/admin_shell.py` | UPDATE | Whatever the live pass finds (Tasks 3–6), and — on current reading, the leading candidate — the Task 10 cut |
| `chat_ui/chat_ui/components/register.py` | UPDATE (conditional) | Only if Tasks 3–7 find a defect on the register |
| `chat_ui/chat_ui/components/summary.py` | UPDATE (conditional) | Only if Task 8 finds a card, fill, accent, or a second subset signal |
| `chat_ui/chat_ui/theme.py` | UPDATE (conditional) | A new token, or a new admin-scoped `GLOBAL_CSS` rule, if and only if a fix needs one. **No existing token or rule may be retuned** (AC 7) |
| `chat_ui/chat_ui/admin_copy.py` | UPDATE (conditional) | Only if the Task 10 cut removes a string, or a fix needs a word |
| `tests/test_admin_shell.py` | UPDATE | Focus/keyboard/reduced-motion guards for the shell; the cut asserted absent |
| `tests/test_register.py` | UPDATE | The scroll container and `_GRID` alignment guards; focusable-by-construction guard |
| `tests/test_summary.py` | UPDATE | AC 6 as assertions: no card, no fill, no accent, indentation as the sole subset signal |
| `tests/test_render_invariants.py` | UPDATE (conditional) | Only if a fix or the cut needs pinning at page level rather than component level |
| `.agents/reports/PRD-006-admin-console/STORY-019-quality-floor-and-critique.report.md` | CREATE | AC 5 requires the cut recorded in the report — a report deliverable, not an optional write-up |

**Files that must NOT change** (AC 7, and PRD Section 11's quality indicators):
`chat_ui/chat_ui/state.py`, `copy.py`, `formatting.py`, `models.py`,
`components/chat.py`, `components/bubbles.py`, `components/shell.py`, and
anything under `app/`.

---

## Tasks

Execute in order. Tasks 3–9 are measurement tasks: each states what is read out
of the live page and what value passes. A task that measures a pass still
produces a recorded number for the report — "verified" without a number is not
what AC 4 asks for.

### Task 1: Seed a hundred rows across all four verdicts, without touching a real database

- **File**: `<scratchpad>/seed_register.py` (throwaway; not committed)
- **Action**: CREATE
- **Implement**:
  - Back up the console's database first: `cp chat_ui/harness_ai.db chat_ui/harness_ai.db.story019.bak`. The app runs from `chat_ui/`, and `chat_ui/.env` sets `DATABASE_URL` — that file is what the server reads. Restore it in Task 12.
  - Write ~100–120 `AuditLog` rows through `app.db.database.insert_audit_log`, importing the model from `app/db/models.py`. Do not write SQL by hand.
  - Distribution must make the stripe judgeable and match reality: the large majority **cleared**, and a scatter of ~6 **held**, ~4 **denied**, ~3 **fault** at uneven intervals. An even distribution would make any margin look like a stripe and would prove nothing.
  - Vary `user_id` (4–5 names), `model_used`, and `tokens_used` across one, two, three and four digits — AC 4's alignment claim is only testable against ragged widths.
  - Timestamps **must** use the logger's real format, `%Y-%m-%dT%H:%M:%SZ` (`app/services/audit_logger.py:8`), spread over hours. STORY-011's report records this exact trap: `datetime.isoformat()` writes microseconds, widens the column and gives a false layout signal.
  - Set `prompt_preview` / `response_preview` on every row to distinct sentinels, so Task 9's page-source check re-confirms Risk 2 for free at a hundred rows.
  - Give some rows a long real User-Agent string and some rows `pii_entities`, so the disclosure and the `minmax(9rem, 1fr)` device column are exercised.
- **Mirror**: the seeding block inside `tests/test_render_invariants.py`'s `_CHECK_SCRIPT` (lines ~152-200) — same `settings.DATABASE_URL` discipline, same `init_db()`-before-anything ordering.
- **Validate**: `python -c "from app.db.database import count_audit_logs; print(count_audit_logs())"` with the console's `DATABASE_URL` reports ≥100, and a verdict tally printed by the script shows all four non-zero.

### Task 2: Start the production server per the reflex-process-management skill

- **File**: none (process)
- **Action**: RUN
- **Implement**:
  - `cd chat_ui && reflex compile --dry` first — the skill's quick validation step, and cheaper than a failed boot.
  - `reflex run --env prod --single-port 2>&1 | tee reflex.log`, in the background.
  - Read the port from `reflex.log`'s `App running at: http://0.0.0.0:<port>` line. **Do not assume 3000 or 8000**, even though STORY-017 landed on 3000 — the skill is explicit about this and a stale assumption is how the wrong process gets signalled.
  - Note in the report that `chat_ui/reflex.lock/` will be modified by the production build; STORY-017 Deviation 5 records that it is a side effect of running, and Task 12 reverts it.
- **Mirror**: STORY-017's report, "End-to-End Verification (live, prod server on :3000)".
- **Validate**: `reflex.log` carries the running line and no traceback; `/admin/audit` returns the gate.

### Task 3: Walk the whole keyboard traversal and record the order (AC 1)

- **File**: none (measurement) — then `admin_shell.py` / `register.py` if it fails
- **Action**: VERIFY, then UPDATE only on failure
- **Implement**:
  - Gate first, unauthenticated: Tab from document start; the token field must be reachable (it also carries `auto_focus`), then the submit. Enter in the field must submit the form (`rx.form` + `type="submit"`).
  - Authenticate, then walk the authenticated register with repeated Tab, recording `document.activeElement`'s tag, `aria-label`/text and `aria-pressed`/`aria-expanded` at each stop. The expected order is document order, which is the order Section 6.1's wireframe reads in: **view switch (Summary link) → Refresh → Sign out → the four verdict chips → the search field → the three sort controls → Clear → each row's disclosure toggle, top to bottom**.
  - Confirm the active view is *not* a stop — `admin_shell.py:_view_link` renders it as plain text with `aria-current="page"` deliberately, and a focus stop on a control that does nothing is the defect, not its absence.
  - Open a disclosure with Enter, then with Space, and confirm `aria-expanded` flips and focus stays on the toggle.
  - Repeat the walk on `/admin/stats`: switch → Refresh → Sign out, and nothing else, since the summary has no controls of its own.
  - Also walk with the fault panel open (force it as STORY-017 did — hold a `BEGIN EXCLUSIVE` lock on the database from a second process): the panel's retry is `refresh_control()` and must be reachable, and it sits between the masthead and the content in document order.
- **Mirror**: the traversal contract stated in `register.py:_control_button` and `_toggle_button`; STORY-017 report check 11.
- **Validate**: every listed control appears exactly once in the walk, in the stated order, with no stop on a non-control and no keyboard trap (Shift+Tab returns the same sequence reversed).

### Task 4: Measure that focus is visible on every stop (AC 1)

- **File**: none (measurement) — then `theme.py` (admin-scoped rule only) on failure
- **Action**: VERIFY, then UPDATE only on failure
- **Implement**:
  - At each stop from Task 3, read `getComputedStyle(document.activeElement)` for `outline-style`, `outline-width` and `outline-color` after focusing **by keyboard** (`:focus-visible` does not match a mouse click, so the measurement must follow a real Tab).
  - Expected: `outline-width` ≥ 2px, `outline-style: solid`, colour `INK_UPSTREAM` — the theme rule, and the sanctioned exception (see Patterns).
  - Two stops need special attention because `GLOBAL_CSS` resets Radix fields: the gate's `#admin_token_input` and the register's `#register_filter_input` both sit inside `.hx-field-boxed`. The `.hx-field` reset that kills the outline (`theme.py`) applies to the chat composer's class, **not** to `hx-field-boxed` — confirm in the browser that the ring is actually painted on the inner `<input>` and is not clipped by the wrapper's `overflow`.
  - If a stop has no visible ring, the fix is a **new** admin-scoped rule appended to `GLOBAL_CSS` (or an inline `_focus_visible` on the admin component). Do not edit the existing `:focus-visible` or `.hx-field` rules — both serve the chat, and AC 7 forbids it.
- **Validate**: a recorded table of stop → outline width/style/colour, with every row non-`none`.

### Task 5: Narrow viewport — no horizontal page scroll, and the table scrolls in its own container (AC 2)

- **File**: none (measurement) — then the offending component on failure
- **Action**: VERIFY, then UPDATE only on failure
- **Implement**:
  - Resize to **360×740**, then **390×844**, then **640×800**, on `/admin/audit`, `/admin/stats`, and the gate.
  - The assertion at every size: `document.documentElement.scrollWidth <= window.innerWidth` (and `document.body.scrollWidth <= innerWidth`). STORY-017 made this check at 640px only; AC 2 says "a narrow viewport", and 360px is where a wrapping layout actually breaks.
  - Then the positive half, which is the part a no-overflow check cannot show: on the register, the scroll container (`class="hx-scroll"`, `overflow-x: auto`) must itself have `scrollWidth > clientWidth` and must actually scroll — read `scrollLeft` back after setting it. A table that fits because it collapsed is a failure dressed as a pass.
  - Check the register in all three states at 360px (rows, no-matches, empty) plus with the fault panel open: the empty panels are `max_width=theme.MEASURE` and the fault sentence wraps inside the same measure.
  - Watch the known suspects: the masthead's two wrapping clusters, the filter strip's two `wrap="wrap"` rows, the sort cluster's `gap="1.25rem"`, the search field's fixed `width="13rem"`, the summary's `_ranked_items` long model/user strings, and the `height="100vh"` on the authenticated column (a `100dvh` fallback is a candidate fix if mobile chrome overlap shows).
- **Validate**: nine measurements (3 widths × 3 surfaces) all satisfying `scrollWidth <= innerWidth`, plus a demonstrated horizontal scroll inside the register's container at 360px.

### Task 6: Reduced motion — nothing animates, including the loading indicator (AC 3)

- **File**: none (measurement) — then the offending component on failure
- **Action**: VERIFY, then UPDATE only on failure
- **Implement**:
  - Emulate `prefers-reduced-motion: reduce` in the browser (an emulation, not a source grep — STORY-017 could only verify this "by rule", from the served CSS, and recorded it as a deviation; AC 3 is the story that closes it by observation).
  - With the media feature active, click **Refresh** and, while the read is in flight, read `document.getAnimations()` — the correct answer is an empty list — and `getComputedStyle(el).animationName === "none"` on the `.hx-pulse` glyph.
  - Sweep every element for a running animation or a non-trivial transition:
    `[...document.querySelectorAll('*')].filter(e => { const s = getComputedStyle(e); return s.animationName !== 'none' || parseFloat(s.transitionDuration) > 0.001; })` → must be empty. This catches the `transition="background-color 120ms ease"` on the gate's submit, which the `*` rule is supposed to neutralise.
  - Slow the read enough to observe the in-flight window (hold the database lock, as STORY-017 did) rather than racing a fast local query.
  - Then repeat **without** the emulation and confirm the pulse *does* run — otherwise the check above passes for the wrong reason.
- **Mirror**: `theme.py`'s `@media (prefers-reduced-motion: reduce)` block; STORY-017 report check 9 and its Deviation 4.
- **Validate**: `getAnimations().length === 0` under reduce with a read in flight; `> 0` without it.

### Task 7: A hundred rows — does the stripe read, and do the numbers align (AC 4)

- **File**: none (measurement + screenshots) — then `register.py` / `theme.py` on failure
- **Action**: VERIFY, then UPDATE only on failure
- **Implement**:
  - Load the seeded register and take screenshots: the full window at ~1440px, a full-page capture of all hundred rows, and the same at 390px. This is the skill's *"a picture is worth 1000 tokens"* — the stripe either reads or it does not, and that judgement is made from the image, not from the grid definition.
  - Judge the margin against its stated job: with ~13 non-cleared rows scattered through ~100, can the exceptions be found by a glance down the left edge without reading the table? Record the judgement and what would have to change if not (the two levers are `theme.GLYPH` and `theme.STAMP_X`, both shared with the chat's rail — so a change there is an AC 7 problem and would instead need a new admin-only token).
  - Alignment, measured rather than eyeballed: collect `getBoundingClientRect().left` (and `.right` for the right-aligned numeric cells) for the `tokens_used` and `audit_id` cells across all visible rows. Every row must report the same value to within a pixel. Then scroll the container to the bottom and re-measure — "down the full window" is the claim, and the sticky column head is exactly where it would break.
  - Re-measure after switching the sort to user and to verdict, and after filtering: reordering must not move a column.
- **Validate**: per-column `left`/`right` variance ≤ 1px across all rows in every sort and filter state; screenshots attached to the report.

### Task 8: The summary reads as a tally sheet — no card, no fill, no accent, indentation alone (AC 6)

- **File**: none (measurement) — then `summary.py` on failure
- **Action**: VERIFY, then UPDATE only on failure
- **Implement**:
  - On the live `/admin/stats`, sweep every element under the sheet and collect computed `background-color`, `border-*`, `box-shadow` and `border-radius`. Passing means: no `background-color` other than the page's `PAPER` (and `CARD` on the masthead, which is the header, not the sheet), no `box-shadow` anywhere, no `border-radius` on a figure, and the only borders are the `RULE` / `RULE_SOFT` hairlines `_block` and `_figure` declare.
  - Collect every colour actually painted on the page and confirm the set is a subset of `{INK, MUTE, PAPER, CARD, RULE, RULE_SOFT, SPINE}` plus the four verdict inks — the summary should in fact paint no verdict ink at all, and no accent under any circumstance.
  - The subset claim, measured: the blocked figures' labels must sit at a strictly greater `getBoundingClientRect().left` than the total's, and must differ from it in **no other channel** — same font family, size, weight, colour. If a second signal (a bullet, a dash, a lighter ink, a smaller size) is doing part of the work, indentation is not carrying it "alone" and the second signal is a Task 10 cut candidate.
- **Mirror**: `summary.py:_figure` (`padding_left=indent`, `border_bottom=RULE_SOFT`) and `_indented_figure`; the allowed-colour set in `tests/test_render_invariants.py`.
- **Validate**: the measured colour set is a subset of the allowed set; blocked `left` > total `left`; no other property differing between them.

### Task 9: The chat is untouched, and nothing shared was altered to serve the console (AC 7)

- **File**: none (verification)
- **Action**: VERIFY
- **Implement**:
  - Open `/` on the same running server after every fix from Tasks 3–8 has landed: the gate, the composer, the transcript and the model selector render and behave as before. Screenshot it for the report.
  - `git diff --stat` must show no chat module changed (`state.py`, `copy.py`, `formatting.py`, `models.py`, `components/chat.py`, `components/bubbles.py`, `components/shell.py`) and nothing under `app/`.
  - If `theme.py` changed, `git diff chat_ui/chat_ui/theme.py` must be **additions only** — a new token or a new admin-scoped rule. A modified existing line is an AC 7 failure and must be reworked as an addition.
  - Re-confirm at a hundred rows what STORY-018 asserted at four: neither preview sentinel appears in `document.documentElement.outerHTML` on either page.
- **Validate**: `git diff --stat` scoped to the forbidden paths is empty; `git diff -U0 chat_ui/chat_ui/theme.py | grep '^-[^-]'` returns nothing; no sentinel in the served HTML.

### Task 10: The self-critique, and the cut (AC 5)

- **File**: the module holding whatever is cut (leading candidate: `chat_ui/chat_ui/components/admin_shell.py`), plus `admin_copy.py` if a string goes with it
- **Action**: UPDATE
- **Implement**:
  - Re-read PRD Section 6.1 in full against the screenshots from Tasks 7 and 8, and write the shortlist into the report — the skill asks for a critique, and a critique with one entry is a decision dressed as a pass. Candidates identified during planning, each with the case for and against:
    1. **The masthead's view word.** `admin_masthead` composes `CONSOLE_TITLE + MASTHEAD_SEPARATOR + view_word` → *HARNESS · REGISTER*, while the two-view switch two clusters to the right already marks the active view as plain bold text with `aria-current="page"`. The console states which view you are on **twice, within one header row**. That is precisely the skill's *"nothing quietly does double duty"*, and cutting the suffix leaves the wordmark doing the wordmark's job and the switch doing the switch's. **Strongest candidate**: it is an accessory, its removal is confined to `admin_shell.py` plus one `admin_copy` constant, it touches nothing the chat renders, and no information is lost.
    2. **The sort cluster's third control.** Three sort keys where the register's one job is *find the exceptions* — sorting by verdict groups them, sorting by user answers user story 4, and sorting by timestamp is the default the rows already arrive in. Weaker: PRD Section 4 lists all three explicitly, so this is a scope change, not a cut.
    3. **The row hover ground (`theme.HOVER`).** A second row-level signal beside the stamp margin. Weaker: `theme.py` argues its case in a comment, it is a shared token, and removing it would be an AC 7 problem.
    4. **`_figure_note` under the counts block.** If Task 8 shows the completion note repeating what the completion label already says, it is double duty. Weaker: STORY-016 pins that label deliberately.
    5. Anything Task 8 finds carrying the subset relationship alongside the indentation — that one cuts itself, because AC 6 says indentation must carry it *alone*.
  - Choose **at least one**, cut it, and justify the choice against the criterion the skill states: does it serve the register's one job? Do not cut two things to look thorough; the point is the one accessory.
  - Re-run Tasks 3–8's measurements on whatever the cut touched.
  - Record in the report: the full shortlist, the cut, the reasoning, and a before/after screenshot. AC 5 makes the report entry part of the acceptance criterion, not documentation of it.
- **Validate**: the cut element is absent from the rendered page; the console still names the current view exactly once; `python -m pytest -q` still green.

### Task 11: Pin the floor and the cut with tests

- **File**: `tests/test_admin_shell.py`, `tests/test_register.py`, `tests/test_summary.py` (and `tests/test_render_invariants.py` only if a claim needs page level)
- **Action**: UPDATE
- **Implement**: a browser measurement that nobody re-runs is a claim, not a guarantee. Add the subset of these that the pass actually establishes:
  - **Keyboard, by construction**: every interactive admin element is a native `<button>`, `<input>`, `<a>` or `<form>` control — no `div` carrying an `on_click`, and no `tabindex="-1"` anywhere in either page's output.
  - **Focus, by construction**: no admin component declares an `outline: none` / `outline="none"` / `_focus` / `_focus_visible` that removes the ring; `GLOBAL_CSS` still carries the `:focus-visible` rule.
  - **Narrow viewport, by construction**: the register's scroll container keeps `overflow-x: auto` **and** the table keeps its `min_width`; neither page's root sets a `min_width` or a fixed px `width`.
  - **Alignment, by construction**: `_GRID` remains the single constant used by both `_column_head` and `_row` — the property Task 7 measures, asserted where it cannot drift.
  - **Reduced motion**: extend the existing STORY-017 guards so the `@media (prefers-reduced-motion: reduce)` block covers every class any admin module uses for animation (today, only `.hx-pulse`).
  - **AC 6 as assertions** in `tests/test_summary.py`: no `box-shadow`, no `border-radius`, no `background_color` in the sheet's source; the blocked figures differ from the total in `padding_left` and in nothing else.
  - **The cut, asserted absent**, so it cannot be restored without a failing test — with a docstring saying what was cut and why, in the house style (`fault_panel`'s docstring records STORY-017's cut the same way).
- **Mirror**: `tests/test_admin_shell.py`'s existing `test_the_panel_paints_no_verdict_ink`, `test_the_indicator_is_the_only_moving_element`, `test_no_admin_module_declares_its_own_animation`.
- **Validate**: `python -m pytest -q` — all green, and every new test demonstrated to fail against the pre-fix code (*"a guard nobody has watched fail is a guard nobody knows is armed"* — `tests/test_admin_palette.py`'s own words).

### Task 12: Stop the server and restore everything the pass borrowed

- **File**: `chat_ui/harness_ai.db`, `chat_ui/reflex.lock/`, `chat_ui/reflex.log`
- **Action**: RESTORE
- **Implement**:
  - Stop the server by signalling the **listening** PID only (see the Windows adaptation in Skills In Use). Never kill by image name — the skill's warning about not killing the user's browser applies with more force when the matching is coarser.
  - Restore the database from the Task 1 backup and delete the backup.
  - `git checkout -- chat_ui/reflex.lock` — modified by the production build, not by this story (STORY-017 Deviation 5).
  - Confirm `chat_ui/reflex.log` is untracked/ignored, or remove it.
  - Final `git status` must show only the intended source, test and `.agents/` changes.
- **Validate**: `git status --porcelain` lists nothing unexpected; the seeded rows are gone from `chat_ui/harness_ai.db`.

---

## End-to-End Tests

Run against the live production server with the hundred-row database loaded.
Each line records a measured value in the report, not a tick.

- [ ] `reflex compile --dry` clean; server up; port read from `reflex.log`
- [ ] Gate: Tab reaches the field and the submit; Enter submits; a wrong token is refused with the one generic message and the field cleared
- [ ] Register: full Tab walk hits switch → Refresh → Sign out → 4 chips → search → 3 sort controls → Clear → each row toggle, once each, in that order; Shift+Tab reverses it
- [ ] Summary: full Tab walk hits switch → Refresh → Sign out and nothing else
- [ ] Fault panel open: the retry is in the walk, between masthead and content
- [ ] Every focus stop: computed outline ≥ 2px solid, `INK_UPSTREAM`
- [ ] Enter and Space both toggle a row disclosure; `aria-expanded` flips; focus stays put
- [ ] 360 / 390 / 640px × gate / register / summary: `documentElement.scrollWidth <= innerWidth` — nine measurements
- [ ] 360px register: the `hx-scroll` container has `scrollWidth > clientWidth` and scrolls horizontally
- [ ] 360px register in all three states and with the fault panel open: still no page overflow
- [ ] `prefers-reduced-motion: reduce` with a read in flight: `document.getAnimations().length === 0`; no element with a `transitionDuration > 0.001s`
- [ ] Without the emulation, the same read shows the pulse running (the control for the above)
- [ ] 100 rows: screenshots at 1440px full-page and at 390px; the stripe judged and the judgement recorded
- [ ] `tokens_used` and `audit_id` cell offsets vary ≤ 1px across every row, at the top and at the bottom of the scroll, in all three sorts
- [ ] Summary: measured colour set ⊆ allowed set; no shadow, no radius, no fill; blocked `left` > total `left` with no other property differing
- [ ] Both pages at 100 rows: neither preview sentinel in `outerHTML`
- [ ] `/` after all fixes: chat renders and behaves unchanged; screenshot
- [ ] The cut: absent from the page; the view named exactly once; before/after screenshots

## Validation

```bash
# compile + run (from chat_ui/, per the reflex-process-management skill)
cd chat_ui && reflex compile --dry
cd chat_ui && reflex run --env prod --single-port 2>&1 | tee reflex.log

# the suite, from the repo root
python -m pytest -q

# AC 7: nothing shared, nothing under app/
git diff --stat -- app/
git diff --stat -- chat_ui/chat_ui/state.py chat_ui/chat_ui/copy.py \
  chat_ui/chat_ui/formatting.py chat_ui/chat_ui/models.py \
  chat_ui/chat_ui/components/chat.py chat_ui/chat_ui/components/bubbles.py \
  chat_ui/chat_ui/components/shell.py
git diff -U0 chat_ui/chat_ui/theme.py | grep '^-[^-]'   # must print nothing
```

> Note carried forward from STORY-015 and STORY-017: `git diff main --stat -- app/`
> is **not** empty on this branch — `app/db/database.py` and `app/db/models.py`
> differ from `main` because of commit `3f553f2`, a PRD-004-era PII column
> migration, not because of any PRD-006 story. STORY-020 owns that reconciliation.
> This story's own check is that *it* adds nothing under `app/`.

## Acceptance Criteria

(Copied from story `STORY-019`)

- [ ] Given a keyboard-only user, when they traverse the gate, the view switch, the filters, the sort controls, the row disclosures, refresh and sign out, then every control is reachable in a sensible order with visible focus.
- [ ] Given a narrow viewport, when either page renders, then the layout holds — no horizontal page scroll — and the table scrolls within its own container.
- [ ] Given `prefers-reduced-motion: reduce`, when the console is used, then nothing animates, including the loading indicator.
- [ ] Given the register with a hundred rows loaded, when it is viewed, then the stamp margin reads as a scannable stripe and the numeric columns align down the full window — PRD Section 6.1's stated purpose is met on screen, not just in the code.
- [ ] Given a self-critique pass against Section 6.1, when it is complete, then at least one accessory that does not serve the register's one job has been identified and cut, and the cut is recorded in the story's report.
- [ ] Given the summary, when it is reviewed, then it carries no card, no fill and no accent colour, and the blocked figures read as a subset of the total by their indentation alone.
- [ ] Given the chat surface, when it is opened after this pass, then it is unchanged — no shared component or token was altered to serve the console.
- [ ] All tasks completed
- [ ] `python -m pytest -q` passes, with PRD-001/003/004 suites unmodified
- [ ] `reflex compile --dry` clean and both console views render without error
- [ ] Every new value resolves from `theme.py`; no literal hex or size added to an admin module
- [ ] Follows existing patterns
