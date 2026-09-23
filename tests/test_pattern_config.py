"""PRD-011 STORY-005: the built-in policy, YAML loading and startup validation.

This module covers `app/services/pattern_config.py` and only it: the policy
model, the seven built-in patterns split into two lists, `load()`'s wholesale
replacement, and one case per malformed-file rule.

What it deliberately does **not** cover:

- the `roles:` vocabulary, the empty-`roles:` rule, `PATTERN_PROFILE_DEFAULT`'s
  cross-check and `get_profile()` -- STORY-006, in depth in
  `tests/test_pattern_profiles.py`. This module carries one table row per
  roles rule so the file-path check below covers them too;
- the message walk, short-circuiting and the per-message scan ceiling --
  `inspect()` in STORY-008.

The built-in policy's *verdicts* are asserted against
`tests/test_pattern_characterization.py`'s pinned corpus (AC 1) with a local
walker, not with `inspect()`, for the same reason STORY-003 proved its scope AC
with a local helper: the real walk belongs to a story that has not happened
yet, and shipping half of it here would be shipping policy this story does not
own.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import re
from pathlib import Path

import pytest

import app.services.pattern_config as pattern_config
from app.config import settings
from app.services.pattern_config import (
    BUILT_IN_POLICY,
    PatternConfigError,
    PatternList,
    PatternPolicy,
    Profile,
    get_policy,
    load,
)
from app.models.messages import Message
from app.services.pattern_detector import (
    PatternCompileError,
    inspect,
    strip_code_spans,
)

# The corpus STORY-001 pinned, imported rather than copied. The coupling is
# deliberate: a hand-copied corpus is one that drifts from the pinned one, and
# AC 1 is a claim about *that* corpus. `tests/test_pattern_characterization.py`
# already uses the same instrument on itself
# (`test_every_flip_case_is_a_pinned_case`). Both names are private to that
# module; reaching across for them is the point, not an oversight.
from tests.test_pattern_characterization import PRD_011_FLIP_CASES, _CASES


@pytest.fixture
def _reset_policy():
    """Restore the module-level policy after a test rebinds it.

    `tests/test_authz.py`'s `_reset_role_permissions`, for the same reason: one
    test's `load()` must not be the next test's starting policy.
    """
    original = pattern_config._policy
    yield
    pattern_config._policy = original


@pytest.fixture(autouse=True)
def _default_profile_is_chat(monkeypatch):
    """PRD-011 STORY-006: `load()` now cross-checks `PATTERN_PROFILE_DEFAULT`
    against the profiles it installs, so every successful load below depends on
    it naming `chat` -- pinned here so a developer's `.env` cannot decide it."""
    monkeypatch.setattr(settings, "PATTERN_PROFILE_DEFAULT", "chat")


def _write(tmp_path, text: str) -> str:
    path = tmp_path / "patterns.yaml"
    path.write_text(text, encoding="utf-8")
    return str(path)


_VALID_FILE = """
lists:
  only:
    match: word
    scope: everywhere
    patterns:
      - hello there
profiles:
  chat:
    lists: [only]
    roles:
      user: block
"""


# --- AC 1: the built-in policy ---------------------------------------------


def test_load_is_noop_when_patterns_file_unset(monkeypatch, _reset_policy):
    """An empty setting reads no file at all -- not a file that happens to be
    missing, and not a default path (AC 1)."""
    monkeypatch.setattr(settings, "PATTERNS_FILE", "")

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("read_text should not be called when PATTERNS_FILE is empty")

    monkeypatch.setattr(Path, "read_text", _fail_if_called)

    assert load() is None
    assert get_policy() is BUILT_IN_POLICY


def test_built_in_lists_hold_exactly_todays_seven_patterns():
    """AC 1: "whose lists together hold exactly today's seven patterns".

    PRD-011 STORY-008 deleted the pre-PRD-011 constant this used to compare
    against, and rewrote the assertion against the literal seven, as this
    docstring said it would.
    """
    policy = get_policy()
    configured = [pattern for pattern_list in policy.lists.values() for pattern in pattern_list.patterns]

    assert len(configured) == 7
    assert sorted(configured) == sorted(
        [
            "ignore previous instructions",
            "forget everything",
            "show system prompt",
            "reveal password",
            "execute code",
            "admin mode",
            "override",
        ]
    )


