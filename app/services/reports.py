"""Read-only access to the delivery record under `.agents/`.

The Reports section renders what the story workflow already writes to disk:

    .agents/PRDs/{PRD-ID}-{slug}/index.md                   the story board
    .agents/stories/{PRD-ID}-{slug}/{STORY-ID}-{slug}.md    one story, frontmatter first
    .agents/reports/{PRD-ID}-{slug}/{STORY-ID}-{slug}.report.md

**This module is the only reader.** No Reflex component or state touches the
filesystem; they call `list_prds()`, `list_stories()` and `get_story_detail()`
and render what comes back. That seam is what lets the source move (a cache
service, a git blob store) without a UI change.

**Identifiers in, folders resolved here.** Callers pass the short id in any
case -- `prd-008`, `PRD-008`, `story-019` -- and the folder is found by prefix,
so a URL never has to repeat a slug and a renamed slug never breaks a link.

**One bad file costs one entry, never the page.** A report whose frontmatter
does not parse is logged and skipped; the rest of the feed still renders. The
two failures the UI must tell apart are kept apart here:

- `.agents/reports` (or the whole `.agents`) is absent -> empty results. That is
  a project with nothing completed yet, not a fault.
- The directory exists but cannot be listed -> `ReportsReadError`. An empty feed
  in that case would say "nothing done yet" about a project that has shipped
  eight PRDs.

**Not a markdown parser.** The report sections are fixed by the workflow
(`## Summary`, `## Files Changed`, `## Validation Results`, `## Acceptance
Criteria`, ...), so each is located by its heading and read in the one shape
the workflow writes it in: a paragraph, a header-named table, a checklist.

**Caching.** Parsing is ~270 small files; the result is kept in memory and
rebuilt when the signature changes -- the mtimes of every directory *and* file
involved. Directory mtimes alone would catch a new report but not an edit to an
existing one, and the extra `stat` calls are what a `scandir` already returns.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from pathlib import Path

import frontmatter

from app.config import settings

logger = logging.getLogger(__name__)

# --- Public vocabulary ---------------------------------------------------

STATUS_DONE = "done"
STATUS_IN_PROGRESS = "in-progress"
STATUS_PLANNED = "planned"
STATUS_BLOCKED = "blocked"

#: Every status a card can carry, in the order a filter lists them.
STATUSES = (STATUS_DONE, STATUS_IN_PROGRESS, STATUS_PLANNED, STATUS_BLOCKED)

# The workflow writes `todo` on a story that has not started; the section calls
# it *planned*, which is the word a reader of release notes expects.
_STATUS_ALIASES = {
    "done": STATUS_DONE,
    "complete": STATUS_DONE,
    "completed": STATUS_DONE,
    "in-progress": STATUS_IN_PROGRESS,
    "in_progress": STATUS_IN_PROGRESS,
    "progress": STATUS_IN_PROGRESS,
    "todo": STATUS_PLANNED,
    "planned": STATUS_PLANNED,
    "blocked": STATUS_BLOCKED,
}


class ReportsReadError(Exception):
    """The record exists but could not be read (permissions, not a directory)."""


@dataclass(frozen=True)
class PrdSummary:
    id: str  # "PRD-008"
    slug: str  # "prd-008", the URL segment
    name: str
    total: int
    done: int
    pct: int


@dataclass(frozen=True)
class StoryRef:
    story_id: str
    slug: str
    title: str


@dataclass(frozen=True)
class StoryCard:
    story_id: str  # "STORY-019"
    slug: str  # "story-019"
    prd_id: str
    prd_slug: str
    prd_name: str
    title: str
    status: str
    date: str  # ISO date: `completed` from the report, else the story's `updated`
    commit: str  # first SHA only; `commits` holds all of them
    commits: tuple[str, ...]
    summary: str  # first paragraph of `## Summary`, "" when there is no report


@dataclass(frozen=True)
class FileChange:
    path: str
    action: str
    detail: str


@dataclass(frozen=True)
class ValidationRow:
    check: str
    result: str
    passed: bool | None  # None when the result carries neither mark


@dataclass(frozen=True)
class CriterionItem:
    text: str
    checked: bool


@dataclass(frozen=True)
class StoryDetail:
    card: StoryCard
    has_report: bool
    plan: str
    summary: tuple[str, ...]  # every paragraph of `## Summary`
    acceptance: tuple[CriterionItem, ...]
    files: tuple[FileChange, ...]
    validation: tuple[ValidationRow, ...]
    prev: StoryRef | None
    next: StoryRef | None


# --- Filesystem layout ---------------------------------------------------

_PRD_ID = re.compile(r"^(PRD-\d+)", re.IGNORECASE)
_STORY_ID = re.compile(r"^(STORY-\d+)", re.IGNORECASE)
_SHA = re.compile(r"\b[0-9a-f]{7,40}\b")


def default_root() -> Path:
    """`settings.REPORTS_AGENTS_DIR`, or `.agents` at the repository root."""
    configured = settings.REPORTS_AGENTS_DIR.strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / ".agents"


def commit_url(sha: str) -> str:
    """The commit on the hosted repository, or "" for no commit."""
    if not sha:
        return ""
    return f"{settings.REPORTS_REPO_URL.rstrip('/')}/commit/{sha}"


def _canonical_prd(value: str) -> str | None:
    match = _PRD_ID.match(value.strip())
    return match.group(1).upper() if match else None


def _canonical_story(value: str) -> str | None:
    match = _STORY_ID.match(value.strip())
    return match.group(1).upper() if match else None


def _number(identifier: str) -> int:
    digits = re.search(r"\d+", identifier)
    return int(digits.group()) if digits else 0


def _scan(directory: Path) -> list[os.DirEntry]:
    """Entries of `directory`; [] when it does not exist, raises when unreadable."""
    try:
        with os.scandir(directory) as entries:
            return sorted(entries, key=lambda entry: entry.name)
    except FileNotFoundError:
        return []
    except OSError as exc:  # PermissionError, NotADirectoryError, ...
        raise ReportsReadError(f"cannot list {directory}: {exc}") from exc


# --- Section extraction --------------------------------------------------

_INLINE_MARKS = re.compile(r"(\*\*|__|`)")
_SINGLE_EMPHASIS = re.compile(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])")


def _plain(text: str) -> str:
    """Inline emphasis and code marks removed; everything else left as written."""
    return _SINGLE_EMPHASIS.sub(r"\1", _INLINE_MARKS.sub("", text)).strip()


def _section(body: str, heading: str) -> str:
    """The text under `## {heading}`, up to the next `## ` heading."""
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(body)
    return match.group(1).strip("\n") if match else ""


_FENCE = re.compile(r"^```.*?^```[^\n]*$", re.MULTILINE | re.DOTALL)


def _paragraphs(section: str) -> list[str]:
    """Prose paragraphs, joined line by line; tables, lists and fences skipped."""
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", _FENCE.sub("", section)):
        lines = [line.strip() for line in block.strip().splitlines()]
        if lines and not lines[0].startswith(("|", "- ", "* ", "#", ">")):
            paragraphs.append(_plain(" ".join(lines)))
    return [p for p in paragraphs if p]


def _table(section: str) -> tuple[list[str], list[list[str]]]:
    """The first pipe table in a section, as (lower-cased headers, rows)."""
    lines = [line.strip() for line in section.splitlines()]
    table: list[list[str]] = []
    for line in lines:
        if line.startswith("|"):
            table.append([cell.strip() for cell in line.strip("|").split("|")])
        elif table:
            break
    if len(table) < 2:
        return [], []
    headers = [cell.lower() for cell in table[0]]
    rows = [row for row in table[1:] if not all(re.fullmatch(r":?-+:?", c) for c in row if c)]
    return headers, rows


def _column(headers: list[str], name: str, default: int) -> int:
    return headers.index(name) if name in headers else default


def _files(section: str) -> list[FileChange]:
    headers, rows = _table(section)
    if not headers:
        return []
    path_at = _column(headers, "file", 0)
    action_at = _column(headers, "action", 1)
    changes = []
    for row in rows:
        cells = row + [""] * (len(headers) - len(row))
        detail = " · ".join(
            _plain(cells[i]) for i in range(len(headers)) if i not in (path_at, action_at) and cells[i]
        )
        changes.append(
            FileChange(
                path=_plain(cells[path_at]),
                action=_plain(cells[action_at]).upper() if action_at < len(cells) else "",
                detail=detail,
            )
        )
    return [change for change in changes if change.path]


def _validation(section: str) -> list[ValidationRow]:
    headers, rows = _table(section)
    if not headers:
        return []
    check_at = _column(headers, "check", 0)
    result_at = _column(headers, "result", len(headers) - 1)
    results = []
    for row in rows:
        cells = row + [""] * (len(headers) - len(row))
        raw = cells[result_at]
        passed = True if "✅" in raw else False if ("❌" in raw or "✗" in raw) else None
        result = _plain(raw.replace("✅", "").replace("❌", ""))
        results.append(ValidationRow(check=_plain(cells[check_at]), result=result, passed=passed))
    return [row for row in results if row.check]


_CHECKBOX = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*]\s+(.*)$")


def _criteria(section: str) -> list[CriterionItem]:
    items = []
    for line in section.splitlines():
        if match := _CHECKBOX.match(line):
            items.append(CriterionItem(text=_plain(match.group(2)), checked=match.group(1) != " "))
        elif (match := _BULLET.match(line)) and not line.startswith(" "):
            items.append(CriterionItem(text=_plain(match.group(1)), checked=False))
    return [item for item in items if item.text]


# --- Parsing one PRD -----------------------------------------------------


def _iso(value) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip() if value else ""


def _commits(value) -> tuple[str, ...]:
    return tuple(_SHA.findall(str(value))) if value else ()


def _load(path: Path) -> frontmatter.Post | None:
    """A parsed file, or None -- logged -- when its frontmatter does not parse."""
    try:
        return frontmatter.load(path)
    except Exception as exc:  # noqa: BLE001 -- yaml raises a family, not one type
        logger.warning("reports: skipping %s: %s", path, exc)
        return None


@dataclass
class _Story:
    story_id: str
    title: str = ""
    status: str = ""
    date: str = ""
    commits: tuple[str, ...] = ()
    plan: str = ""
    report_body: str | None = None


@dataclass
class _Prd:
    id: str
    name: str
    board: dict[str, tuple[str, str]] = field(default_factory=dict)  # id -> (title, status)
    stories: dict[str, _Story] = field(default_factory=dict)


_BOARD_ROW = re.compile(r"^\|\s*(STORY-\d+)\s*\|\s*(.*?)\s*\|", re.IGNORECASE)
_BOARD_STATUS = re.compile(r"\b(done|in-progress|todo|blocked)\b", re.IGNORECASE)


def _read_board(prd: _Prd, index: Path) -> None:
    post = _load(index)
    if post is None:
        return
    heading = re.search(r"^#\s+(.+)$", post.content, re.MULTILINE)
    if heading:
        name = re.sub(r"\s+—\s+Story Board\s*$", "", heading.group(1)).strip()
        prd.name = re.sub(r"^PRD-\d+[\w-]*:\s*", "", name) or prd.name
    headers, rows = _table(_section(post.content, "Stories"))
    status_at = _column(headers, "status", 3)
    for row in rows:
        story_id = _canonical_story(row[0]) if row else None
        if not story_id or len(row) <= status_at:
            continue
        status = _BOARD_STATUS.search(row[status_at])
        title = row[_column(headers, "title", 1)] if len(row) > 1 else ""
        prd.board[story_id] = (_plain(title), status.group(1).lower() if status else "")


def _read_story(prd: _Prd, path: Path) -> None:
    post = _load(path)
    if post is None:
        return
    story_id = _canonical_story(str(post.get("id") or path.name))
    if not story_id:
        return
    story = prd.stories.setdefault(story_id, _Story(story_id))
    story.title = str(post.get("title") or "").strip() or story.title
    story.status = str(post.get("status") or "").strip() or story.status
    story.date = story.date or _iso(post.get("updated"))
    story.commits = story.commits or _commits(post.get("commit"))
    story.plan = story.plan or str(post.get("plan") or "")


def _read_report(prd: _Prd, path: Path) -> None:
    post = _load(path)
    if post is None:
        return
    story_id = _canonical_story(str(post.get("story") or path.name))
    if not story_id:
        logger.warning("reports: skipping %s: no story id", path)
        return
    story = prd.stories.setdefault(story_id, _Story(story_id))
    story.report_body = post.content
    story.date = _iso(post.get("completed")) or story.date
    story.commits = _commits(post.get("commit")) or story.commits
    story.plan = str(post.get("plan") or "") or story.plan
    if not story.status and str(post.get("status") or "").upper() == "COMPLETE":
        story.status = STATUS_DONE
    if not story.title:
        heading = re.search(r"^#\s+.*?STORY-\d+:\s*(.+)$", post.content, re.MULTILINE)
        story.title = heading.group(1).strip() if heading else ""


# --- The corpus and its cache --------------------------------------------


@dataclass(frozen=True)
class _Corpus:
    prds: tuple[PrdSummary, ...]
    cards: tuple[StoryCard, ...]  # feed order
    details: dict[str, StoryDetail]  # "PRD-008/STORY-019" -> detail


def _prd_folders(root: Path) -> dict[str, dict[str, Path]]:
    """{kind: {PRD-ID: folder}} for the three trees the section reads."""
    folders: dict[str, dict[str, Path]] = {}
    for kind in ("PRDs", "stories", "reports"):
        found: dict[str, Path] = {}
        for entry in _scan(root / kind):
            prd_id = _canonical_prd(entry.name)
            if prd_id and entry.is_dir():
                found.setdefault(prd_id, Path(entry.path))
        folders[kind] = found
    return folders


def _signature(root: Path) -> tuple:
    """Every directory and file mtime the corpus depends on.

    `os.stat` on the path, never `DirEntry.stat()`: on Windows the latter returns
    the timestamp cached in the *parent's* directory index, which NTFS updates
    lazily, so a folder written moments ago reports an mtime that shifts on the
    next listing and the cache would miss on every request.
    """
    stamps: list[tuple[str, int]] = []
    for kind in ("PRDs", "stories", "reports"):
        base = root / kind
        for entry in _scan(base):
            if not entry.is_dir():
                continue
            stamps.append((entry.path, _mtime(entry.path)))
            for child in _scan(Path(entry.path)):
                if child.name.endswith(".md"):
                    stamps.append((child.path, _mtime(child.path)))
    return tuple(stamps)


def _mtime(path: str) -> int:
    try:
        return os.stat(path).st_mtime_ns
    except FileNotFoundError:  # removed between the listing and the stat
        return -1


def _build(root: Path) -> _Corpus:
    folders = _prd_folders(root)
    prds: dict[str, _Prd] = {}
    for prd_id in sorted(set().union(*(f.keys() for f in folders.values())), key=_number):
        prd = prds[prd_id] = _Prd(prd_id, prd_id)
        if board := folders["PRDs"].get(prd_id):
            if (board / "index.md").is_file():
                _read_board(prd, board / "index.md")
        if stories := folders["stories"].get(prd_id):
            for entry in _scan(stories):
                if entry.name.endswith(".md") and _canonical_story(entry.name):
                    _read_story(prd, Path(entry.path))
        if reports := folders["reports"].get(prd_id):
            for entry in _scan(reports):
                if entry.name.endswith(".report.md"):
                    _read_report(prd, Path(entry.path))

    summaries: list[PrdSummary] = []
    cards: list[StoryCard] = []
    details: dict[str, StoryDetail] = {}
    for prd in prds.values():
        # The board is the PRD's own tally; stories on disk are the fallback
        # for a PRD whose index.md is missing or unreadable.
        tally = prd.board or {sid: (s.title, s.status) for sid, s in prd.stories.items()}
        total = len(tally)
        done = sum(1 for _, status in tally.values() if _normalize(status) == STATUS_DONE)
        summaries.append(
            PrdSummary(
                id=prd.id,
                slug=prd.id.lower(),
                name=prd.name,
                total=total,
                done=done,
                pct=round(done * 100 / total) if total else 0,
            )
        )

        ordered = sorted(prd.stories.values(), key=lambda s: _number(s.story_id))
        prd_cards = []
        for story in ordered:
            board_title, board_status = prd.board.get(story.story_id, ("", ""))
            body = story.report_body or ""
            summary = _paragraphs(_section(body, "Summary"))
            card = StoryCard(
                story_id=story.story_id,
                slug=story.story_id.lower(),
                prd_id=prd.id,
                prd_slug=prd.id.lower(),
                prd_name=prd.name,
                title=story.title or board_title or story.story_id,
                status=_normalize(story.status or board_status) or STATUS_PLANNED,
                date=story.date,
                commit=story.commits[0] if story.commits else "",
                commits=story.commits,
                summary=summary[0] if summary else "",
            )
            prd_cards.append(card)
            details[f"{prd.id}/{story.story_id}"] = StoryDetail(
                card=card,
                has_report=story.report_body is not None,
                plan=story.plan,
                summary=tuple(summary),
                acceptance=tuple(_criteria(_section(body, "Acceptance Criteria"))),
                files=tuple(_files(_section(body, "Files Changed"))),
                validation=tuple(_validation(_section(body, "Validation Results"))),
                prev=None,
                next=None,
            )
        for i, card in enumerate(prd_cards):
            key = f"{prd.id}/{card.story_id}"
            ref = lambda c: StoryRef(c.story_id, c.slug, c.title)  # noqa: E731
            details[key] = replace(
                details[key],
                prev=ref(prd_cards[i - 1]) if i > 0 else None,
                next=ref(prd_cards[i + 1]) if i + 1 < len(prd_cards) else None,
            )
        cards.extend(prd_cards)

    # Newest first; within a day, the later PRD and the later story first, so
    # a day's work reads in the order it was merged.
    cards.sort(key=lambda c: (c.date, _number(c.prd_id), _number(c.story_id)), reverse=True)
    return _Corpus(prds=tuple(summaries), cards=tuple(cards), details=details)


def _normalize(status: str) -> str:
    return _STATUS_ALIASES.get(status.strip().lower(), "") if status else ""


_lock = threading.Lock()
_cache: dict[Path, tuple[tuple, _Corpus]] = {}


def _corpus(root: Path | None) -> _Corpus:
    root = (root or default_root()).resolve()
    if root.exists() and not root.is_dir():
        raise ReportsReadError(f"{root} is not a directory")
    signature = _signature(root)
    with _lock:
        cached = _cache.get(root)
        if cached and cached[0] == signature:
            return cached[1]
    corpus = _build(root)
    with _lock:
        _cache[root] = (signature, corpus)
    return corpus


def clear_cache() -> None:
    with _lock:
        _cache.clear()


# --- Public API ----------------------------------------------------------


def normalize_status(value: str | None) -> str | None:
    """A filter value as one of `STATUSES`, or None for "every status"."""
    return _normalize(value or "") or None


def list_prds(root: Path | None = None) -> list[PrdSummary]:
    """Every PRD with a board, stories or reports, in PRD order."""
    return list(_corpus(root).prds)


def list_stories(
    prd_id: str | None = None,
    status: str | None = None,
    q: str | None = None,
    root: Path | None = None,
) -> list[StoryCard]:
    """The feed: newest first, optionally narrowed to one PRD, one status and a text.

    An unknown `prd_id` returns [] rather than the whole feed -- a link to a PRD
    that does not exist should not quietly show every other one. An unknown
    `status` is ignored, the way an absent one is.
    """
    cards = _corpus(root).cards
    if prd_id:
        wanted = _canonical_prd(prd_id)
        cards = tuple(c for c in cards if c.prd_id == wanted)
    if wanted_status := normalize_status(status):
        cards = tuple(c for c in cards if c.status == wanted_status)
    if needle := (q or "").strip().lower():
        cards = tuple(
            c
            for c in cards
            if needle
            in " ".join((c.story_id, c.title, c.prd_id, c.prd_name, *c.commits)).lower()
        )
    return list(cards)


def get_story_detail(prd_id: str, story_id: str, root: Path | None = None) -> StoryDetail | None:
    """One story in full, with its neighbours in the same PRD; None when unknown."""
    prd, story = _canonical_prd(prd_id or ""), _canonical_story(story_id or "")
    if not prd or not story:
        return None
    return _corpus(root).details.get(f"{prd}/{story}")
