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

# The view switch. Two destinations under PRD-006, three since PRD-013 added the
# Usage table (STORY-016): still few enough to be peers in the masthead rather
# than a sidebar (PRD-006 Section 6.1).
VIEW_REGISTER_LABEL = "Register"
VIEW_SUMMARY_LABEL = "Summary"
VIEW_USAGE_LABEL = "Usage"
# PRD-018 STORY-012: the fifth peer.
VIEW_STORAGE_LABEL = "Storage"
# PRD-022 STORY-016 (F9): the sixth peer.
VIEW_PROVIDERS_LABEL = "Providers"
# PRD-023 STORY-018 (F11): the seventh peer, present only with MCP_ENABLED=true.
VIEW_SKILLS_LABEL = "Skills"

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
# PRD-020 D13: the provider that served the row (empty for rows before it).
COLUMN_PROVIDER = "Provider"
# PRD-022 STORY-016 (F8): which try of the request this row is. 1 is the first
# upstream call; a fallback answer is 2 or more. The absent mark on rows that
# never reached the upstream step.
COLUMN_ATTEMPT = "Try"
COLUMN_ATTEMPT_TITLE = "Which upstream attempt of the request this row records"
# PRD-021 F7: the tag on a row that was delivered in real time, and its
# hover/assistive text so it is not only a caps word.
LIVE_LABEL = "LIVE"
LIVE_TITLE = "Delivered in real time"
COLUMN_TOKENS = "Tokens"
# PRD-013 (STORY-015): the head keeps its one word, and this states the order
# of the "2,140 / 312" cell once, on hover, rather than on every row. A head
# reading "Tokens in / out" would also sit over rows that show a single total.
COLUMN_TOKENS_TITLE = "Input / output tokens, or the total where no split was recorded"
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
# PRD-013 (STORY-015): the token totals' scope. Not SUMMARY_SCOPE_ALL_TIME,
# because that would be false: the sums read NULL as 0 (PRD-013 Section 6.10),
# so a row from before the split and an upstream-error row contribute nothing.
# What the figure does cover is every row that recorded a split.
SUMMARY_SCOPE_TOKENS = "All time, rows that recorded an input and output split"
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

# What to call each of the thirteen reads inside FAULT_MESSAGE_TEMPLATE. These are the
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
# PRD-013 STORY-006: the three figures the batched read gained, named so that
# a failed read is named. STORY-015 renders them on the summary.
# "blocks", not "refusals": GATE_REFUSED_MESSAGE must stay the only string here
# that mentions a refusal (PRD-006 Section 9, `tests/test_admin_copy.py`), and
# "blocked" is already how the two other blocked counts are named.
READ_LABEL_INPUT_TOKENS = "the input token total"
READ_LABEL_OUTPUT_TOKENS = "the output token total"
READ_LABEL_USAGE_LIMITS = "the usage-limit blocks"
# PRD-013 STORY-016: the Usage table's read. Not one of the thirteen above and
# not in `admin_state._READS`: it is a separate read with its own fault (F16), so
# a failure here names itself and never blanks the summary or the Register.
READ_LABEL_USAGE = "the usage for today"
# PRD-018 STORY-012: the Storage view's read, its own fault like the usage read.
READ_LABEL_STORAGE = "the storage status"
# PRD-022 STORY-016: the Providers view's read, its own fault like the storage one.
READ_LABEL_PROVIDERS = "the providers status"
# PRD-023 STORY-018: the Skills view's read, its own fault like the providers one.
READ_LABEL_SKILLS = "the skills"

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
# (STORY-015), so the sheet says why rather than showing twelve dashes.
EMPTY_SUMMARY_TITLE = "Nothing to summarize."
EMPTY_SUMMARY_BODY = (
    "No query has been recorded, so every figure would be zero. Refresh once "
    "traffic starts."
)

# --- Usage (PRD-013 STORY-016) -------------------------------------------
# The Usage table: what each user has used today against their token budget.
# Plain words for what an operator controls and recognises (frontend-design):
# "Budget" and "Used", not token_budget_daily or tokens_today.
#
# The window, stated on the table rather than implied: every figure states its
# window (PRD-006 Risk 4), and this view's window is not the summary's.
USAGE_CAPTION = "Today, UTC"

