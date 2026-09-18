---
id: STORY-013
prd: PRD-010
slug: context-limit-bubble-and-trimmed-note
title: "Chat UI: context_limit bubble and 'earlier exchanges not sent' footer note"
type: feature
priority: medium
complexity: medium
phase: "3 - Chat sends history"
status: done
labels: [chat-ui, frontend, copy]
epic_branch: epic/PRD-010-multi-turn-pipeline
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-013-context-limit-bubble-and-trimmed-note.plan.md
report: .agents/reports/PRD-010-multi-turn-pipeline/STORY-013-context-limit-bubble-and-trimmed-note.report.md
commit: null
depends_on: [STORY-008, STORY-012]
blocks: [STORY-016]
skills: [frontend-design]
created: 2026-09-17
updated: 2026-09-18
---

# STORY-013: Chat UI: context_limit bubble and "earlier exchanges not sent" footer note

## Description

As an end user, I want to be told plainly when a chat is too long to send, and when earlier exchanges were left out of what the model saw, so that I know why the model forgot something and what to do about it.

## Acceptance Criteria

- [ ] Given `_do_send` receives a `QueryBlockedContextLimitResponse`, when it builds the bubble, then it appends `ChatMessage(kind="context_limit", content=result.reason, prompt=text, detail=<"characters 250113 of 200000" or "messages 101 of 100">)` through `_append_and_persist`. STORY-008's interim "Unhandled response type" test is replaced, and the new test asserts the kind and detail.
- [ ] Given a `context_limit` bubble (live or restored), when it renders via [chat_ui/chat_ui/components/bubbles.py](../../../chat_ui/chat_ui/components/bubbles.py), then it is a distinct `rx.match` arm that reuses the existing block-bubble geometry (rail cell + content column), with a tag and copy constants from [chat_ui/chat_ui/copy.py](../../../chat_ui/chat_ui/copy.py): body "This chat is too long to send." and direction "Start a new chat to continue." It does not fall through to the default arm.
- [ ] Given an assistant bubble with `history_trimmed > 0`, when its success metadata footer renders, then it includes a note built from a copy template, for example "3 earlier exchanges were not sent to the model" (singular "1 earlier exchange was not sent to the model"). With `history_trimmed == 0` the footer is byte-identical to today's (test in [tests/test_success_metadata_footer.py](../../../tests/test_success_metadata_footer.py)).
- [ ] Given the copy tests ([tests/test_copy.py](../../../tests/test_copy.py)) and contrast tests ([tests/test_contrast.py](../../../tests/test_contrast.py)), when this story lands, then the new constants are covered, the new copy contains no "context", "limit", "token" or apology wording, and any new ink/tint pair meets the existing contrast threshold.
- [ ] Given the app is run (`/run`), when a long chat is forced over a small monkeypatched limit, then a screenshot of the `context_limit` bubble and of a trimmed footer is attached to the story report, and [tests/test_render_invariants.py](../../../tests/test_render_invariants.py) is green.

## Technical Notes

- Work inside the existing register and bubble system (`theme.py`, `bubbles.py` "The six kinds" section). This is a new kind, not a new visual direction (PRD Section 8). No new animation; restored bubbles keep `restored=True` behaviour.
- Tag choice: follow `TAG_DUPLICATE = "HELD"` / `TAG_INJECTION = "DENIED"`. A plain verb-state such as `"TOO LONG"` fits. Colour: reuse a block tone rather than inventing one.
- Footer placement: after the existing metadata items, joined with `FOOTER_SEPARATOR`.
- `frontend-design` rules to apply verbatim:
  - "Write from the end user's side of the screen. Name things by what people control and recognize, never by how the system is built."
  - "Treat failure and emptiness as moments for direction, not mood. Explain what went wrong and how to fix it, in the interface's voice rather than a person's. Errors don't apologize, and they are never vague about what happened."
  - "Keep the register conversational and tuned: plain verbs, sentence case, no filler, with tone matched to the brand and the audience. Let each element do exactly one job."
  - "However, sometimes less is more, and extra animation contributes to the feeling that the design is AI-generated."
  - "Structure is information. Structural devices, numbering, eyebrows, dividers, labels, should encode something true about the content, not decorate it."
- Skills: frontend-design

## Dependencies

- **Blocked by**: STORY-008, STORY-012
- **Blocks**: STORY-016

## PRD Reference

Source: [`PRD-010-multi-turn-pipeline/PRD.md`](../../PRDs/PRD-010-multi-turn-pipeline/PRD.md) — sections 4 (Chat UI), 5 (story 2), 6.5, 7 (F6, F8), 8 (skill constraints), 11
