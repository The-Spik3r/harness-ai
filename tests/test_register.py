"""Smoke and invariant tests for the register.

Three halves, because three different kinds of claim need three different tools.

**The build probe** runs in a subprocess with `PYTHONPATH` set to `chat_ui/`,
which is how Reflex itself imports the app (`chat_ui.components...`, not
`chat_ui.chat_ui.components...`). Doing it in-process would put the inner
package on `sys.path` and break every other test module, which reaches the same
files by their repo-root path — the same reason `tests/test_admin_shell.py` and
`tests/test_chat_components_import.py` each take one.

**The source assertions** read the module as text. They cover the acceptance
criteria a build cannot: that no colour is written as a literal hex, that every
string resolves from `admin_copy`, and that the type roles are the way round
PRD-006 Section 6.1 inverts them for this surface — `FONT_DATA` dominant,
`FONT_BODY` on the scope line and nowhere else.

**The preview boundary** is PRD-006 Risk 2 checked from the two sides that are
checkable here. `to_audit_row` is the only constructor on the console's path and
it names every field it copies, so the first assertion is that neither preview
survives it. The second is that the component reads only fields that exist on
`AuditRow` — together they say a preview cannot reach the screen because it
never reaches the row and the row is all the register reads. The *live* render
check against a seeded database is STORY-018's AC 1; it needs a running page,
which is out of a unit test's reach.

**A note for STORY-018.** `tests/test_admin_palette.py` records that
`theme.GLOBAL_CSS` sets the global `:focus-visible` outline to a chat-only ink
and that a naive grep of rendered admin HTML will find it. That does not arise
in this file: `admin_page()` owns the stylesheet, so `str(register())` carries
no `GLOBAL_CSS`. A whole-page assertion will have to allow for it; a
component-level one does not.
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
from chat_ui.chat_ui.admin_formatting import to_audit_row  # noqa: E402
from chat_ui.chat_ui.admin_models import AuditRow  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTHONPATH = [str(REPO_ROOT / "chat_ui"), str(REPO_ROOT)]

REGISTER_SOURCE_PATH = (
    REPO_ROOT / "chat_ui" / "chat_ui" / "components" / "register.py"
)

# Every column PRD-006 Section 4 names, plus the two in-row marks and the four
# verdict words. Each must reach the screen through `admin_copy.`, and none may
# appear in the source as a literal.
COPY_NAMES = (
    "COLUMN_TIME",
    "COLUMN_USER",
    "COLUMN_VERDICT",
    "COLUMN_MODEL",
    "COLUMN_TOKENS",
    "COLUMN_PII",
    "COLUMN_DEVICE",
    "COLUMN_ID",
    "AUDIT_ID_PREFIX",
    "PII_INDICATOR_LABEL",
    "VERDICT_CLEARED_LABEL",
    "VERDICT_HELD_LABEL",
    "VERDICT_DENIED_LABEL",
    "VERDICT_FAULT_LABEL",
    # STORY-012's disclosure: the six field labels, the control in both its
    # directions, and the two PII presence words.
    "DETAIL_ERROR_LABEL",
    "DETAIL_PATTERN_LABEL",
    "DETAIL_PROMPT_HASH_LABEL",
    "DETAIL_DEVICE_LABEL",
    "DETAIL_PII_ENTITIES_LABEL",
    "DETAIL_PII_INPUT_LABEL",
    "DETAIL_PII_OUTPUT_LABEL",
    "DETAIL_TOGGLE_OPEN_LABEL",
    "DETAIL_TOGGLE_CLOSE_LABEL",
    "DETAIL_TOGGLE_OPEN_MARK",
    "DETAIL_TOGGLE_CLOSE_MARK",
    "DETAIL_PII_PRESENT_LABEL",
    "DETAIL_PII_ABSENT_LABEL",
)

# Every label the disclosure puts on screen, as the strings that must reach the
# rendered output. `DETAIL_TIMESTAMP_LABEL` is deliberately absent: the row's
# time cell already carries the absolute stamp, and repeating it below would be
# the second summary the disclosure is not (see register.py's docstring).
DETAIL_LABELS = (
    admin_copy.DETAIL_ERROR_LABEL,
    admin_copy.DETAIL_PATTERN_LABEL,
    admin_copy.DETAIL_PROMPT_HASH_LABEL,
    admin_copy.DETAIL_DEVICE_LABEL,
    admin_copy.DETAIL_PII_ENTITIES_LABEL,
    admin_copy.DETAIL_PII_INPUT_LABEL,
    admin_copy.DETAIL_PII_OUTPUT_LABEL,
)

# The five fields PRD-006 Section 10 moves onto the disclosure, as `AuditRow`
# field names. Each must be read by the component, or the disclosure is not
# showing what the story says it shows.
DETAIL_ROW_FIELDS = (
    "error_message",
    "suspicious_pattern",
    "prompt_hash",
    "device_full",
    "pii_entities",
    "pii_detected_input",
    "pii_detected_output",
)

# The eight column heads, as the strings that must appear in the output.
COLUMN_HEADS = (
    admin_copy.COLUMN_TIME,
    admin_copy.COLUMN_USER,
    admin_copy.COLUMN_VERDICT,
    admin_copy.COLUMN_MODEL,
    admin_copy.COLUMN_TOKENS,
    admin_copy.COLUMN_PII,
    admin_copy.COLUMN_DEVICE,
    admin_copy.COLUMN_ID,
)

VERDICT_LABELS = (
    admin_copy.VERDICT_CLEARED_LABEL,
    admin_copy.VERDICT_HELD_LABEL,
    admin_copy.VERDICT_DENIED_LABEL,
    admin_copy.VERDICT_FAULT_LABEL,
)

# The four verdict inks the register draws (PRD-006 Section 6.1's colour table).
VERDICT_INKS = {
    "INK_CLEAR": theme.INK_CLEAR,
    "INK_HELD": theme.INK_HELD,
    "INK_DENIED": theme.INK_DENIED,
    "INK_FAULT": theme.INK_FAULT,
}

# Everything the register is allowed to paint: the four inks plus the ground
# tokens. Computed from theme.py rather than hard-coded, so retuning a token
# retunes the assertion in the same edit.
ALLOWED_COLOURS = {value.upper() for value in VERDICT_INKS.values()} | {
    theme.PAPER.upper(),
    theme.CARD.upper(),
    theme.INK.upper(),
    theme.MUTE.upper(),
    theme.RULE.upper(),
    theme.RULE_SOFT.upper(),
    theme.SPINE.upper(),
    theme.HOVER.upper(),
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
    from chat_ui.components.register import (
        register,
        _column_head,
        _detail,
        _disclosure_toggle,
        _row,
        _row_line,
        _scope_line,
        _stamp_margin,
        _verdict_tag,
    )
except Exception as exc:
    print(json.dumps({"errors": ["import: {}: {}".format(type(exc).__name__, exc)]}))
    sys.exit(0)

# The separation, from the importing side: nothing the register pulls in may
# drag a chat component along with it.
result["chat_modules_loaded"] = [
    name
    for name in ("chat_ui.components.chat", "chat_ui.components.bubbles")
    if name in sys.modules
]

# Every factory builds. The per-row helpers are exercised through a real
# rx.foreach so they are handed the Var they get in production, not a mock.
broken = []
built = {}
factories = [
    ("register", lambda: register()),
    ("_column_head", lambda: _column_head()),
    ("_scope_line", lambda: _scope_line()),
    ("rows", lambda: rx.box(rx.foreach(AdminState.visible_rows, _row))),
    ("lines", lambda: rx.box(rx.foreach(AdminState.visible_rows, _row_line))),
    ("stamps", lambda: rx.box(rx.foreach(AdminState.visible_rows, _stamp_margin))),
    ("tags", lambda: rx.box(rx.foreach(AdminState.visible_rows, _verdict_tag))),
    ("detail", lambda: rx.box(rx.foreach(AdminState.visible_rows, _detail))),
    (
        "toggle",
        lambda: rx.box(rx.foreach(AdminState.visible_rows, _disclosure_toggle)),
    ),
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

result["rendered"] = built.get("register", "")
# The disclosure and its control, separately: `register()` compiles the rows
# through rx.foreach, so the detail is in there too — but a test that means to
# assert something about the disclosure should fail when the disclosure is what
# broke, not when the table is.
result["detail"] = built.get("detail", "")
result["toggle"] = built.get("toggle", "")
result["rows_rendered"] = built.get("rows", "")

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
            # register imports admin_state, which imports app.config.settings,
            # where ADMIN_TOKEN is a required field. Same defaults
            # tests/test_admin_shell.py sets.
            "ADMIN_TOKEN": os.environ.get("ADMIN_TOKEN", "test-token"),
            "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", "test-key"),
        },
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.fail(f"register probe crashed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def source() -> str:
    return REGISTER_SOURCE_PATH.read_text(encoding="utf-8")


# --- The build probe ------------------------------------------------------


def test_module_imports(probe):
    """Catches circular imports and names missing at module scope."""
    assert not probe["errors"], probe["errors"]


def test_every_factory_builds(probe):
    """The table, the head, the scope line, and the three per-row helpers."""
    assert not probe["errors"], probe["errors"]
    assert not probe["broken_factories"], probe["broken_factories"]


def test_register_loads_no_chat_component(probe):
    """PRD-006 Section 4's cross-surface separation, from the importing side.

    Stronger than a source grep: a chat component pulled in transitively by
    something the register imports would show up here and nowhere else.
    """
    assert not probe["errors"], probe["errors"]
    assert not probe["chat_modules_loaded"], probe["chat_modules_loaded"]


@pytest.mark.parametrize("head", COLUMN_HEADS)
def test_every_column_head_is_rendered(probe, head):
    """AC 1: the eight columns PRD-006 Section 4 names are all on the surface."""
    assert not probe["errors"], probe["errors"]
    assert head in probe["rendered"], head


@pytest.mark.parametrize("label", VERDICT_LABELS)
def test_every_verdict_arm_is_compiled(probe, label):
    """AC 3, from the render side.

    All four `rx.match` arms are in the compiled output, so no verdict falls
    through to the default — which would show the absent mark where a verdict
    belongs.
    """
    assert not probe["errors"], probe["errors"]
    assert label in probe["rendered"], label


@pytest.mark.parametrize("name", sorted(VERDICT_INKS))
def test_every_verdict_ink_is_drawn(probe, name):
    """AC 3: four verdicts, four inks, no two sharing a treatment."""
    assert not probe["errors"], probe["errors"]
    assert VERDICT_INKS[name].lower() in probe["rendered"].lower(), name


def test_no_colour_outside_the_allowed_set(probe):
    """AC 6, over the rendered output rather than the source.

    A source grep cannot see a colour a component supplies at compile time —
    the failure `admin_shell.py` records for `rx.link`'s Radix accent. This
    collects every hex the compiled register actually contains and holds it to
    the four verdict inks plus the ground tokens.
    """
    assert not probe["errors"], probe["errors"]
    found = {c.upper() for c in re.findall(r"#[0-9a-fA-F]{6}\b", probe["rendered"])}
    assert found <= ALLOWED_COLOURS, sorted(found - ALLOWED_COLOURS)


def test_no_tint_reaches_the_output(probe):
    """PRD-006 Risk 6: "a hundred tinted rows would be a heat map of noise."

    The palette test asserts the register names no tint; this asserts none
    arrives in the output by another route.
    """
    assert not probe["errors"], probe["errors"]
    rendered = probe["rendered"].upper()
    for name in ("TINT_CLEAR", "TINT_HELD", "TINT_DENIED", "TINT_UPSTREAM", "TINT_FAULT"):
        assert getattr(theme, name).upper() not in rendered, name


@pytest.mark.parametrize("token", ["STAMP_X", "ROW_H", "HOVER"])
def test_the_register_tokens_are_wired(probe, token):
    """The stamp margin is a fixed-width column (AC 4), the rows carry the
    register's height, and the hover ground is reachable."""
    assert not probe["errors"], probe["errors"]
    assert getattr(theme, token).lower() in probe["rendered"].lower(), token


