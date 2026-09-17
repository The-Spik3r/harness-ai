---
id: STORY-018
prd: PRD-010
slug: readme-and-env-documentation
title: "README: multi-turn context shipped, limits and trade-offs; .env.example settings"
type: technical
priority: medium
complexity: small
phase: "4 - Prove and document"
status: todo
labels: [docs]
epic_branch: epic/PRD-010-multi-turn-pipeline
plan: null
report: null
commit: null
depends_on: [STORY-014, STORY-015, STORY-016, STORY-017]
blocks: []
skills: []
created: 2026-09-17
updated: 2026-09-17
---

# STORY-018: README: multi-turn context shipped, limits and trade-offs; .env.example settings

## Description

As a reader of the README, I want to know that chats are now conversations, what the model sees, what it doesn't, and which settings control it, so that the documented behaviour matches the shipped one.

## Acceptance Criteria

- [ ] Given [README.md](../../../README.md), when read, then *Multi-turn context* moves from the roadmap (the unchecked item and the "intended direction" section) to shipped behaviour describing: history comes only from answered exchanges; history is always redacted; the oldest exchanges are dropped when a chat exceeds the limits, with a note on the reply; the pipeline refuses oversized conversations; `CHAT_HISTORY_ENABLED=false` keeps single-turn.
- [ ] Given the *Limitations* section, when read, then "No multi-turn context" is removed, and it states: limits are characters, not tokens; patterns inspect only the newest user turn (provisional until PRD-011); PII audit fields describe the new turn and output only (D7); the first send of two new chats with the same text within 24 h is still a duplicate; redacted history can make answers less precise.
- [ ] Given `POST /query` documentation, when read, then the context-limit `BLOCKED` body is shown, with the note that it is the only new outcome, and the configuration table lists `OPENROUTER_TIMEOUT_SECONDS`, `CONTEXT_MAX_MESSAGES`, `CONTEXT_MAX_CHARACTERS` and `PIPELINE_MAX_WORKERS` with defaults and purpose.
- [ ] Given [.env.example](../../../.env.example), when read, then the four settings appear with their defaults and one-line comments, in a `# Multi-turn pipeline (PRD-010)` group.
- [ ] Given [pre-prds/PRE-PRD-010-multi-turn-pipeline.md](../../../pre-prds/PRE-PRD-010-multi-turn-pipeline.md), when read, then `status: promoted` and `prd:` point at this PRD (already set at PRD creation; verify). Every new or changed README anchor link resolves.

## Technical Notes

- Record the STORY-015 latency numbers in one sentence where the README discusses cost, and the STORY-014 result where it discusses the executor.
- Update the *OpenAI-compatible endpoint* section only where it now references shipped behaviour (the pipeline accepts messages internally; no HTTP ingress yet). Do not describe PRD-014 as shipped.
- Match the README's existing voice and heading structure (PRD-009 STORY-010 is the precedent).
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-014, STORY-015, STORY-016, STORY-017
- **Blocks**: None

## PRD Reference

Source: [`PRD-010-multi-turn-pipeline/PRD.md`](../../PRDs/PRD-010-multi-turn-pipeline/PRD.md) — sections 7 (F9), 9.3, 10, 15 (Refinement of the brief's criterion)
