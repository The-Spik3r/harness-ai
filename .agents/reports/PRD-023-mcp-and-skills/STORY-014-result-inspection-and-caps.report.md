---
story: STORY-014
prd: PRD-023
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-014-result-inspection-and-caps.plan.md
epic_branch: epic/PRD-023-mcp-and-skills
commit: 786c4a2
status: COMPLETE
completed: 2026-11-23
---

# Implementation Report - STORY-014: Results: size cap, pattern inspection, uninspected counts

**Plan**: `.agents/plans/PRD-023-mcp-and-skills/completed/STORY-014-result-inspection-and-caps.plan.md`
**Epic Branch**: `epic/PRD-023-mcp-and-skills`
**Commit**: `786c4a2`

## Summary

M9 of `mcp_gateway.call()` now screens a result that came back from upstream. The result is serialized once with `canonical_json`. Over the server's `max_result_bytes` it is not returned and not inspected (`result_too_large`). Otherwise it is inspected as one `tool` message under the `code` profile (text blocks, `resource.text`, canonical `structuredContent`, joined with newlines). A `block` hit withholds it (`result_blocked`); anything else is returned unmodified. Size and hash always describe the upstream result. Flags are `{"list", "pattern_id"}` dicts (`pattern_id` = zero-based index within the list) and `{"uninspected": n}`. A screening fault fails closed to `result_blocked`. Timeout and `upstream_error` texts are not screened (size/hash `None`).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Widen `record_outcome` flags (annotation, docstring, `sort_keys`) and model comment | `app/services/action_audit.py`, `app/db/models.py` | done |
| 2 | `_inspect_result`, `_screen_result`, texts, `result_digest(canonical)`, M9 branch | `app/services/mcp_gateway.py` | done |
| 3 | Tests | `tests/test_mcp_results.py`, `tests/test_mcp_tools_call.py`, `tests/test_mcp_audit.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests (`-m "not db"`) | 110 passed, 43 deselected |
| db-marked test | not run locally (Docker Desktop down); CI |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- Tests patch `pattern_config.get_profile` (not `pattern_detector.inspect`) to prove "never inspected" / fault injection: `tools/list` also calls `pattern_detector.inspect`.
- The stub's `inject` returns `structuredContent` too, so the expected upstream size in the block test includes it.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_mcp_results.py` | over cap not inspected; cap boundary (== ok, +1 too large); inject unmodified + flags, no text in logs/rows; dedup + order; `tool: block` withheld; uninspected counts; none uninspected; inspected inputs (resource, structured, joined, image-only); truncation counted; identity + PII untouched; harness results unscreened; screening fault fails closed; db row shape (`db`) |
| `tests/test_mcp_audit.py` | `record_outcome` stores dict flags as sorted-key JSON |
| `tests/test_mcp_tools_call.py` | two `result_digest(...)` assertions now pass the canonical text |

## Acceptance Criteria

- [x] AC1 too large: exact text, `result_too_large`, not inspected
- [x] AC2 inject returned unmodified; flags name list + pattern index, never text
- [x] AC3 `tool: block` -> error result `result_blocked`
- [x] AC4 image/audio/resource_link/unknown/blob uninspected + count; text, resource text, structured inspected as one message
- [x] AC5 `result_bytes`/`result_hash` stored (`hash_prompt`), result not stored, no PII redaction (db row test runs on CI)
