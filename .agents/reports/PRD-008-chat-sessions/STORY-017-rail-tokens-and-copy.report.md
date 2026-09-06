---
story: STORY-017
prd: PRD-008
plan: .agents/plans/PRD-008-chat-sessions/completed/STORY-017-rail-tokens-and-copy.plan.md
epic_branch: epic/PRD-008-chat-sessions
commit: 9df2a39
status: COMPLETE
completed: 2026-09-06
---

# Implementation Report — STORY-017: Rail tokens in theme.py and every rail string in copy.py, adding no new ink

**Plan**: `.agents/plans/PRD-008-chat-sessions/completed/STORY-017-rail-tokens-and-copy.plan.md`
**Epic Branch**: `epic/PRD-008-chat-sessions`
**Commit**: `9df2a39`

## Summary

Four rail sizes appended to `theme.py`, ten rail strings appended to `copy.py`, three tests appended to `tests/test_copy.py`. 219 insertions and **zero deletions** across the three files — every change is an append, which is what the two census guards in `tests/test_untouched_app.py` require and what the diff now proves rather than asserts.

The story's central constraint held: **the theme diff contains no hex literal at all**, and `tests/test_contrast.py` is byte-identical to its parent. The rail needed no new colour because the five tokens it grounds on (`PAPER`, `CARD`, `RULE`, `INK`, `HOVER`) were already declared, and its active mark is `RAIL_X` / `GLYPH` / `SPINE` — the same three tokens `bubbles.py` assembles for the transcript's rail and `register.py` for the stamp margin, appearing a third time at a third scale. No mark token was declared, deliberately: a `SESSION_RAIL_MARK_W` beside `GLYPH` would be a third device wearing the second one's clothes.

The three new tests were each run **red** against the defect it exists to catch before being left green, per STORY-020's rule that a guard which has never failed is a guard nobody has verified.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Four rail sizes in the `--- Scale ---` block, no colour, nothing added to `GLOBAL_CSS` | `chat_ui/chat_ui/theme.py` | ✅ |
| 2 | Ten rail strings under one new banner at end of file | `chat_ui/chat_ui/copy.py` | ✅ |
| 3 | Ten names added to the existing import block | `tests/test_copy.py` | ✅ |
| 4 | Three tests appended under a STORY-017 banner | `tests/test_copy.py` | ✅ |
| 5 | Each new guard broken once and confirmed red, then reverted | — | ✅ |
| 6 | No-new-ink diff proof (hex count, `TINT_*`/verdict-ink sweep, contrast suite untouched) | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `tests/test_copy.py` | ✅ 32 passed (was 29; +3) |
| `tests/test_contrast.py` | ✅ passed **and** `git diff --quiet` clean — AC 9 |
| `tests/test_untouched_app.py` | ✅ 9 passed (theme tokens not retuned; no assertion removed from the two extendable suites) |
| `tests/test_admin_palette.py`, `tests/test_render_invariants.py` | ✅ passed — neither noticed the story, as predicted |
| Targeted suite batch (6 files) | ✅ 161 passed |
| Full suite | ✅ **1534 passed**, 2 pre-existing deprecation warnings, 102s |
| Backend/chat import | ✅ `python -c "import chat_ui.chat_ui.state"` clean |
| Frontend lint | n/a — no JS in this repo; `python -m pytest -q` is the equivalent gate |
| Guards proven red (Task 5) | ✅ 3/3 |
| E2E checklist | ✅ 8/8 |

### Task 6 output, verbatim

```
--- 1. hex literals added to theme.py (must be 0) ---
0
--- 2. TINT_/verdict inks in either module's added lines ---
(no match at all)
--- 3. test_contrast.py untouched ---
contrast suite unmodified
```

### Task 5, the three red runs

