import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings, settings

REPO_ROOT = Path(__file__).resolve().parents[1]


# --- AC1: new fields are available with the documented defaults ---


def test_rbac_settings_available_with_documented_defaults():
    assert settings.RBAC_ENABLED is True
    assert settings.RBAC_DEFAULT_ROLE == "user"
    assert settings.RBAC_ROLES_FILE == ""
    assert isinstance(settings.MODEL_ALLOWLIST, str)
    assert settings.MODEL_ALLOWLIST != ""


# --- AC2: model_allowlist_list parses exactly like pii_entities_list ---


def test_model_allowlist_list_parses_like_pii_entities_list(monkeypatch):
    monkeypatch.setattr(settings, "MODEL_ALLOWLIST", " gpt-4 , ,claude-3-sonnet ,")

    assert settings.model_allowlist_list == ["gpt-4", "claude-3-sonnet"]


def test_model_allowlist_list_default_matches_prd_default_models():
    assert settings.model_allowlist_list == [
        "gpt-4",
        "claude-3-sonnet",
        "openai/gpt-4o",
        "anthropic/claude-3.5-sonnet",
    ]


# --- AC3: none of the new vars set -- defaults apply, nothing raises ---


def test_settings_construct_without_new_env_vars(monkeypatch):
    for var in ("RBAC_ENABLED", "RBAC_DEFAULT_ROLE", "RBAC_ROLES_FILE", "MODEL_ALLOWLIST"):
        monkeypatch.delenv(var, raising=False)

    fresh = Settings(_env_file=None)

    assert fresh.RBAC_ENABLED is True
    assert fresh.RBAC_DEFAULT_ROLE == "user"
    assert fresh.RBAC_ROLES_FILE == ""
    assert fresh.model_allowlist_list  # non-empty


# --- AC4: .env.example documents every new variable, Settings field for field ---


def test_env_example_documents_every_new_rbac_var_with_a_comment():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for var in ("RBAC_ENABLED", "RBAC_DEFAULT_ROLE", "RBAC_ROLES_FILE", "MODEL_ALLOWLIST"):
        assert re.search(rf"(?m)^#.+\n{var}=", text), f"{var} missing from .env.example or missing its comment line"


def test_env_example_rbac_vars_appear_in_settings_field_order():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    declared_order = ["RBAC_ENABLED", "RBAC_DEFAULT_ROLE", "RBAC_ROLES_FILE", "MODEL_ALLOWLIST"]

    positions = [text.index(f"{var}=") for var in declared_order]

    assert positions == sorted(positions)


# --- PRD-007 STORY-005: DATABASE_URL semantics and TURSO_AUTH_TOKEN ----------
#
# Every test below constructs Settings explicitly rather than reading the
# process environment, because the whole point of the story is what happens at
# construction. `_env_file=None` keeps a developer's real `.env` -- which on a
# pre-migration machine still says `sqlite:///harness_ai.db` -- from deciding
# whether these pass.

# A token value no message is allowed to echo (AC 6).
_TOKEN_SENTINEL = "s3cr3t-sentinel"

_REMOTE_URL = "libsql://harness-ai-acme.turso.io"
_LOCAL_URL = "http://127.0.0.1:8080"


def _settings(**overrides) -> Settings:
    base = {"OPENROUTER_API_KEY": "test-key", "ADMIN_TOKEN": "test-token"}
    return Settings(_env_file=None, **{**base, **overrides})


@pytest.mark.parametrize("url", [_REMOTE_URL, "https://harness-ai-acme.turso.io"])
def test_remote_endpoint_without_a_token_is_a_startup_error(url):
    """AC 2: both remote schemes require the credential, not just libsql://."""
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=url, TURSO_AUTH_TOKEN="")

    assert "TURSO_AUTH_TOKEN" in str(exc_info.value)


def test_local_dev_server_without_a_token_is_accepted():
    """AC 3: the local libSQL server takes no token (PRD Section 9)."""
    result = _settings(DATABASE_URL=_LOCAL_URL)

    assert result.DATABASE_URL == _LOCAL_URL
    assert result.TURSO_AUTH_TOKEN == ""


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///harness_ai.db",  # the default this story removed
        "sqlite:///:memory:",  # Dockerfile:17's build placeholder
        "sqlite:////app/data/harness_ai.db",  # docker-compose.yml:12
    ],
)
def test_any_sqlite_url_is_rejected_and_the_message_names_the_replacement(url):
    """AC 4: never a file, never silently ignored, and the error is actionable.

    Parametrized over the three spellings that actually exist in this repo, so
    a validator that only caught `sqlite:///` relative paths would fail here.
    """
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=url)

    message = str(exc_info.value)
    assert "libsql://" in message, "the message must name the replacement form"


def test_database_url_is_required_with_no_default(monkeypatch):
    """AC 5: the default is removed, not replaced with another default.

    `_env_file=None` silences the dotenv source but not the process
    environment, and `tests/conftest.py` puts a placeholder there so the suite
    can import `app.config` at all -- so "unset" has to be made true here, the
    way `test_settings_construct_without_new_env_vars` above does it.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        _settings()

    assert "DATABASE_URL" in str(exc_info.value)
    assert Settings.model_fields["DATABASE_URL"].is_required()


def test_a_valid_remote_pair_constructs():
    """AC 7's fifth case: the configuration this PRD is migrating toward."""
    result = _settings(DATABASE_URL=_REMOTE_URL, TURSO_AUTH_TOKEN=_TOKEN_SENTINEL)

    assert result.DATABASE_URL == _REMOTE_URL
    assert result.TURSO_AUTH_TOKEN == _TOKEN_SENTINEL


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///harness_ai.db",  # scheme failure, token present but irrelevant
        "postgres://db.example.com",  # unsupported scheme
    ],
)
def test_no_failure_message_ever_echoes_the_token(url):
    """AC 6: the credential is "never echoed in error messages" (PRD Section 9)."""
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=url, TURSO_AUTH_TOKEN=_TOKEN_SENTINEL)

    assert _TOKEN_SENTINEL not in str(exc_info.value)


def test_a_token_carried_inside_the_url_is_not_echoed_either():
    """AC 6's sharp case, and the reason messages quote only the scheme.

    A libSQL endpoint can carry its credential in the URL itself. Here the
    setting is empty, so validation fails for a missing TURSO_AUTH_TOKEN -- and
    a message that echoed `DATABASE_URL`, the way `app/db/database.py:25` does,
    would print the token while reporting that no token was given.
    """
    url = f"libsql://harness-ai-acme.turso.io?authToken={_TOKEN_SENTINEL}"

    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=url, TURSO_AUTH_TOKEN="")

    assert _TOKEN_SENTINEL not in str(exc_info.value)


def test_unsupported_scheme_names_the_accepted_ones():
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL="postgres://db.example.com", TURSO_AUTH_TOKEN="t")

    message = str(exc_info.value)
    for scheme in ("libsql://", "https://", "http://"):
        assert scheme in message


def test_https_is_remote_even_though_it_starts_like_http():
    """`"https://".startswith("http://")` is False, and the token rule depends on it.

    Pinned because the next reader will assume the opposite, and the failure it
    would cause -- a remote endpoint silently accepted with no credential -- is
    the one this story exists to prevent.
    """
    with pytest.raises(ValidationError):
        _settings(DATABASE_URL="https://harness-ai-acme.turso.io")


def test_surrounding_whitespace_is_stripped_not_rejected():
    """A trailing newline in a `.env` value must not read as an unknown scheme."""
    result = _settings(DATABASE_URL=f"  {_LOCAL_URL}\n")

    assert result.DATABASE_URL == _LOCAL_URL


# --- AC4 (STORY-005): .env.example documents both new variables --------------


def test_env_example_documents_both_turso_vars_with_a_comment():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for var in ("DATABASE_URL", "TURSO_AUTH_TOKEN"):
        assert re.search(rf"(?m)^#.+\n{var}=", text), f"{var} missing from .env.example or missing its comment line"


def test_env_example_carries_no_sqlite_url():
    """The committed example must not hand anyone the value that now fails."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "DATABASE_URL=sqlite:" not in text


def test_env_example_turso_vars_appear_in_settings_field_order():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    declared_order = ["DATABASE_URL", "TURSO_AUTH_TOKEN"]

    positions = [text.index(f"{var}=") for var in declared_order]

    assert positions == sorted(positions)


def test_env_example_ships_no_token_value():
    """AC 6's committed-file half: the example must never carry a real token."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    assert re.search(r"(?m)^TURSO_AUTH_TOKEN=$", text), "TURSO_AUTH_TOKEN must be present and empty"


# --- STORY-008: the build-time bootstrap switch is opt-in to disable ---


def test_db_bootstrap_enabled_defaults_to_true():
    """The guard is on unless something deliberately turns it off.

    A default of False would make the escape hatch the norm and the guard the
    exception -- the inversion PRD-007 Section 2 rejects ("a fallback that
    silently writes audit rows to a local file no one reads is worse than a
    failure"). Only the Dockerfile's builder stage may set it.
    """
    assert _settings(DATABASE_URL=_LOCAL_URL).DB_BOOTSTRAP_ENABLED is True


def test_db_bootstrap_enabled_can_be_turned_off_for_the_build():
    """STORY-014 sets this in the builder stage, where `reflex export` imports
    chat_ui.chat_ui with no database reachable (PRD Section 11)."""
    result = _settings(DATABASE_URL=_LOCAL_URL, DB_BOOTSTRAP_ENABLED="false")

    assert result.DB_BOOTSTRAP_ENABLED is False
# --- PRD-008 STORY-001: chat transcript persistence settings -----------------
#
# Nothing reads either setting yet -- app/services/chat_sessions.py (STORY-006)
# is the only consumer. What is asserted here is the switch existing and
# refusing a value that would lie to a user, because PRD-008 Risk 1 makes this
# the mitigation for the largest exposure the PRD introduces, and a mitigation
# is only load-bearing if it lands before the thing it mitigates.


def test_chat_history_settings_available_with_documented_defaults():
    """AC 1: both settings exist with the defaults PRD-008 Section 9 tabulates."""
    result = _settings(DATABASE_URL=_LOCAL_URL)

    assert result.CHAT_HISTORY_ENABLED is True
    assert result.CHAT_SESSION_LIMIT == 50


def test_chat_history_can_be_turned_off_with_the_string_false():
    """AC 3: `false`, the string, is what a `.env` file and Docker actually supply.

    Asserted with `is False` rather than `not ...` so a value that merely
    happens to be falsy -- an empty string surviving coercion, say -- fails.
    """
    result = _settings(DATABASE_URL=_LOCAL_URL, CHAT_HISTORY_ENABLED="false")

    assert result.CHAT_HISTORY_ENABLED is False


