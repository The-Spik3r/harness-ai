---
story: STORY-015
prd: PRD-015
plan: .agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-015-e2e-openai-python-sdk.plan.md
epic_branch: epic/PRD-015-openai-compatible-endpoint
commit: f642340
status: COMPLETE
completed: 2026-10-27
---

# Implementation Report — STORY-015: E2E: OpenAI Python SDK, non-streaming, streaming, blocks and retries

**Plan**: `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-015-e2e-openai-python-sdk.plan.md`
**Epic Branch**: `epic/PRD-015-openai-compatible-endpoint`
**Commit**: `f642340`

## Summary

`tests/e2e/test_openai_sdk.py` drives the official OpenAI Python SDK (**`openai==3.40.0`**, pinned in the new `requirements-e2e.txt`) against a live harness. Only `base_url` and `api_key` change, and `max_retries` stays at the SDK default of 2. The stub upstream (`scripts/stub_openrouter.py`) and `uvicorn app.main:app` both run as subprocesses on ephemeral ports, and the harness reaches the stub through `OPENROUTER_BASE_URL`. The SDK behaves as PRD Section 7.5 intends:

- **Success.** Content, `finish_reason`, `usage` and `id == chatcmpl-harness-<audit id>` match the stub script and the audit row, without streaming and with streaming (including `include_usage`).
- **Blocks.** All five pre-upstream blocks (suspicious, duplicate, context, model, usage) raise `BadRequestError` or `PermissionDeniedError` with their Section 7.5 `code`, streamed and not. Each writes exactly one row and never reaches the upstream.
- **Retryable fault.** A 503-once upstream is retried by the SDK and succeeds, leaving one failed row and one success row.
- **Non-retryable fault.** An upstream 400 is raised after **one** attempt. The status is 502, which the SDK's status rule would retry, so that single attempt comes from `x-should-retry: false`. A negative control proved it: without the header there are 3 attempts.
- **Post-commit fault.** On a stream, an upstream fault arrives as one SSE `error` event and isn't retried (PRD 7.6).

The module is opt-in. A new `e2e` marker is skipped unless `--run-e2e` is given, independently of `--run-benchmark`. All storage access runs in child processes against a required loopback `HARNESS_E2E_LIBSQL_URL`, so the module isn't a `db` test and never touches the unit suite's database. The children run in a temp directory, so the developer `.env` isn't read.

The stub gained a per-rule `times` cap ("answer the first N matches, then fall through"), because SDK retries resend an identical body and a stateless rule can't tell the attempts apart. No file under `app/` changed.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Pin the SDK (3.40.0), install it, check that pydantic/httpx didn't move | `requirements-e2e.txt` | ✅ |
| 2 | Verify that `_should_retry` honours `x-should-retry` | (research, below) | ✅ |
| 3 | Stub `times` cap, thread-safe, per server | `scripts/stub_openrouter.py` | ✅ |
| 4 | Stub tests, README row, example rule | `tests/test_stub_openrouter.py`, `tests/e2e/scripts/README.md`, `tests/e2e/scripts/example.json` | ✅ |
| 5 | `e2e` marker + `--run-e2e`, independent of `--run-benchmark` | `tests/conftest.py`, `tests/test_e2e_marker.py` | ✅ |
| 6 | This story's stub script | `tests/e2e/scripts/openai_sdk.json` | ✅ |
| 7 | The E2E module | `tests/e2e/__init__.py`, `tests/e2e/test_openai_sdk.py` | ✅ |
| 8 | `-m "not db"` + full regression | none | ✅ |

## SDK version and retry behaviour (AC 3, AC 5)

