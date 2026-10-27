---
story: STORY-014
prd: PRD-015
slug: stub-upstream
title: "Scripted stub upstream for E2E runs"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-015-openai-compatible-endpoint
created: 2026-10-26
---

# Plan: Scripted stub upstream for E2E runs

## Summary

Add `scripts/stub_openrouter.py`, a standard-library HTTP server (`http.server.ThreadingHTTPServer`)
that answers `POST .../chat/completions` from a JSON script file. Each rule matches on the **last
`user` message** (substring or regex). The first matching rule wins, and the script's `default`
answers when none match. A rule either returns a body (`content`, `finish_reason`, `usage`) or fails
with `fail_status`, optionally after `delay_seconds`. Every request logs one ASCII line to stderr: the
model, the message count, the sorted parameter keys and the rule that answered. Headers are never
logged.

The harness reaches the stub through the existing `OPENROUTER_BASE_URL` setting (STORY-002,
`app/config.py:240`, loopback http already allowed at `app/config.py:83-86`). Nothing under `app/`
changes. The module exposes `load_script()` and `make_server()` so `tests/test_stub_openrouter.py`
can run it in a thread on an ephemeral port and drive it with the real `call_openrouter`. One example
script lands in `tests/e2e/scripts/` for STORY-015 to STORY-018.

## User Story

As the engineer running the client E2E stories
I want a local upstream that speaks enough Chat Completions to answer from a script
So that real clients can be driven end to end through a live harness on a machine where OpenRouter cannot be reached

## Story Reference

- Story file: `.agents/stories/PRD-015-openai-compatible-endpoint/STORY-014-stub-upstream.md`
- PRD: `.agents/PRDs/PRD-015-openai-compatible-endpoint/PRD.md` (Sections 7.9, 14 Risk 7, 15 D10)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (test tooling, not shipped behaviour) |
| Complexity | MEDIUM |
| Systems Affected | `scripts/`, `tests/`, `tests/e2e/scripts/` (new). `app/` untouched |
| Story | STORY-014 |
| PRD | PRD-015 |
| Epic Branch | `epic/PRD-015-openai-compatible-endpoint` (commit directly on this branch) |
| Depends on | STORY-002 (done, `f4f2a83`) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| none | The story says "Skills: none applicable". `.agents/skills/` holds only `frontend-design`, and this story has no UI | — |

---

## Patterns to Follow

### Stub HTTP server in tests (the direct precedent)
```python
# SOURCE: tests/test_pipeline_concurrency.py:516-575, 604-614
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

class _SlowHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler's spelling
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        ...
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep pytest output clean
        pass

server = ThreadingHTTPServer(("127.0.0.1", port), _SlowHandler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
monkeypatch.setattr(settings, "OPENROUTER_BASE_URL", f"http://127.0.0.1:{port}/v1")
```
The stub binds port 0 and reads `server.server_address[1]`. That avoids `_free_port`'s
bind-release-rebind race.

### Script module shape (docstring-first, argparse, `main(argv) -> int`)
```python
# SOURCE: scripts/manage_users.py:138-191
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="manage_users.py")
    ...
def main(argv: Optional[Sequence[str]] = None) -> int:
    ...
if __name__ == "__main__":
    raise SystemExit(main())
```
The module docstring explains why the script exists, in the style of `scripts/measure_usage_latency.py:1-55`.
Here it also says the stub is a test tool (PRD 7.9) that `app/` never imports.

### The client contract the stub must satisfy
```python
# SOURCE: app/services/openrouter_client.py (call_openrouter)
url = f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"
content = data["choices"][0]["message"]["content"]          # required
finish_reason = choice.get("finish_reason")                  # optional str
tokens_used = data["usage"]["total_tokens"]                  # required
input_tokens = _token_count(usage.get("prompt_tokens"))      # optional
# _classify_http_error: HTTPStatusError -> (status, status >= 500 or status == 429)
#                       TransportError (incl. timeouts) -> (None, True)
```

