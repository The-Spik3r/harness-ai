---
id: STORY-001
prd: PRD-008
slug: chat-history-configuration
title: "CHAT_HISTORY_ENABLED and CHAT_SESSION_LIMIT settings, with the off state documented as supported"
type: technical
priority: high
complexity: small
phase: "1 - Schema and store"
status: todo
labels: [backend, config, security]
epic_branch: epic/PRD-008-chat-sessions
plan: null
report: null
commit: null
depends_on: []
blocks: [STORY-006]
skills: []
created: 2026-09-02
updated: 2026-09-02
---

# STORY-001: CHAT_HISTORY_ENABLED and CHAT_SESSION_LIMIT settings, with the off state documented as supported

## Description

As a security admin, I want transcript persistence to be a setting I control, so that a deployment that must not hold prompt text can run this build with the feature off (PRD Section 5, story 7).

This story lands first because it is the mitigation for the PRD's largest risk, and a mitigation added last is a mitigation someone argues out of scope. Every later story reads these settings; none of them get to decide whether the switch exists.

## Acceptance Criteria

- [ ] Given [app/config.py](../../../app/config.py), when `Settings` is read, then `CHAT_HISTORY_ENABLED: bool = True` and `CHAT_SESSION_LIMIT: int = 50` are declared, grouped and commented in the style of the `RBAC_*` and `PII_*` blocks already there.
- [ ] Given `CHAT_SESSION_LIMIT`, when a value below 1 is supplied, then startup fails with a message naming the setting — a limit of 0 renders an empty rail on a user who has sessions, which is a silent lie rather than a small list.
- [ ] Given `CHAT_HISTORY_ENABLED=false` in the environment, when settings load, then `settings.CHAT_HISTORY_ENABLED is False` — asserted with the string `"false"`, since that is what an `.env` file and a Docker `environment:` block actually supply.
- [ ] Given [.env.example](../../../.env.example), when it is read, then both variables appear with their defaults and a comment stating what the off state does: no transcript is written, none is read, and the chat behaves as it did before this PRD.
- [ ] Given [tests/test_config.py](../../../tests/test_config.py), when the suite runs, then the existing assertions pass unmodified and new ones cover the default, the explicit `false`, and the rejected limit.

## Technical Notes

- Files: [app/config.py](../../../app/config.py), [.env.example](../../../.env.example), [tests/test_config.py](../../../tests/test_config.py). Nothing else.
- Follow the existing grouping convention exactly: `RBAC_ENABLED` and `PII_REDACTION_ENABLED` are both `bool = True` with a comment naming the PRD that added them. Match that shape, and name PRD-008.
- Use a `field_validator` for the limit, in the style of `_validate_database_url` — the module already prefers a startup error over a defaulted-away bad value.
- Do **not** read these settings anywhere yet. The service in [[STORY-006]] is the only consumer, and wiring a reader here would put the flag's behaviour in a story whose diff cannot show it working.
- PRD Section 9, verbatim, is the acceptance bar this story is written against: "`CHAT_HISTORY_ENABLED=false` turns the feature off entirely — no write, no read, no rail — and the deployment gets today's ephemeral behaviour from the same image. A deployment that cannot hold prompt text has a supported configuration rather than a fork."
- The README's environment table is updated in [[STORY-022]], not here — one docs commit, at the end, when the variables' behaviour is real.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story touches no UI. No skill applies.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-006

## PRD Reference

Source: [`PRD-008/PRD.md`](../../PRDs/PRD-008-chat-sessions/PRD.md) — Section 4 (Configuration), Section 5 (story 7), Section 9, Section 12 Phase 1, Risk 1
