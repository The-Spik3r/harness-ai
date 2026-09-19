---
story: STORY-003
prd: PRD-010
slug: openrouter-payload-characterization
title: "Characterize today's OpenRouter request payload and /query upstream body"
type: REFACTOR
complexity: SMALL
epic_branch: epic/PRD-010-multi-turn-pipeline        # all stories commit here, no per-story branch
created: 2026-09-17
---

# Plan: Characterize today's OpenRouter request payload and /query upstream body

## Summary

This is a test-only story: no production file changes. It pins, on **untouched** code, the exact upstream request `call_openrouter` sends today (payload shape with key order, headers, URL, default-client timeout) and the exact arguments `POST /query` passes into `call_openrouter` (prompt unchanged, requested model, `api_key=None`). Four `test_characterization_*` tests are added — three extending `tests/test_openrouter_client.py` using its existing `_FakeClient` (which already records `{"url", "headers", "json"}` per call, so no extension is actually needed), and one added beside the six outcomes in `tests/test_query_outcomes_regression.py`, reusing its `client`/`temp_db`/`_AUTH_HEADERS` fixtures. These four tests are what STORY-004 (which changes `call_openrouter` to take `messages` instead of `prompt`) and STORY-005 (which changes the hard-coded 30s timeout) must keep green or deliberately cite when they change an assertion.

## User Story

As an integrating developer
I want the exact upstream request `/query` sends today pinned by a test before the client changes
So that the "byte-identical payload" promise is checked, not assumed

## Story Reference

- Story file: `.agents/stories/PRD-010-multi-turn-pipeline/STORY-003-openrouter-payload-characterization.md`
- PRD: `.agents/PRDs/PRD-010-multi-turn-pipeline/PRD.md` — sections 2 (Pin before you change), 9.2 (invariants), 11, 12 (Phase 1), 14 (Risk 1)

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR (test-only characterization, no behavior change) |
| Complexity | SMALL |
| Systems Affected | `tests/test_openrouter_client.py`, `tests/test_query_outcomes_regression.py` |
| Story | STORY-003 |
| PRD | PRD-010 |
| Epic Branch | `epic/PRD-010-multi-turn-pipeline` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | The only skill in `.agents/skills/` is `frontend-design`, which covers UI and copy. This story is backend test characterization with no UI surface; the story's `skills: []` field and Technical Notes agree ("Skills: none applicable"). | — |

---

## Patterns to Follow

### Existing `_FakeClient` already records every call (no extension needed)
```python
// SOURCE: tests/test_openrouter_client.py:18-28
class _FakeClient:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.requests = []

    def post(self, url, headers=None, json=None):
        self.requests.append({"url": url, "headers": headers, "json": json})
        if self._exc:
            raise self._exc
        return self._response
```
`client.requests[0]` already gives `{"url", "headers", "json"}` for exact-payload assertions. The story's Technical Notes say "Extend the existing `_FakeClient` ... to record calls" — it already does; Task 1 below confirms this in the plan rather than adding dead code.

### Production payload under test (untouched — this is what gets pinned)
```python
// SOURCE: app/services/openrouter_client.py:8-10, 36-46
_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_TIMEOUT_SECONDS = 30.0
...
headers = {
    "Authorization": f"Bearer {resolved_key}",
    "Content-Type": "application/json",
}
payload = {
    "model": model,
    "messages": [{"role": "user", "content": prompt}],
}
...
http_client = client or httpx.Client(timeout=_TIMEOUT_SECONDS)
```

### Router-level `call_openrouter` call site (what the pipeline test pins)
```python
// SOURCE: app/services/query_pipeline.py:163-166
openrouter_result = call_openrouter(
    redacted_prompt, model=model, api_key=openrouter_api_key
)
```
For a PII-free prompt, `redacted_prompt == prompt`, and `POST /query`'s `openrouter_api_key` defaults to `None` (`app/models/schemas.py:16`), so the pipeline-level test's expected received args are `{"prompt": <unchanged text>, "model": "gpt-4", "api_key": None}`.

### Six-outcome regression file: fixtures + patch site to reuse for the new pipeline-level test
```python
// SOURCE: tests/test_query_outcomes_regression.py:34-49, 69-70, 81-93
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

def test_outcome_1_success(temp_db, monkeypatch):
    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_success)
    ...
```
The new test patches the same site, `app.routers.query.call_openrouter`, with a recording fake instead of `_fake_success`, and reuses `temp_db`/`client`/`_AUTH_HEADERS` exactly as outcomes 1–6 do. Rows 1–6 themselves are not touched.

