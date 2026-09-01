---
story: STORY-008
prd: PRD-006
slug: admin-copy-module
title: "admin_copy.py: every admin-facing string in one module"
type: NEW_CAPABILITY
complexity: LOW
epic_branch: epic/PRD-006-admin-console
created: 2026-08-30
---

# Plan: `admin_copy.py` — the console's whole vocabulary, before a component exists

## Summary

Create `chat_ui/chat_ui/admin_copy.py` as the single source of every user-facing string the admin console will render, modelled on `chat_ui/chat_ui/copy.py` (PRD-004 STORY-007): flat module constants, grouped by surface, with templates as `str.format` constants rather than concatenation at the call site. This story is written **before** any admin component, which is the whole point — eight downstream stories (009, 011 … 017) are blocked on it, so the register, the gate, the filters, the summary and the fault panel each start with their words already chosen and named, and none of them ever needs a literal. Two strings already exist in `admin_state.py` (`GATE_REFUSED_MESSAGE`, `LOAD_FAILED_MESSAGE`) plus the ten fault labels inside `_READS`; that module's own comments say three times over that STORY-008 moves them here — so the second half of this story is that move, done as a **re-export** so `tests/test_admin_state.py:65`'s existing import path keeps working and the ten label *values* stay byte-identical (three tests assert on them by literal). The third piece is the copy test: `tests/test_copy.py` gains an append-only block asserting every new constant is non-empty and that the templates carry their placeholders. No component, no Reflex API, no colour, no `app/` change.

## User Story

As an integrating developer
I want every admin-facing string to resolve from one module
So that no literal text lives in a component and the wording of a figure's label can be asserted in a test.

## Story Reference

- Story file: `.agents/stories/PRD-006-admin-console/STORY-008-admin-copy-module.md`
- PRD: `.agents/PRDs/PRD-006-admin-console/PRD.md` — Section 4 (design & copy), Section 6 (files), Section 6.1 (copy, layout, the tally sheet), Section 9 (no token oracle), Section 11, Section 12 Phase 2

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | LOW |
| Systems Affected | `chat_ui/chat_ui/admin_copy.py` (CREATE), `chat_ui/chat_ui/admin_state.py` (UPDATE — imports the three string groups it currently declares), `tests/test_copy.py` (UPDATE, append-only). No `app/` change, no component change, no new dependency, no Reflex API. |
| Story | STORY-008 |
| PRD | PRD-006 |
| Epic Branch | `epic/PRD-006-admin-console` (commit directly on this branch) |

**Dependency check**: `depends_on: []` — nothing blocks this story. `blocks: [STORY-009, STORY-011, STORY-012, STORY-013, STORY-014, STORY-015, STORY-016, STORY-017]`, all eight still `todo`, so no file yet imports these names and every name chosen here is still free. Working tree clean on `epic/PRD-006-admin-console` at `3f26449`. Baseline captured before planning: `python -m pytest tests/test_copy.py tests/test_admin_state.py -q` → **78 passed in 0.34s**. Cleared to proceed.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `.agents/skills/frontend-design` | Read in full (`.agents/skills/frontend-design/SKILL.md`); it is the only skill listed on the story and the only one that binds here, because this story is *entirely* the "More on writing in design" section. Four rules govern every constant below, and each is quoted at its point of use in the module docstring: **(1)** *"Errors don't apologize, and they are never vague about what happened."* — the fault template names the read and states that nothing on screen moved; there is no "Sorry" and no "Something went wrong". **(2)** *"An empty screen is an invitation to act."* — each of the three empty states ends in the action available from it. **(3)** *"An action keeps the same name through the whole flow, so the button that says 'Publish' produces a toast that says 'Published.'"* — **Refresh** → **Refreshed {time}**, and the retry inside the fault panel is the same `REFRESH_LABEL`, not a second word. **(4)** *"A control should say exactly what happens when it's used: 'Save changes,' not 'Submit.'"* — the gate submits with `Open the console`, not `Submit`; the filter clear is `Clear filters`. Also binding negatively: *"Let each element do exactly one job. A label labels, an example demonstrates"* — the scope line states the window, the figure label names the count, and neither does the other's job. | Tasks 1–4 |
| `reflex-docs` (**NOT INSTALLED**) | `chat_ui/AGENTS.md` mandates it for any Reflex API. This story uses **none**: `admin_copy.py` is plain module constants with no `rx.` import, exactly as `copy.py` is, and the test is plain `pytest`. `admin_state.py`'s edit is an import statement and three name deletions — no Reflex surface is touched. Nothing to substitute. | none |
| `reflex-process-management` (**NOT INSTALLED**) | Mandated for any compile/run/reload cycle. This story starts no server and compiles no page; validation is `pytest` plus `git diff`. | none |