def test_built_in_lists_are_the_two_of_prd_section_6_3():
    """The split is decision D3, and the scopes are the reason it exists."""
    policy = get_policy()

    assert list(policy.lists) == ["injection", "keywords"]

    injection = policy.lists["injection"]
    assert injection.match == "word"
    # `everywhere`: an injection phrase counts inside a code fence too, which is
    # what stops a fence being used to hide one (PRD Section 9.2, T6).
    assert injection.scope == "everywhere"
    assert injection.patterns == (
        "ignore previous instructions",
        "forget everything",
        "show system prompt",
        "reveal password",
    )

    keywords = policy.lists["keywords"]
    assert keywords.match == "word"
    # `outside_code`: these three are ordinary vocabulary in source.
    assert keywords.scope == "outside_code"
    # Order, not membership. "admin mode" precedes "override", which is the
    # whole of the list-order precedence case pinned in the characterization
    # module -- a set assertion here would let a reorder pass and flip that row.
    assert keywords.patterns == ("execute code", "admin mode", "override")


def test_built_in_patterns_are_compiled_tuples():
    for pattern_list in get_policy().lists.values():
        assert isinstance(pattern_list.patterns, tuple)
        assert isinstance(pattern_list.compiled, tuple)
        assert len(pattern_list.compiled) == len(pattern_list.patterns)
        assert all(isinstance(compiled, re.Pattern) for compiled in pattern_list.compiled)


def _verdict(text: str) -> str | None:
    """What the built-in policy reports for one message's text: the `chat`
    profile's blocking pattern for one `user` turn, or None.

    This was a local stand-in for `inspect()` until STORY-008 shipped it.
    PRD-011 STORY-008: it now delegates, so AC 1's parity check runs over the
    real walk rather than a copy of it.
    """
    result = inspect([Message("user", text)], get_policy().profiles["chat"])
    return result.block.pattern if result.block is not None else None

_FLIPS = {text: after for text, _, after in PRD_011_FLIP_CASES}

_PARITY_CASES = [(text, _FLIPS.get(text, today), text in _FLIPS) for text, today in _CASES]

_PARITY_IDS = [
    f"{'flip' if flipped else 'same'}-{index}" for index, (_, _, flipped) in enumerate(_PARITY_CASES)
]


@pytest.mark.parametrize("text, expected, flipped", _PARITY_CASES, ids=_PARITY_IDS)
def test_built_in_policy_matches_the_characterization_corpus(text, expected, flipped):
    """AC 1: today's verdict for every case outside STORY-001's flip set, and
    the declared *after* verdict for every case inside it.

    The flip rows are asserted here rather than left to STORY-008 because one
    of them -- the fenced `@Override` case -- is a *prediction* that
    `PRD_011_FLIP_CASES` explicitly makes conditional on this story:
    "this row depends on STORY-005 giving the built-in `keywords` list
    `scope: outside_code`". This is where that debt is paid or defaulted on.
    """
    assert _verdict(text) == expected


def test_get_policy_returns_the_built_in_policy_without_load():
    """AC 5: no `load()`, no raise -- the built-in policy stands on its own,
    exactly as `authz.ROLE_PERMISSIONS` does before `authz.load()` runs."""
    assert get_policy() is BUILT_IN_POLICY
    assert isinstance(get_policy(), PatternPolicy)


def test_a_failed_load_leaves_the_previous_policy_in_force(tmp_path, monkeypatch, _reset_policy):
    """Nothing is rebound until every rule has passed, so a broken file cannot
    leave a half-applied policy behind (the reason `_policy` is assigned last)."""
    monkeypatch.setattr(settings, "PATTERNS_FILE", _write(tmp_path, "lists: {}\nprofiles: {}\n"))

    with pytest.raises(PatternConfigError):
        load()

    assert get_policy() is BUILT_IN_POLICY


# --- AC 2: wholesale replacement, compiled once ----------------------------


