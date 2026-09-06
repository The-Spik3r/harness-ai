---
story: STORY-017
prd: PRD-008
slug: rail-tokens-and-copy
title: "Rail tokens in theme.py and every rail string in copy.py, adding no new ink"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-06
---

# Plan: Rail tokens in theme.py and every rail string in copy.py, adding no new ink

## Summary

Four size tokens and ten strings, appended to two files that already exist, plus three new tests. Nothing renders. This story is the declaration pass that STORY-018 builds against: after it, `session_rail.py` has no size to choose, no word to write and no colour to reach for, and the single-file guarantees that `theme.py` and `copy.py` each carry are still true once a rail exists.

The interesting part of a story this small is what it is forbidden to add. The palette is closed: the rail is `PAPER` against the transcript's `CARD`, ruled with `RULE`, and its active row is marked with the `RAIL_X` / `GLYPH` / `SPINE` device that `bubbles.py` and `register.py` already draw at two other scales. So the theme diff contains **no hex literal at all** — four `rem`-valued sizes and a comment naming the three tokens the mark reuses. `tests/test_contrast.py` therefore passes unmodified, and that is not a happy accident to be checked at the end: it is the story's proof that AC 2 held. If that suite needs a line, a colour was added that the PRD said not to add.

On the copy side, six of the rail's strings already exist — STORY-012 wrote the two row fallbacks, STORY-014/015 the three save/load notices, STORY-016 the delete confirmation and its label — each with a comment reserving the remainder for this story by name. This plan adds exactly that remainder and nothing further: the **New chat** label, the empty-rail invitation, the read-failure line, the rename affordance, the delete dialog's dismissal, the cap line STORY-018 AC 11 needs, and the collapse control STORY-019 needs. Every one has a named consumer in Phase 4, which is the story's own bar: *"if a string has no consumer by the end of Phase 4, it should not have been added."*

Two findings from the exploration are recorded rather than fixed here, because `state.py` is not this story's file. First, `sessions_error` is set to `str(exc)` at four sites (`state.py:220`, `:425`, `:496`, `:750`), and `ChatSessionError` is raised as `f"{operation} failed: {exc}"` (`app/services/chat_sessions.py:85`) — storage-mechanism text that must never reach a reader. The fault copy below is written so STORY-018 renders **the constant**, using `sessions_error` only as the trigger. Second, no handler re-reads the session list, so STORY-018's retry has nothing to call yet. Both are in **Risks**.

## User Story

As a maintainer
I want the rail's sizes and words declared before the rail is built
So that the component that follows has nothing left to invent.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-017-rail-tokens-and-copy.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md` — Section 4 (Surface), Section 6.1 (Color, Type, Layout, Signature, Copy), Section 11 (Quality indicators), Section 12 Phase 4, Risk 6

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | `chat_ui/chat_ui/theme.py`, `chat_ui/chat_ui/copy.py`, `tests/test_copy.py` |
| Story | STORY-017 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |
| Depends on | None (verified: `depends_on: []`) |
| Blocks | STORY-018 |

---

## Skills In Use

`.agents/skills/` was listed in full. It holds exactly one skill, `frontend-design`, and its `SKILL.md` was read end to end. The story's frontmatter names it and nothing else; no other `SKILL.md` in that directory matches this domain because there is no other. The two plugin skills `chat_ui/AGENTS.md` mandates — `reflex-docs` and `reflex-process-management` — are named here for completeness and are **not** engaged: this story writes no Reflex component and starts no Reflex process. They are STORY-018's and STORY-019's.

| Skill | Rule from SKILL.md, verbatim | Tasks affected |
|-------|------------------------------|----------------|
| `.agents/skills/frontend-design` | *"Where the brief pins down a visual direction, follow it exactly — the brief's own words always win."* The brief is PRD Section 6.1 plus `theme.py`'s inspection ledger. This story proposes no direction. | Task 1 |
| `.agents/skills/frontend-design` | *"Structural devices... should encode something true about the content, not decorate it."* The spine encodes *which one of these is the one*, which is why the active mark reuses `SPINE`/`GLYPH`/`RAIL_X` instead of declaring a fourth device. | Task 1 |
| `.agents/skills/frontend-design` | *"An empty screen is an invitation to act."* | Task 2, Task 4 |
| `.agents/skills/frontend-design` | *"Errors don't apologize, and they are never vague about what happened."* | Task 2, Task 4 |
| `.agents/skills/frontend-design` | *"An action keeps the same name through the whole flow, so the button that says 'Publish' produces a toast that says 'Published.'"* — **New chat** produces a chat; **Retry** appears in the fault line and on its control; **Delete** is already the affordance, the dialog and the confirmation. | Task 2, Task 5 |
| `.agents/skills/frontend-design` | *"Name things by what people control and recognize, never by how the system is built."* — the direct reason `str(exc)` must not be the fault line. | Task 2, Risks |
| `.agents/skills/frontend-design` | *"Keep the register conversational and tuned: plain verbs, sentence case, no filler."* | Task 2 |
| `.agents/skills/frontend-design` | *"Before leaving the house, take a look in the mirror and remove one accessory."* — applied in Task 2 to the three strings this plan considered and cut (see **Deviations**). | Task 2 |
| `reflex-docs` (plugin, per `chat_ui/AGENTS.md`) | Not engaged. No Reflex API is touched: `theme.py` and `copy.py` are plain module-level constants and import nothing from `reflex`. Confirmed by reading both files in full. | — |
| `reflex-process-management` (plugin) | Not engaged. Nothing to compile, run or reload; validation is `pytest` and `python -c` imports. | — |

---

## Patterns to Follow

### Theme — a named token, in `rem`, with the reason beside it

New tokens go in the `--- Scale ---` block, in the idiom the story's AC names (`RAIL_X`, `ROW_H`, `COLUMN_MAX`): flat uppercase, string literal, trailing comment saying what the number is *for*.

```python
# SOURCE: chat_ui/chat_ui/theme.py:74-83
RADIUS = "3px"
RAIL_X = "1.875rem"  # rail's distance from the transcript's left edge
STAMP_X = RAIL_X  # the register's stamp margin *is* the chat's rail, continued
GLYPH = "9px"
ROW_H = "2.25rem"  # one register row: dense enough to scan a hundred
COLUMN_MAX = "56rem"
MEASURE = "42rem"  # reading measure for prose — roughly 70 characters
PANEL_MAX = "36rem"  # a verdict is a short record, not a banner
```

### The device this story must not re-declare

`SPINE`, `GLYPH` and `RAIL_X` are already assembled into a marked row twice. The rail is the third assembly of the same three tokens, which is why it needs no mark token of its own.

```python
# SOURCE: chat_ui/chat_ui/components/bubbles.py:26-44 — the transcript's rail
        width=theme.GLYPH,
        height=theme.GLYPH if filled else "3px",
