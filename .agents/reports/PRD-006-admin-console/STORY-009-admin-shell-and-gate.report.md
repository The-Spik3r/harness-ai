---
story: STORY-009
prd: PRD-006
plan: .agents/plans/PRD-006-admin-console/completed/STORY-009-admin-shell-and-gate.plan.md
epic_branch: epic/PRD-006-admin-console
commit: 5a35ce3
status: COMPLETE
completed: 2026-08-31
---

# Implementation Report — STORY-009: `admin_shell.py`, the token gate, the masthead and the two-view switch

**Plan**: `.agents/plans/PRD-006-admin-console/completed/STORY-009-admin-shell-and-gate.plan.md`
**Epic Branch**: `epic/PRD-006-admin-console`
**Commit**: `5a35ce3`

## Summary

`chat_ui/chat_ui/components/admin_shell.py` is the console's first rendered surface and the frame every later admin component hangs inside. It exports `admin_gate()` (the full-page token form), `admin_masthead(active)` (wordmark, the rule-separated two-view switch, sign out, hairline under) and `admin_page(content, active)` (the wrapper that renders one or the other off `AdminState.authenticated`), plus the four constants — `ROUTE_REGISTER`, `ROUTE_SUMMARY`, `VIEW_REGISTER`, `VIEW_SUMMARY` — that STORY-010 will import rather than re-type.

The module follows `shell.py`'s *structure* and replaces its palette decisions. That split was the story's real content: `user_id_gate()` is the closest existing full-page gate, and copying it wholesale would have carried `INK_UPSTREAM` onto the console's submit hover, which PRD-006 Section 6.1 keeps chat-only. The hover moves to `MUTE` instead, measured at 4.63:1 for `PAPER` on `MUTE` and asserted in `tests/test_contrast.py` — the tightest pairing in that list, and the reason it is a test rather than a comment.

The shell draws exactly four lines and nothing else: the rule between Register and Summary, the rule before Sign out, the hairline under the masthead, and the gate panel's border. No fill, no shadow, no icon, no accent, one transition. PRD-006 Section 6.1 spends the console's boldness on the register's stamp margin (STORY-011), so this file is hairlines and alignment on purpose.

