---
id: STORY-017
prd: PRD-023
slug: admin-api
title: "Admin API: `GET /audit/actions` MCP filters and fields, `GET /skills`"
type: feature
priority: medium
complexity: medium
phase: "4 - Bridge, evidence and clients"
status: in-progress
labels: [api, admin, audit]
epic_branch: epic/PRD-023-mcp-and-skills
plan: .agents/plans/PRD-023-mcp-and-skills/STORY-017-admin-api.plan.md
report: null
commit: null
depends_on: [STORY-008, STORY-007]
blocks: [STORY-018]
skills: []
created: 2026-11-22
updated: 2026-11-23
---

# STORY-017: Admin API: `GET /audit/actions` MCP filters and fields, `GET /skills`

## Description

As an auditor, I want to filter actions by surface, server, outcome and link, and list skills with the roles that hold them, so that gateway activity is reviewable.

## Acceptance Criteria

- [ ] Given `GET /audit/actions?surface=mcp&outcome=timeout`, `?server=github`, `?linked=false`, when requested, then only matching rows return and entries carry `surface`, `mcp_server`, `skills`, `linked_decision_id`, `outcome`, `duration_ms`, `result_bytes`, `result_flags`; `audit:read:all` / `audit:read:own` scoping is unchanged
- [ ] Given an invalid filter value (e.g. `surface=x`), when requested, then 422 or the module's existing validation error
- [ ] Given `GET /skills` with `stats:read`, when requested, then it returns each skill's id, version, description, tools, requires and holding roles, and `mcp_config_digest`, with no URL, header name or credential; without `stats:read` it is 403; with `MCP_ENABLED=false` it returns an empty list (or 404, decided in the plan and documented)

## Technical Notes

- `app/routers/admin.py` (`/audit/actions`).
- Roles per skill come from the role matrix (`authz`).

## Dependencies

- **Blocked by**: STORY-008, STORY-007
- **Blocks**: STORY-018

## PRD Reference

Source: [`PRD-023/PRD.md`](../../PRDs/PRD-023-mcp-and-skills/PRD.md) — Sections 4 (API and admin console), 10, F11
