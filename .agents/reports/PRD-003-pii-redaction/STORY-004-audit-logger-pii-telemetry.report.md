---
story: STORY-004
prd: PRD-003
plan: .agents/plans/PRD-003-pii-redaction/completed/STORY-004-audit-logger-pii-telemetry.plan.md
epic_branch: epic/PRD-003-pii-redaction
commit: 1347e53
status: COMPLETE
completed: 2026-07-31
---

# Implementation Report — STORY-004: Audit logger records PII telemetry (raw preview unchanged)

**Plan**: `.agents/plans/PRD-003-pii-redaction/completed/STORY-004-audit-logger-pii-telemetry.plan.md`
**Epic Branch**: `epic/PRD-003-pii-redaction`
**Commit**: `1347e53`

## Summary

Extended `log_query()` in `app/services/audit_logger.py` with three optional parameters — `pii_detected_input: bool = False`, `pii_detected_output: bool = False`, `pii_entities: Optional[list[str]] = None` — passed through to the `AuditLog` columns STORY-003 added. The `list[str]` → `"A,B"` join lives here and only here, implemented as an inline conditional (`",".join(pii_entities) if pii_entities else None`) mirroring the file's existing transform-or-`None` style at lines 30-31.

The raw-text derivation is untouched: `prompt_hash`, `prompt_preview`, `response_hash`, and `response_preview` still come from the raw `prompt`/`response` arguments. The diff on `app/services/audit_logger.py` is **6 additions, 0 deletions** — proof at the diff level that the PRD Section 9 / RF-7 "audit log stays raw" guarantee was not disturbed. No Presidio import was added; the function accepts already-computed booleans and entity lists, so the adapter boundary in `pii_redactor.py` stays intact (PRD Section 6).

All three parameters are appended last with defaults, so the four existing call sites in `app/services/query_pipeline.py` (lines 29, 43, 58, 68) and the five pre-existing tests in `tests/test_audit_logger.py` are byte-for-byte unmodified. Nothing passes the new arguments yet — that wiring belongs to STORY-005 (input entities) and STORY-006 (output entities), so every audit row is still written with `False`/`False`/`None` and runtime behavior is unchanged from `main`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Append 3 optional parameters to the `log_query()` signature | `app/services/audit_logger.py` | ✅ |
| 2 | Pass the 3 values into the `AuditLog(...)` construction, joining the entity list | `app/services/audit_logger.py` | ✅ |
| 3 | Add 4 tests: values persisted, defaults when omitted, empty list → `None`, raw previews with PII present | `tests/test_audit_logger.py` | ✅ |
| 4 | Add the order-preservation test pinning Design Note 2 | `tests/test_audit_logger.py` | ✅ |
| 5 | Full-suite regression + changed-file scope gate | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Frontend lint | N/A — no npm frontend in this repo (Reflex/Python project; no `package.json`) |
| Tests | ✅ 127 passed (122 baseline + 5 new) |
| `tests/test_audit_logger.py` | ✅ 10 passed (5 pre-existing unmodified + 5 new) |
| E2E | ✅ 10/10 |
| Changed-file scope | ✅ exactly `app/services/audit_logger.py`, `tests/test_audit_logger.py` |
| Diff shape | ✅ 0 deletions across both files (86 + 6 insertions) |
| `duplicate_checker.py` / `query_pipeline.py` untouched | ✅ (RF-6) |
| No Presidio import in `audit_logger.py` | ✅ adapter boundary intact |

### E2E Checklist

| # | Check | Result |
|---|-------|--------|
| 1 | `pytest tests/test_audit_logger.py -v` | ✅ 10 passed |
| 2 | Existing `log_query()` consumers unmodified (`test_query_router`, `test_integration`, `test_audit_router`, `test_stats_router`, `test_chat_state`) | ✅ 40 passed, zero edits (AC2) |
| 3 | Full suite `pytest` | ✅ 127 passed |
| 4 | `git diff --name-only` scope | ✅ 2 code/test files; `duplicate_checker.py` and `query_pipeline.py` absent |
| 5 | `git diff tests/test_audit_logger.py` additions-only | ✅ 86 insertions, 0 deletions (AC4) |
| 6 | Default path inert against the real DB | ✅ `hello hi False False None` |
| 7 | Raw-preview guarantee with PII present, real DB | ✅ `'my email is juan@empresa.com'` / `'EMAIL_ADDRESS,PERSON' True True` — no `<EMAIL_ADDRESS>` placeholder in the preview (AC1 + AC3) |
| 8 | Stale-DB contingency (Design Note 7) | ✅ not triggered — no `sqlite3.OperationalError`; STORY-003 had already recreated the DB |
| 9 | `from app.main import app` | ✅ imports cleanly |
| 10 | `uvicorn app.main:app` + `curl /health` | ✅ startup complete (Presidio model loaded), `{"status":"ok"}` |
| 11 | `GET /audit` with admin token | ✅ HTTP 200, `{"total":0,"queries":[]}` — response shape unchanged (PII field exposure is STORY-009) |

