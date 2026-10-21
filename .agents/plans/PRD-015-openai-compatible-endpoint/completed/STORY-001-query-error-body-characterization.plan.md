---
story: STORY-001
prd: PRD-015
slug: query-error-body-characterization
title: "Characterize /query's error bodies and the upstream request body before /v1 exists"
type: REFACTOR
complexity: LOW
epic_branch: epic/PRD-015-openai-compatible-endpoint
created: 2026-10-21
---

# Plan: Characterize /query's error bodies and the upstream request body before /v1 exists

## Summary

One new test module, `tests/test_v1_query_isolation.py`, written and run green on untouched code. It does two things. First, it pins the full status and whole JSON body of every `/query` error that STORY-010's app-wide exception handlers could touch: 401 (no bearer, invalid bearer), 403 (missing `query:submit`), 422 (missing `prompt`, malformed `session_id`), 500 (`DuplicateCheckError`, `PiiRedactorError`) and 502 (`OpenRouterError`). Second, it pins the upstream request. A real `call_openrouter` is driven over an `httpx.MockTransport` from a `/query` success and from a direct `run_conversation` call with all four `GenerationParams` set. The test asserts the URL and that the JSON body's keys are exactly `model`, `messages` and the set parameters. No production file changes. The module is named for both halves so STORY-010 can add the `/v1` half later.

## User Story

As a maintainer
I want `/query`'s error responses and the exact body sent upstream pinned on untouched code
So that the `/v1` exception handlers and the parameter work later in this epic provably change neither

## Story Reference

- Story file: `.agents/stories/PRD-015-openai-compatible-endpoint/STORY-001-query-error-body-characterization.md`
- PRD: `.agents/PRDs/PRD-015-openai-compatible-endpoint/PRD.md` (Sections 6.3, 7.5, 9.2 T5, 11, 14 Risk 4)

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR (characterization only, no behaviour change) |
| Complexity | LOW |
| Systems Affected | tests only |
| Story | STORY-001 |
| PRD | PRD-015 |
| Epic Branch | `epic/PRD-015-openai-compatible-endpoint` (commit directly on this branch) |

### Branch note (read before Task 1)

The epic branch does not exist yet. Local `main` is stale (`728dd60`, before the PRD-014 merge). `origin/main` is `c1b2e33`, which merges PRD-014 and includes the `db` marker, the storage guard and the lazy libSQL endpoint that AC4 relies on. Create the branch from `origin/main`:

```bash
git fetch origin
git checkout -b epic/PRD-015-openai-compatible-endpoint origin/main
```

The working tree's untracked `.agents/PRDs/PRD-015-*` and `.agents/stories/PRD-015-*` and the modified `pre-prds/*` carry over on checkout. "Untouched main" in AC1 means `origin/main` at `c1b2e33` with only this test file added.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| none | `.agents/skills/` holds only `frontend-design`; this story has no UI (story Technical Notes, PRD Section 15) | none |

---

## Patterns to Follow

### Module header and env defaults
```python
# SOURCE: tests/test_query_router.py:1-4
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
```

### Local `temp_db` override that seeds the authenticated user
```python
# SOURCE: tests/test_query_router.py:52-58
@pytest.fixture
def temp_db(temp_db):
    """conftest's initialized database, plus this suite's authenticated user."""
    insert_user(
        User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN))
    )
    return temp_db
```

### Upstream monkeypatch at the router binding
```python
# SOURCE: tests/test_query_router.py:85-96
def _fail_if_called(*args, **kwargs):
    raise AssertionError("call_openrouter should not have been called")

def test_missing_authorization_header_returns_401_and_no_audit_row(temp_db, monkeypatch):
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
    unauth_client = TestClient(app)
    response = unauth_client.post("/query", json={"prompt": "hello world"})
```

