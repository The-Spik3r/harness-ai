---
id: STORY-023
prd: PRD-008
slug: untouched-app-guard-rescope
title: "test_untouched_app.py: retire the provenance guards whose question is closed, and convert the pinned suites to a coverage census"
type: technical
priority: high
complexity: medium
phase: "4 - Surface and hardening"
status: done
labels: [tests, ci, tech-debt]
epic_branch: epic/PRD-008-chat-sessions
plan: .agents/plans/PRD-008-chat-sessions/completed/STORY-023-untouched-app-guard-rescope.plan.md
report: .agents/reports/PRD-008-chat-sessions/STORY-023-untouched-app-guard-rescope.report.md
commit: acc3a08
depends_on: []
blocks: []
skills: []
created: 2026-09-04
updated: 2026-09-04
---

# STORY-023: test_untouched_app.py: retire the provenance guards whose question is closed, and convert the pinned suites to a coverage census

## Description

As a maintainer, I want `pytest -q` to be green on `main`, so that a red CI means something broke — because right now it means nothing at all, and every story in this PRD has had to prove its own innocence by hand before it could be believed.

CI has been red on `main` since PRD-007 merged (`b720d4d`, PR #7). Seven guards in [tests/test_untouched_app.py](../../../tests/test_untouched_app.py) fail there, and they fail on every branch cut from it. [.github/workflows/ci.yml](../../../.github/workflows/ci.yml) runs `pytest -q` on push to `main` and on every PR into it, with no `--deselect` and no `continue-on-error`, so the job is red and the merge gate has stopped discriminating.

**This is not a product defect.** Nothing under `app/` or `chat_ui/` imports that module, and the `Dockerfile` never runs `pytest` — the shipped image is byte-identical whether those seven pass or fail. What is broken is the signal, which is the thing a test suite is for.

## Acceptance Criteria

- [ ] Given `pytest -q` on this branch, when it runs to completion, then it reports **zero failures** — and the seven that fail today are gone by deletion or by reformulation, never by `xfail`, `skip` or a `--deselect` in configuration.
- [ ] Given `tests/test_untouched_app.py`, when it is read, then it no longer contains any assertion of the form "this path has not changed since `_BASE`" evaluated against the **working tree** — the four guards `test_no_file_under_app_changed_since_prd_006_began`, `test_no_new_dependency_in_either_requirements_file`, `test_the_chat_modules_are_unchanged_since_prd_006_began` and `test_the_caddyfile_and_rxconfig_are_unchanged` are removed.
- [ ] Given the removal, when the report is written, then it records the evidence that PRD-006's claim was **true** and only its measurement was wrong: the 40 commits from `577a285` to `99afc9f`, excluding what arrived via the `main` merge `0f77203`, touched zero files under `app/`, zero pinned suites, zero requirements and zero chat modules. The claim is preserved as a finding; only the broken instrument is discarded.
- [ ] Given `test_the_pinned_suites_are_byte_unmodified`, when it is replaced, then the six suites are asserted by **census**: every `test_` function present in the file at `_BASE` is still present by name today. Extending a suite passes; deleting a case fails.
- [ ] Given a hypothetical deletion of one `test_` function from any of the six pinned suites, when the suite runs, then the new census guard fails — verified during implementation by removing one temporarily, observing the red, and restoring it.
- [ ] Given the three durable guards `test_no_assertion_was_removed_from_the_two_extendable_suites`, `test_no_theme_token_was_retuned_or_removed` and `test_the_chat_humanizer_still_renders_what_it_did`, when the story is complete, then they are **byte-unmodified** — this story removes and reformulates, it does not touch what already works.
- [ ] Given the census guard and the three survivors, when the suite runs with `git` unavailable or the history shallow, then it skips rather than fails — the concession the module already makes, inherited unchanged.
- [ ] Given the module docstring, when it is read afterwards, then it explains why the provenance guards were retired, in terms of the defect rather than of convenience: a two-point diff from a fixed baseline to a moving tree answers "what changed since PRD-006 began", never "what did PRD-006 change", and the two stopped being the same question the moment `main` was merged into the epic branch.

## Technical Notes

- Only one file changes: [tests/test_untouched_app.py](../../../tests/test_untouched_app.py). No production code, no configuration, no CI edit. If `ci.yml` needs a change to go green, that is a sign the wrong fix is being applied — the suite must be honestly green, not filtered green.
- **The defect, stated precisely.** `_BASE = "d3e6279"` is the parent of PRD-006's first commit, and `_changed_since_base()` diffs it against the working tree. That equals "what PRD-006 changed" only while PRD-006 is the last thing on the branch. It has not been since `0f77203` ("Merge branch 'main' into epic/PRD-006-admin-console"), which pulled PRD-005's `app/` work into the diff range. **The guard was already unmeasurable before PRD-007 existed**; PRD-007 and PRD-008 only widened a gap that was already open.
- **A plain upper bound does not fix it.** Diffing `_BASE` against PRD-006's merge, or against its branch tip, still reports twelve files under `app/`, because both endpoints sit above the `main` merge. Recovering the claim requires excluding what that merge contributed (`git log <tip> --not <main-at-merge> <base>`), which is why reformulating these four is not worth it: the correct version is a historical fact about immutable commits that can never fail again, and a test that can only pass is not a test.
- **The three survivors are the model to follow**, and the file already argues for them against itself. `test_no_theme_token_was_retuned_or_removed`'s docstring says it verbatim: *"A line-level diff is the wrong instrument... The claim that actually matters is value-level, so that is what is asserted."* That reasoning was applied to one guard and not to the other ten. The census this story writes for the pinned suites is the same move — and `test_no_assertion_was_removed_from_the_two_extendable_suites` is already a working implementation of it for two files, so **extend or generalize that helper rather than writing a second one**; `_TEST_DEF` and the `_git("show", f"{base}:{path}")` idiom are both already there.
- The three guards that currently **pass** by luck — `test_the_caddyfile_and_rxconfig_are_unchanged` and the pinned-suite cases for `tests/test_admin_auth.py` and `tests/test_route_reservations.py` — carry the identical defect and are removed or converted with the rest. Leaving them because they are green today would leave the same failure armed for whoever first edits the `Caddyfile` legitimately.
- `_EXTENDED_SUITES` and `_UNMODIFIED_SUITES` collapse into one list once both are asserted by census. Whether to merge them is an implementation call; if they stay separate, the reason belongs in a comment.
- **Do not re-baseline `_BASE` to a newer commit.** It would make the suite green today and re-break it at the next PRD, which is the exact cycle this story exists to end.
- Running the suite needs the local libSQL dev server from `tests/conftest.py`'s session fixture, even though none of these guards touch storage: the fixture is autouse and calls `pytest.exit` when the endpoint is unreachable. `docker start harness-libsql-dev` first.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story touches one test module. No skill applies.

## Dependencies

- **Blocked by**: none — it touches one test file that no other story reads.
- **Blocks**: nothing formally. It should land **before the PRD-008 → `main` PR**, so that PR is reviewed against a CI whose colour carries information.

## PRD Reference

Not sourced from PRD-008's own sections. The guard belongs to PRD-006 STORY-020, whose report certified the containment claim when the tree still supported it: [`PRD-006/STORY-020`](../../reports/PRD-006-admin-console/STORY-020-untouched-app-regression.report.md).

It is carried here rather than reopened under PRD-006 because PRD-006's epic branch is merged and closed, and because the cost being paid is PRD-008's: every story in this PRD has had to stash its own work and re-measure the baseline to show the seven failures were not its doing (see the reports for STORY-002 through STORY-008). Landing the fix on `epic/PRD-008-chat-sessions` is what makes this PRD's own merge PR green.
