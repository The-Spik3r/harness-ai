---
story: STORY-023
prd: PRD-008
plan: .agents/plans/PRD-008-chat-sessions/completed/STORY-023-untouched-app-guard-rescope.plan.md
epic_branch: epic/PRD-008-chat-sessions
commit: PENDING
status: COMPLETE
completed: 2026-09-04
---

# Implementation Report — STORY-023: retire the provenance guards, census the pinned suites

**Plan**: `.agents/plans/PRD-008-chat-sessions/completed/STORY-023-untouched-app-guard-rescope.plan.md`
**Epic Branch**: `epic/PRD-008-chat-sessions`
**Commit**: `PENDING`

## Summary

`tests/test_untouched_app.py` asserted PRD-006's containment by diffing a pinned baseline (`_BASE = d3e6279`) against the **working tree**. Seven of its thirteen cases had been failing since PRD-007 merged, taking CI down on `main` and on every branch cut from it.

The four working-tree provenance guards are deleted, the byte-equality pin on the six pinned suites is replaced by a `test_` **name census**, and the three durable guards are byte-unmodified. `pytest -q` now reports **1333 passed, 0 failed**. No `xfail`, no `skip` beyond the git-unavailable concession the module already made, no `--deselect`, no `ci.yml` edit, and no re-baselining of `_BASE`.

## The evidence AC 3 requires: PRD-006's claim was true, only its measurement was wrong

