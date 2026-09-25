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
