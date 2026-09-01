---
story: STORY-006
prd: PRD-006
slug: admin-state-tests
title: "tests/test_admin_state.py: gate, sign-out, failed read, four verdicts, no leak"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-006-admin-console
created: 2026-08-30
---

# Plan: `tests/test_admin_state.py` — the Phase 1 validation, completed

## Summary

Close PRD-006 Section 12's Phase 1 validation by finishing `tests/test_admin_state.py`. The file already exists at 1015 lines and 52 passing tests: STORY-003, STORY-004 and STORY-005 each wrote their own half as they landed, and the file's own docstring says so — *"STORY-006 extends this file further: the four verdicts against constructed `AuditLog`s land here once that story runs."* So this story is an **ENHANCEMENT to one existing test file**, not a new one, and the honest scope is the gap between the seven acceptance criteria and what is already asserted. That gap is three things: **AC 4** — the four verdicts (plus the Risk 3 fifth case) asserted against constructed `AuditLog`s, which no test in this file does today; **AC 6** — the no-leak claim asserted field-by-field on an `AuditRow` built from a seeded log, where the existing test asserts it only through `repr()` of the loaded list; and **AC 7** — a verdict filter and a free-text filter applied together with the *database call count* asserted unchanged across the filtering, which today is two separate tests that never meet. AC 1, AC 2, AC 3 and the read half of AC 5 are already satisfied verbatim and are re-verified rather than rewritten; AC 5's row half gets one added assertion line so the `/admin/stats`-with-no-session case states both halves in one place. No application file is touched: this story writes tests only, and every test named in PRD Section 11 must still pass **unmodified**.

## User Story

As an integrating developer
I want the admin state driven directly by unit tests
So that the gate, the failure arm and the verdict derivation are proven without a browser (PRD Section 12 Phase 1 validation).

## Story Reference

- Story file: `.agents/stories/PRD-006-admin-console/STORY-006-admin-state-tests.md`
- PRD: `.agents/PRDs/PRD-006-admin-console/PRD.md` — Section 11 (quality indicators), Section 12 Phase 1 validation, Risks 1, 2, 3

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `tests/test_admin_state.py` (UPDATE — the only file). No `app/` change, no `chat_ui/` change, no new module, no new dependency. |
| Story | STORY-006 |
| PRD | PRD-006 |
| Epic Branch | `epic/PRD-006-admin-console` (commit directly on this branch) |

**Dependency check**: `depends_on: [STORY-002, STORY-003, STORY-004, STORY-005]` — all four `status: done` on this branch at `0fe6c69`, `048a873`, `e8c331e`, `631bbff` respectively. `derive_verdict`/`to_audit_row`/`VERDICTS` exist in `chat_ui/chat_ui/admin_formatting.py`; `AdminState.authenticate`/`sign_out`/`load`/`visible_rows` all exist in `chat_ui/chat_ui/admin_state.py`. `python -m pytest tests/test_admin_state.py -q` → **52 passed**. Working tree clean on `epic/PRD-006-admin-console`. Cleared to proceed.

**Scope note, stated up front**: the story title reads *"New file `tests/test_admin_state.py`"* in its Technical Notes, and the file already exists — STORY-003 created it and STORY-004/005 extended it, each recording in the module docstring that STORY-006 would finish it. The deliverable is therefore the same set of assertions the story asks for, appended to that file rather than written into a second one. A second file of the same name is not possible, and a differently named one would split the state's tests across two modules for no gain. This is the only deviation from the story text, and it changes what is written, not what is asserted.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `.agents/skills/frontend-design` | Read in full (`.agents/skills/frontend-design/SKILL.md`). Scanned and found **not binding on this story**: it governs visual direction, typography, palette and copy, and this story renders nothing, emits no user-facing string and touches no component. Its rules land in STORY-011/013/014/019. Recorded so a later reader knows it was checked rather than skipped. | none |
| `reflex-docs` (**NOT INSTALLED**) | `chat_ui/AGENTS.md` mandates it for any Reflex API. This story drives `rx.State` event handlers and one `@rx.var` from tests. Substituted as described below. | Task 1, Task 4 |
| `reflex-process-management` (**NOT INSTALLED**) | Mandated for any compile/run/reload cycle. This story starts no server and compiles no page — validation is `pytest` only. | none |

