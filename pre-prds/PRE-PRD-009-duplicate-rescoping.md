---
target_prd: PRD-009
slug: duplicate-rescoping
title: Duplicate detection rescoping
status: promoted
prd: .agents/PRDs/PRD-009-duplicate-rescoping/PRD.md
depends_on: []
blocks: [PRD-010]
estimated_stories: 8-10
created: 2026-09-16
---

# Duplicate detection rescoping

## Problem

Duplicate detection is the product's central control, and its current scope is wrong for any traffic that retries or converses.

1. **Failed attempts count as prior queries.** `find_duplicate_timestamp` ([app/db/database.py:758](../app/db/database.py)) matches `prompt_hash` against every `audit_logs` row in the window, with no filter on `success`. The pipeline logs a failed OpenRouter call with the prompt ([query_pipeline.py](../app/services/query_pipeline.py), `except OpenRouterError`), so the user's retry is held as a duplicate of the call that failed. This is a defect in `POST /query` today; coding agents retry automatically, which turns it into a loop.
2. **The hash is global.** `check_duplicate(prompt)` ([duplicate_checker.py](../app/services/duplicate_checker.py)) has no user or session scope. Two users sending the same prompt block each other.
3. **Multi-turn is undefined.** The README ([Multi-turn context](../README.md#multi-turn-context)) names this as the reason multi-turn is deferred: "yes", "go on", "thanks" would collide across every user. PRD-010 cannot ship until the key is defined.

## Goal

A duplicate means *the same caller asking the same thing in the same context within the window* — and nothing else. Defined once, in a shape that already accommodates multi-turn input.

## Proposed scope

**In**
- Exclude failed attempts (`success = 0`) from the duplicate lookup.
- Scope the lookup by `user_id`.
- A key function that takes the conversation, not a string: e.g. `hash(user_id, last_user_turn, hash(prefix))`. With single-turn input the prefix is empty, so `/query` behaviour is a special case.
- Index supporting the new lookup (`user_id, prompt_hash, timestamp`), converged by `init_db()`.
- Characterization tests pinning today's behaviour before the change; regression of the six `/query` outcomes.
- README update: the Multi-turn context section's blocker is resolved.

**Out**
- Semantic duplicate detection (separate roadmap item).
- Accepting message arrays in the pipeline (PRD-010).
- Changing the 24h window.

## Open decisions

| # | Question | Proposed default |
|---|---|---|
| D1 | Is a policy denial (`denied_permission` set, `success=True`) a prior query for duplicate purposes? | No — only rows that reached the model or were blocked by a content check count. |
| D2 | Scope: `user_id` only, or `user_id + session_id`? | `user_id` + conversation prefix hash. A session id is not available to external clients. |
| D3 | Does a duplicate-blocked row itself extend the window? | No — match the first *non-blocked* occurrence, as today's `ORDER BY timestamp ASC` implies. |
| D4 | Are `tool`-role turns ever part of the key? | Not in this PRD; revisit in PRD-016. |
| D5 | Is `prompt_hash` recomputed, or is a new `dedup_key` column added? | New column, so existing rows and `/audit` semantics are untouched. |

## Evidence

- `find_duplicate_timestamp` — `WHERE prompt_hash = ? AND timestamp >= ?`, no `success`, no `user_id`.
- `log_query` stores `prompt_hash = hash_prompt(prompt)` on every arm, including failures.
- README: "Rescoping that hash … deserves its own threat reasoning and its own tests rather than arriving as a side effect."

## Success criteria

- A retry after an OpenRouter failure is not blocked.
- The same prompt from two users is not blocked.
- The same prompt from the same user within 24h, after a success, is still blocked.
- `/query` without the new behaviour's inputs returns the same six outcomes as before.

## Risks

| Risk | Mitigation |
|---|---|
| Weakening the central control (per-user scope lets N accounts bypass it) | State explicitly in the threat model; rate limits in PRD-013 cover multi-account abuse. |
| Excluding failures lets an attacker probe by forcing errors | Failures still audited; count them in PRD-013's usage limits. |
| Libsql index migration on a live Turso DB | Additive, idempotent, same pattern as PRD-008 STORY-003. |

## Tentative story breakdown

1. Threat reasoning + characterization tests of current duplicate behaviour
2. `dedup_key` column and index, converged by `init_db()`
3. Key function over a conversation (single-turn as special case)
4. Lookup excludes failed rows
5. Lookup scoped by user
6. `check_duplicate` and pipeline use the new key; `log_query` writes it
7. Two-user and retry-after-failure tests
8. Six-outcome regression
9. README and `.env` docs
