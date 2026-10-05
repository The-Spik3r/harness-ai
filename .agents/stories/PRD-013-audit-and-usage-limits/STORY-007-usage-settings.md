---
id: STORY-007
prd: PRD-013
slug: usage-settings
title: "Limit and break-glass settings with startup validators"
type: technical
priority: high
complexity: small
phase: "2 - Limit primitives"
status: todo
labels: [backend, config]
epic_branch: epic/PRD-013-audit-and-usage-limits
plan: null
report: null
commit: null
depends_on: []
blocks: [STORY-010, STORY-013]
skills: []
created: 2026-10-04
updated: 2026-10-04
---

# STORY-007: Limit and break-glass settings with startup validators

## Description

As a platform operator, I want the limits and the break-glass policy set in `.env` and checked at startup, so that a mistyped value stops the boot with a message naming it instead of silently disabling a limit.

## Acceptance Criteria

- [ ] Given no new variables set, when `Settings()` is built, then `USAGE_LIMITS_ENABLED` is `True`, `USAGE_DAILY_TOKEN_BUDGET` is `"*=1000000"`, `USAGE_REQUESTS_PER_MINUTE` is `"*=60"` and `BREAK_GLASS_INGRESSES` is `"query,chat"`.
- [ ] Given `USAGE_REQUESTS_PER_MINUTE="*=60,admin=unlimited,auditor=10"`, when the parsed property is read, then it is `{"*": 60, "admin": None, "auditor": 10}`.
- [ ] Given a limit map with no `*` entry, a value of `0`, a negative or non-numeric value, a role listed twice, or an entry with no `=`, when `Settings()` is built, then it raises with a message that names the setting, quotes the offending entry and shows a valid example.
- [ ] Given `BREAK_GLASS_INGRESSES` set to `""`, `"chat"` or `"query"`, when `Settings()` is built, then it is accepted; given `"v1"` or `"query,v1"`, then it raises with a message saying `ADMIN_TOKEN` is never accepted on `/v1`; given an unknown name, then it raises naming the accepted values.
- [ ] Given the story's diff, when it is reviewed, then no production code reads the four settings yet, and `tests/test_config.py` covers every case above.

## Technical Notes

- `app/config.py`: follow the `CHAT_SESSION_LIMIT` and `PII_ENTITIES_CODE` validator style. Reuse `_split_comma_list`.
- Parsed properties: `usage_daily_token_budget_map` and `usage_requests_per_minute_map` as `dict[str, Optional[int]]` (`None` = unlimited), and `break_glass_ingresses` as a `frozenset[str]`.
- Role names are not checked against the RBAC matrix: `RBAC_ROLES_FILE` may define any role and is loaded after `Settings` is built (PRD Section 6.6).
- Each field's comment names the story that becomes its consumer, as the PRD-010/012 blocks do.
- The defaults are provisional (PRD Section 9.3, Assumptions). Say so in the comment.
- Skills: none applicable. No UI surface changes in this story.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-010, STORY-013

## PRD Reference

Source: [`PRD-013-audit-and-usage-limits/PRD.md`](../../PRDs/PRD-013-audit-and-usage-limits/PRD.md) — sections 6.6, 6.8, 7 (F6), 9.3
