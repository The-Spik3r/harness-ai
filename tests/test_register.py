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
        _row,
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
    ("stamps", lambda: rx.box(rx.foreach(AdminState.visible_rows, _stamp_margin))),
    ("tags", lambda: rx.box(rx.foreach(AdminState.visible_rows, _verdict_tag))),
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


def test_the_row_model_still_has_no_preview_field():
    """Restated from the register's side: the projection is the mitigation, and
    a preview field arriving on it would silently make every assertion above
    vacuous."""
    fields = set(AuditRow.model_fields)
    assert "prompt_preview" not in fields
    assert "response_preview" not in fields
