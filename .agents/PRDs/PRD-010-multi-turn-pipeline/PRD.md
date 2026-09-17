---
id: PRD-010
slug: multi-turn-pipeline
title: Multi-turn Pipeline — Conversations In, Off the Shared Threadpool
status: draft
base_branch: main
epic_branch: epic/PRD-010-multi-turn-pipeline
created: 2026-09-17
updated: 2026-09-17
---

## 1. Executive Summary

The pipeline speaks exactly one user turn. `run_query(identity, prompt: str, …)` ([app/services/query_pipeline.py](../../../app/services/query_pipeline.py)) takes a string. `call_openrouter` ([app/services/openrouter_client.py](../../../app/services/openrouter_client.py)) always sends `[{"role": "user", "content": prompt}]`: no system prompt, no history, no generation parameters, and a hard-coded `_TIMEOUT_SECONDS = 30.0`. It reads only `choices[0].message.content`, so a `null` content surfaces as a `KeyError`-shaped "unexpected response shape". A chat session is therefore a saved transcript the model never sees (README, *Multi-turn context*). Every later PRD in the OpenAI-compatible track (011–016) needs a conversation, not a string.

There is also a process-level problem that multi-turn makes worse. The Reflex backend mounts the FastAPI app (`api_transformer=fastapi_app` in `chat_ui/chat_ui/chat_ui.py`), so both ingresses share one process. `POST /query` is a sync `def` route, so each upstream wait holds one of anyio's ~40 threadpool tokens. `ChatState._do_send` runs `run_query` through `asyncio.to_thread`, which holds a thread in the event loop's *default* executor, the same pool that serves session-rail reads and the admin snapshot. Larger contexts mean longer upstream calls, and a few slow ones stall `/health`, `/query` and the chat UI together.

This PRD makes the pipeline take a **normalized list of messages**. It sends them to OpenRouter with an **allowlisted** set of generation parameters, and it runs every upstream wait on a **dedicated, bounded executor** instead of the shared pools. `POST /query` becomes the one-message case through a thin adapter, with the same request and response shapes and the same six outcomes. The chat UI sends the session's history, built from successful exchanges only and always redacted. `CHAT_HISTORY_ENABLED=false` keeps today's single-turn behaviour byte for byte. PRD-009's `dedup_key` finally receives the real conversation, with no second definition of "duplicate".

**MVP goal:** in the chat UI, the model can answer "what did I just ask?". `/query` still passes the six-outcome regression. Ten concurrent slow upstream calls do not delay `/health` or a fast `/query`.

## 2. Mission

Turn the harness from a prompt filter into a conversation filter without widening any ingress, and without letting one slow model call hold the process hostage.

Core principles:
- **One pipeline, many shapes in.** `run_conversation` is the only pipeline. `run_query(prompt=…)` is a one-line adapter over it, so `/query`, the chat UI and PRD-014's endpoint share one ordered sequence of checks.
- **Normalize at the edge, never inside.** OpenAI message shapes (content-part lists, `null`) become one internal `Message(role, content: str)` in one function. Nothing past that function ever sees a list or a `None`.
- **Refuse, don't silently truncate.** The pipeline refuses a conversation over its limits, with the limit named in the response. Truncation is a *client* decision. The chat UI makes it visibly, not silently.
- **The model never sees what it did not see the first time.** History is redacted at the pipeline on every send, whatever its source. The model gets redacted text only, while the duplicate key stays on raw text (PRD-009 invariant).
- **No new ingress in this PRD.** No HTTP route accepts `messages` or generation parameters yet. The only multi-turn caller is `ChatState`, whose history comes from the database, not the browser. Caller-supplied history arrives with PRD-014, after PRD-011/012/013 have hardened the checks it needs.
- **Pin before you change.** The six-outcome regression (PRD-009 STORY-001) and the client's payload shape are asserted green before any internal line moves.

## 3. Target Users

**End User (Employee)**: chats in the Reflex UI. Today every turn is answered as if it were the first, so "and in Python?" and "shorten that" get non-answers. They need the session to be a conversation, and when earlier turns are left out for size they need to be told, not left to find out.

**Integrating Developer**: calls `POST /query` from scripts. They need nothing to change: same body, same response union, same status codes. The one new outcome, a context-limit refusal, is reachable only with a prompt larger than any realistic single-turn request (Section 6.5).

**Platform Operator**: runs the single container (`reflex run --env prod --backend-only` behind Caddy). They need slow upstream calls not to take `/health` down with them, so the orchestrator does not restart a healthy container. They also need two new settings with safe defaults: the timeout and the executor size.

**Security/Compliance Admin**: owns what reaches the model. They need history to go out redacted, blocked turns never to be replayed into context, generation parameters limited to an allowlist, and every refusal audited like any other outcome.

**PRD-011 / 012 / 013 / 014 implementers** (internal): they need a `Message` model and a `run_conversation` entry point to build on. The provisional "last user turn" inspection policy is marked as theirs to replace, in one named function.

## 4. MVP Scope

### In Scope

**Message model (`app/models/messages.py`, new)**
- [ ] `Role = Literal["system", "user", "assistant", "tool"]` and a frozen `Message(role, content: str)` dataclass that structurally satisfies PRD-009's `DedupTurn`
- [ ] `normalize_message(raw: Mapping) -> Message` and `normalize_messages(raw: Sequence[Mapping]) -> list[Message]` for OpenAI shapes: `content` as `str`, as a list of parts, or `null`
- [ ] `MessageNormalizationError` for unknown roles, non-text parts, `null` content on a non-assistant role, and `tool_calls` present

**Settings (`app/config.py`)**
- [ ] `OPENROUTER_TIMEOUT_SECONDS: float = 120.0` (must be `> 0`)
- [ ] `CONTEXT_MAX_MESSAGES: int = 100` (must be `≥ 1`)
- [ ] `CONTEXT_MAX_CHARACTERS: int = 200_000` (must be `≥ 1`; the sum of `len(content)` over all messages)
- [ ] `PIPELINE_MAX_WORKERS: int = 32` (must be `≥ 1`)
- [ ] Startup-error validators in the `CHAT_SESSION_LIMIT` style, each message saying what to set instead

