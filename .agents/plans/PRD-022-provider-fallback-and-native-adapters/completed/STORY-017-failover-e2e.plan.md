---
story: STORY-017
prd: PRD-022
slug: failover-e2e
title: E2E — OpenRouter killed, Anthropic answers a tools request, breaker opens, status reports it
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
created: 2026-11-20
---

# Plan: Failover E2E

## Summary

One new module `tests/e2e/test_failover.py` (marker `e2e`, skipped without `--run-e2e`) runs two copies of the existing stub subprocess (`scripts/stub_openrouter.py`: Chat mode as OpenRouter, Messages mode as Anthropic), a real `uvicorn` harness with `PROVIDERS_FILE` + `PROVIDER_CHAINS_FILE` written to a tmp dir, and the OpenAI SDK. One ordered scenario drives AC1-AC4 against ONE harness process (breakers are per process). No stub or `app/` change: the stub already has Messages mode, scripted faults and a per-request log line that serves as the hit counter.

- Story: `.agents/stories/PRD-022-provider-fallback-and-native-adapters/STORY-017-failover-e2e.md`
- PRD sections used: 5 (US 1, 3, 4, 6), F6, F7, F9, F11, 10 (`/providers/status`, `/v1` errors), 11 MVP
- Systems affected: tests only (`tests/e2e/`, two stub scripts)

## Design Decisions

- **The stub is reused, not extended.** There is no HTTP control API. The hit counter is the stub's stderr log: every POST to a served endpoint logs one `... rule=<label> ... -> <status>` line, 503s included (`scripts/stub_openrouter.py:982`, `:1065`). `_live.Stub.requests()` / `settle()` (`tests/e2e/_live.py:215-233`) already count those lines, so `len(stub.settle())` is the counter. (`server.endpoint_hits()`, `stub_openrouter.py:1126`, is in-process only; not used.) Both stubs start with `_live.start_stub(script, cwd)` (`_live.py:236`, `--port 0`: runtime-picked ports). Its `base` ends in `/v1`; the Anthropic provider takes the base without `/v1` (mirror `tests/test_anthropic_primary_pipeline.py:50-69`; the stub routes any path ending `/messages`, line 1033).
- **Breaker cooldown is not configurable.** `_BREAKER_OPEN_SECONDS = 10.0` and `_BREAKER_FAILURE_THRESHOLD = 5` are module constants in `app/services/upstream/health.py:42-43`; no setting or env var changes them, and this story must not touch `app/`. So the whole "open" phase runs inside one 10 s window, guarded in the test: record `time.monotonic()` right after the request that opens OpenRouter's breaker (`t0`); before the exhaustion step, fail with an explicit "too slow for the breaker cooldown" message if `elapsed > open_seconds - 3`. Read both constants, never hard-code 5 / 10. Do not `import app.services...` in the test process (it builds `Settings()` and reads `.env`; `_live.py:7-8`): load `health.py` by file path with `importlib` as `tests/test_anthropic_primary_pipeline.py:30-34` does for the stub (it is pure: stdlib, `circuit_breaker`, `upstream.types`; if its imports cannot resolve that way, `ast`-parse the two constants and assert their types).
- **No SDK retries, no subprocess inside the window.** `openai.OpenAI(..., max_retries=0)` (a 502 `upstream_unavailable` is retried by the SDK, which would multiply hits; `test_openai_sdk.py:145` asserts the default 2: comment why this module overrides it). Audit rows are read with `httpx` on `GET /audit` using `harness.admin_token` (`_live.py:258`), not the `dump_rows` child (1-2 s each). `/providers/status` is `stats:read` (`app/routers/admin.py:235`), also reachable with the break-glass token.
- **Time-line (module-scoped, tests run in definition order as in `test_openai_sdk.py`).** OR stub: every request fails 503. Ant stub: a request whose last user message contains `total outage` fails 503, anything else answers a `bash` tool call.
  1. R1 (AC1): answered by Anthropic; OR failures 1.
  2. R2-R5: OR failures reach the threshold; breaker opens (`t0`).
  3. R6 (AC2): OR hit count unchanged (`len(or_stub.settle())` before/after), Ant +1, still answered.
  4. R7-R11, prompt contains `total outage`: OR skipped as `open`, Ant fails 503 `threshold` times, Ant breaker opens. Assert only status 502 and `error.code`.
  5. R12 (AC3): both open.
  6. `GET /providers/status` right after (AC4), still inside the window.
  After `t0` that is 7 harness requests, 2-3 settles (0.3 s each) and the status read: count hits only at the points that need it.
