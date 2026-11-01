---
story: STORY-014
prd: PRD-015
plan: .agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-014-stub-upstream.plan.md
epic_branch: epic/PRD-015-openai-compatible-endpoint
commit: e6d9ab7
status: COMPLETE
completed: 2026-10-26
---

# Implementation Report — STORY-014: Scripted stub upstream for E2E runs

**Plan**: `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-014-stub-upstream.plan.md`
**Epic Branch**: `epic/PRD-015-openai-compatible-endpoint`
**Commit**: `e6d9ab7`

## Summary

`scripts/stub_openrouter.py` is a scripted stand-in for OpenRouter. It uses only the standard
library (`http.server.ThreadingHTTPServer`) and speaks enough Chat Completions for
`call_openrouter`. It is a test tool, not shipped behaviour (PRD 7.9). Nothing under `app/` imports
it, and `app/` is unchanged.

- **Script format.** A JSON script holds `rules` and an optional `default`. Each rule matches the
  last `user` message by `contains` or `regex`. The first match wins. If nothing matches, the
  script's default answers, or a built-in default when the script has none.
- **Replies.** A reply sets `content`, `finish_reason` and `usage`, or it sets `fail_status`
  (400 to 599) instead of a body. Either kind can wait `delay_seconds` first.
- **Validation.** Script errors are caught when the script loads. The message names the field, and
  the CLI exits with code 2.
- **Logging.** Each request writes one ASCII line to stderr: the path, the model, the message
  count, the sorted parameter keys, the rule that answered, the delay and the status.
- **No secrets in logs.** The handler reads no header except `Content-Length`, so the
  `Authorization` value is never in scope of any log call. The access log of
  `BaseHTTPRequestHandler` is disabled.
- **Readiness.** `GET /health` answers 200, so E2E runners can wait for the stub.
- **Scripts for later stories.** `tests/e2e/scripts/` holds `example.json`, which has every rule
  kind, and a README with the format and the run recipe.

With the stub in place, a live harness on this machine answers `/v1` and `/query` with 200 again.
Previously, every upstream call failed with TLS or 401 errors, so both returned 502.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Script model, parsing, validation, `select`, last-user subject | `scripts/stub_openrouter.py` | ✅ |
| 2 | Handler, `make_server`, CLI (`--port`, `--script`, `--host`) | `scripts/stub_openrouter.py` | ✅ |
| 3 | Example script and README | `tests/e2e/scripts/example.json`, `tests/e2e/scripts/README.md` | ✅ |
| 4 | Tests against the real `call_openrouter`, no DB | `tests/test_stub_openrouter.py` | ✅ |
| 5 | `-m "not db"` and full regression | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `python scripts/stub_openrouter.py --help` | ✅ exit 0 |
| Example script loads | ✅ 5 rules |
| `tests/test_stub_openrouter.py` | ✅ 38 passed in 2.5 s |
| With `tests/test_openrouter_client.py`, `-m "not db"` | ✅ 121 passed |
| `pytest tests/ -m "not db"` | ✅ 3,456 passed / 26 skipped / 1,425 deselected, 88 s |
| Full suite (throwaway libSQL `:8086`) | ✅ 4,880 passed / 27 skipped, 310 s, no flakes (STORY-013: 4,842 + 38 new) |
| `grep -rn stub_openrouter app/` | ✅ empty (also asserted by a test) |
| Backend import / server start | ✅ uvicorn started for E2E, `/health` 200 |
| Frontend lint | n/a (no frontend in this repo story) |
| E2E | ✅ 10/10 (see below) |

### End-to-end run

Setup:
- Docker Desktop was off at the start. I started it and created a throwaway libSQL on `:8087`,
  then ran `init_db()` and `create-user e2e014 --role admin` before uvicorn started.
- The stub ran as `python scripts/stub_openrouter.py --port 9100 --script tests/e2e/scripts/example.json`.
- uvicorn ran on `:8765` with `OPENROUTER_BASE_URL=http://127.0.0.1:9100/v1`,
  `OPENROUTER_API_KEY=sk-e2e-secret`, `OPENROUTER_TIMEOUT_SECONDS=2` and `V1_ENABLED=true`.

