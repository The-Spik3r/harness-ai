---
id: STORY-003
prd: PRD-005
slug: identity-resolution
title: Identity resolution — token hashing, Identity value object, ADMIN_TOKEN break-glass
type: feature
priority: high
complexity: medium
phase: "Phase 1 — Identity foundation"
status: todo
labels: [backend, security]
epic_branch: epic/PRD-005-rbac
plan: null
report: null
commit: null
depends_on: [STORY-002]
blocks: [STORY-004, STORY-006, STORY-012]
skills: []
created: 2026-08-28
updated: 2026-08-28
---

# STORY-003: Identity resolution — token hashing, Identity value object, ADMIN_TOKEN break-glass

## Description

As a security admin, I want a credential resolved server-side into a verified `Identity`, so that every downstream decision rests on who the server confirmed rather than on what the caller claimed.

## Acceptance Criteria

- [ ] Given a valid active user token, when `resolve(token)` is called, then it returns `Identity(user_id, role)`
- [ ] Given an unknown, malformed, empty, or deactivated token, when `resolve(token)` is called, then it returns `None` — never a partial, default, or anonymous identity
- [ ] Given the configured `ADMIN_TOKEN`, when `resolve(token)` is called, then it returns a synthetic `Identity` with role `admin`, compared with `secrets.compare_digest`
- [ ] Given a token is issued, when it is persisted, then only its SHA-256 digest is stored and the plaintext appears nowhere in the database or logs
- [ ] Given `issue_token()`, when it generates a credential, then it uses `secrets.token_urlsafe(32)` and returns the plaintext exactly once

## Technical Notes

- New `app/services/identity.py`: frozen `Identity` dataclass, `hash_token()`, `issue_token()`, `resolve()`.
- `Identity` is immutable and produced **only** here — nothing else constructs one in production code, which is what makes it a trustworthy argument type downstream.
- `hash_prompt()` from `duplicate_checker.py` is deliberately **not** reused: same algorithm, different purpose.
- SHA-256 is appropriate only because tokens are 256-bit and machine-generated (PRD Section 8). If human-chosen passwords are ever introduced, argon2/bcrypt becomes mandatory.
- Tests: new `tests/test_identity.py`.

## Dependencies

- **Blocked by**: STORY-002
- **Blocks**: STORY-004, STORY-006, STORY-012

## PRD Reference

Source: [`PRD-005/PRD.md`](../../PRDs/PRD-005-rbac/PRD.md) — sections 6, 8, 9
