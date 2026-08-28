---
id: PRD-004
slug: chat-ui-redesign
title: Chat UI Redesign — Full Pipeline Visibility & Error Handling
status: complete
base_branch: main
epic_branch: epic/PRD-004-chat-ui-redesign
created: 2026-08-21
updated: 2026-08-28
---

## 1. Executive Summary

The chat UI shipped by PRD-002 was built against a three-outcome backend: success, duplicate-blocked, suspicious-blocked. Since then PRD-003 added PII redaction, and the pipeline's response contract grew accordingly — `QuerySuccessResponse` now carries six fields and `run_query(...)` can raise a third exception type. The UI never caught up. Today `ChatState.send()` reads exactly one field of six (`result.response`), discards `pii_redacted`, `pii_entities_masked`, `audit_id`, `model_used`, `tokens_used`, and the suspicious block's `pattern`, and renders all three non-success outcomes as the same amber bubble.

Worse, it is missing an exception arm. `chat_ui/chat_ui/state.py:67` catches `DuplicateCheckError` and `OpenRouterError` only, while `app/services/query_pipeline.py` raises `PiiRedactorError` at two points (lines 58 and 83). The REST router handles it (`app/routers/query.py:28` → HTTP 500); the chat does not. In a Reflex background event an uncaught exception produces no bubble at all — the user's message simply hangs with no response and no error. Separately, `run_query(...)` is blocking sync code called directly inside an `async` event handler, so every request freezes the whole Reflex server for the duration of the OpenRouter call (30 s timeout) plus spaCy inference.

This PRD is a **full redesign of the chat surface** — and only the chat surface. It replaces the untyped `list[dict[str, str]]` message model with a typed model carrying per-outcome metadata, renders each of the six real pipeline outcomes distinctly, surfaces PII redaction as an informational badge (never a block), adds the pending/loading state the async fix makes possible, and gives blocked and failed messages a way out (edit-and-resend, retry). Nothing under `app/` changes: the REST contract, the audit schema, and the pipeline are untouched.

## 2. Mission

Make the chat UI show everything the harness actually did to a message — and never lose a message to a silent failure.

Core principles:
- **Every outcome is visible**: each distinct thing the pipeline can return or raise gets its own visual treatment. No two semantically different outcomes share a bubble style.
- **No silent drops**: every exception path terminates in a rendered bubble. This extends PRD-002's "fail loud, not silent" principle from *blocks* to *errors*.
- **Inform, don't obstruct**: PII redaction is surfaced as a quiet badge, never as a gate. This preserves PRD-003's "mask, never block" principle rather than contradicting it in the UI layer.
- **Presentation only**: the redesign consumes what the pipeline already returns. If a piece of information is not in the response contract today, it is out of scope rather than a reason to change `app/`.
- **Every dead end has an exit**: a blocked or failed message offers the next action (edit-and-resend, retry), instead of terminating the conversation.

## 3. Target Users

**End User (Employee)** — Unchanged persona from PRD-002, but with a sharper pain point: today they cannot tell the difference between "the harness blocked you for a benign reason", "the harness flagged you as a security event", and "the upstream provider is down" — all three render identically. They also have no idea PII redaction exists, since PRD-003 shipped entirely invisibly to them. Technical level: non-technical to technical.

**Security/Compliance Admin** — Unchanged from PRD-002/PRD-003: keeps using `/audit` and `/stats` via bearer token. This PRD does **not** add an admin UI. Their interest here is that the chat displays `audit_id` on successful exchanges, so a user reporting an issue can quote a row ID instead of a paraphrase.

**Integrating Developer** — Cares that the redesign stays inside `chat_ui/` and does not alter `run_query(...)`, the response schemas, or the audit contract, so PRD-001/002/003's test suites keep passing unmodified.

## 4. MVP Scope

### In Scope

