"""The real-time OpenCode E2E's constants and pure helpers (PRD-021 STORY-014).

Nothing here is a test or a fixture, and nothing reads the environment, starts a
process or imports `app` (the reason `_live.py` gives). `test_opencode_realtime.py`
runs the real OpenCode with them; `tests/test_e2e_opencode_realtime_script.py`
pins what they render in the everyday suite.
"""

import json
from typing import Optional

from tests.e2e import _live
from tests.e2e import _opencode
from tests.e2e._opencode import HARNESS_MODEL, repo_root_text  # noqa: F401  (re-exported for the module)

SCRIPT = _live.REPO_ROOT / "tests" / "e2e" / "scripts" / "opencode_realtime.json"
PROVIDER = "harness-rt"
#: Stub rule labels (the rule's index in opencode_realtime.json).
DROP_RULE, TEXT_RULE, REASON_RULE, FALLBACK_RULE = "0", "1", "2", "3"
COMPLETION_ID_PREFIX = "chatcmpl-harness-rt-"
#: The key OpenCode is told to read reasoning from (PRD-021 O5: the harness emits only this one).
REASONING_FIELD = "reasoning_content"

_REPO = "@REPO@"
_SENTINEL = "@SENTINEL@"

# Literals of authz.PERMISSION_* (no `app` import here); the fast test ties them to authz.
ADMIN_PERMISSIONS = ["query:submit", "query:byok", "audit:read:all", "audit:read:own", "stats:read"]
USER_PERMISSIONS = ["query:submit", "audit:read:own", "stream:realtime"]
AUDITOR_PERMISSIONS = ["query:submit", "audit:read:own", "stream:realtime", "reasoning:view"]


def render_script(repo_text: str, sentinel: str) -> str:
    """The committed stub script with `@REPO@` and `@SENTINEL@` replaced (mirrors `_opencode.render_script`)."""
    rendered = SCRIPT.read_text(encoding="utf-8").replace(_REPO, repo_text).replace(_SENTINEL, sentinel)
    json.loads(rendered)
    return rendered


def registry_yaml(base_url: str) -> str:
    """The registry file for the harness child: one internal keyless provider whose model streams and reasons.

    Legacy mode never streams (PRD-021 OD1), so real time needs a file-mode registry.
    """
    return (
        "version: 1\n"
        f"default_model: {HARNESS_MODEL}\n"
        "providers:\n"
        f"  - name: {PROVIDER}\n"
        "    type: openai_compatible\n"
        f"    base_url: {base_url}\n"
        "    trust: internal\n"
        "    usage_missing: estimate\n"
        "    models:\n"
        f"      - id: {HARNESS_MODEL}\n"
        "        capabilities: {tools: true, streaming: true, reasoning: true}\n"
    )


def roles_json() -> str:
    """`RBAC_ROLES_FILE` content. It replaces the matrix wholesale (authz.load), so `user` and `auditor` are redefined.

    manage_users.py limits `--role` to admin|auditor|user, so the grants ride on those names.
    """
    return json.dumps({"admin": ADMIN_PERMISSIONS, "user": USER_PERMISSIONS, "auditor": AUDITOR_PERMISSIONS}, indent=2)


def opencode_config(base_url: str, token: str, reasoning_key: Optional[dict] = None) -> dict:
    """`_opencode.opencode_config` plus the reasoning field OpenCode reads (Task 3b).

    `reasoning_key` is merged into the model entry (e.g. `{"compatibility": {"reasoningField": ...}}`).
    """
    config = _opencode.opencode_config(base_url, token)
    model = config["provider"]["harness"]["models"][HARNESS_MODEL]
    if reasoning_key:
        model.update(reasoning_key)
    return config


def parse_sse(entries: Optional[list]) -> list:
    """The recorder's `(seconds, payload)` list as chunks.

    Each chunk: `t`, `id`, `content`, `reasoning`, `tool_calls`, `finish_reason`, `raw`; `[DONE]` is
    `{"t", "done": True}`.
    """
    chunks = []
    for seconds, payload in entries or []:
        if payload.strip() == "[DONE]":
            chunks.append({"t": seconds, "done": True, "raw": payload})
            continue
        body = json.loads(payload)
        choice = (body.get("choices") or [{}])[0]
        delta = choice.get("delta") or {}
        chunks.append({
            "t": seconds, "done": False, "id": body.get("id"), "content": delta.get("content"),
            "reasoning": delta.get("reasoning_content"), "tool_calls": delta.get("tool_calls"),
            "role": delta.get("role"), "finish_reason": choice.get("finish_reason"),
            "raw": payload, "body": body,
        })
    return chunks


def argument_fragments(arguments: str, size: int) -> list:
    """The stub's cuts of a call's `arguments` (scripts/stub_openrouter.py: pieces of at most `size`)."""
    return [arguments[i:i + size] for i in range(0, len(arguments), size)] or [""]
