"""The `usage_limit` bubble, criterion by criterion (PRD-013 STORY-014).

One test (or one parametrized pair) per acceptance criterion:

1. A refused send shows exactly one bubble, with the sentence for its limit.
2. A reload restores that bubble with the same text, and does not animate it.
3. Neither the bubble nor the user turn that caused it reaches the next send.
   Driven through the **real pipeline**, with only `call_openrouter` faked, so
   the refusal is the one the gate actually produces.
4. `UsageLimitError` -- the counter could not be read -- still shows the
   existing internal-error bubble, and `pending` is cleared.
5. The rendered copy carries none of the four words the story bans, the bubble
   is wired the way `context_limit`'s is, and STORY-011's interim routing is
   gone.

**Source assertions, read as text, and no in-process import of
`chat_ui.components.*`.** `tests/test_session_rail.py` and
`tests/test_chat_shell.py` both record the reason in their docstrings:
importing the inner package puts it on `sys.path` and breaks every other test
module, which reaches these files by their repo-root path. The build-level
claim -- that the renderer compiles against a Var -- is covered by
`tests/test_chat_components_import.py`'s subprocess probe, which this story
extends rather than duplicates. `tests/test_context_limit_bubble.py` is the
precedent for every structural test below.

Its own small helpers rather than imports from `tests/test_chat_state.py`, the
idiom `tests/test_chat_history_send.py` states: cross-importing between test
modules is not this suite's way.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import re
from pathlib import Path

import pytest

from app.config import settings
from app.db.database import insert_user
from app.db.models import User
from app.models.schemas import QueryBlockedUsageLimitResponse, QuerySuccessResponse
from app.services.identity import hash_token
from app.services.openrouter_client import OpenRouterResult
from app.services.usage_limits import UsageLimitError

import chat_ui.chat_ui.state as chat_state_mod
from chat_ui.chat_ui.formatting import format_usage_limit_notice
from chat_ui.chat_ui.state import ChatState

_AUTH_USER_ID = "juan@empresa.com"
_AUTH_TOKEN = "test-user-token"

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CHAT = _REPO_ROOT / "chat_ui" / "chat_ui" / "components" / "chat.py"
_BUBBLES = _REPO_ROOT / "chat_ui" / "chat_ui" / "components" / "bubbles.py"
_STATE = _REPO_ROOT / "chat_ui" / "chat_ui" / "state.py"

# The kind string, written once here and asserted on both sides of the wire. A
# typo in either place is otherwise a silent fallback bubble.
_KIND = "usage_limit"

# STORY-014 AC 1 and PRD-013 Section 6.10, verbatim.
_TOKENS_SENTENCE = "You've reached today's usage limit. You can send again after 00:00 UTC."
_REQUESTS_SENTENCE = "You're sending too fast. Wait a minute, then send again."

# (limit, maximum, actual, resets_at, the sentence the reader sees)
_REFUSALS = [
    ("tokens", 1000000, 1003412, "2026-10-20T00:00:00Z", _TOKENS_SENTENCE),
    ("requests", 60, 61, "2026-10-19T14:23:00Z", _REQUESTS_SENTENCE),
]
_REFUSAL_IDS = ["tokens", "requests"]


@pytest.fixture
def temp_db(temp_db):
    """conftest's initialized database, plus this suite's authenticated user."""
    insert_user(
        User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN))
    )
    return temp_db


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _make_state() -> ChatState:
    state = ChatState(_reflex_internal_init=True)
    state.user_id = _AUTH_USER_ID
    state._token = _AUTH_TOKEN
    return state


async def _send(state: ChatState, text: str) -> None:
    state.input_text = text
    handler = type(state).event_handlers["send"]
    await handler.fn(state)  # bypasses the background-task chain guard


async def _restore(session_id: str) -> ChatState:
    """A fresh signed-in state showing `session_id` -- the reload, modelled."""
    state = _make_state()
    handler = type(state).event_handlers["select_session"]
    await handler.fn(state, session_id)
    return state


def _stub_pipeline(monkeypatch, fake):
    """One stand-in on both of `_do_send`'s entry points: `run_query` for the
    first send of a chat, `run_conversation` for every later one. Stubbing only
    one would let the other reach the real pipeline."""

    def _via_query(**kwargs):
        return fake()

    def _via_conversation(*args, **kwargs):
        return fake()

    monkeypatch.setattr(chat_state_mod, "run_query", _via_query)
    monkeypatch.setattr(chat_state_mod, "run_conversation", _via_conversation)


def _refusal(limit, maximum, actual, resets_at):
    return QueryBlockedUsageLimitResponse(
        reason="Usage limit reached",
        limit=limit,
        maximum=maximum,
        actual=actual,
        resets_at=resets_at,
    )


def _fake_call_openrouter(messages, model="gpt-4", api_key=None, params=None):
    """A reply that names nothing the prompt said, so a content assertion has to
    come from what was actually sent."""
    return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)


def _capturing_run_conversation(captured):
    """A `run_conversation` stand-in that records the conversation it was handed
    (`tests/test_chat_history_send.py`'s helper of the same name)."""

    def _fake(identity, messages, device, model, openrouter_api_key,
              params=None, call_openrouter=None, session_id=None, ingress=None):
        captured["messages"] = list(messages)
        return QuerySuccessResponse(
            response="ok", audit_id=1, model_used="gpt-4", tokens_used=1
        )

    return _fake


def _renderer_source() -> str:
    """`render_usage_limit`'s body, from its `def` to the next top-level `def`,
    so no assertion can pass because some *other* renderer names the token."""
    source = _BUBBLES.read_text(encoding="utf-8")
    start = source.index("def render_usage_limit(")
    rest = source[start + 1 :]
    end = rest.find("\ndef ")
    assert end != -1, "render_usage_limit is the last top-level def; slice never terminates"
    return rest[:end]


def _usage_arm_source() -> str:
    """`_do_send`'s `QueryBlockedUsageLimitResponse` arm, up to the next branch."""
    source = _STATE.read_text(encoding="utf-8")
    start = source.index("elif isinstance(result, QueryBlockedUsageLimitResponse):")
    rest = source[start + 1 :]
    end = min(i for i in (rest.find("\n            elif "), rest.find("\n            else:")) if i != -1)
    return rest[:end]


# --------------------------------------------------------------------------
# AC 1 -- one bubble, the sentence for its limit
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("limit,maximum,actual,resets_at,expected", _REFUSALS, ids=_REFUSAL_IDS)
async def test_a_refused_send_shows_one_usage_limit_bubble_with_its_sentence(
    temp_db, monkeypatch, limit, maximum, actual, resets_at, expected
):
    _stub_pipeline(monkeypatch, lambda: _refusal(limit, maximum, actual, resets_at))

    state = _make_state()
    await _send(state, "hello world")

    bubble = state.messages[-1]
    assert bubble.kind == _KIND
    assert bubble.detail == expected
    assert bubble.prompt == "hello world"
    assert [m.kind for m in state.messages].count(_KIND) == 1
    # The interim route is gone: a refusal is not a fault.
    assert not any(m.kind == "internal_error" for m in state.messages)
    assert state.pending is False


# --------------------------------------------------------------------------
# AC 2 -- a reload restores the same bubble
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("limit,maximum,actual,resets_at,expected", _REFUSALS, ids=_REFUSAL_IDS)
async def test_a_reload_restores_the_same_bubble_with_the_same_text(
    temp_db, monkeypatch, limit, maximum, actual, resets_at, expected
):
    """Two sends, not one: the first send's user bubble is appended before the
    lazy create and so has no session to be filed under
    (`tests/test_chat_state.py`'s round-trip docstring), but each outcome bubble
    is. `restored` is asserted because `_entry` reads it to keep a rehydrated
    bubble out of the mount animation -- "Switching sessions does not animate"
    (PRD-008 Section 6.1)."""
    _stub_pipeline(monkeypatch, lambda: _refusal(limit, maximum, actual, resets_at))

    state = _make_state()
    await _send(state, "first prompt")
    await _send(state, "second prompt")
    live = [m for m in state.messages if m.kind == _KIND]
    assert len(live) == 2

    restored = [m for m in (await _restore(state.active_session_id)).messages if m.kind == _KIND]

    assert len(restored) == len(live)
    for before, after in zip(live, restored):
        assert after.detail == before.detail == expected
        assert after.content == before.content == "Usage limit reached"
        assert after.prompt == before.prompt
        assert after.restored is True


# --------------------------------------------------------------------------
# AC 3 -- the refused turn never reaches the model
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_neither_the_bubble_nor_its_user_turn_reaches_the_next_send(
    temp_db, monkeypatch
):
    """Through the real pipeline and the real gate; only `call_openrouter` is
    faked, and the capture replaces `run_conversation` only for the last send.

    **The token budget, not the rate.** The rate window is derived from the
    database's clock inside `admit_usage`'s statement, so it cannot be frozen,
    and a minute boundary between two sends would admit the one meant to be
    refused. The budget only rolls over at 00:00 UTC. With a budget of 1, the
    first send is admitted (0 used) and charged 12 tokens, so the second is
    refused with `limit="tokens"`.

    `chat_history.assemble` reads only `assistant` rows, so this holds by
    construction (PRD-010 D4); this is that claim stated from outside.
    """
    monkeypatch.setattr(settings, "USAGE_LIMITS_ENABLED", True)
    monkeypatch.setattr(settings, "USAGE_DAILY_TOKEN_BUDGET", "*=1")
    monkeypatch.setattr(chat_state_mod, "call_openrouter", _fake_call_openrouter)
    refused = "the refused question"

    state = _make_state()
    await _send(state, "an answered question")
    assert state.messages[-1].kind == "assistant"
    await _send(state, refused)
    assert state.messages[-1].kind == _KIND
    assert state.messages[-1].detail == _TOKENS_SENTENCE

    captured = {}
    monkeypatch.setattr(chat_state_mod, "run_conversation", _capturing_run_conversation(captured))
    await _send(state, "a fresh question")

    contents = [message.content for message in captured["messages"]]
    assert not any(refused in content for content in contents)
    assert not any(_TOKENS_SENTENCE in content for content in contents)
    assert not any("Usage limit reached" in content for content in contents)
    assert contents.count("an answered question") == 1
    last = captured["messages"][-1]
    assert (last.role, last.content) == ("user", "a fresh question")


# --------------------------------------------------------------------------
# AC 4 -- a counter that cannot be read is a fault, shown as one
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_usage_limit_error_shows_the_internal_error_bubble_and_clears_pending(
    temp_db, monkeypatch
):
    def _raise():
        raise UsageLimitError("Usage admission failed: counter unreachable")

    _stub_pipeline(monkeypatch, _raise)

    state = _make_state()
    await _send(state, "hello world")

    bubble = state.messages[-1]
    assert bubble.kind == "internal_error"
    assert bubble.content == "internal_error"
    assert bubble.detail == "Usage admission failed: counter unreachable"
    assert not any(m.kind == _KIND for m in state.messages)
    assert state.pending is False


# --------------------------------------------------------------------------
# AC 5 -- the copy, the wiring, and the interim routing gone
# --------------------------------------------------------------------------


@pytest.mark.parametrize("limit,maximum,actual,resets_at,expected", _REFUSALS, ids=_REFUSAL_IDS)
def test_the_rendered_copy_never_says_rate_limit_quota_sorry_or_oops(
    limit, maximum, actual, resets_at, expected
):
    """The sentence as the bubble draws it -- built by the same call `_do_send`
    makes -- and the tag above it."""
    from chat_ui.chat_ui.copy import TAG_USAGE_LIMIT

    rendered = format_usage_limit_notice(limit, resets_at)
    assert rendered == expected, "positive control: the sentence under test is the real one"

    for text in (rendered, TAG_USAGE_LIMIT):
        lowered = text.lower()
        for banned in ("rate limit", "quota exceeded", "sorry", "oops"):
            assert banned not in lowered, f"{text!r} contains {banned!r}"


def test_the_match_has_a_usage_limit_arm_above_the_default():
    """A distinct arm, and reached before the fallback: a membership check would
    pass on an arm written below `render_fallback` and never reached."""
    source = _CHAT.read_text(encoding="utf-8")

    arm = f'("{_KIND}", render_usage_limit(message))'
    assert arm in source, f"message_bubble has no {_KIND} arm"
    default = "render_fallback(message)"
    assert default in source, "the default arm is gone; rx.match would raise on an unknown kind"
    assert source.index(arm) < source.rindex(default), (
        f"the {_KIND} arm is written after the default arm, so it is unreachable"
    )
    assert "render_usage_limit," in source, "render_usage_limit is not in chat.py's import block"


def test_the_kind_string_matches_the_bubble_state_builds():
    assert f'("{_KIND}"' in _CHAT.read_text(encoding="utf-8")
    assert f'kind="{_KIND}"' in _STATE.read_text(encoding="utf-8")


def test_the_usage_limit_bubble_draws_only_contrast_covered_tokens():
    """Plan D-B: the reused pair is one the contrast suite asserts. `_INK_ON_TINT`
    is imported rather than restated, so the two cannot drift apart."""
    from tests.test_contrast import _INK_ON_TINT

    drawn = set(re.findall(r"theme\.((?:INK|TINT)_[A-Z_]+)", _renderer_source()))
    assert drawn == {"INK_HELD", "TINT_HELD"}, f"the bubble draws tokens beyond the reused pair: {sorted(drawn)}"
    assert ("INK_HELD", "TINT_HELD") in _INK_ON_TINT


def test_the_usage_limit_bubble_writes_no_user_facing_literal():
    """Every word the reader sees resolves from `copy.py`: the tag by name, the
    sentence through `message.detail`, which `_do_send` builds from
    `copy.USAGE_LIMIT_NOTICES`. Asserted on the values, because a pasted
    literal is invisible in a diff that also adds the constant."""
    from chat_ui.chat_ui import copy

    body = _renderer_source()
    whole_file = _BUBBLES.read_text(encoding="utf-8")

    assert "copy.TAG_USAGE_LIMIT" in body
    assert "message.detail" in body
    assert "_action(" not in body, "the bubble offers no retry (plan D-C)"

    for value in (
        copy.TAG_USAGE_LIMIT,
        copy.USAGE_LIMIT_TOKENS_TEMPLATE,
        copy.USAGE_LIMIT_REQUESTS_NOTICE,
        _TOKENS_SENTENCE,
    ):
        assert value not in whole_file, f"{value!r} is inlined in bubbles.py as a literal"


def test_the_interim_routing_story_011_added_is_gone():
    """STORY-011 routed the refusal through `internal_error` "until STORY-014".
    That arm now builds the `usage_limit` bubble and nothing else."""
    source = _STATE.read_text(encoding="utf-8")
    arm = _usage_arm_source()

    assert "Interim (PRD-013 STORY-011)" not in source
    assert "until STORY-014" not in source
    assert f'kind="{_KIND}"' in arm
    assert "internal_error" not in arm, "the usage-limit arm still builds an internal-error bubble"
    assert "format_usage_limit_notice(" in arm
