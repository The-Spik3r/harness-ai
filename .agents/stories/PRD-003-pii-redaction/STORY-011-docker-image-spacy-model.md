---
id: STORY-011
prd: PRD-003
slug: docker-image-spacy-model
title: "Docker image: install spaCy PII model"
type: technical
priority: high
complexity: small
phase: "4 - Docs & Rollout"
status: done
labels: [devops, docker, pii]
epic_branch: epic/PRD-003-pii-redaction
plan: .agents/plans/PRD-003-pii-redaction/completed/STORY-011-docker-image-spacy-model.plan.md
report: .agents/reports/PRD-003-pii-redaction/STORY-011-docker-image-spacy-model.report.md
commit: 2457952
depends_on: [STORY-002]
blocks: [STORY-012]
skills: []
created: 2026-07-24
updated: 2026-08-02
---

# STORY-011: Docker image — install spaCy PII model

## Description

As a devops engineer, I want the `en_core_web_lg` spaCy model downloaded during the Docker build, so the containerized app boots successfully with the same PII redaction behavior as `python app.py`, consistent with PRD-001's Docker/local parity principle (PRD Mission — "Portable by default").

## Acceptance Criteria

- [ ] Given `docker build` runs, when the final image stage installs `requirements.txt`, then it also runs `python -m spacy download en_core_web_lg` so the model is present in the image (not downloaded at container startup).
- [ ] Given the container starts via `docker-compose up`, when `lifespan` triggers [[STORY-002]]'s startup load, then the Presidio analyzer initializes successfully — no missing-model error.
- [ ] Given the builder stage (used only for the Reflex frontend export, per the existing `Dockerfile` comments), when it builds, then it is **not** required to download the spaCy model unless `chat_ui.chat_ui`'s import chain actually triggers Presidio initialization at import time — verify this and only add the download step to the builder stage if needed.
- [ ] Given the resulting image, when its size is compared to the pre-PRD-003 image, then the increase is noted for [[STORY-012]]'s README documentation (PRD Risk 5 — accepted tradeoff, not a blocker).

## Technical Notes

- Update `Dockerfile` ([Dockerfile](../../../Dockerfile)): in the final stage (`FROM python:3.11-slim`, after `RUN pip install --no-cache-dir -r requirements.txt`), add `RUN python -m spacy download en_core_web_lg`.
- Check whether the builder stage's `RUN reflex init --no-agents` / `reflex export` step actually imports `app.main` deeply enough to construct the Presidio singleton at import time (per [[STORY-001]]/[[STORY-002]]'s lazy-vs-eager design) — if the singleton is genuinely lazy (only forced by `lifespan`, which doesn't run during `reflex export --frontend-only`), the builder stage does not need the model and should be left alone to keep build time down.
- `docker-compose.yml` itself likely needs no changes (no new env vars are required to have values — `PII_*` settings all have defaults per [[STORY-001]]), but confirm nothing in `docker-compose.yml` hardcodes an env allowlist that would need the new `PII_*` vars added.

## Dependencies

- **Blocked by**: STORY-002
- **Blocks**: STORY-012

## PRD Reference

Source: [`PRD-003/PRD.md`](../../PRDs/PRD-003-pii-redaction/PRD.md) — Mission (Portable by default), Section 8 (Deployment), Risk 5 (Section 14)
