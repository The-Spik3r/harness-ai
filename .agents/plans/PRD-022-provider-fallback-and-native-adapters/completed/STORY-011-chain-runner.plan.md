---
story: STORY-011
prd: PRD-022
slug: chain-runner
title: chain.py — per-request eligibility, per-route redaction hook, run() with per-attempt callbacks, ChainExhausted
type: NEW_CAPABILITY
complexity: large
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
created: 2026-11-20
---

# Plan: Chain runner

## Summary

New pure `app/services/upstream/chain.py`: `run(...)` walks a `chain_config.Chain`, skips ineligible candidates with a reason, asks the caller's `prepare(route)` what each may receive, calls `attempt(route, sent, timeout)`, records health, and decides fallback from `UpstreamError.fallback_eligible` and `released()`. Returns a frozen `ChainOutcome` or raises the failing error / `ChainExhausted`. It is not wired into the pipeline (STORY-012). Small additive edits: the per-attempt `timeout` reaches the adapters through a keyword-only seam parameter (this story), `ChainSnapshot` gains `limits`, and `trust_lowered()` is shared with STORY-009's validator.

- Story: `.agents/stories/PRD-022-provider-fallback-and-native-adapters/STORY-011-chain-runner.md`
- PRD sections used: 6.1-6.4, 6.9, F4, F7, 10 (error table), D6, D7, D8, D15, T3
- Systems affected: `app/services/upstream/` (chain.py new; `__init__`, `types`, both adapters, `chain_config` additive)

## Design Decisions

- **Sync, not async.** The pipeline is synchronous end to end: `run_conversation`/`run_query` are `def` (`query_pipeline.py:463,1518`), step 7 calls `call_openrouter(...)` directly (`:1196`), and `call_upstream`/`stream_upstream` are blocking (`upstream/__init__.py:136,153`). `run` is a plain `def`, so STORY-012 calls it where step 7 calls the seam and FastAPI runs it in its threadpool as today.
- **Contract (what STORY-012/014 consume):**
```python
def run(chain: Chain, *, primary: Route, limits: Optional[ChainLimits], needs: RequestNeeds,
        byok: bool, policy: Hashable,
        resolve: Callable[[str], Optional[Route]], permitted: Callable[[str], bool],
        prepare: Callable[[Route], Any],            # sent, or REDACTION_LIMIT
        attempt: Callable[[Route, Any, Optional[float]], Any],
        on_attempt_failed: Callable[..., None],     # (candidate, error, *, attempt)
        released: Callable[[], bool],
        clock: Callable[[], float] = time.monotonic) -> ChainOutcome
@dataclass(frozen=True) class RequestNeeds: tools: bool; forced_tool_choice: bool; streaming: bool; estimate: Optional[Callable[[Route], int]]
@dataclass(frozen=True) class ChainOutcome: result; candidate: Candidate; route: Route; attempt: int; fallback_reason: Optional[str]; skipped: Optional[str]  # "p:reason,..." or None
REDACTION_LIMIT = object-sentinel class instance (`prepare` returns it for a `code` size breach)
```
  `resolve` is the request's registry snapshot lookup (caller closes over it); `permitted(model_id)` wraps `authz.authorize_route` (True/False on `PermissionDenied`), so `chain.py` imports neither authz (settings, DB) nor the registry. A `resolve` of None is skipped as `forbidden` (provider rendered `unknown`; fail closed). `on_attempt_failed` gets the candidate only; the pipeline closure re-resolves its route. `byok` = the caller sent a key. The attempt closure passes the key only when `route.model_id == chain.model` (D15; a non-primary never runs with `byok`).