def test_load_replaces_the_policy_wholesale(tmp_path, monkeypatch, _reset_policy):
    """AC 2, stated as "a list present in the built-in policy and absent from
    the file is gone". No merge: an operator who deletes a pattern from their
    file must not still have it in force."""
    monkeypatch.setattr(settings, "PATTERNS_FILE", _write(tmp_path, _VALID_FILE))

    load()
    policy = get_policy()

    assert set(policy.lists) == {"only"}
    assert "injection" not in policy.lists
    assert "keywords" not in policy.lists
    assert set(policy.profiles) == {"chat"}
    assert policy.profiles["chat"].lists == (policy.lists["only"],)


def test_load_compiles_every_pattern_once_at_load(tmp_path, monkeypatch, _reset_policy):
    """AC 2: "every pattern is compiled once, at load, with `compile_pattern`".

    The spy counts calls, which is what distinguishes "compiled at load" from
    "compiled on first use" -- the second would pass an isinstance check and
    still put a compile on the request path.
    """
    calls = []
    real = pattern_config.compile_pattern

    def _counting_compile(pattern, match):
        calls.append((pattern, match))
        return real(pattern, match)

    monkeypatch.setattr(pattern_config, "compile_pattern", _counting_compile)
    monkeypatch.setattr(
        settings,
        "PATTERNS_FILE",
        _write(
            tmp_path,
            """
lists:
  a:
    match: word
    scope: everywhere
    patterns: [one, two]
  b:
    match: word
    scope: outside_code
    patterns: [three]
profiles:
  chat:
    lists: [a, b]
    roles: {user: block}
""",
        ),
    )
    # PRD-011 STORY-006: `roles:` is now required and the profile must be the
    # pinned default -- the fixture changed, not what this test asserts.

    load()

    assert calls == [("one", "word"), ("two", "word"), ("three", "word")]

    policy = get_policy()
    for pattern_list in policy.lists.values():
        assert all(isinstance(compiled, re.Pattern) for compiled in pattern_list.compiled)
        assert len(pattern_list.compiled) == len(pattern_list.patterns)

    get_policy()
    get_policy()
    assert len(calls) == 3


def test_declared_order_survives_parsing(tmp_path, monkeypatch, _reset_policy):
    """Lists in declared order, patterns in declared order, both as tuples.

    Deliberately non-alphabetical: `yaml.safe_load` preserves mapping order,
    and the tuples are what stop anything downstream reordering them
    (PRD Section 6.2, F5).
    """
    monkeypatch.setattr(
        settings,
        "PATTERNS_FILE",
        _write(
            tmp_path,
            """
lists:
  zebra:
    match: word
    scope: everywhere
    patterns: [zulu, alpha, mike]
  alpha:
    match: word
    scope: everywhere
    patterns: [yankee]
profiles:
  chat:
    lists: [zebra, alpha]
    roles: {user: block}
""",
        ),
    )
    # PRD-011 STORY-006: `roles:` is now required and the profile must be the
    # pinned default, so `p` became `chat` -- the order assertions are unchanged.

    load()
    policy = get_policy()

    assert list(policy.lists) == ["zebra", "alpha"]
    assert policy.lists["zebra"].patterns == ("zulu", "alpha", "mike")
    assert isinstance(policy.lists["zebra"].patterns, tuple)
    assert [pattern_list.name for pattern_list in policy.profiles["chat"].lists] == [
        "zebra",
        "alpha",
    ]


def test_profile_lists_are_resolved_objects_not_names(tmp_path, monkeypatch, _reset_policy):
    """Resolved at load, so an undefined name is a startup error and can never
    be a request-time KeyError (PRD Section 7/F4)."""
    monkeypatch.setattr(settings, "PATTERNS_FILE", _write(tmp_path, _VALID_FILE))

    load()
    policy = get_policy()

    (resolved,) = policy.profiles["chat"].lists
    assert isinstance(resolved, PatternList)
    assert resolved is policy.lists["only"]


