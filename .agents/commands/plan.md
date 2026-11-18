---
description: Create implementation plan for a single story
argument-hint: <path/to/story.md | STORY-ID>
---

# Implementation Plan Generator (per-story)

**Input**: $ARGUMENTS

## Objective

Transform a single story into a battle-tested implementation plan via codebase exploration. One plan per story (1:1).

**Core Principle**: PLAN ONLY — no code written to the application. Plan lives at `.agents/plans/{PRD-ID}/{STORY-ID}-{slug}.plan.md`.

**Order**: CODEBASE FIRST. Solutions must fit existing patterns.

**Budget**: the plan is read by the implementer and by the orchestrator's verification, so every line is paid for several times. Keep it **under ~12 KB**. Point to code (`file:line`) instead of copying it: an excerpt is at most 5 lines, and never a whole function or file (the implementer opens the file anyway). Do not repeat what the story already says; link to it.

---

## Phase 1: PARSE INPUT

Resolve input to a story file:

| Input | Action |
|-------|--------|
| Path to story `.md` | Load directly |
| `STORY-NNN` | Search `.agents/stories/*/STORY-NNN-*.md`. If multiple, ask user. |
| Path to PRD `.prd.md` (legacy) | Reject — must target a single story |
| Blank | List in-progress/todo stories, ask user |

Read story frontmatter:
- `id`, `prd`, `slug`, `title`, `type`, `complexity`
- `epic_branch`
- `depends_on`, `blocks`
- `status` (must be `todo` or `in-progress`)

If `status: blocked` → STOP, report blocker.

If `depends_on` non-empty, verify each dependency `status: done`. If not, warn user and ask whether to proceed.

Read the parent PRD **selectively** (`.agents/PRDs/{prd}/PRD.md`; PRDs run to 80 KB). Do not read it whole:
1. Its frontmatter, and its outline: `grep -n "^#" <PRD>`.
2. Only the sections this story needs: those the orchestrator names in your prompt, those the story's body or Technical Notes cite (sections, decision IDs such as "D7"), and the architecture section for the modules you touch. Read them with offset/limit.
3. Grep for this story's ID and for the decision IDs it uses, to catch references elsewhere in the PRD.

If the orchestrator gave you **design points**, they are binding. If the code makes one impossible, say so in the output instead of choosing another design.

---

## Phase 1b: SCAN SKILLS (mandatory)

- Read `skills` field from story frontmatter (if populated by `/create-stories`)
- List `.agents/skills/` and read each referenced `SKILL.md` in full
- Also read any `SKILL.md` whose `description` matches the story domain even if not listed
- Extract: required tools, allowed-tools restrictions, command syntax, workflow constraints
- Carry these rules into Phase 3 design and Phase 4 task steps — name the skill explicitly in any task that depends on it (e.g., `Validate via agent-browser snapshot + click flow`)

---

## Phase 2: EXPLORE

### Study the Codebase

Use an Explore agent (or Grep/Glob plus partial reads with offset/limit; open a large file whole only when you need all of it) to find:

1. **Similar implementations** — analogous features with file:line refs
2. **Naming conventions** — actual examples
3. **Error handling patterns** — how errors are created/handled
4. **Type definitions** — relevant interfaces/types
5. **Test patterns** — test file structure + assertions

### Document Patterns

| Category | File:Lines | Pattern |
|----------|------------|---------|
| NAMING | `path/to/file.py:10-15` | {description} |
| ERRORS | `path/to/file.py:20-30` | {description} |
| SCHEMAS | `path/to/schemas.py:1-10` | {description} |
| UI | `chat_ui/chat_ui/{module}.py:1-25` | {description} |

---

## Phase 3: DESIGN

- Files to CREATE
- Files to UPDATE
- Dependency order
- Risks + mitigations

---

## Phase 4: GENERATE

### Plan File Path

`.agents/plans/{PRD-ID}/{STORY-ID}-{slug}.plan.md`

```bash
mkdir -p .agents/plans/{PRD-ID}
```

### Plan Template

