---
story: STORY-018
prd: PRD-008
slug: session-rail-component
title: "session_rail.py: the spine as the active mark, three states, no fill and no pill"
type: NEW_CAPABILITY
complexity: HIGH
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-06
---

# Plan: session_rail.py — the spine as the active mark, three states, no fill and no pill

## Summary

Build `chat_ui/chat_ui/components/session_rail.py`: a fixed-width `PAPER` column listing `ChatState.sessions` newest-activity-first, each row a title in `FONT_DISPLAY`/`TEXT_DATA` over an activity time in `FONT_DATA`/`TEXT_TAG`, with the active row marked by a solid `SPINE` bar on its left edge and by nothing else. The component renders three mutually exclusive body states — no sessions, sessions listed, a read that failed — plus a **New chat** control at the top, per-row rename and delete affordances that are real `<button>`s in document order, and a delete confirmation that names the chat. Every string comes from `copy.py` (STORY-017 landed all of them) and every colour and size from `theme.py` (`SESSION_RAIL_W`, `SESSION_RAIL_ROW_H`, `SESSION_RAIL_GUTTER` landed with it). Because Reflex has no component-local state, the rail's four UI-only vars and their events are added to `ChatState`, along with the `sessions_total` field and `rail_scope` computed var the cap statement needs — which requires one new service wrapper, `chat_sessions.count(identity)`, over the already-written `database.count_chat_sessions`. Layout integration into the shell is STORY-019; the design-guard tests are STORY-020.

## User Story

As an employee
I want a list of my conversations that gets me back into the right one and out of the way
So that switching subjects costs a glance and a click rather than a scroll through one endless transcript.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-018-session-rail-component.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md` — Section 4 (Surface), Section 6.1 (all), Section 7, Section 11, Section 12 Phase 4, Risk 6

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | HIGH |
| Systems Affected | `chat_ui/` components, `chat_ui/` state, `app/services/chat_sessions.py`, `tests/` |
| Story | STORY-018 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |

**Dependencies verified**: STORY-012 (`543922c`), STORY-013 (`ba43c5c`), STORY-016 (`310ac02`), STORY-017 (`9df2a39`) — all `status: done`.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| **frontend-design** | *"Spend your boldness in one place. Let the signature element be the one memorable thing, keep everything around it quiet and disciplined, and cut any decoration that does not serve the brief."* The spine is that one place; everything else is rules and type. Also its quality floor — *"visible keyboard focus"* — and its copy rules: *"an empty screen is an invitation to act"*, *"errors don't apologize"*, *"an action keeps the same name through the whole flow"*. Its governing rule here is that **a pinned direction wins**: PRD Section 6.1 and `theme.py` are the pin, so this story proposes no direction. | Tasks 2–8, Task 11 (the "remove one accessory" pass) |
| **reflex-docs** | `chat_ui/AGENTS.md`, verbatim: *"For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs."* Covers `rx.foreach` over the summaries, `rx.cond` for the active mark and the three states, and `rx.el.button` semantics. **Confirm against the pinned `reflex==0.9.6.post1`** (`chat_ui/requirements.txt:9`) before writing, not from recall. | Tasks 1, 3–8 |
| **reflex-process-management** | `chat_ui/AGENTS.md`, verbatim: *"When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill."* | Task 10 (compile probe), Task 11 (run + screenshot) |

---

## Patterns to Follow

### The signature mark — the same device at a third scale

```python
# SOURCE: chat_ui/chat_ui/components/register.py:166-200
def _stamp(ink: str) -> rx.Component:
    """The mark itself: a stamped square, the same one the chat's rail carries."""
    return rx.box(
        width=theme.GLYPH,
        height=theme.GLYPH,
        flex_shrink="0",
        border_radius="1px",
        background_color=ink,
    )


def _stamp_margin(row) -> rx.Component:
    return rx.box(
        rx.match(
            row.verdict,
            (VERDICT_HELD, _stamp(theme.INK_HELD)),
            ...
            rx.fragment(),
        ),
        width=theme.STAMP_X,
        flex_shrink="0",
        align_self="stretch",
        display="flex",
        ...
    )
```

The rail's mark is this shape at the third scale: `width=theme.GLYPH`, `height` stretched to the row rather than square, `background_color=theme.SPINE`, inside a `width=theme.RAIL_X` margin box — `RAIL_X` reused, not re-declared, exactly as `theme.STAMP_X = RAIL_X` does it (`chat_ui/chat_ui/theme.py:84-86`, asserted by identity in `tests/test_admin_palette.py`).

### Keyboard-reachable control with no chrome of its own

```python
# SOURCE: chat_ui/chat_ui/components/register.py:288-320
def _toggle_button(row, mark: str, label: str, expanded: str) -> rx.Component:
    """The disclosure control for one row, drawing no chrome of its own.

    A real `<button>`, which is the whole of the keyboard answer: it takes focus
    in document order and fires on both Enter and Space with no key handling
    here, and `theme.GLOBAL_CSS`'s `:focus-visible` rule gives it the ring. No
    local `outline`/`box_shadow` may take that back.

    `type="button"` is explicit for the reason `admin_shell.py`'s sign-out
    records: an unqualified <button> defaults to submit.
    """
    return rx.el.button(
        mark,
        on_click=AdminState.toggle_detail(row.audit_id),
        type="button",
        cursor="pointer",
        background="none",
        border="none",
        padding="0",
        ...
        custom_attrs={"aria-label": label, "aria-expanded": expanded},
    )
