---
id: STORY-003
prd: PRD-012
slug: pii-benchmark-baseline
title: "Benchmark harness, baseline numbers, pinned versions and tokenizer-only analyzer feasibility"
type: spike
priority: high
complexity: large
phase: "1 - Measure and pin"
status: done
labels: [pii, performance, tooling]
epic_branch: epic/PRD-012-pii-for-code
plan: .agents/plans/PRD-012-pii-for-code/completed/STORY-003-pii-benchmark-baseline.plan.md
report: .agents/reports/PRD-012-pii-for-code/STORY-003-pii-benchmark-baseline.report.md
commit: ddf6596
depends_on: [STORY-001]
blocks: [STORY-005, STORY-006, STORY-013]
skills: []
created: 2026-09-23
updated: 2026-09-24
---

# STORY-003: Benchmark harness, baseline numbers, pinned versions and tokenizer-only analyzer feasibility

## Description

As a platform operator, I want redaction latency and false positives measured at agent-sized contexts before anything changes, so that the `code` threshold, size limit and latency budget are set from data.

## Acceptance Criteria

- [ ] Given `scripts/measure_pii_latency.py --sizes 40000,200000,400000 --runs N`, when it runs on untouched code, then it prints p50/p95 of `redact()` per size over conversations built from `tests/corpora/pii/code/` plus prose filler, and the per-entity-type false-positive count over the code corpus at `PII_SCORE_THRESHOLD=0.35`.
- [ ] Given the script, when it runs with a pattern-only entity list (`EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE`) on (a) the full `en_core_web_lg` analyzer and (b) a tokenizer-only `spacy.blank("en")` analyzer, then both sets of timings are reported, or (b) is reported as infeasible with the Presidio error that shows why.
- [ ] Given the report, when it is read, then it states the resolved `presidio-analyzer`, `presidio-anonymizer` and `spacy` versions, and `requirements.txt` pins exactly those.
- [ ] Given the numbers, when the report concludes, then it fixes `PII_SCORE_THRESHOLD_CODE`, `PII_MAX_CHARACTERS_CODE` and the p95 budget at 200,000 characters, states the reasoning for each, and states whether `PERSON` stays out of `PII_ENTITIES_CODE` (D7).
- [ ] Given concurrency, when the script runs with `--concurrency 1` and `--concurrency 4` in threads, then throughput for both is reported (T10). No budget is asserted on it.

## Technical Notes

- This is the story that turns the PRD's provisional values into decided ones. Write the report to `.agents/reports/PRD-012-pii-for-code/STORY-003-pii-benchmark-baseline.report.md`. STORY-005 reads the three numbers from it.
- Feasibility of (b) is the PRD's Risk 2. Try `NlpEngineProvider` with a blank model first, then a thin `SpacyNlpEngine` subclass that loads `spacy.blank("en")`. Record which one works. If neither does, record the fallback (pattern-only entities on the full engine) and set the budget from that.
- Time `redact()` only, not the pipeline, and follow `scripts/measure_history_latency.py`'s style and output format. The 400k size is over `CONTEXT_MAX_CHARACTERS` on purpose, to measure the analyzer rather than the limit.
- Pinning versions may change the resolved environment. Run the full suite after pinning, and restart the libSQL dev container if fixtures mass-fail (the README note).
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-005, STORY-006, STORY-013

## PRD Reference

Source: [`PRD-012-pii-for-code/PRD.md`](../../PRDs/PRD-012-pii-for-code/PRD.md) — sections 4 (Benchmark and baseline), 6.4 (D7), 7 (F1), 9.3, 11 (Benchmark criteria), 14 (Risk 2)
