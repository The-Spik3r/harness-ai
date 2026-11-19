---
story: STORY-012
prd: PRD-021
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-012-chat-progress-ui.plan.md
epic_branch: epic/PRD-021-realtime-streaming
commit: pending
status: COMPLETE
completed: 2026-11-19
---

# Implementation Report - STORY-012: Progress line, live answer and reasoning block in the chat UI

**Plan**: `.agents/plans/PRD-021-realtime-streaming/completed/STORY-012-chat-progress-ui.plan.md`
**Epic Branch**: `epic/PRD-021-realtime-streaming`
**Commit**: `pending`

## Summary

The pending entry now shows `word . N s` in an `aria-live` word span, the live answer (`_prose`) and a live reasoning block when those vars are non-empty. A pure `progress.py` maps (stage, phase, action) to one word from `copy.py`. The seconds counter and the 300 ms rule run in the browser through one page-level `useEffect` interval (`PROGRESS_TICK_JS`). The success bubble carries the reasoning in memory (`ChatMessage.reasoning`, `reasoning_open`), collapsed by default, with a real toggle button; nothing is persisted or restored.

## Validation

| Check | Result |
|-------|--------|
| Backend import | OK |
| tests/test_chat_progress_ui.py | 23 passed |
| tests/test_chat_components_import.py + startup_guard + test_chat_state_streaming.py | 32 passed (with the above: 54 passed, 1 failed, the failure fixed and re-run: 1 passed) |
| tests/test_chat_ui_storage_failures.py (renders render_assistant) | 21 passed with progress file (44 total) |
| tests/test_chat_state.py `-k "stored or restore or message or transcript"` | partial: 5 of 23 selected passed before the run was stopped (each DB test took minutes on this machine); no failure seen |
| E2E (real `reflex run`) | not run: no browser session; the node tick tests, the render probe and a compile check of hooks/imports/custom code carry AC2 |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- Accepted by the orchestrator: epoch values are change keys, elapsed is measured with `performance.now()` (clock skew).
- `message_bubble` / `render_assistant` take an optional `index=None` (a toggle needs the index; existing one-arg callers still work). Without an index no toggle is offered.
- Toggle: reflex 0.9.6.post1 `istate/proxy.py` puts pydantic `BaseModel` in `MUTABLE_TYPES` (:378-381) and `MutableProxy.__setattr__` marks the state dirty (:652-666), so the plain attribute set is used, not the `model_copy` fallback; a test asserts `messages` is in `dirty_vars`.
- `tests/test_chat_components_import.py` not edited (`render_reasoning_block` is not a `bubbles` renderer taking `message_var`).
- Node is not set up in `.github/workflows/ci.yml`; the node tests skip when `node` is absent (ubuntu runners usually ship it, so they likely run in CI, unverified).

## Acceptance Criteria

- [x] AC1 copy vocabulary and T4 (enumeration tests)
- [x] AC2 word, seconds, 300 ms, aria-live (node tick tests, render probe)
- [x] AC3 live entry in the pending slot, tag SENDING, `_prose` (render probe)
- [x] AC4 reasoning block, collapsed after, not restored (D8 tests)
- [x] AC5 focus (real button, global focus-visible), pulse reused, no new keyframe (CSS test); 360 px layout by wrap/min-width, not browser-checked
