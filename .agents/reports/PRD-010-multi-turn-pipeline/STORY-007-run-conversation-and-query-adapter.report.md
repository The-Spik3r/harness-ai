---
story: STORY-007
prd: PRD-010
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-007-run-conversation-and-query-adapter.plan.md
epic_branch: epic/PRD-010-multi-turn-pipeline
commit: 0096e2e
status: COMPLETE
completed: 2026-09-18
---

# Implementation Report — STORY-007: run_conversation over messages; run_query becomes a one-message adapter

**Plan**: `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-007-run-conversation-and-query-adapter.plan.md`
**Epic Branch**: `epic/PRD-010-multi-turn-pipeline`
**Commit**: `0096e2e`

## Summary

`app/services/query_pipeline.py` was rewritten so `run_conversation(identity, messages, device, model, openrouter_api_key, params=None, call_openrouter=call_openrouter, session_id=None)` is the pipeline, holding the same check order the prior `run_query` had (authorize/model/BYOK → duplicate → pattern → redact → upstream → redact response → audit), with a `# context limit (STORY-008)` marker left at the insertion point for the next story. `run_conversation` validates conversation structure first — empty, non-user-final, or any `tool` turn — raising `InvalidConversationError` before `dedup_key`, authorization, or any `log_query` call, so it is unreachable from any ingress this PRD ships and writes no audit row. `dedup_key` now runs over the raw `messages` sequence; the audit `prompt` on every arm is the last user turn's content; pattern detection runs through a new provisional `_inspection_target(messages)` (last user turn only, D6); every message is redacted before it leaves the process (D5), with PII-audit fields (`pii_detected_input`, `pii_entities`) scoped to only the last user turn's redact call plus the output (D7). `params` is forwarded to `call_openrouter` only when not `None`, preserving compatibility with the ~90 existing injected `(messages, model, api_key)` test stubs. `run_query` is now a one-line adapter: `return run_conversation(identity, [Message("user", prompt)], device, model, openrouter_api_key, call_openrouter=call_openrouter, session_id=session_id)`, with its exact signature unchanged. The private `_UserTurn` dataclass is deleted.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Rewrite `query_pipeline.py`: `InvalidConversationError`, `_validate_conversation`, `_inspection_target`, `run_conversation`, `run_query` adapter, `_UserTurn` deleted | `app/services/query_pipeline.py` | ✅ |
| 2 | Repoint `test_messages.py`'s `_UserTurn` reference at the file's own local `_Turn` stand-in; drop the now-unused `query_pipeline` import | `tests/test_messages.py` | ✅ |
| 3 | Create this story's own tests (`InvalidConversationError`, adapter delegation, D5/D7 redaction+audit scoping, `_inspection_target`, placeholder passthrough, conditional `params`) | `tests/test_query_pipeline_run_conversation.py` | ✅ |
| 4 | Run the full suite and the two AC-named files explicitly | n/a (validation) | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`python -c "import app.services.query_pipeline"`) | ✅ |
| `_UserTurn` fully removed (`grep -rn "_UserTurn" app/ tests/ chat_ui/`) | ✅ only comment/assertion references remain |
| `InvalidConversationError` defined and raised only in `query_pipeline.py`, caught nowhere | ✅ |
| `tests/test_query_pipeline_dedup_key.py` + `tests/test_pii_dedup_isolation.py` (AC-named, unmodified) | ✅ 32 passed |
| `tests/test_messages.py` | ✅ 50 passed |
| `tests/test_query_pipeline_run_conversation.py` (new) | ✅ 18 passed |
| Full suite `pytest tests/` | ✅ 2083 passed, 25 skipped, 0 failed (27m21s) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/query_pipeline.py` | UPDATE | rewritten (~300 lines; `_UserTurn` removed, `run_conversation`/`InvalidConversationError`/`_inspection_target`/`_validate_conversation` added) |
| `tests/test_messages.py` | UPDATE | -8/+7 (one test repointed at local `_Turn`; unused import dropped) |
| `tests/test_query_pipeline_run_conversation.py` | CREATE | +~300 (18 tests) |
| `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-007-run-conversation-and-query-adapter.plan.md` | CREATE (archived) | +638 |

## Deviations from Plan

- Task 2: the plan proposed adding a new local `_Turn` dataclass to `tests/test_messages.py`. On inspection, that file already defines a structurally identical `_Turn(role, content)` dataclass (used a few lines below by `test_multi_turn_message_list_matches_structural_turns`), so the existing one was reused instead of duplicating it. The assertion itself is unchanged, per the original test's own comment ("never delete the assertion").
- No other deviations. The `run_conversation`/`run_query` implementation matches the plan's snippet essentially verbatim.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_query_pipeline_run_conversation.py` | `_UserTurn` deleted; `run_conversation`/`run_query` signatures; adapter delegation with exact forwarded args; `InvalidConversationError` for `[]`/non-user-final/tool-turn-present (zero audit rows, `authorize` and `dedup_key` never called); `dedup_key` computed over raw messages before authorization; audit `prompt` = last user turn on duplicate/suspicious/success arms; `_inspection_target` docstring + last-turn-only behavior; provisional policy ignores injection in an earlier turn; D5 (every message redacted, AC's exact PII scenario); D7 (PII audit fields scoped to last turn + output, both the "no PII in last turn" and "PII in last turn" cases); already-redacted assistant turn passes through unchanged; `params=None` omitted from the call, `params=GenerationParams(...)` forwarded exactly |
| `tests/test_messages.py` | `test_message_list_keys_like_a_structural_user_turn` (was `test_message_list_keys_like_the_pipeline_user_turn_today`) — same assertion, now against the file's local `_Turn` instead of the deleted `query_pipeline._UserTurn` |

## Acceptance Criteria

- [x] `run_conversation(identity, messages, device, model, openrouter_api_key, params=None, call_openrouter=call_openrouter, session_id=None)` holds the pipeline; `run_query`'s exact signature is unchanged and its body is a single `return run_conversation(...)`; `_UserTurn` is deleted.
- [x] `messages` that is `[]`, ends in a non-`user` turn, or contains any `tool` turn raises `InvalidConversationError` before key derivation, authorization or any `log_query` (zero audit rows, asserted).
- [x] `key = dedup_key(identity.user_id, messages)` on the raw messages; audit `prompt` on every arm is the last user turn's content; pattern detection runs on `_inspection_target(messages)`, docstring-marked `PROVISIONAL (PRD-010 D6)`.
- [x] `[user("my email is jane@corp.com"), assistant("noted"), user("what is my email?")]` — no recorded upstream content contains `jane@corp.com` (D5); audit `pii_detected_input`/`pii_entities` reflect only the last user turn plus output (D7), `EMAIL_ADDRESS` absent when neither contains an email.
- [x] Full suite green (2083 passed, 25 skipped, 0 failed), including the six-outcome regression, `test_query_pipeline_dedup_key.py`, and `test_pii_dedup_isolation.py::test_hash_prompt_only_ever_receives_raw_text`, with no outcome assertion changed; single-turn upstream payload remains byte-identical (STORY-003).
