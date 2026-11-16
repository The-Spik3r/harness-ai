---
description: Take one PRD end-to-end — stories, per-story plan + implement via subagents, one final suite, push and PR
argument-hint: <PRD-ID | path/to/PRD.md>
---

# Orchestrate a PRD (local file workflow, single-branch per epic)

**PRD**: $ARGUMENTS

## Mission

Deliver a whole PRD on its epic branch. You are the **orchestrator**: you create the stories yourself, then for each story launch a **plan subagent** (`plan.md`) and an **implement subagent** (`implement.md`), and verify each subagent did exactly what it should before moving on. At the end you run the full suite **once**, fix anything carried over, push the epic branch and open the PR. You never merge.

**Core Philosophy**: Subagents do the work and the orchestrator checks it. You have the context of the whole PRD, so you catch errors that cross stories and you fix them at the end. Subagents never re-run the full suite.

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
| Stories exist under `.agents/stories/{PRD-ID}/` | **Resume**: skip Phase 1, continue from the first story not `done` |
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

### 0.3 Baseline suite (background)

Start the full suite on the epic branch **before** any story lands, in the background (`run_in_background`), logging to the scratchpad:

```bash
docker restart harness-libsql-dev >/dev/null && PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider > "{scratchpad}/baseline_suite.log" 2>&1
```

It runs while you create the stories, so it costs no wall-clock time. Its failures are the **pre-existing failures**: list them in the brief so no subagent tries to "fix" them, and use them in Phase 4 to tell carried-over errors from old ones.

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
  - **Do NOT run the full suite** (user decision: the orchestrator runs it once at the end). Wherever implement.md or the plan says "full suite", this rule wins. Run instead, in one pytest call: every new or modified test file, the existing `tests/test_<module>.py` of every pre-existing module you changed, the tests the plan names, and the guard tests (`test_pii_redaction_integration.py` when you rename or remove a test; `test_untouched_app.py` when you touch app files). Do not add every file that merely imports a changed module. Aim for under ~10 minutes. Record the exact pass/fail/skip counts. In the report write "Full suite: deferred to orchestrator (user decision)".
  - Renaming or removing a pre-existing test function: register the old name in `_DELIBERATELY_SUPERSEDED_TESTS` in `tests/test_pii_redaction_integration.py`.
- **Always prefix pytest with `PYTHONUTF8=1`** (the Spanish Windows locale breaks `test_db_isolation_harness.py` otherwise).
- DB tests need the libSQL dev server `harness-libsql-dev` on :8080. If many `db` tests error at fixture setup, run `docker restart harness-libsql-dev` and rerun before suspecting the code. Do not start a second one.
- Pre-existing failures (from the orchestrator's baseline; ignore them, do not fix them): {list from baseline_suite.log, or "none"}.

## Commits (implement subagent)
- Stage files explicitly; never `git add -A` / `git add .`. Never `--no-verify`; if a hook fails, fix the cause and make a new commit.
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
- [ ] Deviations the subagent reported are acceptable. If one changes what a later story assumes, record it (3.5)

If something is wrong, resume the same agent with SendMessage and list the exact defects, or fix it yourself and commit `fix({PRD-ID}): {STORY-ID} <what>`. Move on only when the story is truly done.

### 3.5 Orchestrator decisions

Whenever you resolve a conflict (story vs PRD vs code), correct a story's text, or accept a deviation, record it where the next agents will read it: add a line to the affected later stories' **Technical Notes** (`Orchestrator decision ({STORY-ID} plan): …`), amend the PRD if the PRD was wrong, and append a brief rule if it is general. These edits ride in the next story's commit.

### 3.6 Failures during the loop

| Failure | Action |
|---------|--------|
| Subagent hits the usage limit after writing partial work | Resume it with SendMessage ("continue from where you stopped") |
| Subagent hits the limit before writing anything | Relaunch fresh with the same prompt |
| Subagent stops on "dirty working tree" for files of this story | Resume it: those files belong to the story (see brief) |
| A subagent's targeted run is very slow | Tell it to narrow the set (brief rule); append the lesson to the brief |
| The story itself is ambiguous in a way that changes the design | Resolve it from the PRD or code; ask the user only if it is genuinely theirs (Golden Rule) |
| An unexpected change shows up in the tree that no agent claims | Back it up to the scratchpad, diff against HEAD, then restore it, and tell the user in the final output |

---

## Phase 4: FINAL FULL SUITE (once)

When every story is `done`, run the full suite **once**, in the background:

```bash
docker restart harness-libsql-dev >/dev/null && PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider > "{scratchpad}/full_suite.log" 2>&1
```

Wait for the completion notification; do not poll in a sleep loop. If the user asks how it is going, read the tail of the log (the percentage and any `F`).

Triage every failure against the baseline:

| Failure | Action |
|---------|--------|
| Also fails in the baseline | Pre-existing; do not fix it. Rerun it alone to confirm it is environmental (e.g. a timing test) |
| New | A carried-over error: you have the PRD-wide context, so fix it. Fix the cause, not the test, unless the test is a guard (a census or inventory test) that should register the new code; then register it with a comment citing the PRD and the reason |
| Order-dependent (passes alone, fails in the suite) | Check whether it reproduces without this PRD's changes; if it does, it is pre-existing. Otherwise fix it |

After fixing, rerun the affected test files (not the full suite again), then commit with explicit staging:
`fix({PRD-ID}): …` or `test({PRD-ID}): …`.

---

## Phase 5: CLOSE, PUSH, PR

1. Confirm the PRD frontmatter `status: done` (the last story normally sets it), the board shows 100% and `gen_index.py` prints `errors: none`. Commit if anything changed.
2. `git status` is clean, and `git log --oneline {base_branch}..{epic_branch}` lists every story.
3. Push the epic branch: `git push -u origin {epic_branch}`.
4. Open the PR against `{base_branch}` with `gh pr create --base {base_branch} --head {epic_branch} --title "Epic/{PRD-ID} {PRD title}" --body-file {scratchpad}/pr_body.md`. Write the body in the user's language:
   - **Summary**: what the PRD delivers, in 2–3 sentences
   - **What's new**, grouped by area (modules, config/permissions, data/API, UI, tests/corpora, docs), each item naming the files
   - **Out of scope**: what the PRD defers, and to which PRD
   - **Validation**: the exact final suite counts, each carried-over error fixed (with its commit), and each pre-existing failure, marked as such
   - **Known limitations**, as documented
   - The PR attribution line from the session's instructions, if any
5. **Never merge.** The merge is the user's decision.

---

## Phase 6: OUTPUT

```markdown
## {PRD-ID} orchestrated

**Epic Branch**: `{epic_branch}` (pushed) · **PR**: {url}
**Stories**: {done}/{total} done · {N} commits

### Final suite
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

- Never merge; push only in Phase 5. After Phase 0, never switch branches.
- Stage files explicitly. Never `--no-verify`, never amend, never force.
- One subagent at a time.
- Subagents never run the full suite. You run it once in Phase 0 (baseline) and once in Phase 4.
- Talk to the user in their language; command files, code and commits stay in English, matching the repo.
- Ask only for genuine ambiguity (Golden Rule). Report everything else in the Phase 6 output.
