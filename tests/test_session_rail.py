"""Smoke and invariant tests for the session rail.

Two halves, following `tests/test_register.py`, because two kinds of claim need
two different tools.

**The build probe** runs in a subprocess with `PYTHONPATH` set to `chat_ui/`,
which is how Reflex itself imports the app (`chat_ui.components...`, not
`chat_ui.chat_ui.components...`). Doing it in-process would put the inner
package on `sys.path` and break every other test module, which reaches the same
files by their repo-root path. Every row helper is exercised with
`ChatState.sessions[0]` — a Var, never a concrete `ChatSessionSummary` — because
`rx.foreach` hands them a JS reference and calling them any other way would not
compile the same code.

**The source assertions** read the module as text. They cover what a build
cannot: that no colour is written as a literal hex, that no rail token is
written as its value, that every user-facing string resolves from `copy`, and
that the type roles are the ones PRD-008 Section 6.1 fixes.

**The design guards landed in STORY-020**, in the third section below: no
`TINT_*`, no verdict ink, no radius beyond `theme.RADIUS`, and every colour a
ground token. They are PRD-008 Risk 6's "component test", and they extended this
file rather than replacing it — STORY-018's own combined floor test,
`test_the_rail_renders_only_ground_tokens_and_one_radius`, was split into
`test_the_only_radius_in_the_rail_is_the_theme_radius` and
`test_every_colour_in_the_rail_is_a_ground_token` so that a drift prints one
failure naming one claim.

**The `INK_SELF` exception, and how it was resolved.** `theme.INK_SELF ==
theme.INK` (both `#14181C`), so a verdict-ink guard that tests `INK_SELF in
rendered` fires on every rail row's title colour: right about the bytes, wrong
about the claim. It is the same shape of exception `tests/test_admin_palette.py`
records for the `:focus-visible` ring. AC 2 is therefore asserted in two halves —
six inks by value against the rendered output, all seven by token name against
the source — and `test_ink_self_cannot_be_excluded_by_rail_value` records why,
so that a future attempt to "complete" the value tuple finds the reason first.

**The violation was run.** A `TINT_HELD` background on the active row turned
`test_no_tint_reaches_the_rail[TINT_HELD]` and
`test_every_colour_in_the_rail_is_a_ground_token` red together, and was removed;
the run is recorded in STORY-020's report. Because a removed violation proves
nothing about tomorrow, `test_the_tint_guard_detects_a_tint` runs the same
comparison over a synthetic sample and keeps the claim standing.
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

from chat_ui.chat_ui import copy, theme  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTHONPATH = [str(REPO_ROOT / "chat_ui"), str(REPO_ROOT)]

RAIL_SOURCE_PATH = REPO_ROOT / "chat_ui" / "chat_ui" / "components" / "session_rail.py"

# Every string the rail puts on screen. Each must reach it through `copy.`, and
# none may appear in the source as a literal.
COPY_NAMES = (
    "SESSION_NEW_CHAT_LABEL",
    "SESSION_RAIL_EMPTY_TITLE",
    "SESSION_RAIL_EMPTY_BODY",
    "SESSION_RAIL_FAULT_TITLE",
    "SESSION_RAIL_FAULT_BODY",
    "SESSION_RENAME_LABEL",
    "SESSION_RENAME_PLACEHOLDER",
    "SESSION_DELETE_CONFIRM_TEMPLATE",
    "SESSION_DELETE_CONFIRM_LABEL",
    "SESSION_DELETE_CANCEL_LABEL",
    "RETRY_LABEL",
)

# The three tokens STORY-017 declared for this surface. The rail must name them,
# never their values -- the single-file rule that story exists to enforce.
RAIL_TOKEN_VALUES = {
    "SESSION_RAIL_W": theme.SESSION_RAIL_W,
    "SESSION_RAIL_ROW_H": theme.SESSION_RAIL_ROW_H,
    "SESSION_RAIL_GUTTER": theme.SESSION_RAIL_GUTTER,
}


@pytest.fixture(scope="module")
def source() -> str:
    return RAIL_SOURCE_PATH.read_text(encoding="utf-8")


def _docstring_nodes(tree: ast.AST) -> set:
    """Every `ast.Constant` that is a docstring, by identity.

    This module argues its refusals in prose -- it names `rx.alert_dialog` in
    order to refuse it, and quotes the copy constants' own words to explain
    them. So the assertions below are about *code*, and the prose has to be
    excluded rather than the prose rewritten to dodge a grep: a comment that
    cannot say what it refuses is worth less than the test.
    """
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                found.add(id(body[0].value))
    return found


@pytest.fixture(scope="module")
def code_strings(source) -> list:
    """Every string literal the rail's *code* contains, docstrings excluded."""
    tree = ast.parse(source)
    docs = _docstring_nodes(tree)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docs
    ]