### Error handling
- Script errors are found when the script loads, not when a request arrives. `load_script` raises
  `ScriptError(ValueError)` with a message that names the rule index and the field. `main` prints
  `stub_openrouter: <message>` to stderr and returns 2, which matches argparse's usage-error code.
- Request-time faults: a non-JSON body or missing `messages` returns 400 with an OpenRouter-shaped
  `{"error": {"message", "code"}}`. A path that does not end in `/chat/completions` returns 404.
- When the client hangs up during a delay, the late write raises `BrokenPipeError`,
  `ConnectionResetError` or `ConnectionAbortedError` (on Windows). The handler catches these and
  ignores them.

### Tests
```python
# SOURCE: tests/test_measure_usage_latency.py:11-20 and tests/test_openrouter_client.py:1-15
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
import pytest
from app.config import settings
...
monkeypatch.setattr(settings, "OPENROUTER_TIMEOUT_SECONDS", 7.5)   # test_openrouter_client.py:177
```
No storage fixture and no `db` marker are used, so the module runs under `-m "not db"` with Docker off.

---

## Design

### Script format (JSON)

```json
{
  "default": {"content": "stub default answer", "finish_reason": "stop"},
  "rules": [
    {"contains": "rename foo", "content": "...edit...", "finish_reason": "stop",
     "usage": {"prompt_tokens": 12, "completion_tokens": 30}},
    {"regex": "(?i)^slow\\b", "delay_seconds": 5, "content": "late"},
    {"contains": "upstream down", "fail_status": 503},
    {"contains": "bad request", "fail_status": 400}
  ]
}
```

- Top-level keys are `rules` (a list, optional, empty by default) and `default` (optional). Any other
  key is a `ScriptError`.
- Each rule has exactly one matcher, `contains` (a case-sensitive substring) or `regex` (`re.search`,
  compiled at load). The `default` has no matcher.
- Response keys are shared by rules and the default:
  - `content` (str, default `""`)
  - `finish_reason` (str or null, default `"stop"`)
  - `usage` (an object with optional `prompt_tokens`, `completion_tokens` and `total_tokens`, each a
    non-negative int; defaults to `{1, 1}`, and `total_tokens` defaults to the sum)
  - `delay_seconds` (a number >= 0, default 0)
  - `fail_status` (an int from 400 to 599). When it is set, the body keys are not allowed. Mixing
    them is a `ScriptError`, because a fail rule has no body.
- When the script has no `default`, a built-in one answers `"stub_openrouter: no rule matched"` with
  `finish_reason: "stop"`. A request with no match therefore still succeeds visibly.
- The match subject is the content of the last message whose `role == "user"`. A non-string content
  (a parts list) is joined from its `text` parts. When there is no user message, the subject is `""`.

### Response

The response is `200` with `{"id": "chatcmpl-stub-<n>", "object": "chat.completion", "created": <int>,
"model": <request model>, "choices": [{"index": 0, "message": {"role": "assistant", "content": ...},
"finish_reason": ...}], "usage": {...}}`. A fail rule returns `fail_status` with
`{"error": {"message": "stub_openrouter: scripted failure", "code": <status>}}`. The delay is a
`time.sleep` in the handler thread before either reply. `daemon_threads = True`, so a sleeping
handler never blocks shutdown.

### Log line (stderr, one per request, ASCII only)

```
stub_openrouter: POST /v1/chat/completions model='openai/gpt-4o' messages=3 params=[max_tokens,temperature] rule=1 -> 200
```

- `params` lists the sorted request keys other than `model` and `messages`.
- `rule` is the zero-based index or `default`.
- The line is built with `ascii()` for the model and `str.encode("ascii", "backslashreplace")` for
  the final line. A non-ASCII model name, or a key a client invents, cannot break a cp1252 console
  (see memory: ASCII-only test output).
