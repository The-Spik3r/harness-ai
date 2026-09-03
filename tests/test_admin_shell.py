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

sys.path.insert(0, str(Path(__file__).parent.parent))

from chat_ui.chat_ui import admin_copy, theme  # noqa: E402
from tests.conftest import child_db_env  # noqa: E402

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
#
# STORY-019 removed three names from this tuple rather than from `admin_copy`:
# `MASTHEAD_SEPARATOR`, `CONSOLE_VIEW_REGISTER` and `CONSOLE_VIEW_SUMMARY` are
# the cut view word and the middot that joined it (see
# `test_the_masthead_is_the_wordmark_and_nothing_else`). They are still declared,
# because PRD-006 Section 15 keeps `tests/test_copy.py` unmodified and it asserts
# them by name — but this tuple is the list of strings the shell *renders*, and
# the shell no longer renders them. Leaving them here would assert the cut back.
COPY_NAMES = (
    "CONSOLE_TITLE",
    "VIEW_REGISTER_LABEL",
    "VIEW_SUMMARY_LABEL",
    "SIGN_OUT_LABEL",
    "GATE_TITLE",
    "GATE_BODY",
    "GATE_PLACEHOLDER",
    "GATE_SUBMIT_LABEL",
    # STORY-017: the refresh cluster and the fault panel.
    "REFRESH_LABEL",
    "REFRESH_IN_FLIGHT_LABEL",
    "FAULT_TITLE",
)

# The admin modules, globbed the way tests/test_admin_palette.py globs them: a
# later story adding one must not have to remember this file.
ADMIN_MODULE_PATTERNS = (
    "chat_ui/chat_ui/admin_*.py",
    "chat_ui/chat_ui/components/admin_*.py",
    "chat_ui/chat_ui/components/register.py",
    "chat_ui/chat_ui/components/summary.py",
)

# PRD-006 Section 4, out of scope, verbatim: "Auto-refresh, polling, or push
# updates — refresh is a deliberate action." Each of these is a way to make the
# console read on its own; none may appear in an admin module.
AUTO_REFRESH_MARKERS = (
    "on_mount",
    "setInterval",
    "set_interval",
    "rx.moment",
    "interval=",
    "asyncio.sleep",
)

# PRD-006 Section 6.1: the loading indicator is "the sole moving element", and
# it reuses the chat's class rather than declaring a second animation.
MOTION_MARKERS = ("@keyframes", "animation:", "animation=")

# The frontend-design skill, verbatim: "errors don't apologize, and they are
# never vague about what happened."
APOLOGY_WORDS = ("sorry", "apolog", "oops", "unfortunately", "whoops", "please try")

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

def _admin_modules() -> list[Path]:
    found: list[Path] = []
    for pattern in ADMIN_MODULE_PATTERNS:
        found.extend(sorted(REPO_ROOT.glob(pattern)))
    return found


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
        fault_panel,
        refresh_control,
        refreshed_stamp,
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
    ("refresh_control", lambda: refresh_control()),
    ("refreshed_stamp", lambda: refreshed_stamp()),
    ("fault_panel", lambda: fault_panel()),
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

# The masthead carries the wordmark and nothing else — STORY-019's cut. The
# uppercase view words are what was removed; the switch's own labels
# ("Register" / "Summary") must still be there, because the switch is the
# element that owns the fact now.
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
    "separator_rendered": (
        admin_copy.MASTHEAD_SEPARATOR in register_masthead
        or admin_copy.MASTHEAD_SEPARATOR in summary_masthead
    ),
    "both_have_switch_labels": all(
        label in masthead
        for masthead in (register_masthead, summary_masthead)
        for label in (
            admin_copy.VIEW_REGISTER_LABEL,
            admin_copy.VIEW_SUMMARY_LABEL,
        )
    ),
    "both_mark_current": (
        'aria-current' in register_masthead and 'aria-current' in summary_masthead
    ),
}

# STORY-017's three components, and both pages, as compiled strings.
result["control"] = built.get("refresh_control", "")
result["stamp"] = built.get("refreshed_stamp", "")
result["panel"] = built.get("fault_panel", "")
result["page_register"] = page
result["page_summary"] = built.get("admin_page(summary)", "")

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


