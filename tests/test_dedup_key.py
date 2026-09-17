"""PRD-009 STORY-003: `dedup_key(user_id, turns)`, the one definition of "duplicate".

The key is a pure function over a conversation (PRD-009 Section 6.2), and every
property below is one of Section 7 F3's. Nothing in production calls it yet --
STORY-006 wires it into `run_query` -- so these tests are the whole contract
until then. Turns are a local frozen dataclass on purpose: `DedupTurn` is a
structural Protocol, and PRD-010's message model must satisfy it without
importing it (see `test_any_object_with_role_and_content_works`).
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import hashlib
import inspect
import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

import app.services.duplicate_checker as duplicate_checker
from app.services.duplicate_checker import DEDUP_KEY_VERSION, dedup_key, hash_prompt

_JUAN = "juan@empresa.com"
_MARIA = "maria@empresa.com"


@dataclass(frozen=True)
class _Turn:
    role: str
    content: str


def _user(content):
    return _Turn("user", content)


def _assistant(content):
    return _Turn("assistant", content)


def _system(content):
    return _Turn("system", content)


def _framed_sha256(value, ensure_ascii=False):
    """Section 6.2's framing, rebuilt here independently of the module."""
    framed = json.dumps(value, ensure_ascii=ensure_ascii, separators=(",", ":"))
    return hashlib.sha256(framed.encode("utf-8")).hexdigest()


def test_exports_version_v1_and_the_specified_signature():
    assert DEDUP_KEY_VERSION == "v1"
    assert list(inspect.signature(dedup_key).parameters) == ["user_id", "turns"]
    assert isinstance(duplicate_checker.DedupTurn, type)


def test_same_inputs_same_key():
    first = dedup_key(_JUAN, [_user("hi"), _assistant("hello"), _user("yes")])
    second = dedup_key(_JUAN, [_user("hi"), _assistant("hello"), _user("yes")])

    assert first == second


# These digests change only with a deliberate DEDUP_KEY_VERSION bump. They were
# computed from the Section 6.2 formula outside the module, so a framing change
# must fail here -- never "fix" a constant to match the code.
def test_key_for_a_fixed_single_turn_input_is_pinned():
    key = dedup_key(_JUAN, [_user("summarise this week's incidents")])

    assert key == "0b206c744aa7f9f63562d512657e199713e403130a76a0eda9f75c0743484652"


def test_key_for_a_fixed_multi_turn_input_is_pinned():
    key = dedup_key(
        _JUAN,
        [_user("list files"), _assistant("README.md app tests"), _user("yes")],
    )

    assert key == "c63baa9722eff55aed5b2e29db3316b4972843bb43dfb7f7f38cc7068ada4705"


def test_different_user_id_different_key():
    turns = [_user("summarise this week's incidents")]

    assert dedup_key(_JUAN, turns) != dedup_key(_MARIA, turns)


def test_single_turn_differs_from_multi_turn_with_same_last_turn():
    single = dedup_key(_JUAN, [_user("x")])
    multi = dedup_key(_JUAN, [_user("y"), _assistant("z"), _user("x")])

    assert single != multi


def test_different_prefixes_same_last_turn_differ():
    """PRD-009 Section 5, story 5: "yes" means different things in different contexts."""
    greeting = dedup_key(_JUAN, [_user("hi"), _assistant("hello"), _user("yes")])
    listing = dedup_key(_JUAN, [_user("list files"), _assistant("…"), _user("yes")])

    assert greeting != listing


def test_whitespace_is_significant():
    assert dedup_key(_JUAN, [_user("hello world")]) != dedup_key(_JUAN, [_user("hello world ")])


def test_delimiter_injection_does_not_collide():
    injected_left = dedup_key(_JUAN, [_user('a","b'), _user("c")])
    injected_right = dedup_key(_JUAN, [_user("a"), _user('b","c')])

    assert injected_left != injected_right


def test_role_and_content_swap_in_prefix_does_not_collide():
    as_user = dedup_key(_JUAN, [_user("assistant"), _user("x")])
    as_assistant = dedup_key(_JUAN, [_assistant("user"), _user("x")])

    assert as_user != as_assistant