`.agents/skills/` holds exactly one skill (`frontend-design`, pinned in `skills-lock.json`); the two Reflex skills ship in the `reflex-dev/agent-skills` plugin, which is not installed here — the same gap STORY-001 … STORY-007 each recorded. As with STORY-007, no substitution is needed, because no Reflex surface is touched.

---

## Patterns to Follow

### Flat module constants, grouped by surface, with the reason in the comment

```python
# SOURCE: chat_ui/chat_ui/copy.py:14-21
# --- Session gate --------------------------------------------------------
USER_ID_PROMPT_TITLE = "Who is sending?"
USER_ID_PROMPT_BODY = (
    "Every prompt is recorded against a user ID. Enter the one you go by."
)
USER_ID_PLACEHOLDER = "e.g. a.torres"
USER_ID_SUBMIT_LABEL = "Start session"
USER_ID_VALIDATION_ERROR = "Enter a user ID to start the session."
```

No dict, no class, no enum, no catalogue — PRD Section 4 out of scope: *"A full i18n framework — copy centralization only, as in PRD-004."* Constants import cleanly, are greppable by name, and fail at import time when one is deleted out from under a component; a dict lookup fails at render time instead.

### Templates as constants, formatted at the call site — never concatenated

```python
# SOURCE: chat_ui/chat_ui/copy.py:66-68
PII_BADGE_TEMPLATE = "{count} PII types masked in this exchange: {entities}"
PII_BADGE_SINGLE_TEMPLATE = "1 PII type masked in this exchange: {entities}"
```

```python
# SOURCE: chat_ui/chat_ui/copy.py:81-83
DUPLICATE_RELATIVE_TIME_TEMPLATE = "Already sent {relative} ({absolute})"
DUPLICATE_WINDOW_RELEASE_TEMPLATE = "24h window releases at {release}"
```

The `_TEMPLATE` suffix is the existing convention and marks the constants that must be `.format(...)`-ed. Story AC 3 names two of them explicitly — `"100 most recent of {total}"` and `"Refreshed {time}"`.

### The comment carries the *reason*, not the string

```python
# SOURCE: chat_ui/chat_ui/copy.py:63-65
# Risk 5: the badge covers the whole exchange, because run_query(...) returns
# the union of input and output entities. The copy says so rather than letting
# the reader assume it means their prompt alone.
```

Every constant in this repo whose wording has a *requirement* behind it carries that requirement in a comment above it. `FIGURE_COMPLETION_LABEL` is this story's version of that and gets the longest comment in the file.

### Values are not copy — the split already exists on this surface

```python
# SOURCE: chat_ui/chat_ui/admin_formatting.py:34-40
# ... These are values, not copy: they are the `rx.match` keys and the filter
# values downstream, so they are constants rather than inline literals ...
VERDICT_CLEARED = "cleared"
VERDICT_HELD = "held"
```

`admin_formatting.VERDICT_*` are **keys**; `admin_copy.VERDICT_*_LABEL` are **words on screen**. They happen to hold the same four strings today and must stay separate names anyway: the day the register renders `HELD` as "Held (duplicate)" the key must not move with it. Same rule for `admin_formatting.VALUE_ABSENT` / `SHARE_UNDEFINED` — those are the *absence marks the formatter writes into a field*, they stay where they are, and this story does not duplicate them.

