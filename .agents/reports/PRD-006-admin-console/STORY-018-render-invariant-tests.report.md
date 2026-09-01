---
story: STORY-018
prd: PRD-006
plan: .agents/plans/PRD-006-admin-console/completed/STORY-018-render-invariant-tests.plan.md
epic_branch: epic/PRD-006-admin-console
commit: ec7515e
status: COMPLETE
completed: 2026-08-31
---

# Implementation Report — STORY-018: Render invariant tests: no previews in output, no tint or stray colour on the console

**Plan**: `.agents/plans/PRD-006-admin-console/completed/STORY-018-render-invariant-tests.plan.md`
**Epic Branch**: `epic/PRD-006-admin-console`
**Commit**: `ec7515e`

## Summary

PRD-006 Risks 2 and 6 — the previews never reaching the screen, and the console
never painting outside its four verdict inks — are now asserted against a real
database rather than checked by eye. `tests/test_render_invariants.py` seeds a
throwaway SQLite file with four rows, one per verdict, every one carrying a
distinct sentinel in both preview columns; drives `AdminState.authenticate()` and
`AdminState.load()` for real; and inspects the two things that together are what
the browser receives — the compiled page templates for `/admin/audit` and
`/admin/stats`, and the JSON state payload bound into them. No sentinel appears
in either.

The colour half went from per-component to per-page. `tests/test_admin_palette.py`
gained the literal-hex guard applied across the glob that defines an admin module
(seven files, four of which had no such check before) plus a self-test that runs
the same detector over a sample. `tests/test_contrast.py` gained the console's
pairings as a set — six inks across three grounds, eighteen combinations — rather
than a list that has to be remembered when a component moves an ink.

No file under `app/` or `chat_ui/` was touched.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Seeded whole-console probe: previews, boundary, tint, palette (AC 1–4) | `tests/test_render_invariants.py` | ✅ |
| 2 | Literal-hex guard over every admin module, plus its self-test (AC 5) | `tests/test_admin_palette.py` | ✅ |
| 3 | The console's ink × ground contrast matrix (AC 6) | `tests/test_contrast.py` | ✅ |
| 4 | Full suite and change-scope verification | — | ✅ (one finding, below) |

## Validation Results

| Check | Result |
|-------|--------|
| `pytest tests/test_render_invariants.py` | ✅ 57 passed |
| `pytest tests/test_admin_palette.py` | ✅ 18 passed (was 11) |
| `pytest tests/test_contrast.py` | ✅ 41 passed (was 23) |
| Full suite | ✅ 833 passed |
| E2E | ✅ 4/5 — see the `app/` finding below |
| Nothing under `app/` or `chat_ui/` modified by this story | ✅ |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_render_invariants.py` | CREATE | +438 |
| `tests/test_admin_palette.py` | UPDATE | +59/-7 |
| `tests/test_contrast.py` | UPDATE | +48/-0 |

`tests/test_contrast.py` appears in PRD Section 15's "tests that must pass
unmodified" list, and the edit is deliberate: PRD Section 4 requires that "any
new ink/ground pairing … is asserted in `tests/test_contrast.py`", the story's
own technical note says to extend that file rather than duplicate its `contrast()`
helper, and STORY-007 already added the row-hover block to it. The diff is purely
additive — 48 insertions, zero deletions, no existing assertion touched.

## Deviations from Plan

**None in substance.** Two details settled during execution:

- Task 2 planned to "confirm the glob covers `admin_shell.py` before relying on
  it, and add a pattern if any admin module is unmatched". Checked: the existing
  `ADMIN_MODULE_PATTERNS` resolves to all seven admin modules
  (`admin_copy`, `admin_formatting`, `admin_models`, `admin_state`,
  `admin_shell`, `register`, `summary`). No pattern was added.
- `tests/test_contrast.py`'s module docstring gained a sentence naming what
  STORY-018 added, so the file's own map of itself stays current. Not in the
  plan's task list; it is one paragraph and no assertion.

## Findings

**`git diff main --stat -- app/` is not empty, and it is not this story's doing.**
The plan's last E2E item expected it to print nothing. It prints two files:

```
 app/db/database.py | 14 +++++++++++++-
 app/db/models.py   | 11 +++++++++++
