---
id: STORY-007
prd: PRD-012
slug: pii-policy
title: "pii_policy: built-in chat and code policies, profile fallback, load() in both lifespans"
type: feature
priority: high
complexity: medium
phase: "2 - Primitives"
status: done
labels: [backend, pii, config]
epic_branch: epic/PRD-012-pii-for-code
plan: .agents/plans/PRD-012-pii-for-code/completed/STORY-007-pii-policy.plan.md
report: .agents/reports/PRD-012-pii-for-code/STORY-007-pii-policy.report.md
commit: 50ef312
depends_on: [STORY-005]
blocks: [STORY-008, STORY-009]
skills: []
created: 2026-09-23
updated: 2026-09-25
---

# STORY-007: pii_policy: built-in chat and code policies, profile fallback, load() in both lifespans

## Description

As a security admin, I want PII behaviour chosen by the same server-selected profile that chooses the pattern policy, falling back to the strictest policy for any unknown name, so that the permissive `code` behaviour is reachable only where the server intends it.

## Acceptance Criteria

- [ ] Given `app/services/pii_policy.py`, when it is read, then the frozen `PiiPolicy` dataclass has the fields of PRD Section 6.2 (`name`, `input_roles`, `output`, `skip_fenced_blocks`, `entities`, `threshold`, `max_characters`, `structure_safe`), using PRD-010's `Role` type.
- [ ] Given the built-in `chat` policy, when it is built, then it matches the Section 6.2 table exactly: every role, output on, no fence skipping, `PII_ENTITIES`, `PII_SCORE_THRESHOLD`, `max_characters=None`, `structure_safe=False`.
- [ ] Given the built-in `code` policy, when it is built with default settings, then `input_roles` is `{user, assistant, tool}`, output off, fence skipping on, `PII_ENTITIES_CODE`, `PII_SCORE_THRESHOLD_CODE`, `PII_MAX_CHARACTERS_CODE`, `structure_safe=True`; with `PII_CODE_REDACT_SYSTEM=true` it adds `system`, and the other two booleans map as named.
- [ ] Given `get_pii_policy(name)` with a name that is neither `chat` nor `code`, when it is called, then it returns `chat`. Given `load()` at startup, then it logs one INFO line per profile name in the loaded pattern policy that has no PII policy, naming it and saying it resolves to `chat`.
- [ ] Given `app/main.py` and `chat_ui/chat_ui/chat_ui.py`, when each lifespan starts, then `pii_policy.load()` runs after `pattern_config.load()`, and a `PiiConfigError` stops the boot.

## Technical Notes

- The policy is built from `settings` in `load()` and read back by `get_pii_policy`. Tests that `monkeypatch` settings must call `load()` again. Follow `pattern_config`'s get/load split.
- The fallback goes to `chat` because it is the most masking policy (PRD Section 6.2, D8). A test must pin that an unknown name gets `chat` and not `code`.
- `PiiConfigError` is reserved for inconsistent combinations. With only built-in policies and validated settings it is essentially unreachable today. Define it and test the one combination `load()` checks.
- No request schema gains a field. The PRD-011 unknown-field schema test already covers that.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-005
- **Blocks**: STORY-008, STORY-009

## PRD Reference

Source: [`PRD-012-pii-for-code/PRD.md`](../../PRDs/PRD-012-pii-for-code/PRD.md) — sections 6.2 (D8), 6.3 (D1, D3), 6.10, 7 (F5), 10
