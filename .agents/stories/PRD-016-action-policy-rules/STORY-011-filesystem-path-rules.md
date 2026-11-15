---
id: STORY-011
prd: PRD-016
slug: filesystem-path-rules
title: Filesystem path rules — normalization, workspace containment, protected paths
type: feature
priority: high
complexity: medium
phase: "3 - Classifiers and the engine"
status: todo
labels: [backend, security, classifier]
epic_branch: epic/PRD-016-action-policy-rules
plan: null
report: null
commit: null
depends_on: [STORY-006]
blocks: [STORY-013]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-011: Filesystem path rules — normalization, workspace containment, protected paths

## Description

As a security admin, I want every write classified against the workspace and the protected-path list after the path is normalized, so that `..`, mixed separators and case cannot reach `.env`, credentials or CI config.

## Acceptance Criteria

- [ ] Given `normalize_path`, when called with `src\\a.ts`, `C:\\Repo\\x`, `a//b/./c`, `a/b/../c`, `~/x`, then it returns `src/a.ts`, `c:/Repo/x`, `a/b/c`, `a/c`, and a path whose first segment is the literal `~`; it touches no filesystem.
- [ ] Given no workspace roots, when `classify_write` runs on `src/a.ts`, then `fs.write_in_workspace`; on `../../etc/passwd`, then `fs.write_outside_workspace`; on `/etc/hosts`, then `fs.write_outside_workspace`; given a root of `/home/dev/projects`, then `/home/dev/projects/app/x.ts` is `fs.write_in_workspace` and `/home/dev/projects2/x` is not.
- [ ] Given `.env`, `./.env`, `config/../.env`, `.ENV.local`, `/home/dev/projects/app/.env.local`, `.github/workflows/ci.yml`, `.git/config`, `id_rsa`, `x.pem`, when classified as writes, then each is `fs.write_protected`, including inside a workspace root (protection is checked before containment).
- [ ] Given a read of `src/a.ts`, when `classify_read` runs, then `fs.read`; a read of a secret file glob returns the secret classifier's hook result, which STORY-012 fills in (until then a placeholder that tests mark as pending).
- [ ] Given the module, when imported, then it reads no settings and performs no I/O.

## Technical Notes

- Orchestrator decision (STORY-006 plan): glob semantics are fixed by `action_config`: `*`, `?`, whole-segment `**`; path globs anchored `(?:^|/)...$` used with `.search()`, IGNORECASE; consume the compiled globs, do not re-translate.
- New `app/services/action_classifiers/paths.py`: `NormalizedPath`, `normalize_path`, `classify_write(path, policy)`, `classify_read(path, policy)`.
- `PurePosixPath` after separator rewrite; lowercase the drive letter only; resolve `..` lexically; a relative path that resolves above its start escapes.
- Containment compares normalized path segments, not string prefixes (so `/projects2` is not under `/projects`).
- Symlinks are not resolved (PRD Risk 4); say so in the module docstring.
- Tests: new `tests/test_action_paths.py`, one case per T6 trick.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-006
- **Blocks**: STORY-013

## PRD Reference

Source: [`PRD-016-action-policy-rules/PRD.md`](../../PRDs/PRD-016-action-policy-rules/PRD.md) — sections 6.3 (filesystem rows), 6.5, 7 (F4), 9.2 (T6), 14 (Risk 4), 15 (D11)