@pytest.mark.parametrize("limit", [0, -1, "0"])
def test_a_chat_session_limit_below_one_is_a_startup_error(limit):
    """AC 2: a limit of 0 renders an empty rail on a user who has sessions.

    `"0"` is parametrized alongside the ints because the environment supplies
    strings and pydantic coerces before the validator runs -- a validator
    written against the raw string would pass the int cases and leak this one.
    """
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, CHAT_SESSION_LIMIT=limit)

    assert "CHAT_SESSION_LIMIT" in str(exc_info.value)


def test_a_chat_session_limit_of_one_is_accepted():
    """The boundary on the accepted side, so `<= 1` fails here and not in STORY-006."""
    result = _settings(DATABASE_URL=_LOCAL_URL, CHAT_SESSION_LIMIT=1)

    assert result.CHAT_SESSION_LIMIT == 1


def test_settings_construct_without_the_chat_vars(monkeypatch):
    """The defaults are the module's, not a developer's exported environment."""
    for var in ("CHAT_HISTORY_ENABLED", "CHAT_SESSION_LIMIT"):
        monkeypatch.delenv(var, raising=False)

    fresh = _settings(DATABASE_URL=_LOCAL_URL)

    assert fresh.CHAT_HISTORY_ENABLED is True
    assert fresh.CHAT_SESSION_LIMIT == 50


def test_env_example_documents_both_chat_vars_with_a_comment():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for var in ("CHAT_HISTORY_ENABLED", "CHAT_SESSION_LIMIT"):
        assert re.search(rf"(?m)^#.+\n{var}=", text), f"{var} missing from .env.example or missing its comment line"


def test_env_example_chat_vars_appear_in_settings_field_order():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    declared_order = ["CHAT_HISTORY_ENABLED", "CHAT_SESSION_LIMIT"]

    positions = [text.index(f"{var}=") for var in declared_order]

    assert positions == sorted(positions)


def test_env_example_says_what_the_off_state_does():
    """AC 4's content half: the comment states the consequence, not the type.

    Asserted on substance rather than on an exact sentence, so rewording the
    comment stays a docs change instead of a red test.
    """
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    comment = re.search(r"(?m)((?:^#.*\n)+)CHAT_HISTORY_ENABLED=", text)

    assert comment, "CHAT_HISTORY_ENABLED has no comment block above it"
    block = comment.group(1).lower()
    assert block.count("\n") >= 2, "one line cannot say what the off state does"
    for token in ("false", "transcript", "rail", "prd-008"):
        assert token in block, f"the CHAT_HISTORY_ENABLED comment never mentions {token!r}"


# --- PRD-010 STORY-002: upstream timeout, context limits, pipeline workers --
#
# Nothing reads these settings yet. What is asserted here is that each has
# the documented default, and that a value of 0 or negative fails at
# construction with a message naming the setting and what it controls.


def test_multiturn_pipeline_settings_available_with_documented_defaults():
    """AC 1 / AC 3: all four settings exist with PRD-010 Section 9.3's defaults."""
    result = _settings(DATABASE_URL=_LOCAL_URL)

    assert result.OPENROUTER_TIMEOUT_SECONDS == 120.0
    assert result.CONTEXT_MAX_MESSAGES == 100
    assert result.CONTEXT_MAX_CHARACTERS == 200_000
    assert result.PIPELINE_MAX_WORKERS == 32


@pytest.mark.parametrize("value", [0, 0.0, -1, "0"])
def test_openrouter_timeout_seconds_at_or_below_zero_is_a_startup_error(value):
    """AC 2: names the setting, the value received, and its purpose."""
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, OPENROUTER_TIMEOUT_SECONDS=value)

    message = str(exc_info.value)
    assert "OPENROUTER_TIMEOUT_SECONDS" in message
    assert "upstream request timeout in seconds" in message


@pytest.mark.parametrize(
    "field,value",
    [
        ("CONTEXT_MAX_MESSAGES", 0),
        ("CONTEXT_MAX_MESSAGES", -1),
        ("CONTEXT_MAX_MESSAGES", "0"),
        ("CONTEXT_MAX_CHARACTERS", 0),
        ("CONTEXT_MAX_CHARACTERS", -1),
        ("CONTEXT_MAX_CHARACTERS", "0"),
        ("PIPELINE_MAX_WORKERS", 0),
        ("PIPELINE_MAX_WORKERS", -1),
        ("PIPELINE_MAX_WORKERS", "0"),
    ],
)
def test_a_pipeline_size_setting_below_one_is_a_startup_error(field, value):
    """AC 3: each of the three integer settings, in the _validate_chat_session_limit style.

    `"0"` sits alongside the ints for the same reason CHAT_SESSION_LIMIT's
    equivalent test does: the environment supplies strings, and pydantic
    coerces before the validator runs.
    """
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, **{field: value})

    assert field in str(exc_info.value)


def test_pipeline_size_settings_accept_the_boundary_value_of_one():
    result = _settings(
        DATABASE_URL=_LOCAL_URL,
        CONTEXT_MAX_MESSAGES=1,
        CONTEXT_MAX_CHARACTERS=1,
        PIPELINE_MAX_WORKERS=1,
    )

    assert result.CONTEXT_MAX_MESSAGES == 1
    assert result.CONTEXT_MAX_CHARACTERS == 1
    assert result.PIPELINE_MAX_WORKERS == 1


def test_settings_construct_without_the_multiturn_pipeline_vars(monkeypatch):
    """The defaults are the module's, not a developer's exported environment."""
    for var in (
        "OPENROUTER_TIMEOUT_SECONDS",
        "CONTEXT_MAX_MESSAGES",
        "CONTEXT_MAX_CHARACTERS",
        "PIPELINE_MAX_WORKERS",
    ):
        monkeypatch.delenv(var, raising=False)

    fresh = _settings(DATABASE_URL=_LOCAL_URL)

    assert fresh.OPENROUTER_TIMEOUT_SECONDS == 120.0
    assert fresh.CONTEXT_MAX_MESSAGES == 100
    assert fresh.CONTEXT_MAX_CHARACTERS == 200_000
    assert fresh.PIPELINE_MAX_WORKERS == 32


def test_env_example_documents_every_multiturn_pipeline_var_with_a_comment():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for var in (
        "OPENROUTER_TIMEOUT_SECONDS",
        "CONTEXT_MAX_MESSAGES",
        "CONTEXT_MAX_CHARACTERS",
        "PIPELINE_MAX_WORKERS",
    ):
        assert re.search(rf"(?m)^#.+\n{var}=", text), f"{var} missing from .env.example or missing its comment line"


def test_env_example_multiturn_pipeline_vars_appear_in_settings_field_order():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    declared_order = [
        "OPENROUTER_TIMEOUT_SECONDS",
        "CONTEXT_MAX_MESSAGES",
        "CONTEXT_MAX_CHARACTERS",
        "PIPELINE_MAX_WORKERS",
    ]

    positions = [text.index(f"{var}=") for var in declared_order]

    assert positions == sorted(positions)


# --- PRD-011 STORY-004: pattern policy settings ------------------------------
#
# Nothing reads these four yet -- `app/services/pattern_config.py` (STORY-005)
# and `inspect()` (STORY-008) are the consumers. What is asserted here is that
# each has the default PRD-011 Section 9.3 tabulates, that the two validators
# that can run at construction time do, and -- the one with teeth -- that the
# profile-membership check has *not* been smuggled in here, because the file it
# would have to read is not loaded when Settings is constructed.

_PATTERN_VARS = (
    "PATTERNS_FILE",
    "PATTERN_PROFILE_DEFAULT",
    "PATTERNS_ALLOW_REGEX",
    "PATTERN_MAX_SCAN_CHARACTERS",
)


def test_pattern_policy_settings_available_with_documented_defaults():
    """AC 1: all four exist with PRD-011 Section 9.3's defaults."""
    result = _settings(DATABASE_URL=_LOCAL_URL)

    assert result.PATTERNS_FILE == ""
    assert result.PATTERN_PROFILE_DEFAULT == "chat"
    assert result.PATTERNS_ALLOW_REGEX is False
    assert result.PATTERN_MAX_SCAN_CHARACTERS == 1_000_000


def test_patterns_allow_regex_can_be_turned_on_with_the_string_true():
    """`true`, the string, is what a `.env` file and Docker actually supply.

    Asserted with `is True` for the same reason
    `test_chat_history_can_be_turned_off_with_the_string_false` uses `is False`:
    a value that merely happens to be truthy must not pass.
    """
    result = _settings(DATABASE_URL=_LOCAL_URL, PATTERNS_ALLOW_REGEX="true")

    assert result.PATTERNS_ALLOW_REGEX is True


@pytest.mark.parametrize("value", [0, -1, "0"])
def test_a_pattern_max_scan_characters_below_one_is_a_startup_error(value):
    """AC 2: the message names the field, the rejected value and what it bounds.

    All three are asserted rather than just the field name, because "names the
    rejected value and what the field bounds" is what separates this message
    from a bare pydantic one. `"0"` sits alongside the ints for the reason the
    PRD-010 equivalent gives: the environment supplies strings, and pydantic
    coerces before the validator runs.
    """
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, PATTERN_MAX_SCAN_CHARACTERS=value)

    message = str(exc_info.value)
    assert "PATTERN_MAX_SCAN_CHARACTERS" in message
    assert str(int(value)) in message, "the message must quote the value it rejected"
    assert "per-message ceiling" in message, "the message must say what the field bounds"


def test_pattern_max_scan_characters_accepts_the_boundary_value_of_one():
    """The boundary on the accepted side, so a `<= 1` typo fails here, not in STORY-008."""
    result = _settings(DATABASE_URL=_LOCAL_URL, PATTERN_MAX_SCAN_CHARACTERS=1)

    assert result.PATTERN_MAX_SCAN_CHARACTERS == 1


@pytest.mark.parametrize("value", ["", "   "])
def test_an_empty_pattern_profile_default_is_a_startup_error(value):
    """AC 3's first half: non-empty is the one check that belongs here."""
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, PATTERN_PROFILE_DEFAULT=value)

    assert "PATTERN_PROFILE_DEFAULT" in str(exc_info.value)


