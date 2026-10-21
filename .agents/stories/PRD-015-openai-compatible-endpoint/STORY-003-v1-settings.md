---
id: STORY-003
prd: PRD-015
slug: v1-settings
title: "V1_ENABLED and V1_SSE_KEEPALIVE_SECONDS settings with startup validators"
type: technical
priority: medium
complexity: small
phase: "1 - Foundations"
status: todo
labels: [backend, config]
epic_branch: epic/PRD-015-openai-compatible-endpoint
plan: null
report: null
commit: null
depends_on: []
blocks: [STORY-009, STORY-013]
skills: []
created: 2026-10-21
updated: 2026-10-21
---

# STORY-003: V1_ENABLED and V1_SSE_KEEPALIVE_SECONDS settings with startup validators

## Description

As a platform operator, I want a switch for the `/v1` ingress and a bounded keep-alive interval, both validated at startup, so that I can turn the door off and a mis-set value stops the boot with a message naming it.

## Acceptance Criteria

- [ ] Given nothing configured, when settings load, then `V1_ENABLED is True` and `V1_SSE_KEEPALIVE_SECONDS == 10`.
- [ ] Given `V1_SSE_KEEPALIVE_SECONDS` of `0`, `-1` or `61`, when settings load, then startup fails with a message naming the setting, the value, the accepted range (`> 0` and `<= 60`) and an example; `0.5` and `60` are accepted.
- [ ] Given `V1_ENABLED=false`, when settings load, then it parses as `False` (the router mount that reads it is STORY-009).
- [ ] Given the existing config tests, when they run, then none changes.

## Technical Notes

- `app/config.py`: two fields beside the PRD-013 settings, each with a validator following `_validate_openrouter_timeout_seconds`; add both to the setting-description map at the top of the module if it lists every setting.
- No setting chooses the `/v1` profile: it is the literal `"code"` at the call site (PRD Section 9.3, PRD-011 D2). Do not add one.
- `.env.example` entries are written in STORY-019 with the rest of the documentation.
- Tests in `tests/test_config.py`; no DB.
- Skills: none applicable.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-009, STORY-013

## PRD Reference

Source: [`PRD-015-openai-compatible-endpoint/PRD.md`](../../PRDs/PRD-015-openai-compatible-endpoint/PRD.md) — section 9.3
