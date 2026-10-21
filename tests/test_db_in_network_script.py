"""`scripts/test-db-in-network.sh`, checked as text (PRD-014 STORY-008).

The script itself needs Docker, so it is proved by running it (STORY-008
report). What can drift without anyone running it is checked here: the tests it
deselects must still exist and still be `db` tests, it must keep the overrides
that stop an in-container run from reaching the `.env` database, and it must
stay LF so bash can read it on a Windows checkout.
"""

import ast
import re
from pathlib import Path

from tests.conftest import _in_db_nodeids

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "scripts" / "test-db-in-network.sh"


def _deselected() -> list[str]:
    return re.findall(r'--deselect "([^"]+)"', _SCRIPT.read_text(encoding="utf-8"))


def test_every_deselected_test_exists_and_is_a_db_test():
    nodeids = _deselected()
    assert len(nodeids) == 3
    for nodeid in nodeids:
        path, name = nodeid.split("::")
        tree = ast.parse((_ROOT / path).read_text(encoding="utf-8"))
        defined = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        assert name in defined, f"{nodeid} is deselected by the script but no longer exists"
        assert _in_db_nodeids(nodeid), f"{nodeid} is deselected by the script but is not in _DB_NODEIDS"


def test_the_run_overrides_every_inherited_database_setting():
    text = _SCRIPT.read_text(encoding="utf-8")
    assert '-e HARNESS_TEST_LIBSQL_URL="$url"' in text
    assert '-e DATABASE_URL="$url"' in text
    assert "-e TURSO_AUTH_TOKEN= " in text
    assert "--env-file" not in text
    assert "python -m pytest tests/ -m db" in text


def test_the_script_is_lf_only_and_kept_so_by_gitattributes():
    assert b"\r" not in _SCRIPT.read_bytes()
    assert "*.sh text eol=lf" in (_ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
