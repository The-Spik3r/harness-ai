"""Smoke and invariant tests for the admin console's shell.

Two halves, because two different kinds of claim need two different tools.

**The build probe** runs in a subprocess with `PYTHONPATH` set to `chat_ui/`,
which is how Reflex itself imports the app (`chat_ui.components...`, not
`chat_ui.chat_ui.components...`). Doing it in-process would put the inner
package on `sys.path` and break every other test module, which reaches the same
files by their repo-root path — the same reason `tests/test_chat_components_import.py`
takes a subprocess, and its docstring records what happened the one time the
component layer went untested: "232 tests green, `reflex run` dead."

**The source assertions** read the module as text. They cover the two STORY-009
acceptance criteria a build cannot: that no colour is written as a literal hex
and no user-facing string is written as a literal, both of which are true of a
file that imports and renders perfectly.

The cross-surface separation (PRD-006 Section 4: "no admin page renders a chat
component") is asserted from *both* sides — `sys.modules` after the import,
which catches a transitive import, and the source, which catches an import that
happens to be unreachable at module scope.

STORY-010 extends this file with the **registration probe** below: the shell is
only reachable once `chat_ui.py` registers it, and the two claims — "the module
builds" and "the app serves it at the agreed path" — belong together rather than
in `tests/test_chat_components_import.py`, which is the chat's smoke test and
should stay that. That probe imports the real `rx.App`, so it is a second
subprocess rather than more work inside the first: the shell probe must keep
proving the module imports *on its own*, with no app object dragged in behind it.

STORY-011 and STORY-015 fill `admin_page()`'s `content` slot. Neither adds a
page, so the route assertions below are exhaustive and should stay that way — a
fourth admin route arriving without a story is what they exist to catch.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTHONPATH = [str(REPO_ROOT / "chat_ui"), str(REPO_ROOT)]

SHELL_SOURCE_PATH = REPO_ROOT / "chat_ui" / "chat_ui" / "components" / "admin_shell.py"

# The routes PRD-006 Section 6 pins, restated here rather than imported: a test
# that imports the constant it is checking asserts only that the constant equals
# itself. STORY-010 registers pages at these paths.
EXPECTED_ROUTES = {"ROUTE_REGISTER": "/admin/audit", "ROUTE_SUMMARY": "/admin/stats"}

# Taken by app/routers/admin.py, tests/test_route_reservations.py and the
# Caddyfile's @backend_routes matcher. The console's routes must not be these.
BACKEND_ROUTES = ("/audit", "/stats", "/query", "/health")

# Every masthead-and-gate constant the shell renders. Each must reach the screen
# through `admin_copy.`, and none may appear in the source as a literal.
COPY_NAMES = (
    "CONSOLE_TITLE",
    "MASTHEAD_SEPARATOR",
    "CONSOLE_VIEW_REGISTER",
    "CONSOLE_VIEW_SUMMARY",
    "VIEW_REGISTER_LABEL",
    "VIEW_SUMMARY_LABEL",
    "SIGN_OUT_LABEL",
    "GATE_TITLE",
    "GATE_BODY",
    "GATE_PLACEHOLDER",
    "GATE_SUBMIT_LABEL",
)

# Module paths an admin component may never import (PRD-006 Section 4). Written
# as dotted paths, not bare words: "chat" alone appears inside "chat_ui" on every
# legitimate import line in the file.
FORBIDDEN_IMPORTS = (
    "components.chat",
    "components.bubbles",
    "components import chat",
    "components import bubbles",
    "bubbles",
)

# --- STORY-010: registration -----------------------------------------------

APP_SOURCE_PATH = REPO_ROOT / "chat_ui" / "chat_ui" / "chat_ui.py"

# Reflex stores a page under its route with the surrounding slashes stripped and
# "/" mapped to "index" (reflex_base/utils/format.py, format_route). These are
# those stored keys, not URLs — the leading slash is added back before the
# collision checks below.
EXPECTED_PAGE_KEYS = ["admin", "admin/audit", "admin/stats", "index"]

# Reserved by Reflex >=0.8; restated from tests/test_route_reservations.py, which
# this story must leave unmodified. Asserting it from the console's side too means
# a colliding admin route fails in the file that introduced it.
REFLEX_RESERVED_ROUTES = {"/ping", "/_event", "/_upload"}

# Owned by app/routers/admin.py, by that same reserved-route test, and by the
# Caddyfile's @backend_routes matcher. The console lives one level down.
BACKEND_ROUTE_PATHS = {"/query", "/audit", "/stats", "/health"}


# Runs in the subprocess. Emits one JSON object on the last stdout line.
_CHECK_SCRIPT = r"""
import json, sys

