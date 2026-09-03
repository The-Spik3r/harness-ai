---
id: PRD-008
slug: chat-sessions
title: Chat Sessions — Persisted, Per-Conversation Transcripts
status: draft
base_branch: main
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-02
updated: 2026-09-02
---

## 1. Executive Summary

The chat has no memory of itself. `ChatState.messages` is a list on a Reflex state object, and that is the only place a transcript has ever existed: a page reload empties it, `logout()` empties it deliberately, and a container restart empties it for everyone at once. PRD-007 moved the record to Turso so that two instances could share one database — and proved it in `tests/test_two_instance_smoke.py` — but the transcript was never part of what moved. A user whose browser reconnects to the second instance mid-conversation finds an empty screen, because the conversation was never anywhere but the first instance's process memory.

The record did not lose anything, because the record was never the transcript. `audit_logs` stores `prompt_hash`, a truncated `prompt_preview` and a truncated `response_preview` — enough to prove what happened, deliberately not enough to reconstruct what was said. That is the right shape for evidence and the wrong shape for a conversation, and no amount of reading from `audit_logs` will produce a transcript that PRD-004's bubbles could render back.

This PRD builds **chat sessions**: a user's conversations become first-class, persisted, addressable objects. Two new tables (`chat_sessions`, `chat_messages`) alongside `audit_logs` and `users` in the same Turso database, a session rail on the chat surface for moving between conversations, and a `session_id` on the audit row so the record and the transcript can be joined. Every message is stored with the verdict PRD-004 already computed for it, so a restored conversation reads exactly as it read live — held rows still held, denied rows still denied.

**What this PRD deliberately does not build is multi-turn context.** Every send stays exactly what it is today: one user turn, alone, to OpenRouter. Sessions are how a person organizes and returns to their work; they are not, in this PRD, what the model sees. Section 13 records why that separation is load-bearing rather than timid — multi-turn breaks the duplicate checker in a way that needs its own design, and the README's OpenAI-compatible endpoint section already names the same open question.

## 2. Mission

Give a conversation somewhere to live, without turning the evidence log into a chat history.

Core principles:
- **The record and the conversation are different artifacts.** `audit_logs` stays what it is: hashes, previews, verdicts, immutable. `chat_sessions` is the user's working copy — theirs to name and theirs to delete. Deleting a chat never deletes an audit row.
- **Persist what the surface already showed.** The transcript stores the prompt the owner typed and the response the pipeline *released* — the redacted one. Nothing the checks held back gets written down on the way to being displayed.
- **One turn in, one turn out.** The pipeline signature does not change. A session groups sends; it does not concatenate them.
- **Sessions are owned.** Every read and every write asserts the row belongs to the caller's `user_id`. This is the first row-level authorization in the system and it is written as a rule, not as a filter someone remembered to add.
- **Additive, in the pattern already set.** New tables via `CREATE TABLE IF NOT EXISTS` in `init_db()`, the new audit column via `AUDIT_LOGS_ADDED_COLUMNS`. PRD-005 added `users` exactly this way; there is no migration tool to introduce and none is introduced.

## 3. Target Users

**End User (Employee)** — the primary persona and the only one whose surface changes. Today they lose their work by reloading the page, and they cannot run two lines of enquiry without the second scrolling the first out of reach. They need conversations that persist, that are separable, and that come back the way they left them. Technical level: unchanged from PRD-002 — they hold a token and type prompts.

**Security/Compliance Admin** — their console is untouched, but their *posture* is not. This PRD is the first time full prompt and response text is written to durable storage under a user's name. They need that to be a deployment decision they can see and switch off, and they need the audit trail to gain something from it rather than merely absorb the risk — which is what the `session_id` join gives them.

**Integrating Developer** — cares that `POST /query` stays compatible. `session_id` arrives as an optional field on `QueryRequest`, the way `device` already is; a client that omits it behaves exactly as it does today, and `tests/test_query_router.py`, `tests/test_integration.py` and `tests/test_route_reservations.py` pass unmodified.

## 4. MVP Scope

### In Scope

**Schema (`app/db/`)**
- [ ] `chat_sessions` table: `session_id` (TEXT PK, UUID4), `user_id`, `title`, `created_at`, `updated_at`
- [ ] `chat_messages` table: `id` (INTEGER PK AUTOINCREMENT), `session_id`, `kind`, `content`, `prompt`, `created_at`, plus the verdict metadata PRD-004's `ChatMessage` already carries
- [ ] Index on `chat_sessions(user_id, updated_at DESC)` and on `chat_messages(session_id, id)`
- [ ] `session_id TEXT` added to `audit_logs` through `AUDIT_LOGS_ADDED_COLUMNS` — nullable, so every existing row and every API client that omits it stays valid
- [ ] Both tables created in `init_db()` with `CREATE TABLE IF NOT EXISTS`, in the same `_session()` block as `users`

**Data access (`app/db/database.py`)**
- [ ] `create_chat_session`, `get_chat_session`, `list_chat_sessions(user_id, limit)`, `rename_chat_session`, `touch_chat_session`, `delete_chat_session`
- [ ] `append_chat_message`, `list_chat_messages(session_id, user_id)`, `count_chat_sessions(user_id)`
- [ ] Every function that names a session takes `user_id` and scopes the `WHERE` clause by it — no function accepts a bare `session_id` and returns a row
- [ ] `delete_chat_session` removes the session and its messages in one `_session()` transaction, and touches no `audit_logs` row

