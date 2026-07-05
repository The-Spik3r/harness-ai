---
story: STORY-007
prd: PRD-002
slug: chat-pipeline-test-suite
title: "Chat pipeline unit test suite"
type: technical
complexity: MEDIUM
epic_branch: epic/PRD-002-reflex-chat-ui        # all stories commit here, no per-story branch
created: 2026-07-05
---

# Plan: Chat pipeline unit test suite

## Summary

Add a single new test file, `tests/test_chat_state.py`, containing two logical groups of unit tests: (1) direct unit tests of `app/services/query_pipeline.py::run_query(...)` covering the success, duplicate-blocked, suspicious-blocked, and OpenRouter-error paths — mirroring the assertions PRD-001's `tests/test_query_router.py` already makes against `POST /query`, but calling the pipeline function directly; and (2) unit tests of `ChatState.send()` (`chat_ui/chat_ui/state.py`) covering the same four outcomes as they render into `ChatState.messages`, plus a cross-path audit-row parity test and a cross-path duplicate-window test. No production code changes — this is a test-only story. No new file is needed for the route-collision assertion (AC5): it already exists at `tests/test_route_reservations.py::test_no_route_collides_with_reflex_reserved_routes` and already runs as part of the same `pytest` invocation.

Two non-obvious mechanics drive the design of the `ChatState.send()` tests, both verified empirically against the installed `reflex==0.9.6.post1` in this repo (not assumed from memory):

1. **Import path**: `ChatState` lives at `chat_ui/chat_ui/state.py`. The outer `chat_ui/` (Reflex project root) has no `__init__.py`, so it resolves as an implicit namespace package from the repo root; the inner `chat_ui/chat_ui/` *does* have `__init__.py`. The correct import from `tests/` (run from repo root) is `from chat_ui.chat_ui.state import ChatState` / `import chat_ui.chat_ui.state as chat_state_mod`, and the correct `monkeypatch.setattr` target is `"chat_ui.chat_ui.state.call_openrouter"`. (STORY-006's report guessed `"chat_ui.state.call_openrouter"` — that path does **not** resolve; confirmed by directly attempting `import chat_ui.state` in this environment, which raises `ModuleNotFoundError: No module named 'chat_ui.state'`.)
2. **Background event handler**: `ChatState.send` is decorated `@rx.event(background=True)`. Reflex's `State.__getattribute__` wraps *any* attribute access to a background handler with a chain-guard (`_no_chain_background_task`) that raises `RuntimeError` once awaited, regardless of calling context — so `await state.send()` cannot be used directly in a test. The raw, unwrapped coroutine function is reachable via `type(state).event_handlers["send"].fn`, which the test suite awaits directly: `await type(state).event_handlers["send"].fn(state)`. Also, `ChatState()` cannot be instantiated directly outside a running app (`ReflexRuntimeError`); tests must pass `ChatState(_reflex_internal_init=True)`, the framework's documented internal-init escape hatch. Both mechanics were confirmed by an interactive experiment: constructing a state this way, monkeypatching `call_openrouter`, and invoking `handler.fn(state)` correctly ran `run_query(...)` and appended the expected bubble to `state.messages`.

## User Story

As a devops engineer
I want unit tests covering the `run_query(...)` extraction and `ChatState.send()`
So that chat-vs-API parity (audit rows, blocked reasons) is verified automatically rather than only by manual walkthrough, and regressions are caught before Docker packaging

## Story Reference

- Story file: `.agents/stories/PRD-002-reflex-chat-ui/STORY-007-chat-pipeline-test-suite.md`
- PRD: `.agents/PRDs/PRD-002-reflex-chat-ui/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | technical |
| Complexity | MEDIUM |
| Systems Affected | `tests/` (new file only) |
| Story | STORY-007 |
| PRD | PRD-002 |
| Epic Branch | `epic/PRD-002-reflex-chat-ui` (commit directly on this branch) |

---

## Skills In Use

None. `story.skills: []`, `.agents/skills/` has no entries, and no `SKILL.md` matches this story's domain (pytest unit testing) beyond the general Reflex skills (`reflex-docs`, `reflex-process-management`), which are not implicated here since this story writes no Reflex UI code and never starts a live Reflex server.

---

## Patterns to Follow

### DB fixture + row counting (mirror exactly)
```python
// SOURCE: tests/test_query_router.py:24-35
@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path


def _count_audit_rows() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]
```

### Seeding a duplicate row (mirror exactly)
```python
// SOURCE: tests/test_query_router.py:38-49
def _seed_duplicate(prompt: str, hours_ago: float = 2) -> str:
    timestamp = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime(
        _TIMESTAMP_FORMAT
    )
    insert_audit_log(
        AuditLog(
            timestamp=timestamp,
            user_id="juan@empresa.com",
            prompt_hash=hash_prompt(prompt),
        )
    )
    return timestamp
