---
id: STORY-014
prd: PRD-012
slug: chat-regression-and-docs
title: "chat regression sweep, README and .env docs, pre-PRD promoted"
type: technical
priority: medium
complexity: medium
phase: "4 - Decide and prove"
status: todo
labels: [docs, tests, regression]
epic_branch: epic/PRD-012-pii-for-code
plan: null
report: null
commit: null
depends_on: [STORY-002, STORY-011, STORY-012, STORY-013]
blocks: []
skills: []
created: 2026-09-23
updated: 2026-09-23
---

# STORY-014: chat regression sweep, README and .env docs, pre-PRD promoted

## Description

As a platform operator, I want the README to say exactly what the `code` profile masks and gives up, with measured figures, so that I can configure and defend the deployment without reading the code.

## Acceptance Criteria

- [ ] Given the full suite, when it runs, then it is green, and `git diff` since the epic's base shows no changed assertion in `test_pii_redactor.py`, `test_pii_redaction_integration.py`, `test_pii_characterization.py`, `test_query_outcomes_regression.py` or `test_chat_outcomes_regression.py`.
- [ ] Given the README PII section, when it is read, then it describes the `chat` and `code` profiles, reproduces the Section 6.3 role table, and states plainly: fenced blocks unmasked, names and places not detected by default, output not masked, number tokens quoted in JSON, over-limit refused, `profile` in the audit.
- [ ] Given the README, when it quotes latency, then it gives the STORY-003 / STORY-013 figures for both profiles beside the existing ~0.93 s history figure, and names `scripts/measure_pii_latency.py`.
- [ ] Given `.env.example` and the README configuration table, when they are read, then all six new settings appear with defaults and one-line purposes, and the four existing `PII_*` rows say they apply to `chat`.
- [ ] Given `pre-prds/PRE-PRD-012-pii-for-code.md` and `pre-prds/README.md`, when they are read, then the brief is `status: promoted` with `prd:` set, and its table row links PRD-012 with status `promoted`.

## Technical Notes

- Follow the PRD-011 STORY-013 shape: regression sweep plus documentation in one commit.
- Update the README *Known limitations* bullets on PII audit semantics only where the `profile` field changes what they say.
- Link the D5 decision record from the README only if the decision changes user-visible behaviour.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-002, STORY-011, STORY-012, STORY-013
- **Blocks**: None

## PRD Reference

Source: [`PRD-012-pii-for-code/PRD.md`](../../PRDs/PRD-012-pii-for-code/PRD.md) — sections 4 (Documentation), 7 (F12), 11 (Quality indicators)
