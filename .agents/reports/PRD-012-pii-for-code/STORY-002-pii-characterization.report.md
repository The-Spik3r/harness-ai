---
story: STORY-002
prd: PRD-012
plan: .agents/plans/PRD-012-pii-for-code/completed/STORY-002-pii-characterization.plan.md
epic_branch: epic/PRD-012-pii-for-code
commit: 5e93b18
status: COMPLETE
completed: 2026-09-24
---

# Implementation Report — STORY-002: Characterize today's redact() and pipeline steps 6 and 8 before anything moves

**Plan**: `.agents/plans/PRD-012-pii-for-code/completed/STORY-002-pii-characterization.plan.md`
**Epic Branch**: `epic/PRD-012-pii-for-code` (base for AC 5: `f98c57b`)
**Commit**: `5e93b18`

## Summary

`tests/test_pii_characterization.py` pins today's `chat` redaction byte for byte, on untouched code:

- **`redact()`**: 12 prompts, each pinned as one `(masked_text, sorted_entities)` tuple. They include no PII, empty, already-masked (`<PERSON>` / `<EMAIL_ADDRESS>`), the PRD Section 1 `author = "Jane Doe"` line, and one prompt with all seven default entity types.
- **`run_conversation` steps 6 and 8**: four chat-shaped conversations, each run under `profile=None` and `profile="chat"`, with a recording `call_openrouter` stub. For each run the module pins:
  - the exact `Message` list sent upstream, and that there is exactly one call;
  - the whole `QuerySuccessResponse`, minus `audit_id`;
  - the audit row's `pii_detected_input`, `pii_detected_output`, `pii_entities` and `response_preview`;
  - that `response_hash` is the hash of the unmasked response.

  The four conversations are PII in the last turn, PII in history only (PRD-010 D7), PII in the response only, and a different type in each of the three places.
- **Five guards** restate AC 1, 3 and 4 against the case tables, so an edit that drops coverage fails.

An autouse fixture pins the four shipped `PII_*` settings. It replaces any cached analyzer that is not built on `en_core_web_lg`, then asserts that the large model is in use.

No file under `app/`, `chat_ui/` or `requirements.txt` changed: `git diff --name-only f98c57b -- app/ chat_ui/ requirements.txt` is empty.

## Tasks Completed

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 0 | Preflight: started Docker Desktop and `harness-libsql-dev`, recorded BASE `f98c57b`, committed the plan (`72dfee9`), and took a baseline of 2635 passed, 26 skipped, 2 failed. The two failures were flakes: both passed in isolation and in every later full run (see *Validation*) | — | ✅ |
| 1 | Module skeleton, settings/model fixture, 12 `redact()` pins, 2 guards | `tests/test_pii_characterization.py` | ✅ |
| 2 | 4 conversation cases × 2 profiles, 3 guards | `tests/test_pii_characterization.py` | ✅ (one deviation, below) |
| 3 | Seven bite checks, the fixture-defence check, full suite, AC 5 diff | — | ✅ |
| 4 | This report | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Frontend lint | N/A. No frontend in the change; the UI is Reflex/Python |
| `/health` smoke (uvicorn on :8765) | ✅ `{"status":"ok"}` [200] |
| `pytest tests/test_pii_characterization.py` | ✅ 25 passed |
| Neighbours (`test_pii_redactor`, `test_pii_redaction_integration`, `test_query_pipeline_run_conversation`, `test_query_pipeline_multiturn`, this module) | ✅ 93 passed |
| Order: redactor → characterization, characterization → redactor, `test_main` → characterization | ✅ 33 / 33 / 39 passed |
| Full suite | ✅ 2661 passed, 26 skipped, **0 failed**, 1 error (see note) |
| AC 5: `git diff --name-only f98c57b -- app/ chat_ui/ requirements.txt` | ✅ empty |

**About the full-suite error.** Each of two full runs, one of them after restarting the container, raised exactly one `Hrana … tcp connect error (os error 10060)` against the libSQL container, in a **different, unrelated** test each time: `test_query_pipeline_dedup_key.py::…[openrouter-failure]`, then `test_integration.py::test_query_results_are_consistent_across_audit_and_stats`. Both pass in isolation (10 passed). The two baseline failures (`test_pipeline_concurrency.py::test_health_and_query_answer_while_ten_chat_sends_are_blocked`, `test_query_pipeline_run_conversation.py::test_params_are_forwarded_when_set`) happened before this module existed, and passed in both later runs. This is the local Docker/libSQL flakiness PRD Section 11 warns about ("restart the libSQL dev container, not bisect code"). None of these involve this module.

## Measured with

presidio-analyzer 2.2.364, presidio-anonymizer 2.2.364, spaCy 3.8.16, `en_core_web_lg` 3.8.0, phonenumbers 9.0.38, on `epic/PRD-012-pii-for-code` @ `f98c57b`. **For STORY-003:** these are the versions to pin in `requirements.txt`. If a later version bump changes a pin here, the bump is the cause, and the pin must not be edited to "fix" it.

## Bite checks (Task 3)

Each was a temporary edit, reverted with `git checkout -- app/` or the test-file backup. `git status` afterwards showed only the new module.

