"""Smoke and invariant tests for the summary's tally sheet.

The same two halves `tests/test_register.py` is built from, and for the same
reasons.

**The build probe** runs in a subprocess with `PYTHONPATH` set to `chat_ui/`,
which is how Reflex itself imports the app (`chat_ui.components...`, not
`chat_ui.chat_ui.components...`). Doing it in-process would put the inner package
on `sys.path` and break every other test module, which reaches the same files by
their repo-root path.

**The source assertions** read the module as text, covering the criteria a build
cannot: that no colour is written as a literal hex, that every string resolves
from `admin_copy`, that the sheet paints none of the register's verdict inks, and
that the type roles are the way round PRD-006 Section 6.1 inverts them.

**Where the nine figures are asserted.** Not here. The labels, values, scopes and
shares live on `SummaryFigure` objects built in `AdminState`, so the compiled
sheet carries `total_figure?.["label"]` rather than the words — which is the
derived-once rule working, not a gap. `tests/test_admin_state.py` asserts the
nine figures and their contents; what this file asserts is that the sheet binds
to all five figure vars, so every figure that exists reaches the screen. The two
halves together are the claim.

**`figure["items"]`, not `figure.items`.** `SummaryFigure.items` collides with
`ObjectVar.items`, the dict-like method on every Reflex object Var, so the
attribute form yields a bound method and `rx.foreach` raises at build time. The
probe would catch it; the source guard below names it, because the failure is
otherwise mystifying.
"""

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from chat_ui.chat_ui import admin_copy, theme  # noqa: E402
from chat_ui.chat_ui.admin_state import RANKED_LIMIT  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTHONPATH = [str(REPO_ROOT / "chat_ui"), str(REPO_ROOT)]

SUMMARY_SOURCE_PATH = REPO_ROOT / "chat_ui" / "chat_ui" / "components" / "summary.py"

# Every string the sheet itself puts on screen — the three block headings, the
# two explanatory lines, the ranked list's empty case and the empty sheet's
# panel. The nine figure labels are deliberately absent: they arrive through
# `SummaryFigure`, and `tests/test_admin_state.py` asserts them there.
COPY_NAMES = (
    "SUMMARY_COUNTS_HEADING",
    "SUMMARY_WHO_HEADING",
    "SUMMARY_PII_HEADING",
    "SUMMARY_SCOPE_NOTE",
    "FIGURE_COMPLETION_NOTE",
    "RANKED_EMPTY_LABEL",
    "EMPTY_SUMMARY_TITLE",
    "EMPTY_SUMMARY_BODY",
)

# The five figure vars, and therefore the nine figures. A sheet that dropped one
# would render eight figures and pass every other test in this file.
FIGURE_VARS = (
    "total_figure",
    "blocked_figures",
    "completion_figure",
    "who_figures",
    "pii_figures",
)

# The four `SummaryFigure` fields the sheet renders, as they compile.
FIGURE_FIELDS = ("label", "value", "scope", "share", "items")

# The register's legend, and not this surface's. PRD-006 Section 6.1 gives the
# four inks one job each — a verdict on a row — and a figure is not a verdict.
VERDICT_INKS = {
    "INK_CLEAR": theme.INK_CLEAR,
    "INK_HELD": theme.INK_HELD,
    "INK_DENIED": theme.INK_DENIED,
    "INK_FAULT": theme.INK_FAULT,
}

# Everything the sheet is allowed to paint: the ground tokens, and nothing else.
# Computed from theme.py rather than hard-coded, so retuning a token retunes the
# assertion in the same edit.
ALLOWED_COLOURS = {
    theme.PAPER.upper(),
    theme.CARD.upper(),
    theme.INK.upper(),
    theme.MUTE.upper(),
    theme.RULE.upper(),
    theme.RULE_SOFT.upper(),
}

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
    from chat_ui.admin_state import AdminState
    from chat_ui.components.summary import (
        summary,
        _block,
        _empty_summary,
        _figure,
        _figure_note,
        _indented_figure,
        _rank_line,
        _ranked_items,
        _scope_note,
        _sheet,
        _sheet_body,
    )
except Exception as exc:
    print(json.dumps({"errors": ["import: {}: {}".format(type(exc).__name__, exc)]}))
    sys.exit(0)

# The separation, from the importing side: nothing the sheet pulls in may drag a
# chat component along with it.
result["chat_modules_loaded"] = [
    name
    for name in ("chat_ui.components.chat", "chat_ui.components.bubbles")
    if name in sys.modules
]

