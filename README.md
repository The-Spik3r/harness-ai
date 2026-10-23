<div align="center">

# Harness AI

**A control-plane interceptor for LLM traffic — duplicate blocking, prompt-injection defense, and full audit logging, in front of any OpenRouter-served model.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED.svg)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](docs/testing.md#running-tests)

<br/>

<img src="docs/media/harness-demo.gif" alt="Harness AI demo: a prompt with personal data is masked, an injection attempt is denied, a repeated prompt is held, then the admin console and the reports section" width="900"/>

<sub>A prompt with personal data is masked · an injection attempt is denied · a repeat is held · every verdict lands in the admin console. <a href="docs/media/harness-demo.mp4">Full-quality video (MP4)</a></sub>

</div>

---

## Table of Contents

- [Problem](#problem)
- [Solution](#solution)
- [Screenshots](#screenshots)
- [Architecture](#architecture)
- [Features](#features)
- [Requirements](#requirements)
- [Quickstart — Local](#quickstart--local)
- [Quickstart — Docker](#quickstart--docker)
- [Chat UI](#chat-ui)
- [Reports](#reports)
- [Documentation](#documentation)
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

**Harness AI** sits between your application (or a human, via the built-in chat UI) and any model served through [OpenRouter](https://openrouter.ai). Every request passes through a fixed pipeline before it is allowed to leave your infrastructure:

```
identity resolution + authorization  →  usage gate  →  duplicate check (24h)  →  prompt-injection check  →  PII redaction (prompt)  →  forward to OpenRouter  →  PII redaction (response)  →  token charge  →  audit log
```

If either check fails, the request is rejected **before** it reaches the model provider, and the rejection is logged with the same rigor as a successful call. Redaction, by contrast, never rejects anything — it only masks. An unverified or unauthorized request never reaches the duplicate check at all.

---

## Screenshots

| | |
|---|---|
| ![Sign-in form asking for an access token](docs/screenshots/login.png) | ![Empty chat listing the three things the harness does](docs/screenshots/chat-empty.png) |
| **Sign in** — every prompt is recorded against a verified identity. | **Chat** — the empty state names the three verdicts before anything is sent. |
| ![Assistant reply with email, person and phone number masked](docs/screenshots/chat-pii-masked.png) | ![An injection attempt denied and a repeated prompt held](docs/screenshots/chat-blocked.png) |
| **PII redaction** — names, emails and phone numbers are masked before and after the model. | **Blocked** — a matched injection pattern is *denied*; an exact repeat within 24h is *held*. |
| ![Audit register with one denied row expanded](docs/screenshots/admin-audit-detail.png) | ![Summary figures for traffic, users and models](docs/screenshots/admin-stats.png) |
| **Admin · Register** — every request, blocked or not, with the matched pattern and prompt hash. | **Admin · Summary** — totals across the whole audit table. |
| ![Reports feed of completed stories](docs/screenshots/reports-feed.png) | ![A single story report in the light theme](docs/screenshots/reports-story-light.png) |
| **Reports** — the build history, read straight from `.agents/`. | **Light theme** — one icon in every masthead switches the ground. |

All captures were taken from a running instance with [agent-browser](https://www.npmjs.com/package/agent-browser); the personal data in them is invented.

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
        │   Harness AI (FastAPI)│
        │                       │
        │  0. Resolve identity  │◄──── Turso (users)
        │     + authorize       │
        │  1. Usage gate        │◄──── Turso (usage_daily)
        │     (admit / refuse)  │
        │  2. Validate request  │
        │  3. Hash prompt       │
        │  4. Duplicate check   │◄──── Turso (audit_logs)
        │     (24h window)      │
        │  5. Pattern check     │
        │     (prompt injection)│
        │  6. PII redaction     │
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
        │   Charge tokens       │────► Turso (usage_daily)
        │   (reported usage)    │
        └───────────┬───────────┘
                     ▼
        ┌───────────────────────┐
        │   Audit log write     │────► Turso (audit_logs)
        │  user · device · hash │
        │  model · tokens · flag│
        └───────────┬───────────┘
                     ▼
              Response to caller
                     │
                     │ chat UI only, after the pipeline has returned
                     ▼
        ┌───────────────────────┐
        │   Transcript write    │────► Turso (chat_sessions,
        │   (owner-scoped)      │              chat_messages)
        └───────────────────────┘
```

Blocked requests (missing/invalid credential, missing permission, usage limit, duplicate, or suspicious pattern) short-circuit before the provider — the model provider is never called, and the block is still logged. The usage gate sits right after step 0's authorization: it counts the attempt in Turso (`usage_daily`) and refuses a user over a limit, and after the provider answers, the tokens it reported are charged back to the same row — see [Usage limits](docs/features.md#usage-limits). Redaction sits after every check, so a blocked request is never analyzed for PII. The diagram shows the `chat` profile, the one both ingresses run; under the `code` profile the response-redaction box is skipped and `system` turns are not redacted — see [PII redaction](docs/features.md#pii-redaction).

The transcript write is **not** a pipeline step. It happens in the chat UI after the pipeline has returned, it is allowed to fail without taking the answer with it, and `CHAT_HISTORY_ENABLED=false` removes it entirely — which is why removing it leaves the request pipeline exactly as the previous release ran it. `POST /query` writes no transcript at all; it only records which conversation a row belonged to.

---

## Features

| Capability | Description |
|---|---|
| **Single entry point** | `POST /query` intercepts every prompt/response pair; nothing reaches OpenRouter without passing through it. |
| **Chat UI** | A browser-based chat served from the same port and process as the API, running through the identical pipeline as `POST /query`. |
| **Role-based access control** | Every request is resolved to a verified `Identity` from a per-user bearer token — no self-declared `user_id` is trusted. Three fixed roles (`admin`, `auditor`, `user`) each hold an explicit permission set; deny-by-default for any unmapped role or permission. `ADMIN_TOKEN` remains a break-glass admin credential, not the primary auth mechanism. |
| **Duplicate blocking** | Exact-match (word-for-word) detection of a prompt the **same account** already had answered within a rolling 24-hour window. Scoped per user, never across users — see [Duplicate detection scope](docs/features.md#duplicate-detection-scope). |
| **Prompt-injection blocking** | Word-boundary matching against a per-deployment pattern file, applied per message role: the caller's own turns are blocked on a hit, and an instruction planted in a tool result is flagged in the audit rather than blocked. See [Pattern policy](docs/features.md#pattern-policy). |
| **PII redaction** | Under the `chat` profile (`POST /query` and the chat UI), [Microsoft Presidio](https://microsoft.github.io/presidio/) masks personal data (names, emails, phone numbers, cards, SSNs, IBANs, locations) in the outbound prompt and its history before they reach OpenRouter, and in the model's response before it reaches the caller. Masking never blocks a `chat` request, and the audit log keeps the raw text. A `code` profile for coding agents masks prose only, runs pattern recognizers only, leaves the response alone, and refuses a request too large to analyze. See [PII redaction](docs/features.md#pii-redaction). English-only in this release. |
| **Full audit logging** | Every request — success or blocked — writes one row to the `audit_logs` table in Turso: user, device, hashed prompt/response with a 500-character preview, model, tokens (input and output), flags, and timestamp, plus the ingress it came through, its message count and a conversation key that groups an agent's turns. IP addresses and geolocation are never captured. |
| **Persisted chat sessions** | The chat UI holds named, per-conversation transcripts in Turso — restored on reload, on a new browser session, and from any instance sharing the database. Each transcript is readable only by the account that wrote it; no admin surface exposes one. `CHAT_HISTORY_ENABLED=false` turns the whole feature off, from the same image. |
| **Multi-turn context** | The chat sends the conversation, not just the latest message: every answered exchange in the session that fits the configured limits goes upstream, redacted, on every send. The pipeline takes a list of messages; `POST /query` is the one-message case and is unchanged. See [Multi-turn context](docs/features.md#multi-turn-context). |
| **Usage limits** | A daily token budget and a per-minute request rate for every user, set by role with per-user overrides, on by default, and held in the shared database so a second instance does not double them. A user over a limit gets a `BLOCKED` answer saying when to try again, never a `429`, and the refusal is audited. See [Usage limits](docs/features.md#usage-limits). |
| **Admin endpoints** | `GET /audit` and `GET /stats` expose the last 100 audit entries and aggregate statistics, gated behind a bearer token. The admin console adds a Usage page: what each user has used today. |
| **Docker parity** | Identical behavior via `python app.py` or `docker-compose up` — no environment-specific branches. |
| **Model-agnostic** | Works with any model OpenRouter serves — Claude, GPT, or others — with no code changes. |

## Requirements

- Python 3.9+. The pinned `libsql==0.1.11` publishes wheels for CPython 3.9–3.13 on Windows, 3.10–3.13 on macOS, and 3.8–3.14 on Linux; on any other interpreter `pip install` falls back to building the Rust source distribution, which needs a working toolchain. The Docker image is `python:3.11`.
- Docker & Docker Compose (optional, for containerized deployment)
- An [OpenRouter](https://openrouter.ai) API key
- A Turso database, or any libSQL endpoint — `DATABASE_URL` has no default and the application will not start without one (see [Persistence & Deployment](docs/deployment.md#persistence--deployment))
- For running the test suite only: a local libSQL server for the storage tests (see [Running Tests](docs/testing.md#running-tests)); `pytest -m "not db"` needs none — no Turso account needed
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

`DATABASE_URL` has no default: without it the process exits on a configuration error before it serves anything. A local libSQL server is enough for a first run — set `DATABASE_URL=http://127.0.0.1:8080` and leave `TURSO_AUTH_TOKEN` empty (see [Running Tests](docs/testing.md#running-tests) for the one-line `docker run`). A Turso database needs both values, and a `sqlite:` URL is a startup error rather than a file. See [Persistence & Deployment](docs/deployment.md#persistence--deployment).

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

The audit trail lives in Turso, reached over the network, so the container holds no database and no volume is involved. Restarting, rebuilding, or tearing the stack down — `docker compose down -v` included — does not touch the audit history. See [Persistence & Deployment](docs/deployment.md#persistence--deployment).

The image bakes `en_core_web_lg` in at build time, so no model download happens at container start — without it, a fresh container would pull ~400 MB before serving its first request. This makes the image substantially larger: measured with `docker image inspect`, the pre-PII image was 131 MB and the current one is 628 MB (of which ~446 MB is the model layer), and the first build spends ~40 s downloading it. Accepted tradeoff — see PRD-003 Risk 5. (`docker images` reports larger figures for the same images on containerd-backed installs; the numbers above use `docker image inspect`.)

---

## Chat UI

Alongside the REST API, the harness ships a browser-based chat — no separate service, no second port.

Open it after either quickstart above:

```
http://localhost:8000/
```

The chat UI and the REST API share the exact same process, port, and query pipeline (identity resolution → duplicate check → pattern check → PII redaction → OpenRouter call → audit log): a prompt sent from the chat produces the identical audit row a `curl -X POST /query` call would.

<p align="center">
  <img src="docs/screenshots/chat-blocked.png" alt="Chat transcript: a masked reply, an injection attempt denied, and a repeated prompt held" width="800"/>
</p>

**Session identity** — on first load, the chat presents a login form asking for a bearer token (the same credential issued by `scripts/manage_users.py` or `ADMIN_TOKEN`), rendered as a password-style input. The token is held only in a backend-only Reflex var (`_token`, never serialized to the client) and is never cached as a role — every message re-resolves the identity, and therefore the role, from the database via the same `identity.resolve()` used by `POST /query`. An invalid or expired token shows an inline error on the login form and never reaches the chat.

**Message rendering** — your own messages render right-aligned; a successful model response renders as a left-aligned assistant bubble. A blocked message (duplicate within 24h, or a suspicious pattern match) renders as a distinct centered bubble carrying the same `reason` text the REST API returns — it is never silently dropped.

**Session rail** — the chat keeps named conversations, listed down the left. **A chat is created on the first send, never on page load**: opening the app and typing nothing leaves no row behind. That first prompt also names the chat, automatically, and you can rename it afterwards. The rail lists your own chats newest-activity-first with the current one marked; sending in a chat moves it to the top, and renaming deliberately does not — it would move the row you are looking at while you are looking at it. It lists at most `CHAT_SESSION_LIMIT` chats and states its window against your real total (`50 most recent of 212`), so a capped list never reads as a complete one. It has three states and they are distinct: your chats, an invitation when you have none, and a read-failure notice that says nothing on screen has changed. Below a narrow viewport it collapses behind a **Chats** control. Deleting asks first, and says what it will and will not remove.

**Known limitations (MVP)**

- No token-by-token streaming — the full response renders once available, same as `POST /query` today.
- **The context limits are characters, not tokens.** `CONTEXT_MAX_CHARACTERS` counts characters across message contents — a deliberate proxy, because counting tokens means carrying a per-model tokenizer the harness does not have. Budget conservatively: for English prose, ~200,000 characters is roughly 50,000 tokens, and code runs denser.
- **Every user turn is checked for patterns on every send, history included.** The chat runs the `chat` profile, which inspects each `user` turn in the conversation and no `assistant` turn. The consequence worth knowing: after an operator adds a pattern to the patterns file, a chat whose *earlier*, already-answered question contains it is blocked on every further send, because that question is re-inspected each time the history goes upstream. Start a new chat to continue. See [Pattern policy](docs/features.md#pattern-policy).
- **The PII audit fields describe the new turn and the output, not the history.** `pii_detected_input` and `pii_entities` on an audit row cover the message you just sent plus the model's reply. Entities found while re-masking history are masked but not recorded again — otherwise one email in the first turn would mark every later send of that session as a PII event and inflate the figures in `/stats` and the admin console.
- **The first send of two new chats with the same text is still a duplicate.** Two brand-new chats both start as a single turn, so within 24 hours the second is indistinguishable from repeating a `POST /query` call — and that is held, by design. Once a chat has an exchange behind it its history is part of the key, so *"yes"* after two different conversations is two different queries. See [Duplicate detection scope](docs/features.md#duplicate-detection-scope).
- **Redacted history can make answers less precise.** The model sees `<PERSON>` where you wrote a name, in every earlier turn as well as the current one, so a conversation that turns on the specifics of masked data will read as vaguer than the transcript on your screen. The trade is deliberate: unmasked text never leaves the process.
- **The first turn of a brand-new chat is not saved.** The session row is created after your prompt is already on screen — deliberately, so a slow write never delays what you typed — so reloading a first conversation begins at the assistant's reply. Every turn after it is saved in full.
- Two tabs open on the same chat do not see each other's writes. Each loads its own view and the second one to write simply wins.
- A denied query (missing permission, disallowed model, or BYOK without `query:byok`) renders as an in-thread bubble, not a session error — the same rendering path as a duplicate or injection block.

---

## Reports

`/reports` is a read-only, navigable changelog of how this project was built: every story the workflow completed, newest first, read straight from `.agents/`. It needs no token — the PRDs, stories and implementation reports it renders are already public in the repository.

<p align="center">
  <img src="docs/screenshots/reports-story.png" alt="A story report: summary, acceptance criteria and the PRD sidebar" width="800"/>
</p>

| Route | Shows |
|---|---|
| `/reports` | Every story across every PRD, newest first |
| `/reports?status=done` · `in-progress` · `planned` · `blocked` | The same feed, filtered by status |
| `/reports?q=text` | The same feed, filtered by story id, title, PRD or commit |
| `/reports/prd-008` | One PRD's stories; the sidebar marks it |
| `/reports/prd-008/story-019` | One story's report: summary, acceptance criteria, files changed, validation results, and its neighbours in the PRD |

Identifiers in the URL are the short ids in any case (`prd-008`, not `PRD-008-chat-sessions`); the folder is resolved by prefix. The filters are query parameters on either feed route, so a filtered view is a shareable link.

What it reads, all through `app/services/reports.py`: `.agents/PRDs/*/index.md` for each PRD's name and progress, `.agents/stories/*/*.md` for titles and status, and `.agents/reports/*/*.report.md` for the report itself — frontmatter via `python-frontmatter`, sections by their fixed `##` headings. Parsed results are cached in memory and rebuilt when any of those files or folders changes. A missing `.agents/reports` renders an empty feed; a record that exists but cannot be read renders a distinct fault state; a single report with broken frontmatter is logged and left out without affecting the rest.

Commit SHAs link to `REPORTS_REPO_URL`. The Docker image copies `.agents/PRDs`, `.agents/stories` and `.agents/reports` so the section has content in a container; point `REPORTS_AGENTS_DIR` elsewhere to read a different checkout.

---

## Documentation

The deep reference lives in [`docs/`](docs/) — the README stays focused on what the project is, how it looks, and how to run it.

| Doc | What's in it |
|---|---|
| [Features in depth](docs/features.md) | Duplicate-detection scope, multi-turn context, pattern policy, PII redaction and usage limits — full behaviour and the threat reasoning behind each. |
| [Configuration](docs/configuration.md) | Every environment variable, its default, and what it changes. |
| [API reference](docs/api.md) | `POST /query`, `GET /audit` and `GET /stats` — every request and response shape. |
| [Persistence & deployment](docs/deployment.md) | Where state lives, what is stored and who can read it, multi-instance notes, and migrating off SQLite. |
| [Testing](docs/testing.md) | Running the suite, the libSQL diagnostics verdicts, and troubleshooting. |
| [Roadmap](docs/roadmap.md) | Shipped, next up, and design notes for the planned work. |

---

## Roadmap

**Shipped** — duplicate detection, prompt-injection blocking, full audit logging (Turso / libSQL), the chat UI, PII redaction on input and output, RBAC, persisted chat sessions, multi-turn context, a configurable per-deployment pattern policy, PII redaction for code, and per-user usage limits.

**Next up** — provider resilience: retry, circuit breaker and offline buffering in front of the database, a second provider as fallback to OpenRouter, and websocket session affinity so the harness can run behind a load balancer. This is the first work beyond the Turso migration, because today a transient database or provider outage fails requests rather than degrading them — see [The database is a hard dependency of every request](docs/deployment.md#the-database-is-a-hard-dependency-of-every-request).

**Planned** — semantic (not just exact-match) duplicate detection, an OpenAI-compatible endpoint, MCP servers and agent skills behind the same pipeline, and action policy rules for tool calls.

The full roadmap, with design notes for each planned item, is in **[docs/roadmap.md](docs/roadmap.md)**.

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
