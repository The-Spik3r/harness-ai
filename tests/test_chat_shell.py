"""The chat shell's layout: the rail beside the transcript, and the collapse.

Two halves, following `tests/test_session_rail.py` and `tests/test_admin_shell.py`,
because two kinds of claim need two different tools.

**The build probe** runs in a subprocess with `PYTHONPATH` set to `chat_ui/`,
which is how Reflex itself imports the app (`chat_ui.components...`, not
`chat_ui.chat_ui.components...`). Doing it in-process would put the inner
package on `sys.path` and break every other test module, which reaches the same
files by their repo-root path. It renders the real `index()` — the page, not a
component — so the assertions below are about what the browser is actually sent.

**The source assertions** read `shell.py` and `chat_ui.py` as text. They cover
what a build cannot: that the breakpoint is named rather than typed, that no
colour is a literal hex, and that this module adds no stylesheet of its own.

**What "the rendered output" is here.** A Reflex page compiles to a *template*
that references state vars, not to HTML with values in it — the point
`tests/test_render_invariants.py` makes at length. Every claim below is
therefore about the template: the CSS objects Reflex emits, the media queries it
wraps them in, and the order the elements appear in. That is exactly the right
altitude for a layout, which is a claim about structure and not about data.

**Why the media queries are asserted as strings.** `rx.breakpoints` compiles to
emotion keys of the form `@media screen and (min-width: X)` — mobile-first
`min-width`, verified against the pinned Reflex (`reflex_base/style.py`'s
`media_query`). So the *narrow* arm is the one keyed at `0px` and the *wide* arm
is the one keyed at `theme.SESSION_RAIL_COLLAPSE_W`. Getting that backwards is
the single easiest way to ship this story inverted — a rail that collapses on
big screens and crowds small ones — and it would look correct in a diff, so it
is pinned here rather than reviewed.

**The design guards are STORY-020's**, not this file's: no `TINT_*`, no verdict
ink, no radius beyond `theme.RADIUS`. What is here is the layout subset
STORY-019 can assert about its own composition without pre-empting them.
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

SHELL_SOURCE_PATH = REPO_ROOT / "chat_ui" / "chat_ui" / "components" / "shell.py"
APP_SOURCE_PATH = REPO_ROOT / "chat_ui" / "chat_ui" / "chat_ui.py"

# The two media-query keys the collapse is built from. Derived from the token,
# never typed: a test that hard-coded "60rem" would keep passing after someone
# moved the breakpoint and stop describing the app.
NARROW_MQ = "@media screen and (min-width: 0px)"
WIDE_MQ = f"@media screen and (min-width: {theme.SESSION_RAIL_COLLAPSE_W})"

# Every transition that was on this surface before PRD-008 and is not this
# story's. All three are colour-only hover feedback on a `<button>` from
# PRD-004 -- the composer's Send, the session gate's submit, and the bubbles'
# "Edit and resend" -- and not one of them moves geometry or runs unprompted.
# Named exhaustively so the count below stays real: a fourth arriving from
# anywhere fails this file rather than being absorbed by a loosened grep.
PRE_EXISTING_TRANSITIONS = (
    "background-color 120ms ease",
    "background-color 120ms ease, border-color 120ms ease",
    "background-color 120ms ease, opacity 120ms ease",
)


def own_css(rendered: str) -> str:
    """The first `css:({...})` object in a rendered component — its *own* style.

    Every assertion about "this element declares X" needs this. `str(component)`
    is the whole subtree, so a naive substring search for `["transition"]` on
    `shell_body()` finds the hover transition on an "Edit and resend" button
    nine levels down and reports it as a property of the row. That is not a
    stricter test, it is a different and wrong one: it cannot distinguish the
    layout's own motion from motion inside the content the layout holds, which
    is the exact distinction this story's motion criterion turns on.

    Brace-matched rather than regex'd, because these objects nest — media-query
    arms and `&:hover` blocks are themselves objects.
    """
    start = rendered.index("css:({")
    depth = 0
    for i in range(start + 5, len(rendered)):
        if rendered[i] == "{":
            depth += 1
        elif rendered[i] == "}":
            depth -= 1
            if depth == 0:
                return rendered[start : i + 1]
    raise AssertionError("unbalanced css object")


@pytest.fixture(scope="module")
def source() -> str:
    return SHELL_SOURCE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def app_source() -> str:
    return APP_SOURCE_PATH.read_text(encoding="utf-8")


def _docstring_nodes(tree: ast.AST) -> set:
    """Every `ast.Constant` that is a docstring, by identity.

    `shell.py` argues its refusals in prose — it names `display: none` and
    `opacity` in order to explain why neither is used — so the code assertions
    below have to exclude the prose rather than the prose be rewritten to dodge
    a grep. `tests/test_session_rail.py` records the same reasoning for the same
    reason.
    """
    found = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
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
    """Every string literal `shell.py`'s *code* contains, docstrings excluded."""
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
# The build probe — the real page, rendered
# --------------------------------------------------------------------------


