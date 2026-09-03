---
id: STORY-010
prd: PRD-008
slug: query-request-session-id
title: "QueryRequest.session_id with UUID validation and a 403 on a foreign session"
type: feature
priority: high
complexity: medium
phase: "2 - Pipeline and API"
status: todo
labels: [backend, api, security]
epic_branch: epic/PRD-008-chat-sessions
plan: null
report: null
commit: null
depends_on: [STORY-006, STORY-009]
blocks: [STORY-021, STORY-022]
skills: []
created: 2026-09-02
updated: 2026-09-02
---

# STORY-010: QueryRequest.session_id with UUID validation and a 403 on a foreign session

## Description

As an integrating developer, I want `POST /query` to keep working unchanged when I send no `session_id`, so that adopting this release requires no client change (PRD Section 5, story 9) — and as a security admin, I want a session id belonging to someone else refused rather than honoured.

## Acceptance Criteria

- [ ] Given [app/models/schemas.py](../../../app/models/schemas.py), when `QueryRequest` is read, then it declares `session_id: Optional[str] = None`, validated as a UUID4 string when present.
- [ ] Given a request omitting `session_id`, when it is served, then the response and the audit row are identical to the current release, with `session_id` written as `NULL`.
- [ ] Given a request whose `session_id` is not a UUID, when it is served, then the response is `422` from Pydantic validation — not a 500 and not a silently ignored field.
- [ ] Given a request whose `session_id` names a session owned by another identity, when it is served, then the response is `403` with detail `"session_id does not belong to the authenticated identity"`, raised in [app/routers/query.py](../../../app/routers/query.py) beside the existing `user_id` mismatch check.
- [ ] Given a request whose `session_id` names no session at all, when it is served, then the response is the same `403` — the caller cannot distinguish "not yours" from "does not exist", matching [app/services/identity.py](../../../app/services/identity.py)'s rule that "None covers every failure case alike... so the caller cannot distinguish them."
- [ ] Given a refused request, when the audit trail is read, then the refusal is recorded — a rejected send is logged with the same rigour as an accepted one, which is PRD-001's founding property.
- [ ] Given `settings.CHAT_HISTORY_ENABLED is False`, when a request carries a `session_id`, then the ownership check is a no-op and the id is written to the audit row as supplied — the flag governs the transcript, not the audit column.
- [ ] Given [tests/test_query_router.py](../../../tests/test_query_router.py), [tests/test_integration.py](../../../tests/test_integration.py) and [tests/test_route_reservations.py](../../../tests/test_route_reservations.py), when the suite runs, then all three pass **unmodified**.

## Technical Notes

- Files: [app/models/schemas.py](../../../app/models/schemas.py), [app/routers/query.py](../../../app/routers/query.py).
- Put the ownership refusal immediately beside the existing check, which is the precedent for exactly this shape:

  ```python
  if request.user_id is not None and request.user_id != identity.user_id:
      raise HTTPException(status_code=403, detail="user_id does not match the authenticated identity")
  ```

- The check calls `chat_sessions.get(identity, session_id)` from [[STORY-006]] and refuses on `None`. Do not reimplement the `WHERE user_id = ?` here — PRD Section 6 puts the ownership rule in exactly one module.
- Validate the UUID with a Pydantic validator on the string field rather than typing it as `uuid.UUID`. The field round-trips to the audit column and to `ChatState` as a string, and a type that serializes differently on the way out is a second representation of the same id.
- **No new route.** PRD Section 10: "Session management is in-process from `ChatState` through `app/services/chat_sessions.py`... A REST surface for sessions would need its own auth story and its own tests to earn a place." `tests/test_route_reservations.py` passing unmodified is the proof, and the `Caddyfile`'s `@backend_routes` matcher needs no change.
- `QueryRequest.user_id` keeps its deprecated status and its comment. This story adds a field beside it; it does not revisit it.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story touches no UI. No skill applies.

## Dependencies

- **Blocked by**: STORY-006, STORY-009
- **Blocks**: STORY-021, STORY-022

## PRD Reference

Source: [`PRD-008/PRD.md`](../../PRDs/PRD-008-chat-sessions/PRD.md) — Section 4 (Pipeline & API), Section 5 (story 9), Section 9 (Ownership), Section 10, Section 12 Phase 2, Risk 3
