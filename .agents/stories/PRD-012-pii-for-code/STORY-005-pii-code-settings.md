---
id: STORY-005
prd: PRD-012
slug: pii-code-settings
title: "Six PII code-profile settings with startup validators"
type: technical
priority: high
complexity: small
phase: "2 - Primitives"
status: todo
labels: [backend, config]
epic_branch: epic/PRD-012-pii-for-code
plan: null
report: null
commit: null
depends_on: [STORY-003]
blocks: [STORY-006, STORY-007]
skills: []
created: 2026-09-23
updated: 2026-09-23
---

# STORY-005: Six PII code-profile settings with startup validators

## Description

As a platform operator, I want the `code` profile's PII behaviour tunable from `.env` and validated at boot, so that I can move its defaults without a code change and a mis-set value stops the process loudly.

## Acceptance Criteria

- [ ] Given `app/config.py`, when it is read, then `PII_ENTITIES_CODE`, `PII_SCORE_THRESHOLD_CODE`, `PII_MAX_CHARACTERS_CODE`, `PII_CODE_REDACT_OUTPUT` (`False`), `PII_CODE_REDACT_SYSTEM` (`False`) and `PII_CODE_SKIP_CODE_BLOCKS` (`True`) exist, with the entity list, threshold and size limit defaults taken from the STORY-003 report.
- [ ] Given `PII_ENTITIES_CODE` empty or naming an unknown entity type, when `Settings` is constructed, then it raises with a message naming the setting, the bad value and the accepted names.
- [ ] Given `PII_SCORE_THRESHOLD_CODE` outside `[0, 1]`, or `PII_MAX_CHARACTERS_CODE < 1`, when `Settings` is constructed, then it raises with the `_RESOURCE_BOUNDS`-style message.
- [ ] Given a `pii_entities_code_list` property, when it is read, then it parses like `pii_entities_list`.
- [ ] Given the existing four `PII_*` settings, when this story lands, then their names, defaults and validation are unchanged.

## Technical Notes

- Follow the settings-group comment style used for the PRD-010 and PRD-011 groups: each field names the story that consumes it (STORY-006, STORY-007, STORY-010).
- The known entity names are the seven Presidio types today's default uses plus any others Presidio's default registry provides. Validate against a module-level constant, not by loading the analyzer, because `Settings` is built before any model loads.
- Add `PII_MAX_CHARACTERS_CODE` to `_RESOURCE_BOUNDS` so its validator message matches the others.
- Extend `tests/test_config.py`.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-003
- **Blocks**: STORY-006, STORY-007

## PRD Reference

Source: [`PRD-012-pii-for-code/PRD.md`](../../PRDs/PRD-012-pii-for-code/PRD.md) — sections 4 (Settings), 7 (F4), 9.3
