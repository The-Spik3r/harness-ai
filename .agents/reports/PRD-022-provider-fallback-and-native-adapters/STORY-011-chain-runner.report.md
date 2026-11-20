---
story: STORY-011
prd: PRD-022
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-011-chain-runner.plan.md
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
commit: pending
status: COMPLETE
completed: 2026-11-20
---

# Implementation Report — STORY-011: chain.py runner

**Plan**: `.agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-011-chain-runner.plan.md`
**Epic Branch**: `epic/PRD-022-provider-fallback-and-native-adapters`
**Commit**: `pending`

## Summary

New pure `app/services/upstream/chain.py`: sync `run(chain, *, primary, limits, needs, byok, policy, resolve, permitted, prepare, attempt, on_attempt_failed, released, clock)` returning a frozen `ChainOutcome` or raising the failing `UpstreamError` / `ChainExhausted`. Check order: forbidden, capability, byok, deadline, cached `prepare` (`redaction_limit`), `health.admit` last. Not wired into the pipeline (STORY-012). Additive support: `ChainSnapshot.limits`, `chain_config.current_limits()`, public `trust_lowered()`, and a keyword-only `timeout` on `call_upstream` / `stream_upstream` carried by `UpstreamRequest.timeout_seconds` and honoured by both adapters.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | limits on snapshot, `current_limits`, `trust_lowered` | `app/services/upstream/chain_config.py` | done |
| 2 | per-attempt timeout through seam and adapters | `types.py`, `__init__.py`, `openai_compatible.py`, `anthropic.py` | done |
| 3 | runner | `app/services/upstream/chain.py` | done |
| 4 | tests | `tests/test_chain_runner.py` + additions | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests | 549 + 3 new anthropic + 16 pii guard, all passed (see below) |
| E2E | none through the app (plan: not wired until STORY-012) |

Full suite: GitHub CI on push (user decision).

## Files Changed

`chain.py` (CREATE); `chain_config.py`, `types.py`, `__init__.py`, `openai_compatible.py`, `anthropic.py` (UPDATE); `tests/test_chain_runner.py` (CREATE, 48 tests); additions in `tests/test_chain_config.py`, `test_upstream_adapter.py`, `test_stream_upstream_seam.py`, `test_anthropic_adapter.py`.

## Deviations from Plan

- Seam signature snapshot `tests/test_upstream_adapter.py::test_call_upstream_keeps_call_openrouters_signature` updated (comment cites STORY-011): `timeout` appended as keyword-only.
- An owned httpx client is built with the bound and gets no per-call `timeout=`; only an injected client does, so existing stub clients `post(url, headers, json)` keep working. The Anthropic owned client is built via the unchanged two-argument `_open_sdk_client(provider, key)` when no timeout is set (suites patch that form).
- Otherwise as planned, including the orchestrator-accepted deviations.

## Acceptance Criteria

- [x] AC1 eligibility reasons and order: `test_chain_runner.py` skip and order tests
- [x] AC2 failure callback ordering, eligibility, `released()`: failure tests
- [x] AC3 `ChainExhausted`, retry-after, last error: exhaustion tests
- [x] AC4 outcome, `fallback_reason`, `skipped`: success tests
- [x] AC5 `prepare` hook, cache, fail closed, deadline timeout: prepare and deadline tests, adapter timeout tests