`.agents/skills/` holds exactly one skill (`frontend-design`); the two Reflex skills ship in the `reflex-dev/agent-skills` plugin, which is not installed here — the same gap STORY-001 … STORY-005 each recorded. The substitution used by those stories applies unchanged and needs no new verification for this one: the tests below drive handlers through `type(state).event_handlers[name].fn(state, ...)` and read the computed var through plain attribute access, both of which are **already established in this very file** (`tests/test_admin_state.py:63-75`, `:674-676`, `:696-697`) against the pinned `reflex==0.9.6.post1`, and all 52 existing tests pass. Copying a working in-repo idiom is stronger evidence than prose about it.

---

## Patterns to Follow

### The import preamble — repo root, never `chat_ui/`

```python
# SOURCE: tests/test_admin_state.py:28-48 (identical in tests/test_chat_state.py, tests/test_contrast.py:11-14)
import asyncio
import os
import sys
import threading
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

# Repo root, not chat_ui/ — putting the inner package on sys.path[0] shadows
# the namespace package every other test module imports through.
sys.path.insert(0, str(Path(__file__).parent.parent))
```

Already present at the top of the file. Nothing in this story adds a new import block; new imports (`to_audit_row`, `VERDICT_*`) join the existing `from chat_ui.chat_ui...` group.

### Driving a handler without a Reflex runtime

```python
# SOURCE: tests/test_admin_state.py:59-75
def _state() -> AdminState:
    return AdminState(_reflex_internal_init=True)

def _authenticate(state: AdminState, token: str):
    """Drives the handler directly, as tests/test_chat_state.py:80-84 does."""
    state.token_input = token
    return type(state).event_handlers["authenticate"].fn(state)

async def _load(state: AdminState):
    return await type(state).event_handlers["load"].fn(state)
```

### Patching the reads where `admin_state` looks them up

```python
# SOURCE: tests/test_admin_state.py:363-406 (the _Reads harness)
def install(self):
    import chat_ui.chat_ui.admin_state as admin_state_mod
    returns = dict(_READ_RETURNS)
    returns["list_audit_logs"] = _logs()
    stubbed = tuple(
        (field, label, self._stub(field, fn.__name__, returns), kwargs)
        for field, label, fn, kwargs in _ORIGINAL_READS
    )
    self._monkeypatch.setattr(admin_state_mod, "_READS", stubbed)
    return self
```

`_READS` is the lookup site — `load()` iterates that tuple, so replacing it *is* patching where the state looks the functions up, exactly as the story's Technical Notes require. Patching `app.db.database.list_audit_logs` would not take, because `admin_state` bound the function objects at import.

### Constructing an `AuditLog` for a verdict assertion

```python
# SOURCE: tests/test_admin_formatting.py:40-64
def make_log(**fields) -> AuditLog:
    ...
    return AuditLog(**fields)

def test_each_verdict_derives_from_its_condition():
    assert derive_verdict(make_log(was_duplicate_blocked=True)) == VERDICT_HELD
    assert derive_verdict(make_log(suspicious_pattern="ignore_instructions")) == VERDICT_DENIED
    assert derive_verdict(make_log(success=False)) == VERDICT_FAULT
    assert derive_verdict(make_log()) == VERDICT_CLEARED
```

This is the *unit* of the derivation and it already exists. STORY-006's AC 4 is the same claim asserted **on the console's own path** — a constructed `AuditLog` carried through `to_audit_row` and through `load()` into `AdminState.rows` — because that is the path a regression would break while `test_admin_formatting.py` stayed green (e.g. `load()` switching to a different row constructor). The new tests reference the constants, not re-typed strings.

### Asserting a negative against the module namespace, not its source text

```python
# SOURCE: tests/test_admin_state.py:301-307
def test_admin_state_has_no_write_path_to_the_audit_log():
    import chat_ui.chat_ui.admin_state as admin_state_mod
    assert not hasattr(admin_state_mod, "insert_audit_log")
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_admin_state.py` | UPDATE | Add the STORY-006 section (AC 4, AC 6, AC 7); add one assertion to the existing unauthenticated-load test for AC 5; extend the `_Reads` harness with an optional row set; update the module docstring's forward reference. |

No other file changes. `git diff --stat` after this story must list exactly one path.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Let `_Reads` serve a caller-supplied row set

