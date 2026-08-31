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

STORY-010 should extend **this** file with its route-registration probe rather
than `tests/test_chat_components_import.py`, which is the chat's smoke test and
should stay that.
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
