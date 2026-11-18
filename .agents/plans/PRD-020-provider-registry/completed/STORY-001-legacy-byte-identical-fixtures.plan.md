---
story: STORY-001
prd: PRD-020
slug: legacy-byte-identical-fixtures
title: Record the legacy byte-identical fixtures before any refactor
type: REFACTOR
complexity: medium
epic_branch: epic/PRD-020-provider-registry
created: 2026-11-18
---

# Plan: Record the legacy byte-identical fixtures before any refactor

## Summary

Add `tests/fixtures/prd020_legacy/` (plain `.json`/`.txt`, a README) and one replay test, `tests/test_prd020_legacy_fixtures.py`, recorded against the UNCHANGED `app/`. Upstream bytes are captured from the real `call_openrouter` through `httpx.MockTransport` (its `client=` parameter), not re-derived. `/v1/models*` and `/query` are driven through `TestClient(app)` and compared on raw `response.content`. This is the D1 contract that STORY-005 (adapter), 007 (routing), 011 (`/v1/models`) and 012 (`/query` default model) must keep green without editing a fixture.

- Story: `.agents/stories/PRD-020-provider-registry/STORY-001-legacy-byte-identical-fixtures.md` (AC text lives there)
- PRD sections used: 6.2, 11 (first two bullets), 12 Phase 1, 14 risk 1, D1
- Systems affected: tests only. **Nothing under `app/` changes** (`git diff main -- app/` must stay empty).

## Design Decisions

