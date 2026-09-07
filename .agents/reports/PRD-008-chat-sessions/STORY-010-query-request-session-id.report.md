---
story: STORY-010
prd: PRD-008
plan: .agents/plans/PRD-008-chat-sessions/completed/STORY-010-query-request-session-id.plan.md
epic_branch: epic/PRD-008-chat-sessions
commit: 27c7716
status: COMPLETE
completed: 2026-09-04
---

# Implementation Report — STORY-010: QueryRequest.session_id with UUID validation and a 403 on a foreign session

**Plan**: `.agents/plans/PRD-008-chat-sessions/completed/STORY-010-query-request-session-id.plan.md`
**Epic Branch**: `epic/PRD-008-chat-sessions`
**Commit**: `27c7716`

## Summary

`POST /query` now accepts the conversation a send belongs to. `QueryRequest` gained `session_id: Optional[str] = None`, validated by a Pydantic `field_validator` as a **canonical** UUID4 string — v4 only, and the exact 36-character lowercase hyphenated spelling, so `{braces}`, `urn:uuid:` and uppercase hex are refused as second representations of the same id rather than filed into the audit column under a spelling no `WHERE session_id = ?` will match. `app/routers/query.py` refuses a session that is not the caller's with `403 "session_id does not belong to the authenticated identity"`, **audits that refusal**, and otherwise threads `session_id` into `run_query`, where STORY-009 already carries it to all seven `log_query` call sites.

The story's Technical Notes prescribed `chat_sessions.get(...)` and "refuse on `None`". Implementing that literally would have broken the story's own AC 7, and the plan's decision table is why a ninth service function exists instead — see **Deviations** below.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `QueryRequest.session_id` + canonical-UUID4 `field_validator` | `app/models/schemas.py` | ✅ |
| 2 | Request-contract census + validator unit cases | `tests/test_schemas.py` | ✅ |
| 3 | `owns()` — the ninth service function, holding the flag branch | `app/services/chat_sessions.py` | ✅ |
| 4 | The audited 403, the passthrough, `ChatSessionError` → 500 | `app/routers/query.py` | ✅ |
| 5 | The two ownership suites learn about the ninth function | `tests/test_chat_sessions.py`, `tests/test_session_ownership.py` | ✅ |
| 6 | The acceptance suite, driven through `POST /query` | `tests/test_query_session_id.py` | ✅ |
| 7 | Pinned suites unmodified; full suite; clean diff | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Full suite `pytest -q` | ✅ 1388 passed |
| `tests/test_query_session_id.py` | ✅ 23 passed |
| `tests/test_schemas.py` | ✅ 22 passed |
| `tests/test_chat_sessions.py` | ✅ 119 passed |
| `tests/test_session_ownership.py` | ✅ 28 passed |
| Pinned three (`test_query_router`, `test_integration`, `test_route_reservations`) | ✅ 53 passed, `git diff` **empty** for all three |
| `tests/test_untouched_app.py` censuses | ✅ 9 passed |
| E2E against a live uvicorn server + real libSQL | ✅ 11/11 |
| Frontend lint | n/a — no file under `chat_ui/` was opened |

### Mutation checks (a guard never seen to fail is decoration)

Each was applied, observed to fail the intended test, and reverted:

| Mutation | Tests that went red |
|---|---|
| Drop `session_id=request.session_id` from the `run_query` call | `test_omitting_session_id_leaves_the_rest_of_the_audit_row_identical`, `test_the_owner_of_the_session_is_not_refused`, `test_history_off_writes_the_supplied_id_verbatim` |
| `owns()` returns `False` when history is off (the defect the story's literal reading would have shipped) | `test_history_off_makes_the_ownership_check_a_no_op`, `test_history_off_writes_the_supplied_id_verbatim`, `test_owns_answers_true_and_issues_nothing_when_history_is_off` |
| Remove the `log_query` call from the refusal arm | `test_the_403_writes_one_audit_row_naming_the_refusal`, `test_the_unknown_session_refusal_is_audited_too` |

### End-to-end, against a running server

A uvicorn process on the local libSQL dev server, two genuine seeded accounts, `curl`:

| # | Check | Result |
|---|---|---|
| 1 | `session_id: "not-a-uuid"` | 422, body names `["body","session_id"]` |
| 2 | Uppercase UUID4 | 422 |
| 3 | v1 UUID | 422 |
| 4 | Braced UUID | 422 |
| 5 | Session owned by the other account | 403, `{"detail":"session_id does not belong to the authenticated identity"}` |
| 6 | Well-formed UUID4 naming no row | 403, body **byte-identical** to #5 |
| 7 | `session_id` omitted | reaches the pipeline (502 from the deliberately invalid upstream key); audit row `session_id` **NULL** |
| 8 | Caller's own session | reaches the pipeline; audit row carries the id |
| 9 | Audit rows for the four refusals | 4 rows, `success=False`, reason in `error_message`, attempted id on each, `denied_permission` NULL |
| 10 | 422 requests | wrote **no** audit row |
| 11 | `/health`, `/audit`, `/stats` 200; `/sessions` 404 | no new route |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/models/schemas.py` | UPDATE | +58/-1 |
| `app/routers/query.py` | UPDATE | +58 |
| `app/services/chat_sessions.py` | UPDATE | +36 |
| `tests/test_schemas.py` | UPDATE | +69 |
| `tests/test_chat_sessions.py` | UPDATE | +57/-19 |
| `tests/test_session_ownership.py` | UPDATE | +8/-1 |
| `tests/test_query_session_id.py` | CREATE | +491 |

## Deviations from Plan

**One, planned and argued in advance: a ninth function in `app/services/chat_sessions.py`.**

The story named two files and said the check should call `chat_sessions.get(identity, session_id)` and refuse on `None`. That is not implementable alongside the story's own AC 7:

| Approach | 403 on foreign & unknown | Flag off ⇒ no-op (AC 7) | Existing guard |
|---|---|---|---|
| Refuse on `chat_sessions.get(...) is None` | ✅ | ❌ 403s every session-carrying request when history is off | ✅ |
| Router adds `settings.CHAT_HISTORY_ENABLED and ...` | ✅ | ✅ | ❌ fails `test_no_module_outside_the_service_branches_on_chat_history_enabled` |
| **`chat_sessions.owns(identity, session_id)`** | ✅ | ✅ | ✅ |

`get()` short-circuits to `None` when `CHAT_HISTORY_ENABLED` is false, so refusing on `None` 403s every request carrying a `session_id` on a history-off deployment. The obvious repair is forbidden by a pre-existing AST guard that walks every module under `app/` and `chat_ui/`. `owns()` therefore holds the flag branch where PRD Section 6 puts it, and reimplements nothing — it makes the same one-line `database.get_chat_session` call `get()` makes.

Both affected suites document this as their intended extension path: `test_the_service_exposes_exactly_those_eight` said "a later story that exposes a ninth function has to say so by editing this tuple", and `test_the_service_call_table_covers_every_discovered_function` goes red until the new function is driven with a foreign credential. Both were updated accordingly (`THE_EIGHT` → `THE_NINE`; `owns` added to `_KNOWN_SERVICE`, `_SERVICE_SHAPES`, `_SERVICE_READS` and the read control).

**Two smaller notes:**

- `tests/test_schemas.py::test_query_request_contract_is_unchanged` enumerates `QueryRequest`'s fields and is *designed* to fail when one is added. The plan anticipated this; the field list gained `session_id` and two clauses asserting it is optional and defaulted.
- **The refusal is audited; the `user_id` mismatch beside it still is not.** AC 6 requires this arm to be recorded, while `tests/test_query_router.py` pins the older arm to write no row and must pass unmodified. The asymmetry is deliberate, commented at the call site, and pinned by `test_the_user_id_mismatch_403_still_writes_no_row` so the next reader does not unify them by accident.

**Environmental, not a code change:** the local libSQL dev server expires a long-lived process's stream after roughly a minute of inactivity (`STREAM_EXPIRED`), which surfaces as a 500 from `find_user_by_token_hash` in the auth dependency — before any of this story's code runs, and reproducible on the unchanged path. The E2E run above was therefore performed within a single process lifetime. Two full-suite runs also hit the known mass-fixture-error degradation and were re-run green after `docker restart harness-libsql-dev`.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_query_session_id.py` (new, 23) | AC 2: `..._without_session_id_still_succeeds_and_writes_null`, `test_omitting_session_id_leaves_the_rest_of_the_audit_row_identical`. AC 3: `test_a_malformed_session_id_is_a_422_from_validation` (6 params), `test_a_version_1_uuid_is_also_a_422`, `..._names_the_field_in_the_422_body`, `test_a_non_string_session_id_is_also_a_422`. AC 4/5: `..._owned_by_another_identity_is_a_403_with_the_exact_detail`, `test_a_session_that_does_not_exist_is_the_same_403`, `test_the_refused_request_never_reaches_openrouter`, `test_the_owner_of_the_session_is_not_refused`. AC 6: `test_the_403_writes_one_audit_row_naming_the_refusal`, `test_the_unknown_session_refusal_is_audited_too`, `test_the_user_id_mismatch_403_still_writes_no_row`. AC 7: `test_history_off_makes_the_ownership_check_a_no_op`, `test_history_off_writes_the_supplied_id_verbatim`, `test_history_off_still_validates_the_uuid`. AC 8 + structure: `test_the_three_pinned_suites_are_unmodified_in_the_working_tree`, `test_the_router_never_branches_on_the_history_flag` |
| `tests/test_schemas.py` (extended) | `test_query_request_contract_is_unchanged` (now includes `session_id`), `..._accepts_a_uuid4_session_id_unchanged`, `..._omitting_session_id_is_none`, `..._refuses_anything_but_a_canonical_uuid4` (7 params), `..._error_names_the_field` |
| `tests/test_chat_sessions.py` (extended) | `test_owns_answers_true_and_issues_nothing_when_history_is_off`; `owns` folded into `THE_NINE`, so it is now covered by the declaration census, the exact-surface census, the identity-first and no-bare-user_id rules, the store-passthrough check, the flag-off tripwire and the three `ChatSessionError` wrapping tests |
| `tests/test_session_ownership.py` (extended) | `owns` added to `_KNOWN_SERVICE`, `_SERVICE_SHAPES` and `_SERVICE_READS`, so it is discovered, coverage-checked, driven with a foreign credential, and asserted `True` for its owner in the read control |

## Acceptance Criteria

- [x] `QueryRequest` declares `session_id: Optional[str] = None`, validated as a UUID4 string when present
- [x] A request omitting `session_id` produces a response and an audit row identical to the current release, with `session_id` written as `NULL`
- [x] A `session_id` that is not a UUID is `422` from Pydantic validation — not a 500, not silently ignored
- [x] A `session_id` owned by another identity is `403` with detail `"session_id does not belong to the authenticated identity"`, raised beside the existing `user_id` mismatch check
- [x] A `session_id` naming no session at all is the same `403`, byte-identical, so the caller cannot distinguish "not yours" from "does not exist"
- [x] A refused request is recorded in the audit trail
- [x] With `CHAT_HISTORY_ENABLED is False` the ownership check is a no-op and the id is written to the audit row as supplied
- [x] `tests/test_query_router.py`, `tests/test_integration.py` and `tests/test_route_reservations.py` pass **unmodified**
- [x] All tasks completed
- [x] Full suite `pytest -q` green (1388 passed)
- [x] No new route; `tests/test_route_reservations.py` proves it, and `/sessions` is a 404 on the live server
- [x] `QueryRequest.user_id` keeps its deprecated status and its comment
- [x] No module outside `app/config.py` and `app/services/chat_sessions.py` references `CHAT_HISTORY_ENABLED`
- [x] Follows existing patterns (the `user_id` 403, `_deny`'s audit shape, the service's flag-then-`_wrapped` template)
