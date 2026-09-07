"""The ground toggle, its wording, and the two-palette contract behind them.

Three kinds of claim, three instruments, on this file's neighbours' pattern.

**The build probe** runs in a subprocess with `PYTHONPATH` set to `chat_ui/`,
which is how Reflex itself imports the app (`chat_ui.components...`, not
`chat_ui.chat_ui.components...`). `tests/test_admin_shell.py` records why this
cannot be done in-process: putting the inner package on `sys.path` breaks every
other test module, which reaches the same files by their repo-root path.

**The source assertions** read the module as text, and cover what a build cannot:
that the component writes no colour, no size and no user-facing string of its
own. All three are true of a file that imports and renders perfectly, which is
exactly why they need their own tool.

**The palette assertions** read `theme.py`. `tests/test_contrast.py` already
holds both palettes to the AA floor; what is left is the plumbing — that every
token is a reference, that every reference has a declaration on both grounds, and
that the stylesheet actually carries the two blocks. A palette that is perfectly
legible and never reaches the page is the failure this half exists for.

**On the Reflex constants.** `MODE_LIGHT` and `MODE_DARK` are not ours: they are
what Reflex's `resolvedColorMode` reports and what its pre-paint script reads
back out of `localStorage["theme"]`. `ground_switch.py` writes them as literals
rather than importing them, on the reasoning `tests/test_render_invariants.py`
uses for its verdict names — a constant imported from the thing under test agrees
with itself. So they are pinned here against `reflex.style`, which is where a
Reflex upgrade renaming a mode would otherwise land as a toggle that silently
stops choosing an icon.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from chat_ui.chat_ui import ground_copy, theme  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTHONPATH = [str(REPO_ROOT / "chat_ui"), str(REPO_ROOT)]

SWITCH_SOURCE_PATH = (
    REPO_ROOT / "chat_ui" / "chat_ui" / "components" / "ground_switch.py"
)
COPY_SOURCE_PATH = REPO_ROOT / "chat_ui" / "chat_ui" / "ground_copy.py"

# Every string the toggle renders -- both of them accessible names, since the
# control draws no text at all. Each must reach the screen through
# `ground_copy.`, and none may appear in the component as a literal.
COPY_NAMES = (
    "GROUND_TO_DARK_LABEL",
    "GROUND_TO_LIGHT_LABEL",
)

# The four surfaces PRD-006 and PRD-008 leave standing, and the toggle is on all
# of them: a reader who can reach a screen can change its ground from that
# screen. Written as (label, factory) pairs the probe calls by name.
SURFACES = (
    ("chat header", "header"),
    ("chat gate", "login_gate"),
    ("console masthead", "admin_masthead"),
    ("console gate", "admin_gate"),
)

_CHECK_SCRIPT = r"""
import json, sys

result = {"errors": []}

try:
    from chat_ui import ground_copy
    from chat_ui.components.ground_switch import MODE_DARK, MODE_LIGHT, ground_switch
    from chat_ui.components.shell import header, login_gate
    from chat_ui.components.admin_shell import (
        VIEW_REGISTER,
        admin_gate,
        admin_masthead,
    )
except Exception as exc:
    print(json.dumps({"errors": ["import: {}: {}".format(type(exc).__name__, exc)]}))
    sys.exit(0)

result["modes"] = {"light": MODE_LIGHT, "dark": MODE_DARK}

try:
    result["toggle"] = str(ground_switch())
except Exception as exc:
    result["errors"].append("ground_switch: {}: {}".format(type(exc).__name__, exc))
    result["toggle"] = ""

# The four surfaces, each rendered whole. Rendering the surface rather than the
# toggle is the point: it is what catches the toggle being dropped from a header
# during an unrelated edit, which a test of `ground_switch()` alone cannot see.
surfaces = {
    "header": lambda: header(),
    "login_gate": lambda: login_gate(),
    "admin_masthead": lambda: admin_masthead(VIEW_REGISTER),
    "admin_gate": lambda: admin_gate(),
}
built = {}
for name, factory in surfaces.items():
    try:
        built[name] = str(factory())
    except Exception as exc:
        result["errors"].append("{}: {}: {}".format(name, type(exc).__name__, exc))
        built[name] = ""
