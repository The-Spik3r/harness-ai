"""The OpenCode E2E's constants and pure helpers (PRD-017 STORY-016).

Nothing here is a test or a fixture, and nothing reads the environment, starts a
process or imports `app` (importing `app.services` builds `Settings()` in the
caller's process, the reason `_live.py` gives). `tests/e2e/test_opencode.py`
runs the real OpenCode with them, and the everyday
`tests/test_e2e_opencode_script.py` pins what they render, so a change to the
stub script or to the action policy fails in the normal suite and not only
under `--run-e2e`.
"""

import json
from pathlib import Path

from tests.e2e import _live

SCRIPT = _live.REPO_ROOT / "tests" / "e2e" / "scripts" / "opencode.json"
ALLOWLIST = HARNESS_MODEL = "openai/gpt-4o"
#: `<provider id>/<model id>`: the model id keeps its own slash.
OPENCODE_MODEL = "harness/openai/gpt-4o"
OPENCODE_VERSION = "v2.0.10"
TEST_COMMAND = "python -m unittest"

#: The stub's rule labels (tests/e2e/scripts/opencode.json): the rule's index.
DROP_RULE, START_RULE, EDIT_RULE, WRITE_RULE, TEST_RULE, DONE_RULE = "0", "1", "2", "3", "4", "5"
FAILED_RULE, TITLE_RULE = "6", "7"

CALC_ORIGINAL = "def add(a, b):\n    return a - b\n"
CALC_EDITED = "def add(a, b):\n    return a + b\n"
TEST_ORIGINAL = "# placeholder\n"
TEST_WRITTEN = (
    "import unittest\n\nfrom src.calc import add\n\n\nclass AddTest(unittest.TestCase):\n"
    "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n\n\n"
    'if __name__ == "__main__":\n    unittest.main()\n'
)

#: app/services/tool_release.py:41 (DENIAL_NOTE_TEMPLATE), mirrored as a literal for the
#: reason in the module docstring. tests/test_e2e_opencode_script.py keeps them equal.
DENIAL_NOTE_TEMPLATE = "[harness] tool call {name} ({id}) was denied: {reason}"

_PLACEHOLDER = "@REPO@"


def repo_root_text(path: Path) -> str:
    """The repository's absolute path as forward slashes, safe inside a JSON string and a YAML scalar."""
    text = path.resolve().as_posix()
    for bad in ('"', "\\", _PLACEHOLDER):
        assert bad not in text, f"the repository path holds {bad!r}, which the rendered script cannot carry"
    return text


def render_script(repo_text: str) -> str:
    """The committed stub script with `@REPO@` replaced by `repo_text`.

    The placeholder is only inside `arguments` strings. The substituted path has
    no quote or backslash, so the JSON stays valid and every `arguments` stays a
    byte string the stub sends as given (PRD-017 D13).
    """
    rendered = SCRIPT.read_text(encoding="utf-8").replace(_PLACEHOLDER, repo_text)
    json.loads(rendered)  # fails here, naming the script, rather than inside the stub
    return rendered


def policy_yaml(repo_text: str) -> str:
    """The E2E action policy (F11): the workspace root and the one allowlisted shell command."""
    return (
        "# PRD-017 STORY-016: the E2E action policy (F11). Sections left out keep the built-in ones,\n"
        "# including the built-in tool mapping (OpenCode 2.0: shell, read, write, edit with filePath|path).\n"
        "# `execute` (CodeMode) is not mapped, so it stays tool.unknown.\n"
        "workspace:\n"
        "  roots:\n"
        f'    - "{repo_text}"\n'
        "shell:\n"
        "  allow:\n"
        f"    - {TEST_COMMAND}\n"
    )


def opencode_config(base_url: str, token: str) -> dict:
    """The `OPENCODE_CONFIG_CONTENT` JSON: the harness as an OpenAI-compatible provider.

    `agent.title.disable` stops OpenCode's tool-less title request, so each run's
    first request is the agent's own.
    """
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": OPENCODE_MODEL,
        "agent": {"title": {"disable": True}},
        "provider": {
            "harness": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Harness",
                "options": {"baseURL": f"{base_url}/v1", "apiKey": token},
                "models": {HARNESS_MODEL: {"name": "gpt-4o"}},
            }
        },
    }
