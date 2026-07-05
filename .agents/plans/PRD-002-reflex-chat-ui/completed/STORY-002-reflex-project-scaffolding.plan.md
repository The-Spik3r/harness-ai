---
story: STORY-002
prd: PRD-002
slug: reflex-project-scaffolding
title: "Reflex project scaffolding & dependency setup"
type: technical
complexity: small
epic_branch: epic/PRD-002-reflex-chat-ui        # all stories commit here, no per-story branch
created: 2026-07-04
---

# Plan: Reflex project scaffolding & dependency setup

## Summary

Stand up a standalone Reflex project at `chat_ui/` alongside PRD-001's existing `app/` tree, using Reflex's own `reflex init --name chat_ui --template blank` scaffolder (run with `chat_ui/` as the working directory so the generated layout lands as `chat_ui/rxconfig.py` + `chat_ui/chat_ui/chat_ui.py`, matching PRD Section 6 exactly). Add `reflex` pinned to an exact version in the root `requirements.txt`. Add stub `state.py` and a stub `components/` subpackage per the story's AC5. This story does not touch `app/` at all and does not wire up `api_transformer` (that's STORY-003) — it only needs the Reflex app to boot standalone in dev mode and PRD-001's test suite to keep passing untouched.

This plan was verified against the real `reflex init`/`reflex run` output rather than assumed from memory: reflex `0.9.6.post1` was installed in a scratch venv on this machine (Windows, Python 3.14.5) and actually run end-to-end (`reflex init` → `reflex run` → `curl` both the frontend placeholder page and backend `/ping`, both returned 200) before writing this plan, so the file list and task steps below reflect actual tool output, not documentation guesses.

## User Story

As a devops engineer
I want a scaffolded Reflex project living alongside the existing FastAPI app, with `reflex` pinned in dependencies
So that later stories have a place to build the chat UI without touching PRD-001's existing `app/` tree

## Story Reference

- Story file: `.agents/stories/PRD-002-reflex-chat-ui/STORY-002-reflex-project-scaffolding.md`
- PRD: `.agents/PRDs/PRD-002-reflex-chat-ui/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | technical |
| Complexity | small |
| Systems Affected | root `requirements.txt`; new `chat_ui/` tree (isolated from `app/`) |
| Story | STORY-002 |
| PRD | PRD-002 |
| Epic Branch | `epic/PRD-002-reflex-chat-ui` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` exists but is empty (confirmed via directory listing). Story frontmatter `skills: []` is consistent with this — no skill rules apply to this story.

---

## Codebase State / Patterns to Follow

`app/` has no Reflex precedent to mirror — this is a brand-new, independent package tree, so the "pattern source" here is Reflex's own scaffolder output (verified live in this session) rather than existing repo code. Two small conventions do carry over from `app/`:

### Existing empty-package-marker convention (mirror for `components/__init__.py`)
```python
// SOURCE: app/__init__.py (entire file)
(empty file — marks the directory as an importable package)
```

### Verified `reflex init --name chat_ui --template blank` output (run from inside `chat_ui/`)
```python
// SOURCE: actual generated chat_ui/rxconfig.py, this session
import reflex as rx

config = rx.Config(
    app_name="chat_ui",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ]
)
```
```python
// SOURCE: actual generated chat_ui/chat_ui/chat_ui.py, this session (the blank template's placeholder page)
"""Welcome to Reflex! This file outlines the steps to create a basic app."""

import reflex as rx

from rxconfig import config


class State(rx.State):
    """The app state."""


def index() -> rx.Component:
    # Welcome Page (Index)
    return rx.container(
        rx.color_mode.button(position="top-right"),
        rx.vstack(
            rx.heading("Welcome to Reflex!", size="9"),
            rx.text(
                "Get started by editing ",
                rx.code(f"{config.app_name}/{config.app_name}.py"),
                size="5",
            ),
            rx.link(
                rx.button("Check out our docs!"),
                href="https://reflex.dev/docs/getting-started/introduction/",
                is_external=True,
            ),
            spacing="5",
            justify="center",
            min_height="85vh",
        ),
    )


app = rx.App()
app.add_page(index)
```
This placeholder page already satisfies AC1/AC3 ("renders a placeholder page", "boots without errors") with zero hand-written UI code — leave it unmodified in this story; STORY-004 replaces it with the real chat components.

