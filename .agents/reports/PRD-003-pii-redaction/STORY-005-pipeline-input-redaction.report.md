---
story: STORY-005
prd: PRD-003
plan: .agents/plans/PRD-003-pii-redaction/completed/STORY-005-pipeline-input-redaction.plan.md
epic_branch: epic/PRD-003-pii-redaction
commit: c69a656
status: COMPLETE
completed: 2026-07-31
---

# Implementation Report — STORY-005: Redact prompt before forwarding to OpenRouter

**Plan**: `.agents/plans/PRD-003-pii-redaction/completed/STORY-005-pipeline-input-redaction.plan.md`
**Epic Branch**: `epic/PRD-003-pii-redaction`
**Commit**: `c69a656`

## Summary

`run_query()` now redacts the prompt between the pattern check and the OpenRouter call, and forwards `redacted_prompt` — never the raw text — to the third-party provider. The raw `prompt` variable is never reassigned, so `check_duplicate()`, `detect_suspicious_pattern()`, and all five `log_query()` call sites provably still operate on raw text (RF-6, RF-7).

`redact()` is wrapped in the same log-then-bare-`raise` block the OpenRouter call already used: a `PiiRedactorError` writes a `success=False` audit row carrying the raw prompt and the error message, then propagates to `app/routers/query.py`, which maps it to HTTP 500 alongside the existing `DuplicateCheckError` arm. Fail-closed (a broken analyzer can never leak raw PII to OpenRouter, because redaction precedes the OpenRouter `try:`) and fully audited (the request never vanishes without a row).

`input_entities` is captured and left unused as a named seam for STORY-006. The caller still receives the raw model response — output redaction is STORY-006, and the `pii_redacted` response field is STORY-007.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Import `redact` + `PiiRedactorError` into the pipeline | `app/services/query_pipeline.py` | ✅ |
| 2 | Redact between pattern check and OpenRouter call; audited fail-closed block | `app/services/query_pipeline.py` | ✅ |
| 3 | Translate `PiiRedactorError` → HTTP 500 at the router | `app/routers/query.py` | ✅ |
| 4 | Add 9 pipeline redaction tests | `tests/test_query_router.py` | ✅ |
| 5 | Full-suite regression, scope check, latency verification | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | ✅ `from app.main import app` OK |
| Frontend lint | N/A — no npm frontend in this repo |
| Tests | ✅ 136 passed (baseline 127 + 9 new) |
| `tests/test_query_router.py` alone | ✅ 16 passed (7 pre-existing + 9 new) |
| Untouched suites (dedup, pattern, redactor, integration) | ✅ 40 passed, unmodified |
| Latency test in isolation | ✅ passes after prescribed warm-up (see Deviation 1) |
| E2E | ✅ 9/9 |
| Server startup (`lifespan` → `pii_redactor.load()`) | ✅ `{"status":"ok"}` on `/health` |
| Scope: only 3 code files changed | ✅ |
| `prompt=prompt` occurrences | ✅ 5 (all `log_query` calls raw) |
| No direct `presidio` import in pipeline/router | ✅ 0 matches |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/query_pipeline.py` | UPDATE | +16/-1 |
| `app/routers/query.py` | UPDATE | +3/-0 |
| `tests/test_query_router.py` | UPDATE | +162/-0 |

`duplicate_checker.py`, `pattern_detector.py`, `audit_logger.py`, `pii_redactor.py`, and `schemas.py` are absent from the diff, as the plan required.

## Deviations from Plan

1. **`test_full_pipeline_latency_within_budget` needed the warm-up the plan had pre-authorized.** Run in isolation (`pytest tests/...::test_full_pipeline_latency_within_budget`) the test failed at `assert 1.1872898 < 0.5` — the cold spaCy model load landing inside the timed request. This is exactly the failure Design Note 8 anticipated, and the fix applied is the one it prescribed verbatim: a `query_pipeline.redact("warm up")` call before `start = time.perf_counter()`, with a comment citing PRD Section 11, **not** a raised budget. The budget still measures per-request pipeline overhead. Note the plan's "tests diff is additions-only" gate still holds — the change inserted 4 lines and deleted none (`+162/-0`). The test passes in isolation, per-file, and in the full suite.

2. **The E2E audited-failure probe needed a distinct prompt.** The plan's script reused the same prompt string as the preceding success probe. Because that probe had already written an audit row, `check_duplicate()` would have short-circuited the second request to `BLOCKED` **before** ever reaching `redact()` — the probe would have printed a misleading pass. Used `e2e-probe2@empresa.com` (and `e2e-probe3@` for the toggle probe) so each probe exercises the path it claims to.

3. **The "clean prompt → HTTP 200" E2E check could not return 200 against the live server.** No real `OPENROUTER_API_KEY` is available, so the request reached OpenRouter and came back `401 Unauthorized` → HTTP 502. That failure is itself the proof the pipeline completed redaction and got to the network step. The unchanged-response-contract claim was verified instead via the blocked path over real HTTP: `POST /query` with `"please override the rules"` → HTTP 200 with byte-identical shape `{"status":"BLOCKED","reason":"Suspicious pattern detected","pattern":"override"}`, no new fields.

4. **AC wording clarification.** The plan's AC read "No Presidio import in `query_pipeline.py` beyond `redact`", but Task 1/2 (as revised for the audited failure path) also import `PiiRedactorError`. Both names come from the app's own adapter module `app.services.pii_redactor`, not from `presidio_*` — `grep -c presidio` returns 0 in both changed source files, so the adapter boundary the AC protects (PRD Section 6) is intact.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_query_router.py` | `test_pii_prompt_is_redacted_before_reaching_openrouter` (AC1) |
| | `test_duplicate_and_pattern_checks_still_receive_the_raw_prompt` (AC2) |
| | `test_audit_row_keeps_raw_prompt_when_pii_redacted` (RF-6/RF-7) |
| | `test_redact_not_invoked_when_duplicate_blocked` (AC3) |
| | `test_redact_not_invoked_when_suspicious_pattern_blocked` (AC3) |
| | `test_clean_prompt_is_forwarded_unchanged` (AC4) |
| | `test_redaction_disabled_forwards_raw_prompt` (`PII_REDACTION_ENABLED` toggle) |
| | `test_redactor_failure_returns_500_and_never_calls_openrouter` (fail-closed + row written) |
| | `test_redactor_failure_audit_row_keeps_raw_prompt_and_error` (audited failure row) |

