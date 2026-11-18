---
id: STORY-002
prd: PRD-021
slug: permissions-and-switch
title: Stream permissions and the STREAMING_ENABLED switch
type: feature
priority: high
complexity: small
phase: "1 - Survey and seams"
status: todo
labels: [backend, rbac, config]
epic_branch: epic/PRD-021-realtime-streaming
plan: null
report: null
commit: null
depends_on: []
blocks: [STORY-005]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-002: Stream permissions and the STREAMING_ENABLED switch

## Description

As a security admin, I want two new permissions that I can grant per role through `RBAC_ROLES_FILE`, and a master switch that is off by default, so that nobody gets real-time output or reasoning until I decide it.

## Acceptance Criteria

- [ ] Given `app/services/authz.py`, when imported, then `PERMISSION_STREAM_REALTIME == "stream:realtime"`, `PERMISSION_REASONING_VIEW == "reasoning:view"`, `STREAM_PERMISSIONS` is the frozenset of both, and both are in `_KNOWN_PERMISSIONS` (unioned like `ACTION_PERMISSIONS`)
- [ ] Given the built-in matrix, when inspected, then no built-in role (`admin` included) holds either permission, and a comment beside `ROLE_PERMISSIONS` says why (who may read unfinished model output is a deployment decision)
- [ ] Given an `RBAC_ROLES_FILE` granting `stream:realtime` to a role, when `load()` runs, then it is accepted, and `holds(role, "stream:realtime")` is true for that role only; with `RBAC_ENABLED=false` and the built-in matrix, `holds()` is false for every role (T8)
- [ ] Given `app/config.py`, when settings load with no env, then `STREAMING_ENABLED is False`, `STREAM_HOLDBACK_MAX_CHARACTERS == 400` (validated `100 ≤ n ≤ 4000`) and `STREAM_COALESCE_MS == 50` (validated `0 ≤ n ≤ 500`); out-of-range values fail at startup with a message naming the variable
- [ ] Given the change, when the existing authz and config tests run, then they pass unchanged

## Technical Notes

- `authz.py:29-49` (`ACTION_PERMISSIONS` union into `_KNOWN_PERMISSIONS`), `:57-74` (matrix), `:96-126` (`load()` unknown-permission check), `:168-185` (`holds()`, no RBAC bypass).
- Settings are only declared here; nothing reads them yet (STORY-005 reads `STREAMING_ENABLED`, STORY-008 the hold-back bound, STORY-010 the coalesce interval). Follow the existing validator style in `app/config.py`.
- Add the three variables to `.env.example` only in STORY-016 (docs), not here — unless a test of `.env.example` coverage requires it now; then add them commented with the default.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-005

## PRD Reference

Source: [`PRD-021/PRD.md`](../../PRDs/PRD-021-realtime-streaming/PRD.md) — Sections 4 (Permissions and switch), F1, 9.1, 9.3, D1, D2