### Tests — one flat non-empty assertion, plus a named test per string with a requirement

```python
# SOURCE: tests/test_copy.py:31-46
def test_copy_constants_exist_and_not_empty():
    """Verify all critical copy strings are non-empty and accessible."""
    assert USER_ID_PROMPT_TITLE
    assert COMPOSER_PLACEHOLDER == "Message..."
```

```python
# SOURCE: tests/test_copy.py:49-55
def test_risk_5_pii_exchange_phrasing():
    """AC3 / Risk 5: PII badge copy explicitly states masking applies to the exchange, not prompt alone."""
    assert "masked in this exchange" in PII_BADGE_TEMPLATE
```

Story AC 6 asks for the first pattern ("each constant asserted non-empty, matching the existing test's pattern"). The second pattern — assert on *substance*, never on the whole sentence — is what STORY-016 builds on top of this file.

### The test import preamble — repo root, never `chat_ui/`

```python
# SOURCE: tests/test_copy.py:1-6
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from chat_ui.chat_ui.copy import (...)
```

Already at the top of `tests/test_copy.py`; the appended block reuses it and adds one more `from chat_ui.chat_ui.admin_copy import ...`.

---

## The strings — what goes in, and why each is worded this way

This is the specification Task 1 implements. Grouped as the file will be.

**1. Masthead and views** (STORY-009). `CONSOLE_TITLE = "HARNESS"` — the same wordmark `copy.SHELL_HEADER_TITLE` carries, deliberately re-declared rather than imported from `copy.py`: PRD Section 4 requires that no admin module import a chat module, and a shared constant would be the first thread of exactly that coupling. `CONSOLE_VIEW_REGISTER` / `CONSOLE_VIEW_SUMMARY` are the masthead's second word (`HARNESS · REGISTER`), joined by `MASTHEAD_SEPARATOR = " · "` — the same separator `copy.FOOTER_SEPARATOR` uses, again re-declared. `VIEW_REGISTER_LABEL = "Register"` / `VIEW_SUMMARY_LABEL = "Summary"` are the two switch labels, `SIGN_OUT_LABEL = "Sign out"`.

**2. Gate** (STORY-009). `GATE_TITLE`, `GATE_BODY`, `GATE_PLACEHOLDER`, `GATE_SUBMIT_LABEL`, and exactly one `GATE_REFUSED_MESSAGE`. Story AC 5 and PRD Section 9 both fix the refusal: it states access was refused and does not say why, one message for empty, malformed and wrong tokens alike. The value moves verbatim from `admin_state.py:60` — `"Access refused. That token was not accepted."` — because three tests compare `gate_error` against the imported constant and a reworded value would be a silent change to what a refused admin reads. There is **one** refusal constant in the file and STORY-016 asserts that a second one cannot be added.

**3. Sign-out has no notice string.** Story AC 4, second half: *"**Sign out** returns the gate rather than a 'session ended' notice."* This is a deliberate *absence* — there is no `SIGN_OUT_CONFIRMATION` and no `SESSION_ENDED_MESSAGE` in the file, and the docstring says so, so the next reader does not add one to be helpful.

**4. Column heads** (STORY-011), one per column PRD Section 4 names: `COLUMN_TIME`, `COLUMN_USER`, `COLUMN_VERDICT`, `COLUMN_MODEL`, `COLUMN_TOKENS`, `COLUMN_PII`, `COLUMN_DEVICE`, `COLUMN_ID`. Short, because `theme.TEXT_MICRO` is a 10px signpost over a dense column and a two-word head would wrap into the row height. `COLUMN_ID = "ID"` heads a column of `#3180` values; `PII_INDICATOR_LABEL = "PII"` is the in-row mark itself, distinct from the head.

**5. Verdict labels** (STORY-011), four: `VERDICT_CLEARED_LABEL`, `VERDICT_HELD_LABEL`, `VERDICT_DENIED_LABEL`, `VERDICT_FAULT_LABEL` — lowercase words. The wireframe's `DENIED` / `cleared` casing is a *treatment* (PRD Section 6.1 gives the exceptions the display face and the emphasis), so the case belongs in `register.py`'s `text_transform`, not baked into the copy — otherwise the same word arrives in two cases from two constants and the filter chip and the row cell disagree.

