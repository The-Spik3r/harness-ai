---
story: STORY-010
prd: PRD-008
slug: query-request-session-id
title: "QueryRequest.session_id with UUID validation and a 403 on a foreign session"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-04
---

# Plan: QueryRequest.session_id with UUID validation and a 403 on a foreign session

## Summary

STORY-009 left `run_query` able to carry a `session_id` to all seven of its `log_query` call sites, and nothing yet hands it one. This story opens the API end: `QueryRequest` gains `session_id: Optional[str] = None` validated as a canonical UUID4 string by a Pydantic `field_validator` (not typed as `uuid.UUID`, because the value round-trips to a TEXT audit column and to `ChatState` as a string, and a type that serializes differently on the way out is a second representation of the same id); `app/routers/query.py` refuses a session belonging to someone else with `403 "session_id does not belong to the authenticated identity"`, immediately beside the `user_id` mismatch check it is modelled on, **audits the refusal**, and otherwise passes `session_id=request.session_id` into `run_query`.

The story's Technical Notes say the check "calls `chat_sessions.get(identity, session_id)` ... and refuses on `None`". **That cannot be written literally without breaking AC 7.** `chat_sessions.get` short-circuits to `None` when `CHAT_HISTORY_ENABLED` is false, so a router refusing on `None` would 403 every request carrying a `session_id` on a history-off deployment, where AC 7 requires the ownership check to be a no-op and the id to reach the audit column as supplied. The obvious repair — `if settings.CHAT_HISTORY_ENABLED and chat_sessions.get(...) is None` — is forbidden by a test that already exists: `tests/test_chat_sessions.py:1258 test_no_module_outside_the_service_branches_on_chat_history_enabled` walks the AST of every file under `app/` and `chat_ui/` and fails on any reference to the identifier outside `app/config.py` and `app/services/chat_sessions.py`. So the flag branch has to live in the service, and this plan adds a **ninth service function**, `chat_sessions.owns(identity, session_id) -> bool`, which answers exactly the router's question and holds the flag rule where PRD Section 6 puts it. That is a deliberate, argued deviation from the story's two-file list — see **Deviation from the story's Technical Notes** below — and it is a sanctioned extension rather than a break: `test_the_service_exposes_exactly_those_eight` says in its own docstring that "a later story that exposes a ninth function has to say so by editing this tuple rather than by nobody noticing", and `test_the_service_call_table_covers_every_discovered_function` is built to go red until a new function is driven with a foreign credential.

The refusal is audited, and that is the second place this story departs from its nearest precedent: the `user_id` mismatch above it writes **no** audit row, pinned by `tests/test_query_router.py:94`. That test must keep passing unmodified, so the `user_id` arm is left exactly as it is and only the session arm logs — AC 6's "a rejected send is logged with the same rigour as an accepted one" applies to the arm this story adds, not retroactively to the one beside it.

## User Story

As an integrating developer
I want `POST /query` to keep working unchanged when I send no `session_id`
So that adopting this release requires no client change — and, as a security admin, so that a session id belonging to someone else is refused rather than honoured.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-010-query-request-session-id.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md` — Section 4 (Pipeline & API), Section 5 (story 9), Section 9 (Ownership), Section 10, Section 12 Phase 2, Risk 3

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/models/schemas.py`, `app/routers/query.py`, `app/services/chat_sessions.py`, four test suites |
| Story | STORY-010 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |

**Dependencies verified.** `depends_on: [STORY-006, STORY-009]`, both `status: done`:

- STORY-006 → commit `1f529d3`. Confirmed by reading `app/services/chat_sessions.py`: the eight functions are present, each takes `identity: Identity` first, and each opens with `if not settings.CHAT_HISTORY_ENABLED:`.
- STORY-009 → commit `9ffb083`. Confirmed by reading `app/services/query_pipeline.py:61`: `run_query(..., session_id: Optional[str] = None)` is the last parameter, and `_deny` at line 31 takes it undefaulted.

Nothing blocks this story. It blocks STORY-021 and STORY-022; neither is touched here. `AuditQueryEntry.session_id` is **STORY-011** and is deliberately not added by this plan.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` was listed fresh for this plan and holds exactly one entry, `frontend-design`. Its `SKILL.md` frontmatter scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one", and its body is palette, typography, layout, motion and copy direction. This story edits two `app/` modules, one service and four test files, renders nothing and adds no string a user reads. The one string it does add — the 403 detail — is an API error body fixed verbatim by the story's AC 4, not a copy decision. | None |

The story's frontmatter carries `skills: []` and its Technical Notes reach the same conclusion; the scan was re-run against the directory rather than inherited from the story. `chat_ui/AGENTS.md`'s **reflex-docs** and **reflex-process-management** rules are not engaged either — no file under `chat_ui/` is opened by any task below.

---

## Patterns to Follow

### Naming — the optional, defaulted field appended to a request model

```python
# SOURCE: app/models/schemas.py:6-15
class QueryRequest(BaseModel):
    # Deprecated (PRD-005 Section 10): accepted for backward compatibility
    # only. Never trusted as identity -- the audited user id always comes
    # from the authenticated credential. A value that doesn't match the
    # credential is refused with 403 rather than silently overridden.
    user_id: Optional[str] = None
    prompt: str
    device: Optional[str] = None
    model: str = "gpt-4"
    openrouter_api_key: Optional[str] = None