def test_the_scope_line_is_bound_to_the_state(probe):
    """AC 2: the line is the state's field, not a string built in the component.

    `register_scope` is a computed var, so the compiled output references the
    state rather than carrying a literal — which is what proves the denominator
    is `count_audit_logs()`'s value and not a number typed here.
    """
    assert not probe["errors"], probe["errors"]
    assert "register_scope" in probe["rendered"]


# --- The source assertions ------------------------------------------------


def test_source_is_discoverable(source):
    """A missing file would pass every source test below vacuously."""
    assert source.strip(), REGISTER_SOURCE_PATH


def test_no_literal_hex_colour(source):
    """Every colour resolves from theme.py (AC 6).

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
    """Case-sensitive and quoted, deliberately: the verdict *keys* ("cleared",
    "held", …) are values the formatter declares and this module imports, and
    they differ from the labels only in what module owns them — so the check is
    that the label's value is not typed here, not that the word never appears.
    """
    value = getattr(admin_copy, name)
    assert f'"{value}"' not in source, f"{name}'s value is a literal in the register"
    assert f"'{value}'" not in source, f"{name}'s value is a literal in the register"


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


def test_body_face_appears_only_on_the_scope_line(source):
    """AC 5, made countable.

    PRD-006 Section 6.1 reserves `FONT_BODY` for "the two or three explanatory
    lines that state a scope". There is one such line on the register, so there
    is one use of the face.
    """
    assert source.count("theme.FONT_BODY") == 1, source.count("theme.FONT_BODY")


def test_the_data_face_is_dominant(source):
    """AC 5's "FONT_DATA is the dominant face", in the one form that survives a
    refactor: it is used more than the display face, which sets only the tags
    and the column heads."""
    assert source.count("theme.FONT_DATA") > source.count("theme.FONT_DISPLAY")


def test_register_sets_no_focus_reset(source):
    """theme.GLOBAL_CSS gives every focusable element a visible ring; a local
    `outline: none` would silently take it back."""
    for killer in ("outline", "box_shadow"):
        assert f'"{killer}": "none"' not in source, killer
    assert 'outline="none"' not in source


def test_the_table_scrolls_in_its_own_container(source):
    """AC 7, asserted on the three properties that make it true.

    A flex child will not shrink below its content without `min-height: 0`, so
    without it the container grows past the viewport and the *page* scrolls.
    """
    assert 'overflow_y="auto"' in source
    assert 'min_height="0"' in source
    assert 'class_name="hx-scroll"' in source


# --- The preview boundary (AC 8) ------------------------------------------


def test_neither_preview_survives_the_projection():
    """PRD-006 Risk 2, at the boundary that is supposed to hold it.

    `to_audit_row` is the only constructor on the console's path and it names
    every field it copies. Both previews are populated here with strings that
    exist nowhere else, so a `**log.__dict__` shortcut or a field-copy loop
    added later fails this.
    """
    prompt_marker = "SENTINEL-PROMPT-PREVIEW-b3f19a"
    response_marker = "SENTINEL-RESPONSE-PREVIEW-7c02de"

    class _Log:
        id = 3180
        timestamp = "2026-08-31T14:22:07+00:00"
        user_id = "a.torres"
        was_duplicate_blocked = False
        suspicious_pattern = None
        success = True
        model_used = "gpt-4"
        tokens_used = 412
        pii_detected_input = True
        pii_detected_output = False
        pii_entities = "EMAIL_ADDRESS,PERSON"
        device = "Mozilla/5.0"
        prompt_hash = "deadbeef"
        error_message = None
        prompt_preview = prompt_marker
        response_preview = response_marker

    row = to_audit_row(_Log())

    haystack = " ".join(str(value) for value in row.model_dump().values())
    assert prompt_marker not in haystack
    assert response_marker not in haystack


def test_the_register_reads_only_fields_that_exist_on_the_row(source):
    """The other half of the boundary, and the one that covers the component.

    The previews cannot reach the screen because they never reach the row — but
    that only holds while the register reads the row and nothing else. Every
    `row.<attr>` in the source is checked against `AuditRow`'s real fields, so a
    component reaching for a preview by name fails here rather than at render.
    """
    referenced = set(re.findall(r"\brow\.([a-z_][a-z0-9_]*)", source))
    assert referenced, "no row fields are read — the regex or the module moved"
    unknown = referenced - set(AuditRow.model_fields)
    assert not unknown, unknown


# --- The row disclosure (STORY-012) ---------------------------------------


@pytest.mark.parametrize("label", DETAIL_LABELS)
def test_every_disclosure_label_is_rendered(probe, label):
    """AC 1: every field PRD-006 Section 10 moves onto disclosure is labelled."""
    assert not probe["errors"], probe["errors"]
    assert label in probe["detail"], label


@pytest.mark.parametrize("field", DETAIL_ROW_FIELDS)
def test_the_disclosure_reads_every_disclosure_only_field(source, field):
    """AC 1, from the source side.

    A label rendered over a value the component never reads would satisfy the
    test above and show nothing. Each disclosure-only field must actually be
    read off the row.
    """
    assert f"row.{field}" in source, field


def test_the_error_message_and_the_pattern_lead_the_disclosure(probe):
    """AC 2 and AC 3, as ordering.

    A **fault** row is opened to read its error and a **denied** row to read its
    pattern (PRD-006 Section 5, story 3), so those two labels precede the hash.
    Neither value is projected by `GET /audit` at all — the error not at all,
    the pattern only as a flattened boolean — which is the console's clearest
    gain over `curl`.
    """
    assert not probe["errors"], probe["errors"]
    detail = probe["detail"]
    error_at = detail.index(admin_copy.DETAIL_ERROR_LABEL)
    pattern_at = detail.index(admin_copy.DETAIL_PATTERN_LABEL)
    hash_at = detail.index(admin_copy.DETAIL_PROMPT_HASH_LABEL)
    assert error_at < pattern_at < hash_at


def test_the_pii_indicator_is_split_on_the_disclosure(probe):
    """AC 4: one combined indicator in the row, two separate facts below it.

    The row answers "was there PII"; the disclosure answers "where". Two labels
    holding the same string would collapse that back into one statement.
    """
    assert not probe["errors"], probe["errors"]
    assert admin_copy.PII_INDICATOR_LABEL in probe["rendered"]
    assert admin_copy.DETAIL_PII_INPUT_LABEL in probe["detail"]
    assert admin_copy.DETAIL_PII_OUTPUT_LABEL in probe["detail"]
    assert admin_copy.DETAIL_PII_INPUT_LABEL != admin_copy.DETAIL_PII_OUTPUT_LABEL


def test_the_absent_case_is_stated_rather_than_left_blank(probe, source):
    """AC 5, over the two kinds of absence this surface has.

    The three nullable strings never arrive blank — `admin_formatting._text`
    wrote `VALUE_ABSENT` into them at the boundary — so the component adds no
    fallback for those and none is asserted here. What must be stated at render
    are the two cases with no absent mark to carry: an empty entity list, and a
    False boolean.
    """
    assert not probe["errors"], probe["errors"]
    assert admin_copy.DETAIL_PII_ABSENT_LABEL in probe["detail"]
    assert admin_copy.DETAIL_PII_PRESENT_LABEL in probe["detail"]
    # The entity list falls back to the absent mark, and does so on a length
    # test: rx.cond compiles to JS, where [] is truthy, so a bare truthiness
    # test would render an empty list as though it were populated.
    assert "pii_entities.length()" in source


def test_the_disclosure_renders_no_preview(probe):
    """AC 6, restated over the disclosure specifically.

    `test_the_register_reads_only_fields_that_exist_on_the_row` already regexes
    every `row.<attr>` in the module, so it covers the new helpers — but the
    disclosure is the surface that renders the *rest* of the row, and it is
    where a preview would be reached for.
    """
    assert not probe["errors"], probe["errors"]
    assert "prompt_preview" not in probe["detail"]
    assert "response_preview" not in probe["detail"]


def test_the_toggle_is_a_real_button_with_an_accessible_name(probe):
    """AC 7.

    A real `<button>` is the whole keyboard answer: focusable in document order,
    fires on Enter and Space with no key handling of ours. The mark is what the
    eye gets, so the name has to come from `aria-label` — and `aria-expanded`
    carries the state that the mark shows visually.
    """
    assert not probe["errors"], probe["errors"]
    toggle = probe["toggle"]
    # Reflex compiles to JSX, not to an HTML string, so the element is asserted
    # as the tag it renders rather than as "<button".
    assert 'jsx("button"' in toggle
    assert 'type:"button"' in toggle
    assert "aria-expanded" in toggle
    assert admin_copy.DETAIL_TOGGLE_OPEN_LABEL in toggle
    assert admin_copy.DETAIL_TOGGLE_CLOSE_LABEL in toggle


def test_the_open_state_is_the_state_var_not_the_dom(probe, source):
    """AC 8's mechanism.

    `rx.foreach` compiles to a `.map()` whose children are keyed by position, so
    an open flag held in the DOM would reattach itself to whichever row landed
    in that slot once STORY-013's sort and filter move them. The open set is
    `audit_id`s on the state instead, and the membership test is
    `Var.contains()` — `in` is not supported on Vars.
    """
    assert not probe["errors"], probe["errors"]
    assert "open_rows" in probe["rendered"]
    # `contains` compiles to a JS `.includes(...)` over the open set.
    assert "AdminState.open_rows.contains(" in source
    assert ".includes(" in probe["rendered"]
    # Called, not merely named: both appear in this module's docstring, which
    # records why they were rejected.
    assert "rx.el.details(" not in source
    assert "rx.accordion(" not in source


def test_toggling_one_row_is_one_event_carrying_one_id(source):
    """AC 8: the handler is called with the row's own id, so it can only ever
    open or close that row."""
    assert "AdminState.toggle_detail(row.audit_id)" in source


def test_the_disclosure_wraps_where_the_row_truncates(source):
    """AC 2's "in full".

    A row cell truncates to protect the alignment a hundred rows are scanned on.
    Below the row line there is no alignment to protect, and an `error_message`
    or a full User-Agent clipped at the container edge would be the value the
    disclosure exists to show, half-shown.
    """
    assert 'white_space="normal"' in source
    assert 'word_break="break-word"' in source


def test_the_disclosure_continues_the_stamp_margins_edge(source):
    """Risk 6, and the one structural move the disclosure makes.

    No card and no fill: what marks the block as the row's record is that the
    stamp margin's own edge runs down through it, so an open row never breaks
    the stripe of exceptions. `border_left` off `STAMP_X`, and no background.
    """
    assert "margin_left=theme.STAMP_X" in source
    assert 'background_color=theme.CARD' not in source


def test_the_row_model_still_has_no_preview_field():
    """Restated from the register's side: the projection is the mitigation, and
    a preview field arriving on it would silently make every assertion above
    vacuous."""
    fields = set(AuditRow.model_fields)
    assert "prompt_preview" not in fields
    assert "response_preview" not in fields
