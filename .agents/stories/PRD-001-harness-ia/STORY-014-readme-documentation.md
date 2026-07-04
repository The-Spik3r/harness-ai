---
id: STORY-014
prd: PRD-001
slug: readme-documentation
title: README & usage documentation
type: technical
priority: low
complexity: small
phase: "5 - Docker & Documentation"
status: done
labels: [docs]
epic_branch: epic/PRD-001-harness-ia
plan: .agents/plans/PRD-001-harness-ia/completed/STORY-014-readme-documentation.plan.md
report: .agents/reports/PRD-001-harness-ia/STORY-014-readme-documentation.report.md
commit: 8c59001
depends_on: [STORY-013]
blocks: []
skills: []
created: 2026-07-04
updated: 2026-07-04
---

# STORY-014: README & usage documentation

## Description

As an open-source contributor or adopter, I want a clear README with copy-paste examples, so that I can run the harness locally or via Docker and understand its API without reading the source.

## Acceptance Criteria

- [ ] Given the README, when followed step-by-step, then a new user can run the harness both via `python app.py` and `docker-compose up` successfully.
- [ ] Given the README, when read, then it documents every env var from PRD Section 9 with a description and example value.
- [ ] Given the README, when read, then it includes copy-paste `curl` (or equivalent) examples for `POST /query` (success, duplicate-blocked, pattern-blocked), `GET /audit`, and `GET /stats`.
- [ ] Given `.env.example`, when copied to `.env`, then it contains every required var with placeholder values and inline comments.
- [ ] Given the repo, when checked, then a LICENSE file (MIT, per PRD Section 13) is present.

## Technical Notes

- Write `README.md` at the project root and `.env.example` per PRD Section 6/8/13.
- Keep examples aligned exactly with the request/response shapes in PRD Section 10 so they're copy-paste-correct.

## Dependencies

- **Blocked by**: STORY-013
- **Blocks**: None

## PRD Reference

Source: [`PRD-001/PRD.md`](../../PRDs/PRD-001-harness-ia/PRD.md) — Section 12 (Phase 5), Section 13 (Open Source)
