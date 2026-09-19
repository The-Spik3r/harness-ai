---
id: STORY-002
prd: PRD-010
slug: timeout-context-and-executor-settings
title: "Settings: upstream timeout, context limits and pipeline executor size"
type: technical
priority: high
complexity: small
phase: "1 - Model, settings, client"
status: done
labels: [backend, config]
epic_branch: epic/PRD-010-multi-turn-pipeline
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-002-timeout-context-and-executor-settings.plan.md
report: .agents/reports/PRD-010-multi-turn-pipeline/STORY-002-timeout-context-and-executor-settings.report.md
commit: 6c7048e
depends_on: []
blocks: [STORY-005, STORY-006, STORY-008]
skills: []
created: 2026-09-17
updated: 2026-09-17
---

# STORY-002: Settings: upstream timeout, context limits and pipeline executor size

## Description

As a platform operator, I want the upstream timeout, the context limits and the pipeline executor size to be settings with safe defaults and startup validation, so that I can tune them per deployment and a bad value fails at boot rather than in production.

## Acceptance Criteria

- [ ] Given [app/config.py](../../../app/config.py), when `Settings` is read, then it has `OPENROUTER_TIMEOUT_SECONDS: float = 120.0`, `CONTEXT_MAX_MESSAGES: int = 100`, `CONTEXT_MAX_CHARACTERS: int = 200_000` and `PIPELINE_MAX_WORKERS: int = 32`, grouped under a `# Multi-turn pipeline (PRD-010)` comment.
- [ ] Given `OPENROUTER_TIMEOUT_SECONDS=0` or a negative value, when `Settings()` is constructed, then it raises a validation error naming the setting, the value received, and that it is the upstream request timeout in seconds.
- [ ] Given `CONTEXT_MAX_MESSAGES=0`, `CONTEXT_MAX_CHARACTERS=0` or `PIPELINE_MAX_WORKERS=0` (and negatives), when `Settings()` is constructed, then each raises a validation error naming the setting and what it controls, in the `_validate_chat_session_limit` style. Parametrized tests in [tests/test_config.py](../../../tests/test_config.py) cover each.
- [ ] Given no environment overrides, when `Settings()` is constructed, then the four defaults above hold (test).
- [ ] Given the full test suite, when this story lands, then it is green. No code reads the new settings yet, and each field's comment names the story that consumes it (STORY-005, STORY-006, STORY-008).

## Technical Notes

- Follow `_validate_chat_session_limit` in [app/config.py](../../../app/config.py): a `field_validator` per setting, or one shared validator over the three integer fields, with an instructive message saying what the value controls and what to set instead.
- `CONTEXT_MAX_CHARACTERS` is the sum of `len(message.content)` over all messages. Characters, not tokens, is a documented proxy (PRD Section 4, Out of Scope). Say so in the comment.
- Leave `.env.example` alone. STORY-018 documents all four settings together with the README.
- Existing tests that construct `Settings()` with a minimal environment must not break. Every new field has a default.
- Skills: none applicable.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-005, STORY-006, STORY-008

## PRD Reference

Source: [`PRD-010-multi-turn-pipeline/PRD.md`](../../PRDs/PRD-010-multi-turn-pipeline/PRD.md) — sections 4 (Settings), 7 (F2), 9.3
