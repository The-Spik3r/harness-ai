---
id: STORY-019
prd: PRD-004
slug: six-outcome-regression-verification
title: "Six-outcome walkthrough and full-suite regression verification"
type: technical
priority: high
complexity: medium
phase: "4 - Shell, session, and recovery actions"
status: todo
labels: [tests, ui, verification]
epic_branch: epic/PRD-004-chat-ui-redesign
plan: null
report: null
commit: null
depends_on: [STORY-006, STORY-009, STORY-010, STORY-011, STORY-012, STORY-013, STORY-015, STORY-016, STORY-017, STORY-018]
blocks: []
skills: []
created: 2026-08-21
updated: 2026-08-21
---

# STORY-019: Six-outcome walkthrough and full-suite regression verification

## Description

As an integrating developer, I want the finished redesign verified against every MVP success criterion and proved to be confined to `chat_ui/`, so that the epic closes on evidence rather than on assumption (PRD Section 11, User Story 8).

## Acceptance Criteria

- [ ] Given the six pipeline outcomes, when each is exercised end to end, then each renders its own distinct treatment: a seeded duplicate; a prompt containing `override`; a prompt with an email address; an unset `OPENROUTER_API_KEY` for the upstream error; `PII_NLP_MODEL` set to a bogus value for `PiiRedactorError`; and a forced arbitrary exception for the catch-all (PRD Section 12 Phase 3 validation).
- [ ] Given the full repo test suite (PRD-001/002/003), when it runs, then it passes and `tests/test_chat_state.py` is the only test file whose diff is non-empty across the epic.
- [ ] Given `git diff main...epic/PRD-004-chat-ui-redesign -- app/`, when run, then it is empty — zero files modified under `app/` (PRD Section 11, Section 12 quality table).
- [ ] Given a chat-originated audit row from the walkthrough, when inspected, then `device` is non-null and `model_used` matches the model selected in the UI.
- [ ] Given each MVP "definition of done" checkbox in PRD Section 11, when the walkthrough concludes, then each is confirmed and recorded in the story report.

## Technical Notes

- No production code is expected here; if the walkthrough uncovers a defect, fix it in this story's commit and note it in the report.
- Quality indicators to record verbatim as the closing evidence (PRD Section 11): outcomes with a dedicated rendering 6/6; exception types with a handler 3 named + 1 catch-all; response contract fields consumed 6/6 (was 1/6); files modified under `app/` 0; existing test suites 100% passing, unmodified except `test_chat_state.py`; event-loop blocking during a request 0 ms.
- `tests/test_route_reservations.py` must still pass — this PRD adds no routes (PRD Section 9).
- The environment manipulations for the error walkthrough (`OPENROUTER_API_KEY`, `PII_NLP_MODEL`) are local and temporary; no `.env.example` or config change is in scope, since this PRD adds no environment variables (PRD Section 9).
- Run and inspect the app per `chat_ui/AGENTS.md` (verbatim): "When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill for the correct sequence and error investigation steps."

## Dependencies

- **Blocked by**: STORY-006, STORY-009, STORY-010, STORY-011, STORY-012, STORY-013, STORY-015, STORY-016, STORY-017, STORY-018
- **Blocks**: None

## PRD Reference

Source: [`PRD-004/PRD.md`](../../PRDs/PRD-004-chat-ui-redesign/PRD.md) — Section 11 (Success Criteria), Section 12 Phases 3 and 4, User Story 8