**Pipeline & API (`app/`)**
- [ ] `QueryRequest.session_id: Optional[str]`, validated as a UUID4 string when present
- [ ] `run_query(...)` gains `session_id: Optional[str]` and passes it through to `log_query(...)` on **every** logging path — including the three denial arms and the three failure arms
- [ ] `log_query` and `AuditLog` carry `session_id`
- [ ] `AuditQueryEntry` gains `session_id` so `GET /audit` can report it
- [ ] A `session_id` that does not belong to the authenticated identity is refused with 403, in the same place `user_id` mismatch already is

**Chat state (`chat_ui/`)**
- [ ] `ChatState` gains `sessions: list[ChatSessionSummary]`, `active_session_id: str`, and loads both on sign-in
- [ ] Lazy creation: a session row is written on the first send, never on page load — an opened-and-abandoned tab leaves nothing behind
- [ ] Auto-title from the first prompt (truncated at a word boundary), overridable by rename
- [ ] Switching sessions loads that transcript from the database and replaces `messages`
- [ ] Every persisted message is written after the bubble is appended, so a write failure degrades to "this turn was not saved" rather than losing the turn on screen
- [ ] `logout()` clears session state as it clears `messages` today; the rows survive in the database
- [ ] Delete a chat, with confirmation, from the rail
- [ ] All database calls offloaded with `asyncio.to_thread(...)`, per PRD-004's precedent

**Surface (design direction in Section 6.1)**
- [ ] A session rail listing the caller's conversations, newest activity first, with the active one marked
- [ ] "New chat" action; the empty state doubles as the new-chat state
- [ ] Rail states: no sessions yet, sessions listed, and a read that failed
- [ ] Every new string in `copy.py`; every colour, size and face from `theme.py`
- [ ] Contrast parity asserted in `tests/test_contrast.py` for any new pairing
- [ ] Responsive down to a narrow viewport (the rail collapses), visible keyboard focus, `prefers-reduced-motion` respected

**Configuration**
- [ ] `CHAT_HISTORY_ENABLED` (default `true`). Set `false` and no transcript row is ever written or read, and the chat behaves exactly as it does today — the switch a compliance-strict deployment needs
- [ ] `CHAT_SESSION_LIMIT` — the ceiling on sessions listed per user (default 50)

### Out of Scope

- [ ] **Multi-turn context to the model** — `call_openrouter` keeps its `prompt: str` signature and keeps sending one user message. See Section 13.
- [ ] **Any change to the duplicate checker** — `check_duplicate` stays a global 24h exact-match over the prompt hash. Rescoping it is multi-turn's prerequisite, not this PRD's work.
- [ ] **Storing the redacted prompt** — `run_query` returns the redacted *response* and not the redacted prompt; surfacing it is a pipeline change PRD-004 Section 13 already parked.
- [ ] **Streaming** — unchanged; the harness must see a complete response before releasing it.
- [ ] **Search across sessions, folders, pinning, tagging, sharing, export** — the rail lists and switches. Nothing more.
- [ ] **Editing or branching a past turn** — `edit_and_resend` keeps its current behaviour: it refills the composer, it does not rewrite history.
- [ ] **Sessions in the admin console** — PRD-006's register and summary are untouched. The `session_id` column reaches `GET /audit` and stops there.
- [ ] **Automatic retention or expiry** — no TTL job. Deletion is a user action.
- [ ] **Cross-tab live sync** — two tabs on one session do not push to each other; the second one to load wins its own view.
- [ ] **Encryption at rest beyond what Turso provides** — no application-level envelope encryption.
- [ ] **Sharing a session with another user** — ownership is single and absolute.

## 5. User Stories

1. **As an employee**, I want my conversation to still be there after I reload the page, so that a stray refresh does not cost me an afternoon of work.
   - Example: reloading mid-conversation returns the same twelve bubbles, with the held one still marked held.

2. **As an employee**, I want to keep separate conversations for separate subjects, so that starting a new line of enquiry does not bury the previous one.
   - Example: the rail lists *Quarterly close reconciliation* and *Vendor contract review*; switching between them swaps the transcript and nothing else.

3. **As an employee**, I want my chats named by what they are about, so that a list of eleven conversations is scannable rather than eleven timestamps.
   - Example: a chat opened with "summarise the Q3 vendor spend" appears in the rail as *Summarise the Q3 vendor spend*, renameable.

4. **As an employee**, I want to delete a conversation I no longer want on screen, so that the list stays mine.
   - Example: deleting a chat removes it from the rail and its messages from the database; the audit rows it produced remain, and the admin console is unchanged.

5. **As an employee**, I want a blocked or failed turn to still be part of the conversation when I come back to it, so that the transcript is a true account and not just the answers.
   - Example: a reloaded session still shows *DENIED — matched pattern* where it was, in its ink, and offers the same **Edit and resend**.

6. **As an employee reconnecting to a different instance**, I want my conversations to be there anyway, so that the two-instance deployment PRD-007 shipped is invisible to me.
   - Example: instance A wrote the session, instance B serves the reload, the transcript is identical.

