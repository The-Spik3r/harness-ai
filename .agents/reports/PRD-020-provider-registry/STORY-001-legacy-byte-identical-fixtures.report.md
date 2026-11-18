---
story: STORY-001
prd: PRD-020
plan: .agents/plans/PRD-020-provider-registry/completed/STORY-001-legacy-byte-identical-fixtures.plan.md
epic_branch: epic/PRD-020-provider-registry
commit: pending
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report - STORY-001: Record the legacy byte-identical fixtures

**Plan**: `.agents/plans/PRD-020-provider-registry/completed/STORY-001-legacy-byte-identical-fixtures.plan.md`
**Epic Branch**: `epic/PRD-020-provider-registry`
**Commit**: `pending`

## Summary

Added `tests/fixtures/prd020_legacy/` and `tests/test_prd020_legacy_fixtures.py`, recorded once (`PRD020_RECORD_FIXTURES=1`) against the unchanged `app/`. Upstream requests come from the real `call_openrouter` over `httpx.MockTransport`; `/v1/models*` and `/query` through `TestClient(app)`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Capture helpers, record/replay | `tests/test_prd020_legacy_fixtures.py` | done |
| 2 | Upstream request fixtures (6 cases) | `tests/fixtures/prd020_legacy/upstream/` | done |
| 3 | Error + success-result fixtures, stub 503 test | `errors.json`, `results.json` | done |
| 4 | `/v1/models` fixtures (6 responses) | `v1/` | done |
| 5 | `/query` fixtures (7 cases a-g) | `query/` | done |
| 6 | README + test | `README.md` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests | 159 passed (new file 12, plus test_openrouter_client.py, test_v1_models.py) |
| Replay x2 after record | 12 passed each, no file changed |
| Mutation check (reorder payload keys in text_params fixture, not committed) | replay failed, restored |
| `git diff --stat HEAD -- app/` | empty |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

| File | Action |
|------|--------|
| `tests/test_prd020_legacy_fixtures.py` | CREATE |
| `tests/fixtures/prd020_legacy/**` (README, errors.json, results.json, upstream/, v1/, query/) | CREATE |

## Deviations from Plan

- Per orchestrator: upstream bodies are compared as `json.loads(..., object_pairs_hook=list)` ordered pairs, not raw bytes (httpx unpinned). Fixture bodies are pretty JSON in sent key order.
- Error messages embedding httpx exception text (http_400/429/503, transport_*) and the `/query` upstream-503 502 detail pin only the harness prefix, status, retryable and URL (httpx wording is version-dependent). Other error strings are pinned in full.
- Added `results.json` (success `OpenRouterResult` fields) and `query/meta.json`; `/query` blocked answers are HTTP 200 with a BLOCKED body (recorded as is).
- `PII_REDACTION_ENABLED` is pinned off so the /query cases do not build spaCy; prompts carry no PII.
- Docker Desktop and `harness-libsql-dev` were not running; started both.

## Tests Written

`tests/test_prd020_legacy_fixtures.py`: upstream request x6 (text_minimal, text_params, tool_request, tool_minimal, byok_key, base_url_trailing_slash), error cases, success result fields, stub 503, `/v1/models` bodies, `/query` bodies, README.

## Acceptance Criteria

- [x] AC1 payload + headers, text and tool: `test_upstream_request_*`
- [x] AC2 error strings, status, retryable: `test_error_cases_match_recorded`, `test_stub_503_through_call_openrouter`
- [x] AC3 `/v1/models` bodies: `test_v1_models_bodies_match_recorded`
- [x] AC4 `/query` success, `query:model:`, `query:byok`: `test_query_bodies_match_recorded`
- [x] AC5 README + empty `app/` diff: `test_readme_documents_normalization`