# Column heads. "User" is COLUMN_USER, shared with the register.
COLUMN_ROLE = "Role"
COLUMN_REQUESTS = "Requests"
COLUMN_INPUT = "Input"
COLUMN_OUTPUT = "Output"
COLUMN_BUDGET = "Budget"
COLUMN_USED = "Used"
# "Denied", never "Refused": GATE_REFUSED_MESSAGE must stay the only string here
# that mentions a refusal (`tests/test_admin_copy.py`), and "denied" is the
# verdict the Register shows for these same rows.
COLUMN_DENIED = "Denied"

# Each head keeps one word; what its values mean is stated once, on hover.
COLUMN_BUDGET_TITLE = (
    "Tokens a day: this user's own limit where one is set, otherwise their role's"
)
# Used is the number the gate compares against the budget, which includes tokens
# a provider reported with no input/output split -- so Input + Output can sum to
# less than it. The title says so, and names the order the rows are in.
COLUMN_USED_TITLE = (
    "Share of the budget used today, counting tokens with no input/output "
    "split. Highest first."
)
COLUMN_DENIED_TITLE = "Requests denied at a usage limit today"

# The budget cell for a user with no budget. A word, not a symbol.
USAGE_BUDGET_UNLIMITED = "unlimited"

# The empty day. The title is the PRD's own sentence (Section 6.10); the body
# says when a row appears and gives the action.
EMPTY_USAGE_TITLE = "No one has sent anything today."
EMPTY_USAGE_BODY = (
    "A user appears here after their first request of the day. Counts reset at "
    "00:00 UTC; Refresh to read them again."
)

# --- Actions (PRD-016 STORY-019) -----------------------------------------
# The Actions view: what agents tried to do and what the action policy decided.
# Plain words for what an operator controls and recognises (frontend-design):
# "Denied", "Flagged", "Allowed", never the `deny`/`flag`/`allow` enum values.
VIEW_ACTIONS_LABEL = "Actions"

# Named as the object of "Could not read ___" (FAULT_MESSAGE_TEMPLATE). Not one
# of the thirteen summary reads: it has its own fault, so a failure here never
# blanks the Register, the summary or Usage.
READ_LABEL_ACTIONS = "the action decisions"

# The filter strip's eyebrow and its four chips. The chips re-read the database
# for the chosen decision (a 500-row window of "all" would hide every old deny
# once volume arrives), so the strip is named for what it shows, not "Filter".
ACTIONS_FILTER_LABEL = "Show"
ACTIONS_FILTER_DENIED_LABEL = "Denied"
ACTIONS_FILTER_FLAGGED_LABEL = "Flagged"
ACTIONS_FILTER_ALLOWED_LABEL = "Allowed"
ACTIONS_FILTER_ALL_LABEL = "All"

# Column heads; "Time", "User" and "Role" are the shared constants above.
# "Allowed by" is the permission that let the role through the rule.
COLUMN_TOOL = "Tool"
COLUMN_OPERATION = "Operation"
COLUMN_TARGET = "Target"
COLUMN_RULE = "Rule"
COLUMN_DECISION = "Decision"
COLUMN_ALLOWED_BY = "Allowed by"
COLUMN_OPERATION_TITLE = "What the call does to its target, as the tool reported it"
COLUMN_RULE_TITLE = "The rule that decided. A rule's own hover gives the reason it recorded."
COLUMN_ALLOWED_BY_TITLE = (
    "The permission that lets this role through the rule. Empty when the "
    "decision did not depend on one."
)

# One lowercase label per decision, the `VERDICT_*_LABEL` rule: the case is
# applied by `text_transform` so a tag and a sentence cannot disagree.
DECISION_DENY_LABEL = "denied"
DECISION_FLAG_LABEL = "flagged"
DECISION_ALLOW_LABEL = "allowed"

# The scope line states the window against the true total (PRD-006 Risk 4):
# "500 most recent of 1,204 denied". "All" reads "of 1,204 recorded".
ACTIONS_SCOPE_TEMPLATE = "{shown} most recent of {total} {decision}"
ACTIONS_SCOPE_ALL = "recorded"