result = {"errors": []}

try:
    import reflex as rx
    from chat_ui import admin_copy
    from chat_ui.components.admin_shell import (
        ROUTE_REGISTER,
        ROUTE_SUMMARY,
        VIEW_REGISTER,
        VIEW_SUMMARY,
        admin_gate,
        admin_masthead,
        admin_page,
    )
except Exception as exc:
    print(json.dumps({"errors": ["import: {}: {}".format(type(exc).__name__, exc)]}))
    sys.exit(0)

# The separation, from the importing side: nothing the shell pulls in may drag
# a chat component along with it.
result["chat_modules_loaded"] = [
    name
    for name in ("chat_ui.components.chat", "chat_ui.components.bubbles")
    if name in sys.modules
]

# Every exported factory builds. Both mastheads, so a broken active-view branch
# fails a test rather than a page.
broken = []
factories = [
    ("admin_gate", lambda: admin_gate()),
    ("admin_masthead(register)", lambda: admin_masthead(VIEW_REGISTER)),
    ("admin_masthead(summary)", lambda: admin_masthead(VIEW_SUMMARY)),
    ("admin_page(register)", lambda: admin_page(rx.box("x"), VIEW_REGISTER)),
    ("admin_page(summary)", lambda: admin_page(rx.box("x"), VIEW_SUMMARY)),
]
built = {}
for name, factory in factories:
    try:
        component = factory()
        if not isinstance(component, rx.Component):
            broken.append(name)
        else:
            built[name] = str(component)
    except Exception as exc:
        broken.append("{} ({}: {})".format(name, type(exc).__name__, exc))
result["broken_factories"] = broken

# Both rx.cond branches compile into one page: the gate's submit and the
# masthead's sign out are present in the same rendered page, which is what
# "the pages exist unconditionally; the token check decides what they render"
# looks like from the outside (PRD-006 Section 6).
page = built.get("admin_page(register)", "")
result["page_has_gate_submit"] = admin_copy.GATE_SUBMIT_LABEL in page
result["page_has_sign_out"] = admin_copy.SIGN_OUT_LABEL in page

# The masthead names the view it is on, and not the other one. The separator is
# a non-ASCII middot that the JSX renderer escapes to ·, so the two view
# words are checked rather than the concatenated title.
register_masthead = built.get("admin_masthead(register)", "")
summary_masthead = built.get("admin_masthead(summary)", "")
result["masthead_words"] = {
    "register_has_register": admin_copy.CONSOLE_VIEW_REGISTER in register_masthead,
    "register_has_summary_word": admin_copy.CONSOLE_VIEW_SUMMARY in register_masthead,
    "summary_has_summary": admin_copy.CONSOLE_VIEW_SUMMARY in summary_masthead,
    "summary_has_register_word": admin_copy.CONSOLE_VIEW_REGISTER in summary_masthead,
    "both_have_wordmark": (
        admin_copy.CONSOLE_TITLE in register_masthead
        and admin_copy.CONSOLE_TITLE in summary_masthead
    ),
}

result["routes"] = {"ROUTE_REGISTER": ROUTE_REGISTER, "ROUTE_SUMMARY": ROUTE_SUMMARY}
result["views"] = {"VIEW_REGISTER": VIEW_REGISTER, "VIEW_SUMMARY": VIEW_SUMMARY}