```

Both come from commit `3f553f2` — *"feat(chat-ui): implement PII column migration
and enhance duplicate message formatting"*, dated 2026-08-28 — which sits on the
epic branch between the end of PRD-004 and STORY-001 of PRD-006, before any work
on this console began. It adds `AUDIT_LOGS_ADDED_COLUMNS` and an additive
`_add_missing_columns()` migration to `init_db()`.

This story changed nothing under `app/` (`git status --porcelain -- app/ chat_ui/`
is empty), so the check is reported here rather than marked passed. Its owner is
**STORY-020**, whose whole subject is "the proof that nothing under `app/`
changed": that story will have to decide whether PRD Section 11's bar is read
against the epic's own base or against `main`, and if the latter, whether
`3f553f2` is reverted, split out, or recorded as a pre-existing exception. Noted
now so STORY-020 meets it as a decision rather than a surprise.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_render_invariants.py` | `test_the_probe_ran`; `test_the_probe_actually_loaded_the_seeded_record` (the non-vacuity control); `test_no_preview_reaches_the_rendered_output` (8 sentinels × payload + 2 pages = 24); `test_the_row_model_has_no_preview_field` (2); `test_the_row_model_still_carries_what_the_register_reads` (14); `test_no_tint_reaches_either_page` (5 tints × 2 pages = 10); `test_no_colour_outside_the_allowed_set` (2 pages); `test_the_focus_ring_is_the_only_upstream_ink` (2 pages); `test_ink_self_cannot_be_excluded_by_value` — 57 total |
| `tests/test_admin_palette.py` | `test_no_admin_module_writes_a_literal_hex` (7 modules); `test_the_hex_guard_detects_a_hex` |
| `tests/test_contrast.py` | `test_every_console_pairing_is_readable` (6 inks × 3 grounds = 18) |

### The two guards, watched failing

Both were verified by producing the failure the acceptance criteria describe,
then reverted:

- **Non-vacuity.** Seeding zero rows instead of four: **56 of 57 tests still
  passed** — every preview, tint and colour negative among them — and only
  `test_the_probe_actually_loaded_the_seeded_record` failed (`assert 0 == 4`).
  That is the file's own proof that its negatives are statements about a
  populated console, and that the control is what stands between it and a
  tautology.
- **The palette guard bites.** Adding `background_color="#FF00AA"` to
  `chat_ui/chat_ui/components/summary.py` failed exactly two tests, one per
  side of the claim: `test_no_admin_module_writes_a_literal_hex[summary.py]`
  named the file, and `test_no_colour_outside_the_allowed_set[summary_page]`
  named the page. AC 5 is stated as a failure, so it was checked by causing one.

## Design notes carried into the code

Three things the tests could not assert the obvious way, each recorded where a
future reader would otherwise try:

- **A compiled Reflex page carries no values.** It is a template referencing
  state vars; the values arrive as a payload. A preview test that greps only
  `str(register())` would pass whether or not the boundary held, which is why
  the assertion covers `AdminState.dict()` as well.
- **`INK_UPSTREAM` is legitimately on every admin page.** `theme.GLOBAL_CSS`
  paints the global `:focus-visible` ring with it and `admin_page()` owns that
  stylesheet. The rendered stylesheet is stripped before any hex is collected —
  and the strip asserts it shortened the string, so a change in how Reflex
  renders the style element fails loudly instead of silently disarming every
  colour assertion. Stripping `theme.GLOBAL_CSS` itself does *not* work; Reflex
  escapes it on the way in. The exception is pinned from both sides, so an admin
  component adopting the blue fails, and so does the focus ring going missing.
  `tests/test_admin_palette.py` predicted this for STORY-018; its docstring now
  points at where it was answered.
- **`INK_SELF` cannot be excluded by value** — it and `INK` are both `#14181C`.
  The claim stays a by-name source grep in `tests/test_admin_palette.py`, and
  `test_ink_self_cannot_be_excluded_by_value` records the reason.

The story cites `tests/test_pii_badge.py` and `tests/test_success_metadata_footer.py`
as the precedent for asserting over a rendered Reflex component. They are not —
both assert over copy constants and `ChatMessage` fields, and neither renders
anything. The real precedent is the subprocess probe in `tests/test_register.py`,
`tests/test_summary.py` and `tests/test_admin_shell.py`, and the story's actual
instruction — reuse that approach rather than invent a second one — was honoured
by using it.

## Acceptance Criteria

- [x] Given a seeded database whose rows carry distinctive `prompt_preview` and `response_preview` strings, when the register is rendered, then neither string appears anywhere in the rendered output — 24 assertions over 8 sentinels × the payload and both pages, with the non-vacuity control proving the rows were really there.
- [x] Given `AuditRow`, when its attributes are enumerated, then it has no preview field — asserted over `AuditRow.__fields__`, with the 14 fields the register does read asserted present so the negative means something.
- [x] Given the register and the summary, when their rendered output is inspected, then no `TINT_*` value from `theme.py` appears — 5 tints × both pages, read by token name.
- [x] Given the console's rendered output, when its colour values are collected, then every one falls within the allowed set — both pages held to the four verdict inks plus the ground tokens, `INK_UPSTREAM` excluded outside the pinned focus-ring exception, `INK_SELF` covered by name in the palette test because it cannot be covered by value.
- [x] Given a new hard-coded hex added to any admin component, when the suite runs, then the palette test fails — verified by adding one to `summary.py` and watching both guards fail.
- [x] Given `tests/test_contrast.py`, when the suite runs, then every pairing the console introduced clears `AA_NORMAL` — 18 pairings, tightest `MUTE` on `PAPER` at 4.63:1.
- [x] All tasks completed
- [x] Full suite green (833 passed), PRD-001/003/004 test files unmodified
- [x] No file under `app/` or `chat_ui/` changed **by this story** — see the `app/` finding above for the pre-existing epic-branch divergence
- [x] Follows existing patterns