def test_pattern_profile_default_is_not_checked_against_any_policy_here():
    """AC 3's second half, and the assertion with teeth.

    Whether the name matches a profile the policy defines is a cross-check
    between this setting and `PATTERNS_FILE`, and the file is not read when
    Settings is constructed (PRD-011 Section 9.3). `pattern_config.load()`
    owns it -- STORY-006 raises `PatternConfigError` there naming the setting,
    the missing profile and the profiles that do exist.

    So a name nothing defines must construct cleanly *here*. A future field
    validator that went looking for the file would turn this red, which is the
    point: it would either fail every boot or silently skip the check.
    """
    result = _settings(
        DATABASE_URL=_LOCAL_URL, PATTERN_PROFILE_DEFAULT="a-profile-nothing-defines"
    )

    assert result.PATTERN_PROFILE_DEFAULT == "a-profile-nothing-defines"


def test_pattern_profile_default_strips_surrounding_whitespace():
    """A trailing newline in a `.env` value must not become part of the name.

    The same treatment `test_surrounding_whitespace_is_stripped_not_rejected`
    pins for DATABASE_URL -- and it matters more here, because the untrimmed
    value would reach `get_profile()` and miss by a character.
    """
    result = _settings(DATABASE_URL=_LOCAL_URL, PATTERN_PROFILE_DEFAULT="  code\n")

    assert result.PATTERN_PROFILE_DEFAULT == "code"


def test_settings_construct_without_the_pattern_policy_vars(monkeypatch):
    """The defaults are the module's, not a developer's exported environment."""
    for var in _PATTERN_VARS:
        monkeypatch.delenv(var, raising=False)

    fresh = _settings(DATABASE_URL=_LOCAL_URL)

    assert fresh.PATTERNS_FILE == ""
    assert fresh.PATTERN_PROFILE_DEFAULT == "chat"
    assert fresh.PATTERNS_ALLOW_REGEX is False
    assert fresh.PATTERN_MAX_SCAN_CHARACTERS == 1_000_000


def test_env_example_documents_every_pattern_policy_var_with_a_comment():
    """AC 4: all four present, each with an explanation above it."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for var in _PATTERN_VARS:
        assert re.search(rf"(?m)^#.+\n{var}=", text), f"{var} missing from .env.example or missing its comment line"


def test_env_example_pattern_policy_vars_appear_in_settings_field_order():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    positions = [text.index(f"{var}=") for var in _PATTERN_VARS]

    assert positions == sorted(positions)


def test_env_example_pattern_defaults_match_the_settings_defaults():
    """AC 4's "same defaults" half, compared against the fields, not a copy.

    A hand-written example drifts from the code silently; asserting against
    `Settings.model_fields` means the drift is a red test instead. Values are
    read as the strings a `.env` really supplies -- which is also why
    `PATTERN_MAX_SCAN_CHARACTERS` is written `1000000` there and `1_000_000`
    in the field: the underscore form is a Python literal, not an environment
    one.
    """
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    defaults = {name: Settings.model_fields[name].default for name in _PATTERN_VARS}

    def value_of(var: str) -> str:
        match = re.search(rf"(?m)^{var}=(.*)$", text)
        assert match, f"{var} is not assigned in .env.example"
        return match.group(1).strip()

    assert value_of("PATTERNS_FILE") == "", "PATTERNS_FILE must ship empty -- empty is the built-in policy"
    assert value_of("PATTERN_PROFILE_DEFAULT") == defaults["PATTERN_PROFILE_DEFAULT"]
    assert value_of("PATTERNS_ALLOW_REGEX") == str(defaults["PATTERNS_ALLOW_REGEX"]).lower()
    assert int(value_of("PATTERN_MAX_SCAN_CHARACTERS")) == defaults["PATTERN_MAX_SCAN_CHARACTERS"]


def test_env_example_points_at_the_sample_patterns_file():
    """PRD-011 STORY-013 AC 4: `.env.example` names the working sample, and
    the sample it names exists -- a pointer to a missing file is worse than
    none."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "examples/patterns.yaml" in text
    assert (REPO_ROOT / "examples" / "patterns.yaml").is_file()


def test_requirements_declares_pyyaml_explicitly():
    """AC 5: PyYAML is a declared dependency, not a transitive one.

    It is already installed through `python-frontmatter`, so nothing breaks
    today by leaving it out -- which is exactly why it needs pinning down in a
    test. PRD-011 Section 8: depending on a transitive dependency is how a
    build breaks silently, on the day the intermediate package drops it.
    STORY-005 is the first module to `import yaml`.
    """
    text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert re.search(r"(?mi)^PyYAML\b", text), "PyYAML must be declared in requirements.txt"


# --- PRD-012 STORY-005: PII code-profile settings ----------------------------
#
# Nothing reads these six yet -- STORY-006 (analyzer choice), STORY-007 (the
# `code` policy) and STORY-010 (the refusal arm) are the consumers. What is
# asserted here is that each has the default STORY-003's report decided, that
# the three validators reject what they must at construction time with a
# message that says how to fix it, and that the four existing PII_* settings
# -- `chat`'s -- are untouched. `.env.example` is STORY-014's, not this block's.

from app.config import _POSITIVE_LIMIT_DESCRIPTIONS, _PRESIDIO_ENTITY_NAMES  # noqa: E402

_PII_CODE_VARS = (
    "PII_ENTITIES_CODE",
    "PII_SCORE_THRESHOLD_CODE",
    "PII_MAX_CHARACTERS_CODE",
    "PII_CODE_REDACT_OUTPUT",
    "PII_CODE_REDACT_SYSTEM",
    "PII_CODE_SKIP_CODE_BLOCKS",
)


def _assert_pii_code_defaults(result: Settings) -> None:
    assert result.PII_ENTITIES_CODE == "EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE"
    assert result.PII_SCORE_THRESHOLD_CODE == 0.40
    assert result.PII_MAX_CHARACTERS_CODE == 200_000
    assert result.PII_CODE_REDACT_OUTPUT is False
    assert result.PII_CODE_REDACT_SYSTEM is False
    assert result.PII_CODE_SKIP_CODE_BLOCKS is True


def test_pii_code_settings_available_with_documented_defaults():
    """AC 1: all six exist; threshold and size limit are STORY-003's R1 and R3."""
    _assert_pii_code_defaults(_settings(DATABASE_URL=_LOCAL_URL))


def test_pii_entities_code_default_is_the_benchmarked_pattern_list():
    """AC 1's "taken from the STORY-003 report", compared against the list the
    benchmark actually measured rather than a second hand-written copy.

    PERSON and LOCATION stay out: R4 kept PERSON out on latency, and D7 keeps
    the default free of NER types so the tokenizer-only analyzer is chosen.
    """
    import scripts.measure_pii_latency as bench

    parsed = _settings(DATABASE_URL=_LOCAL_URL).pii_entities_code_list

    assert parsed == list(bench.PATTERN_ENTITIES)
    assert "PERSON" not in parsed
    assert "LOCATION" not in parsed


def test_pii_code_bools_parse_the_strings_a_dotenv_supplies():
    """Asserted with `is`, as the PRD-008 and PRD-011 blocks do: a value that
    merely happens to be truthy must not pass."""
    result = _settings(
        DATABASE_URL=_LOCAL_URL,
        PII_CODE_REDACT_OUTPUT="true",
        PII_CODE_REDACT_SYSTEM="true",
        PII_CODE_SKIP_CODE_BLOCKS="false",
    )

    assert result.PII_CODE_REDACT_OUTPUT is True
    assert result.PII_CODE_REDACT_SYSTEM is True
    assert result.PII_CODE_SKIP_CODE_BLOCKS is False


def test_settings_construct_without_the_pii_code_vars(monkeypatch):
    """The defaults are the module's, not a developer's exported environment."""
    for var in _PII_CODE_VARS:
        monkeypatch.delenv(var, raising=False)

    _assert_pii_code_defaults(_settings(DATABASE_URL=_LOCAL_URL))


@pytest.mark.parametrize("value", ["", "   ", " , ,"])
def test_an_empty_pii_entities_code_is_a_startup_error(value):
    """AC 2's first half. The message also names the real off switch, so an
    operator who emptied the list to disable PII is told what to do instead."""
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, PII_ENTITIES_CODE=value)

    message = str(exc_info.value)
    assert "PII_ENTITIES_CODE" in message
    assert "PII_REDACTION_ENABLED" in message


@pytest.mark.parametrize(
    "value,bad",
    [
        ("EMAIL_ADDRESS,NOT_A_TYPE", "NOT_A_TYPE"),
        ("email_address", "email_address"),
        ("EMAIL_ADDRESS, PASSPORT", "PASSPORT"),
    ],
)
def test_an_unknown_pii_entity_code_is_a_startup_error(value, bad):
    """AC 2's second half: the setting, the bad value and the accepted names.

    `email_address` is rejected because Presidio's names are case-sensitive:
    accepted here, it would pass startup and then detect nothing.
    """
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, PII_ENTITIES_CODE=value)

    message = str(exc_info.value)
    assert "PII_ENTITIES_CODE" in message
    assert bad in message
    for name in _PRESIDIO_ENTITY_NAMES:
        assert name in message, f"the message must list the accepted name {name}"


@pytest.mark.parametrize("name", sorted(_PRESIDIO_ENTITY_NAMES))
def test_every_known_entity_name_is_accepted_alone(name):
    """Includes PERSON and LOCATION: opting into NER is the operator's call (D7)."""
    result = _settings(DATABASE_URL=_LOCAL_URL, PII_ENTITIES_CODE=name)

    assert result.pii_entities_code_list == [name]


def test_known_entity_names_match_presidios_default_registry():
    """The constant exists so Settings never loads an analyzer; this test is
    what stops it drifting from the Presidio version requirements.txt pins.

    Loading the predefined recognizers builds no spaCy model, so this stays
    cheap.
    """
    from presidio_analyzer import RecognizerRegistry

    registry = RecognizerRegistry()
    registry.load_predefined_recognizers(languages=["en"])

    assert set(registry.get_supported_entities(languages=["en"])) == _PRESIDIO_ENTITY_NAMES


def test_known_entity_names_cover_todays_pii_entities():
    """The seven types today's `chat` default uses are all known names."""
    assert set(_settings(DATABASE_URL=_LOCAL_URL).pii_entities_list) <= _PRESIDIO_ENTITY_NAMES


@pytest.mark.parametrize("value", [-0.01, 1.01, -1, 2, "1.5", "nan", "inf"])
def test_a_pii_score_threshold_code_outside_zero_to_one_is_a_startup_error(value):
    """AC 3: names the field, the rejected value and what it is.

    `"nan"` is the case the `not 0 <= value <= 1` form exists for: NaN fails
    every comparison, so a `value < 0 or value > 1` check would let it through.
    """
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, PII_SCORE_THRESHOLD_CODE=value)

    message = str(exc_info.value)
    assert "PII_SCORE_THRESHOLD_CODE" in message
    assert "between 0 and 1" in message
    assert "minimum Presidio confidence" in message
    assert f"got {float(value)}" in message, "the message must quote the value it rejected"