- Message content is never logged.
- `log_message` is overridden to a no-op, so `BaseHTTPRequestHandler`'s own access log does not run.
- The handler never reads `self.headers` except for `Content-Length`. The `Authorization` value is
  therefore never in scope of any log call. The test asserts this rather than relying on it.
- `make_server(..., log=stream)` takes the stream, `sys.stderr` by default, so tests capture it
  directly without `capsys` threading issues.
- `GET /health` returns `200 {"status":"ok"}` without logging, so E2E stories can poll for readiness.

### Public surface

```python
class ScriptError(ValueError): ...
@dataclass(frozen=True) class Reply: content, finish_reason, usage, delay_seconds, fail_status
@dataclass(frozen=True) class Rule: contains | pattern, reply
@dataclass(frozen=True) class Script: rules, default;  def select(subject) -> tuple[str, Reply]
def parse_script(raw: Any) -> Script
def load_script(path) -> Script            # json.load (utf-8) + parse_script
def make_server(script, host="127.0.0.1", port=0, log=None) -> ThreadingHTTPServer
def main(argv=None) -> int                  # --port (required), --script (required), --host (default 127.0.0.1)
```

`main` prints `stub_openrouter: listening on http://<host>:<port>/v1` to stdout with `flush=True`,
then calls `serve_forever()`. It handles `KeyboardInterrupt` and returns 0. Because the line carries
the real bound port, `--port 0` works for the subprocess test.

### Files

| File | Action | Purpose |
|------|--------|---------|
| `scripts/stub_openrouter.py` | CREATE | The stub: script parsing, selection, handler, `make_server`, CLI |
| `tests/e2e/scripts/example.json` | CREATE | One example script: a substring rule, a regex rule, a delay rule, a 503 and a 400, plus a default |
| `tests/e2e/scripts/README.md` | CREATE | A short format reference and the run command. STORY-015 to STORY-018 add their scripts here |
| `tests/test_stub_openrouter.py` | CREATE | ACs 1 to 4, against the real `call_openrouter`, no DB |

No `tests/e2e/__init__.py`, because the directory holds data, not tests. pytest only collects
`test_*.py`, and the JSON/MD files are invisible to it.

### Risks and mitigations

| Risk | Mitigation |
|------|------------|
| A delayed handler outlives the test and writes to a closed socket, so a traceback lands in stderr | Catch the three connection errors around the write. `daemon_threads = True`. Call `server.shutdown(); server.server_close()` in a fixture finalizer |
| The timeout test is slow or flaky | `OPENROUTER_TIMEOUT_SECONDS=0.3` with `delay_seconds=3`, bounded by a `time.monotonic()` assertion that the call returned in under 2 s |
| `_free_port` race | Bind port 0 inside `make_server` |
| The repo is CRLF (memory, STORY-007) | Create the files with the Write tool. Do not append with heredocs |
| Something under `app/` starts importing the stub | A test greps `app/**/*.py` for `stub_openrouter` |
| A non-`db` test reaching storage trips the PRD-014 guard | The stub test imports only `app.config`, `app.models.messages` and `app.services.openrouter_client`. None of them opens a connection |
| Handoff guards (`test_no_route_accepts_messages_params_or_system`, `_PRE_EPIC_UNTOUCHED_TESTS`) | Neither is affected: no new route and no pre-epic test edited. The full run confirms it |

---

## Tasks

Execute in order. Each task is atomic and verifiable. The venv is `C:/Users/tobip/.venvs/harness-ai/Scripts/python.exe`
(written as `$PY` below). Run from the `harness-ai` repo root.

### Task 1: Script model and parsing

