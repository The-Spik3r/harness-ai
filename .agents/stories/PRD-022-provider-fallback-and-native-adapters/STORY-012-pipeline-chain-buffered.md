---
id: STORY-012
prd: PRD-022
slug: pipeline-chain-buffered
title: Pipeline steps 6+7 through chain.run() for buffered calls — per-attempt rows, exhaustion row, admit/charge once
type: feature
priority: high
complexity: large
phase: "3 - Chains and breaker"
status: done
labels: [backend, pipeline, audit, security]
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-012-pipeline-chain-buffered.plan.md
report: .agents/reports/PRD-022-provider-fallback-and-native-adapters/STORY-012-pipeline-chain-buffered.report.md
commit: 505b126
depends_on: [STORY-003, STORY-011]
blocks: [STORY-013, STORY-014, STORY-015]
skills: []
created: 2026-11-20
updated: 2026-11-20
---

# STORY-012: Pipeline chain integration (buffered)

## Description

As an integrating developer, I want a provider outage on a buffered request to cost one slower answer instead of a 502, with each failed attempt on record, so that the harness keeps answering without crossing a trust, RBAC or BYOK line.

## Acceptance Criteria

- [ ] Given no chains file, when any request runs, then step 7 calls `call_upstream` exactly once with today's arguments and every existing pipeline/`/v1`/`/query` test passes unmodified (rows: `attempt=1`, chain columns NULL)
- [ ] Given the User story 1 chain and an OpenRouter 503, when a buffered request runs, then two rows share `request_id`: attempt 1 `success=0`, `provider=openrouter`, its `route_model`, error message unchanged; attempt 2 `success=1`, `provider=anthropic-direct`, `upstream_model`, `provider_trust`, `fallback_reason=status_503`; both `model_used=<requested id>`; the failure row is written before attempt 2 starts (spy ordering)
- [ ] Given a relaxed `internal` primary that fails and an `external` candidate with `allow_lower_trust`, when the fallback runs, then the external call receives standard-redacted text computed from the raw conversation, its row has `pii_input_relaxed=0` and `fallback_reason` ends with `;trust_lowered` (T3); a candidate over the `code` redaction limit is skipped as `redaction_limit`; a redaction error fails closed through today's arm
- [ ] Given every candidate skipped before any attempt, when the chain exhausts, then exactly one `success=0` row with `error_message='all providers unavailable'`, the primary's PRD-020 columns and `skipped_providers` is written and `/query` answers 502 `all providers unavailable`; a BYOK request makes exactly one attempt and lists the others as `byok` (User story 7)
- [ ] Given any chained request, when it completes, then `admit` was called once and `charge` once with the answering attempt's usage (reported or estimated); a failed attempt row is never a prior query (resending after an all-failed chain is answered, not held); `/query`'s `model_used` in the response is the answering catalogue id (D17) while the audit `model_used` stays the requested id; the success row's `skipped_providers` lists skips

## Technical Notes

- Orchestrator decision (STORY-008): the success row's `ignored_params` is `_merge_ignored_params(edge, result.dropped_params, route)` in `query_pipeline.py`; the realtime branch gets `dropped_params` from `upstream.dropped_params_for(route, request)`. With a chain, pass the *answering attempt's* route and request to both, never the primary's.

- `app/services/query_pipeline.py` steps 6 (`:880-999`) and 7 buffered branch (`:1151-1206`), 7b charge (`:1208`), success row (`:1337`). `_route_fields(route)` `:306` produces PRD-020's columns per route: call it with the **attempt's** route. Call `chain.run` through its module binding (PRD 6.9, `query_pipeline.py:17-20` pattern) so tests can replace it.
- Step 6 becomes `prepare(route)`: factor today's step-6 body (limit check + redaction loop + entity capture) into a function of `(messages, policy, route)` used both for the primary and for each candidate; the primary's behaviour and row on a limit breach / redaction error stay exactly as today.
- The attempt-row callback uses required keyword arguments `request_id`, `attempt`, `route` (PRD 6.9, `_deny` rule).
- Streaming (`streamed_step`) stays single-candidate in this story: the realtime path keeps calling `stream_upstream` once (STORY-014 adds the window). Record that limitation in the code comment.
- Increment STORY-010's process counters (`attempts_failed`, `fallback_answers`, `skipped`) here.
- Orchestrator decision (STORY-010): call `health.sync({p.name for p in registry.providers})` once per request before running the chain, so breakers of providers removed from the registry are dropped. Counting rules for `health` are in STORY-011's notes.
- Orchestrator decision (STORY-011): `chain.run(chain, *, primary, limits, needs, byok, policy, resolve, permitted, prepare, attempt, on_attempt_failed, released, clock)` is sync and returns `ChainOutcome(result, candidate, route, attempt, fallback_reason, skipped)` or raises `ChainExhausted` / the non-eligible `UpstreamError`. `limits` from `chain_config.current_limits()`; `resolve`/`permitted` wrap the registry and `authz.authorize_route` (chain.py imports neither). The `attempt` closure passes `timeout=` to `call_upstream` only when it is not None (suite stubs `(messages, model, api_key)` must keep working). `prepare` returns `chain.REDACTION_LIMIT` for a redaction-limit skip; a primary-only request whose primary is a `redaction_limit` skip must keep today's `QueryBlockedContextLimitResponse` (`query_pipeline.py` step 6), not become `ChainExhausted`. A request with no chain configured must behave exactly as today (one row, no new column values beyond PRD-020's).

## Dependencies

- **Blocked by**: STORY-003, STORY-011
- **Blocks**: STORY-013, STORY-014, STORY-015

## PRD Reference

Source: [`PRD-022/PRD.md`](../../PRDs/PRD-022-provider-fallback-and-native-adapters/PRD.md) — Sections 6.1, 6.4, 6.7, F7, F8, F10, D10, D15, D16, D17, Section 11 functional requirements, User stories 1, 2, 7