```

This is the whole answer to AC 8 (*"reachable by keyboard with visible focus and not hover-only"*): real `<button>`s, no `_hover`-gated `display`, no local outline override.

### Row-keyed open state, never DOM-held

```python
# SOURCE: chat_ui/chat_ui/components/register.py:279-286
def _is_open(row):
    """`Var.contains()` and not `in`: the `in` operator is not supported on Vars.
    The set is `audit_id`s, so the answer follows the row through any reorder."""
    return AdminState.open_rows.contains(row.audit_id)
```

Register's reason applies verbatim to the rail and harder: `rx.foreach` compiles to a `.map()` keyed by position, and **the rail reorders on every send** (`_promote_session`, `chat_ui/chat_ui/state.py:534-555`). A rename field or a delete confirmation held by position would reattach to whichever chat landed in that slot. So both are keyed on `session_id` — here a single `str` var rather than a set, because only one row may be renaming or confirming at a time.

### The scope line, computed Python-side

```python
# SOURCE: chat_ui/chat_ui/admin_state.py:606-635
@rx.var
def register_scope(self) -> str:
    """... a hard-coded 100 would render "100 most recent of 12", which is false on
    a young deployment ..."""
    return REGISTER_SCOPE_TEMPLATE.format(...)
```

```python
# SOURCE: chat_ui/chat_ui/components/register.py:898-906
def _scope_line() -> rx.Component:
    """"100 most recent of 3,180" — the window, stated against the whole record."""
    return rx.box(
        AdminState.register_scope,
        ...
    )
```

The component reads a `str` var; the formatting is Python-side. `copy.SESSION_RAIL_SCOPE_TEMPLATE = "{shown} most recent of {total}"` (`chat_ui/chat_ui/copy.py:217`) is the rail's equivalent and takes the same treatment.

### Rows read fields; they do not compute

```python
# SOURCE: chat_ui/chat_ui/models.py:42-50
    session_id: str = ""
    title: str = ""
    # Humanized activity time, precomputed in the backend: component functions
    # only ever see Vars, so datetime math cannot run at render.
    activity_info: str = ""
```

Three fields, and the rail renders two of them plus the id it dispatches on. Nothing else.

### Tests — build probe in a subprocess, then source assertions

```python
# SOURCE: tests/test_register.py:1-52 (and tests/test_chat_components_import.py:1-27)
"""**The build probe** runs in a subprocess with `PYTHONPATH` set to `chat_ui/`,
which is how Reflex itself imports the app (`chat_ui.components...`, not
`chat_ui.chat_ui.components...`). Doing it in-process would put the inner
package on `sys.path` and break every other test module ...

**The source assertions** read the module as text. They cover the acceptance
criteria a build cannot: that no colour is written as a literal hex, that every
string resolves from `admin_copy` ..."""

REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTHONPATH = [str(REPO_ROOT / "chat_ui"), str(REPO_ROOT)]
```

```python
# SOURCE: tests/test_chat_components_import.py:70-73
# Renderers receive a Var, never a concrete ChatMessage: rx.foreach hands them
# a JS reference. Exercising them any other way would not compile the same code.
message_var = ChatState.messages[0]
```

The rail's row functions take `ChatState.sessions[0]` for the same reason.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/chat_sessions.py` | UPDATE | Add `count(identity)` — the flag short-circuit and the `_wrapped` error contract live here and nowhere else, so the rail's total cannot reach `database.count_chat_sessions` any other way. |
| `chat_ui/chat_ui/state.py` | UPDATE | `sessions_total`, `rail_scope`, `history_enabled`; the four rail UI vars and their six events; `retry_sessions`; `_load_sessions` extracted from `login`. |
| `chat_ui/chat_ui/components/session_rail.py` | CREATE | The component: header + New chat, the three body states, the row with its spine, rename and delete. |
| `tests/test_chat_sessions.py` | UPDATE | `count` — flag off, ownership, and that it ignores `CHAT_SESSION_LIMIT`. |
| `tests/test_chat_state.py` | UPDATE | The new vars and events: scope var, retry, rename/delete UI flow, and that they clear on `logout`. |
| `tests/test_session_rail.py` | CREATE | Build probe + source assertions, mirroring `tests/test_register.py`'s two halves. STORY-020 extends this file with the design guards; do not pre-empt them. |

**Not in this story**: `chat_ui/chat_ui/chat_ui.py` and `components/shell.py` (STORY-019 owns the composition and the collapse), `tests/test_contrast.py` and the palette-drift guard (STORY-020). `theme.py` and `copy.py` are **complete** — if this story needs a token or a string that is not there, that is a STORY-017 defect to record, not a literal to write.

---

## Design Decisions

### 1. Where the `CHAT_HISTORY_ENABLED` branch goes (AC 10)

