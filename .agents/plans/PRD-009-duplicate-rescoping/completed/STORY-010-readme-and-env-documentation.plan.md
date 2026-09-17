---
story: STORY-010
prd: PRD-009
slug: readme-and-env-documentation
title: "README documents the rescoped control, its trade-offs and the resolved multi-turn blocker; .env.example confirmed unchanged"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-009-duplicate-rescoping
created: 2026-09-17
---

# Plan: README documents the rescoped control, its trade-offs and the resolved multi-turn blocker; .env.example confirmed unchanged

## Summary

This is a documentation-only story that closes PRD-009. `README.md` still describes the duplicate control as it was before the epic: global, keyed on text alone, and the reason multi-turn is deferred. It also says a failed duplicate check fails open, which was never true. The README is edited in five places:

1. The Features table's *Duplicate blocking* row.
2. A new `### Duplicate detection scope` note under Features, stating what counts and what does not, T1 with PRD-013 as its owner, and T8.
3. The *Multi-turn context* section, whose blocker becomes the pipeline (PRD-010).
4. The *OpenAI-compatible endpoint* "what gets hashed" bullet, which is now answered.
5. The fail-open sentence under *The database is a hard dependency of every request*, corrected to 500 / fail-closed.

`.env.example` and `app/config.py` are verified untouched. That is recorded as evidence for the report, not assumed. No production code or test changes. Links and anchors are verified with a throwaway script, and the full suite is run to confirm nothing reads the README.

## User Story

As a security admin
I want the weakened and strengthened cases written down where operators read, with their mitigations
So that the rescoping is a decision I can review and not a regression I discover

## Story Reference

- Story file: `.agents/stories/PRD-009-duplicate-rescoping/STORY-010-readme-and-env-documentation.md`
- PRD: `.agents/PRDs/PRD-009-duplicate-rescoping/PRD.md`: Section 4 (Documentation), Section 5 (story 8), 6.3 (what-counts table), 7 (F7), 9.2 (T1–T8), 9.3, 12 (Phase 4), 15 (*Observed discrepancy*)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (docs only; story `type: technical`) |
| Complexity | LOW |
| Systems Affected | `README.md` only. Verified untouched: `.env.example`, `app/config.py`. Possibly staged: `pre-prds/PRE-PRD-009-duplicate-rescoping.md` (see Task 6 gate) |
| Story | STORY-010 |
| PRD | PRD-009 |
| Epic Branch | `epic/PRD-009-duplicate-rescoping` (commit directly on this branch) |
| Dependencies | STORY-007 ✅ done (`c734df9`), STORY-009 ✅ done (`29e471e`) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | I scanned `.agents/skills/` and read `frontend-design/SKILL.md`. It covers UI visual design. The story's `skills: []` is empty and its Technical Notes say `frontend-design` does not cover documentation. No rule applies. | — |

---

## Facts the design depends on (verified during planning)

