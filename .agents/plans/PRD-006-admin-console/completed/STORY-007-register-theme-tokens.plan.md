---
story: STORY-007
prd: PRD-006
slug: register-theme-tokens
title: "theme.py register tokens: row height, stamp-margin width, hover ground, micro type step"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-006-admin-console
created: 2026-08-30
---

# Plan: `theme.py` register tokens — four additions, no new hue

## Summary

Add the four tokens PRD Section 12 Phase 2 names — a register row height, a stamp-margin width, a row hover ground and a micro type step — to `chat_ui/chat_ui/theme.py` as module constants beside the existing ones, and prove the one new colour among them against `tests/test_contrast.py`. Three of the four are sizes and carry no contrast risk; the fourth, the hover ground, is the only new hue-bearing value in the whole console and is therefore the only real work in this story. It is picked, not invented: the candidates were measured with the repo's own `contrast()` helper before this plan was written, and `#F1F3F5` — a neutral step between `CARD` and `PAPER`, on the existing blue-grey axis — clears WCAG AA against all four verdict inks (5.45 … 7.12), against `INK` (16.04) and against `MUTE` (4.80), so a hovered row stays readable whether the register sits on the card or on the paper. The stamp margin is not a fresh number at all: `STAMP_X = RAIL_X` continues the chat's rail literally, which is what PRD Section 6.1 asks for. This is an **additions-only** edit: no existing token value changes, so the chat surface renders identically, and every assertion already in `tests/test_contrast.py` is preserved verbatim while new tables are appended beside them.

## User Story

As an integrating developer
I want every new size and colour the console needs added to `theme.py` and nowhere else
So that the single-file token guarantee PRD-004 established survives a second surface.

## Story Reference

- Story file: `.agents/stories/PRD-006-admin-console/STORY-007-register-theme-tokens.md`
- PRD: `.agents/PRDs/PRD-006-admin-console/PRD.md` — Section 4 (design & copy), Section 6.1 (colour, type, the stamp margin), Section 8, Section 12 Phase 2, Risk 6

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | `chat_ui/chat_ui/theme.py` (UPDATE), `tests/test_contrast.py` (UPDATE, additive), `tests/test_admin_palette.py` (CREATE). No `app/` change, no component change, no new dependency. |
| Story | STORY-007 |
| PRD | PRD-006 |
| Epic Branch | `epic/PRD-006-admin-console` (commit directly on this branch) |

**Dependency check**: `depends_on: []` — nothing blocks this story. `blocks: [STORY-009, STORY-011, STORY-015, STORY-018]`, all four still `todo`, so no downstream file yet reads these names and the token names chosen here are still free. Working tree clean on `epic/PRD-006-admin-console` at `d1da6d5`. Baseline captured before planning: `python -m pytest tests/test_contrast.py -q` → **16 passed in 0.02s**. Cleared to proceed.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `.agents/skills/frontend-design` | Read in full (`.agents/skills/frontend-design/SKILL.md`). **Binding on this story** — it is the only story-listed skill and this is a palette/type decision. The governing rule is the one the story quotes verbatim: *"Where the brief pins down a visual direction, follow it exactly — the brief's own words always win, including when it asks for one of these looks."* PRD Section 6.1 is that pin, so the palette is inherited and no accent is proposed. Two further rules bind: *"Spend your boldness in one place"* — spent already on the stamp margin, so the hover ground must be near-invisible rather than a second signal; and the calibration warning against a default look — the hover value is deliberately kept on the existing cool blue-grey axis, not warmed toward the cream default the skill names. | Task 1, Task 3 |
| `reflex-docs` (**NOT INSTALLED**) | `chat_ui/AGENTS.md` mandates it for any Reflex API. This story uses **no Reflex API**: `theme.py` is plain module constants with no `rx.` import, and the tests are plain `pytest`. Nothing to substitute. | none |
| `reflex-process-management` (**NOT INSTALLED**) | Mandated for any compile/run/reload cycle. This story starts no server and compiles no page — validation is `pytest` plus a `git diff` read. | none |

`.agents/skills/` holds exactly one skill (`frontend-design`); the two Reflex skills ship in the `reflex-dev/agent-skills` plugin, which is not installed here — the same gap STORY-001 … STORY-006 each recorded. Unlike those stories, this one needs no substitution at all, because it touches no Reflex surface.