PRD-006's containment claim is **confirmed**. The 40 commits from `577a285` (STORY-001, PRD-006's first) to `99afc9f` (STORY-020's record commit) touched:

| Pinned path | Files touched by PRD-006's 40 commits |
|---|---|
| `app/` | **0** |
| `requirements.txt`, `chat_ui/requirements.txt` | **0** |
| `Caddyfile`, `chat_ui/rxconfig.py` | **0** |
| the six `_CHAT_MODULES` | **0** |
| the six pinned test suites | **0** |

Verified with `git log --name-only --pretty=format: 99afc9f --not 8ada67a d3e6279 -- <path>` (where `8ada67a` is the `main` side of the merge `0f77203`), each returning empty. The only `chat_ui/chat_ui/components/` files those commits touched are the console's own additions: `admin_shell.py`, `register.py`, `summary.py`.

**The claim is preserved as this finding. Only the broken instrument was discarded.**

### Why the instrument was broken

`_changed_since_base()` diffed `_BASE` against the **working tree**, which answers "what changed since PRD-006 began", never "what did PRD-006 change". The two coincide only while PRD-006 is the last thing on the branch, and they stopped coinciding at `0f77203` ("Merge branch 'main' into epic/PRD-006-admin-console"), which pulled PRD-005's `app/` work into the range. **The guards were already unmeasurable before PRD-007 existed.** By PRD-008 they reported 15 files under `app/`, one requirements file and all six chat modules — none of it PRD-006's doing.

### Correction to the story's Technical Notes

The story states that diffing `_BASE` "against PRD-006's merge, **or against its branch tip**, still reports twelve files under `app/`, because both endpoints sit above the `main` merge". The branch-tip half is **incorrect**: `0f77203`'s first parent is `99afc9f`, so the `main` merge sits *above* PRD-006's tip, not below it.

- `git diff --name-only d3e6279 99afc9f -- app/` → **0 files** (the tip)
- `git diff --name-only d3e6279 0f77203 -- app/` → **12 files** (the merge)

The twelve-file figure is real but belongs only to the merge commit. The `--not` formulation and the plain tip diff agree.

This does **not** weaken the story's conclusion. The defect was the *working-tree* endpoint, not the choice of upper bound. Pinned between two immutable commits the assertion becomes a historical fact that can never fail again, and a test that can only pass is not a test — so the guards are still correctly retired rather than repaired.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Start libSQL dev server; capture pre-change baseline (7 failed, 6 passed) | — | ✅ |
| 2 | Delete the four working-tree provenance guards and their dead support | `tests/test_untouched_app.py` | ✅ |
| 3 | Replace the byte-equality pin with a name census | `tests/test_untouched_app.py` | ✅ |
| 4 | Add the superseded-names allowlist for `test_chat_state.py` | `tests/test_untouched_app.py` | ✅ |
| 5 | Rewrite the module docstring around the defect | `tests/test_untouched_app.py` | ✅ |
| 6 | Prove the census has teeth (tamper test) | `tests/test_db.py` (reverted) | ✅ |
| 7 | Confirm the three durable guards are byte-unmodified | `tests/test_untouched_app.py` | ✅ |
| 8 | Full-suite green and commit | — | ✅ |
| 8b | *(deviation)* Record the five retired names in the sibling census guard | `tests/test_pii_redaction_integration.py` | ✅ |

## Deviations from Plan

### D1 — A second file had to change: `tests/test_pii_redaction_integration.py`

**The plan and the story both said exactly one file would change. Two did.**

`tests/test_pii_redaction_integration.py::test_no_pre_epic_test_function_was_removed_or_renamed` censuses **every** `.py` file under `tests/` against `git merge-base main HEAD` — including `tests/test_untouched_app.py` itself. Deleting four guards and renaming a fifth made that guard fail:

```
AssertionError: {'tests/test_untouched_app.py': [
  'test_no_file_under_app_changed_since_prd_006_began',
  'test_no_new_dependency_in_either_requirements_file',
  'test_the_caddyfile_and_rxconfig_are_unchanged',
  'test_the_chat_modules_are_unchanged_since_prd_006_began',
  'test_the_pinned_suites_are_byte_unmodified']}
```

Neither the story nor the plan anticipated this. It was found by Phase 4's full-suite run, not by reasoning.

**Resolution**: the five names were added to that module's existing `_DELIBERATELY_SUPERSEDED_TESTS` allowlist, with a comment block recording why each was retired and that the fifth is a rename, not a deletion.

**Why this is the right call rather than a workaround.** AC 1 — `pytest -q` reports zero failures — is the entire purpose of the story, and it is unreachable without this. The "only one file changes" constraint is a Technical Note whose stated rationale is "No production code, no configuration, no CI edit"; a sibling test module is none of those three. `_DELIBERATELY_SUPERSEDED_TESTS` is the repo's own, already-documented mechanism for "a later PRD deliberately superseded these test functions", and this is precisely that case. The alternative — leaving it red — would defeat the story.

The change is additive: one comment block and one dict entry. No assertion, helper or existing entry in that module was modified.

### D2 — Line-ending normalization

The new module head was authored with LF while the repo's working tree is CRLF (`core.autocrlf=true`, no `.gitattributes`). The whole file was normalized to CRLF so the surviving tail stayed byte-identical on disk and the diff stayed minimal.

### D3 — Tamper-test target

Plan Task 6 said "delete one `test_` function from `tests/test_db.py`". The first attempt used a guessed name (`test_init_db_creates_tables`) that does not exist, so nothing was removed and the guard correctly stayed green. Repeated with the real name, `test_init_db_creates_table`.

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| `tests/test_untouched_app.py` | ✅ 9 passed (was 7 failed, 6 passed) |
| Full suite `pytest -q` | ✅ **1333 passed, 0 failed** |
| Census tamper test (AC 5) | ✅ red on deletion, green on restore |
| Three survivors byte-identical to `HEAD` | ✅ 4974 bytes, exact match |
| Shallow history → skip, not fail (AC 7) | ✅ 9 skipped, 0 failed |
| No `xfail` / `--deselect` / `continue-on-error` | ✅ no hits |
| `_BASE` not re-baselined | ✅ still `d3e6279` |
| `.github/workflows/ci.yml` untouched | ✅ |

### Tamper test transcript (AC 5)

With `test_init_db_creates_table` temporarily removed from `tests/test_db.py`:

```
AssertionError: tests/test_db.py lost test functions present at d3e6279: ['test_init_db_creates_table']
FAILED tests/test_untouched_app.py::test_no_test_was_removed_from_the_six_pinned_suites[tests/test_db.py]
1 failed, 5 passed
```

Restored with `git checkout -- tests/test_db.py`; `git status --porcelain tests/test_db.py` is empty and the module returns to 9 passed.

### Shallow-history transcript (AC 7)

A `--depth 1` clone cannot resolve `_BASE`:

```
$ git rev-parse --verify 'd3e6279^{commit}'
fatal: Needed a single revision
$ pytest tests/test_untouched_app.py -q -rs
SKIPPED [6] baseline d3e6279 not resolvable; provenance unverifiable here
SKIPPED [1] ... [1] ... [1] ...
9 skipped
```

This is the CI path: `.github/workflows/ci.yml` uses `actions/checkout@v4` at its default `fetch-depth: 1`, so every guard in this module skips there. The module's value is local and pre-merge; deepening the checkout would be the `ci.yml` edit the story forbids.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_untouched_app.py` | UPDATE | +101/−87 (262 → 276 lines) |
| `tests/test_pii_redaction_integration.py` | UPDATE | +25/−0 |

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_untouched_app.py` | `test_no_test_was_removed_from_the_six_pinned_suites` — parametrized over the six pinned suites; asserts every `test_` function present at `_BASE` is still present by name, less a documented superseded-names allowlist. Replaces `test_the_pinned_suites_are_byte_unmodified`. |

Guards removed (4): `test_no_file_under_app_changed_since_prd_006_began`, `test_no_new_dependency_in_either_requirements_file`, `test_the_caddyfile_and_rxconfig_are_unchanged`, `test_the_chat_modules_are_unchanged_since_prd_006_began`. Dead support removed with them: `_changed_since_base()`, `_APP_TREE`, `_REQUIREMENTS`, `_DEPLOYMENT`, `_CHAT_MODULES`.

Guards unchanged (3, byte-identical): `test_no_assertion_was_removed_from_the_two_extendable_suites`, `test_no_theme_token_was_retuned_or_removed`, `test_the_chat_humanizer_still_renders_what_it_did`.

### The census allowlist, and why it exists

`tests/test_chat_state.py` had four `test_` functions present at `_BASE` and absent today, so a literal census would have failed on arrival:

| Removed at `_BASE` | Replaced in-file by |
|---|---|
| `test_chat_state_submit_empty_or_whitespace_user_id_shows_error` | `test_chat_state_login_empty_token_shows_error` |
| `test_chat_state_submit_valid_user_id_clears_error_and_sets_user` | `test_chat_state_login_valid_token_sets_user_id_and_clears_error` |
| `test_chat_state_reset_user_id_clears_error` | folded into `test_chat_state_logout_clears_session_and_credential` |
| `test_reset_user_id_clears_the_transcript` | `test_logout_clears_the_transcript` |

All four were removed by `a38f38b` — **PRD-005 STORY-014**, "chat UI login replaces the free-text user_id prompt" — a deliberate, documented breaking change that reached this branch through `main`, not PRD-006's work. `tests/test_pii_redaction_integration.py:338-350` already carried the identical allowlist for the identical four names; this mirrors that mechanism rather than inventing a second one.

Every other pinned suite censuses clean, including the four that had been failing byte-equality: `test_db.py` 23 → 118 functions, `test_audit_router.py` 6 → 10, `test_stats_router.py` 5 → 9, none removed.

## Known Limitations

- `_TEST_DEF` (`^def (test_\w+)`) does not match `async def` or class-method tests, so deleting one of those from a pinned suite would pass unnoticed. Inherited unchanged from both pre-existing census guards; the pinned files currently contain no `async def test_`. Left alone to keep the three survivors byte-identical.
- `tests/conftest.py:143` still describes `test_admin_auth.py` as "pinned byte-for-byte" by this module. That is now imprecise here, but remains true via `tests/test_pii_redaction_integration.py:303-312`, which still byte-pins it. Not edited — out of this story's scope.
- Deleting the `app/` guard removes the only automated check that PRD-006 added nothing under `app/`. The claim is historical and settled (recorded above). Live containment for PRD-008's own work is asserted by `tests/test_session_ownership.py` and `tests/test_chat_sessions.py`.

## Acceptance Criteria

- [x] `pytest -q` reports **zero failures** (1333 passed); the seven are gone by deletion or reformulation — no `xfail`, `skip` or `--deselect`.
- [x] No assertion of the form "this path has not changed since `_BASE`" against the working tree remains; all four named guards removed.
- [x] The report records the evidence that PRD-006's claim was **true** and only its measurement was wrong (see above), plus a correction to the story's branch-tip claim.
- [x] The six suites are asserted by **census**: extending passes, deleting fails.
- [x] Verified by removing one `test_` function, observing the red, and restoring it — transcript above.
- [x] The three durable guards are **byte-unmodified** (verified: 4974 bytes, exact match against `HEAD`).
- [x] With git unavailable or the history shallow, the census guard and the three survivors **skip** rather than fail — verified on a `--depth 1` clone.
- [x] The module docstring explains the retirement in terms of the defect: a two-point diff from a fixed baseline to a moving tree answers "what changed since PRD-006 began", never "what did PRD-006 change".
- [x] All tasks completed
- [x] Follows existing patterns
