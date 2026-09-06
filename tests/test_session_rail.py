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

**The design guards are STORY-020's**, not this file's: no `TINT_*`, no verdict
ink, no radius beyond `theme.RADIUS`, every colour a ground token, and the
deliberate-violation run that proves the guard bites. That story extends this
file rather than replacing it. What is here is the subset STORY-018 can assert
about its own component without pre-empting them.

**A note for STORY-020.** `theme.INK_SELF == theme.INK` (both `#14181C`), so a
verdict-ink guard that tests `INK_SELF in rendered` will fire on every rail row's
title colour and be *right* about the bytes and wrong about the claim. It is the
same shape of exception `tests/test_admin_palette.py` records for the
`:focus-visible` ring, and it needs the same explicit handling: compare against
the six inks that are not `INK`, or compare by token name rather than by value.
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
result["hexes"] = sorted(set(re.findall(r"#[0-9a-fA-F]{6}\b", rendered)))
result["radii"] = sorted(set(re.findall(r'\["borderRadius"\] : "([^"]+)"', rendered)))

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


def test_the_rail_renders_only_ground_tokens_and_one_radius(probe):
    """The subset of PRD Risk 6 this story can assert about its own component.

    STORY-020 owns the full guard, including the deliberate violation. This is
    the floor: no colour reaches the screen that is not one of PRD Section 6.1's
    grounds, and the only radius is `theme.RADIUS` -- the pill being the drift's
    most likely first step.
    """
    grounds = {
        theme.PAPER,
        theme.CARD,
        theme.INK,
        theme.MUTE,
        theme.RULE,
        theme.RULE_SOFT,
        theme.HOVER,
        theme.SPINE,
    }
    assert set(probe["hexes"]) <= grounds, f"non-ground colour: {probe['hexes']}"
    assert probe["radii"] == [theme.RADIUS], probe["radii"]


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
