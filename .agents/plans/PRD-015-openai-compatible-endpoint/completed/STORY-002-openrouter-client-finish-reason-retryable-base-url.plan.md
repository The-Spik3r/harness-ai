---
story: STORY-002
prd: PRD-015
slug: openrouter-client-finish-reason-retryable-base-url
title: "OpenRouter client: finish_reason, upstream_status and retryable, OPENROUTER_BASE_URL"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-015-openai-compatible-endpoint
created: 2026-10-21
---

# Plan: OpenRouter client: finish_reason, upstream_status and retryable, OPENROUTER_BASE_URL

## Summary

Three additive changes to the upstream client, plus one setting. First, `OpenRouterResult` gets a sixth field, `finish_reason: Optional[str] = None`, declared after `output_tokens`. It is read from `choices[0].finish_reason` and is `None` when that value is absent or not a string. Second, `OpenRouterError` gets keyword-only `upstream_status` and `retryable` attributes. The single `except httpx.HTTPError` arm is split three ways: `HTTPStatusError` carries its status and is retryable for 5xx and 429; `TransportError`, which includes timeouts and connect errors, is retryable with no status; and any other `HTTPError` is not retryable. Every message string stays byte-identical. Third, `_API_URL` goes away. The request URL becomes `f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"`, read per call. The new setting defaults to `https://openrouter.ai/api/v1` and has a startup validator: `https://` with a host, or `http://` only when the host is `127.0.0.1`, `localhost` or `::1`. No caller of `call_openrouter` changes, and nobody reads the new fields yet. STORY-009 and STORY-011 are their consumers.

## User Story

As the `/v1` implementer
I want the upstream client to report why a completion stopped and whether a failure is worth retrying, and to accept a configurable base URL
So that success and fault translation have the facts they need and E2E runs can use a local stub

## Story Reference

- Story file: `.agents/stories/PRD-015-openai-compatible-endpoint/STORY-002-openrouter-client-finish-reason-retryable-base-url.md`
- PRD: `.agents/PRDs/PRD-015-openai-compatible-endpoint/PRD.md` (Sections 4 "Upstream client", 7.4, 7.5, 9.2 T10, 9.3, 15 D7 / D10)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (additive; no caller changes) |
| Complexity | MEDIUM |
| Systems Affected | `app/services/openrouter_client.py`, `app/config.py`, tests |
| Story | STORY-002 |
| PRD | PRD-015 |
| Epic Branch | `epic/PRD-015-openai-compatible-endpoint` (commit directly on this branch) |
| Depends on | STORY-001 (✅ done, `0341ed6`) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` holds only `frontend-design`; this story is backend-only. The story says "Skills: none applicable". | — |

---

## Patterns to Follow

### Optional result field, declared last with a default
```python
# SOURCE: app/services/openrouter_client.py:93-102
@dataclass
class OpenRouterResult:
    response: str
    model_used: str
    tokens_used: int
    # PRD-013 STORY-003: usage.prompt_tokens and usage.completion_tokens, None
    # when the provider omitted or malformed the field. Declared after
    # tokens_used with defaults so three-argument construction keeps working.
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
```

### Lenient read of an optional provider field
```python
# SOURCE: app/services/openrouter_client.py:84-89
def _token_count(value: Any) -> Optional[int]:
    """A provider-reported token count, or None when it is not usable (PRD-013 F3)."""
    # bool is a subclass of int: True/False must not be recorded as 1/0.
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value
```

### Settings read per call, not at import
```python
# SOURCE: app/services/openrouter_client.py:134-135 (the timeout precedent)
owns_client = client is None
http_client = client or httpx.Client(timeout=settings.OPENROUTER_TIMEOUT_SECONDS)
```
`app/services/query_pipeline.py:78` (`_context_limit_exceeded`) is the documented reason. Tests use `monkeypatch.setattr(settings, ...)`, so a value captured at import would ignore them.

### URL validator: strip, quote the scheme only, name the rule
```python
# SOURCE: app/config.py:357-379
@field_validator("DATABASE_URL")
@classmethod
def _validate_database_url(cls, value: str) -> str:
    """A libSQL endpoint, or a startup error -- never a file (PRD-007)."""
    url = value.strip()
    scheme = _scheme_of(url).lower()
    ...
    if scheme not in _REMOTE_SCHEMES + (_LOCAL_SCHEME,):
        raise ValueError(
            f"Unsupported DATABASE_URL scheme: {scheme!r}. Expected one of: "
            "libsql://, https://, http:// (local dev server only)."
        )
    return url
