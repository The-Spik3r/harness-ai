---
story: STORY-008
prd: PRD-004
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-008-bubble-renderers-match-dispatch.plan.md
epic_branch: epic/PRD-004-chat-ui-redesign
commit: 1bc7b0c
status: COMPLETE
completed: 2026-08-21
---

# Implementation Report — STORY-008: Six bubble renderers dispatched by rx.match on kind

**Plan**: `.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-008-bubble-renderers-match-dispatch.plan.md`
**Epic Branch**: `epic/PRD-004-chat-ui-redesign`
**Commit**: `1bc7b0c`

## Summary

Created `chat_ui/chat_ui/components/bubbles.py` exposing six dedicated bubble renderers (`user`, `assistant`, `duplicate`, `injection`, `upstream_error`, `internal_error`) with zero hardcoded literals (using `chat_ui.copy`), and updated `chat_ui/chat_ui/components/chat.py` to dispatch via a single `rx.match(message.kind, ...)` replacing the legacy nested `rx.cond`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Create six bubble renderers module | `chat_ui/chat_ui/components/bubbles.py` | ✅ |
| 2 | Refactor chat dispatch to use `rx.match` on `message.kind` | `chat_ui/chat_ui/components/chat.py` | ✅ |
| 3 | Verify compilation and test suite execution | Test suite (`pytest`) | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Python module import (`chat_ui.components.bubbles`, `chat_ui.components.chat`) | ✅ |
| Tests | ✅ (213 passed, 0 failed) |

## Files Changed

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/components/bubbles.py` | CREATE | Define six outcome renderers and fallback |
| `chat_ui/chat_ui/components/chat.py` | UPDATE | Replace nested `rx.cond` with `rx.match` dispatch |

## Deviations from Plan

None. Implementation matched the plan exactly.

## Acceptance Criteria

- [x] Given `chat_ui/chat_ui/components/bubbles.py`, when it is created, then it exposes one renderer per `kind` — `user`, `assistant`, `duplicate`, `injection`, `upstream_error`, `internal_error` — and no two semantically different outcomes share a bubble style (PRD Section 11: "6 / 6 outcomes with a dedicated rendering").
- [x] Given `components/chat.py`, when a message is rendered, then dispatch is a single `rx.match` on `message.kind`, replacing the nested `rx.cond` over three roles.
- [x] Given a `duplicate` message, when rendered, then it uses benign-nudge styling; given an `injection` message, then it uses security-event styling and displays the matched `pattern` value.
- [x] Given an `upstream_error` message, when rendered, then it is an upstream-incident card that names OpenRouter as the failing party, visually distinct from the `internal_error` card.
- [x] Given any error card, when rendered, then it shows `detail`.
- [x] Given `rx.match` over `kind`, when an unknown kind value is encountered, then the default arm still renders a visible bubble rather than nothing.
- [x] All tasks completed.
