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

import copy
import hashlib
import inspect
import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

import app.services.duplicate_checker as duplicate_checker
from app.models.messages import Message, ToolCallSpec
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


# PRD-017 D4 ("unchanged keys"): these literals were computed from the pre-PRD-017
# implementation on 2026-11-15, before dedup_key learned tool turns. Never refresh
# them to match the code: a change here resets every prior 24-hour duplicate window.
_TOOL_FREE_PINS = [
    pytest.param(
        [("system", "be brief"), ("user", "list files")],
        "d30f177a22197275c34ef46081e0a8a974b5ec0acac53b9591e2163fa2bcb53f",
        id="system_user",
    ),
    pytest.param(
        [("system", "be brief"), ("user", "list files"),
         ("assistant", "README.md app tests"), ("user", "yes")],
        "de4af3dcb032b0eb30e0bae5980b11946cadc744894e0c2b8ea14bebf60fb930",
        id="system_multi",
    ),
    pytest.param(
        [("user", "npm test"), ("user", "npm test")],
        "e368c79de34837cbf74126494e6128150557d9bd53dcdd691d302a972d63a226",
        id="user_user",
    ),
    pytest.param(
        [("user", "acentuación y emoji 🙂"), ("assistant", "sí"), ("user", "¿y ahora?")],
        "f7d83fc4992bd88707566e207147f7a74ac64fe842198b12abf94939f7364234",
        id="non_ascii",
    ),
]


@pytest.mark.parametrize("pairs, expected", _TOOL_FREE_PINS)
def test_tool_free_keys_are_pinned_from_prd_009(pairs, expected):
    assert dedup_key(_JUAN, [_Turn(r, c) for r, c in pairs]) == expected


@pytest.mark.parametrize("pairs, expected", _TOOL_FREE_PINS)
def test_message_instances_key_like_role_content_turns(pairs, expected):
    # The real model (tool_calls=(), tool_call_id=None) takes the tool-free branch.
    assert dedup_key(_JUAN, [Message(r, c) for r, c in pairs]) == expected


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


def _call(call_id="c1", name="ls", arguments="{}"):
    return ToolCallSpec(call_id, name, arguments)


def _a_calls(*calls):
    return Message("assistant", "", tuple(calls))


def _tool(call_id, content):
    return Message("tool", content, tool_call_id=call_id)


@pytest.mark.parametrize(
    "turns",
    [
        [_Turn("tool", "ls output"), _user("x")],
        [Message("user", "x"), _a_calls(_call()), _tool("c1", "ls output")],
    ],
    ids=["tool-in-prefix", "tool-as-final-turn"],
)
def test_tool_turns_are_keyed_not_refused(turns):
    # PRD-017 D4 (STORY-006): tool turns are keyed in the prefix, never the anchor; this replaces the PRD-017 refusal (was test_tool_turn_anywhere_is_refused_naming_prd_017).
    key = dedup_key(_JUAN, turns)

    assert len(key) == 64
    assert set(key) <= set("0123456789abcdef")


def test_tool_shaped_conversation_without_a_user_turn_is_refused():
    with pytest.raises(ValueError, match="needs a user turn"):
        dedup_key(_JUAN, [_a_calls(_call()), _tool("c1", "out")])


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


# --- PRD-017 STORY-006: tool turns (D4, Section 6.4) ---


_LS = _call("c1", "ls", "{}")
_LS_OUT = "README.md\nsrc"
_FRAMES = [["assistant", "", [["c1", "ls", "{}"]]], ["tool", _LS_OUT, "c1"]]


def _expected_tool_key(prefix, anchor_text):
    """Section 6.4 rebuilt outside the module: the anchor's slot is null."""
    return _framed_sha256(
        [DEDUP_KEY_VERSION, _JUAN, hash_prompt(anchor_text), _framed_sha256(prefix)]
    )


def _loop_turns():
    return [Message("user", "list files"), _a_calls(_LS), _tool("c1", _LS_OUT)]


def test_tool_shaped_key_is_the_section_6_4_formula():
    # anchor last: [frame(u1), frame(A), frame(T), null]
    key = dedup_key(_JUAN, _loop_turns() + [Message("user", "now run the tests")])
    prefix = [["user", "list files"], *_FRAMES, None]
    assert key == _expected_tool_key(prefix, "now run the tests")
    assert key == "46ac98f59e93155d3117663c87639de6dd96cc5ca179f5b13dda234142f28762"

    # tool final: the anchor is the only user turn: [null, frame(A), frame(T)]
    key = dedup_key(_JUAN, _loop_turns())
    assert key == _expected_tool_key([None, *_FRAMES], "list files")
    assert key == "2d0429e076c98d694359db9c9faef08a1b3aa98db13c54f8c1443f53523b0d36"


