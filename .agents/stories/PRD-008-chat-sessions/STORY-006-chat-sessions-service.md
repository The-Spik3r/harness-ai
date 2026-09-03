---
id: STORY-006
prd: PRD-008
slug: chat-sessions-service
title: "app/services/chat_sessions.py: the ownership rule and the CHAT_HISTORY_ENABLED short-circuit in one place"
type: feature
priority: high
complexity: medium
phase: "1 - Schema and store"
status: todo
labels: [backend, service, security, config]
epic_branch: epic/PRD-008-chat-sessions
plan: null
report: null
commit: null
depends_on: [STORY-001, STORY-004, STORY-005]
blocks: [STORY-007, STORY-010, STORY-013]
skills: []
created: 2026-09-02
updated: 2026-09-02
---

# STORY-006: app/services/chat_sessions.py: the ownership rule and the CHAT_HISTORY_ENABLED short-circuit in one place

## Description

As a maintainer, I want one module that owns both "whose row is this" and "is history on at all", so that no caller has to remember either — the way [app/services/authz.py](../../../app/services/authz.py) owns the permission matrix so no caller writes a role check.

## Acceptance Criteria

- [ ] Given `app/services/chat_sessions.py`, when it is read, then it exposes `create`, `list_for`, `get`, `rename`, `touch`, `delete`, `append_message` and `messages_for`, each taking an `Identity` rather than a bare `user_id` string.
- [ ] Given every function, when it calls into [app/db/database.py](../../../app/db/database.py), then it passes `identity.user_id` — the service is the only place that converts an Identity into an owner, and no caller outside it reaches `database.py`'s session functions.
- [ ] Given `settings.CHAT_HISTORY_ENABLED is False`, when any write function is called, then **no statement is issued** and the caller receives a value it can proceed with: `create` returns `None`, `append_message` returns `None`, `touch`/`rename`/`delete` return `False`.
- [ ] Given `settings.CHAT_HISTORY_ENABLED is False`, when any read function is called, then it returns an empty list or `None` without issuing a statement — asserted by patching the database module and observing that nothing on it was called, not merely by observing an empty result.
- [ ] Given `CHAT_SESSION_LIMIT`, when `list_for` is called, then it passes that setting as the limit, and no caller supplies its own — the cap is a deployment decision, not a UI one.
- [ ] Given `create(identity, first_prompt)`, when it is called, then the session is created with a title derived from the prompt, and the derivation is **delegated**, not reimplemented — [[STORY-012]] owns the rule.
- [ ] Given a foreign `session_id`, when it is passed to any function, then the service returns the same not-found value as a genuinely missing id — the caller cannot distinguish "does not exist" from "not yours", following the precedent in [app/services/identity.py](../../../app/services/identity.py)'s `resolve()`: "None covers every failure case alike -- unknown, malformed, empty, or deactivated -- so the caller cannot distinguish them."
- [ ] Given a `StorageError` from the database layer, when it reaches the service, then it is wrapped in a module-owned `ChatSessionError`, in the pattern [app/services/duplicate_checker.py](../../../app/services/duplicate_checker.py) uses for `DuplicateCheckError`.
- [ ] Given [tests/test_chat_sessions.py](../../../tests/test_chat_sessions.py), when it runs, then the flag-off case, the foreign-identity case and the error-wrapping case each have their own assertion.

## Technical Notes

- New file `app/services/chat_sessions.py`. It imports from [app/db/database.py](../../../app/db/database.py) and [app/services/identity.py](../../../app/services/identity.py), and it imports nothing from `chat_ui/`.
- PRD Section 6 names the pattern this story implements, verbatim: "`app/services/chat_sessions.py` holds the ownership rule and the `CHAT_HISTORY_ENABLED` short-circuit in one place, the way `authz.py` holds the permission matrix. `ChatState` calls the service, never `database.py` directly."
- And the flag's shape, also verbatim: "with `CHAT_HISTORY_ENABLED=false` the service returns empty lists and writes nothing, and the rail renders as absent. **No caller branches on the flag.**" A `if settings.CHAT_HISTORY_ENABLED` anywhere outside this module is a defect this story is responsible for preventing.
- Read the setting through `settings.CHAT_HISTORY_ENABLED` at call time, not into a module-level constant at import. [app/services/authz.py](../../../app/services/authz.py)'s `load()` is the counter-example and its docstring says why it is different: it is called once at startup deliberately. A flag captured at import cannot be flipped by a test without reloading the module.
- **No new permission.** PRD Section 9: "`query:submit` still gates sending; owning a session grants nothing beyond reading and deleting it." Do not add a `chat:read:own` to [app/services/authz.py](../../../app/services/authz.py) — RBAC answers what a role may do, ownership answers whose row this is, and PRD Section 6 requires both to apply without either substituting for the other.
- The break-glass `admin` identity gets no special case. PRD Section 9: "The break-glass `admin` identity from `identity.py` owns its own sessions like any other user and gains no read access to anyone else's."
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story touches no UI. No skill applies.

## Dependencies

- **Blocked by**: STORY-001, STORY-004, STORY-005
- **Blocks**: STORY-007, STORY-010, STORY-013

## PRD Reference

Source: [`PRD-008/PRD.md`](../../PRDs/PRD-008-chat-sessions/PRD.md) — Section 4 (Data access, Configuration), Section 6 (Design patterns), Section 9 (Ownership, RBAC interaction), Section 12 Phase 1, Risks 1 & 2