def test_pii_score_threshold_code_accepts_both_boundaries():
    assert _settings(DATABASE_URL=_LOCAL_URL, PII_SCORE_THRESHOLD_CODE=0).PII_SCORE_THRESHOLD_CODE == 0.0
    assert _settings(DATABASE_URL=_LOCAL_URL, PII_SCORE_THRESHOLD_CODE=1).PII_SCORE_THRESHOLD_CODE == 1.0


@pytest.mark.parametrize("value", [0, -1, "0"])
def test_a_pii_max_characters_code_below_one_is_a_startup_error(value):
    """AC 3: the exact positive-limit message the other resource bounds use."""
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, PII_MAX_CHARACTERS_CODE=value)

    message = str(exc_info.value)
    assert f"PII_MAX_CHARACTERS_CODE must be at least 1, got {int(value)}." in message
    assert _POSITIVE_LIMIT_DESCRIPTIONS["PII_MAX_CHARACTERS_CODE"] in message


def test_pii_max_characters_code_accepts_the_boundary_value_of_one():
    """The boundary on the accepted side, so a `<= 1` typo fails here, not in STORY-010."""
    result = _settings(DATABASE_URL=_LOCAL_URL, PII_MAX_CHARACTERS_CODE=1)

    assert result.PII_MAX_CHARACTERS_CODE == 1


def test_pii_entities_code_list_parses_like_pii_entities_list():
    """AC 4: the same input through both properties gives the same list."""
    raw = " EMAIL_ADDRESS , ,US_SSN ,"
    result = _settings(DATABASE_URL=_LOCAL_URL, PII_ENTITIES=raw, PII_ENTITIES_CODE=raw)

    assert result.pii_entities_code_list == result.pii_entities_list == ["EMAIL_ADDRESS", "US_SSN"]


def test_existing_pii_settings_keep_their_defaults():
    """AC 5: the values tests/test_pii_characterization.py pins as shipped."""
    result = _settings(DATABASE_URL=_LOCAL_URL)

    assert result.PII_REDACTION_ENABLED is True
    assert result.PII_SCORE_THRESHOLD == 0.35
    assert result.PII_ENTITIES == "PERSON,EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE,LOCATION"
    assert result.PII_NLP_MODEL == "en_core_web_lg"


def test_existing_pii_settings_gained_no_validation():
    """AC 5's "validation unchanged", and the assertion with teeth.

    The new validators are `code`-only. `chat`'s settings are PRD-003's and
    had none; a validator that crept onto them would turn this red.
    """
    result = _settings(DATABASE_URL=_LOCAL_URL, PII_ENTITIES="NOT_A_TYPE", PII_SCORE_THRESHOLD=5)

    assert result.pii_entities_list == ["NOT_A_TYPE"]
    assert result.PII_SCORE_THRESHOLD == 5


# --- PRD-012 STORY-014: .env.example documents the six PII code settings -----
#
# STORY-005 left `.env.example` to this story. The six are documented in their
# own group, in field order, with the defaults the fields carry; and the four
# existing PII_* comments now say which profile each one governs (plan D3).

_EXISTING_PII_VARS = ("PII_REDACTION_ENABLED", "PII_SCORE_THRESHOLD", "PII_ENTITIES", "PII_NLP_MODEL")


def _env_example_value(text: str, var: str) -> str:
    match = re.search(rf"(?m)^{var}=(.*)$", text)
    assert match, f"{var} is not assigned in .env.example"
    return match.group(1).strip()


def test_env_example_documents_every_pii_code_var_with_a_comment():
    """PRD-012 STORY-014 AC 4: all six present, each with an explanation above it."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for var in _PII_CODE_VARS:
        assert re.search(rf"(?m)^#.+\n{var}=", text), f"{var} missing from .env.example or missing its comment line"


def test_env_example_pii_code_vars_appear_in_settings_field_order():
    """PRD-012 STORY-014 AC 4. The order is read from `Settings.model_fields`,
    not from a literal, so a field moved in `app/config.py` moves the
    expectation with it."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    declared_order = [name for name in Settings.model_fields if name in _PII_CODE_VARS]

    assert sorted(declared_order) == sorted(_PII_CODE_VARS)
    positions = [text.index(f"{var}=") for var in declared_order]

    assert positions == sorted(positions)


def test_env_example_pii_code_defaults_match_settings():
    """PRD-012 STORY-014 AC 4's "with defaults", compared against the fields.

    Read as the strings a `.env` supplies: `200000` there is `200_000` in the
    field, and booleans are lowercase.
    """
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    defaults = {name: Settings.model_fields[name].default for name in _PII_CODE_VARS}

    assert _env_example_value(text, "PII_ENTITIES_CODE") == defaults["PII_ENTITIES_CODE"]
    assert float(_env_example_value(text, "PII_SCORE_THRESHOLD_CODE")) == defaults["PII_SCORE_THRESHOLD_CODE"]
    assert int(_env_example_value(text, "PII_MAX_CHARACTERS_CODE")) == defaults["PII_MAX_CHARACTERS_CODE"]
    for var in ("PII_CODE_REDACT_OUTPUT", "PII_CODE_REDACT_SYSTEM", "PII_CODE_SKIP_CODE_BLOCKS"):
        assert _env_example_value(text, var) == str(defaults[var]).lower()


def test_env_example_existing_pii_comments_name_their_profile():
    """PRD-012 STORY-014 AC 4: the four existing PII_* settings say they apply
    to `chat`.

    Asserted on substance rather than on an exact sentence, so rewording stays
    a docs change. The master switch must also name `code`: it turns off every
    profile, and a comment reading "chat" alone would say `code` cannot be
    switched off (plan D3).
    """
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for var in _EXISTING_PII_VARS:
        comment = re.search(rf"(?m)((?:^#.*\n)+){var}=", text)
        assert comment, f"{var} has no comment block above it"
        block = comment.group(1).lower()
        assert "chat" in block, f"{var}'s comment does not say it applies to the chat profile"
        if var == "PII_REDACTION_ENABLED":
            assert "code" in block, "PII_REDACTION_ENABLED's comment must say it also governs code"


# --- PRD-013 STORY-007: usage-limit and break-glass settings -----------------
#
# Nothing reads these four yet -- STORY-010 (limit resolution), STORY-011 (the
# gate), STORY-012 (the charge) and STORY-013 (the break-glass ingress policy)
# are the consumers. What is asserted here is the defaults, the two parsed
# shapes, and that every malformed value stops construction with a message
# naming the setting, quoting the offending entry and showing a valid example.
# `.env.example` is STORY-018's, not this block's.

from app.config import _LIMIT_MAP_EXAMPLES  # noqa: E402

_USAGE_VARS = (
    "USAGE_LIMITS_ENABLED",
    "USAGE_DAILY_TOKEN_BUDGET",
    "USAGE_REQUESTS_PER_MINUTE",
    "BREAK_GLASS_INGRESSES",
)

# Each limit-map setting and the property that parses it.
_LIMIT_MAP_PROPERTIES = {
    "USAGE_DAILY_TOKEN_BUDGET": "usage_daily_token_budget_map",
    "USAGE_REQUESTS_PER_MINUTE": "usage_requests_per_minute_map",
}


def test_usage_settings_available_with_documented_defaults(monkeypatch):
    """AC 1, with the developer's exported environment taken out of it."""
    for var in _USAGE_VARS:
        monkeypatch.delenv(var, raising=False)

    result = _settings(DATABASE_URL=_LOCAL_URL)

    assert result.USAGE_LIMITS_ENABLED is True
    assert result.USAGE_DAILY_TOKEN_BUDGET == "*=1000000"
    assert result.USAGE_REQUESTS_PER_MINUTE == "*=60"
    assert result.BREAK_GLASS_INGRESSES == "query,chat"
    assert result.usage_daily_token_budget_map == {"*": 1000000}
    assert result.usage_requests_per_minute_map == {"*": 60}
    assert result.break_glass_ingresses == frozenset({"query", "chat"})


def test_usage_limits_enabled_parses_the_string_false():
    """Asserted with `is`, as the earlier blocks do for their switches."""
    assert _settings(DATABASE_URL=_LOCAL_URL, USAGE_LIMITS_ENABLED="false").USAGE_LIMITS_ENABLED is False


@pytest.mark.parametrize("setting", sorted(_LIMIT_MAP_PROPERTIES))
def test_limit_map_parses_roles_and_unlimited(setting):
    """AC 2's example, over both settings: one parser serves both."""
    result = _settings(DATABASE_URL=_LOCAL_URL, **{setting: "*=60,admin=unlimited,auditor=10"})

    assert getattr(result, _LIMIT_MAP_PROPERTIES[setting]) == {"*": 60, "admin": None, "auditor": 10}


def test_limit_map_strips_whitespace_and_accepts_an_unlimited_star():
    """Whitespace around roles and values is a `.env` habit, not an error;
    `*` itself may be unlimited."""
    spaced = _settings(DATABASE_URL=_LOCAL_URL, USAGE_REQUESTS_PER_MINUTE=" * = 5 , admin=unlimited ,")
    unbounded = _settings(DATABASE_URL=_LOCAL_URL, USAGE_DAILY_TOKEN_BUDGET="*=unlimited")

    assert spaced.usage_requests_per_minute_map == {"*": 5, "admin": None}
    assert unbounded.usage_daily_token_budget_map == {"*": None}


@pytest.mark.parametrize("setting", sorted(_LIMIT_MAP_PROPERTIES))
@pytest.mark.parametrize(
    "value,offending",
    [
        ("admin=10", "admin=10"),  # no `*` entry: the whole value is quoted
        ("", ""),  # empty: no entries, so no `*`
        ("*=0", "*=0"),
        ("*=-5", "*=-5"),
        ("*=abc", "*=abc"),
        ("*=1.5", "*=1.5"),
        ("*=1_000", "*=1_000"),
        ("*=60,admin=Unlimited", "admin=Unlimited"),
        ("*=60,admin=1,admin=2", "'admin'"),  # role twice
        ("*=60,admin", "'admin'"),  # no `=`
        ("*=60,=5", "'=5'"),  # empty role
    ],
)
def test_an_invalid_limit_map_is_a_startup_error(setting, value, offending):
    """AC 3: the setting, the offending entry and that setting's own example."""
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, **{setting: value})

    message = str(exc_info.value)
    assert setting in message
    assert offending in message
    assert _LIMIT_MAP_EXAMPLES[setting] in message


