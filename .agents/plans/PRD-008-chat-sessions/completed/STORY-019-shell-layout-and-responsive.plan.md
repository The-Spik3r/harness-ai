---
story: STORY-019
prd: PRD-008
slug: shell-layout-and-responsive
title: "The rail in the shell: full-width masthead kept, collapse at a narrow viewport, one transition"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-06
---

# Plan: The rail in the shell

## Summary

STORY-018 built `session_rail()` and deliberately left it unmounted — "the composition is STORY-019's" (STORY-018 report, line 63). This story mounts it. `index()`'s authenticated branch becomes `vstack(header, hstack(rail_slot, transcript_column), chat_input)`: the masthead keeps the full width, the rail and the transcript sit side by side beneath it in a flex row that owns the page's remaining height, and the composer stays along the bottom. Below `theme.SESSION_RAIL_COLLAPSE_W` (60rem, already declared by STORY-017) the rail's slot collapses to zero width and `visibility: hidden`, which both reclaims the transcript's full width and takes the rail out of tab order; a disclosure control in the masthead — displayed only below that breakpoint — brings it back. The collapse is the one animated thing this story adds, and `theme.GLOBAL_CSS`'s existing `prefers-reduced-motion` block already neutralises it. Nothing in the login gate, the two admin routes, or the session-switch path changes.

## User Story

As an employee on a laptop or a narrow window
I want the rail to give way to the conversation when there is no room for both
So that the feature that helps me switch chats does not cost me the chat I am reading.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-019-shell-layout-and-responsive.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md` — Section 4 (Surface), Section 6.1 (Layout, Motion), Section 11, Section 12 Phase 4

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/` component layer, `chat_ui` state (one presentation var), test suite |
| Story | STORY-019 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| **frontend-design** (`.agents/skills/frontend-design/SKILL.md`) | Quality floor, verbatim: *"Build to a quality floor without announcing it: responsive down to mobile, visible keyboard focus, reduced motion respected."* This story is where that floor is met for the rail. Also its motion caution (*"extra animation contributes to the feeling that the design is AI-generated"*), its CSS-specificity warning (*"It's easy to generate CSS classes that cancel each other out… often with paddings/margins between sections"*), its copy rules (*"an action keeps the same name through the whole flow"*, *"nothing quietly does double duty"*), and its closing discipline (*"before leaving the house, take a look in the mirror and remove one accessory"*). | Tasks 2, 3, 4, 6, 9, 10 |
| **reflex-docs** (plugin skill, per `chat_ui/AGENTS.md`: *"For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the reflex-docs skill rather than relying on memory"*) | The responsive API was verified against the pinned Reflex (0.9.6.post1) rather than recalled — see **Patterns to Follow → Responsive**. `rx.breakpoints(custom=…)` with CSS-unit keys compiles to `@media screen and (min-width: …)` (`reflex_base/style.py:106`), i.e. mobile-first `min-width`, so the map reads *initial → collapsed*, *60rem → open*. | Tasks 2, 3 |
| **reflex-process-management** (plugin skill, per `chat_ui/AGENTS.md`) | `reflex compile --dry` for the fast check, `reflex run --env prod --single-port 2>&1 \| tee reflex.log` for the look, and `reflex.log` first when anything fails. The skill's port/PID steps assume `lsof`; this is Windows, so the equivalents are spelled out in Task 9. Screenshots are mandatory — the skill and the story both note *"a picture is worth 1000 tokens."* | Tasks 9, 10 |

---

## Patterns to Follow

### Responsive (verified against the pinned Reflex, not recalled)

```python
# SOURCE: .venv/Lib/site-packages/reflex_base/breakpoints.py:24-42
class Breakpoints(dict[K, V]):
    def factorize(self):
        # "initial" -> "0px"; a named key -> its em value; any other key passes through
        ...

# SOURCE: .venv/Lib/site-packages/reflex_base/style.py:97-106
def media_query(breakpoint_expr: str):
    return f"@media screen and (min-width: {breakpoint_expr})"
```

Confirmed by execution against the installed version: `rx.breakpoints(custom={"initial": "none", "60rem": "flex"})` converts to `{"0px": "none", "60rem": "flex"}` and emits a `min-width` media query. Custom CSS-unit keys are supported (they are *not* supported on Radix component props — no Radix prop is made responsive here). Values may be Vars, so `rx.cond(...)` is legal inside the map.

### Layout composition — the shell as a column, sections as flex children

