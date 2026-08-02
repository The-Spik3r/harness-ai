---
id: STORY-012
prd: PRD-003
slug: readme-env-docs-rollout
title: "README, .env.example, and roadmap updates for PII redaction"
type: technical
priority: medium
complexity: small
phase: "4 - Docs & Rollout"
status: done
labels: [docs]
epic_branch: epic/PRD-003-pii-redaction
plan: .agents/plans/PRD-003-pii-redaction/completed/STORY-012-readme-env-docs-rollout.plan.md
report: .agents/reports/PRD-003-pii-redaction/STORY-012-readme-env-docs-rollout.report.md
commit: 2f9a9e3
depends_on: [STORY-010, STORY-011]
blocks: []
skills: []
created: 2026-07-24
updated: 2026-08-02
---

# STORY-012: README, .env.example, and roadmap updates for PII redaction

## Description

As an integrating developer or devops engineer evaluating this project, I want the README and `.env.example` to accurately document the new PII redaction feature and its env vars, and the roadmap checkbox flipped to done, so the documented behavior matches what's actually shipped (PRD Section 12, Phase 4).

## Acceptance Criteria

- [ ] Given `README.md`'s Features table (around [README.md:102](../../../README.md)), when read, then it lists PII redaction on input/output, mentioning it's English-only, mask-not-block, and Presidio-backed.
- [ ] Given `README.md`'s Environment Variables section (around [README.md:180](../../../README.md)), when read, then it documents `PII_REDACTION_ENABLED`, `PII_SCORE_THRESHOLD`, `PII_ENTITIES`, `PII_NLP_MODEL` with the same defaults as [[STORY-001]]'s implementation.
- [ ] Given `README.md`'s API Reference section (around [README.md:195](../../../README.md)), when read, then the `POST /query` response example includes `pii_redacted`/`pii_entities_masked`, and `GET /audit`/`GET /stats` examples include the new PII telemetry fields from [[STORY-009]].
- [ ] Given `README.md`'s Roadmap section ([README.md:326](../../../README.md)), when read, then `- [ ] PII redaction on input/output` is changed to `- [x] PII redaction on input/output`.
- [ ] Given `.env.example` ([`.env.example`](../../../.env.example)), when read, then it includes the four new `PII_*` vars with a short comment each, matching the existing file's comment style.
- [ ] Given `README.md`'s Requirements/Quickstart sections, when read, then they note the added spaCy model download step and the image-size/build-time impact from [[STORY-011]] (PRD Risk 5).

## Technical Notes

- Follow the existing `.env.example` comment style exactly (one comment line above each var, see current file).
- Keep this story doc-only — no source code changes. It is intentionally the last story so it can document the actual shipped shape of every field, not the PRD's pre-implementation draft.

## Dependencies

- **Blocked by**: STORY-010, STORY-011
- **Blocks**: None

## PRD Reference

Source: [`PRD-003/PRD.md`](../../PRDs/PRD-003-pii-redaction/PRD.md) — Section 12 (Phase 4 — Docs & Rollout), Section 9 (Environment variables), Section 10 (API Specification)
