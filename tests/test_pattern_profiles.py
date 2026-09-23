"""PRD-011 STORY-006: profiles and the role inspection matrix.

Covers the profile half of `app/services/pattern_config.py`: the Section 6.4
matrix of the built-in policy, cell by cell; the `roles:` vocabulary and the
empty-map rule; lists resolved to objects at load; `PATTERN_PROFILE_DEFAULT`'s
cross-check on both of `load()`'s paths; `get_profile()`; and that the role
vocabulary is `app.models.messages.Role`, reused rather than redefined.

What it deliberately does **not** cover: walking a conversation and what a
hit does (`inspect()` and the pipeline's block arm, STORY-008), and the chat
ingress passing no profile (STORY-008). The `code` profile has no HTTP
ingress in this PRD at all -- PRD-014 mounts one -- so nothing here touches a
router.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

from pathlib import Path
from typing import get_args, get_type_hints

import pytest

import app.models.messages as messages
import app.services.pattern_config as pattern_config
from app.config import settings
from app.models.messages import Role
from app.services.pattern_config import (
    BUILT_IN_POLICY,
    PatternConfigError,
    PatternList,
    Profile,
    get_policy,
    get_profile,
    load,
)

_ACTIONS = ("block", "flag")


@pytest.fixture
def _reset_policy():
    """Restore the module-level policy after a test rebinds it -- the fixture
    `tests/test_pattern_config.py` and `tests/test_authz.py` each keep locally."""
    original = pattern_config._policy
    yield
    pattern_config._policy = original


@pytest.fixture(autouse=True)
def _default_profile_is_chat(monkeypatch):
    """`load()` cross-checks `PATTERN_PROFILE_DEFAULT`; pin the baseline so a
    developer's `.env` cannot decide a test. Tests that need another default
    set it themselves."""
    monkeypatch.setattr(settings, "PATTERN_PROFILE_DEFAULT", "chat")


def _write(tmp_path, text: str) -> str:
    path = tmp_path / "patterns.yaml"
    path.write_text(text, encoding="utf-8")
    return str(path)


def _file_with_roles(roles_yaml: str, profile: str = "chat") -> str:
    """One valid list and one profile whose `roles:` line is `roles_yaml`."""
    return (
        "lists:\n"
        "  only:\n"
        "    match: word\n"
        "    scope: everywhere\n"
        "    patterns: [hello]\n"
        "profiles:\n"
        f"  {profile}:\n"
        "    lists: [only]\n"
        f"    {roles_yaml}\n"
    )


# --- AC 1: the Section 6.4 matrix, cell by cell -----------------------------

#: (profile, role, action or None). None is "not inspected" -- which means the
#: role is *absent* from the map, not present with a falsy value.
_MATRIX = [
    ("chat", "system", None),
    ("chat", "user", "block"),
    ("chat", "assistant", None),
    ("chat", "tool", None),
    ("code", "system", None),
    ("code", "user", "block"),
    ("code", "assistant", None),
    ("code", "tool", "flag"),
]


@pytest.mark.parametrize(
    "profile_name, role, expected",
    _MATRIX,
    ids=[f"{p}-{r}-{a or 'not-inspected'}" for p, r, a in _MATRIX],
)
def test_built_in_matrix_cell(profile_name, role, expected):
    """PRD-011 Section 6.4. Each "not inspected" cell asserts absence, not
    `.get() is None`: absence is what "not inspected" means (Section 7/F4), and
    a key mapped to a falsy value would pass the weaker check."""
    roles = BUILT_IN_POLICY.profiles[profile_name].roles

    if expected is None:
        assert role not in roles
    else:
        assert roles[role] == expected


def test_the_matrix_has_no_cells_beyond_section_6_4():
    """Exactly two profiles, exactly these keys -- the parametrized cells above
    cannot see an extra profile or an extra role nobody wrote into the table."""
    assert set(BUILT_IN_POLICY.profiles) == {"chat", "code"}
    assert dict(BUILT_IN_POLICY.profiles["chat"].roles) == {"user": "block"}
    assert dict(BUILT_IN_POLICY.profiles["code"].roles) == {"user": "block", "tool": "flag"}


def test_built_in_profile_lists():
    """`chat` loads both lists; `code` does not load `keywords` at all, which is
    its real answer to `@Override` (PRD-011 Sections 6.2, 6.4, D3)."""
    profiles = BUILT_IN_POLICY.profiles

    assert [pattern_list.name for pattern_list in profiles["chat"].lists] == [
        "injection",
        "keywords",
    ]
    assert [pattern_list.name for pattern_list in profiles["code"].lists] == ["injection"]


def test_every_built_in_role_and_action_is_in_the_vocabulary():
    """The built-in maps are a Python literal, not run through the file
    validator; this is what stops them drifting outside the vocabulary."""
    for profile in BUILT_IN_POLICY.profiles.values():
        for role, action in profile.roles.items():
            assert role in get_args(Role), f"{profile.name}: {role!r}"
            assert action in _ACTIONS, f"{profile.name}: {role!r} -> {action!r}"


# --- AC 2: the roles: map is validated at load ------------------------------

#: (id, roles line, substrings the message must contain). Each names the
#: profile, the offending key and -- where there is a closed set -- the
#: allowed values.
_BAD_ROLES = [
    (
        "unknown-role",
        "roles: {admin: block}",
        ["profile 'chat'", "unknown role", "'admin'", "assistant, system, tool, user"],
    ),
    (
        "unknown-role-wrong-case",
        "roles: {User: block}",
        ["profile 'chat'", "unknown role", "'User'", "assistant, system, tool, user"],
    ),
    (
        "unknown-action",
        "roles: {user: deny}",
        ["profile 'chat'", "'user'", "unknown action", "'deny'", "block, flag"],
    ),
    (
        "unknown-action-after-a-good-role",
        "roles: {user: block, tool: warn}",
        ["profile 'chat'", "'tool'", "unknown action", "'warn'", "block, flag"],
    ),
    ("empty-roles", "roles: {}", ["profile 'chat'", "roles is empty"]),
    ("null-roles", "roles:", ["profile 'chat'", "roles is empty"]),
    ("roles-not-a-mapping", "roles: [user]", ["profile 'chat'", "roles must be a mapping"]),
    ("roles-a-string", "roles: user", ["profile 'chat'", "roles must be a mapping"]),
]


@pytest.mark.parametrize(
    "roles_yaml, expected_substrings",
    [(roles_yaml, expected) for _, roles_yaml, expected in _BAD_ROLES],
    ids=[case_id for case_id, _, _ in _BAD_ROLES],
)
def test_bad_roles_map_fails_load_naming_the_offender(
    roles_yaml, expected_substrings, tmp_path, monkeypatch, _reset_policy
):
    path = _write(tmp_path, _file_with_roles(roles_yaml))
    monkeypatch.setattr(settings, "PATTERNS_FILE", path)

    with pytest.raises(PatternConfigError) as exc_info:
        load()

    message = str(exc_info.value)
    for expected in expected_substrings + [path]:
        assert expected in message, f"{expected!r} missing from: {message}"
    # Rebound last: a rejected file leaves the previous policy in force.
    assert get_policy() is BUILT_IN_POLICY


def test_missing_roles_key_fails_load(tmp_path, monkeypatch, _reset_policy):
    """An absent `roles:` would be an empty map by another name (PRD-011
    Section 9.2, T5), so the key is required."""
    body = (
        "lists:\n  only:\n    match: word\n    scope: everywhere\n    patterns: [hello]\n"
        "profiles:\n  chat:\n    lists: [only]\n"
    )
    monkeypatch.setattr(settings, "PATTERNS_FILE", _write(tmp_path, body))

    with pytest.raises(PatternConfigError) as exc_info:
        load()

    message = str(exc_info.value)
    assert "profile 'chat'" in message
    assert "missing key 'roles'" in message


@pytest.mark.parametrize("action", _ACTIONS)
@pytest.mark.parametrize("role", get_args(Role))
def test_every_role_and_action_is_accepted(role, action, tmp_path, monkeypatch, _reset_policy):
    """The positive half of AC 2: the whole vocabulary loads, and is stored as
    written."""
    body = _file_with_roles(f"roles: {{{role}: {action}}}")
    monkeypatch.setattr(settings, "PATTERNS_FILE", _write(tmp_path, body))

    load()

    assert dict(get_policy().profiles["chat"].roles) == {role: action}


def test_roles_keep_declared_order(tmp_path, monkeypatch, _reset_policy):
    body = _file_with_roles("roles: {tool: flag, user: block}")
    monkeypatch.setattr(settings, "PATTERNS_FILE", _write(tmp_path, body))

    load()

    assert list(get_policy().profiles["chat"].roles) == ["tool", "user"]


# --- AC 3: lists are resolved objects, at load ------------------------------


@pytest.mark.parametrize("profile_name", ["chat", "code"])
def test_built_in_profile_lists_are_the_policys_own_objects(profile_name):
    policy = get_policy()

    for pattern_list in policy.profiles[profile_name].lists:
        assert isinstance(pattern_list, PatternList)
        assert pattern_list is policy.lists[pattern_list.name]


def test_undefined_list_is_a_startup_error_not_a_key_error(tmp_path, monkeypatch, _reset_policy):
    """Resolved at load, so the failure happens at startup as
    `PatternConfigError` and can never surface as a request-time `KeyError`
    (PRD-011 Section 7/F4)."""
    body = (
        "lists:\n  only:\n    match: word\n    scope: everywhere\n    patterns: [hello]\n"
        "profiles:\n  chat:\n    lists: [ony]\n    roles: {user: block}\n"
    )
    monkeypatch.setattr(settings, "PATTERNS_FILE", _write(tmp_path, body))

    with pytest.raises(PatternConfigError) as exc_info:
        load()

    assert not isinstance(exc_info.value, KeyError)
    assert "'ony'" in str(exc_info.value)
    assert "defined lists: only" in str(exc_info.value)


# --- AC 4: PATTERN_PROFILE_DEFAULT's cross-check, and get_profile -----------


def test_default_naming_an_undefined_profile_fails_load_from_a_file(
    tmp_path, monkeypatch, _reset_policy
):
    path = _write(tmp_path, _file_with_roles("roles: {user: block}"))
    monkeypatch.setattr(settings, "PATTERNS_FILE", path)
    monkeypatch.setattr(settings, "PATTERN_PROFILE_DEFAULT", "nope")

    with pytest.raises(PatternConfigError) as exc_info:
        load()

    message = str(exc_info.value)
    assert "PATTERN_PROFILE_DEFAULT" in message
    assert "'nope'" in message
    assert "defined profiles: chat" in message
    assert path in message
    # Checked before the rebind, like every other rule.
    assert get_policy() is BUILT_IN_POLICY


def test_default_naming_an_undefined_profile_fails_load_without_a_file(
    monkeypatch, _reset_policy
):
    """The empty-setting path checks too -- against the built-in policy, and
    still without reading any file. Otherwise `PATTERN_PROFILE_DEFAULT=nope`
    boots cleanly and fails on the first request (PRD-011 Section 2)."""
    monkeypatch.setattr(settings, "PATTERNS_FILE", "")
    monkeypatch.setattr(settings, "PATTERN_PROFILE_DEFAULT", "nope")

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("read_text should not be called when PATTERNS_FILE is empty")

    monkeypatch.setattr(Path, "read_text", _fail_if_called)

    with pytest.raises(PatternConfigError) as exc_info:
        load()

    message = str(exc_info.value)
    assert "PATTERN_PROFILE_DEFAULT" in message
    assert "'nope'" in message
    assert "defined profiles: chat, code" in message
    assert "PATTERNS_FILE is unset" in message


def test_default_code_loads_against_the_built_in_policy(monkeypatch, _reset_policy):
    monkeypatch.setattr(settings, "PATTERNS_FILE", "")
    monkeypatch.setattr(settings, "PATTERN_PROFILE_DEFAULT", "code")

    assert load() is None
    assert get_policy() is BUILT_IN_POLICY


def test_default_may_name_any_profile_the_file_defines(tmp_path, monkeypatch, _reset_policy):
    """`chat` is the default's default, not a required profile name."""
    monkeypatch.setattr(
        settings,
        "PATTERNS_FILE",
        _write(tmp_path, _file_with_roles("roles: {user: block, tool: flag}", profile="code")),
    )
    monkeypatch.setattr(settings, "PATTERN_PROFILE_DEFAULT", "code")

    load()

    assert set(get_policy().profiles) == {"code"}