# Every factory builds. The per-figure helpers are exercised through a real
# rx.foreach so they are handed the Var they get in production, not a mock.
broken = []
built = {}
factories = [
    ("summary", lambda: summary()),
    ("sheet", lambda: _sheet()),
    ("body", lambda: _sheet_body()),
    ("empty_summary", lambda: _empty_summary()),
    ("scope_note", lambda: _scope_note()),
    ("total", lambda: _figure(AdminState.total_figure)),
    ("completion", lambda: _figure(AdminState.completion_figure)),
    (
        "blocked",
        lambda: rx.box(rx.foreach(AdminState.blocked_figures, _indented_figure)),
    ),
    ("who", lambda: rx.box(rx.foreach(AdminState.who_figures, _figure))),
    ("pii", lambda: rx.box(rx.foreach(AdminState.pii_figures, _figure))),
    (
        "ranked_items",
        lambda: rx.box(rx.foreach(AdminState.who_figures, _ranked_items)),
    ),
    ("rank_line", lambda: rx.box(rx.foreach(AdminState.top_models, _rank_line))),
    ("note", lambda: _figure_note("a note")),
    ("block", lambda: _block("HEADING", _figure(AdminState.total_figure))),
]
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

result["rendered"] = built.get("summary", "")
for _name in (
    "sheet",
    "body",
    "empty_summary",
    "scope_note",
    "total",
    "completion",
    "blocked",
    "who",
    "pii",
    "ranked_items",
    "note",
    "block",
):
    result[_name] = built.get(_name, "")

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
            # summary imports admin_state, which imports app.config.settings,
            # where ADMIN_TOKEN is a required field. Same defaults
            # tests/test_register.py sets.
            "ADMIN_TOKEN": os.environ.get("ADMIN_TOKEN", "test-token"),
            "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", "test-key"),
        },
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.fail(f"summary probe crashed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def source() -> str:
    return SUMMARY_SOURCE_PATH.read_text(encoding="utf-8")


# --- The build probe ------------------------------------------------------


def test_module_imports(probe):
    """Catches circular imports and names missing at module scope."""
    assert not probe["errors"], probe["errors"]


def test_every_factory_builds(probe):
    """The sheet, the three blocks' helpers, the empty panel and the notes.

    This is also where `figure.items` would fail if it were ever written that
    way: `rx.foreach` over the attribute form raises `TypeError` at build time.
    """
    assert not probe["errors"], probe["errors"]
    assert not probe["broken_factories"], probe["broken_factories"]


def test_the_summary_loads_no_chat_component(probe):
    """PRD-006 Section 4, from the importing side: not one chat module is pulled
    in transitively."""
    assert not probe["errors"], probe["errors"]
    assert not probe["chat_modules_loaded"], probe["chat_modules_loaded"]


@pytest.mark.parametrize("var", FIGURE_VARS)
def test_every_figure_var_reaches_the_sheet(probe, var):
    """AC 1, in the half a component test can carry.

    The nine labels are on `SummaryFigure` objects the state builds, so the
    compiled sheet references the vars rather than the words —
    `tests/test_admin_state.py` asserts the nine figures those vars hold. What is
    asserted here is that all five reach the screen, so no figure is built and
    then left unrendered.
    """
    assert not probe["errors"], probe["errors"]
    assert var in probe["rendered"], var


@pytest.mark.parametrize("field", FIGURE_FIELDS)
def test_every_figure_field_is_rendered(probe, field):
    """A figure's label, value, scope, share and ranked items all reach the
    output — a field built in state and never bound is a fact the sheet claims to
    carry and does not."""
    assert not probe["errors"], probe["errors"]
    assert f'["{field}"]' in probe["rendered"], field


def test_the_three_blocks_are_headed(probe):
    """PRD-006 Section 6.1's structure: the counts, the who/what facts, then PII
    telemetry closing the sheet."""
    assert not probe["errors"], probe["errors"]
    for heading in (
        admin_copy.SUMMARY_COUNTS_HEADING,
        admin_copy.SUMMARY_WHO_HEADING,
        admin_copy.SUMMARY_PII_HEADING,
    ):
        assert heading in probe["rendered"], heading


def test_only_the_blocked_figures_are_indented(probe, source):
    """AC 2's first half. The indent is a `padding_left` of `theme.STAMP_X`, and
    it must reach the two blocked figures and no other figure — indenting a
    fourth would assert a subset relationship that is not there.

    Counted in the source rather than the output: the compiled sheet cannot say
    which `padding_left` belonged to which call. Two uses, and exactly two —
    `_indented_figure`, and the completion note, which is indented because it
    belongs to the figure above it rather than to the block.
    """
    assert not probe["errors"], probe["errors"]
    assert "_indented_figure" in source
    assert source.count("indent=theme.STAMP_X") == 1
    assert (
        "rx.foreach(AdminState.blocked_figures, _indented_figure)" in source
    ), "the blocked pair is what indents"
    assert theme.STAMP_X in probe["blocked"]


def test_the_completion_note_is_on_the_sheet(probe):
    """AC 3's second half: the label states what the number counts, the note says
    why it is not an answer rate."""
    assert not probe["errors"], probe["errors"]
    assert admin_copy.FIGURE_COMPLETION_NOTE in probe["rendered"]


def test_the_sheet_never_says_success_rate(probe):
    """AC 3. STORY-016 pins the constant; this pins the screen, including any
    stray literal a component might introduce beside it."""
    assert not probe["errors"], probe["errors"]
    assert "success rate" not in probe["rendered"].lower()


def test_the_scope_note_states_the_two_windows(probe):
    """AC 4 and PRD-006 Risk 4: the sheet names the difference between its
    all-time totals and the register's window, rather than leaving 3,180 beside
    100 rows to read as a contradiction."""
    assert not probe["errors"], probe["errors"]
    assert admin_copy.SUMMARY_SCOPE_NOTE in probe["rendered"]
    assert admin_copy.SUMMARY_SCOPE_NOTE in probe["scope_note"]


def test_the_ranked_lists_state_their_cut(probe):
    """AC 6. The cut rides on the figure's value, built from RANKED_LIMIT — the
    same constant the read passes as its `limit`."""
    assert not probe["errors"], probe["errors"]
    assert admin_copy.RANKED_CUT_TEMPLATE.format(n=RANKED_LIMIT) == "top 5"
    assert "value" in probe["who"]
    assert admin_copy.RANKED_EMPTY_LABEL in probe["who"]


def test_the_empty_sheet_says_why(probe):
    """A total of 0 is stated, not shown as nine dashes, and the panel ends in the
    action available from it."""
    assert not probe["errors"], probe["errors"]
    assert admin_copy.EMPTY_SUMMARY_TITLE in probe["empty_summary"]
    assert admin_copy.EMPTY_SUMMARY_BODY in probe["empty_summary"]


def test_the_body_chooses_between_the_sheet_and_the_empty_panel(probe, source):
    """The precedence is `AdminState.summary_state`'s, and the fault arm renders
    the sheet: `FAULT_MESSAGE_TEMPLATE` promises "Nothing on screen has changed",
    so the figures from the last good read stay standing under STORY-017's
    panel."""
    assert not probe["errors"], probe["errors"]
    assert "summary_state" in probe["rendered"]
    assert "(SUMMARY_STATE_FAULT, _sheet())" in source
    assert "(SUMMARY_STATE_EMPTY, _empty_summary())" in source


def test_no_colour_outside_the_allowed_set(probe):
    """AC 7, over the rendered output rather than the source.

    A source grep cannot see a colour a component supplies at compile time — the
    failure `admin_shell.py` records for `rx.link`'s Radix accent. This collects
    every hex the compiled sheet actually contains and holds it to the ground
    tokens.
    """
    assert not probe["errors"], probe["errors"]
    found = {c.upper() for c in re.findall(r"#[0-9a-fA-F]{6}\b", probe["rendered"])}
    assert found <= ALLOWED_COLOURS, sorted(found - ALLOWED_COLOURS)


@pytest.mark.parametrize("name", sorted(VERDICT_INKS))
def test_no_verdict_ink_is_painted_on_the_summary(probe, name):
    """AC 7's "no accent colour". The four inks are the register's legend, one per
    outcome; a figure is not an outcome, and borrowing an ink here would say a
    number had a verdict."""
    assert not probe["errors"], probe["errors"]
    assert VERDICT_INKS[name].upper() not in probe["rendered"].upper(), name


def test_no_tint_reaches_the_output(probe):
    """PRD-006 Risk 6. The palette test asserts the module names no tint; this
    asserts none arrives in the output by another route."""
    assert not probe["errors"], probe["errors"]
    rendered = probe["rendered"].upper()
    for name in (
        "TINT_CLEAR",
        "TINT_HELD",
        "TINT_DENIED",
        "TINT_UPSTREAM",
        "TINT_FAULT",
    ):
        assert getattr(theme, name).upper() not in rendered, name


def test_the_sheet_carries_no_card(probe):
    """AC 7, as the list of what is absent.

    PRD-006 Risk 6 names the drift this catches: "admin console" is the strongest
    pull toward KPI cards in the whole design space, and it "arrives one
    reasonable-looking component at a time, usually as a Radix card imported for
    convenience". A card is a fill, a shadow and a radius; the sheet has rules.
    """
    assert not probe["errors"], probe["errors"]
    rendered = probe["rendered"].lower()
    for card_property in ("boxshadow", "borderradius", "background"):
        assert card_property not in rendered, card_property


# --- The source assertions ------------------------------------------------


def test_source_is_discoverable(source):
    """A missing file would pass every source test below vacuously."""
    assert source.strip(), SUMMARY_SOURCE_PATH


def test_no_literal_hex_colour(source):
    """Every colour resolves from theme.py (AC 7).

    A hex in this file is a colour a change of visual direction would miss,
    breaking the single-file guarantee theme.py's own docstring makes.
    """
    offenders = re.findall(r"#[0-9a-fA-F]{6}\b", source)
    assert not offenders, f"colours belong in theme.py: {offenders}"


@pytest.mark.parametrize("name", COPY_NAMES)
def test_every_string_is_read_from_admin_copy(source, name):
    assert f"admin_copy.{name}" in source, f"{name} is not rendered from admin_copy"


@pytest.mark.parametrize("name", COPY_NAMES)
def test_no_copy_value_is_written_as_a_literal(source, name):
    value = getattr(admin_copy, name)
    assert f'"{value}"' not in source, f"{name}'s value is a literal in the summary"
    assert f"'{value}'" not in source, f"{name}'s value is a literal in the summary"


@pytest.mark.parametrize("forbidden", FORBIDDEN_IMPORTS)
def test_source_imports_no_chat_component(source, forbidden):
    """PRD-006 Section 4, from the source side. Complements the `sys.modules`
    probe: this catches an import that exists but happens not to have executed."""
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]
    offenders = [line for line in import_lines if forbidden in line]
    assert not offenders, offenders


