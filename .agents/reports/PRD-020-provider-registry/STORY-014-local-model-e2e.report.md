---
story: STORY-014
prd: PRD-020
plan: .agents/plans/PRD-020-provider-registry/completed/STORY-014-local-model-e2e.plan.md
epic_branch: epic/PRD-020-provider-registry
commit: 54ad114
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report — STORY-014: Opt-in end-to-end run against a real local OpenAI-compatible server

**Plan**: `.agents/plans/PRD-020-provider-registry/completed/STORY-014-local-model-e2e.plan.md`
**Epic Branch**: `epic/PRD-020-provider-registry`
**Commit**: `54ad114`

## Summary

An opt-in E2E module drives a real harness subprocess (file mode, one keyless `local` provider, `trust: internal`, `usage_missing: estimate`, `timeout_seconds: 300`) against LM Studio at `http://localhost:1235/v1`, model `google/gemma-4-e4b`. Pure helpers (env defaults, probe, server facts, registry YAML) have unit tests in the default suite. No `app/` change.

The story ACs were amended by the planner: `ollama` -> `local`, Ollama defaults -> LM Studio defaults, "server version / model digest" -> "what the server exposes".

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Helpers | `tests/e2e/_local_model.py` | done |
| 2 | Helper unit tests | `tests/test_local_model_e2e_helpers.py` | done |
| 3 | E2E module | `tests/e2e/test_local_model.py` | done |
| 4 | Story AC text + static check | story file | done |
| 5 | Live run | n/a | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Frontend lint | n/a (no frontend) |
| Helper unit tests + `tests/test_e2e_live.py` | 33 passed |
| Live E2E (helpers + e2e files, `--run-e2e`, defaults, libSQL on :8088) | 12 passed in 42.15s (4 e2e + 8 helper) |
| Without `--run-e2e` | 4 skipped ("e2e: pass --run-e2e") |
| `HARNESS_E2E_LOCAL_MODEL=no-such-model` | 4 skipped: "model 'no-such-model' is not served at http://localhost:1235/v1; set HARNESS_E2E_LOCAL_MODEL to one of ['google/gemma-4-e4b', 'text-embedding-nomic-embed-text-v1.5']" |
| `HARNESS_E2E_LOCAL_BASE_URL=http://127.0.0.1:9/v1` | 4 skipped: "no local model server answered at http://127.0.0.1:9/v1/models (ConnectError); start one or set HARNESS_E2E_LOCAL_BASE_URL" |
| Full suite | GitHub CI on push (user decision) |

The throwaway libSQL container `harness-libsql-e2e020-014` was removed afterwards.

## Live run facts (`local-model-run.json`, AC5)

- Server: LM Studio (`/api/version` not exposed). Version: not exposed. Digest: not exposed.
- Model info from `/api/v0/models`: arch `gemma4`, quantization `Q4_K_M`, compatibility_type `gguf`, state `loaded`, max_context_length 131072.
- Usage: `usage_estimated` false on all three paths. `/query` real, `/v1` streamed real, `/v1` tool call real (the server reports `usage`).
- Rows: all `provider='local'`, `provider_trust='internal'`, `model_used='google/gemma-4-e4b'`, success. `/query` 281 tokens; `/v1` streamed row `streamed=true`, 39 tokens; `/v1` tool row `has_tool_calls=true`, 162 tokens.
- Tool call: outcome `called` (not skipped); one `action_decisions` row `read` / allow / `fs.read`, joined by `audit_id`.

## Server quirk found (PRD risk 2; docs, not code)

LM Studio rejects the object form of `tool_choice` (`{"type":"function","function":{"name":"read"}}`) with HTTP 400: "Invalid tool_choice type: 'object'. Supported string values: none, auto, required". The harness forwarded it correctly and answered 502 (it does not relay the upstream reason). The first live run failed on this (the planned object form); the module now sends `tool_choice: "required"` (with a single tool that forces it, and is accepted by LM Studio). The retry-without-`tool_choice` fallback stays for other servers. Worth a line in the STORY-015 docs.

## Files Changed

| File | Action |
|------|--------|
| `tests/e2e/_local_model.py` | CREATE |
| `tests/e2e/test_local_model.py` | CREATE |
| `tests/test_local_model_e2e_helpers.py` | CREATE |
| story, index, plan (archived), this report | UPDATE/CREATE |

## Deviations from Plan

- `tool_choice` is the string `"required"`, not the forced-function object (LM Studio quirk above). The fallback's assertion is relaxed to "502 and a failed row", because the harness does not relay the upstream error text.
- A missing `HARNESS_E2E_LIBSQL_URL` fails like every other E2E module (orchestrator decision), after the model-server probe has passed.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_local_model_e2e_helpers.py` | registry YAML loads keyless/internal/estimate; probe ok / model missing / unreachable; server_facts LM Studio / Ollama / not exposed; local_config defaults and overrides |
| `tests/e2e/test_local_model.py` | `/query`; SDK streamed `/v1`; forced `read` tool call through the action policy; facts recorded |

## Acceptance Criteria

- [x] AC1 `/query` answered, row `provider='local'` (`test_query_is_answered_and_the_row_names_local`)
- [x] AC2 `/v1` via the OpenAI SDK, streamed to the client (`test_sdk_v1_streamed_to_client_is_answered_and_the_row_names_local`)
- [x] AC3 tool call released through the action policy (`test_v1_tool_call_is_released_through_the_action_policy`)
- [x] AC4 skipped, never failed, reason names what is missing (probe unit tests + the three manual variants above)
- [x] AC5 server facts and usage real/estimated recorded (`test_zz_facts_recorded` + the section above)
