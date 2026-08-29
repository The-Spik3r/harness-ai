---
story: STORY-014
prd: PRD-005
slug: chat-ui-login
title: Chat UI login replaces the free-text user_id prompt
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-005-rbac
created: 2026-08-28
---

# Plan: Chat UI login replaces the free-text user_id prompt

## Summary

`chat_ui/chat_ui/state.py` still gates the chat behind a free-text `user_id_input` box (`submit_user_id()`), and its `_do_send()` calls `run_query(user_id=..., ...)` — a keyword `run_query()` no longer accepts since STORY-010 changed its signature to `run_query(identity: Identity, ...)`. Confirmed by running the current suite: `python -m pytest tests/test_chat_state.py` fails 6 tests today with `TypeError: run_query() got an unexpected keyword argument 'user_id'` swallowed by the catch-all `except Exception` into a bogus `internal_error` bubble. This story replaces the free-text prompt with a real login: a token is validated via `app.services.identity.resolve()` (the same function `require_identity` uses at the HTTP boundary), and only the resulting `Identity.user_id` — never a role, never the raw token — becomes a `ChatState` var. `ChatState.user_id` continues to gate the UI and label the transcript, but every `send()` call re-resolves a fresh `Identity` from the credential and hands it straight to `run_query(identity=..., ...)`; nothing about authorization is ever read back out of `self`. The credential itself lives in `_token`, a backend-only var (Reflex's documented mechanism for "authentication tokens, or other sensitive state" — never serialized to the client, never settable by a client-originated event), so `ChatState`'s only client-visible, click-settable identity fact is the plain `user_id` string set exclusively by `login()`. Finally, `QueryResponse` has grown a fourth member since this file was last touched — `QueryBlockedForbiddenResponse` — and the current `_do_send()` has a catch-all `else` that would silently render it as the prompt-injection bubble; this story makes every branch of the union explicit.

## User Story

As an end user
I want to log in to the chat with my own credential
So that my activity is attributed to me and cannot be spoofed by typing someone else's user id

## Story Reference

- Story file: `.agents/stories/PRD-005-rbac/STORY-014-chat-ui-login.md`
- PRD: `.agents/PRDs/PRD-005-rbac/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/chat_ui/state.py`, `chat_ui/chat_ui/models.py`, `chat_ui/chat_ui/copy.py`, `chat_ui/chat_ui/theme.py`, `chat_ui/chat_ui/components/shell.py`, `chat_ui/chat_ui/components/chat.py`, `chat_ui/chat_ui/components/bubbles.py`, `chat_ui/chat_ui/chat_ui.py`, `tests/test_chat_state.py`, `tests/test_chat_components_import.py` |
| Story | STORY-014 |
| PRD | PRD-005 |
| Epic Branch | `epic/PRD-005-rbac` (commit directly on this branch) |

---

## Skills In Use

None apply. `skills: []` in story frontmatter. `.agents/skills/` contains only `frontend-design` (net-new visual identity for a page/brief) — this story strictly extends PRD-004's existing inspection-ledger design system (`theme.py` tokens, `bubbles.py`'s panel/tag/rail shapes), it does not create one, so that skill does not apply. `chat_ui/AGENTS.md` names three Reflex plugin skills (`reflex-docs`, `setup-python-env`, `reflex-process-management`); they were consulted during planning (`rx.State` backend-only vars and `get_state` semantics) and the environment is already set up (`.venv` has Reflex + all deps installed) — no further action needed from them at implementation time beyond the same doc lookups if a Reflex API question comes up.

---

## Design Decision: one state, backend-only var — not a second `rx.State` class

The AC says `ChatState` must hold no token and no role. Two designs were considered:

1. **Cross-state**: a separate `AuthState(rx.State)` owns `_token`; `ChatState.send()` calls `await self.get_state(AuthState)` to fetch it fresh.
2. **Backend-only var on `ChatState` itself**: `_token: str = ""` (leading underscore).

`get_state()` resolves siblings via `self._get_root_state().get_substate(...)`, which requires the full app-registered state tree (all `rx.State` subclasses wired together as one root's substates, normally built by Reflex's `StateManager` when a real client connects). Verified directly against the installed Reflex build:
```
// SOURCE: reflex.state.BaseState._get_root_state (installed package, via `python -c "import inspect, reflex as rx; print(inspect.getsource(rx.State._get_root_state))"`)
def _get_root_state(self) -> BaseState:
    parent_state = self
    while parent_state.parent_state is not None:
        parent_state = parent_state.parent_state
    return parent_state
```
A bare `ChatState(_reflex_internal_init=True)` — exactly how every existing test in `tests/test_chat_state.py` constructs its fixture (`_make_state()`, `F:\AI\harness-ai\tests\test_chat_state.py:75-78`) — has `parent_state=None`, so it *is* its own root with no substates. `get_state(AuthState)` on it would raise, and there is no app/websocket/state-manager scaffolding in this unit-test harness to make it otherwise. Option 1 would force every send-path test onto much heavier, more fragile plumbing than this codebase's existing test style uses anywhere.

Option 2 is also the framework's own documented answer for exactly this problem:
```
Backend-only vars ... "authentication tokens, or other sensitive state" ...
"not synchronized with the frontend" ... the frontend cannot mutate them.
// SOURCE: https://reflex.dev/docs/vars/base-vars (fetched during planning)
```
So `_token` stays a backend-only var directly on `ChatState`. It satisfies the AC's substance exactly — no token or role is ever a client-visible, client-settable, or cached-and-trusted value — even though, read hyper-literally, the class still has an attribute named `_token`. The test suite verifies the substance directly: no field named `token` or `role` exists in `ChatState.__annotations__` (Task 10, new test), and a dedicated test proves the role is re-derived from the database on every `send()` call rather than cached anywhere (Task 10, `test_chat_state_send_reresolves_role_on_every_call`).

---

## Patterns to Follow