---

## Patterns to Follow

### Naming — bare structural nouns, a trailing axis letter where the axis matters

```python
# SOURCE: chat_ui/chat_ui/theme.py:74-79
RADIUS = "3px"
RAIL_X = "1.875rem"  # rail's distance from the transcript's left edge
GLYPH = "9px"
COLUMN_MAX = "56rem"
MEASURE = "42rem"  # reading measure for prose — roughly 70 characters
PANEL_MAX = "36rem"  # a verdict is a short record, not a banner
```

No prefix, no namespace, no `ADMIN_` qualifier: the file is the namespace, and `RAIL_X` already sets the precedent that a horizontal margin measure ends in `_X`. `STAMP_X` and `ROW_H` follow it. Sizes are CSS strings with units, never bare numbers.

### The type scale — one `TEXT_*` constant per step, ascending, with the role in the comment

```python
# SOURCE: chat_ui/chat_ui/theme.py:68-72
# --- Scale ---------------------------------------------------------------
TEXT_TAG = "0.6875rem"  # verdict tags, eyebrows
TEXT_DATA = "0.75rem"  # footers, evidence lines
TEXT_BODY = "0.9375rem"
TEXT_LEAD = "1.0625rem"
```

`TEXT_MICRO` is a *new smallest* step, so it belongs above `TEXT_TAG` to keep the block ascending.

### Grounds live in one block, each with the reason it exists

```python
# SOURCE: chat_ui/chat_ui/theme.py:14-25
# --- Ground --------------------------------------------------------------
# A cool blue-grey paper rather than warm cream: this is an institutional
# record, not a magazine.
PAPER = "#ECEFF1"
CARD = "#FFFFFF"
INK = "#14181C"
MUTE = "#626C77"
RULE = "#CBD2D9"
RULE_SOFT = "#DDE2E7"
```

Every value in this block is a cool blue-grey with the green channel between the red and the blue (`EC-EF-F1`, `CB-D2-D9`, `DD-E2-E7`). The hover ground has to sit on that same axis or it reads as a tint.

### Contrast tests — one named table, parametrized, `contrast()` reused not rewritten

```python
# SOURCE: tests/test_contrast.py:44-63
_INK_ON_TINT = [
    ("INK_CLEAR", theme.INK_CLEAR, theme.TINT_CLEAR),
    ...
]


@pytest.mark.parametrize("name,ink,tint", _INK_ON_TINT)
def test_verdict_ink_is_readable_on_the_paper(name, ink, tint):
    """The tag is small text on the transcript ground."""
    assert contrast(ink, theme.PAPER) >= AA_NORMAL, name
```

The story's technical note pins this: *"extend it with an ink-on-hover-ground table rather than writing a second helper."*

### The test import preamble — repo root, never `chat_ui/`

```python
# SOURCE: tests/test_contrast.py:9-18
import sys
from pathlib import Path

# Repo root, not chat_ui/ — putting the inner package on sys.path[0] shadows
# the namespace package every other test module imports through.
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from chat_ui.chat_ui import theme
```

---

## The four tokens — values, and why these values

| Token | Value | Where it goes | Derivation |
|---|---|---|---|
| `HOVER` | `"#F1F3F5"` | Ground block, after `RULE_SOFT`, before the `SPINE` comment | The only new hue-bearing value in the console. Sits between `CARD` (`#FFFFFF`) and `PAPER` (`#ECEFF1`) on the existing blue-grey axis (`F1-F3-F5`: green between red and blue, exactly as `PAPER`/`RULE`/`RULE_SOFT` do). Perceptible against `CARD` (1.11:1) yet lighter than `PAPER`, so it works as a hover whether the register body is drawn on the card or on the paper. |
| `ROW_H` | `"2.25rem"` | Metrics block, after `GLYPH` | 36px. Dense enough that a hundred rows read as one continuous stripe of exceptions down the stamp margin, and tall enough that the row-level disclosure control clears the WCAG 2.2 24×24 target-size minimum with room to spare. Expressed in `rem` like `RAIL_X`, not `px` like `GLYPH`, because it scales with the reader's type size. |
| `STAMP_X` | `RAIL_X` (the constant, not a copy of its literal) | Metrics block, immediately after `RAIL_X` | PRD Section 6.1: *"This is the chat's rail (`RAIL_X`, `GLYPH`, `SPINE` — already in `theme.py`) continued rather than reinvented."* Binding to the constant makes the continuation structural: retuning the chat's rail retunes the register's margin in the same edit, and the two can never silently drift apart. |
| `TEXT_MICRO` | `"0.625rem"` | Scale block, above `TEXT_TAG` | 10px, one step below `TEXT_TAG` (11px), keeping the block ascending. Reserved for the register's column heads — Archivo, uppercase, wide tracking — where the label is a signpost the admin reads once, not content they read a hundred times. Never for row data, which stays at `TEXT_DATA`. |