The two E2E rows written against the real `harness_ai.db` (items 6-7) were deleted afterward; the DB was verified back at 0 rows, as found.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/audit_logger.py` | UPDATE | +6/-0 |
| `tests/test_audit_logger.py` | UPDATE | +86/-0 |

## Deviations from Plan

**None.** Every task, validation command, and E2E check was executed exactly as written, and each produced the outcome the plan predicted — including the specific figures: signature defaults `False False None`, 9 tests after Task 3, 10 after Task 4, 127 in the full suite, and the exact real-DB output strings in E2E items 6 and 7.

Two plan predictions worth recording as confirmed rather than assumed:

1. **The venv-interpreter instruction (Design Note 8) was necessary and sufficient.** Every command ran under `.venv/Scripts/python.exe`, and the 8 collection errors STORY-003 hit with bare `python` did not recur. Carrying that deviation forward into this plan removed it as a live issue.
2. **The stale-`harness_ai.db` risk (Design Note 7) did not materialize.** The plan predicted STORY-003 had already resolved it; the real-DB E2E writes confirmed this by succeeding, which is a stronger check than inspecting the schema.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_audit_logger.py` | `test_pii_telemetry_persisted_when_supplied` (NEW) — AC1: booleans and `["EMAIL_ADDRESS", "PERSON"]` persist as `True`/`True`/`"EMAIL_ADDRESS,PERSON"` |
| `tests/test_audit_logger.py` | `test_pii_telemetry_defaults_when_omitted` (NEW) — AC2: omitting the new args yields `False`/`False`/`None` |
| `tests/test_audit_logger.py` | `test_empty_entity_list_stored_as_none` (NEW) — Design Note 1: `[]` stores as `None`, not `""` |
| `tests/test_audit_logger.py` | `test_previews_and_hashes_stay_raw_when_pii_detected` (NEW) — AC3 guard: previews/hashes match the raw text and contain no `<EMAIL_ADDRESS>` placeholder even when both PII flags are set |
| `tests/test_audit_logger.py` | `test_entity_list_joined_in_caller_order_without_reordering` (NEW) — Design Note 2: a deliberately non-alphabetical list round-trips in caller order, so a later stray `sorted()` fails loudly |

The five pre-existing tests were not modified — only appended to. Booleans are asserted with `is True` / `is False` (identity, not truthiness), which is what proves the `int()`→`bool()` conversion at the DB boundary rather than a raw `1`/`0` leaking through.

## Acceptance Criteria

- [x] Given `log_query()` is called with `pii_detected_input=True`, `pii_detected_output=True`, `pii_entities=["EMAIL_ADDRESS", "PERSON"]`, when the audit row is written, then those values are persisted via the new `AuditLog` columns from STORY-003.
- [x] Given `log_query()` is called without the new PII arguments (existing call sites), when it runs, then it behaves identically to today — defaults to no PII detected, and `prompt_preview`/`response_preview` are computed from the raw text exactly as before.
- [x] Given `log_query(prompt=..., response=...)` is called, when the audit row is written, then `prompt_preview`/`response_preview`/`prompt_hash`/`response_hash` are still derived from the **raw** prompt/response passed in.
- [x] Given the existing `tests/test_audit_logger.py` suite, when run, then all existing tests pass unmodified.
- [x] All tasks completed
- [x] Full test suite passes (127 passed)
- [x] Backend server starts without error
- [x] Lines 28-31 of `app/services/audit_logger.py` (preview/hash derivation) unchanged — verified in the diff (0 deletions)
- [x] No Presidio import in `app/services/audit_logger.py` (adapter boundary intact, PRD Section 6)
- [x] `app/services/duplicate_checker.py` untouched (PRD Section 9, RF-6)
- [x] Only `app/services/audit_logger.py` and `tests/test_audit_logger.py` changed
- [x] Follows existing patterns (optional params appended last with defaults, inline transform-or-`None` conditional in the `AuditLog(...)` constructor, comma-joined entity format matching `app/config.py:22`, `temp_db` fixture and `is True`/`is False` assertions in tests)

## Notes for Downstream Stories

- **STORY-005 / STORY-006** (`query_pipeline.py`): the parameters are now available but nothing passes them. Wire them at the success-path `log_query()` call (`query_pipeline.py:68-76`) as `pii_detected_input=bool(input_entities)`, `pii_detected_output=bool(output_entities)`, `pii_entities=<deduplicated input + output>`. **Dedup and ordering are the caller's job** — `log_query()` joins exactly what it is handed, in the order given, and a test now pins that. Critically, keep passing the **raw** `openrouter_result.response` as `response=`; only the returned `QuerySuccessResponse` gets the redacted text.
- **STORY-009** (`/audit`, `/stats`): the "no PII detected" storage format is now settled as **`NULL`, not `""`** — the decision STORY-003's report deferred to this story. The read-side split therefore only needs a `None` check (`row.pii_entities.split(",") if row.pii_entities else []`) and will never see a `[""]` artifact. Rows written before this story, and rows written on paths that never detect PII, are indistinguishable — both `NULL`.
- **Duplicate entity types within one row are possible in principle** if a future caller passes a list with repeats, since `log_query()` does not dedupe by contract. STORY-009's `top_pii_entities` aggregate should count distinct types per row if that matters for the metric.
