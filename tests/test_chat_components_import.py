"""Smoke test for the Reflex component layer.

Every other chat test exercises ChatState only, so a broken import or a
renderer deleted from bubbles.py passes the whole suite while the app fails to
start. That is exactly what happened when a merge dropped
render_pending_indicator() and reintroduced a circular `chat_ui.chat_ui` import:
232 tests green, `reflex run` dead.

The checks run in a subprocess with PYTHONPATH set to `chat_ui/`, which is how
Reflex itself imports the app (`chat_ui.components...`, not
`chat_ui.chat_ui.components...`). Doing it in-process would put the inner
package on sys.path and break every other test module, which reaches the same
files by their repo-root path.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTHONPATH = [str(REPO_ROOT / "chat_ui"), str(REPO_ROOT)]

# Every renderer message_bubble() dispatches to, plus the pending indicator.
_EXPECTED_RENDERERS = [
    "render_user",
    "render_assistant",
    "render_duplicate",
    "render_injection",
    "render_upstream_error",
    "render_internal_error",
    "render_fallback",
    "render_pending_indicator",
]

# Every kind send() can append, plus one it never emits: the rx.match default
# arm has to keep "no silent drops" true at the render layer too.
_KINDS = [
    "user",
    "assistant",
    "duplicate",
    "injection",
    "upstream_error",
    "internal_error",
    "something_new",
]

# Runs in the subprocess. Takes the renderer and kind lists as JSON on argv so
# nothing has to be interpolated into the source.
_CHECK_SCRIPT = r"""
import json, sys

renderers, kinds = json.loads(sys.argv[1]), json.loads(sys.argv[2])
result = {"errors": []}

try:
    import reflex as rx
    from chat_ui.components import bubbles
    from chat_ui.components.chat import chat_input, message_bubble, message_list
    from chat_ui.components.shell import empty_state, header, user_id_gate
    from chat_ui.state import ChatState
except Exception as exc:
    print(json.dumps({"errors": ["import: {}: {}".format(type(exc).__name__, exc)]}))
    sys.exit(0)

result["missing_renderers"] = [n for n in renderers if not hasattr(bubbles, n)]

# Renderers receive a Var, never a concrete ChatMessage: rx.foreach hands them
# a JS reference. Exercising them any other way would not compile the same code.
message_var = ChatState.messages[0]

unrendered = []
for name in renderers:
    try:
        renderer = getattr(bubbles, name)
        component = renderer() if name == "render_pending_indicator" else renderer(message_var)
        if not isinstance(component, rx.Component):
            unrendered.append(name)
    except Exception as exc:
        unrendered.append("{} ({}: {})".format(name, type(exc).__name__, exc))

# And the rx.match dispatch itself, including its default arm.
try:
    if not isinstance(message_bubble(message_var), rx.Component):
        unrendered.append("message_bubble")
except Exception as exc:
    unrendered.append("message_bubble ({}: {})".format(type(exc).__name__, exc))
result["unrendered_kinds"] = unrendered

broken = []
for factory in (header, empty_state, user_id_gate, message_list, chat_input):
    try:
        if not isinstance(factory(), rx.Component):
            broken.append(factory.__name__)
    except Exception as exc:
        broken.append("{} ({}: {})".format(factory.__name__, type(exc).__name__, exc))
result["broken_shell"] = broken

print(json.dumps(result))
"""


@pytest.fixture(scope="module")
def probe():
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            _CHECK_SCRIPT,
            json.dumps(_EXPECTED_RENDERERS),
            json.dumps(_KINDS),
        ],
        cwd=str(REPO_ROOT / "chat_ui"),
        env={**os.environ, "PYTHONPATH": os.pathsep.join(_PYTHONPATH)},
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.fail(f"component probe crashed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_component_modules_import(probe):
    """Catches circular imports and names missing at module scope."""
    assert not probe["errors"], probe["errors"]


def test_every_renderer_is_defined(probe):
    assert not probe["errors"], probe["errors"]
    assert not probe["missing_renderers"], (
        f"bubbles.py is missing renderers: {probe['missing_renderers']}"
    )


def test_every_kind_renders_a_component(probe):
    """PRD-004 'no silent drops', enforced at the render layer."""
    assert not probe["errors"], probe["errors"]
    assert not probe["unrendered_kinds"], probe["unrendered_kinds"]


def test_page_shell_builds(probe):
    assert not probe["errors"], probe["errors"]
    assert not probe["broken_shell"], probe["broken_shell"]