- `python -m pip index versions openai` gave `openai (3.40.0)`, the newest on 2026-10-27. The venv had 3.36.1.
- The plain `pip install -r requirements-e2e.txt` failed with `CERTIFICATE_VERIFY_FAILED` (self-signed certificate in chain) on `files.pythonhosted.org`. That's the same TLS interception that blocks OpenRouter from this machine. `pip install --use-feature=truststore -r requirements-e2e.txt` worked: it still verifies certificates, but against the Windows certificate store.
- **openai 3.40.0 depends on `httpx2` 2.16.0**, a separate distribution, and no longer on `httpx`. The harness's `httpx` stayed at **0.28.1**, `pydantic` at **2.13.5** and `pydantic_core` at **2.46.5** (checked before and after). `pip check` reports no broken requirements. `tests/test_v1_schemas.py` passes 28/28 against 3.40.0.
- `openai/_base_client.py:925-964` (`_should_retry`) reads `x-should-retry` **before** its status rule: `"true"` retries, `"false"` doesn't, and otherwise it retries 408/409/429/>=500. In `_constants.py`: `DEFAULT_MAX_RETRIES = 2`, `INITIAL_RETRY_DELAY = 0.5`, `MAX_RETRY_DELAY = 8.0`. **The header is honoured by the pinned version**, which PRD Section 15's assumption needed.
- `openai/_streaming.py:95-106`: a `data:` event carrying `error` raises `APIError(body=data["error"])`, which is the PRD 7.6 contract.

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`python -c "from app.main import app"`) | ✅ OK |
| `tests/test_stub_openrouter.py` | ✅ 47 passed (38 before) |
| `tests/test_e2e_marker.py` + benchmark corpus + isolation harness, `-m "not db"` | ✅ 128 passed, 1 skipped |
| `pytest --markers` | ✅ lists `@pytest.mark.e2e` |
| `pytest tests/e2e` without the flag | ✅ 19 skipped (`e2e: pass --run-e2e`), no errors |
| `-m "not db"` (Docker-free, `HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:9`) | ✅ 3,469 passed / 45 skipped in 97 s |
| Full suite (throwaway libSQL `:8086`) | ✅ 4,893 passed / 46 skipped in 334 s, no flakes, 0 `libsql verdict` lines |
| E2E, `--run-e2e` (throwaway libSQL `:8088`) | ✅ 19/19 in ~29 s, three times |
| Frontend lint | n/a (no UI) |

The skipped count went from 27 to 46: these are the 19 E2E tests, skipped by default.

## End-to-end run

The commands, exactly as run (Git Bash, venv Python):

```bash
"$LOCALAPPDATA/Programs/DockerDesktop/Docker Desktop.exe"   # it was off; then: until docker info; do sleep 3; done
docker run -d --name harness-libsql-e2e015 -p 8088:8080 -e SQLD_NODE=primary ghcr.io/tursodatabase/libsql-server:latest
HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088 python -m pytest tests/e2e/test_openai_sdk.py -m e2e --run-e2e -v -p no:cacheprovider
```

| Run | Result |
|---|---|
| 1 (first draft) | 17 passed, 2 failed, 1 teardown error. Both failures were test-side, and both are fixed: see Deviations 3 and 4 |
| 2 | ✅ 19 passed in 28.9 s, 21 rows |
| 3, **same container** | ✅ 19 passed in 27.9 s. The run nonce isolates the runs, so the module doesn't need an empty database |
| Negative control: `_from_v1_error` with `headers=None` (local, reverted, `git diff -- app/` empty afterwards) | ❌ as intended: `test_a_non_retryable_upstream_400_is_raised_after_one_attempt` failed with `assert ['7', '7', '7'] == ['7']`, i.e. 3 upstream attempts without the header |
| Negative control: `HARNESS_E2E_LIBSQL_URL` unset | ❌ as intended: 19 setup errors, `HARNESS_E2E_LIBSQL_URL is not set. Start a throwaway libSQL: docker run ...`. No child started |
| Negative control: `HARNESS_E2E_LIBSQL_URL=http://db.example.com:8080` | ❌ as intended: `must be a loopback endpoint, got host 'db.example.com'` |
| 4, final code | ✅ 19 passed in 28.8 s |
| After the runs | 0 `uvicorn`/`stub_openrouter` processes left (the harness fixture asserts its port closes). `docker rm -f harness-libsql-e2e015 harness-libsql-story015` |

