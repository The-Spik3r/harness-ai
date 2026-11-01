---
story: STORY-012
prd: PRD-015
slug: v1-models
title: "GET /v1/models and /v1/models/{id} from MODEL_ALLOWLIST"
type: NEW_CAPABILITY
complexity: LOW
epic_branch: epic/PRD-015-openai-compatible-endpoint
created: 2026-10-25
---

# Plan: GET /v1/models and /v1/models/{id} from MODEL_ALLOWLIST

## Summary

Add two read-only routes to `app/routers/v1.py`: `GET /v1/models` returns a
`ModelList` built from `settings.model_allowlist_list` (read per request, in
configured order), and `GET /v1/models/{model_id:path}` returns one
`ModelEntry` or a 404 `model_not_found`. Both use the same
`require_permission(PERMISSION_QUERY_SUBMIT)` dependency as
`chat_completions`, so the 401/403 shape refusals already come from the
STORY-010 handlers. The one new refusal is break-glass: no pipeline runs here,
so the router refuses `identity.break_glass` itself with a 403
`break_glass_not_permitted` and writes no row (PRD Section 7.2). The schemas
(`ModelEntry`, `ModelList`) and the error builder (`_error`) already exist;
this story only wires them up. Nothing is audited (Section 7.7).

## User Story

As an integrating developer
I want my client to discover the models I may use
So that its model picker shows only names the harness will accept

## Story Reference

- Story file: `.agents/stories/PRD-015-openai-compatible-endpoint/STORY-012-v1-models.md`
- PRD: `.agents/PRDs/PRD-015-openai-compatible-endpoint/PRD.md` (Sections 7.2, 7.5, 7.7, 10, D4)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | LOW |
| Systems Affected | `/v1` router, tests |
| Story | STORY-012 |
| PRD | PRD-015 |
| Epic Branch | `epic/PRD-015-openai-compatible-endpoint` (commit directly on this branch) |

Dependencies STORY-004, STORY-009, STORY-010 are all `done`.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` has only `frontend-design`; this story is backend-only. Story frontmatter `skills: []`. | — |

---

## Patterns to Follow

### Schemas (already exist, STORY-004)
```python
# SOURCE: app/models/v1_schemas.py:175-186
class ModelEntry(BaseModel):
    """One `GET /v1/models` entry (Section 7.7). `created` is unknown, so `0`."""
    id: str
    object: Literal["model"] = "model"
    created: int = 0
    owned_by: str

class ModelList(BaseModel):
    object: Literal["list"] = "list"
    data: List[ModelEntry]
```

### Route + dependency + JSONResponse
```python
# SOURCE: app/routers/v1.py:171-176, 224-227
@router.post("/v1/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    x_harness_device: Optional[str] = Header(default=None, alias=DEVICE_HEADER),
    identity: Identity = Depends(require_permission(PERMISSION_QUERY_SUBMIT)),
) -> Any:
    ...
    return JSONResponse(completion.model_dump(mode="json"), headers=...)
```

### Error Handling
```python
# SOURCE: app/routers/v1.py:112-132 -- the one place a /v1 error body is built;
# every 4xx gets x-should-retry: false automatically.
def _error(status_code, type_, code, message, param=None, headers=None, harness=None) -> JSONResponse: ...

# SOURCE: app/routers/v1.py:183-184 -- refusal log: who and which rule, never content
logger.info("v1 request refused: user_id=%s code=%s", identity.user_id, exc.code)
```
Codes come from `app/services/v1_translate.py:55-74` (`BREAK_GLASS_NOT_PERMITTED`
exists; `model_not_found` does not yet — add `MODEL_NOT_FOUND` beside them).

The pipeline's break-glass refusal message, which the router's own refusal
should match so a client sees one text for one rule:
`"Break-glass credential not permitted on this ingress: ingress:break_glass"`
(pinned in `tests/test_v1_errors.py:254-273`). `harness` is `null` here: no
pipeline response exists (`ErrorDetail` docstring, `v1_schemas.py:199-213`).

### Allowlist (read per request)
```python
# SOURCE: app/config.py:651-653 -- a property over the MODEL_ALLOWLIST string
@property
def model_allowlist_list(self) -> list[str]:
    return [item.strip() for item in self.MODEL_ALLOWLIST.split(",") if item.strip()]