```

`session_id` is added **after** `openrouter_api_key`, defaulted, so no positional constructor and no existing client body changes. `user_id` keeps its deprecation comment untouched — the story is explicit that this adds a field beside it and does not revisit it.

### Validation — `field_validator`, refusing at the boundary with a message that says what to do

```python
# SOURCE: app/config.py:126-142
    @field_validator("CHAT_SESSION_LIMIT")
    @classmethod
    def _validate_chat_session_limit(cls, value: int) -> int:
        """At least one session listed, or a startup error (PRD-008).

        A limit of 0 renders an empty rail on a user who has sessions, which is
        a silent lie rather than a small list -- so it fails at startup the way
        a bad DATABASE_URL does, rather than being defaulted away.
        """
        if value < 1:
            raise ValueError(
                f"CHAT_SESSION_LIMIT must be at least 1, got {value}. It is the "
                ...
            )
        return value
```

Pydantic is 2.13.5 (`requirements.txt` pins it unversioned; the installed version is v2), so `field_validator` + `@classmethod` is the house form, and it is already used for exactly this "refuse, with a sentence explaining the refusal" purpose. In a `BaseModel` a raised `ValueError` becomes a `422` — which is AC 3, obtained without any router code.

### Error handling — the 403 this one is modelled on, verbatim

```python
# SOURCE: app/routers/query.py:20-25
    if request.user_id is not None and request.user_id != identity.user_id:
        raise HTTPException(
            status_code=403,
            detail="user_id does not match the authenticated identity",
        )
```

### Error handling — the router's existing service-error-to-status mapping

```python
# SOURCE: app/routers/query.py:34-39
    except DuplicateCheckError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except PiiRedactorError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except OpenRouterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
```

`ChatSessionError` is a service-layer failure of exactly this family, and the ownership check runs *before* the `try` today's block wraps. Task 4 covers it explicitly rather than letting a storage failure during the check leave the router as an unhandled 500 with a traceback.

### Indistinguishability — the rule this story's AC 5 cites by name

```python
# SOURCE: app/services/identity.py:44-50
def resolve(token: Optional[str]) -> Optional[Identity]:
    """Verifies a credential and returns the Identity it belongs to, or
    None. None covers every failure case alike -- unknown, malformed,
    empty, or deactivated -- so the caller cannot distinguish them (PRD
    Section 9; STORY-002 Design Note 5 makes the same choice one layer
    down)."""
```

```python
# SOURCE: app/services/chat_sessions.py:166-176 (get)
    """This identity's session, or `None`.

    A session belonging to someone else returns `None`, exactly as one that does
    not exist does. ... A caller that could would have a membership
    oracle over other people's session ids.
    """
```

`owns()` inherits this: one `False` for the foreign session and the unknown one, so the caller cannot distinguish them, which is AC 5 stated one layer below where the story states it.

### The service's own shape — flag short-circuit, then `_wrapped`

```python
# SOURCE: app/services/chat_sessions.py:178-183
    if not settings.CHAT_HISTORY_ENABLED:
        return None

    with _wrapped("get"):
        return database.get_chat_session(session_id, identity.user_id)
```

`owns()` is written to this template exactly — the same two-line guard, the same `_wrapped(<own name>)`, the same single store call — because three suites assert the template structurally (`_service_statements_of`, the `history_off` tripwire, and the `ChatSessionError` wrapping tests) and a function shaped differently fails them for the right reason.

### Audit of a refusal — the pipeline's precedent for logging a rejected send

```python
# SOURCE: app/services/query_pipeline.py:43-52 (_deny)
    log_query(
        user_id=identity.user_id,
        prompt=prompt,
        device=device,
        success=True,
        role=identity.role,
        denied_permission=exc.permission,
        session_id=session_id,
    )
```

The refusal row in Task 4 follows this argument set, with two differences argued at the task: `denied_permission` stays `None` (no permission was denied — RBAC passed), and `success=False` with an `error_message` carries the reason, because `audit_logs` has no column for "refused for a foreign session" and this story adds none.

### Tests — the router suite's fixture, client and row-counting helpers

```python
# SOURCE: tests/test_query_router.py:28-49
_AUTH_USER_ID = "juan@empresa.com"
_AUTH_TOKEN = "test-user-token"
_AUTH_HEADERS = {"Authorization": f"Bearer {_AUTH_TOKEN}"}

