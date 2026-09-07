"""Design tokens for the Harness AI chat surface.

Direction: *inspection ledger*. The chat is not a messaging app, it is a
running record of traffic that passed through a checkpoint. Every entry is a
full-width row clamped to a vertical rail; the rail glyph and the verdict tag
carry the outcome. Nothing alternates left and right, nothing floats in a
bubble.

Every colour and size used anywhere in the UI is defined here, so a change of
visual direction is a single-file edit — the same guarantee copy.py gives for
wording.

**Two grounds, one design.** The ledger now renders on paper or on slate, and
the switch is a CSS custom property swap rather than a second set of
components. `LIGHT` and `DARK` below hold the two palettes as hex; every colour
token in this module is the *reference* `var(--hx-…)`, which is what the
components consume. Nothing downstream of this file knows which ground it is
drawing on, so the single-file guarantee above survives the second palette
intact — `components/` holds no hex and no colour-mode branch.

The indirection is the point. Reflex stamps `class="light"` / `class="dark"` on
the document element, and does it in a blocking pre-paint script, so the swap is
one attribute, repaints without re-rendering a single component, and never puts
a colour in the state graph. The alternative — `rx.color_mode_cond` per token —
would have branched at ~250 call sites and made every ground a state read.

**The palettes are held to the same floor.** `tests/test_contrast.py`
parametrizes its whole matrix over both dicts, so the dark ground clears WCAG AA
on exactly the pairings the light one does. The dark palette's tightest pairing
is `MUTE` on `HOVER` at 6.15:1; the light one's is `MUTE` on `PAPER` at 4.63:1.
"""

# --- The two grounds -----------------------------------------------------
# LIGHT is the original palette, unchanged in value: a cool blue-grey paper
# rather than warm cream, because this is an institutional record and not a
# magazine. DARK is its slate counterpart, and it is not an inversion — an
# inverted #ECEFF1 would be a black that vibrates under the verdict inks. It is
# a cool near-black ground with the inks re-pitched *lighter* rather than
# darker, which is the direction that keeps a pigment reading as the same
# pigment when the ground flips.
#
# The keys are the contract. Both dicts carry the same names, the module-level
# tokens below are written against those names, and `tests/test_contrast.py`
# iterates them — so a colour added to one palette and forgotten in the other is
# a test failure rather than an unstyled element.

LIGHT: dict[str, str] = {
    # Ground.
    "PAPER": "#ECEFF1",
    "CARD": "#FFFFFF",
    "INK": "#14181C",
    "MUTE": "#626C77",
    "RULE": "#CBD2D9",
    "RULE_SOFT": "#DDE2E7",
    # The register's row hover. A hover has to be findable without becoming a
    # second signal — the stamp margin is where that surface spends its
    # boldness — so it lifts toward the card rather than darkening toward the
    # rule. Darkening was measured and rejected: it drops MUTE below AA, and
    # MUTE sets the register's timestamps.
    "HOVER": "#F1F3F5",
    # The rail itself. It has to hold its own against the paper: it is the one
    # structural line the whole design rests on.
    "SPINE": "#C3CBD3",
    # Stamp inks. One pigment per pipeline outcome. This is a legend, not
    # decoration: PRD-004 requires that no two semantically different outcomes
    # share a treatment, so each ink maps to exactly one branch of
    # run_query(...).
    "INK_CLEAR": "#1B5E4B",  # assistant — cleared inspection
    "INK_HELD": "#7C5E11",  # duplicate — held, not rejected
    "INK_DENIED": "#9B2226",  # injection — denied and logged
    "INK_FORBIDDEN": "#B5541D",  # forbidden by policy -- distinct from INK_DENIED
    "INK_UPSTREAM": "#34567F",  # OpenRouter failed — an outside party
    "INK_FAULT": "#5D4A8C",  # the harness itself failed
    "INK_SELF": "#14181C",  # your own words — plain ink, no verdict
    # Tint used behind a stamped panel. Kept at a whisper so the rail, not the
    # fill, does the signalling.
    "TINT_CLEAR": "#F1F6F4",
    "TINT_HELD": "#FAF6EA",
    "TINT_DENIED": "#FBF1F1",
    "TINT_FORBIDDEN": "#FCF1E8",
    "TINT_UPSTREAM": "#F1F4F9",
    "TINT_FAULT": "#F5F3F9",
}

