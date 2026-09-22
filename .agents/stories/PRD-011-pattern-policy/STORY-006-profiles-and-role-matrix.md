---
id: STORY-006
prd: PRD-011
slug: profiles-and-role-matrix
title: "Profiles and the role inspection matrix"
type: feature
priority: high
complexity: medium
phase: "2 - Configuration and profiles"
status: todo
labels: [backend, config, security]
epic_branch: epic/PRD-011-pattern-policy
plan: null
report: null
commit: null
depends_on: [STORY-005]
blocks: [STORY-007, STORY-008]
skills: []
created: 2026-09-22
updated: 2026-09-22
---

# STORY-006: Profiles and the role inspection matrix

## Description

As a security admin, I want each profile to declare which message roles it inspects and what happens on a hit, so that the scope of prompt inspection is a document I can review rather than behaviour I have to infer from code.

## Acceptance Criteria

- [ ] Given the built-in policy, when its profiles are read, then `chat` is `lists: [injection, keywords]`, `roles: {user: block}` and `code` is `lists: [injection]`, `roles: {user: block, tool: flag}` — the matrix in PRD Section 6.4, asserted cell by cell including the four "not inspected" cells.
- [ ] Given a profile's `roles:` map, when it names a role outside `Literal["system", "user", "assistant", "tool"]` or an action outside `block | flag`, then `load()` raises `PatternConfigError` naming the profile, the key and the allowed values. An empty `roles:` map is likewise an error (PRD 9.2 T5).
- [ ] Given a profile, when it is built, then its `lists` are resolved to `PatternList` objects at load time, so an undefined list name is a startup error and can never surface as a request-time `KeyError`.
- [ ] Given `PATTERN_PROFILE_DEFAULT` naming a profile the loaded policy does not define, when `load()` runs, then it raises `PatternConfigError` naming the setting, the missing profile and the profiles that do exist. Given `get_profile("nope")`, then it raises the same error type.
- [ ] Given `Role` in [app/models/messages.py](../../../app/models/messages.py), when the role vocabulary is needed, then it is imported from there — this story introduces no second role literal — and a test asserts every member of that `Literal` is an accepted `roles:` key.

## Technical Notes

- A role **absent** from `roles:` is not inspected. This is the opposite default from RBAC, where an absent permission denies. The asymmetry is deliberate (PRD Section 7 F4) and must be stated in the `Profile` docstring, because a reader who knows `authz.py` will otherwise assume deny-by-default here.
- `Profile` is a frozen dataclass holding resolved `PatternList` objects and a `Mapping[Role, action]`, per PRD Section 6.2. `roles` stored as a plain dict is fine; the frozen dataclass is what makes it not-reassignable.
- The `code` profile ships tested but with **no HTTP ingress** — PRD-014 mounts one. Do not add a route, a setting per endpoint, or a request field for it (PRD Sections 4 Out of Scope, 6.6, 9.2 T1).
- `system` is not inspected under `code` on purpose and the docstring should carry the one-line reason (it is the client's own prompt, and the single richest source of false positives — STORY-011 demonstrates it). A future PRD-014 decision may change that cell; it should be easy to find.
- Tests in `tests/test_pattern_profiles.py`.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-005
- **Blocks**: STORY-007, STORY-008

## PRD Reference

Source: [`PRD-011-pattern-policy/PRD.md`](../../PRDs/PRD-011-pattern-policy/PRD.md) — sections 4 (Profiles), 6.2, 6.4 (D1), 6.6 (D2), 7 (F4), 9.2 (T1, T5), 11