_CHECK_SCRIPT = r"""
import json, re, sys

result = {"errors": []}
try:
    from chat_ui import copy, theme
    from chat_ui.components import shell as mod
    from chat_ui.components.chat import chat_input
except Exception as exc:
    print(json.dumps({"errors": ["import: {}: {}".format(type(exc).__name__, exc)]}))
    sys.exit(0)

for name in ("header", "rail_disclosure", "rail_slot", "transcript_column",
             "shell_body", "empty_state", "login_gate"):
    try:
        getattr(mod, name)()
    except Exception as exc:
        result["errors"].append("{}: {}: {}".format(name, type(exc).__name__, exc))

# The page itself, built the way index() builds it. Imported from the app module
# so that what is asserted is the composition that ships, not a restatement of
# it in this test -- a restated layout would agree with itself forever.
try:
    from chat_ui.chat_ui import index
    page = str(index())
except Exception as exc:
    print(json.dumps({"errors": ["index: {}: {}".format(type(exc).__name__, exc)]}))
    sys.exit(0)

result["page_len"] = len(page)
result["page"] = page

result["slot"] = str(mod.rail_slot())
result["body"] = str(mod.shell_body())
result["column"] = str(mod.transcript_column())
result["header"] = str(mod.header())
result["disclosure"] = str(mod.rail_disclosure())
result["gate"] = str(mod.login_gate())
result["composer"] = str(chat_input())

# Every distinct transition declared anywhere on the signed-in page.
result["page_transitions"] = sorted(set(
    re.findall(r'\["transition"\] : "([^"]+)"', page)
))
result["shell_transitions"] = sorted(set(
    re.findall(r'\["transition"\] : "([^"]+)"', result["body"])
))
result["column_max"] = theme.COLUMN_MAX in result["column"]
result["rail_present"] = "hx-scroll" in result["slot"]

print(json.dumps(result))
"""