| Injected defect | Test that caught it |
|---|---|
| `SESSION_RAIL_EMPTY_TITLE = "No chats yet."` | `test_the_empty_rail_invites_a_chat_rather_than_reporting_none` — failed on the `"no chats"` sweep |
| `SESSION_RAIL_FAULT_BODY = "Sorry, something went wrong. Try again later."` | `test_the_rail_read_failure_names_the_read_and_offers_the_retry` — failed on the missing `RETRY_LABEL`, and would have failed on `"sorry"` |
| `SESSION_RAIL_SHOW_LABEL = ""` | `test_every_rail_string_exists_and_is_not_empty` — failed on the strip check |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/theme.py` | UPDATE | +25 / -0 |
| `chat_ui/chat_ui/copy.py` | UPDATE | +69 / -0 |
| `tests/test_copy.py` | UPDATE | +125 / -0 |

## What Was Added

**`theme.py`** — four sizes, no colour:

| Token | Value | Why that value |
|---|---|---|
| `SESSION_RAIL_W` | `15rem` | Less `RAIL_X` and two gutters leaves ~34 characters at `TEXT_DATA` — under `formatting.TITLE_MAX_LENGTH` (48), so the title's primary cut and the CSS fallback compose as STORY-012 declared rather than competing |
| `SESSION_RAIL_ROW_H` | `3rem` | Two lines: the title, and the activity time under it. `ROW_H` (2.25rem) is a one-line register row and does not fit |
| `SESSION_RAIL_GUTTER` | `0.75rem` | The rail's own padding and its gap to the transcript |
| `SESSION_RAIL_COLLAPSE_W` | `60rem` | `SESSION_RAIL_W` + `MEASURE` is 57rem — the width at which the rail stops costing the transcript its reading measure, rather than an arbitrary device breakpoint |

**`copy.py`** — ten strings: `SESSION_NEW_CHAT_LABEL`, `SESSION_RAIL_EMPTY_TITLE`, `SESSION_RAIL_EMPTY_BODY`, `SESSION_RAIL_FAULT_TITLE`, `SESSION_RAIL_FAULT_BODY`, `SESSION_RAIL_SCOPE_TEMPLATE`, `SESSION_RENAME_LABEL`, `SESSION_RENAME_PLACEHOLDER`, `SESSION_DELETE_CANCEL_LABEL`, `SESSION_RAIL_SHOW_LABEL`.

## Deviations from Plan

| Plan said | Implementation did | Why |
|---|---|---|
| Mirror `chat_ui/chat_ui/theme.py:74-83` | The `RAIL_X`/`ROW_H`/`COLUMN_MAX` group is actually at `:82-90` | Citation offset in the plan; the quoted block content was correct and was followed exactly. Recorded for accuracy, no behaviour change. |
| Copy banner comment: "STORY-018's component for eight of them, STORY-019's collapse for the ninth" | Shipped as "nine of them... the tenth" | Arithmetic fix. Ten constants: nine have a STORY-018 consumer, one (`SESSION_RAIL_SHOW_LABEL`) is STORY-019's. |
| Task 5 revert verified with `git diff --quiet chat_ui/chat_ui/copy.py` | Verified by restoring each constant's value and re-running to green | The plan's own task text already noted that check would not be clean (the story's additions are themselves uncommitted at that point). The three experiments were reverted individually and the suite confirmed green before proceeding. |
| — | `sed -i` rewrote `copy.py`'s line endings from CRLF to LF during Task 5 | Harmless and invisible to the repo: `core.autocrlf=true` normalizes to LF in the index, so the commit is +69/-0 with no whitespace churn, and the working copy is restored to CRLF on the next checkout. Flagged because the same command on a repo without that setting would have produced a whole-file diff. |

Everything else matched the plan, including all three strings and the fourth token added beyond the story's enumerated list — each argued in the plan's Deviations table and each with a named Phase 4 consumer.

## Findings Recorded For Later Stories

Neither is fixed here; `state.py` is not this story's file and changing it would put an untested edit in a copy-only diff.

1. **`sessions_error` carries mechanism text.** It is set to `str(exc)` at four sites (`state.py:220`, `:425`, `:496`, `:750`), and `ChatSessionError` is raised as `f"{operation} failed: {exc}"` (`app/services/chat_sessions.py:85`). If STORY-018 renders that var's text, an employee sees `list_for failed: ...` and this story's fault copy is never seen. The instruction to render the constants and treat the var as a trigger is written into the comment beside the fault pair, where STORY-018 will read it. Worth an assertion in STORY-020: no rail output contains `"failed:"`.
2. **STORY-018's retry has nothing to call.** No handler in `ChatState` re-reads the session list — the read is inline in `login()` (`state.py:213-220`). `SESSION_RAIL_FAULT_BODY` promises a Retry that needs a `reload_sessions()` handler, or a reuse of that read path, before the fault state is honest.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_copy.py` | `test_every_rail_string_exists_and_is_not_empty` — all 17 rail strings (the 10 new plus the 6 inherited from STORY-012/014/015/016) non-empty; `New chat` pinned verbatim; the scope template carries both placeholders and equals `admin_copy.REGISTER_SCOPE_TEMPLATE` |
| `tests/test_copy.py` | `test_the_empty_rail_invites_a_chat_rather_than_reporting_none` — no census phrasing, an act named, sentence case, no mechanism words |
| `tests/test_copy.py` | `test_the_rail_read_failure_names_the_read_and_offers_the_retry` — names the chats, contains `RETRY_LABEL`, states the screen is unchanged, and refuses apology, vagueness and mechanism words |

## Acceptance Criteria

- [x] `theme.py` declares the rail's width, row height and gutter as named tokens, in the style of the existing `RAIL_X`, `ROW_H`, `COLUMN_MAX` group
- [x] No new colour value is added — 0 hex literals in the theme diff, verified against the diff itself
- [x] The active mark reuses `SPINE`, `GLYPH` and `RAIL_X` rather than declaring parallel values
- [x] `copy.py` carries every rail string: the **New chat** label, the empty-rail invitation, the read-failure line, STORY-014's not-saved notice, the delete confirmation, the rename affordance and STORY-012's fallback title
- [x] The delete confirmation names the chat and states the record of what was checked is kept, in the user's words (STORY-016's constant, asserted here as part of the rail vocabulary)
- [x] The empty-rail string invites the reader to start a chat rather than reporting that none exist
- [x] The read-failure string names what failed, offers the retry, and does not apologize
- [x] `tests/test_copy.py` asserts every new constant exists and is non-empty, following the file's existing pattern
- [x] `tests/test_contrast.py` passes **unmodified** — no new ink/ground pairing was introduced
- [x] All tasks completed
- [x] Backend/chat import clean
- [x] Follows existing patterns