def test_a_zero_limit_names_the_real_off_switch():
    """0 reads like "off" and is not; the message says what is."""
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, USAGE_DAILY_TOKEN_BUDGET="*=0")

    assert "USAGE_LIMITS_ENABLED" in str(exc_info.value)


def test_limit_map_role_names_are_not_checked_against_rbac():
    """PRD-013 Section 6.6: RBAC_ROLES_FILE may define any role and loads later."""
    result = _settings(DATABASE_URL=_LOCAL_URL, USAGE_REQUESTS_PER_MINUTE="*=1,no-such-role=2")

    assert result.usage_requests_per_minute_map == {"*": 1, "no-such-role": 2}


@pytest.mark.parametrize(
    "value,expected",
    [
        ("", frozenset()),
        ("chat", frozenset({"chat"})),
        ("query", frozenset({"query"})),
        ("query,chat", frozenset({"query", "chat"})),
        (" chat , chat ", frozenset({"chat"})),
    ],
)
def test_break_glass_ingresses_accepts_any_subset_of_query_and_chat(value, expected):
    """AC 4's first clause, including empty: the setting can tighten to nothing."""
    assert _settings(DATABASE_URL=_LOCAL_URL, BREAK_GLASS_INGRESSES=value).break_glass_ingresses == expected


@pytest.mark.parametrize("value", ["v1", "query,v1"])
def test_break_glass_ingresses_refuses_v1(value):
    """AC 4's second clause: the message says the token is never accepted there."""
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, BREAK_GLASS_INGRESSES=value)

    message = str(exc_info.value)
    assert "BREAK_GLASS_INGRESSES" in message
    assert "ADMIN_TOKEN" in message
    assert "/v1" in message


@pytest.mark.parametrize("value,bad", [("admin", "admin"), ("Chat", "Chat"), ("query,console", "console")])
def test_break_glass_ingresses_refuses_an_unknown_name(value, bad):
    """AC 4's third clause: the accepted values are named, and the `/v1`
    message is not reused for a name that is merely unknown."""
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, BREAK_GLASS_INGRESSES=value)

    message = str(exc_info.value)
    assert "BREAK_GLASS_INGRESSES" in message
    assert bad in message
    assert "chat, query" in message
    assert "/v1" not in message


# --- PRD-013 STORY-018: .env.example documents the usage-limit settings ------
#
# STORY-007 added the four fields and left `.env.example` to this story. They
# are documented in their own group, in field order, with the defaults the
# fields carry; and the ADMIN_TOKEN comment now says where the token is refused.

_USAGE_VARS = (
    "USAGE_LIMITS_ENABLED",
    "USAGE_DAILY_TOKEN_BUDGET",
    "USAGE_REQUESTS_PER_MINUTE",
    "BREAK_GLASS_INGRESSES",
)


def _env_example_comment(text: str, var: str) -> str:
    comment = re.search(rf"(?m)((?:^#.*\n)+){var}=", text)
    assert comment, f"{var} has no comment block above it"
    return comment.group(1)


def test_env_example_documents_every_usage_var_with_a_comment():
    """PRD-013 STORY-018 AC 4: all four present, each with an explanation above it."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for var in _USAGE_VARS:
        assert re.search(rf"(?m)^#.+\n{var}=", text), f"{var} missing from .env.example or missing its comment line"


def test_env_example_usage_vars_appear_in_settings_field_order():
    """PRD-013 STORY-018 AC 4. The order is read from `Settings.model_fields`,
    so a field moved in `app/config.py` moves the expectation with it."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    declared_order = [name for name in Settings.model_fields if name in _USAGE_VARS]

    assert sorted(declared_order) == sorted(_USAGE_VARS)
    positions = [text.index(f"{var}=") for var in declared_order]

    assert positions == sorted(positions)


def test_env_example_usage_defaults_match_settings():
    """PRD-013 STORY-018 AC 4: the template carries the shipped defaults, not
    the validator's examples (`admin=120`, `admin=unlimited`)."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    defaults = {name: Settings.model_fields[name].default for name in _USAGE_VARS}

    assert _env_example_value(text, "USAGE_LIMITS_ENABLED") == str(defaults["USAGE_LIMITS_ENABLED"]).lower()
    for var in ("USAGE_DAILY_TOKEN_BUDGET", "USAGE_REQUESTS_PER_MINUTE", "BREAK_GLASS_INGRESSES"):
        assert _env_example_value(text, var) == defaults[var]


def test_env_example_admin_token_comment_names_v1_and_the_setting():
    """PRD-013 STORY-018 AC 4: the ADMIN_TOKEN entry says it is refused on /v1
    and names the setting that can refuse it elsewhere (Section 9.3)."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    block = _env_example_comment(text, "ADMIN_TOKEN")

    assert "v1" in block
    assert "BREAK_GLASS_INGRESSES" in block


def test_env_example_says_what_disabling_usage_limits_does():
    """PRD-013 STORY-018 AC 4, on substance rather than an exact sentence: the
    off state writes and reads no counter."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    block = _env_example_comment(text, "USAGE_LIMITS_ENABLED").lower()

    assert "false" in block
    assert "counter" in block


# --- PRD-015 STORY-002: OPENROUTER_BASE_URL ------------------------------------
#
# The validator is PRD-015 Section 9.2 T10's mitigation: every call sends
# OPENROUTER_API_KEY to this URL, so only https:// or a loopback http:// host
# boots.

_BASE_URL_RULE_FRAGMENTS = ("OPENROUTER_BASE_URL", "https://", "127.0.0.1", "localhost", "::1", "Example")


def test_openrouter_base_url_defaults_to_openrouter():
    assert _settings(DATABASE_URL=_LOCAL_URL).OPENROUTER_BASE_URL == "https://openrouter.ai/api/v1"


@pytest.mark.parametrize(
    "url",
    [
        pytest.param("https://openrouter.ai/api/v1", id="default"),
        pytest.param("HTTPS://openrouter.ai/api/v1", id="upper-scheme"),
        pytest.param("https://proxy.internal.example/v1", id="other-https-host"),
        pytest.param("https://openrouter.ai/api/v1/", id="trailing-slash"),
        pytest.param("http://127.0.0.1:9100/v1", id="ipv4-loopback"),
        pytest.param("http://localhost:9100/v1", id="localhost"),
        pytest.param("http://LOCALHOST:9100/v1", id="localhost-upper"),
        pytest.param("http://[::1]:9100/v1", id="ipv6-loopback"),
    ],
)
def test_openrouter_base_url_accepts_https_or_loopback_http(url):
    assert _settings(DATABASE_URL=_LOCAL_URL, OPENROUTER_BASE_URL=url).OPENROUTER_BASE_URL == url


def test_openrouter_base_url_surrounding_whitespace_is_stripped():
    result = _settings(DATABASE_URL=_LOCAL_URL, OPENROUTER_BASE_URL="  http://127.0.0.1:9100/v1\n")

    assert result.OPENROUTER_BASE_URL == "http://127.0.0.1:9100/v1"


@pytest.mark.parametrize(
    "url",
    [
        pytest.param("http://example.com/v1", id="http-remote"),
        pytest.param("http://127.0.0.2/v1", id="http-other-127"),
        pytest.param("http://localhost.example.com/v1", id="http-localhost-prefix"),
        pytest.param("ftp://127.0.0.1/v1", id="ftp"),
        pytest.param("", id="empty"),
        pytest.param("   ", id="blank"),
        pytest.param("openrouter.ai/api/v1", id="no-scheme"),
        pytest.param("https://", id="no-host"),
    ],
)
def test_openrouter_base_url_rejection_names_the_setting_rule_and_an_example(url):
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, OPENROUTER_BASE_URL=url)

    message = str(exc_info.value)
    for fragment in _BASE_URL_RULE_FRAGMENTS:
        assert fragment in message, fragment


@pytest.mark.parametrize(
    "url",
    [
        pytest.param(f"http://user:{_TOKEN_SENTINEL}@example.com/v1", id="userinfo"),
        pytest.param(f"ftp://127.0.0.1/{_TOKEN_SENTINEL}", id="path"),
        pytest.param(f"https://?key={_TOKEN_SENTINEL}", id="query-no-host"),
    ],
)
def test_openrouter_base_url_rejection_never_echoes_the_value(url):
    """Messages quote the scheme and host only (`_scheme_of`'s rule), and
    hide_input_in_errors keeps pydantic from appending the raw value."""
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, OPENROUTER_BASE_URL=url)

    assert _TOKEN_SENTINEL not in str(exc_info.value)


# --- PRD-015 STORY-003: V1_ENABLED and V1_SSE_KEEPALIVE_SECONDS --------------
#
# Nothing reads these yet -- STORY-009 mounts /v1 from V1_ENABLED and
# STORY-013 paces keep-alive lines from V1_SSE_KEEPALIVE_SECONDS.
# `.env.example` is STORY-019's, not this block's.

_V1_VARS = ("V1_ENABLED", "V1_SSE_KEEPALIVE_SECONDS")
_KEEPALIVE_RULE_FRAGMENTS = ("V1_SSE_KEEPALIVE_SECONDS", "> 0", "<= 60", "Example")


def test_v1_settings_available_with_documented_defaults(monkeypatch):
    """AC 1, with the developer's exported environment taken out of it."""
    for var in _V1_VARS:
        monkeypatch.delenv(var, raising=False)

    result = _settings(DATABASE_URL=_LOCAL_URL)

    assert result.V1_ENABLED is True
    assert result.V1_SSE_KEEPALIVE_SECONDS == 10


def test_v1_enabled_parses_the_string_false():
    """AC 3. Asserted with `is`, as the earlier blocks do for their switches."""
    assert _settings(DATABASE_URL=_LOCAL_URL, V1_ENABLED="false").V1_ENABLED is False


@pytest.mark.parametrize(
    "value,shown",
    [
        (0, "got 0"),
        (-1, "got -1"),
        (61, "got 61"),
        ("0", "got 0"),
        (60.01, "got 60.01"),
        ("nan", "got nan"),
        ("inf", "got inf"),
    ],
)
def test_v1_sse_keepalive_seconds_out_of_range_is_a_startup_error(value, shown):
    """AC 2: names the setting, the value, the accepted range and an example.

    `"nan"` and `"inf"` parse as floats, so the range check itself must turn
    them away -- which `not 0 < value <= 60` does.
    """
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, V1_SSE_KEEPALIVE_SECONDS=value)

    message = str(exc_info.value)
    for fragment in _KEEPALIVE_RULE_FRAGMENTS:
        assert fragment in message, fragment
    assert shown in message