@pytest.mark.parametrize("ink", ["INK_UPSTREAM", "INK_SELF", "TINT_"])
def test_the_source_names_no_chat_only_colour(source, ink):
    """The two chat-only inks and the five tints, from the source side —
    `tests/test_admin_palette.py` globs this file for the same thing, and the
    duplication is deliberate: that guard is about the console as a whole, this
    one fails inside the summary's own test run."""
    assert ink not in source, ink


def test_the_body_face_is_reserved_for_the_two_explanatory_lines(source):
    """PRD-006 Section 6.1 reserves `FONT_BODY` for "the two or three explanatory
    lines that state a scope". The sheet has exactly three uses and they are
    exactly those lines: the opening scope note, the per-figure scope, and the
    completion note. The empty panel's sentence is the fourth — it is an
    explanatory line of the same kind, and it is the only one on screen when it
    renders, because it replaces the sheet entirely.

    An exact count, not a ceiling: everything else here is a number or a label,
    and the reading face creeping onto a fifth element is how a tally sheet
    starts reading as prose.
    """
    assert source.count("theme.FONT_BODY") == 4, source.count("theme.FONT_BODY")


def test_the_data_face_carries_the_values(source):
    """PRD-006 Section 6.1 inverts the chat's type roles on this console:
    `FONT_DATA` is the dominant face because the sheet is numbers, and they must
    align down the right edge to be comparable at a glance."""
    assert source.count("theme.FONT_DATA") > source.count("theme.FONT_DISPLAY")


