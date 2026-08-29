---
story: STORY-014
prd: PRD-005
plan: .agents/plans/PRD-005-rbac/completed/STORY-014-chat-ui-login.plan.md
epic_branch: epic/PRD-005-rbac
commit: PENDING
status: COMPLETE
completed: 2026-08-29
---

# Implementation Report — STORY-014: Chat UI login replaces the free-text user_id prompt

**Plan**: `.agents/plans/PRD-005-rbac/completed/STORY-014-chat-ui-login.plan.md`
**Epic Branch**: `epic/PRD-005-rbac`
**Commit**: `PENDING` (filled in after commit)

## Summary

Replaced `chat_ui`'s free-text `user_id` prompt with a real token login. `login()` (renamed from `submit_user_id()`) validates the submitted token via `app.services.identity.resolve()` — the same function `require_identity` uses at the HTTP boundary — and, on success, sets only `ChatState.user_id` from the resolved `Identity`. The credential itself is stored in `_token`, a Reflex backend-only var (never synchronized to the client, never settable by a client event); `ChatState` holds no field named `token` or `role` anywhere. `_do_send()` re-resolves a fresh `Identity` from `_token` on every `send()` call and passes it to `run_query(identity=..., ...)`, fixing a pre-existing break: `run_query()` had required an `Identity` since STORY-010, but this file still called it with the old `user_id=` keyword, which the current suite confirmed was silently swallowed into a bogus `internal_error` bubble by the catch-all exception handler (6 failing tests at baseline). The `QueryResponse` union's fourth member, `QueryBlockedForbiddenResponse`, now has its own explicit `isinstance` branch and its own bubble (`kind="forbidden"`) instead of falling through the old catch-all `else` into the injection bubble.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Login/token copy replaces user-id session-gate copy | `chat_ui/chat_ui/copy.py` | ✅ |
| 2 | `ChatMessage` gains `required_permission` | `chat_ui/chat_ui/models.py` | ✅ |
| 3 | Distinct ink for the forbidden verdict | `chat_ui/chat_ui/theme.py` | ✅ |
| 4 | Login/logout, backend-only token, per-call re-resolution, explicit response branches | `chat_ui/chat_ui/state.py` | ✅ |
| 5 | `render_forbidden()` | `chat_ui/chat_ui/components/bubbles.py` | ✅ |
| 6 | Register `"forbidden"` match arm | `chat_ui/chat_ui/components/chat.py` | ✅ |
| 7 | `login_gate()` + sign-out header control | `chat_ui/chat_ui/components/shell.py` | ✅ |
| 8 | Import `login_gate` | `chat_ui/chat_ui/chat_ui.py` | ✅ |
| 9 | Rename + new kind/renderer | `tests/test_chat_components_import.py` | ✅ |
| 10 | Rewrite for login/logout, identity-based `send()`, forbidden branch | `tests/test_chat_state.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `python -c "import app.routers.query"` | ✅ |
| `chat_ui` component-layer import (`copy`, `theme`, `models`, `state`, `bubbles`, `chat`, `shell`) | ✅ |
| `tests/test_chat_state.py` | ✅ 36 passed (was 28 passed / 6 failed pre-story) |
| `tests/test_chat_components_import.py` | ✅ 4 passed |
| `tests/test_query_router.py`, `tests/test_auth_dependencies.py`, `tests/test_query_pipeline_authorization.py` | ✅ 96 passed combined with the above (no regression) |
| Full suite `pytest tests/` | ✅ 380 passed |
| E2E | ✅ 8/8 (see below) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/copy.py` | UPDATE | Session-gate + verdict-tag copy replaced/added |
| `chat_ui/chat_ui/models.py` | UPDATE | +1 field (`required_permission`) |
| `chat_ui/chat_ui/theme.py` | UPDATE | +2 tokens (`INK_FORBIDDEN`, `TINT_FORBIDDEN`) |
| `chat_ui/chat_ui/state.py` | UPDATE | Full rewrite of the login/session/send flow |
| `chat_ui/chat_ui/components/bubbles.py` | UPDATE | +1 renderer (`render_forbidden`) |
| `chat_ui/chat_ui/components/chat.py` | UPDATE | +1 match arm |
| `chat_ui/chat_ui/components/shell.py` | UPDATE | `user_id_gate()` → `login_gate()`; header control renamed |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | Import rename |
| `tests/test_chat_components_import.py` | UPDATE | +1 renderer/kind, rename |
| `tests/test_chat_state.py` | UPDATE | Full rewrite: new fixtures, login/logout tests, forbidden test, re-resolution test, revocation test |
| `tests/test_copy.py` | UPDATE (deviation) | `USER_ID_PROMPT_TITLE`/`SHELL_CHANGE_USER_LABEL` → `LOGIN_PROMPT_TITLE`/`SHELL_LOGOUT_LABEL` |
| `tests/test_pii_redaction_integration.py` | UPDATE (deviation) | Registered 4 legitimately superseded `test_chat_state.py` test names in `_DELIBERATELY_SUPERSEDED_TESTS` |

