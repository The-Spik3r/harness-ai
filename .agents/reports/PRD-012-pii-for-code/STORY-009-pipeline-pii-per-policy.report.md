---
story: STORY-009
prd: PRD-012
plan: .agents/plans/PRD-012-pii-for-code/completed/STORY-009-pipeline-pii-per-policy.plan.md
epic_branch: epic/PRD-012-pii-for-code
commit: pending
status: COMPLETE
completed: 2026-09-25
---

# Implementation Report — STORY-009: Pipeline steps 6 and 8 redact per the resolved policy

**Plan**: `.agents/plans/PRD-012-pii-for-code/completed/STORY-009-pipeline-pii-per-policy.plan.md`
**Epic Branch**: `epic/PRD-012-pii-for-code`
**Commit**: `pending`

## Summary

`run_conversation` now resolves the PII policy once per request, with `get_pii_policy(profile_name)` at the head of step 6. It uses the name step 5 already computes from `profile` / `PATTERN_PROFILE_DEFAULT`.

**Step 6**
- A message whose role is not in `policy.input_roles` is appended as the same `Message` object, so it reaches upstream byte-identical. This is `code`'s `system` turn.
- Every other message goes through a new private helper, `_redact(text, policy)`.
- `_redact` calls `redact()` by `query_pipeline`'s own name for a policy without `structure_safe` (`chat`), and `redact_for_policy()` otherwise.

**Step 8**
- Runs only when `policy.output` is on.
- When it is off (the `code` default), the response is returned unchanged and `output_entities = []`, so the row records `pii_detected_output=0`.

**Unchanged**
- PRD-010 D7: only the last user turn's entities, plus the output's, are recorded.
- The two redaction-error arms.
- `_validate_conversation`.
- Every `log_query` call.

`/query` and the chat UI produce the same bytes as before. The characterization, integration and both outcome-regression suites pass with no assertion changed.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Imports; the `_redact(text, policy)` helper | `app/services/query_pipeline.py` | ✅ |
| 2 | Step 6: policy resolved once, role gate, same-object pass-through | `app/services/query_pipeline.py` | ✅ |
| 3 | Step 8 gated on `policy.output` | `app/services/query_pipeline.py` | ✅ |
| 4 | Test module scaffold: fixtures, stub upstream, audit readers | `tests/test_query_pipeline_pii_profiles.py` | ✅ |
| 5 | Tests grouped by AC | `tests/test_query_pipeline_pii_profiles.py` | ✅ |
| 6 | Regression sweep | — | ✅ (after the deviation below) |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A. The repository has no `frontend/`. |
| New tests | ✅ 20 passed |
| New tests against the **pre-change** pipeline | 13 failed, 7 passed. The 7 are the behaviours meant to stay the same: `chat` D7, the `chat` error arm, and `code` with output or system redaction on. |
| Protected and F-1 suites (10 files) | ✅ 177 passed |
| Full suite | ✅ 3072 passed, 26 skipped. The baseline before any change was 3052 passed, 26 skipped. |
| `GET /health` on a live `uvicorn app.main:app` | ✅ `{"status":"ok"}` |
| E2E | ✅ 4/4 (see below) |

### E2E

| Check | How | Result |
|-------|-----|--------|
| `/query` path masks prompt and response; the row has input and output PII | `test_pii_redaction_integration.py` (TestClient, unchanged), plus `run_query` against the local libSQL dev server with a stub upstream | ✅ |
| Chat UI send path unchanged | `test_chat_outcomes_regression.py`, unchanged | ✅ |
| `run_conversation(profile="code")`: `system` is the same object, the user email is masked, the response is unmasked, `pii_detected_output=0` | Direct call against the local libSQL dev server with a stub upstream | ✅ |
| Full suite green | `pytest tests/ -q` | ✅ |

The live server needed `RBAC_ENABLED=false`, because the empty dev database has no users and the bootstrap guard refuses to start. That guard is unrelated to this story. No request was sent to OpenRouter: the live model is replaced by a stub everywhere, as the story's Technical Notes require.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/query_pipeline.py` | UPDATE | +73/-26 |
| `tests/test_query_pipeline_pii_profiles.py` | CREATE | +436 |
| `tests/test_query_pipeline_patterns.py` | UPDATE | +11/-0 |

## Deviations from Plan

