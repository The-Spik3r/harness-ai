---
target_prd: PRD-013
slug: audit-and-usage-limits
title: Audit for conversations and usage limits
status: draft
prd:
depends_on: [PRD-010]
blocks: [PRD-014]
estimated_stories: 16-18
created: 2026-09-16
---

# Audit for conversations and usage limits

## Problem

**Audit was shaped for one prompt, one response.** [audit_logger.py](../app/services/audit_logger.py) stores `prompt_hash` and `prompt_preview = prompt[:500]` (same for response). It does *not* store the full prompt, so storage growth is not the issue. The issue is meaning:

- For a multi-turn request, "the prompt" is undefined. The first 500 characters of a conversation are usually the system prompt — identical on every row and useless as evidence.
- No column records: which ingress (`/query` vs `/v1`), how many messages, input vs. output tokens (only `tokens_used` total), whether the response was streamed, whether it carried tool calls, which role triggered a block (PRD-011 adds that one).
- `session_id` requires a harness-minted UUID4 (PRD-008). External clients have no session; there is no way to group an agent's turns into one conversation.

**There are no usage limits.** No rate limit and no token budget per user or role. The harness holds the only OpenRouter key, so any valid user token can spend it without bound — and a coding agent in a loop will.

**The admin token is a sharp edge.** `resolve()` ([identity.py:55](../app/services/identity.py)) maps `ADMIN_TOKEN` to the break-glass admin, which bypasses the model allowlist. It will end up pasted into an agent's config.

## Goal

Every row answers "what was attempted, by whom, through which door, at what cost" for multi-turn traffic; every user has a bounded spend; the break-glass credential stays break-glass.

## Proposed scope

**In**
- Additive migration: `ingress`, `message_count`, `input_tokens`, `output_tokens`, `streamed`, `has_tool_calls`, `conversation_key`.
- Preview policy for multi-turn: preview of the **last user turn**, hash of the full conversation.
- OpenRouter client returns prompt/completion tokens separately.
- Conversation grouping for external clients (derived key, see D2).
- Token budget per user per period; request rate limit per user; both configurable per role.
- Budget/rate refusals audited like any block.
- Admin token policy for non-UI ingress.
- `/audit`, `/stats` and the admin console surface the new fields and a usage view.

**Out**
- Billing, invoices, cost in currency (tokens only).
- Distributed rate limiting beyond what Turso provides.

## Open decisions

| # | Question | Proposed default |
|---|---|---|
| D1 | Budget period | Daily, UTC, per user; role-level default with per-user override. |
| D2 | Conversation key for external clients | Hash of the first `system` + first `user` message + user_id. |
| D3 | Rate limit storage | Turso counter rows, consistent across instances (PRD-007 two-instance requirement). |
| D4 | Admin token on `/v1` | Refused; admins use a normal user token with the `admin` role. |
| D5 | Budget exhausted response | 403 with a reason, never 429 (clients auto-retry 429). |

## Evidence

- `_PREVIEW_LENGTH = 500`; `response_hash`, `response_preview` computed the same way.
- `call_openrouter` reads only `usage.total_tokens`.
- `MODEL_ALLOWLIST_WILDCARD_ROLES` bypass in `authorize_model` ([authz.py](../app/services/authz.py)).

## Success criteria

- A 50-turn conversation produces 50 rows sharing one `conversation_key`, each previewing its own user turn.
- A user over budget is refused and the refusal is audited; another user is unaffected.
- Limits hold across two instances.
- `ADMIN_TOKEN` is refused on the non-UI ingress.
- Admin console shows usage per user without breaking existing views.

## Risks

| Risk | Mitigation |
|---|---|
| Counter writes add latency to every request | Batched read of counters (PRD-007 pattern); write after response. |
| Derived conversation key collides across unrelated conversations | Includes user_id; documented as grouping aid, not identity. |
| Admin console scope creep (PRD-006 was 20 stories) | Usage view limited to one table; charts out of scope. |

## Tentative story breakdown

1. Additive migration of new audit columns
2. `log_query` accepts new fields; preview policy for multi-turn
3. Split token counts from OpenRouter
4. Conversation key derivation
5. Pipeline writes new fields on every arm
6. `/audit` entry fields
7. `/stats` usage aggregates
8. Budget and rate settings (role default, user override)
9. Usage counter storage
10. Budget enforcement in pipeline
11. Rate limit enforcement
12. Audited refusals
13. Admin token policy on non-UI ingress
14. Admin console: new columns and filters
15. Admin console: usage view
16. Two-instance limit test
17. Console regression
18. README and `.env` docs
