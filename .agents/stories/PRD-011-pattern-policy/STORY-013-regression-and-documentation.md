---
id: STORY-013
prd: PRD-011
slug: regression-and-documentation
title: "Default-config /query regression, README, .env and the promoted pre-PRD"
type: technical
priority: high
complexity: medium
phase: "4 - Prove and document"
status: todo
labels: [backend, tests, docs]
epic_branch: epic/PRD-011-pattern-policy
plan: null
report: null
commit: null
depends_on: [STORY-007, STORY-010, STORY-011, STORY-012]
blocks: []
skills: []
created: 2026-09-22
updated: 2026-09-22
---

# STORY-013: Default-config /query regression, README, .env and the promoted pre-PRD

## Description

As an integrating developer and as a reader of this repository, I want `/query` proven unchanged under the default configuration and the new policy documented, so that nobody has to read the source to learn what is inspected and what is not.

## Acceptance Criteria

- [ ] Given the finished epic and no `PATTERNS_FILE` set, when [tests/test_query_outcomes_regression.py](../../../tests/test_query_outcomes_regression.py) runs, then all seven outcomes pass with no assertion modified, and `tests/test_query_router.py`, `tests/test_integration.py`, `tests/test_chat_outcomes_regression.py` and `tests/test_history_off_integration.py` are unchanged.
- [ ] Given STORY-001's characterization flip set, when the default policy runs the full characterization corpus, then exactly the flipped cases differ from today's verdicts — a final assertion of PRD Section 11's *Refinement of the brief's criterion*, run against the completed epic rather than against a half-built one.
- [ ] Given [README.md](../../../README.md), when it is read, then: the "case-insensitive substring match" line and the published seven-pattern line are replaced; the role inspection matrix of PRD Section 6.4 appears; the file format and the four settings are documented; the *Known limitations* note saying patterns are checked on the newest user turn only is replaced by what actually happens now; indirect injection is stated to be flagged rather than blocked with PRD-015 named as the enforcement point; the narrowed `blocked_suspicious` counter is called out; and *Configurable, per-deployment pattern lists* is ticked on the roadmap.
- [ ] Given `.env.example` and `examples/patterns.yaml`, when they are read, then all four settings are present with defaults and explanations, and the sample file is referenced from both the README and `.env.example`.
- [ ] Given [pre-prds/PRE-PRD-011-pattern-policy.md](../../../pre-prds/PRE-PRD-011-pattern-policy.md), when it is read, then `status: promoted` and `prd: .agents/PRDs/PRD-011-pattern-policy/PRD.md`, and [pre-prds/README.md](../../../pre-prds/README.md)'s brief table reflects it. The full suite is green.

## Technical Notes

- The regression runs on the **default** configuration, because that is what an existing deployment gets after upgrading. A deployment that sets `PATTERNS_FILE` has opted into its own policy and is its own responsibility.
- The README changes are not cosmetic: the published pattern list and the substring sentence are both *wrong* after this epic, and the *Known limitations* note explicitly names PRD-011 as its replacement. Leaving either in place means the documentation describes a detector that no longer exists.
- State the accepted exposure plainly in the README, in the same place the role matrix appears: an instruction planted in a tool result is recorded and still reaches the model in this release (PRD 9.2 T2). It is the one thing a reader could otherwise get wrong in the dangerous direction.
- Also worth a line: RBAC denies by default and pattern inspection does not — a role absent from a profile's `roles:` map is simply not inspected (PRD Section 7 F4).
- Mark the pre-PRD promoted here, as PRD-010 STORY-018 did, rather than at PRD-creation time — the brief stays accurate as a brief until the work it describes exists.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-007, STORY-010, STORY-011, STORY-012
- **Blocks**: None

## PRD Reference

Source: [`PRD-011-pattern-policy/PRD.md`](../../PRDs/PRD-011-pattern-policy/PRD.md) — sections 7 (F9), 9.2 (T2), 9.3, 11 (Refinement, Quality indicators), 12 (Phase 4)
