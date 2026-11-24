"""PRD-023 T17 / STORY-010: the harness runs no tool code, and only one module holds the SDK.

`mcp` (the SDK) and `httpx2` (its transport) are imported by
`app/services/mcp_upstream.py` and nothing else under `app/`. Nothing under
`app/` imports `mcp.client.stdio` (a subprocess transport), `mcp.server*`, or
`subprocess` in a module that also imports `mcp*`. Test infrastructure
(`scripts/stub_mcp_server.py`) is outside `app/` and may use the server side.
"""

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ALLOWED = "app/services/mcp_upstream.py"
_SDK_ROOTS = ("mcp", "httpx2")


def _imported(source: str) -> list:
    names = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
            # `from mcp.client import stdio` imports mcp.client.stdio.
            names += [f"{node.module}.{a.name}" for a in node.names]
    return names


def _is_sdk(name: str) -> bool:
    return any(name == root or name.startswith(root + ".") for root in _SDK_ROOTS)


def violations(source: str, path: str) -> list:
    """What `source` (a module at repo-relative `path`) may not import."""
    names = _imported(source)
    found = []
    if path != _ALLOWED:
        found += [f"{path}: imports {n}" for n in names if _is_sdk(n)]
    found += [
        f"{path}: imports {n}"
        for n in names
        if n == "mcp.client.stdio" or n == "mcp.server" or n.startswith("mcp.server.")
    ]
    if any(n == "mcp" or n.startswith("mcp.") for n in names) and any(
        n == "subprocess" or n.startswith("subprocess.") for n in names
    ):
        found.append(f"{path}: imports subprocess alongside the mcp SDK")
    return found


def _app_files():
    return sorted((_REPO_ROOT / "app").rglob("*.py"))


def test_only_mcp_upstream_imports_mcp_and_httpx2():
    found = []
    for path in _app_files():
        rel = path.relative_to(_REPO_ROOT).as_posix()
        found += violations(path.read_text(encoding="utf-8"), rel)

    assert found == []


def test_the_guard_is_not_vacuous():
    allowed = _REPO_ROOT / _ALLOWED
    assert allowed.is_file()
    imported = _imported(allowed.read_text(encoding="utf-8"))
    assert any(n == "mcp" or n.startswith("mcp.") for n in imported)
    assert any(n == "httpx2" or n.startswith("httpx2.") for n in imported)
    # The scanner flags planted sources, and the allowed module is allowed only for sdk imports.
    assert violations("import mcp\n", "app/services/other.py")
    assert violations("import httpx2\n", "app/x.py")
    assert violations("from mcp.client.stdio import stdio_client\n", _ALLOWED)
    assert violations("from mcp.server.mcpserver import MCPServer\n", _ALLOWED)
    assert violations("from mcp.client import stdio\n", _ALLOWED)
    assert violations("import subprocess\nimport mcp\n", _ALLOWED)
    assert violations("from mcp import ClientSession\nimport httpx2\n", _ALLOWED) == []
    assert violations("import subprocess\nimport json\n", "app/services/other.py") == []
