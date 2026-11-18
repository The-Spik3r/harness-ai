---
id: PRD-021
slug: realtime-streaming
title: Real-Time Streaming and Reasoning Visibility, Decided by the Admin — and Honest Progress Feedback When It Is Off
status: in-progress
base_branch: main
epic_branch: epic/PRD-021-realtime-streaming
created: 2026-11-16
updated: 2026-11-18
---

> **Prerequisite.** This PRD builds on **[PRD-020 provider-registry](../PRD-020-provider-registry/PRD.md)** (draft) and consumes what it leaves ready for this PRD: the `ProviderAdapter` protocol with a synchronous `stream()` and a pure `collect()` (PRD-020 D11, Section 6.4), the `call_upstream` seam (D12), per-model capabilities `tools`/`streaming`/`reasoning`/`max_context_tokens` (D6, F4), the missing-usage estimate (D8) and the audit-column path (D13). It does not redesign the registry. It **adds** three things to PRD-020's surface, each stated where it is used: a `ReasoningDelta` event (Section 6.2), a `stream_upstream` seam beside `call_upstream` (Section 6.2), and four audit columns after PRD-020's five (F7).

## 1. Executive Summary

Today `stream: true` on `/v1/chat/completions` is **buffered**. The router commits to SSE once the upstream call starts, sends `: keep-alive` comments until the whole pipeline has finished, then emits the answer as one content chunk, one chunk per released tool call, a finish chunk, an optional usage chunk and `[DONE]` ([app/services/v1_sse.py:46-84](../../../app/services/v1_sse.py), `:125-141`). Upstream, the harness never streams at all: `call_openrouter` posts one JSON request and reads `choices[0].message.content` from one JSON response ([app/services/openrouter_client.py:264-316](../../../app/services/openrouter_client.py)). The chat UI is worse off: `_do_send` awaits `run_conversation` to completion on the pipeline executor and appends one bubble ([chat_ui/chat_ui/state.py:1120-1158](../../../chat_ui/chat_ui/state.py), `:1311`); until then the only feedback is a static, pulsing `SENDING · Waiting on the model` ([chat_ui/chat_ui/components/bubbles.py:495-503](../../../chat_ui/chat_ui/components/bubbles.py), [copy.py:51-52](../../../chat_ui/chat_ui/copy.py)). A reasoning model that thinks for forty seconds looks exactly like a hung request. Reasoning itself is dropped: no file in `app/` or `chat_ui/` reads a `reasoning` field.

