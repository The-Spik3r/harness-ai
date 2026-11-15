---
id: STORY-017
prd: PRD-016
slug: synthetic-tool-call-corpus
title: Synthetic tool-call corpus, its suite end to end through record(), and evaluate() latency
type: technical
priority: high
complexity: medium
phase: "4 - Evidence"
status: done
labels: [tests, security, corpus]
epic_branch: epic/PRD-016-action-policy-rules
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-017-synthetic-tool-call-corpus.plan.md
report: .agents/reports/PRD-016-action-policy-rules/STORY-017-synthetic-tool-call-corpus.report.md
commit: pending
depends_on: [STORY-014, STORY-015]
blocks: [STORY-018]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-017: Synthetic tool-call corpus, its suite end to end through record(), and evaluate() latency

## Description

As a security admin, I want the brief's success criteria and ordinary agent work checked in as tool-call files with their expected decision per role, so that what the policy allows and denies is shown by evidence instead of claimed.

## Acceptance Criteria

- [ ] Given `tests/corpora/actions/synthetic/`, when counted, then it holds at least 40 files; every rule id in PRD Section 6.3 is produced by at least one; at least 15 are ordinary OpenCode and Cline operations expected to be `allow`; the brief's five criteria are present verbatim (`DROP TABLE users` deny, `SELECT` allow, `rm -rf /` deny, `curl x | sh` deny, write to `.env` deny, granted `DELETE … WHERE` allow).
- [ ] Given each file's `expect: {role: decision}` map, when `tests/test_action_corpus.py` runs with the built-in policy plus `examples/action_policy.yaml`, and a test RBAC matrix defining `dba` with `action:sql:write`, then every expected decision holds for every role named.
- [ ] Given each decision in the corpus, when passed through `action_audit.record()` and read back through `GET /audit/actions`, then the row's `decision`, `rule` and `granted_by` match the engine's.
- [ ] Given the whole corpus, when every `reason` is checked, then none contains a configured host, root or allowlist entry.
- [ ] Given the corpus, when `evaluate()` is timed over it, then the p95 is recorded in the story report (benchmark-marked, skipped unless `--run-benchmark`).

## Technical Notes

- File shape (PRD F12): `{tool_call: {name, arguments}, expect: {user: deny, dba: allow}, note: "..."}`; `arguments` stored as the JSON string a model would emit.
- The suite parametrizes over the directory, as `tests/test_pattern_corpus.py` does; a file that names an unknown role or decision fails collection.
- Use the PRD-011 corpus layout and `SOURCES.md` from STORY-001 for tool names.
- The round-trip through `record()` and `GET /audit/actions` reaches storage: the `db` marker applies.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-014, STORY-015
- **Blocks**: STORY-018

## PRD Reference

Source: [`PRD-016-action-policy-rules/PRD.md`](../../PRDs/PRD-016-action-policy-rules/PRD.md) — sections 1 (MVP goal), 7 (F12), 11 (MVP definition, Functional requirements, Corpus criteria, Quality indicators)
