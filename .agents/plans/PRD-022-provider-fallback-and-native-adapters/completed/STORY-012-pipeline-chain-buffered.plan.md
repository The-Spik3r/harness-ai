---
story: STORY-012
prd: PRD-022
slug: pipeline-chain-buffered
title: Pipeline steps 6+7 through chain.run() for buffered calls
type: ENHANCEMENT
complexity: large
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
created: 2026-11-20
---

# Plan: Pipeline chain integration (buffered)

## Summary

`run_conversation` asks `chain_config.chain_for(model, ingress)` once at step 6. A model with no chain (`len(candidates) == 1`) and every streamed-realtime request keep today's code path: step 6 inline, one `call_openrouter`/`stream_upstream`, no `health`, no deadline, rows `attempt=1` with NULL chain columns. A chained buffered request skips the inline step 6 and calls `chain.run(...)` through the module binding. `chain.run` prepares (redacts) per route, attempts, records health and returns a `ChainOutcome`. The pipeline supplies `prepare`, `attempt`, `on_attempt_failed`, `permitted`, `resolve`; it writes one row per failed attempt as it happens, one exhaustion row when no attempt ran, and a success row built from the answering attempt. Step 6's body becomes a pure function `_prepare_input(messages, policy, route)`.

No router change: `ChainExhausted` is an `OpenRouterError` subclass (retryable, message `all providers unavailable`), so `/query` already answers 502 with that detail (`app/routers/query.py:90-91`) and `/v1` already maps it to `upstream_unavailable` (`app/routers/v1.py:300-301`). `retry-after`, `harness.provider`, `X-Harness-Provider` and `/v1`'s `model` are STORY-013; none is needed by this story's tests.

- Story: `.agents/stories/PRD-022-provider-fallback-and-native-adapters/STORY-012-pipeline-chain-buffered.md` (AC text lives there)
- PRD sections used: 6.1, 6.3, 6.4, 6.7, 6.9, F7, F8, 10 (error table), D10, D16, D17, user stories 1 and 7, T3
- Systems affected: `app/services/query_pipeline.py` only, plus tests

## Design Decisions (the orchestrator's design points are binding and applied verbatim)

- **No chain = PRD-020 path, unchanged.** `chained = len(req_chain.candidates) > 1 and not streamed_step`. `streamed_step` (today `:1058`) is a pure function of `visibility`; move that line above step 6. Streaming/realtime on a chained model stays single-candidate (primary only, inline step 6, `stream_upstream`); comment: "STORY-014 adds the window and per-attempt state".
- **`_prepare_input(messages, policy, route)`**: module level, pure, no logging. Returns `_Prepared(messages: tuple[Message, ...], entities: tuple[str, ...], relaxed: bool)` (frozen) or `_OverLimit(maximum, actual)` (frozen); raises `PiiRedactorError` unchanged. It is today's `:931-1040`: `relaxed = route.relaxes_input()`, `over = None if relaxed else _redaction_limit_exceeded(...)` (`:950`), the redaction loop, final-turn entities. Always from the raw `messages` (T3, D16). Messages go upstream as `list(prepared.messages)` (suite stubs may compare with a list).
- **Inline path** (no chain, or streamed): `try: p = _prepare_input(...) except PiiRedactorError as exc: _log_redaction_failed(route, exc); raise`. `_OverLimit` keeps today's limit row and `QueryBlockedContextLimitResponse`. Then `redacted_messages = list(p.messages)`, `input_entities = list(p.entities)`, `relaxed = p.relaxed`.
- **Chain path `prepare(r)` closure**: the same try/except with the candidate's route `r`; `_OverLimit` becomes `chain.REDACTION_LIMIT` (a skip, no row); otherwise returns the `_Prepared`. A redaction error on any candidate is today's fail-closed arm (row `success=0`, `error_message=str(exc)`, attempt/route_model NULL as today, then raise). `chain.run` does not record it.
- **Keep the `log_query(` census at 11.** `tests/test_query_pipeline_routing.py:403-409` asserts exactly 11 sites and the literal `_route_fields(route)` within 120 chars of each; `test_query_pipeline_audit_fields.py` scans the same sites. So no new `log_query(` call: two existing arms become local functions called from several places.
  - `_log_redaction_failed(route, exc)`: the step-6 redactor arm (`:1011-1032`), `pii_input_relaxed=route.relaxes_input()`.
  - `_log_failed_attempt(route, *, request_id, attempt, route_model, error_message, skipped_providers)`: the step-7 failure arm (`:1236-1255`). Parameter named `route` so `**_route_fields(route),` stays first. Keyword-only and required (the `_deny` rule, `:381-461`, with the same kind of comment). `model_used=model`; `streamed_realtime`, `reasoning_shown`, `stream_redaction_divergence`, `completion_id` read the live locals as today. Callers: (a) the inline `except` arm with `attempt=1, route_model=model, skipped_providers=None` (byte-identical rows), (b) `on_attempt_failed`, (c) the exhaustion row. Define it just before step 7's `try`.
