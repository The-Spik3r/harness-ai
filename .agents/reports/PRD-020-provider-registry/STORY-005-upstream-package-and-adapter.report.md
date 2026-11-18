---
story: STORY-005
prd: PRD-020
plan: .agents/plans/PRD-020-provider-registry/completed/STORY-005-upstream-package-and-adapter.plan.md
epic_branch: epic/PRD-020-provider-registry
commit: pending
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report - STORY-005: Upstream package, OpenAI-compatible adapter and call_upstream

## Summary

`app/services/upstream/` (params, types, openai_compatible, `call_upstream`) replaces the body of
`openrouter_client.py`, which is now aliases only. `call_upstream` resolves the model through the
registry, applies the D10 key rule, and calls `OpenAICompatibleAdapter` with
`httpx.Client(timeout=provider.timeout_seconds, follow_redirects=False)`. A 3xx is a non-retryable
`UpstreamError` (explicit status check). Error strings take the provider label. The stub gained
`"usage": null`, `auth=yes|no` in its log, `redirect_status`/`location` replies and an in-process
`require_key`.

## Validation

| Check | Result |
|-------|--------|
| Backend import | OK |
| test_upstream_adapter + test_stub_openrouter | 108 passed |
| test_openrouter_client + test_prd020_legacy_fixtures | 139 passed (fixtures unedited) |
| Router/v1/audit files (see below) | all dots; run cut by a 590 s timeout at ~86%, no failure seen |
| test_query_pipeline_run_conversation + test_untouched_app + test_pii_redaction_integration | 43 passed |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- The stub log puts `auth=yes|no` before `tools=`, not before `->`: two existing assertions
  (`endswith("tools=2 calls=1 -> 200")`, `endswith("tools=0 calls=0 -> 503")`) would otherwise break.
- `usage: null` stub reply is covered at the stub level; at the adapter level a null `usage` raises
  TypeError (unchanged legacy behaviour, `None["total_tokens"]`), so the adapter test uses a missing
  `usage` key. D8 (STORY-009) owns this.
- Dropped the planned "keyed file provider without a key" test: the loader refuses an unset `key_env`
  at load, so the runtime message is only reachable for a non-legacy provider whose key is empty.
  Legacy `key_missing` is covered.
- The "injected stub through run_query" check asserts the bound-alias default instead of running the pipeline.

## Tests Written

`tests/test_upstream_adapter.py` (shim identity, signature, no-shim-import scan, two-stub two-key run,
default client kwargs, 302/3xx not followed, `Local` labels, D10 both ways, legacy `key_missing`,
unroutable model, no-leak); `tests/test_stub_openrouter.py` (auth presence, usage null, redirect reply
and validation). `tests/test_openrouter_client.py`: two kwargs assertions now include
`follow_redirects: False` (PRD-020 D5/F3).

## Acceptance Criteria

- [x] AC1 legacy fixtures unedited and green; shim aliases; app imports
- [x] AC2 two stubs, `auth=yes|no`, own key only, no key in logs
- [x] AC3 client kwargs, 302 not followed
- [x] AC4 `Local ...` labels
- [x] AC5 D10 and legacy `key_missing`
