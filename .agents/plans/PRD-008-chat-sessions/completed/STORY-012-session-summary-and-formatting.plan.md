---
story: STORY-012
prd: PRD-008
slug: session-summary-and-formatting
title: "ChatSessionSummary plus auto-title derivation and relative activity time in formatting.py"
type: NEW_CAPABILITY
complexity: LOW
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-04
---

# Plan: ChatSessionSummary plus auto-title derivation and relative activity time in formatting.py

## Summary

Three pure-Python additions and two copy constants, all of them backend-side, none of them rendered. `models.py` gains `ChatSessionSummary` — `session_id`, `title`, `activity_info`, and deliberately nothing else, because PRD Section 6.1 fixes the rail's metadata at "a relative activity time and nothing else". `formatting.py` gains `derive_title(prompt)`, which truncates the first prompt at a word boundary, and `format_activity(updated_at, now=None)`, which turns the session's stored `updated_at` into "2m ago" / "yesterday" / "3 days ago". `copy.py` gains the two fallback strings those functions return when their input has nothing usable in it.

The interesting part of a story this small is the four edge cases the ACs enumerate, and they are all in `derive_title`: a prompt under the cap must come back untouched with no ellipsis, a single unbroken token longer than the cap must truncate rather than vanish, and a whitespace-only prompt must produce a nameable row rather than a blank one. The naive one-liner — `prompt[:cap].rsplit(" ", 1)[0]` — gets two of those wrong, so the implementation below is written against them and `tests/test_formatting.py` pins each one.

`format_activity` is a *third* spelling of a span already spelled twice, and the rule from `formatting.py`'s own comment applies: "One threshold table, two spellings... they must never drift into two different ideas of when an hour becomes a day." So it composes `humanize_compact` for everything under a day and adds the day arm on top, rather than opening a second bucket table. `_humanize` and `humanize_compact` are not touched — `tests/test_untouched_app.py:test_the_chat_humanizer_still_renders_what_it_did` compares `_humanize` span by span against the PRD-006 baseline and would fail if they were.

## User Story

As an employee
I want my chats named by what they are about
So that a list of eleven conversations is scannable rather than eleven timestamps.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-012-session-summary-and-formatting.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md` — Section 4 (Chat state), Section 5 (story 3), Section 6.1 (metadata in the rail), Section 7, Section 12 Phase 3

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | LOW |
| Systems Affected | `chat_ui/chat_ui/models.py`, `chat_ui/chat_ui/formatting.py`, `chat_ui/chat_ui/copy.py`, `tests/test_formatting.py` (new), `tests/test_copy.py` |
| Story | STORY-012 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |
| Depends on | None |
| Blocks | STORY-013, STORY-018 |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `reflex-docs` (plugin, named in story frontmatter) | `chat_ui/AGENTS.md`, verbatim: "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory." Governs the base class for `ChatSessionSummary`. | Task 2 |
| `.agents/skills/frontend-design` | Listed, read in full. Scoped to "distinctive, intentional visual design when building new UI" — palette, typography, layout, motion. This story renders nothing. The one rule with a subject here is its writing section ("plain verbs, sentence case, no filler"), applied to the two fallback strings in Task 1. | Task 1 |

`.agents/skills/` was listed and holds exactly one skill. Its rules for the rail's visual design land in STORY-017 and STORY-018, as the story's own Technical Notes say; this plan confirms that independently rather than inheriting it.

**`reflex-docs` outcome, and a deviation from the PRD.** PRD Section 8 says *"`rx.Base` for `ChatSessionSummary`"*. That is wrong against the pinned dependency, and it was already found to be wrong once — `admin_models.py`'s module docstring records it. Verified again here against the installed tree rather than recalled:

```
$ python -c "import reflex; ...; reflex.Base"
reflex 0.9.6.post1  pydantic 2.13.5
rx.Base MISSING: No reflex attribute Base
```

`rx.Base` was the pydantic-v1 shim; Reflex 0.9.x is pydantic-v2 based and no longer exports it. So `ChatSessionSummary` subclasses `pydantic.BaseModel`, which is what `ChatMessage` and both admin models already do and what the story instructs ("follow whatever `models.py`'s `ChatMessage` already does rather than introducing a second convention"). This is recorded under **Deviations** below so the PRD's line is not silently ignored.

---

## Patterns to Follow

### Naming — a model of plain, already-formatted fields, with the rule in a comment

`ChatSessionSummary` sits directly under `ChatMessage` in the same module, in the same shape: `pydantic.BaseModel`, every field defaulted, every derived value a plain `str` computed in the backend. The comment above `activity_info` reuses `ChatMessage`'s existing wording rather than inventing a second phrasing of the same rule.

```python
# SOURCE: chat_ui/chat_ui/models.py:1-21
import pydantic


