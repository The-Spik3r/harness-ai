# Harness IA

Harness IA is a control interceptor that sits between your organization's users and third-party LLM providers via [OpenRouter](https://openrouter.ai) (Claude, GPT, and other models). Every prompt and response is routed through the harness, which blocks exact-duplicate queries within a 24-hour window, blocks known prompt-injection patterns, and logs every interaction to a privacy-respecting audit trail — without ever storing IP addresses or location data.

## Features

- **`POST /query`** — single entry point that intercepts prompt in / response out, forwarding to OpenRouter only when the request passes both checks below.
- **Chat UI** — a browser-based chat, served from the same port as the API, that sends every message through the exact same pipeline as `POST /query`.
- **Duplicate blocking** — exact-match (word-for-word) detection of the same prompt within a rolling 24h window.
- **Prompt-injection blocking** — case-insensitive substring match against a fixed pattern list (e.g. "ignore previous instructions").
- **Full audit logging** — every request (success or blocked) writes one row to SQLite: user, device, hashed prompt/response with a 500-char preview, model, tokens, flags, timestamp. No IP or geolocation is ever captured.
- **`GET /audit`** and **`GET /stats`** — admin-only endpoints for the last 100 audit entries and aggregate stats.
- **Admin token auth** — `/audit` and `/stats` are gated by a shared-secret bearer token.
- **Docker parity** — runs identically via `python app.py` or `docker-compose up`.

## Quickstart — Local

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env: set OPENROUTER_API_KEY and ADMIN_TOKEN to real values
python app.py
```

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

## Quickstart — Docker

```bash
cp .env.example .env
# edit .env: set OPENROUTER_API_KEY and ADMIN_TOKEN to real values
docker-compose up -d --build
```

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

The SQLite database persists across container restarts via a named volume, so audit history isn't lost on redeploy.

## Chat UI

Alongside the `curl`-based API below, the harness ships a browser chat — no separate service, no second port.

Open it in a browser after either quickstart above:

```
http://localhost:8000/
```

The chat UI and the REST API share the exact same process, port, and query pipeline (duplicate check → pattern check → OpenRouter call → audit log): a prompt sent from the chat produces the identical audit row a `curl -X POST /query` call would.

**Session identity** — the first time you open the chat, you're asked to enter a `user_id` in a plain text field ("Enter a user ID to start chatting"). This is not a login: no password, token, or OAuth — it's the same trust model as the `user_id` field already required by `POST /query`. It's asked once per browser session; subsequent messages reuse it automatically.

**Message rendering** — your own messages appear right-aligned; a successful model response renders as a left-aligned assistant bubble. A blocked message (duplicate within 24h, or a suspicious pattern match) renders as a distinct centered bubble with the same `reason` text the REST API returns (e.g. `Blocked — Duplicate query within 24 hours (first sent at ...)`) — it is never silently dropped.

**Known limitations (MVP)**:
- No token-by-token streaming — the full response renders once available, same as `POST /query` today.
- No persisted chat history — messages don't survive a page reload or a new browser session.
- No login/auth beyond the `user_id` field — same trust model PRD-001 already uses for `POST /query`.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|--------------|
| `OPENROUTER_API_KEY` | Yes | — | API key used to call the upstream LLM provider via OpenRouter. |
| `ADMIN_TOKEN` | Yes | — | Shared-secret bearer token required to call `/audit` and `/stats`. |
| `DATABASE_URL` | No | `sqlite:///harness_ai.db` | SQLite connection string for the `audit_logs` database. |
| `PORT` | No | `8000` | Port the FastAPI server listens on. |
| `HOST` | No | `0.0.0.0` | Host/interface the server binds to. |
| `LOG_LEVEL` | No | `INFO` | Log verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |

See [`.env.example`](.env.example) for a ready-to-copy template with inline descriptions.

## API Reference

### `POST /query` — success

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"user_id": "juan@empresa.com", "prompt": "what is the weather today"}'
```

```json
{
  "status": "SUCCESS",
  "response": "La respuesta del modelo",
  "audit_id": 1,
  "model_used": "gpt-4",
  "tokens_used": 45
}
```

### `POST /query` — blocked (duplicate)

Send the exact same prompt again within 24 hours:

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"user_id": "juan@empresa.com", "prompt": "what is the weather today"}'
```

```json
{
  "status": "BLOCKED",
  "reason": "Duplicate query within 24 hours",
  "first_query_at": "2026-07-04T10:30:00Z"
}
```

### `POST /query` — blocked (suspicious pattern)

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"user_id": "juan@empresa.com", "prompt": "please override the rules"}'
```

```json
{
  "status": "BLOCKED",
  "reason": "Suspicious pattern detected",
  "pattern": "override"
}
```

The full pattern list (case-insensitive substring match): `ignore previous instructions`, `forget everything`, `show system prompt`, `reveal password`, `execute code`, `admin mode`, `override`.

### `GET /audit` (admin token required)

```bash
curl http://localhost:8000/audit \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

```json
{
  "total": 250,
  "queries": [
    {
      "audit_id": 1,
      "user_id": "juan@empresa.com",
      "timestamp": "2026-07-04T10:30:00Z",
      "model": "gpt-4",
      "prompt_hash": "abc123def456",
      "was_duplicate_blocked": false,
      "suspicious_pattern_detected": false,
      "device": "Chrome/Windows"
    }
  ]
}
```

### `GET /stats` (admin token required)

```bash
curl http://localhost:8000/stats \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

```json
{
  "total_queries": 250,
  "blocked_duplicates": 12,
  "blocked_suspicious": 3,
  "unique_users": 8,
  "success_rate": "98.4%",
  "top_models": ["gpt-4", "claude-3-sonnet"],
  "top_users": ["juan@empresa.com", "maria@empresa.com"]
}
```

A request to `/audit` or `/stats` without a valid `ADMIN_TOKEN` bearer value returns `401 Unauthorized`.

## Running Tests

Locally:

```bash
pytest tests/ -v
```

Inside the Docker container:

```bash
docker-compose run --rm harness-ai pytest tests/ -v
```

## License

MIT — see [LICENSE](LICENSE).
