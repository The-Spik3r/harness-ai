---
id: STORY-004
prd: PRD-001
slug: duplicate-detection-service
title: Duplicate detection service (24h exact-match)
type: feature
priority: high
complexity: medium
phase: "2 - Core Logic"
status: todo
labels: [backend, security]
epic_branch: epic/PRD-001-harness-ia
plan: null
report: null
commit: null
depends_on: [STORY-002, STORY-003]
blocks: [STORY-008]
skills: []
created: 2026-07-04
updated: 2026-07-04
---

# STORY-004: Duplicate detection service (24h exact-match)

## Description

As a security admin, I want identical queries blocked if repeated within 24 hours, so that the same prompt can't be used to duplicate-train or duplicate-leak information (RF-3, RF-4).

## Acceptance Criteria

- [ ] Given a prompt hashed with SHA256, when the identical hash exists in `audit_logs` with a `timestamp` within the last 24 hours, then the checker returns a blocked result with the `first_query_at` of the original entry.
- [ ] Given a prompt hashed with SHA256, when no matching hash exists in the last 24 hours (including when it exists but is older than 24h), then the checker returns "not a duplicate."
- [ ] Given two prompts that differ by even a single character/whitespace, when hashed, then they produce different hashes and are never flagged as duplicates (exact word-for-word match only, per PRD Section 4).
- [ ] Given the checker runs, when called with an empty or malformed DB, then it fails safely (raises a clear error) rather than silently treating everything as non-duplicate.

## Technical Notes

- Implement `app/services/duplicate_checker.py` per PRD Section 6.
- Use `hashlib.sha256` on the raw prompt string (no normalization) — this matches the RF-4 "match exacto (palabra por palabra)" requirement.
- Query pattern: `SELECT ... FROM audit_logs WHERE prompt_hash = ? AND timestamp >= (now - 24h)`.
- Unit test with a fake/in-memory SQLite DB seeded with known rows at various timestamps (just inside vs. just outside the 24h window).

## Dependencies

- **Blocked by**: STORY-002, STORY-003
- **Blocks**: STORY-008

## PRD Reference

Source: [`PRD-001/PRD.md`](../../PRDs/PRD-001-harness-ia/PRD.md) — Section 5 (User Story 2), Section 7 (Duplicate blocking), Section 12 (Phase 2)
