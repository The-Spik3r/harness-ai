---
id: STORY-016
prd: PRD-006
slug: completion-label-copy-test
title: "Copy test pinning the completion label so it cannot regress to \"success rate\""
type: technical
priority: high
complexity: small
phase: "3 - The summary"
status: done
labels: [tests, copy, admin]
epic_branch: epic/PRD-006-admin-console
plan: .agents/plans/PRD-006-admin-console/completed/STORY-016-completion-label-copy-test.plan.md
report: .agents/reports/PRD-006-admin-console/STORY-016-completion-label-copy-test.report.md
commit: null
depends_on: [STORY-008, STORY-015]
blocks: [STORY-020]
skills: []
created: 2026-08-28
updated: 2026-08-31
---

# STORY-016: Copy test pinning the completion label so it cannot regress to "success rate"

## Description

As an integrating developer, I want the completion figure's wording asserted in a test, so that the one label on the console with a correctness requirement cannot drift back to a name that misstates what it counts (PRD Risk 4).

## Acceptance Criteria

- [ ] Given [tests/test_copy.py](../../../tests/test_copy.py) (or a sibling admin copy test), when it runs, then it asserts the completion label states that blocked rows are included in the count.
- [ ] Given the completion label, when it is asserted, then the test fails if the wording becomes "success rate" or any phrasing that reads as an answer rate.
- [ ] Given every constant in `admin_copy.py`, when the test runs, then each is asserted non-empty, matching the existing `test_copy_constants_exist_and_not_empty` pattern.
- [ ] Given the scope templates — the register's "100 most recent of {total}" and the summary's all-time scope line — when the test runs, then both are asserted to state their window (Risk 4).
- [ ] Given the gate refusal string, when the test runs, then exactly one refusal constant exists — no second, more specific message can be added without failing the test (Section 9's no-oracle rule).
- [ ] Given the existing chat copy assertions in [tests/test_copy.py](../../../tests/test_copy.py), when the suite runs, then they pass unmodified.

## Technical Notes

- Risk 4 mitigation, verbatim: "The completion label is covered by a copy test so its wording cannot drift back to 'success rate'."
- PRD Section 12 Phase 3 validation: "the completion label is asserted in a copy test so the wording cannot regress to 'success rate'."
- Follow the existing structure of [tests/test_copy.py](../../../tests/test_copy.py) — it imports constants by name from `chat_ui.chat_ui.copy` and asserts them individually; add the admin constants the same way.
- Assert on substance, not on the exact sentence: a test that pins the full string breaks on every legitimate wording tweak. Assert that the label contains the qualifier and does **not** contain the forbidden phrasing.
- Keep this in the existing test file if the imports stay readable; a separate `tests/test_admin_copy.py` is equally acceptable and does not touch the file PRD Section 11 requires to pass unmodified.

## Dependencies

- **Blocked by**: STORY-008, STORY-015
- **Blocks**: STORY-020

## PRD Reference

Source: [`PRD-006/PRD.md`](../../PRDs/PRD-006-admin-console/PRD.md) — Section 11, Section 12 Phase 3 validation, Risk 4