- **File**: `scripts/stub_openrouter.py`
- **Action**: CREATE
- **Implement**:
  - The module docstring, which says it is a test tool for E2E (PRD-015 7.9, Risk 7, D10), that it
    is not shipped behaviour, and that nothing in `app/` imports it. Include the usage lines and the
    script format summary.
  - Use standard-library imports only: `argparse, json, re, sys, threading, time, dataclasses,
    http.server, itertools`.
  - Add `ScriptError`, `Reply`, `Rule`, `Script`, `parse_script` and `load_script`, following the
    Design section. Validation rejects:
    - unknown keys (top level, rule and usage)
    - both or neither of `contains` and `regex` on a rule
    - a `regex` that does not compile (the message names the rule index and `re.error`)
    - a non-str `content`
    - a `finish_reason` that is neither str nor null
    - usage values that are not non-negative ints (`bool` rejected, mirroring `_token_count`)
    - `delay_seconds` that is negative or not a number
    - a `fail_status` outside 400 to 599, or combined with `content`, `finish_reason` or `usage`
  - `Script.select(subject)` returns `(label, reply)`. The label is `"0"`, `"1"` and so on, or
    `"default"`.
  - Add `_last_user_text(messages)`, following the Design section.
- **Mirror**: the docstring style of `scripts/measure_usage_latency.py:1-55`, and the
  bool-is-int guard in `app/services/openrouter_client.py` (`_token_count`).
- **Validate**: `$PY -c "import scripts.stub_openrouter as s; print(s.parse_script({'rules': []}).select('x'))"`

### Task 2: Handler, server factory and CLI

- **File**: `scripts/stub_openrouter.py`
- **Action**: UPDATE
- **Implement**:
  - `_StubHandler(BaseHTTPRequestHandler)`, with `script` and `log` bound per server through a
    subclass that `make_server` creates. A class attribute keeps two servers in one process
    independent.
  - `do_POST`:
    - A path that does not end in `/chat/completions` returns 404.
    - Read `Content-Length` bytes and parse the JSON. A bad body returns 400.
    - `messages` must be a list, or the request gets 400.
    - Select a reply, write the log line, sleep `delay_seconds`, then send the fail or success body.
      Connection errors are swallowed.
  - `do_GET /health` returns 200. Any other GET returns 404.
  - `log_message` is a no-op.
  - The log write goes through a `threading.Lock` so concurrent lines do not interleave.
  - A request counter (`itertools.count`) builds the `id`.
  - `make_server` sets `ThreadingHTTPServer.daemon_threads = True` on a subclass and returns the
    server, not yet serving.
  - `_build_parser` and `main(argv)`, following the Design section. Script errors and an unreadable
    file print `stub_openrouter: ...` and return 2.
  - `if __name__ == "__main__": raise SystemExit(main())`.
- **Mirror**: `tests/test_pipeline_concurrency.py:522-575` for the handler, and
  `scripts/manage_users.py:138-191` for the CLI.
- **Validate**: run `$PY scripts/stub_openrouter.py --help`. It exits 0, and the help shows
  `--port`, `--script` and `--host`.

### Task 3: Example script and README

- **Files**: `tests/e2e/scripts/example.json`, `tests/e2e/scripts/README.md`
- **Action**: CREATE
- **Implement**:
  - `example.json` has a default, a `contains` rule with explicit `usage` and `finish_reason:
    "length"`, a `regex` rule, a `delay_seconds` rule, a `fail_status: 503` rule and a
    `fail_status: 400` rule.
  - The README is short: what the directory is, the format (copied from the Design table), and the
    two-terminal run recipe:
    `python scripts/stub_openrouter.py --port 9100 --script tests/e2e/scripts/example.json`, then
    start the harness with `OPENROUTER_BASE_URL=http://127.0.0.1:9100/v1`.
  - The README says that the harness still sends its `OPENROUTER_API_KEY` and the stub ignores it,
    so any non-empty value works.
- **Validate**: `$PY -c "import scripts.stub_openrouter as s; print(len(s.load_script('tests/e2e/scripts/example.json').rules))"`

### Task 4: Tests