class ChatMessage(pydantic.BaseModel):
    """Typed chat message model carrying kind discriminator and metadata."""

    kind: str
    content: str
    ...
    # Humanized duplicate copy, precomputed in the backend: component
    # functions only ever see Vars, so datetime math cannot run at render.
    duplicate_relative_info: str = ""
    duplicate_release_info: str = ""
```

```python
# SOURCE: chat_ui/chat_ui/admin_models.py:29-46 -- the same rule, stated for rows
class AuditRow(pydantic.BaseModel):
    """One register row: every field the audit table and its disclosure render."""

    audit_id: int = 0
    timestamp_absolute: str = ""
    # Pre-formatted in admin_formatting.py, never at render: the relative time
    # needs datetime math, and the three below need a placeholder when their
    # source column is NULL -- neither can run against a Var.
    timestamp_relative: str = ""
```

### Truncation — a length constant and an ellipsis constant, beside the function

`derive_title`'s cap is not a literal in the body. `admin_formatting.py` already set this shape for the register's device column, including the "the full value is kept elsewhere" note, and `derive_title` is the same operation on a different column.

```python
# SOURCE: chat_ui/chat_ui/admin_formatting.py:56-59, 172-178
DEVICE_TRUNCATE_LENGTH = 32
DEVICE_ELLIPSIS = "…"

def _truncate_device(device: Optional[str]) -> tuple[str, str]:
    """Returns (in-row device string, full device string)."""
    if not device:
        return VALUE_ABSENT, VALUE_ABSENT
    if len(device) <= DEVICE_TRUNCATE_LENGTH:
        return device, device
    return device[:DEVICE_TRUNCATE_LENGTH] + DEVICE_ELLIPSIS, device
```

### Error handling — degrade to a copy constant, never raise into a render

The AC names this precedent by name. A bad timestamp costs the relative reading, not the row; the fallback is a constant from `copy.py`, and the `except` is broad because `fromisoformat` raises more than one type across the inputs a stored column can hold.

```python
# SOURCE: chat_ui/chat_ui/formatting.py:56-79
def format_duplicate_info(first_query_at: str) -> tuple[str, str]:
    """...Falls back to a plain notice when first_query_at is missing or unparseable,
    so a bad timestamp degrades the card instead of dropping it."""
    if not first_query_at:
        return DUPLICATE_FALLBACK_TEXT, ""
    try:
        dt = datetime.fromisoformat(first_query_at.replace("Z", "+00:00"))
        seconds = int((datetime.now(timezone.utc) - dt).total_seconds())
        ...
    except Exception:
        return DUPLICATE_UNPARSEABLE_TEMPLATE.format(absolute=first_query_at), ""
```

```python
# SOURCE: chat_ui/chat_ui/admin_formatting.py:158-170 -- the same degrade, with an injectable clock
def _format_timestamps(raw: Optional[str], now: datetime) -> tuple[str, str]:
    """Degrades the way `formatting.py:format_duplicate_info` does..."""
    if not raw:
        return VALUE_ABSENT, VALUE_ABSENT
    try:
        recorded = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        seconds = int((now - recorded).total_seconds())
        return humanize_compact(seconds), raw
    except Exception:
        return VALUE_ABSENT, raw
