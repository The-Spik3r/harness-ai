---
id: STORY-002
prd: PRD-022
slug: upstream-error-and-result-fields
title: UpstreamError kind/provider/retry_after + fallback_eligible, ChainExhausted, cache fields on results
type: feature
priority: high
complexity: medium
phase: "1 - Foundations"
status: todo
labels: [backend, upstream, contract]
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
plan: null
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-005, STORY-010]
skills: []
created: 2026-11-20
updated: 2026-11-20
---

# STORY-002: UpstreamError extension, ChainExhausted, cache fields on results

## Description

As the chain runner and the breaker, I want every upstream failure to say which provider failed, what kind of fault it was, and whether it may fall back, so that eligibility (Section 6.2) is one property and not a re-classification in each caller.

## Acceptance Criteria

- [ ] Given `UpstreamError`, when constructed as today (`message, *, upstream_status, retryable`), then `str(exc)`, `upstream_status` and `retryable` are unchanged and the new keyword fields default: `provider=None`, `kind=None`, `retry_after_seconds=None`; the `openrouter_client.OpenRouterError` alias and `/v1`'s `_PIPELINE_FAULTS` / `_fault_code` keep working with no edit to their tests
- [ ] Given the closed vocabulary `timeout | transport | status | shape | refusal | incompatible | misconfigured | exhausted`, when an `UpstreamError` has `kind` outside it, then construction raises `ValueError`; `fallback_eligible` is `retryable or kind == "misconfigured"` (parametrized test over every row of PRD 6.2)
- [ ] Given the OpenAI-compatible adapter, when it raises for a timeout, transport error, 5xx, 429 (with `retry-after` parsed to an int ≥ 1 when present), 401, other 4xx or a malformed body, then it sets `kind` (`timeout`, `transport`, `status`, `status`, `misconfigured`, `status`, `shape`) and `provider=<registry name>` with no change to message, status or `retryable` (existing adapter tests unmodified)
- [ ] Given `ChainExhausted`, when constructed with the skipped list and an optional `retry_after_seconds`, then it is an `UpstreamError` subclass with `kind="exhausted"`, `retryable=True`, message `all providers unavailable`, and carries `skipped: tuple[tuple[str, str], ...]` (provider, reason) and `last_error: Optional[UpstreamError]`
- [ ] Given `UpstreamResult` and `UsageReport`, when built as today, then the new defaulted fields `cache_read_tokens: Optional[int] = None`, `cache_write_tokens: Optional[int] = None`, `reasoning_blocks: int = 0` exist, and `collect()` copies the cache fields from the last `UsageReport` into the result (existing `collect(stream(r)) == complete(r)` tests unchanged)

## Technical Notes

- `app/services/upstream/types.py:15-37` (`UpstreamError`), `:40-60` (`UpstreamResult`), `:93-99` (`UsageReport`); `collect.py`; `openai_compatible.py`/`reply.py` for the existing classification (PRD cites the pre-PRD-020 `_classify_http_error` at `openrouter_client.py:188-197`; find its PRD-020 home).
- `ChainExhausted` lives in `types.py` and is exported from the package `__init__` so `v1.py` and the pipeline import it without importing `chain.py`.
- 401 is `kind="misconfigured"` but stays `retryable=False` (client contract unchanged; PRD 6.2 note).
- Frozen dataclasses; new fields last and defaulted (PRD-013/017 precedent).
- Orchestrator decision (STORY-001 findings): `UpstreamError` today has only `upstream_status`/`retryable`; `_classify_http_error` lives at `app/services/upstream/openai_compatible.py:54` and is typed on `httpx.HTTPError` -- set `kind`/`provider` there; the Anthropic adapter has its own mapping. `ToolCallDelta`'s field is `arguments` (not `arguments_fragment`).

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-005, STORY-010

## PRD Reference

Source: [`PRD-022/PRD.md`](../../PRDs/PRD-022-provider-fallback-and-native-adapters/PRD.md) — Sections 4 (Errors and result), 6.2, F1, D11
