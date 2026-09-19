---
story: STORY-018
prd: PRD-010
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-018-readme-and-env-documentation.plan.md
epic_branch: epic/PRD-010-multi-turn-pipeline
commit: e6c2749
status: COMPLETE
completed: 2026-09-19
---

# Implementation Report — STORY-018: README: multi-turn context shipped, limits and trade-offs; .env.example settings

**Plan**: `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-018-readme-and-env-documentation.plan.md`
**Epic Branch**: `epic/PRD-010-multi-turn-pipeline`
**Commit**: `e6c2749`

## Summary

The last story of PRD-010 makes the documentation match the shipped pipeline. `### Multi-turn context` **moved** out of the roadmap — where it sat below "Everything below this line is **intended direction, not current behavior**" — into the Features block as shipped behaviour, with the heading text kept byte-identical so all four inbound `#multi-turn-context` links still resolve. Its roadmap checkbox moved from *Planned* to *Shipped*. The Chat UI's "No multi-turn context" limitation is gone, replaced by the five caveats the story names. `POST /query` gained its seventh outcome block, the configuration table gained four rows, and `.env.example` gained a `# Multi-turn pipeline (PRD-010)` group — the work STORY-002 explicitly deferred here.

**No production file changed.** `git diff HEAD -- app/ chat_ui/` is empty; every claim the README now makes was read out of the shipped code, the PRD, or the STORY-014/015 reports rather than asserted.

Two numbers are recorded in the README for the first time. The STORY-015 measurement — **~0.93 s added per send at 20 exchanges, 97% of it re-redaction** — is stated plainly under *What it costs*, along with the fact that one of the two levers against it (`PII_REDACTION_ENABLED`) turns off a security control. The STORY-014 result is stated where the README explains why the pipeline has its own thread pool, scoped to what the tests actually assert: responsiveness under a blocked upstream, not throughput.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Features table gains a *Multi-turn context* row | `README.md` | ✅ |
| 2 | `### Multi-turn context` moved out of the roadmap and rewritten as shipped behaviour | `README.md` | ✅ |
| 3 | Roadmap item moved from *Planned* to *Shipped* | `README.md` | ✅ |
| 4 | Chat UI *Known limitations* rewritten (five new bullets) | `README.md` | ✅ |
| 5 | Context-limit `BLOCKED` block in the API Reference | `README.md` | ✅ |
| 6 | Four rows in the Environment Variables table | `README.md` | ✅ |
| 7 | `# Multi-turn pipeline (PRD-010)` group | `.env.example` | ✅ |
| 8 | Two guard tests for the new group (supporting edit) | `tests/test_config.py` | ✅ |
| 9 | Pre-PRD, track overview and `app/config.py` verified, not edited | — | ✅ |
| 10 | Link/anchor checker written and run on HEAD and the working copy | scratchpad | ✅ |
| 11 | Full suite, change audit, commit | — | ✅ |
| 12 | *OpenAI-compatible endpoint* — one sentence on what is now built | `README.md` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Full suite (`pytest tests/ -q`) | ✅ 2255 passed, 26 skipped |
| `tests/test_config.py` | ✅ 54 passed (52 before, +2) |
| Guard-test mutation check | ✅ deleting a comment line fails the new test; restored |
| Link/anchor checker — working copy | ✅ 55 local links, 0 anchor failures |
| Link/anchor checker — `HEAD:README.md` self-check | ✅ slug function proven on the pre-edit file |
| Inbound link from PRD-009's PRD | ✅ `#multi-turn-context` resolves |
| Required anchors present | ✅ `multi-turn-context`, `post-query--blocked-context-limit`, `duplicate-detection-scope`, `chat-ui` |
| `.env.example` ASCII + comment-above-assignment | ✅ |
| Documented defaults vs `app/config.py` | ✅ `120.0`, `100`, `200000`, `32` — field for field |
| Edited tables column-consistent | ✅ Features 4 cols, Environment Variables 6 cols |
| Production code untouched | ✅ `git diff HEAD -- app/ chat_ui/` empty |

The suite's first run produced one fixture `StorageError` in `tests/test_audit_logger.py`. That is the known libSQL dev-server degradation under repeated suites; the container was restarted and the re-run was fully green, with no code change in between.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `README.md` | UPDATE | +50/−11 |
| `.env.example` | UPDATE | +18 |
| `tests/test_config.py` | UPDATE | +26 |