@pytest.fixture(scope="module")
def probe() -> dict:
    env = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join(_PYTHONPATH),
        DATABASE_URL=os.environ.get("DATABASE_URL", "http://127.0.0.1:8080"),
        OPENROUTER_API_KEY=os.environ.get("OPENROUTER_API_KEY", "test-key"),
        ADMIN_TOKEN=os.environ.get("ADMIN_TOKEN", "test-token"),
    )
    proc = subprocess.run(
        [sys.executable, "-c", _CHECK_SCRIPT],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, f"probe crashed:\n{proc.stdout}\n{proc.stderr}"
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out["errors"] == [], out["errors"]
    return out


def test_every_factory_builds(probe):
    """The module imports the way Reflex imports it, and the page compiles.

    A broken import or a component that raises fails here rather than at
    `reflex run` — the failure `tests/test_chat_components_import.py` was
    written after a merge had already shipped once.
    """
    assert probe["page_len"] > 0


# --- AC 1 + AC 2: the three bands, and the masthead across the top --------


def test_the_page_is_masthead_then_row_then_composer(probe):
    """AC 1. The order is asserted by position in the compiled page.

    Not "all four are present somewhere": a rail rendered *below* the composer
    would satisfy that and would be the wrong page. Position is the claim.

    The composer is located by its input's `id`, not by `COMPOSER_SEND_LABEL`.
    That label is "Send", which is a substring of the rail's own empty-state
    body ("**Send** a prompt below and this conversation appears here"), so a
    search for it finds the rail first and reports the composer as sitting
    above itself. An id is unique; a four-letter label is not.
    """
    page = probe["page"]
    header_at = page.index(copy.SHELL_HEADER_TITLE)
    rail_at = page.index(copy.SESSION_NEW_CHAT_LABEL)
    composer_at = page.index('id:"chat_input"')
    assert header_at < rail_at < composer_at, (header_at, rail_at, composer_at)


def test_the_transcript_sits_beside_the_rail_in_one_row(probe):
    """AC 1's "side by side". The row holds the two columns, and not the
    masthead — which is the band above it and must stay full width."""
    body = probe["body"]
    assert "hx-scroll" in body, "the rail is not in the row"
    assert theme.COLUMN_MAX in body, "the transcript is not in the row"
    assert copy.SHELL_HEADER_TITLE not in body, "the masthead is inside the row"


def test_the_composer_is_in_the_transcripts_column(probe):
    """The story's one departure from PRD Section 6.1's wireframe, pinned so it
    stays a decision rather than becoming an accident.

    The wireframe draws the composer spanning the full width beneath both
    columns. Built that way and measured on screen, it centred its `COLUMN_MAX`
    on the *page* while the transcript centred on its *column* — 120px of
    visible misalignment, exactly half the rail. Inside the column it aligns by
    construction, and it says the true thing about itself: it types into this
    transcript, not into the page.
    """
    assert 'id:"chat_input"' in probe["column"], "the composer left the column"
    assert 'id:"chat_input"' in probe["body"]
    # And it is still the last thing in the column, not floating above the
    # transcript.
    column = probe["column"]
    assert column.index(theme.COLUMN_MAX) < column.index('id:"chat_input"')


def test_the_masthead_still_spans_the_full_width(probe):
    """AC 2, first half. PRD Section 6.1: the header "keeps spanning the full
    width"."""
    assert '["width"] : "100%"' in probe["header"]


def test_the_masthead_still_carries_the_session_facts(probe):
    """AC 2, second half. PRD Section 6.1: the masthead "stays the one place the
    session's facts (who is sending, which model) live"."""
    header = probe["header"]
    assert 'id:"model-selector"' in header, "the model selector left the masthead"
    assert "user_id" in header, "the signed-in user left the masthead"
    assert copy.SHELL_USER_LABEL in header
    assert copy.SHELL_LOGOUT_LABEL in header


def test_the_masthead_is_not_inside_the_row(probe):
    """AC 2, structurally. A masthead that became a column of the row would
    still render "at the top" of that column and would stop being full width."""
    assert copy.SHELL_HEADER_TITLE not in probe["body"]


# --- AC 3: the collapse, and the control that undoes it -------------------


def test_the_slot_collapses_below_the_breakpoint_and_not_above_it(probe):
    """AC 3, and the assertion that catches an inverted breakpoint.

    `rx.breakpoints` is mobile-first `min-width`, so the `0px` arm is the narrow
    one. The narrow arm must consult `rail_expanded`; the wide arm must not —
    above the breakpoint there is room for both columns and the var decides
    nothing.
    """
    slot = probe["slot"]
    narrow = slot[slot.index(NARROW_MQ) : slot.index(WIDE_MQ)]
    wide = slot[slot.index(WIDE_MQ) :]

    assert "rail_expanded" in narrow, "the narrow arm ignores the disclosure"
    assert '"0"' in narrow, "the narrow arm does not collapse"
    assert theme.SESSION_RAIL_W in narrow, "the narrow arm cannot reopen"

    assert "rail_expanded" not in wide, "the wide arm is gated on the disclosure"
    assert theme.SESSION_RAIL_W in wide, "the wide arm does not hold the rail open"


def test_the_disclosure_exists_and_only_below_the_breakpoint(probe):
    """AC 3's "a control to bring the rail back", and its restraint.

    Above the breakpoint the rail is always there, so the control is `display:
    none` — an inert word in the masthead is the accessory the skill's mirror
    pass removes.
    """
    disclosure = probe["disclosure"]
    assert copy.SESSION_RAIL_SHOW_LABEL in disclosure
    assert "toggle_rail" in disclosure, "the control is wired to nothing"
    narrow = disclosure[disclosure.index(NARROW_MQ) : disclosure.index(WIDE_MQ)]
    wide = disclosure[disclosure.index(WIDE_MQ) :]
    assert '"none"' not in narrow, "the control is hidden where it is needed"
    assert '"none"' in wide, "the control is shown where the rail cannot collapse"


def test_the_disclosure_is_in_the_masthead(probe):
    """Where it is decides the tab order, so it is asserted rather than left to
    the eye. AC 8 depends on this being true."""
    assert copy.SESSION_RAIL_SHOW_LABEL in probe["header"]


def test_the_disclosure_says_which_state_it_is_in(probe):
    """The label does not flip, so `aria-expanded` is the only thing that tells
    a screen reader whether the rail is open. Without it the control is a word
    that does something invisible."""
    disclosure = probe["disclosure"]
    assert '"aria-expanded"' in disclosure
    assert "rail_expanded" in disclosure
    assert '"aria-controls"' in disclosure


def test_the_disclosure_carries_no_icon_or_glyph(probe, code_strings):
    """PRD Section 8 admits no icon set, and a "☰" or "+" would be a
    user-facing string with no home in `copy.py`."""
    for glyph in ("☰", "+", "×", "‹", "›", "▸", "▾"):
        assert glyph not in code_strings, glyph


# --- AC 4 + AC 5: one transition, and nothing else moves ------------------


def test_the_collapse_is_the_only_transition_the_layout_declares(probe):
    """AC 4, scoped honestly.

    Read literally, "the only transition on the surface" is already false and
    was before this story: the composer's Send and the gate's submit each carry
    a colour-only hover transition from PRD-004. Those two are named in
    `PRE_EXISTING_TRANSITIONS` and excluded **by name**, so this stays a real
    count — a third transition arriving anywhere on the page fails here — rather
    than a grep loosened until it passed. The finding is recorded in the story's
    report rather than silently reinterpreted.

    Within the layout itself the claim is exact and is what this story owns:
    of the four elements STORY-019 adds — the row, the rail's slot, the
    transcript column and the disclosure — exactly one declares a transition,
    and it is the collapse.
    """
    own = {
        name: own_css(probe[name])
        for name in ("body", "slot", "column", "disclosure")
    }
    movers = [name for name, css in own.items() if '["transition"]' in css]
    assert movers == ["slot"], movers

    only = re.search(r'\["transition"\] : "([^"]+)"', own["slot"]).group(1)
    assert only.startswith("max-width "), only

    unexpected = [
        t
        for t in probe["page_transitions"]
        if t not in PRE_EXISTING_TRANSITIONS and t != only
    ]
    assert not unexpected, unexpected


def test_the_collapse_is_disabled_under_reduced_motion():
    """AC 4's second half.

    `theme.GLOBAL_CSS` already neutralises every transition on the page, so this
    story adds no CSS. That is the thing worth pinning: the rule is load-bearing
    for a story that did not write it, and deleting it would silently re-enable
    the one animation the PRD allows only conditionally.
    """
    css = theme.GLOBAL_CSS
    assert "@media (prefers-reduced-motion: reduce)" in css
    block = css[css.index("@media (prefers-reduced-motion: reduce)") :]
    assert "transition-duration: 0.01ms !important" in block


def test_switching_sessions_animates_nothing(probe):
    """AC 5. PRD Section 6.1: the skill's warning about extra animation "applies
    hardest to the operation a user will perform thirty times a day".

    The switch is `select_session` on a rail row. The column that swaps beneath
    it declares no motion of its own, and neither does the rail the click
    landed in — so nothing this story built moves when a session changes.

    **What this test does not cover, and cannot.** Every bubble carries
    PRD-004's `.hx-entry` class, whose 200ms rise runs when a node *mounts*. A
    switch replaces `messages`, so whether the restored transcript animates
    depends on React's reconciliation of an index-keyed `.map()` — reused nodes
    do not re-run a CSS animation, newly-mounted ones do. That is a claim about
    a browser, not about a template, so it is settled by watching a real switch
    during E2E and recorded in the story's report — not asserted here, where it
    could only be asserted as something weaker that looked like proof.
    """
    assert '["transition"]' not in own_css(probe["column"])
    assert '["animation"]' not in own_css(probe["column"])
    assert '["transition"]' not in own_css(probe["body"])
    assert "hx-entry" not in probe["slot"]
    assert "hx-pulse" not in probe["slot"]


# --- AC 6: the gate is untouched ------------------------------------------


def test_the_gate_renders_no_rail(probe):
    """AC 6. The rail lives inside `index()`'s authenticated arm only, so an
    unauthenticated visitor renders what they rendered before this story."""
    gate = probe["gate"]
    assert copy.SESSION_NEW_CHAT_LABEL not in gate
    assert copy.SESSION_RAIL_SHOW_LABEL not in gate
    assert "hx-scroll" not in gate
    assert copy.LOGIN_SUBMIT_LABEL in gate, "the gate stopped being the gate"


def test_the_gate_is_still_the_other_arm_of_the_same_cond(app_source):
    """AC 6, structurally: the gate stays where it was.

    The story is explicit — "Keep the `rx.cond` on `user_id` exactly where it
    is — it is the gate." A rail mounted outside that arm would read the session
    list for a visitor who has not signed in.
    """
    tree = ast.parse(app_source)
    index_fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "index"
    )
    conds = [
        node
        for node in ast.walk(index_fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "cond"
    ]
    assert len(conds) == 1, "index() no longer has exactly one gate"
    gate = conds[0]
    assert "user_id" in ast.unparse(gate.args[0])
    assert "login_gate" in ast.unparse(gate.args[2])
    assert "shell_body" in ast.unparse(gate.args[1])


# --- AC 7: the reading measure survives the reclaimed width ---------------


def test_the_reading_measure_still_governs_the_transcript(probe):
    """AC 7. `COLUMN_MAX` reaches the column through `message_list()` and
    `empty_state()`, which each clamp and centre themselves."""
    assert probe["column_max"]


def test_the_transcript_column_adds_no_second_clamp(source):
    """AC 7's other half, and the skill's "nothing quietly does double duty".

    Two centring clamps on nested boxes is the cancelling-margins failure the
    frontend-design skill warns about: the outer one would win, the inner one
    would look redundant, and removing the wrong one would silently widen the
    measure.
    """
    tree = ast.parse(source)
    column = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "transcript_column"
    )
    body = ast.unparse(column).split('"""')[-1]
    assert "max_width" not in body, "the column clamps the measure a second time"