7. **As a security admin**, I want transcript persistence to be a setting I control, so that a deployment that must not hold prompt text can run this build with the feature off.
   - Example: `CHAT_HISTORY_ENABLED=false` boots the same image, the rail is absent, and no `chat_messages` row is written.

8. **As a compliance admin**, I want an audit row to name the conversation it came from, so that a report about "that chat" resolves to a set of rows rather than a guess.
   - Example: `GET /audit` returns `session_id` alongside `audit_id`; three rows share one session and are visibly one conversation.

9. **As an integrating developer**, I want `POST /query` to keep working unchanged when I send no `session_id`, so that adopting this release requires no client change.

## 6. Core Architecture & Patterns

The pipeline keeps its shape. What changes is that a send now has a *place* it belongs to, and that place is recorded on both sides — in the transcript the user reads, and on the audit row the admin reads.

```
                        app/db/database.py  ──►  Turso / libSQL
                                │
       ┌────────────────────────┼────────────────────────┐
       │                        │                        │
   audit_logs                users                 chat_sessions
   (evidence, immutable)   (identity)              chat_messages
   + session_id  ──────── joins ────────────────────────┘
       ▲                                                 ▲
       │ log_query(...)                                  │ append_chat_message(...)
       │                                                 │
  app/services/query_pipeline.py                   chat_ui ChatState
```

Send path, with the two writes distinguished:

```
ChatState._do_send(text)
   │  resolve(_token) ──► Identity        (unchanged, re-derived every send)
   │  ensure_session()  ──► create_chat_session(...) on first send only
   ▼
await asyncio.to_thread(run_query, ..., session_id=active_session_id)
   │
   ├── SUCCESS / HELD / DENIED / FORBIDDEN ──► log_query(session_id=...)   [evidence]
   │                                                    │
   ▼                                                    ▼
append bubble to self.messages                   audit_logs row
   │
   ▼
append_chat_message(session_id, bubble)          [transcript]
   │  raises ──► bubble stays on screen, one notice, session untouched
   ▼
touch_chat_session(session_id)  ──► updated_at, and the rail reorders
```

**Order is deliberate.** The audit write happens inside the pipeline, where it always has; the transcript write happens after, in the UI layer, and is allowed to fail without taking the turn with it. Evidence is the thing that must not be lost, and it is not made to depend on a feature the deployment can switch off.

**What a stored message holds.** `chat_messages` mirrors `ChatMessage` field for field, because a restored bubble must render through the same `rx.match` in `components/chat.py` as a live one — a second, lossier model would produce transcripts that read differently after a reload, which is exactly the bug this PRD exists to remove.

| Bubble kind | `content` stores | Notes |
|---|---|---|
| `user` | the prompt as typed | The owner is the only reader; this is the text they wrote. |
| `assistant` | the **redacted** response | `QuerySuccessResponse.response` — what the pipeline released, never the raw upstream text. |
| `duplicate` | the reason | Plus `first_query_at`; the humanized copy is recomputed on load, not stored, so it stays relative to *now*. |
| `injection` | the reason | Plus `pattern`. |
| `forbidden` | the reason | Plus `required_permission`. |
| `upstream_error` / `internal_error` | the kind marker | Plus `detail`, as PRD-004 already renders it. |

**Ownership as a signature rule, not a filter.** Every session-scoped function in `database.py` takes `user_id` as a required parameter and puts it in the `WHERE` clause:

```python
def list_chat_messages(session_id: str, user_id: str) -> list[StoredMessage]:
    # user_id is not optional and not defaulted -- a caller that forgets it
    # fails at the call site rather than reading someone else's conversation.
```

This is the first row-level authorization in the system: RBAC (PRD-005) answers *may this role do this kind of thing*, and it has no opinion about *whose row this is*. Both checks apply — `query:submit` still gates the send — and neither substitutes for the other.

**Ordering.** `chat_messages` is read `ORDER BY id ASC`, never by timestamp. PRD-006 Section 13 already recorded that `audit_logs` ties arbitrarily when two rows share a second on a TEXT timestamp; a transcript that reorders itself on reload would be a visible instance of the same defect, so the autoincrement key is the order and the timestamp is only displayed.

Files:

```
app/
├── db/
│   ├── models.py            # CHANGED: chat_sessions + chat_messages DDL, ChatSession/StoredMessage
│   └── database.py          # CHANGED: nine session functions, session_id on the audit insert
├── models/schemas.py        # CHANGED: session_id on QueryRequest and AuditQueryEntry
├── routers/query.py         # CHANGED: session ownership refusal, session_id passthrough
├── services/
│   ├── query_pipeline.py    # CHANGED: session_id threaded to every log_query call
│   ├── audit_logger.py      # CHANGED: session_id parameter
│   └── chat_sessions.py     # NEW: create/list/rename/delete + ownership, over database.py
└── config.py                # CHANGED: CHAT_HISTORY_ENABLED, CHAT_SESSION_LIMIT

chat_ui/chat_ui/
├── state.py                 # CHANGED: sessions, active_session_id, lazy create, load, delete
├── models.py                # CHANGED: ChatSessionSummary
├── copy.py                  # CHANGED: rail strings
├── theme.py                 # CHANGED: rail tokens only
├── formatting.py            # CHANGED: auto-title derivation, relative activity time
└── components/
    ├── session_rail.py      # NEW: the rail
    └── shell.py             # CHANGED: rail slot in the layout
```