- **Limits come from the snapshot.** `ChainSnapshot` has no limits today (`chain_config.py:80-91`; `ChainLimits` lives only inside `load()`, `:353-357`). Add `limits: Optional[ChainLimits] = None` (default keeps every `ChainSnapshot(...)` call valid; only `validate_chains` builds one, `:303`) filled by `validate_chains`, and `chain_config.current_limits()`. No snapshot, `limits=None`: no deadline, timeout None (exactly today's single call). Deadline = `limits.deadline_seconds` else `primary.provider.timeout_seconds` (F5/D13, as `validate_chains` computes `:293-296`).
- **Deadline.** `start = clock()` when `run` starts. Per candidate `remaining = deadline - (clock() - start)`; `remaining < limits.min_attempt_seconds` -> `deadline` skip. Per-attempt `timeout = min(route.provider.timeout_seconds, remaining)` using that same reading (measured before `prepare`; redaction time can overshoot it, accepted: re-checking after `admit` would strand a half-open trial).
- **Timeout reaches the adapter.** This story adds it (cheap, and the deadline test needs a real consumer): `UpstreamRequest.timeout_seconds: Optional[float] = None` (`types.py:141-152`); `call_upstream` and `stream_upstream` get keyword-only `timeout: Optional[float] = None` after `*,` (`__init__.py:136,153`, positional signature unchanged), put into the request. Adapters use `request.timeout_seconds or provider.timeout_seconds`: `openai_compatible._open_client` (`:134-139`; an injected client gets `timeout=` per `.post`/`.stream` call, `:184,229`) and the stream deadline (`:221,237`); `anthropic._open_sdk_client` (`:471-478`, called `:500,537`; an injected `sdk_client` uses `.with_options(timeout=)`). **STORY-012's `attempt` closure adds `timeout=` to `extra` only when not None** (the `params=`/`tools=` rule, `query_pipeline.py:1043-1052`), so every suite stub `(messages, model, api_key)` keeps working; with no chain `run` passes None.
- **Check order (orchestrator-approved deviation from the AC list).** forbidden -> capability -> byok -> deadline -> `prepare` (`redaction_limit`) -> `health.admit` (`open`/`half_open_busy`). The AC lists the breaker before the deadline; the order differs only for a candidate with several reasons at once, and `admit` must be LAST because an admitted half-open trial that is not attempted blocks the provider until its 10 s lease expires (`circuit_breaker.py:218-226`; STORY-010 note). The primary skips `forbidden` (step 2 ruled). Every skip calls `health.count_skipped(provider, reason)` and is appended to `skipped`. Capability: `tools` needs `capabilities.tools` (+`forced_tool_choice` when forced), `streaming` for realtime, and `needs.estimate(route) > capabilities.max_context_tokens` only when that max is set (the estimate depends on the provider's chars-per-token, so it is a callable evaluated lazily, as `_estimated_tokens_exceeded` skips the estimate with no max, `query_pipeline.py:186-204`).
- **`prepare` cache (T3).** `cache[(policy, route.relaxes_input())]`. `policy` is the request's `PiiPolicy` (frozen dataclass, `pii_policy.py:70`), one per request (`query_pipeline.py:923`), passed by the caller. `prepare(route)` takes only the route: `run` has no way to hand it another candidate's output, and the cache returns output derived from the raw conversation under an identical key (rule 2). A cached `REDACTION_LIMIT` is reused too. A `PiiRedactorError` from `prepare` propagates (fail closed); a cache hit never re-calls `prepare`, so the pipeline's entity/audit side effects happen once per distinct key.
- **Failure semantics.** `UpstreamError` from `attempt`: `health.record(name, err)`; `on_attempt_failed(candidate, err, attempt=n)` before the next candidate; continue only if `err.fallback_eligible and not released()`, else re-raise `err` (a non-eligible error is therefore raised the moment it happens, and "last attempt failed non-eligibly" needs no end-of-loop case). Success: `health.record(name, None)`; `health.count_fallback_answer()` when `attempt > 1`. `attempt` numbers calls made, so skips do not consume numbers (rows are per attempt, D10). Any other exception (incl. `PiiRedactorError` from `prepare`, `KeyboardInterrupt`/cancellation, a bug) propagates unchanged and is not recorded. **A claimed half-open trial in that case is accepted:** `admit` already claimed it, nothing reports, and the provider stays `half_open_busy` until the breaker's lease (`open_seconds` = 10 s) lapses; there is no release API and `record(None)` would falsely close the breaker. Tested.
- **Exhaustion.** Loop ends with no success: `ChainExhausted(skipped, last_error=<last eligible failure or None>, retry_after_seconds=max(1, min(skip.retry_after for open/half_open_busy)) or None)`. Skips carry `retry_after` from `Admission`; None entries are ignored. `last_error` is None when no attempt ran.
- **`fallback_reason`.** Base from the previous failed attempt: `status_<code>` when `error.upstream_status` is set, else `error.kind or "unclassified"`; `;trust_lowered` appended when `trust_lowered(primary.provider, route.provider)`. No previous failure (primary skipped, a later candidate answers as attempt 1): only `trust_lowered` when it applies, else None. `trust_lowered` is extracted from `_check_entry`'s `crossing` expression (`chain_config.py:~208`, `primary.trust == "internal" and provider.trust == "external"`) into a public pure function used by both, so startup and runtime share one ordering (D6; "compared with the primary, never the previous entry").
- **STORY-014 hook.** `released()` is called after every failed attempt, live, so it may close over the sink/stream state that the streaming `attempt` mutates; `run` never reads sink state itself. Fresh per-attempt state is the closure's job.

---

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`; no UI).

---

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Module docstring, PRD cites, pure/locks statement | `upstream/health.py:1-27` | Same register; state "Pure" and what is injected |
| Frozen dataclasses, closed vocab | `chain_config.py:56-78`, `health.py:55-65` (`SKIP_REASONS`) | `Candidate/Chain/ChainLimits`; use `health.SKIP_REASONS` words only |
| Health calls | `health.py:record/admit/count_skipped/count_fallback_answer` | Call via the module (`health.admit(...)`) so tests can patch it |
| Error types | `types.py:28-67` (`UpstreamError`), `:70-95` (`ChainExhausted`) | Build `ChainExhausted(skipped, last_error=, retry_after_seconds=)`; never put text in it (T10) |
| Injected-clock tests | `tests/test_provider_health.py:19-24` (`now` fixture, `health.reset(clock=...)`) | Same fixture; no real sleeps |
| Purity test | `tests/test_provider_health.py:346-359` | Same AST walk for `chain.py` (allowed internal imports: `chain_config`, `health`, `types`) |
| Chain files in tests | `tests/_providers.py:71-79` | Build registries/routes with the existing helpers |

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/upstream/chain.py` | CREATE | `run`, `RequestNeeds`, `ChainOutcome`, `REDACTION_LIMIT` |
| `app/services/upstream/chain_config.py` | UPDATE | `ChainSnapshot.limits`, `current_limits()`, public `trust_lowered()` (additive; behaviour unchanged) |
| `app/services/upstream/types.py` | UPDATE | `UpstreamRequest.timeout_seconds` (default None) |
| `app/services/upstream/__init__.py` | UPDATE | `timeout` keyword on `call_upstream`/`stream_upstream` |
| `app/services/upstream/openai_compatible.py`, `anthropic.py` | UPDATE | Honour `request.timeout_seconds` |
| `tests/test_chain_runner.py` | CREATE | Every rule with fakes + injected clock; AST purity |
| `tests/test_chain_config.py`, `tests/test_upstream_adapter.py`, `tests/test_stream_upstream_seam.py` | UPDATE | Small additions (limits on snapshot, `trust_lowered`, timeout reaches adapter, unset keyword absent) |

## Tasks

### Task 1: Shared pieces in `chain_config.py`
- Add `limits` to `ChainSnapshot` (set in `validate_chains`, `:303`), `current_limits()`, `trust_lowered(primary_provider, provider) -> bool`; make `_check_entry` use it.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_chain_config.py`

### Task 2: Timeout through the seam and adapters
- Per the Design Decision above. Default None everywhere; no existing call changes. Tests: the OpenAI-compatible adapter builds its client / the SDK client gets the smaller timeout; unset keeps `provider.timeout_seconds`; a stub without `timeout=` is untouched.
- **Mirror**: `__init__.py:136-150` (keyword-only `tools=`).
- **Validate**: `... pytest -q -p no:cacheprovider tests/test_upstream_adapter.py tests/test_stream_upstream_seam.py`

### Task 3: `chain.py`
- Implement per the contract. Order of operations per candidate: resolve -> forbidden (non-primary) -> capability -> byok -> deadline -> cached `prepare` -> `health.admit` -> clock-derived timeout -> `attempt`. Imports: stdlib, `health`, `types`, `chain_config` only (no settings read, no `open`).
- **Validate**: Task 4 tests.

### Task 4: `tests/test_chain_runner.py`
Fakes for `attempt`/`prepare`/callbacks, `health.reset(clock=...)`, one shared fake clock for `run` and health. Cases:
1. each skip reason alone (`forbidden`, `capability` x4 incl. estimate only when max set, `byok`, `deadline`, `redaction_limit`, `open`, `half_open_busy`), each calling `count_skipped`; the primary is never `forbidden` (`permitted` not called for it).
2. order with several reasons at once; `admit` is last: a candidate that is `redaction_limit` or `deadline` never calls `admit` (half-open trial not claimed: spy on `admit`).
3. failure: eligible error -> `record`, then `on_attempt_failed` strictly before the next `attempt` (shared event log), next candidate runs; non-eligible (4xx, `shape`, `incompatible`) re-raised, no further attempt; eligible but `released()` true -> re-raised.
4. exhaustion: all skipped (no `last_error`, retry_after = min over open/half_open_busy, >=1, None when none open); all failed eligibly (`last_error` = the last); mixed skip + fail.
5. success: `record(None)`, `count_fallback_answer` only for `attempt > 1`, outcome fields, `skipped` string `p:r,p:r`, `None` when empty.
6. `fallback_reason`: `status_503`, `timeout`, `unclassified`, `;trust_lowered` (internal primary, external answer), trust-only with primary skipped, none on attempt 1 success.
7. `prepare`: cache hit for same `(policy, relaxes_input)` and miss for different; internal-relaxed primary fails then the external candidate gets standard-redacted text (T3: fake `prepare` keyed on `relaxes_input()`); `PiiRedactorError` propagates, nothing attempted; `REDACTION_LIMIT` -> skip.
8. deadline with injected clock: timeout = `min(provider, remaining)`; a slow first attempt (clock advanced inside the fake) leaves `remaining < min_attempt` -> next candidate `deadline`-skipped; `limits=None` -> timeout None, no deadline skip; default deadline = primary's `timeout_seconds`.
9. non-`UpstreamError` from `attempt` propagates unchanged and is not recorded; a half-open trial claimed that way is `half_open_busy` until the 10 s lease passes (advance clock), then admitted again.
10. AST purity of `chain.py`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_chain_runner.py`

## End-to-End Tests

- [ ] None through the app: `run` is not wired until STORY-012. Task 2 covers the seam end to end with the loopback stub style of `tests/test_upstream_adapter.py`.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_chain_runner.py tests/test_chain_config.py tests/test_provider_health.py tests/test_upstream_adapter.py tests/test_stream_upstream_seam.py tests/test_upstream_error_fields.py tests/test_untouched_app.py
```
Full suite: GitHub CI on push (user decision). Grep `tests/` for `UpstreamRequest(` and `ChainSnapshot(` hits and run them.

## Acceptance Criteria → Tasks → Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 eligibility reasons + order | 3, 4 | `test_chain_runner.py` cases 1, 2 |
| AC2 failure callback ordering, eligibility, `released()` | 3, 4 | case 3 |
| AC3 `ChainExhausted`, retry-after, non-eligible last error | 3, 4 | case 4 |
| AC4 success outcome, `fallback_reason`, `skipped` string | 1, 3, 4 | cases 5, 6 |
| AC5 `prepare` hook, cache, fail closed, deadline timeout | 2, 3, 4 | cases 7, 8, and Task 2 adapter tests |

Plus: all tasks completed, validation passes, follows existing patterns.

## Notes for the orchestrator / STORY-012

- Deviations: check order (approved); `limits` stored on `ChainSnapshot` (the snapshot had none); `timeout` seam wired here, not STORY-012.
- STORY-012: today a primary `redaction_limit` returns `QueryBlockedContextLimitResponse` (`query_pipeline.py:960-985`); under `run` the primary is a `redaction_limit` skip, so the pipeline must keep that verdict when every candidate is skipped and the primary's skip is `redaction_limit` with no attempt run.
- Open: `count_fallback_answer` fires on `attempt > 1` (binding); a candidate answering as attempt 1 because the primary was skipped is not counted as a fallback answer.

## Orchestrator review (3.2)

All deviations accepted: limits on `ChainSnapshot` (optional, default None); the `timeout` keyword wired here (buffered and stream; the stream adapters' existing total deadline becomes `min(provider, remaining)`, consistent with D13); check order with `admit` last; `resolve`/`permitted` callables instead of importing `authz`; `fallback_reason` with no previous failed attempt is `trust_lowered` when it applies, else None; `count_fallback_answer` only for `attempt > 1` (PRD F8: success rows with `attempt > 1`); the half-open lease after a non-`UpstreamError`.