```
Module constants sit above `Settings`, each with its rule in a comment (`_REMOTE_SCHEMES`, `_BREAK_GLASS_ACCEPTED` at `app/config.py:7-12, 74-77`).

### Error handling (today's single arm, to be split)
```python
# SOURCE: app/services/openrouter_client.py:137-142
try:
    resp = http_client.post(_API_URL, headers=headers, json=payload)
    resp.raise_for_status()
except httpx.HTTPError as exc:
    raise OpenRouterError(f"OpenRouter request failed: {exc}") from exc
```

### Tests: client
```python
# SOURCE: tests/test_openrouter_client.py:24-44
class _FakeClient:
    def __init__(self, response=None, exc=None): ...
    def post(self, url, headers=None, json=None):
        self.requests.append({"url": url, "headers": headers, "json": json})
        if self._exc:
            raise self._exc
        return self._response

def _response(content="Hello!", tokens=45, status_code=200, body=None): ...
```
New sections use the `# --- PRD-015 STORY-002: ... ---` header (see `:283`, `:367`), and parametrized cases get `pytest.param(..., id=...)` (see `_UNUSABLE_COUNTS`, `:375-384`).

### Tests: config
```python
# SOURCE: tests/test_config.py:95-97
def _settings(**overrides) -> Settings:
    base = {"OPENROUTER_API_KEY": "test-key", "ADMIN_TOKEN": "test-token"}
    return Settings(_env_file=None, **{**base, **overrides})
```
Rejections are asserted with `pytest.raises(ValidationError)` plus substring checks on `str(exc_info.value)` (`:125-136`, `:194-200`).

---

## Design decisions

1. **`OpenRouterError` signature.** `__init__(self, message, *, upstream_status=None, retryable=False)` calls `super().__init__(message)`. That keeps `str(exc)` and `exc.args == (message,)` unchanged. It matters because 29 test sites build `OpenRouterError("...")` positionally, and `/query`'s 502 `detail` and the audit `error_message` both use `str(exc)` (`app/routers/query.py:40`, `app/services/query_pipeline.py:656`). The defaults (`None`, `False`) are the conservative reading: an error nobody classified is not retried.

2. **Classification table.** It lives in one private helper, `_classify_http_error(exc) -> tuple[Optional[int], bool]`, so the rule is written once:

   | Exception | `upstream_status` | `retryable` |
   |---|---|---|
   | `httpx.HTTPStatusError`, status ≥ 500 | status | `True` |
   | `httpx.HTTPStatusError`, status 429 | 429 | `True` |
   | `httpx.HTTPStatusError`, any other status (4xx, and 1xx/3xx, which `raise_for_status` also raises for) | status | `False` |
   | `httpx.TransportError` (covers `TimeoutException`, `ConnectError`, the other `NetworkError`s, `ProtocolError`, `ProxyError`) | `None` | `True` |
   | any other `httpx.HTTPError` (`DecodingError`, `TooManyRedirects`, ...) | `None` | `False` |

   The story names `TransportError`, so the plan uses it. `UnsupportedProtocol` is also a `TransportError`, but it cannot occur once the validator restricts the scheme to `http`/`https`. Do not add a carve-out for it.

   Shape failures, null content, missing key and empty messages keep `(None, False)`. Pass the defaults explicitly only where it helps the reader. In practice, leave those four `raise` sites unchanged.

3. **`finish_reason` read.** On the success path, after `content is None` has been ruled out: `finish_reason = raw if isinstance(raw := choice.get("finish_reason"), str) else None`, or the two-line equivalent without the walrus, to match the module's style. Values are not checked against an allowlist. `stop`/`length`/`content_filter` pass through, and any other string passes through unchanged. Mapping a missing value to `"stop"` is STORY-009's job (PRD 7.4), not the client's. The null-content arm keeps its existing `choice.get("finish_reason")` for the message; its text must not move.