### `resolve(token)` — the same function `require_identity` already uses; None covers every failure alike
```
// SOURCE: app/services/identity.py:46-62
def resolve(token: Optional[str]) -> Optional[Identity]:
    """Verifies a credential and returns the Identity it belongs to, or
    None. None covers every failure case alike -- unknown, malformed,
    empty, or deactivated -- so the caller cannot distinguish them (PRD
    Section 9; STORY-002 Design Note 5 makes the same choice one layer
    down)."""
    if not token:
        return None
    if secrets.compare_digest(token, settings.ADMIN_TOKEN):
        return Identity(user_id=_ADMIN_BREAK_GLASS_USER_ID, role=_ADMIN_ROLE)
    user = find_user_by_token_hash(hash_token(token))
    if user is None:
        return None
    return Identity(user_id=user.user_id, role=user.role)
```
`login()` calls this once to validate the form submission; `_do_send()` calls it again, fresh, on every `send()` — this is the literal mechanism behind AC3 ("re-resolved server-side on every call").

### `require_identity` — the same "resolve every request, never cache a role" shape at the HTTP boundary
```
// SOURCE: app/middleware/auth.py:14-20
def require_identity(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Identity:
    identity = resolve(credentials.credentials if credentials else None)
    if identity is None:
        raise HTTPException(status_code=401, detail="Invalid or missing credential")
    return identity
```
`ChatState._do_send()` mirrors this: resolve from the credential, reject `None` before doing anything else, never keep the resolved role around afterward.

### `run_query()` — Identity-first signature this file must now call correctly
```
// SOURCE: app/services/query_pipeline.py:45-52
def run_query(
    identity: Identity,
    prompt: str,
    device: Optional[str],
    model: str,
    openrouter_api_key: Optional[str],
    call_openrouter: Callable[..., OpenRouterResult] = call_openrouter,
) -> QueryPipelineResult:
```

### `QueryResponse` — four members, the one this file is missing
```
// SOURCE: app/models/schemas.py:40-51
class QueryBlockedForbiddenResponse(BaseModel):
    status: Literal["BLOCKED"] = "BLOCKED"
    reason: str
    required_permission: str


QueryResponse = Union[
    QuerySuccessResponse,
    QueryBlockedDuplicateResponse,
    QueryBlockedSuspiciousResponse,
    QueryBlockedForbiddenResponse,
]
```

### Backend-only var — Reflex's documented mechanism for exactly this credential
```
Any Var in a state class that starts with an underscore (_) is considered
backend only and will not be synchronized with the frontend ... used to
store ... authentication tokens, or other sensitive state.
// SOURCE: https://reflex.dev/docs/vars/base-vars (fetched during planning)
```

