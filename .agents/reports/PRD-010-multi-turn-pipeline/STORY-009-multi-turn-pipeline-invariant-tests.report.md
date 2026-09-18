---
story: STORY-009
prd: PRD-010
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-009-multi-turn-pipeline-invariant-tests.plan.md
epic_branch: epic/PRD-010-multi-turn-pipeline
commit: PENDING
status: COMPLETE
completed: 2026-09-18
---

# Implementation Report — STORY-009: Multi-turn pipeline invariants

**Plan**: `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-009-multi-turn-pipeline-invariant-tests.plan.md`
**Epic Branch**: `epic/PRD-010-multi-turn-pipeline`
**Commit**: `PENDING`

## Summary

One new test module, `tests/test_query_pipeline_multiturn.py` (853 lines, 25 tests),
asserts PRD-010 Section 9.2's invariants on multi-turn input through `run_conversation`:
the full check order in one spy trace, raw-only hashing across both halves of
`dedup_key`, redaction of every turn before anything leaves the process, PRD-009's
duplicate scope over conversation prefixes, the provisional D6 inspection policy pinned
as intended, the no-new-ingress schema test, and a per-outcome audit-row census.

**No production line changed.** Every invariant held on the code as STORY-007 and
STORY-008 left it, so the contingency in the plan — fix first in a separate commit
referencing the story that introduced the defect — was not needed.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Module skeleton, prologue, shared helpers, three-exchange fixture | `tests/test_query_pipeline_multiturn.py` | ✅ |
| 2 | AC1 — check order in one spy trace (exact + first-occurrence) | same | ✅ |
| 3 | AC2 — raw hashing (last turn *and* prefix); no raw PII upstream | same | ✅ |
| 4 | AC3 — duplicate scope follows the prefix | same | ✅ |
| 5 | AC4 — provisional D6 policy pinned, with a control | same | ✅ |
| 6 | AC5a — no route accepts `messages`/`params`/`system` | same | ✅ |
| 7 | AC5b — one audit row per outcome; zero for `InvalidConversationError` | same | ✅ |
| 8 | Neighbours, full suite, negative controls | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A — no frontend in this repo (`chat_ui` is Reflex/Python); story touches no UI |
| New module | ✅ 25 passed |
| Overlapping neighbours (5 files) | ✅ 77 passed |
| Full suite | ✅ 2129 passed, 25 skipped (159s) |
| E2E | ✅ 5/5 |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_query_pipeline_multiturn.py` | CREATE | +853 |

No production file and no pre-existing test was modified.

## Deviations from Plan

1. **`body_field.type_` does not exist on FastAPI 0.141.1.** The plan (and the story's
   Technical Notes) assumed the pydantic-v1-shim accessor. On the pinned version the body
   model is at `body_field.field_info.annotation`, and `type_` is absent — a walk reading
   only `type_` returns `None` for every route and the schema test passes vacuously.
   `_body_model()` now reads `type_` first and falls back to `field_info.annotation`, with
   the reason in its docstring, so a future version bump in either direction keeps working.
   `test_the_walk_finds_the_known_request_body` is what makes this detectable at all.
2. **Task 7's census is seven separate tests, not one parametrization.** The plan allowed
   a parametrized form "where the arms differ only in setup and expected row fields"; in
   practice each arm differs in *both* (call shape too — two arms raise, one is
   parametrized over three malformed conversations), and a parametrization carrying that
   much per-case branching reads worse than seven short tests. The `_run()` helper absorbs
   the shared setup instead.
3. **Two tests added beyond the plan**, both closing holes the plan's own reasoning
   implied: `test_the_same_yes_from_two_users_is_not_a_duplicate` (the key carries
   `user_id`, so windows never cross) and
   `test_inspection_target_still_carries_its_provisional_marker` (the marker is how
   PRD-011's implementer finds the one function to replace — PRD User Story 8).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_query_pipeline_multiturn.py` | **Order (2)**: `test_check_order_on_a_three_exchange_conversation`, `test_check_order_first_occurrences_match_the_prd_invariant` |