print(json.dumps(result))
"""


@pytest.fixture(scope="module")
def probe():
    proc = subprocess.run(
        [sys.executable, "-c", _CHECK_SCRIPT],
        cwd=str(REPO_ROOT / "chat_ui"),
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(_PYTHONPATH),
            # admin_shell imports admin_state, which imports app.config.settings,
            # where ADMIN_TOKEN is a required field. Same defaults
            # tests/test_admin_state.py sets.
            "ADMIN_TOKEN": os.environ.get("ADMIN_TOKEN", "test-token"),
            "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", "test-key"),
        },
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.fail(f"admin shell probe crashed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def source() -> str:
    return SHELL_SOURCE_PATH.read_text(encoding="utf-8")


# --- The build probe ------------------------------------------------------


def test_module_imports(probe):
    """Catches circular imports and names missing at module scope."""
    assert not probe["errors"], probe["errors"]


def test_every_factory_builds(probe):
    """The gate, both mastheads and both wrapped pages."""
    assert not probe["errors"], probe["errors"]
    assert not probe["broken_factories"], probe["broken_factories"]


def test_shell_loads_no_chat_component(probe):
    """PRD-006 Section 4's cross-surface separation, from the importing side.

    Stronger than a source grep: a chat component pulled in transitively by
    something the shell imports would show up here and nowhere else.
    """
    assert not probe["errors"], probe["errors"]
    assert not probe["chat_modules_loaded"], probe["chat_modules_loaded"]


def test_page_carries_both_gate_branches(probe):
    """Both `rx.cond` arms compile into the one page.

    The gate's submit label and the masthead's sign out are in the same rendered
    output, which is what PRD-006 Section 6's "the pages exist unconditionally"
    means concretely — and it is why the read, not the render, is what actually
    keeps data off an unauthenticated screen (Risk 1).
    """
    assert not probe["errors"], probe["errors"]
    assert probe["page_has_gate_submit"], "the gate's submit is not in the page"
    assert probe["page_has_sign_out"], "the masthead's sign out is not in the page"


def test_masthead_names_its_own_view(probe):
    """`HARNESS · REGISTER` on the register, `HARNESS · SUMMARY` on the summary."""
    assert not probe["errors"], probe["errors"]
    words = probe["masthead_words"]
    assert words["both_have_wordmark"]
    assert words["register_has_register"]
    assert words["summary_has_summary"]
    assert not words["register_has_summary_word"]
    assert not words["summary_has_register_word"]


@pytest.mark.parametrize(("name", "expected"), sorted(EXPECTED_ROUTES.items()))
def test_route_constants_are_declared_here(probe, name, expected):
    """The route string is typed once in the codebase, and this is where.

    STORY-010 imports these rather than re-typing them, so a moved page cannot
    leave the two-view switch pointing at the old path.
    """
    assert not probe["errors"], probe["errors"]
    assert probe["routes"][name] == expected


def test_console_routes_do_not_collide_with_the_backend(probe):
    """PRD-006 Section 6's routing constraint: `/audit` and `/stats` are taken.

    The console lives under `/admin/`, which falls through Caddy's
    `@backend_routes` matcher to the static file server and needs no
    Caddyfile change.
    """
    assert not probe["errors"], probe["errors"]
    for route in probe["routes"].values():
        assert route.startswith("/admin/"), route
        assert route not in BACKEND_ROUTES, route


def test_view_keys_are_distinct(probe):
    assert not probe["errors"], probe["errors"]
    assert probe["views"]["VIEW_REGISTER"] != probe["views"]["VIEW_SUMMARY"]


# --- The source assertions ------------------------------------------------


def test_source_is_discoverable(source):
    """A missing file would pass every source test below vacuously."""
    assert source.strip(), SHELL_SOURCE_PATH


def test_no_literal_hex_colour(source):
    """Every colour resolves from theme.py (STORY-009 AC 7).

    A hex in this file is a colour that a change of visual direction would miss,
    breaking the single-file guarantee theme.py's own docstring makes.
    """
    offenders = re.findall(r"#[0-9a-fA-F]{6}\b", source)
    assert not offenders, f"colours belong in theme.py: {offenders}"


@pytest.mark.parametrize("name", COPY_NAMES)
def test_every_string_is_read_from_admin_copy(source, name):
    assert f"admin_copy.{name}" in source, f"{name} is not rendered from admin_copy"


@pytest.mark.parametrize("name", COPY_NAMES)
def test_no_copy_value_is_written_as_a_literal(source, name):
    """AC 7's "no literal text", made checkable.

    Case-sensitive and quoted, deliberately: the view *keys* ("register",
    "summary") are values this module legitimately declares, and they differ
    from the labels ("Register", "Summary") only in case.
    """
    from chat_ui.chat_ui import admin_copy

    value = getattr(admin_copy, name)
    assert f'"{value}"' not in source, f"{name}'s value is a literal in the shell"
    assert f"'{value}'" not in source, f"{name}'s value is a literal in the shell"


@pytest.mark.parametrize("forbidden", FORBIDDEN_IMPORTS)
def test_source_imports_no_chat_component(source, forbidden):
    """PRD-006 Section 4, from the source side.

    Complements the `sys.modules` probe: this catches an import that exists but
    is never reached, which the runtime check would miss.
    """
    import_lines = [
        line
        for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    offenders = [line for line in import_lines if forbidden in line]
    assert not offenders, offenders


def test_shell_sets_no_focus_reset(source):
    """The quality floor's keyboard half (AC 8).

    theme.GLOBAL_CSS gives every focusable element a visible ring; a local
    `outline: none` would silently take it back on the one control that set it.
    """
    for killer in ("outline", "box_shadow"):
        assert f'"{killer}": "none"' not in source, killer
    assert "outline=\"none\"" not in source


# --- STORY-010: the registration probe ------------------------------------

# A second subprocess, not more work inside the first. This one imports the real
# rx.App — which runs chat_ui.py top to bottom, including init_db() — and the
# shell probe has to keep proving that admin_shell imports on its own, with no
# app object behind it.
#
# The route-table walk is tests/test_route_reservations.py:13-25 verbatim.
# FastAPI wraps include_router() results in a lazy _IncludedRouter, so reaching
# the real paths means descending into original_router.routes.
_PAGES_CHECK_SCRIPT = r"""
import json, sys