`reflex init` also generates, alongside the two files above: `chat_ui/chat_ui/__init__.py` (empty), `chat_ui/.gitignore` (excludes `.web`, `*.db`, `*.py[cod]`, `assets/external/`, `__pycache__/`, `.states` — git honors nested `.gitignore` files, so no change to the root `.gitignore` is needed), `chat_ui/assets/favicon.ico`, `chat_ui/AGENTS.md` and `chat_ui/CLAUDE.md` (Reflex-authored docs pointing at Reflex's own Claude-skill plugin — harmless, keep as-is, may help later Reflex-focused stories), `chat_ui/reflex.lock/package.json` (frontend lockfile snapshot, keep — reproducible installs), and a `chat_ui/requirements.txt` containing only `reflex==0.9.6.post1` (see Design Decision 2 below — this one gets deleted).

---

## Design Decisions

1. **Run `reflex init` with `chat_ui/` as the working directory, not the repo root.** `reflex init --name <x>` always creates the app package (`<x>/<x>.py`) one level below wherever it's invoked. Running it from repo root would produce `chat_ui/chat_ui.py` (one level, not two), which does not match PRD Section 6's `chat_ui/chat_ui/chat_ui.py`. Creating an empty `chat_ui/` directory first and running `reflex init --name chat_ui --template blank` *inside* it reproduces the PRD's exact two-level layout using the tool's own scaffolder, rather than hand-assembling files that could drift from what `reflex run`/`reflex export` actually expect.

2. **Delete the `chat_ui/requirements.txt` that `reflex init` generates.** The scaffolder writes its own local `requirements.txt` (just `reflex==<version>`) next to `rxconfig.py`. PRD Section 8 says to "pin an exact version in `requirements.txt`" (singular, the existing root file, per the story's AC2: "Given `requirements.txt`, when dependencies are updated..."). Keeping two requirements files inside one repo invites drift (e.g. version bumped in one but not the other); this plan treats the root `requirements.txt` as the single source of truth and removes the nested duplicate.

3. **Pin `reflex==0.9.6.post1`.** Confirmed as the current latest release (`pip index versions reflex`) and confirmed installable in this environment (Windows, Python 3.14.5) with no dependency conflicts.

4. **No changes to the root `.gitignore`.** `chat_ui/.gitignore` (generated by `reflex init`) already excludes `.web/` (the compiled frontend, regenerated by every `reflex run`/`reflex export`) and other Reflex-local artifacts. Git applies nested `.gitignore` files automatically, so nothing needs to be added to the root file for this story.

5. **Keep `chat_ui/AGENTS.md`, `chat_ui/CLAUDE.md`, `chat_ui/reflex.lock/`.** These are auto-generated by `reflex init`, are self-contained inside `chat_ui/`, and don't collide with anything at the repo root (no root `CLAUDE.md`/`AGENTS.md` exists today). Deleting them would be pure churn against the tool's own output for no behavioral benefit.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `requirements.txt` | UPDATE | Add `reflex==0.9.6.post1`, pinned exact version (AC2) |
| `chat_ui/rxconfig.py` | CREATE (via `reflex init`) | Reflex config; `app_name="chat_ui"` — `api_transformer` added in STORY-003 |
| `chat_ui/chat_ui/__init__.py` | CREATE (via `reflex init`) | Marks `chat_ui/chat_ui/` as a package |
| `chat_ui/chat_ui/chat_ui.py` | CREATE (via `reflex init`) | `rx.App()` entrypoint + placeholder page (unmodified template output) |
| `chat_ui/chat_ui/state.py` | CREATE | Stub — real `ChatState` added in STORY-006 |
| `chat_ui/chat_ui/components/__init__.py` | CREATE | Stub subpackage — real components added in STORY-004 |
| `chat_ui/.gitignore` | CREATE (via `reflex init`) | Excludes `.web/`, `*.db`, `__pycache__/`, etc. — keep as generated |
| `chat_ui/assets/favicon.ico` | CREATE (via `reflex init`) | Default Reflex favicon — keep as generated |
| `chat_ui/AGENTS.md`, `chat_ui/CLAUDE.md` | CREATE (via `reflex init`) | Reflex-authored docs — keep as generated |
| `chat_ui/reflex.lock/package.json` | CREATE (via `reflex init`) | Frontend lockfile snapshot — keep as generated |
| `chat_ui/requirements.txt` | CREATE then DELETE | Redundant with root `requirements.txt` (Design Decision 2) |

No files under `app/` or `tests/` are touched (AC4).

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Pin `reflex` in root `requirements.txt`

- **File**: `requirements.txt`
- **Action**: UPDATE
- **Implement**: Append a new line: `reflex==0.9.6.post1`.
- **Mirror**: existing unpinned entries in `requirements.txt` (`fastapi`, `uvicorn[standard]`, ...) — this is the one deliberately-pinned exception per PRD Section 8.
- **Validate**: `pip install -r requirements.txt` completes with no errors in the project's virtualenv.

### Task 2: Scaffold the Reflex project with `reflex init`

- **File**: `chat_ui/` (new directory tree)
- **Action**: CREATE
- **Implement**: From the repo root: `mkdir chat_ui && cd chat_ui && reflex init --name chat_ui --template blank`. This generates `rxconfig.py`, `chat_ui/__init__.py`, `chat_ui/chat_ui.py` (placeholder page), `.gitignore`, `assets/favicon.ico`, `AGENTS.md`, `CLAUDE.md`, `reflex.lock/package.json`, and `requirements.txt` (removed in Task 3) — all verified live in this session (see "Patterns to Follow" above). Do not hand-edit `chat_ui/chat_ui.py` in this story.
- **Mirror**: PRD Section 6 suggested directory additions — `chat_ui/rxconfig.py`, `chat_ui/chat_ui/chat_ui.py`.
- **Validate**: `chat_ui/rxconfig.py` and `chat_ui/chat_ui/chat_ui.py` exist; `python -c "import ast; ast.parse(open('chat_ui/rxconfig.py', encoding='utf-8').read())"` and the same for `chat_ui/chat_ui/chat_ui.py` both parse with no syntax errors.

### Task 3: Remove the redundant nested `requirements.txt`

- **File**: `chat_ui/requirements.txt`
- **Action**: DELETE
- **Implement**: Delete the `requirements.txt` `reflex init` generated inside `chat_ui/` (Design Decision 2) — the root `requirements.txt` from Task 1 is the single source of truth.
- **Validate**: `chat_ui/requirements.txt` no longer exists.

### Task 4: Create `state.py` stub

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: CREATE
- **Implement**: A minimal placeholder module — a single module docstring noting `ChatState` lands here in STORY-006. No classes, no imports, no dead code.
- **Mirror**: story AC5 / PRD Section 6 (`chat_ui/chat_ui/state.py` listed as a stub).
- **Validate**: `python -c "import ast; ast.parse(open('chat_ui/chat_ui/state.py', encoding='utf-8').read())"` parses with no errors.

### Task 5: Create `components/` stub subpackage

- **File**: `chat_ui/chat_ui/components/__init__.py`
- **Action**: CREATE
- **Implement**: Empty file, marking `components/` as an importable subpackage (mirrors `app/__init__.py`'s empty-package convention).
- **Mirror**: `app/__init__.py` (empty file, package marker).
- **Validate**: `chat_ui/chat_ui/components/__init__.py` exists.

### Task 6: Verify the scaffolded app boots standalone in dev mode

- **File**: N/A (validation only, no file changes)
- **Action**: VALIDATE
- **Implement**: From `chat_ui/`, run `reflex run`. First run downloads Reflex's bundled `bun` binary plus ~280 frontend packages (requires network access) before reaching "App Running" — this was observed to take roughly 60-90 seconds in this session. Confirm it reaches "App Running" and serves the frontend + backend.
- **Mirror**: verified directly in this session with `reflex 0.9.6.post1` on this same Windows/Python 3.14 environment — `reflex run` reached "App Running", frontend `GET /` returned 200, and backend `GET /ping` returned 200.
- **Validate**: with `reflex run` active, `curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/` → `200`; `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/ping` → `200`. Stop the process afterward (Ctrl+C, or kill the process tree on Windows).

### Task 7: Confirm PRD-001's existing test suite still passes unmodified

- **File**: N/A (validation only, no file changes)
- **Action**: VALIDATE
- **Implement**: From the repo root, run `pytest`. This story adds files only under `chat_ui/`, never touching `app/` or `tests/`, so the existing suite must be unaffected.
- **Validate**: `pytest` exits 0 with the same pass count as before this story (AC4).

---

## End-to-End Tests

- [ ] `chat_ui/` exists with `rxconfig.py`, `chat_ui/chat_ui.py`, `chat_ui/state.py`, `chat_ui/components/` — matches PRD Section 6 layout (AC1, AC5)
- [ ] `reflex==0.9.6.post1` present in root `requirements.txt`, exact version pin (AC2)
- [ ] `cd chat_ui && reflex run` boots without error and serves a placeholder page on the frontend port, `/ping` reachable on the backend port (AC3)
- [ ] `pytest` from repo root passes unmodified, same suite as before this story (AC4)
- [ ] No files under `app/` were created, modified, or deleted by this story

---

## Validation

```bash
pip install -r requirements.txt
cd chat_ui && reflex run
# separate terminal, while reflex run is active:
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/ping
# stop reflex run, then from repo root:
cd ..
pytest
```

---

## Acceptance Criteria

(Copied from story STORY-002)

- [ ] Given the project root, when scaffolding completes, then a `chat_ui/` directory exists with `rxconfig.py` and a `chat_ui/chat_ui/` package containing `chat_ui.py` (an `rx.App()` entrypoint that renders a placeholder page).
- [ ] Given `requirements.txt`, when dependencies are updated, then `reflex` is added and pinned to an exact version.
- [ ] Given a clean checkout with dependencies installed, when `reflex init` state is inspected (or `reflex run` is invoked in dev mode), then the app boots without errors and serves a placeholder page.
- [ ] Given the new `chat_ui/` directory, when PRD-001's existing test suite runs, then it continues to pass unmodified.
- [ ] Given the directory layout in PRD Section 6, when scaffolding completes, then it matches the suggested structure: `chat_ui/rxconfig.py`, `chat_ui/chat_ui/chat_ui.py`, `chat_ui/chat_ui/state.py` (stub), `chat_ui/chat_ui/components/` (empty or stub).
- [ ] All tasks completed
- [ ] `pytest` passes (full suite, unmodified)
- [ ] `reflex run` boots without error from `chat_ui/`
- [ ] Follows PRD Section 6/8 conventions and the verified `reflex init` scaffolder output
