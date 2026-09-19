---
story: STORY-013
prd: PRD-010
slug: context-limit-bubble-and-trimmed-note
title: "Chat UI: context_limit bubble and 'earlier exchanges not sent' footer note"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-010-multi-turn-pipeline
created: 2026-09-18
---

# Plan: Chat UI: context_limit bubble and "earlier exchanges not sent" footer note

## Summary

Close the two gaps STORY-012 handed over. First, `_do_send`'s `isinstance` chain gains the arm the fifth union member never got, so an over-limit send renders a `context_limit` bubble that says what happened and what to do instead of an `internal_error` reading "Unhandled response type". Second, `render_assistant`'s metadata footer learns to say how many whole exchanges `chat_history.fit` dropped, from the `history_trimmed` number STORY-012 already carries onto the bubble and STORY-010 already persists. Everything reuses what exists: the seventh `rx.match` arm in `chat.py`, the `_entry` / `_rail` / `_tag` / `_panel` geometry in `bubbles.py`, the `INK_HELD` / `TINT_HELD` pigment, and the singular/plural `rx.cond` the PII badge already uses two lines above the footer. No new theme token, no new animation, no new visual direction.

## User Story

As an end user
I want to be told plainly when a chat is too long to send, and when earlier exchanges were left out of what the model saw
So that I know why the model forgot something and what to do about it.

## Story Reference

- Story file: `.agents/stories/PRD-010-multi-turn-pipeline/STORY-013-context-limit-bubble-and-trimmed-note.md`
- PRD: `.agents/PRDs/PRD-010-multi-turn-pipeline/PRD.md` — sections 4 (Chat UI), 5 (story 2), 6.5 (D2), 7 (F6, F8), 8 (skill constraints), 11

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/chat_ui/copy.py`, `chat_ui/chat_ui/components/bubbles.py`, `chat_ui/chat_ui/components/chat.py`, `chat_ui/chat_ui/state.py`, tests (copy, contrast, components, footer, chat state) |
| Story | STORY-013 |
| PRD | PRD-010 |
| Epic Branch | `epic/PRD-010-multi-turn-pipeline` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `frontend-design` | Story frontmatter lists it, and PRD Section 8 pins its writing rules to exactly these two surfaces. Rules carried into the design below: *"Write from the end user's side of the screen. Name things by what people control and recognize, never by how the system is built"*; *"Treat failure and emptiness as moments for direction, not mood… Errors don't apologize, and they are never vague about what happened"*; *"Keep the register conversational and tuned: plain verbs, sentence case, no filler… Let each element do exactly one job"*; *"However, sometimes less is more, and extra animation contributes to the feeling that the design is AI-generated"*; *"Structure is information. Structural devices… should encode something true about the content, not decorate it."* | Tasks 1, 2, 3, 6 |

The skill's *"take one real aesthetic risk"* clause does **not** apply here and is deliberately not exercised. PRD Section 8 is explicit that both surfaces "follow the existing register and bubble system… rather than introducing a new visual direction", and the story's Technical Notes say "This is a new kind, not a new visual direction". The risk-taking was spent when the ledger was designed; this story is the seventh entry in it.

---

## Design Decisions

Three choices the story left open, each resolved with evidence, because each would look arbitrary in a diff.

### D-A: the tag is `"TOO LONG"`

`TAG_DUPLICATE = "HELD"` and `TAG_INJECTION = "DENIED"` are past-participle verb states in the rail's own voice; `TAG_UPSTREAM`/`TAG_INTERNAL` name the party at fault. A context limit is neither a verdict on the content nor a fault, so the state itself is the honest tag. The story's Technical Notes propose `"TOO LONG"` and nothing better presented itself: it is the one thing that is true, it is not mechanism language, and it reads at `TEXT_TAG` size.

### D-B: the pigment is `INK_HELD` / `TINT_HELD`, reused — **and `INK_FORBIDDEN` was rejected on measured contrast**

The story says "reuse a block tone rather than inventing one", so no new token is added to `theme.LIGHT` / `theme.DARK`. Two candidates were measured against `tests/test_contrast.py`'s `AA_NORMAL = 4.5`:

| Pair | light on `PAPER` | light on its tint | dark on `PAPER` | dark on its tint |
|---|---|---|---|---|
| `INK_FORBIDDEN` / `TINT_FORBIDDEN` | **4.28** ❌ | **4.44** ❌ | 8.51 | 7.94 |
| `INK_HELD` / `TINT_HELD` | 5.25 ✅ | 5.61 ✅ | 9.24 | 8.44 |

`INK_FORBIDDEN` was the better semantic fit on first reading — a configured limit is a rule of the deployment, and like `render_forbidden` the new bubble offers no retry — but it is **below AA on the light ground**, which is precisely why it is the one verdict pair missing from `_INK_ON_TINT` (`tests/test_contrast.py:140-146`). Choosing it would either fail AC 4 or require leaving the new pair out of the contrast suite, which is the same silence repeated. `INK_HELD` passes in both palettes and its meaning is right anyway: theme.py:69 glosses it "duplicate — held, not rejected", and a context-limit refusal is held, not rejected — nothing is wrong with what the user wrote, the send simply did not happen, and the user can act.

Sharing one pigment between two kinds is a real cost against theme.py's one-pigment-per-outcome habit, and it is paid knowingly: the tag disambiguates them, and the amber family now means "your turn did not go through, and you can fix it", which is true of both members.

> **Out of scope, surfaced not fixed:** `INK_FORBIDDEN` is sub-AA on the light ground today, so the existing `forbidden` bubble's tag and panel text already fail the threshold the rest of the palette is held to. This story neither causes nor repairs it, and must not silently adopt it. Raise it as its own story against PRD-006/PRD-010's theme, not here.

### D-C: the direction is prose, not a second "New chat" button

`ChatState.new_chat` exists (`chat_ui/chat_ui/state.py:449`) and `copy.SESSION_NEW_CHAT_LABEL = "New chat"` exists, so `_action(copy.SESSION_NEW_CHAT_LABEL, ChatState.new_chat, ink)` is available and would mirror `render_duplicate`'s `_action`. It is deliberately **not** used. The session rail already carries that control permanently, one click away and always on screen; a bubble-local duplicate of it scrolls out of the viewport and gives the interface two controls for one job, against *"Let each element do exactly one job."* The bubble's job is to say what happened and point at the control that already exists — which is exactly what `DUPLICATE_CHANGE_NOTICE` does at `bubbles.py:258-264`, in prose, inside the panel.

If review prefers the button, it is a one-line addition at the end of the `_panel` call and needs no other change. Recorded so the absence reads as a decision.

---

## Patterns to Follow

### Copy — `SCREAMING_SNAKE` under a section banner, templates end in `_TEMPLATE`, singular gets its own constant

```python
# SOURCE: chat_ui/chat_ui/copy.py:54-63
# --- Verdict tags --------------------------------------------------------
# One tag per pipeline outcome, in the rail's own vocabulary.
TAG_USER = "YOU"
TAG_ASSISTANT = "CLEARED"
TAG_DUPLICATE = "HELD"
TAG_INJECTION = "DENIED"
```

```python
# SOURCE: chat_ui/chat_ui/copy.py:69-73
PII_BADGE_TEMPLATE = "{count} PII types masked in this exchange: {entities}"
PII_BADGE_SINGLE_TEMPLATE = "1 PII type masked in this exchange: {entities}"
```

The plural/singular pair is the exact precedent for the footer note: two constants, the singular spelling `1` literally rather than interpolating it.

### Bubbles — a block kind is `_entry(message, _rail(ink), _tag(...), _panel(ink, tint, ...))`

```python
# SOURCE: chat_ui/chat_ui/components/bubbles.py:305-333
def render_forbidden(message) -> rx.Component:
    """Denied by policy, not detected as an attack -- no retry action, since
    resending the same prompt hits the same permission check again."""
    ink, tint = theme.INK_FORBIDDEN, theme.TINT_FORBIDDEN
    return _entry(
        message,
        _rail(ink),
        _tag(copy.TAG_FORBIDDEN, ink),
        _panel(
            ink,
            tint,
            _prose(message.content),
            rx.cond(
                message.required_permission != "",
                _evidence(
                    f"{copy.FORBIDDEN_PERMISSION_LABEL}: ",
                    rx.el.span(message.required_permission, ...),
                    color=ink,
                    margin_top="0.5rem",
                ),
                rx.fragment(),
            ),
        ),
    )