| Check | Result |
|-------|--------|
| Stub `/health` | 200 `{"status": "ok"}` |
| `/v1` "please rename foo" + `temperature`, `max_tokens` | 200, content ``Renamed `foo` to `bar`.``, `finish_reason: length`, usage `12/30/42`, all as scripted |
| `/v1` regex rule ("Hello harness") | scripted answer |
| `/v1` no match | the script's default |
| `/v1` `fail_status: 503` | 502 `upstream_unavailable`, no `x-should-retry` (retryable) |
| `/v1` `fail_status: 400` | 502, `x-should-retry: false` (non-retryable) |
| `/v1` 5 s delay vs 2 s timeout | 502 `upstream_unavailable` after 2.0 s (retryable) |
| `/query` with the rename trigger | 200 `SUCCESS`, scripted content, `tokens_used: 42` |
| Stub log | one ASCII line per request (7). Example: `model='openai/gpt-4o' messages=1 params=[max_tokens,temperature] rule=0 delay=0 -> 200` |
| Secrets in stub output | `sk-e2e-secret`, the user token and `Bearer` each appear 0 times in stdout and stderr |

The first `/query` attempt came back as `BLOCKED: Duplicate query within 24 hours`. The probe had
reused the prompt it had just sent through `/v1`, and the harness's duplicate check works across
both ingresses. This was a probe mistake, not a stub fault. A distinct prompt containing the same
trigger returned 200.

Teardown: I stopped uvicorn and the stub, and `netstat` confirmed nothing was still listening on
`:8765` or `:9100`. I then ran `docker rm -f` on both throwaway containers.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `scripts/stub_openrouter.py` | CREATE | +382 |
| `tests/test_stub_openrouter.py` | CREATE | +409 |
| `tests/e2e/scripts/example.json` | CREATE | +32 |
| `tests/e2e/scripts/README.md` | CREATE | +42 |
| `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-014-stub-upstream.plan.md` | CREATE (archived) | +441 |

## Deviations from Plan

- **More detail in the log line.** The log line also records the request path, `delay=` and the
  response status (`-> 503`). This lets a reader of an E2E log see which fault was injected. It
  still carries no content and no headers.
- **More tests than planned.** The plan listed 14 cases. Parametrization (16 bad scripts, 503 and
  429) and four small additions bring the count to 38. The additions are parts-list content,
  `/health` with no log line, the response-body shape, and a missing script file exiting with
  code 2.
- **Faster test teardown.** The test fixture passes `poll_interval=0.05` to `serve_forever`, so
  each `shutdown()` at teardown takes about 50 ms instead of 0.5 s. The file run dropped from
  about 10 s to 2.5 s. This change was made on disk after the first green run, and I kept it.
- **A test-source literal.** `test_log_is_ascii_and_never_carries_message_content` now spells its
  non-ASCII input as literal characters rather than `\u` escapes. The file is UTF-8. Behaviour is
  identical, and the assertion is on the log, which stays ASCII.
- **The `/query` E2E prompt.** I changed the prompt to avoid the harness's duplicate check, as
  described above.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_stub_openrouter.py` | The scripted result through `call_openrouter`. The log line's model, message count and parameter keys. An ASCII-only log that never carries content. Matching only the last user message. Regex matching with first-match-wins. The configured default. The built-in default. Parts-list content. Delay beyond the timeout is retryable with `upstream_status=None`. Delay within the timeout answers. 400 is non-retryable. 503 and 429 are retryable. The `Authorization` value is never logged on any path (StringIO and `capfd`). A bad body or wrong path leaves the server serving. `/health`. The response shape. 16 bad-script rejections that name the field. The example script loads with every rule kind. The CLI serves on `--port 0` (the AC's literal command). The CLI exits 2 on a bad or missing script. Nothing under `app/` mentions the stub |

## Acceptance Criteria

- [x] Given `python scripts/stub_openrouter.py --port 9100 --script <file>`, when the harness runs with `OPENROUTER_BASE_URL=http://127.0.0.1:9100/v1`, then a `/v1` request is answered with the scripted content, `finish_reason` and `usage`, and the stub logs (ASCII only) each received request's model, message count and parameter keys.
- [x] Given a script rule matching on the last user message (substring or regex), when a request matches, then its response is used; given no match, then a configurable default; rules can set `delay_seconds` and `fail_status` (e.g. 503, 400) instead of a body.
- [x] Given the stub's own test, when it runs, then `call_openrouter` against the stub returns the scripted result, a `delay_seconds` rule exceeding `OPENROUTER_TIMEOUT_SECONDS` raises a retryable `OpenRouterError`, and a `fail_status: 400` raises a non-retryable one.
- [x] Given the stub, when it receives an `Authorization` header, then it never logs the header's value.
- [x] All tasks completed
- [x] `-m "not db"` and full suites pass
- [x] No new dependency; nothing in `app/` imports the stub
- [x] Follows existing patterns