def test_roles_are_validated_at_load(tmp_path, monkeypatch, _reset_policy):
    """The STORY-005/STORY-006 boundary, now crossed.

    PRD-011 STORY-006 AC 2: rewritten in place. This was
    `test_roles_are_stored_but_not_validated_here` and asserted that
    `martian: incinerate` loaded; the same file now fails startup naming the
    profile and the role. Coverage in depth -- every rule, every accepted
    role and action -- is `tests/test_pattern_profiles.py`.
    """
    monkeypatch.setattr(
        settings,
        "PATTERNS_FILE",
        _write(
            tmp_path,
            """
lists:
  only:
    match: word
    scope: everywhere
    patterns: [hello]
profiles:
  p:
    lists: [only]
    roles:
      martian: incinerate
""",
        ),
    )

    with pytest.raises(PatternConfigError) as exc_info:
        load()

    message = str(exc_info.value)
    assert "profile 'p'" in message
    assert "'martian'" in message
    assert get_policy() is BUILT_IN_POLICY


def test_the_built_in_profiles_carry_the_section_6_4_matrix():
    """A smoke assertion kept from STORY-005 so the maps are never invented
    twice. The matrix is asserted cell by cell -- the four "not inspected"
    cells included -- in `tests/test_pattern_profiles.py` (PRD-011 STORY-006
    AC 1)."""
    policy = get_policy()

    assert [pattern_list.name for pattern_list in policy.profiles["chat"].lists] == [
        "injection",
        "keywords",
    ]
    assert policy.profiles["chat"].roles == {"user": "block"}
    assert [pattern_list.name for pattern_list in policy.profiles["code"].lists] == ["injection"]
    assert policy.profiles["code"].roles == {"user": "block", "tool": "flag"}


# --- AC 3: one case per malformed-file rule --------------------------------