| | **Raw hashing / redaction (4)**: `test_hash_prompt_only_ever_receives_raw_text_multi_turn`, `test_prefix_hashing_receives_raw_turns_only`, `test_no_upstream_message_contains_raw_pii_from_any_turn`, `test_the_key_on_the_row_is_the_key_over_the_raw_conversation` |
| | **Duplicate scope (4)**: `test_yes_after_two_different_exchanges_is_not_a_duplicate`, `test_the_same_single_turn_yes_twice_is_held`, `test_the_same_three_turn_conversation_twice_is_held`, `test_the_same_yes_from_two_users_is_not_a_duplicate` |
| | **Provisional policy (3)**: `test_provisional_policy_inspects_last_user_turn_only`, `test_the_same_injection_as_the_last_turn_is_blocked`, `test_inspection_target_still_carries_its_provisional_marker` |
| | **No new ingress (2)**: `test_the_walk_finds_the_known_request_body`, `test_no_route_accepts_messages_params_or_system` |
| | **Audit census (10)**: success, duplicate, suspicious, forbidden, context-limit, upstream-error, internal-error arms — one row each; `test_invalid_conversation_writes_no_audit_row[empty\|final-assistant-turn\|tool-turn]` — zero rows |

## End-to-End Verification

| # | Check | Result |
|---|-------|--------|
| 1 | `pytest tests/test_query_pipeline_multiturn.py -q` | ✅ 25 passed |
| 2 | `pytest -q` (full suite) | ✅ 2129 passed, 25 skipped |
| 3 | `git status --short` — one new file, no production/test file modified | ✅ |
| 4 | **Negative control**: swapped Steps 3 and 4 in `query_pipeline.py` (duplicate before context limit) | ✅ both order tests failed, naming the swap: `first occur at [0, 3, 2, 4, 5, 10]`. Reverted with `git checkout`. |
| 5 | **Negative control**: added `messages: Optional[list] = None` to `QueryRequest` | ✅ schema test failed loudly: `a route now accepts caller-supplied conversation input: [('/query', 'messages')]`. Reverted with `git checkout`. |

Controls 4 and 5 are the ones that matter: they show the two tests most at risk of
passing vacuously are in fact load-bearing. Both reverts were verified by re-running the
module (25 passed) and `git status`.

## Acceptance Criteria

- [x] Three-exchange conversation with spies on `authorize`, the limit check, `check_duplicate`, `detect_suspicious_pattern`, `redact` and `call_openrouter` records authorization → context limit → duplicate → patterns → redaction → upstream
- [x] PII in turn 1: every hashed string is raw, no placeholder is ever hashed, no upstream message carries the raw PII — and the prefix half is covered through `_sha256_json`, which `hash_prompt` alone cannot see
- [x] `"yes"` after two different exchanges is not held; the same single-turn `[user("yes")]` twice within 24 h **is** held (PRD 11, Appendix *Refinement of the brief's criterion*)
- [x] `test_provisional_policy_inspects_last_user_turn_only` — injection in an earlier turn is not blocked, docstring cites D6/T2 and PRD-011, and the spy proves the earlier turn never reached the detector
- [x] No route body schema has a `messages`, `params` or `system` field; every outcome arm writes exactly one audit row, `InvalidConversationError` writes zero
- [x] All tasks completed
- [x] Full suite green
- [x] No production file changed; no pre-existing test modified
- [x] Follows existing patterns (spy shape, audit helpers, module prologue, `_IncludedRouter` descent)

## Notes for Later Stories

- **PRD-011** must rewrite `test_provisional_policy_inspects_last_user_turn_only` to
  assert the injection *is* caught, not delete it; the module docstring and the test's own
  docstring both say so.
- **PRD-014**, the first ingress to accept caller-supplied history, must update
  `test_no_route_accepts_messages_params_or_system` together with PRD Section 9.2 T2. The
  assertion message says this at the point of failure.
- **STORY-016** (the seven-outcome regression) is unblocked by this story.
