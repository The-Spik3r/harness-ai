---
id: STORY-013
prd: PRD-012
slug: code-round-trip-suite
title: "Code round-trip suite and the latency-budget assertion"
type: technical
priority: high
complexity: medium
phase: "4 - Decide and prove"
status: todo
labels: [tests, pii, performance]
epic_branch: epic/PRD-012-pii-for-code
plan: null
report: null
commit: null
depends_on: [STORY-001, STORY-003, STORY-008, STORY-009]
blocks: [STORY-014]
skills: []
created: 2026-09-23
updated: 2026-09-23
---

# STORY-013: Code round-trip suite and the latency-budget assertion

## Description

As a security admin and an integrating developer, I want the MVP criteria asserted over the corpus and the benchmark, so that "code survives and prose is still masked, within budget" is a green test rather than a claim.

## Acceptance Criteria

- [ ] Given `tests/test_pii_code_corpus.py`, when it runs, then under `code` every fenced sample in `tests/corpora/pii/code/` is byte-identical after redaction, and every unfenced sample keeps its count and positions of quotes, backslashes, backticks and line breaks, with every `.py` still passing `ast.parse` and every `.json` still passing `json.loads`.
- [ ] Given `tests/corpora/pii/prose/`, when each file is redacted under both `chat` and `code`, then its declared entities are masked, except entity types absent from `PII_ENTITIES_CODE` under `code`, which the test enumerates explicitly.
- [ ] Given `tests/corpora/pii/json/`, when each file is redacted under `code`, then it parses, and number-token PII is quoted.
- [ ] Given the benchmark rerun at 200,000 characters under `code`, when p95 is measured, then it is under the budget the STORY-003 report fixed, and the number is recorded in this story's report.
- [ ] Given at least one code-corpus file, when it goes through today's `chat` policy, then it is asserted to change (a masked identifier or literal). That proves the corpus is not vacuous.

## Technical Notes

- Guard the latency assertion with a marker (`@pytest.mark.benchmark`) so the everyday run stays fast. Run it explicitly in this story and in STORY-014.
- Test `tool`-shaped content by direct call to `redact_for_policy`, since step 0 still refuses `tool` turns.
- The "not vacuous" assertion mirrors PRD-011 Risk 5 / STORY-011.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-001, STORY-003, STORY-008, STORY-009
- **Blocks**: STORY-014

## PRD Reference

Source: [`PRD-012-pii-for-code/PRD.md`](../../PRDs/PRD-012-pii-for-code/PRD.md) — sections 7 (F11), 11 (MVP definition, Benchmark criteria, Refinement), 14 (Risk 1)