```

Passing `message` as `_entry`'s first argument is what keeps `restored=True` bubbles out of the `.hx-entry` mount animation (`bubbles.py:112-147`). It is not optional decoration — omit it and switching sessions animates the restored transcript.

### Bubbles — a direction line is prose in the panel, in the body font at data size

```python
# SOURCE: chat_ui/chat_ui/components/bubbles.py:258-264
            rx.box(
                copy.DUPLICATE_CHANGE_NOTICE,
                font_family=theme.FONT_BODY,
                font_size=theme.TEXT_DATA,
                color=ink,
                margin_top="0.5rem",
            ),
```

### Bubbles — the headline is a copy constant, `message.content` carries the machine reason

```python
# SOURCE: chat_ui/chat_ui/components/bubbles.py:336-359, 374-381
def _failure(message, ink, tint, tag, headline) -> rx.Component:
    ...
        _prose(headline),
        rx.cond(
            message.detail != "",
            _evidence(f"{copy.DETAIL_LABEL}: ", message.detail, color=ink, ...),
            rx.fragment(),
        ),
```

`render_internal_error` renders `copy.INTERNAL_ERROR_HEADLINE` while `state.py:1234` sets `content="internal_error"`. That split is the precedent AC 1 and AC 2 together describe: `content=result.reason` is stored (`"Conversation exceeds context limit"` — mechanism language, right for the row), and the *rendered* body is the copy constant.

### Bubbles — singular/plural chosen at render with `rx.cond`

```python
# SOURCE: chat_ui/chat_ui/components/bubbles.py:179-186
    badge_text = rx.cond(
        message.pii_entities.length() == 1,
        copy.PII_BADGE_SINGLE_TEMPLATE.format(entities=entities),
        copy.PII_BADGE_TEMPLATE.format(
            count=message.pii_entities.length(), entities=entities
        ),
    )
```

### State — one `elif isinstance(...)` arm per union member, building one `ChatMessage`

```python
# SOURCE: chat_ui/chat_ui/state.py:1221-1228
            elif isinstance(result, QueryBlockedForbiddenResponse):
                bubble = ChatMessage(
                    kind="forbidden",
                    content=result.reason,
                    prompt=text,
                    required_permission=result.required_permission,
                )
