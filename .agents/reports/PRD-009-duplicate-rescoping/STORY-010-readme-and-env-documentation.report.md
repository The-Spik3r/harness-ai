---
story: STORY-010
prd: PRD-009
plan: .agents/plans/PRD-009-duplicate-rescoping/completed/STORY-010-readme-and-env-documentation.plan.md
epic_branch: epic/PRD-009-duplicate-rescoping
commit: 599f9df
status: COMPLETE
completed: 2026-09-17
---

# Implementation Report — STORY-010: README documents the rescoped control, its trade-offs and the resolved multi-turn blocker; .env.example confirmed unchanged

**Plan**: `.agents/plans/PRD-009-duplicate-rescoping/completed/STORY-010-readme-and-env-documentation.plan.md`
**Epic Branch**: `epic/PRD-009-duplicate-rescoping`
**Commit**: `599f9df`

## Summary

This story brings `README.md` in line with the duplicate control PRD-009 shipped. It is documentation only; no production code or test changed.

- **Features.** The *Duplicate blocking* row now says per-account, exact-match, rolling 24h. It links a new `### Duplicate detection scope` note that covers:
  - what counts as a prior query, and what does not;
  - the two accepted weaknesses: one repeat per account (T1, owned by PRD-013) and the one-off post-upgrade gap (T8);
  - a link to PRD-009 Section 9.2 for the full threat reasoning.
- **Multi-turn context.** Duplicate detection is no longer named as the blocker. The key is defined over a conversation, and what remains is the pipeline (PRD-010). The roadmap checkbox is untouched.
- **OpenAI-compatible endpoint.** The "what gets hashed" question is answered: the last user turn plus a hash of the preceding turns, per user.
- **The database is a hard dependency of every request.** The sentence claiming a duplicate-check storage failure "lets the query through" is corrected to the tested behaviour: `500`, fail-closed, citing `test_duplicate_check_storage_failure_returns_500`.
- **API reference.** The duplicate example now says "same account" and defines `first_query_at` as the earliest qualifying occurrence. This is a supporting edit beyond the listed ACs (see Deviations).

`.env.example` and `app/config.py` were verified untouched (AC 4 evidence below). With the user's approval, `pre-prds/` was committed for the first time.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | AC 1: Features row + `### Duplicate detection scope` note | `README.md` | ✅ |
| 2 | AC 2: Multi-turn context names the pipeline (PRD-010), not duplicate detection | `README.md` | ✅ |
| 3 | AC 2: OpenAI endpoint "what gets hashed" answered | `README.md` | ✅ |
| 4 | AC 3: fail-open sentence corrected to 500 / fail-closed, test cited | `README.md` | ✅ |
| 5 | Duplicate API example aligned (same account, `first_query_at` meaning) | `README.md` | ✅ |
| 6 | AC 4 + AC 5: `.env.example`/config verified; pre-PRD verified `promoted`; `pre-prds/` staging gate asked | — (evidence), `pre-prds/` | ✅ |
| 7 | AC 5: link/anchor checker, self-checked on `HEAD:README.md`, run on the edited README | scratchpad (not committed) | ✅ |
| 8 | Full suite, change audit, commit | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| App import (`python -c "from app.main import app"`) | ✅ `OK` |
| Frontend lint | N/A. The repo has no `frontend/`; the chat UI is Reflex (`chat_ui/`), and this story does not touch it. |
| Health smoke | ✅ `python app.py` from the edited tree, on port 8765 against the local libSQL dev server (`RBAC_ENABLED=false`, `PII_REDACTION_ENABLED=false`, never the remote `.env` database). `GET /health` → `{"status":"ok"}`, then stopped. |
| Tests | ✅ `1965 passed, 25 skipped` (`pytest tests/ -q`, 140.61s) |
| E2E | ✅ 6/6 |
| Link/anchor checker | ✅ Every link this story added or changed resolves (see AC 5). One failure predates this story (see Deviations). |

**Suite note.** The first full run gave `1964 passed, 25 skipped, 1 error`. The error was a `StorageError` from `app/db/database.py:618` in the fixture of `tests/test_reporting_invariance.py::test_stats_and_summary_snapshot_report_the_same_figures_on_the_fixed_seed`. That test passed when re-run alone (`1 passed`). This matches the known dev-server degradation after hours of use (the container had been up 4 hours). I restarted `harness-libsql-dev` and re-ran the full suite: `1965 passed, 25 skipped`, no errors. No test reads the README, so the change could not have caused it.

## Acceptance Criteria Evidence

### AC 1 — Features row and the *Duplicate detection scope* note