def test_the_masthead_is_the_wordmark_and_nothing_else(probe):
    """STORY-019's cut, asserted absent so it cannot come back unnoticed.

    The masthead read `HARNESS · REGISTER` / `HARNESS · SUMMARY` until the
    quality-floor pass, while the two-view switch beside it already marked the
    current view with `aria-current="page"`. Naming the view twice in one header
    row is the frontend-design skill's "nothing quietly does double duty", so the
    suffix came off (`admin_shell.py:admin_masthead` records the reasoning).

    This replaces `test_masthead_names_its_own_view`, which asserted the
    behaviour that was cut. The three copy constants stay declared — PRD-006
    Section 15 keeps `tests/test_copy.py` unmodified and it asserts them by name
    — so the assertion is over what the masthead *renders*, which is the thing
    the critique actually changed.
    """
    assert not probe["errors"], probe["errors"]
    words = probe["masthead_words"]
    assert words["both_have_wordmark"], "the wordmark itself must stay"
    assert not words["register_has_register"], "the cut view word is back"
    assert not words["summary_has_summary"], "the cut view word is back"
    assert not words["register_has_summary_word"]
    assert not words["summary_has_register_word"]
    assert not words["separator_rendered"], "the middot had nothing left to join"


def test_the_switch_still_owns_the_current_view(probe):
    """The other half of the cut: removing a naming may not remove *the* naming.

    Cutting the masthead suffix is only correct because the switch states the
    same fact and can be acted on. If the switch stopped carrying both labels or
    stopped marking the current one, the console would name the view zero times
    and the cut would have taken information with it.
    """
    assert not probe["errors"], probe["errors"]
    words = probe["masthead_words"]
    assert words["both_have_switch_labels"], "the switch lost a destination"
    assert words["both_mark_current"], "the switch no longer marks the current view"


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


# --- STORY-017: refresh and the fault panel -------------------------------
# The control, the line it produces and the panel that offers it again. The
# state behind all three is STORY-004's and is asserted in
# tests/test_admin_state.py; what is asserted here is that it reaches the screen
# on both pages, that the control locks, and that nothing on this surface moves
# except the one indicator.


def test_the_refresh_control_reaches_both_pages(probe):
    """AC 1, the control's half. It is declared once and called from the
    masthead, which every page goes through, so each page carries its own
    instance rather than sharing one.

    The *line* it produces is asserted in `tests/test_register.py` and
    `tests/test_summary.py`: PRD-006 Section 6.1's wireframe puts the stamp at
    the foot of each view's scope column, beside the window it stamps, not in
    the header.
    """
    assert not probe["errors"], probe["errors"]
    for page in ("page_register", "page_summary"):
        assert admin_copy.REFRESH_LABEL in probe[page], page


def test_the_control_and_the_line_share_one_verb(probe):
    """AC 1, and the frontend-design skill's "an action keeps the same name
    through the whole flow": Refresh -> Refreshing -> Refreshed.

    Read off the constants rather than the rendered page, so a reworded control
    that left its line behind fails here rather than on screen.
    """
    stem = admin_copy.REFRESH_LABEL.lower()[:7]
    assert admin_copy.REFRESH_IN_FLIGHT_LABEL.lower().startswith(stem)
    assert admin_copy.REFRESHED_TEMPLATE.lower().startswith(stem)


def test_the_stamp_binds_the_state_var_and_not_a_formatted_string(probe):
    """The line is composed in Python (`AdminState.refreshed_stamp`), because
    `REFRESHED_TEMPLATE` is a format string and components receive Vars."""
    assert not probe["errors"], probe["errors"]
    assert "refreshed_stamp" in probe["stamp"]


def test_the_control_locks_for_the_duration_of_a_read(probe):
    """AC 2. `disabled` is bound to the same flag `load()` sets, so the lock and
    the read cannot disagree."""
    assert not probe["errors"], probe["errors"]
    assert "loading" in probe["control"]
    assert "disabled" in probe["control"]


def test_the_control_shows_an_indicator_while_the_read_is_out(probe):
    """AC 2's second half: the label states the tense and one glyph pulses."""
    assert not probe["errors"], probe["errors"]
    assert admin_copy.REFRESH_IN_FLIGHT_LABEL in probe["control"]
    assert "hx-pulse" in probe["control"]


def test_the_panel_names_the_read_and_offers_the_retry(probe):
    """AC 3. The sentence is `AdminState.error`, which `load()` builds from
    FAULT_MESSAGE_TEMPLATE and the failing read's label."""
    assert not probe["errors"], probe["errors"]
    assert admin_copy.FAULT_TITLE in probe["panel"]
    assert "error" in probe["panel"]
    assert admin_copy.REFRESH_LABEL in probe["panel"]