```

### Copy — grouped under a section banner, with the reasoning in the comment

```python
# SOURCE: chat_ui/chat_ui/copy.py:79-89
# --- Recovery actions ----------------------------------------------------
RETRY_LABEL = "Retry"
# Risk 4: resending the same text is blocked again, so the copy names the one
# thing that makes the action work.
DUPLICATE_CHANGE_NOTICE = "Change the wording before you send it again."
DUPLICATE_RELATIVE_TIME_TEMPLATE = "Already sent {relative} ({absolute})"
DUPLICATE_FALLBACK_TEXT = "Already submitted recently."
DUPLICATE_UNPARSEABLE_TEMPLATE = "Already sent at {absolute}"
```

### Tests — the derived value is pinned where it is derived, boundary by boundary

`format_duplicate_info` and `_humanize` are tested in `tests/test_copy.py` today, parametrized across every unit boundary with singular and plural pinned separately. The new formatting tests take the same shape in their own file.

```python
# SOURCE: tests/test_copy.py:189-210
@pytest.mark.parametrize(
    "seconds,expected",
    [
        (-5, "just now"),
        (0, "just now"),
        (1, "1 second ago"),
        (60, "1 minute ago"),
        (86400, "1 day ago"),
        (172800, "2 days ago"),
    ],
)
def test_relative_time_reads_naturally_at_every_boundary(seconds, expected):
    """A duplicate card is the first thing many users see; "1 seconds ago"
    undermines it. Every unit boundary is pinned, singular and plural."""
    from chat_ui.chat_ui.formatting import _humanize

    assert _humanize(seconds) == expected
```

```python
# SOURCE: tests/test_copy.py:1-6 -- the sys.path preamble every suite here opens with
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/copy.py` | UPDATE | Two fallback constants: the untitled-session title and the unreadable-activity string. Section banner appended at the end of the file. |
| `chat_ui/chat_ui/models.py` | UPDATE | `ChatSessionSummary` — `session_id`, `title`, `activity_info`. |
| `chat_ui/chat_ui/formatting.py` | UPDATE | `TITLE_MAX_LENGTH`, `TITLE_ELLIPSIS`, `derive_title(prompt)`, `format_activity(updated_at, now=None)`. |
| `tests/test_formatting.py` | CREATE | Both functions, all four `derive_title` edge cases, every `format_activity` bucket boundary and its fallback, plus the model's field list. |
| `tests/test_copy.py` | UPDATE | The two new constants asserted by name, appended below the existing tests. |

Dependency order: copy → models → formatting → tests. `formatting.py` imports from `copy.py`, so the constants land first.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: The two fallback strings in `copy.py`

- **File**: `chat_ui/chat_ui/copy.py`
- **Action**: UPDATE
- **Implement**: Append a new section at the end of the file. Only these two constants — the rail's own strings (row labels, "New chat", the delete confirmation, the empty-rail invitation) belong to STORY-017 and must not be pre-empted here.

```python
# --- Session fallbacks ---------------------------------------------------
# The two strings a session row falls back to. Both are failures of the
# *input*, not of the reader, so neither apologizes and neither explains the
# mechanism: a blank row in the rail is unclickable and unnameable, and that
# is the whole problem being solved. The rail's own strings are STORY-017's.
SESSION_UNTITLED_TITLE = "Untitled chat"
# The counterpart of DUPLICATE_UNPARSEABLE_TEMPLATE above: a timestamp that
# will not parse costs the relative reading, not the row.
SESSION_ACTIVITY_UNKNOWN = "no recent activity"
```

- **Mirror**: `chat_ui/chat_ui/copy.py:79-89` — section banner, then the constant, then the comment saying *why* the string is worded that way.
- **Constraint (frontend-design, writing section)**: sentence case, plain verbs, no filler, no apology. "Untitled chat" names the thing by what the user recognizes; "no recent activity" states the fact rather than reporting a parse failure.
- **Validate**: `python -c "from chat_ui.chat_ui.copy import SESSION_UNTITLED_TITLE, SESSION_ACTIVITY_UNKNOWN; print(SESSION_UNTITLED_TITLE, '/', SESSION_ACTIVITY_UNKNOWN)"`

### Task 2: `ChatSessionSummary` in `models.py`

- **File**: `chat_ui/chat_ui/models.py`
- **Action**: UPDATE
- **Implement**: Append below `ChatMessage`. Three fields, all defaulted, all `str`.

```python
class ChatSessionSummary(pydantic.BaseModel):
    """One row of the session rail: what it is called, and when it last moved.

    Three fields, and the absence of the rest is the design. PRD-008 Section
    6.1, verbatim: "Every session row carries a relative activity time and
    nothing else -- no message count, no model, no verdict summary... a figure
    belongs in the rail only if the reader needs it to choose a row, and they
    do not." Adding one here removes that decision rather than improving the
    model, the way a preview field would on `admin_models.AuditRow`.

    `pydantic.BaseModel`, not `rx.Base`: `rx.Base` does not exist in the pinned
    `reflex==0.9.6.post1` (it was the pydantic-v1 shim, and Reflex 0.9.x is
    pydantic-v2 based). `ChatMessage` above and both models in
    `admin_models.py` subclass `pydantic.BaseModel` for the same reason and
    render fine under `rx.foreach`.
    """

    session_id: str = ""
    title: str = ""
    # Humanized activity time, precomputed in the backend: component functions
    # only ever see Vars, so datetime math cannot run at render. A field rather
    # than a computed property for PRD-006's derived-once row model --
    # components read fields; they do not compute. Never stored: a persisted
    # "2m ago" is wrong the moment it is read back, so `format_activity`
    # recomputes it on every load.
    activity_info: str = ""
