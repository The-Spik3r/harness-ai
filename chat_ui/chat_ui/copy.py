"""Centralized user-facing copy and templates for chat_ui.

Per PRD-004 Section 4 and STORY-007, every user-facing string, label and
template lives here, so changing the display language is a single-file edit.

Voice: the interface states what happened and what to do next. It does not
apologize, it does not hedge, and it never describes itself in terms of how it
is built. Verdict tags are the interface's vocabulary — the tag on a bubble,
the word in the copy below it, and the label on its button all agree.
"""

# --- Session gate --------------------------------------------------------
LOGIN_PROMPT_TITLE = "Sign in"
LOGIN_PROMPT_BODY = (
    "Every prompt is recorded against your identity. Enter your access "
    "token to start the session."
)
LOGIN_TOKEN_PLACEHOLDER = "Access token"
LOGIN_SUBMIT_LABEL = "Sign in"
LOGIN_TOKEN_REQUIRED_ERROR = "Enter a token to sign in."
LOGIN_INVALID_TOKEN_ERROR = "Invalid or deactivated token."
# A credential can go bad mid-session (deactivated by an admin while the tab
# stays open). send() re-resolves on every call and surfaces this rather
# than silently keep using a role that no longer exists.
SESSION_INVALIDATED_ERROR = (
    "Your session credential is no longer valid. Sign out and sign in again."
)

# --- Header --------------------------------------------------------------
SHELL_HEADER_TITLE = "HARNESS"
SHELL_HEADER_BADGE = "Inspecting"
SHELL_USER_LABEL = "Sending as"
SHELL_LOGOUT_LABEL = "Sign out"
SHELL_MODEL_SLOT_LABEL = "Model"

# --- Empty state ---------------------------------------------------------
# An empty screen is an invitation to act, and here it is also the legend for
# the rail the transcript is about to fill.
EMPTY_STATE_TITLE = "Nothing sent yet."
EMPTY_STATE_SUBTITLE = (
    "Write below and the harness inspects the prompt before it reaches the "
    "model. Whatever it decides, you see it on the rail."
)
EMPTY_STATE_PII_FEATURE = "Personal data is masked, never blocked"
EMPTY_STATE_SECURITY_FEATURE = "Injection attempts are denied and logged"
EMPTY_STATE_DEDUP_FEATURE = "A repeat within 24 hours is held"

# --- Composer ------------------------------------------------------------
COMPOSER_PLACEHOLDER = "Message..."
COMPOSER_SEND_LABEL = "Send"
PENDING_INDICATOR_TEXT = "Waiting on the model"
PENDING_TAG = "SENDING"

# --- Verdict tags --------------------------------------------------------
# One tag per pipeline outcome, in the rail's own vocabulary.
TAG_USER = "YOU"
TAG_ASSISTANT = "CLEARED"
TAG_DUPLICATE = "HELD"
TAG_INJECTION = "DENIED"
TAG_FORBIDDEN = "FORBIDDEN"
TAG_UPSTREAM = "UPSTREAM"
TAG_INTERNAL = "FAULT"
TAG_UNKNOWN = "LOGGED"

SUCCESS_ROLE_LABEL = "assistant"
USER_ROLE_LABEL = "user"
WELCOME_MESSAGE_CONTENT = "Write below and the harness inspects the prompt before it reaches the model."

# --- PII badge -----------------------------------------------------------
# Risk 5: the badge covers the whole exchange, because run_query(...) returns
# the union of input and output entities. The copy says so rather than letting
# the reader assume it means their prompt alone.
PII_BADGE_TEMPLATE = "{count} PII types masked in this exchange: {entities}"
PII_BADGE_SINGLE_TEMPLATE = "1 PII type masked in this exchange: {entities}"

# --- Success footer ------------------------------------------------------
FOOTER_SEPARATOR = " · "
FOOTER_TOKENS_LABEL = "tokens"
FOOTER_AUDIT_PREFIX = "#"

# --- Recovery actions ----------------------------------------------------
RETRY_LABEL = "Retry"
EDIT_AND_RESEND_LABEL = "Edit and resend"
# Risk 4: resending the same text is blocked again, so the copy names the one
# thing that makes the action work.
DUPLICATE_CHANGE_NOTICE = "Change the wording before you send it again."
DUPLICATE_RELATIVE_TIME_TEMPLATE = "Already sent {relative} ({absolute})"
DUPLICATE_WINDOW_RELEASE_TEMPLATE = "24h window releases at {release}"
DUPLICATE_FALLBACK_TEXT = "Already submitted recently."
DUPLICATE_UNPARSEABLE_TEMPLATE = "Already sent at {absolute}"

