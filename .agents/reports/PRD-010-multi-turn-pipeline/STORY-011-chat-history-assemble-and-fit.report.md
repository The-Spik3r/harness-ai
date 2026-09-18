---
story: STORY-011
prd: PRD-010
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-011-chat-history-assemble-and-fit.plan.md
epic_branch: epic/PRD-010-multi-turn-pipeline
commit: PENDING
status: COMPLETE
completed: 2026-09-18
---

# Implementation Report — STORY-011: chat_history.assemble and fit

**Plan**: `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-011-chat-history-assemble-and-fit.plan.md`
**Epic Branch**: `epic/PRD-010-multi-turn-pipeline`
**Commit**: `PENDING`

## Summary

`app/services/chat_history.py` ships with exactly two public functions and no state.

`assemble(identity, session_id)` makes one call to `chat_sessions.messages_for`, keeps only `kind == "assistant"` rows, and emits `Message("user", row.prompt), Message("assistant", row.content)` per row. D4 therefore holds *by construction*: `duplicate`, `injection`, `forbidden`, `upstream_error`, `internal_error` and `context_limit` rows are never read, so there is no deny-list of kinds to keep in step with the bubble model, and STORY-013's new kind is excluded the moment it exists. PRD 6.4 fact 1 is satisfied because each pair is rebuilt from the assistant row's own `prompt`, which is why a session whose first user bubble was never persisted still yields its opening exchange.

`fit(history, new_turn, max_messages, max_characters)` is pure. It appends the new turn and, while either limit is broken, drops `kept[2:]` — the oldest whole exchange, both halves together — counting as it goes, with `[new_turn]` as a floor it never goes below. AC 5's `([new_turn], len(history) // 2)` falls out of that loop rather than being special-cased, which is deliberate: a separate "does the new turn alone fit" branch would duplicate the character arithmetic and could disagree with it.

