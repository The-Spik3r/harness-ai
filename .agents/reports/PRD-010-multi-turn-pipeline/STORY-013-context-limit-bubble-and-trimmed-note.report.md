---
story: STORY-013
prd: PRD-010
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-013-context-limit-bubble-and-trimmed-note.plan.md
epic_branch: epic/PRD-010-multi-turn-pipeline
commit: 36b6088
status: COMPLETE
completed: 2026-09-18
---

# Implementation Report — STORY-013: Chat UI: context_limit bubble and "earlier exchanges not sent" footer note

**Plan**: `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-013-context-limit-bubble-and-trimmed-note.plan.md`
**Epic Branch**: `epic/PRD-010-multi-turn-pipeline`
**Commit**: `36b6088`

## Summary

The two gaps STORY-012 handed over are closed. `_do_send`'s `isinstance` chain
gained the arm the fifth union member never got, so an over-limit send now
renders a `context_limit` bubble that says what happened and what to do,
instead of an `internal_error` reading "Unhandled response type". And
`render_assistant`'s metadata footer now says how many whole exchanges
`chat_history.fit` dropped, from the `history_trimmed` number STORY-012 already
carried and STORY-010 already persists.

Nothing new was invented to do it: the seventh `rx.match` arm, the existing
`_entry` / `_rail` / `_tag` / `_panel` geometry, the `INK_HELD` pigment already
on the palette, and the singular/plural `rx.cond` the PII badge uses two lines
above the footer. No new theme token, no new animation, no new visual direction.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Copy constants: tag, headline, direction, detail + footer templates | `chat_ui/chat_ui/copy.py` | ✅ |
| 2 | `render_context_limit` + the trimmed note in the footer | `chat_ui/chat_ui/components/bubbles.py` | ✅ |
| 3 | The seventh `rx.match` arm, above the default | `chat_ui/chat_ui/components/chat.py` | ✅ |
| 4 | The `elif` arm in `_do_send`; corrected the stale `else` comment | `chat_ui/chat_ui/state.py` | ✅ |
| 5 | Copy coverage + the banned-wording guard | `tests/test_copy.py` | ✅ |
| 6 | Arm position, reused tokens, no literals | `tests/test_context_limit_bubble.py` | ✅ |
| 7 | Render smoke + footer suite extended | `tests/test_chat_components_import.py`, `tests/test_success_metadata_footer.py` | ✅ |
| 8 | Replaced STORY-008's interim test; both parametrized lists extended | `tests/test_chat_state.py` | ✅ |
| 9 | Full suite | — | ✅ |
| 10 | Live run, both surfaces, both grounds | `docs/screenshots/` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Full suite | ✅ 2220 passed, 25 skipped, 0 failed |
| `tests/test_render_invariants.py` | ✅ green, **unedited** |
| Census guards (`test_untouched_app.py`) | ✅ |
| App compiles and serves (`reflex run --env prod`) | ✅ HTTP 200 |
| E2E | ✅ 10/10 |

## Design Decisions Carried Out

### The pigment is `INK_HELD`, and `INK_FORBIDDEN` was rejected on measured contrast

`INK_FORBIDDEN` was the closer semantic match — a configured maximum is a rule
of the deployment, and like `render_forbidden` this bubble offers no retry. It
was measured before being chosen, and it fails:

| Pair | light on `PAPER` | light on its tint | dark on `PAPER` | dark on its tint |
|---|---|---|---|---|
| `INK_FORBIDDEN` / `TINT_FORBIDDEN` | **4.28** ❌ | **4.44** ❌ | 8.51 | 7.94 |
| `INK_HELD` / `TINT_HELD` | 5.25 ✅ | 5.61 ✅ | 9.24 | 8.44 |

Against `AA_NORMAL = 4.5`. That is why `INK_FORBIDDEN` is the one verdict pair
missing from `_INK_ON_TINT` in `tests/test_contrast.py` — the list does not
have a hole by accident. `INK_HELD` clears the floor in both palettes and means
the right thing anyway (`theme.py:69`: "duplicate — held, not rejected"). Two
kinds now share one pigment, which is a real cost against theme.py's
one-pigment-per-outcome habit; the tag carries the distinction, and the amber
family now means "your turn did not go through, and you can fix it", true of
both members.

`tests/test_context_limit_bubble.py::test_the_context_limit_bubble_draws_only_contrast_covered_tokens`
imports `_INK_ON_TINT` rather than restating it, so the two files cannot drift
and a later swap to `INK_FORBIDDEN` fails loudly.

> **Pre-existing defect, surfaced not fixed.** `INK_FORBIDDEN` being sub-AA on
> the light ground means the **existing** `forbidden` bubble's tag and panel
> text already fail the threshold the rest of the palette is held to. This
> story neither caused nor repaired it, and deliberately did not adopt it.
> It wants its own story against the theme.

