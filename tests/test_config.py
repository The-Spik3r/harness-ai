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