@pytest.mark.parametrize("profile_name", ["chat", "code"])
def test_get_profile_returns_the_policys_profile(profile_name):
    profile = get_profile(profile_name)

    assert isinstance(profile, Profile)
    assert profile is get_policy().profiles[profile_name]


def test_get_profile_unknown_name_raises_the_same_error_type():
    with pytest.raises(PatternConfigError) as exc_info:
        get_profile("nope")

    message = str(exc_info.value)
    assert "'nope'" in message
    assert "defined profiles: chat, code" in message


def test_get_profile_reads_the_loaded_policy_not_the_built_in_one(
    tmp_path, monkeypatch, _reset_policy
):
    """After a file that defines only `chat` loads, the built-in `code` is gone
    -- wholesale replacement, seen through `get_profile`."""
    body = _file_with_roles("roles: {user: flag}")
    monkeypatch.setattr(settings, "PATTERNS_FILE", _write(tmp_path, body))

    load()

    assert dict(get_profile("chat").roles) == {"user": "flag"}
    with pytest.raises(PatternConfigError):
        get_profile("code")


# --- AC 5: Role is reused, not redefined ------------------------------------


def test_pattern_config_uses_the_messages_role():
    """One role vocabulary in the codebase (PRD-011 Section 6.2): the name
    `pattern_config` uses *is* `messages.Role`, and `Profile.roles` is keyed on
    it."""
    assert pattern_config.Role is messages.Role
    key_type, _ = get_args(get_type_hints(Profile)["roles"])
    assert key_type is Role


@pytest.mark.parametrize("role", get_args(Role))
def test_every_role_member_is_an_accepted_roles_key(role, tmp_path, monkeypatch, _reset_policy):
    """Parametrized over the `Literal` itself, so a role added to
    `app/models/messages.py` is exercised here with no edit to this file."""
    monkeypatch.setattr(
        settings, "PATTERNS_FILE", _write(tmp_path, _file_with_roles(f"roles: {{{role}: block}}"))
    )

    load()

    assert role in get_policy().profiles["chat"].roles


# --- Technical Notes: the asymmetry with RBAC is written down ---------------


def test_profile_docstring_states_absent_means_not_inspected():
    """A reader who knows `authz.py` assumes deny-by-default here. The
    docstring must say otherwise (PRD-011 Section 7/F4), and this stops the
    paragraph being tidied away."""
    doc = Profile.__doc__

    assert "not inspected" in doc
    assert "authz" in doc