### The direction is prose, not a second "New chat" button

`ChatState.new_chat` and `copy.SESSION_NEW_CHAT_LABEL` both exist, so an
`_action` button was available and would have mirrored `render_duplicate`. Not
used: the session rail already carries that control permanently and always on
screen, so a bubble-local duplicate scrolls out of the viewport and gives the
interface two controls for one job. It is a one-line addition if review
disagrees.

### `content` is stored, the headline is rendered

`content=result.reason` ("Conversation exceeds context limit") goes on the row
so the restored transcript and the audit row agree; the bubble draws
`CONTEXT_LIMIT_HEADLINE` over it. That split is `render_internal_error`'s, not
a new one.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/copy.py` | UPDATE | +23 |
| `chat_ui/chat_ui/components/bubbles.py` | UPDATE | +69 |
| `chat_ui/chat_ui/components/chat.py` | UPDATE | +11/-1 |
| `chat_ui/chat_ui/state.py` | UPDATE | +37/-5 |
| `tests/test_context_limit_bubble.py` | CREATE | +133 |
| `tests/test_copy.py` | UPDATE | +106 |
| `tests/test_chat_state.py` | UPDATE | +111/-18 |
| `tests/test_success_metadata_footer.py` | UPDATE | +19 |
| `tests/test_chat_components_import.py` | UPDATE | +2 |
| `docs/screenshots/chat-context-limit{,-light}.png` | CREATE | — |
| `docs/screenshots/chat-trimmed-footer{,-light}.png` | CREATE | — |

## Deviations from Plan

1. **`tests/test_contrast.py` was not modified.** The plan's *Files to Change*
   table listed it as UPDATE, but the plan's own Risks row and Task 6 text both
   say the guard belongs in the new file, importing `_INK_ON_TINT` rather than
   editing it — because no new ink/tint pair is added, so there is nothing to
   add to that list, and editing an extend-only census-pinned suite for no
   reason is the wrong move. The guard exists and is stronger for importing the
   list. AC 4's contrast clause is satisfied.

2. **Task 7's validate command cannot pass as written, for a pre-existing
   reason.** `python -m pytest tests/test_chat_components_import.py
   tests/test_success_metadata_footer.py` errors at collection with
   `No module named 'chat_ui.chat_ui.models'`. Reproduced with all of this
   story's changes stashed, so it is **not** a regression:
   `tests/test_success_metadata_footer.py:6` inserts `chat_ui/` onto
   `sys.path`, which shadows the outer package, and the file only collects when
   something imports `chat_ui.chat_ui.*` first. Validated instead with
   `tests/test_copy.py tests/test_success_metadata_footer.py` (60 passed) and
   by the full suite. Left alone rather than half-fixed — it is a latent trap in
   a file this story only appends to.

3. **Task 10 used a local stub upstream instead of live model calls.** The plan
   pointed at STORY-012's live-run precedent, but the trimmed footer only needs
   a *successful* exchange — the answer's text is irrelevant to what the footer
   renders. A stub on `127.0.0.1:9099`, reached by patching
   `openrouter_client._API_URL` from a `sitecustomize.py` on `PYTHONPATH` in the
   scratchpad, exercises the entire real path (state → `fit` → pipeline →
   redaction → persistence → render) at no cost with nothing leaving the
   machine. **No repo file was changed to do it.** `DATABASE_URL` was overridden
   to the local libSQL dev server and verified before launch, so the hosted
   Turso database was never touched.

4. **Task 10's two captures needed two runs, not one.** The plan suggested
   forcing the refusal with a small `CONTEXT_MAX_CHARACTERS` and the trimmed
   footer with a small `CONTEXT_MAX_MESSAGES`. The message-limit route cannot
   reach the refusal at all: `fit` trims history until it fits, so the only
   conversation that can exceed is one whose *single new user turn* is itself
   over the character budget — which is exactly PRD 6.5's reachability note.
   Run 1: `CONTEXT_MAX_MESSAGES=3` for the footers. Run 2:
   `CONTEXT_MAX_CHARACTERS=40` for the refusal.

5. **Task 8 extended two parametrized lists the plan did not name.**
   `test_every_bubble_kind_is_persisted` and
   `test_every_bubble_kind_survives_the_round_trip` both enumerate every kind;
   leaving the eighth out would have left their own docstrings false. The
   round-trip case is what proves AC 2's "restored" half at field level, plus
   one dedicated test for `restored is True`, which `_fields` excludes.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_context_limit_bubble.py` | `test_the_match_has_a_context_limit_arm_above_the_default`, `test_the_renderer_is_imported_by_name`, `test_the_context_limit_bubble_draws_only_contrast_covered_tokens`, `test_the_context_limit_bubble_writes_no_user_facing_literal`, `test_the_kind_string_matches_the_bubble_state_builds` |