**OpenRouter client (`app/services/openrouter_client.py`)**
- [ ] `call_openrouter(messages: Sequence[Message], model, api_key, params: Optional[GenerationParams] = None, client=None)`
- [ ] `GenerationParams` allowlist: `temperature`, `max_tokens`, `top_p`, `stop`, range-validated, sent only when set
- [ ] Timeout read from `settings.OPENROUTER_TIMEOUT_SECONDS`
- [ ] `null` content → an explicit `OpenRouterError` naming `finish_reason`, and naming tool calls when `tool_calls` is present
- [ ] A payload for one user message with no params is byte-identical to today's

**Concurrency (`app/services/pipeline_executor.py`, new)**
- [ ] One process-wide `ThreadPoolExecutor(max_workers=PIPELINE_MAX_WORKERS, thread_name_prefix="pipeline")`
- [ ] `async def run_in_pipeline(fn, /, *args, **kwargs)`, which is the only way either ingress runs the pipeline
- [ ] `POST /query` becomes `async def`; its body (session-ownership check, audit, pipeline) runs as one sync unit in the executor
- [ ] `ChatState._do_send` calls `run_in_pipeline` instead of `asyncio.to_thread` for the pipeline call

**Pipeline (`app/services/query_pipeline.py`)**
- [ ] `run_conversation(identity, messages, device, model, openrouter_api_key, params=None, call_openrouter=…, session_id=None)`
- [ ] `run_query(identity, prompt, …)` becomes an adapter: `run_conversation(identity, [Message("user", prompt)], …)`, with a signature unchanged for every existing caller and test
- [ ] Structural validation: non-empty, last message `role == "user"`, no `tool` role (PRD-016) → `InvalidConversationError`, raised before any audit row (programming error, not an outcome)
- [ ] Context-limit refusal (`QueryBlockedContextLimitResponse`), audited, checked after authorization and before the duplicate check
- [ ] `dedup_key(identity.user_id, messages)` over the raw conversation as received, replacing the private `_UserTurn`
- [ ] Provisional inspection policy in one named function, `_inspection_target(messages)`: pattern detection runs on the last `user` turn only
- [ ] Outbound redaction applies to **every** message's content (D5). Audit PII fields keep their meaning: last user turn plus output (D7)
- [ ] Audit row `prompt` = last user turn content, so `prompt_hash` keeps its meaning

**History (`app/services/chat_history.py`, new)**
- [ ] `assemble(identity, session_id) -> list[Message]`: successful exchanges only, built from `kind == "assistant"` rows as `(user: row.prompt, assistant: row.content)`
- [ ] `fit(history, new_turn, max_messages, max_characters) -> (messages, trimmed_exchanges)`: a pure function that drops the oldest whole exchanges until the conversation fits
- [ ] `chat_messages.history_trimmed INTEGER` (nullable), converged by `init_db()` in the PRD-008 pattern

**Chat UI (`chat_ui/chat_ui/state.py`, components)**
- [ ] With history on and a session: assemble → fit → `run_conversation`. With history off, or on the first send of a new chat: `run_query(prompt=text)` exactly as today
- [ ] A context-limit refusal renders as an in-thread `context_limit` bubble through the existing bubble path
- [ ] When `history_trimmed > 0`, the assistant bubble's metadata footer reads, for example, "3 earlier exchanges were not sent to the model"

**Tests & docs**
- [ ] Client tests: payload shape, parameter allowlist, timeout wiring, `null` content
- [ ] Normalization and pipeline tests over multi-turn input
- [ ] Concurrency test: ten blocked upstream calls do not delay `/health` or a fast `/query`
- [ ] Six-outcome regression plus a seventh row (context limit); chat UI regression with history off
- [ ] Two-instance smoke extended with a multi-turn chat
- [ ] README: *Multi-turn context* moves from roadmap to shipped; `.env.example` gains the four settings

### Out of Scope
- [ ] `messages`, `params` or `system` on `POST /query`'s request body, and any new HTTP ingress (PRD-014)
- [ ] Tool calls, the `tools` parameter, `tool` role turns in the pipeline (PRD-016)
- [ ] Streaming, SSE (PRD-014)
- [ ] The final per-role inspection policy for patterns (PRD-011) and PII (PRD-012)
- [ ] Token budgets, per-user rate limits, cost accounting for history (PRD-013)
- [ ] An `async` rewrite of the pipeline, database layer or redactor (D1)
- [ ] Token-based context limits (characters are the proxy; tokenizer-accurate limits are future work)
- [ ] Reversible PII placeholders in history (PRD-012)
- [ ] A system prompt set by the chat UI or by the deployment
- [ ] Changing `dedup_key`, `DEDUP_KEY_VERSION` or the lookup (PRD-009 is final for this PRD)

## 5. User Stories

1. **As an end user, I want the model to see my earlier turns in this chat, so that follow-ups like "shorten that" work.**
   *Example:* I ask "Give me a regex for ISO dates", then "now make it accept times too". The second answer extends the first regex instead of asking which regex I mean.

2. **As an end user, I want to be told when earlier turns were left out, so that I know why the model forgot something.**
   *Example:* in a 60-exchange session the footer under the reply reads "12 earlier exchanges were not sent to the model".

3. **As an end user, I want blocked and failed turns kept out of the model's context, so that a refused prompt cannot come back in through history.**
   *Example:* my "ignore previous instructions…" turn was held as suspicious. The next send's history contains only the exchanges that got an answer.

4. **As an integrating developer, I want `POST /query` to behave exactly as before, so that my scripts need no change.**
   *Example:* the same body returns the same `SUCCESS` payload, the same `BLOCKED` reasons and the same 502/500 mapping, and the upstream request body is byte-identical.

5. **As a platform operator, I want slow model calls not to block health checks or other requests, so that one slow model does not restart a healthy container.**
   *Example:* ten requests to a model taking 60 s are in flight, and `GET /health` still answers in milliseconds.

6. **As a compliance admin, I want history sent redacted and parameters allowlisted, so that multi-turn exposes no more than single-turn did.**
   *Example:* my first turn mentioned `jane@corp.com`. On every later send the model receives `<EMAIL_ADDRESS>` in that position, and an attempt to pass `logit_bias` is rejected before any network call.

