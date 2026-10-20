---
id: STORY-010
prd: PRD-013
slug: usage-limits-service
title: "usage_limits: limit resolution and the rate and budget checks"
type: feature
priority: high
complexity: medium
phase: "2 - Limit primitives"
status: done
labels: [backend, limits]
epic_branch: epic/PRD-013-audit-and-usage-limits
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-010-usage-limits-service.plan.md
report: .agents/reports/PRD-013-audit-and-usage-limits/STORY-010-usage-limits-service.report.md
commit: 3570281
depends_on: [STORY-007, STORY-008, STORY-009]
blocks: [STORY-011]
skills: []
created: 2026-10-04
updated: 2026-10-19
---

# STORY-010: usage_limits: limit resolution and the rate and budget checks

## Description

As a platform operator, I want one function that says whether an identity is admitted and why not, so that the pipeline enforces limits without knowing how they are configured or stored.

## Acceptance Criteria

- [ ] Given an identity with a per-user override, with only a role entry, and with a role that has no entry, when `limits_for(identity)` is called, then it returns the override, the role's value and the `*` value respectively, resolved independently for the budget and the rate.
- [ ] Given a rate limit of 3, when `admit` is called four times in one minute, then the first three are admitted and the fourth is refused with `limit="requests"`, `maximum=3`, `actual=4` and `resets_at` equal to the end of the current minute in the audit timestamp format.
- [ ] Given `tokens_today` at or above the budget and `charges_budget=True`, when `admit` is called, then it is refused with `limit="tokens"` and `resets_at` at the next 00:00 UTC; with `charges_budget=False` it is admitted.
- [ ] Given both limits broken, when `admit` is called, then `limit="requests"` is the one reported; given a limit of `unlimited`, then that check never refuses.
- [ ] Given `admit_usage` raising `StorageError`, when `admit` is called, then it raises `UsageLimitError`; given `charge_usage` raising `StorageError`, when `charge` is called, then it logs at `ERROR` with the user id, day and counts, and returns without raising.

## Technical Notes

- New file `app/services/usage_limits.py`; tests in `tests/test_usage_limits.py`.
- `Admission` should make the refused and admitted cases impossible to confuse: for example a frozen dataclass with `admitted: bool`, `day: str` and optional refusal fields, or two classes. The pipeline needs `day` on admission to charge the right row.
- Read settings per call, not at import, so `monkeypatch.setattr(settings, ...)` works (the `_context_limit_exceeded` note).
- `resets_at` is derived from the `window_start` and `day` the database returned, not from the instance clock.
- The break-glass identity has no `users` row and so no override; it resolves through the `admin` role like any admin (PRD Section 6.6).
- `charge(user_id, day, input_tokens, output_tokens, total_tokens)`: when the split is present charge the split, otherwise charge `total_tokens` to `unsplit_tokens` (PRD F11).
- This module does not read `USAGE_LIMITS_ENABLED`. The pipeline decides whether to call it (STORY-011).
- Skills: none applicable. No UI surface changes in this story.

## Dependencies

- **Blocked by**: STORY-007, STORY-008, STORY-009
- **Blocks**: STORY-011

## PRD Reference

Source: [`PRD-013-audit-and-usage-limits/PRD.md`](../../PRDs/PRD-013-audit-and-usage-limits/PRD.md) — sections 6.5, 6.6 (D1), 7 (F9), 9.2 (T7, T8)