def test_the_retry_is_the_refresh_control_itself(source):
    """AC 4, and the skill's consistency rule: one action, one name, one
    handler. Two call sites would be two buttons; two `on_click` sites would be
    two ways to start a read."""
    assert source.count("on_click=AdminState.load") == 1
    assert source.count("def refresh_control") == 1
    # Called as an argument exactly twice: once by the masthead, once by the
    # panel. Counted with the trailing comma so the prose in the docstrings,
    # which names the function too, is not counted as a call site.
    assert source.count("refresh_control(),") == 2


def test_each_page_renders_its_own_panel(probe):
    """AC 7. Not a shared instance reached from one view: both pages compile the
    panel, so the fault path on either renders independently."""
    assert not probe["errors"], probe["errors"]
    assert admin_copy.FAULT_TITLE in probe["page_register"]
    assert admin_copy.FAULT_TITLE in probe["page_summary"]


def test_the_panel_does_not_apologise(probe):
    """AC 5, the frontend-design skill verbatim: "errors don't apologize, and
    they are never vague about what happened."""
    assert not probe["errors"], probe["errors"]
    lowered = probe["panel"].lower()
    for word in APOLOGY_WORDS:
        assert word not in lowered, word
    # And it is not vague: the sentence names a read and states the action.
    assert "{read}" in admin_copy.FAULT_MESSAGE_TEMPLATE
    assert admin_copy.REFRESH_LABEL in admin_copy.FAULT_MESSAGE_TEMPLATE


def test_the_panel_paints_no_verdict_ink(probe):
    """The STORY-017 critique pass, pinned.

    PRD-006 Section 6.1 gives each of the four inks exactly one job — a verdict
    on a register row — and spends the console's boldness on the stamp margin,
    where a mark means "this row is an exception". The panel briefly carried an
    `INK_FAULT` mark in that same shape; it was cut, because the same device
    outside the margin spends the margin's meaning without adding a fact the
    words do not already state. This keeps it cut.
    """
    assert not probe["errors"], probe["errors"]
    for name in ("INK_CLEAR", "INK_HELD", "INK_DENIED", "INK_FAULT"):
        assert getattr(theme, name).upper() not in probe["panel"].upper(), name


def test_the_indicator_is_the_only_moving_element(source):
    """AC 6, first half. The pulse is the chat's existing class, so the console
    declares no animation of its own — and therefore cannot declare one that the
    reduced-motion block does not already cover."""
    for marker in MOTION_MARKERS:
        assert marker not in source, marker
    assert source.count('class_name="hx-pulse"') == 1


@pytest.mark.parametrize(
    "module", sorted(str(p) for p in _admin_modules()), ids=lambda p: Path(p).name
)
def test_no_admin_module_declares_its_own_animation(module):
    """AC 6 across the console, not just the shell."""
    text = Path(module).read_text(encoding="utf-8")
    for marker in MOTION_MARKERS:
        assert marker not in text, (module, marker)


def test_reduced_motion_covers_the_indicator():
    """AC 6, second half. The opt-out is `theme.GLOBAL_CSS`'s, which
    `admin_page()` injects onto every console page — asserted by reading the
    stylesheet rather than by trusting that it was inherited."""
    css = theme.GLOBAL_CSS
    block = css.split("@media (prefers-reduced-motion: reduce)", 1)
    assert len(block) == 2, "the reduced-motion block is gone"
    opt_out = block[1].split("}}", 1)[0] if "}}" in block[1] else block[1]
    assert "hx-pulse" in opt_out
    assert "animation: none" in opt_out


