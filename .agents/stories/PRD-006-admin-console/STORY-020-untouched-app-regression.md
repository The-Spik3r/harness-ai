---
id: STORY-020
prd: PRD-006
slug: untouched-app-regression
title: "Full-suite regression and the proof that nothing under app/ changed"
type: technical
priority: high
complexity: small
phase: "4 - Hardening"
status: todo
labels: [tests, verification, admin]
epic_branch: epic/PRD-006-admin-console
plan: null
report: null
commit: null
depends_on: [STORY-006, STORY-016, STORY-017, STORY-018, STORY-019]
blocks: []
skills: [reflex-process-management]
created: 2026-08-28
updated: 2026-08-28
---

# STORY-020: Full-suite regression and the proof that nothing under app/ changed

## Description

As an integrating developer, I want the console confined to `chat_ui/` with no new route on the FastAPI app, so that the REST contract, the audit schema and PRD-001/003's test suites are provably unchanged (PRD Section 5, story 9).

## Acceptance Criteria

- [ ] Given the full test suite, when it runs, then it is green — including [tests/test_admin_auth.py](../../../tests/test_admin_auth.py), [tests/test_audit_router.py](../../../tests/test_audit_router.py), [tests/test_stats_router.py](../../../tests/test_stats_router.py), [tests/test_db.py](../../../tests/test_db.py), [tests/test_route_reservations.py](../../../tests/test_route_reservations.py), [tests/test_chat_state.py](../../../tests/test_chat_state.py), [tests/test_copy.py](../../../tests/test_copy.py) and [tests/test_contrast.py](../../../tests/test_contrast.py), each passing **unmodified** except where this PRD's own stories added assertions to `test_copy.py` and `test_contrast.py`.
- [ ] Given `git diff main --stat`, when it is run, then **no file under `app/` is changed** — no new database function, no query parameter, no schema migration, no change to `AuditQueryEntry` or `StatsResponse`.
- [ ] Given both `requirements.txt` files, when they are diffed against `main`, then neither has a new dependency.
- [ ] Given the [Caddyfile](../../../Caddyfile) and [rxconfig.py](../../../chat_ui/rxconfig.py), when they are diffed, then neither is changed.
- [ ] Given the MVP walkthrough, when it is performed end to end, then an admin can open `/admin/audit`, enter the token, and answer "what was blocked, what failed, and how much of it touched PII" without a terminal — every Section 11 functional checkbox verified and recorded.
- [ ] Given the chat surface, when it is exercised through its six outcomes, then it behaves exactly as PRD-004 shipped it.

## Technical Notes

- PRD Section 11, verbatim: "`tests/test_audit_router.py`, `tests/test_stats_router.py`, `tests/test_admin_auth.py`, `tests/test_db.py`, `tests/test_route_reservations.py` and `tests/test_chat_state.py` pass **unmodified** — the proof that `app/` and the chat are untouched" and "`git diff main --stat` shows no file under `app/` changed."
- Run the `git diff main --stat` check explicitly and paste its output into the story report; the claim is only as good as the evidence.
- Per `chat_ui/AGENTS.md`, verbatim: "When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill for the correct sequence and error investigation steps."
- If a genuine defect in `app/` surfaces during this pass, do **not** fix it here — PRD Section 4 puts every change under `app/` out of scope and Section 13 already records the three known ones (`error_kind`, projecting `success`/`error_message`, `count_answered_queries()`). Record it as a follow-up.
- Walk PRD Section 11's functional list item by item against a seeded database containing at least one row of each verdict, at least one PII row and at least one row with an `error_message`.

## Dependencies

- **Blocked by**: STORY-006, STORY-016, STORY-017, STORY-018, STORY-019
- **Blocks**: None

## PRD Reference

Source: [`PRD-006/PRD.md`](../../PRDs/PRD-006-admin-console/PRD.md) — Section 5 (story 9), Section 10, Section 11, Section 12 Phase 4
