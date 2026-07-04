---
id: PRD-002
slug: reflex-chat-ui
title: Harness IA - Embedded Chat UI (Reflex)
status: draft
base_branch: epic/PRD-001-harness-ia
epic_branch: epic/PRD-002-reflex-chat-ui
created: 2026-07-04
updated: 2026-07-04
---

## 1. Executive Summary

Harness IA (PRD-001) ships as a headless FastAPI service: every interaction with the LLM gatekeeper — sending a prompt, checking for duplicates/blocks, reading audit data — happens via `curl`/HTTP clients. That's fine for integrating developers, but it gives end users no direct, human-friendly way to talk to the harness the way they'd talk to Claude or ChatGPT.

This PRD adds a **chat interface embedded in the same deployable unit** as the existing harness — not a separate frontend service, not a second container, not a second port. Built with [Reflex](https://reflex.dev) (Apache 2.0, pure-Python full-stack framework that compiles to a FastAPI backend + React frontend), the chat UI mounts the existing `app/main.py` FastAPI instance via Reflex's `api_transformer` and runs in Reflex's single-port production mode, so `docker-compose up` continues to expose exactly one port serving both the API and the browser-based chat.

The chat UI is a thin presentation layer: every message a user sends goes through the *exact same* pipeline as `POST /query` today (duplicate check → pattern check → OpenRouter call → audit log), so there is no parallel code path to keep in sync and no gap in the audit trail. The MVP goal is: open one URL, type a prompt, see either a model response or a clear "blocked" bubble explaining why — with zero additional infrastructure beyond what PRD-001 already deploys.

## 2. Mission

Give end users a Claude-like way to talk to the harness directly, without adding a second service, a second deployment step, or a parallel code path that could drift from the audited `/query` pipeline.

Core principles:
- **One deployable unit**: the chat UI ships inside the same container/process/port as the API — "portable" stays true, not "two things that happen to be deployed together."
- **No parallel pipeline**: the chat calls the same duplicate-check/pattern-check/audit-log/OpenRouter code the REST API uses — one source of truth for blocking logic.
- **Simple over clever**: no streaming, no multi-room chat, no persisted history in the MVP — a working single-session chat first.
- **Privacy first, inherited**: the chat UI introduces no new data collection beyond what PRD-001 already logs (no IP/geolocation, same hash+preview audit rows).
- **Fail loud, not silent**: a blocked message renders as a distinct, explained chat bubble — never a silently dropped message.

## 3. Target Users

**End User (Employee)** — Same persona as PRD-001, but now interacts through a browser chat window instead of a client app calling `/query` directly. Wants something that feels like talking to Claude: type, send, see a response or a clear reason it was blocked. Technical level: non-technical to technical; no REST/curl knowledge required.

**Security/Compliance Admin** — Unchanged from PRD-001. Continues to use `/audit` and `/stats` via bearer token; this PRD does not add an admin UI. Cares that chat-originated traffic is indistinguishable in the audit log from API-originated traffic.

**Devops/Integrating Developer** — Deploys the harness. Cares that adding a UI doesn't turn one container into two, doesn't add a second port to open in a firewall, and doesn't meaningfully complicate the Docker build.

## 4. MVP Scope

### In Scope
- [ ] Reflex app mounted into the existing FastAPI instance via `api_transformer` (or equivalent single-process integration) — one process, one port
- [ ] Single-page chat UI: message list + input box, Claude-like visual style (avatars, alternating bubble alignment)
- [ ] Chat "send" action reuses the existing `/query` pipeline logic in-process (duplicate check, pattern check, OpenRouter call, audit log) — refactored into a callable service function shared by the REST route and the chat state handler
- [ ] Distinct rendering for `SUCCESS` (model response bubble) vs `BLOCKED` (duplicate) vs `BLOCKED` (suspicious pattern), each with the same `reason` text the API already returns
- [ ] Lightweight session identity: a simple text field where the user enters their `user_id` once per session (no OAuth/login) — same trust model as the existing `user_id` presence check in PRD-001
- [ ] Single Dockerfile/docker-compose update: multi-stage build compiles the Reflex frontend, final image runs one process on the existing `PORT`
- [ ] Existing `POST /query`, `GET /audit`, `GET /stats` continue to work unchanged, reachable on the same port as the chat UI

### Out of Scope
- [ ] Token-by-token streaming of the model response (MVP renders the full response once available, same as today's `/query`)
- [ ] Multi-room / multi-conversation chat, or any persisted chat history across sessions or browsers
- [ ] Model picker / per-message model selection in the UI (uses the same default model as `/query` today)
- [ ] Full auth/login flow for end users (still a free-text `user_id`, per PRD-001's existing trust model)
- [ ] Admin dashboard UI for `/audit` / `/stats` (admins keep using the existing bearer-token REST endpoints)
- [ ] File uploads, voice input, or any Reflex feature beyond a text chat
- [ ] Horizontal scaling / multi-instance websocket considerations (out of scope per PRD-001's existing <50-user NFR)

## 5. User Stories

1. **As an end user**, I want a chat window that looks and feels like Claude, so that I can send prompts to the harness without knowing curl or REST.
   - Example: open `http://localhost:8000/`, type "what is the weather today", press send, see the model's reply appear as a chat bubble.

2. **As an end user**, I want a clearly-labeled blocked message when my prompt is a duplicate or matches a suspicious pattern, so that I understand why I didn't get a normal response.
   - Example: sending the same exact prompt twice within 24h renders a system-style bubble: "Blocked — duplicate query within 24 hours (first sent at 2026-07-04T10:30:00Z)" instead of a model response.

3. **As an integrating developer**, I want the chat UI's send action to call the exact same pipeline function as `POST /query`, so that duplicate detection, pattern blocking, and audit logging behave identically regardless of entry point.
   - Example: a prompt sent via the chat UI and the same prompt sent via `curl -X POST /query` produce audit rows with the same schema and are subject to the same 24h duplicate window (they count against each other).

4. **As a devops engineer**, I want the chat UI and the API to ship in one Docker image on one port, so that deployment stays as simple as `docker-compose up` with no new exposed ports or services.
   - Example: `docker-compose up -d --build` starts one container; `curl http://localhost:8000/health` and opening `http://localhost:8000/` in a browser both work against the same running process.

5. **As a security admin**, I want chat-originated queries to appear in `/audit` and `/stats` with no special-casing, so that compliance reporting doesn't need to distinguish traffic origin.
   - Example: `GET /audit` shows chat-originated and API-originated rows interleaved by timestamp, with identical fields.

## 6. Core Architecture & Patterns

```
Browser (Reflex chat UI, served over WebSocket + static assets)
        │
        ▼
Single ASGI process, single port (PORT, e.g. 8000)
  ├── Reflex app (chat state, event handlers, static frontend)
  │       │  ChatState.send() calls the shared pipeline function directly (in-process)
  │       ▼
  └── Existing FastAPI app (mounted via api_transformer)
          ├── POST /query   → same shared pipeline function
          ├── GET /audit    (unchanged, admin-token gated)
          └── GET /stats    (unchanged, admin-token gated)
                  │
                  ▼
            SQLite (audit_logs) — unchanged schema from PRD-001
                  │
                  ▼
            OpenRouter API — unchanged client from PRD-001
```

Key architectural decision: the `POST /query` route handler's body (duplicate check → pattern check → OpenRouter call → audit log) is extracted into a single reusable function (e.g. `app/services/query_pipeline.py::run_query(...)`) that both the FastAPI route and the Reflex `ChatState` event handler call. This avoids a second implementation of the blocking/audit logic and guarantees the guarantee in User Story 3.

Suggested directory additions (on top of PRD-001's existing `app/` tree):
```
harness-ai/
├── app/
│   ├── main.py                    # existing FastAPI app; also passed as api_transformer target
│   ├── services/
│   │   └── query_pipeline.py      # NEW: extracted run_query(...) shared by route + chat state
│   └── ...                        # unchanged from PRD-001
├── chat_ui/                       # NEW: Reflex app
│   ├── rxconfig.py                 # app_name, api_transformer -> app.main:app
│   ├── chat_ui/
│   │   ├── chat_ui.py              # rx.App() entrypoint
│   │   ├── state.py                # ChatState: messages, input, send() -> run_query(...)
│   │   └── components/
│   │       └── chat.py             # message bubble + input bar (Claude-like styling)
├── Dockerfile                      # updated: multi-stage (node/bun build stage + python runtime stage)
├── docker-compose.yml              # unchanged port mapping; single service
└── tests/
    └── test_chat_state.py          # NEW: unit tests for ChatState.send()
```

Design patterns:
- **Shared pipeline extraction**: `run_query(...)` becomes the single source of truth, called by both the REST route (`routers/query.py`) and the Reflex `ChatState`, per the Strategy/Repository patterns already established in PRD-001.
- **Composition over new service**: Reflex is *mounted into* the existing app (`api_transformer=app.main.app`), not the other way around — the FastAPI app remains the system of record; Reflex adds a UI layer on top.
- **State pattern** (Reflex-native): `ChatState` holds `messages: list[dict]` and `input_text: str`; `send()` is the sole event handler that appends the user message, calls `run_query(...)`, and appends the resulting bubble (success or blocked).

## 7. Tools/Features

| Feature | Maps to | Detail |
|---|---|---|
| Embedded chat UI | New | Reflex-based single-page chat, Claude-like bubble styling, served from the same port as the API. |
| Shared query pipeline | Refactor of PRD-001 RF-1–RF-9 | `run_query(...)` extracted so `POST /query` and the chat's `send()` call identical logic. |
| Blocked-state rendering | New (UI) | Duplicate/pattern block reasons rendered as a distinct chat bubble style, using the same `reason` strings already returned by `/query`. |
| Session `user_id` entry | New (UI), reuses PRD-001 RF-14 | Simple text field collected once per browser session; passed into `run_query(...)` exactly as `POST /query` requires today. |
| Single-port packaging | New | Reflex `--env prod` single-port mode + `api_transformer`; Docker multi-stage build compiles the frontend once, ships no Node runtime in the final image. |
| Unchanged admin endpoints | PRD-001 (no change) | `/audit`, `/stats` keep their existing bearer-token gating; no admin UI added in this PRD. |

## 8. Technology Stack

**Frontend / Chat UI**
- Reflex (pure-Python, compiles to React + FastAPI) — pin an exact version in `requirements.txt`
- Reflex's built-in chat/component primitives, styled to approximate Claude's chat layout (avatars, alternating alignment)

**Backend (unchanged from PRD-001, extended)**
- Python 3.11+, FastAPI, Uvicorn, Pydantic v2, SQLite, `httpx`, `hashlib`
- New: `app/services/query_pipeline.py` extracted from the existing `POST /query` route

**Build/Deploy**
- Node.js or Bun (build-time only, invoked by Reflex's tooling to compile the frontend) — not present in the final runtime image if the Dockerfile uses a multi-stage build
- Docker + docker-compose, single service, single exposed port (unchanged `PORT` env var from PRD-001)

**Testing**
- `pytest` (existing) + new unit tests for `run_query(...)` extraction and `ChatState.send()`
- Existing integration test suite (PRD-001 STORY-012) must continue to pass unmodified against `POST /query`, `GET /audit`, `GET /stats`

**Dependencies (additions to PRD-001's `requirements.txt`)**
```
reflex
```

## 9. Security & Configuration

**Auth approach**
- Unchanged: `/audit` and `/stats` remain gated by `ADMIN_TOKEN`. The chat UI has no admin capability and never sends or displays the admin token.
- Chat session identity: a free-text `user_id` entered once in the browser, carrying the same trust level as the existing presence-check on `POST /query` (not a new identity system).

**Privacy guarantees (inherited from PRD-001, unchanged)**
- No IP address or geolocation captured anywhere, including by the chat UI or its WebSocket transport.
- Audit rows for chat-originated queries use the same hash+500-char-preview scheme as API-originated queries — no raw prompt/response text is stored beyond what PRD-001 already allows.

**New environment variables**
```bash
# Reflex (build/runtime)
REFLEX_ENV=prod          # single-port production mode
```
No other new environment variables; `PORT`, `HOST`, `ADMIN_TOKEN`, `OPENROUTER_API_KEY`, `DATABASE_URL` are reused as-is from PRD-001.

**Reflex reserved routes (must not collide with existing routes)**
- `/ping`, `/_event`, `/_upload` are reserved by Reflex's internal API. PRD-001's existing routes (`/query`, `/audit`, `/stats`, `/health`) do not collide with these; this must be re-verified if any future route is added under those names.

**In scope for MVP security**: reuse of PRD-001's user_id presence check and admin-token gating; no new attack surface beyond the chat UI's own input (which is subject to the same pattern-detection blocklist as any other prompt).

**Out of scope for MVP security**: any new auth mechanism for chat sessions, rate limiting, CSRF/session hardening beyond Reflex's defaults.

## 10. API Specification

No new public REST endpoints are introduced by this PRD. `POST /query`, `GET /audit`, and `GET /stats` retain the exact request/response contracts defined in PRD-001 Section 10, unchanged.

The chat UI communicates with its backend exclusively through Reflex's internal WebSocket event protocol (`/_event`, reserved — see Section 9), not through a new HTTP endpoint. The `ChatState.send()` handler calls the shared `run_query(...)` function in-process (a direct Python call, not an HTTP round-trip), then updates the Reflex state, which pushes the new chat bubble to the browser over the existing WebSocket connection.

## 11. Success Criteria

**MVP definition of done**
- [ ] Opening the harness's single exposed port in a browser shows a working chat UI (not just the REST API)
- [ ] A prompt sent through the chat UI produces the same audit row (schema and content) as an equivalent `POST /query` call
- [ ] A duplicate prompt sent through the chat UI within 24h renders a blocked bubble with the same reason PRD-001's `/query` returns
- [ ] A prompt matching a suspicious pattern renders a blocked bubble with the same reason PRD-001's `/query` returns
- [ ] `docker-compose up` exposes exactly one port; `GET /health`, `POST /query`, `GET /audit`, `GET /stats` all remain reachable and pass PRD-001's existing test suite unmodified
- [ ] Final Docker image does not ship a Node/Bun runtime (multi-stage build discards the frontend build stage)

**Quality indicators**

| Metric | Target |
|---|---|
| Existing PRD-001 test suite | 100% passing, unmodified |
| Chat-vs-API audit row parity | Identical schema for identical inputs |
| Additional exposed ports | 0 (stays at 1) |
| Blocked-reason parity (chat vs API) | 100% match with `/query`'s `reason` strings |

## 12. Implementation Phases

**Phase 1 — Shared pipeline extraction** (~1 day)
- Goal: no behavior change, pure refactor.
- Deliverables: `app/services/query_pipeline.py::run_query(...)` extracted from the existing `POST /query` route handler; route now calls it.
- Validation: PRD-001's existing test suite (STORY-012) passes unmodified against the refactored route.

**Phase 2 — Reflex scaffolding & single-process mount** (~2 days)
- Goal: Reflex app boots and successfully mounts the existing FastAPI app on one port.
- Deliverables: `chat_ui/` Reflex project, `rxconfig.py` with `api_transformer` pointing at `app.main:app`, verified in `--env prod` single-port mode.
- Validation: `GET /health`, `POST /query`, `GET /audit`, `GET /stats` all still reachable on the same port Reflex serves its frontend from.

**Phase 3 — Chat UI components** (~2 days)
- Goal: Claude-like chat interface (static, not yet wired to the pipeline).
- Deliverables: message list, input bar, avatar/bubble styling based on Reflex's chat-bot template.
- Validation: manual UI walkthrough — sending a message renders a user bubble; visual review against the Claude-like reference style.

**Phase 4 — Wire chat to the shared pipeline** (~2 days)
- Goal: chat messages actually flow through `run_query(...)`.
- Deliverables: `ChatState.send()` calling `run_query(...)`, distinct rendering for `SUCCESS` vs both `BLOCKED` variants, session `user_id` entry field.
- Validation: User Stories 1–3 all demonstrated manually; audit rows verified identical for chat vs. `curl` calls of the same prompt.

**Phase 5 — Docker packaging & docs** (~1–2 days)
- Goal: single-image, single-port deployment; documentation updated.
- Deliverables: multi-stage `Dockerfile` (Node/Bun build stage discarded in final image), updated `docker-compose.yml` (if needed), `README.md` updated with a "chat UI" quickstart alongside the existing curl examples.
- Validation: `docker-compose up -d --build` then both `curl http://localhost:8000/health` and opening `http://localhost:8000/` in a browser succeed from a clean build.

## 13. Future Considerations

Post-MVP enhancements (explicitly deferred):
- Token-by-token streaming of OpenRouter responses into the chat bubble
- Model picker dropdown in the chat UI
- Persisted chat history per `user_id` (would require a new table/schema decision)
- Replacing free-text `user_id` entry with a real auth/login flow
- An admin dashboard UI (Reflex page over `/audit` and `/stats`), reusing this PRD's single-process infrastructure
- Multi-instance/horizontal scaling considerations for the WebSocket-based frontend, if user count grows past PRD-001's <50-user NFR

## 14. Risks & Mitigations

1. **Risk**: Reflex's build step requires Node.js/Bun, adding a new toolchain dependency to the Docker build.
   **Mitigation**: Use a multi-stage Dockerfile — the Node/Bun stage compiles static frontend assets only; the final runtime image is Python-only, matching PRD-001's existing image profile.

2. **Risk**: Mounting the existing FastAPI app inside Reflex via `api_transformer` could silently collide with Reflex's reserved routes (`/ping`, `/_event`, `/_upload`) if either app adds a route under those names later.
   **Mitigation**: Document the reserved list in this PRD (Section 9) and add a startup-time or test-time assertion that no harness route collides with them.

3. **Risk**: Extracting `run_query(...)` from the route handler could introduce a behavior regression if request-scoped concerns (e.g. FastAPI `Depends`-injected DB sessions) don't translate cleanly to a plain function called from Reflex's event handler.
   **Mitigation**: Phase 1 is a pure-refactor step validated against the existing PRD-001 test suite *before* Reflex is introduced at all, isolating this risk from the UI work.

4. **Risk**: A bug or crash in the Reflex chat layer runs in the same process as the core API, so a UI-side fault could affect API availability — a tighter coupling than a separate frontend service would have.
   **Mitigation**: Accepted trade-off in exchange for the "one deployable unit" requirement; mitigate with the Phase 4/5 validation steps and by keeping `ChatState.send()` a thin wrapper with no logic beyond calling `run_query(...)`.

5. **Risk**: No token streaming in the MVP may feel less "Claude-like" than users expect from the visual styling.
   **Mitigation**: Documented explicitly as a known MVP limitation (Section 4, Out of Scope) and listed as the top post-MVP candidate (Section 13).

## 15. Appendix

**Related docs**
- [PRD-001 — Harness IA MVP](../PRD-001-harness-ia/PRD.md) — this PRD extends it; Phase 1 here refactors PRD-001's `POST /query` route without changing its contract.

**Skills referenced**: None — `.agents/skills/` does not exist at the time this PRD was generated.

**Dependencies**
- Everything PRD-001 depends on (OpenRouter API key, Python 3.11+, Docker/docker-compose)
- `reflex` Python package (new)
- Node.js or Bun, build-time only, invoked by Reflex's own tooling (new, not a runtime dependency of the final image)
