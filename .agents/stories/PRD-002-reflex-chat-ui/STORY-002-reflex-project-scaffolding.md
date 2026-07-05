---
id: STORY-002
prd: PRD-002
slug: reflex-project-scaffolding
title: "Reflex project scaffolding & dependency setup"
type: technical
priority: high
complexity: small
phase: "2 - Reflex scaffolding & single-process mount"
status: done
labels: [frontend, reflex, scaffolding]
epic_branch: epic/PRD-002-reflex-chat-ui
plan: .agents/plans/PRD-002-reflex-chat-ui/completed/STORY-002-reflex-project-scaffolding.plan.md
report: .agents/reports/PRD-002-reflex-chat-ui/STORY-002-reflex-project-scaffolding.report.md
commit: f669762
depends_on: [STORY-001]
blocks: [STORY-003]
skills: []
created: 2026-07-04
updated: 2026-07-04
---

# STORY-002: Reflex project scaffolding & dependency setup

## Description

As a devops engineer, I want a scaffolded Reflex project living alongside the existing FastAPI app, with `reflex` pinned in dependencies, so that later stories have a place to build the chat UI without touching PRD-001's existing `app/` tree (PRD Section 6, Section 8).

## Acceptance Criteria

- [ ] Given the project root, when scaffolding completes, then a `chat_ui/` directory exists with `rxconfig.py` and a `chat_ui/chat_ui/` package containing `chat_ui.py` (an `rx.App()` entrypoint that renders a placeholder page).
- [ ] Given `requirements.txt`, when dependencies are updated, then `reflex` is added and pinned to an exact version, per PRD Section 8's "pin an exact version in `requirements.txt`".
- [ ] Given a clean checkout with dependencies installed, when `reflex init` state is inspected (or `reflex run` is invoked in dev mode), then the app boots without errors and serves a placeholder page — this does not yet need to mount the FastAPI app (that is STORY-003).
- [ ] Given the new `chat_ui/` directory, when PRD-001's existing test suite runs, then it continues to pass unmodified — scaffolding introduces no changes to `app/`.
- [ ] Given the directory layout in PRD Section 6, when scaffolding completes, then it matches the suggested structure: `chat_ui/rxconfig.py`, `chat_ui/chat_ui/chat_ui.py`, `chat_ui/chat_ui/state.py` (stub), `chat_ui/chat_ui/components/` (empty or stub).

## Technical Notes

- Follow the suggested directory additions in PRD Section 6 exactly:
  ```
  chat_ui/
  ├── rxconfig.py
  ├── chat_ui/
  │   ├── chat_ui.py
  │   ├── state.py
  │   └── components/
  ```
- `rxconfig.py` will need `api_transformer` wired to `app.main:app` eventually, but this story only needs the Reflex project to boot standalone — the actual mount/verification against the existing FastAPI routes is STORY-003's job, to keep this story small and focused on scaffolding only.
- Per PRD Section 8 (Technology Stack), pin an exact Reflex version rather than a loose range, matching the existing `requirements.txt` convention (other deps are unpinned today, but PRD explicitly calls for pinning Reflex).
- `state.py` and `components/` can be empty stubs in this story; STORY-004 fills in the actual chat components and STORY-006 fills in `ChatState`.
- No changes to `app/` (PRD-001's existing tree) should be needed for this story — it is purely additive.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-003

## PRD Reference

Source: [`PRD-002/PRD.md`](../../PRDs/PRD-002-reflex-chat-ui/PRD.md) — Section 6 (Core Architecture & Patterns, suggested directory additions), Section 8 (Technology Stack), Section 12 Phase 2 (Reflex scaffolding & single-process mount)