@pytest.mark.parametrize("value", [0.5, 60, "60"])
def test_v1_sse_keepalive_seconds_accepts_the_range_bounds(value):
    result = _settings(DATABASE_URL=_LOCAL_URL, V1_SSE_KEEPALIVE_SECONDS=value)

    assert result.V1_SSE_KEEPALIVE_SECONDS == float(value)


def test_no_setting_chooses_the_v1_profile():
    """PRD-015 Section 9.3: the /v1 profile is the literal "code" at the call
    site (PRD-011 D2), never a setting."""
    assert not [name for name in Settings.model_fields if name.startswith("V1_") and "PROFILE" in name]


# --- PRD-015 STORY-019: .env.example documents the three /v1 settings ---------
#
# STORY-002 and STORY-003 added the fields and left `.env.example` to this
# story. Each is present with an explanation above it, in field order, with the
# shipped default; OPENROUTER_BASE_URL's comment carries T10's rule.

_V1_VARS = ("OPENROUTER_BASE_URL", "V1_ENABLED", "V1_SSE_KEEPALIVE_SECONDS")


def test_env_example_documents_the_v1_vars_with_a_comment_in_field_order():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    declared_order = [name for name in Settings.model_fields if name in _V1_VARS]

    assert sorted(declared_order) == sorted(_V1_VARS)
    for var in _V1_VARS:
        assert re.search(rf"(?m)^#.+\n{var}=", text), f"{var} missing from .env.example or missing its comment line"
    positions = [text.index(f"{var}=") for var in declared_order]
    assert positions == sorted(positions)


def test_env_example_v1_defaults_match_settings():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    defaults = {name: Settings.model_fields[name].default for name in _V1_VARS}

    assert _env_example_value(text, "OPENROUTER_BASE_URL") == defaults["OPENROUTER_BASE_URL"]
    assert _env_example_value(text, "V1_ENABLED") == str(defaults["V1_ENABLED"]).lower()
    assert float(_env_example_value(text, "V1_SSE_KEEPALIVE_SECONDS")) == defaults["V1_SSE_KEEPALIVE_SECONDS"]


def test_env_example_base_url_comment_states_the_t10_rule():
    """PRD-015 T10: a non-loopback http:// host would receive the key."""
    block = _env_example_comment((REPO_ROOT / ".env.example").read_text(encoding="utf-8"), "OPENROUTER_BASE_URL")

    for fragment in ("https://", "loopback", "127.0.0.1", "OPENROUTER_API_KEY", "T10"):
        assert fragment in block, fragment


# --- PRD-016 STORY-005: action policy settings ---
#
# Nothing reads these three yet: action_config (STORY-006/007/008) and
# action_policy (STORY-014) are the consumers. Their .env.example lines are
# STORY-020's (the last two tests of this section), and the check that ACTION_SQL_DIALECT names a dialect sqlglot
# knows belongs to STORY-008's action_config.load().

_ACTION_VARS = ("ACTION_POLICY_FILE", "ACTION_MAX_ARGUMENT_CHARACTERS", "ACTION_SQL_DIALECT")


def test_action_settings_available_with_documented_defaults(monkeypatch):
    """AC 1: the three settings exist with PRD-016 Section 9.3's defaults."""
    for var in _ACTION_VARS:
        monkeypatch.delenv(var, raising=False)

    result = _settings(DATABASE_URL=_LOCAL_URL)

    assert result.ACTION_POLICY_FILE == ""
    assert result.ACTION_MAX_ARGUMENT_CHARACTERS == 100_000
    assert result.ACTION_SQL_DIALECT == ""


@pytest.mark.parametrize("value", [0, -1, "0"])
def test_an_action_max_argument_characters_below_one_is_a_startup_error(value):
    """AC 1: 0 reads like "no ceiling" and is not one, so the message names the
    field, the value, what it bounds and what to set instead."""
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, ACTION_MAX_ARGUMENT_CHARACTERS=value)

    message = str(exc_info.value)
    assert "ACTION_MAX_ARGUMENT_CHARACTERS" in message
    assert f"got {int(value)}" in message, "the message must quote the value it rejected"
    assert "tool.malformed" in message, "the message must say what the field bounds"
    assert "ACTION_MAX_ARGUMENT_CHARACTERS=100000" in message, "the message must say what to set instead"


def test_action_max_argument_characters_accepts_the_boundary_value_of_one():
    assert _settings(DATABASE_URL=_LOCAL_URL, ACTION_MAX_ARGUMENT_CHARACTERS=1).ACTION_MAX_ARGUMENT_CHARACTERS == 1


def test_action_sql_dialect_is_only_a_string_here():
    """The assertion with teeth: no sqlglot check slipped into Settings. A name
    no dialect has is accepted here and refused by STORY-008's loader."""
    assert _settings(DATABASE_URL=_LOCAL_URL, ACTION_SQL_DIALECT="nosuchdb").ACTION_SQL_DIALECT == "nosuchdb"


def test_action_policy_file_is_not_read_by_settings(tmp_path):
    """A path that does not resolve constructs fine: the file is action_config's
    to read (STORY-006/007), not Settings'."""
    missing = str(tmp_path / "missing.yaml")

    assert _settings(DATABASE_URL=_LOCAL_URL, ACTION_POLICY_FILE=missing).ACTION_POLICY_FILE == missing


def test_env_example_documents_the_action_policy_vars_with_a_comment():
    """PRD-016 STORY-020 AC 3: all three present, each with a comment line above."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for var in _ACTION_VARS:
        assert re.search(rf"(?m)^#.+\n{var}=", text), f"{var} missing from .env.example or missing its comment line"


def test_env_example_action_policy_defaults_match_settings():
    """The documented values are the defaults, and the vars follow Settings order."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    defaults = {name: Settings.model_fields[name].default for name in _ACTION_VARS}

    assert _env_example_value(text, "ACTION_POLICY_FILE") == defaults["ACTION_POLICY_FILE"]
    assert int(_env_example_value(text, "ACTION_MAX_ARGUMENT_CHARACTERS")) == defaults["ACTION_MAX_ARGUMENT_CHARACTERS"]
    assert _env_example_value(text, "ACTION_SQL_DIALECT") == defaults["ACTION_SQL_DIALECT"]
    positions = [text.index(f"{var}=") for var in _ACTION_VARS]
    assert positions == sorted(positions)


# --- PRD-017 STORY-002: V1_TOOLS_ENABLED and V1_TOOL_MODELS -------------------
# STORY-008 (the translator) and STORY-010 (step 7c) read them now; the last two
# tests of this section, the .env.example ones, are STORY-018's.


def test_tool_settings_available_with_documented_defaults(monkeypatch):
    for var in ("V1_TOOLS_ENABLED", "V1_TOOL_MODELS"):
        monkeypatch.delenv(var, raising=False)
    result = _settings(DATABASE_URL=_LOCAL_URL)

    assert result.V1_TOOLS_ENABLED is False
    assert result.V1_TOOL_MODELS == ""
    assert result.v1_tool_models_list == []


def test_v1_tools_enabled_parses_the_string_true():
    assert _settings(DATABASE_URL=_LOCAL_URL, V1_TOOLS_ENABLED="true").V1_TOOLS_ENABLED is True


def test_v1_tool_models_list_returns_stripped_names_in_order():
    result = _settings(
        DATABASE_URL=_LOCAL_URL,
        MODEL_ALLOWLIST="gpt-4,openai/gpt-4o,anthropic/claude-3.5-sonnet",
        V1_TOOL_MODELS="openai/gpt-4o, anthropic/claude-3.5-sonnet",
    )

    assert result.v1_tool_models_list == ["openai/gpt-4o", "anthropic/claude-3.5-sonnet"]


@pytest.mark.parametrize(
    ("allowlist", "tool_models", "offending"),
    [
        ("gpt-4,openai/gpt-4o", "openai/gpt-4o, mistral/x", "mistral/x"),
        ("gpt-4,openai/gpt-4o", "OpenAI/GPT-4o", "OpenAI/GPT-4o"),
        ("", "openai/gpt-4o", "openai/gpt-4o"),
    ],
    ids=["one-bad-among-good", "case-mismatch", "empty-allowlist"],
)
def test_v1_tool_models_entry_outside_model_allowlist_is_a_startup_error(allowlist, tool_models, offending):
    """The list has no admin exemption: admin's any-model allowance is not
    consulted at startup, so the empty-allowlist case fails too (PRD-017 D3)."""
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, MODEL_ALLOWLIST=allowlist, V1_TOOL_MODELS=tool_models)

    message = str(exc_info.value)
    for fragment in ("V1_TOOL_MODELS", "MODEL_ALLOWLIST", "Example", offending):
        assert fragment in message, fragment
    # The good entry is not reported as offending.
    assert "not in MODEL_ALLOWLIST: openai/gpt-4o, " not in message


@pytest.mark.parametrize("value", ["   ", " , ,"])
def test_v1_tool_models_blank_parses_to_no_restriction(value):
    result = _settings(DATABASE_URL=_LOCAL_URL, MODEL_ALLOWLIST="gpt-4", V1_TOOL_MODELS=value)

    assert result.v1_tool_models_list == []


_TOOL_VARS = ("V1_TOOLS_ENABLED", "V1_TOOL_MODELS")


def test_env_example_documents_the_tool_vars_with_a_comment():
    """PRD-017 STORY-018 AC 4: both present, each with a comment line above."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for var in _TOOL_VARS:
        assert re.search(rf"(?m)^#.+\n{var}=", text), f"{var} missing from .env.example or missing its comment line"


def test_env_example_tool_defaults_match_settings():
    """The documented values are the defaults, and the vars sit in Settings order:
    after V1_SSE_KEEPALIVE_SECONDS and before ACTION_POLICY_FILE (app/config.py)."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    defaults = {name: Settings.model_fields[name].default for name in _TOOL_VARS}

    assert _env_example_value(text, "V1_TOOLS_ENABLED") == str(defaults["V1_TOOLS_ENABLED"]).lower()
    assert _env_example_value(text, "V1_TOOL_MODELS") == defaults["V1_TOOL_MODELS"]
    positions = [text.index(f"{var}=") for var in _TOOL_VARS]
    assert positions == sorted(positions)
    assert text.index("V1_SSE_KEEPALIVE_SECONDS=") < positions[0]
    assert positions[-1] < text.index("ACTION_POLICY_FILE=")


# --- PRD-018 STORY-008: audit journal settings ---