```

- **Mirror**: `chat_ui/chat_ui/models.py:1-21` (base class, defaults, comment wording) and `chat_ui/chat_ui/admin_models.py:9-19` (the "this omission is the mitigation" docstring).
- **Skill**: `reflex-docs` — the base-class choice is the Reflex API decision in this story, resolved above under **Skills In Use** and re-verified against the installed `reflex==0.9.6.post1` rather than recalled.
- **Validate**: `python -c "from chat_ui.chat_ui.models import ChatSessionSummary as S; print(sorted(S.model_fields)); print(S())"` → exactly `['activity_info', 'session_id', 'title']`

### Task 3: `derive_title` in `formatting.py`

- **File**: `chat_ui/chat_ui/formatting.py`
- **Action**: UPDATE
- **Implement**: Extend the `from .copy import (...)` block with the two new constants, then append the cap constants and the function. Do **not** touch `_BUCKETS`, `_bucket`, `_humanize`, `humanize_compact` or `format_duplicate_info`.

```python
# The auto-title cap. A rail row is a label on a shelf, not a sentence, and a
# title long enough to need two lines defeats the scan the rail exists for.
# 48 leaves the CSS ellipsis in STORY-018 as a second line of defence at a
# narrow viewport rather than as the only one -- the truncation a user reads
# should be the one Python decided, which is the same argument
# `admin_formatting.DEVICE_TRUNCATE_LENGTH` makes for the device column.
TITLE_MAX_LENGTH = 48
TITLE_ELLIPSIS = "…"


def derive_title(prompt: str) -> str:
    """The session's auto-title: the first prompt, cut at a word boundary.

    Called exactly once per session, by `app/services/chat_sessions.create`,
    which takes it as an injected parameter so the rule lives here and not in
    `app/`. Nothing caches the result and nothing re-derives it: a rename
    (STORY-016) replaces the title outright, and a renamed session must never
    drift back to its first prompt.

    Four inputs decide the shape of this function, and the naive one-liner
    `prompt[:TITLE_MAX_LENGTH].rsplit(" ", 1)[0]` gets two of them wrong:

      short prompt          -> returned unchanged, and with no ellipsis, because
                               an ellipsis is a claim that something was cut
      long prompt           -> cut at the last space inside the cap
      one unbroken token    -> cut at the cap. `rsplit` has no boundary to find
                               and returns the empty string once anything
                               precedes the token, which would title the session
                               with nothing at all
      whitespace only       -> SESSION_UNTITLED_TITLE. A blank row in the rail
                               is unclickable and unnameable

    Whitespace is collapsed first, so a pasted multi-line prompt yields one
    line: a newline inside a rail row is not a title, it is a layout bug.
    """
    text = " ".join(prompt.split())
    if not text:
        return SESSION_UNTITLED_TITLE
    if len(text) <= TITLE_MAX_LENGTH:
        return text

    head = text[:TITLE_MAX_LENGTH]
    cut = head.rsplit(" ", 1)[0].rstrip()
    if not cut:
        # No boundary inside the cap -- one long token. Cut it at the cap
        # rather than returning nothing.
        cut = head
    return cut + TITLE_ELLIPSIS