This PRD makes real-time delivery a **permission the admin grants**, per role, in two separate parts: `stream:realtime` (see the answer as it is written) and `reasoning:view` (see the model's reasoning). No built-in role holds either, and a master switch, `STREAMING_ENABLED`, defaults off, so an upgrade changes nothing a client receives. For a role that holds `stream:realtime`, text streams token by token while the guarantees that matter stay where they are: every verdict is still decided before the upstream call, **tool calls are still held** until their arguments are complete and the action policy has decided them, output PII redaction still runs (through a hold-back redactor that never releases a half-seen entity), usage is still charged and the audit row still written once the stream ends — and the row now says the response was delivered in real time.

For everyone else in the chat UI, the wait stops being a black box. The pulsing line is replaced by **truthful progress words** derived from real state: the harness stage the request is actually in (checking permissions, checking for a repeat, inspecting the prompt, masking personal data) and the model's phase read from the upstream stream without exposing a byte of its content (thinking, writing the answer). Progress words are chat-UI only: a `/v1` client never receives one in `content`, because a coding agent writes `content` into files.

**MVP goal:** with `STREAMING_ENABLED=true` and `stream:realtime` granted to a role through `RBAC_ROLES_FILE`, an OpenAI SDK stream and the chat UI both show the first content within one upstream token of the provider sending it (measured against the stub upstream); a scripted `DROP TABLE` tool call is still denied with no argument fragment ever sent; an email split across three upstream deltas reaches the chat UI as `<EMAIL_ADDRESS>`; the audit row has `streamed_realtime=1`; and with the switch off, or for a role without the permission, every `/v1` response is byte-identical to today's and the chat UI's final bubble is identical to today's.

## 2. Mission

Let the admin decide who sees the model work in real time, and make every answer path — real time or not — tell the user the truth about what is happening.

Core principles:

- **Granted, never assumed.** Real-time text and reasoning are two permissions checked with `holds()`, which has no `RBAC_ENABLED` bypass ([app/services/authz.py:168-185](../../../app/services/authz.py)). No built-in role holds them; no request field asks for them.
- **Text streams, actions do not.** A tool call is a proposal to act; it reaches the client only whole and decided (PRD-017 principle "Decide before release"). Streaming changes when text arrives, never what an action is allowed to do.
- **Never release what has not been checked.** Every check that runs on the response today still runs, on exactly the text the client receives. Where a check needs context (PII spans), the stream waits for the context, not the other way round.
- **Progress words are facts.** A word is shown only when the stage it names is running or the phase it names has been observed in the upstream stream. Nothing rotates, nothing is random, nothing depends on what a check found.
- **Content is the client's file.** `/v1` `content` carries only model text and the harness's own denial notes, as today. Feedback to a human goes to the human's interface.
- **Off means today.** `STREAMING_ENABLED=false`, or a role without the permission on `/v1`, is today's behaviour byte for byte, verified by running the PRD-015 and PRD-017 stream suites unchanged.

## 3. Target Users

**Security/Compliance Admin.** Owns `RBAC_ROLES_FILE`. Needs to decide, per role, whether text and reasoning may be seen live; needs reasoning, which is more sensitive than the answer, to be a separate grant; needs the audit to say which responses were delivered live and whether reasoning was shown.

**Chat UI user (non-technical).** Writes in Spanish more often than not; today stares at "Waiting on the model" for up to two minutes (`OPENROUTER_TIMEOUT_SECONDS=120`, [app/config.py:240](../../../app/config.py), a provider's `timeout_seconds` under PRD-020). Needs to know the request is alive and roughly where it is, in words that are true. With the permission, wants to read the answer as it is written.

**Integrating Developer (coding agent).** Runs OpenCode, Cline or an OpenAI SDK against `/v1`. With the permission, wants first-token latency instead of a 30-second silence followed by a wall of text, and wants reasoning in the field the client already renders. Never wants a progress word written into a file.

**Platform Operator.** Owns `.env` and the provider registry (PRD-020). Needs one switch to turn upstream streaming on and off, needs a streamed answer to be charged even when the provider reports no usage, and needs the latency and divergence numbers to decide whether to widen the grant.

## 4. MVP Scope

### In Scope

**Permissions and switch**
- [ ] `PERMISSION_STREAM_REALTIME = "stream:realtime"`, `PERMISSION_REASONING_VIEW = "reasoning:view"` in `app/services/authz.py`, added to `_KNOWN_PERMISSIONS` (so `RBAC_ROLES_FILE` can grant them through `load()`'s unknown-permission check, `:113-124`); in no built-in role's set (`:57-74`) (D1)
- [ ] Both checked with `holds()`, never `authorize()` (D1, T8)
- [ ] `STREAMING_ENABLED: bool = False` — off: no upstream stream, permissions inert, today byte for byte (D2)

**Upstream (through PRD-020's adapter)**
- [ ] The pipeline consumes PRD-020's `adapter.stream()` (`TextDelta`, `ToolCallDelta`, `UsageReport`, `Finish`) through a new `stream_upstream` seam (Section 6.2)
- [ ] `ReasoningDelta(text)` added to PRD-020's `UpstreamEvent` union; the OpenAI-compatible adapter maps the provider's reasoning field to it; `collect()` ignores it (Section 6.2)
- [ ] Eligibility per request: the model's `streaming` capability; otherwise this request is delivered buffered and the row says so (D4)
- [ ] Missing usage on a real-time stream is charged by PRD-020's D8 estimate whatever the provider's `usage_missing` mode, including after a mid-stream fault (D4, T6)
- [ ] One total deadline, the provider's `timeout_seconds` (PRD-020's provider field, the adapter's `httpx` timeout), over the whole stream (D20)

**Pipeline (`app/services/query_pipeline.py`)**
- [ ] `run_conversation(..., *, sink: Optional[DeliverySink] = None)` — None (every caller today) emits nothing and takes today's path (D18)
- [ ] Step 2d (new, after step 2c): compute `Visibility(realtime, reasoning)` with `holds()`, `STREAMING_ENABLED` and the model's capabilities (D3, D4)
- [ ] Stage events at steps 2, 2c, 4, 5, 6, 7, 8 — names only, never findings (D11, T10)
- [ ] Step 7 streamed: content deltas through the output gate (D7), reasoning deltas through the reasoning gate (D8), tool-call fragments accumulated and never forwarded (D6), phase events always (D13)
- [ ] Steps 7b, 7c, 8 after the stream ends, in today's order; step 8's output redaction replaced by the stream gate's final pass when real time (D7)
- [ ] Audit: `streamed_realtime`, `reasoning_shown`, `stream_redaction_divergence`, `completion_id` (D14, D17)

**Output gate (`app/services/stream_redaction.py`, new)**
- [ ] Hold-back redactor: release by segment (sentence or line), redacting each with the previous segment as context; bounded hold (D7)
- [ ] Final pass over the whole text; a mismatch with what was released sets `stream_redaction_divergence` and logs a `WARNING` with user and completion id, never content (D7, T12)

**`/v1` (`app/routers/v1.py`, `app/services/v1_sse.py`, `app/services/v1_translate.py`, `app/models/v1_schemas.py`)**
- [ ] Commit rule unchanged (PRD-015 D8): verdicts keep their real status (D5)
- [ ] Real-time chunk sequence (Section 6.6); `ChunkDelta.reasoning_content` (D9)
- [ ] Non-streamed or buffered response with `reasoning:view`: `message.reasoning_content` (D9)
- [ ] Keep-alive comments unchanged; no progress word ever in `content` or in any field a client renders (D10)
- [ ] Error after commit: one `error` event, no `[DONE]` (D16)

**Chat UI (`chat_ui/chat_ui/state.py`, `components/bubbles.py`, `components/chat.py`, `copy.py`)**
- [ ] `ChatState` passes a sink to `run_conversation`; a background consumer applies events in coalesced `async with self` blocks (D19)
- [ ] With `stream:realtime`: a live assistant entry that grows; with `reasoning:view`: a collapsible, visually distinct reasoning block (D12)
- [ ] Without: the pending entry shows the current progress word and elapsed seconds (D11, D12)
- [ ] Persisted once, at the end, exactly as today; a failed stream becomes today's error bubble (D16)

**Stub upstream (`scripts/stub_openrouter.py`)**
- [ ] PRD-020 F6's SSE mode (two content deltas, two-fragment arguments, usage chunk) extended with per-chunk delays, configurable chunk size, scripted reasoning deltas, and a mid-stream failure; logging still never prints content

**Documentation**
- [ ] `docs/features.md` OpenAI-compatible endpoint (`:241`, `:248`) and Tool calling (`:476`, `:489`) sections rewritten for the two delivery modes; `README.md`, `.env.example`, `docs/roadmap.md`

### Out of Scope

- [ ] Any change to buffered delivery for roles without `stream:realtime` — byte-for-byte unchanged on `/v1`; identical final bubble in the chat UI
- [ ] Native provider adapters (PRD-022); this PRD consumes PRD-020's OpenAI-compatible adapter only
- [ ] Real-time delivery on `POST /query` (it is a JSON endpoint; D20 of this PRD keeps it untouched)
- [ ] Tool calling in the chat UI (PRD-017 D17 stands); the chat's "preparing an action" word is therefore defined but unreachable (D11)
- [ ] Streaming tool-call arguments to the client, or releasing calls one by one before the upstream finishes (D6, Section 13)
- [ ] Storing reasoning text in the audit or in `chat_messages` (D8)
- [ ] Pattern inspection of the response or of reasoning (no check inspects the response today; unchanged)
- [ ] Cancelling the upstream call when the client disconnects (D15; Open decision O4)
- [ ] An admin-console page for the new permissions — they are granted through `RBAC_ROLES_FILE`, as the action permissions are (PRD-016 D6)

## 5. User Stories

1. **As a security admin, I want to grant live answers to one role and not another, so that I decide who sees unfinished text.**
   *Example:* `RBAC_ROLES_FILE` gives `engineer` `["query:submit", "audit:read:own", "stream:realtime"]`. An `engineer`'s OpenAI SDK stream receives its first content chunk 0.4 s after the upstream's first token; a `user`'s identical request receives keep-alives and then the whole answer, byte-identical to today.

2. **As a security admin, I want reasoning to be a separate grant, so that a role allowed to see live answers does not automatically see the model's private working.**
   *Example:* `engineer` holds `stream:realtime` only. The upstream sends 3 000 reasoning tokens then the answer: the client receives keep-alives during the reasoning, then content deltas. No `reasoning_content` key appears in any chunk. The row has `streamed_realtime=1`, `reasoning_shown=0`.

3. **As a chat user without the permission, I want to see what the harness is doing, so that a long wait does not look like a hang.**
   *Example:* the entry reads `Inspecting the prompt`, then `Masking personal data`, then `Waiting on the model · 3 s`, then `Thinking · 14 s` while reasoning tokens arrive (none shown), then `Writing the answer · 31 s`, then the finished answer replaces it.

4. **As a chat user with `stream:realtime`, I want to read the answer as it is written, without seeing personal data the harness would have masked.**
   *Example:* the model writes "contact ana.lopez@example.com for access" across three deltas (`ana.lo`, `pez@exam`, `ple.com for access`). The live entry shows "contact" and then, once the sentence ends, `contact <EMAIL_ADDRESS> for access.` — never the partial address.

5. **As an integrating developer, I want text to stream while tool calls stay controlled, so that I get latency without losing the action policy.**
   *Example:* OpenCode streams "I'll drop the table now." live; the model's `bash` call with `sqlite3 app.db "DROP TABLE users"` arrives in nine argument fragments, none of which is forwarded. At stream end the call is denied; the client receives the note `[harness] tool call bash (call_7) was denied: destructive SQL is not permitted: DROP` as a final content delta and `finish_reason: "stop"`.

6. **As an auditor, I want each row to say how its response was delivered, so that "what did the user see, and when" has an answer.**
   *Example:* `GET /audit` returns `streamed: true, streamed_realtime: true, reasoning_shown: true, completion_id: "chatcmpl-harness-rt-5f0c…"`; the client log line with that id leads to the row.

7. **As a platform operator, I want a streamed answer charged even when the provider reports no usage, so that streaming never becomes a way around the token budget.**
   *Example:* a local llama.cpp model (`streaming: true`) streams 2 800 characters and ends without a usage chunk. The row has `streamed_realtime=1`, `usage_estimated=1`, `tokens_used` = PRD-020's D8 estimate over the characters sent and received; the user's `unsplit_tokens` grows by the same amount. The same holds on the legacy OpenRouter provider, whose `usage_missing` is `error`: the text has already been delivered, so the harness charges the estimate rather than raise.

8. **As an integrating developer, I want a failure mid-stream to look like today's failure, so that my client's error handling still works.**
   *Example:* the upstream drops the connection after 40 deltas. The client receives one `data: {"error": {"code": "upstream_unavailable", ...}}` and no `[DONE]`; the OpenAI SDK raises `APIError`; the row is `success=0` and the retry is not held as a duplicate.

## 6. Core Architecture & Patterns

### 6.1 Where streaming sits in the pipeline

```
0.  structural validation
1.  dedup_key, conversation_key                         stage: —
2.  authorize / model / BYOK, 2b break-glass             stage: checking_permissions
2c. usage admission                                      stage: checking_usage   (only when USAGE_LIMITS_ENABLED)
2d. VISIBILITY (new)  caps      = route.model.capabilities   (PRD-020 F4; resolved at step 2 from the same snapshot, D12)
                      realtime  = STREAMING_ENABLED ∧ holds(stream:realtime) ∧ caps.streaming
                      reasoning = STREAMING_ENABLED ∧ holds(reasoning:view)  ∧ caps.reasoning
                      upstream_streamed = STREAMING_ENABLED ∧ caps.streaming
                                          ∧ (realtime ∨ reasoning ∨ ingress == "chat")
3.  context limits
4.  duplicate                                            stage: checking_duplicates
5.  patterns                                             stage: inspecting_prompt
6.  redact input                                         stage: masking_input    (only when PII_REDACTION_ENABLED)
7.  upstream          upstream_streamed ? stream_upstream(...) → adapter.stream() : call_upstream(...) → adapter.complete()
                      for each event:                    phase: waiting → thinking → writing → preparing_action
                        content    → output gate (D7)  → sink.content(text)    if realtime
                        reasoning  → reasoning gate (D8) → sink.reasoning(text) if reasoning ∧ realtime
                        tool frag  → accumulate (never forwarded, D6)
                        usage, finish → kept
7b. charge                                               (after the stream ends; UsageReport, else PRD-020 D8 estimate)
7c. actions                                              stage: evaluating_actions (only when calls exist)
8.  output redaction (buffered) | gate final pass (realtime), audit row, record(), return
```

Every verdict is still decided before step 7, so PRD-015 D8's commit rule holds unchanged: a request committed to SSE ends in a completion or a fault, never in a 4xx (D5). Step 2d sits after 2c because visibility is meaningless for a request about to be refused, and computing it earlier would let a refused caller learn, by timing, whether their role holds a grant (the reason step 2c sits after authorization, `query_pipeline.py:432-438`).

Why `upstream_streamed` is wider than `realtime`: the chat UI's progress phases (D13) need the upstream's event sequence even when no content is forwarded. `/v1` without either permission keeps today's non-streamed upstream call (`ingress == "chat"` is false), so its upstream traffic and its response are both unchanged (D22).

### 6.2 The upstream interface (PRD-020 D11, D12) and what this PRD adds

PRD-020 Section 6.4 defines the adapter this PRD consumes. Used as written:

```python
@dataclass(frozen=True)
class UpstreamRequest:                     # PRD-020
    messages: Sequence[Message]; upstream_model: str
    params: Optional[GenerationParams]; tools: Optional[ToolParams]

class ProviderAdapter(Protocol):           # PRD-020 D11
    def complete(self, request: UpstreamRequest, api_key: Optional[str]) -> UpstreamResult: ...
    def stream(self, request: UpstreamRequest, api_key: Optional[str]) -> Iterator[UpstreamEvent]: ...

UpstreamEvent = TextDelta(text) | ToolCallDelta(index, id?, name?, arguments_fragment)
              | UsageReport(prompt?, completion?, total?) | Finish(reason?)
              | ReasoningDelta(text)       # ADDED by PRD-021 (below)

def collect(events: Iterable[UpstreamEvent]) -> UpstreamResult    # PRD-020: pure, complete()'s rules
```

Capabilities are PRD-020's four, per model (F4): `tools`, `streaming`, `reasoning`, `max_context_tokens`. This PRD reads `streaming` (eligibility, D4) and `reasoning` (whether reasoning can exist); it adds **no capability** (`stream_usage` from the first draft is dropped, D4).

**What PRD-021 adds to PRD-020's surface:**

1. **`ReasoningDelta(text)`** in the `UpstreamEvent` union. The OpenAI-compatible adapter maps the provider's streamed reasoning field (`delta.reasoning` on OpenRouter, `delta.reasoning_content` on DeepSeek-style servers — both **unverified per provider**, STORY-001) to it, only for a model whose `reasoning` capability is true; otherwise the field is dropped. `collect()` ignores `ReasoningDelta`, so PRD-020's property `collect(stream(r)) == complete(r)` is unaffected and reasoning can never leak into `UpstreamResult.response`.
2. **`stream_upstream(messages, model, api_key=None, params=None, client=None, *, tools=None) -> Iterator[UpstreamEvent]`** in `app/services/upstream/__init__.py`, beside PRD-020's `call_upstream` with the identical signature (PRD-020 D12). It resolves the route from the same immutable registry snapshot and calls `adapter.stream()`. `run_conversation` gains `stream_upstream=` as an injectable default, exactly as `call_openrouter=` is today (`query_pipeline.py:315`), so tests replace it with a scripted iterator and the router wraps it for the commit signal (Section 6.3).
3. **Four audit columns** after PRD-020's five (F7).

No fallback is kept. The first draft proposed a `stream_openrouter` function and a `STREAMING_MODELS` setting in case PRD-020 slipped; PRD-020 now specifies, implements and tests `stream()` against the stub (its Phase 3, D11), so a second streaming client would only be code to delete. PRD-021 is **blocked** until PRD-020's `stream()`, `collect()` and capabilities are merged.

**Consuming the stream.** On the pipeline thread, step 7 iterates `stream_upstream(...)`, keeps every event in order, and routes each: `TextDelta` → output gate (D7), `ReasoningDelta` → reasoning gate (D8), `ToolCallDelta` → kept only (never forwarded, D6), `UsageReport`/`Finish` → kept. After the iterator ends, `collect(events)` builds the `UpstreamResult` with complete()'s exact rules — `content: null` beside calls → `""`, arguments joined per `index` and never parsed (PRD-017 D13), duplicate ids refused, the D8 usage rule — so steps 7b, 7c and 8 receive the same type, built by the same rules, as on the buffered path. This PRD writes no fragment assembler of its own.

**Usage on a real-time stream (D4).** Once any content or reasoning has been released, the response is delivered whether or not the provider reports usage, so the request must be charged either way. `collect()` applies PRD-020 D8 with the provider's own `usage_missing` mode; for a real-time request the pipeline calls it with that mode overridden to `estimate` (the exact keyword is fixed in PRD-020's `collect` signature; STORY-003 adds it there if PRD-020 ships without one). Result: a stream that ends without a `UsageReport` is charged PRD-020's character estimate as `unsplit_tokens` and the row has `usage_estimated=1` — on every provider, including the legacy OpenRouter provider whose default mode is `error`. A buffered request keeps the provider's mode, so `error` still means "refuse an unmetered answer" wherever the answer has not left yet.

**Errors.** `stream()` raises PRD-020's `UpstreamError` with today's `retryable` classification (`openrouter_client.py:188-197`) for a transport fault, a non-2xx before the first event, or a fault mid-stream. The OpenAI-compatible adapter sends `stream: true` and `stream_options: {"include_usage": true}` (PRD-020 Section 6.4); whether a given provider honours `include_usage` is exactly the case PRD-020 D8 covers.

### 6.3 The delivery sink (D18)

```python
class DeliverySink(Protocol):           # app/services/delivery.py (new), pure protocol
    def stage(self, name: StageName) -> None: ...
    def phase(self, name: PhaseName, action_kind: Optional[OperationKind] = None) -> None: ...
    def content(self, text: str) -> None: ...        # only ever called when visibility.realtime
    def reasoning(self, text: str) -> None: ...      # only when visibility.reasoning ∧ visibility.realtime
    def committed(self, completion_id: str) -> None: ...  # the upstream stream opened (commit signal)
```

- **The pipeline decides, the sink obeys.** Filtering by permission is done in the pipeline at step 2d, not in the sink: a sink that never receives a content call cannot leak one. A test wraps a recording sink and asserts that, for a role without `stream:realtime`, `content` is never called.
- **Never blocks the pipeline.** Implementations (`QueueSink` for the router and the chat UI) hand each event to the event loop with `loop.call_soon_threadsafe` into an unbounded `asyncio.Queue`. Memory is bounded by the response, which the pipeline accumulates anyway for the audit row; nothing is bounded twice.
- **Survives a vanished consumer.** After the consumer is gone (disconnect, closed tab), puts are dropped; the pipeline runs to completion (PRD-015 Section 7.6's rule, D15).
- **`sink=None` is today.** Every existing caller passes nothing; no event is computed; `run_query` and `/query` are byte-for-byte unchanged (D20).
- **The commit signal moves.** Today `_Upstream.__call__` is the commit signal (`app/routers/v1.py:120-151`). With a sink, `committed()` is called when `adapter.stream()` returns its first event or `adapter.complete()` is entered; the router's `wait_for_commit` (`v1_sse.py:96-108`) waits on it exactly as on `upstream.started` today.

### 6.4 Visibility matrix (D3)

| `stream:realtime` | `reasoning:view` | `/v1` `stream: true` | `/v1` `stream: false` | Chat UI |
|---|---|---|---|---|
| no | no | today's buffered SSE, byte for byte | today | progress words; final bubble as today |
| yes | no | real-time content; reasoning dropped (keep-alives while the model thinks) | today | live answer; no reasoning |
| no | yes | buffered SSE; the role chunk also carries the whole redacted `reasoning_content` | `message.reasoning_content` | progress words; after the answer, a collapsed reasoning block |
| yes | yes | real-time content and `reasoning_content` deltas | `message.reasoning_content` | live reasoning block, then live answer |

`STREAMING_ENABLED=false` collapses every row to the first. A model without `caps.streaming` collapses the realtime column to "no" for that request (D4). A model without `caps.reasoning` never yields reasoning, whatever the grant.

### 6.5 The output gate: hold-back redaction (D7)

Output redaction today is one call over the whole text at step 8 (`query_pipeline.py:850-882`): `chat` always (`pii_policy.py:111-116`, `output=True`), `code` only when `PII_CODE_REDACT_OUTPUT` (default `False`, `pii_policy.py:138`, `config.py:327`). An email split across deltas would defeat a per-delta redactor. The gate:

```
buffer += delta
while a segment boundary exists in buffer:
    segment, buffer = split at the first boundary
    redacted = _redact(context_tail + segment, policy)  → strip the context_tail's redacted prefix
    release(redacted segment)
    context_tail = last ≤ 200 characters of the *raw* released text
if len(buffer) > STREAM_HOLDBACK_MAX_CHARACTERS: release up to the last whitespace in it, through the same path
at Finish: release the remainder through the same path
```

- **Boundary.** `chat`: sentence end (`.`, `?`, `!`, `…` followed by whitespace) or newline. `code` (structure-safe, line-oriented): newline. A fenced block under `code` with `skip_fenced_blocks` is released line by line unredacted, as step 8 would leave it.
- **Context tail.** Presidio raises scores on context words near an entity, and the `chat` NER model needs the sentence around a name. Each segment is analyzed with the raw tail of the previous one prepended; only spans that start inside the new segment are applied. A span that would start in the tail was already decided when the tail was released.
- **Bound.** `STREAM_HOLDBACK_MAX_CHARACTERS` (default 400): a run-on line with no boundary is cut at its last whitespace once it grows past the bound, so the user is never stalled indefinitely. The longest pattern entity in the default lists (an IBAN with spaces, 42 characters; a credit card with separators, 23) is well under it; an entity crossing a forced cut is the residual risk the final pass detects.
- **Final pass.** At `Finish`, the whole raw text is redacted once, exactly as step 8 does today, and compared with the concatenation of released segments. Equal: nothing to do. Different: the row's `stream_redaction_divergence = 1`, a `WARNING` names the user and `completion_id`, and the chat UI's persisted bubble and the audit's entities use the final pass (the authoritative one). What already left cannot be recalled; the column makes it measurable (Risk 1).
- **Cost.** One analyzer call per segment instead of one per response. Under `chat` the NER model's per-call overhead is the cost; STORY-008 measures p95 per segment and total against step 8's single call and records it in `docs/features.md`.
- **Under `code` with output off (the default)** there is no gate: deltas are forwarded as they arrive, coalesced to at most one chunk per 50 ms (D21), and the final pass is not run, as step 8 does not run today.

Mutual exclusion ("real time or output redaction, never both") was considered and rejected: `chat` always redacts output, so it would mean the chat UI could never stream, which is where the feature matters most to a human reader (D7).

### 6.6 What a `/v1` real-time stream sends

After commit (the upstream stream opened; every verdict already decided):

```
data: {"id":"chatcmpl-harness-rt-<uuid>","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}
: keep-alive                                                     (every V1_SSE_KEEPALIVE_SECONDS while nothing is releasable)
data: {... "delta":{"reasoning_content":"The user wants…"} ...}   (reasoning ∧ realtime only, D9)
data: {... "delta":{"content":"I'll drop "} ...}                 (each released segment; D7/D21)
data: {... "delta":{"content":"the table now."} ...}
data: {... "delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"read","arguments":"{…whole…}"}}]} ...}
data: {... "delta":{"content":"\n\n[harness] tool call bash (call_7) was denied: …"} ...}   (one per deny, after the calls)
data: {... "delta":{},"finish_reason":"tool_calls"}
data: {"choices":[],"usage":{...}}                               (include_usage only)
data: [DONE]
```

- The role chunk is sent at commit, so the client's first byte after the headers is real; keep-alives continue to fill gaps (unchanged comment, `v1_sse.py:33`).
- Tool calls and notes follow the last content, in PRD-017 Section 6.6's shapes; the finish chunk is still the last delta (OpenCode errors on a delta after a `finish_reason`, `v1_sse.py:57-58`).
- `finish_reason` follows the release rule (`tool_release`), as today.
- No chunk carries a `harness` object (PRD-015's rule); the id leads to the row (D17).

### 6.7 Chat UI flow (D19)

```
_do_send (background task)
  ├─ sink = QueueSink(loop)
  ├─ task = run_in_pipeline(run_conversation, ..., sink=sink)       # unchanged arguments otherwise
  └─ while not task.done() or queue not empty:
        events = drain(queue, max_wait=100 ms)                      # coalesce
        async with self:                                            # one state delta per batch
            self.progress_stage / progress_phase / progress_since   # always
            self.live_text += content events                        # realtime only
            self.live_reasoning += reasoning events                 # reasoning ∧ realtime only
  result = await task                                               # today's branch chain, unchanged
  bubble built exactly as today (content = result.response)         # the final pass's text
  async with self: clear live_* and progress_*; _append_and_persist(bubble)
```

- Reflex sends a background task's state changes when each `async with self` block exits; batching at 100 ms caps websocket traffic at ten updates a second whatever the token rate. (Behaviour as documented by Reflex for background events; STORY-011 verifies it against the pinned Reflex version with the `reflex-docs` skill, per `chat_ui/AGENTS.md`.)
- The live entry and the pending indicator occupy the slot `render_pending_indicator` occupies today (`components/chat.py:57`), so the transcript does not jump when the final bubble replaces it (the property that function's docstring states).
- The final bubble is built from `result.response` exactly as today (`state.py:1200-1221`), so what is persisted to `chat_messages` and what the transcript restores is the same text the non-streamed path produces (PRD-008 Section 9: the raw upstream text is never written there).

### 6.8 Directory structure (files touched)

```
app/
├── config.py                    # + STREAMING_ENABLED, STREAM_HOLDBACK_MAX_CHARACTERS, STREAM_COALESCE_MS
├── services/
│   ├── authz.py                 # + two permissions, STREAM_PERMISSIONS, _KNOWN_PERMISSIONS
│   ├── delivery.py              # NEW: DeliverySink protocol, StageName/PhaseName, QueueSink, Visibility
│   ├── stream_redaction.py      # NEW: output gate and reasoning gate (pure apart from _redact)
│   ├── stream_assembly.py       # NEW: phase derivation from events (pure); fragments are PRD-020 collect()'s
│   ├── upstream/__init__.py     # + stream_upstream() beside PRD-020's call_upstream (D12 signature)
│   ├── upstream/openai_compatible.py  # + ReasoningDelta mapping in PRD-020's stream()
│   ├── query_pipeline.py        # sink=, step 2d, streamed step 7, stage events, audit fields
│   ├── audit_logger.py          # new fields passed through
│   ├── v1_sse.py                # realtime_events(); completion_events() unchanged
│   └── v1_translate.py          # reasoning_content on result and role chunk
├── models/v1_schemas.py         # ChunkDelta.reasoning_content, AssistantMessage.reasoning_content
├── routers/v1.py                # sink, commit on sink.committed, realtime StreamingResponse
├── db/models.py                 # four columns: AUDIT_LOGS_ADDED_COLUMNS + CREATE_AUDIT_LOGS_TABLE, after PRD-020's five; AuditLog
└── db/database.py               # _SUMMARY_SQL json_object keys (after PRD-020's), _row_to_audit_log
chat_ui/chat_ui/
├── state.py                     # sink, consumer loop, progress_* and live_* vars
├── copy.py                      # PROGRESS_* vocabulary, reasoning block labels
└── components/bubbles.py, chat.py   # render_live_entry, progress line, reasoning block
scripts/stub_openrouter.py       # streamed scripted replies
tests/  test_delivery.py, test_stream_redaction.py, test_stream_assembly.py,
        test_query_pipeline_streaming.py, test_v1_realtime.py, test_chat_progress.py (all NEW)
docs/features.md, README.md, .env.example, docs/roadmap.md
```

### 6.9 Patterns followed

- **Defaulted keyword, passed only when set** — `sink=` joins `params=` and `tools=` (PRD-010 STORY-005, PRD-017 Section 6.9): every injected stub and every existing caller keeps working.
- **Pure modules, I/O at the edges** — `delivery`, `stream_assembly` and the gate's segmenting logic read no settings; the pipeline passes the limits in, read per request (the `_context_limit_exceeded` rule, `query_pipeline.py:125-129`).
- **Required keyword for every row-writing arm** — `streamed_realtime` and `reasoning_shown` join `_deny`'s discipline (`query_pipeline.py:245-305`): a forgotten arm is a `TypeError`, not a row that claims buffered delivery.
- **Grants through the matrix, not settings** — the PRD-016 D6/D7 precedent: permissions in `RBAC_ROLES_FILE`, read with `holds()`.
- **Copy centralized** — every new user-facing string in `copy.py`, the file whose docstring says changing the display language is a single-file edit (`copy.py:1-4`).

## 7. Tools/Features

### F1 — Permissions and switch
Section 4. `STREAM_PERMISSIONS = frozenset({PERMISSION_STREAM_REALTIME, PERMISSION_REASONING_VIEW})`, unioned into `_KNOWN_PERMISSIONS` like `ACTION_PERMISSIONS` (`authz.py:29-49`). A comment beside `ROLE_PERMISSIONS` states why no built-in role holds them, `admin` included: who may read unfinished model output is a deployment decision.

### F2 — Upstream stream
Section 6.2. PRD-020's `stream()` already parses SSE and yields `TextDelta`, `ToolCallDelta`, `UsageReport` and `Finish`; this PRD adds the `ReasoningDelta` mapping and the `stream_upstream` seam. A stream that ends without `Finish` is an `UpstreamError`, non-retryable; one that ends without `UsageReport` is charged by estimate when real time (Section 6.2, D4) and follows the provider's `usage_missing` mode otherwise.

### F3 — Visibility (step 2d)
Section 6.1. A frozen `Visibility(realtime, reasoning, upstream_streamed)` computed once; every later step reads it.

### F4 — Stage and phase events
D11, D13. Stages are emitted at the head of the step that runs, only if it runs; phases are derived by `stream_assembly.phase_of(event)`: first `ReasoningDelta` → `thinking`; first `TextDelta` → `writing`; first `ToolCallDelta` with a name → `preparing_action` with the call's mapped `OperationKind` (`action_classifiers/__init__.py:31`: `shell`, `sql`, `fs_write`, `fs_read`, `http`), or `None` when the name maps to nothing. A phase is emitted on change only.

### F5 — Output and reasoning gates
Section 6.5 and D8.

### F6 — Held tool calls
D6. `ToolCallDelta`s are kept, never forwarded; at the end PRD-020's `collect(events)` joins them per `index` under `complete()`'s rules and returns them in `UpstreamResult.tool_calls`. Step 7c is today's code over that tuple, unchanged.

### F7 — Audit
D14, D17. Four columns on `audit_logs`, on exactly the path PRD-020 D13 uses for its five (`provider`, `upstream_model`, `provider_trust`, `pii_input_relaxed`, `usage_estimated`), and **after** them in every list:

1. `AUDIT_LOGS_ADDED_COLUMNS` entries (`app/db/models.py`; applied by `_add_missing_columns`, `app/db/database.py:730`), so an existing database gains them at startup — the path that added `streamed` (`database.py:703-705`).
2. The same columns declared in `CREATE_AUDIT_LOGS_TABLE` (`app/db/models.py:4`), so a fresh database has them without an `ALTER`.
3. Four keys in `_SUMMARY_SQL`'s `json_object` (`database.py:1330-1381`), after PRD-020's five: `_row_to_audit_log` (`database.py:920`) reads every key and a missing one is a `KeyError` (the rule the comment at `:1330-1332` states). None takes a `?` parameter, so the summary's parameter tuple is unchanged (the rule at `:1326-1329`).
4. `AuditLog` (`app/db/models.py`), `log_query`'s keyword arguments (`audit_logger.py`), the audit query API entry and the admin Register row.

Rows written before this PRD read `0`/NULL and are never backfilled; `0` is true of every one of them (nothing streamed in real time before). If PRD-020's columns are not yet merged when STORY-009 lands, the story is blocked rather than reordering the lists.

| Column | Type | Meaning |
|---|---|---|
| `streamed_realtime` | `INTEGER NOT NULL DEFAULT 0` | content left the harness before the upstream finished |
| `reasoning_shown` | `INTEGER NOT NULL DEFAULT 0` | any reasoning text was delivered (live or whole) |
| `stream_redaction_divergence` | `INTEGER NOT NULL DEFAULT 0` | the gate's released text differed from the final pass |
| `completion_id` | `TEXT NULL` | the realtime stream's id; NULL otherwise (D17) |

`streamed` keeps its meaning (the response was SSE). `GET /audit` and the Register view return the new fields; the Register shows `LIVE` beside a real-time row.

### F8 — `/v1` delivery
Section 6.6. `v1_sse.realtime_events(queue, ...)` is a new async generator; `completion_events()` is untouched, so every buffered path is the same function as today.

### F9 — Chat UI
Sections 6.7 and 7.1 below.

### F10 — Stub upstream
A reply may set `stream: {chunk_chars, delay_ms, reasoning: "…", fail_after: N}`; with it, a request carrying `stream: true` is answered as SSE in that shape, ending with a usage chunk; without it, today's JSON.

### 7.1 Chat UI progress feedback (UI)

The pending entry keeps its slot, tag and rail (`bubbles.py:495-503`); its evidence line changes from a fixed string to the current progress word plus elapsed seconds.

| Event | Word (English, `copy.py`) | Shown when |
|---|---|---|
| stage `checking_permissions` | Checking permissions | step 2 running |
| stage `checking_usage` | Checking your usage | step 2c, only with `USAGE_LIMITS_ENABLED` |
| stage `checking_duplicates` | Checking for a repeat | step 4 |
| stage `inspecting_prompt` | Inspecting the prompt | step 5 |
| stage `masking_input` | Masking personal data | step 6, only with `PII_REDACTION_ENABLED` |
| phase `waiting` | Waiting on the model | step 7 entered, no upstream event yet (today's `PENDING_INDICATOR_TEXT`, kept) |
| phase `thinking` | Thinking | reasoning deltas arriving |
| phase `writing` | Writing the answer | content deltas arriving |
| phase `preparing_action` | Preparing an action: {kind} (`run a command`, `query a database`, `edit a file`, `read a file`, `make a web request`; `use a tool` when unmapped) | a tool call's name has arrived (unreachable in the chat today, D11) |
| stage `evaluating_actions` | Checking the actions | step 7c (unreachable in the chat today) |
| stage `masking_output` | Masking personal data in the answer | buffered step 8, `chat` policy |

Rules (frontend-design: "Write from the end user's side of the screen. Name things by what people control and recognize"; "Use active voice as default"; `copy.py:6-9`'s voice: "states what happened … never describes itself in terms of how it is built"):

- **Words name the control, not the code.** "Masking personal data", never "Running Presidio"; the controls are already the interface's vocabulary (`EMPTY_STATE_PII_FEATURE = "Personal data is masked, never blocked"`, `copy.py:44`).
- **No flicker.** A word replaces the visible one only if its stage is still current 300 ms after it started; sub-300 ms stages (most of steps 2-6) are never shown, which is true — they finished — and calm. The `waiting`, `thinking` and `writing` phases are where seconds pass.
- **Elapsed time is the honest number.** `Thinking · 14 s` from the moment the request was sent; no percentage, no estimated time left (the harness cannot know either).
- **Motion.** The existing `hx-pulse` on the rail and line, nothing new; `theme.GLOBAL_CSS`'s reduced-motion block already stops it (frontend-design: "reduced motion respected"; `components/shell.py:33-35`). The seconds counter ticks once a second, not per token.
- **Accessible.** The word sits in an `aria-live="polite"` region that changes only when the word changes, never on the seconds tick, so a screen reader hears "Thinking", then "Writing the answer", not a count.
- **Live answer.** With `stream:realtime`, the entry's tag stays `SENDING` until the final bubble (tag `CLEARED`) replaces it: the tag vocabulary (`copy.py:56-68`) means "verdict", and a live answer has none yet. Text uses `_prose` (`bubbles.py:61-71`, `white-space: pre-wrap`), so a half-written line wraps like a finished one.
- **Reasoning block.** Collapsible, collapsed by default after the answer arrives, set in the data face (`_evidence`'s `FONT_DATA`, `bubbles.py:74-80`) with the label `Model reasoning — not checked as an answer` so it never reads as the reply (frontend-design: "Let each element do exactly one job"). Never persisted (D8): a restored transcript shows no reasoning, and the block says so on the live bubble (`Not saved with the chat`).

**Language (D11).** `copy.py` is English today (`PENDING_INDICATOR_TEXT = "Waiting on the model"`); the Reports section alone is Spanish by specification (`reports_copy.py:7-11`). The progress vocabulary ships in English in `copy.py`, keyed by event name, so the language switch remains the single-file edit `copy.py:4` promises. Shipping Spanish is Open decision O1.

## 8. Technology Stack

| Layer | Choice | Note |
|---|---|---|
| Upstream wire | OpenAI Chat Completions streaming (SSE `chat.completion.chunk`) | Through PRD-020's OpenAI-compatible adapter; `httpx.Client.stream` on the pipeline thread |
| Upstream provider | OpenRouter | Its streamed reasoning field (`delta.reasoning`) and usage chunk are **unverified** here; STORY-001 records them |
| Client wire | OpenAI streaming plus `reasoning_content` deltas | `reasoning_content` is DeepSeek's field and the one most OpenAI-compatible clients read (unverified per client, STORY-001) |
| Redaction | Presidio via `pii_redactor._redact` paths, unchanged | The gate calls the same `_redact(text, policy)` step 8 calls (`query_pipeline.py:225-242`) |
| Chat UI | Reflex background events, `async with self` batching | Per `chat_ui/AGENTS.md`, Reflex APIs are checked with the `reflex-docs` skill in STORY-011, not from memory |
| Tests | `pytest`; stub upstream streaming; OpenAI Python SDK stream accumulator in-process | E2E for OpenCode and Cline reuse PRD-017's harness, opt-in |

frontend-design applies to the chat UI stories only: "Build to a quality floor without announcing it: responsive down to mobile, visible keyboard focus, reduced motion respected" is the acceptance floor for the progress line, the live entry and the reasoning block's toggle.

## 9. Security & Configuration

### 9.1 Authorization

`/v1` still requires `query:submit`; the chat UI still resolves the token fresh per send (`state.py:965-967`). The two new permissions are read with `holds()` at step 2d. `holds()` reads `ROLE_PERMISSIONS` only and has no `RBAC_ENABLED` escape hatch (`authz.py:168-185`): with RBAC off, roles still hold exactly what the matrix says, which in the built-in matrix is neither permission. Using `authorize()` would grant real time to every caller of an RBAC-off deployment (T8).

### 9.2 Threat reasoning

| # | Threat | Treatment |
|---|---|---|
| T1 | **An action leaks before it is decided** — a partial `arguments` fragment, or a call released before the stream ends, reaches the client | Fragments are never forwarded (D6); no code path forwards a `ToolCallDelta`; step 7c runs after the iterator ends, on `collect()`'s calls; `realtime_events` renders tool calls only from the `Release`. A test scripts a `DROP TABLE` call in nine fragments with content before and after and asserts no fragment substring appears in any chunk before the note |
| T2 | **PII split across deltas** escapes a per-delta redactor | The output gate releases only whole segments redacted with context (D7). Tests split each default entity type at every character offset |
| T3 | **Reasoning echoes what the answer would not** — the client's `system` prompt (not redacted under `code`, `pii_policy.py:131-133`), PII inside fenced blocks (skipped under `code`), every input turn's PII when PRD-020 relaxes step 6 for an `internal` provider (PRD-020 Section 6.6: input not redacted, output still is), an instruction injected through a `tool` result, the model's own unfiltered speculation about the user | A separate grant (D1) held by no role; the reasoning gate redacts under **every** policy, including `code` with output redaction off (D8), with the `chat` entity list when the policy's own list is narrower; never persisted (D8); labelled in the UI as not checked as an answer. Residual, stated in the docs: a granted role can read the system prompt the client itself sent and whatever a tool returned — the grant is the admin's acceptance of that |
| T4 | **Progress words leak content** — a model-chosen tool name or argument shown as a word | Fixed vocabulary only; a tool name is shown only through its mapped `OperationKind` (F4), never the raw name; no phase carries text. A test asserts every progress string the UI can render is a `copy.py` constant or a template over the closed kind set |
| T5 | **Progress words reach a `/v1` file** | `/v1` never receives stage or phase events: the router's sink drops them (it renders keep-alives only). A test asserts that, for every scripted stream, the concatenated `content` deltas equal the redacted model text plus the denial notes, nothing else |
| T6 | **Budget bypass through streaming** — text is delivered and then nothing is charged: the provider sends no usage chunk (under `usage_missing: error` today's rule would raise and charge nothing), the client disconnects, or the stream faults after content left | Every real-time request that released anything is charged: the provider's `UsageReport` if present, else PRD-020's D8 estimate over the characters sent and received, whatever the provider's `usage_missing` mode (D4), marked `usage_estimated=1`. A **mid-stream fault after release** charges the estimate of what was received before the row is written `success=0` — the one arm where today's upstream-error rule ("a call that reported nothing charges nothing", `query_pipeline.py:786-793`) is deliberately not followed, because something was delivered. Disconnect: D15. A fault before any release charges nothing, as today. Residual: the estimate's accuracy (PRD-020 Risk 3), not its existence |
| T7 | **Disconnect to dodge the charge or the audit** | The pipeline keeps reading the upstream to the end and charges and audits (D15), the PRD-015 Section 7.6 rule extended to streaming |
| T8 | **Grant leak through RBAC off** | `holds()`, not `authorize()` (9.1) |
| T9 | **Text left, no row** — the process dies mid-stream after content was released | The row is written at the end, as today, so a crash leaves released text unrecorded. Mitigation: an `INFO` line at commit names the user, model and `completion_id` (never content), so the gap is findable. A write-ahead row is Open decision O3 |
| T10 | **Progress as an oracle** — "Masking personal data" lasting longer reveals the prompt had PII; a stage shown only on a hit reveals the finding | Stage events depend on configuration only (enabled or not), never on findings; the 300 ms rule hides most stage timing. Residual: duration is observable, as total latency already is |
| T11 | **Slow consumer exhausts memory** | The queue holds at most the response the pipeline already accumulates; coalescing (D21) bounds chunk count; `CONTEXT_MAX_CHARACTERS` and the model's `max_tokens` bound the response |
| T12 | **Gate miss** — an entity crossing a forced cut, or found only with whole-text context | Final pass detects it, `stream_redaction_divergence=1`, `WARNING`; the persisted bubble and the audit use the final pass. Released text cannot be recalled: that is the cost of real time the admin grants, measured, and stated in the docs |
| T13 | **A verdict after commit** | Unchanged: every verdict precedes step 7 (D5); `_sse_events`' warning for an impossible post-commit verdict (`v1.py:273-278`) is kept in the realtime renderer |

### 9.3 Configuration

| Variable | Default | Validation | Purpose |
|---|---|---|---|
| `STREAMING_ENABLED` | `false` | bool | Master switch: any upstream streaming, any real-time delivery |
| `STREAM_HOLDBACK_MAX_CHARACTERS` | `400` | `100 ≤ n ≤ 4000` | Forced release bound for the output gate (Section 6.5) |
| `STREAM_COALESCE_MS` | `50` | `0 ≤ n ≤ 500` | Minimum interval between `/v1` content chunks when no gate holds text (D21) |
| `RBAC_ROLES_FILE` | unchanged | now may grant `stream:realtime`, `reasoning:view` | The grant |

`V1_SSE_KEEPALIVE_SECONDS` keeps its meaning. The provider's `timeout_seconds` (PRD-020; `OPENROUTER_TIMEOUT_SECONDS` for the legacy provider) now bounds the whole stream, not each read (D20).

### 9.4 Out of scope (security)
Recalling released text; inspecting reasoning with the pattern lists; storing reasoning for audit (Open decision O2); per-user (rather than per-role) grants.

## 10. API Specification

**`POST /v1/chat/completions`** — request unchanged. `stream: true` from a role holding `stream:realtime` (switch on, eligible model) returns `200 text/event-stream` with Section 6.6's sequence. Headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no` (as today, `v1.py:355`); no `X-Harness-Audit-Id` (the row does not exist yet, as today).

Non-streamed or buffered response for a role holding `reasoning:view`:

```json
{"id": "chatcmpl-harness-412", "object": "chat.completion",
 "choices": [{"index": 0, "finish_reason": "stop", "logprobs": null,
   "message": {"role": "assistant", "content": "The answer.", "reasoning_content": "First, <PERSON> asked…"}}],
 "usage": {...}, "harness": {...}}
```

`reasoning_content` is absent (not `null`) for a role without the grant, so every such body is today's byte for byte (the PRD-017 STORY-011 set-ness rule).

Errors: unchanged table (PRD-015 Section 7.5). Post-commit faults on a real-time stream are one `error` event with the same codes; no `[DONE]`.

**`GET /audit`** — rows gain `streamed_realtime`, `reasoning_shown`, `stream_redaction_divergence`, `completion_id`. Filter `?completion_id=` (exact match), scoped by `audit:read:own` / `audit:read:all` as today.

Internal API:

```python
authz.PERMISSION_STREAM_REALTIME, authz.PERMISSION_REASONING_VIEW, authz.STREAM_PERMISSIONS
delivery.DeliverySink, delivery.QueueSink(loop), delivery.Visibility(realtime, reasoning, upstream_streamed)
stream_redaction.OutputGate(policy, holdback_max).feed(text) -> list[str]; .finish() -> GateResult
stream_redaction.redact_reasoning(text, policy) -> str
stream_assembly.phase_of(event, previous) -> Optional[PhaseName]
upstream.stream_upstream(messages, model, api_key=None, params=None, client=None, *, tools=None) -> Iterator[UpstreamEvent]
upstream.ReasoningDelta(text)                      # added to PRD-020's UpstreamEvent
run_conversation(..., stream_upstream=upstream.stream_upstream)   # injectable, as call_openrouter=
run_conversation(..., *, sink: Optional[DeliverySink] = None)
```

## 11. Success Criteria

### MVP definition
With the switch on and the grant in `RBAC_ROLES_FILE`: first-content latency through the harness within the stub's first-chunk delay plus 100 ms (p95, `code` profile with the output gate off; the `chat` gate's added cost is measured and reported, Quality indicators) on `/v1` and in the chat UI; the PRD-017 `DROP TABLE` criterion holds on a real-time stream with no fragment released; every default PII entity split at every offset is redacted in the released text; the row records real-time delivery. With the switch off or without the grant: the PRD-015 and PRD-017 stream and body suites pass unchanged.

### Functional requirements
- [ ] Switch off: no upstream request carries `stream`; every PRD-015/PRD-017 `/v1` test passes unchanged; the chat UI shows stage words with today's final bubble
- [ ] Switch on, no grant, `/v1`: upstream request byte-identical to today (non-streamed); response byte-identical
- [ ] Switch on, no grant, chat: upstream streamed; progress words follow the scripted phase order; no content or reasoning event reaches `ChatState`
- [ ] `stream:realtime` only: content deltas arrive before the upstream finishes; no `reasoning_content` anywhere; `reasoning_shown=0`
- [ ] `reasoning:view` only: buffered delivery with whole `reasoning_content`; `streamed_realtime=0`, `reasoning_shown=1`
- [ ] Both: reasoning deltas then content deltas; both redacted
- [ ] RBAC off with the built-in matrix: no caller gets real time
- [ ] A model with `streaming: false`: buffered, `streamed_realtime=0`
- [ ] A real-time stream with no usage chunk, on a `usage_missing: error` provider and on an `estimate` one: `success=1`, `usage_estimated=1`, `unsplit_tokens` charged the D8 estimate; the same stream buffered on the `error` provider: today's `UpstreamError`
- [ ] A mid-stream fault after release: estimate charged, `success=0`; before release: nothing charged
- [ ] Tool calls: no fragment substring in any chunk before release; release shapes are PRD-017's; `record()` failure → error event, no call released
- [ ] Output gate: every default entity split at every offset is masked; forced cut at `STREAM_HOLDBACK_MAX_CHARACTERS`; divergence sets the column and logs no content
- [ ] Disconnect mid-stream: row written, usage charged, `success=1`
- [ ] Upstream fault mid-stream: one error event, no `[DONE]`, row `success=0`, retry not a duplicate; chat shows today's `upstream_error` bubble and persists no partial text
- [ ] `/v1` `content` concatenation equals redacted model text plus notes for every scripted stream (T5)
- [ ] `completion_id` on the row equals every chunk's `id`; `GET /audit?completion_id=` returns the row

### Quality indicators
- [ ] Full suite green; no pre-existing assertion changed except where a story names it, citing PRD-021 and the decision
- [ ] Gate cost recorded: p95 per segment and per response under `chat` and `code`, against step 8's single call
- [ ] Chat UI: at most 10 state updates per second during a 200-token/s stream (measured)
- [ ] frontend-design floor on the new UI: visible keyboard focus on the reasoning toggle, reduced motion respected, usable at 360 px width
- [ ] `delivery`, `stream_assembly` and the gate's segmenter read no settings and do no I/O

## 12. Implementation Phases

### Phase 1 — Survey and seams (Stories 1–4)
**Goal:** know what the provider and the clients send, and land the inert pieces.
**Deliverables:** STORY-001 survey (OpenRouter streamed reasoning field and usage chunk per registered model; which of OpenCode 2.0.10, Cline, the OpenAI SDKs display `reasoning_content` vs `reasoning`); permissions and `STREAMING_ENABLED`; `stream_upstream` seam and `ReasoningDelta` on PRD-020's adapter; `collect()`'s real-time usage override; stub SSE mode extended (delays, reasoning, mid-stream fault).
**Validation:** full suite green with the switch off; the survey report pins versions and recorded request/response shapes.

### Phase 2 — Pipeline (Stories 5–9)
**Goal:** the pipeline streams internally and emits events, guarantees intact.
**Deliverables:** `delivery` and step 2d; stage events; `stream_upstream`, `ReasoningDelta`, `stream_assembly` and held tool calls through `collect()`; output and reasoning gates; audit columns and the final pass.
**Validation:** pipeline tests with a recording sink across the visibility matrix; T1, T2, T5 tests.

### Phase 3 — Ingresses (Stories 10–13)
**Goal:** both doors deliver.
**Deliverables:** `/v1` real-time renderer and `reasoning_content`; chat UI consumer, progress line, live entry, reasoning block; `GET /audit` fields and filter; Register `LIVE` marker.
**Validation:** OpenAI SDK accumulator in-process; chat state tests; latency measurement.

### Phase 4 — Clients and docs (Stories 14–16)
**Goal:** real clients work; operators can turn it on.
**Deliverables:** OpenCode and Cline E2E on real-time streams (text, denial, reasoning display as surveyed); `docs/features.md`, README, `.env.example`, roadmap.
**Validation:** E2E reports; docs reviewed against the final behaviour.

## 13. Future Considerations

- **Per-call early release**: release a tool call as soon as the next call's first fragment (or `Finish`) proves its arguments complete, evaluating each on its own (`evaluate_all` already decides each call independently, PRD-016). Saves seconds for multi-call responses.
- **Write-ahead audit row** at commit, updated at the end (O3).
- **Reasoning audit store** with its own retention and read permission (O2).
- **Progress words for `/v1` humans** through a side channel a client opts into (an `X-Harness-Progress` SSE event type clients ignore) — only once a client is shown to ignore unknown event types safely.
- **Streaming on `POST /query`** as an opt-in SSE variant, if a non-chat client appears.
- **Admin-console grant editor** for the permission matrix, covering action and stream permissions together.
- **Native-adapter reasoning formats** (PRD-022): Anthropic thinking blocks, Gemini thoughts, normalized into `ReasoningDelta`.

## 14. Risks & Mitigations

| # | Risk | Likelihood / Impact | Mitigation |
|---|---|---|---|
| 1 | **Gate misses PII the whole-text pass catches** | Medium / High | Context tail, sentence segmentation, final pass with `stream_redaction_divergence`; the rate is reported before widening grants; STORY-008's corpus pins it per entity |
| 2 | **Gate makes `chat` streams stutter** (NER per sentence) | Medium / Medium | Measured in STORY-008; if p95 per segment exceeds 150 ms, segments batch to two sentences; the user still sees a phase word between releases |
| 3 | **Provider fields differ from the survey** (reasoning field name, missing usage chunk) | High / Medium | STORY-001 records per model; PRD-020's `streaming`/`reasoning` capabilities default false in file mode until an operator sets them; a missing usage chunk is charged by estimate (D4); an unknown field is dropped, never forwarded |
| 4 | **A client mishandles `reasoning_content`** (renders it as content, writes it to a file) | Low / High | Survey per client; the grant is per role, so an admin grants it only to roles whose client is verified; docs list verified clients |
| 5 | **Reflex batching behaves differently than assumed** | Medium / Medium | STORY-011 verifies against the pinned version with `reflex-docs`; fallback: a timer-driven poll of a server-side buffer |
| 6 | **PRD-020 slips or changes shape** | Medium / Medium | Hard dependency, no fallback (Section 6.2): Phase 1 starts only once PRD-020's `stream()`, `collect()`, capabilities and audit columns are merged; a shape change there moves only Section 6.2's seam and F7's column order |
| 7 | **Buffered paths regress** while the pipeline grows a second step-7 branch | Low / High | PRD-015/PRD-017 suites run unchanged with the switch off and on-without-grant; `sink=None` takes the literal current branch |

## 15. Appendix

### Decisions

| # | Question | Decision |
|---|---|---|
| D1 | Who decides real time and reasoning | **Two per-role RBAC permissions**, `stream:realtime` and `reasoning:view`, granted only through `RBAC_ROLES_FILE`, held by no built-in role (`admin` included), checked with `holds()` (no RBAC-off bypass). Agreed with the user |
| D2 | Rollout switch | **`STREAMING_ENABLED=false`** by default: with it off nothing streams upstream and the permissions are inert, so a grant written ahead of time cannot take effect by surprise |
| D3 | How the two grants combine | **Independent**: `stream:realtime` governs timing, `reasoning:view` governs whether reasoning is delivered at all; four cells (Section 6.4) |
| D4 | Eligibility and usage | **Eligible when PRD-020's `streaming` capability is true**; no `stream_usage` capability is added. A real-time stream that ends without usage is **charged PRD-020's D8 estimate whatever the provider's `usage_missing` mode** (`usage_estimated=1`), and a mid-stream fault after release charges the estimate too. Falling back to buffered was rejected: it would have to be decided before the first byte, when no one knows whether the usage chunk will come. Honouring `usage_missing: error` was rejected: after release, raising cannot un-deliver the text and would charge nothing. Either way the budget is never bypassable: every request that delivered anything is charged a reported or estimated, never zero, count (T6) |
| D5 | Commit rule | **Unchanged** (PRD-015 D8): every verdict before step 7, real status codes; SSE committed when the upstream stream opens |
| D6 | Tool calls under real time | **Held until the upstream finishes**, fragments never forwarded, `evaluate_all` once, released in one burst after the text, notes as one final content delta. Agreed with the user; per-call early release is Section 13 |
| D7 | Output PII redaction under real time | **Hold-back gate** releasing whole segments (sentence/line) redacted with a context tail, bounded at 400 characters, plus a final whole-text pass that records divergence. Mutual exclusion rejected: `chat` always redacts output, so the chat UI could never stream. Under `code` with output off (default) there is no gate, as today |
| D8 | Reasoning handling | **Redacted under every policy** (the `chat` entity list when the policy's is narrower, because reasoning is not written to files and PRD-012 D1's reason for not redacting `code` output does not apply), **never persisted** to `chat_messages` or `audit_logs`; the row records only `reasoning_shown` |
| D9 | `/v1` reasoning field | **`reasoning_content`** on deltas and on the message (DeepSeek's field, read by most OpenAI-compatible clients — **unverified per client**, STORY-001). Absent, not `null`, without the grant |
| D10 | Progress words on `/v1` | **Never**, in no field a client renders; keep-alive comments stay content-free. Agreed with the user |
| D11 | Progress vocabulary and language | **Closed vocabulary from real stages and observed phases** (Section 7.1), configuration-dependent only; English in `copy.py` keyed by event, matching the chat's current language; the tool phase and `evaluating_actions` are defined but unreachable in the chat (no tools there, PRD-017 D17) |
| D12 | Progress presentation | **One word plus elapsed seconds** in the existing pending slot; 300 ms debounce; `aria-live` on word changes only; existing pulse and reduced-motion rule; reasoning in a collapsible data-face block labelled as unchecked |
| D13 | Reading the upstream without forwarding it | **The chat ingress streams upstream whenever the switch is on and the model can**, to derive phases; `/v1` without a grant keeps today's non-streamed upstream call |
| D14 | Audit | **Row at the end, as today**, with `streamed_realtime`, `reasoning_shown`, `stream_redaction_divergence`; `response` keeps the raw upstream text (today's rule); on a mid-stream fault, the raw text received so far |
| D15 | Client disconnect | **Keep reading to the end**; charge and audit as a success; log the disconnect (user, `completion_id`) |
| D16 | Fault mid-stream | **One `error` event, no `[DONE]`** (`/v1`, as today); row `success=0`; chat UI replaces the live entry with today's `upstream_error` bubble and persists no partial text (history is answered exchanges only, PRD-010) |
| D17 | Completion id before the row exists | **`chatcmpl-harness-rt-<uuid4 hex>`**, stored in `completion_id`; buffered ids stay `chatcmpl-harness-<audit_id>` (`v1_schemas.py:26-33`) |
| D18 | How events leave the pipeline | **A `DeliverySink` keyword**, filtered by visibility inside the pipeline, never blocking it; `None` is today |
| D19 | Chat UI rendering | **Background consumer, 100 ms coalesced `async with self` batches**, final bubble built and persisted exactly as today |
| D20 | Timeout and `/query` | **The provider's `timeout_seconds` bounds the whole stream**; `/query` never passes a sink and never streams |
| D21 | Chunk rate when nothing holds text | **Coalesce to one `/v1` chunk per `STREAM_COALESCE_MS`** (50 ms) |
| D22 | Byte-for-byte guarantee | **`/v1` without the grant: request upstream and response both unchanged**; chat without the grant: final bubble and persisted row unchanged; only the pending line differs |

### Open decisions (proposed default)

| # | Question | Proposed default |
|---|---|---|
| O1 | Ship the progress vocabulary in Spanish? The user writes Spanish; the chat UI's copy is English today | **Decided (user, 2026-11-18): English**, matching the rest of `copy.py`; Spanish stays a one-file swap later; a per-user locale is out of scope |
| O2 | Store reasoning for the auditor? | **No** (D8). A later PRD may add a separate store with retention and its own read permission |
| O3 | Write-ahead audit row at commit (closes T9)? | **No**: it changes every row's lifecycle and the duplicate rule (`success=1` rows only); the commit `INFO` line is the mitigation |
| O4 | Cancel the upstream when the client disconnects (saves tokens)? | **No** (D15): usage would be unknown and T7 opens; revisit with cost data |
| O5 | Also emit OpenRouter-style `reasoning` beside `reasoning_content`? | **Only if STORY-001 finds a target client that reads `reasoning` and not `reasoning_content`**; otherwise one field |
| O6 | Should stage words in the chat require `STREAMING_ENABLED`? | **No**: stage words are internal state and change no upstream traffic, so they ship on by default; only the upstream phases need the switch |
| O7 | Is `chat` with real time worth the gate's cost if divergence is non-zero? | **Ship, measure, report** the divergence rate per entity before an admin widens grants; no automatic disable |

### Orchestrator decisions (story creation, 2026-11-18)

- **OD1 — Legacy mode never streams (user decision).** With no `PROVIDERS_FILE`, PRD-020's implicit `openrouter` models have `streaming=false` and `reasoning=false` (`provider_registry.py`, legacy `Capabilities(tools=…)`), and this PRD leaves that alone (PRD-020 D1, Risk 3). Real time and the chat's upstream phases (`thinking`, `writing`) therefore need a providers-file model with `streaming: true`. Stage words still show in legacy mode. User story 7's "legacy OpenRouter provider whose `usage_missing` is `error`" is tested with a file-mode provider declaring `usage_missing: error`.
- **OD2 — STORY-001 makes live calls (user decision):** a few small streamed requests to OpenRouter with the operator's key, plus the local server PRD-020 STORY-014 used, when reachable.
- **OD3 — PRD-020 is merged** (`be78ab6`); the "draft" mentions of PRD-020 above predate that. `collect()` ships without a `usage_missing` override, so STORY-003 adds it (Section 6.2).
- **OD4 — Story split.** Phase 2's audit story (STORY-009) follows the gates so the pipeline writes all four columns at once; STORY-008 measures the gate cost (Risk 2); Phase 3 is `/v1` (010), chat state (011), chat rendering (012), audit API and Register (013); Phase 4 is OpenCode E2E (014), Cline E2E (015), docs (016).

### Evidence (verified against `main` @ `2253871`)
- `app/services/v1_sse.py:1-17,46-84,125-141`: buffered stream; one content chunk; keep-alives until the pipeline is done.
- `app/routers/v1.py:120-151`: `_Upstream` is the commit signal; `:332-356`: commit rule and `StreamingResponse`; `:343-344`: no audit header on streams.
- `app/services/openrouter_client.py:245-316`: one non-streamed POST; `usage.total_tokens` required (`:310-316`); no `stream` key ever sent; no reasoning field read.
- `app/services/query_pipeline.py:750-784` step 7, `:786-811` 7b, `:813-839` 7c, `:841-882` step 8 output redaction, `:893-918` the success row with `streamed=`.
- `app/services/pii_policy.py:111-116` `chat` `output=True`; `:131-138` `code` roles and `output=PII_CODE_REDACT_OUTPUT`; `app/config.py:327` default `False`.
- `app/services/authz.py:40-49` `_KNOWN_PERMISSIONS`; `:57-74` built-in matrix; `:96-126` `load()`; `:168-185` `holds()` without bypass.
- `app/models/v1_schemas.py:26-33` id derived from `audit_id`; `:210-213` `ChunkDelta` has role, content, tool_calls only.
- `app/services/v1_translate.py:135,462-473` `stream_options` read, `include_usage` honoured only when streamed.
- `chat_ui/chat_ui/state.py:950-1320` `_do_send` awaits the pipeline then appends one bubble; `components/bubbles.py:495-503` and `copy.py:51-52` the static pending line; `copy.py:1-4` English, single-file language switch; `reports_copy.py:7` Spanish for Reports only.
- `scripts/stub_openrouter.py:63-64`: the stub never streams today (PRD-020 F6 adds an SSE mode, which this PRD extends).
- `docs/features.md:241,248,476,489`: "`stream: true` is buffered, not streamed" in both sections.
- No file under `app/` or `chat_ui/chat_ui/` reads a reasoning field (grep `reasoning`: comment prose only).

### Not verified (recorded for STORY-001)
- OpenRouter's streamed reasoning field name (`delta.reasoning` assumed) and whether it is sent without an explicit reasoning request parameter.
- That OpenRouter sends a final usage chunk for every model when `stream_options.include_usage` is set. No longer a safety question (a missing chunk is charged by estimate, D4), only an accuracy one: STORY-001 records how often each registered model's real-time rows are `usage_estimated=1`.
- Which clients display `reasoning_content` (believed: OpenCode via the AI SDK's OpenAI-compatible provider; Cline for DeepSeek-style providers; the OpenAI Python SDK keeps it in `model_extra` but displays nothing).
- Reflex's flush-on-`async with self` exit for background events in the pinned version.

### Related documents
- PRD-005 (RBAC): the matrix and `RBAC_ROLES_FILE`
- PRD-008 (chat sessions): raw upstream text never persisted
- PRD-010 (multi-turn): history is answered exchanges only
- PRD-012 (PII for code): D1 (no `code` output redaction), structure-safe redaction
- PRD-013 (audit and usage): `streamed`, the charge at 7b, `AUDIT_LOGS_ADDED_COLUMNS`
- PRD-015 (endpoint): D6 chunking, D8 commit rule, Section 7.6 disconnect rule
- PRD-016 (action policy): `holds()`, D6 grants through the matrix
- PRD-017 (tool calling): step 7c, release shapes, D13 arguments untouched, D17 no tools in the chat
- PRD-020 (provider registry, draft): D6/F4 capabilities, D8 usage estimate, D11 adapter (`complete`/`stream`/`collect`), D12 `call_upstream` seam, D13 audit-column path, F6 stub SSE mode
- PRD-022 (native adapters, planned): out of scope

### Dependencies
- Depends on: **PRD-020** (draft; hard dependency, no fallback — needs `stream()`, `collect()`, capabilities, D8 estimate and its five audit columns merged first), PRD-015, PRD-016, PRD-017 (done)
- Adds to PRD-020's surface: `ReasoningDelta` in `UpstreamEvent`; `stream_upstream` beside `call_upstream`; a `usage_missing` override on `collect()` if PRD-020 ships without one; four audit columns after its five
- Blocks: none

**Skills referenced:** frontend-design — applies to the chat UI stories (progress line, live entry, reasoning block). Rules cited in Sections 7.1, 8 and 11: "Write from the end user's side of the screen. Name things by what people control and recognize, never by how the system is built"; "Use active voice as default"; "Let each element do exactly one job"; "Build to a quality floor without announcing it: responsive down to mobile, visible keyboard focus, reduced motion respected"; and "sometimes less is more, and extra animation contributes to the feeling that the design is AI-generated", which is why the existing pulse is reused and nothing new moves. No rule from it applies to Sections 6 or 9.
