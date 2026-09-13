"""The Reports pages: routes, on_load handlers, the state each URL lands in, and
the guards that keep the section public and palette-bound.

Three instruments, on the pattern of `tests/test_chat_shell.py` and
`tests/test_admin_shell.py`:

**Handlers in-process.** `ReportsState`'s `load_feed` / `load_detail` are driven
with a real `RouterData` built from a URL, against the fixture `.agents/` tree
(`REPORTS_AGENTS_DIR`). Each route shape is asserted by the state arm it lands
in -- cards, empty, no-match, not-found, fault -- which is what the page renders.

**The app in a subprocess.** Importing `chat_ui.chat_ui` registers the pages;
the probe checks the three routes exist, carry the right on_load, and that each
page compiles. It runs with `PYTHONPATH=chat_ui/` for the reason the other probes
give: that is how Reflex imports the app, and doing it in-process breaks every
other test module.

**Why this is the smoke test, and not an HTTP 200.** A Reflex page is served by
the compiled frontend (`reflex export` / the Node build), which the suite does
not build; the backend alone has no HTML to answer `/reports` with. What can
fail without a browser -- a route Reflex rejects, a page that raises while
compiling, an on_load that raises or lands in the wrong arm, a missing record
turning into an exception -- is all asserted here.
"""

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import reflex as rx

sys.path.insert(0, str(Path(__file__).parent.parent))

from reflex.istate.data import RouterData  # noqa: E402

from app.config import settings  # noqa: E402
from app.services import reports  # noqa: E402
from chat_ui.chat_ui import reports_copy  # noqa: E402
from chat_ui.chat_ui import reports_state as rs  # noqa: E402
from tests.reports_fixture import build_agents_tree  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTHONPATH = [str(REPO_ROOT / "chat_ui"), str(REPO_ROOT)]

REPORTS_MODULES = (
    REPO_ROOT / "chat_ui" / "chat_ui" / "components" / "reports.py",
    REPO_ROOT / "chat_ui" / "chat_ui" / "reports_state.py",
    REPO_ROOT / "chat_ui" / "chat_ui" / "reports_models.py",
    REPO_ROOT / "chat_ui" / "chat_ui" / "reports_copy.py",
)


# --- Handlers -------------------------------------------------------------------


@pytest.fixture
def agents(tmp_path, monkeypatch):
    reports.clear_cache()
    root = build_agents_tree(tmp_path)
    monkeypatch.setattr(settings, "REPORTS_AGENTS_DIR", str(root))
    yield root
    reports.clear_cache()


def _state_at(url: str) -> rs.ReportsState:
    """A `ReportsState` whose router reports `url`, the way a browser request does.

    Built through the root `rx.State`: `router` is inherited, and setting it on a
    parentless substate has nowhere to go.
    """
    root = rx.State(_reflex_internal_init=True)
    root.router = RouterData.from_router_data(
        {"headers": {"origin": "http://testserver"}, "asPath": url, "pathname": url.split("?")[0]}
    )
    return root.get_substate(rs.ReportsState.get_full_name().split("."))


def _run(state: rs.ReportsState, handler: str, *args):
    return type(state).event_handlers[handler].fn(state, *args)


def _feed(url: str) -> rs.ReportsState:
    state = _state_at(url)
    _run(state, "load_feed")
    return state


def _detail(url: str) -> rs.ReportsState:
    state = _state_at(url)
    _run(state, "load_detail")
    return state


def test_feed_route_lists_every_story_newest_first(agents):
    state = _feed("/reports")
    assert state.feed_state == rs.FEED_CARDS
    assert state.active_prd == ""
    assert [c.key for c in state.cards] == [
        "prd-002/story-002",
        "prd-002/story-001",
        "prd-002/story-003",
        "prd-001/story-002",
        "prd-001/story-001",
    ]
    assert [p.slug for p in state.prds] == ["prd-001", "prd-002", "prd-003"]