# Tests: monkeypatch.setattr(settings, "MODEL_ALLOWLIST", "...")  (tests/test_config.py:31-34)
```
Default: `gpt-4,claude-3-sonnet,openai/gpt-4o,anthropic/claude-3.5-sonnet` (`app/config.py:204`).

### Tests
```python
# SOURCE: tests/test_v1_errors.py:28-133
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
client = TestClient(app, headers=_AUTH_HEADERS)

@pytest.fixture
def temp_db(temp_db):
    insert_user(User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN)))
    return temp_db

def _count_audit_rows() -> int: ...
def _error(status_code, type_, code, message, harness=None, param=None): ...
def _assert_response(response, expected): ...   # status + whole body + x-should-retry: false

# 401 without storage: tests/test_v1_errors.py:364-368 (no temp_db)
# 403 via an `auditor` user: tests/test_v1_errors.py:378-389
# ADMIN_TOKEN client: tests/test_v1_errors.py:256
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/v1_translate.py` | UPDATE | Add the `MODEL_NOT_FOUND = "model_not_found"` code constant beside the Section 7.5 codes |
| `app/routers/v1.py` | UPDATE | `_model_entry`, `_refuse_break_glass`, `GET /v1/models`, `GET /v1/models/{model_id:path}`; docstring update |
| `tests/test_v1_models.py` | CREATE | The four ACs over HTTP |

---

## Tasks

`$PY` = `C:/Users/tobip/.venvs/harness-ai/Scripts/python.exe`. DB-backed tests need
the libsql dev container (see test-env notes).

### Task 1: `MODEL_NOT_FOUND` code

- **File**: `app/services/v1_translate.py`
- **Action**: UPDATE
- **Implement**: Add `MODEL_NOT_FOUND = "model_not_found"` next to
  `INVALID_API_KEY` (lines ~72-73), commented as the `GET /v1/models/{id}`
  404 (router). Pure constant; module purity is unchanged.
- **Mirror**: `app/services/v1_translate.py:71-73` (`INVALID_API_KEY` with its "(router handler)" comment)
- **Validate**: `$PY -m pytest tests/test_v1_translate_request.py -q -m "not db"` (purity test still passes)

### Task 2: Entry builder and break-glass refusal

- **File**: `app/routers/v1.py`
- **Action**: UPDATE
- **Implement**:
  - Import `ModelEntry`, `ModelList` from `app.models.v1_schemas`;
    `BREAK_GLASS_NOT_PERMITTED`, `MODEL_NOT_FOUND` from `v1_translate`;
    `settings` from `app.config`.
  - `_model_entry(model_id: str) -> ModelEntry`: `owned_by` is the prefix
    before the first `/` when there is one and it is non-empty, else
    `"harness"` (`prefix, sep, _ = model_id.partition("/")`).
  - `_refuse_break_glass(identity) -> Optional[JSONResponse]`: when
    `identity.break_glass`, log `v1 request refused: user_id=%s code=%s` with
    `BREAK_GLASS_NOT_PERMITTED` and return
    `_error(403, "permission_error", BREAK_GLASS_NOT_PERMITTED,
    "Break-glass credential not permitted on this ingress: ingress:break_glass")`.
    Docstring: router-level because no pipeline runs (Section 7.2); only
    `resolve(ADMIN_TOKEN)` sets the flag, so an `admin`-role user token passes;
    no row is written. Do NOT consult `settings.break_glass_ingresses` — its
    validator forbids `v1` (PRD-013), so the answer is always "refuse".
- **Mirror**: `app/routers/v1.py:112-132` (`_error`), `:183-184` (log line)
- **Validate**: `$PY -c "import app.routers.v1"` from repo root with `PYTHONPATH=.`

### Task 3: The two routes

- **File**: `app/routers/v1.py`
- **Action**: UPDATE
- **Implement**: Place after `chat_completions`, before the exception-handler section.
  ```python
  @router.get("/v1/models")
  async def list_models(identity: Identity = Depends(require_permission(PERMISSION_QUERY_SUBMIT))) -> Any:
      refusal = _refuse_break_glass(identity)
      if refusal is not None:
          return refusal
      # Read per request (tests monkeypatch it). An admin may send any model, but
      # "any" cannot be listed, so every role sees the configured entries (Section 7.7).
      models = ModelList(data=[_model_entry(m) for m in settings.model_allowlist_list])
      return JSONResponse(models.model_dump(mode="json"))

  @router.get("/v1/models/{model_id:path}")
  async def retrieve_model(model_id: str, identity: ... same dependency) -> Any:
      refusal = ...
      if model_id not in settings.model_allowlist_list:   # exact match, no aliasing (D4)
          logger.info("v1 request refused: user_id=%s code=%s", identity.user_id, MODEL_NOT_FOUND)
          return _error(404, "invalid_request_error", MODEL_NOT_FOUND, "model not in MODEL_ALLOWLIST")
      return JSONResponse(_model_entry(model_id).model_dump(mode="json"))
  ```
  - `{model_id:path}` because ids contain `/`; Starlette matches on the
    decoded path, so `openai%2Fgpt-4o` and `openai/gpt-4o` both arrive as
    `openai/gpt-4o`.
  - The 404 message names the rule, never the requested id (T6 habit: no
    echo of caller input). The id is not logged either.
  - No `run_in_pipeline`, no audit call: Section 7.7, not audited.
  - Update the module docstring: replace "STORY-012 adds `/v1/models`" with a
    sentence saying `/v1/models` lists `MODEL_ALLOWLIST`, refuses break-glass
    itself and writes no row. Update the `_HTTP_ERRORS` comment: 404 there is
    routing; `model_not_found` is the route's own `_error`.
- **Mirror**: `app/routers/v1.py:171-227`
- **Validate**: `$PY -m pytest tests/test_v1_router.py tests/test_v1_errors.py tests/test_v1_query_isolation.py -q` (unchanged suites still green; `test_wrong_method_is_405...` and `test_unknown_v1_path_is_404...` use other paths, unaffected)

### Task 4: Tests

- **File**: `tests/test_v1_models.py`
- **Action**: CREATE
- **Implement**: Module docstring naming STORY-012 and Sections 7.2/7.7.
  Copy the header pattern of `tests/test_v1_errors.py` (env defaults,
  `temp_db` override inserting a `user`, `_count_audit_rows`, `_error`,
  `_assert_response`). Tests:
  1. `test_list_is_allowlist_in_order` (AC1) — default allowlist; assert the
     whole body: 4 entries in config order, `owned_by` `harness`, `harness`,
     `openai`, `anthropic`, `created: 0`, `object: "model"`; top-level
     `object: "list"`; `_count_audit_rows() == 0`.
  2. `test_list_reads_allowlist_per_request` — `monkeypatch.setattr(settings,
     "MODEL_ALLOWLIST", "z/last,a-first,m/mid")` → that order, unsorted.
  3. `test_admin_role_user_sees_same_entries` (AC2) — insert an `admin`-role
     user with its own token; body equals the `user`-role body.
  4. `test_retrieve_encoded_and_unencoded` (AC3) — parametrize
     `/v1/models/openai%2Fgpt-4o` and `/v1/models/openai/gpt-4o` → 200
     `{"id": "openai/gpt-4o", "object": "model", "created": 0, "owned_by": "openai"}`.
     Also `/v1/models/gpt-4` → `owned_by: "harness"`.
  5. `test_retrieve_unknown_is_404_model_not_found` (AC3) — parametrize an
     unknown name and a near-miss (`openai/gpt-4o-mini`, `OPENAI/GPT-4O`: exact
     match, D4); `_assert_response` 404 `invalid_request_error`
     `model_not_found`, `harness: null`, `x-should-retry: false`; the id does
     not appear in `response.text`.
  6. `test_admin_token_is_403_break_glass_not_permitted_without_row` (AC4) —
     parametrize both paths; ADMIN_TOKEN client; whole error body;
     `_count_audit_rows() == 0`.
  7. `test_no_bearer_is_401_invalid_api_key` (AC4) — both paths, no `temp_db`
     (resolve(None) reaches no storage); message `"Invalid or missing credential"`.
  8. `test_auditor_is_403_permission_denied` (AC4) — both paths, `auditor`
     user; message `"Permission denied: query:submit"`; no rows.
  9. `test_post_to_models_is_405` — `client.post("/v1/models")` → 405
     `method_not_allowed`, `allow: GET` (routing via the STORY-010 handler).
- **Mirror**: `tests/test_v1_errors.py:254-273, 364-389, 440-455`
- **Validate**: `$PY -m pytest tests/test_v1_models.py -q`

---

## Risks

| Risk | Mitigation |
|------|-----------|
| `%2F` is not decoded by the TestClient/uvicorn stack, so the encoded form 404s via routing | Test 4 covers it in-process; the E2E check below covers real uvicorn. If uvicorn keeps `%2F` raw, `{model_id:path}` still matches `openai%2Fgpt-4o` as one segment — then `unquote(model_id)` in the route. Decide from the test, don't pre-emptively unquote (double-decoding `%252F` would be wrong). |
| `{model_id:path}` matches empty (`/v1/models/`) | Empty id is not in the list → 404 `model_not_found`; acceptable, no special case. |
| Break-glass check placed before the dependency | It must run after `require_permission`, so a missing bearer is still 401 and an auditor still 403. The check lives in the route body. |
| A DB-less test reaching storage fails the "reached storage without declaring it" guard | Only the no-bearer test omits `temp_db`; every other test takes it. |

---

## End-to-End Tests

- [ ] Start the app against the dev DB (`V1_ENABLED=true`), create a `user`
      token with `scripts/manage_users.py create-user`, then
      `curl -s -H "Authorization: Bearer $T" http://127.0.0.1:8000/v1/models` → 200 list in config order.
