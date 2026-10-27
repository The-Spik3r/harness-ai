# E2E stub scripts

These are the scripts for `scripts/stub_openrouter.py`. The stub is a scripted stand-in for OpenRouter, and it is a test tool, not shipped behaviour (PRD-015 Section 7.9). The client E2E stories (STORY-015 to STORY-018) add their own scripts here. `example.json` demonstrates every rule kind.

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
    {"contains": "upstream down", "fail_status": 503}
  ]
}
```

| Key | Where | Meaning |
|-----|-------|---------|
| `contains` / `regex` | rule (exactly one) | Matches a substring, or a pattern through `re.search`, against the **last `user` message** |
| `content` | rule, default | The assistant text. Defaults to `""` |
| `finish_reason` | rule, default | A string or `null`. Defaults to `"stop"` |
| `usage` | rule, default | `prompt_tokens` / `completion_tokens` default to 1 each. `total_tokens` defaults to their sum |
| `delay_seconds` | rule, default | Sleeps before replying. Defaults to 0 |
| `fail_status` | rule, default | Replies with this status (400 to 599) and an error body instead of a body. It cannot be combined with `content`, `finish_reason` or `usage` |

The first matching rule wins. If no rule matches, `default` answers. If `default` is missing, a built-in default answers `stub_openrouter: no rule matched`. A malformed script is rejected at startup, with exit code 2 and the offending field named.

Each request logs one ASCII line on stderr with the model, the message count, the parameter keys and the rule that answered. It never logs message content or headers.