# --------------------------------------------------------------------------
# The build probe
# --------------------------------------------------------------------------


_CHECK_SCRIPT = r"""
import json, re, sys

result = {"errors": []}
try:
    import reflex as rx
    from chat_ui import copy, theme
    from chat_ui.components import session_rail as mod
    from chat_ui.state import ChatState
except Exception as exc:
    print(json.dumps({"errors": ["import: {}: {}".format(type(exc).__name__, exc)]}))
    sys.exit(0)

# A Var, exactly as rx.foreach supplies one.
row = ChatState.sessions[0]

for name in ("_spine", "_row_open_button", "_row_actions", "_rename_field",
             "_delete_confirm", "_row"):
    try:
        getattr(mod, name)(row)
    except Exception as exc:
        result["errors"].append("{}: {}: {}".format(name, type(exc).__name__, exc))

for name in ("_new_chat_control", "_scope_line", "_empty_state", "_fault_state",
             "_body", "session_rail"):
    try:
        getattr(mod, name)()
    except Exception as exc:
        result["errors"].append("{}: {}: {}".format(name, type(exc).__name__, exc))

rendered = str(mod.session_rail())
result["rendered_len"] = len(rendered)
# The stylesheet belongs to index(); a second copy on the page is the mistake
# PRD-006's admin components were told not to make.
result["carries_global_css"] = "::selection" in rendered or "hx-composer" in rendered

# The delete sentence must interpolate the row's title as a Var expression, not
# leak Reflex's internal marker into the page as text.
confirm = str(mod._delete_confirm(row))
result["confirm_leaks_marker"] = "<reflex.Var>" in confirm
result["confirm_reads_title"] = '["title"]' in confirm

# The signature, and the three tokens it is built from.
result["has_spine"] = theme.SPINE in rendered
result["spine_only_when_active"] = str(mod._spine(row)).count(theme.SPINE) == 1
result["has_rail_x"] = theme.RAIL_X in rendered
result["has_glyph"] = theme.GLYPH in rendered

# Every colour the rail actually renders.
# Every colour the rail actually renders, named by its token rather than by its
# value: `theme.PAPER` *is* the string `var(--hx-paper)` now that theme.py holds
# two palettes, and the hex appears only in the stylesheet. A hex search here
# would come back empty, and every comparison below is a subset or a membership
# check that an empty set satisfies -- so the collector matches the reference
# form, which is exactly what `getattr(theme, NAME)` returns.
result["colours"] = sorted(set(re.findall(r"var\(--hx-[a-z0-9-]+\)", rendered)))

# Every radius, in both spellings the compiled output can carry: Reflex's
# inline-style JS form, and raw CSS from a style string or a `_hover` block.
# STORY-020 widened this -- the JS-only matcher it inherited would let a
# raw-CSS pill through unseen, and a pill is the drift's first step.
_RADIUS_FORMS = {
    "js": r'\["borderRadius"\] : "([^"]+)"',
    "css": r"border-radius\s*:\s*([^;\"'}]+)",
}
_by_form = {
    form: [value.strip() for value in re.findall(pattern, rendered)]
    for form, pattern in _RADIUS_FORMS.items()
}
result["radii"] = sorted({value for values in _by_form.values() for value in values})
# The per-form counts, so a Reflex change to the compiled shape is visible
# rather than silent: a detector that quietly matches nothing is worse than
# no detector. Same defence `_page_without_the_stylesheet` uses for its strip.
result["radius_form_counts"] = {form: len(values) for form, values in _by_form.items()}

print(json.dumps(result))
"""


