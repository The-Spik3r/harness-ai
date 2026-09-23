---
id: STORY-007
prd: PRD-011
slug: startup-load-and-sample-file
title: "pattern_config.load() in both lifespans, and a working sample file"
type: technical
priority: high
complexity: small
phase: "2 - Configuration and profiles"
status: done
labels: [backend, config, startup]
epic_branch: epic/PRD-011-pattern-policy
plan: .agents/plans/PRD-011-pattern-policy/completed/STORY-007-startup-load-and-sample-file.plan.md
report: .agents/reports/PRD-011-pattern-policy/STORY-007-startup-load-and-sample-file.report.md
commit: efb1924
depends_on: [STORY-005, STORY-006]
blocks: [STORY-013]
skills: []
created: 2026-09-22
updated: 2026-09-22
---

# STORY-007: pattern_config.load() in both lifespans, and a working sample file

## Description

As a platform operator, I want the patterns file loaded and validated at startup whichever way the app is launched, so that a broken file can never reach a running deployment.

## Acceptance Criteria

- [ ] Given [app/main.py](../../../app/main.py)'s lifespan, when the app starts, then `pattern_config.load()` runs beside `authz.load()`, and a `PatternConfigError` propagates: the process does not start.
- [ ] Given `chat_ui/chat_ui/chat_ui.py`, when the Reflex backend starts with the FastAPI app mounted through `api_transformer`, then `pattern_config.load()` runs there too — that mount bypasses `app.main`'s lifespan entirely, which is why `init_db()` and `authz.load()` are already registered in both places (PRD-007).
- [ ] Given `examples/patterns.yaml`, when it is read, then it is the file in PRD Section 6.3 verbatim, comments included, and a test loads it through `pattern_config.load()` and asserts the resulting policy equals the built-in policy — a sample that does not parse is worse than no sample (PRD Section 11, Quality indicators).
- [ ] Given a test that points `PATTERNS_FILE` at a malformed file and starts the app, when startup runs, then it fails with `PatternConfigError`, asserted for both entry points.
- [ ] Given an existing deployment with no `PATTERNS_FILE` set, when it starts, then no file is read, the built-in policy stands, and no existing startup test changes.

## Technical Notes

- Both call sites, not one. `chat_ui/chat_ui/chat_ui.py`'s `register_lifespan_task` path is the one that actually runs in production (`reflex run --env prod --backend-only`); `app/main.py`'s lifespan serves plain uvicorn and the test client. Missing either is the failure mode PRD-007 documented and PRD Section 6.9 turned into a rule.
- Order within the lifespan: after `authz.load()` is fine; both are pure configuration loads with no dependency between them. Keep them adjacent so the next config loader (PRD-015) has an obvious home.
- `examples/` does not exist yet — create it. Keep the sample identical to PRD Section 6.3 so the PRD and the shipped file cannot drift; the test asserting policy equality is what enforces that.
- `tests/test_chat_ui_startup_guard.py` is the existing home for mounted-app startup assertions; extend it rather than adding a parallel file.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-005, STORY-006
- **Blocks**: STORY-013

## PRD Reference

Source: [`PRD-011-pattern-policy/PRD.md`](../../PRDs/PRD-011-pattern-policy/PRD.md) — sections 6.3, 6.8, 6.9, 7 (F3), 11 (Quality indicators), 12 (Phase 2)
