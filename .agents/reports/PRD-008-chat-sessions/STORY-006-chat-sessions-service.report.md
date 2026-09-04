---
story: STORY-006
prd: PRD-008
plan: .agents/plans/PRD-008-chat-sessions/completed/STORY-006-chat-sessions-service.plan.md
epic_branch: epic/PRD-008-chat-sessions
commit: pending
status: COMPLETE
completed: 2026-09-03
---

# Implementation Report — STORY-006: app/services/chat_sessions.py: the ownership rule and the CHAT_HISTORY_ENABLED short-circuit in one place

**Plan**: `.agents/plans/PRD-008-chat-sessions/completed/STORY-006-chat-sessions-service.plan.md`
**Epic Branch**: `epic/PRD-008-chat-sessions`
**Commit**: `pending`

## Summary

`app/services/chat_sessions.py` is new: eight public functions — `create`, `list_for`, `get`, `rename`, `touch`, `delete`, `append_message`, `messages_for` — each taking an `Identity` as its first, undefaulted parameter and passing `identity.user_id` into the nine store functions STORY-004 and STORY-005 built. Nothing else in the codebase converts an `Identity` into an owner, and `identity.role` is never read: PRD Section 9 divides the two questions, and this module answers only "whose row is this".

Every function opens with `if not settings.CHAT_HISTORY_ENABLED:` and returns the value the story names — `None` for `create` and `append_message`, `False` for `touch`/`rename`/`delete`, `[]`/`None` for the reads — **before** touching `app.db.database`. The setting is read at call time on every call, never captured at import, so a test can flip it without reloading the module.

`StorageError` is wrapped in a module-owned `ChatSessionError` through one `_wrapped(operation)` context manager rather than nine copies of the same `except` arm, with the service function's own name in the message and the `StorageError` preserved on `__cause__`.

`tests/test_chat_sessions.py` was extended in place a third time, as its own docstring directed for STORY-005 and as this story's AC 9 names, with 59 new cases in a labelled STORY-006 section.

## The one design conflict, and how it was resolved

AC 6 requires `create(identity, first_prompt)` to title the session from the prompt with the derivation **delegated** to STORY-012 — which puts `derive_title(prompt)` in `chat_ui/chat_ui/formatting.py`. This story's Technical Notes forbid importing anything from `chat_ui/`, the repository's import direction is one-way (`chat_ui` → `app`, never back), and STORY-012 is `todo` and not a dependency of this story, so `derive_title` does not exist yet.

**Resolved with the user before the plan was written**: the deriver is injected —

```python
def create(identity: Identity, first_prompt: str, derive_title: Callable[[str], str]) -> Optional[str]:
```

The service calls the rule and does not own it, `first_prompt` stays in the signature AC 6 spells, `app/` gains no dependency on `chat_ui/`, and this story ships with no dependency on STORY-012. `derive_title` has no default on purpose: any default would be a derivation living in this module, which is the reimplementation AC 6 forbids. Three tests pin this — the deriver's sentinel return is what lands in the title column, `create`'s body contains no slice or split, and the parameter is undefaulted so omitting it is a `TypeError`.

**Consequence for STORY-013**: its call site reads `chat_sessions.create(identity, prompt, formatting.derive_title)`.

## Two judgment calls recorded in the code

**1. `append_message` raises for a foreign session rather than returning `None`, and that satisfies AC 7.** The store raises one `StorageError` with one message for the foreign *and* the unknown session, deliberately (STORY-005: "a read that finds nothing is an ordinary outcome, a write that silently lands nowhere is not"). AC 7 requires the caller not be able to *distinguish* the two, not that they be silent — and `test_append_message_fails_identically_for_foreign_and_unknown_sessions` asserts the two messages are byte-identical. Returning `None` instead would have collided with the flag-off `None` and handed STORY-014's degraded arm a successful-looking write that never happened.