| # | Temporary change | Result |
|---|---|---|
| 1a | `PII_SCORE_THRESHOLD` default 0.35 → 0.5 in `app/config.py` | 25 passed: the fixture isolates the module from settings drift |
| 1b | Fixture's threshold 0.35 → 0.5 | 3 failed: `person-phone`, and `pii-in-history-only` under both profiles (the bare phone scores 0.40) |
| 2 | `redact()` returns `list(set)` instead of `sorted(set)` | 2 failed: `person-phone`, `every-default-entity` (the other multi-entity cases happen to come out in sorted order) |
| 3 | Step 6 redacts only the last message | 4 failed: history-only and history+last+response, both profiles |
| 4 | Step 8 returns the unredacted response | 4 failed: response-only and history+last+response, both profiles |
| 5 | Step 8 audits `redacted_response` instead of the raw one | 4 failed: same two cases, on `response_preview` / `response_hash` |
| 6 | Step 6 records every message's entities, not only the last | 4 failed: history-only and history+last+response, both profiles (D7) |
| 7 | Anonymizer `DEFAULT` operator → `replace` with `<PII>` | 17 failed: every case that masks anything |
| F-1 | A stale `en_core_web_sm` analyzer injected at import | Reset branch on: 25 passed. Reset branch disabled: all 25 fail with `assert 'core_web_sm' == 'core_web_lg'` |

The first F-1 attempt, a leak through `test_pii_redactor.py`'s fixture, proved nothing: that file's last test leaves no analyzer built. The direct injection replaced it.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_pii_characterization.py` | CREATE | +369 |
| `.agents/plans/PRD-012-pii-for-code/completed/STORY-002-pii-characterization.plan.md` | MOVE (archived) | 0 |
| `.agents/reports/PRD-012-pii-for-code/STORY-002-pii-characterization.report.md` | CREATE | this file |

## Deviations from Plan

1. **The audit row has no `response` column.** The plan (F-3, Task 2) pinned `row.response`. `AuditLog` stores `response_preview` (the first 500 characters) and `response_hash` (`app/services/audit_logger.py:42-43`, `app/db/models.py:230-231`). The module pins `response_preview` exactly, and pins `response_hash == hash_prompt(upstream_response)`. Every response is under 500 characters, so the preview is the whole response. **F-3's finding still holds in this form:** the audit keeps the preview and hash of the **unmasked** response. The in-memory probe behind the plan had captured the `response=` keyword passed to `log_query`, not the stored columns. That is how the plan missed this. Every other measured value matched the real DB unchanged.
2. **One bite check added.** The F-1 fixture-defence check, because monkeypatch restoration meant the plan's order checks never exercised the reset branch.
3. **Docker Desktop** was started from `%LOCALAPPDATA%\Programs\DockerDesktop` (user install), not `C:\Program Files\Docker`.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_pii_characterization.py` | `test_redact_output_is_pinned` × 12 (`no-pii`, `empty`, `already-masked`, `person-email`, `person-phone`, `card`, `ssn`, `iban`, `apostrophe-name-location`, `non-ascii-names`, `code-string-literal`, `every-default-entity`); `test_the_every_entity_case_covers_every_default_entity`; `test_the_redact_cases_include_the_required_shapes`; `test_chat_conversation_is_pinned` × 8 (4 cases × `default`/`chat`); `test_the_conversation_cases_are_chat_shaped`; `test_the_history_only_case_masks_history_and_records_nothing`; `test_the_response_case_masks_the_response` |

## For later stories

- **STORY-009**:
  - Import `CONVERSATION_CASES` for the `chat` assertions. Do not copy them.
  - The pipeline cases already run under `profile=None` and `profile="chat"`. Once `get_pii_policy("chat")` resolves in step 6, both parametrizations must pass unchanged.
- **STORY-014**:
  - Diff this whole module against its commit. No assertion may change (PRD Section 11).
  - `REDACT_CASES` is also importable.

## Observations (recorded, not fixed)

- **The audit keeps the unmasked model response.** `response_preview` holds up to 500 characters of it, and `response_hash` is its hash (`query_pipeline.py:390` passes `openrouter_result.response`). A Security/Compliance Admin reading the Register sees output PII that the chat user never saw. No PRD-012 story owns this, so it needs a decision in a future PRD. PRD-012 must not change it silently, and this module makes sure it can't.
- **The NER span can swallow a leading capitalised verb.** `Call Aisha Bello` becomes `<PERSON>`, so the user reads "Sent. <PERSON> on phone …".
- **`tests/test_pii_redactor.py` runs on `en_core_web_sm`,** contrary to the story's Technical Notes. The large-model precedent is `tests/test_pii_redaction_integration.py`.
- **A bare `555-01xx` phone with `call` scores 0.40.** Bite 1b confirms it: masked under `chat` (0.35), missed at the provisional `code` threshold (0.5). This agrees with STORY-001 F-2.

## Acceptance Criteria

- [x] Given `tests/test_pii_characterization.py` on untouched code, when it runs, then it is green and pins the exact output of `redact()` (masked text and sorted entity list) for a fixed set of at least ten prompts, including one with no PII, one with an already-masked `<PERSON>`, and one with every default entity type.
- [x] Given a chat-shaped conversation (no system turn, user/assistant history plus a new user turn), when `run_conversation` runs with a recording `call_openrouter` stub, then the test pins the exact `Message` list the stub receives, the exact response returned, and the audit row's `pii_detected_input`, `pii_detected_output` and `pii_entities`.
- [x] Given the same conversation with PII only in a history turn, when it runs, then the test pins that the history turn is masked upstream and that its entities are **not** recorded in the audit fields (PRD-010 D7).
- [x] Given the response contains PII, when it runs, then the test pins that the returned response is masked and `pii_detected_output` is true.
- [x] Given this story's commit, when it is diffed, then no file under `app/` changes.
- [x] All tasks completed
- [x] Full suite green (0 failures; one environmental libSQL connect timeout, different test each run, passes in isolation)
- [x] Follows existing patterns
