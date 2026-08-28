---
id: STORY-008
prd: PRD-004
slug: bubble-renderers-match-dispatch
title: "Six bubble renderers dispatched by rx.match on kind"
type: feature
priority: high
complexity: large
phase: "3 - Bubble redesign & PII badge"
status: done
labels: [ui, reflex, components]
epic_branch: epic/PRD-004-chat-ui-redesign
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-008-bubble-renderers-match-dispatch.plan.md
report: .agents/reports/PRD-004-chat-ui-redesign/STORY-008-bubble-renderers-match-dispatch.report.md
commit: 1bc7b0c
depends_on: [STORY-004, STORY-007]
blocks: [STORY-009, STORY-010, STORY-011, STORY-012, STORY-013, STORY-014, STORY-018]
skills: []
created: 2026-08-21
updated: 2026-08-21
---

# STORY-008: Six bubble renderers dispatched by rx.match on kind

## Description

As an end user, I want a duplicate block, an injection block, an upstream failure and an internal failure to look different from each other, so that I can tell "you already asked this" apart from "this was logged as a security event" and from "the provider is down" (PRD User Story 2, Section 2 "Every outcome is visible").

## Acceptance Criteria

- [x] Given `chat_ui/chat_ui/components/bubbles.py`, when it is created, then it exposes one renderer per `kind` — `user`, `assistant`, `duplicate`, `injection`, `upstream_error`, `internal_error` — and no two semantically different outcomes share a bubble style (PRD Section 11: "6 / 6 outcomes with a dedicated rendering").
- [x] Given `components/chat.py`, when a message is rendered, then dispatch is a single `rx.match` on `message.kind`, replacing the nested `rx.cond` over three roles at [chat.py:8-51](../../../chat_ui/chat_ui/components/chat.py), so a seventh outcome later is one new arm rather than another nesting level.
- [x] Given a `duplicate` message, when rendered, then it uses benign-nudge styling; given an `injection` message, then it uses security-event styling and displays the matched `pattern` value — the two must be visually distinct, not today's shared amber bubble.
- [x] Given an `upstream_error` message, when rendered, then it is an upstream-incident card that names OpenRouter as the failing party, visually distinct from the `internal_error` card (Risk 7).
- [x] Given any error card, when rendered, then it shows `detail` (the exception text) — the same strings `POST /query` already returns in its HTTP 500/502 `detail` field, so no new disclosure is introduced (PRD Section 9).
- [x] Given `rx.match` over `kind`, when an unknown kind value is encountered, then the default arm still renders a visible bubble rather than nothing.

## Technical Notes

- New file `chat_ui/chat_ui/components/bubbles.py`; `components/chat.py` becomes dispatch plus composer, per the file map in PRD Section 6.
- All display strings come from [[STORY-007]]'s `chat_ui/chat_ui/copy.py` — no literals in this module.
- PRD Section 6, "Discriminated union rendering": "one `rx.match` on `kind` dispatching to six renderers, replacing today's nested `rx.cond` on three roles (`components/chat.py:8-51`). Adding a seventh outcome later becomes one new arm, not another nesting level."
- Scope boundaries: the PII badge is [[STORY-009]], the success footer is [[STORY-010]], duplicate relative-time formatting is [[STORY-011]], the retry/edit-and-resend buttons are [[STORY-018]]. This story renders the six shells and the injection `pattern`, leaving hook points for those.
- `rx.match` semantics over a state Var and `rx.Base` attribute access in `rx.foreach` must be confirmed against the docs — per `chat_ui/AGENTS.md` (verbatim): "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs."
- Verify by compiling and running per `chat_ui/AGENTS.md` (verbatim): "When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill for the correct sequence and error investigation steps."
- Manual check for the injection arm: a prompt containing `override` returns `pattern == "override"` (PRD Section 12 Phase 3 validation).

## Dependencies

- **Blocked by**: STORY-004, STORY-007
- **Blocks**: STORY-009, STORY-010, STORY-011, STORY-012, STORY-013, STORY-014, STORY-018

## PRD Reference

Source: [`PRD-004/PRD.md`](../../PRDs/PRD-004-chat-ui-redesign/PRD.md) — Section 4 (Message model & rendering), Section 6 (patterns, file map), Section 11, Section 12 Phase 3, User Story 2, Risk 7