- **AC3 checked against the code: no contradiction.** All candidates skipped as `open` makes `chain.run` raise `ChainExhausted(skips, last_error=None, retry_after_seconds=min(..))` (`app/services/upstream/chain.py:222-224`). `v1_translate.translate_exhausted` returns the non-retryable `upstream_error` (O5) only when `last_error is None` AND every skip reason is capability/forbidden/byok; otherwise `upstream_unavailable` with `retry_after_seconds` (`app/services/v1_translate.py:692-717`). All-open is therefore 502 `upstream_unavailable` + `retry-after`, as the AC says. The pipeline writes one row with `attempt=None`, `skipped_providers="openrouter:open,anthropic-direct:open"`, `error_message=str(exc)` (`app/services/query_pipeline.py:1520-1546`). Assert the observed `error_message` (the V1 body says "all providers unavailable").
- **Finding the rows.** `request_id` is not in the `/v1` body. Take the audit id from `X-Harness-Audit-Id` (== `completion.id` suffix), `GET /audit?completion_id=chatcmpl-harness-<id>` gives `request_id`, then `GET /audit?request_id=<id>` gives both attempt rows (`app/routers/admin.py:41-66`, field names `:104-130`). R12 has no completion id: use the e2e user's newest row with `attempt is None` (the user is unique to the module).
- **Expected R1 rows (US 1).** By `attempt`: 1 = `success` false, `provider=openrouter`, `route_model=anthropic/claude-sonnet-4.6`, `error_message` starts `OpenRouter request failed: 503` (provider `label: OpenRouter`); 2 = `success` true, `provider=anthropic-direct`, `upstream_model=claude-sonnet-4-6`, `provider_trust=external`, `fallback_reason=status_503`. Both `model_used=anthropic/claude-sonnet-4.6`. Where the code's wording differs, assert the code and report it.
- **Tool-call assertions (US 3, F10).** Ant stub answers `tool_calls: [{"name":"bash","arguments":"{\"command\":\"npm test\"}"}]`. Client: `choices[0].message.tool_calls[0].function.arguments == '{"command":"npm test"}'`, `finish_reason == "tool_calls"`, `completion.model == "anthropic-direct/claude-sonnet-4-6"`, raw header `x-harness-provider == "anthropic-direct"`, `completion.model_extra["harness"]` has `provider` and `attempts == 2`. Harness env `V1_TOOLS_ENABLED=true` and an `ACTION_POLICY_FILE` allowing the command (`tests/e2e/_opencode.py:64-76` shows the shape; `shell.allow: [npm test]`; `bash` maps to `shell`, `app/services/action_adapters.py:516`). Do NOT set `V1_TOOL_MODELS` (Settings error with `PROVIDERS_FILE`, `app/config.py:864`); tool capability comes from `capabilities: {tools: true}`.
- **Isolation.** Child-only storage as in `test_openai_sdk.py`'s docstring: user via `_live.create_user`, audit via httpx to the harness; the test process never opens the DB. Every prompt carries a run nonce and a counter (the duplicate checker rejects repeats).

## Skills In Use

None (`.agents/skills/` holds only `frontend-design`, not applicable; story `skills: []`).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Module layout, marker, DB guard | `tests/e2e/test_openai_sdk.py:34-135` | `pytestmark = pytest.mark.e2e`, `importorskip("openai")`, `e2e_db_url` / `child_cwd` / `child_env` / `users` / `harness` fixtures, run-recipe docstring |
| Process plumbing | `tests/e2e/_live.py:236-300` | `start_stub`, `start_harness` (teardown stop + `port_closed_within`) |
| Registry/roles/policy files in tmp | `tests/e2e/test_opencode_realtime.py:162-190` | files under `child_cwd`; env `PROVIDERS_FILE`, `OPENROUTER_API_KEY=""`, `RBAC_ENABLED`, `V1_ENABLED`, `USAGE_REQUESTS_PER_MINUTE="*=unlimited"` |
| Anthropic provider yaml | `tests/test_anthropic_primary_pipeline.py:50-69` | `type: anthropic`, `insecure_http: true`, `key_env`, `usage_missing`, `default_max_tokens` |
| Chains yaml | `examples/chains.yaml` | `version: 1`, `chains: [{match: {model}, candidates: [{model}, {model}]}]` |
| Hit delta | `test_openai_sdk.py:166-173` (`new_requests`) | before/after of `stub.settle()` |
| Row report | `test_openai_sdk.py:151-163` | optional `rows.json` (ASCII, no token/prompt/answer) |