```

- **Mirror**: `chat_ui/chat_ui/admin_formatting.py:56-59, 172-178` — constant pair beside the function, `<=` comparison so a value exactly at the cap is not ellipsized.
- **Validate**:
  `python -c "from chat_ui.chat_ui.formatting import derive_title as d; print(repr(d('Summarise the Q3 vendor spend'))); print(repr(d('x'*80))); print(repr(d('   ')))"`
  → the short prompt unchanged, a 48-char cut plus `…`, and `Untitled chat`.

### Task 4: `format_activity` in `formatting.py`

- **File**: `chat_ui/chat_ui/formatting.py`
- **Action**: UPDATE
- **Implement**: Append below `derive_title`. It composes `humanize_compact` rather than re-bucketing.

```python
# One day in seconds, named because `format_activity` branches on it twice.
_ONE_DAY_SECONDS = 86400
_YESTERDAY_TEXT = "yesterday"
_DAYS_AGO_TEMPLATE = "{days} days ago"


def format_activity(updated_at: str, now: Optional[datetime] = None) -> str:
    """The rail's activity time: "2m ago", "yesterday", "3 days ago".

    A **third** spelling of a span already spelled twice, so it composes the
    shared bucket table rather than opening a second one -- the rule the table
    states for itself at the top of this module: the chat's "2 minutes ago" and
    the register's "2m ago" "must never drift into two different ideas of when
    an hour becomes a day". Under a day this *is* `humanize_compact`. Only the
    day arm is new, and only because the rail is the one surface where
    "yesterday" is more useful than a count: a reader choosing between eleven
    conversations reads it faster than "1d ago".

    Recomputed on every load and never stored (PRD Section 6). A persisted
    "2m ago" is wrong the moment it is read back.

    `now` is a parameter so the value is deterministic under test and so a
    rail of thirty rows shares one clock read -- the same reason
    `admin_formatting.to_audit_row` takes one. Degrades to
    SESSION_ACTIVITY_UNKNOWN on a missing or unparseable timestamp rather than
    raising, as `format_duplicate_info` does with
    DUPLICATE_UNPARSEABLE_TEMPLATE: a bad column costs the reading, not the row.
    """
    if not updated_at:
        return SESSION_ACTIVITY_UNKNOWN
    if now is None:
        now = datetime.now(timezone.utc)
    try:
        moved = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        seconds = int((now - moved).total_seconds())
    except Exception:
        return SESSION_ACTIVITY_UNKNOWN

    if seconds < _ONE_DAY_SECONDS:
        # Covers the negative case too: a stored timestamp ahead of the clock
        # reads "just now" rather than a negative count.
        return humanize_compact(seconds)
    days = seconds // _ONE_DAY_SECONDS
    if days == 1:
        return _YESTERDAY_TEXT
    return _DAYS_AGO_TEMPLATE.format(days=days)