| `tests/test_copy.py` | `test_every_context_limit_string_exists_and_is_not_empty`, `test_the_context_limit_copy_is_the_wording_the_prd_fixed`, `test_the_context_limit_copy_names_no_mechanism_and_does_not_apologize`, `test_the_trimmed_footer_note_reads_as_a_sentence_for_one_and_many` |
| `tests/test_success_metadata_footer.py` | `test_footer_trimmed_copy_constants`, `test_chat_message_carries_history_trimmed` |
| `tests/test_chat_state.py` | `test_chat_state_send_context_limit_renders_a_context_limit_bubble` (replaces the interim pin), `test_a_restored_context_limit_bubble_keeps_its_copy_and_is_marked_restored`, plus `context_limit` cases in both kind-enumerating parametrize lists |

## The Live Run

Run through the real `ChatState` path in `reflex run --env prod --single-port`.
`DATABASE_URL` pointed at the local libSQL dev server and the upstream at a
local stub, so nothing left the machine and nothing was written to the hosted
database.

### The trimmed footer (`CONTEXT_MAX_MESSAGES=3`)

Five sends in one session, every footer read off the live DOM:

```
gpt-4 · 41 tokens · #1
gpt-4 · 42 tokens · #2
gpt-4 · 43 tokens · #3 · 1 earlier exchange was not sent to the model
gpt-4 · 44 tokens · #4 · 2 earlier exchanges were not sent to the model
gpt-4 · 45 tokens · #5 · 3 earlier exchanges were not sent to the model
```

Sends 1 and 2 are the **`history_trimmed == 0` control** for AC 3: the footer
is `model · N tokens · #ID`, no separator, no note. Send 3 is the singular,
sends 4 and 5 the plural — including PRD Section 5 story 2's own example.

The stub recorded what actually went upstream, which is `fit` capping at 3:

```
[stub] send #1: 1 messages upstream
[stub] send #2: 3 messages upstream
[stub] send #3: 3 messages upstream
[stub] send #4: 3 messages upstream
[stub] send #5: 3 messages upstream
```

A page reload reproduced all five footers byte-for-byte, which is PRD Section
11's "a reload shows the same note (persisted)".

Screenshots: `docs/screenshots/chat-trimmed-footer.png` (dark),
`docs/screenshots/chat-trimmed-footer-light.png` (light).

### The `context_limit` bubble (`CONTEXT_MAX_CHARACTERS=40`)

A 92-character turn into the same session:

```
TOO LONG
This chat is too long to send.
Detail: characters 92 of 40
Start a new chat to continue.
```

Rail glyph and tag in `INK_HELD`, panel on `TINT_HELD` with the 2px left
border, headline in prose, counts in the data voice, direction last. Not an
`internal_error`, which is the whole point of the story. A reload restored it
identically. "New chat" followed by a short prompt then produced an ordinary
`CLEARED` bubble (`gpt-4 · 46 tokens · #7`), so the refusal did not poison the
session.

Screenshots: `docs/screenshots/chat-context-limit.png` (dark),
`docs/screenshots/chat-context-limit-light.png` (light).

## End-to-End Checks

| # | Check | Result |
|---|-------|--------|
| 1 | Over-limit send → `context_limit` bubble with tag, headline, detail, direction | ✅ |
| 2 | Row carries `content == "Conversation exceeds context limit"`, never shown on screen | ✅ |
| 3 | Reload → same kind, content, detail; `restored=True`; no re-animation | ✅ |
| 4 | New chat + normal send → ordinary assistant bubble | ✅ |
| 5 | 1 dropped → singular; 3 dropped → plural | ✅ |
| 6 | 0 dropped → footer unchanged, no trailing separator | ✅ |
| 7 | History off → no note (0 by construction, STORY-012) | ✅ covered by `test_history_off_integration.py` |
| 8 | `something_new` still lands on `render_fallback` | ✅ `_KINDS` keeps it last |
| 9 | `test_render_invariants.py` green, unedited | ✅ |
| 10 | Both surfaces captured in light and dark | ✅ |

## Acceptance Criteria

- [x] `_do_send` appends `ChatMessage(kind="context_limit", content=result.reason, prompt=text, detail=…)` through `_append_and_persist`; STORY-008's interim test replaced, new test asserts kind and detail
- [x] A `context_limit` bubble (live and restored) renders as a distinct `rx.match` arm reusing the block-bubble geometry, tag and copy constants from `copy.py`; does not fall through to the default arm
- [x] `history_trimmed > 0` renders the note from a copy template, singular and plural; `history_trimmed == 0` leaves the footer as it was
- [x] New constants covered by `tests/test_copy.py`; no "context", "limit", "token" or apology wording; no new ink/tint pair added, and the reused pair is contrast-covered and pinned
- [x] App run, both surfaces screenshotted, `tests/test_render_invariants.py` green
- [x] All tasks completed
- [x] Full suite green
- [x] Follows existing patterns