**6. Scope lines** (STORY-011, STORY-013, STORY-015). `REGISTER_SCOPE_TEMPLATE = "{shown} most recent of {total}"` — AC 3's named template, with `{shown}` rather than a literal `100` so the register formats it from `admin_state.REGISTER_ROW_LIMIT` and the number is typed once in the codebase. `REGISTER_FILTERED_TEMPLATE = "{shown} of {loaded} shown"` is the *filtered* count STORY-013 AC 4 requires to be distinct from the scope line. `SUMMARY_SCOPE_ALL_TIME` states the summary's window in the words Risk 4 needs — all time, the whole table — and `SUMMARY_SCOPE_NOTE` is the one prose line that names the difference from the register's window, because Risk 4 is precisely that the two numbers read as a contradiction when nothing says otherwise.

**7. Refresh** (STORY-017). `REFRESH_LABEL = "Refresh"`, `REFRESHED_TEMPLATE = "Refreshed {time}"`, `REFRESH_IN_FLIGHT_LABEL = "Refreshing"`. AC 4's first half, and the skill's Publish/Published rule: one verb, three tenses, no fourth word anywhere in the flow. The fault panel's retry control reuses `REFRESH_LABEL` rather than declaring `RETRY_LABEL` — a second name for the same button is exactly what the rule forbids.

**8. Fault panel** (STORY-017). `FAULT_TITLE` plus `FAULT_MESSAGE_TEMPLATE`, whose value moves verbatim from `admin_state.LOAD_FAILED_MESSAGE`, and the ten `READ_LABEL_*` constants `_READS` currently spells inline. The template already satisfies the skill: it names the read that failed, states that nothing on screen changed, and gives the action — no apology, no vagueness. The ten labels keep their exact current values (`"the audit rows"`, `"the recorded total"`, `"the blocked duplicates"`, `"the blocked patterns"`, `"the user count"`, `"the completed count"`, `"the PII detection count"`, `"the model ranking"`, `"the user ranking"`, `"the PII entity ranking"`) because `tests/test_admin_state.py` asserts three of them as literals.

**9. The three empty states** (STORY-014, STORY-015). Story AC 1 asks for three; PRD Section 4's three register states are *no rows recorded*, *none matching the filter*, and *rows shown* — and the third of those is a table, not a state that needs copy. The three that need copy are therefore: the empty register (`EMPTY_REGISTER_TITLE` / `_BODY`), the no-matches state (`EMPTY_MATCHES_TITLE` plus `EMPTY_MATCHES_TEMPLATE` naming the filter, plus `CLEAR_FILTERS_LABEL`), and the empty summary (`EMPTY_SUMMARY_TITLE` / `_BODY`) — which STORY-015 AC 8 needs when `total_queries` is 0 and every share is a placeholder. Each ends in an available action, per the skill. The no-matches state's filter description is built from `FILTER_DESCRIPTION_VERDICT_TEMPLATE`, `FILTER_DESCRIPTION_SEARCH_TEMPLATE` and `FILTER_DESCRIPTION_JOIN` rather than concatenated in the component (AC 3).

**10. Filter and sort controls** (STORY-013). `FILTER_VERDICT_LABEL`, `FILTER_SEARCH_LABEL`, `FILTER_SEARCH_PLACEHOLDER`, `SORT_LABEL`, three `SORT_*_LABEL`s matching `admin_state.SORT_KEYS`, and `SORT_ASCENDING_MARK` / `SORT_DESCENDING_MARK` for the active-direction indicator.