result["surfaces"] = built

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
            # tests/test_admin_shell.py sets.
            "ADMIN_TOKEN": os.environ.get("ADMIN_TOKEN", "test-token"),
            "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", "test-key"),
        },
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.fail(f"ground toggle probe crashed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def source() -> str:
    return SWITCH_SOURCE_PATH.read_text(encoding="utf-8")


# --- The build probe ------------------------------------------------------


def test_module_imports(probe):
    """Catches circular imports and names missing at module scope."""
    assert not probe["errors"], probe["errors"]


def test_the_grounds_are_named_the_way_reflex_names_them(probe):
    """The toggle chooses its icon by comparing against these two strings.

    `reflex.style` is imported here and not in the component, which is the whole
    point: the component states the literals so a reader can see what is being
    compared, and this file proves the literals are still the right ones. A
    Reflex upgrade that renamed a mode would otherwise leave a toggle whose
    comparison never matches -- no error, and a moon on every ground.
    """
    from reflex.style import DARK_COLOR_MODE, LIGHT_COLOR_MODE

    assert probe["modes"] == {"light": LIGHT_COLOR_MODE, "dark": DARK_COLOR_MODE}


def test_the_toggle_is_a_single_control(probe):
    """One button, one icon -- the whole point of replacing the three segments.

    Counted from the rendered class rather than from the source, so a second
    control arriving through a loop or a stray composition is caught the same as
    one typed by hand.
    """
    assert not probe["errors"], probe["errors"]
    assert probe["toggle"].count("hx-ground-toggle") == 1, probe["toggle"]
    assert probe["toggle"].count('type:"button"') == 1, probe["toggle"]


def test_the_icon_is_a_sun_on_light_and_a_moon_on_dark(probe):
    """Both glyphs are in the compiled output, on opposite arms of one branch.

    Asserting both names is what distinguishes a working toggle from one wired to
    a single icon: a component that rendered `LucideMoon` unconditionally would
    look correct in a screenshot of the dark ground and be frozen on the light
    one.
    """
    assert not probe["errors"], probe["errors"]
    assert "LucideSun" in probe["toggle"], probe["toggle"]
    assert "LucideMoon" in probe["toggle"], probe["toggle"]


def test_the_icon_follows_the_ground_actually_on_screen(probe):
    """`resolvedColorMode`, never `rawColorMode`.

    The raw var reports the stored *preference*, which is `"system"` until the
    reader presses this control for the first time -- neither a sun nor a moon.
    An icon chosen from it would fall through to the wrong glyph on exactly the
    default state, which is the state most readers see first. The resolved var
    reports the ground the page is painting, which is what the icon claims.
    """
    assert not probe["errors"], probe["errors"]
    assert "resolvedColorMode" in probe["toggle"], probe["toggle"]
    assert "rawColorMode" not in probe["toggle"], probe["toggle"]


def test_the_toggle_names_the_action_rather_than_the_state(probe):
    """The control draws no text, so `aria-label` is its only name.

    Both directions are present and both come from `ground_copy`, so a reader on
    either ground is told what pressing it does rather than what it currently is
    -- "Switch to dark" beside a sun, not "Light" beside a sun, which would leave
    a screen-reader user to infer the verb.
    """
    assert not probe["errors"], probe["errors"]
    assert ground_copy.GROUND_TO_DARK_LABEL in probe["toggle"]
    assert ground_copy.GROUND_TO_LIGHT_LABEL in probe["toggle"]
    assert "aria-label" in probe["toggle"]


def test_the_toggle_carries_no_visible_text(probe):
    """The minimalism is the requirement, so it is asserted rather than assumed.

    The three-segment switch this replaced rendered `Light`, `Dark` and `System`
    as three words in the masthead. Nothing but the icon and the accessible name
    may come back: a visible label creeping in beside the glyph is the drift this
    catches, and it would be invisible to every other test here.
    """
    assert not probe["errors"], probe["errors"]
    for word in ("Light", "Dark", "System"):
        assert f'"{word}"' not in probe["toggle"], f"{word} is drawn as text"


@pytest.mark.parametrize("label,factory", SURFACES)
def test_the_toggle_reaches_every_surface(probe, label, factory):
    """A reader can change the ground from any screen they can reach.

    Both gates are included on purpose. The toggle carries no state and reaches
    no backend -- `toggle_color_mode` is a client-side event -- so it works
    before sign-in, and the screen where a reader most needs a legible ground is
    the one they are staring at while typing a token they cannot see.

    Parametrized per surface so a failure names the screen that lost it.
    """
    assert not probe["errors"], probe["errors"]
    assert "hx-ground-toggle" in probe["surfaces"][factory], label


# --- The source assertions ------------------------------------------------


def test_the_component_source_exists():
    """A missing file would pass every source test below vacuously."""
    assert SWITCH_SOURCE_PATH.is_file(), SWITCH_SOURCE_PATH


def test_no_colour_is_written_as_a_literal_hex(source):
    """`theme.py` is the only place a colour is spelled."""
    assert re.findall(r"#[0-9a-fA-F]{6}\b", source) == []


def test_the_component_imports_no_token_at_all(source):
    """Stronger than the hex guard, and specific to this component.

    Every rule the toggle needs is `.hx-ground-toggle` in `theme.GLOBAL_CSS`,
    including the icon's dimensions -- which is why the component passes no
    `size` to `rx.icon` either. A `color=theme.INK` or a `size=15` appearing here
    would be a second place the control's appearance is decided, free to disagree
    with the stylesheet.

    Asserted as "does not import `theme`" rather than as "the string `theme.`
    does not appear": the module's docstring names `theme.GLOBAL_CSS` when it
    explains where its styling lives, and a guard that forbade *discussing* the
    stylesheet would push the explanation out of the file to satisfy a grep.
    Without the import there is no token to reach for, which is the claim.
    """
    imports = [
        line
        for line in source.splitlines()
        if line.startswith(("import ", "from ")) and "theme" in line
    ]
    assert imports == [], imports
    assert "from chat_ui import ground_copy" in source, (
        "the component does import its own copy module"
    )


def test_the_icon_is_not_sized_in_the_component(source):
    """The size lives beside the colour, in the one file that owns both.

    `rx.icon("sun", size=15)` would render a `size` prop straight onto the svg
    and quietly win over the stylesheet, splitting the control's appearance
    across two files -- the same defect the token guard above prevents for
    colour, in the one dimension `theme.py`'s docstring also claims ("every
    colour and size").
    """
    assert "size=" not in source, "the svg is sized by .hx-ground-toggle in theme.py"


def test_every_user_facing_string_resolves_from_copy(source):
    """No literal user-facing text in a component (PRD-004 STORY-007's rule).

    Both directions, as `tests/test_session_rail.py` puts it: the constant is
    referenced as `ground_copy.NAME`, and its *value* appears nowhere in the
    source -- a pasted string beside the reference would satisfy the first check
    alone and then drift.
    """
    for name in COPY_NAMES:
        assert f"ground_copy.{name}" in source, f"{name} never rendered"
        value = getattr(ground_copy, name)
        assert f'"{value}"' not in source, f"{name} pasted as {value!r}"


def test_the_copy_constants_are_non_empty():
    """`tests/test_copy.py`'s pattern, for the third copy module."""
    for name in COPY_NAMES:
        value = getattr(ground_copy, name)
        assert isinstance(value, str) and value.strip(), name


def test_the_two_labels_name_opposite_grounds():
    """The pair has to be a pair, and nothing here would notice if it were not.

    Both labels are rendered from one `rx.cond`, so two strings naming the same
    ground -- the copy/paste this catches -- would compile, render, announce
    "Switch to dark" on both grounds, and pass every other test in this file.
    """
    assert ground_copy.GROUND_TO_DARK_LABEL != ground_copy.GROUND_TO_LIGHT_LABEL
    assert "dark" in ground_copy.GROUND_TO_DARK_LABEL.lower()
    assert "light" in ground_copy.GROUND_TO_LIGHT_LABEL.lower()


def test_the_copy_module_holds_only_the_toggles_wording():
    """A third copy module earns its place by staying small.

    `ground_copy.py` exists because the toggle is one control on two surfaces and
    neither `copy.py` nor `admin_copy.py` can own it (its docstring gives the full
    reasoning, including the `tests/test_copy.py` closure that makes `admin_copy`
    impossible). That justification lasts exactly as long as the module holds
    nothing else -- the moment it becomes a general dumping ground for shared
    strings, the boundary between the chat's wording and the console's is gone.
    """
    declared = {
        name for name in dir(ground_copy) if name.isupper() and not name.startswith("_")
    }
    assert declared == set(COPY_NAMES), sorted(declared.symmetric_difference(COPY_NAMES))


# --- The stylesheet owns the control's appearance -------------------------


def test_the_stylesheet_carries_the_toggles_rules():
    """The component is styleless, so these rules are the whole control.

    Colour at rest, colour on hover, and the icon's dimensions. If the class ever
    goes missing from `theme.GLOBAL_CSS` the toggle still renders and still works
    -- as a browser-default button with a 24px black glyph in the masthead -- so
    nothing else in this file would fail.
    """
    assert ".hx-ground-toggle {" in theme.GLOBAL_CSS
    assert ".hx-ground-toggle svg {" in theme.GLOBAL_CSS
    assert ".hx-ground-toggle:hover {" in theme.GLOBAL_CSS


def test_the_stylesheet_quotes_no_user_facing_string():
    """A comment in `theme.GLOBAL_CSS` is shipped page content, not a note.

    `index()` emits the stylesheet through `rx.el.style(...)` at the top of every
    page, so any label named in a comment lands in the compiled output *before*
    the component that renders it. `tests/test_chat_shell.py` locates the
    masthead and the rail by their copy to assert the page's band order, and a
    draft of the ground toggle's comment named three controls by their exact
    labels -- putting the rail's wording above the masthead's and inverting the
    order that test reads. It failed honestly and this is the guard that keeps it
    from being rediscovered.

    Every copy module, because the stylesheet is shared by both surfaces.

    Two exclusions, both necessary and neither of them a weakening. The custom
    property *names* are lowercased token names, so `--hx-ink-denied` contains
    the verdict label "denied" and `--hx-ink-fault` contains "fault" -- they are
    stripped first, because a guard that fired on them would forbid the palette
    from being declared. And values under five characters after stripping are
    skipped: `admin_copy`'s filter joiner is the word "and", which no English
    comment can avoid. What remains is every real label, matched on word
    boundaries so "Retry" is caught and "retrying" is not mistaken for it.
    """
    from chat_ui.chat_ui import admin_copy
    from chat_ui.chat_ui import copy as chat_copy

    prose = re.sub(r"--hx-[a-z0-9-]+", "", theme.GLOBAL_CSS)

    offenders = []
    for module in (chat_copy, admin_copy, ground_copy):
        for name in dir(module):
            if not name.isupper() or name.startswith("_"):
                continue
            value = getattr(module, name)
            if not isinstance(value, str) or len(value.strip()) < 5:
                continue
            if re.search(rf"\b{re.escape(value.strip())}", prose):
                offenders.append(f"{module.__name__}.{name} = {value!r}")
    assert offenders == [], offenders


def test_the_toggle_spends_no_ink_the_design_did_not_already_have():
    """MUTE at rest, INK on hover, on the register's HOVER ground.

    The same three tokens `shell.py` and `admin_shell.py` give the sign-out
    control beside it. PRD-006 Section 6.1 closes the palette to new accents, and
    an icon is exactly where one would arrive first -- a blue moon, a yellow sun.
    """
    rule_start = theme.GLOBAL_CSS.index(".hx-ground-toggle {")
    rules = theme.GLOBAL_CSS[rule_start : rule_start + 900]
    used = set(re.findall(r"var\(--hx-[a-z0-9-]+\)", rules))
    assert used <= {theme.MUTE, theme.INK, theme.HOVER}, sorted(
        used - {theme.MUTE, theme.INK, theme.HOVER}
    )


# --- The palette plumbing -------------------------------------------------


def test_every_colour_token_is_a_custom_property_reference():
    """The indirection the whole ground toggle rests on.

    A token left as a raw hex would render a colour that cannot follow the class
    on the document element: correct on the light ground, frozen on the dark one,
    and invisible to `tests/test_contrast.py`, which reads the palettes rather
    than the tokens. Derived from `LIGHT`'s keys rather than from a typed list, so
    a colour added tomorrow is covered without anyone remembering this file.
    """
    for name in theme.LIGHT:
        value = getattr(theme, name)
        assert re.fullmatch(r"var\(--hx-[a-z0-9-]+\)", value), f"{name} = {value!r}"


@pytest.mark.parametrize("palette_name", ("LIGHT", "DARK"))
def test_the_stylesheet_declares_every_token_on_both_grounds(palette_name):
    """Every reference resolves, on the ground it is read on.

    `tests/test_contrast.py` proves the palettes are legible; this proves they
    arrive. An undeclared custom property is not an error in CSS -- the
    declaration is simply dropped and the element renders with whatever it
    inherited -- so a token missing from one block is a silent hole on one ground
    only, which is the hardest kind of colour bug to see in a diff.
    """
    palette = getattr(theme, palette_name)
    for name, value in palette.items():
        declaration = f"--hx-{name.lower().replace('_', '-')}: {value};"
        assert declaration in theme.GLOBAL_CSS, declaration


def test_the_stylesheet_carries_exactly_one_block_per_ground():
    """The switch is `html.dark`, and it is the selector Reflex actually sets.

    `theme.py`'s docstring states why there is no `prefers-color-scheme` media
    query here: Reflex's pre-paint script resolves "system" against the OS itself
    and stamps the class, so a media query would fight that class on every
    machine whose OS setting and explicit choice disagree. Asserting its absence
    keeps that reasoning from being quietly undone by a future edit that "adds
    dark mode support" a second time.
    """
    assert theme.GLOBAL_CSS.count("html.dark {") == 1
    assert theme.GLOBAL_CSS.count(":root {") == 1
    assert "prefers-color-scheme" not in theme.GLOBAL_CSS


def test_both_grounds_declare_their_colour_scheme():
    """The one thing the custom properties cannot reach.

    Form controls, the scrollbar gutter and the canvas behind an overscroll are
    painted by the browser, not by this stylesheet. Without `color-scheme` they
    stay light on a dark page -- the exact mismatch `chat_ui.py` records as the
    reason the Radix appearance was pinned in the first place.
    """
    assert "color-scheme: light;" in theme.GLOBAL_CSS
    assert "color-scheme: dark;" in theme.GLOBAL_CSS


def test_the_radix_appearance_follows_the_colour_mode():
    """The pin that would reintroduce the bug it was added to fix.

    `appearance="light"` was correct while the design had one palette: it stopped
    Radix painting dark-mode controls on a light page. With two palettes the same
    pin produces the mirror defect -- light-mode Radix controls on a slate page --
    so the appearance has to resolve from the same colour mode `html.dark` does.

    Asserted over the source rather than by importing the app: `chat_ui.py` builds
    the real `rx.App`, mounts the FastAPI app and calls `init_db()` at import.

    Comment lines are stripped first, and that is not a convenience. The comment
    above the call deliberately quotes the old `appearance="light"` to record why
    the pin existed and why it inverted -- history worth keeping, and exactly the
    kind of prose a naive substring check would force someone to delete.
    """
    source = (REPO_ROOT / "chat_ui" / "chat_ui" / "chat_ui.py").read_text(
        encoding="utf-8"
    )
    code = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )
    assert 'appearance="inherit"' in code
    assert 'appearance="light"' not in code
    assert 'appearance="dark"' not in code