- **File**: `tests/test_admin_state.py`
- **Action**: UPDATE
- **Implement**: `_Reads.__init__` gains a keyword-only `logs=None`; `install()` uses `returns["list_audit_logs"] = _logs() if self.logs is None else list(self.logs)`. Default behaviour is byte-identical for the eleven existing call sites, which pass no `logs`.
- **Why**: AC 4 needs `load()` to return *five specific* `AuditLog`s, and the harness currently hardcodes `_logs()`. A second parallel harness would be the alternative, and would then need its own thread/fault/kwargs bookkeeping.
- **Mirror**: `tests/test_admin_state.py:363-406` — same `__init__`/`install`/`_stub` shape, same "built from the pristine `_ORIGINAL_READS`" comment.
- **Validate**: `python -m pytest tests/test_admin_state.py -q` → still **52 passed** (no test changed behaviour yet).

### Task 2: The four verdicts against constructed `AuditLog`s, plus the Risk 3 fifth case (AC 4)

- **File**: `tests/test_admin_state.py`
- **Action**: UPDATE
- **Implement**: a new section header `# STORY-006: the verdicts, the projection and the filters, from the state's side`, then:
  - `_VERDICT_LOGS`: five `AuditLog`s constructed in this order — (1) `was_duplicate_blocked=True`, (2) `suspicious_pattern="ignore_instructions"`, (3) `success=False, error_message="boom"`, (4) plain/default, (5) `success=False, model_used="gpt-4", error_message="redaction failed"`. Each gets a distinct `id` and a valid ISO `timestamp`, newest first, so `audit_id` identifies the row in a failure message.
  - `_EXPECTED_VERDICTS = [VERDICT_HELD, VERDICT_DENIED, VERDICT_FAULT, VERDICT_CLEARED, VERDICT_FAULT]` — imported constants, never re-typed literals (`tests/test_admin_state.py:1006-1014` forbids a second copy of the vocabulary in `admin_state`; the same discipline applies here).
  - `test_each_constructed_log_reaches_the_row_with_its_verdict`: parametrized over `zip(_VERDICT_LOGS, _EXPECTED_VERDICTS)`, asserting `to_audit_row(log, _NOW).verdict == expected` — the derivation as the console's own projection applies it.
  - `test_the_loaded_register_carries_the_four_verdicts_in_order`: authenticate, `_Reads(monkeypatch, logs=_VERDICT_LOGS).install()`, `await _load(state)`, then `[row.verdict for row in state.rows] == _EXPECTED_VERDICTS`. This is the end-to-end half — it fails if `load()` ever stops using `to_audit_row`.
  - `test_a_failed_row_that_recorded_a_model_is_still_fault`: the fifth log and the third log asserted **equal to each other**, and both equal to `VERDICT_FAULT`. PRD Risk 3 verbatim — the output-side `PiiRedactorError` arm (`app/services/query_pipeline.py:91-93`) writes `model_used` together with `success=False`, so a `model_used` branch would split one verdict into two and misclassify it.
- **Mirror**: `tests/test_admin_formatting.py:59-101` for the constructed-log style; `tests/test_admin_state.py:469-497` for the load-then-assert-rows style.
- **Validate**: `python -m pytest tests/test_admin_state.py -q -k verdict` → new tests pass, and `test_the_verdict_vocabulary_is_imported_not_redeclared` still passes.

### Task 3: The no-leak assertion, field by field (AC 6, Risk 2)

- **File**: `tests/test_admin_state.py`
- **Action**: UPDATE
- **Implement**: `test_a_row_built_from_a_seeded_log_carries_neither_preview` — construct one `AuditLog` with **every** displayed column populated *and* `prompt_preview="SENTINEL PROMPT TEXT"`, `response_preview="SENTINEL RESPONSE TEXT"`, then `row = to_audit_row(log, _NOW)` and assert:
  - `not hasattr(row, "prompt_preview")` and `not hasattr(row, "response_preview")`;
  - `"prompt_preview" not in type(row).model_fields` and likewise `response_preview` — the class-level check, not the instance attribute (pydantic 2.13 deprecates instance access to `model_fields`);
  - neither sentinel appears in any field **value**: iterate `row.model_dump().values()`, flatten one level for the `list[str]` fields, and assert the substring is absent from each `str(value)`. This is the assertion the existing `repr()` check (`:499-514`) approximates — `repr` would also pass if a preview were stored in a field whose repr were truncated.