- `README.md:153`: "detection of a prompt the **same account** already had answered within a rolling 24-hour window. Scoped per user, never across users — see [Duplicate detection scope](#duplicate-detection-scope)."
- `README.md:162` `### Duplicate detection scope`, directly under the Features table:
  - **Counts:** a request that reached the model and succeeded; a suspicious-pattern block.
  - **Does not count:** failures (`502`, redaction `500`); policy denials (disallowed model, BYOK without `query:byok`, missing permission, foreign `session_id`); duplicate blocks; other users' rows; rows written before this release.
  - **T1:** "N accounts can each send the same prompt once per window … per-user rate limits and token budgets that close the gap are planned as PRD-013 and are not built yet."
  - **T8:** "Rows written before this release have no key, so a prompt answered in the 24 hours before the upgrade can be sent once more after it. The gap closes on its own 24 hours after deploy."
- Each case maps to a test in `tests/test_duplicate_scope.py`: `:196`, `:254`, `:301`, `:352`, `:395`, `:429`, `:486`, `:517`, `:548`, `:581`, `:617`, `:665`, `:730`.

### AC 2 — Multi-turn context and the OpenAI "what gets hashed" bullet

- **The old blocker is gone.** "It breaks duplicate detection" no longer appears. In the section, `grep "breaks duplicate detection\|global 24-hour"` matches only the past-tense sentence "the check used to hash the whole prompt against a global 24-hour window".
- **New text:**
  - "**Duplicate detection is no longer the blocker.** … The key is now defined over a conversation rather than a string. `dedup_key(user_id, turns)` … a `POST /query` send is the one-turn case, with an empty prefix."
  - "**What remains is the pipeline, owned by PRD-010.**"
- **OpenAI bullet:** "~~What gets hashed for duplicate detection in a multi-turn conversation.~~ **Answered:** the last user turn plus a hash of the preceding turns, per user — the key `POST /query` already uses, with a non-empty prefix."
- **Roadmap checkbox:** `git diff README.md | grep "^[-+].*\[ \] \[Multi-turn"` → nothing, so it is untouched.

### AC 3 — Fail-open sentence corrected

- `grep -c "lets the query through" README.md` → `0`.
- New text: "There is no exception for the duplicate check. A storage failure during the duplicate lookup returns `500`, and the query never reaches the model — the check fails closed, as `tests/test_query_router.py::test_duplicate_check_storage_failure_returns_500` asserts."
- Verified against code:
  - `app/routers/query.py:101-102` maps `DuplicateCheckError` → `HTTPException(500)`.
  - `tests/test_query_router.py:207` exists and asserts `500` plus `"Duplicate lookup failed"`.

### AC 4 — `.env.example` and `app/config.py`: no setting added, none needed

Commands run on the epic head. Each printed nothing:

```
$ git log --oneline main..HEAD -- app/config.py .env.example
$ git diff --stat main -- app/config.py .env.example
$ git status --short -- .env.example app/config.py
$ grep -inE "dup|dedup|window" .env.example app/config.py
```

Recorded explicitly:

- **No setting was added by PRD-009.** No epic commit touches `app/config.py` or `.env.example`. Both still carry the same 20 settings.
- **None is needed.** The 24h window is the inline `timedelta(hours=24)` in `check_duplicate` (`app/services/duplicate_checker.py:30`). It is unchanged and deliberately not configurable (PRD-009 Section 4 *Out of Scope*, Section 9.3). The key version `DEDUP_KEY_VERSION = "v1"` is a code constant, not configuration.
- **`.env.example` is untouched.** It is not in `599f9df`, and `tests/test_config.py`'s `.env.example` tests pass unmodified.

### AC 5 — Links resolve, pre-PRD promoted, suite green

- **Checker.** `check_readme_links.py` builds GitHub heading slugs outside code fences, then checks every in-page anchor, every relative file link, and cross-file anchors.
  - *Self-check on `git show HEAD:README.md`:* all 45 pre-existing TOC and in-page links resolve, including `#quickstart--local` and `#persistence--deployment`. The only failure is `SECURITY.md` (see Deviations).
  - *Negative control:* a fake anchor and a missing file both fail.
- **On the edited README:** 51 relative links checked. All pass except the same `SECURITY.md` link.
  - `#duplicate-detection-scope` ×3: Features row, Multi-turn context, API example.
  - `#multi-turn-context` ×3: Chat UI limitation, roadmap, OpenAI bullet.
  - `#openai-compatible-endpoint`, from the Multi-turn context section.
  - `.agents/PRDs/PRD-009-duplicate-rescoping/PRD.md#92-threat-reasoning`: file exists and heading `### 9.2 Threat reasoning` matches.
