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
duplicate check (24h)  →  prompt-injection check  →  PII redaction (prompt)  →  forward to OpenRouter  →  PII redaction (response)  →  audit log
```

If either check fails, the request is rejected **before** it reaches the model provider, and the rejection is logged with the same rigor as a successful call. Redaction, by contrast, never rejects anything — it only masks.

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
        │  5. PII redaction     │
        │     (outbound prompt) │
        └───────────┬───────────┘
                     │ checks passed, prompt masked
                     ▼
        ┌───────────────────────┐
        │   OpenRouter API      │
        │ (Claude, GPT, others) │
        └───────────┬───────────┘
                     │ response
                     ▼
        ┌───────────────────────┐
        │   PII redaction       │
        │   (model response)    │
        └───────────┬───────────┘
                     ▼
        ┌───────────────────────┐
        │   Audit log write     │
        │  user · device · hash │
        │  model · tokens · flag│
        └───────────┬───────────┘
                     ▼
              Response to caller
```

Blocked requests (duplicate or suspicious pattern) short-circuit at step 3 or 4 — the model provider is never called, and the block is still logged. Redaction sits after both checks, so a blocked request is never analyzed for PII.

---

## Features

| Capability | Description |
|---|---|
| **Single entry point** | `POST /query` intercepts every prompt/response pair; nothing reaches OpenRouter without passing through it. |
| **Chat UI** | A browser-based chat served from the same port and process as the API, running through the identical pipeline as `POST /query`. |
| **Duplicate blocking** | Exact-match (word-for-word) detection of repeated prompts within a rolling 24-hour window. |
| **Prompt-injection blocking** | Case-insensitive substring match against a maintained pattern list. |
| **PII redaction** | [Microsoft Presidio](https://microsoft.github.io/presidio/) masks personal data (names, emails, phone numbers, cards, SSNs, IBANs, locations) in the outbound prompt before it reaches OpenRouter, and in the model's response before it reaches the caller. Masking never blocks a request, and the audit log keeps the raw text. English-only in this release. |
| **Full audit logging** | Every request — success or blocked — writes one row to SQLite: user, device, hashed prompt/response with a 500-character preview, model, tokens, flags, and timestamp. IP addresses and geolocation are never captured. |
| **Admin endpoints** | `GET /audit` and `GET /stats` expose the last 100 audit entries and aggregate statistics, gated behind a bearer token. |
| **Docker parity** | Identical behavior via `python app.py` or `docker-compose up` — no environment-specific branches. |
| **Model-agnostic** | Works with any model OpenRouter serves — Claude, GPT, or others — with no code changes. |

---

## Requirements

- Python 3.9+
- Docker & Docker Compose (optional, for containerized deployment)
- An [OpenRouter](https://openrouter.ai) API key
- ~500 MB of disk for the English spaCy NLP model (`en_core_web_lg`) used by PII redaction
- Network access at install/build time to download that model — or at first startup, if you skip the download step and let Presidio fetch it

---

## Quickstart — Local

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_lg   # English NLP model used by PII redaction (~425 MB)
cp .env.example .env
# edit .env: set OPENROUTER_API_KEY and ADMIN_TOKEN to real values
python app.py
```

The model is a separate download — `requirements.txt` installs Presidio and spaCy but not the model itself. If you skip this step, Presidio fetches the model automatically the first time the service starts: the first boot then stalls on a ~400 MB download and needs network access at runtime. To run without redaction entirely, set `PII_REDACTION_ENABLED=false` in `.env`.

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

The image bakes `en_core_web_lg` in at build time, so no model download happens at container start — without it, a fresh container would pull ~400 MB before serving its first request. This makes the image substantially larger: measured with `docker image inspect`, the pre-PII image was 131 MB and the current one is 628 MB (of which ~446 MB is the model layer), and the first build spends ~40 s downloading it. Accepted tradeoff — see PRD-003 Risk 5. (`docker images` reports larger figures for the same images on containerd-backed installs; the numbers above use `docker image inspect`.)

---

## Chat UI

Alongside the REST API, the harness ships a browser-based chat — no separate service, no second port.

Open it after either quickstart above:

```
http://localhost:8000/
```

The chat UI and the REST API share the exact same process, port, and query pipeline (duplicate check → pattern check → PII redaction → OpenRouter call → audit log): a prompt sent from the chat produces the identical audit row a `curl -X POST /query` call would.

**Session identity** — on first load, the chat asks for a `user_id` in a plain text field. This is not a login: no password, token, or OAuth — it is the same trust model already required by `POST /query`. It is requested once per browser session; subsequent messages reuse it automatically.

**Message rendering** — your own messages render right-aligned; a successful model response renders as a left-aligned assistant bubble. A blocked message (duplicate within 24h, or a suspicious pattern match) renders as a distinct centered bubble carrying the same `reason` text the REST API returns — it is never silently dropped.

**Known limitations (MVP)**

- No token-by-token streaming — the full response renders once available, same as `POST /query` today.
- No persisted chat history — messages do not survive a page reload or a new browser session.
- No login/auth beyond the `user_id` field — same trust model already used by `POST /query`.
- No visible indicator when PII is masked — redaction still applies to every chat message, but the UI does not yet surface *that* it happened (the REST API does, via `pii_redacted`).

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
| `PII_REDACTION_ENABLED` | No | `true` | Master switch for PII redaction on prompts and responses. Set to `false` to skip all NLP work (and the model download requirement). |
| `PII_SCORE_THRESHOLD` | No | `0.35` | Minimum Presidio confidence for an entity to be masked. Deliberately low — the project favors over-masking over missing real PII. |
| `PII_ENTITIES` | No | `PERSON,EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE,LOCATION` | Comma-separated list of Presidio entity types to detect and mask. |
| `PII_NLP_MODEL` | No | `en_core_web_lg` | spaCy model backing Presidio's analyzer. This is the only model the Dockerfile and the Quickstart install; naming a different one (e.g. `en_core_web_trf`) makes spaCy try to download it at startup, which is slow and fails outright if the name is unresolvable or the package needs a C++ toolchain to build. |

All four PII settings are read once at startup (`app/config.py`); changing them requires a restart.

See [`.env.example`](.env.example) for a ready-to-copy template with inline descriptions.

---

## API Reference

### `POST /query` — success

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"user_id": "analyst-7", "prompt": "my name is Maria Gomez, my email is juan@empresa.com"}'
```

```json
{
  "status": "SUCCESS",
  "response": "Sure — I will reply to <EMAIL_ADDRESS> for <PERSON>.",
  "audit_id": 1,
  "model_used": "gpt-4",
  "tokens_used": 45,
  "pii_redacted": true,
  "pii_entities_masked": ["EMAIL_ADDRESS", "PERSON"]
}
```

OpenRouter received `my name is <PERSON>, my email is <EMAIL_ADDRESS>` — never the raw text. `pii_entities_masked` is the sorted union of entity types masked in the prompt and in the response; when nothing is detected, `pii_redacted` is `false` and the list is empty. Both fields are additive — clients that ignore unknown fields are unaffected, and the two `BLOCKED` shapes below are unchanged (redaction runs only after both checks pass).

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
      "device": "Chrome/Windows",
      "pii_detected_input": true,
      "pii_detected_output": false,
      "pii_entities": ["EMAIL_ADDRESS", "PERSON"]
    }
  ]
}
```

`pii_entities` is the union of types masked in either direction. The audit trail deliberately stores the **raw, unmasked** prompt and response previews in the database — an auditor investigating an incident needs the actual value, not `<EMAIL_ADDRESS>` — but this endpoint exposes neither the raw previews nor the masked text, only the flags above.

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
  "top_users": ["juan@empresa.com", "maria@empresa.com"],
  "pii_detected_queries": 34,
  "top_pii_entities": ["EMAIL_ADDRESS", "PERSON"]
}
```