def test_tool_turn_is_never_the_anchor():
    key = dedup_key(_JUAN, _loop_turns())

    assert key == _expected_tool_key([None, *_FRAMES], "list files")
    assert key != _expected_tool_key([None, *_FRAMES], _LS_OUT)


def test_assistant_with_empty_tool_calls_frames_as_today():
    with_empty = [Message("user", "x"), Message("assistant", "y", ()), Message("user", "z")]
    plain = [_user("x"), _assistant("y"), _user("z")]

    assert dedup_key(_JUAN, with_empty) == dedup_key(_JUAN, plain)


def test_arguments_are_framed_as_the_raw_string():
    # PRD-017 D13: arguments are never parsed, so "{}" and "{ }" are different bytes.
    def key(arguments):
        return dedup_key(
            _JUAN,
            [Message("user", "x"), _a_calls(_call("c1", "ls", arguments)), _tool("c1", "o")],
        )

    assert key("{}") != key("{ }")
    assert key("{}") == key("{}")


def test_call_order_and_each_call_field_are_keyed():
    def key(*calls):
        answers = [_tool(c.id, "o") for c in calls]
        return dedup_key(_JUAN, [Message("user", "x"), _a_calls(*calls), *answers])

    one, two = _call("c1", "ls", "{}"), _call("c2", "cat", '{"p":1}')
    keys = {
        key(one, two),
        key(two, one),
        key(_call("c9", "ls", "{}"), two),
        key(_call("c1", "pwd", "{}"), two),
        key(_call("c1", "ls", "{ }"), two),
    }

    assert len(keys) == 5


def test_anchor_position_is_marked():
    # PRD-017 Section 6.4, AC3: identical texts, the anchor in a different place.
    first = [Message("user", "u1"), _a_calls(_LS), _tool("c1", _LS_OUT), Message("user", "u2")]
    second = [Message("user", "u1"), Message("user", "u2"), _a_calls(_LS), _tool("c1", _LS_OUT)]

    assert dedup_key(_JUAN, first) != dedup_key(_JUAN, second)


def test_tool_framing_cannot_be_forged_by_tool_free_content():
    real = [Message("user", "u1"), _a_calls(_LS), _tool("c1", _LS_OUT), Message("user", "u2")]
    forged = [
        Message("user", "u1"),
        Message("assistant", '["assistant","",[["c1","ls","{}"]]]'),
        Message("user", '["tool","README.md\\nsrc","c1"]'),
        Message("user", "u2"),
    ]
    null_forged = [Message("user", "null"), Message("user", "u2")]

    assert dedup_key(_JUAN, real) != dedup_key(_JUAN, forged)
    assert dedup_key(_JUAN, real) != dedup_key(_JUAN, null_forged)


_BASH_TEST = '{"command":"npm test"}'
_OUT = "2 tests passed"


def _npm_test_loop():
    """Five requests of one agent loop; r2 and r4 repeat the same command and output."""
    ask = "run the tests, fix the failure, run them again"
    r1 = [Message("system", "be brief"), Message("user", ask)]
    r2 = r1 + [_a_calls(_call("call_0", "bash", _BASH_TEST)), _tool("call_0", _OUT)]
    # id reuse, as some providers do (PRD-017 Section 6.3 rule 3)
    r3 = r2 + [_a_calls(_call("call_0", "edit", '{"path":"src/a.ts"}')), _tool("call_0", "ok")]
    r4 = r3 + [_a_calls(_call("call_0", "bash", _BASH_TEST)), _tool("call_0", _OUT)]
    r5 = r4 + [Message("assistant", "All tests pass."), Message("user", ask)]
    return [r1, r2, r3, r4, r5]


def test_npm_test_twice_in_one_loop_never_shares_a_key():
    loop = _npm_test_loop()

    assert len({dedup_key(_JUAN, r) for r in loop}) == len(loop)


def test_byte_identical_resend_shares_its_key():
    r4 = _npm_test_loop()[3]
    rebuilt = [
        Message(
            m.role, m.content,
            tuple(ToolCallSpec(c.id, c.name, c.arguments) for c in m.tool_calls),
            m.tool_call_id,
        )
        for m in r4
    ]

    assert dedup_key(_JUAN, r4) == dedup_key(_JUAN, copy.deepcopy(r4))
    assert dedup_key(_JUAN, r4) == dedup_key(_JUAN, rebuilt)
