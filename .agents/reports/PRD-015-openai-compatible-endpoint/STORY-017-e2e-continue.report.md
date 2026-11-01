---
story: STORY-017
prd: PRD-015
plan: .agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-017-e2e-continue.plan.md
epic_branch: epic/PRD-015-openai-compatible-endpoint
commit: d64774d
status: COMPLETE
completed: 2026-10-30
---

# Implementation Report — STORY-017: E2E: Continue chat through the harness

**Plan**: `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-017-e2e-continue.plan.md`
**Epic Branch**: `epic/PRD-015-openai-compatible-endpoint`
**Commit**: `d64774d`

## Summary

`tests/e2e/test_continue.py` runs Continue's own CLI, **`@continuedev/cli` 1.5.47** (`cn`), in **headless mode** (`cn -p "<prompt>" --config <file>`) against a live harness on the stub upstream. **This is the headless CLI run, not a manual VS Code run**, so there are no screenshots. The config is PRD Section 10's model entry, plus `requestOptions.headers` carrying `X-Harness-Device`.

- **Chat (AC 1).** The stub's answer is printed exactly. The row has `ingress='v1'`, `profile='code'`, `streamed=1` (equal to the request's `stream: true`) and `device` equal to the header's value.
- **Block (AC 2).** An injection phrase makes `cn` print `{"status":"error","message":"400 Suspicious pattern detected: ignore previous instructions"}` and exit 1. It sends one request, which writes one row.
- **Paths (AC 3).** `cn` 1.5.47 calls exactly one `/v1` path, `POST /v1/chat/completions`. It never calls `/v1/models` or `/v1/models/{id}`, so there is nothing there to fail.
- **Tools (AC 4, PRD Risk 2).** **Continue sends `tools` in chat by default.** `cn` is an agent, and both its default mode and `--readonly` send its built-in tools, which `/v1` refuses with 400 `tools_not_supported`. **`--exclude "*"`** makes it send `tools: []`, an accepted default, so chat becomes text-only. STORY-019 must document this flag.
- **Keep-alives (PRD Risk 1).** A 20 s stub delay with `V1_SSE_KEEPALIVE_SECONDS=2` delivered **10 `: keep-alive` lines** to Continue's own SSE parser, which is not the OpenAI SDK's. The answer then arrived intact (21.1 s).

The recording proxy in `tests/e2e/_live.py` now logs each call's `status` and the `keepalives` it relayed, and it forwards `X-Harness-Device`, recording only that it was present. No file under `app/` changed.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Pin Continue's CLI; install outside the repo | `tests/e2e/continue/package.json`, `package-lock.json`, `requirements-e2e.txt` | ✅ |
| 2 | Spike: run `cn` by hand, record what it sends | (research, below) | ✅ |
| 3 | Recorder: `status`, `keepalives`, `device_header`; forward the device header | `tests/e2e/_live.py`, `tests/test_e2e_live.py` | ✅ |
| 4 | Stub script + README | `tests/e2e/scripts/continue.json`, `tests/e2e/scripts/README.md` | ✅ |
| 5 | Module: constants, fixtures, runner | `tests/e2e/test_continue.py` | ✅ |
| 6 | The tests | `tests/e2e/test_continue.py` | ✅ |
| 7 | Regression | none | ✅ |

## Continue version, install and config (AC 4)

- `npm view @continuedev/cli version` gave `1.5.47` (`latest`) on 2026-10-30. The bundle is a single `dist/index.js`, and the `cn` bin is `dist/cn.js`.
- **Node** v24.21.0, npm 12.2.0. `node` comes from `PATH`, and its version is recorded in `continue-run.json`.
- **Install, outside the repo.** The commands were `cp tests/e2e/continue/package*.json C:/Users/tobip/.venvs/continue-e2e/` and then `npm ci --prefix C:/Users/tobip/.venvs/continue-e2e`: 12 packages, 84 MB, about 1 s from cache. npm needed no TLS workaround. No `node_modules` is in the repo. The module finds the install through **`HARNESS_E2E_CONTINUE`** (the install directory). It checks the installed version against the pin and runs `node <dist/cn.js>` directly, not the `cn.cmd` shim.
- **Command** (the token lives only in the config file, which is deleted at teardown):

  ```
  node <continue-e2e>/node_modules/@continuedev/cli/dist/cn.js
    -p "E2E-CONTINUE-CHAT [<nonce>-chat] what is the capital of France?"
    --config <continue home>/config-chat.yaml
    --exclude "*"
  ```

  The env sets `HOME`/`USERPROFILE=<continue home>`, `CONTINUE_GLOBAL_DIR=<continue home>/.continue`, `CONTINUE_CLI_ENABLE_TELEMETRY=0`, `CONTINUE_METRICS_ENABLED=0`, `NO_COLOR=1`, `FORCE_COLOR=0`, `CI=1` and `NODE_OPTIONS=--use-system-ca`. Every inherited `OPENAI_*`, `OPENROUTER_*`, `ANTHROPIC_*`, `CONTINUE_*` and `AIDER_*` variable is removed. The cwd is a throwaway directory holding one `README.md`, and stdin is `DEVNULL`.
