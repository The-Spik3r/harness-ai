---
id: STORY-008
prd: PRD-003
slug: dedup-pattern-isolation-tests
title: "Tests: redaction cannot affect dedup/pattern-check behavior"
type: technical
priority: high
complexity: medium
phase: "3 - Isolation Testing"
status: done
labels: [backend, testing, pii, security]
epic_branch: epic/PRD-003-pii-redaction
plan: .agents/plans/PRD-003-pii-redaction/completed/STORY-008-dedup-pattern-isolation-tests.plan.md
report: .agents/reports/PRD-003-pii-redaction/STORY-008-dedup-pattern-isolation-tests.report.md
commit: 58ee0a6
depends_on: [STORY-006]
blocks: [STORY-010]
skills: []
created: 2026-07-24
updated: 2026-08-01
---

# STORY-008: Tests — redaction cannot affect dedup/pattern-check behavior

## Description

As a security admin, I want duplicate-detection behavior completely unaffected by redaction, so two legitimately distinct requests from different users are never conflated because their redacted text happens to look identical (PRD User Story 6, RF-6).

## Acceptance Criteria

- [ ] Given two prompts differing only in an email address (e.g. `"contact me at a@x.com"` vs `"contact me at b@y.com"`), when both are submitted, then they hash differently and neither is ever flagged as a duplicate of the other, even though both would redact to `"contact me at <EMAIL_ADDRESS>"`.
- [ ] Given `app/services/duplicate_checker.py`, when inspected/tested, then it is byte-for-byte unmodified by this epic and its existing test suite (`tests/test_duplicate_checker.py`) passes unchanged.
- [ ] Given a prompt that matches the existing suspicious-pattern blocklist, when submitted, then it is still blocked before redaction or the OpenRouter call ever run — same behavior as PRD-001.
- [ ] Given the `hash_prompt()` function used by both dedup and the audit logger, when called during a redacted-pipeline run, then it is always invoked with raw text, never redacted text, at every call site.

## Technical Notes

- Add tests to `tests/test_duplicate_checker.py` or a new `tests/test_pii_dedup_isolation.py` asserting the scenarios above, driving through `run_query()` (or `check_duplicate` directly) with a stubbed/mocked `call_openrouter` and `pii_redactor.redact` where useful to isolate NLP inference cost from the assertion.
- Confirm via test (not just inspection) that `git diff` on `app/services/duplicate_checker.py` is empty for this epic — this is the RF-6 guarantee. Consider asserting the module's hash of `check_duplicate`'s signature/behavior stays stable rather than literally diffing the file.
- Verify `app/services/pattern_detector.py` continues to run on raw text and its existing suite (`tests/test_pattern_detector.py`) is untouched.

## Dependencies

- **Blocked by**: STORY-006
- **Blocks**: STORY-010

## PRD Reference

Source: [`PRD-003/PRD.md`](../../PRDs/PRD-003-pii-redaction/PRD.md) — User Story 6, Section 9 (RF-6), Section 12 (Phase 3), Section 8 (Testing)