# --- PRD-023 STORY-018 (D21): the gateway's share of the Actions view ----------
# Present only with MCP_ENABLED=true; with it off none of these reaches the page.
# The second chip strip: which surface the rows came through.
ACTIONS_SURFACE_LABEL = "Surface"
ACTIONS_SURFACE_ALL_LABEL = "All surfaces"
ACTIONS_SURFACE_V1_LABEL = "/v1"
ACTIONS_SURFACE_MCP_LABEL = "Gateway"
# A toggle, not a chip: PRD 6.8 makes the unlinked gateway call a filter of its
# own (a gateway call that claimed no `/v1` alias decision).
ACTIONS_UNLINKED_LABEL = "Unlinked gateway calls"
ACTIONS_UNLINKED_TITLE = (
    "Gateway calls that claimed no /v1 alias decision. Shows every decision, "
    "not only the denied ones."
)
COLUMN_SERVER = "Server"
COLUMN_SKILLS = "Skills"
COLUMN_OUTCOME = "Outcome"
COLUMN_LINKED = "Linked"
COLUMN_SERVER_TITLE = "The upstream MCP server the call was addressed to"
COLUMN_SKILLS_TITLE = "The skills that exposed this tool to the caller"
COLUMN_OUTCOME_TITLE = "What happened to a forwarded call (empty when it was not forwarded)"
COLUMN_LINKED_TITLE = (
    "The /v1 alias decision this gateway call claimed. Unlinked: no alias "
    "decision was claimed for this call."
)
# The cell's own title when it is a link: the row it names is only on the page
# when it is inside the current window.
ACTIONS_LINKED_LINK_TITLE = (
    "Jumps to that /v1 decision when it is in the rows shown; choose All "
    "surfaces or /v1 to bring it in."
)
ACTIONS_LINKED_NONE = "unlinked"
# Under a surface or unlinked narrowing the table-wide totals would misstate the
# window, so the line states the window and the narrowing and no total.
ACTIONS_SCOPE_NARROWED_TEMPLATE = "{shown} most recent {decision}, {narrow}"
ACTIONS_NARROW_V1 = "/v1 calls"
ACTIONS_NARROW_MCP = "gateway calls"
ACTIONS_NARROW_UNLINKED = "unlinked gateway calls"

# --- PRD-023 STORY-018: the Skills view -----------------------------------
SKILLS_CAPTION_TEMPLATE = "Configuration digest {digest}"
SKILLS_LABEL_TOOLS = "Tools"
SKILLS_LABEL_REQUIRES = "Requires"
SKILLS_LABEL_ROLES = "Roles holding it"
EMPTY_SKILLS_TITLE = "No skills configured."
EMPTY_SKILLS_BODY = (
    "This view lists the skills the MCP gateway offers: named sets of tools, "
    "each held by the roles whose permissions include skill:<id>. Skills come "
    "from the skills section of the file MCP_CONFIG_FILE names; none is defined "
    "there. Refresh to read again."
)

# The empty view says what it will contain, why it is empty, and the action.
EMPTY_ACTIONS_TITLE_TEMPLATE = "No {decision} actions recorded."
EMPTY_ACTIONS_ALL_TITLE = "No actions recorded."
# PRD-017 STORY-013: reworded now that `/v1` tool calls are decided live.
# It names `V1_TOOLS_ENABLED`, so renaming that setting must reword it.
EMPTY_ACTIONS_BODY = (
    "This view lists the decisions the action policy made on tool calls "
    "that models sent through /v1, denied first. Decisions are recorded "
    "only while tool calling is on (V1_TOOLS_ENABLED=true); each tool "
    "call a model makes then adds a row here. Refresh to read again."
)

