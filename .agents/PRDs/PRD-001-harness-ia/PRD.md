---
id: PRD-001
slug: harness-ia
title: Harness IA - MVP
status: draft
base_branch: main
epic_branch: epic/PRD-001-harness-ia
created: 2026-07-04
updated: 2026-07-04
---

## 1. Executive Summary

Harness IA is a control interceptor that sits between an organization's users and third-party LLM providers (via OpenRouter, covering Claude, GPT, and other models). Every prompt and every model response is routed through the harness, which enforces three guarantees before/after the call: no exact-duplicate query is sent twice within a 24-hour window, no request containing a basic prompt-injection pattern reaches the model, and every interaction is fully audited (who, what, when, device) without ever storing IP addresses or precise location data.

The core problem this solves is uncontrolled, duplicate, or adversarial traffic to LLMs from within an organization — which risks unintentional retraining exposure, wasted spend, and prompt-injection compromise — while giving admins a lightweight, privacy-respecting audit trail. The MVP is intentionally narrow: exact-match duplicate detection (not semantic), a fixed list of injection patterns (not ML-based detection), and SQLite for storage (no external DB dependency).

The MVP goal is a single FastAPI service, runnable identically via `python app.py` or Docker, that fronts OpenRouter, blocks the two failure modes above, logs every request/response to SQLite, and exposes `/audit` and `/stats` for admins — all within a <500ms overhead budget and supporting up to 50 concurrent users.

## 2. Mission

Protect organizations from unintentional data leakage and duplicate LLM training exposure by acting as a transparent, auditable gatekeeper between users and any LLM provider.

Core principles:
- **Privacy first**: never store IPs, geolocation, or any data beyond what's needed to prove who did what and when.
- **Model-agnostic**: works with any model OpenRouter can reach — no lock-in to a single provider.
- **Fail loud, not silent**: blocked requests return a clear, structured reason — never a silent drop.
- **Simple over clever**: exact-match duplicate detection and pattern-list injection detection, not ML — predictability over sophistication in the MVP.
- **Portable by default**: identical behavior running locally (`python app.py`) or in Docker.

## 3. Target Users

**Security/Compliance Admin** — Deploys and monitors the harness for an organization. Needs to see aggregate stats (`/stats`) and detailed audit trails (`/audit`) to prove compliance and spot abuse, without ever handling raw IP/location data. Technical level: comfortable with REST APIs and env var configuration, not necessarily a Python developer.

**End User (Employee)** — Sends prompts to LLMs through internal tooling that calls the harness instead of OpenRouter directly. Wants fast, transparent responses and a clear explanation when a request is blocked (duplicate or suspicious pattern). Technical level: non-technical to technical, interacts only via whatever client app wraps `/query`.

**Integrating Developer** — Wires the harness into existing internal tools that previously called OpenRouter directly. Wants a drop-in-compatible API surface, clear env var configuration, and a Docker Compose setup that "just works." Technical level: experienced backend developer.

## 4. MVP Scope

### In Scope
- [ ] Single `POST /query` endpoint that intercepts prompt in and response out
- [ ] Exact-match (word-for-word) duplicate detection within a rolling 24h window, per prompt hash
- [ ] Basic prompt-injection pattern blocklist (string/substring match, case-insensitive)
- [ ] Full audit logging to SQLite: user_id, device, prompt hash + 500-char preview, response hash + 500-char preview, model, tokens used, timestamp (UTC), duplicate/suspicious flags, success flag, error message
- [ ] `GET /audit` (admin-only) — last 100 audit entries
- [ ] `GET /stats` (admin-only) — aggregate counts (total/blocked/unique users/success rate/top models/top users)
- [ ] OpenRouter integration as the only upstream provider, model selectable per request
- [ ] `user_id` required on every request (simple presence check, not full auth/identity provider integration)
- [ ] Admin token (bearer/shared secret) gating `/audit` and `/stats`
- [ ] Dockerfile + docker-compose.yml, and equivalent local run via `python app.py`
- [ ] Config entirely via environment variables (no config UI)

### Out of Scope
- [ ] Automatic PII redaction
- [ ] Advanced RBAC (roles/permissions beyond a single admin token)
- [ ] Automatic fine-tuning pipelines
- [ ] End-user feedback loop on responses
- [ ] Per-department custom rule sets
- [ ] IP blocking / geolocation-based controls
- [ ] ML-based suspicious pattern detection (regex/string list only in MVP)
- [ ] Semantic/fuzzy duplicate detection (exact-match only in MVP)

## 5. User Stories