## Deviations from Plan

Two files outside the plan's "Files to Change" list needed updates, both caught immediately by running the full `pytest tests/` suite (not just the plan's named validation targets) before considering the story done:

1. **`tests/test_copy.py`** — imports `USER_ID_PROMPT_TITLE` and `SHELL_CHANGE_USER_LABEL` from `chat_ui.chat_ui.copy`, both renamed by Task 1. The story's Technical Notes named only `tests/test_chat_state.py`; this file wasn't anticipated. Fixed with a straight rename to `LOGIN_PROMPT_TITLE` / `SHELL_LOGOUT_LABEL`.
2. **`tests/test_pii_redaction_integration.py`** — contains a repo-wide meta-test (`test_no_pre_epic_test_function_was_removed_or_renamed`, added by an earlier PRD) that diffs every `tests/*.py` file against `git merge-base main HEAD` and fails if a test function disappears without being listed in `_DELIBERATELY_SUPERSEDED_TESTS`. Renaming `submit_user_id()`/`reset_user_id()` to `login()`/`logout()` legitimately superseded four old test names. Registered them in `_DELIBERATELY_SUPERSEDED_TESTS["tests/test_chat_state.py"]` following the exact convention STORY-013 used for the same guard.

No other deviations. All ten plan tasks were implemented as specified, including the backend-only-var design decision documented in the plan (rather than a cross-state `get_state()` split).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_chat_state.py` | `test_chat_state_send_forbidden_response_renders_its_own_bubble_not_injection`, `test_chat_state_send_reresolves_role_on_every_call`, `test_chat_state_holds_no_token_or_role_var`, `test_chat_state_send_when_credential_revoked_mid_session_appends_internal_error`, `test_chat_state_login_empty_token_shows_error`, `test_chat_state_login_invalid_token_shows_error_and_stays_locked`, `test_chat_state_login_deactivated_token_rejected`, `test_chat_state_login_valid_token_sets_user_id_and_clears_error`, `test_chat_state_logout_clears_session_and_credential`, `test_chat_state_send_passes_resolved_identity_and_prompt_to_run_query` (rewrite of the old user_id-keyword test) |

## Acceptance Criteria

- [x] Given the login form, when a valid token is submitted, then the session becomes authenticated and the chat is usable
- [x] Given an invalid or deactivated token, when it is submitted, then an error is shown and the chat stays locked
- [x] Given an authenticated session, when `send()` runs, then the role is re-resolved server-side on every call, never read from a state var
- [x] Given `ChatState`, when inspected, then it holds no token and no role — only the authenticated `user_id`, set exclusively by `login()`
- [x] Given a `QueryBlockedForbiddenResponse`, when returned, then `send()` handles it in an explicit `isinstance` branch and renders its own bubble, not the suspicious-pattern one

## End-to-End Verification (manual, browser-driven)

1. ✅ `reflex run` starts; login gate (not free-text box) renders with a masked "Access token" field
2. ✅ Empty submission → "Enter a token to sign in." — chat stays locked
3. ✅ Invalid token → "Invalid or deactivated token." — chat stays locked
4. ✅ Valid token (minted via `scripts/manage_users.py create-user`) → chat opens; header shows `SENDING AS demo.reviewer` and a "Sign out" control
5. ✅ Sent a real prompt → pipeline ran end to end with `identity=`, real OpenRouter round trip, assistant bubble rendered (`CLEARED`, `gpt-4 · 23 tokens · #17`)
6. ✅ Deactivated the user mid-session (`manage_users.py deactivate-user`) while the tab stayed open, sent another prompt → `FAULT` bubble ("Your session credential is no longer valid. Sign out and sign in again."), no crash, `pending` correctly reset
7. ✅ "Sign out" → login gate reappears, transcript cleared
