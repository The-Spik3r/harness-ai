---
id: STORY-004
prd: PRD-011
slug: pattern-settings
title: "Four pattern-policy settings with startup validators"
type: technical
priority: high
complexity: small
phase: "2 - Configuration and profiles"
status: todo
labels: [backend, config]
epic_branch: epic/PRD-011-pattern-policy
plan: null
report: null
commit: null
depends_on: []
blocks: [STORY-005]
skills: []
created: 2026-09-22
updated: 2026-09-22
---

# STORY-004: Four pattern-policy settings with startup validators

## Description

As a platform operator, I want the pattern policy's four knobs to exist with safe defaults and instructive startup errors, so that a misconfiguration stops the boot with a message telling me what to set instead.

## Acceptance Criteria

- [ ] Given [app/config.py](../../../app/config.py), when `Settings` is read, then it declares `PATTERNS_FILE: str = ""`, `PATTERN_PROFILE_DEFAULT: str = "chat"`, `PATTERNS_ALLOW_REGEX: bool = False` and `PATTERN_MAX_SCAN_CHARACTERS: int = 1_000_000`, each with a comment naming the story that becomes its consumer.
- [ ] Given `PATTERN_MAX_SCAN_CHARACTERS=0` or a negative value, when `Settings` is constructed, then it raises with a message naming the field, the rejected value and what the field bounds — the `CHAT_SESSION_LIMIT` / `_PIPELINE_LIMIT_DESCRIPTIONS` style already in the file.
- [ ] Given `PATTERN_PROFILE_DEFAULT`, when `Settings` is constructed, then it is **not** validated here beyond being non-empty: it is a cross-check against the loaded policy and belongs in `pattern_config.load()` (STORY-005), because the file is not read when `Settings` is constructed. A comment in the field says so.
- [ ] Given `.env.example`, when it is read, then all four variables appear with the same defaults and a one- or two-line explanation each, in the style of the `CONTEXT_MAX_*` block.
- [ ] Given `requirements.txt`, when it is read, then `PyYAML` is declared explicitly, and `tests/test_config.py` gains cases for the new fields and their validator. The full suite is green with no production consumer of the new settings yet.

## Technical Notes

- Four settings and no fifth: the profile is a call-site argument, not a setting per endpoint (PRD Section 6.6, D2).
- `PyYAML` is already installed transitively through `python-frontmatter` (`yaml 6.0.3` in the active environment). Declare it anyway — PRD Section 8 states the reason, and a transitive dependency disappearing is a silent build break.
- Reuse the `_PIPELINE_LIMIT_DESCRIPTIONS` mapping pattern for the validator message rather than inlining prose in the `raise`, matching what `CONTEXT_MAX_MESSAGES` already does.
- Nothing reads these settings in this commit. That mirrors PRD-010 STORY-002, which landed four settings ahead of their consumers for the same reason: a settings commit that also changes behaviour cannot be reverted cleanly.
- Skills: none applicable.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-005

## PRD Reference

Source: [`PRD-011-pattern-policy/PRD.md`](../../PRDs/PRD-011-pattern-policy/PRD.md) — sections 4 (Settings), 6.9, 8, 9.3
