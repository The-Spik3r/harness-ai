---
story: STORY-023
prd: PRD-008
slug: untouched-app-guard-rescope
title: "test_untouched_app.py: retire the provenance guards whose question is closed, and convert the pinned suites to a coverage census"
type: REFACTOR
complexity: MEDIUM
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-04
---

# Plan: test_untouched_app.py — retire the provenance guards, census the pinned suites

## Summary

`tests/test_untouched_app.py` asserts PRD-006's containment by diffing a pinned baseline (`_BASE = d3e6279`) against the **working tree**. That comparison answers "what changed since PRD-006 began", not "what did PRD-006 change", and the two questions diverged the moment `main` was merged into the epic branch. Seven guards fail today and take CI down with them. This plan deletes the four working-tree provenance guards outright (their question is closed and provably answered), replaces the byte-equality pin on the six suites with a **name census** that permits extension and forbids deletion, leaves the three durable guards byte-identical, and rewrites the module docstring to explain the defect rather than the convenience. Exactly one file changes.

## User Story

As a maintainer
I want `pytest -q` to be green on this branch
So that a red CI means something broke, instead of meaning nothing at all.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-023-untouched-app-guard-rescope.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR |
| Complexity | MEDIUM |
| Systems Affected | test suite only (`tests/test_untouched_app.py`) |
| Story | STORY-023 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |

---

## Skills In Use

`.agents/skills/` was listed in full. It contains exactly one skill:

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `frontend-design` | **Does not apply.** Its `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one" — palette, typography, layout. This story changes one Python test module and renders nothing. | none |

The story's `skills:` frontmatter is `[]`, which matches. No skill constrains any task below.

---

## Baseline Evidence (gathered during exploration — this is the material AC 3 requires)

All commands run at the repo root on `epic/PRD-008-chat-sessions`.

**The seven failures are exactly the seven the story names**, confirmed by running the module:

```
FAILED test_no_file_under_app_changed_since_prd_006_began
FAILED test_no_new_dependency_in_either_requirements_file
FAILED test_the_chat_modules_are_unchanged_since_prd_006_began
FAILED test_the_pinned_suites_are_byte_unmodified[tests/test_audit_router.py]
FAILED test_the_pinned_suites_are_byte_unmodified[tests/test_stats_router.py]
FAILED test_the_pinned_suites_are_byte_unmodified[tests/test_db.py]
FAILED test_the_pinned_suites_are_byte_unmodified[tests/test_chat_state.py]
7 failed, 6 passed
```

**The rest of the suite is already green** — `pytest -q` reports `7 failed, 1330 passed`, and all seven are in this module. Fixing this one file is sufficient for AC 1; nothing else is red.

**PRD-006's claim was true.** `577a285` (STORY-001, first commit) through `99afc9f` (STORY-020 record) is 40 commits. `git log --name-only 99afc9f --not 8ada67a d3e6279` over each pinned path returns **empty** for `app/`, for both requirements files, for `Caddyfile`/`rxconfig.py`, for the six pinned suites, and for the six `_CHAT_MODULES` — the only `chat_ui/chat_ui/components/` files it touched are the three the console added (`admin_shell.py`, `register.py`, `summary.py`).

**Correction to the story's Technical Notes.** The story states that diffing `_BASE` "against PRD-006's merge, **or against its branch tip**, still reports twelve files under `app/`". The branch-tip half is wrong: `0f77203`'s *first* parent is `99afc9f`, so the `main` merge sits **above** the tip, not below it. `git diff --name-only d3e6279 99afc9f -- app/` returns **zero files**. The twelve-file figure is real but belongs only to the merge commit (`git diff d3e6279 0f77203 -- app/` → 12). The `--not` formulation and the plain tip diff therefore agree, and the report can cite the simpler one.

This correction does **not** weaken the story's conclusion. The guards must still be retired, because the defect is the *working-tree* endpoint, not the choice of upper bound: pinned against immutable commits the assertion becomes a historical fact that can never fail again, and a test that can only pass is not a test.

**The census does not pass as specified — this is the one real finding.** `tests/test_chat_state.py` has four `test_` functions present at `_BASE` and absent today:

| Removed at `_BASE` | Removed by | Replaced in-file by |
|---|---|---|
| `test_chat_state_submit_empty_or_whitespace_user_id_shows_error` | `a38f38b` | `test_chat_state_login_empty_token_shows_error` |
| `test_chat_state_submit_valid_user_id_clears_error_and_sets_user` | `a38f38b` | `test_chat_state_login_valid_token_sets_user_id_and_clears_error` |
| `test_chat_state_reset_user_id_clears_error` | `a38f38b` | folded into `test_chat_state_logout_clears_session_and_credential` |
| `test_reset_user_id_clears_the_transcript` | `a38f38b` | `test_logout_clears_the_transcript` |

`a38f38b` is **PRD-005 STORY-014**, "chat UI login replaces the free-text user_id prompt" — a deliberate, documented breaking change that arrived on this branch via `main`, not PRD-006's work. Every other pinned suite censuses clean (`test_db.py` 23 → 118 functions, none gone; `test_audit_router.py` 6 → 10; `test_stats_router.py` 5 → 9; `test_admin_auth.py` and `test_route_reservations.py` unchanged at 6 and 2).

**The repo already has the answer to this.** `tests/test_pii_redaction_integration.py:338-350` defines `_DELIBERATELY_SUPERSEDED_TESTS`, a path → names allowlist subtracted from the census set, and its comment block **already documents these exact four `test_chat_state.py` names with their replacements**. Task 4 mirrors that mechanism and cross-references it rather than re-arguing it.

---

## Patterns to Follow

### Naming and docstrings — sentence-style names, docstrings that cite the AC and justify the instrument

```python
# SOURCE: tests/test_untouched_app.py:153-160
def test_no_assertion_was_removed_from_the_two_extendable_suites():
    """AC 1, the half byte-equality cannot cover.

    `test_copy.py` and `test_contrast.py` were extended by this PRD's own
    stories, so a diff against them is expected and says nothing. What must
    still hold is that extending them never *removed* a check: every test
    function present at the baseline is still present by name.
    """
