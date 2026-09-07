---
story: STORY-019
prd: PRD-008
plan: .agents/plans/PRD-008-chat-sessions/completed/STORY-019-shell-layout-and-responsive.plan.md
epic_branch: epic/PRD-008-chat-sessions
commit: pending
status: COMPLETE
completed: 2026-09-07
---

# Implementation Report — STORY-019: The rail in the shell

**Plan**: `.agents/plans/PRD-008-chat-sessions/completed/STORY-019-shell-layout-and-responsive.plan.md`
**Epic Branch**: `epic/PRD-008-chat-sessions`
**Commit**: `pending`

## Summary

STORY-018's rail is mounted. `index()`'s authenticated branch is now `vstack(header, shell_body())`, where `shell_body()` is a flex row holding `rail_slot()` beside `transcript_column()`. Below `theme.SESSION_RAIL_COLLAPSE_W` (60rem) the slot collapses to a zero `max-width` with `visibility: hidden` — reclaiming the transcript's full width *and* removing the rail from the tab order — and a **Chats** disclosure in the masthead brings it back. The collapse is the one transition the layout declares, and `theme.GLOBAL_CSS`'s existing reduced-motion block already neutralises it, so this story added no CSS at all.

Three things were found by running the app that no amount of reading would have produced, and each is a change beyond the plan: the composer was misaligned by exactly half the rail's width and moved into the transcript's column; a session switch **did** animate, violating AC 5, and was fixed with a per-message `restored` discriminator; and with `CHAT_HISTORY_ENABLED=false` at a narrow viewport the masthead offered a **Chats** control that revealed a column of nothing.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `rail_expanded` + `toggle_rail`, and `logout()` resets it | `chat_ui/chat_ui/state.py` | ✅ |
| 2 | `rail_slot()` — the collapsing column | `chat_ui/chat_ui/components/shell.py` | ✅ |
| 3 | `rail_disclosure()` — **Chats**, in the masthead | `chat_ui/chat_ui/components/shell.py` | ✅ |
| 4 | `transcript_column()` — the reading column, on `CARD` | `chat_ui/chat_ui/components/shell.py` | ✅ |
| 5 | `shell_body()` — the row | `chat_ui/chat_ui/components/shell.py` | ✅ |
| 6 | `index()` composition, gate unmoved | `chat_ui/chat_ui/chat_ui.py` | ✅ |
| 7 | Confirm `theme.py` needs no new token | `chat_ui/chat_ui/theme.py` | ✅ (no edit) |
| 8 | `tests/test_chat_shell.py` | `tests/test_chat_shell.py` | ✅ |
| 9 | Compile, run, screenshot, prove admin routes untouched | — | ✅ |
| 10 | Self-critique pass | — | ✅ |
| 11 | State tests | `tests/test_chat_state.py` | ✅ |
| + | **AC 5 fix**: `restored` discriminator | `models.py`, `state.py`, `bubbles.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `reflex compile --dry` | ✅ compiled in 5.7s |
| `reflex run --env prod --single-port` | ✅ served, exercised in Chrome at three widths |
| `tests/test_chat_shell.py` | ✅ 38 passed |
| `tests/test_chat_state.py` | ✅ 136 passed (+5) |
| Chat suites on a fresh container | ✅ 194 passed |
| `tests/test_admin_shell.py` + `tests/test_register.py` | ✅ 273 passed, **both undiffed** |
| Full suite | ✅ 1620 passed (1577 at HEAD, +43 new) |
| E2E checklist | ✅ 12/12 |

**On the full-suite flake.** Each full run reported one or two errors, in a *different* unrelated file each time (`test_query_router`, `test_migrate_to_turso_cli`, `test_pii_redaction_integration`, `test_chat_sessions`, `test_query_pipeline_authorization`), every one an `app.db` `StorageError` and every one passing in isolation. This was not taken on trust: the work was stashed and the suite run against clean `HEAD`, which failed the same way (`test_db.py::test_concurrent_init_db_on_an_empty_database_converges`). The flake is the shared libSQL dev server degrading under repeated suites, it predates this story, and restarting the container clears it — after a fresh restart the chat suites are 194/194 green.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/components/shell.py` | UPDATE | +312/-1 |
| `chat_ui/chat_ui/state.py` | UPDATE | +46 |
| `chat_ui/chat_ui/components/bubbles.py` | UPDATE | +34/-3 |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | +29/-8 |
| `chat_ui/chat_ui/models.py` | UPDATE | +23 |
| `tests/test_chat_shell.py` | CREATE | +833 |
| `tests/test_chat_state.py` | UPDATE | +80 |

`theme.py` and `copy.py` were **not** touched: STORY-017 had already declared `SESSION_RAIL_COLLAPSE_W` and `SESSION_RAIL_SHOW_LABEL` for exactly this story, and both were used by name. `chat_ui/reflex.lock/*` was modified as a side effect of running the app (an unrelated `lucide-react` bump) and was reverted rather than committed.

## Deviations from Plan

