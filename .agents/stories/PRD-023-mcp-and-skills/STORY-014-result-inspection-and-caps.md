---
id: STORY-014
prd: PRD-023
slug: result-inspection-and-caps
title: "Results: size cap, pattern inspection under the `tool` cell, uninspected counts"
type: feature
priority: high
complexity: medium
phase: "3 - The gateway"
status: todo
labels: [mcp, security, patterns]
epic_branch: epic/PRD-023-mcp-and-skills
plan: null
report: null
commit: null
depends_on: [STORY-013]
blocks: [STORY-019]
skills: []
created: 2026-11-22
updated: 2026-11-22
---

# STORY-014: Results: size cap, pattern inspection under the `tool` cell, uninspected counts

## Description

As a security admin, I want tool results inspected as untrusted `tool` content and capped in size, so that indirect prompt injection is flagged and a dump cannot flood the agent.

## Acceptance Criteria

- [ ] Given the stub's `huge` result over `MCP_MAX_RESULT_BYTES` (or the server's `max_result_bytes`), when returned, then the agent gets `isError: true` with `[harness] the result of <name> (<id>) exceeded <n> bytes and was not returned; the call ran` and `outcome='result_too_large'`
- [ ] Given the stub's `inject` result, when returned, then it is unmodified and `result_flags` names the injection list and pattern id but never the matched text
- [ ] Given a deployment profile whose `tool` cell is `block`, when a result hits, then it is replaced by an error result with `outcome='result_blocked'`
- [ ] Given `image`, `audio` and `resource_link` blocks, when returned, then they pass through uninspected and `result_flags` records `{"uninspected": n}`; text, embedded-resource text and canonical `structuredContent` are inspected as one `tool` message under the `code` profile
- [ ] Given any result, when recorded, then `result_bytes` and `result_hash` (`hash_prompt` over the canonical result) are stored and the result itself is not; no PII redaction is applied (O5)

## Technical Notes

- `pattern_detector.inspect` and the `code` profile's `tool` cell (`app/services/pattern_config.py`).
- Extends STORY-013's M9 in `mcp_gateway.py`.

## Dependencies

- **Blocked by**: STORY-013
- **Blocks**: STORY-019

## PRD Reference

Source: [`PRD-023/PRD.md`](../../PRDs/PRD-023-mcp-and-skills/PRD.md) — Sections 6.7, F7, D11, O5, T5, T14, T15