**Message model & rendering**
- [ ] Replace `messages: list[dict[str, str]]` with a typed message model carrying a `kind` discriminator plus per-kind metadata fields
- [ ] Six distinct rendered kinds: `user`, `assistant`, `duplicate`, `injection`, `upstream_error`, `internal_error`
- [ ] `duplicate` and `injection` render as visually distinct cards — benign-nudge styling vs. security-event styling — instead of today's shared amber bubble
- [ ] `injection` bubble displays the matched `pattern` value from `QueryBlockedSuspiciousResponse`
- [ ] `duplicate` bubble renders `first_query_at` as a humanized relative time plus the absolute timestamp, and states when the 24-hour window releases

**Error handling**
- [ ] `ChatState.send()` catches `PiiRedactorError` (currently uncaught — the silent-drop bug)
- [ ] Catch-all `except Exception` arm so no pipeline failure can ever produce a message with no bubble
- [ ] `OpenRouterError` renders as an upstream-incident card, distinct from internal errors
- [ ] Every error bubble carries a retry action that re-submits the original prompt text

**Async & pending state**
- [ ] `run_query(...)` invoked via `asyncio.to_thread(...)` so the blocking call no longer freezes the Reflex event loop
- [ ] Pending state: typing/loading indicator, disabled input and send button while a request is in flight, preventing concurrent in-flight sends from the same session
- [ ] Auto-scroll to the newest message on append

**PII surfacing (informational only)**
- [ ] Assistant bubbles show a PII badge when `pii_redacted` is `true`, listing the entity types from `pii_entities_masked`
- [ ] Badge copy is accurate about its own limits: it reports the union across the exchange, because `run_query(...)` does not separate input from output entities
- [ ] Badge is quiet and inline — never a modal, never a confirmation step, never a block

**Metadata & session**
- [ ] Successful exchanges display `model_used`, `tokens_used`, and `audit_id` in a subdued footer on the assistant bubble
- [ ] Model selector driven by a curated allowlist, passed as `QueryRequest.model` (replaces the hardcoded `"gpt-4"` at `state.py:64`)
- [ ] `device` populated from the browser User-Agent instead of the current `None`, so chat rows stop being deviceless in `audit_logs`
- [ ] `user_id` entry gains inline validation with a visible error on empty submit (currently a silent `return`)
- [ ] Active `user_id` shown in a header, with an action to change it without reloading the page
- [ ] Edit-and-resend action on `duplicate` bubbles: repopulates the input with the original prompt and focuses it

**Layout**
- [ ] Redesigned shell: header (harness identity, session `user_id`, model selector), message area, composer
- [ ] Empty state replacing the hardcoded `WELCOME_MESSAGE` dict
- [ ] All user-facing copy centralized in one module, so changing display language is a single-file edit
- [ ] Existing test suites (PRD-001/002/003) continue to pass; `tests/test_chat_state.py` updated to assert structured fields instead of formatted strings

### Out of Scope
- [ ] **Blocking or confirming on PII detection** — explicitly rejected: the badge informs, it never gates. Preserves PRD-003's mask-never-block contract, and a hard block would be unusable at the deliberately low `PII_SCORE_THRESHOLD` of 0.35
- [ ] **Showing the redacted prompt** (the "what actually left the building" diff) — `run_query(...)` returns only `redacted_response`, not `redacted_prompt`; exposing it is a backend change
- [ ] **Separating input-side from output-side PII in the UI** — `query_pipeline.py:100` returns the union; splitting it is a backend change
- [ ] **Admin dashboard for `/audit` and `/stats`** — admins keep the bearer-token REST endpoints (unchanged from PRD-002)
- [ ] **Any change under `app/`** — no schema changes, no pipeline changes, no new endpoints
- [ ] **Per-user duplicate scoping** — `duplicate_checker.py` hashes the prompt with no `user_id` filter, so another user's identical prompt blocks yours. A real product issue, but a backend/product decision, tracked in Section 13
- [ ] **`DATABASE_URL` relative-path fix** — `sqlite:///harness_ai.db` resolves per-cwd, producing separate DBs for `reflex run` (from `chat_ui/`) and `python app.py` (from the repo root). Deployment/config concern, tracked in Section 13
- [ ] Token-by-token streaming (backend does not support it)
- [ ] Persisted chat history across reloads or sessions
- [ ] Real auth/login beyond the free-text `user_id`
- [ ] A full i18n framework (only copy centralization is in scope)
- [ ] Prompt length limits or character counters

