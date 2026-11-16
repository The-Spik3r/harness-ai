"""Regenerate a PRD's story board (index.md) and validate its stories.

Usage (from the repo root):
    PYTHONIOENCODING=utf-8 .venv/Scripts/python .agents/scripts/gen_index.py <PRD-ID | PRD dir>

Writes `.agents/PRDs/{PRD-ID}-{slug}/index.md` in the format of
`create-stories.md` Phase 5 and prints `errors: none | count: N` when every
story has the full frontmatter, the same epic branch as the PRD, and a
consistent depends_on/blocks DAG. Any other `errors:` line is a failure; the
script exits 1 so callers can gate on it.
"""

import glob
import os
import sys

import frontmatter

REQUIRED = [
    "id", "prd", "slug", "title", "type", "priority", "complexity", "phase",
    "status", "labels", "epic_branch", "plan", "report", "commit",
    "depends_on", "blocks", "skills", "created", "updated",
]
ICON = {"todo": "⬜", "in-progress": "🟡", "done": "✅", "blocked": "🔴"}


def resolve_prd_dir(arg: str) -> str:
    if os.path.isdir(arg):
        return os.path.normpath(arg)
    matches = glob.glob(os.path.join(".agents", "PRDs", f"{arg}-*"))
    if len(matches) != 1:
        sys.exit(f"errors: cannot resolve PRD {arg!r} (matches: {matches})")
    return matches[0]


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    prd_dir = resolve_prd_dir(sys.argv[1])
    name = os.path.basename(prd_dir)
    prd = frontmatter.load(os.path.join(prd_dir, "PRD.md")).metadata
    files = sorted(glob.glob(os.path.join(".agents", "stories", name, "STORY-*.md")))
    stories = [frontmatter.load(f).metadata for f in files]
    if not stories:
        sys.exit(f"errors: no stories under .agents/stories/{name}/")

    by_id = {s.get("id"): s for s in stories}
    errs = []
    for s in stories:
        sid = s.get("id", "?")
        errs += [f"{sid} missing {k}" for k in REQUIRED if k not in s]
        if s.get("epic_branch") != prd.get("epic_branch"):
            errs.append(f"{sid} epic_branch differs from the PRD")
        if s.get("status") not in ICON:
            errs.append(f"{sid} unknown status {s.get('status')!r}")
        for dep in s.get("depends_on") or []:
            if dep not in by_id:
                errs.append(f"{sid} unknown dep {dep}")
                continue
            if sid not in (by_id[dep].get("blocks") or []):
                errs.append(f"{dep} does not list {sid} in blocks")
            if dep >= sid:
                errs.append(f"{sid} depends on later {dep}")
        for b in s.get("blocks") or []:
            if b not in by_id:
                errs.append(f"{sid} blocks unknown {b}")
            elif sid not in (by_id[b].get("depends_on") or []):
                errs.append(f"{b} does not depend on {sid}")

    done = sum(s.get("status") == "done" for s in stories)
    lines = [
        f"# {prd['id']}-{prd['slug']}: {prd['title']} — Story Board", "",
        "**PRD**: [PRD.md](./PRD.md)",
        f"**Epic Branch**: `{prd['epic_branch']}` (base: `{prd['base_branch']}`)",
        f"**Status**: {'done' if done == len(stories) else 'active'}", "",
        "## Progress", "",
        f"{done}/{len(stories)} stories done — {round(100 * done / len(stories))}%", "",
        "## Stories", "",
        f"All stories commit on the epic branch `{prd['epic_branch']}`. No per-story branches.", "",
        "| ID | Title | Type | Status | Complexity | Plan | Commit |",
        "|----|-------|------|--------|------------|------|--------|",
    ]
    for s in stories:
        plan = s.get("plan")
        plan_cell = f"[plan](../../{plan.split('.agents/', 1)[1]})" if plan else "—"
        commit_cell = f"`{s['commit']}`" if s.get("commit") else "—"
        status = s.get("status")
        lines.append(
            f"| {s.get('id')} | {s.get('title')} | {s.get('type')} | "
            f"{ICON.get(status, '?')} {status} | {s.get('complexity')} | {plan_cell} | {commit_cell} |"
        )
    lines += ["", "## Status Icons", "- ⬜ todo", "- 🟡 in-progress", "- ✅ done", "- 🔴 blocked", "",
              "## Dependencies", ""]
    lines += [f"- {s['id']} blocked by {', '.join(s['depends_on'])}" for s in stories if s.get("depends_on")]

    with open(os.path.join(prd_dir, "index.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print("errors:", errs or "none", "| count:", len(stories))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
