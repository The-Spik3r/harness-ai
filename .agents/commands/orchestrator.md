---
description: Take one PRD end-to-end — stories, per-story plan + implement via subagents, GitHub CI as the full suite on a draft PR, PR marked ready
argument-hint: <PRD-ID | path/to/PRD.md>
---

# Orchestrate a PRD (local file workflow, single-branch per epic)

**PRD**: $ARGUMENTS

## Mission

Deliver a whole PRD on its epic branch. You are the **orchestrator**: you create the stories yourself, then for each story launch a **plan subagent** (`plan.md`) and an **implement subagent** (`implement.md`), and verify each subagent did exactly what it should before moving on. The full suite runs in **GitHub CI** on every push of the epic branch (a draft PR opened in Phase 1); you read each run, fix what it finds while the story that caused it is fresh, and mark the PR ready at the end. You never merge.

**Core Philosophy**: Subagents do the work and the orchestrator checks it. You have the context of the whole PRD, so you catch errors that cross stories, and CI tells you which story introduced one. Nobody runs the full suite locally: it takes ~1.5 h on the Windows dev machine and ~5–7 min in CI (the repo is public, so Actions minutes are free).

**Golden Rule — autonomy with one exception**: run start to finish without pausing to report progress. Stop and ask the user (AskUserQuestion) **only** for a genuine ambiguity: a decision that is the user's to make, that neither the PRD, the code nor a sensible default resolves, and where a wrong guess would mean redoing work. Everything else, decide yourself and record it (see "Orchestrator decisions"). Never stop just to inform.

**Model split** (Agent tool `model` param):

| Role | Model | Why |
|------|-------|-----|
| Orchestrator (you) | session model | Holds the PRD-wide context, verifies, fixes carried-over errors |
| Plan subagent | `opus` | The plan carries the design decisions |
| Implement subagent | `sonnet` | Executes a verified plan; cheaper on usage limits |

---

## Phase 0: PREFLIGHT

### 0.1 Resolve the PRD

| Input | Action |
|-------|--------|
| Path to `PRD.md` | Load directly |
| `PRD-NNN` | Resolve to `.agents/PRDs/PRD-NNN-*/PRD.md` |
| Blank | List `.agents/PRDs/`, ask which PRD |

Read the full PRD. Extract `id`, `slug`, `title`, `status`, `base_branch`, `epic_branch` from the frontmatter.

| PRD state | Action |
|-----------|--------|
| `status: done` and every story `done` | STOP: "Nothing to orchestrate" |
| Stories exist under `.agents/stories/{PRD-ID}/` | **Resume**: skip Phase 1 except its push and draft PR (`gh pr view {epic_branch}`; push and create it if missing), continue from the first story not `done` |
| No stories | Full run |

### 0.2 Git state

```bash
git branch --show-current
git status --short
```

| State | Action |
|-------|--------|
| Working tree dirty with changes that belong to no story | STOP: "Stash or commit changes first" |
| Epic branch missing | `git checkout {base_branch} && git pull --ff-only && git checkout -b {epic_branch}` |
| Epic branch exists, not current | `git checkout {epic_branch}` |
| Already on epic branch | Proceed |

After this phase, **nobody switches branches**: not you and not any subagent.

### 0.3 Baseline (from CI, not local)

The baseline is the latest CI run of `{base_branch}`; every merge runs it, so it already exists:

```bash
gh run list --branch {base_branch} --workflow CI --limit 1 --json databaseId,conclusion,headSha,createdAt
# conclusion != success:
gh run view {id} --log-failed
```

Its failures (if any) are the **pre-existing failures**: list them in the brief so no subagent tries to "fix" them, and use them to tell carried-over errors from old ones. If its `headSha` is not the commit the epic branch starts from, or no run exists, note it; the first CI run on the draft PR (Phase 1) is then the effective baseline for anything the stories commit has not touched.

**Fallback (CI unavailable):** run the suite locally in the background and never at the same time as any other pytest — every DB test shares the one libSQL dev server, and two concurrent runs fail each other:

```bash
docker restart harness-libsql-dev >/dev/null && PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider > "{scratchpad}/baseline_suite.log" 2>&1
```

---

