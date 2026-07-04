---
story: STORY-007
prd: PRD-001
slug: openrouter-client
title: OpenRouter API client wrapper
type: feature
complexity: medium
epic_branch: epic/PRD-001-harness-ia
created: 2026-07-04
---

# Plan: OpenRouter API client wrapper

## Summary

Add `app/services/openrouter_client.py`, a thin wrapper around OpenRouter's chat-completion endpoint (`POST https://openrouter.ai/api/v1/chat/completions`). It exposes one plain function, `call_openrouter(prompt, model="gpt-4", api_key=None, client=None) -> OpenRouterResult`, matching the function-based service style already established by `duplicate_checker.py`, `pattern_detector.py`, and `audit_logger.py`. The function resolves the API key (per-request `api_key` argument, falling back to `settings.OPENROUTER_API_KEY`), builds a single-user-message chat-completion request, and returns an `OpenRouterResult` dataclass (`response`, `model_used`, `tokens_used`) ready to feed straight into `QuerySuccessResponse` (STORY-003) and `audit_logger.log_query` (STORY-006). Any resolution failure, network error, non-2xx status, or malformed response body is caught and re-raised as a single typed `OpenRouterError`, following the exact `DuplicateCheckError` convention — never a raw `httpx` exception reaching the caller, and never the API key appearing in an error message. Testability is achieved via an optional `client` parameter (PRD Technical Notes: "Client must be swappable/mockable for tests — no direct HTTP calls inside route handlers") rather than by adding a new mocking dependency — tests inject a fake object exposing `.post(...)` that returns real `httpx.Response` instances built in-memory, so no network call and no new library (e.g. `respx`) is needed. This is the first module in the repo to use `httpx`; no async precedent exists anywhere in the codebase (all services, DB access, and tests are synchronous), so the client uses a synchronous `httpx.Client`, keeping the pipeline sync end-to-end for STORY-008 to consume directly.

## User Story

As an integrating developer
I want a thin client wrapping OpenRouter's chat completion API
So that the harness can forward prompts to any model (Claude, GPT, etc.) OpenRouter supports

## Story Reference

- Story file: `.agents/stories/PRD-001-harness-ia/STORY-007-openrouter-client.md`
- PRD: `.agents/PRDs/PRD-001-harness-ia/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | feature |
| Complexity | medium |
| Systems Affected | `app/services/` (new module in existing package) |
| Story | STORY-007 |
| PRD | PRD-001 |
| Epic Branch | `epic/PRD-001-harness-ia` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` contains no `SKILL.md` files, and the story's `skills: []` frontmatter is empty — same situation as STORY-001 through STORY-006.

---

## Codebase State

`app/config.py:7` already defines `OPENROUTER_API_KEY: str` as a required field on the pydantic `Settings` class (no default), loaded from `.env`/environment at `Settings()` construction time (`app/config.py:16`). Tests override it via `monkeypatch.setattr(settings, "OPENROUTER_API_KEY", ...)`, the same mechanism `tests/test_duplicate_checker.py:42` uses for `DATABASE_URL` — so `call_openrouter` must read `settings.OPENROUTER_API_KEY` at call time (module-level `from app.config import settings`, attribute access inside the function), not capture it at import time.

`app/models/schemas.py:6-19` (STORY-003, done) already defines `QueryRequest.model: str = "gpt-4"` and `QueryRequest.openrouter_api_key: Optional[str] = None`, and `QuerySuccessResponse` expects exactly `response: str`, `model_used: str`, `tokens_used: int` — the three fields `OpenRouterResult` must supply. STORY-008 (router, not yet built) will pass `request.model` and `request.openrouter_api_key` straight through to `call_openrouter`.

`app/services/duplicate_checker.py:12-13` is the only existing custom-exception precedent in the repo: a bare `class DuplicateCheckError(Exception): pass`, raised via `raise DuplicateCheckError(f"...: {exc}") from exc` around a lower-level exception (`sqlite3.Error`). No `app/exceptions.py` module exists. `openrouter_client.py` follows this exact one-exception-per-service-module convention with `OpenRouterError`.