### Auditor identity for the 403
```python
# SOURCE: tests/test_query_router.py:99-109
insert_user(User(user_id="reviewer", role="auditor", token_hash=hash_token("auditor-token")))
auditor_client = TestClient(app, headers={"Authorization": "Bearer auditor-token"})
response = auditor_client.post("/query", json={"prompt": "hello world"})
assert response.status_code == 403
assert response.json() == {"detail": f"Permission denied: {PERMISSION_QUERY_SUBMIT}"}
```

### Redaction stub by the pipeline's own name
```python
# SOURCE: tests/test_audit_characterization.py:146-147, 160
def _mask_nothing(text, *args):
    return text, []
monkeypatch.setattr(query_pipeline, "redact", _mask_nothing)
```
`query_pipeline._redact` calls `redact` by this module's name for the `chat` policy (`app/services/query_pipeline.py:173-190`), so the patch reaches `/query`.

### The router's error mapping being pinned
```python
# SOURCE: app/routers/query.py:27-41
except DuplicateCheckError as exc:
    raise HTTPException(status_code=500, detail=str(exc)) from exc
...
except PiiRedactorError as exc:
    raise HTTPException(status_code=500, detail=str(exc)) from exc
except OpenRouterError as exc:
    raise HTTPException(status_code=502, detail=str(exc)) from exc
```

### Upstream payload characterization (reuse `_API_URL`, do not define a third)
```python
# SOURCE: tests/test_openrouter_client.py:21, 126-136
_API_URL = "https://openrouter.ai/api/v1/chat/completions"
...
assert json.dumps(payload, sort_keys=False) == json.dumps(expected, sort_keys=False)
```
`tests/test_audit_characterization.py:620` defines its own copy on purpose ("Private on purpose"). This module imports the one from `tests.test_openrouter_client`. The precedent for importing from a test module is `tests/test_audit_characterization.py:74` (`from tests.test_query_pipeline_patterns import ...`).

### Direct `run_conversation` call
```python
# SOURCE: tests/test_query_pipeline_run_conversation.py:35, 196-199
_JUAN = Identity(user_id="juan@empresa.com", role="user")
query_pipeline.run_conversation(
    identity=_JUAN, messages=messages, device=None, model="gpt-4",
    openrouter_api_key=None, call_openrouter=_fake_call_openrouter,
)
```

### Frozen-record module docstring
```text
# SOURCE: tests/test_audit_characterization.py:1-9
**Every assertion in this module is a frozen record of pre-PRD-013 behaviour.
None of it is a requirement.** ... A later story may add assertions for the
fields it adds. It may not change or delete one written here.
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_v1_query_isolation.py` | CREATE | The `/query` half of the isolation pins (status and whole body for 401/403/422/500/502) and the upstream URL/body-keys baseline (PRD T5) |

No production file, no `conftest.py` change. `db` marking is automatic: every test that requests `temp_db` is marked at collection (`tests/conftest.py:150-160`). The one storage-free test, no bearer, requests no storage fixture. `resolve(None)` returns before `find_user_by_token_hash` (`app/services/identity.py:75-76`), so the storage guard does not fire.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Create the epic branch and capture today's bodies

- **File**: none (probe only, nothing committed)
- **Action**: Create the branch (see Branch note). Then, with the libSQL container up, capture the exact 422 bodies on untouched code from a throwaway script under the scratchpad. Pass `PYTHONPATH` in `C:\...` form. Use `TestClient(app)` with a valid user token seeded through `temp_db`-equivalent setup, or a quick `pytest` with `print(response.json())` and `-s`.
- **Why**: AC1 pins the 422 bodies "as returned today, including `loc` and `type`". FastAPI 0.142.2 and pydantic 2.13.5 decide `msg`, `input` and `ctx` (the `ctx.error` encoding of the `ValueError` raised by `QueryRequest._validate_session_id`, `app/models/schemas.py:27-68`). The literals must come from observation, not memory. Expected shapes, to be confirmed:
  - missing `prompt`, body `{}`: `{"detail": [{"type": "missing", "loc": ["body", "prompt"], "msg": "Field required", "input": {}}]}`
  - malformed `session_id`, body `{"prompt": "hello world", "session_id": "not-a-uuid"}`: one entry with `"type": "value_error"`, `"loc": ["body", "session_id"]`, `"msg": "Value error, session_id must be a canonical lowercase UUID4 string, got 'not-a-uuid'. ..."`, `"input": "not-a-uuid"`, and a `ctx` key