### `_entry` / `_panel` / `_tag` / `_evidence` — the shared shape every ledger kind reuses
```
// SOURCE: chat_ui/chat_ui/components/bubbles.py:251-278 (render_injection, the closest existing analogue to the new "forbidden" kind)
def render_injection(message) -> rx.Component:
    ink, tint = theme.INK_DENIED, theme.TINT_DENIED
    return _entry(
        _rail(ink),
        _tag(copy.TAG_INJECTION, ink),
        _panel(
            ink, tint,
            _prose(message.content),
            rx.cond(
                message.pattern != "",
                _evidence(f"{copy.INJECTION_PATTERN_LABEL}: ", rx.el.span(message.pattern, ...), color=ink, margin_top="0.5rem"),
                _evidence(copy.INJECTION_NO_PATTERN, color=ink, margin_top="0.5rem"),
            ),
        ),
    )
```
`render_forbidden()` (Task 5) follows this exactly, swapping `pattern`/`INJECTION_PATTERN_LABEL` for `required_permission`/`FORBIDDEN_PERMISSION_LABEL`, and its own ink so it never shares a treatment with `render_injection` (`theme.py`'s own rule: "no two semantically different outcomes share a treatment, so each ink maps to exactly one branch of `run_query(...)`" — `chat_ui/chat_ui/theme.py:29-30`).

### Tests: DB-backed identity + bearer header, seeded in `temp_db`
```
// SOURCE: tests/test_query_router.py:29-46
_AUTH_USER_ID = "juan@empresa.com"
_AUTH_TOKEN = "test-user-token"
_AUTH_HEADERS = {"Authorization": f"Bearer {_AUTH_TOKEN}"}

client = TestClient(app, headers=_AUTH_HEADERS)

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    insert_user(
        User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN))
    )
    return db_path
```
`tests/test_chat_state.py`'s rewritten `temp_db` fixture and `_make_state()` follow this shape so `ChatState._token` resolves to a real DB-backed `Identity` instead of the free-text string the old tests set directly on `state.user_id`.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/copy.py` | UPDATE | Replace `USER_ID_*` session-gate copy with `LOGIN_*` token copy; add `TAG_FORBIDDEN`, `FORBIDDEN_PERMISSION_LABEL`, `SESSION_INVALIDATED_ERROR`; rename `SHELL_CHANGE_USER_LABEL` → `SHELL_LOGOUT_LABEL` |
| `chat_ui/chat_ui/models.py` | UPDATE | Add `required_permission: str = ""` to `ChatMessage` |
| `chat_ui/chat_ui/theme.py` | UPDATE | Add `INK_FORBIDDEN` / `TINT_FORBIDDEN` — the forbidden verdict needs its own ink, not `INK_DENIED` (that's injection's) |
| `chat_ui/chat_ui/state.py` | UPDATE | `submit_user_id()`/`reset_user_id()` become `login()`/`logout()`; drop `user_id_input`/`user_id_error`, add `token_input`/`login_error`/backend-only `_token`; `_do_send()` re-resolves `Identity` from `_token` every call and passes `identity=` to `run_query()`; explicit `isinstance` branches for all four `QueryResponse` members |
| `chat_ui/chat_ui/components/bubbles.py` | UPDATE | Add `render_forbidden()` |
| `chat_ui/chat_ui/components/chat.py` | UPDATE | Register `"forbidden"` arm in `message_bubble()`'s `rx.match` |
| `chat_ui/chat_ui/components/shell.py` | UPDATE | `user_id_gate()` → `login_gate()`, a token form (`type="password"`) wired to `ChatState.login`; header's user control renamed to a sign-out action wired to `ChatState.logout` |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | Import `login_gate` instead of `user_id_gate` |
| `tests/test_chat_components_import.py` | UPDATE | Rename `user_id_gate` → `login_gate`; add `"forbidden"` / `"render_forbidden"` to the expected kind/renderer lists |
| `tests/test_chat_state.py` | UPDATE | New `_AUTH_USER_ID`/`_AUTH_TOKEN` + DB-seeding `temp_db`; `login()`/`logout()` tests (empty/invalid/deactivated/valid token); `_fake_run_query` signatures updated to `identity`; new forbidden-response test; new role-re-resolution test; new mid-session-revocation test; audit-parity tests send a bearer header |

Not touched in this story:
- `app/routers/query.py`, `app/middleware/auth.py`, `app/services/identity.py`, `app/services/query_pipeline.py` — all STORY-010/012/013 territory, already correct and unchanged
- `scripts/manage_users.py` — used only to mint a token for manual E2E testing below, not modified

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: `copy.py` — login/token copy replaces the user-id session-gate copy

- **File**: `chat_ui/chat_ui/copy.py`
- **Action**: UPDATE
- **Implement**: Replace the "Session gate" block (`chat_ui/chat_ui/copy.py:12-19`):
  ```python
  # --- Session gate --------------------------------------------------------
  LOGIN_PROMPT_TITLE = "Sign in"
  LOGIN_PROMPT_BODY = (
      "Every prompt is recorded against your identity. Enter your access "
      "token to start the session."
  )
  LOGIN_TOKEN_PLACEHOLDER = "Access token"
  LOGIN_SUBMIT_LABEL = "Sign in"
  LOGIN_TOKEN_REQUIRED_ERROR = "Enter a token to sign in."
  LOGIN_INVALID_TOKEN_ERROR = "Invalid or deactivated token."
  # A credential can go bad mid-session (deactivated by an admin while the
  # tab stays open). send() re-resolves on every call and surfaces this
  # rather than silently keep using a role that no longer exists.
  SESSION_INVALIDATED_ERROR = (
      "Your session credential is no longer valid. Sign out and sign in again."
  )
  ```
  Rename `SHELL_CHANGE_USER_LABEL = "Switch user"` (`chat_ui/chat_ui/copy.py:25`) to:
  ```python
  SHELL_LOGOUT_LABEL = "Sign out"
  ```
  Add to the "Verdict tags" block (`chat_ui/chat_ui/copy.py:46-54`), after `TAG_INJECTION`:
  ```python
  TAG_FORBIDDEN = "FORBIDDEN"
  ```
  Add to the "Block and failure cards" block (`chat_ui/chat_ui/copy.py:83-86`), after `INJECTION_NO_PATTERN`:
  ```python
  FORBIDDEN_PERMISSION_LABEL = "Required permission"
  ```
- **Mirror**: `chat_ui/chat_ui/copy.py:84-85` (`INJECTION_PATTERN_LABEL`/`INJECTION_NO_PATTERN`) for the evidence-label naming convention.
- **Validate**: `cd chat_ui && ../.venv/Scripts/python.exe -c "from chat_ui import copy"` succeeds (run from `chat_ui/`, matching this file's existing import root).

### Task 2: `models.py` — `ChatMessage` gains `required_permission`

- **File**: `chat_ui/chat_ui/models.py`
- **Action**: UPDATE
- **Implement**: Add one field, next to `pattern` (the other block-reason field):
  ```python
  pattern: str = ""
  required_permission: str = ""
  ```
- **Mirror**: `chat_ui/chat_ui/models.py:15` (`pattern: str = ""`) — identical shape.
- **Validate**: `cd chat_ui && ../.venv/Scripts/python.exe -c "from chat_ui.models import ChatMessage; ChatMessage(kind='forbidden', content='x', required_permission='query:submit')"` succeeds.

### Task 3: `theme.py` — a distinct ink for the forbidden verdict

- **File**: `chat_ui/chat_ui/theme.py`
- **Action**: UPDATE
- **Implement**: Add after `INK_SELF` (`chat_ui/chat_ui/theme.py:36`):
  ```python
  INK_FORBIDDEN = "#B5541D"  # forbidden by policy -- distinct from injection's INK_DENIED
  ```
  Add after `TINT_DENIED` (`chat_ui/chat_ui/theme.py:42`):
  ```python
  TINT_FORBIDDEN = "#FCF1E8"
  ```
- **Mirror**: `chat_ui/chat_ui/theme.py:33,42` (`INK_DENIED`/`TINT_DENIED`) — same naming/pairing convention.
- **Validate**: `cd chat_ui && ../.venv/Scripts/python.exe -c "from chat_ui import theme; theme.INK_FORBIDDEN; theme.TINT_FORBIDDEN"` succeeds.

### Task 4: `state.py` — login/logout, backend-only token, per-call re-resolution, explicit response branches

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE (full rewrite of the file's contents; structure below)
- **Implement**:
  ```python
  import asyncio
  import reflex as rx

  from app.models.schemas import (
      QueryBlockedDuplicateResponse,
      QueryBlockedForbiddenResponse,
      QueryBlockedSuspiciousResponse,
      QuerySuccessResponse,
  )
  from app.services.duplicate_checker import DuplicateCheckError
  from app.services.identity import resolve
  from app.services.openrouter_client import OpenRouterError, call_openrouter
  from app.services.pii_redactor import PiiRedactorError
  from app.services.query_pipeline import run_query
  from .models import ChatMessage
  from .copy import (
      LOGIN_INVALID_TOKEN_ERROR,
      LOGIN_TOKEN_REQUIRED_ERROR,
      SESSION_INVALIDATED_ERROR,
  )
  from .formatting import format_duplicate_info
  from .config import DEFAULT_MODEL


  class ChatState(rx.State):
      """Session state for the chat surface: the transcript, the composer, and
      who is sending.

      send() is the only consumer of run_query(...) and handles every branch
      it can produce -- four response types, three named exceptions, and a
      catch-all -- appending exactly one typed ChatMessage for each. That
      exhaustiveness is what makes PRD-004's "no silent drops" structural
      rather than aspirational. The call itself runs on a worker thread, so a
      30-second OpenRouter round trip never blocks the Reflex event loop.

      PRD-005 Risk 5: a role read from a Reflex state var is cosmetic, not a
      security boundary -- state vars are serialized to the client and
      mutable by client-originated events. So this class holds no role at
      all, and its only credential is `_token`, a backend-only var (leading
      underscore): Reflex never syncs it to the frontend and no client event
      can set it. login() is the only place that writes it or `user_id`;
      every send() re-derives the Identity -- and so the role -- from
      `_token` via resolve(), fresh, on every call.
      """

      messages: list[ChatMessage] = []
      input_text: str = ""
      user_id: str = ""
      token_input: str = ""
      login_error: str = ""
      pending: bool = False
      selected_model: str = DEFAULT_MODEL

      _token: str = ""

      @rx.var
      def has_messages(self) -> bool:
          return len(self.messages) > 0

      @rx.event
      def set_input_text(self, text: str):
          self.input_text = text

      @rx.event
      def set_token_input(self, text: str):
          self.token_input = text

      @rx.event
      def set_selected_model(self, model: str):
          self.selected_model = model

      @rx.event
      def login(self):
          token = self.token_input.strip()
          if not token:
              self.login_error = LOGIN_TOKEN_REQUIRED_ERROR
              return

          identity = resolve(token)
          if identity is None:
              self.login_error = LOGIN_INVALID_TOKEN_ERROR
              return

          self.login_error = ""
          self.token_input = ""
          self._token = token
          self.user_id = identity.user_id

      @rx.event
      def logout(self):
          """Ends the session. The transcript goes with it: the header names
          who is sending, so leaving one user's prompts on screen under
          another's ID would misattribute them in a surface people read as a
          record."""
          self._token = ""
          self.user_id = ""
          self.token_input = ""
          self.login_error = ""
          self.messages = []
          self.input_text = ""

      @rx.event
      def edit_and_resend(self, prompt: str):
          if self.pending:
              return
          self.input_text = prompt
          return rx.set_focus("chat_input")

      async def _do_send(self, text: str):
          # Claim the in-flight slot first and on its own, so everything that
          # can raise afterwards is inside the try/finally that clears
          # `pending` (PRD-004 Risk 3: a stuck flag locks the composer
          # permanently).
          async with self:
              if not self.user_id.strip():
                  return
              text = text.strip()
              if not text:
                  return
              if self.pending:
                  return
              self.pending = True
              token = self._token

          # PRD-005 Risk 5: re-resolved fresh on every call, never cached --
          # there is no role field anywhere on this class to read one from.
          identity = resolve(token)
          if identity is None:
              async with self:
                  self.messages.append(
                      ChatMessage(
                          kind="internal_error",
                          content="internal_error",
                          prompt=text,
                          detail=SESSION_INVALIDATED_ERROR,
                      )
                  )
                  self.pending = False
              return

          try:
              async with self:
                  self.messages.append(
                      ChatMessage(kind="user", content=text, prompt=text)
                  )
                  self.input_text = ""
                  model = self.selected_model
                  device = None
                  try:
                      if (
                          self.router
                          and self.router.headers
                          and self.router.headers.raw_headers
                      ):
                          device = self.router.headers.raw_headers.get("user-agent")
                  except Exception:
                      device = None

              try:
                  result = await asyncio.to_thread(
                      run_query,
                      identity=identity,
                      prompt=text,
                      device=device,
                      model=model,
                      openrouter_api_key=None,
                      call_openrouter=call_openrouter,
                  )
              except OpenRouterError as exc:
                  async with self:
                      self.messages.append(
                          ChatMessage(
                              kind="upstream_error",
                              content="upstream_error",
                              prompt=text,
                              detail=str(exc),
                          )
                      )
                  return
              except (DuplicateCheckError, PiiRedactorError) as exc:
                  async with self:
                      self.messages.append(
                          ChatMessage(
                              kind="internal_error",
                              content="internal_error",
                              prompt=text,
                              detail=str(exc),
                          )
                      )
                  return
              except Exception as exc:
                  async with self:
                      self.messages.append(
                          ChatMessage(
                              kind="internal_error",
                              content="internal_error",
                              prompt=text,
                              detail=str(exc),
                          )
                      )
                  return

              if isinstance(result, QuerySuccessResponse):
                  bubble = ChatMessage(
                      kind="assistant",
                      content=result.response,
                      prompt=text,
                      model_used=result.model_used,
                      tokens_used=result.tokens_used,
                      audit_id=result.audit_id,
                      pii_redacted=result.pii_redacted,
                      pii_entities=result.pii_entities_masked,
                  )
              elif isinstance(result, QueryBlockedDuplicateResponse):
                  relative_info, release_info = format_duplicate_info(
                      result.first_query_at
                  )
                  bubble = ChatMessage(
                      kind="duplicate",
                      content=result.reason,
                      prompt=text,
                      first_query_at=result.first_query_at,
                      duplicate_relative_info=relative_info,
                      duplicate_release_info=release_info,
                  )
              elif isinstance(result, QueryBlockedSuspiciousResponse):
                  bubble = ChatMessage(
                      kind="injection",
                      content=result.reason,
                      prompt=text,
                      pattern=result.pattern,
                  )
              elif isinstance(result, QueryBlockedForbiddenResponse):
                  bubble = ChatMessage(
                      kind="forbidden",
                      content=result.reason,
                      prompt=text,
                      required_permission=result.required_permission,
                  )
              else:
                  # Unreachable for the current QueryResponse union -- kept so
                  # a fifth member added later without updating this chain
                  # surfaces as a visible bubble instead of an unhandled
                  # exception.
                  bubble = ChatMessage(
                      kind="internal_error",
                      content="internal_error",
                      prompt=text,
                      detail=f"Unhandled response type: {type(result).__name__}",
                  )

              async with self:
                  self.messages.append(bubble)
          finally:
              async with self:
                  self.pending = False

      @rx.event(background=True)
      async def retry_message(self, prompt: str):
          await self._do_send(prompt)

      @rx.event(background=True)
      async def send(self):
          # Read through the lock: a background event has no exclusive access
          # to state outside an `async with self` block.
          async with self:
              text = self.input_text
          await self._do_send(text)
  ```
  Note the `else` branch reachability comment: the QueryResponse union has exactly four members today (`QuerySuccessResponse`, `QueryBlockedDuplicateResponse`, `QueryBlockedSuspiciousResponse`, `QueryBlockedForbiddenResponse`), all now explicit `elif` arms — the final `else` is a total-function safety net, not a live path, satisfying AC5's "not the suspicious-pattern one" by construction rather than by luck.
- **Mirror**: `app/middleware/auth.py:14-20` (`require_identity`) for the resolve-then-reject-None shape; `app/services/query_pipeline.py:45-52` for the `identity=` keyword `run_query()` now requires.
- **Validate**: `cd chat_ui && ../.venv/Scripts/python.exe -c "from chat_ui.state import ChatState"` succeeds.

### Task 5: `bubbles.py` — `render_forbidden()`

- **File**: `chat_ui/chat_ui/components/bubbles.py`
- **Action**: UPDATE
- **Implement**: Add after `render_injection()` (`chat_ui/chat_ui/components/bubbles.py:278`):
  ```python
  def render_forbidden(message) -> rx.Component:
      """Denied by policy, not detected as an attack -- no retry action,
      since resending the same prompt hits the same permission check again."""
      ink, tint = theme.INK_FORBIDDEN, theme.TINT_FORBIDDEN
      return _entry(
          _rail(ink),
          _tag(copy.TAG_FORBIDDEN, ink),
          _panel(
              ink,
              tint,
              _prose(message.content),
              rx.cond(
                  message.required_permission != "",
                  _evidence(
                      f"{copy.FORBIDDEN_PERMISSION_LABEL}: ",
                      rx.el.span(
                          message.required_permission,
                          background_color=f"{ink}1A",
                          padding="0.05rem 0.3rem",
                          border_radius="2px",
                      ),
                      color=ink,
                      margin_top="0.5rem",
                  ),
                  rx.fragment(),
              ),
          ),
      )
  ```
- **Mirror**: `chat_ui/chat_ui/components/bubbles.py:251-278` (`render_injection`) — identical shape, swapping `pattern`/`INJECTION_PATTERN_LABEL` for `required_permission`/`FORBIDDEN_PERMISSION_LABEL` and the ink pair.
- **Validate**: covered by Task 9's component-import probe (`render_forbidden` added to `_EXPECTED_RENDERERS`).

### Task 6: `chat.py` — register the `"forbidden"` match arm

- **File**: `chat_ui/chat_ui/components/chat.py`
- **Action**: UPDATE
- **Implement**: Extend the `bubbles` import (`chat_ui/chat_ui/components/chat.py:6-15`) with `render_forbidden`, and add an arm to `message_bubble()` (`chat_ui/chat_ui/components/chat.py:19-31`):
  ```python
  from chat_ui.components.bubbles import (
      render_assistant,
      render_duplicate,
      render_fallback,
      render_forbidden,
      render_injection,
      render_internal_error,
      render_pending_indicator,
      render_upstream_error,
      render_user,
  )
  ...
  def message_bubble(message) -> rx.Component:
      """One rx.match over `kind`, one arm per pipeline outcome. A seventh
      outcome later is one new arm, not another level of nesting."""
      return rx.match(
          message.kind,
          ("user", render_user(message)),
          ("assistant", render_assistant(message)),
          ("duplicate", render_duplicate(message)),
          ("injection", render_injection(message)),
          ("forbidden", render_forbidden(message)),
          ("upstream_error", render_upstream_error(message)),
          ("internal_error", render_internal_error(message)),
          render_fallback(message),
      )
  ```
- **Mirror**: existing `("injection", render_injection(message))` arm — identical pattern.
- **Validate**: covered by Task 9.

### Task 7: `shell.py` — `login_gate()` and a sign-out header control

- **File**: `chat_ui/chat_ui/components/shell.py`
- **Action**: UPDATE
- **Implement**: Rename `user_id_gate()` (`chat_ui/chat_ui/components/shell.py:193-280`) to `login_gate()` and rewire it to `ChatState`'s new token vars, with `type="password"` on the input:
  ```python
  def login_gate() -> rx.Component:
      """Full-page form collecting the session's access token before the chat
      opens. type="password" keeps the credential off-screen while typed --
      the risk PRD-005 Risk 5 calls out is a role trusted from the client,
      not the token being visible in the input, but there is no reason to
      show it either."""
      return rx.center(
          rx.box(
              rx.box(
                  copy.SHELL_HEADER_TITLE,
                  font_family=theme.FONT_DISPLAY,
                  font_size="1.0625rem",
                  font_weight="700",
                  letter_spacing="0.16em",
                  color=theme.INK,
              ),
              rx.box(
                  copy.LOGIN_PROMPT_TITLE,
                  font_family=theme.FONT_DISPLAY,
                  font_size="1.5rem",
                  font_weight="600",
                  letter_spacing="-0.02em",
                  color=theme.INK,
                  margin_top="1.75rem",
              ),
              rx.box(
                  copy.LOGIN_PROMPT_BODY,
                  font_family=theme.FONT_BODY,
                  font_size=theme.TEXT_BODY,
                  line_height="1.6",
                  color=theme.MUTE,
                  margin_top="0.5rem",
              ),
              rx.form(
                  rx.input(
                      value=ChatState.token_input,
                      on_change=ChatState.set_token_input,
                      placeholder=copy.LOGIN_TOKEN_PLACEHOLDER,
                      type="password",
                      auto_focus=True,
                      width="100%",
                      font_family=theme.FONT_DATA,
                      font_size=theme.TEXT_BODY,
                      height="2.5rem",
                      background_color=theme.CARD,
                      border=f"1px solid {theme.RULE}",
                      border_radius=theme.RADIUS,
                      margin_top="1.5rem",
                  ),
                  rx.cond(
                      ChatState.login_error != "",
                      rx.box(
                          ChatState.login_error,
                          font_family=theme.FONT_DATA,
                          font_size=theme.TEXT_DATA,
                          color=theme.INK_DENIED,
                          margin_top="0.5rem",
                      ),
                      rx.fragment(),
                  ),
                  rx.box(
                      rx.el.button(
                          copy.LOGIN_SUBMIT_LABEL,
                          type="submit",
                          cursor="pointer",
                          width="100%",
                          height="2.5rem",
                          font_family=theme.FONT_DISPLAY,
                          font_size=theme.TEXT_BODY,
                          font_weight="600",
                          color=theme.PAPER,
                          background_color=theme.INK,
                          border="none",
                          border_radius=theme.RADIUS,
                          _hover={"background_color": theme.INK_UPSTREAM},
                          transition="background-color 120ms ease",
                      ),
                      margin_top="1rem",
                  ),
                  on_submit=ChatState.login,
                  width="100%",
              ),
              width="100%",
              max_width="24rem",
              padding="2.25rem",
              background_color=theme.CARD,
              border=f"1px solid {theme.RULE}",
              border_radius=theme.RADIUS,
          ),
          height="100vh",
          width="100%",
          padding="1.5rem",
      )
  ```
  In `header()` (`chat_ui/chat_ui/components/shell.py:87-101`), rename the control and its handler:
  ```python
  rx.el.button(
      copy.SHELL_LOGOUT_LABEL,
      on_click=ChatState.logout,
      type="button",
      cursor="pointer",
      background="none",
      border="none",
      padding="0",
      font_family=theme.FONT_DISPLAY,
      font_size=theme.TEXT_DATA,
      color=theme.MUTE,
      text_decoration="underline",
      text_underline_offset="3px",
      _hover={"color": theme.INK},
  ),
  ```
  (`ChatState.user_id` display just above it, `chat_ui/chat_ui/components/shell.py:79-86`, is unchanged — `user_id` still holds the authenticated id.)
- **Mirror**: the rest of `user_id_gate()`'s layout (`chat_ui/chat_ui/components/shell.py:193-280`) is preserved verbatim except for the token/copy/type swap above.
- **Validate**: covered by Task 9.

### Task 8: `chat_ui.py` — import `login_gate`

- **File**: `chat_ui/chat_ui/chat_ui.py`
- **Action**: UPDATE
- **Implement**: In the import (`chat_ui/chat_ui/chat_ui.py:16`) and in `index()` (`chat_ui/chat_ui/chat_ui.py:27-47`):
  ```python
  from chat_ui.components.shell import empty_state, header, login_gate
  ...
  def index() -> rx.Component:
      return rx.fragment(
          rx.el.style(theme.GLOBAL_CSS),
          rx.cond(
              ChatState.user_id != "",
              rx.vstack(
                  header(),
                  rx.cond(
                      ChatState.has_messages,
                      message_list(),
                      empty_state(),
                  ),
                  chat_input(),
                  height="100vh",
                  width="100%",
                  spacing="0",
                  background_color=theme.PAPER,
              ),
              login_gate(),
          ),
      )
  ```
- **Mirror**: unchanged `rx.cond(ChatState.user_id != "", ..., ...)` gate — only the else-branch factory name changes.
- **Validate**: covered by Task 9.

### Task 9: `tests/test_chat_components_import.py` — rename + new kind/renderer

- **File**: `tests/test_chat_components_import.py`
- **Action**: UPDATE
- **Implement**:
  1. `_EXPECTED_RENDERERS` (`tests/test_chat_components_import.py:28-37`): add `"render_forbidden"` after `"render_injection"`.
  2. `_KINDS` (`tests/test_chat_components_import.py:41-49`): add `"forbidden"` after `"injection"`.
  3. In `_CHECK_SCRIPT`'s import block (`tests/test_chat_components_import.py:64`): `from chat_ui.components.shell import empty_state, header, login_gate`.
  4. In `_CHECK_SCRIPT`'s shell-factory loop (`tests/test_chat_components_import.py:94`): `for factory in (header, empty_state, login_gate, message_list, chat_input):`.
- **Mirror**: the file's own existing entries for `render_injection`/`"injection"`/`user_id_gate` — same three lists, one more row each.
- **Validate**: `cd F:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_chat_components_import.py -q` — all four tests pass (this is the test that would have caught the STORY-014-era `chat_ui.state` import breaking, per the file's own docstring).

### Task 10: `tests/test_chat_state.py` — rewrite for login/logout, identity-based `send()`, and the forbidden branch

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE
- **Implement**:
  1. Imports — replace the `chat_ui.chat_ui.copy` import and extend the `app.*` imports:
     ```python
     from app.db.database import get_audit_log, get_connection, init_db, insert_audit_log, insert_user
     from app.db.models import AuditLog, User
     from app.models.schemas import (
         QueryBlockedDuplicateResponse,
         QueryBlockedForbiddenResponse,
         QueryBlockedSuspiciousResponse,
         QuerySuccessResponse,
     )
     from app.services.identity import hash_token
     ...
     from chat_ui.chat_ui.copy import LOGIN_INVALID_TOKEN_ERROR, LOGIN_TOKEN_REQUIRED_ERROR
     ```
     (`app.services.identity.Identity` and the rest of the existing imports are unchanged.)
  2. Module constants + `temp_db`, mirroring `tests/test_query_router.py:29-46`:
     ```python
     _AUTH_USER_ID = "juan@empresa.com"
     _AUTH_TOKEN = "test-user-token"

     @pytest.fixture
     def temp_db(tmp_path, monkeypatch):
         db_path = tmp_path / "test.db"
         monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
         init_db()
         insert_user(
             User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN))
         )
         return db_path
     ```
  3. `_make_state()` sets the backend-only token directly, same style as the existing `state.user_id = user_id` line:
     ```python
     def _make_state(user_id: str = _AUTH_USER_ID, token: str = _AUTH_TOKEN) -> ChatState:
         state = ChatState(_reflex_internal_init=True)
         state.user_id = user_id
         state._token = token
         return state
     ```
     Drop the now-redundant explicit `user_id="juan@empresa.com"` argument from every call site that used it (`_make_state(user_id="juan@empresa.com")` → `_make_state()`) — the default already matches.
  4. `_send()` helper (`tests/test_chat_state.py:81-84`) is unchanged.
  5. Rename the two `run_query`-signature tests that fake `run_query` directly by keyword — `test_run_query_*` (AC1 tests, `tests/test_chat_state.py:92-168`) are unchanged; they already call `run_query(identity=Identity(...), ...)` directly and pass today.
  6. In the four tests that monkeypatch `chat_state_mod.run_query` with a fake taking `user_id` as its first parameter — `test_chat_state_send_passes_session_user_id_and_prompt_to_run_query`, `test_chat_state_send_passes_selected_model`, `test_chat_state_send_populates_device_from_router_headers`, `test_chat_state_send_device_fallback_when_headers_missing` — rename that parameter to `identity` in each fake's signature. Rewrite the first one fully (the other three only need the signature rename, keeping their existing bodies otherwise):
     ```python
     @pytest.mark.asyncio
     async def test_chat_state_send_passes_resolved_identity_and_prompt_to_run_query(
         temp_db, monkeypatch
     ):
         recorded = {}

         def _fake_run_query(identity, prompt, device, model, openrouter_api_key, call_openrouter):
             recorded["identity"] = identity
             recorded["prompt"] = prompt
             return QuerySuccessResponse(
                 response="ok", audit_id=1, model_used=model, tokens_used=1
             )

         monkeypatch.setattr(chat_state_mod, "run_query", _fake_run_query)

         state = _make_state()
         await _send(state, "hello world")

         assert recorded["identity"].user_id == _AUTH_USER_ID
         assert recorded["identity"].role == "user"
         assert recorded["prompt"] == "hello world"
     ```
  7. Add two new tests directly exercising AC3 (re-resolution, never cached) — place them near the send tests:
     ```python
     @pytest.mark.asyncio
     async def test_chat_state_send_reresolves_role_on_every_call(temp_db, monkeypatch):
         """AC3: the role must come from the database on every call, never
         from anything cached on ChatState -- promoting the user mid-session
         with no code path that touches ChatState must still be picked up."""
         recorded_roles = []

         def _fake_run_query(identity, prompt, device, model, openrouter_api_key, call_openrouter):
             recorded_roles.append(identity.role)
             return QuerySuccessResponse(response="ok", audit_id=1, model_used=model, tokens_used=1)

         monkeypatch.setattr(chat_state_mod, "run_query", _fake_run_query)

         state = _make_state()
         await _send(state, "first prompt")
         assert recorded_roles == ["user"]

         with get_connection() as conn:
             conn.execute("UPDATE users SET role = 'admin' WHERE user_id = ?", (_AUTH_USER_ID,))

         await _send(state, "second prompt")
         assert recorded_roles == ["user", "admin"]


     def test_chat_state_holds_no_token_or_role_var():
         """AC4: only `user_id` (and the backend-only `_token`) may exist as
         an identity-related field -- no field literally named `token` or
         `role` anywhere on the class."""
         assert "role" not in ChatState.__annotations__
         assert "token" not in ChatState.__annotations__
         assert "_token" in ChatState.__annotations__
     ```
  8. Add a test for the new `QueryBlockedForbiddenResponse` branch (AC5):
     ```python
     @pytest.mark.asyncio
     async def test_chat_state_send_forbidden_response_renders_its_own_bubble_not_injection(
         temp_db, monkeypatch
     ):
         def _fake_run_query(identity, prompt, device, model, openrouter_api_key, call_openrouter):
             return QueryBlockedForbiddenResponse(
                 reason="Model not permitted for this role",
                 required_permission="query:model:gpt-4",
             )

         monkeypatch.setattr(chat_state_mod, "run_query", _fake_run_query)

         state = _make_state()
         await _send(state, "hello world")

         assert state.messages[-1].kind == "forbidden"
         assert state.messages[-1].kind != "injection"
         assert state.messages[-1].content == "Model not permitted for this role"
         assert state.messages[-1].required_permission == "query:model:gpt-4"
     ```
  9. Add a test for mid-session token revocation (defensive: AC3's "never trust a cached role" implies handling resolution failure, not just success):
     ```python
     @pytest.mark.asyncio
     async def test_chat_state_send_when_credential_revoked_mid_session_appends_internal_error(
         temp_db, monkeypatch
     ):
         from app.db.database import deactivate_user

         monkeypatch.setattr(chat_state_mod, "run_query", _fail_if_called)
         deactivate_user(_AUTH_USER_ID)

         state = _make_state()
         await _send(state, "hello world")

         assert state.messages[-1].kind == "internal_error"
         assert state.pending is False
     ```
  10. Replace the `submit_user_id`/`reset_user_id` test block (`tests/test_chat_state.py:469-517`) with login/logout coverage (AC1, AC2):
      ```python
      def test_chat_state_login_empty_token_shows_error():
          state = ChatState(_reflex_internal_init=True)
          state.token_input = "   "
          state.login()
          assert state.user_id == ""
          assert state.login_error == LOGIN_TOKEN_REQUIRED_ERROR

          state.token_input = ""
          state.login()
          assert state.user_id == ""
          assert state.login_error == LOGIN_TOKEN_REQUIRED_ERROR


      def test_chat_state_login_invalid_token_shows_error_and_stays_locked(temp_db):
          state = ChatState(_reflex_internal_init=True)
          state.token_input = "not-a-real-token"
          state.login()
          assert state.user_id == ""
          assert state.login_error == LOGIN_INVALID_TOKEN_ERROR


      def test_chat_state_login_deactivated_token_rejected(temp_db):
          from app.db.database import deactivate_user

          deactivate_user(_AUTH_USER_ID)
          state = ChatState(_reflex_internal_init=True)
          state.token_input = _AUTH_TOKEN
          state.login()
          assert state.user_id == ""
          assert state.login_error == LOGIN_INVALID_TOKEN_ERROR


      def test_chat_state_login_valid_token_sets_user_id_and_clears_error(temp_db):
          state = ChatState(_reflex_internal_init=True)
          state.token_input = "   "
          state.login()
          assert state.login_error == LOGIN_TOKEN_REQUIRED_ERROR

          state.token_input = _AUTH_TOKEN
          state.login()
          assert state.user_id == _AUTH_USER_ID
          assert state.login_error == ""
          assert state.token_input == ""
          assert state._token == _AUTH_TOKEN


      def test_chat_state_logout_clears_session_and_credential(temp_db):
          state = ChatState(_reflex_internal_init=True)
          state.token_input = _AUTH_TOKEN
          state.login()
          assert state.user_id == _AUTH_USER_ID

          state.logout()
          assert state.user_id == ""
          assert state.token_input == ""
          assert state.login_error == ""
          assert state._token == ""
      ```
  11. `test_chat_state_empty_and_reset_user_id` (`tests/test_chat_state.py:469-472`, the `has_messages`/empty check) keeps its `has_messages`/`messages` assertions but drops the `reset_user_id()` call it no longer needs (folded into item 10's `test_chat_state_logout_clears_session_and_credential` instead).
  12. `test_chat_state_model_selection` (`tests/test_chat_state.py:526-538`): replace `state.reset_user_id()` with `state.logout()`.
  13. `test_reset_user_id_clears_the_transcript` (`tests/test_chat_state.py:660-674`): rename to `test_logout_clears_the_transcript` and replace `state.reset_user_id()` with `state.logout()`; body otherwise unchanged.
  14. Audit-parity tests — add a bearer header to the API leg, matching `tests/test_query_router.py`'s pattern:
      ```python
      @pytest.mark.asyncio
      async def test_chat_and_api_audit_rows_share_schema_and_fields(temp_db, monkeypatch):
          def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
              return OpenRouterResult(response=f"response to {prompt}", model_used=model, tokens_used=7)

          monkeypatch.setattr(chat_state_mod, "call_openrouter", _fake_call_openrouter)
          monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)

          state = _make_state()
          await _send(state, "prompt from chat")
          chat_row_id = _last_audit_id()

          client.post(
              "/query",
              headers={"Authorization": f"Bearer {_AUTH_TOKEN}"},
              json={"prompt": "prompt from api"},
          )
          api_row_id = _last_audit_id()
          ...  # rest of the function body (field-parity loop) unchanged
      ```
      ```python
      @pytest.mark.asyncio
      async def test_duplicate_sent_via_chat_blocks_identical_prompt_via_api(temp_db, monkeypatch):
          def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
              return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)

          monkeypatch.setattr(chat_state_mod, "call_openrouter", _fake_call_openrouter)

          state = _make_state()
          await _send(state, "same prompt text")
          chat_entry = get_audit_log(_last_audit_id())

          response = client.post(
              "/query",
              headers={"Authorization": f"Bearer {_AUTH_TOKEN}"},
              json={"prompt": "same prompt text"},
          )

          assert response.status_code == 200
          assert response.json() == {
              "status": "BLOCKED",
              "reason": "Duplicate query within 24 hours",
              "first_query_at": chat_entry.timestamp,
          }
      ```
  15. All remaining tests not named above (`test_chat_state_pending_resets_on_success`, `test_chat_state_pending_resets_on_all_outcomes`, `test_chat_state_concurrent_send_guard`, `test_retry_message_resubmits_prompt`, `test_edit_and_resend_repopulates_composer`, `test_recovery_actions_ignored_when_pending`, `test_model_config_allowlist_and_default`) need no changes beyond `_make_state()` already resolving a real identity — they use `lambda *a, **kw` / `*args, **kwargs` fakes or the real `run_query`, so the `user_id`→`identity` keyword rename does not affect them.
- **Mirror**: `tests/test_query_router.py:29-46` for the fixture/constants shape; `tests/test_auth_dependencies.py:83-98` for the `insert_user` + `resolve`-based assertion style.
- **Validate**: `cd F:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_chat_state.py -q` — all tests (existing + new) pass.

---

## End-to-End Tests

- [ ] `.venv/Scripts/python.exe -m pytest tests/test_chat_state.py tests/test_chat_components_import.py -q` — full green, up from today's 6 failures
- [ ] `.venv/Scripts/python.exe -m pytest tests/test_query_pipeline_authorization.py tests/test_auth_dependencies.py tests/test_query_router.py -q` — untouched suites still pass (no regression)
- [ ] Manual: `python scripts/manage_users.py create-user --user-id manual-test --role user` (from repo root, `.venv` active) to mint a real token, then `cd chat_ui && reflex run`; open the app — the login gate (not a free-text box) appears
- [ ] Manual: submit an empty token → inline error, chat stays locked
- [ ] Manual: submit a bogus token → "Invalid or deactivated token.", chat stays locked
- [ ] Manual: submit the real token from `manage_users.py` → chat opens, header shows the user id and a "Sign out" control
- [ ] Manual: send a prompt → assistant bubble renders normally (pipeline still works end to end with the new `identity=` call)
- [ ] Manual: `python scripts/manage_users.py deactivate-user --user-id manual-test` in another terminal while the tab stays open, then send another prompt → an internal-error bubble appears (session invalidated), not a crash
- [ ] Manual: click "Sign out" → the login gate reappears and the transcript is gone

---

## Validation

```bash
cd F:/AI/harness-ai
.venv/Scripts/python.exe -c "import app.routers.query"
cd chat_ui
../.venv/Scripts/python.exe -c "from chat_ui import copy, theme; from chat_ui.models import ChatMessage; from chat_ui.state import ChatState; from chat_ui.components import bubbles; from chat_ui.components.chat import chat_input, message_bubble, message_list; from chat_ui.components.shell import empty_state, header, login_gate"
cd ..
.venv/Scripts/python.exe -m pytest tests/test_chat_state.py tests/test_chat_components_import.py tests/test_query_router.py tests/test_auth_dependencies.py tests/test_query_pipeline_authorization.py -q
```

---

## Acceptance Criteria

(Copied from story `STORY-014`)

- [ ] Given the login form, when a valid token is submitted, then the session becomes authenticated and the chat is usable
- [ ] Given an invalid or deactivated token, when it is submitted, then an error is shown and the chat stays locked
- [ ] Given an authenticated session, when `send()` runs, then the role is re-resolved server-side on every call, never read from a state var
- [ ] Given `ChatState`, when inspected, then it holds no token and no role — only the authenticated `user_id`, set exclusively by `login()`
- [ ] Given a `QueryBlockedForbiddenResponse`, when returned, then `send()` handles it in an explicit `isinstance` branch and renders its own bubble, not the suspicious-pattern one
- [ ] All tasks completed
- [ ] `tests/test_chat_state.py` and `tests/test_chat_components_import.py` pass in full
- [ ] Follows existing `resolve()`/`Identity`/`isinstance`-chain/backend-only-var patterns