# --- AC 8: focus order, and a collapsed rail that leaves it ---------------


def test_the_collapsed_rail_leaves_the_tab_order(probe):
    """AC 8's hard half, and the reason `visibility` was chosen over `opacity`.

    `opacity: 0` would transition just as well and would leave every row button,
    Rename and Delete focusable inside a zero-width column — a reader tabbing
    through a collapsed rail would cross a dozen invisible controls with a
    visible focus ring landing on nothing. `visibility: hidden` is the only
    property that both transitions and removes the subtree from tab order.
    """
    slot = probe["slot"]
    assert '["visibility"]' in slot
    assert '"hidden"' in slot
    assert '["opacity"]' not in slot, "opacity would keep the rail focusable"
    assert '["display"] : "none"' not in slot, "display:none cannot transition"


def test_nothing_in_the_layout_cancels_the_focus_ring(source):
    """AC 8's "visible focus at every stop".

    `theme.GLOBAL_CSS` gives every focusable element a ring; a local `outline:
    none` would take it back on exactly the controls this story adds.
    `tests/test_admin_shell.py` makes the same check for the console.
    """
    for killer in ("outline", "box_shadow"):
        assert f'"{killer}": "none"' not in source, killer
    assert 'outline="none"' not in source


def test_the_document_order_is_the_focus_order(probe):
    """AC 8. No `tabindex` anywhere, so document order *is* the tab order — and
    document order is asserted by `test_the_page_is_masthead_then_row_then_composer`
    above. What is left to check is that nothing overrides it."""
    assert "tabIndex" not in probe["page"]
    assert "tabindex" not in probe["page"]