def test_feed_route_with_a_trailing_slash(agents):
    assert _feed("/reports/").feed_state == rs.FEED_CARDS


def test_card_view_is_finished_for_the_component(agents):
    card = next(c for c in _feed("/reports").cards if c.key == "prd-001/story-001")
    assert card.heading == "STORY-001 · Scaffold the project"
    assert card.href == "/reports/prd-001/story-001"
    assert card.status == "done" and card.status_label == "Done"
    assert card.date_label == "4 jul 2026"
    assert card.commit == "aaaaaaa"
    pending = next(c for c in _feed("/reports").cards if c.key == "prd-002/story-002")
    assert pending.summary == reports_copy.CARD_NO_SUMMARY


@pytest.mark.parametrize(
    "url, keys",
    [
        ("/reports?status=done", ["prd-002/story-001", "prd-001/story-002", "prd-001/story-001"]),
        ("/reports?status=in-progress", ["prd-002/story-002"]),
        ("/reports?q=scaffold", ["prd-001/story-001"]),
        ("/reports?q=bbbbbbb", ["prd-001/story-002"]),
        ("/reports?status=done&q=chat", ["prd-002/story-001"]),
    ],
)
def test_query_parameters_filter_the_feed(agents, url, keys):
    state = _feed(url)
    assert state.feed_state == rs.FEED_CARDS
    assert [c.key for c in state.cards] == keys


def test_query_parameters_are_restored_into_the_controls(agents):
    state = _feed("/reports?status=in-progress&q=rail")
    assert state.status_filter == "in-progress"
    assert state.query == "rail"
    # And carried on the navigation, so switching PRD keeps the filter.
    assert state.all_href == "/reports?status=in-progress&q=rail"
    assert state.prds[1].href == "/reports/prd-002?status=in-progress&q=rail"


def test_no_match_is_its_own_state_not_the_empty_one(agents):
    state = _feed("/reports?q=nothing-matches-this")
    assert state.feed_state == rs.FEED_NO_MATCH
    assert state.cards == []


@pytest.mark.parametrize("url", ["/reports/prd-002", "/reports/PRD-002", "/reports/prd-002/"])
def test_prd_route_scopes_the_feed_and_marks_the_prd(agents, url):
    state = _feed(url)
    assert state.feed_state == rs.FEED_CARDS
    assert state.active_prd == "prd-002"
    assert state.active_prd_name == "Beta Chat"
    assert {c.prd_id for c in state.cards} == {"PRD-002"}


def test_prd_without_stories_is_empty_for_that_prd(agents):
    state = _feed("/reports/prd-003")
    assert state.feed_state == rs.FEED_EMPTY_PRD
    assert "Gamma Later" in state.empty_prd_body


def test_unknown_prd_is_not_found(agents):
    assert _feed("/reports/prd-999").feed_state == rs.FEED_PRD_MISSING


def _replaced_url(event) -> str:
    """The address a filter handler's `history.replaceState` call writes."""
    script = event.args[0][1]._var_value
    match = re.fullmatch(r"window\.history\.replaceState\(null, '', (\"[^\"]*\")\)", script)
    assert match, script
    return json.loads(match.group(1))


def test_filter_handlers_refilter_and_rewrite_the_url(agents):
    state = _feed("/reports/prd-002")
    event = _run(state, "set_status_filter", "done")
    assert [c.key for c in state.cards] == ["prd-002/story-001"]
    assert _replaced_url(event) == "/reports/prd-002?status=done"

    event = _run(state, "set_query", "nope")
    assert state.feed_state == rs.FEED_NO_MATCH
    assert _replaced_url(event) == "/reports/prd-002?status=done&q=nope"

    event = _run(state, "clear_filters")
    assert state.feed_state == rs.FEED_CARDS and len(state.cards) == 3
    assert _replaced_url(event) == "/reports/prd-002"


