"""Centralized user-facing copy and templates for chat_ui.

Per PRD-004 Section 4 and STORY-007, all user-facing strings, labels,
templates, and risk mitigations are centralized here.
"""

# Session / User ID Entry
USER_ID_PROMPT_TITLE = "Enter a user ID to start chatting"
USER_ID_PLACEHOLDER = "user_id"
USER_ID_SUBMIT_LABEL = "Continue"
USER_ID_VALIDATION_ERROR = "Please enter a user ID to continue"

# Shell Header & Navigation
SHELL_HEADER_TITLE = "Harness AI"
SHELL_HEADER_BADGE = "Enterprise Guardrail"
SHELL_USER_LABEL = "User"
SHELL_CHANGE_USER_LABEL = "Change user"
SHELL_MODEL_SLOT_LABEL = "Model: gpt-4"

# Empty State
EMPTY_STATE_TITLE = "Welcome to Harness AI"
EMPTY_STATE_SUBTITLE = "Ask questions, generate content, or analyze data safely. All prompts pass through enterprise PII protection, duplicate checking, and security guardrails."
EMPTY_STATE_PII_FEATURE = "PII Masking Active"
EMPTY_STATE_SECURITY_FEATURE = "Prompt Injection Defense"
EMPTY_STATE_DEDUP_FEATURE = "24h Query Deduplication"

# Composer & General UI
COMPOSER_PLACEHOLDER = "Message..."
PENDING_INDICATOR_TEXT = "Model is thinking..."

# Welcome Message
WELCOME_MESSAGE_CONTENT = "Hi! Type a message below and press send."

# Outcome / Bubble Labels & Templates
SUCCESS_ROLE_LABEL = "assistant"
USER_ROLE_LABEL = "user"

# PII Badge Template (Risk 5 mitigation: explicit that masking covers the whole exchange)
PII_BADGE_TEMPLATE = "{count} PII types masked in this exchange: {entities}"
PII_BADGE_SINGLE_TEMPLATE = "1 PII type masked in this exchange: {entities}"

# Success Metadata Footer
FOOTER_SEPARATOR = " · "
FOOTER_TOKENS_LABEL = "tokens"
FOOTER_AUDIT_PREFIX = "#"

# Recovery Actions (Retry & Edit-and-Resend)
RETRY_LABEL = "Retry"
EDIT_AND_RESEND_LABEL = "Edit and resend"
# Risk 4 mitigation: states text must change for resend to go through
DUPLICATE_CHANGE_NOTICE = "Original text restored. Modify text to go through."
DUPLICATE_RELATIVE_TIME_TEMPLATE = "Already sent {relative} ({absolute})"
DUPLICATE_WINDOW_RELEASE_TEMPLATE = "24h window releases at {release}"
DUPLICATE_FALLBACK_TEXT = "Already submitted recently."
DUPLICATE_UNPARSEABLE_TEMPLATE = "Already sent at {absolute}"

# Error / Block Cards
# Risk 7 mitigation: upstream error names OpenRouter explicitly
UPSTREAM_ERROR_PREFIX = "OpenRouter upstream error"
INTERNAL_ERROR_PREFIX = "Internal error"
