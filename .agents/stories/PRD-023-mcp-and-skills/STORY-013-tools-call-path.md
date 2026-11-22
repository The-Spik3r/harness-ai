---
id: STORY-013
prd: PRD-023
slug: tools-call-path
title: "`tools/call`: usage, visibility, evaluation, record before forward, forward, outcome"
type: feature
priority: high
complexity: large
phase: "3 - The gateway"
status: todo
labels: [mcp, security, audit]
epic_branch: epic/PRD-023-mcp-and-skills
plan: null
report: null
commit: null
depends_on: [STORY-006, STORY-008, STORY-012]
blocks: [STORY-014, STORY-016]
skills: []
created: 2026-11-22
updated: 2026-11-22
---

# STORY-013: `tools/call`: usage, visibility, evaluation, record before forward, forward, outcome

## Description

As a security admin, I want every gateway `tools/call` decided by the action policy and recorded before it is forwarded, so that the decision is enforced at execution and there is never an executed call with no row.

## Acceptance Criteria

- [ ] Given `DROP TABLE users` on `postgres-staging__query` for a role without `action:sql:ddl`, when called, then the result is `isError: true` with the exact PRD-017 note text, the row is `surface='mcp'`, `deny`, `sql.ddl`, `outcome NULL`, and the stub's `query` counter is 0; for `dba` with the grant it is `allow`, forwarded, `outcome='ok'`
- [ ] Given a tool outside the caller's skills, when called, then the answer is `-32602` (not revealing existence), a `deny` / `tool.not_in_skill` row is written, and the stub counter is 0; non-object `arguments` → `-32602`; absent → `{}`
- [ ] Given a storage failure injected at the pre-forward write, when called, then `-32603` "decision could not be recorded" is returned and the stub counter is 0; given a failure at `record_outcome`, then the result is returned, `ERROR` is logged and the row stays with `outcome NULL`
- [ ] Given usage over the rate, when called, then HTTP 429 with `Retry-After` from `resets_at`, no row and no upstream request (M4 before evaluation, `charges_budget=False`)
- [ ] Given an allowed call, when forwarded, then the classified canonical string and the forwarded object come from one parse (T7); `slow` past its timeout returns `isError` "timed out after <n>s; the call may have run" with `outcome='timeout'` and no retry; an upstream JSON-RPC error returns the "may have run" text with `outcome='upstream_error'` and the upstream message only logged; `isError` from the server is `tool_error`; `push_files` with `.github/workflows/ci.yml` → `fs.write_protected`; `create_pull_request` → forwarded, `flag` / `tool.opaque`

## Technical Notes

- Steps M3–M9 of Section 6.3. M7's correlation is a seam here (`audit_id=None`, no link); STORY-016 fills it. Result inspection and caps are STORY-014 (here: return the result unmodified and record bytes/hash).
- Pre-forward write: `record()` without `audit_ref` so it never journals (PRD-018 O8).
- The row's `skills` column lists every held skill containing the tool as `id@version`.
- At most three DB round trips per call (admit, link lookup + insert, outcome).

## Dependencies

- **Blocked by**: STORY-006, STORY-008, STORY-012
- **Blocks**: STORY-014, STORY-016

## PRD Reference

Source: [`PRD-023/PRD.md`](../../PRDs/PRD-023-mcp-and-skills/PRD.md) — Sections 6.3, 10 (error table), F6, D8, D9, D13, D14, T6, T7, T9, T10, User Stories 2–5