# Every ink above clears WCAG AA (4.5:1) for small text against both PAPER and
# its own tint; the ochre was darkened from #8A6A12, which sat at 4.38 on
# PAPER. tests/test_contrast.py holds the line — for this dict and the next.

DARK: dict[str, str] = {
    # Ground. The card *rises* out of the paper here rather than bleaching to
    # white: on a dark ground the raised surface is the lighter one, so the
    # header and the gate panel read as lifted by the same move that takes
    # PAPER to CARD on the light ground, in the opposite direction.
    "PAPER": "#12161A",
    "CARD": "#1A1F25",
    "INK": "#E4E9ED",
    "MUTE": "#9AA6B2",
    "RULE": "#2C333A",
    "RULE_SOFT": "#232930",
    # Same reasoning as the light hover, mirrored: it lifts *toward the card*,
    # which on this ground means lighter still. MUTE on it is 6.15:1 — the
    # tightest pairing in the dark palette, and the one that sets its floor.
    "HOVER": "#20262D",
    # The spine stays the one structural line, so it clears the rule here the
    # way #C3CBD3 clears #CBD2D9 on paper.
    "SPINE": "#39424B",
    # The inks, re-pitched rather than re-chosen. Each keeps its hue and its
    # meaning and gains the lightness a dark ground needs: the green is still
    # the cleared green, the ochre still the held ochre. The mapping to
    # run_query(...) branches is untouched — this is the same legend printed in
    # a second ink weight, which is what lets `formatting.py` and
    # `admin_formatting.py` stay entirely unaware that a second ground exists.
    "INK_CLEAR": "#5FD1A9",
    "INK_HELD": "#DCB44A",
    "INK_DENIED": "#F08A8D",
    "INK_FORBIDDEN": "#EDA06A",
    "INK_UPSTREAM": "#8FB3E0",
    "INK_FAULT": "#B9A6E8",
    # Identical to INK, exactly as in the light palette: "your own words" is
    # plain ink on either ground, and a dark palette that let the two drift would
    # be inventing a verdict for the reader's own turn.
    # `tests/test_contrast.py::test_ink_self_is_the_same_pigment_as_ink_on_both_grounds`
    # holds the identity on both palettes at once.
    "INK_SELF": "#E4E9ED",
    # Tints, at the same whisper. On a dark ground a tint is a *warming or
    # cooling* of the paper by a few steps, not a wash — pushed further and the
    # panel starts competing with the rail it is supposed to sit behind.
    "TINT_CLEAR": "#16211D",
    "TINT_HELD": "#221E14",
    "TINT_DENIED": "#241819",
    "TINT_FORBIDDEN": "#231B15",
    "TINT_UPSTREAM": "#171D26",
    "TINT_FAULT": "#1D1926",
}


def _custom_property(name: str) -> str:
    """`INK_CLEAR` -> `--hx-ink-clear`.

    One place, so the declaration block and the token references below cannot
    drift apart. Private: nothing outside this module needs to build a property
    name, because the tokens below are already the full `var(...)` reference —
    which is the string a component renders and therefore the string the render
    guards in `tests/` compare against.
    """
    return f"--hx-{name.lower().replace('_', '-')}"


def _declarations(palette: dict[str, str]) -> str:
    return "\n  ".join(f"{_custom_property(k)}: {v};" for k, v in palette.items())


