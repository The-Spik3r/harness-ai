---
story: STORY-013
prd: PRD-013
slug: break-glass-ingress-policy
title: Break-glass ingress policy
type: NEW_CAPABILITY
complexity: LOW
epic_branch: epic/PRD-013-audit-and-usage-limits
created: 2026-10-19
---

# Plan: Break-glass ingress policy

## Summary

Add step 2b to `run_conversation`: when the identity is the break-glass one (`identity.break_glass`, set only by `resolve(ADMIN_TOKEN)`, STORY-008) and the call's `ingress` is not in `settings.break_glass_ingresses` (STORY-007), refuse through the existing forbidden arm, `_deny(..., exc=PermissionDenied("ingress:break_glass"), reason="Break-glass credential not permitted on this ingress")`. The check goes after the BYOK arm and before the usage gate (2c). It fails closed, because `None` is never in the allowed set. It reads the setting per call. It adds no response class and no RBAC permission. The test that `ingress` stays in step with the code is `Ingress = Literal["query", "chat", "v1"]`, defined next to `ContextLimit` and used to annotate the pipeline's `ingress` parameters. All behaviour is pinned in a new `tests/test_query_pipeline_break_glass.py`.

## User Story

As a security admin
I want `ADMIN_TOKEN` refused on ingresses where agents connect
So that pasting the break-glass credential into an agent's configuration does not work

## Story Reference