**11. Row disclosure** (STORY-012). One label per field PRD Section 10 puts on disclosure: `DETAIL_TOGGLE_OPEN_LABEL` / `DETAIL_TOGGLE_CLOSE_LABEL`, `DETAIL_TIMESTAMP_LABEL`, `DETAIL_PROMPT_HASH_LABEL`, `DETAIL_ERROR_LABEL`, `DETAIL_PATTERN_LABEL`, `DETAIL_DEVICE_LABEL`, `DETAIL_PII_ENTITIES_LABEL`, `DETAIL_PII_INPUT_LABEL`, `DETAIL_PII_OUTPUT_LABEL`. `DETAIL_PATTERN_LABEL` is worded as `copy.INJECTION_PATTERN_LABEL` already words it — *"Matched pattern"* — because the same fact under two names on two surfaces is the vocabulary drift the skill's "cohesion and consistency" rule is about; the string is re-declared, not imported.

**12. Summary figures** (STORY-015), nine labels plus their block headings and the ranked-list cut. The one with a correctness requirement is:

```python
FIGURE_COMPLETION_LABEL = "Completed without error (blocked queries included)"
```

PRD Section 4: *"`success_rate` labeled for what it counts — rows the pipeline completed without raising, blocked rows included — not as an answer rate."* The word *success* does not appear, because `count_successful_queries()` counts `success = 1` and the pipeline writes `success=True` for both a held duplicate and a denied injection — so a label reading "success rate" states something false about the number beside it. `FIGURE_COMPLETION_NOTE` carries the full sentence. STORY-016 pins both against the forbidden phrasings; this story writes them and asserts non-empty.