7. **As an end user who says "yes" often, I want the same short reply after a different exchange not to be held as a duplicate, so that ordinary conversation works.**
   *Example:* "yes" after "Should I add tests?" and later "yes" after "Want the SQL version?" both go through, because PRD-009's key sees different prefixes.

8. **As the PRD-011/012/014 implementer, I want one `Message` model, one `run_conversation` and one named provisional policy, so that I replace a function instead of re-plumbing the pipeline.**
   *Example:* PRD-011 changes `_inspection_target` to cover every `user` turn and every `system` turn, and no caller changes.

## 6. Core Architecture & Patterns

### 6.1 Request flow

```
POST /query (async def)                        ChatState._do_send (background event)
  │ body → run_in_pipeline(_handle_query)        │ history on + session? ──no──► run_in_pipeline(run_query, prompt=text)
  ▼                                              │ yes
  [pipeline executor thread]                     ▼ run_in_pipeline(chat_history.assemble) → fit() (pure)
  foreign-session check + audit (unchanged)      │
  run_query(prompt) ──adapter──┐                 └──► run_in_pipeline(run_conversation, messages)
                               ▼                                    │
                    run_conversation(identity, messages, …) ◄───────┘
                      0. validate structure            → InvalidConversationError (no row)
                      1. key = dedup_key(user_id, messages)   (raw text)
                      2. authorize / model / BYOK       → forbidden     (row)
                      3. context limits                 → context_limit (row, success=0)   ← new
                      4. check_duplicate(user_id, key)  → duplicate     (row)
                      5. patterns on _inspection_target(messages)       → suspicious (row)
                      6. redact every message (D5); entities of last user turn kept (D7)
                      7. call_openrouter(redacted_messages, model, key, params)
                      8. redact response; audit; return
```

The check order from PRD-009 Section 6.1 is preserved: authorization before duplicate, duplicate before patterns and redaction. The context-limit check sits between authorization and duplicate for two reasons. A caller without `query:submit` learns nothing about limits. And an over-limit conversation never consults, or counts toward, the duplicate window.

### 6.2 The message model

```python
Role = Literal["system", "user", "assistant", "tool"]

@dataclass(frozen=True)
class Message:
    role: Role
    content: str          # always a str after normalization; "" is legal only for assistant

def normalize_message(raw: Mapping[str, Any]) -> Message: ...
```

Normalization rules, each deliberate:

| Input `content` | Result | Why |
|---|---|---|
| `"text"` | `"text"` | Common case |
| `[{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]` | `"a\nb"` | Parts joined with `\n`: deterministic, and it keeps part boundaries visible to pattern detection (a part ending in `ignore` followed by one starting `previous` must not fuse into a new word) |
| Any part whose `type != "text"` (e.g. `image_url`) | `MessageNormalizationError` | No inspection exists for non-text content, so it is refused rather than dropped |
| `null` with `role == "assistant"` | `""` | Valid in OpenAI history (a tool-call turn) |
| `null` with any other role | `MessageNormalizationError` | A user turn with nothing in it is malformed |
| `tool_calls` key present | `MessageNormalizationError` | PRD-016 |
| Unknown `role` | `MessageNormalizationError` | |

`tool` is a valid `Role` so that PRD-016 does not have to widen the type. `run_conversation` refuses it structurally, matching `dedup_key`'s existing `ValueError`, so neither layer guesses.

In this PRD, normalization has **no production HTTP caller**. `ChatState` builds `Message` objects directly from rows. The normalizer ships now, fully tested, because it defines the model PRD-011/012/013 design against, and PRD-014 is its first ingress.

### 6.3 Off the shared pools (Decision D1, with a correction to the brief)

The brief proposed "dedicated executor first; async client inside `call_openrouter` only". **The second half would not help.** `run_query` is synchronous. If `call_openrouter` awaited an `httpx.AsyncClient` internally, it would still need a running loop and a thread to block on while `run_query` waits for its result. The thread doing the waiting would still be anyio's (for `/query`) or the default executor's (for `ChatState`). What frees the shared pools is changing **whose thread** waits.

```python
# app/services/pipeline_executor.py
_executor = ThreadPoolExecutor(max_workers=settings.PIPELINE_MAX_WORKERS, thread_name_prefix="pipeline")

async def run_in_pipeline(fn, /, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, functools.partial(fn, *args, **kwargs))
```

- **`POST /query` becomes `async def`.** Its whole body, including the foreign-session `owns()` check and its audit write, is moved into a sync `_handle_query(request, identity)` and awaited through `run_in_pipeline`. No database or Presidio call runs on the event loop. The `require_permission` dependency stays sync; FastAPI runs it in the threadpool briefly, as today. The exception-to-status mapping is unchanged and wraps the `await`.
- **`ChatState` uses the same executor** for the pipeline call and for `chat_history.assemble`. Session-rail reads and admin snapshots stay on `asyncio.to_thread`, which is exactly the pool this change stops starving.
- **Saturation queues and does not fail.** With all `PIPELINE_MAX_WORKERS` threads waiting upstream, the next pipeline call waits in the executor's queue. `/health`, static routes and non-pipeline Reflex events are unaffected. The wait is bounded by `OPENROUTER_TIMEOUT_SECONDS`.
- **Not async end to end.** The libSQL client, Presidio and `log_query` are sync. Rewriting them is the "largest refactor since PRD-002" risk the brief names, for no gain over a dedicated pool at this scale.

### 6.4 History assembly (Decisions D3, D4, D5)

Two facts about `chat_messages` decide the design:

1. **The first user bubble of a new chat is never persisted.** `_append_and_persist` runs with `session_id == ""` before `chat_sessions.create` (README, *Limitations*). Rebuilding pairs from `user` rows would lose every session's first question.
2. **Every `assistant` row already holds its exchange.** `row.prompt` is the raw user text and `row.content` is the redacted reply, the only form ever persisted (PRD-008 Section 9).

So `assemble` reads **only `kind == "assistant"` rows**, in `id` order, and emits `Message("user", row.prompt), Message("assistant", row.content)` for each. D4 holds by construction: `duplicate`, `injection`, `forbidden`, `upstream_error`, `internal_error` and `context_limit` rows are never read, and neither are the user bubbles that preceded them.

`fit(history, new_turn, max_messages, max_characters)` drops the **oldest whole exchange** (never half of one) until both limits hold, and returns how many it dropped. If the new turn alone exceeds the character limit, `fit` returns it unchanged with no history, and the pipeline refuses it (6.5). The client truncates, and the pipeline refuses (D2).

