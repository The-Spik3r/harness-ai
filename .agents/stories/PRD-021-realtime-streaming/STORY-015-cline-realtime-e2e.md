---
id: STORY-015
prd: PRD-021
slug: cline-realtime-e2e
title: Cline end-to-end on a real-time stream
type: technical
priority: low
complexity: small
phase: "4 - Clients and docs"
status: todo
labels: [testing, e2e, v1]
epic_branch: epic/PRD-021-realtime-streaming
plan: null
report: null
commit: null
depends_on: [STORY-001, STORY-004, STORY-010]
blocks: [STORY-016]
skills: []
created: 2026-11-18
updated: 2026-11-18
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

## Dependencies

- **Blocked by**: STORY-001, STORY-004, STORY-010
- **Blocks**: STORY-016

## PRD Reference

Source: [`PRD-021/PRD.md`](../../PRDs/PRD-021-realtime-streaming/PRD.md) — Sections 8, 12 Phase 4, Risk 4
