<div align="center">

# Harness IA

**A control-plane interceptor for LLM traffic — duplicate blocking, prompt-injection defense, and full audit logging, in front of any OpenRouter-served model.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED.svg)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](#running-tests)

</div>

---

## Table of Contents

- [Problem](#problem)
- [Solution](#solution)
- [Architecture](#architecture)
- [Features](#features)
- [Requirements](#requirements)
- [Quickstart — Local](#quickstart--local)
- [Quickstart — Docker](#quickstart--docker)
- [Chat UI](#chat-ui)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Running Tests](#running-tests)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [Security](#security)
- [License](#license)

---

## Problem

Organizations adopting LLMs in production face three recurring, unmanaged risks:

| Risk | Consequence |
|---|---|
| **Repeated identical queries** | The same sensitive prompt is sent to a third-party model multiple times, multiplying exposure with no added value. |
| **No interception layer** | Prompts and responses go directly from application code to the model provider — no centralized point to inspect, block, or log traffic. |
| **No audit trail** | When something goes wrong (a leak, a misuse, a compliance question), there is no record of who asked what, when, or which model answered. |

## Solution

**Harness IA** sits between your application (or a human, via the built-in chat UI) and any model served through [OpenRouter](https://openrouter.ai). Every request passes through a fixed pipeline before it is allowed to leave your infrastructure:

```
duplicate check (24h)  →  prompt-injection check  →  forward to OpenRouter  →  audit log
```

If either check fails, the request is rejected **before** it reaches the model provider, and the rejection is logged with the same rigor as a successful call.

---

## Architecture

```
┌──────────────┐        ┌──────────────┐
│   Chat UI    │        │   Your App   │
│ (browser)    │        │  (any client)│
└──────┬───────┘        └──────┬───────┘
       │                       │
       │      POST /query      │
       └───────────┬───────────┘
                    ▼
        ┌───────────────────────┐
        │   Harness IA (FastAPI)│
        │                       │
        │  1. Validate request  │
        │  2. Hash prompt       │
        │  3. Duplicate check   │◄──── SQLite (audit_logs)
        │     (24h window)      │
        │  4. Pattern check     │
        │     (prompt injection)│
        └───────────┬───────────┘
                     │ passes both checks
                     ▼
        ┌───────────────────────┐
        │   OpenRouter API      │
        │ (Claude, GPT, others) │
        └───────────┬───────────┘
                     │ response
                     ▼
        ┌───────────────────────┐
        │   Audit log write     │
        │  user · device · hash │
        │  model · tokens · flag│
        └───────────┬───────────┘
                     ▼
              Response to caller
```

Blocked requests (duplicate or suspicious pattern) short-circuit at step 3 or 4 — the model provider is never called, and the block is still logged.

---

## Features

| Capability | Description |
|---|---|
| **Single entry point** | `POST /query` intercepts every prompt/response pair; nothing reaches OpenRouter without passing through it. |
| **Chat UI** | A browser-based chat served from the same port and process as the API, running through the identical pipeline as `POST /query`. |
| **Duplicate blocking** | Exact-match (word-for-word) detection of repeated prompts within a rolling 24-hour window. |
| **Prompt-injection blocking** | Case-insensitive substring match against a maintained pattern list. |
| **Full audit logging** | Every request — success or blocked — writes one row to SQLite: user, device, hashed prompt/response with a 500-character preview, model, tokens, flags, and timestamp. IP addresses and geolocation are never captured. |
| **Admin endpoints** | `GET /audit` and `GET /stats` expose the last 100 audit entries and aggregate statistics, gated behind a bearer token. |
| **Docker parity** | Identical behavior via `python app.py` or `docker-compose up` — no environment-specific branches. |
| **Model-agnostic** | Works with any model OpenRouter serves — Claude, GPT, or others — with no code changes. |

---

## Requirements

- Python 3.9+
- Docker & Docker Compose (optional, for containerized deployment)
- An [OpenRouter](https://openrouter.ai) API key

---

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

The SQLite database persists across container restarts via a named volume — audit history is not lost on redeploy.

---

## Chat UI

Alongside the REST API, the harness ships a browser-based chat — no separate service, no second port.

Open it after either quickstart above:

```
http://localhost:8000/
```

The chat UI and the REST API share the exact same process, port, and query pipeline (duplicate check → pattern check → OpenRouter call → audit log): a prompt sent from the chat produces the identical audit row a `curl -X POST /query` call would.

**Session identity** — on first load, the chat asks for a `user_id` in a plain text field. This is not a login: no password, token, or OAuth — it is the same trust model already required by `POST /query`. It is requested once per browser session; subsequent messages reuse it automatically.

**Message rendering** — your own messages render right-aligned; a successful model response renders as a left-aligned assistant bubble. A blocked message (duplicate within 24h, or a suspicious pattern match) renders as a distinct centered bubble carrying the same `reason` text the REST API returns — it is never silently dropped.

**Known limitations (MVP)**

- No token-by-token streaming — the full response renders once available, same as `POST /query` today.
- No persisted chat history — messages do not survive a page reload or a new browser session.
- No login/auth beyond the `user_id` field — same trust model already used by `POST /query`.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENROUTER_API_KEY` | Yes | — | API key used to call the upstream LLM provider via OpenRouter. |
| `ADMIN_TOKEN` | Yes | — | Shared-secret bearer token required to call `/audit` and `/stats`. |
| `DATABASE_URL` | No | `sqlite:///harness_ai.db` | SQLite connection string for the `audit_logs` database. |
| `PORT` | No | `8000` | Port the FastAPI server listens on. |
| `HOST` | No | `0.0.0.0` | Host/interface the server binds to. |
| `LOG_LEVEL` | No | `INFO` | Log verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |

See [`.env.example`](.env.example) for a ready-to-copy template with inline descriptions.

---

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

```json
{
  "status": "BLOCKED",
  "reason": "Duplicate query within 24 hours",
  "first_query_at": "2026-07-04T10:30:00Z"
}
```

### `POST /query` — blocked (suspicious pattern)

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

---

## Running Tests

Locally:

```bash
pytest tests/ -v
```

Inside the Docker container:

```bash
docker-compose run --rm harness-ai pytest tests/ -v
```

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'fastapi'`**
Run `pip install -r requirements.txt`.

**`OPENROUTER_API_KEY not found` on startup**
Copy `.env.example` to `.env` and fill in a real key.

**Docker container exits immediately**
Check logs with `docker-compose logs harness-ai`.

**`401 Unauthorized` on `/audit` or `/stats`**
Confirm the `Authorization: Bearer <token>` header matches `ADMIN_TOKEN` in `.env` exactly.

---

## Roadmap

- [x] Duplicate detection (24h, exact match)
- [x] Prompt-injection blocking (pattern list)
- [x] Full audit logging (SQLite)
- [x] Chat UI
- [ ] Semantic (not just exact-match) duplicate detection
- [ ] PII redaction on input/output
- [ ] Role-based access control (RBAC)
- [ ] Configurable, per-deployment pattern lists

---

## Contributing

Contributions are welcome.

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m 'Add my feature'`
4. Push the branch: `git push origin feature/my-feature`
5. Open a Pull Request

Please include tests for any new behavior.

---

## Security

This project handles LLM traffic that may include sensitive prompts. If you discover a security vulnerability, please report it privately rather than opening a public issue — see [SECURITY.md](SECURITY.md) for details.

---

## License

MIT — see [LICENSE](LICENSE).