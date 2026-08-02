---
story: STORY-005
prd: PRD-003
slug: pipeline-input-redaction
title: "Redact prompt before forwarding to OpenRouter"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-003-pii-redaction        # all stories commit here, no per-story branch
created: 2026-07-31
---

# Plan: Redact prompt before forwarding to OpenRouter

## Summary

Insert a single redaction step into `run_query()` in `app/services/query_pipeline.py`, between the pattern check (line 41-53) and the OpenRouter call (line 56): `redacted_prompt, input_entities = redact(prompt)`, then pass `redacted_prompt` — and only that — into `call_openrouter(...)`. This is the first point in the codebase where the pipeline stops handing raw user text to a third party, and it is deliberately the *only* line of behaviour this story changes.

Everything upstream and downstream of that one call stays raw. `check_duplicate(prompt)` (line 26) and `detect_suspicious_pattern(prompt)` (line 41) keep receiving the original `prompt` variable — physically impossible to break here, because redaction is placed *after* both and binds its output to a **new** name rather than rebinding `prompt` (Design Note 1). Every `log_query(...)` call site — the four existing ones and the one this story adds — passes `prompt=prompt`, so `prompt_hash`/`prompt_preview` remain raw (PRD Section 9, RF-6/RF-7). Placement after the two blocking checks also satisfies AC3 for free: on a duplicate-blocked or pattern-blocked request the function has already returned, so `redact()` — and its NLP inference — is never reached.

`input_entities` is captured and intentionally left unused by this story; [[STORY-006]] combines it with the output entity list and wires both into `log_query()`. The `PII_REDACTION_ENABLED=false` toggle needs no branch in the pipeline: [[STORY-001]] already made `redact()` a pass-through returning `(text, [])` when disabled (`pii_redactor.py:50-51`), so the pipeline calls it unconditionally (Design Note 3).

The redaction call is wrapped in the **same log-then-re-raise shape the OpenRouter call already uses** (`query_pipeline.py:55-66`): on `PiiRedactorError` the pipeline writes a `success=False` audit row carrying the raw prompt and the error message, then re-raises; `app/routers/query.py` maps it to a clean HTTP 500 alongside the existing `DuplicateCheckError` arm. That is fail-closed *and* fully audited — a broken analyzer can never silently forward raw PII, and it can never make a request vanish without a trace either. PRD-001's "exactly one audit row per request" guarantee holds on this path too (Design Note 4).

## User Story

As an end user
I want any PII I type into a prompt masked before it leaves the organization's infrastructure
So that my personal data is never sent to the third-party model provider (PRD User Story 1, RF-1, RF-2)

## Story Reference

- Story file: `.agents/stories/PRD-003-pii-redaction/STORY-005-pipeline-input-redaction.md`
- PRD: `.agents/PRDs/PRD-003-pii-redaction/PRD.md` — Section 6 (Core Architecture, steps 4-6), User Story 1, Section 9 (Redaction scope), Section 12 Phase 2

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `app/services/query_pipeline.py`, `app/routers/query.py`, `tests/test_query_router.py` |
| Story | STORY-005 |
| PRD | PRD-003 |
| Epic Branch | `epic/PRD-003-pii-redaction` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` does not exist in this repository (confirmed — `Glob .agents/skills/**/SKILL.md` returns no files), the story's `skills:` frontmatter field is `[]`, and PRD Section 15 states it explicitly ("Skills referenced: None"). Same finding as the [[STORY-001]] through [[STORY-004]] plans.

---

## Dependency Check

| Dependency | Status | Verified |
|---|---|---|
| [[STORY-001]] — Presidio PII redactor service | ✅ done (`0495068`) | `redact()` exists at `app/services/pii_redactor.py:49` and returns `Tuple[str, List[str]]` |
| [[STORY-002]] — Load NLP model at startup | ✅ done (`358ddc6`) | `pii_redactor.load()` called in `lifespan` at `app/main.py:14` |

Both `depends_on` entries are `done` — no blocker, no user confirmation needed.

---

## Patterns to Follow

### Service functions are imported by name and called directly

```python
# SOURCE: app/services/query_pipeline.py:8-11
from app.services.audit_logger import log_query
from app.services.duplicate_checker import check_duplicate
from app.services.openrouter_client import OpenRouterError, OpenRouterResult, call_openrouter
from app.services.pattern_detector import detect_suspicious_pattern
```

Four of the pipeline's five collaborators are plain `from ... import name`. Only `call_openrouter` additionally appears as an injectable default parameter, because the *router* passes it explicitly (`app/routers/query.py:23`). `redact` is a service like `check_duplicate`, not a router-injected dependency — it follows the plain-import form (Design Note 2).

### Sequential guard-then-proceed pipeline, each stage on its own

```python
# SOURCE: app/services/query_pipeline.py:26-53
    duplicate_result = check_duplicate(prompt)

    if duplicate_result.is_duplicate:
        log_query(...)
        return QueryBlockedDuplicateResponse(...)

    pattern_result = detect_suspicious_pattern(prompt)
    if pattern_result.is_suspicious:
        log_query(...)
        return QueryBlockedSuspiciousResponse(...)
