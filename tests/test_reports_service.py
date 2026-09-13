"""`app/services/reports.py` against a fixture `.agents/` tree.

The service is the only reader of the delivery record, so its three functions
carry every claim the Reports pages make about data: order, filters, the
detail's sections, and -- the two that matter most -- that one broken file costs
one entry and that an absent record is empty rather than a fault.

Every test passes `root` explicitly and clears the cache first, so nothing here
reads the repository's real `.agents/`.
"""

import logging
import os

import pytest

from app.services import reports
from tests.reports_fixture import build_agents_tree


@pytest.fixture
def agents(tmp_path):
    reports.clear_cache()
    yield build_agents_tree(tmp_path)
    reports.clear_cache()


def _keys(cards):
    return [f"{c.prd_id}/{c.story_id}" for c in cards]


# --- list_prds ---------------------------------------------------------------


def test_list_prds_reads_every_board_in_prd_order(agents):
    prds = reports.list_prds(root=agents)
    assert [p.id for p in prds] == ["PRD-001", "PRD-002", "PRD-003"]
    assert [p.slug for p in prds] == ["prd-001", "prd-002", "prd-003"]
    assert [p.name for p in prds] == ["Alpha Platform", "Beta Chat", "Gamma Later"]


def test_list_prds_counts_from_the_board(agents):
    alpha, beta, gamma = reports.list_prds(root=agents)
    # The board says three done even though one report is unreadable: the tally
    # is the board's, the feed is the files'.
    assert (alpha.total, alpha.done, alpha.pct) == (3, 3, 100)
    assert (beta.total, beta.done, beta.pct) == (3, 1, 33)
    assert (gamma.total, gamma.done, gamma.pct) == (0, 0, 0)


# --- list_stories: order -----------------------------------------------------


def test_feed_is_newest_first_across_prds(agents):
    assert _keys(reports.list_stories(root=agents)) == [
        "PRD-002/STORY-002",  # updated 2026-08-03, no report yet
        "PRD-002/STORY-001",  # completed 2026-08-01
        "PRD-002/STORY-003",  # updated 2026-07-30
        "PRD-001/STORY-002",  # completed 2026-07-06
        "PRD-001/STORY-001",  # completed 2026-07-04
    ]


def test_same_day_ties_break_by_prd_then_story_descending(tmp_path):
    reports.clear_cache()
    agents = build_agents_tree(tmp_path)
    story = agents / "stories/PRD-001-alpha/STORY-002-audit-schema.md"
    report = agents / "reports/PRD-001-alpha/STORY-002-audit-schema.report.md"
    report.write_text(report.read_text(encoding="utf-8").replace("2026-07-06", "2026-07-04"), encoding="utf-8")
    story.write_text(story.read_text(encoding="utf-8").replace("2026-07-06", "2026-07-04"), encoding="utf-8")
    keys = _keys(reports.list_stories(prd_id="prd-001", root=agents))
    assert keys == ["PRD-001/STORY-002", "PRD-001/STORY-001"]


def test_card_fields(agents):
    card = next(c for c in reports.list_stories(root=agents) if c.story_id == "STORY-001" and c.prd_id == "PRD-001")
    assert card.title == "Scaffold the project"  # the story's title wins over the report heading
    assert card.slug == "story-001" and card.prd_slug == "prd-001"
    assert card.prd_name == "Alpha Platform"
    assert card.status == "done"
    assert card.date == "2026-07-04"
    assert card.commit == "aaaaaaa"
    # First paragraph only, lines joined, emphasis marks removed.
    assert card.summary == "Scaffolded the FastAPI app. It continues on a second line of the same paragraph."


def test_a_story_without_a_report_has_no_summary_and_keeps_its_status(agents):
    by_key = {f"{c.prd_id}/{c.story_id}": c for c in reports.list_stories(root=agents)}
    assert by_key["PRD-002/STORY-002"].status == "in-progress"
    assert by_key["PRD-002/STORY-002"].summary == ""
    assert by_key["PRD-002/STORY-003"].status == "planned"  # `todo` reads as planned


# --- list_stories: filters -----------------------------------------------------


@pytest.mark.parametrize("prd_id", ["prd-002", "PRD-002", "Prd-002", "PRD-002-beta"])
def test_prd_filter_accepts_the_short_id_in_any_case(agents, prd_id):
    assert {c.prd_id for c in reports.list_stories(prd_id=prd_id, root=agents)} == {"PRD-002"}