...
        rx.box(width="1px", flex="1", background_color=theme.SPINE),
...
        width=theme.RAIL_X,
```

```python
# SOURCE: chat_ui/chat_ui/components/register.py:11-13 — the register's stamp margin
the chat's rail continued rather than reinvented: `theme.STAMP_X is
theme.RAIL_X` (asserted by identity in `tests/test_admin_palette.py`) and the
mark is the same `theme.GLYPH` square.
```

### Copy — banner, constant, and a comment saying *why the string is that string*

```python
# SOURCE: chat_ui/chat_ui/copy.py:104-112
# --- Session fallbacks ---------------------------------------------------
# The two strings a session row falls back to. Both are failures of the
# *input*, not of the reader, so neither apologizes and neither explains the
# mechanism: a blank row in the rail is unclickable and unnameable, and that
# is the whole problem being solved. The rail's own strings are STORY-017's.
SESSION_UNTITLED_TITLE = "Untitled chat"
```

### Copy — the fault panel this rail's fault state is modelled on

PRD-006 solved the identical problem for the register: name the read that failed, say the screen did not move, give the action, and keep the action's verb the same as the control's.

```python
# SOURCE: chat_ui/chat_ui/admin_copy.py:152-159
# --- Fault panel ---------------------------------------------------------
FAULT_TITLE = "The read failed."
# Names what failed, states that the screen did not move, gives the action. The
# stale register is not a wrong one, and which of the two an admin is looking at
# is the fact they need before trusting anything on screen. "Refresh" is the same
# word REFRESH_LABEL carries.
FAULT_MESSAGE_TEMPLATE = (
    "Could not read {read}. Nothing on screen has changed. Refresh to try "
    "again. ({detail})"
)
```

### Copy — the scope line, and why the rail re-declares it rather than importing it

```python
# SOURCE: chat_ui/chat_ui/admin_copy.py:120-122
# {shown} rather than a literal 100: the register formats this from
# `admin_state.REGISTER_ROW_LIMIT`, so the cap is typed once in the codebase and
# a changed limit cannot leave the copy claiming the old one.
REGISTER_SCOPE_TEMPLATE = "{shown} most recent of {total}"
```

```
# SOURCE: chat_ui/chat_ui/admin_copy.py:10 — the boundary rule
This module imports nothing at all.
```

### Tests — append below a banner, never edit above the line

```python
# SOURCE: tests/test_copy.py:535-541
# --------------------------------------------------------------------------
# STORY-012 -- the session rail's two fallback strings.
#
# Appended, never edited above: `tests/test_copy.py` is one of the two suites
# `tests/test_untouched_app.py` pins by census, and every test above this line
# is untouched.
# --------------------------------------------------------------------------
```

```python
# SOURCE: tests/test_copy.py:544-560 — named import at the top, then a voice sweep
def test_session_fallback_copy_names_the_thing_rather_than_the_failure():
    """STORY-012: both fallbacks are user-facing sentences, so both live here.

    Neither may report a parse failure or apologize (frontend-design: "errors
    don't apologize, and they are never vague about what happened")...
    """
    assert SESSION_UNTITLED_TITLE
    assert SESSION_ACTIVITY_UNKNOWN

    for text in (SESSION_UNTITLED_TITLE, SESSION_ACTIVITY_UNKNOWN):
        assert text == text[0].upper() + text[1:] or text == text.lower()
```

```python
# SOURCE: tests/test_copy.py:29-41 — every new constant is imported by name,
# so a rename fails at collection rather than at render
    # STORY-016: the delete flow's two words.
    SESSION_DELETE_CONFIRM_TEMPLATE,
    SESSION_DELETE_CONFIRM_LABEL,
)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/theme.py` | UPDATE | Four rail sizes appended to the `--- Scale ---` block: `SESSION_RAIL_W`, `SESSION_RAIL_ROW_H`, `SESSION_RAIL_GUTTER`, `SESSION_RAIL_COLLAPSE_W`. No colour, no font, no CSS. |
| `chat_ui/chat_ui/copy.py` | UPDATE | Ten rail strings under one new banner at the end of the file. |
| `tests/test_copy.py` | UPDATE | Ten names added to the existing import block; three new tests appended under a STORY-017 banner. |