```

Each stage: call the service, bind the result to a `*_result` name, early-return on the blocking condition. Redaction is a non-blocking stage, so it is a bare call with tuple unpacking and no `if` — a blank line before and after, sitting between the pattern block and the `try:` (PRD Section 6, pipeline pattern).

### Tuple-unpacking contract of `redact()`

```python
# SOURCE: app/services/pii_redactor.py:49-51
def redact(text: str) -> Tuple[str, List[str]]:
    if not settings.PII_REDACTION_ENABLED or not text:
        return text, []
```

```python
# SOURCE: app/services/pii_redactor.py:73-74
    entities_found = sorted({result.entity_type for result in results})
    return anonymized.text, entities_found
```

Always a 2-tuple. Returns the input text verbatim and `[]` (never `None`) when redaction is disabled, when the text is empty, and when no entity clears the threshold. That is exactly AC4 ("clean prompt → text unchanged, no entities") — already guaranteed by the callee, so this story only has to *not* interfere.

### Failure path: log the raw attempt, then re-raise

```python
# SOURCE: app/services/query_pipeline.py:55-66
    try:
        openrouter_result = call_openrouter(prompt, model=model, api_key=openrouter_api_key)
    except OpenRouterError as exc:
        log_query(
            user_id=user_id,
            prompt=prompt,
            device=device,
            model_used=model,
            success=False,
            error_message=str(exc),
        )
        raise
```

The pipeline already owns exactly one failure idiom: catch the service's own exception, write a `success=False` row with the **raw** prompt and `error_message=str(exc)`, then bare `raise` so the router decides the status code. The redaction failure path is this same block with a different exception type — no new pattern is invented (Design Note 4).

### Errors raised as a module-specific exception, translated at the router

```python
# SOURCE: app/services/pii_redactor.py:13-14
class PiiRedactorError(Exception):
    pass
```

```python
# SOURCE: app/routers/query.py:25-28
    except DuplicateCheckError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except OpenRouterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
```

Each service defines its own exception; the router — never the pipeline — maps it to a status code with `from exc`. `PiiRedactorError` gets the same treatment as `DuplicateCheckError` (500: an internal component failed), added in the same `except` chain.

### Tests: HTTP-level pipeline tests with a monkeypatched OpenRouter

```python
# SOURCE: tests/test_query_router.py:24-29
@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path
```

```python
# SOURCE: tests/test_query_router.py:76-84
def test_clean_prompt_success_returns_expected_shape_and_logs_row(temp_db, monkeypatch):
    def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
        return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)

    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)
```

Every pipeline test drives the real `POST /query` through `TestClient`, takes `temp_db`, and replaces the network call by patching the **string target** `"app.routers.query.call_openrouter"` (the router's import site, because the router passes it in as an argument).

### Tests: "this must never be reached" assertion

```python
# SOURCE: tests/test_query_router.py:52-53
def _fail_if_called(*args, **kwargs):
    raise AssertionError("call_openrouter should not have been called")
```

The existing idiom for proving a short-circuit. AC3 ("`redact()` never invoked on blocked requests") reuses this shape, patched at `"app.services.query_pipeline.redact"` — the *pipeline's* import site, since nothing injects `redact` from the router.

### Tests: raw-text guarantee asserted against a recomputed hash

```python
# SOURCE: tests/test_query_router.py:38-48
def _seed_duplicate(prompt: str, hours_ago: float = 2) -> str:
    ...
    insert_audit_log(AuditLog(timestamp=timestamp, user_id="juan@empresa.com", prompt_hash=hash_prompt(prompt)))
```

`hash_prompt(prompt)` recomputed from the literal raw text is the file's existing way of pinning "the hash came from *this* string" — the tool for proving that dedup never saw redacted text.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/query_pipeline.py` | UPDATE | Import `redact` + `PiiRedactorError`; call `redact` after the pattern check inside a log-then-re-raise block; pass `redacted_prompt` to `call_openrouter` |
| `app/routers/query.py` | UPDATE | Translate `PiiRedactorError` → HTTP 500, mirroring `DuplicateCheckError` |
| `tests/test_query_router.py` | UPDATE | Add 9 tests covering AC1-AC4, the raw-audit guarantee, the disabled toggle, and the audited fail-closed error path |

**Explicitly NOT touched:**

- `app/services/pii_redactor.py` — [[STORY-001]] is done; this story is a pure consumer. No new argument, no new function, no threshold logic here
- `app/services/duplicate_checker.py` — untouched, byte-for-byte (PRD Section 9, RF-6). Must be absent from `git diff --name-only`
- `app/services/pattern_detector.py` — untouched
- `app/services/audit_logger.py` — not edited. [[STORY-004]] already added the three telemetry params; **wiring them is [[STORY-006]]'s scope**, not this story's (Design Note 5). The four existing `log_query(...)` calls keep their current argument lists, and the one new call (the redaction-failure row) uses only parameters that already existed before [[STORY-004]]
- `app/models/schemas.py` — the `pii_redacted` / `pii_entities_masked` response fields are [[STORY-007]]; `QuerySuccessResponse` gains nothing here
- The response path — `openrouter_result.response` is returned raw to the caller after this story. Output redaction is [[STORY-006]] (Design Note 6)
- `app/main.py` — the `lifespan` `pii_redactor.load()` call is already in place from [[STORY-002]]
- `tests/test_duplicate_checker.py`, `tests/test_pattern_detector.py`, `tests/test_pii_redactor.py`, `tests/test_integration.py` — all must pass **unmodified** (PRD Section 11)

