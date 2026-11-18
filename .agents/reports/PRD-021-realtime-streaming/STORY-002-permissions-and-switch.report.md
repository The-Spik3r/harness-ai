---
story: STORY-002
prd: PRD-021
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-002-permissions-and-switch.plan.md
epic_branch: epic/PRD-021-realtime-streaming
commit: pending
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report - STORY-002: Stream permissions and the STREAMING_ENABLED switch

**Plan**: `.agents/plans/PRD-021-realtime-streaming/completed/STORY-002-permissions-and-switch.plan.md`
**Epic Branch**: `epic/PRD-021-realtime-streaming`
**Commit**: `pending`

## Summary

Declared `stream:realtime` and `reasoning:view` in `authz.py` (constants, `STREAM_PERMISSIONS`, added to `_KNOWN_PERMISSIONS`; no built-in role holds either). Declared `STREAMING_ENABLED` (False), `STREAM_HOLDBACK_MAX_CHARACTERS` (400, 100..4000) and `STREAM_COALESCE_MS` (50, 0..500) in `config.py` with startup validators. Nothing reads the settings yet.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Permissions + known set + matrix comment | `app/services/authz.py` | done |
| 2 | Settings + validators | `app/config.py` | done |
| 3 | authz tests; guard assertion updated | `tests/test_authz.py` | done |
| 4 | config tests | `tests/test_config.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests (authz, config, providers_docs, untouched_app) | 375 passed, 0 failed, 0 skipped |
| E2E | grant path proven by the `load()` tmp-file test; app imports |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

`tests/test_authz.py::test_known_permissions_are_the_original_five_plus_the_six` had its assertion pair updated (known set includes `STREAM_PERMISSIONS`, 13 entries) with a comment citing PRD-021 D1; function name kept. Accepted by the orchestrator; the story's "existing tests pass unchanged" cannot hold for this one test.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_authz.py` | constants/frozenset/known; no built-in role; load grant accepted (both); misspelling refused; holds false RBAC on/off; authorize-vs-holds contrast |
| `tests/test_config.py` | defaults; true parses; holdback and coalesce out of range; bounds accepted |

## Acceptance Criteria

- [x] AC1 constants, frozenset, known set
- [x] AC2 no built-in role holds either; comment
- [x] AC3 file grant accepted; holds() role-only; RBAC off false
- [x] AC4 defaults, ranges, message names the variable
- [x] AC5 existing tests pass (one assertion pair updated, see Deviations)