**Files deliberately NOT changed** — each one would be a scope error, and each is listed so the omission reads as a decision:

| File | Why not |
|------|---------|
| `tests/test_contrast.py` | AC 9. It must pass **unmodified**; a needed edit here means a colour was added. STORY-020 owns any extension. |
| `chat_ui/chat_ui/state.py` | Not in the story's file list. The `str(exc)` finding is recorded in **Risks** and consumed by STORY-018's render choice, not fixed here. |
| `chat_ui/chat_ui/components/*` | STORY-018 and STORY-019. This story renders nothing. |
| `chat_ui/chat_ui/formatting.py` | Its `_YESTERDAY_TEXT`, `_DAYS_AGO_TEMPLATE`, `"just now"` and `_BUCKETS` unit words are user-visible strings outside `copy.py`. That was settled by STORY-012's plan (its Deviations table: splitting one humanizer's vocabulary across two files would make "2m ago" and "yesterday" editable in different places), and re-opening it here would rewrite a done story. |
| `tests/test_admin_palette.py` | Its `test_register_tokens_exist` shape is the right guard for the new tokens, but the rail's version of it is STORY-020's deliverable by that story's own AC list. |

Dependency order: `theme.py` and `copy.py` are independent of each other and of everything else — neither imports the other, and nothing imports the new names yet. `tests/test_copy.py` last.

---

## Tasks

### Task 1: The four rail sizes in `theme.py`

- **File**: `chat_ui/chat_ui/theme.py`
- **Action**: UPDATE
- **Implement**: Append to the end of the `--- Scale ---` block, after `PANEL_MAX` and **before** the `--- Global stylesheet ---` banner. Add nothing to `GLOBAL_CSS`: the rail's rules are STORY-019's, and a selector added here would have no component to select.

```python
# The session rail. Four sizes, no colour: PRD Section 6.1 closes the palette
# for this surface -- "no new inks. The rail is PAPER ground against the
# transcript's CARD, separated by the existing RULE. The active session is
# marked with INK type against HOVER." Every one of those five tokens is
# already declared above, so this block adds none.
#
# The active mark is not declared here either, and that is the point. It is
# RAIL_X / GLYPH / SPINE -- the same three tokens bubbles.py assembles for the
# transcript's rail and register.py for the stamp margin -- appearing a third
# time at a third scale. PRD Section 6.1: "Three surfaces, one structural
# device, each time encoding *which one of these is the one*." A
# SESSION_RAIL_MARK_W beside GLYPH would be a third device wearing the second
# one's clothes.
SESSION_RAIL_W = "15rem"  # ~34 title characters at TEXT_DATA past the RAIL_X inset
SESSION_RAIL_ROW_H = "3rem"  # two lines: the title, and the activity time under it
SESSION_RAIL_GUTTER = "0.75rem"  # the rail's own padding and its gap to the transcript
# Below this the rail collapses (STORY-019). SESSION_RAIL_W + MEASURE is 57rem,
# so 60rem is the width at which the rail stops costing the transcript its
# reading measure rather than an arbitrary device breakpoint.
SESSION_RAIL_COLLAPSE_W = "60rem"
```

- **Mirror**: `chat_ui/chat_ui/theme.py:74-83` — the `RAIL_X` / `ROW_H` / `COLUMN_MAX` group, exactly as AC 1 asks: flat uppercase name, `rem` string, trailing comment naming what the number is for.
- **Naming decision** (record it in the commit body, not only here): `SESSION_RAIL_*`, not `RAIL_*`. `RAIL_X` already means the *transcript's* rail and is reused by this surface for the active mark's inset, so `RAIL_W` would be read as that rail's width at exactly the point the two meet. `SESSION_*` is also the prefix `copy.py` already carries for this feature.
- **Width, justified**: `formatting.TITLE_MAX_LENGTH = 48` is the primary cut, and STORY-012's plan states the CSS ellipsis is the fallback. `15rem` minus the `RAIL_X` (1.875rem) mark column and two `SESSION_RAIL_GUTTER`s leaves ~11.6rem, which is ~34 characters of Archivo at `TEXT_DATA` — under the 48-character cap, so the two cuts compose as STORY-012 declared rather than competing.
- **Constraint (AC 2)**: the diff must contain zero `#RRGGBB` literals. Task 6 runs the grep.
- **Constraint (`tests/test_untouched_app.py:test_no_theme_token_was_retuned_or_removed`)**: that guard parses every module-level uppercase literal and fails if an existing one changes value or disappears. Adding names passes; editing `ROW_H`, `RAIL_X`, `GLYPH`, `SPINE` or any hex does not. Do not "tidy" anything already in the file.
- **Validate**:
  ```bash
  python -c "from chat_ui.chat_ui import theme; print(theme.SESSION_RAIL_W, theme.SESSION_RAIL_ROW_H, theme.SESSION_RAIL_GUTTER, theme.SESSION_RAIL_COLLAPSE_W)"
  python -m pytest tests/test_untouched_app.py -q
  ```

### Task 2: The ten rail strings in `copy.py`

- **File**: `chat_ui/chat_ui/copy.py`
- **Action**: UPDATE
- **Implement**: Append one new banner block at the **end** of the file, below `TRANSCRIPT_NOT_LOADED_NOTICE`. Do not edit the `Session fallbacks`, `Session deletion` or `Transcript persistence` blocks above — those are STORY-012's, STORY-016's and STORY-014/015's, and each already reserves this block by name.