- Not a critical story: no design points from the orchestrator.
- **Record = replay.** Fixtures are written once by the test itself when `PRD020_RECORD_FIXTURES=1` is set (a single `_check(rel_path, actual_bytes)` helper: record mode writes, normal mode asserts `actual == path.read_bytes()`). Run record mode ONCE, against the unchanged code, then read every file. The README says the env var exists for this story only and a later story must never run it.
- **Compare bytes, not parsed dicts.** Payload fixture = the exact `request.content` bytes MockTransport saw (key order and separators included). Responses = `response.content`. Pretty-printing would hide a reorder; do not.
- **Fixed inputs.** Base URL pinned with `monkeypatch.setattr(settings, "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")` and `OPENROUTER_API_KEY="test-key"` (httpx error text embeds the URL, so a stub's ephemeral port would make strings non-deterministic). `MODEL_ALLOWLIST` and `V1_TOOL_MODELS` pinned to the defaults (`app/config.py:215`, `:397`) so a developer `.env` cannot change a fixture. Monkeypatch only; nothing persists.
- **Normalization** (README lists each): only `audit_id` (int) and `audit_ref` (UUID) in `/query` success bodies, regex-replaced by `<AUDIT_ID>` / `<AUDIT_REF>` before writing and comparing. Everything else is compared as is: `/v1/models` `created` is the constant `0` (`app/models/v1_schemas.py:279`), the payload has no ids or timestamps, and error strings are deterministic under the pinned URL. State this explicitly.

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`; no UI).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Fake upstream | `tests/test_openrouter_client.py:21-47` | `_FakeClient`/`_response` shape; use the stronger `httpx.Client(transport=httpx.MockTransport(handler))` so the real `post(url, headers=, json=)` serializes the body |
| Error assertions | `tests/test_openrouter_client.py` (`pytest.raises(OpenRouterError)`, `.upstream_status`, `.retryable`) | attributes defined at `app/services/openrouter_client.py:15-40` |
| Stub | `tests/test_stub_openrouter.py:78-96` (`stub` fixture) | only for the one stub test; MockTransport is preferred for byte capture |
| /v1 client + users | `tests/test_v1_models.py:24-55` | `TestClient(app, headers=...)`; `temp_db` override with `insert_user(User(...))`; admin user as `tests/test_main.py:113` (`role="admin"`, `hash_token`) |
| Pipeline authz | `tests/test_query_pipeline_authorization.py:197-231` | role `user` lacks `query:byok`; role `admin` holds it (`app/services/authz.py:55-70`) |
| Env prologue | `tests/test_openrouter_client.py:5-6` | `os.environ.setdefault(...)` before app imports |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_prd020_legacy_fixtures.py` | CREATE | capture helpers, record/replay, all five AC groups |
| `tests/fixtures/prd020_legacy/README.md` | CREATE | normalization, record procedure, "never edit" rule |
| `tests/fixtures/prd020_legacy/{upstream,v1,query}/*.json`, `errors.json` | CREATE | the recorded bytes (Tasks 2-5) |
| story file, `.agents/PRDs/PRD-020-provider-registry/index.md` | UPDATE | plan link, status (done by the planner) |

`tests/fixtures/` does not exist yet and no `.gitignore` rule matches it (checked).

## Tasks

### Task 1: Capture helpers

- **File**: `tests/test_prd020_legacy_fixtures.py`
- **Implement**: `_capture(responder)` returns `(client, calls)`: an `httpx.Client(transport=httpx.MockTransport(handler))`; the handler appends `{"path": request.url.path, "url": str(request.url), "authorization": ..., "content_type": ..., "body": request.content}` and returns the scripted `httpx.Response` (or raises the scripted exception). Add `_check(...)` (record/replay) and an autouse fixture pinning settings. Assert only the two harness headers (`Authorization`, `Content-Type`, set at `openrouter_client.py:241-244`), never httpx-generated ones (`user-agent`, `accept`, `content-length`).
- **Mirror**: `tests/test_openrouter_client.py:21-47`
- **Validate**: record run, then normal run (see Validation).

### Task 2: Upstream request fixtures (AC1)

Each case writes `upstream/<case>.request.json` (exact payload bytes) and `upstream/<case>.meta.json` (`path` `/api/v1/chat/completions`, `Authorization`, `Content-Type`):
1. `text_minimal`: one user message, `model="gpt-4"`, `api_key=None` (settings key). Asserts no `stream` key (never set, `:245-248`).
2. `text_params`: system + user + assistant turns, all four `GenerationParams` (`:249-253`; order temperature, max_tokens, top_p, stop).
3. `tool_request`: `ToolParams(tools, tool_choice, parallel_tool_calls)` (`:257-262`) with an assistant `tool_calls` turn and a `tool` message so `_wire_message` is exercised (open it for the shapes); plus `tool_minimal` with the two optional fields None (omitted).
4. `byok_key`: `api_key="sk-caller-key"` (clearly fake) while the settings key is `test-key`; meta shows `Authorization: Bearer sk-caller-key`.
5. `base_url_trailing_slash`: trailing-slash base URL still posts to `.../chat/completions` (`rstrip('/')`, `:268`); path only.

### Task 3: Error and edge fixtures (AC2)

One entry per case in `errors.json` (`{"case": {"message","upstream_status","retryable"}}`, `indent=2`, `sort_keys`, ASCII), from the real call: `messages_empty` (`:232-233`), `key_missing` (settings key `""`, `api_key=None`, `:235-239`), `http_400`, `http_429`, `http_503`, `transport_timeout` (handler raises `httpx.ConnectTimeout("timed out")`), `transport_connect_error` (`_classify_http_error`, `:188-197`), `body_not_json`, `body_no_choices`, `choices_empty_list`, `message_without_content`, `content_null` (`:302`), `content_null_with_tool_calls_no_tools_sent` (suffix `; tool calls are not supported (PRD-017)`, `:303-304`), `usage_missing` (`:310-316`), `usage_without_total_tokens`, and the `_parse_tool_calls` shape errors with `tools=` sent (`:157-184`: not a list, non-object, empty id, wrong type, no name, non-string arguments, duplicate id). Also record the success `OpenRouterResult` fields for a full usage body (`prompt/completion tokens`, `finish_reason`) and for `usage` without the split (None), since STORY-005 moves this parsing.
- AC2 names the stub: add one test with the `stub` factory (`tests/test_stub_openrouter.py:78`) and a `fail_status: 503` rule. Its message holds the ephemeral port, so assert only `upstream_status`, `retryable` and the `OpenRouter request failed: ` prefix, no fixture bytes.

### Task 4: `/v1/models` fixtures (AC3)

`TestClient(app)` with a seeded admin and user token (module `temp_db` override, as `tests/test_v1_models.py:50-55`). Record status, `x-should-retry` (when present) and raw `response.content` for: list as admin and as user; `/v1/models/openai/gpt-4o` as admin and as user (id with `/`, `app/routers/v1.py:461-475`); and the missing-model 404 (`/v1/models/no-such-model`, `MODEL_NOT_FOUND`, `:470-473`) for both roles. Files `v1/list.<role>.json`, `v1/one.<role>.json`, `v1/missing.<role>.json`, statuses and headers in `v1/meta.json`. `tests/test_v1_models.py` compares parsed JSON; raw bytes are the gap this closes.

### Task 5: `/query` fixtures (AC4)

- Route `app.routers.query.call_openrouter` (imported at `app/routers/query.py:14`, passed at `:186`) through a `monkeypatch` wrapper that calls the REAL `call_openrouter` with `client=<MockTransport client>`, so upstream bytes and the HTTP body are captured together. Open the pipeline's upstream call in `app/services/query_pipeline.py` first and match the exact arguments it passes (do not guess the signature).
- `POST /query` with seeded `user` and `admin` tokens: (a) success, allowed model, user; (b) success with NO `model` key (default `gpt-4`, `app/models/schemas.py:18`; record the upstream payload `model`: STORY-012's contract); (c) BYOK as admin (success, upstream `Authorization` shows the caller key); (d) not-allowed model as user, blocked body with `query:model:<m>` (`query_pipeline.py:404-413`, `schemas.py:117-120`); (e) BYOK key as user, `query:byok` blocked body (`:415-423`); (f) admin with an off-list model succeeds (wildcard passthrough that STORY-007 must keep); (g) upstream 503 through `/query` (open the error arm in `app/routers/query.py` and record status + body).
- Normalize `audit_id`/`audit_ref` by regex; everything else raw bytes.

### Task 6: README (AC5)

`tests/fixtures/prd020_legacy/README.md`: purpose (D1, risk 1), layout, pinned settings, the normalization list, how it was recorded (record mode, once, unchanged `app/`), the rule that later stories keep the suite green WITHOUT editing a fixture (a failing fixture is a legacy regression to report, never a stale file), and that `git diff main -- app/` was empty for STORY-001. Add `test_readme_documents_normalization` asserting it names `<AUDIT_ID>`, `<AUDIT_REF>` and the no-edit sentence.

## End-to-End Tests

- [ ] `TestClient(app)` GET `/v1/models`, `/v1/models/{id}`, POST `/query` replay equal the files (Tasks 4-5).
- [ ] Real `call_openrouter` over MockTransport replays payload + headers (Task 2).
- [ ] Record run once, then normal run twice; `git status` shows only the new files and the replay changes nothing.
- [ ] Manual mutation check, not committed: reorder a payload key in a scratch copy and confirm the replay fails.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 PRD020_RECORD_FIXTURES=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_prd020_legacy_fixtures.py   # once
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_prd020_legacy_fixtures.py tests/test_openrouter_client.py tests/test_v1_models.py
git diff main -- app/    # must print nothing
```

No `app/` change, so `test_untouched_app.py` is not needed. No test renamed or removed, so `test_pii_redaction_integration.py` is not needed. The test needs `temp_db` (libSQL on :8080; `docker restart harness-libsql-dev` if fixture setup errors). It is unmarked, so it runs in the default suite.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 payload + headers, text and tool | 1, 2 | `test_prd020_legacy_fixtures.py::test_upstream_request_*` |
| AC2 error strings, status, retryable | 3 | `::test_error_cases_match_recorded` (+ stub 503 test) |
| AC3 `/v1/models` bodies (+404) | 4 | `::test_v1_models_bodies_match_recorded` |
| AC4 `/query` success, `query:model:`, `query:byok` | 5 | `::test_query_bodies_match_recorded` |
| AC5 normalization README, empty `app/` diff, no-edit rule | 6 | `::test_readme_documents_normalization`; `git diff main -- app/` empty |

Plus: all tasks completed, validation passes, follows existing patterns.

## Risks / Open Questions

- Story line refs are off by one or two (payload `:241-262`, URL `:268`); the cites above were opened.
- httpx serializes `json=` itself; separators could differ across httpx versions. Fixtures pin the version in `requirements.txt`, which CI also uses; a mismatch fails loudly: report, do not edit.
- Error strings built from `str(httpx.HTTPStatusError)` embed the URL and an httpx docs link; that is today's output, pin it as is.
- `/query` cases (b), (f), (g) go beyond the AC list on purpose (orchestrator note: STORY-007/012 contracts).