**D5, redacted always, is enforced at the pipeline, not at assembly.** Stored `prompt` is raw, and PRD-014 callers will send whatever they like, so step 6 of 6.1 redacts every message on every send. Presidio's default operator writes `<ENTITY_TYPE>` placeholders, which the analyzer does not re-detect, so an already-redacted assistant turn passes through unchanged.

**The duplicate key sees the raw conversation as received:** raw user prompts plus stored (redacted) assistant replies, after `fit`. That is deterministic for a given transcript, and it is exactly what a PRD-014 client would resend, since it only ever received the redacted reply.

### 6.5 Context limits (Decision D2)

```python
class QueryBlockedContextLimitResponse(BaseModel):
    status: Literal["BLOCKED"] = "BLOCKED"
    reason: str                       # "Conversation exceeds context limit"
    limit: Literal["messages", "characters"]
    maximum: int
    actual: int
```

- Added to `QueryResponse` and `QueryPipelineResult`. `messages` is checked first, and only one limit is reported.
- **Audited** with `success=False`, `error_message="context limit: characters 250000 > 200000"`, and the non-NULL `dedup_key`. `success=0` means it never counts as a prior query (PRD-009 Section 6.3), which is correct because it never got a verdict. No new `audit_logs` column.
- **`/query` reachability:** a single prompt over 200,000 characters (≈50k tokens) is now refused where it previously went upstream. This is the one intended behaviour change on `/query`. It is documented in the README and pinned as regression row 7.

### 6.6 Provisional inspection policy (Decision D6)

```python
def _inspection_target(messages: Sequence[Message]) -> str:
    """PROVISIONAL (PRD-010 D6): the last user turn. PRD-011 replaces this."""
```

Pattern detection runs on this string only. For the chat UI that is sufficient: every history user turn was itself the last user turn of an earlier send that passed, because D4 admits only answered exchanges. For caller-supplied history it is not sufficient. That gap is PRD-011's, and PRD-014 depends on PRD-011 in the track graph (T2).

### 6.7 Decision D7 (new): what the PII audit fields mean

`pii_detected_input` and `pii_entities` keep their current meaning: **entities in the new user turn, plus the output**. Entities found while re-redacting history are not recorded again. If they were, one email in turn 1 would mark every later row of the session as a PII event, inflating `pii_detected_queries` in `/stats` and the admin console, and misdescribing sends that contained no new PII. The redaction itself is unaffected: history is still masked. PRD-012 revisits this when it defines per-role PII policy.

### 6.8 Directory structure (files touched)

```
app/
├── config.py                       # + 4 settings, validators
├── models/
│   ├── messages.py                 # NEW: Role, Message, normalize_*, MessageNormalizationError
│   └── schemas.py                  # + QueryBlockedContextLimitResponse in the union
├── routers/query.py                # async def; body → _handle_query via run_in_pipeline
├── db/
│   ├── models.py                   # StoredMessage.history_trimmed; added-columns entry
│   └── database.py                 # chat_messages column convergence; writes the field
└── services/
    ├── openrouter_client.py        # messages + GenerationParams; configurable timeout; null content
    ├── pipeline_executor.py        # NEW: bounded executor, run_in_pipeline
    ├── query_pipeline.py           # run_conversation; run_query adapter; limits; D5/D6/D7
    └── chat_history.py             # NEW: assemble(), fit()
chat_ui/chat_ui/
├── state.py                        # history path; run_in_pipeline; context_limit bubble
├── models.py / copy.py             # context_limit kind, trimmed-footer copy
└── components/bubbles.py           # context_limit bubble; trimmed note in footer
tests/
├── test_messages.py                          # NEW
├── test_openrouter_client.py                 # extended
├── test_query_pipeline_multiturn.py          # NEW
├── test_chat_history.py                      # NEW
├── test_pipeline_concurrency.py              # NEW
├── test_query_outcomes_regression.py         # + row 7
├── test_chat_state.py / test_history_off_integration.py   # extended
└── test_two_instance_smoke.py                # + multi-turn session
```

### 6.9 Patterns followed

- **Settings validated at startup with instructive errors** (`CHAT_SESSION_LIMIT` in `app/config.py`).
- **Additive column convergence** via the added-columns list and `_is_duplicate_column` race tolerance (PRD-008 STORY-003, PRD-009 STORY-002).
- **Required keyword on every audit arm**: the new context-limit arm passes `dedup_key` and `session_id` explicitly (PRD-008 STORY-009, PRD-009 Risk 6).
- **Every refusal is audited**, and every bubble goes through `_append_and_persist` (PRD-008).
- **Injectable `call_openrouter`**: tests swap the callable, never the network.
- **Characterization first**: payload-shape and six-outcome tests go green on untouched code before the story that changes it.

## 7. Tools/Features

### F1 — Message model and normalization
`Message`, `Role`, `normalize_message(s)`, `MessageNormalizationError`. Pure, with no I/O and no settings. Property tests cover every row of the 6.2 table, plus `Message` satisfying `DedupTurn` (a `dedup_key` call on a list of `Message` type-checks and runs).

### F2 — Settings
Four settings with defaults and validators (Section 9.3). A value of `0` or a negative value fails at import, with a message naming the setting and a sane value.

### F3 — OpenRouter client over messages
```python
@dataclass(frozen=True)
class GenerationParams:
    temperature: Optional[float] = None   # 0.0 ≤ t ≤ 2.0
    max_tokens: Optional[int] = None      # ≥ 1
    top_p: Optional[float] = None         # 0.0 < p ≤ 1.0
    stop: Optional[Union[str, list[str]]] = None   # ≤ 4 sequences

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "GenerationParams":
        """Raises UnsupportedParameterError naming every key outside the allowlist."""
```
The payload is `{"model", "messages": [{"role", "content"}…]}` plus only the non-`None` params. The timeout comes from settings, read per call so tests can override it. `choices[0].message.content is None` raises `OpenRouterError("OpenRouter returned no text content (finish_reason=…)")`, and the message says "tool calls are not supported (PRD-016)" when `tool_calls` is present. The router's 502 mapping is unchanged.

