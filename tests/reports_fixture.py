"""A small `.agents/` tree for the Reports tests, written into a temp directory.

Three PRDs, shaped to exercise what the real record has and the edges it does
not have yet:

- PRD-001: two done stories with reports on different dates, and one report
  whose frontmatter is broken YAML -- it must be skipped, not fatal.
- PRD-002: one done story with a report, one in-progress story with no report,
  and one `todo` story with no report.
- PRD-003: a board and nothing else -- a PRD with no stories yet.
"""

from pathlib import Path


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _board(prd: str, name: str, rows: list[tuple[str, str, str, str]]) -> str:
    lines = "\n".join(
        f"| {sid} | {title} | feature | {icon} {status} | small | — | {commit} |"
        for sid, title, status, commit in rows
        for icon in [{"done": "✅", "in-progress": "🟡", "todo": "⬜"}[status]]
    )
    return f"""# {prd}: {name} — Story Board

**PRD**: [PRD.md](./PRD.md)

## Progress

x/y stories done

## Stories

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
{lines}

## Status Icons
- ✅ done
"""


def _story(sid: str, prd: str, title: str, status: str, updated: str, commit: str = "null") -> str:
    return f"""---
id: {sid}
prd: {prd}
title: "{title}"
status: {status}
plan: .agents/plans/{prd}/{sid}.plan.md
commit: {commit}
updated: {updated}
---

# {sid}: {title}
"""


def _report(sid: str, prd: str, commit: str, completed: str, summary: str) -> str:
    return f"""---
story: {sid}
prd: {prd}
plan: .agents/plans/{prd}/completed/{sid}.plan.md
epic_branch: epic/{prd}
commit: {commit}
status: COMPLETE
completed: {completed}
---

# Implementation Report — {sid}: ignored when the story has a title

## Summary

{summary}
It continues on a **second line** of the *same* paragraph.

A second paragraph that the card does not show.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Do it | `a.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `pytest -q` | ✅ 12 passed |
| Manual check | ❌ failed once |
| Lint | skipped |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/a.py` | CREATE | +40 |
| `tests/test_a.py` | UPDATE | +12/-3 |

## Deviations from Plan

None.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_a.py` | one |

## Acceptance Criteria

- [x] **AC 1** — the first criterion
- [ ] AC 2 — the second, unchecked
"""


def build_agents_tree(root: Path) -> Path:
    """Write the fixture under `root/.agents` and return that directory."""
    agents = root / ".agents"

    _write(
        agents / "PRDs/PRD-001-alpha/index.md",
        _board(
            "PRD-001",
            "Alpha Platform",
            [
                ("STORY-001", "Scaffold", "done", "`aaaaaaa`"),
                ("STORY-002", "Audit schema", "done", "`bbbbbbb`"),
                ("STORY-003", "Broken one", "done", "`ccccccc`"),
            ],
        ),
    )
    _write(agents / "stories/PRD-001-alpha/STORY-001-scaffold.md",
           _story("STORY-001", "PRD-001", "Scaffold the project", "done", "2026-07-04", "aaaaaaa"))
    _write(agents / "stories/PRD-001-alpha/STORY-002-audit-schema.md",
           _story("STORY-002", "PRD-001", "Audit schema", "done", "2026-07-06", "bbbbbbb"))
    _write(agents / "reports/PRD-001-alpha/STORY-001-scaffold.report.md",
           _report("STORY-001", "PRD-001", "aaaaaaa", "2026-07-04", "Scaffolded the FastAPI app."))
    _write(agents / "reports/PRD-001-alpha/STORY-002-audit-schema.report.md",
           _report("STORY-002", "PRD-001", "bbbbbbb", "2026-07-06", "Created the audit_logs table."))
    # Unterminated flow sequence: yaml raises on load.
    _write(
        agents / "reports/PRD-001-alpha/STORY-003-broken.report.md",
        "---\nstory: STORY-003\nprd: [PRD-001\ncommit: ccccccc\n---\n\n## Summary\n\nNever shown.\n",
    )

    _write(
        agents / "PRDs/PRD-002-beta/index.md",
        _board(
            "PRD-002",
            "Beta Chat",
            [
                ("STORY-001", "Chat components", "done", "`ddddddd`"),
                ("STORY-002", "Session rail", "in-progress", "—"),
                ("STORY-003", "Docs", "todo", "—"),
            ],
        ),
    )
    _write(agents / "stories/PRD-002-beta/STORY-001-chat-components.md",
           _story("STORY-001", "PRD-002", "Chat components", "done", "2026-08-01", "ddddddd"))
    _write(agents / "stories/PRD-002-beta/STORY-002-session-rail.md",
           _story("STORY-002", "PRD-002", "Session rail", "in-progress", "2026-08-03"))
    _write(agents / "stories/PRD-002-beta/STORY-003-docs.md",
           _story("STORY-003", "PRD-002", "Write the docs", "todo", "2026-07-30"))
    _write(agents / "reports/PRD-002-beta/STORY-001-chat-components.report.md",
           _report("STORY-001", "PRD-002", "ddddddd", "2026-08-01", "Built the chat components."))

    _write(agents / "PRDs/PRD-003-gamma/index.md", _board("PRD-003", "Gamma Later", []))
    return agents
