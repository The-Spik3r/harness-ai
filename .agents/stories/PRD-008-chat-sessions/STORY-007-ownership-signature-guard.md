---
id: STORY-007
prd: PRD-008
slug: ownership-signature-guard
title: "tests/test_session_ownership.py: the ownership rule asserted against signatures, not against memory"
type: technical
priority: high
complexity: small
phase: "1 - Schema and store"
status: todo
labels: [tests, security, backend]
epic_branch: epic/PRD-008-chat-sessions
plan: null
report: null
commit: null
depends_on: [STORY-004, STORY-005, STORY-006]
blocks: [STORY-021]
skills: []
created: 2026-09-02
updated: 2026-09-02
---

# STORY-007: tests/test_session_ownership.py: the ownership rule asserted against signatures, not against memory

## Description

As a maintainer, I want the "every session function names an owner" rule enforced by a test that inspects the signatures, so that the rule still fails when someone adds a tenth function next month and nobody remembers the rule existed.

This is the same move [tests/test_untouched_app.py](../../../tests/test_untouched_app.py) made for PRD-006's containment: "That proof was a document, and a document does not fail when someone adds a database function next month."

## Acceptance Criteria

- [ ] Given `tests/test_session_ownership.py`, when it runs, then it enumerates every public callable in [app/db/database.py](../../../app/db/database.py) whose name matches the session/message surface (`*_chat_session*`, `*_chat_message*`) and asserts each declares a `user_id` parameter that is **required and has no default**.
- [ ] Given a hypothetical new function added to that surface without `user_id`, when the suite runs, then this test fails — verified during implementation by adding one temporarily and observing the red, then removing it.
- [ ] Given `app/services/chat_sessions.py`, when the same inspection runs over it, then every public function takes an `Identity` as its first parameter.
- [ ] Given two seeded users, when every read path in both modules is driven with the other user's credential, then each returns empty, `None` or `False`, and never a row.
- [ ] Given every write path driven with a foreign credential, when the call returns, then the database is byte-identical to before — asserted by counting rows in both tables, not by trusting the return value.
- [ ] Given `count_audit_logs()`, when a foreign-credential `delete` is attempted, then it is unchanged, and so is the count of `chat_messages` rows belonging to the real owner.
- [ ] Given the suite, when it runs offline with no Turso account, then it passes — the property PRD-007 STORY-006 established for every test in this repository.

## Technical Notes

- New file `tests/test_session_ownership.py`. Uses the existing `tests/conftest.py` fixture that provisions an isolated database per test — do not add a second fixture.
- Use `inspect.signature(...)` for the structural assertions. The point is that the check survives refactoring: a test that lists nine function names by hand goes stale the moment a tenth is added, which is the exact failure this story exists to prevent. Discover the functions, do not enumerate them.
- PRD Risk 2 is the whole of this story's justification, verbatim: "RBAC has never asked *whose row is this*, so there is no habit to fall back on, and the failure mode is silent: a missing `WHERE user_id = ?` returns data rather than an error. *Mitigation*: the rule lives in the signature — `user_id` is required and undefaulted on every session-scoped function, so an omission is a `TypeError` at the call site rather than a leak at runtime."
- Seed the two users with [app/services/identity.py](../../../app/services/identity.py)'s `issue_token()` and `hash_token()` plus `insert_user`, the way [tests/test_rbac.py](../../../tests/test_rbac.py) already does. Do not fabricate token hashes by hand.
- This story adds no production code. If a signature has to change to make the test pass, that is a defect in [[STORY-004]], [[STORY-005]] or [[STORY-006]] and should be fixed there, with the reason recorded in this story's report.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story touches no UI. No skill applies.

## Dependencies

- **Blocked by**: STORY-004, STORY-005, STORY-006
- **Blocks**: STORY-021

## PRD Reference

Source: [`PRD-008/PRD.md`](../../PRDs/PRD-008-chat-sessions/PRD.md) — Section 6 (Ownership as a signature rule), Section 11 (Quality indicators), Section 12 Phase 1, Risk 2