PRD Section 6 says *"the service returns empty lists and writes nothing, and the rail renders as absent. **No caller branches on the flag.**"* Read against `app/services/chat_sessions.py:18-20` — which pins the rule as *"an `if settings.CHAT_HISTORY_ENABLED` anywhere but here and `app/config.py` is a"* [defect] — the prohibition is on **data-access callers**: nothing between the service and the database may re-ask the question the service already answered.

But "absent" is not a data question, and no amount of empty lists produces it: an empty list is AC 5's invitation state, which is precisely what AC 10 says the rail must **not** be. Something at the surface has to render nothing.

**Decision**: exactly one branch, expressed once, at the top of `session_rail()`:

```python
return rx.cond(ChatState.history_enabled, _rail(), rx.fragment())
```

`ChatState.history_enabled` is an `@rx.var` reading `settings.CHAT_HISTORY_ENABLED` — precedent `chat_ui/chat_ui/admin_state.py:33,944`, which imports `from app.config import settings` and reads it in state. The var exists so the branch is one expression in one module rather than a flag consulted per row, and so STORY-019 can hang the column's `display` off the same var without adding a second reading of the setting.

**Assumption recorded**: STORY-019 additionally removes the rail's *column* from the layout on the same var, so nothing reserves width for an absent rail. If the reviewer reads Section 6 as forbidding even this single surface branch, the alternative is a `chat_sessions.enabled()` accessor that moves the same `if` behind a function call — a rename, not a removal — and the finding belongs in the report.

### 2. The confirmation is the component's, and it is inline

STORY-016 pinned this in `delete_session`'s docstring, verbatim (`chat_ui/chat_ui/state.py:457-462`): *"`rx.window_alert` and `rx.alert_dialog` both exist in the pinned Reflex, and neither is used: the confirmation is STORY-018's component, and a state handler that popped its own dialog would put the flow's gate in a layer the component cannot replace. This handler *is* the confirmed branch."*

**Decision**: no `rx.alert_dialog`. The confirming row **replaces its own content in place** with the confirmation sentence and two buttons. Three reasons, all from the brief:

1. A modal is the assistant-app sidebar's other half — it arrives with rounded corners, an overlay tint and a red destructive button, which is three of Risk 6's named drifts in one component.
2. `rx.alert_dialog` supplies colour and radius at compile time. `register.py:57-60` refused `rx.accordion` for exactly that: *"`rx.accordion` additionally supplies colour at compile time"*.
3. In-place is honest about scope: the thing being deleted is the row you are looking at, and it stays on screen while you decide.

`copy.SESSION_DELETE_CONFIRM_TEMPLATE` names the chat and states the record is kept; `SESSION_DELETE_CONFIRM_LABEL` ("Delete") and `SESSION_DELETE_CANCEL_LABEL` ("Keep chat") are the two doors. Per the skill's *"an action keeps the same name through the whole flow"*, the row affordance and the confirming button both read **Delete** — which `chat_ui/chat_ui/copy.py:139` already records as deliberate.

### 3. Rename is inline too, and its state is keyed on `session_id`

`rename_session(session_id, title)` exists (`chat_ui/chat_ui/state.py:376`) and refuses an empty title silently by design. The rail supplies the field. `renaming_session_id` + `rename_draft` are keyed vars for the `_promote_session` reorder reason above.

The row is a `<button>`; a text input cannot be nested inside a button (invalid HTML, and the click would be swallowed). **So the row's clickable element and its rename field are siblings in the row box, swapped by `rx.cond` on `renaming_session_id == row.session_id`** — never nested.

### 4. Three states are `rx.cond`, and their order encodes the story's rule

AC 6: *"a failed read must never render a silently empty list, which would read as 'you have no chats'."* So the fault check is **outermost**:

```
rx.cond(sessions_error != "",  _fault_state(),
rx.cond(sessions.length() > 0, _session_list(),
                               _empty_state()))
```

A read that failed leaves `self.sessions = []` **and** sets `sessions_error` (`chat_ui/chat_ui/state.py:219-220`), so the two conditions are simultaneously true on that path and only the order distinguishes them. Getting this backwards is the exact conflation PRD-006's Risk called out for its register, which the story names.

### 5. What the rail does *not* get

Applying the skill's *"remove one accessory"* before building rather than after:

- **No icon** for New chat. `copy.SESSION_NEW_CHAT_LABEL` is the whole control; PRD Section 8 says *"no icon set"*.
- **No count badge, no model, no verdict summary** on a row — `ChatSessionSummary` has three fields and `models.py:28-33` records that the absence is the design.
- **No hover-revealed controls.** AC 8 forbids hover-only; the affordances are always in the DOM and always focusable.
- **No `rx.el.style(theme.GLOBAL_CSS)`** — `index()` already carries it (story's last technical note).
- **No border radius** except `theme.RADIUS`, and none at all on a row. The pill is Risk 6's named first step.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Confirm the Reflex API surface against the pinned build

- **File**: none (research)
- **Action**: READ
- **Implement**: Per `chat_ui/AGENTS.md`, use the **reflex-docs** skill — not recall — to confirm for `reflex==0.9.6.post1` (`chat_ui/requirements.txt:9`): `rx.foreach` over a `list[pydantic.BaseModel]` state var; `rx.cond` nesting and its two-arm form; `Var.length()` and `Var.contains()` on a list var; comparing a `str` Var to a Var (`ChatState.active_session_id == row.session_id`) inside `rx.cond`; passing an argument to an event handler from inside `rx.foreach` (`ChatState.select_session(row.session_id)`); `rx.el.button` props and `custom_attrs`; `rx.input` `value`/`on_change`/`on_blur`/`on_key_down`.
- **Mirror**: `chat_ui/chat_ui/components/register.py:279-320` already exercises most of these against this exact pin.
- **Validate**: Record in the report any API that differs from what `register.py` uses. If `Var.length()` is unavailable, `rx.cond(ChatState.sessions, ...)` on truthiness is the fallback — decide here, not mid-component.

### Task 2: Add `count(identity)` to the sessions service

- **File**: `app/services/chat_sessions.py`
- **Action**: UPDATE
- **Implement**: Add, next to `list_for`:
  ```python
  def count(identity: Identity) -> int:
      """How many sessions this identity has in total, cap or no cap. ..."""
      if not settings.CHAT_HISTORY_ENABLED:
          return 0
      with _wrapped("count"):
          return database.count_chat_sessions(identity.user_id)
  ```
  Docstring carries the reason `database.count_chat_sessions` already records (`app/db/database.py:1757-1770`): `len(list_for(...))` can never exceed the limit it was called with, so a capped list reports "50 of 50" on an account with two hundred and is indistinguishable from one with exactly fifty. State explicitly that it **ignores `CHAT_SESSION_LIMIT`**, and that `identity` is required and undefaulted per Risk 2 — the rule that lives in the signature.
- **Mirror**: `app/services/chat_sessions.py:126-150` (`list_for`) — same flag short-circuit, same `_wrapped` wrapper, same `identity.user_id` scoping.
- **Validate**: `python -m pytest tests/test_chat_sessions.py tests/test_session_ownership.py -q` — including the signature-inspection test, which must accept the new function without modification.

### Task 3: Extend `ChatState` with the rail's data vars

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**:
  1. `sessions_total: int = 0` in the var block, with a comment saying why it is not `len(self.sessions)`.
  2. Extract the session-loading body of `login` (lines ~212-249) into `async def _load_sessions(self, identity) -> None`, and have it set `sessions_total` from `await asyncio.to_thread(chat_sessions.count, identity)` on the success arm and `0` on the `ChatSessionError` arm. **Keep `login`'s behaviour byte-identical otherwise** — the transcript auto-open and both failure arms move as they are.
  3. `@rx.var def rail_scope(self) -> str` returning `""` when `sessions_total <= len(self.sessions)` (nothing is being withheld, so say nothing) and `copy.SESSION_RAIL_SCOPE_TEMPLATE.format(shown=len(self.sessions), total=f"{self.sessions_total:,}")` otherwise. Thousands separator Python-side, per `admin_state.py:606-635`.
  4. `@rx.var def history_enabled(self) -> bool: return settings.CHAT_HISTORY_ENABLED`, with the Decision-1 note in its docstring. Add `from app.config import settings` — mirror `chat_ui/chat_ui/admin_state.py:33`.
  5. `@rx.event async def retry_sessions(self)` — re-resolves the Identity from `_token`, sets `sessions_error = SESSION_INVALIDATED_ERROR` and returns if it is `None`, otherwise calls `_load_sessions`. It re-reads the **list only**; it does not touch `messages` or `active_session_id`, because AC 6's fault state is about the list and the transcript on screen is still true.
  6. In `delete_session`, decrement `sessions_total` on the success path (guarding at zero) so the scope line does not go stale after a delete; in `_do_send`'s lazy-create arm, increment it.
- **Mirror**: `chat_ui/chat_ui/state.py:183-250` (`login`), `:376-444` (`rename_session`) for the `resolve(self._token)` / `SESSION_INVALIDATED_ERROR` prologue every handler shares.
- **Validate**: `python -m pytest tests/test_chat_state.py -q` — existing tests must pass **unmodified**, which is the proof the `login` extraction changed no behaviour.

### Task 4: Extend `ChatState` with the rail's four UI vars and six events

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: Add to the var block, with a comment marking them as **presentation state, keyed on `session_id`, never on list position** (the `_promote_session` reorder reason):
  ```python
  renaming_session_id: str = ""
  rename_draft: str = ""
  confirming_delete_id: str = ""
  ```
  And the events:
  - `begin_rename(session_id, title)` — sets both; clears `confirming_delete_id` (only one row is ever in a mode); returns `rx.set_focus(...)` on the field id if Task 1 confirms a per-row id is workable, otherwise `auto_focus` on the input.
  - `set_rename_draft(text)` — plain setter, mirroring `set_input_text` (`state.py:170-172`).
  - `commit_rename()` — clears `renaming_session_id`/`rename_draft` and **returns** `ChatState.rename_session(sid, draft)`; the existing handler owns the empty-title refusal and the ownership re-check, and this must not duplicate either.
  - `cancel_rename()` — clears both, writes nothing.
  - `ask_delete(session_id)` — sets `confirming_delete_id`; clears `renaming_session_id`.
  - `cancel_delete()` — clears it.
  Guard `begin_rename` and `ask_delete` with `if self.pending: return`, matching `new_chat` and `edit_and_resend` (`state.py:310-323`).
  Clear all three vars in `logout()` (`state.py:252-286`) alongside `sessions`, and clear `confirming_delete_id` at the end of `delete_session` — a confirmation for a row that is gone must not survive it.
- **Mirror**: `chat_ui/chat_ui/state.py:287-317` (`new_chat`) for the guard-and-clear shape; `admin_state.py`'s `toggle_detail` for keyed UI state.
- **Validate**: `python -m pytest tests/test_chat_state.py -q`

### Task 5: Create the rail's frame — module docstring, header, New chat, scope line

- **File**: `chat_ui/chat_ui/components/session_rail.py`
- **Action**: CREATE
- **Implement**: Imports `import reflex as rx` and `from chat_ui import copy, theme` / `from chat_ui.state import ChatState` — the **inner-package** form every component uses (`components/chat.py:3-17`), because that is how Reflex imports the app.
  Module docstring in the house style: what the surface is, **what it refuses** (quote PRD Section 6.1's assistant-app-sidebar paragraph), where the boldness is spent, why type is `FONT_DISPLAY` for titles (*"labels on a shelf, not prose"*), and that this module reads fields and does not compute.
  Then:
  - `_rail_label()` — `copy.SESSION_RAIL_SHOW_LABEL` as a quiet eyebrow in `FONT_DISPLAY`/`TEXT_TAG`, `theme.MUTE`, letter-spaced like `shell.py:_label` (`components/shell.py:17-27`).
  - `_new_chat_button()` — `rx.el.button(copy.SESSION_NEW_CHAT_LABEL, on_click=ChatState.new_chat, type="button", ...)`. **Not** the composer's inverted `INK` fill (`components/chat.py:77-99`): PRD Section 6.1 refuses *"a bright 'New chat' button at the top"*. It is `INK` type on `PAPER`, a `RULE` hairline top and bottom or none at all, `border_radius=theme.RADIUS`, `_hover={"background_color": theme.HOVER}`. Full rail width, left-aligned with the rows so the `RAIL_X` margin runs unbroken down the column.
  - `_scope_line()` — `rx.cond(ChatState.rail_scope != "", rx.box(ChatState.rail_scope, ...), rx.fragment())` in `FONT_DATA`/`TEXT_TAG`/`MUTE`.
  - `session_rail()` — the public entry: `rx.cond(ChatState.history_enabled, _rail(), rx.fragment())` per Decision 1, and `_rail()` the `PAPER` column at `width=theme.SESSION_RAIL_W`, `padding=theme.SESSION_RAIL_GUTTER`, `border_right=f"1px solid {theme.RULE}"`, `flex_shrink="0"`, `class_name="hx-scroll"` with `overflow_y="auto"` (STORY-019 AC 9 wants the rail scrolling in its own container; giving it the existing scrollbar styling here costs nothing and keeps `theme.py` the single source).
- **Mirror**: `chat_ui/chat_ui/components/register.py:127-165` for the small-helper style; `components/shell.py:17-27` for `_label`.
- **Validate**: `PYTHONPATH=chat_ui:. python -c "from chat_ui.components.session_rail import session_rail; print(type(session_rail()))"` — imports and builds.

### Task 6: The row, and the spine

- **File**: `chat_ui/chat_ui/components/session_rail.py`
- **Action**: UPDATE
- **Implement**:
  - `_is_active(row)` → `ChatState.active_session_id == row.session_id`.
  - `_spine(row)` — **the signature**. `rx.box(rx.cond(_is_active(row), rx.box(width=theme.GLYPH, height="100%", background_color=theme.SPINE, border_radius="1px"), rx.fragment()), width=theme.RAIL_X, flex_shrink="0", align_self="stretch", display="flex", align_items="center")`. Docstring states the PRD's sentence verbatim and names the two things it must not become: a fill, and a pill. `RAIL_X` and `GLYPH` and `SPINE` are **reused by name**, not by value — the identity guarantee `theme.py:99-108` and `tests/test_admin_palette.py` both insist on.
  - `_row_title(row)` — `row.title` in `theme.FONT_DISPLAY` / `theme.TEXT_DATA` / `theme.INK`, `font_weight="500"` for **every** row (AC 2 forbids bold as an active mark, so weight cannot vary), single line with `overflow="hidden"`, `text_overflow="ellipsis"`, `white_space="nowrap"`.
  - `_row_activity(row)` — `row.activity_info` in `theme.FONT_DATA` / `theme.TEXT_TAG` / `theme.MUTE`.
  - `_row_open_button(row)` — `rx.el.button(_row_title(row), _row_activity(row), on_click=ChatState.select_session(row.session_id), type="button", ...)`, transparent background, no border, `text_align="left"`, `width="100%"`, `min_height=theme.SESSION_RAIL_ROW_H`, `cursor="pointer"`, `_hover={"background_color": theme.HOVER}`. **The active row gets no background of its own** — hover is a pointer affordance, not the active mark. No `aria-current` fill; use `custom_attrs={"aria-current": rx.cond(_is_active(row), "true", "false")}` if Task 1 confirms a Var is accepted there, otherwise omit it and note why.
  - `_row(row)` — `rx.box(_spine(row), rx.box(<open button or rename field>, _row_actions(row), ...), display="flex", align_items="stretch", border_bottom=f"1px solid {theme.RULE_SOFT}")`. Hairline between rows, nothing else: no card, no radius, no fill.
  - `_session_list()` — `rx.box(rx.foreach(ChatState.sessions, _row), ...)`. `ChatState.sessions` is already newest-activity-first (`ORDER BY updated_at DESC`, and `_promote_session` maintains it), so the component **does not sort** — AC 1's ordering is the state's guarantee and the docstring says so.
- **Mirror**: `chat_ui/chat_ui/components/register.py:166-209` (`_stamp` / `_stamp_margin`), `:471-535` (`_row_line` / `_row`).
- **Validate**: build probe as Task 5; visually confirm in Task 11 that exactly one row carries a spine.

### Task 7: Rename and delete affordances, and the in-place confirmation

- **File**: `chat_ui/chat_ui/components/session_rail.py`
- **Action**: UPDATE
- **Implement**:
  - `_action_button(label, on_click)` — a shared quiet `<button>`: `FONT_DISPLAY`/`TEXT_TAG`/`theme.MUTE`, `_hover={"color": theme.INK}`, `type="button"`, no background, no border, **no `display` gated on hover**. AC 8 in one helper.
  - `_row_actions(row)` — `_action_button(copy.SESSION_RENAME_LABEL, ChatState.begin_rename(row.session_id, row.title))` and `_action_button(copy.SESSION_DELETE_CONFIRM_LABEL, ChatState.ask_delete(row.session_id))`. Both always rendered, always in tab order, after the row's open button so the order reads open → rename → delete.
  - `_rename_field(row)` — `rx.input(value=ChatState.rename_draft, on_change=ChatState.set_rename_draft, on_blur=ChatState.commit_rename, placeholder=copy.SESSION_RENAME_PLACEHOLDER, auto_focus=True, class_name="hx-field", ...)` wrapped in an `rx.form(on_submit=ChatState.commit_rename)` so Enter commits, with Escape → `ChatState.cancel_rename` via `on_key_down` if Task 1 confirms the key API; if it does not, a visible **Keep chat**-style cancel button is the fallback and the report records the substitution. Type is `FONT_DISPLAY`/`TEXT_DATA` — the field must look like the title it replaces.
  - `_delete_confirm(row)` — replaces the row's content: the sentence `copy.SESSION_DELETE_CONFIRM_TEMPLATE.format(title=row.title)` — **build it with `.format()` on the Var per Task 1's finding; if the pinned build cannot format a Var, use `f"…"` via `rx.Var` string concatenation or a `@rx.var` on state that formats `confirming_delete_id`'s title Python-side, and record which** — in `FONT_BODY`/`TEXT_DATA`, then `_action_button(copy.SESSION_DELETE_CONFIRM_LABEL, ChatState.delete_session(row.session_id))` and `_action_button(copy.SESSION_DELETE_CANCEL_LABEL, ChatState.cancel_delete)`. **No verdict ink on the Delete button** — AC 3 forbids it, and a red destructive button is Risk 6's drift arriving as good practice. The confirmation's own weight is that it is a sentence naming the chat.
  - Wire the three-way row body: `rx.cond(ChatState.confirming_delete_id == row.session_id, _delete_confirm(row), rx.cond(ChatState.renaming_session_id == row.session_id, _rename_field(row), rx.fragment(_row_open_button(row), _row_actions(row))))`.
- **Mirror**: `chat_ui/chat_ui/components/register.py:288-345`; `components/chat.py:57-110` for the `rx.form` + `rx.input` shape.
- **Validate**: build probe; Task 11 drives rename, cancel, delete, cancel-delete by keyboard alone.

### Task 8: The three states

- **File**: `chat_ui/chat_ui/components/session_rail.py`
- **Action**: UPDATE
- **Implement**:
  - `_empty_state()` — `copy.SESSION_RAIL_EMPTY_TITLE` in `FONT_DISPLAY`/`TEXT_DATA`/`INK`, `copy.SESSION_RAIL_EMPTY_BODY` in `FONT_BODY`/`TEXT_DATA`/`MUTE` beneath. An invitation, not a census; no illustration, no button repeating New chat (which is already at the top — *"nothing quietly does double duty"*).
  - `_fault_state()` — `copy.SESSION_RAIL_FAULT_TITLE`, then `copy.SESSION_RAIL_FAULT_BODY`, then a retry `_action_button(..., ChatState.retry_sessions)`. **`ChatState.sessions_error` is not rendered as the message**: `chat_ui/chat_ui/copy.py:201-206` records that it holds `str(exc)` from the storage layer and that the rail *"names its own failure in the two constants and treats `sessions_error` as the trigger, not as the text."* The retry's label is `copy.SESSION_RAIL_FAULT_BODY`'s promise made clickable — use the constant STORY-017 provided; if no retry label constant exists, that is a STORY-017 gap to record, **not** a literal to write here.
  - `_body()` — the nesting from Decision 4, fault outermost.
- **Mirror**: `chat_ui/chat_ui/components/shell.py:146-192` (`empty_state`); `register.py:1140` for the "scope statements are still true of an empty register" reasoning, which applies to `_scope_line` sitting outside `_body`.
- **Validate**: Task 9's tests assert all three branches are reachable and distinct.

### Task 9: Tests — build probe and source assertions

- **File**: `tests/test_session_rail.py`
- **Action**: CREATE
- **Implement**: Two halves, per `tests/test_register.py`'s docstring.
  **Build probe** (subprocess, `PYTHONPATH=[chat_ui/, repo root]`): imports `session_rail` and every private helper; calls each row helper with `ChatState.sessions[0]` (a Var, per `test_chat_components_import.py:70-73`); asserts `str(session_rail())` is non-empty and contains no `GLOBAL_CSS` marker (the story's last technical note, checked rather than trusted).
  **Source assertions** (read the module as text):
  - No literal `#RRGGBB` — reuse `test_admin_palette.py:_literal_hexes`'s detector shape (`re.findall(r"#[0-9a-fA-F]{6}\b", source)`).
  - Every user-facing string reaches the screen through `copy.` — assert each of the eight constants the rail consumes appears as `copy.NAME`, and that none of their **values** appears as a literal in the source.
  - `theme.SPINE`, `theme.RAIL_X` and `theme.GLYPH` all appear — the signature is present and is the reused device, not a parallel one.
  - No `SESSION_RAIL_` token is written as its value (`"15rem"`, `"3rem"`, `"0.75rem"`) — STORY-017's single-file rule, and the defect that story exists to prevent.
  - Type roles: `FONT_DISPLAY` accompanies `TEXT_DATA` for titles and `FONT_DATA` accompanies `TEXT_TAG` for the activity time, per PRD Section 6.1.
  - Three-state reachability: the source names `SESSION_RAIL_EMPTY_TITLE`, `SESSION_RAIL_FAULT_TITLE` and `rx.foreach` — an empty list and a failed read cannot render the same thing.
  Add a module docstring stating that **the design guards are STORY-020's** and this file will be extended, not replaced.
- **Mirror**: `tests/test_register.py:1-120`, `tests/test_admin_palette.py:63-75`, `tests/test_chat_components_import.py:53-95`.
- **Validate**: `python -m pytest tests/test_session_rail.py -q`

### Task 10: Tests — state and service

- **File**: `tests/test_chat_state.py`, `tests/test_chat_sessions.py`
- **Action**: UPDATE
- **Implement**:
  - `count`: returns `0` when `CHAT_HISTORY_ENABLED=false`; counts only the calling identity's rows; **exceeds `CHAT_SESSION_LIMIT`** when the user has more (seed limit+2, assert the count is limit+2 while `list_for` returns limit) — the one assertion that proves the "50 of 50" lie is fixed; wraps a `StorageError` as `ChatSessionError`.
  - `rail_scope`: `""` when nothing is withheld; the template with a thousands separator when it is.
  - `retry_sessions`: repopulates `sessions` and clears `sessions_error` after a failing read starts succeeding; leaves `messages` untouched; sets `SESSION_INVALIDATED_ERROR` on a dead token.
  - The UI vars: `begin_rename` refused while `pending`; `commit_rename` delegates to `rename_session` and clears the draft; `cancel_rename` writes nothing; `ask_delete`/`cancel_delete` set and clear; `delete_session` clears `confirming_delete_id` and decrements `sessions_total`; `logout` clears all four.
- **Mirror**: existing cases in each file; use the same fixtures from `tests/conftest.py`.
- **Validate**: `python -m pytest tests/test_chat_state.py tests/test_chat_sessions.py tests/test_session_ownership.py -q`

### Task 11: Compile, run, look, and remove one accessory

- **File**: none (verification)
- **Action**: VERIFY
- **Implement**: Follow the **reflex-process-management** skill for the compile-and-run sequence. Temporarily mount `session_rail()` in `index()` to see it — **revert that before committing**, since the composition is STORY-019's. Sign in against a seeded database with several sessions and drive the whole surface **by keyboard only**: tab order, visible focus at every stop, New chat, select, rename (commit and cancel), delete (confirm and cancel). Force `sessions_error` to see the fault state; sign in as a user with no sessions to see the empty state; set `CHAT_HISTORY_ENABLED=false` and confirm nothing renders. Take screenshots — the skill notes *"a picture is worth 1000 tokens."*
  Then the frontend-design skill's closing discipline, verbatim: *"Consider Chanel's advice: before leaving the house, take a look in the mirror and remove one accessory."* Run it against the rail's one job — **get me back into the right one, and get out of the way** — and cut whatever fails it. Record what was cut in the report; if nothing was, record that too, and why.
- **Validate**: screenshots attached to the report; full suite green.

---

## End-to-End Tests

- [ ] Sign in with several seeded sessions → rail lists them newest-activity-first, titles and activity times only.
- [ ] Exactly one row carries a `SPINE` mark, and it is the active one; no row carries a fill, a rounded highlight or a bold title.
- [ ] Click a non-active row → `select_session` runs, the transcript swaps, the spine moves.
- [ ] Send a message in the second-most-recent chat → that row moves to the top and keeps the spine.
- [ ] Click a row **while a send is in flight** → nothing happens; the transcript does not swap (STORY-015's guard).
- [ ] **New chat** → transcript empties, no row is marked, no row is added to the rail (nothing is written until the first send).
- [ ] Tab from the composer → every rail control is reachable with a visible focus ring; no affordance requires hover.
- [ ] Rename: Enter commits and the title changes in place without the row moving; Escape/blur-cancel leaves it unchanged; an empty title is refused silently.
- [ ] Delete: the confirmation names the chat and says the record is kept; **Keep chat** cancels and writes nothing; **Delete** removes the row and lands on the next chat.
- [ ] Sign in as a user with no sessions → the invitation, not "no chats found", and not the fault state.
- [ ] Force a read failure → the fault line and a working retry, **never** a silently empty list.
- [ ] Seed more than `CHAT_SESSION_LIMIT` sessions → the scope line states the cap against the true total ("50 most recent of 212"); with fewer, no scope line at all.
- [ ] `CHAT_HISTORY_ENABLED=false` → the rail is absent, and the chat is fully working.
- [ ] Both admin routes render untouched.

## Validation

```bash
python -m pytest tests/test_session_rail.py tests/test_chat_state.py tests/test_chat_sessions.py -q
python -m pytest -q                      # full suite; the Section 11 list unmodified
PYTHONPATH=chat_ui:. python -c "from chat_ui.components.session_rail import session_rail; session_rail()"
cd chat_ui && reflex run                 # per reflex-process-management
```

## Acceptance Criteria

(Copied from story STORY-018)

- [ ] `session_rail.py` lists `ChatState.sessions` newest-activity-first, each row showing the title and the relative activity time and nothing else.
- [ ] The active session is marked by a solid vertical mark in `SPINE` on the left edge of its row — and by nothing else: no fill, no rounded highlight, no bold, no accent.
- [ ] The rendered output contains no `TINT_*` value, no verdict ink, and no border radius beyond `theme.RADIUS`.
- [ ] A **New chat** control sits at the rail's top, calling STORY-016's `new_chat()`.
- [ ] With no sessions, the empty state invites the user to start one, using STORY-017's copy.
- [ ] On a failed read, the rail shows the fault line naming what failed with a retry — never a silently empty list.
- [ ] Clicking a row runs `select_session(...)` and swaps the transcript; a click during an in-flight send is refused per STORY-015's guard.
- [ ] The rename and delete affordances are reachable by keyboard with visible focus and are not hover-only.
- [ ] Delete's confirmation names the chat and states the record is kept; only a confirmed delete calls `delete_session(...)`.
- [ ] With `settings.CHAT_HISTORY_ENABLED is False` the rail is **absent** — not empty, not disabled.
- [ ] With `CHAT_SESSION_LIMIT` sessions loaded, the cap is stated against the true total from `count_chat_sessions(...)`.
- [ ] Every user-facing string resolves from `copy.py` and every size and colour from `theme.py`.
- [ ] All tasks completed
- [ ] Full test suite passes; the Section 11 suites pass unmodified
- [ ] `reflex run` compiles and the rail renders in all three states
- [ ] Follows existing patterns (`register.py`'s stamp margin, `test_register.py`'s two-halves test shape)

---

## Risks + Mitigations

| Risk | Mitigation |
|------|-----------|
| **The rail drifts into the assistant-app sidebar** (PRD Risk 6) — a card for a row, a rounded highlight for the active one, an accent for the button. | Decision 5 cuts each one before building rather than after. Task 9 asserts no literal hex and no stray radius; STORY-020 lands the full drift guard and is explicitly allowed to fail this component. |
| **The empty state and the fault state collapse into one.** A failed read leaves `sessions == []` *and* `sessions_error != ""`, so both conditions are true at once. | Decision 4 fixes the branch order with the fault check outermost, and Task 9 asserts both constants are named in the source. The story calls this the exact conflation PRD-006's Risk caught for its register. |
| **Row-keyed UI state reattaches to the wrong chat.** `rx.foreach` keys by position and `_promote_session` reorders the list on every send. | `renaming_session_id` and `confirming_delete_id` are keyed on `session_id`, never on index — `register.py:279-286`'s reason, which bites harder here because this list actually reorders. |
| **The scope line lies.** `len(self.sessions)` can never exceed the limit, so "50 of 50" is indistinguishable from a user with exactly fifty. | `sessions_total` comes from `count_chat_sessions`, which ignores `CHAT_SESSION_LIMIT` by design (`database.py:1765-1767`). Task 10 seeds limit+2 rows and asserts the count exceeds the list. |
| **Scope creep into STORY-019.** The component needs to be seen to be judged, and seeing it means mounting it. | Task 11 mounts it temporarily and reverts before commit. No change to `chat_ui.py` or `shell.py` is committed by this story. |
| **The `CHAT_HISTORY_ENABLED` branch is read as violating "no caller branches on the flag."** | Decision 1 states the reading, confines the branch to one expression in one module, and names the alternative. If the reviewer disagrees, the fix is a one-line accessor and the finding goes in the report. |
| **A missing token or string tempts a literal.** | STORY-017 is `done` and owns both files. Task 9 asserts no literal hex and no literal `SESSION_RAIL_*` value. A genuine gap is recorded as a STORY-017 defect, not patched here. |