### F4 — Dedicated pipeline executor
`pipeline_executor.run_in_pipeline`, with `/query` and `ChatState` both routed through it (6.3). A `shutdown()` hook runs on app lifespan exit (mounted-app lifespan caveat: register it where `init_db()` already works around the `api_transformer` lifespan bypass).

### F5 — `run_conversation` and the `run_query` adapter
The flow in 6.1. `run_query` keeps its exact signature and delegates. The private `_UserTurn` is deleted and replaced by `Message`. The eight audit arms (seven existing plus context limit) all pass `dedup_key` and `session_id`.

### F6 — Context-limit refusal
The response model, pipeline check, audit arm, router passthrough (no new status code: 200 with `BLOCKED`, like the other three blocks), and a chat bubble.

### F7 — History assembly and fitting
`chat_history.assemble` (one read through `chat_sessions.messages_for`, filtered to assistant rows) and `chat_history.fit` (pure). History off or no session → `[]`.

### F8 — ChatState sends history
```python
if session_id and settings.CHAT_HISTORY_ENABLED:
    history = await run_in_pipeline(chat_history.assemble, identity, session_id)
    messages, trimmed = chat_history.fit(history, Message("user", text), …)
    result = await run_in_pipeline(run_conversation, identity=identity, messages=messages, …)
else:
    trimmed = 0
    result = await run_in_pipeline(run_query, identity=identity, prompt=text, …)  # today's path
```
`trimmed` is stored on the assistant bubble as `history_trimmed` and rendered in the footer. The branch on `CHAT_HISTORY_ENABLED` is explicit because it selects the pipeline input, not persistence. `chat_sessions` already no-ops when history is off, so `assemble` would return `[]` anyway, but reading the flag keeps the off path provably identical: same function, same arguments, no extra read.

### F9 — Documentation
README: *Multi-turn context* moves to shipped. *Limitations* loses "No multi-turn context" and gains the D7 audit semantics and the character (not token) limit. New settings go in the configuration table and `.env.example`. The track overview in `pre-prds/README.md` marks PRE-PRD-010 `promoted`.

## 8. Technology Stack

No new dependencies.

| Layer | Technology (installed) | Use in this PRD |
|---|---|---|
| Runtime | Python 3.11 (`Dockerfile`) | `concurrent.futures.ThreadPoolExecutor`, `asyncio.run_in_executor`, `dataclasses`, `typing.Literal` |
| API | FastAPI 0.141.1 / Starlette 1.6.0 / anyio 4.15.0 | `/query` becomes `async def`; the anyio threadpool is no longer held for upstream waits |
| HTTP client | httpx 0.28.1 | Sync `httpx.Client`, unchanged; timeout from settings |
| Chat UI | Reflex 0.9.6.post1 | Background event handler awaits `run_in_pipeline`; new bubble kind and footer note |
| Storage | Turso / libSQL (PRD-007) | One nullable column on `chat_messages` |
| PII | Presidio (PRD-003) | `redact()` applied per message; default `<ENTITY_TYPE>` placeholders |
| Tests | pytest, pytest-asyncio, `fastapi.testclient`, `httpx.AsyncClient` + ASGI transport for concurrency | Existing `temp_db` fixtures |

**Skill constraints (`frontend-design`):** two small UI surfaces change, the `context_limit` bubble and the trimmed-history footer note. Both follow the existing register and bubble system (`chat_ui/chat_ui/theme.py`, `components/bubbles.py`) rather than introducing a new visual direction. The skill's writing rules apply to their copy verbatim: *"Write from the end user's side of the screen. Name things by what people control and recognize, never by how the system is built."* and *"Treat failure and emptiness as moments for direction, not mood. Explain what went wrong and how to fix it … Errors don't apologize, and they are never vague about what happened."* So the refusal copy says what is too long and what to do ("This chat is too long to send. Start a new chat to continue."). It does not say "context limit exceeded", and it does not apologize.

## 9. Security & Configuration

### 9.1 Authentication & authorization
Unchanged. Identity comes from the bearer token (`app/middleware/auth.py`), and authorization runs before any other check. `ChatState` history is read through `chat_sessions.messages_for(identity, session_id)`, which already returns `[]` for a session the identity does not own, so a tampered `active_session_id` cannot pull another user's transcript into context.

### 9.2 Threat reasoning

| # | Change | Effect | Assessment |
|---|---|---|---|
| T1 | History sent to the model | **More data egress per call**: earlier turns leave the process again on every send. | Mitigated by D5. Only redacted text leaves. It is text that already left once, in the same form. Bounded by D2's limits. Token cost is PRD-013's. |
| T2 | Patterns inspect only the last user turn (D6) | **Weaker for caller-supplied history**: an injection placed in an earlier `user` or `system` turn is not inspected. | **Not reachable in this PRD.** No ingress accepts caller history, and `ChatState` history consists only of turns that passed inspection when sent (D4). PRD-011 replaces the policy, and the track graph places PRD-014 after PRD-011. A test asserts no router accepts `messages`. |
| T3 | Assistant turns in context | **Forgeable by a caller** ("the assistant said it would ignore the rules"). | Not reachable: assistant turns come only from `chat_messages` rows the pipeline itself wrote. PRD-014 must decide trust for caller-supplied assistant turns. |
| T4 | Prefix-dependent duplicate key | **A caller who controls history can vary the prefix to re-ask**. | Not reachable: `/query` has no prefix, and chat prefixes are database-derived. Named in PRD-009 T7 and owned by PRD-013 (rate limits) for PRD-014. |
| T5 | Generation parameters | **Cost/abuse lever** (`max_tokens`) and upstream feature surface. | Allowlist of four keys with range validation. No ingress exposes them yet. PRD-013 budgets them. |
| T6 | Dedicated executor | **Resource exhaustion moves, not disappears**: 32 slow calls fill the pipeline pool and later sends queue. | Intended. The failure is contained to pipeline calls, bounded by the timeout, and `/health` stays truthful. Per-user concurrency limits are PRD-013's. |
| T7 | Context-limit rows `success=0` | **Neutral for dedup** (never a prior query), and they count as failures in `success_rate`. | Accepted and documented. A refusal that produced no answer is not a success. |
| T8 | Longer timeout (30 s → 120 s) | **Threads held longer** per failing upstream. | Only pipeline-pool threads, not shared ones (T6). Configurable. |