4. **URL composition.** `_DEFAULT_BASE_URL` is not added to the client; the default lives only in `Settings`. Delete `_API_URL` from `app/services/openrouter_client.py` and add a tiny `_chat_completions_url()` helper (or an inline expression) that reads `settings.OPENROUTER_BASE_URL` on every call. `rstrip('/')` makes `http://127.0.0.1:9100/v1/` and `.../v1` equivalent.

5. **Validator rule.** Use `urllib.parse.urlsplit` on the stripped value:
   - empty after strip → reject (the message says it is empty)
   - scheme `https` (case-insensitive) and a non-empty `hostname` → accept
   - scheme `http` and `hostname` in `{"127.0.0.1", "localhost", "::1"}` → accept (`urlsplit("http://[::1]:9100/v1").hostname == "::1"`, and `hostname` is lowercased)
   - otherwise reject.

   Every message names `OPENROUTER_BASE_URL`, states the rule ("`https://`, or `http://` only on 127.0.0.1, localhost or ::1"), and gives two examples: `https://openrouter.ai/api/v1` and `http://127.0.0.1:9100/v1`. A message quotes the **scheme** (via `_scheme_of`) and, for the http-on-non-loopback case, the **hostname**. It never quotes the full value: a URL may carry userinfo, and `_scheme_of`'s docstring sets that rule for this module. Return the stripped value, as `_validate_database_url` does.

   The docstring cites PRD-015 Section 9.2 T10: this validator is the mitigation for a setting that could redirect the OpenRouter key to another host.

6. **Setting-description map.** `_POSITIVE_LIMIT_DESCRIPTIONS` covers only the positive-limit settings, not every setting, so per the story's conditional the new field is **not** added to it. `.env.example` is STORY-019's. No existing test requires every `Settings` field to appear there: the `.env.example` order tests filter to their own var groups.

