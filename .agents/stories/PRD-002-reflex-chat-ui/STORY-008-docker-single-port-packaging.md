---
id: STORY-008
prd: PRD-002
slug: docker-single-port-packaging
title: "Multi-stage Docker packaging for single-port image"
type: technical
priority: medium
complexity: medium
phase: "5 - Docker packaging & docs"
status: done
labels: [devops, docker]
epic_branch: epic/PRD-002-reflex-chat-ui
plan: .agents/plans/PRD-002-reflex-chat-ui/completed/STORY-008-docker-single-port-packaging.plan.md
report: .agents/reports/PRD-002-reflex-chat-ui/STORY-008-docker-single-port-packaging.report.md
commit: 75e5ad6
depends_on: [STORY-007]
blocks: [STORY-009]
skills: []
created: 2026-07-04
updated: 2026-07-05
---

# STORY-008: Multi-stage Docker packaging for single-port image

## Description

As a devops engineer, I want the chat UI and API packaged into one Docker image behind one port via a multi-stage build, so that `docker-compose up` keeps working exactly as it does today, with no new exposed ports or Node/Bun runtime shipped in the final image (PRD Section 4, User Story 4).

## Acceptance Criteria

- [ ] Given the updated `Dockerfile`, when built, then it uses a multi-stage build: a Node.js/Bun stage compiles the Reflex frontend's static assets, and the final runtime stage is Python-only (no Node/Bun binaries present in the final image).
- [ ] Given `docker-compose up -d --build` is run from a clean checkout, when the container starts, then exactly one port is exposed (the existing `PORT` env var, unchanged from PRD-001) and no new service or port mapping is added to `docker-compose.yml`.
- [ ] Given the running container, when `curl http://localhost:8000/health` is called, then it returns the existing healthy response, and opening `http://localhost:8000/` in a browser shows the working chat UI — both against the same running process.
- [ ] Given the running container, when `POST /query`, `GET /audit`, and `GET /stats` are called, then they behave exactly as PRD-001 specifies, unchanged.
- [ ] Given the final built image, when its layers/filesystem are inspected, then no Node or Bun runtime is present — only the compiled static frontend assets and the Python runtime.
- [ ] Given `REFLEX_ENV=prod` (from STORY-003), when the container runs, then it is set appropriately in the Dockerfile/compose so the app boots in single-port production mode without manual intervention.

## Technical Notes

- Current baseline to modify: [`Dockerfile`](../../../Dockerfile) (currently a single-stage `python:3.11-slim` build running `python app.py`) and [`docker-compose.yml`](../../../docker-compose.yml) (currently one service, one port mapping via `${PORT:-8000}`) — both must be extended, not replaced wholesale, preserving the existing `PORT`/`DATABASE_URL`/env-file conventions.
- Per PRD Section 14 Risk 1: "Use a multi-stage Dockerfile — the Node/Bun stage compiles static frontend assets only; the final runtime image is Python-only, matching PRD-001's existing image profile."
- Per PRD Section 11 (Success Criteria): "Final Docker image does not ship a Node/Bun runtime (multi-stage build discards the frontend build stage)" and "Additional exposed ports: 0 (stays at 1)".
- Per PRD Section 12 Phase 5: "multi-stage `Dockerfile` (Node/Bun build stage discarded in final image), updated `docker-compose.yml` (if needed)." Validation: `docker-compose up -d --build` then both `curl http://localhost:8000/health` and opening `http://localhost:8000/` succeed from a clean build.
- The CMD/entrypoint will need to launch Reflex in `--env prod` single-port mode rather than the current `python app.py`/uvicorn-only invocation — confirm this doesn't regress `GET /health` or any existing route.

## Dependencies

- **Blocked by**: STORY-007
- **Blocks**: STORY-009

## PRD Reference

Source: [`PRD-002/PRD.md`](../../PRDs/PRD-002-reflex-chat-ui/PRD.md) — Section 4 (User Story 4), Section 11 (Success Criteria), Section 12 Phase 5 (Docker packaging & docs), Section 14 Risk 1
