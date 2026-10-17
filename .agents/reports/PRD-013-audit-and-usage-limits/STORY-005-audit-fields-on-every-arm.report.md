---
story: STORY-005
prd: PRD-013
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-005-audit-fields-on-every-arm.plan.md
epic_branch: epic/PRD-013-audit-and-usage-limits
commit: 1ab83f2
status: COMPLETE
completed: 2026-10-17
---

# Implementation Report — STORY-005: log_query and every pipeline arm write the new fields; ingress at every call site

**Plan**: `.agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-005-audit-fields-on-every-arm.plan.md`
**Epic Branch**: `epic/PRD-013-audit-and-usage-limits`
**Commit**: `1ab83f2` (plan: `624d057`)

## Summary

Every row `run_conversation` writes now records four new fields:

- `ingress`, which is what the call site passed.
- `message_count`, which is `len(messages)` as received.
- `conversation_key`, computed once at step 1b over the raw text.
- `streamed`, which is what the call site passed.

The success and output-redaction-error rows also carry `input_tokens` and `output_tokens` from `OpenRouterResult`. The upstream-error row carries neither. `has_tool_calls=False` is passed once, on the success row, with a comment naming PRD-016.

`log_query` takes all eight PRD-013 parameters. `_deny` requires four new ones. `run_query` forwards `ingress="query"`. `/query` and its foreign-session refusal name the `query` door. ChatState names `chat` on both branches.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Baseline: 3425 passed, 27 skipped, 1 failed. The failure is pre-existing and order-dependent; see below | — | ✅ |
| 2 | `log_query` gains eight parameters | `app/services/audit_logger.py` | ✅ |
| 3 | Persist and default tests | `tests/test_audit_logger.py` | ✅ |
| 4 | Pipeline: step 1b, ten arms, `_deny` +4, `run_query` | `app/services/query_pipeline.py` | ✅ |
| 5 | Foreign-session row (comment item 7) and explicit `ingress` on the route's `run_query` | `app/routers/query.py` | ✅ |
| 6 | `ingress="chat"` on both branches | `chat_ui/chat_ui/state.py` | ✅ |
| 7 | Signature pins and fixed-signature stubs (F-2) | five test files | ✅ |
| 8 | New module: AC 1-5 | `tests/test_query_pipeline_audit_fields.py` | ✅ |
| 9 | Full suite | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A: there is no `frontend/`. The chat UI is Reflex and no linter is configured |
| `curl /health` | ✅ `{"status":"ok"}` |
| Tests | ✅ 3466 passed, 27 skipped, 0 failed (baseline 3426 + 40 new) |
| `git diff tests/test_audit_characterization.py` | ✅ empty |
| Scan mutation check | ✅ Removing one `ingress="chat"` made the scan fail at `chat_ui/chat_ui/state.py:1133`. The line was then restored |
| E2E | ✅ 3/3 (see below) |

### Baseline failure (pre-existing)

`tests/test_rbac.py::test_query_submit_matrix_through_post_query[auditor]` failed in the baseline run at `assert _count_audit_rows() == 0`, before any change was made. It passes when run on its own and passed in the post-change full run. It is order-dependent leakage between tests, which is the subject of the untracked `pre-prds/PRE-PRD-017-test-suite-db-isolation.md`. It is not related to this story.

### E2E

The configured `OPENROUTER_API_KEY` returns **401 Unauthorized**, so a live success response was not possible.

1. **Live `POST /query`** (`python app.py`, real key): HTTP 502. The row is the upstream-error arm: `ingress='query'`, `message_count=1`, a 64-hex `conversation_key`, `streamed=0`, and `input_tokens`/`output_tokens` NULL. That matches AC 1's "the upstream-error row has neither".
2. **`POST /query` over real HTTP with only the upstream stubbed** (a uvicorn server on :8001 with `app.routers.query.call_openrouter` replaced): HTTP 200 `SUCCESS`. The row has `ingress='query'`, `message_count=1`, `streamed=0`, `has_tool_calls=0`, `input_tokens=30`, `output_tokens=12` and `tokens_used=42`.
3. **Three chat sends in one chat** through the real `ChatState`, the real pipeline, the real PII model and the dev database, with the upstream stubbed: `ingress='chat'` on all three, `message_count` 1, 3 and 5, all in one session.

