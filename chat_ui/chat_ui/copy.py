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