### Audit rows produced (final run; `rows.json`, no tokens or prompt text)

| id | user | success | streamed | ingress/profile | model | tokens | verdict field | error_message | from |
|---|---|---|---|---|---|---|---|---|---|
| 70 | main | True | False | v1/code | openai/gpt-4o | 18 | - | - | non-streaming success |
| 71 | main | True | False | v1/code | openai/gpt-4o | 18 | - | - | `X-Harness-Audit-Id` check |
| 72 | main | True | True | v1/code | openai/gpt-4o | 18 | - | - | streaming + `include_usage` |
| 73 | main | True | True | v1/code | openai/gpt-4o | 18 | - | - | streaming, no usage chunk |
| 74 | budget | True | False | v1/code | openai/gpt-4o | 5 | - | - | spends the 1-token budget |
| 75 | main | True | False | v1/code | - | - | pattern=ignore previous instructions | - | suspicious, json |
| 76 | main | True | True | v1/code | - | - | pattern=ignore previous instructions | - | suspicious, stream |
| 77 | main | True | False | v1/code | openai/gpt-4o | 4 | - | - | duplicate seed (json) |
| 78 | main | True | False | v1/code | - | - | duplicate | - | duplicate, json |
| 79 | main | True | False | v1/code | openai/gpt-4o | 4 | - | - | duplicate seed (stream case) |
| 80 | main | True | True | v1/code | - | - | duplicate | - | duplicate, stream |
| 81 | main | False | False | v1/code | - | - | - | context limit: messages 5 > 4 | context, json |
| 82 | main | False | True | v1/code | - | - | - | context limit: messages 5 > 4 | context, stream |
| 83 | main | True | False | v1/code | - | - | denied=query:model:not-on/the-list | - | model, json |
| 84 | main | True | True | v1/code | - | - | denied=query:model:not-on/the-list | - | model, stream |
| 85 | budget | True | False | v1/code | - | - | limit=tokens | - | usage, json |
| 86 | budget | True | True | v1/code | - | - | limit=tokens | - | usage, stream |
| 87 | main | False | False | v1/code | openai/gpt-4o | - | - | OpenRouter request failed: Server error '503 Service Unavailable' ... | 503-once, attempt 1 |
| 88 | main | True | False | v1/code | openai/gpt-4o | 2 | - | - | 503-once, SDK retry, answered |
| 89 | main | False | False | v1/code | openai/gpt-4o | - | - | OpenRouter request failed: Client error '400 Bad Request' ... | upstream 400, one attempt |
| 90 | main | False | True | v1/code | openai/gpt-4o | - | - | OpenRouter request failed: Server error '503 Service Unavailable' ... | streamed 503, one error event |

Every block wrote exactly one row, and the upstream log saw no request for any of them. The retry wrote rows 87 (failed) and 88 (success), and the completion id names row 88.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `requirements-e2e.txt` | CREATE | +4 |
| `scripts/stub_openrouter.py` | UPDATE | +31/-9 |
| `tests/conftest.py` | UPDATE | +25/-7 |
| `tests/e2e/__init__.py` | CREATE | +0 |
| `tests/e2e/scripts/README.md` | UPDATE | +4/-1 |
| `tests/e2e/scripts/example.json` | UPDATE | +9 |
| `tests/e2e/scripts/openai_sdk.json` | CREATE | +48 |
| `tests/e2e/test_openai_sdk.py` | CREATE | +622 |
| `tests/test_e2e_marker.py` | CREATE | +70 |
| `tests/test_stub_openrouter.py` | UPDATE | +50 |
| `.agents/plans/.../completed/STORY-015-e2e-openai-python-sdk.plan.md` | CREATE (archived) | +371 |