Two things landed differently than a first reading of the plan would suggest, and both are recorded below: the palette guard fired on the module's own *prose*, and the plan's `app/` end-to-end check was mis-scoped in a way that matters for STORY-020.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | The gate, the masthead, the switch, the wrapper, the route constants | `chat_ui/chat_ui/components/admin_shell.py` | ✅ |
| 2 | Reach the Radix field's inner `<input>` by id | `chat_ui/chat_ui/theme.py` | ✅ |
| 3 | Assert the one new ink/ground pairing (`PAPER` on `MUTE`) | `tests/test_contrast.py` | ✅ |
| 4 | Build probe + source invariants | `tests/test_admin_shell.py` | ✅ |
| 5 | Quality-floor pass: focus, tab order, narrow viewport, motion | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `tests/test_admin_shell.py` | ✅ 39 passed |
| `tests/test_admin_palette.py` (unmodified) | ✅ 10 passed |
| `tests/test_contrast.py` | ✅ 23 passed (was 22) |
| Chat surface untouched | ✅ 34 passed |
| Full suite | ✅ **418 passed** (baseline 378, +40) |
| PRD-006 changes nothing under `app/` | ✅ empty over `577a285^..HEAD` |
| Guards verified to bite (mutation check) | ✅ hex, copy-literal, forbidden-import |
| No Radix accent in rendered masthead | ✅ zero accent tokens |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/components/admin_shell.py` | CREATE | +337 |
| `tests/test_admin_shell.py` | CREATE | +328 |
| `chat_ui/chat_ui/theme.py` | UPDATE | +6/-3 |
| `tests/test_contrast.py` | UPDATE | +5/-0 |

Exactly the four paths the plan named. No `app/` change, no `chat_ui.py` change (route registration is STORY-010), no new dependency.

## Deviations from Plan

**1. The palette guard fired on the module's own docstring.** Task 1's first validation failed on both parametrizations of `test_no_admin_module_references_a_chat_only_ink`. The cause was not a colour in the code — it was the docstring paragraph *explaining* that the two inks are chat-only, which named them. `tests/test_admin_palette.py` greps the whole file as text, and correctly so: it cannot distinguish prose from a prop. The paragraph was reworded to describe the pair without spelling either name, and it now says why it is written that way, so the next person does not reintroduce the names while documenting the same rule. Risk 3 in the plan anticipated the copy-paste failure and caught a subtler one.

**2. The plan's `app/` end-to-end check was mis-scoped, and this matters for STORY-020.** The plan asked for `git diff main --stat -- app/` to be empty. It is not — `app/db/database.py` and `app/db/models.py` differ from `main` by a PII column migration in commit `3f553f2`, which is *PRD-004-era work already on the epic branch* and predates every PRD-006 commit (`git merge-base --is-ancestor 3f553f2 577a285` → true). The epic branch carries unmerged PRD-004 commits, so `main` is simply not the right baseline for a PRD-006 scope claim. The invariant PRD-006 Section 4 actually states does hold, and was verified two ways: no PRD-006 story commit touches `app/` (checked individually across all eight), and `git diff 577a285^..HEAD --stat -- app/` is empty. **STORY-020's "proof that nothing under `app/` changed" must use the range form, not `git diff main`** — the `main` form will fail for reasons that have nothing to do with PRD-006.

**3. `_label()` helper not written.** Plan task 1.4 made it conditional — *"Only add it if the file actually needs a second eyebrow"*. The masthead's switch links carry their own type and the gate has no eyebrow, so there was no caller. Cut, per the plan's own instruction and the skill's remove-one-accessory rule.

**4. The masthead title is asserted by its two view words, not as one concatenated string.** `admin_copy.MASTHEAD_SEPARATOR` is a non-ASCII middot, and the JSX renderer escapes it to `·`, so `"HARNESS · REGISTER" in rendered` is false while the title is perfectly correct. The test asserts the wordmark and the correct view word are present and the *other* view word is absent, which is the substantive claim anyway.

**5. `tests/test_contrast.py` parametrizes with the string form** (`"name,fg,bg"`), not the tuple form the plan's snippet showed. Matched the file as it is.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_admin_shell.py` | **Build probe (subprocess, Reflex's own import path):** module imports; all five factories build (gate, both mastheads, both wrapped pages); no chat component in `sys.modules`; both `rx.cond` branches compile into one page; each masthead names its own view and not the other; both route constants pinned; routes do not collide with `/audit` `/stats` `/query` `/health`; view keys distinct. **Source invariants:** no literal hex colour; each of 11 copy constants read through `admin_copy.`; no copy value written as a literal (11 cases); no forbidden chat import (5 cases); no local focus reset. — 39 tests |
| `tests/test_contrast.py` | `("inverted button label on hover", PAPER, MUTE)` — 4.63:1 |

The three source guards were mutation-checked rather than assumed: injecting a literal hex, an inlined `"Sign out"`, and a `from chat_ui.components.chat import chat_input` each made the corresponding test fail, and the case-sensitive quoted match confirmed the view keys (`"register"`/`"summary"`) do not false-positive against the labels (`"Register"`/`"Summary"`).

## Notes for the stories this one unblocks

- **STORY-010** imports `ROUTE_REGISTER` / `ROUTE_SUMMARY` / `VIEW_REGISTER` / `VIEW_SUMMARY` from `admin_shell` rather than re-typing the paths, and its page functions **must not** inject a second `rx.el.style(theme.GLOBAL_CSS)` — `admin_page()` owns it. Extend `tests/test_admin_shell.py` with the route-registration probe; `tests/test_chat_components_import.py` is the chat's smoke test and should stay that.
- **STORY-018** should assert against *rendered* output that no Radix accent token reaches the console. `rx.link` runs `props.setdefault("_hover", {"color": color("accent", 8)})` before any other prop handling (`reflex_components_radix/themes/typography/link.py:86`), so a link written without an explicit `_hover` puts an accent in the masthead and **passes** `test_admin_palette.py`, which greps source and cannot see a colour Radix supplies at compile time. Verified clean here (zero accent tokens rendered), but it is a source-invisible failure mode and belongs in the render-invariant test. `test_admin_palette.py:15-21`'s note about the `:focus-visible` blue still applies.
- **STORY-019** inherits a quality floor already checked, not deferred: four real focusable elements with no local `outline`/`box-shadow` reset (a test guards this), no `tab_index` anywhere, `flex_wrap` + `row_gap` + the existing `hx-header-meta` media rule for narrow viewports, and one transition that `prefers-reduced-motion` already flattens.
- The token field is `type="password"` with `autoComplete: off` — a hint browsers may ignore. If a password manager prompt proves annoying in practice, that is a UI-local change.

## Acceptance Criteria

- [x] Given `chat_ui/chat_ui/components/admin_shell.py`, when it is created, then it exports a gate component, a masthead component and a wrapper that renders the gate when `AdminState.authenticated` is False and its content when True.
- [x] Given `/admin/stats` reached directly with no session, when it renders, then the gate is shown and no data appears — both pages assert the condition independently. *(`admin_page(content, VIEW_SUMMARY)` carries its own `rx.cond`; verified the summary page renders the gate's submit at `AdminState` defaults. The data half is `load()`'s own gate, unchanged from STORY-004.)*
- [x] Given a submitted wrong or empty token, when the gate re-renders, then it shows the one generic refusal message from `admin_copy` and the token field is not repopulated. *(`rx.cond` on `gate_error`; the field is controlled by `token_input`, which `_refuse()` clears. No `reset_on_submit`.)*
- [x] Given the masthead, when it renders, then it carries the console title, the two-view switch separated by a rule, and the sign-out control — with a hairline under it.
- [x] Given the sign-out control, when it is activated, then the gate returns and the loaded rows are gone from state. *(wired to STORY-003's `sign_out`, which is `reset()`.)*
- [x] Given the shell, when it is inspected, then it renders no chat component and imports nothing from `chat.py` or `bubbles.py`. *(asserted from both sides — `sys.modules` and source.)*
- [x] Given the shell, when its styling is read, then every colour and size resolves from `theme.py` and every string from `admin_copy` — no literal hex, no literal text.
- [x] Given a keyboard user, when they tab to the token field, the submit, the view switch and sign out, then focus is visible on each.
- [x] All tasks completed
- [x] Full test suite passes — 418 passed
- [x] PRD-006 has changed nothing under `app/` (see Deviation 2 for the correct check)
- [x] Follows existing patterns