`RANKED_CUT_TEMPLATE = "top {n}"` states the cut STORY-015 AC 6 requires; `n` comes from `top_models(limit=5)`'s default rather than a literal 5 in the copy. `SHARE_TEMPLATE = "{share} of all queries"` renders `format_share`'s output as a phrase — the percentage itself is computed in `admin_formatting.format_share`, and this constant only supplies the words around it.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/admin_copy.py` | CREATE | Every admin-facing string, as flat constants grouped by surface. |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | Import `GATE_REFUSED_MESSAGE`, `LOAD_FAILED_MESSAGE` and the ten read labels from `admin_copy` instead of declaring them; keeps both names importable from `admin_state` for the existing test. |
| `tests/test_copy.py` | UPDATE (append-only) | Assert every new constant non-empty and every template's placeholders present, per AC 6. |

Nothing else. No component exists yet to de-literalize — AC 2's grep is satisfied vacuously today and becomes a real check as STORY-009 … STORY-017 land against this module.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create `chat_ui/chat_ui/admin_copy.py`

- **File**: `chat_ui/chat_ui/admin_copy.py`
- **Action**: CREATE
- **Implement**: The twelve groups specified in "The strings" above, in that order, each under a `# --- Group ---` banner comment in `copy.py`'s style. Open with a module docstring that states: the module is the console's whole vocabulary and the counterpart to `copy.py`; it imports nothing from `copy.py` or any chat module, because PRD Section 4 forbids the coupling and a shared constant is the first thread of it; the four `frontend-design` rules that govern the wording, quoted; the value/copy split against `admin_formatting.VERDICT_*`; and the two deliberate absences — no sign-out notice (AC 4) and no second refusal message (AC 5, PRD Section 9). Carry a per-constant reason comment on `GATE_REFUSED_MESSAGE`, `FIGURE_COMPLETION_LABEL`, `REFRESH_LABEL`/`REFRESHED_TEMPLATE`, and the `READ_LABEL_*` block. Every string with a value in it is a `_TEMPLATE` constant.
- **Mirror**: `chat_ui/chat_ui/copy.py:1-9` (docstring stating the module's contract and voice), `:14-21` (grouped constants), `:63-68` (a reason comment above the template it explains), `:81-85` (template naming).
- **Do not**: import `reflex`, import from `chat_ui.chat_ui.copy`, define a dict/enum/class, or duplicate `admin_formatting.VALUE_ABSENT` / `SHARE_UNDEFINED`.
- **Validate**: `python -c "from chat_ui.chat_ui import admin_copy"` and `python -c "import ast,sys; m=ast.parse(open('chat_ui/chat_ui/admin_copy.py').read()); assert not [n for n in m.body if isinstance(n,(ast.Import,ast.ImportFrom))], 'admin_copy must import nothing'"`

### Task 2: Move the gate refusal out of `admin_state.py`

- **File**: `chat_ui/chat_ui/admin_state.py`
- **Action**: UPDATE
- **Implement**: Delete the `GATE_REFUSED_MESSAGE = "..."` assignment (and the "STORY-008 moves this string" line of its comment, now done), and add `from .admin_copy import GATE_REFUSED_MESSAGE` to the existing relative-import block beside `from .admin_formatting import ...`. Keep the surrounding comment explaining the no-oracle rule where it is — it documents `_refuse()`'s behaviour, not the string's location. The name must stay importable as `chat_ui.chat_ui.admin_state.GATE_REFUSED_MESSAGE`, which a plain re-export gives for free.
- **Mirror**: the existing `from .admin_formatting import VERDICTS, format_refreshed_at, to_audit_row` line — same relative form, same block.
- **Validate**: `python -m pytest tests/test_admin_state.py -q` → the same **61** tests pass (baseline count for this file), including `test_admin_state.py:181/208/220`'s three `gate_error == GATE_REFUSED_MESSAGE` assertions, unmodified.

### Task 3: Move the fault template and the ten read labels out of `admin_state.py`

- **File**: `chat_ui/chat_ui/admin_state.py`
- **Action**: UPDATE
- **Implement**: Delete the `LOAD_FAILED_MESSAGE = (...)` assignment and add it to the same `from .admin_copy import ...` line as `FAULT_MESSAGE_TEMPLATE as LOAD_FAILED_MESSAGE` — aliased, so `load()`'s `LOAD_FAILED_MESSAGE.format(read=..., detail=...)` call site is untouched and the name a future test may import still resolves. Then replace each of the ten inline label literals in `_READS` with its `admin_copy.READ_LABEL_*` constant, importing them by name. Update the `_READS` comment: "The label is the only user-facing string here and moves to admin_copy.py with STORY-008" becomes a statement that the labels now come from `admin_copy`, and the `len(_READS) == 10` invariant note stays.
- **Mirror**: the existing aliased-import convention already in this file (`top_models as read_top_models`) and its comment explaining why the alias exists.
- **Do not**: change any of the ten label *values*, or the tuple's order — `_READS`' order is documented as deliberate (rows first, `total_recorded` second) and `tests/test_admin_state.py` asserts a call count of 8 against a mid-table failure.
- **Validate**: `python -m pytest tests/test_admin_state.py -q` (unchanged pass count) plus `git diff -U0 chat_ui/chat_ui/admin_state.py | grep '^[-+].*"the '` shows each removed literal reappearing only as a constant reference.

### Task 4: Extend `tests/test_copy.py` with the admin constants

- **File**: `tests/test_copy.py`
- **Action**: UPDATE (append-only)
- **Implement**: Add one `from chat_ui.chat_ui.admin_copy import (...)` block below the existing chat import, and append — after every existing test, changing none of them — (a) `test_admin_copy_constants_exist_and_not_empty`, a flat `assert CONSTANT` per constant in the module, matching `test_copy_constants_exist_and_not_empty`'s shape; (b) `test_admin_copy_templates_carry_their_placeholders`, asserting each `_TEMPLATE` contains its named fields and `.format(...)`s without `KeyError`; (c) `test_refresh_keeps_one_verb_across_the_flow`, asserting `REFRESH_LABEL.lower()` is a prefix of `REFRESHED_TEMPLATE.lower()` and that no constant in the module contains `"session ended"` (AC 4); (d) `test_one_refusal_message_only`, asserting `GATE_REFUSED_MESSAGE` is the only module-level name matching `*REFUS*`/`*DENIED_ACCESS*` (AC 5, and the seam STORY-016 extends). Assert on substance, never on a whole sentence.
- **Mirror**: `tests/test_copy.py:1-6` (import preamble), `:31-46` (flat non-empty test), `:49-55` (a named test per string with a requirement, docstring citing the AC/Risk).
- **Do not**: touch, reword or reorder any of the nine existing tests — PRD Section 15 lists this file as must-pass-unmodified and the reading below (Risk 1) is *append-only*.
- **Validate**: `python -m pytest tests/test_copy.py -q` → the 8 existing tests (17 cases with the parametrize) still pass by name, plus the 4 new ones.

### Task 5: Prove the chat surface and `app/` are untouched

- **File**: none
- **Action**: verification only
- **Implement**: Confirm the diff is the three files this plan names and nothing else, that `copy.py` is byte-identical, and that no admin module imports a chat module.
- **Validate**:
  ```bash
  git diff --stat main -- app/            # empty
  git diff --stat main -- chat_ui/chat_ui/copy.py   # empty
  grep -rn "from chat_ui.chat_ui.copy\|from .copy import\|from chat_ui import copy" chat_ui/chat_ui/admin_*.py   # no output
  python -m pytest tests/ -q
  ```

---

## End-to-End Tests

No page renders these strings yet — STORY-009 … STORY-017 are the consumers and all eight are `todo` — so there is no browser check to run, and inventing one would mean writing a throwaway page this story does not own. The checks are therefore static, and the visual half (that the masthead's two words fit the hairline, that a column head does not wrap at `TEXT_MICRO`, that the no-matches sentence reads as an invitation rather than a scold) belongs to STORY-011/014's validation and to STORY-019's self-critique.

- [ ] `python -c "from chat_ui.chat_ui import admin_copy"` imports clean with no `rx.` import and no chat import
- [ ] `python -c "from chat_ui.chat_ui.admin_state import GATE_REFUSED_MESSAGE, LOAD_FAILED_MESSAGE"` still resolves — the re-export holds the existing import path
- [ ] `python -c "from chat_ui.chat_ui import admin_copy as c; print(c.REGISTER_SCOPE_TEMPLATE.format(shown=100, total=3180))"` → `100 most recent of 3,180`-shaped output
- [ ] `python -c "from chat_ui.chat_ui import admin_copy as c; print(c.REFRESHED_TEMPLATE.format(time='14:22:07'))"` → `Refreshed 14:22:07`
- [ ] `python -c "from chat_ui.chat_ui import admin_copy as c; assert 'success rate' not in c.FIGURE_COMPLETION_LABEL.lower()"`
- [ ] Every `READ_LABEL_*` value appears verbatim in `_READS` and `tests/test_admin_state.py` passes unmodified
- [ ] `git diff main --stat -- app/` is empty
- [ ] Full suite green, PRD-001/003/004 tests unmodified

---

## Validation

```bash
python -m pytest tests/test_copy.py tests/test_admin_state.py -q
python -m pytest tests/ -q
python -c "from chat_ui.chat_ui import admin_copy, admin_state"
git diff --stat main -- app/
git diff chat_ui/chat_ui/admin_state.py
```

---

## Risks + Mitigations

**1. `tests/test_copy.py` is on PRD Section 15's "must pass unmodified" list, and AC 6 requires extending it.**
The two readings collide, exactly as they did for `tests/test_contrast.py` in STORY-007.
*Mitigation*: the same resolution, for consistency — read "unmodified" as *no existing assertion weakened, reworded, reordered or removed*, which is what the list protects. Task 4 is strictly append-only and says so; the eight existing tests must still be present and passing **by name** afterwards, and the report records the before/after counts. STORY-016 has an explicit escape hatch its story text already grants (*"a separate `tests/test_admin_copy.py` is equally acceptable"*) and should use it, so the pinning tests never touch this file at all.

**2. Moving three string groups out of `admin_state.py` could break `tests/test_admin_state.py`, which is 61 passing tests this story does not own.**
`GATE_REFUSED_MESSAGE` is imported from `admin_state` by name at line 65, and three read labels are asserted as literals.
*Mitigation*: the move is a **re-export**, not a relocation of the import path — `from .admin_copy import GATE_REFUSED_MESSAGE` leaves `chat_ui.chat_ui.admin_state.GATE_REFUSED_MESSAGE` resolving to the identical object, and the ten label values are copied byte-for-byte with no rewording. Task 2 and Task 3 each validate against the untouched test file before the next task starts. If a value ever *should* change wording, that is a deliberate edit with the test updated in the same commit — not a side effect of this move.

**3. Naming the constants wrong is expensive here in a way it is not elsewhere.**
Eight stories import from this module; a rename after STORY-011 lands is a multi-file edit, and this story is the last cheap moment.
*Mitigation*: every name above is derived from the surface it appears on (`COLUMN_*`, `FIGURE_*`, `DETAIL_*`, `EMPTY_*`, `FILTER_*`, `SORT_*`, `READ_LABEL_*`), matching how `copy.py` groups by `SHELL_*` / `EMPTY_STATE_*` / `DUPLICATE_*`, and the four `SORT_*_LABEL` and four `VERDICT_*_LABEL` names are aligned one-to-one with `admin_state.SORT_KEYS` and `admin_formatting.VERDICTS` so a mismatch is visible at a glance. Constants (not a dict) mean a wrong name fails at import, in the test run, not at render.

**4. The completion label is the one string that can be *wrong* rather than merely awkward.**
"Success rate" is the phrasing every reader's fingers reach for, and it misstates the number.
*Mitigation*: the word *success* is absent from `FIGURE_COMPLETION_LABEL` and from `FIGURE_COMPLETION_NOTE`; the reason is a comment directly above them quoting PRD Section 1's diagnosis; and STORY-016 exists solely to pin it. Task 4's E2E check asserts the forbidden phrase now, so the guard is in place from this commit rather than from STORY-016's.

**5. Copy drift back into components.**
AC 2's grep passes vacuously today, so nothing *proves* the rule until components exist — and the first component to want a word this module lacks will inline it.
*Mitigation*: the module is written to over-cover deliberately — every downstream story's strings are here now, including STORY-012's disclosure labels and STORY-015's nine figure labels, so the components that land later find their words already named. Where a component still needs one, the fix is a constant here, and STORY-018's render-invariant tests plus STORY-019's pass are where the grep becomes a real check.

**6. Over-building toward an i18n catalogue.**
A "copy module" with forty constants invites a dict, a lookup helper, or a `Copy` class.
*Mitigation*: PRD Section 4 puts a full i18n framework out of scope and `copy.py` is the shape to match — flat constants, no accessor. Task 1's validation asserts the module has zero imports, which forecloses the helper-module version of the same drift.

---

## Acceptance Criteria

(Copied from story `STORY-008`)

- [ ] Given `chat_ui/chat_ui/admin_copy.py`, when it is created, then it holds every admin-facing string: the masthead, the two view-switch labels, the sign-out label, the gate prompt and its single refusal message, the column heads, the four verdict labels, the scope lines, the refresh label and refreshed stamp template, the fault panel, and the three empty states.
- [ ] Given any admin component, when it is grepped for quoted user-facing text, then none is found — every string resolves through `admin_copy`.
- [ ] Given a label with a value in it, when it is defined, then it is a template constant (as `chat_ui/chat_ui/copy.py`'s `PII_BADGE_TEMPLATE` is) rather than string concatenation at the call site — including "100 most recent of {total}" and "Refreshed {time}".
- [ ] Given the refresh control and the post-refresh line, when both are read, then they share the same verb — the control labeled **Refresh** produces the line **Refreshed 14:22:07**, and **Sign out** returns the gate rather than a "session ended" notice.
- [ ] Given the gate refusal string, when it is read, then it states that access was refused and does not say why — one message for empty, malformed and wrong tokens alike.
- [ ] Given `admin_copy.py`, when `tests/test_copy.py` is extended, then each constant is asserted non-empty, matching the existing test's pattern.
- [ ] All tasks completed
- [ ] `tests/test_admin_state.py` passes unmodified
- [ ] `git diff main --stat -- app/` is empty
- [ ] Follows existing patterns (`copy.py`'s grouping, naming and template conventions)