Verified and **not** changed: `pre-prds/PRE-PRD-010-multi-turn-pipeline.md`, `pre-prds/README.md`, `app/config.py`, `app/`, `chat_ui/`.

## Deviations from Plan

1. **One paragraph carried over from the deleted section (addition).** Task 2(a) deleted the old *Multi-turn context* section wholesale, but that section held the only README explanation of `dedup_key` being defined over a conversation — and both the *OpenAI-compatible endpoint* bullet and PRD-009's PRD link here expecting to find it. A condensed paragraph, *"The duplicate check sees the conversation, not the string"*, was carried into the new section so those inbound links still land on the answer. No new claim; the wording is a compression of the deleted text.
2. **Task 4's validation figure was wrong in the plan.** It expected 8 bullets under *Known limitations*; the correct count is 9 (4 original bullets kept, 1 replaced by 5). The original list had five bullets, not four. The edit itself is as planned.
3. **Task 9's `app/config.py` check used the wrong baseline.** The plan ran `git diff --stat main -- app/config.py` expecting empty output; it reports 53 insertions, because STORY-002 (`6c7048e`) added the four settings on this same epic branch. The meaningful check is against `HEAD` — `git diff --stat HEAD -- app/config.py` is empty, confirming this story changed nothing. Recorded here rather than silently substituted.
4. **Two guard tests added to `tests/test_config.py`** (planned as Task 8, flagged there as beyond the story's ACs). Every other settings group in that file carries a `…_documents_…_with_a_comment` + `…_appear_in_settings_field_order` pair; the PRD-010 group lacked one only because STORY-002 deferred `.env.example` to this story. Their mutation check is recorded above.
5. **Curly quotes normalized.** The first draft of the new copy used typographic quotes around *"yes"*; the README uses straight quotes throughout, so six characters were normalized.

## Findings (not fixed — outside this story)

- **`README.md` links to `SECURITY.md`, which does not exist in the repository.** The link-checker's self-check against `HEAD:README.md` found it, so it predates this story (`git log -- SECURITY.md` is empty — the file has never been tracked). The README's *Security* section tells a reporter to "see SECURITY.md for details", and that link 404s on GitHub today. Fixing it means either writing a security policy or rewording the section, which is a decision for the repository owner, not a documentation edit this story can make on its own.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_config.py` | `test_env_example_documents_every_multiturn_pipeline_var_with_a_comment` — each of the four settings appears in `.env.example` with a comment line directly above it; `test_env_example_multiturn_pipeline_vars_appear_in_settings_field_order` — the four appear in `Settings` declaration order |

No test reads `README.md`, so the prose edits are covered by the link/anchor checker and the manual checks above rather than by the suite.

## Not Verified

The plan's first two E2E items asked for a rendered Markdown preview and for clicking each link in it. This session has no browser or preview surface, so the structures a render would expose were checked mechanically instead: fence markers balanced (50), both edited tables column-consistent, and every link resolved by the checker. **No human visual render of the README was performed.**

## Acceptance Criteria

- [x] *Multi-turn context* moved from the roadmap (unchecked item **and** the "intended direction" section) to shipped behaviour, describing: history from answered exchanges only; history always redacted; oldest exchanges dropped past the limits with a note on the reply; the pipeline refuses oversized conversations; `CHAT_HISTORY_ENABLED=false` keeps single-turn
- [x] *Limitations*: "No multi-turn context" removed; characters not tokens; patterns on the newest user turn (provisional until PRD-011); PII audit fields describe the new turn and output only (D7); the first send of two new chats with the same text within 24 h is still a duplicate; redacted history can make answers less precise
- [x] `POST /query` documentation shows the context-limit `BLOCKED` body, noted as the only new outcome, and the configuration table lists all four settings with defaults and purpose
- [x] `.env.example` carries the four settings with defaults and one-line comments in a `# Multi-turn pipeline (PRD-010)` group
- [x] `pre-prds/PRE-PRD-010-multi-turn-pipeline.md` reads `status: promoted` with `prd:` pointing at this PRD (verified, unchanged); every new or changed README anchor link resolves
- [x] All tasks completed
- [x] STORY-015 latency numbers recorded where the README discusses cost; STORY-014's result where it discusses the executor
- [x] PRD-014 is not described as shipped — the "intended direction" line is untouched and the added sentence names what does not exist
- [x] No production code changed (`app/`, `chat_ui/` untouched)
- [x] Full suite green
- [x] Follows existing README patterns (voice, anchors, cited tests)