- **Pre-PRD.** `pre-prds/PRE-PRD-009-duplicate-rescoping.md` reads `status: promoted`, `prd: .agents/PRDs/PRD-009-duplicate-rescoping/PRD.md`, and that path exists. It is now tracked in `599f9df`.
- **Suite.** `1965 passed, 25 skipped`. `tests/test_reports_service.py` and `tests/test_config.py` were unmodified and green.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `README.md` | UPDATE | +35/-7 |
| `pre-prds/` (8 briefs + `README.md`) | CREATE (first commit; content unchanged) | +787 |
| `.agents/plans/PRD-009-duplicate-rescoping/completed/STORY-010-readme-and-env-documentation.plan.md` | CREATE (archived plan) | +335 |
| `.agents/reports/PRD-009-duplicate-rescoping/STORY-010-readme-and-env-documentation.report.md` | CREATE | this file |
| `.agents/stories/PRD-009-duplicate-rescoping/STORY-010-readme-and-env-documentation.md` | UPDATE (frontmatter) | — |
| `.agents/PRDs/PRD-009-duplicate-rescoping/index.md`, `PRD.md` | UPDATE (status, `updated`) | — |
| `.env.example`, `app/config.py` | **unchanged** (verified) | 0 |

## Deviations from Plan

1. **`pre-prds/` committed whole.** The Task 6 gate asked the user, who chose to commit the whole directory (the recommended option). The 9 files went into `599f9df` with their content unchanged. The two `pre-prds/` links in `PRD-009/PRD.md` now resolve in git.
2. **Extra link in Multi-turn context.** The section still links to `#openai-compatible-endpoint` ("That answers the question the OpenAI-compatible endpoint section posed …"). The old text linked there, and the question it answers is posed there. The link resolves.
3. **"A missing permission" added to the policy-denial bullet.** The plan's copy listed model, BYOK and foreign session. The missing-`query:submit` case is also tested (`tests/test_duplicate_scope.py:429`), so the list is complete now.
4. **Task 5 is a supporting edit beyond the listed ACs.** The API example said "Send the exact same prompt again within 24 hours", which contradicts the new note. It now says "from the same account, within 24 hours of it being answered" and defines `first_query_at`. The response shape is unchanged (PRD Section 10).
5. **Anchor counts were ×3, not ×4.** The plan's Task 7 miscounted. `#duplicate-detection-scope` is linked from three places (row, Multi-turn, API example) and `#multi-turn-context` from three (`:259`, roadmap, OpenAI bullet). Every one resolves.
6. **Pre-existing broken link, not fixed.** `[SECURITY.md](SECURITY.md)` in the *Security* section points to a file that does not exist in the repository. It was added in `3d6f83c` and is not a link this story added or changed. It is out of scope and left for a follow-up.
7. **Link checker bug found by its own self-check.** Windows stdin decoded the README in a non-UTF-8 codepage, which broke the em-dash slugs (`#quickstart--local`). The checker now reads stdin bytes as UTF-8, and the self-check passes. The script lives in the scratchpad and is not committed.
8. **E2E render checks were automated, not clicked by hand.**
   - *Structure:* `markdown-it` (CommonMark + tables + strikethrough) confirmed the Features row is still a two-cell table row, the new section renders 3 lists (2 + 5 + 2 items), the strikethrough renders, and the corrected sentences are present.
   - *Link targets:* covered by the checker's GitHub slug rules (validated on the existing TOC). This renderer does not emit heading ids.
9. **Suite re-run after a dev-server restart.** See the suite note under Validation Results.

## Tests Written

None. This story changes documentation only, and there is no new code to test. The plan chose not to add a committed README link test. Link verification was done with the scratchpad checker described under AC 5.

## Acceptance Criteria

- [x] Given `README.md`, when it is read, then the Features table's *Duplicate blocking* row says per-user, exact-match, rolling 24h, and a short "Duplicate detection scope" note (under Features) states what counts (successes, suspicious-pattern blocks), what does not (failures, policy denials, duplicate blocks, other users' rows, pre-upgrade rows), trade-off T1 and its owner PRD-013, and the one-off post-upgrade gap T8
- [x] Given the *Multi-turn context* section, when it is read, then it no longer names duplicate detection as the blocker. It states that the key is defined over a conversation and that multi-turn is blocked only on the pipeline (PRD-010). The *OpenAI-compatible endpoint* "what gets hashed" bullet is answered: the last user turn plus a hash of the preceding turns, per user
- [x] The "lets the query through" sentence is corrected to the tested behaviour (500, fail-closed), citing `test_duplicate_check_storage_failure_returns_500`
- [x] `.env.example` and `app/config.py`: no setting added by this epic, none needed, recorded explicitly above; `.env.example` untouched
- [x] Every anchor and relative link added or changed resolves; `pre-prds/PRE-PRD-009-duplicate-rescoping.md` reads `status: promoted` with its `prd:` path set; full suite green (`tests/test_reports_service.py` unaffected)
- [x] All tasks completed
- [x] Roadmap *Multi-turn context* checkbox untouched
- [x] No production code or test file changed
- [x] Follows existing README patterns (bold lead-ins, stated reasons, cited tests, GitHub anchors)