```python
# --- Session rail --------------------------------------------------------
# The rest of the rail's words, and the last of them: the blocks above hold
# the six strings STORY-012, STORY-014, STORY-015 and STORY-016 each needed
# early, and each of those blocks names this one as the owner of the
# remainder. Every constant below has a consumer in Phase 4 -- STORY-018's
# component for eight of them, STORY-019's collapse for the ninth -- because
# a rail string with no consumer is a string that should not have been added.

# The control, and what it produces, share one name (frontend-design: "an
# action keeps the same name through the whole flow"). PRD Section 6.1 fixes
# the words: "The control is **New chat**, and what it produces is a chat."
SESSION_NEW_CHAT_LABEL = "New chat"

# The empty rail. It is an invitation, never a census: PRD Section 6.1, "the
# empty rail reads as an invitation to start one rather than as a report that
# none exist", which is the skill's "an empty screen is an invitation to act"
# applied to this surface. "No chats yet." is the sentence this pair exists to
# refuse. The body says *below* because creation is lazy -- PRD Section 4, "a
# session row is written on the first send, never on page load" -- so the
# first chat is made by sending, not by clicking New chat.
SESSION_RAIL_EMPTY_TITLE = "Start your first chat."
SESSION_RAIL_EMPTY_BODY = "Send a prompt below and this conversation appears here."

# The read that failed, in the shape admin_copy.FAULT_TITLE and
# FAULT_MESSAGE_TEMPLATE already solved for the register: name the read, state
# that the screen did not move, give the action, and spell the action with the
# same word its control carries -- RETRY_LABEL above, unchanged and not
# re-declared.
#
# No {detail} placeholder, deliberately, and this is the one place this block
# departs from the register's template. `ChatState.sessions_error` holds
# `str(exc)` from a ChatSessionError raised as f"{operation} failed: {exc}"
# (app/services/chat_sessions.py:85) -- "list_for failed: ..." is the storage
# layer describing itself, and the skill is explicit: "name things by what
# people control and recognize, never by how the system is built." So
# STORY-018 renders these two constants and treats `sessions_error` as the
# trigger, not as the text.
SESSION_RAIL_FAULT_TITLE = "Could not read your chats."
SESSION_RAIL_FAULT_BODY = "Nothing on screen has changed. Retry to read them again."

# The window, stated the way the register states its own (admin_copy.
# REGISTER_SCOPE_TEMPLATE, identical wording). PRD-006 Risk 4 is the reason a
# cap is never silent: a truncated list beside no scope "invites a wrong
# reading", and a rail that quietly stops at CHAT_SESSION_LIMIT would read as
# a complete list of the user's chats. Re-declared rather than imported:
# admin_copy's own docstring fixes that boundary -- "this module imports
# nothing at all" -- and the two surfaces are separately editable by design.
SESSION_RAIL_SCOPE_TEMPLATE = "{shown} most recent of {total}"

# Rename: the verb on the affordance, and the field's label. The placeholder
# names the thing the reader is naming, not the operation being performed on
# it -- a label labels (frontend-design: "let each element do exactly one
# job"). Empty input is refused silently by `ChatState.rename_session`
# (state.py:411-413, deliberate per its docstring), so there is no
# rename-failed string here to go unused.
SESSION_RENAME_LABEL = "Rename"
SESSION_RENAME_PLACEHOLDER = "Chat name"

# The delete dialog's other door. SESSION_DELETE_CONFIRM_LABEL above is the
# affordance and the confirming button both; this is the one that walks away,
# and it says what it does rather than "Cancel" -- the reader is choosing
# between two outcomes for the chat, not between acting and aborting.
SESSION_DELETE_CANCEL_LABEL = "Keep chat"

# STORY-019's collapse control, declared here for the same reason that story
# declares its breakpoint token here: one file for the words, one for the
# sizes, and a literal in a component is the defect both rules exist to
# prevent. Named for what it shows, which is what the rail is a list of.
SESSION_RAIL_SHOW_LABEL = "Chats"
```

