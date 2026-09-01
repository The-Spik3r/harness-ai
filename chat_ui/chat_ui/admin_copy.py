"""Centralized user-facing copy and templates for the admin console.

The counterpart to `copy.py`, and deliberately a **second** module rather than a
second half of the first one: PRD-006 Section 6 lists `admin_copy.py` as a new
file, and the two surfaces stay separate. That separation is structural, not
filing — PRD-006 Section 4 requires that "`ChatState` never reads admin state,
and no admin page renders a chat component", and a constant imported across the
boundary is the first thread of exactly that coupling. So where a word is shared
with the chat (the HARNESS wordmark, the " · " separator, "Matched pattern"), it
is **re-declared here**, not imported. This module imports nothing at all.

Voice, inherited from `copy.py` and from the **frontend-design** skill, which
governs every string below:

  "Errors don't apologize, and they are never vague about what happened."
      -> FAULT_MESSAGE_TEMPLATE names the read that failed and states that
         nothing on screen moved. No "Sorry", no "Something went wrong".

  "An empty screen is an invitation to act."
      -> each of the three empty states ends in the action available from it.

  "An action keeps the same name through the whole flow, so the button that says
   'Publish' produces a toast that says 'Published.'"
      -> Refresh -> Refreshing -> Refreshed {time}. One verb, three tenses, and
         the fault panel's retry is that same REFRESH_LABEL rather than a second
         word for the same button.

  "A control should say exactly what happens when it's used: 'Save changes,' not
   'Submit.'"
      -> the gate submits with "Open the console"; the filter clears with
         "Clear filters".

**Copy is not values.** `admin_formatting.VERDICT_*` are keys — the `rx.match`
arms and the filter values — while the `VERDICT_*_LABEL` constants below are the
words on screen. They hold the same four strings today and stay separate names
anyway: the day the register renders "Held (duplicate)" the key must not move
with it. For the same reason this module does not redeclare
`admin_formatting.VALUE_ABSENT` or `SHARE_UNDEFINED`; those are the absence marks
the formatter writes *into* a row field, and they belong with the formatter.

**Two deliberate absences.** There is no sign-out notice: PRD-006 Section 6.1
says "**Sign out** returns the gate, not a 'session ended' notice", so the gate
reappearing *is* the confirmation. And there is exactly **one** refusal message —
PRD-006 Section 9: "an empty, malformed or wrong token produces the same message.
The gate reports that access was refused, not why." A second, more helpful
message is the oracle that section forbids; `tests/test_copy.py` fails if one is
added.

Per PRD-006 Section 4, this is copy centralization, not i18n: flat constants, no
catalogue, no lookup helper.
"""

# --- Masthead and views --------------------------------------------------
# "HARNESS · REGISTER" / "HARNESS · SUMMARY". The wordmark and the separator are
# re-declared rather than imported from copy.py — see the module docstring.
CONSOLE_TITLE = "HARNESS"
MASTHEAD_SEPARATOR = " · "
CONSOLE_VIEW_REGISTER = "REGISTER"
CONSOLE_VIEW_SUMMARY = "SUMMARY"

# The two-view switch. Exactly two destinations, so they are peers in the
# masthead rather than a sidebar (PRD-006 Section 6.1).
VIEW_REGISTER_LABEL = "Register"
VIEW_SUMMARY_LABEL = "Summary"

SIGN_OUT_LABEL = "Sign out"

# --- Gate ----------------------------------------------------------------
GATE_TITLE = "Admin token"
GATE_BODY = (
    "The console reads the audit record. Enter the admin token to open it."
)
GATE_PLACEHOLDER = "Admin token"
# Names what happens, not the mechanism: "Open the console", never "Submit".
GATE_SUBMIT_LABEL = "Open the console"

# One message for an empty token, a wrong-length token and a wrong token of the
# right length. PRD-006 Section 9: "The gate reports that access was refused, not
# why." Three conditions in `AdminState._refuse()` reach this string, and they
# must be indistinguishable from outside the gate — splitting it into a second,
# more specific message is the token oracle that section forbids.
# `admin_state.py` imports this name; `tests/test_admin_state.py` compares
# `gate_error` against it.
GATE_REFUSED_MESSAGE = "Access refused. That token was not accepted."

