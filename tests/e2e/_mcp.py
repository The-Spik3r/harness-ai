"""The MCP client E2E's constants and pure helpers (PRD-023 STORY-020).

Nothing here is a test or a fixture, and nothing starts a process or reads the
environment. `tests/e2e/test_mcp_clients.py` runs the real OpenCode and Cline CLIs
with them against a live harness (`/mcp`) and the real MCP stub, and the everyday
`tests/test_e2e_mcp_clients_script.py` pins what they render, so a change to the
scripts, the config or the corpus fails in the normal suite and not only under
`--run-e2e`.

The cases are the STORY-019 corpus's (`outcome-select-ok`, `brief-drop-table`, role
`dev`): the decision, the rule and the outcome the rows must carry are read from the
YAML, not restated. The corpus roles exist only in `mcp_corpus.configure()`'s
monkeypatched matrix, so a real process gets the same matrix through
`RBAC_ROLES_FILE` (`roles_json`), and `scripts/manage_users.py` only creates `admin`,
`auditor` and `user`: `ROLE_MAP` says which harness role stands for which corpus role.
"""

import json
from pathlib import Path

from tests import mcp_corpus
from tests.e2e import _live
from tests.e2e._cline import auth_command, cline_executable, run_command  # noqa: F401  (re-exported)
from tests.e2e._opencode import repo_root_text  # noqa: F401  (re-exported)

SCRIPTS = _live.REPO_ROOT / "tests" / "e2e" / "scripts"
OPENCODE_SCRIPT = SCRIPTS / "opencode_mcp.json"
CLINE_SCRIPT = SCRIPTS / "cline_mcp.json"

OPENCODE_VERSION = "v2.3.2"
CLINE_VERSION = "3.0.74"
#: The model the clients are configured with. The scripted fake provider answers it; nothing is checked on it.
MODEL = "openai/gpt-4o"
OPENCODE_MODEL = f"harness/{MODEL}"

#: The corpus cases replayed (file stems of `tests/corpora/mcp/calls/`) and the corpus role they run as.
CASE_ALLOW = "outcome-select-ok"
CASE_DENY = "brief-drop-table"
CORPUS_ROLE = "dev"

#: The MCP server key both clients are configured with; it prefixes the model-facing tool names.
CLIENT_KEY = "harness"
#: What the model sees for the stub's `query` tool (STORY-002, `tests/corpora/mcp/SOURCES.md`).
OPENCODE_QUERY = f"{CLIENT_KEY}_stub__query"
CLINE_QUERY = f"{CLIENT_KEY}__stub__query"
OPENCODE_PREFIX = f"{CLIENT_KEY}_"
CLINE_PREFIX = f"{CLIENT_KEY}__"

#: Corpus role -> the role `scripts/manage_users.py` can create (test-only mapping, stated in the module docstring).
ROLE_MAP = {"dev": "user", "dba": "admin", "user": "auditor"}

#: The stub's rule labels (the rule's index in each script).
OC_AFTER_RULE, OC_DROP_RULE, OC_ALLOW_RULE, OC_TITLE_RULE = "0", "1", "2", "3"
CL_AFTER_RULE, CL_DROP_RULE, CL_ALLOW_RULE = "0", "1", "2"
#: Cline picks the scenario from the system prompt's working directory (see `_cline.TASK_DIR`).
CL_ALLOW_DIR = "e2e023-020-cline-allow"
CL_DROP_DIR = "e2e023-020-cline-drop"

_ARGS_ALLOW, _ARGS_DENY = "@ARGS_ALLOW@", "@ARGS_DENY@"

# Literals, not imports of `app.services.authz`: the matrix a real process loads is a JSON file.
_BUILT_IN = {
    "admin": ["query:submit", "query:byok", "audit:read:all", "audit:read:own", "stats:read", "mcp:connect"],
    "auditor": ["audit:read:all", "audit:read:own", "stats:read"],
    "user": ["query:submit", "audit:read:own", "mcp:connect"],
}


def pick_cases() -> dict:
    """`{"allow": Case, "deny": Case}` from the corpus, by file stem. Fails naming a missing stem."""
    by_stem = {case.path.stem: case for case in mcp_corpus.load_corpus()}
    picked = {}
    for key, stem in (("allow", CASE_ALLOW), ("deny", CASE_DENY)):
        assert stem in by_stem, f"the corpus has no {stem}.yaml (tests/corpora/mcp/calls)"
        assert by_stem[stem].e2e, f"{stem}.yaml is marked e2e: false"
        picked[key] = by_stem[stem]
    return picked


def visible_tools() -> list:
    """The bare `stub__*` names the skill's holder is offered: the skill's tools minus what the stub does not have
    (`nope`) and what the harness withholds (`poisoned`, an injection in its description). Sorted."""
    hidden = {f"{mcp_corpus.SERVER}__{tool}" for tool in ("nope", "poisoned")}
    return sorted(set(mcp_corpus.SKILL.tools) - hidden)