- [ ] `curl .../v1/models/openai%2Fgpt-4o` and `.../v1/models/openai/gpt-4o` → 200 entry (real uvicorn decoding).
- [ ] `curl -i .../v1/models/nope` → 404 `model_not_found`, `x-should-retry: false`.
- [ ] `curl -i -H "Authorization: Bearer $ADMIN_TOKEN" .../v1/models` → 403 `break_glass_not_permitted`.
- [ ] OpenAI Python SDK (in venv): `OpenAI(base_url=".../v1", api_key=T).models.list()` yields the ids;
      `.models.retrieve("openai/gpt-4o")` returns the entry (SDK path-encodes the slash).
- [ ] `GET /audit` (admin) shows no new rows after the above.

---

## Validation

```bash
PY=C:/Users/tobip/.venvs/harness-ai/Scripts/python.exe
$PY -m pytest tests/test_v1_models.py -q
$PY -m pytest tests/test_v1_errors.py tests/test_v1_router.py tests/test_v1_query_isolation.py tests/test_v1_translate_request.py -q
$PY -m pytest tests/ -q -m "not db"
```

---

## Acceptance Criteria

(Copied from story `STORY-012`)

- [ ] Given a `user`-role token and the default `MODEL_ALLOWLIST`, when `GET /v1/models` is sent, then 200 with `object: "list"` and one entry per allowlisted model in configured order, each `{"id", "object": "model", "created": 0, "owned_by"}` with `owned_by` the prefix before `/` or `harness`.
- [ ] Given an `admin`-role user token, when the list is requested, then it returns the same entries (the wildcard cannot be enumerated; documented in STORY-019).
- [ ] Given `GET /v1/models/openai%2Fgpt-4o` (and the unencoded `/v1/models/openai/gpt-4o`), when sent, then 200 with that entry; given a name not in the list, then 404 `model_not_found` with `x-should-retry: false`.
- [ ] Given `ADMIN_TOKEN`, no bearer, or an identity without `query:submit`, when either route is called, then 403 `break_glass_not_permitted`, 401 `invalid_api_key` or 403 `permission_denied` respectively, in the error shape; no route writes an audit row.
- [ ] All tasks completed
- [ ] Backend tests pass
- [ ] Follows existing patterns