def test_unknown_prd_is_empty_not_the_whole_feed(agents):
    assert reports.list_stories(prd_id="prd-999", root=agents) == []
    assert reports.list_stories(prd_id="not-a-prd", root=agents) == []


@pytest.mark.parametrize("prd_id", [None, ""])
def test_no_prd_means_every_prd(agents, prd_id):
    assert len(reports.list_stories(prd_id=prd_id, root=agents)) == 5


@pytest.mark.parametrize(
    "status, expected",
    [
        ("done", ["PRD-002/STORY-001", "PRD-001/STORY-002", "PRD-001/STORY-001"]),
        ("in-progress", ["PRD-002/STORY-002"]),
        ("planned", ["PRD-002/STORY-003"]),
        ("todo", ["PRD-002/STORY-003"]),
    ],
)
def test_status_filter(agents, status, expected):
    assert _keys(reports.list_stories(status=status, root=agents)) == expected


@pytest.mark.parametrize("status", [None, "", "all", "nonsense"])
def test_absent_or_unknown_status_filters_nothing(agents, status):
    assert len(reports.list_stories(status=status, root=agents)) == 5


@pytest.mark.parametrize(
    "q, expected",
    [
        ("scaffold", ["PRD-001/STORY-001"]),  # title, case-insensitive
        ("STORY-002", ["PRD-002/STORY-002", "PRD-001/STORY-002"]),  # story id
        ("bbbbbbb", ["PRD-001/STORY-002"]),  # commit
        ("prd-001", ["PRD-001/STORY-002", "PRD-001/STORY-001"]),  # PRD id
        ("beta chat", ["PRD-002/STORY-002", "PRD-002/STORY-001", "PRD-002/STORY-003"]),  # PRD name
        ("   ", None),  # blank is no filter
        ("zzz-no-match", []),
    ],
)
def test_text_filter(agents, q, expected):
    keys = _keys(reports.list_stories(q=q, root=agents))
    assert keys == (expected if expected is not None else _keys(reports.list_stories(root=agents)))


def test_filters_combine(agents):
    keys = _keys(reports.list_stories(prd_id="prd-002", status="done", q="chat", root=agents))
    assert keys == ["PRD-002/STORY-001"]


# --- Faults ------------------------------------------------------------------


def test_broken_frontmatter_is_skipped_and_logged_without_breaking_the_feed(agents, caplog):
    with caplog.at_level(logging.WARNING, logger="app.services.reports"):
        cards = reports.list_stories(root=agents)
    assert "PRD-001/STORY-003" not in _keys(cards)
    assert len(cards) == 5
    assert any("STORY-003-broken.report.md" in record.getMessage() for record in caplog.records)
    assert reports.get_story_detail("prd-001", "story-003", root=agents) is None