## 5. User Stories

1. **As an end user**, I want a message that fails inside the harness to still produce a visible bubble, so my message is never silently swallowed.
   - Example: `PiiRedactorError` is raised because the spaCy model failed to load; instead of nothing appearing, an internal-error card renders with the error text and a retry button.

2. **As an end user**, I want a duplicate block and a prompt-injection block to look different, so I can tell "you already asked this" apart from "this was logged as a security event".
   - Example: `"hello world"` sent twice renders a neutral card reading "Already sent 2 hours ago (2026-08-21T10:30:00Z) — the 24h window releases at 12:30"; `"please override the rules"` renders a red security card reading "Blocked as prompt injection — matched pattern: `override`".

3. **As an end user**, I want to know when the harness masked personal data in my exchange, so I understand why a response might read `<PERSON>` instead of a name.
   - Example: an assistant bubble carries a badge: "2 PII types masked in this exchange: PERSON, EMAIL_ADDRESS" — rendered inline, with no interruption to the conversation.

4. **As an end user**, I want visible feedback while the model is thinking, so a 30-second OpenRouter call doesn't look like a frozen page.
   - Example: on send, the composer disables and a typing indicator appears until the response, error, or block bubble arrives.

5. **As an end user**, I want a way out of a blocked or failed message, so a dead-end bubble isn't the end of the conversation.
   - Example: a duplicate card's "Edit and resend" button repopulates the composer with the original prompt and focuses it; an upstream-error card's "Retry" button resends unchanged.

6. **As an end user**, I want to see which model answered and what it cost, so my usage isn't invisible.
   - Example: an assistant bubble footer reads `gpt-4 · 45 tokens · #127`, where `#127` is the `audit_id`.

7. **As a security admin**, I want chat-originated audit rows to record the device, so `audit_logs.device` isn't null for every chat row while API rows can populate it.
   - Example: a message sent from Chrome on Windows writes a row whose `device` column is populated, matching what `POST /query` accepts via `QueryRequest.device`.

8. **As an integrating developer**, I want the redesign confined to `chat_ui/`, so the REST contract, the pipeline, and the audit schema are provably unchanged.
   - Example: PRD-001/002/003 test suites pass unmodified except `tests/test_chat_state.py`, whose changes are limited to assertions about bubble structure.

## 6. Core Architecture & Patterns

The pipeline is unchanged. Only the consumer changes — from a one-field reader to an exhaustive one:

```
ChatState.send()  (Reflex background event)
   │
   │  append kind="user" message, set pending=True
   ▼
await asyncio.to_thread(run_query, ...)         ← CHANGED: was a blocking sync call
   │                                               in the async event handler
   ├── QuerySuccessResponse ───────────────────► kind="assistant"
   │      response, model_used, tokens_used,        + PII badge  (pii_redacted)
   │      audit_id, pii_redacted,                   + footer     (model/tokens/audit_id)
   │      pii_entities_masked
   │
   ├── QueryBlockedDuplicateResponse ──────────► kind="duplicate"
   │      reason, first_query_at                    + relative time, window release
   │                                                + "Edit and resend"
   │
   ├── QueryBlockedSuspiciousResponse ─────────► kind="injection"
   │      reason, pattern                           + matched pattern shown
   │
   ├── raises OpenRouterError ─────────────────► kind="upstream_error"  + "Retry"
   │
   ├── raises PiiRedactorError ────────────────► kind="internal_error"  + "Retry"
   │      (NEW arm — currently uncaught)
   │
   ├── raises DuplicateCheckError ─────────────► kind="internal_error"  + "Retry"
   │
   └── raises Exception ───────────────────────► kind="internal_error"  + "Retry"
          (NEW catch-all — no path may end with no bubble)
   │
   ▼
append bubble, set pending=False, scroll to newest
```

Message model (replacing `list[dict[str, str]]`):

