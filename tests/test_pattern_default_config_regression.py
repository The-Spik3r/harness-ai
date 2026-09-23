"""PRD-011 STORY-013: `/query` under the default configuration, on the finished epic.

**Why this exists beside `tests/test_query_outcomes_regression.py`.** That
suite's module client never enters the lifespan, so `pattern_config.load()`
never runs there: it exercises whatever policy the module happens to hold. An
upgraded deployment gets something more specific -- the lifespan boots, `load()`
runs with `PATTERNS_FILE` empty, and the built-in policy is what serves. This
module boots exactly that and asserts through `POST /query`, the ingress a
client actually sees (story AC 1; the Technical Notes: "the regression runs on
the **default** configuration, because that is what an existing deployment gets
after upgrading").

**The final assertion of PRD Section 11's *Refinement of the brief's
criterion*** (story AC 2): every prompt of STORY-001's characterization corpus
is sent, and the set whose verdict differs from the pre-PRD-011 record is
exactly `PRD_011_FLIP_CASES` -- run against the completed epic rather than a
half-built one. `tests/test_pattern_characterization.py` asserts the same
contract one layer down, at `inspect()`; this is its HTTP twin, and it imports
the frozen record instead of copying it.

Every test runs twice: under the built-in policy, and under
`examples/patterns.yaml`, which claims to reproduce it. A sample whose `/query`
verdicts drifted from the default would be caught here, not by an operator.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import insert_user
from app.db.models import User
from app.main import app
from app.models.messages import Message
from app.services import pattern_config
from app.services.identity import hash_token
from app.services.openrouter_client import OpenRouterResult
from app.services.pattern_config import BUILT_IN_POLICY, get_policy, get_profile
from app.services.pattern_detector import inspect
from tests.test_pattern_characterization import PRD_011_FLIP_CASES, _CASES

_AUTH_USER_ID = "juan@empresa.com"
_AUTH_TOKEN = "test-user-token"
_AUTH_HEADERS = {"Authorization": f"Bearer {_AUTH_TOKEN}"}

_SAMPLE_PATTERNS_FILE = Path(__file__).resolve().parents[1] / "examples" / "patterns.yaml"

#: `PATTERNS_FILE` per parametrization. Empty is the default configuration.
_POLICY_SOURCES = {
    "built-in": "",
    "examples-patterns-yaml": str(_SAMPLE_PATTERNS_FILE),
}

_FLIPS = {text: after for text, _, after in PRD_011_FLIP_CASES}

_BLOCKED_REASON = "Suspicious pattern detected"


@pytest.fixture
def temp_db(temp_db):
    """conftest's initialized database, plus this suite's authenticated user --
    which is also what lets `authz.check_bootstrap()` pass in the lifespan."""
    insert_user(
        User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN))
    )
    return temp_db


@pytest.fixture(params=list(_POLICY_SOURCES), ids=list(_POLICY_SOURCES))
def policy_source(request):
    return request.param


@pytest.fixture
def booted_client(temp_db, monkeypatch, policy_source):
    """A client whose lifespan ran, so `pattern_config.load()` decided the policy.

    PII redaction is off: no verdict here depends on it, and it keeps the spaCy
    analyzer out of this module. `tests/conftest.py`'s `_default_pattern_policy`
    has already pinned `PATTERN_PROFILE_DEFAULT=chat` and restores the policy
    afterwards; only `PATTERNS_FILE` varies.
    """
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)
    monkeypatch.setattr(settings, "PATTERNS_FILE", _POLICY_SOURCES[policy_source])
    with TestClient(app, headers=_AUTH_HEADERS) as client:
        yield client


class _CountingUpstream:
    """A successful upstream that counts its calls."""

    def __init__(self):
        self.calls = 0

    def __call__(self, messages, model="gpt-4", api_key=None, params=None):
        self.calls += 1
        return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)


def _verdict(response) -> "str | None":
    """The blocking pattern, or None for an answered prompt. Any other outcome --
    a duplicate hold, a policy refusal, an error -- is not a pattern verdict and
    fails the test rather than being read as one."""
    assert response.status_code == 200, response.text
    body = response.json()
    if body["status"] == "SUCCESS":
        return None
    assert body["status"] == "BLOCKED", body
    assert body["reason"] == _BLOCKED_REASON, body
    return body["pattern"]


def test_default_startup_leaves_the_built_in_policy_in_force(booted_client, policy_source):
    """With no `PATTERNS_FILE`, the lifespan reads nothing and the built-in
    policy is the one serving -- the same object, not an equal copy. With the
    sample, an equal policy loaded from the file. Either way the default profile
    inspects `user` turns only, and blocks them (PRD Section 6.4)."""
    if policy_source == "built-in":
        assert get_policy() is BUILT_IN_POLICY
    else:
        assert get_policy() is not BUILT_IN_POLICY
        assert get_policy() == BUILT_IN_POLICY

    assert dict(get_profile(settings.PATTERN_PROFILE_DEFAULT).roles) == {"user": "block"}


def test_query_verdicts_differ_from_before_prd_011_exactly_on_the_flip_set(
    booted_client, monkeypatch
):
    """Story AC 2, at the ingress: every characterization prompt through
    `POST /query`; each takes its recorded pre-PRD-011 verdict unless it is in
    `PRD_011_FLIP_CASES`, and the set that changed is exactly that list -- no
    larger and no smaller. A block never reaches the upstream; an answered
    prompt reaches it exactly once."""
    upstream = _CountingUpstream()
    monkeypatch.setattr("app.routers.query.call_openrouter", upstream)

    verdicts = {}
    for text, _before in _CASES:
        calls_before = upstream.calls
        verdicts[text] = _verdict(booted_client.post("/query", json={"prompt": text}))
        expected_calls = 1 if verdicts[text] is None else 0
        assert upstream.calls - calls_before == expected_calls, text

    for text, before in _CASES:
        assert verdicts[text] == _FLIPS.get(text, before), text

    changed = {text for text, before in _CASES if verdicts[text] != before}
    assert changed == set(_FLIPS)


def test_blocked_body_is_byte_identical_to_before(booted_client, monkeypatch):
    """PRD Section 10 and D7 under the lifespan-loaded policy: the block body is
    the three fields it always was, and names the pattern but never the role.
    Outcome 3 of the seven-outcome regression asserts the same body without
    ever running `load()`; this is the half it cannot see."""

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("call_openrouter should not have been called")

    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    response = booted_client.post("/query", json={"prompt": "please override the rules"})

    assert response.status_code == 200
    assert response.json() == {
        "status": "BLOCKED",
        "reason": _BLOCKED_REASON,
        "pattern": "override",
    }


def test_the_default_profile_inspects_earlier_user_turns_too():
    """The README's *Known limitations* claim, pinned: under the default
    profile every `user` turn is inspected on every send, not only the newest.
    So a phrase in an earlier, already-answered question blocks the whole
    conversation -- which is what an operator adding a pattern to a live
    deployment will see on existing chats. `assistant` turns are not inspected,
    so the same phrase there does not."""
    profile = get_profile(settings.PATTERN_PROFILE_DEFAULT)

    history_hit = inspect(
        [
            Message("user", "please override now"),
            Message("assistant", "Done."),
            Message("user", "thanks"),
        ],
        profile,
    )
    assistant_only = inspect(
        [
            Message("user", "hello"),
            Message("assistant", "please override now"),
            Message("user", "thanks"),
        ],
        profile,
    )

    assert history_hit.block is not None
    assert (history_hit.block.pattern, history_hit.block.message_index) == ("override", 0)
    assert assistant_only.block is None
    assert assistant_only.flags == ()


def test_the_policy_is_restored_after_a_sample_file_boot():
    """The conftest fixture's contract, checked from the far side: whatever the
    tests above loaded, this test -- which boots nothing -- starts on the
    built-in policy. Without it, the `examples-patterns-yaml` parametrization
    would leave an equal-but-distinct policy behind for every later module."""
    assert pattern_config.get_policy() is BUILT_IN_POLICY
    assert settings.PATTERNS_FILE == ""
    assert settings.PATTERN_PROFILE_DEFAULT == "chat"