**1. The composer moved into the transcript's column** — the plan's Task 10 item 3, decided on screen.

Built as the plan specified (a full-width band beneath both columns, per PRD Section 6.1's wireframe) it centred its `COLUMN_MAX` on the *page* while the transcript centred on its *column*. Measured in Chrome: composer at 512–1408, bubbles at 632–1528 — 120px apart, exactly half the rail's 240px. Two fixes existed; padding the band by the rail's width would have restated the collapse in a second place, animation included, to reproduce a centring the column already does. The deciding reason was the skill's *"structure is information"*: the composer types into **this transcript**, scoped to the active session exactly as the bubbles are, and a band stretching under the rail says it belongs to the page. The departure is from the wireframe's ASCII, not from Section 6.1's prose, which places the rail "at the left, under the existing masthead" and says nothing about where the composer stops. Pinned by `test_the_composer_is_in_the_transcripts_column`.

**2. AC 5 was actually broken, and the fix reaches three files outside the plan's list.**

`.hx-entry` (PRD-004) runs on *mount*. A session switch replaces `messages`, so React mounts every bubble the previous transcript did not have. Measured with an `animationstart` listener in Chrome: switching a 2-message chat for a 5-message one fired **exactly three** `hx-enter` animations. PRD Section 6.1 refuses this outright, and it is the operation the PRD says a user performs thirty times a day.

Fixed with `ChatMessage.restored`, set only in `_to_chat_message` (the sole path a stored row takes to the screen) and read only in `bubbles._entry`. **Per message, never toggled** — the obvious alternative, one "suppress animations" flag on `ChatState` switched off after the restore, has a retrigger bug strictly worse than the defect: re-enabling animation on already-mounted nodes starts it on all of them, so the next send would animate the entire transcript. Verified both directions in the browser: a switch now fires **zero** animations, and a live send still fires `hx-enter` on both new bubbles plus `hx-pulse` on the pending indicator — PRD-004's one orchestrated moment is intact, because it is about *arrival* and a restored bubble was never an arrival.

**3. `max_width`, not `width`, on the slot** — a better answer than the plan's, found while writing it.

The plan flagged that a slot declaring a `width` would reserve 15rem of blank column when `session_rail()` returns `rx.fragment()`, and offered as the fallback "extend the flag question inside `session_rail.py`". Neither was needed. The slot states no width at all: it is a flex item sized by its content — the rail's own `SESSION_RAIL_W`, or nothing — and the breakpoint map supplies only a *cap*. An absent rail leaves a column of zero with no configuration question asked twice, and `max-width` transitions exactly as `width` would. Confirmed that `.rt-Box` is `border-box` (`@radix-ui/themes/layout.css`) so the cap clips nothing off the rail's padding — checked, not assumed.

**4. `rail_disclosure()` returns nothing when there is no rail** — found on screen, not planned.

With `CHAT_HISTORY_ENABLED=false` at 900px the masthead showed **Chats**, a control revealing a column of nothing. `shell.py` may not ask the flag (it is named exactly once in all of `chat_ui/`, at the top of `session_rail()`), so `_rail_is_present()` asks the *component* whether it rendered — which is also the better question, since what a disclosure needs to know is "is there a rail to reveal". Pinned by `test_there_is_no_disclosure_when_there_is_no_rail`.

**5. `state.py`, `models.py` and `bubbles.py` were edited**, none of them in the story's stated file list. `state.py` was anticipated in the plan (Risk 7); the other two are the AC 5 fix. Recorded rather than absorbed.

## Self-Critique Pass — "remove one accessory"

Run with the rail on screen at three widths, against *get me back into the right one, and get out of the way*.

**1. Two rails on one screen — they do not compete.** PRD Section 6.1's argument holds, and it is visible in the screenshots: the transcript's `RAIL_X`/`GLYPH` rail is a hairline with square stamps *inside* a white column; the session rail's spine is a solid bar at the far-left edge of a grey one. Different scale, different ground, different axis of meaning. No finding.

**2. The transcript ground: `CARD` kept.** The plan set it with an explicit revert criterion — if the six `TINT_*` panels stopped reading as panels against white, revert to `PAPER`. They read *better*: the tints are off-white washes designed against `PAPER` (#ECEFF1), and against `CARD` (#FFFFFF) they separate more, not less. Verified in Chrome that the rail is `rgb(236,239,241)` and the column `rgb(255,255,255)` — PRD Section 6.1's "PAPER ground against the transcript's CARD" is now literally true, where before this story the hairline was doing all of the separating (STORY-018's report flagged exactly this). `tests/test_contrast.py` already covers `INK`/`MUTE` on `CARD`; no new pairing.

**3. The composer's alignment — the accessory removed.** See Deviation 1. The thing cut was a whole band: the composer stopped being a page-wide element and became part of the column it types into.

**4. The always-visible Rename/Delete pair — re-examined, kept, still a cost.** STORY-018's report handed this forward by name. On screen it is real: every row carries two extra words, and thirty rows carry sixty, which is visibly busier than a hover-revealed menu. It is kept because hiding it is refused twice over — by STORY-018's own accessibility criterion and by PRD Section 6.1's kebab-menu refusal — and because the alternative removes the affordance for exactly the reader who most needs it. Recorded as a standing cost rather than reverted; if it is ever revisited, the change belongs in a story that can also answer the keyboard question.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_chat_shell.py` (new, 38) | the page builds; masthead→row→composer order; the row holds both columns and not the masthead; masthead keeps full width, model selector and user; the slot's narrow arm consults `rail_expanded` and the wide arm does not (the inverted-breakpoint guard); the disclosure exists only below the breakpoint, sits in the masthead, carries `aria-expanded`/`aria-controls`, and uses no icon or glyph; exactly one transition in the layout and it is the collapse, with the three pre-existing hover transitions excluded **by name**; reduced motion still neutralises it; the switch animates nothing; the gate renders no rail and is still the other arm of the one `rx.cond`; `COLUMN_MAX` governs and the column adds no second clamp; `visibility` not `opacity` so a collapsed rail leaves the tab order; nothing cancels the focus ring; no `tabindex`; the rail scrolls in itself; `minWidth: 0` and the row's `overflow: hidden`; the row owns the leftover height; the slot reserves no column with history off and the disclosure disappears with it; positive controls for both; no literal hex, no typed breakpoint, every string from `copy`, no stylesheet, the flag never named |
| `tests/test_chat_shell.py` (AC 5, 4 of the above) | a restored bubble carries no entry animation; a live one still does; the class is decided per message and reads no `ChatState`; every renderer passes its message to `_entry` |
| `tests/test_chat_state.py` (+5) | `rail_expanded` defaults closed; `toggle_rail` opens and closes; it is **not** refused mid-send (unlike the rail's write modes, and why); it touches nothing else; `logout()` closes it |

## Acceptance Criteria

- [x] **AC 1** — masthead across the full width, rail and transcript side by side beneath it, composer along the bottom (of the transcript's column — see Deviation 1)
- [x] **AC 2** — masthead still spans the full width and still carries the model selector and the signed-in user
- [x] **AC 3** — below 60rem the rail collapses, the transcript takes the full width, and **Chats** brings it back
- [x] **AC 4** — the collapse is the only transition the layout declares (`max-width, visibility` at 160ms), and the reduced-motion rule collapses it to 0.01ms — verified in the browser by reproducing the rule and watching the computed duration drop. *Read literally the AC is false and was before this story*: three colour-only hover transitions from PRD-004 (composer Send, gate submit, Edit and resend) already existed, plus `.hx-entry` and `.hx-pulse`. They are named exhaustively in the test rather than grepped around, and removing them is a PRD-004 surface change out of this story's scope.
- [x] **AC 5** — a session switch fires zero animations, verified with an `animationstart` listener (three before the fix)
- [x] **AC 6** — the login gate is unchanged: no rail, no session read, and the `rx.cond` on `user_id` is where it was
- [x] **AC 7** — `COLUMN_MAX` still governs; the column adds no second clamp and the bubbles do not stretch into reclaimed width
- [x] **AC 8** — tab order is masthead → rail → transcript → composer with no `tabindex` anywhere; a collapsed rail is absent from the accessibility tree entirely; the `:focus-visible` ring is intact
- [x] **AC 9** — the rail scrolls in its own container with 27 sessions, and the page body does not scroll horizontally even with a 135-character unbroken token in a bubble
- [x] **AC 10** — `/admin/audit` and `/admin/stats` render with no rail and no chat state; `tests/test_admin_shell.py` and `tests/test_register.py` pass **unmodified** (`git diff --stat` empty)
- [x] All tasks completed
- [x] `reflex compile --dry` succeeds; `reflex run --env prod` serves without tracebacks
- [x] Follows existing patterns

## Notes Forward

**For STORY-020 (design guards).** The rail component itself is untouched by this story, so its palette guards land exactly as planned. Two things that surface changed underneath it: the transcript column is now `CARD` rather than inheriting `PAPER`, which is the ground the rail's `PAPER` is measured against; and `shell.py` now renders layout CSS, so a guard globbing `chat_ui/components/*.py` for hexes will newly include it (it declares none — `test_no_colour_is_written_as_a_literal_hex` already holds it to that).

**For STORY-022 (README/.env).** `CHAT_HISTORY_ENABLED=false` now also removes the **Chats** disclosure, not just the rail — worth one clause if that flag's documented behaviour is enumerated.

**A pre-existing gap, unchanged.** STORY-018's report recorded that `select_session`, `rename_session`, `delete_session` and `retry_sessions` call `resolve(self._token)` *outside* their `try`, so a `StorageError` escapes uncaught. Still true, still not this story's, still worth a follow-up story.

**The dev-server flake is worth a fixture, not a habit.** Proving the suite flake was pre-existing cost a stash-and-rerun of the full suite. A conftest that restarts or health-checks the libSQL container between suites would turn that into a non-event.
