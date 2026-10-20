import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import dataclasses
import hashlib
import inspect

import pytest

from app.config import settings
# set_user_limits: PRD-013 STORY-008 (D1), per-user overrides on the users row.
from app.db.database import deactivate_user, insert_user, set_user_limits
from app.db.models import User
from app.services import identity as identity_module
from app.services.identity import Identity, hash_token, issue_token, resolve


# --- AC1 / AC2: valid, unknown, malformed, empty, deactivated tokens ---


def test_resolve_returns_identity_for_valid_active_user(temp_db):
    insert_user(User(user_id="ana", role="user", token_hash=hash_token("plaintext-token")))

    assert resolve("plaintext-token") == Identity(user_id="ana", role="user")


def test_resolve_hashes_the_credential_not_the_stored_digest(temp_db):
    insert_user(User(user_id="ana", role="user", token_hash=hash_token("plaintext-token")))

    assert resolve(hash_token("plaintext-token")) is None


def test_resolve_unknown_token_returns_none(temp_db):
    assert resolve("never-issued") is None


def test_resolve_empty_token_returns_none(temp_db):
    assert resolve("") is None


def test_resolve_none_token_returns_none(temp_db):
    assert resolve(None) is None


def test_resolve_malformed_token_returns_none(temp_db):
    insert_user(User(user_id="ana", role="user", token_hash=hash_token("plaintext-token")))

    assert resolve("not-a-real-token-!@#$") is None


def test_resolve_deactivated_user_returns_none(temp_db):
    insert_user(User(user_id="ana", role="user", token_hash=hash_token("plaintext-token")))
    deactivate_user("ana")

    assert resolve("plaintext-token") is None


# --- AC3: ADMIN_TOKEN break-glass ---


def test_resolve_admin_token_returns_synthetic_admin_identity(temp_db):
    # PRD-013 STORY-008 (D4, Section 6.8): only the ADMIN_TOKEN path sets break_glass.
    assert resolve(settings.ADMIN_TOKEN) == Identity(
        user_id="admin", role="admin", break_glass=True
    )


def test_resolve_admin_token_uses_compare_digest(monkeypatch, temp_db):
    calls = []
    original = identity_module.secrets.compare_digest

    def _tracking(a, b):
        calls.append((a, b))
        return original(a, b)

    monkeypatch.setattr(identity_module.secrets, "compare_digest", _tracking)

    result = resolve(settings.ADMIN_TOKEN)

    # PRD-013 STORY-008 (D4, Section 6.8): only the ADMIN_TOKEN path sets break_glass.
    assert result == Identity(user_id="admin", role="admin", break_glass=True)
    assert len(calls) == 1
    assert calls[0] == (settings.ADMIN_TOKEN, settings.ADMIN_TOKEN)


def test_resolve_wrong_token_is_not_treated_as_admin(temp_db):
    assert resolve("close-but-wrong") is None


def test_resolve_admin_token_works_without_users_table(uninitialized_db):
    result = resolve(settings.ADMIN_TOKEN)

    assert result == Identity(user_id="admin", role="admin", break_glass=True)


# --- PRD-013 STORY-008: break_glass and the per-user overrides ---


def test_resolve_admin_token_sets_break_glass_and_no_overrides(temp_db):
    """AC5, first half: the break-glass identity has no `users` row, so both
    overrides are None; it gets the admin role's limits in STORY-010."""
    result = resolve(settings.ADMIN_TOKEN)

    assert result.break_glass is True
    assert result.token_budget_daily is None
    assert result.requests_per_minute is None


def test_resolve_admin_role_user_token_is_not_break_glass(temp_db):
    """AC5, second half: break_glass marks the credential, not the role."""
    insert_user(User(user_id="root", role="admin", token_hash=hash_token("root-token")))

    result = resolve("root-token")

    assert result.role == "admin"
    assert result.break_glass is False


def test_resolve_carries_the_users_limit_overrides(temp_db):
    """AC2: set_user_limits() reaches the Identity on the next resolve(), with
    an untouched column still None."""
    insert_user(User(user_id="dana", role="user", token_hash=hash_token("dana-token")))
    set_user_limits("dana", token_budget_daily=5_000_000)

    result = resolve("dana-token")

    assert result == Identity(
        user_id="dana", role="user", token_budget_daily=5_000_000
    )
    assert result.requests_per_minute is None
    assert result.break_glass is False


def test_resolve_user_without_overrides_carries_none(temp_db):
    insert_user(User(user_id="ana", role="user", token_hash=hash_token("ana-token")))

    result = resolve("ana-token")

    assert (result.token_budget_daily, result.requests_per_minute) == (None, None)


# --- AC5: token issuance, and hashing correctness ---


def test_issue_token_uses_token_urlsafe_with_32_bytes(monkeypatch):
    calls = []
    original = identity_module.secrets.token_urlsafe

    def _tracking(nbytes=None):
        calls.append(nbytes)
        return original(nbytes)

    monkeypatch.setattr(identity_module.secrets, "token_urlsafe", _tracking)

    issue_token()

    assert calls == [32]


def test_issue_token_returns_distinct_high_entropy_values():
    first = issue_token()
    second = issue_token()

    assert first != second
    assert len(first) > 32
    assert len(second) > 32


def test_issue_token_returns_a_string():
    assert isinstance(issue_token(), str)


def test_hash_token_matches_manual_sha256():
    assert hash_token("abc") == hashlib.sha256(b"abc").hexdigest()


def test_hash_token_is_deterministic():
    assert hash_token("same") == hash_token("same")


def test_hash_token_differs_for_different_input():
    assert hash_token("a") != hash_token("b")


def test_hash_token_is_case_sensitive():
    assert hash_token("Token") != hash_token("token")


# --- Identity immutability, equality, and hash_prompt isolation ---


def test_identity_is_frozen():
    ident = Identity(user_id="ana", role="user")

    with pytest.raises(dataclasses.FrozenInstanceError):
        ident.role = "admin"


def test_identity_equality_by_value():
    assert Identity("ana", "user") == Identity("ana", "user")
    assert Identity("ana", "user") != Identity("ana", "admin")


def test_identity_is_hashable():
    {Identity("ana", "user")}


def test_identity_two_positional_args_still_construct():
    """PRD-013 STORY-008 adds three defaulted fields after `role`, so every
    existing `Identity(user_id, role)` across the suite keeps working."""
    ident = Identity("ana", "user")

    assert ident.break_glass is False
    assert ident.token_budget_daily is None
    assert ident.requests_per_minute is None


def test_identity_new_fields_are_frozen_too():
    ident = Identity("ana", "user")

    with pytest.raises(dataclasses.FrozenInstanceError):
        ident.break_glass = True
    with pytest.raises(dataclasses.FrozenInstanceError):
        ident.token_budget_daily = 1


def test_identity_module_does_not_import_hash_prompt():
    source = inspect.getsource(identity_module)

    assert "hash_prompt" not in source
    assert "duplicate_checker" not in source