def test_detail_route(agents):
    state = _detail("/reports/prd-001/story-002")
    assert state.detail_state == rs.DETAIL_FOUND
    assert state.active_prd == "prd-001"
    detail = state.detail
    assert detail.heading == "STORY-002 · Audit schema"
    assert detail.has_report
    assert detail.commit_url == "https://github.com/The-Spik3r/harness-ai/commit/bbbbbbb"
    assert detail.files_label == "Files changed — 2 archivos"
    assert detail.validation_label == "Validation results — 1/3 pasaron"
    assert [v.outcome for v in detail.validation] == ["pass", "fail", "unknown"]
    assert detail.prev_href == "/reports/prd-001/story-001"
    assert detail.next_href == ""
    assert detail.prd_href == "/reports/prd-001"


def test_detail_of_a_story_without_a_report(agents):
    state = _detail("/reports/prd-002/story-002")
    assert state.detail_state == rs.DETAIL_FOUND
    assert not state.detail.has_report
    assert "In progress" in state.detail.no_report_body


@pytest.mark.parametrize("url", ["/reports/prd-001/story-999", "/reports/prd-999/story-001", "/reports/prd-001/story-003"])
def test_unknown_or_unparseable_story_is_not_found(agents, url):
    # story-003's report has broken frontmatter: it is excluded, so it is not found.
    assert _detail(url).detail_state == rs.DETAIL_MISSING


def test_missing_reports_directory_renders_the_empty_state_not_a_fault(tmp_path, monkeypatch):
    reports.clear_cache()
    monkeypatch.setattr(settings, "REPORTS_AGENTS_DIR", str(tmp_path / "no-such" / ".agents"))
    state = _feed("/reports")
    assert state.feed_state == rs.FEED_EMPTY
    assert state.cards == [] and state.prds == []
    assert _detail("/reports/prd-001/story-001").detail_state == rs.DETAIL_MISSING


def test_an_unreadable_record_renders_the_fault_state(tmp_path, monkeypatch):
    reports.clear_cache()
    not_a_directory = tmp_path / "agents-file"
    not_a_directory.write_text("", encoding="utf-8")
    monkeypatch.setattr(settings, "REPORTS_AGENTS_DIR", str(not_a_directory))
    assert _feed("/reports").feed_state == rs.FEED_FAULT
    assert _detail("/reports/prd-001/story-001").detail_state == rs.DETAIL_FAULT


def test_empty_and_fault_copy_are_different_sentences():
    assert reports_copy.EMPTY_TITLE != reports_copy.FAULT_TITLE
    assert reports_copy.EMPTY_BODY != reports_copy.FAULT_BODY


# --- The app, in a subprocess -----------------------------------------------------

_PAGES_PROBE = r"""
import json, sys

result = {"errors": []}
try:
    from chat_ui.chat_ui import app as reflex_app
    from chat_ui.components.reports import reports_detail_page, reports_feed_page
except Exception as exc:
    print(json.dumps({"errors": ["import: {}: {}".format(type(exc).__name__, exc)]}))
    sys.exit(0)

result["pages"] = sorted(reflex_app._unevaluated_pages)
# A bound state handler is stored as the EventHandler itself (`.fn`); a spec such
# as the console's redirect wraps one (`.handler.fn`). Both reduce to a qualname.
result["load_event_handlers"] = {
    route: [
        getattr(getattr(getattr(e, "handler", e), "fn", None), "__qualname__", "?")
        for e in events
    ]
    for route, events in reflex_app._load_events.items()
}
built = {}
for name, factory in (("feed", reports_feed_page), ("detail", reports_detail_page)):
    try:
        built[name] = str(factory())
    except Exception as exc:
        result["errors"].append("{}: {}: {}".format(name, type(exc).__name__, exc))
        built[name] = ""
result["built"] = built
print(json.dumps(result))
"""