#: (id, file body, substrings the message must contain). One row per rule named
#: in AC 3. Asserted on substrings rather than whole messages: the wording must
#: stay editable, the named offender must not.
_MALFORMED_CASES = [
    (
        "unparseable-yaml",
        "lists:\n  - [unbalanced\n",
        ["PATTERNS_FILE", "parse"],
    ),
    ("not-a-mapping-empty", "", ["document", "mapping"]),
    ("not-a-mapping-scalar", "hello", ["document", "mapping"]),
    (
        "missing-lists",
        "profiles:\n  p:\n    lists: [k]\n",
        ["document", "missing key", "lists"],
    ),
    (
        "missing-profiles",
        "lists:\n  k:\n    match: word\n    scope: everywhere\n    patterns: [x]\n",
        ["document", "missing key", "profiles"],
    ),
    (
        "empty-lists",
        "lists: {}\nprofiles:\n  p:\n    lists: [k]\n",
        ["lists", "empty"],
    ),
    (
        "empty-profiles",
        "lists:\n  k:\n    match: word\n    scope: everywhere\n    patterns: [x]\nprofiles: {}\n",
        ["profiles", "empty"],
    ),
    (
        "unknown-top-level-key",
        "list:\n  k: 1\n",
        ["document", "unknown key", "'list'"],
    ),
    (
        "unknown-list-key",
        "lists:\n  keywords:\n    mach: word\n    scope: everywhere\n    patterns: [x]\n"
        "profiles:\n  p:\n    lists: [keywords]\n",
        ["list 'keywords'", "unknown key", "'mach'", "match"],
    ),
    (
        "missing-list-key",
        "lists:\n  keywords:\n    match: word\n    patterns: [x]\nprofiles:\n  p:\n    lists: [keywords]\n",
        ["list 'keywords'", "missing key", "'scope'"],
    ),
    (
        "unknown-match",
        "lists:\n  keywords:\n    match: words\n    scope: everywhere\n    patterns: [x]\n"
        "profiles:\n  p:\n    lists: [keywords]\n",
        ["list 'keywords'", "unknown match", "'words'", "word", "regex"],
    ),
    (
        "unknown-scope",
        "lists:\n  keywords:\n    match: word\n    scope: outside-code\n    patterns: [x]\n"
        "profiles:\n  p:\n    lists: [keywords]\n",
        ["list 'keywords'", "unknown scope", "'outside-code'", "outside_code"],
    ),
    (
        "empty-patterns",
        "lists:\n  keywords:\n    match: word\n    scope: everywhere\n    patterns: []\n"
        "profiles:\n  p:\n    lists: [keywords]\n",
        ["list 'keywords'", "patterns is empty"],
    ),
    (
        "patterns-not-a-list",
        "lists:\n  keywords:\n    match: word\n    scope: everywhere\n    patterns: override\n"
        "profiles:\n  p:\n    lists: [keywords]\n",
        ["list 'keywords'", "patterns must be a list"],
    ),
    (
        "unknown-profile-key",
        "lists:\n  k:\n    match: word\n    scope: everywhere\n    patterns: [x]\n"
        "profiles:\n  chat:\n    list: [k]\n",
        ["profile 'chat'", "unknown key", "'list'", "lists"],
    ),
    (
        "profile-missing-lists",
        "lists:\n  k:\n    match: word\n    scope: everywhere\n    patterns: [x]\n"
        "profiles:\n  chat:\n    roles:\n      user: block\n",
        ["profile 'chat'", "missing key", "'lists'"],
    ),
    (
        # PRD-011 STORY-006: `roles:` added. `roles` is now a required key and
        # would otherwise fail first, so the row would stop testing its id.
        "undefined-list-in-profile",
        "lists:\n  keywords:\n    match: word\n    scope: everywhere\n    patterns: [x]\n"
        "profiles:\n  chat:\n    lists: [keyword]\n    roles:\n      user: block\n",
        ["profile 'chat'", "undefined list", "'keyword'", "keywords"],
    ),
    # PRD-011 STORY-006 AC 2 and T5: one row per roles rule, so the file-path
    # check below covers them. In depth in tests/test_pattern_profiles.py.
    (
        "missing-roles",
        "lists:\n  k:\n    match: word\n    scope: everywhere\n    patterns: [x]\n"
        "profiles:\n  chat:\n    lists: [k]\n",
        ["profile 'chat'", "missing key", "'roles'"],
    ),
    (
        "empty-roles",
        "lists:\n  k:\n    match: word\n    scope: everywhere\n    patterns: [x]\n"
        "profiles:\n  chat:\n    lists: [k]\n    roles: {}\n",
        ["profile 'chat'", "roles is empty"],
    ),
    (
        "null-roles",
        "lists:\n  k:\n    match: word\n    scope: everywhere\n    patterns: [x]\n"
        "profiles:\n  chat:\n    lists: [k]\n    roles:\n",
        ["profile 'chat'", "roles is empty"],
    ),
    (
        "roles-not-a-mapping",
        "lists:\n  k:\n    match: word\n    scope: everywhere\n    patterns: [x]\n"
        "profiles:\n  chat:\n    lists: [k]\n    roles: [user]\n",
        ["profile 'chat'", "roles must be a mapping"],
    ),
    (
        "unknown-role",
        "lists:\n  k:\n    match: word\n    scope: everywhere\n    patterns: [x]\n"
        "profiles:\n  chat:\n    lists: [k]\n    roles:\n      admin: block\n",
        ["profile 'chat'", "unknown role", "'admin'", "assistant, system, tool, user"],
    ),
    (
        "unknown-action",
        "lists:\n  k:\n    match: word\n    scope: everywhere\n    patterns: [x]\n"
        "profiles:\n  chat:\n    lists: [k]\n    roles:\n      user: deny\n",
        ["profile 'chat'", "'user'", "unknown action", "'deny'", "block, flag"],
    ),
]

_MALFORMED_IDS = [case_id for case_id, _, _ in _MALFORMED_CASES]


@pytest.mark.parametrize(
    "body, expected_substrings",
    [(body, expected) for _, body, expected in _MALFORMED_CASES],
    ids=_MALFORMED_IDS,
)
def test_malformed_file_raises_naming_the_offender(
    body, expected_substrings, tmp_path, monkeypatch, _reset_policy
):
    """AC 3: every rule raises `PatternConfigError`, and the message names the
    offending list or profile and the rule that failed."""
    monkeypatch.setattr(settings, "PATTERNS_FILE", _write(tmp_path, body))

    with pytest.raises(PatternConfigError) as exc_info:
        load()

    message = str(exc_info.value)
    for expected in expected_substrings:
        assert expected in message, f"{expected!r} missing from: {message}"