Nothing in production imports the module. STORY-012 is its first caller, which is the same criterion STORY-001 held itself to and is what makes this story provably unable to change existing behaviour.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Module docstring, imports, `assemble` | `app/services/chat_history.py` | ✅ |
| 2 | `_characters` helper and `fit` | `app/services/chat_history.py` | ✅ |
| 3 | AC 1 — pairs per assistant row, `id` order | `tests/test_chat_history.py` | ✅ |
| 4 | AC 2 — no unanswered kind contributes; first exchange survives; no redaction | `tests/test_chat_history.py` | ✅ |
| 5 | AC 3 — three empty cases, unusable prompt, one read, error propagation | `tests/test_chat_history.py` | ✅ |
| 6 | AC 4/5 — `fit`'s stated behaviours | `tests/test_chat_history.py` | ✅ |
| 7 | The seam with `query_pipeline._context_limit_exceeded` | `tests/test_chat_history.py` | ✅ |
| 8 | Randomized property tests (200 cases) | `tests/test_chat_history.py` | ✅ |
| 9 | Module-shape invariants | `tests/test_chat_history.py` | ✅ |
| 10 | Whole-suite verification | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Module imports (`assemble` structure, AST) | ✅ |
| `fit` behaviour (plan's inline assertions) | ✅ |
| Pre-existing architecture tests (`test_chat_sessions.py`) | ✅ 4 passed |
| New test module | ✅ 58 passed |
| Neighbours (`chat_sessions`, `messages`, `context_limit`) | ✅ 191 passed |
| Full suite | ✅ 2199 passed, 25 skipped |
| E2E | ✅ 7/7 |
| No pre-existing production file modified | ✅ |

Frontend lint and `curl /health` from the command's generic checklist do not apply: this story adds no route and touches no frontend file, and the repo has no linter or formatter. "Validate" here means pytest against the local libSQL dev server.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/chat_history.py` | CREATE | +195 |
| `tests/test_chat_history.py` | CREATE | +896 |

## Deviations from Plan

Four, none of them changing what is asserted.

1. **Lowercase builtin generics instead of the plan's `List` / `Tuple`.** The plan's snippets imported `List`, `Sequence`, `Tuple` from `typing`. The two modules this one sits between spell it `list[Message]` (`app/models/messages.py:80`, `app/services/chat_sessions.py:324`), so the signatures are `-> list[Message]` and `-> tuple[list[Message], int]`, with only `Sequence` imported from `typing`. `query_pipeline`'s `Optional[Tuple[...]]` is the minority form in this repo.

2. **Task 1's validate command was rewritten to count calls through `ast` rather than `str.count`.** As written it asserted `inspect.getsource(h.assemble).count('messages_for') == 1` and failed — because `assemble`'s own docstring names `chat_sessions.messages_for` in prose, making two textual hits for one call. The AST form asserts what the check meant (`calls.count('messages_for') == 1`) and is immune to documentation. The same substitution applies to the `CHAT_HISTORY_ENABLED` and `list_chat_messages` clauses, which the module docstring also names deliberately — and is exactly the distinction the repo's own architecture tests draw at `tests/test_chat_sessions.py:1400-1405`, where only `ast.Name` and `ast.Attribute` nodes count.

3. **The 200 property cases and the two limit sweeps are iterated inside one test each, not parametrized.** The plan asked for `@pytest.mark.parametrize("seed", range(200))`. That collected 339 tests in this module, and `tests/conftest.py:155` resets the database before *every* test, autouse — so each case opened a real libSQL connection for a function that performs no I/O. The run died on `os error 10048` (ephemeral ports exhausted). All 200 cases still run, and every assertion names its seed, so a failure reproduces exactly; that naming was the only thing parametrization bought here. Test count fell from 339 to 58.

4. **`test_no_production_module_imports_chat_history_yet` walks imports through `ast` rather than grepping.** The plan said grep and allow comment hits. An import walk needs no allowance: `app/db/models.py:284` mentions `chat_history.fit` in a comment and is invisible to it, while an actual import anywhere under `app/`, `chat_ui/` or `scripts/` is caught.

One addition beyond the plan: **`test_the_random_cases_actually_exercise_trimming`**. The 200-case property test would make 200 green assertions about a branch `fit` never took if `_random_case` happened to generate only comfortable limits, so the distribution is asserted — currently 64 untrimmed, 99 trimmed, 37 at the floor. This closes the one vacuity trap the plan named (R4) but did not pin with a test.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_chat_history.py` | 58 tests. **AC 1**: pair-per-assistant-row with `(role, content)` tuples so intra-pair order is pinned; 20 exchanges on one tied `created_at` proving `id` order; two-messages-per-exchange for 0/1/5. **AC 2**: `test_no_unanswered_kind_contributes_a_message` parametrized over seven kinds including `context_limit`, each sandwiched between two real exchanges; an all-noise transcript; the missing-first-user-bubble case; `assemble` does not redact. **AC 3**: history off with a `_Tripwire` over `chat_sessions.database` (no statement issued, not merely an empty result); foreign session with ana's own non-empty result asserted in the same test; unknown session; `NULL`/`""` prompt skipped; empty `content` kept (the deliberate asymmetry); exactly one read via a counting spy; `ChatSessionError` propagates. **AC 4/5**: message-limit and character-limit tables with the boundary rows exact; never-splits sweep; new-turn-last sweep over both limits; limits-are-arguments-not-settings; both floor paths; no input mutation; odd history rejected for lengths 1/3/5; empty history accepted. **Seam**: `_context_limit_exceeded(fitted) is None` across five trimming shapes, and non-`None` naming `"characters"` on the floor row. **Properties**: 200 seeded random cases × five properties, with "order preserved" asserted as a contiguous-suffix identity; determinism; case-distribution guard. **Shape**: exports exactly `assemble`/`fit`; no Reflex/`chat_ui` import; no `settings`/`database` reference in code; nothing in production imports the module. |

## Acceptance Criteria

- [x] `assemble` reads through `chat_sessions.messages_for` and returns `[Message("user", row.prompt), Message("assistant", row.content), …]` for `kind == "assistant"` rows only, in `id` order
- [x] No `user`, `duplicate`, `injection`, `forbidden`, `upstream_error`, `internal_error` or `context_limit` row contributes a message; a session whose first user bubble was never persisted still yields its first exchange
- [x] History off, a foreign session and an unknown session all return `[]`; an assistant row with `prompt` `NULL` or empty is skipped
- [x] `fit` drops the oldest whole exchange repeatedly until both limits hold, never splits a pair, puts the new turn last, and returns `(history + [new_turn], 0)` when everything fits
- [x] A new turn that alone exceeds `max_characters` returns `([new_turn], len(history) // 2)`, and the pipeline then refuses it (asserted, not described); `fit` is pure, with property tests over random histories
- [x] All tasks completed
- [x] Full test suite green (2199 passed, 25 skipped)
- [x] No pre-existing file modified — the diff is two new code files
- [x] `assemble` makes exactly one `messages_for` call, re-sorts nothing, re-checks no ownership
- [x] `fit` reads no `settings` and mutates no input
- [x] No Reflex or `chat_ui` import in `app/services/chat_history.py`
- [x] The two pre-existing repo-wide architecture tests still pass with a new module under `app/`
- [x] Follows existing patterns

## Notes for STORY-012

- `chat_history.assemble` is sync and does one read: call it through `run_in_pipeline`. `fit` is pure and belongs inline.
- **Delete `test_no_production_module_imports_chat_history_yet`** when wiring the first caller. Its docstring says so; leaving it would block the story.
- `fit` raises `ValueError` on an odd-length history. `assemble`'s output is always pair-shaped, so pass it through unchanged rather than slicing it.
- The limits are STORY-012's to supply: `settings.CONTEXT_MAX_MESSAGES` and `settings.CONTEXT_MAX_CHARACTERS`, read at the call site.
- `fit`'s second return value is the count for `chat_messages.history_trimmed` (STORY-010's column) and STORY-013's footer. It counts **exchanges**, not messages.

## Environment Note

The full suite hit a single fixture-level socket failure twice during this story — first `os error 10048` on `tests/test_chat_history.py`, then `os error 10060` on an unrelated `tests/test_session_rail.py` test. A different test and a different errno each run, each passing in isolation: the shared libSQL dev server stalling under sustained load, which `tests/conftest.py:82-122` already documents as landing "as a setup ERROR on whichever unrelated test came next … never in isolation". Restarting `harness-libsql-dev` cleared it, and the suite then ran green at 2199 passed. Deviation 3 above independently cut this module's connection churn by 83%.
