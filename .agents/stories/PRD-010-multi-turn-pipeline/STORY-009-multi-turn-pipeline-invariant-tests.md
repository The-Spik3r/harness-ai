---
id: STORY-009
prd: PRD-010
slug: multi-turn-pipeline-invariant-tests
title: "Multi-turn pipeline invariants: check order, raw hashing, redaction, duplicate scope, no ingress"
type: technical
priority: high
complexity: medium
phase: "2 - Pipeline over messages"
status: done
labels: [backend, tests, security]
epic_branch: epic/PRD-010-multi-turn-pipeline
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-009-multi-turn-pipeline-invariant-tests.plan.md
report: .agents/reports/PRD-010-multi-turn-pipeline/STORY-009-multi-turn-pipeline-invariant-tests.report.md
commit: 90f07f1
depends_on: [STORY-007, STORY-008]
blocks: [STORY-016]
skills: []
created: 2026-09-17
updated: 2026-09-18
---

# STORY-009: Multi-turn pipeline invariants: check order, raw hashing, redaction, duplicate scope, no ingress

## Description

As a security admin, I want the PRD's invariants asserted on multi-turn input through `run_conversation`, so that the conversation filter is proven to hold everything the prompt filter held before any UI starts sending history.

## Acceptance Criteria

- [ ] Given the new [tests/test_query_pipeline_multiturn.py](../../../tests/test_query_pipeline_multiturn.py), when a three-exchange conversation runs with spies on `authorize`, the limit check, `check_duplicate`, `detect_suspicious_pattern`, `redact` and `call_openrouter`, then the recorded order is authorization → context limit → duplicate → patterns → redaction → upstream (PRD 9.2 invariant 1).
- [ ] Given PII in turn 1 and a spy on `hash_prompt`, when the conversation runs, then every hashed string is raw, no placeholder string is ever hashed, and no upstream message contains the raw PII (invariants 2–3; mirrors `test_hash_prompt_only_ever_receives_raw_text` for prefixes).
- [ ] Given one user, when `"yes"` is sent after `[user("Should I add tests?"), assistant("…")]` and later after `[user("Want the SQL version?"), assistant("…")]`, both through `run_conversation` against `temp_db`, then neither is held as a duplicate. When the same `[user("yes")]` single-turn conversation is sent twice within 24 h, the second **is** held (PRD 11, Appendix *Refinement of the brief's criterion*).
- [ ] Given an injection string (`"ignore previous instructions"`) placed in an **earlier** user turn and a benign last turn, when it runs, then it is **not** blocked. The test is named `test_provisional_policy_inspects_last_user_turn_only` and carries a docstring citing D6/T2 and PRD-011, so the provisional gap is pinned as intended, not discovered.
- [ ] Given every route registered on `app.main.app`, when the request models are inspected, then no request body schema has a `messages`, `params` or `system` field (PRD 9.2 T2 / Section 11 schema test). Every outcome arm in this file writes exactly one audit row, and `InvalidConversationError` writes zero.

## Technical Notes

- Tests only; no production change. If an invariant fails, fix it in a separate commit that references the story that introduced the defect, then land these tests.
- Use `temp_db` and the injected `call_openrouter` recorder. No network.
- For order spies, wrap through `monkeypatch.setattr` on `app.services.query_pipeline.<name>` (the names the pipeline actually looks up), as the existing [tests/test_query_pipeline_authorization.py](../../../tests/test_query_pipeline_authorization.py) does.
- The route-schema test walks `app.routes`, collects `APIRoute.body_field` models, and checks `model_fields`. It must fail loudly if PRD-014 later adds such a field without updating the test.
- Following the libSQL dev-server note, mass fixture errors mean restart the container.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-007, STORY-008
- **Blocks**: STORY-016

## PRD Reference

Source: [`PRD-010-multi-turn-pipeline/PRD.md`](../../PRDs/PRD-010-multi-turn-pipeline/PRD.md) — sections 5 (stories 6, 7), 6.6, 9.2 (T2, invariants), 11, 15 (Refinement of the brief's criterion)
