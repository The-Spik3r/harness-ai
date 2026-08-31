---
story: STORY-012
prd: PRD-006
plan: .agents/plans/PRD-006-admin-console/completed/STORY-012-row-detail-disclosure.plan.md
epic_branch: epic/PRD-006-admin-console
commit: PENDING
status: COMPLETE
completed: 2026-08-31
---

# Implementation Report — STORY-012: Row detail disclosure

**Plan**: `.agents/plans/PRD-006-admin-console/completed/STORY-012-row-detail-disclosure.plan.md`
**Epic Branch**: `epic/PRD-006-admin-console`
**Commit**: `PENDING`

## Summary

Each register row now carries a disclosure holding the five fields `GET /audit`
does not return in full: `error_message`, `suspicious_pattern`, `prompt_hash`,
the full User-Agent, and the PII entity types — with the row's one combined PII
indicator split into `pii_detected_input` and `pii_detected_output`. A tenth
grid track at the right edge holds a chromeless `rx.el.button`; the open set is
`AdminState.open_rows: list[int]`, keyed on `audit_id` and tested with
`Var.contains()`.

Nothing under `app/` was touched (`git diff --name-only | grep -c '^app/'` → 0),
no `theme.py` token was added, and no new colour was introduced.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Four disclosure copy constants (two toggle marks, two PII presence words) | `chat_ui/chat_ui/admin_copy.py` | ✅ |
| 2 | Pin them in the copy test's assertions and exhaustiveness set | `tests/test_copy.py` | ✅ |
| 3 | `open_rows: list[int]` + `toggle_detail(audit_id)` | `chat_ui/chat_ui/admin_state.py` | ✅ |
| 4 | Five handler tests (open/close/reassign, independence, id-keying, sign-out) | `tests/test_admin_state.py` | ✅ |
| 5 | Control column, toggle, detail block, `_row`/`_row_line` restructure | `chat_ui/chat_ui/components/register.py` | ✅ |
| 6 | Eleven disclosure tests + probe factories + `COPY_NAMES` extension | `tests/test_register.py` | ✅ |
| 7 | Live run against a seeded database, all four verdicts | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `reflex compile --dry` | ✅ compiled in 2.5s |
| Full pytest suite | ✅ 561 passed |
| `tests/test_register.py` | ✅ 116 passed (67 → 116) |
| `tests/test_admin_state.py` | ✅ 70 passed (65 → 70) |
| No `app/` change | ✅ 0 files |
| E2E | ✅ 11/12 in-browser; 1 covered at state level (see below) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/admin_copy.py` | UPDATE | +28 |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | +39 |
| `chat_ui/chat_ui/components/register.py` | UPDATE | +277/-20 |
| `tests/test_admin_state.py` | UPDATE | +82 |
| `tests/test_copy.py` | UPDATE | +12 |
| `tests/test_register.py` | UPDATE | +208 |

## Deviations from Plan

1. **`test_toggle_detail_opens_closes_and_reassigns` uses object identity, not
   `id()`.** The plan specified comparing `id(state.open_rows)` across toggles.
   That failed: CPython reused the freed list's address, so the ids matched
   despite a correct reassignment. The test now holds the previous list object
   and asserts both `is not` and that the old list is unmutated — which is the
   stronger claim the plan actually wanted.

2. **Two test assertions rewritten for how Reflex actually compiles.** The plan
   assumed HTML-shaped output. Reflex emits JSX, so `"<button" in toggle` became
   `'jsx("button"' in toggle` plus `'type:"button"'`, and the `contains()` check
   asserts the compiled `.includes(` in the rendered output.

3. **`rx.el.details` / `rx.accordion` are asserted as *not called*, not as
   absent.** Both names appear in `register.py`'s docstring, which records why
   they were rejected; the test greps for `rx.el.details(` with the paren. One
   register docstring was also reworded so the quoted string `"Show detail"`
   stopped tripping `test_no_copy_value_is_written_as_a_literal`.

4. **`chat_ui/reflex.lock/{bun.lock,package.json}` reverted, not committed.**
   `reflex run --env prod` reformatted both and bumped `lucide-react`
   1.14.0 → 1.26.0. That is build-tool churn unrelated to this story, so it was
   reverted rather than ridden into the story commit.

5. **E2E "open disclosure survives a reorder" was verified at state level, not
   in the browser.** The plan suggested driving it by re-sorting, but the sort
   and filter controls are STORY-013 and do not exist yet, so there is no UI to
   reorder from. It is covered by
   `test_open_rows_is_keyed_on_the_audit_id_not_the_position`, which opens a
   row, sorts, and asserts the open set did not follow the slot — plus a live
   DOM check pairing each open detail's `prompt_hash` against its own row's
   `#id`, which a position-keyed disclosure would fail. Worth re-running in the
   browser once STORY-013 lands.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_admin_state.py` | `open_rows_is_a_declared_var_with_an_empty_default`, `toggle_detail_opens_closes_and_reassigns`, `each_rows_disclosure_is_independent`, `open_rows_is_keyed_on_the_audit_id_not_the_position`, `sign_out_closes_every_disclosure` |
| `tests/test_register.py` | `every_disclosure_label_is_rendered` (×7), `disclosure_reads_every_disclosure_only_field` (×7), `error_message_and_pattern_lead_the_disclosure`, `pii_indicator_is_split_on_the_disclosure`, `absent_case_is_stated_rather_than_left_blank`, `disclosure_renders_no_preview`, `toggle_is_a_real_button_with_an_accessible_name`, `open_state_is_the_state_var_not_the_dom`, `toggling_one_row_is_one_event_carrying_one_id`, `disclosure_wraps_where_the_row_truncates`, `disclosure_continues_the_stamp_margins_edge` |
| `tests/test_copy.py` | Four new constants asserted non-empty and added to the exhaustiveness set |

## E2E Verification (live, seeded database, `reflex run --env prod`)

| # | Check | Result |
|---|-------|--------|
| 1 | Toggle opens the detail under its own row; mark flips `+` → `−` | ✅ |
| 2 | **fault** row shows `error_message` in full, wrapped | ✅ `OpenRouter request failed: timeout after 30s while awaiting completion` |
| 3 | **denied** row shows the real pattern | ✅ `ignore previous instructions` |
| 4 | PII row shows types + two split `detected` lines | ✅ `PHONE_NUMBER EMAIL_ADDRESS PERSON`, both sides `detected` |
| 5 | Empty row states every field absent, no blank cells | ✅ four `—` plus two `not detected` |
| 6 | Neither preview reaches the DOM | ✅ both seeded sentinels absent from `body.innerHTML` |
| 7 | Keyboard: Tab focuses, `:focus-visible` ring, Enter opens, Space closes | ✅ 2px `#34567F` ring, no pointer used |
| 8 | Four open, close one → other three stay open | ✅ |
| 9 | Open state follows the row, not the slot | ✅ state-level + DOM pairing (see Deviation 5) |
| 10 | Sign out → gate; sign back in → all closed | ✅ 0 open toggles, 0 detail nodes |
| 11 | Narrow viewport (420px): container scrolls, page does not | ✅ `pageScrollsX: false` |
| 12 | No colour outside the allowed set on an open row | ✅ 0 violations; only fill is the 9×9 `INK_FAULT` stamp |

The `#EDEEF0` seen in a first, over-broad colour sweep is the Radix theme root's
default **inherited** `color`, present on 55 elements page-wide since STORY-009
and painted by nothing in the register — every element that renders text sets
its own ink. Recorded here so STORY-018's render-invariant assertion expects it,
alongside the `INK_UPSTREAM` focus ring `tests/test_admin_palette.py` already
documents.

## Acceptance Criteria

- [x] Disclosure shows `prompt_hash`, `error_message`, PII entity types, full User-Agent, `suspicious_pattern`
- [x] **fault** row renders `error_message` in full
- [x] **denied** row shows the actual `suspicious_pattern`, not a flattened boolean
- [x] `pii_detected_input` / `pii_detected_output` shown split
- [x] Empty fields stated as absent, never blank
- [x] No `prompt_preview`, no `response_preview`
- [x] Focusable with visible focus, operable without a pointer
- [x] Each row's open state independent
- [x] All tasks completed
- [x] `reflex compile --dry` passes
- [x] Full pytest suite passes (561)
- [x] No card, no fill, no accent, no tint on the disclosure (Risk 6)
- [x] Follows existing patterns