# --- Block and failure cards --------------------------------------------
INJECTION_PATTERN_LABEL = "Matched pattern"
INJECTION_NO_PATTERN = "This prompt matched a prompt-injection rule."
FORBIDDEN_PERMISSION_LABEL = "Required permission"

# Risk 7: the upstream card names OpenRouter, so a model the key cannot reach
# does not read as "the harness is broken".
UPSTREAM_ERROR_PREFIX = "OpenRouter did not answer"
UPSTREAM_ERROR_HEADLINE = "OpenRouter did not answer."
INTERNAL_ERROR_PREFIX = "The harness failed before the model"
INTERNAL_ERROR_HEADLINE = "The harness failed before reaching the model."
DETAIL_LABEL = "Detail"

# --- Session fallbacks ---------------------------------------------------
# The two strings a session row falls back to. Both are failures of the
# *input*, not of the reader, so neither apologizes and neither explains the
# mechanism: a blank row in the rail is unclickable and unnameable, and that
# is the whole problem being solved. The rail's own strings are STORY-017's.
SESSION_UNTITLED_TITLE = "Untitled chat"
# The counterpart of DUPLICATE_UNPARSEABLE_TEMPLATE above: a timestamp that
# will not parse costs the relative reading, not the row.
SESSION_ACTIVITY_UNKNOWN = "no recent activity"

# --- Session deletion ----------------------------------------------------
# STORY-016 owns the delete flow, so its two words live here; the rest of the
# rail's strings -- the New chat label, the empty-rail invitation, the read
# failure line, the rename affordance -- are STORY-017's, exactly as the
# Session fallbacks block above says. Two stories cannot both write one
# constant, and this is the one STORY-016's own AC requires.
#
# PRD-008 Section 9 is the source and governs the second sentence: "`audit_logs`
# is append-only and stays so... The confirmation copy says this in the user's
# words." So the promise is made in what the reader controls and recognizes --
# the chat goes, the record of what was checked stays -- and never in the
# schema's terms (frontend-design: "Name things by what people control and
# recognize, never by how the system is built").
#
# One `{title}` placeholder, the shape PII_BADGE_TEMPLATE above already uses:
# STORY-018 formats it per row inside an `rx.foreach`, and a Reflex Var
# interpolates through `str.format` into the same Var-embedded string an
# f-string produces.
SESSION_DELETE_CONFIRM_TEMPLATE = (
    "Delete “{title}”? The chat and its messages go for good. The record of "
    "what was checked is kept."
)
# The action keeps its name through the whole flow (frontend-design: "the
# button that says 'Publish' produces a toast that says 'Published'"), so the
# affordance, this confirmation and nothing else all say Delete. Not Remove.
SESSION_DELETE_CONFIRM_LABEL = "Delete"

# --- Transcript persistence ----------------------------------------------
# PRD-008 Risk 5: the model answered and the audit row is already written --
# only the saving failed, and the notice says exactly that much. It names the
# consequence the reader can act on (the turn is here until they reload)
# rather than the mechanism that produced it, and it does not apologize
# (frontend-design: "errors don't apologize, and they are never vague about
# what happened").
TRANSCRIPT_NOT_SAVED_NOTICE = (
    "This turn was not saved to your history. It stays on screen until you "
    "reload the page."
)
# The counterpart for a failed touch, and deliberately a different string.
# The write landed; only the ordering did not. Saying "not saved" here would
# be false, and STORY-014 AC 6 is explicit that a failed reorder "must not
# surface as a lost turn".
SESSION_ORDER_STALE_NOTICE = (
    "This chat is saved. The list order is out of date until you reload."
)
# The read counterpart of TRANSCRIPT_NOT_SAVED_NOTICE above. STORY-015 AC 9
# requires the transcript on screen to be left alone when a load fails, so the
# notice must say that the *previous* conversation is what the reader is still
# looking at -- a bare "could not load" would leave them unsure which chat the
# bubbles belong to. Names the consequence, not the mechanism, and does not
# apologize.
TRANSCRIPT_NOT_LOADED_NOTICE = (
    "This chat could not be loaded. The conversation on screen is unchanged."
)