---

## Design Notes (decisions worth stating up front)

1. **Bind to a new name (`redacted_prompt`); never rebind `prompt`.** The story's Technical Notes call this out explicitly, and it is the entire mechanical safeguard behind AC2 and RF-6. Because `prompt` is never reassigned, every earlier and later reader of that variable — `check_duplicate(prompt)`, `detect_suspicious_pattern(prompt)`, and all five `log_query(prompt=prompt, ...)` calls — provably still sees raw text; a reviewer confirms it by reading the diff, not by tracing control flow. A `prompt = redact(prompt)[0]` shortcut would silently corrupt the dedup hash *and* the audit preview in one stroke. It is forbidden here, and Task 5's diff check exists to catch it.

2. **`redact` is imported by name, not added as an injectable parameter.** `run_query()`'s `call_openrouter` parameter exists because the router owns that dependency and passes it (`query.py:23`); `check_duplicate`, `detect_suspicious_pattern`, and `log_query` — the actual peers of `redact` — are all plain imports. Tests patch `"app.services.query_pipeline.redact"`, which works exactly like the existing `"app.routers.query.call_openrouter"` patching, so nothing is lost in testability. Adding a fifth parameter would also change `run_query()`'s signature, which [[STORY-006]] and [[STORY-007]] would then have to keep threading through the router.

3. **No `if settings.PII_REDACTION_ENABLED:` branch in the pipeline.** The story asks to "confirm the exact toggle point with [[STORY-001]]'s implementation" — confirmed: `pii_redactor.py:50` already short-circuits to `return text, []` when the flag is false, before any analyzer is touched. Duplicating that check in the pipeline would put the toggle in two places that can drift, and would break `test_load_is_noop_when_redaction_disabled`'s premise that the redactor owns its own disabled path. The pipeline calls `redact()` unconditionally and gets a pass-through. A test pins this end-to-end anyway (Task 4, `test_redaction_disabled_forwards_raw_prompt`), because "the toggle works from the caller's seat" is worth asserting even when the mechanism lives one layer down.

4. **Fail-closed on `PiiRedactorError`, and audited: log a `success=False` row, re-raise, translate to 500 at the router.** `redact()` raises `PiiRedactorError` if the model fails to load or analysis/anonymization throws (`pii_redactor.py:26, 62, 71`). Three decisions stack here:

   **(a) Fail-closed, not fail-open.** The alternative — swallowing the exception and forwarding the raw prompt — would send unmasked PII to OpenRouter precisely when the safety net is broken, inverting the whole point of the feature. PRD's "mask, never block" principle governs *detection outcomes* (a detected entity never denies a request), not infrastructure failure. A dead analyzer is the same class of event as `DuplicateCheckError`, which already returns 500. Because redaction sits **before** the `try:` block, a failure means `call_openrouter` is never reached — the fail-closed guarantee comes from statement order, not from the exception handling.

   **(b) The failure is audited.** Without a `log_query()` call the request would vanish with zero rows, which breaks PRD-001's "exactly one audit row per request" guarantee on the one path where an auditor most wants a record: text that reached the redactor, broke it, and was never sent anywhere. The row stores the **raw** prompt (RF-7), so the auditor can see exactly what input tripped the analyzer, plus `success=False` and `error_message=str(exc)`. It is written by mirroring the existing OpenRouter-failure block verbatim (`query_pipeline.py:57-66`) — same shape, same argument order, different exception type — so the file ends up with two structurally identical failure handlers instead of one handler and one novelty.

   **(c) `model_used` is deliberately omitted from that row** (unlike the OpenRouter-failure row, which passes `model_used=model`). `top_models()` counts every row where `model_used IS NOT NULL` with no `success` filter (`app/db/database.py:158-166`), so recording a model on a request that never reached model selection would inflate `/stats`' `top_models` with a model that was never invoked. The OpenRouter path legitimately attempted its model; this one did not. `success_rate` still moves correctly, because it divides `count_successful_queries()` by the total row count (`app/routers/admin.py:48-50`) — the failure is visible in `/stats` rather than hidden.

   `error_message` needs no prefix: `PiiRedactorError`'s own messages already read `"PII analysis failed: ..."`, `"PII anonymization failed: ..."`, or `"Failed to load Presidio NLP model ..."` (`pii_redactor.py:26, 62, 71`), so `str(exc)` is self-describing exactly like the OpenRouter path's is. The three PII telemetry columns from [[STORY-004]] keep their defaults (`False`/`False`/`None`) on this row — "unknown", strictly speaking, not "no PII found" — which is unambiguous in practice because the row is identifiable by `success=False` + `error_message`.

   Out of scope, worth naming: `DuplicateCheckError` still writes **no** audit row today (it raises inside `check_duplicate()` before the first `log_query`). After this story the redaction failure path is better audited than the dedup failure path. That is an improvement, not a regression, and closing the gap on `check_duplicate` is a candidate follow-up — not this story's business, and not something to fix while touching `duplicate_checker.py` is forbidden by RF-6.

