---
id: STORY-003
prd: PRD-023
slug: mcp-sdk-pin
title: "Pin the `mcp` SDK and prove its client behaviours offline"
type: technical
priority: high
complexity: medium
phase: "1 - Verify the protocol and the clients"
status: todo
labels: [mcp, dependencies, security]
epic_branch: epic/PRD-023-mcp-and-skills
plan: null
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-009, STORY-010]
skills: []
created: 2026-11-22
updated: 2026-11-22
---

# STORY-003: Pin the `mcp` SDK and prove its client behaviours offline

## Description

As a platform operator, I want the `mcp` SDK pinned exactly and its client behaviour proved by tests, so that the southbound client rests on verified facts and an upgrade is a deliberate story.

## Acceptance Criteria

- [ ] Given `requirements.txt`, when the story is done, then `mcp==<exact version>` is pinned (the `sqlglot==30.27.0` convention) and the report lists its transitive dependencies diffed against existing pins, with no existing pin changed unless justified in the report
- [ ] Given the SDK, when tests run, then `tests/test_prd023_mcp_sdk_facts.py` proves against a localhost server (no internet): the module paths `mcp.ClientSession` and the Streamable HTTP client, how static headers are set, that a 30x redirect is not followed (or how to disable following), how a per-call timeout is applied, and how the client answers a server-to-client request (`sampling/createMessage`) when no callback is registered
- [ ] Given the PRD-016-era `mcp` absence, when the SDK is installed, then `.venv` imports work and `from app.main import app` still imports
- [ ] Given any SDK fact that contradicts Section 8 or D14/D16/T12, when found, then the report names it and the PRD amendment it needs

## Technical Notes

- Depends on STORY-001's protocol findings (revision strings).
- The test may start the SDK's `FastMCP` server in a subprocess or thread on localhost; that is test infrastructure only. STORY-009 builds the real stub server.
- Check CI installs from `requirements.txt` (`.github/workflows/`).

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-009, STORY-010

## PRD Reference

Source: [`PRD-023/PRD.md`](../../PRDs/PRD-023-mcp-and-skills/PRD.md) — Sections 8, 15 (Facts to verify: mcp SDK), D18, R1