def test_missing_file_raises_naming_the_path(tmp_path, monkeypatch, _reset_policy):
    """AC 3's first rule. Separate from the table because there is no file to
    write -- the whole point is that the path does not resolve."""
    missing = tmp_path / "does-not-exist.yaml"
    monkeypatch.setattr(settings, "PATTERNS_FILE", str(missing))

    with pytest.raises(PatternConfigError) as exc_info:
        load()

    message = str(exc_info.value)
    assert "PATTERNS_FILE" in message
    assert str(missing) in message


def test_every_malformed_case_names_the_file_path(tmp_path, monkeypatch, _reset_policy):
    """The path is in every message, not just some.

    An operator debugging a failed boot has a path in an environment variable
    and a traceback in a log; a message that names the rule but not the file
    makes them join the two by hand -- which is why `authz.py`'s messages all
    carry `RBAC_ROLES_FILE`'s path.
    """
    for case_id, body, _ in _MALFORMED_CASES:
        path = _write(tmp_path, body)
        monkeypatch.setattr(settings, "PATTERNS_FILE", path)

        with pytest.raises(PatternConfigError) as exc_info:
            load()

        assert path in str(exc_info.value), f"{case_id} does not name the file"


# --- AC 4: the regex gate and the ReDoS heuristic --------------------------

# PRD-011 STORY-006: `p` became `chat` with a `roles:` map -- `roles` is now
# required and the profile must be the pinned default for the success case.
_REGEX_FILE = """
lists:
  risky:
    match: regex
    scope: everywhere
    patterns: ['%s']
profiles:
  chat:
    lists: [risky]
    roles: {user: block}
"""


def test_regex_list_is_refused_while_the_setting_is_false(tmp_path, monkeypatch, _reset_policy):
    """AC 4: refused outright, and the message names the setting to change.

    Off by default is the first of the four ReDoS layers, and the error has to
    be actionable -- an operator who wanted a regex list needs to be told which
    switch they are missing, not just that regex is unavailable.
    """
    monkeypatch.setattr(settings, "PATTERNS_ALLOW_REGEX", False)
    monkeypatch.setattr(settings, "PATTERNS_FILE", _write(tmp_path, _REGEX_FILE % r"overrid\w*"))

    with pytest.raises(PatternConfigError) as exc_info:
        load()

    message = str(exc_info.value)
    assert "risky" in message
    assert "PATTERNS_ALLOW_REGEX=true" in message


def test_word_lists_are_unaffected_by_the_regex_setting(tmp_path, monkeypatch, _reset_policy):
    """The gate is per list and on `match: regex` only -- a `word` list loads
    with the setting false, which is the default every deployment runs."""
    monkeypatch.setattr(settings, "PATTERNS_ALLOW_REGEX", False)
    monkeypatch.setattr(settings, "PATTERNS_FILE", _write(tmp_path, _VALID_FILE))

    load()

    assert set(get_policy().lists) == {"only"}


def test_regex_list_loads_when_the_setting_is_true(tmp_path, monkeypatch, _reset_policy):
    monkeypatch.setattr(settings, "PATTERNS_ALLOW_REGEX", True)
    monkeypatch.setattr(settings, "PATTERNS_FILE", _write(tmp_path, _REGEX_FILE % r"overrid\w*"))

    load()
    risky = get_policy().lists["risky"]

    assert risky.match == "regex"
    assert len(risky.compiled) == 1
    # The stem a deployment writes when it wants the substring behaviour word
    # matching gave up (PRD Section 9.2, T3).
    assert risky.compiled[0].search("overridden") is not None