Design patterns:
- **Service module over raw database calls**: `app/services/chat_sessions.py` holds the ownership rule and the `CHAT_HISTORY_ENABLED` short-circuit in one place, the way `authz.py` holds the permission matrix. `ChatState` calls the service, never `database.py` directly.
- **Feature flag at the service boundary**: with `CHAT_HISTORY_ENABLED=false` the service returns empty lists and writes nothing, and the rail renders as absent. No caller branches on the flag.
- **Same message model both directions**: a stored row rehydrates into the same `ChatMessage` a live send produces.
- **Thread-offloaded blocking work**: every database call from `ChatState` goes through `asyncio.to_thread(...)`; state mutation stays inside `async with self`.
- **Backend-only credential unchanged**: `_token` stays a backend var and the Identity is still re-resolved on every send. `active_session_id` *is* client-visible, which is precisely why the server re-checks ownership on every read rather than trusting it.

Per `chat_ui/AGENTS.md`, every Reflex API used here is verified against the **reflex-docs** skill rather than recalled, and any run/compile/restart cycle follows **reflex-process-management**.

### 6.1 Design direction

Written against the **frontend-design** skill (pinned in `skills-lock.json`). Its first rule is that *"where the brief pins down a visual direction, follow it exactly — the brief's own words always win."* The direction is pinned twice over: `theme.py` declares the **inspection ledger**, and PRD-006 already extended it once. Palette and faces are inherited. The decision this PRD actually makes is **where the rail goes and what it says**.

**Subject, audience, job.** The subject is a shelf of bound volumes beside the ledger already on the desk. The audience is one employee with somewhere between two and thirty conversations. The single job of the rail is *get me back into the right one, and get out of the way*.

**What this design is refusing.** The template answer is the assistant-app sidebar: a dark panel, rounded pill rows, a hover-revealed kebab menu, relative timestamps under every title, and a bright "New chat" button at the top. It is the single strongest pull in this design space, and the skill names the failure mode directly — those are *"defaults rather than choices, and they appear regardless of subject."* The chat surface is a light, ruled, hairline record; a dark pill-shaped panel bolted to its left edge would be the one element on screen belonging to a different product.

**Color** — no new inks. The rail is `PAPER` ground against the transcript's `CARD`, separated by the existing `RULE`. The active session is marked with `INK` type against `HOVER`, not with a fill or an accent. The seven verdict inks stay in the transcript, where they mean something: a rail row is not a verdict and must not borrow one.

**Type** — `FONT_DISPLAY` at `TEXT_DATA` for session titles, `FONT_DATA` at `TEXT_TAG` for the activity time. Titles are set in the display face rather than the body serif because they are *labels on a shelf*, not prose — the same reasoning that made `FONT_DATA` dominant in PRD-006's register.

**Layout** — the rail is a fixed-width column at the left, under the existing masthead, so the header keeps spanning the full width and stays the one place the session's facts (who is sending, which model) live.

```
┌──────────────────────────────────────────────────────────────┐
│ HARNESS · Inspecting        Model [gpt-4]  Sending as m.silva │
├───────────────────┬──────────────────────────────────────────┤
│ + New chat        │                                          │
│                   │   YOU     Summarise the Q3 vendor spend  │
│ ▏Q3 vendor spend  │  ▕                                       │
│  2m ago           │   CLEARED Across the three vendors...    │
│                   │  ▕                                       │
│  Contract review  │   HELD    Already sent 4m ago            │
│  yesterday        │  ▕                                       │
│                   │                                          │
│  Payroll question │                                          │
│  3 days ago       │                                          │
├───────────────────┴──────────────────────────────────────────┤
│ [ Message...                                        ] [Send] │
└──────────────────────────────────────────────────────────────┘
```

**Signature — the spine.** The active session is marked by a solid vertical mark in `SPINE` on the left edge of its row, and nothing else: no fill, no rounded highlight, no bold. It is `RAIL_X` / `GLYPH` / `SPINE` — the chat's own rail and PRD-006's stamp margin — appearing a third time, at a third scale. Three surfaces, one structural device, each time encoding *which one of these is the one*. That is the skill's *"structural devices should encode something true about the content, not decorate it"*, and it is the only place boldness is spent here.

**On metadata in the rail.** Every session row carries a relative activity time and nothing else — no message count, no model, no verdict summary. The skill's caution about numbered markers generalizes: a figure belongs in the rail only if the reader needs it to choose a row, and they do not. They choose by title and by recency.

**Copy.** Per the skill, *"an empty screen is an invitation to act"* and *"an action keeps the same name through the whole flow."* The control is **New chat**, and what it produces is a chat. The empty rail reads as an invitation to start one rather than as a report that none exist. Deleting asks once, names the chat it is about to delete, and says plainly that the audit record is unaffected — because that is the fact a user in an audited system will actually want to know. Errors do not apologize: a failed transcript write says the turn was not saved and offers the retry.