- Story file: `.agents/stories/PRD-013-audit-and-usage-limits/STORY-013-break-glass-ingress-policy.md`
- PRD: `.agents/PRDs/PRD-013-audit-and-usage-limits/PRD.md`, Sections 6.1, 6.8 (D4), 7 (F12), 9.2 (T9 and the order invariant), 11 (Break-glass; Refinement of the brief's criteria)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | LOW |
| Systems Affected | `app/services/query_pipeline.py` (one arm, one helper, one Literal); tests |
| Story | STORY-013 |
| PRD | PRD-013 |
| Epic Branch | `epic/PRD-013-audit-and-usage-limits` (commit directly on this branch) |
| Dependencies | STORY-005 ✅, STORY-007 ✅, STORY-008 ✅ |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` holds only `frontend-design`. This story changes no UI: the chat UI's forbidden bubble already renders the refusal. | — |

---

## What already exists (from the dependencies)

| Piece | Where | Notes |
|-------|-------|-------|
| `Identity.break_glass: bool = False` | `app/services/identity.py:43` | Frozen dataclass. Only `resolve()` sets it to True, at `app/services/identity.py:71-74` (the `ADMIN_TOKEN` path). |
| `BREAK_GLASS_INGRESSES: str = "query,chat"` | `app/config.py:338` | Validator at `app/config.py:510-540` rejects `v1` and unknown names and accepts `""`. |
| `settings.break_glass_ingresses -> frozenset[str]` | `app/config.py:556-557` | Property: it re-parses on every access, so a `monkeypatch.setattr(settings, "BREAK_GLASS_INGRESSES", ...)` takes effect on the next call. |
| `ingress` on every arm and call site | `app/services/query_pipeline.py:197, 242, 746`; `app/routers/query.py:145`; `chat_ui/chat_ui/state.py:1127, 1152` | `/query` passes `"query"` and both ChatState branches pass `"chat"`. Direct callers pass `None`. |
| The 2b placeholder comment | `app/services/query_pipeline.py:239-242` | "STORY-013's break-glass arm (2b) goes between the BYOK arm above and this block." |
| Forbidden bubble | `chat_ui/chat_ui/state.py:1236-1242` | Takes `reason` and `required_permission` from the result and needs no change. |
| Admin console gate | `chat_ui/chat_ui/admin_state.py:955-985` | Compares the submitted token with `settings.ADMIN_TOKEN` and never calls `resolve` or the pipeline. Unchanged. |

`Ingress` does **not** exist yet: `ingress` is typed `Optional[str]` everywhere. The story says to define it.

---

## Patterns to Follow

### Literals live beside the result union
```python
# SOURCE: app/services/query_pipeline.py:39-48
QueryPipelineResult = Union[
    QuerySuccessResponse,
    ...
    QueryBlockedUsageLimitResponse,
]

ContextLimit = Literal["messages", "characters"]
```

### A forbidden arm: `_deny` with a `PermissionDenied`
```python
# SOURCE: app/services/query_pipeline.py:285-294
    if openrouter_api_key is not None:
        try:
            authorize(identity, PERMISSION_QUERY_BYOK)
        except PermissionDenied as exc:
            return _deny(
                identity, prompt, device, session_id=session_id, dedup_key=key,
                profile=profile_name, ingress=ingress, message_count=message_count,
                conversation_key=conv_key, streamed=streamed, exc=exc,
                reason="Missing required permission",
            )
```
`_deny` (`app/services/query_pipeline.py:170-220`) writes the one row with `success=True`, `role`, `denied_permission=exc.permission` and all the PRD-013 fields, and returns `QueryBlockedForbiddenResponse(reason, required_permission=exc.permission)`. `PermissionDenied(permission)` is a plain exception carrying `.permission`. Constructing one does **not** touch `_KNOWN_PERMISSIONS` (`app/services/authz.py:16`, checked only by role-map validation at `:91`), the same way `authorize_model` raises `query:model:{model}`.

### Settings read per call, with a helper the tests can spy on
```python
# SOURCE: app/services/query_pipeline.py:73-99 (_context_limit_exceeded docstring)
#   Both maxima are read off `settings` **here, per call** rather than captured
#   at import ... every test in this suite sets them with
#   `monkeypatch.setattr(settings, ...)`, which a module-level constant would
#   silently ignore.
```
Order tests spy on module-level names of `query_pipeline` (`authorize`, `admit`, `_context_limit_exceeded`, ...). That is why the new check gets its own module-level predicate.

### Tests: the order spy, `_fail_if_called`, row read-back by id
```python
# SOURCE: tests/test_query_pipeline_usage_limits.py:318-371
def test_check_order_puts_the_gate_between_authorization_and_the_context_limit(temp_db, monkeypatch):
    trace: list = []
    real = {"authorize": query_pipeline.authorize, ... "admit": query_pipeline.admit, ...}
    def _spy_authorize(identity, permission):
        trace.append("authorize"); return real["authorize"](identity, permission)
    ...
    monkeypatch.setattr(query_pipeline, "admit", _spy_admit)
    ...
    assert trace == ["authorize", "authorize", "usage", "context_limit", "duplicate", "pattern", "upstream"]
```
```python
# SOURCE: tests/test_query_pipeline_usage_limits.py:94-110, 128-129
def _count_audit_rows() -> int: ...SELECT COUNT(*) AS n FROM audit_logs...
def _last_audit_entry():  # By id, not timestamp: timestamps have one-second resolution.
def _fail_if_called(*args, **kwargs):
    raise AssertionError("this collaborator should not have been called")
```
```python
# SOURCE: tests/test_query_pipeline_usage_limits.py:505-512 (route client)
@pytest.fixture
def client(temp_db):
    insert_user(User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN)))
    return TestClient(app, headers={"Authorization": f"Bearer {_AUTH_TOKEN}"})
# /query upstream is patched at "app.routers.query.call_openrouter".
```
```python
# SOURCE: tests/test_chat_state.py:126-136 (driving ChatState for real)
def _make_state(user_id=_AUTH_USER_ID, token=_AUTH_TOKEN) -> ChatState:
    state = ChatState(_reflex_internal_init=True); state.user_id = user_id; state._token = token; return state
async def _send(state, text):
    state.input_text = text
    await type(state).event_handlers["send"].fn(state)
# Upstream patched at chat_state_mod.call_openrouter.
```
```python
# SOURCE: tests/test_admin_state.py:199-210 (admin console gate)
def test_correct_token_authenticates_clears_the_error_and_triggers_the_load(configured_token):
    state = _state(); returned = _authenticate(state, configured_token)
    assert state.authenticated is True