No `httpx` usage exists anywhere in `app/` or `tests/` yet — it's listed in `requirements.txt:5` but unused. This story is the first real usage. No async pattern exists anywhere in the codebase either (`app/main.py`'s route/lifespan functions and every existing service/test are synchronous, and `pytest-asyncio` is a declared-but-unused dependency) — so this plan deliberately uses a synchronous `httpx.Client`, not `httpx.AsyncClient`, to match the codebase's actual (not PRD-suggested) convention.

`app/main.py:16-18` has an explicit comment confirming router wiring is out of scope until STORY-008/010/011: `# Routers are registered here by later stories`. This story only touches `app/services/`.

`requirements.txt` already lists `httpx` (line 5) — no dependency changes needed. No `respx` or other HTTP-mocking library is installed; this plan avoids adding one (see Design Decision 3).

---

## Design Decisions

1. **Synchronous `httpx.Client`, not `httpx.AsyncClient`.** The PRD (Section 8) suggests `httpx.AsyncClient` for tests, but zero code in this repo is async today — every service is a plain sync function, `app/db/database.py` uses sync `sqlite3`, and no test uses `@pytest.mark.asyncio`. Introducing async here would force STORY-008's router and every caller in between to become async too, which is a bigger change than this story's scope. Sync `httpx.Client` keeps `call_openrouter` a drop-in sync function matching `check_duplicate`/`detect_suspicious_pattern`/`log_query`.

2. **One exception class, `OpenRouterError(Exception)`, covers both configuration errors and network/response errors** (mirrors `DuplicateCheckError` — one class per service, message text distinguishes the cause). The story's ACs ask for "a clear configuration error" and "a typed error" separately, but both map onto "the caller can catch one exception type and log `success=false` with `error_message=str(exc)`" — a second exception subclass would be unused complexity relative to what STORY-008 actually needs.

3. **Testability via an injectable `client` parameter, not a new mocking library.** PRD Technical Notes explicitly require the client to be "swappable/mockable for tests." Rather than adding `respx` (not currently a dependency), `call_openrouter(..., client: Optional[httpx.Client] = None)` accepts any object exposing `.post(url, headers=, json=) -> httpx.Response`. When omitted, the function creates and closes its own `httpx.Client`. Tests pass a small fake class and construct real `httpx.Response` objects in-memory (`httpx.Response(status_code, request=..., json=...)`) — this exercises the real `.raise_for_status()`/`.json()` code paths without a network call or a new dependency, consistent with the existing test suite's "monkeypatch only, no mock libraries" convention.