**Measured before choosing.** Run against the repo's own `tests/test_contrast.py::contrast`, candidates in the `CARD`→`PAPER` band:

| Ground | `INK_CLEAR` | `INK_HELD` | `INK_DENIED` | `INK_FAULT` | `INK` | `MUTE` |
|---|---|---|---|---|---|---|
| `#F4F6F7` | 7.05 | 5.59 | 7.31 | 6.86 | 16.46 | 4.93 |
| **`#F1F3F5`** | **6.87** | **5.45** | **7.12** | **6.69** | **16.04** | **4.80** |
| `#EFF2F4` | 6.79 | 5.39 | 7.05 | 6.61 | 15.87 | 4.75 |

`#F1F3F5` is the darkest of the three that still holds a comfortable margin over 4.5 on the tightest pairing (`INK_HELD`, the ochre that had to be darkened once already), and the darkest gives the most visible hover.

**Why the hover ground is not a step *down* from `PAPER`.** The obvious alternative — hover by darkening, e.g. `#E3E8EC` — was measured and rejected: it puts `MUTE` at **4.33**, below AA. `MUTE` is already at 4.63 on `PAPER`, so it has 0.13 of headroom and any darkening spends it. Since the register's timestamps and secondary columns are exactly the kind of text `MUTE` sets, hovering must lighten, not darken. This is recorded here so the "improvement" is not reintroduced in STORY-011.

**What this story does *not* add**, each for a stated reason:

- **No tint.** PRD Section 6.1: *"a hundred tinted rows would be a heat map of noise."* No `TINT_*` name is added and none of the existing five is referenced by the console.
- **No accent.** The frontend-design skill's pinned-direction rule, applied to PRD Section 6.1's *"no cards, no fills, and no accent colour of its own."*
- **No verdict→ink map.** PRD Section 6.1's table maps the four verdicts onto four existing inks, but the mapping is dispatched with `rx.match` at the component level and belongs to STORY-011. Putting a dict in `theme.py` would make the token file import-aware of the verdict vocabulary in `admin_formatting.py`, which it currently is not.
- **No dark or narrow-viewport variant.** `GLOBAL_CSS` declares `color-scheme: light` and the responsive pass is STORY-019.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/theme.py` | UPDATE | Add `HOVER` to the Ground block, `TEXT_MICRO` to the Scale block, `ROW_H` and `STAMP_X` to the metrics block. Additions only — no existing line's value changes. |
| `tests/test_contrast.py` | UPDATE (additive) | Append an `_INK_ON_HOVER` table using the existing `contrast()` helper, plus `INK`-on-hover and `MUTE`-on-hover rows in the neutral-pairs list. Every existing assertion preserved verbatim. |
| `tests/test_admin_palette.py` | CREATE | Assert AC 1 (the four tokens exist and are well-formed) and AC 3 (`INK_UPSTREAM` / `INK_SELF` referenced by no admin module). STORY-018 extends this same file with the rendered-output half of Risk 6 rather than starting a third palette file. |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add `HOVER` to the Ground block

- **File**: `chat_ui/chat_ui/theme.py`
- **Action**: UPDATE
- **Implement**: After `RULE_SOFT = "#DDE2E7"` (line 22) and before the `# The rail itself.` comment that introduces `SPINE`, add:

  ```python
  # The register's row hover. A hover has to be findable without becoming a
  # second signal — the stamp margin is where this surface spends its
  # boldness — so it lifts toward the card rather than darkening toward the
  # rule. Darkening was measured and rejected: it drops MUTE below AA, and
  # MUTE sets the register's timestamps.
  HOVER = "#F1F3F5"
  ```

  Keep it inside the `--- Ground ---` block: it is a ground, and the block is where a reader looks for one.
