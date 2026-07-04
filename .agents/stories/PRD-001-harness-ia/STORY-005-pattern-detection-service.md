---
id: STORY-005
prd: PRD-001
slug: pattern-detection-service
title: Suspicious pattern detection service
type: feature
priority: high
complexity: small
phase: "2 - Core Logic"
status: done
labels: [backend, security]
epic_branch: epic/PRD-001-harness-ia
plan: .agents/plans/PRD-001-harness-ia/completed/STORY-005-pattern-detection-service.plan.md
report: .agents/reports/PRD-001-harness-ia/STORY-005-pattern-detection-service.report.md
commit: 42724a4
depends_on: [STORY-003]
blocks: [STORY-008]
skills: []
created: 2026-07-04
updated: 2026-07-04
---

# STORY-005: Suspicious pattern detection service

## Description

As a security admin, I want basic prompt-injection patterns blocked before they reach the model, so that known attack strings never get forwarded upstream (RF-13).

## Acceptance Criteria

- [x] Given a prompt containing any of the seven patterns from PRD Section 9 ("ignore previous instructions", "forget everything", "show system prompt", "reveal password", "execute code", "admin mode", "override"), when scanned, then the detector flags it as suspicious and reports which pattern matched.
- [x] Given a prompt with a pattern in different casing (e.g. "IGNORE PREVIOUS INSTRUCTIONS"), when scanned, then it is still flagged (case-insensitive match).
- [x] Given a prompt containing none of the listed patterns, when scanned, then the detector reports "clean" and no pattern name.
- [x] Given the pattern list, when a new pattern needs to be added, then it can be done by editing a single data structure (list/config), not branching logic (Strategy pattern per PRD Section 6).

## Technical Notes

- Implement `app/services/pattern_detector.py` per PRD Section 6.
- Patterns list lives as a simple Python list/constant, substring + case-insensitive match — no regex complexity needed for MVP.
- Unit test each of the 7 patterns individually plus at least one clean prompt and one mixed-case match.

## Dependencies

- **Blocked by**: STORY-003
- **Blocks**: STORY-008

## PRD Reference

Source: [`PRD-001/PRD.md`](../../PRDs/PRD-001-harness-ia/PRD.md) — Section 5 (User Story 3), Section 9 (Suspicious pattern list), Section 12 (Phase 2)