## Phase 1: CREATE STORIES (orchestrator, not a subagent)

Follow `.agents/commands/create-stories.md` **phase by phase** yourself. You need the PRD-wide context later, so you do not delegate this step.

While decomposing, collect the PRD's genuine ambiguities: contradictions between sections, requirements that conflict with the real code, and choices the PRD leaves open that change the design. Resolve what the code or a sensible default answers, and record it. Ask the user only about what remains, batched into **one** AskUserQuestion (up to 4 questions) and not spread across the run. Amend the PRD text where it was wrong, and say so in the commit.

Then regenerate and validate the board:

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python .agents/scripts/gen_index.py {PRD-ID}
```

It must print `errors: none`. Commit the stories, the index and any PRD amendments:
`docs({PRD-ID}): stories + index`.

Then push the epic branch and open a **draft** PR, so every later push runs CI:

```bash
git push -u origin {epic_branch}
gh pr create --draft --base {base_branch} --head {epic_branch} --title "Epic/{PRD-ID} {PRD title}" --body-file {scratchpad}/pr_body.md
```

The draft body is short: the PRD summary, a link to the PRD and board, and "in progress — orchestrated; CI is the full suite". Phase 5 replaces it. The repo is public, so the work in progress is visible from here on.

Do not pause for review here; continue to Phase 2.

---

## Phase 2: WRITE THE SUBAGENT BRIEF

Write `{scratchpad}/SUBAGENT_BRIEF.md` from the template below, filling every `{…}`. Every subagent prompt tells it to read the brief first. When you learn a rule during the run (a wrong command, an environmental failure, a convention), **append it to the brief** so later subagents inherit it.

````markdown
# Shared brief for {PRD-ID} subagents (read fully before starting)

You are one subagent in an orchestrated run. An orchestrator verifies your output after you finish. It checks the files, the diff and the tests, so report only what you actually did and saw.

## Repository and branch
- Repo: `{repo path}`. Branch: `{epic_branch}`. It is checked out. **Never** switch or create branches, push, merge, rebase, amend or force anything.
- PRD: `.agents/PRDs/{PRD-dir}/PRD.md`. Stories: `.agents/stories/{PRD-dir}/`. Board: `.agents/PRDs/{PRD-dir}/index.md`.
- Today's date for every `created` / `updated` / `completed` field: **{YYYY-MM-DD}**.

## Commands you follow
- PLAN subagent: follow `.agents/commands/plan.md` phase by phase, skipping nothing (including SCAN SKILLS and UPDATE STORY FILE + index). PLAN ONLY: no application code, tests or docs, and no commits. If you cannot spawn Explore agents, explore with Grep/Glob/Read yourself. The plan must cite real `file:line` references that you opened.
- IMPLEMENT subagent: follow `.agents/commands/implement.md` phase by phase, skipping nothing.
  - The working tree will contain this story's plan plus the story/index edits the planner made. They belong to this story; do not stop for them.
  - Validation for this repo: there is no `frontend/` and no npm lint. Use:
    - `.venv/Scripts/python -c "from app.main import app; print('OK')"`
    - Only if you touched `chat_ui/`: the probe form from `tests/test_chat_ui_startup_guard.py` (cwd `chat_ui/`, `PYTHONPATH="<repo>/chat_ui;<repo>"`, env `DATABASE_URL`, `OPENROUTER_API_KEY`, `ADMIN_TOKEN` set, then `import chat_ui.chat_ui`). Running that test file is usually enough.
  - **Do NOT run the full suite** (user decision: it runs in GitHub CI on every push; the orchestrator reads it). Wherever implement.md or the plan says "full suite", this rule wins. **Never run two pytest processes at once**: every DB test shares the one libSQL server, and concurrent runs fail each other with `no such table`. Leave no background process or timer behind when you finish. Run instead, in one pytest call: every new or modified test file, the existing `tests/test_<module>.py` of every pre-existing module you changed, the tests the plan names, and the guard tests (`test_pii_redaction_integration.py` when you rename or remove a test; `test_untouched_app.py` when you touch app files). Do not add every file that merely imports a changed module. Aim for under ~10 minutes. Record the exact pass/fail/skip counts. In the report write "Full suite: GitHub CI on push (user decision)".
  - Renaming or removing a pre-existing test function: register the old name in `_DELIBERATELY_SUPERSEDED_TESTS` in `tests/test_pii_redaction_integration.py`.
- **Always prefix pytest with `PYTHONUTF8=1`** (the Spanish Windows locale breaks `test_db_isolation_harness.py` otherwise).
- DB tests need the libSQL dev server `harness-libsql-dev` on :8080. If many `db` tests error at fixture setup, run `docker restart harness-libsql-dev` and rerun before suspecting the code. Do not start a second one.
- Pre-existing failures (from the orchestrator's baseline; ignore them, do not fix them): {list from baseline_suite.log, or "none"}.

## Commits (implement subagent)
- Stage files explicitly; never `git add -A` / `git add .`. Never `--no-verify`; if a hook fails, fix the cause and make a new commit. Never push: the orchestrator pushes after it verifies the story.
- End every commit message with exactly: `{trailer}`
- Order: commit code + tests + archived plan + report (with `commit: pending`) as `<type>({PRD-ID}): {STORY-ID} <summary>`. Capture the SHA. Then make one small follow-up `chore({PRD-ID}): {STORY-ID} report; update status + index` that fills the SHA into the report and story frontmatter.

## Editing files
- Use the Edit/Write tools for code. Git Bash heredocs on this machine mangle `\\` escapes inside Python edit scripts.

## Regenerating index.md
After any story frontmatter change, run from the repo root:
`PYTHONIOENCODING=utf-8 .venv/Scripts/python .agents/scripts/gen_index.py {PRD-ID}`
It must print `errors: none`.

## Code conventions (non-negotiable)
- Match the surrounding code: comment density, docstring style (they cite PRD sections and decisions, e.g. "{PRD-ID} D7"), naming, frozen dataclasses for config models, closed vocabularies, and error messages that name the file, the node and the rule.
- Every modified pre-existing test assertion gets a comment citing {PRD-ID} and the decision.
- Do not implement work that belongs to a later story. If the story text conflicts with the PRD or the real code, follow the code's reality, document the deviation in the plan or report, and tell the orchestrator.
{PRD-specific rules, e.g. "pure modules X, Y import no settings and do no I/O"}

## What to return (your final message)
- PLAN subagent: the plan path, a 3–5 line summary, the files to CREATE/UPDATE, one line per AC saying how it is covered, open risks/questions, and confirmation that the story frontmatter (`plan`, `status: in-progress`) and the index were updated.
- IMPLEMENT subagent: the commit SHA(s), the files changed, the exact targeted test counts, each AC with pass/fail and the test that proves it, deviations, and anything left undone. If something failed or you stopped early, say so plainly. Do not report success you did not verify.
````

`{trailer}` is the commit attribution line from the session's instructions (system attribution reminder, CLAUDE.md or memory); fall back to the one in `implement.md`.

---

## Phase 3: STORY LOOP

Process stories **strictly sequentially** in dependency order (lowest ID whose `depends_on` are all `done`). Never run two subagents at once: they share one branch and one working tree.

For each story:

### 3.1 Plan subagent (`model: opus`)

Prompt (adapt, keep every element):

```
Read {scratchpad}/SUBAGENT_BRIEF.md fully first. You are the PLAN subagent for
{STORY-ID} of {PRD-ID}. Run /plan on .agents/stories/{PRD-dir}/{STORY-file}
by following .agents/commands/plan.md. Orchestrator notes for this story:
{decisions from earlier stories that affect it, known traps, or "none"}.
```

### 3.2 Verify the plan (orchestrator)

Before any code is written, check:

- [ ] The plan file exists at `.agents/plans/{PRD-dir}/{STORY-ID}-{slug}.plan.md`
- [ ] Every story AC maps to a task **and** a test
- [ ] Open a sample of the cited `file:line` references: they are real and say what the plan claims
- [ ] The plan does not pull in work from a later story, and does not drop work that this story owns
- [ ] Its design agrees with the PRD and with decisions taken in earlier stories
- [ ] Story frontmatter shows `status: in-progress` and `plan:`; `gen_index.py` prints `errors: none`
- [ ] `git status` shows only the plan, story and index changes (no code)

If the plan is wrong: fix small issues yourself by editing the plan, or resume the same agent with SendMessage and the specific corrections. Never pass a plan you have not checked to the implement subagent.

### 3.3 Implement subagent (`model: sonnet`)

```
Read {scratchpad}/SUBAGENT_BRIEF.md fully first. You are the IMPLEMENT subagent
for {STORY-ID} of {PRD-ID}. Run /implement on {plan path} by following
.agents/commands/implement.md. Orchestrator notes: {plan corrections you made,
traps, or "none"}.
```

### 3.4 Verify the implementation (orchestrator)

Do not trust the report; check the repository:

- [ ] `git log --oneline -3`: the story commit plus the chore SHA commit, with the right messages and trailer
- [ ] `git show --stat {sha}`: only this story's files; no stray edits (diff any unexpected file against HEAD before keeping it)
- [ ] `git status --short` is clean
- [ ] Story frontmatter: `status: done`, `commit`, `report`, archived `plan` path; `gen_index.py` prints `errors: none`
- [ ] The report exists, with exact targeted-test counts and every AC marked with its proving test
- [ ] Read the core of the diff: it implements the ACs and the conventions in the brief (docstrings citing the PRD, comments on modified assertions)
- [ ] **Spot-check** one or two key behaviours yourself with a small script in the scratchpad (written with Write, not `bash -c` quoting), e.g. call the new function on an edge case from the ACs
- [ ] Deviations the subagent reported are acceptable. If one changes what a later story assumes, record it (3.6)

If something is wrong, resume the same agent with SendMessage and list the exact defects, or fix it yourself and commit `fix({PRD-ID}): {STORY-ID} <what>`. Move on only when the story is truly done.

### 3.5 Push and read CI

Once a story passes 3.4, push it: `git push`. CI runs while the next story is being planned, so it costs no wall-clock time. Read the run when you verify the **next** story (or wait with `gh run watch {id} --exit-status` if nothing else is running):

```bash
gh run list --branch {epic_branch} --workflow CI --limit 1 --json databaseId,status,conclusion,headSha
gh run view {id} --log-failed      # only when it failed
```

| CI result | Action |
|-----------|--------|
| Success | Continue |
| A failure also in the baseline (0.3) | Pre-existing; do not fix. If it is a timing test, `gh run rerun {id} --failed` once to confirm it is environmental |
| A new failure | A carried-over error, and `headSha` tells you which story introduced it. Fix it now, while that story is fresh: fix the cause (or register new code in a guard such as a census, with a comment citing the PRD), rerun the affected test files locally, commit `fix({PRD-ID}): …`, push, and read the next run before moving on |
| Passes in CI, fails locally on Windows (or the reverse) | A platform difference: fix the code for both, and record it in the brief |
| CI did not run, or is unavailable | Fall back to the local suite at Phase 4 (see 0.3's fallback) |

Several stories may land between two reads; one run covers all of them. A failure that blocks a later story's plan is fixed before that story is implemented.

### 3.6 Orchestrator decisions

Whenever you resolve a conflict (story vs PRD vs code), correct a story's text, or accept a deviation, record it where the next agents will read it: add a line to the affected later stories' **Technical Notes** (`Orchestrator decision ({STORY-ID} plan): …`), amend the PRD if the PRD was wrong, and append a brief rule if it is general. These edits ride in the next story's commit.

### 3.7 Failures during the loop

| Failure | Action |
|---------|--------|
| Subagent hits the usage limit after writing partial work | Resume it with SendMessage ("continue from where you stopped") |
| Subagent hits the limit before writing anything | Relaunch fresh with the same prompt |
| Subagent stops on "dirty working tree" for files of this story | Resume it: those files belong to the story (see brief) |
| A subagent's targeted run is very slow | Tell it to narrow the set (brief rule); append the lesson to the brief |
| The story itself is ambiguous in a way that changes the design | Resolve it from the PRD or code; ask the user only if it is genuinely theirs (Golden Rule) |
| An unexpected change shows up in the tree that no agent claims | Back it up to the scratchpad, diff against HEAD, then restore it, and tell the user in the final output |

---

## Phase 4: FINAL CI RUN

When every story is `done` and pushed, the CI run of the last commit is the final suite. Wait for it rather than polling in a loop:

```bash
gh run list --branch {epic_branch} --workflow CI --limit 1 --json databaseId,headSha,status
gh run watch {id} --exit-status          # in the background; its exit is the notification
gh run view {id} --log-failed            # only when it failed
```

Check that the run's `headSha` is the epic branch's HEAD; if it is not (a push did not trigger, or a later one is queued), wait for the right one. If the user asks how it is going, `gh run view {id}` shows the step and its time.

**Fallback (CI unavailable):** run the suite locally in the background, with nothing else using the libSQL server, as in 0.3's fallback, logging to `{scratchpad}/full_suite.log`.

Triage every failure against the baseline:

| Failure | Action |
|---------|--------|
| Also fails in the baseline | Pre-existing; do not fix it. Rerun it alone to confirm it is environmental (e.g. a timing test) |
| New | A carried-over error: you have the PRD-wide context, so fix it. Fix the cause, not the test, unless the test is a guard (a census or inventory test) that should register the new code; then register it with a comment citing the PRD and the reason |
| Order-dependent (passes alone, fails in the suite) | Check whether it reproduces without this PRD's changes; if it does, it is pre-existing. Otherwise fix it |

| Fails in CI only (Linux) or locally only (Windows) | A platform difference, not flakiness: fix the code for both. Reproduce a Linux-only failure locally in a `python:3.11-slim` container when the fix is not obvious |

After fixing, rerun the affected test files locally, then commit with explicit staging (`fix({PRD-ID}): …` or `test({PRD-ID}): …`), push, and read the new CI run. Phase 4 ends on a green run (or one whose only failures are pre-existing).

---

## Phase 5: CLOSE, MARK THE PR READY

1. Confirm the PRD frontmatter `status: done` (the last story normally sets it), the board shows 100% and `gen_index.py` prints `errors: none`. Commit and push if anything changed (and read that CI run, as in Phase 4).
2. `git status` is clean, `git log --oneline {base_branch}..{epic_branch}` lists every story, and `git status -sb` shows nothing ahead of `origin/{epic_branch}`.
3. Replace the draft body and mark the PR ready: `gh pr edit {number} --body-file {scratchpad}/pr_body.md`, then `gh pr ready {number}`. Write the body in the user's language:
   - **Summary**: what the PRD delivers, in 2–3 sentences
   - **What's new**, grouped by area (modules, config/permissions, data/API, UI, tests/corpora, docs), each item naming the files
   - **Out of scope**: what the PRD defers, and to which PRD
   - **Validation**: the final CI run (link, counts, duration), each carried-over error fixed (with its commit and the story that introduced it), and each pre-existing failure, marked as such
   - **Known limitations**, as documented
   - The PR attribution line from the session's instructions, if any
4. **Never merge.** The merge is the user's decision.

---

## Phase 6: OUTPUT

```markdown
## {PRD-ID} orchestrated

**Epic Branch**: `{epic_branch}` (pushed) · **PR**: {url}
**Stories**: {done}/{total} done · {N} commits

### Final suite (CI run {url})
{passed} passed, {skipped} skipped, {failed} failed ({duration})
- Carried-over errors fixed: {list with commits, or "none"}
- Pre-existing failures: {list, or "none"}

### Orchestrator decisions
{the decisions that changed stories or the PRD, one line each}

### Things to look at
{unexpected tree changes, accepted deviations, documented limitations, or "none"}

### Next step
Review and merge the PR when approved.
```

---

## Rules (all phases)

- Never merge. Push the epic branch from Phase 1 on, after each verified story and each fix; subagents never push. After Phase 0, never switch branches.
- Stage files explicitly. Never `--no-verify`, never amend, never force.
- One subagent at a time. Never two pytest processes at once (they share one libSQL server).
- Nobody runs the full suite locally: CI runs it on every push. The local suite is only the fallback when CI is unavailable.
- Talk to the user in their language; command files, code and commits stay in English, matching the repo.
- Ask only for genuine ambiguity (Golden Rule). Report everything else in the Phase 6 output.