| Fact | Evidence |
|---|---|
| **No test reads `README.md` or `pre-prds/`.** `tests/test_reports_service.py` builds fixture `.agents` files only. README appears in test comments and docstrings, never in an assertion. | grep over `tests/`. Mentions only at `tests/test_query_outcomes_regression.py:191-193` (docstring), `tests/test_two_instance_smoke.py:462-466` (comment) and `tests/test_dedup_key.py:80` (turn text). |
| **No link or anchor checker exists** in `tests/`, `scripts/` or CI. | `scripts/` holds only `manage_users.py` and `migrate_to_turso.py`. |
| **Duplicate storage failure → 500.** | `app/routers/query.py:101-102` `except DuplicateCheckError as exc: raise HTTPException(status_code=500, ...)`; `tests/test_query_router.py:207` `test_duplicate_check_storage_failure_returns_500` asserts `500` and `"Duplicate lookup failed"` in the detail, with `call_openrouter` patched to fail if reached. |
| **The key over a conversation.** | `app/services/duplicate_checker.py:56` `dedup_key(user_id: str, turns: Sequence[DedupTurn]) -> str` returns `_sha256_json([DEDUP_KEY_VERSION, user_id, hash_prompt(last.content), prefix_hash])` (:68). `DEDUP_KEY_VERSION = "v1"` (:47). `check_duplicate(user_id: str, key: str)` (:29). The 24h window is inline `timedelta(hours=24)` (:30), not a setting. |
| **The lookup.** | `app/db/database.py:786-792`: `WHERE user_id = ? AND dedup_key = ? AND timestamp >= ? AND success = 1 AND was_duplicate_blocked = 0 AND denied_permission IS NULL ORDER BY timestamp ASC LIMIT 1`. |
| **Every what-counts row has an end-to-end test** (safe to state in the README). | `tests/test_duplicate_scope.py`: two users :617; same-user repeat :196; after 502 :486; after input redactor :517; after output redactor :548; after model/BYOK/permission denial :352/:395/:429; after foreign session :581; pattern block counts :254; D3 chaining :301; pre-upgrade NULL row :665; whitespace :750. |
| **No setting added by this epic.** | `git log --oneline main..HEAD -- app/config.py .env.example` → empty. `Settings` and `.env.example` both carry the same 20 names, and none is duplicate- or dedup-related. |
| **Pre-PRD already promoted, but untracked.** | `pre-prds/PRE-PRD-009-duplicate-rescoping.md` frontmatter: `status: promoted`, `prd: .agents/PRDs/PRD-009-duplicate-rescoping/PRD.md`. `git ls-files pre-prds` → empty, and `git log --all -- pre-prds` → empty. The directory has never been committed. |
| **PRD-013 has no PRD folder.** | `.agents/PRDs/` ends at `PRD-009-duplicate-rescoping`, and PRD-013 exists only as the untracked `pre-prds/PRE-PRD-013-audit-and-usage-limits.md`. The README therefore **names PRD-013 in text and does not link it**, because a link to an untracked file would be broken on GitHub. |
| **No story report records the `.env.example` confirmation yet.** | STORY-002 report :85 and STORY-007 report :134 mention it in passing. STORY-007's says "STORY-010 confirms it formally". |
| **README line map** (current, pre-edit). | Features row :153; Features table ends :160; fail-open sentence :329; duplicate API example :433-443; roadmap multi-turn checkbox :629 (**do not touch**); Multi-turn context :637-643; OpenAI "what gets hashed" bullet :659. |

---

## Patterns to Follow

### README voice: concrete, states the reason, bold lead-in sentence
```
// SOURCE: README.md:306
**`CHAT_HISTORY_ENABLED=false` is a supported configuration, not a degraded mode.** With it off, no transcript row is written and none is read, the session rail is *absent* rather than empty, ...
```

### Naming a trade-off and who owns it, without marketing
```
// SOURCE: README.md:318-323
**What is still not included.** The database blocker is gone; the deployment topology is not built:

- **No load balancer or health-check configuration** is provided or documented here.
...
Treat multi-instance as *unblocked*, not *delivered*.
```

### Citing a test as proof in prose
```
// SOURCE: README.md:316
**This is proven rather than assumed.** `tests/test_two_instance_smoke.py` starts two application processes against one database and asserts that ...
```

### In-page anchors (GitHub slug: lowercase, punctuation dropped, spaces → hyphens)
```
// SOURCE: README.md:31, 259, 629
- [Quickstart — Local](#quickstart--local)
See [Multi-turn context](#multi-turn-context) for why, and what it would cost to change.
- [ ] [Multi-turn context](#multi-turn-context) — sending a chat's history to the model, ...
```

### Relative link into `.agents/`
```
// SOURCE: .agents/PRDs/PRD-009-duplicate-rescoping/PRD.md:18
The README's [Multi-turn context](../../../README.md#multi-turn-context) section ...
```
From `README.md` the path is `.agents/PRDs/PRD-009-duplicate-rescoping/PRD.md#92-threat-reasoning`, the slug of `### 9.2 Threat reasoning`.

### Commit messages on this epic
```
// SOURCE: git log (7525223, 29e471e, 7f528ff)
docs(readme): STORY-022 the persistence model the code actually has
test(duplicates): STORY-009 reporting invariance and six-outcome regression on the finished epic
chore(PRD-009): update STORY-009 status + index
```

### Error handling
Not applicable. No code changes. The "error" here is a README claim that contradicts tested behaviour, and it is fixed by citing the test that asserts the real behaviour (see the voice pattern above).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `README.md` | UPDATE | Features row; new `### Duplicate detection scope`; Multi-turn context rewrite; OpenAI bullet answered; fail-open sentence corrected; duplicate API example sentence aligned |
| `.env.example` | **NONE** (verify only) | AC 4: confirmed untouched, evidence recorded in the report |
| `app/config.py` | **NONE** (verify only) | AC 4 |
| `pre-prds/PRE-PRD-009-duplicate-rescoping.md` | **NONE** to content (already `promoted`); staging is **gated** (Task 6) | AC 5 |
| `C:\Users\tobip\AppData\Local\Temp\claude\...\scratchpad\check_readme_links.py` | CREATE (scratchpad, **not committed**) | AC 5 link/anchor verification |

