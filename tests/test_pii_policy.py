"""PRD-012 STORY-007: `app/services/pii_policy.py` (Sections 6.2, 6.3, 7/F5).

Covers the policy model, the two built-in policies built from settings, the
`chat` fallback for unknown profile names and its startup log line, and the one
inconsistent combination `load()` refuses. The lifespan wiring is covered in
`tests/test_main.py` (FastAPI) and `tests/test_chat_ui_startup_guard.py`
(Reflex).

Policies are built by `load()` from `settings`, so every test that patches a
setting calls `load()` again. `tests/conftest.py`'s `_default_pii_policy`
restores the policies afterwards, and `_default_pattern_policy` restores the
pattern policy the log tests replace.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import dataclasses
import logging
from typing import get_args

import pytest

from app.config import Settings, settings
from app.models.messages import Role
from app.services import pattern_config, pii_policy
from app.services.pattern_config import BUILT_IN_POLICY
from app.services.pii_policy import (
    FALLBACK_POLICY_NAME,
    PiiConfigError,
    PiiPolicy,
    get_pii_policy,
    load,
)

_LOGGER = "app.services.pii_policy"

#: Every setting a built-in policy reads. Pinned to the class defaults so a
#: developer's `.env` cannot decide a "default settings" assertion.
_POLICY_VARS = (
    "PII_ENTITIES",
    "PII_SCORE_THRESHOLD",
    "PII_ENTITIES_CODE",
    "PII_SCORE_THRESHOLD_CODE",
    "PII_MAX_CHARACTERS_CODE",
    "PII_CODE_REDACT_OUTPUT",
    "PII_CODE_REDACT_SYSTEM",
    "PII_CODE_SKIP_CODE_BLOCKS",
)


@pytest.fixture
def defaults(monkeypatch):
    for name in _POLICY_VARS:
        monkeypatch.setattr(settings, name, Settings.model_fields[name].default)


def _records(caplog):
    return [r for r in caplog.records if r.name == _LOGGER]


def _inconsistent_code_policy():
    """The one combination load() checks: fence skipping without structure-safe replacement."""
    real = pii_policy._build_code_policy()
    return lambda: dataclasses.replace(real, skip_fenced_blocks=True, structure_safe=False)


# --- AC 1: the policy model -------------------------------------------------


def test_pii_policy_is_a_frozen_dataclass_with_the_section_6_2_fields():
    assert [field.name for field in dataclasses.fields(PiiPolicy)] == [
        "name",
        "input_roles",
        "output",
        "skip_fenced_blocks",
        "entities",
        "threshold",
        "max_characters",
        "structure_safe",
    ]
    with pytest.raises(dataclasses.FrozenInstanceError):
        get_pii_policy("chat").output = False


def test_input_roles_use_the_messages_role_vocabulary(defaults):
    """PRD-010's `Role` is the only role vocabulary: no second literal."""
    load()
    assert get_pii_policy("chat").input_roles == frozenset(get_args(Role))
    assert get_pii_policy("code").input_roles <= frozenset(get_args(Role))


# --- AC 2: chat -------------------------------------------------------------


def test_chat_policy_matches_the_section_6_2_table(defaults):
    load()
    chat = get_pii_policy("chat")

    assert chat.name == "chat"
    # Written out, not derived from `Role`: widening `Role` must be noticed here.
    assert chat.input_roles == {"system", "user", "assistant", "tool"}
    assert chat.output is True
    assert chat.skip_fenced_blocks is False
    assert chat.entities == tuple(settings.pii_entities_list)
    assert chat.entities == (
        "PERSON",
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "CREDIT_CARD",
        "US_SSN",
        "IBAN_CODE",
        "LOCATION",
    )
    assert chat.threshold == settings.PII_SCORE_THRESHOLD == 0.35
    assert chat.max_characters is None
    assert chat.structure_safe is False


def test_chat_policy_reads_pii_entities_and_threshold_at_load(defaults, monkeypatch):
    """Built by load(), not frozen at import: a patched setting is seen after load()."""
    monkeypatch.setattr(settings, "PII_ENTITIES", "EMAIL_ADDRESS")
    monkeypatch.setattr(settings, "PII_SCORE_THRESHOLD", 0.6)

    load()

    chat = get_pii_policy("chat")
    assert chat.entities == ("EMAIL_ADDRESS",)
    assert chat.threshold == 0.6


# --- AC 3: code -------------------------------------------------------------