# --- Colour tokens -------------------------------------------------------
# What every component imports. These are `var(...)` references, not values:
# the value arrives from the `:root` / `html.dark` blocks in GLOBAL_CSS.
#
# Deliberately written out one per line rather than generated into the module
# namespace. They are named constants that an editor can jump to and a reader
# can grep, and PRD-006's admin palette guard greps this file's *names*; a
# `globals().update(...)` loop would save twenty lines and cost all of that.
#
# No fallback value is given inside the `var()`. A `var(--hx-paper, #ECEFF1)`
# would put a light hex into every compiled component, which is exactly what
# `tests/test_render_invariants.py` reads a page for. The custom properties are
# defined unconditionally at `:root`, so the fallback would never fire anyway.
PAPER = f"var({_custom_property('PAPER')})"
CARD = f"var({_custom_property('CARD')})"
INK = f"var({_custom_property('INK')})"
MUTE = f"var({_custom_property('MUTE')})"
RULE = f"var({_custom_property('RULE')})"
RULE_SOFT = f"var({_custom_property('RULE_SOFT')})"
HOVER = f"var({_custom_property('HOVER')})"
SPINE = f"var({_custom_property('SPINE')})"

INK_CLEAR = f"var({_custom_property('INK_CLEAR')})"
INK_HELD = f"var({_custom_property('INK_HELD')})"
INK_DENIED = f"var({_custom_property('INK_DENIED')})"
INK_FORBIDDEN = f"var({_custom_property('INK_FORBIDDEN')})"
INK_UPSTREAM = f"var({_custom_property('INK_UPSTREAM')})"
INK_FAULT = f"var({_custom_property('INK_FAULT')})"
INK_SELF = f"var({_custom_property('INK_SELF')})"

TINT_CLEAR = f"var({_custom_property('TINT_CLEAR')})"
TINT_HELD = f"var({_custom_property('TINT_HELD')})"
TINT_DENIED = f"var({_custom_property('TINT_DENIED')})"
TINT_FORBIDDEN = f"var({_custom_property('TINT_FORBIDDEN')})"
TINT_UPSTREAM = f"var({_custom_property('TINT_UPSTREAM')})"
TINT_FAULT = f"var({_custom_property('TINT_FAULT')})"

# --- Type ----------------------------------------------------------------
# Three roles, each doing one job:
#   display — the wordmark and the verdict tags (institutional grotesque)
#   body    — transcript prose, yours and the model's (this is a record, and
#             records are set in a reading face)
#   data    — evidence: audit ids, token counts, matched patterns, timestamps
FONT_DISPLAY = "'Archivo', 'Helvetica Neue', Arial, sans-serif"
FONT_BODY = "'Source Serif 4', Georgia, 'Times New Roman', serif"
FONT_DATA = "'JetBrains Mono', 'SF Mono', Consolas, monospace"

FONTS_HREF = (
    "https://fonts.googleapis.com/css2"
    "?family=Archivo:wght@400;500;600;700"
    "&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600"
    "&family=JetBrains+Mono:wght@400;500"
    "&display=swap"
)

# --- Scale ---------------------------------------------------------------
# Nothing below this line takes a second value on the dark ground. A ground
# changes what a colour has to be; it does not change a reading measure, a row
# height or a corner radius, and giving these a dark variant would invent a
# difference the design does not have.
TEXT_MICRO = "0.625rem"  # register column heads — a signpost, never row data
TEXT_TAG = "0.6875rem"  # verdict tags, eyebrows
TEXT_DATA = "0.75rem"  # footers, evidence lines
TEXT_BODY = "0.9375rem"
TEXT_LEAD = "1.0625rem"

RADIUS = "3px"
RAIL_X = "1.875rem"  # rail's distance from the transcript's left edge
STAMP_X = RAIL_X  # the register's stamp margin *is* the chat's rail, continued
GLYPH = "9px"
ROW_H = "2.25rem"  # one register row: dense enough to scan a hundred
COLUMN_MAX = "56rem"
MEASURE = "42rem"  # reading measure for prose — roughly 70 characters
PANEL_MAX = "36rem"  # a verdict is a short record, not a banner