---

## Tasks

Execute in order. Each task is atomic and verifiable. The exact text below is the intended copy. `/implement` may tighten the wording but must keep every fact and link.

### Task 1: AC 1 — Features row and the *Duplicate detection scope* note

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**:
  - Replace line 153 with:
    ```
    | **Duplicate blocking** | Exact-match (word-for-word) detection of a prompt the **same account** already had answered within a rolling 24-hour window. Scoped per user, never across users — see [Duplicate detection scope](#duplicate-detection-scope). |
    ```
  - After the Features table (after line 160, before the `---` at :162), insert the subsection:
    ```markdown

    ### Duplicate detection scope

    A duplicate is **the same account sending the same prompt, in the same conversation context, within 24 hours of a prior query**. The account is the authenticated identity, never the request body's `user_id`, and the prompt is the raw text, never the redacted one.

    **What counts as a prior query:**

    - A request that reached the model and succeeded.
    - A request blocked by the suspicious-pattern check — resending an injection attempt is still held.

    **What does not:**

    - **Failures.** An upstream `502` or a redaction `500` produced no answer, so retrying the same prompt goes through.
    - **Policy denials.** A disallowed model, BYOK without `query:byok`, or a foreign `session_id`: the corrected retry goes through.
    - **Duplicate blocks.** A held repeat does not extend the window. A prompt is allowed again 24 hours after it was *answered*, however many times it was held in between.
    - **Other users' rows.** Two accounts sending the same text are both answered, and nobody can hold a colleague's prompt for a day by sending it first.
    - **Rows written before this release.** They carry no duplicate key and never match.

    Excluding a row from the lookup does not remove it from the record: every one of these attempts still writes its audit row, and `GET /audit`, `GET /stats` and the admin console report exactly what they did before.

    Two weaknesses are accepted on purpose:

    - **One repeat per account.** Because the scope is per user, N accounts can each send the same prompt once per window. Accounts are admin-provisioned with `scripts/manage_users.py`, which bounds N; per-user rate limits and token budgets that close the gap are planned as PRD-013 and are not built yet.
    - **A one-off gap right after upgrading.** Rows written before this release have no key, so a prompt answered in the 24 hours before the upgrade can be sent once more after it. The gap closes on its own 24 hours after deploy; no backfill is run.

    Every case above has an end-to-end test in `tests/test_duplicate_scope.py`. The full threat reasoning — including what the rescoping made stronger — is in [PRD-009, Section 9.2](.agents/PRDs/PRD-009-duplicate-rescoping/PRD.md#92-threat-reasoning).
    ```
  - Note on wording: the story ACs name the trade-offs "T1" and "T8". Operators do not have the PRD's numbering, so the README states them in words and the PRD link carries the numbers. If a reviewer wants the tags visible, append `(T1)` / `(T8)` to the two bold lead-ins. This is a cosmetic choice, not a fact change.
  - "24 hours after it was *answered*" was settled during planning. Within one window, a repeat is blocked and writes a non-qualifying row. So each 24h cycle has exactly one qualifying occurrence, and `ORDER BY timestamp ASC LIMIT 1` returns it. "First answered" (the SQL) and "last answered" (PRD 9.2 T5) are therefore the same row, and the README says neither. Test proof: `test_story_4_row_blocked_at_23h_no_longer_keeps_prompt_blocked_at_25h_d3` (:301) and `test_success_at_24h01m_no_longer_blocks_the_same_prompt` (:730).
- **Mirror**: `README.md:300-310` (bold lead-in sentences, reasons stated), `README.md:318-323` (named gaps)
- **Validate**: `grep -n "Duplicate detection scope\|duplicate-detection-scope\|PRD-013\|92-threat-reasoning" README.md` → the row, heading, two links and the PRD-013 mention all present. The anchor is checked in Task 7.