```

Every arm falls through to the single `await self._append_and_persist(bubble, identity, session_id)` at `state.py:1240` — the new arm adds no persistence call of its own (`state.py:872-877`: "Every bubble in `_do_send` goes through here… what makes a ninth outcome added later persist by default instead of by remembering").

### Tests — component claims run in a subprocess with `PYTHONPATH=chat_ui/`, never in-process

```python
# SOURCE: tests/test_session_rail.py:6-11 (docstring)
# The build probe runs in a subprocess with PYTHONPATH set to chat_ui/, which
# is how Reflex itself imports the app (chat_ui.components..., not
# chat_ui.chat_ui.components...). Doing it in-process would put the inner
# package on sys.path and break every other test module.
```

```python
# SOURCE: tests/test_chat_components_import.py:20-51
_PYTHONPATH = [str(REPO_ROOT / "chat_ui"), str(REPO_ROOT)]
_EXPECTED_RENDERERS = ["render_user", "render_assistant", ...]
_KINDS = ["user", "assistant", ..., "internal_error", "something_new"]
```

### Tests — copy suites append below a banner and assert absence of wording, not just presence

```python
# SOURCE: tests/test_copy.py:737-740
# Appended, never edited above: `tests/test_copy.py` is one of the two suites
# `tests/test_untouched_app.py` pins by census, and every test above this line
# is untouched.
```

```python
# SOURCE: tests/test_copy.py:835-845
    for mechanism in ("session", "row", "record", "database", "null"):
        assert mechanism not in text.lower(), f"{text!r} names the mechanism"
    for apology in ("sorry", "apolog", "unfortunately", "oops"):
        assert apology not in lowered, f"{text!r} apologizes"
    for vague in ("something went wrong", "an error", "try again later"):
        assert vague not in lowered, f"{text!r} is vague: {vague!r}"