**Motion.** One transition: the rail's collapse at a narrow viewport, respecting `prefers-reduced-motion`. Switching sessions does not animate — the skill's warning that *"extra animation contributes to the feeling that the design is AI-generated"* applies hardest to the operation a user will perform thirty times a day.

## 7. Tools/Features

| Feature | Maps to | Detail |
|---|---|---|
| Session rail | New `session_rail.py` | Lists the caller's sessions, newest activity first, capped at `CHAT_SESSION_LIMIT`. |
| Lazy session creation | `chat_sessions.create(...)` | Written on the first send, never on page load. |
| Auto-title | `formatting.py` | First prompt truncated at a word boundary; renameable, never re-derived after a rename. |
| Transcript restore | `list_chat_messages(...)` | Rehydrates into `ChatMessage`, rendered by the existing `rx.match`. |
| Verdict fidelity | Stored `kind` + metadata | A held, denied, forbidden or faulted turn restores with its ink and its actions. |
| Delete a chat | `delete_chat_session(...)` | One transaction, session plus messages; `audit_logs` untouched. |
| Ownership enforcement | `chat_sessions.py` | `user_id` in every `WHERE`; a foreign `session_id` is a 403 on the API and a no-op in the UI. |
| `session_id` on the audit row | `AUDIT_LOGS_ADDED_COLUMNS` | Nullable, additive; joins the record to the conversation. |
| `session_id` over the API | `QueryRequest` / `AuditQueryEntry` | Optional in, reported out; omitting it is today's behaviour exactly. |
| History switch | `CHAT_HISTORY_ENABLED` | `false` writes nothing, reads nothing, renders no rail. |
| Degraded write | `ChatState` | A failed transcript write keeps the bubble and reports it; the send already succeeded. |

## 8. Technology Stack

**Backend**
- Python 3.9+, FastAPI, Pydantic — versions as pinned in `requirements.txt`; no new dependency
- `libsql-client` / Turso as configured by PRD-007 — the new tables live in the same database, reached through the same `_shared_client()` and `_session()` helpers
- `uuid.uuid4()` for session ids — stdlib, no id library
- Schema managed as it already is: `CREATE TABLE IF NOT EXISTS` in `init_db()` plus the `AUDIT_LOGS_ADDED_COLUMNS` path for the one new column. **No ORM and no migration tool is introduced** — PRD-005 added `users` this way and PRD-007 kept it through the Turso move

**Frontend**
- Reflex as pinned in `chat_ui/requirements.txt`; plugins unchanged in `rxconfig.py`
- `rx.Base` for `ChatSessionSummary`, `rx.foreach` for the rail, `rx.cond` for the active mark, `rx.event(background=True)` for the loads — every API confirmed against the **reflex-docs** skill before implementation, per `chat_ui/AGENTS.md`
- `chat_ui/theme.py` extended in place for the rail's width, row height and gutter. Per the **frontend-design** skill the visual direction is inherited, not re-proposed: the skill's own rule is that a pinned direction wins, and `theme.py`'s inspection ledger is that pin. No icon set, no new font, no component library beyond what is configured

**Standard library**
- `asyncio.to_thread` for the database offload, `datetime` for activity times, `uuid` for ids

**Testing**
- `pytest` + `pytest-asyncio`, already in use; new suites `tests/test_chat_sessions.py` and `tests/test_session_ownership.py`

## 9. Security & Configuration

**This PRD changes the data-at-rest posture, and that is its most consequential decision.** Until now the durable store held `prompt_hash`, a truncated `prompt_preview` and a truncated `response_preview`. `chat_messages` holds the full prompt as typed and the full released response. The mitigations are structural, not procedural:

- **`CHAT_HISTORY_ENABLED=false`** turns the feature off entirely — no write, no read, no rail — and the deployment gets today's ephemeral behaviour from the same image. A deployment that cannot hold prompt text has a supported configuration rather than a fork.
- **Responses are stored redacted.** The `assistant` row holds `QuerySuccessResponse.response`, which is what PII redaction released. The raw upstream text is never written to `chat_messages`.
- **Prompts are stored as typed, and only the author reads them.** The owner wrote the text and is the only party who can retrieve it. This is a real widening over `prompt_preview` and is recorded here as such rather than buried — Section 13 carries the change that would let the transcript store the redacted prompt instead.
- **The console does not read this data.** PRD-006's register and summary are unchanged, so no admin surface renders a transcript. The admin gains `session_id` and nothing else.

**Ownership.** Every session function takes `user_id` and scopes on it. `active_session_id` is a client-visible Reflex var and therefore untrusted input, exactly as PRD-005 Risk 5 treats a client-held role: the server re-checks on every read. On `POST /query`, a `session_id` belonging to another identity is refused with 403 in the same place `user_id` mismatch already is, and the refusal is audited.

**RBAC interaction.** No new permission. `query:submit` still gates sending; owning a session grants nothing beyond reading and deleting it. The break-glass `admin` identity from `identity.py` owns its own sessions like any other user and gains no read access to anyone else's — a deliberate refusal, since `audit:read:all` is about the record and this is not the record.