# --- AC 9: the rail scrolls in its own container --------------------------


def test_the_rail_scrolls_inside_itself(probe):
    """AC 9, first half. Thirty chats must not push the composer off screen."""
    slot = probe["slot"]
    assert '["overflowY"] : "auto"' in slot
    assert 'className:"hx-scroll"' in slot


def test_the_row_and_the_column_refuse_a_horizontal_scroll(probe):
    """AC 9, second half — and `minWidth: 0` is the whole of it.

    A flex item defaults to `min-width: auto` and refuses to shrink below its
    content, so one long unbroken token in a bubble would widen the transcript
    past the row and take the page sideways with it. This is the assertion that
    fails if someone "tidies up" that line.
    """
    assert '["minWidth"] : "0"' in probe["column"]
    assert '["overflow"] : "hidden"' in probe["body"]


def test_the_row_owns_the_leftover_height(probe):
    """AC 9's precondition. Without `flex: 1` and `minHeight: 0` the row grows to
    fit its tallest child instead of scrolling it, and the rail's own
    `height: 100%` has nothing definite to measure against."""
    body = probe["body"]
    assert '["flex"] : "1"' in body
    assert '["minHeight"] : "0"' in body


# --- The history flag: an absent rail reserves no column ------------------


_FLAG_SCRIPT = r"""
import json, sys
result = {}
try:
    from chat_ui import copy, theme
    from chat_ui.components.shell import rail_disclosure, rail_slot
except Exception as exc:
    print(json.dumps({"error": "{}: {}".format(type(exc).__name__, exc)}))
    sys.exit(0)

slot = str(rail_slot())
result["rail_present"] = "hx-scroll" in slot
result["new_chat"] = copy.SESSION_NEW_CHAT_LABEL in slot
result["slot"] = slot
result["length"] = len(slot)
result["disclosure"] = str(rail_disclosure())
result["disclosure_offers_the_control"] = copy.SESSION_RAIL_SHOW_LABEL in result["disclosure"]
print(json.dumps(result))
"""