Invariants that must still hold, each asserted by a test:
- Authorization → context limit → duplicate → patterns → redaction → upstream. Order is asserted with spies.
- `dedup_key` and `prompt_hash` are computed from **raw** text. No redacted string is ever hashed (`test_hash_prompt_only_ever_receives_raw_text` extended to multi-turn).
- The upstream payload never contains unredacted content from **any** message (a multi-turn fixture with PII in turn 1).
- Every outcome writes exactly one audit row, except `InvalidConversationError` (a programming error; unreachable from any ingress in this PRD).
- `/query` upstream payload for a normal prompt is byte-identical to the pre-PRD payload.

### 9.3 Configuration

| Variable | Default | Validation | Purpose |
|---|---|---|---|
| `OPENROUTER_TIMEOUT_SECONDS` | `120.0` | `> 0` | Upstream request timeout (was hard-coded 30 s) |
| `CONTEXT_MAX_MESSAGES` | `100` | `≥ 1` | Max messages per conversation sent to the pipeline |
| `CONTEXT_MAX_CHARACTERS` | `200000` | `≥ 1` | Max total characters across message contents |
| `PIPELINE_MAX_WORKERS` | `32` | `≥ 1` | Size of the dedicated pipeline executor |

`CHAT_HISTORY_ENABLED` (existing) additionally selects single-turn vs. multi-turn chat input (F8). With it off, the chat sends exactly what it sends today.

### 9.4 Out of scope (security)
Per-role inspection of history (PRD-011/012). Token budgets, rate limits and per-user concurrency (PRD-013). Trust model for caller-supplied `system`/`assistant` turns (PRD-014). Tool-call arguments (PRD-015/016). Encrypting `chat_messages.prompt` at rest (unchanged from PRD-008).

## 10. API Specification

**`POST /query`: no request change.** The response union gains one member:

```json
{
  "status": "BLOCKED",
  "reason": "Conversation exceeds context limit",
  "limit": "characters",
  "maximum": 200000,
  "actual": 250113
}
```

| Endpoint | Change |
|---|---|
| `POST /query` | Handler is `async def` (not observable to clients). New 200 `BLOCKED` context-limit body for prompts over `CONTEXT_MAX_CHARACTERS`. Everything else unchanged. |
| `GET /health` | None. It now stays responsive under slow upstream load. |
| `GET /audit`, `GET /stats` | None. Context-limit rows appear as `success=false` rows, as upstream failures already do. |

Internal API (Python):

```python
normalize_message(raw: Mapping[str, Any]) -> Message                      # raises MessageNormalizationError
normalize_messages(raw: Sequence[Mapping[str, Any]]) -> list[Message]
GenerationParams.from_mapping(raw) -> GenerationParams                    # raises UnsupportedParameterError
call_openrouter(messages, model="gpt-4", api_key=None, params=None, client=None) -> OpenRouterResult
async run_in_pipeline(fn, /, *args, **kwargs)
run_conversation(identity, messages, device, model, openrouter_api_key,
                 params=None, call_openrouter=call_openrouter, session_id=None) -> QueryPipelineResult
run_query(identity, prompt, device, model, openrouter_api_key,
          call_openrouter=call_openrouter, session_id=None) -> QueryPipelineResult   # unchanged
chat_history.assemble(identity, session_id) -> list[Message]
chat_history.fit(history, new_turn, max_messages, max_characters) -> tuple[list[Message], int]
```

## 11. Success Criteria

### MVP definition
In the chat UI with history on, a second send "what did I just ask?" is answered with the first question. `/query` passes all six regression outcomes with a byte-identical upstream payload. With ten upstream calls blocked, `GET /health` and a fast `POST /query` both complete within 1 s.

### Functional requirements
- [ ] Chat, history on: the upstream payload for send N contains N−1 prior exchanges (user + assistant) followed by the new user turn, oldest first
- [ ] The first exchange of a new chat appears in the history of send 2 (built from the assistant row's `prompt`, not a missing user row)
- [ ] Duplicate, suspicious, forbidden, upstream-error, internal-error and context-limit turns never appear in later history
- [ ] PII in any prior turn reaches upstream as a placeholder, and the audit row's `pii_entities` lists only the new turn's and the output's entities (D7)
- [ ] Chat, history off: `run_query(prompt=text)` is called with today's arguments, and the upstream payload has one message
- [ ] "yes" sent after two different exchanges in one session is not held as a duplicate
- [ ] "yes" as the second send in two different sessions whose first exchanges differ is not held as a duplicate
- [ ] The same "yes" as the **first** send of two new sessions within 24 h **is** held, which is PRD-009's single-turn rule and unchanged (see Appendix, *Refinement of the brief's criterion*)
- [ ] `fit` drops whole oldest exchanges only; the footer shows the dropped count; a reload shows the same note (persisted)
- [ ] A conversation over `CONTEXT_MAX_MESSAGES` or `CONTEXT_MAX_CHARACTERS` returns the context-limit body with one audit row: `success=0`, non-NULL `dedup_key`, reason in `error_message`
- [ ] `call_openrouter` rejects `logit_bias`, `tools`, `stream` via `UnsupportedParameterError` before any HTTP call; `temperature=3` is rejected
- [ ] `null` content → `OpenRouterError` → 502 on `/query`, `upstream_error` bubble in chat
- [ ] Timeout honours `OPENROUTER_TIMEOUT_SECONDS` (asserted on the constructed client)
- [ ] Normalization: every row of the 6.2 table
- [ ] `run_conversation` raises `InvalidConversationError` for `[]`, a final non-user turn, and any `tool` turn, and writes no row
- [ ] No router accepts a `messages` or `params` field (schema test)

### Seven `/query` outcomes (six from PRD-009 unchanged, plus one)

| # | Outcome | Status | Body `status` / detail | Audit rows |
|---|---|---|---|---|
| 1 | Success | 200 | `SUCCESS` | 1 |
| 2 | Duplicate block | 200 | `BLOCKED`, `"Duplicate query within 24 hours"` | 1 |
| 3 | Suspicious-pattern block | 200 | `BLOCKED`, `"Suspicious pattern detected"` | 1 |
| 4 | Policy refusal | 200 | `BLOCKED`, `required_permission` set | 1 |
| 5 | Upstream failure | 502 | `OpenRouterError` detail | 1 |
| 6 | Internal failure | 500 | error detail | per PRD-009 |
| **7** | **Context limit** | **200** | **`BLOCKED`, `"Conversation exceeds context limit"`** | **1** |