- **Why a separate test rather than strengthening `:499`**: that test asserts the property across the *load* path; this one asserts it at the *projection*, which is where Risk 2's mitigation actually lives (`admin_formatting.to_audit_row`). Both paths should state it.
- **Mirror**: `tests/test_admin_state.py:499-514`, and `tests/test_admin_formatting.py`'s seeded-log construction.
- **Validate**: `python -m pytest tests/test_admin_state.py -q -k preview` → passes. Sanity-check the test can fail: temporarily add `prompt_preview` to `AuditRow`, confirm red, revert (do not commit the revert-needed edit).

### Task 4: A verdict filter and a text filter together, with the database untouched (AC 7)

- **File**: `tests/test_admin_state.py`
- **Action**: UPDATE
- **Implement**: `test_filtering_the_loaded_register_narrows_it_without_a_second_read` — authenticate, install `_Reads` (recording harness), `await _load(state)`, assert `len(reads.calls) == 10`; snapshot that count; then set `state.selected_verdicts = [VERDICT_FAULT]` and `state.search` to a user substring, read `state.visible_rows`, assert the returned `audit_id`s are exactly the expected pair, and assert `len(reads.calls)` is **still 10** — plus `reads.calls == calls_before` so an appended call cannot hide behind a length that happens to match. Use `_VERDICT_LOGS` extended with distinguishable `user_id`s so the AND-composition has something to narrow.
- **Why**: AC 7's two halves exist separately today — `test_the_two_filters_compose_as_and` (`:809-827`) asserts the rows against hand-built `AuditRow`s that never came from a read, and `test_evaluating_visible_rows_performs_no_database_read` (`:738-774`) asserts the negative against raising stubs. Neither states the AC's actual claim: rows that *did* come from a read, filtered, with no read repeated.
- **Mirror**: `tests/test_admin_state.py:809-827` for the filter assertions, `:610-624` for the `reads.calls` counting idiom.
- **Validate**: `python -m pytest tests/test_admin_state.py -q -k filtering` → passes.

### Task 5: State AC 5's row half where the read half is asserted

- **File**: `tests/test_admin_state.py`
- **Action**: UPDATE
- **Implement**: add `assert state.rows == []` to `test_an_unauthenticated_load_calls_none_of_the_ten` (`:626-638`), beside the existing `reads.calls == []`. AC 5 is one claim with two halves — the `/admin/stats`-with-no-session case — and today they sit in two tests (`:271-281` asserts the rows, `:626` asserts the reads). Extend the test's docstring to name AC 5 and Risk 1.
- **Validate**: `python -m pytest tests/test_admin_state.py -q -k unauthenticated` → both unauthenticated tests pass.

### Task 6: Update the module docstring's forward reference

- **File**: `tests/test_admin_state.py`
- **Action**: UPDATE
- **Implement**: the docstring's last paragraph currently reads *"STORY-006 extends this file further: the four verdicts against constructed `AuditLog`s land here once that story runs."* Replace it with the finished statement — what STORY-006 added (the verdicts on the console's own path, the field-level no-leak assertion, the filter-without-a-read pairing) and why each is invisible in a diff, in the voice the three paragraphs above it already use. Also update the STORY-005 section's trailing note at `:652-653` (*"STORY-006 extends this block…"*) so it no longer points forward to work that is done.
- **Validate**: `python -m pytest tests/test_admin_state.py -q` → all tests pass; docstring names no unfinished story.

### Task 7: Confirm nothing else moved

- **File**: none (verification only)
- **Action**: verify
- **Implement**: run the full suite; run PRD Section 11's six named test files explicitly; confirm `git diff --stat` lists **only** `tests/test_admin_state.py` and `git diff main --stat -- app/` is empty; confirm `requirements.txt` is unchanged (PRD Section 8 — no new dependencies).
- **Validate**: commands in the Validation block below.

---

## End-to-End Tests

No browser, no server — Phase 1's validation is explicitly *"unit tests drive the state directly"* (PRD Section 12). The end-to-end checks for this story are therefore suite-level:

- [ ] `python -m pytest tests/test_admin_state.py -q` → all tests pass, count up from 52 by the number added
- [ ] `python -m pytest -q` → full suite green
- [ ] `python -m pytest tests/test_admin_auth.py tests/test_audit_router.py tests/test_stats_router.py tests/test_db.py tests/test_route_reservations.py tests/test_chat_state.py -q` → pass, and `git diff --name-only` shows none of these six files modified
- [ ] `git diff main --stat -- app/` → empty (PRD Section 11 quality indicator)
- [ ] `git diff --stat` → exactly one file listed

