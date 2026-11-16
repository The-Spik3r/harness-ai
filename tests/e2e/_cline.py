"""The Cline E2E's constants and pure helpers (PRD-017 STORY-017).

Nothing here is a test or a fixture, and nothing reads the environment, starts a
process or imports `app` (importing `app.services` builds `Settings()` in the
caller's process, the reason `_live.py` gives). `tests/e2e/test_cline.py` runs
the real Cline with them, and the everyday `tests/test_e2e_cline_script.py` pins
what they render, so a change to the stub script or to the action policy fails
in the normal suite and not only under `--run-e2e`.

The task is STORY-016's (`_opencode`): the same repository layout, the same file
contents, the same audit assertions. Only the tool shapes differ (Cline 4.x).
"""

import json
from pathlib import Path

from tests.e2e import _live
from tests.e2e._opencode import (  # noqa: F401  (re-exported: the same task, reused)
    CALC_EDITED,
    CALC_ORIGINAL,
    DENIAL_NOTE_TEMPLATE,
    TEST_ORIGINAL,
    TEST_WRITTEN,
    repo_root_text,
)

SCRIPT = _live.REPO_ROOT / "tests" / "e2e" / "scripts" / "cline.json"
POLICY = _live.REPO_ROOT / "tests" / "e2e" / "cline" / "action_policy.yaml"
CLIENT_DIR = _live.REPO_ROOT / "tests" / "e2e" / ".clients" / "cline"
CLINE_VERSION = "3.0.74"
ALLOWLIST = HARNESS_MODEL = "openai/gpt-4o"
TEST_COMMAND = "python -m unittest"
#: Never `npm -g` (PRD-017: no global installs). The install is local, pinned and git-ignored.
INSTALL_RECIPE = (
    "npm install --prefix tests/e2e/.clients/cline --save-exact --no-audit --no-fund cline@3.0.74 "
    "(or copy tests/e2e/cline/package.json there and run npm install --prefix tests/e2e/.clients/cline)"
)

#: `-t`, as the story asks. It does not bound the run (probe: Cline sent 984 requests in 60 s with `-t 10`),
#: so the real bounds are the script's `default` (a `submit_and_exit`) and `PROCESS_TIMEOUT_SECONDS`.
RUN_TIMEOUT_SECONDS = 60
PROCESS_TIMEOUT_SECONDS = 180

#: Directory names the stub tells the two scenarios apart by: Cline's system prompt carries the
#: working directory, and the last user turn is Cline's own nudge, not the prompt.
TASK_DIR = "e2e017-017-cline-task"
DROP_DIR = "e2e017-017-cline-drop"

#: The stub's rule labels (tests/e2e/scripts/cline.json): the rule's index.
DROP_SUBMIT_RULE, DROP_RULE, START_RULE, EDIT_RULE, TEST_RULE, WRITE_RULE, DONE_RULE, FAILED_RULE = (
    "0", "1", "2", "3", "4", "5", "6", "7")

#: The tools Cline's `--yolo` preset advertises for `openai/gpt-4o` (planning probe), sorted.
YOLO_TOOLS = ("editor", "read_files", "run_commands", "submit_and_exit")

_PLACEHOLDER = "@REPO@"


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
    """The committed Cline action policy (F11) with `@REPO@` replaced by the workspace root."""
    return POLICY.read_text(encoding="utf-8").replace(_PLACEHOLDER, repo_text)


def cline_executable(client_dir: Path) -> Path:
    """The platform binary under `client_dir`, not the npm `.cmd` shim (not spawnable from Python).

    Returns a path and does not check that it exists; the fixture does.
    """
    found = sorted((client_dir / "node_modules" / "@cline").glob("cli-*/bin/cline*"))
    if len(found) != 1:
        return client_dir / "node_modules" / "@cline" / "cli-<platform>" / "bin" / "cline"
    return found[0]


def auth_command(exe, data_dir: Path, base_url: str, token: str) -> list:
    """`cline auth`: the harness as an `openai-compatible` provider, in `data_dir`.

    `data_dir` must be absolute: a relative one is resolved against the process's
    cwd for `auth` and against `-c` for the run, so the run found no provider
    config and called api.openai.com with no key (planning probe, item 2).
    """
    assert Path(data_dir).is_absolute(), "--data-dir must be an absolute path"
    return [str(exe), "auth", "--data-dir", str(data_dir), "--provider", "openai-compatible",
            "--apikey", token, "--modelid", HARNESS_MODEL, "--baseurl", f"{base_url}"]


def run_command(exe, data_dir: Path, repo: Path, prompt: str) -> list:
    """`cline --yolo --json` headless in `repo`, one run."""
    assert Path(data_dir).is_absolute(), "--data-dir must be an absolute path"
    return [str(exe), "--data-dir", str(data_dir), "--yolo", "--json", "-c", str(repo),
            "-P", "openai-compatible", "-m", HARNESS_MODEL, "-t", str(RUN_TIMEOUT_SECONDS), prompt]