1. **As an integrating developer**, I want a single `POST /query` endpoint compatible with OpenRouter's model roster, so that I can swap my existing direct-to-OpenRouter calls for harness calls with minimal changes.
   - Example: `POST /query` with `{"user_id": "juan@empresa.com", "device": "Chrome/Windows", "prompt": "...", "model": "gpt-4"}` returns `{"status": "SUCCESS", "response": "...", "audit_id": "...", "model_used": "gpt-4", "tokens_used": 45}`.

2. **As a security admin**, I want identical queries blocked if repeated within 24 hours, so that the same prompt can't be used to duplicate-train or duplicate-leak information.
   - Example: the same word-for-word prompt sent 2 hours after the first attempt returns `{"status": "BLOCKED", "reason": "Duplicate query within 24 hours", "first_query_at": "2026-07-04T10:30:00Z"}` and never reaches OpenRouter.

3. **As a security admin**, I want basic prompt-injection patterns blocked before they reach the model, so that known attack strings (e.g. "ignore previous instructions") never get forwarded upstream.
   - Example: a prompt containing "ignore previous instructions" returns `{"status": "BLOCKED", "reason": "Suspicious pattern detected", "pattern": "prompt_injection"}`.

4. **As a compliance officer**, I want every query and response logged (hashed + truncated preview) without any IP or geolocation data, so that we have a full audit trail that respects user privacy by construction.
   - Example: `GET /audit` (with valid admin token) returns the last 100 entries, each including `device` but never an IP field.

5. **As a security admin**, I want an aggregate stats view, so that I can monitor system health and spot abuse trends without reading raw logs.
   - Example: `GET /stats` returns `{"total_queries": 250, "blocked_duplicates": 12, "blocked_suspicious": 3, "unique_users": 8, "success_rate": "98.4%", ...}`.

6. **As a devops engineer**, I want the harness to run identically via Docker Compose or `python app.py`, so that local development and production deployment behave the same way.
   - Example: `docker-compose up` and `python app.py` both expose the same API on the configured `PORT`/`HOST`.

7. **As an admin**, I want `/audit` and `/stats` protected by an admin token, so that only authorized staff can see even the hashed/truncated audit data.
   - Example: a request to `/audit` without a valid `ADMIN_TOKEN` bearer value is rejected.

8. **As an end user**, I want a clear, structured error when my request is blocked, so that I understand why (duplicate vs. suspicious pattern) instead of receiving a generic failure.

## 6. Core Architecture & Patterns

```
User → POST /query → FastAPI Harness → OpenRouter API (Claude, GPT, ...)
                          │
                          ▼
                    SQLite (audit_logs)
```

Request pipeline (executed in order, per RF-1 through RF-9):
1. Verify `user_id` present and non-empty
2. Hash prompt (SHA256)
3. Look up prompt hash in `audit_logs` for a match within the last 24h → block if found
4. Scan prompt against the suspicious-pattern list → block if matched
5. Forward to OpenRouter with the requested model
6. Receive response
7. Log everything (hashes, previews, tokens, flags, timestamp) to SQLite
8. Return result to the user