- **`on_attempt_failed(candidate, error, *, attempt)`** (chain.py calls `on_attempt_failed(candidate, error, attempt=attempts)`): `_log_failed_attempt(attempt_route, request_id=request_id, attempt=attempt, route_model=attempt_route.model_id, error_message=str(error), skipped_providers=None)`, then `attempts_failed += 1`. `attempt_route` is the route the `attempt` closure last received (the pipeline is sync), so the row uses the exact snapshot route `chain.run` used. The row is written inside `chain.run` before the next candidate starts (AC2 spy ordering).
- **`attempt(route_, sent, timeout)` closure**: `answer_prepared = sent` and `attempt_route = route_` first; `kw = dict(extra)`; `kw["timeout"] = timeout` only when not None (stubs `(messages, model, api_key)` keep working); `call_openrouter(list(sent.messages), model=route_.model_id, api_key=openrouter_api_key if route_ is route else None, **kw)`. `call_openrouter` is `run_conversation`'s parameter, the seam `/v1`'s `_Upstream` and tests see (one call per attempt). The caller key reaches only the primary (`route_ is route`; `chain.run` skips others as `byok`).
- **`chain.run` arguments**: `chain=req_chain`, `primary=route`, `limits=chain_config.current_limits()`, `needs=RequestNeeds(tools=tools is not None, forced_tool_choice=_forces_tool(tools), streaming=False, estimate=lambda r: estimate_tokens(messages, ("", ()), r.provider.estimate_chars_per_token, tools=tools.tools if tools is not None else None))` (mirrors `_estimated_tokens_exceeded`, `:204-215`), `byok=openrouter_api_key is not None`, `policy=policy`, `resolve=provider_registry.resolve`, `permitted=` a closure over `authorize_route(identity, id)` returning False on `PermissionDenied` (called via this module's name so tests can patch it), `released=lambda: False`, no `clock`. `_forces_tool(tools)`: `tool_choice == "required"` or a Mapping (names a function); `"auto"`, `"none"` and None are not forced (PRD F4).
- **Health and counting.** One `health.sync({p.name for p in provider_registry.current().providers})` just before `chain.run`, chained requests only. The pipeline does NOT call `health.record`, `count_skipped` or `count_fallback_answer`; `chain.run` already does (overrides the story note "Increment ... counters here").
- **Answering attempt.** After `run` returns: `route = outcome.route` (deliberate rebinding: step 8's error row, the success row and `_merge_ignored_params(..., route)` then use the answering route and keep the guard-mandated literal `_route_fields(route)`; comment it), `relaxed = answer_prepared.relaxed`, `input_entities = list(answer_prepared.entities)`, `redacted_messages = list(answer_prepared.messages)`, `attempt_no = outcome.attempt`, `route_model = outcome.route.model_id`, `fallback_reason = outcome.fallback_reason`, `skipped = outcome.skipped`. `answer_prepared` is the value of the last call, which is the one that returned. Step 8 never sees the primary's prepared value (T3).
- **Defaults for the no-chain path** (set before step 7): `attempt_no=1`, `route_model=model`, `fallback_reason=None`, `skipped=None`. Step 8's error row (`:1346-1350`) and the success row (`:1391-1396`) replace the literal `attempt=1, route_model=model` with these locals and add `fallback_reason=`, `skipped_providers=`.
- **`model_used`.** `call_upstream` returns `model_used` equal to the id it was called with, so a chained result carries the answering catalogue id (D17). Response: `QuerySuccessResponse.model_used=openrouter_result.model_used` (answering id, line `:1494` unchanged). Audit rows on the chained path: `model_used=model` (requested). The no-chain path keeps `openrouter_result.model_used` in the row (stubs may return something else): `row_model_used = model if chained else openrouter_result.model_used`.
- **Exhaustion.** `except ChainExhausted as exc` around `chain.run`: if `attempts_failed == 0`, `_log_failed_attempt(route, request_id=request_id, attempt=None, route_model=model, error_message=str(exc), skipped_providers=",".join(f"{p}:{r}" for p, r in exc.skipped) or None)` (primary's PRD-020 columns), then `raise`. With attempts run, no extra row (F7); skips after the last attempt appear only in the counters (known limitation, say so in the code comment and the report). Any other `OpenRouterError` from `run`: its row was written by `on_attempt_failed`; re-raise (today's mapping). The chain branch sits beside the inline `try`, not inside its `except (OpenRouterError, PiiRedactorError)`, which would double-log.
- **Usage.** `admit` stays at 2c, once. `charge` at 7b stays once, from the answering result. A failed buffered attempt charges nothing. T6's released-charge arm is streamed-only and untouched.
- **Order change to document.** `safe.stage("masking_input")` and `safe.committed(...)` stay where they are (once per request). On a chain the primary's capability/byok/deadline skips now precede its redaction (chain.run's order).

## Skills In Use

None apply. `.agents/skills/` holds only `frontend-design`; the story has `skills: []`.

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Module-binding seam | `query_pipeline.py:17-20, 56-62` | import `chain`, `chain_config`, `health` as modules from `app.services.upstream`; call `chain.run(...)` as an attribute |
| Required keywords | `query_pipeline.py:381-461` (`_deny`) | `_log_failed_attempt` keyword-only, required, with the rule's comment |
| Failure row | `query_pipeline.py:1229-1256` | template for the helper |
| Route per row | `query_pipeline.py:324-335` | `_route_fields(route)` first argument |
| Chain tests | `tests/test_chain_runner.py`, `tests/_providers.py:54-100` (`provider_file`, `chains_file`) | registry and chains fixtures, reset on teardown |
| Pipeline driver | `tests/test_query_pipeline_routing.py:60-120` | `temp_db`, injected `call_openrouter`, audit-row readers from `tests/test_audit_characterization.py` |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/query_pipeline.py` | UPDATE | `_prepare_input`, `_Prepared`, `_OverLimit`, `_forces_tool`; step 6 split; chain branch; two local row helpers; answering-attempt rebinding; row fields |
| `tests/test_query_pipeline_chain.py` | CREATE | chain behaviour per AC |

No other app file changes. Existing tests stay unmodified.

## Tasks

### Task 1: Factor step 6 into `_prepare_input` (no behaviour change)
- **File**: `app/services/query_pipeline.py` (`:923-1040`)
- **Implement**: add `_Prepared`, `_OverLimit`, `_prepare_input` next to `_redact` (`:287`); add `_log_redaction_failed`; rewire the inline step 6; move `streamed_step` above step 6. Add `from app.services import provider_registry` and `from app.services.upstream import chain, chain_config, health` (no local named `chain`; call the request's chain `req_chain`).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_query_pipeline_pii_relaxation.py tests/test_query_pipeline_pii_profiles.py tests/test_query_pipeline_context_limit.py` (pass unmodified before moving on).

### Task 2: `_log_failed_attempt` for the inline failure arm
- **File**: `app/services/query_pipeline.py` (`:1199-1256`)
- **Implement**: the arm becomes the local helper; the inline `except` calls it with `attempt=1, route_model=model`. Rows byte-identical.
- **Validate**: `tests/test_query_pipeline_routing.py tests/test_query_pipeline_audit_fields.py` (census 11 holds).

### Task 3: Chain branch for buffered chained requests
- **File**: `app/services/query_pipeline.py` (step 6 head, step 7, step 8, success row)
- **Implement**: everything under Design Decisions: `req_chain`/`chained`, closures, `health.sync`, `chain.run`, exhaustion row, rebinding, defaults, `row_model_used`, new row fields. Streamed branch: add the STORY-014 comment only.
- **Mirror**: `app/services/upstream/chain.py:106-224` (signatures and call order).
- **Validate**: Task 4 tests plus the Task 1-2 files.

### Task 4: Tests
- **File**: `tests/test_query_pipeline_chain.py` (CREATE)
- **Implement**: `provider_file` (openrouter, anthropic-direct, an `internal` relaxed provider; yaml shapes from `tests/test_chain_config.py`) and `chains_file`; `health.reset()` before and after (autouse); injected `call_openrouter` stubs recording `(model, api_key, kwargs)`; rows read as the routing tests do. AC2 ordering: the second call's stub reads the audit rows and asserts the failure row already exists. Free ports and deadline loops only if a stub server is used.

## End-to-End Tests

- [ ] `TestClient(app).post("/query")` with the User story 1 chain and a 503 on the primary: 200, response `model_used` = answering id, two rows for one `request_id` (via `get_audit_log` / `GET /audit?request_id=`)
- [ ] `/query` with every candidate skipped (breakers opened with `health.breaker(name).force_open(...)`): 502 `all providers unavailable`, one `success=0` row with `skipped_providers`
- [ ] `/v1` with the same all-skipped chain: 502 `upstream_unavailable` through the existing mapping (no header asserted; STORY-013)

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_query_pipeline_chain.py tests/test_chain_runner.py tests/test_query_pipeline_routing.py tests/test_query_pipeline_audit_fields.py tests/test_query_pipeline_run_conversation.py tests/test_query_pipeline_pii_relaxation.py tests/test_query_pipeline_pii_profiles.py tests/test_query_pipeline_context_limit.py tests/test_query_pipeline_max_context_tokens.py tests/test_query_pipeline_usage_limits.py tests/test_query_pipeline_usage_estimate.py tests/test_query_pipeline_tools.py tests/test_query_pipeline_streaming.py tests/test_query_pipeline_dedup_key.py tests/test_prd020_legacy_fixtures.py tests/test_untouched_app.py
```
One pytest process at a time. Also grep `tests/` for `inspect.signature(` on `run_conversation` (its signature does not change). Full suite: GitHub CI.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 no chain: one call, rows `attempt=1`, chain columns NULL, legacy tests unmodified | 1, 2, 3 | new `test_no_chain_is_prd020_path` (`chain.run` patched to raise, never called; `health` untouched; no `timeout=`) plus the unmodified files above |
| AC2 503 then fallback: two rows, one `request_id`, failure row before attempt 2, `status_503`, `model_used` requested | 3 | `test_503_then_fallback_two_rows`, `test_failure_row_written_before_next_attempt` |
| AC3 relaxed primary fails, external gets standard-redacted text, `pii_input_relaxed=0`, `;trust_lowered`; over-limit candidate skipped; redaction error fails closed | 1, 3 | `test_fallback_redacts_from_raw_for_the_receiving_route` (asserts the stub's messages), `test_candidate_over_code_limit_is_skipped`, `test_redaction_error_on_candidate_fails_closed` |
| AC4 all skipped before any attempt: one `success=0` row, primary columns, `skipped_providers`, `/query` 502; BYOK one attempt, others `byok` | 3 | `test_exhausted_without_attempt_writes_one_row`, `test_query_route_maps_exhausted_to_502`, `test_byok_single_attempt_lists_byok_skips` (key reaches only the primary) |
| AC5 admit once, charge once with answering usage; failed row not a prior query; `model_used` response vs audit; success row lists skips | 3 | `test_admit_and_charge_once` (spies on `query_pipeline.admit`/`charge`), `test_resend_after_all_failed_is_answered`, `test_model_used_response_vs_audit`, `test_success_row_lists_skips` |
| No double counting; `health.sync` once | 3 | `test_pipeline_counts_nothing_itself` |
| Realtime stays single-candidate | 3 | `test_streamed_request_on_chained_model_stays_single_candidate` |

## Risks and open points

- `attempt=NULL` on the exhaustion row is my reading of D10/F8 (no call was made); the story is silent.
- A chained request whose primary is a `redaction_limit` skip (BYOK included) ends as `ChainExhausted` (502), not `QueryBlockedContextLimitResponse`: per the binding design point. The story's "primary-only" wording is the no-chain path here.
- A chained primary with a `capability` gap is now a skip, not a call. No-chain behaviour is unchanged.
- Skips after the last attempt are on no row (F7 limitation, as instructed).
- The `route = outcome.route` rebinding is what lets the existing guard tests (`_route_fields(route)` literal, 11 sites) stay unmodified.

## Orchestrator review (3.2)

Accepted: risks 1, 3, 4, 5, 6, 7 as written; no router change; the census-preserving helpers.
**Changed (risk 2, binding):** a redaction limit is deterministic, so "all providers unavailable, retry" would mislead. When `chain.run` raises `ChainExhausted` with **no attempt run** (`last_error is None`) and the **primary** was skipped as `redaction_limit`, the pipeline returns today's `QueryBlockedContextLimitResponse` and writes today's limit row from the primary's `_OverLimit` (the `prepare` closure keeps the primary's `_OverLimit` when it maps it to `REDACTION_LIMIT`), not the `'all providers unavailable'` row. If any attempt ran, or the primary was skipped for another reason, the F7 rules apply as planned. Add a test: `test_chained_primary_over_limit_with_no_attempt_keeps_limit_verdict`, and one where the primary is over the limit but a relaxed internal fallback answers.