5. **`input_entities` is captured but deliberately unused until [[STORY-006]].** The story says to "keep the return value available rather than discarding it", and [[STORY-006]]'s Technical Notes (line 40) assign the combined `pii_entities=input_entities + output_entities` wiring to that story so the dedup/merge lives in one place. Writing `redacted_prompt, _ = redact(prompt)` here would force [[STORY-006]] to re-edit this line; writing a partial `log_query(pii_detected_input=...)` now would create a call site [[STORY-006]] must immediately rewrite. So the variable sits assigned-and-unused for exactly one story. This is not dead code by accident — it is a named seam. There is no linter configured in this repo (no `ruff.toml`, `pyproject.toml`, `setup.cfg`, or `pytest.ini`), so no unused-variable warning will fire.

6. **The caller still gets the raw model response after this story — that is correct, not incomplete.** Redaction is one-directional here (outbound prompt only, PRD Section 6 steps 4-6). `QuerySuccessResponse(response=openrouter_result.response, ...)` at line 78-83 is untouched. [[STORY-006]] adds the inbound half. Consequently `test_clean_prompt_success_returns_expected_shape_and_logs_row` and `test_happy_path_returns_success_and_logs_exactly_one_row`, which assert on the exact response body, stay green unmodified.

7. **Existing tests are unaffected — verified empirically, not assumed.** Every prompt the current suite sends through the success path was run through the real redactor at the default `PII_SCORE_THRESHOLD=0.35`: `'hello world'`, `'what is the weather today'`, `'duplicate me please'`, `'clean prompt one'`, and `'how fast is this'` all return `(text_unchanged, [])`. No false positive changes the text handed to the mocked `call_openrouter`, and the mocks ignore the prompt argument anyway. Blocked-path tests never reach the redactor at all. Baseline to preserve: **127 passed** (`.venv/Scripts/python.exe -m pytest`, measured on this branch before the change).

8. **Latency: cold path ~1.1 s, warm path ~5 ms — measured.** `test_full_pipeline_latency_within_budget` (`tests/test_query_router.py:157-170`) asserts a full `/query` round trip under 0.5 s, so it is the one existing test that redaction could plausibly break. Measured on this machine with `en_core_web_lg`: first `redact()` call (lazy analyzer construction) 1.12 s, subsequent calls 0.005 s. The latency test is the **last** test in its file and several earlier tests in that same file already drive a successful `/query`, so the module-level `_analyzer` singleton is always warm by the time it runs — and `TestClient` here is constructed without a `with` block, so `lifespan`/`load()` does not preload it. 5 ms of NER against a 0.5 s budget is not a risk. Task 5 verifies this explicitly rather than trusting the reasoning; if the ordering ever changes, the fix is a warm-up `redact("warm up")` call before `start = time.perf_counter()` in that test, **not** a raised budget — PRD Section 11 explicitly declines to set a latency ceiling for redaction, so the 0.5 s number must keep measuring pipeline overhead, not model load.

9. **Use `.venv/Scripts/python.exe` for every command.** [[STORY-003]]'s report (Deviation 1) recorded that bare `python` on this machine resolves to a global Python 3.13 without `presidio-analyzer`, producing collection errors in every module that transitively imports `app.main` → `app.services.pii_redactor`. Environment mismatch, not a code defect. All commands below name the venv interpreter explicitly.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Import `redact` into the pipeline

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**: Add one import, alphabetically after the `pattern_detector` import (line 11), keeping the existing block's sorted order:
  ```python
  from app.services.pattern_detector import detect_suspicious_pattern
  from app.services.pii_redactor import PiiRedactorError, redact
  ```
  Both names are needed: `redact` for the call, `PiiRedactorError` for the audited failure block in Task 2 (Design Note 4). Do not add `redact` to `run_query()`'s parameter list (Design Note 2).