```python
class ChatMessage(rx.Base):
    kind: str                      # user | assistant | duplicate | injection
                                   # | upstream_error | internal_error
    content: str                   # prompt text, response text, or reason
    prompt: str = ""               # original prompt, for retry / edit-and-resend
    model_used: str = ""
    tokens_used: int = 0
    audit_id: int = 0
    pii_redacted: bool = False
    pii_entities: list[str] = []
    pattern: str = ""              # injection only
    first_query_at: str = ""       # duplicate only
    detail: str = ""               # error text for the two error kinds
```

Files touched (all inside `chat_ui/`):
```
chat_ui/
├── chat_ui/
│   ├── chat_ui.py                 # CHANGED: page shell composition
│   ├── state.py                   # CHANGED: typed messages, asyncio.to_thread,
│   │                              #          exhaustive except arms, pending flag,
│   │                              #          model/device/user_id handling, retry
│   ├── models.py                  # NEW: ChatMessage
│   ├── copy.py                    # NEW: all user-facing strings, one place
│   ├── config.py                  # NEW: curated model allowlist
│   └── components/
│       ├── chat.py                # CHANGED: bubble dispatch by kind, composer
│       ├── bubbles.py             # NEW: the six bubble renderers + PII badge
│       └── shell.py               # NEW: header (user_id, model selector), empty state
└── tests/test_chat_state.py       # CHANGED (repo root): structural assertions
```

Design patterns:
- **Discriminated union rendering**: one `rx.match` on `kind` dispatching to six renderers, replacing today's nested `rx.cond` on three roles (`components/chat.py:8-51`). Adding a seventh outcome later becomes one new arm, not another nesting level.
- **Exhaustive result handling**: `send()` handles every branch `run_query(...)` can produce — three return types, three named exceptions, one catch-all. The catch-all is the invariant that makes "no silent drops" structurally true rather than aspirational.
- **Thread-offloaded blocking work**: the pipeline stays synchronous; the UI adapts via `asyncio.to_thread(...)`. State mutation remains inside `async with self` blocks, per Reflex's background-event contract.
- **Presentation-only boundary**: `chat_ui/` imports from `app/` and never modifies it, preserving PRD-002's "no parallel pipeline" guarantee.

Per `chat_ui/AGENTS.md`, Reflex API usage must be verified against the **reflex-docs** skill rather than recalled from memory, and any run/compile/restart cycle must follow the **reflex-process-management** skill.

## 7. Tools/Features

| Feature | Maps to | Detail |
|---|---|---|
| Typed message model | New | `ChatMessage` with a `kind` discriminator; unblocks every metadata-bearing feature below. |
| Six-outcome rendering | Redesign of PRD-002 3-role rendering | Distinct treatment per pipeline outcome; injection shows `pattern`, duplicate shows relative time. |
| `PiiRedactorError` arm | Bug fix (PRD-003 fallout) | The uncaught exception at `state.py:67` that currently drops messages silently. |
| Catch-all error arm | New | Structural guarantee that no path ends without a bubble. |
| `asyncio.to_thread` offload | Bug fix | Unfreezes the Reflex event loop; prerequisite for any loading indicator to animate. |
| Pending / loading state | New | Typing indicator, disabled composer, no concurrent in-flight sends. |
| PII badge | Consumes PRD-003 STORY-007 | Renders `pii_redacted` + `pii_entities_masked`; closes README's known limitation #4. |
| Success metadata footer | Consumes PRD-001 response fields | `model_used`, `tokens_used`, `audit_id` — all already returned, all currently discarded. |
| Model selector | Consumes `QueryRequest.model` | Curated allowlist; reverses PRD-002's out-of-scope item now that the rest of the UI can show which model answered. |
| Device capture | Consumes `QueryRequest.device` | Browser User-Agent into the existing `audit_logs.device` column. |
| Edit-and-resend / Retry | New | Recovery affordance on blocked and failed bubbles. |
| Session header | New | Visible `user_id`, change-user action, validation on empty submit. |
| Auto-scroll | New | Newest message scrolled into view on append. |

## 8. Technology Stack