4. **Never interpolate the resolved API key into an error message.** Only `str(exc)` (the underlying `httpx` exception's own string form, which does not include request headers) is included in `OpenRouterError` messages. A dedicated test (`test_api_key_never_appears_in_error_message`) asserts this holds, since the story's Technical Notes explicitly call out not logging full API keys.

5. **Single-turn request body only** — `messages: [{"role": "user", "content": prompt}]`, no system prompt or conversation history. The PRD's `/query` endpoint (Section 10) is single-turn by design; adding multi-turn support now would be scope creep beyond what STORY-007/008 need.

6. **Fixed 30-second request timeout as a module constant**, not a new `Settings` field. No AC or PRD section calls for configurable timeout, and the <500ms NFR (PRD Section 11) is documented elsewhere as harness-overhead budget, not upstream LLM latency — no story currently asks for this to be tunable.

---

## Patterns to Follow

### Service function style (module constant + one exception + plain function)
```python
// SOURCE: app/services/duplicate_checker.py:9-13,22-37
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class DuplicateCheckError(Exception):
    pass


def hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def check_duplicate(prompt: str) -> DuplicateCheckResult:
    ...
    try:
        match = find_duplicate_timestamp(prompt_hash, cutoff)
    except sqlite3.Error as exc:
        raise DuplicateCheckError(f"Duplicate lookup failed: {exc}") from exc
```
`openrouter_client.py` follows the same shape: constants, one exception class, one function that wraps a lower-level exception (`httpx.HTTPError`) into the typed one.

### Result dataclass style
```python
// SOURCE: app/services/duplicate_checker.py:16-19
@dataclass
class DuplicateCheckResult:
    is_duplicate: bool
    first_query_at: Optional[str] = None
```
`OpenRouterResult` mirrors this: a plain `@dataclass` with the exact fields the caller (`QuerySuccessResponse`, `audit_logger.log_query`) needs.

### Settings access (read at call time, mockable via monkeypatch)
```python
// SOURCE: app/config.py:1-16
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    ...
    OPENROUTER_API_KEY: str

settings = Settings()
```
```python
// SOURCE: tests/test_duplicate_checker.py:39-43
@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path
```
Same `monkeypatch.setattr(settings, "OPENROUTER_API_KEY", ...)` pattern is used to test env-var fallback.

### Tests: env-var bootstrap (every test file repeats this before importing `app.config`)
```python
// SOURCE: tests/test_pattern_detector.py:1-4
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
```
`tests/test_openrouter_client.py` opens with the same two lines.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/openrouter_client.py` | CREATE | `OpenRouterError`, `OpenRouterResult`, `call_openrouter(...)` — resolves API key, calls OpenRouter chat completions, returns typed result or raises typed error |
| `tests/test_openrouter_client.py` | CREATE | Unit tests via an injectable fake HTTP client — success, default model, key resolution/override, missing key, network error, non-2xx status, malformed body, key-never-leaked |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create `app/services/openrouter_client.py`

- **File**: `app/services/openrouter_client.py`
- **Action**: CREATE
- **Implement**:
  ```python
  from dataclasses import dataclass
  from typing import Optional

  import httpx

  from app.config import settings

  _API_URL = "https://openrouter.ai/api/v1/chat/completions"
  _DEFAULT_MODEL = "gpt-4"
  _TIMEOUT_SECONDS = 30.0


  class OpenRouterError(Exception):
      pass


  @dataclass
  class OpenRouterResult:
      response: str
      model_used: str
      tokens_used: int


  def call_openrouter(
      prompt: str,
      model: str = _DEFAULT_MODEL,
      api_key: Optional[str] = None,
      client: Optional[httpx.Client] = None,
  ) -> OpenRouterResult:
      resolved_key = api_key or settings.OPENROUTER_API_KEY
      if not resolved_key:
          raise OpenRouterError(
              "OpenRouter API key not configured: pass openrouter_api_key or set OPENROUTER_API_KEY"
          )

      headers = {
          "Authorization": f"Bearer {resolved_key}",
          "Content-Type": "application/json",
      }
      payload = {
          "model": model,
          "messages": [{"role": "user", "content": prompt}],
      }

      owns_client = client is None
      http_client = client or httpx.Client(timeout=_TIMEOUT_SECONDS)
      try:
          try:
              resp = http_client.post(_API_URL, headers=headers, json=payload)
              resp.raise_for_status()
          except httpx.HTTPError as exc:
              raise OpenRouterError(f"OpenRouter request failed: {exc}") from exc

          try:
              data = resp.json()
              content = data["choices"][0]["message"]["content"]
              tokens_used = data["usage"]["total_tokens"]
          except (KeyError, IndexError, ValueError) as exc:
              raise OpenRouterError(
                  f"OpenRouter returned an unexpected response shape: {exc}"
              ) from exc
      finally:
          if owns_client:
              http_client.close()

      return OpenRouterResult(response=content, model_used=model, tokens_used=tokens_used)
  ```
- **Mirror**: `app/services/duplicate_checker.py:1-23` (imports, module constants, exception class, plain-function style); `app/config.py:7,16` (`settings.OPENROUTER_API_KEY` read contract).
- **Validate**: `python -c "from app.services.openrouter_client import call_openrouter"` succeeds.

### Task 2: Create `tests/test_openrouter_client.py`

- **File**: `tests/test_openrouter_client.py`
- **Action**: CREATE
- **Implement**: Env-var bootstrap (mirror `tests/test_pattern_detector.py:1-4`). A `_FakeClient` test double with a `.post(url, headers=None, json=None)` method that records the call and either returns a pre-built `httpx.Response` or raises a pre-set exception. A `_success_response(content, tokens, status_code)` helper building `httpx.Response(status_code, request=httpx.Request("POST", _API_URL), json={"choices": [{"message": {"content": content}}], "usage": {"total_tokens": tokens}})`. Tests:
  1. `test_success_returns_response_model_and_tokens` — fake client returns a 200 with `content="Hello!"`, `tokens=45`; assert `result.response == "Hello!"`, `result.model_used == "gpt-4"`, `result.tokens_used == 45` (AC 1).
  2. `test_default_model_used_when_omitted` — call without `model=`; assert `result.model_used == "gpt-4"` and the fake client's recorded request body has `"model": "gpt-4"` (AC 2).
  3. `test_per_request_api_key_overrides_env` — `monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "env-key")`, call with `api_key="explicit-key"`; assert recorded `Authorization` header is `"Bearer explicit-key"` (AC 3).
  4. `test_falls_back_to_env_key_when_not_provided` — same monkeypatch, call without `api_key`; assert recorded `Authorization` header is `"Bearer env-key"` (AC 3).
  5. `test_missing_key_raises_config_error` — `monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")`, call without `api_key`; assert `pytest.raises(OpenRouterError, match="not configured")` (AC 3).
  6. `test_network_error_raises_openrouter_error` — fake client raises `httpx.ConnectTimeout("timed out")`; assert `pytest.raises(OpenRouterError)`, not the raw `httpx` exception (AC 4).
  7. `test_non_2xx_status_raises_openrouter_error` — fake client returns a 500 response; assert `pytest.raises(OpenRouterError)` (AC 4).
  8. `test_malformed_response_body_raises_openrouter_error` — fake client returns a 200 with an unexpected JSON shape (e.g. `{"unexpected": "shape"}`); assert `pytest.raises(OpenRouterError)`.
  9. `test_api_key_never_appears_in_error_message` — fake client raises `httpx.ConnectTimeout`, call with `api_key="super-secret-key"`; assert the raised exception's `str(...)` does not contain `"super-secret-key"`.