def never_offered() -> list:
    """Bare tool names that must not reach the model: not in the skill, absent upstream, or withheld."""
    return ["stub__create_branch", "stub__poisoned", "stub__nope"]


def opencode_tool_name(bare: str) -> str:
    return OPENCODE_PREFIX + bare


def cline_tool_name(bare: str) -> str:
    return CLINE_PREFIX + bare


def roles_json() -> str:
    """`RBAC_ROLES_FILE` content: the corpus matrix of `mcp_corpus.configure()` on the harness roles of `ROLE_MAP`.

    Built-in permissions stay (the file replaces the matrix wholesale), `mcp:connect` for each, the skill for
    `dev`'s role, the skill and `action:sql:ddl` for `dba`'s.
    """
    skill = f"skill:{mcp_corpus.SKILL_ID}"
    matrix = {role: list(permissions) for role, permissions in _BUILT_IN.items()}
    for corpus_role, extra in (("dev", [skill]), ("dba", [skill, "action:sql:ddl"]), ("user", [])):
        role = matrix[ROLE_MAP[corpus_role]]
        for permission in ("mcp:connect", *extra):
            if permission not in role:
                role.append(permission)
    return json.dumps(matrix, indent=2)


def mcp_config_yaml(stub_url: str) -> str:
    """`MCP_CONFIG_FILE` content: server `stub` (plain http to loopback, no auth) and the corpus skill."""
    tools = ", ".join(mcp_corpus.SKILL.tools)
    return (
        "# PRD-023 STORY-020: the E2E gateway config (shape of examples/mcp.yaml).\n"
        "servers:\n"
        f"  {mcp_corpus.SERVER}:\n"
        f"    url: {stub_url}\n"
        "    allow_insecure: true\n"
        "    auth: {type: none}\n"
        f"    timeout_seconds: {mcp_corpus.TIMEOUT_SECONDS * 15}\n"
        "skills:\n"
        f"  {mcp_corpus.SKILL_ID}:\n"
        f"    version: {mcp_corpus.SKILL.version}\n"
        f"    description: {mcp_corpus.SKILL.description}\n"
        f"    instructions: {mcp_corpus.SKILL.instructions}\n"
        f"    tools: [{tools}]\n"
        "    requires: []\n"
    )


def policy_yaml() -> str:
    """`ACTION_POLICY_FILE` content: the corpus policy plus the two skill tools it leaves out.

    `mcp_corpus.configure()` installs its config by assignment, so it never cross-validates the
    skill's `nope` and `poisoned` against the policy. A real process does (`mcp_config.load()`,
    "has no mcp_tools or mcp_opaque_tools entry"): both get an `allow` entry. Neither is ever
    offered or called (absent upstream / withheld), so the entries decide nothing.
    """
    assert mcp_corpus.POLICY.endswith("    inject: allow\n"), "mcp_corpus.POLICY changed: update _mcp.policy_yaml"
    return mcp_corpus.POLICY + "    nope: allow\n    poisoned: allow\n"


def _client_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def opencode_config(provider_base: str, harness_base: str, token: str) -> dict:
    """The `OPENCODE_CONFIG_CONTENT` JSON.

    The model provider is the scripted fake (`provider_base`, no `/v1` hop to the harness); the harness is
    only an MCP server, `remote`, with the static `Authorization` header (STORY-002). `codemode: false` keeps
    OpenCode calling the MCP tool itself. No `enabled` key: OpenCode's switch is `disabled`.
    """
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": OPENCODE_MODEL,
        "agent": {"title": {"disable": True}},
        "provider": {
            "harness": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Scripted model",
                "options": {"baseURL": f"{provider_base}/v1", "apiKey": "e2e-unused-key"},
                "models": {MODEL: {"name": "gpt-4o"}},
            }
        },
        "mcp": {
            "servers": {
                CLIENT_KEY: {
                    "type": "remote",
                    "url": f"{harness_base}/mcp",
                    "headers": _client_headers(token),
                    "codemode": False,
                }
            }
        },
    }


def cline_settings(harness_base: str, token: str) -> dict:
    """`<data-dir>/settings/cline_mcp_settings.json`. Without `type` Cline falls back to SSE and lists nothing."""
    return {
        "mcpServers": {
            CLIENT_KEY: {
                "type": "streamableHttp",
                "url": f"{harness_base}/mcp",
                "headers": _client_headers(token),
            }
        }
    }


def render_script(path: Path) -> str:
    """A committed scenario script with the corpus's argument texts in place of `@ARGS_ALLOW@` / `@ARGS_DENY@`.

    The placeholders sit inside `arguments` strings; the corpus text is substituted as a JSON string body, so
    the stub sends the corpus bytes and the script stays valid JSON.
    """
    cases = pick_cases()
    rendered = path.read_text(encoding="utf-8")
    for placeholder, key in ((_ARGS_ALLOW, "allow"), (_ARGS_DENY, "deny")):
        rendered = rendered.replace(placeholder, json.dumps(cases[key].arguments)[1:-1])
    json.loads(rendered)  # fails here, naming the script, rather than inside the stub
    return rendered