def test_the_ranked_items_are_read_by_subscript(source):
    """`SummaryFigure.items` collides with `ObjectVar.items`, the dict-like method
    on every Reflex object Var, so `figure.items` yields a bound method and
    `rx.foreach` raises at build time. The subscript form returns a typed
    `list[str]`. Verified against the pinned reflex==0.9.6.post1.

    Guarded in the source because the attribute form is the one anybody would
    write first, and its error message names neither `items` nor the figure.

    Asserted over the parsed tree rather than the text: the module and
    `_ranked_items` both name the attribute form in order to warn about it, and a
    text guard that cannot tell a warning from a use would be answered by
    deleting the warning.
    """
    assert '["items"]' in source

    offenders = [
        node.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Attribute) and node.attr == "items"
    ]
    assert not offenders, offenders


def test_the_summary_sets_no_focus_reset(source):
    """theme.GLOBAL_CSS gives every focusable element a visible ring; a local
    `outline: none` would silently take it back."""
    for killer in ("outline", "box_shadow"):
        assert f'"{killer}": "none"' not in source, killer
    assert 'outline="none"' not in source


def test_the_sheet_scrolls_in_its_own_container(source):
    """The sheet scrolls, not the page. A flex child will not shrink below its
    content without `min-height: 0`, so without it the container grows past the
    viewport and the document takes over the scrolling."""
    assert 'overflow_y="auto"' in source
    assert 'min_height="0"' in source
    assert 'class_name="hx-scroll"' in source


def test_the_sheet_answers_a_narrow_viewport_by_wrapping(source):
    """The same move `admin_masthead` and `_filter_strip` make: the value drops
    under its label rather than crushing it, with no breakpoint and no new CSS."""
    assert 'wrap="wrap"' in source
