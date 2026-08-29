---
id: STORY-017
prd: PRD-005
slug: rbac-test-suite
title: RBAC test suite — full matrix coverage and ingress parity
type: technical
priority: high
complexity: medium
phase: "Phase 4 — Endpoint permissions, docs, rollout"
status: done
labels: [testing, security]
epic_branch: epic/PRD-005-rbac
plan: .agents/plans/PRD-005-rbac/completed/STORY-017-rbac-test-suite.plan.md
report: .agents/reports/PRD-005-rbac/STORY-017-rbac-test-suite.report.md
commit: PENDING
depends_on: [STORY-013, STORY-014, STORY-015]
blocks: [STORY-018]
skills: []
created: 2026-08-28
updated: 2026-08-29
---

# STORY-017: RBAC test suite — full matrix coverage and ingress parity

## Description

As a maintainer, I want a suite covering the whole permission matrix through both ingresses, so that the control cannot silently degrade when a new caller is added.

## Acceptance Criteria

- [ ] Given the role/permission matrix, when the suite runs, then every cell is asserted in both directions — granted and denied
- [ ] Given each permission, when tested, then it is exercised through **both** `POST /query` and `ChatState.send()`, asserting identical denials
- [ ] Given a denial through either ingress, when asserted, then the mocked OpenRouter client is never called and exactly one audit row carries the role and the missing permission
- [ ] Given a pre-RBAC fixture database, when `init_db()` runs, then migration preserves every existing row and adds both new columns
- [ ] Given the PRD-001/002/003 suites, when the full suite runs, then they pass, modified only where `run_query()` now requires an identity

## Technical Notes

- New `tests/test_rbac.py`; extend `tests/test_chat_state.py` for the UI ingress.
- The ingress-parity tests are the regression guard for PRD Risk 1. A router-only suite would stay green even if the chat UI bypassed authorization completely — which is precisely the failure this PRD exists to prevent, so these tests are not optional coverage.
- Follows the PRD-003 STORY-008 precedent: isolation tests proving a new control cannot alter existing pipeline behavior.

## Dependencies

- **Blocked by**: STORY-013, STORY-014, STORY-015
- **Blocks**: STORY-018

## PRD Reference

Source: [`PRD-005/PRD.md`](../../PRDs/PRD-005-rbac/PRD.md) — sections 8, 11, 14 (Risk 1)