**2. The module does `from app.db import database` and calls qualified**, unlike `duplicate_checker`'s name-import. AC 4 requires proving the flag-off arm "by patching the database module and observing that nothing on it was called" — one qualified attribute access lets a single `_Tripwire` object cover all nine store functions, where name-imports would need nine patches and would silently miss a tenth.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Module docstring, imports, `ChatSessionError`, `_wrapped` | `app/services/chat_sessions.py` | ✅ |
| 2 | `create`, `list_for`, `get`, `rename`, `touch`, `delete` | `app/services/chat_sessions.py` | ✅ |
| 3 | `append_message`, `messages_for` | `app/services/chat_sessions.py` | ✅ |
| 4 | STORY-006 test section, 59 cases | `tests/test_chat_sessions.py` | ✅ |
| 5 | Full-suite regression | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `python -c "import app.services.chat_sessions"` | ✅ |
| `python -c "from app.main import app"` | ✅ |
| `pytest tests/test_chat_sessions.py` | ✅ 115 passed (26 STORY-004 + 30 STORY-005 + 59 new) |
| `pytest tests/test_config.py tests/test_db.py tests/test_identity.py tests/test_authz.py tests/test_duplicate_checker.py` | ✅ 235 passed |
| Full suite | ⚠️ 1298 passed, 7 failed — all pre-existing, see below |
| E2E | ✅ 6/6 |

Frontend lint is not applicable: this story touches no file under `chat_ui/` and the project has no `npm` frontend.

### The 7 full-suite failures are pre-existing, not this story

The same seven `tests/test_untouched_app.py` guards STORY-002, STORY-003, STORY-004 and STORY-005 each recorded. Measured rather than assumed, the way those stories did it: `app/services/chat_sessions.py` was moved aside and `tests/test_chat_sessions.py` stashed, then the guard suite was run against the clean tree at `HEAD` (`493fa3a`):

```
7 failed, 6 passed   # baseline, none of this story's code present
7 failed, 6 passed   # with this story's code
```

The two failure lists are identical name for name; only the reported duration differs. This story introduces none of them. They are PRD-006-scoped guards asserting `app/` is unchanged since that PRD's baseline, and PRD-007 and PRD-008 have changed `app/` by design ever since. Re-baselining that guard remains its own piece of work and is deliberately not done here.

### A libSQL dev-server degradation was hit and is not a code defect

The first run of `tests/test_chat_sessions.py` reported `96 passed, 19 errors`, every error a fixture failure in `conftest._reset_database` with `Hrana: api error: status=400 ... {"message":"The stream has expired due to inactivity","code":"STREAM_EXPIRED"}` — not one assertion failure among them. `docker restart harness-libsql-dev` and a re-run produced `115 passed`. This is the recorded pattern for this dev server: mass fixture errors mean restart the container, not bisect the code.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/chat_sessions.py` | CREATE | +279 |
| `tests/test_chat_sessions.py` | UPDATE | +656/-2 |

## Deviations from Plan

1. **A ninth structural guard was added beyond the plan's list**: `test_no_module_outside_the_service_calls_the_store_session_functions`. AC 2's second half — "no caller outside it reaches `database.py`'s session functions" — is a property about what future code may do, and the plan only had a guard for the flag half of that sentence. It discovers the store's session/message surface from `dir(database)` rather than listing it, so it covers functions added later. Both guards pass on the current tree.

2. **`_service_statements_of` was added rather than widening STORY-004's `_statements_of`** to take a module. Widening it would have made two stories' assertions fail together for one story's reason; the helper is nine lines and the duplication is the cheaper of the two.

3. **The plan's Task 2 heading reads "The five session functions" and then lists six.** A typo in the heading only; six were implemented, as the body of the task and the surface table both specify.

4. **`THE_WRITES` / `THE_READS` tuples from the plan's sketch were dropped** in favour of inline `pytest.mark.parametrize` tables that pair each function with its expected flag-off value. The tuples would have been a second list to keep in step with the parametrize tables, which is the staleness the discovered-not-enumerated rule exists to avoid.

Everything else matched the plan.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_chat_sessions.py` (STORY-006 section, 59 cases) | **Surface (AC 1, 2)**: `test_the_eight_service_functions_are_declared`, `test_the_service_exposes_exactly_those_eight`, `test_every_service_function_takes_an_identity_first`, `test_no_service_function_accepts_a_bare_user_id`, `test_every_service_function_passes_identity_user_id_to_the_store`, `test_no_module_outside_the_service_calls_the_store_session_functions` · **Flag off (AC 3, 4)**: `test_writes_return_a_usable_value_and_issue_nothing_when_history_is_off` ×5, `test_reads_return_empty_and_issue_nothing_when_history_is_off` ×3, `test_history_off_reaches_the_database_for_none_of_the_eight`, `test_the_flag_is_read_at_call_time_not_captured_at_import`, `test_no_module_outside_the_service_branches_on_chat_history_enabled` · **Limit (AC 5)**: `test_list_for_takes_no_limit_parameter`, `test_list_for_applies_the_configured_limit`, `test_list_for_reflects_a_changed_limit_without_a_reload`, `test_messages_for_is_not_capped_by_the_session_limit` · **Delegation (AC 6)**: `test_create_delegates_the_title_derivation_and_stores_its_result`, `test_create_calls_the_deriver_exactly_once`, `test_create_does_not_call_the_deriver_when_history_is_off`, `test_the_service_reimplements_no_title_rule`, `test_derive_title_has_no_default`, `test_the_service_imports_nothing_from_chat_ui` · **Ownership (AC 7)**: `test_every_read_returns_nothing_for_a_foreign_identity`, `test_a_foreign_session_is_indistinguishable_from_an_unknown_one`, `test_every_write_driven_by_a_foreign_identity_changes_no_row`, `test_the_break_glass_admin_identity_gets_no_special_case`, `test_two_identities_round_trip_without_seeing_each_other` · **Error wrapping (AC 8)**: `test_every_function_wraps_storage_failure_in_chat_session_error` ×8, `test_the_wrapped_error_keeps_the_storage_error_as_its_cause` ×8, `test_the_wrapped_error_names_the_service_operation` ×8, `test_a_storage_error_never_escapes_as_itself`, `test_append_message_fails_identically_for_foreign_and_unknown_sessions`, `test_a_working_database_raises_nothing` |