```

- Add `from typing import Optional` to the module's imports (`formatting.py` has no `typing` import today; `admin_formatting.py:20` is the precedent for the line).
- **Mirror**: `chat_ui/chat_ui/admin_formatting.py:158-170` (parse, degrade, injectable `now`), `chat_ui/chat_ui/formatting.py:44-51` (`humanize_compact` as the shared spelling).
- **Note on where the strings live**: `_YESTERDAY_TEXT` and `_DAYS_AGO_TEMPLATE` are module-private in `formatting.py`, beside `"just now"` and the bucket table's `"second"/"minute"/"hour"/"day"`, which are already there rather than in `copy.py`. They are *units of a humanizer*, and splitting one humanizer's vocabulary across two files would leave "2m ago" and "yesterday" editable in different places. The two constants in `copy.py` are fallbacks — whole user-facing sentences — which is the line `copy.py` already draws.
- **Validate**:
  `python -c "from datetime import datetime,timezone; from chat_ui.chat_ui.formatting import format_activity as f; n=datetime(2026,9,4,12,0,0,tzinfo=timezone.utc); print(f('2026-09-04T11:58:00Z',n), '|', f('2026-09-03T11:00:00Z',n), '|', f('2026-09-01T11:00:00Z',n), '|', f('nope',n), '|', f('',n))"`
  → `2m ago | yesterday | 3 days ago | no recent activity | no recent activity`

### Task 5: `tests/test_formatting.py`

- **File**: `tests/test_formatting.py`
- **Action**: CREATE
- **Implement**: A new suite — `test_copy.py` is one of the two suites `tests/test_untouched_app.py:_EXTENDED_SUITES` pins by census, and while appending to it is allowed, the bulk of this story's behaviour is formatting rather than copy and belongs in its own file. Open with the `sys.path` preamble every suite here uses. These tests touch no database, so they need no libSQL container and no `temp_db` fixture.

Cases, one assertion cluster each:

1. `test_a_short_prompt_is_its_own_title` — under the cap, returned unchanged, and `TITLE_ELLIPSIS not in result` (AC 3).
2. `test_a_prompt_exactly_at_the_cap_is_not_ellipsized` — `len == TITLE_MAX_LENGTH`, boundary pinned on the `<=` side.
3. `test_a_long_prompt_is_cut_at_a_word_boundary` — result ends with the ellipsis, `len(result) <= TITLE_MAX_LENGTH + 1`, the stripped body contains no partial word (assert the body is a prefix of the source **and** that the character following it in the source is a space), and no trailing space before the ellipsis (AC 2).
4. `test_one_unbroken_token_truncates_at_the_cap` — the AC 4 case. A single token of 200 characters, and separately a short word followed by a 200-character token, which is the input a naive `rsplit(" ", 1)[0]` returns `""` for. Both must return a non-empty title of cap length plus the ellipsis.
5. `test_a_whitespace_only_prompt_falls_back` — parametrized over `""`, `"   "`, `"\n\t "` → `SESSION_UNTITLED_TITLE` (AC 5).
6. `test_a_multiline_prompt_becomes_one_line` — no `\n` in the result.
7. `test_activity_reads_at_every_boundary` — parametrized against a frozen `now`, covering: 0s, 1s, 59s, 60s (`1m ago`), 120s (`2m ago`), 3599s, 3600s (`1h ago`), 86399s, 86400s (`yesterday`), 172799s (`yesterday`), 172800s (`2 days ago`), 259200s (`3 days ago`) (AC 6). Mirrors `test_copy.py:189-210`'s shape.
8. `test_a_future_timestamp_reads_as_just_now` — clock skew must not print a negative count.
9. `test_an_unreadable_activity_time_falls_back_without_raising` — `""`, `"not-a-timestamp"`, `"2026-13-45T99:99:99Z"` → `SESSION_ACTIVITY_UNKNOWN`, no exception (AC 7).
10. `test_activity_defaults_to_the_utc_clock` — called with no `now`, against a timestamp stamped `datetime.now(timezone.utc)` in `_TIMESTAMP_FORMAT`, returns `just now`. Pins that the default clock is UTC-aware and not naive-local, which is the failure that would make every row read "3 days ago" on a machine in another zone.
11. `test_the_summary_carries_three_fields_and_no_figure` — `sorted(ChatSessionSummary.model_fields) == ["activity_info", "session_id", "title"]`, with a docstring quoting PRD Section 6.1. This is the AC 1 guard, and it fails if a message count, a model or a verdict is ever added (AC 1).
12. `test_the_stored_timestamp_format_round_trips` — feeds `format_activity` a string produced by `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`, which is `app/db/database.py:36:_TIMESTAMP_FORMAT`, the exact shape `chat_sessions.updated_at` holds. Pins the seam between the store's format and this parser rather than assuming the `Z`-replacement covers it.

- **Mirror**: `tests/test_copy.py:1-6` (preamble), `tests/test_copy.py:189-210` (boundary parametrization), `tests/test_admin_formatting.py:1-10` (module docstring stating what the file defends).
- **Validate**: `python -m pytest tests/test_formatting.py -q`

### Task 6: The two copy constants asserted in `tests/test_copy.py`

- **File**: `tests/test_copy.py`
- **Action**: UPDATE
- **Implement**: Append at the end of the file, under a section banner in the style of the STORY-008 banner at line ~226 — nothing above is edited, reordered or weakened, which is what `test_untouched_app.py:test_no_assertion_was_removed_from_the_two_extendable_suites` checks. Import both constants **by name** at the top import block for `chat_ui.chat_ui.copy`, so a rename fails at collection rather than at render. One test:

```python
def test_session_fallback_copy_names_the_thing_rather_than_the_failure():
    """STORY-012: both fallbacks are user-facing sentences, so both live here.

    Neither may report a parse failure or apologize (frontend-design: "errors
    don't apologize, and they are never vague about what happened"), and the
    untitled fallback must be non-empty -- a blank row in the rail is
    unclickable and unnameable.
    """