### Concurrency
- [ ] With `PIPELINE_MAX_WORKERS=16` and ten `/query` calls blocked inside a stub upstream (released by an event, not by sleeping), `GET /health` returns in < 1 s and an eleventh `/query` with a non-blocking stub returns `SUCCESS` in < 1 s
- [ ] The same holds with the ten blocked calls issued through `ChatState._do_send`
- [ ] A manual smoke against a local slow HTTP server (60 s delay) reproduces the above; documented in the story report, not in CI

### Quality indicators
- [ ] Full suite green. Per the libSQL dev-server note, mass fixture errors mean restart the container, not bisect code
- [ ] No outcome assertion in `test_query_router.py`, `test_integration.py` or `test_query_outcomes_regression.py` rows 1–6 modified
- [ ] `test_two_instance_smoke.py` passes with a multi-turn session added
- [ ] Every modified pre-existing test carries a comment citing PRD-010 and its decision
- [ ] Added latency per chat send ≤ one `messages_for` read plus per-turn redaction, measured and recorded in the STORY-015 report at 20 exchanges

## 12. Implementation Phases

### Phase 1 — Model, settings, client (Stories 1–5)
**Goal:** the building blocks exist and are tested, with no production caller changed.
**Deliverables:** `Message` and normalization; four settings with validators; payload-shape characterization of today's client, then `call_openrouter(messages, params)` with the allowlist, configurable timeout and `null` content handling. The pipeline passes `[Message("user", redacted_prompt)]`, so the payload stays byte-identical.
**Validation:** full suite green; client characterization test unchanged in its assertions.

### Phase 2 — Pipeline over messages (Stories 6–9)
**Goal:** `run_conversation` is the pipeline; `/query` runs it through the adapter off the shared pools.
**Deliverables:** `pipeline_executor`; `/query` `async def` + `_handle_query`; `run_conversation` + `run_query` adapter; `dedup_key` on `Message`s; `_inspection_target`; per-message redaction with D7 audit semantics; context-limit refusal (response, audit arm, router).
**Validation:** seven-outcome regression green; concurrency test green for `/query`; multi-turn pipeline tests green through direct calls.

### Phase 3 — Chat sends history (Stories 10–13)
**Goal:** a chat session is a conversation.
**Deliverables:** `chat_messages.history_trimmed` convergence; `chat_history.assemble` / `fit`; `ChatState` history path via `run_in_pipeline`; `context_limit` bubble; trimmed-footer note; history-off path pinned identical.
**Validation:** "what did I just ask?" scenario passes with a stub echoing received messages; history-off integration test unchanged.

### Phase 4 — Prove and document (Stories 14–18)
**Goal:** nothing else moved, and readers know what changed.
**Deliverables:** consolidated client, pipeline and concurrency suites; six/seven-outcome and chat UI regression; two-instance smoke with history; README and `.env.example`; pre-PRD marked promoted.
**Validation:** full suite green; README links resolve; manual slow-upstream smoke recorded.

## 13. Future Considerations

- **PRD-011 (pattern policy)**: replaces `_inspection_target` with a per-role policy over every message; closes T2.
- **PRD-012 (PII for code)**: per-role redaction, possibly reversible placeholders so redacted history degrades answers less; revisits D7.
- **PRD-013 (audit & usage limits)**: token budgets for history, per-user concurrency caps on the pipeline executor, `max_tokens` budgets; closes T5/T6.
- **PRD-014 (OpenAI-compatible endpoint)**: first HTTP caller of `normalize_messages` and `GenerationParams.from_mapping`; decides trust for caller-supplied `system`/`assistant` turns (T3); maps the context-limit block to an OpenAI error.
- **PRD-016 (tool calling)**: lifts the `tool`-role and `tool_calls` refusals; `DEDUP_KEY_VERSION` bump per PRD-009.
- **Token-accurate limits**: replace the character proxy with a per-model tokenizer once model metadata is available.
- **Summarizing old turns** instead of dropping them in `fit`: a client-side policy that can slot in without pipeline changes.
- **Deployment system prompt**: a setting that prepends a `system` message; deliberately deferred until PRD-011 inspects system turns.

## 14. Risks & Mitigations

| # | Risk | Likelihood / Impact | Mitigation |
|---|---|---|---|
| 1 | **Largest pipeline refactor since PRD-002** breaks a `/query` outcome. | Medium / High | `run_query` keeps its signature as an adapter; payload characterization and seven-outcome regression land before internals move; no outcome assertion may change. |
| 2 | **Moving `/query` to `async def` puts blocking I/O on the event loop** (e.g. the foreign-session `owns()` check left outside the executor). | Medium / High | The whole handler body lives in sync `_handle_query`, awaited via `run_in_pipeline`; a test patches `owns` and `log_query` to record `threading.current_thread().name` and asserts the `pipeline` prefix. |
| 3 | **Per-turn redaction latency** grows with history (Presidio on every message, every send). | Medium / Medium | Bounded by `CONTEXT_MAX_*`; measured at 20 exchanges (Section 11); assistant turns are already placeholder text and cheap to analyse; a per-content redaction cache is a documented follow-up if the measurement is poor. |
| 4 | **Redacted history makes answers worse** (the model sees `<PERSON>` where the user wrote a name). | High / Low | Intended (D5), documented in the README; reversible placeholders are PRD-012's question. |
| 5 | **Executor lifecycle under Reflex's mounted app**: the `api_transformer` lifespan bypass means a shutdown hook never runs, or the executor is created before settings load. | Low / Medium | Lazy creation on first use, guarded by a lock (`database.py`'s `_client_lock` pattern); shutdown registered where `init_db()` already handles the bypass; worker threads are daemon-equivalent in `ThreadPoolExecutor` at interpreter exit. |
| 6 | **Token cost jumps** with history. | High / Medium | D2 limits now; `CHAT_HISTORY_ENABLED=false` restores single-turn; budgets in PRD-013. |

## 15. Appendix