# --- Register columns ----------------------------------------------------
# One head per column PRD-006 Section 4 names. Short on purpose: they are set at
# theme.TEXT_MICRO over a dense row, and a two-word head wraps into theme.ROW_H.
COLUMN_TIME = "Time"
COLUMN_USER = "User"
COLUMN_VERDICT = "Verdict"
COLUMN_MODEL = "Model"
COLUMN_TOKENS = "Tokens"
COLUMN_PII = "PII"
COLUMN_DEVICE = "Device"
# Heads a column of "#3180" values — the row's real audit_id, and the string a
# user quotes out of the chat's success footer (PRD-004 STORY-010).
COLUMN_ID = "ID"
AUDIT_ID_PREFIX = "#"

# The in-row mark itself, distinct from the column head above it: the head names
# the column, the mark states the fact. Absence is the formatter's VALUE_ABSENT.
PII_INDICATOR_LABEL = "PII"

# --- Verdict labels ------------------------------------------------------
# The four words on screen. Lowercase here, deliberately: PRD-006 Section 6.1's
# wireframe shows the exceptions in caps, but that is a *treatment* — the
# register applies it with text_transform so the same word cannot arrive in two
# cases from two constants and leave the filter chip disagreeing with the row.
VERDICT_CLEARED_LABEL = "cleared"
VERDICT_HELD_LABEL = "held"
VERDICT_DENIED_LABEL = "denied"
VERDICT_FAULT_LABEL = "fault"

# --- Scope lines ---------------------------------------------------------
# PRD-006 Risk 4: all-time figures beside a 100-row window "invite a wrong
# reading", so scope is a required part of every label rather than a nicety.
#
# {shown} rather than a literal 100: the register formats this from
# `admin_state.REGISTER_ROW_LIMIT`, so the cap is typed once in the codebase and
# a changed limit cannot leave the copy claiming the old one.
REGISTER_SCOPE_TEMPLATE = "{shown} most recent of {total}"
# The filtered count, which is a different statement from the scope line above
# and must not replace it (STORY-013): the scope states the window, this states
# how much of the window survived the filter.
REGISTER_FILTERED_TEMPLATE = "{shown} of {loaded} shown"

SUMMARY_SCOPE_ALL_TIME = "All time, every recorded row"
# The one prose line on the summary, and the direct mitigation for Risk 4: it
# names the difference between the two windows so 3,180 beside 100 rows reads as
# two scopes rather than as a contradiction.
SUMMARY_SCOPE_NOTE = (
    "These figures count the whole table. The register shows only the most "
    "recent rows."
)

# --- Refresh -------------------------------------------------------------
# One verb across the whole flow: the control says Refresh, the in-flight state
# says Refreshing, the line it produces says Refreshed. The fault panel's retry
# reuses REFRESH_LABEL rather than declaring a second name for the same button.
REFRESH_LABEL = "Refresh"
REFRESH_IN_FLIGHT_LABEL = "Refreshing"
REFRESHED_TEMPLATE = "Refreshed {time}"
# Before the first read completes there is no stamp to show, and a blank slot
# beside the control reads as a broken one.
NEVER_REFRESHED_LABEL = "Not read yet"

# --- Fault panel ---------------------------------------------------------
FAULT_TITLE = "The read failed."
# Names what failed, states that the screen did not move, gives the action. The
# stale register is not a wrong one, and which of the two an admin is looking at
# is the fact they need before trusting anything on screen. "Refresh" is the same
# word REFRESH_LABEL carries. `admin_state.py` imports this as
# LOAD_FAILED_MESSAGE and formats it with the read's label and the exception.
FAULT_MESSAGE_TEMPLATE = (
    "Could not read {read}. Nothing on screen has changed. Refresh to try "
    "again. ({detail})"
)

# What to call each of the ten reads inside FAULT_MESSAGE_TEMPLATE. These are the
# labels `admin_state._READS` carries and are worded as the object of "Could not
# read ___", which is why each begins with an article. Their values are pinned by
# `tests/test_admin_state.py` — three are asserted as literals — so a rewording
# here is a test-visible change rather than a silent one.
READ_LABEL_ROWS = "the audit rows"
READ_LABEL_TOTAL = "the recorded total"
READ_LABEL_BLOCKED_DUPLICATES = "the blocked duplicates"
READ_LABEL_BLOCKED_SUSPICIOUS = "the blocked patterns"
READ_LABEL_UNIQUE_USERS = "the user count"
READ_LABEL_SUCCESSFUL = "the completed count"
READ_LABEL_PII_QUERIES = "the PII detection count"
READ_LABEL_TOP_MODELS = "the model ranking"
READ_LABEL_TOP_USERS = "the user ranking"
READ_LABEL_TOP_PII = "the PII entity ranking"