def test_code_policy_defaults(defaults):
    load()
    code = get_pii_policy("code")

    assert code.name == "code"
    assert code.input_roles == {"user", "assistant", "tool"}
    assert code.output is False
    assert code.skip_fenced_blocks is True
    assert code.entities == ("EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "US_SSN", "IBAN_CODE")
    assert code.threshold == 0.40
    assert code.max_characters == 200_000
    assert code.structure_safe is True


def test_code_policy_adds_system_when_pii_code_redact_system(defaults, monkeypatch):
    monkeypatch.setattr(settings, "PII_CODE_REDACT_SYSTEM", True)

    load()

    assert get_pii_policy("code").input_roles == {"system", "user", "assistant", "tool"}


@pytest.mark.parametrize("value", [True, False])
def test_code_policy_maps_output_and_skip_settings(defaults, monkeypatch, value):
    """Each boolean maps to the field it names, and only to it."""
    monkeypatch.setattr(settings, "PII_CODE_REDACT_OUTPUT", value)
    monkeypatch.setattr(settings, "PII_CODE_SKIP_CODE_BLOCKS", not value)

    load()

    code = get_pii_policy("code")
    assert code.output is value
    assert code.skip_fenced_blocks is (not value)
    assert code.input_roles == {"user", "assistant", "tool"}


def test_code_policy_reads_entities_threshold_and_limit_settings(defaults, monkeypatch):
    monkeypatch.setattr(settings, "PII_ENTITIES_CODE", "EMAIL_ADDRESS,PERSON")
    monkeypatch.setattr(settings, "PII_SCORE_THRESHOLD_CODE", 0.7)
    monkeypatch.setattr(settings, "PII_MAX_CHARACTERS_CODE", 5000)

    load()

    code = get_pii_policy("code")
    assert code.entities == ("EMAIL_ADDRESS", "PERSON")
    assert code.threshold == 0.7
    assert code.max_characters == 5000


def test_code_settings_do_not_touch_chat(defaults, monkeypatch):
    """The six code settings apply to `code` only (PRD-012 Section 9.3)."""
    monkeypatch.setattr(settings, "PII_CODE_REDACT_OUTPUT", True)
    monkeypatch.setattr(settings, "PII_CODE_REDACT_SYSTEM", True)
    monkeypatch.setattr(settings, "PII_CODE_SKIP_CODE_BLOCKS", False)
    monkeypatch.setattr(settings, "PII_ENTITIES_CODE", "EMAIL_ADDRESS")
    load()
    after = get_pii_policy("chat")

    monkeypatch.setattr(settings, "PII_CODE_REDACT_OUTPUT", False)
    monkeypatch.setattr(settings, "PII_CODE_REDACT_SYSTEM", False)
    monkeypatch.setattr(settings, "PII_CODE_SKIP_CODE_BLOCKS", True)
    monkeypatch.setattr(settings, "PII_ENTITIES_CODE", Settings.model_fields["PII_ENTITIES_CODE"].default)
    load()

    assert after == get_pii_policy("chat")


# --- AC 4: fallback and its startup log -------------------------------------


def test_fallback_name_is_chat():
    assert FALLBACK_POLICY_NAME == "chat"


def test_unknown_name_resolves_to_chat_not_code():
    """D8: an unknown profile gets the most masking policy, never the permissive one."""
    fallback = get_pii_policy("strict")

    assert fallback is get_pii_policy("chat")
    assert fallback is not get_pii_policy("code")
    assert fallback.name == "chat"
    assert fallback.output is True


def test_get_pii_policy_works_before_load():
    """Built at import, like `pattern_config.get_policy()`: the pipeline and
    every test that never boots an app can resolve a policy."""
    assert get_pii_policy("code").name == "code"
    assert get_pii_policy("chat").name == "chat"


def test_get_pii_policy_does_not_log(caplog):
    """On the request path: the fallback is logged at startup, never per request."""
    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        get_pii_policy("unknown")

    assert _records(caplog) == []


def test_load_logs_nothing_for_the_built_in_pattern_policy(caplog):
    """The built-in pattern policy defines exactly `chat` and `code`."""
    assert set(pattern_config.get_policy().profiles) == {"chat", "code"}

    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        load()

    assert _records(caplog) == []


def test_load_logs_one_info_line_per_profile_without_a_pii_policy(caplog):
    pattern_config._policy = dataclasses.replace(
        BUILT_IN_POLICY,
        profiles={
            **BUILT_IN_POLICY.profiles,
            "strict": BUILT_IN_POLICY.profiles["chat"],
            "agent": BUILT_IN_POLICY.profiles["code"],
        },
    )

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        load()

    records = _records(caplog)
    assert len(records) == 2
    assert all(record.levelno == logging.INFO for record in records)
    messages = [record.getMessage() for record in records]
    # Sorted, so the order is deterministic for operators and for this test.
    assert "'agent'" in messages[0]
    assert "'strict'" in messages[1]
    for message in messages:
        assert "resolves to 'chat'" in message
        assert "'code'" not in message


# --- PiiConfigError ----------------------------------------------------------


def test_load_raises_pii_config_error_for_skip_fenced_blocks_without_structure_safe(monkeypatch):
    before = get_pii_policy("code")
    monkeypatch.setattr(pii_policy, "_build_code_policy", _inconsistent_code_policy())

    with pytest.raises(PiiConfigError, match="skip_fenced_blocks requires structure_safe") as excinfo:
        load()

    assert "'code'" in str(excinfo.value)
    # Nothing is rebound until every check has passed.
    assert get_pii_policy("code") is before


@pytest.mark.parametrize("skip", [True, False])
def test_built_in_policies_pass_the_consistency_check(defaults, monkeypatch, skip):
    monkeypatch.setattr(settings, "PII_CODE_SKIP_CODE_BLOCKS", skip)

    for policy in pii_policy._build_policies().values():
        assert pii_policy._check_consistent(policy) is None
    load()


def test_failed_load_logs_no_fallback_lines(monkeypatch, caplog):
    """The check runs before the log, so a boot that fails says only why."""
    pattern_config._policy = dataclasses.replace(
        BUILT_IN_POLICY,
        profiles={**BUILT_IN_POLICY.profiles, "strict": BUILT_IN_POLICY.profiles["chat"]},
    )
    monkeypatch.setattr(pii_policy, "_build_code_policy", _inconsistent_code_policy())

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        with pytest.raises(PiiConfigError):
            load()

    assert _records(caplog) == []