Suggested directory structure:
```
harness-ai/
├── app/
│   ├── main.py                 # FastAPI app, route registration
│   ├── config.py                # env var loading (pydantic Settings)
│   ├── models/
│   │   └── schemas.py           # Pydantic request/response models
│   ├── db/
│   │   ├── database.py          # SQLite connection/session setup
│   │   └── models.py            # audit_logs table definition
│   ├── services/
│   │   ├── duplicate_checker.py # 24h exact-hash lookup
│   │   ├── pattern_detector.py  # injection pattern matching
│   │   ├── openrouter_client.py # OpenRouter API wrapper
│   │   └── audit_logger.py      # writes audit_logs rows
│   ├── routers/
│   │   ├── query.py             # POST /query
│   │   └── admin.py             # GET /audit, GET /stats
│   └── middleware/
│       └── auth.py              # user_id presence + admin token checks
├── tests/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

Design patterns:
- **Pipeline/middleware pattern** for the 8-step request flow in `query.py`, so each step is independently testable.
- **Repository pattern** for `audit_logs` access (`db/database.py`), isolating SQL from route/service logic.
- **Dependency injection** via FastAPI `Depends` for DB sessions and admin-token verification.
- **Strategy pattern** for `pattern_detector.py` — the pattern list (Section 9) is a data-driven list, not hardcoded branching, so it's easy to extend later.

## 7. Tools/Features

| Feature | Maps to | Detail |
|---|---|---|
| Query interception | RF-1, RF-2 | All traffic to/from the model passes through the harness; no direct client-to-OpenRouter path. |
| Duplicate blocking | RF-3, RF-4 | SHA256 hash of the exact prompt string, looked up against entries from the last 24h; word-for-word match only (no normalization/fuzzy matching in MVP). |
| Audit logging | RF-5–RF-9 | Every request writes one `audit_logs` row: user_id, device, timestamp, prompt/response hash + 500-char preview, model, tokens, flags. No IP is ever captured. |
| OpenRouter wrapper | RF-10, RF-11 | Thin client wrapping OpenRouter's chat completion API; model name passed through, defaulting to `gpt-4`. |
| `/query` endpoint | RF-12 | Single entry point accepting `user_id`, `device`, `prompt`, optional `model`, optional per-request `openrouter_api_key`. |
| Suspicious pattern detection | RF-13 | Case-insensitive substring match against the fixed list in Section 9. |
| User identification | RF-14 | `user_id` required on every request; absence is a 4xx rejection before any hashing/forwarding occurs. |
| Docker packaging | RF-15, RF-16 | `Dockerfile` + `docker-compose.yml`; identical behavior to `python app.py` for local runs. |

## 8. Technology Stack

**Backend**
- Python 3.11+
- FastAPI (API framework)
- Uvicorn (ASGI server)
- Pydantic v2 (request/response validation, settings)
- SQLite (via built-in `sqlite3` or SQLAlchemy Core) for `audit_logs` storage
- `httpx` (or `requests`) for the OpenRouter HTTP client
- `hashlib` (stdlib) for SHA256 hashing

**Testing**
- `pytest` + `pytest-asyncio` for unit tests
- `httpx.AsyncClient` / FastAPI `TestClient` for endpoint tests

**Deployment**
- Docker + docker-compose
- `.env` file / environment variables for all configuration (Section 9)

**Dependencies (indicative `requirements.txt`)**
```
fastapi
uvicorn[standard]
pydantic
httpx
python-dotenv
pytest
pytest-asyncio
```

## 9. Security & Configuration

**Auth approach**
- End-user requests: presence check on `user_id` (RF-14). No password/OAuth flow in MVP — identity is asserted by the caller, not verified against an identity provider.
- Admin endpoints (`/audit`, `/stats`): gated by a static `ADMIN_TOKEN` shared secret (bearer header).

**Privacy guarantees**
- No public IPs ever stored (NFR: Privacy).
- No geolocation/location logging.
- Prompts and responses stored only as SHA256 hashes plus a 500-character preview — never the full raw text beyond that preview.

**Environment variables**
```bash
# OpenRouter
OPENROUTER_API_KEY=xxx

# Database
DATABASE_URL=sqlite:///harness_ai.db

# Server
PORT=8000
HOST=0.0.0.0

# Security
ADMIN_TOKEN=secreto123   # Required bearer value for /audit and /stats

