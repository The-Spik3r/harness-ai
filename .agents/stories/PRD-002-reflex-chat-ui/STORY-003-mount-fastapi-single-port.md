---
id: STORY-003
prd: PRD-002
slug: mount-fastapi-single-port
title: "Mount existing FastAPI app into Reflex (single-port process)"
type: technical
priority: high
complexity: medium
phase: "2 - Reflex scaffolding & single-process mount"
status: todo
labels: [backend, reflex, integration]
epic_branch: epic/PRD-002-reflex-chat-ui
plan: null
report: null
commit: null
depends_on: [STORY-002]
blocks: [STORY-004]
skills: []
created: 2026-07-04
updated: 2026-07-04
---

# STORY-003: Mount existing FastAPI app into Reflex (single-port process)

## Description

As a devops engineer, I want Reflex to mount the existing `app/main.py` FastAPI instance via `api_transformer` and run in single-port production mode, so that the chat UI and the REST API are reachable on exactly one port with no second service or port to manage (PRD Section 4, User Story 4).

## Acceptance Criteria

- [ ] Given `chat_ui/rxconfig.py`, when `api_transformer` is configured, then it points at `app.main:app` (the existing FastAPI instance from PRD-001), per PRD Section 6's architecture diagram.
- [ ] Given the Reflex app runs with `REFLEX_ENV=prod` (single-port mode), when the process starts, then `GET /health`, `POST /query`, `GET /audit`, and `GET /stats` are all reachable on the same port the chat UI's frontend is served from — no second port is opened.
- [ ] Given Reflex's reserved routes (`/ping`, `/_event`, `/_upload` per PRD Section 9), when the mounted app's routes are enumerated, then none of PRD-001's existing routes (`/query`, `/audit`, `/stats`, `/health`) collide with them.
- [ ] Given the risk in PRD Section 14 Risk 2 (route collision), when the app starts up, then a startup-time or test-time assertion checks that no harness route collides with Reflex's reserved route list, so future route additions fail loudly instead of silently colliding.
- [ ] Given PRD-001's existing test suite (STORY-012), when it runs against the mounted app, then it passes unmodified — mounting introduces no behavior change to the existing REST endpoints.

## Technical Notes

- Per PRD Section 6: "Composition over new service: Reflex is *mounted into* the existing app (`api_transformer=app.main.app`), not the other way around — the FastAPI app remains the system of record; Reflex adds a UI layer on top."
- Per PRD Section 9: reserved routes `/ping`, `/_event`, `/_upload` must not collide with PRD-001's routes; add the assertion described in Risk 2's mitigation (Section 14) — a simple check at startup or in a test that diffs the harness's route table against the reserved list.
- Per PRD Section 12 Phase 2 validation: "`GET /health`, `POST /query`, `GET /audit`, `GET /stats` all still reachable on the same port Reflex serves its frontend from."
- New environment variable per PRD Section 9: `REFLEX_ENV=prod` for single-port production mode. `PORT`, `HOST`, `ADMIN_TOKEN`, `OPENROUTER_API_KEY`, `DATABASE_URL` are reused as-is from PRD-001 — no changes needed to those.
- This story is the integration point referenced in PRD Section 14 Risk 4 ("a bug or crash in the Reflex chat layer runs in the same process as the core API") — keep the mount configuration itself minimal and don't add chat logic here (that's STORY-004+).

## Dependencies

- **Blocked by**: STORY-002
- **Blocks**: STORY-004

## PRD Reference

Source: [`PRD-002/PRD.md`](../../PRDs/PRD-002-reflex-chat-ui/PRD.md) — Section 4 (User Story 4), Section 6 (Core Architecture & Patterns), Section 9 (Reflex reserved routes), Section 12 Phase 2, Section 14 Risk 2 & Risk 4
