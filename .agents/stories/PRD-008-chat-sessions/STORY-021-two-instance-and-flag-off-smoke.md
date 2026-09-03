---
id: STORY-021
prd: PRD-008
slug: two-instance-and-flag-off-smoke
title: "Two instances serve one session, and CHAT_HISTORY_ENABLED=false writes nothing -- proven, not assumed"
type: technical
priority: high
complexity: medium
phase: "4 - Surface and hardening"
status: todo
labels: [tests, integration, security, deployment]
epic_branch: epic/PRD-008-chat-sessions
plan: null
report: null
commit: null
depends_on: [STORY-007, STORY-010, STORY-015, STORY-016]
blocks: [STORY-022]
skills: []
created: 2026-09-02
updated: 2026-09-02
---

# STORY-021: Two instances serve one session, and CHAT_HISTORY_ENABLED=false writes nothing — proven, not assumed

## Description

As an employee reconnecting to a different instance, I want my conversations to be there anyway, so that the two-instance deployment PRD-007 shipped is invisible to me (PRD Section 5, story 6) — and as a security admin, I want the off state proven by a test rather than promised by a docstring.

## Acceptance Criteria

- [ ] Given the pattern in [tests/test_two_instance_smoke.py](../../../tests/test_two_instance_smoke.py), when it is extended, then a session created and written through one client is read back in full through a **separate, freshly constructed** client — not through the writing one.
- [ ] Given that round trip, when the transcript is compared, then every message matches in order and in every field, including the metadata that drives the verdict rendering.
- [ ] Given a session created on instance A and deleted on instance B, when instance A reads it, then it is gone from both tables and `count_audit_logs()` is unchanged.
- [ ] Given `CHAT_HISTORY_ENABLED=false`, when a full send is driven end to end, then `chat_sessions` and `chat_messages` are both **empty**, the audit row is written as normal, and the response is unchanged.
- [ ] Given `CHAT_HISTORY_ENABLED=false`, when the read paths are driven, then the database module is not called at all — asserted by patching it and observing no call, per [[STORY-006]]'s criterion.
- [ ] Given `CHAT_HISTORY_ENABLED` flipped back to `true`, when a send runs, then persistence resumes with no restart-time migration and no error about missing rows.
- [ ] Given a `session_id` created by user A, when user B sends it to `POST /query` against the second instance, then the response is `403` — the ownership check is not instance-local state.
- [ ] Given the suite, when it runs offline with no Turso account, then it passes — the property every test in this repository holds since PRD-007 STORY-006.

## Technical Notes

- Files: [tests/test_two_instance_smoke.py](../../../tests/test_two_instance_smoke.py) (extended) and a new flag-off integration test. No production code.
- The separate-client requirement is not ceremony. PRD-007 STORY-006 recorded why, verbatim: "the write is durably committed — verified by reading it back **through a separate, freshly constructed client**, not through the writing one. This is Risk 1 and the single most dangerous failure mode in the epic: a lost `insert_audit_log()` is invisible until someone reads an empty audit trail." A lost transcript row has the same shape and the same invisibility.
- The flag-off test must assert **absence of calls**, not merely absence of rows. A service that calls the database and discards the result would pass a row-count assertion and would still be writing under a flag that says it does not.
- Reuse the local libSQL server the existing smoke test provisions. Do not introduce a second harness or a second fixture.
- PRD Section 11 lists both of these as functional requirements rather than as nice-to-haves: "Two instances against one database serve the same session" and "`CHAT_HISTORY_ENABLED=false` writes no row, reads no row, renders no rail, and leaves the chat fully working."
- The rail's absence under the flag is asserted in [[STORY-018]]'s render criteria; this story covers the data side. Both halves are needed for PRD Risk 1's mitigation to be real.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story asserts data behaviour and runs no renderer. No skill applies.

## Dependencies

- **Blocked by**: STORY-007, STORY-010, STORY-015, STORY-016
- **Blocks**: STORY-022

## PRD Reference

Source: [`PRD-008/PRD.md`](../../PRDs/PRD-008-chat-sessions/PRD.md) — Section 5 (stories 6, 7), Section 9, Section 11, Section 12 Phase 4, Risk 1