def test_audit_buffer_settings_have_the_documented_defaults():
    """PRD-018 9.3: the defaults, and they satisfy the minimum for the default worker count."""
    config = _settings()
    assert config.AUDIT_BUFFER_DIR == "./var/audit-buffer"
    assert config.AUDIT_BUFFER_MAX_BYTES == 67108864  # 32 x 131072 = 4 MiB <= 64 MiB


@pytest.mark.parametrize("value", ["", "   "])
def test_audit_buffer_dir_empty_is_a_startup_error(value):
    with pytest.raises(ValidationError) as exc_info:
        _settings(AUDIT_BUFFER_DIR=value)
    assert "AUDIT_BUFFER_DIR" in str(exc_info.value)


@pytest.mark.parametrize("value", [4 * 65536 * 2 - 1, "0"])
def test_audit_buffer_max_bytes_below_two_reserves_per_worker_is_a_startup_error(value):
    with pytest.raises(ValidationError) as exc_info:
        _settings(PIPELINE_MAX_WORKERS=4, AUDIT_BUFFER_MAX_BYTES=value)
    message = str(exc_info.value)
    assert "AUDIT_BUFFER_MAX_BYTES" in message and "PIPELINE_MAX_WORKERS" in message


def test_audit_buffer_max_bytes_exact_minimum_is_accepted():
    assert _settings(PIPELINE_MAX_WORKERS=4, AUDIT_BUFFER_MAX_BYTES=4 * 65536 * 2).AUDIT_BUFFER_MAX_BYTES == 524288


def test_settings_construction_does_not_touch_the_audit_buffer_dir(tmp_path):
    """PRD-018 STORY-008: the directory is created when the journal opens, never at settings load."""
    target = tmp_path / "never"
    _settings(AUDIT_BUFFER_DIR=str(target))
    assert not target.exists()


def test_reserve_constant_is_the_journals():
    from app import config
    from app.db import audit_journal

    assert config._JOURNAL_ENTRY_RESERVE_BYTES is audit_journal._JOURNAL_ENTRY_RESERVE_BYTES
    assert audit_journal._JOURNAL_ENTRY_RESERVE_BYTES == 65536


# --- PRD-018 STORY-014: .env.example documents the audit journal settings -----

_AUDIT_BUFFER_VARS = ("AUDIT_BUFFER_DIR", "AUDIT_BUFFER_MAX_BYTES")


def test_env_example_documents_both_audit_buffer_vars_with_a_comment():
    """PRD-018 STORY-014 AC 2: both present, each with an explanation directly above it."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for var in _AUDIT_BUFFER_VARS:
        assert re.search(rf"(?m)^#.+\n{var}=", text), f"{var} missing from .env.example or missing its comment line"


def test_env_example_audit_buffer_vars_appear_in_settings_field_order():
    """PRD-018 STORY-014 AC 2. The order is read from `Settings.model_fields`."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    declared_order = [name for name in Settings.model_fields if name in _AUDIT_BUFFER_VARS]

    assert sorted(declared_order) == sorted(_AUDIT_BUFFER_VARS)
    positions = [text.index(f"{var}=") for var in declared_order]

    assert positions == sorted(positions)


def test_env_example_audit_buffer_defaults_match_settings():
    """PRD-018 STORY-014 AC 2: the template carries the shipped defaults (PRD 9.3)."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    assert _env_example_value(text, "AUDIT_BUFFER_DIR") == Settings.model_fields["AUDIT_BUFFER_DIR"].default
    assert int(_env_example_value(text, "AUDIT_BUFFER_MAX_BYTES")) == Settings.model_fields["AUDIT_BUFFER_MAX_BYTES"].default


# --- PRD-019 STORY-001: readiness settings (Section 9.3, D3) -----------------


def test_readiness_settings_defaults():
    """PRD-019 STORY-001 AC 1: shipped defaults (Section 9.3)."""
    s = _settings()

    assert s.DRAIN_FILE == "/tmp/harness-drain"
    assert s.READY_DB_TIMEOUT_SECONDS == 2.0


@pytest.mark.parametrize("bad", ["", "   ", "relative/x", "C:rel"])
def test_drain_file_rejects_non_absolute_paths(bad):
    """PRD-019 STORY-001 AC 1: empty or relative values fail naming the setting."""
    with pytest.raises(ValidationError) as excinfo:
        _settings(DRAIN_FILE=bad)

    assert "DRAIN_FILE" in str(excinfo.value)
    assert "absolute" in str(excinfo.value)


@pytest.mark.parametrize("good", ["/tmp/x", r"C:\tmp\x", r"\\server\share\drain"])
def test_drain_file_accepts_posix_windows_and_unc_absolute_paths(good):
    """PRD-019 STORY-001 AC 1 (orchestrator decision): POSIX or Windows absolute."""
    assert _settings(DRAIN_FILE=good).DRAIN_FILE == good


@pytest.mark.parametrize("bad", [0, -1, 10.01, float("nan"), "abc"])
def test_ready_db_timeout_rejects_out_of_range_values(bad):
    """PRD-019 STORY-001 AC 1: must be > 0 and <= 10, and the message names the setting."""
    with pytest.raises(ValidationError) as excinfo:
        _settings(READY_DB_TIMEOUT_SECONDS=bad)

    assert "READY_DB_TIMEOUT_SECONDS" in str(excinfo.value)


def test_ready_db_timeout_message_states_the_rule():
    with pytest.raises(ValidationError) as excinfo:
        _settings(READY_DB_TIMEOUT_SECONDS=0)

    assert "greater than 0 and at most 10" in str(excinfo.value)


@pytest.mark.parametrize("good", [0.5, 10])
def test_ready_db_timeout_accepts_the_range(good):
    assert _settings(READY_DB_TIMEOUT_SECONDS=good).READY_DB_TIMEOUT_SECONDS == good


# --- PRD-020 STORY-002: PROVIDERS_FILE and the conditional OPENROUTER_API_KEY --


def _no_key_settings(monkeypatch, **overrides) -> Settings:
    """Settings with OPENROUTER_API_KEY genuinely unset (conftest sets it in os.environ)."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("PROVIDERS_FILE", raising=False)
    base = {"ADMIN_TOKEN": "test-token", "DATABASE_URL": _LOCAL_URL}
    return Settings(_env_file=None, **{**base, **overrides})


def test_openrouter_api_key_is_no_longer_a_required_field():
    # PRD-020 D1: it was required; now empty is a valid default, checked conditionally.
    field = Settings.model_fields["OPENROUTER_API_KEY"]
    assert not field.is_required()
    assert field.default == ""


def test_no_file_and_no_key_is_a_startup_error_naming_the_key(monkeypatch):
    with pytest.raises(ValidationError) as excinfo:
        _no_key_settings(monkeypatch)
    message = str(excinfo.value)
    assert "OPENROUTER_API_KEY" in message
    assert "PROVIDERS_FILE" in message

    with pytest.raises(ValidationError) as excinfo:
        _no_key_settings(monkeypatch, ADMIN_TOKEN=_TOKEN_SENTINEL)
    assert _TOKEN_SENTINEL not in str(excinfo.value)


def test_no_file_and_empty_string_key_is_a_startup_error(monkeypatch):
    with pytest.raises(ValidationError) as excinfo:
        _no_key_settings(monkeypatch, OPENROUTER_API_KEY="")
    assert "OPENROUTER_API_KEY" in str(excinfo.value)


def test_providers_file_set_and_no_key_constructs(monkeypatch, tmp_path):
    result = _no_key_settings(monkeypatch, PROVIDERS_FILE=str(tmp_path / "missing.yaml"))
    assert result.OPENROUTER_API_KEY == ""


def test_providers_file_is_not_read_by_settings(tmp_path):
    # PRD-020 STORY-002 AC5: a nonexistent path constructs and round-trips.
    path = str(tmp_path / "does-not-exist.yaml")
    assert _settings(DATABASE_URL=_LOCAL_URL, PROVIDERS_FILE=path).PROVIDERS_FILE == path
    assert _settings(DATABASE_URL=_LOCAL_URL).PROVIDERS_FILE == ""


def test_providers_file_with_v1_tool_models_is_a_startup_error(tmp_path):
    path = str(tmp_path / "providers.yaml")
    with pytest.raises(ValidationError) as excinfo:
        _settings(
            DATABASE_URL=_LOCAL_URL,
            PROVIDERS_FILE=path,
            MODEL_ALLOWLIST="gpt-4,openai/gpt-4o",
            V1_TOOL_MODELS="openai/gpt-4o",
        )
    message = str(excinfo.value)
    for fragment in ("V1_TOOL_MODELS", "PROVIDERS_FILE", "D6", "registry"):
        assert fragment in message
    assert "not in MODEL_ALLOWLIST" not in message

    # PRD-020 D6 ordering: an entry outside the allowlist still gets the D6 message.
    with pytest.raises(ValidationError) as excinfo:
        _settings(
            DATABASE_URL=_LOCAL_URL,
            PROVIDERS_FILE=path,
            MODEL_ALLOWLIST="gpt-4",
            V1_TOOL_MODELS="other/model",
        )
    assert "D6" in str(excinfo.value)
    assert "not in MODEL_ALLOWLIST" not in str(excinfo.value)


@pytest.mark.parametrize("blank", ["", "   ", " , ,"])
def test_providers_file_with_blank_v1_tool_models_passes(tmp_path, blank):
    result = _settings(
        DATABASE_URL=_LOCAL_URL,
        PROVIDERS_FILE=str(tmp_path / "providers.yaml"),
        V1_TOOL_MODELS=blank,
    )
    assert result.v1_tool_models_list == []


def test_no_file_with_v1_tool_models_still_validates_as_before():
    result = _settings(
        DATABASE_URL=_LOCAL_URL,
        MODEL_ALLOWLIST="gpt-4,openai/gpt-4o",
        V1_TOOL_MODELS="openai/gpt-4o",
    )
    assert result.v1_tool_models_list == ["openai/gpt-4o"]


# --- PRD-021 STORY-002: streaming settings (Section 9.3, D2) ---
#
# Nothing reads these yet -- STORY-005 reads STREAMING_ENABLED, STORY-008 the
# hold-back bound, STORY-010 the coalesce interval. `.env.example` is
# STORY-016's, not this block's.

_STREAM_VARS = ("STREAMING_ENABLED", "STREAM_HOLDBACK_MAX_CHARACTERS", "STREAM_COALESCE_MS")


def test_stream_settings_available_with_documented_defaults(monkeypatch):
    for var in _STREAM_VARS:
        monkeypatch.delenv(var, raising=False)

    result = _settings(DATABASE_URL=_LOCAL_URL)

    assert result.STREAMING_ENABLED is False
    assert result.STREAM_HOLDBACK_MAX_CHARACTERS == 400
    assert result.STREAM_COALESCE_MS == 50