```markdown
---
story: {STORY-ID}
prd: {PRD-ID}
slug: {kebab-slug}
title: {Story title}
type: {NEW_CAPABILITY | ENHANCEMENT | REFACTOR | BUG_FIX}
complexity: {small | medium | large}   # copied from the story
epic_branch: {epic branch}        # all stories commit here, no per-story branch
created: {YYYY-MM-DD}
---

# Plan: {Story Title}

## Summary

{One paragraph: what we're building + approach}

- Story: `.agents/stories/{PRD-ID}/{STORY-ID}-{slug}.md` (user story and full AC text live there; do not copy them)
- PRD sections used: {e.g. "§4.2, D7, D11"}
- Systems affected: {list}

## Design Decisions

{Only when the story fixes something hard to change later: contracts and signatures, concurrency/failure semantics, data formats. One bullet each, with the edge cases. Include the orchestrator's design points verbatim. Otherwise: "none beyond the tasks".}

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| {skill-name} | {rule from SKILL.md} | Task {N}, Task {M} |

---

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Naming | `{file:lines}` | {one line} |
| Error handling | `{file:lines}` | {one line} |
| Tests | `{file:lines}` | {one line} |

Add an excerpt (at most 5 lines) only where the one-line description is not enough.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/{module}.py` | CREATE | {why} |
| `app/routers/{router}.py` | UPDATE | {why} |
| `tests/test_{module}.py` | CREATE | {why} |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: {Description}

- **File**: `app/services/{module}.py`
- **Action**: CREATE / UPDATE
- **Implement**: {what to do}
- **Mirror**: `app/services/{existing_module}.py:lines` — follow this pattern
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_{module}.py`

### Task 2: {Description}

- **File**: `chat_ui/chat_ui/{module}.py`
- **Action**: CREATE / UPDATE
- **Implement**: {what to do}
- **Mirror**: `chat_ui/chat_ui/{existing_module}.py:lines`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_chat_ui_startup_guard.py`

{Continue for each task...}

---

## End-to-End Tests

List manual/automated E2E checks for `/implement` to execute:

- [ ] {A test that drives the real FastAPI app through the changed route, e.g. `TestClient(app)` → expected status + body shape}
- [ ] {Only if `chat_ui/` changed: the behaviour the user sees}
- [ ] {Other E2E checks}

---

## Validation

There is no `frontend/` and no npm lint in this repo. Always prefix pytest with `PYTHONUTF8=1` (the Spanish Windows locale breaks some tests otherwise), and run one pytest at a time (every DB test shares the one libSQL dev server, `harness-libsql-dev` on :8080). The full suite runs in GitHub CI on push; list targeted tests here instead.

```bash
# The app imports
.venv/Scripts/python -c "from app.main import app; print('OK')"
# Targeted tests, in one pytest call: new/changed test files, the tests/test_<module>.py
# of each module changed, and the guard tests that apply
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider {test files}
```

Guard tests to add when they apply:
- `tests/test_untouched_app.py` when you touch files under `app/`
- `tests/test_pii_redaction_integration.py` when you rename or remove a test (register the old name in `_DELIBERATELY_SUPERSEDED_TESTS`)
- `tests/test_chat_ui_startup_guard.py` when you touch `chat_ui/`

---

## Acceptance Criteria → Tasks → Tests

One row per AC of story `{STORY-ID}` (short label, not the full text):

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 {short label} | Task {N} | `tests/test_x.py::test_name` |
| AC2 {short label} | Task {M} | `tests/test_y.py::test_name` |

Plus: all tasks completed, validation passes, follows existing patterns.
```

---

## Phase 5: UPDATE STORY FILE

After plan written, update the story file frontmatter:

- Set `plan: .agents/plans/{PRD-ID}/{STORY-ID}-{slug}.plan.md`
- If `status: todo` → set `status: in-progress`
- Update `updated: {YYYY-MM-DD}`

Then regenerate `.agents/PRDs/{PRD-ID}/index.md` to reflect the new status + plan link.

---

## Phase 6: OUTPUT

```markdown
## Plan Created

**Story**: {STORY-ID} — {title}
**File**: `.agents/plans/{PRD-ID}/{STORY-ID}-{slug}.plan.md`

**Summary**: {2-3 sentences}
**Size**: {N} KB (`wc -c`; trim it if over ~12 KB)

**Scope**:
- {N} files to CREATE
- {M} files to UPDATE
- {K} total tasks

**Key Patterns**:
- {Pattern 1 with file:line}
- {Pattern 2 with file:line}

**Story Status**: todo → in-progress
**Index**: regenerated at `.agents/PRDs/{PRD-ID}/index.md`

**Next Step**: `/implement .agents/plans/{PRD-ID}/{STORY-ID}-{slug}.plan.md`
```