- **Validate**: the printed dicts are pasted verbatim as literals in Task 2. Keep the `msg` string whole. It is long, so build it from the same three string pieces the validator uses, or split it across adjacent literals.

### Task 2: Write `tests/test_v1_query_isolation.py`, the error-body half

- **File**: `tests/test_v1_query_isolation.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring: PRD-015 STORY-001. This is a frozen record of `/query`'s error bodies on `main` before any `/v1` code. STORY-010 registers app-wide handlers that must delegate outside `/v1/` (PRD Section 7.5, Risk 4) and adds the `/v1` half to this module. A later story may add tests here. It may not change or delete a pin. Bodies are compared as whole dicts so a handler cannot add, rename or reshape a field. Also note the libSQL dev-container advice, as `tests/test_audit_characterization.py` does.
  - Header: `os.environ.setdefault` for `OPENROUTER_API_KEY` and `ADMIN_TOKEN`, then imports.
  - Constants: own `_AUTH_USER_ID` / `_AUTH_TOKEN` / `_AUTH_HEADERS` (don't import `test_query_router`'s module-level client). `_PROMPT = "hello world"`.
  - Local `temp_db` override seeding the `user`-role caller (mirror `tests/test_query_router.py:52-58`).
  - `_fail_if_called` local.
  - Tests. Each one asserts `response.status_code == N` and `response.json() == {...}` with a literal dict:
    1. `test_query_401_without_bearer_body_is_pinned(monkeypatch)`: **no `temp_db`** (the storage-free test, AC4). `TestClient(app)` with no headers, upstream patched to `_fail_if_called`. Expect `401`, `{"detail": "Invalid or missing credential"}`.
    2. `test_query_401_with_unknown_bearer_body_is_pinned(temp_db, monkeypatch)`: header `Bearer not-a-real-token`. Same body. Needs storage because `resolve` looks the hash up.
    3. `test_query_403_without_query_submit_body_is_pinned(temp_db, monkeypatch)`: seed `reviewer`/`auditor`. Expect `{"detail": "Permission denied: query:submit"}`. Write the literal string, not `f"...{PERMISSION_QUERY_SUBMIT}"`, so a renamed constant shows up as a diff.
    4. `test_query_422_missing_prompt_body_is_pinned(temp_db, monkeypatch)`: body `{}`, literal from Task 1. Needs a valid bearer because FastAPI resolves the auth dependency before reporting body errors. A 401 would mask the 422.
    5. `test_query_422_malformed_session_id_body_is_pinned(temp_db, monkeypatch)`: literal from Task 1.
    6. `test_query_500_duplicate_check_error_body_is_pinned(temp_db, monkeypatch)`: `monkeypatch.setattr(query_pipeline, "check_duplicate", _raise(DuplicateCheckError("Duplicate lookup failed: isolation probe")))`, upstream `_fail_if_called`. Expect `500`, `{"detail": "Duplicate lookup failed: isolation probe"}`. Use a fixed message, not the `DROP TABLE` route in `tests/test_query_router.py:210-237`: a real driver error makes `detail` driver-dependent, which a whole-dict pin cannot hold. The real-failure path stays pinned there.
    7. `test_query_500_pii_redactor_error_body_is_pinned(temp_db, monkeypatch)`: `monkeypatch.setattr(query_pipeline, "redact", ...)` raising `PiiRedactorError("PII analysis failed: isolation probe")`, upstream `_fail_if_called`. Expect `500` and that detail.
    8. `test_query_502_openrouter_error_body_is_pinned(temp_db, monkeypatch)`: `query_pipeline.redact` -> `_mask_nothing`. Upstream raises `OpenRouterError("OpenRouter request failed: isolation probe")`. Expect `502` and that detail.
  - Keep every string in the file ASCII (cp1252 console, memory note). Use `--` not em dashes in comments.
- **Mirror**: `tests/test_query_router.py:85-110` (structure), `tests/test_audit_characterization.py:1-42` (docstring tone)
- **Validate**: `C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe -m pytest tests/test_v1_query_isolation.py -q` (8 passed)

### Task 3: Add the upstream-request half

- **File**: `tests/test_v1_query_isolation.py`
- **Action**: UPDATE
- **Implement**:
  - `from tests.test_openrouter_client import _API_URL` (story note: reuse, don't define a third).
  - `from app.services.openrouter_client import GenerationParams, OpenRouterResult, call_openrouter` (the real one, kept under a local name such as `_real_call_openrouter` so the router monkeypatch doesn't shadow it).
  - Helper `_capturing_transport(seen: list) -> httpx.MockTransport`. Its handler appends the `httpx.Request` and returns `httpx.Response(200, json={"choices": [{"message": {"content": "Hi there!"}, "finish_reason": "stop"}], "model": "gpt-4", "usage": {"total_tokens": 12}})`.
  - Helper `_upstream_over(transport)` returns `def _call(messages, model=..., api_key=None, params=None): return _real_call_openrouter(messages, model=model, api_key=api_key, params=params, client=httpx.Client(transport=transport))`. It accepts `params` because `run_conversation` passes it only when set (`app/services/query_pipeline.py:648-655`). Close the client in a `with` block.
  - `test_query_success_upstream_request_is_pinned(temp_db, monkeypatch)`: `query_pipeline.redact` -> `_mask_nothing`. Patch `app.routers.query.call_openrouter` with `_upstream_over(...)`. POST `/query` `{"prompt": "hello world"}` gives `200`. Then exactly one captured request, with `request.method == "POST"`, `str(request.url) == _API_URL` and `list(json.loads(request.content)) == ["model", "messages"]`. Also pin the whole body: `{"model": "gpt-4", "messages": [{"role": "user", "content": "hello world"}]}`. The model is `QueryRequest`'s default. Read it from `app/models/schemas.py`; if it differs, pin what is sent.
  - `test_run_conversation_upstream_request_with_all_four_params_is_pinned(temp_db, monkeypatch)`: `query_pipeline.redact` -> `_mask_nothing`. Call `query_pipeline.run_conversation(identity=Identity(user_id=_AUTH_USER_ID, role="user"), messages=[Message("user", "hello world")], device=None, model="gpt-4", openrouter_api_key=None, params=GenerationParams(temperature=0.2, max_tokens=100, top_p=0.9, stop=["END"]), call_openrouter=_upstream_over(...))`. Assert the result is `QuerySuccessResponse`, then `str(request.url) == _API_URL`. Assert `list(body) == ["model", "messages", "temperature", "max_tokens", "top_p", "stop"]`, ordered like `call_openrouter`'s field loop (`app/services/openrouter_client.py:129-133`). Assert the values `0.2, 100, 0.9, ["END"]`. A comment cites PRD Section 9.2 T5: no key outside `model`, `messages` and the four fields.
  - No assertion on the `Authorization` header value. The key comes from `.env` or the `setdefault`, and printing it on failure would leak it.
- **Mirror**: `tests/test_openrouter_client.py:126-149` (payload/URL characterization), `tests/test_query_pipeline_run_conversation.py:196-199`
- **Validate**: `C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe -m pytest tests/test_v1_query_isolation.py -q` (10 passed)

### Task 4: Prove the `db` split (AC4)

- **File**: none
- **Action**: verify markers and the Docker-free run
- **Implement**:
  - `python -m pytest tests/test_v1_query_isolation.py -m db --collect-only -q` lists 9 tests (all but the no-bearer one).
  - `HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:9 python -m pytest tests/test_v1_query_isolation.py -m "not db" -q` gives 1 passed, 9 deselected. A dead endpoint proves the run needs no Docker, without stopping the shared container (memory note, PRD-014 STORY-007).
- **Validate**: both commands' outputs match the counts above

### Task 5: Full-suite regression (AC3)

- **File**: none
- **Action**: run the whole suite in the background, wrapped in the `SetThreadExecutionState` keep-awake helper (S3 sleep note). Log to a file through `cmd /c "... > log 2>&1"`.
- **Validate**: all green except known flakes. Any failing `db` test is triaged with `grep "libsql verdict"` on the log: `likely infrastructure` means rerun only that file. Expected count is the previous total plus 10. `git diff --stat origin/main -- tests app` shows only the new file.

---

## End-to-End Tests

No running server is involved. The `TestClient` requests are the E2E surface for this story:

- [ ] `POST /query` with no bearer returns `401` `{"detail": "Invalid or missing credential"}` with Docker unreachable
- [ ] Each of the 7 storage-backed error cases returns its pinned status and whole body against the libSQL dev container
- [ ] A `/query` success sends exactly `{"model", "messages"}` to `https://openrouter.ai/api/v1/chat/completions` through a real `call_openrouter` and `httpx.MockTransport`
- [ ] `run_conversation` with all four `GenerationParams` sends exactly `model, messages, temperature, max_tokens, top_p, stop`

