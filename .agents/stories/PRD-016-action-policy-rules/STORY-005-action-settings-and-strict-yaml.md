---
id: STORY-005
prd: PRD-016
slug: action-settings-and-strict-yaml
title: Three action settings; strict_yaml with duplicate-key rejection; pattern_config adopts it
type: technical
priority: high
complexity: small
phase: "2 - Configuration"
status: done
labels: [backend, config]
epic_branch: epic/PRD-016-action-policy-rules
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-005-action-settings-and-strict-yaml.plan.md
report: .agents/reports/PRD-016-action-policy-rules/STORY-005-action-settings-and-strict-yaml.report.md
commit: pending
depends_on: []
blocks: [STORY-007]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-005: Three action settings; strict_yaml with duplicate-key rejection; pattern_config adopts it

## Description

As a platform operator, I want the action policy's settings validated at startup and a YAML key written twice to stop the boot, so that neither a bad value nor a silently dropped section can change what is enforced.

## Acceptance Criteria

- [ ] Given `app/config.py`, when `Settings` is built, then `ACTION_POLICY_FILE: str = ""`, `ACTION_MAX_ARGUMENT_CHARACTERS: int = 100000` and `ACTION_SQL_DIALECT: str = ""` exist; `ACTION_MAX_ARGUMENT_CHARACTERS=0` fails validation with a message that says what to set instead.
- [ ] Given `strict_yaml.safe_load("a: 1\na: 2\n")`, when called, then it raises `yaml.YAMLError` naming the duplicate key `a` and its line; nested duplicates are caught too; a document without duplicates returns exactly what `yaml.safe_load` returns.
- [ ] Given a `!!python/object` tag, when loaded through `strict_yaml`, then it is refused as `yaml.safe_load` refuses it.
- [ ] Given `pattern_config.load()` with a `PATTERNS_FILE` containing a duplicate key, when it runs, then it raises `PatternConfigError` naming the file and the key; every other assertion in `tests/test_pattern_config.py` is unchanged and green.
- [ ] Given `pattern_config.load()`'s docstring, when read after the story, then its "PyYAML resolves duplicate mapping keys silently" paragraph is replaced by a note citing PRD-016 D13.

## Technical Notes

- New `app/services/strict_yaml.py`: a `yaml.SafeLoader` subclass overriding `construct_mapping` to track keys; `safe_load(text)`.
- `pattern_config.load()` swaps `yaml.safe_load` for `strict_yaml.safe_load`; keep its `except yaml.YAMLError` arm, so the message keeps the `Failed to parse PATTERNS_FILE` prefix.
- `ACTION_SQL_DIALECT` is checked against `sqlglot` in STORY-008, not here (`sqlglot` is not installed yet); here it is only a string.
- Add the three settings, commented, to `.env.example` in STORY-020, not here.
- Tests: new `tests/test_strict_yaml.py`; one new case in `tests/test_pattern_config.py` with a comment citing PRD-016 D13; settings cases beside the existing `CONTEXT_MAX_*` validator tests.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-007

## PRD Reference

Source: [`PRD-016-action-policy-rules/PRD.md`](../../PRDs/PRD-016-action-policy-rules/PRD.md) — sections 4 (Configuration, Settings), 6.6 (Strict YAML), 9.3, 14 (Risk 8), 15 (D13)