### Task 2: AC 2 — *Multi-turn context* no longer names duplicate detection as the blocker

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Replace the paragraphs at :639, :641 and :643 (keep the `### Multi-turn context` heading so `#multi-turn-context` still resolves from :259 and :629):
  ```markdown
  A chat session today is a **saved transcript, not a conversation the model remembers**. Every send is one user turn, alone: the stored history is rendered on your screen and is never added to the prompt. Sending it is the natural next step, and one prerequisite for it is now in place.

  **Duplicate detection is no longer the blocker.** It was: the check used to hash the whole prompt against a global 24-hour window, so *"yes"*, *"go on"* and *"thanks"* would have been held as duplicates of each other across every user. The key is now defined over a conversation rather than a string. `dedup_key(user_id, turns)` in `app/services/duplicate_checker.py` combines the user, the last user turn, and a hash of every turn before it; a `POST /query` send is the one-turn case, with an empty prefix. The same *"yes"* from another user, or after a different exchange, is a different key. See [Duplicate detection scope](#duplicate-detection-scope).

  **What remains is the pipeline, owned by PRD-010.** `run_query`, `QueryRequest` and the chat UI still accept one prompt rather than a list of turns, so nothing yet feeds the key a real history. That work passes the conversation to the same function; it does not redefine what a duplicate is. `chat_messages` is deliberately shaped so its input is a read away. Tool-role turns are refused by the key rather than guessed at, so tool calling will have to decide how they count.
  ```
- **Do not** edit the roadmap checkbox at :629 (Technical Notes: still unshipped).
- **Mirror**: current :639-643 voice and length
- **Validate**: `sed -n '/^### Multi-turn context/,/^### OpenAI-compatible endpoint/p' README.md | grep -n "breaks duplicate detection\|global 24-hour"`. It must print only the historical "used to hash … global 24-hour" sentence, and no "It breaks duplicate detection" lead-in. `git diff README.md | grep "^[-+]- \[ \] \[Multi-turn"` prints nothing.

### Task 3: AC 2 — OpenAI-compatible endpoint's "what gets hashed" answered

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Replace the bullet at :659 with:
  ```markdown
  - ~~What gets hashed for duplicate detection in a multi-turn conversation.~~ **Answered:** the last user turn plus a hash of the preceding turns, per user — the key `POST /query` already uses, with a non-empty prefix. An agent that resends an unchanged history and repeats its last turn is a duplicate; one whose history has moved on is not. See [Multi-turn context](#multi-turn-context).
  ```
  If strikethrough reads as noisy in review, drop the `~~` and keep the **Answered:** lead-in. Keep "Open design questions:" as the list header, since the other two bullets are still open.
- **Mirror**: README list style at :658-660
- **Validate**: `grep -n "Answered:\*\* the last user turn plus a hash of the preceding turns, per user" README.md` → one hit

### Task 4: AC 3 — correct the fail-open sentence

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Replace line 329 with:
  ```markdown
  There is no exception for the duplicate check. A storage failure during the duplicate lookup returns `500`, and the query never reaches the model — the check fails closed, as `tests/test_query_router.py::test_duplicate_check_storage_failure_returns_500` asserts. An earlier version of this section said the opposite; the code never did. Letting a failed check through would turn every database outage into a window with no duplicate control, which would be a security decision, not a resilience detail. Resilience work is the first item on the roadmap beyond this migration.
  ```
- **Mirror**: README :316 (cite the test as proof)
- **Validate**: `grep -n "lets the query through" README.md` → no hits. `grep -n "test_duplicate_check_storage_failure_returns_500" README.md` → one hit. `grep -n "def test_duplicate_check_storage_failure_returns_500" tests/test_query_router.py` → one hit (the name is real).