```

### Tests — the footer suite is plain module-level functions, no fixtures

```python
# SOURCE: tests/test_success_metadata_footer.py:12-16
def test_footer_copy_constants():
    """Verify footer copy constants are defined correctly."""
    assert copy.FOOTER_SEPARATOR == " · "
    assert copy.FOOTER_TOKENS_LABEL == "tokens"
    assert copy.FOOTER_AUDIT_PREFIX == "#"
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/copy.py` | UPDATE | `TAG_CONTEXT_LIMIT`; headline, direction and detail-template constants; the two footer-note templates |
| `chat_ui/chat_ui/components/bubbles.py` | UPDATE | `render_context_limit`; the trimmed note appended to `render_assistant`'s footer |
| `chat_ui/chat_ui/components/chat.py` | UPDATE | Import the renderer; add the seventh arm to `message_bubble`'s `rx.match` |
| `chat_ui/chat_ui/state.py` | UPDATE | Import `QueryBlockedContextLimitResponse`; the `elif` arm; correct the now-false `else` comment |
| `tests/test_copy.py` | UPDATE | STORY-013 banner + constant coverage and the banned-wording guard (AC 4) |
| `tests/test_contrast.py` | UPDATE | One guard that the new bubble reuses a contrast-covered pair (AC 4, D-B) |
| `tests/test_chat_components_import.py` | UPDATE | `_EXPECTED_RENDERERS` + `_KINDS` gain the new renderer and kind |
| `tests/test_success_metadata_footer.py` | UPDATE | The two templates, their rendered strings, and `history_trimmed` on the model (AC 3) |
| `tests/test_context_limit_bubble.py` | CREATE | Source + build assertions: distinct arm, not the fallback, reused tokens, no literal copy (AC 2) |
| `tests/test_chat_state.py` | UPDATE | Replace STORY-008's interim test with the real bubble assertion (AC 1) |

Deliberately **not** in scope: `chat_ui/chat_ui/theme.py` (D-B adds no token), `chat_ui/chat_ui/models.py` (`history_trimmed` already exists at `models.py:34`), the persistence round-trip (`_to_stored_message`/`_to_chat_message` already carry `content`, `detail` and `history_trimmed` verbatim — `state.py:76-77`, `state.py:132-133`), `app/` (the pipeline arm is STORY-008's, shipped), `tests/test_render_invariants.py` (admin-console only; AC 5 asks that it stay green, not that it change), and the `INK_FORBIDDEN` contrast defect (D-B).

---

## Dependency Order

Task 1 (copy) has no dependencies and every other production task reads it. Task 2 (bubbles) needs Task 1. Task 3 (chat.py wiring) needs Task 2. Task 4 (state.py) needs Task 1 only, but is sequenced after 3 so the first end-to-end render is reachable. Tests follow their subject: 5 after 1; 6 after 2 and 3; 7 after 4. Task 8 is the suite, Task 9 the live run.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add the copy constants

- **File**: `chat_ui/chat_ui/copy.py`
- **Action**: UPDATE
- **Implement**: Three edits, each in the block that already owns that kind of string.

  1. In the verdict-tag block (`copy.py:54-63`), after `TAG_INTERNAL`, before `TAG_UNKNOWN`:

     ```python
     TAG_CONTEXT_LIMIT = "TOO LONG"
     ```

     A plain verb-state, like `HELD` and `DENIED` (D-A). Keep `TAG_UNKNOWN` last — it is the fallback and the list reads as "outcomes, then the catch-all".

  2. In the block-and-failure-card block (`copy.py:92-103`), after `DETAIL_LABEL`:

     ```python
     # The chat is over a configured maximum, so this send did not happen. The
     # copy says what is too long and what to do instead; it never says
     # "context limit", which is the name of the setting, not of the problem
     # (PRD-010 Section 8, frontend-design: name things by what people control
     # and recognize). It does not apologize -- nothing failed.
     CONTEXT_LIMIT_HEADLINE = "This chat is too long to send."
     CONTEXT_LIMIT_NEW_CHAT_NOTICE = "Start a new chat to continue."
     # The counts, in the data voice, e.g. "characters 250113 of 200000". The
     # placeholder is `unit` and not `limit` because the value it takes is
     # "characters" or "messages" -- a unit the reader recognizes -- and
     # because "limit" is one of the words this story's copy must not contain.
     CONTEXT_LIMIT_DETAIL_TEMPLATE = "{unit} {actual} of {maximum}"
     ```

  3. In the success-footer block (`copy.py:76-79`), after `FOOTER_AUDIT_PREFIX`:

     ```python
     # What `chat_history.fit` dropped from the send this footer belongs to.
     # Plural and singular are two constants, not one with a conditional "s",
     # because the singular also changes the verb (PII badge, copy.py:69-73).
     FOOTER_TRIMMED_TEMPLATE = "{count} earlier exchanges were not sent to the model"
     FOOTER_TRIMMED_SINGLE_TEMPLATE = "1 earlier exchange was not sent to the model"
     ```

  Every string is sentence case, has no trailing filler, and contains none of `context`, `limit`, `token`, or an apology — Task 5 asserts that rather than trusting it.
- **Mirror**: `chat_ui/chat_ui/copy.py:54-63` (tags), `:69-73` (plural/singular pair), `:92-103` (card constants with a risk comment above each)
- **Validate**: `python -c "import sys; sys.path.insert(0,'chat_ui'); from chat_ui import copy; print(copy.TAG_CONTEXT_LIMIT, '|', copy.CONTEXT_LIMIT_HEADLINE, '|', copy.CONTEXT_LIMIT_DETAIL_TEMPLATE.format(unit='characters', actual=250113, maximum=200000))"`

### Task 2: Add `render_context_limit` and the footer note

- **File**: `chat_ui/chat_ui/components/bubbles.py`
- **Action**: UPDATE
- **Implement**: Two edits.

  1. A new renderer directly after `render_forbidden` (ends `bubbles.py:333`) and before `_failure`, so the block kinds stay contiguous:

     ```python
     def render_context_limit(message) -> rx.Component:
         """Held for length, not judged. The amber of `render_duplicate` on
         purpose: nothing is wrong with what was written, the send just did not
         happen, and the user can act. `INK_FORBIDDEN` was the closer semantic
         match and was rejected -- it is below AA on the light ground (plan
         D-B), which is why it is the one verdict pair missing from
         `_INK_ON_TINT`.

         No recovery action: the session rail's "New chat" is that control and
         it is always on screen (plan D-C).
         """
         ink, tint = theme.INK_HELD, theme.TINT_HELD
         return _entry(
             message,
             _rail(ink),
             _tag(copy.TAG_CONTEXT_LIMIT, ink),
             _panel(
                 ink,
                 tint,
                 _prose(copy.CONTEXT_LIMIT_HEADLINE),
                 rx.cond(
                     message.detail != "",
                     _evidence(
                         f"{copy.DETAIL_LABEL}: ",
                         message.detail,
                         color=ink,
                         margin_top="0.5rem",
                     ),
                     rx.fragment(),
                 ),
                 rx.box(
                     copy.CONTEXT_LIMIT_NEW_CHAT_NOTICE,
                     font_family=theme.FONT_BODY,
                     font_size=theme.TEXT_DATA,
                     color=ink,
                     margin_top="0.5rem",
                 ),
             ),
         )
     ```

     Note `_prose(copy.CONTEXT_LIMIT_HEADLINE)` and **not** `_prose(message.content)`: `content` holds `"Conversation exceeds context limit"`, the pipeline's reason, which belongs in the row and not on the screen. This is `render_internal_error`'s split, not a new one. Pass `message` to `_entry` — restored bubbles must not animate.

  2. Inside `render_assistant`, extend the `footer` (`bubbles.py:203-220`). Build the note above the `footer = rx.cond(...)`:

     ```python
         trimmed_note = rx.cond(
             message.history_trimmed == 1,
             copy.FOOTER_TRIMMED_SINGLE_TEMPLATE,
             copy.FOOTER_TRIMMED_TEMPLATE.format(count=message.history_trimmed),
         )
     ```

     and append exactly one child after `message.audit_id`, leaving every existing child and every style prop byte-for-byte as it is:

     ```python
                 copy.FOOTER_AUDIT_PREFIX,
                 message.audit_id,
                 # STORY-013: the only footer item that is about the send
                 # rather than the answer. Appended last and joined with
                 # FOOTER_SEPARATOR, so with `history_trimmed == 0` the
                 # false arm is `rx.fragment()` and the footer renders the
                 # same DOM it did before this story (AC 3).
                 rx.cond(
                     message.history_trimmed > 0,
                     rx.el.span(copy.FOOTER_SEPARATOR, trimmed_note),
                     rx.fragment(),
                 ),
     ```

     The `rx.el.span` wrapper keeps the separator and the note in one conditional, so there is no way to ship a footer ending in a dangling `" · "`. The `rx.fragment()` false arm is what makes AC 3's "byte-identical" true at the DOM: an unmounted fragment emits no node and no text.
- **Mirror**: `bubbles.py:305-333` (`render_forbidden` shape), `:258-264` (prose direction line), `:179-186` (singular/plural `rx.cond`), `:336-359` (`_evidence` + `DETAIL_LABEL`)
- **Validate**: `python -m pytest tests/test_chat_components_import.py -q` (still green before Task 3 wires the arm — the renderer must at least import and build)

### Task 3: Dispatch the new kind from `message_bubble`

- **File**: `chat_ui/chat_ui/components/chat.py`
- **Action**: UPDATE
- **Implement**: Add `render_context_limit` to the alphabetically sorted import block (`chat.py:6-16`, between `render_assistant` and `render_duplicate`), and add the arm to the `rx.match` (`chat.py:20-33`) after `("forbidden", ...)` and before `("upstream_error", ...)`, so the three blocked outcomes stay together and the two failures follow:

  ```python
          ("context_limit", render_context_limit(message)),
  ```

  It must sit **above** the trailing `render_fallback(message)` default — AC 2's "It does not fall through to the default arm" is a claim about this line's position, and Task 6 asserts it. Update the docstring's "A seventh outcome later is one new arm, not another level of nesting" to record that the seventh arrived and the shape held.
- **Mirror**: `chat_ui/chat_ui/components/chat.py:20-33`
- **Validate**: `python -m pytest tests/test_chat_components_import.py tests/test_chat_shell.py -q`

### Task 4: Build the bubble in `_do_send`

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: Three edits.

  1. Add `QueryBlockedContextLimitResponse` to the `app.models.schemas` import block (`state.py:10-15`), keeping it alphabetically first among the `QueryBlocked*` names.
  2. A new arm after `QueryBlockedForbiddenResponse` (`state.py:1221-1228`) and before the `else`:

     ```python
                 elif isinstance(result, QueryBlockedContextLimitResponse):
                     bubble = ChatMessage(
                         kind="context_limit",
                         # The pipeline's reason, stored not shown: the bubble
                         # renders copy.CONTEXT_LIMIT_HEADLINE instead, the way
                         # the failure kinds do. Keeping it on the row means the
                         # restored transcript and the audit row agree.
                         content=result.reason,
                         prompt=text,
                         detail=CONTEXT_LIMIT_DETAIL_TEMPLATE.format(
                             unit=result.limit,
                             actual=result.actual,
                             maximum=result.maximum,
                         ),
                     )
     ```

     `history_trimmed` stays at its `0` default: no exchange was dropped from an answer, because there was no answer — the reasoning `state.py:1194-1200` already spells out for the other blocked arms. The detail string is built here, at send time, so the restored bubble reproduces it from the persisted `detail` column with no recomputation (`state.py:76`, `state.py:132`).

     `state.py` imports copy constants **by name**, not as a module: add `CONTEXT_LIMIT_DETAIL_TEMPLATE` to the `from .copy import (...)` block at `state.py:25`, keeping that block's existing order. Do not inline the string as an f-string — `copy.py:30-31` records why every constant is imported by name ("so a rename fails at collection rather than at render"), and Task 6.4's no-literal guard depends on it.
  3. Correct the `else` comment (`state.py:1230-1232`). It currently reads "Unreachable for the current QueryResponse union -- kept so a **fifth** member added later…", which became false when STORY-008 added the fifth member and is now false in the other direction. Replace with wording that says the chain covers all five members of `QueryResponse` today and this arm exists so a sixth surfaces as a visible bubble rather than an unhandled exception. Do not delete the `else` — it is the "no silent drops" guarantee the fallback arm mirrors at the render layer.
- **Mirror**: `state.py:1221-1228` (arm shape), `state.py:1194-1200` (comment altitude on a field that is deliberately left at its default)
- **Validate**: `python -m pytest tests/test_chat_state.py tests/test_chat_history_send.py tests/test_history_off_integration.py -q`

### Task 5: Copy coverage and the banned-wording guard

- **File**: `tests/test_copy.py`
- **Action**: UPDATE
- **Implement**: **Append below the existing content**, under a new banner — this suite is census-pinned (`tests/test_untouched_app.py:86`) and `test_copy.py:737-740` states the rule: nothing above the line may be edited. Add the five new constants to the by-name import block at the top (that is an extension, not an edit of a test) and add:

  ```python
  # --- STORY-013: the context-limit bubble and the trimmed-history note ----
  # Appended, never edited above (see the STORY-017 banner for the rule).
  ```

  Then four tests:
  1. `test_every_context_limit_string_exists_and_is_not_empty` — the tuple-and-loop shape of `test_every_rail_string_exists_and_is_not_empty` (`test_copy.py:744-786`) over `TAG_CONTEXT_LIMIT`, `CONTEXT_LIMIT_HEADLINE`, `CONTEXT_LIMIT_NEW_CHAT_NOTICE`, `CONTEXT_LIMIT_DETAIL_TEMPLATE`, `FOOTER_TRIMMED_TEMPLATE`, `FOOTER_TRIMMED_SINGLE_TEMPLATE`.
  2. `test_the_context_limit_copy_is_the_wording_the_prd_fixed` — exact equality on `CONTEXT_LIMIT_HEADLINE == "This chat is too long to send."` and `CONTEXT_LIMIT_NEW_CHAT_NOTICE == "Start a new chat to continue."` (PRD Section 8 quotes both verbatim) and `TAG_CONTEXT_LIMIT == "TOO LONG"`.
  3. `test_the_context_limit_copy_names_no_mechanism_and_does_not_apologize` — **AC 4**, following `test_copy.py:801-845`. Over the headline, the notice and the detail template: assert sentence case (`text == text[0].upper() + text[1:]`) for the two prose strings and `not text.isupper()`; then for every one of them, `for mechanism in ("context", "limit", "token"): assert mechanism not in text.lower()`; then the apology and vague loops (`"sorry"`, `"apolog"`, `"unfortunately"`, `"oops"`; `"something went wrong"`, `"an error"`, `"try again later"`). `TAG_CONTEXT_LIMIT` is exempt from the sentence-case check and asserted `.isupper()` instead — it is a rail tag, and the tags are the one place this interface shouts.
     Guard against a false pass: assert first that the strings under test are non-empty, so a renamed constant resolving to `""` cannot satisfy every `not in`.
  4. `test_the_trimmed_footer_note_reads_as_a_sentence_for_one_and_many` — `FOOTER_TRIMMED_SINGLE_TEMPLATE` is already complete (no `{count}`) and equals `"1 earlier exchange was not sent to the model"`; `FOOTER_TRIMMED_TEMPLATE.format(count=3) == "3 earlier exchanges were not sent to the model"` (PRD Section 5, story 2's example and the story's AC 3). Assert the singular says `exchange was` and the plural says `exchanges were`, so a later edit cannot regress the verb while keeping the noun.
- **Mirror**: `tests/test_copy.py:735-741` (banner + rule), `:744-786` (enumeration), `:801-845` (absence assertions)
- **Validate**: `python -m pytest tests/test_copy.py -q` and `python -m pytest tests/test_untouched_app.py -q`

### Task 6: Pin the arm, the tokens and the absence of literals

- **File**: `tests/test_context_limit_bubble.py`
- **Action**: CREATE
- **Implement**: A module docstring naming STORY-013 and saying what this file is for: the claims AC 2 makes that neither the copy suite nor the import smoke covers — that the kind has its own arm, that the arm is above the default, that the bubble reuses a contrast-covered pigment, and that no user-facing string is written as a literal in `bubbles.py`. Source assertions, read as text, following the "source assertions" half of `tests/test_session_rail.py` (its docstring, lines 15-19, explains why text is the right tool for these).

  1. `test_the_match_has_a_context_limit_arm_above_the_default` — read `chat_ui/chat_ui/components/chat.py`; assert `'("context_limit", render_context_limit(message))'` appears, and that its index is **less than** the index of `"render_fallback(message)"` as it appears in the `rx.match` call. That index comparison is the test of AC 2's "does not fall through to the default arm"; a bare `in` would pass even if the arm were written after the default.
  2. `test_the_renderer_is_imported_by_name` — `render_context_limit` is in `chat.py`'s import block, so a missing import fails at collection rather than at render.
  3. `test_the_context_limit_bubble_draws_only_contrast_covered_tokens` — **AC 4 / plan D-B**. Slice `render_context_limit`'s source out of `bubbles.py` (from `def render_context_limit` to the next top-level `def`), assert it names `theme.INK_HELD` and `theme.TINT_HELD`, assert it names **no** other `INK_`/`TINT_` token by regex, and assert `("INK_HELD", "TINT_HELD")` is a member of `tests.test_contrast._INK_ON_TINT` — importing that list rather than restating it, so the two files cannot drift. This is the test that fails if someone later swaps in `INK_FORBIDDEN`.
  4. `test_the_context_limit_bubble_writes_no_user_facing_literal` — every quoted string in that source slice is either a style value or resolves from `copy.`; concretely, assert `copy.CONTEXT_LIMIT_HEADLINE`'s and `copy.CONTEXT_LIMIT_NEW_CHAT_NOTICE`'s *values* do not appear as literals in `bubbles.py`, mirroring the rail vocabulary guard at `test_copy.py:911-935`.
  5. `test_the_kind_string_matches_the_bubble_state_builds` — assert the literal `"context_limit"` appears in both `chat.py`'s match and `state.py`'s `kind=` for the new arm. A typo in either is otherwise a silent fallback bubble, which is exactly the failure this story exists to remove.

  Do **not** import `chat_ui.components.*` in-process here. `tests/test_session_rail.py:6-11` and `tests/test_chat_shell.py:6-11` both record why: it puts the inner package on `sys.path` and breaks every other test module. Text assertions need no import; the build claim is already covered by Task 7's extension of the subprocess probe.
- **Mirror**: `tests/test_session_rail.py` (source-assertion half), `tests/test_copy.py:852-935` (no-literal guard)
- **Validate**: `python -m pytest tests/test_context_limit_bubble.py -q`

### Task 7: Extend the render smoke and the footer suite

- **File**: `tests/test_chat_components_import.py`, `tests/test_success_metadata_footer.py`
- **Action**: UPDATE
- **Implement**:

  1. `tests/test_chat_components_import.py` — add `"render_context_limit"` to `_EXPECTED_RENDERERS` (`:28-38`, after `render_forbidden`) and `"context_limit"` to `_KINDS` (`:42-51`, after `"forbidden"`). Keep `"something_new"` last: the comment above the list says it is the kind `send()` never emits, and it is what proves the default arm still exists after Task 3 added an arm above it. The probe then renders the new renderer against `ChatState.messages[0]` — a Var, as `rx.foreach` hands it over — which is the build-level proof that `_prose`, `_evidence` and `rx.cond` accept what Task 2 passes them.
  2. `tests/test_success_metadata_footer.py` — append two tests in the file's existing plain-function style (no fixtures, one-line docstring):
     - `test_footer_trimmed_copy_constants` — the two templates exist, and their formatted output for 1 and 3 is the wording AC 3 fixes.
     - `test_chat_message_carries_history_trimmed` — `ChatMessage(kind="assistant", content="Hello", history_trimmed=3).history_trimmed == 3` and that the field defaults to `0`, which is the value that must render no note.

     Leave `test_footer_copy_constants` and `test_chat_message_metadata_fields` untouched — the byte-identity half of AC 3 is the claim that those two still pass unchanged, and editing them would destroy the evidence.
- **Mirror**: `tests/test_chat_components_import.py:28-51`, `tests/test_success_metadata_footer.py:12-30`
- **Validate**: `python -m pytest tests/test_chat_components_import.py tests/test_success_metadata_footer.py -q`

### Task 8: Replace STORY-008's interim test

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE
- **Implement**: Delete `test_chat_state_send_context_limit_lands_on_interim_internal_error_bubble` (`tests/test_chat_state.py:306-346`) and put the real assertion in its place, keeping the same stub shape (`_stub_pipeline(monkeypatch, _fake_run_query)`, `_make_state()`, `await _send(state, "hello world")`) and the same `QueryBlockedContextLimitResponse(reason="Conversation exceeds context limit", limit="characters", maximum=10, actual=12)`:

  ```python
  @pytest.mark.asyncio
  async def test_chat_state_send_context_limit_renders_a_context_limit_bubble(
      temp_db, monkeypatch
  ):
      """PRD-010 STORY-013: replaces STORY-008's interim `internal_error` pin.
      ...
      """
      ...
      assert state.messages[-1].kind == "context_limit"
      assert state.messages[-1].content == "Conversation exceeds context limit"
      assert state.messages[-1].detail == "characters 12 of 10"
      assert state.messages[-1].prompt == "hello world"
      assert state.messages[-1].history_trimmed == 0
  ```

  The docstring should say it discharges the promise STORY-008's docstring made ("STORY-013 is expected to delete it and assert the bubble instead") and note that `detail` is `"<unit> <actual> of <maximum>"`, deliberately a different shape from the audit row's `"context limit: characters 12 > 10"` — the row is for an operator reading a table, the bubble is for the person who sent the message.

  Add a second test that the bubble survives a reload: build the same over-limit send, then re-read the transcript through the state's restore path and assert `kind`, `content` and `detail` come back identical with `restored is True`. AC 2 says "live or restored" and nothing else in the suite proves the restored half. If the existing tests have a helper for the restore path, reuse it; otherwise follow whichever test in this file already exercises `_to_chat_message`.

  **Census check, already verified:** this suite is in `_UNMODIFIED_SUITES` (`tests/test_untouched_app.py:71-78`), but the census compares against baseline `d3e6279`, and `git show d3e6279:tests/test_chat_state.py` does not contain this test name (it has 11 test functions, none of them this one). Deleting it therefore cannot trip `test_no_test_was_removed_from_the_six_pinned_suites`. Task 5's validate step re-runs that guard rather than trusting the check.
- **Mirror**: `tests/test_chat_state.py:306-346` (the test being replaced), `:282-302` (`render_forbidden`'s state test)
- **Validate**: `python -m pytest tests/test_chat_state.py tests/test_untouched_app.py -q`

### Task 9: Full suite

- **File**: —
- **Action**: VERIFY
- **Implement**: Run the whole suite. Per the libSQL dev-server note, mass fixture errors mean restarting the libSQL container, not bisecting this change. Confirm `tests/test_render_invariants.py` is green without having been edited — AC 5 asks for it to pass, and it is admin-console only, so a failure there would mean a new token leaked onto an admin page.
- **Validate**: `python -m pytest -q`

### Task 10: Run the app and capture both surfaces

- **File**: — (screenshots into `docs/screenshots/`, referenced from the story report)
- **Action**: VERIFY
- **Implement**: **AC 5.** Use the `/run` skill to launch the app rather than improvising a command. Override `DATABASE_URL` to the local libSQL dev server first, exactly as STORY-012's report records ("a verification run has no business writing sessions, transcript rows and audit rows into production").

  Two captures:
  1. **The `context_limit` bubble** — monkeypatch or set `CONTEXT_MAX_CHARACTERS` small (e.g. `40`), send a longer prompt, screenshot the bubble showing the `TOO LONG` tag, the headline, the `Detail: characters N of 40` line and the direction. Reload the page and confirm the restored bubble is identical, which is the `restored=True` half of AC 2.
  2. **A trimmed footer** — set `CONTEXT_MAX_MESSAGES` small (e.g. `3`) so `chat_history.fit` drops whole exchanges, send enough turns for `history_trimmed` to reach 1 and then 3, and screenshot the footer reading the singular and the plural. Capture a `history_trimmed == 0` footer in the same session as the control for AC 3.

  Check both in light and dark ground — D-B's contrast argument is about both palettes and the screenshots are the only place it is seen rather than computed.

  Save as `docs/screenshots/chat-context-limit.png` and `docs/screenshots/chat-trimmed-footer.png`, matching the existing `chat-blocked.png` / `chat-pii-masked.png` naming, and attach them to the story report.
- **Mirror**: `.agents/reports/PRD-010-multi-turn-pipeline/STORY-012-chat-state-sends-history.report.md` ("The live run" section), `docs/screenshots/`
- **Validate**: both screenshots exist and are referenced from the report; the app compiled and served without console errors

---

## End-to-End Tests

- [ ] Send an over-limit conversation in the chat → a `context_limit` bubble with the `TOO LONG` tag, "This chat is too long to send.", `Detail: characters N of M`, and "Start a new chat to continue." — **not** an `internal_error` bubble
- [ ] The same bubble carries `content == "Conversation exceeds context limit"` on the row while showing none of that text on screen
- [ ] Reload onto that session → the bubble restores with the same kind, content and detail, `restored=True`, and does not replay the `.hx-entry` animation
- [ ] "New chat", then a normal send → an ordinary assistant bubble; the refusal did not poison the session
- [ ] A send where `fit` dropped 1 exchange → footer ends "· 1 earlier exchange was not sent to the model"; 3 dropped → "· 3 earlier exchanges were not sent to the model"
- [ ] A send that dropped nothing → the footer is `model · N tokens · #ID` with no trailing separator and no note
- [ ] With `CHAT_HISTORY_ENABLED` off → footers show no note at all (`trimmed` is 0 on that path by construction, STORY-012)
- [ ] `something_new` as a kind still lands on `render_fallback` — the seventh arm did not displace the default
- [ ] `tests/test_render_invariants.py` green, unedited
- [ ] Both screenshots captured in light and dark ground