`pii_detected_queries` counts audit rows flagged on input **or** output; `top_pii_entities` ranks individual entity types by frequency across rows.

A request to `/audit` or `/stats` without a valid `ADMIN_TOKEN` bearer value returns `401 Unauthorized`.

---

## Running Tests

The PII tests load the real `en_core_web_lg` model, so run the `spacy download` step from [Quickstart — Local](#quickstart--local) first — otherwise the first test run spends several minutes downloading it. The in-container run needs nothing extra (the image already has it).

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

**First startup stalls while downloading several hundred MB**
That is spaCy fetching `en_core_web_lg` because it was never installed — Presidio downloads a missing model on first use rather than failing. Run `python -m spacy download en_core_web_lg` up front (see [Quickstart — Local](#quickstart--local)) to keep it out of the startup path, or set `PII_REDACTION_ENABLED=false` to skip redaction entirely.

**`[x] No compatible package found for '<model>'` and the process exits during startup**
`PII_NLP_MODEL` names a model spaCy cannot resolve, so the automatic download fails and takes the process down with it. Fix the name, or install that model yourself. Because the model is loaded at startup, this kills the boot rather than the first request. Load failures that are not download failures surface instead as `PiiRedactorError: Failed to load Presidio NLP model '<model>'`.

**Model responses contain `<PERSON>` or `<EMAIL_ADDRESS>` where you expected real text**
That is PII redaction working as designed — the threshold (`PII_SCORE_THRESHOLD`, default `0.35`) deliberately favors over-masking. Raise it, or trim `PII_ENTITIES`, if a specific entity type is too aggressive for your use case.

**`401 Unauthorized` on `/audit` or `/stats`**
Confirm the `Authorization: Bearer <token>` header matches `ADMIN_TOKEN` in `.env` exactly.

---

## Roadmap

- [x] Duplicate detection (24h, exact match)
- [x] Prompt-injection blocking (pattern list)
- [x] Full audit logging (SQLite)
- [x] Chat UI
- [ ] Semantic (not just exact-match) duplicate detection
- [x] PII redaction on input/output
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