- **Mirror**: `app/services/query_pipeline.py:8-11` — plain `from app.services.X import name`, one per collaborator, alphabetically ordered by module.
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -c "import app.services.query_pipeline as qp; print(qp.redact.__module__)"
  ```
  → `app.services.pii_redactor`

### Task 2: Redact the prompt between the pattern check and the OpenRouter call

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**: Insert one statement after the `pattern_result.is_suspicious` block (ends line 53) and before `try:` (line 55), then change the argument passed to `call_openrouter`:
  ```python
          return QueryBlockedSuspiciousResponse(
              reason="Suspicious pattern detected",
              pattern=pattern_result.pattern,
          )

      try:
          redacted_prompt, input_entities = redact(prompt)
      except PiiRedactorError as exc:
          log_query(
              user_id=user_id,
              prompt=prompt,
              device=device,
              success=False,
              error_message=str(exc),
          )
          raise

      try:
          openrouter_result = call_openrouter(
              redacted_prompt, model=model, api_key=openrouter_api_key
          )
      except OpenRouterError as exc:
  ```
  - `redacted_prompt` is a **new** name. `prompt` is never reassigned anywhere in this function (Design Note 1).
  - `input_entities` is intentionally unused until [[STORY-006]] (Design Note 5). Do not rename it to `_`.
  - The `except` block is the existing OpenRouter-failure block (lines 57-66) with two differences, both deliberate: the exception type, and **no `model_used=model`** — see Design Note 4(c), it would pollute `/stats`' `top_models`. Bare `raise`, never `raise HTTPException` — status codes belong to the router.
  - Do **not** add the [[STORY-004]] telemetry arguments (`pii_detected_input=...`) to this call. They keep their defaults on a failure row; wiring them is [[STORY-006]].
  - No `if settings.PII_REDACTION_ENABLED` guard (Design Note 3).
  - **Change exactly one argument on the OpenRouter call**: `call_openrouter(prompt, ...)` → `call_openrouter(redacted_prompt, ...)`. Every other occurrence of `prompt` in the file stays as-is — specifically `check_duplicate(prompt)` (line 26), `detect_suspicious_pattern(prompt)` (line 41), and `prompt=prompt` in every `log_query(...)` call, now five of them.
  - Add `PiiRedactorError` to the Task 1 import: `from app.services.pii_redactor import PiiRedactorError, redact`.
- **Mirror**: `app/services/query_pipeline.py:57-66` — the log-then-bare-`raise` failure block, copied argument-for-argument minus `model_used`. `app/services/query_pipeline.py:26` and `:41` — service call bound to a local, blank line separating stages.
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && git diff -U3 app/services/query_pipeline.py
  ```
  → the only `-` lines are the single `call_openrouter(prompt, ...)` line; `check_duplicate(prompt)`, `detect_suspicious_pattern(prompt)`, and every `prompt=prompt` are untouched.
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_query_router.py tests/test_integration.py -q
  ```
  → still green with **zero** test edits (Design Note 7; the test file is not touched until Task 4).

### Task 3: Translate `PiiRedactorError` to HTTP 500 at the router

- **File**: `app/routers/query.py`
- **Action**: UPDATE
- **Implement**: Add the import and one `except` arm. Place the new arm after `DuplicateCheckError` and before `OpenRouterError`, matching pipeline order:
  ```python
  from app.services.duplicate_checker import DuplicateCheckError
  from app.services.openrouter_client import OpenRouterError, call_openrouter
  from app.services.pii_redactor import PiiRedactorError
  from app.services.query_pipeline import run_query
  ```
  ```python
      except DuplicateCheckError as exc:
          raise HTTPException(status_code=500, detail=str(exc)) from exc
      except PiiRedactorError as exc:
          raise HTTPException(status_code=500, detail=str(exc)) from exc
      except OpenRouterError as exc:
          raise HTTPException(status_code=502, detail=str(exc)) from exc
  ```
  500, not 502: the failure is internal (the local NLP engine), not an upstream gateway problem. Do not add a broad `except Exception`.
- **Mirror**: `app/routers/query.py:25-28` — one `except` per service exception, `HTTPException(...) from exc`, no logging (this file has none).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_query_router.py -q
  ```
  → green. Behavioural proof arrives with Task 4's two `test_redactor_failure_*` tests.

### Task 4: Add pipeline redaction tests