**Deletion semantics.** `delete_chat_session` removes rows from `chat_sessions` and `chat_messages` only. `audit_logs` is append-only and stays so; the orphaned `session_id` on those rows is expected, and it is what preserves the evidence when a user tidies their list. The confirmation copy says this in the user's words.

**New environment variables**

| Variable | Default | Purpose |
|---|---|---|
| `CHAT_HISTORY_ENABLED` | `true` | Master switch for transcript persistence. |
| `CHAT_SESSION_LIMIT` | `50` | Sessions listed per user in the rail. |

Both land in `app/config.py`, `.env.example` and the README's environment table, following the pattern of `PII_REDACTION_ENABLED` and `RBAC_ENABLED`.

**Unchanged**: `ADMIN_TOKEN`, `RBAC_ENABLED`, `RBAC_ROLES_FILE`, `PII_REDACTION_ENABLED`, `DATABASE_URL`, `DB_BOOTSTRAP_ENABLED`, the Reflex reserved routes, and the `Caddyfile`'s `@backend_routes` matcher — this PRD adds no HTTP route.

## 10. API Specification

**No new endpoints.** Session management is in-process from `ChatState` through `app/services/chat_sessions.py`, the same boundary PRD-006's console holds against `database.py`. A REST surface for sessions would need its own auth story and its own tests to earn a place, and nothing in this PRD's scope calls for one; Section 13 records it as the follow-up it is.

`POST /query` — two additive changes, both backward compatible:

```jsonc
// Request
{
  "prompt": "Summarise the Q3 vendor spend",
  "model": "gpt-4",
  "device": "Mozilla/5.0 ...",
  "session_id": "0f6c2e5a-9b3d-4c81-a7f2-1d5e8c9b0a34"  // NEW, optional
}
```

- Omitted → today's behaviour exactly: the audit row's `session_id` is `NULL`.
- Present and malformed → `422`, from Pydantic validation.
- Present and owned by another identity → `403`, `"session_id does not belong to the authenticated identity"`.

Response shapes are unchanged. All four `QueryResponse` members keep their current fields.

`GET /audit` — `AuditQueryEntry` gains `session_id: Optional[str]`. Additive on a response model; existing consumers ignore it.

`GET /stats`, `GET /health` — unchanged.

## 11. Success Criteria

**MVP is done when** a user can hold several named conversations, leave, come back on a different instance, and find each one exactly as they left it — verdicts included — while the audit trail gains a join key and no admin surface gains a transcript.

Functional requirements:
- [ ] A reload restores the active session's transcript, in order, with every bubble's kind and metadata intact
- [ ] A held, denied, forbidden or faulted turn restores with its ink, its detail and its actions
- [ ] The rail lists the caller's sessions newest-activity-first and marks the active one
- [ ] Sending in a session moves it to the top of the rail
- [ ] Opening the app and sending nothing creates no session row
- [ ] The first send auto-titles the session from the prompt; a rename persists and survives further sends
- [ ] Switching sessions replaces the transcript and nothing else — the model selector and the signed-in user are untouched
- [ ] Deleting a chat removes it and its messages, leaves every `audit_logs` row in place, and `count_audit_logs()` is unchanged across the delete
- [ ] A `session_id` from another user is refused: 403 on `POST /query`, and `list_chat_messages` returns empty rather than another user's rows
- [ ] `POST /query` without `session_id` behaves identically to the current release and writes `NULL`
- [ ] `GET /audit` reports `session_id` for rows that have one
- [ ] `CHAT_HISTORY_ENABLED=false` writes no row, reads no row, renders no rail, and leaves the chat fully working
- [ ] A forced failure in `append_chat_message` leaves the bubble on screen, reports that the turn was not saved, and does not clear the transcript
- [ ] Two instances against one database serve the same session (the `tests/test_two_instance_smoke.py` pattern, extended)

Quality indicators:
- [ ] `tests/test_query_router.py`, `tests/test_integration.py`, `tests/test_route_reservations.py`, `tests/test_admin_auth.py`, `tests/test_audit_router.py`, `tests/test_stats_router.py`, `tests/test_rbac.py` and `tests/test_summary.py` pass **unmodified**
- [ ] `test_added_columns_declaring_not_null_also_declare_a_default` still holds for the new audit column
- [ ] `init_db()` issues no `ALTER` on a current schema — the steady-state assertion PRD-007 relies on across hot reloads
- [ ] No new dependency in either `requirements.txt`
- [ ] No function in `database.py` returns a session or a message without a `user_id` parameter — asserted by signature inspection in `tests/test_session_ownership.py`
- [ ] Every rail string resolves from `copy.py`; every colour and size from `theme.py`; `tests/test_contrast.py` covers any new pairing
- [ ] Section 6.1's direction is met: the rail carries no fill, no pill, no accent colour and no verdict ink
- [ ] Keyboard-reachable rail with visible focus; the rail collapses at a narrow viewport and `prefers-reduced-motion` is honoured

## 12. Implementation Phases

**Phase 1 — Schema and store**
- Goal: sessions exist in the database, owned.
- Deliverables: the two tables and their indexes in `models.py`; `session_id` in `AUDIT_LOGS_ADDED_COLUMNS`; the nine functions in `database.py`; `app/services/chat_sessions.py` with the ownership rule and the `CHAT_HISTORY_ENABLED` short-circuit; the two config settings.
- Validation: `tests/test_chat_sessions.py` and `tests/test_session_ownership.py` — a session created under one user is invisible to another through every read path; delete removes messages and leaves `count_audit_logs()` unchanged; `init_db()` is idempotent and issues no `ALTER` on a current schema; the flag off makes every write a no-op.