## Deviations from Plan

1. **Marker tests are in a new `tests/test_e2e_marker.py`, not in `tests/test_conftest_fixtures.py`.** That file covers only the database fixtures. The new file uses the `pytester` child with a copied conftest, from `tests/test_db_isolation_harness.py:522-527`.
2. **pip needed `--use-feature=truststore`** because of TLS interception on this machine (see above). This isn't a verification bypass.
3. **`resets_at` is `2026-10-29T00:00:00Z`, not `2026-10-22 00:00:00`.** The plan's regex copied the example spelling from PRD Sections 5 and 7.5. The implementation (`usage_limits._next_utc_midnight`, PRD-013) uses the audit `_TIMESTAMP_FORMAT`. The test now asserts the implemented format, plus the message suffix `resets at <resets_at>`. **Doc finding for STORY-019:** the PRD example and any README text should say `...T00:00:00Z`.
4. **The harness teardown waits up to 10 s for the port to close instead of probing once.** On Windows, the venv's `Scripts\python.exe` is a launcher whose interpreter runs as a child, so `terminate()` ends the launcher and the socket closes a moment later, when the launcher's job object closes. A single probe raced that. Afterwards no process was left. This is very likely the mechanism behind the earlier "orphaned uvicorn after TaskStop" memory note.
5. **The upstream-400 test checks attempts before the header.** The first negative control failed on the header assertion, which hid the attempt count. With the order reversed, the control shows the 3 attempts, which is the behaviour the AC is about.
6. **The budget case uses `set-limits --token-budget 1` plus one real answered call**, as planned (Decision 2), instead of the story note's `*=1` plus `charge()`. It worked first time, so the fallback wasn't needed.
7. **Extra coverage beyond the plan:** a streamed call *without* `stream_options` sends no usage chunk, the `X-Harness-Audit-Id` header is checked via `with_raw_response`, and there are non-loopback URL and `times: 1.5` checks.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/e2e/test_openai_sdk.py` (19, opt-in) | `models.list` allowlist. Non-streaming success vs script and row. `X-Harness-Audit-Id`. Streaming with `include_usage`. Streaming without usage. 10 × block (suspicious/duplicate/context/model/usage × json/stream). 503-once retried. Upstream 400 one attempt. Streamed fault, one error event. Every row `v1`/`code` |
| `tests/test_stub_openrouter.py` (+9) | `times` caps then falls through. Falls through to default. Counted per server. Uncapped without `hits`. 5 bad-script rows (`0`, `True`, `"1"`, `1.5`, on `default`) |
| `tests/test_e2e_marker.py` (4) | Skipped by default. `--run-e2e` runs them and leaves benchmark skipped. `--run-benchmark` doesn't un-skip e2e. Marker registered |

## Acceptance Criteria

- [x] Live `uvicorn` harness on the stub, `OpenAI(base_url=".../v1", api_key=<user token>)` with default `max_retries`: without and with `stream=True` (+ `include_usage`), content, `finish_reason`, `usage` and `id` match the stub script and the audit row (rows 70-73)
- [x] Suspicious, duplicate, over-limit, non-allowlisted model and exhausted budget, each streamed and not: `BadRequestError`/`PermissionDeniedError` with the 7.5 `code`, exactly one row per call, no retry (rows 75-86)
- [x] 503 once then 200: retried and succeeds, one `success=False` row + one success row (87, 88). Upstream 400: raised after one attempt, one row (89). `x-should-retry: false` honoured by openai 3.40.0, proven by the negative control
- [x] `client.models.list()` returns the allowlist
- [x] The report records the pinned `openai` version, the exact commands and the audit rows
- [x] All tasks completed
- [x] `-m "not db"` and the full suite pass, and `tests/e2e` is skipped by default
- [x] No file under `app/` changed
- [x] Follows existing patterns
