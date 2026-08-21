---
description: Prime agent with codebase + local PRD/story context
argument-hint: [PRD-ID | STORY-ID | path-to-prd-or-story]
---

# Prime: Load Project Context

**Input**: $ARGUMENTS

## Objective

Build comprehensive understanding of this codebase + the active PRD/story context.

**Core Principle**: READ ONLY — no code written. Strictly analysis and context loading.

---

## Step 0: Load Local PRD/Story Context (if provided)

Resolve input:

| Input | Resolution |
|-------|-----------|
| `PRD-NNN` | Load `.agents/PRDs/PRD-NNN-*/PRD.md` + `index.md` + every story under `.agents/stories/PRD-NNN-*/` |
| `STORY-NNN` (with active PRD context) | Load that story file + parent PRD + sibling stories' frontmatter |
| Path to `PRD.md` | Load that PRD + index + its stories |
| Path to story `.md` | Load that story + parent PRD + sibling stories' frontmatter |
| Blank | Auto-resolve: scan all PRDs under `.agents/PRDs/PRD-*/`, load every PRD that is **not completed** (see below). Do not ask the user which PRD — this is fully automatic. |

### Blank input: completed-PRD filter

A PRD counts as **completed** — and is skipped when input is blank — if either is true:
- `PRD.md` frontmatter `status` is `done` or `archived`, OR
- Every story under `.agents/stories/{PRD-ID}/` has `status: done` (i.e. `index.md` Progress reads N/N — 100%)

For each remaining (non-completed) PRD, load `PRD.md` + `index.md` + every story under `.agents/stories/{PRD-ID}/`, same as the `PRD-NNN` row above.

- If exactly one PRD is non-completed → treat it as the single active PRD for the rest of this command (Step 1 + Output run as normal).
- If more than one is non-completed → load all of them; repeat the **Story Progress** bullet and the **Deterministic Automation Block** once per PRD in the Output.
- If zero are non-completed (every PRD done/archived) → skip PRD context entirely, state "No active PRDs — all completed" in the Output, and proceed with Step 1 (codebase-only) context.

Extract from frontmatter:
- PRD: `id`, `slug`, `status`, `base_branch`, `epic_branch`
- Story: `id`, `status`, `epic_branch`, `plan`, `commit`, `depends_on`, `blocks`, `complexity`

Read story bodies for: description, acceptance criteria, technical notes.

---

## Step 1: Analyze the Codebase

1. Read `backend/AGENTS.md` for backend conventions/architecture (if exists)
2. Read `frontend/AGENTS.md` if exists, else inspect `frontend/src/`
3. Backend structure: routers, services, repositories, models, schemas
4. Frontend structure: pages, components, layouts, lib
5. Check `frontend/package.json` for deps
6. Recent commits: `git log --oneline -5`
7. Current branch: `git branch --show-current`

---

## Output

Scannable summary:

- **Active PRD**: `{PRD-ID}` — {title} (status: {status})
- **Epic Branch**: `{epic_branch}` (base: `{base_branch}`)
- **Story Progress**: {done}/{total} done, {in-progress} in flight, {blocked} blocked
- **Active Story** (if specified): `{STORY-ID}` — {title} (status: {status}, commit: `{commit or "—"}`)
  - Acceptance criteria summary
  - Dependencies status (blocked-by satisfied? Y/N)
- **Project Purpose**: one sentence
- **Tech Stack**:
  - Frontend: React 19 + Vite + React Router 7, shadcn/ui, Tailwind v4, JavaScript
  - Backend: FastAPI + SQLAlchemy 2.x + Pydantic v2, SQLite, Uvicorn
- **Data Model**: core entities + relationships
- **Key Patterns**: backend layered (router → service → repository → model), frontend component/page structure
- **Current Git State**: branch + last 5 commits

Bullet points. Concise.

### Deterministic Automation Block (mandatory, always last)

If one or more PRD contexts were loaded (Step 0 resolved one or more `PRD-ID`s — whether from explicit input or auto-resolved blank input), end the response with this exact block per PRD, one after another in `PRD-ID` order — fixed field names, one value per line, no prose before/after it, no rewording, no omitted fields. This is parsed by automation; format must not vary between runs.

```
{PRD-ID}:
Last-Story: {relative path to highest-numbered story with status: done, or "none"}
Last-Report: {relative path to that story's report, or "none"}
Next-Story: {relative path to lowest-numbered story with status: todo whose depends_on are all status: done, or "none"}
```

Field derivation (deterministic, do not use judgment). All paths are relative to the repo root, forward slashes, starting with `.agents/`:
- `Last-Story` — scan all stories in `.agents/stories/{PRD-ID}/`, filter `status: done`, take the highest `STORY-NNN` number. Value is the full path (e.g. `.agents/stories/PRD-003-pii-redaction/STORY-008-dedup-pattern-isolation-tests.md`), not just the filename.
- `Last-Report` — that same story's `report` frontmatter field, which already holds the full path (e.g. `.agents/reports/PRD-003-pii-redaction/STORY-008-dedup-pattern-isolation-tests.report.md`). Use it verbatim.
- `Next-Story` — filter stories with `status: todo`, keep only those whose every `depends_on` entry has `status: done`, take the lowest `STORY-NNN` number. Full path under `.agents/stories/{PRD-ID}/`.
- If zero PRDs are non-completed (all done/archived), omit this block entirely and state so in prose instead.

Example (single active PRD):
```
PRD-003:
Last-Story: .agents/stories/PRD-003-pii-redaction/STORY-008-dedup-pattern-isolation-tests.md
Last-Report: .agents/reports/PRD-003-pii-redaction/STORY-008-dedup-pattern-isolation-tests.report.md
Next-Story: .agents/stories/PRD-003-pii-redaction/STORY-009-audit-stats-pii-endpoints.md
```

Example (blank input, multiple active PRDs — one block per PRD, PRD-001 omitted because it's completed):
```
PRD-002:
Last-Story: .agents/stories/PRD-002-reflex-chat-ui/STORY-005-chat-message-streaming.md
Last-Report: .agents/reports/PRD-002-reflex-chat-ui/STORY-005-chat-message-streaming.report.md
Next-Story: .agents/stories/PRD-002-reflex-chat-ui/STORY-006-chat-history-persistence.md

PRD-003:
Last-Story: .agents/stories/PRD-003-pii-redaction/STORY-008-dedup-pattern-isolation-tests.md
Last-Report: .agents/reports/PRD-003-pii-redaction/STORY-008-dedup-pattern-isolation-tests.report.md
Next-Story: .agents/stories/PRD-003-pii-redaction/STORY-009-audit-stats-pii-endpoints.md
```