```python
# SOURCE: chat_ui/chat_ui/chat_ui.py:36-52
rx.cond(
    ChatState.user_id != "",
    rx.vstack(
        header(),
        rx.cond(ChatState.has_messages, message_list(), empty_state()),
        chat_input(),
        height="100vh", width="100%", spacing="0",
        background_color=theme.PAPER,
    ),
    login_gate(),
)
```

The `rx.cond` on `user_id` is the gate and does not move. `header()` and `chat_input()` are already `flex_shrink="0"`; `message_list()` and `empty_state()` already carry `flex="1"`. The new row inherits that contract.

### The rail's own contract (what the slot must not fight)

```python
# SOURCE: chat_ui/chat_ui/components/session_rail.py — session_rail()
return rx.box(
    ..., class_name="hx-scroll",
    display="flex", flex_direction="column",
    width=theme.SESSION_RAIL_W, flex_shrink="0",
    height="100%", overflow_y="auto", overflow_x="hidden",
    padding=theme.SESSION_RAIL_GUTTER,
    background_color=theme.PAPER,
    border_right=f"1px solid {theme.RULE}",
)
```

And, with history off, `session_rail()` returns `rx.fragment()` — *no node at all*. Its docstring hands this story the rest by name: "The layout around it — where this column sits, its collapse at a narrow viewport, and reclaiming its width when this function returns nothing — is STORY-019's."

### Header meta, and the breakpoint that already exists on this surface

```css
/* SOURCE: chat_ui/chat_ui/theme.py — GLOBAL_CSS, last rule */
@media (max-width: 40rem) {
  .hx-header-meta { width: 100%; justify-content: space-between; }
}
```