- **File**: `tests/test_stub_openrouter.py`
- **Action**: CREATE
- **Implement**:
  - A module docstring that maps the tests to the ACs.
  - The env `setdefault` header, as in the Tests pattern.
  - A fixture `stub(monkeypatch)` returns a factory. Given a script dict, the factory calls
    `parse_script`, then `make_server(log=io.StringIO())`, starts a daemon thread and monkeypatches
    `settings.OPENROUTER_BASE_URL` to `http://127.0.0.1:<port>/v1`. It returns `(server, log)`. The
    finalizer runs `shutdown()` and `server_close()`.
  - Tests:
    1. **AC 1 and AC 3: the scripted result.** `call_openrouter([Message("user", "rename foo please")], model="m/x", api_key="sk-test")`
       returns the scripted `response`, `finish_reason == "length"`, `tokens_used`, `input_tokens`
       and `output_tokens`.
    2. **AC 1: the log line.** The request carries `GenerationParams(temperature=0.2, max_tokens=50)`
       and two messages. The log has one line containing `model='m/x'`, `messages=2`,
       `params=[max_tokens,temperature]` and `rule=0`. The whole log is `str.isascii()`.
    3. **AC 1: ASCII for non-ASCII input.** A model name and message content with non-ASCII
       characters still produce an ASCII-only log. The content never appears in the log.
    4. **AC 2: the match subject is the last user message.** An earlier user turn that contains the
       trigger does not match when the last user turn does not. A trailing assistant turn is skipped
       when the subject is chosen.
    5. **AC 2: regex.** A `regex` rule matches through `re.search`. The first matching rule wins
       over a later one.
    6. **AC 2: defaults.** With no match, the configured default answers. With no `default` key, the
       built-in default answers.
    7. **AC 3: retryable timeout.** Set `OPENROUTER_TIMEOUT_SECONDS=0.3` and use a
       `delay_seconds: 3` rule. The call raises `OpenRouterError` with `retryable is True` and
       `upstream_status is None`, and returns in under 2 s.
    8. **AC 3: non-retryable 400.** A `fail_status: 400` rule raises with `retryable is False` and
       `upstream_status == 400`. A parametrized companion runs 503 and 429 and expects
       `retryable is True`.
    9. **AC 4: the key is never logged.** Use `api_key="sk-secret-STORY014"`, then run the success,
       fail and delay rules and a raw `httpx.post` with a bad JSON body. The secret and the string
       `Bearer` appear nowhere in the log. Assert this on the captured stream, and also through
       `capfd` (for anything written straight to fd 2).
    10. **Script validation.** A parametrized test feeds `parse_script` bad scripts (both matchers,
        neither matcher, a bad regex, `fail_status` 200, `fail_status` with `content`, a negative
        delay, `True` as a token count, an unknown key). Each raises `ScriptError`, and the message
        names the offending field.
    11. **The example loads.** `load_script("tests/e2e/scripts/example.json")` succeeds and has at
        least one rule of each kind.
    12. **CLI subprocess (AC 1's literal command).** `subprocess.Popen([sys.executable,
        "scripts/stub_openrouter.py", "--port", "0", "--script", <example>], cwd=_REPO_ROOT,
        stdout=PIPE, stderr=PIPE, text=True)`. Read the listening line with a bounded wait (a reader
        thread with a 10 s join), then `httpx.post` a request and check the body. `terminate()` in
        `finally`. A second run with a bad script exits 2 and prints `stub_openrouter:` on stderr.
    13. **Containment.** No file under `app/` mentions `stub_openrouter`, which checks the "nothing
        in `app/` imports it" claim.
    14. **404 and 400 surface.** A wrong path returns 404, and a non-JSON body returns 400. Neither
        crashes the server, and a following valid request still answers.
- **Mirror**: `tests/test_openrouter_client.py` (imports and monkeypatching settings) and
  `tests/test_pipeline_concurrency.py:604-614` (the server thread lifecycle).
- **Validate**: `$PY -m pytest tests/test_stub_openrouter.py -q`, then
  `$PY -m pytest tests/test_stub_openrouter.py tests/test_openrouter_client.py -m "not db" -q`

### Task 5: Full regression

- **Validate**:
  - `$PY -m pytest tests/ -m "not db" -q` (about 90 s, Docker not needed).
  - Then run the full suite in the background on a throwaway libSQL (`HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:8086`,
    see memory). Start Docker Desktop first if it is off, and ask before recreating any shared
    container. Record the counts in the report.

---

## End-to-End Tests

The live recipe follows memory ("/v1 live E2E recipe") and uses the real stub instead of a scratchpad
one:

- [ ] Start a throwaway libSQL on `:8087`, run `init_db()` and `manage_users.py create-user` (this
      must come **before** uvicorn).
- [ ] Start `python scripts/stub_openrouter.py --port 9100 --script tests/e2e/scripts/example.json`
      in the background, then `curl http://127.0.0.1:9100/health` and expect 200.