# The session rail. Four sizes, no colour: PRD-008 Section 6.1 closes the
# palette for this surface -- "no new inks. The rail is PAPER ground against
# the transcript's CARD, separated by the existing RULE. The active session is
# marked with INK type against HOVER." Every one of those five tokens is
# already declared above, so this block adds none.
#
# The active mark is not declared here either, and that is the point. It is
# RAIL_X / GLYPH / SPINE -- the same three tokens bubbles.py assembles for the
# transcript's rail and register.py for the stamp margin -- appearing a third
# time at a third scale. PRD-008 Section 6.1: "Three surfaces, one structural
# device, each time encoding *which one of these is the one*." A
# SESSION_RAIL_MARK_W beside GLYPH would be a third device wearing the second
# one's clothes.
#
# SESSION_RAIL_*, not RAIL_*: RAIL_X above already means the *transcript's*
# rail and is reused by this surface, so a bare RAIL_W would name the wrong
# rail at the one point the two meet.
SESSION_RAIL_W = "15rem"  # ~34 title characters at TEXT_DATA past the RAIL_X inset
SESSION_RAIL_ROW_H = "3rem"  # two lines: the title, and the activity time under it
SESSION_RAIL_GUTTER = "0.75rem"  # the rail's own padding and its gap to the transcript
# Below this the rail collapses (STORY-019). SESSION_RAIL_W + MEASURE is 57rem,
# so 60rem is the width at which the rail stops costing the transcript its
# reading measure rather than an arbitrary device breakpoint.
SESSION_RAIL_COLLAPSE_W = "60rem"

