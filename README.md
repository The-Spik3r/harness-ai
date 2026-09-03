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
- [Persistence & Deployment](#persistence--deployment)
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
identity resolution + authorization  →  duplicate check (24h)  →  prompt-injection check  →  PII redaction (prompt)  →  forward to OpenRouter  →  PII redaction (response)  →  audit log
```

If either check fails, the request is rejected **before** it reaches the model provider, and the rejection is logged with the same rigor as a successful call. Redaction, by contrast, never rejects anything — it only masks. An unverified or unauthorized request never reaches the duplicate check at all.

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
        │  0. Resolve identity  │◄──── Turso (users)
        │     + authorize       │
        │  1. Validate request  │
        │  2. Hash prompt       │
        │  3. Duplicate check   │◄──── Turso (audit_logs)
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

Blocked requests (missing/invalid credential, missing permission, duplicate, or suspicious pattern) short-circuit at step 0, 3, or 4 — the model provider is never called, and the block is still logged. Redaction sits after every check, so a blocked request is never analyzed for PII.

---

## Features

| Capability | Description |
|---|---|
| **Single entry point** | `POST /query` intercepts every prompt/response pair; nothing reaches OpenRouter without passing through it. |
| **Chat UI** | A browser-based chat served from the same port and process as the API, running through the identical pipeline as `POST /query`. |
| **Role-based access control** | Every request is resolved to a verified `Identity` from a per-user bearer token — no self-declared `user_id` is trusted. Three fixed roles (`admin`, `auditor`, `user`) each hold an explicit permission set; deny-by-default for any unmapped role or permission. `ADMIN_TOKEN` remains a break-glass admin credential, not the primary auth mechanism. |
| **Duplicate blocking** | Exact-match (word-for-word) detection of repeated prompts within a rolling 24-hour window. |
| **Prompt-injection blocking** | Case-insensitive substring match against a maintained pattern list. |
| **PII redaction** | [Microsoft Presidio](https://microsoft.github.io/presidio/) masks personal data (names, emails, phone numbers, cards, SSNs, IBANs, locations) in the outbound prompt before it reaches OpenRouter, and in the model's response before it reaches the caller. Masking never blocks a request, and the audit log keeps the raw text. English-only in this release. |
| **Full audit logging** | Every request — success or blocked — writes one row to the `audit_logs` table in Turso: user, device, hashed prompt/response with a 500-character preview, model, tokens, flags, and timestamp. IP addresses and geolocation are never captured. |
| **Admin endpoints** | `GET /audit` and `GET /stats` expose the last 100 audit entries and aggregate statistics, gated behind a bearer token. |
| **Docker parity** | Identical behavior via `python app.py` or `docker-compose up` — no environment-specific branches. |
| **Model-agnostic** | Works with any model OpenRouter serves — Claude, GPT, or others — with no code changes. |

---

## Requirements

- Python 3.9+. The pinned `libsql==0.1.11` publishes wheels for CPython 3.9–3.13 on Windows, 3.10–3.13 on macOS, and 3.8–3.14 on Linux; on any other interpreter `pip install` falls back to building the Rust source distribution, which needs a working toolchain. The Docker image is `python:3.11`.
- Docker & Docker Compose (optional, for containerized deployment)
- An [OpenRouter](https://openrouter.ai) API key
- A Turso database, or any libSQL endpoint — `DATABASE_URL` has no default and the application will not start without one (see [Persistence & Deployment](#persistence--deployment))
- For running the test suite only: a local libSQL server (see [Running Tests](#running-tests)) — no Turso account needed
- ~500 MB of disk for the English spaCy NLP model (`en_core_web_lg`) used by PII redaction
- Network access at install/build time to download that model — or at first startup, if you skip the download step and let Presidio fetch it

---

## Quickstart — Local

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_lg   # English NLP model used by PII redaction (~425 MB)
cp .env.example .env
# edit .env: set OPENROUTER_API_KEY, ADMIN_TOKEN, DATABASE_URL and
# TURSO_AUTH_TOKEN to real values
python scripts/manage_users.py create-user --user-id admin --role admin
# copy the printed token now -- it cannot be recovered later; this is
# your bearer token for POST /query, /audit, and /stats
python app.py
```

`DATABASE_URL` has no default: without it the process exits on a configuration error before it serves anything. A local libSQL server is enough for a first run — set `DATABASE_URL=http://127.0.0.1:8080` and leave `TURSO_AUTH_TOKEN` empty (see [Running Tests](#running-tests) for the one-line `docker run`). A Turso database needs both values, and a `sqlite:` URL is a startup error rather than a file. See [Persistence & Deployment](#persistence--deployment).

The model is a separate download — `requirements.txt` installs Presidio and spaCy but not the model itself. If you skip this step, Presidio fetches the model automatically the first time the service starts: the first boot then stalls on a ~400 MB download and needs network access at runtime. To run without redaction entirely, set `PII_REDACTION_ENABLED=false` in `.env`.

Skipping the `create-user` step makes the service fail at startup with `RbacNotBootstrappedError` (see Troubleshooting) — `ADMIN_TOKEN` alone is not sufficient, by design.

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

## Quickstart — Docker

```bash
cp .env.example .env
# edit .env: set OPENROUTER_API_KEY, ADMIN_TOKEN, DATABASE_URL and
# TURSO_AUTH_TOKEN to real values
docker-compose up -d --build
docker-compose run --rm harness-ai python scripts/manage_users.py create-user --user-id admin --role admin
# copy the printed token now -- it cannot be recovered later
docker-compose up -d   # see the note below: the first boot exits before this user exists
```

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

Skipping the `create-user` step makes the service fail at startup with `RbacNotBootstrappedError` (see Troubleshooting) — `ADMIN_TOKEN` alone is not sufficient, by design.

**On a brand-new database the first `up` is expected to exit.** The bootstrap guard runs at startup, before you have had any chance to create a user, so the container stops with `RbacNotBootstrappedError`; `create-user` then runs in a throwaway container of its own, which is why it still works. The second `docker-compose up -d` starts the service now that a user exists. Against a database that already has one, the first `up` is enough.

All four values reach the container through `env_file: .env`, the same way `OPENROUTER_API_KEY` and `ADMIN_TOKEN` always have — `docker-compose.yml` names no environment variables of its own.

If you point this stack at a libSQL dev server running on your own machine rather than at Turso, use `http://host.docker.internal:8080` — inside the container `127.0.0.1` is the container itself.

`--build` is not optional after pulling changes. Compose reuses an existing image rather than rebuilding, and an image built before the Turso migration will now fail at boot rather than silently writing to a file.

The audit trail lives in Turso, reached over the network, so the container holds no database and no volume is involved. Restarting, rebuilding, or tearing the stack down — `docker compose down -v` included — does not touch the audit history. See [Persistence & Deployment](#persistence--deployment).

The image bakes `en_core_web_lg` in at build time, so no model download happens at container start — without it, a fresh container would pull ~400 MB before serving its first request. This makes the image substantially larger: measured with `docker image inspect`, the pre-PII image was 131 MB and the current one is 628 MB (of which ~446 MB is the model layer), and the first build spends ~40 s downloading it. Accepted tradeoff — see PRD-003 Risk 5. (`docker images` reports larger figures for the same images on containerd-backed installs; the numbers above use `docker image inspect`.)

---

## Chat UI

Alongside the REST API, the harness ships a browser-based chat — no separate service, no second port.

Open it after either quickstart above:

```
http://localhost:8000/
```

The chat UI and the REST API share the exact same process, port, and query pipeline (identity resolution → duplicate check → pattern check → PII redaction → OpenRouter call → audit log): a prompt sent from the chat produces the identical audit row a `curl -X POST /query` call would.

**Session identity** — on first load, the chat presents a login form asking for a bearer token (the same credential issued by `scripts/manage_users.py` or `ADMIN_TOKEN`), rendered as a password-style input. The token is held only in a backend-only Reflex var (`_token`, never serialized to the client) and is never cached as a role — every message re-resolves the identity, and therefore the role, from the database via the same `identity.resolve()` used by `POST /query`. An invalid or expired token shows an inline error on the login form and never reaches the chat.

**Message rendering** — your own messages render right-aligned; a successful model response renders as a left-aligned assistant bubble. A blocked message (duplicate within 24h, or a suspicious pattern match) renders as a distinct centered bubble carrying the same `reason` text the REST API returns — it is never silently dropped.

**Known limitations (MVP)**

- No token-by-token streaming — the full response renders once available, same as `POST /query` today.
- No persisted chat history — messages do not survive a page reload or a new browser session.
- A denied query (missing permission, disallowed model, or BYOK without `query:byok`) renders as an in-thread bubble, not a session error — the same rendering path as a duplicate or injection block.
- No visible indicator when PII is masked — redaction still applies to every chat message, but the UI does not yet surface *that* it happened (the REST API does, via `pii_redacted`).

---

## Persistence & Deployment

### Where state lives

Both tables the harness owns — `audit_logs` and `users` — live in a [Turso](https://turso.tech) (libSQL) database, reached over the network. There is no database file in the repository, in the image, or in the compose stack, and there is no local-file fallback: a `sqlite:` `DATABASE_URL` is a startup error rather than a file, deliberately, because a local database written to an ephemeral container layer is read by nobody and backed up by nobody.

To provision one: create a database, take its `libsql://<database>-<org>.turso.io` URL and an auth token, and put both in `.env` as `DATABASE_URL` and `TURSO_AUTH_TOKEN`. Any libSQL endpoint works — the local dev server on `http://` is the same contract without the token.

### Multiple instances

Several application instances may now share one database. That is what this migration bought: the audit trail is no longer an artifact of one container's filesystem, and `init_db()` converges correctly when instances start against the same database simultaneously, rather than racing each other through the schema migration.

**What is not included.** The database blocker is gone; the deployment topology is not built:

- **No load balancer or health-check configuration** is provided or documented here.
- **No Reflex websocket session affinity.** The chat UI holds a websocket per session, so placing instances behind a round-robin balancer without sticky sessions is not a supported configuration today.
- **No production two-instance validation yet.** Running two instances against one database is designed for and expected to work, but the end-to-end proof is still outstanding work, not a completed test.

Treat multi-instance as *unblocked*, not *delivered*.

### The database is a hard dependency of every request

With the local file gone, every `POST /query` makes network round trips it never used to — one for the duplicate check, one for the audit write. Retry, circuit-breaker, and offline-buffering behavior are deliberately outside the current scope, which has a consequence worth knowing before you size a deployment rather than during an incident: **a transient database outage fails requests instead of degrading them.** Endpoints that previously could not fail on storage now can.

There is one existing exception, preserved on purpose: duplicate checking still degrades gracefully — a storage failure there lets the query through rather than rejecting it, because a failed duplicate check is not a reason to deny a user. Resilience work is the first item on the roadmap beyond this migration.

### Migrating an existing SQLite deployment

If you are upgrading a deployment that still holds a legacy `harness_ai.db`, `scripts/migrate_to_turso.py` copies `audit_logs` and `users` out of that file and into the database `DATABASE_URL` names.

```bash
python scripts/migrate_to_turso.py --source harness_ai.db --dry-run   # reports counts, writes nothing
python scripts/migrate_to_turso.py --source harness_ai.db             # copies, then verifies
```

Four properties matter when you run it:

- **The source file is opened read-only and is never modified.** It stays authoritative until verification passes, and the script never deletes it — that is your decision, afterwards.
- **A non-empty destination is refused, and there is no `--force`.** One file, one run. If your rows are spread across several files, only one of them can be copied.
- **Verification is not optional.** The script checks per-table counts, compares every row by column name, confirms `audit_logs.id` values are preserved rather than regenerated, and reads a sample back through the application's own accessors. Any mismatch exits non-zero.
- **Delete the source only after a clean run.** If the live database is inside a Docker volume rather than in the repository, extract it from the volume first — the file in your working tree may not be the one your deployment has been writing to.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENROUTER_API_KEY` | Yes | — | API key used to call the upstream LLM provider via OpenRouter. |
| `ADMIN_TOKEN` | Yes | — | Break-glass bearer token that always resolves to the `admin` role, independent of the `users` table. Not the primary auth mechanism — issue individual tokens with `scripts/manage_users.py` instead. |
| `DATABASE_URL` | Yes | — | libSQL endpoint for the `audit_logs` and `users` database: `libsql://<database>-<org>.turso.io`, `https://...`, or `http://127.0.0.1:8080` for the local dev server. No default, and a `sqlite:` value is a startup error — the local-file path was removed deliberately, not deprecated. |
| `TURSO_AUTH_TOKEN` | Yes for remote | — | Bearer token for the database. Required whenever `DATABASE_URL` is `libsql://` or `https://`; unused by the local `http://` dev server, which takes no token. Never logged — configuration errors quote the URL's scheme only, never the URL itself. |
| `DB_BOOTSTRAP_ENABLED` | No | `true` | Whether startup probes the database and applies the schema. The only sanctioned `false` is the Docker builder stage, where the image must build with no database reachable. `false` in a running deployment boots an application whose schema was never created. |
| `PORT` | No | `8000` | Port the FastAPI server listens on. |
| `HOST` | No | `0.0.0.0` | Host/interface the server binds to. |
| `LOG_LEVEL` | No | `INFO` | Log verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `RBAC_ENABLED` | No | `true` | Deny-by-default authorization enforcement. `false` preserves exact pre-RBAC (PRD-001) behavior — a documented migration escape hatch, not a normal operating mode. |
| `RBAC_DEFAULT_ROLE` | No | `user` | Role assigned by `scripts/manage_users.py create-user` when `--role` is omitted. |
| `RBAC_ROLES_FILE` | No | — (empty) | Optional path to a JSON role→permission matrix overriding the built-in default. A malformed file or an unrecognized permission fails startup rather than silently falling back. |
| `MODEL_ALLOWLIST` | No | `gpt-4,claude-3-sonnet,openai/gpt-4o,anthropic/claude-3.5-sonnet` | Comma-separated models a `user`-role caller may request. Validated server-side; `admin` bypasses this list entirely. |
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
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "my name is Maria Gomez, my email is juan@empresa.com"}'
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

The token identifies the caller — the request body's `user_id`, if present, is accepted only for backward compatibility and must match the authenticated identity or the request is refused with `403` (`user_id does not match the authenticated identity`).

### `POST /query` — 401 (no or invalid credential)

```json
{"detail": "Invalid or missing credential"}
```

Missing header, unknown token, or a deactivated user all map to this same response — deliberately indistinguishable, so a caller cannot enumerate valid credentials.

### `POST /query` — 403 (authenticated, lacks `query:submit`)

```json
{"detail": "Permission denied: query:submit"}
```

The `auditor` role holds no `query:submit` permission by default, so it always gets this response from `POST /query`. In the chat UI, the identical decision renders as an in-thread bubble rather than a session error, because the browser ingress has no router layer to enforce it at.

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

### `POST /query` — 200, refused by policy

```json
{
  "status": "BLOCKED",
  "reason": "Model not permitted for this role",
  "required_permission": "query:model:claude-3-opus"
}
```

Model-allowlist and BYOK (`openrouter_api_key`) refusals return `200` with this shape, not `403` — the caller is authenticated and allowed to call the endpoint, but the content of the request is what's refused. This is the same rendering path as a duplicate or injection block.

### `GET /audit` (requires `audit:read:all` or `audit:read:own`)

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
      "pii_entities": ["EMAIL_ADDRESS", "PERSON"],
      "role": "user",
      "denied_permission": "query:byok"
    }
  ]
}
```

`pii_entities` is the union of types masked in either direction. The audit trail deliberately stores the **raw, unmasked** prompt and response previews in the database — an auditor investigating an incident needs the actual value, not `<EMAIL_ADDRESS>` — but this endpoint exposes neither the raw previews nor the masked text, only the flags above.

`audit:read:all` returns every row; with only `audit:read:own`, the response contains solely the caller's rows and `total` reflects that scoped count. An identity holding neither permission gets `403` `{"detail": "Permission denied: audit:read:own"}` (the last permission attempted). `role` and `denied_permission` are populated on every row — `null` for rows written before this control existed or for a successful, non-denied query.

### `GET /stats` (requires `stats:read`)

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

A missing or invalid credential on any endpoint returns `401`. An authenticated identity that lacks the endpoint's required permission (e.g. a `user` role calling `GET /stats`) returns `403` with `{"detail": "Permission denied: stats:read"}`.

---

## Running Tests

The PII tests load the real `en_core_web_lg` model, so run the `spacy download` step from [Quickstart — Local](#quickstart--local) first — otherwise the first test run spends several minutes downloading it. The in-container run needs nothing extra (the image already has it).

The suite needs a libSQL server to run against. **No Turso account is required** — the tests use a local server that runs offline, takes no token, and never touches a hosted database:

```bash
docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary \
  ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67
```

The tests default to `http://127.0.0.1:8080`; set `HARNESS_TEST_LIBSQL_URL` to point them somewhere else if that port is taken (`tests/conftest.py`).

Locally:

```bash
pytest tests/ -v
```

Inside the Docker container:

```bash
docker-compose run --rm \
  -e HARNESS_TEST_LIBSQL_URL=http://host.docker.internal:8080 \
  -e DATABASE_URL=http://host.docker.internal:8080 \
  -e TURSO_AUTH_TOKEN= \
  harness-ai pytest tests/ -v
```

All three overrides are required, for three different reasons. The container inherits its environment from `.env` through `env_file`, so without them each of these would be the deployment's value rather than a test value:

- `HARNESS_TEST_LIBSQL_URL` points the test fixtures at a server they can actually reach. Inside a container, `127.0.0.1` is the container's own loopback, not your host — without this the run fails immediately with a connection error.
- `DATABASE_URL` overrides the value `env_file: .env` injects into the container. The test suite's own default is applied with `setdefault`, which cannot override a variable the process already inherited, and one test in `tests/test_db.py` calls `monkeypatch.undo()` — which also reverts the autouse fixture that redirects each test at an isolated database. Everything after that line runs against whatever `DATABASE_URL` the container was started with. **Without this override, an in-container test run can reach the database named in your `.env` — including a production one.** Always pass it.
- `TURSO_AUTH_TOKEN=` (deliberately empty) keeps the deployment's real credential out of the test process. `tests/test_config.py` asserts that a local `http://` endpoint is accepted *without* a token and that an `https://` endpoint is rejected *for lacking* one; an inherited token makes both assertions false and produces two failures that have nothing to do with your change.

On Linux, `host.docker.internal` is not resolvable by default; add `--add-host=host.docker.internal:host-gateway` to the command above.

**A known collection error, and when it does *not* apply.** Running `tests/test_pii_badge.py` or `tests/test_success_metadata_footer.py` **on their own** fails at collection with `ModuleNotFoundError: No module named 'chat_ui.chat_ui.models'; 'chat_ui.chat_ui' is not a package`. This is a packaging problem, not a database one, and it does not affect a whole-suite run: collecting the full `tests/` directory imports `chat_ui.chat_ui` as a package first, and both modules then pass. If you need to run either file in isolation, expect this error until the packaging is fixed.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'fastapi'`**
Run `pip install -r requirements.txt`.

**`OPENROUTER_API_KEY not found` on startup**
Copy `.env.example` to `.env` and fill in a real key.

**`DATABASE_URL must name a libSQL endpoint, not a file` at startup**
Your `.env` still carries a `sqlite:` URL from before the Turso migration. `DATABASE_URL` now names a network endpoint (`libsql://...`, `https://...`, or `http://127.0.0.1:8080` for the local dev server), and a file path is rejected rather than quietly created — see the [Environment Variables](#environment-variables) table. The full message names the replacement to use.

**`TURSO_AUTH_TOKEN is required when DATABASE_URL names a remote endpoint` at startup**
A `libsql://` or `https://` endpoint needs its token; the check fires before anything is dialled, so this is a configuration error rather than a connection failure. The local `http://` dev server takes no token — leave `TURSO_AUTH_TOKEN` empty for it.

**`DatabaseUnreachableError: Cannot reach the database at <endpoint>`**
The endpoint is not reachable from this host, and the application refuses to start rather than boot into a broken state. There is deliberately no local-file fallback to degrade to. Check `DATABASE_URL`, network reachability, and — if the endpoint answers but the credential is refused — expect `DatabaseAuthError` instead, which means `TURSO_AUTH_TOKEN` is wrong or expired rather than the host being down. The message quotes the driver's own reason at the end.

**Docker container exits immediately**
Check logs with `docker-compose logs harness-ai`. If the traceback ends in `sqlite3.connect` — a call the current code no longer contains — you are running an image built before the Turso migration: `docker-compose up` reuses an existing image rather than rebuilding it. Rebuild with `docker-compose up -d --build`.

**First startup stalls while downloading several hundred MB**
That is spaCy fetching `en_core_web_lg` because it was never installed — Presidio downloads a missing model on first use rather than failing. Run `python -m spacy download en_core_web_lg` up front (see [Quickstart — Local](#quickstart--local)) to keep it out of the startup path, or set `PII_REDACTION_ENABLED=false` to skip redaction entirely.

**`[x] No compatible package found for '<model>'` and the process exits during startup**
`PII_NLP_MODEL` names a model spaCy cannot resolve, so the automatic download fails and takes the process down with it. Fix the name, or install that model yourself. Because the model is loaded at startup, this kills the boot rather than the first request. Load failures that are not download failures surface instead as `PiiRedactorError: Failed to load Presidio NLP model '<model>'`.

**Model responses contain `<PERSON>` or `<EMAIL_ADDRESS>` where you expected real text**
That is PII redaction working as designed — the threshold (`PII_SCORE_THRESHOLD`, default `0.35`) deliberately favors over-masking. Raise it, or trim `PII_ENTITIES`, if a specific entity type is too aggressive for your use case.

**`RbacNotBootstrappedError: RBAC_ENABLED=true but no active users exist` at startup**
Bootstrap at least one user: `python scripts/manage_users.py create-user --user-id <id> --role admin`. This is required even when `ADMIN_TOKEN` is set — break-glass does not satisfy the bootstrap guard (`app/services/authz.py`'s `check_bootstrap()`). To migrate an existing deployment without bootstrapping immediately, set `RBAC_ENABLED=false`.

**`401 Unauthorized` on `/query`, `/audit`, or `/stats`**
The `Authorization: Bearer <token>` header is missing, doesn't match any active user's token, or matches a deactivated user. Issue a token with `python scripts/manage_users.py create-user --user-id <id> --role <admin|auditor|user>`, or confirm `ADMIN_TOKEN` in `.env` matches exactly (it always works as break-glass).

**`403 Forbidden` on `/query`, `/audit`, or `/stats`**
The credential is valid, but the role lacks the permission that endpoint requires — for example, an `auditor` calling `/query`, or a `user` calling `/stats`. This is different from `401`: authentication succeeded, authorization did not. See the role→permission matrix in the Features table above, or `app/services/authz.py`.

---

## Roadmap

### Shipped

- [x] Duplicate detection (24h, exact match)
- [x] Prompt-injection blocking (pattern list)
- [x] Full audit logging (Turso / libSQL)
- [x] Chat UI
- [x] PII redaction on input/output
- [x] Role-based access control (RBAC)

### Planned

- [ ] Semantic (not just exact-match) duplicate detection
- [ ] Configurable, per-deployment pattern lists
- [ ] [OpenAI-compatible endpoint](#openai-compatible-endpoint) — drop-in use from OpenCode and other coding agents
- [ ] [MCP servers and agent skills](#mcp-servers-and-agent-skills) — code-writing tools behind the same pipeline
- [ ] [Action policy rules](#action-policy-rules) — deny destructive SQL, shell, and filesystem operations

Everything below this line is **intended direction, not current behavior**. The only ingress that exists today is `POST /query`.

### OpenAI-compatible endpoint

`POST /query` is a shape specific to this project: every client has to be written against it, which is why the chat UI is the only thing that speaks it. The plan is to add `POST /v1/chat/completions` following the OpenAI Chat Completions standard, so tools that already speak it — [OpenCode](https://github.com/sst/opencode), Cline, Continue, Aider, the official OpenAI SDKs — can be pointed at the harness by changing one base URL:

```bash
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_API_KEY=<harness token — never the OpenRouter key>
```

This would be a translation layer, not a second pipeline: it maps the `messages` array onto the existing duplicate → pattern → PII → OpenRouter → audit flow, and maps a block back onto the standard's error shape, so the calling tool surfaces an ordinary API error instead of a malformed completion. The harness becomes the only component holding the real OpenRouter key.

Open design questions:

- How `user_id` and device are carried — a custom header, or the standard's optional `user` field.
- What gets hashed for duplicate detection in a multi-turn conversation — the last user turn only, or the full `messages` array. A coding agent resends most of its context every turn, so a naive whole-array hash would almost never collide, and a last-turn hash would block legitimate retries.
- Whether `stream: true` can be supported at all, given the harness must inspect a complete response before releasing it. A partial answer is buffering upstream and re-emitting as SSE once the checks pass — streaming-shaped, not streaming-latency.

### MCP servers and agent skills

An OpenAI-compatible endpoint invites coding agents, and coding agents do not only produce text — they call tools, and those tools write files, run commands, and query databases. The current text-level checks do not cover that: a prompt can pass the injection filter and still yield a tool call that drops a table.

The plan is to extend interception down to the tool layer:

- **[MCP](https://modelcontextprotocol.io) servers behind the harness** — the harness fronts one or more MCP servers, so tool discovery and every `tools/call` pass through it and land in the audit log next to the prompts that caused them.
- **Skills** — packaged capabilities (write code, open a pull request, run a migration) exposed through that same interception point, so what an agent is allowed to do becomes a deployment decision rather than a client-side one.
- **Tool-call auditing** — one row per call: tool name, arguments, user, allowed or denied. The current `audit_logs` schema records prompts and responses only, so this needs a schema addition.

### Action policy rules

The piece that makes the above safe to enable: a deny-by-default rule set evaluated **before** a tool call executes, occupying the same position for actions that the pattern check occupies for prompts.

| Rule class | Example of what it denies |
|---|---|
| **Destructive SQL** | `DROP`, `TRUNCATE`, `ALTER`, `GRANT`, and `DELETE`/`UPDATE` without a `WHERE` clause — read-only `SELECT` stays allowed |
| **Shell execution** | Arbitrary command execution: `rm -rf`, `curl ... \| sh`, package installs, service restarts |
| **Filesystem writes** | Writes outside an allowlisted workspace path; any edit to `.env`, credential files, or CI configuration |
| **Network egress** | Calls to hosts outside an allowlist — the same exfiltration concern the harness already answers for prompts |
| **Secret access** | Reads of environment variables or files matching secret patterns |

The design intent carries over from the existing checks: a denial short-circuits **before** the action happens, returns a `reason` string the calling agent can display, and is logged with the same rigor as an allowed call — the audit trail has to show what was attempted, not only what succeeded.

These rules are per-deployment configuration, which makes *Configurable, per-deployment pattern lists* a prerequisite for this work rather than an independent nice-to-have. RBAC, already shipped, is the natural pairing: the same `DELETE` can already be denied for one role and allowed for another via the role→permission matrix in `app/services/authz.py` — action policy rules would extend that same deny-by-default model from prompts to tool calls.

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