# --- The three empty states ----------------------------------------------
# PRD-006 Section 4 names three register states — no rows recorded, rows recorded
# but none matching, and rows shown. The third is a table, so the three states
# that need words are the two empty registers below plus the empty summary.
# Each one ends in the action available from it, per the skill.

# 1. Nothing has ever been recorded.
EMPTY_REGISTER_TITLE = "The register is empty."
EMPTY_REGISTER_BODY = (
    "No prompt has passed through the harness yet. Refresh once traffic starts."
)

# 2. Rows are loaded, but the filter matches none of them. PRD-006 Section 6.1:
# "the no-matches state names the filter that produced it and offers to clear
# it" — so the filter is named in the sentence, not merely implied by an empty
# table, and the description is assembled from the three constants below rather
# than concatenated in the component.
EMPTY_MATCHES_TITLE = "No rows match this filter."
EMPTY_MATCHES_TEMPLATE = "{filters} matched none of the {loaded} rows loaded."
FILTER_DESCRIPTION_VERDICT_TEMPLATE = "verdict {verdicts}"
FILTER_DESCRIPTION_SEARCH_TEMPLATE = 'text "{search}"'
FILTER_DESCRIPTION_JOIN = " and "
# Between two selected verdicts *inside* FILTER_DESCRIPTION_VERDICT_TEMPLATE —
# "verdict held, denied". Distinct from FILTER_DESCRIPTION_JOIN above, which joins
# the two *kinds* of filter ('verdict denied and text "ana"'): one is a list, the
# other a conjunction, and collapsing them would read as "verdict held and denied
# and text ...". A named constant rather than a ", " typed into admin_state.py,
# because STORY-014 AC 5 requires every string on these panels resolve from this
# module.
FILTER_DESCRIPTION_VERDICT_JOIN = ", "

# 3. The summary with nothing to total. Every share renders its placeholder here
# (STORY-015), so the sheet says why rather than showing nine dashes.
EMPTY_SUMMARY_TITLE = "Nothing to summarize."
EMPTY_SUMMARY_BODY = (
    "No query has been recorded, so every figure would be zero. Refresh once "
    "traffic starts."
)

# --- Filter and sort controls --------------------------------------------
FILTER_VERDICT_LABEL = "Verdict"
FILTER_SEARCH_LABEL = "Find"
FILTER_SEARCH_PLACEHOLDER = "user, model or id"
CLEAR_FILTERS_LABEL = "Clear filters"

# One label per key in `admin_state.SORT_KEYS`, aligned one-to-one so a missing
# ordering is visible at a glance rather than at render.
SORT_LABEL = "Sort"
SORT_TIMESTAMP_LABEL = "Time"
SORT_USER_LABEL = "User"
SORT_VERDICT_LABEL = "Verdict"
SORT_ASCENDING_MARK = "↑"
SORT_DESCENDING_MARK = "↓"

# --- Row disclosure ------------------------------------------------------
# One label per field PRD-006 Section 10 puts on disclosure. The toggle keeps its
# name across both directions of the same control.
DETAIL_TOGGLE_OPEN_LABEL = "Show detail"
DETAIL_TOGGLE_CLOSE_LABEL = "Hide detail"

# The toggle's *visible* content, against the two labels above as its accessible
# name. Two names for one control, and not drift: the control sits in a 2.5rem
# column at the right edge of a hundred rows, and "Show detail" set a hundred
# times down that edge would compete with the stamp margin — which is where
# PRD-006 Section 6.1 spends the whole design's boldness. `SORT_ASCENDING_MARK`
# above is the precedent for a mark living in this module; the register's "no
# icon" refusal is about icons, and these are characters. U+2212 MINUS SIGN
# rather than a hyphen, for the same typographic reason `VALUE_ABSENT` is an em
# dash.
DETAIL_TOGGLE_OPEN_MARK = "+"
DETAIL_TOGGLE_CLOSE_MARK = "−"