**Frontend / Chat UI (unchanged stack, extended usage)**
- Reflex — version as pinned in `chat_ui/requirements.txt`; plugins already configured in `rxconfig.py`: `TailwindV4Plugin`, `RadixThemesPlugin`, `SitemapPlugin`
- `rx.Base` for the typed message model, `rx.match` for kind dispatch, `rx.scroll_area` / scroll-into-view for auto-scroll — all APIs to be confirmed against the **reflex-docs** skill before implementation, per `chat_ui/AGENTS.md`

**Backend (consumed, not modified)**
- `app/services/query_pipeline.py::run_query(...)` — unchanged
- `app/models/schemas.py` — unchanged; the redesign consumes fields that already exist
- `app/services/pii_redactor.py` — unchanged; only its `PiiRedactorError` is newly caught

**Standard library**
- `asyncio.to_thread` (Python 3.9+, already the project's floor per README)

**Testing**
- `pytest` + `pytest-asyncio` (already in use by `tests/test_chat_state.py`)
- No new dependencies in either `requirements.txt`

## 9. Security & Configuration

**No new environment variables.** The model allowlist is a UI-level constant; `OPENROUTER_API_KEY`, `ADMIN_TOKEN`, `DATABASE_URL`, `PORT`, `HOST`, and all four `PII_*` settings are consumed unchanged from `app/config.py`.

**PII display guarantee** — the badge renders entity *types* only (`PERSON`, `EMAIL_ADDRESS`, …), never detected values and never the raw text Presidio matched. The user's own prompt remains visible in their own bubble, which is their own input and not a disclosure. No new surface exposes the audit log's raw previews.

**Admin token** — unchanged from PRD-002: the chat UI has no admin capability, never holds the admin token, and this PRD adds no path to `/audit` or `/stats`.

**Error detail exposure** — error bubbles show exception messages (e.g. `"OpenRouter request failed: ..."`). These are the same strings `POST /query` already returns in its HTTP 500/502 `detail` field (`app/routers/query.py:26-31`), so this introduces no disclosure the REST API does not already make.

**Model allowlist** — the selector offers a curated list rather than a free-text field. An arbitrary model string would reach OpenRouter and return an error the user cannot act on; an allowlist keeps `QueryRequest.model` values known-good without adding server-side validation.

**Privacy (inherited, unchanged)** — no IP address or geolocation captured. The newly-populated `device` field is the browser User-Agent, which the `audit_logs.device` column and `QueryRequest.device` already accommodate by design; it is not new data collection, it is a column stopping being null.

**Reflex reserved routes** — `/ping`, `/_event`, `/_upload` remain reserved (PRD-002 Section 9). This PRD adds no routes, so `tests/test_route_reservations.py` continues to hold.

## 10. API Specification

**No new or modified endpoints.** `POST /query`, `GET /audit`, `GET /stats`, and `GET /health` retain their exact contracts from PRD-001 and PRD-003.

The chat UI communicates over Reflex's internal WebSocket event protocol and calls `run_query(...)` in-process, as established by PRD-002 Section 10. What changes is only how much of the existing contract the UI consumes:

| Contract element | PRD-002 UI | After this PRD |
|---|---|---|
| `QuerySuccessResponse.response` | consumed | consumed |
| `QuerySuccessResponse.model_used` | discarded | rendered in footer |
| `QuerySuccessResponse.tokens_used` | discarded | rendered in footer |
| `QuerySuccessResponse.audit_id` | discarded | rendered in footer |
| `QuerySuccessResponse.pii_redacted` | discarded | drives the PII badge |
| `QuerySuccessResponse.pii_entities_masked` | discarded | listed in the PII badge |
| `QueryBlockedDuplicateResponse.first_query_at` | inlined raw into a string | relative + absolute time, window release |
| `QueryBlockedSuspiciousResponse.pattern` | discarded | shown on the security card |
| `QueryRequest.model` | hardcoded `"gpt-4"` | model selector |
| `QueryRequest.device` | always `None` | browser User-Agent |
| `PiiRedactorError` | uncaught → silent drop | internal-error card |
| `DuplicateCheckError` | generic system bubble | internal-error card |
| `OpenRouterError` | generic system bubble | upstream-error card |
| any other exception | uncaught → silent drop | internal-error card |

## 11. Success Criteria

**MVP definition of done**
- [ ] A `PiiRedactorError` raised anywhere in `run_query(...)` renders a visible error bubble instead of nothing
- [ ] An arbitrary unexpected exception raised inside `run_query(...)` also renders a visible error bubble
- [ ] Duplicate, injection, upstream-error, and internal-error each render with a visually distinct treatment
- [ ] A suspicious-pattern block displays the matched `pattern` string
- [ ] A duplicate block displays a humanized relative time derived from `first_query_at` and offers edit-and-resend
- [ ] A successful exchange with PII displays a badge naming the masked entity types
- [ ] A successful exchange displays `model_used`, `tokens_used`, and `audit_id`
- [ ] The composer is disabled and a loading indicator is visible for the full duration of an in-flight request
- [ ] The Reflex event loop stays responsive during a slow `run_query(...)` — a second browser session can navigate and interact while one request is in flight
- [ ] Selecting a model in the UI produces an audit row whose `model_used` matches the selection
- [ ] A chat-originated audit row has a non-null `device` value
- [ ] Submitting an empty `user_id` shows a visible validation error instead of doing nothing
- [ ] PRD-001/002/003 test suites pass; `tests/test_chat_state.py` changes are limited to bubble-structure assertions
- [x] ~~No file under `app/` is modified by this epic~~ — **not met.** Commit
  `60835dc` added `AUDIT_LOGS_ADDED_COLUMNS` to `app/db/models.py` and
  `_add_missing_columns()` to `app/db/database.py`, an additive `ALTER TABLE`
  migration bringing databases created before PRD-003 up to the current schema.
  The change is correct and needed — `CREATE TABLE IF NOT EXISTS` is a no-op
  against an existing file, so the PII columns were never added to older DBs —
  but it belongs to a backend PRD, not to this one. Kept rather than reverted,
  because reverting it re-breaks every pre-PRD-003 database. Recorded here so
  the "0 files under `app/`" quality indicator is not claimed falsely.

**Quality indicators**

| Metric | Target |
|---|---|
| Pipeline outcomes with a dedicated rendering | 6 / 6 |
| `run_query(...)` exception types with a handler | 3 named + 1 catch-all |
| Response contract fields consumed by the UI | 6 / 6 (was 1 / 6) |
| Files modified under `app/` | 2 (deviation, see Section 11) |
| Existing test suites passing | 100%, unmodified except `test_chat_state.py` |
| Event-loop blocking during a request | 0 ms (offloaded to a worker thread) |

## 12. Implementation Phases

**Phase 1 — Correctness foundation** (~1 day)
- Goal: fix the two defects that make everything else meaningful, with no visual change yet.
- Deliverables: `asyncio.to_thread(...)` offload; `PiiRedactorError` arm; catch-all `except Exception` arm; `pending` state var on `ChatState`.
- Validation: a test forcing `PiiRedactorError` asserts a bubble is appended; a test forcing an arbitrary exception does the same; existing `test_chat_state.py` still passes.

**Phase 2 — Typed message model** (~1 day)
- Goal: replace `list[dict[str, str]]` with `ChatMessage`; pure data-model refactor.
- Deliverables: `chat_ui/models.py`; `send()` populating every metadata field from each result type; `test_chat_state.py` migrated to structural assertions.
- Validation: every field of `QuerySuccessResponse`, `QueryBlockedDuplicateResponse`, and `QueryBlockedSuspiciousResponse` is asserted to land on the appended message.

**Phase 3 — Bubble redesign & PII badge** (~2 days)
- Goal: the six distinct renderings, plus everything the metadata now makes possible.
- Deliverables: `components/bubbles.py` with `rx.match` dispatch; PII badge; success footer; duplicate relative-time formatting; injection pattern display; loading indicator; auto-scroll; `chat_ui/copy.py`.
- Validation: manual walkthrough of all six outcomes (a duplicate seeded in the DB, a prompt containing `override`, a prompt with an email, an unset `OPENROUTER_API_KEY` for the upstream error, `PII_NLP_MODEL` set to a bogus value for the internal error).

**Phase 4 — Shell, session, and recovery actions** (~1–2 days)
- Goal: everything around the message list.
- Deliverables: header with `user_id` and change-user action; `user_id` validation; model selector over the allowlist in `chat_ui/config.py`; User-Agent capture into `device`; edit-and-resend on duplicates; retry on both error kinds; empty state.
- Validation: User Stories 5–8 demonstrated manually; audit rows inspected for non-null `device` and a `model_used` matching the selector.

## 13. Future Considerations

Deferred, with the reason each is deferred:

- **Show the redacted prompt** — the highest-value follow-up. Returning `redacted_prompt` on `QuerySuccessResponse` is an additive schema field plus one line in `query_pipeline.py`, and it would let the UI show a real diff of what left the building versus what the user typed. Out of scope here only because this PRD does not touch `app/`.
- **Split input-side from output-side PII** — `query_pipeline.py:100` unions the two entity lists; `audit_logs` already stores them separately as `pii_detected_input` / `pii_detected_output`. Surfacing the split needs the response contract to stop flattening it.
- **Per-user duplicate scoping** — `check_duplicate(prompt)` hashes the prompt alone, so any user's identical prompt blocks any other's. In a chat this fires constantly on short messages ("hola", "gracias"). Related to the roadmap's semantic-duplicate item; a product decision, not a UI one.
- **`DATABASE_URL` as an absolute path** — the relative `sqlite:///harness_ai.db` resolves against the process cwd, so `reflex run` from `chat_ui/` and `python app.py` from the repo root write to different databases, splitting both the audit trail and the duplicate window. A config/deployment fix.
- **Admin dashboard** — a Reflex page over `/audit` and `/stats`, including the PRD-003 telemetry (`pii_detected_queries`, `top_pii_entities`). Explicitly deferred at scoping time; carried over from PRD-002 Section 13.
- **Token-by-token streaming** — still blocked on the backend, unchanged from PRD-002.
- **Persisted chat history** and **real auth** — unchanged from PRD-002 Section 13.
- **Full i18n** — this PRD centralizes copy in one module, which is the prerequisite; a locale framework is the follow-up.

## 14. Risks & Mitigations

1. **Risk**: `tests/test_chat_state.py` asserts exact dict equality on bubble contents (lines 181-210, e.g. `{"role": "system", "content": f"Blocked — Duplicate query within 24 hours (first sent at {timestamp})"}`). The typed message model breaks all of them at once, and a careless migration could weaken the tests into asserting nothing meaningful.
   **Mitigation**: Phase 2 migrates them to assert on *structured fields* (`kind == "duplicate"`, `first_query_at == timestamp`) rather than on rendered strings — stricter than the current string comparison, not looser. The audit-parity tests (lines 240-306) assert on database rows, not bubbles, and must pass unmodified as the proof that pipeline behavior is unchanged.

2. **Risk**: The `PII_SCORE_THRESHOLD` default of 0.35 is deliberately permissive and over-masks ordinary text (PRD-003 Section 2, "recall over precision"). A PII badge will therefore fire on a large share of messages, and users will learn to ignore it — badge fatigue that defeats the point of surfacing it.
   **Mitigation**: The badge is designed as a quiet inline element, not an alert: no color-coded alarm, no modal, no interruption. It is a factual annotation on the exchange. This is also the concrete reason the "block or confirm on PII" option was rejected at scoping — at this threshold it would make the chat unusable.

3. **Risk**: Moving `run_query(...)` onto a worker thread while the `pending` flag lives in Reflex state introduces a race: state mutated outside an `async with self` block, or a `pending` flag left stuck `True` if an exception escapes before it is cleared, permanently disabling the composer.
   **Mitigation**: All state mutation stays inside `async with self` blocks; `pending = False` is set in a `finally` block so no exception path can leave the composer locked. A test asserts `pending is False` after each of the six outcomes, including the catch-all arm.

4. **Risk**: Edit-and-resend on a duplicate bubble invites the user to resend the identical prompt, which is blocked again — a loop that makes the affordance feel broken.
   **Mitigation**: The action repopulates and focuses the composer with the original text and pairs it with copy stating the text must change to go through. The underlying cause (prompt-only, cross-user hashing) is called out in Section 13 as a backend follow-up rather than papered over in the UI.

5. **Risk**: The PII badge reports the union of input and output entities, but users will naturally read it as "this is what *I* leaked". Mislabeling it would be a correctness problem in a compliance-facing product.
   **Mitigation**: Copy is explicit that it covers the whole exchange ("masked in this exchange"), not the prompt alone. The precise split is listed as a Section 13 follow-up so the limitation is tracked rather than quietly tolerated.

6. **Risk**: A crash in the redesigned chat layer takes down the API with it — the two share a process, per PRD-002's `api_transformer` architecture. This redesign adds materially more UI logic than PRD-002 shipped, increasing that exposure.
   **Mitigation**: Inherited trade-off, re-declared here. The catch-all exception arm (Phase 1) is the primary containment: no pipeline failure escapes `send()`. Rendering logic stays free of I/O and free of pipeline logic.

7. **Risk**: The model selector lets a user pick a model the configured OpenRouter key cannot access, producing an `OpenRouterError` the user reads as "the harness is broken".
   **Mitigation**: A curated allowlist in `chat_ui/config.py` rather than free text, and the upstream-error card names OpenRouter explicitly as the failing party and offers retry.

## 15. Appendix

**Related docs**
- [PRD-001 — Harness IA MVP](../PRD-001-harness-ia/PRD.md) — source of the response contract this PRD finally consumes in full.
- [PRD-002 — Embedded Chat UI (Reflex)](../PRD-002-reflex-chat-ui/PRD.md) — the UI this PRD redesigns. Its Section 4 out-of-scope items for model picker and blocked-state rendering are revisited here; its single-process/single-port architecture is unchanged.
- [PRD-003 — PII Redaction](../PRD-003-pii-redaction/PRD.md) — shipped `pii_redacted` / `pii_entities_masked` and `PiiRedactorError`; this PRD is the UI half that was never built. README "Known limitations (MVP)" item 4 is closed here.
- `chat_ui/AGENTS.md` — mandates the Reflex agent skills for any Reflex work in this repo.

**Skills referenced**: None — `.agents/skills/` does not exist at the time this PRD was generated (verified in Phase 1b). The project's Reflex conventions come from `chat_ui/AGENTS.md`, which requires the externally-installed `reflex-docs`, `setup-python-env`, and `reflex-process-management` plugin skills; their constraints are cited in Sections 6 and 8.

**Dependencies**
- No new packages in either `requirements.txt`.
- `asyncio.to_thread` requires Python 3.9+, already the project's declared floor.
- Depends on PRD-003 being merged (it is — `main` as of commit `56a3781`), since the PII badge consumes fields it introduced.

**Source references for the defects this PRD fixes**
- `chat_ui/chat_ui/state.py:67` — `except (DuplicateCheckError, OpenRouterError)`; missing `PiiRedactorError`
- `chat_ui/chat_ui/state.py:59` — blocking `run_query(...)` inside an `async` background event
- `chat_ui/chat_ui/state.py:64` — hardcoded `model="gpt-4"`
- `chat_ui/chat_ui/state.py:63` — `device=None`
- `chat_ui/chat_ui/state.py:73,80` — discarded success metadata and `pattern`
- `chat_ui/chat_ui/state.py:41-43` — `submit_user_id` silent return on empty input
- `chat_ui/chat_ui/components/chat.py:8-51` — nested `rx.cond` over three roles
- `chat_ui/chat_ui/components/chat.py:56` — `overflow_y="auto"` with no scroll-into-view
- `app/services/query_pipeline.py:58,83` — the two `PiiRedactorError` raise sites
- `app/routers/query.py:28` — the REST handler for `PiiRedactorError` that the chat lacks
