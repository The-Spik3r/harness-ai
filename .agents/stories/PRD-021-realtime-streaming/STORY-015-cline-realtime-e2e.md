---
id: STORY-015
prd: PRD-021
slug: cline-realtime-e2e
title: Cline end-to-end on a real-time stream
type: technical
priority: low
complexity: small
phase: "4 - Clients and docs"
status: done
labels: [testing, e2e, v1]
epic_branch: epic/PRD-021-realtime-streaming
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-015-cline-realtime-e2e.plan.md
report: .agents/reports/PRD-021-realtime-streaming/STORY-015-cline-realtime-e2e.report.md
commit: pending
depends_on: [STORY-001, STORY-004, STORY-010]
blocks: [STORY-016]
skills: []
created: 2026-11-18
updated: 2026-11-19
---

# STORY-015: Cline end-to-end on a real-time stream

## Description

As an integrating developer using Cline, I want the same real-time proof as for OpenCode, so that the docs can list Cline as verified or name what does not work.

## Acceptance Criteria

- [ ] Given PRD-017's opt-in Cline E2E script and the streaming stub, when Cline runs against a harness with the switch on and a role holding `stream:realtime`, then the text arrives and the run completes, or the report states precisely why Cline cannot be driven here
- [ ] Given a scripted denied tool call, when Cline runs, then the denial note is shown and no fragment was released
- [ ] Given both grants, when Cline runs, then the report records whether Cline displays `reasoning_content`
- [ ] Given the default suite, when it runs without the opt-in, then the tests are skipped

## Technical Notes

- Reuse `tests/test_e2e_cline_script.py`. If Cline is not installed or cannot be scripted on this machine, record that in the report (the story is done when the scripted test exists, is skipped by default, and the report states the outcome) — do not install global tooling without telling the orchestrator.
- Orchestrator note (STORY-001): Cline 3.0.74 is installed at `tests/e2e/.clients/cline`; its AI SDK reads `delta.reasoning_content ?? delta.reasoning`.
- Orchestrator decision (STORY-014): mirror STORY-014's design: a new opt-in module beside the PRD-017 Cline test (left unchanged), `_live.Recorder(keep_sse=True)` as the harness-side proof, stub `stream` shape (`chunk_chars` 6-8, `delay_ms` 60), a throwaway libSQL on its own port, `STREAMING_ENABLED=true`, a file-mode registry with `streaming`/`reasoning` capabilities and an `RBAC_ROLES_FILE` that redefines `user`/`auditor` (`manage_users.py` only accepts admin|auditor|user). Every row must show `streamed_realtime` true (a buffered fallback fails). Reuse `tests/e2e/_opencode_realtime.py` helpers where they are client-neutral. "Reasoning displayed" is an observation, the sentinel-never-in-content/files/audit assertions are hard.

## Dependencies

- **Blocked by**: STORY-001, STORY-004, STORY-010
- **Blocks**: STORY-016

## PRD Reference

Source: [`PRD-021/PRD.md`](../../PRDs/PRD-021-realtime-streaming/PRD.md) — Sections 8, 12 Phase 4, Risk 4