1. **`tests/test_query_pipeline_patterns.py` was modified.** The plan expected `git diff --stat tests/` to list only the new file.
   - `test_flag_arm_runs_before_redaction_and_upstream` runs under `profile="code"` and records redaction by spying on `query_pipeline.redact` alone. Under `code`, step 6 now calls `redact_for_policy`, so the trace had no `"redact"` entry.
   - The shared helper `_install_spies` now also spies on `redact_for_policy`, under the same `"redact"` label. The change carries a comment citing PRD-012 STORY-009 (F8).
   - No assertion changed. Under `chat`, `redact_for_policy` is never called, so no other test's trace changes.
   - The file is not one of the four protected files (PRD Section 11).
   - Plan F-1 listed this file for its `chat` spies and missed that one of its tests runs under `code`.
2. **`PII_SCORE_THRESHOLD_CODE` is 0.40, not 0.5.** STORY-003 fixed it at 0.40. The PRD's 0.5 was provisional. The tests pin the shipped 0.40.
3. **The planned "last turn phone" case for AC 4 under `code` became an email plus a history IBAN.** Its purpose is the same: something is masked in history and not recorded, while the last turn and the output are recorded. It avoids depending on whether a 555-01xx phone clears 0.40.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_query_pipeline_pii_profiles.py` | **AC 1:** `test_chat_calls_redact_for_every_message_then_the_response[default, chat]` |
| | **Once-per-request:** `test_policy_is_resolved_once_from_the_step_5_name[default, chat, code]` |
| | **AC 2:** `test_code_passes_system_through_as_the_same_object`, `test_code_sends_user_and_assistant_through_redact_for_policy`, `test_code_redacts_system_when_configured`, `test_code_skips_fenced_blocks_and_masks_the_prose_around_them` |
| | **PRD Section 11:** `test_code_never_reaches_the_full_analyzer` |
| | **AC 3:** `test_code_returns_the_response_unmasked_and_records_no_output_pii`, `test_code_masks_the_response_when_output_redaction_is_on`, `test_code_output_off_still_records_input_pii` |
| | **AC 4:** `test_code_masks_history_pii_without_recording_it`, `test_code_records_last_turn_and_output_entities_only`, `test_chat_records_last_turn_and_output_entities_only[2 cases]` |
| | **AC 5:** `test_redaction_error_on_history_writes_the_error_row_and_never_calls_upstream[code, chat]`, `test_json_post_condition_failure_takes_the_redaction_error_arm` |

## Handoff (for later stories)

- **STORY-010**:
  - The size check goes directly below `policy = get_pii_policy(profile_name)`, where a comment marks the spot, and before the step-6 loop.
  - Count only roles in `policy.input_roles`, using `strip_fenced_blocks` under `skip_fenced_blocks`.
  - A test that spies on redaction under `code` must spy on `query_pipeline.redact_for_policy`, not only `redact`.
- **STORY-011**:
  - Pass `profile=profile_name` on every `log_query` call.
  - Under `code` with output off, `pii_detected_output=0` means "not analyzed".
- **STORY-012 / STORY-013**: `run_conversation(profile="code")` is now the real `code` path. Use an injected upstream stub.

## Acceptance Criteria

- [x] Given `run_conversation` with no `profile` (the `/query` and chat UI path), when it runs, then step 6 calls `redact()` for every message and step 8 redacts the response, and `test_pii_characterization.py`, `test_pii_redaction_integration.py` and `test_query_outcomes_regression.py` pass with no assertion changed.
- [x] Given `profile="code"`, when a conversation has `system`, `user` and `assistant` turns, then the `system` turn reaches `call_openrouter` byte-identical, and `user` and `assistant` turns go through `redact_for_policy` with the `code` policy.
- [x] Given `profile="code"` and a response containing `alice@example.com`, when it runs, then the returned response is unchanged and the audit row has `pii_detected_output=0`; with `PII_CODE_REDACT_OUTPUT=true`, it is masked and `pii_detected_output=1`.
- [x] Given either profile, when history turns carry PII, then only the last user turn's entities (plus output entities, when output is redacted) are recorded in `pii_detected_input` / `pii_entities` (PRD-010 D7 kept).
- [x] Given `redact_for_policy` raises `PiiRedactorError` on any message, when step 6 runs, then the existing redaction-error arm writes its row and re-raises, and `call_openrouter` is never called.
- [x] All tasks completed
- [x] Full test suite passes; no assertion changed in the protected test files
- [x] Follows existing patterns