@pytest.mark.parametrize(
    "module", sorted(str(p) for p in _admin_modules()), ids=lambda p: Path(p).name
)
def test_no_admin_module_refreshes_itself(module):
    """AC 8, and PRD-006 Section 4's out-of-scope list: "Auto-refresh, polling,
    or push updates — refresh is a deliberate action."

    The companion to `test_no_console_view_loads_on_page_load`, which covers the
    `on_load` route. This covers the component and state routes: a mount hook, a
    timer, or a sleep loop that would read again without anyone asking.
    """
    text = Path(module).read_text(encoding="utf-8")
    for marker in AUTO_REFRESH_MARKERS:
        assert marker not in text, (module, marker)


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
def pages_probe(database_url_factory):
    # DATABASE_URL is pinned because importing chat_ui.chat_ui calls init_db() at
    # module scope; without it the probe writes harness_ai.db into chat_ui/ on
    # every run. The file is gitignored, so it would go unnoticed. The URL comes
    # from conftest so the libSQL swap has one place to change; the factory is
    # session-scoped because this fixture is module-scoped and could not request
    # a function-scoped one.
    # It travels in DATABASE_URL alone. It briefly took two variables: STORY-005
    # made a `sqlite:///` value a startup error, and a child constructs its own
    # Settings() where monkeypatch cannot reach, so the validating URL and the
    # real one had to travel separately. STORY-006 made the fixtures hand out a
    # real libSQL endpoint, which validates, so one variable carries it again.
    db_url = database_url_factory("admin_pages")
    proc = subprocess.run(
        [sys.executable, "-c", _PAGES_CHECK_SCRIPT],
        cwd=str(REPO_ROOT / "chat_ui"),
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(_PYTHONPATH),
            "ADMIN_TOKEN": os.environ.get("ADMIN_TOKEN", "test-token"),
            "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", "test-key"),
            **child_db_env(db_url),
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


# --- STORY-019: the quality floor ------------------------------------------
# Appended, never edited above. The live pass walked the whole console from the
# keyboard and measured a 2px solid ring on every stop (gate field, gate submit,
# the switch, refresh, sign out, four chips, the find field, three sort controls,
# clear, and a row disclosure). These pin the two source facts that produce it.


def test_the_focus_ring_is_declared_for_every_focusable_element():
    """AC 1's "visible focus", asserted at the one place that grants it.

    `theme.GLOBAL_CSS` carries a bare `:focus-visible` rule and `admin_page()`
    injects that stylesheet onto both console pages, which is why the walk
    measured the same ring on all fifteen stops rather than on the handful of
    elements that happen to keep a browser default. A ring that exists only in a
    browser default is one Radix reset away from gone.
    """
    css = theme.GLOBAL_CSS
    assert ":focus-visible" in css, "the global focus ring is gone"
    block = css.split(":focus-visible", 1)[1].split("}", 1)[0]
    assert "outline:" in block, "the focus rule no longer draws an outline"
    assert "none" not in block, "the focus rule draws nothing"
    # Measured live as 2px solid rgb(52, 86, 127) on every stop.
    assert "2px" in block


@pytest.mark.parametrize(
    "module", sorted(str(p) for p in _admin_modules()), ids=lambda p: Path(p).name
)
def test_no_admin_module_takes_the_focus_ring_back(module):
    """The companion: the ring is granted globally, so it can only be lost
    locally.

    `tests/test_register.py` and `tests/test_summary.py` each assert this for
    their own file. It belongs on the glob that already defines what an admin
    module is, so a module added tomorrow is covered the day it lands — the same
    argument `tests/test_admin_palette.py` makes for the hex guard.
    """
    text = Path(module).read_text(encoding="utf-8")
    for killer in ('"outline": "none"', 'outline="none"', '"box_shadow": "none"'):
        assert killer not in text, (module, killer)
    assert "tabindex" not in text.lower()
    assert "tab_index" not in text


@pytest.mark.parametrize(
    "module", sorted(str(p) for p in _admin_modules()), ids=lambda p: Path(p).name
)
def test_no_admin_module_pins_a_width_the_viewport_cannot_meet(module):
    """AC 2 by construction.

    Measured live at 360, 390 and 640px across the gate, the register and the
    summary: `documentElement.scrollWidth == innerWidth` in all nine. The layout
    answers a narrow viewport by wrapping, and the one element that genuinely
    cannot wrap — the ten-column table — scrolls inside its own container
    (`tests/test_register.py` pins that pair). What would break it is a hard
    pixel width on something the page cannot shrink, so no admin module may
    declare one.

    `max_width` is untouched by this: a maximum shrinks. `min_width="0"` is the
    flex idiom that *enables* shrinking, and `min_width=_MIN_WIDTH` inside the
    scroll container is the table's own width, which is the point of AC 2's
    second half rather than a violation of its first.
    """
    text = Path(module).read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in text.splitlines()
        if re.search(r'(?<!max_)(?<!\w)width=f?"\d+px"', line)
    ]
    assert not offenders, (module, offenders)