@pytest.fixture(scope="module")
def pages_probe():
    proc = subprocess.run(
        [sys.executable, "-c", _PAGES_PROBE],
        cwd=str(REPO_ROOT / "chat_ui"),
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(_PYTHONPATH),
            "ADMIN_TOKEN": os.environ.get("ADMIN_TOKEN", "test-token"),
            "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", "test-key"),
            # Importing the app calls init_db(); this probe is about pages, and
            # must not need (or write to) a database.
            "DB_BOOTSTRAP_ENABLED": "false",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.fail(f"reports pages probe crashed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_the_app_imports_with_the_reports_pages(pages_probe):
    assert not pages_probe["errors"], pages_probe["errors"]


@pytest.mark.parametrize(
    "route, handler",
    [
        ("reports", "ReportsState.load_feed"),
        ("reports/[prd_id]", "ReportsState.load_feed"),
        ("reports/[prd_id]/[story_id]", "ReportsState.load_detail"),
    ],
)
def test_the_three_routes_are_registered_with_their_loader(pages_probe, route, handler):
    assert route in pages_probe["pages"]
    assert pages_probe["load_event_handlers"][route] == [handler]


def test_both_pages_compile_with_every_state_arm(pages_probe):
    feed, detail = pages_probe["built"]["feed"], pages_probe["built"]["detail"]

    def compiled(text):
        # The compiled JSX escapes non-ASCII ("Todav\u00eda"), as JSON does.
        return json.dumps(text)[1:-1]

    for text in (reports_copy.EMPTY_TITLE, reports_copy.FAULT_TITLE, reports_copy.NO_MATCH_TITLE,
                 reports_copy.PRD_NOT_FOUND_TITLE, reports_copy.SEARCH_PLACEHOLDER):
        assert compiled(text) in feed, text
    for text in (reports_copy.STORY_NOT_FOUND_TITLE, reports_copy.NO_REPORT_TITLE, reports_copy.FAULT_TITLE):
        assert compiled(text) in detail, text


def test_the_pages_carry_the_ground_switch(pages_probe):
    for page in pages_probe["built"].values():
        assert "hx-ground-toggle" in page


def test_the_disclosures_start_collapsed(pages_probe):
    detail = pages_probe["built"]["detail"]
    assert detail.count('jsx("details"') == 2
    assert not re.search(r"open\s*:", detail)


# --- Source guards -------------------------------------------------------------------


@pytest.mark.parametrize("path", REPORTS_MODULES, ids=lambda p: p.name)
def test_no_literal_hex_in_the_reports_modules(path):
    assert re.findall(r"#[0-9a-fA-F]{6}\b", path.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("path", REPORTS_MODULES, ids=lambda p: p.name)
def test_the_section_imports_neither_the_chat_nor_the_console(path):
    """Public pages must not pull an authenticated surface's state onto them."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    offenders = [m for m in imported if re.search(r"(^|\.)(state|admin_state|copy|admin_copy|ChatState|AdminState)$", m)]
    assert offenders == [], offenders


def test_the_reports_modules_never_touch_the_filesystem_directly():
    """Every read goes through `app.services.reports` (the seam that allows caching or
    moving the source without a UI change)."""
    for path in REPORTS_MODULES:
        source = path.read_text(encoding="utf-8")
        for forbidden in ("open(", "os.scandir", "os.listdir", "Path(", "glob(", "frontmatter"):
            assert forbidden not in source, f"{path.name} uses {forbidden}"


def test_status_inks_are_declared_in_one_mapping():
    """`STATUS_TONES` is the only place a status becomes a colour."""
    source = REPORTS_MODULES[0].read_text(encoding="utf-8")
    block = source.split("STATUS_TONES: dict", 1)[1].split("}", 1)[0]
    for ink in ("INK_CLEAR", "INK_HELD", "TINT_CLEAR", "TINT_HELD"):
        assert ink in block
        assert source.count(f"theme.{ink}") == 1, ink


def test_every_status_the_service_emits_has_a_tone_and_a_label():
    tones_source = REPORTS_MODULES[0].read_text(encoding="utf-8")
    for status in reports.STATUSES:
        assert status in reports_copy.STATUS_LABELS
        assert f'"{status}":' in tones_source
