# E2E stub scripts

These are the scripts for `scripts/stub_openrouter.py`. The stub is a scripted stand-in for OpenRouter, and it is a test tool, not shipped behaviour (PRD-015 Section 7.9). The client E2E stories (STORY-015 to STORY-018) add their own scripts here: `openai_sdk.json` (STORY-015), `aider.json` (STORY-016), `continue.json` (STORY-017) and `docker_smoke.json` (STORY-018). PRD-017 adds `opencode.json` (STORY-016) and `cline.json` (STORY-017). `example.json` demonstrates every rule kind. `tool_loop.json` (PRD-017 STORY-014) scripts a tool-calling agent loop.

`tool_loop.json` answers a first user turn containing `TOOL-LOOP` with a `read` call, then each later request by what the last assistant turn called (`after_call`): after `read` an `edit`, after `edit` a `shell` call running `npm test`, and after `shell` a final text (a failure text when the result does not contain `passing`). It uses generic tool names; the client scripts (STORY-016, STORY-017) bring their own.

`opencode.json` (PRD-017 STORY-016) scripts OpenCode 2.0's two E2E scenarios. A first user turn containing `E2E-OPENCODE-TASK` gets a `read` of `src/calc.py`, then each later request is answered by `after_call`: after `read` an `edit` (`oldString`/`newString`), after `edit` a `write` of `tests/test_calc.py`, after `write` a `shell` call running `python -m unittest -q`, and after `shell` a final text (`E2E-OPENCODE-DONE` when the output has a line starting with `OK`, a failure text otherwise). A first user turn containing `E2E-OPENCODE-DROP` gets a `shell` call running `sqlite3 app.db "DROP TABLE users"`, which the harness denies (`sql.ddl`), so OpenCode only ever sees the harness's note as text. The last rule answers a request without `tools` (OpenCode's session-title request, normally disabled by `agent.title.disable`). The paths in `read`, `edit` and `write` are `@REPO@`: the test renders the script with the throwaway repository's forward-slash path (`tests/e2e/_opencode.py`) and writes the copy into its temporary directory, so the committed file is never loaded as it is.

`cline.json` (PRD-017 STORY-017) scripts Cline 4.x's two E2E scenarios with Cline's tool names: `read_files` (`files[].path`), `editor` (`path`, `old_text`, `new_text`) and `run_commands` (`commands[]`). Cline's last user turn is its own nudge, not the prompt, so the scenario is picked from the system prompt, which carries the `-c` working directory: a directory named `e2e017-017-cline-task` gets a `read_files` of `src/calc.py`, then each later request is answered by `after_call`: after `read_files` an `editor` edit, after the first `editor` result an `editor` that replaces the `# placeholder` line of `tests/test_calc.py` (an `editor` on an existing file needs `old_text`), after the second `editor` a `run_commands` of `python -m unittest -q`, and after `run_commands` a `submit_and_exit` (verified when the output has an escaped or real newline then `OK`, because Cline wraps the stderr output in JSON text; a failing summary otherwise). A directory named `e2e017-017-cline-drop` gets a `run_commands` of `sqlite3 app.db "DROP TABLE users"`, which the harness denies (`sql.ddl`); Cline prints the harness note and asks again, and the next request (last assistant turn holds the note) gets a `submit_and_exit`. Cline's loop ends only on a `submit_and_exit` call whose `summary` has at least 10 characters, and `-t` does not stop it (the planning probe saw 984 requests in a minute), so every path ends in that call and so does the `default`. The paths are `@REPO@`, rendered by `tests/e2e/_cline.py`. Its action policy is `tests/e2e/cline/action_policy.yaml` (`tools:` for Cline's names, and `submit_and_exit` under `opaque_tools`).

`cline_realtime.json` (PRD-021 STORY-015) scripts Cline's real-time scenarios, every reply carrying a `stream` shape (6 to 8 characters per delta, 60 ms apart). The scenario is picked from the system prompt's working directory, as in `cline.json`: `e2e021-015-cline-text` gets text plus a `submit_and_exit`, `e2e021-015-cline-reason` the same with a `stream.reasoning` carrying `@SENTINEL@` (rendered by `tests/e2e/_cline_realtime.py`), and `e2e021-015-cline-drop` a `run_commands` of `sqlite3 app.db "DROP TABLE users"` that the harness denies; the follow-up (last assistant turn holds the harness note) gets a `submit_and_exit`. Every path ends in `submit_and_exit`, which `opaque_tools` allows and the harness releases whole.

`aider.json` answers Aider's edit request with a SEARCH/REPLACE block in the `diff` edit format, and Aider's separate commit-message request (its user turn always contains `# Diffs:`) with a fixed sentence. The commit-message rule comes first, because that request also quotes the edit request.

`continue.json` answers Continue's chat prompt with a fixed sentence, and its slow prompt with another after a 20 s delay, so the harness sends SSE keep-alives before the answer. Continue's CLI makes one request per prompt, so there is no second rule.

`docker_smoke.json` is the script for the Docker smoke (`tests/e2e/test_docker_smoke.py`). There the stub runs inside the harness container's network namespace (`tests/e2e/docker/compose.smoke.yml`), so the harness still reaches it on `127.0.0.1`. Each rule has a job:
- The default answers the direct-vs-Caddy comparison.
- `SMOKE-SLOW` waits 30 s, so keep-alives can be timed through Caddy at a 10 s interval.
- `SMOKE-WAVE` waits 5 s, which separates the requests that found a pipeline worker from the ones that queued for one.
- `SMOKE-QUERY` answers the `/query` check.

## Run

```bash
# terminal 1: the stub
python scripts/stub_openrouter.py --port 9100 --script tests/e2e/scripts/example.json

# terminal 2: the harness, pointed at it
OPENROUTER_BASE_URL=http://127.0.0.1:9100/v1 uvicorn app.main:app --port 8765
```

`GET http://127.0.0.1:9100/health` answers 200 once the stub is listening. The harness still sends its `OPENROUTER_API_KEY` to the stub, and the stub ignores it, so any non-empty value works. The stub never logs the key.

## Format

```json
{
  "default": {"content": "...", "finish_reason": "stop"},
  "rules": [
    {"contains": "rename foo", "content": "...", "usage": {"prompt_tokens": 12, "completion_tokens": 30}},
    {"regex": "(?i)^hello", "content": "..."},
    {"contains": "please be slow", "delay_seconds": 5, "content": "..."},
    {"contains": "upstream down", "fail_status": 503},
    {"contains": "flaky", "times": 1, "fail_status": 503},
    {"contains": "flaky", "content": "answered on the retry"}
  ]
}
```

| Key | Where | Meaning |
|-----|-------|---------|
| `contains` / `regex` | rule (exactly one) | Matches a substring, or a pattern through `re.search`, against the **last message of `role`** (default `user`; `""` when there is no user message). `{"regex": ""}` matches any content |
| `content` | rule, default | The assistant text. Defaults to `""`, or to `null` when the reply has `tool_calls` |
| `finish_reason` | rule, default | A string or `null`. Defaults to `"stop"`, or to `"tool_calls"` when the reply has `tool_calls` |
| `tool_calls` | rule, default | A non-empty list of `{"name", "arguments", "id"?}`. `arguments` must be a string and is sent as given. An omitted `id` becomes `call_<n>` from a per-stub counter; a scripted id may not look like `call_<digits>` and must be unique in the reply |
| `usage` | rule, default | `prompt_tokens` / `completion_tokens` default to 1 each. `total_tokens` defaults to their sum |
| `delay_seconds` | rule, default | Sleeps before replying. Defaults to 0 |
| `fail_status` | rule, default | Replies with this status (400 to 599) and an error body instead of a body. It cannot be combined with `content`, `finish_reason`, `usage` or `tool_calls` |
| `role` | rule only | `system`, `user`, `assistant` or `tool`: which message `contains` / `regex` test (the last one of that role). The rule does not match when the request has none |
| `last_role` | rule only | Same vocabulary. The rule matches only when the conversation's last message has this role |
| `after_call` | rule only | The rule matches only when the last assistant turn called a tool of this name. Independent of ids, arguments and tool-result text, which clients rewrite |
| `advertises` | rule only | The rule matches only when the request's `tools` list offers a function of this name |
| `times` | rule only | Answers the first N matches (an integer from 1), then the rule is skipped as if it did not match, so a later rule or `default` answers. Counted per stub process: restart the stub to reset it |

The first matching rule wins. If no rule matches, `default` answers. If `default` is missing, a built-in default answers `stub_openrouter: no rule matched`. A malformed script is rejected at startup, with exit code 2 and the offending field named.

Each request logs one ASCII line on stderr with the model, the message count, the parameter keys, the rule that answered, and the counts `tools=<n>` (tools offered) and `calls=<n>` (calls answered). It never logs message content, tool names, arguments or headers. The stub never streams: `call_openrouter` does not send `stream` upstream.

## Scripting an agent loop

Sequence the rules on `after_call` (what the last assistant turn called) rather than on tool-result text, because clients rewrite ids and word results their own way. Tool content reaches the stub after the harness's pattern and PII steps (PRD-017 D13), so any text a rule matches on must be a marker that is not PII.

To end the loop:
- OpenCode stops on a text reply (a reply without `tool_calls`, `finish_reason` `"stop"`).
- Cline never stops on its own. Add a rule with `"advertises": "submit_and_exit"` that answers with a `submit_and_exit` call, and still pass `-t` to the client as a safety net.
