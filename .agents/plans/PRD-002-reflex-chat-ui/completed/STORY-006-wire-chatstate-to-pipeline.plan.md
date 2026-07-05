---
story: STORY-006
prd: PRD-002
slug: wire-chatstate-to-pipeline
title: "Wire ChatState.send() to the shared query pipeline"
type: feature
complexity: MEDIUM
epic_branch: epic/PRD-002-reflex-chat-ui
created: 2026-07-05
---

# Plan: Wire ChatState.send() to the shared query pipeline

## Summary

Rewrite `ChatState.send()` so it stops being presentation-only (STORY-004/005 left it appending only the user's own message) and instead calls the exact same `run_query(...)` function `POST /query` uses (STORY-001, `app/services/query_pipeline.py`), in-process, with the session's `user_id` (STORY-005) and the typed prompt. Because `run_query(...)` ends in a blocking `httpx` call to OpenRouter (`app/services/openrouter_client.py:call_openrouter`, up to 30s), `send()` becomes a Reflex **background event** (`@rx.event(background=True)`) so a slow OpenRouter response for one user does not freeze the shared event loop for other sessions — state is only mutated inside `async with self:` blocks, matching Reflex's documented pattern for blocking work in background tasks. The three possible outcomes (`QuerySuccessResponse`, `QueryBlockedDuplicateResponse`, `QueryBlockedSuspiciousResponse`) are mapped to three distinct message-bubble renderings: `role="assistant"` for success (existing gray/left bubble), and a new `role="system"` bubble style (centered, amber, no avatar) for both blocked variants, using the exact `reason` string `run_query(...)` returns with no rewording, per the story's technical notes. `call_openrouter` is imported and passed through explicitly (mirroring `app/routers/query.py`'s pattern) so STORY-007's test suite can monkeypatch `chat_ui.state.call_openrouter` the same way `tests/test_query_router.py` monkeypatches `app.routers.query.call_openrouter`.

## User Story

As an integrating developer
I want the chat UI's send action to call the exact same `run_query(...)` function `POST /query` uses, with distinct rendering for success vs. both blocked variants
So that duplicate detection, pattern blocking, and audit logging behave identically regardless of entry point

## Story Reference

- Story file: `.agents/stories/PRD-002-reflex-chat-ui/STORY-006-wire-chatstate-to-pipeline.md`
- PRD: `.agents/PRDs/PRD-002-reflex-chat-ui/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | feature |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/chat_ui/state.py`, `chat_ui/chat_ui/components/chat.py` |
| Story | STORY-006 |
| PRD | PRD-002 |
| Epic Branch | `epic/PRD-002-reflex-chat-ui` (commit directly on this branch) |

---

## Skills In Use

`.agents/skills/` does not exist and the story's `skills:` frontmatter is empty, so no project skill file applies directly. `chat_ui/AGENTS.md` asks for the `reflex-dev/agent-skills` plugin's three skills; `reflex-docs` is installed (confirmed via the Skill tool, which returned its reference index of doc URLs — no local component-level pages beyond that index). Because this story's core risk is a **blocking network call inside a Reflex event handler**, `reflex-docs`'s background-events reference page was fetched directly via WebFetch (`https://reflex.dev/docs/events/background-events`) rather than relying on memory:

> Background events are event handlers decorated with `@rx.event(background=True)` that "may run concurrently with other EventHandler functions," so lengthy operations don't freeze the UI. State changes must occur exclusively within `async with self:` blocks — this "refreshes the state and takes an exclusive lock to prevent other tasks or event handlers from modifying it concurrently." Outside this block, vars "may be stale," and mutating them raises `ImmutableStateError`. Blocking work (the doc's example uses `await asyncio.sleep(...)`) belongs **outside** the `async with self:` block.

This directly shapes Task 1 below: `run_query(...)` (which blocks on `httpx`) is called outside any `async with self:` block; state is only touched (read of `user_id`/`input_text`, and the two message appends) inside `async with self:`.

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `reflex-docs` (background events) | `send()` must not block the shared event loop for the duration of the OpenRouter HTTP call | Task 1 |

---

## Patterns to Follow

### Shared pipeline call site (backend, PRD-001/PRD-002 STORY-001)
```python
// SOURCE: app/routers/query.py:11-28
@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    if not request.user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")

    try:
        return run_query(
            user_id=request.user_id,
            prompt=request.prompt,
            device=request.device,
            model=request.model,
            openrouter_api_key=request.openrouter_api_key,
            call_openrouter=call_openrouter,
        )
    except DuplicateCheckError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except OpenRouterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
```
`send()` mirrors this exact call shape (`run_query(user_id=..., prompt=..., device=..., model=..., openrouter_api_key=..., call_openrouter=call_openrouter)`) and the same two `except` clauses, translated into a chat bubble instead of an `HTTPException`. `device` has no chat-UI equivalent → pass `None` (an accepted value per `QueryRequest.device: Optional[str] = None`). `model`/`openrouter_api_key` have no chat-UI input either → pass the same defaults `QueryRequest` uses (`model="gpt-4"`, `openrouter_api_key=None`, which makes `call_openrouter` fall back to `settings.OPENROUTER_API_KEY`, per `app/services/openrouter_client.py:30`).

### Existing guarded event handler (to preserve, now inside the lock)
```python
// SOURCE: chat_ui/chat_ui/state.py:39-47
@rx.event
def send(self):
    if not self.user_id.strip():
        return
    text = self.input_text.strip()
    if not text:
        return
    self.messages.append({"role": "user", "content": text})
    self.input_text = ""
```
The blank-`user_id`/blank-`input_text` guards and the user-message append are unchanged in intent; they move inside the first `async with self:` block of the new background `send()`.

### Result discrimination (three-way, two share `status="BLOCKED"`)
```python
// SOURCE: app/models/schemas.py:14-31
class QuerySuccessResponse(BaseModel):
    status: Literal["SUCCESS"] = "SUCCESS"
    response: str
    audit_id: int
    model_used: str
    tokens_used: int

class QueryBlockedDuplicateResponse(BaseModel):
    status: Literal["BLOCKED"] = "BLOCKED"
    reason: str
    first_query_at: str

class QueryBlockedSuspiciousResponse(BaseModel):
    status: Literal["BLOCKED"] = "BLOCKED"
    reason: str
    pattern: str
```
`status` alone cannot distinguish the two `BLOCKED` variants (both are `"BLOCKED"`); `send()` discriminates with `isinstance(result, QuerySuccessResponse)` / `isinstance(result, QueryBlockedDuplicateResponse)` / else-suspicious, since `run_query(...)`'s return type is exactly this three-member `Union` (`app/services/query_pipeline.py:13-15`) with no other possible member.

### Reason string source (verified against existing tests — confirms "no rewording")
```python
// SOURCE: tests/test_query_router.py:108-111, 128
"reason": "Duplicate query within 24 hours",
"first_query_at": timestamp,
...
"reason": "Suspicious pattern detected",
```
The bubble content embeds `result.reason` verbatim (plus a `"Blocked — "` label and, for the duplicate case, `first_query_at`, matching PRD Section 4 User Story 2's example bubble text: `"Blocked — duplicate query within 24 hours (first sent at 2026-07-04T10:30:00Z)"`) — it does not paraphrase or replace the reason text itself.

### Existing rx.cond role-branching (to extend to three branches)
```python
// SOURCE: chat_ui/chat_ui/components/chat.py:6-36
def message_bubble(message: dict) -> rx.Component:
    return rx.cond(
        message["role"] == "user",
        rx.hstack(...),  # blue, right-aligned
        rx.hstack(...),  # gray, left-aligned — currently the "everything else" branch
    )
```
The existing two-way `rx.cond` becomes a nested `rx.cond` (`role == "user"` → user bubble; else `role == "system"` → new blocked/error bubble; else → existing assistant bubble), since Reflex conditionals are strictly two-branch.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/state.py` | UPDATE | Rewrite `send()` as a background event calling `run_query(...)`; map its 3 outcomes (+ pipeline exceptions) to chat bubbles |
| `chat_ui/chat_ui/components/chat.py` | UPDATE | Add a third, visually distinct `role == "system"` branch to `message_bubble()` for blocked/error bubbles |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Rewrite `ChatState.send()` to call `run_query(...)` as a background event

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**:
  ```python
  import reflex as rx

  from app.models.schemas import QueryBlockedDuplicateResponse, QuerySuccessResponse
  from app.services.duplicate_checker import DuplicateCheckError
  from app.services.openrouter_client import OpenRouterError, call_openrouter
  from app.services.query_pipeline import run_query

  WELCOME_MESSAGE = {
      "role": "assistant",
      "content": "Hi! Type a message below and press send.",
  }


  class ChatState(rx.State):
      """Holds chat messages, the input box's text, and the session's user_id.

      user_id is collected once per session via submit_user_id() (STORY-005).
      send() is a thin wrapper around the shared run_query(...) pipeline
      (STORY-001, PRD-002 Risk 4): it appends the user's message, calls
      run_query(...) in-process (a background event, since the OpenRouter
      call blocks), then appends the resulting bubble — success,
      duplicate-blocked, or suspicious-blocked — using the exact reason
      text run_query(...) returns.
      """

      messages: list[dict[str, str]] = [WELCOME_MESSAGE]
      input_text: str = ""
      user_id: str = ""
      user_id_input: str = ""

      @rx.event
      def set_input_text(self, text: str):
          self.input_text = text

      @rx.event
      def set_user_id_input(self, text: str):
          self.user_id_input = text

      @rx.event
      def submit_user_id(self):
          text = self.user_id_input.strip()
          if not text:
              return
          self.user_id = text

      @rx.event(background=True)
      async def send(self):
          async with self:
              if not self.user_id.strip():
                  return
              text = self.input_text.strip()
              if not text:
                  return
              self.messages.append({"role": "user", "content": text})
              self.input_text = ""
              user_id = self.user_id

          try:
              result = run_query(
                  user_id=user_id,
                  prompt=text,
                  device=None,
                  model="gpt-4",
                  openrouter_api_key=None,
                  call_openrouter=call_openrouter,
              )
          except (DuplicateCheckError, OpenRouterError) as exc:
              async with self:
                  self.messages.append({"role": "system", "content": f"Error: {exc}"})
              return

          if isinstance(result, QuerySuccessResponse):
              bubble = {"role": "assistant", "content": result.response}
          elif isinstance(result, QueryBlockedDuplicateResponse):
              bubble = {
                  "role": "system",
                  "content": f"Blocked — {result.reason} (first sent at {result.first_query_at})",
              }
          else:
              bubble = {"role": "system", "content": f"Blocked — {result.reason}"}

          async with self:
              self.messages.append(bubble)
  ```
  Notes on choices made here, tied back to the story's technical notes and PRD:
  - `device=None`, `model="gpt-4"`, `openrouter_api_key=None`: no chat-UI input exists for any of these (out of scope per PRD Section 4 — "Model picker ... uses the same default model as `/query` today"); these are exactly `QueryRequest`'s own defaults (`app/models/schemas.py:9-11`), so chat and a bare `curl -X POST /query -d '{"user_id":...,"prompt":...}'` (omitting `device`/`model`/`openrouter_api_key`) run through `run_query(...)` with identical arguments.
  - `call_openrouter=call_openrouter` passed explicitly (rather than relying on `run_query`'s own default): mirrors `app/routers/query.py:23` exactly, and gives STORY-007 a monkeypatch point (`chat_ui.state.call_openrouter`) the same shape as the existing `app.routers.query.call_openrouter` one used throughout `tests/test_query_router.py`.
  - `except (DuplicateCheckError, OpenRouterError)`: `run_query(...)` can raise these (see `app/services/query_pipeline.py:56-66` re-raising `OpenRouterError`, and `check_duplicate` raising `DuplicateCheckError` on a `sqlite3.Error`, `app/services/duplicate_checker.py:30-33`). The route turns these into `HTTPException`s; the chat has no HTTP response to return, so instead it renders a `role="system"` bubble with the error text — this is not new pipeline logic (no duplicate-check/pattern-check/audit-log re-implementation), just surfacing an exception `run_query(...)` already raises, in keeping with PRD Section 2's "Fail loud, not silent" principle (a stuck/silently-dropped message on an OpenRouter outage would otherwise look like a hang with no explanation).
  - `isinstance` discrimination (not `result.status`): both blocked variants share `status="BLOCKED"` (see Patterns above), so `status` alone can't tell them apart; `isinstance` against the concrete Pydantic response classes is unambiguous and needs no new sentinel/enum.
  - Blocking `run_query(...)` call sits **outside** both `async with self:` blocks, per the `reflex-docs` background-events guidance fetched above — the up-to-30s `httpx` call inside `call_openrouter` does not hold the state lock.
- **Mirror**: `app/routers/query.py:11-28` (call shape + exception mapping); `chat_ui/chat_ui/state.py:39-47` (guard logic, now moved inside the lock).
- **Validate**: `python -c "import ast; ast.parse(open('chat_ui/chat_ui/state.py').read())"`

### Task 2: Add a distinct `system`-role bubble style to `message_bubble()`

- **File**: `chat_ui/chat_ui/components/chat.py`
- **Action**: UPDATE
- **Implement**: Nest a second `rx.cond` for `role == "system"` between the existing user branch and the existing (now else-only) assistant branch:
  ```python
  def message_bubble(message: dict) -> rx.Component:
      """A single chat bubble: user (right, blue), system/blocked (centered, amber), assistant (left, gray)."""
      return rx.cond(
          message["role"] == "user",
          rx.hstack(
              rx.box(
                  message["content"],
                  background_color="#2563eb",
                  color="white",
                  padding="0.65rem 1rem",
                  border_radius="1rem",
                  max_width="70%",
              ),
              rx.avatar(fallback="U", size="2", color_scheme="blue"),
              justify="end",
              width="100%",
          ),
          rx.cond(
              message["role"] == "system",
              rx.center(
                  rx.box(
                      message["content"],
                      background_color="#fef3c7",
                      color="#92400e",
                      padding="0.5rem 1rem",
                      border_radius="0.75rem",
                      max_width="80%",
                      font_size="0.875rem",
                  ),
                  width="100%",
              ),
              rx.hstack(
                  rx.avatar(fallback="AI", size="2", color_scheme="gray"),
                  rx.box(
                      message["content"],
                      background_color="#f3f4f6",
                      color="#111827",
                      padding="0.65rem 1rem",
                      border_radius="1rem",
                      max_width="70%",
                  ),
                  justify="start",
                  width="100%",
              ),
          ),
      )
  ```
  No changes needed to `message_list()`, `user_id_prompt()`, or `chat_input()` — `message_bubble()` is already called generically via `rx.foreach(ChatState.messages, message_bubble)`.
- **Mirror**: `chat_ui/chat_ui/components/chat.py:8-36` (existing two-way `rx.cond` shape, extended to three branches).
- **Validate**: `python -c "import ast; ast.parse(open('chat_ui/chat_ui/components/chat.py').read())"`

### Task 3: Manual walkthrough — all three outcomes + audit parity (Reflex dev server)

- **File**: N/A (validation only)
- **Action**: N/A
- **Implement**: Ensure `.env` has a real `OPENROUTER_API_KEY` (required for the success-path check only — `app/config.py:7` makes it mandatory at process start regardless). Run `reflex run` from `chat_ui/`, open the served URL, enter a `user_id`, then:
  1. Send a fresh, non-suspicious prompt (e.g. "what is the weather today") → confirm a left-aligned gray **assistant** bubble renders with the model's response (User Story 1).
  2. Send the exact same prompt again immediately → confirm a centered amber **system** bubble renders reading `Blocked — Duplicate query within 24 hours (first sent at <timestamp>)` (User Story 2's example format), not a second assistant response.
  3. Send a prompt containing `"ignore previous instructions"` (a literal entry in `SUSPICIOUS_PATTERNS`, `app/services/pattern_detector.py:4-12`) → confirm a system bubble reading `Blocked — Suspicious pattern detected`.
  4. Audit parity (User Story 3 / AC 5): with the backend also reachable on the same port, run `curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"user_id":"<same id>","prompt":"<a brand-new prompt>"}'` once, then send that *same* prompt again through the chat UI within 24h → confirm it renders as duplicate-blocked (proves the chat and the REST route share the same SQLite-backed dedup window). Then call `GET /audit` (bearer `ADMIN_TOKEN`) and confirm both the curl-originated and chat-originated rows are present with identical schema/fields (per `AuditQueryEntry`, `app/models/schemas.py:39-47`).
- **Mirror**: STORY-004/STORY-005 plans' manual-walkthrough task style.
- **Validate**: Visual review of the three bubble styles + one `GET /audit` inspection confirming schema parity.

### Task 4: Full backend test suite regression check

- **File**: N/A (validation only)
- **Action**: N/A
- **Implement**: Run the existing `pytest` suite from the repo root. This story touches no backend files (`app/`) at all — only `chat_ui/` — so the suite must pass unmodified, unchanged from before this story.
- **Mirror**: STORY-001/STORY-005 plans' "existing suite passes unmodified" validation step.
- **Validate**: `pytest` exits 0 with no new failures.

---

## End-to-End Tests

- [ ] `reflex run` boots without errors from `chat_ui/`
- [ ] A clean prompt renders a distinct assistant-style bubble with the model's response (User Story 1)
- [ ] An immediate repeat of the same prompt renders a distinct system-style bubble reading `Blocked — Duplicate query within 24 hours (first sent at ...)` (User Story 2)
- [ ] A prompt containing a `SUSPICIOUS_PATTERNS` entry renders a distinct system-style bubble reading `Blocked — Suspicious pattern detected`
- [ ] A prompt sent via `curl -X POST /query` and the same prompt sent via chat within 24h count against the same duplicate window (the chat send is blocked as a duplicate)
- [ ] `GET /audit` shows both the curl-originated and chat-originated rows with identical schema (no chat-specific fields)
- [ ] Full `pytest` suite (repo root) passes unmodified — this story touches no backend/test files

---

## Validation

```bash
cd chat_ui && python -c "import ast; ast.parse(open('chat_ui/state.py').read()); ast.parse(open('chat_ui/components/chat.py').read())"
cd chat_ui && reflex run
cd f:/AI/harness-ai && pytest
```

---

## Risks & Notes

1. **Blocking network call inside a Reflex event handler**: `call_openrouter` is a synchronous `httpx.Client` call with a 30s timeout (`app/services/openrouter_client.py:46-50`). Making `send()` a background event (`@rx.event(background=True)`) with the blocking call outside any `async with self:` block prevents one user's slow/hung OpenRouter request from freezing the shared event loop for other concurrent chat sessions — a concern the PRD itself flags generally in Risk 4 ("a bug or crash in the Reflex chat layer runs in the same process as the core API"). This is additive robustness, not new business logic — `run_query(...)` itself is still the single source of truth for duplicate-check/pattern-check/audit-log/OpenRouter-call.
2. **Error-bubble path (`OpenRouterError`/`DuplicateCheckError`) is not explicitly required by the story's ACs**, which only enumerate SUCCESS/duplicate-blocked/suspicious-blocked. It is included because PRD Section 2 explicitly commits to "Fail loud, not silent" and `run_query(...)` can raise on an OpenRouter outage or a SQLite error — without this, such a failure would background-task-crash silently with no bubble at all, which contradicts that principle. This is a thin `try/except` around the existing call, not a reimplementation of any pipeline decision.
3. **No "sending…" / disabled-input indicator** while a background `send()` is in flight. Not required by any AC, and adding an `is_sending` state var plus disabling the input would be UI polish beyond "a thin wrapper with no logic beyond calling `run_query(...)`" (PRD Section 14 Risk 4). Left as a possible follow-up, not part of this story.
4. **STORY-007 handoff**: `call_openrouter` is now imported and passed explicitly in `chat_ui/chat_ui/state.py`, so STORY-007's test suite can `monkeypatch.setattr("chat_ui.state.call_openrouter", ...)` exactly as `tests/test_query_router.py` does for `app.routers.query.call_openrouter` — no further interface changes anticipated for testability.

---

## Acceptance Criteria

(Copied from story STORY-006)

- [ ] Given `ChatState.send()` is invoked with the session's `user_id` (from STORY-005) and the typed prompt, when it runs, then it calls `run_query(...)` (from STORY-001) directly in-process — a plain Python call, not an HTTP round-trip, per PRD Section 10.
- [ ] Given `run_query(...)` returns a `SUCCESS` result, when `ChatState` updates, then the model's response renders as a distinct assistant-style chat bubble (User Story 1).
- [ ] Given `run_query(...)` returns a duplicate-blocked result, when `ChatState` updates, then a distinct system-style bubble renders showing the same `reason` text `POST /query` already returns, per User Story 2's example.
- [ ] Given `run_query(...)` returns a suspicious-pattern-blocked result, when `ChatState` updates, then a distinct system-style bubble renders showing the same `reason` text `POST /query` already returns for that case.
- [ ] Given a prompt is sent via the chat UI and the identical prompt is sent via `curl -X POST /query`, when both audit rows are compared, then they have the same schema and are subject to the same 24h duplicate window (they count against each other).
- [ ] Given a duplicate prompt sent via the chat UI within 24h and a suspicious-pattern prompt sent via the chat UI, when compared against PRD-001's `/query` behavior for the same inputs, then the blocked reasons match 100%.
- [ ] All tasks completed.
- [ ] Follows existing patterns.