**Phase 2 — Pipeline and API**
- Goal: the record names the conversation.
- Deliverables: `session_id` on `QueryRequest` and `AuditQueryEntry`; threaded through `run_query` to every `log_query` call site including the denial and failure arms; the 403 on a foreign session in `routers/query.py`.
- Validation: a request without `session_id` produces a row identical to today's; a request with one round-trips it to `GET /audit`; a foreign `session_id` is a 403 and is audited; the four blocked outcomes each carry the session on their audit row; PRD-001/005 router tests unmodified.

**Phase 3 — State and restore**
- Goal: the conversation comes back.
- Deliverables: `ChatSessionSummary`; `ChatState` session list, active id, lazy create, load, switch, rename, delete; the persist-after-append write with its degraded arm; auto-title in `formatting.py`; `logout()` clearing session state.
- Validation: state-level tests drive the flow directly — a send creates exactly one session, a second send creates none, a switch replaces `messages`, a patched `append_chat_message` raising leaves the transcript intact and reports, logout empties state while the rows survive, and each of the seven bubble kinds survives a store/restore round trip unchanged.

**Phase 4 — Surface and hardening**
- Goal: the rail on screen, and the whole thing holds under failure.
- Deliverables: `session_rail.py`, the `theme.py` rail tokens, the copy module additions, the rail's three states, the delete confirmation, the collapse at a narrow viewport, contrast assertions, the extended two-instance smoke test.
- Validation: full suite green with the listed suites unmodified; a forced read failure renders the rail's fault state rather than an empty list; the palette-drift assertion (Risk 6) fails on a fill or a verdict ink in the rail; a self-critique pass against Section 6.1 — the skill's *"remove one accessory"* — with anything that does not serve *get me back into the right one* cut.

## 13. Future Considerations

- **Multi-turn context — the headline follow-up, and the reason it is not here.** Sending a session's history to the model breaks the duplicate checker: `check_duplicate` hashes the whole prompt against a global 24-hour window with no user and no session scope, so in a real conversation *"yes"*, *"go on"* and *"thanks"* would collide constantly and be held. The README's OpenAI-compatible endpoint section already poses the same question — whether to hash the last turn or the whole array — and answers neither. Rescoping the hash (minimally to `session_id + prompt`, more likely to `user_id + session_id + prompt`) is a change to the product's central security control and deserves its own PRD, its own threat reasoning and its own tests. Bolting it onto a persistence release would decide it by accident. `chat_messages` is deliberately shaped so that PRD is a read away from its input.
- **Storing the redacted prompt.** `run_query` computes `redacted_prompt` and discards it. Returning it would let `chat_messages` hold what actually left the building instead of what the user typed, which is both the safer artifact at rest and the more honest transcript. Carried forward from PRD-004 Section 13, and this PRD raises its value.
- **Session-scoped duplicate detection as a feature, not a fix.** Once the hash is scoped, "you already asked this in *Vendor contract review*" becomes a link the user can follow — the rail turns the duplicate verdict from a dead end into navigation.
- **Sessions in the admin console.** `session_id` reaches `GET /audit` in this PRD and stops. Grouping the register by conversation is a natural PRD-006 extension and needs no schema change, only a new read.
- **A REST surface for sessions.** `GET/POST/DELETE /sessions` would let a non-browser client hold conversations. Deferred because nothing but the chat needs it yet, and because it would be the first endpoint whose authorization is per-row.
- **Retention and expiry.** No TTL exists. A deployment holding prompt text will eventually want one, and it pairs naturally with a retention policy for `audit_logs`, which also has none.
- **Search across sessions.** Once transcripts exist, "where did I ask about the vendor spend" becomes answerable. Full-text search over `chat_messages` is the obvious next read, and the obvious next disclosure question.
- **Concurrent tabs.** Two tabs on one session do not see each other's writes. A background poll or a version column on `chat_sessions` would close it; today the second loader simply wins its own view.

## 14. Risks & Mitigations

**1. Persistence quietly becomes the product's biggest disclosure surface.**
Full prompt text at rest under a user's name is a larger exposure than every previous PRD combined, and it arrives as a convenience feature rather than as a security change — which is exactly how such a thing gets waved through.
*Mitigation*: `CHAT_HISTORY_ENABLED` is scope, not a nicety — a supported off state with a test asserting no row is written. Responses are stored redacted. No admin surface renders a transcript. Section 9 states the widening in plain terms rather than leaving it to be discovered, and Section 13 carries the change that narrows it.

**2. Row-level ownership is new to this codebase and will be forgotten somewhere.**
RBAC has never asked *whose row is this*, so there is no habit to fall back on, and the failure mode is silent: a missing `WHERE user_id = ?` returns data rather than an error.
*Mitigation*: the rule lives in the signature — `user_id` is required and undefaulted on every session-scoped function, so an omission is a `TypeError` at the call site rather than a leak at runtime. `tests/test_session_ownership.py` inspects the signatures and drives every read path with a foreign id.