# --- Global stylesheet ---------------------------------------------------
# Injected once as a <style> tag. Holds only what inline props cannot express:
# the two palettes, keyframes, focus-visible, selection, scrollbars, and the
# reduced-motion opt-out. Everything else lives on the components.
#
# The two palette blocks are the whole of the ground switch. `html.dark` is the
# selector because that is what Reflex's pre-paint script sets on the document
# element: it reads localStorage["theme"], resolves "system" against
# prefers-color-scheme, and adds the class before first paint — which is why
# there is no flash of the wrong ground, and why this file needs no
# prefers-color-scheme media query of its own. Writing one anyway would fight
# the class on every machine whose OS setting and explicit choice disagree.
#
# `color-scheme` is set in both blocks so the browser's own chrome — form
# controls, the scrollbar gutter, the canvas behind an overscroll — follows the
# palette. It is the one thing the custom properties cannot reach.
GLOBAL_CSS = f"""
:root {{
  color-scheme: light;
  {_declarations(LIGHT)}
}}

html.dark {{
  color-scheme: dark;
  {_declarations(DARK)}
}}

body {{
  background: {PAPER};
  color: {INK};
  font-family: {FONT_BODY};
  -webkit-font-smoothing: antialiased;
}}

::selection {{ background: {INK}; color: {PAPER}; }}

/* Keyboard focus stays visible everywhere, including on Radix controls that
   ship their own reset. */
:focus-visible {{
  outline: 2px solid {INK_UPSTREAM};
  outline-offset: 2px;
  border-radius: {RADIUS};
}}

/* A ledger scrolls a lot; give it a rail-coloured thumb rather than the
   platform default. */
.hx-scroll::-webkit-scrollbar {{ width: 10px; }}
.hx-scroll::-webkit-scrollbar-track {{ background: transparent; }}
.hx-scroll::-webkit-scrollbar-thumb {{
  background: {RULE};
  border: 3px solid {PAPER};
  border-radius: 6px;
}}
.hx-scroll::-webkit-scrollbar-thumb:hover {{ background: {MUTE}; }}

/* The one orchestrated moment: an entry arrives by rising onto the rail. */
@keyframes hx-enter {{
  from {{ opacity: 0; transform: translateY(6px); }}
  to   {{ opacity: 1; transform: none; }}
}}
.hx-entry {{ animation: hx-enter 200ms cubic-bezier(0.22, 0.61, 0.36, 1) both; }}

@keyframes hx-pulse {{
  0%, 100% {{ opacity: 1; }}
  50%      {{ opacity: 0.25; }}
}}
.hx-pulse {{ animation: hx-pulse 1.4s ease-in-out infinite; }}

@media (prefers-reduced-motion: reduce) {{
  .hx-entry, .hx-pulse {{ animation: none; }}
  * {{ transition-duration: 0.01ms !important; }}
}}

/* Radix paints the real <input> inside its TextField wrapper, so inline props
   on the wrapper never reach the text the user types. State both colours
   outright rather than inheriting a token that depends on the appearance.
   Four fields need it: the composer, the chat's session gate, the admin
   console's token gate, and the register's filter field. */
#chat_input, #user_id_input, #admin_token_input, #register_filter_input {{
  color: {INK} !important;
  background: transparent;
}}
#chat_input::placeholder, #user_id_input::placeholder,
#admin_token_input::placeholder, #register_filter_input::placeholder {{
  color: {MUTE} !important;
  opacity: 1;  /* Firefox dims placeholders by default */
}}

/* Radix's TextFieldRoot brings its own surface fill, inset border and focus
   ring. Inside the composer frame that is three layers of chrome for one
   field, so strip the wrapper bare and let the frame carry all of it. */
.hx-field, .hx-field:focus-within {{
  background: transparent !important;
  box-shadow: none !important;
  border: none !important;
  outline: none !important;
}}
#chat_input:focus, #chat_input:focus-visible {{
  outline: none !important;
  box-shadow: none !important;
}}
.hx-composer:focus-within {{
  border-color: {INK};
  box-shadow: 0 0 0 1px {INK};
}}

/* The session gate's field is standalone, so there it keeps a real frame. */
.hx-field-boxed {{
  background: {CARD} !important;
  box-shadow: inset 0 0 0 1px {RULE} !important;
}}
.hx-field-boxed:focus-within {{
  box-shadow: inset 0 0 0 1px {INK} !important;
}}

/* The Radix select trigger resolves its own colour token and lands on a
   near-white that vanishes against the header. Reach it by id — the wrapper's
   inline props never get there. */
#model-selector, #model-selector * {{
  color: {INK} !important;
  font-family: {FONT_DATA};
  font-size: {TEXT_DATA};
}}
#model-selector {{
  background: {CARD};
  border: 1px solid {RULE};
  border-radius: {RADIUS};
  box-shadow: none;
}}
#model-selector:hover {{ border-color: {MUTE}; }}

/* The ground toggle: one icon button, and the only icon in the design.

   That is worth stating plainly, because it is a departure. Every other control
   on both surfaces is a word, and the one non-typographic mark anywhere is the
   rail's nine-pixel SPINE, which carries no glyph. A sun and a moon are the
   exception, and they earn it the way no other icon here would: they are the two
   states themselves rather than a picture of an action, they need no legend in
   any language, and the alternative spelled the same fact in three words that
   sat in the masthead permanently.

   **Nothing in this stylesheet may quote a UI string.** The comments here ship
   inside `rx.el.style(...)`, which is emitted at the top of every page, so a
   label named in prose lands in the compiled output *before* the component that
   renders it. `tests/test_chat_shell.py` locates the masthead and the rail by
   their copy to assert the page's band order, and an earlier draft of this
   comment named three controls by their exact labels — putting the rail's
   wording above the masthead's and inverting the order the test reads.

   It spends no new ink. MUTE at rest and INK on hover is exactly the treatment
   the two shells give the control that ends the session, so the icon reads as a
   peer of the words around it rather than as a badge — and the hover ground is
   the register's, appearing here at a third scale.

   Colour and size both live in this rule and not on the component. Lucide
   strokes its glyphs with `currentColor`, so the icon inherits `color` and
   follows the palette with no branch; sizing the svg here rather than through
   the component's `size` prop is what lets `ground_switch.py` import no token at
   all, which `tests/test_ground.py` holds it to. */
.hx-ground-toggle {{
  appearance: none;
  border: none;
  cursor: pointer;
  background: transparent;
  color: {MUTE};
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.25rem;
  border-radius: {RADIUS};
  transition: color 120ms ease, background-color 120ms ease;
}}
.hx-ground-toggle svg {{
  width: 15px;
  height: 15px;
  display: block;
}}
.hx-ground-toggle:hover {{
  color: {INK};
  background: {HOVER};
}}

@media (max-width: 40rem) {{
  .hx-header-meta {{ width: 100%; justify-content: space-between; }}
}}
"""