result = {"errors": []}


def route_paths(fastapi_app):
    paths = set()
    for route in fastapi_app.routes:
        if type(route).__name__ == "_IncludedRouter":
            paths.update(r.path for r in route.original_router.routes)
        elif hasattr(route, "path"):
            paths.add(route.path)
    return paths


try:
    # app.main first, and sampled before the Reflex app is imported: the whole
    # claim is that importing the console changes this table by nothing.
    import app.main

    before = sorted(route_paths(app.main.app))
    from chat_ui.chat_ui import app as reflex_app

    after = sorted(route_paths(app.main.app))
except Exception as exc:
    print(json.dumps({"errors": ["import: {}: {}".format(type(exc).__name__, exc)]}))
    sys.exit(0)

result["routes_before"] = before
result["routes_after"] = after
result["pages"] = sorted(reflex_app._unevaluated_pages)
result["load_event_counts"] = {
    route: len(events) for route, events in reflex_app._load_events.items()
}
# The handler behind each on_load, so "no page loads data" is checked against
# what is wired rather than against a count that a second event would satisfy.
# __qualname__, not __name__: reflex's server_side() builds the handler around an
# inner `def fn(...)` and relabels only the qualname, so __name__ is "fn" for
# every server-side event and would tell these tests nothing apart.
result["load_event_handlers"] = {
    route: [
        getattr(
            getattr(getattr(event, "handler", None), "fn", None), "__qualname__", "?"
        )
        for event in events
    ]
    for route, events in reflex_app._load_events.items()
}
result["load_event_reprs"] = {
    route: [repr(event) for event in events]
    for route, events in reflex_app._load_events.items()
}
result["page_context"] = {
    route: page.context for route, page in reflex_app._unevaluated_pages.items()
}