client = TestClient(app, headers=_AUTH_HEADERS)


@pytest.fixture
def temp_db(temp_db):
    """conftest's initialized database, plus this suite's authenticated user."""
    insert_user(
        User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN))
    )
    return temp_db


def _count_audit_rows() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]
```

The new suite copies this prologue rather than importing from it — `tests/test_query_router.py` must stay unmodified (AC 8), and importing across suites would make it a module this story depends on.

### Tests — two genuine accounts, resolved the way production resolves them

```python
# SOURCE: tests/test_session_ownership.py:232-254
def _seed_two_users() -> tuple[Identity, Identity]:
    """Two real accounts with real credentials, resolved the way production does.
    ...
    "A test that drives a read with `bob` when no bob row exists proves
    less than one where bob is a genuine account: the first can pass because the
    id is unknown, the second only passes because the `WHERE` clause scopes."
    """
```

This is the difference between "the 403 fires because the id was unknown" and "the 403 fires because the row is someone else's", and AC 4 and AC 5 are separate criteria precisely because both cases must be driven.

### Tests — the census idiom for a rule that must outlive this story

```python
# SOURCE: tests/test_untouched_app.py:135-162
    gone = set(_TEST_DEF.findall(base_source)) - set(_TEST_DEF.findall(current_source))
    assert sorted(gone) == [], f"{path} lost test functions present at {_BASE}: {sorted(gone)}"
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/models/schemas.py` | UPDATE | `QueryRequest.session_id` + the UUID4 `field_validator` (AC 1, AC 3) |
| `app/services/chat_sessions.py` | UPDATE | `owns()` — the ninth service function, holding the flag rule where the AST guard requires it (AC 4, AC 5, AC 7) |
| `app/routers/query.py` | UPDATE | The 403 beside the `user_id` check, the audited refusal, `session_id` into `run_query`, `ChatSessionError` → 500 (AC 2, AC 4, AC 5, AC 6) |
| `tests/test_schemas.py` | UPDATE | `test_query_request_contract_is_unchanged` enumerates the field list; adding a field is exactly what it is built to catch |
| `tests/test_chat_sessions.py` | UPDATE | `THE_EIGHT` → nine, one `_call` shape, one flag-off expectation |
| `tests/test_session_ownership.py` | UPDATE | `_KNOWN_SERVICE`, `_SERVICE_SHAPES`, `_SERVICE_READS`, the read control |
| `tests/test_query_session_id.py` | CREATE | The story's eight acceptance criteria, driven through `POST /query` |

**Not changed, deliberately:**

| File | Why not |
|------|---------|
| `app/models/schemas.py` — `AuditQueryEntry` | STORY-011 owns `session_id` on the audit read model. This story stops at the request. |
| `app/services/query_pipeline.py` | STORY-009 finished it. `run_query` already takes and threads `session_id`; nothing here re-enters the pipeline, and no validation is added there (the boundary is the router, which is what keeps the in-process `ChatState` caller and the HTTP caller on one code path). |
| `app/db/database.py`, `app/db/models.py` | The story's "Do not reimplement the `WHERE user_id = ?` here" — `owns()` calls `database.get_chat_session`, which already scopes. No new store function. |
| `Caddyfile`, `app/main.py` | **No new route.** PRD Section 10; `tests/test_route_reservations.py` passing unmodified is the proof, and `@backend_routes` needs no change. |
| `tests/test_query_router.py`, `tests/test_integration.py`, `tests/test_route_reservations.py` | AC 8 and PRD Section 11 require these to pass **unmodified**. They are run, not edited. |
| `tests/test_untouched_app.py` | Its `_UNMODIFIED_SUITES` are `test_admin_auth`, `test_audit_router`, `test_stats_router`, `test_db`, `test_route_reservations`, `test_chat_state` — none of the four suites edited here. Its censuses assert only that baseline test functions were not *removed*; every edit below is additive. No update needed. |
| `README.md`, `.env.example` | STORY-022 owns the documentation pass. |

### Deviation from the story's Technical Notes, stated plainly

The story names two files and says the check "calls `chat_sessions.get(identity, session_id)` ... and refuses on `None`". This plan adds a third production file. The reason is that the story's own AC 7 and that instruction are not simultaneously satisfiable:

| Approach | AC 4/5 (403 on foreign & unknown) | AC 7 (flag off ⇒ no-op) | Existing guard |
|---|---|---|---|
| Router refuses on `chat_sessions.get(...) is None` | ✅ | ❌ 403s every session-carrying request when history is off | ✅ |
| Router adds `settings.CHAT_HISTORY_ENABLED and ...` | ✅ | ✅ | ❌ fails `test_no_module_outside_the_service_branches_on_chat_history_enabled` |
| **`chat_sessions.owns(identity, session_id)`** | ✅ | ✅ | ✅ |

The third row is the only one that passes all three columns, and it honours the *intent* of the note it deviates from — "PRD Section 6 puts the ownership rule in exactly one module" — better than the literal reading does, because the flag rule ends up in that same module rather than in the router. `owns()` reimplements nothing: it calls `database.get_chat_session`, one line, the same call `get()` makes.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: `QueryRequest.session_id`, with the UUID4 validator

- **File**: `app/models/schemas.py`
- **Action**: UPDATE
- **Implement**:
  - Add `import uuid` at the top and extend the pydantic import to `from pydantic import BaseModel, field_validator`.
  - Append `session_id: Optional[str] = None` to `QueryRequest`, **after** `openrouter_api_key`, with a comment recording why it is a `str` and not `uuid.UUID`: the value is written to a TEXT audit column and travels to `ChatState` as a string, and a type that serializes differently on the way out is a second representation of the same id (the story's Technical Notes, verbatim in intent).
  - Add the validator:
    ```python
    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        try:
            parsed = uuid.UUID(value)
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError(...) from exc
        if parsed.version != 4 or str(parsed) != value:
            raise ValueError(...)
        return value
    ```
  - Three properties, each deliberate, each documented in the docstring:
    1. **`None` passes through untouched.** AC 2 — a request omitting the field behaves exactly as the current release. The validator must not run any check on absence.
    2. **`version == 4`.** The story says "validated as a UUID4 string"; `create_chat_session` mints `str(uuid.uuid4())`, so a v1 id is not one this system ever issued.
    3. **`str(parsed) == value`.** This rejects `{braces}`, `urn:uuid:` and uppercase-hex spellings, which all parse but are a *second representation of the same id*. That matters most in the one case where nothing downstream would catch it: with `CHAT_HISTORY_ENABLED=false` the ownership check is a no-op (AC 7) and the value goes straight into the audit column, so an uppercase id would be filed under a spelling no `WHERE session_id = ?` will ever match. This is the strict end of the range the story leaves open; the loosening (normalize to `str(parsed)` instead of refusing) is rejected because AC 7 says the id is written "as supplied", and normalizing would edit it.
  - The `ValueError` message names the field, shows the value and says what a valid one looks like — the shape `app/config.py:137` uses. It reaches the client inside Pydantic's 422 body, so it is the error an integrating developer reads.
- **Mirror**: `app/config.py:126-142` (validator form and message shape); `app/models/schemas.py:6-15` (the appended, defaulted, commented field).
- **Validate**:
  - `python -c "from app.models.schemas import QueryRequest as Q; print(Q(prompt='hi').session_id); print(Q(prompt='hi', session_id='0f6c2e5a-9b3d-4c81-a7f2-1d5e8c9b0a34').session_id)"` → `None` then the id
  - `python -c "from app.models.schemas import QueryRequest as Q; Q(prompt='hi', session_id='not-a-uuid')"` → `ValidationError`

### Task 2: `tests/test_schemas.py` learns about the new field

- **File**: `tests/test_schemas.py`
- **Action**: UPDATE (lines 176-186)
- **Implement**:
  - Add `"session_id"` to the sorted list in `test_query_request_contract_is_unchanged` (it sorts between `prompt` and `user_id`), and assert alongside the existing two clauses that it is not required and defaults to `None` — AC 1 and AC 2 as a contract assertion, in the file that already owns the request contract.
  - Add three focused validator cases in the same file, next to it: a valid UUID4 accepted and returned unchanged; a non-UUID raising `ValidationError`; and `None` accepted. The end-to-end 422 belongs to Task 6's suite; these are the unit-level statements about the model, where the rest of this file already works.
- **Note**: this test is *designed* to fail on a field addition — its name is "contract is unchanged" and the story changes the contract. It is not on any unmodified list (`tests/test_untouched_app.py:71-78`), and editing it is how the change is acknowledged.
- **Mirror**: `tests/test_schemas.py:176-186`.
- **Validate**: `pytest tests/test_schemas.py -q`

### Task 3: `chat_sessions.owns()` — the ninth service function

- **File**: `app/services/chat_sessions.py`
- **Action**: UPDATE
- **Implement**:
  - Add `owns(identity: Identity, session_id: str) -> bool` after `get()`, so the two ownership reads sit together.
    ```python
    def owns(identity: Identity, session_id: str) -> bool:
        if not settings.CHAT_HISTORY_ENABLED:
            return True

        with _wrapped("owns"):
            return database.get_chat_session(session_id, identity.user_id) is not None
    ```
  - The docstring carries the three facts a reader needs, because each is counter-intuitive on its own:
    1. **Why it exists next to `get()`.** `get()` returns a row; this returns the *answer to the router's question*, which `get()` cannot give because its `None` conflates "not yours" with "history is off". A caller resolving that conflation would be a caller branching on the flag, which `tests/test_chat_sessions.py:1258` fails on. The single-purpose function is what keeps the branch here.
    2. **Why history-off answers `True`.** STORY-010 AC 7, quoted: "the ownership check is a no-op and the id is written to the audit row as supplied — **the flag governs the transcript, not the audit column**." With no transcript there are no session rows to own, so there is nothing to refuse; the id is then only a label on the audit row. Naming this honestly matters — `True` here does **not** mean "this identity owns that row", it means "nothing about this id is grounds to refuse the send". Say that in the docstring in those words, since the function name alone reads the other way.
    3. **Why `False` covers two cases.** The foreign session and the session that does not exist answer identically, per `get()`'s docstring and `identity.resolve()`'s rule — otherwise the API is a membership oracle over other people's session ids. This is AC 5.
  - `identity.role` is not read, here or anywhere in the module: PRD Section 9 keeps RBAC and ownership from substituting for one another, and `test_every_service_function_passes_identity_user_id_to_the_store` asserts its absence.
- **Mirror**: `app/services/chat_sessions.py:166-183` (`get`) for the body template; `app/services/chat_sessions.py:64-90` (`_wrapped`) for the error-wrapping contract.
- **Validate**:
  - `python -c "import inspect; from app.services import chat_sessions as c; print(list(inspect.signature(c.owns).parameters))"` → `['identity', 'session_id']`
  - `python -c "import inspect; from app.services import chat_sessions as c; print(inspect.signature(c.owns).return_annotation)"` → `bool`

### Task 4: the router — the 403, the audited refusal, and the passthrough

- **File**: `app/routers/query.py`
- **Action**: UPDATE
- **Implement**, in this order:
  - Import `log_query` from `app.services.audit_logger` and `ChatSessionError` + the `chat_sessions` module from `app.services`.
  - **Leave the `user_id` check exactly as it is** — same position, same message, and still writing no audit row. `tests/test_query_router.py:94-101` asserts `_count_audit_rows() == 0` on that path and must pass unmodified.
  - Immediately after it, add the session check:
    ```python
    if request.session_id is not None and not chat_sessions.owns(identity, request.session_id):
        log_query(
            user_id=identity.user_id,
            prompt=request.prompt,
            device=request.device,
            success=False,
            error_message="session_id does not belong to the authenticated identity",
            role=identity.role,
            session_id=request.session_id,
        )
        raise HTTPException(
            status_code=403,
            detail="session_id does not belong to the authenticated identity",
        )
    ```
  - Four decisions to record in a comment above the block, because each will otherwise read as a mistake:
    - **`request.session_id is not None` first**, so `owns()` is never called for the overwhelming majority of requests that omit the field — AC 2's "identical to the current release" includes issuing no extra query.
    - **The refusal is logged and the `user_id` mismatch beside it is not.** AC 6 requires this arm to be audited ("a rejected send is logged with the same rigour as an accepted one, which is PRD-001's founding property"); the arm above it is pinned by an existing test to write nothing, and this story does not revisit it. State the asymmetry in the comment so the next reader does not "fix" one to match the other.
    - **`success=False` with `error_message`, and `denied_permission=None`.** `_deny` in the pipeline uses `success=True` because a *policy* refusal is a successful harness outcome and the row already says which permission was denied. Here no permission was denied — RBAC passed and `require_permission` let the request through — so `denied_permission` would be a lie, and with `success=True` and no permission the row would be indistinguishable from an ordinary send. `audit_logs` has no column for "refused for a foreign session" and this story adds none, so `success=False` plus the reason in `error_message` is the shape that makes the row readable as the refusal it is.
    - **The supplied `session_id` goes on the row.** It is the thing that was attempted, and recording an attempt to reach another user's conversation is the entire evidentiary value of AC 6. That the id may name a row the caller does not own is expected; PRD Section 9 already accepts orphaned and cross-referencing `session_id` values on append-only audit rows.
  - Add `session_id=request.session_id` to the `run_query(...)` call, after `call_openrouter=`, matching the keyword style already there. This is unconditional — with history off it is how AC 7's "written to the audit row as supplied" happens.
  - Add `except ChatSessionError as exc: raise HTTPException(status_code=500, detail=str(exc)) from exc` to the existing handler chain. The check itself runs before the `try`, so **also** guard the check: move the ownership block inside the `try` that already wraps `run_query`, above the call, so the existing chain covers it with one error-mapping site rather than two. A storage failure during an ownership check must be a 500 that names the failure, not an unhandled exception; that is the same reason `DuplicateCheckError` is mapped at line 34.
- **Mirror**: `app/routers/query.py:20-25` (the 403 shape); `app/routers/query.py:34-39` (service error → status); `app/services/query_pipeline.py:43-52` (the `log_query` argument set for a refusal).
- **Note**: `HTTPException` is not caught by any arm of that chain, so raising the 403 from inside the `try` reaches the client unchanged.
- **Validate**:
  - `python -c "import app.routers.query"` → imports clean
  - `pytest tests/test_query_router.py tests/test_route_reservations.py -q` → green, **with no edit to either file**
  - `git diff --stat tests/test_query_router.py tests/test_integration.py tests/test_route_reservations.py` → empty

### Task 5: the two ownership suites learn about the ninth function

- **File**: `tests/test_chat_sessions.py`, `tests/test_session_ownership.py`
- **Action**: UPDATE
- **Implement** — these are the extension points those files document, exercised as documented:
  - `tests/test_chat_sessions.py:981-990` — add `"owns"` to `THE_EIGHT` and rename it `THE_NINE`, updating its references (lines ~1102, 1111, 1143, 1234, 1533, 1546 and the `test_a_storage_error_never_escapes_as_itself` loop). Update the comment above the tuple to say the ninth is STORY-010's, and rename `test_the_eight_service_functions_are_declared` / `test_the_service_exposes_exactly_those_eight` to match the new count. This is precisely what that second test's docstring asks for: "a later story that exposes a ninth function has to say so by editing this tuple rather than by nobody noticing."
  - `tests/test_chat_sessions.py:1059-1082` — add `"owns": lambda: chat_sessions.owns(identity, session_id)` to the `_call` shapes dict, so the flag-off tripwire, the foreign-identity drives and the three `ChatSessionError` wrapping tests all reach it without further edits.
  - `tests/test_chat_sessions.py:1190-1220` — `owns` is neither a write returning a usable value nor a read returning empty; add it as its own case asserting `_call("owns", ...) is True` under the `history_off` fixture, with a docstring giving Task 3's reason 2. `test_history_off_reaches_the_database_for_none_of_the_eight` then covers it automatically through `THE_NINE`.
  - `tests/test_session_ownership.py:98-108` — add `"owns"` to `_KNOWN_SERVICE`. The floor is a superset assertion so this is not strictly required; it is done because that frozenset documents "the functions that exist today" and a stale floor is a weaker floor.
  - `tests/test_session_ownership.py:296-315` — add `"owns": lambda identity, session_id: chat_sessions.owns(identity, session_id)` to `_SERVICE_SHAPES`, or `test_the_service_call_table_covers_every_discovered_function` goes red. That test going red first is the design working, not a problem to route around.
  - `tests/test_session_ownership.py:372` — add `"owns"` to `_SERVICE_READS`. It is a read: it issues a `SELECT` and changes nothing. `_assert_returns_nothing` already accepts `False`, so the foreign-credential drive asserts AC 5 with no change to the helper.
  - `tests/test_session_ownership.py:437-450` — add `assert chat_sessions.owns(ana, session_id) is True` to the read control, so "returns `False` to everyone" cannot pass the suite.
- **Note**: neither file is on `tests/test_untouched_app.py`'s `_UNMODIFIED_SUITES`, and every edit above is additive — no test function is removed, so the census guards stay green. The two renames add names rather than dropping them; keep the old names' coverage by renaming, not deleting, and re-run `pytest tests/test_untouched_app.py -q` to confirm.
- **Mirror**: the surrounding entries in each table.
- **Validate**: `pytest tests/test_chat_sessions.py tests/test_session_ownership.py -q` → green, including the parametrized `owns` cases now visible in `-v` output.

### Task 6: the story's acceptance criteria, driven through `POST /query`

- **File**: `tests/test_query_session_id.py`
- **Action**: CREATE
- **Implement**: a module docstring naming PRD-008 STORY-010 and stating what the suite is for — the API boundary is the only place a `session_id` arrives from outside the process, and every one of the three answers it can get (accepted, 422, 403) is a security-visible decision. Then the prologue copied from `tests/test_query_router.py:1-49` (the `os.environ.setdefault` pair, `_AUTH_*`, the `client`, the `temp_db` fixture that seeds the authenticated user, `_count_audit_rows`, `_fail_if_called`), a `_fake_call_openrouter` returning an `OpenRouterResult`, and helpers to seed a second real user and a session owned by them. Tests, one per acceptance criterion:

  **AC 2 — the omitted field is today's behaviour exactly**
  1. `test_a_request_without_session_id_still_succeeds_and_writes_null` — `POST /query` with `{"prompt": ...}`; 200, and `get_audit_log(response.json()["audit_id"]).session_id is None`.
  2. `test_omitting_session_id_leaves_the_rest_of_the_audit_row_identical` — two sends on distinct prompts, one omitting the field and one supplying an owned id; the rows agree on `user_id`, `device`, `model_used`, `tokens_used`, `success`, `role`, `denied_permission`, `pii_detected_input`, `pii_detected_output` and `pii_entities`, differing only in `session_id`, `id`, `prompt_hash`, `prompt_preview` and `timestamp`.

  **AC 3 — malformed is a 422, not a 500 and not a silent drop**
  3. `test_a_malformed_session_id_is_a_422_from_validation` — parametrized over `"not-a-uuid"`, `""`, `"0f6c2e5a9b3d4c81a7f21d5e8c9b0a34"` (unhyphenated), `"{0f6c2e5a-9b3d-4c81-a7f2-1d5e8c9b0a34}"`, an uppercase spelling, and a v1 UUID (`str(uuid.uuid1())`). Each asserts `422`, and asserts `_count_audit_rows() == 0` — a request refused before it is a request is not a send, so it produces no row. `call_openrouter` is patched to `_fail_if_called` throughout.
  4. `test_a_malformed_session_id_names_the_field_in_the_422_body` — the error body's `loc` reaches `session_id`, so an integrating developer is told which field, not merely that something failed.
  5. `test_a_non_string_session_id_is_also_a_422` — `{"session_id": 12345}`; the validator must not be reachable only by strings that happen to parse.

  **AC 4 and AC 5 — the foreign session and the unknown session, refused identically**
  6. `test_a_session_owned_by_another_identity_is_a_403_with_the_exact_detail` — seed a second genuine user, create a session owned by them via `chat_sessions.create`, send it with the first user's credential. `403`, and `response.json()["detail"] == "session_id does not belong to the authenticated identity"` — the string AC 4 fixes verbatim.
  7. `test_a_session_that_does_not_exist_is_the_same_403` — a freshly minted `str(uuid.uuid4())` naming nothing. Assert the status **and the body** equal test 6's, byte for byte: AC 5's "the caller cannot distinguish 'not yours' from 'does not exist'" is a claim about what the two responses have in common, so it is asserted as an equality between them rather than as two separate lookups.
  8. `test_the_refused_request_never_reaches_openrouter` — `call_openrouter` patched to `_fail_if_called` on both refusals.
  9. `test_the_owner_of_the_session_is_not_refused` — the control. Every assertion above is satisfied by a router that refuses every `session_id`; this one sends an owned id and asserts `200` and that the row carries it.

  **AC 6 — the refusal is in the record**
  10. `test_the_403_writes_one_audit_row_naming_the_refusal` — `_count_audit_rows()` goes from 0 to exactly 1 across the refused request; the row has `success is False`, `error_message == "session_id does not belong to the authenticated identity"`, `user_id == _AUTH_USER_ID` (the credential's, never the body's), `role == "user"`, `denied_permission is None`, and `session_id` equal to the id that was attempted.
  11. `test_the_user_id_mismatch_403_still_writes_no_row` — the asymmetry, pinned here rather than left to `tests/test_query_router.py` alone, so the next person to unify the two arms sees which of them a test actually wants unchanged.

  **AC 7 — the flag governs the transcript, not the audit column**
  12. `test_history_off_makes_the_ownership_check_a_no_op` — `monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)`, then send another user's session id. `200`, not `403`, and the audit row carries the id **as supplied**.
  13. `test_history_off_still_validates_the_uuid` — the same flag off with `"not-a-uuid"` is still a `422`. Validation is a property of the request model and the flag has no reach into it.
  14. `test_history_off_writes_the_supplied_id_verbatim` — the value read back from `audit_logs` is `==` the string sent, not a normalized or re-parsed one.

  **AC 8 — the three suites pass unmodified**
  15. `test_the_three_pinned_suites_are_unmodified_in_the_working_tree` — `git diff --name-only` (and `--cached`) against the epic branch contains none of `tests/test_query_router.py`, `tests/test_integration.py`, `tests/test_route_reservations.py`. Skip when git is unavailable, the way `tests/test_untouched_app.py:_base()` skips, so the suite stays runnable off a checkout. This is AC 8 turned from a promise into an assertion.

  **The structural guard**
  16. `test_the_router_never_branches_on_the_history_flag` — walk `app/routers/query.py` with `ast` and assert no `CHAT_HISTORY_ENABLED` reference. `tests/test_chat_sessions.py` already asserts this globally; asserting it here too puts the reason at the point of temptation, since the flag branch is the first thing someone reaching for AC 7 will write.
- **Mirror**: `tests/test_query_router.py:1-49` (prologue and helpers), `tests/test_session_ownership.py:232-254` (two genuine accounts), `tests/test_chat_sessions.py:1258-1289` (the `ast` walk), `tests/test_untouched_app.py:113-133` (the `_git` helper and its skip).
- **Validate**: `pytest tests/test_query_session_id.py -q` → all green; then temporarily delete the `session_id=request.session_id` argument from the `run_query` call, re-run, confirm the AC 7 and AC 2 tests **fail**, and restore it. A guard that has never been seen to fail is decoration.

### Task 7: prove the pinned suites are untouched and the whole thing holds

- **File**: — (verification only)
- **Action**: VERIFY
- **Validate**:
  - `pytest tests/test_query_router.py tests/test_integration.py tests/test_route_reservations.py -q` — green, with no edit to any of them (AC 8)
  - `pytest tests/test_untouched_app.py -q` — the censuses still green
  - `pytest -q` — full suite green
  - `git status --porcelain` — exactly the seven files in **Files to Change**, and nothing else
- **Note**: a burst of fixture errors across many suites at once is the libSQL dev container degrading under repeated runs, not this change — restart `harness-libsql-dev` and re-run before investigating the diff.

---

## End-to-End Tests

- [ ] `POST /query` with no `session_id` → 200, audit row's `session_id` is `NULL`, every other field as before — AC 2
- [ ] `POST /query` with `"session_id": "not-a-uuid"` → 422 naming `session_id`, no audit row, `call_openrouter` never called — AC 3
- [ ] `POST /query` with a v1 UUID, an unhyphenated one, a braced one and an uppercase one → 422 each — AC 1
- [ ] `POST /query` with a session owned by another genuine account → 403, detail exactly `"session_id does not belong to the authenticated identity"` — AC 4
- [ ] `POST /query` with a well-formed UUID4 naming no row → byte-identical 403 response to the previous case — AC 5
- [ ] Both refusals → exactly one audit row each, `success=False`, the reason in `error_message`, the attempted `session_id` on the row — AC 6
- [ ] `CHAT_HISTORY_ENABLED=false` + another user's `session_id` → 200, and the id lands in the audit column as supplied — AC 7
- [ ] `CHAT_HISTORY_ENABLED=false` + a malformed id → still 422 — AC 7's boundary
- [ ] `POST /query` with the caller's **own** session id → 200 and the id on the row — the control
- [ ] `tests/test_query_router.py`, `tests/test_integration.py`, `tests/test_route_reservations.py` pass with `git diff` empty for all three — AC 8
- [ ] `GET /audit`, `GET /stats`, `GET /health` unchanged; no new route on `app.routes`

---

## Validation

```bash
pytest tests/test_query_session_id.py -q
pytest tests/test_schemas.py tests/test_chat_sessions.py tests/test_session_ownership.py -q
pytest tests/test_query_router.py tests/test_integration.py tests/test_route_reservations.py -q
pytest tests/test_untouched_app.py tests/test_audit_logger.py tests/test_query_pipeline_session_passthrough.py -q
pytest -q
python -c "from app.models.schemas import QueryRequest as Q; print(sorted(Q.model_fields))"
python -c "import inspect; from app.services import chat_sessions as c; print(list(inspect.signature(c.owns).parameters))"
python -c "import ast,pathlib; t=ast.parse(pathlib.Path('app/routers/query.py').read_text()); print([n.lineno for n in ast.walk(t) if (isinstance(n,ast.Attribute) and n.attr=='CHAT_HISTORY_ENABLED')])"   # expect []
git diff --name-only
git status --porcelain
```

---

## Acceptance Criteria

(Copied from story `STORY-010`)

- [ ] Given `app/models/schemas.py`, when `QueryRequest` is read, then it declares `session_id: Optional[str] = None`, validated as a UUID4 string when present.
- [ ] Given a request omitting `session_id`, when it is served, then the response and the audit row are identical to the current release, with `session_id` written as `NULL`.
- [ ] Given a request whose `session_id` is not a UUID, when it is served, then the response is `422` from Pydantic validation — not a 500 and not a silently ignored field.
- [ ] Given a request whose `session_id` names a session owned by another identity, when it is served, then the response is `403` with detail `"session_id does not belong to the authenticated identity"`, raised in `app/routers/query.py` beside the existing `user_id` mismatch check.
- [ ] Given a request whose `session_id` names no session at all, when it is served, then the response is the same `403` — the caller cannot distinguish "not yours" from "does not exist".
- [ ] Given a refused request, when the audit trail is read, then the refusal is recorded.
- [ ] Given `settings.CHAT_HISTORY_ENABLED is False`, when a request carries a `session_id`, then the ownership check is a no-op and the id is written to the audit row as supplied.
- [ ] Given `tests/test_query_router.py`, `tests/test_integration.py` and `tests/test_route_reservations.py`, when the suite runs, then all three pass **unmodified**.
- [ ] All tasks completed
- [ ] Full suite `pytest -q` green
- [ ] No new route; `tests/test_route_reservations.py` proves it
- [ ] `QueryRequest.user_id` keeps its deprecated status and its comment
- [ ] No module outside `app/config.py` and `app/services/chat_sessions.py` references `CHAT_HISTORY_ENABLED`
- [ ] Follows existing patterns (the `user_id` 403, `_deny`'s audit shape, the service's flag-then-`_wrapped` template)
