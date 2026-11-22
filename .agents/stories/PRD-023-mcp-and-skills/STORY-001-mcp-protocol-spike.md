---
id: STORY-001
prd: PRD-023
slug: mcp-protocol-spike
title: "Spike — verify the MCP protocol facts and re-check the PRD's code evidence against main"
type: spike
priority: high
complexity: medium
phase: "1 - Verify the protocol and the clients"
status: done
labels: [spike, mcp, security]
epic_branch: epic/PRD-023-mcp-and-skills
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-001-mcp-protocol-spike.plan.md
report: .agents/reports/PRD-023-mcp-and-skills/STORY-001-mcp-protocol-spike.report.md
commit: 7e64933
depends_on: []
blocks: [STORY-003, STORY-004, STORY-005, STORY-008]
skills: []
created: 2026-11-22
updated: 2026-11-22
---

# STORY-001: Spike — verify the MCP protocol facts and re-check the PRD's code evidence against main

## Description

As the orchestrator of PRD-023, I want every MCP protocol assumption and every `file:line` the PRD cites checked against the spec and the code as it is today, so that later stories build on facts and not on draft-time assumptions.

## Acceptance Criteria

- [ ] Given the MCP specification, when the spike reads the current revisions, then `tests/corpora/mcp/SOURCES.md` records with pinned links: the supported revision strings (D17), whether JSON-RPC batching was removed in `2025-06-18`, the exact `Mcp-Session-Id` / `MCP-Protocol-Version` spellings, the 404-on-expired-session rule and whether a 404 means the request was not processed (T10), that a stateless server may omit the session header, `InitializeResult.instructions`, tool-name charset/length guidance (O7), the error code for an unknown tool, the `Origin` requirement (T11), and that `notifications/cancelled` is the cancellation method
- [ ] Given the PRD's Evidence list (read on `main` @ `2253871`), when the spike re-reads each cited location on the current `main`, then the report lists every divergence with its consequence for later stories — at least: `action_audit.record(decisions, identity, audit_ref=None, session_id=None)` (PRD-018) replacing `audit_id=`, `ACTION_DECISIONS_ADDED_COLUMNS` already existing with `write_id` (so PRD-023 extends it rather than adding a fourth mapping), PRD-018's journal and the O8 rule for pre-execution writes, and every place step 7c decisions are made today (buffered and PRD-021 real-time paths)
- [ ] Given each 'verify' item of Sections 6.1, 9.1, 9.2 and 15, when the spike is done, then each is marked resolved (with source) or carried as a stated limitation in `SOURCES.md`, and the threat table's T10/T11/T12 treatments are confirmed or corrected
- [ ] Given the spike, when finished, then no application code changes; the report proposes the exact PRD amendments (text and section) for the orchestrator to apply

## Technical Notes

- The report is the deliverable; `tests/corpora/mcp/SOURCES.md` is created here (STORY-002 and STORY-003 append to it).
- Read the spec from its published pages (modelcontextprotocol.io / the spec repo); pin each link to a revision or commit.
- Already seen by the orchestrator: `app/services/action_audit.py:214-238` documents that a PRD-023 pre-forward write must call `record()` without an `audit_ref` (or `database.insert_action_decisions` directly) so it commits or raises and never journals. Confirm and cite.
- Do not survey clients (STORY-002) or pin the SDK (STORY-003).

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-003, STORY-004, STORY-005, STORY-008

## PRD Reference

Source: [`PRD-023/PRD.md`](../../PRDs/PRD-023-mcp-and-skills/PRD.md) — Sections 6.1, 9.2, 15 (Facts to verify, Evidence), Phase 1
