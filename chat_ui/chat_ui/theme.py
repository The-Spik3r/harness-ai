"""Design tokens for the Harness AI chat surface.

Direction: *inspection ledger*. The chat is not a messaging app, it is a
running record of traffic that passed through a checkpoint. Every entry is a
full-width row clamped to a vertical rail; the rail glyph and the verdict tag
carry the outcome. Nothing alternates left and right, nothing floats in a
bubble.

Every colour and size used anywhere in the UI is defined here, so a change of
visual direction is a single-file edit — the same guarantee copy.py gives for
wording.
"""

# --- Ground --------------------------------------------------------------
# A cool blue-grey paper rather than warm cream: this is an institutional
# record, not a magazine.
PAPER = "#ECEFF1"
CARD = "#FFFFFF"
INK = "#14181C"
MUTE = "#626C77"
RULE = "#CBD2D9"
RULE_SOFT = "#DDE2E7"
# The register's row hover. A hover has to be findable without becoming a
# second signal — the stamp margin is where that surface spends its boldness —
# so it lifts toward the card rather than darkening toward the rule. Darkening
# was measured and rejected: it drops MUTE below AA, and MUTE sets the
# register's timestamps.
HOVER = "#F1F3F5"
# The rail itself. It has to hold its own against the paper: it is the one
# structural line the whole design rests on.
SPINE = "#C3CBD3"

# --- Stamp inks ----------------------------------------------------------
# One pigment per pipeline outcome. This is a legend, not decoration: PRD-004
# requires that no two semantically different outcomes share a treatment, so
# each ink maps to exactly one branch of run_query(...).
INK_CLEAR = "#1B5E4B"  # assistant — cleared inspection
INK_HELD = "#7C5E11"  # duplicate — held, not rejected
INK_DENIED = "#9B2226"  # injection — denied and logged
INK_FORBIDDEN = "#B5541D"  # forbidden by policy -- distinct from injection's INK_DENIED
INK_UPSTREAM = "#34567F"  # OpenRouter failed — an outside party
INK_FAULT = "#5D4A8C"  # the harness itself failed
INK_SELF = "#14181C"  # your own words — plain ink, no verdict

# Every ink above clears WCAG AA (4.5:1) for small text against both PAPER and
# its own tint; the ochre was darkened from #8A6A12, which sat at 4.38 on
# PAPER. tests/test_contrast.py holds the line.

# Tint used behind a stamped panel. Kept at a whisper so the rail, not the
# fill, does the signalling.
TINT_CLEAR = "#F1F6F4"
TINT_HELD = "#FAF6EA"
TINT_DENIED = "#FBF1F1"
TINT_FORBIDDEN = "#FCF1E8"
TINT_UPSTREAM = "#F1F4F9"
TINT_FAULT = "#F5F3F9"

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

# --- Global stylesheet ---------------------------------------------------
# Injected once as a <style> tag. Holds only what inline props cannot express:
# keyframes, focus-visible, selection, scrollbars, and the reduced-motion
# opt-out. Everything else lives on the components.
GLOBAL_CSS = f"""
:root {{ color-scheme: light; }}

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

@media (max-width: 40rem) {{
  .hx-header-meta {{ width: 100%; justify-content: space-between; }}
}}
"""