---

## Validation

```bash
python -m pytest tests/test_copy.py tests/test_contrast.py tests/test_context_limit_bubble.py -q
python -m pytest tests/test_chat_components_import.py tests/test_success_metadata_footer.py -q
python -m pytest tests/test_chat_state.py tests/test_untouched_app.py tests/test_render_invariants.py -q
python -m pytest -q
```

---

## Risks + Mitigations

| Risk | Mitigation |
|---|---|
| `INK_FORBIDDEN` is the intuitive pigment for a refusal and is **sub-AA on the light ground** (4.28 / 4.44 vs the 4.5 threshold). Adopting it would ship inaccessible text or force the new pair to be omitted from `_INK_ON_TINT`, repeating the silence that hid the defect. | D-B measures both candidates and picks `INK_HELD` (5.25 / 5.61 light, 9.24 / 8.44 dark). Task 6.3 asserts the renderer names no other ink and that the pair is in `_INK_ON_TINT`, so the swap cannot happen later without a red test. |
| The pre-existing `INK_FORBIDDEN` defect is real and this story does not fix it. | Surfaced explicitly in D-B and in *Files to Change* as out of scope, so it is recorded rather than absorbed. It wants its own story against the theme. |
| AC 3's "byte-identical when `history_trimmed == 0`" cannot be proved by rendering: a Reflex page compiles to a template with a client-side conditional, not to HTML — the point `tests/test_render_invariants.py` makes at length. A test that renders and greps would give a false result either way. | The guarantee is structural and stated as such: one appended child whose false arm is `rx.fragment()`, which mounts no node and no text. The evidence is (a) `test_footer_copy_constants` and `test_chat_message_metadata_fields` passing unedited, (b) Task 10's `history_trimmed == 0` control screenshot next to the trimmed one. Neither is claimed to be more than it is. |
| Appending to `render_assistant`'s footer risks a dangling `" · "` if the separator and the note are two separate conditionals and one is edited later. | Both live inside a single `rx.cond` behind one `rx.el.span`, so they cannot be separated by accident. |
| `tests/test_chat_state.py` is census-pinned and Task 8 deletes a test from it. | Verified, not assumed: `git show d3e6279:tests/test_chat_state.py` has 11 test functions and does not include the interim test, which STORY-008 added at `e4de634`. Task 8's validate step runs `test_untouched_app.py`. |
| `tests/test_copy.py` and `tests/test_contrast.py` are extend-only by census. | Task 5 appends below a banner and edits nothing above; Task 6 puts the new contrast guard in a **new** file and imports `_INK_ON_TINT` rather than editing `test_contrast.py`'s list, so no existing parametrization changes. |
| The banned-wording test could pass vacuously if a constant is renamed to `""` or the test walks the wrong names. | Task 5.3 asserts non-emptiness before asserting absence, and Task 5.1 enumerates the constants by name so a rename fails at import. |
| `CONTEXT_LIMIT_DETAIL_TEMPLATE` would itself fail the banned-wording test if its placeholder were `{limit}`. | The placeholder is `{unit}`, which is also the more accurate word for a value that is "characters" or "messages". Called out in Task 1's comment so a later "tidy-up" rename does not reintroduce it. |
| Two kinds now share `INK_HELD`, against theme.py's one-pigment-per-outcome habit. | Accepted knowingly (D-B), with the tag carrying the distinction and the shared pigment given a meaning true of both members. The alternative was an inaccessible colour or a new token the story forbids. |
| Passing `message` to `_entry` is easy to forget, and omitting it silently re-enables the mount animation on restored bubbles. | Called out in Task 2 and in the *Patterns* section; visible in Task 10's reload check, which is the only place it can actually be seen. |