```

### Module docstring style
Every PRD-013 test module opens with a docstring that names the story, the PRD sections and what is pinned, then sets `os.environ.setdefault("OPENROUTER_API_KEY", "test-key")` and `os.environ.setdefault("ADMIN_TOKEN", "test-token")` before importing app code (`tests/test_query_pipeline_usage_limits.py:1-36`).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/query_pipeline.py` | UPDATE | `Ingress` Literal; `_break_glass_refused(identity, ingress)` predicate; step 2b arm; `ingress` annotations go from `Optional[str]` to `Optional[Ingress]`; update the 2c comment that points at 2b |
| `tests/test_query_pipeline_break_glass.py` | CREATE | AC 1-5 |

No change to `app/config.py`, `identity.py`, `authz.py`, `schemas.py`, the router, ChatState or AdminState.

---

## Tasks

Run them in order. Each task is atomic and can be verified on its own.

### Task 1: Define `Ingress` and type the pipeline's `ingress` parameters

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**:
  - Below `ContextLimit` (line 48), add `Ingress = Literal["query", "chat", "v1"]`, with a one-line comment citing PRD-013 Sections 6.8 and 6.9: the doors a call site may name, with `v1` reserved for PRD-014.
  - Change `ingress: Optional[str]` to `Optional[Ingress]` in `_deny` (line 197), `run_conversation` (line 242) and `run_query` (line 746, keeping the default `"query"`).
  - Leave `audit_logger.log_query(ingress: Optional[str])` alone. It is a storage-layer writer, and importing from the pipeline would invert the dependency. It is out of scope.
- **Mirror**: `ContextLimit` at `app/services/query_pipeline.py:48`
- **Validate**: `python -c "import app.services.query_pipeline"`. The annotation alone changes no behaviour, so `pytest tests/test_query_pipeline_audit_fields.py -q` stays green.

### Task 2: Add the `_break_glass_refused` predicate

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**: a module-level function placed after `_context_limit_exceeded`:
  ```python
  def _break_glass_refused(identity: Identity, ingress: Optional[Ingress]) -> bool:
      return identity.break_glass and ingress not in settings.break_glass_ingresses
  ```
  Its docstring (matching the `_context_limit_exceeded` docstring) says:
  - The marker is the **credential**, not the role. An `admin`-role user token and a directly built `Identity("admin", "admin")` both have `break_glass=False`, so this never fires for them (AC 4).
  - It **fails closed**: `None` is in no allowed set, so a direct call that names no door is refused (T9).
  - The setting is read **here, per call**, through the property, for the reason `_context_limit_exceeded` gives.
  - The setting can only tighten: its validator rejects `v1`, so no configuration admits the token there (D4).
  - The function is module-level so the order test can spy on it by name.
- **Mirror**: `_context_limit_exceeded` at `app/services/query_pipeline.py:73-99`
- **Validate**: `python -c "from app.services.query_pipeline import _break_glass_refused"`

### Task 3: Insert the step 2b arm

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**: directly after the BYOK `if` block (ending at about line 294) and before `# Step 2c`, add:
  ```python
  # Step 2b: break-glass ingress policy (PRD-013 Sections 6.1, 6.8; D4, F12, T9).
  # <comment: after every authorization arm, so the three arms run first and
  #  unchanged (Section 9.1); before the gate, so a refused break-glass attempt
  #  consumes no window and is never charged. Reuses the forbidden arm: one row,
  #  success=True, denied_permission="ingress:break_glass" -- a label on the row
  #  like query:model:{model}, never an RBAC permission, so it is not in
  #  _KNOWN_PERMISSIONS. The admin role's model-allowlist bypass is untouched
  #  (Section 6.8, last bullet).>
  if _break_glass_refused(identity, ingress):
      return _deny(
          identity, prompt, device, session_id=session_id, dedup_key=key,
          profile=profile_name, ingress=ingress, message_count=message_count,
          conversation_key=conv_key, streamed=streamed,
          exc=PermissionDenied("ingress:break_glass"),
          reason="Break-glass credential not permitted on this ingress",
      )
  ```
  - Rewrite the 2c comment's second paragraph (lines 239-242). Remove "STORY-013's break-glass arm (2b) goes between …" and state that 2b sits directly above.
  - Do **not** add `"ingress:break_glass"` to a named constant in `authz.py`. A string literal at the arm, as the PRD's pseudo-code has it, keeps it out of anything that looks like a permission registry.