# Logging
LOG_LEVEL=INFO
```

**Suspicious pattern list (MVP, case-insensitive substring match)**
```
ignore previous instructions
forget everything
show system prompt
reveal password
execute code
admin mode
override
```

**In scope for MVP security**: user_id presence check, admin-token-gated admin endpoints, basic injection pattern blocking, SHA256 hashing of stored content, no IP/location capture.

**Out of scope for MVP security**: OAuth/SSO, per-user roles/permissions, rate limiting, IP allowlisting, ML-based injection detection.

## 10. API Specification

### `POST /query`
**Request**
```json
{
  "user_id": "juan@empresa.com",
  "device": "Chrome/Windows/Mobile",
  "prompt": "Tu pregunta aquí",
  "model": "gpt-4",
  "openrouter_api_key": "xxx"
}
```
`model` optional (default `"gpt-4"`); `openrouter_api_key` optional (falls back to `OPENROUTER_API_KEY` env var).

**Response — success**
```json
{
  "status": "SUCCESS",
  "response": "La respuesta del modelo",
  "audit_id": "abc123",
  "model_used": "gpt-4",
  "tokens_used": 45
}
```

**Response — blocked (duplicate)**
```json
{
  "status": "BLOCKED",
  "reason": "Duplicate query within 24 hours",
  "first_query_at": "2026-07-04T10:30:00Z"
}
```

**Response — blocked (suspicious pattern)**
```json
{
  "status": "BLOCKED",
  "reason": "Suspicious pattern detected",
  "pattern": "prompt_injection"
}
```

### `GET /audit` (admin token required)
Returns the last 100 logged queries.
```json
{
  "total": 250,
  "queries": [
    {
      "audit_id": "abc123",
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

## 11. Success Criteria

**MVP definition of done**
- [ ] `POST /query`, `GET /audit`, `GET /stats` all implemented and passing tests
- [ ] Duplicate detection blocks 100% of exact-match repeats within 24h
- [ ] Suspicious pattern list blocks all seven listed patterns
- [ ] Every query (success or blocked) produces exactly one `audit_logs` row
- [ ] No IP address or geolocation field exists anywhere in the schema or logs
- [ ] Runs identically via `python app.py` and `docker-compose up`

**Quality indicators (from source PRD Section 11)**

| Metric | Target |
|---|---|
| Duplicates blocked correctly | 100% |
| False positives (pattern detection) | < 1% |
| Response time | < 500ms |
| Uptime | 99% |
| Queries audited | 100% |

## 12. Implementation Phases

**Phase 1 — Setup** (~2 days)
- Goal: bootable FastAPI service with SQLite wired up.
- Deliverables: `app/main.py`, `config.py`, `db/database.py`, `audit_logs` schema migration/creation.
- Validation: service starts locally, health check responds, empty `audit_logs` table exists.

**Phase 2 — Core Logic** (~3 days)
- Goal: duplicate detection + suspicious pattern detection + audit logging.
- Deliverables: `duplicate_checker.py`, `pattern_detector.py`, `audit_logger.py`, unit tests for each.
- Validation: exact-duplicate prompt within 24h is blocked; each of the 7 patterns is blocked; every call (blocked or not) writes an audit row.

**Phase 3 — OpenRouter Integration** (~2 days)
- Goal: working end-to-end call to a real model through OpenRouter.
- Deliverables: `openrouter_client.py`, `POST /query` wired to the full 8-step pipeline.
- Validation: happy-path flow from Section 5.1 of the source doc produces a real model response and a logged audit row with token usage.

**Phase 4 — Admin Endpoints & Testing** (~2 days)
- Goal: `/audit` and `/stats`, admin-token gating, full test suite.
- Deliverables: `routers/admin.py`, `middleware/auth.py`, `pytest` suite covering happy path, duplicate block, pattern block, and admin auth.
- Validation: all endpoints match the API spec in Section 10; unauthorized admin calls rejected.

**Phase 5 — Docker & Documentation** (~1–2 days)
- Goal: portable, documented deployment.
- Deliverables: `Dockerfile`, `docker-compose.yml`, `.env.example`, `README.md` with copy-paste usage examples.
- Validation: `docker-compose up` and `python app.py` produce identical behavior against the same test suite/manual checks.

## 13. Future Considerations

Post-MVP enhancements (explicitly deferred, per source PRD Section 12):
- Automatic PII redaction before logging/forwarding
- Advanced RBAC (per-department roles/permissions)
- Semantic/fuzzy duplicate detection (beyond exact string match)
- ML-based suspicious pattern / prompt-injection detection
- End-user feedback loop on model responses
- Per-department custom rule sets
- Rate limiting and abuse throttling
- Migration path off SQLite (e.g. Postgres) if user count grows meaningfully past 50

## 14. Risks & Mitigations

1. **Risk**: Exact-match duplicate detection is trivially bypassed by rephrasing the same question.
   **Mitigation**: Document this as a known MVP limitation; track as a candidate for semantic dedup post-MVP.

2. **Risk**: Basic substring pattern matching produces false positives (e.g. legitimate use of the word "override" in a business context) or false negatives (trivial obfuscation of blocked phrases).
   **Mitigation**: Keep the pattern list small, case-insensitive, and easily configurable; monitor `/stats` for block rates to catch over-blocking early.

3. **Risk**: SQLite concurrency limits under write-heavy load.
   **Mitigation**: Acceptable given the NFR target of <50 users; document the Postgres migration path for future scale.

4. **Risk**: `ADMIN_TOKEN` as a single static shared secret is a weak auth model if leaked.
   **Mitigation**: Document as an MVP limitation; recommend rotation and treating it as a deployment secret, not a long-term identity solution.

5. **Risk**: OpenRouter outage or latency spike breaks the <500ms NFR and/or causes user-facing failures.
   **Mitigation**: Log failed upstream calls with `success=false` and a clear `error_message`, rather than silently dropping or mis-logging them as successful.

## 15. Appendix

**Related docs**
- Source informal specification: [doc/PRD.md](../../../doc/PRD.md) (original Spanish-language draft; this document formalizes it per the `/create-prd` template)

**Skills referenced**: None — `.agents/skills/` did not exist at the time this PRD was generated.

**Dependencies**
- An OpenRouter account and API key (`OPENROUTER_API_KEY`)
- Python 3.11+ / Docker + Docker Compose for deployment