**3. `active_session_id` is a client-visible Reflex var.**
PRD-005 Risk 5 established that a state var is serialized to the client and mutable by client-originated events. A session id is exactly that, and it names a row.
*Mitigation*: it is treated as untrusted input everywhere. The server re-checks ownership on every read against the freshly resolved Identity, never against the var; the API refuses a foreign session with 403 and audits the refusal.

**4. Sessions invite multi-turn, and multi-turn breaks deduplication.**
Once conversations look like conversations, sending the history feels like the obvious next commit — and the first short reply will be held as a duplicate of every other short reply in the deployment.
*Mitigation*: the pipeline signature is unchanged and multi-turn is an explicit out-of-scope item, with the mechanism written down in Sections 4 and 13 so the "improvement" cannot be added without meeting the argument. `call_openrouter` keeping `prompt: str` is the structural version of the same refusal.

**5. A failed transcript write could take a successful turn with it.**
The model answered, the audit row is written, and then the transcript insert fails — a naive implementation raises and the user loses a paid, logged answer.
*Mitigation*: the write happens after the bubble is appended and is caught on its own, following PRD-004's "no silent drops" invariant: the bubble stays, a notice says the turn was not saved, and the session is untouched. A test patches `append_chat_message` to raise and asserts the transcript is intact.

**6. The rail drifts into the assistant-app sidebar.**
"Chat with a session list" is the most templated pattern in current UI, and the drift arrives one reasonable component at a time — a card for a row, a rounded highlight for the active one, an accent for the button.
*Mitigation*: Section 6.1's refusals are checkable items in Section 4 and Section 11, and a component test asserts the rail renders no `TINT_*` value, no verdict ink and no border radius beyond `theme.RADIUS` — the drift fails a test rather than a review, as PRD-006 Risk 6 established.

**7. `init_db()` gains two more `CREATE TABLE` statements and one more `ALTER` candidate.**
It runs at import time on every Reflex hot reload and on every instance boot, and PRD-007 documented the race where N instances all try the same `ALTER`.
*Mitigation*: the tables use `CREATE TABLE IF NOT EXISTS` and are therefore idempotent by construction; the one new column goes through `_add_missing_columns`, which already treats a duplicate-column loss as convergence. The existing assertion that a current schema issues no `ALTER` is extended to cover it.

## 15. Appendix

**Related documents**
- [PRD-001 — Harness IA](../PRD-001-harness-ia/PRD.md) — defines `audit_logs`, `POST /query`, `GET /audit` and the pipeline this PRD threads `session_id` through.
- [PRD-002 — Embedded Chat UI (Reflex)](../PRD-002-reflex-chat-ui/PRD.md) — the single-process architecture, the in-process consumption pattern and the reserved routes inherited here.
- [PRD-004 — Chat UI Redesign](../PRD-004-chat-ui-redesign/PRD.md) — the `ChatMessage` model, the outcome vocabulary, the `theme.py` tokens, centralized copy, the `asyncio.to_thread` offload and the "no silent drops" invariant. `chat_messages` is that model given a table.
- [PRD-005 — RBAC](../PRD-005-rbac/PRD.md) — `Identity`, `resolve()`, the permission matrix, and Risk 5's rule about client-visible state vars, which governs `active_session_id`.
- [PRD-006 — Admin Console](../PRD-006-admin-console/PRD.md) — the surface this PRD leaves untouched, and the source of the stamp-margin device the rail's spine continues.
- [PRD-007 — Turso Migration](../PRD-007-turso-migration/PRD.md) — the shared database the new tables live in, `_shared_client()`/`_session()`, the `_add_missing_columns` convergence rule, and `tests/test_two_instance_smoke.py`.

**Code dependencies (modified)**
- `app/db/models.py`, `app/db/database.py`, `app/models/schemas.py`, `app/routers/query.py`, `app/services/query_pipeline.py`, `app/services/audit_logger.py`, `app/config.py`
- `chat_ui/chat_ui/state.py`, `models.py`, `copy.py`, `theme.py`, `formatting.py`, `components/shell.py`

**Code dependencies (read, not modified)**
- `app/services/identity.py` — `resolve`, `Identity`
- `app/services/authz.py` — `authorize`, `PERMISSION_QUERY_SUBMIT`
- `app/services/duplicate_checker.py`, `app/services/pii_redactor.py`, `app/services/openrouter_client.py` — untouched, and Section 4 says so on purpose
- `chat_ui/chat_ui/components/chat.py`, `components/bubbles.py` — the `rx.match` a restored bubble renders through

**Tests that must pass unmodified**
`tests/test_query_router.py`, `tests/test_integration.py`, `tests/test_route_reservations.py`, `tests/test_admin_auth.py`, `tests/test_audit_router.py`, `tests/test_stats_router.py`, `tests/test_rbac.py`, `tests/test_authz.py`, `tests/test_identity.py`, `tests/test_duplicate_checker.py`, `tests/test_pattern_detector.py`, `tests/test_pii_redactor.py`, `tests/test_summary.py`, `tests/test_register.py`

**Skills referenced**: frontend-design, reflex-docs, reflex-process-management
