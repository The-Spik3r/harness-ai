---
story: STORY-003
prd: PRD-002
plan: .agents/plans/PRD-002-reflex-chat-ui/completed/STORY-003-mount-fastapi-single-port.plan.md
epic_branch: epic/PRD-002-reflex-chat-ui
commit: 336427a
status: COMPLETE
completed: 2026-07-05
---

# Implementation Report — STORY-003: Mount existing FastAPI app into Reflex (single-port process)

**Plan**: `.agents/plans/PRD-002-reflex-chat-ui/completed/STORY-003-mount-fastapi-single-port.plan.md`
**Epic Branch**: `epic/PRD-002-reflex-chat-ui`
**Commit**: `336427a`

## Summary

Wired `chat_ui/chat_ui/chat_ui.py` to mount the existing `app.main.app` FastAPI instance via `rx.App(api_transformer=fastapi_app)`, with a `sys.path` fix so the cross-directory import from `chat_ui/`'s own project root reaches the repo-root `app` package. Added `tests/test_route_reservations.py` to assert no harness route collides with Reflex's reserved routes. During manual `reflex run --env prod` validation, discovered and fixed a real functional gap: Reflex's `api_transformer` mounts the passed FastAPI app as a Starlette sub-app under a *new* outer Starlette app whose own lifespan runs instead — `app.main`'s `lifespan` (and its `init_db()` call) never fires when mounted this way. Fixed by calling `init_db()` eagerly at import time in `chat_ui.py`, which is safe because table creation is idempotent (`CREATE TABLE IF NOT EXISTS`).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Mount `app.main.app` via `api_transformer`, fix `sys.path`, add eager `init_db()` | `chat_ui/chat_ui/chat_ui.py` | ✅ |
| 2 | Route-collision assertion vs. Reflex reserved routes | `tests/test_route_reservations.py` | ✅ |
| 3 | Manual single-port validation (`reflex run --env prod`) | N/A (validation) | ✅ |
| 4 | Full PRD-001 test suite regression check | N/A (validation) | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `chat_ui/chat_ui/chat_ui.py` parses (AST) | ✅ |
| `pytest tests/test_route_reservations.py` | ✅ 2 passed |
| Full `pytest` suite | ✅ 99 passed (97 pre-existing + 2 new) |
| `reflex run --env prod` boots, logs single port | ✅ `App running at: http://0.0.0.0:3000/` |
| `GET /` (port 3000) | ✅ 200 (Reflex frontend) |
| `GET /health` (port 3000) | ✅ 200 `{"status":"ok"}` |
| `POST /query` (port 3000) | ✅ reaches pipeline — 502 from invalid test OpenRouter key (expected, not 404) |
| `GET /audit` (port 3000, bearer token) | ✅ 200, shows the row from the `/query` call above |
| `GET /stats` (port 3000, bearer token) | ✅ 200, correct aggregate counts |
| Port 8000 | ✅ not listening (single-port confirmed) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | +14/-1 |
| `tests/test_route_reservations.py` | CREATE | +26 |

## Deviations from Plan

1. **`api_transformer` location** (anticipated in the plan itself, not a surprise during implementation): wired in `chat_ui/chat_ui/chat_ui.py` via `rx.App(api_transformer=...)`, not in `rxconfig.py` as the story's literal wording said — confirmed against live Reflex docs/source for `reflex==0.9.6.post1` before implementing, since `rx.Config` has no such field.
2. **New finding during Task 3 validation, not anticipated in the plan**: Reflex's `api_transformer` mount does not propagate `app.main`'s ASGI lifespan, so `init_db()` never ran, causing `/audit` and `/stats` to 500 with `no such table: audit_logs`. Fixed by calling `init_db()` eagerly at module import time in `chat_ui.py` (idempotent, no schema risk). This is a one-line addition beyond what the plan's Task 1 specified, kept as small and targeted as the rest of the mount wiring.
3. `reflex run` regenerated a nested `chat_ui/requirements.txt` (containing only `reflex==0.9.6.post1`) as a side effect of the CLI invocation. STORY-002 had deliberately removed this file (root `requirements.txt` is the single source of truth). Left the regenerated file on disk (deletion was blocked by the permission classifier as an unrequested destructive action) but did not stage or commit it — it remains an untracked, gitignored-adjacent artifact with no effect on the repo.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_route_reservations.py` | `test_no_route_collides_with_reflex_reserved_routes`, `test_expected_harness_routes_present` |

## Acceptance Criteria

- [x] `api_transformer` is configured to point at `app.main:app` (implemented in `chat_ui/chat_ui/chat_ui.py` via `rx.App(api_transformer=...)` — see Deviation 1 for why this differs from the story's `rxconfig.py` wording)
- [x] Running with `reflex run --env prod` (single-port mode), `GET /health`, `POST /query`, `GET /audit`, `GET /stats` are all reachable on the same port the chat UI's frontend is served from (verified: port 3000 only, port 8000 not listening)
- [x] No harness route collides with Reflex's reserved routes (`/ping`, `/_event`, `/_upload`) — enforced by `tests/test_route_reservations.py`
- [x] PRD-001's existing test suite passes unmodified (99/99, including the 2 new tests)
- [x] All tasks completed
- [x] Follows existing patterns (module-level env defaults + `TestClient`, no new test infra)