- **Mirror**: `chat_ui/chat_ui/theme.py:14-25` — one constant per line, the reason in the comment above it, cool blue-grey axis.
- **Do not**: touch `PAPER`, `CARD`, `INK`, `MUTE`, `RULE`, `RULE_SOFT` or `SPINE`. AC 6 is a byte-level claim about the chat.
- **Validate**: `python -c "from chat_ui.chat_ui import theme; print(theme.HOVER)"` → `#F1F3F5`

### Task 2: Add `TEXT_MICRO` to the Scale block

- **File**: `chat_ui/chat_ui/theme.py`
- **Action**: UPDATE
- **Implement**: Insert as the first entry of the `--- Scale ---` block, above `TEXT_TAG` (line 69), so the block stays ascending:

  ```python
  TEXT_MICRO = "0.625rem"  # register column heads — a signpost, never row data
  ```
- **Mirror**: `chat_ui/chat_ui/theme.py:69-72` — trailing `#` comment naming the role, `rem` units.
- **Validate**: `python -c "from chat_ui.chat_ui import theme; print(theme.TEXT_MICRO, theme.TEXT_TAG)"` → `0.625rem 0.6875rem`

### Task 3: Add `ROW_H` and `STAMP_X` to the metrics block

- **File**: `chat_ui/chat_ui/theme.py`
- **Action**: UPDATE
- **Implement**: In the block at lines 74-79, add `STAMP_X` immediately after `RAIL_X` and `ROW_H` after `GLYPH`:

  ```python
  RAIL_X = "1.875rem"  # rail's distance from the transcript's left edge
  STAMP_X = RAIL_X  # the register's stamp margin *is* the chat's rail, continued
  GLYPH = "9px"
  ROW_H = "2.25rem"  # one register row: dense enough to scan a hundred
  ```

  `STAMP_X` binds to the constant deliberately — see the derivation table. Do not copy the literal `"1.875rem"`.
- **Mirror**: `chat_ui/chat_ui/theme.py:74-79`; the rail's consumers are `chat_ui/chat_ui/components/bubbles.py:26-45`, which is the geometry `STAMP_X` is continuing.
- **Validate**: `python -c "from chat_ui.chat_ui import theme; assert theme.STAMP_X == theme.RAIL_X; print(theme.ROW_H, theme.STAMP_X)"` → `2.25rem 1.875rem`

### Task 4: Extend `tests/test_contrast.py` with the hover-ground table

- **File**: `tests/test_contrast.py`
- **Action**: UPDATE — **append only**. Do not edit, reorder or reword any existing test; PRD Section 15 lists this file among those that must keep passing.
- **Implement**:
  1. After the `_INK_ON_TINT` tests, add the parallel table and its test:

     ```python
     # The register draws every verdict ink on the row hover ground, so the
     # hover is a fifth ground the inks have to clear — not a decoration.
     _INK_ON_HOVER = [
         ("INK_CLEAR", theme.INK_CLEAR),
         ("INK_HELD", theme.INK_HELD),
         ("INK_DENIED", theme.INK_DENIED),
         ("INK_FAULT", theme.INK_FAULT),
     ]


     @pytest.mark.parametrize("name,ink", _INK_ON_HOVER)
     def test_verdict_ink_is_readable_on_the_row_hover(name, ink):
         """A hovered row is still a row being read."""
         assert contrast(ink, theme.HOVER) >= AA_NORMAL, name
     ```

     Four entries, not six: `INK_UPSTREAM` and `INK_SELF` are chat-only per PRD Section 6.1, and asserting them here would imply the console draws them.
  2. Add three rows to the existing `test_neutral_pairs_are_readable` parametrize list — `("body ink on row hover", theme.INK, theme.HOVER)`, `("muted text on row hover", theme.MUTE, theme.HOVER)`, `("rule on row hover", theme.RULE, theme.HOVER)` — **appended** to the list, existing rows untouched. The `MUTE` row is the one that matters: it is the pairing that ruled out a darkening hover.

     Expect the `RULE` row to fail — measured at ~1.47:1, because `RULE` is a hairline, not text, and AA does not apply to it. Drop that third row rather than weakening `AA_NORMAL`, and record the drop in the report. It is listed here so the decision is made deliberately rather than by omission.
  3. Update the module docstring's second paragraph to name the hover ground as the second thing this file now holds the line on. One sentence, no rewrite of the existing text.