E2E 2 and 3 replace the provider call only. Rerun them live once the key is valid.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/audit_logger.py` | UPDATE | +26 |
| `app/services/query_pipeline.py` | UPDATE | +88/-3 |
| `app/routers/query.py` | UPDATE | +13 |
| `chat_ui/chat_ui/state.py` | UPDATE | +5 |
| `tests/test_query_pipeline_audit_fields.py` | CREATE | +516 |
| `tests/test_audit_logger.py` | UPDATE | +40 |
| `tests/test_query_pipeline_run_conversation.py` | UPDATE | +16/-3 |
| `tests/test_chat_state.py` | UPDATE | +10/-1 |
| `tests/test_chat_history_send.py` | UPDATE | +5/-1 |
| `tests/test_chat_outcomes_regression.py` | UPDATE | +2/-1 |
| `tests/test_rbac.py` | UPDATE | +2/-1 |

Total: 723 insertions and 10 deletions across 11 files.

## Deviations from Plan

1. **The route passes `ingress="query"` explicitly.** Task 5 covered only the foreign-session row. AC 5 requires every production call to pass `ingress` explicitly, and the plan's own scan lists the route's `run_query` call as a checked site. So the route spells out the default, with a comment saying why.
2. **The chat helpers are mirrored, not imported.** Task 8 said to import `_make_state`/`_send` from `tests/test_chat_history_send.py`. That module's docstring says cross-importing is not this suite's convention, so the three small helpers are mirrored, with a comment saying so. Imports from `tests/test_audit_characterization.py` stay, because that module explicitly allows them.
3. **`_shipped_settings` is imported from the characterization module as an autouse fixture.** It gives this module shipped settings and a pass-through `redact` everywhere, so no test loads the spaCy model. The plan expected each section to stub `redact` itself.
4. **An extra test.** `test_a_response_without_the_split_still_records_the_total` covers the PRD Section 11 line "a provider response without the split still succeeds, with both fields NULL and tokens_used set" at the pipeline level.
5. **E2E used a stubbed upstream.** The OpenRouter key is invalid; see above.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_query_pipeline_audit_fields.py` | `test_every_characterized_arm_has_expectations_here`; `test_each_arm_writes_the_new_fields` ×12; `test_a_direct_call_without_a_door_records_null` ×12; `test_deny_requires_each_new_field_with_no_default` ×4; `test_a_response_without_the_split_still_records_the_total`; `test_query_rows_name_the_query_door` ×2; `test_the_foreign_session_refusal_names_the_door_and_no_key`; `test_the_nth_chat_send_carries_2n_minus_1_messages`; `test_a_chat_send_without_history_names_the_chat_door`; `test_a_fifty_turn_conversation_is_one_conversation_of_fifty_rows`; `test_every_production_pipeline_call_names_its_door`; `test_every_direct_log_query_call_passes_the_three_fields` (38 in all) |
| `tests/test_audit_logger.py` | `test_prd013_fields_persisted_when_supplied`, `test_prd013_fields_default_when_omitted` |

## Acceptance Criteria

- [x] Any arm of `run_conversation` writes `ingress` (as passed), `message_count == len(messages)`, a non-NULL `conversation_key` and `streamed` (as passed). The success and output-redaction-error rows have the token pair. The upstream-error row has neither.
- [x] `POST /query` success and block rows have `ingress='query'` and `message_count=1`. The foreign-session refusal has `ingress='query'`, `message_count=1` and `conversation_key` NULL.
- [x] Chat sends with history and without it are `ingress='chat'`. The Nth send with nothing trimmed has `message_count == 2N-1`, checked against what the pipeline received.
- [x] A 50-turn `run_conversation(ingress="v1")` gives 50 rows, one `conversation_key`, 50 distinct `dedup_key` values and `ingress='v1'` on each.
- [x] Scan: every `run_conversation`/`run_query` call in `app/` and `chat_ui/` passes `ingress` or is `run_query`'s delegation. Every direct `log_query` call passes `ingress`, `message_count` and `conversation_key`.