- **`config.yaml`** (PRD Section 10, with only the base, token and device being the test's):

  ```yaml
  name: e2e017
  version: 1.0.0
  schema: v1
  models:
    - name: harness-gpt-4o
      provider: openai
      model: openai/gpt-4o
      apiBase: <recorder>/v1
      apiKey: <harness token>
      roles: [chat, edit]
      requestOptions:
        headers:
          X-Harness-Device: e2e017-<nonce>
  ```

## Task 2 spike: what `cn` sends

The spike was a scratch server (stub, harness and recorder kept up, plus a `cn` runner) against a throwaway libSQL on `:8088`.

| Question | Observed (1.5.47) |
|---|---|
| `cn --help` | `-p/--print`, `--config`, `--readonly`, `--exclude <tool>` (repeatable), `--format json`, `--silent` all exist |
| Model received for `model: openai/gpt-4o` | `openai/gpt-4o`, **verbatim** (unlike litellm/Aider). `model: gpt-4o` arrives as `gpt-4o` |
| Keys of a chat request | `messages, model, stream, stream_options, tools`, with `stream: true` and `stream_options: {include_usage: true}`. No `temperature`, `max_tokens`, `tool_choice`, `functions` or `user` |
| Messages | 2 turns, `system` then `user`, keys `role`/`content` only. The last role is `user` |
| `tools`, default mode | **non-empty**, giving 400 `tools: tool calling is not supported (PRD-016)`, no row, exit 1 |
| `tools`, `--readonly` | **non-empty** (the read-only tools), same 400 |
| `tools`, `--exclude "*"` | **`[]`**, accepted, answered, exit 0. The plan's ladder stopped here (option 3); options 4 and 5 weren't needed |
| Requests per `-p` run | 1. No title or summary call, and no `/v1/models` or `/v1/models/{id}` call |
| Block (400 `suspicious_pattern`) | One POST, stderr `{"status":"error","message":"400 Suspicious pattern detected: ignore previous instructions"}`, exit 1 |
| 403 (`model: gpt-4o`, not on the allowlist) | One POST, stderr `{"status":"error","message":"403 Model not permitted for this role: query:model:gpt-4o"}`, exit 1. **Not retried**, unlike Aider |
| Output | `-p` prints the answer alone on stdout, with a trailing newline. `--format json` wraps it: `{"response": "...", "status": "success", "note": "Response was not valid JSON, ..."}` |
| Env read (grepped from `dist/index.js`) | `CONTINUE_GLOBAL_DIR` (else `~/.continue`), `CONTINUE_CLI_ENABLE_TELEMETRY` / `CONTINUE_METRICS_ENABLED` (metrics only export when an OTEL endpoint is set), `CONTINUE_API_BASE` (default `https://api.continue.dev/`). `cn` also runs `dotenv.config()`, so it **loads a `.env` from its cwd**, and it reads `~/.claude/settings.json` and `<cwd>/.claude/settings.json` for hooks. Hence the throwaway cwd and home |
| Network | Every run finished in about 1 s, with and without `NODE_OPTIONS=--use-system-ca`. There was no hub, update or telemetry stall behind the TLS interception |
| Files `cn` writes under its home | `.continue/logs/cn.log`, `.continue/permissions.yaml`, and `.continue/sessions/<id>.json` + `sessions.json` (the conversation) after a successful answer. **None contains the token** (grepped; also asserted by `test_zz`) |
| Retry source | The bundle's retry wrapper (`maxRetries` default 2) retries only errors marked `isRetryable`. The observed 400 and 403 were each sent once. The minified bundle has no stable file:line to quote, so the evidence is the recorder's count: one POST per refused prompt |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK (no `app/` change) |
| `tests/test_e2e_live.py` | ✅ 22 passed (18 + 4 new) |
| `pytest tests/e2e` without the flag | ✅ 30 skipped (`e2e: pass --run-e2e`), no errors |
| `-m "not db"` (Docker-free, `HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:9`) | ✅ 3,491 passed / 56 skipped in 91 s (STORY-016: 3,487 / 50) |
| Full suite (throwaway libSQL `:8086`) | ✅ 4,915 passed / 57 skipped in 342 s, 0 `libsql verdict` lines (STORY-016: 4,911 / 51) |
| E2E `test_continue.py` (`:8088`) | ✅ 6/6 in 37.9 s |
| E2E second run, same container | ✅ 6/6 in 38.2 s |
| E2E all three modules | ✅ 30/30 in 163 s |
| `git diff --stat HEAD -- app/` | ✅ empty |
| Frontend lint | n/a (no UI) |

## End-to-end run

The commands, exactly as run (Git Bash, harness venv Python). Docker Desktop was started first:

```bash
docker run -d --name harness-libsql-e2e017 -p 8088:8080 -e SQLD_NODE=primary ghcr.io/tursodatabase/libsql-server:latest
HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088 HARNESS_E2E_CONTINUE=C:/Users/tobip/.venvs/continue-e2e \
  python -m pytest tests/e2e/test_continue.py -m e2e --run-e2e -v -p no:cacheprovider
HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088 HARNESS_E2E_CONTINUE=C:/Users/tobip/.venvs/continue-e2e \
  HARNESS_E2E_AIDER=C:/Users/tobip/.venvs/aider-e2e/Scripts/aider.exe \
  python -m pytest tests/e2e -m e2e --run-e2e -v -p no:cacheprovider
docker rm -f harness-libsql-e2e017
```

| Run | Result |
|---|---|
| Continue module, first | ✅ 6 passed in 37.9 s (39 s wall) |
| Continue module, same container again | ✅ 6 passed in 38.2 s. The nonce isolates the runs |
| All three modules | ✅ 30 passed in 163 s. The recorder change left STORY-015/016 green |
| Control 1: `HARNESS_E2E_CONTINUE` unset, then an empty dir | ❌ as intended: 6 setup errors in 0.3 s, `HARNESS_E2E_CONTINUE is not set. Install the pinned Continue CLI: cp tests/e2e/continue/package*.json ...` (and `has no @continuedev/cli: ...`). No child starts |
| Control 2: `requestOptions.headers` removed from the template (local, restored byte for byte) | ❌ as intended: the chat test fails on `post["device_header"] is True`, so the device assertion is live |
| Control 3: `V1_SSE_KEEPALIVE_SECONDS=60` (local, restored) | ❌ as intended, on `keepalives >= 5` (0). Exit 0 and the full answer had already been asserted, so **Continue tolerates 20 s with no byte at all**; no first-byte timeout showed up |
| After the runs | 0 `uvicorn`/`stub_openrouter`/`cn.js` processes (`Get-CimInstance Win32_Process`). Harness ports closed (fixture assertion). `harness-libsql-e2e017` and `harness-libsql-full017` removed |

### Requests Continue sent (recorder log, first run; names only)

| Test | Exit | Calls | Keys | tools | Status | Keep-alives | Device header | Upstream rule |
|---|---|---|---|---|---|---|---|---|
| chat | 0 | `POST /v1/chat/completions` | `messages, model, stream, stream_options, tools` | `[]` | 200 | 0 | yes | `1` (chat) |
| slow | 0 | same | same | `[]` | 200 | **10** | yes | `0` (slow, 20 s) |
| block | 1 | same | same | `[]` | 400 | 0 | yes | none |
| default mode (no `--exclude`) | 1 | same | same | **non-empty** | 400 | 0 | yes | none |

`continue-run.json["v1_paths"]` = `["POST /v1/chat/completions"]`.

### Audit rows produced (first run; `rows.json`, no tokens or prompt text)

| id | user | success | streamed | ingress/profile | device | model | tokens | ignored_params | verdict |
|---|---|---|---|---|---|---|---|---|---|
| 1 | chat | True | True | v1/code | `e2e017-16e2803c` | openai/gpt-4o | 35 | NULL | - |
| 2 | slow | True | True | v1/code | `e2e017-16e2803c` | openai/gpt-4o | 29 | NULL | - |
| 3 | block | True | True | v1/code | `e2e017-16e2803c` | - | - | NULL | pattern=ignore previous instructions |

The default-mode `tools` refusal wrote no row (a shape refusal). **`ignored_params` names: none.** Continue sends nothing the harness ignores: `stream_options.include_usage` is read, and `tools: []` is an accepted default.

## Findings (for STORY-019 and the PRD)

1. **Continue's CLI needs `--exclude "*"` for `/v1`.** Without it, every prompt is 400 `tools_not_supported` (PRD Risk 2, now observed). `--readonly` isn't enough. The per-client README should show the flag and the error it prevents. **Not verified here:** the VS Code extension's Chat mode, which this story didn't need, because the CLI route worked (PRD Section 8 allows either).
2. **Continue sends `model` verbatim.** The README's `model: openai/gpt-4o` works as written. No prefix trick is needed, unlike Aider's `openai/openai/gpt-4o`.
3. **Continue doesn't retry a 400 or a 403**, so one refusal writes one row. That contrasts with Aider's litellm, which retries a 403 about 9 times (STORY-016 Finding 1). PRD story 6's "shows it and stops" holds for Continue.
4. **Continue's own SSE parser handles keep-alive comments**: 10 of them before the content, then a correct answer. It also waited out 20 s of silence with keep-alives effectively off (Control 3). PRD Risk 1 is satisfied for Continue directly. STORY-018 still covers the Caddy leg.
5. **`cn` loads `.env` from its cwd and `~/.claude/settings.json` hooks.** Worth a line in the setup docs: a developer's project `.env` can feed `cn` variables.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/e2e/continue/package.json` | CREATE | +8 |
| `tests/e2e/continue/package-lock.json` | CREATE | +399 |
| `requirements-e2e.txt` | UPDATE | +3/-1 |
| `tests/e2e/_live.py` | UPDATE | +28/-9 |
| `tests/test_e2e_live.py` | UPDATE | +46/-1 |
| `tests/e2e/scripts/continue.json` | CREATE | +22 |
| `tests/e2e/scripts/README.md` | UPDATE | +3/-1 |
| `tests/e2e/test_continue.py` | CREATE | +485 |
| `.agents/plans/.../completed/STORY-017-e2e-continue.plan.md` | CREATE (archived) | +389 |

## Deviations from Plan

1. **Four recorder unit tests instead of three.** `test_the_recorder_counts_one_keep_alive_on_the_plain_stream` covers the single-chunk case next to the split-chunk one. The existing `test_the_recorder_forwards_get_and_logs_it_apart_from_posts` now expects the new entry fields (`status`, `keepalives`, `device_header`), because the helper's behaviour changed by design.
2. **The trailing partial line isn't counted** in `keepalives`. Only complete lines are counted, before each chunk is relayed, so the count is final by the time the client has the bytes. SSE comment lines always end in a newline.
3. **The Decision 3 ladder stopped at option 3** (`--exclude "*"`). Options 4 (capabilities override) and 5 (system-message tools) weren't tried. The manual VS Code fallback wasn't needed, so there are no screenshots in `docs/screenshots/`.
4. **The CLI's retry policy is evidenced by behaviour, not file:line.** The plan asked for a source quote, but the package ships one minified 13 MB bundle. The recorder's one-POST count for the 400 and the 403 is the evidence, and `test_a_blocked_message_shows_the_reason_and_is_sent_once` pins it.
5. **`users` has four labels (`chat`, `slow`, `block`, `tools`)** instead of the plan's three, so the slow test's row delta is its own.
6. **`test_zz` also asserts that no file Continue wrote under its home holds a token.** This came from the spike's file listing.
7. **The block test asserts `returncode != 0`.** `cn -p` exits 1 on an error, while the plan only recorded the code.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/e2e/test_continue.py` (6, opt-in) | Chat answer printed + v1/code/streamed/device row, `ignored_params` NULL. Slow answer across 10 keep-alives. Block: reason printed, exit 1, one POST, one row. Default mode sends tools: 400 by name, no row. Every `/v1` path recorded, `/v1/models*` 200. Every row v1/code/device, and no token in Continue's files |
| `tests/test_e2e_live.py` (+4, 22 total) | Status logged for GET and POST. Keep-alive lines counted across a chunk boundary. One keep-alive on a plain stream. Device header forwarded, only its presence recorded. (The GET log test updated for the new fields) |

## Acceptance Criteria

- [x] Continue configured with the PRD Section 10 `config.yaml` entry (provider `openai`, `apiBase` the harness `/v1`, `apiKey` a harness token): the stub's answer is shown, and the row has `ingress='v1'`, `profile='code'` and `streamed=1`, equal to the request's `stream: true`
- [x] A blocked message: Continue shows `400 Suspicious pattern detected: ignore previous instructions` and doesn't resend it (one POST, one row)
- [x] Model discovery and startup: 1.5.47 calls no `/v1/models` or `/v1/models/{id}` path (asserted 200 if it did). The only `/v1` path called, `POST /v1/chat/completions`, is recorded
- [x] The report records the pinned version (`@continuedev/cli` 1.5.47, Node v24.21.0), the mode (**headless CLI**, no manual run, no screenshots), and that Continue **sends `tools` in chat mode by default**, with `--exclude "*"` as the fix
- [x] Keep-alive lines reach Continue's parser during a 20 s stub delay (10 lines, answer intact)
- [x] The row's `device` equals the `X-Harness-Device` set through `requestOptions.headers`
- [x] All tasks completed
- [x] `-m "not db"` and the full suite pass, and `tests/e2e` is skipped by default
- [x] No file under `app/` changed
- [x] Follows existing patterns