- **Mirror**: `tests/test_pattern_detector.py:1-11` (env bootstrap + import style); `tests/test_duplicate_checker.py:115-117` (`pytest.raises(<TypedError>)` assertion style).
- **Validate**: `pytest tests/test_openrouter_client.py -v` — all 9 tests pass.

---

## End-to-End Tests

- [ ] Call `call_openrouter` with a fake client simulating a real OpenRouter success payload → returns `response`, `model_used`, `tokens_used` matching the payload (AC 1)
- [ ] Call `call_openrouter` without `model` → defaults to `"gpt-4"` (AC 2)
- [ ] Call with a per-request `openrouter_api_key` → that key is used over the env var; call with neither set → raises `OpenRouterError` with a clear configuration message (AC 3)
- [ ] Simulate a timeout and a non-2xx OpenRouter response → both raise `OpenRouterError`, never a raw `httpx` exception (AC 4)
- [ ] `pytest tests/ -v` (full existing suite + new file) passes green

---

## Validation

```bash
pytest tests/test_openrouter_client.py -v
pytest tests/ -v
python -c "from app.services.openrouter_client import call_openrouter"
```

---

## Acceptance Criteria

(Copied from story STORY-007)

- [ ] Given a prompt and a model name, when the client calls OpenRouter, then it returns the model's text response and token usage.
- [ ] Given no `model` is specified upstream, when the client is invoked, then it defaults to `"gpt-4"` per PRD Section 10.
- [ ] Given a per-request `openrouter_api_key` is provided, when the client calls OpenRouter, then it uses that key instead of the `OPENROUTER_API_KEY` env var; given neither is provided, then it raises a clear configuration error.
- [ ] Given OpenRouter returns an error or times out, when the client is invoked, then it surfaces a typed error (not a raw exception) so the caller can log `success=false` with an `error_message`.
- [ ] All tasks completed
- [ ] Frontend lint passes — N/A, no frontend in this MVP; substitute `pytest tests/ -v` passes
- [ ] Backend server starts without error
- [ ] Follows existing patterns (function-based service, one exception class per module, injectable client for testability)