- **Mirror**: the BYOK arm at `app/services/query_pipeline.py:285-294`
- **Validate**: `pytest tests/test_query_pipeline_usage_limits.py tests/test_query_pipeline_authorization.py tests/test_query_pipeline_audit_fields.py -q`. They must stay green. None of them sends a break-glass identity, and the existing order test does not spy on the new helper, so its trace is unchanged (the STORY-011 plan's Risks row anticipated this).

### Task 4: Create `tests/test_query_pipeline_break_glass.py`

- **File**: `tests/test_query_pipeline_break_glass.py`
- **Action**: CREATE
- **Implement**: the module docstring names STORY-013, PRD-013 Sections 6.1, 6.8 and 9.2 (T9), and lists what is pinned. Set the env defaults, then import `query_pipeline`, `chat_state_mod`, `settings`, `resolve`, `Identity`, `hash_token`, `insert_user`, `User`, `get_audit_log`, `get_connection`, `TestClient`, `app`, `Message`, `QueryBlockedForbiddenResponse` and `QuerySuccessResponse`. Local helpers copied in the style of `tests/test_query_pipeline_usage_limits.py`: `_count_audit_rows`, `_last_audit_entry`, `_fail_if_called`, `_answer` and `_run(identity, *, ingress=..., upstream=...)`.

  The break-glass identity is always `resolve(settings.ADMIN_TOKEN)`, never a hand-built `Identity(..., break_glass=True)`. AC 1 is phrased in terms of what `resolve` returns, and going through `resolve` keeps the test honest if the marker's source changes. One assertion pins `break_glass is True` as a precondition.

  Tests, grouped by AC:

  **AC 1: refused under `v1` and `None`, with one row and no upstream call**
  - `test_break_glass_is_refused_on_v1_with_the_forbidden_body_and_one_row`, parametrized over `ingress="v1"` and the argument omitted (`ingress=None`, ids `v1` and `no-door`):
    - upstream is `_fail_if_called`;
    - `monkeypatch.setattr(query_pipeline, "admit", _fail_if_called)` proves the gate is never reached and nothing is counted;
    - `result == QueryBlockedForbiddenResponse(reason="Break-glass credential not permitted on this ingress", required_permission="ingress:break_glass")`;
    - the audit-row count goes up by exactly 1;
    - the row has `success is True`, `denied_permission == "ingress:break_glass"`, `role == "admin"`, `user_id == "admin"`, `ingress` equal to the parameter (`"v1"` or `None`), `message_count == 1`, non-NULL `dedup_key` and `conversation_key`, `limit_exceeded is None` and `was_duplicate_blocked is False`.
  - `test_the_refusal_holds_with_usage_limits_off`: with `USAGE_LIMITS_ENABLED=False` the result is the same. The arm does not depend on the gate's switch.
  - `test_ingress_break_glass_is_not_an_rbac_permission`: `"ingress:break_glass" not in authz._KNOWN_PERMISSIONS`.

  **AC 2: the default setting leaves `/query` and chat unchanged**
  - `test_default_setting_admits_break_glass_on_query_and_chat`, parametrized over `"query"` and `"chat"`: `_run(resolve(ADMIN_TOKEN), ingress=door, upstream=_answer)` returns `QuerySuccessResponse` and its row has `denied_permission is None`.
  - `test_post_query_with_admin_token_succeeds_under_the_default`: `TestClient(app, headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"})`, upstream patched at `"app.routers.query.call_openrouter"` with `_answer`, response `200` and `status == "SUCCESS"` (assert whatever `QuerySuccessResponse` actually serializes; read it from `app/models/schemas.py` first).
  - `test_chat_ui_send_with_admin_token_is_answered_under_the_default` (async): a real `ChatState` with `state._token = settings.ADMIN_TOKEN` and `user_id="admin"`, `chat_state_mod.call_openrouter` patched to `_answer`, `_send(state, "hello")`. The last bubble's `kind` is the success kind, not `"forbidden"`.

  **AC 3: the setting tightens**
  - `test_setting_chat_only_refuses_post_query_with_the_200_body`: `monkeypatch.setattr(settings, "BREAK_GLASS_INGRESSES", "chat")`; `POST /query` with the admin bearer and upstream `_fail_if_called`. Response `200` and json `{"status": "BLOCKED", "reason": "Break-glass credential not permitted on this ingress", "required_permission": "ingress:break_glass"}`. The row has `ingress == "query"`.
  - `test_setting_empty_refuses_the_chat_ui_with_the_forbidden_bubble` (async): `BREAK_GLASS_INGRESSES=""`, a real ChatState send with `ADMIN_TOKEN` and upstream `_fail_if_called`. The last bubble has `kind == "forbidden"`, `content` equal to the reason and `required_permission == "ingress:break_glass"`. The row has `ingress == "chat"`.
  - `test_the_setting_is_read_per_call`: the same identity and `ingress="query"`. The call succeeds under the default. After `monkeypatch.setattr(..., "chat")` it is refused, with no re-import in between.

  **AC 4: the role is not the marker**
  - `test_an_admin_role_user_token_is_not_refused_on_v1`: `insert_user(User(user_id="root", role="admin", token_hash=hash_token("root-token")))`; `ident = resolve("root-token")`; assert `ident.break_glass is False`; `_run(ident, ingress="v1", upstream=_answer)` returns `QuerySuccessResponse`.
  - `test_a_directly_built_admin_identity_is_not_refused_on_v1`: `Identity("admin", "admin")` with `ingress="v1"` returns `QuerySuccessResponse`.
  - `test_the_predicate_ignores_role`: unit-level, parametrized over identity × ingress, calling `query_pipeline._break_glass_refused` directly. It returns True only for the break-glass identity with `v1` or `None` under the default setting.

  **AC 5: the console is untouched, and the order**
  - `test_admin_console_gate_still_accepts_admin_token`: copy the `_state`/`_authenticate` helpers from `tests/test_admin_state.py`, or import them if that module documents them as importable (check its docstring first; copy if it doesn't). Patch `query_pipeline.run_conversation` and `query_pipeline._break_glass_refused` with `_fail_if_called`; authenticating with `settings.ADMIN_TOKEN` sets `authenticated is True`. This proves the console never enters the pipeline.
  - `test_check_order_puts_break_glass_after_authorization_and_before_the_gate`: copy the usage-limits order test's spies and add `_spy_break_glass` (label `"break_glass"`) wrapping `query_pipeline._break_glass_refused`. With the default identity `_JUAN` and `api_key=None`, `trace == ["authorize", "authorize", "break_glass", "usage", "context_limit", "duplicate", "pattern", "upstream"]`.
  - `test_check_order_with_byok_puts_break_glass_after_all_three_arms`: the same spies, identity `Identity("root", "admin")` (holds `query:byok`), `api_key="sk-caller"`. The trace starts `["authorize", "authorize", "authorize", "break_glass", "usage", ...]`.
  - `test_a_caller_denied_by_authorization_never_reaches_break_glass`: `_DENIED = Identity("reviewer", "auditor")`, with `_break_glass_refused` patched to `_fail_if_called`. The result is the `query:submit` refusal. This proves that authorization runs first and the arms are not reordered.
- **Mirror**: `tests/test_query_pipeline_usage_limits.py` (helpers, order spy, `client` fixture, route tests) and `tests/test_chat_state.py:126-136, 286-305` (ChatState drive, forbidden bubble)
- **Validate**: `pytest tests/test_query_pipeline_break_glass.py -v`

### Task 5: Full regression

- **Action**: run the whole suite.
- **Implement**: the one behaviour change that existing tests could hit is a **direct** `run_conversation`/`run_query` call with `resolve(ADMIN_TOKEN)` and no `ingress` (`run_query` defaults to `"query"`, so only `run_conversation` is exposed). The exploration found none: `break_glass=True` appears only in `tests/test_identity.py` and `tests/test_usage_limits.py`, and neither calls the pipeline. If one surfaces, the test should pass the door its production counterpart passes. Do not weaken the fail-closed rule.
- **Validate**: `pytest -q` (see the harness-ai test-env memory for the venv, the libSQL container and the known flakes).

---

## End-to-End Tests

- [ ] `pytest tests/test_query_pipeline_break_glass.py -v` → all green
- [ ] Start the API (`uvicorn app.main:app`), `curl -s -X POST localhost:8000/query -H "Authorization: Bearer $ADMIN_TOKEN" -H 'content-type: application/json' -d '{"prompt":"hi"}'` → today's behaviour (SUCCESS or the usual upstream outcome)
- [ ] Restart with `BREAK_GLASS_INGRESSES=chat` and send the same curl → `200` `{"status":"BLOCKED","reason":"Break-glass credential not permitted on this ingress","required_permission":"ingress:break_glass"}`; `GET /audit` shows the row with `denied_permission="ingress:break_glass"`, `ingress="query"`
- [ ] Start with `BREAK_GLASS_INGRESSES=v1` → startup fails with the STORY-007 message (regression check, already covered by `tests/test_config.py`)
- [ ] (No browser check needed: the chat bubble path is exercised by the real-ChatState tests in Task 4.)

---

## Validation

```bash
python -c "import app.services.query_pipeline"
pytest tests/test_query_pipeline_break_glass.py -v
pytest tests/test_query_pipeline_usage_limits.py tests/test_query_pipeline_authorization.py tests/test_query_pipeline_audit_fields.py tests/test_chat_state.py tests/test_admin_state.py -q
pytest -q
```

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| An existing test sends `resolve(ADMIN_TOKEN)` through `run_conversation` without a door and starts failing | None found in exploration. If one appears, fix the test's door (Task 5) and keep fail-closed. |
| Arm placed after `admit()` would count or charge a refused attempt | The order test (AC 5) and `admit` patched to `_fail_if_called` in AC 1 pin the position. |
| `"ingress:break_glass"` mistaken for a grantable permission | String literal at the arm, a negative assertion against `_KNOWN_PERMISSIONS`, and a comment. |
| Typing `ingress` as `Literal` tempts someone to annotate `log_query` and import the pipeline from the logger | Task 1 leaves `audit_logger` on `Optional[str]` and says why. |
| ChatState tests with `ADMIN_TOKEN` hit a real upstream if the stub misses a branch | Use `upstream=_fail_if_called` where refusal is expected, and patch `chat_state_mod.call_openrouter` (the binding both branches use) where success is expected. |
| `ARM_CASES` in `tests/test_audit_characterization.py` not extended | Deliberate, following STORY-011's precedent: a new arm there would change STORY-001's assertions. The row's fields are pinned in AC 1, and the AST scan in `test_query_pipeline_audit_fields.py` doesn't apply because the arm goes through `_deny`. |

---

## Acceptance Criteria

(Copied from story `STORY-013`)

- [ ] Given the identity `resolve(ADMIN_TOKEN)` returns, when `run_conversation(..., ingress="v1")` or `run_conversation(...)` with no ingress runs, then it returns `QueryBlockedForbiddenResponse(reason="Break-glass credential not permitted on this ingress", required_permission="ingress:break_glass")`, writes one row with `denied_permission="ingress:break_glass"`, and makes no upstream call.
- [ ] Given the default `BREAK_GLASS_INGRESSES`, when the break-glass identity sends through `POST /query` or the chat UI, then the request proceeds exactly as before this story.
- [ ] Given `BREAK_GLASS_INGRESSES="chat"`, when the break-glass identity calls `POST /query`, then it gets the `200` policy-refusal body; given `""`, then the chat UI refuses it too.
- [ ] Given a user token whose role is `admin`, or an `Identity("admin", "admin")` built directly, when it runs under `ingress="v1"`, then this arm does not fire.
- [ ] Given the admin console, when `ADMIN_TOKEN` is submitted at its gate, then sign-in works as before, and spies show this arm runs after the three authorization arms and before the usage gate.
- [ ] All tasks completed
- [ ] Full `pytest` suite passes
- [ ] Follows existing patterns
