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
# The rail itself. It has to hold its own against the paper: it is the one
# structural line the whole design rests on.
SPINE = "#C3CBD3"

# --- Stamp inks ----------------------------------------------------------
# One pigment per pipeline outcome. This is a legend, not decoration: PRD-004
# requires that no two semantically different outcomes share a treatment, so
# each ink maps to exactly one branch of run_query(...).
INK_CLEAR = "#1B5E4B"  # assistant — cleared inspection
INK_HELD = "#8A6A12"  # duplicate — held, not rejected
INK_DENIED = "#9B2226"  # injection — denied and logged
INK_FORBIDDEN = "#B5541D"  # forbidden by policy -- distinct from injection's INK_DENIED
INK_UPSTREAM = "#34567F"  # OpenRouter failed — an outside party
INK_FAULT = "#5D4A8C"  # the harness itself failed
INK_SELF = "#14181C"  # your own words — plain ink, no verdict

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
TEXT_TAG = "0.6875rem"  # verdict tags, eyebrows
TEXT_DATA = "0.75rem"  # footers, evidence lines
TEXT_BODY = "0.9375rem"
TEXT_LEAD = "1.0625rem"

RADIUS = "3px"
RAIL_X = "1.875rem"  # rail's distance from the transcript's left edge
GLYPH = "9px"
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