```

Assert: both non-empty; both sentence case; neither contains `"error"`, `"invalid"`, `"failed"`, `"sorry"`, `"unparseable"`, `"None"`, `"null"`; and `derive_title("   ") == SESSION_UNTITLED_TITLE` so the constant is proven to be the one actually returned rather than merely present.

- **Mirror**: `tests/test_copy.py:1-28` (named imports), `tests/test_copy.py:504-520` (the forbidden-word assertion shape).
- **Validate**: `python -m pytest tests/test_copy.py -q`

---

## End-to-End Tests

There is no rendered output in this story, so "end to end" here means the seams with the code on either side of it.

- [ ] `python -m pytest tests/test_formatting.py tests/test_copy.py -q` → all pass.
- [ ] `python -m pytest tests/test_untouched_app.py -q` → passes. Specifically `test_the_chat_humanizer_still_renders_what_it_did` (proves `_humanize` was not disturbed by the new arm) and `test_no_assertion_was_removed_from_the_two_extendable_suites` (proves `test_copy.py` was appended to, not edited).
- [ ] **The STORY-006 seam**: `derive_title` satisfies the injected `Callable[[str], str]` that `app/services/chat_sessions.create` demands.
      `python -c "import inspect; from chat_ui.chat_ui.formatting import derive_title; print(inspect.signature(derive_title))"` → `(prompt: str) -> str`, one positional parameter, so `create(identity, prompt, derive_title)` type-checks and calls cleanly.
- [ ] **The store seam**: `format_activity` parses what `create_chat_session` and `touch_chat_session` actually write — `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")` (`app/db/database.py:36`). Covered by Task 5 case 12; confirm it is not skipped.
- [ ] `python -m pytest tests/test_chat_state.py tests/test_chat_components_import.py tests/test_render_invariants.py -q` → the chat modules still import and render. `models.py` and `formatting.py` are on the chat's import path, so a syntax or import error here is a broken surface, not a broken test.
- [ ] Import the whole package once, to prove no circular import was introduced between `formatting.py` and `copy.py`:
      `python -c "import chat_ui.chat_ui.state; print('ok')"`

**Note before running any suite that touches the database** (`test_chat_state.py`, and the full run): those need the local libSQL dev server from `tests/conftest.py`'s decision record. If the run produces mass fixture errors, restart the container rather than bisecting the code — the dev server degrades under repeated suites. The three files this story creates or changes are pure Python and need none of it.

---

## Validation

```bash
# The story's own suites
python -m pytest tests/test_formatting.py tests/test_copy.py -q

# The guards that could be broken from a distance
python -m pytest tests/test_untouched_app.py -q

# The chat still imports and renders
python -m pytest tests/test_chat_state.py tests/test_chat_components_import.py tests/test_render_invariants.py -q
python -c "import chat_ui.chat_ui.state; print('ok')"

# Full suite before the commit
python -m pytest -q
```

---

## Deviations