```

### The census idiom to reuse — `_TEST_DEF` + `git show {base}:{path}`, missing file reads as empty

```python
# SOURCE: tests/test_untouched_app.py:161-177
    base_source = _git("show", f"{base}:{path}")
    assert base_source is not None, f"git show failed for {path}"
    current = _REPO_ROOT / path
    current_source = current.read_text(encoding="utf-8") if current.exists() else ""
    gone = sorted(
        set(_TEST_DEF.findall(base_source)) - set(_TEST_DEF.findall(current_source))
    )
```

### The superseded-names allowlist — the precedent to mirror

```python
# SOURCE: tests/test_pii_redaction_integration.py:338-350 and :373
_DELIBERATELY_SUPERSEDED_TESTS = {
    "tests/test_chat_state.py": {
        "test_chat_state_submit_empty_or_whitespace_user_id_shows_error",
        ...
    },
}
# ... inside the guard:
        gone -= _DELIBERATELY_SUPERSEDED_TESTS.get(path, set())
```

### Skip-not-fail when git is unavailable, with a message saying what still holds

```python
# SOURCE: tests/test_untouched_app.py:115-118
    base = _base()
    if base is None:
        pytest.skip(f"baseline {_BASE} not resolvable; provenance unverifiable here")
```

This concession is load-bearing in CI: `.github/workflows/ci.yml` uses `actions/checkout@v4` with default `fetch-depth: 1`, so `_BASE` is genuinely unresolvable there and the census skips. Preserve it exactly.

### Module constants — `_UPPER_SNAKE`, tuple, each preceded by the PRD section it encodes

```python
# SOURCE: tests/test_untouched_app.py:83-92
# PRD-006 Section 15, "Tests that must pass unmodified". ...
_UNMODIFIED_SUITES = (
    "tests/test_admin_auth.py",
    ...
)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_untouched_app.py` | UPDATE | The only file this story touches: delete four guards, convert the pinned-suite pin to a census, rewrite the docstring. |

No production code, no configuration, no CI edit — per the story's Technical Notes, needing a `ci.yml` change would itself be the signal that the wrong fix is being applied.

---

## Design Decisions

**D1 — Delete, do not reformulate, the four provenance guards.** Removing them takes `_changed_since_base()`, `_APP_TREE`, `_REQUIREMENTS`, `_DEPLOYMENT` and `_CHAT_MODULES` with them, since nothing else reads any of those. The claim survives as a finding in the report, not as an assertion that can only pass.

**D2 — Keep `_UNMODIFIED_SUITES` and `_EXTENDED_SUITES` separate; do not merge them.** The story's Technical Notes call the merge "an implementation call", but AC 6 requires `test_no_assertion_was_removed_from_the_two_extendable_suites` to be **byte-unmodified**, and that guard reads `_EXTENDED_SUITES` by name. Merging the lists would edit its body and break AC 6. AC 6 is binding where the note is advisory, so the lists stay separate and — as the note itself directs — **the reason goes in a comment**. The new guard still honours "extend or generalize rather than write a second helper" by *reusing* `_TEST_DEF`, `_base()`, `_git()` and the `git show` idiom without editing the survivor.

**D3 — Census the six by `@pytest.mark.parametrize`, matching the shape of the test it replaces.** `test_the_pinned_suites_are_byte_unmodified` is already parametrized over `_UNMODIFIED_SUITES`; keeping that shape means one red case names the offending file directly.

**D4 — Carry the four superseded `test_chat_state.py` names in an allowlist** mirroring `_DELIBERATELY_SUPERSEDED_TESTS`, with `a38f38b` cited and the replacement for each name recorded. The alternative — dropping `test_chat_state.py` from the census — would silently surrender the census over its other 11 baseline functions, which all still hold. (See Risks R1.)

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Start the libSQL dev server

- **File**: none
- **Action**: environment setup
- **Implement**: `docker start harness-libsql-dev`. `tests/conftest.py:106-126` has an autouse **session** fixture that calls `pytest.exit(..., returncode=1)` when the endpoint is unreachable, so the whole session aborts before any guard runs — even though none of these guards touch storage.
- **Validate**: `python -m pytest tests/test_untouched_app.py -q` runs and reports `7 failed, 6 passed` (the pre-change baseline).

### Task 2: Delete the four working-tree provenance guards and their now-dead support

- **File**: `tests/test_untouched_app.py`
- **Action**: UPDATE
- **Implement**: Remove the functions `test_no_file_under_app_changed_since_prd_006_began`, `test_no_new_dependency_in_either_requirements_file`, `test_the_caddyfile_and_rxconfig_are_unchanged` and `test_the_chat_modules_are_unchanged_since_prd_006_began`. Then remove what becomes unreachable: the `_changed_since_base()` helper and the constants `_APP_TREE`, `_REQUIREMENTS`, `_DEPLOYMENT`, `_CHAT_MODULES` (with their comment blocks). Keep `_git()`, `_base()`, `_BASE`, `_REPO_ROOT`, `_TEST_DEF` — all still used. Remove the `_DEPLOYMENT` guard even though it is green today: it carries the identical defect and would fire on the first legitimate `Caddyfile` edit.
- **Mirror**: n/a (deletion)
- **Validate**: `grep -n "_changed_since_base\|_APP_TREE\|_DEPLOYMENT\|_CHAT_MODULES" tests/test_untouched_app.py` returns nothing; `python -m pytest tests/test_untouched_app.py -q` reports 4 failed, 2 passed (only the pinned-suite params still red).

### Task 3: Replace the byte-equality pin with a name census

- **File**: `tests/test_untouched_app.py`
- **Action**: UPDATE
- **Implement**: Replace `test_the_pinned_suites_are_byte_unmodified` with `test_no_test_was_removed_from_the_six_pinned_suites`, keeping `@pytest.mark.parametrize("path", _UNMODIFIED_SUITES)`. Body: resolve `_base()`, `pytest.skip` with the existing message when it is `None`, `_git("show", f"{base}:{path}")`, assert non-`None`, read the current file (`""` when absent), and assert `sorted(set(base_names) - set(current_names) - allowlist) == []` with a message naming the file and the missing functions. Reuse `_TEST_DEF` — do not define a second regex. Docstring states the reformulation: extending a suite passes, deleting a case fails.
- **Mirror**: `tests/test_untouched_app.py:161-177` for the census body; `tests/test_pii_redaction_integration.py:353-375` for the same shape at file scope.
- **Validate**: `python -m pytest tests/test_untouched_app.py -q` — `test_chat_state.py` is the only remaining failure (the allowlist lands in Task 4).

### Task 4: Add the superseded-names allowlist for `test_chat_state.py`

- **File**: `tests/test_untouched_app.py`
- **Action**: UPDATE
- **Implement**: Add `_DELIBERATELY_SUPERSEDED_TESTS = {"tests/test_chat_state.py": {…four names…}}` above the new guard, subtracted from `gone` as in the precedent. The preceding comment must record: that `a38f38b` (**PRD-005 STORY-014**) replaced the free-text `user_id` prompt with a token login; that it reached this branch through `main` and is not PRD-006's work; the replacement for each of the four names (table in *Baseline Evidence* above); and a pointer to `tests/test_pii_redaction_integration.py:338-350`, which already carries the identical allowlist for the identical reason. Also add the D2 comment explaining why `_UNMODIFIED_SUITES` and `_EXTENDED_SUITES` stay separate.
- **Mirror**: `tests/test_pii_redaction_integration.py:338-350`
- **Validate**: `python -m pytest tests/test_untouched_app.py -q` → **0 failed**.

### Task 5: Rewrite the module docstring around the defect

- **File**: `tests/test_untouched_app.py`
- **Action**: UPDATE
- **Implement**: Keep the opening statement of what STORY-020 proved and the closing paragraph on skip-not-fail (both still true). Replace the "**Why the baseline is a pinned SHA**" section with "**Why the provenance guards were retired**": a two-point diff from a fixed baseline to a *moving working tree* answers "what changed since PRD-006 began", never "what did PRD-006 change", and the two stopped being the same question at `0f77203` (`Merge branch 'main' into epic/PRD-006-admin-console`), which pulled PRD-005's `app/` work into the range — before PRD-007 existed. State that the claim itself was verified true (40 commits `577a285`→`99afc9f`, zero files under any pinned path) and is preserved in STORY-023's report; that the correct assertion would compare two immutable commits and could never fail, which is not a test; and that `_BASE` is deliberately **not** re-baselined, since that would go green today and re-break at the next PRD. Note the retained `3f553f2` attribution only if it still serves the surviving guards.
- **Mirror**: the survivors' own reasoning — `test_no_theme_token_was_retuned_or_removed`'s "A line-level diff is the wrong instrument… The claim that actually matters is value-level, so that is what is asserted."
- **Validate**: `python -m pytest tests/test_untouched_app.py -q` → 0 failed; docstring names the defect, not convenience.

### Task 6: Prove the census has teeth (AC 5)

- **File**: `tests/test_db.py` (temporary, reverted)
- **Action**: verification only — no committed change
- **Implement**: Delete one `test_` function from `tests/test_db.py`, run the module, observe `test_no_test_was_removed_from_the_six_pinned_suites[tests/test_db.py]` fail and name that function, then restore with `git checkout -- tests/test_db.py`. Record the observed failure text for the report.
- **Validate**: `git status --porcelain tests/test_db.py` is empty afterwards; `python -m pytest tests/test_untouched_app.py -q` → 0 failed.

### Task 7: Confirm the three durable guards are byte-unmodified (AC 6)

- **File**: `tests/test_untouched_app.py`
- **Action**: verification only
- **Implement**: `git diff -U0 tests/test_untouched_app.py` and confirm no hunk falls inside `test_no_assertion_was_removed_from_the_two_extendable_suites`, `test_no_theme_token_was_retuned_or_removed` or `test_the_chat_humanizer_still_renders_what_it_did`. If a hunk touches any of the three, the change is out of scope — revert that hunk.
- **Validate**: the three function bodies are identical to `git show HEAD:tests/test_untouched_app.py`.

### Task 8: Full-suite green and commit

- **File**: `tests/test_untouched_app.py`
- **Action**: UPDATE (commit)
- **Implement**: Run the whole suite, confirm zero failures, and commit on `epic/PRD-008-chat-sessions` (no per-story branch). Verify no `xfail`, `skip` (beyond the inherited git-unavailable concession), `--deselect`, `ci.yml` edit or `_BASE` re-baseline was introduced.
- **Validate**: `python -m pytest -q` → `0 failed`; `git diff --stat HEAD` lists **only** `tests/test_untouched_app.py`.

---

## End-to-End Tests

- [ ] `docker start harness-libsql-dev`, then `python -m pytest tests/test_untouched_app.py -q` → 0 failed
- [ ] `python -m pytest -q` (full suite) → 0 failed, ~1337 passed
- [ ] `grep -nE "xfail|--deselect" tests/test_untouched_app.py setup.cfg pytest.ini pyproject.toml` → no new hits
- [ ] `git diff --stat HEAD` → exactly one file changed
- [ ] `grep -n '_BASE = ' tests/test_untouched_app.py` → still `"d3e6279"`
- [ ] Simulated shallow clone: `python -m pytest tests/test_untouched_app.py -q` in a tree where `_BASE` is unresolvable → cases **skip**, none fail
- [ ] Task 6's tamper test observed red, then restored green

## Validation

```bash
docker start harness-libsql-dev
python -m pytest tests/test_untouched_app.py -q
python -m pytest -q
git diff --stat HEAD
```

---

## Risks + Mitigations

| # | Risk | Mitigation |
|---|------|------------|
| R1 | The allowlist (D4) is the same "exception that swallows the rule" move the story warns against. | It is bounded to four names in one file, each tied to a named commit and a named replacement, and mirrors an existing in-repo precedent that documents these exact four. The census keeps full force over the other five suites and over `test_chat_state.py`'s remaining 11 baseline functions. The rejected alternative — dropping `test_chat_state.py` from the list — would surrender all 11. |
| R2 | `_TEST_DEF` (`^def (test_\w+)`) misses `async def` and class-method tests, so a deletion of one would pass unnoticed. | Inherited limitation, identical in both existing census guards; the suite currently uses no `async def test_` in the pinned files. Out of scope to change — noting it keeps AC 6's byte-equality intact. |
| R3 | CI's `actions/checkout@v4` is shallow, so every census case skips there and CI proves less than a local run. | Pre-existing and deliberate (module docstring). The guard's value is local and pre-merge. Deepening the checkout is a `ci.yml` edit the story explicitly forbids. |
| R4 | `tests/conftest.py:143` says `test_admin_auth.py` is "pinned byte-for-byte" by this module — stale once Task 3 lands. | The claim stays true via `tests/test_pii_redaction_integration.py:303-312`, which still byte-pins it, so the comment is imprecise rather than wrong. The story restricts this change to one file; flag it in the report and leave `conftest.py` alone. |
| R5 | Deleting the `app/` guard removes the only automated check that PRD-006 added nothing under `app/`. | The claim is historical and settled — its evidence is recorded in the report. Live containment for PRD-008's own work is asserted by `tests/test_session_ownership.py` and `tests/test_chat_sessions.py`, not by this module. |

---

## Acceptance Criteria

(Copied from story `STORY-023`)

- [ ] Given `pytest -q` on this branch, when it runs to completion, then it reports **zero failures** — and the seven that fail today are gone by deletion or by reformulation, never by `xfail`, `skip` or a `--deselect` in configuration.
- [ ] Given `tests/test_untouched_app.py`, when it is read, then it no longer contains any assertion of the form "this path has not changed since `_BASE`" evaluated against the **working tree** — the four named guards are removed.
- [ ] Given the removal, when the report is written, then it records the evidence that PRD-006's claim was **true** and only its measurement was wrong: the 40 commits from `577a285` to `99afc9f`, excluding what arrived via the `main` merge `0f77203`, touched zero files under `app/`, zero pinned suites, zero requirements and zero chat modules.
- [ ] Given `test_the_pinned_suites_are_byte_unmodified`, when it is replaced, then the six suites are asserted by **census**: every `test_` function present in the file at `_BASE` is still present by name today. Extending a suite passes; deleting a case fails.
- [ ] Given a hypothetical deletion of one `test_` function from any of the six pinned suites, when the suite runs, then the new census guard fails — verified during implementation by removing one temporarily, observing the red, and restoring it.
- [ ] Given the three durable guards, when the story is complete, then they are **byte-unmodified**.
- [ ] Given the census guard and the three survivors, when the suite runs with `git` unavailable or the history shallow, then it skips rather than fails.
- [ ] Given the module docstring, when it is read afterwards, then it explains why the provenance guards were retired in terms of the defect rather than of convenience.
- [ ] All tasks completed
- [ ] Full suite green (`pytest -q` → 0 failed)
- [ ] Exactly one file changed
- [ ] Follows existing patterns