---

## Validation

```bash
python -m pytest tests/test_admin_state.py -q
python -m pytest -q
python -m pytest tests/test_admin_auth.py tests/test_audit_router.py tests/test_stats_router.py tests/test_db.py tests/test_route_reservations.py tests/test_chat_state.py -q
git diff --stat
git diff main --stat -- app/
git diff --stat -- requirements.txt chat_ui/requirements.txt
```

---

## Risks + Mitigations

**1. Rewriting what already passes.** Four of the seven ACs are satisfied by tests written under STORY-003/004/005. Re-implementing them would churn a green file and risk weakening an assertion in the retelling.
*Mitigation*: the Acceptance Criteria block below maps every AC to the test that satisfies it, existing or new. Only three ACs get new tests; one gets a single added line; three are verified in place and left alone.

**2. `_Reads` is shared by eleven tests.** Task 1 edits a harness the whole STORY-004 block depends on.
*Mitigation*: the new parameter is keyword-only with a `None` default and the existing branch is unchanged, so every current call site takes the identical path. Task 1's validation is "still 52 passed" before any new test exists — a regression there is caught before it can be attributed to a new test.

**3. A no-leak test that cannot fail.** An assertion that iterates fields and finds no sentinel passes trivially if it iterates the wrong thing (e.g. an empty dict from a mistyped `model_dump`).
*Mitigation*: Task 3's validation includes deliberately adding a preview field to `AuditRow`, confirming red, and reverting — the test is proven to fail before it is trusted to pass. The seeded log also populates every displayed column, so the flattening loop demonstrably has values to walk.

**4. Duplicating `tests/test_admin_formatting.py`.** `derive_verdict`'s four arms and the Risk 3 case are already asserted there.
*Mitigation*: the new tests assert the derivation **on the console's path** — through `to_audit_row` and through `load()` into `AdminState.rows` — which is the claim AC 4 makes and which the formatting tests structurally cannot make. The overlap is one parametrized test and it guards a different regression: `load()` ceasing to use the projection.

---

## Acceptance Criteria

(Copied from story `STORY-006`, each mapped to the test that satisfies it)

- [ ] Correct token → `authenticated` True; wrong and empty tokens both leave it False and produce the **same** error string, asserted as equal to each other — `test_correct_token_authenticates_clears_the_error_and_triggers_the_load` (`:135`) and `test_the_three_refusals_produce_the_identical_message` (`:169`). **Already satisfied; verified in place.**
- [ ] `sign_out()` empties the rows, clears the summary figures, clears the token and sets `authenticated` False — `test_sign_out_clears_the_token_the_rows_and_the_figures` (`:235`) and `test_sign_out_clears_every_declared_var` (`:250`). **Already satisfied; verified in place.**
- [ ] A patched read that raises → error string set, `loading` False, previously loaded rows unchanged — `test_a_failed_read_names_it_and_leaves_the_record_untouched` (`:548`) and `test_every_read_position_faults_the_same_way` (`:574`). **Already satisfied; verified in place.**
- [ ] Four constructed `AuditLog`s → exactly **held**, **denied**, **fault**, **cleared** — **NEW**, Task 2.
- [ ] The Risk 3 fifth case: `success=False` **with** `model_used` → **fault** — **NEW**, Task 2.
- [ ] Unauthenticated `load()` → row list empty **and** no read function called — `test_an_unauthenticated_load_calls_none_of_the_ten` (`:626`, one assertion added by Task 5) with `test_load_on_an_unauthenticated_state_reads_nothing` (`:271`).
- [ ] An `AuditRow` from a seeded log has no preview attribute and neither preview string in any field value — **NEW**, Task 3.
- [ ] `visible_rows` under a verdict filter and a free-text filter returns the expected rows with the database not called again — **NEW**, Task 4.
- [ ] All tasks completed
- [ ] Full suite green; PRD Section 11's six named test files pass **unmodified**
- [ ] `git diff --stat` lists only `tests/test_admin_state.py`; nothing under `app/` changed; no new dependency
- [ ] Follows existing patterns (import preamble, handler-driving helpers, `_READS` patch site, imported verdict constants)