| PRD / story says | Plan does | Why |
|---|---|---|
| PRD Section 8: "`rx.Base` for `ChatSessionSummary`" | `pydantic.BaseModel` | `rx.Base` does not exist in the pinned `reflex==0.9.6.post1` — verified against the installed tree, not recalled. `admin_models.py`'s docstring already recorded this once for `AuditRow`. The story's own Technical Notes instruct following `ChatMessage`, which is `pydantic.BaseModel`. Following the PRD literally would not import. |
| Story: "a copy-module fallback string" for the whitespace case | `SESSION_UNTITLED_TITLE` in `copy.py`; but `"yesterday"` and `"{days} days ago"` stay in `formatting.py` | The fallbacks are whole user-facing sentences and belong in `copy.py`, which is what the story asks for. The humanizer's *units* are already in `formatting.py` (`"just now"`, `"second"`, `"minute"`, `"hour"`, `"day"`), and splitting one humanizer's vocabulary across two files would make "2m ago" and "yesterday" editable in different places. Called out here so it reads as a decision, not an oversight. |
| — | No `to_session_summary(...)` projection function | `admin_formatting.to_audit_row` is the obvious analogue and it is deliberately **not** built here: AC 1 fixes this story's deliverable at the model plus the two functions, and the `ChatSession` → `ChatSessionSummary` mapping is STORY-013's, which is where the list is assembled and where `format_activity`'s single shared `now` will be read. Building it here would put a function with no caller on the branch. |

---

## Risks

| Risk | Mitigation |
|---|---|
| A change to the shared bucket table to serve the rail's "yesterday" would silently reword the chat's duplicate card and the register's time column. | `format_activity` composes `humanize_compact` and adds one arm above it; `_BUCKETS`, `_bucket`, `_humanize` and `humanize_compact` are untouched. `test_untouched_app.py:test_the_chat_humanizer_still_renders_what_it_did` compares `_humanize` against the PRD-006 baseline across every boundary and fails if this is got wrong. |
| `derive_title` returns an empty string, producing a rail row that cannot be clicked or named. | Three separate guards — the whitespace collapse, the `if not text` fallback, and the `if not cut` fallback — with Task 5 cases 4 and 5 pinning the two that a naive implementation misses. |
| A naive-local `datetime.now()` would make every row read "3 days ago" for a reader in another zone. | `datetime.now(timezone.utc)`, matching `format_duplicate_info` and `format_refreshed_at`; Task 5 case 10 pins the default clock, and case 12 pins the store's own timestamp format through the parser. |
| The cap becomes a second opinion once STORY-018 adds a CSS ellipsis, and a title is cut twice. | `TITLE_MAX_LENGTH` is a named module constant with a comment saying it is the primary cut and the CSS is the fallback at a narrow viewport. STORY-018 reads it rather than guessing. |
| Someone adds a message count to `ChatSessionSummary` "for completeness", undoing PRD Section 6.1. | Task 5 case 11 asserts the field list exactly, with the PRD quote in its docstring — the same mitigation shape `tests/test_admin_models.py` uses for `AuditRow`'s absent preview fields. |

---

## Acceptance Criteria

(Copied from story `STORY-012`)

- [ ] Given `chat_ui/chat_ui/models.py`, when it is read, then `ChatSessionSummary` declares `session_id`, `title`, `activity_info` and nothing else — no message count, no model, no verdict summary.
- [ ] Given `chat_ui/chat_ui/formatting.py`, when `derive_title(prompt)` is called, then it returns the prompt truncated at a **word boundary**, never mid-word, with an ellipsis only when it actually truncated.
- [ ] Given a prompt shorter than the cap, when `derive_title` runs, then it returns the prompt unchanged with no ellipsis.
- [ ] Given a prompt that is one very long unbroken token, when `derive_title` runs, then it truncates at the cap rather than returning the whole token or an empty string — the case a naive `rsplit(" ", 1)` returns empty for.
- [ ] Given a prompt that is only whitespace, when `derive_title` runs, then it returns a copy-module fallback string rather than an empty title.
- [ ] Given `format_activity(updated_at)`, when it is called, then it returns a relative string ("2m ago", "yesterday", "3 days ago") computed against `datetime.now(timezone.utc)`.
- [ ] Given an `updated_at` that does not parse, when `format_activity` runs, then it returns a fallback rather than raising.
- [ ] Given `tests/test_copy.py` and a new formatting test, when they run, then both functions are covered including all four edge cases above.
- [ ] All tasks completed
- [ ] Backend server starts without error (`python -c "import chat_ui.chat_ui.state"` clean)
- [ ] Follows existing patterns