def _slot_with_flag(value: str) -> dict:
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


def test_the_slot_reserves_no_column_when_history_is_off():
    """STORY-018's "absent, not empty", carried through the layout.

    `session_rail()` returns `rx.fragment()` with the flag off, so the slot
    wraps nothing — and a slot that declared a `width` would reserve fifteen
    rems of blank column for it anyway. It declares only a `max-width`, so an
    empty flex item is sized by its content and comes out at zero.

    Asking the flag in `shell.py` was not available: it may be named exactly
    once in the whole of `chat_ui/`, at the top of `session_rail()`
    (`tests/test_chat_sessions.py`'s allowlist, and
    `test_the_flag_is_named_once_and_only_at_the_surface`). So this is the
    assertion that keeps the layout honest without a second mention.
    """
    off = _slot_with_flag("false")
    assert off["rail_present"] is False
    assert off["new_chat"] is False
    assert '["width"]' not in own_css(off["slot"]), "the empty slot reserves a column"
    assert '["maxWidth"]' in own_css(off["slot"]), "the slot lost its cap"


def test_the_slot_holds_the_rail_when_history_is_on():
    """The positive control. Every assertion above is a negative, and negatives
    pass on an empty render — this is what stands between them and a
    tautology."""
    on = _slot_with_flag("true")
    assert on["rail_present"] is True
    assert on["new_chat"] is True
    # The slot itself still states no width either way -- the fifteen rems in
    # the rendered output are the *rail's* own, inside it.
    assert '["width"]' not in own_css(on["slot"])
    assert on["length"] > _slot_with_flag("false")["length"]


# --- Source assertions ----------------------------------------------------


def test_source_is_discoverable(source, app_source):
    assert source.strip(), SHELL_SOURCE_PATH
    assert app_source.strip(), APP_SOURCE_PATH


def test_no_colour_is_written_as_a_literal_hex(code_strings):
    """Every colour resolves from `theme.py` — the single-file rule."""
    offenders = [s for s in code_strings if re.fullmatch(r"#[0-9a-fA-F]{3,8}", s)]
    assert not offenders, offenders


def test_the_breakpoint_is_named_and_never_typed(code_strings):
    """STORY-017 declared `SESSION_RAIL_COLLAPSE_W` with its reasoning intact
    (`SESSION_RAIL_W + MEASURE` is 57rem). A literal here would let the token and
    the layout drift apart silently."""
    assert theme.SESSION_RAIL_COLLAPSE_W not in code_strings
    assert theme.SESSION_RAIL_W not in code_strings


def test_every_user_facing_string_resolves_from_copy(source, code_strings):
    """The one string this story puts on screen is `SESSION_RAIL_SHOW_LABEL`,
    and STORY-017 already declared it for this control."""
    assert "copy.SESSION_RAIL_SHOW_LABEL" in source
    assert copy.SESSION_RAIL_SHOW_LABEL not in code_strings


def test_the_shell_emits_no_stylesheet_of_its_own(source):
    """`index()` carries `theme.GLOBAL_CSS`; a second copy on one page is the
    mistake `session_rail.py` and PRD-006's admin components both record. This
    story's collapse rules are inline style props for the same reason — the
    skill's warning that generated CSS classes "cancel each other out".

    Asserted over the *code*, not the file text: this module's prose explains at
    length that `GLOBAL_CSS`'s reduced-motion rule is what disables the
    collapse, and a docstring that cannot name the thing it depends on is worth
    less than the test. `tests/test_session_rail.py` records the same reasoning.
    """
    tree = ast.parse(source)
    docs = _docstring_nodes(tree)
    referenced = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr in ("GLOBAL_CSS", "style")
        and id(node) not in docs
    ]
    assert referenced == [], [ast.unparse(n) for n in referenced]