def test_streaming_enabled_parses_the_string_true():
    assert _settings(DATABASE_URL=_LOCAL_URL, STREAMING_ENABLED="true").STREAMING_ENABLED is True


@pytest.mark.parametrize("value", [99, 4001, 0, -1])
def test_stream_holdback_out_of_range_is_a_startup_error(value):
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, STREAM_HOLDBACK_MAX_CHARACTERS=value)

    message = str(exc_info.value)
    assert "STREAM_HOLDBACK_MAX_CHARACTERS" in message
    assert f"got {value}" in message
    assert "Example" in message


@pytest.mark.parametrize("value", [-1, 501])
def test_stream_coalesce_ms_out_of_range_is_a_startup_error(value):
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, STREAM_COALESCE_MS=value)

    message = str(exc_info.value)
    assert "STREAM_COALESCE_MS" in message
    assert f"got {value}" in message
    assert "Example" in message


@pytest.mark.parametrize("value", [100, 4000])
def test_stream_holdback_accepts_the_range_bounds(value):
    result = _settings(DATABASE_URL=_LOCAL_URL, STREAM_HOLDBACK_MAX_CHARACTERS=value)

    assert result.STREAM_HOLDBACK_MAX_CHARACTERS == value


@pytest.mark.parametrize("value", [0, 500])
def test_stream_coalesce_ms_accepts_the_range_bounds(value):
    assert _settings(DATABASE_URL=_LOCAL_URL, STREAM_COALESCE_MS=value).STREAM_COALESCE_MS == value


# --- PRD-022 STORY-009: provider-chain settings (Section 9.3, D5) ---
#
# Nothing but chain_config.load() reads these; the chains file is not opened here.

_CHAIN_VARS = (
    "PROVIDER_CHAINS_FILE",
    "PROVIDER_CHAIN_MAX_CANDIDATES",
    "PROVIDER_CHAIN_DEADLINE_SECONDS",
    "PROVIDER_MIN_ATTEMPT_SECONDS",
)


def test_provider_chain_settings_available_with_documented_defaults(monkeypatch):
    for var in _CHAIN_VARS:
        monkeypatch.delenv(var, raising=False)

    result = _settings(DATABASE_URL=_LOCAL_URL)

    assert result.PROVIDER_CHAINS_FILE == ""
    assert result.PROVIDER_CHAIN_MAX_CANDIDATES == 3
    assert result.PROVIDER_CHAIN_DEADLINE_SECONDS is None
    assert result.PROVIDER_MIN_ATTEMPT_SECONDS == 5.0


@pytest.mark.parametrize("value", [0, 6, -1])
def test_provider_chain_max_candidates_out_of_range_is_a_startup_error(value):
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, PROVIDER_CHAIN_MAX_CANDIDATES=value)

    message = str(exc_info.value)
    assert "PROVIDER_CHAIN_MAX_CANDIDATES" in message and f"got {value}" in message
    assert "Example" in message


@pytest.mark.parametrize("value", [1, 5])
def test_provider_chain_max_candidates_accepts_the_bounds(value):
    result = _settings(DATABASE_URL=_LOCAL_URL, PROVIDER_CHAIN_MAX_CANDIDATES=value)
    assert result.PROVIDER_CHAIN_MAX_CANDIDATES == value


@pytest.mark.parametrize("value", [0, -1])
def test_provider_chain_deadline_must_be_positive(value):
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, PROVIDER_CHAIN_DEADLINE_SECONDS=value)

    message = str(exc_info.value)
    assert "PROVIDER_CHAIN_DEADLINE_SECONDS" in message and f"got {value}" in message
    assert "Example" in message


def test_provider_chain_deadline_accepts_a_positive_value():
    result = _settings(
        DATABASE_URL=_LOCAL_URL,
        PROVIDER_CHAIN_DEADLINE_SECONDS=0.5,
        PROVIDER_MIN_ATTEMPT_SECONDS=0.1,
    )
    assert result.PROVIDER_CHAIN_DEADLINE_SECONDS == 0.5


@pytest.mark.parametrize("value", [0, -1])
def test_provider_min_attempt_must_be_positive(value):
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, PROVIDER_MIN_ATTEMPT_SECONDS=value)

    message = str(exc_info.value)
    assert "PROVIDER_MIN_ATTEMPT_SECONDS" in message and f"got {value}" in message
    assert "Example" in message


@pytest.mark.parametrize("deadline", [5, 4])
def test_provider_min_attempt_not_below_a_set_deadline_is_a_startup_error(deadline):
    with pytest.raises(ValidationError) as exc_info:
        _settings(
            DATABASE_URL=_LOCAL_URL,
            PROVIDER_CHAIN_DEADLINE_SECONDS=deadline,
            PROVIDER_MIN_ATTEMPT_SECONDS=5,
        )

    message = str(exc_info.value)
    assert "PROVIDER_MIN_ATTEMPT_SECONDS" in message
    assert "PROVIDER_CHAIN_DEADLINE_SECONDS" in message


def test_provider_chains_file_without_providers_file_is_a_startup_error(monkeypatch):
    monkeypatch.delenv("PROVIDERS_FILE", raising=False)
    secret_path = "/etc/secret-chains-path.yaml"
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, PROVIDER_CHAINS_FILE=secret_path)

    message = str(exc_info.value)
    assert "PROVIDER_CHAINS_FILE" in message and "PROVIDERS_FILE" in message
    assert secret_path not in message


def test_provider_chains_file_with_providers_file_constructs(tmp_path):
    path = str(tmp_path / "chains.yaml")  # settings never opens it
    result = _settings(
        DATABASE_URL=_LOCAL_URL,
        PROVIDERS_FILE=str(tmp_path / "providers.yaml"),
        PROVIDER_CHAINS_FILE=path,
    )
    assert result.PROVIDER_CHAINS_FILE == path


# --- PRD-023 STORY-004: MCP gateway settings (Section 9.3) ---
#
# Nothing reads these yet; mcp_config.load() (STORY-007) owns the file.

_MCP_VARS_IN_ORDER = (
    "MCP_ENABLED",
    "MCP_CONFIG_FILE",
    "MCP_CALL_TIMEOUT_SECONDS",
    "MCP_MAX_REQUEST_BYTES",
    "MCP_MAX_RESULT_BYTES",
    "MCP_TOOLS_CACHE_SECONDS",
    "MCP_UPSTREAM_SESSION_IDLE_SECONDS",
    "MCP_LINK_WINDOW_SECONDS",
    "MCP_ALLOWED_ORIGINS",
)


def test_mcp_settings_available_with_documented_defaults(monkeypatch):
    for var in _MCP_VARS_IN_ORDER:
        monkeypatch.delenv(var, raising=False)

    result = _settings(DATABASE_URL=_LOCAL_URL)

    assert result.MCP_ENABLED is False
    assert result.MCP_CONFIG_FILE == ""
    assert result.MCP_CALL_TIMEOUT_SECONDS == 60
    assert result.MCP_MAX_REQUEST_BYTES == 1048576
    assert result.MCP_MAX_RESULT_BYTES == 1048576
    assert result.MCP_TOOLS_CACHE_SECONDS == 60
    assert result.MCP_UPSTREAM_SESSION_IDLE_SECONDS == 300
    assert result.MCP_LINK_WINDOW_SECONDS == 300
    assert result.MCP_ALLOWED_ORIGINS == ""
    assert result.mcp_allowed_origins == ()


def test_mcp_enabled_parses_the_string_true():
    assert _settings(DATABASE_URL=_LOCAL_URL, MCP_ENABLED="true").MCP_ENABLED is True


_MCP_BOUNDS = [
    ("MCP_CALL_TIMEOUT_SECONDS", [0, 601], [1, 600]),
    ("MCP_MAX_REQUEST_BYTES", [1023, 0], [1024]),
    ("MCP_MAX_RESULT_BYTES", [1023, 0], [1024]),
    ("MCP_TOOLS_CACHE_SECONDS", [-1, 86401], [0, 86400]),
    ("MCP_UPSTREAM_SESSION_IDLE_SECONDS", [9, 0], [10]),
    ("MCP_LINK_WINDOW_SECONDS", [-1, 86401], [0, 86400]),
]


@pytest.mark.parametrize("var, value", [(var, v) for var, bad, _ in _MCP_BOUNDS for v in bad])
def test_mcp_int_setting_out_of_range_is_a_startup_error(var, value):
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, **{var: value})

    message = str(exc_info.value)
    assert var in message
    assert f"got {value}" in message
    assert "Example" in message


@pytest.mark.parametrize("var, value", [(var, v) for var, _, ok in _MCP_BOUNDS for v in ok])
def test_mcp_int_setting_accepts_the_range_bounds(var, value):
    assert getattr(_settings(DATABASE_URL=_LOCAL_URL, **{var: value}), var) == value


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", ()),
        ("  ,  ", ()),
        ("HTTPS://Example.COM/", ("https://example.com",)),
        ("http://localhost:3000", ("http://localhost:3000",)),
        ("https://a.com:443", ("https://a.com",)),
        ("http://a.com:80/", ("http://a.com",)),
        ("https://a.com:8443", ("https://a.com:8443",)),
        ("http://[::1]:3000", ("http://[::1]:3000",)),
        ("https://a.com, https://A.com/ ,http://b.com", ("https://a.com", "http://b.com")),
    ],
)
def test_mcp_allowed_origins_are_normalized(raw, expected):
    assert _settings(DATABASE_URL=_LOCAL_URL, MCP_ALLOWED_ORIGINS=raw).mcp_allowed_origins == expected


@pytest.mark.parametrize(
    "entry",
    [
        "https://a.com/path",
        "*",
        "https://*.a.com",
        "a.com",
        "//a.com",
        "ftp://a.com",
        "https://a.com?x=1",
        "https://a.com#f",
        "https://u@a.com",
        "https://a.com:notaport",
        "https://",
    ],
)
def test_mcp_allowed_origins_refuses_a_non_origin_entry(entry):
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, MCP_ALLOWED_ORIGINS=f"https://ok.com,{entry}")

    message = str(exc_info.value)
    assert "MCP_ALLOWED_ORIGINS" in message
    assert repr(entry) in message


def test_env_example_documents_the_nine_mcp_vars_in_order_each_with_a_comment():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for var in _MCP_VARS_IN_ORDER:
        assert re.search(rf"(?m)^#.+\n{var}=", text), f"{var} missing from .env.example or its comment line"
    positions = [text.index(f"{var}=") for var in _MCP_VARS_IN_ORDER]
    assert positions == sorted(positions)
