---
id: STORY-011
prd: PRD-007
slug: stats-endpoint-batched
title: "GET /stats consumes the batched read instead of nine sequential calls"
type: enhancement
priority: medium
complexity: small
phase: "3 - Network-cost remediation"
status: done
labels: [backend, api, performance, admin]
epic_branch: epic/PRD-007-turso-migration
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-011-stats-endpoint-batched.plan.md
report: .agents/reports/PRD-007-turso-migration/STORY-011-stats-endpoint-batched.report.md
commit: 94fdf4a
depends_on: [STORY-010]
blocks: []
skills: []
created: 2026-09-01
updated: 2026-09-02
---

# STORY-011: GET /stats consumes the batched read instead of nine sequential calls

## Description

As an integrating developer, I want `GET /stats` to answer in one database round trip, so that the endpoint's latency does not scale with the number of figures it reports now that each read crosses a network.

[app/routers/admin.py:71-84](../../../app/routers/admin.py) currently calls nine database functions in sequence to assemble one `StatsResponse`. The response schema does not change; only how it is filled.

## Acceptance Criteria

- [ ] Given `GET /stats`, when it is served, then it issues **one** database round trip for all its figures, using the batched read from [[STORY-010]].
- [ ] Given the response, when it is compared to `main`'s output for the same data, then it is byte-identical. `StatsResponse`'s field set, types, and ordering are unchanged.
- [ ] Given the success-rate figure, when it is computed, then it is still `count_successful_queries() / count_audit_logs()` with the same semantics documented at [chat_ui/chat_ui/admin_copy.py:292](../../../chat_ui/chat_ui/admin_copy.py) — `success = 1` includes blocked-but-recorded queries. Do not "fix" that while touching the code; it is documented behavior and any change belongs in its own story.
- [ ] Given a division by zero on an empty database, when `/stats` is served, then it behaves exactly as it does today.
- [ ] Given `stats:read` authorization, when an unauthorized caller requests `/stats`, then the gate behaves unchanged — no PRD-005 behavior moves in this story.
- [ ] Given `tests/test_stats_router.py`, when it runs, then it passes with its assertions unchanged, plus a new assertion pinning the single-round-trip property.
- [ ] Given `GET /audit`, when it is inspected, then it is untouched. Its `count_audit_logs(user_id=scope_user_id)` call at [app/routers/admin.py:43](../../../app/routers/admin.py) is a scoped read, not part of the summary, and stays a standalone call.

## Technical Notes

- Files: [app/routers/admin.py](../../../app/routers/admin.py) (`get_stats` only), `tests/test_stats_router.py`.
- The endpoint needs nine of the ten batched figures; it does not need `list_audit_logs`. Confirm the batched read lets a caller skip a figure it does not want, or that fetching it is cheap enough not to matter — and say which in the report.
- The endpoint is a plain `def` (line 70), dispatched by FastAPI to a threadpool. Keep it synchronous. Making it `async def` here would put a blocking client call on the event loop, which is worse than what it replaces.
- Resist widening the diff. `get_audit` shares the file and reads similarly, but it is a scoped, per-caller read that this PRD does not touch.
- PRD Section 10 states the contract this story must not break: "Response schema identical; internally one batched read instead of nine."
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story changes a JSON endpoint, not rendered output. No skill applies.

## Dependencies

- **Blocked by**: STORY-010
- **Blocks**: None

## PRD Reference

Source: [`PRD-007/PRD.md`](../../PRDs/PRD-007-turso-migration/PRD.md) — Section 6 Pattern 3, Section 7.3, Section 10, Section 12 Phase 3