print(json.dumps(result))
"""


@pytest.fixture(scope="module")
def pages_probe(tmp_path_factory):
    # DATABASE_URL is pinned because importing chat_ui.chat_ui calls init_db() at
    # module scope; without it the probe writes harness_ai.db into chat_ui/ on
    # every run. The file is gitignored, so it would go unnoticed.
    db_path = tmp_path_factory.mktemp("admin_pages") / "probe.db"
    proc = subprocess.run(
        [sys.executable, "-c", _PAGES_CHECK_SCRIPT],
        cwd=str(REPO_ROOT / "chat_ui"),
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(_PYTHONPATH),
            "ADMIN_TOKEN": os.environ.get("ADMIN_TOKEN", "test-token"),
            "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", "test-key"),
            "DATABASE_URL": f"sqlite:///{db_path}",
        },
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.fail(f"admin pages probe crashed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def app_source() -> str:
    return APP_SOURCE_PATH.read_text(encoding="utf-8")


def test_app_module_imports(pages_probe):
    """The app builds with the admin pages registered.

    A route Reflex rejects (verify_route_validity) or a page function that raises
    fails here, at import, rather than at `reflex run`.
    """
    assert not pages_probe["errors"], pages_probe["errors"]


def test_both_console_views_are_registered(pages_probe):
    """STORY-010 AC 1, and the chat's page in the same assertion.

    Exhaustive rather than a subset check: `index` must survive, and a fourth
    admin route arriving without a story should fail here.
    """
    assert not pages_probe["errors"], pages_probe["errors"]
    assert pages_probe["pages"] == EXPECTED_PAGE_KEYS


def test_admin_lands_on_the_register(pages_probe):
    """`/admin` carries exactly one on_load, and it is the redirect."""
    assert not pages_probe["errors"], pages_probe["errors"]
    assert pages_probe["load_event_handlers"]["admin"] == ["_redirect"]
    (redirect_repr,) = pages_probe["load_event_reprs"]["admin"]
    assert "/admin/audit" in redirect_repr, redirect_repr


def test_no_console_view_loads_on_page_load(pages_probe):
    """STORY-010 AC 5, stated at the route layer.

    The data is read by `AdminState.load`, and `authenticate()` is what returns
    it. Wiring it to a page's on_load would read the database for an
    unauthenticated visitor — the read `AdminState.load`'s own guard exists to
    refuse — so no view may carry a load event at all.
    """
    assert not pages_probe["errors"], pages_probe["errors"]
    for route in ("admin/audit", "admin/stats", "index"):
        assert pages_probe["load_event_counts"][route] == 0, route
    all_handlers = [
        handler
        for handlers in pages_probe["load_event_handlers"].values()
        for handler in handlers
    ]
    assert not [h for h in all_handlers if "AdminState" in h], all_handlers
    assert not [h for h in all_handlers if h.endswith(".load")], all_handlers


def test_importing_the_console_adds_no_backend_route(pages_probe):
    """STORY-010 AC 2, and the strongest form available.

    Sampled before and after the import, so it catches a route added as an import
    side effect — which reading the diff would not.
    """
    assert not pages_probe["errors"], pages_probe["errors"]
    assert pages_probe["routes_after"] == pages_probe["routes_before"]
    assert BACKEND_ROUTE_PATHS <= set(pages_probe["routes_after"])


@pytest.mark.parametrize("route", sorted(set(EXPECTED_PAGE_KEYS) - {"index"}))
def test_console_route_collides_with_nothing(pages_probe, route):
    """STORY-010 AC 3, restated from the console's side.

    tests/test_route_reservations.py must pass unmodified, so this is a second
    statement of the same guarantee in the file that introduced the routes.
    """
    assert not pages_probe["errors"], pages_probe["errors"]
    path = "/" + route
    assert path not in REFLEX_RESERVED_ROUTES
    assert path not in BACKEND_ROUTE_PATHS
    assert path not in pages_probe["routes_after"]


@pytest.mark.parametrize("route", sorted(set(EXPECTED_PAGE_KEYS) - {"index"}))
def test_console_routes_are_kept_out_of_the_sitemap(pages_probe, route):
    """SitemapPlugin writes every registered route into the public sitemap.xml.

    `None`, not `{}`: generate_links_for_sitemap skips a page only on an explicit
    None, and `{}` means "default configuration" — it would publish the route.
    """
    assert not pages_probe["errors"], pages_probe["errors"]
    assert pages_probe["page_context"][route] == {"sitemap": None}


def test_app_source_is_discoverable(app_source):
    assert app_source.strip(), APP_SOURCE_PATH


@pytest.mark.parametrize(("name", "literal"), sorted(EXPECTED_ROUTES.items()))
def test_route_is_imported_not_retyped(app_source, name, literal):
    """The route string is typed once, in admin_shell.py.

    The expected value comes from this module's own EXPECTED_ROUTES rather than
    from `admin_shell` — importing that module in-process would put the inner
    package on sys.path, which is the whole reason every other check here runs in
    a subprocess. `test_route_constants_are_declared_here` already pins
    EXPECTED_ROUTES to what the module actually declares.

    `/admin` is deliberately not covered: the landing route is not a view, so
    admin_shell has no reason to name it, and it is a literal here.
    """
    assert name in app_source, f"{name} should be imported and used by chat_ui.py"
    assert f'"{literal}"' not in app_source, f"{literal} is retyped in chat_ui.py"
    assert f"'{literal}'" not in app_source, f"{literal} is retyped in chat_ui.py"