### `pattern_detector` allowlist the new prompt text must avoid
```python
// SOURCE: app/services/pattern_detector.py:4-12
SUSPICIOUS_PATTERNS: List[str] = [
    "ignore previous instructions", "forget everything", "show system prompt",
    "reveal password", "execute code", "admin mode", "override",
]
```
The characterization prompt must contain none of these substrings (case-insensitive) or the pipeline-level test would hit outcome 3 (suspicious block) instead of success.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_openrouter_client.py` | UPDATE | Add 3 `test_characterization_*` tests pinning payload shape (key order), headers/URL, and the default client's `timeout=30.0` |
| `tests/test_query_outcomes_regression.py` | UPDATE | Add 1 `test_characterization_*` test pinning what `/query` passes into `call_openrouter` (prompt unchanged, model, `api_key=None`) |

No production file is modified (AC 5).

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Client-level characterization — payload shape, key order, no extra keys

- **File**: `tests/test_openrouter_client.py`
- **Action**: UPDATE
- **Implement**: After the last existing test (`test_api_key_never_appears_in_error_message`, ending at line 111), add a section header comment and the first characterization test:
  ```python
  import json


  # --- PRD-010 STORY-003: characterization of today's OpenRouter payload ---
  #
  # Pinned before PRD-010 STORY-004. Assertions change only where a later
  # story cites the decision.


  def test_characterization_payload_shape_is_byte_identical():
      client = _FakeClient(response=_response())

      call_openrouter("hello", model="gpt-4", api_key="k", client=client)

      payload = client.requests[0]["json"]
      expected = {"model": "gpt-4", "messages": [{"role": "user", "content": "hello"}]}
      # json.dumps with sort_keys=False makes this an ordered comparison, not
      # just an equal-set-of-keys one: a reordered payload would fail here
      # even though `payload == expected` would still pass.
      assert json.dumps(payload, sort_keys=False) == json.dumps(expected, sort_keys=False)
  ```
  `import json` goes at the top of the file with the other stdlib import (`import os`), not inline — match the file's existing import block ordering (stdlib, blank line, third-party, blank line, first-party).
- **Mirror**: `tests/test_openrouter_client.py:40-47` (`test_success_returns_response_model_and_tokens`) for the `_FakeClient` + `call_openrouter(..., client=client)` call shape.
- **Validate**: `cd G:/coding/harness-ai && python -m pytest tests/test_openrouter_client.py -v -k characterization`

### Task 2: Client-level characterization — headers and URL

- **File**: `tests/test_openrouter_client.py`
- **Action**: UPDATE
- **Implement**: Immediately after Task 1's test, add:
  ```python
  def test_characterization_headers_and_url():
      client = _FakeClient(response=_response())

      call_openrouter("hello", model="gpt-4", api_key="k", client=client)

      request = client.requests[0]
      assert request["url"] == _API_URL
      assert request["headers"] == {
          "Authorization": "Bearer k",
          "Content-Type": "application/json",
      }
  ```
- **Mirror**: `tests/test_openrouter_client.py:59-65` (`test_per_request_api_key_overrides_env`) for reading `client.requests[0]["headers"]`; `_API_URL` module constant already defined at `tests/test_openrouter_client.py:15`.
- **Validate**: `cd G:/coding/harness-ai && python -m pytest tests/test_openrouter_client.py -v -k characterization`

### Task 3: Client-level characterization — default client's timeout

- **File**: `tests/test_openrouter_client.py`
- **Action**: UPDATE
- **Implement**: Immediately after Task 2's test, add:
  ```python
  def test_characterization_default_client_uses_todays_timeout(monkeypatch):
      """AC 3: today's value (30.0). STORY-005 changes this deliberately,
      citing PRD-010 at that point."""
      captured = {}

      class _StubHttpxClient:
          def __init__(self, *args, **kwargs):
              captured["kwargs"] = kwargs

          def post(self, url, headers=None, json=None):
              return _response()

          def close(self):
              pass

      monkeypatch.setattr(httpx, "Client", _StubHttpxClient)

      call_openrouter("hello", api_key="k")

      assert captured["kwargs"] == {"timeout": 30.0}
  ```
  `client=None` (omitted) is deliberate: it is the only way to exercise `call_openrouter`'s own `httpx.Client(timeout=_TIMEOUT_SECONDS)` construction (`app/services/openrouter_client.py:46`). Patching `httpx.Client` (the module-level attribute the file already imports as `httpx`, `tests/test_openrouter_client.py:6`) rather than `app.services.openrouter_client.httpx.Client` works because `openrouter_client.py` does `import httpx` and reads `httpx.Client` off the shared module object at call time — patching either name hits the same object, and patching the shared `httpx` module matches how the file already imports it.
- **Mirror**: `tests/test_openrouter_client.py:84-88` (`test_network_error_raises_openrouter_error`) for the `monkeypatch` fixture parameter shape; no existing test patches `httpx.Client` itself, so this is the first of its kind in the file.
- **Validate**: `cd G:/coding/harness-ai && python -m pytest tests/test_openrouter_client.py -v -k characterization`

### Task 4: Pipeline-level characterization — `/query`'s upstream body

- **File**: `tests/test_query_outcomes_regression.py`
- **Action**: UPDATE
- **Implement**: After `test_outcome_6_internal_failure_duplicate_storage` (the file's last test, ending at line 211), add:
  ```python
  # --- PRD-010 STORY-003: characterization of the /query upstream call ---
  #
  # Pinned before PRD-010 STORY-004. Assertions change only where a later
  # story cites the decision. This is the pipeline-level counterpart to
  # tests/test_openrouter_client.py's characterization tests: it is what
  # STORY-004 must keep green when it changes call_openrouter's signature.


  def test_characterization_query_upstream_receives_prompt_model_and_no_api_key(
      temp_db, monkeypatch
  ):
      received = {}

      def _recording_success(prompt, model="gpt-4", api_key=None):
          received["prompt"] = prompt
          received["model"] = model
          received["api_key"] = api_key
          return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)

      monkeypatch.setattr("app.routers.query.call_openrouter", _recording_success)

      prompt = "characterization: pin today's upstream body before STORY-004"
      response = client.post("/query", json={"prompt": prompt})

      assert response.status_code == 200
      assert response.json()["status"] == "SUCCESS"
      assert received == {"prompt": prompt, "model": "gpt-4", "api_key": None}
  ```
  The prompt text is PII-free (no names/emails/etc. for Presidio to flag) and contains none of `pattern_detector.SUSPICIOUS_PATTERNS`, so the request reaches outcome 1 (success) rather than being blocked. `model` is omitted from the request body so it takes `QueryRequest`'s default (`"gpt-4"`, `app/models/schemas.py:15`), and `openrouter_api_key` is omitted so it stays `None` — both are what "the requested model" and `api_key=None` in AC 4 refer to.
- **Mirror**: `tests/test_query_outcomes_regression.py:81-93` (`test_outcome_1_success`) for the `temp_db`/`monkeypatch`/`client.post` shape and the same patch site (`app.routers.query.call_openrouter`).
- **Validate**: `cd G:/coding/harness-ai && python -m pytest tests/test_query_outcomes_regression.py -v -k characterization`

---

## End-to-End Tests

This story has no user-facing flow — it is characterization tests over an existing, unchanged endpoint. The checks are the test suite itself:

- [ ] `pytest tests/test_openrouter_client.py -v` — all existing tests plus the 3 new characterization tests pass
- [ ] `pytest tests/test_query_outcomes_regression.py -v` — outcomes 1–6 unchanged and green, plus the new characterization test
- [ ] `pytest` (full suite) — green, confirming nothing else regressed
- [ ] `git status` / `git diff --stat` shows only the two test files changed — no production file under `app/` or `chat_ui/` touched (AC 5)

---

## Validation

```bash
cd G:/coding/harness-ai
python -m pytest tests/test_openrouter_client.py -v
python -m pytest tests/test_query_outcomes_regression.py -v
python -m pytest
git status --short
```

Per the libSQL dev-server note (`tests/conftest.py`), if the full run shows mass fixture errors (e.g. `STREAM_EXPIRED` across unrelated files), restart the local libSQL dev container rather than treating it as a code regression:

```bash
docker restart harness-libsql-dev
```

---

## Acceptance Criteria

(Copied from story `STORY-003`)

- [ ] Given `call_openrouter("hello", model="gpt-4", api_key="k", client=fake)` on **untouched** production code, when the fake client records its `post(url, headers, json)` call, then a test asserts `json == {"model": "gpt-4", "messages": [{"role": "user", "content": "hello"}]}` exactly: equal key set, key order and no extra keys, compared via `json.dumps(..., sort_keys=False)`.
- [ ] Given the same call, when headers are recorded, then the test asserts `{"Authorization": "Bearer k", "Content-Type": "application/json"}` and the URL `https://openrouter.ai/api/v1/chat/completions`.
- [ ] Given no `client` argument, when `call_openrouter` constructs its own `httpx.Client`, then a test (patching `httpx.Client`) asserts it was built with `timeout=30.0`.
- [ ] Given `POST /query` with a PII-free prompt through `TestClient`, when the injected upstream records what it received, then a test asserts it received the prompt text unchanged, the requested model, and `api_key=None`.
- [ ] Given the full suite, when this story lands, then it is green and **no production file is modified**.
- [ ] All tasks completed
- [ ] Tests named `test_characterization_*`, each carrying/near a comment: "Pinned before PRD-010 STORY-004. Assertions change only where a later story cites the decision."
- [ ] Follows existing patterns (`_FakeClient`, `temp_db`/`client` fixtures, `app.routers.query.call_openrouter` patch site)
