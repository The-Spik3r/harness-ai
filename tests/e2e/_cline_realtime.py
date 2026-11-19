"""The real-time Cline E2E's constants and pure helpers (PRD-021 STORY-015).

Nothing here is a test or a fixture, and nothing reads the environment, starts a
process or imports `app` (the reason `_live.py` gives). `test_cline_realtime.py`
runs the real Cline with them; `tests/test_e2e_cline_realtime_script.py` pins what
they render in the everyday suite. The client-neutral pieces (registry, roles file,
SSE parsing) are STORY-014's, and the Cline pieces are PRD-017's: both re-exported.
"""

import json

from tests.e2e import _live
from tests.e2e._cline import (  # noqa: F401  (re-exported for the module)
    CLIENT_DIR,
    DENIAL_NOTE_TEMPLATE,
    INSTALL_RECIPE,
    PROCESS_TIMEOUT_SECONDS,
    YOLO_TOOLS,
    auth_command,
    cline_executable,
    policy_yaml,
    repo_root_text,
    run_command,
)
from tests.e2e._opencode_realtime import (  # noqa: F401  (re-exported for the module)
    COMPLETION_ID_PREFIX,
    REASONING_FIELD,
    argument_fragments,
    parse_sse,
    registry_yaml,
    roles_json,
)

SCRIPT = _live.REPO_ROOT / "tests" / "e2e" / "scripts" / "cline_realtime.json"

#: Directory names the stub tells the scenarios apart by: Cline's system prompt carries the
#: working directory, and its last user turn is its own nudge, not the prompt.
TEXT_DIR = "e2e021-015-cline-text"
DROP_DIR = "e2e021-015-cline-drop"
REASON_DIR = "e2e021-015-cline-reason"

#: Stub rule labels (the rule's index in cline_realtime.json).
FOLLOWUP_RULE, DROP_RULE, TEXT_RULE, REASON_RULE = "0", "1", "2", "3"

_REPO = "@REPO@"
_SENTINEL = "@SENTINEL@"


def render_script(repo_text: str, sentinel: str) -> str:
    """The committed stub script with `@REPO@` and `@SENTINEL@` replaced (`@REPO@` is unused today)."""
    rendered = SCRIPT.read_text(encoding="utf-8").replace(_REPO, repo_text).replace(_SENTINEL, sentinel)
    json.loads(rendered)  # fails here, naming the script, rather than inside the stub
    return rendered