### Task 5: Keep the duplicate API example consistent (scoped supporting edit)

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: The sentence at :435 ("Send the exact same prompt again within 24 hours:") is now wrong for a second account or after a failure. Replace it with `Send the exact same prompt again from the same account, within 24 hours of it being answered:`. After the JSON block (:443), add one line: `` `first_query_at` is the earliest qualifying occurrence in the window — an answered or pattern-blocked send, never a failure or an earlier held repeat. See [Duplicate detection scope](#duplicate-detection-scope). `` Response shape unchanged (PRD Section 10).
- **Why in scope**: PRD Section 10 states the new `first_query_at` meaning, and AC 1's note would otherwise contradict the API reference ten screens down. Record it under *Deviations* in the report as a supporting edit beyond the listed ACs.
- **Validate**: `grep -n "from the same account, within 24 hours" README.md` → one hit

### Task 6: AC 4 + AC 5 — `.env.example`, config, and the pre-PRD

- **Files**: `.env.example`, `app/config.py`, `pre-prds/PRE-PRD-009-duplicate-rescoping.md`
- **Action**: VERIFY (no edits)
- **Implement**: run and capture the output verbatim for the report's AC 4 evidence:
  ```bash
  git log --oneline main..HEAD -- app/config.py .env.example      # expect: empty
  git diff --stat main -- app/config.py .env.example               # expect: empty
  git status --short -- .env.example app/config.py                 # expect: empty
  grep -inE "dup|dedup|window" .env.example app/config.py          # expect: no hits
  ```
  In the report, state explicitly:
  - no setting was added by PRD-009;
  - none is needed, because the 24h window is inline `timedelta(hours=24)` at `app/services/duplicate_checker.py:30`, unchanged and deliberately not configurable (PRD 4 Out of Scope, 9.3);
  - `.env.example` is untouched.

  For the pre-PRD, run `sed -n 1,12p pre-prds/PRE-PRD-009-duplicate-rescoping.md` and confirm `status: promoted` and `prd: .agents/PRDs/PRD-009-duplicate-rescoping/PRD.md`. No content edit.
- **Gate (ask the user before committing):** `pre-prds/` has never been tracked (`git ls-files pre-prds` is empty), and it holds eight briefs plus a README. The "promoted" state exists only in the working tree. Ask the user one question: *commit `pre-prds/` with this story (recommended: the whole directory, because `PRD-009/PRD.md` links both `pre-prds/PRE-PRD-009-...md` and `pre-prds/README.md`, and both links are broken in git until it is tracked), commit only `PRE-PRD-009`, or leave `pre-prds/` untracked?* Do not stage it without an answer. Whatever is chosen goes in the report.
- **Validate**: all four commands print nothing; the pre-PRD frontmatter shows `promoted` + the path

### Task 7: AC 5 — every added or changed link and anchor resolves

- **File**: `<scratchpad>/check_readme_links.py`
- **Action**: CREATE (scratchpad only; never committed)
- **Implement**: a small script that:
  1. Parses `README.md` headings outside fenced code blocks and builds GitHub slugs (`lowercase` → drop every char not in `[a-z0-9 _-]` → spaces to `-`, then de-duplicate with `-1`, `-2` suffixes).
  2. Checks every `](#anchor)` in `README.md` against those slugs.
  3. For every `](relative/path#anchor)` link that is not `http(s)`, checks the file exists from the repo root and, if there is an anchor, that the target Markdown file has a heading with that slug.
  4. Prints each failure and exits non-zero if any fail.

  Self-check first: run the script against the **pre-edit** README (`git show HEAD:README.md`). Every existing Table of Contents link must pass, including `#quickstart--local` and `#persistence--deployment`. That proves the slug function before it is trusted on the new anchors.
- **Validate**: `python <scratchpad>/check_readme_links.py` → 0 failures. It must at least cover `#duplicate-detection-scope` (×4), `#multi-turn-context` (×4), and `.agents/PRDs/PRD-009-duplicate-rescoping/PRD.md#92-threat-reasoning`. Also confirm on the pre-PRD side that `.agents/PRDs/PRD-009-duplicate-rescoping/PRD.md` exists (its `prd:` path).

### Task 8: Full suite, change audit, commit

- **Action**: VERIFY + COMMIT
- **Implement**:
  1. Make sure the libSQL dev server is up: `docker ps --filter name=harness-libsql-dev`. If mass fixture errors appear, restart the container and re-run; do not bisect, since the dev server degrades under repeated suites.
  2. `pytest tests/ -q`, expecting all green. `tests/test_reports_service.py` and `tests/test_config.py` (which reads `.env.example`) must pass unmodified.
  3. Run `git diff --stat`. The only tracked change is `README.md`, plus `pre-prds/` if the Task 6 gate said so.
  4. Run `git diff README.md | grep "^[-+].*\[ \] \[Multi-turn"`, which should print nothing because the roadmap checkbox is untouched.
  5. Commit on `epic/PRD-009-duplicate-rescoping`: `docs(readme): STORY-010 duplicate detection scope, trade-offs and the resolved multi-turn blocker`, with the attribution trailer from the session.
- **Validate**: suite green, and the diff is limited as above

---

## Risks & Mitigations

| # | Risk | Mitigation |
|---|---|---|
| 1 | **The README overstates the window semantics.** "24h after first vs last answered occurrence" is easy to get subtly wrong. | Task 1 requires reading the D3 test (:301) and PRD 9.2 T5 before fixing the sentence. Every claim in the note maps to a named test in `tests/test_duplicate_scope.py`. |
| 2 | **A link to an untracked or non-existent file.** PRD-013 has no PRD folder, and `pre-prds/` is untracked. | PRD-013 is named in text and not linked. The only new cross-file link targets the tracked `PRD-009/PRD.md`. Task 7's script checks file existence and anchors. |
| 3 | **Wrong GitHub slug for `9.2 Threat reasoning`** (the dot). | The slug function is self-checked on existing TOC anchors before use. Expected slug `92-threat-reasoning`. |
| 4 | **The roadmap multi-turn checkbox is edited by accident.** | Explicit do-not-touch in Task 2, and a diff grep in Task 8. |
| 5 | **Committing `pre-prds/` without consent.** It is user-authored planning content, untracked since creation. | Task 6 gate: ask first, record the choice. |
| 6 | **Copying the PRD threat table into the README** (Technical Notes forbid it). | The note gives the operator-facing condensed version: what counts, what does not, T1 and T8. It links 9.2 for the rest. |
| 7 | **Suite flakes from the libSQL dev server.** | Restart the container on mass fixture errors, per the known degradation. |

---

## End-to-End Tests

- [ ] Render `README.md` (VS Code Markdown preview or GitHub branch view). The Features table row and the `Duplicate detection scope` subsection display correctly, and both lists render as lists.
- [ ] In the rendered preview, click every new or changed link: `Duplicate detection scope` from the Features row, Multi-turn context, the API example and the OpenAI bullet; `Multi-turn context` from the OpenAI bullet; `PRD-009, Section 9.2`. Each lands on the right heading.
- [ ] `python <scratchpad>/check_readme_links.py` → 0 failures (also passes on `HEAD:README.md` as the self-check)
- [ ] `grep -n "lets the query through" README.md` → none
- [ ] `git log --oneline main..HEAD -- app/config.py .env.example` → empty
- [ ] `pytest tests/ -q` → green

---

## Validation

```bash
python "<scratchpad>/check_readme_links.py"
grep -n "lets the query through" README.md                        # expect nothing
grep -n "duplicate-detection-scope\|92-threat-reasoning\|PRD-010\|PRD-013" README.md
git log --oneline main..HEAD -- app/config.py .env.example        # expect nothing
git diff --stat                                                    # README.md only (+ pre-prds/ if approved)
pytest tests/ -q
```

---

## Acceptance Criteria

(Copied from story `STORY-010`)

- [ ] Given `README.md`, when it is read, then the Features table's *Duplicate blocking* row says per-user, exact-match, rolling 24h, and a short "Duplicate detection scope" note (under Features or Security) states:
  - what counts as a prior query: successes and suspicious-pattern blocks
  - what does not: failures, policy denials, duplicate blocks, other users' rows, pre-upgrade rows
  - trade-off T1 (one repeat per account) and its owner, PRD-013
  - the one-off post-upgrade gap T8
- [ ] Given the *Multi-turn context* section, when it is read, then it no longer names duplicate detection as the blocker. It states that the key is defined over a conversation and that multi-turn is now blocked only on the pipeline (PRD-010). The *OpenAI-compatible endpoint* bullet asking "what gets hashed" is answered: the last user turn plus a hash of the preceding turns, per user.
- [ ] Given the sentence in *The database is a hard dependency of every request* claiming that a duplicate-check storage failure "lets the query through", when this story lands, then it is corrected to the tested behaviour (500, fail-closed), citing `test_duplicate_check_storage_failure_returns_500`, per PRD Appendix *Observed discrepancy*.
- [ ] Given `.env.example` and `app/config.py`, when they are checked, then no setting was added by this epic and none is needed. The story report records this explicitly, and `.env.example` is untouched.
- [ ] Given every anchor and relative link added or changed, when they are followed, then each resolves (for example `#multi-turn-context`). `pre-prds/PRE-PRD-009-duplicate-rescoping.md` reads `status: promoted` with its `prd:` path set, and the full suite is green (README-reading tests such as `tests/test_reports_service.py` unaffected).
- [ ] All tasks completed
- [ ] Roadmap *Multi-turn context* checkbox untouched
- [ ] No production code or test file changed
- [ ] Follows existing README patterns (voice, anchors, cited tests)
