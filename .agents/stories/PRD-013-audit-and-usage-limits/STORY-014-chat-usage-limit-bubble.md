---
id: STORY-014
prd: PRD-013
slug: chat-usage-limit-bubble
title: "Chat UI usage-limit bubble"
type: feature
priority: medium
complexity: medium
phase: "3 - Enforcement"
status: todo
labels: [frontend, chat-ui]
epic_branch: epic/PRD-013-audit-and-usage-limits
plan: null
report: null
commit: null
depends_on: [STORY-011]
blocks: [STORY-018]
skills: [frontend-design]
created: 2026-10-04
updated: 2026-10-04
---

# STORY-014: Chat UI usage-limit bubble

## Description

As an end user, I want to be told plainly when I have reached a usage limit and when I can send again, so that I do not keep retrying.

## Acceptance Criteria

- [ ] Given a send refused with `limit="tokens"`, when the result arrives, then the thread shows one bubble reading "You've reached today's usage limit. You can send again after 00:00 UTC."; given `limit="requests"`, then it reads "You're sending too fast. Wait a minute, then send again."
- [ ] Given either bubble in a saved chat, when the page is reloaded and the chat reopened, then the same bubble is restored with the same text.
- [ ] Given a chat containing a usage-limit bubble, when the next send assembles history, then neither the bubble nor the user turn that caused it is sent to the model.
- [ ] Given `UsageLimitError` raised during a send, when it is handled, then the thread shows the existing internal-error bubble and `pending` is cleared.
- [ ] Given the bubble's rendered copy, when `tests/test_copy.py` and the render-invariant tests run, then the strings contain no "rate limit", "quota exceeded", "sorry" or "oops", and the temporary routing STORY-011 added is gone.

## Technical Notes

- `frontend-design`, verbatim: *"Write from the end user's side of the screen. Name things by what people control and recognize, never by how the system is built."* and *"Treat failure and emptiness as moments for direction, not mood. Explain what went wrong and how to fix it, in the interface's voice rather than a person's. Errors don't apologize, and they are never vague about what happened."* The copy in the first criterion is written to these rules: it says what happened and when the person can continue, in their terms, without an apology.
- Follow the existing bubble system and theme (`components/bubbles.py`, `theme.py`). This is one more arm of the existing `rx.match`, styled like the other refusal bubbles; it is not a new visual direction.
- Add a `usage_limit` kind to `chat_ui/chat_ui/models.py`, the copy to `copy.py`, the branch in `state.py`'s `_do_send`, and persistence through `_append_and_persist` and the stored-message mappers. `tests/test_context_limit_bubble.py` is the closest precedent.
- Format `resets_at` in Python when the bubble is built, not at render: components receive Vars, so datetime work cannot run there (see the note at the top of `admin_models.py`). Store the finished sentence, or the limit plus the formatted time, in existing `StoredMessage` columns (`detail` is free for refusal bubbles); do not add a column.
- `chat_history.assemble` reads only `assistant` rows, so the third criterion holds by construction; the test proves it.
- New file `tests/test_usage_bubble.py`.

## Dependencies

- **Blocked by**: STORY-011
- **Blocks**: STORY-018

## PRD Reference

Source: [`PRD-013-audit-and-usage-limits/PRD.md`](../../PRDs/PRD-013-audit-and-usage-limits/PRD.md) — sections 5 (story 8), 6.10, 7 (F14), 11 (Surfaces)