@pytest.fixture(scope="module")
def probe() -> dict:
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(_PYTHONPATH))
    proc = subprocess.run(
        [sys.executable, "-c", _CHECK_SCRIPT],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, f"probe crashed:\n{proc.stdout}\n{proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_the_rail_and_every_helper_build(probe):
    """AC 1's structural half: the module imports the way Reflex imports it and
    every function in it compiles against a Var."""
    assert probe["errors"] == []
    assert probe["rendered_len"] > 0


def test_the_rail_does_not_re_emit_the_global_stylesheet(probe):
    """The story's last technical note, checked rather than trusted."""
    assert probe["carries_global_css"] is False


def test_the_active_mark_is_spine_and_appears_once_per_row(probe):
    """AC 2. One mark, in `SPINE`, on the active arm of the row's `rx.cond` --
    and only there, so an inactive row renders no mark at all."""
    assert probe["has_spine"] is True
    assert probe["spine_only_when_active"] is True


def test_the_mark_is_built_from_the_rail_and_glyph_tokens(probe):
    """PRD Section 6.1: the mark "is `RAIL_X` / `GLYPH` / `SPINE` ... appearing a
    third time, at a third scale". Reused, not re-declared at the same value."""
    assert probe["has_rail_x"] is True
    assert probe["has_glyph"] is True


def test_the_delete_sentence_interpolates_the_title_as_a_var(probe):
    """AC 9: the confirmation names the chat.

    `str.format` with a Var is the supported form -- Reflex resolves the marker
    it embeds once the result reaches a component -- but the failure mode if it
    ever stops being supported is silent: the marker renders as page text rather
    than raising. So both halves are asserted, the leak and the read.
    """
    assert probe["confirm_leaks_marker"] is False
    assert probe["confirm_reads_title"] is True


# --------------------------------------------------------------------------
# The design guards (STORY-020)
# --------------------------------------------------------------------------
#
# PRD-008 Risk 6, in full, over the rail's compiled output. STORY-018 shipped
# one combined floor test here and named this story as the owner of the rest;
# `test_the_rail_renders_only_ground_tokens_and_one_radius` was split into the
# two guards below rather than left beside them, so that a drift prints one
# failure naming one claim instead of two failures naming the same edit.
#
# Every token is read from `theme.py` by name, never copied as a literal: a
# token retuned in `theme.py` retunes these assertions in the same edit, which
# is the single-file guarantee `theme.py`'s own docstring makes.


# The six fills in `theme.py`. `tests/test_render_invariants.py` lists five,
# because PRD-006 predates `TINT_FORBIDDEN`; the rail refuses all six.
TINT_NAMES = (
    "TINT_CLEAR",
    "TINT_HELD",
    "TINT_DENIED",
    "TINT_FORBIDDEN",
    "TINT_UPSTREAM",
    "TINT_FAULT",
)

# The seven verdict inks AC 2 names, split by how each one can honestly be
# checked. Six have values of their own and are asserted against what the rail
# renders; `INK_SELF` does not -- see `test_ink_self_cannot_be_excluded_by_rail_value`.
VERDICT_INKS_BY_VALUE = (
    "INK_CLEAR",
    "INK_HELD",
    "INK_DENIED",
    "INK_FORBIDDEN",
    "INK_UPSTREAM",
    "INK_FAULT",
)
VERDICT_INK_NAMES = VERDICT_INKS_BY_VALUE + ("INK_SELF",)

# PRD-008 Section 6.1's grounds, and the whole of the rail's permitted palette.
GROUND_TOKEN_NAMES = (
    "PAPER",
    "CARD",
    "INK",
    "MUTE",
    "RULE",
    "RULE_SOFT",
    "HOVER",
    "SPINE",
)


def _ground_values() -> set:
    return {getattr(theme, name).upper() for name in GROUND_TOKEN_NAMES}


@pytest.mark.parametrize("name", TINT_NAMES)
def test_no_tint_reaches_the_rail(probe, name):
    """AC 1. PRD-008 Risk 6: the drift "arrives one reasonable component at a
    time -- a card for a row, a rounded highlight for the active one, an accent
    for the button".

    A tint is that first card. The five `TINT_*` fills isolate one panel among
    the transcript's prose, and the rail has no prose -- it is a shelf of
    labels. Section 6.1 is explicit that the active session is marked "with
    `INK` type against `HOVER`, not with a fill or an accent".

    Parametrized per tint rather than aggregated, so a failure names the fill
    that arrived.
    """
    assert probe["errors"] == [], probe["errors"]
    value = getattr(theme, name).upper()
    found = {value.upper() for value in probe["colours"]}
    assert value not in found, f"{name} ({value}) is a fill, and the rail carries none"


@pytest.mark.parametrize("name", VERDICT_INKS_BY_VALUE)
def test_no_verdict_ink_reaches_the_rail(probe, name):
    """AC 2, for the six inks that have a value of their own.

    PRD-008 Section 6.1: "The seven verdict inks stay in the transcript, where
    they mean something: a rail row is not a verdict and must not borrow one."
    A session is not cleared, held or denied -- it is a conversation that
    contains turns which were, and colouring the shelf by the last verdict in
    the volume is precisely the accent this design refuses.
    """
    assert probe["errors"] == [], probe["errors"]
    value = getattr(theme, name).upper()
    found = {value.upper() for value in probe["colours"]}
    assert value not in found, f"{name} ({value}) belongs to the transcript"


@pytest.mark.parametrize("name", VERDICT_INK_NAMES)
def test_the_rail_names_no_verdict_ink(source, name):
    """AC 2's other half, by token name over the source.

    This is the mechanism `tests/test_admin_palette.py` uses for the console's
    two chat-only inks, and it is what carries `INK_SELF` -- whose value is
    `INK`'s, so no hex search can see it. Running all seven by name rather than
    only the one that needs it means the two halves agree: a hex the value check
    catches is also a name this catches, and neither is load-bearing alone.

    The grep is over the whole file, prose included, and that is deliberate: the
    rail names no ink token anywhere today. If a future docstring must *name* an
    ink in order to refuse it, narrow this to the `code_strings` treatment this
    module already builds -- do not weaken the grep.
    """
    assert f"theme.{name}" not in source, f"the rail names {name}"


def test_ink_self_cannot_be_excluded_by_rail_value(probe):
    """Why AC 2's value check has six entries and not seven.

    `INK_SELF` and `INK` are one pigment -- "your own words -- plain ink, no
    verdict" -- and the rail sets every session title in `INK`. So a seventh
    entry in `VERDICT_INKS_BY_VALUE` would fail on a *correct* rail: right about
    the bytes, wrong about the claim. STORY-018's module docstring predicted
    this and asked for exactly the split above; `tests/test_render_invariants.py`
    records the identical exception for the console.

    Asserted rather than commented, so that a future attempt to "complete" the
    tuple finds the reason before writing it, and so that the day the two inks
    diverge in `theme.py` this fails and points at the tuple that can then grow.

    **The split is now narrower than it was.** `theme.py`'s second palette moved
    every token behind a custom property, so a component renders
    `var(--hx-ink-self)` or `var(--hx-ink)` -- two distinguishable strings for the
    one pigment. The rendered check the seventh entry could never have is
    therefore possible, and is made below; what stays impossible is a check by
    *value*, which is what this test's name and its six/seven split are about.
    The identity itself now lives in `tests/test_contrast.py`, against the
    palettes, because `theme.INK_SELF == theme.INK` is no longer a statement
    about pigment.
    """
    for palette_name, palette in (("light", theme.LIGHT), ("dark", theme.DARK)):
        assert palette["INK_SELF"] == palette["INK"], palette_name
    assert theme.INK.upper() in {value.upper() for value in probe["colours"]}, (
        "the rail no longer paints INK; the six/seven split may now be wrong"
    )
    assert theme.INK_SELF.upper() not in {
        value.upper() for value in probe["colours"]
    }, "INK_SELF is the transcript's ink for a reader's own words; the rail has none"


def test_the_only_radius_in_the_rail_is_the_theme_radius(probe):
    """AC 3. Section 6.1 refuses "rounded pill rows", and the story names the
    pill as "the drift's most likely first step".

    `theme.RADIUS` by name, never as its value: the assertion is that the rail
    renders *one* radius and that it is the theme's, not that it renders 3px.

    Supersedes the radius half of STORY-018's
    `test_the_rail_renders_only_ground_tokens_and_one_radius`, which made this
    claim and the ground-token claim in one function.
    """
    assert probe["errors"] == [], probe["errors"]
    assert probe["radii"] == [theme.RADIUS], probe["radii"]


def test_the_radius_detector_still_matches_the_compiled_form(probe):
    """The radius guard, kept armed.

    `test_the_only_radius_in_the_rail_is_the_theme_radius` compares a list, and
    an empty list is not equal to `[theme.RADIUS]` -- so a detector that stopped
    matching would fail loudly there too. This states the same thing from the
    other side and names the cause: if Reflex changes how it compiles inline
    styles, the JS-form count goes to zero and this says so directly instead of
    leaving the reader to guess why the radius list emptied.
    """
    assert probe["errors"] == [], probe["errors"]
    counts = probe["radius_form_counts"]
    assert counts["js"] > 0, (
        "the compiled inline-style form matched nothing; the radius detector "
        f"is no longer looking at what Reflex emits: {counts}"
    )


def test_every_colour_in_the_rail_is_a_ground_token(probe):
    """AC 4. Every colour the rail actually paints resolves to one of PRD-008
    Section 6.1's eight grounds.

    A subset, not an equality: `theme.CARD` is legitimately unrendered -- the
    rail's ground is `PAPER` against the transcript's `CARD` -- and demanding
    every ground appear would fail on a correct rail.

    This is the guard that catches a drift no per-token check can enumerate: an
    accent nobody has named yet, or a colour a Radix component supplies at
    compile time. The failure message names the offending colour rather than
    dumping the set.

    Supersedes the ground-token half of STORY-018's
    `test_the_rail_renders_only_ground_tokens_and_one_radius`.
    """
    assert probe["errors"] == [], probe["errors"]
    found = {value.upper() for value in probe["colours"]}
    assert found <= _ground_values(), sorted(found - _ground_values())


def test_the_tint_guard_detects_a_tint():
    """The guard, watched failing -- and kept watched.

    STORY-020's fifth acceptance criterion is a claim about what *fails*: a
    `TINT_HELD` background on the active row must turn this file red. That was
    done during implementation and the run is recorded in this story's report,
    but a violation that has been removed proves nothing about tomorrow. So the
    comparison the two guards above make is run here over a synthetic sample
    containing the tint, which keeps the claim true without a shipped module
    carrying a fill.

    `tests/test_admin_palette.py` puts it best: "A guard nobody has watched fail
    is a guard nobody knows is armed."
    """
    drifted = sorted({theme.PAPER, theme.INK, theme.TINT_HELD})
    found = {value.upper() for value in drifted}

    # AC 1's comparison, over the drifted sample.
    assert theme.TINT_HELD.upper() in found

    # AC 4's comparison, over the same sample: a tint is not a ground, so the
    # two guards catch this edit together rather than one covering for the other.
    assert not found <= _ground_values()
    assert sorted(found - _ground_values()) == [theme.TINT_HELD.upper()]

    # And the clean sample stays clean, so the detector is not simply always red.
    clean = {value.upper() for value in (theme.PAPER, theme.INK, theme.MUTE)}
    assert clean <= _ground_values()


# --------------------------------------------------------------------------
# The source assertions
# --------------------------------------------------------------------------


def test_no_colour_is_written_as_a_literal_hex(source):
    """`theme.py` is the only place a colour is spelled."""
    assert re.findall(r"#[0-9a-fA-F]{6}\b", source) == []


def test_no_rail_token_is_written_as_its_value(source):
    """STORY-017's single-file rule, and the defect it exists to prevent: "a
    literal `"0.75rem"` inside session_rail.py is a defect this story exists to
    prevent"."""
    for name, value in RAIL_TOKEN_VALUES.items():
        assert f'"{value}"' not in source, f"{name} written as {value!r}"
        assert f"theme.{name}" in source, f"{name} never used"


def test_every_user_facing_string_resolves_from_copy(source, code_strings):
    """AC 12, and PRD-004 STORY-007's rule carried into PRD Section 4: no literal
    user-facing text in a component.

    Both directions: the constant is referenced as `copy.NAME`, and its *value*
    appears nowhere in the source -- a pasted string beside the reference would
    satisfy the first half alone.
    """
    for name in COPY_NAMES:
        assert f"copy.{name}" in source, f"{name} is never rendered"
        value = getattr(copy, name)
        assert value not in code_strings, f"{name}'s text is inlined as a literal"


def test_the_type_roles_are_the_ones_the_prd_fixes(source):
    """PRD Section 6.1, verbatim: "`FONT_DISPLAY` at `TEXT_DATA` for session
    titles, `FONT_DATA` at `TEXT_TAG` for the activity time."

    Asserted as adjacency inside the two row helpers rather than as mere presence
    in the file, because the claim is about which face carries which role.
    """
    title_block = source.split("row.title,", 1)[1].split(")", 1)[0]
    assert "theme.FONT_DISPLAY" in title_block
    assert "theme.TEXT_DATA" in title_block

    activity_block = source.split("row.activity_info,", 1)[1].split(")", 1)[0]
    assert "theme.FONT_DATA" in activity_block
    assert "theme.TEXT_TAG" in activity_block


def test_the_three_states_are_three_distinct_renderings(source):
    """PRD Section 4 lists three: "no sessions yet, sessions listed, and a read
    that failed", and AC 6 forbids the last from rendering as the first."""
    assert "copy.SESSION_RAIL_EMPTY_TITLE" in source
    assert "copy.SESSION_RAIL_FAULT_TITLE" in source
    assert "rx.foreach(ChatState.sessions" in source


def test_the_fault_state_is_checked_before_the_empty_state(source):
    """The branch order in `_body`, which is the whole of AC 6.

    A failed read leaves `sessions == []` *and* `sessions_error != ""`, so both
    conditions are true at once and only the order distinguishes them. Reversed,
    the rail tells someone with thirty chats that they have none -- silently,
    which is why it is asserted rather than reviewed.
    """
    body = source.split("def _body()", 1)[1]
    fault_at = body.index("ChatState.sessions_error")
    list_at = body.index("rx.foreach")
    assert fault_at < list_at, "_body renders the list before checking the fault"


def test_the_fault_state_does_not_render_the_storage_layers_words(source):
    """`copy.py`'s rule for this surface: the rail "renders these two constants
    and treats `sessions_error` as the trigger, not as the text", because
    `sessions_error` holds `str(exc)` from the store describing itself."""
    fault = source.split("def _fault_state()", 1)[1].split("def _body()", 1)[0]
    body = fault.split('"""', 2)[2]
    assert "ChatState.sessions_error" not in body


def test_the_row_affordances_are_buttons_and_are_not_hover_gated(source):
    """AC 8: "reachable by keyboard with visible focus and are not hover-only".

    A real `<button>` is the whole keyboard answer, and the kebab-menu refusal is
    the second half: no `display` may be gated on `_hover`, which is how an
    always-present control becomes a hover-revealed one.
    """
    assert "rx.el.button" in source
    for match in re.finditer(r"_hover=\{([^}]*)\}", source):
        assert "display" not in match.group(1), "an affordance is hover-gated"
        assert "visibility" not in match.group(1)


def test_no_row_weight_varies_with_the_active_session(source):
    """AC 2's "and by nothing else": bold is one of the four named refusals, and
    it is the one that arrives looking like an improvement. The title's weight is
    a constant, so it cannot be conditioned on `_is_active`."""
    title_block = source.split("row.title,", 1)[1].split(")", 1)[0]
    weights = re.findall(r'font_weight="(\d+)"', title_block)
    assert weights == ["500"], weights
    assert "_is_active" not in title_block


def test_the_rail_uses_no_dialog_component(source):
    """`delete_session`'s docstring reserved the confirmation for this module:
    "`rx.window_alert` and `rx.alert_dialog` both exist in the pinned Reflex, and
    neither is used". A modal would arrive with an overlay, a radius and a red
    destructive button -- three of PRD Risk 6's drifts in one component.

    Over the AST, because this module names both in prose in order to refuse
    them.
    """
    called = {
        node.func.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "alert_dialog" not in called
    assert "window_alert" not in called
    assert "dialog" not in called


# --------------------------------------------------------------------------
# AC 10 -- the rail is absent when this deployment keeps no history
#
# These go through the subprocess probe like everything else above: the
# component imports `from chat_ui import copy`, which only resolves with
# `chat_ui/` on PYTHONPATH. The flag is supplied through the environment rather
# than monkeypatched, because it has to be set before `app.config` is imported
# in that process -- which is also the honest shape of the thing, since it is a
# deployment setting and not a per-request one.
# --------------------------------------------------------------------------


_FLAG_SCRIPT = r"""
import json, sys
result = {}
try:
    from chat_ui import copy, theme
    from chat_ui.components.session_rail import session_rail
except Exception as exc:
    print(json.dumps({"error": "{}: {}".format(type(exc).__name__, exc)}))
    sys.exit(0)

rendered = str(session_rail())
result["new_chat"] = copy.SESSION_NEW_CHAT_LABEL in rendered
result["empty_title"] = copy.SESSION_RAIL_EMPTY_TITLE in rendered
result["empty_body"] = copy.SESSION_RAIL_EMPTY_BODY in rendered
result["rail_width"] = theme.SESSION_RAIL_W in rendered
result["spine"] = theme.SPINE in rendered
result["length"] = len(rendered)
print(json.dumps(result))
"""


def _render_with_flag(value: str) -> dict:
    env = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join(_PYTHONPATH),
        CHAT_HISTORY_ENABLED=value,
        DATABASE_URL=os.environ.get("DATABASE_URL", "http://127.0.0.1:8080"),
        OPENROUTER_API_KEY=os.environ.get("OPENROUTER_API_KEY", "test-key"),
        ADMIN_TOKEN=os.environ.get("ADMIN_TOKEN", "test-token"),
    )
    proc = subprocess.run(
        [sys.executable, "-c", _FLAG_SCRIPT],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, f"probe crashed:\n{proc.stdout}\n{proc.stderr}"
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert "error" not in out, out["error"]
    return out


def test_the_rail_is_absent_when_history_is_off():
    """AC 10, verbatim: "the rail is **absent** -- not empty, not disabled."

    `rx.fragment()` renders no node, so there is nothing for STORY-019's flex
    row to lay out and no width to reserve. A hidden box would still be in the
    DOM for a screen reader to find, which is "disabled", not "absent".
    """
    off = _render_with_flag("false")

    assert off["new_chat"] is False
    assert off["rail_width"] is False
    assert off["spine"] is False


def test_the_absent_rail_does_not_render_the_invitation():
    """The specific falsehood this branch exists to remove.

    With the flag off the service returns `[]` for everyone, which is byte-for-
    byte the "no sessions yet" answer -- so a rail that did not ask the question
    rendered `SESSION_RAIL_EMPTY_TITLE` at a user whose chats exist and are
    simply not being read, and `SESSION_RAIL_EMPTY_BODY` promised the next
    prompt would appear in a rail nothing is ever written to.

    Both were observed in a browser against a database holding four sessions,
    which is why the invitation is asserted absent in its own right rather than
    left implied by the assertions above.
    """
    off = _render_with_flag("false")

    assert off["empty_title"] is False
    assert off["empty_body"] is False


def test_the_rail_is_present_when_history_is_on():
    """The control. Every assertion above is satisfied by a function that
    returns nothing to anybody, so the flag is driven the other way too and the
    same markers must come back."""
    on = _render_with_flag("true")

    assert on["new_chat"] is True
    assert on["rail_width"] is True
    assert on["length"] > _render_with_flag("false")["length"]


def test_the_flag_is_named_once_and_only_at_the_surface(source):
    """The exemption is one question asked in one place, not a licence.

    `tests/test_chat_sessions.py`'s allowlist admits this file; this pins what it
    was admitted to do. A second reference -- per row, or inside a helper --
    would be the flag leaking into the component's logic rather than gating its
    existence, and the allowlist entry would then be sheltering something it was
    not granted for.
    """
    tree = ast.parse(source)
    named = [
        node
        for node in ast.walk(tree)
        if (isinstance(node, ast.Attribute) and node.attr == "CHAT_HISTORY_ENABLED")
        or (isinstance(node, ast.Name) and node.id == "CHAT_HISTORY_ENABLED")
    ]
    assert len(named) == 1, f"the flag is named {len(named)} times"

    entry = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "session_rail"
    )
    assert any(
        isinstance(n, ast.Attribute) and n.attr == "CHAT_HISTORY_ENABLED"
        for n in ast.walk(entry)
    ), "the flag is not read in session_rail() itself"