- [ ] Start uvicorn on `:8765` with `OPENROUTER_BASE_URL=http://127.0.0.1:9100/v1`,
      `OPENROUTER_API_KEY=sk-e2e-secret`, `DATABASE_URL=http://127.0.0.1:8087/` and `V1_ENABLED=true`.
- [ ] `POST /v1/chat/completions` with the user token and the substring rule's trigger. Expect 200,
      the scripted content, `finish_reason`, and `usage` equal to the script's.
- [ ] The stub's stderr shows one ASCII line with the model, the message count and the params, and
      no `sk-e2e-secret`.
- [ ] Send the `fail_status: 503` trigger and expect `/v1`'s retryable upstream error (STORY-011
      mapping). Send the `fail_status: 400` trigger and expect the non-retryable mapping.
- [ ] Send a delay rule longer than the harness's `OPENROUTER_TIMEOUT_SECONDS` (start uvicorn with
      it set to 2) and expect the retryable timeout mapping.
- [ ] Run `POST /query` against the same stub and expect 200 with the scripted content. This is the
      Technical Notes' "a live `/query` always returns 502", now fixed by the stub.
- [ ] Teardown: stop uvicorn and the stub. Check `Get-NetTCPConnection -LocalPort 8765,9100` for
      orphans (memory: orphaned uvicorn after TaskStop), then run `docker rm -f` on the throwaway.

---

## Validation

```bash
$PY scripts/stub_openrouter.py --help
$PY -m pytest tests/test_stub_openrouter.py -q
$PY -m pytest tests/ -m "not db" -q
grep -rn stub_openrouter app/ || echo "app/ clean"
```

---

## Acceptance Criteria

(Copied from story `STORY-014`)

- [ ] Given `python scripts/stub_openrouter.py --port 9100 --script <file>`, when the harness runs with `OPENROUTER_BASE_URL=http://127.0.0.1:9100/v1`, then a `/v1` request is answered with the scripted content, `finish_reason` and `usage`, and the stub logs (ASCII only) each received request's model, message count and parameter keys.
- [ ] Given a script rule matching on the last user message (substring or regex), when a request matches, then its response is used; given no match, then a configurable default; rules can set `delay_seconds` and `fail_status` (e.g. 503, 400) instead of a body.
- [ ] Given the stub's own test, when it runs, then `call_openrouter` against the stub returns the scripted result, a `delay_seconds` rule exceeding `OPENROUTER_TIMEOUT_SECONDS` raises a retryable `OpenRouterError`, and a `fail_status: 400` raises a non-retryable one.
- [ ] Given the stub, when it receives an `Authorization` header, then it never logs the header's value.
- [ ] All tasks completed
- [ ] `-m "not db"` and full suites pass
- [ ] No new dependency; nothing in `app/` imports the stub
- [ ] Follows existing patterns