def test_non_ascii_hashes_as_utf8():
    text = "acentuación y emoji 🙂"
    turns = [_user(text), _assistant(text), _user(text)]
    prefix = [["user", text], ["assistant", text]]

    expected = _framed_sha256(
        [DEDUP_KEY_VERSION, _JUAN, hash_prompt(text), _framed_sha256(prefix)]
    )
    escaped = _framed_sha256(
        [
            DEDUP_KEY_VERSION,
            _JUAN,
            hash_prompt(text),
            _framed_sha256(prefix, ensure_ascii=True),
        ],
        ensure_ascii=True,
    )

    assert dedup_key(_JUAN, turns) == expected
    assert dedup_key(_JUAN, turns) != escaped


def test_single_turn_prefix_is_empty_string_and_last_component_is_prompt_hash():
    content = "draft the Q3 vendor summary"
    expected = _framed_sha256([DEDUP_KEY_VERSION, _JUAN, hash_prompt(content), ""])

    assert dedup_key(_JUAN, [_user(content)]) == expected
    # The last-turn component is exactly what audit_logs.prompt_hash stores.
    assert hash_prompt(content) == hashlib.sha256(content.encode("utf-8")).hexdigest()


def test_multi_turn_prefix_component_is_sha256_of_role_content_pairs():
    prefix_hash = _framed_sha256([["user", "y"], ["assistant", "z"]])
    expected = _framed_sha256([DEDUP_KEY_VERSION, _JUAN, hash_prompt("x"), prefix_hash])

    assert dedup_key(_JUAN, [_user("y"), _assistant("z"), _user("x")]) == expected


def test_any_object_with_role_and_content_works():
    """Structural typing: nothing has to import or subclass DedupTurn."""
    namespaced = dedup_key(_JUAN, [SimpleNamespace(role="user", content="x")])

    assert namespaced == dedup_key(_JUAN, [_user("x")])


def test_accepts_any_sequence():
    turns = [_user("y"), _assistant("z"), _user("x")]

    assert dedup_key(_JUAN, tuple(turns)) == dedup_key(_JUAN, turns)


def test_system_turn_is_keyed_in_the_prefix():
    with_system = dedup_key(_JUAN, [_system("a"), _user("x")])

    assert with_system != dedup_key(_JUAN, [_user("x")])


def test_empty_conversation_is_refused():
    with pytest.raises(ValueError, match="at least one turn"):
        dedup_key(_JUAN, [])


@pytest.mark.parametrize("final", [_assistant("done"), _system("be brief")])
def test_final_turn_that_is_not_user_is_refused(final):
    with pytest.raises(ValueError, match="final user turn"):
        dedup_key(_JUAN, [_user("x"), final])


@pytest.mark.parametrize(
    "turns",
    [
        [_Turn("tool", "ls output"), _user("x")],
        [_user("x"), _Turn("tool", "ls output")],
    ],
    ids=["tool-in-prefix", "tool-as-final-turn"],
)
def test_tool_turn_anywhere_is_refused_naming_prd_016(turns):
    with pytest.raises(ValueError, match="PRD-016"):
        dedup_key(_JUAN, turns)


@pytest.mark.parametrize("role", ["function", "User", ""])
def test_unknown_role_is_refused(role):
    with pytest.raises(ValueError, match="no rule for this role"):
        dedup_key(_JUAN, [_Turn(role, "x"), _user("x")])


class _Untouchable:
    def __getattr__(self, name):
        raise AssertionError(f"dedup_key touched the clock: {name}")


def test_is_pure(monkeypatch):
    def _no_storage(*args, **kwargs):
        raise AssertionError("dedup_key touched storage")

    monkeypatch.setattr(duplicate_checker, "find_duplicate_timestamp", _no_storage)
    monkeypatch.setattr(duplicate_checker, "datetime", _Untouchable())

    assert dedup_key(_JUAN, [_user("y"), _assistant("z"), _user("x")])

    source = inspect.getsource(dedup_key)
    assert "settings" not in source
    assert "datetime" not in source
