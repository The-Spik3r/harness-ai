"""PRD-013 STORY-004: `conversation_key(user_id, messages)` (PRD Section 6.3, D2).

A pure function over how a conversation starts, and every property below is
one of Section 7 F4's or of the story's ACs. Nothing in production calls it
yet -- STORY-005 computes it in `run_conversation` and writes it on every
audit arm -- so these tests are the whole contract until then.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import ast
import hashlib
import inspect
import json
from pathlib import Path

import app.services.conversation_key as conversation_key_module
from app.models.messages import Message
from app.services.conversation_key import CONVERSATION_KEY_VERSION, conversation_key

_JUAN = "juan@empresa.com"
_MARIA = "maria@empresa.com"
_MODULE_PATH = Path(conversation_key_module.__file__)


def _user(content):
    return Message("user", content)


def _assistant(content):
    return Message("assistant", content)


def _system(content):
    return Message("system", content)


def _framed_sha256(value, ensure_ascii=False):
    """Section 6.3's framing, rebuilt here independently of the module."""
    framed = json.dumps(value, ensure_ascii=ensure_ascii, separators=(",", ":"))
    return hashlib.sha256(framed.encode("utf-8")).hexdigest()


def test_exports_version_c1_and_the_specified_signature():
    assert CONVERSATION_KEY_VERSION == "c1"
    assert list(inspect.signature(conversation_key).parameters) == ["user_id", "messages"]


def test_key_is_the_framed_hash_of_version_user_system_and_first_user(monkeypatch):
    messages = [_system("sys"), _user("a")]

    assert conversation_key(_JUAN, messages) == _framed_sha256(["c1", _JUAN, "sys", "a"])

    before = conversation_key(_JUAN, messages)
    monkeypatch.setattr(conversation_key_module, "CONVERSATION_KEY_VERSION", "c2")
    assert conversation_key(_JUAN, messages) != before


def test_stable_across_fifty_growing_turns():
    messages = [_system("S"), _user("u0")]
    keys = [conversation_key(_JUAN, messages)]
    for i in range(1, 50):
        messages = messages + [_assistant(f"a{i}"), _user(f"u{i}")]
        keys.append(conversation_key(_JUAN, messages))

    assert len(keys) == 50
    assert sum(1 for m in messages if m.role == "user") == 50
    assert len(set(keys)) == 1


def test_differs_by_user():
    messages = [_system("S"), _user("a")]

    assert conversation_key(_JUAN, messages) != conversation_key(_MARIA, messages)


def test_differs_by_first_user_message():
    assert conversation_key(_JUAN, [_system("S"), _user("a")]) != conversation_key(
        _JUAN, [_system("S"), _user("b")]
    )


def test_differs_by_first_system_message():
    assert conversation_key(_JUAN, [_system("S1"), _user("a")]) != conversation_key(
        _JUAN, [_system("S2"), _user("a")]
    )


def test_no_system_turn():
    single = conversation_key(_JUAN, [_user("a")])

    assert single == conversation_key(_JUAN, [_user("a"), _assistant("b"), _user("c")])
    assert single == _framed_sha256(["c1", _JUAN, "", "a"])


def test_only_the_first_system_and_first_user_count():
    base = conversation_key(_JUAN, [_system("S"), _user("a")])

    assert base == conversation_key(
        _JUAN,
        [_system("S"), _user("a"), _assistant("b"), _system("later"), _user("c")],
    )


def test_field_boundaries_cannot_be_forged():
    assert conversation_key(_JUAN, [_system("ab"), _user("c")]) != conversation_key(
        _JUAN, [_system("a"), _user("bc")]
    )
    assert conversation_key("juan", [_system("xS"), _user("a")]) != conversation_key(
        "juanx", [_system("S"), _user("a")]
    )


def test_non_ascii_is_hashed_as_utf8():
    key = conversation_key(_JUAN, [_user("¿qué?")])

    assert key == _framed_sha256(["c1", _JUAN, "", "¿qué?"])
    assert key != _framed_sha256(["c1", _JUAN, "", "¿qué?"], ensure_ascii=True)


def test_imports_no_settings_and_no_database_module():
    source = _MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported = []
    from_imports = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module)
            from_imports.setdefault(node.module, set()).update(a.name for a in node.names)

    for name in imported:
        assert name != "app.config" and not name.startswith("app.config.")
        assert name != "app.db" and not name.startswith("app.db.")
    assert "import settings" not in source
    # Reused, not copied (story Technical Notes).
    assert "_sha256_json" in from_imports.get("app.services.duplicate_checker", set())
    assert "def _sha256_json" not in source
    assert "json.dumps" not in source


def test_docstring_states_the_three_documented_limits():
    doc = (conversation_key_module.__doc__ or "").lower()

    assert "same" in doc
    assert "/query" in doc
    assert "rewrit" in doc