### Source
- Pre-PRD brief: [pre-prds/PRE-PRD-010-multi-turn-pipeline.md](../../../pre-prds/PRE-PRD-010-multi-turn-pipeline.md)
- Track overview: [pre-prds/README.md](../../../pre-prds/README.md). Depends on PRD-009; blocks PRD-011, 012, 013, 014.

### Decisions (resolved from the brief's open decisions)

| # | Question | Decision |
|---|---|---|
| D1 | Async rewrite, or sync pipeline in a dedicated executor? | **Dedicated bounded executor for the whole pipeline call**, from both ingresses; `/query` becomes `async def`. *Correction to the brief:* an async client inside `call_openrouter` alone frees no shared thread while `run_query` is sync (Section 6.3), so it is not part of this PRD. |
| D2 | Over-long context: refuse or truncate? | **Refuse in the pipeline** with the limit named (Section 6.5). The chat UI, as a client, trims oldest whole exchanges and says so. |
| D3 | How many history turns does the chat UI send? | **All successful exchanges that fit** both limits, oldest dropped first. |
| D4 | Are blocked turns part of history? | **No.** History is built from `assistant` rows only, which also recovers the unsaved first user turn. |
| D5 | Redacted or original text as history? | **Redacted, always**, enforced by redacting every message at the pipeline, not by trusting the source. |
| D6 | *(brief's "provisional role policy")* | **Patterns on the last `user` turn only**, in one named function PRD-011 replaces. PII *redaction* covers every message (D5). |
| D7 | *(new)* What do the PII audit fields mean on a multi-turn send? | **New user turn + output only**, so `/stats` PII figures do not inflate across a session (Section 6.7). |

### Refinement of the brief's criterion
The brief lists: *"'yes' sent twice in one session, and in two sessions, is not held as a duplicate."* Under PRD-009's key, `dedup_key(user_id, turns)` with no session component (PRD-009 D2: "external clients have no session id"), this holds whenever the preceding exchanges differ. It does **not** hold when "yes" is the *first* send of two new sessions within 24 h: both conversations are the single turn `[user("yes")]`, identical to two `/query` calls, and PRD-009 deliberately blocks that. This PRD keeps PRD-009's key unchanged and restates the criterion accordingly (Section 11). Adding `session_id` to the key would be a `DEDUP_KEY_VERSION` change owned by a follow-up, not a side effect here.

### Evidence (verified against `epic/PRD-009-duplicate-rescoping` @ `7156251`)
- `app/services/openrouter_client.py`: `_TIMEOUT_SECONDS = 30.0`; `payload = {"model": model, "messages": [{"role": "user", "content": prompt}]}`; reads `data["choices"][0]["message"]["content"]`.
- `app/services/query_pipeline.py`: `run_query(identity, prompt: str, …)`; private `_UserTurn` feeds `dedup_key`; seven `log_query` arms; `call_openrouter(redacted_prompt, model=…, api_key=…)`.
- `app/routers/query.py`: `def query(...)` (sync), foreign-session `owns()` + `log_query` in the handler before `run_query`.
- `app/main.py`: `def health()` (sync).
- `chat_ui/chat_ui/chat_ui.py`: `api_transformer=fastapi_app`, so one process serves both ingresses.
- `chat_ui/chat_ui/state.py` `_do_send`: `await asyncio.to_thread(run_query, …, prompt=text, …)`; user bubble appended with `session_id == ""` before `chat_sessions.create` on a new chat; assistant bubble `content=result.response` (redacted), `prompt=text` (raw).
- `app/db/models.py`: `chat_messages` has `kind`, `content`, `prompt`, and no history metadata column.
- `app/services/duplicate_checker.py`: `DedupTurn` Protocol; `dedup_key` refuses `tool` and a non-user final turn.
- `app/services/pii_redactor.py`: `AnonymizerEngine().anonymize` with default operators, which produce `<ENTITY_TYPE>`.
- `app/models/schemas.py`: `QueryRequest.prompt: str`, `model: str = "gpt-4"`; four-member `QueryResponse` union.

### Story breakdown (generated by `/create-stories`, see [index.md](./index.md))
1. STORY-001 Message model, role type and content normalization (brief 1–2)
2. STORY-002 Settings: timeout, max messages, max characters, pipeline workers (brief 3)
3. STORY-003 Client payload characterization on untouched code (part of brief 13)
4. STORY-004 OpenRouter client sends `messages`; pipeline passes one user message (brief 4)
5. STORY-005 Parameter allowlist, configurable timeout, `null` content (brief 4, 13)
6. STORY-006 Dedicated pipeline executor; `/query` `async def`; ChatState uses it (brief 5)
7. STORY-007 `run_conversation`; `run_query` adapter; key over `Message`s; provisional policy; D5/D7 redaction (brief 6–9)
8. STORY-008 Context-limit refusal: response, audit arm, router (brief 10)
9. STORY-009 Multi-turn pipeline invariant tests (brief 14)
10. STORY-010 `chat_messages.history_trimmed` convergence (brief 11)
11. STORY-011 `chat_history.assemble` / `fit` (brief 11)
12. STORY-012 ChatState sends history; flag-off path pinned (brief 12)
13. STORY-013 `context_limit` bubble and trimmed-history note (brief 12)
14. STORY-014 Concurrency tests (brief 15)
15. STORY-015 Latency measurement at 20 exchanges (Risk 3)
16. STORY-016 Seven-outcome and chat UI regression (brief 16)
17. STORY-017 Two-instance smoke with history (brief 17)
18. STORY-018 README, `.env.example`, pre-PRD promoted (brief 18)

### Related documents
- PRD-003 (PII redaction): raw-text hashing invariant; `redact()`
- PRD-004 (chat UI redesign): background send, `pending` slot, bubble system
- PRD-005 (RBAC): authorization order, `_deny`
- PRD-007 (Turso migration): `init_db()` convergence, `api_transformer` lifespan bypass
- PRD-008 (chat sessions): `chat_messages`, `_append_and_persist`, first-turn gap, `CHAT_HISTORY_ENABLED`
- PRD-009 (duplicate rescoping): `dedup_key`, lookup exclusions, six-outcome regression

### Dependencies
- Depends on: PRD-009 (done)
- Blocks: PRD-011, PRD-012, PRD-013, PRD-014

**Skills referenced:** frontend-design