# --- Filter and sort controls --------------------------------------------
FILTER_VERDICT_LABEL = "Verdict"
FILTER_SEARCH_LABEL = "Find"
# PRD-013 (STORY-015): the field also matches the conversation key, so it says
# so — pasting a key from one row's disclosure shows that conversation. It also
# matches the ingress (`v1`, `chat`, `query`), which the placeholder leaves out:
# naming both clipped inside a field narrow enough to sit beside its label at
# phone width.
# PRD-022 STORY-016: the field also matches the request id, left out of the
# placeholder for the same clipping reason as the ingress.
FILTER_SEARCH_PLACEHOLDER = "user, model, id or conversation"
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
# PRD-011 D6: the two facts that qualify the pattern. Their values are the
# audit's own words (`user`/`tool`/..., `block`/`flag`), shown as recorded. A
# row written before PRD-011 shows the absent mark on both rather than an
# inferred "block" -- its **denied** verdict already says it was blocked, and
# the column itself holds no such claim.
DETAIL_PATTERN_ROLE_LABEL = "Matched in"
DETAIL_PATTERN_ACTION_LABEL = "Pattern action"
DETAIL_DEVICE_LABEL = "User agent"
# PRD-012 D9: the profile that ran, shown as recorded (`chat`, `code`, ...).
# It qualifies the PII lines below it: under `code`, "PII in response" absent
# means the response was not analyzed, not that it was clean.
DETAIL_PROFILE_LABEL = "Profile"
# Shown combined as PII_INDICATOR_LABEL in the row, split here.
DETAIL_PII_ENTITIES_LABEL = "PII types"
DETAIL_PII_INPUT_LABEL = "PII in prompt"
DETAIL_PII_OUTPUT_LABEL = "PII in response"
# PRD-013 (STORY-015): the audit fields, named for what an admin recognises
# rather than for their columns (`limit_exceeded`, `conversation_key`,
# `message_count`, `has_tool_calls`). Values are shown as recorded --
# `requests`/`tokens`, `query`/`chat`/`v1` -- like DETAIL_PATTERN_ACTION_LABEL.
# None of them says "refused": GATE_REFUSED_MESSAGE stays the only one.
DETAIL_LIMIT_LABEL = "Usage limit"
DETAIL_CONVERSATION_LABEL = "Conversation"
# PRD-022 STORY-016 (F8): the id shared by every attempt row of one request.
DETAIL_REQUEST_LABEL = "Request"
DETAIL_INGRESS_LABEL = "Ingress"
DETAIL_MESSAGE_COUNT_LABEL = "Messages"
DETAIL_STREAMED_LABEL = "Streamed"
DETAIL_TOOL_CALLS_LABEL = "Tool calls"
# The two flags, as words. "no" is a recorded fact, not a missing value -- the
# distinction DETAIL_PII_ABSENT_LABEL makes -- so a NULL flag (which the schema
# does not allow) would read as the absent mark, never as "no".
DETAIL_FLAG_YES_LABEL = "yes"
DETAIL_FLAG_NO_LABEL = "no"

# --- Summary figures -----------------------------------------------------
# Four ruled blocks: PRD-006 Section 6.1's three (the counts, the who/what
# facts, PII telemetry) and, since PRD-013, the token totals directly after the
# counts they measure in another unit. Headings, not card titles — the sheet has
# no cards.
SUMMARY_COUNTS_HEADING = "Traffic"
SUMMARY_TOKENS_HEADING = "Tokens"
SUMMARY_WHO_HEADING = "Who and what"
SUMMARY_PII_HEADING = "Personal data"

FIGURE_TOTAL_LABEL = "Queries recorded"
# Indented beneath the total on the sheet, because they are a subset of it.
FIGURE_BLOCKED_DUPLICATES_LABEL = "Held as duplicates"
FIGURE_BLOCKED_SUSPICIOUS_LABEL = "Denied on a pattern"
# PRD-013 (STORY-015): the verdict word the register stamps on these rows,
# beside "Denied on a pattern". A usage-limit row is one row of the table, so it
# is a subset of the total and indents with the other two.
FIGURE_BLOCKED_USAGE_LIMITS_LABEL = "Denied at a usage limit"

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
# PRD-013 (STORY-015): the Tokens block.
FIGURE_INPUT_TOKENS_LABEL = "Input tokens"
FIGURE_OUTPUT_TOKENS_LABEL = "Output tokens"

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

# --- Storage (PRD-018 STORY-012) -----------------------------------------
# The Storage view: the storage circuit breaker, the audit journal and the retry
# counters of the process serving this console. Plain words for what an operator
# controls and recognises (frontend-design). "Turned away", never the refusal
# word: GATE_REFUSED_MESSAGE must stay the only string that mentions one.
STORAGE_CAPTION_TEMPLATE = "This process: {instance}. Counters reset when it restarts."
STORAGE_VERDICT_CLOSED = "Storage is reachable."
STORAGE_VERDICT_OPEN_TEMPLATE = (
    "Storage circuit open since {since}. Requests are turned away for another "
    "{seconds} s."
)
STORAGE_VERDICT_HALF_OPEN_TEMPLATE = (
    "Storage circuit probing since {since}. One request is testing the database."
)
# Shown only while an entry is kept on disk that this process will not retry.
STORAGE_HELD_BACK_TEMPLATE = (
    "{entries} journal entries and {files} journal files are kept on disk and "
    "are not retried. An operator must look at them."
)
STORAGE_NO_JOURNAL = "No audit journal is open in this process."