---

## Validation

```bash
PY='C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe'
docker start harness-libsql-dev
"$PY" -m pytest tests/test_v1_query_isolation.py -q
"$PY" -m pytest tests/test_v1_query_isolation.py -m db --collect-only -q
HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:9 "$PY" -m pytest tests/test_v1_query_isolation.py -m "not db" -q
"$PY" -m pytest tests/ -q   # background, keep-awake wrapper
git diff --stat origin/main -- app tests   # only tests/test_v1_query_isolation.py
```

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| 422 literals written from memory don't match FastAPI 0.142.2 / pydantic 2.13.5 | Task 1 captures them on untouched code first |
| A real storage failure makes the 500 `detail` driver-dependent | Fixed-message stubs at the pipeline's own bindings (`check_duplicate`, `redact`); the real path stays covered by `tests/test_query_router.py:210-237` |
| Shared-DB flake shows as a bare 500 (memory note) | Whole-body pins print the unexpected `detail`; check the `libsql verdict` line and rerun before blaming code |
| Importing `tests.test_openrouter_client` runs its `os.environ.setdefault` lines | Same two defaults this module sets, so no new effect |
| `-m "not db"` run trips the storage guard on the no-bearer test | `resolve(None)` returns before any lookup (`app/services/identity.py:75-76`); Task 4 proves it with a dead endpoint |
| Out of scope but adjacent: `UsageLimitError` and `ChatSessionError` 500s | Not in AC1. STORY-010 may add them beside the `/v1` half; not added here so the module matches the story exactly |

---

## Acceptance Criteria

(Copied from story `STORY-001`)

- [ ] Given untouched `main`, when `tests/test_v1_query_isolation.py` runs, then it pins the full status and JSON body of `POST /query` for: no bearer (401), invalid bearer (401), identity without `query:submit` (403), a body failing validation (422: missing `prompt`, and a malformed `session_id`), `DuplicateCheckError` (500), `PiiRedactorError` (500) and `OpenRouterError` (502), and it passes.
- [ ] Given a `/query` success and a `run_conversation` call with all four `GenerationParams` set, when the upstream request is captured with an `httpx.MockTransport`, then the test pins the URL (`https://openrouter.ai/api/v1/chat/completions`) and that the JSON body's keys are exactly `model`, `messages` and the set parameters.
- [ ] Given the new tests, when the whole suite runs, then no existing assertion is changed and the new tests are green without any production change.
- [ ] Given `-m "not db"`, when it runs, then the tests that need no storage still run without Docker, and the ones that do carry the `db` marker.
- [ ] All tasks completed
- [ ] ASCII-only test output
- [ ] Follows existing patterns
