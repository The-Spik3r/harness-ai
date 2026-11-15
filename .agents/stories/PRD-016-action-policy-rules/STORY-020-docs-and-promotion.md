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

- Orchestrator note (STORY-013): document that embedded SQL uses each client's own dialect (psql=postgres, mysql/mariadb=mysql, sqlite3=sqlite), not `ACTION_SQL_DIALECT`; the reader heads treated as secret reads; and the known over-matches of the built-in globs (`.env.example`, `$KEYBOARD`), which are grantable denies.
- Orchestrator note (STORY-012): document that network matching is by name only (no DNS): a name under an allowlisted wildcard that resolves to a private address (`*.nip.io`, DNS rebinding) is matched; IP literals match only exact IP entries; wildcards never match `localhost`, `*.localhost` or `metadata.google.internal`; IDNA 2003/2008 deviation characters (ß, ς, ZWJ, ZWNJ) are `net.unparsed`.
- Orchestrator note (STORY-011): path checks are lexical only: symlinks, hard links and 8.3 short names are not resolved (PRD Risk 4); containment is case-sensitive except the drive letter (fails closed on Windows).
- Orchestrator note (STORY-010): document that a segment with a `sudo`/`doas` wrapper or leading `NAME=value` assignments is never `shell.allowlisted` (e.g. `CI=1 npm test` is unlisted), and that `python -m pip install` is `shell.package_install`.
- Orchestrator note (STORY-009): list the extra `shell.unclassifiable` triggers beyond PRD 6.3: here-documents `<<`, brace expansion, `$'...'`/`$"..."`, heads with glob chars, `(`, `^`, `env -S`, unquoted drive-letter heads (`C:...`, backslashes lost), nesting deeper than 3 `-c` levels; and that wrappers `command builtin exec nice timeout stdbuf setsid` are stripped with strict option tables.
- Orchestrator note (STORY-008): document as stated limitations of the SQL classifier: tautologies the sqlglot simplifier does not fold (e.g. `id = id`) count as scoped writes; side-effecting functions inside a SELECT (`pg_sleep`, `lo_import`) are reads; `SET`/`USE`, `RENAME TABLE`, `CREATE USER/ROLE` and `GRANT role TO u` are `sql.unparsed` (deny, no grant), stricter than the PRD; `EXPLAIN ANALYZE` is `sql.unparsed`; `ACTION_SQL_DIALECT` is not part of `policy_digest`.
- Orchestrator note (STORY-004): the README/docs state the Cline 4.x argument shapes the built-in mappings do not read and therefore deny as `tool.malformed`: `run_commands` top-level `{command, args?}` / `{command}`, `read_files` with `files` as strings or a string, `paths` as an object, and bare JSON strings/arrays. Two spellings of one target in a call are `tool.malformed` by design.
- Follow the PRD-011 STORY-013 and PRD-015 STORY-019 doc stories for structure and tone.
- State plainly in the README that the harness never executes tools, and that `arguments_preview` can hold up to 500 characters of a denied secret read (T10).
- From STORY-001 (`threat-model.md` S5, S6, S9, S10): tell Cline deployments as well as OpenCode ones to set `workspace.roots` (both send absolute paths); explain that MCP tool names arrive prefixed and must be mapped in `tools:`; state PRD D15 (directory search can return secret contents; keep secrets outside the workspace); map `apply_patch` in the sample.
- Link the README section to `docs/features.md#action-policy-rules`.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-002, STORY-018, STORY-019
- **Blocks**: None

## PRD Reference

Source: [`PRD-016-action-policy-rules/PRD.md`](../../PRDs/PRD-016-action-policy-rules/PRD.md) — sections 4 (Documentation), 6.6 (Strict YAML), 7 (F13), 9.2 (T10), 14 (Risks 3, 4, 8)