def test_the_shell_never_names_the_history_flag(source):
    """The flag is asked once, in `session_rail()`. A second question here would
    be the layout branching on a deployment setting the PRD says no caller may
    branch on."""
    tree = ast.parse(source)
    named = [
        node
        for node in ast.walk(tree)
        if (isinstance(node, ast.Attribute) and node.attr == "CHAT_HISTORY_ENABLED")
        or (isinstance(node, ast.Name) and node.id == "CHAT_HISTORY_ENABLED")
    ]
    assert named == [], "shell.py names CHAT_HISTORY_ENABLED"


# --- AC 5: a restored bubble does not pretend to have just arrived ---------
#
# The half of AC 5 that a template alone cannot state, and the one that was
# actually broken. `.hx-entry` (PRD-004) runs on *mount*; a session switch
# replaces `messages`, so React mounts every bubble the previous transcript did
# not have and each of those animates. Measured in Chrome before the fix:
# switching a 2-message chat for a 5-message one fired exactly three
# `animationstart` events. `ChatMessage.restored` is what removes it, and these
# pin the mechanism at the level a test can reach.


def test_a_restored_bubble_carries_no_entry_animation():
    """PRD Section 6.1: "Switching sessions does not animate."

    `_to_chat_message` is the only thing that sets `restored`, and it is the
    only path a stored row takes to the screen — so this is the whole of the
    claim, stated where the conversion happens.
    """
    from app.db.models import StoredMessage
    from chat_ui.chat_ui.state import _to_chat_message

    restored = _to_chat_message(
        StoredMessage(session_id="s", kind="user", content="hello")
    )
    assert restored.restored is True


def test_a_live_bubble_still_arrives():
    """The other side, and the reason this is a discriminator rather than a
    deletion: PRD-004's "one orchestrated moment" is about *arrival*, and a
    turn that just happened is still an arrival. A default of False is what
    keeps every live send animating."""
    from chat_ui.chat_ui.models import ChatMessage

    assert ChatMessage(kind="user", content="hello").restored is False


def test_the_entry_class_is_decided_per_message_and_never_toggled():
    """The retrigger bug this design exists to avoid.

    A single "suppress animations" flag on `ChatState`, switched off after a
    restore, would start the animation on every already-mounted bubble the next
    time it flipped — turning one wrong animation into a whole transcript of
    them. So the class must be a function of the message and of nothing else:
    no `ChatState` var may appear in `_entry`'s class decision.
    """
    path = REPO_ROOT / "chat_ui" / "chat_ui" / "components" / "bubbles.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    entry = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_entry"
    )
    call = next(
        kw.value
        for node in ast.walk(entry)
        if isinstance(node, ast.Call)
        for kw in node.keywords
        if kw.arg == "class_name"
    )
    rendered = ast.unparse(call)
    assert "restored" in rendered, rendered
    assert "ChatState" not in rendered, "the entry animation reads shared state"


def test_every_entry_kind_passes_its_message_to_the_shared_geometry():
    """`_entry` grew a first parameter, and a renderer that forgot it would pass
    its rail as the message and animate on a Var that has no `restored`.

    Exhaustive over the file rather than over a list retyped here: a ninth
    renderer added later is covered without this test being edited.
    """
    path = REPO_ROOT / "chat_ui" / "chat_ui" / "components" / "bubbles.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_entry"
    ]
    assert calls, "no _entry call sites found"
    for call in calls:
        first = ast.unparse(call.args[0])
        assert first in ("message", "None"), first


def test_there_is_no_disclosure_when_there_is_no_rail():
    """A control for nothing, found on screen and removed.

    With `CHAT_HISTORY_ENABLED=false` the rail does not exist at any width, so
    below the breakpoint the masthead was offering **Chats** — a word that
    revealed a column of nothing. The disclosure now asks `session_rail()`
    whether it rendered, rather than asking the configuration, because
    `shell.py` may not name the flag and because "is there a rail to reveal" is
    the question this control actually has.
    """
    assert _slot_with_flag("false")["disclosure_offers_the_control"] is False
    assert _slot_with_flag("true")["disclosure_offers_the_control"] is True
