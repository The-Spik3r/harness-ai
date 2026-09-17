---
story: STORY-003
prd: PRD-010
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-003-openrouter-payload-characterization.plan.md
epic_branch: epic/PRD-010-multi-turn-pipeline
commit: 1459475
status: COMPLETE
completed: 2026-09-17
---

# Implementation Report — STORY-003: Characterize today's OpenRouter request payload and /query upstream body

**Plan**: `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-003-openrouter-payload-characterization.plan.md`
**Epic Branch**: `epic/PRD-010-multi-turn-pipeline`
**Commit**: `1459475`

## Summary

Added four `test_characterization_*` tests on untouched production code, pinning today's OpenRouter request behavior before STORY-004 changes `call_openrouter` to take a list of `Message`s. Three tests extend `tests/test_openrouter_client.py`: exact payload shape and key order (via `json.dumps(..., sort_keys=False)`), headers + URL, and the default `httpx.Client`'s hard-coded `timeout=30.0`. A fourth, pipeline-level test in `tests/test_query_outcomes_regression.py` asserts `POST /query` passes `call_openrouter` the prompt unchanged, the requested model, and `api_key=None`. No production file was modified.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Payload shape / key-order characterization | `tests/test_openrouter_client.py` | ✅ |
| 2 | Headers and URL characterization | `tests/test_openrouter_client.py` | ✅ |
| 3 | Default client's `timeout=30.0` characterization | `tests/test_openrouter_client.py` | ✅ |
| 4 | Pipeline-level `/query` upstream-call characterization | `tests/test_query_outcomes_regression.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `tests/test_openrouter_client.py` | ✅ 12 passed |
| `tests/test_query_outcomes_regression.py` | ✅ 8 passed (rows 1–6 unchanged + new characterization test) |
| `tests/test_pii_redaction_integration.py` (epic guard invariants) | ✅ 18 passed |
| Full suite | ✅ 2034 passed, 25 skipped, 0 failed |
| No production file modified | ✅ (`git diff --stat` against the prior commit touches only `tests/` and `.agents/`) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_openrouter_client.py` | UPDATE | +55 |
| `tests/test_query_outcomes_regression.py` | UPDATE | +29 |
| `tests/test_pii_redaction_integration.py` | UPDATE | +8/-1 |

## Deviations from Plan

**One deviation, not anticipated by the plan.** `tests/test_pii_redaction_integration.py` carries a cross-epic guard, `_PRE_EPIC_UNTOUCHED_TESTS`, that pins `tests/test_openrouter_client.py` as byte-unmodified for "this epic" — a check computed generically against `git merge-base(main, HEAD)`, so it silently applies to whichever epic is currently running, not just the one that wrote it. It failed as soon as `tests/test_openrouter_client.py` gained the three new characterization tests.

This is the same situation the file already documents for PRD-005 STORY-013, which had to open an equivalent exception for `tests/test_integration.py` when RBAC made a breaking, PRD-documented change to that file. Here, PRD-010 Section 6.8 explicitly lists `tests/test_openrouter_client.py` as "extended", and this story's own Technical Notes require editing it — so the guard was stale, not the story wrong.

**Resolution**: removed `tests/test_openrouter_client.py` from `_PRE_EPIC_UNTOUCHED_TESTS`, with a comment citing PRD-010 STORY-003/004/005 and explaining the file now relies on layer 2's protection instead (`test_no_pre_epic_test_function_was_removed_or_renamed`, which still fails on any deletion or rename of an existing test function, just not on a pure addition). Verified: all 18 tests in `tests/test_pii_redaction_integration.py` pass, including both guard layers.

**Environment note (not a plan deviation, but worth recording):** the project's `.venv` was empty at the start of this story, and the machine's only Python (3.14) cannot install the pinned `libsql==0.1.11` (wheels exist only for CPython 3.9–3.13 on Windows per the README; source build failed at the MSVC linker step). Installed Python 3.12 via winget, rebuilt `.venv` against it, installed `requirements.txt` and the `en_core_web_lg` spaCy model, and started the local libSQL dev container (`docker run ... harness-libsql-dev`) per `tests/conftest.py`'s documented command. The full suite then ran clean.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_openrouter_client.py` | `test_characterization_payload_shape_is_byte_identical`, `test_characterization_headers_and_url`, `test_characterization_default_client_uses_todays_timeout` |
| `tests/test_query_outcomes_regression.py` | `test_characterization_query_upstream_receives_prompt_model_and_no_api_key` |

## Acceptance Criteria

- [x] Given `call_openrouter("hello", model="gpt-4", api_key="k", client=fake)` on untouched production code, a test asserts `json == {"model": "gpt-4", "messages": [{"role": "user", "content": "hello"}]}` exactly (key set, key order, no extra keys), via `json.dumps(..., sort_keys=False)`.
- [x] The same call's headers assert `{"Authorization": "Bearer k", "Content-Type": "application/json"}` and the URL `https://openrouter.ai/api/v1/chat/completions`.
- [x] With no `client` argument, a test patching `httpx.Client` asserts it was built with `timeout=30.0`.
- [x] `POST /query` with a PII-free prompt through `TestClient`: the injected upstream received the prompt unchanged, the requested model, and `api_key=None`.
- [x] Full suite green (2034 passed, 25 skipped); no production file modified.