- **Mirror**: `tests/test_contrast.py:44-77`
- **Validate**: `python -m pytest tests/test_contrast.py -q` → was 16 passed; expect **22 passed** (16 + 4 hover inks + the `INK` and `MUTE` neutral rows), or 23 if the `RULE` row is kept and passes.

### Task 5: Create `tests/test_admin_palette.py` — the chat-only inks stay chat-only

- **File**: `tests/test_admin_palette.py`
- **Action**: CREATE
- **Implement**: Use the repo-root import preamble verbatim from `tests/test_contrast.py:9-18`. Two groups:
  1. **AC 1 — the four tokens exist and are well-formed.** Assert `HOVER`, `ROW_H`, `STAMP_X`, `TEXT_MICRO` are present on `theme`; that `HOVER` matches `^#[0-9A-F]{6}$`; that `ROW_H` and `TEXT_MICRO` end in `rem`; and that `STAMP_X is theme.RAIL_X` — pinning the derivation, not just the value, so a later hand-copied literal fails the test.
  2. **AC 3 — no admin module names a chat-only ink.** Glob `chat_ui/chat_ui/admin_*.py` and `chat_ui/chat_ui/components/admin_*.py` / `register.py` / `summary.py`, read each as text, and assert neither `INK_UPSTREAM` nor `INK_SELF` appears. Write it so the set is discovered by glob, not hard-coded: STORY-009/011/015 add modules to it and the guard must cover them the day they land. Assert the glob is non-empty for the `chat_ui/chat_ui/admin_*.py` pattern (three modules exist today: `admin_models.py`, `admin_formatting.py`, `admin_state.py`) so a broken pattern cannot pass vacuously.
- **Important — state the exception in the module docstring**: `theme.GLOBAL_CSS:99-103` sets the global `:focus-visible` outline to `INK_UPSTREAM`, and the admin pages inherit that stylesheet. That is not a violation — the rule is about *admin modules*, and the focus ring is a shared accessibility affordance, not a verdict signal — but a naive grep of rendered admin HTML will find that blue. Record it here so STORY-018's rendered-output assertion is written knowing about it instead of discovering it as a failure.
- **Mirror**: `tests/test_contrast.py:9-18` for the preamble; `tests/test_admin_models.py` for the module-docstring-states-the-rule style.
- **Validate**: `python -m pytest tests/test_admin_palette.py -q` → all pass.

### Task 6: Prove the chat is untouched

- **File**: none — verification only.
- **Action**: VERIFY
- **Implement**: Read `git diff chat_ui/chat_ui/theme.py` and confirm every hunk is an addition: no `-` line except where a `+` line is inserted between existing ones. Confirm no `TINT_`, no new hue beyond `HOVER`, and no change to any existing constant's value.
- **Validate**:
  - `git diff --stat chat_ui/chat_ui/theme.py` — insertions only, no deletions among the token constants
  - `python -m pytest tests/ -q` — full suite green, with `tests/test_chat_state.py`, `tests/test_copy.py`, `tests/test_pii_badge.py` and `tests/test_chat_components_import.py` unmodified
  - `git diff --stat main -- app/` — **empty**; PRD Section 4 forbids any `app/` change

---

## End-to-End Tests

No page renders these tokens yet — STORY-009/011/015 are the consumers, and all three are still `todo` — so there is no browser check to run and inventing one would mean writing a throwaway page this story does not own. The E2E checks are therefore static:

- [ ] `python -c "from chat_ui.chat_ui import theme"` imports clean — the module has no `rx.` import and must stay importable outside a Reflex app context, which every test in `tests/` depends on
- [ ] All four names resolve: `HOVER`, `ROW_H`, `STAMP_X`, `TEXT_MICRO`
- [ ] `theme.STAMP_X is theme.RAIL_X` — the rail is continued, not copied
- [ ] `theme.GLOBAL_CSS` still formats without a `KeyError` (it is an f-string over the constants; adding names cannot break it, but the import proves it)
- [ ] `git diff main -- app/` is empty
- [ ] Full suite green, PRD-001/003/004 tests unmodified

The visual half — that a hundred rows resolve into a scannable stripe, and that the hover is findable without shouting — is genuinely unverifiable until STORY-011 draws the table. It is Phase 2's validation, not this story's, and STORY-019's self-critique is where the hover value gets looked at with real rows behind it. If it reads too faint there, the fix is one line in this file, which is the whole point of the single-file guarantee.

---

## Validation

```bash
python -m pytest tests/test_contrast.py tests/test_admin_palette.py -q
python -m pytest tests/ -q
python -c "from chat_ui.chat_ui import theme; assert theme.STAMP_X is theme.RAIL_X"
git diff --stat main -- app/
git diff chat_ui/chat_ui/theme.py
```

---

## Risks + Mitigations

**1. `tests/test_contrast.py` is on PRD Section 15's "must pass unmodified" list, and this story modifies it.**
The story's own AC 4 requires extending that file, so the two readings collide.
*Mitigation*: read "unmodified" as *no existing assertion weakened, reworded or removed* — which is what the list protects. Task 4 is append-only and states so explicitly; the 16 existing tests must still be present and passing by name after the edit, and the report records the before/after counts (16 → 22).

**2. The hover ground is chosen against a ground the register does not have yet.**
`#F1F3F5` was measured on the assumption that the register body is drawn on `CARD` or `PAPER`. STORY-011 could land it on something else.
*Mitigation*: the value sits *between* `CARD` and `PAPER`, so it reads as a hover against either, and both are the only two grounds `theme.py` defines. If STORY-011 introduces a third ground, that is a new token and a new contrast row in the same file — the guarantee holds by construction.

**3. `ROW_H` is a number picked without a hundred real rows behind it.**
36px is reasoned from target size and scan density, not observed.
*Mitigation*: it is one line in one file, and STORY-019's self-critique pass is the scheduled moment to retune it. Recorded as an expected-to-be-revisited value rather than a settled one.

**4. Drift toward a tint (PRD Risk 6).**
The next reasonable-looking step after "row hover ground" is "verdict row tint", and `TINT_*` already exists.
*Mitigation*: this story adds no tint name; Task 5's guard file is where STORY-018 hangs the rendered-output assertion that no `TINT_*` value reaches the console.

---

## Acceptance Criteria

(Copied from story `STORY-007`)

- [ ] Given `chat_ui/chat_ui/theme.py`, when the console's tokens are added, then it gains at least a register row height, a stamp-margin width, a row hover ground and a micro type step — the four PRD Section 12 Phase 2 names — each as a module constant beside the existing ones.
- [ ] Given the console's palette, when the tokens are read, then it reuses `INK_CLEAR`, `INK_HELD`, `INK_DENIED`, `INK_FAULT`, `PAPER`, `CARD`, `RULE`, `RULE_SOFT`, `MUTE`, `SPINE` unchanged, and introduces **no** new hue — no accent colour of the console's own.
- [ ] Given `INK_UPSTREAM` and `INK_SELF`, when the console is inspected, then neither is referenced by any admin module — they stay chat-only (PRD Section 6.1).
- [ ] Given any new ink/ground pairing the console introduces, when `tests/test_contrast.py` runs, then that pairing is asserted at or above `AA_NORMAL` (4.5:1) alongside the existing chat pairings.
- [ ] Given the new hover ground, when its contrast against every verdict ink and against `INK` is measured, then each clears WCAG AA and is covered by the contrast test.
- [ ] Given the chat surface, when it is loaded after this change, then it renders identically — no existing token value is altered, only additions are made.
- [ ] All tasks completed
- [ ] `python -m pytest tests/ -q` green, PRD-001/003/004 tests unmodified
- [ ] `git diff main -- app/` empty
- [ ] Follows existing patterns