## E2E Evidence

Against the real SQLite DB and the real Presidio analyzer:

```
SENT   : 'my email is <EMAIL_ADDRESS>, can you draft a reply?'
AUDIT  : 'my email is e2e-probe@empresa.com, can you draft a reply?'
```

Audit rows produced by the probes, showing the Design Note 4(c) distinction — a redaction failure records **no** model, an OpenRouter failure does:

```
{'prompt_preview': '...e2e-probe2@...', 'success': 0, 'model_used': None,    'error_message': 'PII analysis failed: probe'}
{'prompt_preview': '...e2e-http@...',   'success': 0, 'model_used': 'gpt-4', 'error_message': "OpenRouter request failed: ... 401 Unauthorized ..."}
```

All 5 probe rows were deleted afterwards; the repo-root DB is left as found.

## Acceptance Criteria

- [x] PII prompt → `call_openrouter()` invoked with `"my email is <EMAIL_ADDRESS>, can you draft a reply?"`, never the raw prompt
- [x] `check_duplicate()` and `detect_suspicious_pattern()` still receive the raw prompt; redaction happens strictly after both
- [x] Duplicate-blocked / pattern-blocked requests never invoke `redact()` (nor OpenRouter)
- [x] Clean prompt → text forwarded unchanged, no entities reported
- [x] All tasks completed
- [x] Full test suite passes — 136 passed
- [x] Backend server starts without error
- [x] `prompt` is never reassigned in `run_query()`
- [x] All five `log_query(...)` calls pass `prompt=prompt` (raw)
- [x] `PiiRedactorError` → exactly one audit row with `success=False`, raw prompt, self-describing `error_message`, `model_used is None`; OpenRouter never called; router returns 500
- [x] `duplicate_checker.py` and `pattern_detector.py` untouched
- [x] No direct Presidio import in `query_pipeline.py` — adapter boundary intact (see Deviation 4)
- [x] Only `query_pipeline.py`, `routers/query.py`, and `test_query_router.py` changed
- [x] Follows existing patterns