---

## Acceptance Criteria

(Copied from story `STORY-013`)

- [ ] `_do_send` receiving a `QueryBlockedContextLimitResponse` appends `ChatMessage(kind="context_limit", content=result.reason, prompt=text, detail=<"characters 250113 of 200000" or "messages 101 of 100">)` through `_append_and_persist`; STORY-008's interim "Unhandled response type" test is replaced, and the new test asserts the kind and detail
- [ ] A `context_limit` bubble (live or restored) renders via `bubbles.py` as a distinct `rx.match` arm reusing the block-bubble geometry (rail cell + content column), with a tag and copy constants from `copy.py`: body "This chat is too long to send." and direction "Start a new chat to continue."; it does not fall through to the default arm
- [ ] An assistant bubble with `history_trimmed > 0` renders a footer note built from a copy template — "3 earlier exchanges were not sent to the model", singular "1 earlier exchange was not sent to the model"; with `history_trimmed == 0` the footer is byte-identical to today's
- [ ] The new constants are covered by `tests/test_copy.py`; the new copy contains no "context", "limit", "token" or apology wording; any new ink/tint pair meets the existing contrast threshold (none is added — the reused pair is already covered, and Task 6 pins that)
- [ ] With the app run (`/run`) and a long chat forced over a small monkeypatched limit, a screenshot of the `context_limit` bubble and of a trimmed footer is attached to the story report, and `tests/test_render_invariants.py` is green
- [ ] All tasks completed
- [ ] Full suite green
- [ ] Follows existing patterns