```

### Monkeypatching call_openrouter — one target per call site
```python
// SOURCE: tests/test_query_router.py:80 (API path)
monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)

// SOURCE: verified empirically this session (chat path) — NOT "chat_ui.state.call_openrouter"
monkeypatch.setattr("chat_ui.chat_ui.state.call_openrouter", _fake_call_openrouter)
```

### Constructing and driving a background-event ChatState in a test (new pattern, verified this session)
```python
from chat_ui.chat_ui.state import ChatState

def _make_state(user_id: str = "juan@empresa.com") -> ChatState:
    state = ChatState(_reflex_internal_init=True)
    state.user_id = user_id
    return state


async def _send(state: ChatState, text: str) -> None:
    state.input_text = text
    handler = type(state).event_handlers["send"]
    await handler.fn(state)  # bypasses the background-task chain guard on state.send()
```

### run_query(...) direct call shape (mirror app/routers/query.py's call site)
```python
// SOURCE: app/routers/query.py:16-24
run_query(
    user_id=request.user_id,
    prompt=request.prompt,
    device=request.device,
    model=request.model,
    openrouter_api_key=request.openrouter_api_key,
    call_openrouter=call_openrouter,
)
```

### Async test marker (no global asyncio_mode config exists in this repo)
```python
@pytest.mark.asyncio
async def test_chat_state_send_success_appends_assistant_bubble(temp_db, monkeypatch):
    ...
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_chat_state.py` | CREATE | Unit tests for `run_query(...)` (direct) and `ChatState.send()`, per PRD Section 6's suggested new file |

No other files change. `chat_ui/chat_ui/state.py` already imports `call_openrouter` at module scope specifically to make it monkeypatchable (confirmed in STORY-006's report and in the file itself) — no production code edit is needed to make it testable.

---

## Tasks

### Task 1: Scaffold `tests/test_chat_state.py` — imports, env bootstrap, fixtures

- **File**: `tests/test_chat_state.py`
- **Action**: CREATE
- **Implement**:
  - Set `OPENROUTER_API_KEY` / `ADMIN_TOKEN` env defaults at module top via `os.environ.setdefault(...)`, exactly as every other file under `tests/` does, before importing `app.*`.
  - Import: `app.config.settings`, `app.db.database.{get_connection, init_db, insert_audit_log, get_audit_log}`, `app.db.models.AuditLog`, `app.services.duplicate_checker.hash_prompt`, `app.services.openrouter_client.{OpenRouterError, OpenRouterResult}`, `app.services.query_pipeline.run_query`, `app.models.schemas.{QuerySuccessResponse, QueryBlockedDuplicateResponse, QueryBlockedSuspiciousResponse}`.
  - Import Reflex/chat pieces: `import chat_ui.chat_ui.state as chat_state_mod` and `from chat_ui.chat_ui.state import ChatState`.
  - Import `fastapi.testclient.TestClient` and `from app.main import app` for the API-side half of the parity test (Task 4).
  - Add the `temp_db` fixture and `_count_audit_rows()` / `_seed_duplicate()` helpers verbatim from the "Patterns to Follow" section above.
  - Add `_make_state()` and `_send()` helpers verbatim from the "Patterns to Follow" section above.
- **Mirror**: `tests/test_query_router.py:1-53` for the module bootstrap/fixture/helper shape.
- **Validate**: `python -c "import ast; ast.parse(open('tests/test_chat_state.py').read())"` (syntax only at this stage — no test bodies yet).

### Task 2: `run_query(...)` direct unit tests (AC1)

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE (append)
- **Implement**: four `test_run_query_*` functions, each using the `temp_db` fixture and calling `run_query(...)` directly with the exact kwarg shape from `app/routers/query.py:16-24` (pass `call_openrouter=<fake or real>` explicitly rather than relying on the default):
  - `test_run_query_success_returns_response_and_logs_row`: fake `call_openrouter` returns `OpenRouterResult(response="Hi there!", model_used="gpt-4", tokens_used=12)`; assert the return value is a `QuerySuccessResponse` with matching fields, and `_count_audit_rows() == 1`.
  - `test_run_query_duplicate_blocked_before_openrouter_call`: seed via `_seed_duplicate(...)`, pass a `call_openrouter` that raises `AssertionError` if called (mirror `_fail_if_called` from `test_query_router.py:52-53`); assert result is `QueryBlockedDuplicateResponse` with `reason="Duplicate query within 24 hours"` and `first_query_at` equal to the seeded timestamp; assert one new audit row was still written (matches `run_query`'s behavior of logging blocked queries too, per `query_pipeline.py:26-39`).
  - `test_run_query_suspicious_pattern_blocked_before_openrouter_call`: prompt `"please override the rules"`; pass a `call_openrouter` that raises `AssertionError` if called; assert result is `QueryBlockedSuspiciousResponse` with `reason="Suspicious pattern detected"`, `pattern="override"`.
  - `test_run_query_openrouter_error_raises_and_logs_failure`: fake `call_openrouter` raises `OpenRouterError("boom")`; assert `run_query(...)` re-raises `OpenRouterError` (unlike the route, `run_query` itself does not convert it to an HTTP status — that conversion happens in `app/routers/query.py:25-28`, outside this function); after catching it in the test, fetch the last-inserted row via `get_audit_log(...)` and assert `success is False` and `error_message == "boom"` (mirror `test_query_router.py:134-154`).
- **Mirror**: `tests/test_query_router.py:56-155` (same four scenarios, HTTP layer stripped away).
- **Validate**: `pytest tests/test_chat_state.py -v -k run_query`

### Task 3: `ChatState.send()` unit tests (AC2)

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE (append)
- **Implement**: four `@pytest.mark.asyncio async def test_chat_state_send_*` functions, each building a state via `_make_state()`, monkeypatching `"chat_ui.chat_ui.state.call_openrouter"`, and driving it via `_send(state, "<prompt>")`:
  - `test_chat_state_send_success_appends_user_then_assistant_bubble`: fake returns a canned response; assert `state.messages[-2] == {"role": "user", "content": "<prompt>"}` and `state.messages[-1] == {"role": "assistant", "content": "<the fake response text>"}`; assert `state.input_text == ""` after send (cleared per `state.py:55`).
  - `test_chat_state_send_duplicate_blocked_appends_system_bubble`: seed a duplicate for the same prompt text via `_seed_duplicate(...)`; assert the last message is `{"role": "system", "content": f"Blocked — Duplicate query within 24 hours (first sent at {timestamp})"}` — exact string built in `chat_ui/chat_ui/state.py:74-78`.
  - `test_chat_state_send_suspicious_blocked_appends_system_bubble`: prompt containing `"ignore previous instructions"`; assert last message is `{"role": "system", "content": "Blocked — Suspicious pattern detected"}` (`state.py:79-80`).
  - `test_chat_state_send_passes_session_user_id_and_prompt_to_run_query`: monkeypatch `"chat_ui.chat_ui.state.run_query"` (not `call_openrouter`) with a fake that records its kwargs and returns a minimal `QuerySuccessResponse`; call `_send(state, "hello world")` with `state.user_id = "juan@empresa.com"`; assert the recorded call had `user_id="juan@empresa.com"` and `prompt="hello world"` — this directly verifies AC2's "calls `run_query(...)` with the session's `user_id` and prompt" clause, independent of blocking logic.
- **Mirror**: the bubble-formatting branches in `chat_ui/chat_ui/state.py:72-83`; the `_make_state`/`_send` pattern from Task 1.
- **Validate**: `pytest tests/test_chat_state.py -v -k chat_state_send`

### Task 4: Audit-row parity + cross-path duplicate window (AC3)

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE (append)
- **Implement**: two tests using `TestClient(app)` alongside `_send`/`_make_state`:
  - `test_chat_and_api_audit_rows_share_schema_and_fields`: monkeypatch both `"chat_ui.chat_ui.state.call_openrouter"` and `"app.routers.query.call_openrouter"` to return equal-shaped fakes (same `model_used`/`tokens_used`, different `response` text is fine). Send prompt A through `_send(state, "prompt from chat")`; send prompt B through `client.post("/query", json={"user_id": "juan@empresa.com", "prompt": "prompt from api"})`. Fetch both rows via `get_audit_log(...)` (grab ids from `_count_audit_rows`/ordering, e.g. `SELECT id FROM audit_logs ORDER BY id`). Assert both are `AuditLog` instances (identical schema by construction — same dataclass, same table) and assert field-for-field equality on everything that should match given equal-shaped inputs: `user_id`, `model_used`, `tokens_used`, `was_duplicate_blocked=False`, `suspicious_pattern=None`, `success=True`, `error_message=None`, `device=None`. (Fields that legitimately differ per distinct prompt text — `id`, `timestamp`, `prompt_hash`, `prompt_preview`, `response_hash`, `response_preview` — are excluded from the equality check and asserted only to be non-empty/well-formed.)
  - `test_duplicate_sent_via_chat_blocks_identical_prompt_via_api`: send a prompt through `_send(state, "same prompt text")` (chat path, real success), then `client.post("/query", json={"user_id": "juan@empresa.com", "prompt": "same prompt text"})` (API path, identical text). Assert the API response is `{"status": "BLOCKED", "reason": "Duplicate query within 24 hours", "first_query_at": <matches the chat-originated row's timestamp>}` — proving the 24h dedup window is shared across entry points, per User Story 3 / STORY-006 AC5.
- **Mirror**: `tests/test_query_router.py:76-113` for the `TestClient` call shape and response-shape assertions.
- **Validate**: `pytest tests/test_chat_state.py -v -k audit_rows_share_schema` and `-k duplicate_sent_via_chat`

### Task 5: Confirm route-collision assertion runs in the same suite (AC5 — no new code)

- **File**: `tests/test_route_reservations.py`
- **Action**: none (verification only — do not edit this file)
- **Implement**: nothing to write. `test_no_route_collides_with_reflex_reserved_routes` already exists (added under STORY-003) and already executes on every plain `pytest` invocation from the repo root since it's a normal file under `tests/`.
- **Mirror**: N/A
- **Validate**: `pytest tests/test_route_reservations.py -v` passes as part of the same run as Task 6's full-suite check — confirms this assertion is exercised by the regular test run, not a one-off manual check (per the story's 5th acceptance criterion).