def test_missing_reports_folder_is_empty_not_an_error(agents):
    for path in sorted((agents / "reports").rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    (agents / "reports").rmdir()
    # Stories on disk still show, as stories without a report.
    cards = reports.list_stories(root=agents)
    assert cards and all(c.summary == "" for c in cards)


def test_missing_agents_directory_is_empty_not_an_error(tmp_path):
    reports.clear_cache()
    absent = tmp_path / "nowhere" / ".agents"
    assert reports.list_prds(root=absent) == []
    assert reports.list_stories(root=absent) == []
    assert reports.get_story_detail("prd-001", "story-001", root=absent) is None


def test_an_unreadable_record_raises_rather_than_reading_as_empty(tmp_path):
    reports.clear_cache()
    not_a_directory = tmp_path / "agents-file"
    not_a_directory.write_text("", encoding="utf-8")
    with pytest.raises(reports.ReportsReadError):
        reports.list_stories(root=not_a_directory)


def test_an_unlistable_reports_folder_raises(agents, monkeypatch):
    real_scandir = os.scandir

    def scandir(path):
        if str(path).endswith("reports"):
            raise PermissionError("denied")
        return real_scandir(path)

    monkeypatch.setattr(reports.os, "scandir", scandir)
    with pytest.raises(reports.ReportsReadError):
        reports.list_stories(root=agents)


# --- get_story_detail ----------------------------------------------------------


def test_detail_sections(agents):
    detail = reports.get_story_detail("prd-001", "story-002", root=agents)
    assert detail is not None and detail.has_report
    assert detail.card.story_id == "STORY-002"
    assert detail.plan == ".agents/plans/PRD-001/completed/STORY-002.plan.md"
    assert detail.summary == (
        "Created the audit_logs table. It continues on a second line of the same paragraph.",
        "A second paragraph that the card does not show.",
    )
    assert [(c.text, c.checked) for c in detail.acceptance] == [
        ("AC 1 — the first criterion", True),
        ("AC 2 — the second, unchecked", False),
    ]
    assert [(f.path, f.action, f.detail) for f in detail.files] == [
        ("app/a.py", "CREATE", "+40"),
        ("tests/test_a.py", "UPDATE", "+12/-3"),
    ]
    assert [(v.check, v.result, v.passed) for v in detail.validation] == [
        ("pytest -q", "12 passed", True),
        ("Manual check", "failed once", False),
        ("Lint", "skipped", None),
    ]


def test_detail_neighbours_are_by_story_id_within_the_prd(agents):
    first = reports.get_story_detail("prd-002", "story-001", root=agents)
    middle = reports.get_story_detail("prd-002", "story-002", root=agents)
    last = reports.get_story_detail("prd-002", "story-003", root=agents)
    assert first.prev is None and first.next.story_id == "STORY-002"
    assert middle.prev.story_id == "STORY-001" and middle.next.story_id == "STORY-003"
    assert last.prev.story_id == "STORY-002" and last.next is None
    assert middle.next.slug == "story-003" and middle.next.title == "Write the docs"


def test_detail_of_a_story_without_a_report(agents):
    detail = reports.get_story_detail("PRD-002", "STORY-002", root=agents)
    assert detail is not None and not detail.has_report
    assert detail.card.status == "in-progress"
    assert detail.summary == () and detail.files == () and detail.validation == ()


@pytest.mark.parametrize(
    "prd_id, story_id",
    [("prd-001", "story-999"), ("prd-999", "story-001"), ("prd-003", "story-001"), ("", ""), ("x", "y")],
)
def test_unknown_detail_is_none(agents, prd_id, story_id):
    assert reports.get_story_detail(prd_id, story_id, root=agents) is None


# --- Cache ---------------------------------------------------------------------


def test_the_cache_is_reused_while_nothing_changes(agents, monkeypatch):
    reports.list_stories(root=agents)
    calls = []
    real_build = reports._build
    monkeypatch.setattr(reports, "_build", lambda root: calls.append(root) or real_build(root))
    reports.list_stories(root=agents)
    reports.list_prds(root=agents)
    assert calls == []


def test_the_cache_is_rebuilt_when_a_report_is_edited(agents):
    assert reports.list_stories(q="rewritten", root=agents) == []
    report = agents / "reports/PRD-002-beta/STORY-001-chat-components.report.md"
    report.write_text(
        report.read_text(encoding="utf-8").replace("Built the chat components.", "Rewritten summary."),
        encoding="utf-8",
    )
    stat = report.stat()
    os.utime(report, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10_000_000))
    card = next(c for c in reports.list_stories(prd_id="prd-002", root=agents) if c.story_id == "STORY-001")
    assert card.summary.startswith("Rewritten summary.")


def test_the_cache_is_rebuilt_when_a_report_is_added(agents):
    assert reports.get_story_detail("prd-002", "story-002", root=agents).has_report is False
    source = agents / "reports/PRD-002-beta/STORY-001-chat-components.report.md"
    target = agents / "reports/PRD-002-beta/STORY-002-session-rail.report.md"
    target.write_text(source.read_text(encoding="utf-8").replace("STORY-001", "STORY-002"), encoding="utf-8")
    stat = target.parent.stat()
    os.utime(target.parent, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10_000_000))
    assert reports.get_story_detail("prd-002", "story-002", root=agents).has_report is True


# --- Configuration ---------------------------------------------------------------


def test_commit_url_uses_the_configured_repository(monkeypatch):
    monkeypatch.setattr(reports.settings, "REPORTS_REPO_URL", "https://github.com/acme/widget/")
    assert reports.commit_url("abc1234") == "https://github.com/acme/widget/commit/abc1234"
    assert reports.commit_url("") == ""


def test_default_root_is_the_repository_agents_directory(monkeypatch):
    monkeypatch.setattr(reports.settings, "REPORTS_AGENTS_DIR", "")
    assert reports.default_root().name == ".agents"
    assert (reports.default_root().parent / "app" / "services" / "reports.py").is_file()
    monkeypatch.setattr(reports.settings, "REPORTS_AGENTS_DIR", "/somewhere/else")
    assert str(reports.default_root()).replace("\\", "/").endswith("somewhere/else")
