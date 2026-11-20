---
id: STORY-011
prd: PRD-022
slug: chain-runner
title: chain.py — per-request eligibility, per-route redaction hook, run() with per-attempt callbacks, ChainExhausted
type: feature
priority: high
complexity: large
phase: "3 - Chains and breaker"
status: todo
labels: [backend, upstream, security, resilience]
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
plan: null
report: null
commit: null
depends_on: [STORY-009, STORY-010]
blocks: [STORY-012]
skills: []
created: 2026-11-20
updated: 2026-11-20
---

# STORY-011: Chain runner

## Description

As the pipeline, I want one function that walks a model's candidates, skips the ineligible ones with a reason, computes what each candidate is allowed to receive, calls it, and decides whether a fault may fall back, so that the fallback rules live in one tested module and not inside the 1 500-line pipeline.

## Acceptance Criteria

- [ ] Given a candidate, when eligibility runs, then it returns a skip reason in this order: `forbidden` (`authz.authorize_route` for the candidate raises), `capability` (tools / forced tool_choice / realtime streaming / PRD-020 D9 estimate > `max_context_tokens`), `byok` (non-primary with a caller key), `open` / `half_open_busy` (breaker), `deadline` (remaining < `PROVIDER_MIN_ATTEMPT_SECONDS`); the primary is never skipped as `forbidden` (step 2 already ruled)
- [ ] Given `run(...)`, when a candidate's attempt raises an `UpstreamError`, then health records it, the `on_attempt_failed(candidate, error, *, attempt)` callback runs **before** the next candidate starts, and the chain continues only if `error.fallback_eligible` and the caller's `released()` is false; otherwise it re-raises that error
- [ ] Given all candidates skipped or failed, when the loop ends, then `ChainExhausted(skipped, last_error, retry_after_seconds=min over open skips, ≥1, else None)` is raised; if no attempt ran it carries no `last_error`; if the last attempt failed non-eligibly, that error is raised instead (PRD Section 10 table)
- [ ] Given success, when an attempt returns, then health records success and `run` returns an outcome with the result, the answering candidate/route, `attempt` number, `fallback_reason` (`status_<code>` / kind of the previous failure, plus `;trust_lowered` when the answering provider's trust is lower than the primary's) and the `skipped` list rendered as `provider:reason,…`
- [ ] Given the redaction hook, when a candidate is about to be called, then `run` asks the caller's `prepare(route)` for what to send; `prepare` returning a redaction-limit skip makes the candidate a `redaction_limit` skip, a `PiiRedactorError` propagates (fail closed); `run` caches prepared input by `(policy identity, relaxes_input())` and never feeds one candidate's output into another's (T3) — unit tests with fakes cover every rule above plus the deadline (each attempt's timeout = min(provider timeout, remaining)) with an injected clock

## Technical Notes

- New `app/services/upstream/chain.py`. It imports no pipeline module: the pipeline passes callables (`attempt(route, sent, timeout)`, `prepare(route)`, `on_attempt_failed`, `released`). Chain snapshot from STORY-009, breakers from STORY-010, `authz.authorize_route` (`app/services/authz.py:227`).
- Per-attempt timeout: `call_upstream` has no timeout parameter today; the plan must say how the deadline-bounded timeout reaches the adapter without changing the seam's positional signature (e.g. a keyword the seam passes only when set, so suite stubs without it keep working — PRD-010 STORY-005's rule for `params=`).
- Settings read per call (PRD 6.9); the chain and registry are one immutable snapshot per request.

## Dependencies

- **Blocked by**: STORY-009, STORY-010
- **Blocks**: STORY-012

## PRD Reference

Source: [`PRD-022/PRD.md`](../../PRDs/PRD-022-provider-fallback-and-native-adapters/PRD.md) — Sections 6.1, 6.2, 6.4, F4, F5, F7, D7, D8, D13, D15, D16, T2, T3, T7