- **File**: `tests/test_query_router.py`
- **Action**: UPDATE
- **Implement**: Append these tests at the end of the file. Add two imports at the top — `from app.db.database import ...` already provides `get_audit_log`/`get_connection`/`init_db`/`insert_audit_log` (line 13) and `hash_prompt` is already imported (line 16); add `from app.services.pii_redactor import PiiRedactorError` alongside the existing service imports. Do **not** modify any of the seven existing tests.

  ```python
  _PII_PROMPT = "my email is juan@empresa.com, can you draft a reply?"
  _REDACTED_PROMPT = "my email is <EMAIL_ADDRESS>, can you draft a reply?"


  def _capturing_openrouter(seen: list):
      def _call(prompt, model="gpt-4", api_key=None):
          seen.append(prompt)
          return OpenRouterResult(response="drafted", model_used=model, tokens_used=9)

      return _call


  def test_pii_prompt_is_redacted_before_reaching_openrouter(temp_db, monkeypatch):
      seen = []
      monkeypatch.setattr("app.routers.query.call_openrouter", _capturing_openrouter(seen))

      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
      )

      assert response.status_code == 200
      assert seen == [_REDACTED_PROMPT]
      assert "juan@empresa.com" not in seen[0]


  def test_duplicate_and_pattern_checks_still_receive_the_raw_prompt(temp_db, monkeypatch):
      seen_duplicate = []
      seen_pattern = []
      real_check_duplicate = query_pipeline.check_duplicate
      real_detect = query_pipeline.detect_suspicious_pattern

      def _spy_duplicate(prompt):
          seen_duplicate.append(prompt)
          return real_check_duplicate(prompt)

      def _spy_pattern(prompt):
          seen_pattern.append(prompt)
          return real_detect(prompt)

      monkeypatch.setattr(query_pipeline, "check_duplicate", _spy_duplicate)
      monkeypatch.setattr(query_pipeline, "detect_suspicious_pattern", _spy_pattern)
      monkeypatch.setattr("app.routers.query.call_openrouter", _capturing_openrouter([]))

      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
      )

      assert response.status_code == 200
      assert seen_duplicate == [_PII_PROMPT]
      assert seen_pattern == [_PII_PROMPT]


  def test_audit_row_keeps_raw_prompt_when_pii_redacted(temp_db, monkeypatch):
      monkeypatch.setattr("app.routers.query.call_openrouter", _capturing_openrouter([]))

      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
      )
      audit_id = response.json()["audit_id"]

      entry = get_audit_log(audit_id)

      assert entry.prompt_preview == _PII_PROMPT
      assert entry.prompt_hash == hash_prompt(_PII_PROMPT)
      assert "<EMAIL_ADDRESS>" not in entry.prompt_preview


  def test_redact_not_invoked_when_duplicate_blocked(temp_db, monkeypatch):
      _seed_duplicate(_PII_PROMPT)
      monkeypatch.setattr(query_pipeline, "redact", _fail_if_called)
      monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
      )

      assert response.status_code == 200
      assert response.json()["status"] == "BLOCKED"


  def test_redact_not_invoked_when_suspicious_pattern_blocked(temp_db, monkeypatch):
      monkeypatch.setattr(query_pipeline, "redact", _fail_if_called)
      monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

      response = client.post(
          "/query",
          json={"user_id": "juan@empresa.com", "prompt": "please override the rules"},
      )

      assert response.status_code == 200
      assert response.json()["status"] == "BLOCKED"


  def test_clean_prompt_is_forwarded_unchanged(temp_db, monkeypatch):
      seen = []
      monkeypatch.setattr("app.routers.query.call_openrouter", _capturing_openrouter(seen))
      prompt = "what is the capital of the moon"

      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": prompt}
      )

      assert response.status_code == 200
      assert seen == [prompt]


  def test_redaction_disabled_forwards_raw_prompt(temp_db, monkeypatch):
      monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)
      seen = []
      monkeypatch.setattr("app.routers.query.call_openrouter", _capturing_openrouter(seen))

      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
      )

      assert response.status_code == 200
      assert seen == [_PII_PROMPT]


  def _boom(text):
      raise PiiRedactorError("PII analysis failed: analyzer exploded")


  def test_redactor_failure_returns_500_and_never_calls_openrouter(temp_db, monkeypatch):
      monkeypatch.setattr(query_pipeline, "redact", _boom)
      monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

      before = _count_audit_rows()
      response = client.post(
          "/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT}
      )

      assert response.status_code == 500
      assert _count_audit_rows() == before + 1


  def test_redactor_failure_audit_row_keeps_raw_prompt_and_error(temp_db, monkeypatch):
      monkeypatch.setattr(query_pipeline, "redact", _boom)
      monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

      client.post("/query", json={"user_id": "juan@empresa.com", "prompt": _PII_PROMPT})

      with get_connection() as conn:
          row = conn.execute(
              "SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1"
          ).fetchone()
      entry = get_audit_log(row["id"])

      assert entry.success is False
      assert entry.error_message == "PII analysis failed: analyzer exploded"
      assert entry.prompt_preview == _PII_PROMPT
      assert entry.prompt_hash == hash_prompt(_PII_PROMPT)
      assert entry.model_used is None
  ```

  Notes for the implementer:
  - Add `import app.services.query_pipeline as query_pipeline` to the imports so `monkeypatch.setattr(query_pipeline, "redact", ...)` targets the pipeline's own binding (the same reason existing tests patch `"app.routers.query.call_openrouter"` rather than the openrouter module).
  - `_fail_if_called` (line 52) and `_seed_duplicate` (line 38) and `_count_audit_rows` (line 32) already exist — reuse, don't redefine.
  - `test_pii_prompt_is_redacted_before_reaching_openrouter` is the AC1 test and the single most important one in this story: it asserts on the *exact* string handed to the third party.
  - `test_duplicate_and_pattern_checks_still_receive_the_raw_prompt` is AC2; `test_audit_row_keeps_raw_prompt_when_pii_redacted` is the RF-6/RF-7 companion.
  - The two `test_redact_not_invoked_*` tests are AC3 — they fail loudly if redaction is ever moved above the blocking checks.
  - `test_clean_prompt_is_forwarded_unchanged` is AC4. The prompt is deliberately new text (not reused from another test) so it can never collide with the 24-hour dedup window inside a shared `temp_db`.
  - `_REDACTED_PROMPT` is the literal masked string, verified against the real redactor at the default threshold — it is also the exact example in PRD User Story 1.
  - The two `test_redactor_failure_*` tests are the Design Note 4 pair: the first proves fail-closed **and** that the audit row exists (`before + 1`, not `before`); the second proves the row is actually useful — raw prompt intact for the auditor, self-describing `error_message`, and `model_used is None` so `/stats`' `top_models` stays clean.