def test_uncompilable_regex_raises_naming_the_list_and_the_pattern(
    tmp_path, monkeypatch, _reset_policy
):
    """AC 4, and the two-exception seam.

    `compile_pattern` raises `PatternCompileError`, which names the pattern but
    cannot name the list -- `pattern_detector` is pure and does not know where a
    pattern came from. `load()` catches it and re-raises with the list attached.
    `__cause__` is asserted because that chain is the whole reason two exception
    types exist, and a bare `raise` would lose it.
    """
    monkeypatch.setattr(settings, "PATTERNS_ALLOW_REGEX", True)
    monkeypatch.setattr(settings, "PATTERNS_FILE", _write(tmp_path, _REGEX_FILE % "[unclosed"))

    with pytest.raises(PatternConfigError) as exc_info:
        load()

    message = str(exc_info.value)
    assert "risky" in message
    assert "[unclosed" in message
    assert isinstance(exc_info.value.__cause__, PatternCompileError)


def test_nested_quantifier_regex_raises_naming_the_list_and_the_pattern(
    tmp_path, monkeypatch, _reset_policy
):
    """AC 4: the startup heuristic, layer three of four.

    It is a heuristic for the common catastrophic shape and not a proof of
    linear-time matching -- the real protection is that regex is off unless a
    deployment deliberately turns it on.
    """
    monkeypatch.setattr(settings, "PATTERNS_ALLOW_REGEX", True)
    monkeypatch.setattr(settings, "PATTERNS_FILE", _write(tmp_path, _REGEX_FILE % "(a+)+b"))

    with pytest.raises(PatternConfigError) as exc_info:
        load()

    message = str(exc_info.value)
    assert "risky" in message
    assert "(a+)+b" in message
    assert "nested quantifier" in message


# --- The module's own shape ------------------------------------------------


def test_policy_objects_are_frozen():
    """Frozen dataclasses: the policy cannot be edited in place after load.

    Not deep immutability, and not meant to be -- PRD Section 6.2 specifies
    `Mapping`. What must not be reorderable is declared order, and that lives
    in the tuples.
    """
    policy = get_policy()

    with pytest.raises(Exception):
        policy.lists = {}
    with pytest.raises(Exception):
        policy.lists["injection"].scope = "everywhere"
    with pytest.raises(Exception):
        policy.profiles["chat"].name = "other"

    assert isinstance(policy.profiles["chat"], Profile)


def test_load_reads_the_file_once_not_per_get_policy(tmp_path, monkeypatch, _reset_policy):
    """`get_policy()` is on the request path (STORY-008) and must never touch
    the disk. `tests/test_authz.py` holds `authorize()` to the same rule."""
    path = _write(tmp_path, _VALID_FILE)
    monkeypatch.setattr(settings, "PATTERNS_FILE", path)

    reads = []
    real_read_text = Path.read_text

    def _counting_read_text(self, *args, **kwargs):
        reads.append(str(self))
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _counting_read_text)

    load()
    for _ in range(5):
        get_policy()

    assert reads.count(path) == 1


# --- STORY-007: examples/patterns.yaml is loaded, not merely documented -----

#: The shipped sample -- PRD-011 Section 6.3, byte for byte.
_SAMPLE_FILE = Path(__file__).resolve().parents[1] / "examples" / "patterns.yaml"


def test_examples_patterns_yaml_loads_to_the_built_in_policy(monkeypatch, _reset_policy):
    """PRD-011 STORY-007 AC 3 and Section 11's quality indicator: "a sample
    that does not parse is worse than no sample".

    Equality with `BUILT_IN_POLICY` is also the drift guard: the PRD's Section
    6.3, the shipped sample and `_build_built_in()` are three copies of one
    policy, and this is the test that notices when one of them moves. Dict
    `==` ignores key order, so declared order is asserted separately -- it is
    load-bearing for `inspect()`'s reporting order (Section 7/F5).
    """
    monkeypatch.setattr(settings, "PATTERNS_FILE", str(_SAMPLE_FILE))

    load()
    policy = get_policy()

    # A file was actually read and a new policy built -- otherwise the
    # equality below would be trivially true.
    assert policy is not BUILT_IN_POLICY
    assert policy == BUILT_IN_POLICY
    assert list(policy.lists) == list(BUILT_IN_POLICY.lists)
    assert list(policy.profiles) == list(BUILT_IN_POLICY.profiles)
