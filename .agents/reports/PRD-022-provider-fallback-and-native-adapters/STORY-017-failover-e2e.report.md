---
story: STORY-017
prd: PRD-022
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-017-failover-e2e.plan.md
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
commit: c6a39a6
status: COMPLETE
completed: 2026-11-20
---

# Implementation Report - STORY-017: Failover E2E

## Summary

`tests/e2e/test_failover.py`: two stub subprocesses (Chat as OpenRouter failing every request with 503, Messages as Anthropic answering a `bash` call), a real uvicorn harness with `PROVIDERS_FILE` + `PROVIDER_CHAINS_FILE`, the OpenAI SDK with `max_retries=0`. One ordered scenario, five tests. No change to `app/`, the stub or `_live.py`.

## Validation

| Check | Result |
|-------|--------|
| Backend import | OK |
| E2E (`--run-e2e`, throwaway libSQL :8088, container removed) | 5 passed, run 3 times (25 s each) |
| Without `--run-e2e` | 5 skipped; `tests/test_e2e_marker.py` 4 passed |
| Census/stub tests (`test_upstream_stream_collect`, `test_stub_openrouter`, `test_stub_anthropic_mode`, `test_e2e_live`) | 230 passed |
| Full suite | GitHub CI on push (user decision) |

## Timing of the 10 s open window

`health._BREAKER_OPEN_SECONDS = 10` (no seam; constants read from health.py by AST). From the request that opens OpenRouter's breaker: 5.3-5.6 s at the exhaustion step, 5.6-5.8 s at the `/providers/status` read. Guard margin 3 s at the exhaustion step: real margin about 4.4 s. No `app/` seam needed.

## Resolved open points (assert what the code does)

- Stub loader accepts `fail_status` in `default`: the OpenRouter script is just that.
- A 503 is `UpstreamError.kind == "status"`: `last_failure_class == "status"`, counters `openrouter:status`.
- `fallback_answers` counts answers with attempt > 1: R1-R5 = threshold (5), not 6; R6 was Anthropic's first attempt (OpenRouter skipped).
- `/audit` does not expose `success` / `error_message`, and `completion_id` is stored only for real-time streams: AC1/AC2 rows are found by `audit_id` (from the completion id) then `request_id`; success/error/exhausted-row checks read `dump_rows` after the window.
- Failure text is `OpenRouter request failed: Server error '503 Service Unavailable' for url ...` (no `: 503` directly after the label).
- Census over `tests/e2e/scripts/*.json` is `test_upstream_stream_collect._all_replies`: both new scripts pass it.

## Files Changed

| File | Action |
|------|--------|
| `tests/e2e/test_failover.py` | CREATE |
| `tests/e2e/scripts/failover_openrouter.json` | CREATE |
| `tests/e2e/scripts/failover_anthropic.json` | CREATE |
| `tests/e2e/scripts/README.md` | UPDATE |

## Deviations from Plan

- Row `success` / `error_message` and the exhausted row are asserted in a fifth test through `dump_rows` (child), after the window, because `/audit` omits them.
- `fallback_answers == 5`, not 6 (see above).

## Acceptance Criteria

- [x] AC1 `test_first_request_is_answered_by_anthropic_with_two_audit_rows` (+ the fifth test for success/error)
- [x] AC2 `test_breaker_opens_at_the_threshold_and_openrouter_is_not_called`
- [x] AC3 `test_total_outage_is_a_retryable_502_with_zero_stub_hits`
- [x] AC4 `test_providers_status_matches_what_happened`
- [x] AC5 skipped without the flag, passes with it