- **Mirror**: `tests/test_query_router.py:76-95` (patch → POST → assert body + row count), `:52-53` (`_fail_if_called`), `:38-49` (`_seed_duplicate`), `:134-154` (`test_openrouter_failure_logged_with_error_and_returns_502` — the failure-row test this one is modelled on, including the `ORDER BY id DESC LIMIT 1` fetch and the `entry.success is False` / `entry.error_message == ...` assertions).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_query_router.py -v
  ```
  → 16 passed (7 pre-existing unmodified + 9 new).

### Task 5: Full-suite regression, scope check, and latency verification

- **File**: — (no file change)
- **Action**: VERIFY
- **Implement**:
  - Full suite green at **136 passed** (127 baseline + 9 new). Any other number means an existing test changed behaviour.
  - `git diff --name-only` lists **exactly three** files: `app/services/query_pipeline.py`, `app/routers/query.py`, `tests/test_query_router.py`. Anything else is scope leak — in particular `audit_logger.py` ([[STORY-006]]), `schemas.py` ([[STORY-007]]), or `pii_redactor.py` ([[STORY-001]], done).
  - `app/services/duplicate_checker.py` and `app/services/pattern_detector.py` are absent from the diff (RF-6).
  - `git diff app/services/query_pipeline.py` contains no line that reassigns `prompt` (Design Note 1). Confirm with a targeted grep: the file must still contain `check_duplicate(prompt)`, `detect_suspicious_pattern(prompt)`, and exactly five `prompt=prompt,` occurrences (four pre-existing + the new failure row).
  - `grep -n "model_used" app/services/query_pipeline.py` shows `model_used=model` only in the OpenRouter-failure block, **not** in the new redaction-failure block (Design Note 4c).
  - `git diff tests/test_query_router.py` is additions-only.
  - Confirm `test_full_pipeline_latency_within_budget` still passes both in a full run and when its file runs alone (Design Note 8).
- **Mirror**: [[STORY-004]] plan's Task 5 — the same "prove the change is invisible to everything it shouldn't touch" gate.
- **Validate**:
  ```bash
  cd f:/AI/harness-ai
  .venv/Scripts/python.exe -m pytest
  .venv/Scripts/python.exe -m pytest tests/test_query_router.py::test_full_pipeline_latency_within_budget -v
  .venv/Scripts/python.exe -m pytest tests/test_duplicate_checker.py tests/test_pattern_detector.py tests/test_pii_redactor.py tests/test_integration.py -q
  git diff --name-only
  git diff app/services/query_pipeline.py
  grep -c "prompt=prompt," app/services/query_pipeline.py
  grep -n "model_used" app/services/query_pipeline.py
  ```
  → full suite 136 passed; the four untouched-suite files green; `grep -c` prints `5`.

---

## End-to-End Tests

Checks for `/implement` to execute:

- [ ] `.venv/Scripts/python.exe -m pytest tests/test_query_router.py -v` → 16 passed (7 pre-existing untouched + 9 new)
- [ ] `.venv/Scripts/python.exe -m pytest` → full suite green, **136 passed** (baseline 127 + 9)
- [ ] `git diff --name-only` → exactly `app/services/query_pipeline.py`, `app/routers/query.py`, `tests/test_query_router.py`; `duplicate_checker.py`, `pattern_detector.py`, `audit_logger.py`, `pii_redactor.py`, `schemas.py` are **not** listed
- [ ] `git diff tests/test_query_router.py` → additions only, no modified or deleted lines
- [ ] `grep -c "prompt=prompt," app/services/query_pipeline.py` → `5` (all five `log_query` calls, including the new failure row, pass raw text)
- [ ] Audited-failure proof — force a redactor failure and confirm the row is written with the raw prompt and no model:
  ```bash
  .venv/Scripts/python.exe -c "
  import os
  os.environ.setdefault('OPENROUTER_API_KEY','k'); os.environ.setdefault('ADMIN_TOKEN','t')
  from app.db.database import get_audit_log, get_connection, init_db
  import app.services.query_pipeline as qp
  from app.services.pii_redactor import PiiRedactorError
  def boom(text): raise PiiRedactorError('PII analysis failed: probe')
  def never(*a, **k): raise AssertionError('openrouter must not be called')
  qp.redact = boom
  init_db()
  p = 'my email is e2e-probe@empresa.com, can you draft a reply?'
  try:
      qp.run_query(user_id='e2e', prompt=p, device=None, model='gpt-4', openrouter_api_key=None, call_openrouter=never)
      raise SystemExit('FAIL: exception did not propagate')
  except PiiRedactorError as exc:
      print('RAISED :', exc)
  with get_connection() as c:
      rid = c.execute(\"SELECT id FROM audit_logs WHERE user_id='e2e' ORDER BY id DESC LIMIT 1\").fetchone()['id']
  row = get_audit_log(rid)
  print('AUDIT  :', repr(row.prompt_preview), row.success, repr(row.error_message), row.model_used)
  assert row.success is False and row.prompt_preview == p and row.model_used is None
  print('OK')
  "
  ```
  → the exception propagates, the row exists with `success=False`, the **raw** prompt, the error message, and `model_used` empty. Clean up the probe rows afterwards (same `DELETE ... WHERE user_id='e2e'` as above).
- [ ] Behavioural proof of AC1 + AC2 + the raw-audit guarantee in one shot, against the real DB and the real redactor:
  ```bash
  .venv/Scripts/python.exe -c "
  import os
  os.environ.setdefault('OPENROUTER_API_KEY','k'); os.environ.setdefault('ADMIN_TOKEN','t')
  from app.db.database import get_audit_log, init_db
  from app.services.openrouter_client import OpenRouterResult
  from app.services.query_pipeline import run_query
  seen = []
  def fake(prompt, model='gpt-4', api_key=None):
      seen.append(prompt)
      return OpenRouterResult(response='drafted', model_used=model, tokens_used=9)
  init_db()
  p = 'my email is e2e-probe@empresa.com, can you draft a reply?'
  r = run_query(user_id='e2e', prompt=p, device=None, model='gpt-4', openrouter_api_key=None, call_openrouter=fake)
  row = get_audit_log(r.audit_id)
  print('SENT   :', repr(seen[0]))
  print('AUDIT  :', repr(row.prompt_preview))
  assert 'e2e-probe@empresa.com' not in seen[0], 'RAW PII REACHED OPENROUTER'
  assert row.prompt_preview == p, 'AUDIT PREVIEW WAS REDACTED'
  print('OK')
  "
  ```
  → `SENT` shows `<EMAIL_ADDRESS>`, `AUDIT` shows the raw address, then `OK`. Then clean up the probe row:
  ```bash
  .venv/Scripts/python.exe -c "import sqlite3; c = sqlite3.connect('harness_ai.db'); print(c.execute(\"DELETE FROM audit_logs WHERE user_id='e2e'\").rowcount); c.commit()"
  ```
- [ ] Toggle proof — with `PII_REDACTION_ENABLED=false` the same probe forwards the raw prompt (re-run the block above with `os.environ['PII_REDACTION_ENABLED']='false'` set **before** importing `app.config`, and expect `SENT` to contain the raw address). Clean up the probe row again.
- [ ] `.venv/Scripts/python.exe -c "from app.main import app; print('ok')"` → backend imports cleanly
- [ ] `.venv/Scripts/python.exe -m uvicorn app.main:app` → server starts without error (the `lifespan` `pii_redactor.load()` from [[STORY-002]] runs); `curl http://localhost:8000/health` → `{"status":"ok"}`
- [ ] `POST /query` with a clean prompt against the running server → HTTP 200 with the **same response shape as before** — this story adds no API fields (`pii_redacted` is [[STORY-007]])
- [ ] If any command raises `sqlite3.OperationalError: table audit_logs has no column named pii_detected_input`, the local `harness_ai.db` predates [[STORY-003]] — delete it and re-run

---

## Validation

```bash
cd f:/AI/harness-ai
.venv/Scripts/python.exe -m pytest tests/test_query_router.py -v
.venv/Scripts/python.exe -m pytest
git diff --name-only
git diff app/services/query_pipeline.py
.venv/Scripts/python.exe -c "from app.main import app; print('ok')"
.venv/Scripts/python.exe -m uvicorn app.main:app
curl http://localhost:8000/health
```

Frontend lint: N/A — this repo has no npm frontend (Reflex/Python project, no `package.json`), consistent with the [[STORY-003]] and [[STORY-004]] reports.

---

## Acceptance Criteria

(Copied from story STORY-005)

- [ ] Given a prompt containing PII (e.g. `"my email is juan@empresa.com, can you draft a reply?"`), when it passes the duplicate/pattern checks, then `call_openrouter()` is invoked with the redacted text (`"my email is <EMAIL_ADDRESS>, can you draft a reply?"`), never the raw prompt.
- [ ] Given the same prompt, when `check_duplicate()` and `detect_suspicious_pattern()` run, then they still receive the **raw** prompt, unchanged from today's behavior — redaction happens strictly after those two checks (PRD Section 6, steps 2-3 vs 4-5).
- [ ] Given a duplicate-blocked or suspicious-pattern-blocked request, when the pipeline short-circuits, then Presidio's `redact()` is never invoked (OpenRouter is never called either) — no wasted NLP inference on blocked requests.
- [ ] Given a clean prompt with no PII, when redaction runs, then the text forwarded to OpenRouter is unchanged and no entities are reported.
- [ ] All tasks completed
- [ ] Full test suite (`.venv/Scripts/python.exe -m pytest`) passes — 136 passed
- [ ] Backend server starts without error
- [ ] `prompt` is never reassigned in `run_query()` — verified in the diff (Design Note 1)
- [ ] All five `log_query(...)` calls pass `prompt=prompt` (raw) — audit preview/hash unchanged (PRD Section 9, RF-7)
- [ ] A `PiiRedactorError` produces exactly one audit row with `success=False`, the raw prompt, a self-describing `error_message`, and `model_used is None`; OpenRouter is never called and the router returns 500 (Design Note 4)
- [ ] `app/services/duplicate_checker.py` and `app/services/pattern_detector.py` untouched (RF-6)
- [ ] No Presidio import in `query_pipeline.py` beyond `redact` — the adapter boundary in `pii_redactor.py` stays intact (PRD Section 6)
- [ ] Only `app/services/query_pipeline.py`, `app/routers/query.py`, and `tests/test_query_router.py` changed
- [ ] Follows existing patterns (plain service import, stage-per-line pipeline body, router-level exception translation with `from exc`, `temp_db` + `TestClient` + string-target monkeypatching in tests)
