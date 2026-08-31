---
story: STORY-009
prd: PRD-006
slug: admin-shell-and-gate
title: "admin_shell.py: token gate form, masthead, and the two-view switch"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-006-admin-console
created: 2026-08-31
---

# Plan: `admin_shell.py` — the gate, the masthead, and the switch between two peers

## Summary

Create `chat_ui/chat_ui/components/admin_shell.py`: the first *rendered* surface of the console, and the frame every later admin component hangs inside. It exports three things — `admin_gate()` (the full-page token form), `admin_masthead(active)` (wordmark, the two-view switch, sign out, hairline under) and `admin_page(content, active)` (the wrapper that renders one or the other off `AdminState.authenticated`). The closest existing pattern is `components/shell.py`'s `user_id_gate()` / `header()` pair, and this story follows its *structure* — a centred bordered form, a `rx.form` whose `on_submit` calls a zero-argument handler, a controlled `rx.input` bound to a state var, an underlined `rx.el.button` for the session-ending control — while replacing its palette decisions, because one of `shell.py`'s inks (`INK_UPSTREAM`, on the submit hover) is chat-only under PRD Section 6.1 and `tests/test_admin_palette.py` fails the build the moment an admin module names it. Three edits ride along: `theme.py` gains the new field's id in the two `GLOBAL_CSS` rules that colour a Radix text field's inner `<input>` (the only way to reach text the user types), `tests/test_contrast.py` gains the one new ink/ground pairing this story introduces (`PAPER` on `MUTE`, the submit button's hover), and a new `tests/test_admin_shell.py` proves the module builds, imports no chat component, and carries no literal hex or literal user-facing string. No `app/` change, no route registration (STORY-010), no data rendering (STORY-011/015).

## User Story

As a compliance admin
I want one console shell that asks for the token and then carries the masthead and the switch between the two views
So that both pages are gated the same way and reached the same way.

## Story Reference

- Story file: `.agents/stories/PRD-006-admin-console/STORY-009-admin-shell-and-gate.md`
- PRD: `.agents/PRDs/PRD-006-admin-console/PRD.md` — Section 4 (console shell & access), Section 6 (gate as state, files), Section 6.1 (layout, colour, type, copy, motion), Section 9, Section 12 Phase 2, Risks 1 and 6

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/chat_ui/components/admin_shell.py` (CREATE), `chat_ui/chat_ui/theme.py` (UPDATE — two `GLOBAL_CSS` selector lists), `tests/test_admin_shell.py` (CREATE), `tests/test_contrast.py` (UPDATE, append-only). No `app/` change, no `chat_ui.py` change, no new dependency. |
| Story | STORY-009 |
| PRD | PRD-006 |
| Epic Branch | `epic/PRD-006-admin-console` (commit directly on this branch) |

**Dependency check.** `depends_on: [STORY-003, STORY-007, STORY-008]` — all three `status: done` (`048a873`, `a650a97`, `cc857e7`). Everything this story consumes therefore already exists and was read before planning: `AdminState.authenticated` / `token_input` / `gate_error` / `set_token_input` / `authenticate` / `sign_out` (`chat_ui/chat_ui/admin_state.py:252-446`), the four register tokens `HOVER` / `ROW_H` / `STAMP_X` / `TEXT_MICRO` (`chat_ui/chat_ui/theme.py:28,85,83,75`), and the eleven masthead-and-gate constants in `chat_ui/chat_ui/admin_copy.py:56-84`. `blocks: [STORY-010, STORY-011, STORY-015]`, all still `todo`, so the names exported below are free and STORY-010 will import them rather than re-declare a route string. Working tree clean on `epic/PRD-006-admin-console` at `3c5252b`. Baseline captured before planning: `python -m pytest tests/test_admin_palette.py tests/test_contrast.py tests/test_chat_components_import.py tests/test_copy.py -q` → **57 passed in 3.68s**. Cleared to proceed.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `.agents/skills/frontend-design` | Read in full (`.agents/skills/frontend-design/SKILL.md`). Four rules bind here. **(1)** *"Spend your boldness in one place. Let the signature element be the one memorable thing, keep everything around it quiet and disciplined, and cut any decoration that does not serve the brief."* — the signature is STORY-011's stamp margin, so this shell is hairlines and alignment only: no fill, no shadow, no accent, no icon, one border-radius token already in the theme. **(2)** *"Structural devices… should encode something true about the content, not decorate it."* — the rule between **Register** and **Summary** is the switch's whole mechanism (they are two peers, not a hierarchy), and the hairline under the masthead is the boundary between chrome and record. Nothing else is drawn. **(3)** *"A control should say exactly what happens when it's used."* — the submit is `GATE_SUBMIT_LABEL` (*Open the console*), never *Submit*; sign out is `SIGN_OUT_LABEL` and its result is the gate, not a notice (`admin_copy.py:41-47`). **(4)** *"Build to a quality floor without announcing it: responsive down to mobile, visible keyboard focus, reduced motion respected."* — AC 8 is exactly this, and it is Task 5's job here rather than STORY-019's clean-up. | Tasks 1–5 |
| `reflex-docs` (**NOT INSTALLED** — substituted, see below) | `chat_ui/AGENTS.md` mandates it for any Reflex API, and this is the first admin story that is *entirely* Reflex API: `rx.cond`, `rx.form` + `on_submit`, a controlled `rx.input`, `rx.link`'s internal navigation, `rx.el.button`, `rx.el.style`. | Tasks 1, 2, 4 |
| `reflex-process-management` (**NOT INSTALLED**) | Mandated for any compile/run/reload cycle. This story registers no page, so nothing here starts a dev server; the module is exercised by a subprocess import probe (Task 4), which is how `tests/test_chat_components_import.py` already validates `shell.py`. STORY-010 is the story that first compiles these pages, and its notes already carry the skill. | none |

### Skill availability and the substitution

`reflex-docs` and `reflex-process-management` ship in the `reflex-dev/agent-skills` Claude Code *plugin*, which is not installed in this environment — `~/.claude/plugins` is absent and `.agents/skills/` holds only `frontend-design` (confirmed against `skills-lock.json`). This is the same gap STORY-001 … STORY-008 each recorded; it is a tooling gap, not a decision to work from memory. `chat_ui/AGENTS.md`'s rule is *"rather than relying on memory"*, so every Reflex API below was verified against **both** the pinned package (`reflex==0.9.6.post1`, confirmed via `importlib.metadata`) and current Reflex documentation (context7 `/websites/reflex_dev`) before being written into a task. What was verified for **this** story:

1. **`rx.form(on_submit=...)` accepts a zero-argument handler.** `reflex_components_core/el/elements/forms.py:289-313` — `on_submit` is an `EventHandler` over `on_submit_event | on_submit_mapping_event | on_submit_string_event`; the TypedDict field validation at `:405-480` only runs when the handler is *annotated* with a TypedDict. `AdminState.authenticate(self)` takes no `form_data`, exactly as `ChatState.submit_user_id(self)` does at `chat_ui/chat_ui/state.py:51`, which `shell.py:268` already wires this way and which ships today. **Do not** add a `form_data` parameter and **do not** set `reset_on_submit`: the field is controlled by `value=AdminState.token_input`, and `AdminState._refuse()` (`admin_state.py:378-390`) already clears `token_input` on every refusal — which is what AC 3's "the token field is not repopulated" actually rests on.
2. **`rx.cond(condition, if_true, if_false)`** — both branches are compiled into the page; the condition selects at render (`reflex.dev/docs/library/dynamic-rendering/cond`). That property matters for Risk 1 and is written up under Risks below.
3. **`rx.link(href=...)` navigates client-side but injects an accent colour unless `_hover` is passed.** `reflex_components_radix/themes/typography/link.py:86` runs `props.setdefault("_hover", {"color": color("accent", 8)})` *before* anything else, and `:99-116` wraps the child in a `ReactRouterLink` with `as_child=True` — the source comment reads *"If user does not use `as_child`, by default we render using react_router_link to avoid page refresh during internal navigation"*. So `rx.link` is the right component for the two-view switch (a full reload is survivable — the Reflex client token lives in `sessionStorage`, `reflex_base/.templates/web/utils/state.js:86-91` — but it is a needless rehydration on every switch), **and every `rx.link` in this module must pass an explicit `_hover`**, or Radix's accent lands in the masthead and Risk 6's drift arrives through the front door. Pass `underline="none"` and an explicit `color` for the same reason.
4. **`rx.input` is Radix's TextField, and inline props do not reach the inner `<input>`.** Already discovered and documented in this repo at `theme.py:143-153`. That is why the chat's field is coloured by the `#chat_input, #user_id_input` id selectors in `GLOBAL_CSS`, and why Task 2 adds the admin field's id to those same two rules rather than setting `color=` on the component.
5. **`rx.el.button` / `rx.el.style`** — plain HTML elements, already used at `shell.py:87,250` and `chat_ui.py:29`. `type="button"` on the sign-out control is required: an unqualified `<button>` defaults to `submit`, and while sign out sits outside the gate's form, that default is the wrong one to inherit.

---

## Patterns to Follow

### A full-page gate: centred, bordered, one column, controlled field

```python
# SOURCE: chat_ui/chat_ui/components/shell.py:193-281
def user_id_gate() -> rx.Component:
    """Full-page form collecting the session's user_id before the chat opens."""
    return rx.center(
        rx.box(
            rx.box(copy.SHELL_HEADER_TITLE, font_family=theme.FONT_DISPLAY, ...),
            rx.form(
                rx.input(
                    id="user_id_input",
                    class_name="hx-field-boxed",
                    value=ChatState.user_id_input,
                    on_change=ChatState.set_user_id_input,
                    placeholder=copy.USER_ID_PLACEHOLDER,
                    auto_focus=True,
                    custom_attrs={"autoComplete": "off", "autoCorrect": "off"},
                    width="100%", font_family=theme.FONT_DATA,
                    font_size=theme.TEXT_BODY, height="2.5rem",
                    border_radius=theme.RADIUS, margin_top="1.5rem",
                ),
                rx.cond(
                    ChatState.user_id_error != "",
                    rx.box(ChatState.user_id_error, color=theme.INK_DENIED, ...),
                    rx.fragment(),
                ),
                rx.box(rx.el.button(copy.USER_ID_SUBMIT_LABEL, type="submit", ...)),
                on_submit=ChatState.submit_user_id,
                width="100%",
            ),
            width="100%", max_width="24rem", padding="2.25rem",
            background_color=theme.CARD, border=f"1px solid {theme.RULE}",
            border_radius=theme.RADIUS,
        ),
        height="100vh", width="100%", padding="1.5rem",
    )
```

Copy the skeleton verbatim in shape. Change exactly three things: the state (`AdminState`), the strings (`admin_copy`), and the submit button's `_hover` — `shell.py:263` hovers to `theme.INK_UPSTREAM`, which is chat-only and would fail `tests/test_admin_palette.py::test_no_admin_module_references_a_chat_only_ink`.

### A masthead: wordmark left, session controls right, hairline under, rule between peers

```python
# SOURCE: chat_ui/chat_ui/components/shell.py:48-121
def header() -> rx.Component:
    return rx.hstack(
        rx.hstack(  # left cluster: wordmark, then a rule-separated second fact
            rx.box(copy.SHELL_HEADER_TITLE, font_family=theme.FONT_DISPLAY,
                   font_size="1.0625rem", font_weight="700",
                   letter_spacing="0.16em", color=theme.INK),
            rx.hstack(
                ...,
                padding_left="0.875rem", margin_left="0.875rem",
                border_left=f"1px solid {theme.RULE}",   # <- the rule, as a border
            ),
            align="center", spacing="0",
        ),
        rx.hstack(..., class_name="hx-header-meta", align="center", spacing="3"),
        justify="between", align="center", width="100%",
        flex_wrap="wrap", row_gap="0.75rem",           # <- the narrow-viewport answer
        padding="0.9rem 1.5rem",
        border_bottom=f"1px solid {theme.RULE}",       # <- the hairline under
        background_color=theme.CARD, flex_shrink="0",
    )
```

The rule between the two switch destinations is `border_left`, not a `"|"` character and not an `rx.divider()` — the repo already states a rule this way twice (`shell.py:71,106`), and a literal pipe would be a user-facing string with no home in `admin_copy`.

### A session-ending text control

```python
# SOURCE: chat_ui/chat_ui/components/shell.py:87-101
rx.el.button(
    copy.SHELL_CHANGE_USER_LABEL,
    on_click=ChatState.reset_user_id,
    type="button",
    cursor="pointer",
    background="none", border="none", padding="0",
    font_family=theme.FONT_DISPLAY, font_size=theme.TEXT_DATA,
    color=theme.MUTE,
    text_decoration="underline", text_underline_offset="3px",
    _hover={"color": theme.INK},
)
```

### Absolute imports, because Reflex imports the app as `chat_ui.components.*`

```python
# SOURCE: chat_ui/chat_ui/components/shell.py:10-14
import reflex as rx

from chat_ui import copy, theme
from chat_ui.config import MODEL_ALLOWLIST
from chat_ui.state import ChatState
```

Components under `components/` use *absolute* imports, not relative ones, because Reflex puts `chat_ui/` on `PYTHONPATH` and imports `chat_ui.components.shell` (`tests/test_chat_components_import.py:9-13`). So: `from chat_ui import admin_copy, theme` and `from chat_ui.admin_state import AdminState`. Never `from chat_ui.chat_ui import ...`, and never a relative `from ..admin_state import ...` — `admin_state.py` uses relative imports because it is reached by *both* path shapes; a component is reached by one.

### The palette guard this module must pass

```python
# SOURCE: tests/test_admin_palette.py:41-48 — the glob already covers this file
# "Globbed, never hard-coded: STORY-009/011/015 add admin modules and the guard
#  has to cover them the day they land, without anyone remembering this file."
ADMIN_MODULE_PATTERNS = (
    "chat_ui/chat_ui/admin_*.py",
    "chat_ui/chat_ui/components/admin_*.py",   # <- admin_shell.py, from the day it lands
    "chat_ui/chat_ui/components/register.py",
    "chat_ui/chat_ui/components/summary.py",
)
```

`admin_shell.py` must contain neither the substring `INK_UPSTREAM` nor `INK_SELF` nor `TINT_`. It may reference `theme.GLOBAL_CSS`, whose focus ring resolves to `INK_UPSTREAM` — that exception is already written down at `tests/test_admin_palette.py:15-21`.

### Test file shape

```python
# SOURCE: tests/test_chat_components_import.py:24-25,106-123
REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTHONPATH = [str(REPO_ROOT / "chat_ui"), str(REPO_ROOT)]

proc = subprocess.run(
    [sys.executable, "-c", _CHECK_SCRIPT, ...],
    cwd=str(REPO_ROOT / "chat_ui"),
    env={**os.environ, "PYTHONPATH": os.pathsep.join(_PYTHONPATH)},
    capture_output=True, text=True,
)
```

```python
# SOURCE: tests/test_contrast.py:86-101 — append a row, do not restructure
@pytest.mark.parametrize(("name", "fg", "bg"), [
    ("body ink on paper", theme.INK, theme.PAPER),
    ("body ink on card", theme.INK, theme.CARD),
    ("muted text on paper", theme.MUTE, theme.PAPER),
    ("muted text on card", theme.MUTE, theme.CARD),
    ("inverted button label", theme.PAPER, theme.INK),
    ("body ink on row hover", theme.INK, theme.HOVER),
    ("muted text on row hover", theme.MUTE, theme.HOVER),
])
def test_neutral_pairs_are_readable(name, fg, bg): ...
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/components/admin_shell.py` | CREATE | `admin_gate()`, `admin_masthead()`, `admin_page()`, plus the two route constants and the two view keys STORY-010 will import |
| `chat_ui/chat_ui/theme.py` | UPDATE | Add `#admin_token_input` to the two `GLOBAL_CSS` rules at `:146-153` that colour a Radix text field's inner `<input>` and its placeholder |
| `tests/test_admin_shell.py` | CREATE | Builds every exported factory in a subprocess; asserts no chat import, no literal hex, no literal user-facing string, both `authenticated` branches present |
| `tests/test_contrast.py` | UPDATE (append-only) | One new pairing: `PAPER` on `MUTE`, the gate submit's hover ground |

Nothing under `app/`. `chat_ui/chat_ui/chat_ui.py` is **not** touched — route registration is STORY-010, and touching it here would make this story's diff overlap the next one's.

---

## Design decisions (settled before code, per the skill's two-pass rule)

The brief pins colour and type (both inherited from `theme.py`) and pins layout (Section 6.1's wireframe), so the skill's *"where the brief pins down a visual direction, follow it exactly"* governs most of this file. The freedom left is small and is spent as follows; each is a decision, not a default.

**The masthead title is composed, not stored.** `admin_copy` gives `CONSOLE_TITLE` (`"HARNESS"`), `MASTHEAD_SEPARATOR` (`" · "`) and `CONSOLE_VIEW_REGISTER` / `CONSOLE_VIEW_SUMMARY`. `admin_masthead(active)` joins them in plain Python, because `active` is a plain `str` argument, not a Var — so there is no Var arithmetic and no `rx.cond` around the wordmark. This is the same reasoning PRD Section 6 gives for putting verdict derivation in Python: *"component functions receive Reflex Vars, not values."*

**The active view is a parameter, not `router.page.path`.** `admin_page(content, active)` takes the view key from the page that calls it. Reading the route out of the router would make the masthead's correctness depend on a string matching a route registered in a different module (STORY-010) — a coupling with no test between the two halves. A parameter is checkable at the call site, and it is what lets Task 4 build both mastheads without a running server.

**The two-view switch is two destinations, and the current one is not a link to itself.** The active destination renders as an `rx.box` in `INK` at `font_weight="600"`; the inactive one is an `rx.link` in `MUTE` hovering to `INK`. A link to the page you are already on is a control that does nothing, and the skill's *"let each element do exactly one job"* is the reason not to draw one. This also gives the switch its state indication for free — no underline bar, no pill, no fill.

**The gate's panel keeps `CARD` ground and a `RULE` hairline.** This is a panel, not a card in the sense Risk 6 forbids: Risk 6 names *"a row of four KPI cards with big numbers over a striped data table"*, and Section 6.1's refusal is scoped to the register and the summary sheet. `rx.card` — the Radix component the story's Technical Notes call out by name — is used nowhere; the panel is an `rx.box` with `border` and `background_color`, exactly as `shell.py:274-276` builds the chat's gate. The console's two gates resembling each other is the skill's consistency rule, not drift.

**The submit hover moves `INK` → `MUTE`.** `shell.py:263` hovers to `INK_UPSTREAM`, which this module may not name. `MUTE` is a ground token, it is the only other dark neutral in the theme, and `PAPER` on `MUTE` measures **4.63:1** — clearing WCAG AA for normal text with the margin stated rather than assumed. That measurement is why Task 3 exists as its own task rather than a footnote.

**The token field is `type="password"`.** Not specified by the PRD either way. It is a shared secret typed on a screen an admin may not be alone in front of, and PRD Section 9's whole posture is that the token does not linger anywhere. Masking costs nothing, and `admin_copy.GATE_PLACEHOLDER` still names the field.

**No motion.** Section 6.1: *"Motion. Effectively none, and deliberately."* The gate does not fade in, the switch does not slide, and this module defines no `animation` and applies neither `hx-entry` nor `hx-pulse`. The one `transition` carried over from `shell.py:264` (`background-color 120ms ease` on the submit) is kept — it is a hover affordance on a control the pointer is already on, not an entrance — and `GLOBAL_CSS`'s `prefers-reduced-motion` block flattens all transitions to `0.01ms` (`theme.py:138-141`).

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Create `admin_shell.py` — module constants, the gate, the masthead, the wrapper

- **File**: `chat_ui/chat_ui/components/admin_shell.py`
- **Action**: CREATE
- **Mirror**: `chat_ui/chat_ui/components/shell.py:1-14` (docstring + import block), `:48-121` (`header`), `:193-281` (`user_id_gate`)
- **Implement**:

  **1.1 Module docstring** stating the three structural facts a later edit could quietly remove: (a) this module imports nothing from `chat.py` or `bubbles.py` and renders no chat component — PRD Section 4's cross-surface separation, asserted in Task 4; (b) the gate is a *render condition*, per PRD Section 6, and it is the **second** of two guards — `AdminState.load()` returns before touching anything unless `authenticated` (`admin_state.py:446-460`), which is the guard that means an unauthenticated page has no data in state to leak; (c) `INK_UPSTREAM` and `INK_SELF` are chat-only, so the submit hover is `MUTE` rather than the blue `shell.py` uses.

  **1.2 Imports**, absolute, in `shell.py`'s order and nothing else:
  ```python
  import reflex as rx

  from chat_ui import admin_copy, theme
  from chat_ui.admin_state import AdminState
  ```

  **1.3 Route and view constants** — values, not copy, so they live here and not in `admin_copy` (that module's docstring draws exactly this line for `VERDICT_*`: *"Copy is not values"*):
  ```python
  ROUTE_REGISTER = "/admin/audit"
  ROUTE_SUMMARY = "/admin/stats"

  VIEW_REGISTER = "register"
  VIEW_SUMMARY = "summary"
  ```
  Comment them as the single declaration STORY-010 imports, so the route string is typed once in the codebase.

  **1.4 `_label(text)`** — private helper, `shell.py:17-26`'s shape but at `theme.TEXT_MICRO` rather than `TEXT_TAG`: PRD Section 6.1 makes `FONT_DATA` the console's dominant face and `TEXT_MICRO` is the console's signpost step (STORY-007). Uppercase, `letter_spacing="0.08em"`, `color=theme.MUTE`. Only add it if the file actually needs a second eyebrow; if the masthead ends up with one label, inline it and cut the helper (Chanel's mirror applies to code too).

  **1.5 `admin_gate() -> rx.Component`** — `rx.center` wrapping an `rx.box` panel (`width="100%"`, `max_width="24rem"`, `padding="2.25rem"`, `background_color=theme.CARD`, `border=f"1px solid {theme.RULE}"`, `border_radius=theme.RADIUS`), containing in order:
  - the wordmark: `admin_copy.CONSOLE_TITLE`, `FONT_DISPLAY`, `font_size="1.0625rem"`, `font_weight="700"`, `letter_spacing="0.16em"`, `color=theme.INK`
  - `admin_copy.GATE_TITLE` in `FONT_DISPLAY` at `1.5rem` / `600` / `letter_spacing="-0.02em"`, `margin_top="1.75rem"`
  - `admin_copy.GATE_BODY` in `FONT_BODY` at `theme.TEXT_BODY`, `line_height="1.6"`, `color=theme.MUTE`
  - `rx.form(...)` with `on_submit=AdminState.authenticate`, `width="100%"`, containing:
    - `rx.input(id="admin_token_input", class_name="hx-field-boxed", type="password", value=AdminState.token_input, on_change=AdminState.set_token_input, placeholder=admin_copy.GATE_PLACEHOLDER, auto_focus=True, custom_attrs={"autoComplete": "off", "autoCorrect": "off"}, ...)` — sizes lifted from `shell.py:231-236`
    - `rx.cond(AdminState.gate_error != "", rx.box(AdminState.gate_error, font_family=theme.FONT_DATA, font_size=theme.TEXT_DATA, color=theme.INK_DENIED, margin_top="0.5rem"), rx.fragment())`
    - the submit, wrapped in an `rx.box(margin_top="1rem")` as `shell.py:249-267` does: `rx.el.button(admin_copy.GATE_SUBMIT_LABEL, type="submit", cursor="pointer", width="100%", height="2.5rem", font_family=theme.FONT_DISPLAY, font_size=theme.TEXT_BODY, font_weight="600", color=theme.PAPER, background_color=theme.INK, border="none", border_radius=theme.RADIUS, _hover={"background_color": theme.MUTE}, transition="background-color 120ms ease")`

  No `reset_on_submit`. No `form_data` parameter on `authenticate`. `AdminState.set_token_input` is a declared `@rx.event` (`admin_state.py:341-343`) — use it, not an auto-generated setter.

  **1.6 `admin_masthead(active: str) -> rx.Component`** — `rx.hstack(..., justify="between", align="center", width="100%", flex_wrap="wrap", row_gap="0.75rem", padding="0.9rem 1.5rem", border_bottom=f"1px solid {theme.RULE}", background_color=theme.CARD, flex_shrink="0")`:
  - **left**: the composed title — `admin_copy.CONSOLE_TITLE + admin_copy.MASTHEAD_SEPARATOR + (admin_copy.CONSOLE_VIEW_REGISTER if active == VIEW_REGISTER else admin_copy.CONSOLE_VIEW_SUMMARY)` — in `FONT_DISPLAY` / `font_size="1.0625rem"` / `700` / `letter_spacing="0.16em"` / `color=theme.INK`.
  - **right**: an `rx.hstack` carrying `class_name="hx-header-meta"` (so `theme.py:198-200`'s `max-width: 40rem` rule already handles the narrow viewport with no new CSS), `align="center"`, `spacing="3"`, holding
    - the switch: an `rx.hstack(spacing="0")` of `_view_link(VIEW_REGISTER, admin_copy.VIEW_REGISTER_LABEL, ROUTE_REGISTER, active)` then `_view_link(VIEW_SUMMARY, admin_copy.VIEW_SUMMARY_LABEL, ROUTE_SUMMARY, active)`, the second wrapped with `padding_left="0.75rem"`, `margin_left="0.75rem"`, `border_left=f"1px solid {theme.RULE}"` — this border **is** the rule AC 4 requires between the two peers
    - the sign-out control in an `rx.box` with `padding_left="1rem"`, `margin_left="0.25rem"`, `border_left=f"1px solid {theme.RULE}"` — `shell.py:102-107`'s idiom
  - **`_view_link(view, label, href, active)`**: when `view == active`, `rx.box(label, font_family=theme.FONT_DISPLAY, font_size=theme.TEXT_DATA, font_weight="600", color=theme.INK, custom_attrs={"aria-current": "page"})`; otherwise `rx.link(label, href=href, underline="none", color=theme.MUTE, _hover={"color": theme.INK}, font_family=theme.FONT_DISPLAY, font_size=theme.TEXT_DATA, font_weight="500")`. **The explicit `_hover` is mandatory** — without it `rx.link` injects Radix's accent (`reflex_components_radix/themes/typography/link.py:86`); see Risk 1.
  - **sign out**: `rx.el.button(admin_copy.SIGN_OUT_LABEL, on_click=AdminState.sign_out, type="button", ...)` — `shell.py:87-101` verbatim in shape.

  **1.7 `admin_page(content: rx.Component, active: str) -> rx.Component`** — the wrapper:
  ```python
  return rx.fragment(
      rx.el.style(theme.GLOBAL_CSS),
      rx.cond(
          AdminState.authenticated,
          rx.vstack(
              admin_masthead(active),
              content,
              height="100vh", width="100%", spacing="0",
              background_color=theme.PAPER,
          ),
          admin_gate(),
      ),
  )
  ```
  `rx.el.style(theme.GLOBAL_CSS)` is what carries `:focus-visible`, the scrollbar rail and the reduced-motion block onto an admin page; `chat_ui.py:29` does the same for the chat and the admin pages are not otherwise reached by it. Docstring the `rx.cond` as PRD Section 6's *"the guard is the render condition"* **and** name the second guard (`load()`'s own check), so no later reader concludes the render condition stands alone.

- **Validate**: `python -m pytest tests/test_admin_palette.py -q` — the glob at `tests/test_admin_palette.py:45` now matches this file, and the three chat-only/tint assertions must pass on it with **no edit to that test**.

### Task 2: Reach the Radix field's inner `<input>` from `theme.py`

- **File**: `chat_ui/chat_ui/theme.py`
- **Action**: UPDATE
- **Implement**: In `GLOBAL_CSS`, add `#admin_token_input` to the two selector lists at `:146` and `:150`, so they read `#chat_input, #user_id_input, #admin_token_input` and `#chat_input::placeholder, #user_id_input::placeholder, #admin_token_input::placeholder`. Extend the existing comment at `:143-145` with one clause naming the admin gate, so the reason — *"Radix paints the real `<input>` inside its TextField wrapper, so inline props on the wrapper never reach the text the user types"* — still accounts for all three ids.
- **Mirror**: `chat_ui/chat_ui/theme.py:143-153` — the rule already exists; this adds a selector to it and nothing else.
- **Do not**: add a new token, change a value, or touch `.hx-field-boxed` (`:174-180`), which is id-agnostic and already gives the gate's field its frame and its focused inset border.
- **Validate**: `python -m pytest tests/test_contrast.py tests/test_admin_palette.py -q` (no token changed, so both stay green) and `python -c "from chat_ui.chat_ui import theme; assert theme.GLOBAL_CSS.count('#admin_token_input') == 2"`.

### Task 3: Assert the one new ink/ground pairing

- **File**: `tests/test_contrast.py`
- **Action**: UPDATE (append-only)
- **Implement**: Add one row to `test_neutral_pairs_are_readable`'s parametrize list at `:88-95`: `("inverted button label on hover", theme.PAPER, theme.MUTE)`. Measured at **4.63:1**, clearing `AA_NORMAL`. PRD Section 4 requires that *"any new ink/ground pairing clears WCAG AA and is asserted in `tests/test_contrast.py`"*; this story introduces exactly one, and this is it.
- **Mirror**: `tests/test_contrast.py:86-101`
- **Do not** restructure the module or touch the verdict-ink parametrizations; the existing `("inverted button label", theme.PAPER, theme.INK)` row (15.45:1) stays as it is.
- **Validate**: `python -m pytest tests/test_contrast.py -q` — one more test than the baseline, all passing.

### Task 4: `tests/test_admin_shell.py` — it builds, it imports no chat, it holds no literals

- **File**: `tests/test_admin_shell.py`
- **Action**: CREATE
- **Implement**: Two halves.

  **(a) A subprocess build probe**, modelled on `tests/test_chat_components_import.py:106-123` — same `cwd=chat_ui/`, same `PYTHONPATH=[chat_ui/, repo root]`, plus `ADMIN_TOKEN` and `OPENROUTER_API_KEY` in `env` (`admin_shell` imports `admin_state`, which imports `app.config.settings`, where `ADMIN_TOKEN` is a required field — `app/config.py:8`; `tests/test_admin_state.py:43-44` sets both the same way). The probe script asserts:
  - `from chat_ui.components.admin_shell import ROUTE_REGISTER, ROUTE_SUMMARY, VIEW_REGISTER, VIEW_SUMMARY, admin_gate, admin_masthead, admin_page` succeeds
  - `admin_gate()` is an `rx.Component`
  - `admin_masthead(VIEW_REGISTER)` and `admin_masthead(VIEW_SUMMARY)` are each an `rx.Component` — **both** mastheads, so a broken active-view branch fails a test rather than a page
  - `admin_page(rx.box("x"), VIEW_REGISTER)` is an `rx.Component`
  - after the import, `sys.modules` contains neither `chat_ui.components.chat` nor `chat_ui.components.bubbles` — AC 6, and stronger than a source grep because it catches a transitive import too
  - the rendered string of `admin_page(rx.box("x"), VIEW_REGISTER)` contains `admin_copy.GATE_SUBMIT_LABEL` **and** `admin_copy.SIGN_OUT_LABEL`, proving both `rx.cond` branches compiled into the one page — AC 1 and AC 2
  - `ROUTE_REGISTER == "/admin/audit"` and `ROUTE_SUMMARY == "/admin/stats"`, and neither starts with a route reserved by `app/routers/admin.py` (`/audit`, `/stats`) — the constant STORY-010 will import, pinned where it is declared

  **(b) Source assertions**, reading the file as text with no import (the shape `tests/test_admin_palette.py:51-55` uses):
  - **no literal hex**: `re.search(r"#[0-9a-fA-F]{6}\b", source)` finds nothing — AC 7's "no literal hex". If a future `#RRGGBB`-shaped string is ever legitimate in this module, this test is the place that has to be argued with.
  - **every user-facing string comes from `admin_copy`**: for each of `CONSOLE_TITLE`, `MASTHEAD_SEPARATOR`, `CONSOLE_VIEW_REGISTER`, `CONSOLE_VIEW_SUMMARY`, `VIEW_REGISTER_LABEL`, `VIEW_SUMMARY_LABEL`, `SIGN_OUT_LABEL`, `GATE_TITLE`, `GATE_BODY`, `GATE_PLACEHOLDER`, `GATE_SUBMIT_LABEL` — assert the name appears in the source as an `admin_copy.` attribute reference, and that the constant's *value* does not appear as a quoted literal. That is AC 7's "no literal text", made checkable rather than reviewed.
  - **no chat import**: neither `chat` nor `bubbles` appears in any `import` line — AC 6 at source level, complementing the `sys.modules` check.

  Put in the module docstring that STORY-010 should extend **this** file with its route-registration probe rather than `tests/test_chat_components_import.py`, which is the chat's smoke test and should stay that.

- **Mirror**: `tests/test_chat_components_import.py` (whole file), `tests/test_admin_palette.py:24-55`
- **Validate**: `python -m pytest tests/test_admin_shell.py -q`

### Task 5: The quality floor, checked rather than assumed

- **File**: none — a verification pass over Task 1's output, with fixes applied in place
- **Action**: VERIFY
- **Implement**: Re-read `admin_shell.py` against AC 8 and the skill's quality floor:
  - **Focus visible on all four**: each interactive element is a real focusable element — `<input>`, `<button type="submit">`, `<a href>`, `<button type="button">`. `GLOBAL_CSS`'s `:focus-visible` (`theme.py:106-112`) then applies to all four, and `.hx-field-boxed:focus-within` (`:178-180`) adds the field's inset border on top. Nothing in this module may set `outline: none` or `box-shadow: none` on a focusable element. Confirm the wrapper actually emits `rx.el.style(theme.GLOBAL_CSS)` — without it none of this reaches an admin page.
  - **Tab order**: DOM order is wordmark → Register → Summary → Sign out in the masthead, and field → submit in the gate. No `tab_index` anywhere.
  - **Narrow viewport**: the masthead's `flex_wrap="wrap"` + `row_gap` plus the `hx-header-meta` class are the whole answer; the gate is already a `max_width="24rem"` box inside `rx.center` with `padding="1.5rem"`.
  - **Reduced motion**: the only `transition` is the submit's `background-color 120ms ease`, flattened by `theme.py:138-141`. No `animation`, no `hx-entry`, no `hx-pulse` in this module.
  - **Chanel's mirror** (*"before leaving the house… remove one accessory"*): confirm the shell draws exactly four lines — the rule between Register and Summary, the rule before Sign out, the hairline under the masthead, and the gate panel's border. If a fifth appeared, cut it. Same for the `_label` helper from 1.4 if it ended up unused.
- **Validate**: `python -m pytest tests/ -q` — the full suite, at the baseline count plus this story's new tests, with nothing previously green now red.

---

## End-to-End Tests

The pages do not exist until STORY-010, so this story's end-to-end checks sit at the component/compile layer. `/implement` executes these:

- [ ] `python -m pytest tests/test_admin_shell.py -q` → all pass; the probe reports no import error
- [ ] `python -m pytest tests/test_admin_palette.py -q` → passes **unmodified**, now with `admin_shell.py` inside its glob (`test_admin_modules_are_discoverable` proves the glob is non-empty)
- [ ] `python -m pytest tests/test_contrast.py -q` → baseline + 1, all passing
- [ ] `python -m pytest tests/test_chat_components_import.py tests/test_chat_state.py -q` → passes unmodified; the chat surface is untouched
- [ ] `python -m pytest tests/ -q` → full suite green
- [ ] Build both mastheads and confirm the composed title differs: `admin_masthead(VIEW_REGISTER)` renders `HARNESS · REGISTER`, `admin_masthead(VIEW_SUMMARY)` renders `HARNESS · SUMMARY`
- [ ] Render `admin_page(rx.box("seeded"), VIEW_SUMMARY)` with `AdminState` at its defaults and confirm the gate's submit label is present — the unauthenticated default is the gate, on the summary page as much as the register (AC 2)
- [ ] `git diff main --stat -- app/` → **empty**; PRD Section 4 puts `app/` out of scope for the whole PRD
- [ ] `git diff --stat` → exactly four paths: the new component, `theme.py`, the new test, `test_contrast.py`

## Validation

```bash
python -m pytest tests/test_admin_shell.py tests/test_admin_palette.py tests/test_contrast.py -q
python -m pytest tests/ -q
git diff main --stat -- app/          # must print nothing
git diff --stat                        # must list exactly the four planned paths
```

---

## Risks + Mitigations

**1. `rx.link` injects Radix's accent colour when `_hover` is omitted.** `reflex_components_radix/themes/typography/link.py:86` runs `props.setdefault("_hover", {"color": color("accent", 8)})` before any other prop handling, so a switch link written the obvious way puts an accent in the masthead — precisely PRD Risk 6's *"the drift arrives one reasonable-looking component at a time, usually as a Radix card imported for convenience."* It would also pass `tests/test_admin_palette.py`, which greps admin module *source* and cannot see a colour Radix supplies at compile time. *Mitigation*: every `rx.link` in this module passes an explicit `_hover` (Task 1.6), and Task 5 re-checks it. STORY-018's render-invariant test is where this becomes machine-checkable against the rendered output — flag it in this story's report so STORY-018 is written knowing to look.

**2. The render condition is not the only guard, and treating it as one would be wrong.** `rx.cond` compiles both branches, and Reflex ships state deltas to the client independently of what is drawn — so a populated `AdminState.rows` would reach an unauthenticated browser even while the gate is what renders. *Mitigation*: it cannot be populated. `load()` returns before setting anything unless `authenticated` (`admin_state.py:446-460`), which is PRD Risk 1's own stated mitigation — *"the read itself is gated, not just the view, so an unauthenticated page has no data in state to leak regardless of what renders."* This story adds the second guard, not the first, and the module docstring must say so (Task 1.1) so nobody later relaxes `load()`'s check on the grounds that the view already guards it.

**3. Copying `shell.py` copies `INK_UPSTREAM`.** The nearest pattern for the submit button hovers to a chat-only ink (`shell.py:263`), and copy-paste is the expected failure mode. *Mitigation*: `tests/test_admin_palette.py::test_no_admin_module_references_a_chat_only_ink` fails on it the moment the file lands, which is why Task 1's validation runs that test first, before anything else is written.

**4. Radix's TextField swallows inline colour props.** Setting `color=theme.INK` on `rx.input` colours the wrapper, not the text typed into it — the defect `theme.py:143-145` already records for the chat. Without Task 2 the admin token renders in Radix's own gray on a white field. *Mitigation*: Task 2, plus a Task 5 check that both `.hx-field-boxed` and the id reach the field.

**5. `admin_shell.py` and STORY-010's page functions both wanting `rx.el.style(theme.GLOBAL_CSS)`.** If the page function also injects it, the tag renders twice — harmless (identical CSS, idempotent) but sloppy. *Mitigation*: the wrapper owns it, and this plan says so, so STORY-010 does not add a second one. Record it in the report.

**6. Two stories writing `"/admin/audit"`.** STORY-010 registers the routes; if it types the strings again, a later change moves one and not the other. *Mitigation*: `ROUTE_REGISTER` / `ROUTE_SUMMARY` are declared here (Task 1.3), pinned by Task 4's probe, and STORY-010 imports them.

**7. `type="password"` and a browser password manager.** A masked field invites a "save password?" prompt and an autofill on return. *Mitigation*: `custom_attrs={"autoComplete": "off", "autoCorrect": "off"}` is already in the mirrored pattern (`shell.py:230`) and carries over unchanged. This is a hint, not a guarantee — browsers may ignore it — which is worth one line in the report rather than a defence in code.

---

## Acceptance Criteria

(Copied from story `STORY-009`)

- [ ] Given `chat_ui/chat_ui/components/admin_shell.py`, when it is created, then it exports a gate component, a masthead component and a wrapper that renders the gate when `AdminState.authenticated` is False and its content when True.
- [ ] Given `/admin/stats` reached directly with no session, when it renders, then the gate is shown and no data appears — both pages assert the condition independently (Risk 1).
- [ ] Given a submitted wrong or empty token, when the gate re-renders, then it shows the one generic refusal message from `admin_copy` and the token field is not repopulated.
- [ ] Given the masthead, when it renders, then it carries the console title, the two-view switch (Register / Summary) separated by a rule, and the sign-out control — matching PRD Section 6.1's wireframe, with a hairline under it.
- [ ] Given the sign-out control, when it is activated, then the gate returns and the loaded rows are gone from state (STORY-003's `sign_out`).
- [ ] Given the shell, when it is inspected, then it renders no chat component and imports nothing from `chat_ui/components/chat.py` or `bubbles.py` — PRD Section 4's cross-surface separation.
- [ ] Given the shell, when its styling is read, then every colour and size resolves from `theme.py` and every string from `admin_copy` — no literal hex, no literal text.
- [ ] Given a keyboard user, when they tab to the token field, the submit, the view switch and sign out, then focus is visible on each.
- [ ] All tasks completed
- [ ] Full test suite passes (`python -m pytest tests/ -q`)
- [ ] `git diff main --stat -- app/` is empty
- [ ] Follows existing patterns (`shell.py` for structure, `admin_state.py` for the import shape, `test_chat_components_import.py` for the probe)