# The two PII booleans, as words. A false boolean has no VALUE_ABSENT to fall
# back on: `False` is a recorded fact, not a missing value — the same
# distinction `to_audit_row` makes for `tokens_used` — so "not detected" says
# the redactor ran and found nothing, where a dash would say the column was
# NULL. STORY-012 AC 5 requires the empty case be stated rather than left blank.
DETAIL_PII_PRESENT_LABEL = "detected"
DETAIL_PII_ABSENT_LABEL = "not detected"

# Declared, and deliberately not rendered. STORY-008 provisioned "one label per
# field PRD-006 Section 10 puts on disclosure", but that section's timestamp row
# describes the *in-row* column ("relative + absolute"), and
# `components/register.py:_time_cell` already sets the absolute stamp under the
# relative one. Repeating it on the disclosure would be the frontend-design
# skill's "nothing quietly does double duty", and STORY-012's first acceptance
# criterion names five fields, not six.
DETAIL_TIMESTAMP_LABEL = "Recorded"
DETAIL_PROMPT_HASH_LABEL = "Prompt hash"
DETAIL_ERROR_LABEL = "Error"
# The same fact under the same name the chat already gives it
# (copy.INJECTION_PATTERN_LABEL) — re-declared, not imported. Two names for one
# fact across two surfaces is the vocabulary drift the skill's consistency rule
# is about.
DETAIL_PATTERN_LABEL = "Matched pattern"
DETAIL_DEVICE_LABEL = "User agent"
# Shown combined as PII_INDICATOR_LABEL in the row, split here.
DETAIL_PII_ENTITIES_LABEL = "PII types"
DETAIL_PII_INPUT_LABEL = "PII in prompt"
DETAIL_PII_OUTPUT_LABEL = "PII in response"

# --- Summary figures -----------------------------------------------------
# Three ruled blocks, per PRD-006 Section 6.1: the counts, then the who/what
# facts, then PII telemetry. Headings, not card titles — the sheet has no cards.
SUMMARY_COUNTS_HEADING = "Traffic"
SUMMARY_WHO_HEADING = "Who and what"
SUMMARY_PII_HEADING = "Personal data"

FIGURE_TOTAL_LABEL = "Queries recorded"
# Indented beneath the total on the sheet, because they are a subset of it.
FIGURE_BLOCKED_DUPLICATES_LABEL = "Held as duplicates"
FIGURE_BLOCKED_SUSPICIOUS_LABEL = "Denied on a pattern"

# The one label on this console with a correctness requirement.
#
# PRD-006 Section 1 states the defect being labeled around: "`success_rate` is
# computed as `count_successful_queries() / count_audit_logs()`, where
# `count_successful_queries()` counts `success = 1` — which includes every
# duplicate-blocked and every injection-blocked row, because the pipeline logs
# both as `success=True`. The number reads as 'how often users got an answer' and
# counts something else."
#
# So the word *success* does not appear here, and neither does *rate* in the
# sense of an answer rate. PRD-006 Section 4 fixes what it must say instead:
# "labeled for what it counts — rows the pipeline completed without raising,
# blocked rows included — not as an answer rate." The computation is not fixed
# here: `app/` is out of scope for PRD-006 and a truthful metric is deferred to
# its Section 13. STORY-016 pins this wording in a test so it cannot drift back.
FIGURE_COMPLETION_LABEL = "Completed without error (blocked queries included)"
FIGURE_COMPLETION_NOTE = (
    "Counts rows the pipeline finished without raising. A held duplicate and a "
    "denied prompt both count as completed, so this is not an answer rate."
)

FIGURE_UNIQUE_USERS_LABEL = "Distinct users"
FIGURE_TOP_MODELS_LABEL = "Most used models"
FIGURE_TOP_USERS_LABEL = "Most active users"
FIGURE_PII_QUERIES_LABEL = "Queries containing PII"
FIGURE_TOP_PII_LABEL = "Most frequent PII types"

# The cut on every ranked list, stated on the surface (PRD-006 Section 4). {n}
# comes from the read's own limit (`top_models(limit=5)`), so the copy does not
# carry a second, unowned 5.
RANKED_CUT_TEMPLATE = "top {n}"
# Wraps `admin_formatting.format_share`'s output — that function computes the
# percentage, this constant supplies only the words around it.
SHARE_TEMPLATE = "{share} of all queries"
# A ranked list with nothing in it yet. Shorter than the three empty states
# above because it is one figure, not a page.
RANKED_EMPTY_LABEL = "Nothing ranked yet"
