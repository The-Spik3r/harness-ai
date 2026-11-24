---
id: STORY-020
prd: PRD-023
slug: e2e-opencode-cline
title: "E2E (opt-in): OpenCode and the Cline CLI through `/mcp` against the stub"
type: technical
priority: medium
complexity: medium
phase: "4 - Bridge, evidence and clients"
status: done
labels: [tests, e2e, clients]
epic_branch: epic/PRD-023-mcp-and-skills
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-020-e2e-opencode-cline.plan.md
report: .agents/reports/PRD-023-mcp-and-skills/STORY-020-e2e-opencode-cline.report.md
commit: d2ffa6c
depends_on: [STORY-019, STORY-002]
blocks: [STORY-021]
skills: []
created: 2026-11-22
updated: 2026-11-24
---

# STORY-020: E2E (opt-in): OpenCode and the Cline CLI through `/mcp` against the stub

## Description

As an integrating developer, I want real OpenCode and Cline sessions to list their skill's tools and complete one allowed and one denied call through `/mcp`, so that the gateway is proven with the clients it targets.

## Acceptance Criteria

- [x] Given `--run-e2e` and the installed OpenCode (config `type: remote`, static `Authorization`, `codemode: false`), when driven against the harness and stub, then it lists its skill's tools and completes one allowed and one denied call, with matching rows
- [x] Given `--run-e2e` and the installed Cline CLI, when driven the same way, then the same holds
- [x] Given no `--run-e2e`, when the suite runs, then these tests are skipped (CI unaffected)

## Technical Notes

- Orchestrator decision (STORY-002): OpenCode 2.3.2 config: `mcp.servers.harness` with `type: remote`, `url`, `headers`, `codemode: false`. It uses the `disabled` key, not `enabled`. Drive it only with `run --standalone` against a fake provider (repo E2E rule). For the Cline CLI 3.0.74 (`tests/e2e/.clients/cline`), the entry needs `"type": "streamableHttp"`, or it falls back to SSE. Use the scratchpad drivers' approach from STORY-002's report.
- Use the client versions and configs STORY-002 recorded; follow PRD-021's E2E pattern (`tests/test_e2e_cline_realtime_script.py`).
- If a client cannot connect without weakening auth, document it as unsupported (R2) rather than work around it.

## Dependencies

- **Blocked by**: STORY-019, STORY-002
- **Blocks**: STORY-021

## PRD Reference

Source: [`PRD-023/PRD.md`](../../PRDs/PRD-023-mcp-and-skills/PRD.md) — Sections 4 (Test infrastructure), 11 (MVP definition), F12, R2
