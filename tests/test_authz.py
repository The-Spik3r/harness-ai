import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import json
from pathlib import Path

import pytest

import app.services.authz as authz
from app.config import settings
from app.services.authz import (
    AuthzConfigError,
    MODEL_ALLOWLIST_WILDCARD_ROLES,
    PERMISSION_AUDIT_READ_ALL,
    PERMISSION_AUDIT_READ_OWN,
    PERMISSION_QUERY_BYOK,
    PERMISSION_QUERY_SUBMIT,
    PERMISSION_STATS_READ,
    PermissionDenied,
    ROLE_PERMISSIONS,
    authorize,
    authorize_model,
    load,
)
from app.services.identity import Identity

ALL_PERMISSIONS = [
    PERMISSION_QUERY_SUBMIT,
    PERMISSION_QUERY_BYOK,
    PERMISSION_AUDIT_READ_ALL,
    PERMISSION_AUDIT_READ_OWN,
    PERMISSION_STATS_READ,
]

_MATRIX_CASES = [
    (role, permission, permission in ROLE_PERMISSIONS[role])
    for role in ("admin", "auditor", "user")
    for permission in ALL_PERMISSIONS
]


# --- AC1: full matrix, grant + deny, every cell ---


@pytest.mark.parametrize("role, permission, expected_allowed", _MATRIX_CASES)
def test_matrix_cell_matches_prd_section_7(role, permission, expected_allowed):
    identity = Identity(user_id="u", role=role)

    if expected_allowed:
        assert authorize(identity, permission) is None
    else:
        with pytest.raises(PermissionDenied) as exc_info:
            authorize(identity, permission)
        assert exc_info.value.permission == permission


def test_admin_matrix_matches_prd_exactly():
    assert ROLE_PERMISSIONS["admin"] == set(ALL_PERMISSIONS)


def test_auditor_matrix_matches_prd_exactly():
    assert ROLE_PERMISSIONS["auditor"] == {
        PERMISSION_AUDIT_READ_ALL,
        PERMISSION_AUDIT_READ_OWN,
        PERMISSION_STATS_READ,
    }


def test_user_matrix_matches_prd_exactly():
    assert ROLE_PERMISSIONS["user"] == {
        PERMISSION_QUERY_SUBMIT,
        PERMISSION_AUDIT_READ_OWN,
    }


# --- AC2: unknown role denies, never a fallback grant ---


def test_unknown_role_raises_permission_denied():
    identity = Identity(user_id="u", role="superadmin")

    with pytest.raises(PermissionDenied):
        authorize(identity, PERMISSION_QUERY_SUBMIT)


# --- AC3: permission absent from role's grants raises carrying the permission name ---


def test_denied_permission_carries_the_permission_name():
    identity = Identity(user_id="u", role="user")

    with pytest.raises(PermissionDenied) as exc_info:
        authorize(identity, PERMISSION_QUERY_BYOK)

    assert exc_info.value.permission == PERMISSION_QUERY_BYOK


# --- AC4: granted permission returns None, raises nothing ---


def test_granted_permission_returns_none():
    identity = Identity(user_id="u", role="admin")

    assert authorize(identity, PERMISSION_STATS_READ) is None


# --- AC5: RBAC_ENABLED=false is a single explicit bypass branch, with its own test ---


def test_rbac_disabled_allows_even_an_unknown_role(monkeypatch):
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    identity = Identity(user_id="u", role="superadmin")

    assert authorize(identity, PERMISSION_QUERY_BYOK) is None


# --- STORY-007: load() from RBAC_ROLES_FILE ---


@pytest.fixture
def _reset_role_permissions():
    original = authz.ROLE_PERMISSIONS
    yield
    authz.ROLE_PERMISSIONS = original


def test_load_is_noop_when_roles_file_unset(monkeypatch, _reset_role_permissions):
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", "")
    before = authz.ROLE_PERMISSIONS

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("read_text should not be called when RBAC_ROLES_FILE is empty")

    monkeypatch.setattr(Path, "read_text", _fail_if_called)

    load()

    assert authz.ROLE_PERMISSIONS is before  # same object -- never rebuilt


def test_load_replaces_matrix_wholesale_from_valid_file(tmp_path, monkeypatch, _reset_role_permissions):
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"user": [PERMISSION_QUERY_SUBMIT]}))
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(roles_file))

    load()

    assert authz.ROLE_PERMISSIONS == {"user": {PERMISSION_QUERY_SUBMIT}}

    identity = Identity(user_id="u", role="user")
    assert authorize(identity, PERMISSION_QUERY_SUBMIT) is None
    # PERMISSION_AUDIT_READ_OWN was in the built-in "user" grants and is
    # omitted here -- omission is denial, not inherited from the default.
    with pytest.raises(PermissionDenied):
        authorize(identity, PERMISSION_AUDIT_READ_OWN)
    # "admin" was in the built-in matrix and is entirely absent from the
    # file -- also gone, proving replace rather than a per-role merge.
    with pytest.raises(PermissionDenied):
        authorize(Identity(user_id="a", role="admin"), PERMISSION_STATS_READ)


def test_load_raises_on_malformed_json(tmp_path, monkeypatch, _reset_role_permissions):
    roles_file = tmp_path / "roles.json"
    roles_file.write_text("{not valid json")
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(roles_file))
    before = dict(authz.ROLE_PERMISSIONS)

    with pytest.raises(AuthzConfigError) as exc_info:
        load()

    assert str(roles_file) in str(exc_info.value)
    assert authz.ROLE_PERMISSIONS == before  # no silent fallback mutation


def test_load_raises_on_missing_file(tmp_path, monkeypatch, _reset_role_permissions):
    missing = tmp_path / "does-not-exist.json"
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(missing))

    with pytest.raises(AuthzConfigError) as exc_info:
        load()

    assert str(missing) in str(exc_info.value)


def test_load_raises_on_unrecognized_permission(tmp_path, monkeypatch, _reset_role_permissions):
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"user": [PERMISSION_QUERY_SUBMIT, "query:launch-nukes"]}))
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(roles_file))

    with pytest.raises(AuthzConfigError) as exc_info:
        load()

    assert "query:launch-nukes" in str(exc_info.value)


def test_authorize_does_not_read_file_per_call(tmp_path, monkeypatch, _reset_role_permissions):
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"user": [PERMISSION_QUERY_SUBMIT]}))
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(roles_file))
    load()

    read_calls = []
    original_read_text = Path.read_text

    def _counting_read_text(self, *args, **kwargs):
        read_calls.append(self)
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _counting_read_text)

    for _ in range(3):
        authorize(Identity(user_id="u", role="user"), PERMISSION_QUERY_SUBMIT)

    assert read_calls == []


# --- STORY-011: authorize_model() ---


def test_admin_model_wildcard_allows_any_model():
    identity = Identity(user_id="root", role="admin")
    assert "admin" in MODEL_ALLOWLIST_WILDCARD_ROLES

    assert authorize_model(identity, "some-totally-unlisted-model") is None


def test_user_role_allows_models_in_allowlist():
    identity = Identity(user_id="u", role="user")

    for model in settings.model_allowlist_list:
        assert authorize_model(identity, model) is None


def test_user_role_denies_model_outside_allowlist():
    identity = Identity(user_id="u", role="user")

    with pytest.raises(PermissionDenied) as exc_info:
        authorize_model(identity, "not-a-real-model")

    assert exc_info.value.permission == "query:model:not-a-real-model"


def test_rbac_disabled_bypasses_model_check(monkeypatch):
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    identity = Identity(user_id="u", role="user")

    assert authorize_model(identity, "not-a-real-model") is None
