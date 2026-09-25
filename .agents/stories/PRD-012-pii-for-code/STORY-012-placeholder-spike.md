---
id: STORY-012
prd: PRD-012
slug: placeholder-spike
title: "Placeholder spike and decisions/D5-placeholders.md"
type: spike
priority: medium
complexity: medium
phase: "4 - Decide and prove"
status: in-progress
labels: [pii, research, decision]
epic_branch: epic/PRD-012-pii-for-code
plan: .agents/plans/PRD-012-pii-for-code/STORY-012-placeholder-spike.plan.md
report: null
commit: null
depends_on: [STORY-009]
blocks: [STORY-014]
skills: []
created: 2026-09-23
updated: 2026-09-25
---

# STORY-012: Placeholder spike and decisions/D5-placeholders.md

## Description

As an integrating developer, I want evidence on whether fixed placeholders make coding agents unusable, so that the choice between fixed, indexed and reversible placeholders is made on data.

## Acceptance Criteria

- [ ] Given `scripts/spike_pii_placeholders.py`, when it runs with an OpenRouter key, then it drives at least three scripted multi-turn agent tasks (for example, edit a fixture, write a test, rename a field) through `run_conversation(profile="code")`, feeding each response back as history, for each of: (a) fixed `<TYPE>`, (b) indexed per request `<TYPE_n>` numbered by first appearance across the conversation, (c) reversible with an in-memory mapping.
- [ ] Given each run, when it completes, then the script reports, per option, the number of placeholders that appear in model output and whether the task's final artifact is correct.
- [ ] Given `.agents/PRDs/PRD-012-pii-for-code/decisions/D5-placeholders.md`, when it is read, then it records the method, the raw results, the model used, the decision, and why option (c) is or is not adopted, given that a stored mapping is PII at rest.
- [ ] Given the decision is (a), when this story lands, then no production code changes. Given it is (b), then the decision record names the follow-up story instead of implementing it here.
- [ ] Given CI, when the suite runs, then the spike script is not collected as a test.

## Technical Notes

- The mappings for (b) and (c) live only in the spike script. Nothing is persisted, and no production module gains a mapping.
- Link the decision record from PRD Section 15.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-009
- **Blocks**: STORY-014

## PRD Reference

Source: [`PRD-012-pii-for-code/PRD.md`](../../PRDs/PRD-012-pii-for-code/PRD.md) — sections 7 (F10), 9.2 (T8), 14 (Risk 7), 15 (D5)
