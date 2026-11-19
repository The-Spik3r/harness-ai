---
story: STORY-016
prd: PRD-021
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-016-streaming-docs.plan.md
epic_branch: epic/PRD-021-realtime-streaming
commit: pending
status: COMPLETE
completed: 2026-11-19
---

# Implementation Report - STORY-016: Document real-time streaming, grants and progress feedback

**Plan**: `.agents/plans/PRD-021-realtime-streaming/completed/STORY-016-streaming-docs.plan.md`
**Epic Branch**: `epic/PRD-021-realtime-streaming`
**Commit**: `pending`

## Summary

Docs only, no `app/` change. `docs/features.md` gets a "Real-time delivery" subsection (switch, two permissions with a roles-file example, visibility matrix, chunk sequence, verdicts and error-after-commit, the output gate, held tool calls, costs with conditions, four residual risks, verified clients, audit fields, chat UI, out of scope) and its buffered-only statements are rewritten. Settings are in `.env.example` and `docs/configuration.md`; the README has a "Real-time streaming" section; `docs/api.md` documents the four `GET /audit` fields, `?completion_id=` and the real-time chunk shapes; `docs/roadmap.md` marks PRD-021 delivered with the seven Section 13 items unchecked.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | features.md: rewrite buffered statements, new subsection | `docs/features.md` | done |
| 2 | Three settings | `.env.example`, `docs/configuration.md` | done |
| 3 | README section, features row, limitation, roadmap line | `README.md` | done |
| 4 | Roadmap entry, Section 13 items | `docs/roadmap.md` | done |
| 5 | Audit fields, filter, chunk shapes | `docs/api.md` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests | 282 passed (`test_providers_docs.py`, `test_config.py`, `test_caddyfile_routes.py`) |
| E2E (plan: defaults match `app/config.py`, links resolve, no live-model claim) | done by reading: defaults and ranges copied from `app/config.py:393-395` and the validators; new anchors `#real-time-delivery`, `#real-time-streaming` exist; both client runs are labelled stub upstream |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

`docs/features.md`, `docs/api.md`, `docs/configuration.md`, `docs/roadmap.md`, `README.md`, `.env.example` (UPDATE).

## Deviations from Plan

- The first-content figure is documented as a test-enforced bound (`tests/test_v1_realtime.py`), not a measurement.
- The STORY-008 numbers are given without a machine or OS: the report states none. A condition-complete measurement would need a rerun of `scripts/measure_stream_gate_latency.py`.
- Did not add "GET /audit/export": no such route exists.

## Tests Written

None (docs only).

## Acceptance Criteria

- [x] AC1 features.md: buffered vs real time, two permissions, switch, held calls, `reasoning_content`, error after commit, residual risks
- [x] AC2 gate and latency numbers with their conditions
- [x] AC3 three variables with defaults in `.env.example` and README; `RBAC_ROLES_FILE` example grants `stream:realtime`; legacy never streams
- [x] AC4 roadmap delivered, Section 13 items, verified clients (OpenCode 2.3.2, Cline 3.0.74, stub upstream)
