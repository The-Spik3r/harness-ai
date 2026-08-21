---
id: STORY-004
prd: PRD-004
slug: chat-message-model
title: "ChatMessage typed model replaces list[dict[str, str]]"
type: technical
priority: high
complexity: medium
phase: "2 - Typed message model"
status: done
labels: [ui, reflex, state, model]
epic_branch: epic/PRD-004-chat-ui-redesign
plan: .agents/plans/PRD-004-chat-ui-redesign/STORY-004-chat-message-model.plan.md
report: null
commit: null
depends_on: [STORY-002]
blocks: [STORY-005, STORY-008]
skills: []
created: 2026-08-21
updated: 2026-08-21
---

# STORY-004: ChatMessage typed model replaces list[dict[str, str]]

## Description

As an integrating developer, I want chat messages to be a typed model with a `kind` discriminator, so that each pipeline outcome is distinguishable in state instead of being flattened into a formatted string (PRD Section 6, Section 12 Phase 2).

## Acceptance Criteria

- [ ] Given `chat_ui/chat_ui/models.py`, when it is created, then it defines `ChatMessage(rx.Base)` with exactly the fields listed in PRD Section 6: `kind`, `content`, `prompt`, `model_used`, `tokens_used`, `audit_id`, `pii_redacted`, `pii_entities`, `pattern`, `first_query_at`, `detail`, each with the defaults the PRD specifies.
- [ ] Given `ChatState.messages`, when inspected, then it is `list[ChatMessage]` and no longer `list[dict[str, str]]` ([state.py:26](../../../chat_ui/chat_ui/state.py)).
- [ ] Given each of the six outcomes, when `send()` appends its bubble, then `kind` is one of exactly `user`, `assistant`, `duplicate`, `injection`, `upstream_error`, `internal_error` — `OpenRouterError` maps to `upstream_error`; `PiiRedactorError`, `DuplicateCheckError` and the catch-all all map to `internal_error` (PRD Section 6 flow diagram).
- [ ] Given `components/chat.py`, when it renders, then it reads `ChatMessage` attributes instead of `message["role"]` / `message["content"]` and the app still compiles and renders all existing bubbles — full six-way redesign is [[STORY-008]].
- [ ] Given `app/`, when the diff is inspected, then no file under it is modified.

## Technical Notes

- New file `chat_ui/chat_ui/models.py`, exactly as specified in PRD Section 6:

  ```python
  class ChatMessage(rx.Base):
      kind: str
      content: str
      prompt: str = ""
      model_used: str = ""
      tokens_used: int = 0
      audit_id: int = 0
      pii_redacted: bool = False
      pii_entities: list[str] = []
      pattern: str = ""
      first_query_at: str = ""
      detail: str = ""
  ```

- This story is a pure data-model refactor: only `kind` and `content` need to be populated correctly here; filling in the metadata fields per result type is [[STORY-005]].
- `WELCOME_MESSAGE` at [state.py:8-11](../../../chat_ui/chat_ui/state.py) is a `dict` — convert it to a `ChatMessage` for now; its replacement by an empty state is [[STORY-014]].
- `rx.Base` and `rx.foreach` over a typed model list have specific Var-access rules — per `chat_ui/AGENTS.md` (verbatim): "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs."
- `tests/test_chat_state.py` asserts exact dict equality on bubbles (lines 181-210) and will break here; keep it compiling with minimal edits, and migrate it properly in [[STORY-006]] (Risk 1).

## Dependencies

- **Blocked by**: STORY-002
- **Blocks**: STORY-005, STORY-008

## PRD Reference

Source: [`PRD-004/PRD.md`](../../PRDs/PRD-004-chat-ui-redesign/PRD.md) — Section 4 (Message model & rendering), Section 6 (message model), Section 12 Phase 2
