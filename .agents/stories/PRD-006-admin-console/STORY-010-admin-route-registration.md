---
id: STORY-010
prd: PRD-006
slug: admin-route-registration
title: "Register /admin, /admin/audit and /admin/stats without touching a reserved route"
type: technical
priority: high
complexity: small
phase: "2 - The register"
status: done
labels: [ui, reflex, routing, admin]
epic_branch: epic/PRD-006-admin-console
plan: .agents/plans/PRD-006-admin-console/completed/STORY-010-admin-route-registration.plan.md
report: .agents/reports/PRD-006-admin-console/STORY-010-admin-route-registration.report.md
commit: null
depends_on: [STORY-009]
blocks: [STORY-011, STORY-015]
skills: [reflex-docs, reflex-process-management]
created: 2026-08-28
updated: 2026-08-31
---

# STORY-010: Register /admin, /admin/audit and /admin/stats without touching a reserved route

## Description

As an integrating developer, I want the console's two pages registered under `/admin` with no new FastAPI route, so that the REST contract and the reserved-route test hold unmodified (PRD Section 5, story 9).

## Acceptance Criteria

- [ ] Given [chat_ui/chat_ui/chat_ui.py](../../../chat_ui/chat_ui/chat_ui.py), when the console is added, then `app.add_page(...)` registers `/admin/audit` and `/admin/stats`, and `/admin` lands on the register.
- [ ] Given the app, when its routes are listed, then no route is added to the FastAPI app — `app/routers/` is unchanged and `POST /query`, `GET /audit`, `GET /stats`, `GET /health` keep their exact contracts.
- [ ] Given [tests/test_route_reservations.py](../../../tests/test_route_reservations.py), when the suite runs, then it passes **unmodified** — `/ping`, `/_event` and `/_upload` remain reserved and uncollided.
- [ ] Given the [Caddyfile](../../../Caddyfile), when it is inspected, then it is unchanged — `/admin/*` is not in the `@backend_routes` matcher and falls through to the static `file_server`.
- [ ] Given each admin page, when it is opened, then it renders the shell from [[STORY-009]] and loads no data until the gate passes.
- [ ] Given the existing chat page at `/`, when it is opened after this change, then it renders exactly as before.

## Technical Notes

- The only change to [chat_ui/chat_ui/chat_ui.py](../../../chat_ui/chat_ui/chat_ui.py) is the two `app.add_page` calls and their imports; leave `init_db()`, the `api_transformer` wiring and `register_lifespan_task(pii_redactor.load)` untouched — the comments there explain why each exists.
- PRD Section 6 routing constraint: "`/audit` and `/stats` are taken — by `app/routers/admin.py`, by `tests/test_route_reservations.py`, and by the `Caddyfile`'s `@backend_routes` matcher... The console therefore lives at `/admin/audit` and `/admin/stats`, which fall through to Caddy's static `try_files` like every other Reflex page and need **no Caddyfile change**."
- Per `chat_ui/AGENTS.md`, verbatim: "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs." Confirm `app.add_page(..., route=...)` and how `/admin` should redirect or alias to the register.
- Per `chat_ui/AGENTS.md`, verbatim: "When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill for the correct sequence and error investigation steps." This is the first story that compiles the new pages, so follow it here.
- Consider extending [tests/test_chat_components_import.py](../../../tests/test_chat_components_import.py) with an equivalent import smoke test for the admin components, so a broken import fails a test rather than the dev server.

## Dependencies

- **Blocked by**: STORY-009
- **Blocks**: STORY-011, STORY-015

## PRD Reference

Source: [`PRD-006/PRD.md`](../../PRDs/PRD-006-admin-console/PRD.md) — Section 4, Section 5 (story 9), Section 6 (routing constraint), Section 9, Section 10, Section 12 Phase 2
