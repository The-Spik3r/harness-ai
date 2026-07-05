---
id: STORY-009
prd: PRD-002
slug: readme-chat-ui-docs
title: "README chat UI quickstart documentation"
type: technical
priority: low
complexity: small
phase: "5 - Docker packaging & docs"
status: done
labels: [docs]
epic_branch: epic/PRD-002-reflex-chat-ui
plan: .agents/plans/PRD-002-reflex-chat-ui/completed/STORY-009-readme-chat-ui-docs.plan.md
report: .agents/reports/PRD-002-reflex-chat-ui/STORY-009-readme-chat-ui-docs.report.md
commit: 5591895
depends_on: [STORY-008]
blocks: []
skills: []
created: 2026-07-04
updated: 2026-07-05
---

# STORY-009: README chat UI quickstart documentation

## Description

As an end user or devops engineer reading the project README, I want a "chat UI" quickstart section alongside the existing curl examples, so that I know a browser-based chat is available and how to reach it, without needing to reverse-engineer it from code (PRD Section 12 Phase 5).

## Acceptance Criteria

- [ ] Given `README.md`, when updated, then it includes a "Chat UI" section describing how to open the chat (e.g. `http://localhost:8000/` after `docker-compose up`), placed alongside the existing curl-based `/query` examples from PRD-001.
- [ ] Given the README's existing curl examples for `/query`, `/audit`, `/stats`, when reviewed after this update, then they remain unchanged and still accurate — this story only adds, does not rewrite, existing documentation.
- [ ] Given a new reader with no prior context, when they read the updated README, then they understand: (a) the chat UI and the REST API share one port, (b) the chat UI requires entering a `user_id` once per session, (c) blocked messages (duplicate/suspicious) render as distinct bubbles with an explanation.
- [ ] Given the MVP's explicit limitations, when documented, then the README notes the known out-of-scope items relevant to end users: no streaming, no persisted chat history, no login/auth beyond the `user_id` field.
- [ ] Given `docker-compose up -d --build` from a clean checkout, when the steps in the updated README are followed exactly, then both the chat UI and `GET /health` work as described — the README's instructions are verified accurate, not just written.

## Technical Notes

- Per PRD Section 12 Phase 5: "documentation updated... `README.md` updated with a 'chat UI' quickstart alongside the existing curl examples."
- Baseline to extend: [`README.md`](../../../README.md) (added in PRD-001 STORY-014) — add a new section rather than restructuring the existing one.
- Cross-reference PRD-002 Section 4 (Out of Scope) when documenting known MVP limitations, so the README doesn't imply capabilities (streaming, persisted history, full auth) that don't exist yet.
- This is the final story in the epic — after this lands, PRD-002's Section 11 "MVP definition of done" checklist should be fully satisfiable end-to-end.

## Dependencies

- **Blocked by**: STORY-008
- **Blocks**: None

## PRD Reference

Source: [`PRD-002/PRD.md`](../../PRDs/PRD-002-reflex-chat-ui/PRD.md) — Section 4 (Out of Scope), Section 12 Phase 5 (Docker packaging & docs)