7. **The manual slow smoke.** `tests/test_pipeline_concurrency.py:610-613` does `monkeypatch.setattr("app.services.openrouter_client._API_URL", ...)`. With the constant gone, that string-target `setattr` raises `AttributeError` (`raising=True` by default). The test is `skipif(not HARNESS_SLOW_SMOKE)`, so CI and the full suite stay green, but the manual run would break. **Update it** to `monkeypatch.setattr(settings, "OPENROUTER_BASE_URL", f"http://127.0.0.1:{port}/v1")`. `_SlowHandler` answers any path, so `/v1/chat/completions` is served. This is the one edit to an existing test. It is a mechanical consequence of the story's own technical note ("replace `_API_URL`"), not a behaviour change. Record it in the report as an explicit deviation from AC 5's "without change". The alternative, keeping a dead `_API_URL` constant that nothing reads, would make the smoke pass while silently hitting the real OpenRouter, which is worse.

   Other `_API_URL` hits are **test-local** constants (`tests/test_openrouter_client.py:21`, `tests/test_audit_characterization.py:620`, and `tests/test_v1_query_isolation.py:55`, which imports the test module's constant) and are unaffected.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/config.py` | UPDATE | `OPENROUTER_BASE_URL` field (beside `OPENROUTER_TIMEOUT_SECONDS`), loopback-host constant, `_validate_openrouter_base_url` |
| `app/services/openrouter_client.py` | UPDATE | `OpenRouterError` attributes; split the `HTTPError` arm; `finish_reason` on `OpenRouterResult`; per-call URL from settings; delete `_API_URL` |
| `tests/test_config.py` | UPDATE | New `# --- PRD-015 STORY-002 ---` section: default, accepted URLs, rejected URLs, message content, no full-value echo |
| `tests/test_openrouter_client.py` | UPDATE | New section: `finish_reason`, `upstream_status`/`retryable` per failure, unchanged messages, base URL per call, field order |
| `tests/test_pipeline_concurrency.py` | UPDATE | Manual smoke: patch `settings.OPENROUTER_BASE_URL` instead of the deleted `_API_URL` (decision 7) |

---

## Tasks

Execute in order. Each task is atomic and verifiable. Run the venv and the `-m "not db"` suite as the memory notes say (Windows, Git Bash `PYTHONPATH`).

### Task 1: `OPENROUTER_BASE_URL` setting and validator

- **File**: `app/config.py`
- **Action**: UPDATE
- **Implement**:
  - Above `Settings`, beside `_BREAK_GLASS_ACCEPTED`: add `_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})`, with a comment citing PRD-015 Section 9.3 and T10 ("plaintext only where the key cannot leave the machine").
  - `from urllib.parse import urlsplit`.
  - Field directly after `OPENROUTER_TIMEOUT_SECONDS`, in the same comment style: `OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"`. The comment says that `/chat/completions` is appended, that the value is read per call by `call_openrouter`, that it exists so E2E runs can use a local stub (STORY-014), and that it is operator-only.
  - `_validate_openrouter_base_url` per design decision 5, placed after `_validate_openrouter_timeout_seconds`. The docstring names T10.
- **Mirror**: `app/config.py:357-379` (`_validate_database_url`), `app/config.py:84-97` (`_scheme_of`)
- **Validate**: `python -c "from app.config import settings; print(settings.OPENROUTER_BASE_URL)"` prints the default (with `OPENROUTER_API_KEY`, `ADMIN_TOKEN` and `DATABASE_URL` set as in the memory's env recipe).

### Task 2: Config tests

- **File**: `tests/test_config.py`
- **Action**: UPDATE (append a section at the end)
- **Implement** (all via `_settings(DATABASE_URL=_LOCAL_URL, ...)`):
  - default is `https://openrouter.ai/api/v1`
  - accepted (parametrized with ids): `https://openrouter.ai/api/v1`, `HTTPS://openrouter.ai/api/v1`, `https://proxy.internal.example/v1`, `http://127.0.0.1:9100/v1`, `http://localhost:9100/v1`, `http://[::1]:9100/v1`, `http://LOCALHOST:9100/v1`, a trailing `/`; surrounding whitespace is stripped
  - rejected (parametrized): `http://example.com/v1`, `http://127.0.0.2/v1`, `http://localhost.example.com/v1`, `ftp://127.0.0.1/v1`, `""`, `"   "`, `"openrouter.ai/api/v1"` (no scheme), `"https://"` (no host)
  - every rejection's message contains `OPENROUTER_BASE_URL`, `https`, `127.0.0.1`, `localhost`, `::1` and `Example`. This covers AC 4's "names the setting, the rule and an example".
  - no message echoes a sentinel embedded as userinfo or in the path, e.g. `http://user:s3cr3t-sentinel@example.com/v1`. Reuse `_TOKEN_SENTINEL`.
- **Mirror**: `tests/test_config.py:120-218`
- **Validate**: `pytest -q tests/test_config.py -k "openrouter_base_url or OPENROUTER_BASE_URL"`

### Task 3: `OpenRouterError` attributes and failure classification

- **File**: `app/services/openrouter_client.py`
- **Action**: UPDATE
- **Implement**:
  - `OpenRouterError` gets a docstring (what the two attributes mean, and that D7 / STORY-011 is the consumer) and `__init__(self, message: str, *, upstream_status: Optional[int] = None, retryable: bool = False)`, which calls `super().__init__(message)` and sets both attributes.
  - `_classify_http_error(exc: httpx.HTTPError) -> tuple[Optional[int], bool]` per the table in design decision 2. Check `HTTPStatusError` first, then `TransportError`.
  - In the request arm: `except httpx.HTTPError as exc:` → `status, retryable = _classify_http_error(exc)` → `raise OpenRouterError(f"OpenRouter request failed: {exc}", upstream_status=status, retryable=retryable) from exc`. The message expression stays exactly as it is.
- **Mirror**: `_token_count` (`:84-89`) for a small private helper with a one-line docstring
- **Validate**: `pytest -q tests/test_openrouter_client.py` (all existing tests are still green)

### Task 4: `finish_reason` and the per-call URL

- **File**: `app/services/openrouter_client.py`
- **Action**: UPDATE
- **Implement**:
  - `OpenRouterResult`: append `finish_reason: Optional[str] = None` after `output_tokens`, with a `# PRD-015 STORY-002:` comment in the style of the existing one.
  - Success path: read `finish_reason` per design decision 3 inside the existing `try` that holds `choice`. It is never a reason to fail, and has no new exception path. Pass it into the `OpenRouterResult(...)` return.
  - Delete `_API_URL` and post to `f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"`, computed inside `call_openrouter`. Add a one-line comment pointing at the per-call reason (`_context_limit_exceeded`).
- **Mirror**: `app/services/openrouter_client.py:93-102`, `:167-169`
- **Validate**: `pytest -q tests/test_openrouter_client.py tests/test_v1_query_isolation.py tests/test_audit_characterization.py` (STORY-001's URL characterization, `test_characterization_headers_and_url` and `test_the_split_fields_are_declared_last_and_in_order` must pass **unchanged**)

> Note: `test_the_split_fields_are_declared_last_and_in_order` (`tests/test_openrouter_client.py:432-436`) asserts `==` over the **whole** field list, so a sixth field fails it. That conflicts with AC 5's wording. Append `"finish_reason"` to that one expected list. The property the test pins, that the split fields come after `tokens_used` and in order, still holds. Record this in the report beside decision 7 (Risk R1).

### Task 5: Client tests

- **File**: `tests/test_openrouter_client.py`
- **Action**: UPDATE (append `# --- PRD-015 STORY-002 ---` sections)
- **Implement**:
  - **finish_reason**: parametrized over `stop`, `length`, `content_filter` → carried. Absent, `None`, `1`, `True`, `["stop"]` → `None`, and the call still succeeds. Three-argument and three-keyword construction give `finish_reason is None`. A field-order test lists all six.
  - **failure table** (parametrized, `pytest.param(..., id=...)`), each asserting `(upstream_status, retryable)` **and** the message prefix it has today:
    - `httpx.ReadTimeout("t")` → `(None, True)`
    - `httpx.ConnectTimeout("t")` → `(None, True)`
    - `httpx.ConnectError("c")` → `(None, True)`
    - status 500, 503 → `(500, True)`, `(503, True)`
    - status 429 → `(429, True)`
    - status 400, 401, 404 → `(n, False)`
    - malformed JSON (`httpx.Response(200, request=..., content=b"not json")`) → `(None, False)`
    - missing `choices` → `(None, False)`
    - null content → `(None, False)`
    - missing API key → `(None, False)`
  - **messages unchanged**: for one status, one transport and one shape case, assert `str(exc)` equals the full string today's code produces. Compute it from the same `httpx` exception, e.g. `f"OpenRouter request failed: {status_exc}"`, so the test pins the format rather than httpx's wording.
  - **positional construction**: `OpenRouterError("x")` has `str == "x"`, `upstream_status is None`, `retryable is False`, and `args == ("x",)`.
  - **base URL**: unset/default → `client.requests[0]["url"] == "https://openrouter.ai/api/v1/chat/completions"`. `monkeypatch.setattr(settings, "OPENROUTER_BASE_URL", "http://127.0.0.1:9100/v1")` → `.../v1/chat/completions`. The same value with a trailing `/` gives the same URL. A second call after changing the setting in the same test uses the new value (per-call, not import).
- **Mirror**: `tests/test_openrouter_client.py:283-436`
- **Validate**: `pytest -q tests/test_openrouter_client.py`

### Task 6: Repoint the manual slow smoke

- **File**: `tests/test_pipeline_concurrency.py`
- **Action**: UPDATE (lines ~610-613 only)
- **Implement**: replace the `_API_URL` string-target `setattr` with `monkeypatch.setattr(settings, "OPENROUTER_BASE_URL", f"http://127.0.0.1:{port}/v1")`. `settings` is already imported there; confirm it. Add a one-line comment citing PRD-015 STORY-002.
- **Validate**: `pytest -q tests/test_pipeline_concurrency.py` (the smoke is skipped and the rest stays green). Optional: a manual run with `HARNESS_SLOW_SMOKE=1` (about 1 min).

### Task 7: Full suite

- **Validate**: the full suite, per the memory recipe: Docker-free `-m "not db"` first, then the full run with the libsql container. Then `grep -rn "_API_URL" app` returns nothing.

---

## End-to-End Tests

No route consumes these fields yet, so E2E means "the real `httpx` path against a real socket":

- [ ] Start a throwaway local HTTP server on `127.0.0.1:<port>` that answers an OpenRouter-shaped body with `finish_reason: "length"`. Run `OPENROUTER_BASE_URL=http://127.0.0.1:<port>/v1` and call `call_openrouter` from a `python -c` one-liner with no injected client. The server sees `POST /v1/chat/completions`, and the result has `finish_reason == "length"`.
- [ ] Same server returning 503 → `OpenRouterError` with `upstream_status == 503` and `retryable is True`. Returning 401 → `upstream_status == 401` and `retryable is False`.
- [ ] Point at a closed port → `retryable is True` and `upstream_status is None`.
- [ ] Boot the app with `OPENROUTER_BASE_URL=http://example.com/v1` → startup fails with the validator's message. With the setting unset → the app boots and `/health` returns 200.
- [ ] `/query` 502 body for an upstream failure is unchanged (STORY-001's `test_v1_query_isolation.py` covers this in-suite).

---

## Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | `test_the_split_fields_are_declared_last_and_in_order` compares the full field list, and a sixth field fails it, which conflicts with AC 5's "every existing test passes without change" | Same as decision 7: a one-token update (append `"finish_reason"`), recorded as a deviation in the report. The story mandates the field and the test pins a property the change preserves |
| R2 | Manual slow smoke patches the deleted `_API_URL` | Task 6 (decision 7) |
| R3 | A validator message echoes a URL carrying credentials | Quote the scheme and hostname only, and test with `_TOKEN_SENTINEL` in the userinfo |
| R4 | A settings value captured at import ignores `monkeypatch.setattr(settings, ...)` | Read it inside `call_openrouter`, and a test changes it between two calls |
| R5 | Some caller relies on `OpenRouterError.args` or subclasses it | Grepped: no subclass, no `.args` use; 29 positional constructions remain valid |
| R6 | `monkeypatch.setattr(settings, "OPENROUTER_BASE_URL", ...)` bypasses the validator (no `validate_assignment`) | Intended: the validator guards the environment at startup, and tests set loopback values anyway |

---

## Validation

```bash
pytest -q tests/test_openrouter_client.py tests/test_config.py tests/test_v1_query_isolation.py tests/test_audit_characterization.py tests/test_pipeline_concurrency.py
pytest -q -m "not db"
pytest -q            # with the libsql container up
grep -rn "_API_URL" app   # no output
```

---

## Acceptance Criteria

(Copied from story `STORY-002`)

- [ ] Given an upstream response with `choices[0].finish_reason` of `stop`, `length` or `content_filter`, when `call_openrouter` returns, then `OpenRouterResult.finish_reason` carries it; given the field absent or not a string, then it is `None`; three-argument `OpenRouterResult(...)` construction still works.
- [ ] Given each failure (timeout, connect error, upstream 500/503, upstream 429, upstream 400/401/404, malformed JSON, missing `choices`, null content, missing API key), when `call_openrouter` raises `OpenRouterError`, then `upstream_status` is the HTTP status or `None`, and `retryable` is `True` exactly for timeout, connect error, 5xx and 429; the message text of every existing failure is unchanged.
- [ ] Given `OPENROUTER_BASE_URL` unset, when a call is made, then the request URL is byte-identical to today's (`https://openrouter.ai/api/v1/chat/completions`) and STORY-001's characterization passes unchanged.
- [ ] Given `OPENROUTER_BASE_URL=http://127.0.0.1:9100/v1`, when a call is made, then it goes to `http://127.0.0.1:9100/v1/chat/completions`; given `http://example.com/v1`, `ftp://...` or an empty string, then settings fail at startup with a message naming the setting, the rule (`https`, or `http` on `127.0.0.1` / `localhost` / `::1`) and an example.
- [ ] Given the full suite, when it runs, then every existing `call_openrouter` stub (signature `(messages, model, api_key)`) and every existing test pass without change. *(Two recorded exceptions, R1 and R2.)*
- [ ] All tasks completed
- [ ] Backend server starts without error
- [ ] Follows existing patterns