- **Mirror**: `chat_ui/chat_ui/copy.py:104-112` (banner, constant, why-comment) and `chat_ui/chat_ui/admin_copy.py:152-159` (the fault pair's shape).
- **Voice constraints, each traceable to the skill**: sentence case; plain verbs; active voice; no filler; no apology; no mechanism words (`error`, `failed`, `invalid`, `session`, `row`, `database`, `null`) in any string a reader sees. Task 4 asserts these rather than trusting them.
- **Validate**:
  ```bash
  python -c "from chat_ui.chat_ui import copy; print([n for n in dir(copy) if n.startswith('SESSION_') or n.startswith('TRANSCRIPT_')])"
  ```

### Task 3: Import the ten names in `tests/test_copy.py`

- **File**: `tests/test_copy.py`
- **Action**: UPDATE
- **Implement**: Extend the existing `from chat_ui.chat_ui.copy import (...)` block at `tests/test_copy.py:7-41`, appending below the STORY-016 pair with a comment in the same voice. Names only — no test bodies in this task, and nothing above the block is touched.

```python
    # STORY-017: the rail's remaining strings, imported by name like every
    # constant above, so a rename fails at collection rather than at render.
    SESSION_NEW_CHAT_LABEL,
    SESSION_RAIL_EMPTY_TITLE,
    SESSION_RAIL_EMPTY_BODY,
    SESSION_RAIL_FAULT_TITLE,
    SESSION_RAIL_FAULT_BODY,
    SESSION_RAIL_SCOPE_TEMPLATE,
    SESSION_RENAME_LABEL,
    SESSION_RENAME_PLACEHOLDER,
    SESSION_DELETE_CANCEL_LABEL,
    SESSION_RAIL_SHOW_LABEL,
)
```

- **Mirror**: `tests/test_copy.py:29-41`.
- **Constraint**: this is the only edit above the append line, and it is an addition inside an import list — it removes no `def test_`, so `test_no_assertion_was_removed_from_the_two_extendable_suites` still passes. Do **not** extend `test_copy_constants_exist_and_not_empty` at `:148`; that function has been left alone since STORY-007 and every later story appended its own named test instead.
- **Validate**: `python -m pytest tests/test_copy.py -q` (collects; the new names must import).

### Task 4: The three new tests in `tests/test_copy.py`

- **File**: `tests/test_copy.py`
- **Action**: UPDATE
- **Implement**: Append at the end of the file, under a banner in the established form. Three tests, one per AC that has an assertable claim: existence (AC 8), the empty-rail invitation (AC 6), the read failure (AC 7).

```python
# --------------------------------------------------------------------------
# STORY-017 -- the rail's remaining strings.
#
# Appended, never edited above: `tests/test_copy.py` is one of the two suites
# `tests/test_untouched_app.py` pins by census, and every test above this line
# is untouched.
# --------------------------------------------------------------------------


def test_every_rail_string_exists_and_is_not_empty():
    """AC 8: the whole rail vocabulary, asserted by name.

    Existence is the cheap half; the point of listing them together is that
    STORY-018 can be written against this tuple and find nothing missing. The
    six constants STORY-012, STORY-014, STORY-015 and STORY-016 contributed
    are included, because "every rail string" is the claim -- not "every
    string this story happened to add".
    """
    rail_strings = (
        SESSION_NEW_CHAT_LABEL,
        SESSION_RAIL_EMPTY_TITLE,
        SESSION_RAIL_EMPTY_BODY,
        SESSION_RAIL_FAULT_TITLE,
        SESSION_RAIL_FAULT_BODY,
        SESSION_RAIL_SCOPE_TEMPLATE,
        SESSION_RENAME_LABEL,
        SESSION_RENAME_PLACEHOLDER,
        SESSION_DELETE_CANCEL_LABEL,
        SESSION_RAIL_SHOW_LABEL,
        # Contributed early by the stories that needed them first.
        SESSION_UNTITLED_TITLE,
        SESSION_ACTIVITY_UNKNOWN,
        SESSION_DELETE_CONFIRM_TEMPLATE,
        SESSION_DELETE_CONFIRM_LABEL,
        TRANSCRIPT_NOT_SAVED_NOTICE,
        SESSION_ORDER_STALE_NOTICE,
        TRANSCRIPT_NOT_LOADED_NOTICE,
    )
    for text in rail_strings:
        assert isinstance(text, str)
        assert text.strip(), f"empty rail string: {text!r}"

    # PRD Section 6.1 fixes these two words, and the control, the action and
    # what it produces all carry them (frontend-design: "an action keeps the
    # same name through the whole flow").
    assert SESSION_NEW_CHAT_LABEL == "New chat"
    # The scope line states both halves or it is not a scope line (PRD-006
    # Risk 4), and it is the register's own wording rather than a second
    # phrasing of one idea.
    assert "{shown}" in SESSION_RAIL_SCOPE_TEMPLATE
    assert "{total}" in SESSION_RAIL_SCOPE_TEMPLATE
    assert SESSION_RAIL_SCOPE_TEMPLATE == admin_copy.REGISTER_SCOPE_TEMPLATE


def test_the_empty_rail_invites_a_chat_rather_than_reporting_none():
    """AC 6, and the skill verbatim: "an empty screen is an invitation to act".

    PRD Section 6.1: "the empty rail reads as an invitation to start one
    rather than as a report that none exist." An invitation has a verb in it
    and an absence in it has none, so the title is checked for both -- a
    census sentence ("No chats yet", "You have no chats") passes a
    non-emptiness check and fails this one, which is the whole reason this
    test exists beside the one above.
    """
    assert SESSION_RAIL_EMPTY_TITLE
    assert SESSION_RAIL_EMPTY_BODY

    lowered = f"{SESSION_RAIL_EMPTY_TITLE} {SESSION_RAIL_EMPTY_BODY}".lower()
    for absence in ("no chats", "nothing here", "empty", "none", "0 chats"):
        assert absence not in lowered, f"the empty rail reports absence: {absence!r}"
    # The invitation names the act. Both verbs are the ones the surface
    # actually offers: New chat above the rail, and the composer below it.
    assert "start" in lowered or "send" in lowered

    # Sentence case, not Title Case, and no mechanism words: the copy module's
    # register throughout (frontend-design: "plain verbs, sentence case, no
    # filler").
    for text in (SESSION_RAIL_EMPTY_TITLE, SESSION_RAIL_EMPTY_BODY):
        assert text == text[0].upper() + text[1:]
        assert not text.isupper()
        for mechanism in ("session", "row", "record", "database", "null"):
            assert mechanism not in text.lower(), f"{text!r} names the mechanism"


def test_the_rail_read_failure_names_the_read_and_offers_the_retry():
    """AC 7, and the skill verbatim: "errors don't apologize, and they are
    never vague about what happened".

    Three claims, and the third is the one that would rot silently. First, the
    line names what failed -- the reader's chats, not "data". Second, it
    offers the action, spelled with the same word its control carries, so
    RETRY_LABEL is asserted *into* the sentence rather than beside it (the
    shape admin_copy's REFRESH_LABEL/FAULT_MESSAGE_TEMPLATE pair uses). Third,
    it states that the screen did not move: STORY-015 established that a
    failed read leaves the transcript alone, and a fault line that omits that
    leaves the reader unsure which chat the bubbles belong to.
    """
    assert "chats" in SESSION_RAIL_FAULT_TITLE.lower()
    assert RETRY_LABEL.lower() in SESSION_RAIL_FAULT_BODY.lower()
    assert "nothing on screen has changed" in SESSION_RAIL_FAULT_BODY.lower()

    for text in (SESSION_RAIL_FAULT_TITLE, SESSION_RAIL_FAULT_BODY):
        lowered = text.lower()
        # No apology, in any of its usual disguises.
        for apology in ("sorry", "apolog", "unfortunately", "oops"):
            assert apology not in lowered, f"{text!r} apologizes"
        # No vagueness, and no mechanism. "Something went wrong" is the
        # sentence this loop exists to refuse.
        for vague in ("something went wrong", "an error", "try again later"):
            assert vague not in lowered, f"{text!r} is vague: {vague!r}"
        for mechanism in ("session", "exception", "traceback", "null", "500"):
            assert mechanism not in lowered, f"{text!r} names the mechanism"
```

- **Mirror**: `tests/test_copy.py:535-582` — banner, then a named test per claim, with the PRD section or the skill quoted in the docstring.
- **Note on the `admin_copy` reference in test 1**: `tests/test_copy.py:47` already does `from chat_ui.chat_ui import admin_copy`, so the equality assertion needs no new import.
- **Note on `RETRY_LABEL`**: already imported at `tests/test_copy.py:7-41` and already asserted equal to `"Retry"` at `:151`.
- **Validate**: `python -m pytest tests/test_copy.py -q`

### Task 5: Prove the guards are real by breaking them once

- **File**: none (working-tree experiment, reverted)
- **Action**: verify
- **Implement**: STORY-020's rule — *"a guard that has never been red is a guard nobody has verified"* — applied to this story's own three tests, at a cost of about two minutes. In order, each reverted before the next:
  1. Set `SESSION_RAIL_EMPTY_TITLE = "No chats yet."` → `test_the_empty_rail_invites_a_chat_rather_than_reporting_none` must fail on the `"no chats"` assertion. Revert.
  2. Set `SESSION_RAIL_FAULT_BODY = "Sorry, something went wrong. Try again later."` → `test_the_rail_read_failure_names_the_read_and_offers_the_retry` must fail on `"sorry"` **and** on the retry assertion. Revert.
  3. Set `SESSION_RAIL_SHOW_LABEL = ""` → `test_every_rail_string_exists_and_is_not_empty` must fail on the strip check. Revert.
- **Validate**: `git diff --quiet chat_ui/chat_ui/copy.py` is **not** expected to be clean here (the story's own additions are staged in the working tree), so revert each experiment by restoring the constant's intended value and re-running `python -m pytest tests/test_copy.py -q` to green before moving on. Record the three red runs in the story report.

### Task 6: The no-new-ink proof

- **File**: none (inspection)
- **Action**: verify
- **Implement**: AC 2 and AC 9 are claims about the diff, so they are checked against the diff rather than asserted from memory. Three checks:
  ```bash
  # 1. Not one hex literal in the theme diff.
  git diff -U0 -- chat_ui/chat_ui/theme.py | grep '^+' | grep -c '#[0-9a-fA-F]\{6\}'   # must print 0

  # 2. No TINT_* and no verdict ink named anywhere in either changed module's diff.
  git diff -- chat_ui/chat_ui/theme.py chat_ui/chat_ui/copy.py | grep '^+' \
    | grep -E 'TINT_|INK_CLEAR|INK_HELD|INK_DENIED|INK_FORBIDDEN|INK_UPSTREAM|INK_FAULT|INK_SELF'
  # Only the Task 1 comment block may match, and only as prose. Any assignment is a defect.

  # 3. test_contrast.py is byte-identical to HEAD.
  git diff --quiet -- tests/test_contrast.py && echo "contrast suite unmodified"
  ```
- **Why this is a task and not a checkbox**: AC 9 says it outright — *"if one was, this story added a colour it was told not to add."* The failure mode is a plausible-looking `SESSION_RAIL_ACTIVE_BG` added late to make a row "read better", which no other test in the tree would catch until STORY-020 exists.
- **Validate**: all three checks pass; check 3 is also re-run as part of the final suite.

---

## End-to-End Tests

Nothing renders in this story, so "end to end" means the seams with the code on either side of it.

- [ ] `python -m pytest tests/test_copy.py -q` → green, including the three new tests.
- [ ] `python -m pytest tests/test_contrast.py -q` → green **and** unmodified (`git diff --quiet -- tests/test_contrast.py`). This is AC 9 and it is the whole proof for AC 2.
- [ ] `python -m pytest tests/test_untouched_app.py -q` → green. Two guards matter here: `test_no_theme_token_was_retuned_or_removed` (proves no existing token was retuned or dropped by the append) and `test_no_assertion_was_removed_from_the_two_extendable_suites` (proves `test_copy.py` was appended to, not edited).
- [ ] `python -m pytest tests/test_admin_palette.py tests/test_render_invariants.py -q` → green. Neither should notice this story: the new tokens are `rem` sizes, no admin module reads them, and nothing was added to `GLOBAL_CSS`. If either goes red, something was added to the stylesheet that should not have been.
- [ ] **The STORY-018 seam** — every name that story will import resolves, from a cold interpreter:
      ```bash
      python -c "from chat_ui.chat_ui import theme, copy; \
      print(theme.SESSION_RAIL_W, theme.SESSION_RAIL_ROW_H, theme.SESSION_RAIL_GUTTER, theme.SESSION_RAIL_COLLAPSE_W); \
      print(copy.SESSION_NEW_CHAT_LABEL, '|', copy.SESSION_RAIL_EMPTY_TITLE, '|', copy.SESSION_RAIL_FAULT_TITLE, '|', copy.SESSION_RENAME_LABEL, '|', copy.SESSION_DELETE_CANCEL_LABEL, '|', copy.SESSION_RAIL_SHOW_LABEL); \
      print(copy.SESSION_RAIL_SCOPE_TEMPLATE.format(shown=20, total=180))"
      ```
- [ ] **The device seam** — the active mark's three tokens still resolve and are still the shared ones, not copies:
      `python -c "from chat_ui.chat_ui import theme; print(theme.RAIL_X, theme.GLYPH, theme.SPINE); assert theme.STAMP_X is theme.RAIL_X"`
- [ ] **No circular import and no broken surface**: `python -c "import chat_ui.chat_ui.state; print('ok')"` and `python -m pytest tests/test_chat_components_import.py -q`.
- [ ] Full suite: `python -m pytest -q`.

**Note before running any suite that touches the database** (the full run in particular): those need the local libSQL dev server from `tests/conftest.py`'s decision record. If the run produces mass fixture errors, restart the container rather than bisecting the code — the dev server degrades under repeated suites. Everything this story changes is pure Python and needs none of it, so the three targeted runs above are the fast loop.

---

## Validation

```bash
# The story's own suite
python -m pytest tests/test_copy.py -q

# AC 2 and AC 9: the contrast suite passes AND is untouched
python -m pytest tests/test_contrast.py -q
git diff --quiet -- tests/test_contrast.py && echo "contrast suite unmodified"

# No hex added to theme.py
git diff -U0 -- chat_ui/chat_ui/theme.py | grep '^+' | grep -c '#[0-9a-fA-F]\{6\}'

# The guards that can be broken from a distance
python -m pytest tests/test_untouched_app.py tests/test_admin_palette.py tests/test_render_invariants.py -q

# The chat still imports
python -c "import chat_ui.chat_ui.state; print('ok')"

# Full suite before the commit
python -m pytest -q
```

---

## Deviations

| PRD / story says | Plan does | Why |
|---|---|---|
| AC 1: tokens "in the style of the existing `RAIL_X`, `ROW_H`, `COLUMN_MAX` group" | Names them `SESSION_RAIL_W` / `SESSION_RAIL_ROW_H` / `SESSION_RAIL_GUTTER`, not `RAIL_W` / `RAIL_ROW_H` / `RAIL_GUTTER` | Same idiom, longer name. `RAIL_X` already means the *transcript's* rail and is reused by this surface for the active mark's inset, so `RAIL_W` would be read as that rail's width at exactly the point the two meet. `SESSION_*` is the prefix `copy.py` already carries for this feature. |
| Story AC 1 names three tokens (width, row height, gutter) | Adds a fourth, `SESSION_RAIL_COLLAPSE_W` | STORY-019's own Technical Notes ask for it here: *"`theme.py` if the breakpoint needs a token — and it does, per STORY-017's single-file rule."* Declaring it in the story that owns tokens is what that sentence instructs; leaving it would put a literal breakpoint in STORY-019's diff, which is the defect this story exists to prevent. |
| Story AC 4 lists seven rail strings | Adds ten, three beyond the list: `SESSION_RAIL_SCOPE_TEMPLATE`, `SESSION_DELETE_CANCEL_LABEL`, `SESSION_RAIL_SHOW_LABEL` | AC 4's governing clause is *"every rail string"*, and each of the three has a named Phase 4 consumer: the scope line by STORY-018 AC 11 (the cap "stated against the true total... in the manner PRD-006's register states '100 most recent of 3,180'"), the cancel label by STORY-018's confirmation dialog (which needs a second door), and the collapse label by STORY-019's *"control to bring the rail back"*. Without them those stories must each invent a literal. |
| — | `SESSION_RAIL_SHOW_LABEL` is the one string whose consumer's shape is not yet fixed | Flagged rather than hidden: STORY-019 owns the collapse and may want a different control shape. If so it **replaces** this constant rather than adding a second one, and the replacement is a copy edit, not a component literal. |
| PRD Section 6.1 fixes the rail's colours | The theme diff declares no colour at all, not even an alias | The five tokens the rail needs — `PAPER`, `CARD`, `RULE`, `INK`, `HOVER` — plus the mark's `SPINE`, `GLYPH`, `RAIL_X` all already exist. An alias (`SESSION_RAIL_BG = PAPER`) would satisfy the letter of "declared in theme.py" while adding a second name for one value, which is the drift Risk 6 describes arriving "one reasonable component at a time". |
| Story: "the read-failure line... offers the retry" | Reuses the existing `RETRY_LABEL`; declares no `SESSION_RAIL_RETRY_LABEL` | One verb across the flow (frontend-design; and `admin_copy.py:140`'s comment makes the identical choice: *"the fault panel's retry reuses REFRESH_LABEL rather than declaring a second name for the same button"*). The fault body spells "Retry" so the sentence and the control agree, and Task 4 asserts that agreement rather than assuming it. |
| The register's fault template carries `({detail})` | The rail's fault copy carries no `{detail}` | The only detail available is `str(ChatSessionError)`, raised as `f"{operation} failed: {exc}"` (`app/services/chat_sessions.py:85`). Surfacing "list_for failed: ..." is exactly *"how the system is built"*. STORY-018 renders the constants and uses `sessions_error` as the trigger. Recorded in **Risks** so STORY-018 does not re-derive it. |
| — | Three strings were considered and cut | Chanel's rule, applied: a rail heading above the list (the rail's contents are self-evident and PRD Section 6.1's wireframe shows no heading), a rename Save/Cancel pair (an inline field commits on Enter or blur; a Save button is a third control on a row that has two), and a rename-failed notice (`ChatState.rename_session` refuses an empty title *silently* and deliberately, `state.py:411-413`, so the string would have no consumer). |
| — | `tests/test_copy.py:148` `test_copy_constants_exist_and_not_empty` is not extended | Every story since STORY-007 has appended a named test instead, and the census guard makes append-only the safe shape. Extending the old function would work but would break a four-story convention for no gain. |

---

## Risks

| Risk | Mitigation |
|---|---|
| A colour gets added late — an "active row background", a "rail ground" — and the story silently fails the one thing it exists to enforce. | Task 6 greps the diff for hex literals and for `TINT_*`/verdict-ink names, and asserts `tests/test_contrast.py` is byte-identical to HEAD. AC 9 is written as the tell: a contrast edit *is* the defect, not a chore. |
| `sessions_error` holds `str(exc)` at four sites (`state.py:220`, `:425`, `:496`, `:750`) and `ChatSessionError` is `f"{operation} failed: {exc}"` — so if STORY-018 renders that var's text, the rail shows "list_for failed: ..." to an employee and this story's fault copy is never seen. | Written into the `copy.py` comment beside the fault pair, so the instruction sits where STORY-018 will read it: render the constants, treat `sessions_error` as a trigger. Carried into STORY-018's plan as a required render decision, and into STORY-020's scope as an assertion worth making (no rail output contains "failed:"). Not fixed in `state.py` here — that file is not this story's, and changing it would put an untested edit in a copy-only diff. |
| The rail's retry has nothing to call: no handler in `ChatState` re-reads the session list (the read lives inline in `login()`, `state.py:213-220`), so `SESSION_RAIL_FAULT_BODY` could promise an action the surface cannot perform. | Recorded here for STORY-018, which needs a `reload_sessions()` handler — or must reuse the read path — before its fault state is honest. This story's copy is correct as written; the gap is in the story that renders it, and naming it now is cheaper than discovering it at render. |
| `SESSION_RAIL_W` and `formatting.TITLE_MAX_LENGTH` become two opinions about one cut, and a title is truncated twice ("Q3 vendor sp…" in a rail that had room). | The width is derived from the cap rather than picked: 15rem less `RAIL_X` and two gutters is ~34 characters at `TEXT_DATA`, under the 48-character cap, which is the arrangement STORY-012's plan already declared ("`TITLE_MAX_LENGTH` is the primary cut and the CSS is the fallback at a narrow viewport"). The reasoning is in the token's comment so STORY-018 does not re-litigate it. |
| A new token is added to `theme.py` by editing a nearby line, and `test_no_theme_token_was_retuned_or_removed` fails — or worse, passes because the edit was to a comment. | Task 1 is explicit: append only, touch no existing assignment, add nothing to `GLOBAL_CSS`. `tests/test_untouched_app.py` runs in the story's own validation loop, not only at the end. |
| A string is added "for completeness" with no consumer, and Phase 4 ends carrying dead vocabulary — the exact failure the story names. | Every constant in Task 2 has its consumer named in its own comment (STORY-018 for eight, STORY-019 for one, both for `SESSION_NEW_CHAT_LABEL`). The three strings that failed that test are listed in **Deviations** with the reason, so a later reader can see they were considered rather than missed. |
| The three new tests pass on day one and would pass on any string, making them decoration. | Task 5 breaks each one and records the red run in the report, per STORY-020's rule: *"a guard that has never been red is a guard nobody has verified."* |

---

## Acceptance Criteria

(Copied from story `STORY-017`)

- [ ] Given `chat_ui/chat_ui/theme.py`, when it is read, then it declares the rail's width, row height and gutter as named tokens, in the style of the existing `RAIL_X`, `ROW_H`, `COLUMN_MAX` group.
- [ ] Given the diff, when it is inspected, then **no new colour value is added**.
- [ ] Given the new tokens, when they are read, then the active mark reuses `SPINE`, `GLYPH` and `RAIL_X` rather than declaring parallel values.
- [ ] Given `chat_ui/chat_ui/copy.py`, when it is read, then it carries every rail string: the **New chat** label, the empty-rail invitation, the read-failure line, the not-saved notice from STORY-014, the delete confirmation, the rename affordance and the fallback title from STORY-012.
- [ ] Given the delete confirmation string, when it is read, then it names the chat and states that the record of what was checked is kept — in the user's words, not in schema terms.
- [ ] Given the empty-rail string, when it is read, then it invites the reader to start a chat rather than reporting that none exist.
- [ ] Given the read-failure string, when it is read, then it names what failed and offers the retry, and it does not apologize.
- [ ] Given `tests/test_copy.py`, when it runs, then it asserts every new constant exists and is non-empty, following the file's existing pattern.
- [ ] Given `tests/test_contrast.py`, when it runs, then it passes unmodified.
- [ ] All tasks completed
- [ ] Frontend lint passes (n/a — no JS in this repo; `python -m pytest -q` is the equivalent gate)
- [ ] Backend server starts without error (`python -c "import chat_ui.chat_ui.state"` clean)
- [ ] Follows existing patterns