Registry text: `openrouter` (`label: OpenRouter`, `openai_compatible`, OR stub base, `key_env: E2E_OR_KEY`, `trust: external`, model `anthropic/claude-sonnet-4.6`, `capabilities: {tools: true}`) and `anthropic-direct` (`type: anthropic`, Ant stub base minus `/v1`, `insecure_http: true`, `key_env: E2E_ANT_KEY`, `trust: external`, model `anthropic-direct/claude-sonnet-4-6`, `upstream: claude-sonnet-4-6`, `default_max_tokens: 256`, `capabilities: {tools: true}`). Chain: match the first model, candidates both. Env also `E2E_OR_KEY`, `E2E_ANT_KEY` (dummies), `PROVIDER_CHAINS_FILE`. RBAC: reuse `tests/e2e/_opencode_realtime.py:28-65` roles shape if the user token needs it; otherwise `RBAC_ENABLED` as `test_openai_sdk.py:127`.

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/e2e/test_failover.py` | CREATE | scenario, fixtures, assertions |
| `tests/e2e/scripts/failover_openrouter.json` | CREATE | every request 503 (use `default` with `fail_status` if the loader accepts it, else one `{"regex": "", "fail_status": 503}` rule) |
| `tests/e2e/scripts/failover_anthropic.json` | CREATE | rule `{"contains": "total outage", "fail_status": 503}`; default = the `bash` tool call with explicit `usage` |
| `tests/e2e/scripts/README.md` | UPDATE | list the two scripts, if the file enumerates them |

No change to `app/`, the stub, `_live.py` or `requirements-e2e.txt` (`openai==3.40.0`). Grep `tests/test_e2e_*.py` / `test_stub_*.py` for a census of `tests/e2e/scripts/*.json` or e2e modules and register the new files if one exists.

## Tasks

### Task 1: Scripts
- Mirror `tests/e2e/scripts/tool_loop.json`, `openai_sdk.json`; `arguments` stays a string (PRD-017 D13).
- **Validate**: load both with `stub_openrouter.load_script` (a one-liner) and `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_stub_openrouter.py tests/test_stub_anthropic_mode.py`.

### Task 2: Fixtures (`tests/e2e/test_failover.py`)
- Copy the `test_openai_sdk.py` fixtures; add `or_stub`, `ant_stub` (module scope, `with _live.start_stub(...)`); `harness` writes providers/chains/policy files then `_live.start_harness`. One user is enough; audit and status use `harness.admin_token`. State shared across the ordered tests lives in a module-scoped dict fixture.

### Task 3: AC1 and AC2 tests
- R1 via `with_raw_response`, rows via `/audit`; R2-R5 in a loop of `threshold - 1` answered requests; stamp `t0`; R6 with OR delta 0 and Ant delta 1.

### Task 4: AC3 and AC4 tests
- R7-R11 (`pytest.raises(openai.APIStatusError)`, 502), window guard, R12: status 502, `error.code == "upstream_unavailable"`, `retry-after` an int in `[1, open_seconds]`, no `x-should-retry`, zero hits on both stubs, the row (`success` false, `attempt` null, `skipped_providers` as above). `/providers/status`: both `breaker.state == "open"`, `consecutive_failures >= threshold`, `last_failure_class` equals the real `UpstreamError.kind` for a 503 (`app/services/upstream/types.py`; assert what it reports), `counters.breaker_opens == 2`, `fallback_answers == 6` (R1-R6; confirm `health.count_fallback_answer` is per answered request), `attempts_failed` per provider equals `threshold`, `skipped["openrouter:open"]` equals the requests that met an open breaker (R6-R12 = 7) and `skipped["anthropic-direct:open"] >= 1`. Derive each number from the loops and constants.

### Task 5: Marker behaviour (AC5)
- Nothing to add: `tests/conftest.py` skips `e2e` without `--run-e2e` (`tests/test_e2e_marker.py`). Confirm the module collects cleanly without the flag (no module-level DB or process work).

## End-to-End Tests

- [ ] `HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088 pytest tests/e2e/test_failover.py --run-e2e -v` against a throwaway libSQL (recipe as in `test_openai_sdk.py` docstring, container `harness-libsql-e2e022`; never `harness-libsql-dev` :8080). Remove it afterwards.
- [ ] Without `--run-e2e` the module is reported skipped.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/e2e/test_failover.py --run-e2e
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/e2e/test_failover.py tests/test_e2e_marker.py
```
One pytest at a time; leave no stub or uvicorn child (fixture teardown asserts the harness port closes).

## CI

`.github/workflows/ci.yml:89` runs `pytest -q` with no `--run-e2e` and no `HARNESS_E2E_LIBSQL_URL`: CI skips every e2e test, this one included, so AC5's "in CI (if CI runs e2e)" is the skipped branch. The module must still collect on Linux; nothing in it is Windows-specific (process plumbing is `_live.py`'s).

## Risks

- **10 s cooldown on a slow machine** (main risk): guarded with an explicit failure message. If local margins fall under ~3 s, report to the orchestrator: the real fix is a settings/env seam for `_BREAKER_OPEN_SECONDS` in `app/` (PRD-018 constant, out of scope here).
- Harness latency (Presidio) could stretch R7-R12: keep settles to the needed points.
- `last_failure_class`, `error_message` and counter spellings are asserted from observed output, not the PRD's examples (`timeout`/`misconfigured` are other faults).

## Acceptance Criteria → Tasks → Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 Anthropic answers, canonical args, header, two rows | 2, 3 | `tests/e2e/test_failover.py::test_first_request_is_answered_by_anthropic_with_two_audit_rows` |
| AC2 breaker opens at threshold, then zero OR hits | 3 | `test_failover.py::test_breaker_opens_at_the_threshold_and_openrouter_is_not_called` |
| AC3 all open: 502 `upstream_unavailable` + retry-after, zero hits, skipped row | 4 | `test_failover.py::test_total_outage_is_a_retryable_502_with_zero_stub_hits` |
| AC4 `/providers/status` matches | 4 | `test_failover.py::test_providers_status_matches_what_happened` |
| AC5 skipped without the flag, passes with it | 5 | `tests/test_e2e_marker.py` plus the module run with and without `--run-e2e` |
