---
id: STORY-006
prd: PRD-006
slug: admin-state-tests
title: "tests/test_admin_state.py: gate, sign-out, failed read, four verdicts, no leak"
type: technical
priority: high
complexity: medium
phase: "1 - Access and data"
status: done
labels: [tests, state, security, admin]
epic_branch: epic/PRD-006-admin-console
plan: .agents/plans/PRD-006-admin-console/completed/STORY-006-admin-state-tests.plan.md
report: .agents/reports/PRD-006-admin-console/STORY-006-admin-state-tests.report.md
commit: 3d6474e
depends_on: [STORY-002, STORY-003, STORY-004, STORY-005]
blocks: [STORY-020]
skills: []
created: 2026-08-28
updated: 2026-08-30
---

# STORY-006: tests/test_admin_state.py: gate, sign-out, failed read, four verdicts, no leak

## Description

As an integrating developer, I want the admin state driven directly by unit tests, so that the gate, the failure arm and the verdict derivation are proven without a browser (PRD Section 12 Phase 1 validation).

## Acceptance Criteria

- [ ] Given the correct token, when `authenticate()` runs, then `authenticated` is True; given a wrong token and given an empty token, then both leave `authenticated` False and produce the **same** error string — asserted as equal to each other, not merely as non-empty.
- [ ] Given an authenticated state with rows loaded, when `sign_out()` runs, then the row list is empty, the summary figures are cleared, the token is cleared and `authenticated` is False.
- [ ] Given a patched `app.db.database` read function that raises, when `load()` runs, then an error string is set, `loading` is False, and the previously loaded rows are unchanged.
- [ ] Given four constructed `AuditLog` instances — one duplicate-blocked, one with a `suspicious_pattern`, one with `success=False`, one plain — when each is passed through the derivation, then the verdicts are exactly **held**, **denied**, **fault**, **cleared**.
- [ ] Given an unauthenticated `AdminState`, when `load()` is called (the `/admin/stats`-with-no-session case), then the row list is empty and no read function was called — asserted with a patched/spied database module (Risk 1).
- [ ] Given an `AuditRow` produced from a seeded `AuditLog` whose previews are populated, when the row is inspected, then it has no `prompt_preview` and no `response_preview` attribute and neither preview string appears in any of its field values (Risk 2).
- [ ] Given `visible_rows`, when a verdict filter and a free-text filter are applied, then the returned rows match the expectation and the database module was not called again.

## Technical Notes

- New file `tests/test_admin_state.py` at the repo root. Follow the import preamble the existing chat tests use — [tests/test_chat_state.py](../../../tests/test_chat_state.py) and [tests/test_contrast.py:11-14](../../../tests/test_contrast.py) both note, verbatim: "Repo root, not `chat_ui/` — putting the inner package on `sys.path[0]` shadows the namespace package every other test module imports through."
- `pytest` + `pytest-asyncio` are already in use; PRD Section 8: "No new dependencies in either `requirements.txt`."
- Patch the database read functions where `admin_state` looks them up, not where they are defined, or the patch will not take.
- The four-verdict test is the regression guard for Risk 3 — include a fifth case: a `success=False` row that *also* carries `model_used`, asserted as **fault**.
- This story adds a new test file only. Every test named in PRD Section 11 — [tests/test_admin_auth.py](../../../tests/test_admin_auth.py), [tests/test_audit_router.py](../../../tests/test_audit_router.py), [tests/test_stats_router.py](../../../tests/test_stats_router.py), [tests/test_db.py](../../../tests/test_db.py), [tests/test_route_reservations.py](../../../tests/test_route_reservations.py), [tests/test_chat_state.py](../../../tests/test_chat_state.py) — must still pass **unmodified**.

## Dependencies

- **Blocked by**: STORY-002, STORY-003, STORY-004, STORY-005
- **Blocks**: STORY-020

## PRD Reference

Source: [`PRD-006/PRD.md`](../../PRDs/PRD-006-admin-console/PRD.md) — Section 11 (quality indicators), Section 12 Phase 1 validation, Risks 1, 2, 3
