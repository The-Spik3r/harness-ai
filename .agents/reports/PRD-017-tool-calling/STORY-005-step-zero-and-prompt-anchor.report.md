---
story: STORY-005
prd: PRD-017
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-005-step-zero-and-prompt-anchor.plan.md
epic_branch: epic/PRD-017-tool-calling
commit: pending
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-005: Step 0 accepts tool turns under the D6 shape rules; the audit prompt is the final turn

**Plan**: `.agents/plans/PRD-017-tool-calling/completed/STORY-005-step-zero-and-prompt-anchor.plan.md`
**Epic Branch**: `epic/PRD-017-tool-calling`
**Commit**: `pending`

## Summary

The D6 shape rules live in one pure helper, `conversation_shape_violation(messages) -> Optional[tuple[int, str]]`, in `app/models/messages.py` (four rules, the fourth being "the conversation must contain a user turn", R1, approved; PRD Section 6.3 amended). `_validate_conversation` keeps its empty check and raises `InvalidConversationError("messages[i]: <rule>")` from the helper. The audit `prompt` local stays `messages[-1].content`, now the final turn (user or tool, D7); only comments changed there and at step 6. STORY-008's edge will call the same helper.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Pure D6 helper, rewords | `app/models/messages.py` | done |
| 2 | Step 0 uses the helper; prompt anchor and comments | `app/services/query_pipeline.py` | done |
| 3 | Comment-only fixes | `app/services/conversation_key.py`, `app/services/pii_policy.py` | done |
| 4 | Helper tests | `tests/test_messages.py` | done |
| 5 | Pipeline tests | `tests/test_query_pipeline_tools.py` | done |
| 6 | PRD-017 D6 comment on the old step-0 tool params | `tests/test_query_pipeline_run_conversation.py`, `tests/test_query_pipeline_multiturn.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Frontend lint | n/a (no frontend) |
| Targeted run (messages, tools, run_conversation, multiturn, pii_profiles, dedup_key, patterns, conversation_key, pii_policy, v1_translate_request, query/chat outcomes regression, pii_redaction_integration, untouched_app) | 1025 passed, 2 failed (my new test file only: forbidden/duplicate responses carry no `audit_id`), 0 skipped; 797 s |
| After fixing those two tests (read the last audit row instead), `tests/test_query_pipeline_tools.py` alone | 16 passed |
| Full suite | deferred to orchestrator (user decision) |
| E2E | no live E2E: tool turns cannot reach the pipeline from an ingress until STORY-008 |

## Files Changed

| File | Action |
|------|--------|
| `app/models/messages.py` | UPDATE (helper + comments) |
| `app/services/query_pipeline.py` | UPDATE (step 0, comments) |
| `app/services/conversation_key.py` | UPDATE (comment) |
| `app/services/pii_policy.py` | UPDATE (docstring) |
| `tests/test_messages.py` | UPDATE (add tests) |
| `tests/test_query_pipeline_tools.py` | CREATE |
| `tests/test_query_pipeline_run_conversation.py`, `tests/test_query_pipeline_multiturn.py` | UPDATE (comment) |
| PRD.md (Section 6.3 amendment), STORY-005 / STORY-008 story files, index.md | UPDATE (orchestrator edits, staged here) |

## Deviations from Plan

- R1: fourth D6 rule (user turn) added to the helper; approved by the orchestrator, PRD 6.3 amended.
- AC5: the old step-0 tool tests are kept (they assert only the exception type and still violate D6) with a PRD-017 D6 comment; no function renamed, nothing added to `_DELIBERATELY_SUPERSEDED_TESTS`. Accepted by the orchestrator.
- R4: `prompt_preview` is stored as `prompt[:500]` raw, so tests use multi-line tool content and assert it verbatim.
- The `last message must be a user turn` text for an assistant-final conversation at step 0 is now `messages[N]: the last message must be a user or tool turn`. The `/v1` edge's own strings are untouched (STORY-008, D10).
- The forbidden and duplicate arms return no `audit_id`, so those tests read the latest audit row.

## Tests Written

- `tests/test_messages.py`: `test_shape_accepts` (8), `test_shape_refuses` (11), `test_shape_rule_never_echoes_values` (11), `test_shape_helper_signature`.
- `tests/test_query_pipeline_tools.py` (16): accept, seven D6 violations with zero rows, empty, forbidden/success/duplicate/flag prompt anchor, one-prompt-local source check, tool-final PII under `code`, tool-history PII not counted.

## Acceptance Criteria

- [x] AC1 accepts tool-final, user-final unchanged (`test_shape_accepts`, `test_validate_accepts_a_tool_final_conversation`)
- [x] AC2 each D6 violation names index and rule, no row (`test_shape_refuses`, `test_each_d6_violation_raises_naming_index_and_rule_and_writes_no_row`)
- [x] AC3 prompt is the final tool turn on every arm; user-final unchanged (`test_{forbidden,success,duplicate,flag}_arm_prompt_is_the_tool_turn`, `test_every_log_query_site_reads_the_one_prompt_local`, existing `test_audit_prompt_is_last_user_turn_on_*`)
- [x] AC4 PII fields from the final turn under `code` (`test_tool_final_pii_counts_from_the_final_turn`, `test_pii_in_a_tool_history_turn_is_not_counted`)
- [x] AC5 old step-0 tool tests commented with PRD-017 D6 (deviation above)
