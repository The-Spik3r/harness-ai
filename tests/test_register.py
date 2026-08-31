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
    # STORY-013's controls: the three cluster labels, the field's placeholder,
    # the clear action, the three ordering labels and the two direction marks.
    # The four verdict words the chips carry are already listed above — the
    # chip and the row read the same constant, which is what keeps a filter
    # from disagreeing with the rows it produced.
    "FILTER_VERDICT_LABEL",
    "FILTER_SEARCH_LABEL",
    "FILTER_SEARCH_PLACEHOLDER",
    "CLEAR_FILTERS_LABEL",
    "SORT_LABEL",
    "SORT_TIMESTAMP_LABEL",
    "SORT_USER_LABEL",
    "SORT_VERDICT_LABEL",
    "SORT_ASCENDING_MARK",
    "SORT_DESCENDING_MARK",
    # STORY-014's two empty states. The two templates
    # (EMPTY_MATCHES_TEMPLATE and the three FILTER_DESCRIPTION_* parts) are
    # deliberately absent: they are Python format strings assembled in
    # `admin_state.empty_matches_message`, and `tests/test_admin_state.py`
    # asserts the sentence they produce. What must resolve from `admin_copy`
    # *here* is what this module names directly.
    "EMPTY_REGISTER_TITLE",
    "EMPTY_REGISTER_BODY",
    "EMPTY_MATCHES_TITLE",
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
    from chat_ui.admin_state import AdminState, SORT_KEYS
    from chat_ui.components.register import (
        register,
        _SORT_CONTROLS,
        _SORT_MARKS,
        _clear_control,
        _column_head,
        _detail,
        _disclosure_toggle,
        _empty_register,
        _no_matches,
        _register_body,
        _table,
        _filter_strip,
        _filtered_line,
        _row,
        _row_line,
        _scope_line,
        _search_field,
        _sort_controls,
        _stamp_margin,
        _verdict_filter,
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
    # STORY-013's controls. The strip is what the register actually renders;
    # the five below are captured separately so a test that means to assert
    # something about the sort cluster fails when the sort cluster is what
    # broke, not when the strip is.
    ("strip", lambda: _filter_strip()),
    ("verdict_filter", lambda: _verdict_filter()),
    ("search_field", lambda: _search_field()),
    ("sort_controls", lambda: _sort_controls()),
    ("clear_control", lambda: _clear_control()),
    ("filtered_line", lambda: _filtered_line()),
    # STORY-014's three states. Captured one by one for the reason the controls
    # are: a test about the no-matches panel should fail when that panel breaks,
    # not when the table does.
    ("empty_register", lambda: _empty_register()),
    ("no_matches", lambda: _no_matches()),
    ("table", lambda: _table()),
    ("body", lambda: _register_body()),
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
for _name in (
    "strip",
    "verdict_filter",
    "search_field",
    "sort_controls",
    "clear_control",
    "filtered_line",
    "empty_register",
    "no_matches",
    "table",
    "body",
):
    result[_name] = built.get(_name, "")

# The sort tables as data. Emitted from the subprocess rather than imported in
# the test, because `register.py` does `from chat_ui import admin_copy` — which
# resolves only under the chat_ui/ PYTHONPATH this probe runs with, and is the
# whole reason the probe exists.
result["sort_keys"] = list(SORT_KEYS)
result["sort_control_keys"] = [key for key, _ in _SORT_CONTROLS]
result["sort_marks"] = {key: list(pair) for key, pair in _SORT_MARKS.items()}

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


def test_the_body_face_is_reserved_for_the_scope_lines(source):
    """STORY-011 AC 5, made countable.

    PRD-006 Section 6.1 reserves `FONT_BODY` for "the two or three explanatory
    lines that state a scope". The register has exactly two, and both take the
    reading face: `_scope_line` states the window against the whole record, and
    STORY-013's `_filtered_line` states the filtered set against the window.
    Setting the second in a different face would say the two statements are
    different kinds of thing, when they are the same kind at two scopes.

    STORY-014 takes it to **three**, and the count stays exact rather than
    becoming a ceiling. The third is the empty states' sentence — an explanatory
    line of exactly the kind Section 6.1 reserves the face for. One use and not
    two, because both panels are built by the one `_empty_panel`; a second use
    appearing here would mean the two states had grown two separate shapes.

    Still within Section 6.1's "two or three explanatory lines" on screen, too:
    an empty state replaces the table with the scope line still above it, so the
    most an admin ever sees at once is the two scope statements and one panel
    sentence.

    Still a count, and still exact: everything else on this surface is data or a
    label, and the face creeping onto a fourth element is how a register starts
    reading as prose.
    """
    assert source.count("theme.FONT_BODY") == 3, source.count("theme.FONT_BODY")


# The section marker STORY-014 opened in `register.py` for the two empty states.
# Used as a boundary below, and asserted to exist so renaming it fails loudly
# rather than silently skewing a count.
EMPTY_STATE_MARKER = "# --- The three states (STORY-014)"


def test_the_data_face_is_dominant(source):
    """AC 5's "FONT_DATA is the dominant face", in the one form that survives a
    refactor: it is used more than the display face, which sets only the tags
    and the column heads.

    Counted over the **table's** half of the module, which is the half the claim
    is about. PRD-006 Section 6.1 grounds it in the table's own job — "the
    columns are numeric and must align down a hundred rows for scanning to work
    at all" — and the two empty states have no columns and no rows. They
    contribute one display use (the shared panel's title) and no data use, which
    over the whole file drags the comparison to a tie while nothing about the
    table has changed.
    """
    assert EMPTY_STATE_MARKER in source
    table_source = source.split(EMPTY_STATE_MARKER)[0]
    assert table_source.count("theme.FONT_DATA") > table_source.count(
        "theme.FONT_DISPLAY"
    )


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
# --- STORY-013: the filter and sort controls ------------------------------
#
# The controls are asserted from both sides, like the disclosure above: the
# compiled output for what reaches the screen, the source for the claims a
# build cannot make. The recurring claim across all of them is that these
# controls *write state and read a computed var* — PRD-006 Section 6's
# "filtering never re-reads the database" is a property of this surface too,
# not only of `visible_rows`.


def _controls_source(source: str) -> str:
    """Just the control factories, from `_control_label` down to `_scope_line`.

    Sliced rather than asserted over the whole module, because two of the claims
    below are true of the controls and false of the table: the rows *do* paint a
    ground (`theme.HOVER`), and the register does draw borders. A whole-file
    assertion would have to be weakened until it stopped saying anything.
    """
    assert "def _control_label" in source and "def _scope_line" in source
    return source.split("def _control_label")[1].split("def _scope_line")[0]


@pytest.mark.parametrize(
    "label",
    [
        admin_copy.VERDICT_CLEARED_LABEL,
        admin_copy.VERDICT_HELD_LABEL,
        admin_copy.VERDICT_DENIED_LABEL,
        admin_copy.VERDICT_FAULT_LABEL,
    ],
)
def test_every_verdict_is_offered_as_a_filter(probe, label):
    """AC 1: the multi-select covers all four verdicts, not just the exceptions."""
    assert not probe["errors"], probe["errors"]
    assert label in probe["verdict_filter"], label


def test_the_filter_strip_carries_both_filters(probe):
    """AC 1: the verdict multi-select and the free-text field are both on the
    strip PRD-006 Section 6.1's wireframe puts above the table — and the strip
    is what `register()` actually renders, not a factory nothing calls."""
    assert not probe["errors"], probe["errors"]
    assert admin_copy.FILTER_VERDICT_LABEL in probe["strip"]
    assert admin_copy.FILTER_SEARCH_PLACEHOLDER in probe["strip"]
    assert admin_copy.FILTER_VERDICT_LABEL in probe["rendered"]
    assert admin_copy.FILTER_SEARCH_PLACEHOLDER in probe["rendered"]


def test_the_refreshed_stamp_sits_at_the_foot_of_the_scope_column(probe, source):
    """STORY-017, AC 1. PRD-006 Section 6.1's wireframe puts "Refreshed
    14:22:07" directly under the window it stamps, and `_filter_strip` left that
    slot free for it.

    The line itself is `admin_shell.refreshed_stamp()` — one declaration for both
    views, so the register and the summary state the refresh in one voice. What
    is asserted here is that it reaches this surface, and that this file did not
    re-declare it.
    """
    assert not probe["errors"], probe["errors"]
    assert "refreshed_stamp" in probe["strip"]
    assert "refreshed_stamp" in probe["rendered"]
    assert "refreshed_stamp()" in source
    assert "def refreshed_stamp" not in source


def test_the_verdict_filter_writes_the_state_handler(probe):
    """AC 2: a toggle is an event on `AdminState`, and the narrowing is the
    computed var — so no database call is reachable from a chip."""
    assert not probe["errors"], probe["errors"]
    assert "toggle_verdict" in probe["verdict_filter"]
    for forbidden in ("list_audit_logs", "count_audit_logs", "app.db"):
        assert forbidden not in probe["strip"], forbidden


def test_the_selected_verdicts_are_marked_without_a_fill(probe, source):
    """AC 2's "visibly marked", against PRD-006 Risk 6's "no fills".

    The mark is the verdict's own ink plus a rule in that ink plus
    `aria-pressed` — never a ground. `test_no_colour_outside_the_allowed_set`
    already proves no stray colour reaches the output; this proves the controls
    paint no *allowed* colour as a background either.
    """
    assert not probe["errors"], probe["errors"]
    assert "selected_verdicts" in probe["verdict_filter"]
    assert "aria-pressed" in probe["verdict_filter"]
    assert "background_color" not in _controls_source(source), "a control paints a ground"


def test_the_free_text_field_is_bound_to_the_search_var(probe):
    """AC 3: the field is controlled by `search` and writes `set_search`, which
    is what makes typing `127` reach `_matches`' str(audit_id) coercion."""
    assert not probe["errors"], probe["errors"]
    assert "set_search" in probe["search_field"]
    assert "search" in probe["search_field"]


def test_the_field_is_debounced_by_construction(probe):
    """PRD-006 Risk 5: "every keystroke in the filter re-evaluates a computed var
    over the full row list."

    `TextFieldRoot.create` wraps a field given both `value` and `on_change` in
    `DebounceInput`, so the mitigation is the framework's rather than a line of
    code here — which makes it exactly the kind of thing that disappears in a
    refactor to an uncontrolled field with nothing to notice it. Asserted on the
    compiled output so it is checkable rather than assumed.
    """
    assert not probe["errors"], probe["errors"]
    assert "DebounceInput" in probe["search_field"]


def test_the_filtered_count_is_a_second_line_not_a_replacement(probe):
    """AC 4: the filtered count and the window's scope are two statements.

    Both computed vars must reach the strip. Collapsing them — rendering
    `register_filtered` *instead of* `register_scope` — would leave the window's
    own line moving whenever an admin types, which is the misreading PRD-006
    Risk 4 exists to prevent.
    """
    assert not probe["errors"], probe["errors"]
    assert "register_filtered" in probe["strip"]
    assert "register_scope" in probe["strip"]


def test_the_filtered_count_shows_only_against_an_active_filter(probe):
    """"100 of 100 shown" under an untouched register reports nothing."""
    assert not probe["errors"], probe["errors"]
    assert "filters_active" in probe["filtered_line"]


def test_the_clear_action_is_conditional_on_filters_active(probe):
    """AC 5: the clear action restores the window, and appears only when there
    is one to restore — `admin_shell.py:_view_link`'s refusal of a control that
    does nothing, applied here."""
    assert not probe["errors"], probe["errors"]
    assert "clear_filters" in probe["clear_control"]
    assert "filters_active" in probe["clear_control"]
    assert admin_copy.CLEAR_FILTERS_LABEL in probe["clear_control"]


@pytest.mark.parametrize(
    "label",
    [
        admin_copy.SORT_TIMESTAMP_LABEL,
        admin_copy.SORT_USER_LABEL,
        admin_copy.SORT_VERDICT_LABEL,
    ],
)
def test_each_sort_key_has_a_control(probe, label):
    """AC 6: timestamp, user and verdict — the three orderings `_SORT_RANKS`
    dispatches on, each reachable from the surface."""
    assert not probe["errors"], probe["errors"]
    assert label in probe["sort_controls"], label


def test_the_sort_controls_cover_every_declared_key(probe):
    """One control per key in `admin_state.SORT_KEYS`, aligned one-to-one.

    A fourth ordering added to the state with no control would otherwise be
    invisible, and a control for a key the state does not dispatch on would
    silently fall back to the timestamp rank.

    Read off the probe rather than imported here: `register.py` does
    `from chat_ui import admin_copy`, which resolves only under the `chat_ui/`
    PYTHONPATH the subprocess runs with — the whole reason the probe exists.
    """
    assert not probe["errors"], probe["errors"]
    assert probe["sort_control_keys"] == probe["sort_keys"]
    assert sorted(probe["sort_marks"]) == sorted(probe["sort_keys"])


def test_the_timestamp_default_is_marked_active(source, probe):
    """AC 6: "timestamp descending remains the default."

    `sort_key` defaults to the empty string so that `sign_out()`'s reset can
    clear it, and `sort_rows` reads that as the loaded order — which is
    timestamp, newest first. Without the empty-string arm the default ordering
    would render with no control marked: true of the table, invisible on the
    surface.

    The disjunction is a Var `|` and never Python `or`, which would
    short-circuit on the first Var (always truthy) and return it instead.
    """
    assert not probe["errors"], probe["errors"]
    assert 'AdminState.sort_key == ""' in source
    assert "|" in source.split("def _is_sorted_by")[1].split("def _sort_button")[0]
    assert "sort_descending" in probe["sort_controls"]


def test_the_direction_mark_is_chosen_per_ordering(probe):
    """PRD-006's three orderings run in three different natural directions, so
    one glyph cannot serve all of them.

    `sort_rows` documents `sort_descending = False` as the natural order:
    newest-first for timestamp, A-Z for user, exceptions-first for verdict. The
    first two point opposite ways, so the marks are paired per key — and the
    timestamp and user pairs must be inverses of each other, or one of them is
    claiming a direction the list does not run in.
    """
    assert not probe["errors"], probe["errors"]
    marks = probe["sort_marks"]
    assert marks["timestamp"] == list(reversed(marks["user"]))
    assert marks["timestamp"][0] == admin_copy.SORT_DESCENDING_MARK
    assert marks["user"][0] == admin_copy.SORT_ASCENDING_MARK


def _as_compiled(mark: str) -> str:
    """How a non-ASCII mark actually appears in the compiled JSX.

    Reflex emits the arrow into the generated JavaScript as a six-character
    `\\uXXXX` escape, so counting the character itself over the rendered output
    finds nothing and quietly passes an assertion that meant to find something.
    """
    return mark.encode("unicode_escape").decode("ascii")


def test_the_direction_mark_rides_only_on_the_active_control(probe):
    """Three marks on screen would say three orderings are in force at once,
    where exactly one ever is.

    Two occurrences per ordering, not one: the mark comes out of an `rx.cond`
    over `sort_descending`, which compiles to a ternary carrying both of its
    arms. The *inactive* branch of each control carries no mark at all, and that
    is the claim — so the total is exactly two per key, and a mark leaking into
    an inactive branch pushes it to four.
    """
    assert not probe["errors"], probe["errors"]
    rendered = probe["sort_controls"]
    marks = sum(
        rendered.count(_as_compiled(mark))
        for mark in (
            admin_copy.SORT_ASCENDING_MARK,
            admin_copy.SORT_DESCENDING_MARK,
        )
    )
    assert marks == 2 * len(probe["sort_keys"]), marks


def test_every_control_is_a_real_button(probe, source):
    """AC 7: the whole keyboard answer.

    A real `<button>` takes focus in document order and fires on Enter and Space
    with no key handling, and `theme.GLOBAL_CSS`'s `:focus-visible` gives it the
    ring. A styled `rx.box` with an `on_click` would look identical and be
    unreachable by tab — which is why this is asserted on the compiled output
    rather than trusted to the source.
    """
    assert not probe["errors"], probe["errors"]
    for name in ("verdict_filter", "sort_controls", "clear_control"):
        assert "button" in probe[name].lower(), name
    assert 'type="button"' in source


def test_the_controls_set_no_focus_reset(source):
    """The ring `theme.GLOBAL_CSS` grants must not be taken back locally.

    `test_register_sets_no_focus_reset` already covers the whole module; this
    names the controls specifically because they are the elements a keyboard
    user actually lands on, and an `outline: none` added to make a chip "look
    clean" is the likely regression.
    """
    controls = _controls_source(source)
    for killer in ("outline", "box_shadow"):
        assert f'"{killer}": "none"' not in controls, killer
    assert "outline=" not in controls


# --- STORY-014: the three states ------------------------------------------
#
# The precedence itself is asserted in `tests/test_admin_state.py`, not here.
# `rx.match` compiles *every* arm into the output, so "a failed read does not
# render an empty state" is unreadable off the compiled string — it is a claim
# about `AdminState.register_state`, which is a plain Python function. What this
# section asserts is the other half: that each arm is wired to the component the
# story names, and that the two panels look the way AC 6 requires.


def test_both_empty_states_reach_the_output(probe):
    """AC 1 and AC 2: two panels, and two *different* sentences.

    The inequality is the acceptance criterion, not a tautology — a single
    shared "No rows" panel would satisfy every other assertion in this file and
    is exactly the ambiguity PRD-006 Section 4 exists to remove.
    """
    assert not probe["errors"], probe["errors"]
    assert admin_copy.EMPTY_REGISTER_TITLE in probe["empty_register"]
    assert admin_copy.EMPTY_REGISTER_BODY in probe["empty_register"]
    assert admin_copy.EMPTY_MATCHES_TITLE in probe["no_matches"]
    assert admin_copy.EMPTY_REGISTER_TITLE != admin_copy.EMPTY_MATCHES_TITLE
    # And both are reachable from the register itself, not merely constructible.
    for title in (
        admin_copy.EMPTY_REGISTER_TITLE,
        admin_copy.EMPTY_MATCHES_TITLE,
    ):
        assert title in probe["rendered"], title


def test_the_nothing_recorded_state_names_no_filter(probe):
    """AC 1's "distinct in wording", from the side that matters.

    With nothing recorded there is no filter to blame, so the panel must not
    borrow the no-matches vocabulary — including the clear action, which would
    offer to undo something that removed nothing.
    """
    assert admin_copy.EMPTY_MATCHES_TITLE not in probe["empty_register"]
    assert admin_copy.CLEAR_FILTERS_LABEL not in probe["empty_register"]


def test_the_no_matches_state_offers_the_clear_action(probe):
    """AC 2: "offers to clear it".

    Both halves: the word on screen, and the handler behind it — a label with no
    `clear_filters` behind it is a sentence, not an offer.
    """
    assert admin_copy.CLEAR_FILTERS_LABEL in probe["no_matches"]
    assert "clear_filters" in probe["no_matches"]


def test_the_no_matches_sentence_is_bound_to_the_state(probe, source):
    """AC 2's "names the filter that produced it".

    The sentence is `AdminState.empty_matches_message` — a Var reference in the
    output, never a literal assembled here. `EMPTY_MATCHES_TEMPLATE` is a Python
    format string over the selected verdicts and the loaded count, and a
    component receives Vars; the same reason the scope line is a computed var
    (`test_the_scope_line_is_bound_to_the_state`).
    """
    assert "empty_matches_message" in probe["no_matches"]
    assert "AdminState.empty_matches_message" in source
    assert "EMPTY_MATCHES_TEMPLATE" not in source


def test_the_fault_arm_renders_the_table_not_an_empty_state(source):
    """AC 4, at the render layer: an error is never presented as emptiness.

    The precedence that gets us to this arm lives in
    `admin_state.register_state` and is asserted there. What is asserted here is
    the binding — that the `read_failed` arm is the table, so the previously
    loaded rows stay on screen under the fault panel STORY-017 adds, exactly as
    `admin_copy.FAULT_MESSAGE_TEMPLATE`'s "Nothing on screen has changed"
    promises.
    """
    arms = _match_arms(source)
    fault_arm = [line for line in arms if "REGISTER_STATE_FAULT" in line]
    assert len(fault_arm) == 1, arms
    assert "_table()" in fault_arm[0]
    assert "_empty_register" not in fault_arm[0]
    assert "_no_matches" not in fault_arm[0]


def _match_arms(source: str) -> list[str]:
    """The `rx.match` arms in `_register_body`, one per line."""
    return [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith("(REGISTER_STATE_")
    ]


def test_every_register_state_has_an_arm(probe, source):
    """All four keys `admin_state.REGISTER_STATES` declares are matched.

    A state with no arm falls through to the default, which is the table — safe,
    but it would silently retire an empty state rather than fail.
    """
    assert not probe["errors"], probe["errors"]
    arms = _match_arms(source)
    assert len(arms) == 4, arms
    for state in (
        "REGISTER_STATE_FAULT",
        "REGISTER_STATE_EMPTY",
        "REGISTER_STATE_NO_MATCHES",
        "REGISTER_STATE_ROWS",
    ):
        assert any(state in arm for arm in arms), state


def test_the_table_is_the_default_arm(source):
    """An unrecognised state renders the record, never a claim of emptiness.

    The direction of the fallback is the story's whole point in miniature, so it
    is pinned rather than left to reading order.
    """
    match_body = source.split("def _register_body()")[1]
    match_body = match_body.split("return rx.match(")[1].split("\n    )")[0]
    default = match_body.strip().splitlines()[-1].strip()
    assert default == "_table(),", default


def test_the_empty_states_carry_no_card_and_no_illustration(probe):
    """AC 6: the register's existing type and rules, and nothing else.

    An empty state is the single most likely place for a card, a centred icon
    and an accent to arrive on this console (PRD-006 Risk 6) — the template
    answer for a screen with nothing on it. None of them may.
    `test_no_colour_outside_the_allowed_set` covers the accent over the whole
    surface; this covers the shapes.
    """
    for name in ("empty_register", "no_matches"):
        rendered = probe[name]
        for forbidden in (
            "backgroundColor",
            "borderRadius",
            "boxShadow",
            "borderTop",
            "<svg",
            "<img",
        ):
            assert forbidden not in rendered, (name, forbidden)


def test_the_empty_states_use_the_registers_own_type_scale(probe, source):
    """AC 6's "existing type": the panel's faces are the two the surface already
    uses, taken from `theme.py` rather than declared locally."""
    panel = source.split(EMPTY_STATE_MARKER)[1].split("def register()")[0]
    assert "theme.FONT_DISPLAY" in panel
    assert "theme.FONT_BODY" in panel
    assert 'font_family="' not in panel
    assert theme.TEXT_LEAD in probe["empty_register"]


def test_the_table_arm_is_the_table_story_011_built(probe):
    """AC 3: rows shown means the table, unchanged — the same role and the same
    column heads STORY-011 put there, with neither empty state near it."""
    assert 'role:"table"' in probe["table"]
    for head in COLUMN_HEADS:
        assert head in probe["table"], head
    assert admin_copy.EMPTY_REGISTER_TITLE not in probe["table"]
    assert admin_copy.EMPTY_MATCHES_TITLE not in probe["table"]


def test_the_filter_strip_renders_in_every_state(source):
    """The controls sit outside the switch, so the way out of the no-matches
    state is never taken away with the rows.

    `register()` renders `_filter_strip()` as a sibling of `_register_body()`,
    not inside an arm — removing the controls in the one state an admin needs
    them to escape is the dead end the frontend-design skill's "an empty screen
    is an invitation to act" rules out.
    """
    register_body = source.split("def register()")[1]
    assert "_filter_strip()" in register_body
    assert "_register_body()" in register_body
    # And the strip is not inside the switch: _register_body never mentions it.
    switch = source.split("def _register_body()")[1].split("def register()")[0]
    assert "_filter_strip" not in switch
