---
story: STORY-013
prd: PRD-013
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-013-break-glass-ingress-policy.plan.md
epic_branch: epic/PRD-013-audit-and-usage-limits
commit: 180ca6c
status: COMPLETE
completed: 2026-10-19
---

# Implementation Report — STORY-013: Break-glass ingress policy

**Plan**: `.agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-013-break-glass-ingress-policy.plan.md`
**Epic Branch**: `epic/PRD-013-audit-and-usage-limits`
**Commit**: `180ca6c`

## Summary

`run_conversation` has a new step 2b, which runs after the three authorization arms and before the step 2c usage gate. The step calls `_break_glass_refused(identity, ingress)`. That function returns True when `identity.break_glass` is set and `ingress` is not in `settings.break_glass_ingresses`. When it returns True, the request goes through the existing forbidden arm: `_deny(..., exc=PermissionDenied("ingress:break_glass"), reason="Break-glass credential not permitted on this ingress")`. That writes one row with `success=True` and returns `QueryBlockedForbiddenResponse`.

- **Marker:** the credential, not the role. Only `resolve(ADMIN_TOKEN)` sets `break_glass`. An admin-role user token is never refused here, and neither is an `Identity("admin", "admin")` built directly.
- **Fail closed:** `ingress=None` is in no allowed set, so a direct call that passes no ingress is refused.
- **Per call:** `settings.break_glass_ingresses` is read on every call, so a change to the setting takes effect without a restart.
- **No new surface:** no response class, no RBAC permission (`"ingress:break_glass"` is only a row label), and no changes to the router, ChatState or AdminState.
- **Typing:** `Ingress = Literal["query", "chat", "v1"]` now types `ingress` on `_deny`, `run_conversation` and `run_query`. `log_query` stays `Optional[str]`, so the logger does not import from the pipeline.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `Ingress` Literal; `ingress` annotations on `_deny`, `run_conversation`, `run_query` | `app/services/query_pipeline.py` | ✅ |
| 2 | `_break_glass_refused` predicate, module-level so tests can spy on it | `app/services/query_pipeline.py` | ✅ |
| 3 | Step 2b arm; 2c comment and `_deny` comment no longer say "three arms" | `app/services/query_pipeline.py` | ✅ |
| 4 | 26 tests covering AC 1-5 | `tests/test_query_pipeline_break_glass.py` | ✅ |
| 5 | Full regression | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A (no frontend in this repo; the Reflex UI is unchanged) |
| New tests | ✅ 26 passed |
| Related suites (usage limits, authorization, audit fields) | ✅ 85 passed |
| Full suite | ✅ 3685 passed, 27 skipped, 0 failed |
| Mutation check (predicate forced to `False`) | ✅ 9 tests fail, so the arm is pinned. Code restored. |
| E2E | ✅ 3/3 |

### E2E (live uvicorn on :8765 against the dev libSQL container)

1. **Default setting.** `POST /query` with `ADMIN_TOKEN` got past authorization and step 2b and reached upstream. The response was `502` with OpenRouter `401`, the same as `/query` returns on this machine today, because there is no working upstream key. That is today's behaviour, unchanged by this story.
2. **`BREAK_GLASS_INGRESSES=chat`.** `POST /query` returned `200` with `{"status":"BLOCKED","reason":"Break-glass credential not permitted on this ingress","required_permission":"ingress:break_glass"}`. The `/audit` row, matched by `prompt_hash`, has `user_id=admin`, `role=admin`, `denied_permission=ingress:break_glass`, `ingress=query` and `message_count=1`.
3. **`BREAK_GLASS_INGRESSES=v1`.** Startup was refused with STORY-007's message naming the setting.

To start the server, the dev DB needed one active user, because the test suite's `temp_db` empties the shared DB. The E2E created one with `scripts/manage_users.py create-user --user-id e2e-bootstrap --role user`. That user is still in the dev DB.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/query_pipeline.py` | UPDATE | +50/-6 |
| `tests/test_query_pipeline_break_glass.py` | CREATE | +398 |

## Deviations from Plan

- **One test added:** `test_a_refused_break_glass_attempt_stops_before_the_gate`. The plan didn't list it. It records that a refused attempt's trace ends at `break_glass` and never reaches `usage`.
- **Comment fix:** `_deny`'s comment said it served "all three authorization arms". It now says "every authorization arm".
- **AdminState test:** the test builds `AdminState` and drives `authenticate` inline instead of importing `tests/test_admin_state.py`'s helpers. That module does not document its helpers as importable, and the plan said to copy them in that case.
- **E2E step 1:** the plan expected "SUCCESS or the usual upstream outcome". The outcome was the usual upstream failure (502). The success path under the default setting is covered in-process by `test_post_query_with_admin_token_succeeds_under_the_default` and the chat-UI test.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_query_pipeline_break_glass.py` | refused with body and one row (`v1`, no ingress); refusal holds with limits off; label not in `_KNOWN_PERMISSIONS`; default admits on `query`/`chat`; `POST /query` with `ADMIN_TOKEN` succeeds by default; chat UI send answered by default; `chat` setting refuses `/query` with the 200 body; `""` setting refuses chat with the forbidden bubble; setting read per call; admin-role user token not refused on `v1`; direct `Identity("admin","admin")` not refused; predicate table (8 cases); admin console gate unaffected and never enters the pipeline; order: authorize → break_glass → usage → …; order with BYOK; refused attempt stops before the gate; authorization denial never reaches break_glass |

## Acceptance Criteria

- [x] Given the identity `resolve(ADMIN_TOKEN)` returns, when `run_conversation(..., ingress="v1")` or `run_conversation(...)` with no ingress runs, then it returns `QueryBlockedForbiddenResponse(reason="Break-glass credential not permitted on this ingress", required_permission="ingress:break_glass")`, writes one row with `denied_permission="ingress:break_glass"`, and makes no upstream call.
- [x] Given the default `BREAK_GLASS_INGRESSES`, when the break-glass identity sends through `POST /query` or the chat UI, then the request proceeds exactly as before this story.
- [x] Given `BREAK_GLASS_INGRESSES="chat"`, when the break-glass identity calls `POST /query`, then it gets the `200` policy-refusal body; given `""`, then the chat UI refuses it too.
- [x] Given a user token whose role is `admin`, or an `Identity("admin", "admin")` built directly, when it runs under `ingress="v1"`, then this arm does not fire.
- [x] Given the admin console, when `ADMIN_TOKEN` is submitted at its gate, then sign-in works as before, and spies show this arm runs after the three authorization arms and before the usage gate.
