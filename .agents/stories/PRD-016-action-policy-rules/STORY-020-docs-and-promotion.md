---
id: STORY-020
prd: PRD-016
slug: docs-and-promotion
title: README, docs/features.md, docs/roadmap.md, .env.example; full regression; brief promotion verified
type: technical
priority: medium
complexity: small
phase: "4 - Evidence"
status: todo
labels: [docs, tests]
epic_branch: epic/PRD-016-action-policy-rules
plan: null
report: null
commit: null
depends_on: [STORY-002, STORY-018, STORY-019]
blocks: []
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-020: README, docs/features.md, docs/roadmap.md, .env.example; full regression; brief promotion verified

## Description

As a platform operator, I want the action policy documented as shipped, with the file format, the permissions and the limits stated plainly, so that I can configure it correctly and know what it does not cover.

## Acceptance Criteria

- [ ] Given `docs/features.md` and the README, when read, then they describe *Action policy rules* as built but not yet called by `/v1` (PRD-017), with the rule table, the file format with `examples/action_policy.yaml`, the six action permissions and how to grant them in `RBAC_ROLES_FILE`, the relative/absolute path rule and the OpenCode workspace-root setup step, the PowerShell and symlink limitations, and the `PATTERNS_FILE` duplicate-key upgrade note.
- [ ] Given `docs/roadmap.md`'s *Action policy rules* section, when read, then "they are not built yet" is replaced with what is built and what PRD-017 adds, and the roadmap checkbox stays unticked until PRD-017 wires it.
- [ ] Given `.env.example`, when read, then `ACTION_POLICY_FILE`, `ACTION_MAX_ARGUMENT_CHARACTERS` and `ACTION_SQL_DIALECT` are present with comments in the existing style.
- [ ] Given the full suite, when run, then it is green; no pre-existing assertion changed except those STORY-002 and STORY-005 changed, each with a PRD-016 comment; every relative link in the changed docs resolves.
- [ ] Given `pre-prds/PRE-PRD-015-action-policy-rules.md` and `pre-prds/README.md`, when checked, then the brief is `status: promoted` with `prd:` pointing at this PRD and the track table links PRD-016 (done at PRD creation; this story verifies it and fixes any drift).

## Technical Notes

- Follow the PRD-011 STORY-013 and PRD-015 STORY-019 doc stories for structure and tone.
- State plainly in the README that the harness never executes tools, and that `arguments_preview` can hold up to 500 characters of a denied secret read (T10).
- Link the README section to `docs/features.md#action-policy-rules`.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-002, STORY-018, STORY-019
- **Blocks**: None

## PRD Reference

Source: [`PRD-016-action-policy-rules/PRD.md`](../../PRDs/PRD-016-action-policy-rules/PRD.md) — sections 4 (Documentation), 6.6 (Strict YAML), 7 (F13), 9.2 (T10), 14 (Risks 3, 4, 8)
