---
story: STORY-004
prd: PRD-015
plan: .agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-004-v1-schemas.plan.md
epic_branch: epic/PRD-015-openai-compatible-endpoint
commit: 0be7da0
status: COMPLETE
completed: 2026-10-22
---

# Implementation Report — STORY-004: /v1 request, response, chunk and error schemas

**Plan**: `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-004-v1-schemas.plan.md`
**Epic Branch**: `epic/PRD-015-openai-compatible-endpoint`
**Commit**: `0be7da0`

## Summary

`app/models/v1_schemas.py` defines every `/v1` wire shape as a pydantic v2 model:

- `ChatCompletionRequest`
- `ChatCompletion`, together with `Choice`, `AssistantMessage`, `Usage` and `HarnessCompletionInfo`
- `ChatCompletionChunk`, together with `ChunkChoice` and `ChunkDelta`
- `ModelList` and `ModelEntry`
- `ErrorResponse` and `ErrorDetail`

It also has one id helper, `chat_completion_id(audit_id)`.

The request model uses `extra="allow"`. It types only `model`, `messages` (a list whose items stay raw) and `stream`. Every other parameter in Section 7.1 is `Optional[Any]`, so STORY-006 classifies each value and names its `param`.

Two wrap serializers match Section 7.6 exactly. The finish chunk's `delta` is `{}`, and content chunks carry no `usage` key. Every other `null` in the PRD examples stays on the wire.

`app/models/schemas.py` is unchanged.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Request model and id helper | `app/models/v1_schemas.py` | ✅ |
| 2 | Success, chunk and model-list models | `app/models/v1_schemas.py` | ✅ |
| 3 | Error models | `app/models/v1_schemas.py` | ✅ |
| 4 | Tests, including a run of the OpenAI SDK validation | `tests/test_v1_schemas.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A: this repo has no `frontend/` npm project (the UI is Reflex), and the story changes no UI |
| `tests/test_v1_schemas.py` without `openai` | ✅ 24 passed, 4 skipped (the SDK tests, skip shown by `-rs`) |
| `tests/test_v1_schemas.py` with `openai` 3.36.1 | ✅ 28 passed, 0 skipped |
| `tests/test_schemas.py` (the `/query` shapes) | ✅ unchanged and passing |
| `pytest -m "not db"` (full sweep, Docker-free) | ✅ 2709 passed, 26 skipped, 1280 deselected, 72 s |
| `git diff main -- app/models/schemas.py` | ✅ empty |
| Live `/health` | ✅ `{"status":"ok"}`, HTTP 200 |

## E2E

| Check | Result |
|-------|--------|
| With `openai` installed, the 4 AC 5 tests pass with none skipped | ✅ `openai==3.36.1`, pydantic 2.13.5 |
| `import app.main` still works | ✅ |
| `tests/test_schemas.py` passes unchanged | ✅ |
| Smoke: uvicorn starts and `GET /health` returns 200 | ✅ |

The live smoke run did not use the shared `harness-libsql-dev` container, because that container no longer exists on this machine. It followed the throwaway-container recipe instead:

1. Ran `docker run -d --name harness-libsql-e2e-s004 -p 8086:8080 -e SQLD_NODE=primary ghcr.io/tursodatabase/libsql-server:latest`.
2. Seeded the schema with `init_db()` and ran `manage_users.py create-user --user-id e2e-bootstrap --role user` (output discarded).
3. Started uvicorn on port 8017 with `DATABASE_URL=http://127.0.0.1:8086/` and called `curl /health`.
4. Afterwards, stopped uvicorn and removed the container with `docker rm -f`.

`GET /v1/models` returned 404, as expected, because STORY-009 mounts the router. No audit rows were produced, since the story adds no route.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/models/v1_schemas.py` | CREATE | +219 |
| `tests/test_v1_schemas.py` | CREATE | +354 |
| `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-004-v1-schemas.plan.md` | CREATE (archived) | +280 |

## Deviations from Plan

- **The `harness` field of `ErrorDetail` is typed as `Dict[str, Any]` rather than `dict[str, Any]`.** This matches the `typing` generics the module already uses (`List`, `Optional`). The behaviour is the same.
- **Tests 9 and 14 each check one extra case.** Test 9 adds `""` and test 14 adds `"not_found_error"`.
- **`test_request_defaults` also asserts `model_extra == {}`.**
- **`openai` 3.36.1 was left installed in the project venv.** The plan allows this, and it is not in `requirements.txt`. STORY-015 pins it in `requirements-e2e.txt`. Installing it did not change pydantic, which is still 2.13.5.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_v1_schemas.py` | `test_request_keeps_unknown_keys_in_model_extra`, `test_request_defaults`, `test_request_tells_absent_from_explicit_null`, `test_request_parameters_are_not_typed_by_pydantic`, `test_request_missing_or_malformed_required_fields_fail` (5 cases), `test_request_messages_items_stay_raw`, `test_completion_matches_section_7_4`, `test_chat_completion_id_is_the_one_derivation`, `test_completion_refuses_an_unknown_finish_reason` (3), `test_chunks_match_section_7_6` (content/finish/usage), `test_model_list_matches_section_7_7`, `test_error_matches_section_7_5`, `test_error_without_harness_keeps_the_key_as_null`, `test_error_type_is_one_of_the_four` (3), `test_openai_sdk_validates_the_completion`, `test_openai_sdk_validates_each_chunk` (3), for 28 in total |

Every shape test checks `model_dump()`, `model_dump(mode="json")` and `json.loads(model_dump_json())` against the PRD example.

## Notes for Later Stories

- **STORY-009**: `Choice.finish_reason` accepts only `stop`, `length` or `content_filter`. Map any other upstream value (OpenRouter's `"error"`, `"tool_calls"`) to `"stop"` before building it.
- **STORY-006**: tell an absent parameter from an explicit `null` with `request.model_fields_set`. Read unknown keys from `request.model_extra`.
- **STORY-013**: build chunks with `usage=None` for the content and finish chunks. The serializer then omits the key.

## Acceptance Criteria

- [x] Given a request body with `model`, `messages`, `stream` and unknown keys such as `seed` and `profile`, when `ChatCompletionRequest` parses it, then the known fields are typed, the unknown keys are preserved (`extra="allow"`, readable via `model_extra`) and nothing is dropped.
- [x] Given a body without `model` or without `messages`, or with `messages` not a list, when it parses, then validation fails; `messages` items stay raw mappings (the normalizer judges them, not pydantic).
- [x] Given a `ChatCompletion` built with audit id 1842, when it is serialized, then it matches PRD Section 7.4's example field for field.
- [x] Given a `ChatCompletionChunk`, a `ModelList` and an `ErrorResponse`, when serialized, then they match Sections 7.6, 7.7 and 7.5 respectively, including `choices: []` on the usage chunk and the `harness` object inside `error`.
- [x] Given each example serialized to JSON, when the OpenAI Python SDK's own types validate it, then it validates; the test is skipped when `openai` is not installed.
- [x] All tasks completed
- [x] Backend imports and starts without error
- [x] Follows existing patterns