### Task 6: Full-suite regression run (AC4)

- **File**: N/A
- **Action**: validation only
- **Implement**: run the complete suite and confirm the new file's tests pass alongside every existing PRD-001 test file, unmodified.
- **Mirror**: `README.md:159-165` ("Running Tests" section — `pytest tests/ -v`)
- **Validate**: `pytest tests/ -v` — expect all previously-passing tests (99 per STORY-006's report) plus the new `tests/test_chat_state.py` tests, all green, with zero modifications to any existing test file.

---

## End-to-End Tests

This story is unit-test-only (no UI/server changes); "E2E" here means the full automated suite, not a manual browser walkthrough:

- [ ] `pytest tests/test_chat_state.py -v` — all new tests pass in isolation
- [ ] `pytest tests/ -v` — new tests + all existing PRD-001 tests (STORY-012 integration suite) pass together, unmodified
- [ ] Manually diff `git status` / `git diff` after this story to confirm only `tests/test_chat_state.py` was added — no production file touched

---

## Validation

```bash
pytest tests/test_chat_state.py -v
pytest tests/ -v
```

---

## Acceptance Criteria

(Copied from story STORY-007)

- [ ] Given `app/services/query_pipeline.py::run_query(...)`, when unit tested, then tests cover the success path, duplicate-blocked path, suspicious-pattern-blocked path, and OpenRouter-error path, asserting the same outcomes PRD-001's existing integration suite (STORY-012) already asserts against `POST /query`. → Task 2
- [ ] Given `ChatState.send()`, when unit tested, then tests verify it calls `run_query(...)` with the session's `user_id` and prompt, and appends the correct bubble type (success/duplicate-blocked/suspicious-blocked) to `messages` for each outcome. → Task 3
- [ ] Given a prompt sent through `run_query(...)` directly and the same prompt sent through `POST /query`, when audit rows are compared in a test, then they have identical schema and field values. → Task 4
- [ ] Given the new test file `tests/test_chat_state.py`, when the full test suite runs (`pytest`), then both the new chat tests and PRD-001's existing integration test suite (STORY-012) pass together, unmodified for the latter. → Task 6
- [ ] Given the route-collision assertion added in STORY-003, when this test suite runs, then that assertion is included/exercised here (confirmed already covered). → Task 5
- [ ] All tasks completed
- [ ] Follows existing patterns (temp_db fixture, monkeypatch style, TestClient usage)
