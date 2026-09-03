---
id: STORY-012
prd: PRD-008
slug: session-summary-and-formatting
title: "ChatSessionSummary plus auto-title derivation and relative activity time in formatting.py"
type: feature
priority: high
complexity: small
phase: "3 - State and restore"
status: todo
labels: [ui, reflex, models, formatting]
epic_branch: epic/PRD-008-chat-sessions
plan: null
report: null
commit: null
depends_on: []
blocks: [STORY-013, STORY-018]
skills: [reflex-docs]
created: 2026-09-02
updated: 2026-09-02
---

# STORY-012: ChatSessionSummary plus auto-title derivation and relative activity time in formatting.py

## Description

As an employee, I want my chats named by what they are about, so that a list of eleven conversations is scannable rather than eleven timestamps (PRD Section 5, story 3).

## Acceptance Criteria

- [ ] Given [chat_ui/chat_ui/models.py](../../../chat_ui/chat_ui/models.py), when it is read, then `ChatSessionSummary` declares `session_id`, `title`, `activity_info` and nothing else — no message count, no model, no verdict summary.
- [ ] Given [chat_ui/chat_ui/formatting.py](../../../chat_ui/chat_ui/formatting.py), when `derive_title(prompt)` is called, then it returns the prompt truncated at a **word boundary**, never mid-word, with an ellipsis only when it actually truncated.
- [ ] Given a prompt shorter than the cap, when `derive_title` runs, then it returns the prompt unchanged with no ellipsis.
- [ ] Given a prompt that is one very long unbroken token, when `derive_title` runs, then it truncates at the cap rather than returning the whole token or an empty string — the case a naive `rsplit(" ", 1)` returns empty for.
- [ ] Given a prompt that is only whitespace, when `derive_title` runs, then it returns a copy-module fallback string rather than an empty title. A blank row in the rail is unclickable and unnameable.
- [ ] Given `format_activity(updated_at)`, when it is called, then it returns a relative string ("2m ago", "yesterday", "3 days ago") computed against `datetime.now(timezone.utc)`.
- [ ] Given an `updated_at` that does not parse, when `format_activity` runs, then it returns a fallback rather than raising — the precedent `format_duplicate_info` already set with `DUPLICATE_UNPARSEABLE_TEMPLATE`.
- [ ] Given [tests/test_copy.py](../../../tests/test_copy.py) and a new formatting test, when they run, then both functions are covered including all four edge cases above.

## Technical Notes

- Files: [chat_ui/chat_ui/models.py](../../../chat_ui/chat_ui/models.py), [chat_ui/chat_ui/formatting.py](../../../chat_ui/chat_ui/formatting.py), [chat_ui/chat_ui/copy.py](../../../chat_ui/chat_ui/copy.py) (fallback strings only — the rail's own strings land in [[STORY-017]]).
- **Both functions run in the backend, never at render.** The rule is already written into [chat_ui/chat_ui/models.py](../../../chat_ui/chat_ui/models.py)'s comment on the duplicate fields, verbatim: "Humanized duplicate copy, precomputed in the backend: component functions only ever see Vars, so datetime math cannot run at render." `activity_info` is a precomputed string on the summary for exactly that reason.
- This is also why `activity_info` is a field rather than a computed property: PRD-006 established the derived-once row model — "Components read fields; they do not compute."
- `format_activity` recomputes on every load and is never stored. PRD Section 6 says why for the duplicate copy, and the same reasoning governs here: a stored "2m ago" is wrong the moment it is read back.
- Per `chat_ui/AGENTS.md`, verbatim: "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs." That governs the `pydantic.BaseModel` / `rx.Base` choice for `ChatSessionSummary` — follow whatever [chat_ui/chat_ui/models.py](../../../chat_ui/chat_ui/models.py)'s `ChatMessage` already does rather than introducing a second convention.
- PRD Section 6.1 fixes the field list, verbatim: "Every session row carries a relative activity time and nothing else — no message count, no model, no verdict summary... a figure belongs in the rail only if the reader needs it to choose a row, and they do not."
- The rename in [[STORY-016]] must not re-derive the title. Nothing in this story caches the derivation; `derive_title` is called once, by [[STORY-006]]'s `create`, and never again for that session.
- `.agents/skills/` was scanned: `frontend-design` applies to the rail's visual design, which is [[STORY-017]] and [[STORY-018]]. This story produces no rendered output, so only the Reflex API rule above applies.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-013, STORY-018

## PRD Reference

Source: [`PRD-008/PRD.md`](../../PRDs/PRD-008-chat-sessions/PRD.md) — Section 4 (Chat state), Section 5 (story 3), Section 6.1 (metadata in the rail), Section 7, Section 12 Phase 3