STORAGE_HEADING_BREAKER = "Circuit breaker"
STORAGE_HEADING_JOURNAL = "Audit journal"
STORAGE_HEADING_COUNTERS = "Counters"
STORAGE_HEADING_RETRIES = "Retries"
STORAGE_HEADING_EXHAUSTED = "Gave up"
STORAGE_RETRIES_TITLE = "Retries made, by operation and failure class"
STORAGE_EXHAUSTED_TITLE = (
    "Operations that ended in an infrastructure failure, by operation and "
    "failure class, retries that were not allowed included"
)
STORAGE_KEYED_EMPTY = "None"

# PRD-018 STORY-012: "State" alone is quoted by a theme.GLOBAL_CSS comment,
# which tests/test_ground.py forbids for any label of five or more letters.
STORAGE_LABEL_STATE = "Breaker state"
STORAGE_LABEL_SINCE = "Since"
STORAGE_LABEL_FAILURES = "Consecutive failures"
STORAGE_LABEL_LAST_CLASS = "Last failure"
STORAGE_LABEL_ENTRIES = "Entries"
STORAGE_LABEL_SIZE = "Size"
STORAGE_LABEL_OLDEST = "Oldest entry"
STORAGE_LABEL_DRAINING = "Draining"
STORAGE_LABEL_ADOPTED = "Adopted files"
STORAGE_LABEL_HELD_ENTRIES = "Held back entries"
STORAGE_LABEL_HELD_FILES = "Held back files"
STORAGE_LABEL_BREAKER_OPENS = "Times the circuit opened"
STORAGE_LABEL_APPENDED = "Entries journaled"
STORAGE_LABEL_DRAINED = "Entries drained"
STORAGE_LABEL_TORN = "Torn entries discarded"
STORAGE_SIZE_TEMPLATE = "{used} of {limit} bytes"
STORAGE_YES = "yes"
STORAGE_NO = "no"

STORAGE_COLUMN_OPERATION = "Operation"
STORAGE_COLUMN_FAILURE_CLASS = "Class"
STORAGE_COLUMN_COUNT = "Count"

# --- Providers (PRD-022 STORY-016, F9) -----------------------------------
# The Providers view: one circuit breaker per upstream provider and the fallback
# counters of the process serving this console. Plain words, the Storage view's
# restraint. Only a failure kind or a skip reason is ever shown, never message
# text (PRD-022 T10).
PROVIDERS_CAPTION_TEMPLATE = (
    "This process: {instance}. Counters reset when it restarts."
)
PROVIDERS_VERDICT_ALL_CLOSED = "All providers are closed."
PROVIDERS_VERDICT_NONE = "No providers are configured."
PROVIDERS_VERDICT_NOT_CLOSED_TEMPLATE = "Not closed: {names}."

PROVIDERS_HEADING_COUNTERS = "Counters"
PROVIDERS_HEADING_FAILED = "Failed attempts"
PROVIDERS_HEADING_SKIPPED = "Skipped"
PROVIDERS_FAILED_TITLE = "Upstream attempts that failed, by provider and failure kind"
PROVIDERS_SKIPPED_TITLE = "Candidates passed over, by provider and reason"
PROVIDERS_KEYED_EMPTY = "None"

PROVIDERS_LABEL_STATE = "Breaker state"
PROVIDERS_LABEL_SINCE = "Since"
PROVIDERS_LABEL_FAILURES = "Consecutive failures"
PROVIDERS_LABEL_LAST_FAILURE = "Last failure"
PROVIDERS_LABEL_RETRY_AFTER = "Retry after"
PROVIDERS_LABEL_BREAKER_OPENS = "Times a circuit opened"
PROVIDERS_LABEL_FALLBACK_ANSWERS = "Answers from a fallback"
PROVIDERS_SECONDS_TEMPLATE = "{seconds} s"

PROVIDERS_COLUMN_PROVIDER = "Provider"
PROVIDERS_COLUMN_REASON = "Kind or reason"
PROVIDERS_COLUMN_COUNT = "Count"