## E2E Results

| # | Check | Result |
|---|-------|--------|
| 1 | `harness-libsql-dev` running | ✅ (started, then restarted after the stream expiry above) |
| 2 | `pytest tests/test_chat_sessions.py` — all three sections | ✅ 115 passed |
| 3 | Adjacent suites unaffected | ✅ 235 passed |
| 4 | Full suite, no new regression | ✅ (7 pre-existing, measured) |
| 5 | Manual round trip: create → append → messages → touch → list → get, then the same driven by a foreign identity | ✅ owner sees everything; `bob` gets `None`/`[]`/`False` and one `ChatSessionError`; ana's title and message survive intact; `delete` then empties both |
| 6 | Same round trip with `CHAT_HISTORY_ENABLED = False` | ✅ every call returned its flag-off value, the deriver was never called, and the session and message counts were byte-identical before and after |

E2E 5 and 6 were driven through real resolved `Identity` objects (`issue_token` → `hash_token` → `insert_user` → `resolve`) against the live dev database, not fabricated ones.

## Acceptance Criteria

- [x] Exposes `create`, `list_for`, `get`, `rename`, `touch`, `delete`, `append_message`, `messages_for`, each taking an `Identity` rather than a bare `user_id` string
- [x] Every function passes `identity.user_id` into `database.py`; no caller outside the service reaches the store's session functions (both halves guarded structurally)
- [x] Flag off: no statement issued on any write; `create` → `None`, `append_message` → `None`, `touch`/`rename`/`delete` → `False`
- [x] Flag off: reads return `[]`/`None` without issuing a statement — asserted with `_Tripwire`, which fails on contact rather than on an empty result
- [x] `list_for` passes `CHAT_SESSION_LIMIT` and takes no `limit` parameter
- [x] `create` derives the title by delegation, never reimplementation — via an injected `derive_title` (see the conflict resolution above)
- [x] A foreign `session_id` is indistinguishable from a missing one, through every function
- [x] `StorageError` is wrapped in `ChatSessionError`, in `duplicate_checker`'s pattern, with the cause preserved
- [x] `tests/test_chat_sessions.py` has its own assertion for the flag-off, foreign-identity and error-wrapping cases
- [x] All tasks completed
- [x] Full test suite passes (7 pre-existing `test_untouched_app.py` failures, measured against a clean baseline)
- [x] No `CHAT_HISTORY_ENABLED` reference anywhere outside this module and `app/config.py` — guarded by `ast`
- [x] `app/services/chat_sessions.py` imports nothing from `chat_ui/` — guarded by `ast`
- [x] Follows existing patterns
