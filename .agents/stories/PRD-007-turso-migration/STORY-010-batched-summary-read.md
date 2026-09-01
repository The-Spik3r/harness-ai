---
id: STORY-010
prd: PRD-007
slug: batched-summary-read
title: "One batched database read returning all ten summary figures in a single round trip"
type: feature
priority: high
complexity: medium
phase: "3 - Network-cost remediation"
status: todo
labels: [backend, database, performance, admin]
epic_branch: epic/PRD-007-turso-migration
plan: null
report: null
commit: null
depends_on: [STORY-006, STORY-009]
blocks: [STORY-011, STORY-012]
skills: []
created: 2026-09-01
updated: 2026-09-01
---

# STORY-010: One batched database read returning all ten summary figures in a single round trip

## Description

As a compliance admin, I want the admin console's summary figures fetched in one round trip, so that the register stays usable now that each read crosses a network instead of hitting a local file.

Two callers perform the same fan-out today: [chat_ui/chat_ui/admin_state.py:229](../../../chat_ui/chat_ui/admin_state.py) `_READS` runs ten reads sequentially, and `GET /stats` at [app/routers/admin.py:71-84](../../../app/routers/admin.py) runs nine. With connection-per-operation against a file that cost nothing. Against a remote endpoint it is ten sequential round trips per page load. This story builds the batched read in `app/db/`; [[STORY-011]] and [[STORY-012]] adopt it.

## Acceptance Criteria

- [ ] Given the new function in [app/db/database.py](../../../app/db/database.py), when it is called, then it returns all ten figures — `list_audit_logs(limit)`, `count_audit_logs`, `count_blocked_duplicates`, `count_blocked_suspicious`, `count_unique_users`, `count_successful_queries`, `count_pii_detected_queries`, `top_models`, `top_users`, `top_pii_entities` — in **one** round trip.
- [ ] Given the returned value, when a caller reads a figure, then each is individually addressable by name, with the same type the corresponding standalone function returns today (`int`, `list[str]`, `list[AuditLog]`).
- [ ] Given a batch where one statement fails, when the result is inspected, then the caller can tell **which** figure failed while still receiving the ones that succeeded. Collapsing ten reads into one all-or-nothing result destroys the per-figure error attribution that [[STORY-012]] depends on — Risk 6.
- [ ] Given the ten existing standalone functions, when this story completes, then they still exist with unchanged signatures. `count_audit_logs(user_id=...)` in particular is used by `GET /audit` for scoping, not only by the summary, and must not be folded away.
- [ ] Given the batched read and ten individual calls against the same data, when their results are compared, then every figure is identical.
- [ ] Given `list_audit_logs`'s row limit and the ranked functions' `limit`, when the batched read is called, then both are parameters rather than constants baked into the batch. The callers pass `REGISTER_ROW_LIMIT` and `RANKED_LIMIT` respectively.
- [ ] Given `tests/test_db.py`, when it runs, then the batched read is covered for: agreement with the individual functions, per-figure failure isolation, an empty database, and the round-trip count.
- [ ] Given `git diff main --stat`, when it is inspected, then no file under `app/routers/` or `chat_ui/` is modified. This story builds the capability; the callers adopt it in [[STORY-011]] and [[STORY-012]].

## Technical Notes

- Files: [app/db/database.py](../../../app/db/database.py), `tests/test_db.py`.
- The batch API's shape — how statements are submitted, how per-statement results come back, and how a per-statement error is reported — is the sixth behavior verified in [[STORY-001]]. Read the decision record before designing the return type. If per-statement error reporting turned out to be unsupported, the workaround recorded there governs this story, and Risk 6's mitigation has to be satisfied some other way.
- Ten reads, not nine. `GET /stats` needs nine, but `_READS` also carries `list_audit_logs(limit=REGISTER_ROW_LIMIT)` as its first entry. Build for ten; [[STORY-011]] ignores the rows it does not need.
- Read the ordering comment above `_READS` before designing: "Order is the read order and is deliberate: the rows come first so the slowest query fails fast, and `total_recorded` follows them because it is the denominator the register states its 100-row cap against." In a single batch "fails fast" loses its original meaning — note in the report whether the ordering still carries any weight, so [[STORY-012]] knows whether its comment needs updating.
- Prove the round-trip count rather than asserting it in prose. A test that counts statements or requests issued is the evidence PRD Section 12 Phase 3 asks for: "Measured round-trip counts for an admin console load and a `POST /query`."
- [[STORY-009]] must land first. Folding a full-table PII scan into the batch would make the single round trip carry the entire audit history.
- Keep the ten standalone functions. They are part of the module's 22-function public surface that [[STORY-006]] promised not to change, and `tests/test_db.py` covers them directly.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story touches no UI. No skill applies.

## Dependencies

- **Blocked by**: STORY-006, STORY-009
- **Blocks**: STORY-011, STORY-012

## PRD Reference

Source: [`PRD-007/PRD.md`](../../PRDs/PRD-007-turso-migration/PRD.md) — Section 6 Pattern 3, Section 7.3, Section 11, Section 12 Phase 3, Section 14 Risk 6
