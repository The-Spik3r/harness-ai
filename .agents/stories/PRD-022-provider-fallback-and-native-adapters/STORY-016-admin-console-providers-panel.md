---
id: STORY-016
prd: PRD-022
slug: admin-console-providers-panel
title: Admin console — Providers panel and attempt column on the Register
type: feature
priority: medium
complexity: medium
phase: "4 - Observability, streaming, docs"
status: todo
labels: [frontend, chat_ui, admin]
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
plan: null
report: null
commit: null
depends_on: [STORY-015]
blocks: [STORY-018]
skills: [frontend-design]
created: 2026-11-20
updated: 2026-11-20
---

# STORY-016: Admin console Providers panel

## Description

As an operator in the admin console, I want a Providers panel beside the Storage panel and an attempt column on the Register, so that I see unhealthy providers and fallback attempts without a shell.

## Acceptance Criteria

- [ ] Given the admin console, when an admin with `stats:read` opens it, then a Providers panel shows, per provider, the breaker state, since, consecutive failures, last failure class and retry-after, plus the counters, read in-process from `providers_status()` (no HTTP call), beside PRD-018's Storage panel
- [ ] Given the Register, when rows are listed, then it shows `attempt` (and keeps PRD-020's `provider` column); failed attempts remain visible as their own rows; rows of one request can be filtered by `request_id`
- [ ] Given the panel's styling, when built, then it follows `chat_ui/chat_ui/theme.py` and the existing Storage panel's structure; the chat UI startup guard test (`tests/test_chat_ui_startup_guard.py`) passes
- [ ] Given a user without `stats:read`, when they open the console, then the Providers panel is not shown (same rule as Storage)

## Technical Notes

- `chat_ui/chat_ui/admin_*.py` (find the Storage panel added by PRD-018 and the Register's PRD-020 `provider` column); `chat_ui/chat_ui/theme.py`.
- Skill `frontend-design` (verbatim): "Guidance for distinctive, intentional visual design when building new UI or reshaping an existing one. Helps with aesthetic direction, typography, and making choices that don't read as templated defaults." PRD Section 8: "distinctive, intentional visual design … making choices that don't read as templated defaults". The panel follows `chat_ui/chat_ui/theme.py`.
- Validation: the chat_ui probe form in the brief.
- Orchestrator decision (STORY-015): read `health.providers_status(names)` with names from `provider_registry.current().providers`, as `GET /providers/status` does (`app/routers/admin.py`); each breaker is PRD-018's `BreakerStatus` (`since` always a UTC string, never null). `SUMMARY_FIGURES` is now 16: the last three (`fallback_answers`, `failed_attempts`, `answers_by_provider`) are `/stats`-only, and `AdminState.load()` commits only the figures `_READS` names (`chat_ui/chat_ui/admin_state.py`). The Providers panel must not add them to `_READS`.

## Dependencies

- **Blocked by**: STORY-015
- **Blocks**: STORY-018

## PRD Reference

Source: [`PRD-022/PRD.md`](../../PRDs/PRD-022-provider-fallback-and-native-adapters/PRD.md) — Sections 4 (Audit and observability), 8, F9