A second, different breakpoint already governs this page (40rem, `max-width`, on the header's meta cluster). The rail's is 60rem, `min-width`. They are not in conflict — different elements — but the skill's specificity warning applies directly: the new collapse rules go on the components as inline style props, where Reflex scopes them per element, and **nothing new is added to `GLOBAL_CSS`**, so there is no chance of a `.hx-header-meta`-style class collision or a cancelled padding.

### Reduced motion — already global, and it must stay the only answer

```css
/* SOURCE: chat_ui/chat_ui/theme.py — GLOBAL_CSS */
@media (prefers-reduced-motion: reduce) {
  .hx-entry, .hx-pulse { animation: none; }
  * { transition-duration: 0.01ms !important; }
}
```

The `*` rule already covers any `transition` this story adds. No new CSS is required for AC 4's second half; the test asserts that the coverage holds rather than adding a second, narrower rule beside it.

### A quiet control in the masthead

```python
# SOURCE: chat_ui/chat_ui/components/shell.py — header()'s logout button
rx.el.button(
    copy.SHELL_LOGOUT_LABEL,
    on_click=ChatState.logout,
    type="button", cursor="pointer",
    background="none", border="none", padding="0",
    font_family=theme.FONT_DISPLAY, font_size=theme.TEXT_DATA,
    color=theme.MUTE, _hover={"color": theme.INK},
)
```

`type="button"` is explicit (an unqualified `<button>` defaults to submit — the reason `admin_shell.py` records). The disclosure follows this shape exactly: `MUTE` → `INK` on hover, no fill, no accent, no icon.

### Presentation state on `ChatState`

```python
# SOURCE: chat_ui/chat_ui/state.py:179-181
renaming_session_id: str = ""
rename_draft: str = ""
confirming_delete_id: str = ""
```

STORY-018 put its four presentation vars here; `rail_expanded` joins them under the same reasoning. Handler shape from `cancel_rename` (`state.py:489`): `@rx.event`, sync, no database call.

### Tests — the subprocess probe

```python
# SOURCE: tests/test_session_rail.py:44-51
REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTHONPATH = [str(REPO_ROOT / "chat_ui"), str(REPO_ROOT)]
```

Two halves, as `test_session_rail.py`'s docstring fixes them: a **build probe** (renders the real page in a subprocess under the `chat_ui/` PYTHONPATH — in-process would put the inner package on `sys.path` and break every other test module) and **source assertions** (read the module as text). Structural claims go in the probe; "the source may not contain X" claims go in the grep half.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/components/shell.py` | UPDATE | `rail_slot()` (the collapsing column), `transcript_column()` (the reading column), `shell_body()` (the row), and the masthead disclosure control |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | `index()`'s authenticated branch composes `header() / shell_body() / chat_input()`; the `rx.cond` gate stays exactly where it is |
| `chat_ui/chat_ui/state.py` | UPDATE | `rail_expanded: bool = False` and `toggle_rail` — the disclosure's one bit of state |
| `chat_ui/chat_ui/theme.py` | UPDATE (verify-only; likely no edit) | `SESSION_RAIL_COLLAPSE_W = "60rem"` already exists from STORY-017. Confirm it is the only token the collapse needs |
| `tests/test_chat_shell.py` | CREATE | The layout, collapse, motion, focus-order and gate assertions for AC 1–9 |
| `tests/test_chat_state.py` | UPDATE | `rail_expanded` default, `toggle_rail`, and `logout()` resetting it |

Deliberately **not** changed: `chat_ui/chat_ui/copy.py` (STORY-017 already declared `SESSION_RAIL_SHOW_LABEL = "Chats"` *for this control*), `components/session_rail.py`, `components/chat.py`, `components/admin_shell.py`, `components/register.py`, `components/summary.py`, `tests/test_admin_shell.py`, `tests/test_register.py`.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add the disclosure's one bit of state

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**:
  - `rail_expanded: bool = False`, declared beside the STORY-018 presentation vars (`state.py:179-181`), with a comment saying what it is *not*: not a persisted preference, not a data var — the narrow-viewport disclosure's open bit, ignored entirely at or above `SESSION_RAIL_COLLAPSE_W` because the media query wins there.
  - `@rx.event def toggle_rail(self): self.rail_expanded = not self.rail_expanded` — sync, no database, mirroring `cancel_rename` (`state.py:489`).
  - In `logout()` (`state.py:330`), reset `rail_expanded = False` alongside the session state it already clears. A signed-out visitor gets the gate; leaving the bit set would open the rail for whoever signs in next in that tab.
- **Mirror**: `chat_ui/chat_ui/state.py:179-181` (declaration), `:489-493` (handler), `:330-372` (logout's clear list)
- **Do not**: name `CHAT_HISTORY_ENABLED` here — `test_chat_state_never_names_the_history_flag` (`tests/test_chat_state.py:1156`) holds and stays untouched. Absence is `session_rail()`'s question, asked once, at the surface.
- **Validate**: `.venv/Scripts/python -m pytest tests/test_chat_state.py -q`

### Task 2: `rail_slot()` — the collapsing column

- **File**: `chat_ui/chat_ui/components/shell.py`
- **Action**: UPDATE (new function)
- **Implement**: a wrapper around `session_rail()` that owns the collapse and nothing else. The rail sets its own width and `flex_shrink="0"`; the slot animates the width *around* it, so the rail's contents never reflow mid-transition.

  ```python
  _RAIL_COLLAPSE_MS = "160ms"   # inline, as chat.py writes "120ms ease" inline

  def rail_slot() -> rx.Component:
      return rx.box(
          session_rail(),
          display="flex",
          flex_shrink="0",
          overflow="hidden",
          height="100%",
          width=rx.breakpoints(custom={
              "initial": rx.cond(ChatState.rail_expanded, theme.SESSION_RAIL_W, "0"),
              theme.SESSION_RAIL_COLLAPSE_W: theme.SESSION_RAIL_W,
          }),
          visibility=rx.breakpoints(custom={
              "initial": rx.cond(ChatState.rail_expanded, "visible", "hidden"),
              theme.SESSION_RAIL_COLLAPSE_W: "visible",
          }),
          transition=f"width {_RAIL_COLLAPSE_MS} ease, visibility {_RAIL_COLLAPSE_MS} ease",
      )
  ```

  Three decisions worth the reader's time, and each belongs in the docstring:

  1. **`visibility`, not `display`, and not `opacity`.** `display: none` cannot be transitioned, and AC 4 asks for a transition. `visibility: hidden` *is* transitionable and — unlike `opacity: 0` — removes the subtree from tab order, which is what makes AC 8's focus order true while the rail is collapsed. `opacity` would leave a column of focusable buttons in a zero-width strip.
  2. **The slot animates; the rail does not.** Putting the transition on `session_rail()` would mean STORY-018's component knowing about a viewport, which its own closing docstring assigns here instead.
  3. **`session_rail()` may return `rx.fragment()`.** With `CHAT_HISTORY_ENABLED=false` the slot then wraps nothing — and the slot's `width` is declared, so an empty slot would still reserve 15rem and undo STORY-018's "absent, not empty" work. Two ways out. Preferred: the slot reserves nothing of its own (no padding, no border, no `min-width`) and its width comes from a rail that is not there — **verify this on screen and in the probe** (Task 8's flag-off case). If it still reserves width, extend the `settings.CHAT_HISTORY_ENABLED` question *inside* `session_rail.py` — the one file `tests/test_chat_sessions.py`'s allowlist names — to return the whole slot or nothing, rather than opening a second mention in `shell.py`. Record which was needed and why.
- **Mirror**: `chat_ui/chat_ui/components/session_rail.py` — `session_rail()` (the contract being wrapped); `chat_ui/chat_ui/components/chat.py` — `chat_input()` (inline duration string)
- **Validate**: `cd chat_ui && ../.venv/Scripts/reflex compile --dry`

### Task 3: The masthead disclosure

- **File**: `chat_ui/chat_ui/components/shell.py`
- **Action**: UPDATE (`header()` gains one child)
- **Implement**: an `rx.el.button` carrying `copy.SESSION_RAIL_SHOW_LABEL` — the constant STORY-017 declared *for this control* ("STORY-019's collapse control, declared here for the same reason that story declares its breakpoint token in theme.py"), so no new string is added and none is invented.
  - `on_click=ChatState.toggle_rail`, `type="button"`.
  - `custom_attrs={"aria-expanded": rx.cond(ChatState.rail_expanded, "true", "false"), "aria-controls": <the slot's id>}` — give the Task 2 wrapper an `id` (on the wrapper, so it survives the flag-off fragment). One disclosure, one controlled region.
  - `display=rx.breakpoints(custom={"initial": "inline-flex", theme.SESSION_RAIL_COLLAPSE_W: "none"})` — present only where the rail can be collapsed. At or above the breakpoint the rail is always there, and a control to show it would be a control for nothing.
  - Placed in `header()`'s **left** cluster, after the `SHELL_HEADER_BADGE` group, using the same `border_left` / `padding_left` divider the header already uses between its groups — so it reads as part of the masthead's rhythm rather than bolted on, and so DOM order answers AC 8 for free: masthead (wordmark, disclosure, model, user) → rail → transcript → composer.
  - Styling from the logout button in kind: `FONT_DISPLAY`, `TEXT_DATA`, `MUTE` → `INK` on hover, `background="none"`, `border="none"`. **No icon** (PRD Section 8 admits no icon set), **no "+"/"☰" glyph** (a user-facing string with no home in `copy.py` — `admin_shell.py`'s reason for `border_left` over a `"|"`), **no accent** (PRD Section 6.1 refuses "a bright 'New chat' button at the top"; the same refusal governs this control).
  - The label does **not** flip between "Chats" and "Hide chats": `aria-expanded` carries the state to assistive tech, and the skill's *"an action keeps the same name through the whole flow"* is better served by one word than two. `copy.py` declares one constant here, and that is not an accident.
- **Mirror**: `chat_ui/chat_ui/components/shell.py` — `header()`'s logout button and the `border_left` divider on the user group
- **Validate**: `cd chat_ui && ../.venv/Scripts/reflex compile --dry`

### Task 4: `transcript_column()` — the reading column

- **File**: `chat_ui/chat_ui/components/shell.py`
- **Action**: UPDATE (new function)
- **Implement**: the flex child holding `rx.cond(ChatState.has_messages, message_list(), empty_state())`.
  - `flex="1"`, `min_width="0"` — `min_width: 0` is the whole of AC 9's "the page body does not scroll horizontally": a flex item defaults to `min-width: auto` and refuses to shrink below its content, which is how one long unbroken token in a bubble pushes the page sideways.
  - `display="flex"`, `flex_direction="column"`, `min_height="0"`, `height="100%"`, so `message_list()`'s `flex="1"` and its `overflow-y` resolve against a definite height and the rail's `height="100%"` has a row to measure.
  - **Background**: PRD Section 6.1 states the grounds as "the rail is `PAPER` ground against the transcript's `CARD`, separated by the existing `RULE`". The transcript is currently `PAPER` (inherited from `index()`'s vstack), which the STORY-018 report flagged from the browser: *"the rail's `PAPER` ground is the same value as the page ground, so the right-hand hairline is doing all of the separating — worth checking against PRD Section 6.1's 'PAPER against the transcript's CARD' when the real layout lands."* So: set `background_color=theme.CARD` here, then **decide it on screen in Task 10** with an explicit revert criterion — if the six `TINT_*` verdict panels stop reading as panels against `CARD` (they were designed against `PAPER`), revert to `PAPER` and record the departure from Section 6.1 and its reason in the report. Either outcome is written down; neither is left to silence. `tests/test_contrast.py:94-98` already covers `INK` and `MUTE` on `CARD`, so the change introduces no new text pairing.
  - `max_width` is **not** set here. AC 7's reading measure stays where it already lives — `message_list()` and `empty_state()` each set `max_width=theme.COLUMN_MAX, margin="0 auto"` — so bubbles do not stretch into reclaimed width when the rail collapses. A second clamp here would be the skill's *"nothing quietly does double duty"*, and exactly the cancelling-margins failure it warns about.
- **Mirror**: `chat_ui/chat_ui/components/chat.py` — `message_list()` (`flex="1"`, `COLUMN_MAX`, `margin="0 auto"`); `chat_ui/chat_ui/components/shell.py` — `empty_state()` (same clamp)
- **Validate**: `cd chat_ui && ../.venv/Scripts/reflex compile --dry`

### Task 5: `shell_body()` — the row

- **File**: `chat_ui/chat_ui/components/shell.py`
- **Action**: UPDATE (new function)
- **Implement**: `rx.hstack(rail_slot(), transcript_column(), ...)` with:
  - `spacing="0"` — the rail's `RULE` hairline and its `SESSION_RAIL_GUTTER` do the separating; a stack gap would be a second, competing device (and `message_list()` sets `gap="0"` for the same kind of reason).
  - `align="stretch"`, `width="100%"`.
  - `flex="1"`, `min_height="0"` — the row takes the height `header()` and `chat_input()` leave, and its children scroll rather than grow, which is AC 9's "scrolls within its own container".
  - `overflow="hidden"` — the second half of "the page body does not scroll horizontally", and what makes the slot's width animation clip cleanly instead of shoving the transcript during the transition.
- **Mirror**: `chat_ui/chat_ui/chat_ui.py:38-51` (the vstack's `spacing="0"` and explicit sizing)
- **Validate**: `cd chat_ui && ../.venv/Scripts/reflex compile --dry`

### Task 6: Compose `index()`

- **File**: `chat_ui/chat_ui/chat_ui.py`
- **Action**: UPDATE
- **Implement**: the authenticated branch becomes `rx.vstack(header(), shell_body(), chat_input(), height="100vh", width="100%", spacing="0", background_color=theme.PAPER)`.
  - `rx.cond(ChatState.user_id != "", …, login_gate())` stays **exactly** where it is — it is the gate (AC 6), and the rail lives only inside the authenticated arm, so an unauthenticated visitor triggers no session read and sees no rail.
  - `rx.cond(ChatState.has_messages, message_list(), empty_state())` *moves into* `transcript_column()`. It is not deleted and neither arm changes.
  - Adjust the import line to name what `index()` now uses (`shell_body` in place of `empty_state`); import only what this module names.
  - `rx.el.style(theme.GLOBAL_CSS)` stays here and is **not** duplicated into `shell.py` — the mistake `session_rail.py`'s docstring and PRD-006's admin components both record.
- **Mirror**: `chat_ui/chat_ui/chat_ui.py:36-52`
- **Validate**: `cd chat_ui && ../.venv/Scripts/reflex compile --dry`

### Task 7: Confirm `theme.py` needs nothing new

- **File**: `chat_ui/chat_ui/theme.py`
- **Action**: UPDATE (verify-only; edit only if a gap is real)
- **Implement**: confirm `SESSION_RAIL_COLLAPSE_W = "60rem"` is present and is the only token the collapse needs. STORY-017 declared it with its reasoning intact — "`SESSION_RAIL_W` + `MEASURE` is 57rem, so 60rem is the width at which the rail stops costing the transcript its reading measure rather than an arbitrary device breakpoint" — which is this story's "theme.py if the breakpoint needs a token — and it does" already satisfied. The transition **duration** stays inline in `shell.py`: `chat.py` and `shell.py` both already write durations inline (`"background-color 120ms ease"`), and `theme.py`'s stated scope is colours, faces and sizes. If that judgement is reversed during implementation, the constant goes in `theme.py` and nowhere else.
- **Validate**: `grep -n "SESSION_RAIL_COLLAPSE_W" chat_ui/chat_ui/theme.py chat_ui/chat_ui/components/shell.py` — declared once, referenced by name, and `"60rem"` never written as a literal in a component.

### Task 8: `tests/test_chat_shell.py`

- **File**: `tests/test_chat_shell.py`
- **Action**: CREATE
- **Implement**: the two-halves structure `tests/test_session_rail.py` and `tests/test_admin_shell.py` both use — a subprocess build probe under the `chat_ui/` PYTHONPATH, plus source assertions over `shell.py` and `chat_ui.py` as text. Cases, mapped to ACs:
  - **AC 1** — the authenticated page renders the header, a row containing both the rail and the transcript, and the composer, in that order in the compiled output.
  - **AC 2** — the masthead is still `width="100%"` and still carries the model selector (`id="model-selector"`) and `ChatState.user_id`; it is a **sibling** of the row, never a child of it.
  - **AC 3** — the slot's `width` and `visibility` are breakpoint maps whose `initial` arm is driven by `ChatState.rail_expanded` and whose `60rem` arm is unconditional; the disclosure exists, carries `copy.SESSION_RAIL_SHOW_LABEL` and `aria-expanded`, and is `display: none` at and above the breakpoint.
  - **AC 4** — exactly one `transition` is declared across `shell.py`'s new layout functions, and it names `width` (the collapse). The two pre-existing hover transitions (the composer's send button, the gate's submit button) are excluded **by name, with the reason stated in the test's docstring**, never silently. Plus: `theme.GLOBAL_CSS`'s reduced-motion block still contains `* { transition-duration: 0.01ms !important; }`, which is what disables the collapse.
  - **AC 5** — no `transition`, no `animation`, and no `hx-entry`/`hx-pulse` class is attached to the rail slot, the row, or anything on the session-switch path; `select_session` is bound to the row button and nothing about the switch is animated.
  - **AC 6** — the unauthenticated arm is the gate: it contains no rail marker and no session-list binding. The compiled template carries both `rx.cond` arms, so this asserts over the gate arm specifically — the shape `tests/test_admin_shell.py:319` (`test_page_carries_both_gate_branches`) already handles.
  - **AC 7** — `theme.COLUMN_MAX` appears in the compiled transcript column (via `message_list()`/`empty_state()`), and `transcript_column()` itself declares no second `max_width`.
  - **AC 8** — DOM order in the compiled page is header → rail → transcript → composer; the slot uses `visibility` and **not** `opacity` for the collapsed state, so the collapsed rail leaves tab order; no layout element sets `outline: none` or otherwise cancels `GLOBAL_CSS`'s `:focus-visible` (the check `tests/test_admin_shell.py:454` makes for the console).
  - **AC 9** — the rail keeps `overflow_y="auto"` and `class_name="hx-scroll"`; the row sets `overflow="hidden"`; the transcript column sets `min_width="0"`.
  - **Flag off** — with `CHAT_HISTORY_ENABLED=false` the page renders no rail *and the slot reserves no width*. This turns Task 2's open question into an assertion, mirroring `tests/test_session_rail.py:432` (`test_the_rail_is_absent_when_history_is_off`), which already runs a probe with the flag off.
  - **Source half** — no literal hex colour in `shell.py`'s new code, no `"60rem"` literal, every new user-facing string via `copy.`, and no `rx.el.style` in `shell.py`.
- **Mirror**: `tests/test_session_rail.py:34-200` (probe fixture, `_PYTHONPATH`, source fixtures) and `tests/test_admin_shell.py:298-360`
- **Validate**: `.venv/Scripts/python -m pytest tests/test_chat_shell.py -q`

### Task 9: Compile, run, and prove the untouched surfaces

- **File**: — (verification)
- **Action**: RUN
- **Implement**: follow **reflex-process-management**.
  - `cd chat_ui && ../.venv/Scripts/reflex compile --dry`
  - `cd chat_ui && ../.venv/Scripts/reflex run --env prod --single-port 2>&1 | tee reflex.log`, then read `reflex.log` for the actual port — the skill says do not assume 8000.
  - Windows equivalents of the skill's `lsof` steps, which are POSIX-only: `netstat -ano | findstr :<port>` (or PowerShell `Get-NetTCPConnection -LocalPort <port> -State Listen`) to find the **listening** PID, then `taskkill /PID <pid>` (`/F` only if it does not stop). Truncate `reflex.log` before each restart. Production mode has no hot reload — every code change needs a restart.
  - Then, per the story and the skill (*"a picture is worth 1000 tokens"*), take screenshots at **five** points: wide with the rail open (≥60rem); just below the breakpoint with the rail collapsed; the same width with the disclosure toggled open; the same toggle with `prefers-reduced-motion: reduce` emulated; and the login gate.
  - **AC 10 is a test run, not a screenshot**: `.venv/Scripts/python -m pytest tests/test_admin_shell.py tests/test_register.py -q` must pass with **no modification to either file** — confirm with `git diff --stat tests/test_admin_shell.py tests/test_register.py` reporting nothing. Also open `/admin/register` and `/admin/summary` in the browser and confirm no rail and no chat state.
- **Validate**: `reflex.log` free of tracebacks; both admin suites green and undiffed; five screenshots captured.

### Task 10: The self-critique pass — "remove one accessory"

- **File**: `chat_ui/chat_ui/components/shell.py` (and the report)
- **Action**: REVIEW
- **Implement**: with the rail actually on screen, run the skill's closing discipline against the rail's one job — *get me back into the right one, and get out of the way*. Four questions the story and the STORY-018 report already put on the table; each gets an answer in the report whichever way it goes:
  1. **Two rails on one screen.** The transcript's `RAIL_X`/`GLYPH` rail and the session rail's spine are now visible together. PRD Section 6.1 argues they do not compete "because they operate at different scales and mark different things", and the story asks for this to be confirmed rather than assumed. Look; if they *do* compete on screen, the finding belongs in the report — the story says so explicitly.
  2. **The transcript ground.** Task 4's `CARD` decision, resolved on screen against the six `TINT_*` panels, with the outcome and its reason recorded.
  3. **The composer's alignment.** The composer spans the full width beneath both columns (as PRD Section 6.1's wireframe draws it) and centres its `COLUMN_MAX` on the *full* width, so with a 15rem rail present it no longer aligns with the bubbles above it. Judge this on screen. If it reads as broken, that is a decision to record — not a silent move of `chat_input()` inside the transcript column, which would contradict AC 1's "composer along the bottom".
  4. **The always-visible Rename/Delete pair.** The STORY-018 report handed this forward by name: it "is visually busier than a hover-revealed menu would be, which is the deliberate cost of AC 8 and should be re-examined in that story's own 'remove one accessory' pass rather than quietly reverted." Re-examine it here. Hiding it on hover is refused by STORY-018's AC 8 and by PRD Section 6.1's kebab-menu refusal, so any change is a finding for the report, not an edit to `session_rail.py`.
  - **The one accessory actually removed** is then named in the report. If nothing is removed, say why — a pass that always finds something is a pass that is inventing one.
- **Validate**: the report's self-critique section names each of the four and states what was cut.

### Task 11: Extend the state tests

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE
- **Implement**: `rail_expanded` defaults `False`; `toggle_rail` flips it and flips back; `logout()` resets it to `False`; and `toggle_rail` touches nothing else — no session read, no change to `messages`. Follow the file's existing case style and the STORY-018 cases it already carries.
- **Mirror**: `tests/test_chat_state.py` — the STORY-018 presentation-var cases ("`begin_rename` seeds and closes confirmation", "`cancel_rename` discards without dispatching")
- **Validate**: `.venv/Scripts/python -m pytest tests/test_chat_state.py -q`

---

## End-to-End Tests

For `/implement` to execute:

- [ ] Sign in; the page is masthead across the top, rail left, transcript right, composer along the bottom
- [ ] The masthead still spans the full width and still carries the model selector and the signed-in user
- [ ] Narrow the window below 60rem: the rail disappears, the transcript takes the full width, the **Chats** disclosure appears in the masthead
- [ ] Click **Chats**: the rail returns with a width transition, and `aria-expanded` flips to `true`
- [ ] With `prefers-reduced-motion: reduce` emulated, the same toggle is instant
- [ ] Switch sessions at a wide viewport: the transcript is replaced and nothing animates
- [ ] Load the page signed out: the gate only — no rail, and no session read in `reflex.log`
- [ ] With ~30 sessions, the rail scrolls inside its own container; the composer stays put and the page body has no horizontal scrollbar
- [ ] Send a message containing one very long unbroken token: the page still does not scroll horizontally
- [ ] Tab from the top: masthead controls → rail rows and their Rename/Delete → transcript → composer, with a visible ring at every stop; when the rail is collapsed, Tab skips it entirely
- [ ] `CHAT_HISTORY_ENABLED=false`: no rail, no reserved width, chat fully working
- [ ] `/admin/register` and `/admin/summary` render unchanged — no rail, no chat state

## Validation

```bash
cd chat_ui && ../.venv/Scripts/reflex compile --dry
cd chat_ui && ../.venv/Scripts/reflex run --env prod --single-port 2>&1 | tee reflex.log

.venv/Scripts/python -m pytest tests/test_chat_shell.py tests/test_chat_state.py tests/test_session_rail.py -q
.venv/Scripts/python -m pytest tests/test_admin_shell.py tests/test_register.py -q
git diff --stat tests/test_admin_shell.py tests/test_register.py   # must be empty
.venv/Scripts/python -m pytest -q                                   # full suite
```

## Acceptance Criteria

(Copied from story `STORY-019`)

- [ ] Given `chat_ui/chat_ui/chat_ui.py`'s `index()`, when it renders signed-in, then the layout is masthead across the full width, rail and transcript side by side beneath it, composer along the bottom.
- [ ] Given the masthead, when it renders, then it still spans the full width and still carries the model selector and the signed-in user.
- [ ] Given a narrow viewport, when the page renders, then the rail collapses and the transcript keeps the full width, with a control to bring the rail back.
- [ ] Given the collapse, when it animates, then it is the **only** transition on the surface, and it is disabled under `prefers-reduced-motion`.
- [ ] Given a session switch, when it happens, then nothing animates.
- [ ] Given the login gate, when an unauthenticated visitor loads the page, then it is unchanged — no rail, no session read, exactly as today.
- [ ] Given the transcript column, when the rail is present, then `theme.COLUMN_MAX` still governs the reading measure and the bubbles do not stretch to fill the reclaimed width.
- [ ] Given keyboard navigation, when the user tabs through the page, then the order is masthead → rail → transcript → composer, with visible focus at every stop.
- [ ] Given the rail with many sessions, when it overflows, then it scrolls **within its own container** and the page body does not scroll horizontally.
- [ ] Given the two admin routes, when they render, then they are untouched — no rail, no chat state, and `tests/test_admin_shell.py` and `tests/test_register.py` pass unmodified.
- [ ] All tasks completed
- [ ] `reflex compile --dry` succeeds and `reflex run --env prod` serves without tracebacks
- [ ] Full suite green, with the two named suites unmodified
- [ ] Follows existing patterns

---

## Risks + Mitigations

| # | Risk | Mitigation |
|---|------|------------|
| 1 | **AC 4 read literally is already false.** `chat_input()`'s send button and `login_gate()`'s submit button both carry `transition="background-color 120ms ease…"` from PRD-004. The collapse cannot be the *only* transition on the surface without removing those. | Scope AC 4 to the layout: the collapse is the only transition this story adds and the only one that moves geometry; the two pre-existing transitions are colour-only hover affordances that predate PRD-008. Excluded **by name** in the AC 4 test with the reason in its docstring, and recorded as a finding in the report rather than silently reinterpreted. Removing them is a PRD-004 surface change and out of scope. |
| 2 | **`visibility: hidden` is the wrong tool and `display: none` is untransitionable.** Get this wrong and either the collapsed rail keeps a column of buttons in tab order (AC 8 fails silently) or there is no transition to disable (AC 4 fails). | `visibility` chosen deliberately: transitionable *and* removes the subtree from tab order. Asserted in the AC 8 test (`visibility` present, `opacity` absent) and verified by actually tabbing in Task 9. |
| 3 | **An empty slot reserves 15rem when `CHAT_HISTORY_ENABLED=false`**, undoing STORY-018's "absent, not empty" work. | Task 2 states both fixes and the preference between them; Task 8's flag-off probe turns it into an assertion, mirroring `tests/test_session_rail.py:432`. If the wrapper must ask the flag, the question is extended inside `session_rail.py` — the one allowlisted mention — and never opened in `shell.py`. |
| 4 | **Flexbox `min-width: auto` sends the page sideways** on a long unbroken token, breaking AC 9 in a way that only appears with real content. | `min_width="0"` on the transcript column and `overflow="hidden"` on the row, both asserted in Task 8 and both looked at in Task 9 with a long-token message. |
| 5 | **CSS specificity and cancelling paddings** — the skill's named failure mode, and this story adds a section boundary between three stacked regions. | Every collapse rule is an inline style prop on a component, where Reflex scopes it per element; **nothing new goes into `GLOBAL_CSS`**. The existing `@media (max-width: 40rem)` header rule is left alone, and its coexistence with the 60rem `min-width` breakpoint is documented in Patterns. |
| 6 | **The `CARD` transcript ground is a whole-surface change** made inside a layout story, and the six `TINT_*` panels were designed against `PAPER`. | Task 4 sets it, Task 10 decides it on screen against a stated revert criterion, and the report records the outcome either way. `tests/test_contrast.py:94-98` already covers `INK`/`MUTE` on `CARD`, so no new text pairing is introduced. |
| 7 | **`rail_expanded` puts a fifth presentation var on `ChatState`**, and `state.py` is not among the story's listed files. | A deliberate, named deviation: STORY-018 set the precedent with four such vars, `logout()` already has a clear-list to join, and the alternative (a CSS `:checked` sibling hack) trades a real `<button>` for a hidden input — worse on exactly the axis AC 8 measures. Recorded in the report. |
