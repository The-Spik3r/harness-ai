---
id: STORY-001
prd: PRD-001
slug: project-scaffolding
title: Project scaffolding & configuration loading
type: technical
priority: high
complexity: small
phase: "1 - Setup"
status: done
labels: [backend, infra]
epic_branch: epic/PRD-001-harness-ia
plan: .agents/plans/PRD-001-harness-ia/completed/STORY-001-project-scaffolding.plan.md
report: .agents/reports/PRD-001-harness-ia/STORY-001-project-scaffolding.report.md
commit: d94c67a
depends_on: []
blocks: [STORY-002, STORY-003, STORY-009]
skills: []
created: 2026-07-04
updated: 2026-07-04
---

# STORY-001: Project scaffolding & configuration loading

## Description

As an integrating developer, I want a bootable FastAPI project skeleton with environment-variable-driven configuration, so that every later story has a consistent app entrypoint and settings object to build on.

## Acceptance Criteria

- [x] Given a fresh checkout, when I run `python app.py`, then a FastAPI app starts on `HOST`/`PORT` from env vars (defaulting per Section 9 of the PRD).
- [x] Given no `.env` file, when the app starts, then it fails fast with a clear error only if a required var (e.g. `OPENROUTER_API_KEY`) is missing — optional vars fall back to documented defaults.
- [x] Given the `config.py` settings object, when imported from any module, then all env vars from PRD Section 9 (`OPENROUTER_API_KEY`, `DATABASE_URL`, `PORT`, `HOST`, `ADMIN_TOKEN`, `LOG_LEVEL`) are exposed as typed attributes.
- [x] Given `requirements.txt`, when installed in a clean virtualenv, then the app starts with no missing-dependency errors.

## Technical Notes

- Create `app/main.py` (FastAPI app + router registration placeholder) and `app/config.py` (Pydantic `Settings` loading from env, per PRD Section 8/9).
- Use `python-dotenv` or Pydantic's built-in `.env` support for local dev parity with Docker.
- `requirements.txt` per PRD Section 8: `fastapi`, `uvicorn[standard]`, `pydantic`, `httpx`, `python-dotenv`, `pytest`, `pytest-asyncio`.
- This story only stands up the skeleton — no routes with real logic yet.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-002, STORY-003, STORY-009

## PRD Reference

Source: [`PRD-001/PRD.md`](../../PRDs/PRD-001-harness-ia/PRD.md) — Section 6 (Core Architecture), Section 8 (Technology Stack), Section 12 (Phase 1)
