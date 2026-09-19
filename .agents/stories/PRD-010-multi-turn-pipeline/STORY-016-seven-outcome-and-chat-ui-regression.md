---
id: STORY-016
prd: PRD-010
slug: seven-outcome-and-chat-ui-regression
title: "Seven-outcome /query regression and chat UI regression on the finished epic"
type: technical
priority: high
complexity: medium
phase: "4 - Prove and document"
status: done
labels: [tests, regression, api, chat-ui]
epic_branch: epic/PRD-010-multi-turn-pipeline
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-016-seven-outcome-and-chat-ui-regression.plan.md
report: .agents/reports/PRD-010-multi-turn-pipeline/STORY-016-seven-outcome-and-chat-ui-regression.report.md
commit: 233b208
depends_on: [STORY-005, STORY-008, STORY-009, STORY-013]
blocks: [STORY-018]
skills: []
created: 2026-09-17
updated: 2026-09-19
---

# STORY-016: Seven-outcome /query regression and chat UI regression on the finished epic

## Description

As an integrating developer, I want the finished epic proven to leave `/query`'s outcomes, payload and reporting unchanged, and the chat UI's every bubble path working with history on and off, so that the largest pipeline refactor since PRD-002 ships without a silent regression.

## Acceptance Criteria

- [ ] Given [tests/test_query_outcomes_regression.py](../../../tests/test_query_outcomes_regression.py), when run on the finished epic, then outcomes 1–6 pass with **no assertion diff** from `main` (`git diff main -- tests/test_query_outcomes_regression.py` shows only additions: the STORY-003 characterization and outcome 7), and outcome 7 passes.
- [ ] Given `/query` with a normal prompt, when the upstream payload is recorded, then it is byte-identical to STORY-003's characterization, and a `null`-content reply still maps to 502.
- [ ] Given the chat UI with history **on**, when each result type is driven through `_do_send` (success, duplicate, suspicious, forbidden, upstream error, internal error, context limit), then each renders its kind and persists exactly one bubble, and only the success adds an exchange to the next send's history.
- [ ] Given the chat UI with history **off**, when the same seven are driven, then bubbles are identical to history-on except that nothing is persisted and upstream always receives one message. [tests/test_history_off_integration.py](../../../tests/test_history_off_integration.py) is unmodified from `main`.
- [ ] Given [tests/test_reporting_invariance.py](../../../tests/test_reporting_invariance.py), `/audit` and `/stats`, when multi-turn sends with PII only in turn 1 are made, then `pii_detected_queries` counts only sends whose **new** turn or output had PII (D7), and every other figure matches the single-turn equivalent. The full suite is green.

## Technical Notes

- Tests-only story; any failure found is fixed in a separate commit citing the story that introduced it.
- Check PRD Section 11's quality indicators explicitly in the report: no outcome assertion modified in `test_query_router.py`, `test_integration.py` or regression rows 1–6, and every modified pre-existing test carries a PRD-010 comment (grep `PRD-010` across tests and list them).
- Following the libSQL dev-server note, mass fixture errors mean restart the container, not bisect the code.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-005, STORY-008, STORY-009, STORY-013
- **Blocks**: STORY-018

## PRD Reference

Source: [`PRD-010-multi-turn-pipeline/PRD.md`](../../PRDs/PRD-010-multi-turn-pipeline/PRD.md) — sections 5 (story 4), 6.7 (D7), 11 (seven outcomes, quality indicators), 14 (Risk 1)
