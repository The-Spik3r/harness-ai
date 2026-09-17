---
id: STORY-007
prd: PRD-010
slug: run-conversation-and-query-adapter
title: "run_conversation over messages; run_query becomes a one-message adapter"
type: feature
priority: high
complexity: large
phase: "2 - Pipeline over messages"
status: todo
labels: [backend, pipeline, pii, duplicates]
epic_branch: epic/PRD-010-multi-turn-pipeline
plan: null
report: null
commit: null
depends_on: [STORY-001, STORY-004, STORY-005]
blocks: [STORY-008, STORY-009, STORY-012]
skills: []
created: 2026-09-17
updated: 2026-09-17
---

# STORY-007: run_conversation over messages; run_query becomes a one-message adapter

## Description

As the PRD-011/012/014 implementer, I want one pipeline function that takes a conversation, with `run_query(prompt)` as a thin adapter over it, so that every ingress shares one ordered sequence of checks, and history is always redacted before it leaves the process.

## Acceptance Criteria

- [ ] Given [app/services/query_pipeline.py](../../../app/services/query_pipeline.py), when it is read, then `run_conversation(identity, messages, device, model, openrouter_api_key, params=None, call_openrouter=call_openrouter, session_id=None)` holds the pipeline. `run_query(identity, prompt, device, model, openrouter_api_key, call_openrouter=call_openrouter, session_id=None)` keeps its exact signature, and its body is a single `return run_conversation(identity, [Message("user", prompt)], …)`. The private `_UserTurn` is deleted.
- [ ] Given `messages` that is `[]`, ends in a non-`user` turn, or contains any `tool` turn, when `run_conversation` is called, then it raises `InvalidConversationError` **before** key derivation, authorization or any `log_query` (test asserts zero audit rows).
- [ ] Given a valid conversation, when it runs, then: `key = dedup_key(identity.user_id, messages)` on the raw messages; the audit `prompt` on every arm is the **last user turn's** content; pattern detection runs on `_inspection_target(messages)`, a named function returning the last user turn, with a docstring marking it `PROVISIONAL (PRD-010 D6)` for PRD-011 to replace.
- [ ] Given `[user("my email is jane@corp.com"), assistant("noted"), user("what is my email?")]` with redaction on, when the injected upstream records its messages, then **no** recorded content contains `jane@corp.com` (every message is redacted, D5). The audit row's `pii_detected_input` and `pii_entities` reflect only the last user turn plus the output (D7), so `EMAIL_ADDRESS` is absent when neither contains an email.
- [ ] Given the full suite, including the six-outcome regression, [tests/test_query_pipeline_dedup_key.py](../../../tests/test_query_pipeline_dedup_key.py) and [tests/test_pii_dedup_isolation.py](../../../tests/test_pii_dedup_isolation.py) (`test_hash_prompt_only_ever_receives_raw_text`), when this story lands, then it is green with no outcome assertion changed. For single-turn input the upstream payload is still byte-identical (STORY-003).

## Technical Notes

- Check order (PRD 6.1): validate → key → authorize/model/BYOK → *(context limit: STORY-008)* → duplicate → patterns → redact every message → upstream → redact output → audit. Leave a `# context limit (STORY-008)` marker at the insertion point.
- Redaction loop: `redact(m.content)` per message, keeping roles. Keep the entities only from the **last user turn's** call. An input `PiiRedactorError` on *any* message follows the existing input-redactor arm (row with `success=False`, re-raise). Assistant contents that are already placeholders pass through unchanged (Presidio's default `<ENTITY_TYPE>` is not re-detected, PRD 6.4). Add a test for that too.
- Pass `params=` to `call_openrouter` **only when not `None`**, with a comment explaining why (the injected-stub contract, STORY-005 notes).
- All seven existing `log_query` arms keep passing `session_id` and `dedup_key` as required keywords (`_deny`'s pattern, PRD-009 Risk 6).
- `InvalidConversationError` is a programming error, unreachable from any ingress in this PRD. Neither the router nor ChatState catches it (PRD 9.2 invariants).
- `QueryPipelineResult` is unchanged here. STORY-008 adds the context-limit member.
- Full multi-turn invariant coverage (order spies, "yes" criteria, raw hashing over prefixes) is STORY-009. Keep this story's tests to the ACs above.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-001, STORY-004, STORY-005
- **Blocks**: STORY-008, STORY-009, STORY-012

## PRD Reference

Source: [`PRD-010-multi-turn-pipeline/PRD.md`](../../PRDs/PRD-010-multi-turn-pipeline/PRD.md) — sections 2, 4 (Pipeline), 6.1, 6.4 (D5), 6.6 (D6), 6.7 (D7), 7 (F5), 9.2, 10, 15
